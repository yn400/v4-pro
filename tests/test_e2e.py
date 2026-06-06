"""
V4 Pro E2E 集成测试 — mock LLM 全流程不依赖真实 API。
"""
import json
from pathlib import Path
from unittest.mock import MagicMock

from v4_pro.engine import WorkflowEngine
from v4_pro.llm.base import LLMResponse


def _make_mock_llm_response(content: str = '{"status":"ok","data":{}}') -> LLMResponse:
    """创建模拟的 LLMResponse。"""
    return LLMResponse(
        content=content,
        model="deepseek-chat",
        usage={"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300},
        finish_reason="stop",
    )


class TestE2EPipeline:
    """端到端全流程测试 — mock LLM，不依赖外部 API。"""

    def test_research_step(self):
        """Step 1: 市场研究 — mock 调用。"""
        from v4_pro.llm.base import AbstractLLM
        mock_llm = MagicMock(spec=AbstractLLM)
        mock_llm.single_turn.return_value = _make_mock_llm_response(
            '{"market_analysis": {"target_users": ["test"]}, "recommendation": {"go_no_go": "go"}}'
        )

        import tempfile
        engine = WorkflowEngine(llm=mock_llm, prompts_dir=self._get_prompts_dir())
        ws = Path(tempfile.mkdtemp())
        engine.workspace = ws

        result = engine.research("做一个待办事项 App")
        assert "market_analysis" in result
        assert "recommendation" in result

    def test_verify_standalone(self, tmp_path):
        """独立 verify 命令。"""
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text("import os\ndef greet(name):\n    return f'Hello, {name}!'\n")
        engine = WorkflowEngine(llm=MagicMock(), prompts_dir=self._get_prompts_dir())
        engine.workspace = tmp_path / "ws"
        engine.workspace.mkdir(exist_ok=True)

        report = engine.verify(code_path=str(src))
        assert "checks" in report
        assert "summary" in report

    def test_audit_standalone(self, tmp_path):
        """独立 audit 命令。"""
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text("import pickle\nobj = pickle.load(open('x','rb'))\n")
        from v4_pro.audit.scanner import SecurityAuditor
        report = SecurityAuditor().audit(src)
        assert "findings" in report
        assert "summary" in report

    def test_freeze_standalone(self, tmp_path):
        """独立 freeze 命令。"""
        ws = tmp_path / "ws"
        ws.mkdir()
        design = {
            "modules": [{"name": "api", "responsibility": "API", "public_api": ["get"], "dependencies": ["db"]}],
            "data_model": {"entities": [{"name": "Item", "fields": [{"name": "id", "type": "int"}]}]},
        }
        (ws / "design.json").write_text(json.dumps(design, ensure_ascii=False), encoding="utf-8")

        from v4_pro.freeze.manager import FreezeManager
        spec = FreezeManager(ws).freeze("design.json")
        assert "module_interfaces" in spec
        assert "data_models" in spec

    def test_init_command(self, tmp_path):
        """v4-pro init 命令。"""
        import os
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            from v4_pro.scaffold import init_project
            root = init_project(str(tmp_path / "myproject"))
            assert (Path(root) / "v4_workspace").exists()
        finally:
            os.chdir(old_cwd)

    def test_config_loading(self):
        """配置加载验证。"""
        from v4_pro.config import get_settings
        s = get_settings()
        assert s.llm_provider in ("openai", "zhipu", "tongyi", "anthropic")

    def test_design_step_output(self):
        """验证 design 步骤的数据结构。"""
        from v4_pro.llm.base import AbstractLLM
        mock_llm = MagicMock(spec=AbstractLLM)
        mock_llm.single_turn.return_value = _make_mock_llm_response(
            '{"tech_stack":{"frontend":"React"},"modules":[],"data_model":{"entities":[]}}'
        )

        import tempfile
        engine = WorkflowEngine(llm=mock_llm, prompts_dir=self._get_prompts_dir())
        ws = Path(tempfile.mkdtemp())
        engine.workspace = ws
        # Create prerequisite files
        (ws / "research.json").write_text(json.dumps({"recommendation": {"reasoning": "test"}}), encoding="utf-8")
        (ws / "define.json").write_text(json.dumps({"product_goal": "test"}), encoding="utf-8")

        result = engine.design()
        assert "tech_stack" in result

    def test_generate_step_output(self):
        """验证 generate 步骤的数据结构。"""
        from v4_pro.llm.base import AbstractLLM
        mock_llm = MagicMock(spec=AbstractLLM)
        mock_llm.single_turn.return_value = _make_mock_llm_response(
            '{"files":[{"path":"test.py","language":"python","content":"x=1","description":"xxx"}]}'
        )

        import tempfile
        engine = WorkflowEngine(llm=mock_llm, prompts_dir=self._get_prompts_dir())
        ws = Path(tempfile.mkdtemp())
        engine.workspace = ws
        (ws / "design.json").write_text(json.dumps({"tech_stack": {}}), encoding="utf-8")

        result = engine.generate()
        assert "files" in result
        assert len(result["files"]) >= 1

    @staticmethod
    def _get_prompts_dir() -> Path:
        pkg_dir = Path(__file__).resolve().parent.parent
        prompts = pkg_dir / "prompts"
        if prompts.exists():
            return prompts
        return Path.cwd() / "prompts"

"""
上下文增强模块测试。
"""

import json
import tempfile
from pathlib import Path

from v4_pro.context_enricher import ContextEnricher


class TestContextEnricher:
    """ContextEnricher 单元测试。"""

    def test_empty_workspace(self):
        """测试空工作区。"""
        with tempfile.TemporaryDirectory() as tmp:
            enricher = ContextEnricher(Path(tmp))
            context = enricher.enrich()
            assert context["tech_stack"] == {}
            assert context["coding_standards"] == {}
            assert context["architecture_constraints"] == []

    def test_extract_tech_stack_from_design(self):
        """测试从 design.json 提取技术栈。"""
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            design = {
                "tech_stack": {
                    "language": "Python",
                    "framework": "FastAPI",
                    "database": "PostgreSQL",
                },
                "architecture": {"layers": []},
            }
            (ws / "design.json").write_text(
                json.dumps(design, ensure_ascii=False)
            )

            enricher = ContextEnricher(ws)
            context = enricher.enrich()

            assert context["tech_stack"]["language"] == "Python"
            assert context["tech_stack"]["framework"] == "FastAPI"
            assert context["tech_stack"]["database"] == "PostgreSQL"

    def test_extract_coding_standards(self):
        """测试提取编码规范。"""
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            design = {
                "coding_standards": {
                    "max_line_length": 100,
                    "naming_style": "snake_case",
                    "require_type_annotations": True,
                    "require_docstrings": True,
                    "error_handling_pattern": "try-except",
                },
                "architecture": {"layers": []},
            }
            (ws / "design.json").write_text(
                json.dumps(design, ensure_ascii=False)
            )

            enricher = ContextEnricher(ws)
            context = enricher.enrich()

            assert context["coding_standards"]["max_line_length"] == "100"
            assert context["coding_standards"]["naming_style"] == "snake_case"
            assert context["coding_standards"]["require_type_annotations"] == "True"

    def test_extract_arch_constraints(self):
        """测试提取架构约束。"""
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            design = {
                "architecture": {
                    "layers": [
                        {
                            "name": "controller",
                            "forbidden_dependencies": ["dao", "database"],
                            "allowed_dependencies": ["service"],
                        },
                        {
                            "name": "service",
                            "forbidden_dependencies": ["controller"],
                            "allowed_dependencies": ["repository"],
                        },
                    ],
                },
            }
            (ws / "design.json").write_text(
                json.dumps(design, ensure_ascii=False)
            )

            enricher = ContextEnricher(ws)
            context = enricher.enrich()

            constraints = context["architecture_constraints"]
            assert any("controller" in c and "dao" in c for c in constraints)
            assert any("service" in c and "controller" in c for c in constraints)

    def test_frozen_specs_loaded(self):
        """测试加载冻结规范。"""
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            frozen = {"module_interfaces": {"auth": {}}}
            (ws / "frozen_spec.json").write_text(
                json.dumps(frozen, ensure_ascii=False)
            )

            enricher = ContextEnricher(ws)
            context = enricher.enrich()

            assert context["frozen_specs"] is not None
            assert "module_interfaces" in context["frozen_specs"]

    def test_missing_files_no_error(self):
        """测试缺少文件不会报错。"""
        with tempfile.TemporaryDirectory() as tmp:
            enricher = ContextEnricher(Path(tmp))
            context = enricher.enrich()
            # 应该正常返回空上下文
            assert isinstance(context, dict)
            assert "tech_stack" in context

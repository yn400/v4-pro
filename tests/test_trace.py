"""
决策追踪模块测试。
"""

import json
import tempfile
from pathlib import Path

from v4_pro.trace import TraceLogger


class TestTraceLogger:
    """TraceLogger 单元测试。"""

    def test_log_step_creates_file(self):
        """测试记录步骤后文件被创建。"""
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            tracer = TraceLogger(ws)

            tracer.log_step(
                step="research",
                input_summary="测试需求",
                model="gpt-4o",
                temperature=0.7,
                max_tokens=4096,
            )

            log_path = ws / "trace.log"
            assert log_path.exists()

    def test_log_step_format(self):
        """测试记录格式为合法 JSON Lines。"""
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            tracer = TraceLogger(ws)

            tracer.log_step(
                step="design",
                input_summary="test",
                model="gpt-4o",
            )

            log_path = ws / "trace.log"
            content = log_path.read_text(encoding="utf-8")
            lines = content.strip().split("\n")

            assert len(lines) >= 1
            record = json.loads(lines[0])
            assert record["step"] == "design"
            assert record["model"] == "gpt-4o"
            assert "timestamp" in record
            assert "parameters" in record
            assert "input_summary" in record
            assert "output_hash" in record

    def test_read_all_returns_sorted(self):
        """测试 read_all 返回所有记录。"""
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            tracer = TraceLogger(ws)

            tracer.log_step("research", "req1", model="m1")
            tracer.log_step("design", "req2", model="m2")
            tracer.log_step("generate", "req3", model="m3")

            records = tracer.read_all()
            assert len(records) == 3
            assert records[0]["step"] == "research"
            assert records[1]["step"] == "design"
            assert records[2]["step"] == "generate"

    def test_get_last_step(self):
        """测试获取最近一次指定步骤。"""
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            tracer = TraceLogger(ws)

            tracer.log_step("research", "first", model="m1")
            tracer.log_step("design", "middle", model="m2")
            tracer.log_step("research", "second", model="m3")

            last = tracer.get_last_step("research")
            assert last is not None
            assert last["input_summary"] == "second"
            assert last["model"] == "m3"

    def test_get_last_step_not_found(self):
        """测试获取不存在的步骤返回 None。"""
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            tracer = TraceLogger(ws)

            result = tracer.get_last_step("nonexistent")
            assert result is None

    def test_empty_log_returns_empty_list(self):
        """测试空日志返回空列表。"""
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            tracer = TraceLogger(ws)
            assert tracer.read_all() == []

    def test_input_summary_truncation(self):
        """测试输入摘要自动截断。"""
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            tracer = TraceLogger(ws)

            long_input = "x" * 1000
            tracer.log_step("test", long_input)

            records = tracer.read_all()
            assert len(records[0]["input_summary"]) <= 500

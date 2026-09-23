"""
AI 代码异味检测器测试。
"""

import tempfile
from pathlib import Path

from v4_pro.smells import AiSmellDetector


def _scan(code: str, filename: str = "app.py") -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / filename
        f.write_text(code, encoding="utf-8")
        return AiSmellDetector().scan(Path(tmp))


class TestExceptSwallow:
    def test_detect_bare_except_pass(self):
        r = _scan("try:\n    do_x()\nexcept:\n    pass\n")
        assert any(i["rule_id"] == "SMELL/except-swallow" for i in r["issues"])

    def test_detect_exception_pass(self):
        r = _scan("try:\n    do_x()\nexcept Exception:\n    pass\n")
        assert any(i["rule_id"] == "SMELL/except-swallow" for i in r["issues"])

    def test_logged_exception_not_swallow(self):
        r = _scan(
            "import logging\n"
            "try:\n    do_x()\nexcept Exception:\n"
            "    logging.exception('failed')\n"
        )
        assert not any(i["rule_id"] == "SMELL/except-swallow" for i in r["issues"])
        # 但 overbroad-except 仍应提示
        assert any(i["rule_id"] == "SMELL/overbroad-except" for i in r["issues"])

    def test_specific_exception_with_logic_not_flagged(self):
        r = _scan("try:\n    do_x()\nexcept ValueError:\n    handle()\n")
        assert not any(
            i["rule_id"] in ("SMELL/except-swallow", "SMELL/overbroad-except")
            for i in r["issues"]
        )


class TestStubDetection:
    def test_detect_pass_body(self):
        r = _scan("def process(data):\n    pass\n")
        assert any(i["rule_id"] == "SMELL/stub-implementation" for i in r["issues"])

    def test_detect_not_implemented(self):
        r = _scan("def process(data):\n    raise NotImplementedError\n")
        assert any(i["rule_id"] == "SMELL/stub-implementation" for i in r["issues"])

    def test_detect_docstring_only(self):
        r = _scan('def process(data):\n    """处理数据。"""\n')
        assert any(i["rule_id"] == "SMELL/stub-implementation" for i in r["issues"])

    def test_real_implementation_not_flagged(self):
        r = _scan("def process(data):\n    return [x * 2 for x in data]\n")
        assert not any(i["rule_id"] == "SMELL/stub-implementation" for i in r["issues"])

    def test_abstract_method_exempt(self):
        code = (
            "from abc import ABC, abstractmethod\n"
            "class Repo(ABC):\n"
            "    @abstractmethod\n"
            "    def fetch(self, id):\n"
            "        ...\n"
        )
        r = _scan(code)
        assert not any(i["rule_id"] == "SMELL/stub-implementation" for i in r["issues"])

    def test_stub_in_test_file_exempt(self):
        r = _scan("def fake_process(data):\n    pass\n", filename="test_app.py")
        assert not any(i["rule_id"] == "SMELL/stub-implementation" for i in r["issues"])


class TestDuplicateFunction:
    def test_detect_duplicate(self):
        code = "def calc(x):\n    return x + 1\n\ndef calc(x):\n    return x * 2\n"
        r = _scan(code)
        assert any(i["rule_id"] == "SMELL/duplicate-function" for i in r["issues"])

    def test_unique_functions_ok(self):
        code = "def calc(x):\n    return x + 1\n\ndef apply(x):\n    return x * 2\n"
        r = _scan(code)
        assert not any(i["rule_id"] == "SMELL/duplicate-function" for i in r["issues"])


class TestPlaceholders:
    def test_detect_placeholder_key(self):
        code = 'API_KEY = "YOUR_API_KEY_HERE"\nclient = Client(API_KEY)\n'
        r = _scan(code)
        assert any(i["rule_id"] == "SMELL/placeholder-secret" for i in r["issues"])

    def test_detect_changeme(self):
        code = 'password = "changeme"\n'
        r = _scan(code)
        assert any(i["rule_id"] == "SMELL/placeholder-secret" for i in r["issues"])

    def test_detect_example_com(self):
        code = 'WEBHOOK = "https://example.com/api"\n'
        r = _scan(code)
        assert any(i["rule_id"] == "SMELL/placeholder-value" for i in r["issues"])

    def test_placeholder_in_test_exempt(self):
        code = 'FAKE_KEY = "YOUR_API_KEY_HERE"\n'
        r = _scan(code, filename="test_config.py")
        assert not any(
            i["rule_id"] in ("SMELL/placeholder-secret", "SMELL/placeholder-value")
            for i in r["issues"]
        )


class TestJsSmells:
    def test_empty_catch(self):
        r = _scan("try { risky(); } catch (e) { }", filename="app.js")
        assert any(i["rule_id"] == "SMELL/js-empty-catch" for i in r["issues"])

    def test_js_placeholder(self):
        r = _scan('const key = "YOUR_API_KEY";', filename="app.js")
        assert any(i["rule_id"] == "SMELL/placeholder-secret" for i in r["issues"])


class TestTodoHotspot:
    def test_todo_density(self):
        code = "".join(f"# TODO item {i}\nx{i} = {i}\n" for i in range(6))
        r = _scan(code)
        assert any(i["rule_id"] == "SMELL/todo-hotspot" for i in r["issues"])

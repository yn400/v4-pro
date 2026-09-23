"""
幻觉依赖检测器测试 — resolver 注入，全程离线。
"""

import tempfile
from pathlib import Path

from v4_pro.phantom import NODE_BUILTINS, PhantomDependencyChecker


def _scan(code: str, declared: set[str] | None = None, resolver=None,
          allowlist: list[str] | None = None, filename: str = "app.py") -> dict:
    """扫描一段代码，用注入的 resolver 模拟注册表。"""
    if resolver is None:
        resolver = lambda name, eco: "missing"  # noqa: E731 — 默认: 一切都不存在
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / filename).write_text(code, encoding="utf-8")
        # 本地模块伪装: declared 里的名字建成包目录
        for name in (declared or set()):
            pkg = Path(tmp) / name.replace("-", "_")
            pkg.mkdir(exist_ok=True)
            (pkg / "__init__.py").touch()
        checker = PhantomDependencyChecker(
            resolver=resolver, allowlist=allowlist or [],
            cache_path=Path(tmp) / ".v4pro_cache.json",
        )
        return checker.scan(Path(tmp))


class TestPhantomPy:
    def test_hallucinated_package_is_p0(self):
        r = _scan("import fastcsvparser\nfrom superxml import parse\n")
        p0 = [i for i in r["issues"] if i["severity"] == "P0"]
        assert len(p0) == 2
        assert all(i["rule_id"] == "PHANTOM/pypi" for i in p0)

    def test_real_world_hallucination(self):
        # AI 常编造的包名（研究文献中的高频幻觉名）
        r = _scan("import pandas as pd\nimport matplotlibx\n")
        p0 = [i for i in r["issues"] if i["severity"] == "P0"]
        assert [i for i in p0 if "matplotlibx" in i["title"]]

    def test_local_package_not_flagged(self):
        # fastcsvparser 建成本地包目录后不再报
        r = _scan("import fastcsvparser\nfastcsvparser.read()\n",
                  declared={"fastcsvparser"})
        assert not [i for i in r["issues"] if i["severity"] == "P0"]

    def test_relative_import_skipped(self):
        r = _scan("from .utils import helper\nfrom ..pkg import x\n")
        assert r["issues"] == []

    def test_stdlib_skipped(self):
        r = _scan("import os\nimport json\nfrom pathlib import Path\nimport xml.etree.ElementTree\n")
        assert r["issues"] == []

    def test_allowlist(self):
        r = _scan("import fastcsvparser\n", allowlist=["fastcsvparser"])
        assert not [i for i in r["issues"] if i["severity"] == "P0"]

    def test_exists_but_undeclared_is_p2(self):
        # 用一个确定不在本机环境里的包名，避免依赖测试环境的已安装包
        r = _scan("import someveryrarepkg\n", resolver=lambda n, e: "exists")
        assert any(
            i["rule_id"] == "PHANTOM/undeclared" and i["severity"] == "P2"
            for i in r["issues"]
        )
        assert not [i for i in r["issues"] if i["severity"] == "P0"]

    def test_network_failure_never_blocks(self):
        r = _scan("import mysterypkg\n", resolver=lambda n, e: "unknown")
        assert r["passed"] is True
        assert any(i["rule_id"] == "PHANTOM/unverified" for i in r["issues"])

    def test_import_in_function_detected(self):
        r = _scan("def load():\n    import fakecsv\n    return fakecsv\n")
        assert any(i["severity"] == "P0" for i in r["issues"])


class TestPhantomJs:
    def test_hallucinated_npm_package(self):
        r = _scan(
            "const fastCsv = require('fast-csv-pro');\n",
            filename="app.js",
        )
        p0 = [i for i in r["issues"] if i["severity"] == "P0"]
        assert len(p0) == 1
        assert "fast-csv-pro" in p0[0]["title"]

    def test_relative_require_skipped(self):
        r = _scan("const u = require('./utils');\nconst v = require('../lib/x');\n",
                  filename="app.js")
        assert r["issues"] == []

    def test_node_builtin_skipped(self):
        code = "const fs = require('fs');\nconst path = require('path');\n"
        r = _scan(code, filename="app.js")
        assert r["issues"] == []
        assert "fs" in NODE_BUILTINS

    def test_esm_import(self):
        r = _scan("import { lol } from 'totally-real-utils';\n", filename="app.ts")
        assert any(i["severity"] == "P0" for i in r["issues"])

    def test_scoped_package(self):
        r = _scan("import x from '@fakecorp/magic-sdk';\n", filename="app.js")
        assert any(i["severity"] == "P0" and "@fakecorp/magic-sdk" in i["title"] for i in r["issues"])


class TestCache:
    def test_second_scan_uses_cache(self):
        calls = []

        def resolver(name, eco):
            calls.append(name)
            return "missing"

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text("import ghostpkg\n")
            cache = Path(tmp) / ".v4pro_cache.json"
            c1 = PhantomDependencyChecker(resolver=resolver, cache_path=cache)
            c1.scan(Path(tmp))
            n_first = len(calls)
            c2 = PhantomDependencyChecker(resolver=resolver, cache_path=cache)
            c2.scan(Path(tmp))
            assert n_first == 1
            assert c2.stats["cache_hits"] == 1

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


class TestTyposquat:
    """盲区 B: 碰瓷包（存在但名字模仿热门包）。"""

    def test_typosquat_import_flagged_p1(self):
        # requets 与 requests 编辑距离 1，且真实存在于注册表 → P1
        r = _scan("import requets\n", resolver=lambda n, e: "exists")
        hits = [i for i in r["issues"] if i["rule_id"] == "PHANTOM/typosquat"]
        assert len(hits) == 1
        assert hits[0]["severity"] == "P1"
        assert "requests" in hits[0]["title"]

    def test_typosquat_and_fresh_escalates_p0(self):
        # 碰瓷 + 新注册 → 升级 P0
        now = __import__("time").time()
        r = _scan("import requets\n",
                  resolver=lambda n, e: ("exists", now - 10 * 86400))
        hits = [i for i in r["issues"] if i["rule_id"] == "PHANTOM/typosquat"]
        assert len(hits) == 1 and hits[0]["severity"] == "P0"

    def test_famous_name_itself_not_flagged(self):
        # requests 本尊不应被当成碰瓷
        r = _scan("import requests\n",
                  resolver=lambda n, e: ("exists", __import__("time").time() - 3000 * 86400))
        assert not [i for i in r["issues"] if i["rule_id"] == "PHANTOM/typosquat"]

    def test_missing_plus_typosquat_notes_similarity(self):
        r = _scan("import requets\n", resolver=lambda n, e: "missing")
        p0 = [i for i in r["issues"] if i["severity"] == "P0"]
        assert len(p0) == 1 and "requests" in p0[0]["title"]

    def test_short_names_skipped(self):
        # 3 字符以下名字不做碰瓷比对（噪声太大）
        r = _scan("import rqx\n", resolver=lambda n, e: "exists")
        assert not [i for i in r["issues"] if i["rule_id"] == "PHANTOM/typosquat"]

    def test_npm_typosquat(self):
        r = _scan("import x from 'exprss';\n", filename="app.js",
                  resolver=lambda n, e: "exists")
        hits = [i for i in r["issues"] if i["rule_id"] == "PHANTOM/typosquat"]
        assert len(hits) == 1 and hits[0]["severity"] == "P1"


class TestFreshPackage:
    """盲区 C: 新注册包 + 未声明。"""

    def test_fresh_undeclared_p2(self):
        now = __import__("time").time()
        r = _scan("import someveryrarepkg\n",
                  resolver=lambda n, e: ("exists", now - 30 * 86400))
        hits = [i for i in r["issues"] if i["rule_id"] == "PHANTOM/fresh-package"]
        assert len(hits) == 1 and hits[0]["severity"] == "P2"
        assert not [i for i in r["issues"] if i["severity"] in ("P0", "P1")]

    def test_old_package_not_fresh_flag(self):
        now = __import__("time").time()
        r = _scan("import someveryrarepkg\n",
                  resolver=lambda n, e: ("exists", now - 3000 * 86400))
        assert not [i for i in r["issues"] if i["rule_id"] == "PHANTOM/fresh-package"]

    def test_unknown_created_no_fresh_flag(self):
        r = _scan("import someveryrarepkg\n", resolver=lambda n, e: "exists")
        assert not [i for i in r["issues"] if i["rule_id"] == "PHANTOM/fresh-package"]


class TestDeclaredDepsScan:
    """盲区 A: 依赖清单文件本身被幻觉污染。"""

    def test_requirements_hallucinated_package_p0(self, tmp_path):
        req = tmp_path / "requirements.txt"
        req.write_text("requests==2.31.0\nfastcsvparser>=1.0\n")
        (tmp_path / "app.py").write_text("import requests\n")

        calls = []

        def resolver(name, eco):
            calls.append(name)
            return "exists" if name == "requests" else "missing"

        checker = PhantomDependencyChecker(
            resolver=resolver, cache_path=tmp_path / ".v4pro_cache.json",
            installed={"requests"},
        )
        r = checker.scan(tmp_path)
        p0 = [i for i in r["issues"] if i["severity"] == "P0"]
        assert len(p0) == 1
        assert "fastcsvparser" in p0[0]["title"]
        assert p0[0]["rule_id"] == "PHANTOM/declared-pypi"
        assert p0[0]["line"] == 2  # requirements.txt 里那一行

    def test_declared_own_package_skipped(self, tmp_path):
        # pyproject 声明的是项目自身名字 → 不查
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "mypkg"\ndependencies = ["mypkg-sub"]\n'
        )
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").touch()
        (tmp_path / "mypkg_sub").mkdir()
        (tmp_path / "mypkg_sub" / "__init__.py").touch()
        checker = PhantomDependencyChecker(
            resolver=lambda n, e: "missing", cache_path=tmp_path / ".c.json",
        )
        r = checker.scan(tmp_path)
        assert r["issues"] == []

    def test_declared_private_installed_package_skipped(self, tmp_path):
        # 声明了私有内部包（本机已装、公网 404）→ 不误报
        (tmp_path / "requirements.txt").write_text("my-internal-pkg==1.0\n")
        checker = PhantomDependencyChecker(
            resolver=lambda n, e: "missing", cache_path=tmp_path / ".c.json",
            installed={"my-internal-pkg"},
        )
        r = checker.scan(tmp_path)
        assert r["issues"] == []

    def test_declared_typosquat_p1(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("requets>=1.0\n")
        checker = PhantomDependencyChecker(
            resolver=lambda n, e: "exists", cache_path=tmp_path / ".c.json",
        )
        r = checker.scan(tmp_path)
        hits = [i for i in r["issues"] if i["rule_id"] == "PHANTOM/typosquat"]
        assert len(hits) == 1 and hits[0]["severity"] == "P1"

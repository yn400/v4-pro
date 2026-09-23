"""
幻觉依赖检测器（Phantom Dependency Checker）— v4-pro 的核心能力。

AI 生成的代码经常 import 根本不存在的包。攻击者会抢注这些名字投放恶意代码，
这类攻击被称为 slopsquatting（CSA 2026-04 研究笔记）。
本模块在「pip install 之前」把幻觉包揪出来。

判定流程（Python import / JS import+require）:
  1. 标准库（sys.stdlib_module_names / Node 内置模块）      → 放行
  2. 相对导入 / 项目内模块                                  → 放行
  3. 已声明依赖（pyproject.toml / requirements*.txt / package.json）
     或本机已安装（importlib.metadata）                     → 放行
  4. 查注册表（PyPI / npm registry，带本地缓存）:
     - 确认不存在  → P0  幻觉依赖（slopsquatting 风险）
     - 存在但未声明 → P2  未声明依赖
     - 网络失败/离线 → P3  无法核实（永不阻断门禁）
"""

from __future__ import annotations

import ast
import json
import logging
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Node.js 内置模块（常用集）
NODE_BUILTINS = {
    "assert", "async_hooks", "buffer", "child_process", "cluster", "console",
    "constants", "crypto", "dgram", "diagnostics_channel", "dns", "domain",
    "events", "fs", "http", "http2", "https", "inspector", "module", "net",
    "os", "path", "perf_hooks", "process", "punycode", "querystring",
    "readline", "repl", "stream", "string_decoder", "sys", "timers", "tls",
    "trace_events", "tty", "url", "util", "v8", "vm", "wasi", "worker_threads", "zlib",
}

_PY_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)")

_JS_IMPORT_PATTERNS = [
    re.compile(r"""\brequire\s*\(\s*['"]([^'"]+)['"]\s*\)"""),
    re.compile(r"""\bfrom\s+['"]([^'"]+)['"]"""),
    re.compile(r"""\bimport\s*\(\s*['"]([^'"]+)['"]\s*\)"""),
    re.compile(r"""\bimport\s+['"]([^'"]+)['"]"""),  # side-effect import
]


class PhantomDependencyChecker:
    """幻觉依赖检测器。resolver 可注入以便离线测试。"""

    def __init__(
        self,
        resolver: Callable[[str, str], str] | None = None,
        cache_path: Path | None = None,
        offline: bool = False,
        allowlist: list[str] | None = None,
        timeout: int = 5,
        ttl_exists: int = 30,
        ttl_missing: int = 7,
    ):
        self._resolver = resolver  # (name, ecosystem) -> "exists"|"missing"|"unknown"
        self._cache_path = cache_path or Path(".v4pro_cache.json")
        self._offline = offline
        self._allowlist = {a.lower() for a in (allowlist or [])}
        self._timeout = timeout
        self._ttl_exists = ttl_exists * 86400
        self._ttl_missing = ttl_missing * 86400
        self._cache: dict[str, dict] = {}
        self._load_cache()
        self.stats = {"registry_checked": 0, "cache_hits": 0}

    # ── 入口 ─────────────────────────────────────────────────

    def scan(self, code_dir: Path) -> dict[str, Any]:
        code_dir = Path(code_dir)
        if not code_dir.exists():
            return {"passed": True, "issues": [], "summary": {"files_scanned": 0}}

        declared = self._collect_declared(code_dir)
        local_modules = self._collect_local_modules(code_dir)
        installed = self._installed_dists()

        py_imports = self._scan_python_imports(code_dir)
        js_imports = self._scan_js_imports(code_dir)

        issues: list[dict] = []
        for name, files in sorted(py_imports.items()):
            issues.extend(self._judge(name, files, "pypi", declared, local_modules, installed, code_dir))
        for name, files in sorted(js_imports.items()):
            issues.extend(self._judge(name, files, "npm", declared, local_modules, installed, code_dir))

        for i, issue in enumerate(issues):
            issue.setdefault("id", f"PHANTOM-{i+1:03d}")
            issue.setdefault("category", "phantom_dependency")

        self._save_cache()
        p0 = [x for x in issues if x["severity"] == "P0"]
        return {
            "passed": not p0,
            "issues": issues,
            "summary": {
                "declared_packages": len(declared),
                "unique_imports": len(py_imports) + len(js_imports),
                "registry_checked": self.stats["registry_checked"],
                "cache_hits": self.stats["cache_hits"],
            },
        }

    # ── 判定 ─────────────────────────────────────────────────

    def _judge(
        self,
        name: str,
        files: list[tuple[Path, int]],
        ecosystem: str,
        declared: set[str],
        local_modules: set[str],
        installed: set[str],
        code_dir: Path,
    ) -> list[dict]:
        key = name.lower()
        # PyPI 归一化: PEP 503 — 小写、下划线与连字符等价
        norm = key.replace("_", "-") if ecosystem == "pypi" else key
        if key in self._allowlist or norm in self._allowlist:
            return []

        file_ref = f"{files[0][0].name}:{files[0][1]}"
        more = f" 等 {len(files)} 处" if len(files) > 1 else ""

        if ecosystem == "pypi":
            if name in local_modules or key in local_modules or norm in local_modules:
                return []
            if norm in declared or key in {d.replace("_", "-") for d in installed}:
                return []
        else:
            if name in NODE_BUILTINS or name.startswith("node:"):
                return []
            if name.startswith(".") or name.startswith("/") or re.match(r"^@/", name):
                return []
            if name in declared or key in declared:
                return []

        verdict = self._resolve(name, ecosystem)

        if verdict == "missing":
            return [{
                "severity": "P0",
                "rule_id": f"PHANTOM/{ecosystem}",
                "title": f"幻觉依赖: {name} 在 {'PyPI' if ecosystem == 'pypi' else 'npm registry'} 上不存在"
                         f"（{file_ref}{more}）——AI 编造的包名，攻击者可能已抢注（slopsquatting），"
                         "pip install / npm install 会直接拉到恶意代码",
                "file": str(files[0][0]),
                "line": files[0][1],
                "suggestion": f"确认 {name} 是否为正确包名（查官方文档）；"
                              "若为内部包请加入 .v4pro.json 的 phantom.allowlist",
            }]
        if verdict == "exists":
            return [{
                "severity": "P2",
                "rule_id": "PHANTOM/undeclared",
                "title": f"未声明依赖: {name} 可在注册表找到，但未出现在项目依赖清单中"
                         f"（{file_ref}{more}）",
                "file": str(files[0][0]),
                "line": files[0][1],
                "suggestion": "把依赖写入 pyproject.toml / package.json，锁定版本",
            }]
        # unknown — 离线或网络失败，绝不阻断
        return [{
            "severity": "P3",
            "rule_id": "PHANTOM/unverified",
            "title": f"无法核实依赖: {name}（{file_ref}）——离线模式或注册表不可达",
            "file": str(files[0][0]),
            "line": files[0][1],
            "suggestion": "联网后重新运行 v4-pro verify 完成核实",
        }]

    def _resolve(self, name: str, ecosystem: str) -> str:
        cache_key = f"{ecosystem}:{name.lower()}"
        now = time.time()
        entry = self._cache.get(cache_key)
        if entry:
            age = now - entry.get("t", 0)
            if entry.get("e") and age < self._ttl_exists:
                self.stats["cache_hits"] += 1
                return "exists"
            if not entry.get("e") and age < self._ttl_missing:
                self.stats["cache_hits"] += 1
                return "missing"
        if self._resolver:
            verdict = self._resolver(name, ecosystem)
        elif self._offline:
            return "unknown"
        else:
            verdict = self._registry_lookup(name, ecosystem)
        if verdict in ("exists", "missing"):
            self.stats["registry_checked"] += 1
            self._cache[cache_key] = {"e": verdict == "exists", "t": now}
        return verdict

    @staticmethod
    def _registry_lookup(name: str, ecosystem: str) -> str:
        try:
            if ecosystem == "pypi":
                url = f"https://pypi.org/pypi/{name}/json"
            else:
                url = "https://registry.npmjs.org/" + urllib.request.quote(name, safe="")
            req = urllib.request.Request(url, headers={"User-Agent": "v4-pro-phantom-check"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    return "exists"
                return "unknown"
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return "missing"
            return "unknown"
        except (urllib.error.URLError, TimeoutError, OSError):
            return "unknown"

    # ── 依赖清单 ─────────────────────────────────────────────

    def _collect_declared(self, code_dir: Path) -> set[str]:
        declared: set[str] = set()
        # pyproject.toml（tomllib 优先，3.10 降级正则）
        pyproject = code_dir / "pyproject.toml"
        if pyproject.is_file():
            try:
                text = pyproject.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                text = ""
            try:
                import tomllib
                data = tomllib.loads(text)
                deps = data.get("project", {}).get("dependencies", []) \
                    + data.get("build-system", {}).get("requires", [])
                for d in deps:
                    declared.add(_normalize_pypi_name(d))
            except ImportError:
                m = re.search(r"^dependencies\s*=\s*\[(.*?)\]", text, re.S | re.M)
                if m:
                    for item in re.findall(r"""['"]([^'"]+)['"]""", m.group(1)):
                        declared.add(_normalize_pypi_name(item))
            except Exception:  # v4pro:ignore=SMELL/except-swallow pyproject 已用 tomllib 解析过，此处为 3.10 正则降级兜底
                pass
        # requirements*.txt
        for req in code_dir.glob("requirements*.txt"):
            try:
                for line in req.read_text(encoding="utf-8").split("\n"):
                    line = line.strip()
                    if line and not line.startswith(("-", "#")):
                        declared.add(_normalize_pypi_name(line))
            except (OSError, UnicodeDecodeError):
                continue
        # setup.py / setup.cfg 粗略兜底
        for cfg in ("setup.py", "setup.cfg"):
            p = code_dir / cfg
            if p.is_file():
                try:
                    for m in re.finditer(
                        r"""['"]([A-Za-z0-9_.\-]+)(\[[^\]]*\])?(==|>=|<=|~=|>|<)?""",  # noqa: E501
                        p.read_text(encoding="utf-8"),
                    ):
                        name = m.group(1)
                        if name and not name.startswith(("_", ".")):
                            declared.add(_normalize_pypi_name(name))
                except (OSError, UnicodeDecodeError):
                    pass
        # package.json
        pkg = code_dir / "package.json"
        if pkg.is_file():
            try:
                data = json.loads(pkg.read_text(encoding="utf-8"))
                for section in ("dependencies", "devDependencies", "peerDependencies"):
                    for name in data.get(section, {}):
                        declared.add(name.lower())
            except (OSError, json.JSONDecodeError):
                pass
        return declared

    @staticmethod
    def _collect_local_modules(code_dir: Path) -> set[str]:
        locals_: set[str] = set()
        # 被扫描目录自身若为包（含 __init__.py），其名字即可导入
        if (code_dir / "__init__.py").is_file():
            locals_.add(code_dir.name)
        # 全树所有 python 包目录与单文件模块都可导入
        for path in code_dir.rglob("__init__.py"):
            if path.is_file():
                locals_.add(path.parent.name)
        for child in code_dir.iterdir():
            if child.is_file() and child.suffix == ".py":
                locals_.add(child.stem)
        # src 布局
        src = code_dir / "src"
        if src.is_dir():
            for child in src.iterdir():
                if child.is_dir() and (child / "__init__.py").is_file():
                    locals_.add(child.name)
                elif child.is_file() and child.suffix == ".py":
                    locals_.add(child.stem)
        return locals_

    @staticmethod
    def _installed_dists() -> set[str]:
        try:
            from importlib import metadata
            return {d.metadata["Name"].lower() for d in metadata.distributions() if d.metadata["Name"]}
        except Exception:  # v4pro:ignore=SMELL/except-swallow 已安装包枚举失败不阻断门禁，视为空集
            return set()

    # ── import 提取 ──────────────────────────────────────────

    def _scan_python_imports(self, code_dir: Path) -> dict[str, list[tuple[Path, int]]]:
        found: dict[str, list[tuple[Path, int]]] = {}
        for f in self._source_files(code_dir, {".py"}):
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"))
            except (SyntaxError, OSError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level and node.level > 0:
                        continue  # 相对导入
                    if node.module:
                        names = [node.module]
                for full in names:
                    top = full.split(".")[0]
                    if top in ("__future__",) or top in _PY_STDLIB_COVER:
                        continue
                    found.setdefault(top, []).append((f, node.lineno))
        return found

    def _scan_js_imports(self, code_dir: Path) -> dict[str, list[tuple[Path, int]]]:
        found: dict[str, list[tuple[Path, int]]] = {}
        for f in self._source_files(code_dir, {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}):
            try:
                source = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for pat in _JS_IMPORT_PATTERNS:
                for m in pat.finditer(source):
                    spec = m.group(1)
                    if spec.startswith((".", "/")) or re.match(r"^@/", spec):
                        continue
                    if spec.startswith("node:"):
                        continue
                    if spec.startswith("@"):
                        parts = spec.split("/")
                        top = "/".join(parts[:2]) if len(parts) >= 2 else spec
                    else:
                        top = spec.split("/")[0]
                    if top in NODE_BUILTINS:
                        continue
                    line = source[:m.start()].count("\n") + 1
                    found.setdefault(top, []).append((f, line))
        return found

    # ── 缓存 ─────────────────────────────────────────────────

    def _load_cache(self) -> None:
        try:
            if self._cache_path.is_file():
                self._cache = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._cache = {}

    def _save_cache(self) -> None:
        try:
            self._cache_path.write_text(
                json.dumps(self._cache, ensure_ascii=False, indent=0), encoding="utf-8"
            )
        except OSError:
            pass

    @staticmethod
    def _source_files(root: Path, extensions: set[str]) -> list[Path]:
        exclude_dirs = {
            "__pycache__", "node_modules", ".git", ".venv", "venv",
            ".tox", "egg-info", "dist", "build", ".mypy_cache",
        }
        files = []
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix.lower() in extensions:
                if not set(path.parts) & exclude_dirs:
                    files.append(path)
        return files


def _normalize_pypi_name(req: str) -> str:
    """'requests[security]>=2.0 # comment' -> 'requests'"""
    name = re.split(r"[\[><=!~;\s]", req.strip(), maxsplit=1)[0]
    return name.lower().replace("_", "-")


# Python 标准库顶层名（3.10-3.13 常用集 + sys.stdlib_module_names 动态补充）
import sys  # noqa: E402

_PY_STDLIB_COVER: set[str] = set(getattr(sys, "stdlib_module_names", ())) | {
    "typing_extensions",  # 常见类型桩包，运行期常随依赖安装
}

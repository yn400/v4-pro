"""
幻觉依赖检测器（Phantom Dependency Checker）— v4-pro 的核心能力。

AI 生成的代码经常 import 根本不存在的包。攻击者会抢注这些名字投放恶意代码，
这类攻击被称为 slopsquatting（CSA 2026-04 研究笔记）。
本模块在「pip install 之前」把幻觉包和可疑包揪出来。

三层判定（Python import / JS import+require / 依赖清单文件）:
  1. 标准库（sys.stdlib_module_names / Node 内置模块）       → 放行
  2. 相对导入 / 项目内模块                                   → 放行
  3. 本机已安装（importlib.metadata）                        → 放行
  4. 注册表查证（PyPI / npm registry，带本地缓存）:
     - 依赖清单里声明了不存在的包        → P0  幻觉依赖（直接安装即中招）
     - 代码 import 了不存在的包          → P0  幻觉依赖（slopsquatting 风险）
     - 包名与热门包编辑距离 ≤2 且新注册  → P0  疑似碰瓷 + 新包（近似必然攻击）
     - 包名与热门包编辑距离 ≤2           → P1  疑似 typosquatting 碰瓷包
     - 存在、未声明、注册不到 90 天      → P2  新包且未声明（谨慎对待）
     - 存在但未声明                      → P2  未声明依赖
     - 网络失败/离线                     → P3  无法核实（永不阻断门禁）
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

from v4_pro.popular_packages import NPM_POPULAR, PYPI_POPULAR

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

_JS_IMPORT_PATTERNS = [
    re.compile(r"""\brequire\s*\(\s*['"]([^'"]+)['"]\s*\)"""),
    re.compile(r"""\bfrom\s+['"]([^'"]+)['"]"""),
    re.compile(r"""\bimport\s*\(\s*['"]([^'"]+)['"]\s*\)"""),
    re.compile(r"""\bimport\s+['"]([^'"]+)['"]"""),  # side-effect import
]

# 新包判定阈值：注册不到这么多天就格外可疑
FRESH_DAYS = 90


def levenshtein(a: str, b: str, cap: int = 3) -> int:
    """编辑距离（带提前剪枝，cap 以上不再精确计算）。"""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


class PhantomDependencyChecker:
    """幻觉依赖检测器。resolver 可注入以便离线测试。"""

    def __init__(
        self,
        resolver: Callable[[str, str], str | tuple[str, float | None]] | None = None,
        cache_path: Path | None = None,
        offline: bool = False,
        allowlist: list[str] | None = None,
        timeout: int = 5,
        ttl_exists: int = 30,
        ttl_missing: int = 7,
        installed: set[str] | None = None,
    ):
        # resolver 返回 str 或 (verdict, created_epoch|None) 元组
        self._resolver = resolver
        self._cache_path = cache_path or Path(".v4pro_cache.json")
        self._offline = offline
        self._allowlist = {a.lower() for a in (allowlist or [])}
        self._timeout = timeout
        self._ttl_exists = ttl_exists * 86400
        self._ttl_missing = ttl_missing * 86400
        self._installed_override = installed
        self._cache: dict[str, dict] = {}
        self._load_cache()
        self.stats = {"registry_checked": 0, "cache_hits": 0, "typosquat_checked": 0}

    # ── 入口 ─────────────────────────────────────────────────

    def scan(self, code_dir: Path) -> dict[str, Any]:
        code_dir = Path(code_dir)
        if not code_dir.exists():
            return {"passed": True, "issues": [], "summary": {"files_scanned": 0}}

        declared = self._collect_declared(code_dir)  # {norm_name: [(file, line, eco)]}
        declared_names = set(declared.keys())
        local_modules = self._collect_local_modules(code_dir)
        installed = self._installed_dists()
        installed_norm = {d.lower().replace("_", "-") for d in installed}

        py_imports = self._scan_python_imports(code_dir)
        js_imports = self._scan_js_imports(code_dir)

        issues: list[dict] = []
        for name, files in sorted(py_imports.items()):
            issues.extend(self._judge(name, files, "pypi", declared_names, local_modules, installed_norm))
        for name, files in sorted(js_imports.items()):
            issues.extend(self._judge(name, files, "npm", declared_names, local_modules, installed_norm))

        # 盲区 A: 依赖清单文件本身也查（攻击最常走的入口）
        for name in sorted(declared.keys()):
            issues.extend(self._judge_declared(name, declared[name], local_modules, installed_norm))

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

    # ── 代码 import 判定 ─────────────────────────────────────

    def _judge(
        self,
        name: str,
        files: list[tuple[Path, int]],
        ecosystem: str,
        declared: set[str],
        local_modules: set[str],
        installed_norm: set[str],
    ) -> list[dict]:
        key = name.lower()
        norm = key.replace("_", "-") if ecosystem == "pypi" else key
        if key in self._allowlist or norm in self._allowlist:
            return []

        file_ref = f"{files[0][0].name}:{files[0][1]}"
        more = f" 等 {len(files)} 处" if len(files) > 1 else ""

        if ecosystem == "pypi":
            if name in local_modules or key in local_modules or norm in local_modules:
                return []
            if norm in declared or key in installed_norm:
                return []
        else:
            if name in NODE_BUILTINS or name.startswith("node:"):
                return []
            if name.startswith(".") or name.startswith("/") or re.match(r"^@/", name):
                return []
            if key in declared:
                return []

        verdict, created = self._resolve(name, ecosystem)
        squat = self._typosquat(name, ecosystem)

        if verdict == "missing":
            squat_note = f"；且包名与热门包 {squat[0]} 高度相似（编辑距离 {squat[1]}）" if squat else ""
            return [{
                "severity": "P0",
                "rule_id": f"PHANTOM/{ecosystem}",
                "title": f"幻觉依赖: {name} 在 {'PyPI' if ecosystem == 'pypi' else 'npm registry'} 上不存在"
                         f"（{file_ref}{more}）——AI 编造的包名，攻击者可能已抢注（slopsquatting），"
                         f"pip install / npm install 会直接拉到恶意代码{squat_note}",
                "file": str(files[0][0]),
                "line": files[0][1],
                "suggestion": f"确认 {name} 是否为正确包名（查官方文档）；"
                              "若为内部包请加入 .v4pro.json 的 phantom.allowlist",
            }]
        if verdict == "exists":
            if squat:
                fresh, age_days = self._is_fresh(created)
                sev = "P0" if fresh else "P1"
                age_note = f"，且注册仅 {age_days} 天" if fresh else ""
                return [{
                    "severity": sev,
                    "rule_id": "PHANTOM/typosquat",
                    "title": f"疑似碰瓷包: {name} 与热门包 {squat[0]} 编辑距离仅 {squat[1]}{age_note}"
                             f"（{file_ref}{more}）——typosquatting 是最常见的投毒手法",
                    "file": str(files[0][0]),
                    "line": files[0][1],
                    "suggestion": f"检查拼写：你想用的应该是 {squat[0]} 吗？",
                }]
            fresh, age_days = self._is_fresh(created)
            if fresh:
                return [{
                    "severity": "P2",
                    "rule_id": "PHANTOM/fresh-package",
                    "title": f"新注册包: {name} 仅发布 {age_days} 天且未声明依赖（{file_ref}{more}）"
                             "——新包+未声明组合需要人工确认来源",
                    "file": str(files[0][0]),
                    "line": files[0][1],
                    "suggestion": "确认包的可信度（维护者、下载量、源码）后再写入依赖",
                }]
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

    # ── 依赖清单判定（盲区 A）────────────────────────────────

    def _judge_declared(
        self,
        name: str,
        locations: list[tuple[Path, int, str]],
        local_modules: set[str],
        installed_norm: set[str],
    ) -> list[dict]:
        norm = name.lower()
        if norm in self._allowlist:
            return []
        # 声明名连字符 ↔ 模块名下划线（PEP 503），项目自身的包不查
        module_names = {norm, norm.replace("-", "_")}
        if module_names & local_modules:
            return []
        ecosystem = locations[0][2]
        if ecosystem == "npm" and (name in NODE_BUILTINS or name.startswith("node:")):
            return []
        file_ref = f"{locations[0][0].name}:{locations[0][1]}"
        more = f" 等 {len(locations)} 处" if len(locations) > 1 else ""

        # 本机已装的包不去注册表判"存在性"（可能是私有源/内部包）
        verdict, created = (None, None)
        if norm not in installed_norm:
            verdict, created = self._resolve(name, ecosystem)
        else:
            return []

        if verdict == "missing":
            return [{
                "severity": "P0",
                "rule_id": f"PHANTOM/declared-{ecosystem}",
                "title": f"依赖清单中声明了不存在的包: {name}"
                         f"（{file_ref}{more}）——不存在的包装不上是好事，"
                         "但更可能意味着清单被 AI 幻觉污染",
                "file": str(locations[0][0]),
                "line": locations[0][1],
                "suggestion": f"核对 {name} 的正确包名，或移除该条目",
            }]
        if verdict == "exists":
            squat = self._typosquat(name, ecosystem)
            if squat:
                return [{
                    "severity": "P1",
                    "rule_id": "PHANTOM/typosquat",
                    "title": f"疑似碰瓷包: 依赖清单中的 {name} 与热门包 {squat[0]} 编辑距离仅 {squat[1]}"
                             f"（{file_ref}{more}）——typosquatting 是最常见的投毒手法",
                    "file": str(locations[0][0]),
                    "line": locations[0][1],
                    "suggestion": f"检查拼写：你想用的应该是 {squat[0]} 吗？",
                }]
        return []

    # ── 碰瓷 / 新鲜度 ────────────────────────────────────────

    def _typosquat(self, name: str, ecosystem: str) -> tuple[str, int] | None:
        """与热门包编辑距离过近 → (最接近的热门包, 距离)。"""
        self.stats["typosquat_checked"] += 1
        norm = name.lower().replace("_", "-") if ecosystem == "pypi" else name.lower()
        if len(norm) < 4:
            return None
        popular = PYPI_POPULAR if ecosystem == "pypi" else NPM_POPULAR
        if norm in popular:
            return None
        best: tuple[str, int] | None = None
        for p in popular:
            if abs(len(p) - len(norm)) > 2:
                continue
            d = levenshtein(norm, p, cap=3)
            if d > 2:
                continue
            if d == 1 or (d == 2 and len(norm) >= 6):
                if best is None or d < best[1]:
                    best = (p, d)
                    if d == 1:
                        break
        return best

    @staticmethod
    def _is_fresh(created: float | None) -> tuple[bool, int | None]:
        if created is None:
            return False, None
        age_days = int((time.time() - created) / 86400)
        return age_days < FRESH_DAYS, max(age_days, 0)

    # ── 注册表解析（带缓存）──────────────────────────────────

    def _resolve(self, name: str, ecosystem: str) -> tuple[str, float | None]:
        """返回 (verdict, created_epoch|None)。"""
        cache_key = f"{ecosystem}:{name.lower()}"
        now = time.time()
        entry = self._cache.get(cache_key)
        if entry:
            age = now - entry.get("t", 0)
            if (entry.get("e") and age < self._ttl_exists) or \
               (not entry.get("e") and age < self._ttl_missing):
                self.stats["cache_hits"] += 1
                verdict = "exists" if entry.get("e") else "missing"
                return verdict, entry.get("c")
        if self._resolver:
            result = self._resolver(name, ecosystem)
            if isinstance(result, tuple):
                verdict, created = result
            else:
                verdict, created = result, None
        elif self._offline:
            return "unknown", None
        else:
            verdict, created = self._registry_lookup(name, ecosystem)
        if verdict in ("exists", "missing"):
            self.stats["registry_checked"] += 1
            self._cache[cache_key] = {"e": verdict == "exists", "t": now, "c": created}
        return verdict, created

    @staticmethod
    def _registry_lookup(name: str, ecosystem: str) -> tuple[str, float | None]:
        """查注册表，返回 (verdict, 包首次发布时间 epoch|None)。"""
        try:
            if ecosystem == "pypi":
                url = f"https://pypi.org/pypi/{name}/json"
            else:
                url = "https://registry.npmjs.org/" + urllib.request.quote(name, safe="")
            req = urllib.request.Request(url, headers={"User-Agent": "v4-pro-phantom-check"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status != 200:
                    return "unknown", None
                created = _parse_created(resp.read(), ecosystem)
                return "exists", created
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return "missing", None
            return "unknown", None
        except (urllib.error.URLError, TimeoutError, OSError):
            return "unknown", None

    # ── 依赖清单收集（带位置）────────────────────────────────

    def _collect_declared(self, code_dir: Path) -> dict[str, list[tuple[Path, int, str]]]:
        """{归一化包名: [(文件, 行号, 生态)]}。"""
        declared: dict[str, list[tuple[Path, int, str]]] = {}

        def add(name: str, file: Path, line: int, eco: str) -> None:
            declared.setdefault(name, []).append((file, line, eco))

        # pyproject.toml（tomllib 优先，3.10 降级正则）
        pyproject = code_dir / "pyproject.toml"
        if pyproject.is_file():
            try:
                text = pyproject.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                text = ""
            block_line = 1
            try:
                import tomllib
                data = tomllib.loads(text)
                deps = data.get("project", {}).get("dependencies", []) \
                    + data.get("build-system", {}).get("requires", [])
                m = re.search(r"dependencies\s*=", text)
                if m:
                    block_line = text[:m.start()].count("\n") + 1
                for d in deps:
                    add(_normalize_pypi_name(d), pyproject, block_line, "pypi")
            except ImportError:
                m = re.search(r"^dependencies\s*=\s*\[(.*?)\]", text, re.S | re.M)
                if m:
                    line_no = text[:m.start()].count("\n") + 1
                    for item in re.findall(r"""['"]([^'"]+)['"]""", m.group(1)):
                        add(_normalize_pypi_name(item), pyproject, line_no, "pypi")
            except Exception:  # v4pro:ignore=SMELL/except-swallow pyproject 已用 tomllib 解析过，此处为 3.10 正则降级兜底
                pass
        # requirements*.txt（行号精确）
        for req in code_dir.glob("requirements*.txt"):
            try:
                for i, line in enumerate(req.read_text(encoding="utf-8").split("\n"), 1):
                    stripped = line.strip()
                    if stripped and not stripped.startswith(("-", "#")):
                        add(_normalize_pypi_name(stripped), req, i, "pypi")
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
                            add(_normalize_pypi_name(name), p, 1, "pypi")
                except (OSError, UnicodeDecodeError):
                    pass
        # package.json
        pkg = code_dir / "package.json"
        if pkg.is_file():
            try:
                text = pkg.read_text(encoding="utf-8")
                data = json.loads(text)
                line_dep = 1
                m = re.search(r'"dependencies"', text)
                if m:
                    line_dep = text[:m.start()].count("\n") + 1
                for section in ("dependencies", "devDependencies", "peerDependencies"):
                    for name in data.get(section, {}):
                        add(name.lower(), pkg, line_dep, "npm")
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

    def _installed_dists(self) -> set[str]:
        if self._installed_override is not None:
            return self._installed_override
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


def _parse_created(body: bytes, ecosystem: str) -> float | None:
    """从注册表响应解析包首次发布时间（epoch）。失败返回 None。"""
    try:
        data = json.loads(body)
        if ecosystem == "npm":
            created = data.get("time", {}).get("created")
            if created:
                return time.mktime(time.strptime(created[:19], "%Y-%m-%dT%H:%M:%S"))
        else:  # pypi — 取所有版本里最早的 upload_time
            times = []
            for files in (data.get("releases") or {}).values():
                for fobj in files:
                    t = fobj.get("upload_time")
                    if t:
                        times.append(time.mktime(time.strptime(t[:19], "%Y-%m-%d %H:%M:%S")))
            if not times:
                for u in data.get("urls", []):
                    t = u.get("upload_time")
                    if t:
                        times.append(time.mktime(time.strptime(t[:19], "%Y-%m-%d %H:%M:%S")))
            return min(times) if times else None
    except Exception:  # v4pro:ignore=SMELL/except-swallow 时间解析失败只是少一个信号，不影响存在性判定
        return None
    return None


def _normalize_pypi_name(req: str) -> str:
    """'requests[security]>=2.0 # comment' -> 'requests'"""
    name = re.split(r"[\[><=!~;\s]", req.strip(), maxsplit=1)[0]
    return name.lower().replace("_", "-")


# Python 标准库顶层名（3.10-3.13 常用集 + sys.stdlib_module_names 动态补充）
import sys  # noqa: E402

_PY_STDLIB_COVER: set[str] = set(getattr(sys, "stdlib_module_names", ())) | {
    "typing_extensions",  # 常见类型桩包，运行期常随依赖安装
}

# Changelog

## [2.3.0] - 2026-09-24

### Added — 三份独立基准证据（发 Show HN 前的功课）
- **基准 C（真实攻击包）**: OSV 官方 PyPI 转储中 11,744 个真实恶意供应链攻击包，
  固定 seed 抽样 150 个跑完整幻觉检测管线——信号覆盖率 71.3%，
  P0 直接拦截 71.3%（绝大多数恶意包已被 PyPI 下架）；未触发的 43 个诚实公示
- **基准 A（真实人类 bug）**: BugsInPy 数据集 5 项目 24 个真实 bug，
  pre-image blob 还原带缺陷文件——文件级命中 17%、行级定位 0%，
  刻意保留以诚实划界：确定性模式工具不做逻辑缺陷检测
- **基准脚本**: benchmarks/phantom_recall.py（多轮重试排干网络失败）、
  benchmarks/bugsinpy_recall.py（bug.info 元数据定位 pre-image）、
  benchmarks/remote_zip.py（HTTP Range 远程读大 ZIP，不必下 10GB）
- README 增加英文摘要与三份基准汇总
- 数据溯源: OSV 官方转储 / Spracks et al. USENIX Security'25 幻觉包研究
  （Zenodo 制品仅含复现工具，名单未公开——故以 OSV 实攻击数据替代）

## [2.2.1] - 2026-09-24


### Fixed — CI 抓出的两个发布级 bug
1. **Semgrep 规则路径错误**: 引擎在 `v4_pro/verify/semgrep_rules` 找规则，
   实际位于 `v4_pro/semgrep_rules`——本机未装 semgrep 从未暴露，
   CI 深度引擎一开即现形（表现为深度扫描静默产出 0 条发现）
2. **wheel 缺少规则文件**: semgrep_rules 未作为包数据打入 wheel，
   导致 pip 安装的用户深度扫描必然失败——semgrep_rules 升级为
   正式子包并显式声明 package-data，本地构建 wheel 验证通过

### CI
- self-gate 新增 semgrep 诊断步骤：validate + 原始输出 + 引擎 notes 全量落日志，
  断言深度引擎真实产出发现（防静默跳过）

## [2.2.0] - 2026-09-24


### Added — Semgrep 深度扫描引擎（可选增强）
- 内置 AI 场景规则集（v4_pro/semgrep_rules/，11 条 Python + 3 条 JS AST 级规则）
- 检测到本机 semgrep 自动启用；`--semgrep/--no-semgrep` 强制开关；未安装自动降级内置规则
- 深度规则覆盖的内置规则自动让位（SEC/sql-*、SEC/dynamic-exec 等 12 条），避免一鱼两报
- 失败永不阻断：semgrep 崩溃/超时/输出异常均降级为空结果 + 提示

### Added — JS/TS 引擎链（oxlint → eslint → 内置）
- 优先调用 oxlint（单二进制零配置，目录级一次调用），实测 v1.85 JSON 解析
- **修复 Windows 关键 bug**: npm/pip 安装的 .cmd 垫片命令 subprocess 解析不到
  （CreateProcess 限制），改用 shutil.which 全路径解析——此前 Windows 用户
  的 eslint/pylint 集成全部静默失效
- StaticAnalyzer 新增 allow_external 开关（基准测试等场景强制确定性）

### Added — 基准测试框架（诚实版）
- benchmarks/run_benchmark.py：合成标注集（15 文件/35 发现）+ 标准库干净集（10 模块）
- 首轮基准即暴露 5 个真实缺陷，全部修复：
  1. self.SECRET_KEY 属性形式硬编码密钥漏检（正则要求变量名紧贴等号）
  2. SMELL/duplicate-function 未按类作用域分组——不同类同名方法误报
     （selectors.py 26 处、queue.py 15 处误报）
  3. SMELL/stub-implementation 对类方法/下划线私有函数过激——接口实现
     惯用法误报，类方法与私有函数降级 P3
  4. 占位符正则丢失行尾锚——"placeholder too large..." 注释文本误报
  5. exec() 严重度虚高 P0→P1（stdlib 元编程合法使用，与 Bandit 对齐）
- 修复后：合成集检出 35/35；干净集 P0 误报 0、P1 信号 4 处（全部可解释）
- eval(P0)/exec(P1) 拆分为独立规则 SEC/dynamic-exec / SEC/exec-dynamic

### CI
- self-gate job 加装 semgrep + oxlint：深度引擎全开跑自门禁，
  并断言 semgrep 在演示集上真实产出发现（防静默跳过）

### Tests
- 127 → 133 个测试

## [2.1.0] - 2026-09-23


### Added — 幻觉依赖检测三层升级（从"查存在"到"查可疑"）
- **碰瓷包检测（typosquatting）**: 包名与内置热门包名单（PyPI/npm 共 400+ 知名包）编辑距离 ≤2
  → P1；若该包注册还不满 90 天 → 升级 P0（碰瓷 + 新包 ≈ 必然攻击）
- **新包可疑信号**: 代码 import 了注册不到 90 天且未声明的包 → P2 提示人工确认
  （注册表响应中解析首次发布时间，随存在性判定一并缓存）
- **依赖清单扫描（盲区修补）**: requirements.txt / pyproject.toml / package.json 里
  声明了不存在的包 → P0（此前只扫代码 import，攻击者最常投毒的依赖文件反而是盲区）
- 行号精确定位到 requirements.txt 的具体行；项目自身包名与本机已装包自动豁免，不误伤私有源

### Tests
- 114 → 127 个测试（碰瓷/新包/依赖清单三大场景全覆盖）

## [2.0.0] - 2026-09-23


### Added — 幻觉依赖检测（核心新能力）
- 新模块 `v4_pro/phantom.py`：检测 AI 编造的不存在依赖包（slopsquatting 供应链攻击防线）
- Python AST 提取 import / JS·TS 提取 import+require，四步判定：
  标准库 → 本地模块 → 已声明/已安装依赖 → 注册表查证（PyPI / npm registry）
- 注册表查证带本地缓存（`.v4pro_cache.json`，存在 30 天/缺失 7 天 TTL），离线模式降级为 P3 永不阻断
- `phantom.allowlist` 白名单支持内部包名

### Added — AI 代码异味检测
- 新模块 `v4_pro/smells.py`：检测 LLM 生成代码的典型失败模式（传统 linter 不覆盖）
- `SMELL/except-swallow`：except Exception/裸 except 静默吞异常（窄类型 pass 属惯用法，不误报）
- `SMELL/stub-implementation`：桩函数（pass/.../NotImplementedError/纯文档字符串），抽象方法豁免
- `SMELL/duplicate-function`：同名函数重复定义（AI 改写忘删旧版）
- `SMELL/placeholder-secret` / `SMELL/placeholder-value`：占位符密钥与假值
- `SMELL/overbroad-except`、`SMELL/todo-hotspot`、`SMELL/js-empty-catch`

### Added — 门禁工程化
- `--diff <ref>`：只检查相对 git 基线变更的行（PR 门禁不再被存量问题淹没）
- `--baseline` / `--save-baseline`：基线棘轮，存量问题不阻断、新增问题必拦
- `--fail-on P0|P1|P2|P3`：可配置阻断阈值；退出码规范化（0 通过 / 1 未过 / 2 工具错误）
- `--format sarif`：SARIF 2.1.0 输出，可直接上传 GitHub code scanning
- `.v4pro.json` 项目配置：exclude 路径 / disable_rules / 阈值 / 幻觉检测参数；`v4-pro init` 自动生成
- 行内抑制注释：`# v4pro:ignore` 与 `# v4pro:ignore=RULE_ID`
- 所有规则分配稳定 rule_id（SEC/*、SA/*、SMELL/*、PHANTOM/*）

### Fixed — 误报治理（门禁可信的前提）
- Python 注释/文档字符串经 tokenize 精确掩码后再匹配（旧版逐行猜测漏掉多行注释）
- 正则/规则定义行（`re.compile`、`: r"..."`）识别为数据而非代码，不再自指误报
- 审计 v4-pro 自身：14 个误报（risk 51）→ 0 P0 / 0 P1，`verify` 自门禁通过（exit 0）
- subprocess 仅在 shell=True 或拼接命令时报 P1，参数列表形式降级
- innerHTML 清空赋值豁免、降为 P1；测试文件豁免 random/占位符/桩函数类规则
- audit 与 verify 的安全检测统一为同一引擎，消除两套规则漂移

### Tests
- 测试 64 → 114 个（新增 gate/smells/phantom 全套单元测试，含真实 git 仓库集成测试）

## [0.1.0] - 2026-06-09


### Added
- Initial release of V4 Pro — AI Code Quality Gate
- 5-step pipeline: research → define → design → generate → verify
- Quality gate with static analysis, security scan, and architecture compliance
- Independent security audit (OWASP Top 10, 6+ categories)
- Architecture freeze with ratchet constraint mechanism
- Context enrichment engine
- Multi-LLM support: OpenAI, Zhipu GLM, Qwen, Claude (coming)
- 56 unit tests

### Infrastructure
- GitHub Actions CI (3 OS × 3 Python versions)
- PR Quality Gate workflow (reusable)
- PyPI publishing workflow (triggered on release)
- Dockerfile for containerized usage
- MIT License
- Issue/PR templates
- Contributing guide

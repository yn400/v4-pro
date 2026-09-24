<div align="center">

# 🛡️ V4 Pro

**AI 代码质量门禁 · The Quality Gate for AI-Generated Code**

*拦截 AI 幻觉依赖、吞异常、桩函数 —— 在它们上线之前*
*Catch hallucinated dependencies, swallowed exceptions, and stub code — before they ship*

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)]()
[![License](https://img.shields.io/badge/License-MIT-green)]()
[![CI](https://github.com/yn400/v4-pro/actions/workflows/ci.yml/badge.svg)](https://github.com/yn400/v4-pro/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/Tests-133-passing-brightgreen)]()
[![Release](https://img.shields.io/github/v/release/yn400/v4-pro)](https://github.com/yn400/v4-pro/releases)

</div>

---

<div align="left">

**English**: v4-pro is an open-source quality gate for AI-generated code. It detects **hallucinated dependencies** (slopsquatting defense — validated against 11,744 real-world malicious packages from the OSV database, 71.3% P0 interception), **AI-specific code smells** (swallowed exceptions, stub implementations, placeholder secrets), and **security patterns** — with baseline ratchet, git-diff gating, SARIF output, and zero external dependencies. `pip install v4-pro` → `v4-pro verify --code ./src/`

</div>

---

## 为什么需要它 · Why

AI 写代码又快又多，但它会：

- **编造依赖包** — `import fastcsvparser` 这种 PyPI 上根本不存在的包。攻击者专门抢注这些名字投放恶意代码，这类攻击被称为 [slopsquatting](https://labs.cloudsecurityalliance.org/research/csa-research-note-slopsquatting-ai-supply-chain-20260419-csa)，`pip install` 的瞬间就中招
- **静默吞异常** — `except Exception: pass`，出错时一片寂静
- **生成桩函数** — 看起来实现了、函数体其实是 `pass` 或 `raise NotImplementedError`
- **留下占位符** — `YOUR_API_KEY`、`changeme`、`https://example.com/api`
- **改写时忘删旧版** — 同一个函数定义两次

传统 linter（Ruff/Semgrep/ESLint）盯的是代码风格和已知漏洞模式，**以上这些恰好都在盲区里**。V4 Pro 专补这一层。

## 核心能力 · What it catches

| 能力 | 说明 | 无需联网 |
|------|------|:---:|
| 🚫 **幻觉依赖检测** | import 编造包 / 依赖清单被污染 → P0 阻断；碰瓷包（与热门包编辑距离 ≤2）→ P1；新注册可疑包 → P2（注册表查证+缓存，离线降级不误伤） | 离线可用* |
| 🧠 **AI 异味检测** | 吞异常 / 桩函数 / 重复定义 / 占位符密钥 / TODO 热点 | ✅ |
| 🔐 **安全扫描** | SQL 注入 / 命令注入 / 不安全反序列化 / 硬编码密钥 / XSS / 弱哈希（AST+精确正则） | ✅ |
| 🧊 **架构合规** | 冻结分层约束，检查 import 依赖方向 | ✅ |
| 🔬 **深度扫描（可选）** | 检测到 [Semgrep](https://semgrep.dev) 自动启用 AST 级规则（11 条 Python + 3 条 JS）；检测到 [oxlint](https://oxc.rs) 自动接管 JS 深度检查 | ✅ |
| 📏 **静态分析** | pylint/eslint + oxlint 自动检测（装了就用）+ 内置降级规则 | ✅ |

<sub>*离线模式下幻觉检测降级为 P3 提示，绝不阻断门禁</sub>

## 🚀 快速开始 · Quick Start

```bash
# 方式 A: uvx / pipx（推荐，零污染）
uvx v4-pro verify --code ./src/
pipx install v4-pro && v4-pro verify --code ./src/

# 方式 B: pip
pip install v4-pro

# 方式 C: Docker
docker run --rm -v $(pwd):/code ghcr.io/yn400/v4-pro verify --code /code
```

**不需要任何 API Key** — `verify` 是纯本地检查，开箱即用。
（API Key 只在全流程 `run/research/design/generate` 时才需要。）

## 真实效果 · Verified Output

以下是对 [examples/ai_slop_demo.py](examples/ai_slop_demo.py)（一段故意埋了 8 类典型问题的 "AI 生成代码"）的真实运行结果：

```text
┌─────────┬────────┬─────────┬──────────┬────────┬────┐
│ 检查项  │ 总问题 │ P0      │ P1       │ P2     │ P3 │
├─────────┼────────┼─────────┼──────────┼────────┼────┤
│ 安全扫描    │   6    │     3     │      1       │     2      │ 0  │
│ AI 代码异味 │   6    │     0     │      5       │     1      │ 0  │
│ 幻觉依赖    │   2    │     2     │      0       │      0      │ 0  │
├─────────┼────────┼─────────┼──────────┼────────┼────┤
│ 合计        │   14   │     5     │      6       │     3      │ 0  │
└─────────┴────────┴─────────┴──────────┴────────┴────┘

问题详情:
  ● [安全] 使用了不安全的反序列化 — ai_slop_demo.py:42
  ● [安全] 潜在的 SQL 注入（f-string 拼接 SQL） — ai_slop_demo.py:60
  ● [安全] 硬编码密钥/密码（字符串字面量赋值） — ai_slop_demo.py:16
  ● [幻觉依赖] 幻觉依赖: fastcsvparser 在 PyPI 上不存在
     ——AI 编造的包名，攻击者可能已抢注（slopsquatting）— ai_slop_demo.py:14
  ● [幻觉依赖] 幻觉依赖: requets 在 PyPI 上不存在……
     且包名与热门包 requests 高度相似（编辑距离 1）— ai_slop_demo.py:15

✗ 质量门禁未通过！ (exit code 1)
```

14 个报告 = 演示文件里埋的 14 处真问题，**零误报**。埋了什么就报什么，没埋的不报。
<sub>（内置引擎输出；若本机装有 Semgrep/oxlint，深度扫描会叠加发现——如 JS 演示里的 `eval` 只有 oxlint 能抓到）</sub>

### 自门禁 · It gates itself

> 质量门禁工具最大的耻辱是自己的代码过不了自己的门。V4 Pro 在 CI 里装上 Semgrep + oxlint 后运行
> `v4-pro verify --code ./v4_pro/ --semgrep` —— 0 个 P0/P1，通过（深度引擎全开）。
> `v4-pro audit` 自审：**0 发现，风险分 0**。（1.x 版本自审曾报 14 个误报、风险分 51——全部来自规则定义字符串的自指误报，2.0 已根治。）

## 门禁工程化 · Built for CI

### PR 门禁：只看新增问题

存量代码一堆问题不拦新 PR？用基线棘轮或 diff 模式：

```bash
# 一次性保存当前状态为基线（允许此时失败退出）
v4-pro verify --code ./src/ --save-baseline gate.baseline.json

# 之后每次 PR：存量问题不阻断，新增问题必拦
v4-pro verify --code ./src/ --baseline gate.baseline.json

# 或者只检查相对 main 变更的行
v4-pro verify --code ./src/ --diff main

# 提高门槛：P1 也阻断
v4-pro verify --code ./src/ --fail-on P1
```

### GitHub Actions

```yaml
# .github/workflows/gate.yml
name: V4 Pro Quality Gate
on: [pull_request]
jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: {fetch-depth: 0}   # --diff 需要完整历史
      - uses: actions/setup-python@v5
        with: {python-version: "3.12"}
      - run: pip install v4-pro
      - run: v4-pro verify --code ./src/ --diff origin/${{ github.base_ref }}
```

### SARIF 上传 GitHub Code Scanning

```bash
v4-pro verify --code ./src/ --format sarif --output results.sarif
```
配合 [github/codeql-action/upload-sarif](https://github.com/github/codeql-action) 即可在 PR 页面内联显示问题。

### 按需调配置

```bash
v4-pro init   # 生成 .v4pro.json
```

```jsonc
// .v4pro.json
{
  "fail_on": "P0",                       // 阻断阈值
  "exclude": ["docs/**", "*.md"],        // 路径排除（glob）
  "disable_rules": ["SA/print-instead-of-logging"],
  "test_paths": ["tests", "test"],       // 测试目录自动享受宽松规则
  "phantom": {
    "allowlist": ["my-internal-pkg"],    // 内部包白名单
    "offline": false,
    "timeout": 5
  }
}
```

误报时不需要关掉整条规则——在代码行尾加注释即可：

```python
result = legacy_call()  # v4pro:ignore=SMELL/overbroad-except 历史接口，下版本重构
```

## 与同类工具的关系 · Positioning

| 工具 | 擅长 | 与 V4 Pro 的关系 |
|------|------|------|
| Ruff / ESLint | 代码风格、语言级错误 | 互补——风格问题它们更专业 |
| Semgrep / Bandit | 已知漏洞模式 | 互补——但都不查幻觉依赖与 AI 异味 |
| CodeRabbit / pr-agent | AI 生成 PR 评审建议 | 互补——它们给建议，V4 Pro 给硬门禁 |
| Snyk / Mend | 依赖漏洞数据库 | 互补——它们查"已安装的包有没有洞"，V4 Pro 查"这包到底存不存在" |

**V4 Pro 独有**：幻觉依赖检测（slopsquatting 防线）+ AI 生成失败模式检测 + 零依赖本地运行 + 基线/diff 门禁。

## 全流程模式（可选）· Full Pipeline

除了独立门禁，V4 Pro 也提供结构化生成流水线（需配置 LLM API Key）：

```bash
v4-pro run "做一个待办事项 App"
# 研究 → 需求 → 设计 → 生成 → 质量门禁
# 配套: v4-pro freeze 冻结架构规范，防止后续生成腐化
```

| 命令 | 说明 | 需要 Key |
|------|------|:---:|
| `v4-pro verify` | **质量门禁**（五项检查） | ❌ |
| `v4-pro audit` | 独立安全审计 | ❌ |
| `v4-pro init` | 初始化项目 + 门禁配置 | ❌ |
| `v4-pro run <需求>` | 一键全流程 | ✅ |
| `v4-pro research/define/design/generate` | 分步执行 | ✅ |
| `v4-pro freeze` | 冻结架构规范 | ❌ |

## 📊 基准报告 · Benchmark（三份独立证据）

**① 合成 AI-slop 集**（复现：`python benchmarks/run_benchmark.py`）

- 15 文件 / 35 处手工标注问题：检出率 **35/35**
- 干净集（Python 标准库 10 个真实人类模块）：P0 误报 **0**，P1 信号 4 处全部可解释
- 诚实声明：合成集出题人与标注人同为作者（自证局限）；
  其真实价值是过程中逼出了 5 个检测器缺陷修复

**② 真实攻击包**（OSV 官方 PyPI 转储，11,744 个真实供应链攻击包，复现：`python benchmarks/phantom_recall.py`）

- 固定 seed 抽样 150 个真实恶意包，逐个跑完整幻觉依赖检测管线
- **信号覆盖率 71.3%**（107/150），其中 **P0 直接拦截 71.3%**——
  绝大多数恶意包已被 PyPI 下架，AI 推荐这些名字时即被拦截
- 未触发的 43 个：名字正常且仍在线的恶意包——行为分析超出确定性检查的射程（已诚实公示名单）

**③ 真实人类 bug**（BugsInPy 数据集，5 个知名开源项目 24 个真实 bug，复现：`python benchmarks/bugsinpy_recall.py`）

- 文件级命中 **17%**，行级定位 **0%** —— 刻意保留的诚实数字：
  BugsInPy 的 bug 多为逻辑缺陷，确定性模式工具（包括 Bandit/Semgrep 默认规则）
  在同类任务上同样接近零。**v4-pro 不做逻辑缺陷检测**——那是测试套件与
  AI 代码评审的职责，v4-pro 补的是它们之间的模式级空档

## 测试与质量 · Quality

```bash
python -m pytest -v        # 133 个测试全部通过
```

- 覆盖：检测规则正确性、误报抑制、抑制注释、基线/diff 过滤、SARIF 结构、真实 git 仓库集成
- CI 矩阵（ubuntu/windows × py3.10-3.12）+ **自门禁 job**（装上深度引擎后：自己的代码必须过自己的门 + AI-slop 演示必须被拦下 + 验证 Semgrep 真的产出了发现而非静默跳过）

## 项目结构 · Structure

```
v4-pro/
├── v4_pro/
│   ├── cli.py                  # CLI 入口
│   ├── engine.py               # 工作流引擎
│   ├── gate.py                 # 门禁基础设施（掩码/抑制/基线/diff/SARIF）
│   ├── phantom.py              # 幻觉依赖检测（slopsquatting 防线）
│   ├── smells.py               # AI 代码异味检测
│   ├── verify/                 # 安全扫描 / 静态分析 / 架构合规
│   ├── audit/                  # 独立审计（与 verify 同引擎）
│   ├── freeze/                 # 冻结规范管理
│   ├── llm/                    # LLM 适配器层
│   └── config.py               # 配置管理
├── examples/                   # AI-slop 演示文件（可自查复现）
├── presets/                    # 4 种项目类型预设
└── tests/                      # 133 个测试
```

## 支持 · Supported

- **语言**: Python（AST 深度分析）、JavaScript/TypeScript（精确正则）
- **LLM Provider**（仅全流程需要）: OpenAI 兼容 / 智谱 GLM / 通义 Qwen / Claude（即将）
- **平台**: Linux / macOS / Windows（Windows 终端已做 UTF-8 修复）

## 协议 · License

[MIT](LICENSE) — 自由使用、修改、商用。

---

<div align="center">

**如果 V4 Pro 拦下过你的问题，点个 ⭐ 吧！**

[GitHub](https://github.com/yn400/v4-pro) · [Issues](https://github.com/yn400/v4-pro/issues) · [CHANGELOG](CHANGELOG.md)

</div>

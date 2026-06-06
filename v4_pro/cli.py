"""
V4 Pro CLI — 命令行入口。

用法:
    v4-pro research "用户需求描述"
    v4-pro define --from research.json
    v4-pro design --from define.json
    v4-pro generate --from design.json
    v4-pro verify --code ./generated/
    v4-pro audit --code ./generated/
    v4-pro freeze
    v4-pro init
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from v4_pro import __version__
from v4_pro.config import get_settings, reload_settings
from v4_pro.engine import WorkflowEngine
from v4_pro.scaffold import init_project

# ── Rich Console ────────────────────────────────────────────
# Windows 旧终端修复: 启用 VT 处理模式 + UTF-8 编码
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        h = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(h, ctypes.byref(mode)):
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            kernel32.SetConsoleMode(h, mode.value | 0x0004)
    except Exception:
        pass
console = Console()


def _setup_logging(level: str = "INFO") -> None:
    """配置日志系统。"""
    # Windows 旧终端: 日志 stderr 改为 UTF-8
    if sys.platform == "win32":
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


# ── 主入口 ──────────────────────────────────────────────────

@click.group()
@click.option("--debug", is_flag=True, help="启用 DEBUG 日志")
@click.version_option(version=__version__, prog_name="v4-pro")
@click.pass_context
def main(ctx: click.Context, debug: bool) -> None:
    """
    V4 Pro — Vibe Verification & Validation Pipeline for Professionals.

    将 "Vibe Coding" 从随意的 AI 生成升级为结构化、质量可控的工程流水线。
    """
    _setup_logging("DEBUG" if debug else get_settings().log_level)


# ── research ────────────────────────────────────────────────

@main.command()
@click.argument("requirement", required=True)
@click.option(
    "--provider", "-p",
    type=click.Choice(["openai", "zhipu", "tongyi", "anthropic"]),
    help="临时切换 LLM Provider（覆盖 .env 配置）",
)
@click.option(
    "--output", "-o",
    default="research.json",
    help="输出文件名",
)
def research(requirement: str, provider: str | None, output: str) -> None:
    """
    Step 1: 市场研究。

    分析用户需求，输出竞品分析、痛点、机会窗口。

    \\b
    示例:
        v4-pro research "做一个面向大学生的二手交易平台"
        v4-pro research "电商App" --provider zhipu
    """
    _print_banner("[SEARCH]  Step 1/5 — 市场研究")

    try:
        engine = _get_engine(provider)
        result = engine.research(requirement)

        _print_json_summary(result)
        console.print(f"\n[green]✓[/] 研究结果已保存到 [bold]{engine.workspace / output}[/]")

    except Exception as e:
        console.print(f"[red]✗ 研究失败: {e}[/]")
        sys.exit(1)


# ── define ──────────────────────────────────────────────────

@main.command()
@click.option(
    "--from", "source_file",
    default="research.json",
    help="来源文件（研究结果 JSON）",
)
def define(source_file: str) -> None:
    """
    Step 2: 需求定义。

    将研究结果转化为结构化的产品需求定义。
    """
    _print_banner("[LIST]  Step 2/5 — 需求定义")

    try:
        engine = _get_engine()
        result = engine.define(source_file)

        _print_json_summary(result)
        console.print(f"\n[green]✓[/] 需求定义已保存到 [bold]{engine.workspace / 'define.json'}[/]")

    except Exception as e:
        console.print(f"[red]✗ 定义失败: {e}[/]")
        sys.exit(1)


# ── design ──────────────────────────────────────────────────

@main.command()
@click.option(
    "--from", "source_file",
    default="define.json",
    help="来源文件（需求定义 JSON）",
)
@click.option(
    "--provider", "-p",
    type=click.Choice(["openai", "zhipu", "tongyi", "anthropic"]),
    help="临时切换 LLM Provider",
)
def design(source_file: str, provider: str | None) -> None:
    """
    Step 3: 架构设计。

    生成 Mermaid 架构图、技术栈选型、模块划分、数据模型。
    """
    _print_banner("[BUILD] ️  Step 3/5 — 架构设计")

    try:
        engine = _get_engine(provider)
        result = engine.design(source_file)

        _print_design_summary(result)
        console.print(f"\n[green]✓[/] 设计文档已保存到 [bold]{engine.workspace / 'design.json'}[/]")

    except Exception as e:
        console.print(f"[red]✗ 设计失败: {e}[/]")
        sys.exit(1)


# ── generate ────────────────────────────────────────────────

@main.command()
@click.option(
    "--from", "source_file",
    default="design.json",
    help="来源文件（设计文档 JSON）",
)
@click.option(
    "--provider", "-p",
    type=click.Choice(["openai", "zhipu", "tongyi", "anthropic"]),
    help="临时切换 LLM Provider",
)
def generate(source_file: str, provider: str | None) -> None:
    """
    Step 4: 代码生成。

    按设计文档生成完整项目代码，写入 v4_workspace/generated/。
    """
    _print_banner("[BOLT]  Step 4/5 — 代码生成")

    try:
        engine = _get_engine(provider)
        result = engine.generate(source_file)

        meta = result.get("_meta", {})
        file_count = meta.get("files_generated", 0)

        console.print(f"\n[green]✓[/] 已生成 [bold]{file_count}[/] 个文件")
        console.print(f"  输出目录: [bold]{meta.get('output_dir', 'generated/')}[/]")

        # 列出生成的文件
        files = result.get("files", [])
        if files:
            table = Table(title="生成文件列表", box=box.SIMPLE)
            table.add_column("文件路径", style="cyan")
            table.add_column("语言", style="yellow")
            table.add_column("说明")
            for f in files[:20]:  # 最多显示 20 个
                table.add_row(
                    f.get("path", "?"),
                    f.get("language", "?"),
                    f.get("description", "")[:60],
                )
            if len(files) > 20:
                table.add_row("...", f"+{len(files) - 20} 个文件", "")
            console.print(table)

    except Exception as e:
        console.print(f"[red]✗ 生成失败: {e}[/]")
        sys.exit(1)


# ── verify ──────────────────────────────────────────────────

@main.command()
@click.option(
    "--code", "-c",
    default="./generated/",
    help="待检查的代码目录",
)
@click.option(
    "--design", "-d", "design_file",
    default="design.json",
    help="设计文档（用于架构合规检查）",
)
@click.option(
    "--force", "-f",
    is_flag=True,
    help="强制通过（即使有 P0 问题）",
)
@click.option(
    "--format", "-fmt", "output_format",
    type=click.Choice(["rich", "json"]),
    default="rich",
    help="输出格式",
)
def verify(
    code: str,
    design_file: str,
    force: bool,
    output_format: str,
) -> None:
    """
    Step 5: 质量门禁。

    对代码执行静态分析、安全扫描、架构合规三项检查。
    """
    if output_format != "json":
        _print_banner("[SHIELD]   Step 5/5 — 质量门禁")

    try:
        engine = _get_engine()
        report = engine.verify(
            code_path=code,
            design_file=design_file,
            force=force,
        )

        if output_format == "json":
            # JSON 模式：纯 stdout 输出，不混入 Rich 标记或日志
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            _print_verify_report(report)

        summary = report.get("summary", {})
        if output_format == "json":
            # JSON 模式：exit code 反映结果，不额外输出
            if summary.get("blocked") and not force:
                sys.exit(1)
            return

        if summary.get("blocked"):
            console.print(
                f"\n[red]✗ 质量门禁未通过！[/] "
                f"[bold red]{summary['p0_blockers']}[/] 个 P0 阻断问题。"
            )
            console.print("  使用 [bold]--force[/] 可强制通过。")
            sys.exit(1)
        elif summary.get("force_bypass"):
            console.print("\n[yellow]⚠ 已强制通过（有 P0 问题被绕过）[/]")
        else:
            console.print("\n[green]✓ 质量门禁通过！[/]")

    except Exception as e:
        console.print(f"[red]✗ 验证失败: {e}[/]")
        sys.exit(1)


# ── audit ───────────────────────────────────────────────────

@main.command()
@click.option(
    "--code", "-c",
    required=True,
    help="待审计的代码目录",
)
@click.option(
    "--format", "-fmt", "output_format",
    type=click.Choice(["rich", "json"]),
    default="rich",
    help="输出格式",
)
@click.option(
    "--output", "-o",
    default=None,
    help="输出报告到文件",
)
def audit(code: str, output_format: str, output: str | None) -> None:
    """
    独立安全审计。

    检测 OWASP Top 10 中常见的 6 类以上漏洞，
    输出详细安全报告。
    """
    from v4_pro.audit.scanner import SecurityAuditor

    if output_format != "json":
        _print_banner("[KEY]  安全审计")

    try:
        code_path = Path(code).resolve()
        if not code_path.exists():
            raise FileNotFoundError(f"目录不存在: {code_path}")

        auditor = SecurityAuditor()
        report = auditor.audit(code_path)

        if output_format == "json":
            # JSON 模式：纯 stdout 输出，可管道给 jq 或其他工具
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            _print_audit_report(report)

        if output:
            out_path = Path(output)
            out_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            console.print(f"\n[green]✓[/] 报告已保存到 [bold]{out_path}[/]")

    except Exception as e:
        console.print(f"[red]✗ 审计失败: {e}[/]")
        sys.exit(1)


# ── freeze ──────────────────────────────────────────────────

@main.command()
@click.option(
    "--design", "-d", "design_file",
    default="design.json",
    help="设计文档路径",
)
def freeze(design_file: str) -> None:
    """
    冻结当前设计规范。

    将模块接口、数据库 schema 等边界冻结为 frozen_spec.json，
    后续 generate 和 verify 会自动对比棘轮约束。
    """
    from v4_pro.freeze.manager import FreezeManager

    _print_banner("[LAB]  冻结规范")

    try:
        engine = _get_engine()
        manager = FreezeManager(engine.workspace)
        spec = manager.freeze(design_file)

        console.print("[green]✓[/] 规范已冻结")
        console.print(f"  模块接口: [bold]{len(spec.get('module_interfaces', {}))}[/] 个")
        console.print(f"  数据模型: [bold]{len(spec.get('data_models', {}))}[/] 个")
        console.print(f"  冻结文件: [bold]{engine.workspace / 'frozen_spec.json'}[/]")

    except Exception as e:
        console.print(f"[red]✗ 冻结失败: {e}[/]")
        sys.exit(1)


# ── init ────────────────────────────────────────────────────

@main.command()
@click.option(
    "--dir", "-d",
    default=".",
    help="目标目录",
)
def init(dir: str) -> None:
    """
    初始化 V4 Pro 项目脚手架。

    生成 v4_workspace/、prompts/ 等标准目录结构。
    """
    _print_banner("[START]  初始化项目")

    try:
        root = init_project(dir)
        console.print(f"[green]✓[/] 项目已初始化: [bold]{root}[/]")

        # 显示目录结构
        tree_str = f"""
{root}/
├── v4_workspace/
│   └── generated/
├── prompts/
└── .env  (从 .env.example 复制并配置)
"""
        console.print(Panel(tree_str.strip(), title="项目结构", border_style="dim"))

        console.print("\n[yellow]下一步:[/]")
        console.print("  1. 编辑 [bold].env[/] 填入 API Key")
        console.print('  2. 运行 [bold]v4-pro research "你的需求"[/]')

    except Exception as e:
        console.print(f"[red]✗ 初始化失败: {e}[/]")
        sys.exit(1)


# ── run (一键运行全流程) ───────────────────────────────────

@main.command()
@click.argument("requirement", required=True)
@click.option(
    "--provider", "-p",
    type=click.Choice(["openai", "zhipu", "tongyi", "anthropic"]),
    help="LLM Provider",
)
@click.option(
    "--force", "-f",
    is_flag=True,
    help="强制通过质量门禁",
)
def run(requirement: str, provider: str | None, force: bool) -> None:
    """
    一键运行全流程: research → define → design → generate → verify。

    \\b
    示例:
        v4-pro run "做一个待办事项App"
    """
    _print_banner("[START]  V4 Pro 全流程")

    try:
        engine = _get_engine(provider)

        # Step 1
        console.print("[bold cyan]▶ Step 1/5: 市场研究...[/]")
        engine.research(requirement)

        # Step 2
        console.print("[bold cyan]▶ Step 2/5: 需求定义...[/]")
        engine.define()

        # Step 3
        console.print("[bold cyan]▶ Step 3/5: 架构设计...[/]")
        engine.design()

        # Step 4
        console.print("[bold cyan]▶ Step 4/5: 代码生成...[/]")
        engine.generate()

        # Step 5
        console.print("[bold cyan]▶ Step 5/5: 质量门禁...[/]")
        report = engine.verify(force=force)

        summary = report.get("summary", {})
        if summary.get("blocked"):
            console.print(f"\n[red]✗ 质量门禁未通过: {summary['p0_blockers']} 个 P0 问题[/]")
            sys.exit(1)
        else:
            console.print("\n[green]✓ 全流程完成！[/]")
            console.print(f"  P0: [red]{summary['p0_blockers']}[/]  ")
            console.print(f"  P1: [yellow]{summary['p1_warnings']}[/]  ")
            console.print(f"  P2: [dim]{summary['p2_suggestions']}[/]")

    except Exception as e:
        console.print(f"[red]✗ 流程中断: {e}[/]")
        sys.exit(1)


# ── 辅助函数 ────────────────────────────────────────────────

def _get_engine(provider: str | None = None) -> WorkflowEngine:
    """创建 WorkflowEngine，可选临时切换 provider。"""
    if provider:
        # model_copy 生成新实例，保留 pydantic 校验，不直接修改原对象
        settings = reload_settings().model_copy(update={"llm_provider": provider})
        return WorkflowEngine(settings=settings)
    return WorkflowEngine()


def _print_banner(title: str) -> None:
    """打印统一的命令标题。"""
    console.print()
    console.print(Panel(
        Text(title, style="bold white"),
        border_style="cyan",
        padding=(0, 2),
    ))


def _print_json_summary(result: dict) -> None:
    """打印 JSON 结果的简要预览。"""
    # 跳过 _meta 字段
    display = {k: v for k, v in result.items() if not k.startswith("_")}

    # 截断长字符串
    truncated = {}
    for k, v in display.items():
        if isinstance(v, str) and len(v) > 200:
            truncated[k] = v[:200] + "..."
        elif isinstance(v, list) and len(v) > 10:
            truncated[k] = v[:10] + [f"... (+{len(v) - 10} 项)"]
        else:
            truncated[k] = v

    console.print_json(json.dumps(truncated, ensure_ascii=False, indent=2))


def _print_design_summary(result: dict) -> None:
    """打印设计文档的简要预览。"""
    tech = result.get("tech_stack", {})
    if tech:
        table = Table(title="技术栈", box=box.SIMPLE)
        table.add_column("类别", style="cyan")
        table.add_column("选择", style="green")
        for k, v in tech.items():
            if isinstance(v, list):
                v = ", ".join(v)
            table.add_row(k, str(v))
        console.print(table)

    # 架构层
    layers = result.get("architecture", {}).get("layers", [])
    if layers:
        console.print("\n[bold]架构分层:[/]")
        for layer in layers:
            name = layer.get("name", "?")
            modules = layer.get("modules", [])
            console.print(f"  [cyan]{name}[/]: {', '.join(modules)}")


def _print_verify_report(report: dict) -> None:
    """打印质量门禁报告（Rich 格式）。"""
    summary = report.get("summary", {})

    # 汇总表
    table = Table(title="质量门禁报告", box=box.ROUNDED)
    table.add_column("检查项", style="cyan")
    table.add_column("总问题", justify="center")
    table.add_column("P0 [RED] ", justify="center", style="red")
    table.add_column("P1 [YELLOW] ", justify="center", style="yellow")
    table.add_column("P2 [BLUE] ", justify="center", style="dim")

    for check_name, check_result in report.get("checks", {}).items():
        issues = check_result.get("issues", [])
        p0 = sum(1 for i in issues if i.get("severity") == "P0")
        p1 = sum(1 for i in issues if i.get("severity") == "P1")
        p2 = sum(1 for i in issues if i.get("severity") == "P2")
        label_map = {
            "static_analysis": "静态分析",
            "security_scan": "安全扫描",
            "arch_compliance": "架构合规",
        }
        table.add_row(label_map.get(check_name, check_name), str(len(issues)), str(p0), str(p1), str(p2))

    table.add_section()
    table.add_row(
        "[bold]合计[/]",
        str(summary.get("total_issues", 0)),
        str(summary.get("p0_blockers", 0)),
        str(summary.get("p1_warnings", 0)),
        str(summary.get("p2_suggestions", 0)),
    )
    console.print(table)

    # P0 问题详情
    all_issues = []
    for check_name, check_result in report.get("checks", {}).items():
        for issue in check_result.get("issues", []):
            issue["_check"] = check_name
            all_issues.append(issue)

    p0_issues = [i for i in all_issues if i.get("severity") == "P0"]
    if p0_issues:
        console.print("\n[bold red]P0 阻断问题:[/]")
        for issue in p0_issues[:10]:
            console.print(
                f"  [red]●[/] [{issue['_check']}] "
                f"[bold]{issue.get('title', '?')}[/] "
                f"— {issue.get('file', '?')}:{issue.get('line', '?')}"
            )


def _print_audit_report(report: dict) -> None:
    """打印安全审计报告（Rich 格式）。"""
    summary = report.get("summary", {})

    # 严重程度分布
    table = Table(title="安全审计报告", box=box.ROUNDED)
    table.add_column("严重程度", style="bold")
    table.add_column("数量", justify="center")
    table.add_column("占比", justify="right")

    total = summary.get("total_findings", 1)
    for level in ["critical", "high", "medium", "low", "info"]:
        count = summary.get(level, 0)
        if count > 0:
            color = {
                "critical": "red",
                "high": "orange3",
                "medium": "yellow",
                "low": "blue",
                "info": "dim",
            }.get(level, "white")
            table.add_row(
                f"[{color}]{level.upper()}[/]",
                str(count),
                f"{count / total * 100:.0f}%",
            )
    console.print(table)

    # 漏洞类别
    findings = report.get("findings", [])
    categories = {}
    for f in findings:
        cat = f.get("owasp_category", "其他")
        categories[cat] = categories.get(cat, 0) + 1

    if categories:
        console.print("\n[bold]OWASP 覆盖:[/]")
        for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
            console.print(f"  • {cat}: {count} 个发现")


if __name__ == "__main__":
    main()

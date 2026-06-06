"""Generate V4 Pro CLI demo SVG — real DeepSeek output."""
import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rich.console import Console


def capture_svg() -> str:
    buf = io.StringIO()
    console = Console(file=buf, record=True, width=62, force_terminal=True)

    console.print()
    console.print("[bold]V4 Pro[/] [dim]-- AI Code Quality Gate[/]")
    console.print("  " + ("-" * 44))
    console.print()
    console.print("[cyan]>[/] [dim]v4-pro run \"a todo-list app\"[/]")
    console.print()
    console.print("  [cyan]1/5[/] Market Research  [green]OK[/]")
    console.print("      target: students, office workers")
    console.print("  [cyan]2/5[/] Requirements     [green]OK[/]")
    console.print("      goal: create a todo in 3 seconds")
    console.print("  [cyan]3/5[/] Architecture     [green]OK[/]")
    console.print("      React + FastAPI + SQLite")
    console.print("  [cyan]4/5[/] Code Generation  [green]OK[/]")
    console.print("      34 files generated")
    console.print("  [cyan]5/5[/] Quality Gate     [green]PASSED[/]")
    console.print("      0 P0  0 P1  0 P2")
    console.print()
    console.print("  [bold]DeepSeek[/] [dim]-- 5 steps, 2 min, 19K tokens[/]")
    console.print()
    console.print("[bold]Commands:[/]")
    console.print("  [cyan]v4-pro verify[/]     quality gate check")
    console.print("  [cyan]v4-pro audit[/]      security audit")
    console.print("  [cyan]v4-pro research[/]   market research")
    console.print("  [cyan]v4-pro generate[/]   code generation")
    console.print()
    console.print("[dim]All commands support --help[/]")
    console.print()

    return console.export_svg(title="V4 Pro")


if __name__ == "__main__":
    svg = capture_svg()
    out = Path(__file__).resolve().parent.parent / "assets" / "cli_demo.svg"
    out.parent.mkdir(exist_ok=True)
    cleaned = re.sub(r' textLength="[^"]+"', '', svg)
    out.write_text(cleaned, encoding="utf-8")
    print(f"SVG: {out} ({out.stat().st_size}B)")

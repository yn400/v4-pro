"""Generate verify demo SVG — pure ASCII, no Unicode, no overlap."""
import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rich.console import Console


def capture_svg() -> str:
    buf = io.StringIO()
    console = Console(file=buf, record=True, width=64, force_terminal=True)

    console.print()
    console.print("  [bold yellow]v4-pro verify[/] [bold]--code ./src/[/]")
    console.print("  " + ("-" * 42))
    console.print()
    console.print("  [cyan]Static Analysis[/]    2 issues  0 P0  1 P1  1 P2")
    console.print("  [cyan]Security Scan[/]      0 issues  0 P0  0 P1  0 P2")
    console.print("  [cyan]Arch Compliance[/]    1 issue   0 P0  0 P1  1 P2")
    console.print()
    console.print("  [green]PASSED[/]  0 P0  1 P1  2 P2")
    console.print()
    console.print("  [dim]v4-pro audit --code ./src/ --format json[/]")
    console.print("  [dim]v4-pro run \"a blog system\" --force[/]")
    console.print()

    return console.export_svg(title="v4-pro verify")


if __name__ == "__main__":
    svg = capture_svg()
    out = Path(__file__).resolve().parent.parent / "assets" / "verify_demo.svg"
    cleaned = re.sub(r' textLength="[^"]+"', '', svg)
    out.write_text(cleaned, encoding="utf-8")
    print(f"SVG: {out} ({out.stat().st_size}B)")

"""Cube-up sub-commands (``d2rr-toolkit cube-up ...``).

Lean CLI surface over :mod:`d2rr_toolkit.operations.rune_cube_up` for
automation and manual verification. Two subcommands:

  * ``rune``   - cube-up a specific rune code N pairs at a time
                 (:func:`cube_up_file_single`)
  * ``bulk``   - cascading cube-up across r01..r32 with optional
                 per-rune minimum-keep thresholds
                 (:func:`cube_up_file_bulk`)

Both subcommands write in-place by default, creating a timestamped
backup via :mod:`d2rr_toolkit.backup` before touching the file. Pass
``--out <path>`` to write to a separate file and skip the backup.
"""

import re
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.table import Table

from . import app, console, err_console

if TYPE_CHECKING:
    from d2rr_toolkit.operations.rune_cube_up import CubeUpResult
from d2rr_toolkit.operations.rune_cube_up import (
    CannotUpgradeMaxRuneError,
    InvalidRuneCodeError,
    NotEnoughRunesError,
    Section5MissingError,
    StackCapExceededError,
    cube_up_file_bulk,
    cube_up_file_single,
)

cube_app = typer.Typer(
    help="Transmute runes in Section 5 of the shared stash - cube up pairs into the next tier."
)
app.add_typer(cube_app, name="cube-up")


_MIN_KEEP_RE = re.compile(r"^(r(?:0[1-9]|[12]\d|3[0-3])):(\d+)$")


def _parse_min_keep(specs: list[str]) -> dict[str, int]:
    """Parse ``--keep r09:3 --keep r15:50`` into ``{'r09': 3, 'r15': 50}``."""
    out: dict[str, int] = {}
    for spec in specs:
        m = _MIN_KEEP_RE.match(spec.strip().lower())
        if not m:
            raise typer.BadParameter(
                f"--keep value {spec!r} must look like rNN:COUNT (e.g. r15:50). " f"NN is 01..33."
            )
        out[m.group(1)] = int(m.group(2))
    return out


def _print_result_table(result: "CubeUpResult", title: str) -> None:
    """Render a :class:`CubeUpResult` as a compact summary table."""
    tbl = Table(title=title)
    tbl.add_column("rune")
    tbl.add_column("removed", justify="right")
    tbl.add_column("added", justify="right")
    tbl.add_column("remaining", justify="right")
    # Union of all rune codes that moved, plus any non-zero remaining counts.
    codes = sorted(set(result.removed) | set(result.added) | set(result.remaining))
    for code in codes:
        rem = result.removed.get(code, 0)
        add = result.added.get(code, 0)
        rest = result.remaining.get(code, 0)
        if not (rem or add or rest):
            continue
        tbl.add_row(code, str(rem or "-"), str(add or "-"), str(rest))
    console.print(tbl)


@cube_app.command("rune")
def cmd_rune(
    save_file: Path = typer.Argument(..., help="Path to .d2i shared stash file."),
    rune: str = typer.Option(
        ...,
        "--rune",
        "-r",
        help="Input rune code, r01..r32. (r33 is the max tier and cannot be upgraded.)",
    ),
    pairs: int = typer.Option(
        ...,
        "--pairs",
        "-p",
        min=1,
        help="Number of pairs to cube up. Each pair consumes 2 input runes and produces 1 output rune.",
    ),
    out: Path | None = typer.Option(
        None,
        "--out",
        "-o",
        help="Write result to this path instead of overwriting the source file. "
        "When set, no backup is created.",
    ),
    no_backup: bool = typer.Option(
        False,
        "--no-backup",
        help="Skip the automatic backup when writing in-place. Not recommended.",
    ),
) -> None:
    """Cube-up N pairs of a specific rune code in Section 5.

    Example:
        d2rr-toolkit cube-up rune shared.d2i --rune r01 --pairs 10
    """

    backup = not (no_backup or out is not None)
    try:
        res = cube_up_file_single(save_file, rune, pairs, dest_path=out, backup=backup)
    except (
        CannotUpgradeMaxRuneError,
        InvalidRuneCodeError,
        NotEnoughRunesError,
        StackCapExceededError,
        Section5MissingError,
    ) as e:
        err_console.print(f"[bold red]Cube-up failed:[/] {e}")
        raise typer.Exit(1)
    except FileNotFoundError as e:
        err_console.print(f"[bold red]File not found:[/] {e}")
        raise typer.Exit(1)

    _print_result_table(
        res.result, f"Cube-up {rune} -> next tier ({pairs} pair{'s' if pairs != 1 else ''})"
    )
    console.print(f"[green]Wrote:[/] {res.output_path}")
    if res.backup_path:
        console.print(f"[dim]Backup:[/] {res.backup_path}")


@cube_app.command("bulk")
def cmd_bulk(
    save_file: Path = typer.Argument(..., help="Path to .d2i shared stash file."),
    keep: list[str] = typer.Option(
        [],
        "--keep",
        "-k",
        help=(
            "Per-rune floor in ``rNN:COUNT`` form. Repeatable. "
            "Example: --keep r09:3 --keep r15:50 leaves at least 3 Ort and 50 Hel runes."
        ),
    ),
    out: Path | None = typer.Option(
        None,
        "--out",
        "-o",
        help="Write result to this path instead of overwriting the source file. No backup in this case.",
    ),
    no_backup: bool = typer.Option(
        False,
        "--no-backup",
        help="Skip the automatic backup when writing in-place.",
    ),
) -> None:
    """Cascading cube-up across r01..r32 in one pass.

    For each rune tier, upgrade as many pairs as possible (respecting
    the 99-per-stack cap and any ``--keep`` floors). Runes produced at
    tier N are available to the tier-N iteration that follows, so
    chains cascade naturally.

    Example:
        d2rr-toolkit cube-up bulk shared.d2i --keep r09:3 --keep r15:20
    """

    min_keep = _parse_min_keep(keep) if keep else None
    backup = not (no_backup or out is not None)
    try:
        res = cube_up_file_bulk(save_file, min_keep=min_keep, dest_path=out, backup=backup)
    except Section5MissingError as e:
        err_console.print(f"[bold red]Cube-up failed:[/] {e}")
        raise typer.Exit(1)
    except FileNotFoundError as e:
        err_console.print(f"[bold red]File not found:[/] {e}")
        raise typer.Exit(1)

    _print_result_table(res.result, "Cascading cube-up r01..r32")
    if res.result.capped_by_output_limit:
        console.print(
            "[yellow]Some upgrades hit the 99-stack cap:[/] "
            + ", ".join(f"{c}+{n}" for c, n in sorted(res.result.capped_by_output_limit.items()))
        )
    console.print(f"[green]Wrote:[/] {res.output_path}")
    if res.backup_path:
        console.print(f"[dim]Backup:[/] {res.backup_path}")

"""Typer CLI entry point for D2RR Toolkit.

Top-level commands:
  parse        - Parse a .d2s save and list items.
  dump-header  - Dump raw header fields for binary verification.
  inspect      - Render the full tooltip-style item view.

Command groups:
  archive - Infinite Archive orchestration (SQLite-backed):
    extract   - Move a stash tab's items into the archive DB.
    restore   - Restore archived items back into a .d2i tab.
    list      - List archived items (filter by character / tab / quality).
    backups   - List available backups of a save path.
    rollback  - Restore a save path from its most recent backup.
  stash   - Section 5 database (gems / materials / runes):
    status    - Summarise the Section 5 DB contents.
    seed      - Populate the DB from a .d2i file.
    convert   - Cross-convert gem / rune items per cubemain recipes.

This package assembles the Typer app from thematic sub-modules:
  * ``_common``  - game-data loader helpers shared by every command.
  * ``_parse``   - ``parse`` + ``dump-header`` commands.
  * ``_inspect`` - ``inspect`` command + all tooltip-rendering helpers.
  * ``_archive`` - ``archive`` sub-command group + shared mode resolvers.
  * ``_stash``   - ``stash`` sub-command group.

See docs/CLI_REFERENCE.md for per-command arguments, examples, and exit codes.
"""

import sys

# Force UTF-8 output on Windows terminals (box-drawing chars, em-dashes, etc.)
# `reconfigure` is a TextIOWrapper-only method; sys.stdout is typed as TextIO
# in the stubs, but on a real terminal it IS a TextIOWrapper. Wrapped in
# AttributeError catch for the case it's not (pipe / redirection).
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except AttributeError:
        pass

import typer
from rich.console import Console

app = typer.Typer(
    name="d2rr-toolkit",
    help="The Infinite Archive of Sanctuary - D2R Reimagined item parser.",
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True, style="red")


# Re-export for backwards compatibility: 13 tests import
# ``from d2rr_toolkit.cli import _load_game_data``.
from ._common import _load_game_data, _do_load_game_data  # noqa: E402, F401

# Register sub-module commands by importing them in display order.
# Each import triggers the @app.command / @archive_app.command decorators;
# the order here dictates the order in ``d2rr-toolkit --help``.
from . import _parse  # noqa: E402, F401
from . import _inspect  # noqa: E402, F401
from . import _archive  # noqa: E402, F401
from . import _stash  # noqa: E402, F401
from . import _cube  # noqa: E402, F401


# ──────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────


def main() -> None:
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()

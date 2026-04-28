"""`parse` and `dump-header` commands.

Lightweight top-level commands that read a ``.d2s`` file and render a
character overview / raw header dump to the terminal. Full tooltip-style
item inspection lives in :mod:`d2rr_toolkit.cli._inspect`.
"""

import logging
from pathlib import Path

import typer
from rich import box
from rich.panel import Panel
from rich.table import Table

from d2rr_toolkit.exceptions import (
    InvalidSignatureError,
    ToolkitError,
    UnsupportedVersionError,
)
from d2rr_toolkit.game_data.item_names import get_item_names_db
from d2rr_toolkit.parsers.d2s_parser import D2SParser

from . import app, console, err_console
from ._common import _load_game_data
import traceback
import struct
from ._inspect import _render_character
from d2rr_toolkit.game_data.charstats import get_charstats_db
from d2rr_toolkit.game_data.item_stat_cost import get_isc_db
from d2rr_toolkit.game_data.item_types import get_item_type_db


@app.command()
def parse(
    d2s_file: Path = typer.Argument(..., help="Path to the .d2s character save file."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show debug output."),
) -> None:
    """Parse a .d2s character save file and list all items.

    Example:
        d2rr-toolkit parse character.d2s
        d2rr-toolkit parse character.d2s --verbose
    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")

    if not d2s_file.exists():
        err_console.print(f"File not found: {d2s_file}")
        raise typer.Exit(1)

    if d2s_file.suffix.lower() != ".d2s":
        console.print(f"[yellow]Warning:[/] File does not have .d2s extension: {d2s_file.suffix}")

    # Load all game data through the Iron Rule (Reimagined mod first,
    # D2R Resurrected CASC fallback). Required - the parser cannot
    # function without it.
    if not _load_game_data(d2s_file):
        err_console.print(
            "[red bold]ERROR:[/] Game data not found!\n\n"
            "D2RR Toolkit requires D2R Reimagined to be installed.\n"
            "Set D2RR_D2R_INSTALL and D2RR_MOD_DIR environment variables "
            "to the D2R install root and Reimagined mod directory "
            "respectively, or rely on the Windows default "
            "(C:\\Program Files (x86)\\Diablo II Resurrected\\mods\\Reimagined)."
        )
        raise typer.Exit(1)
    # Game data loaded successfully - get database handles.

    if True:  # keep indent level for minimal diff
        isc = get_isc_db()
        itdb = get_item_type_db()
        cs = get_charstats_db()
        names_db = get_item_names_db()
        console.print(
            f"[dim]Game data loaded: {len(isc)} stats | "
            f"{len(itdb._armor_codes)} armor / "
            f"{len(itdb._weapon_codes)} weapon / "
            f"{len(itdb._misc_codes)} misc item codes | "
            f"{len(cs.all_classes())} classes | "
            f"{len(names_db._unique_keys):,} unique / "
            f"{len(names_db._set_item_keys):,} set / "
            f"{len(names_db._prefix_names):,} prefix / "
            f"{len(names_db._suffix_names):,} suffix / "
            f"{len(names_db._runeword_keys):,} runewords / "
            f"{len(names_db._rareprefix_names)} rare-prefix / "
            f"{len(names_db._raresuffix_names)} rare-suffix[/]"
        )
    else:
        console.print(
            "[yellow]Warning:[/] Game data (excel/) not found. Item parsing will be incomplete."
        )

    try:
        parser = D2SParser(d2s_file)
        character = parser.parse()
    except InvalidSignatureError as e:
        err_console.print(f"[bold red]Invalid file:[/] {e}")
        raise typer.Exit(1)
    except UnsupportedVersionError as e:
        err_console.print(f"[bold red]Unsupported version:[/] {e}")
        raise typer.Exit(1)
    except ToolkitError as e:
        err_console.print(f"[bold red]Parse error:[/] {e}")
        if verbose:

            traceback.print_exc()
        raise typer.Exit(1)

    # Imported lazily so that ``_inspect`` (which registers the ``inspect``
    # command) is not pulled in at module load, keeping the --help command
    # order parse / dump-header / inspect / archive / stash.

    _render_character(character)


@app.command(name="dump-header")
def dump_header(
    d2s_file: Path = typer.Argument(..., help="Path to the .d2s character save file."),
) -> None:
    """Dump raw header fields for verification purposes.

    Reads only the fixed header fields without parsing items or stats.
    Useful for quick inspection and verification script output comparison.

    Example:
        d2rr-toolkit dump-header character.d2s
    """

    if not d2s_file.exists():
        err_console.print(f"File not found: {d2s_file}")
        raise typer.Exit(1)

    data = d2s_file.read_bytes()

    console.print()
    console.print(
        Panel(
            f"[bold]D2RR Toolkit[/] - Header Dump\n[dim]{d2s_file}[/]",
            style="cyan",
        )
    )

    # Fixed header fields [BINARY_VERIFIED]
    signature = struct.unpack_from("<I", data, 0x00)[0]
    version = struct.unpack_from("<I", data, 0x04)[0]
    file_size = struct.unpack_from("<I", data, 0x08)[0]
    checksum = struct.unpack_from("<I", data, 0x0C)[0]
    char_class = data[0x18]
    level = data[0x1B]

    # Name at 0x12B [BINARY_VERIFIED]
    name_bytes = data[0x12B:]
    null_pos = name_bytes.find(0x00)
    name = name_bytes[:null_pos].decode("ascii", errors="replace") if null_pos != -1 else "???"

    # Find 'gf' marker
    gf_pos = data.find(b"gf", 800)

    # Charstats DB needed for class-name resolution; load on demand because
    # dump-header is sometimes invoked on a corrupt/unparseable save where
    # full game-data load would fail.

    cs = get_charstats_db()

    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("Field", style="dim")
    table.add_column("Offset")
    table.add_column("Value")
    table.add_column("Status")

    table.add_row(
        "Signature",
        "0x0000",
        f"0x{signature:08X}",
        "[BINARY_VERIFIED]" if signature == 0xAA55AA55 else "WRONG",
    )
    table.add_row(
        "Version",
        "0x0004",
        str(version),
        "[BINARY_VERIFIED]" if version == 105 else "unexpected (105 required)",
    )
    table.add_row("File size", "0x0008", f"{file_size} bytes", "")
    table.add_row("Checksum", "0x000C", f"0x{checksum:08X}", "")
    table.add_row(
        "Class", "0x0018", f"{char_class} = {cs.get_class_name(char_class)}", "[BINARY_VERIFIED]"
    )
    table.add_row("Level", "0x001B", str(level), "[BINARY_VERIFIED]")
    table.add_row("Name", "0x012B", name or "(empty)", "[BINARY_VERIFIED]")
    table.add_row(
        "'gf' marker",
        f"0x{gf_pos:04X}" if gf_pos != -1 else "NOT FOUND",
        f"byte {gf_pos}" if gf_pos != -1 else "MISSING",
        "[BINARY_VERIFIED]" if gf_pos == 833 else "expected 833",
    )

    console.print(table)

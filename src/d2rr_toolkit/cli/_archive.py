"""Archive sub-commands (``d2rr-toolkit archive ...``).

The Infinite Archive orchestration: SQLite-backed item storage with
extract / restore / list / backups / rollback commands. Shares
``_CliMode``, ``_resolve_game_mode``, ``_resolve_db_path`` and
``_cli_mode_to_game_mode`` helpers with :mod:`d2rr_toolkit.cli._stash`.
"""

from pathlib import Path

import typer
from rich import box
from rich.table import Table

from d2rr_toolkit.database.modes import (
    DatabaseModeMismatchError,
    GameMode,
    GameModeError,
    default_archive_db_path,
    mode_from_character,
    mode_from_stash_filename,
)
from d2rr_toolkit.display.colors import get_title_color
from d2rr_toolkit.models.character import ParsedCharacter

from . import app, console, err_console
from ._common import _load_game_data


# ═══════════════════════════════════════════════════════════════════════════════
# Archive commands - The Infinite Archive
# ═══════════════════════════════════════════════════════════════════════════════

archive_app = typer.Typer(help="The Infinite Archive - extract, store, restore items.")
app.add_typer(archive_app, name="archive")

#: Placeholder used as Typer's ``--db`` default. The actual path is
#: resolved at command time by :func:`_resolve_db_path` based on the
#: detected game mode, unless the user passes an explicit value.
DEFAULT_DB_PATH: Path | None = None


def _resolve_game_mode(
    *,
    save_file: Path | None = None,
    character: ParsedCharacter | None = None,
    explicit: GameMode | None = None,
) -> GameMode:
    """Determine the game mode for a CLI command.

    Priority order:

    1. ``explicit`` - the user passed ``--mode`` on the command line.
    2. ``character`` - a parsed character's ``is_hardcore`` bit wins
       over filename heuristics because it is binary-authoritative.
    3. ``save_file`` - sniff the mode from the filename. Used for
       ``.d2i`` stash files where no character is available.

    If none of these yield a mode, :class:`GameModeError` is raised and
    the CLI prints a clear error message.
    """
    if explicit is not None:
        return explicit
    if character is not None:
        return mode_from_character(character)
    if save_file is not None:
        if save_file.suffix.lower() == ".d2i":
            return mode_from_stash_filename(save_file)
        # .d2s without a parsed character - caller should have parsed it.
        raise GameModeError(
            f"Cannot determine game mode from {save_file.name!r} without "
            "parsing the character. Parse it first or pass --mode."
        )
    raise GameModeError("No mode source available - pass --mode or a save file.")


def _resolve_db_path(
    mode: GameMode,
    *,
    db_path_override: Path | None = None,
) -> Path:
    """Return the mode-specific archive DB path, honouring a user override.

    Exits the CLI with a friendly error message (``typer.Exit(1)``) if
    the default save directory cannot be resolved - this keeps the
    user from seeing a raw ``ConfigurationError`` traceback when they
    invoke a command without ``--db`` on a system where
    ``D2RR_SAVE_DIR`` is not set and no Windows heuristic applies.
    """

    if db_path_override is not None:
        return db_path_override
    try:
        return default_archive_db_path(mode)
    except ConfigurationError as e:
        err_console.print(f"[bold red]Save-dir configuration:[/] {e}")
        raise typer.Exit(1)


#: Typer annotation for the shared ``--mode`` flag. Wrapped in an Enum to
#: get tab-completion and proper validation error messages.
from enum import StrEnum  # deferred: only used in CLI option declarations
from d2rr_toolkit.archive import (
    ArchiveError,
    extract_from_d2i,
    restore_to_d2i,
)
from d2rr_toolkit.backup import (
    BACKUP_ROOT,
    list_backups,
    rollback,
)
from d2rr_toolkit.database.item_db import open_item_db
from d2rr_toolkit.exceptions import ConfigurationError


class _CliMode(StrEnum):
    """CLI-facing enum wrapper around the ``GameMode`` literal."""

    softcore = "softcore"
    hardcore = "hardcore"


def _cli_mode_to_game_mode(mode: _CliMode | None) -> GameMode | None:
    """Convert the CLI enum to the toolkit literal, or ``None``."""
    if mode is None:
        return None
    return mode.value


@archive_app.command("extract")
def archive_extract(
    save_file: Path = typer.Argument(..., help="Path to .d2i stash file."),
    tab: int = typer.Option(..., "--tab", "-t", help="Tab index (0-based)."),
    item: int = typer.Option(..., "--item", "-i", help="Item index within tab (0-based)."),
    db_path: Path | None = typer.Option(
        DEFAULT_DB_PATH, "--db", help="Path to archive database (overrides mode-derived default)."
    ),
    mode: _CliMode | None = typer.Option(
        None,
        "--mode",
        "-m",
        help="Game mode (softcore/hardcore). Auto-detected from filename if omitted.",
    ),
    name: str = typer.Option("", "--name", "-n", help="Display name for the item."),
) -> None:
    """Extract an item from a stash into the Infinite Archive.

    Creates a backup of the save file before modification. The item is
    removed from the stash and stored in the database. SoftCore and
    HardCore archives are kept in physically separate files so a
    hardcore character's items can never leak into the softcore pool.

    Example:
        d2rr-toolkit archive extract ModernSharedStashSoftCoreV2.d2i --tab 0 --item 2
    """
    _load_game_data(save_file)


    try:
        game_mode = _resolve_game_mode(
            save_file=save_file,
            explicit=_cli_mode_to_game_mode(mode),
        )
    except GameModeError as e:
        err_console.print(f"[bold red]Mode error:[/] {e}")
        raise typer.Exit(1)

    resolved_path = _resolve_db_path(game_mode, db_path_override=db_path)
    try:
        db = open_item_db(game_mode, db_path=resolved_path)
    except DatabaseModeMismatchError as e:
        err_console.print(f"[bold red]DB mode mismatch:[/] {e}")
        raise typer.Exit(1)

    try:
        db_id = extract_from_d2i(save_file, tab, item, db, display_name=name)
        console.print(f"[green]Extracted item -> {game_mode} Archive (id={db_id})[/]")
    except ArchiveError as e:
        err_console.print(f"[bold red]Archive error:[/] {e}")
        raise typer.Exit(1)
    finally:
        db.close()


@archive_app.command("restore")
def archive_restore(
    item_id: int = typer.Argument(..., help="Database item ID to restore."),
    save_file: Path = typer.Argument(..., help="Path to .d2i stash file."),
    tab: int = typer.Option(0, "--tab", "-t", help="Tab index to insert into (0-based)."),
    db_path: Path | None = typer.Option(
        DEFAULT_DB_PATH, "--db", help="Path to archive database (overrides mode-derived default)."
    ),
    mode: _CliMode | None = typer.Option(
        None,
        "--mode",
        "-m",
        help="Game mode (softcore/hardcore). Auto-detected from filename if omitted.",
    ),
) -> None:
    """Restore an item from the Infinite Archive into a stash.

    Creates a backup of the save file before modification. The game
    mode is auto-detected from the stash filename so a softcore item
    cannot be restored into a hardcore stash.

    Example:
        d2rr-toolkit archive restore 42 ModernSharedStashSoftCoreV2.d2i --tab 1
    """
    _load_game_data(save_file)


    try:
        game_mode = _resolve_game_mode(
            save_file=save_file,
            explicit=_cli_mode_to_game_mode(mode),
        )
    except GameModeError as e:
        err_console.print(f"[bold red]Mode error:[/] {e}")
        raise typer.Exit(1)

    resolved_path = _resolve_db_path(game_mode, db_path_override=db_path)
    try:
        db = open_item_db(game_mode, db_path=resolved_path)
    except DatabaseModeMismatchError as e:
        err_console.print(f"[bold red]DB mode mismatch:[/] {e}")
        raise typer.Exit(1)

    try:
        restore_to_d2i(item_id, save_file, tab, db)
        console.print(
            f"[green]Restored item (id={item_id}) -> {save_file.name} tab {tab} [{game_mode}][/]"
        )
    except ArchiveError as e:
        err_console.print(f"[bold red]Archive error:[/] {e}")
        raise typer.Exit(1)
    finally:
        db.close()


@archive_app.command("list")
def archive_list(
    db_path: Path | None = typer.Option(
        DEFAULT_DB_PATH, "--db", help="Path to archive database (overrides mode-derived default)."
    ),
    mode: _CliMode = typer.Option(
        _CliMode.softcore, "--mode", "-m", help="Game mode (softcore/hardcore)."
    ),
    search: str = typer.Option("", "--search", "-s", help="Search by item name."),
    quality: int | None = typer.Option(None, "--quality", "-q", help="Filter by quality."),
) -> None:
    """Browse or search the Infinite Archive.

    Because ``list`` has no save file to sniff, the ``--mode`` flag is
    required (defaults to softcore). To see the hardcore archive, pass
    ``--mode hardcore``.

    Example:
        d2rr-toolkit archive list
        d2rr-toolkit archive list --mode hardcore
        d2rr-toolkit archive list --search "Blade"
        d2rr-toolkit archive list --quality 7
    """

    game_mode: GameMode = mode.value
    resolved_path = _resolve_db_path(game_mode, db_path_override=db_path)

    if not resolved_path.exists():
        console.print(
            f"[dim]{game_mode.capitalize()} archive is empty "
            f"(no database at {resolved_path.name}).[/]"
        )
        return

    try:
        db = open_item_db(game_mode, db_path=resolved_path)
    except DatabaseModeMismatchError as e:
        err_console.print(f"[bold red]DB mode mismatch:[/] {e}")
        raise typer.Exit(1)
    try:
        if search or quality is not None:
            items = db.search(name=search or None, quality=quality)
        else:
            items = db.list_items()

        if not items:
            console.print("[dim]No items found.[/]")
            return

        table = Table(title=f"Infinite Archive ({len(items)} items)", box=box.ROUNDED)
        table.add_column("ID", style="cyan", width=5)
        table.add_column("Name", style="bold")
        table.add_column("Code", width=6)
        table.add_column("Quality", width=10)
        table.add_column("iLvl", width=5)
        table.add_column("Source", style="dim")
        table.add_column("Extracted", style="dim", width=19)

        for si in items:
            q_color = get_title_color(si.quality)
            table.add_row(
                str(si.id),
                f"[{q_color}]{si.item_name or si.item_code}[/]",
                si.item_code,
                si.quality_name,
                str(si.item_level),
                f"{Path(si.source_file).name} tab {si.source_tab}"
                if si.source_tab >= 0
                else Path(si.source_file).name,
                si.extracted_at[:19],
            )

        console.print(table)
    finally:
        db.close()


@archive_app.command("backups")
def archive_backups(
    save_file: Path = typer.Argument(..., help="Path to the save file."),
) -> None:
    """List available backups for a save file.

    Example:
        d2rr-toolkit archive backups stash.d2i
    """

    backups = list_backups(save_file)
    if not backups:
        console.print("[dim]No backups found.[/]")
        return

    console.print(f"[bold]Backups for {save_file.name}:[/]")
    for bp in backups:
        console.print(f"  {bp.name}  ({bp.stat().st_size} bytes)")


@archive_app.command("rollback")
def archive_rollback(
    save_file: Path = typer.Argument(..., help="Path to the save file."),
    backup_name: str = typer.Argument(..., help="Backup filename to restore from."),
) -> None:
    """Restore a save file from a backup.

    Example:
        d2rr-toolkit archive rollback stash.d2i stash.20260331_120000.d2i.bak
    """

    backup_path = BACKUP_ROOT / save_file.name / backup_name
    if not backup_path.exists():
        err_console.print(f"Backup not found: {backup_path}")
        raise typer.Exit(1)

    rollback(save_file, backup_path)
    console.print(f"[green]Rolled back {save_file.name} from {backup_name}[/]")

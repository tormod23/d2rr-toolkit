"""Stash sub-commands (``d2rr-toolkit stash ...``).

Section 5 database integration: push gems/runes/materials into the
archive (``seed``), list its contents (``status``), and cross-convert
gem/rune items per cubemain recipes (``convert``). Shares the
``_CliMode`` / ``_resolve_game_mode`` / ``_cli_mode_to_game_mode`` /
``DEFAULT_DB_PATH`` helpers with :mod:`d2rr_toolkit.cli._archive`.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.table import Table

from d2rr_toolkit.database.modes import (
    DatabaseModeMismatchError,
    GameMode,
    GameModeError,
)

from . import app, console, err_console
from ._archive import (
    DEFAULT_DB_PATH,
    _CliMode,
    _cli_mode_to_game_mode,
    _resolve_db_path,
    _resolve_game_mode,
)
from ._common import _do_load_game_data, _load_game_data


# ──────────────────────────────────────────────────────────────
# Stash commands (Section 5: Gems/Materials/Runes DB integration)
# ──────────────────────────────────────────────────────────────

stash_app = typer.Typer(
    help="Section 5 DB - push gems/runes/materials into the archive, pull them back out."
)
app.add_typer(stash_app, name="stash")


def _is_gem_in_tab5(item_code: str) -> bool:
    """Return True if ``item_code`` belongs in D2I tab 5 (Gems / Materials / Runes)."""
    from d2rr_toolkit.database.section5_db import is_gem_code

    return is_gem_code(item_code)


@stash_app.command("status")
def stash_status(
    db_path: Path | None = typer.Option(
        DEFAULT_DB_PATH, "--db", help="Path to archive database (overrides mode-derived default)."
    ),
    mode: _CliMode = typer.Option(
        _CliMode.softcore, "--mode", "-m", help="Game mode (softcore/hardcore)."
    ),
) -> None:
    """Show the current Section 5 DB contents: stacks, gem pool, gem templates.

    Defaults to softcore; pass ``--mode hardcore`` to inspect the
    hardcore Section 5 database.

    Example:
        d2rr-toolkit stash status
        d2rr-toolkit stash status --mode hardcore
    """
    from d2rr_toolkit.database.section5_db import open_section5_db
    from d2rr_toolkit.game_data.item_names import get_item_names_db

    # Load names if available for display; failures are non-fatal and
    # fall through to raw item codes. The fallback is deliberate (the
    # command still works on a misconfigured install) but the failure
    # itself MUST be surfaced so the user knows why codes look raw.
    try:
        _do_load_game_data()
    except Exception as e:  # noqa: BLE001 - non-fatal: degrade to raw codes
        logger.warning(
            "Game-data load failed; item names unavailable: %s",
            e,
            exc_info=True,
        )
        err_console.print(
            "[dim]Note:[/] game data could not be loaded - item codes will be shown raw.",
        )

    names = get_item_names_db()

    def nm(c: str) -> str:
        return (names.get_base_item_name(c, "enUS") or c) if names.is_loaded() else c

    game_mode: GameMode = mode.value  # type: ignore[assignment]
    resolved_path = _resolve_db_path(game_mode, db_path_override=db_path)
    try:
        db = open_section5_db(game_mode, db_path=resolved_path)
    except DatabaseModeMismatchError as e:
        err_console.print(f"[bold red]DB mode mismatch:[/] {e}")
        raise typer.Exit(1)
    try:
        stacks = db.list_stacks()
        templates = db.list_gem_templates()
        pool = db.get_gem_pool_count()

        from rich.table import Table

        if stacks:
            tbl = Table(title=f"Non-Gem Stacks ({len(stacks)} codes)")
            tbl.add_column("Code")
            tbl.add_column("Name")
            tbl.add_column("Count", justify="right")
            for s in stacks:
                tbl.add_row(s.item_code, nm(s.item_code), str(s.total_count))
            console.print(tbl)
        else:
            console.print("[dim]No non-gem stacks stored.[/]")

        console.print(f"\n[bold]Gem pool total:[/] {pool} gems")
        if templates:
            tbl = Table(title=f"Gem templates ({len(templates)} types)")
            tbl.add_column("Code")
            tbl.add_column("Name")
            for t in templates:
                tbl.add_row(t.gem_code, nm(t.gem_code))
            console.print(tbl)
        else:
            console.print("[dim]No gem templates seeded yet.[/]")
    finally:
        db.close()


@stash_app.command("seed")
def stash_seed(
    save_file: Path = typer.Argument(..., help="Path to .d2i shared stash file."),
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
    """Seed the Section 5 DB with the entire contents of a stash file's Section 5.

    Reads only - the source .d2i is not modified. Every item in tab 5 is
    routed to the right DB target (stack / gem pool / cluster roll) and
    the counts are incremented by each item's displayed quantity. The
    game mode is auto-detected from the stash filename so SoftCore and
    HardCore seeds never land in the same database.

    Example:
        d2rr-toolkit stash seed ModernSharedStashSoftCoreV2.d2i
        d2rr-toolkit stash seed ModernSharedStashHardCoreV2.d2i
    """
    _load_game_data(save_file)

    from d2rr_toolkit.database.section5_db import (
        is_gem_code,
        is_gem_cluster,
        open_section5_db,
    )
    from d2rr_toolkit.parsers.d2i_parser import D2IParser

    try:
        game_mode = _resolve_game_mode(
            save_file=save_file,
            explicit=_cli_mode_to_game_mode(mode),
        )
    except GameModeError as e:
        err_console.print(f"[bold red]Mode error:[/] {e}")
        raise typer.Exit(1)

    stash = D2IParser(save_file).parse()
    if len(stash.tabs) <= 5:
        err_console.print(f"[red]{save_file.name} has no Section 5 tab[/]")
        raise typer.Exit(1)
    t5 = stash.tabs[5]
    if not t5.items:
        console.print("[yellow]Section 5 is empty - nothing to seed.[/]")
        return

    def disp(it) -> int:
        return it.quantity >> 1 if it.flags.simple else it.quantity

    resolved_path = _resolve_db_path(game_mode, db_path_override=db_path)
    try:
        db = open_section5_db(game_mode, db_path=resolved_path)
    except DatabaseModeMismatchError as e:
        err_console.print(f"[bold red]DB mode mismatch:[/] {e}")
        raise typer.Exit(1)
    import random as _rnd

    rng = _rnd.Random()
    stacks_seeded = 0
    gems_seeded = 0
    cluster_rolls = 0
    rolled_total = 0
    try:
        for item in t5.items:
            qty = disp(item)
            if qty < 1:
                continue
            if is_gem_cluster(item.item_code):
                rolled = db.push_gem_cluster(item, rng=rng)
                cluster_rolls += 1
                rolled_total += rolled
            elif is_gem_code(item.item_code):
                db.push_gem(item, qty)
                gems_seeded += qty
            else:
                db.push_stack(item, qty)
                stacks_seeded += qty
        console.print(
            f"[green]Seeded:[/] {stacks_seeded} stack units, "
            f"{gems_seeded} gems (direct), {cluster_rolls} Gem Cluster"
            f"{'s' if cluster_rolls != 1 else ''} rolled "
            f"[bold]{rolled_total}[/] gems."
        )
        console.print(f"Gem pool total now: [bold]{db.get_gem_pool_count()}[/]")
    finally:
        db.close()


@stash_app.command("convert")
def stash_convert(
    rune_code_arg: str = typer.Argument(
        ..., metavar="CODE", help="Source rune code (e.g. r01 for El)."
    ),
    up: bool = typer.Option(False, "--up", help="Upgrade 2x CODE into 1x next-tier rune."),
    down: bool = typer.Option(
        False, "--down", help="Downgrade 1x CODE into 1x previous-tier rune."
    ),
    db_path: Path | None = typer.Option(
        DEFAULT_DB_PATH, "--db", help="Path to archive database (overrides mode-derived default)."
    ),
    mode: _CliMode = typer.Option(
        _CliMode.softcore, "--mode", "-m", help="Game mode (softcore/hardcore)."
    ),
) -> None:
    """Convert runes within the DB (pure arithmetic, no save-file involvement).

    Both source and target rune types must already have templates in the
    DB (i.e. you must have seeded at least one of each with ``stash seed``
    first). SoftCore and HardCore databases have independent rune pools.

    Example:
        d2rr-toolkit stash convert r01 --up     # 2 El -> 1 Eld (softcore)
        d2rr-toolkit stash convert r02 --down --mode hardcore
    """
    if up == down:
        err_console.print("[red]Specify exactly one of --up or --down.[/]")
        raise typer.Exit(1)

    from d2rr_toolkit.database.section5_db import (
        Section5DBError,
        open_section5_db,
    )

    game_mode: GameMode = mode.value  # type: ignore[assignment]
    resolved_path = _resolve_db_path(game_mode, db_path_override=db_path)
    try:
        db = open_section5_db(game_mode, db_path=resolved_path)
    except DatabaseModeMismatchError as e:
        err_console.print(f"[bold red]DB mode mismatch:[/] {e}")
        raise typer.Exit(1)
    try:
        target = (
            db.convert_runes_upgrade(rune_code_arg)
            if up
            else db.convert_runes_downgrade(rune_code_arg)
        )
        console.print(f"[green]Converted[/] {rune_code_arg} -> {target}")
        console.print(f"  {rune_code_arg} count now: {db.get_stack_count(rune_code_arg)}")
        console.print(f"  {target} count now: {db.get_stack_count(target)}")
    except Section5DBError as e:
        err_console.print(f"[red]{type(e).__name__}:[/] {e}")
        raise typer.Exit(1)
    except ValueError as e:
        err_console.print(f"[red]ValueError:[/] {e}")
        raise typer.Exit(1)
    finally:
        db.close()

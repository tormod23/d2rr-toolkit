"""Full tooltip-style item rendering: `inspect` command + helpers.

Renders a ParsedCharacter / D2I stash with Rich panels, tables and colour
tokens. Owns every ``_render_*`` / ``_add_item_row`` / ``_format_properties``
helper previously inlined at the top of ``cli.py``. The ``parse`` command
in :mod:`d2rr_toolkit.cli._parse` imports :func:`_render_character` from
here; nothing else reaches inside.
"""

from __future__ import annotations

import logging
from pathlib import Path

import typer
from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from d2rr_toolkit.constants import (
    PANEL_NAMES,
    QUALITY_NAMES,
    SLOT_NAMES,
)
from d2rr_toolkit.display.colors import (
    COLOR_CRAFTED,
    COLOR_CORRUPT,
    COLOR_ENCHANT,
    COLOR_MAGIC,
    COLOR_RARE,
    COLOR_SET,
    COLOR_UNIQUE,
    OBSOLETE_GEM_PREFIXES,
    get_item_display_color,
    get_subtype_color,
    get_title_color,
)
from d2rr_toolkit.exceptions import (
    InvalidSignatureError,
    ToolkitError,
    UnsupportedVersionError,
)
from d2rr_toolkit.game_data.item_names import get_item_names_db
from d2rr_toolkit.game_data.properties import get_properties_db
from d2rr_toolkit.game_data.property_formatter import get_property_formatter
from d2rr_toolkit.game_data.sets import get_sets_db
from d2rr_toolkit.game_data.skills import get_skill_db
from d2rr_toolkit.models.character import ParsedCharacter, ParsedItem
from d2rr_toolkit.parsers.d2s_parser import D2SParser

from . import app, console, err_console
from ._common import _load_game_data

# Local alias for the shared material-color function.
_simple_item_color = get_item_display_color


# ──────────────────────────────────────────────────────────────
# Rendering helpers
# ──────────────────────────────────────────────────────────────


def _render_character(character: ParsedCharacter) -> None:
    """Render the parsed character to the terminal using Rich."""
    h = character.header
    s = character.stats

    console.print()
    console.print(
        Panel(
            f"[bold {COLOR_UNIQUE}]{h.character_name}[/]  [dim]·[/]  "
            f"[cyan]{h.character_class_name}[/]  "
            f"[dim]Level[/] [bold]{h.level}[/]",
            title="[bold]D2RR Toolkit - Character[/]",
            style="dim",
        )
    )

    # Stats table
    stats_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    stats_table.add_column("Stat", style="dim")
    stats_table.add_column("Value", style="bold")
    stats_table.add_column("Stat", style="dim")
    stats_table.add_column("Value", style="bold")

    stats_table.add_row("Strength", str(s.strength), "Life", f"{s.current_hp:.0f} / {s.max_hp:.0f}")
    stats_table.add_row(
        "Dexterity", str(s.dexterity), "Mana", f"{s.current_mana:.0f} / {s.max_mana:.0f}"
    )
    stats_table.add_row(
        "Vitality", str(s.vitality), "Stamina", f"{s.current_stamina:.0f} / {s.max_stamina:.0f}"
    )
    stats_table.add_row("Energy", str(s.energy), "Gold", f"{s.gold_inventory:,}")
    stats_table.add_row("Stat pts", str(s.stat_points_remaining), "Stash gold", f"{s.gold_stash:,}")
    stats_table.add_row(
        "Skill pts", str(s.skill_points_remaining), "Experience", f"{s.experience:,}"
    )

    console.print(stats_table)

    # Items
    console.print()
    console.print(f"[bold]Items[/] [dim]({len(character.items)} total)[/]")
    console.print()

    if not character.items:
        console.print("  [dim]No items.[/]")
        return

    item_table = Table(box=box.ROUNDED, show_header=True, header_style="bold")
    item_table.add_column("Code", style="dim", width=6)
    item_table.add_column("Name", width=28)
    item_table.add_column("Quality", width=10)
    item_table.add_column("Location", width=12)
    item_table.add_column("Pos", width=6)
    item_table.add_column("iLVL", width=5)
    item_table.add_column("Defense", width=8)
    item_table.add_column("Dur", width=10)
    item_table.add_column("Flags", width=16)

    equipped_items = character.items_equipped()
    inventory_items = character.items_in_inventory()
    belt_items = character.items_in_belt()

    sections = [
        ("Equipped", equipped_items),
        ("Inventory", inventory_items),
        ("Belt", belt_items),
    ]

    for section_name, section_items in sections:
        if not section_items:
            continue
        item_table.add_row(
            f"[bold dim]── {section_name} ──[/]",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            style="dim",
        )
        for item in section_items:
            _add_item_row(item_table, item)

    console.print(item_table)
    console.print()


def _add_item_row(table: Table, item: ParsedItem) -> None:
    """Add one item row to the items table."""
    f = item.flags

    # Quality color and name (title-line semantics - Crafted => Magic-blue)
    quality_id = item.extended.quality if item.extended else 2
    color = get_title_color(quality_id)
    quality_name = QUALITY_NAMES.get(quality_id, "?")

    # Display name via ItemNamesDatabase
    names_db = get_item_names_db()
    if names_db.is_loaded() and item.extended:
        display_name = (
            names_db.build_display_name(
                item.item_code,
                quality_id,
                unique_type_id=item.unique_type_id,
                set_item_id=item.set_item_id,
                prefix_id=item.prefix_id,
                suffix_id=item.suffix_id,
                rare_name_id1=item.rare_name_id1,
                rare_name_id2=item.rare_name_id2,
                runeword_id=item.runeword_id,
                is_runeword=item.flags.runeword,
                identified=item.flags.identified,
            )
            or ""
        )
    else:
        display_name = ""

    # Location
    if f.location_id == 1:  # equipped
        location = SLOT_NAMES.get(f.equipped_slot, f"slot {f.equipped_slot}")
    elif f.location_id == 2:  # belt
        location = "Belt"
    else:  # stored
        location = PANEL_NAMES.get(f.panel_id, "?")

    pos = f"({f.position_x},{f.position_y})" if f.location_id == 0 else "-"
    ilvl = str(item.extended.item_level) if item.extended else "-"

    # Defense / Durability - weapons have armor_data for durability but no defense
    if item.armor_data:
        from d2rr_toolkit.game_data.item_types import get_item_type_db, ItemCategory as _IC

        dur = f"{item.armor_data.durability.current_durability}/{item.armor_data.durability.max_durability}"
        if get_item_type_db().classify(item.item_code) == _IC.ARMOR:
            defense = str(item.armor_data.defense_display)
        else:
            defense = "-"
    else:
        defense = "-"
        dur = "-"

    # Flags
    flag_parts = []
    if item.flags.starter_item:
        flag_parts.append("starter")
    if item.flags.simple:
        flag_parts.append("simple")
    if item.flags.ethereal:
        flag_parts.append("eth")
    if item.flags.socketed:
        flag_parts.append("sock")
    if item.flags.runeword:
        flag_parts.append("rw")
    if not item.flags.identified:
        flag_parts.append("unid")
    flags_str = " ".join(flag_parts) if flag_parts else ""

    table.add_row(
        item.item_code,
        Text(display_name, style=color),
        Text(quality_name, style=color),
        location,
        pos,
        ilvl,
        defense,
        dur,
        flags_str,
    )


@app.command()
def inspect(
    save_file: Path = typer.Argument(
        ..., help="Path to .d2s (character) or .d2i (shared stash) file."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show debug output."),
) -> None:
    """Inspect items in detail - full tooltip-style display with properties and set bonuses.

    Supports both .d2s (character) and .d2i (shared stash) files.

    Example:
        d2rr-toolkit inspect character.d2s
        d2rr-toolkit inspect ModernSharedStashSoftCoreV2.d2i
    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")

    if not save_file.exists():
        err_console.print(f"File not found: {save_file}")
        raise typer.Exit(1)

    _load_game_data(save_file)

    ext = save_file.suffix.lower()
    if ext == ".d2i":
        _inspect_d2i(save_file)
    else:
        _inspect_d2s(save_file)


def _inspect_d2s(d2s_file: Path) -> None:
    """Inspect a .d2s character save file."""
    try:
        parser = D2SParser(d2s_file)
        character = parser.parse()
    except (InvalidSignatureError, UnsupportedVersionError, ToolkitError) as e:
        err_console.print(f"[bold red]Parse error:[/] {e}")
        raise typer.Exit(1)

    h = character.header
    console.print()
    console.print(
        Panel(
            f"[bold {COLOR_UNIQUE}]{h.character_name}[/]  [dim]·[/]  "
            f"[cyan]{h.character_class_name}[/]  "
            f"[dim]Level[/] [bold]{h.level}[/]",
            title="[bold]D2RR Toolkit - Inspect[/]",
            style="dim",
        )
    )

    _render_inspect(character)


def _inspect_d2i(d2i_file: Path) -> None:
    """Inspect a .d2i shared stash file."""
    from d2rr_toolkit.parsers.d2i_parser import D2IParser

    try:
        parser = D2IParser(d2i_file)
        stash = parser.parse()
    except (ToolkitError, Exception) as e:
        err_console.print(f"[bold red]Parse error:[/] {e}")
        raise typer.Exit(1)

    console.print()
    console.print(
        Panel(
            f"[bold {COLOR_UNIQUE}]Shared Stash[/]  [dim]·[/]  "
            f"{len(stash.tabs)} tabs  [dim]·[/]  "
            f"[bold]{stash.total_items}[/] items",
            title="[bold]D2RR Toolkit - Inspect (Stash)[/]",
            style="dim",
        )
    )

    _render_inspect_stash(stash)


def _render_inspect(character: ParsedCharacter) -> None:
    """Render full item detail panels."""
    from d2rr_toolkit.game_data.item_stat_cost import get_isc_db

    isc_db = get_isc_db()
    skills_db = get_skill_db()
    props_db = get_properties_db()
    formatter = get_property_formatter()
    sets_db = get_sets_db()
    names_db = get_item_names_db()

    # Count equipped set pieces per set name (for active bonus determination)
    equipped_set_counts: dict[str, int] = {}
    for item in character.items:
        if (
            item.flags.location_id == 1
            and item.extended
            and item.extended.quality == 5
            and item.set_item_id is not None
        ):
            item_def = sets_db.get_set_item(item.set_item_id)
            if item_def:
                equipped_set_counts[item_def.set_name] = (
                    equipped_set_counts.get(item_def.set_name, 0) + 1
                )

    # character.items now contains only ROOT items; socket children live
    # in each parent's socket_children list. Render directly.
    for item in character.items:
        _render_item_panel(
            item,
            isc_db,
            skills_db,
            props_db,
            formatter,
            sets_db,
            names_db,
            equipped_set_counts,
            children=list(item.socket_children),
        )

    # ── Mercenary items ─────────────────────────────────────────────────────
    if character.merc_items:
        from rich.text import Text

        console.print()
        console.print(Text("  Mercenary Equipment", style="bold"))

        # merc_items contains only ROOT items; children are nested.
        for item in character.merc_items:
            _render_item_panel(
                item,
                isc_db,
                skills_db,
                props_db,
                formatter,
                sets_db,
                names_db,
                equipped_set_counts,
                children=list(item.socket_children),
            )


def _is_materials_tab(tab, type_db) -> bool:
    """Return True if a tab consists mostly of simple items (gems/runes/materials)."""
    if not tab.items:
        return False
    simple_count = sum(1 for i in tab.items if i.flags.simple)
    return simple_count > len(tab.items) * 0.7  # >70% simple items


def _render_materials_tab(tab, names_db, type_db) -> None:
    """Render a compact display for tabs with gems, runes, and materials."""
    from rich.text import Text

    # Classify items into sections
    gems: list[ParsedItem] = []
    runes: list[ParsedItem] = []
    materials: list[ParsedItem] = []
    other: list[ParsedItem] = []

    _GEM_TYPES = {"gema", "gemd", "geme", "gemo", "gemr", "gems", "gemt", "gemx", "gemz"}
    _TOOL_TYPES = {"grab"}  # gem/rune/jewel pliers
    # Orbs (type=elix with code starting 'oo' or 'ka') belong in Gems section
    _ORB_PREFIXES = ("oo", "ka", "1g")  # ooa, ooc, ooe, ooi, oor, oos, ka3, 1gc
    _MATERIAL_TYPES = {"ques", "rpot", "wpot"}  # quest items, rejuv potions, xp potions

    for item in tab.items:
        t = type_db.get_item_type(item.item_code)
        code = item.item_code
        if t in ("rune", "runx"):
            runes.append(item)
        elif t in _GEM_TYPES or t in _TOOL_TYPES or any(code.startswith(p) for p in _ORB_PREFIXES):
            gems.append(item)
        elif t in _MATERIAL_TYPES or t == "elix":
            materials.append(item)
        else:
            other.append(item)

    # Quantity correction for display:
    # Simple items: raw 9-bit value includes a GUID flag bit -> ~2* actual. Correct with >> 1.
    # Extended items (AdvancedStashStackable): 7-bit value is correct as-is.
    def _display_qty(item: ParsedItem) -> int:
        if item.flags.simple:
            return item.quantity >> 1
        return item.quantity

    # Sort runes by rune number
    def _rune_num(item: ParsedItem) -> int:
        code = item.item_code
        if code.startswith("r") and code[1:].isdigit():
            return int(code[1:])
        if code.startswith("s") and code[1:].isdigit():
            return int(code[1:])  # rune stacks
        return 999

    runes.sort(key=_rune_num)

    # ── Gems section ──────────────────────────────────────────
    # (Colors and gem prefixes are defined in display_colors module.)

    # Gem sorting: obsolete classics -> orbs -> reimagined -> tools
    # Classic gem type order: Ruby(r), Sapphire(b/s), Topaz(y/t), Emerald(g/e), Diamond(w/d), Amethyst(v/a), Skull(k/z)
    _CLASSIC_TYPE_ORDER = {
        "r": 0,
        "b": 1,
        "y": 2,
        "g": 3,
        "w": 4,
        "v": 5,
        "k": 6,  # suffix char
        "s": 1,
        "t": 2,
        "e": 3,
        "d": 4,
        "a": 5,
        "z": 6,
    }  # gem type suffix
    _CLASSIC_QUALITY = {"c": 0, "f": 1, "s": 2, "l": 3, "z": 3, "p": 4}  # quality prefix char
    _ORB_ORDER = {"ka3": 0, "ooe": 1, "oor": 2, "oos": 3, "ooi": 4, "ooa": 5, "ooc": 6}
    _REIMAGINED_ORDER = {
        "gmr": 0,
        "gms": 1,
        "gmt": 2,
        "gme": 3,
        "gmd": 4,
        "gmm": 5,
        "gmo": 6,
        "gmk": 7,
    }

    def _gem_sort_key(item: ParsedItem) -> tuple:
        code = item.item_code
        # Section 0: Obsolete classic gems
        if any(code.startswith(p) for p in OBSOLETE_GEM_PREFIXES):
            if code.startswith("sk"):
                # Skulls: skc=Chipped, skf=Flawed, sku=Regular, skl=Flawless, skz=Perfect
                q = {"c": 0, "f": 1, "u": 2, "l": 3, "z": 4}.get(code[2], 9)
                return (0, 6, q)
            # Standard gems: g{quality}{type} e.g. gcr=Chipped Ruby
            gem_type = _CLASSIC_TYPE_ORDER.get(code[2], 9)
            gem_qual = _CLASSIC_QUALITY.get(code[1], 9)
            return (0, gem_type, gem_qual)
        # Section 1: Orbs
        if code in _ORB_ORDER:
            return (1, _ORB_ORDER[code], 0)
        # Section 2: Reimagined gems
        if code in _REIMAGINED_ORDER:
            return (2, _REIMAGINED_ORDER[code], 0)
        # Section 3: Tools (Gem Cluster, Pliers)
        tool_order = {"1gc": 0, "jwp": 1, "rup": 2}
        return (3, tool_order.get(code, 9), 0)

    gems.sort(key=_gem_sort_key)

    if gems:
        console.print(Text("  Gems", style="bold underline"))
        for item in gems:
            name = names_db.get_base_item_name(item.item_code) or item.item_code
            qty = _display_qty(item)
            clr = _simple_item_color(item.item_code, type_db.get_item_type(item.item_code))
            if qty > 0:
                line = Text.assemble(
                    ("    ", ""),
                    (name, clr),
                    (" ", ""),
                    (f"({qty})", "dim"),
                )
            else:
                line = Text(f"    {name}", style=clr)
            console.print(line)

    # ── Runes section ─────────────────────────────────────────
    if runes:
        console.print(Text("  Runes", style="bold underline"))
        for item in runes:
            code = item.item_code
            # Extract rune number from code (r01->1, r33->33)
            rune_num = _rune_num(item)
            # Get display name (e.g. "El Rune")
            full_name = names_db.get_base_item_name(code) or code
            # Strip "(#N)" suffix, "\n~Pick Up~", and any leftover from strings.json
            import re

            rune_name = re.sub(r"\s*\(#\d+\).*", "", full_name, flags=re.DOTALL).strip()
            qty = _display_qty(item)
            # Format: "El Rune" (orange) "(#1)" (yellow+white) "(n)" (grey)
            parts: list[tuple[str, str]] = [
                ("    ", ""),
                (rune_name, COLOR_CRAFTED),
                (" ", ""),
                ("(", COLOR_RARE),
                (f"#{rune_num}", "white"),
                (")", COLOR_RARE),
            ]
            if qty > 0:
                parts.append((" ", ""))
                parts.append((f"({qty})", "dim"))
            console.print(Text.assemble(*parts))

    # ── Materials section ─────────────────────────────────────
    if materials:
        console.print(Text("  Materials", style="bold underline"))
        for item in materials:
            name = names_db.get_base_item_name(item.item_code) or item.item_code
            qty = _display_qty(item)
            clr = _simple_item_color(item.item_code, type_db.get_item_type(item.item_code))
            if qty > 0:
                line = Text.assemble(
                    ("    ", ""),
                    (name, clr),
                    (" ", ""),
                    (f"({qty})", "dim"),
                )
            else:
                line = Text(f"    {name}", style=clr)
            console.print(line)

    # ── Other items (not classified - rendered as full panels) ─
    return other


def _render_inspect_stash(stash) -> None:
    """Render full item detail panels for a shared stash (.d2i)."""
    from d2rr_toolkit.game_data.item_stat_cost import get_isc_db
    from d2rr_toolkit.game_data.item_types import get_item_type_db

    isc_db = get_isc_db()
    skills_db = get_skill_db()
    props_db = get_properties_db()
    formatter = get_property_formatter()
    sets_db = get_sets_db()
    names_db = get_item_names_db()
    type_db = get_item_type_db()

    # No equipped items in stash -> empty set counts
    equipped_set_counts: dict[str, int] = {}

    for tab in stash.tabs:
        # Tab header
        console.print()
        n = len(tab.items)
        if n == 0:
            console.print(f"[dim]━━━ Tab {tab.tab_index + 1} (empty) ━━━[/]")
            continue
        console.print(f"[bold]━━━ Tab {tab.tab_index + 1} ({n} item{'s' if n != 1 else ''}) ━━━[/]")

        # Detect materials/gems/runes tab -> compact display
        if _is_materials_tab(tab, type_db):
            remaining = _render_materials_tab(tab, names_db, type_db)
            # Render any non-simple items as full panels
            for item in remaining or []:
                _render_item_panel(
                    item,
                    isc_db,
                    skills_db,
                    props_db,
                    formatter,
                    sets_db,
                    names_db,
                    equipped_set_counts,
                    children=[],
                )
            continue

        # tab.items contains only ROOT items; children are nested.
        for item in tab.items:
            _render_item_panel(
                item,
                isc_db,
                skills_db,
                props_db,
                formatter,
                sets_db,
                names_db,
                equipped_set_counts,
                children=list(item.socket_children),
            )


def _tier_suffix(item_code: str) -> str:
    """Return the tier display suffix - delegates to item_display."""
    from d2rr_toolkit.game_data.item_types import get_item_type_db
    from d2rr_toolkit.display.item_display import get_tier_suffix

    return get_tier_suffix(item_code, get_item_type_db())


def _rune_letter(rune_code: str, names_db) -> str:
    """Return the rune letter - delegates to item_display."""
    from d2rr_toolkit.display.item_display import get_rune_letter

    return get_rune_letter(rune_code, names_db)


def _format_properties(prop_list: list[dict], formatter, isc_db, skills_db) -> list[str]:
    """Format a property list to display strings, returning non-None lines."""
    if not formatter.is_loaded() or not isc_db.is_loaded():
        return [
            f"  [stat {p.get('stat_id', '?')}] = {p.get('value', p.get('level', '?'))}"
            for p in prop_list
        ]
    # The structured ``format_properties_grouped`` returns
    # FormattedProperty objects; the CLI renderer currently works on
    # plain strings (with its own COLOR_MAGIC style applied globally),
    # so route through the ``_plain`` compat wrapper.  A follow-up
    # could opt into per-segment colouring here to mirror in-game
    # fluff text colours.
    return formatter.format_properties_grouped_plain(prop_list, isc_db, skills_db)


def _styled_prop_lines(prop_lines: list[str]) -> list:
    """Apply per-line coloring: Corrupted=red, Enchantments=purple, rest=magic-blue.

    Returns a list of Rich Text objects with Corrupted first, then
    Enchantments, then remaining stats - matching in-game tooltip order.
    """
    from rich.text import Text

    corrupted = []
    enchant = []
    normal = []
    for line in prop_lines:
        if line == "Corrupted":
            corrupted.append(Text(line, style=COLOR_CORRUPT))
        elif line.startswith("Enchantments:"):
            # "Enchantments:" in purple, "x / n" in white
            enchant.append(
                Text.assemble(
                    ("Enchantments:", COLOR_ENCHANT),
                    (line[len("Enchantments:") :], "white"),
                )
            )
        else:
            normal.append(Text(line, style=COLOR_MAGIC))
    return corrupted + enchant + normal


def _render_material_panel(
    item: ParsedItem,
    item_type: str,
    names_db,
) -> None:
    """Render a simple / material item as a compact coloured one-liner.

    Materials (gems, runes, potions, keys, scrolls, etc.) and any
    simple item that carries no magical properties are rendered as
    a single line rather than a full tooltip panel. The caller is
    responsible for deciding whether the item qualifies; this helper
    only does the rendering.

    Args:
        item: The parsed item to render.
        item_type: The item type string from ItemTypeDatabase
            (already resolved by the caller to avoid a duplicate
            lookup).
        names_db: The ItemNamesDatabase for base-name resolution.
            If not loaded, the raw item_code is printed instead.
    """
    from rich.text import Text

    base_name = names_db.get_base_item_name(item.item_code) if names_db.is_loaded() else None
    display = base_name or item.item_code
    clr = _simple_item_color(item.item_code, item_type)
    qty = item.quantity >> 1 if item.flags.simple else item.quantity
    if qty > 0:
        console.print(Text.assemble(("  ", ""), (display, clr), (" ", ""), (f"({qty})", "dim")))
    else:
        console.print(Text(f"  {display}", style=clr))


def _render_item_panel(
    item: ParsedItem,
    isc_db,
    skills_db,
    props_db,
    formatter,
    sets_db,
    names_db,
    equipped_set_counts: dict[str, int],
    children: list[ParsedItem] | None = None,
) -> None:
    """Render one item as a Rich panel in tooltip style.

    For runeword items: shows runeword name / base item + tier / rune letters /
    runeword properties.

    For socketed (gemmed) items: shows 'Gemmed <Base> [E]' and aggregates all
    child item properties into a single property list.

    Socket child items (location_id=6) are never rendered as standalone panels -
    they are aggregated into their parent panel via the `children` parameter.
    """
    from rich.text import Text

    if children is None:
        children = []

    # Material-like items: simple items OR extended items that are materials
    # (pliers, gem clusters, orbs, keys, shards, etc.)
    # Rendered as compact colored lines, not full panels.
    from d2rr_toolkit.game_data.item_types import get_item_type_db as _get_type_db

    _tdb = _get_type_db()
    _item_type = _tdb.get_item_type(item.item_code)
    _MATERIAL_TYPES = {"grab", "elix", "ques", "rpot", "wpot"}
    _is_material = (
        not item.extended
        or (_item_type in _MATERIAL_TYPES and not item.magical_properties)
        or (_item_type.startswith("gem") and not item.magical_properties)
    )

    if _is_material:
        _render_material_panel(item, _item_type, names_db)
        return

    quality_id = item.extended.quality
    # Title line colour - Crafted diverges from the tier indicator
    # (title=Magic-blue, subtype=Crafted-orange); get_title_color()
    # hides that special case.
    color = get_title_color(quality_id)
    ilvl = item.extended.item_level
    is_rw = item.flags.runeword
    is_gemmed = item.flags.socketed and children and not is_rw

    # ── Base item name + tier ────────────────────────────────────────────────
    base_name = (
        names_db.get_base_item_name(item.item_code) if names_db.is_loaded() else None
    ) or item.item_code
    tier = _tier_suffix(item.item_code)
    base_with_tier = f"{base_name}{tier}"

    # ── Build display name (title line) ────────────────────────────────────
    identified = item.flags.identified
    if is_rw:
        # Runeword: build_display_name handles recipe-based lookup (immune to
        # version drift) with fallback to runeword_id row-index lookup.
        rune_codes = [c.item_code for c in children] if children else None
        rw_name = None
        if names_db.is_loaded():
            rw_name = names_db.build_display_name(
                item.item_code,
                quality_id,
                runeword_id=item.runeword_id,
                is_runeword=True,
                rune_codes=rune_codes,
                identified=identified,
            )
        display_name = rw_name or base_with_tier
    elif is_gemmed:
        # Unique/Set items have proper names even when socketed - try name
        # lookup first; fall back to "Gemmed {base}" for other qualities.
        resolved_name = None
        if names_db.is_loaded() and quality_id in (5, 7):
            resolved_name = names_db.build_display_name(
                item.item_code,
                quality_id,
                unique_type_id=item.unique_type_id,
                set_item_id=item.set_item_id,
                identified=identified,
            )
        display_name = resolved_name or f"Gemmed {base_with_tier}"
    elif names_db.is_loaded():
        display_name = (
            names_db.build_display_name(
                item.item_code,
                quality_id,
                unique_type_id=item.unique_type_id,
                set_item_id=item.set_item_id,
                prefix_id=item.prefix_id,
                suffix_id=item.suffix_id,
                rare_name_id1=item.rare_name_id1,
                rare_name_id2=item.rare_name_id2,
                runeword_id=item.runeword_id,
                is_runeword=False,
                tier_suffix=tier,
                identified=identified,
            )
            or base_with_tier
        )
    else:
        display_name = item.item_code

    # ── Build panel content ─────────────────────────────────────────────────
    lines: list[Text] = []
    COLOR_RW_BASE = "#717171"  # grey for base item name on runewords

    # Line 1: item name + item level - in quality colour, bold.
    # Runewords always display in Unique-Gold regardless of base quality.
    # Normal (white) socketed items: grey to distinguish from non-socketed.
    # Normal (white) ethereal items: ethereal pink.
    COLOR_ETHEREAL = "#c487f3"
    if is_rw:
        title_color = COLOR_UNIQUE
    elif quality_id == 2 and item.flags.ethereal:
        title_color = COLOR_ETHEREAL
    elif quality_id == 2 and item.flags.socketed:
        title_color = "dim"
    else:
        title_color = color
    lines.append(Text(f"{display_name} ({ilvl})", style=f"bold {title_color}"))

    # Base item name on second line - for items whose display_name differs from the base.
    # This includes: Unique(7), Set(5), Rare(6), Crafted(8), Gemmed socketed items.
    # Also includes misc items (rings, amulets, jewels, charms) where the base type
    # helps identify the item (e.g. "Jewel", "Ring", "Amulet", "Small Charm").
    if not is_rw and quality_id in (5, 6, 7, 8):
        # Named items: always show base type below the display name.
        # The subtype always uses the tier-indicator colour (green/yellow/
        # gold/orange) - this is what distinguishes Crafted from Magic
        # visually, since the title itself is Magic-blue for crafted items.
        base_display = base_with_tier or item.item_code
        base_style = get_subtype_color(quality_id)
        lines.append(Text(base_display, style=base_style))
    elif is_gemmed and display_name != base_with_tier:
        lines.append(Text(base_with_tier, style=COLOR_RW_BASE))

    # For runeword: base item name (grey) + rune letters (gold, no spaces)
    if is_rw:
        lines.append(Text(base_with_tier, style=COLOR_RW_BASE))
        rune_parts = []
        for child in children:
            rune_parts.append(_rune_letter(child.item_code, names_db))
        if rune_parts:
            lines.append(Text(f"'{''.join(rune_parts)}'", style=COLOR_UNIQUE))

    # Flags line - Ethereal only. "Socketed (N)" is shown at end of stats list.
    if item.flags.ethereal:
        lines.append(Text("Ethereal", style="dim"))

    # ── Weapon Damage + Defense + Requirements (shared with GUI) ────────────
    from d2rr_toolkit.game_data.item_types import get_item_type_db
    from d2rr_toolkit.display import item_display

    type_db = get_item_type_db()
    item_category = type_db.classify(item.item_code)

    # Merge all properties FIRST - needed for correct damage/defense calculation
    all_props = item_display.merge_all_properties(item, children, type_db, isc_db)

    # Weapon damage lines
    for dmg in item_display.calculate_weapon_damage(item, all_props, type_db):
        if dmg.has_bonus:
            lines.append(
                Text.assemble(
                    (f"{dmg.label}: ", "white"),
                    (f"{dmg.final_min} to {dmg.final_max}", COLOR_MAGIC),
                )
            )
        else:
            lines.append(Text(f"{dmg.label}: {dmg.final_min} to {dmg.final_max}", style="white"))

    # Defense + Durability
    def_result = item_display.calculate_defense(item, all_props, type_db)
    if def_result is not None:
        if def_result.has_bonus:
            lines.append(
                Text.assemble(
                    ("Defense: ", "white"),
                    (str(def_result.final_defense), COLOR_MAGIC),
                )
            )
        else:
            lines.append(Text(f"Defense: {def_result.base_defense}", style="white"))
        lines.append(
            Text(
                f"Durability: {def_result.durability_current} of {def_result.durability_max}",
                style="white",
            )
        )
    elif item.armor_data:
        # Weapon durability (no defense line) - apply stat 73 max durability bonus
        dur_bonus = sum(p.get("value", 0) for p in all_props if p.get("stat_id") == 73)
        eff_max_dur = item.armor_data.durability.max_durability + dur_bonus
        lines.append(
            Text(
                f"Durability: {item.armor_data.durability.current_durability} of {eff_max_dur}",
                style="white",
            )
        )

    # Belt size (belts only)
    belt_slots = type_db.get_belt_slots(item.item_code)
    if belt_slots > 0:
        lines.append(Text(f"Belt Size: +{belt_slots} Slots", style="white"))

    # Requirements (Str, Dex, Level - with stat 91 reduction + level aggregation)
    reqs = item_display.calculate_requirements(
        item,
        children,
        type_db,
        names_db,
        isc_db,
        sets_db,
    )
    if reqs.dexterity > 0:
        lines.append(Text(f"Required Dexterity: {reqs.dexterity}", style="white"))
    if reqs.strength > 0:
        lines.append(Text(f"Required Strength: {reqs.strength}", style="white"))
    if reqs.level > 0:
        lines.append(Text(f"Required Level: {reqs.level}", style="white"))

    # Class restriction (e.g. "Sorceress Only")
    _CLASS_NAMES = {
        "ama": "Amazon",
        "sor": "Sorceress",
        "nec": "Necromancer",
        "pal": "Paladin",
        "bar": "Barbarian",
        "dru": "Druid",
        "ass": "Assassin",
        "war": "Warlock",
    }
    class_code = type_db.get_class_restriction(item.item_code)
    if class_code:
        class_name = _CLASS_NAMES.get(class_code, class_code)
        lines.append(Text(f"({class_name} Only)", style="white"))

    # ── Unidentified gate ───────────────────────────────────────────────────
    # In D2R, unidentified items show ONLY the base stats (damage/defense/
    # durability/requirements) plus a corrupted-red "Unidentified" line -
    # no magical properties, no set bonuses, no socket count (the socket
    # placeholders are visible in-game as the coloured gem slots, but the
    # textual tooltip doesn't list "Socketed (N)"). Finish the panel here.
    if not identified:
        lines.append(Text("Unidentified", style=f"bold {COLOR_CORRUPT}"))
        panel_content = Text("\n").join(lines)
        console.print(
            Panel(
                panel_content,
                border_style=color,
                padding=(0, 1),
            )
        )
        console.print()
        return

    # ── Properties section ──────────────────────────────────────────────────
    # all_props was already computed above via item_display.merge_all_properties()

    if is_rw:
        prop_lines = _format_properties(all_props, formatter, isc_db, skills_db)
        if prop_lines:
            lines.extend(_styled_prop_lines(prop_lines))
        else:
            lines.append(Text("  (runeword properties not available)", style="dim"))

        # "Socketed (N)" - always last property line
        socket_count = len(children)
        if socket_count > 0:
            lines.append(Text(f"Socketed ({socket_count})", style=COLOR_MAGIC))

    elif is_gemmed:
        # Use merged properties (all_props) which include gem/rune socket
        # bonuses from gems.txt - simple runes have empty magical_properties
        # so their bonuses would be missing if we only showed per-child props.
        gemmed_lines = _format_properties(all_props, formatter, isc_db, skills_db)
        lines.extend(_styled_prop_lines(gemmed_lines))

    else:
        own_lines = _format_properties(list(item.magical_properties), formatter, isc_db, skills_db)
        lines.extend(_styled_prop_lines(own_lines))

    # Automod display was removed: the rolled automod values are already
    # present in ``item.magical_properties`` (e.g. Shimmering's res-all
    # roll of +7 shows as the four elemental-resist entries at value 7).
    # The in-game tooltip shows only the rolled value, never the
    # theoretical "min-max" range, so rendering the range here produced
    # a duplicate line such as "+5-10% to All Resistances" right after
    # "+7% to All Resistances". The automagic.txt lookup lives on as a
    # utility (``format_code_range``) for future template-preview use
    # cases, but must not leak into live-item rendering.

    # ── "Socketed (N)" - at the end of the stats list for ALL socketed items ─
    if item.flags.socketed and not is_rw:
        total_sockets = item.total_nr_of_sockets
        if total_sockets > 0:
            lines.append(Text(f"Socketed ({total_sockets})", style=COLOR_MAGIC))
        else:
            lines.append(Text("Socketed", style=COLOR_MAGIC))

    # ── Set bonus display (quality=5 Set items) ─────────────────────────────
    if quality_id == 5 and item.set_item_id is not None and sets_db.is_loaded():
        result = sets_db.get_set_for_item(item.set_item_id)
        if result:
            set_def, item_def = result
            equipped_count = equipped_set_counts.get(item_def.set_name, 0)
            total = set_def.total_pieces()

            # Item-specific set bonuses (from setitems.txt aprop)
            item_bonus_lines: list[Text] = []
            for tier_bonus in item_def.tier_bonuses:
                req = tier_bonus.pieces_required
                is_active = equipped_count >= req
                style = COLOR_SET if is_active else f"dim {COLOR_SET}"
                for entry in tier_bonus.entries:
                    if entry.effective_value() == 0:
                        continue
                    display = entry.format(formatter, props_db, isc_db, skills_db)
                    if display:
                        item_bonus_lines.append(Text(f"{display} ({req} Items)", style=style))

            # Set-wide bonuses (from sets.txt PCode2-5 + FCode1-8)
            set_bonus_lines: list[Text] = []
            for tier in set_def.partial_tiers:
                req = tier.pieces_required
                is_active = equipped_count >= req
                style = COLOR_UNIQUE if is_active else f"dim {COLOR_UNIQUE}"
                for entry in tier.entries:
                    if entry.effective_value() == 0:
                        continue
                    display = entry.format(formatter, props_db, isc_db, skills_db)
                    if display:
                        set_bonus_lines.append(Text(f"{display} ({req} Items)", style=style))
            if set_def.full_tier:
                is_active = equipped_count >= total
                style = COLOR_UNIQUE if is_active else f"dim {COLOR_UNIQUE}"
                for entry in set_def.full_tier.entries:
                    if entry.effective_value() == 0:
                        continue
                    display = entry.format(formatter, props_db, isc_db, skills_db)
                    if display:
                        set_bonus_lines.append(Text(f"{display} (Full Set)", style=style))

            if item_bonus_lines:
                lines.append(Text("─" * 42, style="dim"))
                for t in item_bonus_lines:
                    lines.append(t)
            if set_bonus_lines:
                lines.append(Text("─" * 42, style="dim"))
                for t in set_bonus_lines:
                    lines.append(t)

            # Set member list - current item in Set-Green, others dark grey
            lines.append(Text("─" * 42, style="dim"))
            lines.append(Text(f"{set_def.name} ({equipped_count}/{total})", style=COLOR_UNIQUE))
            for member in set_def.member_names:
                if member == item_def.name:
                    member_style = COLOR_SET
                else:
                    member_style = "#555555"
                lines.append(Text(f"  {member}", style=member_style))

    # ── Print panel ─────────────────────────────────────────────────────────
    panel_content = Text("\n").join(lines)
    console.print(
        Panel(
            panel_content,
            border_style=color,
            padding=(0, 1),
        )
    )
    console.print()



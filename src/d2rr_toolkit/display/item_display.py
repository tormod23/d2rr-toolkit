"""Shared item display logic - business calculations for CLI and GUI.

This module contains PURE computation logic with NO UI formatting (no HTML,
no Rich/Text, no colors). Both CLI and GUI delegate all item display
calculations here, then apply their own formatting on top.

Extracted to eliminate ~450 lines of duplicated logic between cli.py and
gui/server.py that previously caused bugs when fixes were applied to only
one side (e.g. runeword merge, gem socket bonuses, func=5/6/7 handling).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from d2rr_toolkit.models.character import ParsedItem


# ─── Return Types ─────────────────────────────────────────────────────────────


@dataclass
class DamageLine:
    """One line of weapon damage display."""

    label: str  # "One-Hand Damage" / "Two-Hand Damage"
    final_min: int
    final_max: int
    has_bonus: bool  # True if ED% or flat damage modifies the base


@dataclass
class DefenseResult:
    """Computed defense value for armor items."""

    base_defense: int
    final_defense: int
    has_bonus: bool
    durability_current: int
    durability_max: int


@dataclass
class RequirementsResult:
    """Computed item requirements."""

    strength: int = 0  # 0 = don't display
    dexterity: int = 0  # 0 = don't display
    level: int = 0  # 0 or 1 = don't display


@dataclass
class SocketPosition:
    """Position of one socket overlay on an item sprite, in cell units."""

    x: float  # 0.0 = left edge, 0.5 = centered on 2-wide item
    y: float  # 0.0 = top edge


# ─── Socket Layout ────────────────────────────────────────────────────────────

# Lookup table: (inv_width, inv_height, num_sockets) -> row counts top-to-bottom.
#
# Each list defines the visual *layout* - how many sockets sit in each row,
# top to bottom. Odd counts per row are centered horizontally; the whole
# block is centered vertically inside the item bounds.
#
# This table is independent from _SOCKET_FILL_ORDER, which controls the
# *fill order* (which slot is "slot 1", "slot 2", ... when items are placed).
#
# Verification status (against real D2R Reimagined gameplay):
#   [BV]:
#     (2, 2, 3), (2, 2, 4), (2, 3, 4), (2, 3, 5), (2, 3, 6),
#     (2, 4, 4), (2, 4, 5), (2, 4, 6)
#   [LEGACY (probable, not freshly verified)]:
#     1*N items, 2*N items with 1-3 sockets, single-socket items
#     - these have only one sensible layout (vertical line or single point)
#     so the risk of error is minimal, but they remain unverified for now.
_SOCKET_ROW_COUNTS: dict[tuple[int, int, int], list[int]] = {
    # ── 1-wide items ────────────────────────────────────────────────────
    (1, 1, 1): [1],
    (1, 2, 1): [1],
    (1, 2, 2): [1, 1],
    (1, 3, 1): [1],
    (1, 3, 2): [1, 1],
    (1, 3, 3): [1, 1, 1],
    # ── 2x2 items (helmets, small shields) ──────────────────────────────
    (2, 2, 1): [1],
    (2, 2, 2): [1, 1],
    (2, 2, 3): [2, 1],  # [BV]  oo / o   (was [1,2] = wrong)
    (2, 2, 4): [2, 2],  # [BV]  oo / oo
    # ── 2x3 items (weapons, body armor, shields) ────────────────────────
    (2, 3, 1): [1],
    (2, 3, 2): [1, 1],
    (2, 3, 3): [1, 1, 1],
    (2, 3, 4): [2, 2],  # [BV] oo / oo (centered v)
    (2, 3, 5): [2, 1, 2],  # [BV] oo / o / oo
    (2, 3, 6): [2, 2, 2],  # [BV] oo / oo / oo
    # ── 2x4 items (two-handed weapons, polearms) ────────────────────────
    (2, 4, 1): [1],
    # 2x4 with 2 sockets uses the OUTER positions of the 3-socket layout
    # (y=0.5 + y=2.5, gap in the middle) - matches in-game appearance.
    # The empty middle row (count=0) advances the y-coordinate without
    # placing a socket, leaving the visible vertical gap. [BV]
    (2, 4, 2): [1, 0, 1],
    (2, 4, 3): [1, 1, 1],
    (2, 4, 4): [1, 1, 1, 1],  # [BV] o / o / o / o (vertical)
    (2, 4, 5): [2, 1, 2],  # [BV] oo / o / oo
    (2, 4, 6): [2, 2, 2],  # [BV] oo / oo / oo
}


# Lookup table: (inv_width, inv_height, num_sockets) -> permutation of the
# reading-order positions to match the in-game socket *fill order*.
#
# The base positions returned by the row-count layout are in reading order:
#   row 0 left-to-right, then row 1 left-to-right, etc.
# Some items use a different fill order (e.g. Z-pattern, column-major) that
# the GUI must respect so that runeword runes and gems land in the slots
# the player actually sees.
#
# Each entry is a permutation of length num_sockets:
#   _SOCKET_FILL_ORDER[(w, h, n)] = [a, b, c, ...]
# means "emit positions in order [reading_positions[a], reading_positions[b], ...]"
#
# Missing entries fall through to identity (= reading order). 1- and 2-socket
# layouts are trivially correct under reading order so they don't need entries.
#
# All entries below were verified against real D2R Reimagined items by
# placing gems sequentially or examining a known runeword.
# [BV]
_SOCKET_FILL_ORDER: dict[tuple[int, int, int], list[int]] = {
    # 4-socket items in Z-pattern -> TL, BR, BL, TR
    # Reading order is [TL, TR, BL, BR] = indices [0, 1, 2, 3]
    # Game order TL,BR,BL,TR maps to indices [0, 3, 2, 1]
    # NOTE: (2, 4, 4) is NOT in this group - it has 4 vertical sockets,
    # not a 2x2 cluster, so reading order is already correct.
    (2, 2, 4): [0, 3, 2, 1],
    (2, 3, 4): [0, 3, 2, 1],
    # 5-socket items: center first, then 4 corners in Z-pattern
    # -> MC, TL, BR, BL, TR
    # Reading order is [TL, TR, MC, BL, BR] = indices [0, 1, 2, 3, 4]
    # Game order MC,TL,BR,BL,TR maps to indices [2, 0, 4, 3, 1]
    (2, 3, 5): [2, 0, 4, 3, 1],
    (2, 4, 5): [2, 0, 4, 3, 1],
    # 6-socket items: column-major -> TL, CL, BL, TR, CR, BR
    # Reading order is [TL, TR, CL, CR, BL, BR] = indices [0, 1, 2, 3, 4, 5]
    # Game order TL,CL,BL,TR,CR,BR maps to indices [0, 2, 4, 1, 3, 5]
    (2, 3, 6): [0, 2, 4, 1, 3, 5],
    (2, 4, 6): [0, 2, 4, 1, 3, 5],
}


def get_socket_positions(
    inv_w: int,
    inv_h: int,
    num_sockets: int,
) -> list[SocketPosition]:
    """Return socket overlay positions for an item, in cell-unit coordinates.

    Positions are relative to the item's top-left corner. A value of 0.5
    means the socket is centered between two cells (e.g. single socket on
    a 2-wide item).

    The returned list is in **in-game fill order**: ``positions[i]`` is the
    on-screen location of the socket that the game considers "slot ``i+1``".
    For runeword items this matches the order of runes in the item's child
    list, so ``runes[0]`` always belongs in ``positions[0]``.

    Args:
        inv_w: Item width in grid cells.
        inv_h: Item height in grid cells.
        num_sockets: Number of sockets to place (0-6).

    Returns:
        List of SocketPosition, one per socket, in fill order.
        Empty list if the (w, h, n) combination is not in the layout table.
    """
    if num_sockets <= 0:
        return []

    row_counts = _SOCKET_ROW_COUNTS.get((inv_w, inv_h, num_sockets))
    if row_counts is None:
        return []

    rows = len(row_counts)
    y_offset = (inv_h - rows) / 2.0

    # Step 1: Build positions in reading order (top->bottom, left->right).
    reading_positions: list[SocketPosition] = []
    for row_idx, count in enumerate(row_counts):
        y = y_offset + row_idx
        x_offset = (inv_w - count) / 2.0
        for col in range(count):
            reading_positions.append(SocketPosition(x=x_offset + col, y=y))

    # Step 2: Apply fill-order permutation if one exists for this (w, h, n).
    # Without an entry, the fill order is the same as reading order, which
    # is correct for trivial cases (1 socket, vertical stacks).
    permutation = _SOCKET_FILL_ORDER.get((inv_w, inv_h, num_sockets))
    if permutation is None:
        return reading_positions

    # Defensive: only apply if the permutation length matches the number
    # of positions and is a valid permutation (0..n-1, no duplicates).
    # A malformed entry falls back to reading order so a typo can never
    # break the GUI rendering.
    if len(permutation) != len(reading_positions):
        return reading_positions
    if sorted(permutation) != list(range(len(reading_positions))):
        return reading_positions

    return [reading_positions[i] for i in permutation]


# ─── Tier & Name ──────────────────────────────────────────────────────────────


def get_tier_suffix(item_code: str, type_db) -> str:
    """Return the tier display suffix: ' [N]', ' [X]', or ' [E]'.

    Only armor and weapons have tiers. Returns '' for misc items.
    """
    from d2rr_toolkit.game_data.item_types import ItemCategory

    cat = type_db.classify(item_code)
    if cat not in (ItemCategory.ARMOR, ItemCategory.WEAPON):
        return ""
    tier = type_db.get_item_tier(item_code)
    return {"elite": " [E]", "exceptional": " [X]"}.get(tier, " [N]")


def get_rune_letter(rune_code: str, names_db) -> str:
    """Return the rune letter for a rune item code (e.g. 'r24' -> 'Ist').

    Strips ' Rune (...)' suffix and any trailing junk from strings.json.
    Falls back to the raw code if name is unavailable.
    """
    name = names_db.get_base_item_name(rune_code) if names_db.is_loaded() else None
    if name:
        name = name.split("\n")[0].strip()
        m = re.match(r"^(.+?)\s+Rune", name, re.IGNORECASE)
        if m:
            return m.group(1)
        return name
    return rune_code


def get_rune_formula(rune_codes: list[str], names_db) -> str:
    """Build the rune formula string (e.g. 'AmnRalMalIstOhm')."""
    return "".join(get_rune_letter(rc, names_db) for rc in rune_codes)


def is_material_item(item: ParsedItem, item_type: str) -> bool:
    """Check if an item is a material/gem/rune that uses special display rules."""
    if not item_type:
        return False
    return (
        item_type.startswith("rune")
        or item_type.startswith("gem")
        or item_type in ("misc", "quest")
        or item_type.startswith("ore")
        or item_type.startswith("ess")
        or item_type.startswith("key")
    ) and not item.magical_properties


# ─── Socket Children ──────────────────────────────────────────────────────────


def get_socket_child_codes(
    parent: ParsedItem,
    max_sockets: int,
) -> list[str] | None:
    """Extract rune/gem codes from a parent item's nested socket children.

    Children live in ``parent.socket_children`` since the hierarchical
    refactor - they are no longer interleaved with location_id=6 in the
    flat item list. Returns None if no children present.
    """
    codes = [child.item_code for child in parent.socket_children[:max_sockets]]
    return codes if codes else None


# ─── Runeword Property Merge ─────────────────────────────────────────────────

# Stat 387 = Reimagined display mirror (duplicate of stat 97). Hidden in output.
_RW_HIDDEN_STATS = frozenset({387})


def merge_runeword_properties(
    item: ParsedItem,
    children: list[ParsedItem] | None,
    type_db,
    isc_db,
) -> list[dict]:
    """Merge all property sources for a runeword item.

    Sources (in order):
    1. Base magical_properties (from item binary)
    2. runeword_properties (from item binary, second ISC block)
    3. Rune socket bonuses (computed from gems.txt for each child rune)

    Uses (stat_id, param) as merge key because stats like item_nonclassskill
    (97) use param to distinguish different skills.

    Handles special func codes for properties with empty stat_name:
    - func=5: flat min damage -> stat 21
    - func=6: flat max damage -> stat 22
    - func=7: enhanced damage% -> stat 17 + 18
    """
    merged: dict[tuple[int, int], dict] = {}

    def _merge_prop(p: dict) -> None:
        sid = p.get("stat_id")
        if sid is None or sid in _RW_HIDDEN_STATS:
            return
        key = (sid, p.get("param", 0))
        if key in merged:
            merged[key]["value"] = merged[key].get("value", 0) + p.get("value", 0)
        else:
            merged[key] = dict(p)

    for p in item.magical_properties or []:
        _merge_prop(p)
    for p in item.runeword_properties or []:
        _merge_prop(p)

    # Rune socket bonuses from gems.txt
    _merge_gem_socket_bonuses(item, children, type_db, isc_db, _merge_prop)

    return list(merged.values())


def _merge_gem_socket_bonuses(
    item: ParsedItem,
    children: list[ParsedItem] | None,
    type_db,
    isc_db,
    merge_fn,
) -> None:
    """Compute and merge gem/rune socket bonuses from gems.txt.

    For each socketed child rune/gem, looks up the gem definition in gems.txt,
    determines the appropriate slot type (weapon/helm/shield), and converts
    property codes to stat values via properties.txt.
    """
    from d2rr_toolkit.game_data.gems import get_gems_db
    from d2rr_toolkit.game_data.properties import get_properties_db
    from d2rr_toolkit.game_data.item_types import ItemCategory

    gems_db = get_gems_db()
    props_db = get_properties_db()
    if not gems_db.is_loaded() or not props_db.is_loaded() or not children:
        return

    if type_db.is_shield(item.item_code):
        slot_type = "shield"
    elif type_db.classify(item.item_code) == ItemCategory.WEAPON:
        slot_type = "weapon"
    else:
        slot_type = "helm"

    for child in children:
        gem_def = gems_db.get(child.item_code)
        if gem_def is None:
            continue
        for mod in gem_def.get_mods(slot_type):
            prop_def = props_db.get(mod.prop_code)
            if prop_def is None:
                continue
            for slot in prop_def.slots:
                if not slot.stat_name:
                    # Special func codes with empty stat_name
                    if slot.func == 5:
                        merge_fn({"stat_id": 21, "value": mod.min_val, "param": 0})
                    elif slot.func == 6:
                        merge_fn({"stat_id": 22, "value": mod.max_val, "param": 0})
                    elif slot.func == 7:
                        merge_fn({"stat_id": 17, "value": mod.min_val, "param": 0})
                        merge_fn({"stat_id": 18, "value": mod.min_val, "param": 0})
                    continue
                sd = isc_db.get_by_name(slot.stat_name)
                if sd is None:
                    continue
                if slot.func == 16:
                    val = mod.max_val
                elif slot.func == 17:
                    try:
                        val = int(mod.param) if mod.param else mod.min_val
                    except ValueError:
                        val = mod.min_val
                else:
                    val = mod.min_val
                merge_fn({"stat_id": sd.stat_id, "value": val, "param": 0})


# ─── Weapon Damage ────────────────────────────────────────────────────────────


def calculate_weapon_damage(
    item: ParsedItem,
    all_props: list[dict],
    type_db,
) -> list[DamageLine]:
    """Calculate final weapon damage lines including ED% and flat bonuses.

    D2R damage formula: final = floor(base * (1 + ED%/100)) + flat_damage

    Args:
        item: The weapon item.
        all_props: Merged property list (magical + runeword + gem bonuses).
        type_db: Item type database.

    Returns:
        List of DamageLine (0-2 entries: Two-Hand and/or One-Hand).
    """
    from d2rr_toolkit.game_data.item_types import ItemCategory

    if type_db.classify(item.item_code) != ItemCategory.WEAPON:
        return []

    mindam, maxdam, min2h, max2h, _speed = type_db.get_weapon_stats(item.item_code)

    # Ethereal weapons gain +50% base damage (applied before ED%)
    if item.flags.ethereal:
        mindam = math.floor(mindam * 1.5)
        maxdam = math.floor(maxdam * 1.5)
        min2h = math.floor(min2h * 1.5)
        max2h = math.floor(max2h * 1.5)

    # Collect ED% and flat damage from merged props
    weapon_ed_pct = sum(p.get("value", 0) for p in all_props if p.get("stat_id") == 17)
    # Flat damage: stat 21/22 = one-hand, stat 23/24 = two-hand (secondary)
    flat_1h_min = sum(p.get("value", 0) for p in all_props if p.get("stat_id") == 21)
    flat_1h_max = sum(p.get("value", 0) for p in all_props if p.get("stat_id") == 22)
    flat_2h_min = sum(p.get("value", 0) for p in all_props if p.get("stat_id") == 23)
    flat_2h_max = sum(p.get("value", 0) for p in all_props if p.get("stat_id") == 24)
    has_bonus = (
        weapon_ed_pct > 0
        or flat_1h_min > 0
        or flat_1h_max > 0
        or flat_2h_min > 0
        or flat_2h_max > 0
    )

    lines: list[DamageLine] = []
    candidates: list[tuple[str, int, int, int, int]] = []
    if min2h > 0 and mindam > 0:
        candidates.append(("Two-Hand Damage", min2h, max2h, flat_2h_min, flat_2h_max))
        candidates.append(("One-Hand Damage", mindam, maxdam, flat_1h_min, flat_1h_max))
    elif min2h > 0:
        candidates.append(("Two-Hand Damage", min2h, max2h, flat_2h_min, flat_2h_max))
    elif maxdam > 0:
        candidates.append(("One-Hand Damage", mindam, maxdam, flat_1h_min, flat_1h_max))

    for label, base_min, base_max, flat_min, flat_max in candidates:
        if weapon_ed_pct > 0:
            final_min = max(1, math.floor(base_min * (1 + weapon_ed_pct / 100))) + flat_min
            final_max = math.floor(base_max * (1 + weapon_ed_pct / 100)) + flat_max
        else:
            final_min = base_min + flat_min
            final_max = base_max + flat_max
        lines.append(DamageLine(label, final_min, final_max, has_bonus))

    return lines


# ─── Defense ──────────────────────────────────────────────────────────────────


def calculate_defense(
    item: ParsedItem,
    all_props: list[dict],
    type_db,
) -> DefenseResult | None:
    """Calculate final defense for armor items.

    D2R defense formula: final = floor(base * (1 + ED%/100)) + flat_defense

    Returns None for non-armor items or items without armor_data.
    """
    from d2rr_toolkit.game_data.item_types import ItemCategory

    if type_db.classify(item.item_code) != ItemCategory.ARMOR:
        return None
    if not item.armor_data:
        return None

    base_def = item.armor_data.defense_display
    ed_pct = sum(p.get("value", 0) for p in all_props if p.get("stat_id") == 16)
    flat_def = sum(p.get("value", 0) for p in all_props if p.get("stat_id") == 31)
    has_bonus = ed_pct > 0 or flat_def > 0

    if ed_pct > 0:
        final = math.floor(base_def * (1 + ed_pct / 100)) + flat_def
    else:
        final = base_def + flat_def

    # Stat 73 (maxdurability) adds flat bonus to max durability
    dur_bonus = sum(p.get("value", 0) for p in all_props if p.get("stat_id") == 73)
    effective_max_dur = item.armor_data.durability.max_durability + dur_bonus

    return DefenseResult(
        base_defense=base_def,
        final_defense=final,
        has_bonus=has_bonus,
        durability_current=item.armor_data.durability.current_durability,
        durability_max=effective_max_dur,
    )


# ─── Requirements ─────────────────────────────────────────────────────────────


def calculate_requirements(
    item: ParsedItem,
    children: list[ParsedItem] | None,
    type_db,
    names_db=None,
    isc_db=None,
    sets_db=None,
) -> RequirementsResult:
    """Calculate effective item requirements (Str, Dex, Level).

    Includes:
    - Base requirements from armor.txt/weapons.txt/misc.txt
    - Stat 91 (Requirements -%) from magical + runeword + set bonus properties
    - Level requirement aggregation: max of base, children, set, unique, affix
    """
    reqstr, reqdex, levelreq = type_db.get_requirements(item.item_code)
    quality_id = item.extended.quality if item.extended else 2

    # Apply Requirements Reduced % (stat 91)
    req_pct = 0
    for prop_list in (item.magical_properties, item.runeword_properties, item.set_bonus_properties):
        for p in prop_list or []:
            if p.get("stat_id") == 91:
                req_pct += p.get("value", 0)

    effective_dex = max(0, math.ceil(reqdex * (1 + req_pct / 100))) if reqdex > 0 else 0
    effective_str = max(0, math.ceil(reqstr * (1 + req_pct / 100))) if reqstr > 0 else 0

    # Ethereal items have their Strength (and for weapons Dexterity) reduced by 10
    if item.flags.ethereal:
        effective_str = max(0, effective_str - 10)
        effective_dex = max(0, effective_dex - 10)

    # Level requirement: max of all sources
    child_max_lvl = 0
    for child in children or []:
        _, _, child_lvl = type_db.get_requirements(child.item_code)
        child_max_lvl = max(child_max_lvl, child_lvl)

    set_lvl_req = 0
    if quality_id == 5 and item.set_item_id is not None and sets_db is not None:
        set_item_def = sets_db.get_set_item(item.set_item_id)
        if set_item_def:
            set_lvl_req = set_item_def.level_req

    unique_lvl_req = 0
    if quality_id == 7 and item.unique_type_id is not None and names_db is not None:
        unique_lvl_req = names_db.get_unique_lvl_req(item.unique_type_id)

    affix_lvl_req = 0
    if quality_id in (6, 8) and item.rare_affix_ids and names_db is not None:
        affix_lvl_req = names_db.get_affix_lvl_req(
            item.rare_affix_ids,
            item.rare_affix_slots or None,
        )
    if quality_id == 4 and names_db is not None:
        if item.prefix_id is not None and 0 <= item.prefix_id < len(names_db._prefix_lvl_reqs):
            affix_lvl_req = max(affix_lvl_req, names_db._prefix_lvl_reqs[item.prefix_id])
        if item.suffix_id is not None and 0 <= item.suffix_id < len(names_db._suffix_lvl_reqs):
            affix_lvl_req = max(affix_lvl_req, names_db._suffix_lvl_reqs[item.suffix_id])

    # Crafted-item required-level bonus
    # ---------------------------------
    # Empirically (FrozenOrbHydra: Ghoul/Grim/Doom/Dread Eye, ground truth
    # collected from the in-game tooltip 2026-04-14):
    #   required_level = max_affix_lvlreq + 10 + 3 * num_affixes
    # The +10 + 3n addends compensate for the recipe-mandated bonuses that
    # crafted items carry on top of their random affixes. The rule has
    # been verified across all 4 Grand Charms on FrozenOrbHydra; it is
    # specific to quality=8 (Crafted) and must NOT be applied to Rare
    # (quality=6) where the plain max_affix value already matches the
    # tooltip.
    crafted_bonus = 0
    if quality_id == 8 and item.rare_affix_ids:
        crafted_bonus = 10 + 3 * len(item.rare_affix_ids)

    effective_lvl = max(
        levelreq,
        child_max_lvl,
        set_lvl_req,
        unique_lvl_req,
        affix_lvl_req + crafted_bonus,
    )

    return RequirementsResult(
        strength=effective_str,
        dexterity=effective_dex,
        level=effective_lvl if effective_lvl > 1 else 0,
    )


# ─── Property Merging for All Items ──────────────────────────────────────────


def merge_all_properties(
    item: ParsedItem,
    children: list[ParsedItem] | None,
    type_db,
    isc_db,
) -> list[dict]:
    """Merge all properties for display - handles runeword vs non-runeword items.

    For runeword items: merges magical + runeword + gem socket bonuses with
    (stat_id, param) keying and stat 387 filtering.

    For non-runeword socketed items: concatenates magical_properties from
    parent + children, PLUS gem/rune socket bonuses from gems.txt. Simple
    rune/gem children have 0 magical_properties in their binary; their
    bonuses are defined in gems.txt and must be looked up explicitly.
    [BV]

    For non-socketed items: just the parent's magical_properties.
    """
    if item.flags.runeword:
        return merge_runeword_properties(item, children, type_db, isc_db)
    else:
        all_props = list(item.magical_properties or [])

        # Aggregate children's magical_properties by summing identical stats.
        # This collapses e.g. 3x Winter Facet into single lines:
        #   3x "100% Chance to cast level 37 Blizzard" -> "300% Chance..."
        #   3x "Adds 24-38 Cold Damage" -> "Adds 72-114 Cold Damage"
        if children:
            child_agg: dict[tuple, dict] = {}
            for child in children:
                for p in child.magical_properties or []:
                    sid = p.get("stat_id")
                    if sid is None:
                        continue
                    if "chance" in p:
                        # Encode 2 (skill-on-event): key by (stat_id, skill_id, level)
                        key = (sid, p.get("skill_id", 0), p.get("level", 0))
                        if key in child_agg:
                            child_agg[key]["chance"] += p["chance"]
                        else:
                            child_agg[key] = dict(p)
                    elif "charges" in p:
                        # Encode 3 (charged skill): never aggregate, each is unique
                        ukey = (sid, p.get("skill_id", 0), id(p))
                        child_agg[ukey] = dict(p)
                    else:
                        # Standard stat: key by (stat_id, param)
                        key = (sid, p.get("param", 0))
                        if key in child_agg:
                            child_agg[key]["value"] = child_agg[key].get("value", 0) + p.get(
                                "value", 0
                            )
                        else:
                            child_agg[key] = dict(p)
            all_props.extend(child_agg.values())
        # For socketed non-runeword items: also merge gem/rune bonuses from
        # gems.txt. This handles cases like 4x Vex in a Set armor that give
        # +20 Maximum Fire Resist - not encoded in the binary, only in gems.txt.
        # Bonuses from identical stats are summed (e.g. 4*Vex each giving +5
        # maxfireresist = one entry with +20).
        if item.flags.socketed and children:
            # Collect gem/rune bonuses from gems.txt, summing identical stats
            gem_merged: dict[tuple[int, int], dict] = {}

            def _merge_gem_prop(p: dict) -> None:
                sid = p.get("stat_id")
                if sid is None:
                    return
                key = (sid, p.get("param", 0))
                if key in gem_merged:
                    gem_merged[key]["value"] = gem_merged[key].get("value", 0) + p.get("value", 0)
                else:
                    gem_merged[key] = dict(p)

            _merge_gem_socket_bonuses(item, children, type_db, isc_db, _merge_gem_prop)

            # Merge gem bonuses INTO existing props (sum values for matching
            # stat_id+param keys) so that e.g. -26% fire resist from item
            # base + 30% from 3xBer = +4% in a single entry.
            existing_keys: dict[tuple[int, int], int] = {}
            for i, p in enumerate(all_props):
                sid = p.get("stat_id")
                if sid is not None:
                    key = (sid, p.get("param", 0))
                    existing_keys[key] = i

            for key, gem_prop in gem_merged.items():
                if key in existing_keys:
                    idx = existing_keys[key]
                    all_props[idx] = dict(all_props[idx])
                    all_props[idx]["value"] = all_props[idx].get("value", 0) + gem_prop.get(
                        "value", 0
                    )
                else:
                    all_props.append(gem_prop)

        # Include enchantment/corruption meta-stats from set_bonus_properties.
        # Set items store these in set_bonus_properties rather than magical_properties,
        # but they must appear in the tooltip alongside regular item stats.
        _META_STAT_IDS = {361, 362, 392, 393, 394, 395}
        for p in item.set_bonus_properties or []:
            if p.get("stat_id") in _META_STAT_IDS:
                all_props.append(p)

        return all_props

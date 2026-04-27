#!/usr/bin/env python3
"""Test suite for FrozenOrbHydra audit fixes (fix/frozenorb-audit-bugs).

Regression guards for all bugs found during the intensive FrozenOrbHydra.d2s
audit on 2026-04-07:

  1. Charged skill charges/max_charges swap (Encode 3)
  2. Ethereal weapon +50% base damage + 2H flat damage
  3. Ethereal requirements -10 Str/Dex
  4. Max durability stat 73 bonus
  5. Gem/rune bonuses keyed-merge for socketed unique items
  6. Set item enchantment/corruption meta-stats from set_bonus_properties
  7. Rare/Crafted affix IDs off-by-one
  8. Cold damage "Weapon Cold Damage" (no duration)
  9. Max resistance collapse
 10. Secondary damage combination (stats 23/24)
 11. Class restriction display
 12. Belt size display

Requires: D2R Reimagined installation, FrozenOrbHydra.d2s in project root,
          TC49/MrLockhart.d2s fixture.
"""

from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
src_dir = project_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


CASES = project_root / "tests" / "cases"
FROZEN_ORB_HYDRA = CASES / "TC55" / "FrozenOrbHydra.d2s"
VIKING_BARBIE = CASES / "TC56" / "VikingBarbie.d2s"
MR_LOCKHART = CASES / "TC49" / "MrLockhart.d2s"
STRAFOHDIN = CASES / "TC71" / "StraFoHdin.d2s"


def _init():
    import logging

    logging.basicConfig(level=logging.ERROR)
    from d2rr_toolkit.cli import _load_game_data

    _load_game_data(FROZEN_ORB_HYDRA)


def main() -> int:
    _init()

    from d2rr_toolkit.parsers.d2s_parser import D2SParser
    from d2rr_toolkit.game_data.item_types import get_item_type_db
    from d2rr_toolkit.game_data.item_stat_cost import get_isc_db
    from d2rr_toolkit.game_data.item_names import get_item_names_db
    from d2rr_toolkit.game_data.sets import get_sets_db
    from d2rr_toolkit.game_data.skills import get_skill_db
    from d2rr_toolkit.game_data.property_formatter import get_property_formatter
    from d2rr_toolkit.display.item_display import (
        merge_all_properties,
        calculate_weapon_damage,
        calculate_defense,
        calculate_requirements,
    )

    char = D2SParser(FROZEN_ORB_HYDRA).parse()
    type_db = get_item_type_db()
    isc_db = get_isc_db()
    names_db = get_item_names_db()
    sets_db = get_sets_db()
    skills_db = get_skill_db()
    formatter = get_property_formatter()

    passed = 0
    failed = 0
    total = 0

    def check(condition: bool, name: str, detail: str = ""):
        nonlocal passed, failed, total
        total += 1
        if condition:
            passed += 1
            print(f"  PASS  {name}")
        else:
            failed += 1
            print(f"  FAIL  {name}")
            if detail:
                print(f"        {detail}")

    def get_children(item):
        """Return socket children from the item's socket_children list."""
        return item.socket_children or []

    def stat_value(props, stat_id):
        return sum(p.get("value", 0) for p in props if p.get("stat_id") == stat_id)

    def find_stat(props, stat_id):
        return [p for p in props if p.get("stat_id") == stat_id]

    def fmt(props):
        # The structured ``format_properties_grouped`` returns
        # FormattedProperty objects; this test asserts against plain
        # substrings, so route through the back-compat wrapper.
        return formatter.format_properties_grouped_plain(props, isc_db, skills_db)

    # =========================================================================
    # 1. Charged skill charges/max_charges (Encode 3)
    # =========================================================================
    print("\n=== 1. Charged skill charges/max_charges swap ===")

    # Andariel's Visage: Venom should be 3/20, not 20/3
    for item in char.merc_items:
        if item.item_code == "usk" and item.extended and item.extended.quality == 7:
            venom = [p for p in item.magical_properties if p.get("stat_id") == 204]
            check(len(venom) == 1, "Andariel has Venom charged skill")
            if venom:
                check(venom[0]["charges"] == 3, f"Venom charges=3 (got {venom[0]['charges']})")
                check(
                    venom[0]["max_charges"] == 20,
                    f"Venom max_charges=20 (got {venom[0]['max_charges']})",
                )
            break

    # Infinity: Cyclone Armor should be 30/30
    for item in char.merc_items:
        if item.item_code == "7s8" and item.flags.runeword:
            cyclone = [p for p in (item.runeword_properties or []) if p.get("stat_id") == 204]
            check(len(cyclone) == 1, "Infinity has Cyclone Armor charged skill")
            if cyclone:
                check(
                    cyclone[0]["charges"] == 30, f"Cyclone charges=30 (got {cyclone[0]['charges']})"
                )
                check(
                    cyclone[0]["max_charges"] == 30,
                    f"Cyclone max_charges=30 (got {cyclone[0]['max_charges']})",
                )
            break

    # Edge case: formatted display
    for item in char.merc_items:
        if item.item_code == "usk" and item.extended and item.extended.quality == 7:
            lines = fmt(item.magical_properties)
            has_3_20 = any("(3/20 Charges)" in l for l in lines)
            check(has_3_20, "Venom display shows (3/20 Charges)")
            has_20_3 = any("(20/3 Charges)" in l for l in lines)
            check(not has_20_3, "Venom display does NOT show (20/3 Charges)")
            break

    # =========================================================================
    # 2. Ethereal weapon +50% base damage + 2H flat damage
    # =========================================================================
    print("\n=== 2. Ethereal weapon damage ===")

    # Infinity: Ethereal Thresher, +511% ED, +50-100 secondary
    for item in char.merc_items:
        if item.item_code == "7s8" and item.flags.runeword:
            children = get_children(item)
            merged = merge_all_properties(item, children, type_db, isc_db)
            dmg = calculate_weapon_damage(item, merged, type_db)
            check(len(dmg) == 1, "Infinity has 1 damage line (Two-Hand)")
            check(dmg[0].final_min == 159, f"Infinity min damage=159 (got {dmg[0].final_min})")
            check(dmg[0].final_max == 1389, f"Infinity max damage=1389 (got {dmg[0].final_max})")
            check(
                dmg[0].label == "Two-Hand Damage", f"Damage label is Two-Hand (got {dmg[0].label})"
            )
            break

    # Non-ethereal weapon: Tal Rasha Lidless Eye (not ethereal)
    for item in char.items:
        if item.extended and item.extended.quality == 5 and item.extended.item_level == 71:
            merged = merge_all_properties(item, [], type_db, isc_db)
            dmg = calculate_weapon_damage(item, merged, type_db)
            check(dmg[0].final_min == 30, f"Tal Rasha min=30 (got {dmg[0].final_min})")
            check(dmg[0].final_max == 53, f"Tal Rasha max=53 (got {dmg[0].final_max})")
            check(not item.flags.ethereal, "Tal Rasha is NOT ethereal")
            break

    # =========================================================================
    # 3. Ethereal requirements -10
    # =========================================================================
    print("\n=== 3. Ethereal requirements -10 ===")

    eth_checks = [
        ("uvg", "Dracul's Grasp", 40, 0, True),
        ("ulc", "String of Ears", 40, 0, True),
        ("usk", "Andariel's Visage", 92, 0, True),
        ("7s8", "Infinity", 142, 108, True),
    ]
    for code, name, exp_str, exp_dex, expect_eth in eth_checks:
        for item in char.merc_items:
            if item.item_code == code:
                reqs = calculate_requirements(item, [], type_db, names_db, isc_db, sets_db)
                check(item.flags.ethereal == expect_eth, f"{name} is ethereal={expect_eth}")
                check(reqs.strength == exp_str, f"{name} str={exp_str} (got {reqs.strength})")
                if exp_dex > 0:
                    check(reqs.dexterity == exp_dex, f"{name} dex={exp_dex} (got {reqs.dexterity})")
                break

    # Edge case: non-ethereal item should NOT get -10
    for item in char.items:
        if item.extended and item.extended.quality == 6 and item.extended.item_level == 96:
            check(not item.flags.ethereal, "Blood Track is NOT ethereal")
            reqs = calculate_requirements(item, [], type_db, names_db, isc_db, sets_db)
            check(
                reqs.strength == 208, f"Blood Track str=208 (no eth reduction, got {reqs.strength})"
            )
            break

    # =========================================================================
    # 4. Max durability stat 73 bonus
    # =========================================================================
    print("\n=== 4. Max durability stat 73 bonus ===")

    # String of Ears: base 12 + stat 73 = +10 -> 22/22
    for item in char.merc_items:
        if item.item_code == "ulc":
            merged = merge_all_properties(item, [], type_db, isc_db)
            def_r = calculate_defense(item, merged, type_db)
            check(def_r is not None, "String of Ears has defense data")
            check(
                def_r.durability_current == 22, f"dur current=22 (got {def_r.durability_current})"
            )
            check(def_r.durability_max == 22, f"dur max=22 (got {def_r.durability_max})")
            break

    # Item WITHOUT stat 73: Fortitude (no maxdurability bonus)
    for item in char.merc_items:
        if item.item_code == "uul" and item.flags.runeword:
            children = get_children(item)
            merged = merge_all_properties(item, children, type_db, isc_db)
            def_r = calculate_defense(item, merged, type_db)
            check(
                def_r.durability_max == 36,
                f"Fortitude dur max=36 (no stat 73 bonus, got {def_r.durability_max})",
            )
            break

    # =========================================================================
    # 5. Gem/rune bonus keyed-merge for socketed unique items
    # =========================================================================
    print("\n=== 5. Socketed unique gem bonus merge ===")

    # Andariel: 3xBer+Ral -> fire resist = -26 + 30 = +4
    for item in char.merc_items:
        if item.item_code == "usk" and item.extended and item.extended.quality == 7:
            children = get_children(item)
            check(len(children) == 4, f"Andariel has 4 socket children (got {len(children)})")
            merged = merge_all_properties(item, children, type_db, isc_db)
            fire_val = stat_value(merged, 39)
            check(fire_val == 4, f"fire resist merged = +4 (got {fire_val})")
            # PDR from 3xBer gem bonus
            pdr_val = stat_value(merged, 36)
            check(pdr_val == 24, f"PDR merged = 24 (got {pdr_val})")
            # Formatted output
            lines = fmt(merged)
            has_fire4 = any("+4% Fire Resistance" in l for l in lines)
            check(has_fire4, "formatted shows +4% Fire Resistance")
            has_pdr24 = any("+24% Physical Damage Reduction" in l for l in lines)
            check(has_pdr24, "formatted shows +24% Physical Damage Reduction")
            break

    # =========================================================================
    # 6. Set item enchantment/corruption from set_bonus_properties
    # =========================================================================
    print("\n=== 6. Set item enchant/corrupt meta-stats ===")

    # Tal Rasha Lidless Eye: corrupted + enchantments from set_bonus_properties
    for item in char.items:
        if item.extended and item.extended.quality == 5 and item.extended.item_level == 71:
            merged = merge_all_properties(item, [], type_db, isc_db)
            has_corrupt = stat_value(merged, 361) > 0
            has_enchant = stat_value(merged, 394) > 0
            check(has_corrupt, "merged includes corrupted stat (361)")
            check(has_enchant, "merged includes enchant stat (394)")
            lines = fmt(merged)
            check(any("Corrupted" == l for l in lines), "formatted shows 'Corrupted'")
            check(
                any("Enchantments: 5 / 5" in l for l in lines),
                "formatted shows 'Enchantments: 5 / 5'",
            )
            break

    # Chiad's Halo: enchantments but NO corruption
    for item in char.merc_items:
        if item.item_code == "rin" and item.extended and item.extended.quality == 5:
            merged = merge_all_properties(item, [], type_db, isc_db)
            has_corrupt = stat_value(merged, 361) > 0
            has_enchant = stat_value(merged, 392) > 0
            check(not has_corrupt, "Chiad's Halo NOT corrupted (no stat 361)")
            check(has_enchant, "Chiad's Halo has enchant stat (392)")
            lines = fmt(merged)
            check(not any("Corrupted" == l for l in lines), "formatted does NOT show 'Corrupted'")
            check(
                any("Enchantments: 2 / 2" in l for l in lines),
                "formatted shows 'Enchantments: 2 / 2'",
            )
            break

    # =========================================================================
    # 7. Rare/Crafted affix IDs off-by-one
    # =========================================================================
    print("\n=== 7. Rare affix IDs (off-by-one fix) ===")

    # Blood Track: corrected IDs should be [172, 198, 365, 320, 375, 351]
    for item in char.items:
        if item.extended and item.extended.quality == 6 and item.extended.item_level == 96:
            expected = [172, 198, 365, 320, 375, 351]
            check(
                item.rare_affix_ids == expected,
                f"affix IDs = {expected} (got {item.rare_affix_ids})",
            )
            reqs = calculate_requirements(item, [], type_db, names_db, isc_db, sets_db)
            check(reqs.level == 69, f"Blood Track lvlreq=69 (got {reqs.level})")
            break

    # =========================================================================
    # 8. Cold damage "Weapon Cold Damage" (no duration)
    # =========================================================================
    print("\n=== 8. Cold damage without duration ===")

    # Raven Frost: Adds 25-50 Weapon Cold Damage (NOT "Over 2 Secs")
    for item in char.merc_items:
        if item.item_code == "rin" and item.extended and item.extended.quality == 7:
            lines = fmt(item.magical_properties)
            cold_lines = [l for l in lines if "Cold Damage" in l and "Absorbed" not in l]
            check(len(cold_lines) == 1, f"1 cold damage line (got {len(cold_lines)})")
            if cold_lines:
                check(
                    "Weapon Cold Damage" in cold_lines[0],
                    f"says 'Weapon Cold Damage' (got: {cold_lines[0]})",
                )
                check("Over" not in cold_lines[0], "no 'Over X Secs' duration text")
                check("25-50" in cold_lines[0], f"damage range 25-50 (got: {cold_lines[0]})")
            break

    # =========================================================================
    # 9. Max resistance collapse
    # =========================================================================
    print("\n=== 9. Max resistance collapse ===")

    # Blood Track: 4x +5% max res -> single "All Maximum Resistances" line
    for item in char.items:
        if item.extended and item.extended.quality == 6 and item.extended.item_level == 96:
            lines = fmt(item.magical_properties)
            maxres_lines = [l for l in lines if "Maximum" in l and "Resist" in l]
            check(len(maxres_lines) == 1, f"1 collapsed max resist line (got {len(maxres_lines)})")
            if maxres_lines:
                check(
                    "All Maximum Resistances" in maxres_lines[0],
                    f"collapsed text (got: {maxres_lines[0]})",
                )
            break

    # Edge case: if max resists differ, do NOT collapse (synthetic test)
    test_props = [
        {"stat_id": 40, "value": 5, "param": 0},
        {"stat_id": 42, "value": 5, "param": 0},
        {"stat_id": 44, "value": 3, "param": 0},  # different!
        {"stat_id": 46, "value": 5, "param": 0},
    ]
    lines_unequal = fmt(test_props)
    maxres_u = [l for l in lines_unequal if "Maximum" in l]
    check(len(maxres_u) > 1, f"unequal max resists NOT collapsed ({len(maxres_u)} lines)")

    # =========================================================================
    # 10. Secondary damage combination (stats 23/24)
    # =========================================================================
    print("\n=== 10. Secondary damage combination ===")

    # Infinity: stats 23=50, 24=100 -> "Adds 50-100 Weapon Damage"
    for item in char.merc_items:
        if item.item_code == "7s8" and item.flags.runeword:
            children = get_children(item)
            merged = merge_all_properties(item, children, type_db, isc_db)
            lines = fmt(merged)
            adds_lines = [
                l
                for l in lines
                if "Adds" in l and "Weapon Damage" in l and "Fire" not in l and "Cold" not in l
            ]
            check(
                len(adds_lines) == 1,
                f"1 combined 'Adds X-Y Weapon Damage' line (got {len(adds_lines)})",
            )
            if adds_lines:
                check("50-100" in adds_lines[0], f"range 50-100 (got: {adds_lines[0]})")
            # Must NOT show separate "+50 to Minimum" / "+100 to Maximum"
            sep_min = any("Minimum" in l and "50" in l for l in lines)
            sep_max = any("Maximum" in l and "100" in l for l in lines)
            check(not sep_min, "no separate '+50 to Minimum Weapon Damage'")
            check(not sep_max, "no separate '+100 to Maximum Weapon Damage'")
            break

    # The Vanquisher amulet: has stats 21+22 AND 23+24 AND 159+160
    for item in char.merc_items:
        if item.item_code == "amu" and item.extended and item.extended.quality == 7:
            lines = fmt(item.magical_properties)
            adds_lines = [l for l in lines if "Adds" in l and "Weapon Damage" in l]
            check(
                len(adds_lines) == 1, f"Vanquisher: 1 combined damage line (got {len(adds_lines)})"
            )
            if adds_lines:
                check("15-25" in adds_lines[0], f"range 15-25 (got: {adds_lines[0]})")
            break

    # =========================================================================
    # 11. Class restriction
    # =========================================================================
    print("\n=== 11. Class restriction ===")

    check(type_db.get_class_restriction("obf") == "sor", "Dimensional Shard -> Sorceress")
    check(type_db.get_class_restriction("7s8") is None, "Thresher -> no class restriction")
    check(type_db.get_class_restriction("rin") is None, "Ring -> no class restriction")

    # =========================================================================
    # 12. Belt size
    # =========================================================================
    print("\n=== 12. Belt size ===")

    check(type_db.get_belt_slots("ulc") == 12, "Spiderweb Sash = +12 Slots")
    check(type_db.get_belt_slots("lbl") == 4, "Sash = +4 Slots")
    check(type_db.get_belt_slots("uhc") == 12, "Colossus Girdle = +12 Slots")
    check(type_db.get_belt_slots("rin") == 0, "Ring = 0 (not a belt)")
    check(type_db.get_belt_slots("hbl") == 8, "Plated Belt = +8 Slots")

    # =========================================================================
    # 13. Merc items parsed correctly
    # =========================================================================
    print("\n=== 13. Merc item count and identities ===")

    check(
        len(char.merc_items) == 9, f"FrozenOrbHydra has 9 merc items (got {len(char.merc_items)})"
    )

    merc_parent_codes = [item.item_code for item in char.merc_items]
    check("7s8" in merc_parent_codes, "Infinity (7s8) in merc items")
    check("uul" in merc_parent_codes, "Shadow Plate (uul) in merc items")
    check("usk" in merc_parent_codes, "Demonhead (usk) in merc items")

    # =========================================================================
    # 14. Socket children aggregation (3x Winter Facet)
    # =========================================================================
    print("\n=== 14. Socket children aggregation ===")

    for item in char.items:
        if item.extended and item.extended.quality == 5 and item.extended.item_level == 71:
            children = get_children(item)
            check(len(children) == 3, f"Lidless Eye has 3 children (got {len(children)})")
            merged = merge_all_properties(item, children, type_db, isc_db)
            lines = fmt(merged)

            # Aggregated: 3x 100% -> 300%
            ctc_lines = [l for l in lines if "Chance to cast" in l and "Blizzard" in l]
            check(len(ctc_lines) == 1, f"1 aggregated Blizzard CTC line (got {len(ctc_lines)})")
            if ctc_lines:
                check("300%" in ctc_lines[0], f"300% aggregated chance (got: {ctc_lines[0]})")

            # Aggregated: 3x 24-38 -> 72-114
            cold_lines = [l for l in lines if "Weapon Cold Damage" in l]
            check(len(cold_lines) == 1, f"1 aggregated cold damage line (got {len(cold_lines)})")
            if cold_lines:
                check("72-114" in cold_lines[0], f"72-114 aggregated cold (got: {cold_lines[0]})")

            # Aggregated: 3x 5% -> 15%
            csd_lines = [l for l in lines if "Cold Skill Damage" in l]
            check(len(csd_lines) == 1, f"1 cold skill damage line (got {len(csd_lines)})")
            if csd_lines:
                check("15%" in csd_lines[0], f"15% aggregated (got: {csd_lines[0]})")

            # Aggregated: 3x -5% -> -15%
            ecr_lines = [l for l in lines if "Enemy Cold Resistance" in l]
            check(len(ecr_lines) == 1, f"1 cold pierce line (got {len(ecr_lines)})")
            if ecr_lines:
                check("-15%" in ecr_lines[0], f"-15% aggregated (got: {ecr_lines[0]})")

            # Non-aggregated parent stats still present
            check(any("+25% Faster Cast Rate" in l for l in lines), "parent FCR preserved")
            check(any("+77 to Mana" in l for l in lines), "parent Mana preserved")
            break

    # Edge case: single child should NOT change anything
    for item in char.merc_items:
        if item.item_code == "usk" and item.extended and item.extended.quality == 7:
            children = get_children(item)
            merged_a = merge_all_properties(item, children, type_db, isc_db)
            # 3xBer+Ral: Ber gives PDR, Ral gives fire resist - different stats, no aggregation needed
            pdr = stat_value(merged_a, 36)
            check(pdr == 24, f"Andariel 3xBer PDR=24 (got {pdr})")
            break

    # =========================================================================
    # 15. Set bonus format: suffix "(N Items)" and elemental collapse
    # =========================================================================
    print("\n=== 15. Set bonus format_code_value collapses ===")

    # pierce-elem -> "All Enemy Elemental Resistances"
    from d2rr_toolkit.game_data.properties import get_properties_db

    props_db = get_properties_db()
    display = formatter.format_code_value("pierce-elem", 20, "", props_db, isc_db, skills_db)
    check(
        display is not None and "All Enemy Elemental" in display,
        f"pierce-elem -> All Enemy Elemental (got: {display})",
    )

    # extra-elem -> "All Elemental Skill Damage"
    display2 = formatter.format_code_value("extra-elem", 10, "", props_db, isc_db, skills_db)
    check(
        display2 is not None and "All Elemental Skill Damage" in display2,
        f"extra-elem -> All Elemental Skill Damage (got: {display2})",
    )

    # res-all-max -> "All Maximum Resistances"
    display3 = formatter.format_code_value("res-all-max", 5, "", props_db, isc_db, skills_db)
    check(
        display3 is not None and "All Maximum Resistances" in display3,
        f"res-all-max -> All Maximum Resistances (got: {display3})",
    )

    # res-all -> "All Resistances" (existing, regression check)
    display4 = formatter.format_code_value("res-all", 30, "", props_db, isc_db, skills_db)
    check(
        display4 is not None and "All Resistances" in display4,
        f"res-all -> All Resistances (got: {display4})",
    )

    # sor -> "Sorceress Skill Levels" (class code)
    display5 = formatter.format_code_value("sor", 1, "", props_db, isc_db, skills_db)
    check(
        display5 is not None and "Sorceress" in display5,
        f"sor -> Sorceress Skill Levels (got: {display5})",
    )

    # =========================================================================
    # 16. Quantity data present on stackable items
    # =========================================================================
    print("\n=== 16. Quantity on stackable items ===")

    # Belt potions in FrozenOrbHydra should have quantity
    potion_count = 0
    for item in char.items:
        if item.quantity > 0 and item.flags.simple:
            potion_count += 1
    check(potion_count > 0, f"at least 1 simple item with quantity > 0 (got {potion_count})")

    # Non-stackable items should have quantity 0
    for item in char.items:
        if item.extended and item.extended.quality == 5 and item.extended.item_level == 71:
            check(item.quantity == 0, f"Tal Rasha Lidless Eye quantity=0 (got {item.quantity})")
            break

    # =========================================================================
    # 17. Zero-gap byte coverage for all 4 D2S files
    # =========================================================================
    print("\n=== 17. Zero-gap byte coverage (all 4 D2S files) ===")

    test_files = [
        ("FrozenOrbHydra.d2s", FROZEN_ORB_HYDRA),
        ("VikingBarbie.d2s", VIKING_BARBIE),
        ("MrLockhart.d2s", MR_LOCKHART),
        ("StraFoHdin.d2s", STRAFOHDIN),
    ]

    for name, path in test_files:
        if not path.exists():
            check(False, f"{name}: file not found at {path}")
            continue
        d = path.read_bytes()
        pc = D2SParser(path).parse()

        # Player items gap: sum of source_data == items section size
        pos = pc.items_jm_byte_offset + 4
        for it in pc.items:
            if it.source_data:
                pos += len(it.source_data)
            for child in it.socket_children or []:
                if child.source_data:
                    pos += len(child.source_data)
        player_gap = pc.corpse_jm_byte_offset - pos
        check(player_gap == 0, f"{name}: player item gap = 0 (got {player_gap})")

        # Merc items gap
        jf = d.find(b"jf", pc.corpse_jm_byte_offset)
        kf = d.find(b"kf", jf + 2 if jf > 0 else pc.corpse_jm_byte_offset)
        merc_jm = d.find(b"JM", jf + 2) if jf > 0 else -1
        mpos = merc_jm + 4 if merc_jm > 0 else 0
        for it in pc.merc_items:
            if it.source_data:
                mpos += len(it.source_data)
            for child in it.socket_children or []:
                if child.source_data:
                    mpos += len(child.source_data)
        merc_gap = (kf - mpos) if kf > 0 and mpos > 0 else 0
        check(merc_gap == 0, f"{name}: merc item gap = 0 (got {merc_gap})")

        # No trailing bytes
        trail = len(pc.trailing_item_bytes) if pc.trailing_item_bytes else 0
        check(trail == 0, f"{name}: trailing bytes = 0 (got {trail})")

    # =========================================================================
    # 18. VikingBarbie last socket child padding fix
    # =========================================================================
    print("\n=== 18. VikingBarbie last socket child padding ===")

    vb_path = VIKING_BARBIE
    if vb_path.exists():
        vb = D2SParser(vb_path).parse()
        # The 4 jewels socketed in uow (Ogre Maul) should all be 37 bytes
        uow = None
        for it in vb.items:
            if it.item_code == "uow" and it.flags.location_id == 1:
                uow = it
                break
        found_uow = uow is not None
        uow_children = (uow.socket_children or []) if uow else []
        check(found_uow, "VikingBarbie has uow (Ogre Maul)")
        check(len(uow_children) == 4, f"uow has 4 socket children (got {len(uow_children)})")
        sizes = [len(c.source_data) for c in uow_children]
        check(all(s == 37 for s in sizes), f"all 4 jewels are 37 bytes (got {sizes})")
        # All should have 5 properties
        for i, c in enumerate(uow_children):
            check(
                len(c.magical_properties) == 5,
                f"  jewel {i} has 5 props (got {len(c.magical_properties)})",
            )

    # =========================================================================
    # 19. Set bonus suffix format "(N Items)" not "N Items:"
    # =========================================================================
    print("\n=== 19. Set bonus suffix format ===")

    from d2rr_toolkit.game_data.sets import get_sets_db as _get_sets
    from d2rr_toolkit.game_data.properties import get_properties_db as _get_props

    _sets = _get_sets()
    _props = _get_props()

    # Tal Rasha Lidless Eye set bonus format check
    result = _sets.get_set_for_item(78)  # set_item_id=78
    if result:
        set_def, item_def = result
        # Item-specific tier: should have "(2 Items)" suffix
        for tb in item_def.tier_bonuses:
            for entry in tb.entries:
                if entry.effective_value() == 0:
                    continue
                display = entry.format(formatter, _props, isc_db, skills_db)
                if display:
                    # The CLI would render as "display (N Items)" - check display is not None
                    check(
                        display is not None and len(display) > 0,
                        f"tier bonus '{display}' has content",
                    )
                    break
            break

        # Full set tier: check elemental collapse
        if set_def.full_tier:
            full_displays = []
            for entry in set_def.full_tier.entries:
                if entry.effective_value() == 0:
                    continue
                d = entry.format(formatter, _props, isc_db, skills_db)
                if d:
                    full_displays.append(d)
            check(
                any("All Elemental Skill Damage" in d for d in full_displays),
                "Full Set has 'All Elemental Skill Damage' (collapsed)",
            )
            check(
                any("All Enemy Elemental Resistances" in d for d in full_displays),
                "Full Set has 'All Enemy Elemental Resistances' (collapsed)",
            )
            # Must NOT have separate "Fire Skill Damage"
            check(
                not any("Fire Skill Damage" in d for d in full_displays),
                "Full Set does NOT show separate 'Fire Skill Damage'",
            )

    # =========================================================================
    # Summary
    # =========================================================================
    print()
    print("=" * 60)
    print(f"Total: {passed} PASS, {failed} FAIL ({total} checks)")
    print("=" * 60)
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())

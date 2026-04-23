#!/usr/bin/env python3
"""Test suite for D2S parser trailing item bytes preservation and
Superior runeword / shield parsing fixes.

Covers:
- VikingBarbie: now parses ALL items (113 root player + 9 root merc), 0 trailing bytes
- VikingBarbie: all 12 equipped slots populated (including weapon switch)
- VikingBarbie: Spirit Monarch (Superior RW) single-list format
- VikingBarbie: unmodified round-trip byte-identical
- MrLockhart: clean parse, no trailing bytes, append_item works
- TestSorc: Superior Monarchs with correct ED% + MaxDur% stats

Requires: TC56/VikingBarbie.d2s, TC56/TestSorc.d2s, TC49/MrLockhart.d2s.
"""

from __future__ import annotations

import copy
import sys
import tempfile
from pathlib import Path

project_root = Path(__file__).parent.parent
src_dir = project_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


def _init():
    import logging

    logging.basicConfig(level=logging.ERROR)
    from d2rr_toolkit.cli import _load_game_data

    _load_game_data(project_root / "tests" / "cases" / "TC49" / "MrLockhart.d2s")


def main() -> int:
    _init()

    from d2rr_toolkit.parsers.d2s_parser import D2SParser
    from d2rr_toolkit.writers.d2s_writer import D2SWriter
    from d2rr_toolkit.writers.item_utils import patch_item_position
    from d2rr_toolkit.game_data.item_stat_cost import get_isc_db

    isc = get_isc_db()

    viking_path = project_root / "tests" / "cases" / "TC56" / "VikingBarbie.d2s"
    mr_path = project_root / "tests" / "cases" / "TC49" / "MrLockhart.d2s"
    test_sorc_path = project_root / "tests" / "cases" / "TC56" / "TestSorc.d2s"

    viking_source = viking_path.read_bytes()
    viking_char = D2SParser(viking_path).parse()

    mr_source = mr_path.read_bytes()
    mr_char = D2SParser(mr_path).parse()

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
            detail_str = f" -- {detail}" if detail else ""
            print(f"  FAIL  {name}{detail_str}")

    # ----------------------------------------------------------------
    # 1. VikingBarbie: full parse (no trailing bytes)
    # ----------------------------------------------------------------
    print("\n--- VikingBarbie: full parse ---")

    check(
        viking_char.trailing_item_bytes is None or len(viking_char.trailing_item_bytes) == 0,
        "VikingBarbie has 0 trailing bytes",
        f"got {len(viking_char.trailing_item_bytes) if viking_char.trailing_item_bytes else 0}",
    )
    check(
        viking_char.corpse_jm_byte_offset is not None,
        "VikingBarbie corpse_jm_byte_offset is set",
    )
    check(
        len(viking_char.items) == 113,
        "VikingBarbie has 113 root items",
        f"got {len(viking_char.items)}",
    )
    check(
        len(viking_char.merc_items) == 9,
        "VikingBarbie has 9 root merc items",
        f"got {len(viking_char.merc_items)}",
    )

    # ----------------------------------------------------------------
    # 2. VikingBarbie: all 12 equipped slots
    # ----------------------------------------------------------------
    print("\n--- VikingBarbie: equipped slots ---")

    equipped_slots = {
        it.flags.equipped_slot for it in viking_char.items if it.flags.location_id == 1
    }
    check(
        equipped_slots == set(range(1, 13)),
        "All 12 equipped slots present",
        f"missing: {set(range(1, 13)) - equipped_slots}",
    )

    # Weapon switch items
    switch_items = {
        it.flags.equipped_slot: it
        for it in viking_char.items
        if it.flags.location_id == 1 and it.flags.equipped_slot in (11, 12)
    }
    check(
        12 in switch_items
        and switch_items[12].item_code == "uit"
        and switch_items[12].flags.runeword,
        "LH Switch = Spirit Monarch (runeword)",
    )
    check(
        11 in switch_items and switch_items[11].item_code == "wsd",
        "RH Switch = Warrior Untamed (wsd)",
    )

    # Main weapon + shield
    main_items = {
        it.flags.equipped_slot: it
        for it in viking_char.items
        if it.flags.location_id == 1 and it.flags.equipped_slot in (4, 5)
    }
    check(
        4 in main_items and main_items[4].item_code == "7wa",
        "RH Main = Frost Wyrm (7wa)",
    )
    check(
        5 in main_items and main_items[5].item_code == "uow",
        "LH Main = Knight's Dawn (uow)",
    )

    # ----------------------------------------------------------------
    # 3. VikingBarbie Spirit: RW single-list format
    # ----------------------------------------------------------------
    print("\n--- VikingBarbie Spirit: single-list RW ---")

    spirit = switch_items.get(12)
    if spirit:
        check(
            len(spirit.magical_properties or []) == 0,
            "Spirit base_props = 0 (single-list format)",
        )
        rw_props = spirit.runeword_properties or []
        check(
            len(rw_props) == 7,
            "Spirit rw_props = 7",
            f"got {len(rw_props)}",
        )
        rw_stat_ids = {p["stat_id"] for p in rw_props}
        expected_stats = {3, 9, 32, 99, 105, 127, 147}
        check(
            rw_stat_ids == expected_stats,
            "Spirit RW stats match expected set",
            f"got {rw_stat_ids}",
        )

    # ----------------------------------------------------------------
    # 4. Unmodified round-trips
    # ----------------------------------------------------------------
    print("\n--- Unmodified round-trips ---")

    writer_v = D2SWriter(viking_source, viking_char)
    result_v = writer_v.build()
    check(
        result_v == viking_source,
        "VikingBarbie unmodified -> byte-identical",
        f"len diff: {len(result_v)} vs {len(viking_source)}",
    )

    writer_m = D2SWriter(mr_source, mr_char)
    result_m = writer_m.build()
    check(
        result_m == mr_source,
        "MrLockhart unmodified -> byte-identical",
    )

    # ----------------------------------------------------------------
    # 5. MrLockhart: no trailing bytes, clean parse
    # ----------------------------------------------------------------
    print("\n--- MrLockhart: clean parse ---")

    check(
        mr_char.trailing_item_bytes is None,
        "MrLockhart has no trailing bytes",
    )
    check(
        mr_char.corpse_jm_byte_offset is not None,
        "MrLockhart corpse_jm_byte_offset is set",
    )

    # ----------------------------------------------------------------
    # 6. MrLockhart append_item still works
    # ----------------------------------------------------------------
    print("\n--- MrLockhart append ---")

    donor = mr_char.items[0]
    donor_copy = copy.deepcopy(donor)
    donor_copy.source_data = patch_item_position(
        donor_copy.source_data,
        location_id=0,
        panel_id=1,
        position_x=0,
        position_y=0,
    )
    writer_mr = D2SWriter(mr_source, mr_char)
    result_mr = writer_mr.append_item(donor_copy)
    expected_size = len(mr_source) + len(donor.source_data)
    check(
        len(result_mr) == expected_size,
        "MrLockhart append: file size correct",
        f"got {len(result_mr)}, expected {expected_size}",
    )

    with tempfile.NamedTemporaryFile(suffix=".d2s", delete=False) as f:
        f.write(result_mr)
        tmp_path = Path(f.name)
    try:
        reparsed = D2SParser(tmp_path).parse()
        check(
            reparsed.corpse_jm_byte_offset is not None,
            "MrLockhart append: re-parse finds corpse JM",
        )
        check(
            len(reparsed.items) == len(mr_char.items) + 1,
            "MrLockhart append: +1 items",
            f"got {len(reparsed.items)}",
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    # ----------------------------------------------------------------
    # 7. TestSorc: Superior Monarchs with ED% + MaxDur%
    # ----------------------------------------------------------------
    print("\n--- TestSorc: Superior Monarchs ---")

    if test_sorc_path.exists():
        ts_char = D2SParser(test_sorc_path).parse()
        monarchs = [it for it in ts_char.items if it.item_code == "uit"]
        check(
            len(monarchs) == 3,
            "TestSorc has 3 Monarchs",
            f"got {len(monarchs)}",
        )
        expected = {0: (2, 3), 2: (15, 12), 4: (12, 7)}
        for m in monarchs:
            x = m.flags.position_x
            if x in expected:
                ed_exp, md_exp = expected[x]
                props = {p["stat_id"]: p.get("value") for p in (m.magical_properties or [])}
                ed = props.get(16)
                md = props.get(75)
                check(
                    ed == ed_exp and md == md_exp,
                    f"Monarch ({x},0): ED={ed_exp}% MaxDur={md_exp}%",
                    f"got ED={ed} MaxDur={md}",
                )
                check(
                    m.total_nr_of_sockets == 4,
                    f"Monarch ({x},0): 4 sockets",
                    f"got {m.total_nr_of_sockets}",
                )
    else:
        print("  SKIP  TestSorc.d2s not found")

    # ----------------------------------------------------------------
    # Summary
    # ----------------------------------------------------------------
    print(f"\n{'=' * 60}")
    print(f"Total: {passed} PASS, {failed} FAIL ({total} checks)")
    print(f"{'=' * 60}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

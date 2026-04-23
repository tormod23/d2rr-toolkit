#!/usr/bin/env python3
"""Build a demo character by injecting items from donor test cases.

Uses the D2S Writer to take a base character (TC12 TestSorc) and inject
cool unique/set/rare items from TC48, TC49, TC55, and TC56 into
the inventory and stash.

Usage:
    python tests/build_demo_character.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Project source must be importable
project_root = Path(__file__).parent.parent
src_dir = project_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


def main():
    from d2rr_toolkit.config import init_game_paths
    from d2rr_toolkit.game_data.charstats import load_charstats
    from d2rr_toolkit.game_data.item_stat_cost import load_item_stat_cost
    from d2rr_toolkit.game_data.item_types import load_item_types, get_item_type_db
    from d2rr_toolkit.game_data.item_names import load_item_names, get_item_names_db
    from d2rr_toolkit.parsers.d2s_parser import D2SParser
    from d2rr_toolkit.writers.d2s_writer import D2SWriter
    from d2rr_toolkit.writers.item_utils import patch_item_position
    from d2rr_toolkit.models.character import ParsedItem

    # Load game data via the Iron Rule.
    print("Loading game data...")
    init_game_paths()
    load_charstats()
    load_item_stat_cost()
    load_item_types()
    load_item_names()
    type_db = get_item_type_db()
    name_db = get_item_names_db()
    print("Game data loaded.")

    cases_dir = project_root / "tests" / "cases"

    # ── Parse base character ──────────────────────────────────────────
    base_path = cases_dir / "TC12" / "TestSorc.d2s"
    print(f"\nBase character: {base_path}")
    base_data = base_path.read_bytes()
    base_char = D2SParser(base_path).parse()
    print(
        f"  {base_char.header.character_name} L{base_char.header.level} "
        f"{base_char.header.character_class_name} - {len(base_char.items)} items"
    )
    print(f"  JM offset: {base_char.items_jm_byte_offset}")
    print(f"  Corpse JM: {base_char.corpse_jm_byte_offset}")

    # ── Parse donor characters ────────────────────────────────────────
    donors = {}
    for tc_name, filename in [
        ("TC48", "BigStats.d2s"),
        ("TC49", "MrLockhart.d2s"),
        ("TC55", "FrozenOrbHydra.d2s"),
        ("TC56", "VikingBarbie.d2s"),
    ]:
        path = cases_dir / tc_name / filename
        if path.exists():
            char = D2SParser(path).parse()
            donors[tc_name] = char
            print(f"  Donor {tc_name}: {char.header.character_name} - {len(char.items)} items")

    # ── Select cool items ─────────────────────────────────────────────
    # Hand-picked items that are interesting for in-game verification
    selected: list[tuple[str, int, str]] = []  # (tc, item_index, description)

    # TC49 MrLockhart - diverse unique/set collection
    tc49 = donors["TC49"]
    picks_49 = [
        (53, "Unique Small Charm (Black Soulstone) - 14 props"),
        (54, "Unique Medium Charm (Throne of Power) - 12 props"),
        (55, "Unique Grand Charm (Gheed's Fortune) - 7 props"),
        (18, "Unique Ring - 6 props"),
        (28, "Unique Ring - 5 props"),
        (108, "Unique Amulet - 5 props"),
        (0, "Set Amulet - 4 props"),
        (1, "Set Ring - 4 props"),
        (7, "Set Ring - 4 props"),
        (17, "Unique Belt (Thundergod's Vigor?) - 7 props"),
        (19, "Unique Throwing Knife - 10 props"),
        (137, "Unique Jewel - 7 props"),
        (4, "Unique Diadem - 10 props"),
        (9, "Set Belt - 6 props"),
    ]

    # TC55 FrozenOrbHydra - crafted + set items
    tc55 = donors["TC55"]
    picks_55 = [
        (1, "Unique Small Charm - 14 props"),
        (2, "Unique Gloves - 8 props"),
    ]

    # TC48 BigStats - unique jewel + set armor
    tc48 = donors["TC48"]
    picks_48 = [
        (6, "Unique Jewel - 7 props"),
    ]

    # ── Simple grid placer ────────────────────────────────────────────
    # Inventory: 10 wide x 8 tall, panel_id=1
    # Stash: 16 wide x 13 tall, panel_id=5

    class GridPlacer:
        def __init__(self, width: int, height: int, panel_id: int):
            self.width = width
            self.height = height
            self.panel_id = panel_id
            self.grid = [[False] * width for _ in range(height)]

        def place(self, item_w: int, item_h: int) -> tuple[int, int] | None:
            """Find first empty spot for an item of given size. Returns (x, y) or None."""
            for y in range(self.height - item_h + 1):
                for x in range(self.width - item_w + 1):
                    if self._fits(x, y, item_w, item_h):
                        self._mark(x, y, item_w, item_h)
                        return (x, y)
            return None

        def _fits(self, x: int, y: int, w: int, h: int) -> bool:
            for dy in range(h):
                for dx in range(w):
                    if self.grid[y + dy][x + dx]:
                        return False
            return True

        def _mark(self, x: int, y: int, w: int, h: int) -> None:
            for dy in range(h):
                for dx in range(w):
                    self.grid[y + dy][x + dx] = True

    inv_placer = GridPlacer(10, 8, panel_id=1)
    stash_placer = GridPlacer(16, 13, panel_id=5)

    # ── Collect and position items ────────────────────────────────────
    items_to_inject: list[ParsedItem] = []
    placement_log: list[str] = []

    def add_item(donor_char, item_idx: int, desc: str, placer: GridPlacer, target_name: str):
        item = donor_char.items[item_idx]
        if not item.source_data:
            print(f"  SKIP: Item [{item_idx}] has no source_data")
            return False

        w, h = type_db.get_inv_dimensions(item.item_code)
        pos = placer.place(w, h)
        if pos is None:
            print(f"  SKIP: No room for [{item_idx}] {item.item_code} ({w}x{h}) in {target_name}")
            return False

        x, y = pos
        patched_blob = patch_item_position(
            item.source_data,
            position_x=x,
            position_y=y,
            panel_id=placer.panel_id,
            location_id=0,  # Stored
            equipped_slot=0,
        )
        # Create a copy of the item with the patched blob
        patched_item = item.model_copy()
        patched_item.source_data = patched_blob

        items_to_inject.append(patched_item)
        entry = f"  [{target_name}] ({x},{y}) {item.item_code} ({w}x{h}) - {desc}"
        placement_log.append(entry)
        print(entry)
        return True

    print("\n--- Placing items in INVENTORY (10x8) ---")
    # Small items first for inventory
    for idx, desc in picks_49[:3]:  # 3 unique charms
        add_item(tc49, idx, desc, inv_placer, "Inventory")
    for idx, desc in picks_49[3:6]:  # rings + amulet
        add_item(tc49, idx, desc, inv_placer, "Inventory")
    for idx, desc in picks_55:
        add_item(tc55, idx, desc, inv_placer, "Inventory")
    for idx, desc in picks_48:
        add_item(tc48, idx, desc, inv_placer, "Inventory")

    print("\n--- Placing items in STASH (16x13) ---")
    for idx, desc in picks_49[6:]:
        add_item(tc49, idx, desc, stash_placer, "Stash")

    # ── Build the modified character ──────────────────────────────────
    print("\n--- Building modified D2S ---")
    writer = D2SWriter(base_data, base_char, item_names_db=name_db)

    # Remove existing stored items (just the 1 item from TC12)
    removed = writer.remove_stored_items()
    print(f"  Removed {len(removed)} original stored items")

    # Inject our curated selection
    writer.inject_items(items_to_inject)

    output_path = project_root / "tests" / "cases" / "TC60" / "TestSorc.d2s"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer.write(output_path)

    print(f"\n  Written: {output_path}")
    print(f"  File size: {output_path.stat().st_size} bytes")

    # ── Verify by re-parsing ──────────────────────────────────────────
    print("\n--- Verification: re-parsing ---")
    verify_char = D2SParser(output_path).parse()
    print(
        f"  Character: {verify_char.header.character_name} L{verify_char.header.level} {verify_char.header.character_class_name}"
    )
    print(f"  Total items: {len(verify_char.items)}")
    eq = len(verify_char.items_equipped())
    stored_inv = len(verify_char.items_in_inventory())
    stored_stash = len(
        [i for i in verify_char.items if i.flags.location_id == 0 and i.flags.panel_id == 5]
    )
    belt = len(verify_char.items_in_belt())
    sock = len([i for i in verify_char.items if i.flags.location_id == 6])
    print(
        f"  Equipped={eq} Inventory={stored_inv} Stash={stored_stash} Belt={belt} Socketed={sock}"
    )

    # Print each item with position
    print("\n--- Item List ---")
    for i, item in enumerate(verify_char.items):
        loc = item.flags.location_id
        panel = item.flags.panel_id
        x, y = item.flags.position_x, item.flags.position_y
        w, h = type_db.get_inv_dimensions(item.item_code)
        q = item.extended.quality_name if item.extended else "simple"
        where = {
            0: {1: "Inv", 4: "Cube", 5: "Stash"}.get(panel, f"p{panel}"),
            1: "Eq",
            2: "Belt",
            6: "Sock",
        }.get(loc, f"loc{loc}")
        print(f"  [{i}] {item.item_code} ({w}x{h}) {q} @ {where}({x},{y})")

    print("\n--- Placement Summary ---")
    for entry in placement_log:
        print(entry)

    # ── carry1 validation test ──────────────────────────────────────────
    print("\n--- carry1 Validation Test ---")
    from d2rr_toolkit.writers.d2s_writer import D2SWriteError

    # Re-parse the output file to get fresh offsets
    verify_data = output_path.read_bytes()
    verify_char2 = D2SParser(output_path).parse()
    writer2 = D2SWriter(verify_data, verify_char2, item_names_db=name_db)

    # Try to inject a SECOND Nightshade (Grand Charm with carry1) - must fail
    nightshade = tc49.items[55]  # Nightshade (Unique Grand Charm, carry1 restricted)
    patched = patch_item_position(nightshade.source_data, position_x=0, position_y=5, panel_id=1)
    dup_item = nightshade.model_copy()
    dup_item.source_data = patched
    try:
        writer2.inject_items([dup_item])
        print("  FAIL: carry1 violation was NOT detected!")
        return 1
    except D2SWriteError as e:
        print(f"  PASS: carry1 correctly rejected: {e}")

    # Try to inject a SECOND Black Soulstone (no carry1) - must succeed
    writer3 = D2SWriter(verify_data, verify_char2, item_names_db=name_db)
    black_soul = tc49.items[53]  # Black Soulstone (no carry1)
    patched2 = patch_item_position(black_soul.source_data, position_x=0, position_y=5, panel_id=1)
    dup_item2 = black_soul.model_copy()
    dup_item2.source_data = patched2
    try:
        writer3.inject_items([dup_item2])
        print("  PASS: Black Soulstone (no carry1) correctly accepted")
    except D2SWriteError as e:
        print(f"  FAIL: Black Soulstone wrongly rejected: {e}")
        return 1

    print(f"\nDONE. File ready for in-game testing: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


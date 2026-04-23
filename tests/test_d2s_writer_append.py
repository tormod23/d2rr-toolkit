#!/usr/bin/env python3
"""Test suite for D2SWriter.append_item() (feature/gui-pull-from-db).

Covers the byte-splice append method that inserts items into D2S files
without triggering the full rebuild path. This method was introduced to
avoid the corpse_jm_byte_offset=None problem and is the primary write
path for pull-from-DB transfers.

Regression guards for bugs found during manual testing:
- Insert position must be after JM-counted items (not before corpse JM)
- JM count must increment by item_count (1 for simple, 1+N for socketed)
- Multiple consecutive appends must not corrupt the file
- Socket children must survive re-parse after append
- Append must work even when corpse_jm_byte_offset is None

Requires: D2R Reimagined installation, TC49/MrLockhart.d2s fixture.
"""

from __future__ import annotations

import struct
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
    from d2rr_toolkit.writers.d2s_writer import D2SWriter, D2SWriteError
    from d2rr_toolkit.writers.item_utils import patch_item_position
    from d2rr_toolkit.models.character import ParsedItem, ItemFlags

    src_path = project_root / "tests" / "cases" / "TC49" / "MrLockhart.d2s"
    source = src_path.read_bytes()
    char = D2SParser(src_path).parse()

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

    def make_item(code, blob, pos_x=0, pos_y=0, panel=5, socketed=False, runeword=False, sockets=0):
        patched = patch_item_position(blob, pos_x, pos_y, panel_id=panel)
        flags = ItemFlags.model_construct(
            identified=True,
            socketed=socketed,
            starter_item=False,
            simple=False,
            ethereal=False,
            personalized=False,
            runeword=runeword,
            location_id=0,
            equipped_slot=0,
            position_x=pos_x,
            position_y=pos_y,
            panel_id=panel,
        )
        return ParsedItem.model_construct(
            item_code=code,
            flags=flags,
            source_data=patched,
            magical_properties=[],
            set_bonus_properties=[],
            set_bonus_mask=0,
            total_nr_of_sockets=sockets,
            quantity=0,
        )

    # Find a simple stored item for test templates
    simple_stored = next(
        it
        for it in char.items
        if it.flags.location_id == 0
        and not it.flags.socketed
        and it.item_code in ("cm1", "jew", "amu", "rin")
    )

    # -- 1. Basic append: single unsocketed item ----------------------------
    print("\n=== 1. Basic append ===")

    w = D2SWriter(source, char)
    item_a = make_item(simple_stored.item_code, simple_stored.source_data, 0, 0)
    result = w.append_item(item_a)

    # File grew by exactly the blob size
    check(
        len(result) == len(source) + len(simple_stored.source_data),
        f"file grew by {len(simple_stored.source_data)} bytes",
        f"expected {len(source) + len(simple_stored.source_data)}, got {len(result)}",
    )

    # JM count incremented by 1
    jm_off = char.items_jm_byte_offset
    old_count = struct.unpack_from("<H", source, jm_off + 2)[0]
    new_count = struct.unpack_from("<H", result, jm_off + 2)[0]
    check(new_count == old_count + 1, f"JM count: {old_count} -> {new_count}")

    # Re-parse succeeds and finds the appended item
    tmp = Path(tempfile.mkdtemp()) / "append1.d2s"
    tmp.write_bytes(result)
    char1 = D2SParser(tmp).parse()
    check(
        len(char1.items) > len(char.items),
        f"re-parsed has more items ({len(char1.items)} vs {len(char.items)})",
    )
    check(char1.corpse_jm_byte_offset is not None, "corpse_jm_byte_offset preserved after append")
    check(
        len(char1.merc_items) == len(char.merc_items),
        f"merc items unchanged ({len(char1.merc_items)})",
    )

    # -- 2. Socketed append (item_count > 1) --------------------------------
    print("\n=== 2. Socketed append ===")

    # Build a socketed item blob from an equipped item with children
    eq_parent = next(it for it in char.items if it.item_code == "uui" and it.socket_children)
    eq_children = eq_parent.socket_children
    combined = bytearray(eq_parent.source_data)
    for c in eq_children:
        combined += c.source_data

    socketed_item = make_item(
        eq_parent.item_code,
        bytes(combined),
        pos_x=4,
        pos_y=4,
        socketed=True,
        runeword=eq_parent.flags.runeword,
        sockets=eq_parent.total_nr_of_sockets,
    )

    w2 = D2SWriter(source, char)
    result2 = w2.append_item(socketed_item, item_count=5)

    new_count2 = struct.unpack_from("<H", result2, jm_off + 2)[0]
    check(
        new_count2 == old_count + 5,
        f"JM count incremented by 5 (parent+4 children): {old_count} -> {new_count2}",
    )

    # Re-parse and verify children
    tmp2 = Path(tempfile.mkdtemp()) / "append2.d2s"
    tmp2.write_bytes(result2)
    char2 = D2SParser(tmp2).parse()
    check(char2.corpse_jm_byte_offset is not None, "corpse_jm preserved after socketed append")

    # Find the appended item and check its children
    found_parent = False
    for it in char2.items:
        if it.item_code == "uui" and it.flags.position_x == 4 and it.flags.panel_id == 5:
            found_parent = True
            check(
                len(it.socket_children) == 4,
                f"appended socketed item has 4 children (got {len(it.socket_children)})",
            )
            break
    check(found_parent, "appended socketed item found at (4,4) in stash")

    # -- 3. Multiple consecutive appends ------------------------------------
    print("\n=== 3. Multiple consecutive appends ===")

    # First append
    w3 = D2SWriter(source, char)
    r3a = w3.append_item(make_item("cm1", simple_stored.source_data, 0, 0))
    tmp3 = Path(tempfile.mkdtemp()) / "multi.d2s"
    tmp3.write_bytes(r3a)
    char3a = D2SParser(tmp3).parse()

    # Second append (new writer from re-parsed character)
    w3b = D2SWriter(tmp3.read_bytes(), char3a)
    r3b = w3b.append_item(make_item("cm1", simple_stored.source_data, 1, 0))
    tmp3.write_bytes(r3b)
    char3b = D2SParser(tmp3).parse()

    # Third append
    w3c = D2SWriter(tmp3.read_bytes(), char3b)
    r3c = w3c.append_item(make_item("cm1", simple_stored.source_data, 2, 0))
    tmp3.write_bytes(r3c)
    char3c = D2SParser(tmp3).parse()

    final_count = struct.unpack_from("<H", r3c, jm_off + 2)[0]
    check(
        final_count == old_count + 3, f"3 consecutive appends: count {old_count} -> {final_count}"
    )
    check(char3c.corpse_jm_byte_offset is not None, "corpse_jm preserved after 3 appends")
    check(
        len(char3c.merc_items) == len(char.merc_items),
        f"merc items still {len(char.merc_items)} after 3 appends",
    )

    # -- 4. Append with no source_data raises --------------------------------
    print("\n=== 4. Error handling ===")

    bad_item = ParsedItem.model_construct(
        item_code="xxx",
        flags=ItemFlags.model_construct(
            identified=True,
            socketed=False,
            starter_item=False,
            simple=False,
            ethereal=False,
            personalized=False,
            runeword=False,
            location_id=0,
            equipped_slot=0,
            position_x=0,
            position_y=0,
            panel_id=5,
        ),
        source_data=None,
        magical_properties=[],
        set_bonus_properties=[],
        set_bonus_mask=0,
        total_nr_of_sockets=0,
        quantity=0,
    )
    try:
        D2SWriter(source, char).append_item(bad_item)
        check(False, "append without source_data raises")
    except D2SWriteError:
        check(True, "append without source_data raises D2SWriteError")

    # -- 5. Append preserves file integrity (checksum valid) -----------------
    print("\n=== 5. Checksum integrity ===")

    w5 = D2SWriter(source, char)
    r5 = w5.append_item(make_item("cm1", simple_stored.source_data, 5, 5))

    # Verify checksum by re-computing
    r5_buf = bytearray(r5)
    stored_checksum = struct.unpack_from("<I", r5_buf, 0x0C)[0]
    # Zero the checksum field and recompute
    struct.pack_into("<I", r5_buf, 0x0C, 0)
    computed = 0
    for byte in r5_buf:
        computed = ((computed << 1) | (computed >> 31)) & 0xFFFFFFFF
        computed = (computed + byte) & 0xFFFFFFFF
    check(
        computed == stored_checksum,
        f"checksum valid (stored=0x{stored_checksum:08X}, computed=0x{computed:08X})",
    )

    # -- Summary -------------------------------------------------------------
    print()
    print("=" * 60)
    print(f"Total: {passed} PASS, {failed} FAIL ({total} checks)")
    print("=" * 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

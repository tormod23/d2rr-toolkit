#!/usr/bin/env python3
"""Test suite for D2I Section 5 writer (feature/d2i-section5-writer).

Covers the Shared Stash "Gems/Materials/Runes" section writer pipeline:

- Parser metadata: every stackable Section 5 item gets a quantity_bit_offset
  and quantity_bit_width populated (9 for simple, 7 for extended).
- patch_item_quantity: modifies the quantity field in-place on a blob copy,
  preserves the simple-item LSB flag bit, enforces the 0..99 game cap.
- clone_with_quantity: returns a new ParsedItem with patched blob and
  updated raw quantity, usable as a template for further operations.
- _display_to_raw_quantity: correct encoding for both simple and extended.
- Writer roundtrip: unchanged tabs remain byte-identical; patched tabs
  produce a valid .d2i that re-parses with the new quantities.
- Add / remove entries in Section 5: writer rebuilds the section with
  correct count + size, trailing sections preserved.
- Split workflow: one N-stack cloned into (a, b) pair with a+b=N.
- Error handling: missing metadata, out-of-range quantities, missing blob.

Requires: D2R Reimagined installation, tests/cases/TC61/MixedSection5.d2i fixture.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

project_root = Path(__file__).parent.parent
src_dir = project_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


def _init():
    """Load game data, parse TC61 fixture, return (orig_bytes, stash)."""
    import logging

    logging.basicConfig(level=logging.ERROR)

    from d2rr_toolkit.cli import _load_game_data
    from d2rr_toolkit.parsers.d2i_parser import D2IParser

    fixture = project_root / "tests" / "cases" / "TC61" / "MixedSection5.d2i"
    _load_game_data(fixture)
    orig = fixture.read_bytes()
    stash = D2IParser(fixture).parse()
    return fixture, orig, stash


def main() -> int:
    from d2rr_toolkit.parsers.d2i_parser import D2IParser
    from d2rr_toolkit.writers.d2i_writer import D2IWriter, DuplicateSection5ItemError
    from d2rr_toolkit.writers.item_utils import (
        SECTION5_MAX_QUANTITY,
        SIMPLE_QTY_WIDTH,
        EXTENDED_QTY_WIDTH,
        clone_with_quantity,
        patch_item_quantity,
        read_bits,
    )

    fixture, orig_bytes, stash = _init()
    t5 = stash.tabs[5]

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

    def rewrite_tabs(modified_tab5):
        """Helper: build output bytes with tab5 replaced, parse back.

        Uses from_stash() so the writer matches the production path:
        snapshot in _original_items + byte-splice for changed tabs.
        Direct 2-arg construction would route through the legacy
        full-rebuild path, which is now hard-blocked for grid tabs.
        """
        writer = D2IWriter.from_stash(orig_bytes, stash)
        writer._tab_items[5] = modified_tab5  # noqa: SLF001
        out = bytes(writer.build())
        tmp = Path(tempfile.mkdtemp()) / "rt.d2i"
        tmp.write_bytes(out)
        return out, D2IParser(tmp).parse()

    def display_of(item):
        # Now uses the model's display_quantity property - replaces the
        # manual (raw >> 1) workaround that was needed before the property existed.
        return item.display_quantity

    # -- 1. Parser metadata ---------------------------------------------------
    print("\n=== 1. Parser metadata ===")

    check(len(t5.items) == 34, "TC61 Section 5 has 34 items")

    metadata_ok = 0
    for it in t5.items:
        if it.quantity_bit_offset is not None:
            if it.flags.simple and it.quantity_bit_width == SIMPLE_QTY_WIDTH:
                metadata_ok += 1
            elif not it.flags.simple and it.quantity_bit_width == EXTENDED_QTY_WIDTH:
                metadata_ok += 1
    check(metadata_ok == 34, "all 34 items have correct quantity metadata", f"got {metadata_ok}/34")

    for it in t5.items:
        bits_total = len(it.source_data) * 8
        in_range = it.quantity_bit_offset + it.quantity_bit_width <= bits_total
        if not in_range:
            check(
                False,
                f"{it.item_code} bit-range inside blob",
                f"off={it.quantity_bit_offset} w={it.quantity_bit_width} total={bits_total}",
            )
            break
    else:
        check(True, "all quantity bit-ranges lie inside their blobs")

    # -- 2. read_bits helper round-trip --------------------------------------
    print("\n=== 2. read_bits helper ===")

    for it in t5.items:
        raw = read_bits(it.source_data, it.quantity_bit_offset, it.quantity_bit_width)
        if raw != it.quantity:
            check(False, f"read_bits({it.item_code})", f"expected {it.quantity}, got {raw}")
            break
    else:
        check(True, "read_bits reproduces parser quantity for all 34 items")

    # -- 3. patch_item_quantity: simple items --------------------------------
    print("\n=== 3. patch_item_quantity: simple items ===")

    r01 = next(it for it in t5.items if it.item_code == "r01")
    original_lsb = r01.quantity & 1

    for target_disp in [1, 50, 99]:
        new_blob = patch_item_quantity(r01, target_disp)
        new_raw = read_bits(new_blob, r01.quantity_bit_offset, SIMPLE_QTY_WIDTH)
        # LSB preserved
        check(
            (new_raw & 1) == original_lsb,
            f"r01 LSB preserved at disp={target_disp}",
            f"orig LSB={original_lsb}, new raw={new_raw}",
        )
        # Upper 8 bits encode target
        check(
            (new_raw >> 1) == target_disp,
            f"r01 upper-8 encodes disp={target_disp}",
            f"new raw={new_raw}, upper={new_raw >> 1}",
        )
        # Blob length unchanged
        check(
            len(new_blob) == len(r01.source_data),
            f"r01 blob length preserved at disp={target_disp}",
        )

    # -- 4. patch_item_quantity: extended items ------------------------------
    print("\n=== 4. patch_item_quantity: extended items ===")

    xa4 = next(it for it in t5.items if it.item_code == "xa4")
    for target in [1, 50, 99]:
        new_blob = patch_item_quantity(xa4, target)
        new_raw = read_bits(new_blob, xa4.quantity_bit_offset, EXTENDED_QTY_WIDTH)
        check(new_raw == target, f"xa4 extended 7-bit encodes qty={target}", f"got raw={new_raw}")
        check(len(new_blob) == len(xa4.source_data), f"xa4 blob length preserved at qty={target}")

    # -- 5. patch_item_quantity: error handling ------------------------------
    print("\n=== 5. Error handling ===")

    try:
        patch_item_quantity(r01, -1)
        check(False, "negative quantity raises")
    except ValueError:
        check(True, "negative quantity raises ValueError")

    try:
        patch_item_quantity(r01, SECTION5_MAX_QUANTITY + 1)
        check(False, "quantity > 99 raises")
    except ValueError:
        check(True, "quantity > 99 raises ValueError")

    # [BV TC61 round 2] quantity=0 creates a hidden zombie entry in the game's
    # save file. The writer forbids it and forces callers to drop the item
    # from the tab list instead.
    try:
        patch_item_quantity(r01, 0)
        check(False, "quantity=0 raises (zombie prevention)")
    except ValueError as e:
        check(
            "zombie" in str(e).lower() or "remove" in str(e).lower(),
            "quantity=0 raises with explanation mentioning zombie/remove",
            f"msg: {e}",
        )

    # Synthesise an item without metadata
    fake = r01.model_copy(update={"quantity_bit_offset": None, "quantity_bit_width": 0})
    try:
        patch_item_quantity(fake, 50)
        check(False, "missing metadata raises")
    except ValueError:
        check(True, "missing metadata raises ValueError")

    # -- 6. clone_with_quantity -----------------------------------------------
    print("\n=== 6. clone_with_quantity ===")

    # Simple clone
    cloned_r01 = clone_with_quantity(r01, 50)
    check(cloned_r01 is not r01, "clone produces new object")
    check(cloned_r01.source_data is not r01.source_data, "clone has new blob reference")
    check(len(cloned_r01.source_data) == len(r01.source_data), "clone blob same length")
    check(cloned_r01.quantity_bit_offset == r01.quantity_bit_offset, "clone preserves bit offset")
    check(cloned_r01.quantity_bit_width == r01.quantity_bit_width, "clone preserves bit width")
    check(display_of(cloned_r01) == 50, f"clone display=50 (got {display_of(cloned_r01)})")

    # Extended clone
    cloned_xa4 = clone_with_quantity(xa4, 99)
    check(display_of(cloned_xa4) == 99, "extended clone display=99")

    # Clone a clone
    cloned_again = clone_with_quantity(cloned_r01, 1)
    check(display_of(cloned_again) == 1, "clone-of-clone works")

    # -- 7. Writer roundtrip: untouched -------------------------------------
    print("\n=== 7. Writer roundtrip: untouched ===")

    out_untouched, _ = rewrite_tabs(list(t5.items))
    check(
        out_untouched == orig_bytes,
        "untouched tab5 produces byte-identical output",
        f"len orig={len(orig_bytes)}, out={len(out_untouched)}",
    )

    # -- 8. Writer roundtrip: quantity-patched ------------------------------
    print("\n=== 8. Writer roundtrip: patched ===")

    patches = {"r01": 50, "xa4": 99, "gme": 77, "rup": 1}
    new_tab5 = []
    for it in t5.items:
        if it.item_code in patches:
            new_tab5.append(clone_with_quantity(it, patches[it.item_code]))
        else:
            new_tab5.append(it)

    out_patched, stash_patched = rewrite_tabs(new_tab5)
    check(len(out_patched) == len(orig_bytes), "patched file has same length as original")
    check(len(stash_patched.tabs[5].items) == 34, "patched file has 34 items in tab5")

    for code, expected in patches.items():
        it = next(x for x in stash_patched.tabs[5].items if x.item_code == code)
        check(
            display_of(it) == expected,
            f"re-parsed {code} display={expected}",
            f"got {display_of(it)}",
        )

    # Other items unchanged
    untouched_ok = 0
    for code in ("r09", "ooc", "ka3", "xa1"):
        orig_it = next(x for x in t5.items if x.item_code == code)
        new_it = next(x for x in stash_patched.tabs[5].items if x.item_code == code)
        if display_of(orig_it) == display_of(new_it):
            untouched_ok += 1
    check(untouched_ok == 4, "untouched items keep their quantity", f"got {untouched_ok}/4")

    # -- 9. Remove entries ---------------------------------------------------
    print("\n=== 9. Remove entries ===")

    reduced = [it for it in t5.items if it.item_code not in ("pk2", "pk3", "jwp")]
    out_rm, stash_rm = rewrite_tabs(reduced)
    check(len(stash_rm.tabs[5].items) == 31, "after removing 3 items, tab5 has 31")
    removed_codes = {it.item_code for it in stash_rm.tabs[5].items}
    check(
        "pk2" not in removed_codes and "pk3" not in removed_codes and "jwp" not in removed_codes,
        "removed codes are absent from re-parsed tab5",
    )
    # Trailing sections preserved
    check(len(stash_rm.tabs) == 6, "all 6 tabs still present after removal")
    # Original output length MUST differ (items were removed)
    check(len(out_rm) < len(orig_bytes), "removed-items file is smaller")

    # -- 10. Add / in-place replace -----------------------------------------
    # Section 5 rejects duplicate item_codes [BV TC61], so "add" in practice
    # means "remove an existing entry and add a differently-quantified clone
    # of another existing code" - i.e. the El Rune stack moves from 9 to 50
    # and the Key of Hate is removed in the same operation. This mirrors the
    # DB-transfer pattern: pull a quantity out, push a (possibly merged) stack
    # back in, all without introducing duplicates.
    print("\n=== 10. Add / in-place replace ===")

    # Remove one existing (Key of Hate) and replace another (r01 quantity 9 -> 77)
    after_replace = []
    for it in t5.items:
        if it.item_code == "pk2":
            continue  # drop Key of Hate
        if it.item_code == "r01":
            after_replace.append(clone_with_quantity(it, 77))
            continue
        after_replace.append(it)
    out_rep, stash_rep = rewrite_tabs(after_replace)
    check(len(stash_rep.tabs[5].items) == 33, "after remove-one + replace-one, tab5 has 33 items")
    r01_new = next(x for x in stash_rep.tabs[5].items if x.item_code == "r01")
    check(display_of(r01_new) == 77, "replaced r01 display=77")
    check(
        not any(x.item_code == "pk2" for x in stash_rep.tabs[5].items), "pk2 (Key of Hate) is gone"
    )

    # -- 10b. Duplicate detection (writer must refuse) ----------------------
    print("\n=== 10b. Duplicate detection ===")

    dup_writer = D2IWriter.from_stash(orig_bytes, stash)
    dup_writer._tab_items[5] = list(t5.items) + [clone_with_quantity(r01, 50)]  # noqa: SLF001
    try:
        dup_writer.build()
        check(False, "duplicate r01 raises DuplicateSection5ItemError")
    except DuplicateSection5ItemError as e:
        check("r01" in str(e), "duplicate r01 raises with item_code in message", f"msg: {e}")

    # Multiple duplicates at once
    dup_writer2 = D2IWriter.from_stash(orig_bytes, stash)
    dup_writer2._tab_items[5] = (  # noqa: SLF001
        list(t5.items) + [clone_with_quantity(r01, 50), clone_with_quantity(xa4, 50)]
    )
    try:
        dup_writer2.build()
        check(False, "multi-duplicate raises")
    except DuplicateSection5ItemError as e:
        msg = str(e)
        check(
            "r01" in msg and "xa4" in msg,
            "multi-duplicate message lists all offending codes",
            f"msg: {msg}",
        )

    # Sections 0-4 can legally contain duplicates (grid tabs) - but tab5 is empty
    # in this test, so we only verify the validation targets ONLY tab5, never 0-4.
    # This is covered implicitly by tests 7/8 where tab0-4 stay as-is.

    # -- 11. Split workflow (the main DB-transfer use case) ------------------
    print("\n=== 11. Split workflow ===")

    # Simulate: "I have 99 El-runes, want to move 90 to DB, keep 9"
    # Step 1: clone original into two stacks
    big = clone_with_quantity(r01, 99)  # first make it 99
    stay = clone_with_quantity(big, 9)  # stays in stash
    leave = clone_with_quantity(big, 90)  # what goes to DB (we just verify it exists)
    check(
        display_of(stay) + display_of(leave) == 99, "split: stay + leave == original (9 + 90 = 99)"
    )

    # Replace r01 in stash with the 'stay' clone, write, re-parse
    after_split = [stay if it is r01 else it for it in t5.items]
    out_split, stash_split = rewrite_tabs(after_split)
    r01_after_split = next(x for x in stash_split.tabs[5].items if x.item_code == "r01")
    check(display_of(r01_after_split) == 9, "after split, r01 in stash has display=9")

    # Also round-trip the 'leave' clone on its own (DB would store it as template)
    leave_raw = read_bits(leave.source_data, leave.quantity_bit_offset, SIMPLE_QTY_WIDTH)
    check((leave_raw >> 1) == 90, "leave-clone has display=90 encoded in blob")

    # -- 12. Boundary conditions ---------------------------------------------
    print("\n=== 12. Boundary conditions ===")

    # quantity=1 is the minimum allowed value (0 would create a zombie)
    min_q = clone_with_quantity(r01, 1)
    check(display_of(min_q) == 1, "quantity=1 (minimum) round-trips through clone")
    try:
        clone_with_quantity(r01, 0)
        check(False, "clone_with_quantity(0) raises")
    except ValueError:
        check(True, "clone_with_quantity(0) raises ValueError (zombie prevention)")
    max_q = clone_with_quantity(r01, 99)
    check(display_of(max_q) == 99, "quantity=99 round-trips through clone")

    # Writer still byte-identical when we set a quantity back to its original
    same = clone_with_quantity(r01, display_of(r01))
    # This produces the SAME blob iff the LSB was preserved and display matches
    check(same.source_data == r01.source_data, "clone-with-same-quantity produces identical blob")

    # -- Summary -------------------------------------------------------------
    print()
    print("=" * 60)
    print(f"Total: {passed} PASS, {failed} FAIL ({total} checks)")
    print("=" * 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())


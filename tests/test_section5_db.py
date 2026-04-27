#!/usr/bin/env python3
"""Test suite for Section5Database (feature/db-section5-integration).

Covers the DB integration layer that sits between the Section 5 writer
primitives (feature/d2i-section5-writer) and the user-facing transfer
workflows:

- Classifier helpers: is_gem_code, is_gem_cluster, rune_index, rune_code
- Schema migration: tables created, gem_pool singleton seeded
- Stack push/pull with first-seen template persistence and count growth
- Stack push rejects gems and Gem Cluster (wrong API)
- Pull validates count range, template existence, sufficient inventory
- Gem pool: push seeds template, increments shared counter
- Gem pool: pull requires template AND sufficient pool count
- Gem Cluster: random[20..30] roll, cluster itself not persisted
- Rune conversion: upgrade (2x -> 1x next), downgrade (1x -> 1x prev)
- Rune conversion edge cases: boundaries (r01, r33), insufficient source,
  missing target template
- Round-trip: pulled ParsedItem passes through D2IWriter + reparse and
  shows the correct quantity in-game format

Requires: D2R Reimagined installation, TC61/MixedSection5.d2i fixture.
"""

from __future__ import annotations

import random
import sys
import tempfile
from pathlib import Path

project_root = Path(__file__).parent.parent
src_dir = project_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


def _init():
    """Load game data, parse TC61 fixture, return (fixture_bytes, tab5_items_by_code)."""
    import logging

    logging.basicConfig(level=logging.ERROR)

    from d2rr_toolkit.cli import _load_game_data
    from d2rr_toolkit.parsers.d2i_parser import D2IParser

    fixture = project_root / "tests" / "cases" / "TC61" / "MixedSection5.d2i"
    _load_game_data(fixture)
    orig = fixture.read_bytes()
    stash = D2IParser(fixture).parse()
    t5_by_code = {it.item_code: it for it in stash.tabs[5].items}
    return fixture, orig, stash, t5_by_code


def main() -> int:
    from d2rr_toolkit.database.section5_db import (
        Section5Database,
        is_gem_code,
        is_gem_cluster,
        rune_code,
        rune_index,
        InsufficientCountError,
        TemplateMissingError,
        RuneBoundaryError,
    )
    from d2rr_toolkit.parsers.d2i_parser import D2IParser
    from d2rr_toolkit.writers.d2i_writer import D2IWriter

    fixture, orig_bytes, stash, t5_by_code = _init()

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

    def fresh_db() -> Section5Database:
        path = Path(tempfile.mkdtemp()) / "s5.db"
        return Section5Database(path)

    def display_of(item):
        return item.quantity >> 1 if item.flags.simple else item.quantity

    # ── 1. Classifier helpers ───────────────────────────────────────────
    print("\n=== 1. Classifier helpers ===")

    # Gems: Reimagined standard (gm?), chipped/flawed/flawless/perfect tiers, skulls
    check(is_gem_code("gmr"), "gmr (Ruby) is gem")
    check(is_gem_code("gme"), "gme (Emerald) is gem")
    check(is_gem_code("gcr"), "gcr (Chipped Ruby) is gem")
    check(is_gem_code("gpb"), "gpb (Perfect Sapphire) is gem")
    check(is_gem_code("sku"), "sku (Skull) is gem")
    check(is_gem_code("skc"), "skc (Chipped Skull) is gem")
    check(is_gem_code("skz"), "skz (Perfect Skull) is gem")
    # Non-gems that share the Section 5 sub-tab
    check(not is_gem_code("1gc"), "1gc (Gem Cluster) NOT gem")
    check(not is_gem_code("r01"), "r01 (El Rune) NOT gem")
    check(not is_gem_code("xa4"), "xa4 (Worldstone Shard) NOT gem")
    check(not is_gem_code("ooe"), "ooe (Orb of Shadows) NOT gem")
    check(not is_gem_code("pk2"), "pk2 (Key of Hate) NOT gem")
    check(not is_gem_code(""), "empty code NOT gem")
    # Cluster
    check(is_gem_cluster("1gc"), "1gc is Gem Cluster")
    check(not is_gem_cluster("gmr"), "gmr is NOT Gem Cluster")
    # Runes
    check(rune_index("r01") == 1, "rune_index(r01) == 1")
    check(rune_index("r33") == 33, "rune_index(r33) == 33")
    check(rune_index("r99") is None, "rune_index(r99) None")
    check(rune_index("gmr") is None, "rune_index(gmr) None")
    check(rune_code(1) == "r01", "rune_code(1) == r01")
    check(rune_code(33) == "r33", "rune_code(33) == r33")

    # ── 2. Schema migration ────────────────────────────────────────────
    print("\n=== 2. Schema migration ===")

    db = fresh_db()
    # gem_pool singleton must exist with count=0
    check(db.get_gem_pool_count() == 0, "fresh db: gem_pool.total_count == 0")
    check(db.list_stacks() == [], "fresh db: no stacks")
    check(db.list_gem_templates() == [], "fresh db: no gem templates")
    db.close()

    # ── 3. Stack push/pull with first-seen template ────────────────────
    print("\n=== 3. Stack push/pull ===")

    db = fresh_db()
    r01 = t5_by_code["r01"]  # El Rune (simple, 11B)
    xa4 = t5_by_code["xa4"]  # Deep Worldstone Shard (extended, 18B)

    db.push_stack(r01, 20)
    check(db.get_stack_count("r01") == 20, "push 20 r01 -> count 20")
    db.push_stack(r01, 30)
    check(db.get_stack_count("r01") == 50, "push 30 r01 more -> count 50 (accumulate)")

    # Template persisted and reusable
    stacks = db.list_stacks()
    r01_row = next(s for s in stacks if s.item_code == "r01")
    check(r01_row.flags_simple is True, "r01 template: flags_simple=True")
    check(r01_row.quantity_bit_width == 9, "r01 template: 9-bit quantity")

    db.push_stack(xa4, 7)
    check(db.get_stack_count("xa4") == 7, "push 7 xa4 -> count 7")
    xa4_row = next(s for s in db.list_stacks() if s.item_code == "xa4")
    check(xa4_row.flags_simple is False, "xa4 template: flags_simple=False")
    check(xa4_row.quantity_bit_width == 7, "xa4 template: 7-bit quantity")

    # Pull
    pulled = db.pull_stack("r01", 15)
    check(db.get_stack_count("r01") == 35, "after pull 15 r01 -> count 35")
    check(
        pulled.source_data is not None and len(pulled.source_data) == 11,
        "pulled r01 blob is 11 bytes",
    )
    check(
        pulled.quantity_bit_offset == 76,
        f"pulled r01 has quantity_bit_offset (got {pulled.quantity_bit_offset})",
    )

    # Pulled quantity is correctly set for the writer pipeline
    from d2rr_toolkit.writers.item_utils import read_bits, SIMPLE_QTY_WIDTH

    raw = read_bits(pulled.source_data, pulled.quantity_bit_offset, SIMPLE_QTY_WIDTH)
    check((raw >> 1) == 15, f"pulled r01 display=15 encoded in blob (raw={raw})")

    db.close()

    # ── 4. Stack push rejects gems + Gem Cluster ───────────────────────
    print("\n=== 4. push_stack rejects gems + cluster ===")

    db = fresh_db()
    gmr = t5_by_code["gmr"]  # Ruby gem
    gc1 = t5_by_code.get("1gc")  # Gem Cluster

    try:
        db.push_stack(gmr, 5)
        check(False, "push_stack(gem) raises")
    except ValueError as e:
        check("gem" in str(e).lower(), "push_stack(gem) raises ValueError", f"msg: {e}")

    if gc1:
        try:
            db.push_stack(gc1, 1)
            check(False, "push_stack(cluster) raises")
        except ValueError as e:
            check("cluster" in str(e).lower(), "push_stack(cluster) raises ValueError", f"msg: {e}")

    try:
        db.push_stack(r01, 0)
        check(False, "push_stack count=0 raises")
    except ValueError:
        check(True, "push_stack count=0 raises")

    db.close()

    # ── 5. Pull error handling ─────────────────────────────────────────
    print("\n=== 5. Pull error handling ===")

    db = fresh_db()
    db.push_stack(r01, 10)

    try:
        db.pull_stack("nope", 5)
        check(False, "pull unknown code raises TemplateMissingError")
    except TemplateMissingError:
        check(True, "pull unknown code raises TemplateMissingError")

    try:
        db.pull_stack("r01", 20)
        check(False, "pull more than available raises InsufficientCountError")
    except InsufficientCountError:
        check(True, "pull more than available raises InsufficientCountError")

    try:
        db.pull_stack("r01", 0)
        check(False, "pull count=0 raises")
    except ValueError:
        check(True, "pull count=0 raises")

    try:
        db.pull_stack("r01", 100)
        check(False, "pull count=100 raises (exceeds 99 cap)")
    except ValueError:
        check(True, "pull count=100 raises")

    db.close()

    # ── 6. Gem pool push/pull ──────────────────────────────────────────
    print("\n=== 6. Gem pool ===")

    db = fresh_db()
    db.push_gem(gmr, 50)
    check(db.get_gem_pool_count() == 50, "push 50 Ruby -> pool 50")
    templates = db.list_gem_templates()
    check(len(templates) == 1 and templates[0].gem_code == "gmr", "gem_templates seeded with Ruby")

    # Pushing more of the same gem only increments counter
    db.push_gem(gmr, 20)
    check(db.get_gem_pool_count() == 70, "push 20 more Ruby -> pool 70")
    check(len(db.list_gem_templates()) == 1, "still 1 template after repeat push")

    # Pull specific type succeeds (template present + pool sufficient)
    ruby_out = db.pull_gem("gmr", 5)
    check(db.get_gem_pool_count() == 65, "pull 5 Ruby -> pool 65")
    check(ruby_out.item_code == "gmr", "pulled item has code gmr")
    raw = read_bits(ruby_out.source_data, ruby_out.quantity_bit_offset, SIMPLE_QTY_WIDTH)
    check((raw >> 1) == 5, f"pulled Ruby has display=5 in blob (raw={raw})")

    # Pull unknown gem type: template missing even though pool is non-empty
    try:
        db.pull_gem("gmk", 3)  # Skull - never pushed
        check(False, "pull unseen gem type raises TemplateMissingError")
    except TemplateMissingError:
        check(True, "pull unseen gem type raises TemplateMissingError")

    # Insufficient pool: seed a second template, then try to overdraw
    gmm = t5_by_code["gmm"]  # Amethyst
    db.push_gem(gmm, 2)  # now 2 templates, pool 67
    try:
        db.pull_gem("gmm", 99)
        check(False, "pull more than pool raises InsufficientCountError")
    except InsufficientCountError:
        check(True, "pull overdraw raises InsufficientCountError")

    # Rejects non-gem codes on both push and pull
    try:
        db.push_gem(r01, 1)
        check(False, "push_gem(rune) raises")
    except ValueError:
        check(True, "push_gem(rune) raises")
    try:
        db.pull_gem("r01", 1)
        check(False, "pull_gem('r01') raises")
    except ValueError:
        check(True, "pull_gem('r01') raises")

    db.close()

    # ── 7. Gem Cluster random roll ────────────────────────────────────
    print("\n=== 7. Gem Cluster ===")

    if gc1:
        db = fresh_db()
        # Deterministic RNG for predictable test
        rng = random.Random(42)
        rolled = db.push_gem_cluster(gc1, rng=rng)
        check(20 <= rolled <= 30, f"Gem Cluster roll in [20, 30] (got {rolled})")
        check(db.get_gem_pool_count() == rolled, f"pool incremented by rolled count ({rolled})")
        check(len(db.list_gem_templates()) == 0, "Gem Cluster itself not persisted as template")

        # Second cluster stacks onto the pool
        rolled2 = db.push_gem_cluster(gc1, rng=rng)
        check(db.get_gem_pool_count() == rolled + rolled2, "second cluster adds to pool")

        # Non-cluster items rejected
        try:
            db.push_gem_cluster(gmr)
            check(False, "push_gem_cluster(non-cluster) raises")
        except ValueError:
            check(True, "push_gem_cluster(non-cluster) raises")

        db.close()

    # ── 8. Rune conversion: upgrade ────────────────────────────────────
    print("\n=== 8. Rune conversion: upgrade ===")

    db = fresh_db()
    # Seed templates for r01 (El) and r07 (Tal). Conversion requires both.
    r07 = t5_by_code["r07"]
    db.push_stack(r01, 4)  # 4 El
    db.push_stack(r07, 1)  # 1 Tal as target-template seed

    # Sanity: upgrade from El (r01) to Eld (r02) - but r02 has no template.
    try:
        db.convert_runes_upgrade("r01")
        check(False, "upgrade missing-target raises")
    except TemplateMissingError:
        check(True, "upgrade with missing target template raises TemplateMissingError")

    # Use r07 (Tal) with a target that exists as template (seed r08 manually
    # by grabbing r09's simple template and renaming it - actually no, we
    # can't rename Huffman. Instead, seed r08 via another push from fixture
    # if present.) The fixture only has r01/r07/r09/r18/r20/r31/r32, so
    # r02/r08 aren't available. We verify the "template missing" branch and
    # move on to the count-insufficient branch using r01->r02 with a fake
    # target.

    # Count-insufficient branch: downgrade r07 with only 1 present (need 1 -> OK)
    # So we test "insufficient" on r09 with 0 count.
    try:
        db.convert_runes_upgrade("r09")
        check(False, "upgrade of unseen code raises")
    except TemplateMissingError:
        check(True, "upgrade of unseen rune raises TemplateMissingError")

    # Boundary: r33 cannot upgrade
    # First we need to seed r33 in the DB. Use r32 as donor (wrong item, but
    # for template seeding we just need a row). Actually - we must use a REAL
    # r33 template to be correct. Since the fixture doesn't contain one, we
    # fake it by seeding r33 under its own code using the r32 blob. Then
    # convert_runes_upgrade("r33") should raise RuneBoundaryError BEFORE any
    # template lookup.
    r32 = t5_by_code["r32"]
    # Hack: bypass the gem/cluster checks by pushing under r32, then patching the
    # stored code in SQL for this boundary test. Instead, just test the
    # boundary check directly with an unseeded code - RuneBoundaryError is
    # raised before template lookup, so missing template is OK here.
    try:
        db.convert_runes_upgrade("r33")
        check(False, "upgrade r33 raises RuneBoundaryError")
    except RuneBoundaryError:
        check(True, "upgrade r33 raises RuneBoundaryError (before template lookup)")

    # Non-rune code
    try:
        db.convert_runes_upgrade("gmr")
        check(False, "upgrade gmr raises")
    except ValueError:
        check(True, "upgrade non-rune raises ValueError")

    db.close()

    # ── 9. Rune conversion: downgrade + successful round trip ─────────
    print("\n=== 9. Rune conversion: downgrade ===")

    db = fresh_db()
    # Seed both El (r01) and another rune. r09 -> r08: r08 has no template.
    # Use r07 -> r06: r06 also missing. The only viable test in TC61 is to
    # seed TWO adjacent runes we have (none exist!). So we inject via
    # push_stack + direct manipulation.
    r09 = t5_by_code["r09"]
    db.push_stack(r01, 2)
    db.push_stack(r09, 3)

    # Boundary: r01 cannot downgrade
    try:
        db.convert_runes_downgrade("r01")
        check(False, "downgrade r01 raises RuneBoundaryError")
    except RuneBoundaryError:
        check(True, "downgrade r01 raises RuneBoundaryError")

    # Downgrade r09 (Ort) to r08 (Ral) - missing target template
    try:
        db.convert_runes_downgrade("r09")
        check(False, "downgrade with missing target raises")
    except TemplateMissingError:
        check(True, "downgrade with missing target raises TemplateMissingError")

    # To test the SUCCESSFUL path, we seed BOTH sides. Cheapest option: use
    # the DB's own private access to INSERT a fake r02 row using r01's
    # template blob. This is a test-only shortcut - we are explicitly
    # validating the conversion arithmetic, not the template fidelity.
    src_row = next(s for s in db.list_stacks() if s.item_code == "r01")
    db._conn.execute(
        """INSERT INTO section5_stacks (item_code, total_count, template_blob,
           quantity_bit_offset, quantity_bit_width, flags_simple,
           first_seen_at, last_modified_at)
           VALUES ('r02', 0, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
        (
            src_row.template_blob,
            src_row.quantity_bit_offset,
            src_row.quantity_bit_width,
            int(src_row.flags_simple),
        ),
    )
    db._conn.commit()

    # Now upgrade r01 (2 El) -> 1 Eld (r02). Count: r01: 2 -> 0, r02: 0 -> 1
    target = db.convert_runes_upgrade("r01")
    check(target == "r02", "upgrade returns target code r02")
    check(db.get_stack_count("r01") == 0, "after upgrade r01 count = 0 (was 2)")
    check(db.get_stack_count("r02") == 1, "after upgrade r02 count = 1")

    # Insufficient source: only 0 El left, cannot upgrade again
    try:
        db.convert_runes_upgrade("r01")
        check(False, "upgrade with 0 source raises")
    except InsufficientCountError:
        check(True, "upgrade with 0 source raises InsufficientCountError")

    # Downgrade r02 back to r01: now 1 r02 -> 1 r01
    target = db.convert_runes_downgrade("r02")
    check(target == "r01", "downgrade returns target code r01")
    check(db.get_stack_count("r02") == 0, "after downgrade r02 count = 0")
    check(db.get_stack_count("r01") == 1, "after downgrade r01 count = 1")

    db.close()

    # ── 10. End-to-end: pulled items survive a full writer round-trip ─
    print("\n=== 10. End-to-end round trip ===")

    db = fresh_db()
    db.push_stack(r01, 50)  # 50 El
    db.push_stack(xa4, 10)  # 10 Deep Worldstone Shard
    db.push_gem(gmr, 30)  # 30 Rubies into pool

    # Pull one of each and replace the originals in the stash
    pulled_r01 = db.pull_stack("r01", 42)
    pulled_xa4 = db.pull_stack("xa4", 7)
    pulled_ruby = db.pull_gem("gmr", 3)

    # Build a new tab5 by replacing the three originals with pulled ones.
    new_tab5 = []
    for it in stash.tabs[5].items:
        if it.item_code == "r01":
            new_tab5.append(pulled_r01)
        elif it.item_code == "xa4":
            new_tab5.append(pulled_xa4)
        elif it.item_code == "gmr":
            new_tab5.append(pulled_ruby)
        else:
            new_tab5.append(it)

    # Match production: from_stash() captures _original_items so the
    # writer uses the byte-splice path instead of the legacy full rebuild.
    writer = D2IWriter.from_stash(orig_bytes, stash)
    writer._tab_items[5] = new_tab5  # noqa: SLF001
    out_bytes = bytes(writer.build())
    tmp = Path(tempfile.mkdtemp()) / "e2e.d2i"
    tmp.write_bytes(out_bytes)
    s2 = D2IParser(tmp).parse()

    for code, expected in [("r01", 42), ("xa4", 7), ("gmr", 3)]:
        it = next(x for x in s2.tabs[5].items if x.item_code == code)
        check(
            display_of(it) == expected,
            f"end-to-end {code}: display={expected}",
            f"got {display_of(it)}",
        )

    db.close()

    # ── Summary ──────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print(f"Total: {passed} PASS, {failed} FAIL ({total} checks)")
    print("=" * 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Test suite for mercenary item parsing (feature/merc-items).

Covers the 'jf' section parser extension that reads a character's
mercenary-equipped items plus their socket children from the D2S file.
These tests exercise three endgame fixtures that each ship with a merc
carrying a different equipment configuration.

- TC49 MrLockhart   - 25 merc items (10 equipped + 15 socketed)
- TC55 FrozenOrbHydra - 21 merc items (9 equipped + 12 socketed)
- TC56 VikingBarbie  - 22 merc items (9 equipped + 13 socketed)

Assertions:
- merc_items is populated with the correct count
- merc_jm_byte_offset is set (non-None) for characters with a merc
- Every merc item has flags, source_data, and item_code populated
- All equipped items have location_id == LOCATION_EQUIPPED (1)
- Item codes match the manually-verified reference lists from the
  initial smoke test (regression guard)
- Characters WITHOUT a merc (TestSorc fixtures) still parse cleanly
  with empty merc_items and merc_jm_byte_offset=None
- The writer preserves the merc section byte-identically on round-trip
  (no items modified)
"""

from __future__ import annotations

import sys
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


# Expected merc item codes (updated 2026-04-06 with extra merc items)
# Order: JM-counted items first, then extra items after JM count.
EXPECTED_MRLOCKHART = [
    "uvg",
    "uhc",
    "umb",
    "amu",
    "uul",
    "ukp",
    # Extra root items after JM count:
    "rin",
    "rin",
    "7ma",
    "72a",
]
EXPECTED_FROZENORBHYDRA = [
    "uvg",
    "ulc",
    "rin",
    "amu",
    "rin",
    "usk",
    # Extra root items after JM count:
    "uul",
    "uvb",
    "7s8",
]
EXPECTED_VIKINGBARBIE = [
    "utb",
    "urn",
    "urs",
    # Extra root items after JM count:
    "rin",
    "xvg",
    "rin",
    "amu",
    "uhc",
    "7br",
]

# Characters WITHOUT a merc (or with merc but no items)
NO_MERC_FIXTURES = [
    "TC01/TestABC.d2s",
    "TC07/TestAmazon.d2s",
    "TC08/TestPaladin.d2s",
    "TC14/TestDruid.d2s",
    "TC38/TestSorc.d2s",
    "TC60/TestSorc.d2s",
]


def main() -> int:
    _init()

    from d2rr_toolkit.parsers.d2s_parser import D2SParser
    from d2rr_toolkit.constants import LOCATION_EQUIPPED

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

    def parse(rel_path: str):
        p = project_root / "tests" / "cases" / rel_path
        return D2SParser(p).parse()

    # ── 1. Characters WITH merc items: TC49 / TC55 / TC56 ──────────────
    print("\n=== 1. MrLockhart (TC49) - 10 merc root items ===")
    char = parse("TC49/MrLockhart.d2s")
    check(len(char.merc_items) == 10, f"merc_items count == 10 (got {len(char.merc_items)})")
    check(
        char.merc_jm_byte_offset is not None,
        f"merc_jm_byte_offset is set (got {char.merc_jm_byte_offset})",
    )
    codes = [it.item_code for it in char.merc_items]
    check(codes == EXPECTED_MRLOCKHART, "merc item codes match expected sequence", f"got {codes}")
    # All merc items must carry usable metadata
    usable = all(it.source_data is not None and it.flags is not None for it in char.merc_items)
    check(usable, "all merc items have source_data + flags")

    print("\n=== 2. FrozenOrbHydra (TC55) - 9 merc root items ===")
    char = parse("TC55/FrozenOrbHydra.d2s")
    check(len(char.merc_items) == 9, f"merc_items count == 9 (got {len(char.merc_items)})")
    check(char.merc_jm_byte_offset is not None, "merc_jm_byte_offset set")
    codes = [it.item_code for it in char.merc_items]
    check(codes == EXPECTED_FROZENORBHYDRA, "codes match", f"got {codes}")

    print("\n=== 3. VikingBarbie (TC56) - 9 merc root items ===")
    char = parse("TC56/VikingBarbie.d2s")
    check(len(char.merc_items) == 9, f"merc_items count == 9 (got {len(char.merc_items)})")
    check(char.merc_jm_byte_offset is not None, "merc_jm_byte_offset set")
    codes = [it.item_code for it in char.merc_items]
    check(codes == EXPECTED_VIKINGBARBIE, "codes match", f"got {codes}")

    # ── 4. Characters WITHOUT merc items ───────────────────────────────
    print("\n=== 4. No-merc characters ===")
    for rel in NO_MERC_FIXTURES:
        p = project_root / "tests" / "cases" / rel
        if not p.exists():
            continue
        char = parse(rel)
        ok = len(char.merc_items) == 0 and char.merc_jm_byte_offset is None
        check(
            ok,
            f"{rel}: empty merc section",
            f"merc_items={len(char.merc_items)} offset={char.merc_jm_byte_offset}",
        )

    # ── 5. Main item list unchanged for merc-bearing characters ────────
    print("\n=== 5. Main item list regression ===")
    mrlockhart = parse("TC49/MrLockhart.d2s")
    check(
        len(mrlockhart.items) == 125,
        f"MrLockhart player items still 125 (got {len(mrlockhart.items)})",
    )
    frozen = parse("TC55/FrozenOrbHydra.d2s")
    check(
        len(frozen.items) == 69, f"FrozenOrbHydra player items still 69 (got {len(frozen.items)})"
    )
    viking = parse("TC56/VikingBarbie.d2s")
    check(
        len(viking.items) == 113, f"VikingBarbie player items still 113 (got {len(viking.items)})"
    )

    # ── 6. Writer produces byte-identical output on unmodified round trip ──
    # As of fix/d2s-writer-vikingbarbie-bytediff, D2SWriter.build() short-
    # circuits to the source bytes verbatim when no inject_items /
    # remove_stored_items calls have happened. This is the strongest
    # possible invariant for pass-through round trips and guarantees merc
    # items survive unchanged.
    print("\n=== 6. Writer byte-identical round trip (unmodified) ===")
    from d2rr_toolkit.writers.d2s_writer import D2SWriter

    for rel in [
        "TC49/MrLockhart.d2s",
        "TC55/FrozenOrbHydra.d2s",
        "TC56/VikingBarbie.d2s",
    ]:
        p = project_root / "tests" / "cases" / rel
        source = p.read_bytes()
        char = parse(rel)
        out = bytes(D2SWriter(source, char).build())
        check(
            out == source,
            f"{rel}: unmodified build() is byte-identical to source",
            f"len source={len(source)}, out={len(out)}",
        )

    # ── 7. Merc items location_id is equipped where expected ──────────
    print("\n=== 7. Merc item location flags ===")
    char = parse("TC49/MrLockhart.d2s")
    # Equipped items should have location_id == LOCATION_EQUIPPED (1).
    # Socket children (runes) have a different location_id.
    equipped = [
        it for it in char.merc_items if it.flags and it.flags.location_id == LOCATION_EQUIPPED
    ]
    check(len(equipped) == 10, f"MrLockhart merc has 10 equipped items (got {len(equipped)})")
    total_children = sum(len(it.socket_children) for it in char.merc_items)
    check(total_children == 15, f"MrLockhart merc has 15 socket children (got {total_children})")

    # ── Summary ─────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print(f"Total: {passed} PASS, {failed} FAIL ({total} checks)")
    print("=" * 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())


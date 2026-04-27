#!/usr/bin/env python3
"""Test suite for extended CharacterHeader fields (feature/character-header-fields).

Verifies the new header fields added for the character-select screen:
  - status_byte, is_hardcore, died_flag, is_dead (computed), is_expansion
  - progression, highest_difficulty_completed
  - gender (class-based lookup)
  - title (computed from progression + is_hardcore + gender)

Verified against 7 real D2S files:
  HCLives         (HC Warlock, level 1, alive)
  HCDied          (HC Warlock, level 1, permanently dead)
  MrLockhart      (SC Warlock, Patriarch)
  FrozenOrbHydra  (SC Sorceress, Matriarch)
  VikingBarbie    (SC Sorceress, Matriarch)
  StraFoHdin      (SC Paladin, Patriarch)
  AAAAA           (SC Warlock, Patriarch) - test copy

Status byte bit layout (BINARY_VERIFIED):
  bit 2 (0x04): Hardcore
  bit 3 (0x08): Died flag (HC=permadead, SC=historical "has died")

Expansion is implicit in D2R v105 (always True).
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
    from d2rr_toolkit.cli import _load_game_data  # noqa: E402

    _load_game_data(project_root / "tests" / "cases" / "TC49" / "MrLockhart.d2s")


def main() -> int:
    # Load game data via CLI helper (falls back to d2rr_toolkit.cli)
    try:
        from d2rr_toolkit.cli import _load_game_data
    except ImportError:
        from d2rr_toolkit.cli import _load_game_data
    import logging

    logging.basicConfig(level=logging.ERROR)
    _load_game_data(project_root / "tests" / "cases" / "TC49" / "MrLockhart.d2s")

    from d2rr_toolkit.parsers.d2s_parser import D2SParser
    from d2rr_toolkit.models.character import CharacterHeader

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

    # ── Locate test D2S files ──────────────────────────────────────────
    # Each character lives in its dedicated TC directory; the project
    # root is no longer scanned (loose copies were removed during repo
    # hygiene).
    name_to_tc = {
        "MrLockhart": "TC49",
        "FrozenOrbHydra": "TC55",
        "VikingBarbie": "TC56",
        "StraFoHdin": "TC71",
        "HCLives": "TC71",
        "HCDied": "TC71",
    }
    char_files: dict[str, Path] = {}
    for name, tc in name_to_tc.items():
        candidate = project_root / "tests" / "cases" / tc / f"{name}.d2s"
        if candidate.exists():
            char_files[name] = candidate
    aaaaa = project_root / "tests" / "cases" / "TC49" / "AAAAA.d2s"
    if aaaaa.exists():
        char_files["AAAAA"] = aaaaa

    # ── 1. Parse all 5 characters ──────────────────────────────────────
    print("\n=== 1. Parse characters ===")
    chars = {}
    # Expected internal character_name per test file key.
    # AAAAA.d2s is a test copy that internally still holds the MrLockhart name.
    expected_names = {
        "MrLockhart": "MrLockhart",
        "FrozenOrbHydra": "FrozenOrbHydra",
        "VikingBarbie": "VikingBarbie",
        "StraFoHdin": "StraFoHdin",
        "HCLives": "HCLives",
        "HCDied": "HCDied",
        "AAAAA": "MrLockhart",  # AAAAA.d2s is a renamed copy
    }
    for name, path in char_files.items():
        char = D2SParser(path).parse()
        chars[name] = char
        expected = expected_names.get(name, name)
        check(
            char.header.character_name == expected,
            f"{name}: name parsed correctly (expected {expected!r})",
        )

    # ── 2. Progression and difficulty ──────────────────────────────────
    print("\n=== 2. Progression and difficulty ===")
    # Endgame chars (Patriarch/Matriarch) = prog 15
    endgame_chars = ("MrLockhart", "FrozenOrbHydra", "VikingBarbie", "StraFoHdin", "AAAAA")
    for name in endgame_chars:
        if name not in chars:
            continue
        h = chars[name].header
        check(h.progression == 15, f"{name}: progression=15 (Hell completed)")
        check(h.highest_difficulty_completed == 3, f"{name}: highest_difficulty_completed=3")
    # Brand new HC chars (level 1) = prog 0
    for name in ("HCLives", "HCDied"):
        if name not in chars:
            continue
        h = chars[name].header
        check(h.progression == 0, f"{name}: progression=0 (brand new char)")
        check(h.highest_difficulty_completed == 0, f"{name}: highest_difficulty_completed=0")

    # ── 3. Status flags: SC endgame chars ──────────────────────────────
    print("\n=== 3. Status flags: SC endgame chars ===")
    for name in endgame_chars:
        if name not in chars:
            continue
        h = chars[name].header
        check(h.is_expansion is True, f"{name}: is_expansion=True")
        check(h.is_hardcore is False, f"{name}: is_hardcore=False (user confirmed SC)")
        check(h.is_dead is False, f"{name}: is_dead=False (SC: never permadead)")
        check(h.died_flag is True, f"{name}: died_flag=True (SC died at some point)")
        check(h.status_byte == 0x08, f"{name}: status_byte=0x08 (died_flag only)")

    # ── 3b. Status flags: HC chars ─────────────────────────────────────
    print("\n=== 3b. Status flags: HC chars ===")
    if "HCLives" in chars:
        h = chars["HCLives"].header
        check(h.is_hardcore is True, "HCLives: is_hardcore=True")
        check(h.died_flag is False, "HCLives: died_flag=False")
        check(h.is_dead is False, "HCLives: is_dead=False (HC alive)")
        check(h.status_byte == 0x04, "HCLives: status_byte=0x04 (HC only)")
    if "HCDied" in chars:
        h = chars["HCDied"].header
        check(h.is_hardcore is True, "HCDied: is_hardcore=True")
        check(h.died_flag is True, "HCDied: died_flag=True")
        check(h.is_dead is True, "HCDied: is_dead=True (HC permadead)")
        check(h.status_byte == 0x0C, "HCDied: status_byte=0x0C (HC + died_flag)")

    # ── 4. Gender mapping ──────────────────────────────────────────────
    print("\n=== 4. Gender mapping ===")
    expected_genders = {
        "MrLockhart": "male",  # Warlock
        "FrozenOrbHydra": "female",  # Sorceress
        "VikingBarbie": "female",  # Sorceress
        "StraFoHdin": "male",  # Paladin
        "AAAAA": "male",  # Warlock
        "HCLives": "male",  # Warlock
        "HCDied": "male",  # Warlock
    }
    for name, expected in expected_genders.items():
        if name in chars:
            actual = chars[name].header.gender
            check(actual == expected, f"{name}: gender={actual} (expected {expected})")

    # ── 5. Title computation ───────────────────────────────────────────
    print("\n=== 5. Title computation ===")
    expected_titles = {
        "MrLockhart": "Patriarch",  # SC + prog=15 + male (Warlock)
        "FrozenOrbHydra": "Matriarch",  # SC + prog=15 + female (Sorceress)
        "VikingBarbie": "Matriarch",  # SC + prog=15 + female (Sorceress)
        "StraFoHdin": "Patriarch",  # SC + prog=15 + male (Paladin)
        "AAAAA": "Patriarch",  # SC + prog=15 + male (Warlock)
        "HCLives": "",  # HC + prog=0 -> no title
        "HCDied": "",  # HC + prog=0 -> no title
    }
    for name, expected in expected_titles.items():
        if name in chars:
            actual = chars[name].header.title
            check(actual == expected, f"{name}: title={actual!r} (expected {expected!r})")

    # ── 6. Title logic edge cases (unit tests on CharacterHeader) ──────
    print("\n=== 6. Title logic edge cases ===")

    def mk_header(progression=0, is_hardcore=False, died_flag=False, character_class=3):
        return CharacterHeader(
            version=105,
            file_size=0,
            checksum=0,
            character_name="Test",
            character_class=character_class,
            character_class_name="Paladin",
            level=1,
            status_byte=0,
            is_hardcore=is_hardcore,
            died_flag=died_flag,
            is_expansion=True,
            progression=progression,
        )

    # SC no title
    check(mk_header(progression=0).title == "", "SC prog=0 -> no title")
    check(mk_header(progression=4).title == "", "SC prog=4 -> no title")
    # SC tiers
    check(mk_header(progression=5, character_class=3).title == "Slayer", "SC prog=5 male -> Slayer")
    check(
        mk_header(progression=5, character_class=1).title == "Slayer", "SC prog=5 female -> Slayer"
    )
    check(
        mk_header(progression=10, character_class=3).title == "Champion", "SC prog=10 -> Champion"
    )
    check(
        mk_header(progression=15, character_class=3).title == "Patriarch",
        "SC prog=15 male -> Patriarch",
    )
    check(
        mk_header(progression=15, character_class=1).title == "Matriarch",
        "SC prog=15 female -> Matriarch",
    )
    check(
        mk_header(progression=14, character_class=3).title == "Champion",
        "SC prog=14 -> Champion (boundary)",
    )
    check(
        mk_header(progression=9, character_class=3).title == "Slayer",
        "SC prog=9 -> Slayer (boundary)",
    )
    # HC tiers (based on classic D2 bit layout - PENDING HC VERIFICATION)
    check(mk_header(progression=5, is_hardcore=True).title == "Destroyer", "HC prog=5 -> Destroyer")
    check(
        mk_header(progression=10, is_hardcore=True).title == "Conqueror", "HC prog=10 -> Conqueror"
    )
    check(
        mk_header(progression=15, is_hardcore=True, character_class=3).title == "Guardian",
        "HC prog=15 male -> Guardian",
    )
    check(
        mk_header(progression=15, is_hardcore=True, character_class=1).title == "Guardian",
        "HC prog=15 female -> Guardian (gender-neutral)",
    )
    check(mk_header(progression=0, is_hardcore=True).title == "", "HC prog=0 -> no title")

    # ── 6b. is_dead computed property logic ────────────────────────────
    print("\n=== 6b. is_dead computed logic ===")
    check(
        mk_header(is_hardcore=False, died_flag=False).is_dead is False,
        "SC + no died_flag -> not dead",
    )
    check(
        mk_header(is_hardcore=False, died_flag=True).is_dead is False,
        "SC + died_flag -> NOT dead (historical)",
    )
    check(
        mk_header(is_hardcore=True, died_flag=False).is_dead is False,
        "HC + no died_flag -> not dead (alive)",
    )
    check(
        mk_header(is_hardcore=True, died_flag=True).is_dead is True,
        "HC + died_flag -> DEAD (permadead)",
    )

    # ── 7. highest_difficulty_completed boundaries ─────────────────────
    print("\n=== 7. highest_difficulty_completed boundaries ===")
    check(mk_header(progression=0).highest_difficulty_completed == 0, "prog=0 -> diff=0")
    check(mk_header(progression=4).highest_difficulty_completed == 0, "prog=4 -> diff=0")
    check(mk_header(progression=5).highest_difficulty_completed == 1, "prog=5 -> diff=1 (Normal)")
    check(mk_header(progression=9).highest_difficulty_completed == 1, "prog=9 -> diff=1")
    check(
        mk_header(progression=10).highest_difficulty_completed == 2, "prog=10 -> diff=2 (Nightmare)"
    )
    check(mk_header(progression=14).highest_difficulty_completed == 2, "prog=14 -> diff=2")
    check(mk_header(progression=15).highest_difficulty_completed == 3, "prog=15 -> diff=3 (Hell)")

    # ── 8. Gender mapping edge cases ───────────────────────────────────
    print("\n=== 8. Gender mapping edge cases ===")
    check(mk_header(character_class=0).gender == "female", "class 0 Amazon -> female")
    check(mk_header(character_class=1).gender == "female", "class 1 Sorceress -> female")
    check(mk_header(character_class=2).gender == "male", "class 2 Necromancer -> male")
    check(mk_header(character_class=3).gender == "male", "class 3 Paladin -> male")
    check(mk_header(character_class=4).gender == "male", "class 4 Barbarian -> male")
    check(mk_header(character_class=5).gender == "male", "class 5 Druid -> male")
    check(mk_header(character_class=6).gender == "female", "class 6 Assassin -> female")
    check(mk_header(character_class=7).gender == "male", "class 7 Warlock -> male (Reimagined)")
    check(mk_header(character_class=99).gender == "male", "class 99 unknown -> male (default)")

    # ── 9. Existing fields unchanged (backwards compatibility) ─────────
    print("\n=== 9. Backwards compatibility ===")
    if "MrLockhart" in chars:
        h = chars["MrLockhart"].header
        check(h.version == 105, "version still present")
        check(h.level == 98, "level still correct")
        check(h.character_class == 7, "character_class still correct (7=Warlock)")
        check(h.character_class_name == "Warlock", "character_class_name still correct")
        check(h.file_size > 0, "file_size still populated")

    # ── Summary ────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"Total: {passed} PASS, {failed} FAIL ({total} checks)")
    print(f"{'=' * 60}")
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())

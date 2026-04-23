#!/usr/bin/env python3
"""Unit tests for d2rr_toolkit.database.modes.

Covers mode detection from parsed characters and stash filenames, the
default path builders, and the two mode-specific exception types. No
D2R installation required - uses synthetic ParsedCharacter stand-ins
so we can test even edge cases the live game never produces.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _make_character(is_hardcore: bool):
    """Build a ParsedCharacter with just the header bit under test."""
    from d2rr_toolkit.models.character import CharacterHeader, ParsedCharacter

    header = CharacterHeader.model_construct(is_hardcore=is_hardcore)
    return ParsedCharacter.model_construct(header=header)


def main() -> int:
    from d2rr_toolkit.database.modes import (
        DatabaseModeMismatchError,
        GameModeError,
        HARDCORE,
        SOFTCORE,
        default_archive_db_name,
        default_archive_db_path,
        mode_from_character,
        mode_from_stash_filename,
    )

    passed = 0
    failed = 0

    def check(cond: bool, name: str, detail: str = "") -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"  PASS  {name}")
        else:
            failed += 1
            suffix = f" -- {detail}" if detail else ""
            print(f"  FAIL  {name}{suffix}")

    # -- Constants ----------------------------------------------------------
    check(SOFTCORE == "softcore", "SOFTCORE constant")
    check(HARDCORE == "hardcore", "HARDCORE constant")

    # -- Mode from character ------------------------------------------------
    sc_char = _make_character(is_hardcore=False)
    hc_char = _make_character(is_hardcore=True)
    check(mode_from_character(sc_char) == SOFTCORE, "softcore char -> softcore")
    check(mode_from_character(hc_char) == HARDCORE, "hardcore char -> hardcore")

    # -- Mode from stash filename: canonical game filenames ----------------
    check(
        mode_from_stash_filename("ModernSharedStashSoftCoreV2.d2i") == SOFTCORE,
        "canonical softcore stash filename",
    )
    check(
        mode_from_stash_filename("ModernSharedStashHardCoreV2.d2i") == HARDCORE,
        "canonical hardcore stash filename",
    )

    # -- Case-insensitivity + Path input -----------------------------------
    check(
        mode_from_stash_filename(Path("modernsharedstashsoftcorev2.d2i")) == SOFTCORE,
        "lowercase stash filename",
    )
    check(
        mode_from_stash_filename(Path("/tmp/MODERN_SHARED_STASH_HARDCORE_V2.d2i")) == HARDCORE,
        "uppercase hardcore with full path",
    )

    # -- Renamed backups still resolve --------------------------------------
    check(
        mode_from_stash_filename("backup_softcore_2026.d2i") == SOFTCORE,
        "custom-renamed softcore backup",
    )

    # -- Ambiguous filename raises -----------------------------------------
    try:
        mode_from_stash_filename("stash.d2i")
    except GameModeError:
        check(True, "ambiguous filename -> GameModeError")
    else:
        check(False, "ambiguous filename -> GameModeError", "did not raise")

    # -- Filename containing BOTH hints raises -----------------------------
    try:
        mode_from_stash_filename("softcore_and_hardcore.d2i")
    except GameModeError:
        check(True, "both hints -> GameModeError")
    else:
        check(False, "both hints -> GameModeError", "did not raise")

    # -- Default archive DB filenames --------------------------------------
    check(
        default_archive_db_name(SOFTCORE) == "d2rr_archive_softcore.db",
        "softcore archive filename",
    )
    check(
        default_archive_db_name(HARDCORE) == "d2rr_archive_hardcore.db",
        "hardcore archive filename",
    )
    # -- Default archive DB paths (with explicit base_dir) -----------------
    base = Path("/tmp/d2rr_toolkit_test")
    check(
        default_archive_db_path(SOFTCORE, base_dir=base) == base / "d2rr_archive_softcore.db",
        "softcore archive path with base_dir",
    )
    check(
        default_archive_db_path(HARDCORE, base_dir=base) == base / "d2rr_archive_hardcore.db",
        "hardcore archive path with base_dir",
    )

    # -- Default base_dir resolves to the D2RR save directory --------------
    # The archive DB co-locates with the Reimagined-modded save files so
    # "back up mods/ReimaginedThree" also backs up the archive.
    # D2RR_SAVE_DIR overrides the Windows heuristic on every platform
    # (test uses it to avoid depending on the OS running the suite).
    import os

    fake_save_dir = Path("/tmp/fake_d2r_save_dir")
    old_env = os.environ.get("D2RR_SAVE_DIR")
    os.environ["D2RR_SAVE_DIR"] = str(fake_save_dir)
    try:
        default_path = default_archive_db_path(SOFTCORE)
        check(
            default_path.parent == fake_save_dir,
            "default base_dir resolves from D2RR_SAVE_DIR",
            f"got {default_path.parent}",
        )
        check(
            default_path.name == "d2rr_archive_softcore.db",
            "default filename stays mode-specific",
            default_path.name,
        )
    finally:
        if old_env is None:
            del os.environ["D2RR_SAVE_DIR"]
        else:
            os.environ["D2RR_SAVE_DIR"] = old_env

    # -- SC and HC paths are always distinct ------------------------------
    check(
        default_archive_db_path(SOFTCORE, base_dir=base)
        != default_archive_db_path(HARDCORE, base_dir=base),
        "SC and HC archive paths are distinct",
    )

    # -- Exception hierarchy -----------------------------------------------
    check(
        issubclass(GameModeError, ValueError),
        "GameModeError is a ValueError",
    )
    check(
        issubclass(DatabaseModeMismatchError, RuntimeError),
        "DatabaseModeMismatchError is a RuntimeError",
    )

    print("-" * 72)
    print(f"Total: {passed} PASS, {failed} FAIL")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())


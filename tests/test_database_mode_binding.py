#!/usr/bin/env python3
"""Integration tests for the SC/HC meta-tag protection on both DBs.

Verifies:
- A fresh ItemDatabase writes its mode into the meta table.
- Opening the same file with a different mode raises
  DatabaseModeMismatchError.
- Section5Database shares the meta table - opening it after an
  ItemDatabase has bound the mode is consistent.
- open_item_db / open_section5_db factories build separate files for
  softcore and hardcore.
- Re-opening a database with the same mode is a no-op (idempotent).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def main() -> int:
    from d2rr_toolkit.database.item_db import ItemDatabase, open_item_db
    from d2rr_toolkit.database.section5_db import (
        Section5Database,
        open_section5_db,
    )
    from d2rr_toolkit.database.modes import (
        DatabaseModeMismatchError,
        HARDCORE,
        SOFTCORE,
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

    tmp = Path(tempfile.mkdtemp())

    # -- Test 1: fresh softcore ItemDatabase tags itself ------------------
    sc_path = tmp / "sc.db"
    db = ItemDatabase(sc_path, mode=SOFTCORE)
    check(db.mode == SOFTCORE, "fresh ItemDatabase binds softcore")
    db.close()

    # -- Test 2: reopening with same mode is idempotent -------------------
    db = ItemDatabase(sc_path, mode=SOFTCORE)
    check(db.mode == SOFTCORE, "reopen with same mode is idempotent")
    db.close()

    # -- Test 3: reopening with WRONG mode raises -------------------------
    try:
        ItemDatabase(sc_path, mode=HARDCORE)
    except DatabaseModeMismatchError as e:
        check(
            "softcore" in str(e) and "hardcore" in str(e),
            "opening SC file as HC raises DatabaseModeMismatchError",
            str(e)[:80],
        )
    else:
        check(
            False, "opening SC file as HC raises DatabaseModeMismatchError", "no exception raised"
        )

    # -- Test 4: Section5Database shares the meta tag ---------------------
    s5 = Section5Database(sc_path, mode=SOFTCORE)
    check(s5.mode == SOFTCORE, "Section5Database inherits softcore tag from shared file")
    s5.close()

    # -- Test 5: Section5Database also refuses wrong mode -----------------
    try:
        Section5Database(sc_path, mode=HARDCORE)
    except DatabaseModeMismatchError:
        check(True, "Section5Database refuses HC open on SC file")
    else:
        check(False, "Section5Database refuses HC open on SC file")

    # -- Test 6: factories build distinct SC/HC files ---------------------
    sc_db = open_item_db(SOFTCORE, base_dir=tmp)
    hc_db = open_item_db(HARDCORE, base_dir=tmp)
    check(
        sc_db._path != hc_db._path,
        "open_item_db SC and HC get different files",
        f"sc={sc_db._path.name} hc={hc_db._path.name}",
    )
    check(
        sc_db.mode == SOFTCORE and hc_db.mode == HARDCORE,
        "factories return correctly-tagged databases",
    )
    sc_db.close()
    hc_db.close()

    # -- Test 7: factory respects explicit db_path override ---------------
    override = tmp / "custom_sc.db"
    db = open_item_db(SOFTCORE, db_path=override)
    check(db._path == override, "explicit db_path overrides mode-derived name")
    db.close()

    # -- Test 8: Default mode is softcore when unspecified ----------------
    default_path = tmp / "defaultmode.db"
    db = ItemDatabase(default_path)  # no mode kwarg
    check(db.mode == SOFTCORE, "unspecified mode defaults to softcore (backwards compat)")
    db.close()

    # -- Test 9: open_section5_db factory sanity --------------------------
    s5 = open_section5_db(HARDCORE, base_dir=tmp)
    check(s5.mode == HARDCORE, "open_section5_db returns HC-bound instance")
    s5.close()

    # -- Test 10: SC and HC paths have distinct names ---------------------
    sc2 = open_item_db(SOFTCORE, base_dir=tmp)
    hc2 = open_item_db(HARDCORE, base_dir=tmp)
    check("softcore" in sc2._path.name, "SC filename contains 'softcore'", sc2._path.name)
    check("hardcore" in hc2._path.name, "HC filename contains 'hardcore'", hc2._path.name)
    sc2.close()
    hc2.close()

    print("-" * 72)
    print(f"Total: {passed} PASS, {failed} FAIL")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

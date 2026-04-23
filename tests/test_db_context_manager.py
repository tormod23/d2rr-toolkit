"""ItemDatabase / Section5Database support `with`-block usage.

The exit handler must close the underlying SQLite connection even
when the body raises. Leaving the connection open would eventually
exhaust file handles under repeated CLI invocations.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from d2rr_toolkit.database import item_db as item_db_module
from d2rr_toolkit.database import section5_db as section5_db_module
from d2rr_toolkit.database.item_db import ItemDatabase
from d2rr_toolkit.database.section5_db import Section5Database


def test_item_db_closes_on_exception(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        with ItemDatabase(tmp_path / "x.db", mode=item_db_module.SOFTCORE) as db:
            assert db.mode is not None
            raise RuntimeError("boom")
    # Connection must be closed; subsequent use raises.
    with pytest.raises(sqlite3.ProgrammingError):
        db._conn.execute("SELECT 1")  # noqa: SLF001


def test_item_db_closes_on_happy_path(tmp_path: Path) -> None:
    with ItemDatabase(tmp_path / "x.db", mode=item_db_module.SOFTCORE) as db:
        pass
    with pytest.raises(sqlite3.ProgrammingError):
        db._conn.execute("SELECT 1")  # noqa: SLF001


def test_section5_db_closes_on_exception(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        with Section5Database(
            tmp_path / "s5.db", mode=section5_db_module.SOFTCORE
        ) as db:
            raise RuntimeError("boom")
    with pytest.raises(sqlite3.ProgrammingError):
        db._conn.execute("SELECT 1")  # noqa: SLF001

"""ItemDatabase._migrate must fail-loud on ALTER failures.

We exercise the fail-loud path by wrapping a read-only SQLite
connection whose ``execute`` reports the optional columns as missing
from ``PRAGMA table_info`` and rejects every ALTER with
``sqlite3.OperationalError``. The exception must propagate out of
``_migrate``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from d2rr_toolkit.database import item_db as item_db_module
from d2rr_toolkit.database.item_db import ItemDatabase


def _seed_db(path: Path) -> None:
    db = ItemDatabase(path, mode=item_db_module.SOFTCORE)
    db.close()


class _FakeROConn:
    """Tiny connection shim: PRAGMA returns no columns, ALTER raises."""

    class _EmptyCursor:
        def fetchall(self) -> list[tuple]:
            return []

    def execute(self, sql: str, *args, **kwargs):
        stripped = sql.strip().upper()
        if stripped.startswith("PRAGMA TABLE_INFO"):
            return _FakeROConn._EmptyCursor()
        if stripped.startswith("ALTER"):
            raise sqlite3.OperationalError("attempt to write a readonly database")
        raise AssertionError(f"unexpected SQL in test: {sql!r}")

    def commit(self) -> None:
        raise AssertionError("commit should not be reached on failed migration")

    def close(self) -> None:
        pass


def test_migrate_raises_on_readonly_db(tmp_path: Path) -> None:
    db = object.__new__(ItemDatabase)
    db._conn = _FakeROConn()  # type: ignore[attr-defined]
    db._mode = item_db_module.SOFTCORE  # type: ignore[attr-defined]
    with pytest.raises(sqlite3.OperationalError) as excinfo:
        db._migrate()
    # The exception text must identify it as the readonly-DB failure,
    # not e.g. a Python AttributeError from something else going wrong.
    assert "readonly" in str(excinfo.value).lower()


def test_migrate_is_noop_when_columns_present(tmp_path: Path) -> None:
    """Freshly seeded DB already has every column; a second _migrate
    call must complete without raising or doing any ALTER."""
    db_path = tmp_path / "items.db"
    _seed_db(db_path)
    db = ItemDatabase(db_path, mode=item_db_module.SOFTCORE)
    try:
        db._migrate()  # must not raise
    finally:
        db.close()

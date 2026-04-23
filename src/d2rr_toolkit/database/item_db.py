"""SQLite Item Database - the Infinite Archive.

Stores items extracted from D2S/D2I save files with both:
- Display attributes (searchable): name, quality, properties, etc.
- Binary blob (for writing back): raw item bytes for exact restoration.

Usage:
    db = ItemDatabase("items.db")
    db.store_item(item, source_file="char.d2s", source_tab=-1)
    results = db.search(name="Blade of Ali Baba")
    item_row = db.get_item(1)
    db.mark_restored(1)
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from d2rr_toolkit.database.modes import (
    GameMode,
    META_SCHEMA_SQL,
    SOFTCORE,
    bind_database_mode,
    default_archive_db_path,
)
from d2rr_toolkit.models.character import ParsedItem

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Display attributes (searchable)
    item_code TEXT NOT NULL,
    item_name TEXT NOT NULL DEFAULT '',
    quality INTEGER NOT NULL DEFAULT 0,
    quality_name TEXT NOT NULL DEFAULT '',
    item_level INTEGER NOT NULL DEFAULT 0,
    is_ethereal INTEGER NOT NULL DEFAULT 0,
    is_socketed INTEGER NOT NULL DEFAULT 0,
    is_runeword INTEGER NOT NULL DEFAULT 0,
    properties_json TEXT NOT NULL DEFAULT '[]',
    -- Binary blob (for writing back). For socketed items this is the
    -- concatenated blobs of parent + all socket children.
    source_data BLOB NOT NULL,
    -- Number of socket children included in source_data (0 = no children).
    child_count INTEGER NOT NULL DEFAULT 0,
    -- GUI display hints (computed at store time, avoid re-parsing blobs)
    sprite_key TEXT NOT NULL DEFAULT '',
    invtransform TEXT NOT NULL DEFAULT '',
    -- Metadata
    source_file TEXT NOT NULL DEFAULT '',
    source_tab INTEGER NOT NULL DEFAULT -1,
    extracted_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'available'
);

CREATE INDEX IF NOT EXISTS idx_items_name ON items(item_name);
CREATE INDEX IF NOT EXISTS idx_items_code ON items(item_code);
CREATE INDEX IF NOT EXISTS idx_items_quality ON items(quality);
CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
"""

_MIGRATION_ADD_SPRITE_KEY = "ALTER TABLE items ADD COLUMN sprite_key TEXT NOT NULL DEFAULT ''"
_MIGRATION_ADD_INVTRANSFORM = "ALTER TABLE items ADD COLUMN invtransform TEXT NOT NULL DEFAULT ''"
_MIGRATION_ADD_CHILD_COUNT = "ALTER TABLE items ADD COLUMN child_count INTEGER NOT NULL DEFAULT 0"


@dataclass
class StoredItem:
    """An item stored in the database."""

    id: int
    item_code: str
    item_name: str
    quality: int
    quality_name: str
    item_level: int
    is_ethereal: bool
    is_socketed: bool
    is_runeword: bool
    properties_json: str
    source_data: bytes
    child_count: int
    sprite_key: str
    invtransform: str
    source_file: str
    source_tab: int
    extracted_at: str
    status: str


class ItemDatabase:
    """SQLite database for the Infinite Archive.

    Each database is tagged with a :class:`~d2rr_toolkit.database.modes.GameMode`
    (``softcore`` or ``hardcore``) the first time it is opened. Later opens
    are validated against the caller's expected mode; a mismatch raises
    :class:`DatabaseModeMismatchError` instead of silently mixing items
    from the two ladders.

    Args:
        db_path: Filesystem path to the SQLite file. The two modes should
            live in physically separate files (see :func:`open_item_db`);
            the meta-table validation is a belt-and-braces check, not a
            replacement for filename segregation.
        mode: Expected game mode. If omitted, the database is treated as
            softcore for backwards compatibility with pre-SC/HC code that
            wrote the archive DB without a mode tag.
    """

    def __init__(
        self,
        db_path: str | Path,
        mode: GameMode | None = None,
    ) -> None:
        self._path = Path(db_path)
        self._conn = sqlite3.connect(str(self._path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.executescript(META_SCHEMA_SQL)
        self._migrate()
        # Default to softcore if no mode is given - preserves the legacy
        # API used by older scripts and tests that don't know about the
        # SC/HC split yet.
        self._mode: GameMode = bind_database_mode(
            self._conn,
            mode if mode is not None else SOFTCORE,
            db_path=self._path,
        )
        logger.info(
            "ItemDatabase opened: %s [mode=%s]",
            self._path,
            self._mode,
        )

    @property
    def mode(self) -> GameMode:
        """Return the game mode this database is bound to."""
        return self._mode

    def _migrate(self) -> None:
        """Run schema migrations for columns added after initial release.

        Migrations are fail-loud: a failed ``ALTER TABLE`` raises
        :class:`sqlite3.OperationalError` out of ``ItemDatabase(...)``.
        The pre-check on ``PRAGMA table_info`` filters the benign
        "column already exists" case, so the catch only fires on
        genuinely exceptional conditions (disk full, lock contention,
        read-only filesystem, corrupt DB).
        """
        # Check which optional columns already exist.
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(items)").fetchall()}
        for column, ddl in (
            ("sprite_key", _MIGRATION_ADD_SPRITE_KEY),
            ("invtransform", _MIGRATION_ADD_INVTRANSFORM),
            ("child_count", _MIGRATION_ADD_CHILD_COUNT),
        ):
            if column in columns:
                continue
            try:
                self._conn.execute(ddl)
                self._conn.commit()
                logger.info(
                    "Migration: added %s column to items table",
                    column,
                )
            except sqlite3.OperationalError as exc:
                logger.error(
                    "Schema migration failed (ALTER TABLE items ADD COLUMN %s): %s. "
                    "Database is in an inconsistent state; operations will fail.",
                    column,
                    exc,
                )
                raise

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    def __enter__(self) -> "ItemDatabase":
        """Support ``with ItemDatabase(...) as db:`` usage."""
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        """Close the connection on context-manager exit, even on error."""
        self.close()

    def store_item(
        self,
        item: ParsedItem,
        display_name: str = "",
        source_file: str = "",
        source_tab: int = -1,
        sprite_key: str = "",
        invtransform: str = "",
        child_count: int = 0,
    ) -> int:
        """Store an item in the database.

        Args:
            item: ParsedItem with source_data set.
            display_name: Human-readable item name for searching.
            source_file: Path of the save file the item was extracted from.
            source_tab: Tab index (-1 for d2s items).
            sprite_key: Stable sprite key (from _sprite_key_for_item) for
                        the GUI to load the correct sprite without re-parsing.

        Returns:
            Database row ID of the stored item.

        Raises:
            ValueError: If item has no source_data.
        """
        if item.source_data is None:
            raise ValueError(f"Item '{item.item_code}' has no source_data")

        ext = item.extended
        props = [
            {"stat_id": p.get("stat_id"), "name": p.get("name"), "value": p.get("value")}
            for p in (item.magical_properties or [])
        ]

        cursor = self._conn.execute(
            """INSERT INTO items (
                item_code, item_name, quality, quality_name, item_level,
                is_ethereal, is_socketed, is_runeword,
                properties_json, source_data, child_count, sprite_key, invtransform,
                source_file, source_tab, extracted_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item.item_code,
                display_name,
                ext.quality if ext else 0,
                ext.quality_name if ext else "",
                ext.item_level if ext else 0,
                int(item.flags.ethereal),
                int(item.flags.socketed),
                int(item.flags.runeword),
                json.dumps(props),
                item.source_data,
                child_count,
                sprite_key,
                invtransform,
                str(source_file),
                source_tab,
                datetime.now().isoformat(),
                "available",
            ),
        )
        self._conn.commit()
        row_id = cursor.lastrowid
        logger.info("Stored item '%s' (%s) as DB id=%d", display_name, item.item_code, row_id)
        return row_id

    def get_item(self, item_id: int) -> StoredItem | None:
        """Retrieve an item by ID."""
        row = self._conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_stored_item(row)

    def list_items(self, status: str = "available") -> list[StoredItem]:
        """List all items with the given status."""
        rows = self._conn.execute(
            "SELECT * FROM items WHERE status = ? ORDER BY extracted_at DESC", (status,)
        ).fetchall()
        return [self._row_to_stored_item(r) for r in rows]

    def search(
        self,
        name: str | None = None,
        item_code: str | None = None,
        quality: int | None = None,
        status: str = "available",
    ) -> list[StoredItem]:
        """Search items by attributes."""
        conditions = ["status = ?"]
        params: list = [status]
        if name:
            conditions.append("item_name LIKE ?")
            params.append(f"%{name}%")
        if item_code:
            conditions.append("item_code = ?")
            params.append(item_code)
        if quality is not None:
            conditions.append("quality = ?")
            params.append(quality)

        query = f"SELECT * FROM items WHERE {' AND '.join(conditions)} ORDER BY extracted_at DESC"
        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_stored_item(r) for r in rows]

    def mark_restored(self, item_id: int) -> None:
        """Mark an item as restored (no longer available for extraction)."""
        self._conn.execute("UPDATE items SET status = 'restored' WHERE id = ?", (item_id,))
        self._conn.commit()
        logger.info("Item id=%d marked as restored", item_id)

    def delete_item(self, item_id: int) -> None:
        """Permanently delete an item from the database."""
        self._conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
        self._conn.commit()

    def count(self, status: str = "available") -> int:
        """Count items with the given status."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM items WHERE status = ?", (status,)
        ).fetchone()
        return row[0] if row else 0

    @staticmethod
    def _row_to_stored_item(row: sqlite3.Row) -> StoredItem:
        """Convert a sqlite3 row tuple into a :class:`StoredItem` dataclass."""
        return StoredItem(
            id=row["id"],
            item_code=row["item_code"],
            item_name=row["item_name"],
            quality=row["quality"],
            quality_name=row["quality_name"],
            item_level=row["item_level"],
            is_ethereal=bool(row["is_ethereal"]),
            is_socketed=bool(row["is_socketed"]),
            is_runeword=bool(row["is_runeword"]),
            properties_json=row["properties_json"],
            source_data=row["source_data"],
            child_count=row["child_count"] if "child_count" in row.keys() else 0,
            sprite_key=row["sprite_key"] if "sprite_key" in row.keys() else "",
            invtransform=row["invtransform"] if "invtransform" in row.keys() else "",
            source_file=row["source_file"],
            source_tab=row["source_tab"],
            extracted_at=row["extracted_at"],
            status=row["status"],
        )


def open_item_db(
    mode: GameMode,
    *,
    base_dir: Path | None = None,
    db_path: Path | None = None,
) -> ItemDatabase:
    """Open (or create) the mode-specific Infinite Archive database.

    This is the preferred entry point for all CLI and service code: it
    builds the canonical mode-specific filename, constructs the
    :class:`ItemDatabase` with the right mode tag, and guarantees that
    SoftCore and HardCore items end up in separate files.

    Args:
        mode: ``"softcore"`` or ``"hardcore"``. Usually derived from a
            parsed character via
            :func:`d2rr_toolkit.database.modes.mode_from_character`, or
            from a stash filename via
            :func:`d2rr_toolkit.database.modes.mode_from_stash_filename`.
        base_dir: Directory in which to place the DB file. Defaults to
            the current working directory - matching legacy behaviour.
            Ignored when ``db_path`` is given.
        db_path: Explicit path override for advanced use cases. When
            supplied, the mode parameter is still validated against the
            DB's stored meta tag, so passing the wrong path for the
            expected mode raises :class:`DatabaseModeMismatchError`.

    Returns:
        An opened :class:`ItemDatabase` bound to *mode*.

    Raises:
        DatabaseModeMismatchError: If the target file already exists
            and carries a different mode tag.
    """
    if db_path is None:
        db_path = default_archive_db_path(mode, base_dir=base_dir)
    return ItemDatabase(db_path, mode=mode)


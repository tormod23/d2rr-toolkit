"""
src/d2rr_toolkit/game_data/hireling.py
======================================
Loads and provides access to hireling.txt data.

hireling.txt defines mercenary (hireling) base stats per tier: class name,
subtype, version group, act/difficulty, starting level, experience curve,
HP curve. We use it to resolve the 16-bit ``merc_type`` field stored in
the D2S header (byte 0xA9) into a human-readable class + difficulty.

Row indexing is ``row_position`` in the file (0-based). The ``merc_type``
binary value is literally that row index.

[SOURCE: hireling.txt from excel/reimagined/ - always read at runtime]
"""

from __future__ import annotations

import csv
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from d2rr_toolkit.meta.source_versions import SourceVersions


logger = logging.getLogger(__name__)


@dataclass
class HirelingRow:
    """One row of hireling.txt. Indexed by the binary merc_type field."""

    row_index: int  # binary merc_type value
    class_name: str  # "Rogue Scout", "Desert Mercenary", "Iron Wolf", ...
    subtype: str  # *SubType column (Reimagined sometimes sets this)
    version: int  # 0 = vanilla row, 100 = Reimagined v=100 variant
    difficulty: int  # 1=Normal, 2=Nightmare, 3=Hell
    base_level: int  # starting level for this row
    name_first: str  # first NameFirst entry (merc name range start)
    name_last: str  # NameLast entry (merc name range end)


class HirelingDatabase:
    """In-memory database of hireling rows keyed by binary merc_type.

    MUST be loaded before use - raises RuntimeError if accessed unloaded.
    """

    def __init__(self) -> None:
        self._rows: list[HirelingRow] = []
        self._loaded = False
        # String-key -> localized name from mercenaries.json (CASC) or a mod
        # override. Populated by :meth:`load_merc_names`.
        self._merc_names: dict[str, str] = {}

    def load(self, path: Path) -> None:
        """Load hireling.txt from a disk path (backward-compat)."""
        if not path.exists():
            logger.warning("hireling.txt not found at %s", path)
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                rows = list(csv.DictReader(f, delimiter="\t"))
        except OSError as e:
            logger.error("Cannot read %s: %s", path, e)
            return
        self.load_from_rows(rows, source=str(path))

    def load_from_rows(self, rows: list[dict[str, str]], *, source: str = "<rows>") -> None:
        """Populate the database from pre-parsed rows (Iron Rule entry point)."""

        def _int(row: dict, key: str) -> int:
            try:
                return int(row.get(key, "0") or "0")
            except ValueError:
                return 0

        self._rows = []
        for idx, row in enumerate(rows):
            self._rows.append(
                HirelingRow(
                    row_index=idx,
                    class_name=row.get("Hireling", "").strip(),
                    subtype=row.get("*SubType", "").strip() or row.get("SubType", "").strip(),
                    version=_int(row, "Version"),
                    difficulty=_int(row, "Difficulty"),
                    base_level=_int(row, "Level"),
                    name_first=row.get("NameFirst", "").strip(),
                    name_last=row.get("NameLast", "").strip(),
                )
            )

        self._loaded = True
        logger.info(
            "Hireling: %d rows loaded from %s",
            len(self._rows),
            source,
        )

    def is_loaded(self) -> bool:
        """Return True if the database has been populated."""
        return self._loaded

    def get_row(self, merc_type: int) -> HirelingRow | None:
        """Return the hireling row for the given binary merc_type value."""
        if 0 <= merc_type < len(self._rows):
            return self._rows[merc_type]
        return None

    def class_name(self, merc_type: int) -> str:
        """Return the display class name for a merc_type, or empty string."""
        row = self.get_row(merc_type)
        return row.class_name if row else ""

    # ── Merc name resolution ─────────────────────────────────────────────

    def load_merc_names(self, json_blob: bytes) -> None:
        """Populate the merc-name table from a mercenaries.json payload.

        Accepts the raw bytes of Blizzard's localization JSON as shipped
        inside the CASC archive at ``data/local/lng/strings/mercenaries.json``.
        Expected schema: a list of objects with ``Key`` and one or more
        language columns (``enUS`` preferred, any non-empty value
        accepted as fallback).

        Safe to call multiple times - later calls override earlier keys.
        """
        try:
            text = json_blob.decode("utf-8-sig", errors="replace")
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Failed to parse mercenaries.json: %s", e)
            return

        added = 0
        for entry in data if isinstance(data, list) else []:
            if not isinstance(entry, dict):
                continue
            key = entry.get("Key", "")
            if not key:
                continue
            value = entry.get("enUS") or next(
                (v for k, v in entry.items() if k != "Key" and isinstance(v, str) and v),
                "",
            )
            if value:
                self._merc_names[key] = value
                added += 1

        logger.info(
            "Hireling: %d merc names loaded into the name table (total: %d)",
            added,
            len(self._merc_names),
        )

    def resolve_merc_name(self, merc_type: int, name_id: int) -> str | None:
        """Resolve a merc (type_id, name_id) pair into a localized name.

        Uses the ``NameFirst`` template from hireling.txt to work out the
        string key, then looks that key up in the merc-name table.

        Returns ``None`` if the hireling row cannot be found, the
        NameFirst template cannot be parsed, or the name table does not
        contain the computed key.
        """
        row = self.get_row(merc_type)
        if row is None or not row.name_first:
            return None

        # Split "merc01", "merca201", "MercX101" into (prefix, base_number, width).
        match = re.match(r"^(.+?)(\d+)$", row.name_first)
        if not match:
            return None
        prefix = match.group(1)
        base_num = int(match.group(2))
        width = len(match.group(2))

        key = f"{prefix}{base_num + name_id:0{width}d}"
        return self._merc_names.get(key)


# ──────────────────────────────────────────────────────────────────────────────
# Module-level singleton + public API
# ──────────────────────────────────────────────────────────────────────────────

_HIRELING_DB = HirelingDatabase()


def get_hireling_db() -> HirelingDatabase:
    """Return the global HirelingDatabase singleton."""
    return _HIRELING_DB


SCHEMA_VERSION_HIRELING: int = 1


def load_hireling(
    *,
    use_cache: bool = True,
    source_versions: "SourceVersions | None" = None,
    cache_dir: "Path | None" = None,
) -> None:
    """Populate the :class:`HirelingDatabase` from ``data/global/excel/hireling.txt``.

    Mercenary class / subclass / difficulty definitions.  Lets
    the merc-parser resolve a merc-type header into a
    human-readable label (``Rogue Scout D1``, ...) for the
    character-select screen.

    Transparently backed by the persistent pickle cache - see
    :mod:`d2rr_toolkit.meta.cache` (or the top-level
    ``GAME_DATA_CACHE.md`` reference) for the invalidation
    contract.  Callers that omit the kwargs get the pre-cache
    behaviour unchanged, just faster on the second launch.

    Args:
        use_cache: ``False`` disables the persistent cache for
            this call only (also honoured via
            ``D2RR_DISABLE_GAME_DATA_CACHE=1``).  Tests use this
            to force a fresh parse without mutating global state.
        source_versions: Optional :class:`SourceVersions`.  When
            omitted the helper resolves it from the current
            :class:`GamePaths` and memoises the result process-
            wide, so a batch of loaders that all default still
            only pays one disk probe.
        cache_dir: Optional cache root override.  Tests route
            this into a ``tmp_path`` fixture; production callers
            rely on the platformdirs default
            (``%LOCALAPPDATA%/d2rr-toolkit/data_cache`` on Windows).
    """
    from d2rr_toolkit.meta import cached_load

    def _build() -> None:
        """Populate the :class:`HirelingDatabase` via the Iron Rule.

        Does not touch the merc-name table - use :func:`load_merc_names`
        separately if name resolution is needed.
        """
        from d2rr_toolkit.adapters.casc import read_game_data_rows

        casc_path = "data:data/global/excel/hireling.txt"
        rows = read_game_data_rows(casc_path)
        if not rows:
            logger.warning(
                "hireling.txt not found in mod or CASC - "
                "merc type resolution will fall back to empty strings."
            )
            return
        get_hireling_db().load_from_rows(rows, source=casc_path)

    cached_load(
        name="hireling",
        schema_version=SCHEMA_VERSION_HIRELING,
        singleton=get_hireling_db(),
        build=_build,
        use_cache=use_cache,
        source_versions=source_versions,
        cache_dir=cache_dir,
    )


def load_merc_names(json_blob: bytes) -> None:
    """Populate the global merc-name table.

    The caller is responsible for locating the ``mercenaries.json`` payload
    (usually read from the CASC archive at
    ``data/local/lng/strings/mercenaries.json``). Passing an already-parsed
    ``dict`` is not supported on purpose - the loader must own the decoding
    to handle BOM and encoding fallbacks consistently.
    """
    get_hireling_db().load_merc_names(json_blob)

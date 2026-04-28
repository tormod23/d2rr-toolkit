"""
Loads properties.txt - maps property codes to ISC stat names.

Property codes (like "res-fire", "str", "ac") appear in:
  - setitems.txt prop1..9 (item-own affixes of set items)
  - setitems.txt aprop1a..5b (per-item set bonus tiers)
  - sets.txt PCode2a..5b (set-wide partial bonuses)
  - sets.txt FCode1..8 (full set bonuses)

Lookup chain for display:
  property code -> stat name(s) via properties.txt
  -> stat_id via ISC by-name lookup
  -> display string via PropertyFormatter

[SOURCE: excel/reimagined/properties.txt - always read at runtime]
"""

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from d2rr_toolkit.game_data.item_stat_cost import ItemStatCostDatabase
    from d2rr_toolkit.meta.source_versions import SourceVersions
from d2rr_toolkit.adapters.casc import read_game_data_rows
from d2rr_toolkit.meta import cached_load

logger = logging.getLogger(__name__)

MAX_PROP_STATS = 7  # properties.txt supports up to 7 stat slots per code


@dataclass(slots=True)
class PropertyStatSlot:
    """One stat slot within a property definition."""

    func: int  # property function (1=direct, 2=percent, 19=skill, etc.)
    stat_name: str  # ISC stat name (e.g. "fireresist", "armorclass")
    set_val: str  # set/param modifier (usually empty)
    val: str  # additional value modifier (usually empty)


@dataclass(slots=True)
class PropertyDefinition:
    """Definition of one property code from properties.txt."""

    code: str
    slots: list[PropertyStatSlot] = field(default_factory=list)

    def stat_names(self) -> list[str]:
        """Return all non-empty stat names."""
        return [s.stat_name for s in self.slots if s.stat_name]

    def primary_stat_id(self, isc_db: "ItemStatCostDatabase") -> int | None:
        """Return the stat_id of the first stat slot, or None."""
        for slot in self.slots:
            if slot.stat_name:
                stat_def = isc_db.get_by_name(slot.stat_name)
                if stat_def is not None:
                    return stat_def.stat_id
        return None


class PropertiesDatabase:
    """Maps property codes to their ISC stat definitions."""

    def __init__(self) -> None:
        self._defs: dict[str, PropertyDefinition] = {}
        self._loaded = False

    def load(self, path: Path) -> None:
        """Load properties.txt from a disk path (backward-compat)."""
        if not path.exists():
            logger.warning("properties.txt not found at %s", path)
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                rows = list(csv.DictReader(f, delimiter="\t"))
        except OSError as e:
            logger.error("Cannot read %s: %s", path, e)
            return
        self.load_from_rows(rows, source=str(path))

    def load_from_rows(self, rows: list[dict[str, str]], *, source: str = "<rows>") -> None:
        """Populate the database from pre-parsed tab-delimited rows."""
        loaded = 0
        for row in rows:
            code = row.get("code", "").strip()
            if not code:
                continue
            slots = []
            for i in range(1, MAX_PROP_STATS + 1):
                func_str = row.get(f"func{i}", "").strip()
                stat_name = row.get(f"stat{i}", "").strip()
                set_val = row.get(f"set{i}", "").strip()
                val = row.get(f"val{i}", "").strip()
                if not func_str and not stat_name:
                    continue
                try:
                    func = int(func_str) if func_str else 0
                except ValueError:
                    func = 0
                slots.append(
                    PropertyStatSlot(
                        func=func,
                        stat_name=stat_name,
                        set_val=set_val,
                        val=val,
                    )
                )
            self._defs[code] = PropertyDefinition(code=code, slots=slots)
            loaded += 1
        self._loaded = True
        logger.info("PropertiesDatabase: %d property codes loaded from %s", loaded, source)

    def get(self, code: str) -> PropertyDefinition | None:
        """Return the :class:`PropertyDefinition` for ``code``, or None if unknown."""

        return self._defs.get(code)

    def is_loaded(self) -> bool:
        """Return True if the database has been populated."""
        return self._loaded

    def __len__(self) -> int:
        return len(self._defs)


_PROPS_DB = PropertiesDatabase()


def get_properties_db() -> PropertiesDatabase:
    """Return the module-level :class:`PropertiesDatabase` singleton."""
    return _PROPS_DB


SCHEMA_VERSION_PROPERTIES: int = 1


def load_properties(
    *,
    use_cache: bool = True,
    source_versions: "SourceVersions | None" = None,
    cache_dir: "Path | None" = None,
) -> None:
    """Populate the :class:`PropertiesDatabase` from ``data/global/excel/properties.txt``.

    Property-code -> stat-id map (e.g. ``res-fire`` ->
    ``fireresist`` -> ISC stat 39).  Consumed by
    :class:`SetBonusEntry.format` when rendering set-tier
    bonuses from ``setitems.txt`` / ``sets.txt``.

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

    def _build() -> None:
        """Populate the :class:`PropertiesDatabase` via the Iron Rule."""

        casc_path = "data:data/global/excel/properties.txt"
        rows = read_game_data_rows(casc_path)
        if not rows:
            logger.warning("properties.txt not found in mod or CASC")
            return
        get_properties_db().load_from_rows(rows, source=casc_path)

    cached_load(
        name="properties",
        schema_version=SCHEMA_VERSION_PROPERTIES,
        singleton=get_properties_db(),
        build=_build,
        use_cache=use_cache,
        source_versions=source_versions,
        cache_dir=cache_dir,
    )

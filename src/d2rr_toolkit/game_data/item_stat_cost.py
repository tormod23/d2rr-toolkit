"""
Loads and provides access to ItemStatCost.txt data.

This is the single most critical game data file for item parsing.
It defines how every magical property (stat) is encoded in save files:
  - Save Bits:       how many bits the value occupies
  - Save Add:        bias to subtract from stored value for display
  - Save Param Bits: extra param bits before the value (if > 0)
  - Encode:          special encoding type (0=normal, 1=min/max pair,
                                            2=skill-on-event, 3=charged)

Without this file, we cannot read magical property VALUES and therefore
cannot determine where one property ends and the next begins.

Data source priority: excel/reimagined/ first (mod overrides vanilla values).

[BV] Character stat IDs 0-15 confirmed correct.
[SPEC_ONLY] Item property stats (IDs 16+) - widths from file, not yet
             individually binary-verified against item binary data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from d2rr_toolkit.meta.source_versions import SourceVersions

logger = logging.getLogger(__name__)


@dataclass
class StatDefinition:
    """Definition of one stat from ItemStatCost.txt."""

    stat_id: int
    name: str
    save_bits: int  # bits for value in item property list
    save_add: int  # subtract from stored value for display
    save_param_bits: int  # extra param bits before value (usually 0)
    encode: int  # 0=normal, 1=minmax, 2=skill-evt, 3=charged
    signed: bool
    csv_bits: int  # bits for character stats section [BV]
    csv_param: int
    # Description fields for property display
    desc_priority: int = 0  # display order (higher = shown first in D2R; sort DESC)
    descfunc: int = 0  # description function type (19=standard, 15=skill-on-event, etc.)
    descval: int = 0  # value display position (1=before, 2=after)
    descstrpos: str = ""  # string key for positive values (e.g. "ModStr1a")
    descstrneg: str = ""  # string key for negative values
    descstr2: str = ""  # secondary string key (e.g. for skill-on-event event name)


class ItemStatCostDatabase:
    """In-memory database of all stat definitions from ItemStatCost.txt."""

    def __init__(self) -> None:
        self._stats: dict[int, StatDefinition] = {}
        self._loaded = False

    def load(self, path: Path) -> None:
        """Load stat definitions from a disk path (backward-compat)."""
        if not path.exists():
            logger.warning("ItemStatCost.txt not found at %s", path)
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                import csv as _csv

                rows = list(_csv.DictReader(f, delimiter="\t"))
        except OSError as e:
            logger.error("Cannot read %s: %s", path, e)
            return
        self.load_from_rows(rows, source=str(path))

    def load_from_rows(self, rows: list[dict[str, str]], *, source: str = "<rows>") -> None:
        """Populate the database from pre-parsed rows (Iron Rule entry point)."""

        def gi(row: dict[str, str], key: str, default: int = 0) -> int:
            v = (row.get(key) or "").strip()
            try:
                return int(v) if v else default
            except ValueError:
                return default

        def gs(row: dict[str, str], key: str, default: str = "") -> str:
            return (row.get(key) or default).strip() or default

        loaded = 0
        for row in rows:
            # Skip header-like or blank rows
            stat_id_raw = (row.get("*ID") or "").strip()
            if not stat_id_raw:
                continue
            try:
                stat_id = int(stat_id_raw)
            except ValueError:
                continue
            if stat_id < 0:
                continue
            self._stats[stat_id] = StatDefinition(
                stat_id=stat_id,
                name=gs(row, "Stat"),
                save_bits=gi(row, "Save Bits"),
                save_add=gi(row, "Save Add"),
                save_param_bits=gi(row, "Save Param Bits"),
                encode=gi(row, "Encode"),
                signed=gi(row, "Signed") == 1,
                csv_bits=gi(row, "CSvBits"),
                csv_param=gi(row, "CSvParam"),
                desc_priority=gi(row, "descpriority"),
                descfunc=gi(row, "descfunc"),
                descval=gi(row, "descval"),
                descstrpos=gs(row, "descstrpos"),
                descstrneg=gs(row, "descstrneg"),
                descstr2=gs(row, "descstr2"),
            )
            loaded += 1

        self._loaded = True
        logger.info("ItemStatCost: %d stats loaded from %s", loaded, source)

    def get(self, stat_id: int) -> StatDefinition | None:
        """Return the :class:`ItemStatCostEntry` for ``stat_id``, or None if unknown."""

        return self._stats.get(stat_id)

    def get_by_name(self, name: str) -> StatDefinition | None:
        """Look up a stat definition by its ISC 'Stat' name."""
        if not hasattr(self, "_by_name"):
            self._by_name: dict[str, StatDefinition] = {s.name: s for s in self._stats.values()}
        return self._by_name.get(name)

    def is_loaded(self) -> bool:
        """Return True if the database has been populated."""
        return self._loaded

    def load_patch(self, path: Path) -> None:
        """Load a patch file with missing stat definitions.

        Patch file format: tab-separated columns with header row.
        Required columns: *ID, Save Bits
        Optional: Save Add, Save Param Bits, Encode, Stat

        Args:
            path: Path to the patch .txt file.
        """
        if not path.exists():
            logger.debug("ISC patch file not found: %s", path)
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = [l for l in f.readlines() if not l.strip().startswith("#") and l.strip()]
        except OSError as e:
            logger.error("Cannot read patch %s: %s", path, e)
            return
        if not lines:
            return

        headers = lines[0].strip().split("	")

        def col(n):
            try:
                return headers.index(n)
            except ValueError:
                return None

        idx_id = col("*ID")
        idx_sb = col("Save Bits")
        idx_sa = col("Save Add")
        idx_sp = col("Save Param Bits")
        idx_enc = col("Encode")
        idx_name = col("Stat")

        if idx_id is None or idx_sb is None:
            logger.error("ISC patch missing required columns (*ID, Save Bits)")
            return

        loaded = 0
        for line in lines[1:]:
            p = line.strip().split("	")
            if not p or not p[0].strip():
                continue
            try:
                sid = int(p[idx_id].strip())

                def gi(idx, default=0):
                    if idx is None or idx >= len(p):
                        return default
                    v = p[idx].strip()
                    try:
                        return int(v) if v else default
                    except ValueError:
                        return default

                self._stats[sid] = StatDefinition(
                    stat_id=sid,
                    name=p[idx_name].strip() if idx_name and idx_name < len(p) else f"custom_{sid}",
                    save_bits=gi(idx_sb),
                    save_add=gi(idx_sa),
                    save_param_bits=gi(idx_sp),
                    encode=gi(idx_enc),
                    signed=False,
                    csv_bits=0,
                    csv_param=0,
                )
                loaded += 1
            except (ValueError, IndexError):
                # Malformed patch row - skip it silently. The patch file
                # is optional and user-editable; bad rows should not break
                # the whole load.
                pass
        logger.info("ISC patch: %d stats loaded from %s", loaded, path)

    def __len__(self) -> int:
        return len(self._stats)


_ISC_DB = ItemStatCostDatabase()


def get_isc_db() -> ItemStatCostDatabase:
    """Return the module-level :class:`ItemStatCostDatabase` singleton."""
    return _ISC_DB


# Bump when StatDefinition or ItemStatCostDatabase gain/lose/rename a
# field.  Tests in tests/test_game_data_cache.py guard this via a
# dataclass-field-hash invariant.
SCHEMA_VERSION_ITEM_STAT_COST: int = 1


def load_item_stat_cost(
    *,
    use_cache: bool = True,
    source_versions: "SourceVersions | None" = None,
    cache_dir: "Path | None" = None,
) -> None:
    """Populate the :class:`ItemStatCostDatabase` via the Iron Rule.

    Transparently backed by the toolkit's persistent pickle cache -
    see :func:`d2rr_toolkit.meta.cached_load` for the invalidation
    contract.  Callers that omit the kwargs get the same behaviour
    as before the cache landed, just faster on the second launch.

    Args:
        use_cache: ``False`` disables the persistent cache for this
            call only (also honoured via
            ``D2RR_DISABLE_GAME_DATA_CACHE=1``).
        source_versions: Optional :class:`SourceVersions`.  When
            omitted, resolved lazily from :class:`GamePaths` and
            memoised across loaders.
        cache_dir: Optional override for the cache root.  Tests
            route this into a ``tmp_path`` fixture; production
            callers rely on the platformdirs default.
    """
    from d2rr_toolkit.meta import cached_load

    def _build() -> None:
        from d2rr_toolkit.adapters.casc import read_game_data_rows

        casc_path = "data:data/global/excel/itemstatcost.txt"
        rows = read_game_data_rows(casc_path)
        if not rows:
            logger.warning(
                "ItemStatCost.txt not found in mod or CASC - magical properties cannot be parsed."
            )
            return
        get_isc_db().load_from_rows(rows, source=casc_path)

    cached_load(
        name="item_stat_cost",
        schema_version=SCHEMA_VERSION_ITEM_STAT_COST,
        singleton=get_isc_db(),
        build=_build,
        use_cache=use_cache,
        source_versions=source_versions,
        cache_dir=cache_dir,
    )


def load_isc_patch(patch_path: Path) -> None:
    """Load an ISC patch file with missing stat definitions.

    Args:
        patch_path: Path to the patch .txt file.
    """
    get_isc_db().load_patch(patch_path)

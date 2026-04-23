"""Gem/Rune socketing bonus database - loads gems.txt.

Maps rune codes (e.g. 'r24' for Ist) to their socketing bonuses per
item slot type (weapon / helm=body-armor / shield).

[SOURCE: excel/reimagined/gems.txt - always read at runtime]
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from d2rr_toolkit.meta.source_versions import SourceVersions


logger = logging.getLogger(__name__)


@dataclass
class GemSocketBonus:
    """One property granted when a gem/rune is socketed in a specific slot."""

    prop_code: str  # e.g. "mag%" - look up via PropertiesDatabase
    param: str = ""  # optional param (skill name, class, etc.)
    min_val: int = 0
    max_val: int = 0


@dataclass
class GemDefinition:
    """All socketing bonuses for one gem or rune."""

    name: str
    code: str  # item code (e.g. "r24" for Ist Rune)
    weapon_mods: list[GemSocketBonus] = field(default_factory=list)
    helm_mods: list[GemSocketBonus] = field(default_factory=list)  # also body armor
    shield_mods: list[GemSocketBonus] = field(default_factory=list)

    def get_mods(self, slot_type: str) -> list[GemSocketBonus]:
        """Return mods for the given slot type.

        Args:
            slot_type: "weapon", "helm" (= body armor + helms), or "shield"
        """
        if slot_type == "weapon":
            return self.weapon_mods
        if slot_type == "shield":
            return self.shield_mods
        return self.helm_mods  # default: helm = body armor


class GemsDatabase:
    """Maps gem/rune codes to their socketing bonuses."""

    def __init__(self) -> None:
        self._defs: dict[str, GemDefinition] = {}  # code -> definition
        self._loaded = False

    def load(self, path: Path) -> None:
        """Load gems.txt from a disk path (backward-compat)."""
        if not path.exists():
            logger.warning("gems.txt not found at %s", path)
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
        loaded = 0
        for row in rows:
            code = row.get("code", "").strip()
            name = row.get("name", "").strip()
            if not code:
                continue
            self._defs[code] = GemDefinition(
                name=name,
                code=code,
                weapon_mods=self._read_mods(row, "weapon"),
                helm_mods=self._read_mods(row, "helm"),
                shield_mods=self._read_mods(row, "shield"),
            )
            loaded += 1
        self._loaded = True
        logger.info("GemsDatabase: %d gem/rune entries loaded from %s", loaded, source)

    @staticmethod
    def _read_mods(row: dict, prefix: str) -> list[GemSocketBonus]:
        """Read up to 3 mod slots for a given prefix (weapon/helm/shield)."""
        mods: list[GemSocketBonus] = []
        for i in range(1, 4):
            prop_code = row.get(f"{prefix}Mod{i}Code", "").strip()
            if not prop_code:
                continue
            param = row.get(f"{prefix}Mod{i}Param", "").strip()
            try:
                min_val = int(row.get(f"{prefix}Mod{i}Min", "0").strip() or "0")
                max_val = int(row.get(f"{prefix}Mod{i}Max", "0").strip() or "0")
            except ValueError:
                min_val = max_val = 0
            mods.append(
                GemSocketBonus(
                    prop_code=prop_code,
                    param=param,
                    min_val=min_val,
                    max_val=max_val,
                )
            )
        return mods

    def get(self, code: str) -> GemDefinition | None:
        """Return gem/rune definition by item code."""
        return self._defs.get(code)

    def is_loaded(self) -> bool:
        """Return True if the database has been populated."""
        return self._loaded

    def __len__(self) -> int:
        return len(self._defs)


_GEMS_DB = GemsDatabase()


def get_gems_db() -> GemsDatabase:
    """Return the module-level :class:`GemsDatabase` singleton."""
    return _GEMS_DB


SCHEMA_VERSION_GEMS: int = 1


def load_gems(
    *,
    use_cache: bool = True,
    source_versions: "SourceVersions | None" = None,
    cache_dir: "Path | None" = None,
) -> None:
    """Populate the :class:`GemsDatabase` from ``data/global/excel/gems.txt``.

    Per-gem + per-skull modifier table.  Determines what a gem
    contributes depending on whether it sits in a weapon,
    armor or shield socket (Reimagined customises the
    original D2 tables extensively).

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
        """Populate the :class:`GemsDatabase` via the Iron Rule."""
        from d2rr_toolkit.adapters.casc import read_game_data_rows

        casc_path = "data:data/global/excel/gems.txt"
        rows = read_game_data_rows(casc_path)
        if not rows:
            logger.warning("gems.txt not found in mod or CASC")
            return
        _GEMS_DB.load_from_rows(rows, source=casc_path)

    cached_load(
        name="gems",
        schema_version=SCHEMA_VERSION_GEMS,
        singleton=get_gems_db(),
        build=_build,
        use_cache=use_cache,
        source_versions=source_versions,
        cache_dir=cache_dir,
    )


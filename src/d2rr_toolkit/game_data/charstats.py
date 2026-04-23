"""
Loads and provides access to charstats.txt data.

charstats.txt defines per-class character statistics: class name, base
attribute values, per-level growth rates, starting skills, and starting
equipment.  We use the "class" column (first column) to map binary class
IDs to human-readable names, eliminating the hardcoded CLASS_NAMES dict
in constants.py.

Class ID assignment (binary format, row-indexed, skipping the "Expansion"
separator that D2 uses between classic and expansion classes):
  0 = Amazon
  1 = Sorceress
  2 = Necromancer
  3 = Paladin
  4 = Barbarian
  (skip "Expansion" separator row - empty class entry, not a real class)
  5 = Druid
  6 = Assassin
  7 = Warlock  (new class added by D2R Reimagined)

[SOURCE: charstats.txt from excel/reimagined/ - always read at runtime,
 never cached as hardcoded constants]
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from d2rr_toolkit.meta.source_versions import SourceVersions


# Note: CLASS_NAMES in constants.py is kept for backward compatibility
# (e.g. D2S header parsing where only the ID is needed). Class names for
# display purposes MUST come from charstats.txt loaded at runtime.

logger = logging.getLogger(__name__)


@dataclass
class ClassDefinition:
    """Base statistics for one character class from charstats.txt."""

    class_id: int  # binary ID (0-7)
    name: str  # display name (e.g. "Amazon")
    base_str: int  # base Strength
    base_dex: int  # base Dexterity
    base_int: int  # base Energy
    base_vit: int  # base Vitality
    base_stamina: int  # base Stamina
    # Per-level growth (stored in fourths in the file; use /4.0 for display)
    life_per_level_fourths: int
    stamina_per_level_fourths: int
    mana_per_level_fourths: int
    # Per-stat growth (stored in fourths in the file)
    life_per_vitality_fourths: int
    stamina_per_vitality_fourths: int
    mana_per_magic_fourths: int


class CharStatsDatabase:
    """In-memory database of character class definitions from charstats.txt.

    After loading, provides class name lookup and base stat access.
    MUST be loaded before use - raises RuntimeError if accessed unloaded.
    """

    def __init__(self) -> None:
        self._classes: dict[int, ClassDefinition] = {}
        # Skill tab keys: (class_id, tab_within_class) -> StrSklTabItem key
        self._skill_tab_keys: dict[tuple[int, int], str] = {}
        self._loaded = False

    def load(self, path: Path) -> None:
        """Load charstats.txt from a disk path (backward-compat)."""
        if not path.exists():
            logger.warning("charstats.txt not found at %s", path)
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                rows = list(csv.DictReader(f, delimiter="\t"))
        except OSError as e:
            logger.error("Cannot read %s: %s", path, e)
            return
        self.load_from_rows(rows, source=str(path))

    def load_from_rows(self, rows: list[dict[str, str]], *, source: str = "<rows>") -> None:
        """Populate the database from pre-parsed rows (Iron Rule entry point).

        Rows are assigned class IDs sequentially (0, 1, 2, ...) skipping
        any row whose "class" field is empty or == "Expansion" (the classic
        vs expansion class separator in the D2 data files).
        """
        self._classes = {}
        class_id = 0

        def _int(row: dict, key: str) -> int:
            try:
                return int(row.get(key, "0") or "0")
            except ValueError:
                return 0

        for row in rows:
            name = row.get("class", "").strip()
            if not name or name.lower() == "expansion":
                # Skip separator / blank rows
                continue

            # Load skill tab keys (StrSkillTab1/2/3)
            for tab_idx in range(3):
                tab_key = row.get(f"StrSkillTab{tab_idx + 1}", "").strip()
                if tab_key:
                    self._skill_tab_keys[(class_id, tab_idx)] = tab_key

            self._classes[class_id] = ClassDefinition(
                class_id=class_id,
                name=name,
                base_str=_int(row, "str"),
                base_dex=_int(row, "dex"),
                base_int=_int(row, "int"),
                base_vit=_int(row, "vit"),
                base_stamina=_int(row, "stamina"),
                life_per_level_fourths=_int(row, "LifePerLevel"),
                stamina_per_level_fourths=_int(row, "StaminaPerLevel"),
                mana_per_level_fourths=_int(row, "ManaPerLevel"),
                life_per_vitality_fourths=_int(row, "LifePerVitality"),
                stamina_per_vitality_fourths=_int(row, "StaminaPerVitality"),
                mana_per_magic_fourths=_int(row, "ManaPerMagic"),
            )
            class_id += 1

        self._loaded = True
        logger.info(
            "CharStats: %d class definitions loaded from %s",
            len(self._classes),
            source,
        )

    def is_loaded(self) -> bool:
        """Return True if the database has been populated."""
        return self._loaded

    def get_class_name(self, class_id: int) -> str:
        """Return display name for the given class ID.

        Requires the database to be loaded from charstats.txt at runtime.
        No hardcoded fallback - all class names come from game data.
        Returns "Unknown(N)" if the ID is not in the loaded data.
        """
        if not self._loaded:
            raise RuntimeError(
                "CharStats database not loaded - cannot resolve class names. "
                "Load game data first via load_charstats()."
            )
        cd = self._classes.get(class_id)
        return cd.name if cd is not None else f"Unknown({class_id})"

    def get_skill_tab_key(self, class_id: int, tab_within_class: int) -> str | None:
        """Return the StrSklTabItem key for a class skill tab.

        Args:
            class_id: Class index (0=Amazon, ..., 7=Warlock).
            tab_within_class: Tab index within class (0, 1, or 2).

        Returns:
            String key (e.g. "StrSklTabItem19") or None.
        """
        return self._skill_tab_keys.get((class_id, tab_within_class))

    def get_class_def(self, class_id: int) -> ClassDefinition | None:
        """Return the full ClassDefinition for the given class ID, or None."""
        return self._classes.get(class_id)

    def all_classes(self) -> list[ClassDefinition]:
        """Return all loaded class definitions sorted by class_id."""
        return sorted(self._classes.values(), key=lambda c: c.class_id)


# ──────────────────────────────────────────────────────────────────────────────
# Module-level singleton + public API
# ──────────────────────────────────────────────────────────────────────────────

_CHARSTATS_DB = CharStatsDatabase()


def get_charstats_db() -> CharStatsDatabase:
    """Return the global CharStatsDatabase singleton."""
    return _CHARSTATS_DB


SCHEMA_VERSION_CHARSTATS: int = 1


def load_charstats(
    *,
    use_cache: bool = True,
    source_versions: "SourceVersions | None" = None,
    cache_dir: "Path | None" = None,
) -> None:
    """Populate the :class:`CharStatsDatabase` from ``data/global/excel/charstats.txt``.

    Class definitions - used throughout the pipeline for
    display-name resolution (``class_id`` -> ``Amazon`` ...
    ``Warlock``) and for skill-tab resolution in the
    ``descfunc=14`` formatter branch.  Reimagined's 8-class
    roster (incl. Warlock at ``class_id=7``) is loaded here.

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
        """Populate the :class:`CharStatsDatabase` via the Iron Rule."""
        from d2rr_toolkit.adapters.casc import read_game_data_rows

        casc_path = "data:data/global/excel/charstats.txt"
        rows = read_game_data_rows(casc_path)
        if not rows:
            logger.error("charstats.txt not found in mod or CASC - class name lookup will fail.")
            return
        get_charstats_db().load_from_rows(rows, source=casc_path)

    cached_load(
        name="charstats",
        schema_version=SCHEMA_VERSION_CHARSTATS,
        singleton=get_charstats_db(),
        build=_build,
        use_cache=use_cache,
        source_versions=source_versions,
        cache_dir=cache_dir,
    )



"""
Loads and provides access to CubeMain.txt data, focusing on the
Reimagined Item Corruption system.

CubeMain.txt defines all Horadric Cube recipes.  In D2R Reimagined the
corruption system is implemented entirely through two sets of recipes:

  1. DUMMY recipes (op=18, param=361, value=0):
       First cube press.  Fires when item does NOT yet have stat 361
       (item_corrupted).  Rolls corruptedDummy = random(1-100) and sets
       item_corrupted = 1.

  2. SUCCESS recipes (op=15, param=362, value=N):
       Second cube press.  op=15 checks stat 362 >= N.  Rows are sorted
       high-to-low in the file -> first-match-wins semantics implement range
       brackets.  Adds the corruption bonus mods, then:
         - item_corrupted  += 1  -> total = 2   (always)
         - corruptedDummy  += 101 -> total = original_roll + 101

Binary state after full corruption
-----------------------------------
  stat 361 (item_corrupted)    = 2  (always)
  stat 362 (item_corruptedDummy) = roll + 101  (range 102-201)

To decode the dice roll from a saved item:
  roll = item_corruptedDummy - 101   (gives 1-100)
  If item_corruptedDummy <= 100: phase-2 not yet applied (phase-1 done only)

[SOURCE: cubemain.txt from excel/reimagined/ - always read at runtime,
 never cached as hardcoded constants]
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

# ──────────────────────────────────────────────────────────────────────────────
# Phase-2 corruptedDummy encoding constants.
# These come from the CubeMain data itself (corruptedDummy += 101 in every
# SUCCESS recipe), but they define the encoding semantics and are kept here
# as named constants rather than magic literals.
# ──────────────────────────────────────────────────────────────────────────────

CORRUPTION_PHASE2_OFFSET: int = 101
"""Added to corruptedDummy by every phase-2 SUCCESS recipe.
After phase-2: stored_value = original_roll + 101.
To recover original roll: roll = stored_value - 101.
[Derived from CubeMain.txt corruptedDummy mod min=101/max=101 pattern]
"""

CORRUPTION_FULLY_DONE_THRESHOLD: int = 101
"""stat 362 > 100 means phase-2 is complete.
Stored values 102-201 indicate a fully corrupted item.
[Derived from CubeMain.txt: DUMMY adds 1-100, SUCCESS adds +101]
"""


@dataclass
class CorruptionMod:
    """One modifier applied by a corruption outcome."""

    mod: str  # property code from Properties.txt (e.g. "deadly", "crush")
    param: str  # parameter string (may be empty; used for oskill to specify skill_id)
    min_val: int  # minimum value (often == max_val for corruption outcomes)
    max_val: int  # maximum value


@dataclass
class CorruptionOutcome:
    """One range-band in the corruption outcome table for a specific item type."""

    item_type: str  # e.g. "glov", "shld", "amu", "weap"
    roll_min: int  # minimum dice roll (inclusive) that maps to this outcome
    roll_max: int  # maximum dice roll (inclusive)
    label: str  # human-readable description (from recipe description field)
    mods: list[CorruptionMod] = field(default_factory=list)

    @property
    def probability_pct(self) -> int:
        """Probability as integer percentage (1-25)."""
        return self.roll_max - self.roll_min + 1

    @property
    def is_beneficial(self) -> bool:
        """True if outcome adds at least one mod (not Nothing / Brick)."""
        return len(self.mods) > 0


class CubeMainDatabase:
    """In-memory database of corruption outcomes parsed from CubeMain.txt.

    After loading, call get_corruption_outcome(item_type, roll) to look up
    what effect a specific dice roll produces for a given item slot type.

    Item type codes (from input 1 of SUCCESS recipes):
        amu, belt, boot, glov, helm, rin, shld, tors, weap
    """

    def __init__(self) -> None:
        # item_type -> list of CorruptionOutcome, sorted roll_min DESC
        self._outcomes: dict[str, list[CorruptionOutcome]] = {}
        self._loaded = False

    def load(self, path: Path) -> None:
        """Load CubeMain.txt from a disk path (backward-compat)."""
        if not path.exists():
            logger.warning("CubeMain.txt not found at %s", path)
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

        Uses first-match-wins semantics matching the game engine: recipes are
        stored high-to-low in the file, and op=15 fires when stat >= value.
        We reconstruct roll_min/roll_max from consecutive value boundaries.
        """
        # ── Collect SUCCESS rows grouped by item type ─────────────────────
        # Key = item_type str; value = list of (threshold_val, label, mods)
        by_type: dict[str, list[tuple[int, str, list[CorruptionMod]]]] = {}

        for r in rows:
            desc = r.get("description", "")
            if "CORRUPT ITEM SUCCESS" not in desc:
                continue

            item_type = r.get("input 1", "").strip()
            if not item_type:
                continue

            try:
                threshold = int(r.get("value", "0") or "0")
            except ValueError:
                continue

            # Extract human-readable label from description
            label = desc
            if "=" in desc:
                label = desc.split("=")[-1].strip()
            # Remove trailing probability annotation "(N% Chance)"
            if "Chance" in label:
                label = label.split("(")[0].strip()

            # Collect mods (skip the always-present corrupted/corruptedDummy markers)
            mods: list[CorruptionMod] = []
            for i in range(1, 6):
                mod_name = r.get(f"mod {i}", "").strip()
                if not mod_name or mod_name in ("corrupted", "corruptedDummy"):
                    continue
                try:
                    min_val = int(r.get(f"mod {i} min", "0") or "0")
                    max_val = int(r.get(f"mod {i} max", "0") or "0")
                except ValueError:
                    min_val = max_val = 0
                param = r.get(f"mod {i} param", "").strip()
                mods.append(
                    CorruptionMod(
                        mod=mod_name,
                        param=param,
                        min_val=min_val,
                        max_val=max_val,
                    )
                )

            if item_type not in by_type:
                by_type[item_type] = []
            by_type[item_type].append((threshold, label, mods))

        # ── Build CorruptionOutcome objects with roll_min / roll_max ───────
        # Rows are stored high-to-low in the file (first-match-wins).
        # Sort descending and compute ranges from consecutive thresholds.
        self._outcomes = {}
        for item_type, entries in by_type.items():
            entries.sort(key=lambda x: -x[0])  # high to low
            outcomes: list[CorruptionOutcome] = []
            for idx, (threshold, label, mods) in enumerate(entries):
                roll_min = threshold
                roll_max = entries[idx - 1][0] - 1 if idx > 0 else 100
                outcomes.append(
                    CorruptionOutcome(
                        item_type=item_type,
                        roll_min=roll_min,
                        roll_max=roll_max,
                        label=label,
                        mods=mods,
                    )
                )
            self._outcomes[item_type] = outcomes

        total = sum(len(v) for v in self._outcomes.values())
        self._loaded = True
        logger.info(
            "CubeMain: %d corruption outcomes loaded (%d item types) from %s",
            total,
            len(self._outcomes),
            source,
        )

    def is_loaded(self) -> bool:
        """Return True if the database has been populated."""
        return self._loaded

    def get_outcome_table(self, item_type: str) -> list[CorruptionOutcome]:
        """Return all outcomes for the given item type (sorted roll_min DESC).

        Returns an empty list if item_type unknown or DB not loaded.
        """
        return self._outcomes.get(item_type, [])

    def get_corruption_outcome(self, item_type: str, roll: int) -> CorruptionOutcome | None:
        """Find the corruption outcome for a given item type and dice roll (1-100).

        Uses first-match-wins (same logic as game engine op=15 / sorted high-to-low):
        returns the first outcome whose roll_min <= roll.

        Args:
            item_type: CubeMain input-1 code ("glov", "shld", "amu", etc.)
            roll:       Dice roll integer in range 1-100.

        Returns:
            CorruptionOutcome or None if not found / DB not loaded.
        """
        for outcome in self._outcomes.get(item_type, []):
            if roll >= outcome.roll_min:
                return outcome
        return None

    @staticmethod
    def decode_corrupted_dummy(stored_value: int) -> tuple[int, bool]:
        """Decode stat 362 (item_corruptedDummy) into the original dice roll.

        Phase-1 stores the raw roll (1-100).
        Phase-2 adds 101, so stored = roll + 101 (range 102-201).

        Args:
            stored_value: Value of stat 362 as read from the save file.

        Returns:
            (roll, phase2_complete) where roll is 1-100 and
            phase2_complete indicates whether the second cube press was applied.
        """
        if stored_value > CORRUPTION_FULLY_DONE_THRESHOLD:
            return stored_value - CORRUPTION_PHASE2_OFFSET, True
        return stored_value, False

    @staticmethod
    def item_type_from_item_code(item_code: str, item_category: str) -> str | None:
        """Best-effort mapping from parsed item_code category to CubeMain type string.

        CubeMain SUCCESS rows use these input-1 type codes for phase-2:
          amu, belt, boot, glov, helm, rin, shld, tors, weap

        The item_category argument should be the ItemCategory string from
        game_data.item_types (e.g. "armor", "weapon", "shield", "misc").
        Returns None if the mapping cannot be determined.

        NOTE: This provides a best-effort mapping.  For exact classification,
        the item type hierarchy from armor.txt/weapons.txt should be used.
        """
        _CATEGORY_MAP: dict[str, str] = {
            "armor": "tors",  # torso armor - see below for overrides
            "weapon": "weap",
            "shield": "shld",
        }
        return _CATEGORY_MAP.get(item_category)


# ──────────────────────────────────────────────────────────────────────────────
# Module-level singleton + public API
# ──────────────────────────────────────────────────────────────────────────────

_CUBEMAIN_DB = CubeMainDatabase()


def get_cubemain_db() -> CubeMainDatabase:
    """Return the global CubeMainDatabase singleton."""
    return _CUBEMAIN_DB


SCHEMA_VERSION_CUBEMAIN: int = 1


def load_cubemain(
    *,
    use_cache: bool = True,
    source_versions: "SourceVersions | None" = None,
    cache_dir: "Path | None" = None,
) -> None:
    """Populate the :class:`CubeMainDatabase` from ``data/global/excel/cubemain.txt``.

    Horadric-cube recipes.  Powers the corruption-outcome lookup
    (``op=18`` / ``op=15`` phases, stat ``362`` roll index)
    plus every other recipe-driven tooltip augmentation.

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
        """Populate the :class:`CubeMainDatabase` via the Iron Rule."""
        from d2rr_toolkit.adapters.casc import read_game_data_rows

        casc_path = "data:data/global/excel/cubemain.txt"
        rows = read_game_data_rows(casc_path)
        if not rows:
            logger.warning(
                "CubeMain.txt not found in mod or CASC - corruption outcome lookup unavailable."
            )
            return
        get_cubemain_db().load_from_rows(rows, source=casc_path)

    cached_load(
        name="cubemain",
        schema_version=SCHEMA_VERSION_CUBEMAIN,
        singleton=get_cubemain_db(),
        build=_build,
        use_cache=use_cache,
        source_versions=source_versions,
        cache_dir=cache_dir,
    )


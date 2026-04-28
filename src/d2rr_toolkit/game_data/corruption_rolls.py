"""Corruption-roll tables - deterministic mapping from stat362 to applied mods.

The Reimagined Corruption system (Orb of Corruption ``ka3``) stamps an
item with a dice roll in ``item_corruptedDummy`` (stat 362) and, on a
second cube application, awards a tier-specific mod bundle chosen by
that roll.  Because the rolled value is *stored on the item*, the mod
bundle is 100% recoverable after-the-fact - there's no ambiguity and
no probabilistic lookup.

Binary encoding recap (from ``project_corruption_mechanics.md``):

  * Phase 1: ``stat 361 = 1`` (marker), ``stat 362 = 1..100`` (the roll)
  * Phase 2: ``stat 361 = 2`` (marker), ``stat 362 = 101..201``
    -> Decode: ``real_roll = stat362 - 101``

Outcome lookup by item type and roll (from cubemain.txt op=15 rows
keyed to ``input 1`` + ``value``, rows sorted high threshold first,
first match wins):

  * roll ∈ [100, 100] -> "Special" tier (1%)
  * roll ∈ [46..99]   -> 10 distinct beneficial tiers (6/7/8/9/6/6/6/6/7)
  * roll ∈ [21, 45]   -> "Nothing" (25%, no bonus mods)
  * roll ∈ [11, 20]   -> "Brick Rare"   (10%, no bonus mods)
  * roll ∈ [1, 10]    -> "Brick White"  (10%, no bonus mods)

Supported item-type tokens (from ``input 1`` of the op=15 rows):
``amu``, ``belt``, ``boot``, ``glov``, ``helm``, ``rin``, ``shld``,
``tors``, ``weap``.  For helmet/shield/armor the generic ``armo,XX``
rows only cover the *phase-1 DUMMY* recipes - phase-2 outcomes always
use the slot-specific ``helm``/``shld``/``tors`` tokens.

This module loads everything into an immutable in-memory database at
process start via :func:`load_corruption_rolls`.  The data is tiny
(168 rows total) and the cache helper makes warm loads free.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from d2rr_toolkit.meta.source_versions import SourceVersions
from d2rr_toolkit.adapters.casc import read_game_data_rows
from d2rr_toolkit.meta import cached_load

logger = logging.getLogger(__name__)

# Bump when the dataclass field layout changes.
SCHEMA_VERSION_CORRUPTION_ROLLS: int = 2  # +par on CorruptionMod

# Per-row mod slots in cubemain.txt (``mod 1`` .. ``mod 5``).  The last
# two beneficial slots are always the ``corrupted`` / ``corruptedDummy``
# book-keeping markers which the formatter already skips - we filter
# them out here so ``CorruptionOutcome.mods`` only carries the actual
# bonus effects.
_MAX_MOD_SLOTS = 5
_MARKER_CODES = frozenset({"corrupted", "corruptedDummy"})


# ── Dataclasses ─────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CorruptionMod:
    """One applied mod inside a corruption outcome.

    ``code`` is a property-code (same domain as properties.txt; resolved
    to ISC stats by the caller).  ``par`` is the raw parameter string
    from the ``mod N param`` cubemain column - skill name for oskill-
    style mods, class code for class-specific bonuses, empty for plain
    numerical mods.  ``min_value``/``max_value`` are from the cubemain
    row - for corruption these are almost always identical (each tier
    awards a fixed number, not a rolled range).
    """

    code: str
    par: str
    min_value: float
    max_value: float

    @property
    def is_fixed(self) -> bool:
        """Return True if this mod has a fixed (non-random) value."""
        return self.min_value == self.max_value


@dataclass(frozen=True, slots=True)
class CorruptionOutcome:
    """One corruption tier for one item-type category.

    ``threshold`` is the inclusive lower bound the post-Phase-2 roll must
    satisfy (``roll >= threshold`` AND smaller than the next tier up).
    ``is_brick`` signals tiers that apply ONLY the corrupted markers
    (rolls 1-45).  ``row_index`` pins back to the source cubemain.txt
    line for debugging.
    """

    item_type: str
    threshold: int
    description: str
    mods: tuple[CorruptionMod, ...]
    row_index: int

    @property
    def is_brick(self) -> bool:
        """Return True if this outcome is a "bricked" corruption (no mods)."""
        return len(self.mods) == 0


# ── Database ────────────────────────────────────────────────────────────────


class CorruptionRollDatabase:
    """In-memory lookup ``(item_type, roll) -> CorruptionOutcome``.

    Stores outcomes sorted HIGH threshold first per item type so the
    ``first-match-wins`` semantics of the cube engine produce identical
    results here.
    """

    def __init__(self) -> None:
        # item_type -> list of outcomes sorted by threshold desc
        self._by_type: dict[str, list[CorruptionOutcome]] = {}
        self._loaded = False

    def load_from_rows(
        self,
        cubemain_rows: list[dict[str, str]],
        *,
        source: str = "<rows>",
    ) -> None:
        """Populate the database from pre-parsed cubemain.txt rows."""
        self._by_type.clear()
        for i, row in enumerate(cubemain_rows):
            if (row.get("input 2") or "").strip() != "ka3":
                continue
            if (row.get("op") or "").strip() != "15":
                continue
            try:
                threshold = int(row.get("value") or "")
            except ValueError:
                continue
            if threshold < 1:
                continue
            item_type = (row.get("input 1") or "").strip()
            if not item_type:
                continue
            mods = _extract_mods(row)
            outcome = CorruptionOutcome(
                item_type=item_type,
                threshold=threshold,
                description=(row.get("description") or "").strip(),
                mods=mods,
                row_index=i,
            )
            self._by_type.setdefault(item_type, []).append(outcome)

        # Sort each type's outcomes high->low threshold so a linear scan
        # naturally fires the "first match wins" semantic.
        for outcomes in self._by_type.values():
            outcomes.sort(key=lambda o: -o.threshold)

        self._loaded = True
        total = sum(len(v) for v in self._by_type.values())
        logger.info(
            "CorruptionRollDatabase: %d types, %d outcomes (from %s)",
            len(self._by_type),
            total,
            source,
        )

    def is_loaded(self) -> bool:
        """Return True if the database has been populated."""
        return self._loaded

    # ── Lookup API ──────────────────────────────────────────────────────

    def decode_roll(self, stat_362_value: int | None) -> int | None:
        """Convert the raw ``stat_362`` binary value to the real roll.

        Returns ``None`` when:
          * the stat is absent (no corruption),
          * or the value < 101 (phase 1 only - no mods applied yet).

        Otherwise returns ``stat_362_value - 101`` in the 0..100 range
        the cubemain thresholds use.
        """
        if stat_362_value is None:
            return None
        if stat_362_value < 101:
            return None
        return stat_362_value - 101

    def outcome_for(
        self,
        item_type: str,
        roll: int,
    ) -> CorruptionOutcome | None:
        """Return the matching ``CorruptionOutcome`` or ``None``.

        ``item_type`` is the short token from ``input 1`` (``amu`` /
        ``weap`` / ``shld`` / ...).  The caller is expected to have
        already mapped the save-file item code to this bucket via
        :meth:`map_item_code` below.
        """
        outcomes = self._by_type.get(item_type)
        if not outcomes:
            return None
        for outcome in outcomes:
            if roll >= outcome.threshold:
                return outcome
        return None

    def outcomes_for_type(
        self,
        item_type: str,
    ) -> tuple[CorruptionOutcome, ...]:
        """Return every outcome for the given item type (ordered)."""
        return tuple(self._by_type.get(item_type, ()))

    # ── Item-code bucketing ─────────────────────────────────────────────

    # Mapping from item-category tokens to the corruption bucket names
    # cubemain uses.  Weapons have a catch-all ``weap`` bucket; every
    # weapon subtype (sword, axe, bow, ...) maps to it.  Armor is split
    # into slot-specific buckets (helm, tors, glov, boot, belt, shld).
    # Rings and amulets are self-named.  Charms / jewels / runes /
    # materials are NOT corruptable in Reimagined -> return None.
    def map_item_code(self, item_code: str, item_types: "set[str]") -> str | None:
        """Return the corruption bucket for a save-file item or ``None``.

        ``item_types`` is the set of itype ancestors from ``itypes.txt``
        that the given ``item_code`` expands into (e.g. for a Large
        Shield ``tow`` the set contains ``shie``, ``shld``, ``armo``).
        Cubemain uses a mix of item codes (``amu``, ``rin``) and itype
        tokens (``shld``, ``tors``, ...), so we try both - the item code
        itself first, then its ancestors.
        """
        buckets = {"amu", "belt", "boot", "glov", "helm", "rin", "shld", "tors", "weap"}
        if item_code in buckets:
            return item_code
        for t in item_types:
            if t in buckets:
                return t
        return None


# ── Helpers ─────────────────────────────────────────────────────────────────


def _extract_mods(row: dict[str, str]) -> tuple[CorruptionMod, ...]:
    """Pull the non-marker ``mod N`` entries from a cubemain row.

    The game stores up to five mods per row; slots 4-5 typically carry
    the ``corrupted`` / ``corruptedDummy`` markers which we filter out
    because :class:`CorruptionMod` only represents the real stat
    bonuses the player cares about.
    """
    out: list[CorruptionMod] = []
    for i in range(1, _MAX_MOD_SLOTS + 1):
        code = (row.get(f"mod {i}") or "").strip()
        if not code:
            continue
        if code in _MARKER_CODES:
            continue
        mn = _parse_numeric(row.get(f"mod {i} min"))
        mx = _parse_numeric(row.get(f"mod {i} max"))
        if mn is None or mx is None:
            continue
        par = (row.get(f"mod {i} param") or "").strip()
        out.append(
            CorruptionMod(
                code=code,
                par=par,
                min_value=mn,
                max_value=mx,
            )
        )
    return tuple(out)


def _parse_numeric(v: object | None) -> float | None:
    """Return the first numeric token in ``s`` as an int, or None."""

    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ── Module-level singleton + loader ─────────────────────────────────────────

_CORRUPTION_DB = CorruptionRollDatabase()


def get_corruption_db() -> CorruptionRollDatabase:
    """Return the module-level :class:`CorruptionRollDatabase` singleton."""
    return _CORRUPTION_DB


def load_corruption_rolls(
    *,
    use_cache: bool = True,
    source_versions: "SourceVersions | None" = None,
    cache_dir: "Path | None" = None,
) -> None:
    """Populate the process-wide :class:`CorruptionRollDatabase`.

    Reads ``cubemain.txt`` through the standard Iron-Rule path
    (CASC -> Reimagined mod overlay).  Cached via
    :mod:`d2rr_toolkit.meta.cache` on subsequent calls; the disabled
    flag honours ``D2RR_DISABLE_GAME_DATA_CACHE=1`` as well.
    """

    def _build() -> None:

        rows = read_game_data_rows("data:data/global/excel/cubemain.txt")
        if not rows:
            logger.warning(
                "corruption_rolls: cubemain.txt returned no rows - corruption attribution disabled."
            )
            return
        _CORRUPTION_DB.load_from_rows(
            rows,
            source="data:data/global/excel/cubemain.txt",
        )

    cached_load(
        name="corruption_rolls",
        schema_version=SCHEMA_VERSION_CORRUPTION_ROLLS,
        singleton=_CORRUPTION_DB,
        build=_build,
        use_cache=use_cache,
        source_versions=source_versions,
        cache_dir=cache_dir,
    )

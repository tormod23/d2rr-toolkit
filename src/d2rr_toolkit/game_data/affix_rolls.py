"""Affix-roll-range database - resolves (context, stat_id) -> StatRollRange.

Consumers of :class:`FormattedProperty` that want to render a
perfect-roll indicator + ``[min-max]`` suffix need two things:

  1. The ``(min, max)`` range the stat COULD have rolled in.
  2. The source table the range came from (unique / set / runeword /
     magic-prefix / magic-suffix).

Both come from the same small set of D2R data files.  The game-data
cache already loads them for other purposes; this module adds a
resolver layer that indexes each table by the key ``ItemRollContext``
uses (``*ID`` for uniques/sets, row index for runes / magicprefix /
magicsuffix), expands property codes into ISC stat ids via
:class:`PropertiesDatabase`, and returns a pre-computed bundle per
``(source, row, slot)``.

The resolver is *pure data* - it never looks at a rolled value.
:class:`PropertyFormatter` owns the runtime comparison between
``StatRollRange.max_value`` and the item's current rolled value and
sets ``FormattedProperty.is_perfect`` accordingly.

Matching semantics (v1):

  * The primary match key is ``(stat_id, param)``, where ``param``
    is the integer the parser stored on the property dict (skill id,
    class index, tab index, ...) or ``0`` for param-free stats.
  * Table rows carry a string ``par`` column: a skill name, class
    code, or numeric token.  The resolver normalises it to an int
    through :class:`SkillDatabase` / :class:`CharStatsDatabase`; if
    normalisation fails or disagrees with the prop's param, the
    slot is ignored.  This keeps e.g. ``+1 Paladin Combat Skills``
    and ``+1 Paladin Offensive Skills`` from mis-merging.
  * Multiple slots on the same source row that target the same
    stat id AND param sum their ``(min, max)`` contributions and
    the resolver returns the aggregate range - matches what
    :class:`PropertyFormatter` does for the rolled value itself.

Performance: every query is O(max_slots_per_row) over at most five
source rows (unique OR set, plus 1 runeword, plus <=3 prefixes, plus
<=3 suffixes).  No file I/O; everything is pre-indexed at load time.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

from d2rr_toolkit.game_data._roll_types import (
    ItemRollContext,
    RollSource,
    StatRollRange,
)

if TYPE_CHECKING:
    from d2rr_toolkit.game_data.charstats import CharStatsDatabase
    from d2rr_toolkit.game_data.item_stat_cost import ItemStatCostDatabase
    from d2rr_toolkit.game_data.properties import PropertiesDatabase
    from d2rr_toolkit.game_data.skills import SkillDatabase
    from d2rr_toolkit.meta.source_versions import SourceVersions
from d2rr_toolkit.adapters.casc import read_game_data_rows
from d2rr_toolkit.meta import cached_load

logger = logging.getLogger(__name__)

# Bump when the internal row/slot dataclasses gain / lose / rename
# fields - gated by the cache helper via the standard
# ``SCHEMA_VERSION_*`` pattern.
SCHEMA_VERSION_AFFIX_ROLLS: int = 2  # +automagic index + dmg-norm broadcast

# Maximum slot count per source, straight from the TSV column
# definitions.  Used as a defensive upper bound; additional columns
# are silently ignored.
_MAX_UNIQUE_SLOTS = 12
_MAX_SET_OWN_SLOTS = 9  # setitems.txt prop1..prop9 (own affixes)
_MAX_MAGIC_AFFIX_SLOTS = 3  # magicprefix / magicsuffix: mod1..mod3
_MAX_RUNE_SLOTS = 7  # runes.txt T1Code1..T1Code7


# Class code -> binary class index, mirroring the mapping used by the
# property formatter.  Kept local so we don't couple to the formatter
# module order.
_CLASS_CODE_TO_INDEX: dict[str, int] = {
    "ama": 0,
    "sor": 1,
    "nec": 2,
    "pal": 3,
    "bar": 4,
    "dru": 5,
    "ass": 6,
    "war": 7,
}


# Property codes that do NOT declare an explicit ``stat1`` in
# properties.txt but still map to well-known ISC stats via the
# ``func1`` machinery the game uses at runtime.  Reimagined 3.0.7
# data (cross-checked against Lightsabre + a sweep of uniqueitems.txt)
# only exercises a handful of these, so a small hardcoded map is the
# right size for v1.  Any code absent from this map AND from
# properties.txt's own ``statN`` columns yields ``None`` from the
# resolver - the GUI then suppresses the range/star for that stat,
# which is better than guessing.
_PROP_CODE_FALLBACK_STATS: dict[str, tuple[int, ...]] = {
    # dmg% = Enhanced Damage (item_maxdamage_percent + item_mindamage_percent)
    "dmg%": (17, 18),
    # extra-fire / extra-cold / ... are skill damage percents.
    # Populate these on demand; every uniqueitems row that uses them
    # today still resolves through the ISC primary_stat because
    # properties.txt declares a stat1 for them.
}


# ── Internal row dataclasses ─────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _RolledSlot:
    """One ``(code, par, min, max)`` entry from a source-table row.

    ``code`` is a property-code string (from properties.txt); the
    resolver expands it to one or more ISC stat ids on demand via
    :class:`PropertiesDatabase`.  ``par`` is the raw string from
    the ``parN`` / ``modNparam`` / ``T1ParamN`` column - kept as
    text because the same column may hold a skill name, a class
    code, or a numeric token depending on the stat.
    """

    code: str
    par: str
    min_value: float
    max_value: float


@dataclass(frozen=True, slots=True)
class SlotContribution:
    """One (source, slot)->stat contribution for the breakdown resolver.

    ``fixed_amount`` is the exact value this slot contributed to the
    queried stat when that value is deterministic (slot min==max, or
    dual-stat damage pair where min/max encode the two stats' fixed
    values).  ``None`` means the actual rolled value lies somewhere in
    ``[min_value, max_value]`` and must be inferred from the observed
    stat minus other contributions.

    ``source_code`` is the raw property code from the source row
    (``dmg-norm``, ``res-ltng``, ...) - useful for source_detail strings
    and for callers that want to distinguish dual-stat from broadcast
    contributions post-hoc.
    """

    source: "RollSource"
    source_code: str
    fixed_amount: float | None
    min_value: float
    max_value: float
    is_fixed: bool


@dataclass(frozen=True, slots=True)
class _RolledRow:
    """A single source-table row (one unique, one set item, ...).

    ``slots`` preserves the column order of the source TSV so the
    resolver can iterate predictably and the tests can pin specific
    slot indices to their expected values.
    """

    slots: tuple[_RolledSlot, ...]


# ── AffixRollDatabase ────────────────────────────────────────────────────────


class AffixRollDatabase:
    """In-memory index of roll ranges by source + row + stat id.

    Populated once per process via :func:`load_affix_rolls` (cached
    by the standard game-data cache) and queried on every tooltip
    render.  Instances are pickle-friendly so the cache's snapshot
    /restore round-trips cleanly.
    """

    def __init__(self) -> None:
        # Key: *ID (uniqueitems.txt / setitems.txt `*ID` column).
        self._uniques: dict[int, _RolledRow] = {}
        self._sets_own: dict[int, _RolledRow] = {}
        # Key: row index (0-based, matching the parser's field).
        self._magicprefix: dict[int, _RolledRow] = {}
        self._magicsuffix: dict[int, _RolledRow] = {}
        self._runes: dict[int, _RolledRow] = {}
        # Key: row index into automagic.txt (1-based in the parser -
        # the stored automod_id == 0 means "no automod", anything
        # above is ``row_index = stored - 1``).  automagic rows use
        # the same mod1/2/3 schema as magicprefix.txt.
        self._automagic: dict[int, _RolledRow] = {}
        self._loaded = False

    # ── Loading ────────────────────────────────────────────────────────────

    def load_from_rows(
        self,
        *,
        uniqueitems_rows: list[dict[str, str]],
        setitems_rows: list[dict[str, str]],
        magicprefix_rows: list[dict[str, str]],
        magicsuffix_rows: list[dict[str, str]],
        runes_rows: list[dict[str, str]],
        automagic_rows: list[dict[str, str]] | None = None,
        source: str = "<rows>",
    ) -> None:
        """Populate every index from pre-parsed TSV rows."""
        self._uniques.clear()
        self._sets_own.clear()
        self._magicprefix.clear()
        self._magicsuffix.clear()
        self._automagic.clear()
        self._runes.clear()

        for row in uniqueitems_rows:
            sid = _maybe_int(row.get("*ID"))
            if sid is None:
                continue
            parsed = _parse_numbered_slots(
                row, "prop", "par", "min", "max", limit=_MAX_UNIQUE_SLOTS
            )
            if parsed:
                self._uniques[sid] = _RolledRow(slots=parsed)

        for row in setitems_rows:
            sid = _maybe_int(row.get("*ID"))
            if sid is None:
                continue
            parsed = _parse_numbered_slots(
                row, "prop", "par", "min", "max", limit=_MAX_SET_OWN_SLOTS
            )
            if parsed:
                self._sets_own[sid] = _RolledRow(slots=parsed)

        for idx, row in enumerate(magicprefix_rows):
            parsed = _parse_numbered_slots(
                row, "mod", "param", "min", "max", limit=_MAX_MAGIC_AFFIX_SLOTS, code_suffix="code"
            )
            if parsed:
                self._magicprefix[idx] = _RolledRow(slots=parsed)

        for idx, row in enumerate(magicsuffix_rows):
            parsed = _parse_numbered_slots(
                row, "mod", "param", "min", "max", limit=_MAX_MAGIC_AFFIX_SLOTS, code_suffix="code"
            )
            if parsed:
                self._magicsuffix[idx] = _RolledRow(slots=parsed)

        for idx, row in enumerate(runes_rows):
            parsed = _parse_numbered_slots(
                row, "T1Code", "T1Param", "T1Min", "T1Max", limit=_MAX_RUNE_SLOTS, code_suffix=""
            )
            if parsed:
                self._runes[idx] = _RolledRow(slots=parsed)

        if automagic_rows:
            for idx, row in enumerate(automagic_rows):
                parsed = _parse_numbered_slots(
                    row,
                    "mod",
                    "param",
                    "min",
                    "max",
                    limit=_MAX_MAGIC_AFFIX_SLOTS,
                    code_suffix="code",
                )
                if parsed:
                    self._automagic[idx] = _RolledRow(slots=parsed)

        self._loaded = True
        logger.info(
            "AffixRollDatabase: %d uniques, %d sets, %d magicprefix, "
            "%d magicsuffix, %d runes loaded from %s",
            len(self._uniques),
            len(self._sets_own),
            len(self._magicprefix),
            len(self._magicsuffix),
            len(self._runes),
            source,
        )

    def is_loaded(self) -> bool:
        """Return True if the database has been populated."""
        return self._loaded

    # ── Resolver API ───────────────────────────────────────────────────────

    def resolve(
        self,
        ctx: "ItemRollContext",
        stat_id: int,
        *,
        param: int = 0,
        isc_db: "ItemStatCostDatabase",
        props_db: "PropertiesDatabase",
        skills_db: "SkillDatabase | None" = None,
        charstats_db: "CharStatsDatabase | None" = None,
    ) -> "StatRollRange | None":
        """Return the effective :class:`StatRollRange` for one stat.

        Walks every source referenced by ``ctx`` and sums every
        matching slot's ``(min, max)`` contribution.  Returns the
        aggregated range, or ``None`` when no source matched.

        When two different sources both match (e.g. a Unique with
        both its row-level stat AND a magic affix of the same stat
        id - impossible on a real item but legal in synthetic
        tests), the first non-None source wins in priority order
        Unique -> Set -> Runeword -> Magic prefix -> Magic suffix.
        """
        # Compound-encoded stats (encode=2 skill-event, encode=3
        # skill-charges) pack multiple semantic fields (chance, level,
        # skill id, ...) into one binary value.  The source row's
        # ``min`` / ``max`` columns store TWO of those fields, not a
        # rolling window for a single value.  Displaying [min-max] for
        # such stats is misleading (see Spring Facet bug: CTC level 47
        # + chance 100 rendered as "[47-100]" range + star).  Treat as
        # un-rollable.
        stat_def = isc_db.get(stat_id)
        if stat_def is not None and stat_def.encode in (2, 3):
            return None

        # Source priority order intentionally stable across runs so
        # the resolver's output is deterministic for tests.
        for source, rows in self._iter_sources(ctx):
            aggregate_min: float | None = None
            aggregate_max: float | None = None
            for row in rows:
                for slot in row.slots:
                    if not self._slot_matches(
                        slot,
                        stat_id,
                        param,
                        isc_db=isc_db,
                        props_db=props_db,
                        skills_db=skills_db,
                        charstats_db=charstats_db,
                    ):
                        continue
                    if aggregate_min is None:
                        aggregate_min = slot.min_value
                        aggregate_max = slot.max_value
                    else:
                        # ``aggregate_max`` is set in lockstep with
                        # ``aggregate_min`` above; both move together.
                        assert aggregate_max is not None
                        aggregate_min += slot.min_value
                        aggregate_max += slot.max_value
            if aggregate_min is not None and aggregate_max is not None:
                # Normalise so (min, max) always satisfies min <= max
                # - some affixes use negative-is-better encoding with
                # min < max in absolute terms but numerically swapped.
                lo, hi = sorted((aggregate_min, aggregate_max))
                return StatRollRange(min_value=lo, max_value=hi, source=source)
        return None

    # ── Breakdown API (per-slot contributions, no suppression) ─────────

    def iter_slot_contributions(
        self,
        ctx: "ItemRollContext",
        stat_id: int,
        *,
        param: int = 0,
        isc_db: "ItemStatCostDatabase",
        props_db: "PropertiesDatabase",
        skills_db: "SkillDatabase | None" = None,
        charstats_db: "CharStatsDatabase | None" = None,
    ) -> list["SlotContribution"]:
        """Yield per-slot contributions to ``stat_id`` without suppression.

        Unlike :meth:`resolve`, this method does NOT collapse the dual-stat
        damage-pair heuristic: it returns one
        :class:`SlotContribution` per slot-stat pair that actually
        contributes to ``stat_id``.  For dual-stat damage codes (``dmg-norm``,
        ``dmg-fire``, ``dmg-pois``, ...) this surfaces the fixed per-side
        value (slot.min for min-stat, slot.max for max-stat) - which is
        exactly what the breakdown resolver needs to attribute the rolled
        value without mis-representing it as a range.

        Single-stat slots and broadcast multi-stat slots (``all-stats``,
        ``res-all``, ...) surface with ``(range_min, range_max)`` equal to
        the slot's own min/max columns - the breakdown resolver then
        infers the rolled value from the observation.
        """
        out: list[SlotContribution] = []
        for source, rows in self._iter_sources(ctx):
            for row in rows:
                for slot in row.slots:
                    contrib = self._slot_contribution_to(
                        slot,
                        stat_id,
                        param=param,
                        source=source,
                        isc_db=isc_db,
                        props_db=props_db,
                        skills_db=skills_db,
                        charstats_db=charstats_db,
                    )
                    if contrib is not None:
                        out.append(contrib)
        return out

    def _slot_contribution_to(
        self,
        slot: _RolledSlot,
        stat_id: int,
        *,
        param: int,
        source: "RollSource",
        isc_db: "ItemStatCostDatabase",
        props_db: "PropertiesDatabase",
        skills_db: "SkillDatabase | None",
        charstats_db: "CharStatsDatabase | None",
    ) -> "SlotContribution | None":
        """Compute a single slot's per-stat contribution.

        Returns ``None`` when the slot does not touch ``stat_id``.  For
        dual-stat damage slots the returned :class:`SlotContribution`
        has ``is_fixed=True`` and ``fixed_amount`` set to the side of
        the min/max pair that matches ``stat_id``.
        """
        prop_def = props_db.get(slot.code)
        declared_names: list[str] = []
        declared_stat_ids: list[int] = []
        if prop_def is not None:
            for name in prop_def.stat_names():
                if not name:
                    continue
                declared_names.append(name)
                sd = isc_db.get_by_name(name)
                if sd is not None:
                    declared_stat_ids.append(sd.stat_id)

        fallback_stat_ids = list(_PROP_CODE_FALLBACK_STATS.get(slot.code, ()))
        all_stat_ids = declared_stat_ids + fallback_stat_ids

        # Normal-weapon-damage broadcast: the D2 engine stores the slot
        # value on ALL three weapon-damage families (1H / 2H / throw).
        # dmg-norm is the dual-stat variant (min -> 21/23/159, max -> 22
        # /24/160).  dmg-min broadcasts only to the three MIN stats
        # with the rolled value in [slot.min, slot.max].  dmg-max
        # broadcasts only to the three MAX stats.  See
        # _DMG_NORM_DUAL_CODES / _DMG_MIN_ONLY_CODES / _DMG_MAX_ONLY_CODES.
        dmg_norm_broadcast = False
        dmg_min_only_broadcast = False
        dmg_max_only_broadcast = False
        if slot.code in _DMG_NORM_DUAL_CODES and stat_id in _DMG_NORM_REPLICATION_STATS:
            dmg_norm_broadcast = True
        elif slot.code in _DMG_MIN_ONLY_CODES and stat_id in _DMG_NORM_MIN_STATS:
            dmg_min_only_broadcast = True
        elif slot.code in _DMG_MAX_ONLY_CODES and stat_id in _DMG_NORM_MAX_STATS:
            dmg_max_only_broadcast = True
        elif stat_id not in all_stat_ids:
            return None

        # Param guard: same semantics as _slot_matches.
        if slot.par:
            slot_param = _normalise_param(
                slot.par,
                skills_db=skills_db,
                charstats_db=charstats_db,
            )
            if slot_param is not None and param != 0 and slot_param != param:
                return None

        # Dual-stat damage-pair detection (same rule as _slot_matches).
        dual_stat = _is_dual_stat_damage_slot(declared_names)

        # dmg-norm dual-stat broadcast: slot.min -> min-stat family,
        # slot.max -> max-stat family.  Each side is fixed.
        if dmg_norm_broadcast:
            for min_sid, max_sid in _DMG_NORM_REPLICATION_PAIRS:
                if stat_id == min_sid:
                    val = float(slot.min_value)
                    return SlotContribution(
                        source=source,
                        source_code=slot.code,
                        fixed_amount=val,
                        min_value=val,
                        max_value=val,
                        is_fixed=True,
                    )
                if stat_id == max_sid:
                    val = float(slot.max_value)
                    return SlotContribution(
                        source=source,
                        source_code=slot.code,
                        fixed_amount=val,
                        min_value=val,
                        max_value=val,
                        is_fixed=True,
                    )

        # dmg-min / dmg-max single-side broadcast: the rolled value sits
        # somewhere in [slot.min, slot.max] and is applied to all three
        # stats on the corresponding side.  Treat as a rolled (non-
        # fixed) contribution unless the slot has zero width.
        if dmg_min_only_broadcast or dmg_max_only_broadcast:
            lo = float(slot.min_value)
            hi = float(slot.max_value)
            if lo > hi:
                lo, hi = hi, lo
            is_fixed = lo == hi
            return SlotContribution(
                source=source,
                source_code=slot.code,
                fixed_amount=lo if is_fixed else None,
                min_value=lo,
                max_value=hi,
                is_fixed=is_fixed,
            )

        if dual_stat and len(declared_stat_ids) >= 2:
            # Collect every declared stat by its name role.  Damage
            # codes come in three flavours:
            #   * 2-stat:  dmg-norm / dmg-fire / dmg-cold / dmg-ltng -
            #     one min + one max (+ optional length for cold/pois)
            #   * 3-stat:  dmg-pois / dmg-cold - same + length column
            #   * 7-stat:  dmg-elem - 3 min (fire/ltng/cold) + 3 max
            #     + coldlength.  slot.min broadcasts to ALL min stats,
            #     slot.max broadcasts to ALL max stats, slot.par holds
            #     the cold length (only coldlength listed, no fire/ltng
            #     length per game engine).
            # We therefore collect LISTS, not single values.
            min_side_stats: list[int] = []
            max_side_stats: list[int] = []
            length_stats: list[int] = []
            for sid, name in zip(declared_stat_ids, declared_names):
                low = name.lower()
                if "length" in low:
                    length_stats.append(sid)
                elif "min" in low:
                    min_side_stats.append(sid)
                elif "max" in low:
                    max_side_stats.append(sid)
            if stat_id in min_side_stats:
                val = float(slot.min_value)
                return SlotContribution(
                    source=source,
                    source_code=slot.code,
                    fixed_amount=val,
                    min_value=val,
                    max_value=val,
                    is_fixed=True,
                )
            if stat_id in max_side_stats:
                val = float(slot.max_value)
                return SlotContribution(
                    source=source,
                    source_code=slot.code,
                    fixed_amount=val,
                    min_value=val,
                    max_value=val,
                    is_fixed=True,
                )
            if stat_id in length_stats:
                # Length stats (coldlength=56, poisonlength=59) come
                # from the slot's ``par`` column, not min/max.
                # Value is a frame count (25 frames = 1 second).
                try:
                    val = float(slot.par)
                except TypeError, ValueError:
                    val = 0.0
                return SlotContribution(
                    source=source,
                    source_code=slot.code,
                    fixed_amount=val,
                    min_value=val,
                    max_value=val,
                    is_fixed=True,
                )
            # Fallthrough: neither side matched (unexpected) - treat
            # as a rolled single-stat contribution.

        # Single-stat OR broadcast OR fallback-mapped slot: the rolled
        # value for this stat is somewhere in [slot.min, slot.max].
        lo = float(slot.min_value)
        hi = float(slot.max_value)
        if lo > hi:
            lo, hi = hi, lo
        is_fixed = lo == hi
        return SlotContribution(
            source=source,
            source_code=slot.code,
            fixed_amount=lo if is_fixed else None,
            min_value=lo,
            max_value=hi,
            is_fixed=is_fixed,
        )

    # ── Internal helpers ──────────────────────────────────────────────────

    def _iter_sources(
        self,
        ctx: "ItemRollContext",
    ) -> Iterable[tuple["RollSource", list[_RolledRow]]]:
        """Yield ``(source_tag, [rows])`` in priority order.

        Priority (stable):
          1. Unique row (ctx.unique_id)
          2. Set own-stats row (ctx.set_id)
          3. Runeword row (ctx.runeword_id)
          4. Magic prefixes (ctx.prefix_ids - multiple possible)
          5. Magic suffixes (ctx.suffix_ids - multiple possible)

        Callers walk the yielded list and stop at the first source
        that contributes a matching slot.
        """
        if ctx.unique_id is not None:
            row = self._uniques.get(ctx.unique_id)
            if row is not None:
                yield ("unique", [row])
        if ctx.set_id is not None:
            row = self._sets_own.get(ctx.set_id)
            if row is not None:
                yield ("set", [row])
        if ctx.runeword_id is not None:
            row = self._runes.get(ctx.runeword_id)
            if row is not None:
                yield ("runeword", [row])
        if ctx.prefix_ids:
            rows = [r for pid in ctx.prefix_ids if (r := self._magicprefix.get(pid)) is not None]
            if rows:
                # Magic / Rare distinction is purely presentational
                # for v1 - both use magicprefix as the roll source.
                # The ``source`` tag reflects whichever interpretation
                # the caller considers canonical.  v1 uses
                # "magic_prefix" as the tag; "rare_prefix" is
                # reserved for a future pass if needed.
                yield ("magic_prefix", rows)
        if ctx.suffix_ids:
            rows = [r for sid in ctx.suffix_ids if (r := self._magicsuffix.get(sid)) is not None]
            if rows:
                yield ("magic_suffix", rows)
        # automod source intentionally NOT yielded here.  Empirical
        # tests against the full VikingBarbie live-save show that
        # charms with ``automod_id`` pointing to automagic.txt rows
        # 22-25 ("Shimmering" / "Rainbow" / ...) don't actually receive
        # the ``res-all`` mod on their stat rolls - only the
        # ``oskill_hide`` sub-mod (Hidden Charm Passive, skill 449)
        # applies.  The automagic.txt ``itype`` columns list
        # ``armo``/``weap`` but the Reimagined engine routes charms
        # through the slot for the passive bonus only.  Yielding the
        # full automagic row as a contribution would double-count
        # stats that the prefix already provides; leaving it
        # unattributed here defers the leftover to the breakdown
        # resolver's ``unknown_modifier`` fallback instead.

    def _slot_matches(
        self,
        slot: _RolledSlot,
        stat_id: int,
        param: int,
        *,
        isc_db: "ItemStatCostDatabase",
        props_db: "PropertiesDatabase",
        skills_db: "SkillDatabase | None",
        charstats_db: "CharStatsDatabase | None",
    ) -> bool:
        """Test whether a slot contributes to ``(stat_id, param)``.

        A match requires ALL of:
          * ``slot.code`` expands to at least one ISC stat whose
            ``stat_id`` equals the caller's ``stat_id`` - OR matches
            via one of the damage-group follower mappings (e.g.
            ``dmg-norm`` -> stats 21 and 22 are both valid).
          * Either the slot has no ``par``, OR the slot's ``par``
            normalises to an integer equal to the caller's ``param``.
            A slot with an empty ``par`` matches any param - this is
            the correct behaviour for most rolled stats (damage,
            resistances, attributes).  Slots with a ``par`` value
            (skill-on-event, class skills) only match when the
            params agree, so ``+1 Paladin Combat Skills`` doesn't
            merge with ``+1 Paladin Defensive Skills``.
        """
        # ── Stat-id match ─────────────────────────────────────────────
        # Resolve the slot's property code to one or more ISC stat
        # ids.  Primary source: properties.txt's declared statN
        # columns (via ``PropertiesDatabase``).  Fallback: the
        # hardcoded ``_PROP_CODE_FALLBACK_STATS`` map for codes like
        # ``dmg%`` that use func1-only expansion with no statN
        # column in properties.txt.
        prop_def = props_db.get(slot.code)
        candidate_stat_ids: set[int] = set()
        declared_names: list[str] = []
        if prop_def is not None:
            for slot_stat_name in prop_def.stat_names():
                if not slot_stat_name:
                    continue
                declared_names.append(slot_stat_name)
                stat_def = isc_db.get_by_name(slot_stat_name)
                if stat_def is not None:
                    candidate_stat_ids.add(stat_def.stat_id)

        # Dual-stat single-slot encoding: property codes like
        # ``dmg-norm`` / ``dmg-fire`` / ``dmg2%`` / ``flat-dmg/lvl``
        # declare exactly two stats where one is the "min" half and
        # the other the "max" half of a damage-like pair.  The slot's
        # ``min`` column supplies the fixed value for the min-stat,
        # and ``max`` supplies the fixed value for the max-stat -
        # NEITHER column is a rolling window.  Without this guard the
        # resolver would emit e.g. "Adds 63-511 Fire Damage [63-511]"
        # on Conclave of Elements, as reported from the live FrozenOrbHydra
        # save.  Detect via the ``min`` / ``max`` substring heuristic
        # rather than a hardcoded allowlist so future Reimagined data
        # drops that add new dual-stat damage codes keep working.
        if _is_dual_stat_damage_slot(declared_names):
            return False

        candidate_stat_ids.update(_PROP_CODE_FALLBACK_STATS.get(slot.code, ()))
        if stat_id not in candidate_stat_ids:
            return False

        # ── Param match ──────────────────────────────────────────────
        # Empty par: wildcard (damage / resist / attr stats).
        if not slot.par:
            return True
        slot_param = _normalise_param(
            slot.par,
            skills_db=skills_db,
            charstats_db=charstats_db,
        )
        if slot_param is None:
            # Un-normalisable par - treat as a loose match so an
            # unexpected column value doesn't silently reject.
            return True
        # When the caller's param is 0 the stat either has no
        # parameter OR the parser couldn't recover one.  Slots with
        # a non-zero param like ``"1"`` on ``ignore-ac`` are genuine
        # flag values, not discriminators between distinct variants;
        # accepting loosely here matches the intended semantics:
        # two affixes that produce the SAME stat id with DIFFERENT
        # par values are distinct stats. Distinct-par-distinct-stat
        # only applies when BOTH sides have a non-zero param.
        if param == 0:
            return True
        return slot_param == param


# ── Module-level helpers ─────────────────────────────────────────────────────

# Stats that are treated as members of the same damage group for the
# "dmg-norm" / "dmg-ltng" / "dmg-fire" style expansions.  Each entry is
# (lead_stat_id, follower_stat_id) where either stat legitimately pairs
# with the same property code's min/max columns.
_DAMAGE_SIBLING_GROUPS: tuple[tuple[int, int], ...] = (
    (21, 22),  # mindamage / maxdamage
    (23, 24),  # secondary_mindamage / secondary_maxdamage
    (48, 49),  # item_fire_mindamage / item_fire_maxdamage
    (50, 51),  # item_ltng_mindamage / item_ltng_maxdamage
    (52, 53),  # item_mag_mindamage / item_mag_maxdamage
    (54, 55),  # item_cold_mindamage / item_cold_maxdamage
    (57, 58),  # item_pos_mindamage / item_pos_maxdamage
    (159, 160),  # item_throw_mindamage / item_throw_maxdamage
)
_DAMAGE_SIBLING_PAIRS: frozenset[tuple[int, int]] = frozenset(
    pair for lo, hi in _DAMAGE_SIBLING_GROUPS for pair in ((lo, hi), (hi, lo))
)


# Replication groups for "normal weapon damage" - the D2 engine
# broadcasts ``dmg-norm`` / ``dmg-min`` / ``dmg-max`` slot values to all
# three damage-pair families the engine tracks per weapon: 1H (21,22),
# 2H (23,24) and throw (159,160).  The parser faithfully stores all six
# stats on the item so the breakdown resolver must attribute them all
# to the same single slot contribution.  The tuples are (min_stat,
# max_stat) pairs; a slot awards its ``slot.min`` to each min-side and
# its ``slot.max`` to each max-side.
_DMG_NORM_REPLICATION_PAIRS: tuple[tuple[int, int], ...] = (
    (21, 22),  # mindamage / maxdamage      - 1H
    (23, 24),  # secondary_min / secondary_max - 2H
    (159, 160),  # item_throw_min / item_throw_max
)
_DMG_NORM_REPLICATION_STATS: frozenset[int] = frozenset(
    s for pair in _DMG_NORM_REPLICATION_PAIRS for s in pair
)
_DMG_NORM_MIN_STATS: frozenset[int] = frozenset(p[0] for p in _DMG_NORM_REPLICATION_PAIRS)
_DMG_NORM_MAX_STATS: frozenset[int] = frozenset(p[1] for p in _DMG_NORM_REPLICATION_PAIRS)

# Property codes whose slot value broadcasts to all three normal-weapon
# damage-pair families (1H / 2H / throw).  ``dmg-norm`` is the dual-
# stat variant (slot.min -> min-stat family, slot.max -> max-stat family);
# ``dmg-min`` / ``dmg-max`` are single-side variants whose slot.min/max
# columns form the roll window of the rolled value applied to ALL min
# (resp. max) stats in the three families.
_DMG_NORM_DUAL_CODES: frozenset[str] = frozenset({"dmg-norm"})
_DMG_MIN_ONLY_CODES: frozenset[str] = frozenset({"dmg-min"})
_DMG_MAX_ONLY_CODES: frozenset[str] = frozenset({"dmg-max"})


def _are_damage_siblings(a: int, b: int) -> bool:
    """Return True iff ``a`` and ``b`` are a known damage-group pair."""
    return (a, b) in _DAMAGE_SIBLING_PAIRS


def _is_dual_stat_damage_slot(declared_names: list[str]) -> bool:
    """Return True iff the slot's declared stats are a min/max pair.

    Matches every property code whose ``prop_def`` declares two or
    more ISC stats where at least one name contains ``min``
    (case-insensitive) and at least one contains ``max``.  Covers:

      * 2-stat damage pairs: ``dmg-norm`` (mindamage/maxdamage),
        ``dmg-fire``, ``dmg-cold``, ``dmg-ltng``, ``dmg-mag`` -
        slot.min feeds the min-stat, slot.max feeds the max-stat.
      * 2-stat percent pairs: ``dmg%`` - wait, this one's declared
        as 0 stats (see _PROP_CODE_FALLBACK_STATS) so isn't hit here.
      * 2-stat Reimagined extras: ``dmg2%`` (pl_min/maxdamage_percent),
        ``dmg3%`` (pl_min/maxthrowdmg_percent), ``flat-dmg/lvl``
        (item_min/maxdamage_perlvl).
      * 3-stat poison: ``dmg-pois`` (poisonmindam / poisonmaxdam /
        poisonlength) - slot.min/max are two fixed per-frame damage
        values, slot.par is the duration in frames.  Reported from
        VikingBarbie's "Foul Grand Charm of Vita" where the raw
        magicprefix row [280, 360] was surfaced as a tooltip range
        despite actually being two fixed internal-unit values that
        the formatter scales to the displayed "Adds 82-105 Poison
        Damage over 3 Seconds" via the poisonlength multiplier.

    Broadcast-style multi-stat codes (``all-stats`` -> 4 attributes
    all named ``strength``/``dexterity``/..., ``res-all`` -> 4 resists
    named ``fireresist``/..., ``fireskill`` -> ``item_elemskill`` +
    ``item_elemskillfire``) have no ``min``/``max`` substrings and
    correctly fall through to the range-attaching path.
    """
    if len(declared_names) < 2:
        return False
    lows = [n.lower() for n in declared_names]
    has_min = any("min" in n for n in lows)
    has_max = any("max" in n for n in lows)
    return has_min and has_max


def _normalise_param(
    par: str,
    *,
    skills_db: "SkillDatabase | None",
    charstats_db: "CharStatsDatabase | None",
) -> int | None:
    """Coerce a raw ``par`` column to the integer the parser stores.

    Accepts:
      * Plain integers (``"1"``, ``"53"``) - returned as-is.
      * Skill names (``"Chain Lightning"``) via :meth:`SkillDatabase.id_by_name`.
      * Class codes (``"pal"`` / ``"sor"`` / ...) via the fixed 0..7 map.
      * Empty / whitespace - returns None (meaning "ignore param match").

    Returns ``None`` when the par isn't recognisable - the caller
    then treats the slot as a loose match.
    """
    s = par.strip()
    if not s:
        return None
    # Direct numeric
    try:
        return int(s)
    except ValueError:
        pass
    # Class code
    low = s.lower()
    if low in _CLASS_CODE_TO_INDEX:
        return _CLASS_CODE_TO_INDEX[low]
    # Skill name
    if skills_db is not None:
        sid = skills_db.id_by_name(s)
        if sid is not None:
            return sid
    return None


def _maybe_int(v: object | None) -> int | None:
    """Tolerant int coercion - returns None on empty / non-numeric."""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _parse_numbered_slots(
    row: dict[str, str],
    code_prefix: str,
    par_prefix: str,
    min_prefix: str,
    max_prefix: str,
    *,
    limit: int,
    code_suffix: str = "",
) -> tuple[_RolledSlot, ...]:
    """Extract a row's numbered slot columns into ``_RolledSlot`` tuples.

    Handles the two column-layout flavours that appear in the live
    tables:

      * ``prop1``, ``par1``, ``min1``, ``max1`` (uniqueitems / setitems)
        - pass ``code_suffix=""`` and ``code_prefix="prop"``.
      * ``mod1code``, ``mod1param``, ``mod1min``, ``mod1max``
        (magicprefix / magicsuffix) - pass ``code_suffix="code"`` and
        ``code_prefix="mod"``; the ``_{i}_`` is inserted between.
      * ``T1Code1``, ``T1Param1``, ``T1Min1``, ``T1Max1``
        (runes.txt) - pass ``code_suffix=""`` and prefixes ``T1Code``
        etc. with the numeric slot suffix already part of the prefix
        syntax.

    Empty slots (empty code) are skipped; the first non-empty slot
    and every subsequent non-empty slot are preserved in order.
    """
    slots: list[_RolledSlot] = []
    for i in range(1, limit + 1):
        if code_suffix:
            # magicprefix.txt style: mod1code, mod1param, mod1min, mod1max
            code_col = f"{code_prefix}{i}{code_suffix}"
            par_col = f"{code_prefix}{i}{par_prefix}"
            min_col = f"{code_prefix}{i}{min_prefix}"
            max_col = f"{code_prefix}{i}{max_prefix}"
        else:
            # uniqueitems.txt / setitems.txt / runes.txt style:
            # prop1, par1, min1, max1  OR  T1Code1, T1Param1, T1Min1, T1Max1
            code_col = f"{code_prefix}{i}"
            par_col = f"{par_prefix}{i}"
            min_col = f"{min_prefix}{i}"
            max_col = f"{max_prefix}{i}"
        code = (row.get(code_col) or "").strip()
        if not code:
            continue
        par = (row.get(par_col) or "").strip()
        min_v = _parse_numeric(row.get(min_col))
        max_v = _parse_numeric(row.get(max_col))
        if min_v is None or max_v is None:
            # Incomplete slot - skip rather than guess.
            continue
        slots.append(
            _RolledSlot(
                code=code,
                par=par,
                min_value=min_v,
                max_value=max_v,
            )
        )
    return tuple(slots)


def _parse_numeric(v: object | None) -> float | None:
    """Parse a min/max column value.  Accepts int-ish or float-ish."""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ── Module-level singleton + loader ──────────────────────────────────────────

_AFFIX_ROLL_DB = AffixRollDatabase()


def get_affix_roll_db() -> AffixRollDatabase:
    """Return the process-wide :class:`AffixRollDatabase` instance."""
    return _AFFIX_ROLL_DB


def load_affix_rolls(
    *,
    use_cache: bool = True,
    source_versions: "SourceVersions | None" = None,
    cache_dir: "Path | None" = None,
) -> None:
    """Populate the :class:`AffixRollDatabase` from the game data.

    Reads five tables through the Iron Rule:

      * ``uniqueitems.txt`` - row-level prop/par/min/max slots.
      * ``setitems.txt`` - own-stats (prop1..9); set-bonus slots
        (``aprop*``) are handled separately by the formatter and
        therefore NOT indexed here.
      * ``magicprefix.txt`` / ``magicsuffix.txt`` - up to 3 rolled
        mod slots each.
      * ``runes.txt`` - up to 7 runeword stat slots per row.

    Transparently backed by the persistent pickle cache - see
    :mod:`d2rr_toolkit.meta.cache` / ``GAME_DATA_CACHE.md``.  When
    the cache is disabled the cold parse takes ~30 ms on Reimagined
    3.0.7 data; warm hit is under 10 ms.

    Args:
        use_cache: ``False`` skips the persistent cache for this
            call only; also honoured via the
            ``D2RR_DISABLE_GAME_DATA_CACHE=1`` env var.
        source_versions: Optional :class:`SourceVersions`.
        cache_dir: Optional cache root override.
    """

    def _build() -> None:

        u_rows = read_game_data_rows("data:data/global/excel/uniqueitems.txt")
        s_rows = read_game_data_rows("data:data/global/excel/setitems.txt")
        p_rows = read_game_data_rows("data:data/global/excel/magicprefix.txt")
        x_rows = read_game_data_rows("data:data/global/excel/magicsuffix.txt")
        r_rows = read_game_data_rows("data:data/global/excel/runes.txt")
        a_rows = read_game_data_rows("data:data/global/excel/automagic.txt")
        if not (u_rows or s_rows or p_rows or x_rows or r_rows):
            logger.warning(
                "affix_rolls: no source tables found - roll ranges will "
                "be unavailable.  Item tooltips fall back to "
                "roll_ranges=() / is_perfect=False everywhere."
            )
            return
        _AFFIX_ROLL_DB.load_from_rows(
            uniqueitems_rows=u_rows,
            setitems_rows=s_rows,
            magicprefix_rows=p_rows,
            magicsuffix_rows=x_rows,
            runes_rows=r_rows,
            automagic_rows=a_rows,
            source="data:data/global/excel/{uniqueitems,setitems,magic*,runes,automagic}.txt",
        )

    cached_load(
        name="affix_rolls",
        schema_version=SCHEMA_VERSION_AFFIX_ROLLS,
        singleton=_AFFIX_ROLL_DB,
        build=_build,
        use_cache=use_cache,
        source_versions=source_versions,
        cache_dir=cache_dir,
    )

"""
Converts parsed item property dicts to human-readable display strings.

Lookup chain for a standard property (Encode 0):
  prop["stat_id"] -> ISC StatDefinition -> descstrpos key
  -> item-modifiers.json template (e.g. "%+d to Strength")
  -> substitute %+d/%d/%s with prop["value"]/param/skill_name
  -> "+25 to Strength"

Lookup chain for a set bonus property code (from sets.txt/setitems.txt):
  code (e.g. "res-fire") -> PropertiesDatabase -> stat_name
  -> ISC by-name -> StatDefinition -> descstrpos key -> template -> display string

Template placeholder conventions (item-modifiers.json):
  %+d   signed integer with sign (e.g. +25 or -10)
  %d    unsigned integer (25)
  %+d%% signed percent (+25%)
  %d%%  unsigned percent (25%)
  %s    string (skill name, class name, etc.)
  %%    literal percent sign

Special stat groups displayed as one line:
  Stats 48+49: "Adds X-Y Fire Damage"
  Stats 50+51: "Adds X-Y Lightning Damage"
  Stats 52+53: "Adds X-Y Magic Damage"
  Stats 54+55: "Adds X-Y Cold Damage"
  Stats 57+58: "Adds X-Y Poison Damage over Z seconds"
  Stats 17+18: "+X% Enhanced Damage" (combined, show 17's value only)

[i18n note: lang parameter accepted everywhere; currently only enUS supported.
 Extend StringsDatabase.get() calls to pass lang when i18n is needed.]
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Literal

if TYPE_CHECKING:
    from d2rr_toolkit.game_data.item_stat_cost import ItemStatCostDatabase, StatDefinition
    from d2rr_toolkit.game_data.item_types import ItemTypeDatabase
    from d2rr_toolkit.game_data.properties import PropertiesDatabase
    from d2rr_toolkit.game_data.skills import SkillDatabase
    from d2rr_toolkit.game_data.stat_breakdown import StatBreakdown
    from d2rr_toolkit.meta.source_versions import SourceVersions

logger = logging.getLogger(__name__)

# Stat pairs that are displayed as one combined line.
# Key = first/min stat_id, value = list of subsequent stat_ids in the group.
DAMAGE_STAT_GROUPS: dict[int, list[int]] = {
    21: [22],  # mindamage + maxdamage -> "Adds X-Y Weapon Damage"
    23: [24],  # secondary_mindamage + secondary_maxdamage -> "Adds X-Y Weapon Damage"
    17: [18],  # item_maxdamage_percent + item_mindamage_percent -> Enhanced Damage
    48: [49],  # item_fire_mindamage + item_fire_maxdamage
    50: [51],  # item_ltng_mindamage + item_ltng_maxdamage
    52: [53],  # item_mag_mindamage + item_mag_maxdamage
    54: [55, 56],  # item_cold_mindamage + item_cold_maxdamage + item_cold_length
    57: [58, 59],  # item_pos_mindamage + item_pos_maxdamage + item_pos_length
}

# stat_ids that are "followers" in a damage group (shown as part of the group, not alone)
DAMAGE_GROUP_FOLLOWERS: set[int] = {
    sid for partners in DAMAGE_STAT_GROUPS.values() for sid in partners
}

# Stats that are internal/hidden but have a paired "display" stat with the correct template.
# Maps internal_stat_id -> display_stat_id.
# Example: stat 97 item_nonclassskill (descfunc=0, no template) ->
#          stat 387 item_nonclassskill_display (descfunc=28, template "ItemModifierNonClassSkill")
DISPLAY_REDIRECT: dict[int, int] = {
    97: 387,  # item_nonclassskill -> "+X to SkillName (oskill)"
}

# Display-mirror stats that should ALWAYS be suppressed from output.
# These are the VALUES of DISPLAY_REDIRECT - they exist only as template sources
# for their redirected counterparts and must never be shown directly.
DISPLAY_MIRROR_STATS: frozenset[int] = frozenset(DISPLAY_REDIRECT.values())

# Reimagined-internal skill IDs that should NEVER appear in tooltips.
# These are engine-internal skills used for hidden mod mechanics.
HIDDEN_SKILL_PARAMS: set[int] = {
    449,  # "Hidden Charm Passive" - internal passive that gates charm effects
}

# Stats that are Reimagined-internal duplicates of primary damage stats and
# should be hidden from display when the primary stat (21/22) is present with
# the same value.  They appear on jewels/charms as duplicate min/max damage.
REIMAGINED_DUPLICATE_DAMAGE: dict[int, int] = {
    23: 21,  # secondary_mindamage  -> duplicate of mindamage (when both present)
    24: 22,  # secondary_maxdamage  -> duplicate of maxdamage (when both present)
    159: 21,  # item_throw_mindamage -> duplicate of mindamage
    160: 22,  # item_throw_maxdamage -> duplicate of maxdamage
}

# Damage group display templates (filled programmatically)
DAMAGE_GROUP_TEMPLATES: dict[int, str] = {
    21: "Adds %(min)d-%(max)d Weapon Damage",
    23: "Adds %(min)d-%(max)d Weapon Damage",
    17: "%(val)s%% Enhanced Weapon Damage",
    48: "Adds %(min)d-%(max)d Weapon Fire Damage",
    50: "Adds %(min)d-%(max)d Weapon Lightning Damage",
    52: "Adds %(min)d-%(max)d Weapon Magic Damage",
    54: "Adds %(min)d-%(max)d Cold Damage",  # duration handled specially
    57: "Adds %(min)d-%(max)d Poison Damage",  # duration handled specially
}

# properties.txt ``func`` column -> canonical ISC stat id(s) that the
# game engine applies for func-only codes.  These codes have NO
# ``stat1`` entry in properties.txt (the game maps them via func at
# runtime), so ``PropertyDefinition.primary_stat_id`` returns ``None``
# for them.  Without this fallback, :meth:`format_code_value` emits the
# raw property code (e.g. ``"+200 dmg%"`` instead of
# ``"+200% Enhanced Weapon Damage"``).
#
# Verified against properties.txt (Reimagined 3.0.7).  Only the 5 codes
# that actually appear in sets.txt / setitems.txt are listed - the
# others (monster-only, affix-rand, ...) never reach this path.
#
# [BV Forsaken Divinity full-set bonus: "+200% Enhanced Weapon Damage"
#  via FCode1='dmg%' FMin1=200]
_FUNC_ONLY_CODE_TO_STAT: dict[str, int] = {
    # dmg%  (func=7): engine applies to stat 17 (item_maxdamage_percent)
    # + stat 18 (item_mindamage_percent) - the "Enhanced Damage" pair.
    # Template in DAMAGE_GROUP_TEMPLATES[17].
    "dmg%": 17,
    # dmg-min (func=5): engine applies to stats 21/23/159 (mindamage
    # across all weapon-damage families).  Canonical display uses the
    # 1H pair (stat 21 + stat 22) template.
    "dmg-min": 21,
    # dmg-max (func=6): stats 22/24/160 - mirror of dmg-min.
    "dmg-max": 22,
    # indestruct (func=20): stat 152 (item_indesctructible).
    "indestruct": 152,
    # ethereal (func=23): flag, not a stat.  Handled as a static
    # string in :meth:`format_code_value` because ISC has no stat for it.
}

# Damage groups with duration (frames) - need special conversion for display.
# Poison: display_damage = round(raw_value * duration / 256), display_secs = duration / 25
# Cold: display_secs = duration / 25 (damage values are direct, no /256)
_FRAMES_PER_SECOND = 25


def _strip_color(text: str) -> str:
    """Remove D2R in-game color markup sequences (ÿcX)."""
    return re.sub(r"[ÿ\xff]c.", "", text, flags=re.DOTALL).strip()


# ── D2R inline colour markup ─────────────────────────────────────────────────
#
# Reimagined's ``item-modifiers.json`` (and friends) embeds colour changes as
# three-byte escape sequences ``\xFFc<L>`` (``ÿ`` + ``c`` + a single-byte
# token ``L``).  A single property string may carry MULTIPLE tokens - it is
# intrinsically a list of coloured runs, not a "whole-line colour" flag.
#
# Known tokens in the live data (authoritative list - consumers SHOULD
# accept unknown tokens gracefully and fall back to their default colour):
#
#   '0'  white             '5'  dark grey (fluff / low quality)
#   '1'  red               '6'  black
#   '2'  set green         '7'  tan
#   '3'  magic blue        '8'  orange (crafted)
#   '4'  unique gold       '9'  yellow (rare)
#   ':'  dark green        ';'  purple
#   'K'  grey (used on fluff text such as ``fadeDescription``)
#
# The splitter below is the boundary between "raw D2R text" and "consumer-
# friendly segments".  Every public structured API on
# :class:`PropertyFormatter` returns text that has already been through
# :func:`_split_color`; plain-text consumers get the same data with tokens
# stripped via :func:`_strip_color` (or via a convenience ``plain_text``
# accessor on :class:`FormattedProperty`).
_COLOR_TOKEN_RE = re.compile(r"[ÿ\xff]c(.)", re.DOTALL)


@dataclass(frozen=True, slots=True)
class FormattedSegment:
    """One contiguous run of text in a single colour token.

    Attributes:
        text:        The visible text of this run.  Always non-empty for
                     segments produced by :func:`_split_color` - empty runs
                     are discarded there, so consumers can rely on this.
        color_token: The raw D2R colour token that applies to the run
                     (e.g. ``"K"`` for grey, ``"3"`` for magic blue), or
                     ``None`` when the run inherits the caller's default
                     colour (text before any explicit token).
    """

    text: str
    color_token: str | None


# ── Roll-range metadata ──────────────────────────────────────────────────────
#
# The GUI tooltip wants to show, next to every rollable stat:
#
#   1. a perfect-roll star  (current_value == max_value for the stat)
#   2. a ``[min-max]`` hint  (the range the stat COULD have landed in)
#
# Those are presentation-layer decisions; the data required to make them
# is a per-stat ``(min, max, source)`` triple.  The toolkit is the only
# side of the pipeline that sees the affix / unique / set / runes
# tables, so it owns the resolution.  The structured formatter attaches
# the resulting :class:`StatRollRange` instances to the matching
# :class:`FormattedProperty` at render time.
#
# Back-compat: both new fields default to "no info" so earlier pickle
# caches and downstream consumers keep loading unchanged.


# Sources tracked in v1. New sources can land here + in the resolver
# without breaking the ``Literal`` accept list for existing consumers -
# they simply extend it.
RollSource = Literal[
    "unique",
    "set",
    "runeword",
    "magic_prefix",
    "magic_suffix",
    "rare_prefix",
    "rare_suffix",
    # automod: automagic.txt contributions attached via
    # ``ParsedItem.automod_id``.  Reserved; the plain ``resolve`` path
    # doesn't emit this source directly (the automagic itype-filter
    # rules for which rows actually apply to which items aren't fully
    # mapped - suppressing avoids over-attribution on charms).
    "automod",
    # Reserved for future expansion; not emitted in current output:
    "crafted",
]


@dataclass(frozen=True, slots=True)
class StatRollRange:
    """Possible roll window for a single stat on a single item.

    ``min_value`` / ``max_value`` carry the roll bounds as they
    appear in the source table - typically integers, but stored as
    ``float`` so future fractional stats (e.g. percentage-per-level
    coefficients) don't force a breaking change.

    For stats where ``min_value == max_value`` the roll is
    effectively fixed - :meth:`is_fixed` returns ``True`` and
    presentation layers typically suppress both the perfect-roll
    star and the ``[min-max]`` suffix (no visual value there).

    All v1 sources use "bigger = better" semantics.  Stats where
    smaller is better (rare negative-is-better affixes) surface
    via ``is_perfect == True`` when ``current >= max`` and may
    mislead the GUI slightly; this is deliberate - the inversion
    flag ships later if anyone complains.
    """

    min_value: float
    max_value: float
    source: "RollSource"

    def is_fixed(self) -> bool:
        """``True`` when the roll window has zero width."""
        return self.min_value == self.max_value

    def is_perfect(self, current_value: float) -> bool:
        """``True`` when the rolled value has reached (or exceeded)
        the max of its roll window.  The ``>=`` is deliberate so
        integer stats that rolled exactly at max show as perfect."""
        return current_value >= self.max_value


def _range_contains(
    rng: "StatRollRange",
    current_value: float,
    *,
    item_has_stat_modifiers: bool = False,
) -> bool:
    """Return True iff ``current_value`` is plausibly within ``rng``.

    For plain items (no corruption / enchantment / ethereal / runeword),
    the check is strict: ``current_value`` must satisfy
    ``min <= current_value <= max``.  That's what lets us catch
    parser-misID bugs like "Coral Grand Charm rendered as Amber" -
    the rolled 25 sits below Amber's [26, 30] range, so the gate
    rejects the range cleanly.

    For items with stat modifiers active (``item_has_stat_modifiers``),
    the upper bound is removed: Corruption adds free bonus stats,
    Enchantment lets players stack capped mods on top, Ethereal boosts
    defense by 50%, Runeword items carry their full RW stat block in
    addition to any base affixes.  Any of these can legitimately push
    a stat above its source-table max.  The lower bound stays strict
    - no modifier system in Reimagined pushes a positive stat BELOW
    its minimum, so ``current < min`` still signals a source mismatch.

    The :class:`StatBreakdownResolver` (opt-in via
    ``format_properties_grouped(breakdown=True)``) offers the exact
    per-stat decomposition: subtract known modifier contributions
    (corruption tables + enchantment recipes + ethereal + affix rolls)
    and attribute the leftover to an ``unknown_modifier`` /
    ``residual`` slot.  This tighter gate here is kept as the fast
    path - callers that only need the roll-range display without the
    full decomposition pay no breakdown cost.
    """
    if current_value < rng.min_value:
        return False
    if item_has_stat_modifiers:
        # Modifier-loose: any value at or above the min is plausible.
        # Corruption / Enchantment / Ethereal / RW add on top, never
        # subtract, for the stats they affect.
        return True
    return current_value <= rng.max_value


@dataclass(frozen=True, slots=True)
class ItemRollContext:
    """Everything the formatter needs to resolve roll ranges.

    Build once per item (via :meth:`from_parsed_item`) and thread the
    same instance through :meth:`format_properties_grouped` and
    :meth:`format_prop_structured`.  Pass ``None`` to skip roll
    resolution - identical to the behaviour before roll-range
    resolution landed.

    Every field is optional because an item may carry none of them
    (plain base item, magic item with only a suffix, ...).  The
    resolver reads what is present and leaves the rest untouched.

    Attributes:
        quality: The D2R quality code (2..8), mostly informational -
            the other fields already disambiguate the actual lookup
            table to consult.  Included so a future resolver can
            decide e.g. that Crafted items behave differently from
            Rare without the caller having to redo the lookup.
        unique_id: ``*ID`` value from ``uniqueitems.txt`` (NOT the
            row index - Reimagined has separator rows that skew the
            two).  Matches ``ParsedItem.unique_type_id``.
        set_id: ``*ID`` from ``setitems.txt``.  Matches
            ``ParsedItem.set_item_id``.
        runeword_id: Row index into ``runes.txt``.  Matches
            ``ParsedItem.runeword_id``.
        prefix_ids: Row indices into ``magicprefix.txt``.  Length 0-1
            for Magic items (one prefix), 0-3 for Rare / Crafted
            items.  Derived from ``ParsedItem.prefix_id`` or from the
            even-index slots of ``rare_affix_slots`` + ``rare_affix_ids``.
        suffix_ids: Row indices into ``magicsuffix.txt``.  Same
            shape as ``prefix_ids``.  Derived from
            ``ParsedItem.suffix_id`` or from odd-index slots.
    """

    quality: int | None = None
    unique_id: int | None = None
    set_id: int | None = None
    runeword_id: int | None = None
    prefix_ids: tuple[int, ...] = ()
    suffix_ids: tuple[int, ...] = ()
    # automagic.txt row index (``ParsedItem.automod_id`` - 0-based
    # after the has_gfx=1 carry-bit masking; 0 means "no automod
    # applied").  Consulted by :class:`StatBreakdownResolver` when
    # a magic-quality item carries a residual the standard affix
    # sources don't explain - a Reimagined follow-up signal, not a
    # direct contribution (see ``affix_rolls._iter_sources``).
    automod_id: int | None = None

    # ── Stat-modifier flags (Reimagined layer on top of base rolls) ─
    # Any of these makes the rolled stat's observed value legitimately
    # higher than its source-table max: Corruption adds free mods,
    # Enchantment lets the player pile capped bonuses on top, Ethereal
    # inflates defense by 50%, and Runeword items get their full RW
    # stat block grafted onto the base item.  The consistency gate in
    # the formatter loosens the ``observed <= range.max`` check and
    # suppresses the perfect-roll star whenever any of these is True,
    # so legitimately modified items don't falsely report "parser
    # mismatch".  A dedicated StatBreakdownResolver (follow-up)
    # will eventually subtract out the precise modifier contributions
    # and restore per-source perfection flags - for now this is the
    # conservative, zero-risk approximation.
    is_corrupted: bool = False
    is_enchanted: bool = False
    is_ethereal: bool = False
    is_runeword: bool = False

    @property
    def has_stat_modifiers(self) -> bool:
        """Any modifier system that can push stats above their base range."""
        return self.is_corrupted or self.is_enchanted or self.is_ethereal or self.is_runeword

    @classmethod
    def from_parsed_item(cls, item: object) -> "ItemRollContext":
        """Pull the relevant fields off a :class:`ParsedItem`.

        Handles the convention split between Magic items
        (single ``prefix_id`` / ``suffix_id``) and Rare / Crafted
        items (parallel ``rare_affix_ids`` + ``rare_affix_slots``
        lists, where slot parity distinguishes prefix from suffix).

        The ``item`` type is declared as ``object`` to avoid
        pulling ``ParsedItem`` into this module's import graph;
        the field reads are duck-typed and tolerant of missing
        attributes.
        """
        quality = _maybe_int(getattr(getattr(item, "extended", None), "quality", None))

        unique_id = _maybe_int(getattr(item, "unique_type_id", None))
        set_id = _maybe_int(getattr(item, "set_item_id", None))
        rw_id = _maybe_int(getattr(item, "runeword_id", None))

        prefix_ids: tuple[int, ...] = ()
        suffix_ids: tuple[int, ...] = ()

        # Magic items (quality=4) use scalar prefix_id / suffix_id.
        # 0 is the "no affix" sentinel and MUST NOT be treated as a
        # row index (row 0 of magicprefix.txt is a header / separator).
        scalar_prefix = _maybe_int(getattr(item, "prefix_id", None))
        scalar_suffix = _maybe_int(getattr(item, "suffix_id", None))
        if scalar_prefix:
            prefix_ids = (scalar_prefix,)
        if scalar_suffix:
            suffix_ids = (scalar_suffix,)

        # Rare / Crafted items (quality=6/8) use parallel rare_affix_ids
        # + rare_affix_slots lists.  Even slots -> prefix table, odd ->
        # suffix table.  See ``project_rare_misc_7slot_qsd`` + the
        # memory note on the parallel-slot convention.
        rare_ids = list(getattr(item, "rare_affix_ids", []) or [])
        rare_slots = list(getattr(item, "rare_affix_slots", []) or [])
        if rare_ids and len(rare_slots) == len(rare_ids):
            ps = tuple(aid for aid, slot in zip(rare_ids, rare_slots) if aid and (slot % 2) == 0)
            ss = tuple(aid for aid, slot in zip(rare_ids, rare_slots) if aid and (slot % 2) == 1)
            if ps:
                prefix_ids = ps
            if ss:
                suffix_ids = ss

        # ── Modifier detection ───────────────────────────────────────
        # Corruption: item_corrupted (stat 361) present with any
        # non-zero value.  Both phase-1 (value=1) and phase-2 (value=2)
        # states can legitimately grow the observed stats above their
        # base ranges - phase-1 doesn't yet pay out bonuses but the
        # tolerance is harmless there.
        # Enchantment: Reimagined fake-stats 392..395 flag that the
        # player has access to additional upgrade slots; the actual
        # enchant mods flow as normal stats in the same list.
        # Ethereal / Runeword: straight from the item flags.
        magical = getattr(item, "magical_properties", None) or ()
        stat_ids = {p.get("stat_id") for p in magical if isinstance(p, dict)}
        is_corrupted = 361 in stat_ids
        is_enchanted = bool(stat_ids & {392, 393, 394, 395})
        flags = getattr(item, "flags", None)
        is_ethereal = bool(getattr(flags, "ethereal", False))
        is_runeword = bool(getattr(flags, "runeword", False))

        # automod_id is meaningful for bf1=False items (charms, tools,
        # orbs) AND for bf1=True weapons/armor where the slot is
        # genuinely present (see project_parser_padding_and_automod).
        # Rare and Crafted items (quality=6/8) store their mods via
        # rare_affix_ids - the automod_id field is still populated but
        # its contribution is already represented in the rare affix
        # chain, so attributing it separately would double-count.
        raw_automod = _maybe_int(getattr(item, "automod_id", None))
        if raw_automod is not None and quality in (6, 8):
            raw_automod = None
        automod_id = raw_automod

        return cls(
            quality=quality,
            unique_id=unique_id,
            set_id=set_id,
            runeword_id=rw_id,
            prefix_ids=prefix_ids,
            suffix_ids=suffix_ids,
            automod_id=automod_id,
            is_corrupted=is_corrupted,
            is_enchanted=is_enchanted,
            is_ethereal=is_ethereal,
            is_runeword=is_runeword,
        )


def _maybe_int(v: object) -> int | None:
    """Best-effort integer coercion.  Empty / None / non-numeric -> None."""
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True, slots=True)
class FormattedProperty:
    """A display-ready property line split into coloured segments.

    Produced by :meth:`PropertyFormatter.format_prop_structured` and
    :meth:`PropertyFormatter.format_properties_grouped`.  Every GUI that
    wants per-segment colour rendering (e.g. the tooltip renderer in the
    D2RR ToolkitGUI project) consumes this shape directly; plain-text
    consumers (the CLI, logs, tests) use either :attr:`plain_text` or
    the ``format_properties_grouped_plain`` convenience wrapper.

    Attributes:
        segments:        The coloured parts, in order.  Joined without a
                         separator on ``.text`` they reproduce the full
                         visible text.  Always at least one segment for
                         any visible line; never an empty tuple.
        plain_text:      All colour tokens removed - matches the return
                         of the pre-refactor ``format_properties_grouped``
                         exactly, by construction.
        source_stat_ids: The ISC stat IDs that produced this line.
                         ``()`` for synthetic collapses
                         (``"+X to all Attributes"``, all-resistance
                         collapse, elemental skill damage / pierce
                         collapses) that aggregate multiple stats into
                         a single line without a canonical single owner.
                         Non-empty for everything else: ``(stat_id,)`` for
                         a lone property, ``(lead_id, follower_id, ...)``
                         for a damage group.
        roll_ranges:     Possible roll window(s) for the stat(s) on
                         this line.  Empty tuple means "no roll info
                         known" (base item stat, synthetic collapse,
                         stat the resolver couldn't match to a source
                         table row, or no :class:`ItemRollContext`
                         passed to the formatter).  For a simple
                         single-stat line the tuple has length 1; for
                         a damage pair collapsed by
                         :meth:`format_properties_grouped` it has
                         length 2 in the order ``(min_dmg_range,
                         max_dmg_range)`` - consumers can rely on
                         that index convention.
        is_perfect:      ``True`` iff every range in ``roll_ranges``
                         reports :meth:`StatRollRange.is_perfect`
                         against the stat's current rolled value.
                         ``False`` when ``roll_ranges`` is empty - no
                         range, no perfection claim.
    """

    segments: tuple[FormattedSegment, ...]
    plain_text: str
    source_stat_ids: tuple[int, ...] = ()
    roll_ranges: tuple[StatRollRange, ...] = ()
    is_perfect: bool = False
    # Per-stat source decomposition: ``base_roll`` / ``corruption`` /
    # ``enchantment`` / ``ethereal_bonus`` / ``unknown_modifier`` /
    # ``residual``.  Populated only when the caller passes
    # ``breakdown=True`` to
    # :meth:`PropertyFormatter.format_properties_grouped` - the
    # default ``None`` preserves the pre-breakdown dataclass shape
    # byte-for-byte (old pickles round-trip).  See
    # ``docs/GUI_STAT_BREAKDOWN_API.md`` for the consumer reference.
    breakdown: "StatBreakdown | None" = None


def _split_color(text: str) -> list[FormattedSegment]:
    """Parse a D2R colour-tagged string into :class:`FormattedSegment` runs.

    Rules:
      * Text before the first colour token has ``color_token=None`` (the
        caller's default colour applies).
      * A colour token switches the *following* text to its colour.  Runs
        of zero length (two adjacent tokens, or a trailing token with no
        text after it) are discarded so consumers never see empty
        segments.
      * Unknown tokens are preserved verbatim - it is the consumer's
        responsibility to map them to a palette (and to fall back
        sensibly when it can't).

    The concatenation of all ``.text`` fields reproduces the input with
    colour tokens removed, which matches :func:`_strip_color`'s output
    (minus the trailing whitespace strip - see
    :meth:`FormattedProperty.plain_text` construction, which calls
    ``.strip()`` to stay byte-identical to the legacy plain output).
    """
    segments: list[FormattedSegment] = []
    cur_token: str | None = None
    last_end = 0
    for m in _COLOR_TOKEN_RE.finditer(text):
        run = text[last_end : m.start()]
        if run:
            segments.append(FormattedSegment(text=run, color_token=cur_token))
        cur_token = m.group(1)
        last_end = m.end()
    tail = text[last_end:]
    if tail:
        segments.append(FormattedSegment(text=tail, color_token=cur_token))
    return segments


def _make_formatted(
    raw: str | None,
    source_stat_ids: tuple[int, ...] = (),
) -> FormattedProperty | None:
    """Wrap a raw (possibly colour-tagged) string as a :class:`FormattedProperty`.

    Returns ``None`` when the formatter decided to emit nothing (hidden
    stats, lone damage-group followers, ...).  The resulting object always
    carries at least one segment when non-``None``; lines with no
    visible content after trimming are also folded to ``None`` so
    downstream iteration doesn't have to guard against empty strings.
    """
    if raw is None:
        return None
    # Trim trailing whitespace without touching the colour structure so
    # ``plain_text`` matches the legacy ``_strip_color(...).strip()``
    # contract the CLI / tests have relied on since day one.
    segments = _split_color(raw)
    # Strip outer whitespace from the first/last segments to mirror
    # ``.strip()`` on the plain text while keeping colour boundaries
    # intact.  Inner whitespace is preserved verbatim.
    if segments:
        head = segments[0]
        lstripped = head.text.lstrip()
        if lstripped != head.text:
            segments[0] = FormattedSegment(text=lstripped, color_token=head.color_token)
        if segments and not segments[0].text:
            segments.pop(0)
    if segments:
        last = segments[-1]
        rstripped = last.text.rstrip()
        if rstripped != last.text:
            segments[-1] = FormattedSegment(text=rstripped, color_token=last.color_token)
        if segments and not segments[-1].text:
            segments.pop()
    if not segments:
        return None
    plain = "".join(s.text for s in segments)
    return FormattedProperty(
        segments=tuple(segments),
        plain_text=plain,
        source_stat_ids=source_stat_ids,
    )


def _apply_template(
    template: str,
    value: int,
    secondary: int = 0,
    name_str: str = "",
    name_str2: str = "",
) -> str:
    """Fill a display template with numeric and string values.

    Handles (in order):
      %+d   -> signed value (e.g. +25, -10)
      %d%%  -> value followed by literal %
      %d    -> plain value
      %s    -> first: name_str, second: name_str2 (e.g. skill name + class name)
      %%    -> literal %
    """
    result = template

    # Replace %+d (signed integer with explicit sign)
    result = re.sub(r"%\+d", lambda _: f"{value:+d}", result)

    # Replace paired %d patterns for charged/aura (secondary value after first %d)
    first_d_replaced = False

    def replace_d(m: re.Match) -> str:
        nonlocal first_d_replaced, value, secondary
        if not first_d_replaced:
            first_d_replaced = True
            return str(value)
        else:
            return str(secondary)

    result = re.sub(r"%d", replace_d, result)

    # Replace %% with literal %
    result = result.replace("%%", "%")

    # Replace %s - first occurrence with name_str, second with name_str2
    _s_strs = [s for s in [name_str, name_str2] if s]
    for s_val in _s_strs:
        if "%s" in result:
            result = result.replace("%s", s_val, 1)
    # Any remaining %s -> "?"
    result = result.replace("%s", "?")

    return result.strip()


class PropertyFormatter:
    """Converts property dicts and property codes to display strings."""

    def __init__(self) -> None:
        self._templates: dict[str, str] = {}  # Key -> enUS template string
        self._loaded = False

    def load_from_bytes(self, raw: bytes, *, source: str = "<bytes>") -> None:
        """Parse item-modifiers.json from raw bytes (Iron Rule entry point)."""
        try:
            entries = json.loads(raw.decode("utf-8-sig", errors="replace"))
        except (ValueError, json.JSONDecodeError) as e:
            logger.error("Cannot parse item-modifiers.json %s: %s", source, e)
            return
        if not isinstance(entries, list):
            logger.warning(
                "Unexpected JSON structure in %s (expected array)",
                source,
            )
            return
        for entry in entries:
            key = entry.get("Key", "")
            text = entry.get("enUS", "")
            if key and text:
                # Keep the raw D2R colour markup (``ÿcX``) in the cache.
                # Stripping here would make every downstream formatter
                # emit monochrome output, erasing the dark-grey fluff
                # colour on stats like ``fadeDescription``.  The split
                # into coloured segments happens at the public
                # structured API boundary (:meth:`format_prop_structured`,
                # :meth:`format_properties_grouped`); plain-text callers
                # get the stripped form via
                # :meth:`format_properties_grouped_plain`.
                self._templates[key] = text
        self._loaded = True
        logger.info(
            "PropertyFormatter: %d templates loaded from %s",
            len(self._templates),
            source,
        )

    def is_loaded(self) -> bool:
        """Return True if the database has been populated."""
        return self._loaded

    def get_template(self, key: str) -> str | None:
        """Return the raw template string for ``key``, or None if not loaded."""

        return self._templates.get(key)

    # ── Core formatting API ────────────────────────────────────────────────────

    def format_prop(
        self,
        prop: dict,
        isc_db: "ItemStatCostDatabase",
        skills_db: "SkillDatabase | None" = None,
        lang: str = "enUS",
    ) -> str | None:
        """Format a single magical property dict to a plain display string.

        Colour tokens are stripped so the return value stays byte-
        identical to the pre-refactor output.  GUIs that need per-segment
        colour rendering should call :meth:`format_prop_structured` or
        :meth:`format_properties_grouped` instead.
        """
        raw = self._format_prop_raw(prop, isc_db, skills_db, lang)
        if raw is None:
            return None
        return _strip_color(raw)

    def format_prop_structured(
        self,
        prop: dict,
        isc_db: "ItemStatCostDatabase",
        skills_db: "SkillDatabase | None" = None,
        lang: str = "enUS",
        *,
        roll_context: "ItemRollContext | None" = None,
        props_db: "PropertiesDatabase | None" = None,
    ) -> FormattedProperty | None:
        """Format a single property dict as a :class:`FormattedProperty`.

        The returned object preserves every inline D2R colour token that
        appeared in the source template - GUIs can paint each segment
        in its own colour (e.g. grey for fluff fields like
        ``fadeDescription``).

        When ``roll_context`` is provided the formatter also resolves
        the stat's roll range against the affix / unique / set /
        runeword tables and attaches it via
        :attr:`FormattedProperty.roll_ranges` plus the derived
        :attr:`FormattedProperty.is_perfect` flag.  When ``None``
        (default) both fields are left at their empty defaults,
        matching the behaviour before roll-range resolution landed.
        """
        raw = self._format_prop_raw(prop, isc_db, skills_db, lang)
        stat_id = prop.get("stat_id")
        ids: tuple[int, ...] = (stat_id,) if isinstance(stat_id, int) else ()
        fp = _make_formatted(raw, source_stat_ids=ids)
        if fp is None or roll_context is None or not ids:
            return fp
        rng = self._resolve_range_for_stat(
            stat_id=stat_id,
            prop=prop,
            roll_context=roll_context,
            isc_db=isc_db,
            props_db=props_db,
            skills_db=skills_db,
        )
        if rng is None:
            return fp
        current = self._current_value_for_perfection(prop, stat_id)
        has_mods = roll_context.has_stat_modifiers
        if not _range_contains(rng, current, item_has_stat_modifiers=has_mods):
            # See _attach_single_roll_range for the full rationale
            # (VikingBarbie "Coral Grand Charm" parser-misID bug).
            return fp
        # Modifier-loose items don't get the perfect-roll star on
        # this fast path - we can't tell whether THIS stat was boosted
        # by corruption / enchantment / ethereal / RW without walking
        # the breakdown resolver.  Callers that need the precise
        # per-source perfection flag should invoke
        # :meth:`format_properties_grouped` with ``breakdown=True``;
        # the resulting ``StatBreakdown.is_perfect_roll`` isolates the
        # base-roll-at-max check from the modifier contributions.
        is_perfect = rng.is_perfect(current) and not has_mods
        return FormattedProperty(
            segments=fp.segments,
            plain_text=fp.plain_text,
            source_stat_ids=fp.source_stat_ids,
            roll_ranges=(rng,),
            is_perfect=is_perfect,
        )

    # ── Roll-range helpers ─────────────────────────────────────────────────

    @staticmethod
    def _current_value_for_perfection(prop: dict, stat_id: int) -> float:
        """Pull the rolled value out of ``prop`` for perfection checks.

        Most props expose ``value``; encode=2 (skill-on-event) stats
        use ``chance`` / ``level`` instead - and the rolled number
        that the GUI wants to compare against the range's ``max`` is
        the chance (which matches the ``min`` column of the
        uniqueitems row; the ``max`` column carries the skill LEVEL
        and is handled by the roll resolver via the same column
        split).  For v1 we compare the primary rolled value; the
        skill-level component is already captured in the range's
        ``max_value`` via the same source-table slot.
        """
        v = prop.get("value")
        if isinstance(v, (int, float)):
            return float(v)
        # encode=2 fallback: the rolled chance lives in ``chance``.
        c = prop.get("chance")
        if isinstance(c, (int, float)):
            return float(c)
        return 0.0

    def _resolve_range_for_stat(
        self,
        *,
        stat_id: int,
        prop: dict,
        roll_context: "ItemRollContext",
        isc_db: "ItemStatCostDatabase",
        props_db: "PropertiesDatabase | None",
        skills_db: "SkillDatabase | None",
    ) -> "StatRollRange | None":
        """Resolve the :class:`StatRollRange` for one stat / prop dict.

        Lazy-imports :mod:`affix_rolls` so the formatter still works
        in environments that never load the affix-roll DB (tests,
        headless pipelines).  The database's own
        :meth:`is_loaded` gate doubles as the availability check.
        """
        if props_db is None:
            return None
        try:
            from d2rr_toolkit.game_data.affix_rolls import (
                get_affix_roll_db,
                load_affix_rolls,
            )
            from d2rr_toolkit.game_data.charstats import get_charstats_db
        except ImportError:
            logger.warning("affix_rolls / charstats modules unavailable")
            return None
        db = get_affix_roll_db()
        if not db.is_loaded():
            # Auto-load on first use so callers don't have to wire a
            # separate load_affix_rolls() call.  Cached after the first
            # hit via the standard cached_load pattern, so this is a
            # one-time cost per process.
            try:
                load_affix_rolls()
            except (OSError, ValueError, KeyError) as exc:
                logger.warning("affix_rolls: auto-load failed: %s", exc)
                return None
            if not db.is_loaded():
                return None
        # ``param`` on a property dict is the integer the parser
        # stored (skill id, class index, or 0 for paramless stats).
        param_raw = prop.get("param", 0)
        try:
            param = int(param_raw) if param_raw is not None else 0
        except (TypeError, ValueError):
            param = 0
        return db.resolve(
            roll_context,
            stat_id,
            param=param,
            isc_db=isc_db,
            props_db=props_db,
            skills_db=skills_db,
            charstats_db=get_charstats_db(),
        )

    def _format_prop_raw(
        self,
        prop: dict,
        isc_db: "ItemStatCostDatabase",
        skills_db: "SkillDatabase | None" = None,
        lang: str = "enUS",
    ) -> str | None:
        """Core formatter producing the raw (possibly colour-tagged) string.

        Shared by :meth:`format_prop` (plain) and
        :meth:`format_prop_structured` (segmented).  Every descfunc
        branch returns the template text with colour tokens intact; the
        caller decides whether to strip or split them.
        """
        stat_id = prop.get("stat_id")
        if stat_id is None:
            return None

        # Damage-group follower stats are normally displayed as part of their
        # group (e.g. stat 22 maxdamage paired with stat 21 mindamage).
        # When called from format_properties_grouped(), lone followers are
        # allowed through. When called standalone, skip them to avoid
        # double-display.  The grouped formatter handles this distinction.

        stat_def = isc_db.get(stat_id)
        if stat_def is None:
            return f"[unknown stat {stat_id}]"

        # Apply display redirect: some internal stats (descfunc=0, no template) have a paired
        # display stat with the correct template. Use the display stat for formatting but keep
        # the original prop's value and param.
        if stat_id in DISPLAY_REDIRECT:
            display_stat = isc_db.get(DISPLAY_REDIRECT[stat_id])
            if display_stat is not None:
                stat_def = display_stat

        encode = stat_def.encode
        descfunc = stat_def.descfunc

        # ── Encode 2: skill-on-event ───────────────────────────────────────
        if encode == 2:
            return self._format_skill_on_event(prop, stat_def, skills_db)

        # ── Encode 3: charged skill ────────────────────────────────────────
        if encode == 3:
            return self._format_charged_skill(prop, stat_def, skills_db)

        # ── Encode 1: min/max pair ─────────────────────────────────────────
        if encode == 1 and stat_id not in DAMAGE_STAT_GROUPS:
            # Non-damage encode=1 (e.g. item_nonclassskill with save_param_bits>0)
            # Pass actual param - oskill stats need it for skill name lookup.
            value = prop.get("value", 0)
            param = prop.get("param", 0)
            return self._apply_stat_template(stat_def, value, param, skills_db)

        # ── Damage groups (hardcoded pairs) ───────────────────────────────
        if stat_id in DAMAGE_STAT_GROUPS:
            # Handled by format_properties_grouped - return None for individual display
            return None

        # ── Encode 4 (special) and Encode 0 (standard) ────────────────────
        value = prop.get("value", 0)
        param = prop.get("param", 0)

        # descfunc=20: Corrupted - static string.  The template may
        # carry inline colour tokens (e.g. "Corrupted" is rendered red
        # in-game); leave them in place so the structured API sees the
        # real colouring and ``format_prop``'s wrapper strips them for
        # plain-text callers.
        if descfunc == 20:
            key = stat_def.descstrpos
            tmpl = self._templates.get(key, "Corrupted")
            return tmpl

        # descfunc=3: static display string (no value substitution)
        if descfunc == 3:
            key = stat_def.descstrpos
            return self._templates.get(key, stat_def.name) or stat_def.name

        # descfunc=16: Level X AuraName Aura When Equipped
        if descfunc == 16:
            key = stat_def.descstrpos
            tmpl = self._templates.get(key, "Level %d %s Aura When Equipped")
            skill_name = (skills_db.name(param) if skills_db else None) or f"Skill{param}"
            return _apply_template(tmpl, value, 0, skill_name)

        # descfunc=13: "+X to [ClassName] Skill Levels"
        # param = class index (0=Amazon ... 7=Warlock).
        if descfunc == 13:
            from d2rr_toolkit.game_data.charstats import get_charstats_db

            cls_name = get_charstats_db().get_class_name(param) or f"Class{param}"
            sign = "+" if value >= 0 else ""
            return f"{sign}{value} to {cls_name} Skill Levels"

        # descfunc=14: "+X to [SkillTabName] (ClassName Only)"
        # param = (class_index << 3) | tab_within_class.
        # Lookup: charstats -> StrSklTabItem key -> item-modifiers.json template.
        if descfunc == 14:
            from d2rr_toolkit.game_data.charstats import get_charstats_db

            cdb = get_charstats_db()
            cls_idx = param >> 3
            tab_idx = param & 7
            cls_name = cdb.get_class_name(cls_idx) or f"Class{cls_idx}"
            tab_key = cdb.get_skill_tab_key(cls_idx, tab_idx)
            if tab_key:
                tmpl = self._templates.get(tab_key)
                if tmpl:
                    # Template like "%+d to Traps" -> apply value, then append class
                    line = _apply_template(tmpl, value)
                    if line:
                        return f"{line} ({cls_name} Only)"
            sign = "+" if value >= 0 else ""
            return f"{sign}{value} to SkillTab{param} ({cls_name} Only)"

        # descfunc=11: "Repairs N durability in M seconds" or "Repairs N per sec"
        # Used by stat 252 item_replenish_durability. The stored value is a
        # per-frame repair rate on a 100-unit scale. D2's in-game display
        # branches on whether the rate is slow enough to express as
        # "1 every M seconds" (ModStre9u) or fast enough to express as
        # "N per second" (ModStre9t):
        #   value <  100: seconds = 100 // value -> "Repairs 1 durability in {seconds} seconds"
        #   value >= 100: per_sec = value // 100 -> "Repairs {per_sec} durability per second"
        # Zero value is a no-op (stat would not be present in binary).
        # [BV MercOnly Sandstorm Trek value=5 -> "Repairs 1 durability in 20 seconds"]
        if descfunc == 11:
            if value <= 0:
                return None
            if value < 100:
                seconds = 100 // value
                key = "ModStre9u"
                tmpl = self._templates.get(key, "Repairs %d durability in %d seconds")
                # Template has TWO %d placeholders: substitute 1 and seconds in order.
                return tmpl.replace("%d", "1", 1).replace("%d", str(seconds), 1)
            per_sec = value // 100
            key = "ModStre9t"
            tmpl = self._templates.get(key, "Repairs %d durability per second")
            return tmpl.replace("%d", str(per_sec), 1)

        # Standard: descfunc 1,2,4,5,12,17,18,19 etc. -> template substitution
        return self._apply_stat_template(stat_def, value, param, skills_db)

    def format_properties_grouped(
        self,
        props: list[dict],
        isc_db: "ItemStatCostDatabase",
        skills_db: "SkillDatabase | None" = None,
        lang: str = "enUS",
        *,
        roll_context: "ItemRollContext | None" = None,
        props_db: "PropertiesDatabase | None" = None,
        breakdown: bool = False,
        item: object | None = None,
        item_types_db: "ItemTypeDatabase | None" = None,
    ) -> list[FormattedProperty]:
        """Format a full list of properties into structured, coloured lines.

        This is the primary entry point for displaying all properties of
        an item.  Damage pairs (min+max, min+max+duration) collapse into
        one combined line, matching D2R's in-game tooltip layout; stat
        collections (``all attributes``, ``all resistances``, the four-
        element mastery / pierce families) collapse when every member
        is present with an identical value.

        Returns a list of :class:`FormattedProperty` instances - each
        carries both a ``plain_text`` accessor for string-only consumers
        and a ``segments`` tuple for GUIs that need per-segment colour
        rendering (e.g. the dark-grey fluff text on
        ``fadeDescription``).

        **Roll ranges.**  Pass an :class:`ItemRollContext`
        via ``roll_context=`` (plus a loaded :class:`PropertiesDatabase`
        via ``props_db=``) to opt into roll-range resolution.  Every
        returned FormattedProperty then carries:

          * ``roll_ranges`` - ``(StatRollRange,)`` for single-stat
            lines, ``(min_range, max_range)`` for damage pairs
            collapsed by the grouping machinery, ``()`` when the
            resolver couldn't match the stat against any source row.
          * ``is_perfect`` - ``True`` iff every range in
            ``roll_ranges`` reports ``is_perfect()`` against the
            prop's current rolled value.  ``False`` when
            ``roll_ranges`` is empty.

        With ``roll_context=None`` (the default) both new fields stay
        at their empty defaults - byte-identical output to the
        behaviour before roll-range resolution landed.

        Existing consumers that want the pre-refactor ``list[str]``
        shape can call :meth:`format_properties_grouped_plain` instead;
        it is a thin wrapper that emits each property's ``plain_text``.
        """
        # ── Unidentified item gate ────────────────────────────────────────
        # When an item carries ``flags.identified == False`` its tooltip
        # in D2R shows ONLY the base stats (defense, damage, durability,
        # requirements) plus an "Unidentified" red line - no magical
        # properties, no set bonuses, no runeword props. Suppress the
        # full property list here so any caller that routes through this
        # entry point honours the identification gate without needing
        # its own check. Base-stat rendering (damage/defense/etc.) is
        # independent and lives in the caller's own display pipeline.
        if item is not None:
            flags = getattr(item, "flags", None)
            if flags is not None and getattr(flags, "identified", True) is False:
                return []

        formatted = self._format_properties_grouped_raw(
            props,
            isc_db,
            skills_db,
            lang,
            roll_context=roll_context,
            props_db=props_db,
        )
        if not breakdown:
            return formatted

        # Per-stat breakdown attribution path - opt-in per call.
        # Attribute every stat's observed value to its source
        # (``base_roll`` / ``corruption`` / ``enchantment`` /
        # ``ethereal_bonus`` / ``unknown_modifier`` / ``residual``)
        # via :class:`StatBreakdownResolver`.  Requires ``item`` so
        # the resolver can read item_code + flags for corruption
        # bucketing + ethereal bonus detection; requires ``props_db``
        # for code -> stat expansion.  When either is missing the call
        # returns without breakdown data (logged).
        if item is None or props_db is None or roll_context is None:
            logger.warning(
                "format_properties_grouped(breakdown=True) requires "
                "item= + props_db= + roll_context=; falling back to "
                "un-attributed output.",
            )
            return formatted

        try:
            from d2rr_toolkit.game_data.affix_rolls import (
                get_affix_roll_db,
                load_affix_rolls,
            )
            from d2rr_toolkit.game_data.corruption_rolls import (
                get_corruption_db,
                load_corruption_rolls,
            )
            from d2rr_toolkit.game_data.enchantment_recipes import (
                get_enchantment_db,
                load_enchantment_recipes,
            )
            from d2rr_toolkit.game_data.stat_breakdown import (
                StatBreakdownResolver,
            )
        except ImportError:
            logger.warning("stat breakdown imports failed; skipping attribution")
            return formatted

        # Lazy-load the three data sources the resolver needs.  The
        # cached_load helper makes repeat calls free.
        if not get_affix_roll_db().is_loaded():
            try:
                load_affix_rolls()
            except (OSError, ValueError, KeyError) as exc:
                logger.warning("affix_rolls auto-load failed: %s", exc)
        if not get_corruption_db().is_loaded():
            try:
                load_corruption_rolls()
            except (OSError, ValueError, KeyError) as exc:
                logger.warning("corruption_rolls auto-load failed: %s", exc)
        if not get_enchantment_db().is_loaded():
            try:
                load_enchantment_recipes()
            except (OSError, ValueError, KeyError) as exc:
                logger.warning("enchantment_recipes auto-load failed: %s", exc)

        resolver = StatBreakdownResolver(
            affix_db=get_affix_roll_db(),
            corruption_db=get_corruption_db(),
            enchant_db=get_enchantment_db(),
            isc_db=isc_db,
            props_db=props_db,
            skills_db=skills_db,
            item_types_db=item_types_db,
        )
        breakdowns = resolver.resolve_item(item, roll_context)

        # Stamp each FormattedProperty's ``breakdown`` field.  When a
        # single line collapses multiple stats (damage pair), we pick
        # the first stat's breakdown as representative - the GUI can
        # walk ``source_stat_ids`` if it needs per-half detail.
        out: list[FormattedProperty] = []
        for fp in formatted:
            sid = fp.source_stat_ids[0] if fp.source_stat_ids else None
            bd = breakdowns.get(sid) if sid is not None else None
            # Joint-perfection for multi-stat display lines
            # (``Adds X-Y Fire Damage`` collapses stats 48 + 49 into
            # one line).  The star must only appear when EVERY stat
            # in the group rolled at its range max - a max-min-side
            # + partial-max-side pair (4/max=4 + 7/max=8) must NOT
            # display the star.  The per-stat breakdown only attributes
            # ONE stat, so take ``is_perfect`` as the conjunction of
            # ``breakdown.is_perfect_roll`` across every source_stat_id
            # the line covers.
            is_perfect = fp.is_perfect
            if bd is not None:
                per_stat_perfections: list[bool] = []
                for s in fp.source_stat_ids:
                    sbd = breakdowns.get(s)
                    if sbd is not None:
                        per_stat_perfections.append(sbd.is_perfect_roll)
                if per_stat_perfections:
                    is_perfect = all(per_stat_perfections)
                else:
                    is_perfect = bd.is_perfect_roll
                # For multi-stat display lines (damage-pair collapses
                # like "Adds 1-5 Cold Damage"), the primary stat's
                # breakdown doesn't reflect partial perfection on the
                # follower side.  A GUI that reads
                # ``fp.breakdown.is_perfect_roll`` directly would see
                # stat-54-only perfection (True) and render the star
                # even though the max-side stat 55 rolled below its
                # ceiling.  Override the attached breakdown's
                # ``is_perfect_roll`` with the joint value so the
                # breakdown is consistent with the line's
                # ``is_perfect`` flag - callers that need the per-stat
                # perfection can still query ``breakdowns[stat_id]``
                # directly.
                if len(fp.source_stat_ids) > 1 and bd.is_perfect_roll != is_perfect:
                    from dataclasses import replace as _dc_replace

                    bd = _dc_replace(bd, is_perfect_roll=is_perfect)
            out.append(
                FormattedProperty(
                    segments=fp.segments,
                    plain_text=fp.plain_text,
                    source_stat_ids=fp.source_stat_ids,
                    roll_ranges=fp.roll_ranges,
                    is_perfect=is_perfect,
                    breakdown=bd,
                )
            )
        return out

    def format_properties_grouped_plain(
        self,
        props: list[dict],
        isc_db: "ItemStatCostDatabase",
        skills_db: "SkillDatabase | None" = None,
        lang: str = "enUS",
    ) -> list[str]:
        """Backward-compatible string-list wrapper for
        :meth:`format_properties_grouped`.

        Returns one ``plain_text`` per formatted property, preserving the
        pre-refactor behaviour byte-for-byte.  Toolkit-internal and
        external callers that do not need coloured segments can stay on
        this API indefinitely.  Roll-range metadata is deliberately not
        surfaced here - plain-string consumers have no way to render
        the star glyph or the ``[min-max]`` suffix anyway.
        """
        return [
            fp.plain_text
            for fp in self._format_properties_grouped_raw(
                props,
                isc_db,
                skills_db,
                lang,
            )
        ]

    def _format_properties_grouped_raw(
        self,
        props: list[dict],
        isc_db: "ItemStatCostDatabase",
        skills_db: "SkillDatabase | None" = None,
        lang: str = "enUS",
        *,
        roll_context: "ItemRollContext | None" = None,
        props_db: "PropertiesDatabase | None" = None,
    ) -> list[FormattedProperty]:
        """Shared implementation behind ``format_properties_grouped`` and
        its plain-text compatibility wrapper.

        Builds structured :class:`FormattedProperty` objects.  Every
        synthetic collapse line (``+X to all Attributes`` etc.) is
        emitted with an empty ``source_stat_ids``; real props carry
        ``(stat_id,)``; damage groups carry
        ``(lead_id, *follower_ids)``.
        """
        result: list[FormattedProperty] = []

        # Sort properties by descpriority DESCENDING (higher = shown first),
        # matching D2R in-game display order.  For stats with
        # descpriority=0 that have a DISPLAY_REDIRECT target, inherit
        # the target's priority (e.g. stat 97 -> stat 387's priority).
        #
        # Within a tied priority the game displays LATER-inserted
        # props FIRST - this surfaces on multi-instance stat_ids like
        # ``item_singleskill`` (stat 107) with multiple skill params.
        # For a Vicious Dagger of Maiming that carries Summon Goatman
        # (skill 373) then Demonic Mastery (skill 374), the binary
        # order is 373 -> 374 but the in-game tooltip shows 374 first.
        # The original-index tie-breaker below reverses same-priority
        # groups accordingly.  Python's ``sorted`` is stable; using
        # the NEGATIVE of the original index as the secondary key
        # gives us the reverse-insertion tie behavior without
        # disturbing the primary priority order.
        def _prio(entry: tuple[int, dict]) -> tuple[int, int]:
            idx, p = entry
            sid = p.get("stat_id", -1)
            sd = isc_db.get(sid)
            prio = sd.desc_priority if sd else 0
            if prio == 0 and sid in DISPLAY_REDIRECT:
                redirect_sd = isc_db.get(DISPLAY_REDIRECT[sid])
                if redirect_sd:
                    prio = redirect_sd.desc_priority
            return (-prio, -idx)

        props = [p for _, p in sorted(list(enumerate(props)), key=_prio)]

        # Build index: stat_id -> prop for fast lookup
        stat_to_prop: dict[int, dict] = {p["stat_id"]: p for p in props if "stat_id" in p}

        already_handled: set[int] = set()

        # ── Pre-compute collapse groups ───────────────────────────────────────
        # Detect which stat groups should be collapsed into a single line.
        # The collapsed line is emitted when the FIRST member stat is
        # encountered in the priority-sorted loop, so it appears at the
        # correct position rather than always at the top.
        # Synthetic collapses carry an empty ``source_stat_ids``:
        # they aggregate multiple stats into a line that has no
        # single canonical owner.  Consumers that want to know which
        # stats fed a collapse line can walk the stat-id set against
        # the well-known tuples below.
        # Maps: first_encountered_stat_id -> FormattedProperty (ready to emit)
        _collapse_lines: dict[int, FormattedProperty] = {}

        def _register_collapse(stat_ids: tuple[int, ...], raw_line: str) -> None:
            """Attach ``raw_line`` to the first member that appears in the
            priority-sorted prop list, wrapped as a :class:`FormattedProperty`
            with an empty ``source_stat_ids`` (synthetic collapse).

            When a roll context is active, also resolves the roll range
            via the member stats' source slot - without this, collapsed
            lines like "+12% to All Resistances" silently lose the
            range display even though the underlying set/unique slot
            (e.g. Vampire's Crusade ``res-all`` 8..15) is fully known
            to the resolver. [BV Vampire's Crusade ring]
            """
            formatted = _make_formatted(raw_line, source_stat_ids=())
            if formatted is None:
                return
            formatted = self._attach_collapse_roll_range(
                formatted,
                stat_ids=stat_ids,
                stat_to_prop=stat_to_prop,
                roll_context=roll_context,
                isc_db=isc_db,
                props_db=props_db,
                skills_db=skills_db,
            )
            for p in props:
                if p.get("stat_id") in stat_ids:
                    _collapse_lines[p["stat_id"]] = formatted
                    break
            already_handled.update(stat_ids)

        # Apply the 5 multi-stat collapse rules (All Attributes /
        # All Resistances / All Max Res / Elemental Mastery / Elemental
        # Pierce). Each fires only when every member stat is present
        # with the same value - matching the in-game rule. Extracted to
        # keep this function readable.
        for stat_ids, line_builder in self._collapse_rules():
            members = [stat_to_prop.get(sid) for sid in stat_ids]
            if not all(p is not None for p in members):
                continue
            values = [p["value"] for p in members]  # type: ignore[union-attr]
            if len(set(values)) != 1:
                continue
            raw_line = line_builder(values[0])
            if raw_line:
                _register_collapse(stat_ids, raw_line)

        # ── Pre-mark damage group followers as handled ────────────────────────
        # Followers (e.g. stat 18) must be suppressed when their lead (stat 17)
        # is present, regardless of sort order. The group line is emitted when
        # the lead stat is encountered.
        for lead_id, follower_ids in DAMAGE_STAT_GROUPS.items():
            if lead_id in stat_to_prop:
                for fid in follower_ids:
                    if fid in stat_to_prop:
                        already_handled.add(fid)

        # ── Suppress Reimagined duplicate damage stats ────────────────────────
        # Stats 23/24/159/160 duplicate stats 21/22 on jewels/charms.
        # Only suppress when the primary stat is present with the same value.
        for dup_id, primary_id in REIMAGINED_DUPLICATE_DAMAGE.items():
            dup = stat_to_prop.get(dup_id)
            primary = stat_to_prop.get(primary_id)
            if dup is not None and primary is not None:
                if dup.get("value") == primary.get("value"):
                    already_handled.add(dup_id)

        # Suppress display-mirror stats (e.g. stat 387) - they exist only as
        # template sources for DISPLAY_REDIRECT and must never be shown directly.
        already_handled.update(DISPLAY_MIRROR_STATS)

        for prop in props:
            stat_id = prop.get("stat_id")
            if stat_id is None:
                continue

            # Emit collapsed group line at its priority-correct position.
            # Check BEFORE already_handled since the trigger stat is also
            # in already_handled (to prevent individual formatting).
            if stat_id in _collapse_lines:
                result.append(_collapse_lines[stat_id])
                continue

            if stat_id in already_handled:
                continue

            # Suppress Reimagined-internal hidden skills (e.g. Hidden Charm Passive)
            if prop.get("param") in HIDDEN_SKILL_PARAMS:
                continue

            # Check if this is the lead of a damage group
            if stat_id in DAMAGE_STAT_GROUPS:
                raw_line = self._format_damage_group(stat_id, prop, stat_to_prop)
                if raw_line:
                    follower_ids = tuple(
                        fid for fid in DAMAGE_STAT_GROUPS[stat_id] if fid in stat_to_prop
                    )
                    fp = _make_formatted(
                        raw_line,
                        source_stat_ids=(stat_id, *follower_ids),
                    )
                    if fp is not None:
                        fp = self._attach_damage_pair_roll_ranges(
                            fp,
                            lead_prop=prop,
                            follower_props=[stat_to_prop[fid] for fid in follower_ids],
                            roll_context=roll_context,
                            isc_db=isc_db,
                            props_db=props_db,
                            skills_db=skills_db,
                        )
                        result.append(fp)
                    already_handled.add(stat_id)
                    for fid in DAMAGE_STAT_GROUPS[stat_id]:
                        already_handled.add(fid)
                    continue

            # Skip followers only if their lead stat is present (already handled).
            # Lone followers (e.g. stat 22 maxdamage without stat 21 mindamage)
            # should be displayed individually.
            if stat_id in DAMAGE_GROUP_FOLLOWERS and stat_id in already_handled:
                continue

            # Route through the *raw* formatter so the resulting
            # FormattedProperty retains any colour tokens that were in
            # the template (e.g. ``ÿcK`` on ``fadeDescription``).
            raw_line = self._format_prop_raw(prop, isc_db, skills_db, lang)
            fp = _make_formatted(raw_line, source_stat_ids=(stat_id,))
            if fp is not None:
                fp = self._attach_single_roll_range(
                    fp,
                    prop=prop,
                    stat_id=stat_id,
                    roll_context=roll_context,
                    isc_db=isc_db,
                    props_db=props_db,
                    skills_db=skills_db,
                )
                result.append(fp)
            # Only mark as handled if the stat should appear at most once.
            # Stats with save_param_bits > 0 (e.g. stat 107 item_singleskill,
            # stat 97 item_nonclassskill) can appear MULTIPLE times with
            # different param values - do NOT deduplicate those.
            sd = isc_db.get(stat_id)
            if sd is None or sd.save_param_bits == 0:
                already_handled.add(stat_id)

        return result

    # ── Roll-range attachment helpers (v1) ─────────────────────────────────

    def _attach_single_roll_range(
        self,
        fp: FormattedProperty,
        *,
        prop: dict,
        stat_id: int,
        roll_context: "ItemRollContext | None",
        isc_db: "ItemStatCostDatabase",
        props_db: "PropertiesDatabase | None",
        skills_db: "SkillDatabase | None",
    ) -> FormattedProperty:
        """Attach a single :class:`StatRollRange` + perfect flag.

        Returns ``fp`` unchanged when no context was provided or no
        range could be resolved.  Returns a NEW FormattedProperty
        (dataclass is frozen) with ``roll_ranges`` and
        ``is_perfect`` populated otherwise.
        """
        if roll_context is None:
            return fp
        rng = self._resolve_range_for_stat(
            stat_id=stat_id,
            prop=prop,
            roll_context=roll_context,
            isc_db=isc_db,
            props_db=props_db,
            skills_db=skills_db,
        )
        if rng is None:
            return fp
        current = self._current_value_for_perfection(prop, stat_id)
        # Consistency gate: if the rolled value lies OUTSIDE the
        # resolved range the source-row selection is almost certainly
        # wrong - e.g. a parser carry-chain edge case picks prefix_id
        # 1004 "Amber" for a charm that actually rolled via prefix 1003
        # "Coral", so the 25% Lightning Resistance value sits below
        # the Amber range [26, 30] (reported from VikingBarbie's Grand
        # Charm).  Showing that range mis-informs the user.  A roll
        # window MUST contain its own rolled value; when it doesn't,
        # drop the range + perfect flag so the tooltip falls back to
        # the plain value line.
        has_mods = roll_context.has_stat_modifiers
        if not _range_contains(rng, current, item_has_stat_modifiers=has_mods):
            return fp
        is_perfect = rng.is_perfect(current) and not has_mods
        return FormattedProperty(
            segments=fp.segments,
            plain_text=fp.plain_text,
            source_stat_ids=fp.source_stat_ids,
            roll_ranges=(rng,),
            is_perfect=is_perfect,
        )

    def _attach_damage_pair_roll_ranges(
        self,
        fp: FormattedProperty,
        *,
        lead_prop: dict,
        follower_props: list[dict],
        roll_context: "ItemRollContext | None",
        isc_db: "ItemStatCostDatabase",
        props_db: "PropertiesDatabase | None",
        skills_db: "SkillDatabase | None",
    ) -> FormattedProperty:
        """Attach (min_range, max_range) for a collapsed damage pair.

        ``roll_ranges[0]`` is the MIN-damage stat's range,
        ``roll_ranges[1]`` is the MAX-damage stat's range.
        ``is_perfect`` is True iff BOTH current values == their
        individual range maxima.

        When only one side has a resolvable range, emit the pair
        anyway with the un-resolvable side's ``roll_ranges`` entry
        omitted from the aggregate - edge case: "if only one of
        the pair has a resolvable roll range, pass the pair anyway".
        We model that as a tuple of the resolved ranges only
        (length 1 in that edge); consumers that expect length-2 MUST
        check ``len(roll_ranges)`` defensively.  When NEITHER side
        has a range we return ``fp`` unchanged (length-0 tuple).
        """
        if roll_context is None:
            return fp
        # Collect every prop in display order: lead first, then
        # followers in the order they appear in DAMAGE_STAT_GROUPS.
        # Exclude the length-side stats (coldlength=56, poisonlength=
        # 59) - the formatted damage line doesn't surface the duration
        # number in its range suffix ("Adds 1-2 Cold Damage" omits the
        # frame count), so including a third ``[25-25]`` entry in the
        # ``roll_ranges`` tuple surfaces a confusing orphan number in
        # the GUI.  The length is still attributed in the per-stat
        # breakdown for the individual length stat.
        _LENGTH_STATS: frozenset[int] = frozenset({56, 59})
        ordered: list[dict] = [
            lead_prop,
            *[p for p in follower_props if p.get("stat_id") not in _LENGTH_STATS],
        ]
        ranges: list[StatRollRange] = []
        current_vals: list[float] = []
        for p in ordered:
            sid = p.get("stat_id")
            if not isinstance(sid, int):
                continue
            rng = self._resolve_range_for_stat(
                stat_id=sid,
                prop=p,
                roll_context=roll_context,
                isc_db=isc_db,
                props_db=props_db,
                skills_db=skills_db,
            )
            if rng is None:
                continue
            cur = self._current_value_for_perfection(p, sid)
            # Same consistency gate as _attach_single_roll_range -
            # a stale prefix_id can surface a range that doesn't
            # contain the rolled value.  Skip the half in that case
            # rather than mislead the user.  For items with active
            # stat modifiers the ceiling is lifted (current may
            # legitimately exceed range.max) but the floor stays
            # strict - no modifier in Reimagined drives a positive
            # stat below its range minimum.
            if not _range_contains(
                rng,
                cur,
                item_has_stat_modifiers=roll_context.has_stat_modifiers,
            ):
                continue
            ranges.append(rng)
            current_vals.append(cur)
        if not ranges:
            return fp
        # Broadcast collapse: when every resolved range is identical
        # (same min, max, source), the pair is sourced from a single
        # rolled value that the game applies to every stat in the
        # group - e.g. Occam's Razor "+161% Enhanced Weapon Damage"
        # where ``dmg%`` feeds ONE rolled ED% into both stat 17 and
        # stat 18.  Showing "[140-190 / 140-190]" mis-suggests two
        # independent rolls; collapse to a single range.  Keep the
        # tuple length == 2 when the sides came from genuinely
        # different slots (e.g. separate ``dmg-min`` + ``dmg-max``
        # rolls with distinct ranges - same display, different bins).
        if len(ranges) >= 2 and all(r == ranges[0] for r in ranges[1:]):
            collapsed = (ranges[0],)
        else:
            collapsed = tuple(ranges)
        is_perfect = (
            all(rng.is_perfect(val) for rng, val in zip(ranges, current_vals))
            and not roll_context.has_stat_modifiers
        )
        return FormattedProperty(
            segments=fp.segments,
            plain_text=fp.plain_text,
            source_stat_ids=fp.source_stat_ids,
            roll_ranges=collapsed,
            is_perfect=is_perfect,
        )

    def _collapse_rules(
        self,
    ) -> list[tuple[tuple[int, ...], Callable[[int], str | None]]]:
        """Return the five multi-stat collapse rules the formatter applies.

        Each rule pairs a tuple of member stat IDs with a function that
        renders the collapsed line from the shared value. Rules fire
        only when every member stat is present with the same value
        (enforced by the caller); this method is deliberately pure /
        stateless so unit tests can exercise the builders in
        isolation.

        Returns:
            List of ``(stat_ids, line_builder(value) -> raw_line_or_None)``
            tuples. The order matches the legacy in-function layout so
            output ordering is preserved exactly.
        """

        def _all_attributes(v: int) -> str:
            return f"+{v} to all Attributes"

        def _all_resistances(v: int) -> str | None:
            tmpl = self._templates.get(
                "strModAllResistances",
                "%+d%% to All Resistances",
            )
            return _apply_template(tmpl, v)

        def _all_max_resistances(v: int) -> str:
            return f"+{v}% to All Maximum Resistances"

        def _elemental_mastery(v: int) -> str:
            return f"+{v}% to All Elemental Skill Damage"

        def _elemental_pierce(v: int) -> str:
            return f"-{v}% to Enemy Elemental Resistance"

        return [
            ((0, 1, 2, 3), _all_attributes),  # str/eng/dex/vit
            ((39, 41, 43, 45), _all_resistances),  # fire/ltng/cold/pois
            ((40, 42, 44, 46), _all_max_resistances),  # max variants
            ((329, 330, 331, 332), _elemental_mastery),  # mastery 4-elem
            ((333, 334, 335, 336), _elemental_pierce),  # pierce 4-elem
        ]

    def _attach_collapse_roll_range(
        self,
        fp: FormattedProperty,
        *,
        stat_ids: tuple[int, ...],
        stat_to_prop: dict[int, dict],
        roll_context: "ItemRollContext | None",
        isc_db: "ItemStatCostDatabase",
        props_db: "PropertiesDatabase | None",
        skills_db: "SkillDatabase | None",
    ) -> FormattedProperty:
        """Attach a roll range to a collapsed multi-stat line.

        Handles the five collapse groups emitted by ``_register_collapse``
        (All Attributes / All Resistances / All Maximum Resistances /
        All Elemental Skill Damage / Enemy Elemental Resistance). Each
        collapse gets its values from a SINGLE source slot whose code
        expands to the member stats at runtime (``res-all`` ->
        fire/light/cold/poison resist, ``all-stats`` -> str/energy/dex/vit,
        etc.). The roll resolver already understands that expansion - it
        returns the same ``StatRollRange`` for every member stat. Our job
        here is to query at least one member and attach the resolved
        range to the collapse line.

        We query EVERY member and verify they all return an identical
        range. If so, we attach a single-element ``roll_ranges`` tuple.
        If they diverge (shouldn't happen with current data but a sanity
        net for future multi-source collapses), we fall back to no
        range attachment so the tooltip reverts to the unparameterised
        line rather than showing a misleading range.

        Returns ``fp`` unchanged when no context was provided, when no
        range was resolvable, or when the rolled values sit outside the
        resolved range (the same consistency gate used by
        :meth:`_attach_single_roll_range`).
        """
        if roll_context is None:
            return fp

        ranges: list = []
        current_vals: list[int] = []
        for sid in stat_ids:
            prop = stat_to_prop.get(sid)
            if prop is None:
                continue
            rng = self._resolve_range_for_stat(
                stat_id=sid,
                prop=prop,
                roll_context=roll_context,
                isc_db=isc_db,
                props_db=props_db,
                skills_db=skills_db,
            )
            if rng is None:
                continue
            cur = self._current_value_for_perfection(prop, sid)
            # Same consistency gate as the single-stat path - a stale
            # source-row selection can yield a window that doesn't
            # contain the rolled value.  Skip the mismatched member;
            # if ALL members are skipped we fall through and return
            # ``fp`` unchanged below.
            if not _range_contains(
                rng,
                cur,
                item_has_stat_modifiers=roll_context.has_stat_modifiers,
            ):
                continue
            ranges.append(rng)
            current_vals.append(cur)

        if not ranges:
            return fp

        # All member stats share one source slot -> ranges should be
        # identical. Collapse to a single-element tuple. If they
        # diverge the resolver is reading multiple source rows, which
        # violates the single-slot assumption for these collapses;
        # surface NO range rather than pick arbitrarily.
        if not all(r == ranges[0] for r in ranges[1:]):
            return fp

        is_perfect = (
            all(rng.is_perfect(val) for rng, val in zip(ranges, current_vals))
            and not roll_context.has_stat_modifiers
        )
        return FormattedProperty(
            segments=fp.segments,
            plain_text=fp.plain_text,
            source_stat_ids=fp.source_stat_ids,
            roll_ranges=(ranges[0],),
            is_perfect=is_perfect,
        )

    # Class property codes -> class index for stat 83 (item_addclassskills).
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

    def format_code_value(
        self,
        code: str,
        value: int,
        param: str = "",
        props_db: "PropertiesDatabase | None" = None,
        isc_db: "ItemStatCostDatabase | None" = None,
        skills_db: "SkillDatabase | None" = None,
        lang: str = "enUS",
    ) -> str | None:
        """Format a property code + value (from sets.txt/setitems.txt) to a display string.

        Used for set bonus display where bonuses are stored as property codes
        (e.g. "res-fire", min=25, max=25) rather than binary stat_ids.

        Args:
            code:     Property code (e.g. "res-fire", "str", "ac").
            value:    The effective value (usually min==max, so just use min).
            param:    Optional param string (for skill-related codes).
            props_db: Loaded PropertiesDatabase.
            isc_db:   Loaded ISC database.
            skills_db: Loaded skills database.
            lang:     Language code.

        Returns:
            Display string or fallback.
        """
        if not code:
            return None
        if props_db is None or isc_db is None:
            return f"{code} +{value}" if value else code

        # ── Class skill codes (ama, sor, nec, pal, bar, dru, ass, war) ────
        # These map to stat 83 (item_addclassskills) with param = class index.
        if code in self._CLASS_CODE_TO_INDEX:
            from d2rr_toolkit.game_data.charstats import get_charstats_db

            cls_idx = self._CLASS_CODE_TO_INDEX[code]
            cls_name = get_charstats_db().get_class_name(cls_idx) or code
            sign = "+" if value >= 0 else ""
            return f"{sign}{value} to {cls_name} Skill Levels"

        # ── Multi-stat properties (e.g. res-all -> fire+light+cold+poison) ─
        # If code has 3+ stat slots with the same value, show as combined line.
        prop_def = props_db.get(code)
        if prop_def is None:
            return f"{code} +{value}" if value else code

        if code == "res-all":
            tmpl = self._templates.get("strModAllResistances", "%+d%% to All Resistances")
            return _apply_template(tmpl, value)

        if code == "res-all-max":
            return f"+{value}% to All Maximum Resistances"

        if code == "pierce-elem":
            return f"-{value}% to All Enemy Elemental Resistances"

        if code == "extra-elem":
            return f"+{value}% to All Elemental Skill Damage"

        # ── Func-only codes (no stat1 in properties.txt) ────────────────
        # The engine applies these via the ``func`` column.  Route them
        # through the canonical ISC stat so the existing template
        # machinery produces the correct game-facing label (e.g.
        # "+200% Enhanced Weapon Damage" instead of "+200 dmg%").
        #
        # ``ethereal`` has no ISC stat - it's a flag the game displays
        # as a static tooltip string, so handle it directly.
        if code == "ethereal":
            tmpl = self._templates.get(
                "strethereal",
                "Ethereal (Cannot be Repaired)",
            )
            return tmpl

        # Get primary stat - with func-only fallback for the handful of
        # codes where properties.txt declares no stat1 column.
        stat_id = prop_def.primary_stat_id(isc_db)
        if stat_id is None:
            fallback_stat = _FUNC_ONLY_CODE_TO_STAT.get(code)
            if fallback_stat is not None:
                stat_id = fallback_stat
                # For ``dmg%`` specifically, route through the damage-
                # group template so the output matches the binary-stat
                # rendering exactly (Enhanced Weapon Damage line).
                if code == "dmg%":
                    template = DAMAGE_GROUP_TEMPLATES.get(17)
                    if template:
                        sign = "+" if value >= 0 else ""
                        return template % {"val": f"{sign}{value}"}
            else:
                return f"+{value} {code}"

        stat_def = isc_db.get(stat_id)
        if stat_def is None:
            return f"+{value} {code}"

        # ── Skill property codes (code='skill', param=skill_name) ─────────
        # param is a skill NAME string (e.g. "Wearwolf"), not a numeric ID.
        # Resolve to skill ID for template substitution.
        param_int = 0
        if param:
            try:
                param_int = int(param)
            except ValueError:
                # Non-numeric param - look up skill by name
                if skills_db is not None:
                    param_int = skills_db.id_by_name(param) or 0
                else:
                    param_int = 0

        return self._apply_stat_template(stat_def, value, param_int, skills_db)

    def format_code_range(
        self,
        code: str,
        value_min: int,
        value_max: int,
        param: str = "",
        props_db: "PropertiesDatabase | None" = None,
        isc_db: "ItemStatCostDatabase | None" = None,
        skills_db: "SkillDatabase | None" = None,
        lang: str = "enUS",
    ) -> str | None:
        """Format a property code with a min-max range (for automod display).

        When min == max, delegates to :meth:`format_code_value`.
        When min != max, shows a range like "+1-5 to Life".
        """
        if value_min == value_max:
            return self.format_code_value(
                code,
                value_min,
                param,
                props_db,
                isc_db,
                skills_db,
                lang,
            )
        # Format with min value, then replace the numeric part with "min-max"
        display = self.format_code_value(
            code,
            value_min,
            param,
            props_db,
            isc_db,
            skills_db,
            lang,
        )
        if display:
            min_s = str(value_min)
            range_s = f"{value_min}-{value_max}"
            if min_s in display:
                return display.replace(min_s, range_s, 1)
        return f"{code} ({value_min}-{value_max})"

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _apply_stat_template(
        self,
        stat_def: "StatDefinition",
        value: int,
        param: int,
        skills_db: "SkillDatabase | None",
    ) -> str | None:
        """Apply a stat's descstrpos/descstrneg template with the given value."""
        # Per-character-level stats (stat names containing "perlevel").
        # Binary stores value*8; display = value/8, with "(Based on Character Level)".
        # Note: descfunc=19 is the standard %+d format used by MOST stats -
        # it does NOT indicate per-level. Only the stat NAME determines this.
        if stat_def.name and "perlevel" in stat_def.name:
            per_level = value / 8
            if per_level == int(per_level):
                val_str = f"{int(per_level):+d}"
            else:
                val_str = f"+{per_level:.2f}" if per_level >= 0 else f"{per_level:.2f}"
            key = stat_def.descstrpos
            tmpl = self._templates.get(key, "") if key else ""
            if tmpl:
                import re as _re

                line = _re.sub(r"%\+?d", val_str, tmpl)
                line = line.replace("%%", "%")
            else:
                line = f"{val_str} {stat_def.name or key}"
            return f"{line} (Based on Character Level)"

        key = stat_def.descstrpos if value >= 0 else (stat_def.descstrneg or stat_def.descstrpos)
        if not key:
            # descfunc=0 means "internal/hidden stat - not shown in tooltip"
            if stat_def.descfunc == 0:
                return None
            # Other stats with a missing template - fall back to stat name as debug aid
            if stat_def.name:
                return f"+{value} {stat_def.name}" if value >= 0 else f"{value} {stat_def.name}"
            return None

        template = self._templates.get(key)
        if not template:
            # Key exists but no template loaded -> fall back
            return f"+{value} {key}"

        # Determine if a skill name is needed (%s in template)
        name_str = ""
        name_str2 = ""
        if "%s" in template:
            if skills_db is not None:
                name_str = skills_db.name(param) or str(param)
                # Second %s: class name for class-specific skills (e.g. "(Assassin only)")
                if template.count("%s") >= 2:
                    skill_def = skills_db.get(param)
                    if skill_def and skill_def.charclass:
                        _CLASS_CODE_TO_NAME = {
                            "ama": "Amazon",
                            "sor": "Sorceress",
                            "nec": "Necromancer",
                            "pal": "Paladin",
                            "bar": "Barbarian",
                            "dru": "Druid",
                            "ass": "Assassin",
                            "war": "Warlock",
                        }
                        cls_name = _CLASS_CODE_TO_NAME.get(skill_def.charclass, skill_def.charclass)
                        name_str2 = f"({cls_name} Only)"

        # descfunc / descval rules (D2 convention): when the template
        # has no ``%d`` / ``%+d`` placeholder, the engine prepends or
        # appends the numeric value based on descfunc + descval.
        #
        #   descval = 0 : value not displayed at all (template only).
        #   descval = 1 : value BEFORE template text (``{val} {text}``).
        #   descval = 2 : value AFTER template text  (``{text} {val}``).
        #
        # descfunc then selects the numeric format:
        #   1  -> +value          (e.g. ``"+1 Life Per Hit"``)
        #   2  -> value%          (e.g. ``"1% Chance to ..."``)
        #   3  -> static string - no numeric (treated as descval=0)
        #   4  -> +value%         (e.g. ``"+1% Chance ..."``)
        #   5  -> value%          (alias of 2 per D2 quirks)
        #   6  -> +value          (alias of 1)
        #   7  -> value%          (alias of 2)
        #   8  -> +value%         (alias of 4)
        #   9  -> value           (plain integer, no sign)
        #  10  -> value%          (alias of 2)
        #  12  -> +value          (alias of 1 per Reimagined)
        # Other descfuncs either inject %d into the template (19-based
        # standard) or use custom paths earlier (11, 13, 14, 16, 20).
        if "%d" not in template and "%+d" not in template:
            val_str: str | None = None
            descfunc = stat_def.descfunc
            descval = stat_def.descval
            if descval != 0 and descfunc not in (0, 3):
                if descfunc in (1, 6, 12):
                    val_str = f"{value:+d}"  # "+1" / "-1"
                elif descfunc in (2, 5, 7, 10):
                    val_str = f"{value}%"
                elif descfunc in (4, 8):
                    val_str = f"{value:+d}%" if value != 0 else "0%"
                elif descfunc == 9:
                    val_str = f"{value}"
            if val_str is not None:
                # name-placeholder substitution still needs to happen
                # for templates like ``"+%d to %s"`` - but if we land
                # here the template has no %d, so name_str is the only
                # other concern.  Keep it simple: apply the val + text.
                body = template
                if "%s" in body:
                    # Replace first %s with skill name, second with class qualifier
                    body = body.replace("%s", name_str, 1)
                    if name_str2:
                        body = body.replace("%s", name_str2, 1)
                if descval == 1:
                    return f"{val_str} {body}".strip()
                if descval == 2:
                    return f"{body} {val_str}".strip()

        return _apply_template(template, value, 0, name_str, name_str2)

    def _format_skill_on_event(
        self,
        prop: dict,
        stat_def: "StatDefinition",
        skills_db: "SkillDatabase | None",
    ) -> str | None:
        """Format Encode=2 (skill-on-event) property."""
        level = prop.get("level", 0)
        skill_id = prop.get("skill_id", 0)
        chance = prop.get("chance", 0)
        skill_name = (
            prop.get("skill_name")
            or (skills_db.name(skill_id) if skills_db else None)
            or f"Skill{skill_id}"
        )

        key = stat_def.descstrpos
        template = self._templates.get(key, "%d%% Chance to cast level %d %s on attack")

        # Templates like "%d%% Chance to cast level %d %s on attack"
        # need: chance, level, skill_name
        result = template
        result = re.sub(r"%\+d", f"{chance:+d}", result, count=1)

        # Replace first %d with chance, second with level
        count = [0]

        def repl(m: re.Match) -> str:
            count[0] += 1
            return str(chance) if count[0] == 1 else str(level)

        result = re.sub(r"%d", repl, result)
        result = result.replace("%%", "%")
        if "%s" in result:
            result = result.replace("%s", skill_name, 1)
        # Colour tokens stay intact - the public structured API handles
        # the final segment split; the plain-text API strips.
        return result.strip()

    def _format_charged_skill(
        self,
        prop: dict,
        stat_def: "StatDefinition",
        skills_db: "SkillDatabase | None",
    ) -> str | None:
        """Format Encode=3 (charged skill) property."""
        level = prop.get("level", 0)
        skill_id = prop.get("skill_id", 0)
        charges = prop.get("charges", 0)
        max_charges = prop.get("max_charges", 0)
        skill_name = (
            prop.get("skill_name")
            or (skills_db.name(skill_id) if skills_db else None)
            or f"Skill{skill_id}"
        )

        key = stat_def.descstrpos
        template = self._templates.get(key, "Level %d %s (%d/%d Charges)")

        # Template: "Level %d %s (%d/%d Charges)" -> level, skill_name, charges, max_charges
        result = template
        vals = [level, charges, max_charges]
        idx = [0]

        def repl(m: re.Match) -> str:
            v = vals[idx[0]] if idx[0] < len(vals) else 0
            idx[0] += 1
            return str(v)

        result = re.sub(r"%d", repl, result)
        result = result.replace("%%", "%")
        if "%s" in result:
            result = result.replace("%s", skill_name, 1)
        # See ``_format_skill_on_event`` - colour tokens preserved.
        return result.strip()

    def _format_damage_group(
        self,
        lead_stat_id: int,
        lead_prop: dict,
        stat_to_prop: dict[int, dict],
    ) -> str | None:
        """Format a damage group (min+max or enhanced damage pair) as one line."""
        template = DAMAGE_GROUP_TEMPLATES.get(lead_stat_id)
        if template is None:
            return None

        val_min = lead_prop.get("value", 0)
        follower_ids = DAMAGE_STAT_GROUPS.get(lead_stat_id, [])
        val_max = stat_to_prop.get(follower_ids[0], {}).get("value", 0) if follower_ids else 0

        if lead_stat_id == 17:
            # Enhanced damage: show only the "enhanced" value with sign
            sign = "+" if val_min >= 0 else ""
            return template % {"val": f"{sign}{val_min}"}

        # Poison damage (57->58,59): convert binary values to display.
        # Binary: poisonmindam = display_dmg * 256 / duration_frames
        # Display: damage = round(raw * duration / 256), secs = duration / 25
        if lead_stat_id == 57 and len(follower_ids) >= 2:
            duration_frames = stat_to_prop.get(follower_ids[1], {}).get("value", 0)
            if duration_frames > 0:
                display_min = round(val_min * duration_frames / 256)
                display_max = round(val_max * duration_frames / 256)
                display_secs = duration_frames // _FRAMES_PER_SECOND
                if display_min == display_max:
                    return f"+{display_min} Poison Damage Over {display_secs} Secs"
                return f"Adds {display_min}-{display_max} Poison Damage Over {display_secs} Secs"

        # Cold damage (54->55,56): no duration display (only Poison has "Over X Secs")
        if lead_stat_id == 54:
            if val_min == val_max:
                return f"+{val_min} Weapon Cold Damage"
            return f"Adds {val_min}-{val_max} Weapon Cold Damage"

        # Fire / Lightning / Magic / Physical weapon damage: when the
        # min and max values are identical the in-game tooltip collapses
        # the "Adds X-X" phrasing to the simpler "+X DamageType" form
        # (e.g. "+1 Weapon Lightning Damage" for a Small Charm that
        # rolled both light-min and light-max at 1).  Reproduce that
        # collapse so the tooltip matches the game verbatim.
        if val_min == val_max:
            type_suffixes = {
                21: "Weapon Damage",
                23: "Weapon Damage",
                48: "Weapon Fire Damage",
                50: "Weapon Lightning Damage",
                52: "Weapon Magic Damage",
            }
            type_text = type_suffixes.get(lead_stat_id)
            if type_text:
                return f"+{val_min} {type_text}"

        return template % {"min": val_min, "max": val_max}


# ── Module-level singleton ─────────────────────────────────────────────────────

_PROP_FORMATTER = PropertyFormatter()


def get_property_formatter() -> PropertyFormatter:
    """Return the global PropertyFormatter singleton."""
    return _PROP_FORMATTER


SCHEMA_VERSION_PROPERTY_FORMATTER: int = 1


def load_property_formatter(
    *,
    use_cache: bool = True,
    source_versions: "SourceVersions | None" = None,
    cache_dir: "Path | None" = None,
) -> None:
    """Populate the :class:`PropertyFormatter` from the strings table.

    Reads ``data/local/lng/strings/item-modifiers.json`` (via
    :func:`read_game_data_bytes`).  Holds every ``descstrpos`` /
    ``descstrneg`` template the formatter substitutes values into
    - including the raw ``\\xFFc<L>`` colour tokens that the
    structured :class:`FormattedProperty` output preserves (see
    ``FORMATTED_PROPERTIES.md`` for the full colour-token table).

    Transparently backed by the persistent pickle cache - see
    :mod:`d2rr_toolkit.meta.cache` for the invalidation contract.

    Args:
        use_cache: ``False`` disables the cache for this call.
        source_versions: Optional :class:`SourceVersions`; shared
            instance preferred across batched loaders.
        cache_dir: Optional cache root override.
    """
    from d2rr_toolkit.meta import cached_load

    def _build() -> None:
        _build_property_formatter_from_source()

    cached_load(
        name="property_formatter",
        schema_version=SCHEMA_VERSION_PROPERTY_FORMATTER,
        singleton=get_property_formatter(),
        build=_build,
        use_cache=use_cache,
        source_versions=source_versions,
        cache_dir=cache_dir,
    )


def _build_property_formatter_from_source() -> None:
    """Legacy parse path - fetch JSON via CASC and load into the singleton."""
    from d2rr_toolkit.adapters.casc import read_game_data_bytes

    casc_path = "data:data/local/lng/strings/item-modifiers.json"
    raw = read_game_data_bytes(casc_path)
    if raw is None:
        logger.warning(
            "item-modifiers.json not found in mod or CASC - property display strings unavailable."
        )
        return
    get_property_formatter().load_from_bytes(raw, source=casc_path)



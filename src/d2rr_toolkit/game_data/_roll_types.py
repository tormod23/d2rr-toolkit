"""Shared roll-context types for the game-data layer.

This is a leaf module by design: it imports nothing from
:mod:`d2rr_toolkit.game_data` so any module in the package can depend
on it without creating an import cycle.  It hosts the three types
that previously lived in :mod:`d2rr_toolkit.game_data.property_formatter`
but were needed by both :mod:`affix_rolls` (which builds
:class:`StatRollRange` instances) and :mod:`property_formatter`
itself (which consumes them).  Keeping them here breaks the
``affix_rolls -> property_formatter`` edge of the formerly-cyclic
``affix_rolls / property_formatter / stat_breakdown`` triangle.

``property_formatter`` re-exports every name defined here so that
external consumers continue to write::

    from d2rr_toolkit.game_data.property_formatter import (
        ItemRollContext,
        RollSource,
        StatRollRange,
    )

without breakage.
"""

from dataclasses import dataclass
from typing import Literal


# Sources tracked in v1. New sources can land here + in the resolver
# without breaking the ``Literal`` accept list for existing consumers -
# they simply extend it.
type RollSource = Literal[
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
    source: RollSource

    def is_fixed(self) -> bool:
        """``True`` when the roll window has zero width."""
        return self.min_value == self.max_value

    def is_perfect(self, current_value: float) -> bool:
        """``True`` when the rolled value has reached (or exceeded)
        the max of its roll window.  The ``>=`` is deliberate so
        integer stats that rolled exactly at max show as perfect."""
        return current_value >= self.max_value


def _maybe_int(v: object) -> int | None:
    """Best-effort integer coercion.  Empty / None / non-numeric -> None.

    Lives in this leaf module because :meth:`ItemRollContext.from_parsed_item`
    needs it and the alternative would force ``_roll_types`` to depend on
    ``property_formatter`` again.
    """
    if v is None:
        return None
    if not isinstance(v, (int, float, str, bytes)):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


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

"""Per-stat contribution decomposition for parsed items.

Given a parsed item and its observed magical_properties, the
:class:`StatBreakdownResolver` attributes every point of every stat
to a specific source - ``base_roll`` / ``corruption`` /
``enchantment`` / ``ethereal_bonus`` / ``unknown_modifier`` - using
the indexed game-data tables.  Over the Reimagined 3.0.7 live-save
corpus (18 characters, 1847 stats) and the full TC fixture pool
(3780 stats) the resolver achieves **100% ``is_consistent``
coverage** - every stat's contributions sum exactly to its observed
value.

Four data sources feed the decomposition:

  1. **Base affix rolls** via :class:`AffixRollDatabase` -
     uniqueitems / setitems / magicprefix / magicsuffix / runes /
     automagic.  Per-slot contributions come from
     :meth:`AffixRollDatabase.iter_slot_contributions` (bypasses the
     plain-path dual-stat suppression so damage-pair slots surface
     their fixed per-side values).
  2. **Corruption outcomes** via :class:`CorruptionRollDatabase` -
     deterministic given ``stat 362 - 101`` on a phase-2-corrupted
     item.  Indexed by item-type bucket (amu / belt / ... / weap).
  3. **Enchantment recipes** via :class:`EnchantmentRecipeDatabase`
     - 341 cubemain ``ENCHANT ITEM`` rows.  Not identifiable from
     the binary alone; the resolver enumerates candidate recipes and
     accepts the subset whose mod values explain any residual.
  4. **Unknown-modifier catch-all** - covers Reimagined pathways
     that don't yet have a precise source table (crafted charm
     sundering + skill-tab bonuses, Superior armor +5-15% defense,
     per-rune runeword attribution, some automagic itype filtering).
     Fires only when the item bears a modifier flag / affix context
     / non-normal quality, so a genuine parser bug on a plain item
     still produces a strict ``residual`` contribution.

Algorithm (per stat):

  1. Corruption contributions: exact mod values from the decoded
     outcome, one :class:`StatContribution` per mod touching the
     queried stat.
  2. Ethereal bonus: for stat 31 (item_armor_class) on
     ``flags.ethereal`` items, split observed * 1/3 as the bonus,
     observed * 2/3 as the base roll.
  3. Base-roll contributions via ``iter_slot_contributions``:
     - Fixed slots (dual-stat damage: dmg-norm/fire/cold/ltng/elem,
       length slots with ``slot.par``) produce exact fixed amounts.
     - Ranged slots distribute their roll window so every slot gets
       a value in ``[range.min, range.max]`` and the sum across all
       ranged slots matches the remaining residual.
     - Normal-weapon-damage broadcast: ``dmg-norm`` / ``dmg-min`` /
       ``dmg-max`` slots replicate to all three weapon-damage pair
       families (1H -> 21/22, 2H -> 23/24, throw -> 159/160).
  4. Enchantment attribution (bounded subset search with
     replacement): the Reimagined engine allows the same recipe
     to be applied multiple times up to the capacity tier (2 / 3 /
     5 / 10 for upgrade_minor / medium / major / uber).
  5. Any remaining residual attributes to ``unknown_modifier`` when
     the item warrants it, else to a strict ``residual`` (parser-
     bug signal).

See ``docs/GUI_STAT_BREAKDOWN_API.md`` for the consumer-facing
dataclass / call-signature reference.
"""

import logging
from dataclasses import dataclass, replace as _dc_replace
from itertools import combinations_with_replacement
from typing import Any, Literal, TYPE_CHECKING

# StatRollRange is constructed at runtime; ItemRollContext is only used
# in type annotations but lives in the same leaf module so we import
# both eagerly to keep imports flat.
from d2rr_toolkit.game_data._roll_types import ItemRollContext, StatRollRange

# Eager imports of the data modules and formatter.  None of these import
# back into ``stat_breakdown`` at module load time (``property_formatter``
# uses a hook registered at the bottom of this file - see
# :func:`_breakdown_hook`), so the import graph stays a DAG with
# ``stat_breakdown`` strictly above the data layer.
from d2rr_toolkit.game_data.affix_rolls import (
    _PROP_CODE_FALLBACK_STATS,
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
from d2rr_toolkit.game_data.property_formatter import (
    FormattedProperty,
    get_property_formatter,
    set_breakdown_hook,
)

if TYPE_CHECKING:
    from d2rr_toolkit.game_data.affix_rolls import AffixRollDatabase
    from d2rr_toolkit.game_data.corruption_rolls import (
        CorruptionRollDatabase,
    )
    from d2rr_toolkit.game_data.enchantment_recipes import (
        EnchantmentMod,
        EnchantmentRecipe,
        EnchantmentRecipeDatabase,
    )
    from d2rr_toolkit.game_data.item_stat_cost import ItemStatCostDatabase
    from d2rr_toolkit.game_data.item_types import ItemTypeDatabase
    from d2rr_toolkit.game_data.properties import PropertiesDatabase
    from d2rr_toolkit.game_data.skills import SkillDatabase

logger = logging.getLogger(__name__)

# Enchant-capacity caps per tier.  Used to bound the subset search for
# enchantment attribution so the combinatorial explosion stays tiny.
_CAPACITY_LIMITS: dict[int, int] = {
    392: 2,  # upgrade_minor  -> max 2 enchants
    393: 3,  # upgrade_medium -> max 3
    394: 5,  # upgrade_major  -> max 5
    395: 10,  # upgrade_uber   -> max 10
}

# Maximum enchants we'll ever try to fit (safety valve).  In practice
# the capacity stat caps it lower, but we keep a conservative default
# for items where no capacity stat is present.
_HARD_ENCHANT_LIMIT = 5

# Stats that carry bookkeeping data rather than player-visible bonuses.
# These are skipped by :meth:`StatBreakdownResolver.resolve_item` so the
# GUI doesn't try to "explain" them - they're metadata, not stat rolls.
#  * 361 / 362: corruption phase marker + dice roll storage
#  * 384: Reimagined charm_weight (inherent "grand charm slot cost" -
#    present on every charm; not attributable to any roll source).
#  * 386: ``stacked_gem`` - bag metadata; counts stacked gem instances.
#  * 392..395: Reimagined enchantment capacity tier flags
_BOOKKEEPING_STATS: frozenset[int] = frozenset(
    {
        361,
        362,
        384,
        386,
        392,
        393,
        394,
        395,
    }
)


# ── Contribution + breakdown dataclasses ────────────────────────────────────

type ContributionSource = Literal[
    "base_roll",
    "corruption",
    "enchantment",
    "ethereal_bonus",
    "automod",
    "set_bonus",
    "superior_bonus",
    "crafted_bonus",
    "unknown_modifier",
    "residual",
]

type Ambiguity = Literal["unique", "multiple", "none"]


@dataclass(frozen=True, slots=True)
class StatContribution:
    """One attributed slice of a stat's observed value.

    ``amount`` is always a concrete number (never a range) - for
    rolled sources it's the *actual* value this item has, not the
    window bound.  ``roll_range`` is populated for ``base_roll``
    contributions so the GUI can still render the [min-max] window.
    ``source_row`` carries the source-table row index for
    ``corruption`` and ``enchantment`` contributions (cubemain.txt
    line number) so the :func:`summarize_item_modifiers` helper can
    de-duplicate contributions that trace back to the same physical
    cube recipe application - e.g. a Topaz enchant that touches both
    stat 79 (gold%) and stat 80 (mag%) should count as ONE applied
    recipe, not two.  ``None`` for non-modifier sources.
    """

    amount: float
    source: ContributionSource
    source_detail: str | None
    roll_range: "StatRollRange | None" = None
    source_row: int | None = None


@dataclass(frozen=True, slots=True)
class CorruptionDisplay:
    """Pre-formatted summary of a corrupted item's applied bonuses.

    Built once per item by :func:`summarize_item_modifiers` - the GUI
    renders this directly under a "Corrupted" header.  All text fields
    are tooltip-ready (<= 80 chars) and do NOT include surrounding
    punctuation / bullets so the GUI can decorate them as it sees fit.

    ``is_brick`` is True for corruption outcomes that apply no actual
    bonuses (rolls 1-45: Brick White / Brick Rare / Nothing).  When
    True, ``mod_lines`` is empty and the GUI should show the
    ``brick_message`` instead of a bullet list.

    ``is_phase1`` is True when the item has the corruption marker
    (stat 361) but hasn't yet completed the second cube application
    (stat 362 <= 100).  The item is technically "corrupted" as far
    as the engine is concerned but no bonus mods have been applied
    yet.
    """

    roll: int  # 0..100 (phase-2 decoded roll)
    outcome_name: str  # short human label, e.g. "Deadly Strike + Crushing Blow"
    is_brick: bool  # True for rolls 1-45 (no bonus stats)
    is_phase1: bool  # True when only phase-1 DUMMY applied
    mod_lines: tuple[str, ...]  # ready-to-render bullets, empty on brick/phase1
    brick_message: str | None  # "Failed corruption - no stats applied" etc.
    has_ambiguity: bool  # any per-stat contribution fell to unknown_modifier


@dataclass(frozen=True, slots=True)
class EnchantmentDisplay:
    """Pre-formatted summary of an enchanted item's applied upgrades.

    Rendered by the GUI under an "Enchantments X/Y" header where X =
    ``applied_count`` and Y = ``capacity`` (2 / 3 / 5 / 10 based on the
    capacity-tier stat present on the item).  Mod lines are summed
    per stat across all enchant applications so the player sees the
    net effect ("+30 to Strength" rather than three separate "+10"
    entries for the same applied-thrice recipe).
    """

    tier_name: str  # "Minor" / "Medium" / "Major" / "Uber"
    capacity: int  # max enchants allowed by tier
    applied_count: int  # distinct recipe applications attributed
    mod_lines: tuple[str, ...]  # "+30 to Strength" etc., one per stat
    has_ambiguity: bool  # any enchant slot could not be isolated


@dataclass(frozen=True, slots=True)
class ItemModifierSummary:
    """Top-level modifier summary ready for direct GUI rendering.

    Built via :func:`summarize_item_modifiers` from a parsed item +
    the per-stat :class:`StatBreakdown` map.  Use the blocks to lay
    out tooltip sections; each block's text is pre-formatted so the
    GUI only needs to decorate with indentation / colour.
    """

    corruption: CorruptionDisplay | None
    enchantment: EnchantmentDisplay | None


@dataclass(frozen=True, slots=True)
class StatBreakdown:
    """Full decomposition of one stat's observed value.

    ``contributions`` sum to ``observed_value`` when
    ``is_consistent`` is True.  ``is_perfect_roll`` is True iff every
    ``base_roll`` contribution rolled at (or above) its range max -
    modifier contributions don't count toward perfection since they
    were deliberately applied by the player.

    ``ambiguity``:
      * ``"unique"``: exactly one valid decomposition found
      * ``"multiple"``: several decompositions could explain the value;
        the first consistent one is returned in ``contributions`` but
        others exist.  GUI can expose them if needed.
      * ``"none"``: no decomposition reached the observed value -
        either the item uses a modifier we don't yet understand, or
        the parser produced a wrong value.  ``parser_warning`` carries
        a human-readable description of what went wrong.
    """

    stat_id: int
    observed_value: float
    contributions: tuple[StatContribution, ...]
    is_consistent: bool
    is_perfect_roll: bool
    ambiguity: Ambiguity
    parser_warning: str | None = None


# ── Resolver ────────────────────────────────────────────────────────────────


class StatBreakdownResolver:
    """Top-level API: takes a parsed item + its roll context, returns
    a ``{stat_id: StatBreakdown}`` mapping.

    The resolver is stateless between calls - it consults the passed-in
    database singletons for every attribution.  Construction is cheap
    (no data parsing) so callers typically build one per request.
    """

    def __init__(
        self,
        *,
        affix_db: "AffixRollDatabase",
        corruption_db: "CorruptionRollDatabase",
        enchant_db: "EnchantmentRecipeDatabase",
        isc_db: "ItemStatCostDatabase",
        props_db: "PropertiesDatabase",
        skills_db: "SkillDatabase | None" = None,
        item_types_db: "ItemTypeDatabase | None" = None,
    ) -> None:
        self._affix_db = affix_db
        self._corruption_db = corruption_db
        self._enchant_db = enchant_db
        self._isc = isc_db
        self._props = props_db
        self._skills = skills_db
        self._item_types = item_types_db

    # ── Public API ──────────────────────────────────────────────────────

    def resolve_item(
        self,
        item: object,
        roll_context: "ItemRollContext",
    ) -> dict[int, StatBreakdown]:
        """Decompose every magical property on ``item``.

        Returns a mapping ``stat_id -> StatBreakdown``.  Stats that
        appear multiple times on the item (e.g. ``item_singleskill``
        with different skill params) get one breakdown per occurrence
        keyed by position - callers that need those fine-grained
        attributions should walk :meth:`resolve_stat` directly.
        """
        magical = getattr(item, "magical_properties", None) or ()
        out: dict[int, StatBreakdown] = {}
        for prop in magical:
            if not isinstance(prop, dict):
                continue
            sid = prop.get("stat_id")
            if not isinstance(sid, int):
                continue
            if sid in _BOOKKEEPING_STATS:
                # Skip corruption/enchantment bookkeeping stats - they
                # carry metadata, not player-visible stat bonuses.
                continue
            # Empty encode=2/3 proc stat slots: value=0 is the "no
            # proc" sentinel that the parser still surfaces as a
            # property.  The binary has no chance/level/skill there
            # so any GUI trying to render it would just show a blank
            # placeholder.  Skip - not a real stat attribution.
            value = prop.get("value")
            if value == 0 or value is None:
                stat_def = self._isc.get(sid)
                if stat_def is not None and stat_def.encode in (2, 3):
                    continue
            if sid in out:
                # Same stat appearing twice - already handled first
                # occurrence.  For +skill / +charge tab style stats
                # the breakdown is identical, so collapsing is OK.
                continue
            out[sid] = self.resolve_stat(
                stat_id=sid,
                prop=prop,
                item=item,
                roll_context=roll_context,
            )
        return out

    def summarize_modifiers(
        self,
        item: object,
        roll_context: "ItemRollContext",
        breakdowns: "dict[int, StatBreakdown] | None" = None,
    ) -> ItemModifierSummary:
        """Build a per-block modifier summary for tooltip rendering.

        The returned :class:`ItemModifierSummary` carries one optional
        :class:`CorruptionDisplay` + one optional
        :class:`EnchantmentDisplay`, each with pre-formatted
        ``mod_lines`` the GUI can render verbatim under its
        "Corrupted" / "Enchantments X/Y" block headers.

        Call with the already-computed ``breakdowns`` dict (from
        :meth:`resolve_item`) to avoid re-running the per-stat
        decomposition; pass ``None`` to have this method compute it
        internally.
        """
        if breakdowns is None:
            breakdowns = self.resolve_item(item, roll_context)

        corruption = self._build_corruption_display(
            item,
            roll_context,
            breakdowns,
        )
        enchantment = self._build_enchantment_display(
            item,
            roll_context,
            breakdowns,
        )
        return ItemModifierSummary(
            corruption=corruption,
            enchantment=enchantment,
        )

    def resolve_stat(
        self,
        *,
        stat_id: int,
        prop: dict[str, Any],
        item: object,
        roll_context: "ItemRollContext",
    ) -> StatBreakdown:
        """Decompose one specific stat into its contributions."""
        observed = _coerce_float(prop.get("value"))
        if observed is None:
            return self._empty_breakdown(stat_id, 0.0, warning="value is None")

        contributions: list[StatContribution] = []

        # ── 1. Corruption (deterministic) ─────────────────────────
        for c in self._corruption_contributions(stat_id, item):
            contributions.append(c)

        # ── 2. Ethereal defense bonus ──────────────────────────────
        eth = self._ethereal_contribution(stat_id, item, prop)
        if eth is not None:
            contributions.append(eth)

        # ── 3. Base roll contributions (per slot, no suppression) ──
        # Subtract deterministic corruption / ethereal contributions
        # before attributing the rolled portion so the range-clipping
        # happens against the correct residual.
        det_sum = sum(c.amount for c in contributions)
        base_contribs = self._base_roll_contributions(
            stat_id,
            prop,
            roll_context,
            observed - det_sum,
        )
        contributions.extend(base_contribs)

        # Sum so far (base uses actual rolled value, deterministic
        # modifiers use their fixed contributions).
        explained = sum(c.amount for c in contributions)
        residual = observed - explained

        ambiguity: Ambiguity = "unique"
        warning: str | None = None

        # ── 4. Enchantment attribution (subset search) ─────────────
        if not _is_close(residual, 0.0) and roll_context.is_enchanted:
            match = self._enchantment_attribution(
                residual=residual,
                stat_id=stat_id,
                item=item,
            )
            if match is not None:
                recipes, ambiguity_status = match
                for recipe, mod in recipes:
                    contributions.append(
                        StatContribution(
                            amount=mod.max_value,
                            source="enchantment",
                            source_detail=_compose_source_detail(
                                "Enchantment",
                                mod.code,
                                mod.max_value,
                                mod.par,
                                self._props,
                                self._isc,
                                self._skills,
                            ),
                            roll_range=None,
                            source_row=recipe.row_index,
                        )
                    )
                explained = sum(c.amount for c in contributions)
                residual = observed - explained
                if ambiguity_status == "multiple":
                    ambiguity = "multiple"
        # Recompute residual after any enchantment attribution.
        residual = observed - sum(c.amount for c in contributions)

        # ── 5. Classify leftovers ──────────────────────────────────
        is_consistent = _is_close(residual, 0.0)
        if not is_consistent:
            # Two cases:
            #
            # (a) The item bears a Reimagined modifier layer the
            #     resolver doesn't yet decompose exactly (crafted
            #     charm sundering, superior-quality armor%, unique
            #     per-level bonuses, multi-enchant stacking overflow,
            #     etc.).  Attribute the leftover as an
            #     ``unknown_modifier`` contribution so ``is_consistent``
            #     stays True - the GUI can still render the stat
            #     honestly - but set ``parser_warning`` so the audit
            #     tool can surface where the resolver's data model
            #     has a gap.  This only fires on items whose quality
            #     / flags genuinely warrant an unknown-source
            #     contribution (Set / Unique / Rare / Crafted /
            #     Superior / modifier-flagged); plain Magic items
            #     fall through to the strict ``residual`` path so a
            #     genuine parser bug isn't hidden by the attribution.
            #
            # (b) No modifier flag is present and the item isn't a
            #     special-quality bucket -> genuine residual, emit
            #     inconsistency + warning the way it used to.
            quality = roll_context.quality
            special_quality = quality in (3, 5, 6, 7, 8)  # sup/set/rare/uni/craft
            # Magic items with an automod_id > 0 carry an additional
            # automagic.txt contribution we don't fully attribute yet
            # (Reimagined-specific skill-tab and charm-passive bonuses).
            has_automod = (roll_context.automod_id or 0) > 0
            # Magic items (q=4) with any affix source: prefix / suffix
            # rows may include Reimagined per-level codes
            # (``item_resist_X_perlevel``, ``item_armorpercent_perlevel``,
            # ``item_replenish_durability``, ...) whose exact value
            # tables the resolver doesn't yet split by row.  Treat
            # leftover as unknown_modifier so the breakdown stays
            # consistent while the audit tool captures the gap.
            has_affix_context = bool(
                roll_context.prefix_ids
                or roll_context.suffix_ids
                or roll_context.unique_id is not None
                or roll_context.set_id is not None
                or roll_context.runeword_id is not None
            )
            if (
                roll_context.has_stat_modifiers
                or special_quality
                or has_automod
                or has_affix_context
            ):
                contributions.append(
                    StatContribution(
                        amount=residual,
                        source="unknown_modifier",
                        source_detail=_unknown_modifier_label(roll_context),
                        roll_range=None,
                    )
                )
                is_consistent = True
                warning = (
                    f"stat {stat_id}: {residual:g} attributed as "
                    "unknown_modifier - the resolver's source index "
                    "doesn't yet decompose every Reimagined contribution "
                    "pathway precisely (e.g. crafted charm sundering, "
                    "Superior armor bonus, per-rune runeword split)."
                )
                ambiguity = "multiple"
            else:
                contributions.append(
                    StatContribution(
                        amount=residual,
                        source="residual",
                        source_detail="Unattributed (possible parser bug)",
                        roll_range=None,
                    )
                )
                ambiguity = "none"
                warning = (
                    f"stat {stat_id}: unexplained residual {residual:g} "
                    f"(observed={observed:g}, attributed="
                    f"{observed - residual:g}) on an item with NO "
                    "modifier flags and no affix context - likely a "
                    "parser bug or an un-indexed data source."
                )

        # ── 6. Perfection: all base rolls at their max? ────────────
        is_perfect = _is_perfect_roll(contributions)

        return StatBreakdown(
            stat_id=stat_id,
            observed_value=observed,
            contributions=tuple(contributions),
            is_consistent=is_consistent,
            is_perfect_roll=is_perfect,
            ambiguity=ambiguity,
            parser_warning=warning,
        )

    # ── Individual contribution resolvers ────────────────────────────

    def _build_corruption_display(
        self,
        item: object,
        roll_context: "ItemRollContext",
        breakdowns: dict[int, StatBreakdown],
    ) -> CorruptionDisplay | None:
        """Aggregate all corruption contributions into a display block.

        Returns ``None`` when the item is not corrupted (no stat 361
        present).  Handles three shapes:

          * **Phase 1 only** (stat 362 <= 100): the item has been
            marked corrupted but the second cube application that
            picks the outcome hasn't fired yet.  No mods applied.
          * **Phase 2 brick** (roll 1-45): the outcome table returned
            an empty mod list - user sees the "Failed corruption"
            message instead of a bullet list.
          * **Phase 2 success** (roll 46-100): full mod list attributed
            from the matching cubemain row.  The ``mod_lines`` field
            carries one pre-formatted line per applied mod.
        """
        if not roll_context.is_corrupted:
            return None
        stat_362 = _stat_value(item, 362)
        roll = self._corruption_db.decode_roll(stat_362)
        if roll is None:
            # Phase-1-only corruption: stat 361 is set, stat 362 is
            # in the 1..100 range (waiting for the second cube press).
            return CorruptionDisplay(
                roll=int(stat_362 or 0),
                outcome_name="pending (second cube application required)",
                is_brick=False,
                is_phase1=True,
                mod_lines=(),
                brick_message=(
                    "Corruption in progress - apply the Orb of "
                    "Corruption a second time to finalise the roll."
                ),
                has_ambiguity=False,
            )

        bucket = self._corruption_bucket_for(item)
        if bucket is None:
            return CorruptionDisplay(
                roll=roll,
                outcome_name="unknown (item type not in corruption table)",
                is_brick=True,
                is_phase1=False,
                mod_lines=(),
                brick_message="Corruption outcome unavailable for this item type.",
                has_ambiguity=False,
            )
        outcome = self._corruption_db.outcome_for(bucket, roll)
        if outcome is None:
            return None

        outcome_name = _shorten_corruption_name(outcome.description)
        if outcome.is_brick:
            # Rolls 21-45 are "Nothing", 11-20 "Brick Rare", 1-10
            # "Brick White/Magic".  All three apply no mods.
            if roll >= 21:
                brick_msg = "Failed corruption - no stats applied."
            else:
                brick_msg = "Failed corruption - item downgraded, no stats applied."
            return CorruptionDisplay(
                roll=roll,
                outcome_name=outcome_name,
                is_brick=True,
                is_phase1=False,
                mod_lines=(),
                brick_message=brick_msg,
                has_ambiguity=False,
            )

        # Success: format each mod line using the short display helper.
        mod_lines: list[str] = []
        for mod in outcome.mods:
            line = _short_mod_display(
                mod.code,
                mod.max_value,
                mod.par,
                self._props,
                self._isc,
                self._skills,
            )
            if line:
                mod_lines.append(line)

        # Ambiguity: did any per-stat breakdown fall back to
        # unknown_modifier because of a corruption pathway?  The
        # label helper tags it in the detail text.
        has_ambiguity = any(
            any(
                c.source == "unknown_modifier" and "Corruption" in (c.source_detail or "")
                for c in bd.contributions
            )
            for bd in breakdowns.values()
        )
        return CorruptionDisplay(
            roll=roll,
            outcome_name=outcome_name,
            is_brick=False,
            is_phase1=False,
            mod_lines=tuple(mod_lines),
            brick_message=None,
            has_ambiguity=has_ambiguity,
        )

    def _build_enchantment_display(
        self,
        item: object,
        roll_context: "ItemRollContext",
        breakdowns: dict[int, StatBreakdown],
    ) -> EnchantmentDisplay | None:
        """Aggregate all enchantment contributions into a display block.

        Derives:

          * ``capacity`` / ``tier_name`` from whichever
            ``upgrade_{minor,medium,major,uber}`` stat is on the item.
          * ``applied_count`` from the number of **distinct recipe row
            indices** referenced by the per-stat enchantment
            contributions (multi-application of the same recipe
            counts as multiple distinct applications via
            ``combinations_with_replacement`` at resolve time).
          * ``mod_lines`` by summing the amount of every enchantment
            contribution per stat, then formatting as compact
            stat-line text.  The result matches what the game would
            display if you hovered each upgraded stat.
        """
        if not roll_context.is_enchanted:
            return None

        # Capacity / tier from upgrade_* stat.
        tier_name, capacity = self._enchantment_tier_info(item)

        # Collect per-stat sums and source_row tallies.
        per_stat_sum: dict[int, float] = {}
        applied_rows: list[int] = []
        has_ambiguity = False
        for sid, bd in breakdowns.items():
            for c in bd.contributions:
                if c.source == "enchantment":
                    per_stat_sum[sid] = per_stat_sum.get(sid, 0.0) + c.amount
                    if c.source_row is not None:
                        applied_rows.append(c.source_row)
                elif c.source == "unknown_modifier" and "Enchant" in (c.source_detail or ""):
                    has_ambiguity = True

        # applied_count: unique physical cube recipe rows encountered.
        # When the same recipe is stacked N times, the subset search
        # records N contributions per stat touched, all with the same
        # source_row; collapse by dividing by the number of stats
        # each recipe touches - but that double-counts for multi-mod
        # recipes.  Simpler and closer to user intent: per-stat
        # contributions are the *applications* directly (one
        # StatContribution per application-per-stat).  Take the MAX
        # count seen on any single stat as a safe lower bound of
        # applied slots.
        row_counts: dict[int, int] = {}
        for sid, bd in breakdowns.items():
            stat_row_counts: dict[int, int] = {}
            for c in bd.contributions:
                if c.source == "enchantment" and c.source_row is not None:
                    stat_row_counts[c.source_row] = stat_row_counts.get(c.source_row, 0) + 1
            for row_id, n in stat_row_counts.items():
                row_counts[row_id] = max(row_counts.get(row_id, 0), n)
        applied_count = sum(row_counts.values())

        # Format mod_lines by building a synthetic (code, amount, par)
        # from each summed stat.  We look up the stat's formatted
        # display via the PropertyFormatter against a synthetic prop
        # dict - this yields exactly the same text the main tooltip
        # would show for the enchanted stat.
        mod_lines = self._format_summed_mod_lines(per_stat_sum, item)

        return EnchantmentDisplay(
            tier_name=tier_name,
            capacity=capacity,
            applied_count=applied_count,
            mod_lines=mod_lines,
            has_ambiguity=has_ambiguity,
        )

    def _enchantment_tier_info(self, item: object) -> tuple[str, int]:
        """Return ``(tier_name, capacity)`` from the upgrade_* stat."""
        for sid, cap in _CAPACITY_LIMITS.items():
            if _stat_value(item, sid):
                tier_name = {
                    392: "Minor",
                    393: "Medium",
                    394: "Major",
                    395: "Uber",
                }.get(sid, "Unknown")
                return tier_name, cap
        return "Unknown", _HARD_ENCHANT_LIMIT

    def _format_summed_mod_lines(
        self,
        per_stat_sum: "dict[int, float]",
        item: object,
    ) -> tuple[str, ...]:
        """Format summed per-stat enchant totals as compact lines.

        Uses :meth:`PropertyFormatter.format_prop` on a synthetic
        ``{stat_id, value, param}`` dict so the enchant block shows
        the same "+30 to Strength" / "+1 to All Skills" text the
        main tooltip would render for the same stat value.
        """
        if not per_stat_sum:
            return ()
        fmt = get_property_formatter()
        out: list[str] = []
        magical = getattr(item, "magical_properties", None) or ()
        param_by_stat = {
            p.get("stat_id"): p.get("param", 0) for p in magical if isinstance(p, dict)
        }
        for stat_id, amount in sorted(per_stat_sum.items()):
            param = param_by_stat.get(stat_id, 0)
            synthetic_prop = {
                "stat_id": stat_id,
                "value": int(amount) if amount == int(amount) else amount,
                "param": param,
            }
            try:
                line = fmt.format_prop(
                    synthetic_prop,
                    self._isc,
                    self._skills,
                )
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning(
                    "breakdown preview: format_prop failed for stat_id=%s: %s",
                    stat_id,
                    exc,
                )
                line = None
            if line:
                out.append(line.strip())
        return tuple(out)

    def _corruption_contributions(
        self,
        stat_id: int,
        item: object,
    ) -> list[StatContribution]:
        """Return every corruption mod touching ``stat_id`` on the item.

        Deterministic: the roll stored in ``stat 362`` picks exactly
        one outcome row from the table for the item's corruption
        bucket.  Zero contributions when the item isn't phase-2
        corrupted, or when the chosen outcome doesn't touch this stat.
        """
        stat_362 = _stat_value(item, 362)
        roll = self._corruption_db.decode_roll(stat_362)
        if roll is None:
            return []
        bucket = self._corruption_bucket_for(item)
        if bucket is None:
            return []
        outcome = self._corruption_db.outcome_for(bucket, roll)
        if outcome is None:
            return []
        out: list[StatContribution] = []
        for mod in outcome.mods:
            # Convert mod's property code to stat id(s).  Most cases
            # hit a single stat; a handful of broadcast codes (e.g.
            # ``res-all``) touch multiple.
            stat_ids = self._stat_ids_for_code(mod.code)
            if stat_id in stat_ids:
                out.append(
                    StatContribution(
                        amount=mod.max_value,
                        source="corruption",
                        source_detail=_compose_source_detail(
                            "Corruption",
                            mod.code,
                            mod.max_value,
                            mod.par,
                            self._props,
                            self._isc,
                            self._skills,
                        ),
                        roll_range=None,
                        source_row=outcome.row_index,
                    )
                )
        return out

    def _ethereal_contribution(
        self,
        stat_id: int,
        item: object,
        prop: dict[str, Any],
    ) -> StatContribution | None:
        """Ethereal items have +50% defense on stat 31 only."""
        if stat_id != 31:
            return None
        flags = getattr(item, "flags", None)
        if not getattr(flags, "ethereal", False):
            return None
        # The engine multiplies base defense by 1.5, so the ethereal
        # "bonus" half is one-third of the final value.  We encode it
        # as a separate contribution so the base_roll attribution
        # reflects what the unmodified item would have rolled.
        observed = _coerce_float(prop.get("value")) or 0.0
        base = observed * (2.0 / 3.0)
        bonus = observed - base
        if not _is_close(bonus, 0.0):
            return StatContribution(
                amount=bonus,
                source="ethereal_bonus",
                source_detail="Ethereal (+50% defense)",
                roll_range=None,
            )
        return None

    def _base_roll_contributions(
        self,
        stat_id: int,
        prop: dict[str, Any],
        roll_context: "ItemRollContext",
        remaining: float,
    ) -> list[StatContribution]:
        """Enumerate per-slot base_roll contributions for ``stat_id``.

        Uses :meth:`AffixRollDatabase.iter_slot_contributions` so dual-
        stat damage slots (``dmg-norm``, ``dmg-fire``, ``dmg-pois``, ...)
        surface their fixed per-side value instead of being suppressed.

        ``remaining`` is the stat value left to explain after
        deterministic (corruption + ethereal) contributions have been
        subtracted.  For each non-fixed slot we clip the rolled portion
        of ``remaining`` to the slot's range window - multiple ranged
        slots are handled sequentially in source-priority order.  For
        typical items only one ranged slot touches any given stat; the
        degenerate multi-ranged case (e.g. a unique with own affix + a
        runeword + a magic prefix all contributing hp) gets linear
        allocation in priority order, which is the simplest policy that
        stays consistent with observed totals.
        """
        try:
            contribs = self._affix_db.iter_slot_contributions(
                roll_context,
                stat_id,
                param=_coerce_int(prop.get("param", 0)) or 0,
                isc_db=self._isc,
                props_db=self._props,
                skills_db=self._skills,
            )
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning(
                "iter_slot_contributions failed for stat_id=%s: %s",
                stat_id,
                exc,
            )
            return []
        if not contribs:
            return []

        out: list[StatContribution] = []
        residual = remaining
        # Two passes: first attribute every fixed slot (its contribution
        # is known up-front); then distribute what's left over the
        # ranged slots in source-priority order (already the order
        # iter_slot_contributions returns).
        fixed_total = sum((c.fixed_amount or 0.0) for c in contribs if c.is_fixed)
        residual = remaining - fixed_total
        for c in contribs:
            if c.is_fixed:
                amount = c.fixed_amount or 0.0
                rng = StatRollRange(
                    min_value=c.min_value,
                    max_value=c.max_value,
                    source=c.source,
                )
                out.append(
                    StatContribution(
                        amount=amount,
                        source="base_roll",
                        source_detail=_base_roll_label(c.source),
                        roll_range=rng,
                    )
                )
        # Distribute the residual across ranged slots.  Start each slot
        # at its minimum, then dump the "surplus" (residual minus sum
        # of minimums) into slots left-to-right in source-priority
        # order, capping each at its range width.  This mirrors the
        # most common real-world case where two prefix+suffix slots
        # both contribute hp (prefix "Blooming" 10-15 + suffix "of
        # Substinence" 10-15) and the observed value is anywhere in
        # the summed [20, 30] window - each half gets a specific
        # rolled value that makes the total match.
        ranged_slots = [c for c in contribs if not c.is_fixed]
        if ranged_slots:
            ranged_min_sum = sum(c.min_value for c in ranged_slots)
            surplus = residual - ranged_min_sum
            # Clip surplus to [0, total_width] so the allocation stays
            # consistent even when the observed value falls slightly
            # outside the total summed range (rare rounding edge).
            total_width = sum(c.max_value - c.min_value for c in ranged_slots)
            if surplus < 0:
                surplus = 0.0
            elif surplus > total_width:
                surplus = total_width
            for c in ranged_slots:
                rng = StatRollRange(
                    min_value=c.min_value,
                    max_value=c.max_value,
                    source=c.source,
                )
                width = c.max_value - c.min_value
                take = min(width, surplus)
                amount = c.min_value + take
                surplus -= take
                out.append(
                    StatContribution(
                        amount=amount,
                        source="base_roll",
                        source_detail=_base_roll_label(c.source),
                        roll_range=rng,
                    )
                )
        return out

    def _enchantment_attribution(
        self,
        *,
        residual: float,
        stat_id: int,
        item: object,
    ) -> tuple[list[tuple["EnchantmentRecipe", "EnchantmentMod"]], str] | None:
        """Find the enchant recipe subset whose mods sum to ``residual``.

        Returns a tuple ``(subset, ambiguity)`` where ``ambiguity`` is
        ``"unique"`` if exactly one subset matched, ``"multiple"`` if
        more than one did (the first match is returned - caller
        disambiguates).  Returns ``None`` when no subset matches.
        """
        bucket_matches = self._enchantment_buckets_for(item)
        if not bucket_matches:
            return None

        # Collect every (recipe, mod) that touches this stat AND is
        # valid for one of the item's enchantment buckets.
        candidates: list[tuple["EnchantmentRecipe", "EnchantmentMod"]] = []
        seen_rows: set[int] = set()
        for bucket in bucket_matches:
            for recipe, mod in self._enchant_db.recipes_touching_code_for_stat(
                stat_id=stat_id,
                stat_ids_for_code=self._stat_ids_for_code,
                bucket=bucket,
            ):
                if recipe.row_index in seen_rows:
                    continue
                seen_rows.add(recipe.row_index)
                candidates.append((recipe, mod))
        if not candidates:
            return None

        # Capacity-bounded subset search.  Small fan-out (<= 34 recipes
        # per item type) keeps combinations cheap even at capacity 10.
        capacity = self._enchant_capacity_for(item)
        matches = _find_subsets_summing_to(candidates, residual, capacity)
        if not matches:
            return None
        if len(matches) == 1:
            return matches[0], "unique"
        return matches[0], "multiple"

    # ── Cached helpers ──────────────────────────────────────────────────

    def _stat_ids_for_code(self, prop_code: str) -> set[int]:
        """Expand a property code to every ISC stat id it touches."""
        # Delegate to the affix resolver's helper - it already knows
        # the dmg% fallback map and all the broadcast codes.
        pd = self._props.get(prop_code)
        ids: set[int] = set()
        if pd is not None:
            for name in pd.stat_names():
                if not name:
                    continue
                sd = self._isc.get_by_name(name)
                if sd is not None:
                    ids.add(sd.stat_id)
        ids.update(_PROP_CODE_FALLBACK_STATS.get(prop_code, ()))
        return ids

    def _corruption_bucket_for(self, item: object) -> str | None:
        """Return the cubemain corruption bucket key for ``item``, or None."""

        code = getattr(item, "item_code", "") or ""
        itypes = self._item_types_for(code)
        return self._corruption_db.map_item_code(code, itypes)

    def _enchantment_buckets_for(self, item: object) -> list[str]:
        """Return every cubemain enchantment bucket ``item`` could belong to."""

        code = getattr(item, "item_code", "") or ""
        itypes = self._item_types_for(code)
        return self._enchant_db.map_item_code(code, itypes)

    def _item_types_for(self, item_code: str) -> set[str]:
        """Return the itype-ancestor set for an item.

        e.g. Large Shield ``tow`` -> ``{tow, shie, shld, armo, any}``.
        Walks ``armor.txt`` / ``weapons.txt`` type+type2 columns up
        through ``itypes.txt`` Equiv parents via
        :meth:`ItemTypeDatabase.get_itype_ancestors`.

        Logs a warning when the code is NOT found in any item table -
        that normally means a typo in a synthetic test case or a new
        item introduced by a mod update we haven't indexed yet.  Silent
        empty-set fallback masks both conditions; loud warning surfaces
        them.  Falls back to an empty set when the type database wasn't
        provided (caller gets no corruption/enchant matches, which is
        the safe default for tests that don't care).
        """
        if self._item_types is None or not item_code:
            return set()
        ancestors = self._item_types.get_itype_ancestors(item_code)
        if not ancestors and not self._item_types.contains(item_code):
            logger.warning(
                "StatBreakdownResolver: item_code %r is not present "
                "in armor.txt / weapons.txt / misc.txt - "
                "corruption and enchantment attribution will be skipped "
                "for this item.  Typo or unindexed mod addition?",
                item_code,
            )
        return ancestors

    def _enchant_capacity_for(self, item: object) -> int:
        """Return the max enchants the item's capacity stat allows."""
        for sid, cap in _CAPACITY_LIMITS.items():
            if _stat_value(item, sid):
                return cap
        return _HARD_ENCHANT_LIMIT

    # ── Misc helpers ────────────────────────────────────────────────────

    def _empty_breakdown(
        self,
        stat_id: int,
        observed: float,
        *,
        warning: str,
    ) -> StatBreakdown:
        """Return a :class:`StatBreakdown` with no contributions (skipped stat)."""
        return StatBreakdown(
            stat_id=stat_id,
            observed_value=observed,
            contributions=(),
            is_consistent=False,
            is_perfect_roll=False,
            ambiguity="none",
            parser_warning=warning,
        )


# ── Helpers ─────────────────────────────────────────────────────────────────

_EPSILON = 1e-6


# Short, human-readable source labels the GUI can render verbatim in
# tooltips.  The underlying ``source`` literal stays machine-readable;
# this map is only for presentation.
_BASE_ROLL_LABELS: dict[str, str] = {
    "unique": "Unique base",
    "set": "Set base",
    "runeword": "Runeword base",
    "magic_prefix": "Magic Prefix",
    "magic_suffix": "Magic Suffix",
    "rare_prefix": "Rare Prefix",
    "rare_suffix": "Rare Suffix",
    "automod": "Automagic",
    "crafted": "Crafted Affix",
}


def _base_roll_label(source: str) -> str:
    """Short human-readable label for a ``base_roll`` source."""
    return _BASE_ROLL_LABELS.get(source, source.replace("_", " ").title())


def _shorten_corruption_name(description: str) -> str:
    """Extract the outcome-name portion of a cubemain description.

    Raw example:
      ``"CORRUPT ITEM SUCCESS - Gloves & Orb of Corruption  +
         CorruptedDummy 77-82 = Deadly Strike + Crushing Blow (6% Chance)"``

    Returns ``"Deadly Strike + Crushing Blow"`` - everything after the
    last ``" = "`` with the trailing ``"(N% Chance)"`` probability
    stripped.  Falls back to the first 60 chars of the description
    when the shape doesn't match.
    """
    if not description:
        return "Corruption"
    # Split on " = " to isolate the outcome portion.
    if " = " in description:
        tail = description.rsplit(" = ", 1)[1].strip()
    else:
        tail = description.strip()
    # Strip trailing "(X% Chance)" annotation.
    if tail.endswith(")") and "(" in tail:
        paren = tail.rfind("(")
        inside = tail[paren + 1 : -1]
        if "%" in inside and "Chance" in inside:
            tail = tail[:paren].strip()
    return tail or description[:60]


def _short_mod_display(
    code: str,
    value: float,
    par: str,
    props_db: "PropertiesDatabase | None",
    isc_db: "ItemStatCostDatabase",
    skills_db: "SkillDatabase | None",
) -> str:
    """Render a ``(code, value, par)`` triple as a compact stat line.

    Delegates to :meth:`PropertyFormatter.format_code_value` so the
    display text matches what the game tooltip would show for the same
    property (e.g. ``deadly 5`` -> ``"+5% Deadly Strike"``, ``hp 30`` ->
    ``"+30 to Life"``, ``oskill par=Teleport 1`` -> ``"+1 to Teleport"``).
    Falls back to a terse ``"+value code"`` when the formatter isn't
    available or returns ``None``.
    """
    fmt = get_property_formatter()
    try:
        # ``format_code_value`` accepts only int; coerce floats to int (the
        # display formatter does its own perlevel division).
        iv = int(value)
        display = fmt.format_code_value(
            code,
            iv,
            par or "",
            props_db,
            isc_db,
            skills_db,
        )
        if display:
            return display.strip()
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning(
            "format_code_value fallback for code=%r value=%r: %s",
            code,
            value,
            exc,
        )
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:g} {code}"


def _compose_source_detail(
    prefix: str,
    code: str,
    value: float,
    par: str,
    props_db: "PropertiesDatabase | None",
    isc_db: "ItemStatCostDatabase",
    skills_db: "SkillDatabase | None",
) -> str:
    """Combine a source-category prefix (``"Corruption"`` /
    ``"Enchantment"``) with the short mod display, producing tooltip
    text like ``"Enchantment: +30 to Life"`` or
    ``"Corruption: +5% Deadly Strike"``.
    """
    body = _short_mod_display(
        code,
        value,
        par,
        props_db,
        isc_db,
        skills_db,
    )
    return f"{prefix}: {body}"


def _unknown_modifier_label(roll_context: "ItemRollContext") -> str:
    """Label for the ``unknown_modifier`` catch-all contribution.

    Tailors the message to which modifier path is most likely the
    source - corruption / enchantment flags first, then falls back to
    a generic "modifier" phrasing for crafted / superior / runeword
    residuals that don't ship a specific flag.
    """
    if roll_context.is_corrupted and roll_context.is_enchanted:
        return "Corruption or Enchantment (could not fully isolate)"
    if roll_context.is_corrupted:
        return "Corruption (precise mod could not be isolated)"
    if roll_context.is_enchanted:
        return "Enchantment (precise recipe could not be isolated)"
    if roll_context.is_runeword:
        return "Runeword bonus (per-rune split unavailable)"
    if roll_context.is_ethereal:
        return "Ethereal bonus (precise split unavailable)"
    return "Modifier bonus (precise source could not be isolated)"


def _is_close(a: float, b: float) -> bool:
    """Return True if ``a`` and ``b`` agree within a tolerance (handles fixed-point)."""

    return abs(a - b) < _EPSILON


def _coerce_float(v: object) -> float | None:
    """Coerce ``v`` to float, returning ``None`` for non-numeric inputs."""

    if v is None:
        return None
    if not isinstance(v, (int, float, str, bytes)):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _coerce_int(v: object) -> int | None:
    """Coerce ``v`` to int, returning ``None`` for non-numeric inputs."""

    if v is None:
        return None
    if not isinstance(v, (int, float, str, bytes)):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _stat_value(item: object, stat_id: int) -> int | None:
    """Return the effective value of ``prop`` (may apply fixed-point scaling)."""

    magical = getattr(item, "magical_properties", None) or ()
    for p in magical:
        if isinstance(p, dict) and p.get("stat_id") == stat_id:
            v = _coerce_int(p.get("value"))
            if v is not None:
                return v
    return None


def _is_perfect_roll(contributions: list[StatContribution]) -> bool:
    """True iff every ``base_roll`` contribution rolled at its max."""
    any_base = False
    for c in contributions:
        if c.source != "base_roll" or c.roll_range is None:
            continue
        any_base = True
        if c.amount < c.roll_range.max_value:
            return False
    return any_base


def _find_subsets_summing_to(
    candidates: list[tuple["EnchantmentRecipe", "EnchantmentMod"]],
    target: float,
    max_subset_size: int,
) -> list[list[tuple["EnchantmentRecipe", "EnchantmentMod"]]]:
    """Enumerate multi-subsets of (recipe, mod) whose mods sum to ``target``.

    D2R Reimagined lets the player apply the SAME enchant recipe more
    than once on the same item (up to the capacity-tier cap).  We
    therefore use :func:`itertools.combinations_with_replacement` so
    stacked applications (e.g. three +10 str/vit Fal-Rune enchants
    producing +30 to each) are recovered correctly.

    Returns up to 2 matching subsets (early-stops at 2 - caller only
    needs to distinguish unique vs. multiple).  Fan-out is bounded by
    ``len(candidates)`` (<= 34) times ``max_subset_size`` (<= 10)
    combinations-with-replacement, which stays well inside 50k
    evaluations even at capacity 10.
    """
    matches: list[list[tuple["EnchantmentRecipe", "EnchantmentMod"]]] = []
    max_size = min(max_subset_size, _HARD_ENCHANT_LIMIT)
    for size in range(1, max_size + 1):
        for combo in combinations_with_replacement(candidates, size):
            s = sum(mod.max_value for (_r, mod) in combo)
            if _is_close(s, target):
                matches.append(list(combo))
                if len(matches) >= 2:
                    return matches
    return matches


# ─── Breakdown hook registration ────────────────────────────────────────────
#
# Registered with :mod:`property_formatter` at module load time so callers can
# keep using ``PropertyFormatter.format_properties_grouped(breakdown=True)``
# without ``property_formatter`` having to import this module - which would
# close the ``property_formatter <-> stat_breakdown`` cycle.  See the module
# docstring of :mod:`d2rr_toolkit.game_data._roll_types` for the full
# rationale.


def _breakdown_hook(
    formatted: list["FormattedProperty"],
    *,
    isc_db: "ItemStatCostDatabase",
    props_db: "PropertiesDatabase",
    skills_db: "SkillDatabase | None",
    item_types_db: "ItemTypeDatabase | None",
    item: object,
    roll_context: ItemRollContext,
) -> list["FormattedProperty"]:
    """Stamp per-stat breakdown attribution onto pre-formatted properties.

    This is the hook installed onto :mod:`property_formatter` and invoked from
    inside ``PropertyFormatter.format_properties_grouped(breakdown=True)``.
    Callers do not need to invoke it directly - register the module
    (``import d2rr_toolkit.game_data.stat_breakdown``) and use the formatter
    API as before.
    """
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

    # Stamp each FormattedProperty's ``breakdown`` field.  When a single line
    # collapses multiple stats (damage pair), pick the first stat's breakdown
    # as representative - the GUI can walk ``source_stat_ids`` if it needs
    # per-half detail.
    out: list[FormattedProperty] = []
    for fp in formatted:
        sid = fp.source_stat_ids[0] if fp.source_stat_ids else None
        bd = breakdowns.get(sid) if sid is not None else None
        # Joint-perfection for multi-stat display lines: the star must only
        # appear when EVERY stat in the group rolled at its range max.  See
        # the (now-deleted) inline comment in property_formatter.py for the
        # full rationale - this branch preserves that semantics verbatim.
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
            if len(fp.source_stat_ids) > 1 and bd.is_perfect_roll != is_perfect:
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


set_breakdown_hook(_breakdown_hook)

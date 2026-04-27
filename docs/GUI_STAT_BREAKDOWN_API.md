# GUI Integration Guide - Stat Breakdown Resolver

**Audience:** GUI / tooltip renderer developers consuming the toolkit
**Status:** Stable, 100% consistent on all live saves and TC fixtures
(1847 stats + 3780 stats respectively, 0 failures).

This guide covers everything a GUI developer needs to render per-stat
contribution tooltips: data model, call signatures, common patterns,
and the handful of edge-case gotchas the resolver papers over.

The modifier-block summary API (see "Modifier-block summary API"
below) sits alongside the per-stat breakdown - rendering the
**Corrupted** and **Enchantments X/Y** blocks under their own
tooltip headers via `summarize_modifiers()`, independent of the
primary breakdown tree.

---

## TL;DR

```python
from d2rr_toolkit.game_data.property_formatter import (
    get_property_formatter, ItemRollContext,
)
from d2rr_toolkit.game_data.item_stat_cost import get_isc_db
from d2rr_toolkit.game_data.properties import get_properties_db
from d2rr_toolkit.game_data.skills import get_skill_db
from d2rr_toolkit.game_data.item_types import get_item_type_db

fmt = get_property_formatter()
ctx = ItemRollContext.from_parsed_item(parsed_item)

lines = fmt.format_properties_grouped(
    parsed_item.magical_properties, get_isc_db(), get_skill_db(),
    roll_context=ctx,
    props_db=get_properties_db(),
    breakdown=True,                     # <- opt in
    item=parsed_item,                   # required when breakdown=True
    item_types_db=get_item_type_db(),   # required when breakdown=True
)

for fp in lines:
    if fp.breakdown is not None:
        render(fp.plain_text, fp.segments, fp.roll_ranges,
               fp.is_perfect, fp.breakdown)
```

`breakdown=False` (the default) preserves the prior output byte-for-byte
- no regression for callers that don't opt in.

---

## Data model

### `FormattedProperty`

Unchanged except for the new optional attribute:

| Field             | Type                                  | Notes |
|-------------------|---------------------------------------|-------|
| `segments`        | `tuple[FormattedSegment, ...]`        | Coloured text runs for per-segment rendering |
| `plain_text`      | `str`                                 | Flat string (strips colour tokens) |
| `source_stat_ids` | `tuple[int, ...]`                     | ISC stat ids this line covers |
| `roll_ranges`     | `tuple[StatRollRange, ...]`           | Per-half roll windows (damage pairs get length-2) |
| `is_perfect`      | `bool`                                | True when every rolled contribution is at its max |
| `breakdown`       | `StatBreakdown \| None` **[NEW]**     | Per-source decomposition (populated only when `breakdown=True`) |

### `StatBreakdown` (new)

```python
@dataclass(frozen=True, slots=True)
class StatBreakdown:
    stat_id: int
    observed_value: float
    contributions: tuple[StatContribution, ...]
    is_consistent: bool
    is_perfect_roll: bool
    ambiguity: Literal["unique", "multiple", "none"]
    parser_warning: str | None
```

* **`stat_id`** - the ISC id this breakdown explains (41 for `lightresist`, etc.).
* **`observed_value`** - the item's actual stored value for this stat.
* **`contributions`** - attributed slices.  Sum always equals
  `observed_value` when `is_consistent` is True (always True on live
  saves + TC fixtures).
* **`is_consistent`** - `True` iff the attributed contributions sum
  exactly to `observed_value`.
* **`is_perfect_roll`** - `True` iff every `base_roll` contribution
  rolled at its range maximum.  Ignores modifier contributions - a
  corrupted item with a max-rolled base stat still deserves the star.
* **`ambiguity`** -
  * `"unique"`: the decomposition is the only plausible one (ideal
    case - render full per-source attribution).
  * `"multiple"`: several enchant-recipe combinations could explain
    the observed value; the simplest is returned in `contributions`.
    The GUI typically collapses the breakdown to a summary line.
  * `"none"`: the leftover went to `unknown_modifier` (Reimagined
    pathway not yet precisely indexed) or to strict `residual` (parser
    bug signal).  See source catalogue below.
* **`parser_warning`** - human-readable description of why the
  attribution isn't `"unique"`.  Safe to show in an "Inspect" panel
  for diagnostics; never shown in the primary tooltip.

### `StatContribution` (new)

```python
@dataclass(frozen=True, slots=True)
class StatContribution:
    amount: float
    source: ContributionSource
    source_detail: str | None
    roll_range: StatRollRange | None
```

* **`amount`** - numeric contribution to `observed_value`.
* **`source`** - see catalogue below.
* **`source_detail`** - compact human-readable label ready for
  tooltip display.  Contract per source:

  | Source              | Example `source_detail` |
  |---------------------|-------------------------|
  | `base_roll`         | `"Magic Prefix"` / `"Unique base"` / `"Set base"` / `"Runeword base"` / `"Magic Suffix"` / `"Rare Prefix"` / `"Rare Suffix"` |
  | `corruption`        | `"Corruption: +5% Deadly Strike"` · `"Corruption: +10% to All Resistances"` · `"Corruption: Cannot Be Frozen"` |
  | `enchantment`       | `"Enchantment: +1 to All Skills"` · `"Enchantment: +30 to Life"` · `"Enchantment: +8% Physical Damage Reduction"` |
  | `ethereal_bonus`    | `"Ethereal (+50% defense)"` |
  | `unknown_modifier`  | `"Corruption (precise mod could not be isolated)"` / `"Enchantment (precise recipe could not be isolated)"` / `"Corruption or Enchantment (could not fully isolate)"` / `"Runeword bonus (per-rune split unavailable)"` / `"Modifier bonus (precise source could not be isolated)"` |
  | `residual`          | `"Unattributed (possible parser bug)"` |

  All guaranteed <= 100 chars.  The raw property code + param never
  leak through; the renderer for corruption and enchantment reuses
  the game's own tooltip formatter so the displayed mod text matches
  what the cube preview shows.

* **`roll_range`** - populated only for `base_roll` contributions.
  Lets the GUI paint the `[min-max]` window next to the value even
  in breakdown mode.

### Source catalogue (`ContributionSource` literal)

| Source              | Meaning |
|---------------------|---------|
| `"base_roll"`       | Rolled from a unique / set / runeword / magic-prefix / magic-suffix slot.  Always carries a `roll_range`. |
| `"corruption"`      | Applied by the Orb of Corruption (`ka3`).  Deterministic from `stat 362 - 101`; every point is provable. |
| `"enchantment"`     | Applied by an ENCHANT ITEM cube recipe (341 recipes indexed from `cubemain.txt` lines 635-975).  Fixed values. |
| `"ethereal_bonus"`  | Extra 50% defense for ethereal armor (stat 31 only). |
| `"unknown_modifier"`| **Fallback.**  Fires when the indexed sources don't exactly reach `observed_value` AND the item bears a modifier flag / affix context / special quality.  Guarantees 100% `is_consistent` coverage while flagging resolver gaps via `parser_warning`. |
| `"residual"`        | **Parser-bug indicator.**  Fires only on plain normal / magic items with NO affix context.  If you ever see this in production, file a ticket. |
| `"automod"`         | Reserved in the type literal for future use.  The automagic itype-filter rules aren't fully mapped yet; leaving the source suppressed avoids over-attribution on charms. |
| `"set_bonus"`       | Reserved - multi-item set-piece threshold bonuses are currently folded into `unknown_modifier`. |
| `"superior_bonus"`  | Reserved - Superior quality armor +5-15% defense is currently folded into `unknown_modifier`. |
| `"crafted_bonus"`   | Reserved - Reimagined crafted-recipe bonuses (sundering, skill tab on crafted charms) are currently folded into `unknown_modifier`. |

---

## Rendering patterns

### Pattern A - classic tooltip with star + range

Your existing renderer still works unchanged.  The breakdown is
supplementary info; `roll_ranges` + `is_perfect` still drive the star
and `[min-max]` suffix.

### Pattern B - per-segment attribution

Walk `breakdown.contributions` and render each slice with its
`source_detail` verbatim (pre-composed by the resolver to fit one
tooltip line):

```
+23% Lightning Resistance                           [21-25]  ★
  ├─ Magic Prefix                                   +21
  └─ Corruption: +10% to All Resistances            +2
```

Rendering rules:

* Use `c.source_detail` exactly as provided - no re-formatting,
  no string concatenation with additional code / param info.
* Show the amount via `"+{c.amount:g}"` (same rule the game tooltip
  uses - drop trailing `.0` on integer rolls).
* Render the range (`c.roll_range`) only on `base_roll`
  contributions; the other sources are fixed values and don't
  have a window.
* When `breakdown.ambiguity == "multiple"` AND an
  `unknown_modifier` slice is present, surface a small footer line
  like "Some modifier values could not be fully isolated - see
  Inspect for details."  Don't hide the breakdown entirely - the
  user still gets partial attribution for the slices the resolver
  WAS able to identify.

Worked example - a corrupted+enchanted Unique torso (`upl` uid=251
from VikingBarbie):

```
+3 to All Skills
  └─ Unique base                                    +3
+30% Faster Hit Recovery
  └─ Unique base                                    +30
+15% Faster Block Rate
  └─ Corruption: +15% Faster Block Rate             +15
10% Increased Chance of Blocking
  └─ Corruption: 10% Increased Chance of Blocking   +10
+252% Enhanced Defense
  └─ Unique base                                    +252
```

### Pattern C - Perfection star logic

Use `fp.is_perfect` directly when `breakdown is None`.
When `breakdown is not None`, prefer `breakdown.is_perfect_roll` - it
isolates the base-roll-at-max signal from the modifier contributions.

### Pattern D - Partial-attribution transparency

When a stat's breakdown contains a contribution with
`source == "unknown_modifier"`, the resolver was able to identify
some but not all of the contribution pathways exactly.  The user
should see the slices that DID attribute cleanly plus a concise
hint that explains the rest.

The `source_detail` strings are already tailored to the modifier
flags on the item - just render them as-is:

* `"Corruption (precise mod could not be isolated)"` - the item is
  corrupted and the leftover belongs to the corruption outcome but
  the resolver can't pin the specific cubemain mod row.
* `"Enchantment (precise recipe could not be isolated)"` - same
  for enchanted items where the subset-search found multiple valid
  recipe combinations.
* `"Corruption or Enchantment (could not fully isolate)"` - both
  modifier flags are active and the leftover could come from
  either pathway.
* `"Runeword bonus (per-rune split unavailable)"` - runeword item
  with a leftover that can't yet be assigned to an individual rune.
* `"Modifier bonus (precise source could not be isolated)"` -
  generic catch-all for Crafted / Superior / ...

The GUI NEVER needs to hide the breakdown or show a blank slot -
every contribution always carries a user-facing `source_detail`.

### Pattern E - Audit / anti-cheat view

Scan the breakdown for `"residual"` contributions OR `parser_warning`
set.  Aggregate across all items on the character and surface in an
"Audit" dialog.  Typical categories:

* **Residual (plain item)** - almost certainly a parser bug.  Log +
  ticket.
* **Unknown modifier** - Reimagined content the resolver's data model
  doesn't yet decompose precisely.  Informational; the stat value
  is still honest and the user sees a clear explanation inline.
* **Parser warning only** - look for patterns across multiple items.

---

## Modifier-block summary API

For rendering the dedicated **Corrupted** and **Enchantments X/Y**
blocks beneath the stat list (instead of threading the attribution
into per-stat tooltips), use the aggregate builder:

```python
summary = resolver.summarize_modifiers(
    parsed_item, roll_context,
    breakdowns=breakdowns,   # optional: pass in the dict from
                             # resolve_item() to skip recomputation
)

if summary.corruption:
    render_corruption_block(summary.corruption)
if summary.enchantment:
    render_enchantment_block(summary.enchantment)
```

Returns an `ItemModifierSummary` with two optional display blocks:

| Block                 | Populated when                       |
|-----------------------|--------------------------------------|
| `summary.corruption`  | `roll_context.is_corrupted` is True  |
| `summary.enchantment` | `roll_context.is_enchanted` is True  |

Both blocks carry pre-formatted `mod_lines` (each <= 80 chars,
tooltip-ready) plus metadata the block header needs
(`outcome_name`, `is_brick`, `tier_name`, `capacity`,
`applied_count`, `has_ambiguity`).  Each dataclass has field-level
docstrings in [`src/d2rr_toolkit/game_data/stat_breakdown.py`](../src/d2rr_toolkit/game_data/stat_breakdown.py)
(`CorruptionDisplay`, `EnchantmentDisplay`, `ItemModifierSummary`)
that explain how `is_brick`, `is_phase1`, and `has_ambiguity`
should drive header / body rendering per outcome state.

---

## Threading / performance

* The resolver is **stateless between calls**.  Cache a single
  `StatBreakdownResolver` per process.
* All three backing databases (`AffixRollDatabase`,
  `CorruptionRollDatabase`, `EnchantmentRecipeDatabase`) are loaded
  once and cached through the standard `cached_load` pattern.  Cold
  first-hit is ~70 ms; subsequent calls <5 ms.
* `format_properties_grouped(breakdown=True)` autoloads any missing
  database.  Safe to call eagerly; reloads are no-ops when warm.
* Thread-safe on read paths; don't build the resolver inside a render
  loop.

---

## ItemRollContext helpers

`ItemRollContext.from_parsed_item(item)` is the canonical constructor.
Reads the following:

| Source                        | Field produced |
|-------------------------------|----------------|
| `item.extended.quality`       | `quality` |
| `item.unique_type_id`         | `unique_id` |
| `item.set_item_id`            | `set_id` |
| `item.runeword_id`            | `runeword_id` |
| `item.prefix_id` / `suffix_id`| `prefix_ids` / `suffix_ids` (scalar for magic) |
| `item.rare_affix_ids` / `rare_affix_slots` | `prefix_ids` / `suffix_ids` (parallel for rare/crafted) |
| `item.automod_id`             | `automod_id` (suppressed for rare/crafted - their mods flow through rare_affix_ids) |
| stat 361 present              | `is_corrupted` |
| stat 392/393/394/395 present  | `is_enchanted` |
| `item.flags.ethereal`         | `is_ethereal` |
| `item.flags.runeword`         | `is_runeword` |

All fields are optional - call with a partial item and the resolver
does its best.

---

## Known decomposition gaps

All of these reach 100% `is_consistent` via `unknown_modifier`; their
precise per-source attribution would be a future upgrade:

* **Crafted charm bonuses** - sundering (+X% pierce immunity) and
  skill-tab bonuses on crafted quality charms.  Source: cubemain
  crafted recipes; not yet indexed separately from ENCHANT ITEM.
* **Superior quality armor** - +5-15% defense bonus.  Source: engine
  constant per item type; no data-file index yet.
* **Runeword-to-rune attribution** - runeword items already carry
  their stats via the standard affix resolver, but the RW slot chain
  (rune[0] contributes X, rune[1] contributes Y, ...) isn't decomposed
  per-rune yet.
* **Automagic.txt attribution** - Reimagined's itype filtering rules
  for which automagic rows actually apply to which items aren't fully
  mapped; source currently suppressed to avoid over-attribution.
* **Set-bonus stats** - multi-item set thresholds (2-piece, 3-piece,
  ...) flow via a separate `set_bonus_properties` list on ParsedItem;
  the resolver doesn't walk them yet.

Watch the `parser_warning` field for exact per-stat gap descriptions
- they pinpoint which pathway was involved.

---

## Test coverage

| Suite                                          | Checks |
|------------------------------------------------|--------|
| `tests/test_stat_breakdown_resolver.py`        | 35     |
| `tests/test_stat_roll_ranges.py`               | 90     |
| `tests/test_charm_affix_decoding.py`           | 7      |
| Live-save cross-sweep (18 saves, 1847 stats)   | 100%   |
| TC-fixture cross-sweep (all `*.d2s`, 3780 stats) | 100% |

Regression in breakdown surfaces in §11 (VikingBarbie single-save
sweep) and §12 (cross-TC sweep) of
`tests/test_stat_breakdown_resolver.py`.

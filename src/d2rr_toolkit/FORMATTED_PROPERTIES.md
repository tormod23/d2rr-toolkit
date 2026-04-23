# Property Formatter - Structured Coloured Output

Turn the parser's raw `magical_properties` lists into display-ready
tooltip lines for the GUI. The formatter lives at
`d2rr_toolkit.game_data.property_formatter` and offers two output
shapes:

1. **Structured** (`list[FormattedProperty]`) - one object per tooltip
   line, carrying a tuple of coloured text segments that reproduces
   D2R's in-game per-segment colouring.
2. **Plain text** (`list[str]`) - the legacy shape; every colour
   token stripped. Use when the consumer paints lines in a single
   colour regardless.

## Quick Start

```python
from d2rr_toolkit.game_data.property_formatter import (
    get_property_formatter, FormattedProperty, FormattedSegment,
)
from d2rr_toolkit.game_data.item_stat_cost import get_isc_db
from d2rr_toolkit.game_data.skills import get_skill_db

fmt    = get_property_formatter()
isc    = get_isc_db()
skills = get_skill_db()

# Structured -- for GUI tooltip rendering:
lines: list[FormattedProperty] = fmt.format_properties_grouped(
    list(item.magical_properties), isc, skills,
)
for line in lines:
    for seg in line.segments:
        colour = COLOR_FOR_TOKEN.get(seg.color_token, DEFAULT_BLUE)
        render(seg.text, colour=colour)

# Plain -- for CLI / logging / tests:
plain: list[str] = fmt.format_properties_grouped_plain(
    list(item.magical_properties), isc, skills,
)
print("\n".join(plain))
```

## Dataclasses

### `FormattedSegment`

```python
@dataclass(frozen=True, slots=True)
class FormattedSegment:
    text: str
    color_token: str | None
```

One contiguous run of text in a single colour. `color_token` is the
raw one-character D2R token from the source template (see table
below); `None` means "use the caller's default colour" (text before
the first explicit token).

`text` is always non-empty for segments produced by the splitter -
empty runs are discarded, so consumers can iterate without guards.

### `FormattedProperty`

```python
@dataclass(frozen=True, slots=True)
class FormattedProperty:
    segments: tuple[FormattedSegment, ...]
    plain_text: str
    source_stat_ids: tuple[int, ...] = ()
    roll_ranges: tuple[StatRollRange, ...] = ()
    is_perfect: bool = False
```

| Field | Meaning |
|---|---|
| `segments` | Coloured pieces in order. Joining on `.text` reproduces the full visible line. Always at least one segment for a visible line. |
| `plain_text` | All tokens stripped. Matches the pre-refactor `format_properties_grouped` output byte-for-byte, by construction. |
| `source_stat_ids` | ISC stat IDs that produced this line. `()` for synthetic collapses (see below); `(stat_id,)` for a lone property; `(lead_id, *followers)` for a damage group. |
| `roll_ranges` | Possible roll windows resolved from the affix / unique / set / runeword tables when the caller supplies an `ItemRollContext`. Length 0 = "no info", length 1 = single-stat line, length 2 = damage pair `(min_range, max_range)`. See `StatRollRange` below. |
| `is_perfect` | `True` iff every range in `roll_ranges` reports `is_perfect()` against the prop's current rolled value. `False` when `roll_ranges` is empty - no range, no perfection claim. |

### `StatRollRange` + `ItemRollContext`

```python
@dataclass(frozen=True, slots=True)
class StatRollRange:
    min_value: float
    max_value: float
    source: RollSource           # "unique" | "set" | "runeword" |
                                 # "magic_prefix" | "magic_suffix" | ...

    def is_fixed(self) -> bool: ...
    def is_perfect(self, current: float) -> bool: ...


@dataclass(frozen=True, slots=True)
class ItemRollContext:
    quality: int | None = None       # 2..8
    unique_id: int | None = None     # *ID column of uniqueitems.txt
    set_id: int | None = None        # *ID column of setitems.txt
    runeword_id: int | None = None   # row index into runes.txt
    prefix_ids: tuple[int, ...] = () # row indices into magicprefix.txt
    suffix_ids: tuple[int, ...] = () # row indices into magicsuffix.txt

    @classmethod
    def from_parsed_item(cls, item) -> "ItemRollContext": ...
```

Build once per item (typically via `ItemRollContext.from_parsed_item`)
and thread the same instance through `format_properties_grouped` +
`format_prop_structured`. Passing `None` skips roll resolution -
every returned FormattedProperty has `roll_ranges=()` and
`is_perfect=False`, byte-identical to the behaviour before roll-range
resolution landed.

The resolver (see `affix_rolls.py::AffixRollDatabase`) walks every
source referenced by the context, aggregates `(min, max)`
contributions per stat id, and normalises the roll window so
`max >= min` always holds. Source priority when two sources could
both match: Unique -> Set -> Runeword -> Magic prefix -> Magic suffix.

## Colour Token Table

D2R embeds colour changes as three-byte escape sequences ``\xFFc<L>``
(``ÿ`` + ``c`` + a single-byte token `L`). The toolkit loader keeps
those bytes in the template cache verbatim - stripping is deferred to
the public API boundary. The known tokens in the live Reimagined data:

| Token | Colour | Typical use |
|---|---|---|
| `0` | white | default body text |
| `1` | red | Corrupted, critical warnings |
| `2` | set green | set bonuses (active) |
| `3` | magic blue | magic-prefix modifiers |
| `4` | unique gold | unique item name / token banners |
| `5` | dark grey | low-quality items |
| `6` | black | rare |
| `7` | tan | normal |
| `8` | orange | crafted |
| `9` | yellow | rare prefix |
| `:` | dark green | |
| `;` | purple | enchantments |
| `K` | grey | fluff text (`fadeDescription` - "You feel incorporeal...") |

Unknown tokens are passed through verbatim; consumers should fall
back to their default colour. 54 of the 441 shipped entries in
`item-modifiers.json` carry at least one token; the other 387 are
plain text and produce a single-segment `FormattedProperty` with
`color_token=None`.

## API Reference

### `format_properties_grouped(props, isc_db, skills_db=None, lang="enUS", *, roll_context=None, props_db=None) -> list[FormattedProperty]`

Primary entry point. Consumes the full `magical_properties` list of an
item and returns one `FormattedProperty` per tooltip line. Handles:

* Damage pairs (min+max, min+max+duration) collapsed into one line
  with `source_stat_ids=(lead, *followers)`.
* Stat collapses (`all Attributes`, `All Resistances`, elemental
  mastery / pierce) when every member is present with an identical
  value - emitted with `source_stat_ids=()` per convention.
* Priority ordering via ISC `desc_priority` (descending).
* Hidden / follower / mirror stat suppression.
* Reimagined hidden-skill filtering (skill 449).
* **Roll-range resolution** when the optional `roll_context=` +
  `props_db=` kwargs are supplied.  Each output line then carries
  `roll_ranges` (tuple of `StatRollRange`, length 1 for simple
  stats, length 2 for damage pairs with `(min_range, max_range)`)
  and `is_perfect` (True iff every range's max equals the stat's
  rolled value).  See the `StatRollRange` block above and the
  sample in the `Roll-range usage` section below.

### `format_properties_grouped_plain(props, isc_db, skills_db=None, lang="enUS") -> list[str]`

Back-compat wrapper. Returns `[p.plain_text for p in
format_properties_grouped(...)]`. Byte-identical to the pre-refactor
output - any existing test expecting the legacy `list[str]` shape
continues to pass without change.

### `format_prop(prop, isc_db, skills_db=None, lang="enUS") -> str | None`

Single-property variant returning plain text (token-stripped).
Unchanged signature; consumers that only render one line at a time
(e.g. set bonuses, runeword property lists) keep using this.

### `format_prop_structured(prop, isc_db, skills_db=None, lang="enUS") -> FormattedProperty | None`

Structured twin of `format_prop`. Returns a single
`FormattedProperty` with the prop's stat id in `source_stat_ids`.

### `format_code_value(code, value, param="", ...) -> str | None`

Used by `SetBonusEntry.format()` to render set bonuses keyed by
property code (from `sets.txt` `PCode*` / `FCode*` and `setitems.txt`
`aprop*`). Plain-text output; retains back-compat for existing
callers. For encode=2 / encode=3 stats (chance-to-cast skill-on-event,
charged skill), `SetBonusEntry.format` now routes through a prop-dict
builder internally so the `max` column (skill level) no longer gets
dropped - see **§Chance-to-cast** below.

### Internals

* `_COLOR_TOKEN_RE = re.compile(r"[ÿ\xff]c(.)", re.DOTALL)` - the
  authoritative pattern. Capture group is the token.
* `_split_color(text) -> list[FormattedSegment]` - splits at every
  token, discards zero-length runs, closes any open run at EOF.
* `_strip_color(text) -> str` - remove all tokens. Kept as a helper
  for the plain paths.
* `_make_formatted(raw, source_stat_ids=()) -> FormattedProperty |
  None` - the boundary between "raw formatter output" and "structured
  API". Applies a strip-equivalent whitespace trim and returns
  `None` for blank lines.

## Chance-to-cast Set Bonuses

`setitems.txt` / `sets.txt` encode every chance-to-cast tier bonus as
a two-column pair:

* `amin` / `PMin` / `FMin`   -> **chance** (% or charge count)
* `amax` / `PMax` / `FMax`   -> **skill level**
* `apar` / `PParam` / `FParam` -> **skill name** (string, not id)

The default single-value formatter path
(`format_code_value`) only passes one number through, which caused
tooltips like "4% Chance to cast level **0** Shock Wave when struck"
(Darkmage's Solar Flair, raw min=4 max=20 param="Shock Wave") for
every encode=2 / encode=3 stat until
`SetBonusEntry._format_encoded_skill` was added - it detects the
encode value, resolves the skill name to an id via
`SkillDatabase.id_by_name()`, and feeds a full
`{chance, level, skill_id, skill_name}` prop dict to `format_prop`.

Blast-radius audit in Reimagined 3.0.7: **23 per-item bonuses** on 23
set items + **15 full-set FCode bonuses** on 15 different sets used
the affected codes (`hit-skill`, `gethit-skill`, `kill-skill`). All
pinned in `tests/test_set_bonus_ctc_levels.py` (58 checks).

## Loader Contract

`PropertyFormatter.load_from_bytes` parses `item-modifiers.json` and
stores each entry's enUS template **with colour tokens intact**:

```python
self._templates[key] = text    # NOT _strip_color(text)
```

This is the only file on which the colour information is available;
stripping at load time would erase it before any formatter branch
could see it. The public API applies stripping (plain path) or
splitting (structured path) at the final return point.

Downstream stripping was also removed from the three per-descfunc
branches (descfunc=20 `Corrupted`, `_format_skill_on_event`,
`_format_charged_skill`) that used to call `_strip_color` on their
intermediate string - they now emit the raw (possibly-tagged) string
and let the boundary wrapper decide.

## Test Coverage

`tests/test_inline_color_codes.py` - **40 checks**:

1. Loader retains `\xFFc<L>` bytes verbatim (synthetic JSON fixture).
2. `_split_color` round-trips across 6 input classes; concatenation
   always matches `_strip_color`.
3. End-to-end through the live `item-modifiers.json`:
   `fadeDescription` renders with a `K` (grey) segment and
   `source_stat_ids=(181,)`.
4. `structured[i].plain_text == plain[i]` across a 9-prop sample
   exercising every descfunc branch and every collapse.
5. All-resist collapse carries `source_stat_ids=()`.
6. Damage pair `(21, 22)` carries `source_stat_ids=(21, 22)`; lone
   follower renders with `(22,)`.
7. `format_prop` plain path strips every `\xFF` byte.

Full regression check: running this suite alongside the other 12
always-green suites yields ~1000 checks / 0 FAIL.

## Roll-range usage

Render an item's tooltip with a perfect-roll star + `[min-max]`
hints per stat:

```python
from d2rr_toolkit.game_data.property_formatter import (
    get_property_formatter, ItemRollContext,
)
from d2rr_toolkit.game_data.item_stat_cost import get_isc_db
from d2rr_toolkit.game_data.skills import get_skill_db
from d2rr_toolkit.game_data.properties import get_properties_db
from d2rr_toolkit.game_data.affix_rolls import load_affix_rolls

# Load the roll DB once at startup, alongside the other
# game_data loaders.  Uses the same cached_load pattern, so warm
# launches hit ~5 ms.
load_affix_rolls()

ctx = ItemRollContext.from_parsed_item(item)   # item = ParsedItem
lines = get_property_formatter().format_properties_grouped(
    list(item.magical_properties),
    get_isc_db(), get_skill_db(),
    roll_context=ctx, props_db=get_properties_db(),
)

for line in lines:
    star = "*" if line.is_perfect else " "
    if line.roll_ranges:
        ranges = " / ".join(
            f"[{r.min_value:g}-{r.max_value:g}]" for r in line.roll_ranges
        )
        print(f"{star} {line.plain_text}  {ranges}")
    else:
        print(f"{star} {line.plain_text}")
```

Sample output on TC56 Lightsabre (every stat resolved to its
`uniqueitems.txt` prop row):

```
  15% Chance to cast level 50 Chain Lightning on striking       [15-50]
* +20% Increased Attack Speed                                   [20-20]
  +232% Enhanced Weapon Damage                                  [200-250] / [200-250]
  Adds 30-55 Weapon Damage                                      [30-55] / [30-55]
* Ignore Target's Defense                                       [1-1]
  Adds 1-450 Weapon Lightning Damage                            [1-450] / [1-450]
* +30% to Lightning Skill Damage                                [15-30]
* +15% Lightning Damage Absorbed                                [10-15]
* +7 to Light Radius                                            [7-7]
```

Star on fixed / at-max rolls, `[min-max]` on every rollable line,
two ranges per damage pair.  See `affix_rolls.py` for the resolver
internals and `tests/test_stat_roll_ranges.py` (45 checks) for the
full regression matrix.



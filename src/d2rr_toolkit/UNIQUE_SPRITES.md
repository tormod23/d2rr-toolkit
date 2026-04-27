# Unique & Set Item Sprite Resolution

How the toolkit maps a `ParsedItem` to the correct HD sprite bytes when
the item is a Unique or Set piece with a dedicated sprite override.
Base-item sprites and GFX variants (covered by the plain `item_code`
and `item_code#gfx_index` paths) are not in scope here - see
`BULK_SPRITE_LOADER.md` for the full preloader architecture.

## Authoritative data sources

D2R Reimagined ships the HD sprite manifests inside the mod MPQ tree.
The toolkit reads them through the Iron Rule (`CASCReader.read_file`,
Reimagined mod install first, D2R Resurrected CASC fallback):

| File | Purpose | Key format |
|---|---|---|
| `data/hd/items/items.json` | Base-item `code -> asset path` | `item_code` (3-4 chars) |
| `data/hd/items/uniques.json` | Per-unique sprite override | snake-case of `uniqueitems.txt.index` |
| `data/hd/items/sets.json` | Per-set-item sprite override | snake-case of `setitems.txt.index` |

Each `uniques.json` / `sets.json` entry carries three tiers
(`normal` / `uber` / `ultra`) that usually point at the same asset:

```json
[
    {"stealskull": {
        "normal": "helmet/coif_of_glory",
        "uber":   "helmet/coif_of_glory",
        "ultra":  "helmet/coif_of_glory"
    }},
    {"the_gnasher": {...}},
    ...
]
```

The `asset_path` is a two-segment mod-relative path; the sprite
basename is the last segment.  The toolkit probes mod HD first and
falls back to CASC via the shared sprite-name index in the bulk
loader.

## Two name spaces

A Unique/Set item has two distinct names:

| Source | Name | Example |
|---|---|---|
| `uniqueitems.txt.index` column | **raw internal name** | `Life and Death` |
| `ItemNamesDatabase.get_unique_name(*ID)` (via `item-names.json`) | **localised display name** | `Life & Death` |

The mod's JSON manifests are keyed on snake-case of the **raw**
column; the GUI resolves item names through the localised table.
When the two match (most rows), both snake forms coincide.  When the
mod has chosen a different display name, they diverge - and the
resolver has to bridge the gap.

### Current divergent entries (Reimagined 3.0.7)

**37 uniques + 2 sets** diverge between raw and display.  Of these,
**4 uniques** have a dedicated sprite in `uniques.json` and therefore
need the alias bridge; the rest have no custom sprite and fall back
to the base item sprite regardless.

| Raw `index` | Display name | Base code |
|---|---|---|
| `Life and Death` | `Life & Death` | `cm2` |
| `Unique Warlock Helm` | `Hellwarden's Will` | `xsk` |
| `Ars Al'Diablolos` | `Ars Al'Diabolos` | `waf` |
| `El Druin` | `El'Druin` | `7gs` |

Set-side divergences (`Panda's Mitts` -> `Mittens`, `Panda's Coat` ->
`Jacket`) carry no dedicated sprite at present; the alias helper
handles them pre-emptively so a future sprite update is covered.

## Snake-case normalisation

```python
from d2rr_toolkit.sprites import display_name_to_snake_case
```

Algorithm: lowercase -> strip apostrophes (not replaced with
underscore) -> collapse runs of non-alphanumeric chars into a single
underscore -> strip leading/trailing underscores.

| Input | Output |
|---|---|
| `Stealskull` | `stealskull` |
| `The Gnasher` | `the_gnasher` |
| `Civerb's Cudgel` | `civerbs_cudgel` |
| `Axe of Fechmar` | `axe_of_fechmar` |
| `Life and Death` | `life_and_death` |
| `Life & Death` | `life_death` |
| `El'Druin` | `eldruin` |

Same function, different name-space inputs -> different keys.  That
asymmetry is why the resolver needs either to start from the raw
name or to accept a map with both snakes registered.

## Sprite-dict key schema

All sprite bytes live in a single `dict[str, bytes]`.  Keys follow
`make_sprite_key`:

| Inputs | Returned key |
|---|---|
| `"rin"` | `"rin"` |
| `"rin"`, `gfx_index=3` | `"rin#3"` |
| `"rin"`, `unique_name="Ring of Engagement"` | `"rin@Ring of Engagement"` |
| `"amu"`, `set_name="Tal Rasha's Lidless Eye"` | `"amu@Tal Rasha's Lidless Eye"` |

Priority: `unique_name` > `set_name` > `gfx_index` > plain code.

**Callers pass the localised display name.**  The bulk loader stores
each sprite under the display-name key and registers the raw-name
key as a back-compat alias when they differ, so the same dict serves
both a GUI that resolves names via `ItemNamesDatabase` and a script
that iterates the raw `uniqueitems.txt.index` column.

## Public API

### `load_unique_sprite_map(path, *, tier="normal") -> dict[str, str]`
### `load_set_sprite_map(path, *, tier="normal") -> dict[str, str]`

Parse `uniques.json` / `sets.json` into a flat `{snake_name: asset_path}`
dict keyed on the raw snake only.  Handles both the list-of-
single-key-dicts layout (current Reimagined) and a plain-dict
fallback (defensive).

### `load_unique_sprite_map_with_aliases(path, uniqueitems_rows, names_db, *, tier="normal") -> dict[str, str]`
### `load_set_sprite_map_with_aliases(path, setitems_rows, names_db, *, tier="normal") -> dict[str, str]`

Enriched variants.  Return a **strict superset** of the plain loaders'
output: every diverging row gets its display-name snake added as a
second key pointing to the same asset path.

Arguments:

* `path` - path to `uniques.json` / `sets.json`
* `uniqueitems_rows` / `setitems_rows` - already-loaded rows from
  `read_game_data_rows("data:data/global/excel/uniqueitems.txt")` /
  `setitems.txt`
* `names_db` - loaded `ItemNamesDatabase`.  When `None` or not loaded,
  no aliases are added and the result equals the plain map.
* `tier` - `"normal"` / `"uber"` / `"ultra"` (default `"normal"`)

Recommended for any caller whose downstream lookup derives the
`unique_name` / `set_name` from `ItemNamesDatabase`, i.e. the GUI
and the CLI.

### `display_name_to_snake_case(display_name: str) -> str`

Shared normaliser used by every path above.  Deterministic; no
dependencies; safe to call on either the raw or the display name.

### `SpriteResolver`

```python
from d2rr_toolkit.sprites import SpriteResolver
```

On-demand sprite retrieval for consumers that don't want the full
bulk preload.  Constructor accepts the sprite maps produced by the
loaders above:

```python
SpriteResolver(
    casc_reader=casc,
    mod_hd_dir=gp.mod_hd_items,
    mod_dc6_dir=gp.mod_dc6_items,
    items_json=items_json,
    unique_sprite_map=unique_sprite_map,   # enriched preferred
    set_sprite_map=set_sprite_map,          # enriched preferred
)

png = resolver.get_sprite("cm2", unique_name="Life & Death")
png = resolver.get_sprite("rin", unique_name="Stealskull", base_code="rin")
png = resolver.get_sprite("rin", gfx_index=3)
```

When passed the enriched maps, the resolver resolves any display
name that appears in either name space transparently.  The legacy
directory-probing fallback (`uniquering/`, `uniqueamulet/`, ...) is
retained for callers that supply neither map.

## End-to-end resolution contract

Given a `ParsedItem`, the recommended flow for the GUI is:

```python
from d2rr_toolkit.game_data.item_names import get_item_names_db
from d2rr_toolkit.sprites import make_sprite_key

names_db = get_item_names_db()
utid     = getattr(item, "unique_type_id", None)
sid      = getattr(item, "set_item_id", None)

unique_name = names_db.get_unique_name(utid)   if utid else None
set_name    = names_db.get_set_item_name(sid)  if sid  else None

key = make_sprite_key(
    item.item_code,
    gfx_index=getattr(item, "gfx_index", None),
    unique_name=unique_name,
    set_name=set_name,
)
png = sprites.get(key) or sprites.get(make_sprite_key(item.item_code))
```

The `sprites.get(key) or sprites.get(code)` pattern is the canonical
fallback: when a unique has no dedicated sprite, the key carrying
its display name is absent and the base-item sprite takes over.

## Bulk loader integration

`load_all_item_sprites` (see `BULK_SPRITE_LOADER.md`) performs the
enrichment internally:

1. Parse `uniqueitems.txt` / `setitems.txt` rows with `*ID`, raw
   name, and code per entry.
2. Look each unique's asset up in `uniques.json` keyed by the **raw**
   snake - that's the authoritative manifest.
3. Resolve the display name via `ItemNamesDatabase.get_unique_name(*ID)`
   (falls back to the raw name if no localisation exists).
4. Store the decoded PNG under
   `make_sprite_key(code, unique_name=display_name)` - the key the
   GUI looks up.
5. When display != raw, also register the raw-name key as an alias
   pointing to the same PNG so scripts using the raw index keep
   working.

Same flow for `sets.json` / `setitems.txt` in Phase 4.

## Test coverage

| Suite | Checks | Covers |
|---|---:|---|
| `tests/test_bulk_sprite_loader.py` | 91+ | Full preloader flow, per-basename cache, resolver parity |
| `tests/test_unique_sprite_display_name_alias.py` | 23 | TC55 FrozenOrbHydra's unique charms + the 4 user-visible divergent uniques + `load_unique_sprite_map_with_aliases` pinning |
| `tests/test_decode_sprite_tail_bug.py` | 20 | SpA1 decoder (unrelated to the name spaces but the same pipeline - see `adapters/casc/SPRITES.md`) |

Key assertions pinned against the live Reimagined 3.0.7 data:

* `cm2@Life & Death` -> 34 977-byte unique PNG, byte-distinct from the
  `cm2` base sprite.
* `cm2@Life and Death` (raw alias) -> same PNG as above.
* `snake("Life & Death") == "life_death"` - confirms the display
  snake differs from the manifest key (`life_and_death`) and hence
  the alias is necessary.
* `load_unique_sprite_map_with_aliases` populates exactly the four
  expected aliases (`life_death`, `hellwardens_will`,
  `ars_aldiabolos`, `eldruin`) against the live `uniques.json`.

# d2rr-toolkit Quick Start Guide

How to use the d2rr-toolkit from a standalone GUI project to load
characters, resolve item sprites, and read game assets.

## Prerequisites

```python
# Both packages must be importable (e.g. via pip install -e)
import d2rr_toolkit
from d2rr_toolkit.adapters.casc import CASCReader
from d2rr_toolkit.adapters.casc.sprites import decode_sprite
```

---

## 1. Initialize Game Data (once at startup)

Every tool that uses d2rr-toolkit needs to load the game data tables
before parsing characters or resolving sprites.

```python
from pathlib import Path
from d2rr_toolkit.config import init_game_paths
from d2rr_toolkit.meta import get_source_versions
from d2rr_toolkit.game_data.item_types import load_item_types, get_item_type_db
from d2rr_toolkit.game_data.item_names import load_item_names, get_item_names_db
from d2rr_toolkit.game_data.item_stat_cost import load_item_stat_cost
from d2rr_toolkit.game_data.skills import load_skills
from d2rr_toolkit.game_data.charstats import load_charstats
from d2rr_toolkit.game_data.sets import load_sets
from d2rr_toolkit.game_data.gems import load_gems
from d2rr_toolkit.game_data.properties import load_properties
from d2rr_toolkit.game_data.property_formatter import load_property_formatter
from d2rr_toolkit.game_data.automagic import load_automagic

# Point to your D2R installation and mod.
paths = init_game_paths(
    d2r_install=Path(r"C:\Program Files (x86)\Diablo II Resurrected"),
    mod_dir=Path(r"C:\Program Files (x86)\Diablo II Resurrected\mods\Reimagined"),
)

# Resolve the version markers once and thread them into every
# loader - shared `SourceVersions` lets the persistent pickle
# cache invalidate every entry in one atomic sweep when D2R or
# Reimagined ships a new version.  See GAME_DATA_CACHE.md for the
# full invalidation contract.
versions = get_source_versions(
    game_dir=paths.d2r_install, mod_dir=paths.mod_dir,
)

# Load all game data (order does not matter). Each loader resolves
# its files through the shared CASCReader singleton - Reimagined mod
# install first, D2R Resurrected CASC archive as the sole fallback.
# See the Iron Rule dossier in memory: project_data_source_iron_rule.
# First launch hits the cold parse (~1-2 s total); every subsequent
# launch reads from the on-disk cache (~200-300 ms total).
load_item_types(source_versions=versions)
load_item_stat_cost(source_versions=versions)
load_item_names(source_versions=versions)
load_skills(source_versions=versions)
load_charstats(source_versions=versions)
load_sets(source_versions=versions)
load_gems(source_versions=versions)
load_properties(source_versions=versions)
load_property_formatter(source_versions=versions)
load_automagic(source_versions=versions)
```

> **Tip.**  Every `load_*()` accepts `use_cache=False` for tests
> that want a fresh parse, and `cache_dir=tmp_path` for routing
> the pickle files into a throwaway directory.  Globally disable
> the cache in CI via the environment variable
> `D2RR_DISABLE_GAME_DATA_CACHE=1`.

---

## 2. Parse a Character (.d2s)

```python
from d2rr_toolkit.parsers.d2s_parser import D2SParser

character = D2SParser(Path(r"C:\Users\me\Saved Games\...\MyChar.d2s")).parse()

print(f"Name:  {character.header.character_name}")
print(f"Level: {character.header.level}")
print(f"Class: {character.header.character_class_name}")
print(f"Items: {len(character.items)}")
```

---

## 3. Read Items with Positions and Sprites

Each `ParsedItem` has position and display information that a GUI needs:

```python
from d2rr_toolkit.constants import (
    LOCATION_STORED, LOCATION_EQUIPPED, LOCATION_BELT,
)

type_db = get_item_type_db()
names_db = get_item_names_db()

# character.items contains only ROOT items. Socket children (runes /
# gems / jewels in sockets) live nested inside each parent's
# `socket_children` list, so no manual skip filter is needed.
for i, item in enumerate(character.items):
    # Optional: render the parent's socket children alongside it.
    children = item.socket_children   # list[ParsedItem], may be empty

    # Grid position (for inventory/stash items)
    x = item.flags.position_x
    y = item.flags.position_y
    panel = item.flags.panel_id      # 1=Inventory, 4=Cube, 5=Stash
    location = item.flags.location_id  # 0=Stored, 1=Equipped, 2=Belt

    # Item dimensions (in grid cells)
    inv_w, inv_h = type_db.get_inv_dimensions(item.item_code)

    # Display name
    quality_id = item.extended.quality if item.extended else 2
    display_name = names_db.build_display_name(
        item.item_code, quality_id,
        unique_type_id=getattr(item, 'unique_type_id', None),
        set_item_id=getattr(item, 'set_item_id', None),
        prefix_id=getattr(item, 'prefix_id', None),
        suffix_id=getattr(item, 'suffix_id', None),
        is_runeword=item.flags.runeword,
    )

    # Inventory file (sprite filename without extension)
    invfile = type_db.get_inv_file(item.item_code) or ""

    print(f"[{i}] {display_name}")
    print(f"     Code: {item.item_code}, Location: {location}, Panel: {panel}")
    print(f"     Position: ({x}, {y}), Size: {inv_w}x{inv_h}")
    print(f"     Invfile: {invfile}")
    print(f"     Ethereal: {item.flags.ethereal}, Socketed: {item.flags.socketed}")
```

### Equipped Items

Equipped items have `location_id=1` and use `equipped_slot` instead of
grid coordinates:

```python
SLOT_NAMES = {
    1: "Head", 2: "Neck", 3: "Torso", 4: "Right Hand", 5: "Left Hand",
    6: "Right Ring", 7: "Left Ring", 8: "Waist", 9: "Feet", 10: "Hands",
    11: "Alt Right Hand", 12: "Alt Left Hand",
}

for item in character.items:
    if item.flags.location_id == LOCATION_EQUIPPED:
        slot = item.flags.equipped_slot
        print(f"{SLOT_NAMES.get(slot, '?')}: {item.item_code}")
```

---

## 4. Load Item Sprites via SpriteResolver

The `SpriteResolver` searches mod directory and CASC archive automatically:

```python
from d2rr_toolkit.adapters.casc import CASCReader
from d2rr_toolkit.sprites.resolver import SpriteResolver
from d2rr_toolkit.sprites import (
    load_items_json,
    load_unique_sprite_map_with_aliases,
    load_set_sprite_map_with_aliases,
)
from d2rr_toolkit.config import get_game_paths
from d2rr_toolkit.adapters.casc import read_game_data_rows
from d2rr_toolkit.game_data.item_names import get_item_names_db

gp = get_game_paths()
names_db = get_item_names_db()   # already loaded in §1

casc = CASCReader(gp.d2r_install)
items_json = load_items_json(gp.mod_items_json)

# uniques.json / sets.json enriched with display-name aliases.
# 37 Reimagined uniques + 2 sets have localized names that differ
# from their raw uniqueitems.txt / setitems.txt index column (e.g.
# raw "Life and Death" displays as "Life & Death").  The alias
# loaders register the display-name snake as a second key pointing
# at the same asset path so a GUI resolving names via
# `ItemNamesDatabase.build_display_name()` always hits.
u_rows = read_game_data_rows("data:data/global/excel/uniqueitems.txt")
s_rows = read_game_data_rows("data:data/global/excel/setitems.txt")
unique_sprite_map = load_unique_sprite_map_with_aliases(
    gp.mod_uniques_json, u_rows, names_db,
)
set_sprite_map = load_set_sprite_map_with_aliases(
    gp.mod_sets_json, s_rows, names_db,
)

resolver = SpriteResolver(
    casc_reader=casc,
    mod_hd_dir=gp.mod_hd_items,       # .../Reimagined.mpq/data/hd/global/ui/items
    mod_dc6_dir=gp.mod_dc6_items,      # .../Reimagined.mpq/data/global/items (legacy)
    items_json=items_json,
    unique_sprite_map=unique_sprite_map,
    set_sprite_map=set_sprite_map,
)

# Load a sprite by item code
png_bytes = resolver.get_sprite("rin")                     # Base ring
png_bytes = resolver.get_sprite("rin", gfx_index=3)        # Ring variant 3
png_bytes = resolver.get_sprite(
    "rin", unique_name="Ring of Engagement", base_code="rin"  # Unique sprite
)

# Load a sprite by CASC path (for non-item sprites like UI panels)
png_bytes = resolver.get_sprite_by_path(
    "data:data/hd/global/ui/panel/gemsocket.sprite"
)
```

The plain `load_unique_sprite_map` / `load_set_sprite_map` helpers
still exist as a minimum-dependency fallback, but the `_with_aliases`
variants are the recommended path for any caller whose input comes
from `ItemNamesDatabase`.  See `UNIQUE_SPRITES.md` for the full
resolution contract and the divergent-name reference table.

---

## 5. Load a File Directly from Disk (Mod Directory)

For files that exist as regular files in the mod directory (not inside
the CASC archive), you do NOT need the CASC reader at all. Just read
the file directly:

```python
from pathlib import Path

# This is a regular PNG file on disk -- just read it!
stash_bg = Path(
    r"C:\Program Files (x86)\Diablo II Resurrected"
    r"\mods\Reimagined\Reimagined.mpq"
    r"\data\hd\global\ui\panel\stash\stashpanel_bg2.png"
)
png_bytes = stash_bg.read_bytes()
# -> Ready to use as image source in your GUI
```

**Important distinction:** The CASC archive contains the **base game** files.
Mod files are stored as regular files on disk inside the mod directory.
If a file exists in the mod directory, you can read it directly with
`Path.read_bytes()`. The CASC reader is only needed for base game files
that the mod does NOT override.

### When to use what:

| File Location | How to Read | Example |
|---|---|---|
| Mod directory (exists on disk) | `Path(...).read_bytes()` | `stashpanel_bg2.png`, mod-added sprites |
| CASC archive (base game only) | `casc.read_file(path)` | Vanilla weapon sprites, fonts, game tables |
| CASC archive (.sprite format) | `casc.read_file()` + `decode_sprite()` | HD item sprites (SpA1 format -> PNG) |
| Either (mod overrides base) | `casc.read_file()` with `mod_dir=` | Automatic: checks mod first, CASC fallback |

### Reading ANY mod file by known path:

```python
from pathlib import Path

mod_root = Path(
    r"C:\Program Files (x86)\Diablo II Resurrected"
    r"\mods\Reimagined\Reimagined.mpq"
)

# PNG files are already images -- read directly
panel_bg = (mod_root / "data/hd/global/ui/panel/stash/stashpanel_bg2.png").read_bytes()

# SpA1 .sprite files need decoding
from d2rr_toolkit.adapters.casc.sprites import decode_sprite
sprite_raw = (mod_root / "data/hd/global/ui/items/misc/ring/ring.sprite").read_bytes()
png_bytes = decode_sprite(sprite_raw)  # SpA1 -> PNG with transparency

# Excel data files are just TSV text
weapons_txt = (mod_root / "data/global/excel/weapons.txt").read_text(encoding="utf-8")
```

---

## 6. Resolve Invtransform (Color Tinting)

The GUI needs to know which color tint to apply to an item's sprite:

```python
from d2rr_toolkit.display.invtransform import get_invtransform

for item in character.items:
    tint = get_invtransform(item)
    # tint is e.g. "cred", "lgld", "dpur", or None
    if tint:
        print(f"{item.item_code}: tint={tint}")
```

The function reads gem-socket children from `item.socket_children`
directly - no need to pass the surrounding item list.

The returned string is a D2R color code. Your GUI maps these to actual
colors/CSS filters. Common codes:

| Code | Color | Typical Source |
|------|-------|----------------|
| `cred` | Bright red | Ruby gem socket |
| `cblu` | Bright blue | Sapphire gem socket |
| `cgrn` | Bright green | Emerald gem socket |
| `dgld` | Dark gold | Unique items |
| `lpur` | Light purple | Amethyst gem socket |
| `whit` | White | Diamond gem socket |
| `dred` | Dark red | Set items |
| `lgld` | Light gold | Magic prefix |

---

## 7. Render Item Properties as Coloured Tooltip Lines

The property formatter turns the parser's raw `magical_properties`
list into display-ready lines. It exposes two output shapes:

* **Structured** - `list[FormattedProperty]` from
  `format_properties_grouped(...)`, one `FormattedProperty` per
  tooltip line, each carrying a tuple of `FormattedSegment(text,
  color_token)` so a GUI can paint per-segment colours (dark-grey
  fluff on `fadeDescription`, red on `Corrupted`, etc.).
* **Plain strings** - `list[str]` from
  `format_properties_grouped_plain(...)`, legacy shape with every
  colour token stripped.  Use this when the consumer paints the
  whole line in a single colour anyway.

```python
from d2rr_toolkit.game_data.property_formatter import (
    get_property_formatter, FormattedProperty, FormattedSegment,
)
from d2rr_toolkit.game_data.item_stat_cost import get_isc_db
from d2rr_toolkit.game_data.skills import get_skill_db

fmt = get_property_formatter()
isc = get_isc_db()
skills = get_skill_db()

for item in char.items:
    lines: list[FormattedProperty] = fmt.format_properties_grouped(
        list(item.magical_properties), isc, skills,
    )
    for line in lines:
        # GUI path: render each segment in its mapped colour.
        for seg in line.segments:
            colour = COLOR_FOR_TOKEN.get(seg.color_token, DEFAULT_BLUE)
            render(seg.text, colour=colour)
        # CLI / log path: just print the plain text.
        print(line.plain_text)
```

### Colour token table

The tokens are raw `\xFFc<L>` escapes embedded by D2R in
`item-modifiers.json` and friends. The toolkit passes them through
unchanged - consumers map them to their own palette:

| Token | Colour | Typical use |
|---|---|---|
| `0` | white | default body text |
| `1` | red | Corrupted, critical warnings |
| `2` | set green | set bonuses |
| `3` | magic blue | magic-prefix modifiers |
| `4` | unique gold | unique item name |
| `5` | dark grey | low-quality items |
| `6` | black | rare |
| `7` | tan | normal |
| `8` | orange | crafted |
| `9` | yellow | rare prefix |
| `:` | dark green | |
| `;` | purple | enchantments |
| `K` | grey | fluff text (`fadeDescription`) |

Unknown tokens arrive verbatim; GUIs should fall back to their
default colour when they see one they don't recognise.

### Set-bonus lines

`SetBonusEntry.format(...)` feeds the same pipeline for per-item
bonuses from `setitems.txt` (`aprop1a`..`aprop5b`) and set-wide
bonuses from `sets.txt` (`PCode2..5 a/b`, `FCode1..8`). Chance-to-
cast entries (`hit-skill`, `gethit-skill`, `kill-skill`) now carry
their full `chance`/`level`/`skill_name` triple through the template
- earlier revisions dropped the level (stored in the `max` column)
and produced "chance to cast level 0 <Skill>". See
`tests/test_set_bonus_ctc_levels.py` for the pinned expected strings.

---

## 8. Socket Layout

For items with sockets, the GUI needs to render socket overlays:

```python
from d2rr_toolkit.display.item_display import get_socket_positions

# Get socket positions (relative coordinates within the item)
inv_w, inv_h = type_db.get_inv_dimensions(item.item_code)
num_sockets = item.total_nr_of_sockets or 0
positions = get_socket_positions(inv_w, inv_h, num_sockets)
# Returns: [(x_fraction, y_fraction), ...] for each socket
```

---

## Full Example: Render a Character Inventory

```python
from pathlib import Path
from d2rr_toolkit.config import init_game_paths
from d2rr_toolkit.game_data.item_types import load_item_types, get_item_type_db
from d2rr_toolkit.game_data.item_names import load_item_names, get_item_names_db
from d2rr_toolkit.game_data.item_stat_cost import load_item_stat_cost
from d2rr_toolkit.game_data.skills import load_skills
from d2rr_toolkit.game_data.charstats import load_charstats
from d2rr_toolkit.parsers.d2s_parser import D2SParser
from d2rr_toolkit.display.invtransform import get_invtransform
from d2rr_toolkit.display.item_display import get_socket_positions
from d2rr_toolkit.constants import LOCATION_STORED
from d2rr_toolkit.sprites.resolver import SpriteResolver
from d2rr_toolkit.adapters.casc import CASCReader
import json

# -- Init (once) --
gp = init_game_paths()
load_item_types(); load_item_stat_cost(); load_item_names()
load_skills(); load_charstats()

casc = CASCReader(gp.d2r_install)
items_json = json.loads(gp.mod_items_json.read_text()) if gp.mod_items_json.exists() else {}
resolver = SpriteResolver(casc, gp.mod_hd_items, gp.mod_dc6_items, items_json)

# -- Parse character --
char = D2SParser(Path("MyChar.d2s")).parse()
type_db = get_item_type_db()

# -- Build inventory grid --
GRID_W, GRID_H = 10, 8  # Reimagined inventory size

for item in char.items:
    # char.items contains only ROOT items (no socket children) - no
    # skip filter is needed; render each item directly. Children of
    # socketed items are accessible via item.socket_children.
    if item.flags.location_id != LOCATION_STORED or item.flags.panel_id != 1:
        continue  # Only inventory items

    x, y = item.flags.position_x, item.flags.position_y
    w, h = type_db.get_inv_dimensions(item.item_code)
    invfile = type_db.get_inv_file(item.item_code) or ""
    tint = get_invtransform(item)

    # Load sprite PNG
    gfx = getattr(item, 'gfx_index', -1)
    png = resolver.get_sprite(item.item_code, gfx_index=gfx, invfile=invfile)

    print(f"Place {item.item_code} at ({x},{y}) size {w}x{h} tint={tint} sprite={'OK' if png else 'MISSING'}")
```

---

## Further reading

Topic-focused reference docs in this directory:

| Doc | Covers |
|---|---|
| `GAME_DATA_CACHE.md` | Persistent pickle cache backing every `load_*()`: `SourceVersions`, invalidation contract, atomic writes, benchmark table, env-var opt-out, verification matrix. |
| `UNIQUE_SPRITES.md` | Unique + set item sprite resolution: two name spaces (raw index vs localised display), snake-case normaliser, `load_unique_sprite_map_with_aliases`, end-to-end resolution contract, divergent-entry reference table. |
| `BULK_SPRITE_LOADER.md` | Splash-screen sprite preloader: all sprite keys in one `dict[str, bytes]`, phase layout, performance numbers, thread-safety notes. |
| `BULK_HEADER_PARSER.md` | Fast-path header-only parser for character-select screens. |
| `FORMATTED_PROPERTIES.md` | Structured property formatter: `FormattedSegment` / `FormattedProperty`, D2R colour-token table, CTC set-bonus chance/level encoding. |
| `SOCKET_LAYOUT.md` | Socket layout + fill-order tables for tooltip overlay rendering. |
| `PALETTE_TINTING.md` | Full D2-accurate palette tinting pipeline (indexed DC6 + colourmap). |
| `LOGGING_HYGIENE.md` | The library-logging convention: silent-by-default, opt-in helpers, hot-path guards. |
| `adapters/casc/README.md` + `adapters/casc/SPRITES.md` | CASC archive reader + SpA1 / DC6 sprite decoders (header-offset layout). |

Memory notes (`memory/`) persist the key findings for future
sessions - search `MEMORY.md` for topic keywords.

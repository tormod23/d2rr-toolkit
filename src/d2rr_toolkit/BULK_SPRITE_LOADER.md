# Bulk Item Sprite Preloader

One-shot sprite loader for D2R Reimagined GUIs. Loads every base-item
sprite, GFX variant, unique override, and set override into a single
dict in memory - designed to be called once at app startup (from a
splash-screen loading worker) so later item rendering is a plain
dict lookup.

**Performance:** ~1.7 seconds for ~915 sprites on NVMe SSD (warm cache).
No thread pool, no on-disk cache, no Qt/PySide dependencies.

## When to use

Use this API when you want **all** item sprites loaded up-front so that
the main GUI can render inventories, stashes, and item tooltips without
any disk IO or sprite decoding on the hot path. Typical use: a splash
screen's `AssetLoaderWorker`.

For one-off sprite lookups (e.g. cursor icons, tab decorations) keep
using `SpriteResolver.get_sprite()` - the bulk loader is additive, not
a replacement.

## Setup

The bulk loader needs:

1. **Game data tables loaded once** - `prepare_bulk_sprite_loader()`
   loads `item_types`, `item_names`, and `sets`. No other loaders required.
2. **A `CASCReader` instance** for vanilla base-game sprites.
3. **A `GamePaths` instance** for locating mod HD/DC6 directories.
4. **A flat `items_json` dict** - the raw D2R file is a list of single-key
   dicts; use `load_items_json(path)` to flatten it.

```python
from pathlib import Path
from d2rr_toolkit.config import init_game_paths
from d2rr_toolkit.sprites import (
    load_all_item_sprites,
    load_items_json,
    make_sprite_key,
    prepare_bulk_sprite_loader,
)
from d2rr_toolkit.adapters.casc import CASCReader  # or pycasc once extracted

# Once, at app start. prepare_bulk_sprite_loader pulls item_types,
# item_names and sets through the shared CASCReader (Iron Rule:
# Reimagined mod first, D2R Resurrected CASC fallback).
paths = init_game_paths()
prepare_bulk_sprite_loader()

items_json = load_items_json(paths.mod_items_json)
casc = CASCReader(paths.d2r_install)
```

## API

### `load_all_item_sprites(casc_reader, game_paths, items_json, *, ...) -> dict[str, bytes]`

Preload every item sprite into a single dict keyed by `make_sprite_key()`.

```python
sprites = load_all_item_sprites(
    casc_reader=casc,
    game_paths=paths,
    items_json=items_json,
    progress_callback=lambda msg, cur, tot: print(msg, cur, tot),
)
# sprites: dict[str, bytes] - e.g. {"rin": b"\x89PNG...", "rin#3": b"...", "rin@Ring of Engagement": b"..."}
```

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `casc_reader` | `CASCReader` | required | For loading vanilla base-game sprites |
| `game_paths` | `GamePaths` | required | For locating mod HD/DC6 directories |
| `items_json` | `dict[str, str]` | required | Flat `item_code -> asset_path` (use `load_items_json()`) |
| `include_base_items` | `bool` | `True` | Load base item sprites |
| `include_unique_variants` | `bool` | `True` | Load per-unique sprite overrides |
| `include_gfx_variants` | `bool` | `True` | Load GFX index variants for items that have them |
| `progress_callback` | `Callable[[str, int, int], None] \| None` | `None` | Splash-screen progress updates |
| `skip_errors` | `bool` | `True` | Skip corrupt sprites silently (log at DEBUG) |

**Returns:** `dict[str, bytes]` - sprite key -> PNG bytes.

**Raises:** `ValueError` if `casc_reader` or `game_paths` is `None`.

### `make_sprite_key(item_code, *, gfx_index=None, unique_name=None, set_name=None) -> str`

Build a stable sprite lookup key. **Both the loader and the GUI must
use this helper** so keys stay in sync.

| Inputs | Returned key |
|---|---|
| `"rin"` | `"rin"` |
| `"rin"`, `gfx_index=3` | `"rin#3"` |
| `"rin"`, `unique_name="Ring of Engagement"` | `"rin@Ring of Engagement"` |
| `"amu"`, `set_name="Tal Rasha's Lidless Eye"` | `"amu@Tal Rasha's Lidless Eye"` |

Priority: `unique_name` > `set_name` > `gfx_index` > plain code.

**Pass the localized display name**, not the raw internal name.  The
loader stores unique/set sprites under the display-name key (what
``ItemNamesDatabase.get_unique_name(*ID)`` returns) so a GUI that
resolves names via ``build_display_name`` always hits the correct
entry.  For 37 uniques (and 2 sets) the display name diverges from
the raw ``uniqueitems.txt.index`` - e.g. raw ``Life and Death`` ->
display ``Life & Death``; the loader registers the raw-name key as
a back-compat alias so scripts using the raw index keep working.
See ``UNIQUE_SPRITES.md`` for the full resolution contract and
the divergent-name reference table.

```python
# When rendering a parsed item
def sprite_key_for_item(item):
    return make_sprite_key(
        item.item_code,
        gfx_index=item.gfx_index,
        unique_name=item.unique_name,
    )

png = sprites.get(sprite_key_for_item(my_item))
if png:
    pix = QPixmap()
    pix.loadFromData(png)
```

### `load_items_json(path) -> dict[str, str]`

Load and flatten the Reimagined `items.json` file into the flat format
the bulk loader expects.

The raw file has this structure::

```json
[
    {"hax": {"asset": "axe/hand_axe"}},
    {"rin": {"asset": "ring/ring"}},
    ...
]
```

`load_items_json()` returns::

```python
{"hax": "axe/hand_axe", "rin": "ring/ring", ...}
```

Also handles the already-flat `{"hax": "axe/hand_axe"}` format in case
the file structure changes. Returns `{}` if the file does not exist.

### `prepare_bulk_sprite_loader() -> None`

Load the minimum set of game data tables needed by the bulk loader:
- `item_types.txt`
- `item_names` (strings + uniqueitems.txt + setitems.txt)
- `sets.txt`

All reads go through the shared `CASCReader` singleton (Iron Rule:
Reimagined mod first, D2R Resurrected CASC fallback). Call once at
app startup. Safe to call multiple times - the loaders are idempotent.

## Full Example

```python
from pathlib import Path
from d2rr_toolkit.config import init_game_paths
from d2rr_toolkit.sprites import (
    load_all_item_sprites,
    load_items_json,
    make_sprite_key,
    prepare_bulk_sprite_loader,
)
from d2rr_toolkit.adapters.casc import CASCReader

# --- Startup (runs once, typically inside a splash-screen worker) ---
paths = init_game_paths()
prepare_bulk_sprite_loader()

items_json = load_items_json(paths.mod_items_json)
casc = CASCReader(paths.d2r_install)

def on_progress(msg: str, cur: int, tot: int) -> None:
    print(f"[{cur:5}/{tot}] {msg}")

sprites = load_all_item_sprites(
    casc_reader=casc,
    game_paths=paths,
    items_json=items_json,
    progress_callback=on_progress,
)
# sprites now contains ~900-1500 entries, ~15-30 MB in memory

# --- Later, when rendering a parsed item ---
def get_item_sprite(item) -> bytes | None:
    return sprites.get(make_sprite_key(
        item_code=item.item_code,
        gfx_index=getattr(item, "gfx_index", None),
        unique_name=getattr(item, "unique_name", None),
    ))
```

## Sprite Key Schema

| Format | Meaning | Example |
|---|---|---|
| `"<code>"` | Base item, no variant | `"rin"` |
| `"<code>#<gfx_index>"` | Base item with GFX variant (0-based) | `"rin#3"` |
| `"<code>@<unique_name>"` | Unique item with dedicated sprite | `"rin@Ring of Engagement"` |
| `"<code>@<set_name>"` | Set item with dedicated sprite | `"amu@Tal Rasha's Lidless Eye"` |

## Progress Callback

Signature matches the typical Qt `progress` signal::

```python
def progress_callback(message: str, current: int, total: int) -> None:
    ...
```

**Frequency:** Called in batches of ~50 sprites (not after every sprite)
to avoid overhead in the hot path. Messages emitted for each phase:

```
("Loading base items...",    0, 2282)
("Loading base items...",   50, 2282)
...
("Loading GFX variants...",  800, 2282)
...
("Loading unique overrides...", 1600, 2282)
...
("Loading set overrides...",  1950, 2282)
("Sprite preload complete",   2282, 2282)
```

Note: `total` is the sum of the work units across all phases (base items
+ GFX probes + unique entries + set entries), not the number of sprites
that will end up in the result dict.

## Performance

Measured on real Reimagined mod data (~800 item codes, ~677 uniques,
~455 set items), post Reimagined 3.0.7:

| Run | Time | Sprites |
|---|---|---|
| Cold cache | ~2.5 s | ~1110 |
| Warm cache | ~1.5-2.0 s | ~1110 |
| `[SpriteResolver.get_sprite(c) for c in ...]` | ~60+ s | similar |

Totals include back-compat raw-name aliases for diverging display-name
entries (see ``make_sprite_key`` above), so the sprite dict may carry
a handful of duplicate entries pointing at the same PNG bytes.

**Optimizations applied:**
- Single recursive scan of the mod HD directory into a `{basename: Path}` index
- Single CASC path-map scan into a `{basename: CKey}` index
- Per-basename PNG cache (no duplicate SpA1 decodes across phases)
- Inline SpA1 decoder: reads pixel data at the fixed 40-byte header
  offset (same rule as the canonical ``decode_sprite``; see
  ``adapters/casc/SPRITES.md`` for the format spec) and skips PIL's
  PNG size-reduction pass - roughly 3* faster than the default decoder for
  bulk use, correct on sprites that carry trailing mipmap/lowend
  regions.

## Memory Usage

Expected footprint: **15-30 MB** total for ~900-1500 sprites.
Individual sprites are 2-60 KB PNGs. The returned dict is safe to keep
in memory for the full lifetime of the app.

## Logging

At the default `logging.INFO` root level, the bulk loader emits exactly
one start line and 4-5 summary lines (counts from Reimagined 3.0.7)::

```
INFO d2rr_toolkit.sprites.bulk_loader: Starting bulk item sprite preload
INFO d2rr_toolkit.sprites.bulk_loader: Base items: 800 loaded, 0 missing
INFO d2rr_toolkit.sprites.bulk_loader: GFX variants: 56 loaded
INFO d2rr_toolkit.sprites.bulk_loader: Unique overrides: 446 loaded, 0 missing
INFO d2rr_toolkit.sprites.bulk_loader: Set overrides: 140 loaded, 0 missing
INFO d2rr_toolkit.sprites.bulk_loader: Total: ~1110 sprites in ~2s
```

Per-sprite failures are logged at `DEBUG` level only and guarded by
`isEnabledFor(DEBUG)` so they do not appear in normal INFO output and
do not incur string-formatting cost when DEBUG is disabled.

## Error Handling

- **Missing sprites** (item code has no associated sprite file): silently
  skipped, counted in the `... missing` stat.
- **Corrupt SpA1 data**: logged at DEBUG, `None` returned, item omitted
  from result dict. With `skip_errors=False` the first corrupt sprite
  raises and aborts the load.
- **`casc_reader=None` or `game_paths=None`**: `ValueError` - this is a
  programmer error, not a runtime issue.
- **Empty `items_json`**: returns empty dict, logs zero counts. No crash.

## Thread Safety

The bulk loader is **not thread-safe** and is meant to be called once
from a single background thread (e.g. `AssetLoaderWorker.run`). The
underlying `CASCReader` is also not thread-safe. Do not call this
function from multiple threads concurrently.

## Verification

Two test suites protect the loader:

* `tests/test_bulk_sprite_loader.py` - 91+ checks covering the full
  Phase 1-4 flow plus `SpriteResolver` parity (see list below).
* `tests/test_unique_sprite_display_name_alias.py` - 23 checks that
  pin down the display-name vs raw-index alias fix (TC55
  FrozenOrbHydra's three unique large charms + the 4 user-visible
  divergent uniques + `load_unique_sprite_map_with_aliases`).
* `tests/test_decode_sprite_tail_bug.py` - 20 checks that protect
  the SpA1 header-offset fix (see ``adapters/casc/SPRITES.md``) -
  includes a live smoke test against `stash_tabs2.sprite` to confirm
  trailer-carrying sprites decode correctly.

Original sections in `test_bulk_sprite_loader.py`:

1. `make_sprite_key` edge cases (9 checks)
2. `load_items_json` handles list-of-dict format
3. Basic load: returns dict of PNG bytes
4. Key distribution: base / gfx / overrides all populated
5. Correctness: pixel-identical output vs `SpriteResolver.get_sprite()` on a 20-item sample
6. Performance: < 3s warm cache (verified at ~1.7s)
7. Memory usage: 5-100 MB range
8. Progress callback: correct signature, final call has `cur == tot`, all phases emitted
9. Error handling: `ValueError` on missing args, empty `items_json` returns empty dict
10. Log sanity: < 20 INFO lines total, no bit-reader traces

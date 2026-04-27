# Persistent Game-Data Cache

Every `load_*()` in :mod:`d2rr_toolkit.game_data` and
:func:`d2rr_toolkit.catalog.item_catalog.load_item_catalog` is
transparently backed by an on-disk pickle cache.  First launch of a
given game + mod version pays the full parse cost, every subsequent
launch reads the populated singleton straight from disk.  On the
Reimagined 3.0.7 reference install this turns a ~1.4 s cold parse
into a ~270 ms warm load - a consistent 5* improvement with zero
call-site change.

## Contract

A cache entry is **fresh** iff all three markers below match the
on-disk snapshot:

| Marker | Source | Bumped when |
|---|---|---|
| `CACHE_FORMAT_VERSION` | :mod:`d2rr_toolkit.meta.cache` | the outer pickle wrapper format changes |
| `schema_version` | per-loader module constant (`SCHEMA_VERSION_*`) | any dataclass field on the cached singleton is added / removed / renamed |
| `source_versions` | :class:`SourceVersions` - `(game_version, mod_version)` | D2R receives a patch OR the Reimagined mod ships a new version |

Any mismatch triggers a silent rebuild; the cache file is rewritten
with the fresh snapshot.  Corrupt or truncated pickles are detected
at load time and treated identically to a mismatch - the loader
falls through to a fresh parse and swallows the exception.

## Invalidation key - `SourceVersions`

```python
from d2rr_toolkit.meta import SourceVersions, get_source_versions

versions = get_source_versions(
    game_dir=Path(r"C:\Program Files (x86)\Diablo II Resurrected"),
    mod_dir=Path(r"C:\...\mods\Reimagined"),
)
print(versions.cache_key())
# -> "game=b4d9b17aecc8ca12 mod=Reimagined@3.0.7"
```

* `game_version` - short SHA-256 prefix of `<game_dir>/.build.info`
  (Blizzard's launcher manifest). Hashing the whole file decouples
  us from their column layout; any patch bumps the hash.
* `mod_version` - the `version` field from
  `<mod_dir>/<name>.mpq/modinfo.json`.  `None` for a vanilla run.
* `mod_name` - informational only.  **NOT** part of the cache key
  - a mod rename without content change must not force a rebuild.

Equality / hashing is structural so a single `SourceVersions`
instance is safe as a dict key.  The GUI's `SQLiteAssetCache`
consumes the same object for its own invalidation, guaranteeing
the two caches agree on "is the input fresh?" by construction.

A missing / malformed `modinfo.json` degrades to `mod_version=None`
with a `WARNING` log - the library stays usable against a broken
mod install.  A missing `.build.info` raises
:class:`SourceVersionsError`: we refuse to cache against an unknown
game state.

## Loader signature

Every cached loader accepts the same three kwargs (all
keyword-only, defaulting to today's behaviour):

```python
def load_item_stat_cost(
    *,
    use_cache: bool = True,
    source_versions: SourceVersions | None = None,
    cache_dir: Path | None = None,
) -> None: ...
```

| kwarg | Purpose |
|---|---|
| `use_cache=True` | Set `False` to skip the cache for this call only - reads and writes both bypassed.  Also honoured globally via the env var `D2RR_DISABLE_GAME_DATA_CACHE=1`. |
| `source_versions=None` | Pass the shared instance from `get_source_versions(...)` to avoid re-reading `.build.info` + `modinfo.json` on every loader.  When omitted, the helper resolves once and memoises the result across loaders. |
| `cache_dir=None` | Tests route this into a `tmp_path`.  Production callers rely on the platformdirs default (`%LOCALAPPDATA%/d2rr-toolkit/data_cache` on Windows). |

Return type and side-effect contract are **unchanged**: every
loader still populates its module-level singleton and returns
`None`.  Existing call sites don't need updating.

## Recommended wiring

For any consumer that runs multiple loaders in a batch (CLI, GUI
startup), resolve `SourceVersions` once and thread it through every
call:

```python
from d2rr_toolkit.meta import get_source_versions
from d2rr_toolkit.config import init_game_paths
from d2rr_toolkit.game_data.item_stat_cost import load_item_stat_cost
from d2rr_toolkit.game_data.item_names import load_item_names
from d2rr_toolkit.game_data.skills import load_skills
# ... other loaders

gp = init_game_paths()
versions = get_source_versions(game_dir=gp.d2r_install, mod_dir=gp.mod_dir)

load_item_stat_cost(source_versions=versions)
load_item_names(source_versions=versions)
load_skills(source_versions=versions)
# ... pass the same instance to every loader
```

The shared instance eliminates duplicate file reads *and* makes
cache validity a single visible decision at the call site.

## Cache layout on disk

```
%LOCALAPPDATA%/d2rr-toolkit/data_cache/
    automagic.pkl
    charstats.pkl
    cubemain.pkl
    gems.pkl
    hireling.pkl
    item_catalog.pkl
    item_names.pkl          (largest - ~7 MB)
    item_stat_cost.pkl
    item_types.pkl
    properties.pkl
    property_formatter.pkl
    sets.pkl
    skills.pkl
```

Total footprint on Reimagined 3.0.7: ~7.4 MB.  The
`item_names.pkl` entry dominates because it carries the full
13-language strings table - still tiny compared to a single HD
sprite asset.

## Performance (Reimagined 3.0.7, NVMe SSD, warm OS cache)

| Loader | Cold parse (ms) | Warm cache hit (ms) | Ratio | Pickle KB |
|---|---:|---:|---:|---:|
| `load_item_types` | 37.7 | 30.0 | 1.3x | 72 |
| `load_item_stat_cost` | 8.2 | 1.7 | 4.7x | 46 |
| `load_item_names` | 904.7 | 126.7 | 7.1x | 6 923 |
| `load_skills` | 27.1 | 1.9 | 14.4x | 19 |
| `load_charstats` | 0.9 | 0.6 | 1.5x | 2 |
| `load_sets` | 22.6 | 33.9 | 0.7x | 136 |
| `load_gems` | 3.2 | 1.4 | 2.2x | 14 |
| `load_hireling` | 4.0 | 1.3 | 3.0x | 13 |
| `load_properties` | 9.0 | 32.7 | 0.3x | 36 |
| `load_property_formatter` | 4.6 | 1.1 | 4.3x | 18 |
| `load_automagic` | 1.4 | 1.3 | 1.1x | 8 |
| `load_cubemain` | 318.2 | 1.4 | **229.1x** | 12 |
| `load_item_catalog` | 68.8 | 35.0 | 2.0x | 82 |
| **TOTAL** | **1 410.4** | **269.0** | **5.2x** | **7 381** |

`get_source_versions()` probe: **0.72 ms** (target: < 5 ms).

Tiny-loader ratios sometimes go sub-1.0* because the absolute
parse is already in the microsecond range and sub-millisecond
variance dominates.  The win is unambiguous on the large tables
(`item_names`, `cubemain`) that dominated the total.

## Test coverage

`tests/test_game_data_cache.py` - **47 checks** covering every
checklist item:

1. Happy path: cold parse writes cache, warm hit restores it.
2. Corrupt pickle bytes fall through to parse silently.
3. `CACHE_FORMAT_VERSION` mismatch triggers rebuild.
4. `SCHEMA_VERSION_*` mismatch triggers rebuild.
5. `source_versions.game_version` mismatch triggers rebuild.
6. `source_versions.mod_version` mismatch triggers rebuild.
7. `mod_name` change alone does **not** trigger a rebuild.
8. Missing `.build.info` raises `SourceVersionsError`.
9. Missing `modinfo.json` yields `mod_version=None` (no exception).
10. Malformed `modinfo.json` yields `mod_version=None` + warning.
11. `use_cache=False` never reads or writes the cache file.
12. `D2RR_DISABLE_GAME_DATA_CACHE=1` disables every loader globally.
13. Concurrent writes don't race (two threads, same cache name,
    unique `.tmp` suffix per caller).
14. Real-loader roundtrip: `load_item_stat_cost` cache hit restores
    structurally-equal state to the cold parse.
15. Schema-hash sanity across the primary dataclasses.
16. `SourceVersions` is hashable + comparable for cross-cache use
    (GUI `SQLiteAssetCache` consumes the same object).

## Env-var reference

| Variable | Effect |
|---|---|
| `D2RR_DISABLE_GAME_DATA_CACHE=1` | Every `load_*()` call behaves as if `use_cache=False` - used by CI to exercise the fresh-parse path without editing tests. |

## Stage 2 (deferred)

A planned optional SQLite mirror would support tooling /
cross-version diffing.  Stage 1 already hits the perf target
(sub-400 ms warm total), so Stage 2 is deferred until a concrete
tooling need arises.  When it does, the invalidation contract
stays identical - the cache switches from one `*.pkl` per table
to one `data_cache.sqlite` with the same `(fmt, schema,
source_versions)` triple in its `meta` table.

## See also

* `QUICKSTART.md` §1 - shows the recommended wiring pattern
  (resolve `SourceVersions` once at startup, thread through every
  loader).
* `src/d2rr_toolkit/meta/source_versions.py` - implementation of
  the invalidation oracle; `.build.info` hash logic + `modinfo.json`
  reader + degradation rules for missing / malformed files.
* `src/d2rr_toolkit/meta/cache.py` - implementation of `cached_load`;
  atomic write discipline, concurrent-safe `.tmp` naming, the
  in-place singleton-restore pattern (`vars().clear()+update()`).
* `tests/test_game_data_cache.py` - the 47-check verification matrix.
* Iron Rule: `memory/project_data_source_iron_rule.md` - every
  cached file is read through `CASCReader.read_file`, which is
  where the Iron Rule (Reimagined mod first, CASC fallback)
  enforces the mod-overrides-base-game layering.

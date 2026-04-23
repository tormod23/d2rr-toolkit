# Bulk Character Header Parser

Fast-path API for character-select screens. Reads only the header bytes
(~833 bytes) of each `.d2s` file and decodes just the `CharacterHeader`
fields - no Stats, Skills, Items, Mercenary, or Corpse sections are
touched. Typical parse time: **<10 ms for 50 files** on an NVMe SSD.

## When to use

Use this API when you only need the header information (name, class,
level, title, HC/SC status, progression) for a **list view** of
characters - e.g. the character-select screen of a GUI tool.

For the full parse (items, stats, skills) use `D2SParser(path).parse()`
instead.

## Setup

Only one game data table needs to be loaded: `charstats.txt`. No item,
name, skill, or property databases are required.

```python
from d2rr_toolkit.config import init_game_paths
from d2rr_toolkit.game_data.charstats import load_charstats

init_game_paths(
    d2r_install=Path(r"C:\Program Files (x86)\Diablo II Resurrected"),
    mod_dir=Path(r"C:\Program Files (x86)\Diablo II Resurrected\mods\Reimagined"),
)
# load_charstats resolves charstats.txt via the shared CASCReader -
# Reimagined mod install first, D2R Resurrected CASC as fallback.
load_charstats()
```

After this you can call both bulk APIs. **No other loaders are needed.**

## API

### `parse_character_headers(save_dir, *, pattern="*.d2s", skip_errors=True)`

Parse every matching `.d2s` file in a directory. Returns a list of
`CharacterHeader` objects sorted by filename.

```python
from d2rr_toolkit.parsers.d2s_parser import parse_character_headers

headers = parse_character_headers(r"C:\Users\me\Saved Games\Diablo II Resurrected")

for h in headers:
    mode = "HC" if h.is_hardcore else "SC"
    mark = " (DEAD)" if h.is_dead else ""
    title = f" the {h.title}" if h.title else ""
    print(f"{h.character_name}{title} - Lvl {h.level} {h.character_class_name} [{mode}]{mark}")
    print(f"  source: {h.source_path}")
```

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `save_dir` | `Path \| str` | required | Directory to scan |
| `pattern` | `str` | `"*.d2s"` | Glob pattern for files to include |
| `skip_errors` | `bool` | `True` | If `True`, corrupt files are logged and skipped. If `False`, the first parse error is raised as `RuntimeError` (original exception as `__cause__`). |

**Returns:** `list[CharacterHeader]` sorted by filename.

**Raises:**
- `NotADirectoryError` if `save_dir` is not a directory.
- `RuntimeError` (with original exception as `__cause__`) on first parse failure when `skip_errors=False`.

### `parse_character_header(path)`

Parse a single `.d2s` file's header. Useful if you're iterating yourself
or need just one specific character.

```python
from d2rr_toolkit.parsers.d2s_parser import parse_character_header

h = parse_character_header(r"C:\Users\me\Saved Games\...\MyChar.d2s")
print(f"{h.character_name}: Level {h.level} {h.character_class_name}")
```

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `path` | `Path \| str` | Path to the `.d2s` file |

**Returns:** `CharacterHeader` with all fields populated, including `source_path`.

**Raises:** `FileNotFoundError`, `InvalidSignatureError`, `UnsupportedVersionError`, `SpecVerificationError`.

## CharacterHeader fields

All fields on a `CharacterHeader` returned by the bulk parser:

### Stored fields

| Field | Type | Description |
|---|---|---|
| `version` | `int` | D2S version (105 for D2R Reimagined) |
| `file_size` | `int` | Total file size in bytes |
| `checksum` | `int` | D2S file checksum |
| `character_name` | `str` | In-game character name |
| `character_class` | `int` | Class ID (0-7) |
| `character_class_name` | `str` | Human-readable class name |
| `level` | `int` | Character level (1-100) |
| `status_byte` | `int` | Raw status byte at file offset 0x14 |
| `is_hardcore` | `bool` | Hardcore character |
| `died_flag` | `bool` | Raw died bit - **use `is_dead` instead** |
| `is_expansion` | `bool` | Always `True` in D2R v105 |
| `progression` | `int` | 0-15, difficulty completion |
| `source_path` | `Path \| None` | Path to source file (set automatically) |

### Computed properties

| Property | Type | Description |
|---|---|---|
| `is_dead` | `bool` | `True` only if `is_hardcore AND died_flag` (HC permanently dead) |
| `highest_difficulty_completed` | `int` | `0`=none, `1`=Normal, `2`=Nightmare, `3`=Hell |
| `gender` | `"male" \| "female"` | Derived from class ID |
| `title` | `str` | `"Slayer"`/`"Champion"`/`"Patriarch"`/`"Matriarch"` (SC) or `"Destroyer"`/`"Conqueror"`/`"Guardian"` (HC) |

## Important: `is_dead` vs `died_flag`

Use **`is_dead`** for display, not `died_flag`.

- `died_flag` is the raw bit from the file and is **also set** for Softcore
  characters who have died at some point (they respawned and can still
  be played - they just "have a death" in their history).
- `is_dead` is `True` only when the character is Hardcore **and** the died
  flag is set - i.e. the character is permanently dead and cannot be played.

```python
# [OK] Correct
if h.is_dead:
    render_greyed_out()

# [NO] Wrong - would mark SC chars that died once as "dead"
if h.died_flag:
    render_greyed_out()
```

## Gender -> Title Mapping

| Class ID | Class | Gender | SC Title (prog=15) |
|---|---|---|---|
| 0 | Amazon | female | Matriarch |
| 1 | Sorceress | female | Matriarch |
| 2 | Necromancer | male | Patriarch |
| 3 | Paladin | male | Patriarch |
| 4 | Barbarian | male | Patriarch |
| 5 | Druid | male | Patriarch |
| 6 | Assassin | female | Matriarch |
| 7 | Warlock (Reimagined) | male | Patriarch |

## Full Title Mapping

### Softcore

| `progression` | Highest difficulty | Title |
|---|---|---|
| 0-4 | none | `""` (empty) |
| 5-9 | Normal | `"Slayer"` |
| 10-14 | Nightmare | `"Champion"` |
| 15 | Hell | `"Patriarch"` (male) / `"Matriarch"` (female) |

### Hardcore (gender-neutral)

| `progression` | Highest difficulty | Title |
|---|---|---|
| 0-4 | none | `""` (empty) |
| 5-9 | Normal | `"Destroyer"` |
| 10-14 | Nightmare | `"Conqueror"` |
| 15 | Hell | `"Guardian"` |

## Performance characteristics

Measured with 50 real D2S files on NVMe SSD:

| Method | Time | Relative |
|---|---|---|
| `parse_character_headers(dir)` | ~8 ms | **1*** (baseline) |
| `[D2SParser(f).parse() for f in files]` | ~430 ms | ~50* slower |

The bulk parser:
- Reads only the first ~833 bytes per file (no full file read)
- Does not instantiate a `BitReader`
- Does not touch the Stats/Skills/Items/Merc/Corpse sections
- Does not require item/name/skill/property databases to be loaded
- Does not emit per-bit trace logs (bit-reader logging is guarded behind `isEnabledFor(DEBUG)`)

## Logging

At the default `logging.INFO` root level, `parse_character_headers()`
emits exactly two messages:

```
INFO d2rr_toolkit.parsers.d2s_parser: Parsed N character header(s) from DIR
```

(plus any `WARNING`-level messages for skipped corrupt files).

No bit-reader or per-item traces leak into the log. This was a previous
issue - the `BitReader.read()` method now guards its `logger.debug()`
call with `isEnabledFor(DEBUG)` so that INFO-level applications see a
clean log.

## Example: Full character-select screen data

```python
from pathlib import Path
from d2rr_toolkit.config import init_game_paths
from d2rr_toolkit.game_data.charstats import load_charstats
from d2rr_toolkit.parsers.d2s_parser import parse_character_headers

# One-time setup
init_game_paths()
load_charstats()

# Bulk parse (~10 ms for 50 files)
save_dir = Path(r"C:\Users\me\Saved Games\Diablo II Resurrected")
headers = parse_character_headers(save_dir)

# Build GUI rows
rows = []
for h in headers:
    rows.append({
        "path": str(h.source_path),
        "name": h.character_name,
        "title": h.title,
        "level": h.level,
        "class": h.character_class_name,
        "class_id": h.character_class,       # for class-icon lookup
        "gender": h.gender,                  # "male" or "female"
        "mode": "Hardcore" if h.is_hardcore else "Softcore",
        "is_dead": h.is_dead,                # greyed-out rendering
        "progression": h.progression,        # 0..15
        "difficulty_completed": h.highest_difficulty_completed,  # 0..3
    })

# Sort e.g. by level descending
rows.sort(key=lambda r: -r["level"])
```

## Verification

All 122 test checks in `tests/test_bulk_header_parser.py` pass, covering:

1. Correctness - every header field matches `D2SParser.parse().header`
2. `source_path` field populated correctly in both bulk and full parser
3. Directory scan + glob pattern filtering
4. `skip_errors=True` - corrupt files logged and omitted
5. `skip_errors=False` - raises `RuntimeError` with file path
6. Performance - <100 ms for 50 files, >20* faster than full parse
7. No bit-reader traces in INFO log
8. Works with only `charstats.txt` loaded (no item DBs needed)


# d2rr_toolkit.casc -- CASC Archive Reader

Pure-Python reader for Blizzard CASC (Content Addressable Storage Container)
archives, specifically tested with Diablo II Resurrected. Implements the core
algorithms from [CascLib](https://github.com/ladislav-zezula/CascLib) without
any native/C dependencies.

## Package Structure

```
d2rr_toolkit/casc/
    __init__.py       Re-exports CASCReader
    reader.py         Main CASCReader class (public API)
    sprites.py        SpA1 + DC6 sprite decoders (PNG/WebP output)
    _blte.py          BLTE decompression (zlib + raw frames)
    _buildinfo.py     .build.info + build config parsing
    _encoding.py      ENCODING manifest (CKey -> EKey mapping)
    _index.py         Index file (.idx) parsing (EKey -> archive location)
    _tvfs.py          TVFS root parsing (file path -> CKey mapping)
```

## Dependencies

- **Python 3.14+** (uses `X | Y` union syntax, PEP 695 `type` aliases, PEP 649 deferred annotations)
- **Standard library only** for the CASC reader itself (pathlib, struct, zlib, csv, fnmatch)
- **Pillow** (optional) -- required only for `casc.sprites` (sprite-to-image conversion)

## Quick Start

```python
from pathlib import Path
from d2rr_toolkit.adapters.casc import CASCReader
from d2rr_toolkit.adapters.casc.sprites import decode_sprite

# Open the D2R CASC archive
reader = CASCReader(Path(r"C:\Program Files (x86)\Diablo II Resurrected"))

# Read a game data file
weapons_tsv = reader.read_file("data:data/global/excel/weapons.txt")

# Read and convert a sprite to PNG
raw = reader.read_file("data:data/hd/global/ui/items/misc/ring/ring.sprite")
png_bytes = decode_sprite(raw)
Path("ring.png").write_bytes(png_bytes)

# Export as WebP instead
webp_bytes = decode_sprite(raw, format="webp")

# List all item sprites in the archive
for path in reader.list_files("data:data/hd/global/ui/items/*/*.sprite"):
    print(path)
```

## How CASC Works

CASC uses a multi-level indirection to locate files:

```
file_path  --[TVFS root]-->  CKey  --[ENCODING]-->  EKey  --[Index]-->  archive location
                                                                              |
                                                        data.### file  <------+
                                                              |
                                                        BLTE decompress
                                                              |
                                                        file content
```

**Key concepts:**

| Term | Size | Description |
|------|------|-------------|
| CKey | 16 bytes | Content Key -- MD5 hash of the uncompressed file content |
| EKey | 16 bytes | Encoded Key -- MD5 hash of the BLTE-encoded (compressed) content |
| TVFS | variable | Table Virtual File System -- maps human-readable paths to CKeys |
| BLTE | variable | Block Table Encoding -- compression wrapper (zlib or raw frames) |

### Loading Pipeline (5 steps, all automatic on construction)

1. **`.build.info`** -- CSV file in the game root; identifies the active build
   and provides the Build Key (a hex string that locates the build config).

2. **Build Config** -- INI-style file at `Data/config/{bk[:2]}/{bk[2:4]}/{bk}`;
   contains the ENCODING keys and VFS root entry keys.

3. **Index Files (.idx)** -- 16 buckets (00-0F) in `Data/data/`; each maps
   9-byte EKey prefixes to (archive_index, offset, size) triples. Supports
   Index V1 (version 0x05) and V2 (version 0x07).

4. **ENCODING Manifest** -- Maps CKeys to EKeys. Read via the EKey from step 2.
   After this step, a reverse EKey-to-CKey map is built for O(1) TVFS resolution.

5. **TVFS Root** -- Binary prefix tree (trie) mapping file paths to CKeys.
   Hierarchical: the root manifest references sub-VFS files (vfs-1, vfs-2, ...)
   which contain the actual file entries. Sub-VFS paths are prefixed with the
   parent path and a colon (e.g., `data:data/global/excel/weapons.txt`).

### TVFS Path Table Format

The TVFS path table is a serialized prefix tree. Each entry follows this pattern:

```
[optional 0x00 pre-separator]
[length byte + name fragment bytes]
[optional 0x00 post-separator OR implicit separator]
[0xFF + 4-byte node value]
```

**Node values:**
- Bit 31 set (`0x80000000`): Folder node; lower 31 bits = child data size. Recurse.
- Bit 31 clear: File leaf; value = offset into VFS table. Resolve via VFS -> CFT -> EKey.

**Path buffer save/restore:** The path accumulator is saved once at each recursion
level (not per entry) and restored after processing each `0xFF` node. This matches
CascLib's `PathBuffer.Save()`/`Restore()` algorithm.

### BLTE Decompression

BLTE data in archive files is prefixed with a 0x1E-byte header. The BLTE stream
itself starts with the magic `BLTE`, followed by a 4-byte header size:

- **header_size = 0**: Single frame -- the rest of the data is one frame.
- **header_size > 0**: Multi-frame -- a frame table follows with (encoded_size,
  content_size, hash) per frame, then the concatenated frame data.

Each frame has a 1-byte encoding prefix:
- `N` -- raw (no compression)
- `Z` -- zlib compressed
- `E` -- encrypted (not supported; returns None)

---

## API Reference: CASCReader

### Constructor

```python
CASCReader(game_dir: Path, mod_dir: Path | None = None)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `game_dir` | `Path` | **Required.** D2R installation root (must contain `.build.info`). |
| `mod_dir` | `Path \| None` | Optional mod overlay directory. When set, `read_file()` and `has_file()` check this directory first; files on disk override CASC. |

**Raises:** `FileNotFoundError` if `.build.info` or the build config is missing.

**Initialization time:** ~3-5 seconds (parses index files, encoding manifest, and
~175,000 TVFS paths). The reader is fully initialized after construction.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `file_count` | `int` | Number of indexed file paths in the CASC archive. |
| `game_dir` | `Path` | D2R installation root path (as passed to constructor). |
| `mod_dir` | `Path \| None` | Mod overlay directory, or `None` if not configured. |

### File Access Methods

#### `read_file(path: str) -> bytes | None`

Read a file by its CASC path. Returns the decompressed file content, or `None`
if the path is not found.

**Mod overlay behavior:** If `mod_dir` is set, the method first checks for the
file on disk by stripping the sub-VFS prefix (e.g., `data:`) and joining the
remainder with `mod_dir`. If found on disk, returns the disk file content.
Otherwise falls back to the CASC archive.

```python
# Read a game data file
data = reader.read_file("data:data/global/excel/weapons.txt")

# Read an HD sprite (returns raw SpA1 bytes, not an image)
sprite_raw = reader.read_file("data:data/hd/global/ui/items/misc/ring/ring.sprite")
```

#### `read_by_ckey(ckey: bytes) -> bytes | None`

Read a file by its 16-byte content key. No mod overlay -- CKeys are
CASC-specific. Useful when you already have the CKey from `resolve_ckey()`.

```python
ckey = reader.resolve_ckey("data:data/global/excel/weapons.txt")
data = reader.read_by_ckey(ckey)
```

#### `has_file(path: str) -> bool`

Check whether a file exists. Checks mod overlay first (if configured),
then the CASC archive.

```python
if reader.has_file("data:data/global/excel/weapons.txt"):
    print("File exists")
```

### File Discovery Methods

#### `list_files(pattern: str = "*") -> list[str]`

List all CASC file paths matching a glob pattern. Returns a sorted list.

Uses `fnmatch`-style patterns: `*` matches any characters (including `/`),
`?` matches a single character, `[seq]` matches a character set. Use `**`
for recursive matching (converted to `*` internally since `fnmatch`'s `*`
already matches path separators).

```python
# All files in the archive (~175,000)
all_files = reader.list_files("*")

# All HD item sprites
sprites = reader.list_files("data:data/hd/global/ui/items/*/*.sprite")

# All game data Excel files
excel = reader.list_files("data:data/global/excel/*.txt")

# All sound files
sounds = reader.list_files("data:data/hd/global/sfx/*/*.ogg")

# Font files
fonts = reader.list_files("data:data/hd/ui/fonts/*")
```

#### `resolve_ckey(path: str) -> bytes | None`

Return the 16-byte content key for a path without reading the file.
Useful for caching, deduplication, or when you need to read the same
file multiple times efficiently.

```python
ckey = reader.resolve_ckey("data:data/global/excel/weapons.txt")
# ckey is 16 bytes (MD5 of uncompressed content), or None if not found
```

---

## CASC Path Format

Paths in the CASC archive use forward slashes and may have a sub-VFS prefix:

```
data:data/hd/global/ui/items/armor/armor/quilted_armor.sprite
^^^^                                                          sub-VFS prefix
     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^     relative path
```

**Sub-VFS prefix:** Most game files are in sub-VFS directories. The prefix
(e.g., `data:`) indicates which VFS subtree the file belongs to. The colon
separates the VFS name from the file path within it.

**Top-level paths** (no prefix) exist for a few files like `index` and
`binaries/releaseanticheat/x86_64/d2r.exe`.

### Common Path Patterns (D2R)

| Category | Pattern | Example |
|----------|---------|---------|
| Game data (Excel) | `data:data/global/excel/{name}.txt` | `data:data/global/excel/weapons.txt` |
| HD sprites | `data:data/hd/global/ui/items/{cat}/{sub}/{name}.sprite` | `data:data/hd/global/ui/items/misc/ring/ring.sprite` |
| UI panels | `data:data/hd/global/ui/panel/{name}.sprite` | `data:data/hd/global/ui/panel/gemsocket.sprite` |
| Fonts | `data:data/hd/ui/fonts/{name}` | `data:data/hd/ui/fonts/exocetblizzardot-medium.otf` |
| Localized | `data:locales/data/{locale}/...` | `data:locales/data/plpl/data/local/font/latin/fontedit.fnt` |
| Sounds | `data:data/hd/global/sfx/...` | Sound effects and music |

---

## Mod Overlay

When `mod_dir` is provided, `read_file()` and `has_file()` check for files
on disk before falling back to the CASC archive. This supports the D2R modding
pattern where mods override base game files by placing them in a directory.

**Path resolution:** The CASC path is converted to a local path by:
1. Stripping the sub-VFS prefix (everything before and including `:`)
2. Replacing `/` with the OS path separator
3. Joining with `mod_dir`

Example: `"data:data/global/excel/weapons.txt"` with mod_dir
`C:\mods\Reimagined\Reimagined.mpq` resolves to
`C:\mods\Reimagined\Reimagined.mpq\data\global\excel\weapons.txt`.

```python
reader = CASCReader(
    game_dir=Path(r"C:\Program Files (x86)\Diablo II Resurrected"),
    mod_dir=Path(r"C:\mods\Reimagined\Reimagined.mpq"),
)
# Reads from mod directory if the file exists there, otherwise from CASC
data = reader.read_file("data:data/global/excel/weapons.txt")
```

**Note:** `read_by_ckey()` and `resolve_ckey()` bypass the mod overlay entirely,
since content keys are CASC-specific.

---

## Error Handling

All read methods return `None` on failure instead of raising exceptions.
This enables graceful degradation (e.g., missing sprites render as
fallback placeholders instead of crashing the application).

| Scenario | Behavior |
|----------|----------|
| Path not found in TVFS | `read_file()` returns `None` |
| CKey not in ENCODING | `read_by_ckey()` returns `None` |
| EKey not in index | Returns `None` |
| Archive data file missing | Returns `None` |
| Corrupt BLTE data | Logged at DEBUG level, returns `None` |
| Encrypted BLTE frame | Logged at DEBUG level, returns `None` |
| Missing `.build.info` | `FileNotFoundError` raised on construction |
| Missing build config | `FileNotFoundError` raised on construction |

---

## Internal Modules

These modules are implementation details and should not be imported directly.
They are documented here for maintainability.

### `_blte.py`

- `decode_blte(raw: bytes) -> bytes | None` -- Decode BLTE-encoded data.
  Handles archive format (0x1E-byte prefix) and standalone BLTE.
- `_decode_frame(frame_data: bytes) -> bytes | None` -- Decode a single
  BLTE frame (N=raw, Z=zlib, E=encrypted).

### `_buildinfo.py`

- `parse_build_info(game_dir: Path) -> tuple[bytes, bytes]` -- Parse
  `.build.info`, return (build_key, cdn_key).
- `load_build_config(data_dir, build_key) -> tuple[bytes, bytes, list]` --
  Load build config, return (enc_ckey, enc_ekey, vfs_entries).

### `_encoding.py`

- `load_encoding(raw: bytes, ckey_map: dict) -> None` -- Parse ENCODING
  manifest into the provided CKey->EKey dict.
- `build_ekey_to_ckey_map(ckey_map) -> dict` -- Build reverse EKey->CKey
  lookup for O(1) TVFS resolution.

### `_index.py`

- `load_index_files(data_dir) -> tuple[dict, dict, int]` -- Parse all 16
  index files, return (ekey_map, data_files, file_offset_bits).

### `_tvfs.py`

- `parse_tvfs_root(root_data, vfs_entries, path_map, ekey_to_ckey, read_fn)`
  -- Walk the TVFS tree and populate the path->CKey map.

---

## Performance Characteristics

| Operation | Time | Notes |
|-----------|------|-------|
| Construction (full init) | ~3-5 sec | Parses all index files + encoding + TVFS |
| `read_file()` | <1 ms | Dict lookup + single file read + BLTE decompress |
| `read_by_ckey()` | <1 ms | Dict lookup + file read |
| `has_file()` | <0.01 ms | Dict `in` check |
| `list_files("*")` | ~50 ms | Sorts ~175k keys |
| `list_files(pattern)` | ~100-200 ms | fnmatch filter on ~175k keys |
| `resolve_ckey()` | <0.01 ms | Dict `.get()` |

**Memory:** The reader holds ~175k path strings + ~170k CKey/EKey entries +
~150k index entries in memory. Total approximately 80-120 MB.

---

## Test Coverage

94 test checks in `tests/test_casc_reader.py` covering:

- TVFS infrastructure (path count, encoding count, index count)
- Path format correctness (no double slashes, no trailing slashes)
- Sub-VFS resolution (colon-prefixed paths)
- Top-level paths (no sub-VFS prefix)
- Item sprite paths (all three categories: armor, weapon, misc)
- GFX variant sprites (rings, charms, amulets with numbered variants)
- File reading + data integrity (TSV validation, SpA1 magic, OTF header)
- Error handling (non-existent paths, invalid CKeys)
- BLTE decompression (medium and small files)
- Encoding/Index consistency (CKey->EKey resolution rate)
- `list_files()` API (glob patterns, sorted output, empty results)
- `resolve_ckey()` API (lookup, None for missing, round-trip with read_by_ckey)
- Properties (file_count, game_dir, mod_dir)

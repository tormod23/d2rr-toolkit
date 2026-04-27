# casc.sprites -- Sprite Format Decoders

Converts Blizzard-proprietary sprite formats into standard image files
(PNG or WebP) with transparent backgrounds. Part of the `d2rr_toolkit.casc`
package but usable independently -- the only dependency is Pillow.

## Supported Formats

| Format | Magic | Era | Source | Description |
|--------|-------|-----|--------|-------------|
| **SpA1** | `SpA1` (4 bytes) | D2R (2021+) | CASC archive | HD sprites with raw RGBA pixel data |
| **DC6** | *(none)* | D2 Classic (2000) | Mod directories | Legacy RLE-encoded palette-indexed sprites |

## Dependencies

- **Pillow** (`pip install Pillow`) -- required for all sprite decoding.
  WebP support is built into Pillow (no additional packages needed).
- If Pillow is not installed, calling `decode_sprite()` or `decode_dc6()`
  raises `RuntimeError` with a clear installation message.

## Quick Start

```python
from pathlib import Path
from d2rr_toolkit.adapters.casc import CASCReader
from d2rr_toolkit.adapters.casc.sprites import decode_sprite

reader = CASCReader(Path(r"C:\Program Files (x86)\Diablo II Resurrected"))

# Read a sprite from the CASC archive
raw = reader.read_file("data:data/hd/global/ui/items/misc/ring/ring.sprite")

# Convert to PNG (lossless, with transparency)
png_bytes = decode_sprite(raw)
Path("ring.png").write_bytes(png_bytes)

# Convert to WebP (lossless, typically ~30% smaller than PNG)
webp_bytes = decode_sprite(raw, format="webp")
Path("ring.webp").write_bytes(webp_bytes)

# Convert to WebP (lossy, even smaller, for web applications)
webp_lossy = decode_sprite(raw, format="webp", quality=85)
```

## API Reference

### `decode_sprite(data, *, format="png", quality=None) -> bytes | None`

Decode a **SpA1** sprite (D2R HD format) to PNG or WebP image bytes.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `data` | `bytes` | *(required)* | Raw SpA1 file bytes, e.g. from `CASCReader.read_file()`. Must start with magic `SpA1`. |
| `format` | `"png" \| "webp"` | `"png"` | Output image format. |
| `quality` | `int \| None` | `None` | **WebP only.** `None` = lossless. `1`-`100` = lossy quality (higher = better). Ignored for PNG. |

**Returns:** Encoded image bytes (PNG or WebP) with RGBA transparency, or `None`
if the input is not valid SpA1 data.

**Raises:** `RuntimeError` if Pillow is not installed.

#### Output Format Comparison

| Format | Transparency | Compression | Typical Size | Use Case |
|--------|-------------|-------------|-------------|----------|
| PNG (default) | Full alpha | Lossless | 15-60 KB | Archival, pixel-perfect |
| WebP lossless | Full alpha | Lossless | 10-40 KB | Smaller than PNG, still lossless |
| WebP lossy | Full alpha | Lossy | 3-15 KB | Web/app display, fast loading |

### `decode_dc6(data, *, palette=None, format="png", quality=None) -> bytes | None`

Decode a **DC6** sprite (D2 legacy format) to PNG or WebP image bytes.
Only decodes the first frame of the first direction.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `data` | `bytes` | *(required)* | Raw DC6 file bytes. |
| `palette` | `list[tuple[int,int,int]] \| None` | `None` | 256-entry RGB palette for color mapping. If `None`, uses a grayscale fallback. |
| `format` | `"png" \| "webp"` | `"png"` | Output image format. |
| `quality` | `int \| None` | `None` | **WebP only.** Same as `decode_sprite()`. |

**Returns:** Encoded image bytes with RGBA transparency, or `None` on error.

**Raises:** `RuntimeError` if Pillow is not installed.

#### About the Palette

DC6 sprites are palette-indexed (each pixel is a byte referencing a 256-color
palette). The correct palette for D2R inventory sprites is the "units" palette
from `data/global/palette/units/pal.dat` (768 bytes = 256 RGB triples).

If you are reading sprites through the D2RR Toolkit GUI, the palette is
loaded automatically. For standalone use, you can load it manually:

```python
pal_data = Path("pal.dat").read_bytes()
palette = [(pal_data[i*3], pal_data[i*3+1], pal_data[i*3+2]) for i in range(256)]
png = decode_dc6(dc6_bytes, palette=palette)
```

**Palette index 0** is always treated as transparent (alpha = 0), regardless
of its RGB value. This is the D2 convention for sprite transparency.

---

## SpA1 Binary Format

SpA1 is the D2R HD sprite format used for inventory icons, UI elements, and
in-game effects. The format stores raw RGBA pixel data (4 bytes per pixel)
**immediately after a fixed-size 40-byte header** - the pixel block is at
a constant offset for every sprite, regardless of what comes after it.

```
Offset  Size       Field
------  ---------  -----
0x00    4 bytes    Magic: "SpA1" (0x53 0x70 0x41 0x31)
0x04    4 bytes    Version (uint32 LE)
0x08    4 bytes    Width in pixels (uint32 LE)
0x0C    4 bytes    Height in pixels (uint32 LE)
0x10    24 bytes   Per-sprite metadata / padding (varies; ignored)
0x28    W*H*4      Raw RGBA pixel data (4 bytes per pixel: R, G, B, A)
[tail]  optional   Trailing region (mipmaps / lowend variants / padding)
                   present on a subset of sprites; the decoder skips it.
```

**Pixel data location:** The decoder reads the RGBA block at the fixed
offset ``0x28`` (40). A length sanity check rejects truncated files
(``40 + w*h*4 > len(data)`` -> ``None``). Sprites with trailing bytes
beyond ``40 + w*h*4`` are handled correctly - the decoder ignores them.

**Why this matters:** Earlier toolkit revisions computed the offset from
the file *tail* (``len(data) - w*h*4``). That math lands on 40 only when
the file is exactly ``header + pixels`` bytes long, which is the common
case; sprites carrying any trailing region produced garbage output.
``stash_tabs2.sprite`` (780*80 pixels, 70 400 trailing bytes) was the
canonical bug reproducer - rendered as a mostly-red blob because the
trailer's ``[R, 0, 0, 0xff]`` byte pattern happened to look like
partially-transparent red pixels.

**Typical dimensions:** Inventory sprites are small (29*29 to 58*116
pixels), so file sizes range from ~3 KB to ~30 KB for the raw SpA1 data.
Larger UI panels (stash, paperdoll, tab strips) can reach a few MB and
are the ones most likely to carry a trailer.

---

## DC6 Binary Format

DC6 is the original Diablo II sprite format, still used by some mods for
compatibility. It uses RLE (Run-Length Encoding) compression with palette
indices.

```
=== File Header (24 bytes) ===

Offset  Size     Field
------  -------  -----
0x00    4 bytes  Version (int32 LE, typically 6)
0x04    4 bytes  Flags (int32 LE)
0x08    4 bytes  Encoding (int32 LE)
0x0C    4 bytes  Termination (int32 LE, typically 0xEEEEEEEE or 0xCDCDCDCD)
0x10    4 bytes  Directions (int32 LE, typically 1 for inventory sprites)
0x14    4 bytes  Frames per direction (int32 LE)

=== Frame Pointer Table ===

(directions * frames_per_dir) entries, each 4 bytes (uint32 LE),
pointing to the start of each frame's header within the file.

=== Frame Header (32 bytes, at frame pointer offset) ===

Offset  Size     Field
------  -------  -----
+0x00   4 bytes  Flip (int32 LE, 0 = normal bottom-to-top)
+0x04   4 bytes  Width (int32 LE)
+0x08   4 bytes  Height (int32 LE)
+0x0C   4 bytes  Offset X (int32 LE)
+0x10   4 bytes  Offset Y (int32 LE)
+0x14   4 bytes  Unknown (int32 LE)
+0x18   4 bytes  Next Block (int32 LE)
+0x1C   4 bytes  Data Length (int32 LE, size of RLE pixel data)

=== RLE Pixel Data (Data Length bytes, after frame header) ===

Byte-by-byte RLE encoding:

  0x80          End of scanline (advance to next row, reset X to 0)
  byte >= 0x80  Transparent run: skip (byte & 0x7F) pixels
  byte < 0x80   Opaque run: next `byte` bytes are palette indices
```

**Scanline order:** Bottom-to-top (row 0 = bottom of image). The decoder
flips Y coordinates accordingly.

**Only first frame decoded:** The current implementation decodes only the
first frame of the first direction. Multi-frame DC6 files (animations)
would require an extended API.

---

## Usage Examples

### Bulk Export All Item Sprites

```python
from pathlib import Path
from d2rr_toolkit.adapters.casc import CASCReader
from d2rr_toolkit.adapters.casc.sprites import decode_sprite

reader = CASCReader(Path(r"C:\Program Files (x86)\Diablo II Resurrected"))
output = Path("export/sprites")
output.mkdir(parents=True, exist_ok=True)

for path in reader.list_files("data:data/hd/global/ui/items/*/*.sprite"):
    if ".lowend." in path:
        continue  # skip low-quality variants
    name = path.rsplit("/", 1)[-1].replace(".sprite", "")
    raw = reader.read_file(path)
    img = decode_sprite(raw, format="webp")
    if img:
        (output / f"{name}.webp").write_bytes(img)
        print(f"Exported {name}.webp ({len(img)} bytes)")
```

### Extract a Single UI Element

```python
# Menu background, loading screen, or any other UI sprite
raw = reader.read_file("data:data/hd/global/ui/panel/gemsocket.sprite")
png = decode_sprite(raw)
Path("gemsocket.png").write_bytes(png)
```

### Read Non-Sprite Files

The CASC reader can read any file type, not just sprites:

```python
# Game data tables (tab-separated)
weapons = reader.read_file("data:data/global/excel/weapons.txt")
print(weapons.decode("utf-8")[:200])

# Font files
font = reader.read_file("data:data/hd/ui/fonts/exocetblizzardot-medium.otf")
Path("exocet.otf").write_bytes(font)

# JSON configuration
items_json = reader.read_file("data:data/hd/items/items.json")
```

### Error Handling

```python
# Invalid/missing data returns None (no exceptions)
result = decode_sprite(b"not a sprite")
assert result is None

result = decode_sprite(b"")
assert result is None

# But missing Pillow raises RuntimeError with clear message
# (only if Pillow is truly not installed)
```

---

## Performance Notes

| Operation | Time | Notes |
|-----------|------|-------|
| `decode_sprite()` to PNG | ~1-5 ms | Depends on sprite dimensions |
| `decode_sprite()` to WebP lossless | ~2-8 ms | Slightly slower than PNG |
| `decode_sprite()` to WebP lossy | ~1-3 ms | Faster than lossless |
| `decode_dc6()` | ~2-10 ms | RLE decoding + palette lookup |

WebP lossless output is typically **25-35% smaller** than PNG for the same
sprite, with identical visual quality. WebP lossy at quality 85-90 produces
files **70-80% smaller** than PNG with minimal visible difference at
inventory-sprite sizes (29x29 to 58x116 pixels).

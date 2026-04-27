"""Palette and colormap loaders for D2 palette-based item tinting.

Loads the three asset types required to reproduce D2's in-game item
tinting via palette lookup:

  1. pal.dat              -- 256-color RGB palette (disk order: BGR)
  2. *.dat colormaps      -- 21 x 256 per-tint lookup tables
  3. colors.txt           -- code string -> tint-id (0..20)

All three come from the D2R base CASC archive (the Reimagined mod
does not override them).

The pipeline consumer is :mod:`d2rr_toolkit.display.tinted_sprite`
which combines a palette-indexed DC6 sprite, a palette, and a
colormap to produce the final tinted RGBA buffer.

Usage::

    from d2rr_toolkit.display.palette import (
        load_palette, load_colormap, load_colors_txt,
    )

    palette   = load_palette(casc, "act1")
    colormap  = load_colormap(casc, 8)       # invgreybrown
    code_map  = load_colors_txt(casc)
    tint_id   = code_map["cred"]             # 9
    new_index = colormap.lookup(tint_id, old_index)
    rgb       = palette.color(new_index)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from d2rr_toolkit.adapters.casc.reader import CASCReader

logger = logging.getLogger(__name__)


# ── Constants ───────────────────────────────────────────────────────────────

_PAL_DAT_SIZE = 768  # 256 colours * 3 bytes
_COLORMAP_SIZE = 5376  # 21 tints * 256 indices * 1 byte
_TINT_COUNT = 21  # rows in colors.txt

# Colormap ID -> file basename (under data/global/items/palette/).
# IDs 1..5 are in-game ground/sprite maps, 6..8 are inventory maps.
_COLORMAP_FILES: dict[int, str] = {
    1: "grey",
    2: "grey2",
    3: "brown",
    4: "gold",
    5: "greybrown",
    6: "invgrey",
    7: "invgrey2",
    8: "invgreybrown",
}


# ── Data classes ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Palette:
    """256-color palette in RGB order (0..255 per channel).

    The on-disk format is BGR; this class stores the bytes already
    converted to RGB so consumers never have to think about byte order.
    """

    name: str
    rgb: bytes  # 768 bytes, RGB order

    def color(self, index: int) -> tuple[int, int, int]:
        """Return the (R, G, B) tuple for a palette index."""
        if not 0 <= index < 256:
            raise IndexError(f"palette index out of range: {index}")
        i = index * 3
        return (self.rgb[i], self.rgb[i + 1], self.rgb[i + 2])


@dataclass(frozen=True)
class ColorMap:
    """21 * 256 lookup tables for one colormap file.

    Each of the 21 tints is a 256-byte table mapping an input palette
    index to an output palette index. Tint IDs 0..20 correspond to the
    row order in colors.txt.
    """

    colormap_id: int
    name: str
    tints: bytes  # 5376 bytes, laid out as 21 * 256 (tint_id * 256 + in_index)

    def lookup(self, tint_id: int, in_index: int) -> int:
        """Look up a tinted palette index.

        Args:
            tint_id:  0..20, row number from colors.txt.
            in_index: 0..255, the source palette index from the sprite.

        Returns:
            0..255, the transformed palette index.
        """
        if not 0 <= tint_id < _TINT_COUNT:
            raise IndexError(f"tint_id out of range: {tint_id}")
        if not 0 <= in_index < 256:
            raise IndexError(f"in_index out of range: {in_index}")
        return self.tints[tint_id * 256 + in_index]


# ── Caches ──────────────────────────────────────────────────────────────────

# Palettes are keyed by name ("act1" etc.). There's only ever ~1 entry.
_palette_cache: dict[str, Palette] = {}

# Colormaps are keyed by ID. Max 8 entries.
_colormap_cache: dict[int, ColorMap] = {}

# colors.txt is a single dict - cache as a module-level list.
_colors_txt_cache: dict[str, int] | None = None


def clear_caches() -> None:
    """Clear all palette/colormap/colors.txt caches. For testing."""
    global _colors_txt_cache
    _palette_cache.clear()
    _colormap_cache.clear()
    _colors_txt_cache = None


# ── Loaders ─────────────────────────────────────────────────────────────────


def load_palette(casc: "CASCReader", name: str = "act1") -> Palette:
    """Load and parse ``data:data/global/palette/<name>/pal.dat``.

    Converts from disk BGR order to in-memory RGB order so consumers
    can treat the bytes as a plain RGB triple stream.

    Args:
        casc: CASCReader used to read from the D2R base archive.
        name: Palette subdirectory name. Defaults to "act1", which is
              used for all inventory items.

    Returns:
        Palette with 768 bytes of RGB data.

    Raises:
        ValueError: The file is missing or not exactly 768 bytes long.
    """
    cached = _palette_cache.get(name)
    if cached is not None:
        return cached

    casc_path = f"data:data/global/palette/{name}/pal.dat"
    raw = casc.read_file(casc_path)
    if raw is None:
        raise ValueError(f"Palette file not found in CASC: {casc_path}")
    if len(raw) != _PAL_DAT_SIZE:
        raise ValueError(
            f"Palette file {casc_path} has unexpected size {len(raw)} (expected {_PAL_DAT_SIZE})"
        )

    # Disk is BGR; swap to RGB in memory.
    rgb = bytearray(_PAL_DAT_SIZE)
    for i in range(256):
        b = raw[i * 3]
        g = raw[i * 3 + 1]
        r = raw[i * 3 + 2]
        rgb[i * 3] = r
        rgb[i * 3 + 1] = g
        rgb[i * 3 + 2] = b

    palette = Palette(name=name, rgb=bytes(rgb))
    _palette_cache[name] = palette
    logger.debug("Loaded palette %s from %s", name, casc_path)
    return palette


def load_colormap(casc: "CASCReader", colormap_id: int) -> ColorMap:
    """Load and parse ``data:data/global/items/palette/<file>.dat``.

    Colormap ID mapping (from D2 convention)::

        1 -> grey.dat
        2 -> grey2.dat
        3 -> brown.dat
        4 -> gold.dat
        5 -> greybrown.dat
        6 -> invgrey.dat        (inventory grey)
        7 -> invgrey2.dat       (inventory grey alt)
        8 -> invgreybrown.dat   (inventory grey-brown)

    Args:
        casc:        CASCReader.
        colormap_id: 1..8. ID 0 is not valid here - it means "no transform"
                     and must be handled by the caller.

    Returns:
        ColorMap with 5376 bytes of tint lookup data.

    Raises:
        ValueError: ID 0, unknown ID, missing file, or wrong file size.
    """
    cached = _colormap_cache.get(colormap_id)
    if cached is not None:
        return cached

    if colormap_id == 0:
        raise ValueError("colormap_id 0 means 'no transform' and must be handled by the caller")
    if colormap_id not in _COLORMAP_FILES:
        raise ValueError(f"unknown colormap_id: {colormap_id}")

    basename = _COLORMAP_FILES[colormap_id]
    casc_path = f"data:data/global/items/palette/{basename}.dat"
    raw = casc.read_file(casc_path)
    if raw is None:
        raise ValueError(f"Colormap file not found in CASC: {casc_path}")
    if len(raw) != _COLORMAP_SIZE:
        raise ValueError(
            f"Colormap file {casc_path} has unexpected size {len(raw)} (expected {_COLORMAP_SIZE})"
        )

    colormap = ColorMap(colormap_id=colormap_id, name=basename, tints=raw)
    _colormap_cache[colormap_id] = colormap
    logger.debug("Loaded colormap %d (%s) from %s", colormap_id, basename, casc_path)
    return colormap


def load_colors_txt(casc: "CASCReader") -> dict[str, int]:
    """Load and parse ``data:data/global/excel/colors.txt``.

    Returns a mapping from Code string (e.g. ``"cred"``) to tint-id
    (0..20). The row order in the file IS the tint-id; the header
    row is skipped.

    Example::

        {
            "whit": 0, "lgry": 1, "dgry": 2, "blac": 3,
            "lblu": 4, "dblu": 5, "cblu": 6,
            "lred": 7, "dred": 8, "cred": 9,
            "lgrn": 10, "dgrn": 11, "cgrn": 12,
            "lyel": 13, "dyel": 14,
            "lgld": 15, "dgld": 16,
            "lpur": 17, "dpur": 18,
            "oran": 19, "bwht": 20,
        }

    Raises:
        ValueError: file missing or unparseable.
    """
    global _colors_txt_cache
    if _colors_txt_cache is not None:
        return _colors_txt_cache

    casc_path = "data:data/global/excel/colors.txt"
    raw = casc.read_file(casc_path)
    if raw is None:
        raise ValueError(f"colors.txt not found in CASC: {casc_path}")

    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if not lines:
        raise ValueError(f"colors.txt is empty: {casc_path}")

    result: dict[str, int] = {}
    tint_id = 0
    for line in lines[1:]:  # skip header
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        code = parts[1].strip().lower()
        if code:
            result[code] = tint_id
            tint_id += 1

    if not result:
        raise ValueError(f"colors.txt produced no entries: {casc_path}")

    _colors_txt_cache = result
    logger.debug("Loaded colors.txt: %d entries", len(result))
    return result

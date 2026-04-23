"""High-level palette-based item sprite tinting.

This module implements the full D2 in-game tinting pipeline for item
inventory sprites. It combines:

  1. :func:`d2rr_toolkit.display.invtransform.get_invtransform` to
     determine the color code (e.g. ``"cred"``) for an item.
  2. :func:`d2rr_toolkit.display.palette.load_colors_txt` to map that
     code to a tint-id (0..20).
  3. :meth:`ItemTypeDatabase.get_inv_transform_id` to pick the
     colormap file for the item's base category.
  4. A palette-indexed DC6 decode via
     :func:`d2rr_toolkit.sprites.dc6_indexed.decode_dc6_indexed`.
  5. The palette lookup + colormap transform to produce the final
     RGBA pixel buffer.

Returning pure ``bytes`` keeps this module free of Qt/PIL dependencies
so it is safe to call from any GUI stack.

Usage::

    from d2rr_toolkit.display.tinted_sprite import get_tinted_sprite

    result = get_tinted_sprite(item)
    if result is not None:
        # result.rgba is width*height*4 bytes, RGBA8888, y=0 at top.
        qimg = QImage(result.rgba, result.width, result.height, QImage.Format_RGBA8888)
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from d2rr_toolkit.models.character import ParsedItem
    from d2rr_toolkit.adapters.casc.reader import CASCReader

logger = logging.getLogger(__name__)


# ── Public data class ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class TintedSpriteResult:
    """RGBA pixel buffer ready for GUI consumption.

    - ``rgba`` is ``width * height * 4`` bytes, non-premultiplied
      RGBA8888, with y=0 at the top (standard image convention).
    - Transparent pixels are ``(0, 0, 0, 0)``; opaque pixels have
      alpha ``255``.
    """

    width: int
    height: int
    rgba: bytes


# ── Module state ────────────────────────────────────────────────────────────

# Result cache keyed by (invfile_lower, colormap_id, tint_id).
# Same unique with same gem socket would otherwise be decoded on every
# render. This is cheap and monotonic - entries are never invalidated.
_result_cache: dict[tuple[str, int, int], TintedSpriteResult] = {}
_cache_lock = threading.Lock()

# The CASCReader and mod DC6 directory the pipeline should use. These
# are typically supplied by the GUI once at startup via
# :func:`configure_tinted_sprite_pipeline`.
_casc: "CASCReader | None" = None
_mod_dc6_dir: Path | None = None


def configure_tinted_sprite_pipeline(
    casc: "CASCReader | None",
    mod_dc6_dir: Path | None,
) -> None:
    """Register the CASCReader and mod DC6 directory for tinting.

    Call this once at application start-up, before the first
    :func:`get_tinted_sprite` call. If a caller forgets to configure
    the pipeline, :func:`get_tinted_sprite` returns ``None`` - it
    never crashes.

    Args:
        casc:        The same CASCReader instance used elsewhere in
                     the app. May be None if CASC is unavailable
                     (tinting will then fall back to mod-only).
        mod_dc6_dir: The Reimagined mod DC6 items directory
                     (typically ``GamePaths.mod_dc6_items``).
                     May be None - tinting then tries CASC only.
    """
    global _casc, _mod_dc6_dir
    _casc = casc
    _mod_dc6_dir = mod_dc6_dir


def clear_cache() -> None:
    """Drop the (invfile, colormap, tint) result cache. For testing."""
    with _cache_lock:
        _result_cache.clear()


# ── Public API ──────────────────────────────────────────────────────────────


def get_tinted_sprite(item: "ParsedItem") -> TintedSpriteResult | None:
    """Render an item's inventory sprite with D2's palette-based tinting.

    Returns ``None`` if no tinting applies, or if any step of the
    pipeline is missing (no color code, no colormap id, no DC6
    sprite, etc.). The caller should then fall back to the un-tinted
    sprite (e.g. via :class:`SpriteResolver`).

    The full pipeline:

      1. Resolve the color code via
         :func:`d2rr_toolkit.display.invtransform.get_invtransform`.
         If ``None``, return ``None``.
      2. Resolve the tint-id via :func:`load_colors_txt`. If the
         code is not in the table, log a warning and return ``None``.
      3. Resolve the colormap id via the item's base category row
         (``InvTrans`` column). If 0, return ``None``.
      4. Resolve the DC6 invfile: Unique invfile > Set invfile >
         base item invfile. Whichever wins is loaded from the mod
         DC6 directory first, then from CASC.
      5. Decode the DC6 to palette indices via
         :func:`decode_dc6_indexed` (frame 0).
      6. Load the ``act1`` palette and the colormap file.
      7. For each pixel index ``i``:

         - ``i == 0``  -> fully transparent ``(0, 0, 0, 0)``
         - ``i != 0``  -> ``new = colormap.lookup(tint_id, i)``,
           ``(*palette.color(new), 255)``

      8. Return :class:`TintedSpriteResult`.

    Socket children for gem tint lookup are read directly from
    ``item.socket_children``; the surrounding item list is not needed.

    Args:
        item: The :class:`ParsedItem` to tint.

    Returns:
        :class:`TintedSpriteResult` with RGBA pixels, or ``None``.

    Thread-safety:
        Safe to call concurrently from multiple threads. The internal
        result cache is guarded by a lock. Palette and colormap
        loaders are cached at module level and only read-once on
        first use. CASC and DC6 file reads go through the CASCReader /
        Path APIs which are thread-safe for reads.
    """
    if _casc is None:
        # Pipeline never configured - nothing we can do.
        return None

    # Step 1: color code from get_invtransform.
    from d2rr_toolkit.display.invtransform import get_invtransform

    code = get_invtransform(item)
    if code is None:
        return None

    # Step 2: tint id
    from d2rr_toolkit.display.palette import load_colors_txt

    try:
        code_map = load_colors_txt(_casc)
    except ValueError as e:
        logger.warning("Cannot load colors.txt: %s", e)
        return None

    tint_id = code_map.get(code.lower())
    if tint_id is None:
        logger.warning("Unknown color code %r (not in colors.txt)", code)
        return None

    # Step 3: colormap id from InvTrans column of the item's base row
    from d2rr_toolkit.game_data.item_types import get_item_type_db

    type_db = get_item_type_db()
    colormap_id = type_db.get_inv_transform_id(item.item_code)
    if colormap_id == 0:
        # Game data explicitly says "do not transform this item"
        return None

    # Step 4: resolve invfile (unique > set > base)
    invfile = _resolve_invfile(item)
    if not invfile:
        return None

    # Step 4b: result cache hit?
    cache_key = (invfile.lower(), colormap_id, tint_id)
    with _cache_lock:
        cached = _result_cache.get(cache_key)
    if cached is not None:
        return cached

    # Step 5: load + decode DC6
    dc6_bytes = _load_dc6_bytes(invfile)
    if dc6_bytes is None:
        return None

    from d2rr_toolkit.sprites.dc6_indexed import decode_dc6_indexed

    try:
        frame = decode_dc6_indexed(dc6_bytes, frame=0)
    except ValueError as e:
        logger.debug("DC6 indexed decode failed for %r: %s", invfile, e)
        return None

    # Step 6: palette + colormap
    from d2rr_toolkit.display.palette import load_colormap, load_palette

    try:
        palette = load_palette(_casc, "act1")
        colormap = load_colormap(_casc, colormap_id)
    except ValueError as e:
        logger.warning("Cannot load palette/colormap: %s", e)
        return None

    # Step 7: apply the transform
    rgba = _apply_palette_transform(
        frame.indices,
        frame.width,
        frame.height,
        palette.rgb,
        colormap.tints,
        tint_id,
    )

    result = TintedSpriteResult(
        width=frame.width,
        height=frame.height,
        rgba=rgba,
    )

    with _cache_lock:
        _result_cache[cache_key] = result
    return result


# ── Internal helpers ────────────────────────────────────────────────────────


def _resolve_invfile(item: "ParsedItem") -> str:
    """Return the DC6 invfile name for an item.

    Resolution order:
      1. Unique invfile (from uniqueitems.txt, per unique-type-id)
      2. Set-item invfile (from setitems.txt, per set-item-id)
      3. Base item invfile (from armor/weapons/misc.txt)

    Returns the first non-empty match, or an empty string.
    """
    from d2rr_toolkit.game_data.item_names import get_item_names_db
    from d2rr_toolkit.game_data.sets import get_sets_db
    from d2rr_toolkit.game_data.item_types import get_item_type_db

    # 1. Unique override
    unique_type_id = getattr(item, "unique_type_id", None)
    if unique_type_id is not None:
        names_db = get_item_names_db()
        if names_db.is_loaded():
            inv = names_db.get_unique_invfile(unique_type_id)
            if inv:
                return inv

    # 2. Set override
    set_item_id = getattr(item, "set_item_id", None)
    if set_item_id is not None:
        sets_db = get_sets_db()
        if sets_db.is_loaded():
            set_def = sets_db.get_set_item(set_item_id)
            if set_def is not None and set_def.invfile:
                return set_def.invfile

    # 3. Base item invfile
    return get_item_type_db().get_inv_file(item.item_code) or ""


def _load_dc6_bytes(invfile: str) -> bytes | None:
    """Load raw DC6 file bytes.

    Priority: mod DC6 directory first (case-insensitive fallback),
    then CASC archive at ``data:data/global/items/<invfile>.dc6``.
    """
    # 1. Mod directory
    if _mod_dc6_dir is not None:
        mod_path = _mod_dc6_dir / f"{invfile}.dc6"
        if mod_path.exists():
            try:
                return mod_path.read_bytes()
            except OSError as e:
                logger.debug("Mod DC6 read failed for %r: %s", invfile, e)
        else:
            # Case-insensitive fallback
            lower = f"{invfile.lower()}.dc6"
            try:
                for f in _mod_dc6_dir.iterdir():
                    if f.name.lower() == lower:
                        return f.read_bytes()
            except OSError as e:
                logger.debug("Mod DC6 scan failed for %r: %s", invfile, e)

    # 2. CASC fallback
    if _casc is not None:
        casc_path = f"data:data/global/items/{invfile}.dc6"
        data = _casc.read_file(casc_path)
        if data:
            return data

    return None


def _apply_palette_transform(
    indices: bytes,
    width: int,
    height: int,
    palette_rgb: bytes,
    colormap_tints: bytes,
    tint_id: int,
) -> bytes:
    """Apply the colormap + palette lookup to an indexed pixel buffer.

    Pure bytes in, pure bytes out. No Pillow / Qt / NumPy dependency.

    The transform per pixel::

        if index == 0:
            output = (0, 0, 0, 0)
        else:
            new = colormap_tints[tint_id*256 + index]
            (r, g, b) = palette_rgb[new*3 : new*3 + 3]
            output = (r, g, b, 255)
    """
    n = width * height
    out = bytearray(n * 4)  # zero-init -> all transparent

    tint_base = tint_id * 256
    for i in range(n):
        src_idx = indices[i]
        if src_idx == 0:
            # Already (0, 0, 0, 0) from zero-init - skip.
            continue
        new_idx = colormap_tints[tint_base + src_idx]
        rgb_off = new_idx * 3
        o = i * 4
        out[o] = palette_rgb[rgb_off]
        out[o + 1] = palette_rgb[rgb_off + 1]
        out[o + 2] = palette_rgb[rgb_off + 2]
        out[o + 3] = 0xFF

    return bytes(out)


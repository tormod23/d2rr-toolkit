"""Palette-indexed DC6 decoder for D2 palette-based tinting.

Unlike the RGBA decoder in ``d2rr_toolkit.casc.sprites.decode_dc6``
this one does NOT apply a palette at all - it returns the raw
256-color palette indices exactly as they are stored in the DC6 file.

This is required for palette-based item tinting: the caller passes
each index through a colormap LUT and THEN looks up the final RGB
colour from the palette. Applying the palette early (as the RGBA
decoder does) discards the index information and makes tinting
impossible.

Reference implementation: Paul Siramy's ``dc6color.c`` (2002), lines
165-211 (``decompress_dc6()``). The byte-level RLE decoder here is
intentionally identical to that reference.

Usage::

    from d2rr_toolkit.sprites.dc6_indexed import decode_dc6_indexed

    raw = (mod_dc6_dir / "invhlmu.dc6").read_bytes()
    frame = decode_dc6_indexed(raw, frame=0)
    # frame.indices is a flat bytes array, width*height long,
    # row-major, y=0 at top. Index 0 means transparent.
"""

import logging
import struct
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ── Data classes ────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class IndexedDC6Frame:
    """One DC6 frame as palette indices (not RGBA).

    The ``indices`` buffer is a flat byte array of ``width*height``
    bytes, row-major, with y=0 at the TOP of the image (the caller
    never has to deal with DC6's bottom-to-top storage order).

    Index 0 represents a transparent pixel by D2 convention. The
    decoder leaves such pixels as 0 and does not bake any alpha
    channel into the output - that is the caller's job.
    """

    width: int
    height: int
    offset_x: int
    offset_y: int
    indices: bytes


# ── Header constants ────────────────────────────────────────────────────────

_DC6_HEADER_SIZE = 24
_DC6_FRAME_HEADER_SIZE = 32


# ── Public API ──────────────────────────────────────────────────────────────


def decode_dc6_indexed(data: bytes, frame: int = 0) -> IndexedDC6Frame:
    """Decode a single frame of a DC6 file to palette-indexed pixels.

    The DC6 file format stores pixels row-by-row from BOTTOM to TOP
    with a simple RLE-like scheme (reproduced here verbatim from
    dc6color.c decompress_dc6())::

        byte 0x80          end of scanline (y--, x = 0)
        byte with bit7 set skip (byte & 0x7F) pixels (transparent run)
        byte 0..0x7F       literal opaque run: next N bytes are
                           palette indices to copy straight through

    The output buffer has y=0 at the TOP (standard image convention)
    because the write position is computed as ``(height - 1 - y)``.
    This matches the existing RGBA DC6 decoder's coordinate system.

    Args:
        data:  Raw DC6 file bytes.
        frame: Zero-based frame index within direction 0. Default is 0
               which is correct for inventory sprites (single-frame).

    Returns:
        IndexedDC6Frame with width, height, offsets, and the raw
        palette indices.

    Raises:
        ValueError: Input is malformed (too short, missing frame,
                    corrupt header, or RLE overflow).
    """
    if not data or len(data) < _DC6_HEADER_SIZE:
        raise ValueError("DC6 data too short for header")

    # File header [24 bytes]:
    #   version, flags, encoding, termination, directions, frames_per_dir
    try:
        _ver, _flags, _enc, _term, dirs, fpd = struct.unpack_from("<6i", data, 0)
    except struct.error as e:
        raise ValueError(f"DC6 header unpack failed: {e}") from e

    if dirs < 1 or fpd < 1:
        raise ValueError(f"DC6 has no frames: dirs={dirs}, fpd={fpd}")

    total_frames = dirs * fpd
    if not 0 <= frame < total_frames:
        raise ValueError(f"frame index {frame} out of range (0..{total_frames - 1})")

    # Frame pointer table: one u32 LE per frame, directly after the header.
    ptr_offset = _DC6_HEADER_SIZE + frame * 4
    if ptr_offset + 4 > len(data):
        raise ValueError("DC6 frame pointer table truncated")
    frame_ptr = struct.unpack_from("<I", data, ptr_offset)[0]

    if frame_ptr + _DC6_FRAME_HEADER_SIZE > len(data):
        raise ValueError(f"DC6 frame {frame} header out of bounds")

    # Frame header [32 bytes]:
    #   flip, width, height, offset_x, offset_y, unknown, next_block, data_length
    try:
        _flip, width, height, ox, oy, _unk, _nxt, data_len = struct.unpack_from(
            "<8i",
            data,
            frame_ptr,
        )
    except struct.error as e:
        raise ValueError(f"DC6 frame header unpack failed: {e}") from e

    if width <= 0 or height <= 0 or width > 4096 or height > 4096:
        raise ValueError(f"DC6 frame has implausible size: {width}x{height}")

    pixel_start = frame_ptr + _DC6_FRAME_HEADER_SIZE
    pixel_end = pixel_start + data_len
    if pixel_end > len(data):
        raise ValueError(f"DC6 frame {frame} pixel data truncated ({pixel_end} > {len(data)})")
    pixel_data = data[pixel_start:pixel_end]

    # Decode into a top-origin index buffer. DC6 stores rows from bottom
    # to top so we write to (height - 1 - y) to flip the vertical axis.
    indices = bytearray(width * height)  # zero-initialised -> transparent
    x = 0
    y = 0  # counts rows from the bottom (0 = bottom row)
    pos = 0
    n = len(pixel_data)

    while pos < n and y < height:
        b = pixel_data[pos]
        pos += 1

        if b == 0x80:
            # End of scanline - advance one row upward.
            x = 0
            y += 1
            continue

        if b & 0x80:
            # Transparent run: skip (b & 0x7F) pixels to the right.
            x += b & 0x7F
            continue

        # Literal opaque run of length ``b``.
        run_len = b
        if pos + run_len > n:
            # Malformed RLE - truncate at the remaining data. We do NOT
            # raise here so that mildly-corrupt files still render
            # something; this matches the reference decoder's lenient
            # behaviour.
            run_len = n - pos

        # Compute the row in top-origin coordinates once.
        dst_row_y = height - 1 - y
        if 0 <= dst_row_y < height:
            # Copy as many bytes as fit in the remaining row width.
            copy_x_end = min(x + run_len, width)
            copy_len = copy_x_end - x
            if copy_len > 0:
                dst_start = dst_row_y * width + x
                indices[dst_start : dst_start + copy_len] = pixel_data[pos : pos + copy_len]
        # Advance source cursor and pixel column unconditionally,
        # even if they run off the right edge of the image.
        pos += run_len
        x += run_len

    return IndexedDC6Frame(
        width=width,
        height=height,
        offset_x=ox,
        offset_y=oy,
        indices=bytes(indices),
    )

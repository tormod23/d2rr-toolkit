"""Sprite format decoders for D2R CASC archives.

Converts Blizzard-proprietary sprite formats (SpA1, DC6) into standard
image formats (PNG, WebP) with transparent backgrounds.

Both output formats support full RGBA transparency via Pillow.
No additional dependencies beyond Pillow are needed for WebP support.

Usage::

    from d2rr_toolkit.adapters.casc.sprites import decode_sprite, decode_dc6

    # SpA1 (D2R HD sprites from CASC archive)
    png_bytes = decode_sprite(raw_spa1_data)
    webp_bytes = decode_sprite(raw_spa1_data, format="webp")
    webp_lossy = decode_sprite(raw_spa1_data, format="webp", quality=90)

    # DC6 (legacy D2 sprites from mod directories)
    png_bytes = decode_dc6(raw_dc6_data, palette=palette_rgb_list)
"""

from __future__ import annotations

import hashlib
import io
import logging
import struct
from typing import Literal

logger = logging.getLogger(__name__)

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore[assignment, misc]

# Valid output formats
ImageFormat = Literal["png", "webp"]


# SpA1 header is a fixed 40-byte prefix; pixel RGBA follows immediately.
# Some sprites carry trailing bytes after the pixel block (mipmap /
# lowend variants / padding); the historical ``len(data) - rgba_size``
# math happened to land on 40 only for sprites without trailers. For
# files like ``stash_tabs2.sprite`` the tail math skipped into the
# trailer and produced garbage (mostly red) output. The correct rule
# is: pixel data starts at byte 40, every time (980/980 pixel match
# vs. 89/980 with the old math).
_SPA1_HEADER_SIZE = 40


def decode_sprite(
    data: bytes,
    *,
    format: ImageFormat = "png",
    quality: int | None = None,
    source: str | None = None,
) -> bytes | None:
    """Decode a SpA1 sprite file to PNG or WebP bytes with transparency.

    SpA1 is the D2R HD sprite format used in CASC archives. The pixel
    data is raw RGBA (4 bytes per pixel) and begins **immediately after
    the 40-byte header** at file offset 40. Any bytes beyond
    ``40 + width*height*4`` belong to optional trailing regions
    (mipmaps / lowend variants) that this decoder deliberately ignores.

    SpA1 binary layout::

        Bytes 0-3:   Magic "SpA1"
        Bytes 4-7:   Version (uint32 LE)
        Bytes 8-11:  Width (uint32 LE)
        Bytes 12-15: Height (uint32 LE)
        Bytes 16-39: Per-sprite metadata / padding (24 bytes, varies)
        Bytes 40+:   Raw RGBA pixel data (width * height * 4 bytes)
        [trailer]:   Optional extra data (mipmaps, lowend variant, ...)
                     - present on a subset of sprites, ignored here.

    Args:
        data:    Raw SpA1 file bytes (e.g. from CASCReader.read_file()).
        format:  Output format: "png" (default, lossless) or "webp".
        quality: For WebP only. None = lossless, 1-100 = lossy quality.
                 Ignored for PNG.

    Returns:
        Encoded image bytes with transparent background, or None on error.

    Raises:
        RuntimeError: If Pillow is not installed.
    """
    if Image is None:
        raise RuntimeError(
            "Pillow is required for sprite decoding. Install with: pip install Pillow"
        )

    if not data or len(data) < _SPA1_HEADER_SIZE or data[:4] != b"SpA1":
        return None

    try:
        width = struct.unpack_from("<I", data, 8)[0]
        height = struct.unpack_from("<I", data, 12)[0]
        rgba_size = width * height * 4
        data_offset = _SPA1_HEADER_SIZE

        # Reject degenerate dimensions and files that are too short to
        # hold a full RGBA block at the fixed header offset. The old
        # tail-based length check is replaced by an explicit bound check
        # that doesn't rely on file size matching ``header + rgba_size``
        # - sprites with trailing regions legitimately exceed that.
        if rgba_size <= 0 or data_offset + rgba_size > len(data):
            return None

        img = Image.frombytes(
            "RGBA",
            (width, height),
            data[data_offset : data_offset + rgba_size],
        )
        return _save_image(img, format, quality)

    except Exception as e:
        # Include the caller-supplied source tag (path or ckey hex) so
        # a field report naming a broken sprite is reproducible. The
        # decoder itself has no knowledge of CASC paths -- callers that
        # need diagnosable logs must pass source=.
        sha = hashlib.sha1(data).hexdigest()[:12] if data else "<empty>"
        logger.debug(
            "SpA1 decode error for source=%r sha1-12=%s len=%d: %s",
            source if source is not None else "<unknown>",
            sha,
            len(data) if data else 0,
            e,
        )
        return None


def decode_dc6(
    data: bytes,
    *,
    palette: list[tuple[int, int, int]] | None = None,
    format: ImageFormat = "png",
    quality: int | None = None,
    source: str | None = None,
) -> bytes | None:
    """Decode a DC6 sprite file (first frame) to PNG or WebP bytes.

    DC6 is the legacy Diablo II sprite format using RLE-encoded palette
    indices. Requires a 256-entry RGB palette for color mapping.

    DC6 binary layout::

        Header (24 bytes):
            version, flags, encoding, termination, directions, frames_per_dir
            (all int32 LE)
        Frame pointer table (dirs * fpd * 4 bytes)
        Per frame (at pointer offset):
            flip, width, height, offset_x, offset_y, unknown,
            next_block, data_length (all int32 LE)
            RLE pixel data (data_length bytes)

    RLE encoding:
        0x80         -> end of scanline
        byte >= 0x80 -> transparent run (length = byte & 0x7F)
        byte < 0x80  -> opaque run (length = byte, followed by palette indices)

    Scanlines are stored bottom-to-top.

    Args:
        data:    Raw DC6 file bytes.
        palette: 256-entry RGB palette. If None, uses a grayscale fallback.
        format:  Output format: "png" or "webp".
        quality: For WebP only. None = lossless, 1-100 = lossy quality.

    Returns:
        Encoded image bytes with transparent background, or None on error.

    Raises:
        RuntimeError: If Pillow is not installed.
    """
    if Image is None:
        raise RuntimeError(
            "Pillow is required for sprite decoding. Install with: pip install Pillow"
        )

    if not data or len(data) < 32:
        return None

    if palette is None:
        palette = [(i, i, i) for i in range(256)]

    try:
        _ver, _flags, _enc, _term, dirs, fpd = struct.unpack_from("<6i", data, 0)
        if dirs < 1 or fpd < 1:
            return None

        frame_ptr = struct.unpack_from("<I", data, 24)[0]

        _flip, width, height, _ox, _oy, _unk, _nxt, data_len = struct.unpack_from(
            "<8i", data, frame_ptr
        )
        if width <= 0 or height <= 0:
            return None

        pixel_data_start = frame_ptr + 32
        pixel_data = data[pixel_data_start : pixel_data_start + data_len]

        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        pixels = img.load()

        x = 0
        y = height - 1  # DC6 is bottom-to-top
        pos = 0

        while pos < len(pixel_data) and y >= 0:
            b = pixel_data[pos]
            pos += 1

            if b == 0x80:
                x = 0
                y -= 1
            elif b & 0x80:
                x += b & 0x7F
            else:
                run_len = b
                for _ in range(run_len):
                    if pos < len(pixel_data) and 0 <= x < width and 0 <= y < height:
                        idx = pixel_data[pos]
                        pos += 1
                        if idx < len(palette):
                            r, g, b_val = palette[idx]
                            alpha = 0 if idx == 0 else 255
                            pixels[x, y] = (r, g, b_val, alpha)
                        else:
                            pixels[x, y] = (128, 128, 128, 255)
                    x += 1

        return _save_image(img, format, quality)

    except Exception as e:
        # Include caller-supplied source tag for reproducibility.
        sha = hashlib.sha1(data).hexdigest()[:12] if data else "<empty>"
        logger.debug(
            "DC6 decode error for source=%r sha1-12=%s len=%d: %s",
            source if source is not None else "<unknown>",
            sha,
            len(data) if data else 0,
            e,
        )
        return None


def _save_image(
    img: "Image.Image",
    format: ImageFormat,
    quality: int | None,
) -> bytes:
    """Encode a PIL Image to the requested format.

    Args:
        img:     PIL Image in RGBA mode.
        format:  "png" or "webp".
        quality: For WebP: None = lossless, 1-100 = lossy. Ignored for PNG.

    Returns:
        Encoded image bytes.
    """
    buf = io.BytesIO()

    if format == "webp":
        if quality is not None:
            img.save(buf, format="WEBP", quality=quality)
        else:
            img.save(buf, format="WEBP", lossless=True)
    else:
        img.save(buf, format="PNG", **{"opt" + "imize": True})

    return buf.getvalue()

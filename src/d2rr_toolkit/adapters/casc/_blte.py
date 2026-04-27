"""BLTE (Block Table Encoding) decompression for CASC archives.

Handles both archive format (with 0x1E-byte prefix) and standalone BLTE.
Supports N (raw) and Z (zlib) frame encodings. Encrypted (E) frames are
not supported and return None.

Reference: CascLib by Ladislav Zezula - CascDecompress.cpp
"""

from __future__ import annotations

import logging
import zlib

logger = logging.getLogger(__name__)


def decode_blte(raw: bytes) -> bytes | None:
    """Decode BLTE-encoded data.

    Handles both archive format (with 0x1E-byte prefix before BLTE magic)
    and standalone BLTE streams.

    Args:
        raw: Raw bytes from the archive data file.

    Returns:
        Decompressed content, or None on failure.
    """
    pos = 0

    # Check for archive prefix (0x1E bytes before "BLTE")
    if len(raw) > 0x1E + 4:
        if raw[0x1E : 0x1E + 4] == b"BLTE":
            pos = 0x1E
        elif raw[:4] == b"BLTE":
            pos = 0
        else:
            blte_pos = raw.find(b"BLTE")
            if blte_pos >= 0:
                pos = blte_pos
            else:
                return raw  # Not BLTE-encoded, return raw
    elif raw[:4] == b"BLTE":
        pos = 0
    else:
        return raw

    # Parse BLTE header
    pos += 4  # skip "BLTE"
    header_size = int.from_bytes(raw[pos : pos + 4], "big")
    pos += 4

    if header_size == 0:
        # Single-frame file
        return _decode_frame(raw[pos:])

    # Multi-frame
    if raw[pos] != 0x0F:
        logger.debug("BLTE: expected 0x0F, got 0x%02x", raw[pos])
    pos += 1

    frame_count = int.from_bytes(raw[pos : pos + 3], "big")
    pos += 3

    # Parse frame table
    frames = []
    for _ in range(frame_count):
        enc_size = int.from_bytes(raw[pos : pos + 4], "big")
        con_size = int.from_bytes(raw[pos + 4 : pos + 8], "big")
        _frame_hash = raw[pos + 8 : pos + 24]
        frames.append((enc_size, con_size))
        pos += 24

    # Decode frames
    result = bytearray()
    for enc_size, con_size in frames:
        if pos + enc_size > len(raw):
            break
        frame_data = raw[pos : pos + enc_size]
        decoded = _decode_frame(frame_data)
        if decoded:
            result.extend(decoded)
        pos += enc_size

    return bytes(result)


def _decode_frame(frame_data: bytes) -> bytes | None:
    """Decode a single BLTE frame.

    Encoding byte meanings:
        N - raw (no compression)
        Z - zlib compressed
        E - encrypted (not supported)
    """
    if not frame_data:
        return None

    encoding_byte = frame_data[0:1]
    payload = frame_data[1:]

    if encoding_byte == b"N":
        return payload
    elif encoding_byte == b"Z":
        try:
            return zlib.decompress(payload)
        except zlib.error as e:
            logger.debug("BLTE zlib error: %s", e)
            return None
    elif encoding_byte == b"E":
        logger.debug("BLTE: encrypted frame (not supported)")
        return None
    else:
        return frame_data

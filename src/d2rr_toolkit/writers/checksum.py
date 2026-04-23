"""D2S file checksum calculation and patching.

The D2S checksum is a 32-bit rotating sum stored at byte offset 0x0C.
Algorithm:
  1. Zero out the 4 checksum bytes.
  2. For every byte in the file (in order):
       checksum = rotate_left_32(checksum, 1)
       checksum = (checksum + byte) & 0xFFFFFFFF
  3. Write the 32-bit result back at offset 0x0C (little-endian).

[VERIFIED] Algorithm sourced from Trevin's D2 file format docs and
d2itemreader. Consistent with all parsed checksums matching their files.
"""

from __future__ import annotations

import struct
import time

_CHECKSUM_OFFSET = 0x0C
_FILE_SIZE_OFFSET = 0x08
_TIMESTAMP_OFFSET = 0x20


def calculate_checksum(data: bytes | bytearray) -> int:
    """Calculate the D2S file checksum over all bytes.

    The checksum field itself must be zeroed before calling this function.

    Returns:
        32-bit unsigned checksum value.
    """
    checksum = 0
    for byte in data:
        checksum = ((checksum << 1) | (checksum >> 31)) & 0xFFFFFFFF
        checksum = (checksum + byte) & 0xFFFFFFFF
    return checksum


def patch_checksum(data: bytearray) -> int:
    """Recalculate and write the checksum into a mutable byte buffer in-place.

    Zeros the checksum field, computes the checksum over all bytes, and
    writes the result back at offset 0x0C.

    Returns:
        The newly computed checksum value.
    """
    struct.pack_into("<I", data, _CHECKSUM_OFFSET, 0)
    checksum = calculate_checksum(data)
    struct.pack_into("<I", data, _CHECKSUM_OFFSET, checksum)
    return checksum


def patch_file_size(data: bytearray) -> None:
    """Update the file size field at offset 0x08 to match the buffer length."""
    struct.pack_into("<I", data, _FILE_SIZE_OFFSET, len(data))


def patch_timestamp(data: bytearray) -> int:
    """Update the 'last saved' timestamp at offset 0x20 to current UNIX time.

    The D2R game engine writes a uint32 UNIX timestamp here on every save.
    Files whose timestamp has not advanced since the last game-save are
    rejected as corrupt ('Failed to join Game').

    **Must be called BEFORE** :func:`patch_checksum` because the checksum
    covers all bytes including the timestamp.

    [BINARY_VERIFIED TC66: defect file had stale timestamp at 0x20,
     correct file (game-saved) had current timestamp. Only difference
     between the two besides the consequent checksum.]

    Returns:
        The UNIX timestamp that was written.
    """
    ts = int(time.time())
    struct.pack_into("<I", data, _TIMESTAMP_OFFSET, ts)
    return ts

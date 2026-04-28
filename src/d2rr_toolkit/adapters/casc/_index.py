"""CASC index file (.idx) parsing - EKey to archive location mapping.

Step 3 of the CASC loading pipeline. Parses the 16 index files (buckets
0x00-0x0F) to build the EKey -> (archive_index, offset, size) map.

Supports both Index V2 (version 0x07) and V1 (version 0x05).

Reference: CascLib by Ladislav Zezula - CascReadFile.cpp
"""

import logging
import struct
from pathlib import Path

logger = logging.getLogger(__name__)


def load_index_files(
    data_dir: Path,
) -> tuple[dict[bytes, tuple[int, int, int]], dict[int, Path], int]:
    """Load all 16 index files and catalog data.### archive files.

    Args:
        data_dir: Path to the Data/ directory inside the game installation.

    Returns:
        (ekey_map, data_files, file_offset_bits) where:
          ekey_map: EKey 9-byte prefix -> (archive_index, archive_offset, encoded_size)
          data_files: archive_index -> Path to data.### file
          file_offset_bits: bit shift for archive index extraction (typically 30)
    """
    idx_dir = data_dir / "data"
    if not idx_dir.is_dir():
        idx_dir = data_dir

    ekey_map: dict[bytes, tuple[int, int, int]] = {}
    data_files: dict[int, Path] = {}
    file_offset_bits = 30

    # Find latest version of each bucket (0x00-0x0F)
    idx_files: dict[int, Path] = {}
    for f in idx_dir.iterdir():
        if f.suffix == ".idx" and len(f.stem) == 10:
            try:
                bucket = int(f.stem[:2], 16)
                version = int(f.stem[2:], 16)
                if bucket not in idx_files or version > int(idx_files[bucket].stem[2:], 16):
                    idx_files[bucket] = f
            except ValueError:
                continue

    for bucket, path in sorted(idx_files.items()):
        fob = _parse_index_file(path, ekey_map)
        if fob is not None:
            file_offset_bits = fob

    # Catalog data.### files
    for f in idx_dir.iterdir():
        if f.name.startswith("data.") and f.name[5:].isdigit():
            data_files[int(f.name[5:])] = f

    return ekey_map, data_files, file_offset_bits


def _parse_index_file(
    path: Path,
    ekey_map: dict[bytes, tuple[int, int, int]],
) -> int | None:
    """Parse a single index file and populate ekey_map.

    Returns file_offset_bits if successfully parsed, None otherwise.
    """
    data = path.read_bytes()
    if len(data) < 40:
        return None

    pos = 0
    block_size = struct.unpack_from("<I", data, pos)[0]
    pos += 8  # skip size + hash

    if pos + 16 > len(data):
        return None
    index_version = struct.unpack_from("<H", data, pos)[0]
    if index_version not in (0x05, 0x07):
        logger.debug("Unsupported index version %d in %s", index_version, path.name)
        return None

    file_offset_bits = None

    if index_version == 0x07:
        enc_size_len = data[pos + 4]
        stor_off_len = data[pos + 5]
        ekey_len = data[pos + 6]
        file_off_bits = data[pos + 7]
        file_offset_bits = file_off_bits
        entry_size = ekey_len + stor_off_len + enc_size_len

        pos = 8 + block_size
        pos = (pos + 15) & ~15
        if pos + 8 > len(data):
            return file_offset_bits
        data_block_size = struct.unpack_from("<I", data, pos)[0]
        pos += 8

        end_pos = pos + data_block_size
        while pos + entry_size <= end_pos:
            ekey = data[pos : pos + ekey_len]
            off_bytes = data[pos + ekey_len : pos + ekey_len + stor_off_len]
            size_bytes = data[
                pos + ekey_len + stor_off_len : pos + ekey_len + stor_off_len + enc_size_len
            ]

            if ekey == b"\x00" * ekey_len:
                pos += entry_size
                continue

            storage_offset = int.from_bytes(off_bytes, "big")
            archive_index = storage_offset >> file_off_bits
            archive_offset = storage_offset & ((1 << file_off_bits) - 1)
            encoded_size = int.from_bytes(size_bytes, "little")

            ekey_map[ekey] = (archive_index, archive_offset, encoded_size)
            pos += entry_size

    elif index_version == 0x05:
        enc_size_len = data[pos + 16]
        stor_off_len = data[pos + 17]
        ekey_len = data[pos + 18]
        file_off_bits = data[pos + 19]
        file_offset_bits = file_off_bits
        ekey_count1 = struct.unpack_from("<I", data, pos + 20)[0]
        ekey_count2 = struct.unpack_from("<I", data, pos + 24)[0]
        entry_size = ekey_len + stor_off_len + enc_size_len
        pos += 44

        for _ in range(ekey_count1 + ekey_count2):
            if pos + entry_size > len(data):
                break
            ekey = data[pos : pos + ekey_len]
            off_bytes = data[pos + ekey_len : pos + ekey_len + stor_off_len]
            size_bytes = data[
                pos + ekey_len + stor_off_len : pos + ekey_len + stor_off_len + enc_size_len
            ]

            if ekey != b"\x00" * ekey_len:
                storage_offset = int.from_bytes(off_bytes, "big")
                archive_index = storage_offset >> file_off_bits
                archive_offset = storage_offset & ((1 << file_off_bits) - 1)
                encoded_size = int.from_bytes(size_bytes, "little")
                ekey_map[ekey] = (archive_index, archive_offset, encoded_size)
            pos += entry_size

    return file_offset_bits

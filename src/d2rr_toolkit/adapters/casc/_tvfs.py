"""CASC TVFS (Table Virtual File System) root parsing - path to CKey mapping.

Step 5 of the CASC loading pipeline. Walks the TVFS prefix tree to map
file paths to their content keys (CKeys).

The TVFS is hierarchical: the root manifest contains folder entries that
reference sub-VFS files (vfs-1, vfs-2, ...). File entries in those sub-VFS
files contain the actual path -> CKey mappings.

Reference: CascLib by Ladislav Zezula - CascRootFile_TVFS.cpp
"""

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)


def parse_tvfs_root(
    root_data: bytes,
    vfs_entries: list[tuple[bytes, bytes]],
    path_map: dict[str, bytes],
    ekey_to_ckey: dict[bytes, bytes],
    read_by_ekey: Callable[[bytes], bytes | None],
) -> None:
    """Load VFS root and sub-directories to build the path -> CKey map.

    Args:
        root_data: Decompressed root VFS file content.
        vfs_entries: List of (ckey, ekey) pairs from build config.
        path_map: Dict to populate with path -> CKey entries.
        ekey_to_ckey: Reverse map of 9-byte EKey prefix -> CKey.
        read_by_ekey: Callback to read and decompress a file by its EKey.
    """
    # Build set of known VFS EKeys for sub-VFS detection
    vfs_ekeys: set[bytes] = set()
    for _ckey, ekey in vfs_entries:
        vfs_ekeys.add(ekey[:9])

    if root_data[:4] == b"TVFS":
        _parse_tvfs(root_data, "", vfs_ekeys, path_map, ekey_to_ckey, read_by_ekey)
    else:
        _parse_text_root(root_data, path_map)


def _parse_tvfs(
    data: bytes,
    prefix: str,
    vfs_ekeys: set[bytes],
    path_map: dict[str, bytes],
    ekey_to_ckey: dict[bytes, bytes],
    read_by_ekey: Callable[[bytes], bytes | None],
) -> None:
    """Parse a TVFS directory structure."""
    if len(data) < 32 or data[:4] != b"TVFS":
        return

    ekey_size = data[6]
    flags = int.from_bytes(data[8:12], "big")

    path_table_off = int.from_bytes(data[12:16], "big")
    path_table_size = int.from_bytes(data[16:20], "big")
    vfs_table_off = int.from_bytes(data[20:24], "big")
    vfs_table_size = int.from_bytes(data[24:28], "big")
    cft_table_off = int.from_bytes(data[28:32], "big")
    cft_table_size = int.from_bytes(data[32:36], "big")

    cft_off_size = _min_bytes_for(cft_table_size)

    _parse_tvfs_path_tree(
        data,
        path_table_off,
        path_table_off + path_table_size,
        vfs_table_off,
        cft_table_off,
        ekey_size,
        cft_off_size,
        prefix,
        vfs_ekeys,
        path_map,
        ekey_to_ckey,
        read_by_ekey,
    )


def _parse_tvfs_path_tree(
    data: bytes,
    pos: int,
    end: int,
    vfs_off: int,
    cft_off: int,
    ekey_size: int,
    cft_off_size: int,
    path: str,
    vfs_ekeys: set[bytes],
    path_map: dict[str, bytes],
    ekey_to_ckey: dict[bytes, bytes],
    read_by_ekey: Callable[[bytes], bytes | None],
) -> None:
    """Parse TVFS path table entries - exact CascLib algorithm.

    Each entry: [opt 0x00 pre-sep] [len+name] [opt 0x00 post-sep] [0xFF + 4B]

    The path buffer is saved ONCE at the start of this recursion level.
    Within the loop, fragments accumulate into `path`. When a node value
    (0xFF) is processed, `path` is restored to `saved_path` for the
    next sibling. This matches CascLib's PathBuffer.Save()/Restore().
    """
    saved_path = path

    while pos < end:
        # Step 1: Optional pre-separator
        if pos < end and data[pos] == 0x00:
            pos += 1
            if path and not path.endswith("/") and not path.endswith(":"):
                path += "/"

        # Step 2: Name fragment
        if pos < end and data[pos] != 0xFF:
            name_len = data[pos]
            pos += 1
            if pos + name_len > end:
                break
            path += data[pos : pos + name_len].decode("utf-8", errors="replace")
            pos += name_len

        # Step 3: Post-separator
        has_node = False
        if pos < end and data[pos] == 0x00:
            pos += 1
            if path and not path.endswith("/") and not path.endswith(":"):
                path += "/"
        elif pos < end and data[pos] == 0xFF:
            has_node = True
        elif pos < end:
            if path and not path.endswith("/") and not path.endswith(":"):
                path += "/"

        # Step 4: Node value (0xFF marker)
        if has_node or (pos < end and data[pos] == 0xFF):
            pos += 1  # skip 0xFF
            if pos + 4 > end:
                break
            node_val = int.from_bytes(data[pos : pos + 4], "big")
            pos += 4

            if node_val & 0x80000000:
                # Folder node: recurse into children
                child_len = (node_val & 0x7FFFFFFF) - 4
                child_end = pos + child_len
                _parse_tvfs_path_tree(
                    data,
                    pos,
                    min(child_end, end),
                    vfs_off,
                    cft_off,
                    ekey_size,
                    cft_off_size,
                    path,
                    vfs_ekeys,
                    path_map,
                    ekey_to_ckey,
                    read_by_ekey,
                )
                pos = child_end
            else:
                # File leaf: resolve VFS -> CFT -> EKey
                vfs_pos = vfs_off + node_val
                ekey = _read_vfs_ekey(data, vfs_pos, cft_off, ekey_size, cft_off_size)
                if ekey is not None:
                    ekey9 = ekey[:9]
                    if ekey9 in vfs_ekeys:
                        sub_data = read_by_ekey(ekey)
                        if sub_data and sub_data[:4] == b"TVFS":
                            sub_prefix = path + ":" if path else ""
                            _parse_tvfs(
                                sub_data,
                                sub_prefix,
                                vfs_ekeys,
                                path_map,
                                ekey_to_ckey,
                                read_by_ekey,
                            )
                    else:
                        ckey = ekey_to_ckey.get(ekey9)
                        if ckey is not None:
                            path_map[path] = ckey
                        else:
                            path_map[path] = ekey + b"\x00" * (16 - len(ekey))

            # Restore path for next sibling
            path = saved_path


def _read_vfs_ekey(
    data: bytes,
    vfs_pos: int,
    cft_off: int,
    ekey_size: int,
    cft_off_size: int,
) -> bytes | None:
    """Read the EKey for a file entry from the VFS + CFT tables."""
    if vfs_pos >= len(data):
        return None

    span_count = data[vfs_pos]
    if span_count == 0 or span_count > 224:
        return None

    pos = vfs_pos + 1
    span_entry_size = 4 + 4 + cft_off_size

    if pos + span_entry_size > len(data):
        return None

    cft_offset_bytes = data[pos + 8 : pos + 8 + cft_off_size]
    cft_entry_off = int.from_bytes(cft_offset_bytes, "big")

    cft_pos = cft_off + cft_entry_off
    if cft_pos + ekey_size <= len(data):
        return data[cft_pos : cft_pos + ekey_size]

    return None


def _parse_text_root(data: bytes, path_map: dict[str, bytes]) -> None:
    """Parse a text-based root file (pipe-delimited path|ckey)."""
    for line in data.split(b"\r\n"):
        parts = line.split(b"|")
        if len(parts) >= 2:
            path = parts[0].decode("utf-8", errors="replace")
            ckey_hex = parts[1].decode("ascii", errors="replace")
            if ckey_hex and len(ckey_hex) == 32:
                try:
                    path_map[path] = bytes.fromhex(ckey_hex)
                except ValueError:
                    continue


def _min_bytes_for(size: int) -> int:
    """Return minimum byte count to represent a value up to `size`."""
    if size <= 0xFF:
        return 1
    if size <= 0xFFFF:
        return 2
    if size <= 0xFFFFFF:
        return 3
    return 4

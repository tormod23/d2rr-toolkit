"""CASC ENCODING manifest parsing - CKey to EKey mapping.

Step 4 of the CASC loading pipeline. The ENCODING file maps content keys
(CKey, MD5 of uncompressed content) to encoded keys (EKey, MD5 of encoded
content) and content sizes.

Reference: CascLib by Ladislav Zezula - CascRootFile_Text.cpp
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def load_encoding(
    raw: bytes,
    ckey_map: dict[bytes, tuple[bytes, int]],
) -> None:
    """Parse the ENCODING manifest and populate the CKey -> (EKey, size) map.

    Args:
        raw: Decompressed ENCODING file content.
        ckey_map: Dict to populate with CKey -> (EKey_16, content_size) entries.
    """
    if not raw or len(raw) < 22:
        logger.error("Failed to load ENCODING manifest")
        return

    if raw[:2] != b"EN":
        logger.error("Invalid ENCODING magic: %s", raw[:2])
        return

    ckey_len = raw[3]  # 16
    ekey_len = raw[4]  # 16
    ckey_page_size_kb = int.from_bytes(raw[5:7], "big")
    ekey_page_size_kb = int.from_bytes(raw[7:9], "big")
    ckey_page_count = int.from_bytes(raw[9:13], "big")
    ekey_page_count = int.from_bytes(raw[13:17], "big")
    espec_size = int.from_bytes(raw[18:22], "big")

    ckey_page_size = ckey_page_size_kb * 1024
    pos = 22 + espec_size  # skip espec block

    # Skip CKey page table (ckey_page_count * 32 bytes)
    pos += ckey_page_count * 32

    # Parse CKey pages
    for _page in range(ckey_page_count):
        page_end = pos + ckey_page_size
        while pos + 6 + ckey_len + ekey_len <= page_end:
            ekey_count = int.from_bytes(raw[pos : pos + 2], "little")
            if ekey_count == 0:
                break
            content_size = int.from_bytes(raw[pos + 2 : pos + 6], "big")
            ckey = raw[pos + 6 : pos + 6 + ckey_len]
            ekey = raw[pos + 6 + ckey_len : pos + 6 + ckey_len + ekey_len]
            ckey_map[ckey] = (ekey, content_size)
            pos += 6 + ckey_len + ekey_count * ekey_len
        pos = page_end


def build_ekey_to_ckey_map(
    ckey_map: dict[bytes, tuple[bytes, int]],
) -> dict[bytes, bytes]:
    """Build a reverse EKey-prefix-to-CKey lookup map.

    Turns the O(n) linear scan during TVFS resolution into O(1) dict lookup.

    Args:
        ckey_map: The CKey -> (EKey, size) map from load_encoding().

    Returns:
        Dict mapping 9-byte EKey prefix -> 16-byte CKey.
    """
    return {ekey[:9]: ckey for ckey, (ekey, _) in ckey_map.items()}


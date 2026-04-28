"""Parse .build.info and build config files for CASC archives.

Step 1+2 of the CASC loading pipeline:
  1. .build.info -> active build key + CDN key
  2. Build config -> encoding keys + VFS root entries

Reference: CascLib by Ladislav Zezula - CascOpenStorage.cpp
"""

import csv
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def parse_build_info(game_dir: Path) -> tuple[bytes, bytes]:
    """Parse .build.info and return (build_key, cdn_key) as raw 16-byte keys.

    Raises:
        FileNotFoundError: if .build.info does not exist.
        ValueError: if no active build is found.
    """
    bi_path = game_dir / ".build.info"
    if not bi_path.exists():
        raise FileNotFoundError(f".build.info not found in {game_dir}")

    with open(bi_path, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="|")
        header = next(reader)
        col_map = {}
        for i, h in enumerate(header):
            name = h.split("!")[0].strip()
            col_map[name] = i

        for row in reader:
            active_col = col_map.get("Active", -1)
            if active_col >= 0 and row[active_col].strip() == "1":
                bk = bytes.fromhex(row[col_map["Build Key"]].strip())
                ck = bytes.fromhex(row[col_map["CDN Key"]].strip())
                return bk, ck

    raise ValueError("No active build found in .build.info")


def load_build_config(
    data_dir: Path,
    build_key: bytes,
) -> tuple[bytes, bytes, list[tuple[bytes, bytes]]]:
    """Load the build config file and extract encoding + VFS keys.

    Args:
        data_dir: Path to the Data/ directory inside the game installation.
        build_key: 16-byte build key from .build.info.

    Returns:
        (encoding_ckey, encoding_ekey, [(vfs_ckey, vfs_ekey), ...])

    Raises:
        FileNotFoundError: if the config file does not exist.
    """
    hex_key = build_key.hex()
    config_path = data_dir / "config" / hex_key[:2] / hex_key[2:4] / hex_key
    if not config_path.exists():
        raise FileNotFoundError(f"Build config not found: {config_path}")

    config = {}
    with open(config_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, _, value = line.partition("=")
                config[key.strip()] = value.strip()

    # Encoding: "ckey ekey" (two hex strings)
    enc_parts = config.get("encoding", "").split()
    enc_ckey = bytes.fromhex(enc_parts[0]) if len(enc_parts) >= 1 else b""
    enc_ekey = bytes.fromhex(enc_parts[1]) if len(enc_parts) >= 2 else b""

    # VFS entries: vfs-root, vfs-1, vfs-2, etc. (skip vfs-N-size entries)
    vfs_entries = []
    for key in sorted(config.keys()):
        if re.match(r"^vfs(-root|-\d+)$", key):
            parts = config[key].split()
            if len(parts) >= 2 and len(parts[0]) == 32 and len(parts[1]) == 32:
                vfs_entries.append((bytes.fromhex(parts[0]), bytes.fromhex(parts[1])))

    return enc_ckey, enc_ekey, vfs_entries

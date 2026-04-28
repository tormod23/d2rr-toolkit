"""Pure-Python CASC archive reader for Diablo II Resurrected.

Reads files from the D2R CASC storage without any native dependencies.
Based on the CascLib algorithms by Ladislav Zezula
(github.com/ladislav-zezula/CascLib).

The CASC format uses a multi-level indirection::

    file_path -> CKey (content hash) -> EKey (encoded hash)
              -> archive location -> BLTE data

Usage::

    from d2rr_toolkit.adapters.casc import CASCReader

    reader = CASCReader(Path(r"C:/Program Files (x86)/Diablo II Resurrected"))
    data = reader.read_file(
        "data:data/hd/global/ui/items/armor/armor/quilted_armor.sprite"
    )

With mod overlay::

    reader = CASCReader(game_dir, mod_dir=Path(r".../mods/Reimagined/Reimagined.mpq"))
    # Mod files take priority over CASC for read_file() and has_file()
"""

import fnmatch
import logging
from pathlib import Path

from d2rr_toolkit.adapters.casc._blte import decode_blte
from d2rr_toolkit.adapters.casc._buildinfo import (
    load_build_config,
    parse_build_info,
)
from d2rr_toolkit.adapters.casc._encoding import (
    build_ekey_to_ckey_map,
    load_encoding,
)
from d2rr_toolkit.adapters.casc._index import load_index_files
from d2rr_toolkit.adapters.casc._tvfs import parse_tvfs_root

logger = logging.getLogger(__name__)


class CASCReader:
    """Read files from a local D2R CASC archive.

    Args:
        game_dir: Path to the D2R installation root (containing .build.info).
        mod_dir:  Optional mod directory. When set, read_file() and has_file()
                  check for mod-overlaid files on disk before falling back to
                  the CASC archive.
    """

    def __init__(self, game_dir: Path, mod_dir: Path | None = None) -> None:
        self._game_dir = game_dir
        self._mod_dir = mod_dir
        self._data_dir = game_dir / "Data"
        if not self._data_dir.is_dir():
            self._data_dir = game_dir / "data"

        # EKey (9 bytes) -> (archive_index, archive_offset, encoded_size)
        self._ekey_map: dict[bytes, tuple[int, int, int]] = {}
        # CKey (16 bytes) -> (EKey_16, content_size)
        self._ckey_map: dict[bytes, tuple[bytes, int]] = {}
        # file path -> CKey (16 bytes)
        self._path_map: dict[str, bytes] = {}
        # Reverse: EKey 9-byte prefix -> CKey (16 bytes)
        self._ekey_to_ckey: dict[bytes, bytes] = {}

        self._file_offset_bits: int = 30
        self._data_files: dict[int, Path] = {}

        self._load()

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def file_count(self) -> int:
        """Number of indexed file paths in the CASC archive."""
        return len(self._path_map)

    @property
    def game_dir(self) -> Path:
        """D2R installation root path."""
        return self._game_dir

    @property
    def mod_dir(self) -> Path | None:
        """Mod overlay directory, or None if not configured."""
        return self._mod_dir

    # ── Public API: File Access ──────────────────────────────────────────────

    def read_file(self, path: str) -> bytes | None:
        """Read a file by its CASC path.

        If a mod_dir is configured, checks for the file on disk first
        (mod files override CASC). Falls back to the CASC archive.

        Args:
            path: CASC file path, e.g. "data:data/global/excel/weapons.txt"

        Returns:
            File content as bytes, or None if not found.
        """
        # Mod overlay: check disk first
        if self._mod_dir is not None:
            mod_file = self._resolve_mod_path(path)
            if mod_file is not None and mod_file.is_file():
                return mod_file.read_bytes()

        # CASC lookup
        ckey = self._path_map.get(path)
        if ckey is None:
            return None
        return self.read_by_ckey(ckey)

    def read_by_ckey(self, ckey: bytes) -> bytes | None:
        """Read a file by its 16-byte content key (CKey).

        No mod overlay - CKeys are CASC-specific.
        """
        entry = self._ckey_map.get(ckey)
        if entry is None:
            return None
        ekey, content_size = entry
        return self._read_by_ekey(ekey)

    def has_file(self, path: str) -> bool:
        """Check if a file exists (mod overlay + CASC)."""
        if self._mod_dir is not None:
            mod_file = self._resolve_mod_path(path)
            if mod_file is not None and mod_file.is_file():
                return True
        return path in self._path_map

    # ── Public API: File Discovery ───────────────────────────────────────────

    def list_files(self, pattern: str = "*") -> list[str]:
        """List all CASC file paths matching a glob pattern.

        Uses fnmatch-style patterns. Supports ``*``, ``?``, ``[seq]``.
        For recursive matching use ``**`` (e.g. ``"data:data/**/*.sprite"``).

        Examples::

            reader.list_files("data:data/hd/global/ui/items/**/*.sprite")
            reader.list_files("data:data/global/excel/*.txt")
            reader.list_files("*")  # all files

        Args:
            pattern: fnmatch glob pattern. Default "*" returns all paths.

        Returns:
            Sorted list of matching file paths.
        """
        if pattern == "*":
            return sorted(self._path_map.keys())

        # For ** patterns, use a filter that treats ** as matching any path segment
        if "**" in pattern:
            # Convert ** to fnmatch-compatible: replace ** with *
            # fnmatch's * already matches everything including /
            simple_pattern = pattern.replace("**", "*")
            return sorted(p for p in self._path_map if fnmatch.fnmatch(p, simple_pattern))

        return sorted(p for p in self._path_map if fnmatch.fnmatch(p, pattern))

    def resolve_ckey(self, path: str) -> bytes | None:
        """Return the 16-byte content key for a CASC path without reading the file.

        Useful for caching and deduplication (CKey = MD5 of uncompressed content).

        Args:
            path: CASC file path.

        Returns:
            16-byte CKey, or None if path not found in the archive.
        """
        return self._path_map.get(path)

    # ── Mod Overlay ──────────────────────────────────────────────────────────

    def _resolve_mod_path(self, casc_path: str) -> Path | None:
        """Convert a CASC path to a local mod file path.

        Strips the "prefix:" part and joins with mod_dir.
        E.g. ``"data:data/global/excel/weapons.txt"``
           -> ``mod_dir / "data" / "global" / "excel" / "weapons.txt"``.

        Containment invariant: the returned path is guaranteed to be
        strictly inside ``self._mod_dir`` (after symlink resolution).
        Any input that would escape the mod overlay -- via ``..`` segments,
        absolute paths, drive letters, URL-like schemes, or mixed
        separator tricks -- is rejected and returns ``None``.

        Returns ``None`` silently on rejection so the caller transparently
        falls through to the CASC archive, and no timing / error oracle
        is exposed to an attacker feeding crafted paths.
        """
        if self._mod_dir is None:
            return None
        # Strip sub-VFS prefix (e.g. "data:")
        if ":" in casc_path:
            rel = casc_path.split(":", 1)[1]
        else:
            rel = casc_path
        # Reject any attempt to escape mod_dir via "..", absolute paths,
        # drive letters, or URL-like schemes. We resolve both sides so
        # symlinks inside mod_dir still work transparently.
        try:
            mod_root = self._mod_dir.resolve(strict=False)
            candidate = (mod_root / rel).resolve(strict=False)
        except OSError, ValueError:
            return None
        try:
            candidate.relative_to(mod_root)
        except ValueError:
            logger.warning(
                "CASC mod-path rejected (escapes mod_dir): %r",
                casc_path,
            )
            return None
        return candidate

    # ── Loading Pipeline ─────────────────────────────────────────────────────

    def _load(self) -> None:
        """Load the complete CASC index (5-step pipeline)."""
        # Step 1: .build.info
        build_key, cdn_key = parse_build_info(self._game_dir)
        logger.info("Build key: %s", build_key.hex())

        # Step 2: Build config
        enc_ckey, enc_ekey, vfs_entries = load_build_config(self._data_dir, build_key)
        logger.info("Encoding CKey: %s, EKey: %s", enc_ckey.hex(), enc_ekey.hex())

        # Step 3: Index files
        self._ekey_map, self._data_files, self._file_offset_bits = load_index_files(self._data_dir)
        logger.info("Index: %d EKey entries", len(self._ekey_map))

        # Step 4: ENCODING manifest
        enc_raw = self._read_by_ekey(enc_ekey)
        if enc_raw is None:
            raise RuntimeError(
                f"CASC ENCODING blob not found by EKey {enc_ekey.hex()}; "
                "build config / index files are inconsistent."
            )
        load_encoding(enc_raw, self._ckey_map)
        logger.info("Encoding: %d CKey entries", len(self._ckey_map))

        # Build reverse EKey->CKey map
        self._ekey_to_ckey = build_ekey_to_ckey_map(self._ckey_map)
        logger.info("EKey->CKey reverse map: %d entries", len(self._ekey_to_ckey))

        # Step 5: TVFS root
        if vfs_entries:
            root_ckey, root_ekey = vfs_entries[0]
            root_data = self._read_by_ekey(root_ekey)
            if root_data:
                parse_tvfs_root(
                    root_data,
                    vfs_entries,
                    self._path_map,
                    self._ekey_to_ckey,
                    self._read_by_ekey,
                )
        logger.info("VFS root: %d file paths indexed", len(self._path_map))

    def _read_by_ekey(self, ekey: bytes) -> bytes | None:
        """Read and BLTE-decompress a file by its encoded key (EKey)."""
        ekey9 = ekey[:9]
        location = self._ekey_map.get(ekey9)
        if location is None:
            return None

        archive_idx, archive_off, encoded_size = location

        data_path = self._data_files.get(archive_idx)
        if data_path is None or not data_path.exists():
            return None

        with open(data_path, "rb") as f:
            f.seek(archive_off)
            raw = f.read(encoded_size + 0x1E)

        return decode_blte(raw)

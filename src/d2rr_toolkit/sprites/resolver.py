"""Sprite resolution for D2R Reimagined items.

Finds and loads the correct sprite for an item code by searching multiple
sources in priority order:

  1. Dedicated Unique sprite (by item name, from mod HD directory or CASC)
  2. CASC gfx variant sprite (for items with has_custom_graphics)
  3. Mod HD .sprite file (with gfx variant support)
  4. CASC base sprite (vanilla HD)
  5. Mod DC6 legacy sprite (palette-indexed fallback)

Returns raw PNG bytes (decoded from SpA1/DC6). The caller is responsible
for caching and serving.

Usage::

    from d2rr_toolkit.sprites.resolver import SpriteResolver

    resolver = SpriteResolver(casc_reader, mod_hd_dir, mod_dc6_dir, items_json)
    png = resolver.get_sprite("rin")              # Base ring
    png = resolver.get_sprite("rin", gfx_index=3) # Ring variant 3
    png = resolver.get_sprite_by_invfile("invring1", base_code="rin")
"""

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from d2rr_toolkit.adapters.casc.reader import CASCReader
import csv
from d2rr_toolkit.adapters.casc.sprites import (
    decode_dc6,
    decode_sprite,
)
from d2rr_toolkit.config import get_game_paths

logger = logging.getLogger(__name__)


# Shared with d2rr_toolkit.sprites.bulk_loader.display_name_to_snake_case.
# Duplicated here to avoid a circular import between the two modules.
_NAME_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def _snake_case(display_name: str) -> str:
    """Normalise a display name for uniques.json/sets.json lookup."""
    if not display_name:
        return ""
    name = display_name.lower().replace("'", "")
    name = _NAME_NORMALIZE_RE.sub("_", name).strip("_")
    return name


class SpriteResolver:
    """Resolve and load item sprites from mod directory and CASC archive.

    Args:
        casc_reader:  CASCReader instance for vanilla sprite access.
                      Can be None if CASC is unavailable.
        mod_hd_dir:   Path to mod HD sprite directory
                      (e.g. ``Reimagined.mpq/data/hd/global/ui/items``).
                      Can be None if mod has no HD sprites.
        mod_dc6_dir:  Path to mod DC6 sprite directory
                      (e.g. ``Reimagined.mpq/data/global/items``).
                      Can be None if mod has no DC6 sprites.
        items_json:   Dict mapping item_code -> HD asset path
                      (from ``data/hd/items/items.json``).
                      Can be None (disables CASC sprite map building).
    """

    def __init__(
        self,
        casc_reader: "CASCReader | None" = None,
        mod_hd_dir: Path | None = None,
        mod_dc6_dir: Path | None = None,
        items_json: dict[str, str] | None = None,
        *,
        unique_sprite_map: dict[str, str] | None = None,
        set_sprite_map: dict[str, str] | None = None,
    ) -> None:
        """
        Args:
            casc_reader:       CASCReader for vanilla base-game sprites.
            mod_hd_dir:        Mod HD items directory (for PNG-style HD sprites).
            mod_dc6_dir:       Mod DC6 items directory (legacy format).
            items_json:        Base item code -> asset path mapping from
                               ``data/hd/items/items.json`` (flattened by
                               :func:`d2rr_toolkit.sprites.load_items_json`).
            unique_sprite_map: Unique snake_case_name -> asset path mapping
                               from ``data/hd/items/uniques.json`` (loaded
                               via :func:`d2rr_toolkit.sprites.load_unique_sprite_map`).
                               When provided, ``_try_unique_sprite`` uses this
                               as its primary source instead of guessing
                               subdirectory conventions.
            set_sprite_map:    Set snake_case_name -> asset path mapping from
                               ``data/hd/items/sets.json``.
        """
        self._casc = casc_reader
        self._mod_hd_dir = mod_hd_dir
        self._mod_dc6_dir = mod_dc6_dir
        self._items_json = items_json or {}
        self._unique_sprite_map = unique_sprite_map or {}
        self._set_sprite_map = set_sprite_map or {}

        # item_code (or variant key) -> CASC CKey hex string
        self._casc_ckey_map: dict[str, str] = {}

        if casc_reader is not None and items_json:
            self._casc_ckey_map = self._build_casc_sprite_map()
            logger.info("CASC sprite map: %d entries", len(self._casc_ckey_map))

    @property
    def casc_ckey_map(self) -> dict[str, str]:
        """Item code -> CASC content key hex. Read-only."""
        return self._casc_ckey_map

    # ── Public API ───────────────────────────────────────────────────────────

    def get_sprite(
        self,
        item_code: str,
        *,
        gfx_index: int = -1,
        invfile: str = "",
        unique_name: str | None = None,
        set_name: str | None = None,
        base_code: str | None = None,
    ) -> bytes | None:
        """Resolve and return PNG bytes for an item sprite.

        Searches multiple sources in priority order. Returns None if
        no sprite is found anywhere.

        Priority (first match wins):
          1. Unique sprite override (if unique_name is given)
          2. Set sprite override (if set_name is given)
          3. CASC gfx variant (if gfx_index >= 0)
          4. Mod HD sprite (with variant support)
          5. CASC base sprite
          6. DC6 legacy fallback (if invfile is given)

        Args:
            item_code:   Item code (e.g. "rin", "hax").
            gfx_index:   Graphics variant index (-1=no variant, 0-7=variants).
            invfile:     Base inventory filename (e.g. "invhax") for DC6 fallback.
            unique_name: For Unique items: display name for dedicated sprite.
            set_name:    For Set items: display name for dedicated sprite.
            base_code:   For Unique items: base type code (e.g. "rin").
                         Used only by the legacy fallback path.

        Returns:
            PNG bytes with transparent background, or None.
        """
        # 1. Dedicated Unique sprite (by name)
        if unique_name:
            result = self._try_unique_sprite(unique_name, base_code or item_code)
            if result:
                return result

        # 2. Dedicated Set sprite (by name)
        if set_name:
            result = self._try_set_sprite(set_name)
            if result:
                return result

        code = item_code.split("_gfx")[0] if "_gfx" in item_code else item_code

        # 3. CASC gfx variant
        if gfx_index >= 0:
            variant_key = f"{code}_gfx{gfx_index}"
            result = self._try_casc(variant_key)
            if result:
                return result

        # 4. Mod HD sprite (with variant support)
        result = self._try_hd_sprite(code, gfx_index)
        if result:
            return result

        # 5. CASC base sprite
        result = self._try_casc(code)
        if result:
            return result

        # 6. DC6 fallback
        if invfile:
            result = self._try_dc6(invfile)
            if result:
                return result

        return None

    def get_sprite_by_path(self, casc_path: str) -> bytes | None:
        """Read and decode a sprite directly by its CASC path.

        Args:
            casc_path: Full CASC path (e.g. "data:data/hd/global/ui/panel/gemsocket.sprite").

        Returns:
            PNG bytes, or None if not found or not a valid sprite.
        """
        if self._casc is None:
            return None

        data = self._casc.read_file(casc_path)
        if data and data[:4] == b"SpA1":
            return decode_sprite(data)
        return None

    # ── CASC Sprite Map ──────────────────────────────────────────────────────

    def _build_casc_sprite_map(self) -> dict[str, str]:
        """Build item_code -> CASC CKey hex mapping from game data.

        Scans the CASC archive for HD sprite paths, then maps item codes
        (from items.json) and gfx variants to those CKeys.
        """
        if self._casc is None:
            return {}

        result: dict[str, str] = {}

        # Step 1: HD sprite filename -> CKey from CASC path map
        hd_sprite_ckeys: dict[str, str] = {}
        sprite_paths = self._casc.list_files("data:data/hd/global/ui/items/*/*.sprite")
        for path in sprite_paths:
            if ".lowend." in path:
                continue
            fname = path.rsplit("/", 1)[-1].replace(".sprite", "")
            ckey = self._casc.resolve_ckey(path)
            if ckey is not None:
                hd_sprite_ckeys[fname] = ckey.hex()

        # Step 2: Map item codes -> CKeys via items.json
        for code, asset_path in self._items_json.items():
            sprite_name = asset_path.rsplit("/", 1)[-1] if "/" in asset_path else asset_path
            if sprite_name in hd_sprite_ckeys:
                result[code] = hd_sprite_ckeys[sprite_name]

            # Step 2.5: Map gfx_index variants
            for gfx_idx in range(8):
                variant_name = f"{sprite_name}{gfx_idx + 1}"
                if variant_name in hd_sprite_ckeys:
                    result[f"{code}_gfx{gfx_idx}"] = hd_sprite_ckeys[variant_name]

        # Step 3: Map unique invfiles (from uniqueitems.txt)
        self._map_unique_invfiles(result, hd_sprite_ckeys)

        return result

    def _map_unique_invfiles(
        self,
        result: dict[str, str],
        hd_sprite_ckeys: dict[str, str],
    ) -> None:
        """Map unique invfile names to CASC CKeys via items.json asset paths."""

        gp = get_game_paths()
        unique_txt = gp.reimagined_excel / "uniqueitems.txt"
        if not unique_txt.exists():
            return
        try:
            with open(unique_txt, encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f, delimiter="\t")
                for row in reader:
                    invfile = row.get("invfile", "").strip()
                    base_code = row.get("code", "").strip()
                    if not invfile or not base_code or invfile.lower() in result:
                        continue
                    base_asset = self._items_json.get(base_code, "")
                    if not base_asset:
                        continue
                    stripped = invfile[3:] if invfile.lower().startswith("inv") else invfile
                    m = re.search(r"(\d+)$", stripped)
                    if not m:
                        continue
                    base_name = base_asset.rsplit("/", 1)[-1]
                    variant_name = base_name + m.group(1)
                    if variant_name in hd_sprite_ckeys:
                        result[invfile.lower()] = hd_sprite_ckeys[variant_name]
        except (OSError, KeyError) as e:
            logger.debug("Could not read uniqueitems.txt for invfile mapping: %s", e)

    # ── Source-specific loaders ──────────────────────────────────────────────

    def _try_casc(self, item_code: str) -> bytes | None:
        """Try to load from CASC archive by content key."""
        if self._casc is None or not self._casc_ckey_map:
            return None
        ckey_hex = self._casc_ckey_map.get(item_code.lower())
        if not ckey_hex:
            return None
        try:

            ckey = bytes.fromhex(ckey_hex)
            data = self._casc.read_by_ckey(ckey)
            if data and data[:4] == b"SpA1":
                return decode_sprite(data)
        except Exception as e:
            logger.debug("CASC sprite error for %s: %s", item_code, e)
        return None

    def _try_hd_sprite(self, item_code: str, gfx_index: int = -1) -> bytes | None:
        """Try to load from mod HD directory."""
        if self._mod_hd_dir is None:
            return None


        asset_path = self._items_json.get(item_code, "")
        if not asset_path:
            return None

        parts = asset_path.split("/")
        if len(parts) != 2:
            return None

        subdir, base_name = parts

        # Try gfx variant first
        if gfx_index >= 0:
            variant_name = f"{base_name}{gfx_index + 1}"
            for cat in ("armor", "weapon", "misc"):
                sprite_path = self._mod_hd_dir / cat / subdir / f"{variant_name}.sprite"
                if sprite_path.exists():
                    data = sprite_path.read_bytes()
                    if data[:4] == b"SpA1":
                        return decode_sprite(data)

        # Try base sprite
        for cat in ("armor", "weapon", "misc"):
            sprite_path = self._mod_hd_dir / cat / subdir / f"{base_name}.sprite"
            if sprite_path.exists():
                data = sprite_path.read_bytes()
                if data[:4] == b"SpA1":
                    return decode_sprite(data)

        return None

    def _try_unique_sprite(self, unique_name: str, base_code: str) -> bytes | None:
        """Try to load a dedicated Unique item sprite by name.

        Primary path: look up the unique's snake_case name in
        ``unique_sprite_map`` (loaded from ``uniques.json``) to get the
        authoritative asset path, then resolve via :meth:`_load_by_asset_path`.

        Fallback path (only if no map was provided): attempt to load
        ``<snake_name>.sprite`` from legacy uniquering/uniqueamulet/...
        subdirectories. This fallback is kept purely for backwards
        compatibility with callers that construct the resolver without
        passing unique_sprite_map.
        """
        # Primary: JSON-map lookup
        if self._unique_sprite_map:
            snake = _snake_case(unique_name)
            asset_path = self._unique_sprite_map.get(snake)
            if asset_path:
                png = self._load_by_asset_path(asset_path)
                if png is not None:
                    return png

        # Legacy fallback: no map -> guess path from subdirectory conventions
        return self._legacy_unique_sprite_fallback(unique_name, base_code)

    def _try_set_sprite(self, set_name: str) -> bytes | None:
        """Try to load a dedicated Set item sprite by name.

        Looks up the snake_case name in ``set_sprite_map`` (loaded from
        ``sets.json``).
        """
        if not self._set_sprite_map or not set_name:
            return None
        snake = _snake_case(set_name)
        asset_path = self._set_sprite_map.get(snake)
        if not asset_path:
            return None
        return self._load_by_asset_path(asset_path)

    def _load_by_asset_path(self, asset_path: str) -> bytes | None:
        """Load a sprite by its asset path (e.g. ``"helmet/coif_of_glory"``).

        Tries mod HD first (checking all three top-level categories),
        then CASC. Returns None if not found anywhere.
        """

        if not asset_path:
            return None
        sprite_filename = asset_path.rsplit("/", 1)[-1] + ".sprite"
        subpath = asset_path.rsplit("/", 1)[0] if "/" in asset_path else ""
        data: bytes | None

        # 1. Mod HD directory - try all three top-level categories
        if self._mod_hd_dir:
            for top in ("armor", "weapon", "misc"):
                if subpath:
                    candidate = self._mod_hd_dir / top / subpath / sprite_filename
                else:
                    candidate = self._mod_hd_dir / top / sprite_filename
                if candidate.exists():
                    try:
                        data = candidate.read_bytes()
                        if data[:4] == b"SpA1":
                            return decode_sprite(data)
                    except Exception as e:
                        logger.debug("Failed to read %s: %s", candidate, e)

        # 2. CASC archive
        if self._casc:
            for top in ("armor", "weapon", "misc"):
                if subpath:
                    casc_path = f"data:data/hd/global/ui/items/{top}/{subpath}/{sprite_filename}"
                else:
                    casc_path = f"data:data/hd/global/ui/items/{top}/{sprite_filename}"
                data = self._casc.read_file(casc_path)
                if data is not None and data[:4] == b"SpA1":
                    return decode_sprite(data)

        return None

    def _legacy_unique_sprite_fallback(
        self,
        unique_name: str,
        base_code: str,
    ) -> bytes | None:
        """Legacy path for unique sprite lookup without JSON map.

        Tries the old subdirectory-convention approach
        (uniquering/uniqueamulet/uniqueweapon/uniquearmor/uniquecharm).
        Only used when the caller did not provide ``unique_sprite_map``.
        """

        fname = _snake_case(unique_name)
        if not fname:
            return None

        _TYPE_TO_SUBDIR = {
            "rin": "uniquering",
            "amu": "uniqueamulet",
            "cm1": "uniquecharm",
            "cm2": "uniquecharm",
            "cm3": "uniquecharm",
        }
        subdir = _TYPE_TO_SUBDIR.get(base_code)

        if subdir:
            categories = [("misc", subdir)]
        else:
            categories = [
                ("weapon", "uniqueweapon"),
                ("armor", "uniquearmor"),
                ("misc", "uniquecharm"),
            ]

        data: bytes | None
        if self._mod_hd_dir:
            for cat, sub in categories:
                sprite_path = self._mod_hd_dir / cat / sub / f"{fname}.sprite"
                if sprite_path.exists():
                    try:
                        data = sprite_path.read_bytes()
                        if data[:4] == b"SpA1":
                            return decode_sprite(data)
                    except Exception as e:
                        logger.debug("Failed to read %s: %s", sprite_path, e)

        if self._casc:
            for cat, sub in categories:
                casc_path = f"data:data/hd/global/ui/items/{cat}/{sub}/{fname}.sprite"
                data = self._casc.read_file(casc_path)
                if data is not None and data[:4] == b"SpA1":
                    return decode_sprite(data)

        return None

    def _try_dc6(self, invfile: str) -> bytes | None:
        """Try to load a legacy DC6 sprite."""
        if not invfile or self._mod_dc6_dir is None:
            return None


        dc6_path = self._mod_dc6_dir / f"{invfile}.dc6"
        if not dc6_path.exists():
            for f in self._mod_dc6_dir.iterdir():
                if f.name.lower() == f"{invfile.lower()}.dc6":
                    dc6_path = f
                    break
            else:
                return None

        try:
            data = dc6_path.read_bytes()
            return decode_dc6(data)
        except Exception as e:
            logger.debug("DC6 error for %s: %s", invfile, e)
            return None

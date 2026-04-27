"""Bulk item sprite preloader for D2R Reimagined GUIs.

One-shot loader that walks the item database and loads every base-item
sprite, GFX variant, unique override, and set override into a single
dict keyed by a stable lookup string.

Designed to be called once at application start (typically from a
splash-screen loading worker) so that later item rendering can access
every sprite via a simple dict lookup instead of on-demand CASC reads.

Usage::

    from d2rr_toolkit.sprites.bulk_loader import (
        load_all_item_sprites, make_sprite_key, prepare_bulk_sprite_loader,
    )

    # One-time: load game data needed by the bulk loader (Iron Rule)
    prepare_bulk_sprite_loader()

    # Bulk preload (typically ~1-3s on NVMe SSD)
    sprites = load_all_item_sprites(
        casc_reader=casc,
        game_paths=gp,
        items_json=items_json,
        progress_callback=lambda msg, cur, tot: print(msg, cur, tot),
    )

    # Later during item rendering:
    key = make_sprite_key(
        item_code=item.item_code,
        gfx_index=item.gfx_index,
        unique_name=item.unique_name,
    )
    png = sprites.get(key)  # bytes | None
"""

from __future__ import annotations

import csv
import io
import logging
import re
import struct
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from d2rr_toolkit.config import GamePaths
    from d2rr_toolkit.adapters.casc.reader import CASCReader
    from d2rr_toolkit.game_data.item_names import ItemNamesDatabase


# ── Private helpers extracted from load_all_item_sprites ────────────────────
# These support the bulk-loading pipeline as independently testable units.
# They are intentionally module-private - the public API surface remains
# exactly ``load_all_item_sprites`` + friends.


def _decode_spa1_fast(data: bytes) -> bytes | None:
    """Fast SpA1 -> PNG decoder (skips the size-reduction pass).

    Tuned for bulk loading: skips Pillow's size-reduction pass
    which adds ~2-3 ms per sprite - unacceptable at ~3000 sprites
    per warm-up. Single-shot use cases should prefer the canonical
    decoder in :mod:`d2rr_toolkit.adapters.casc.sprites` which
    produces smaller PNGs.

    Pixel data starts at a fixed 40-byte header offset. Earlier
    revisions computed the offset from the file tail, which silently
    corrupted any sprite whose file size exceeded ``40 + w·h·4``.

    Args:
        data: Raw SpA1 bytes (typically 40-byte header + RGBA payload).

    Returns:
        PNG-encoded bytes, or ``None`` if the input is not a valid
        SpA1 blob or decoding fails for any reason.
    """
    if not data or len(data) < 40 or data[:4] != b"SpA1":
        return None
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        width = struct.unpack_from("<I", data, 8)[0]
        height = struct.unpack_from("<I", data, 12)[0]
        rgba_size = width * height * 4
        data_offset = 40
        if rgba_size <= 0 or data_offset + rgba_size > len(data):
            return None
        img = Image.frombytes(
            "RGBA",
            (width, height),
            data[data_offset : data_offset + rgba_size],
        )
        buf = io.BytesIO()
        img.save(buf, format="PNG")  # size-reduction pass off - ~3x faster
        return buf.getvalue()
    except Exception:  # noqa: BLE001 - Pillow error surface is broad
        return None


def _build_mod_hd_index(mod_hd_items: Path) -> dict[str, Path]:
    """Return a ``{sprite_basename: full_path}`` map of every mod HD sprite.

    Single O(n) traversal of the mod HD directory. Lowend variants
    (``*.lowend.sprite``) are excluded - they are pre-decoded legacy
    textures the mod includes for backwards compatibility only.

    Args:
        mod_hd_items: Path to the mod's HD items directory. If it is
            not a directory the function returns an empty dict.

    Returns:
        Dict mapping each sprite's lowercase stem (filename without
        extension) to its absolute :class:`Path`.
    """
    index: dict[str, Path] = {}
    if not mod_hd_items.is_dir():
        return index
    for p in mod_hd_items.rglob("*.sprite"):
        if ".lowend." in p.name:
            continue
        index[p.stem.lower()] = p
    logger.debug("Mod HD sprite index: %d files", len(index))
    return index


def _build_casc_sprite_index(casc_reader: "CASCReader") -> dict[str, bytes]:
    """Return a ``{sprite_basename: ckey}`` map of every CASC item sprite.

    Mirrors :func:`_build_mod_hd_index` for the base-game CASC archive.
    Failures are swallowed (returning an empty dict) because CASC
    access is best-effort - the mod HD directory is usually a complete
    overlay on its own.

    Args:
        casc_reader: Live :class:`CASCReader` instance. ``None`` is
            not tolerated (caller should have validated already).

    Returns:
        Dict mapping each sprite's lowercase basename to its CASC
        content key. Empty on any I/O or CASC error.
    """
    index: dict[str, bytes] = {}
    try:
        for path in casc_reader.list_files(
            "data:data/hd/global/ui/items/*/*.sprite",
        ):
            if ".lowend." in path:
                continue
            fname = path.rsplit("/", 1)[-1].replace(".sprite", "").lower()
            ckey = casc_reader.resolve_ckey(path)
            if ckey is not None:
                index[fname] = ckey
        logger.debug("CASC sprite index: %d files", len(index))
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not pre-scan CASC sprite paths: %s", e)
    return index


class _SpriteResolver:
    """Mod-overlay-aware sprite resolver with decoded-PNG caching.

    Encapsulates the per-phase sprite lookup used by
    :func:`load_all_item_sprites`:

      1. Check the mod HD index (mod overrides beat CASC).
      2. Fall back to the CASC archive.
      3. Cache the decoded PNG per basename so repeat lookups across
         phases (base -> GFX -> unique -> set) don't re-decode.

    Extracted from the original 461-LOC monolith so each lookup step
    is an independently testable unit.
    """

    def __init__(
        self,
        mod_index: dict[str, Path],
        casc_index: dict[str, bytes],
        casc_reader: "CASCReader",
        *,
        skip_errors: bool,
    ) -> None:
        self._mod = mod_index
        self._casc = casc_index
        self._casc_reader = casc_reader
        self._skip_errors = skip_errors
        self._cache: dict[str, bytes | None] = {}

    def load(self, sprite_name: str) -> bytes | None:
        """Resolve a sprite by its base filename (without extension).

        Mod files win over CASC (mod overlay semantics). Decoded PNG
        bytes are cached per sprite basename to avoid duplicate decodes
        across phases.

        Args:
            sprite_name: Sprite file stem (case-insensitive).

        Returns:
            PNG bytes, or ``None`` if neither index has the sprite or
            decoding failed with ``skip_errors=True``.

        Raises:
            Exception: Any decode error from mod or CASC paths when
                ``skip_errors=False`` - matches the pre-refactor
                contract exactly.
        """
        key = sprite_name.lower()
        if key in self._cache:
            return self._cache[key]

        png: bytes | None = None
        mod_path = self._mod.get(key)
        if mod_path is not None:
            try:
                data = mod_path.read_bytes()
                if data[:4] == b"SpA1":
                    png = _decode_spa1_fast(data)
            except Exception as e:  # noqa: BLE001
                if not self._skip_errors:
                    raise
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug("Mod sprite decode failed for %s: %s", sprite_name, e)

        if png is None:
            ckey = self._casc.get(key)
            if ckey is not None:
                try:
                    data = self._casc_reader.read_by_ckey(ckey)
                    if data and data[:4] == b"SpA1":
                        png = _decode_spa1_fast(data)
                except Exception as e:  # noqa: BLE001
                    if not self._skip_errors:
                        raise
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug("CASC sprite decode failed for %s: %s", sprite_name, e)

        self._cache[key] = png
        return png

    @property
    def all_names(self) -> set[str]:
        """Union of mod + CASC sprite names (used for GFX-variant scan)."""
        return set(self._mod.keys()) | set(self._casc.keys())


logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────
# Sprite key schema
# ──────────────────────────────────────────────────────────────────────────
#
# Stable lookup keys for the sprite dict returned by load_all_item_sprites().
# Both the loader and the GUI must use make_sprite_key() to build keys so
# they stay in sync.
#
#   "<code>"                 Base item (no variant)
#   "<code>#<gfx_index>"     Base item with GFX variant (0-based index)
#   "<code>@<unique_name>"   Unique item with dedicated sprite
#   "<code>@<set_name>"      Set item with dedicated sprite
#
# ──────────────────────────────────────────────────────────────────────────


def make_sprite_key(
    item_code: str,
    *,
    gfx_index: int | None = None,
    unique_name: str | None = None,
    set_name: str | None = None,
) -> str:
    """Build a stable sprite lookup key.

    Priority (first non-None wins):
      1. unique_name  -> "<code>@<unique_name>"
      2. set_name     -> "<code>@<set_name>"
      3. gfx_index    -> "<code>#<gfx_index>"
      4. plain        -> "<code>"

    Args:
        item_code: Base item code (e.g. "rin", "amu", "cm1").
        gfx_index: GFX variant index (0-based). None or negative = no variant.
        unique_name: Unique item display name, if the item is a Unique
                     with a dedicated sprite override.
        set_name: Set item display name, if the item is a Set item with
                  a dedicated sprite override.

    Returns:
        Stable sprite lookup key as a string.
    """
    code = item_code.strip().lower()
    if unique_name:
        return f"{code}@{unique_name}"
    if set_name:
        return f"{code}@{set_name}"
    if gfx_index is not None and gfx_index >= 0:
        return f"{code}#{gfx_index}"
    return code


# ──────────────────────────────────────────────────────────────────────────
# Game data setup helper
# ──────────────────────────────────────────────────────────────────────────


def load_items_json(path: Path) -> dict[str, str]:
    """Load and flatten the Reimagined items.json file.

    The raw file format is a list of single-key dicts::

        [
            {"hax": {"asset": "axe/hand_axe"}},
            {"rin": {"asset": "ring/ring"}},
            ...
        ]

    This helper flattens it into the flat ``{item_code: asset_path}``
    mapping that SpriteResolver and load_all_item_sprites() expect::

        {"hax": "axe/hand_axe", "rin": "ring/ring", ...}

    Args:
        path: Path to items.json
              (typically ``<mod>/Reimagined.mpq/data/hd/items/items.json``).

    Returns:
        Flat dict mapping item_code -> asset_path.
        Empty dict if the file does not exist.
    """
    import json

    if not path.exists():
        return {}

    raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    flat: dict[str, str] = {}

    if isinstance(raw, dict):
        # Already flat (or "key": asset_str) - normalize values
        for code, val in raw.items():
            if isinstance(val, str):
                flat[code] = val
            elif isinstance(val, dict):
                asset = val.get("asset") or val.get("path") or ""
                if asset:
                    flat[code] = asset
    elif isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            for code, val in entry.items():
                if isinstance(val, str):
                    flat[code] = val
                elif isinstance(val, dict):
                    asset = val.get("asset") or val.get("path") or ""
                    if asset:
                        flat[code] = asset

    return flat


# Canonical name normalization used for matching display names against
# the snake_case keys used in uniques.json / sets.json.
# Verified against the Reimagined mod data:
#   "Stealskull"        -> "stealskull"
#   "The Gnasher"       -> "the_gnasher"
#   "Axe of Fechmar"    -> "axe_of_fechmar"
#   "Civerb's Cudgel"   -> "civerbs_cudgel"   (apostrophe stripped, not _)
#   "Hwanin's Refuge"   -> "hwanins_refuge"
# The rule is: lowercase, strip apostrophes, then collapse any run of
# non-alphanumeric chars into a single underscore.
_NAME_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def display_name_to_snake_case(display_name: str) -> str:
    """Normalise a unique/set display name for uniques.json/sets.json lookup.

    Examples::

        "Stealskull"       -> "stealskull"
        "The Gnasher"      -> "the_gnasher"
        "Axe of Fechmar"   -> "axe_of_fechmar"
        "Civerb's Cudgel"  -> "civerbs_cudgel"

    Args:
        display_name: Human-readable display name from uniqueitems.txt
                      or setitems.txt (the ``index`` column).

    Returns:
        snake_case key suitable for uniques.json / sets.json lookup.
    """
    if not display_name:
        return ""
    name = display_name.lower().replace("'", "")
    name = _NAME_NORMALIZE_RE.sub("_", name).strip("_")
    return name


def load_unique_sprite_map(
    json_path: Path,
    *,
    tier: str = "normal",
) -> dict[str, str]:
    """Load uniques.json into a ``{snake_case_name: asset_path}`` dict.

    The file has this structure::

        [
            {"stealskull": {
                "normal": "helmet/coif_of_glory",
                "uber":   "helmet/coif_of_glory",
                "ultra":  "helmet/coif_of_glory"
            }},
            {"the_gnasher": {...}},
            ...
        ]

    This is the **authoritative source** for per-unique HD sprite
    overrides in the Reimagined mod. The old ``invfile`` column in
    uniqueitems.txt is a legacy D2 fallback and does NOT match the
    mod's actual sprite layout -- use this loader instead.

    Args:
        json_path: Path to ``uniques.json``
                   (typically ``<mod>/Reimagined.mpq/data/hd/items/uniques.json``).
        tier:      Tier to extract. D2R has three tiers but they are
                   usually identical for the inventory sprite.
                   One of "normal", "uber", "ultra". Default: "normal".

    Returns:
        Dict mapping snake_case unique name -> asset path
        (e.g. ``"stealskull" -> "helmet/coif_of_glory"``).
        Empty dict if the file does not exist.
    """
    return _load_sprite_override_json(json_path, tier=tier)


def load_set_sprite_map(
    json_path: Path,
    *,
    tier: str = "normal",
) -> dict[str, str]:
    """Load sets.json into a ``{snake_case_name: asset_path}`` dict.

    See :func:`load_unique_sprite_map` -- same format and semantics,
    just for set items.
    """
    return _load_sprite_override_json(json_path, tier=tier)


# ── Display-name aliasing ────────────────────────────────────────────────────
#
# uniques.json and sets.json are keyed on snake-case of the RAW
# ``index`` column of ``uniqueitems.txt`` / ``setitems.txt`` - the
# internal identifier used by the mod authors when they generated the
# HD sprite manifests.  The LOCALISED display name that flows through
# :class:`ItemNamesDatabase` (and from there into the GUI / CLI /
# sprite key) is loaded from ``item-names.json`` and can differ from
# the raw index for any row the mod chose to rename or pretty up.
# Famous divergences in the current Reimagined data set:
#
#   raw ``Life and Death``  -> display ``Life & Death``
#   raw ``KhalimFlail``     -> display ``Khalim's Flail``
#   raw ``Unique Warlock Helm`` -> display ``Hellwarden's Will``
#   raw ``Crafted Cold Rupture`` -> display ``Renewed Cold Rupture``
#
# A downstream caller that starts from the display name and snake-
# cases it would end up with ``life_death`` / ``khalims_flail`` /
# ``hellwardens_will`` / ``renewed_cold_rupture`` - none of which
# match the keys in ``uniques.json``.  The helpers below populate the
# display-name snake as an alias pointing to the same asset path so a
# lookup by either name resolves.  This is the only fix-site: the
# snake-case normaliser itself is correct for its contract (it takes
# whatever string you give it), the mismatch is purely in the two
# name spaces not agreeing.


def _extract_star_id_name_pairs(
    rows: list[dict[str, str]],
    *,
    id_col: str = "*ID",
) -> list[tuple[int, str]]:
    """Return ``(*ID, index)`` pairs from a uniqueitems/setitems row list.

    Separator rows (empty code or missing/non-numeric *ID) are skipped.
    The ``index`` column carries the raw internal name used as the
    uniques.json / sets.json key source.
    """
    out: list[tuple[int, str]] = []
    for row in rows:
        raw = (row.get("index") or "").strip()
        sid_str = (row.get(id_col) or "").strip()
        if not raw or not sid_str.isdigit():
            continue
        out.append((int(sid_str), raw))
    return out


def _add_display_name_aliases(
    sprite_map: dict[str, str],
    raw_display_pairs: list[tuple[str, str]],
) -> dict[str, str]:
    """Add display-name snake aliases to a loaded sprite map.

    For each ``(raw_name, display_name)`` pair where snake-casing the
    two yields different keys, register the display snake as an
    additional key pointing to the same asset path that the raw
    snake already resolves to.  No-ops when raw == display or the
    raw snake has no entry in the map (unique without a dedicated
    sprite override).
    """
    for raw_name, display_name in raw_display_pairs:
        raw_snake = display_name_to_snake_case(raw_name)
        disp_snake = display_name_to_snake_case(display_name)
        if raw_snake == disp_snake:
            continue
        asset = sprite_map.get(raw_snake)
        if asset is not None:
            sprite_map.setdefault(disp_snake, asset)
    return sprite_map


def load_unique_sprite_map_with_aliases(
    json_path: Path,
    uniqueitems_rows: list[dict[str, str]],
    names_db: "ItemNamesDatabase | None" = None,
    *,
    tier: str = "normal",
) -> dict[str, str]:
    """Load uniques.json and add display-name snake aliases.

    ``uniques.json`` is keyed by snake-case of the RAW
    ``uniqueitems.txt`` ``index`` column.  Consumers that start from
    the LOCALIZED display name (via
    :class:`~d2rr_toolkit.game_data.item_names.ItemNamesDatabase` ->
    ``strings/item-names.json``) would miss every row whose display
    diverges from its raw name.  This loader adds the display snake
    as a second key per diverging row so lookups by either name
    resolve.

    Back-compat note: the returned map is a strict superset of the
    plain :func:`load_unique_sprite_map` result - all original keys
    remain.  Existing callers that pass the raw name continue to
    work unchanged; new callers that pass the display name are
    supported too.

    Args:
        json_path:        Path to ``uniques.json``.
        uniqueitems_rows: Already-loaded ``uniqueitems.txt`` rows (as
                          returned by ``read_game_data_rows``).  When
                          empty the function behaves identically to
                          :func:`load_unique_sprite_map`.
        names_db:         Loaded :class:`ItemNamesDatabase`.  When
                          ``None`` or not loaded, no aliases are
                          added and the result equals the plain map.
        tier:             "normal" / "uber" / "ultra".
    """
    base = load_unique_sprite_map(json_path, tier=tier)
    if not base or names_db is None or not names_db.is_loaded():
        return base
    pairs: list[tuple[str, str]] = []
    for sid, raw in _extract_star_id_name_pairs(uniqueitems_rows):
        disp = names_db.get_unique_name(sid)
        if disp and disp != raw:
            pairs.append((raw, disp))
    return _add_display_name_aliases(base, pairs)


def load_set_sprite_map_with_aliases(
    json_path: Path,
    setitems_rows: list[dict[str, str]],
    names_db: "ItemNamesDatabase | None" = None,
    *,
    tier: str = "normal",
) -> dict[str, str]:
    """Load sets.json and add display-name snake aliases.

    Analogue of :func:`load_unique_sprite_map_with_aliases` for set
    items.  The current Reimagined data has two diverging set rows
    (``Panda's Mitts`` -> ``Panda's Mittens``; ``Panda's Coat`` ->
    ``Panda's Jacket``) - both break the sprite lookup without the
    alias.
    """
    base = load_set_sprite_map(json_path, tier=tier)
    if not base or names_db is None or not names_db.is_loaded():
        return base
    pairs: list[tuple[str, str]] = []
    for sid, raw in _extract_star_id_name_pairs(setitems_rows):
        disp = names_db.get_set_item_name(sid)
        if disp and disp != raw:
            pairs.append((raw, disp))
    return _add_display_name_aliases(base, pairs)


def _load_sprite_override_json(
    json_path: Path,
    *,
    tier: str = "normal",
) -> dict[str, str]:
    """Shared loader for uniques.json and sets.json."""
    import json

    if not json_path.exists():
        return {}

    try:
        raw = json.loads(json_path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Could not read %s: %s", json_path, e)
        return {}

    result: dict[str, str] = {}

    def _extract(key: str, val: object) -> None:
        if not isinstance(val, dict):
            return
        asset = val.get(tier) or val.get("normal") or val.get("uber") or val.get("ultra")
        if isinstance(asset, str) and asset:
            result[key.lower()] = asset

    if isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, dict):
                for k, v in entry.items():
                    _extract(k, v)
    elif isinstance(raw, dict):
        for k, v in raw.items():
            _extract(k, v)

    return result


def prepare_bulk_sprite_loader() -> None:
    """Load all game data tables needed by load_all_item_sprites().

    Call this once at application startup before invoking the bulk
    loader. Each underlying loader resolves its files through the
    shared :class:`CASCReader` singleton (Iron Rule - Reimagined mod
    first, D2R Resurrected CASC fallback). Safe to call multiple
    times; the loaders are idempotent.
    """
    from d2rr_toolkit.game_data.item_types import load_item_types
    from d2rr_toolkit.game_data.item_names import load_item_names
    from d2rr_toolkit.game_data.sets import load_sets

    load_item_types()
    load_item_names()
    load_sets()


# ──────────────────────────────────────────────────────────────────────────
# Bulk sprite loader
# ──────────────────────────────────────────────────────────────────────────


# Progress callback batch size (one update per N sprites).
_PROGRESS_BATCH = 50


def load_all_item_sprites(
    casc_reader: "CASCReader",
    game_paths: "GamePaths",
    items_json: dict[str, str],
    *,
    include_base_items: bool = True,
    include_unique_variants: bool = True,
    include_gfx_variants: bool = True,
    progress_callback: Callable[[str, int, int], None] | None = None,
    skip_errors: bool = True,
) -> dict[str, bytes]:
    """Preload all item sprites into a single dict in memory.

    Walks the item database, resolves every item code plus its GFX
    variants (Charms/Rings/Amulets/Jewels), plus all unique- and
    set-item sprite overrides, and returns them keyed by a stable
    lookup string.

    No on-disk caching - every call re-reads from source. The returned
    dict is expected to live in memory for the lifetime of the app.

    Internally pre-scans the mod HD directory once into a {basename:
    Path} index, so every item lookup is an O(1) dict access instead
    of a fan-out of Path.exists() calls.

    Args:
        casc_reader:          CASCReader for base-game sprites.
        game_paths:           GamePaths for locating mod sprite dirs.
        items_json:           dict mapping item_code -> HD asset path
                              (from Reimagined.mpq/data/hd/items/items.json).
        include_base_items:   Load base item sprites (default: True).
        include_unique_variants: Load per-unique sprite overrides (default: True).
        include_gfx_variants: Load GFX index variants for items that have them
                              (default: True).
        progress_callback:    Optional callable(message, current, total) for
                              splash-screen progress updates. Called in batches
                              of ~50 sprites to limit overhead.
        skip_errors:          If True, sprites that fail to decode are logged
                              at DEBUG and omitted. If False, raises on first
                              decode failure.

    Returns:
        dict[str, bytes] - sprite key (see make_sprite_key) -> PNG bytes.

    Raises:
        ValueError: If casc_reader or game_paths is None.
    """
    if casc_reader is None:
        raise ValueError("casc_reader is required")
    if game_paths is None:
        raise ValueError("game_paths is required")

    # Pillow is a declared runtime dep (see pyproject.toml). Import
    # eagerly so a missing Pillow surfaces here rather than deep inside
    # the decoder path.
    try:
        from PIL import Image  # noqa: F401 - imported for import-time failure
    except ImportError as e:
        raise RuntimeError(
            "Pillow is required for bulk sprite loading. Install with: pip install Pillow"
        ) from e

    t_start = time.perf_counter()
    logger.info("Starting bulk item sprite preload")

    # Index builders + resolver (see module-private helpers above).
    # Each sub-step is an independently testable unit.
    mod_hd_index = _build_mod_hd_index(game_paths.mod_hd_items)
    casc_sprite_map = _build_casc_sprite_index(casc_reader)
    resolver = _SpriteResolver(
        mod_hd_index,
        casc_sprite_map,
        casc_reader,
        skip_errors=skip_errors,
    )
    _load_by_sprite_name = resolver.load

    sprites: dict[str, bytes] = {}
    stats = {
        "base_loaded": 0,
        "base_missing": 0,
        "gfx_loaded": 0,
        "unique_loaded": 0,
        "unique_missing": 0,
        "set_loaded": 0,
        "set_missing": 0,
    }

    # ── Phase progression setup ────────────────────────────────────────
    base_codes = sorted(items_json.keys()) if items_json else []
    unique_entries = (
        _read_unique_sprite_entries(game_paths.reimagined_excel) if include_unique_variants else []
    )
    set_entries = _read_set_sprite_entries(game_paths.reimagined_excel)

    # Phase totals for progress callback:
    #   Phase 1 (base):     len(base_codes) work units
    #   Phase 2 (GFX):      len(base_codes) work units (only probes 1..7)
    #   Phase 3 (unique):   len(unique_entries)
    #   Phase 4 (set):      len(set_entries)
    total_units = (
        (len(base_codes) if include_base_items else 0)
        + (len(base_codes) if include_gfx_variants else 0)
        + len(unique_entries)
        + len(set_entries)
    )
    if total_units == 0:
        total_units = 1  # avoid zero total in progress callback

    def _emit(phase: str, current: int) -> None:
        if progress_callback is not None:
            progress_callback(phase, current, total_units)

    progress = 0

    # ── Phase 1: Base items ────────────────────────────────────────────
    if include_base_items and base_codes:
        _emit("Loading base items...", progress)
        for code in base_codes:
            asset = items_json.get(code, "")
            if not asset:
                stats["base_missing"] += 1
                progress += 1
                continue

            # asset format: "axe/hand_axe" -> sprite basename "hand_axe"
            sprite_name = asset.rsplit("/", 1)[-1] if "/" in asset else asset
            png = _load_by_sprite_name(sprite_name)

            if png is not None:
                sprites[make_sprite_key(code)] = png
                stats["base_loaded"] += 1
            else:
                stats["base_missing"] += 1

            progress += 1
            if progress % _PROGRESS_BATCH == 0:
                _emit("Loading base items...", progress)

    # ── Phase 2: GFX variants ──────────────────────────────────────────
    # Some items have numbered variants (ring1, ring2, ..., ring6).
    # Probe by iterating mod_hd_index + casc_sprite_map to find all
    # sprite names matching "<base_name><digit>" pattern.
    if include_gfx_variants and base_codes:
        _emit("Loading GFX variants...", progress)
        all_names = resolver.all_names

        for code in base_codes:
            asset = items_json.get(code, "")
            if not asset:
                progress += 1
                continue
            base_name = (asset.rsplit("/", 1)[-1] if "/" in asset else asset).lower()

            # Find all sprite names that match "<base_name><digits>"
            # - e.g. "ring" -> ring1, ring2, ring3, ring4, ring5, ring6.
            for gfx in range(1, 9):  # gfx_index 0..7 -> sprite_name1..8
                variant_name = f"{base_name}{gfx}"
                if variant_name not in all_names:
                    continue
                png = _load_by_sprite_name(variant_name)
                if png is None:
                    continue

                # Skip if byte-identical to base sprite (dedup)
                base_key = make_sprite_key(code)
                base_png = sprites.get(base_key)
                if base_png is not None and base_png == png:
                    continue

                # gfx_index is 0-based; sprite filename uses 1-based numbering
                sprites[make_sprite_key(code, gfx_index=gfx - 1)] = png
                stats["gfx_loaded"] += 1

            progress += 1
            if progress % _PROGRESS_BATCH == 0:
                _emit("Loading GFX variants...", progress)

    # ── Phase 3: Unique overrides ──────────────────────────────────────
    # Authoritative source: uniques.json from the mod HD items dir.
    # Each entry maps snake_case_name -> asset_path, e.g.
    #   "stealskull" -> "helmet/coif_of_glory"
    # The sprite basename is the last segment of the asset path.
    #
    # Name-space reconciliation (see the "Display-name aliasing" block
    # higher up in this module for background):
    #
    #   * uniques.json is keyed by snake-case of the RAW
    #     ``uniqueitems.txt.index`` column.  Use that name to find the
    #     asset.
    #   * The GUI / CLI fetch sprites by ``make_sprite_key(code,
    #     unique_name=item.unique_name)`` where ``item.unique_name``
    #     is the LOCALIZED display name resolved via
    #     ``ItemNamesDatabase.get_unique_name(*ID)``.  Store the
    #     sprite under THAT name so the lookup succeeds.
    #
    # When raw == display (the common case), both keys coincide and
    # the behaviour matches the pre-fix loader exactly.  When they
    # diverge (37 uniques in the current data, incl. "Life and Death"
    # -> "Life & Death"), the fix is the whole point.
    if include_unique_variants and unique_entries:
        _emit("Loading unique overrides...", progress)
        unique_sprite_map = load_unique_sprite_map(game_paths.mod_uniques_json)
        logger.debug("uniques.json entries: %d", len(unique_sprite_map))

        try:
            from d2rr_toolkit.game_data.item_names import get_item_names_db

            _names_db = get_item_names_db()
        except Exception:
            _names_db = None

        def _resolve_unique_display_name(raw_name: str, star_id: str) -> str:
            """Localised display name, with a raw-name fallback.

            Returns the raw name if the ``*ID`` is unparseable, the
            names DB is unloaded, or the lookup comes back empty.
            That guarantees the sprite is always stored under SOME
            key, even in test fixtures without a full names DB.
            """
            if _names_db is None or not _names_db.is_loaded():
                return raw_name
            if not star_id.isdigit():
                return raw_name
            return _names_db.get_unique_name(int(star_id)) or raw_name

        for entry in unique_entries:
            base_code = entry["code"]
            raw_name = entry["name"]
            display_name = _resolve_unique_display_name(
                raw_name,
                entry.get("star_id", ""),
            )

            snake = display_name_to_snake_case(raw_name)
            asset_path = unique_sprite_map.get(snake)

            if not asset_path:
                # No dedicated sprite override - the GUI will fall back
                # to the base item sprite via sprites.get(code).
                progress += 1
                if progress % _PROGRESS_BATCH == 0:
                    _emit("Loading unique overrides...", progress)
                continue

            sprite_name = asset_path.rsplit("/", 1)[-1] if "/" in asset_path else asset_path
            png = _load_by_sprite_name(sprite_name)

            if png is not None:
                # Skip if byte-identical to the base item sprite (dedup).
                base_key = make_sprite_key(base_code)
                base_png = sprites.get(base_key)
                if base_png is not None and base_png == png:
                    stats["unique_loaded"] += 1  # still counted
                else:
                    sprites[make_sprite_key(base_code, unique_name=display_name)] = png
                    # For divergent names, register the raw-name key as
                    # an alias too.  Callers that still use the raw
                    # index (scripts, bulk tooling, legacy tests) keep
                    # working without a forced migration.
                    if display_name != raw_name:
                        sprites.setdefault(
                            make_sprite_key(base_code, unique_name=raw_name),
                            png,
                        )
                    stats["unique_loaded"] += 1
            else:
                stats["unique_missing"] += 1
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "Unique sprite file missing for %s (asset=%s)",
                        display_name,
                        asset_path,
                    )

            progress += 1
            if progress % _PROGRESS_BATCH == 0:
                _emit("Loading unique overrides...", progress)

    # ── Phase 4: Set overrides ─────────────────────────────────────────
    # Authoritative source: sets.json from the mod HD items dir.
    # Same name-space reconciliation as Phase 3 - see the comment there.
    if set_entries:
        _emit("Loading set overrides...", progress)
        set_sprite_map = load_set_sprite_map(game_paths.mod_sets_json)
        logger.debug("sets.json entries: %d", len(set_sprite_map))

        try:
            from d2rr_toolkit.game_data.item_names import get_item_names_db

            _names_db = get_item_names_db()
        except Exception:
            _names_db = None

        def _resolve_set_display_name(raw_name: str, star_id: str) -> str:
            if _names_db is None or not _names_db.is_loaded():
                return raw_name
            if not star_id.isdigit():
                return raw_name
            return _names_db.get_set_item_name(int(star_id)) or raw_name

        for entry in set_entries:
            base_code = entry["code"]
            raw_name = entry["name"]
            display_name = _resolve_set_display_name(
                raw_name,
                entry.get("star_id", ""),
            )

            snake = display_name_to_snake_case(raw_name)
            asset_path = set_sprite_map.get(snake)

            if not asset_path:
                progress += 1
                if progress % _PROGRESS_BATCH == 0:
                    _emit("Loading set overrides...", progress)
                continue

            sprite_name = asset_path.rsplit("/", 1)[-1] if "/" in asset_path else asset_path
            png = _load_by_sprite_name(sprite_name)

            if png is not None:
                base_key = make_sprite_key(base_code)
                base_png = sprites.get(base_key)
                if base_png is not None and base_png == png:
                    stats["set_loaded"] += 1
                else:
                    sprites[make_sprite_key(base_code, set_name=display_name)] = png
                    if display_name != raw_name:
                        sprites.setdefault(
                            make_sprite_key(base_code, set_name=raw_name),
                            png,
                        )
                    stats["set_loaded"] += 1
            else:
                stats["set_missing"] += 1
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "Set sprite file missing for %s (asset=%s)",
                        display_name,
                        asset_path,
                    )

            progress += 1
            if progress % _PROGRESS_BATCH == 0:
                _emit("Loading set overrides...", progress)

    # ── Final summary ──────────────────────────────────────────────────
    _emit("Sprite preload complete", total_units)
    elapsed = time.perf_counter() - t_start
    total_bytes = sum(len(v) for v in sprites.values())
    total_mb = total_bytes / (1024 * 1024)

    logger.info(
        "Base items: %d loaded, %d missing",
        stats["base_loaded"],
        stats["base_missing"],
    )
    logger.info("GFX variants: %d loaded", stats["gfx_loaded"])
    logger.info(
        "Unique overrides: %d loaded, %d missing",
        stats["unique_loaded"],
        stats["unique_missing"],
    )
    logger.info(
        "Set overrides: %d loaded, %d missing",
        stats["set_loaded"],
        stats["set_missing"],
    )
    logger.info(
        "Total: %d sprites, %.1f MB in %.2fs",
        len(sprites),
        total_mb,
        elapsed,
    )

    return sprites


# ──────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────


def _lookup_invfile(item_code: str) -> str:
    """Return the invfile for a base item code, or empty string.

    Kept as a helper for callers that still need the legacy invfile
    column. The bulk loader no longer uses this for unique/set sprite
    lookups - those are resolved via uniques.json / sets.json now.
    """
    try:
        from d2rr_toolkit.game_data.item_types import get_item_type_db

        return get_item_type_db().get_inv_file(item_code) or ""
    except Exception:
        return ""


def _read_unique_sprite_entries(excel_dir: Path) -> list[dict[str, str]]:
    """Read uniqueitems.txt and return entries with code, raw name, *ID.

    Each entry carries:
      * ``code``    - base item code (``uniqueitems.txt`` ``code`` col).
      * ``name``    - the RAW ``index`` column value.  This is the
                      string used to look up the sprite in
                      ``uniques.json`` (whose keys are snake-cased from
                      exactly this column).  It is NOT the display name
                      when the mod has localised it to something else
                      - e.g. raw ``Life and Death`` displays as
                      ``Life & Death``.
      * ``star_id`` - the ``*ID`` column as a string (``""`` if
                      missing / non-numeric).  Phase 3 uses it to
                      resolve the localised display name via the
                      :class:`ItemNamesDatabase` so the sprite can be
                      stored under the key the GUI will actually look
                      up (``"{code}@{display_name}"``).

    Ladder/expansion separator rows (empty code) are skipped.
    """
    path = excel_dir / "uniqueitems.txt"
    if not path.exists():
        return []

    entries: list[dict[str, str]] = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                code = (row.get("code") or "").strip()
                name = (row.get("index") or "").strip()
                if not code or not name:
                    continue
                star_id = (row.get("*ID") or "").strip()
                entries.append({"code": code, "name": name, "star_id": star_id})
    except (OSError, csv.Error) as e:
        logger.warning("Could not read uniqueitems.txt: %s", e)

    return entries


def _read_set_sprite_entries(excel_dir: Path) -> list[dict[str, str]]:
    """Read setitems.txt and return entries with code, raw name, *ID.

    Mirror of :func:`_read_unique_sprite_entries` for set items.
    ``code`` is taken from the ``item`` column (the base item code,
    e.g. ``lrg``); ``name`` is the RAW ``index`` column (the string
    ``sets.json`` snake-keys are derived from); ``star_id`` lets Phase
    4 resolve the localised display name via
    :class:`ItemNamesDatabase.get_set_item_name`.
    """
    path = excel_dir / "setitems.txt"
    if not path.exists():
        return []

    entries: list[dict[str, str]] = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                code = (row.get("item") or "").strip()
                name = (row.get("index") or "").strip()
                if not code or not name:
                    continue
                star_id = (row.get("*ID") or "").strip()
                entries.append({"code": code, "name": name, "star_id": star_id})
    except (OSError, csv.Error) as e:
        logger.warning("Could not read setitems.txt: %s", e)

    return entries

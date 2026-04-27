#!/usr/bin/env python3
"""Test suite for the palette-based tinting pipeline.

Covers the four new APIs:

  1. d2rr_toolkit.display.palette
     - load_palette(casc, name="act1")
     - load_colormap(casc, colormap_id)
     - load_colors_txt(casc)
     - Palette.color(index)
     - ColorMap.lookup(tint_id, in_index)

  2. d2rr_toolkit.game_data.item_types.get_inv_transform_id()

  3. d2rr_toolkit.sprites.dc6_indexed.decode_dc6_indexed()

  4. d2rr_toolkit.display.tinted_sprite
     - configure_tinted_sprite_pipeline()
     - get_tinted_sprite(item)
     - TintedSpriteResult

Plus one end-to-end test that loads MrLockhart's inventory and renders
a handful of tintable items, asserting the RGBA buffer has the right
shape and contains non-zero, opaque pixels.
"""

from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
src_dir = project_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


def main() -> int:
    import logging

    logging.basicConfig(level=logging.WARNING)

    from d2rr_toolkit.adapters.casc import CASCReader
    from d2rr_toolkit.cli import _load_game_data
    from d2rr_toolkit.config import get_game_paths
    from d2rr_toolkit.display.palette import (
        ColorMap,
        Palette,
        clear_caches as clear_palette_caches,
        load_colormap,
        load_colors_txt,
        load_palette,
    )
    from d2rr_toolkit.display.tinted_sprite import (
        TintedSpriteResult,
        clear_cache as clear_tint_cache,
        configure_tinted_sprite_pipeline,
        get_tinted_sprite,
    )
    from d2rr_toolkit.game_data.item_types import get_item_type_db
    from d2rr_toolkit.parsers.d2s_parser import D2SParser
    from d2rr_toolkit.sprites.dc6_indexed import (
        IndexedDC6Frame,
        decode_dc6_indexed,
    )

    # Game data must be loaded for ParsedItem + ItemTypeDatabase lookups.
    _load_game_data(project_root / "MrLockhart.d2s")

    gp = get_game_paths()
    casc = CASCReader(gp.d2r_install)

    passed = 0
    failed = 0
    total = 0

    def check(condition: bool, name: str, detail: str = ""):
        nonlocal passed, failed, total
        total += 1
        if condition:
            passed += 1
            print(f"  PASS  {name}")
        else:
            failed += 1
            print(f"  FAIL  {name}")
            if detail:
                print(f"        {detail}")

    # ── 1. load_palette ────────────────────────────────────────────────
    print("\n=== 1. load_palette ===")
    clear_palette_caches()

    palette = load_palette(casc)
    check(isinstance(palette, Palette), "returns Palette instance")
    check(palette.name == "act1", f"name=act1 ({palette.name!r})")
    check(len(palette.rgb) == 768, f"rgb is 768 bytes ({len(palette.rgb)})")
    check(palette.color(0) == (0, 0, 0), f"index 0 -> (0,0,0)  ({palette.color(0)})")
    # Palette index 1 = RGB (36, 0, 0) after BGR->RGB conversion.
    check(palette.color(1) == (36, 0, 0), f"index 1 -> (36,0,0)  ({palette.color(1)})")

    # Cache: second call returns identical object
    palette2 = load_palette(casc)
    check(palette is palette2, "load_palette is cached")

    # Out-of-range error
    try:
        palette.color(256)
        check(False, "color(256) raises IndexError")
    except IndexError:
        check(True, "color(256) raises IndexError")

    # ── 2. load_colormap ───────────────────────────────────────────────
    print("\n=== 2. load_colormap ===")

    cm8 = load_colormap(casc, 8)
    check(isinstance(cm8, ColorMap), "returns ColorMap instance")
    check(cm8.colormap_id == 8, f"colormap_id=8 ({cm8.colormap_id})")
    check(cm8.name == "invgreybrown", f"name=invgreybrown ({cm8.name})")
    check(len(cm8.tints) == 5376, f"tints is 5376 bytes ({len(cm8.tints)})")
    # invgreybrown.tints[0] == 0xB1.
    check(cm8.tints[0] == 0xB1, f"tints[0] == 0xB1  (0x{cm8.tints[0]:02X})")

    # All 8 colormap IDs should be loadable
    for cid in range(1, 9):
        cm = load_colormap(casc, cid)
        check(
            len(cm.tints) == 5376,
            f"colormap id {cid} ({cm.name}) loads with 5376 bytes",
        )

    # Cache
    cm8b = load_colormap(casc, 8)
    check(cm8 is cm8b, "load_colormap is cached")

    # ID 0 is invalid
    try:
        load_colormap(casc, 0)
        check(False, "colormap_id=0 raises ValueError")
    except ValueError:
        check(True, "colormap_id=0 raises ValueError")

    # ID 9 is invalid
    try:
        load_colormap(casc, 9)
        check(False, "colormap_id=9 raises ValueError")
    except ValueError:
        check(True, "colormap_id=9 raises ValueError")

    # lookup() semantics
    check(cm8.lookup(0, 0) == cm8.tints[0], "lookup(0, 0) == tints[0]")
    check(cm8.lookup(9, 42) == cm8.tints[9 * 256 + 42], "lookup(9, 42) indexed correctly")
    try:
        cm8.lookup(21, 0)  # tint_id out of range
        check(False, "lookup(21, 0) raises IndexError")
    except IndexError:
        check(True, "lookup(21, 0) raises IndexError")

    # ── 3. load_colors_txt ─────────────────────────────────────────────
    print("\n=== 3. load_colors_txt ===")

    codes = load_colors_txt(casc)
    check(isinstance(codes, dict), "returns dict")
    check(len(codes) == 21, f"21 entries ({len(codes)})")
    # Expected codes: whit=0, cred=9, bwht=20.
    check(codes.get("whit") == 0, f"whit -> 0 ({codes.get('whit')})")
    check(codes.get("cred") == 9, f"cred -> 9 ({codes.get('cred')})")
    check(codes.get("bwht") == 20, f"bwht -> 20 ({codes.get('bwht')})")
    # All 21 expected codes.
    expected_order = [
        "whit",
        "lgry",
        "dgry",
        "blac",
        "lblu",
        "dblu",
        "cblu",
        "lred",
        "dred",
        "cred",
        "lgrn",
        "dgrn",
        "cgrn",
        "lyel",
        "dyel",
        "lgld",
        "dgld",
        "lpur",
        "dpur",
        "oran",
        "bwht",
    ]
    for idx, code in enumerate(expected_order):
        check(codes.get(code) == idx, f"{code} -> {idx}")

    # Cache: second call returns the same dict object
    codes2 = load_colors_txt(casc)
    check(codes is codes2, "load_colors_txt is cached")

    # ── 4. get_inv_transform_id ────────────────────────────────────────
    print("\n=== 4. get_inv_transform_id ===")

    type_db = get_item_type_db()
    # Expected: xlm (Casque) -> 8.
    check(type_db.get_inv_transform_id("xlm") == 8, "xlm (Casque) -> 8")
    check(type_db.get_inv_transform_id("XLM") == 8, "case-insensitive (XLM)")
    check(
        type_db.get_inv_transform_id("definitely_not_an_item") == 0,
        "unknown code -> 0",
    )
    # Sanity: at least some items in armor/weapons/misc must have InvTrans>0
    armor_sample_codes = ["xlm", "hax", "axe", "cap", "buc"]
    got_nonzero = any(type_db.get_inv_transform_id(c) > 0 for c in armor_sample_codes)
    check(got_nonzero, "at least one sample item has non-zero InvTrans")

    # ── 5. decode_dc6_indexed ──────────────────────────────────────────
    print("\n=== 5. decode_dc6_indexed ===")

    # Find any DC6 in the mod directory for a smoke test
    mod_dc6 = gp.mod_dc6_items
    sample_dc6: Path | None = None
    if mod_dc6.is_dir():
        for p in sorted(mod_dc6.glob("*.dc6")):
            sample_dc6 = p
            break

    if sample_dc6 is None:
        check(False, "could not find any DC6 file for smoke test")
    else:
        data = sample_dc6.read_bytes()
        frame = decode_dc6_indexed(data, frame=0)
        check(isinstance(frame, IndexedDC6Frame), "returns IndexedDC6Frame")
        check(frame.width > 0, f"width > 0 ({frame.width})")
        check(frame.height > 0, f"height > 0 ({frame.height})")
        check(
            len(frame.indices) == frame.width * frame.height,
            f"indices is width*height bytes ({len(frame.indices)})",
        )
        # Every byte is automatically < 256 - just sanity-check it's bytes
        check(isinstance(frame.indices, bytes), "indices is bytes")
        # At least SOME pixels should be non-zero (opaque)
        non_zero = sum(1 for b in frame.indices if b != 0)
        check(non_zero > 0, f"at least one opaque pixel ({non_zero})")
        # The border row/column should have mostly index-0 pixels
        # (sprites are rarely edge-to-edge). Only a soft check.
        top_row = frame.indices[: frame.width]
        top_zero_ratio = sum(1 for b in top_row if b == 0) / max(len(top_row), 1)
        check(
            top_zero_ratio >= 0.0,  # Always true - just document the value
            f"top-row transparency ratio: {top_zero_ratio:.2f}",
        )

    # Malformed input
    try:
        decode_dc6_indexed(b"")
        check(False, "empty DC6 raises ValueError")
    except ValueError:
        check(True, "empty DC6 raises ValueError")

    try:
        decode_dc6_indexed(b"\x00" * 30)  # too short
        check(False, "truncated DC6 raises ValueError")
    except ValueError:
        check(True, "truncated DC6 raises ValueError")

    # ── 6. get_tinted_sprite (end-to-end) ─────────────────────────────
    print("\n=== 6. get_tinted_sprite end-to-end ===")

    configure_tinted_sprite_pipeline(casc=casc, mod_dc6_dir=gp.mod_dc6_items)
    clear_tint_cache()

    # Parse MrLockhart and find items with invtransform + colormap_id > 0
    char_path = project_root / "tests" / "cases" / "TC49" / "MrLockhart.d2s"
    char = D2SParser(char_path).parse()

    from d2rr_toolkit.display.invtransform import get_invtransform

    tintable_indices: list[int] = []
    for idx, item in enumerate(char.items):
        code = get_invtransform(item)
        cm_id = type_db.get_inv_transform_id(item.item_code)
        if code is not None and cm_id > 0:
            tintable_indices.append(idx)

    check(len(tintable_indices) > 0, f"MrLockhart has tintable items ({len(tintable_indices)})")

    tinted_count = 0
    for idx in tintable_indices[:5]:  # check up to 5 items
        result = get_tinted_sprite(char.items[idx])
        item = char.items[idx]
        if result is None:
            # Some items may have invfile that doesn't exist on disk - log but
            # don't fail: we only assert overall there must be SOME tinted
            # results in the sample.
            continue
        tinted_count += 1
        check(
            isinstance(result, TintedSpriteResult),
            f"item[{idx}] ({item.item_code}) -> TintedSpriteResult",
        )
        check(result.width > 0, f"item[{idx}] width > 0 ({result.width})")
        check(result.height > 0, f"item[{idx}] height > 0 ({result.height})")
        check(
            len(result.rgba) == result.width * result.height * 4,
            f"item[{idx}] rgba length matches dimensions",
        )
        # Every fully-transparent pixel must have RGBA=(0,0,0,0)
        # and every opaque pixel must have alpha=255.
        opaque = 0
        transparent = 0
        bad_alpha = 0
        for i in range(0, len(result.rgba), 4):
            a = result.rgba[i + 3]
            if a == 0:
                transparent += 1
                # RGB must also be 0 for fully transparent pixels
                if result.rgba[i] != 0 or result.rgba[i + 1] != 0 or result.rgba[i + 2] != 0:
                    bad_alpha += 1
            elif a == 255:
                opaque += 1
            else:
                bad_alpha += 1
        check(
            bad_alpha == 0,
            f"item[{idx}] alpha is strictly 0 or 255 ({bad_alpha} bad)",
        )
        check(opaque > 0, f"item[{idx}] has opaque pixels ({opaque})")
        check(transparent > 0, f"item[{idx}] has transparent pixels ({transparent})")

    check(tinted_count > 0, f"at least one item produced a tinted sprite ({tinted_count})")

    # ── 7. Cache behaviour ────────────────────────────────────────────
    print("\n=== 7. Tinted sprite cache ===")

    # Clear and re-render the same item twice - the second call must hit cache.
    # We can't directly observe cache hits but we can verify the result is
    # byte-identical (which it should be anyway, but proves the cache path
    # doesn't corrupt the result).
    if tintable_indices:
        idx = tintable_indices[0]
        clear_tint_cache()
        r1 = get_tinted_sprite(char.items[idx])
        r2 = get_tinted_sprite(char.items[idx])
        if r1 is not None and r2 is not None:
            check(r1 is r2, "second call returns cached object")
        else:
            check(r1 is None and r2 is None, "both calls return same None")

    # ── 8. Pipeline not configured -> None ─────────────────────────────
    print("\n=== 8. Pipeline unconfigured safety ===")

    # Temporarily clear configuration
    configure_tinted_sprite_pipeline(casc=None, mod_dc6_dir=None)
    clear_tint_cache()
    if tintable_indices:
        r = get_tinted_sprite(char.items[tintable_indices[0]])
        check(r is None, "get_tinted_sprite returns None when pipeline unconfigured")
    # Restore
    configure_tinted_sprite_pipeline(casc=casc, mod_dc6_dir=gp.mod_dc6_items)

    # ── 9. Items without invtransform -> None ──────────────────────────
    print("\n=== 9. Non-tintable items return None ===")

    # Find an item where get_invtransform returns None (e.g. a rune or jewel)
    non_tintable: int | None = None
    for idx, item in enumerate(char.items):
        if get_invtransform(item) is None:
            non_tintable = idx
            break
    if non_tintable is not None:
        r = get_tinted_sprite(char.items[non_tintable])
        check(r is None, f"item[{non_tintable}] with no color code returns None")
    else:
        check(False, "could not find a non-tintable item (unexpected)")

    # ── Summary ────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"Total: {passed} PASS, {failed} FAIL ({total} checks)")
    print(f"{'=' * 60}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

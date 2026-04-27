#!/usr/bin/env python3
"""Unit tests for d2rr_toolkit.display.sprite_keys.sprite_key_for_item.

Covers all four key grammars (plain, gfx-only, unique, unique+gfx) and
the safe-default path for simple items without extended data.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _make_item(
    code: str,
    *,
    quality: int = 2,
    has_gfx: bool = False,
    gfx_index: int = 0,
    unique_type_id: int | None = None,
):
    """Build a ParsedItem with just the fields sprite_key_for_item reads."""
    from d2rr_toolkit.models.character import (
        ItemExtendedHeader,
        ItemFlags,
        ParsedItem,
    )

    flags = ItemFlags.model_construct(
        identified=True,
        socketed=False,
        starter_item=False,
        simple=False,
        ethereal=False,
        personalized=False,
        runeword=False,
        location_id=0,
        equipped_slot=0,
        panel_id=0,
        position_x=0,
        position_y=0,
    )
    extended = ItemExtendedHeader.model_construct(
        unique_item_id=0,
        item_level=1,
        quality=quality,
        quality_name="",
        has_custom_graphics=has_gfx,
        gfx_index=gfx_index,
        has_class_specific_data=False,
    )
    return ParsedItem.model_construct(
        item_code=code,
        flags=flags,
        extended=extended,
        unique_type_id=unique_type_id,
    )


def main() -> int:
    from d2rr_toolkit.display.sprite_keys import sprite_key_for_item

    passed = 0
    failed = 0

    def check(got: str, expected: str, name: str) -> None:
        nonlocal passed, failed
        if got == expected:
            passed += 1
            print(f"  PASS  {name}")
        else:
            failed += 1
            print(f"  FAIL  {name} -- expected '{expected}', got '{got}'")

    # -- Plain base sprite ---------------------------------------------------
    item = _make_item("hax", quality=2, has_gfx=False)
    check(sprite_key_for_item(item), "hax", "magic hand axe -> 'hax'")

    # -- GFX variant only (e.g. a Magic charm with custom graphics) ---------
    item = _make_item("cm1", quality=4, has_gfx=True, gfx_index=2)
    check(sprite_key_for_item(item), "g-cm1-2", "magic charm gfx=2 -> 'g-cm1-2'")

    # -- Unique without custom graphics -------------------------------------
    item = _make_item("rin", quality=7, has_gfx=False, unique_type_id=42)
    check(sprite_key_for_item(item), "u-rin-42", "unique ring uid=42 -> 'u-rin-42'")

    # -- Unique + GFX (e.g. Unique Charm with gfx_index variant) ------------
    item = _make_item("cs1", quality=7, has_gfx=True, gfx_index=2, unique_type_id=12)
    check(
        sprite_key_for_item(item),
        "ug-cs1-12-2",
        "unique+gfx charm -> 'ug-cs1-12-2'",
    )

    # -- Unique WITHOUT a unique_type_id degrades to gfx / base -------------
    # (pre-1.07 items, or a degraded unique missing its ID)
    item = _make_item("rin", quality=7, has_gfx=False, unique_type_id=None)
    check(
        sprite_key_for_item(item),
        "rin",
        "unique without unique_type_id falls back to base",
    )

    # -- Simple item (no extended header at all) ----------------------------
    from d2rr_toolkit.models.character import ItemFlags, ParsedItem

    flags = ItemFlags.model_construct(
        identified=True,
        socketed=False,
        starter_item=False,
        simple=True,
        ethereal=False,
        personalized=False,
        runeword=False,
        location_id=0,
        equipped_slot=0,
        panel_id=0,
        position_x=0,
        position_y=0,
    )
    simple_item = ParsedItem.model_construct(
        item_code="hp1",
        flags=flags,
        extended=None,
    )
    check(sprite_key_for_item(simple_item), "hp1", "simple item -> base code only")

    # -- Key is deterministic (same input -> same output) -------------------
    item1 = _make_item("cs1", quality=7, has_gfx=True, gfx_index=2, unique_type_id=12)
    item2 = _make_item("cs1", quality=7, has_gfx=True, gfx_index=2, unique_type_id=12)
    check(
        sprite_key_for_item(item1),
        sprite_key_for_item(item2),
        "same item -> same key (determinism)",
    )

    # -- Key does NOT change with item position (index-independence) --------
    item_a = _make_item("cs1", quality=7, has_gfx=True, gfx_index=2, unique_type_id=12)
    item_b = _make_item("cs1", quality=7, has_gfx=True, gfx_index=2, unique_type_id=12)
    # Only positional fields differ - key must be identical.
    item_b.flags.position_x = 5
    item_b.flags.position_y = 3
    check(
        sprite_key_for_item(item_a),
        sprite_key_for_item(item_b),
        "position change does not affect sprite key",
    )

    print("-" * 72)
    print(f"Total: {passed} PASS, {failed} FAIL")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

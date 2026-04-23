#!/usr/bin/env python3
"""Unit tests for d2rr_toolkit.display.inventory_layout.

Covers the two pure helpers rescued from the legacy GUI server:
``build_occupancy_grid`` and ``item_fits``. These are pure domain
functions with no external state, so we can exercise them with lightweight
synthetic ParsedItem instances and never touch game data.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _make_item(code: str, panel: int, x: int, y: int, location: int = 0):
    """Build a minimal ParsedItem with just the fields the grid reads.

    Uses ``model_construct`` to bypass validation so we only have to set
    the handful of fields the layout helpers actually read. The full
    ItemFlags/ParsedItem schema has 20+ required fields that are
    irrelevant to pure occupancy-grid logic.
    """
    from d2rr_toolkit.models.character import ItemFlags, ParsedItem

    flags = ItemFlags.model_construct(
        identified=True,
        socketed=False,
        starter_item=False,
        simple=False,
        ethereal=False,
        personalized=False,
        runeword=False,
        location_id=location,
        equipped_slot=0,
        panel_id=panel,
        position_x=x,
        position_y=y,
    )
    return ParsedItem.model_construct(
        item_code=code,
        flags=flags,
    )


def _fixed_size(size_map: dict[str, tuple[int, int]]):
    def _lookup(code: str) -> tuple[int, int]:
        return size_map[code]

    return _lookup


def main() -> int:
    from d2rr_toolkit.display.inventory_layout import (
        build_occupancy_grid,
        item_fits,
    )

    passed = 0
    failed = 0

    def check(cond: bool, name: str, detail: str = "") -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"  PASS  {name}")
        else:
            failed += 1
            suffix = f" -- {detail}" if detail else ""
            print(f"  FAIL  {name}{suffix}")

    # -- Test 1: empty inventory --> all cells free, nothing occupied --------
    grid = build_occupancy_grid(
        items=[],
        panel_id=0,
        grid_w=10,
        grid_h=8,
        get_item_size=_fixed_size({}),
    )
    check(
        all(not cell for row in grid for cell in row),
        "empty inventory -> grid is all-False",
    )
    check(
        len(grid) == 8 and all(len(row) == 10 for row in grid),
        "grid shape matches grid_w x grid_h",
    )

    # -- Test 2: single 2x3 item at (1,1) occupies the right cells -----------
    sizes = _fixed_size({"arm": (2, 3)})
    grid = build_occupancy_grid(
        items=[_make_item("arm", panel=0, x=1, y=1)],
        panel_id=0,
        grid_w=10,
        grid_h=8,
        get_item_size=sizes,
    )
    occupied = {(x, y) for y, row in enumerate(grid) for x, cell in enumerate(row) if cell}
    expected = {(1, 1), (2, 1), (1, 2), (2, 2), (1, 3), (2, 3)}
    check(
        occupied == expected,
        "2x3 item at (1,1) occupies 6 expected cells",
        f"got {sorted(occupied)}",
    )

    # -- Test 3: item in a different panel is ignored ------------------------
    grid = build_occupancy_grid(
        items=[_make_item("arm", panel=5, x=0, y=0)],  # stash panel
        panel_id=0,  # asking for inventory
        grid_w=10,
        grid_h=8,
        get_item_size=sizes,
    )
    check(
        all(not cell for row in grid for cell in row),
        "item in panel=5 is ignored when building panel=0 grid",
    )

    # -- Test 4: equipped items (location_id != 0) are ignored ---------------
    grid = build_occupancy_grid(
        items=[_make_item("arm", panel=0, x=0, y=0, location=1)],  # equipped
        panel_id=0,
        grid_w=10,
        grid_h=8,
        get_item_size=sizes,
    )
    check(
        all(not cell for row in grid for cell in row),
        "location_id!=0 items do not occupy grid cells",
    )

    # -- Test 5: item footprint extending past bounds is clipped, not crashing
    grid = build_occupancy_grid(
        items=[_make_item("arm", panel=0, x=9, y=7)],  # origin at last cell
        panel_id=0,
        grid_w=10,
        grid_h=8,
        get_item_size=sizes,  # 2x3 footprint
    )
    occupied = {(x, y) for y, row in enumerate(grid) for x, cell in enumerate(row) if cell}
    check(
        occupied == {(9, 7)},
        "out-of-bounds footprint is clipped to grid",
        f"got {sorted(occupied)}",
    )

    # -- Test 6: item_fits - empty grid, valid placement ---------------------
    grid = [[False] * 10 for _ in range(8)]
    check(
        item_fits(grid, x=0, y=0, w=2, h=3, grid_w=10, grid_h=8),
        "item_fits: 2x3 at (0,0) in empty 10x8 grid",
    )
    check(
        item_fits(grid, x=8, y=5, w=2, h=3, grid_w=10, grid_h=8),
        "item_fits: 2x3 at (8,5) exactly fills the lower-right corner",
    )

    # -- Test 7: item_fits - rejects out-of-bounds ---------------------------
    check(
        not item_fits(grid, x=9, y=0, w=2, h=3, grid_w=10, grid_h=8),
        "item_fits: x overflow rejected",
    )
    check(
        not item_fits(grid, x=0, y=6, w=2, h=3, grid_w=10, grid_h=8),
        "item_fits: y overflow rejected",
    )
    check(
        not item_fits(grid, x=-1, y=0, w=2, h=3, grid_w=10, grid_h=8),
        "item_fits: negative x rejected",
    )

    # -- Test 8: item_fits - rejects collisions ------------------------------
    grid[2][3] = True  # mark a single cell
    check(
        not item_fits(grid, x=2, y=1, w=3, h=2, grid_w=10, grid_h=8),
        "item_fits: collision with occupied cell rejected",
    )
    check(
        item_fits(grid, x=5, y=1, w=3, h=2, grid_w=10, grid_h=8),
        "item_fits: placement away from occupied cell accepted",
    )

    print("-" * 72)
    print(f"Total: {passed} PASS, {failed} FAIL")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())


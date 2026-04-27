"""Inventory layout - 2D occupancy grids and fit detection.

Pure domain helpers for computing which cells of a character's inventory,
stash, or cube are currently occupied, and whether a given item would fit
at a candidate position. No I/O, no GUI assumptions, no third-party deps.

These helpers were originally implemented inside the legacy GUI server
(``d2rr_toolkit.gui.server``) but are framework-agnostic and generally
useful for any consumer that needs to place or restore items into a
character's layout (e.g. CLI restore, a future headless packer, or the
new GUI).

Typical usage:

    from d2rr_toolkit.display.inventory_layout import (
        build_occupancy_grid, item_fits,
    )

    grid = build_occupancy_grid(
        items=character.items,
        panel_id=0,              # 0 = inventory panel
        grid_w=10, grid_h=8,     # Reimagined inventory is 10x8
        get_item_size=type_db.get_inv_dimensions,
    )
    if item_fits(grid, x=3, y=2, w=2, h=3, grid_w=10, grid_h=8):
        ...

Only items with ``location_id == 0`` (stored/in-panel) are counted as
occupying grid cells. Equipped, belt, and socket items are skipped.
"""

from __future__ import annotations

from typing import Iterable, Protocol

from d2rr_toolkit.models.character import ParsedItem

__all__ = [
    "InventoryGrid",
    "ItemSizeLookup",
    "build_occupancy_grid",
    "item_fits",
]


#: A 2D boolean grid indexed ``grid[y][x]``. ``True`` means the cell is
#: occupied by at least one item's footprint.
InventoryGrid = list[list[bool]]


class ItemSizeLookup(Protocol):
    """Callable returning ``(width, height)`` in inventory cells for an item code.

    Typically satisfied by ``ItemTypeDatabase.get_inv_dimensions``.
    """

    def __call__(self, item_code: str) -> tuple[int, int]: ...


#: Sentinel value for the ``location_id`` flag that identifies items stored
#: in the character's inventory/stash/cube panels (as opposed to equipped,
#: socketed, or on the belt). Kept local to avoid a dependency cycle with
#: ``d2rr_toolkit.constants``.
_LOCATION_STORED: int = 0


def build_occupancy_grid(
    items: Iterable[ParsedItem],
    panel_id: int,
    grid_w: int,
    grid_h: int,
    get_item_size: ItemSizeLookup,
) -> InventoryGrid:
    """Build a 2D occupancy grid for one inventory panel.

    Scans ``items`` and marks every cell covered by an in-panel item's
    footprint as ``True``. Items not stored in the given panel (different
    ``panel_id``, or ``location_id != 0`` such as equipped/socketed) are
    ignored. Items whose footprints would extend past the grid bounds are
    clipped to what actually fits - this mirrors how the game engine
    persists over-sized items during shrink-down mod transitions.

    Args:
        items: Iterable of parsed items belonging to the character.
        panel_id: Panel index to build the grid for. Reimagined layout:
            ``0`` = inventory, ``4`` = cube, ``5`` = stash (tab index
            is tracked separately via the stash model).
        grid_w: Grid width in inventory cells.
        grid_h: Grid height in inventory cells.
        get_item_size: Callable returning ``(w, h)`` for an item code,
            typically ``ItemTypeDatabase.get_inv_dimensions``.

    Returns:
        A fresh ``InventoryGrid`` with ``True`` on every cell that is
        occupied by at least one in-panel item.
    """
    grid: InventoryGrid = [[False] * grid_w for _ in range(grid_h)]
    for item in items:
        if item.flags.location_id != _LOCATION_STORED:
            continue
        if item.flags.panel_id != panel_id:
            continue
        w, h = get_item_size(item.item_code)
        origin_y = item.flags.position_y
        origin_x = item.flags.position_x
        for dy in range(h):
            for dx in range(w):
                cy = origin_y + dy
                cx = origin_x + dx
                if 0 <= cy < grid_h and 0 <= cx < grid_w:
                    grid[cy][cx] = True
    return grid


def item_fits(
    grid: InventoryGrid,
    x: int,
    y: int,
    w: int,
    h: int,
    grid_w: int,
    grid_h: int,
) -> bool:
    """Return ``True`` if a ``w * h`` item fits at ``(x, y)`` in ``grid``.

    An item fits when its entire footprint stays inside the grid bounds
    and every cell it would cover is currently free. Note the test is
    purely positional - quality, ethereality, and carry1 constraints
    are the caller's responsibility.

    Args:
        grid: Occupancy grid from :func:`build_occupancy_grid`.
        x: Candidate origin column (0-based).
        y: Candidate origin row (0-based).
        w: Item width in cells.
        h: Item height in cells.
        grid_w: Grid width in cells (must match the grid shape).
        grid_h: Grid height in cells (must match the grid shape).

    Returns:
        ``True`` when the item fits cleanly, otherwise ``False``.
    """
    if x < 0 or y < 0:
        return False
    if x + w > grid_w or y + h > grid_h:
        return False
    for dy in range(h):
        row = grid[y + dy]
        for dx in range(w):
            if row[x + dx]:
                return False
    return True

"""Display logic for D2R Reimagined items.

Pure computation modules for colors, socket layout, damage/defense
calculations, invtransform resolution, palette-based item tinting,
inventory layout and stable sprite cache keys.

All modules in this subpackage are pure-Python and must remain free of
third-party runtime dependencies (PIL is only loaded lazily, inside the
tinted sprite pipeline) so the toolkit can be embedded in headless
contexts without pulling in GUI stacks.
"""

from d2rr_toolkit.display.inventory_layout import (
    InventoryGrid,
    ItemSizeLookup,
    build_occupancy_grid,
    item_fits,
)
from d2rr_toolkit.display.invtransform import get_invtransform
from d2rr_toolkit.display.palette import (
    ColorMap,
    Palette,
    load_colormap,
    load_colors_txt,
    load_palette,
)
from d2rr_toolkit.display.sprite_keys import sprite_key_for_item
from d2rr_toolkit.display.tinted_sprite import (
    TintedSpriteResult,
    configure_tinted_sprite_pipeline,
    get_tinted_sprite,
)

__all__ = [
    # invtransform (color code resolution)
    "get_invtransform",
    # palette loaders
    "Palette",
    "ColorMap",
    "load_palette",
    "load_colormap",
    "load_colors_txt",
    # high-level tinted sprite API
    "TintedSpriteResult",
    "configure_tinted_sprite_pipeline",
    "get_tinted_sprite",
    # inventory layout helpers
    "InventoryGrid",
    "ItemSizeLookup",
    "build_occupancy_grid",
    "item_fits",
    # stable sprite cache keys
    "sprite_key_for_item",
]

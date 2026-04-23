"""Sprite resolution for D2R Reimagined.

Provides:
  - SpriteResolver for finding and loading single sprites on-demand
  - load_all_item_sprites() + make_sprite_key() for bulk preload
"""

from d2rr_toolkit.sprites.bulk_loader import (
    display_name_to_snake_case,
    load_all_item_sprites,
    load_items_json,
    load_set_sprite_map,
    load_set_sprite_map_with_aliases,
    load_unique_sprite_map,
    load_unique_sprite_map_with_aliases,
    make_sprite_key,
    prepare_bulk_sprite_loader,
)
from d2rr_toolkit.sprites.dc6_indexed import (
    IndexedDC6Frame,
    decode_dc6_indexed,
)
from d2rr_toolkit.sprites.resolver import SpriteResolver

__all__ = [
    "SpriteResolver",
    "display_name_to_snake_case",
    "load_all_item_sprites",
    "load_items_json",
    "load_set_sprite_map",
    "load_set_sprite_map_with_aliases",
    "load_unique_sprite_map",
    "load_unique_sprite_map_with_aliases",
    "make_sprite_key",
    "prepare_bulk_sprite_loader",
    # Palette-indexed DC6 decoder (for tinting pipeline)
    "IndexedDC6Frame",
    "decode_dc6_indexed",
]

"""Stable sprite-cache keys for parsed items.

Given a :class:`ParsedItem`, compute a small ASCII string that uniquely
identifies which inventory sprite the item should resolve to, regardless
of its position in the character's item list.

The key encodes the three axes that matter for sprite selection:

* base item code (``hax``, ``cm1``, ...)
* unique-type id, if the item is a Unique (quality ``7``)
* custom graphics index, if the item carries a ``has_custom_graphics`` flag

so that any consumer - a CLI sprite dumper, an on-disk PNG cache,
the new GUI's sprite endpoint - can derive the same key without keeping
the character's item list around.

Key grammar::

    ug-<code>-<uid>-<gfx>   Unique + GFX variant  (e.g. "ug-cs1-12-2")
    u-<code>-<uid>          Unique                (e.g. "u-rin-42")
    g-<code>-<gfx>          GFX variant only      (e.g. "g-cm1-2")
    <code>                  Plain base sprite     (e.g. "hax")

The fallback chain mirrors the in-game lookup order (unique sprite ->
gfx variant -> base invfile), so a consumer can parse a key back into
the exact sequence of sprite lookups to attempt.
"""

from __future__ import annotations

from d2rr_toolkit.models.character import ParsedItem

__all__ = ["sprite_key_for_item"]


#: Quality enum value for Unique items. Kept local rather than imported
#: from ``d2rr_toolkit.constants`` to keep this module dependency-free.
_QUALITY_UNIQUE: int = 7


def sprite_key_for_item(item: ParsedItem) -> str:
    """Return a stable, index-independent sprite cache key for *item*.

    The key is safe to use as a filesystem name, a URL path segment, or
    a dict key. It does not depend on the item's position within the
    character, so indices can shift (items added, removed, reordered)
    without invalidating downstream caches.

    Args:
        item: A parsed item from a D2S/D2I file.

    Returns:
        A short ASCII string following the grammar documented in the
        module docstring.

    Example:
        >>> sprite_key_for_item(unique_charm)      # doctest: +SKIP
        'ug-cs1-12-2'
        >>> sprite_key_for_item(unique_ring)       # doctest: +SKIP
        'u-rin-42'
        >>> sprite_key_for_item(magic_chest)       # doctest: +SKIP
        'g-aar-1'
        >>> sprite_key_for_item(white_hand_axe)    # doctest: +SKIP
        'hax'
    """
    # ``extended`` is optional on simple items; default to "magic" quality
    # (2) and no custom graphics if absent - matches the game's own
    # behavior when reading pre-1.10 simple items.
    quality_id = item.extended.quality if item.extended else 2
    has_gfx = bool(item.extended and item.extended.has_custom_graphics)
    gfx_idx = item.extended.gfx_index if has_gfx and item.extended else 0

    if quality_id == _QUALITY_UNIQUE and item.unique_type_id is not None:
        if has_gfx:
            # Unique + GFX variant needs the full fallback chain:
            # unique sprite -> gfx variant -> base invfile. Consumers
            # parse this 4-part form to drive each probe in turn.
            return f"ug-{item.item_code}-{item.unique_type_id}-{gfx_idx}"
        return f"u-{item.item_code}-{item.unique_type_id}"

    if has_gfx:
        return f"g-{item.item_code}-{gfx_idx}"

    return item.item_code

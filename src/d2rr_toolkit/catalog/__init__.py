"""Item catalog - enumerate filterable types and their base items.

This module provides the data layer behind GUI filter dropdowns
("Select Item Type" + "Select Equipment"). Everything is derived
from the Reimagined Excel files at load time; no item names,
category labels, or hierarchy edges are hardcoded in Python.

See :class:`ItemCatalog` for the public query API and
:mod:`d2rr_toolkit.catalog.item_catalog` for implementation details.
"""

from d2rr_toolkit.catalog.item_catalog import (
    ItemCatalog,
    ItemEntry,
    ItemTypeEntry,
    get_item_catalog,
    load_item_catalog,
)

__all__ = [
    "ItemCatalog",
    "ItemEntry",
    "ItemTypeEntry",
    "get_item_catalog",
    "load_item_catalog",
]


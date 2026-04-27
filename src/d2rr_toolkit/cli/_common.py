"""Shared helpers for the ``d2rr-toolkit`` CLI sub-modules.

Hosts the game-data loader entry points that every command calls before
touching a save file.
"""

from __future__ import annotations

from pathlib import Path

from d2rr_toolkit.game_data.charstats import load_charstats
from d2rr_toolkit.game_data.cubemain import load_cubemain
from d2rr_toolkit.game_data.gems import load_gems
from d2rr_toolkit.game_data.item_names import load_item_names
from d2rr_toolkit.game_data.item_stat_cost import load_item_stat_cost
from d2rr_toolkit.game_data.item_types import load_item_types
from d2rr_toolkit.game_data.properties import load_properties
from d2rr_toolkit.game_data.property_formatter import load_property_formatter
from d2rr_toolkit.game_data.automagic import load_automagic
from d2rr_toolkit.game_data.sets import load_sets
from d2rr_toolkit.game_data.skills import load_skills


def _load_game_data(d2s_file: Path) -> bool:
    """Initialise every game-data database via the Iron Rule.

    Returns ``True`` on success, ``False`` when the Reimagined mod
    install cannot be located. The ``d2s_file`` argument is kept for
    call-site symmetry (every CLI command receives a save path and
    needs the game data loaded before touching it) but plays no role
    in loader configuration any more.
    """
    from d2rr_toolkit.config import get_game_paths

    gp = get_game_paths()
    if not gp.reimagined_excel.is_dir():
        return False
    _do_load_game_data()
    return True


def _do_load_game_data() -> None:
    """Run every loader in the order dictated by their data dependencies.

    All loaders read through the shared :class:`CASCReader` singleton
    (Reimagined mod first, D2R Resurrected CASC second). No arguments
    are passed - every loader resolves its files independently via the
    Iron Rule.
    """
    load_item_types()
    load_item_stat_cost()
    load_skills()
    load_cubemain()
    load_charstats()
    load_item_names()
    load_properties()
    load_property_formatter()
    load_sets()
    load_automagic()
    load_gems()
    # ItemCatalog depends on ItemTypeDatabase + ItemNamesDatabase
    # being populated - must come LAST.
    from d2rr_toolkit.catalog import load_item_catalog

    load_item_catalog()

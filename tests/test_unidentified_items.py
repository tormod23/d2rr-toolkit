"""TC77 - Unidentified items show only base stats, never affix details.

In D2R, items with ``flags.identified == False`` display ONLY:
  - base item name (no prefix/suffix, no unique/set label)
  - base defense / damage
  - durability
  - base strength / dexterity / level requirements
  - a "Unidentified" line (corrupted-red in the CLI)

Everything else is hidden: magical properties, set bonuses, runeword
properties. Identification in-game reveals the full name and stats.

Before fix:
  - ``ItemNamesDatabase.build_display_name`` always resolved the full
    name, revealing set/unique identity prematurely.
  - ``PropertyFormatter.format_properties_grouped`` emitted every stat
    regardless of identification state.
  - CLI ``_render_item_panel`` printed full property/set-bonus blocks
    for unidentified items.

After fix:
  - ``build_display_name(identified=False)`` returns base name + tier
    only (a set Heavy Boots parses to "Heavy Boots", not "Sander's
    Riprap").
  - ``format_properties_grouped`` returns [] when passed an
    ``item=`` whose ``flags.identified`` is False.
  - The CLI item panel short-circuits after base stats and appends
    an "Unidentified" corrupted-red line.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest


@pytest.fixture(scope="module")
def dbs():
    from d2rr_toolkit.game_data.charstats import load_charstats
    from d2rr_toolkit.game_data.item_names import (
        get_item_names_db,
        load_item_names,
    )
    from d2rr_toolkit.game_data.item_stat_cost import (
        get_isc_db,
        load_item_stat_cost,
    )
    from d2rr_toolkit.game_data.item_types import load_item_types
    from d2rr_toolkit.game_data.properties import (
        get_properties_db,
        load_properties,
    )
    from d2rr_toolkit.game_data.property_formatter import (
        get_property_formatter,
        load_property_formatter,
    )
    from d2rr_toolkit.game_data.skills import get_skill_db, load_skills

    load_item_types()
    load_charstats()
    load_item_names()
    load_properties()
    load_item_stat_cost()
    load_skills()
    load_property_formatter()
    return {
        "names": get_item_names_db(),
        "props": get_properties_db(),
        "isc": get_isc_db(),
        "skills": get_skill_db(),
        "fmt": get_property_formatter(),
    }


# ─────────────────────────────────────────────────────────────────────
# §1  build_display_name gate
# ─────────────────────────────────────────────────────────────────────


def test_set_item_unidentified_shows_base_name(dbs):
    """Sander's Riprap (set Heavy Boots) unidentified -> just 'Heavy Boots'."""
    names = dbs["names"]
    # vbt + quality=5 -> should be "Sander's Riprap" when identified
    full = names.build_display_name("vbt", quality=5, set_item_id=0, identified=True)
    unid = names.build_display_name("vbt", quality=5, set_item_id=0, identified=False)
    assert full is not None
    assert unid is not None
    # Unidentified name must equal the pure base name (no set label leak).
    base = names.get_base_item_name("vbt")
    assert unid == base, f"unid name leaked set info: {unid!r} vs base {base!r}"
    # And must DIFFER from the identified version (sanity on the fixture).
    assert full != unid, "set name resolved identically for unid - test fixture broken"


def test_magic_item_unidentified_strips_affixes(dbs):
    """Magic ring with prefix+suffix unidentified -> just 'Ring'."""
    names = dbs["names"]
    # rin quality=4 with arbitrary prefix/suffix IDs
    full = names.build_display_name(
        "rin",
        quality=4,
        prefix_id=1,
        suffix_id=1,
        identified=True,
    )
    unid = names.build_display_name(
        "rin",
        quality=4,
        prefix_id=1,
        suffix_id=1,
        identified=False,
    )
    base = names.get_base_item_name("rin")
    assert unid == base, f"affix leaked on unid: {unid!r}"
    # Identified name is at least as long as base (prefix/suffix attached).
    assert full is None or len(full) >= len(base)


def test_rare_item_unidentified_strips_rare_name(dbs):
    """Rare ring unidentified -> just 'Ring', no two-word rare name."""
    names = dbs["names"]
    full = names.build_display_name(
        "rin",
        quality=6,
        rare_name_id1=0,
        rare_name_id2=0,
        identified=True,
    )
    unid = names.build_display_name(
        "rin",
        quality=6,
        rare_name_id1=0,
        rare_name_id2=0,
        identified=False,
    )
    base = names.get_base_item_name("rin")
    assert unid == base, f"rare name leaked on unid: {unid!r}"


def test_tier_suffix_still_applied_when_unidentified(dbs):
    """Base name includes tier marker [N]/[X]/[E] on unidentified too."""
    names = dbs["names"]
    unid = names.build_display_name(
        "vbt",
        quality=5,
        set_item_id=0,
        tier_suffix=" [N]",
        identified=False,
    )
    assert unid and unid.endswith(" [N]"), unid


# ─────────────────────────────────────────────────────────────────────
# §2  format_properties_grouped gate
# ─────────────────────────────────────────────────────────────────────


def test_format_properties_grouped_empty_for_unidentified(dbs):
    """Unidentified item -> no property lines returned."""
    fmt = dbs["fmt"]
    isc = dbs["isc"]
    # Craft a fake item with identified=False.
    item = SimpleNamespace(
        flags=SimpleNamespace(identified=False),
        item_code="vbt",
    )
    # Non-empty property list - must still return empty.
    props = [
        {"stat_id": 0, "name": "strength", "value": 10, "param": 0},
        {"stat_id": 31, "name": "armorclass", "value": 50, "param": 0},
    ]
    out = fmt.format_properties_grouped(props, isc, item=item)
    assert out == [], f"properties leaked on unidentified: {out}"


def test_format_properties_grouped_unchanged_for_identified(dbs):
    """Identified item -> full property output (regression check)."""
    fmt = dbs["fmt"]
    isc = dbs["isc"]
    item = SimpleNamespace(
        flags=SimpleNamespace(identified=True),
        item_code="vbt",
    )
    props = [
        {"stat_id": 0, "name": "strength", "value": 10, "param": 0},
    ]
    out = fmt.format_properties_grouped(props, isc, item=item)
    assert len(out) >= 1
    # Contains the strength line
    joined = " | ".join(p.plain_text for p in out)
    assert "Strength" in joined, joined


def test_format_properties_grouped_no_item_kwarg(dbs):
    """Without an ``item`` kwarg, the gate is bypassed (back-compat).

    Callers that never supply an item get the pre-patch behaviour. The
    identification gate is opt-in per call via ``item=``.
    """
    fmt = dbs["fmt"]
    isc = dbs["isc"]
    props = [{"stat_id": 0, "name": "strength", "value": 10, "param": 0}]
    out = fmt.format_properties_grouped(props, isc)  # no item kwarg
    assert len(out) >= 1


# ─────────────────────────────────────────────────────────────────────
# §3  End-to-end: live stash unidentified set item
# ─────────────────────────────────────────────────────────────────────


def test_live_stash_unidentified_heavy_boots_if_present(dbs):
    """If the live SharedStash has an unidentified set Heavy Boots, the
    display gate returns its base name, not the set name."""
    from pathlib import Path
    from d2rr_toolkit.parsers.d2i_parser import D2IParser

    from d2rr_toolkit.config import resolve_save_dir
    from d2rr_toolkit.exceptions import ConfigurationError

    try:
        live = resolve_save_dir() / "ModernSharedStashSoftCoreV2.d2i"
    except ConfigurationError:
        pytest.skip("Live stash path unresolvable (set D2RR_SAVE_DIR).")
    if not live.exists():
        pytest.skip("Live stash not available in this environment")
    stash = D2IParser(live).parse()
    names = dbs["names"]
    found = False
    for tab in stash.tabs:
        for it in tab.items:
            if (
                it.item_code == "vbt"
                and it.extended
                and it.extended.quality == 5
                and not it.flags.identified
            ):
                found = True
                unid_name = names.build_display_name(
                    it.item_code,
                    it.extended.quality,
                    set_item_id=it.set_item_id,
                    identified=False,
                )
                # Must be the base name "Heavy Boots", never the set name.
                assert unid_name == names.get_base_item_name(
                    "vbt"
                ), f"live unid leak: {unid_name!r}"
                # And with identified=True, we'd get the set label.
                id_name = names.build_display_name(
                    it.item_code,
                    it.extended.quality,
                    set_item_id=it.set_item_id,
                    identified=True,
                )
                assert id_name != unid_name, f"identified/unid names collapsed: {id_name!r}"
    if not found:
        pytest.skip("No unidentified vbt in current live stash")


# ─────────────────────────────────────────────────────────────────────
# §4  ParsedItem.is_identified convenience accessor
# ─────────────────────────────────────────────────────────────────────


def test_parsed_item_is_identified_property():
    """Top-level accessor mirrors flags.identified and works for both states."""
    from d2rr_toolkit.models.character import ItemFlags, ParsedItem

    item = ParsedItem(
        item_code="vbt",
        flags=ItemFlags(
            identified=True,
            socketed=False,
            starter_item=False,
            simple=False,
            ethereal=False,
            personalized=False,
            runeword=False,
            location_id=0,
            equipped_slot=0,
            position_x=0,
            position_y=0,
            panel_id=1,
        ),
    )
    assert item.is_identified is True
    item2 = item.model_copy(update={"flags": item.flags.model_copy(update={"identified": False})})
    assert item2.is_identified is False


# ─────────────────────────────────────────────────────────────────────
# §5  archive.py refuses unidentified items
# ─────────────────────────────────────────────────────────────────────


def test_archive_refuses_unidentified_item(tmp_path):
    """extract_from_d2i must refuse to archive unidentified items.

    Uses the live SharedStash if it contains at least one unidentified
    item; skips otherwise. The live save is the only fixture with
    unidentified items in the current repo.
    """
    from pathlib import Path

    from d2rr_toolkit.archive import ArchiveError, extract_from_d2i
    from d2rr_toolkit.database.item_db import open_item_db
    from d2rr_toolkit.parsers.d2i_parser import D2IParser

    from d2rr_toolkit.config import resolve_save_dir
    from d2rr_toolkit.exceptions import ConfigurationError

    try:
        live = resolve_save_dir() / "ModernSharedStashSoftCoreV2.d2i"
    except ConfigurationError:
        pytest.skip("Live stash path unresolvable (set D2RR_SAVE_DIR).")
    if not live.exists():
        pytest.skip("Live stash not available in this environment")

    stash = D2IParser(live).parse()
    unid_location = None
    for tab_idx, tab in enumerate(stash.tabs):
        for item_idx, it in enumerate(tab.items):
            if it.flags and not it.flags.identified:
                unid_location = (tab_idx, item_idx)
                break
        if unid_location:
            break
    if unid_location is None:
        pytest.skip("No unidentified item in live stash right now")

    # Copy to tmp - we must not mutate the user's real save file even on
    # a thrown exception. The archive.create_backup call inside
    # extract_from_d2i would otherwise pollute ~/.d2rr_toolkit/backups
    # with the real stash name.
    work = tmp_path / "stash.d2i"
    work.write_bytes(live.read_bytes())
    db_path = tmp_path / "archive.db"
    db = open_item_db("softcore", db_path=db_path)
    try:
        tab_idx, item_idx = unid_location
        with pytest.raises(ArchiveError, match="unidentified"):
            extract_from_d2i(work, tab_idx, item_idx, db, display_name="test")
        # And the file must be byte-identical to the original (no
        # backup written, no modification).
        assert (
            work.read_bytes() == live.read_bytes()
        ), "Refused archive still mutated the stash file"
    finally:
        db.close()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    pytest.main([__file__, "-v"])

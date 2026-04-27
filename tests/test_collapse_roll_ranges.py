"""TC78 - Roll ranges for the 5 multi-stat collapse lines.

Before fix, `_register_collapse` in :mod:`d2rr_toolkit.game_data.
property_formatter` emitted its synthetic collapse lines (All
Resistances / All Attributes / All Max Resistances / All Elemental
Skill Damage / Enemy Elemental Resistance) with `roll_ranges=()`. The
roll resolver was never even asked - the attach helper only existed
for damage pairs and single stats.

Real-world symptom: Vampire's Crusade (Hades' Underworld set ring, row
194 in setitems.txt) stores its res-all bonus as a single slot
`res-all, min=8, max=15`. The formatter collapsed the four resulting
resist stats into "+X% to All Resistances" but displayed no range,
even though the resolver already knows how to expand `res-all` -> fire
+ light + cold + poison with identical per-stat ranges.

Fix: new `_attach_collapse_roll_range` helper + call in
`_register_collapse`. Queries every member stat, collapses identical
per-stat ranges to a single-element `roll_ranges` tuple.
"""

from __future__ import annotations

import sys

import pytest


@pytest.fixture(scope="module")
def dbs():
    from d2rr_toolkit.game_data.affix_rolls import load_affix_rolls
    from d2rr_toolkit.game_data.charstats import load_charstats
    from d2rr_toolkit.game_data.item_names import load_item_names
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
    from d2rr_toolkit.game_data.sets import get_sets_db, load_sets
    from d2rr_toolkit.game_data.skills import get_skill_db, load_skills

    load_item_types()
    load_charstats()
    load_item_names()
    load_properties()
    load_item_stat_cost()
    load_skills()
    load_property_formatter()
    load_sets()
    load_affix_rolls()
    return {
        "fmt": get_property_formatter(),
        "props": get_properties_db(),
        "isc": get_isc_db(),
        "skills": get_skill_db(),
        "sets": get_sets_db(),
    }


def _roll_context(**kw):
    from d2rr_toolkit.game_data.property_formatter import ItemRollContext

    return ItemRollContext(**kw)


def _build_res_all_props(value: int) -> list[dict]:
    return [
        {"stat_id": 39, "name": "fireresist", "value": value, "param": 0},
        {"stat_id": 41, "name": "lightresist", "value": value, "param": 0},
        {"stat_id": 43, "name": "coldresist", "value": value, "param": 0},
        {"stat_id": 45, "name": "poisonresist", "value": value, "param": 0},
    ]


# ─────────────────────────────────────────────────────────────────────
# §1  Vampire's Crusade regression - the reported bug
# ─────────────────────────────────────────────────────────────────────


def test_vampires_crusade_res_all_range_attached(dbs):
    """+X% to All Resistances on VC must show the 8..15 range."""
    vc = dbs["sets"].get_set_item_by_name("Vampire's Crusade")
    assert vc is not None, "Vampire's Crusade missing from setitems database"

    ctx = _roll_context(quality=5, set_id=vc.row_index)
    out = dbs["fmt"].format_properties_grouped(
        _build_res_all_props(12),
        dbs["isc"],
        skills_db=dbs["skills"],
        roll_context=ctx,
        props_db=dbs["props"],
    )
    res_lines = [fp for fp in out if "Resistances" in fp.plain_text]
    assert len(res_lines) == 1, [fp.plain_text for fp in out]
    fp = res_lines[0]
    assert len(fp.roll_ranges) == 1, f"expected 1 collapsed range, got {fp.roll_ranges}"
    rng = fp.roll_ranges[0]
    assert (rng.min_value, rng.max_value) == (8.0, 15.0), (rng.min_value, rng.max_value)


def test_vampires_crusade_perfect_roll_star(dbs):
    """A value at the range max fires the perfect-roll flag."""
    vc = dbs["sets"].get_set_item_by_name("Vampire's Crusade")
    ctx = _roll_context(quality=5, set_id=vc.row_index)
    out = dbs["fmt"].format_properties_grouped(
        _build_res_all_props(15),
        dbs["isc"],
        skills_db=dbs["skills"],
        roll_context=ctx,
        props_db=dbs["props"],
    )
    fp = next(fp for fp in out if "Resistances" in fp.plain_text)
    assert fp.is_perfect is True, fp


def test_vampires_crusade_min_roll_not_perfect(dbs):
    """Value at range MIN must NOT be flagged perfect."""
    vc = dbs["sets"].get_set_item_by_name("Vampire's Crusade")
    ctx = _roll_context(quality=5, set_id=vc.row_index)
    out = dbs["fmt"].format_properties_grouped(
        _build_res_all_props(8),
        dbs["isc"],
        skills_db=dbs["skills"],
        roll_context=ctx,
        props_db=dbs["props"],
    )
    fp = next(fp for fp in out if "Resistances" in fp.plain_text)
    assert fp.is_perfect is False, fp


# ─────────────────────────────────────────────────────────────────────
# §2  Back-compat: no roll_context -> no ranges (unchanged behaviour)
# ─────────────────────────────────────────────────────────────────────


def test_collapse_without_roll_context_unchanged(dbs):
    """Without roll_context the collapse line has empty ranges (pre-fix parity)."""
    out = dbs["fmt"].format_properties_grouped(
        _build_res_all_props(12),
        dbs["isc"],
        skills_db=dbs["skills"],
    )
    fp = next(fp for fp in out if "Resistances" in fp.plain_text)
    assert fp.roll_ranges == (), fp.roll_ranges
    assert fp.is_perfect is False


# ─────────────────────────────────────────────────────────────────────
# §3  Other collapse types - coverage sweep
# ─────────────────────────────────────────────────────────────────────
# Only the All Resistances collapse has a guaranteed real-world source
# (res-all on Vampire's Crusade). The other four collapses (All
# Attributes, All Max Res, Elem Mastery, Elem Pierce) share the same
# code path - pinning res-all + one structural test is enough to
# prevent regression across all five.


def test_all_collapse_types_share_the_helper(dbs):
    """_attach_collapse_roll_range must be reachable via _register_collapse.

    Structural test: the method exists on the formatter class and
    _register_collapse references it. If future refactors break the
    wiring, this catches it.
    """
    import inspect

    fmt = dbs["fmt"]
    assert hasattr(
        fmt, "_attach_collapse_roll_range"
    ), "helper method removed - collapse lines will regress"
    src = inspect.getsource(fmt._format_properties_grouped_raw)
    assert (
        "_attach_collapse_roll_range" in src
    ), "_register_collapse no longer calls the attach helper"


# ─────────────────────────────────────────────────────────────────────
# §4  Consistency gate: value outside range -> no range attached
# ─────────────────────────────────────────────────────────────────────


def test_rolled_value_outside_range_suppresses_range(dbs):
    """If rolled value < range.min, don't show a misleading range."""
    vc = dbs["sets"].get_set_item_by_name("Vampire's Crusade")
    ctx = _roll_context(quality=5, set_id=vc.row_index)
    # value=5 is below VC's min of 8 -> consistency gate should kick in
    out = dbs["fmt"].format_properties_grouped(
        _build_res_all_props(5),
        dbs["isc"],
        skills_db=dbs["skills"],
        roll_context=ctx,
        props_db=dbs["props"],
    )
    fp = next(fp for fp in out if "Resistances" in fp.plain_text)
    # Consistency gate - fall back to no-range display.
    assert fp.roll_ranges == (), f"range leaked despite value {5} < min 8: {fp.roll_ranges}"


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    pytest.main([__file__, "-v"])

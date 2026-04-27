"""TC76 - Func-only property codes in sets/setitems render with in-game labels.

Before fix, `format_code_value('dmg%', 200, ...)` returned literal
``'+200 dmg%'`` because properties.txt declares ``dmg%`` as func-only
(no ``stat1`` column) and the formatter bailed on ``primary_stat_id is None``.
Real-world impact: Set full-set bonuses like the Forsaken Divinity
"+200% Enhanced Weapon Damage" displayed as "+200 DMG%" in tooltips.

Fix: :mod:`d2rr_toolkit.game_data.property_formatter` now maps the 5
func-only codes that actually appear in sets.txt / setitems.txt
(``dmg%``, ``dmg-min``, ``dmg-max``, ``indestruct``, ``ethereal``) to
their canonical ISC stats or static strings and routes through the
existing template infrastructure.
"""

from __future__ import annotations

import sys

import pytest


@pytest.fixture(scope="module")
def formatter_trio():
    """Load all databases the set-bonus formatter depends on."""
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
    return {
        "fmt": get_property_formatter(),
        "props": get_properties_db(),
        "isc": get_isc_db(),
        "skills": get_skill_db(),
        "sets": get_sets_db(),
    }


# ─────────────────────────────────────────────────────────────────────
# §1  Direct format_code_value contract for all 5 func-only codes
# ─────────────────────────────────────────────────────────────────────


def test_dmg_percent_renders_enhanced_weapon_damage(formatter_trio):
    """`dmg%` is THE regression case - pin the exact in-game label."""
    out = formatter_trio["fmt"].format_code_value(
        "dmg%",
        200,
        "",
        formatter_trio["props"],
        formatter_trio["isc"],
        formatter_trio["skills"],
    )
    assert out == "+200% Enhanced Weapon Damage", out


def test_dmg_percent_negative_sign(formatter_trio):
    """Negative ED must carry the sign (no unsigned "%-50" output)."""
    out = formatter_trio["fmt"].format_code_value(
        "dmg%",
        -50,
        "",
        formatter_trio["props"],
        formatter_trio["isc"],
        formatter_trio["skills"],
    )
    assert out == "-50% Enhanced Weapon Damage", out


def test_dmg_min_routes_to_stat_21_template(formatter_trio):
    """`dmg-min` func-only -> stat 21 mindamage template."""
    out = formatter_trio["fmt"].format_code_value(
        "dmg-min",
        5,
        "",
        formatter_trio["props"],
        formatter_trio["isc"],
        formatter_trio["skills"],
    )
    # Must NOT be the raw-code fallback "+5 dmg-min"
    assert out is not None
    assert "dmg-min" not in out, f"raw code leaked: {out!r}"
    assert "5" in out, out


def test_dmg_max_routes_to_stat_22_template(formatter_trio):
    out = formatter_trio["fmt"].format_code_value(
        "dmg-max",
        10,
        "",
        formatter_trio["props"],
        formatter_trio["isc"],
        formatter_trio["skills"],
    )
    assert out is not None
    assert "dmg-max" not in out, f"raw code leaked: {out!r}"
    assert "10" in out, out


def test_indestruct_renders_static_label(formatter_trio):
    out = formatter_trio["fmt"].format_code_value(
        "indestruct",
        0,
        "",
        formatter_trio["props"],
        formatter_trio["isc"],
        formatter_trio["skills"],
    )
    assert out is not None
    assert "Indestructible" in out, out
    assert "indestruct" not in out, f"raw code leaked: {out!r}"


def test_ethereal_renders_static_label(formatter_trio):
    out = formatter_trio["fmt"].format_code_value(
        "ethereal",
        0,
        "",
        formatter_trio["props"],
        formatter_trio["isc"],
        formatter_trio["skills"],
    )
    assert out is not None
    assert "Ethereal" in out, out
    assert out != "+0 ethereal", f"raw code leaked: {out!r}"


# ─────────────────────────────────────────────────────────────────────
# §2  Regression: non-func-only codes remain unchanged
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "code,value,expected_substr",
    [
        ("str", 25, "Strength"),
        ("res-fire", 30, "Fire"),
        ("res-all", 25, "All Resistances"),
        ("ac%", 80, "Enhanced Defense"),
        ("allskills", 2, "All Skills"),
    ],
)
def test_regular_codes_unchanged(formatter_trio, code, value, expected_substr):
    out = formatter_trio["fmt"].format_code_value(
        code,
        value,
        "",
        formatter_trio["props"],
        formatter_trio["isc"],
        formatter_trio["skills"],
    )
    assert out is not None
    assert expected_substr in out, f"{code!r}: {out!r}"


# ─────────────────────────────────────────────────────────────────────
# §3  End-to-end: Forsaken Divinity full-set bonus renders correctly
# ─────────────────────────────────────────────────────────────────────


def test_forsaken_divinity_full_set_bonus(formatter_trio):
    """User-reported regression: Fall from Grace's set must show the
    correct "Enhanced Weapon Damage" label on the Full Set tier."""
    sets = formatter_trio["sets"]
    s = sets._sets.get("Forsaken Divinity")
    assert s is not None, "Forsaken Divinity set not in database"

    lines = []
    for entry in s.full_tier.entries:
        line = entry.format(
            formatter_trio["fmt"],
            formatter_trio["props"],
            formatter_trio["isc"],
            formatter_trio["skills"],
        )
        lines.append(line)

    joined = " | ".join(l or "<None>" for l in lines)
    assert "+200% Enhanced Weapon Damage" in joined, joined
    # And no raw code leaks anywhere
    assert "dmg%" not in joined, f"raw code leaked: {joined}"


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    pytest.main([__file__, "-v"])

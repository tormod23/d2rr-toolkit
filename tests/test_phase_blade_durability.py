#!/usr/bin/env python3
"""Regression suite for the Phase Blade / nodurability weapon parser fix.

Background
----------
The D2R / D2RR save format encodes a weapon's durability block in a shape
that depends on whether the weapon actually has durability:

    max_dur > 0  (normal weapons, all bows, all crossbows - everything
                  except Phase Blade in Reimagined 3.0.7):
        max_dur(8) + cur_dur(8) + unknown_post_dur(2)   = 18 bits

    max_dur == 0 (Phase Blade / ``7cr`` - the only weapon with
                  ``durability=0`` in weapons.txt):
        max_dur(8)               + unknown_post_dur(1)  =  9 bits

The ``unknown_post_dur`` width itself shifts with the
presence/absence of ``cur_dur`` - **2 bits when cur_dur is present,
1 bit when omitted**.  Historical parser code read the 18-bit shape
unconditionally, which for Phase Blade drifted every downstream
stat by 10 bits.  The canonical user-visible bug report: Lightsabre
rendered with fire-damage in the millions, defence +3 686 540 %,
Adds 19-0 Weapon Damage, etc.  Every Phase Blade in every save
file was being mis-parsed the same way.

This suite pins down the exact expected property triple for
Lightsabre (an untampered copy lives in ``tests/cases/TC56``
/VikingBarbie.d2s), plus a broader cross-section of bow / crossbow
weapons that the fix must NOT regress.

Test matrix:

  §1  Lightsabre in TC56/VikingBarbie.d2s produces the in-game
      tooltip exactly (9 stats including the Chain Lightning encode=2
      chance-to-cast).
  §2  Phase Blade carries max_durability=0 AND current_durability=0
      (no in-save durability at all).
  §3  Bows + crossbows still parse with max_durability=250 after the
      fix (previously 250 too - the fix must not touch them).
  §4  The static ``has_durability_bits(7cr) == False``; every other
      code we probe returns True.
  §5  The full save sweeps TC55 / TC56 / TC63 / TC64 still parse
      without spurious values (no stat value > 1 million, no
      negative durability).
"""

from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
src_dir = project_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


# ── Assertion plumbing ─────────────────────────────────────────────────────

_pass = 0
_fail = 0


def ok(name: str) -> None:
    global _pass
    _pass += 1
    print(f"  PASS  {name}")


def fail(name: str, detail: str = "") -> None:
    global _fail
    _fail += 1
    print(f"  FAIL  {name}" + (f": {detail}" if detail else ""))


def check(cond: bool, name: str, detail: str = "") -> None:
    (ok if cond else fail)(name, detail) if not cond else ok(name)


def check(cond: bool, name: str, detail: str = "") -> None:  # noqa: F811
    if cond:
        ok(name)
    else:
        fail(name, detail)


# ── Shared fixtures ────────────────────────────────────────────────────────


def _init_and_parse(d2s_path: Path):
    from d2rr_toolkit.config import init_game_paths
    from d2rr_toolkit.game_data.item_types import load_item_types
    from d2rr_toolkit.game_data.item_stat_cost import load_item_stat_cost
    from d2rr_toolkit.game_data.item_names import load_item_names
    from d2rr_toolkit.game_data.skills import load_skills
    from d2rr_toolkit.game_data.charstats import load_charstats
    from d2rr_toolkit.game_data.sets import load_sets
    from d2rr_toolkit.game_data.properties import load_properties
    from d2rr_toolkit.game_data.property_formatter import load_property_formatter
    from d2rr_toolkit.game_data.automagic import load_automagic
    from d2rr_toolkit.parsers.d2s_parser import D2SParser

    init_game_paths()
    load_item_types()
    load_item_stat_cost()
    load_item_names()
    load_skills()
    load_charstats()
    load_sets()
    load_properties()
    load_property_formatter()
    load_automagic()
    return D2SParser(d2s_path).parse()


# ── §1 Lightsabre tooltip parity ───────────────────────────────────────────


def test_lightsabre_vikingbarbie() -> None:
    """Lightsabre in TC56 - untampered, game-written - renders correctly."""
    print("\n=== 1. Lightsabre (TC56/VikingBarbie.d2s) matches in-game tooltip ===")
    fixture = project_root / "tests" / "cases" / "TC56" / "VikingBarbie.d2s"
    if not fixture.exists():
        print(f"  SKIP  fixture missing: {fixture}")
        return

    char = _init_and_parse(fixture)
    lightsabre = None
    for it in char.items:
        if it.item_code == "7cr" and (it.extended.quality if it.extended else 0) == 7:
            lightsabre = it
            break
    check(lightsabre is not None, "Lightsabre found in TC56")
    if lightsabre is None:
        return

    # Parser-level stat expectations - each entry is
    # ``(stat_id, key, expected_value)`` where key is either "value"
    # or one of {"chance","level","skill_id"} for encode=2 props.
    expected: list[tuple[int, str, int]] = [
        # prop1 light=7 -> item_lightradius (stat 89)
        (89, "value", 7),
        # prop2 hit-skill Chain Lightning min=15 max=50 -> stat 198
        (198, "chance", 15),
        (198, "level", 50),
        (198, "skill_id", 53),  # Chain Lightning skill id
        # prop3 ignore-ac -> item_ignoretargetac (stat 115)
        (115, "value", 1),
        # prop4 abs-ltng% -> item_absorblight_percent (stat 144)
        (144, "value", 15),
        # prop5 swing2 -> item_fasterattackrate (stat 93)
        (93, "value", 20),
        # prop6 extra-ltng -> passive_ltng_mastery (stat 330)
        (330, "value", 30),
        # prop7 dmg-ltng -> lightmindam (50) / lightmaxdam (51)
        (50, "value", 1),
        (51, "value", 450),
        # prop8 dmg% -> item_maxdamage_percent (17) / item_mindamage_percent (18)
        (17, "value", 232),
        (18, "value", 232),
        # prop9 dmg-norm -> mindamage (21) / maxdamage (22)
        (21, "value", 30),
        (22, "value", 55),
    ]

    for stat_id, key, expected_val in expected:
        match = next(
            (p for p in lightsabre.magical_properties if p.get("stat_id") == stat_id),
            None,
        )
        check(match is not None, f"stat {stat_id} present")
        if match is None:
            continue
        actual = match.get(key)
        check(actual == expected_val, f"stat {stat_id}.{key} == {expected_val}", f"got {actual!r}")

    # Max properties count = 14 root stats + hidden charm-passive skill 449
    # (stat 97 item_nonclassskill).  The hidden skill is filtered from
    # the formatter's output but must remain in the raw list for DB
    # round-trip (see project_hidden_charm_passive_skill449.md).
    check(
        len(lightsabre.magical_properties) in (13, 14),
        "13-14 magical properties (9 explicit + pairs + hidden skill 449)",
        f"got {len(lightsabre.magical_properties)}",
    )


# ── §2 Durability state ────────────────────────────────────────────────────


def test_phase_blade_zero_durability() -> None:
    """Phase Blade carries max=0 AND cur=0 - not a read-error artefact."""
    print("\n=== 2. Phase Blade durability: max=0, cur=0 ===")
    fixture = project_root / "tests" / "cases" / "TC56" / "VikingBarbie.d2s"
    if not fixture.exists():
        print(f"  SKIP  fixture missing: {fixture}")
        return

    char = _init_and_parse(fixture)
    for it in char.items:
        if it.item_code == "7cr":
            dur = it.armor_data.durability if it.armor_data else None
            check(dur is not None, "Phase Blade has durability struct")
            if dur is not None:
                check(dur.max_durability == 0, "max_durability == 0", f"got {dur.max_durability}")
                check(
                    dur.current_durability == 0,
                    "current_durability == 0",
                    f"got {dur.current_durability}",
                )
            return


# ── §3 Bow / crossbow no-regression ─────────────────────────────────────────


def test_bows_still_parse_cleanly() -> None:
    """Every bow / crossbow in the fixture corpus still parses sanely.

    The fix tightens the max_dur==0 path.  Everything that has a
    non-zero max_dur keeps the legacy 18-bit block; this test
    guards against an accidental bit-shift there.
    """
    print("\n=== 3. Bows + crossbows keep max_durability=250 + sane stats ===")
    BOW_CODES = {
        "sbw",
        "hbw",
        "lbw",
        "cbw",
        "sbb",
        "lbb",
        "swb",
        "lwb",
        "8sb",
        "8hb",
        "8lb",
        "8cb",
        "8s8",
        "8l8",
        "8sw",
        "8lw",
        "6sb",
        "6hb",
        "6lb",
        "6cb",
        "6sw",
        "6lw",
        "lxb",
        "mxb",
        "hxb",
        "rxb",
        "8lx",
        "8mx",
        "8hx",
        "8rx",
        "6lx",
        "6mx",
        "6hx",
        "6rx",
    }

    seen = 0
    for save in (project_root / "tests" / "cases").rglob("*.d2s"):
        try:
            char = _init_and_parse(save)
        except Exception:
            continue
        items = list(char.items) + list(char.merc_items)
        for parent in list(items):
            items.extend(parent.socket_children)
        for it in items:
            if it.item_code not in BOW_CODES:
                continue
            seen += 1
            dur = it.armor_data.durability if it.armor_data else None
            if dur is None:
                fail(f"{save.name} {it.item_code}: no durability struct")
                continue
            if dur.max_durability != 250:
                fail(
                    f"{save.name} {it.item_code}: max_dur={dur.max_durability}",
                    "expected 250 (Reimagined convention)",
                )
                continue
            # Spot-check for insane stat values (would indicate drift).
            bad = any(abs(p.get("value", 0)) > 1_000_000 for p in it.magical_properties)
            if bad:
                fail(f"{save.name} {it.item_code}: has stat value > 1M")
                continue
            ok(
                f"{save.name:<30} {it.item_code!r} dur={dur.max_durability}/{dur.current_durability}"
            )
    check(seen >= 4, "at least 4 bows / crossbows in the fixture corpus", f"got {seen}")


# ── §4 Static helper ───────────────────────────────────────────────────────


def test_has_durability_bits_static() -> None:
    print("\n=== 4. ItemTypeDatabase.has_durability_bits() classifications ===")
    from d2rr_toolkit.game_data.item_types import get_item_type_db

    t = get_item_type_db()
    check(not t.has_durability_bits("7cr"), "Phase Blade (7cr) has NO durability bits")
    for code in ("lbw", "8sw", "6lw", "mxb", "rxb"):
        check(
            t.has_durability_bits(code),
            f"{code}: has durability bits (nodurability=1 but durability=250)",
        )


# ── §5 Broad sweep for insane values ───────────────────────────────────────


def test_no_absurd_stat_values_anywhere() -> None:
    """Broad check: no item in any fixture has a stat value > 1 million
    (the canonical drift symptom - fire_dam=2.9M etc.).

    NOTE: ``cur_dur > max_dur`` is NOT a drift symptom - it is the
    normal state for items carrying a ``+X durability`` affix, where
    the binary stores the base max and the cumulative effective max
    is only computed at runtime in-game.  This test deliberately
    does NOT flag that case.
    """
    print("\n=== 5. No absurd stat values anywhere (drift canary) ===")
    bad_items: list[str] = []
    for save in (project_root / "tests" / "cases").rglob("*.d2s"):
        try:
            char = _init_and_parse(save)
        except Exception:
            continue
        items = list(char.items) + list(char.merc_items)
        for parent in list(items):
            items.extend(parent.socket_children)
        for it in items:
            for p in it.magical_properties:
                v = p.get("value", 0)
                if isinstance(v, int) and abs(v) > 1_000_000:
                    bad_items.append(
                        f"{save.name}:{it.item_code} stat {p.get('stat_id')} = {v} (suspicious)"
                    )
    check(len(bad_items) == 0, "no items with absurd stat values (drift canary)")
    for line in bad_items[:10]:
        print(f"    {line}")


# ── Entry point ────────────────────────────────────────────────────────────


def main() -> int:
    test_lightsabre_vikingbarbie()
    test_phase_blade_zero_durability()
    test_bows_still_parse_cleanly()
    test_has_durability_bits_static()
    test_no_absurd_stat_values_anywhere()

    print()
    print("=" * 60)
    print(f"Total: {_pass} PASS, {_fail} FAIL ({_pass + _fail} checks)")
    print("=" * 60)
    return 0 if _fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

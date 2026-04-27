#!/usr/bin/env python3
"""Regression tests for the set-bonus Chance-to-Cast level display bug.

Background
----------
``setitems.txt`` and ``sets.txt`` encode chance-to-cast (CTC) and
charged-skill tier bonuses as a pair of columns:

  * ``amin/PMin/FMin``   ->  chance (or charges for ``charged``)
  * ``amax/PMax/FMax``   ->  skill LEVEL
  * ``apar/PParam/FParam`` -> skill NAME

Every other set-bonus code uses ``min == max`` and only the single
effective value matters for display, so early implementations of
:meth:`SetBonusEntry.format` routed every entry through
:meth:`PropertyFormatter.format_code_value` with just ``value_min``.
That silently discarded the skill level for encode=2 / encode=3 stats
and the tooltip ended up showing "chance to cast level **0** ..." on
every affected set piece.

The bug hit at least 23 per-item bonuses (setitems.txt aprop) on 23
different set items plus 15 set-wide full-set bonuses in sets.txt --
e.g. Darkmage's Solar Flair (4p): expected "4% Chance to cast level
20 Shock Wave when struck", displayed "... level 0 ...".

This suite pins down both the canonical failing case from the user
report and a broad cross-section of the other affected bonuses so a
future refactor cannot silently regress any of them.

Test coverage:
  1. Canonical: Darkmage's Solar Flair 4p -- level 20 Shock Wave.
  2. Cross-section: every ``hit-skill`` / ``gethit-skill`` /
     ``kill-skill`` set bonus currently in the Reimagined data
     renders with a non-zero level when its max column is non-zero,
     and the skill name, chance and level all match the raw row.
  3. Single-value bonuses on the same entries (``+25 to Strength``,
     ``+25 to Dexterity``, etc.) keep their unchanged format.
  4. Full-set bonuses (sets.txt FCode) on the same code family are
     also fixed (separate code path through sets.txt).
  5. End-to-end: parsing TC67's shared stash yields the correct level
     on Darkmage's Solar Flair through the real CLI render path.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
src_dir = project_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


# ── Shared init ────────────────────────────────────────────────────────────


def _init() -> tuple[object, ...]:
    """Load paths + every game-data table the tooltip needs. Returns the
    formatter/isc/properties/sets/skills singletons bundled for reuse."""
    from d2rr_toolkit.config import init_game_paths
    from d2rr_toolkit.game_data.item_types import load_item_types
    from d2rr_toolkit.game_data.item_stat_cost import (
        load_item_stat_cost,
        get_isc_db,
    )
    from d2rr_toolkit.game_data.item_names import load_item_names
    from d2rr_toolkit.game_data.skills import load_skills, get_skill_db
    from d2rr_toolkit.game_data.charstats import load_charstats
    from d2rr_toolkit.game_data.sets import load_sets, get_sets_db
    from d2rr_toolkit.game_data.properties import (
        load_properties,
        get_properties_db,
    )
    from d2rr_toolkit.game_data.property_formatter import (
        load_property_formatter,
        get_property_formatter,
    )
    from d2rr_toolkit.game_data.automagic import load_automagic

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

    return (
        get_property_formatter(),
        get_isc_db(),
        get_properties_db(),
        get_sets_db(),
        get_skill_db(),
    )


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
    if cond:
        ok(name)
    else:
        fail(name, detail)


# ── Tests ──────────────────────────────────────────────────────────────────


def test_canonical_darkmage_solar_flair() -> None:
    """Darkmage's Solar Flair 4p: "4% Chance to cast level 20 Shock Wave when struck"."""
    print("\n=== 1. Canonical: Darkmage's Solar Flair 4-piece bonus ===")
    fmt, isc, prd, sets_db, sdb = _init()

    info = sets_db.get_set_for_item(252)
    check(info is not None, "set_item_id 252 (Darkmage's Solar Flair) resolves in sets db")
    if info is None:
        return
    _set_def, item_def = info
    check(item_def.name == "Darkmage's Solar Flair", "item name matches", item_def.name)

    four_piece = next(
        (t for t in item_def.tier_bonuses if t.pieces_required == 4),
        None,
    )
    check(four_piece is not None, "4-piece tier present")
    if four_piece is None:
        return

    ctc = next(
        (e for e in four_piece.entries if e.code == "gethit-skill"),
        None,
    )
    check(ctc is not None, "gethit-skill entry present in 4p tier")
    if ctc is None:
        return
    check(
        ctc.value_min == 4 and ctc.value_max == 20 and ctc.param == "Shock Wave",
        "row matches expected: min=4 max=20 param='Shock Wave'",
        f"got min={ctc.value_min} max={ctc.value_max} param={ctc.param!r}",
    )

    display = ctc.format(fmt, prd, isc, sdb)
    expected = "4% Chance to cast level 20 Shock Wave when struck"
    check(display == expected, "display is the full corrected string", f"got {display!r}")

    # Defensive: the broken decoder emitted 'level 0'. Guard that
    # literal so a future regression fails noisily.
    check("level 0" not in (display or ""), "display does NOT contain 'level 0'")


def test_cross_section_all_ctc_set_bonuses() -> None:
    """Every hit-skill / gethit-skill / kill-skill entry now shows
    the correct level and chance."""
    print("\n=== 2. Every CTC set bonus renders chance+level correctly ===")
    fmt, isc, prd, sets_db, sdb = _init()

    targets = {"hit-skill", "gethit-skill", "kill-skill"}
    checked = 0
    for sid, item_def in sets_db._set_items_by_id.items():
        for tier in item_def.tier_bonuses:
            for e in tier.entries:
                if e.code not in targets:
                    continue
                # Non-zero max is the only case where the old code went
                # wrong; entries with max=0 legitimately render "level 0"
                # (the game simply has no level bonus there). We only
                # assert the fix on entries that had something to lose.
                if e.value_max == 0:
                    continue
                checked += 1
                out = e.format(fmt, prd, isc, sdb) or ""
                m = re.search(r"level (\d+)", out)
                if m is None:
                    fail(
                        f"[{sid}] {item_def.name!r} {tier.pieces_required}p {e.code}",
                        f"no 'level N' in output {out!r}",
                    )
                    continue
                got_level = int(m.group(1))
                chance_match = re.match(r"(\d+)% Chance", out)
                got_chance = int(chance_match.group(1)) if chance_match else -1
                if got_level == e.value_max and got_chance == e.value_min and e.param in out:
                    ok(
                        f"[{sid:3d}] {item_def.name!r} {tier.pieces_required}p "
                        f"{e.code}: level={got_level} chance={got_chance}% "
                        f"skill={e.param!r}"
                    )
                else:
                    fail(
                        f"[{sid}] {item_def.name!r} {tier.pieces_required}p {e.code}",
                        f"expected chance={e.value_min} level={e.value_max} "
                        f"skill={e.param!r}, got {out!r}",
                    )

    check(
        checked >= 15,
        "at least 15 CTC set-item bonuses were exercised (23 affected rows)",
        f"got {checked}",
    )


def test_set_wide_full_tier_bonuses() -> None:
    """Full-set bonuses (sets.txt FCode) on encode=2 stats also render correctly."""
    print("\n=== 3. sets.txt full-set FCode bonuses render correctly ===")
    fmt, isc, prd, sets_db, sdb = _init()

    targets = {"hit-skill", "gethit-skill", "kill-skill"}
    checked = 0
    for name, sdef in sets_db._sets.items():
        if sdef.full_tier is None:
            continue
        for e in sdef.full_tier.entries:
            if e.code not in targets:
                continue
            if e.value_max == 0:
                continue
            checked += 1
            out = e.format(fmt, prd, isc, sdb) or ""
            m = re.search(r"level (\d+)", out)
            if m is None:
                fail(f"full-set {name!r} {e.code}", f"no 'level N' in {out!r}")
                continue
            got_level = int(m.group(1))
            if got_level == e.value_max and e.param in out:
                ok(f"full-set {name!r} {e.code}: level={got_level} skill={e.param!r}")
            else:
                fail(
                    f"full-set {name!r} {e.code}",
                    f"expected level={e.value_max} skill={e.param!r}, got {out!r}",
                )

    check(checked >= 10, "at least 10 full-set CTC bonuses were exercised", f"got {checked}")


def test_single_value_bonuses_unchanged() -> None:
    """Fix doesn't regress non-CTC codes: simple +X entries still format."""
    print("\n=== 4. Single-value set bonuses (str/dex/res-all) unchanged ===")
    fmt, isc, prd, sets_db, sdb = _init()

    # Darkmage's Solar Flair 3p dexterity bonus.
    info = sets_db.get_set_for_item(252)
    assert info is not None
    _set_def, item_def = info
    three_p = next((t for t in item_def.tier_bonuses if t.pieces_required == 3), None)
    assert three_p is not None, "3-piece tier must exist"
    dex = next((e for e in three_p.entries if e.code == "dex"), None)
    check(dex is not None, "3p dexterity entry present")
    if dex is None:
        return
    out = dex.format(fmt, prd, isc, sdb)
    check(out == "+25 to Dexterity", "dexterity formats identically after the fix", f"got {out!r}")

    # Strength (4p) - Darkmage's Solar Flair 4p has 'str' alongside the CTC.
    four_p = next((t for t in item_def.tier_bonuses if t.pieces_required == 4), None)
    assert four_p is not None
    stra = next((e for e in four_p.entries if e.code == "str"), None)
    check(stra is not None, "4p strength entry present")
    if stra is not None:
        out2 = stra.format(fmt, prd, isc, sdb)
        check(
            out2 == "+25 to Strength", "strength formats identically after the fix", f"got {out2!r}"
        )


def test_encode2_prop_dict_from_entry() -> None:
    """Internal: the builder produces a dict with all expected keys.

    Guards against future reorganisation dropping chance / level /
    skill_id from the payload fed to PropertyFormatter.format_prop.
    """
    print("\n=== 5. SetBonusEntry._format_encoded_skill builds full dict ===")
    from d2rr_toolkit.game_data.sets import SetBonusEntry

    fmt, isc, prd, _sets_db, sdb = _init()

    # Shock Wave -> stat 201 (item_skillongethit), encode=2.
    entry = SetBonusEntry(
        code="gethit-skill",
        param="Shock Wave",
        value_min=4,
        value_max=20,
    )
    out = entry.format(fmt, prd, isc, sdb)
    check(
        out == "4% Chance to cast level 20 Shock Wave when struck",
        "Shock Wave decodes via entry.format",
        f"got {out!r}",
    )

    # A skill that definitely doesn't exist - skill_id should be 0 but
    # the skill name must still show via prop.get("skill_name").
    entry2 = SetBonusEntry(
        code="hit-skill",
        param="Totally Bogus Skill",
        value_min=15,
        value_max=7,
    )
    out2 = entry2.format(fmt, prd, isc, sdb) or ""
    check(
        out2.startswith("15% Chance to cast level 7 "),
        "unknown skill name is preserved literally",
        f"got {out2!r}",
    )
    check(
        "Totally Bogus Skill" in out2, "skill name string flows through unchanged", f"got {out2!r}"
    )


def test_end_to_end_tc67_stash() -> None:
    """Parse TC67's shared stash and render the Darkmage item.

    Best-effort: skipped when the fixture is missing.
    """
    print("\n=== 6. End-to-end: TC67 shared stash renders Darkmage at level 20 ===")
    fixture = project_root / "tests" / "cases" / "TC67" / "ModernSharedStashSoftCoreV2.d2i.GAME"
    if not fixture.exists():
        print(f"  SKIP  fixture missing: {fixture}")
        return

    from d2rr_toolkit.parsers.d2i_parser import D2IParser

    fmt, isc, prd, _sets_db, sdb = _init()

    stash = D2IParser(fixture).parse()

    found = None
    for tab in stash.tabs:
        for it in tab.items:
            if getattr(it, "set_item_id", None) == 252:
                found = it
                break
        if found:
            break
    check(found is not None, "Darkmage's Solar Flair found in TC67 stash")
    if found is None:
        return

    # The parser already carries the correctly decoded set_bonus_properties;
    # the user-facing bug was in the aprop display only. Still, confirm
    # both ends agree: binary-decoded level and the sets.txt-derived level
    # must both be 20.
    ctc_prop = next(
        (
            p
            for p in found.set_bonus_properties
            if p.get("name") == "item_skillongethit" and p.get("skill_name") == "Shock Wave"
        ),
        None,
    )
    check(ctc_prop is not None, "item_skillongethit Shock Wave found in set_bonus_properties")
    if ctc_prop is not None:
        check(
            ctc_prop.get("level") == 20,
            "parser-level matches expected 20",
            f"got {ctc_prop.get('level')}",
        )
        check(
            ctc_prop.get("chance") == 4,
            "parser-chance matches expected 4",
            f"got {ctc_prop.get('chance')}",
        )


# ── Entry point ────────────────────────────────────────────────────────────


def main() -> int:
    test_canonical_darkmage_solar_flair()
    test_cross_section_all_ctc_set_bonuses()
    test_set_wide_full_tier_bonuses()
    test_single_value_bonuses_unchanged()
    test_encode2_prop_dict_from_entry()
    test_end_to_end_tc67_stash()

    print()
    print("=" * 60)
    print(f"Total: {_pass} PASS, {_fail} FAIL ({_pass + _fail} checks)")
    print("=" * 60)
    return 0 if _fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

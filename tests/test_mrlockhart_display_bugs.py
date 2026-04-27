#!/usr/bin/env python3
"""Regression suite for six tooltip-display bugs found on MrLockhart.

All six reported in user-facing testing against the live
``MrLockhart.d2s`` (Level 44 Warlock, Reimagined 3.0.7) where the
GUI tooltip diverged from the in-game display.  Fixes land in the
formatter / skills / strings layers; the tests here pin the invariant
against synthetic prop dicts so any future regression in one of the
six paths trips immediately without needing the live save.

  §1  descfunc=1 / descval=1 template prepends the signed value
      (e.g. "+1 Life Per Hit" for the ``healperhit`` template).
  §2  Damage-pair star fires ONLY when every stat in the group
      rolled at its range max (min-side 4/max=4 + max-side 7/max=8
      must NOT set ``is_perfect``).
  §3  Cold / Poison damage-pair collapses drop the length stat
      (56, 59) from the ``roll_ranges`` tuple - no orphan "[25-25]"
      third entry surfacing in the GUI.
  §4  ``Adds X-X`` collapses to ``+X`` for weapon / fire / light /
      magic damage when min and max values are equal.
  §5  SkillDatabase.name() resolves the localized tooltip label via
      skilldesc.txt + StringsDatabase - e.g. skill 383 returns
      "Levitation Mastery" rather than the internal "Levitate".
  §6  Multi-instance stat_ids (e.g. stat 107 with different skill
      params) display in REVERSE insertion order within the same
      priority tier - matching D2R's tooltip behaviour.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
src_dir = project_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

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


def _init_stack():
    os.environ["D2RR_DISABLE_GAME_DATA_CACHE"] = "1"
    from d2rr_toolkit.config import init_game_paths

    init_game_paths()
    from d2rr_toolkit.game_data.item_types import load_item_types
    from d2rr_toolkit.game_data.charstats import load_charstats
    from d2rr_toolkit.game_data.item_names import load_item_names
    from d2rr_toolkit.game_data.item_stat_cost import load_item_stat_cost
    from d2rr_toolkit.game_data.skills import load_skills
    from d2rr_toolkit.game_data.properties import load_properties
    from d2rr_toolkit.game_data.property_formatter import load_property_formatter
    from d2rr_toolkit.game_data.affix_rolls import load_affix_rolls

    load_item_types()
    load_charstats()
    load_item_names()
    load_item_stat_cost()
    load_skills()
    load_properties()
    load_property_formatter()
    load_affix_rolls()


# ── §1: descfunc=1 / descval=1 templates prepend +value ────────────────────


def test_1_descfunc_1_value_prefix() -> None:
    print("\n=== §1: +1 Life per Hit (descfunc=1 / descval=1 template) ===")
    _init_stack()
    from d2rr_toolkit.game_data.property_formatter import get_property_formatter
    from d2rr_toolkit.game_data.item_stat_cost import get_isc_db

    fmt = get_property_formatter()
    # Stat 377 = heal_afterhit (descfunc=1, descval=1, template "Life Per Hit")
    out = fmt.format_prop(
        {"stat_id": 377, "value": 1, "param": 0},
        get_isc_db(),
    )
    check(
        out == "+1 Life Per Hit",
        "formatted output = '+1 Life Per Hit'",
        f"got {out!r}",
    )


# ── §2: damage-pair star requires both halves at max ──────────────────────


def test_2_damage_pair_joint_perfection() -> None:
    print("\n=== §2: Damage-pair star only on joint perfection ===")
    _init_stack()
    from d2rr_toolkit.game_data.property_formatter import (
        get_property_formatter,
        ItemRollContext,
    )
    from d2rr_toolkit.game_data.item_stat_cost import get_isc_db
    from d2rr_toolkit.game_data.properties import get_properties_db
    from d2rr_toolkit.game_data.skills import get_skill_db
    from d2rr_toolkit.game_data.item_types import get_item_type_db

    fmt = get_property_formatter()

    # "Static Grand Charm of Flame" - fire damage with 4 (at max of
    # [2,4]) and 7 (NOT at max of [6,8]).  The line must NOT show
    # ``is_perfect`` because only one half is perfect.
    class _F:
        ethereal = False
        runeword = False

    class _E:
        pass

    class _It:
        item_code = "cm3"
        flags = _F()
        extended = _E()
        magical_properties = [
            {"stat_id": 48, "value": 4, "param": 0},
            {"stat_id": 49, "value": 7, "param": 0},
        ]

    it = _It()
    # Construct a context that resolves the ranges we need - pass
    # the magicsuffix row that actually gives fire-min 2-4 + fire-max
    # 6-8.  The MrLockhart static-flame suffix_id is 704.
    ctx = ItemRollContext(quality=4, suffix_ids=(704,))
    out = fmt.format_properties_grouped(
        it.magical_properties,
        get_isc_db(),
        get_skill_db(),
        roll_context=ctx,
        props_db=get_properties_db(),
        breakdown=True,
        item=it,
        item_types_db=get_item_type_db(),
    )
    fire_line = next((fp for fp in out if 48 in fp.source_stat_ids), None)
    check(fire_line is not None, "fire-damage line produced")
    if fire_line is not None:
        check(
            not fire_line.is_perfect,
            "is_perfect False when max-side rolled below ceiling",
            f"got is_perfect={fire_line.is_perfect}",
        )


# ── §3: length stats dropped from damage-pair roll_ranges ─────────────────


def test_3_length_stats_not_in_damage_ranges() -> None:
    print("\n=== §3: Cold/Poison length stat excluded from roll_ranges ===")
    _init_stack()
    from d2rr_toolkit.game_data.property_formatter import (
        get_property_formatter,
        ItemRollContext,
    )
    from d2rr_toolkit.game_data.item_stat_cost import get_isc_db
    from d2rr_toolkit.game_data.properties import get_properties_db
    from d2rr_toolkit.game_data.skills import get_skill_db

    fmt = get_property_formatter()
    # Small Charm of Frost - stats 54/55/56 with a matching suffix.
    props = [
        {"stat_id": 54, "value": 1, "param": 0},
        {"stat_id": 55, "value": 2, "param": 0},
        {"stat_id": 56, "value": 25, "param": 0},
    ]
    # suffix 629 ("of Frost") rolls cold min/max/length.
    ctx = ItemRollContext(quality=4, suffix_ids=(629,))
    out = fmt.format_properties_grouped(
        props,
        get_isc_db(),
        get_skill_db(),
        roll_context=ctx,
        props_db=get_properties_db(),
    )
    cold_line = next((fp for fp in out if 54 in fp.source_stat_ids), None)
    check(cold_line is not None, "cold-damage line produced")
    if cold_line is not None:
        check(
            len(cold_line.roll_ranges) == 2,
            "roll_ranges has length 2 (min, max - no length)",
            f"got {len(cold_line.roll_ranges)} entries",
        )


# ── §4: Adds X-X collapses to +X ──────────────────────────────────────────


def test_4_damage_min_max_collapse() -> None:
    print("\n=== §4: Adds X-X damage collapses to +X when min==max ===")
    _init_stack()
    from d2rr_toolkit.game_data.property_formatter import get_property_formatter
    from d2rr_toolkit.game_data.item_stat_cost import get_isc_db
    from d2rr_toolkit.game_data.skills import get_skill_db

    fmt = get_property_formatter()
    for stat_min, stat_max, expect in [
        (50, 51, "+1 Weapon Lightning Damage"),  # ltng 1-1
        (48, 49, "+3 Weapon Fire Damage"),  # fire 3-3
        (52, 53, "+4 Weapon Magic Damage"),  # magic 4-4
        (21, 22, "+5 Weapon Damage"),  # physical 5-5
    ]:
        val = int(expect.split()[0].lstrip("+"))
        props = [
            {"stat_id": stat_min, "value": val, "param": 0},
            {"stat_id": stat_max, "value": val, "param": 0},
        ]
        out = fmt.format_properties_grouped(props, get_isc_db(), get_skill_db())
        line = next((fp for fp in out if stat_min in fp.source_stat_ids), None)
        check(
            line is not None and line.plain_text == expect,
            f"collapse {stat_min}/{stat_max} val={val} -> {expect!r}",
            f"got {line.plain_text if line else None!r}",
        )

    # Non-matching values keep the "Adds X-Y" form
    props = [
        {"stat_id": 48, "value": 3, "param": 0},
        {"stat_id": 49, "value": 5, "param": 0},
    ]
    out = fmt.format_properties_grouped(props, get_isc_db(), get_skill_db())
    line = next((fp for fp in out if 48 in fp.source_stat_ids), None)
    check(
        line is not None and line.plain_text == "Adds 3-5 Weapon Fire Damage",
        "no collapse when min != max",
        f"got {line.plain_text if line else None!r}",
    )


# ── §5: skill display names via skilldesc.txt + strings ───────────────────


def test_5_skill_display_name_resolution() -> None:
    print("\n=== §5: skill display name via skilldesc + strings table ===")
    _init_stack()
    from d2rr_toolkit.game_data.skills import get_skill_db

    sdb = get_skill_db()
    # Skill 383 = internal "Levitate" -> display "Levitation Mastery"
    check(
        sdb.name(383) == "Levitation Mastery",
        "skill 383 -> 'Levitation Mastery'",
        f"got {sdb.name(383)!r}",
    )
    # Vanilla skills still resolve to their classic names
    check(
        sdb.name(53) == "Chain Lightning",
        "skill 53 -> 'Chain Lightning'",
    )
    check(
        sdb.name(54) == "Teleport",
        "skill 54 -> 'Teleport'",
    )
    # id_by_name still looks up the INTERNAL name (affix resolver
    # depends on this for slot.par matching).
    check(
        sdb.id_by_name("Levitate") == 383,
        "id_by_name('Levitate') still returns 383 (internal name)",
        f"got {sdb.id_by_name('Levitate')!r}",
    )


# ── §6: multi-instance stat order reversed within priority tier ──────────


def test_6_multi_instance_stat_reverse_order() -> None:
    print("\n=== §6: multi-instance stat_id reverse insertion order ===")
    _init_stack()
    from d2rr_toolkit.game_data.property_formatter import get_property_formatter
    from d2rr_toolkit.game_data.item_stat_cost import get_isc_db
    from d2rr_toolkit.game_data.skills import get_skill_db

    fmt = get_property_formatter()
    # Binary stores stat 107 twice with two different skill params.
    # MrLockhart's Vicious Dagger of Maiming: Summon Goatman (373)
    # then Demonic Mastery (374).  D2R renders the LATER prop first.
    props = [
        {"stat_id": 17, "value": 35, "param": 0},
        {"stat_id": 18, "value": 35, "param": 0},
        {"stat_id": 22, "value": 6, "param": 0},
        {"stat_id": 97, "value": 1, "param": 449},  # hidden charm passive
        {"stat_id": 107, "value": 1, "param": 373},  # Summon Goatman
        {"stat_id": 107, "value": 2, "param": 374},  # Demonic Mastery
    ]
    out = fmt.format_properties_grouped(props, get_isc_db(), get_skill_db())
    # Locate the two +skill lines and verify Demonic Mastery comes
    # before Summon Goatman in output order.
    skill_lines = [
        i
        for i, fp in enumerate(out)
        if any(
            s in ("Summon Goatman", "Demonic Mastery")
            for s in [fp.plain_text.split(" to ", 1)[-1].split(" (", 1)[0]]
        )
    ]
    demonic_idx = next(
        (i for i, fp in enumerate(out) if "Demonic Mastery" in fp.plain_text),
        None,
    )
    goatman_idx = next(
        (i for i, fp in enumerate(out) if "Summon Goatman" in fp.plain_text),
        None,
    )
    check(
        demonic_idx is not None and goatman_idx is not None,
        "both skill lines produced",
    )
    if demonic_idx is not None and goatman_idx is not None:
        check(
            demonic_idx < goatman_idx,
            "Demonic Mastery appears BEFORE Summon Goatman",
            f"got demonic@{demonic_idx}, goatman@{goatman_idx}",
        )


# ── §7: multi-stat breakdown.is_perfect_roll reflects joint perfection ──
# Even with stat 54 at its max (1 of [1,1]), a cold damage pair that
# rolled max-side 1 of [1,5] is NOT perfect.  The per-line
# ``FormattedProperty.is_perfect`` correctly returns False; this test
# on top, this pins that ``fp.breakdown.is_perfect_roll`` tracks the
# joint (line-level) flag on multi-stat display lines so GUI
# renderers that read from the breakdown directly see the same
# answer as ``fp.is_perfect``.


def test_7_breakdown_joint_perfection_on_multi_stat_line() -> None:
    print("\n=== §7: breakdown.is_perfect_roll is joint on multi-stat lines ===")
    _init_stack()
    from d2rr_toolkit.game_data.property_formatter import (
        get_property_formatter,
        ItemRollContext,
    )
    from d2rr_toolkit.game_data.item_stat_cost import get_isc_db
    from d2rr_toolkit.game_data.properties import get_properties_db
    from d2rr_toolkit.game_data.skills import get_skill_db
    from d2rr_toolkit.game_data.item_types import get_item_type_db

    fmt = get_property_formatter()

    # "Inspiring Small Charm of Frost" - cold damage (54=1, 55=1)
    # with suffix 629 that rolls [1,1] on min and [1,5] on max.
    # Stat 54 hits max (1/1) but stat 55 didn't (1/5).  Joint =>
    # NOT perfect.
    class _F:
        ethereal = False
        runeword = False

    class _E:
        pass

    class _It:
        item_code = "cm1"
        flags = _F()
        extended = _E()
        magical_properties = [
            {"stat_id": 54, "value": 1, "param": 0},
            {"stat_id": 55, "value": 1, "param": 0},
            {"stat_id": 56, "value": 25, "param": 0},
        ]

    it = _It()
    ctx = ItemRollContext(quality=4, prefix_ids=(797,), suffix_ids=(629,))
    out = fmt.format_properties_grouped(
        it.magical_properties,
        get_isc_db(),
        get_skill_db(),
        roll_context=ctx,
        props_db=get_properties_db(),
        breakdown=True,
        item=it,
        item_types_db=get_item_type_db(),
    )
    cold_line = next((fp for fp in out if 54 in fp.source_stat_ids), None)
    check(cold_line is not None, "cold damage line produced")
    if cold_line is None:
        return
    check(
        cold_line.is_perfect is False,
        "fp.is_perfect is False (max-side below ceiling)",
    )
    check(
        cold_line.breakdown is not None,
        "breakdown attached for the cold damage line",
    )
    if cold_line.breakdown is not None:
        check(
            cold_line.breakdown.is_perfect_roll is False,
            "breakdown.is_perfect_roll is False on multi-stat line (joint value, not just stat 54)",
            f"got {cold_line.breakdown.is_perfect_roll}",
        )


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass

    test_1_descfunc_1_value_prefix()
    test_2_damage_pair_joint_perfection()
    test_3_length_stats_not_in_damage_ranges()
    test_4_damage_min_max_collapse()
    test_5_skill_display_name_resolution()
    test_6_multi_instance_stat_reverse_order()
    test_7_breakdown_joint_perfection_on_multi_stat_line()
    test_8_cache_enabled_skill_display_name()


def test_8_cache_enabled_skill_display_name() -> None:
    """Reconfirm the Levitation Mastery fix survives the persistent
    pickle cache (the user's GUI sees stale "Levitate" when the
    cache carries a pre-fix item_names / skills pickle).  Bumping
    ``SCHEMA_VERSION_ITEM_NAMES`` + ``SCHEMA_VERSION_SKILLS`` drops
    the old payloads on the first load after the fix.
    """
    print("\n=== §8: cache-enabled skill display name still resolves ===")
    # Unlike the other tests this one does NOT set
    # D2RR_DISABLE_GAME_DATA_CACHE - it exercises the cache path
    # directly so a future schema-version regression (e.g. adding
    # a new field without bumping the version) is caught.
    os.environ.pop("D2RR_DISABLE_GAME_DATA_CACHE", None)
    from d2rr_toolkit.config import init_game_paths

    init_game_paths()
    # Clear module-level singletons so this test sees a fresh load
    # path even if other tests already touched the DBs.
    from d2rr_toolkit.game_data import skills as skills_mod
    from d2rr_toolkit.game_data import item_names as names_mod

    skills_mod._SKILL_DB.__init__()
    names_mod._ITEM_NAMES_DB.__init__()
    from d2rr_toolkit.game_data.item_names import load_item_names
    from d2rr_toolkit.game_data.skills import load_skills, get_skill_db

    load_item_names()
    load_skills()
    check(
        get_skill_db().name(383) == "Levitation Mastery",
        "cache-enabled load resolves skill 383 -> 'Levitation Mastery'",
        f"got {get_skill_db().name(383)!r}",
    )

    print()
    print("=" * 60)
    print(f"Total: {_pass} PASS, {_fail} FAIL ({_pass + _fail} checks)")
    print("=" * 60)
    return 0 if _fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

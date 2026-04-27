#!/usr/bin/env python3
"""Regression test for the has_gfx=1 charm prefix/suffix decoding bug.

For a historical window, every Magic-quality charm (cm1/cm2/cm3) with
``has_gfx=1`` and automod present parsed with its prefix/suffix IDs
bumped by one row.  In VikingBarbie's personal stash this surfaced as
"Amber Grand Charm of Balance" (range 26-30) showing a rolled
Lightning Resistance of 25 - below the range minimum, an impossible
combination.  The actual prefix in-game is "Coral" (range 21-25),
confirmed visually.

Root cause: D2R packs the 12-bit affix index across two fields.  The
low 10 bits sit in the 11-bit ``prefix_id`` slot; the 12th bit (LSB of
``prefix_id + 1``) is carried in whichever field precedes ``prefix_id``
in the bit stream.  For jewels / rings / amulets that skip the
11-bit ``automod`` read, the carry lives in ``has_class``.  For items
that DO read automod (charms, tools, orbs, bf1=True weapons+armor
with ``has_class=1``), the automod read itself stores
``[10-bit real automod, 1-bit prefix carry]`` - the MSB of the
11-bit read is the carry, and the bottom 10 bits are the real automod.

The pre-fix parser unconditionally used ``has_class`` as the carry.
For charms where the carry is really in the automod MSB, this
produced `prefix_id + (1 if has_class else 0)` worth of off-by-one
errors that only surfaced when the adjacent rows rolled their stats
into overlapping ranges (so players rarely noticed - but the
roll-range tooltips always did).

The fix:

  * ``automod_id`` is masked to its low 10 bits on read.
  * The MSB is preserved as ``prefix_carry_from_automod``.
  * The Magic / Set / Unique / Rare affix-ID formulas prefer that
    carry bit when an automod read was performed; they fall back to
    ``has_class`` otherwise (unchanged behaviour for jewels).

This test pins the fix by asserting that every cm1/cm2/cm3 charm in
the TC72 fixture resolves to a prefix whose stat-1 range CONTAINS the
rolled stat value (i.e. the "Coral" sanity check used by the GUI).
Additional hand-verified spot checks anchor the specific Grand
Charms flagged during diagnosis.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
src_dir = project_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

TC72 = project_root / "tests" / "cases" / "TC72" / "VikingBarbie.d2s"

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

    load_item_types()
    load_charstats()
    load_item_names()
    load_item_stat_cost()
    load_skills()
    load_properties()


def _load_magicprefix_rows():
    from d2rr_toolkit.adapters.casc import read_game_data_rows

    return read_game_data_rows("data:data/global/excel/magicprefix.txt")


def _load_magicsuffix_rows():
    from d2rr_toolkit.adapters.casc import read_game_data_rows

    return read_game_data_rows("data:data/global/excel/magicsuffix.txt")


def _stat_ids_for(code: str) -> list[int]:
    """Expand a property code to the ISC stat ids its mod1 touches.

    Broadcasts (``all-stats``, ``res-all``, ...) return ALL expanded
    stats so a charm value that falls within range on any of them
    counts as a match - mirrors the D2 engine's own semantics.
    """
    from d2rr_toolkit.game_data.properties import get_properties_db
    from d2rr_toolkit.game_data.item_stat_cost import get_isc_db

    pd = get_properties_db().get(code)
    if pd is None:
        return []
    out: list[int] = []
    for name in pd.stat_names():
        if not name:
            continue
        sd = get_isc_db().get_by_name(name)
        if sd is not None:
            out.append(sd.stat_id)
    return out


def test_every_charm_prefix_range_contains_its_stat() -> None:
    """For every cm*/charm in the fixture, the resolved prefix_id's
    mod1 range must contain the value of the matching stat."""
    print("\n=== TC72: VikingBarbie charm prefix ranges contain stat values ===")
    _init_stack()
    mp = _load_magicprefix_rows()
    ms = _load_magicsuffix_rows()

    from d2rr_toolkit.parsers.d2s_parser import D2SParser

    ch = D2SParser(TC72).parse()

    # Build a quick lookup: for each charm, does prefix_id's mod1
    # range contain a matching rolled stat value, OR is the stat
    # contribution split across prefix+suffix (in which case we can
    # only check the combined stat lies within combined bounds)?
    problems: list[str] = []
    verified = 0
    for it in ch.items:
        code = getattr(it, "item_code", "")
        if code not in ("cm1", "cm2", "cm3"):
            continue
        pid = it.prefix_id
        if pid is None or pid <= 0:
            continue
        row = mp[pid] if 0 < pid < len(mp) else None
        if row is None:
            continue
        pcode = row.get("mod1code") or ""
        if not pcode:
            continue
        stats = _stat_ids_for(pcode)
        if not stats:
            continue
        pmin = int(row.get("mod1min") or 0)
        pmax = int(row.get("mod1max") or 0)

        # Total stat contribution (prefix + optional same-stat suffix)
        sid = it.suffix_id or 0
        srow = ms[sid] if 0 < sid < len(ms) else None
        s_adds_same = False
        smin = smax = 0
        if srow and srow.get("mod1code") == pcode:
            s_adds_same = True
            smin = int(srow.get("mod1min") or 0)
            smax = int(srow.get("mod1max") or 0)

        combined_min = pmin + (smin if s_adds_same else 0)
        combined_max = pmax + (smax if s_adds_same else 0)

        for prop in it.magical_properties or []:
            psid = prop.get("stat_id")
            pval = prop.get("value")
            if psid not in stats or pval is None:
                continue
            if not (combined_min <= pval <= combined_max):
                pname = (row.get("name") or "").strip()
                problems.append(
                    f"{code} pref={pid} '{pname}' {pcode}: "
                    f"value {pval} outside [{combined_min}, {combined_max}] "
                    f"(prefix [{pmin},{pmax}]"
                    + (f" + suffix [{smin},{smax}]" if s_adds_same else "")
                    + ")"
                )
            verified += 1
            break

    check(
        len(problems) == 0,
        f"all {verified} charm prefix ranges contain their stat values",
        "; ".join(problems[:5]),
    )


def test_viking_grand_charm_spot_checks() -> None:
    """Hand-verified Grand Charms from the VikingBarbie fixture."""
    print("\n=== TC72: Hand-verified Grand Charm prefix IDs ===")
    _init_stack()
    mp = _load_magicprefix_rows()
    ms = _load_magicsuffix_rows()

    from d2rr_toolkit.parsers.d2s_parser import D2SParser

    ch = D2SParser(TC72).parse()

    def find_grand_charms_by_stat(stat_id: int, value: int) -> list:
        return [
            it
            for it in ch.items
            if getattr(it, "item_code", "") == "cm3"
            and any(
                p.get("stat_id") == stat_id and p.get("value") == value
                for p in (it.magical_properties or [])
            )
        ]

    # Coral Grand Charm of Balance: stat 41 lightresist, value 25,
    # suffix 741 "of Balance"
    corals_bal = [it for it in find_grand_charms_by_stat(41, 25) if it.suffix_id == 741]
    check(
        len(corals_bal) >= 1,
        "found 'Coral Grand Charm of Balance' (lightres 25 + suffix 741)",
    )
    if corals_bal:
        it = corals_bal[0]
        pname = (mp[it.prefix_id].get("name") or "").strip()
        check(
            pname == "Coral",
            f"prefix name is 'Coral' (got '{pname}', row {it.prefix_id})",
        )
        check(
            it.prefix_id == 1003,
            f"prefix_id == 1003 (got {it.prefix_id})",
        )

    # Garnet Grand Charm of Dexterity: stat 39 fireres, value 22
    garnets = [
        it for it in find_grand_charms_by_stat(39, 22) if it.suffix_id == 736 and it.prefix_id
    ]
    if garnets:
        it = garnets[0]
        pname = (mp[it.prefix_id].get("name") or "").strip()
        check(
            pname == "Garnet",
            f"'Garnet Grand Charm of Dexterity' resolves to Garnet (got '{pname}')",
        )

    # Cobalt Grand Charm (no suffix): stat 43 coldres, value 25
    cobalts = [
        it for it in find_grand_charms_by_stat(43, 25) if (it.suffix_id or 0) == 0 and it.prefix_id
    ]
    if cobalts:
        it = cobalts[0]
        pname = (mp[it.prefix_id].get("name") or "").strip()
        check(
            pname == "Cobalt",
            f"'Cobalt Grand Charm' resolves to Cobalt (got '{pname}')",
        )


def test_automod_id_masked_to_10_bits() -> None:
    """Automod IDs must fall within automagic.txt row count (~71)."""
    print("\n=== TC72: Automod IDs stay within automagic.txt bounds ===")
    _init_stack()

    from d2rr_toolkit.adapters.casc import read_game_data_rows

    automagic_rows = read_game_data_rows("data:data/global/excel/automagic.txt")
    n_automagic = len(automagic_rows)

    from d2rr_toolkit.parsers.d2s_parser import D2SParser

    ch = D2SParser(TC72).parse()

    violations = []
    for it in ch.items:
        if getattr(it, "item_code", "") not in ("cm1", "cm2", "cm3"):
            continue
        aid = it.automod_id
        if aid is None or aid == 0:
            continue
        if aid >= n_automagic:
            violations.append(f"{it.item_code} automod_id={aid} (table size {n_automagic})")
    check(
        len(violations) == 0,
        f"all charm automod_ids within automagic.txt bounds (0..{n_automagic - 1})",
        "; ".join(violations[:5]),
    )


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass

    test_every_charm_prefix_range_contains_its_stat()
    test_viking_grand_charm_spot_checks()
    test_automod_id_masked_to_10_bits()

    print()
    print("=" * 60)
    print(f"Total: {_pass} PASS, {_fail} FAIL ({_pass + _fail} checks)")
    print("=" * 60)
    return 0 if _fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

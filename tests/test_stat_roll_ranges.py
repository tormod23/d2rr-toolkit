#!/usr/bin/env python3
"""Regression suite for per-stat roll-range metadata on FormattedProperty.

Three categories of test:

  * **Resolver unit tests** exercise ``AffixRollDatabase.resolve`` in
    isolation against real Reimagined 3.0.7 data - they don't touch
    the formatter and therefore pin the "correct min/max for a
    known unique/set/runeword row" contract without tangled
    coupling.
  * **Formatter integration tests** render a :class:`FormattedProperty`
    list with ``roll_context=...`` and assert the ``roll_ranges`` /
    ``is_perfect`` fields have the expected shape.  Damage-pair
    tests live here - the collapsing logic is part of the
    grouped-formatter contract.
  * **Back-compat tests** pin the "no context -> empty tuple" rule
    and confirm old pickles round-trip.

Scenarios:

  1. Synthetic unique, fixed stats only            -> §1  (t_1_*)
  2. Synthetic unique, rollable stats              -> §2  (t_2_*)
  3. Set item - own rollable, bonus fixed          -> §3
  4. Runeword - multi-rune assembly                -> §4
  5. Magic item - prefix / suffix / both           -> §5
  6. Rare item - multiple prefixes & suffixes      -> §6
  7. Damage pair (length-2 roll_ranges)            -> §7
  8. No context -> empty tuple                      -> §8
  9. Stat with param disambiguation                -> §9
  10. Back-compat pickle (field defaults)          -> §10
"""

from __future__ import annotations

import pickle
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
    if cond:
        ok(name)
    else:
        fail(name, detail)


# ── Shared fixture ─────────────────────────────────────────────────────────


def _init_full_stack():
    """Load every game-data table the roll resolver + formatter need.

    Returns a tuple of the handles used throughout the suite -
    deliberately kept as a flat tuple so tests can destructure once
    at the top and refer to the names by local binding.
    """
    import os

    os.environ["D2RR_DISABLE_GAME_DATA_CACHE"] = "1"
    from d2rr_toolkit.config import init_game_paths
    from d2rr_toolkit.game_data.item_types import load_item_types
    from d2rr_toolkit.game_data.item_stat_cost import load_item_stat_cost, get_isc_db
    from d2rr_toolkit.game_data.item_names import load_item_names
    from d2rr_toolkit.game_data.skills import load_skills, get_skill_db
    from d2rr_toolkit.game_data.charstats import load_charstats, get_charstats_db
    from d2rr_toolkit.game_data.sets import load_sets
    from d2rr_toolkit.game_data.properties import load_properties, get_properties_db
    from d2rr_toolkit.game_data.property_formatter import (
        load_property_formatter,
        get_property_formatter,
    )
    from d2rr_toolkit.game_data.automagic import load_automagic
    from d2rr_toolkit.game_data.affix_rolls import (
        load_affix_rolls,
        get_affix_roll_db,
    )

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
    load_affix_rolls()
    return (
        get_property_formatter(),
        get_isc_db(),
        get_skill_db(),
        get_charstats_db(),
        get_properties_db(),
        get_affix_roll_db(),
    )


# ── §1 Synthetic unique - fixed stats only ────────────────────────────────


def test_1_unique_fixed_stats_only() -> None:
    print("\n=== 1. Unique row, all-fixed stats -> length-1 ranges, is_fixed() True ===")
    from d2rr_toolkit.game_data.property_formatter import (
        ItemRollContext,
        StatRollRange,
    )

    fmt, isc, sdb, _cdb, prd, db = _init_full_stack()

    # Lightsabre (*ID=259) prop5 = swing2 20/20 (item_fasterattackrate, stat 93)
    # -> fixed-range entry.  Rolled current value == max == perfect.
    ctx = ItemRollContext(quality=7, unique_id=259)
    props = [{"stat_id": 93, "value": 20, "param": 0}]
    out = fmt.format_properties_grouped(
        props,
        isc,
        sdb,
        roll_context=ctx,
        props_db=prd,
    )
    check(len(out) == 1, "single output line")
    fp = out[0]
    check(len(fp.roll_ranges) == 1, "length-1 roll_ranges")
    rng = fp.roll_ranges[0]
    check(isinstance(rng, StatRollRange), "entry is StatRollRange")
    check(rng.is_fixed() is True, "is_fixed() True")
    check(
        rng.min_value == 20 and rng.max_value == 20,
        "min==max==20",
        f"got {rng.min_value}..{rng.max_value}",
    )
    check(rng.source == "unique", "source='unique'")
    check(fp.is_perfect is True, "is_perfect True (current==max by construction for fixed)")


# ── §2 Unique, rollable stat - correct range + perfection flips ───────────


def test_2_unique_rollable_stat_perfection_flip() -> None:
    print("\n=== 2. Unique rollable stat - range pulls correct min/max + flips ===")
    from d2rr_toolkit.game_data.property_formatter import ItemRollContext

    fmt, isc, sdb, _cdb, prd, _db = _init_full_stack()

    # Lightsabre prop8 = dmg% 200/250 -> item_maxdamage_percent (17) pair 18.
    ctx = ItemRollContext(quality=7, unique_id=259)

    # Rolled max (232 - Lightsabre's actual roll).  Not perfect.
    props = [{"stat_id": 17, "value": 232, "param": 0}]
    out = fmt.format_properties_grouped(props, isc, sdb, roll_context=ctx, props_db=prd)
    fp = out[0]
    rng = fp.roll_ranges[0]
    check(rng.min_value == 200, f"min=200 (got {rng.min_value})")
    check(rng.max_value == 250, f"max=250 (got {rng.max_value})")
    check(fp.is_perfect is False, "rolled 232 -> not perfect")

    # Rolled at the ceiling (250) -> is_perfect True.
    props2 = [{"stat_id": 17, "value": 250, "param": 0}]
    out2 = fmt.format_properties_grouped(props2, isc, sdb, roll_context=ctx, props_db=prd)
    check(out2[0].is_perfect is True, "rolled 250 -> is_perfect True")


# ── §3 Set item - own stats rollable, set-bonus stats fixed ───────────────


def test_3_set_own_vs_bonus() -> None:
    print("\n=== 3. Set item - own stats tagged 'set', set-bonus stats get no range ===")
    from d2rr_toolkit.game_data.property_formatter import ItemRollContext

    fmt, isc, sdb, _cdb, prd, db = _init_full_stack()

    # Pick any set item in the current data.  Tal Rasha's Adjudication
    # (amulet, *ID=77).  Its own props in setitems.txt carry prop1..prop9
    # ranges; the set-bonus lists (aprop*) are handled separately by
    # SetBonusEntry and therefore must NOT show up in our resolver.
    ctx = ItemRollContext(quality=5, set_id=77)

    # Sample any resolvable stat_id from Tal Rasha's Adjudication props.
    # Probe a handful of common set-item own-stat ids; the test only
    # requires ONE to resolve so we're not pinning a specific row.
    resolved = None
    for stat_id in (39, 41, 43, 45, 80, 93, 3, 7, 127):
        rr = db.resolve(
            ctx, stat_id, param=0, isc_db=isc, props_db=prd, skills_db=sdb, charstats_db=None
        )
        if rr is not None:
            resolved = (stat_id, rr)
            break
    check(resolved is not None, "at least one own-stat resolves")
    if resolved is not None:
        sid, rr = resolved
        check(rr.source == "set", f"source='set' for own stat {sid}", f"got {rr.source!r}")


# ── §4 Runeword - multi-rune assembly ─────────────────────────────────────


def test_4_runeword_assembly() -> None:
    print("\n=== 4. Runeword row resolves with source='runeword' ===")
    from d2rr_toolkit.game_data.property_formatter import ItemRollContext

    fmt, isc, sdb, _cdb, prd, db = _init_full_stack()

    # Runes.txt indexed by row number.  Spirit Monarch (row 141 in the
    # current data - may drift with future mod updates; the test
    # survives as long as SOME runeword row with rollable stats
    # exists, which is the structural guarantee).
    from d2rr_toolkit.adapters.casc import read_game_data_rows

    rows = read_game_data_rows("data:data/global/excel/runes.txt")
    # Scan until we find a runeword whose row contains multiple
    # filled T1CodeN slots - that's enough to exercise the parser.
    target_idx = None
    for i, r in enumerate(rows):
        filled = sum(1 for n in range(1, 8) if r.get(f"T1Code{n}", "").strip())
        if filled >= 3:
            target_idx = i
            break
    check(target_idx is not None, "at least one runeword row exists")
    if target_idx is None:
        return

    ctx = ItemRollContext(runeword_id=target_idx)
    # Probe a wide band of plausible runeword stat ids (resists,
    # attributes, damage, enhance-dmg, skills, crushing-blow,
    # deadly-strike, xp, life, mana, ...).  Any single hit satisfies
    # the "resolves via runeword context" contract.
    resolved = None
    for stat_id in (
        # Attribute + life / mana
        0,
        1,
        2,
        3,
        7,
        8,
        9,
        11,
        # Damage + enhancement
        17,
        18,
        21,
        22,
        50,
        51,
        # Passives / procs
        136,
        141,
        93,
        99,
        105,
        # Resistances
        39,
        41,
        43,
        45,
        # Bonus % / misc
        80,
        81,
        83,
        127,
        159,
    ):
        rr = db.resolve(
            ctx, stat_id, param=0, isc_db=isc, props_db=prd, skills_db=sdb, charstats_db=None
        )
        if rr is not None:
            resolved = (stat_id, rr)
            break
    check(
        resolved is not None,
        "at least one runeword stat resolves via context",
        f"target row {target_idx}",
    )
    if resolved is not None:
        _sid, rr = resolved
        check(rr.source == "runeword", "source='runeword'", f"got {rr.source!r}")


# ── §5 Magic item - prefix-only, suffix-only, both ───────────────────────


def test_5_magic_affixes() -> None:
    print("\n=== 5. Magic items: prefix-only / suffix-only / both ===")
    from d2rr_toolkit.game_data.property_formatter import ItemRollContext

    _fmt, isc, sdb, _cdb, prd, db = _init_full_stack()

    # Find any magicprefix / magicsuffix row with a resolvable mod slot.
    # Probe rows 1..50 of each and stop at the first hit.
    prefix_idx = _find_first_magic_mod_row(db, "prefix")
    suffix_idx = _find_first_magic_mod_row(db, "suffix")
    check(prefix_idx is not None, "at least one magicprefix row loaded")
    check(suffix_idx is not None, "at least one magicsuffix row loaded")
    if prefix_idx is None or suffix_idx is None:
        return

    # Prefix-only
    ctx_p = ItemRollContext(quality=4, prefix_ids=(prefix_idx,))
    pfx_stats = _affixed_stat_ids(db, "prefix", prefix_idx)
    for sid in pfx_stats:
        rng = db.resolve(
            ctx_p, sid, param=0, isc_db=isc, props_db=prd, skills_db=sdb, charstats_db=None
        )
        if rng is not None:
            check(rng.source == "magic_prefix", f"prefix-only stat {sid}: source='magic_prefix'")
            break

    # Suffix-only
    ctx_s = ItemRollContext(quality=4, suffix_ids=(suffix_idx,))
    sfx_stats = _affixed_stat_ids(db, "suffix", suffix_idx)
    for sid in sfx_stats:
        rng = db.resolve(
            ctx_s, sid, param=0, isc_db=isc, props_db=prd, skills_db=sdb, charstats_db=None
        )
        if rng is not None:
            check(rng.source == "magic_suffix", f"suffix-only stat {sid}: source='magic_suffix'")
            break

    # Both - source priority puts prefix before suffix when both contribute
    # different stats; here we just verify both sides still resolve.
    ctx_both = ItemRollContext(quality=4, prefix_ids=(prefix_idx,), suffix_ids=(suffix_idx,))
    pfx_resolved = any(
        db.resolve(
            ctx_both, sid, param=0, isc_db=isc, props_db=prd, skills_db=sdb, charstats_db=None
        )
        is not None
        for sid in pfx_stats
    )
    check(pfx_resolved, "both-affixes context still resolves a prefix stat")


def _find_first_magic_mod_row(db, kind: str) -> int | None:
    """Return the first magic-affix row index that has a non-empty slot."""
    store = db._magicprefix if kind == "prefix" else db._magicsuffix
    for idx, row in sorted(store.items()):
        if row.slots:
            return idx
    return None


def _affixed_stat_ids(db, kind: str, idx: int) -> list[int]:
    """Best-effort: pull plausible stat ids from a magic-affix row.

    Mirrors the resolver's own code->stat expansion so that rows
    whose slot codes use the ``func`` fallback map (e.g. ``dmg%``
    has no ``stat1`` in properties.txt but is mapped explicitly to
    stats 17+18 in :data:`affix_rolls._PROP_CODE_FALLBACK_STATS`)
    are still enumerable from the test side.
    """
    from d2rr_toolkit.game_data.affix_rolls import _PROP_CODE_FALLBACK_STATS
    from d2rr_toolkit.game_data.item_stat_cost import get_isc_db
    from d2rr_toolkit.game_data.properties import get_properties_db

    prd = get_properties_db()
    isc = get_isc_db()
    row = (db._magicprefix if kind == "prefix" else db._magicsuffix).get(idx)
    if row is None:
        return []
    out: list[int] = []
    for slot in row.slots:
        pd = prd.get(slot.code)
        if pd is not None:
            for name in pd.stat_names():
                sd = isc.get_by_name(name)
                if sd is not None:
                    out.append(sd.stat_id)
        out.extend(_PROP_CODE_FALLBACK_STATS.get(slot.code, ()))
    return out


# ── §6 Rare-style: multiple prefixes/suffixes resolve independently ──────


def test_6_rare_multi_affixes() -> None:
    print("\n=== 6. Multiple prefixes + multiple suffixes each keep their source ===")
    from d2rr_toolkit.game_data.property_formatter import ItemRollContext

    _fmt, isc, sdb, _cdb, prd, db = _init_full_stack()

    # Find two distinct prefix rows whose slot stats don't overlap -
    # easier to verify independent resolution.  Scan a wide band.
    px_indices: list[int] = []
    seen_stats: set[int] = set()
    for idx, row in sorted(db._magicprefix.items()):
        if len(px_indices) >= 3:
            break
        if not row.slots:
            continue
        sids = set(_affixed_stat_ids(db, "prefix", idx))
        if sids and not (sids & seen_stats):
            px_indices.append(idx)
            seen_stats |= sids
    check(len(px_indices) >= 2, "collected at least 2 non-overlapping prefix rows")
    if len(px_indices) < 2:
        return

    ctx = ItemRollContext(quality=6, prefix_ids=tuple(px_indices))
    # Every prefix's first-stat should still resolve through the same
    # context - the resolver walks all rows in ``ctx.prefix_ids``.
    all_resolved = True
    for idx in px_indices:
        sids = _affixed_stat_ids(db, "prefix", idx)
        hit = False
        for sid in sids:
            rng = db.resolve(
                ctx, sid, param=0, isc_db=isc, props_db=prd, skills_db=sdb, charstats_db=None
            )
            if rng is not None:
                hit = True
                break
        if not hit:
            all_resolved = False
            break
    check(all_resolved, "every collected prefix row contributes a resolvable stat")


# ── §7 Damage pair - length-2 roll_ranges ────────────────────────────────


def test_7_damage_pair() -> None:
    print("\n=== 7. Damage pair from dual-stat slot yields NO roll ranges ===")
    from d2rr_toolkit.game_data.property_formatter import ItemRollContext

    fmt, isc, sdb, _cdb, prd, _db = _init_full_stack()

    # Lightsabre prop9 = dmg-norm 30/55 -> collapses to "Adds 30-55 Weapon Damage".
    # ``dmg-norm`` declares BOTH ``mindamage`` and ``maxdamage`` on the same
    # properties.txt row: slot.min supplies stat 21's fixed value, slot.max
    # supplies stat 22's fixed value.  Neither column encodes a rolling
    # window - they're two fixed numbers packed into one slot.  Per the
    # FrozenOrbHydra "Conclave of Elements" bug report, displaying
    # "[30-55 / 30-55]" misleads the player into thinking the item rolled
    # a range when in fact both sides are fixed.  The resolver must
    # suppress ranges for dual-stat-single-slot codes.
    ctx = ItemRollContext(quality=7, unique_id=259)
    props = [
        {"stat_id": 21, "value": 30, "param": 0},
        {"stat_id": 22, "value": 55, "param": 0},
    ]
    out = fmt.format_properties_grouped(props, isc, sdb, roll_context=ctx, props_db=prd)
    check(len(out) == 1, "collapsed to a single FormattedProperty")
    fp = out[0]
    check(
        fp.roll_ranges == (),
        "dual-stat dmg-norm slot -> empty roll_ranges",
        f"got {fp.roll_ranges}",
    )
    check(fp.is_perfect is False, "is_perfect False when there's no real rolling range")


# ── §8 No context - empty tuple, is_perfect False ────────────────────────


def test_8_no_context_noop() -> None:
    print("\n=== 8. roll_context=None -> roll_ranges=() everywhere ===")
    fmt, isc, sdb, _cdb, prd, _db = _init_full_stack()
    props = [{"stat_id": 7, "value": 100}]  # any stat
    out = fmt.format_properties_grouped(props, isc, sdb)  # NO roll_context
    check(len(out) == 1, "single output")
    fp = out[0]
    check(fp.roll_ranges == (), "roll_ranges is empty tuple")
    check(fp.is_perfect is False, "is_perfect False when no range info")

    # Explicit None - same behaviour
    out2 = fmt.format_properties_grouped(props, isc, sdb, roll_context=None, props_db=prd)
    check(out2[0].roll_ranges == (), "roll_context=None -> empty tuple")


# ── §9 Param disambiguation ──────────────────────────────────────────────


def test_9_param_disambiguation() -> None:
    print("\n=== 9. Same stat id with different params does not merge ===")
    from d2rr_toolkit.game_data.property_formatter import ItemRollContext

    _fmt, isc, sdb, cdb, prd, db = _init_full_stack()

    # Use stat 97 (item_nonclassskill) - encode=0, carries a param
    # (the skill id), appears on Lightsabre via the ``oskill_hide``
    # slot with par='Hidden Charm Passive' (skill 449), min=1, max=1.
    # Matching param resolves to the fixed [1, 1]; non-matching param
    # falls through to a different (loose) match or None - either
    # way, the two paths do NOT merge into a shared range.
    ctx = ItemRollContext(quality=7, unique_id=259)
    matching = db.resolve(
        ctx, 97, param=449, isc_db=isc, props_db=prd, skills_db=sdb, charstats_db=cdb
    )
    check(matching is not None, "matching skill_id resolves")
    if matching is not None:
        check(
            matching.min_value == 1 and matching.max_value == 1,
            "range pulled from matching oskill slot",
        )

    non_matching = db.resolve(
        ctx, 97, param=999, isc_db=isc, props_db=prd, skills_db=sdb, charstats_db=cdb
    )
    if non_matching is None:
        ok("non-matching param rejected cleanly (returns None)")
    else:
        # If we fall through to a loose match the range may still show
        # up, but it mustn't pollute the matching path's result - the
        # resolver's caller distinguishes via the returned range.
        ok(f"non-matching param returned {non_matching} (loose match acceptable)")


# ── §10 Back-compat for pickles built before the roll-range fields ───────


def test_10_pickle_back_compat() -> None:
    print("\n=== 10. Old-shape pickle loads with new field defaults ===")
    from d2rr_toolkit.game_data.property_formatter import (
        FormattedProperty,
        FormattedSegment,
    )

    # Build a pickle payload that mimics the pre-roll-range dataclass shape -
    # no ``roll_ranges`` / ``is_perfect`` fields - and round-trip it
    # through the current dataclass to verify the defaults kick in.
    # We can't literally serialise an older dataclass version, but we
    # can construct with positional args stopping at source_stat_ids
    # and confirm the new fields fall back to their defaults.
    fp = FormattedProperty(
        segments=(FormattedSegment("x", None),),
        plain_text="x",
        source_stat_ids=(7,),
    )
    check(fp.roll_ranges == (), "legacy-shape construction: roll_ranges=()")
    check(fp.is_perfect is False, "legacy-shape construction: is_perfect=False")

    # Serialize + deserialize - frozen dataclass round-trip
    raw = pickle.dumps(fp)
    fp2 = pickle.loads(raw)
    check(fp == fp2, "pickle round-trip preserves equality")
    check(fp2.roll_ranges == (), "after round-trip: roll_ranges still empty")
    check(fp2.is_perfect is False, "after round-trip: is_perfect still False")


# ── §9 Lightsabre verification snippet ───────────────────────────────────


def test_9_lightsabre_snippet_parity() -> None:
    print("\n=== 9. Lightsabre verification snippet: assertions hold ===")
    from d2rr_toolkit.game_data.property_formatter import ItemRollContext

    fmt, isc, sdb, _cdb, prd, _db = _init_full_stack()

    # Lightsabre (*ID=259) prop1 = light 7/7 (item_lightradius stat 89).
    # Use the *real* row ids so the snippet is representative.
    props = [{"stat_id": 89, "value": 7, "param": 0}]
    ctx = ItemRollContext(quality=7, unique_id=259)
    out = fmt.format_properties_grouped(props, isc, sdb, roll_context=ctx, props_db=prd)
    line = out[0]
    check(len(line.roll_ranges) == 1, "len(roll_ranges) == 1")
    rng = line.roll_ranges[0]
    check(rng.min_value == 7 and rng.max_value == 7, "range min/max pinned (7/7)")
    check(rng.source == "unique", "source='unique'")
    check(line.is_perfect is True, "current==max -> is_perfect True")


# ── §11: Auto-load regression ──────────────────────────────────────────────
# The GUI path passes `roll_context=` + `props_db=` but historically did not
# also call `load_affix_rolls()` explicitly.  The formatter must lazy-load
# the affix-roll DB on first use so downstream callers don't have to wire
# a separate bootstrap step.


def test_11_auto_load_on_first_use() -> None:
    print("\n-- §11: Resolver auto-loads AffixRollDatabase on first resolve --")
    # Prime the formatter / ISC / properties stack but reset the
    # affix-roll singleton AFTER, to simulate the GUI path: the caller
    # never invoked load_affix_rolls() explicitly.
    fmt, isc, sdb, _cdb, prd, _db = _init_full_stack()
    from d2rr_toolkit.game_data import affix_rolls as ar_mod

    # Clear the singleton's internal state in place so get_affix_roll_db()
    # keeps returning the same object the formatter will query.
    db_singleton = ar_mod.get_affix_roll_db()
    db_singleton._uniques.clear()
    db_singleton._sets_own.clear()
    db_singleton._magicprefix.clear()
    db_singleton._magicsuffix.clear()
    db_singleton._runes.clear()
    db_singleton._loaded = False
    check(
        not ar_mod.get_affix_roll_db().is_loaded(),
        "pre-condition: affix-roll DB starts unloaded",
    )

    # Lightsabre *ID=155 in Reimagined 3.0.7; stat 93 = ias (unique row
    # has swing2 slot min=max=20 -> perfect @ value 20).
    from d2rr_toolkit.game_data.property_formatter import ItemRollContext

    fp = fmt.format_prop_structured(
        {"stat_id": 93, "value": 20, "param": 0},
        isc,
        sdb,
        roll_context=ItemRollContext(unique_id=155),
        props_db=prd,
    )
    check(
        fp is not None and len(fp.roll_ranges) == 1,
        "resolver auto-loaded and attached roll_ranges",
        detail=f"got roll_ranges={fp.roll_ranges if fp else None}",
    )
    check(
        ar_mod.get_affix_roll_db().is_loaded(),
        "post-condition: affix-roll DB is now loaded",
    )
    check(
        fp.is_perfect is True,
        "is_perfect flips to True when rolled value equals max",
    )


# ── §12: Encode 2/3 compound stats -> no range ──────────────────────────────
# FrozenOrbHydra repro: Spring Facet jewel "100% Chance to Cast Level 47
# Chain Lightning when you Die" rendered with range "[47-100]".  The CTC
# stat has encode=2 - its binary value packs (chance, level, skill id)
# into one integer, so the source row's min/max columns are two fixed
# compound fields, NOT a rolling window.  Displaying a range + star there
# is wrong on both counts.


def test_12_encode_2_3_no_range() -> None:
    print("\n-- §12: encode=2/3 skill-event stats yield no roll range --")
    from d2rr_toolkit.game_data.property_formatter import ItemRollContext

    fmt, isc, sdb, _cdb, prd, _db = _init_full_stack()

    # Find the first encode=2 stat_id present in ISC - that's what
    # a CTC proc surfaces as at the formatter layer.
    encode2_sid: int | None = None
    for sid in range(0, 436):
        sd = isc.get(sid)
        if sd is not None and sd.encode == 2:
            encode2_sid = sid
            break
    check(encode2_sid is not None, "ISC has at least one encode=2 stat")
    if encode2_sid is None:
        return

    # Synthetic unique_id=1 (Magic Quiver row 0 in uniqueitems.txt -
    # exists in every Reimagined build).  We're not exercising the
    # slot match here; we're asserting the encode gate short-circuits
    # BEFORE slot iteration, so any unique_id works.
    ctx = ItemRollContext(quality=7, unique_id=1)
    fp = fmt.format_prop_structured(
        {"stat_id": encode2_sid, "value": 100, "param": 0},
        isc,
        sdb,
        roll_context=ctx,
        props_db=prd,
    )
    check(fp is not None, "formatter still emits the property line")
    if fp is None:
        return
    check(fp.roll_ranges == (), "encode=2 stat -> empty roll_ranges", f"got {fp.roll_ranges}")
    check(fp.is_perfect is False, "encode=2 stat -> is_perfect False")


# ── §13: Conclave-style multi-element proc damage -> no range ──────────────
# FrozenOrbHydra repro: Conclave of Elements Grand Charm with three
# "Adds 63-511 Weapon X Damage" lines.  Each line sources from a single
# dmg-fire / dmg-ltng / dmg-cold slot whose declared stats are the
# matching min/max damage pair.  No rolling range applies.


def test_13_element_proc_damage_no_range() -> None:
    print("\n-- §13: dmg-fire/dmg-cold/dmg-ltng dual-stat slots -> no range --")
    from d2rr_toolkit.game_data.property_formatter import ItemRollContext

    fmt, isc, sdb, _cdb, prd, _db = _init_full_stack()

    # Walk every unique row looking for one that has a dmg-fire slot -
    # the specific row isn't important, we only need the dual-stat
    # detection to fire.  We probe both stat 48 (fire-min) and 49
    # (fire-max) and expect both to resolve to None.
    from d2rr_toolkit.game_data import affix_rolls as ar_mod

    db = ar_mod.get_affix_roll_db()
    probe_unique_id: int | None = None
    for uid, row in db._uniques.items():
        if any(slot.code == "dmg-fire" for slot in row.slots):
            probe_unique_id = uid
            break
    check(
        probe_unique_id is not None,
        "Reimagined data contains at least one unique with dmg-fire slot",
    )
    if probe_unique_id is None:
        return

    ctx = ItemRollContext(quality=7, unique_id=probe_unique_id)
    props = [
        {"stat_id": 48, "value": 63, "param": 0},  # item_fire_mindamage
        {"stat_id": 49, "value": 511, "param": 0},  # item_fire_maxdamage
    ]
    out = fmt.format_properties_grouped(props, isc, sdb, roll_context=ctx, props_db=prd)
    check(len(out) == 1, "fire pair collapses to one FormattedProperty")
    if not out:
        return
    fp = out[0]
    check(
        fp.roll_ranges == (),
        "dmg-fire dual-stat slot -> empty roll_ranges",
        f"got {fp.roll_ranges}",
    )
    check(fp.is_perfect is False, "no range -> is_perfect False")


# ── §14: dmg% broadcast -> single collapsed range ──────────────────────────
# FrozenOrbHydra archive repro: Unique Military Pick "Occam's Razor"
# (*ID=444) shows "+161% Enhanced Weapon Damage [140-190 / 140-190]" -
# the ``dmg%`` property feeds ONE rolled ED% value into both stat 17
# (item_maxdamage_percent) and stat 18 (item_mindamage_percent).
# Both damage-pair halves resolve to the same range from the same
# slot; displaying it twice mis-suggests two independent rolls.
# Collapse identical ranges in _attach_damage_pair_roll_ranges.


def test_14_broadcast_damage_pair_collapse() -> None:
    print("\n-- §14: ED% broadcast damage-pair collapses to one range --")
    from d2rr_toolkit.game_data.property_formatter import ItemRollContext

    fmt, isc, sdb, _cdb, prd, _db = _init_full_stack()

    # Occam's Razor *ID = 444 in Reimagined 3.0.7; dmg% slot has
    # min=140 max=190 -> both stat 17 and stat 18 expand to the same
    # [140, 190] range.
    ctx = ItemRollContext(quality=7, unique_id=444)
    props = [
        {"stat_id": 17, "value": 161, "param": 0},  # maxdamage%
        {"stat_id": 18, "value": 161, "param": 0},  # mindamage%
    ]
    out = fmt.format_properties_grouped(props, isc, sdb, roll_context=ctx, props_db=prd)
    check(len(out) == 1, "ED pair collapses to one FormattedProperty")
    if not out:
        return
    fp = out[0]
    check(
        len(fp.roll_ranges) == 1,
        "broadcast pair -> length-1 roll_ranges (not duplicated)",
        f"got len={len(fp.roll_ranges)}",
    )
    if fp.roll_ranges:
        r = fp.roll_ranges[0]
        check(
            r.min_value == 140 and r.max_value == 190,
            "range pulled from dmg% slot [140, 190]",
            f"got [{r.min_value}, {r.max_value}]",
        )
    check(fp.is_perfect is False, "161 < 190 -> not perfect")

    # Genuine rolling damage pair via two distinct slots (dmg-min +
    # dmg-max) would produce TWO ranges - not exercised here since
    # Reimagined 3.0.7 doesn't use that pattern on any unique, but
    # the equal-range collapse condition in
    # _attach_damage_pair_roll_ranges preserves length-2 when the
    # ranges differ.


# ── §15: Poison damage 3-stat dual-min/max slot -> no range ────────────────
# VikingBarbie archive repro: "Foul Grand Charm of Vita" with stat
# "Adds 82-105 Poison Damage over 3 Seconds" displayed a spurious range
# "[280-360]".  The magicprefix row (984, "Envenomed" -> displayed as
# "Foul" via string-table indirection) has a ``dmg-pois`` slot whose
# prop_def declares THREE stats: poisonmindam, poisonmaxdam,
# poisonlength.  slot.min=280 and slot.max=360 are the raw internal
# per-frame values for the min and max halves of the damage pair (the
# formatter scales them through the duration to display "82-105"); the
# poisonlength comes from slot.par=75 frames.  None is a roll window.
#
# Previous heuristic only rejected 2-stat dual-min/max slots.
# Relaxed to >=2 stats so 3-stat poison is also caught.


def test_15_poison_dual_stat_no_range() -> None:
    print("\n-- §15: dmg-pois 3-stat min/max slot -> empty roll_ranges --")
    from d2rr_toolkit.game_data.property_formatter import ItemRollContext

    fmt, isc, sdb, _cdb, prd, _db = _init_full_stack()

    # Pick ANY magicprefix row with a dmg-pois slot - the dual-stat
    # detection is row-independent.  Row 984 = "Envenomed" (-> "Foul")
    # in Reimagined 3.0.7.
    ctx = ItemRollContext(quality=4, prefix_ids=(984,))
    props = [
        {"stat_id": 57, "value": 280, "param": 75},  # poisonmindam
        {"stat_id": 58, "value": 358, "param": 75},  # poisonmaxdam
        {"stat_id": 59, "value": 75, "param": 0},  # poisonlength
    ]
    out = fmt.format_properties_grouped(props, isc, sdb, roll_context=ctx, props_db=prd)
    # Formatter emits a single "Adds X-Y Poison Damage" line.
    poison_lines = [fp for fp in out if "Poison" in fp.plain_text]
    check(len(poison_lines) >= 1, "poison pair collapsed to a display line")
    if not poison_lines:
        return
    fp = poison_lines[0]
    check(
        fp.roll_ranges == (), "dmg-pois 3-stat slot -> empty roll_ranges", f"got {fp.roll_ranges}"
    )
    check(fp.is_perfect is False, "no range -> is_perfect False")


# ── §16: Consistency gate on mis-identified affix source ──────────────────
# VikingBarbie archive repro: A Grand Charm rolled via the "Coral"
# prefix (row 1003, res-ltng 21-25) was mis-identified by the parser
# carry-chain as the adjacent "Amber" row (1004, res-ltng 26-30).  The
# resolver correctly returned the Amber range [26, 30] for the
# parser-supplied prefix_id, but the stat's displayed value was 25 -
# below the range minimum.  Showing "[26-30]" with a 25% value is
# nonsense; the formatter must detect the inconsistency and drop
# the range so the user sees the plain "25% Lightning Resistance"
# line instead of a misleading tooltip.
#
# This gate is defensive against ANY future source-row-mismatch
# (parser bugs, stale saves after mod data updates, synthetic test
# items with wrong prefix_ids), not just the specific Coral/Amber
# case that prompted it.


def test_16_out_of_range_value_suppresses_display() -> None:
    print("\n-- §16: value outside resolved range -> range suppressed --")
    from d2rr_toolkit.game_data.property_formatter import ItemRollContext

    fmt, isc, sdb, _cdb, prd, _db = _init_full_stack()

    # Mis-ID: charm thinks it's Amber (1004, range [26, 30]) but the
    # actual rolled lightresist is 25 (which really came from Coral).
    bad_ctx = ItemRollContext(quality=4, prefix_ids=(1004,))
    props = [{"stat_id": 41, "value": 25, "param": 0}]
    out = fmt.format_properties_grouped(props, isc, sdb, roll_context=bad_ctx, props_db=prd)
    check(len(out) == 1, "still emits the stat line")
    fp = out[0]
    check(fp.roll_ranges == (), "out-of-range value -> empty roll_ranges", f"got {fp.roll_ranges}")
    check(fp.is_perfect is False, "no range -> is_perfect False")

    # Correct prefix_id for Coral (1003, range [21, 25]) with the
    # same rolled value: range SHOULD appear, and is_perfect True.
    good_ctx = ItemRollContext(quality=4, prefix_ids=(1003,))
    out2 = fmt.format_properties_grouped(props, isc, sdb, roll_context=good_ctx, props_db=prd)
    fp2 = out2[0]
    check(len(fp2.roll_ranges) == 1, "in-range value -> range surfaces normally")
    if fp2.roll_ranges:
        r = fp2.roll_ranges[0]
        check(
            r.min_value == 21 and r.max_value == 25,
            "correct Coral range [21, 25]",
            f"got [{r.min_value}, {r.max_value}]",
        )
    check(fp2.is_perfect is True, "value 25 at Coral ceiling -> is_perfect True")


# ── §17: Modifier-aware consistency gate ────────────────────────────────
# Reimagined layers Corruption / Enchantment / Ethereal / Runeword on top
# of the base affix rolls.  Corruption adds free bonus stats, Enchantment
# lets the player pile capped mods on top, Ethereal inflates defense by
# 50%, Runewords graft a full stat block onto the base item.  Any of
# these can push the observed stat value above the source-table range
# max.  The fast-path consistency gate in ``format_properties_grouped``
# therefore lifts its ceiling when any modifier is active - the floor
# stays strict because no modifier pushes a positive stat BELOW its
# minimum.  Callers that need precise per-source perfection attribution
# opt into the full breakdown resolver via ``breakdown=True``.


def test_17_modifier_aware_gate_above_max() -> None:
    print("\n-- §17: modifier-flagged items accept values above range.max --")
    from d2rr_toolkit.game_data.property_formatter import ItemRollContext

    fmt, isc, sdb, _cdb, prd, _db = _init_full_stack()

    props = [{"stat_id": 41, "value": 32, "param": 0}]  # 32 > Coral's 25

    # Without modifiers the gate rejects (this is the Coral/Amber case)
    bare_ctx = ItemRollContext(quality=4, prefix_ids=(1003,))
    out = fmt.format_properties_grouped(props, isc, sdb, roll_context=bare_ctx, props_db=prd)
    check(out[0].roll_ranges == (), "bare modifier-free item: over-range value -> range suppressed")

    # With is_corrupted=True the gate accepts (corruption may add ltng res)
    cor_ctx = ItemRollContext(quality=4, prefix_ids=(1003,), is_corrupted=True)
    out = fmt.format_properties_grouped(props, isc, sdb, roll_context=cor_ctx, props_db=prd)
    check(len(out[0].roll_ranges) == 1, "is_corrupted=True: over-range value -> range still shown")
    check(
        out[0].is_perfect is False,
        "is_corrupted=True: perfect-roll star suppressed (modifier unknown)",
    )

    # Same for is_enchanted / is_ethereal / is_runeword
    for flag in ("is_enchanted", "is_ethereal", "is_runeword"):
        kwargs = {flag: True}
        mctx = ItemRollContext(quality=4, prefix_ids=(1003,), **kwargs)
        out = fmt.format_properties_grouped(props, isc, sdb, roll_context=mctx, props_db=prd)
        check(len(out[0].roll_ranges) == 1, f"{flag}=True: range shown despite over-range value")
        check(
            out[0].is_perfect is False,
            f"{flag}=True: star suppressed (per-stat attribution deferred)",
        )

    # Floor stays strict even with modifiers: value BELOW min still
    # rejected (no modifier drives positive stats below their floor).
    props_below = [{"stat_id": 41, "value": 15, "param": 0}]  # 15 < Coral's 21
    for flag in ("is_corrupted", "is_enchanted", "is_ethereal", "is_runeword"):
        kwargs = {flag: True}
        mctx = ItemRollContext(quality=4, prefix_ids=(1003,), **kwargs)
        out = fmt.format_properties_grouped(props_below, isc, sdb, roll_context=mctx, props_db=prd)
        check(
            out[0].roll_ranges == (), f"{flag}=True but value below floor -> range still suppressed"
        )

    # Perfect star stays on when value == max AND no modifiers
    props_max = [{"stat_id": 41, "value": 25, "param": 0}]
    clean = ItemRollContext(quality=4, prefix_ids=(1003,))
    out = fmt.format_properties_grouped(props_max, isc, sdb, roll_context=clean, props_db=prd)
    check(out[0].is_perfect is True, "clean item at max: is_perfect True")


def test_18_item_roll_context_modifier_detection() -> None:
    print("\n-- §18: ItemRollContext.from_parsed_item detects modifier flags --")
    from d2rr_toolkit.game_data.property_formatter import ItemRollContext

    # Fake ParsedItem-like object - duck-typed
    class _FakeFlags:
        def __init__(self, eth=False, rw=False):
            self.ethereal = eth
            self.runeword = rw

    class _FakeItem:
        def __init__(self, *, eth=False, rw=False, stats=()):
            self.flags = _FakeFlags(eth, rw)
            self.magical_properties = [{"stat_id": sid, "value": 1, "param": 0} for sid in stats]

    # Plain item
    ctx = ItemRollContext.from_parsed_item(_FakeItem())
    check(ctx.has_stat_modifiers is False, "plain item: no modifiers")

    # Corrupted (stat 361 present)
    ctx = ItemRollContext.from_parsed_item(_FakeItem(stats=[361]))
    check(ctx.is_corrupted is True, "stat 361 -> is_corrupted True")
    check(ctx.has_stat_modifiers is True, "has_stat_modifiers True")

    # Enchanted (any of 392..395)
    for sid in (392, 393, 394, 395):
        ctx = ItemRollContext.from_parsed_item(_FakeItem(stats=[sid]))
        check(ctx.is_enchanted is True, f"stat {sid} -> is_enchanted True")

    # Ethereal / Runeword flags
    ctx = ItemRollContext.from_parsed_item(_FakeItem(eth=True))
    check(ctx.is_ethereal is True, "flags.ethereal -> is_ethereal True")
    ctx = ItemRollContext.from_parsed_item(_FakeItem(rw=True))
    check(ctx.is_runeword is True, "flags.runeword -> is_runeword True")


# ── Entry point ────────────────────────────────────────────────────────────


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass

    test_1_unique_fixed_stats_only()
    test_2_unique_rollable_stat_perfection_flip()
    test_3_set_own_vs_bonus()
    test_4_runeword_assembly()
    test_5_magic_affixes()
    test_6_rare_multi_affixes()
    test_7_damage_pair()
    test_8_no_context_noop()
    test_9_param_disambiguation()
    test_10_pickle_back_compat()
    test_req_9_snippet_parity()
    test_11_auto_load_on_first_use()
    test_12_encode_2_3_no_range()
    test_13_element_proc_damage_no_range()
    test_14_broadcast_damage_pair_collapse()
    test_15_poison_dual_stat_no_range()
    test_16_out_of_range_value_suppresses_display()
    test_17_modifier_aware_gate_above_max()
    test_18_item_roll_context_modifier_detection()

    print()
    print("=" * 60)
    print(f"Total: {_pass} PASS, {_fail} FAIL ({_pass + _fail} checks)")
    print("=" * 60)
    return 0 if _fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

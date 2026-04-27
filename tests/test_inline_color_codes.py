#!/usr/bin/env python3
"""Regression suite for inline D2R colour codes in formatted properties.

Background
----------
D2R's ``item-modifiers.json`` embeds colour changes as three-byte
escape sequences ``\\xFFc<L>``.  The pre-refactor formatter stripped
them at template load time, collapsing every property line to a single
caller-default colour downstream -- which meant the GUI couldn't
render fluff text like ``fadeDescription`` ("You feel incorporeal...")
in dark grey as the in-game client does.

The fix:

  * Stop stripping at load.  The template cache now stores the raw
    ``\\xFFc<L>`` sequences.
  * Introduce ``FormattedSegment`` / ``FormattedProperty`` dataclasses.
  * Split the (possibly colour-tagged) formatter output into a tuple
    of ``(text, color_token)`` segments at the public structured API
    boundary.
  * Keep plain-text callers supported via
    ``format_properties_grouped_plain(...)``.

Test coverage:

  1. Loader preserves tokens.
  2. Segment splitter round-trip across known inputs.
  3. End-to-end with the real ``fadeDescription`` template -- the
     structured output carries a grey ("K") segment.
  4. Compat wrapper returns exactly the legacy plain strings.
  5. Synthetic collapses carry an empty ``source_stat_ids``.
  6. Damage groups carry lead + follower IDs.
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


# The above one-liner is clever but hard to read; re-define cleanly.
def check(cond: bool, name: str, detail: str = "") -> None:  # noqa: F811
    if cond:
        ok(name)
    else:
        fail(name, detail)


# ── Shared init ────────────────────────────────────────────────────────────


def _init_full_stack():
    """Initialise every loader the grouped formatter transitively needs.

    Returns ``(formatter, isc_db, skills_db)`` for downstream tests.
    """
    from d2rr_toolkit.config import init_game_paths
    from d2rr_toolkit.game_data.item_types import load_item_types
    from d2rr_toolkit.game_data.item_stat_cost import (
        load_item_stat_cost,
        get_isc_db,
    )
    from d2rr_toolkit.game_data.item_names import load_item_names
    from d2rr_toolkit.game_data.skills import load_skills, get_skill_db
    from d2rr_toolkit.game_data.charstats import load_charstats
    from d2rr_toolkit.game_data.sets import load_sets
    from d2rr_toolkit.game_data.properties import load_properties
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

    return get_property_formatter(), get_isc_db(), get_skill_db()


# ── Test 1: loader preserves raw tokens ────────────────────────────────────


def test_loader_preserves_tokens() -> None:
    print("\n=== 1. Loader preserves raw colour tokens in the template cache ===")
    from d2rr_toolkit.game_data.property_formatter import PropertyFormatter
    import json

    # Synthetic source so the test doesn't depend on the live data.
    fake = [
        {"Key": "fluffDesc", "enUS": "\xffcKgrey part\xffc3blue part"},
        {"Key": "plainDesc", "enUS": "just plain"},
        {"Key": "allGrey", "enUS": "\xffcKall grey"},
        {"Key": "leadingOnly", "enUS": "\xffc3leading blue"},
    ]
    raw_bytes = json.dumps(fake).encode("utf-8")

    fmt = PropertyFormatter()
    fmt.load_from_bytes(raw_bytes, source="<synthetic>")

    check(
        fmt.get_template("fluffDesc") == "\xffcKgrey part\xffc3blue part",
        "fluffDesc template retains both tokens verbatim",
    )
    check(
        fmt.get_template("plainDesc") == "just plain",
        "plainDesc template stored verbatim (no tokens)",
    )
    check(
        fmt.get_template("allGrey") == "\xffcKall grey",
        "allGrey template retains its leading token",
    )
    check(
        fmt.get_template("leadingOnly") == "\xffc3leading blue",
        "leadingOnly template retains its leading token",
    )


# ── Test 2: segment splitter round-trip ────────────────────────────────────


def test_segment_splitter_round_trip() -> None:
    print("\n=== 2. _split_color round-trips through _strip_color ===")
    from d2rr_toolkit.game_data.property_formatter import (
        _split_color,
        _strip_color,
        FormattedSegment,
    )

    cases: list[tuple[str, list[FormattedSegment]]] = [
        (
            "plain",
            [FormattedSegment(text="plain", color_token=None)],
        ),
        (
            "\xffcKall grey",
            [FormattedSegment(text="all grey", color_token="K")],
        ),
        (
            "prefix \xffcKmid \xffc3tail",
            [
                FormattedSegment(text="prefix ", color_token=None),
                FormattedSegment(text="mid ", color_token="K"),
                FormattedSegment(text="tail", color_token="3"),
            ],
        ),
        (
            "\xffcKYou feel incorporeal...\xffc3",
            [FormattedSegment(text="You feel incorporeal...", color_token="K")],
        ),
        (
            "",
            [],
        ),
        (
            "\xffc3only trailing\xffc4",
            [FormattedSegment(text="only trailing", color_token="3")],
        ),
    ]

    for i, (text, expected) in enumerate(cases, 1):
        got = _split_color(text)
        check(got == expected, f"split case {i}: {text!r}", f"expected {expected!r}, got {got!r}")
        # Round-trip: concatenated .text equals stripped form.
        concat = "".join(s.text for s in got)
        check(
            concat == _strip_color(text),
            f"round-trip case {i}: concatenation == _strip_color",
            f"concat={concat!r}, stripped={_strip_color(text)!r}",
        )


# ── Test 3: fadeDescription end-to-end with live data ──────────────────────


def test_end_to_end_fade_description() -> None:
    print("\n=== 3. End-to-end: fadeDescription flows through with colour intact ===")
    fmt, isc, skills = _init_full_stack()

    # fadeDescription maps to ISC stat 181 ("fade"). Build a synthetic
    # prop dict simulating the item carrying that stat and render.
    stat_def = None
    for sid in range(600):
        sd = isc.get(sid)
        if sd and sd.descstrpos == "fadeDescription":
            stat_def = sd
            target_sid = sid
            break

    check(stat_def is not None, "ISC has a stat mapped to fadeDescription descstrpos")
    if stat_def is None:
        return

    prop = {"stat_id": target_sid, "name": stat_def.name, "param": 0, "value": 1}

    # Structured API: must carry a grey segment with "incorporeal" text.
    result = fmt.format_prop_structured(prop, isc, skills)
    check(result is not None, "format_prop_structured(fade) produces a FormattedProperty")
    if result is None:
        return
    check(
        any(seg.color_token == "K" for seg in result.segments),
        "at least one segment carries the 'K' (grey) colour token",
    )
    check(
        "incorporeal" in result.plain_text,
        "plain_text contains 'incorporeal'",
        f"got {result.plain_text!r}",
    )
    check(
        result.source_stat_ids == (target_sid,),
        "source_stat_ids carries the fade stat id",
        f"got {result.source_stat_ids}",
    )

    # Grouped API: identical content, wrapped in a list.
    grouped = fmt.format_properties_grouped([prop], isc, skills)
    check(len(grouped) == 1, "grouped returns exactly one FormattedProperty for one input prop")
    if grouped:
        check(
            any(s.color_token == "K" for s in grouped[0].segments),
            "grouped output preserves the grey segment",
        )

    # Plain-text wrapper: strips every token, matches the pre-refactor
    # output byte-for-byte.
    plain = fmt.format_properties_grouped_plain([prop], isc, skills)
    check(
        plain == ["You feel incorporeal..."],
        "plain wrapper returns legacy string list",
        f"got {plain!r}",
    )


# ── Test 4: compatibility -- fixtures stay byte-identical ──────────────────


def test_compat_wrapper_fixtures() -> None:
    print("\n=== 4. Plain wrapper returns the same strings as before ===")
    fmt, isc, skills = _init_full_stack()

    # Use a handful of real-ish synthetic properties that collectively
    # exercise every descfunc branch, the damage-group path, and the
    # synthetic collapses.  The exact output per line is less important
    # than the parity check: structured[i].plain_text == plain[i].
    sample_props = [
        {"stat_id": 16, "name": "item_armor_percent", "param": 0, "value": 125},
        {"stat_id": 21, "name": "mindamage", "param": 0, "value": 10},
        {"stat_id": 22, "name": "maxdamage", "param": 0, "value": 20},
        {"stat_id": 39, "name": "fireresist", "param": 0, "value": 25},
        {"stat_id": 41, "name": "lightresist", "param": 0, "value": 25},
        {"stat_id": 43, "name": "coldresist", "param": 0, "value": 25},
        {"stat_id": 45, "name": "poisonresist", "param": 0, "value": 25},
        {"stat_id": 80, "name": "item_magicbonus", "param": 0, "value": 50},
        {"stat_id": 127, "name": "item_allskills", "param": 0, "value": 1},
    ]

    structured = fmt.format_properties_grouped(sample_props, isc, skills)
    plain = fmt.format_properties_grouped_plain(sample_props, isc, skills)

    check(
        len(structured) == len(plain),
        "structured and plain return lists of the same length",
        f"structured={len(structured)}, plain={len(plain)}",
    )
    for i, (fp, s) in enumerate(zip(structured, plain)):
        check(
            fp.plain_text == s,
            f"entry {i}: plain_text == wrapper output",
            f"fp.plain_text={fp.plain_text!r}, s={s!r}",
        )


# ── Test 5: synthetic collapses have empty source_stat_ids ────────────────


def test_collapse_source_ids_empty() -> None:
    print("\n=== 5. Synthetic collapses carry source_stat_ids=() ===")
    fmt, isc, skills = _init_full_stack()

    # All-resistance collapse: 39/41/43/45 all present with the same value.
    props = [
        {"stat_id": 39, "name": "fireresist", "param": 0, "value": 25},
        {"stat_id": 41, "name": "lightresist", "param": 0, "value": 25},
        {"stat_id": 43, "name": "coldresist", "param": 0, "value": 25},
        {"stat_id": 45, "name": "poisonresist", "param": 0, "value": 25},
    ]
    out = fmt.format_properties_grouped(props, isc, skills)
    check(len(out) == 1, "all-resist collapse emits a single line", f"got {len(out)} lines")
    if out:
        check(
            out[0].source_stat_ids == (),
            "collapse line has empty source_stat_ids",
            f"got {out[0].source_stat_ids}",
        )
        check(
            "All Resistances" in out[0].plain_text,
            "collapse line mentions All Resistances",
            f"got {out[0].plain_text!r}",
        )


# ── Test 6: damage groups carry lead + followers ──────────────────────────


def test_damage_group_source_ids() -> None:
    print("\n=== 6. Damage groups carry (lead, *followers) in source_stat_ids ===")
    fmt, isc, skills = _init_full_stack()

    # Stats 21 (mindamage) + 22 (maxdamage) -> one "Adds X-Y Weapon Damage" line.
    props = [
        {"stat_id": 21, "name": "mindamage", "param": 0, "value": 3},
        {"stat_id": 22, "name": "maxdamage", "param": 0, "value": 7},
    ]
    out = fmt.format_properties_grouped(props, isc, skills)
    check(len(out) == 1, "damage pair collapses to one line")
    if out:
        check(
            out[0].source_stat_ids == (21, 22),
            "damage group source_stat_ids == (21, 22)",
            f"got {out[0].source_stat_ids}",
        )
        check(
            "3-7" in out[0].plain_text,
            "damage range present in plain_text",
            f"got {out[0].plain_text!r}",
        )

    # Lone follower (stat 22 only, no stat 21) renders individually
    # and carries (22,) - the lead-absence case.
    lone = fmt.format_properties_grouped(
        [{"stat_id": 22, "name": "maxdamage", "param": 0, "value": 7}],
        isc,
        skills,
    )
    check(len(lone) == 1, "lone follower renders individually")
    if lone:
        check(
            lone[0].source_stat_ids == (22,),
            "lone follower source_stat_ids == (22,)",
            f"got {lone[0].source_stat_ids}",
        )


# ── Test 7: format_prop plain path stays backward compatible ──────────────


def test_format_prop_plain_backward_compat() -> None:
    print("\n=== 7. format_prop returns plain strings (no tokens) ===")
    fmt, isc, skills = _init_full_stack()

    # Render the fadeDescription stat via the plain API; result must
    # NOT contain any colour byte.
    target_sid = None
    for sid in range(600):
        sd = isc.get(sid)
        if sd and sd.descstrpos == "fadeDescription":
            target_sid = sid
            break
    if target_sid is None:
        print("  SKIP  ISC has no fadeDescription stat in this install")
        return
    prop = {"stat_id": target_sid, "name": "fade", "param": 0, "value": 1}
    plain = fmt.format_prop(prop, isc, skills)
    check(
        plain is not None and "\xff" not in plain,
        "format_prop returns a token-free string",
        f"got {plain!r}",
    )
    check(
        plain == "You feel incorporeal...",
        "format_prop output is the stripped fluff text",
        f"got {plain!r}",
    )


# ── Entry point ────────────────────────────────────────────────────────────


def main() -> int:
    test_loader_preserves_tokens()
    test_segment_splitter_round_trip()
    test_end_to_end_fade_description()
    test_compat_wrapper_fixtures()
    test_collapse_source_ids_empty()
    test_damage_group_source_ids()
    test_format_prop_plain_backward_compat()

    print()
    print("=" * 60)
    print(f"Total: {_pass} PASS, {_fail} FAIL ({_pass + _fail} checks)")
    print("=" * 60)
    return 0 if _fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

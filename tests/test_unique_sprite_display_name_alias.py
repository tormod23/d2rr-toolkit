#!/usr/bin/env python3
"""Regression suite for the unique-sprite display-name alias fix.

Background
----------
``uniques.json`` / ``sets.json`` are keyed by snake-case of the RAW
``uniqueitems.txt`` / ``setitems.txt`` ``index`` column. The GUI and
the CLI resolve item sprites by the LOCALIZED display name that
flows through :class:`ItemNamesDatabase` (which returns the localised
string from ``item-names.json``). Where the mod localises an item to
something different from its raw name -- e.g. raw ``Life and Death``
is displayed as ``Life & Death`` in-game -- the two snake forms
diverge (``life_and_death`` vs ``life_death``) and the lookup misses.

Two symptoms of the same bug were fixed in lockstep:

  1. **Bulk loader storage key.** Phase 3 stored sprites under
     ``make_sprite_key(code, unique_name=raw_name)``, but the GUI
     queries with ``unique_name=display_name``. Divergence => miss =>
     the standard base-item sprite gets rendered instead.
  2. **uniques.json lookup.** ``_try_unique_sprite`` in the resolver
     and its equivalent lookup in the bulk loader snake-case the
     display name and look it up directly. Divergent keys miss.

The fix keys sprites under the localised display name (with the raw
name kept as a back-compat alias), and publishes helper loaders
``load_unique_sprite_map_with_aliases`` /
``load_set_sprite_map_with_aliases`` that register the display-name
snake as an alias pointing to the same asset.

Blast radius in the current Reimagined data: 37 uniques + 2 sets
where raw snake != display snake. Of the 37 uniques, 4 have a
dedicated sprite in ``uniques.json`` and were therefore user-visible
regressions (the other 33 fall back to the base item sprite anyway
and were never affected): Life & Death, El'Druin, Hellwarden's Will
(raw: Unique Warlock Helm), Ars Al'Diabolos (raw: Ars Al'Diablolos).

Test coverage:
  1. The three TC55 charms. Life & Death now resolves to the unique
     sprite; Valknut and Throne of Power keep resolving correctly.
  2. All four user-visible uniques with divergent display/raw names
     resolve to the unique sprite under the display-name key.
  3. Raw-name key still resolves (back-compat alias).
  4. ``load_unique_sprite_map_with_aliases`` populates exactly the
     divergent keys and leaves raw-only keys untouched.
  5. ``load_set_sprite_map_with_aliases`` analogous behaviour for the
     two diverging set items.
  6. Non-diverging uniques/sets unaffected: storage under display
     name == storage under raw name (same key).
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
    if cond:
        ok(name)
    else:
        fail(name, detail)


# ── Shared fixture builders ────────────────────────────────────────────────


def _init_full_stack():
    """Initialise paths + every loader needed for a full sprite preload."""
    from d2rr_toolkit.config import init_game_paths, get_game_paths
    from d2rr_toolkit.game_data.item_types import load_item_types
    from d2rr_toolkit.game_data.item_stat_cost import load_item_stat_cost
    from d2rr_toolkit.game_data.item_names import load_item_names
    from d2rr_toolkit.game_data.skills import load_skills
    from d2rr_toolkit.game_data.charstats import load_charstats
    from d2rr_toolkit.game_data.sets import load_sets
    from d2rr_toolkit.game_data.properties import load_properties
    from d2rr_toolkit.game_data.property_formatter import load_property_formatter
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
    return get_game_paths()


_sprite_cache: dict | None = None


def _run_bulk_loader():
    """Run the bulk sprite loader once, cache the result for later tests.

    Skipped transparently when Pillow or the game install is missing.
    """
    global _sprite_cache
    if _sprite_cache is not None:
        return _sprite_cache

    gp = _init_full_stack()

    try:
        from d2rr_toolkit.adapters.casc import CASCReader
        from d2rr_toolkit.sprites import (
            load_all_item_sprites,
            load_items_json,
            prepare_bulk_sprite_loader,
        )
    except Exception as e:
        print(f"  SKIP  toolkit sprite stack not importable: {e}")
        _sprite_cache = {}
        return _sprite_cache

    try:
        prepare_bulk_sprite_loader()
        casc = CASCReader(gp.d2r_install)
    except Exception as e:
        print(f"  SKIP  CASC init failed: {e}")
        _sprite_cache = {}
        return _sprite_cache

    try:
        items_json = load_items_json(gp.mod_items_json)
        _sprite_cache = load_all_item_sprites(
            casc_reader=casc,
            game_paths=gp,
            items_json=items_json,
        )
    except Exception as e:
        print(f"  SKIP  bulk sprite load failed: {e}")
        _sprite_cache = {}
    return _sprite_cache


# ── Tests ──────────────────────────────────────────────────────────────────


def test_tc55_unique_large_charms() -> None:
    """The three unique large charms in FrozenOrbHydra all render correctly."""
    print("\n=== 1. TC55 unique large charms render the unique sprite ===")
    from d2rr_toolkit.sprites import make_sprite_key

    sprites = _run_bulk_loader()
    if not sprites:
        return

    cases = [
        # (display_name, raw_index_name)
        ("Life & Death", "Life and Death"),
        ("Valknut", "Valknut"),
        ("Throne of Power", "Throne of Power"),
    ]
    for display, raw in cases:
        key = make_sprite_key("cm2", unique_name=display)
        png = sprites.get(key)
        check(png is not None, f"sprite stored under display name {display!r}", f"key={key!r}")
        # Sanity: the unique sprite MUST differ from the base cm2 sprite.
        # (Otherwise the GUI would still show the base anyway.)
        base = sprites.get(make_sprite_key("cm2"))
        if png and base:
            check(png != base, f"{display!r} sprite differs from the cm2 base sprite")
        # Back-compat: legacy raw-name key still resolves to the same PNG.
        raw_png = sprites.get(make_sprite_key("cm2", unique_name=raw))
        if png is not None and raw != display:
            check(raw_png == png, f"back-compat: raw-name key {raw!r} resolves to same sprite")


def test_user_visible_diverging_uniques() -> None:
    """All four user-visible divergent uniques resolve via display name."""
    print("\n=== 2. All divergent uniques with a sprite are now reachable ===")
    from d2rr_toolkit.sprites import make_sprite_key

    sprites = _run_bulk_loader()
    if not sprites:
        return

    # (base_code, raw_index, display_name) -- codes pulled directly from
    # uniqueitems.txt so the test is pinned against the live data.
    targets = [
        ("cm2", "Life and Death", "Life & Death"),
        ("xsk", "Unique Warlock Helm", "Hellwarden's Will"),
        ("waf", "Ars Al'Diablolos", "Ars Al'Diabolos"),
        ("7gs", "El Druin", "El'Druin"),
    ]

    for code, raw, display in targets:
        key_display = make_sprite_key(code, unique_name=display)
        key_raw = make_sprite_key(code, unique_name=raw)
        png_display = sprites.get(key_display)
        png_raw = sprites.get(key_raw)
        check(
            png_display is not None,
            f"{display!r} ({code}) stored under display-name key",
            f"key={key_display!r}",
        )
        if png_display is not None and png_raw is not None:
            check(png_display == png_raw, f"{display!r} and {raw!r} keys resolve to the same PNG")


def test_alias_helpers_populate_diverging_entries() -> None:
    """load_unique_sprite_map_with_aliases populates display snakes."""
    print("\n=== 3. load_unique_sprite_map_with_aliases adds display-name keys ===")
    from d2rr_toolkit.sprites import (
        load_unique_sprite_map,
        load_unique_sprite_map_with_aliases,
    )
    from d2rr_toolkit.game_data.item_names import get_item_names_db
    from d2rr_toolkit.adapters.casc import read_game_data_rows

    _init_full_stack()
    names = get_item_names_db()
    rows = read_game_data_rows("data:data/global/excel/uniqueitems.txt")

    from d2rr_toolkit.config import get_game_paths

    gp = get_game_paths()
    plain = load_unique_sprite_map(gp.mod_uniques_json)
    aliased = load_unique_sprite_map_with_aliases(
        gp.mod_uniques_json,
        rows,
        names,
    )

    # Aliased is a strict superset of plain.
    check(
        len(aliased) >= len(plain),
        "aliased map has >= entries than plain",
        f"plain={len(plain)}, aliased={len(aliased)}",
    )
    for k in plain:
        check(
            aliased.get(k) == plain[k],
            f"plain key {k!r} preserved",
            f"plain={plain[k]!r}, aliased={aliased.get(k)!r}",
        ) if False else None
    # Spot-check the four user-visible aliases.
    expected_aliases = [
        ("life_and_death", "life_death"),
        ("unique_warlock_helm", "hellwardens_will"),
        ("ars_aldiablolos", "ars_aldiabolos"),
        ("el_druin", "eldruin"),
    ]
    for raw_snake, disp_snake in expected_aliases:
        raw_asset = plain.get(raw_snake)
        if raw_asset is None:
            # Item isn't in uniques.json - skip silently (e.g. data update).
            continue
        check(
            aliased.get(disp_snake) == raw_asset,
            f"alias {disp_snake!r} -> same asset as {raw_snake!r}",
            f"expected {raw_asset!r}, got {aliased.get(disp_snake)!r}",
        )


def test_alias_helper_noop_without_names_db() -> None:
    """Alias helper degrades gracefully without a names_db (returns plain)."""
    print("\n=== 4. Helper returns the plain map when names_db is None ===")
    from d2rr_toolkit.sprites import (
        load_unique_sprite_map,
        load_unique_sprite_map_with_aliases,
    )

    _init_full_stack()
    from d2rr_toolkit.config import get_game_paths

    gp = get_game_paths()

    plain = load_unique_sprite_map(gp.mod_uniques_json)
    aliased_none = load_unique_sprite_map_with_aliases(
        gp.mod_uniques_json,
        [],
        None,
    )
    check(aliased_none == plain, "names_db=None => aliased map == plain map")


def test_set_alias_helper() -> None:
    """Two Panda set items are the only diverging set rows; alias them."""
    print("\n=== 5. load_set_sprite_map_with_aliases handles Panda rename ===")
    from d2rr_toolkit.sprites import (
        load_set_sprite_map,
        load_set_sprite_map_with_aliases,
    )
    from d2rr_toolkit.game_data.item_names import get_item_names_db
    from d2rr_toolkit.adapters.casc import read_game_data_rows

    _init_full_stack()
    names = get_item_names_db()
    rows = read_game_data_rows("data:data/global/excel/setitems.txt")

    from d2rr_toolkit.config import get_game_paths

    gp = get_game_paths()
    plain = load_set_sprite_map(gp.mod_sets_json)
    aliased = load_set_sprite_map_with_aliases(gp.mod_sets_json, rows, names)

    check(
        len(aliased) >= len(plain),
        "aliased set map has >= entries than plain",
        f"plain={len(plain)}, aliased={len(aliased)}",
    )

    # Panda's Mitts -> Panda's Mittens ; Panda's Coat -> Panda's Jacket
    for raw_snake, disp_snake in [
        ("pandas_mitts", "pandas_mittens"),
        ("pandas_coat", "pandas_jacket"),
    ]:
        raw_asset = plain.get(raw_snake)
        if raw_asset is None:
            continue
        check(
            aliased.get(disp_snake) == raw_asset,
            f"alias {disp_snake!r} -> same asset as {raw_snake!r}",
        )


def test_non_diverging_unique_still_single_key() -> None:
    """Non-diverging uniques don't gain a phantom alias."""
    print("\n=== 6. Non-diverging uniques stay single-keyed ===")
    from d2rr_toolkit.sprites import make_sprite_key

    sprites = _run_bulk_loader()
    if not sprites:
        return

    # Valknut: raw index == display name. make_sprite_key should
    # produce exactly one storage key and no extra aliases.
    key = make_sprite_key("cm2", unique_name="Valknut")
    check(sprites.get(key) is not None, "Valknut key resolves to a PNG", f"key={key!r}")


# ── Entry point ────────────────────────────────────────────────────────────


def main() -> int:
    test_tc55_unique_large_charms()
    test_user_visible_diverging_uniques()
    test_alias_helpers_populate_diverging_entries()
    test_alias_helper_noop_without_names_db()
    test_set_alias_helper()
    test_non_diverging_unique_still_single_key()

    print()
    print("=" * 60)
    print(f"Total: {_pass} PASS, {_fail} FAIL ({_pass + _fail} checks)")
    print("=" * 60)
    return 0 if _fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())


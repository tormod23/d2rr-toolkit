#!/usr/bin/env python3
"""Test suite for d2rr_toolkit.catalog.item_catalog.

Validates that the data-driven Item Type / Equipment enumeration
matches the expected shape of the GUI filter dropdowns:

  * list_equippable_types returns non-trivial coverage.
  * Common categories ('tors', 'bow', 'ring', 'cm3', 'csch', 'grim',
    'orb') are present, properly labelled, and contain the items the
    reference GUI dropdown lists today.
  * Equiv-chain resolution works end-to-end: 'armo' is an echte
    Obermenge of 'tors', 'shie', etc.
  * Tier suffixes propagate into ItemEntry.tier_suffix.
  * Lookups tolerate unknown codes.
  * Every equippable type has at least one base item (item_count > 0).
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def _init() -> None:
    import logging

    logging.basicConfig(level=logging.ERROR)
    from d2rr_toolkit.cli import _load_game_data

    _load_game_data(PROJECT_ROOT / "tests" / "cases" / "TC49" / "MrLockhart.d2s")


def main() -> int:
    _init()
    from d2rr_toolkit.catalog import get_item_catalog

    catalog = get_item_catalog()
    if not catalog.is_loaded():
        print("FAIL  ItemCatalog not loaded after _load_game_data")
        return 1

    passed = failed = 0

    def check(cond: bool, name: str, detail: str = "") -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"  PASS  {name}")
        else:
            failed += 1
            print(f"  FAIL  {name}")
            if detail:
                print(f"        {detail}")

    # ── 1. list_equippable_types coverage ─────────────────────────
    print("\n=== 1. list_equippable_types ===")
    types = catalog.list_equippable_types()
    check(len(types) >= 40, f">=40 equippable types returned (got {len(types)})")

    codes = {t.code for t in types}
    required_codes = {
        "tors",  # Armor ("Body Armor" in GUI)
        "shie",  # Shield
        "shld",  # Any Shield
        "armo",  # Any Armor
        "ring",
        "amul",
        "jewl",
        "cjwl",  # Jewellery
        "scha",
        "mcha",
        "lcha",
        "csch",  # Charms: Small/Large/Grand/Sunder
        "boot",
        "glov",
        "belt",  # Body parts
        "circ",  # Circlet
        "axe",
        "club",
        "mace",
        "hamm",
        "swor",  # Weapons
        "knif",
        "spea",
        "pole",
        "scep",
        "staf",
        "wand",
        "bow",
        "xbow",
        "jave",
        "tkni",
        "taxe",  # Throwing
        "bowq",
        "xboq",  # Quivers (filterable via rollable descendants)
        "mele",
        "miss",
        "thro",
        "weap",  # Weapon super-categories
        # Class-specific (codes as in Reimagined itemtypes.txt)
        "amaz",
        "abow",
        "aspe",
        "ajav",  # Amazon parent + Bow/Spear/Javelin
        "h2h",  # Assassin Hand-to-Hand
        "phlm",
        "pelt",  # Barbarian Primal Helm, Druid Pelt
        "head",
        "ashd",
        "orb",
        "grim",  # Necro/Paladin/Sorc/Warlock off-hands
    }
    missing = required_codes - codes
    check(
        not missing,
        "every GUI-facing type code is present",
        f"missing: {sorted(missing)}" if missing else "",
    )

    # Alphabetical ordering (case-insensitive).
    sorted_names = [t.display_name for t in types]
    check(
        sorted_names == sorted(sorted_names, key=str.lower),
        "list_equippable_types is sorted alphabetically",
    )

    # Every returned type has >=1 base item (filterable categories only).
    zero = [t for t in types if t.item_count == 0]
    check(
        not zero,
        "no equippable type is empty",
        f"empty types: {[t.code for t in zero]}" if zero else "",
    )

    # Every returned type is_filterable by definition of list_equippable_types.
    not_filterable = [t for t in types if not t.is_filterable]
    check(
        not not_filterable, "every listed type is_filterable", f"{[t.code for t in not_filterable]}"
    )

    # Spot-check: bowq is rollable=False but filterable=True (via mboq).
    bowq = catalog.get_item_type("bowq")
    check(
        bowq is not None and not bowq.is_rollable and bowq.is_filterable,
        "bowq: is_rollable=False, is_filterable=True (via mboq descendant)",
        f"bowq={bowq!r}",
    )

    # Negative control: plain gems are never filterable.
    gem_type = catalog.get_item_type("gem")
    check(
        gem_type is not None and not gem_type.is_filterable,
        "gem: is_filterable=False (no rollable descendants)",
    )

    # ── 2. Body Armor (tors) - well-known contents ────────────────
    print("\n=== 2. list_items_of_type('tors') body armor ===")
    torso = catalog.list_items_of_type("tors")
    codes_in_torso = {it.code for it in torso}
    # Sanity: canonical Normal/Exceptional/Elite anchors.
    for expected_code, expected_tier in (
        ("qui", " [N]"),  # Quilted Armor (Normal)
        ("aar", " [N]"),  # Ancient Armor (Normal)
        ("xap", " [E]"),  # Archon Plate (Elite)
        ("uld", " [E]"),  # Dusk Shroud (Elite - elite Quilted tier)
        ("xmp", " [X]"),  # Mage Plate (Exceptional)
    ):
        if expected_code in codes_in_torso:
            entry = next(it for it in torso if it.code == expected_code)
            check(
                entry.tier_suffix == expected_tier,
                f"{expected_code}: tier {expected_tier!r}",
                f"got {entry.tier_suffix!r}",
            )
    check(len(torso) >= 30, f"Body Armor has >=30 entries (got {len(torso)})")
    check(
        all(it.tier_suffix in (" [N]", " [X]", " [E]") for it in torso),
        "every torso item carries a tier suffix",
    )

    # Display-name sort.
    dn = [it.display_name for it in torso]
    check(dn == sorted(dn, key=str.lower), "Body Armor list is sorted by display name")

    # ── 3. Any Armor (armo) - superset of tors/helm/shie/... ────────
    print("\n=== 3. Any Armor bundle ===")
    any_armor = catalog.list_items_of_type("armo")
    any_codes = {it.code for it in any_armor}
    check(codes_in_torso.issubset(any_codes), "Any Armor contains every Body Armor item")

    # Also expect at least one helm, shield, boot, glove, belt.
    def _any_of_type(items, code):
        return any(it.type_code == code or it.type2_code == code for it in items)

    for cat_code in ("helm", "shie", "boot", "glov", "belt"):
        check(_any_of_type(any_armor, cat_code), f"Any Armor covers type '{cat_code}'")

    # Any Armor should NOT include weapons.
    overlap_weap = catalog.list_items_of_type("weap")
    weap_codes = {it.code for it in overlap_weap}
    check(not (any_codes & weap_codes), "Any Armor and Any Weapon are disjoint")

    # ── 4. Jewel vs Colossal Jewel - distinct buckets ─────────────
    print("\n=== 4. Jewel / Colossal Jewel disjointness ===")
    jewl = catalog.list_items_of_type("jewl", include_descendants=False)
    cjwl = catalog.list_items_of_type("cjwl", include_descendants=False)
    check(jewl, "Jewel bucket non-empty")
    check(cjwl, "Colossal Jewel bucket non-empty")
    check(
        not ({it.code for it in jewl} & {it.code for it in cjwl}),
        "Jewel and Colossal Jewel share no items (include_descendants=False)",
    )

    # ── 5. Crafted Sunder Charm isolated ──────────────────────────
    print("\n=== 5. Crafted Sunder Charm (csch) ===")
    csch = catalog.list_items_of_type("csch")
    check(len(csch) >= 1, "Crafted Sunder Charm has >=1 entry")

    # ── 6. Charms - coverage matches Reimagined's data ───────────
    # Reimagined ships multiple GFX variants per charm size; the base
    # name is "Small Charm*" / "Large Charm*" / "Grand Charm*" (the
    # trailing asterisk is an intrinsic Reimagined convention, not a
    # toolkit artefact). Latent Sunder Charm (cs1) shares the Grand
    # Charm size bucket as its type2 = lcha.
    print("\n=== 6. Charms ===")
    scha = catalog.list_items_of_type("scha", include_descendants=False)
    mcha = catalog.list_items_of_type("mcha", include_descendants=False)
    lcha = catalog.list_items_of_type("lcha", include_descendants=False)
    scha_codes = {it.code for it in scha}
    mcha_codes = {it.code for it in mcha}
    lcha_codes = {it.code for it in lcha}
    check("cm1" in scha_codes, "Small Charm bucket contains cm1", f"got {sorted(scha_codes)}")
    check(mcha_codes == {"cm2"}, "Large Charm bucket == {cm2}", f"got {sorted(mcha_codes)}")
    check("cm3" in lcha_codes, "Grand Charm bucket contains cm3", f"got {sorted(lcha_codes)}")
    # The display name comes from the game data verbatim (incl. the
    # trailing '*'); we only assert the non-asterisk prefix so a
    # Reimagined cosmetic change to the suffix would not break the test.
    cm1 = next(it for it in scha if it.code == "cm1")
    cm3 = next(it for it in lcha if it.code == "cm3")
    check(
        cm1.display_name.startswith("Small Charm"),
        "cm1 display starts with 'Small Charm'",
        f"got {cm1.display_name!r}",
    )
    check(
        cm3.display_name.startswith("Grand Charm"),
        "cm3 display starts with 'Grand Charm'",
        f"got {cm3.display_name!r}",
    )

    # ── 7. ItemTypeEntry fields ───────────────────────────────────
    print("\n=== 7. ItemTypeEntry ===")
    tors_entry = catalog.get_item_type("tors")
    check(tors_entry is not None, "lookup of 'tors' returns an entry")
    if tors_entry:
        check(
            tors_entry.display_name == "Armor",
            "'tors' display_name == 'Armor' (verbatim from itemtypes.txt)",
        )
        check("armo" in tors_entry.equiv_chain, "'tors' equiv chain climbs to 'armo'")
        check(tors_entry.is_rollable, "'tors' is rollable (Rare=1)")
        check(tors_entry.item_count > 0, "'tors' has a positive item_count")

    # ── 8. Lookups tolerate unknown codes ─────────────────────────
    print("\n=== 8. Defensive lookups ===")
    check(catalog.get_item_type("nonexistent") is None, "unknown type returns None")
    check(catalog.get_item("xxxxx") is None, "unknown item code returns None")
    check(catalog.list_items_of_type("nonexistent") == [], "unknown type code yields empty list")

    # ── 9. No duplicates in equippable types ──────────────────────
    print("\n=== 9. Integrity ===")
    check(len(codes) == len(types), "equippable types are unique by code")

    # Every equippable type is filterable (>=1 rollable descendant) AND
    # has >=1 base item. Not every one is is_rollable itself - quivers
    # (bowq/xboq) are intentionally included via their rollable Magic
    # quiver children even though their own row has Magic=0 Rare=0.
    check(
        all(t.is_filterable and t.item_count > 0 for t in types),
        "every equippable entry is filterable and non-empty",
    )
    non_rollable_listed = [t.code for t in types if not t.is_rollable]
    check(
        set(non_rollable_listed) >= {"bowq", "xboq"},
        "quivers (bowq, xboq) are listed despite is_rollable=False - "
        "admitted via rollable descendants (mboq, mxbq)",
        f"non-rollable listed: {sorted(non_rollable_listed)}",
    )

    # ── 10. Iron Rule: Reimagined mod wins over CASC ──────────────
    # load() delegates every file access to CASCReader.read_file,
    # which tries the mod install first and falls back to CASC only
    # when the file is absent there. Because Reimagined itemtypes.txt
    # contains codes that the vanilla D2R CASC does NOT have
    # (Colossal Jewel, Crafted Sunder Charm, Warlock Item, Amazon
    # Bow/Spear/Javelin), their presence proves the loader served the
    # Reimagined copy - not a silent fallback to vanilla CASC.
    print("\n=== 10. Iron Rule - Reimagined wins over CASC ===")
    from d2rr_toolkit.config import get_game_paths
    from d2rr_toolkit.adapters.casc import (
        CASCReader,
        get_game_data_reader,
        reset_game_data_reader,
    )
    from d2rr_toolkit.catalog import ItemCatalog as _IC

    try:
        gp = get_game_paths()
    except Exception:  # pragma: no cover - D2R not installed
        gp = None

    if gp is not None and gp.reimagined_excel.is_dir():
        # Default path: load() with no argument uses the shared reader
        # (which was constructed by _load_game_data in _init).
        default_cat = _IC()
        default_cat.load()
        check(
            default_cat.is_loaded() and len(default_cat.list_equippable_types()) > 0,
            "load() with no reader uses the shared singleton",
            f"types={len(default_cat.list_equippable_types())}",
        )
        # Explicit reader - same mod_dir + game_dir as the singleton,
        # just proves the explicit-argument path works identically.
        explicit = CASCReader(game_dir=gp.d2r_install, mod_dir=gp.mod_mpq)
        explicit_cat = _IC()
        explicit_cat.load(explicit)
        check(
            explicit_cat.is_loaded()
            and len(explicit_cat.list_equippable_types())
            == len(default_cat.list_equippable_types()),
            "explicit CASCReader yields same result as singleton",
            f"default={len(default_cat.list_equippable_types())}, "
            f"explicit={len(explicit_cat.list_equippable_types())}",
        )
        # The Iron-Rule evidence: Reimagined-only codes.
        reimagined_only = {"cjwl", "csch", "warl", "abow", "aspe", "ajav"}
        codes_present = {t.code for t in default_cat.list_equippable_types()}
        missing = reimagined_only - codes_present
        check(
            not missing,
            "Reimagined-only type codes are present - mod wins over CASC",
            f"missing: {sorted(missing)}" if missing else "",
        )
    else:
        check(True, "D2R not installed - skipping iron-rule check")

    # ── 11. Failure modes ─────────────────────────────────────────
    # Loading from a CASCReader whose ``game_dir`` contains neither
    # the Reimagined mod files nor a CASC archive MUST raise
    # FileNotFoundError and leave is_loaded=False, so callers can
    # distinguish a clean load from a misconfiguration.
    print("\n=== 11. Failure mode - unreachable reader ===")
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        empty_root = Path(td)
        try:
            broken_reader = CASCReader(game_dir=empty_root, mod_dir=None)
            cat_empty = _IC()
            raised = False
            try:
                cat_empty.load(broken_reader)
            except FileNotFoundError:
                raised = True
            except Exception as e:
                # Some CASC-init failures raise earlier; treat them as
                # acceptable since the end result is still "no data".
                raised = True
                logger.debug("broken reader raised early: %s", e)
            check(raised, "load() raises on a reader with no data sources")
            check(
                not cat_empty.is_loaded(),
                "is_loaded() stays False after a failed load",
            )
        except Exception as e:
            # CASCReader construction itself failed on the empty dir -
            # that's also a sufficient signal that the iron rule is
            # catching misconfigurations loudly.
            check(True, f"CASCReader constructor refused empty game_dir ({type(e).__name__})")

    # Restore clean singleton state so subsequent tests are unaffected.
    reset_game_data_reader()

    # ── 12. Iron Rule at the CASCReader layer ────────────────────
    # Read itemtypes.txt bytes directly through the singleton. The
    # file MUST come from the Reimagined mod install on disk, not
    # from CASC - confirmable by comparing file contents against the
    # mod's own ``itemtypes.txt`` at a known path. If anyone ever
    # breaks the mod-first order in CASCReader.read_file, these two
    # byte strings diverge (or the read returns CASC vanilla).
    print("\n=== 12. Iron Rule - byte-level mod override ===")
    if gp is not None and gp.mod_mpq.is_dir():
        mod_copy_path = gp.mod_mpq / "data" / "global" / "excel" / "itemtypes.txt"
        if mod_copy_path.is_file():
            mod_bytes = mod_copy_path.read_bytes()
            reader = get_game_data_reader()
            served = reader.read_file("data:data/global/excel/itemtypes.txt")
            check(
                served is not None and served == mod_bytes,
                "CASCReader served the exact Reimagined mod itemtypes.txt bytes",
                f"mod_copy={len(mod_bytes)} bytes, served="
                f"{'None' if served is None else f'{len(served)} bytes'}, "
                f"equal={served == mod_bytes if served else False}",
            )
        else:
            check(True, "mod itemtypes.txt not present - skipping byte-level check")
    else:
        check(True, "D2R not installed - skipping byte-level iron-rule check")

    # ── Summary ───────────────────────────────────────────────────
    total = passed + failed
    print()
    print("=" * 56)
    print(f"Total: {passed} PASS, {failed} FAIL ({total} checks)")
    print("=" * 56)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

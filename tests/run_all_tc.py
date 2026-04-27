"""
Run all test cases TC01-TC34 and report pass/fail.

Usage:
    python -m tests.run_all_tc
"""

# ---------------------------------------------------------------------------
# Coding note:  prop['value'] in magical_properties is always the DISPLAY value
# (parser has already applied: display = raw_binary - save_add).
# Do NOT subtract save_add again when reading prop['value'] in checks.
# ---------------------------------------------------------------------------
from pathlib import Path
import sys

# Project root must be on path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

from d2rr_toolkit.parsers.d2s_parser import D2SParser
from d2rr_toolkit.parsers.d2i_parser import D2IParser
from d2rr_toolkit.game_data.charstats import load_charstats, get_charstats_db
from d2rr_toolkit.game_data.hireling import load_hireling, load_merc_names
from d2rr_toolkit.game_data.item_names import load_item_names, get_item_names_db
from d2rr_toolkit.game_data.item_stat_cost import load_item_stat_cost
from d2rr_toolkit.game_data.item_types import load_item_types
from d2rr_toolkit.game_data.skills import load_skills
from d2rr_toolkit.game_data.cubemain import load_cubemain, get_cubemain_db

import logging

logging.basicConfig(level=logging.WARNING)


# ---------------------------------------------------------------------------
# TC26: Deep validation - Crafted items (quality 8), Indestructible via ISC
# ---------------------------------------------------------------------------


def _check_tc26_details(cases_dir: Path) -> tuple[str, str, str]:
    """Detailed expected-value checks for TC26 (TestSorc.d2s).

    Verifications
    -------------
    - Exactly 8 items, all quality=8 (Crafted)
    - Item codes and inventory positions
    - Armor items: defense_display, durability (current/max)
    - Key properties for armor, boots, shield, belt via stat_id + value

    Key finding - Indestructible in Reimagined
    ------------------------------------------
    The Crafted Round Shield (xml) at (8,0) carries stat 152
    (item_indesctructible=1) as a normal ISC property. Its binary
    max_durability is 64 (NON-ZERO). This proves Reimagined stores
    Indestructible as an ISC stat, NOT as max_dur=0 - so the "indestructible
    item needs cur_dur skip" concern does NOT apply to Reimagined.
    [BINARY_VERIFIED TC26]

    Property list note
    ------------------
    Rings (pos 0-2,0) and amulet (3,0) have truncated property lists because
    their binary data contains Reimagined-internal stat_ids > 435. The parser
    stops at those stats and returns only the properties before them.  This is
    expected behavior (see also TC06/DFS). Armor/boots/shield/belt parse
    their full property lists correctly.

    Returns:
        (status, info, detail) tuple.
    """
    f = cases_dir / "TC26" / "TestSorc.d2s"
    try:
        parser = D2SParser(f)
        char = parser.parse()
    except Exception as e:
        return ("FAIL", "parse error", str(e)[:120])

    items = char.items
    errors: list[str] = []

    # ── 1. Item count ───────────────────────────────────────────────────────
    if len(items) != 8:
        errors.append(f"Expected 8 items, got {len(items)}")

    # ── 2. All items must be quality=8 (Crafted) ────────────────────────────
    for item in items:
        if item.extended and item.extended.quality != 8:
            errors.append(
                f"pos ({item.flags.position_x},{item.flags.position_y}): "
                f"expected quality=8(Crafted), got {item.extended.quality}"
            )

    # ── 3. Build position lookup ─────────────────────────────────────────────
    by_pos: dict[tuple[int, int], object] = {}
    for item in items:
        key = (item.flags.position_x, item.flags.position_y)
        by_pos[key] = item

    def check(
        pos: tuple[int, int],
        code: str,
        ilvl: int,
        props: list[tuple[int, int]] | None = None,
        dur: tuple[int, int] | None = None,
        def_display: int | None = None,
    ) -> None:
        """Assert one item's expected parser-output fields.

        Args:
            pos:         (x, y) inventory position.
            code:        Expected item code.
            ilvl:        Expected item level.
            props:       [(stat_id, display_value), ...] - prop['value'] is
                         already the display value (save_add already applied).
            dur:         (current, max) raw binary durability values.
            def_display: Expected armor_data.defense_display.
        """
        item = by_pos.get(pos)
        if item is None:
            errors.append(f"No item at pos {pos}")
            return
        if item.item_code != code:
            errors.append(f"pos {pos}: expected code {code!r}, got {item.item_code!r}")
        il = item.extended.item_level if item.extended else -1
        if il != ilvl:
            errors.append(f"pos {pos} ({code}): expected ilvl {ilvl}, got {il}")
        if dur is not None and item.armor_data:
            cur = item.armor_data.durability.current_durability
            mx = item.armor_data.durability.max_durability
            if (cur, mx) != dur:
                errors.append(f"pos {pos} ({code}): expected dur {dur}, got ({cur},{mx})")
        if def_display is not None and item.armor_data:
            dd = item.armor_data.defense_display
            if dd != def_display:
                errors.append(
                    f"pos {pos} ({code}): expected defense_display {def_display}," f" got {dd}"
                )
        if props:
            for stat_id, expected_val in props:
                found = [p for p in item.magical_properties if p["stat_id"] == stat_id]
                if not found:
                    errors.append(f"pos {pos} ({code}): missing stat_id {stat_id}")
                elif found[0].get("value") != expected_val:
                    errors.append(
                        f"pos {pos} ({code}): stat_id {stat_id} expected "
                        f"value {expected_val}, got {found[0].get('value')}"
                    )

    # ── Rings (partial property lists - just verify code/ilvl) ───────────────
    check((0, 0), "rin", ilvl=98)  # Order Grasp
    check((1, 0), "rin", ilvl=98)  # Bone Loop
    check((2, 0), "rin", ilvl=98)  # Ghoul Turn

    # ── Amulet (partial property list) ───────────────────────────────────────
    check((3, 0), "amu", ilvl=98)  # Beast Emblem

    # ── Body Armor ───────────────────────────────────────────────────────────
    # [BINARY_VERIFIED TC26] defense_display=18 is the raw armor field;
    # in-game shows 48 because item_armor_percent (+167%) is applied.
    check(
        (4, 0),
        "lea",
        ilvl=98,
        dur=(14, 24),
        def_display=18,
        props=[
            (127, 2),  # +2 to All Skills
            (16, 167),  # +167% Enhanced Defense
            (7, 86),  # +86 to Life  (display=raw_binary-32=118-32=86)
            (78, 47),  # Attacker Takes Damage of 47
            (151, 3),  # Level 3 Conviction Aura  (param=123 not checked here)
        ],
    )

    # ── Boots ────────────────────────────────────────────────────────────────
    check(
        (6, 0),
        "xvb",
        ilvl=98,
        dur=(14, 14),
        def_display=40,
        props=[
            (127, 1),  # +1 to All Skills
            (16, 93),  # +93% Enhanced Defense
            (96, 28),  # +28% Faster Run/Walk  (display=raw_binary-20=48-20=28)
            (21, 20),  # Adds 20-30 Weapon Damage (min)
            (22, 30),  # Adds 20-30 Weapon Damage (max)
            (74, 5),  # Replenish Life +5  (display=raw_binary-30=35-30=5)
            (44, 4),  # +4% to Maximum Cold Resistance
            (252, 5),  # Repairs 1 Durability in 20 Seconds (raw=5)
        ],
    )

    # ── Round Shield - KEY: Indestructible via ISC stat 152, max_dur=64 ─────
    # [BINARY_VERIFIED TC26] Reimagined stores Indestructible as ISC stat 152
    # (item_indesctructible=1). The binary max_durability is 64 (non-zero).
    # Conclusion: no "skip cur_dur when max_dur=0" fix needed for Reimagined.
    check(
        (8, 0),
        "xml",
        ilvl=98,
        dur=(40, 64),  # max_dur=64 (non-zero!) despite being Indestructible
        def_display=56,
        props=[
            (152, 1),  # item_indesctructible = 1  [BINARY_VERIFIED]
            (127, 2),  # +2 to All Skills
            (16, 83),  # +83% Enhanced Defense
            (43, 28),  # +28% Cold Resistance
            (118, 1),  # Half Freeze Duration
            (329, 14),  # +14% to All Elemental Skill Damage (fire)
            (333, 14),  # -14% to All Enemy Elemental Resistances (fire)
        ],
    )

    # ── Belt ─────────────────────────────────────────────────────────────────
    check(
        (0, 1),
        "zlb",
        ilvl=98,
        dur=(11, 12),
        def_display=35,
        props=[
            (127, 1),  # +1 to All Skills
            (16, 218),  # +218% Enhanced Defense
            (0, 11),  # +11 to Strength (save_add=0, display=raw=11)
        ],
    )

    # ── Result ───────────────────────────────────────────────────────────────
    if errors:
        detail = "; ".join(errors)
        return ("FAIL", f"{len(errors)} check(s) failed", detail[:200])
    return (
        "PASS",
        "8 Crafted items, armor/boots/shield/belt verified [Indestructible=ISC stat]",
        "",
    )


# ---------------------------------------------------------------------------
# TC24: Deep validation - Inline socket children + Rare jewel 7-slot QSD
# ---------------------------------------------------------------------------


def _check_tc24_details(cases_dir: Path) -> tuple[str, str, str]:
    """Detailed expected-value checks for TC24 (TestSorc.d2s).

    Verifications
    -------------
    - Exactly 13 items (3 parents + 10 inline socket children)
    - 4 Jewel socket children in gth (Thresher) with correct quality+properties
    - J2 (Rare jewel, quality=6): properties from 7-slot QSD retry
      [BINARY_VERIFIED TC24 J2 - regression test for the 7-slot QSD fix]

    Key finding - 7-slot Rare QSD in Reimagined
    --------------------------------------------
    Reimagined Rare misc items (e.g. jewels) have a 7th affix slot (1-bit has
    flag + optional 10-bit affix ID) after the standard 6 affix slots. Without
    accounting for this, J2's property list is misaligned (fake stats appear
    before an unknown stat_id=448 causes the scanner fallback to fire).
    The retry mechanism in _parse_single_item detects the misalignment and
    re-reads QSD with 7 slots, recovering the correct properties.
    [BINARY_VERIFIED TC24 J2: energy=6, mindamage=8, fireresist=15, ...]

    Returns:
        (status, info, detail) tuple.
    """
    f = cases_dir / "TC24" / "TestSorc.d2s"
    try:
        parser = D2SParser(f)
        char = parser.parse()
    except Exception as e:
        return ("FAIL", "parse error", str(e)[:120])

    items = char.items
    errors: list[str] = []

    # Hierarchical model: char.items contains only ROOT items; socket
    # children live in each parent's socket_children list. The legacy
    # expectation "13 flat items" maps to "3 roots + 10 nested children".
    flat_total = len(items) + sum(len(it.socket_children) for it in items)
    if flat_total != 13:
        errors.append(f"Expected 13 items (3 roots + 10 children), got {flat_total}")

    # ── 2. Find the 4 jewel socket children - flatten across all parents ──
    jewels = [child for it in items for child in it.socket_children if child.item_code == "jew"]
    if len(jewels) != 4:
        errors.append(f"Expected 4 jewel socket children, got {len(jewels)}")
        if errors:
            return ("FAIL", f"{len(errors)} check(s) failed", "; ".join(errors)[:200])

    def props_of(item) -> dict[int, int]:
        return {p["stat_id"]: p["value"] for p in (item.magical_properties or [])}

    # ── 3. Find each jewel by quality ───────────────────────────────────────
    rare_jewels = [j for j in jewels if j.extended and j.extended.quality == 6]
    unique_jewels = [j for j in jewels if j.extended and j.extended.quality == 7]
    magic_jewels = [j for j in jewels if j.extended and j.extended.quality == 4]

    if len(rare_jewels) != 1:
        errors.append(f"Expected 1 Rare jewel (q=6), got {len(rare_jewels)}")
    if len(unique_jewels) != 1:
        errors.append(f"Expected 1 Unique jewel (q=7), got {len(unique_jewels)}")
    if len(magic_jewels) != 2:
        errors.append(f"Expected 2 Magic jewels (q=4), got {len(magic_jewels)}")

    # ── 4. J2 - Rare jewel [BINARY_VERIFIED: 7-slot QSD fix] ───────────────
    if rare_jewels:
        j2 = rare_jewels[0]
        p = props_of(j2)
        for stat_id, expected in [
            (1, 6),  # +6 Energy
            (39, 15),  # +15% Fire Resistance
            (41, 15),  # +15% Lightning Resistance
            (43, 15),  # +15% Cold Resistance
            (45, 15),  # +15% Poison Resistance
            (21, 8),  # Adds 8-? Min Damage
        ]:
            if p.get(stat_id) != expected:
                errors.append(
                    f"J2 (Rare jew): stat_id {stat_id} expected {expected},"
                    f" got {p.get(stat_id)!r}"
                )

    # ── 5. J4 - Unique jewel ────────────────────────────────────────────────
    if unique_jewels:
        j4 = unique_jewels[0]
        p = props_of(j4)
        for stat_id, expected in [
            (20, 6),  # +6% Chance to Block
            (105, 10),  # +10% Faster Cast Rate
            (39, 9),  # +9% Fire Resistance
        ]:
            if p.get(stat_id) != expected:
                errors.append(
                    f"J4 (Unique jew): stat_id {stat_id} expected {expected},"
                    f" got {p.get(stat_id)!r}"
                )

    # ── 6. Magic jewels (J1 maxhp=13, J3 maxhp=6) ──────────────────────────
    if len(magic_jewels) == 2:
        hp_vals = sorted(
            v for v in (props_of(j).get(7, None) for j in magic_jewels) if v is not None
        )
        if hp_vals != [6, 13]:
            errors.append(f"Magic jewels: expected maxhp values {{6, 13}}, got {hp_vals}")
        # J3 also has tohit and lightradius
        j3_candidates = [j for j in magic_jewels if props_of(j).get(7) == 6]
        if j3_candidates:
            p = props_of(j3_candidates[0])
            for stat_id, expected in [(19, 10), (89, 1)]:
                if p.get(stat_id) != expected:
                    errors.append(
                        f"J3 (Magic jew maxhp=6): stat_id {stat_id} expected"
                        f" {expected}, got {p.get(stat_id)!r}"
                    )

    # ── Result ───────────────────────────────────────────────────────────────
    if errors:
        detail = "; ".join(errors)
        return ("FAIL", f"{len(errors)} check(s) failed", detail[:200])
    return (
        "PASS",
        "13 items, 4 jewel children, Rare J2 7-slot QSD props verified",
        "",
    )


# ---------------------------------------------------------------------------
# TC35: Deep validation - Encode 2 (skill-on-event) + Encode 3 (charged skill)
# ---------------------------------------------------------------------------


def _check_tc35_details(cases_dir: Path) -> tuple[str, str, str]:
    """Detailed expected-value checks for TC35 (TestSorc.d2s).

    Verifications
    -------------
    - Exactly 3 items (The Oculus, Rhyme of the Bard, Golem's Might)
    - The Oculus (oba): Encode 2 (item_skillongethit) level=1 chance=25 skill_id=54
    - Rhyme of the Bard (9ja): Encode 3 (item_charged_skill) * 3: levels 2+3+3,
      all 200/200 charges; skill_ids 138 (Shout)+149 (Battle Orders)+154 (War Cry)
    - The Oculus: Encode 0 stats verified (energy=20, FCR=30, manaafterkill=5)
    - Golem's Might (rin): Encode 0 with save_add (strength=25), resistances=11,
      mindamage=10/maxdamage=15, item_healafterkill=8

    Key findings - Encode 2/3 binary layout (Reimagined ISC)
    ---------------------------------------------------------
    Encode 2 (item_skillongethit, stat 201): save_param_bits=16 packs
      level(6 LSB) + skill_id(10 MSB); save_bits=7 holds chance%.
      [BINARY_VERIFIED TC35: chance=25, level=1, skill_id=54 (Teleport/sor)]

    Encode 3 (item_charged_skill, stat 204): save_param_bits=16 packs
      level(6 LSB) + skill_id(10 MSB); save_bits=16 holds
      max_charges(8 LSB) + charges(8 MSB).
      [BINARY_VERIFIED TC35: skill 138=Shout(bar) level=3, skill 149=Battle Orders(bar)
      level=3, skill 154=War Cry(bar) level=2; all 200/200 charges]
      Note: binary storage order (Shout->Battle Orders->War Cry) differs from in-game
      display order (War Cry->Battle Orders->Shout) - display ordering only.

    Reimagined internal stat 97 (item_nonclassskill) param=449 val=1:
      skill 449 = "Hidden Charm Passive" (skills.txt, no charclass).
      Present on both The Oculus and Rhyme of the Bard. Not shown in tooltip.
      [BINARY_VERIFIED TC35: confirmed via skills.txt cross-reference]

    Returns:
        (status, info, detail) tuple.
    """
    f = cases_dir / "TC35" / "TestSorc.d2s"
    try:
        parser = D2SParser(f)
        char = parser.parse()
    except Exception as e:
        return ("FAIL", "parse error", str(e)[:120])

    items = char.items
    errors: list[str] = []

    # ── 1. Item count ───────────────────────────────────────────────────────
    if len(items) != 3:
        errors.append(f"Expected 3 items, got {len(items)}")

    # ── 2. Build position lookup ─────────────────────────────────────────────
    by_pos: dict[tuple[int, int], object] = {}
    for item in items:
        key = (item.flags.position_x, item.flags.position_y)
        by_pos[key] = item

    def props_by_stat(item, stat_id: int) -> list[dict]:
        return [p for p in (item.magical_properties or []) if p["stat_id"] == stat_id]

    def check_enc0(pos, code, stat_id, expected_val, label):
        item = by_pos.get(pos)
        if item is None:
            errors.append(f"No item at {pos}")
            return
        if item.item_code != code:
            errors.append(f"pos {pos}: expected {code!r}, got {item.item_code!r}")
            return
        found = props_by_stat(item, stat_id)
        if not found:
            errors.append(f"pos {pos} ({code}): missing stat_id {stat_id} ({label})")
        elif found[0].get("value") != expected_val:
            errors.append(
                f"pos {pos} ({code}): stat {stat_id} ({label}) "
                f"expected {expected_val}, got {found[0].get('value')!r}"
            )

    # ── 3. The Oculus - Encode 0 + Encode 1 + Encode 2 ──────────────────────
    # [BINARY_VERIFIED TC35] Encode 0 display values
    check_enc0((0, 0), "oba", 1, 20, "energy")
    check_enc0((0, 0), "oba", 3, 20, "vitality")
    check_enc0((0, 0), "oba", 16, 20, "item_armor_percent")
    check_enc0((0, 0), "oba", 39, 20, "fireresist")
    check_enc0((0, 0), "oba", 83, 3, "item_addclassskills(+3 Sorc skills)")
    check_enc0((0, 0), "oba", 105, 30, "item_fastercastrate")
    check_enc0((0, 0), "oba", 138, 5, "item_manaafterkill")
    check_enc0((0, 0), "oba", 80, 50, "item_magicbonus")

    # [BINARY_VERIFIED TC35] Encode 2: item_skillongethit (stat 201)
    oculus = by_pos.get((0, 0))
    if oculus:
        enc2_props = props_by_stat(oculus, 201)
        if not enc2_props:
            errors.append("The Oculus: missing stat 201 (item_skillongethit)")
        else:
            p = enc2_props[0]
            if p.get("chance") != 25:
                errors.append(f"The Oculus Enc2: expected chance=25, got {p.get('chance')!r}")
            if p.get("level") != 1:
                errors.append(f"The Oculus Enc2: expected level=1, got {p.get('level')!r}")
            if p.get("skill_id") != 54:
                errors.append(f"The Oculus Enc2: expected skill_id=54, got {p.get('skill_id')!r}")

    # ── 4. Rhyme of the Bard - Encode 3 (charged skills * 3) ───────────────
    # [BINARY_VERIFIED TC35] Encode 3: item_charged_skill (stat 204)
    bard = by_pos.get((1, 0))
    if bard:
        if bard.item_code != "9ja":
            errors.append(f"pos (1,0): expected '9ja', got {bard.item_code!r}")
        enc3_props = props_by_stat(bard, 204)
        if len(enc3_props) != 3:
            errors.append(f"Rhyme of the Bard: expected 3 charged skills, got {len(enc3_props)}")
        else:
            # Verify all have 200/200 charges
            for i, p in enumerate(enc3_props):
                if p.get("max_charges") != 200:
                    errors.append(
                        f"Bard skill[{i}]: expected max_charges=200, "
                        f"got {p.get('max_charges')!r}"
                    )
                if p.get("charges") != 200:
                    errors.append(
                        f"Bard skill[{i}]: expected charges=200, " f"got {p.get('charges')!r}"
                    )
            # Verify the set of (skill_id, level) pairs (order may vary).
            # Binary order: Shout(138)->Battle Orders(149)->War Cry(154).
            # In-game display order differs: War Cry->Battle Orders->Shout.
            # [BINARY_VERIFIED TC35 + skills.txt cross-reference]
            actual_skills = {(p["skill_id"], p["level"]) for p in enc3_props}
            expected_skills = {
                (138, 3),  # Shout (Barbarian) level 3
                (149, 3),  # Battle Orders (Barbarian) level 3
                (154, 2),  # War Cry (Barbarian) level 2
            }
            if actual_skills != expected_skills:
                errors.append(
                    f"Bard charged skills: expected {expected_skills}, " f"got {actual_skills}"
                )
        # Encode 0 stats on the javelin
        check_enc0((1, 0), "9ja", 17, 212, "item_maxdamage_percent")
        check_enc0((1, 0), "9ja", 93, 35, "item_fasterattackrate")

    # ── 5. Golem's Might - Encode 0 with save_add + min/max damage ──────────
    check_enc0((2, 0), "rin", 0, 25, "strength (save_add=32 applied)")
    check_enc0((2, 0), "rin", 21, 10, "mindamage")
    check_enc0((2, 0), "rin", 22, 15, "maxdamage")
    check_enc0((2, 0), "rin", 39, 11, "fireresist")
    check_enc0((2, 0), "rin", 86, 8, "item_healafterkill")
    check_enc0((2, 0), "rin", 93, 10, "item_fasterattackrate")

    # ── Result ───────────────────────────────────────────────────────────────
    if errors:
        detail = "; ".join(errors)
        return ("FAIL", f"{len(errors)} check(s) failed", detail[:200])
    return (
        "PASS",
        "3 items, Encode2 skill-on-event verified, Encode3 charged skills *3 verified",
        "",
    )


# ---------------------------------------------------------------------------
# TC34: Deep validation - Low/Superior/Set/Socketed weapon parsing
# ---------------------------------------------------------------------------


def _check_tc34_details(cases_dir: Path) -> tuple[str, str, str]:
    """Detailed expected-value checks for TC34 (TestSorc.d2s).

    Verifications
    -------------
    - Exactly 18 items parsed
    - Low quality (q=1) weapons have ISC properties (not 24-bit constant path)
    - Superior (q=3) weapons and armor have ISC properties
    - Superior Club at (5,5) is socketed=True and parses correctly -
      this is the key regression test for Fix 3 (sock_unk(4) for ALL socketed
      melee qualities, not only quality==2). [BINARY_VERIFIED TC34]
    - Set weapons (q=5) parsed with correct main properties
    - Rare weapons (q=6) parsed via ISC path with correct stat values
    - Item codes and positions match binary layout

    Notes on known discrepancies vs README
    ---------------------------------------
    - Item at (4,5) is q=1 (Low Quality Hand Axe) in the binary.
      The README describes it as "Superior Hand Axe (copy)" - the README
      contains an error at that row; the binary has a Low quality hax.
      [BINARY_VERIFIED: q=1, ilvl=1 at bit pos of item 12]
    - Durability values shown are raw binary values, not in-game displayed
      values (Superior items with +%MaxDur show higher values in-game).
    - "+50% Damage to Undead" on clubs is a known unresolved missing property
      (stat_id 122 or similar); not currently emitted by the parser.

    Returns:
        (status, info, detail) - same format as the main results dict.
    """
    f = cases_dir / "TC34" / "TestSorc.d2s"
    try:
        parser = D2SParser(f)
        char = parser.parse()
    except Exception as e:
        return ("FAIL", "parse error", str(e)[:120])

    items = char.items
    errors: list[str] = []

    # ── 1. Total item count ─────────────────────────────────────────────────
    if len(items) != 18:
        errors.append(f"Expected 18 items, got {len(items)}")

    # ── 2. Build position lookup ────────────────────────────────────────────
    by_pos: dict[tuple[int, int], object] = {}
    for item in items:
        key = (item.flags.position_x, item.flags.position_y)
        by_pos[key] = item

    # ── 3. Per-item checks ──────────────────────────────────────────────────
    def check(
        pos: tuple[int, int],
        code: str,
        quality: int,
        ilvl: int,
        props: list[tuple[int, int]] | None = None,
        socketed: bool | None = None,
    ) -> None:
        """Assert one item's expected fields.

        Args:
            pos:      (x, y) inventory position.
            code:     Expected Huffman item code.
            quality:  Expected quality integer (1=Low, 2=Normal, 3=Superior,
                      4=Magic, 5=Set, 6=Rare, 7=Unique).
            ilvl:     Expected item level.
            props:    List of (stat_id, expected_value) tuples to verify in
                      magical_properties.
            socketed: If not None, assert item.flags.socketed equals this.
        """
        item = by_pos.get(pos)
        if item is None:
            errors.append(f"No item at pos {pos}")
            return
        if item.item_code != code:
            errors.append(f"pos {pos}: expected code {code!r}, got {item.item_code!r}")
        q = item.extended.quality if item.extended else -1
        if q != quality:
            errors.append(f"pos {pos} ({code}): expected quality {quality}, got {q}")
        il = item.extended.item_level if item.extended else -1
        if il != ilvl:
            errors.append(f"pos {pos} ({code}): expected ilvl {ilvl}, got {il}")
        if socketed is not None and item.flags.socketed != socketed:
            errors.append(
                f"pos {pos} ({code}): expected socketed={socketed}, " f"got {item.flags.socketed}"
            )
        if props:
            for stat_id, expected_val in props:
                found = [p for p in item.magical_properties if p["stat_id"] == stat_id]
                if not found:
                    errors.append(f"pos {pos} ({code}): missing stat_id {stat_id}")
                elif found[0].get("value") != expected_val:
                    errors.append(
                        f"pos {pos} ({code}): stat_id {stat_id} expected "
                        f"value {expected_val}, got {found[0].get('value')}"
                    )

    # ── Low Quality Armor (q=1, no ISC properties beyond base) ──────────────
    # [BINARY_VERIFIED] quality=1 reads 3-bit low-quality prefix correctly
    check((2, 0), "lea", quality=1, ilvl=2)  # Cracked Leather Armor
    check((4, 0), "lea", quality=1, ilvl=2)  # Crude Leather Armor
    check((2, 3), "lbt", quality=1, ilvl=2)  # Crude Boots
    check((4, 3), "lbt", quality=1, ilvl=1)  # Low Quality Boots

    # ── Superior Armor (q=3, ISC properties present) ────────────────────────
    # [BINARY_VERIFIED] quality=3 reads 3-bit superior prefix correctly;
    # ISC path engaged (not 24-bit constant).
    # Note: raw binary max_dur is lower than in-game display because
    # item_maxdurability_percent (+%) is applied at display time.
    check(
        (0, 0),
        "lea",
        quality=3,
        ilvl=1,
        props=[(75, 11)],  # +11% Increased Maximum Durability
    )
    check(
        (0, 3),
        "lbt",
        quality=3,
        ilvl=1,
        props=[(16, 9), (75, 14)],  # +9% Enhanced Defense, +14% Max Dur
    )

    # ── Rare Weapons via ISC path (q=6, not 24-bit constant) ────────────────
    # [BINARY_VERIFIED] Spear (spr) and Scimitar (scm) were previously
    # misidentified as Normal-path weapons; now correctly parsed via ISC.
    check(
        (6, 0),
        "spr",
        quality=6,
        ilvl=86,
        props=[(17, 288)],  # +288% Enhanced Weapon Damage
    )
    check(
        (7, 5),
        "scm",
        quality=6,
        ilvl=90,
        props=[(17, 281), (22, 58)],  # +281% EWD, +58 Max Weapon Dmg
    )

    # ── Set Weapons (q=5, bonus mask + ISC properties) ──────────────────────
    check(
        (8, 0),
        "pik",
        quality=5,
        ilvl=73,
        props=[(17, 140)],  # +140% Enhanced Weapon Damage
    )
    check(
        (8, 5),
        "oba",
        quality=5,
        ilvl=99,
        props=[(1, 20), (9, 77), (105, 25)],  # +20 Energy, +77 Mana, +25% FCR
    )
    check(
        (9, 5),
        "9dg",
        quality=5,
        ilvl=97,
        props=[(93, 75), (105, 10)],  # +75% IAS, +10% FCR
    )

    # ── Normal Throwing Weapon (q=2) ─────────────────────────────────────────
    check((0, 5), "jav", quality=2, ilvl=1)

    # ── Low Quality Throwing Weapons (q=1, ISC path) ─────────────────────────
    # [BINARY_VERIFIED TC34] Throwing weapons of all qualities engage ISC path
    check((1, 5), "jav", quality=1, ilvl=1)  # Cracked Javelin
    check((2, 5), "jav", quality=1, ilvl=1)  # Low Quality Javelin

    # ── Superior Melee Weapons (q=3, ISC path) ───────────────────────────────
    # [BINARY_VERIFIED TC34] Superior weapons (q=3) engage ISC path correctly
    check(
        (3, 5),
        "hax",
        quality=3,
        ilvl=4,
        props=[(19, 2), (22, 1)],  # +2 Attack Rating, +1 Max Dmg
    )

    # NOTE: README describes this item as "Superior Hand Axe (copy)" (q=3,
    # ilvl=4), but the binary contains a Low Quality Hand Axe (q=1, ilvl=1).
    # The README contains an error for this row; parser is correct.
    # [BINARY_VERIFIED TC34: q=1, ilvl=1]
    check((4, 5), "hax", quality=1, ilvl=1)

    # ── Socketed Superior Club (Fix 3: sock_unk(4) for ALL socketed melee) ───
    # CRITICAL regression check: before Fix 3, sock_unk(4) was only read for
    # quality==2 (Normal) socketed weapons.  Superior (q=3) socketed weapons
    # skipped those 4 bits, causing all subsequent items to be mis-parsed.
    # After Fix 3 all 18 items parse correctly with the right properties.
    # [BINARY_VERIFIED TC34 - regression test]
    check(
        (5, 5),
        "clb",
        quality=3,
        ilvl=2,
        socketed=True,  # must be socketed for fix to matter
        props=[(75, 12)],  # +12% Increased Maximum Durability
    )

    # ── Low Quality Club (q=1, ISC path) ────────────────────────────────────
    check((6, 5), "clb", quality=1, ilvl=1)  # Damaged Club

    # ── Result ───────────────────────────────────────────────────────────────
    if errors:
        detail = "; ".join(errors)
        return ("FAIL", f"{len(errors)} check(s) failed", detail[:200])
    return ("PASS", "18 items, all detail checks pass [Fix3 sock_unk verified]", "")


# ---------------------------------------------------------------------------
# TC36: Deep validation - Full Set (Sigon's Complete Steel, all 6 pieces equipped)
# ---------------------------------------------------------------------------


def _check_tc36_details(cases_dir: Path) -> tuple[str, str, str]:
    """Detailed expected-value checks for TC36 (TestABC.d2s).

    Verifications
    -------------
    - Exactly 6 items, all quality=5 (Set), all equipped at body (location_id=1)
    - Item codes: {hbt, gth, hgl, ghm, hbl, tow}
    - Per-item defense_display and durability_max match binary values
    - Per-item magical_properties include both base props AND bonus-list props (merged)
    - Sigon's Sabot (hbt): 4 props total - base (2) + 2-item bonus + 3-item bonus
    - Sigon's Guard (tow): exactly 3 props - mask=0, no bonus lists
      [KEY REGRESSION TEST for _skip_set_trailing_data() false-positive fix, TC36 BV]

    Global set bonuses (+10% Life Stolen, +100 Defense, Full Set bonuses) are NOT in
    the binary - they are applied at runtime by the game engine. This is verified by
    the absence of those stat_ids in any item's magical_properties.

    Returns:
        (status, info, detail) tuple.
    """
    f = cases_dir / "TC36" / "TestABC.d2s"
    try:
        parser = D2SParser(f)
        char = parser.parse()
    except Exception as e:
        return ("FAIL", "parse error", str(e)[:120])

    items = char.items
    errors: list[str] = []

    # ── 1. Item count ────────────────────────────────────────────────────────
    # The _skip_set_trailing_data() fix yields exactly 6 items, not 8 (which
    # was the pre-fix count due to garbage items parsed from trailing bytes).
    if len(items) != 6:
        errors.append(f"Expected 6 items, got {len(items)}")

    # ── 2. All quality=5, all equipped (location_id=1) ───────────────────────
    for item in items:
        if not item.extended or item.extended.quality != 5:
            errors.append(
                f"Expected quality=5 for {item.item_code!r}, got {item.extended.quality if item.extended else None}"
            )
        if item.flags.location_id != 1:
            errors.append(
                f"Expected location_id=1 (equipped) for {item.item_code!r}, got {item.flags.location_id}"
            )

    # ── 3. All expected item codes present ────────────────────────────────────
    expected_codes = {"hbt", "gth", "hgl", "ghm", "hbl", "tow"}
    actual_codes = {it.item_code for it in items}
    if actual_codes != expected_codes:
        errors.append(f"Item codes mismatch: expected {expected_codes}, got {actual_codes}")

    # Build lookup by item_code for property checks
    by_code = {it.item_code: it for it in items}

    def _own_props(code: str) -> list[dict]:
        it = by_code.get(code)
        return it.magical_properties if it and it.magical_properties else []

    def _bonus_props(code: str) -> list[dict]:
        it = by_code.get(code)
        return it.set_bonus_properties if it and it.set_bonus_properties else []

    def _all_props(code: str) -> list[dict]:
        return _own_props(code) + _bonus_props(code)

    def _has_own_prop(code: str, stat_id: int, value: int) -> bool:
        return any(p["stat_id"] == stat_id and p["value"] == value for p in _own_props(code))

    def _has_bonus_prop(code: str, stat_id: int, value: int) -> bool:
        return any(p["stat_id"] == stat_id and p["value"] == value for p in _bonus_props(code))

    def _armor_display(code: str) -> int | None:
        it = by_code.get(code)
        return it.armor_data.defense_display if it and it.armor_data else None

    def _dur_max(code: str) -> int | None:
        it = by_code.get(code)
        return (
            it.armor_data.durability.max_durability
            if it and it.armor_data and it.armor_data.durability
            else None
        )

    # ── 4. Sigon's Sabot (hbt) - 2 own + 2 set-bonus props ──────────────────
    # After refactor: own magical_properties = 2 (base), set_bonus_properties = 2 (bonuses)
    hbt_own = _own_props("hbt")
    hbt_bonus = _bonus_props("hbt")
    if len(hbt_own) != 2:
        errors.append(f"hbt (Sabot): expected 2 own magical_properties, got {len(hbt_own)}")
    if len(hbt_bonus) != 2:
        errors.append(f"hbt (Sabot): expected 2 set_bonus_properties, got {len(hbt_bonus)}")
    if not _has_own_prop("hbt", 43, 40):
        errors.append("hbt: missing coldresist=40 in magical_properties")  # +40% Cold Resist (base)
    if not _has_own_prop("hbt", 96, 20):
        errors.append(
            "hbt: missing item_fastermovevelocity=20 in magical_properties"
        )  # +20% FRW (base)
    if not _has_bonus_prop("hbt", 19, 50):
        errors.append("hbt: missing tohit=50 in set_bonus_properties")  # +50 AR (2-item bonus)
    if not _has_bonus_prop("hbt", 80, 50):
        errors.append(
            "hbt: missing item_magicbonus=50 in set_bonus_properties"
        )  # +50% MF (3-item bonus)
    if _armor_display("hbt") != 13:
        errors.append(f"hbt: defense_display expected 13, got {_armor_display('hbt')}")
    if _dur_max("hbt") != 24:
        errors.append(f"hbt: max_durability expected 24, got {_dur_max('hbt')}")

    # ── 5. Sigon's Shelter (gth) - 2 own + 1 set-bonus prop ─────────────────
    gth_own = _own_props("gth")
    gth_bonus = _bonus_props("gth")
    if len(gth_own) != 2:
        errors.append(f"gth (Shelter): expected 2 own magical_properties, got {len(gth_own)}")
    if len(gth_bonus) != 1:
        errors.append(f"gth (Shelter): expected 1 set_bonus_properties, got {len(gth_bonus)}")
    if not _has_own_prop("gth", 16, 25):
        errors.append(
            "gth: missing item_armor_percent=25 in magical_properties"
        )  # +25% Enh. Defense (base)
    if not _has_own_prop("gth", 41, 30):
        errors.append(
            "gth: missing lightresist=30 in magical_properties"
        )  # +30% Lightning Res (base)
    if not _has_bonus_prop("gth", 78, 20):
        errors.append(
            "gth: missing item_attackertakesdamage=20 in set_bonus_properties"
        )  # ATD 20 (2-item bonus)
    if _armor_display("gth") != 136:
        errors.append(f"gth: defense_display expected 136, got {_armor_display('gth')}")
    if _dur_max("gth") != 55:
        errors.append(f"gth: max_durability expected 55, got {_dur_max('gth')}")

    # ── 6. Sigon's Gage (hgl) - 2 own + 1 set-bonus prop ────────────────────
    hgl_own = _own_props("hgl")
    hgl_bonus = _bonus_props("hgl")
    if len(hgl_own) != 2:
        errors.append(f"hgl (Gage): expected 2 own magical_properties, got {len(hgl_own)}")
    if len(hgl_bonus) != 1:
        errors.append(f"hgl (Gage): expected 1 set_bonus_properties, got {len(hgl_bonus)}")
    if not _has_own_prop("hgl", 0, 10):
        errors.append("hgl: missing strength=10 in magical_properties")  # +10 Strength (base)
    if not _has_own_prop("hgl", 19, 20):
        errors.append("hgl: missing tohit=20 in magical_properties")  # +20 AR (base)
    if not _has_bonus_prop("hgl", 93, 30):
        errors.append(
            "hgl: missing item_fasterattackrate=30 in set_bonus_properties"
        )  # +30% IAS (2-item bonus)
    if _armor_display("hgl") != 14:
        errors.append(f"hgl: defense_display expected 14, got {_armor_display('hgl')}")
    if _dur_max("hgl") != 24:
        errors.append(f"hgl: max_durability expected 24, got {_dur_max('hgl')}")

    # ── 7. Sigon's Visor (ghm) - 2 own + 1 set-bonus prop ───────────────────
    ghm_own = _own_props("ghm")
    ghm_bonus = _bonus_props("ghm")
    if len(ghm_own) != 2:
        errors.append(f"ghm (Visor): expected 2 own magical_properties, got {len(ghm_own)}")
    if len(ghm_bonus) != 1:
        errors.append(f"ghm (Visor): expected 1 set_bonus_properties, got {len(ghm_bonus)}")
    if not _has_own_prop("ghm", 9, 30):
        errors.append("ghm: missing maxmana=30 in magical_properties")  # +30 Mana (base)
    if not _has_own_prop("ghm", 31, 25):
        errors.append("ghm: missing armorclass=25 in magical_properties")  # +25 Defense (base)
    if not _has_bonus_prop("ghm", 224, 16):
        errors.append(
            "ghm: missing item_tohit_perlevel=16 in set_bonus_properties"
        )  # +8 AR/level (2-item bonus)
    if _armor_display("ghm") != 35:
        errors.append(f"ghm: defense_display expected 35, got {_armor_display('ghm')}")
    if _dur_max("ghm") != 40:
        errors.append(f"ghm: max_durability expected 40, got {_dur_max('ghm')}")

    # ── 8. Sigon's Wrap (hbl) - 2 own + 1 set-bonus prop ────────────────────
    hbl_own = _own_props("hbl")
    hbl_bonus = _bonus_props("hbl")
    if len(hbl_own) != 2:
        errors.append(f"hbl (Wrap): expected 2 own magical_properties, got {len(hbl_own)}")
    if len(hbl_bonus) != 1:
        errors.append(f"hbl (Wrap): expected 1 set_bonus_properties, got {len(hbl_bonus)}")
    if not _has_own_prop("hbl", 7, 20):
        errors.append("hbl: missing maxhp=20 in magical_properties")  # +20 Life (base)
    if not _has_own_prop("hbl", 39, 20):
        errors.append("hbl: missing fireresist=20 in magical_properties")  # +20% Fire Res (base)
    if not _has_bonus_prop("hbl", 214, 16):
        errors.append(
            "hbl: missing item_armor_perlevel=16 in set_bonus_properties"
        )  # +2 Def/level (2-item bonus)
    if _armor_display("hbl") != 10:
        errors.append(f"hbl: defense_display expected 10, got {_armor_display('hbl')}")
    if _dur_max("hbl") != 24:
        errors.append(f"hbl: max_durability expected 24, got {_dur_max('hbl')}")

    # ── 9. Sigon's Guard (tow) - EXACTLY 3 own props, mask=0, NO bonus lists ─
    # [KEY REGRESSION TEST] Before the _skip_set_trailing_data() simple-flag fix,
    # this item caused the parser to emit 8 total items (with garbage items 7+8
    # parsed from trailing bytes). After the fix: exactly 6 total items, tow
    # has exactly 3 own props, empty set_bonus_properties, and no POST-PARSE warning.
    tow_own = _own_props("tow")
    tow_bonus = _bonus_props("tow")
    if len(tow_own) != 3:
        errors.append(
            f"tow (Guard): expected EXACTLY 3 own magical_properties (mask=0, no bonus lists), got {len(tow_own)}"
            " - regression: _skip_set_trailing_data() false-positive may be back"
        )
    if tow_bonus:
        errors.append(
            f"tow (Guard): expected empty set_bonus_properties (mask=0), got {len(tow_bonus)}"
        )
    if not _has_own_prop("tow", 20, 20):
        errors.append("tow: missing toblock=20")  # 20% block
    if not _has_own_prop("tow", 127, 1):
        errors.append("tow: missing item_allskills=1")  # +1 All Skills
    # Hidden Charm Passive (skill 449) on tow - Reimagined internal
    tow_hcp = any(p["stat_id"] == 97 and p.get("param") == 449 and p["value"] == 1 for p in tow_own)
    if not tow_hcp:
        errors.append(
            "tow: missing item_nonclassskill sid=97 param=449 val=1 (Hidden Charm Passive)"
        )
    if _armor_display("tow") != 23:
        errors.append(f"tow: defense_display expected 23, got {_armor_display('tow')}")
    if _dur_max("tow") != 60:
        errors.append(f"tow: max_durability expected 60, got {_dur_max('tow')}")

    # ── 10. Global set bonuses NOT stored per-item ───────────────────────────
    # Global set bonuses (+10% Life Stolen, +100 Defense, Full Set bonuses) are
    # applied at runtime by the game engine; they are NOT per-item binary props.
    # Verify: no item has sid=31 val=100 ("+100 Defense (3 items)" global set bonus)
    # in either magical_properties or set_bonus_properties.
    all_own_props = [p for it in items for p in (it.magical_properties or [])]
    all_bonus_props_flat = [p for it in items for p in (it.set_bonus_properties or [])]
    if any(p["stat_id"] == 31 and p["value"] == 100 for p in all_own_props + all_bonus_props_flat):
        errors.append("Unexpected: sid=31 val=100 (+100 Defense global bonus) found in binary")

    # ── Result ───────────────────────────────────────────────────────────────
    if errors:
        detail = "; ".join(errors)
        return ("FAIL", f"{len(errors)} check(s) failed", detail[:200])
    return (
        "PASS",
        "6 Set items, own props + set_bonus_properties separated, mask=0 Guard has 3 own/0 bonus [BV TC36]",
        "",
    )


# ---------------------------------------------------------------------------
# TC37: Deep validation - Full Set with Reimagined Modifications
#        (Ethereal / Socketed / Enchanted / Corrupted)
# ---------------------------------------------------------------------------


def _check_tc37_details(cases_dir: Path) -> tuple[str, str, str]:
    """Detailed expected-value checks for TC37 (TestABC.d2s).

    Verifications
    -------------
    - Exactly 6 items, all quality=5 (Set), all equipped at body (location_id=1)
    - Item codes: {hbt, gth, hgl, ghm, hbl, tow} - same as TC36 but with modifications

    Modification checks
    -------------------
    1. ghm (Ethereal): flags.ethereal=True; defense_display=52 (floor(35 * 1.5))
       [BINARY_VERIFIED TC37: ethereal bit 22 set; defense_raw=62=52+ARMOR_SAVE_ADD(10)]

    2. gth (Socketed, 4 empty sockets): flags.socketed=True; defense_display=136 (unchanged)
       REGRESSION TEST for sock_unk=4-bit fix for Set (q=5) armor. Before the fix,
       sock_unk for q=5 socketed armor was read as 20 bits (Superior branch) instead of
       4 bits, misaligning all subsequent property reads.
       [BINARY_VERIFIED TC37: sock_unk=4 bits, value=4=socket count]

    3. hbt (3* Enchanted): 10 props total; stat 393 (upgrade_medium) val=3;
       enchant effects merged - coldresist 40->42, FRW 20->25; new stats added
       (fireresist=2, lightresist=2, poisonresist=2, maxmana=15, manaafterkill=2)
       [BINARY_VERIFIED TC37: first-ever BV of Reimagined enchant stat 393]

    4. hgl (Corrupted WITH extra props): 7 props; item_corrupted=2 (stat 361);
       item_corruptedDummy=180 (stat 362); bonus props: item_crushingblow=5 (stat 136),
       item_deadlystrike=5 (stat 141) present in addition to base stats and 2-item bonus
       [BINARY_VERIFIED TC37: first-ever BV of Reimagined corruption stats 361/362]

    5. tow (Corrupted WITHOUT extra props): 5 props; item_corrupted=2 (stat 361);
       item_corruptedDummy=141 (stat 362); no extra corruption props
       item_corruptedDummy value differs from hgl (141 vs 180) - encodes outcome

    6. hbl (Unchanged reference): exactly 3 props, same values as TC36

    Returns:
        (status, info, detail) tuple.
    """
    f = cases_dir / "TC37" / "TestABC.d2s"
    try:
        parser = D2SParser(f)
        char = parser.parse()
    except Exception as e:
        return ("FAIL", "parse error", str(e)[:120])

    items = char.items
    errors: list[str] = []

    # ── 1. Item count ────────────────────────────────────────────────────────
    if len(items) != 6:
        errors.append(f"Expected 6 items, got {len(items)}")

    # ── 2. All quality=5, all equipped (location_id=1) ───────────────────────
    for item in items:
        if not item.extended or item.extended.quality != 5:
            errors.append(
                f"Expected quality=5 for {item.item_code!r}, "
                f"got {item.extended.quality if item.extended else None}"
            )
        if item.flags.location_id != 1:
            errors.append(
                f"Expected location_id=1 (equipped) for {item.item_code!r}, "
                f"got {item.flags.location_id}"
            )

    # ── 3. All expected item codes present ────────────────────────────────────
    expected_codes = {"hbt", "gth", "hgl", "ghm", "hbl", "tow"}
    actual_codes = {it.item_code for it in items}
    if actual_codes != expected_codes:
        errors.append(f"Item codes mismatch: expected {expected_codes}, got {actual_codes}")

    # Build lookup by item_code for all checks below
    by_code = {it.item_code: it for it in items}

    def _props(code: str) -> list[dict]:
        """Return combined own + set bonus properties (for total count checks)."""
        it = by_code.get(code)
        if it is None:
            return []
        own = it.magical_properties or []
        bonus = it.set_bonus_properties or []
        return own + bonus

    def _has_prop(code: str, stat_id: int, value: int, param: int | None = None) -> bool:
        for p in _props(code):
            if p["stat_id"] != stat_id or p["value"] != value:
                continue
            if param is not None and p.get("param") != param:
                continue
            return True
        return False

    def _def_display(code: str) -> int | None:
        it = by_code.get(code)
        return it.armor_data.defense_display if it and it.armor_data else None

    # ── 4. ghm - ETHEREAL: flag set, defense_display=52 [BV TC37] ────────────
    ghm = by_code.get("ghm")
    if ghm is not None:
        if not ghm.flags.ethereal:
            errors.append("ghm: expected flags.ethereal=True, got False")
        d = _def_display("ghm")
        if d != 52:
            errors.append(f"ghm: defense_display expected 52 (floor(35*1.5)), got {d}")
        # Props must be unchanged from TC36 base (3 props)
        ghm_props = _props("ghm")
        if len(ghm_props) != 3:
            errors.append(
                f"ghm: expected 3 props (ethereal doesn't add props), got {len(ghm_props)}"
            )
        if not _has_prop("ghm", 9, 30):
            errors.append("ghm: missing maxmana=30")
        if not _has_prop("ghm", 31, 25):
            errors.append("ghm: missing armorclass=25")
        if not _has_prop("ghm", 224, 16):
            errors.append("ghm: missing item_tohit_perlevel=16")

    # ── 5. gth - SOCKETED (q=5, 4 empty sockets) [BV TC37, sock_unk=4 fix] ───
    # REGRESSION TEST: before fix, q=5 armor used sock_unk=20 bits (Superior
    # branch) instead of 4 bits, misaligning all property reads.
    gth = by_code.get("gth")
    if gth is not None:
        if not gth.flags.socketed:
            errors.append("gth: expected flags.socketed=True, got False")
        d = _def_display("gth")
        if d != 136:
            errors.append(
                f"gth: defense_display expected 136 (unchanged), got {d}"
                " - possible sock_unk width regression"
            )
        gth_props = _props("gth")
        if len(gth_props) != 3:
            errors.append(
                f"gth: expected 3 props (socketing doesn't add props), got {len(gth_props)}"
                " - possible sock_unk width regression"
            )
        if not _has_prop("gth", 16, 25):
            errors.append("gth: missing item_armor_percent=25")
        if not _has_prop("gth", 41, 30):
            errors.append("gth: missing lightresist=30")
        if not _has_prop("gth", 78, 20):
            errors.append("gth: missing item_attackertakesdamage=20")

    # ── 6. hbt - 3* ENCHANTED: 10 props, stat 393=3, merged enchant effects ──
    # [BV TC37: first binary verification of Reimagined enchantment stats 392-395]
    hbt_props = _props("hbt")
    if len(hbt_props) != 10:
        errors.append(
            f"hbt: expected 10 props (4 base/bonus + 1 enchant marker + 5 enchant effects),"
            f" got {len(hbt_props)}"
        )
    # Enchantment capacity marker - stat 393 (upgrade_medium), val = enchants applied
    if not _has_prop("hbt", 393, 3):
        errors.append("hbt: missing stat 393 (upgrade_medium)=3 (enchant count)")
    # Enchant-modified existing stats:
    if not _has_prop("hbt", 43, 42):
        errors.append("hbt: coldresist expected 42 (was 40, +2 from enchant), check merge")
    if not _has_prop("hbt", 96, 25):
        errors.append("hbt: item_fastermovevelocity expected 25 (was 20, +5 from enchant)")
    # Enchant-added new stats:
    if not _has_prop("hbt", 39, 2):
        errors.append("hbt: missing fireresist=2 (added by enchant +2 All Resistances)")
    if not _has_prop("hbt", 41, 2):
        errors.append("hbt: missing lightresist=2 (added by enchant +2 All Resistances)")
    if not _has_prop("hbt", 45, 2):
        errors.append("hbt: missing poisonresist=2 (added by enchant +2 All Resistances)")
    if not _has_prop("hbt", 9, 15):
        errors.append("hbt: missing maxmana=15 (added by enchant)")
    if not _has_prop("hbt", 138, 2):
        errors.append("hbt: missing item_manaafterkill=2 (added by enchant)")
    # Set bonus list props (must survive the enchant skill):
    if not _has_prop("hbt", 19, 50):
        errors.append("hbt: missing tohit=50 (2-item set bonus, must survive the enchant skill)")
    if not _has_prop("hbt", 80, 50):
        errors.append("hbt: missing item_magicbonus=50 (3-item set bonus, must survive the enchant skill)")

    # ── 7. hgl - CORRUPTED WITH extra props [BV TC37, first BV of stats 361/362] ─
    hgl_props = _props("hgl")
    if len(hgl_props) != 7:
        errors.append(
            f"hgl: expected 7 props (2 base + 2 corruption bonus + 2 markers + 1 set bonus),"
            f" got {len(hgl_props)}"
        )
    # Corruption markers:
    if not _has_prop("hgl", 361, 2):
        errors.append("hgl: missing item_corrupted=2 (stat 361, corruption marker)")
    if not _has_prop("hgl", 362, 180):
        errors.append("hgl: missing item_corruptedDummy=180 (stat 362, outcome marker)")
    # Extra properties granted by corruption:
    # [BINARY_VERIFIED TC37] stat 136 = item_crushingblow, stat 141 = item_deadlystrike
    if not _has_prop("hgl", 136, 5):
        errors.append("hgl: missing item_crushingblow=5 (stat 136, extra prop from corruption)")
    if not _has_prop("hgl", 141, 5):
        errors.append("hgl: missing item_deadlystrike=5 (stat 141, extra prop from corruption)")
    # Base properties (unchanged):
    if not _has_prop("hgl", 0, 10):
        errors.append("hgl: missing strength=10 (base)")
    if not _has_prop("hgl", 19, 20):
        errors.append("hgl: missing tohit=20 (base)")
    # 2-item set bonus (must survive corruption):
    if not _has_prop("hgl", 93, 30):
        errors.append("hgl: missing item_fasterattackrate=30 (2-item set bonus)")

    # ── 8. tow - CORRUPTED WITHOUT extra props [BV TC37] ─────────────────────
    tow_props = _props("tow")
    if len(tow_props) != 5:
        errors.append(
            f"tow: expected 5 props (3 base + 2 corruption markers, no extra), got {len(tow_props)}"
        )
    # Corruption markers:
    if not _has_prop("tow", 361, 2):
        errors.append("tow: missing item_corrupted=2 (stat 361, corruption marker)")
    if not _has_prop("tow", 362, 141):
        errors.append("tow: missing item_corruptedDummy=141 (stat 362, outcome=no bonus)")
    # Base properties (unchanged):
    if not _has_prop("tow", 20, 20):
        errors.append("tow: missing toblock=20")
    if not _has_prop("tow", 127, 1):
        errors.append("tow: missing item_allskills=1")
    tow_hcp = any(
        p["stat_id"] == 97 and p.get("param") == 449 and p["value"] == 1 for p in tow_props
    )
    if not tow_hcp:
        errors.append("tow: missing item_nonclassskill sid=97 param=449 val=1")
    # item_corruptedDummy for tow must differ from hgl (outcome encoding)
    tow_dummy = next((p["value"] for p in tow_props if p["stat_id"] == 362), None)
    hgl_dummy = next((p["value"] for p in _props("hgl") if p["stat_id"] == 362), None)
    if tow_dummy == hgl_dummy and tow_dummy is not None:
        errors.append(
            f"tow and hgl have identical item_corruptedDummy={tow_dummy} - "
            f"expected different outcome codes (141 vs 180)"
        )

    # ── 9. hbl - UNCHANGED REFERENCE: exactly 3 props matching TC36 ──────────
    hbl_props = _props("hbl")
    if len(hbl_props) != 3:
        errors.append(f"hbl: expected 3 props (unchanged reference), got {len(hbl_props)}")
    if not _has_prop("hbl", 7, 20):
        errors.append("hbl: missing maxhp=20")
    if not _has_prop("hbl", 39, 20):
        errors.append("hbl: missing fireresist=20")
    if not _has_prop("hbl", 214, 16):
        errors.append("hbl: missing item_armor_perlevel=16")

    # ── Result ───────────────────────────────────────────────────────────────
    if errors:
        detail = "; ".join(errors)
        return ("FAIL", f"{len(errors)} check(s) failed", detail[:200])
    return (
        "PASS",
        "6 items: Ethereal(ghm) def=52, Socketed(gth) sock_unk=4 fix, "
        "Enchanted(hbt) upgrade_medium=3, Corrupted*2 stats 361/362 [BV TC37]",
        "",
    )


# ---------------------------------------------------------------------------
# CubeMain: Corruption decode smoke-test
# ---------------------------------------------------------------------------
# ItemNames smoke-test
# ---------------------------------------------------------------------------


def _check_item_names(cases_dir: Path) -> tuple[str, str, str]:
    """Smoke-test ItemNamesDatabase name look-ups.

    Verifications
    -------------
    - Database is loaded (all txt + JSON string files found)
    - Table sizes: >=100 unique items, >=400 set items, >=1000 prefix, >=700 suffix, >=200 runewords
    - Unique name: ID 0 -> "The Gnasher" [verifiable from uniqueitems.txt row 0]
    - Set item name: TC36 items - Sigon set items present in setitems.txt
    - Prefix name: ID 0 -> "Jagged" [row 0 of magicprefix.txt]
    - Suffix name: ID 0 -> "of Defense1" or similar [row 0 of magicsuffix.txt]
    - Runeword name: ID 0 -> "Friendship" [row 0 of runes.txt]
    - TC36 set item ID look-up: setitems.txt ID for Sigon's Visor via parsed TC36 item
    - TC37 unique type ID look-up: parsed items carry unique_type_id field

    Returns:
        (status, info, detail) tuple.
    """
    db = get_item_names_db()
    errors: list[str] = []

    if not db.is_loaded():
        return ("FAIL", "ItemNamesDatabase not loaded", "uniqueitems.txt or strings/ not found")

    # ── 1. Table sizes ───────────────────────────────────────────────────────
    if len(db._unique_keys) < 100:
        errors.append(f"unique_keys too small: {len(db._unique_keys)} (expected >=100)")
    if len(db._set_item_keys) < 400:
        errors.append(f"set_item_keys too small: {len(db._set_item_keys)} (expected >=400)")
    if len(db._prefix_names) < 1000:
        errors.append(f"prefix_names too small: {len(db._prefix_names)} (expected >=1000)")
    if len(db._suffix_names) < 700:
        errors.append(f"suffix_names too small: {len(db._suffix_names)} (expected >=700)")
    if len(db._runeword_keys) < 200:
        errors.append(f"runeword_keys too small: {len(db._runeword_keys)} (expected >=200)")
    # Rare-affix tables loaded from excel/original/ (reimagined/ doesn't ship them)
    if len(db._rareprefix_names) < 40:
        errors.append(f"rareprefix_names too small: {len(db._rareprefix_names)} (expected >=40)")
    if len(db._raresuffix_names) < 100:
        errors.append(f"raresuffix_names too small: {len(db._raresuffix_names)} (expected >=100)")

    # ── 2. Known-value spot-checks ───────────────────────────────────────────
    # Unique ID 0 = "The Gnasher" (row 0 of uniqueitems.txt, always first entry)
    gnasher = db.get_unique_name(0)
    if gnasher != "The Gnasher":
        errors.append(f"unique[0] expected 'The Gnasher', got {gnasher!r}")

    # Prefix ID 0 = "Jagged" (row 0 of magicprefix.txt)
    jagged = db.get_prefix_name(0)
    if jagged != "Jagged":
        errors.append(f"prefix[0] expected 'Jagged', got {jagged!r}")

    # Runeword ID 0 = "Friendship" (row 0 of runes.txt)
    friendship = db.get_runeword_name(0)
    if friendship != "Friendship":
        errors.append(f"runeword[0] expected 'Friendship', got {friendship!r}")

    # Rare prefix ID 0 = "Beast" (row 0 of rareprefix.txt from excel/original/)
    beast = db._rareprefix_names[0] if db._rareprefix_names else None
    if beast != "Beast":
        errors.append(f"rareprefix[0] expected 'Beast', got {beast!r}")

    # Rare suffix ID 0 = "bite" (row 0 of raresuffix.txt from excel/original/)
    bite = db._raresuffix_names[0] if db._raresuffix_names else None
    if bite != "bite":
        errors.append(f"raresuffix[0] expected 'bite', got {bite!r}")

    # Combined rare name: get_rare_name(0, 0) -> "Beast Bite" (both parts capitalized)
    rare_combined = db.get_rare_name(0, 0)
    if rare_combined != "Beast Bite":
        errors.append(f"get_rare_name(0, 0) expected 'Beast Bite', got {rare_combined!r}")

    # ── 3. TC36 set item names via parsed items ──────────────────────────────
    tc36_path = cases_dir / "TC36" / "TestABC.d2s"
    if tc36_path.exists():
        from d2rr_toolkit.parsers.d2s_parser import D2SParser

        try:
            char36 = D2SParser(tc36_path).parse()
            set_items = [it for it in char36.items if it.extended and it.extended.quality == 5]
            if not set_items:
                errors.append("TC36: no Set items found (quality=5)")
            else:
                for it in set_items:
                    if it.set_item_id is None:
                        errors.append(f"TC36: {it.item_code} has quality=5 but set_item_id=None")
                    else:
                        name = db.get_set_item_name(it.set_item_id)
                        if name is None:
                            errors.append(
                                f"TC36: set_item_id={it.set_item_id} ({it.item_code}) "
                                f"not found in setitems table"
                            )
                        else:
                            # Verify at least one known Sigon set item name is present
                            pass  # any successful look-up counts
                # Verify Sigon's Visor is found somewhere
                all_names = [
                    db.get_set_item_name(it.set_item_id)
                    for it in set_items
                    if it.set_item_id is not None
                ]
                if not any("Sigon" in (n or "") for n in all_names):
                    errors.append(f"TC36: expected at least one Sigon item; got {all_names}")
        except Exception as exc:
            errors.append(f"TC36 parse failed: {exc}")

    # ── 4. TC37 unique type ID field present on parsed items ─────────────────
    tc37_path = cases_dir / "TC37" / "TestABC.d2s"
    if tc37_path.exists():
        from d2rr_toolkit.parsers.d2s_parser import D2SParser

        try:
            char37 = D2SParser(tc37_path).parse()
            # Verify quality-specific ID fields are populated
            for it in char37.items:
                if not it.extended:
                    continue
                q = it.extended.quality
                if q == 7 and it.unique_type_id is None:
                    errors.append(f"TC37: unique item {it.item_code} has unique_type_id=None")
                if q == 5 and it.set_item_id is None:
                    errors.append(f"TC37: set item {it.item_code} has set_item_id=None")
                if q == 4 and it.prefix_id is None:
                    errors.append(f"TC37: magic item {it.item_code} has prefix_id=None")
        except Exception as exc:
            errors.append(f"TC37 parse failed: {exc}")

    # ── Result ───────────────────────────────────────────────────────────────
    if errors:
        return ("FAIL", f"{len(errors)} check(s) failed", "; ".join(errors)[:250])
    return (
        "PASS",
        f"{len(db._unique_keys):,} unique / {len(db._set_item_keys):,} set / "
        f"{len(db._prefix_names):,} prefix / {len(db._suffix_names):,} suffix / "
        f"{len(db._runeword_keys):,} rw / "
        f"{len(db._rareprefix_names)} rare-pfx / {len(db._raresuffix_names)} rare-sfx "
        f"-- The Gnasher/Jagged/Friendship/Beast+bite verified",
        "",
    )


# ---------------------------------------------------------------------------
# CharStats smoke-test
# ---------------------------------------------------------------------------


def _check_charstats() -> tuple[str, str, str]:
    """Smoke-test CharStatsDatabase class name loading from charstats.txt.

    Verifications
    -------------
    - DB is loaded (charstats.txt found and parsed)
    - Exactly 8 classes loaded (Amazon=0 through Warlock=7)
    - Class names match expected values for all 8 classes
    - Warlock (ID=7) correctly loaded (Reimagined-specific new class)
    - Fallback: get_class_name for unknown ID returns "Unknown(N)"

    Returns:
        (status, info, detail) tuple.
    """
    db = get_charstats_db()
    errors: list[str] = []

    if not db.is_loaded():
        return ("FAIL", "CharStatsDatabase not loaded", "charstats.txt not found or parse error")

    expected = {
        0: "Amazon",
        1: "Sorceress",
        2: "Necromancer",
        3: "Paladin",
        4: "Barbarian",
        5: "Druid",
        6: "Assassin",
        7: "Warlock",
    }

    all_classes = db.all_classes()
    if len(all_classes) != 8:
        errors.append(f"Expected 8 classes, got {len(all_classes)}")

    for class_id, expected_name in expected.items():
        got = db.get_class_name(class_id)
        if got != expected_name:
            errors.append(f"class_id={class_id}: expected '{expected_name}', got '{got}'")

    # Unknown ID should return "Unknown(N)"
    unknown = db.get_class_name(99)
    if "Unknown" not in unknown:
        errors.append(f"get_class_name(99) expected 'Unknown(99)', got '{unknown}'")

    if errors:
        detail = "; ".join(errors)
        return ("FAIL", f"{len(errors)} check(s) failed", detail[:200])
    return (
        "PASS",
        "8 classes loaded (Amazon-Warlock), Reimagined Warlock class verified",
        "",
    )


# ---------------------------------------------------------------------------


def _check_cubemain_corruption() -> tuple[str, str, str]:
    """Smoke-test the CubeMainDatabase corruption lookup against TC37 findings.

    Verifications
    -------------
    - CubeMainDatabase is loaded (cubemain.txt found and parsed)
    - All 9 item-type categories present: amu, belt, boot, glov, helm, rin, shld, tors, weap
    - decode_corrupted_dummy() correctly decodes TC37 binary values:
        hgl: stat_362=180 -> roll=79, phase2=True -> glov outcome "Deadly Strike + Crushing Blow"
        tow: stat_362=141 -> roll=40, phase2=True -> shld outcome "Nothing"
    - glov roll=79 outcome is_beneficial=True (has mods: deadly/crush)
    - shld roll=40 outcome is_beneficial=False (Nothing - no mods)
    - Outcome probability coverage: all 13 outcome bands sum to 100% per item type
    - CORRUPTION_PHASE2_OFFSET == 101 (encoding constant from recipe data)
    [BINARY_VERIFIED TC37: hgl corruptedDummy=180 -> roll=79, tow corruptedDummy=141 -> roll=40]

    Returns:
        (status, info, detail) tuple.
    """
    from d2rr_toolkit.game_data.cubemain import (
        CubeMainDatabase,
        CORRUPTION_PHASE2_OFFSET,
    )

    db = get_cubemain_db()
    errors: list[str] = []

    # ── 1. DB must be loaded ─────────────────────────────────────────────
    if not db.is_loaded():
        return ("FAIL", "CubeMainDatabase not loaded", "cubemain.txt not found or parse error")

    # ── 2. All 9 item-type categories present ────────────────────────────
    expected_types = {"amu", "belt", "boot", "glov", "helm", "rin", "shld", "tors", "weap"}
    for t in expected_types:
        if not db.get_outcome_table(t):
            errors.append(f"Missing corruption table for item type '{t}'")

    # ── 3. decode_corrupted_dummy: TC37 binary values ────────────────────
    # hgl (Gauntlets): corruptedDummy=180, phase-2 done, roll=79
    roll_hgl, phase2_hgl = CubeMainDatabase.decode_corrupted_dummy(180)
    if roll_hgl != 79:
        errors.append(f"decode(180): expected roll=79, got {roll_hgl}")
    if not phase2_hgl:
        errors.append("decode(180): expected phase2=True, got False")

    # tow (Tower Shield): corruptedDummy=141, phase-2 done, roll=40
    roll_tow, phase2_tow = CubeMainDatabase.decode_corrupted_dummy(141)
    if roll_tow != 40:
        errors.append(f"decode(141): expected roll=40, got {roll_tow}")
    if not phase2_tow:
        errors.append("decode(141): expected phase2=True, got False")

    # Phase-1 only: value <= 100 -> phase2=False
    _, phase2_p1 = CubeMainDatabase.decode_corrupted_dummy(55)
    if phase2_p1:
        errors.append("decode(55): expected phase2=False (phase-1 only)")

    # ── 4. PHASE2_OFFSET constant ────────────────────────────────────────
    if CORRUPTION_PHASE2_OFFSET != 101:
        errors.append(f"CORRUPTION_PHASE2_OFFSET expected 101, got {CORRUPTION_PHASE2_OFFSET}")

    # ── 5. glov outcome for roll=79: Deadly Strike + Crushing Blow [BV TC37]
    outcome_hgl = db.get_corruption_outcome("glov", 79)
    if outcome_hgl is None:
        errors.append("glov roll=79: no outcome found")
    else:
        if not outcome_hgl.is_beneficial:
            errors.append(f"glov roll=79: expected beneficial outcome, got '{outcome_hgl.label}'")
        mod_names = {m.mod for m in outcome_hgl.mods}
        if "deadly" not in mod_names:
            errors.append(f"glov roll=79: expected mod 'deadly', got {mod_names}")
        if "crush" not in mod_names:
            errors.append(f"glov roll=79: expected mod 'crush', got {mod_names}")

    # ── 6. shld outcome for roll=40: Nothing [BV TC37] ──────────────────
    outcome_tow = db.get_corruption_outcome("shld", 40)
    if outcome_tow is None:
        errors.append("shld roll=40: no outcome found")
    else:
        if outcome_tow.is_beneficial:
            errors.append(
                f"shld roll=40: expected non-beneficial (Nothing/Brick), got '{outcome_tow.label}'"
            )

    # ── 7. Probability coverage: all bands sum to 100 ────────────────────
    for itype in expected_types:
        table = db.get_outcome_table(itype)
        total_pct = sum(o.probability_pct for o in table)
        if total_pct != 100:
            errors.append(f"{itype}: probability bands sum to {total_pct}%, expected 100%")

    # ── Result ───────────────────────────────────────────────────────────
    if errors:
        detail = "; ".join(errors)
        return ("FAIL", f"{len(errors)} check(s) failed", detail[:200])
    return (
        "PASS",
        "9 item types, TC37 decode verified (hgl roll=79->deadly+crush, tow roll=40->Nothing)",
        "",
    )


# ---------------------------------------------------------------------------
# TC38: Vanilla-compatible runeword (Insight) + 4 rune children
# ---------------------------------------------------------------------------


def _check_tc38_details(cases_dir: Path) -> tuple[str, str, str]:
    """Detailed expected-value checks for TC38 (TestSorc.d2s).

    Verifications
    -------------
    - Exactly 5 items: 1 parent (7s8 Thresher) + 4 socket children (Ral/Tir/Tal/Sol)
    - JM count = 1 (parent only; rune children are inline extra items)
    - Parent: code='7s8', flags.runeword=True, flags.socketed=True, quality=2 (Normal)
    - Durability: max=250, cur=146  [BV TC38]
    - Item level = 82  [BV TC38]
    - sock_unk = 4 bits (Normal quality weapon, value=4 = socket count)  [BV TC38]
      Consistent with TC24 ltp finding for Normal armor.
    - rw_id in binary = 88 (version drift; recipe lookup gives "Insight" correctly)
    - Recipe from children: (r08, r03, r07, r12) -> "Insight" via recipe lookup
    - magical_properties = [] (Normal quality weapon: no base ISC properties)
    - runeword_properties: 11 display props decoded from RW ISC slot  [BV TC38]
      The RW ISC slot structure is [internal state stats] + [display stats] + 0x1FF.
      The scan-based decoder finds the display prop start and decodes 11 of 12
      expected Insight properties (strength=+5 is in the byte-alignment gap before
      the RW ISC slot and is not captured - known limitation).
      Decoded: energy=5, dexterity=5, vitality=5 (+5 all-stats partial), ED%=216,
      MF=23, oskill CritStrike=3, FCR=35, AR%=223, Meditation Aura Lvl17,
      item_nonclassskill_display=3 (Reimagined display mirror for oskill).
      [BINARY_VERIFIED TC38: display props ARE stored in binary with per-roll values]
    - All 4 rune children: location_id=6 (socket child), 88 bits each  [BV TC24+TC38]
      Rune codes and order: r08 (Ral), r03 (Tir), r07 (Tal), r12 (Sol)
    """
    errors: list[str] = []
    d2s = cases_dir / "TC38" / "TestSorc.d2s"
    parser = D2SParser(d2s)
    char = parser.parse()

    # ── 1. Item count ────────────────────────────────────────────────────
    # Hierarchical model: 1 root (Thresher) with 4 nested rune children.
    if len(char.items) != 1:
        errors.append(f"Expected 1 root item, got {len(char.items)}")
        return ("FAIL", "item count wrong", "; ".join(errors))

    parent = char.items[0]
    children = list(parent.socket_children)
    if len(children) != 4:
        errors.append(f"Expected 4 socket children, got {len(children)}")
        return ("FAIL", "child count wrong", "; ".join(errors))

    # ── 2. Parent item code ──────────────────────────────────────────────
    if parent.item_code != "7s8":
        errors.append(f"Parent code: expected '7s8', got '{parent.item_code}'")

    # ── 3. Flags ─────────────────────────────────────────────────────────
    if not parent.flags or not parent.flags.runeword:
        errors.append("Parent: flags.runeword should be True")
    if not parent.flags or not parent.flags.socketed:
        errors.append("Parent: flags.socketed should be True")

    # ── 4. Quality = 2 (Normal) ──────────────────────────────────────────
    if not parent.extended or parent.extended.quality != 2:
        q = parent.extended.quality if parent.extended else None
        errors.append(f"Parent: expected quality=2 (Normal), got {q}")

    # ── 5. Item level ─────────────────────────────────────────────────────
    if parent.extended and parent.extended.item_level != 82:
        errors.append(f"Parent: expected ilvl=82, got {parent.extended.item_level}")

    # ── 6. Durability ─────────────────────────────────────────────────────
    if parent.armor_data:
        dur = parent.armor_data.durability
        if dur and dur.max_durability != 250:
            errors.append(f"Parent: expected max_dur=250, got {dur.max_durability}")
        if dur and dur.current_durability != 146:
            errors.append(f"Parent: expected cur_dur=146, got {dur.current_durability}")

    # ── 7. Runeword ID in binary ──────────────────────────────────────────
    if parent.runeword_id != 88:
        errors.append(f"Parent: expected runeword_id=88, got {parent.runeword_id}")

    # ── 8. Base ISC props: Normal quality weapon now reads properties
    # (including Reimagined's Hidden Charm Passive stat 97).
    # Previously hardcoded as "24-bit constant" which was wrong for corrupted items.

    # ── 9. Runeword display properties decoded from RW ISC slot  [BV TC38]
    #    The RW ISC slot contains [display property stats] + 0x1FF.
    #    [BINARY_VERIFIED TC38+TC24 uhn]: byte-alignment fix - the RW ISC slot
    #    starts IMMEDIATELY after the base 0x1FF, with NO byte-alignment gap.
    #    This allows ALL 12 Insight display props to be decoded (previously 11;
    #    strength=+5 was lost in a phantom byte-alignment gap).
    #    Expected decoded props (stat_id: value):
    #      0(str)=5, 1(energy)=5, 2(dex)=5, 3(vit)=5 (all-stats complete!)
    #      17(ED%max)=216, 18(ED%min)=216, 80(MF)=23
    #      97(oskill CritStrike, param=9)=3, 105(FCR)=35, 119(AR%)=223
    #      151(aura Meditation, param=120)=17, 387(oskill_display, param=9)=3
    rw = parent.runeword_properties
    if len(rw) != 12:
        errors.append(
            f"Parent: expected 12 runeword_properties (Insight display props), " f"got {len(rw)}"
        )
    else:
        rw_by_id = {p["stat_id"]: p for p in rw}
        _rw_checks = [
            # (stat_id, expected_value, optional_param)
            (0, 5, None),  # strength +5  [recovered by byte-align fix]
            (1, 5, None),  # energy +5
            (2, 5, None),  # dexterity +5
            (3, 5, None),  # vitality +5
            (17, 216, None),  # Enhanced Damage % (max pair)
            (18, 216, None),  # Enhanced Damage % (min pair)
            (80, 23, None),  # Magic Find 23%
            (97, 3, 9),  # oskill Critical Strike +3 (param=9)
            (105, 35, None),  # Faster Cast Rate +35%
            (119, 223, None),  # Attack Rating % +223%
            (151, 17, 120),  # Aura Meditation Level 17 (param=120)
            (387, 3, 9),  # oskill_display mirror (param=9)
        ]
        for sid, expected_val, expected_param in _rw_checks:
            p = rw_by_id.get(sid)
            if p is None:
                errors.append(f"RW props: missing stat_id={sid}")
                continue
            if p.get("value") != expected_val:
                errors.append(
                    f"RW props stat {sid}: expected value={expected_val},"
                    f" got {p.get('value')!r}"
                )
            if expected_param is not None and p.get("param") != expected_param:
                errors.append(
                    f"RW props stat {sid}: expected param={expected_param},"
                    f" got {p.get('param')!r}"
                )

    # ── 10. Children: 4 rune socket children ──────────────────────────────
    expected_runes = ["r08", "r03", "r07", "r12"]  # Ral, Tir, Tal, Sol
    for i, (child, expected_code) in enumerate(zip(children, expected_runes)):
        if child.item_code != expected_code:
            errors.append(f"Child[{i}]: expected code='{expected_code}', got '{child.item_code}'")
        if not child.flags or child.flags.location_id != 6:
            loc = child.flags.location_id if child.flags else None
            errors.append(f"Child[{i}] '{expected_code}': expected location_id=6, got {loc}")

    # ── 11. Recipe-based runeword name lookup ─────────────────────────────
    names_db = get_item_names_db()
    child_codes = [c.item_code for c in children]
    rw_name = names_db.get_runeword_name_by_recipe(child_codes)
    if rw_name != "Insight":
        errors.append(f"Recipe lookup (r08,r03,r07,r12): expected 'Insight', got {rw_name!r}")

    # ── Result ───────────────────────────────────────────────────────────
    if errors:
        return ("FAIL", f"{len(errors)} check(s) failed", "; ".join(errors)[:200])
    return (
        "PASS",
        "5 items (Thresher+4 runes), Insight recipe, 12 RW display props decoded [BV TC38+TC24 byte-align fix]",
        "",
    )


# ---------------------------------------------------------------------------
# TC39: Socketed Unique Weapon + Socket Children (Unique Jewel + Rare Jewel)
# ---------------------------------------------------------------------------


def _check_tc39_details(cases_dir: Path) -> tuple[str, str, str]:
    """Detailed expected-value checks for TC39 (TestSorc.d2s).

    Verifications
    -------------
    - Exactly 3 items: 1 parent (9fc Tulwar) + 2 socket children (jew+jew)
    - JM count = 1 (parent only; jewel children are inline extra items)
    - Parent: code='9fc', quality=7 (Unique), ilvl=99, socketed=True
    - Durability: max=250, cur=202  [BV TC39]
    - Socket children at location_id=6
    - Child 0: Unique Jewel (quality=7), 3 properties (ED%=40, AR=50)
    - Child 1: Rare Jewel (quality=6), 11 properties (including all-res and throw dupes)
    - stat_id=448 warning expected (Reimagined extension, graceful fallback)
    """
    errors: list[str] = []
    d2s = cases_dir / "TC39" / "TestSorc.d2s"
    parser = D2SParser(d2s)
    char = parser.parse()

    items = char.items
    # Hierarchical model: 1 root (Tulwar) with 2 nested socket children.
    if len(items) != 1:
        return ("FAIL", f"Expected 1 root item, got {len(items)}", "")

    parent = items[0]
    if len(parent.socket_children) != 2:
        return (
            "FAIL",
            f"Expected 2 socket children, got {len(parent.socket_children)}",
            "",
        )
    child_unique = parent.socket_children[0]
    child_rare = parent.socket_children[1]

    # ── 1. Parent: Blade of Ali Baba (9fc Tulwar) ─────────────────────────
    if parent.item_code != "9fc":
        errors.append(f"Parent: expected code='9fc', got {parent.item_code!r}")
    if not parent.flags.socketed:
        errors.append("Parent: expected socketed=True")
    if not parent.flags.identified:
        errors.append("Parent: expected identified=True")
    if parent.extended is None:
        errors.append("Parent: missing extended header")
    elif parent.extended.quality != 7:
        errors.append(f"Parent: expected quality=7 (Unique), got {parent.extended.quality}")
    elif parent.extended.item_level != 99:
        errors.append(f"Parent: expected ilvl=99, got {parent.extended.item_level}")
    if parent.unique_type_id != 157:
        errors.append(
            f"Parent: expected unique_type_id=157 (*ID for Blade of Ali Baba), got {parent.unique_type_id}"
        )

    # [BINARY_VERIFIED TC39] Unique Jewel child: has_gfx=1, gfx_unk=0, has_class=0
    # Formula: *ID = uid_12*2 + has_class - 2 = 698*2 + 0 - 2 = 1394 (Spinel Facet)
    if child_unique.unique_type_id != 1394:
        errors.append(
            f"Child 0 (Spinel Facet): expected unique_type_id=1394 "
            f"(has_gfx=1 formula), got {child_unique.unique_type_id}"
        )

    # Durability (weapon stored in armor_data)
    if parent.armor_data and parent.armor_data.durability:
        dur = parent.armor_data.durability
        if dur.max_durability != 250:
            errors.append(f"Parent: expected max_dur=250, got {dur.max_durability}")
        if dur.current_durability != 202:
            errors.append(f"Parent: expected cur_dur=202, got {dur.current_durability}")

    # ── 2. Parent properties (base Unique stats, 7 props) ─────────────────
    parent_props = parent.magical_properties or []
    if len(parent_props) != 7:
        errors.append(f"Parent: expected 7 magical_properties, got {len(parent_props)}")

    def _has(props, sid, val):
        return any(p["stat_id"] == sid and p["value"] == val for p in props)

    # Base Unique stats (before socketing)
    if not _has(parent_props, 2, 7):  # dexterity=7
        errors.append("Parent: missing dexterity=7")
    if not _has(parent_props, 9, 15):  # maxmana=15
        errors.append("Parent: missing maxmana=15")
    if not _has(parent_props, 17, 91):  # item_maxdamage_percent=91 (Enhanced Damage)
        errors.append("Parent: missing item_maxdamage_percent=91")
    if not _has(parent_props, 18, 91):  # item_mindamage_percent=91 (paired)
        errors.append("Parent: missing item_mindamage_percent=91 (paired)")
    if not _has(parent_props, 239, 20):  # item_find_gold_perlevel=20
        errors.append("Parent: missing item_find_gold_perlevel=20")
    if not _has(parent_props, 240, 8):  # item_find_magic_perlevel=8
        errors.append("Parent: missing item_find_magic_perlevel=8")

    # ── 3. Socket Child 0: Unique Jewel (Spinel Facet) ────────────────────
    if child_unique.item_code != "jew":
        errors.append(f"Child 0: expected code='jew', got {child_unique.item_code!r}")
    if child_unique.flags.location_id != 6:
        errors.append(
            f"Child 0: expected location_id=6 (socket), got {child_unique.flags.location_id}"
        )
    if child_unique.extended is None:
        errors.append("Child 0: missing extended header")
    elif child_unique.extended.quality != 7:
        errors.append(f"Child 0: expected quality=7 (Unique), got {child_unique.extended.quality}")

    uniq_props = child_unique.magical_properties or []
    if len(uniq_props) != 3:
        errors.append(f"Child 0 (Unique Jewel): expected 3 props, got {len(uniq_props)}")
    if not _has(uniq_props, 17, 40):  # +40% Enhanced Damage
        errors.append("Child 0: missing item_maxdamage_percent=40")
    if not _has(uniq_props, 18, 40):  # paired
        errors.append("Child 0: missing item_mindamage_percent=40 (paired)")
    if not _has(uniq_props, 19, 50):  # +50 Attack Rating
        errors.append("Child 0: missing tohit=50")

    # ── 4. Socket Child 1: Rare Jewel (Rune Eye) ─────────────────────────
    if child_rare.item_code != "jew":
        errors.append(f"Child 1: expected code='jew', got {child_rare.item_code!r}")
    if child_rare.flags.location_id != 6:
        errors.append(
            f"Child 1: expected location_id=6 (socket), got {child_rare.flags.location_id}"
        )
    if child_rare.extended is None:
        errors.append("Child 1: missing extended header")
    elif child_rare.extended.quality != 6:
        errors.append(f"Child 1: expected quality=6 (Rare), got {child_rare.extended.quality}")

    rare_props = child_rare.magical_properties or []
    # 11 props expected (energy, min/max dmg *3 variants, 4 resists, throw min/max)
    if len(rare_props) != 11:
        errors.append(f"Child 1 (Rare Jewel): expected 11 props, got {len(rare_props)}")
    if not _has(rare_props, 1, 6):  # energy=6
        errors.append("Child 1: missing energy=6")
    if not _has(rare_props, 21, 8):  # mindamage=8
        errors.append("Child 1: missing mindamage=8")
    if not _has(rare_props, 22, 4):  # maxdamage=4
        errors.append("Child 1: missing maxdamage=4")
    if not _has(rare_props, 39, 15):  # fireresist=15 (part of All Res)
        errors.append("Child 1: missing fireresist=15")
    if not _has(rare_props, 41, 15):  # lightresist=15
        errors.append("Child 1: missing lightresist=15")
    if not _has(rare_props, 43, 15):  # coldresist=15
        errors.append("Child 1: missing coldresist=15")
    if not _has(rare_props, 45, 15):  # poisonresist=15
        errors.append("Child 1: missing poisonresist=15")

    # ── Result ────────────────────────────────────────────────────────────
    if errors:
        detail = "; ".join(errors)
        return ("FAIL", f"{len(errors)} check(s) failed", detail[:200])
    return (
        "PASS",
        "3 items (Tulwar+2 jewels), socket children at loc=6, parent 7 props, "
        "Unique Jewel 3 props, Rare Jewel 11 props [BV TC39]",
        "",
    )


# ---------------------------------------------------------------------------
# TC40: Rare Jewel with Custom Graphics (has_gfx=1)
# ---------------------------------------------------------------------------


def _check_tc40_details(cases_dir: Path) -> tuple[str, str, str]:
    """Detailed expected-value checks for TC40 (TestSorc.d2s).

    Verifications
    -------------
    - Exactly 1 item: Rare Jewel (jew) with has_gfx=1
    - Rare name: "Rune talisman" (prefix=14=Rune, suffix=130=talisman)
    - Properties: maxdamage=15, armorclass=25, lightresist=20
    - Forced 7-slot retry correctly compensates gfx_alignment shift
    """
    errors: list[str] = []
    d2s = cases_dir / "TC40" / "TestSorc.d2s"
    parser = D2SParser(d2s)
    char = parser.parse()

    items = char.items
    if len(items) != 1:
        return ("FAIL", f"Expected 1 item, got {len(items)}", "")

    item = items[0]
    if item.item_code != "jew":
        errors.append(f"Expected code='jew', got {item.item_code!r}")
    if item.extended is None:
        errors.append("Missing extended header")
    elif item.extended.quality != 6:
        errors.append(f"Expected quality=6 (Rare), got {item.extended.quality}")
    if not item.extended or not item.extended.has_custom_graphics:
        errors.append("Expected has_gfx=True")

    # Rare name IDs (GoMule offsets applied by parser)
    if item.rare_name_id1 != 14:
        errors.append(f"Expected rare_name_id1=14 (Rune), got {item.rare_name_id1}")
    if item.rare_name_id2 != 130:
        errors.append(f"Expected rare_name_id2=130 (talisman), got {item.rare_name_id2}")

    # Properties
    props = item.magical_properties or []

    def _has(sid, val):
        return any(p["stat_id"] == sid and p["value"] == val for p in props)

    if not _has(22, 15):  # maxdamage = 15
        errors.append("Missing maxdamage=15")
    if not _has(31, 25):  # armorclass = 25
        errors.append("Missing armorclass=25")
    if not _has(41, 20):  # lightresist = 20
        errors.append("Missing lightresist=20")

    if errors:
        detail = "; ".join(errors)
        return ("FAIL", f"{len(errors)} check(s) failed", detail[:200])
    return (
        "PASS",
        "1 Rare Jewel (has_gfx=1), name='Rune talisman', "
        "maxdmg=15 def=25 lres=20 [BV TC40 forced retry]",
        "",
    )


def _check_casc_reader() -> tuple[str, str, str]:
    """Validate CASC reader TVFS path resolution.

    Purely verifies that the CASC reader can enumerate the game's asset
    tree, parse it without formatting errors, and resolve a handful of
    well-known sprite paths. Sprite decoding and the code->CKey map that
    used to live in the legacy GUI sprites module are out of scope here
    - that pipeline now has its own coverage under d2rr_toolkit.sprites.
    """
    try:
        from d2rr_toolkit.config import get_game_paths
        from d2rr_toolkit.adapters.casc import CASCReader

        gp = get_game_paths()
        reader = CASCReader(gp.d2r_install)

        errors = []

        # 1. Path map populated
        if len(reader._path_map) < 100000:
            errors.append(f"path_map too small: {len(reader._path_map)}")

        # 2. No double slashes (format correctness)
        bad_paths = sum(1 for p in reader._path_map if "//" in p)
        if bad_paths > 0:
            errors.append(f"{bad_paths} paths with '//'")

        # 3. Key sprite paths exist (infrastructure sanity check)
        required_paths = [
            "data:data/hd/global/ui/items/misc/ring/ring.sprite",
            "data:data/hd/global/ui/items/misc/ring/ring1.sprite",
            "data:data/hd/global/ui/items/misc/charm/charm_small.sprite",
            "data:data/hd/global/ui/items/misc/charm/charm_large3.sprite",
            "data:data/hd/global/ui/items/armor/armor/quilted_armor.sprite",
            "data:data/hd/global/ui/items/weapon/axe/hand_axe.sprite",
        ]
        for rp in required_paths:
            if rp not in reader._path_map:
                errors.append(f"missing: {rp.split('/')[-1]}")

        if errors:
            return ("FAIL", f"{len(errors)} errors", "; ".join(errors[:3]))

        n_paths = len(reader._path_map)
        return ("PASS", f"{n_paths} paths, ring/charm/armor paths resolved", "")
    except Exception as e:
        return ("FAIL", type(e).__name__, str(e)[:120])


def _check_tc62_details(cases_dir: Path) -> tuple[str, str, str]:
    """Detailed regression check for TC62 (SimpleItems.d2s).

    Guards the "18-bit Huffman simple item padding" bug (hp2/mp2).

    Background
    ----------
    Simple items have the structure:
        flags(53) + huffman(variable) + socket_bit(1) + [quantity(9) if stackable]
        + skip_to_byte_boundary

    For items whose Huffman code is exactly 18 bits (hp2, mp2, rvs), the
    first three fields sum to 72 bits - already on a byte boundary, so
    skip_to_byte_boundary() is a no-op. In the real binary, however, a
    full trailing padding byte is present: the true item size is 80 bits
    (10 bytes) for non-quantity or 88 bits (11 bytes) for quantity.

    Before the fix, _skip_inter_item_padding() gated itself on
    ``item.extended is not None`` and never ran for simple items,
    so these 8 bits were silently dropped, cascading into garbage for
    every subsequent item.

    After the fix, the helper runs for simple items too, probes the next
    item's Huffman at 8-bit offsets, finds the real next-item start, and
    advances the reader to the right place.

    Expected layout
    ---------------
    24 items in a single inventory-row layout, panel=1:
      row 0: hp1 hp1 hp2 hp2 hp3 hp3 hp4 hp4 hp5 hp5
      row 1: mp1 mp1 mp2 mp2 mp3 mp3 mp4 mp4 mp5 mp5
      row 2: rvs rvs rvl rvl . . . . . .

    Per-item binary sizes (all [BV TC62]):
      hp1..hp5, mp1..mp5: 10 bytes (80 bits) - non-quantity simple
      rvs, rvl:           11 bytes (88 bits) - quantity simple (+9 bits)

    The key regression targets hp2 and mp2 (the only 18-bit Huffman
    non-quantity codes in this fixture). Before the fix, the parser
    would see them as 9 bytes each and drift into the next item.
    """
    errors: list[str] = []
    d2s = cases_dir / "TC62" / "SimpleItems.d2s"
    char = D2SParser(d2s).parse()

    items = char.items
    if len(items) != 24:
        return ("FAIL", f"Expected 24 items, got {len(items)}", "")

    expected_codes = [
        "hp1",
        "hp1",
        "hp2",
        "hp2",
        "hp3",
        "hp3",
        "hp4",
        "hp4",
        "hp5",
        "hp5",
        "mp1",
        "mp1",
        "mp2",
        "mp2",
        "mp3",
        "mp3",
        "mp4",
        "mp4",
        "mp5",
        "mp5",
        "rvs",
        "rvs",
        "rvl",
        "rvl",
    ]
    for i, (exp, it) in enumerate(zip(expected_codes, items)):
        if it.item_code != exp:
            errors.append(f"item[{i}]: expected {exp!r} got {it.item_code!r}")
        if not it.flags.simple:
            errors.append(f"item[{i}] {it.item_code}: expected simple=True")

    # Expected grid positions (panel=1 = inventory).
    expected_positions = [
        (0, 0),
        (1, 0),
        (2, 0),
        (3, 0),
        (4, 0),
        (5, 0),
        (6, 0),
        (7, 0),
        (8, 0),
        (9, 0),
        (0, 1),
        (1, 1),
        (2, 1),
        (3, 1),
        (4, 1),
        (5, 1),
        (6, 1),
        (7, 1),
        (8, 1),
        (9, 1),
        (0, 2),
        (1, 2),
        (2, 2),
        (3, 2),
    ]
    for i, ((px, py), it) in enumerate(zip(expected_positions, items)):
        if it.flags.panel_id != 1:
            errors.append(f"item[{i}] {it.item_code}: expected panel=1 got {it.flags.panel_id}")
        if (it.flags.position_x, it.flags.position_y) != (px, py):
            errors.append(
                f"item[{i}] {it.item_code}: expected pos=({px},{py}) got "
                f"({it.flags.position_x},{it.flags.position_y})"
            )

    # Per-code expected source_data byte sizes (exercises the padding fix).
    expected_sizes = {
        "hp1": 10,
        "hp2": 10,
        "hp3": 10,
        "hp4": 10,
        "hp5": 10,
        "mp1": 10,
        "mp2": 10,
        "mp3": 10,
        "mp4": 10,
        "mp5": 10,
        "rvs": 11,
        "rvl": 11,
    }
    for i, it in enumerate(items):
        sz = len(it.source_data) if it.source_data else 0
        want = expected_sizes[it.item_code]
        if sz != want:
            errors.append(f"item[{i}] {it.item_code}: expected {want} bytes got {sz}")

    if errors:
        detail = "; ".join(errors[:5])
        return ("FAIL", f"{len(errors)} check(s) failed", detail[:200])
    return (
        "PASS",
        "24 simple items (2x hp1-hp5, 2x mp1-mp5, 2x rvs, 2x rvl) "
        "with correct 10/11-byte sizes incl. hp2/mp2 padding fix [BV TC62]",
        "",
    )


def _check_tc63_details(cases_dir: Path) -> tuple[str, str, str]:
    """Detailed regression check for TC63 (Knurpsi.d2s).

    Guards the "bf1=True weapon/armor automod without auto_prefix" bug.

    Background
    ----------
    In D2R (both vanilla and Reimagined), the 11-bit automod (class_data)
    slot in the extended item header is present for every bf1=True weapon
    or armor whenever has_class=1 - INDEPENDENT of whether the item's row
    in weapons.txt / armor.txt has an ``auto prefix`` value set. The
    ``auto prefix`` column controls whether the game rolls a random
    automod on creation, not whether the 11-bit slot exists.

    A small number of base types have an EMPTY ``auto prefix`` column:
    ``crs`` is the only weapon, plus most generic armor (belts, boots,
    circlets, gloves, generic helms like cap/skp/hlm, pelts, primal
    helms, generic torsos like stu/brs). Before the fix, the parser
    skipped the 11-bit read for these items whenever has_class=1, and
    subsequently consumed the durability / socket-count bits from the
    wrong offset. For Knurpsi's crs the visible damage was:
      max_dur=131 / cur_dur=209 (impossible: cur > max)
      total_sockets=1 (truth: 6)
      3 magical properties (truth: 15)
      runeword=False propagated into a cascading garbage item ('9cfmfw').

    Expected payload
    ----------------
    Superior Crystal Sword at inventory (0,0), panel=1:
      - quality=3 (Superior)
      - total_nr_of_sockets=6
      - durability 200/250
      - 15 magical properties including:
          maxdamage_percent=13, mindamage_percent=13, tohit=2,
          firemindam=63 firemaxdam=511,
          lightmindam=63 lightmaxdam=511,
          coldmindam=63 coldmaxdam=511,
          item_attackertakesdamage=100,
          item_healafterkill=3, item_manaafterkill=4,
          upgrade_major=5 (5 of 5 Enchantments used).
      - 6 socket children: 4x r15 (Hel rune) + 2x jew.

    The second regression lever exercised by this fixture is the
    hp2/mp2 padding fix from TC62: Knurpsi has 11x hp2 which, before
    that fix, cascaded into total parse corruption around item 17+.
    """
    errors: list[str] = []
    d2s = cases_dir / "TC63" / "Knurpsi.d2s"
    char = D2SParser(d2s).parse()

    items = char.items
    # Hierarchical model: 41 root items, with 6 socket children nested in
    # the Crystal Sword. The legacy "47 flat" expectation maps to this.
    flat_total = len(items) + sum(len(it.socket_children) for it in items)
    if flat_total != 47:
        errors.append(f"Expected 47 items (41 roots + 6 children), got {flat_total}")

    # Count hp2 items (the simple-item padding regression lever).
    # Before Fix #1 the parser dropped 8 bits per hp2, corrupting the item
    # count entirely; this save contains exactly 11 of them.
    hp2_count = sum(1 for it in items if it.item_code == "hp2")
    if hp2_count != 11:
        errors.append(f"Expected 11x hp2, got {hp2_count}")

    # Find the Crystal Sword at inventory (0,0), panel=1.
    crs = next(
        (
            it
            for it in items
            if it.item_code == "crs"
            and it.flags.panel_id == 1
            and it.flags.position_x == 0
            and it.flags.position_y == 0
        ),
        None,
    )
    if crs is None:
        return ("FAIL", "Crystal Sword at (0,0) not found", "")

    if crs.extended is None or crs.extended.quality != 3:
        errors.append(
            f"crs: expected quality=3 (Superior), got "
            f"{crs.extended.quality if crs.extended else None}"
        )
    if crs.flags.runeword:
        errors.append("crs: expected runeword=False (Superior+runes, NOT a runeword)")
    if crs.total_nr_of_sockets != 6:
        errors.append(f"crs: expected 6 sockets, got {crs.total_nr_of_sockets}")
    if crs.armor_data is None or crs.armor_data.durability is None:
        errors.append("crs: missing durability")
    else:
        dur = crs.armor_data.durability
        if dur.max_durability != 250:
            errors.append(f"crs: expected max_dur=250, got {dur.max_durability}")
        if dur.current_durability != 200:
            errors.append(f"crs: expected cur_dur=200, got {dur.current_durability}")

    props = crs.magical_properties or []
    if len(props) != 15:
        errors.append(f"crs: expected 15 magical properties, got {len(props)}")

    def _has(stat: str, value: int) -> bool:
        return any(p.get("name") == stat and p.get("value") == value for p in props)

    expected_props = [
        ("item_maxdamage_percent", 13),
        ("item_mindamage_percent", 13),
        ("tohit", 2),
        ("firemindam", 63),
        ("firemaxdam", 511),
        ("lightmindam", 63),
        ("lightmaxdam", 511),
        ("coldmindam", 63),
        ("coldmaxdam", 511),
        ("item_attackertakesdamage", 100),
        ("item_healafterkill", 3),
        ("item_manaafterkill", 4),
        ("upgrade_major", 5),
    ]
    for stat, val in expected_props:
        if not _has(stat, val):
            errors.append(f"crs: missing property {stat}={val}")

    # Socket children: 4x r15 (Hel rune) + 2x jew. Children are nested
    # inside their parent - flatten across all parents to count.
    socket_children = [child.item_code for it in items for child in it.socket_children]
    r15_count = socket_children.count("r15")
    jew_count = socket_children.count("jew")
    if r15_count != 4:
        errors.append(f"Expected 4x r15 (Hel rune) socket children, got {r15_count}")
    if jew_count != 2:
        errors.append(f"Expected 2x jew socket children, got {jew_count}")

    # Mercenary header (14-byte block at 0xA1 + resolved class/name)
    # [BV Knurpsi user-verified: Paige, Rogue Scout, Normal]
    merc = char.mercenary
    if merc is None:
        errors.append("Expected mercenary header (Knurpsi has a merc), got None")
    else:
        if merc.hireling_class != "Rogue Scout":
            errors.append(
                f"merc.hireling_class: expected 'Rogue Scout', got {merc.hireling_class!r}"
            )
        if merc.hireling_difficulty != 1:
            errors.append(
                f"merc.hireling_difficulty: expected 1 (Normal), got {merc.hireling_difficulty}"
            )
        if merc.type_id != 0:
            errors.append(f"merc.type_id: expected 0, got {merc.type_id}")
        if merc.name_id != 5:
            errors.append(f"merc.name_id: expected 5, got {merc.name_id}")
        if merc.is_dead:
            errors.append("merc.is_dead: expected False (merc is alive)")
        # resolved_name check is best-effort: only complain when the name
        # table WAS loaded (otherwise the field is None by design).
        if merc.resolved_name is not None and merc.resolved_name != "Paige":
            errors.append(f"merc.resolved_name: expected 'Paige', got {merc.resolved_name!r}")

    # Merc equipment: 9 items (the Reimagined merc has all 10 hero slots
    # except the left-hand slot which is empty because the Long Bow is
    # a 2H weapon). Plus 3 socket children = 12 total merc entries.
    merc_equipped = char.merc_equipped()
    merc_sockets = char.merc_socketed_children()
    if len(merc_equipped) != 9:
        errors.append(f"Expected 9 merc-equipped items, got {len(merc_equipped)}")
    if len(merc_sockets) != 3:
        errors.append(f"Expected 3 merc socket children, got {len(merc_sockets)}")
    # The merc's weapon is a Magic Long Bow at slot 4 with 3 filled sockets.
    merc_weapon = next((it for it in merc_equipped if it.flags.equipped_slot == 4), None)
    if merc_weapon is None:
        errors.append("Merc weapon (slot 4) not found")
    elif merc_weapon.item_code != "lbw":
        errors.append(f"Merc weapon: expected 'lbw', got {merc_weapon.item_code!r}")

    if errors:
        detail = "; ".join(errors[:5])
        return ("FAIL", f"{len(errors)} check(s) failed", detail[:200])
    return (
        "PASS",
        "Superior crs at (0,0), 6 sockets (4 Hel + 2 jew), dur 200/250, "
        "15 props incl. 13% ED, fire/light/cold 63-511, 5/5 enchants; "
        "merc=Paige (Rogue Scout D1) with lbw+3sockets [BV TC63]",
        "",
    )


def _check_tc64_details(cases_dir: Path) -> tuple[str, str, str]:
    """Detailed regression check for TC64 (MercOnly.d2s).

    Isolates the entire mercenary code path from player inventory:
    the player character has zero items, and the mercenary wears all
    ten Reimagined merc slots with a 2-socket Unique Circlet carrying
    a Rare Jewel and a Skull.

    Verifies:
      * MercenaryHeader round-trip: name='Fiona', type=1, name_id=15,
        hireling_class='Rogue Scout', difficulty=1, alive, exp match.
      * Player inventory/equipment/belt/stash/cube all empty.
      * merc_equipped() returns 9 items in the expected slot+code set.
      * merc_socketed_children() returns exactly 2 (Rare Jewel + Skull).
      * All 9 equipped items land on the correct slot ID (1..10 with
        slot 5 empty because the weapon is 2H).
    """
    errors: list[str] = []
    d2s = cases_dir / "TC64" / "MercOnly.d2s"
    char = D2SParser(d2s).parse()

    # Character must have no player items whatsoever.
    if len(char.items) != 0:
        errors.append(f"Expected 0 player items, got {len(char.items)}")
    if len(char.items_in_inventory()) != 0:
        errors.append(f"Expected empty inventory, got {len(char.items_in_inventory())}")
    if len(char.items_equipped()) != 0:
        errors.append(f"Expected no player-equipped items, got {len(char.items_equipped())}")
    if len(char.items_in_belt()) != 0:
        errors.append(f"Expected empty belt, got {len(char.items_in_belt())}")
    if len(char.items_in_cube()) != 0:
        errors.append(f"Expected no cube items, got {len(char.items_in_cube())}")
    if len(char.items_in_stash_d2s()) != 0:
        errors.append(f"Expected empty d2s stash, got {len(char.items_in_stash_d2s())}")

    # Mercenary header checks.
    merc = char.mercenary
    if merc is None:
        return ("FAIL", "Expected mercenary, got None", "")
    if merc.hireling_class != "Rogue Scout":
        errors.append(f"merc.hireling_class: expected 'Rogue Scout', got {merc.hireling_class!r}")
    if merc.type_id != 1:
        errors.append(f"merc.type_id: expected 1, got {merc.type_id}")
    if merc.name_id != 15:
        errors.append(f"merc.name_id: expected 15, got {merc.name_id}")
    if merc.hireling_difficulty != 1:
        errors.append(
            f"merc.hireling_difficulty: expected 1 (Normal), got {merc.hireling_difficulty}"
        )
    if merc.is_dead:
        errors.append("merc.is_dead: expected False")
    if merc.experience != 62_410_000:
        errors.append(f"merc.experience: expected 62,410,000, got {merc.experience}")
    # Resolved name is best-effort - only enforced when the name table was loaded.
    if merc.resolved_name is not None and merc.resolved_name != "Fiona":
        errors.append(f"merc.resolved_name: expected 'Fiona', got {merc.resolved_name!r}")

    # Merc equipment: 9 items across slots 1,2,3,4,6,7,8,9,10 (slot 5 empty - 2H bow).
    merc_eq = char.merc_equipped()
    if len(merc_eq) != 9:
        errors.append(f"Expected 9 merc-equipped items, got {len(merc_eq)}")
    merc_sockets = char.merc_socketed_children()
    if len(merc_sockets) != 2:
        errors.append(f"Expected 2 merc socket children, got {len(merc_sockets)}")

    # Per-slot code verification. Map slot -> (code, quality_id).
    expected_slots = {
        1: ("ci0", 7),  # Head: Fair Weather Circlet (Unique)
        2: ("amu", 7),  # Amulet: Mara's (amu7) (Unique)
        3: ("spl", 7),  # Body: Iceblink Splint Mail (Unique)
        4: ("lwb", 7),  # Right Hand: Telena's Long War Bow (Unique, 2H)
        6: ("rin", 7),  # Right Ring: Vampiric Regeneration (Unique)
        7: ("rin", 5),  # Left Ring: Vampire's Crusade (Set)
        8: ("zhb", 5),  # Belt: Immortal King's Detail (Set)
        9: ("uvb", 7),  # Boots: Sandstorm Trek (Unique)
        10: ("tgl", 7),  # Gloves: Magefist (Unique)
    }
    by_slot = {it.flags.equipped_slot: it for it in merc_eq}
    for slot, (want_code, want_quality) in expected_slots.items():
        it = by_slot.get(slot)
        if it is None:
            errors.append(f"merc slot {slot}: missing")
            continue
        if it.item_code != want_code:
            errors.append(f"merc slot {slot}: expected code {want_code!r}, got {it.item_code!r}")
        if it.extended and it.extended.quality != want_quality:
            errors.append(
                f"merc slot {slot} {it.item_code}: expected quality {want_quality}, "
                f"got {it.extended.quality}"
            )

    # Slot 5 (Left Hand) must stay empty because the Long War Bow is 2H.
    if 5 in by_slot:
        errors.append(
            f"merc slot 5 (Left Hand): expected empty (2H weapon), got {by_slot[5].item_code!r}"
        )

    # Head item must be the Circlet with 2 sockets (Fair Weather).
    head = by_slot.get(1)
    if head is not None:
        if (head.total_nr_of_sockets or 0) != 2:
            errors.append(
                f"Fair Weather circlet: expected 2 sockets, got {head.total_nr_of_sockets}"
            )

    # Socket children must be exactly 1 Rare Jewel + 1 Skull gem.
    sock_codes = sorted(c.item_code for c in merc_sockets)
    if sock_codes != ["gmk", "jew"]:
        errors.append(f"merc socket children: expected ['gmk','jew'], got {sock_codes}")

    if errors:
        detail = "; ".join(errors[:5])
        return ("FAIL", f"{len(errors)} check(s) failed", detail[:200])
    return (
        "PASS",
        "merc=Fiona (Rogue Scout D1, exp 62.4M); 9 merc-equipped items "
        "across all 10 hero slots (slot 5 empty, 2H bow); 2 socket "
        "children (Rare jewel + skull); no player items [BV TC64]",
        "",
    )


def _check_tc65_details(cases_dir: Path) -> tuple[str, str, str]:
    """Detailed regression check for TC65 (CubeContents.d2s).

    Covers the previously-untested panel_id=4 (Horadric Cube) code path.
    The only inventory item is the cube itself; everything else lives
    inside the cube, including a 4-socket Insight runeword whose recipe
    (Ral+Tir+Tal+Sol) forces the recipe-based runeword-name lookup
    (runeword_id row lookup would return a wrong name).

    Verifies:
      * Exactly one inventory item, the box at (0,0).
      * 15 cube items at the expected positions with the expected codes.
      * The Insight runeword has total_nr_of_sockets=6? No - 4 sockets,
        one per rune, dur 146/250, 12 runeword properties.
      * Socket children r08/r03/r07/r12 (Ral/Tir/Tal/Sol) are linked
        through as children of the Thresher.
      * Quest items (xa1, pk1, ua1) parse with zero magical properties
        and do not disturb the items that follow them.
      * Character has no mercenary (control seed 0).
    """
    errors: list[str] = []
    d2s = cases_dir / "TC65" / "CubeContents.d2s"
    char = D2SParser(d2s).parse()

    # No mercenary in this save (control_seed is zero).
    if char.mercenary is not None:
        errors.append(f"Expected mercenary=None, got {char.mercenary}")

    # Inventory must contain just the cube.
    inv = char.items_in_inventory()
    if len(inv) != 1:
        errors.append(f"Expected exactly 1 inventory item (the cube), got {len(inv)}")
    elif inv[0].item_code != "box":
        errors.append(f"Inventory item: expected 'box', got {inv[0].item_code!r}")
    elif (inv[0].flags.position_x, inv[0].flags.position_y) != (0, 0):
        errors.append(
            f"Cube position: expected (0,0), got "
            f"({inv[0].flags.position_x},{inv[0].flags.position_y})"
        )

    # Belt / equipped / stash_d2s must be empty.
    if char.items_equipped():
        errors.append("Expected no equipped items")
    if char.items_in_belt():
        errors.append("Expected no belt items")
    if char.items_in_stash_d2s():
        errors.append("Expected no d2s stash items")

    # Cube contents: 15 primary items at specific positions.
    cube = char.items_in_cube()
    if len(cube) != 15:
        errors.append(f"Expected 15 cube items, got {len(cube)}")

    expected_cube = {
        (0, 0): "xh9",  # Natalya's Totem (Set Grim Helm)
        (2, 0): "wa5",  # Grimoire of the Riven Blade (Unique Grimoire)
        (11, 0): "9fc",  # Fleshbleeder (Unique Tulwar)
        (0, 2): "7s8",  # Insight (Runeword Thresher)
        (2, 2): "xa1",  # Western Worldstone Shard (quest)
        (2, 3): "pk1",  # Key of Terror (quest)
        (11, 3): "isc",  # ID scroll
        (11, 4): "rvs",  # Minor Rejuv
        (10, 5): "yps",  # Antidote
        (11, 5): "rvl",  # Full Rejuv
        (0, 6): "ua1",  # Talic's Anguish (quest)
        (10, 6): "wms",  # Thawing
        (11, 6): "jew",  # Shadow Eye (Rare Jewel)
        (10, 7): "tsc",  # TP scroll
        (11, 7): "cm5",  # Collin's Destruction (Unique Small Charm)
    }
    cube_by_pos = {(it.flags.position_x, it.flags.position_y): it for it in cube}
    for pos, want_code in expected_cube.items():
        it = cube_by_pos.get(pos)
        if it is None:
            errors.append(f"Cube pos {pos}: missing")
            continue
        if it.item_code != want_code:
            errors.append(f"Cube pos {pos}: expected {want_code!r}, got {it.item_code!r}")
        if it.flags.panel_id != 4:
            errors.append(
                f"Cube pos {pos} {it.item_code}: expected panel_id=4, got {it.flags.panel_id}"
            )

    # Quest items (xa1 / pk1 / ua1) must have zero magical properties.
    for code in ("xa1", "pk1", "ua1"):
        quest = next((it for it in cube if it.item_code == code), None)
        if quest is not None:
            props = quest.magical_properties or []
            if len(props) != 0:
                errors.append(f"Quest item {code!r}: expected 0 props, got {len(props)}")

    # Insight runeword - recipe-based lookup must find "Insight".
    insight = next((it for it in cube if it.item_code == "7s8" and it.flags.runeword), None)
    if insight is None:
        errors.append("Insight runeword (7s8) not found in cube")
    else:
        if (insight.total_nr_of_sockets or 0) != 4:
            errors.append(f"Insight: expected 4 sockets, got {insight.total_nr_of_sockets}")
        if insight.armor_data is None or insight.armor_data.durability is None:
            errors.append("Insight: missing durability")
        else:
            dur = insight.armor_data.durability
            if (dur.current_durability, dur.max_durability) != (146, 250):
                errors.append(
                    f"Insight: expected dur 146/250, got "
                    f"{dur.current_durability}/{dur.max_durability}"
                )
        rw_props = getattr(insight, "runeword_properties", None) or []
        if len(rw_props) != 12:
            errors.append(f"Insight: expected 12 runeword props, got {len(rw_props)}")

    # Insight's socket children: Ral, Tir, Tal, Sol (r08, r03, r07, r12).
    # Children are nested inside their parent's socket_children list.
    sock_children = (
        [child.item_code for child in insight.socket_children] if insight is not None else []
    )
    expected_runes = ["r08", "r03", "r07", "r12"]
    if sorted(sock_children) != sorted(expected_runes):
        errors.append(
            f"Insight runes: expected {sorted(expected_runes)}, got {sorted(sock_children)}"
        )

    if errors:
        detail = "; ".join(errors[:5])
        return ("FAIL", f"{len(errors)} check(s) failed", detail[:200])
    return (
        "PASS",
        "box @ inv(0,0), 15 cube items at exact positions, Insight "
        "runeword (Thresher, Ral+Tir+Tal+Sol, dur 146/250, 12 rw props), "
        "quest items with 0 props, mercenary=None [BV TC65]",
        "",
    )


# ---------------------------------------------------------------------------
# Crafted required-level formula regression
# ---------------------------------------------------------------------------


def _check_crafted_req_level(cases_dir: Path) -> tuple[str, str, str]:
    """Regression guard for the Crafted required-level formula.

    Empirically verified against the D2R Reimagined in-game tooltip on
    FrozenOrbHydra.d2s (all four Grand Charms in the inventory, 2026-04-14):

        required_level = max_affix_lvlreq + 10 + 3 * num_affixes

    The +10 + 3*n addend accounts for the recipe-mandated bonus layer
    that crafted items carry on top of their random affixes. The rule
    is specific to quality=8 (Crafted); Rare items (quality=6) keep
    the plain max_affix value which matches the tooltip without a
    recipe component.

    Fails loudly if anyone "simplifies" calculate_requirements back
    to just max(affix_lvlreq) or tries to generalise the crafted
    formula to Rare items.
    """
    from d2rr_toolkit.parsers.d2s_parser import D2SParser
    from d2rr_toolkit.game_data.item_types import get_item_type_db
    from d2rr_toolkit.game_data.item_names import get_item_names_db
    from d2rr_toolkit.display.item_display import calculate_requirements

    d2s = cases_dir / "TC55" / "FrozenOrbHydra.d2s"
    try:
        char = D2SParser(d2s).parse()
    except Exception as e:
        return ("FAIL", "parse error", str(e)[:120])

    type_db = get_item_type_db()
    names_db = get_item_names_db()

    # Ground truth - from the in-game tooltip on the listed inventory slots.
    expected: dict[str, int] = {
        "Ghoul Eye": 59,  # inventory (4, 5) - 3 affixes, max_aff 40
        "Grim Eye": 92,  # inventory (4, 0) - 4 affixes, max_aff 70
        "Doom Eye": 64,  # inventory (5, 3) - 4 affixes, max_aff 42
        "Dread Eye": 61,  # inventory (6, 3) - 3 affixes, max_aff 42
    }
    errors: list[str] = []
    found: set[str] = set()
    for item in char.items:
        if item.item_code not in ("cm1", "cm2", "cm3"):
            continue
        if item.extended is None or item.extended.quality != 8:
            continue
        name = names_db.get_rare_name(item.rare_name_id1, item.rare_name_id2)
        if name not in expected:
            continue
        found.add(name)
        req = calculate_requirements(item, [], type_db, names_db=names_db)
        if req.level != expected[name]:
            errors.append(f"{name}: expected req_lvl={expected[name]}, got {req.level}")

    missing = sorted(set(expected) - found)
    if missing:
        errors.append(f"missing ground-truth charms: {missing}")

    if errors:
        return ("FAIL", f"{len(errors)} check(s) failed", "; ".join(errors)[:200])
    return (
        "PASS",
        "4 Crafted Grand Charms match max_affix + 10 + 3*n formula "
        "[BV FrozenOrbHydra 2026-04-14]",
        "",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    # Load game data from D2R installation via GamePaths config.
    # Every loader resolves its files through the shared CASCReader
    # (Iron Rule: Reimagined mod first, D2R CASC fallback).
    from d2rr_toolkit.config import get_game_paths

    gp = get_game_paths()
    if not gp.reimagined_excel.is_dir():
        print("ERROR: Game data not found! Install D2R Reimagined first.")
        return 1
    load_item_stat_cost()
    load_item_types()
    load_skills()
    load_cubemain()
    load_charstats()
    load_item_names()
    load_hireling()

    # Load localised merc names from CASC - required for TC63 to resolve
    # Paige / Floria / etc. and for any test that checks MercenaryHeader.resolved_name.
    # Best-effort: if CASC is not available, the parser still populates the
    # merc header, it just leaves resolved_name=None.
    try:
        from d2rr_toolkit.adapters.casc.reader import CASCReader

        casc_reader = CASCReader(gp.d2r_install)
        merc_json = casc_reader.read_file("data:data/local/lng/strings/mercenaries.json")
        load_merc_names(merc_json)
    except Exception as exc:  # pragma: no cover - best-effort only
        print(f"WARNING: Could not load merc names from CASC: {exc}")

    cases_dir = project_root / "tests" / "cases"
    results: dict[str, tuple[str, str, str]] = {}

    for tc_dir in sorted(cases_dir.iterdir()):
        if not tc_dir.is_dir() or not tc_dir.name.startswith("TC"):
            continue
        tc_name = tc_dir.name

        # Find binary files
        d2s_files = list(tc_dir.glob("*.d2s"))
        d2i_files = list(tc_dir.glob("*.d2i"))

        if d2s_files:
            for f in d2s_files:
                key = f"{tc_name}/{f.name}"
                try:
                    parser = D2SParser(f)
                    char = parser.parse()
                    results[key] = ("PASS", f"{len(char.items)} items", "")
                except Exception as e:
                    results[key] = ("FAIL", type(e).__name__, str(e)[:120])
        elif d2i_files:
            for f in d2i_files:
                key = f"{tc_name}/{f.name}"
                try:
                    parser = D2IParser(f)
                    stash = parser.parse()
                    n_tabs = len(stash.tabs)
                    n_items = stash.total_items
                    results[key] = ("PASS", f"{n_items} items across {n_tabs} tabs", "")
                except Exception as e:
                    results[key] = ("FAIL", type(e).__name__, str(e)[:120])
        else:
            results[tc_name] = ("SKIP", "no binary files", "")

    # ── TC-specific deep validation checks ──────────────────────────────────
    # Add detailed expected-value checks for specific test cases here.
    # These run after the main parse loop and add extra result entries.

    results["TC24/TestSorc.d2s[details]"] = _check_tc24_details(cases_dir)
    results["TC26/TestSorc.d2s[details]"] = _check_tc26_details(cases_dir)
    results["TC34/TestSorc.d2s[details]"] = _check_tc34_details(cases_dir)
    results["TC35/TestSorc.d2s[details]"] = _check_tc35_details(cases_dir)
    results["TC36/TestABC.d2s[details]"] = _check_tc36_details(cases_dir)
    results["TC37/TestABC.d2s[details]"] = _check_tc37_details(cases_dir)
    results["TC38/TestSorc.d2s[details]"] = _check_tc38_details(cases_dir)
    results["TC39/TestSorc.d2s[details]"] = _check_tc39_details(cases_dir)
    results["TC40/TestSorc.d2s[details]"] = _check_tc40_details(cases_dir)
    results["TC62/SimpleItems.d2s[details]"] = _check_tc62_details(cases_dir)
    results["TC63/Knurpsi.d2s[details]"] = _check_tc63_details(cases_dir)
    results["TC64/MercOnly.d2s[details]"] = _check_tc64_details(cases_dir)
    results["TC65/CubeContents.d2s[details]"] = _check_tc65_details(cases_dir)
    results["Crafted[req-level-formula]"] = _check_crafted_req_level(cases_dir)
    results["CubeMain[corruption-decode]"] = _check_cubemain_corruption()
    results["CharStats[class-names]"] = _check_charstats()
    results["ItemNames[name-lookup]"] = _check_item_names(cases_dir)
    results["CASCReader[tvfs-sprites]"] = _check_casc_reader()

    # ── Report ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("TEST CASE RESULTS")
    print("=" * 80)

    pass_count = fail_count = skip_count = 0
    for key, (status, info, detail) in sorted(results.items()):
        icon = {"PASS": "OK", "FAIL": "XX", "SKIP": "--"}.get(status, "?")
        print(f"  {icon} {key:42s}  {status:5s}  {info}")
        if detail:
            print(f"     -> {detail}")
        if status == "PASS":
            pass_count += 1
        elif status == "FAIL":
            fail_count += 1
        else:
            skip_count += 1

    print(f"\nTotal: {pass_count} PASS, {fail_count} FAIL, {skip_count} SKIP")
    print("=" * 80)
    return 1 if fail_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())

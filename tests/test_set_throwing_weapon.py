"""TC76 - Set-quality throwing weapon parsing.

Pins the parser fix for `_parse_misc_throw`: Set-quality throwing
weapons (e.g. Holy Fury / Balrog Spear `7s7`) must read the 5-bit
``set_bonus_mask`` BEFORE the magical-properties block and
process per-tier bonus property lists AFTER the 0x1FF terminator,
mirroring the existing logic for Set melee weapons / Set armor /
Set misc items.

Before the fix, the throwing-weapon path went straight to
``_read_magical_properties`` after reading dur+qty, leaving the
mask bits in the stream. That pushed every property read 5 bits
early, produced six garbage stat reads (35, 89, 128, 304, 341,
355) in place of the four real player-visible properties, and
left 96 unconsumed bits at the end of the item that the parser
re-interpreted as a phantom 'hhwd' item with the impossible
flag combination ``simple AND runeword AND socketed``.

See ``tests/cases/TC76/README.md`` for the in-game tooltip values
that establish the source of truth for this fixture.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

D2S_FIXTURE = PROJECT_ROOT / "tests" / "cases" / "TC76" / "SetThrowingWeapon.d2s"
D2I_FIXTURE = PROJECT_ROOT / "tests" / "cases" / "TC76" / "SetThrowingWeapon.d2i"


@pytest.fixture(scope="module", autouse=True)
def _bootstrap_game_data():
    """Trigger the parser's lazy game-data load."""
    from d2rr_toolkit.game_data.item_types import get_item_type_db
    from d2rr_toolkit.parsers.d2s_parser import D2SParser

    if get_item_type_db().is_loaded():
        return
    try:
        D2SParser(D2S_FIXTURE).parse()
    except Exception:
        pytest.skip("Reimagined Excel base not resolvable (no D2RR install).")


def _find_7s7_d2s():
    from d2rr_toolkit.parsers.d2s_parser import D2SParser

    char = D2SParser(D2S_FIXTURE).parse()
    for it in char.items:
        if it.item_code == "7s7":
            return char, it
    pytest.fail("7s7 not found in D2S fixture")


def _find_7s7_d2i():
    from d2rr_toolkit.parsers.d2i_parser import D2IParser

    sh = D2IParser(D2I_FIXTURE).parse()
    for tab in sh.tabs:
        for it in tab.items:
            if it.item_code == "7s7":
                return sh, tab, it
    pytest.fail("7s7 not found in D2I fixture")


# ---------------------------------------------------------------- #
# S1 - parsers see exactly the documented item layout (no phantoms)
# ---------------------------------------------------------------- #


def test_S1_d2s_no_phantom_in_parsed_items():
    """The D2S parser sees no item with code 'hhwd' AND no item
    with the impossible ``simple AND runeword AND socketed`` flag
    combination. Either presence would mean the throwing-weapon
    Set-quality branch regressed."""
    from d2rr_toolkit.parsers.d2s_parser import D2SParser

    char = D2SParser(D2S_FIXTURE).parse()
    for it in char.items:
        assert it.item_code != "hhwd", (
            f"Phantom 'hhwd' item present at idx {char.items.index(it)} - "
            f"the throwing-weapon Set-quality fix regressed."
        )
        f = it.flags
        impossible = f.simple and f.runeword and f.socketed
        assert not impossible, (
            f"Item {it.item_code!r} has impossible flag combo "
            f"simple+runeword+socketed - parser misalignment regressed."
        )


def test_S1_d2i_no_phantom_in_parsed_items():
    """Same invariant for the D2I shared-stash parser."""
    from d2rr_toolkit.parsers.d2i_parser import D2IParser

    sh = D2IParser(D2I_FIXTURE).parse()
    for tab in sh.tabs:
        for it in tab.items:
            assert it.item_code != "hhwd", (
                "Phantom 'hhwd' in d2i tab - throwing Set-quality fix regressed."
            )
            f = it.flags
            assert not (f.simple and f.runeword and f.socketed), (
                f"Item {it.item_code!r} has impossible flag combination."
            )


def test_S1_d2i_jm_count_matches_parsed_count():
    """Tab 5 (where the 7s7 lives in the d2i fixture) has its
    on-disk JM count matching the number of items the parser
    captures. A mismatch is the load-bearing symptom of the
    Set-throwing parser misalignment cascade."""
    from d2rr_toolkit.parsers.d2i_parser import D2IParser

    sh = D2IParser(D2I_FIXTURE).parse()
    for ti, tab in enumerate(sh.tabs):
        assert tab.jm_item_count == len(tab.items), (
            f"Tab {ti}: JM count {tab.jm_item_count} != parser items "
            f"{len(tab.items)} - parser-extra appearance is the symptom "
            f"of Set-throwing-weapon misalignment."
        )


# ---------------------------------------------------------------- #
# S2 - 7s7 source_data length is 53 bytes (not 41)
# ---------------------------------------------------------------- #


def test_S2_d2s_7s7_source_data_is_53_bytes():
    """The 7s7's source_data must be 53 bytes - the full item
    including its set bonus property lists. Pre-fix, the parser
    captured only 41 bytes and left the trailing 12 bytes as
    a separate 'phantom item'. 53 bytes proves the 5-bit mask
    plus 100 bits of bonus-list data are now correctly consumed
    inside the item."""
    _, item = _find_7s7_d2s()
    assert item.source_data is not None
    assert len(item.source_data) == 53, (
        f"Expected 7s7 source_data to be 53 bytes; got "
        f"{len(item.source_data)} - parser truncating the Set-quality "
        f"set-bonus-list region again?"
    )


def test_S2_d2i_7s7_source_data_is_53_bytes():
    """Same invariant for d2i."""
    _, _, item = _find_7s7_d2i()
    assert item.source_data is not None
    assert len(item.source_data) == 53


# ---------------------------------------------------------------- #
# S3 - set_bonus_mask is 3 (tier-2 + tier-3)
# ---------------------------------------------------------------- #


def test_S3_d2s_set_bonus_mask_is_3():
    """The Holy Fury 7s7 has item-level bonuses for two set tiers:
    37% CTC Chain Lightning at the 2-piece threshold and +6 to
    Charged Strike (oskill) at the 3-piece threshold. The mask
    encodes those as bits 0 and 1 set => decimal 3."""
    _, item = _find_7s7_d2s()
    assert item.set_bonus_mask == 3, (
        f"Expected set_bonus_mask=3 (binary 00011 = tier-2+tier-3); got {item.set_bonus_mask}"
    )


def test_S3_d2i_set_bonus_mask_is_3():
    _, _, item = _find_7s7_d2i()
    assert item.set_bonus_mask == 3


# ---------------------------------------------------------------- #
# S4 - magical_properties matches the in-game tooltip
# ---------------------------------------------------------------- #

EXPECTED_PROPS = [
    (17, 178),  # +178% item_maxdamage_percent
    (18, 178),  # paired with 17 - same value
    (21, 50),  # mindamage (1H weapon damage range min)
    (22, 200),  # maxdamage
    (97, 1),  # item_nonclassskill (oskill marker)
    (159, 50),  # item_throw_mindamage
    (160, 200),  # item_throw_maxdamage
    (253, 25),  # item_replenish_quantity
    (254, 200),  # item_extra_stack
]


def test_S4_d2s_magical_properties_match_tooltip():
    _, item = _find_7s7_d2s()
    actual = [(p.get("stat_id"), p.get("value")) for p in item.magical_properties]
    assert actual == EXPECTED_PROPS, (
        f"D2S 7s7 magical_properties drifted from tooltip values.\n"
        f"  Expected: {EXPECTED_PROPS}\n"
        f"  Actual:   {actual}"
    )


def test_S4_d2i_magical_properties_match_tooltip():
    _, _, item = _find_7s7_d2i()
    actual = [(p.get("stat_id"), p.get("value")) for p in item.magical_properties]
    assert actual == EXPECTED_PROPS


# ---------------------------------------------------------------- #
# S5 - set_bonus_properties contains the item-level set bonuses
# ---------------------------------------------------------------- #


def test_S5_d2s_set_bonus_properties_contain_chain_lightning_ctc():
    """The first set bonus (tier-2 of Wrath of Vengeance) is a
    chance-to-cast Chain Lightning at level 10 with 37% chance."""
    _, item = _find_7s7_d2s()
    # Find a stat with skill_name == 'Chain Lightning'
    found = [p for p in item.set_bonus_properties if p.get("skill_name") == "Chain Lightning"]
    assert found, (
        f"Chain Lightning CTC missing from set_bonus_properties: {item.set_bonus_properties}"
    )
    p = found[0]
    assert p.get("level") == 10
    assert p.get("chance") == 37


def test_S5_d2s_set_bonus_properties_contain_charged_strike_oskill():
    """The second set bonus (tier-3) is +6 to Charged Strike
    as an oskill (item_nonclassskill = stat 97)."""
    _, item = _find_7s7_d2s()
    oskill_entries = [p for p in item.set_bonus_properties if p.get("stat_id") == 97]
    assert oskill_entries, (
        f"Charged Strike oskill missing from set_bonus_properties: {item.set_bonus_properties}"
    )
    p = oskill_entries[0]
    assert p.get("value") == 6, f"Expected +6 to Charged Strike, got value={p.get('value')}"


def test_S5_d2i_set_bonus_properties_match_d2s():
    """The same bonus list should be produced by both parsers,
    because both share the underlying ItemsParserMixin code path."""
    _, item_d2s = _find_7s7_d2s()
    _, _, item_d2i = _find_7s7_d2i()
    assert item_d2s.set_bonus_properties == item_d2i.set_bonus_properties, (
        f"D2S and D2I parsers disagree on Set 7s7 set_bonus_properties:\n"
        f"  D2S: {item_d2s.set_bonus_properties}\n"
        f"  D2I: {item_d2i.set_bonus_properties}"
    )


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    pytest.main([__file__, "-v"])

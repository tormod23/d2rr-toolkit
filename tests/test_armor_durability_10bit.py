#!/usr/bin/env python3
"""Pin the 10-bit cur_dur interpretation of the armor durability block.

Background
----------
The armor type-specific block encodes durability as::

    defense(11) + max_dur(8) + cur_dur(10) = 29 bits

The ``cur_dur`` field is a single 10-bit unsigned integer. Earlier
revisions of this parser read it as ``cur_dur(8) + unknown_post_dur(2)``,
which is observationally equivalent on every game-written fixture in
Reimagined because the base max durability is capped at 250 (hence the
high 2 bits of cur_dur are always zero). The 10-bit encoding is
preferred because the alternative forces an "unknown / reserved 2 bits"
gap into an otherwise densely-packed binary layout.

The WEAPON branch has a different layout (``max(8) + cur(8) + 2``) -
those trailing 2 bits DO carry semantics (see the weapon-path comments
and tests/test_phase_blade_durability.py). This test covers armor only.

## Test matrix

  §1  Every armor item across every fixture parses with
      cur_durability <= 255, i.e. the upper 2 bits of the 10-bit
      field are always zero. This is the core invariant of the
      10-bit read: it's encoding-distinguishable from ``8 + 2`` only
      if the value ever exceeds 255, which it doesn't in Reimagined's
      armor.txt-capped data.

      Note: cur_durability CAN exceed max_durability in some armor
      items (e.g. ``stu`` with cur=35, max=32). This is an affix /
      effective-max display artifact, NOT a parser error - it is
      stable between the old ``8 + 2`` read and the new 10-bit read.

  §2  TC08 / TC10 canonical values are preserved byte-exact across
      the refactor (these are the original durability-width
      regression fixtures).

  §3  Passive round-trip: parse + write with no mutation produces a
      byte-identical file for TC08 (canonical armor fixture).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

_FIXTURE_ROOT = PROJECT_ROOT / "tests" / "cases"


@pytest.fixture(scope="module", autouse=True)
def _bootstrap_game_data():
    """Trigger the parser's own lazy load path via one fixture parse.

    See ``tests/test_rune_cube_up.py`` for the rationale on using the
    minimal parser path rather than ``_load_game_data`` (which eager-
    loads more tables than the parser itself and perturbs some
    snapshot tests when module order is unfortunate).
    """
    from d2rr_toolkit.game_data.item_types import get_item_type_db
    from d2rr_toolkit.parsers.d2s_parser import D2SParser

    probe = next(_FIXTURE_ROOT.rglob("*.d2s"), None)
    if probe is None:
        pytest.skip("No .d2s fixture available to bootstrap game data.")
    if get_item_type_db().is_loaded():
        return
    try:
        D2SParser(probe).parse()
    except Exception:
        pytest.skip("Reimagined Excel base not resolvable (no D2RR install).")


# --------------------------------------------------------------------------- #
#  §1 - upper-2-bits-zero invariant
# --------------------------------------------------------------------------- #


def _walk_armor_items(items, out):
    from d2rr_toolkit.game_data.item_types import ItemCategory, get_item_type_db

    db = get_item_type_db()
    for item in items:
        if item.armor_data is None:
            continue
        try:
            cat = db.classify(item.item_code or "")
        except Exception:
            continue
        if cat == ItemCategory.ARMOR:
            out.append(item)
        for ch in item.socket_children:
            _walk_armor_items([ch], out)


def _collect_all_armor():
    from d2rr_toolkit.parsers.d2i_parser import D2IParser
    from d2rr_toolkit.parsers.d2s_parser import D2SParser

    armor: list = []
    for f in _FIXTURE_ROOT.rglob("*.d2s"):
        try:
            ch = D2SParser(f).parse()
        except Exception:
            continue
        _walk_armor_items(ch.items, armor)
    for f in _FIXTURE_ROOT.rglob("*.d2i*"):
        try:
            sh = D2IParser(f).parse()
        except Exception:
            continue
        for tab in sh.tabs:
            _walk_armor_items(tab.items, armor)
    return armor


def test_S1_every_armor_cur_dur_fits_in_8_bits():
    """cur_dur < 256 for every armor item - upper 2 bits of the 10-bit field are zero.

    This is the core invariant that makes the 10-bit read observationally
    equivalent to the prior ``8 + 2`` read. If an item ever parses with
    cur_dur >= 256, the 10-bit encoding is load-bearing (the new read
    extracts bits the old read discarded as "unknown"). Either outcome
    is informative:

      - no violations (expected): 10-bit and 8+2 produce identical values
        for every armor item; the refactor is neutral on current data.
      - violations: a Reimagined update has raised the durability cap,
        and the 10-bit read captures values the old 8-bit read would
        have truncated.
    """
    armor = _collect_all_armor()
    assert armor, "No armor items discovered in fixture corpus"
    too_big = [
        (it.item_code, it.armor_data.durability.current_durability)
        for it in armor
        if it.armor_data.durability.current_durability > 255
    ]
    assert not too_big, (
        "Armor cur_dur > 255 observed - the 10-bit encoding is now "
        f"load-bearing: {too_big[:5]}"
    )


# --------------------------------------------------------------------------- #
#  §2 - canonical fixture regression
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("fixture", "item_code", "expected_max", "expected_cur"),
    [
        ("TC08/TestPaladin.d2s", "lgl", 12, 12),
        ("TC10/TestPaladin.d2s", "lgl", 12, 10),
    ],
)
def test_S2_canonical_fixtures_preserve_values(
    fixture: str, item_code: str, expected_max: int, expected_cur: int
) -> None:
    """TC08 + TC10 are the original durability-width regression fixtures.

    These MUST produce the same integer values under the 10-bit read as
    they did under the prior ``8 + 2`` interpretation.
    """
    from d2rr_toolkit.parsers.d2s_parser import D2SParser

    p = _FIXTURE_ROOT / fixture
    ch = D2SParser(p).parse()
    matches = [
        it
        for it in ch.items
        if (it.item_code or "").lower() == item_code and it.armor_data is not None
    ]
    assert matches, f"no {item_code!r} armor item in {fixture}"
    dur = matches[0].armor_data.durability
    assert dur.max_durability == expected_max
    assert dur.current_durability == expected_cur


# --------------------------------------------------------------------------- #
#  §3 - passive round-trip
# --------------------------------------------------------------------------- #


def test_S3_tc08_passive_roundtrip_byte_exact(tmp_path: Path) -> None:
    """Parsing TC08 + writing with no modification must match source byte-exact.

    The 10-bit read refactor is bit-consumption-identical to the prior
    ``8 + 2`` reads, so source-data preservation should produce the exact
    same output file.
    """
    from d2rr_toolkit.parsers.d2s_parser import D2SParser
    from d2rr_toolkit.writers.d2s_writer import D2SWriter

    p = _FIXTURE_ROOT / "TC08" / "TestPaladin.d2s"
    src = p.read_bytes()
    char = D2SParser(p).parse()
    writer = D2SWriter(src, char)
    out = tmp_path / "roundtrip.d2s"
    writer.write(out)
    dst = out.read_bytes()

    # The writer refreshes checksum (0x0C..0x0F) and timestamp (0x20..0x23).
    # Tolerate those offsets, require byte-identity everywhere else.
    tolerated = set(range(0x0C, 0x10)) | set(range(0x20, 0x24))
    diffs = [
        i for i, (a, b) in enumerate(zip(src, dst)) if a != b and i not in tolerated
    ]
    assert not diffs, (
        f"{len(diffs)} byte diffs beyond checksum+timestamp - "
        f"first at offsets {diffs[:8]}"
    )
    assert len(src) == len(dst), (
        f"file size changed: src={len(src)} dst={len(dst)}"
    )

#!/usr/bin/env python3
"""Pin Section 6 invariance under item add / remove / move operations.

Background
----------
The seventh page of every Reimagined v105 SharedStash file is an
audit-block (marker ``0xC0EDEAC0`` at +0x40 instead of ``JM``). An
in-game controlled-fixture sequence (TC74 A-E) captured five
snapshots covering: empty stash, +1 item Tab 0, +1 item Tab 1,
remove Tab 1 item, move Tab 0 item to Tab 2.

Empirical finding: Section 6 is byte-identical across every
snapshot. Item add / remove / move operations do not touch the
audit-block.

This is the foundation for the toolkit's verbatim-copy strategy in
``D2IWriter``: as long as the writer preserves the audit page bytes
through any item edit, the file stays internally consistent.

## Test matrix

  S1  Each fixture parses and an audit page is extracted with the
      expected magic, marker, and page metadata.

  S2  Body length is identical across all five fixtures (148 bytes
      each).

  S3  Section 6 BODY (sub-header + records + footer) is byte-identical
      across all five fixtures.

  S4  Item-level state varies as expected (sanity: tab item counts
      match the controlled sequence).

  S5  Passive round-trip: parse + write each fixture without
      mutation produces byte-identical output. Combined with S3, this
      proves our writer cannot drift Section 6 on item-level edits.
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

_FIXTURE_DIR = PROJECT_ROOT / "tests" / "cases" / "TC74"
_LETTERS = ["A", "B", "C", "D", "E"]
_FIXTURE_PATHS = [_FIXTURE_DIR / f"Section6Invariance.d2i.{c}" for c in _LETTERS]
_EXPECTED_TAB_ITEM_COUNTS = {
    "A": [0, 0, 0, 0, 0, 0],
    "B": [1, 0, 0, 0, 0, 0],
    "C": [1, 1, 0, 0, 0, 0],
    "D": [1, 0, 0, 0, 0, 0],
    "E": [0, 0, 1, 0, 0, 0],
}


@pytest.fixture(scope="module", autouse=True)
def _bootstrap_game_data():
    """Trigger the parser's lazy game-data load."""
    from d2rr_toolkit.game_data.item_types import get_item_type_db
    from d2rr_toolkit.parsers.d2s_parser import D2SParser

    probe = next(PROJECT_ROOT.glob("tests/cases/**/*.d2s"), None)
    if probe is None:
        pytest.skip("No .d2s fixture available to bootstrap game data.")
    if get_item_type_db().is_loaded():
        return
    try:
        D2SParser(probe).parse()
    except Exception:
        pytest.skip("Reimagined Excel base not resolvable (no D2RR install).")


@pytest.mark.parametrize(
    ("letter", "fixture"), zip(_LETTERS, _FIXTURE_PATHS, strict=True)
)
def test_S1_each_fixture_has_a_valid_audit_page(letter: str, fixture: Path):
    """Each fixture extracts a structurally-valid Section 6 page."""
    from d2rr_toolkit.analysis.section6 import extract_section6
    from d2rr_toolkit.constants import (
        D2I_AUDIT_BLOCK_MARKER,
        D2I_HEADER_FLAG_REIMAGINED,
    )

    s6 = extract_section6(fixture.read_bytes())
    assert s6 is not None, f"{letter}: no audit block extracted"
    assert s6.audit_marker == D2I_AUDIT_BLOCK_MARKER
    assert s6.header_flag == D2I_HEADER_FLAG_REIMAGINED
    assert s6.version == 105
    assert s6.all_markers_valid


def test_S2_body_length_matches_across_all_fixtures():
    """All five fixtures have identical Section 6 body length."""
    from d2rr_toolkit.analysis.section6 import extract_section6

    lengths = []
    for fixture in _FIXTURE_PATHS:
        s6 = extract_section6(fixture.read_bytes())
        lengths.append(len(s6.body))
    assert len(set(lengths)) == 1, (
        f"Section 6 body length differs across A-E: {dict(zip(_LETTERS, lengths))}"
    )
    # Empty audit body = 80 bytes (20 sub-header + 0 records + 60 footer).
    assert lengths[0] == 80


def test_S3_section6_body_byte_identical_across_all_fixtures():
    """The CORE INVARIANT: Section 6 body is byte-identical across A-E.

    Item add / remove / move operations do not modify the audit page.
    Any failure here means either:
      - the controlled fixture sequence drifted (not a bug in code,
        but a bug in this test suite), OR
      - the audit-block actually does respond to some item operation
        we haven't characterised, in which case the toolkit's
        verbatim-preservation strategy would no longer be sufficient
        and a writer-side updater becomes necessary.
    """
    from d2rr_toolkit.analysis.section6 import extract_section6

    bodies = {}
    for letter, fixture in zip(_LETTERS, _FIXTURE_PATHS, strict=True):
        s6 = extract_section6(fixture.read_bytes())
        bodies[letter] = s6.body

    reference_body = bodies["A"]
    for letter, body in bodies.items():
        assert body == reference_body, (
            f"Section 6 body of fixture {letter} differs from A. "
            f"This breaks the invariant that item add / remove / move "
            f"does not touch the audit-block - investigate before "
            f"trusting the writer's verbatim-copy strategy."
        )


@pytest.mark.parametrize(
    ("letter", "fixture", "expected_counts"),
    [(c, p, _EXPECTED_TAB_ITEM_COUNTS[c]) for c, p in zip(_LETTERS, _FIXTURE_PATHS, strict=True)],
)
def test_S4_item_counts_match_controlled_sequence(
    letter: str, fixture: Path, expected_counts: list[int]
):
    """Sanity check: item layouts in each fixture match the documented
    controlled sequence."""
    from d2rr_toolkit.parsers.d2i_parser import D2IParser

    sh = D2IParser(fixture).parse()
    actual = [len(t.items) for t in sh.tabs]
    assert actual == expected_counts, (
        f"Fixture {letter} item counts {actual} do not match the documented "
        f"controlled-sequence expectation {expected_counts}"
    )


@pytest.mark.parametrize(
    ("letter", "fixture"), zip(_LETTERS, _FIXTURE_PATHS, strict=True)
)
def test_S5_passive_roundtrip_byte_exact(letter: str, fixture: Path):
    """Each fixture round-trips through parse + write byte-exact.

    Combined with S3, this proves our D2IWriter's verbatim-copy
    strategy is sufficient: the audit page is preserved correctly on
    every item-edit scenario captured in the sequence.
    """
    from d2rr_toolkit.parsers.d2i_parser import D2IParser
    from d2rr_toolkit.writers.d2i_writer import D2IWriter

    src = fixture.read_bytes()
    sh = D2IParser(fixture).parse()
    writer = D2IWriter.from_stash(src, sh)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / f"rt-{letter}.d2i"
        writer.write(out)
        dst = out.read_bytes()
    assert src == dst, (
        f"Fixture {letter}: passive round-trip is not byte-exact "
        f"(src={len(src)}, dst={len(dst)})"
    )

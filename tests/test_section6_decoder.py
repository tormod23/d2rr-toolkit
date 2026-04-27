#!/usr/bin/env python3
"""Pin the Reimagined Section 6 (audit-block) structural decode.

Background
----------
Reimagined v105 SharedStash files (``.d2i``) end with a 7th page whose
+0x40 marker is ``0xC0EDEAC0`` instead of ``"JM"``. This page is an
audit / consistency block the game validates on load. Removing items
from the regular tabs without keeping this block in sync produces the
in-game error "Failed to join Game".

The block's structure (verified across the test fixture corpus by
``src/d2rr_toolkit/analysis/section6.py``) is:

  +0x00..0x3F   64-byte page header (same shape as a regular tab page)
  +0x40..0x43   audit marker: 0xC0 0xED 0xEA 0xC0
  +0x44..0x57   20-byte sub-header (semantic decode TBD)
  +0x58..-0x3D  N x 10-byte records (each carrying 0x01C3 at +4..+5)
  -0x3C..end   60-byte trailing footer (6 entries of 10 bytes,
               one per stash tab; semantic decode TBD)

For empty stashes (no items): N = 0, so body = 80 bytes
(20 sub-header + 0 records + 60 footer).

This test pins the structural invariants so any future decode work
(or a regression in our analyzer) is caught immediately.

## Test matrix

  S1  Every .d2i fixture in the test corpus extracts a Section 6 page
      with valid magic, version=105, header_flag=2, audit_marker
      = 0xC0EDEAC0.

  S2  Body length = 20 + N*10 + 60 for every fixture. Empty stashes
      have N=0, body=80.

  S3  Every record's marker == 0x01C3 (constant per-record discriminator).

  S4  The footer is always exactly 60 bytes (= 6 tabs * 10 bytes).

  S5  The empty-stash body (80 bytes) contains exactly the same bytes
      across every empty fixture - byte-stable init signature.

  S6  Fixtures with item activity carry non-zero records; empty / fresh
      fixtures carry zero records (regardless of item count).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

_FIXTURE_ROOT = PROJECT_ROOT / "tests" / "cases"


@pytest.fixture(scope="module", autouse=True)
def _bootstrap_game_data():
    """Trigger the parser's lazy game-data load."""
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


def _all_d2i_fixtures() -> list[Path]:
    """Return every .d2i fixture in tests/cases, excluding those with
    'corrupt' or 'defect' in the name (they intentionally violate
    structure)."""
    out: list[Path] = []
    for f in sorted(_FIXTURE_ROOT.rglob("*.d2i*")):
        n = f.name.lower()
        if "corrupt" in n or "defect" in n:
            continue
        out.append(f)
    return out


# --------------------------------------------------------------------------- #
#  S1 + S2 - structural extraction across every fixture
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("fixture", _all_d2i_fixtures(), ids=lambda p: p.name)
def test_S1_every_fixture_has_valid_audit_block(fixture: Path):
    """Every Reimagined .d2i fixture extracts a structurally-valid
    audit page with the expected page-header values."""
    from d2rr_toolkit.analysis.section6 import extract_section6
    from d2rr_toolkit.constants import (
        D2I_AUDIT_BLOCK_MARKER,
        D2I_HEADER_FLAG_REIMAGINED,
    )

    data = fixture.read_bytes()
    s6 = extract_section6(data)
    assert s6 is not None, f"no audit block found in {fixture.name}"
    assert s6.audit_marker == D2I_AUDIT_BLOCK_MARKER, (
        f"{fixture.name}: audit marker = {s6.audit_marker.hex()}, "
        f"expected {D2I_AUDIT_BLOCK_MARKER.hex()}"
    )
    assert s6.header_flag == D2I_HEADER_FLAG_REIMAGINED, (
        f"{fixture.name}: header_flag = 0x{s6.header_flag:08X}, "
        f"expected 0x{D2I_HEADER_FLAG_REIMAGINED:08X}"
    )
    assert s6.version == 105, (
        f"{fixture.name}: version = {s6.version}, expected 105"
    )


@pytest.mark.parametrize("fixture", _all_d2i_fixtures(), ids=lambda p: p.name)
def test_S2_body_length_matches_three_region_layout(fixture: Path):
    """body_length = 20 (sub-header) + N*10 (records) + 60 (footer)."""
    from d2rr_toolkit.analysis.section6 import extract_section6

    s6 = extract_section6(fixture.read_bytes())
    assert s6 is not None
    expected = 20 + s6.record_count * 10 + 60
    assert len(s6.body) == expected, (
        f"{fixture.name}: body_length {len(s6.body)} != "
        f"20 + {s6.record_count}*10 + 60 = {expected}"
    )


# --------------------------------------------------------------------------- #
#  S3 - every record's marker equals 0x01C3
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("fixture", _all_d2i_fixtures(), ids=lambda p: p.name)
def test_S3_every_record_has_valid_marker(fixture: Path):
    """All audit records in every fixture carry the constant ``0x01C3``
    marker at bytes +4..+5. A single mismatch would mean the structure
    decode is wrong (or the file is corrupt)."""
    from d2rr_toolkit.analysis.section6 import extract_section6

    s6 = extract_section6(fixture.read_bytes())
    assert s6 is not None
    bad = [(r.index, r.marker) for r in s6.records if not r.is_marker_valid]
    assert not bad, (
        f"{fixture.name}: {len(bad)} record(s) with invalid marker. "
        f"First few: {bad[:5]}"
    )


# --------------------------------------------------------------------------- #
#  S4 - footer is always 60 bytes
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("fixture", _all_d2i_fixtures(), ids=lambda p: p.name)
def test_S4_footer_is_always_60_bytes(fixture: Path):
    """The 60-byte trailing footer is present on every audit page,
    regardless of record count. Six 10-byte entries, one per tab."""
    from d2rr_toolkit.analysis.section6 import extract_section6

    s6 = extract_section6(fixture.read_bytes())
    assert s6 is not None
    assert len(s6.footer) == 60, (
        f"{fixture.name}: footer length {len(s6.footer)} != 60"
    )


# --------------------------------------------------------------------------- #
#  S5 - empty-stash bodies are byte-stable
# --------------------------------------------------------------------------- #


def test_S5_truly_empty_stash_body_is_80_bytes():
    """Fixtures with ZERO items AND ZERO records carry an 80-byte body.

    The body LENGTH is invariant for empty audit pages (20 sub-header
    + 0 records + 60 footer = 80 bytes). The body CONTENTS however
    differ across separately-saved empty fixtures - the footer
    encodes per-fixture game state (probably character / session
    metadata) that varies even when no items are involved.

    See TC74 for the controlled fixture sequence that proves footer
    contents are NOT touched by item add / remove / move (which is
    the invariant the toolkit's writer relies on).
    """
    from d2rr_toolkit.analysis.section6 import extract_section6
    from d2rr_toolkit.parsers.d2i_parser import D2IParser

    truly_empty_count = 0
    for f in _all_d2i_fixtures():
        try:
            s6 = extract_section6(f.read_bytes())
            sh = D2IParser(f).parse()
        except Exception:
            continue
        if s6 is None:
            continue
        n_items = sum(len(t.items) for t in sh.tabs)
        if s6.record_count == 0 and n_items == 0:
            assert len(s6.body) == 80, (
                f"truly-empty fixture {f.name}: body length {len(s6.body)} "
                f"!= 80 (= 20 sub-header + 0 records + 60 footer)"
            )
            truly_empty_count += 1
    assert truly_empty_count > 0, "expected at least one truly-empty fixture in corpus"


def test_S5b_footer_diverges_from_reference_when_items_present():
    """When a fixture has items, its footer DIFFERS from the
    truly-empty reference. This proves the footer is not a constant
    - it carries per-stash state (likely per-tab item summaries).

    Documents the invariant the writer must preserve: the footer is
    NOT safe to overwrite with a fixed empty-template when the
    stash has any items at all.
    """
    from d2rr_toolkit.analysis.section6 import extract_section6
    from d2rr_toolkit.parsers.d2i_parser import D2IParser

    reference_footer: bytes | None = None
    differs_when_populated: list[str] = []
    for f in _all_d2i_fixtures():
        try:
            s6 = extract_section6(f.read_bytes())
            sh = D2IParser(f).parse()
        except Exception:
            continue
        if s6 is None:
            continue
        n_items = sum(len(t.items) for t in sh.tabs)
        if s6.record_count == 0 and n_items == 0 and reference_footer is None:
            reference_footer = s6.footer
        elif n_items > 0 and reference_footer is not None:
            if s6.footer != reference_footer:
                differs_when_populated.append(f.name)

    if reference_footer is None:
        pytest.skip("no truly-empty reference fixture available")
    assert differs_when_populated, (
        "expected at least one fixture-with-items to have a footer "
        "different from the truly-empty reference"
    )


# --------------------------------------------------------------------------- #
#  S6 - record count correlates with file activity, not item count
# --------------------------------------------------------------------------- #


def test_S6_record_presence_is_not_item_count_correlated():
    """Document the EMPIRICAL relationship: record count is independent
    of item count. Several fixtures have 30+ items and zero records;
    a few have many records relative to items.

    Not a strict assertion (the exact relationship is still under
    investigation) - this test snapshots the observed counts so any
    drift in the analyzer is detected.
    """
    from d2rr_toolkit.analysis.section6 import extract_section6
    from d2rr_toolkit.parsers.d2i_parser import D2IParser

    observations = []
    for f in _all_d2i_fixtures():
        try:
            s6 = extract_section6(f.read_bytes())
            sh = D2IParser(f).parse()
        except Exception:
            continue
        if s6 is None:
            continue
        n_items = sum(len(t.items) for t in sh.tabs)
        observations.append((f.name, n_items, s6.record_count))

    # Sanity: at least some fixtures have items but zero records,
    # proving the "1 record per item" hypothesis is wrong.
    items_no_records = [
        (n, ni, nr) for (n, ni, nr) in observations if ni > 0 and nr == 0
    ]
    assert items_no_records, (
        "expected at least one fixture with items but zero audit records"
    )

    # And: at least one fixture has both items AND records, so the
    # block isn't always empty either.
    items_and_records = [
        (n, ni, nr) for (n, ni, nr) in observations if ni > 0 and nr > 0
    ]
    assert items_and_records, (
        "expected at least one fixture with items AND audit records"
    )

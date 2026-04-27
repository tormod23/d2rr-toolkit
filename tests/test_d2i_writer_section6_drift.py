"""D2IWriter must fail loudly if Section 6 (audit block) drifts.

## Why

The Reimagined audit block (page 7, marker ``0xC0EDEAC0``) is supposed
to be byte-identical between the writer's source and its output. The
writer's strategy is verbatim trailer-copy: anything past the last
``JM`` section is appended unchanged from the source, which trivially
preserves the audit page.

Empirically (TC74 A-E) the audit block does NOT respond to item
add / remove / move operations - so any in-game-legitimate edit the
toolkit performs MUST also leave the page intact. If a future writer
change ever breaks that invariant, the SharedStash silently
desynchronises with the game's internal audit data and the user
eventually hits "Failed to join Game".

## What this test pins

The new ``_check_section6_preserved`` integrity check. Each test
either:

  - confirms the check passes for normal writer behaviour, or
  - simulates a writer bug (Section 6 corrupted or dropped) and
    verifies the check raises ``D2IWriterIntegrityError`` BEFORE the
    bad bytes can be written to disk.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from d2rr_toolkit.analysis.section6 import extract_section6  # noqa: E402
from d2rr_toolkit.parsers.d2i_parser import D2IParser  # noqa: E402
from d2rr_toolkit.writers.d2i_writer import (  # noqa: E402
    D2IWriter,
    D2IWriterIntegrityError,
    _find_sections,
)

TC74_DIR = PROJECT_ROOT / "tests" / "cases" / "TC74"
SOURCE_FIXTURE = TC74_DIR / "Section6Invariance.d2i.A"


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


# ─────────────────────────────────────────────────────────────────────
# Happy path: Section 6 is preserved on a normal write.
# ─────────────────────────────────────────────────────────────────────


def test_passive_roundtrip_preserves_section6():
    """A no-op build (no item changes) must keep Section 6 byte-identical.

    The writer's verbatim trailer-copy path picks up the audit block
    along with any other trailing bytes. If this test fails the writer
    is corrupting the trailer somehow."""
    source = SOURCE_FIXTURE.read_bytes()
    stash = D2IParser(SOURCE_FIXTURE).parse()
    writer = D2IWriter.from_stash(source, stash)
    built = bytes(writer.build())

    src_s6 = extract_section6(source)
    built_s6 = extract_section6(built)
    assert src_s6 is not None and built_s6 is not None
    src_page = source[src_s6.file_offset : src_s6.file_offset + src_s6.page_size]
    built_page = built[built_s6.file_offset : built_s6.file_offset + built_s6.page_size]
    assert (
        src_page == built_page
    ), "Passive build mutated Section 6 - the trailer-copy path is broken."


def test_item_edit_preserves_section6():
    """Adding/removing items must not touch Section 6 (TC74 invariant).

    Use TC74.B (1 item in tab 0) and remove the item. Section 6 must
    remain byte-identical to the original."""
    source = (TC74_DIR / "Section6Invariance.d2i.B").read_bytes()
    stash = D2IParser(TC74_DIR / "Section6Invariance.d2i.B").parse()
    if not stash.tabs[0].items:
        pytest.skip("TC74.B fixture unexpectedly has no items in tab 0.")

    writer = D2IWriter.from_stash(source, stash)
    writer._tab_items[0].clear()  # noqa: SLF001 - empty tab 0
    built = bytes(writer.build())

    src_s6 = extract_section6(source)
    built_s6 = extract_section6(built)
    src_page = source[src_s6.file_offset : src_s6.file_offset + src_s6.page_size]
    built_page = built[built_s6.file_offset : built_s6.file_offset + built_s6.page_size]
    assert src_page == built_page, (
        "Removing an item drifted Section 6 - the writer is touching "
        "the audit page where it shouldn't."
    )


# ─────────────────────────────────────────────────────────────────────
# Drift: writer bug corrupts Section 6 -> integrity check must raise.
# ─────────────────────────────────────────────────────────────────────


def test_drift_in_audit_marker_is_detected():
    """If the built output's audit marker differs from the source's, the
    integrity check must raise ``D2IWriterIntegrityError`` with a clear
    diagnostic.

    Simulates a writer bug by monkey-patching ``build()`` to flip a byte
    inside Section 6 before the self-check runs."""
    source = SOURCE_FIXTURE.read_bytes()
    stash = D2IParser(SOURCE_FIXTURE).parse()
    writer = D2IWriter.from_stash(source, stash)

    # Capture the original build, mutate one byte inside Section 6, then
    # call _self_check directly to verify it catches the corruption.
    src_s6 = extract_section6(source)
    assert src_s6 is not None

    original_built = bytearray(writer.build())  # baseline (clean) build
    # Flip a byte inside the body region (after the audit marker).
    body_offset = src_s6.file_offset + 0x44 + 5  # 5 bytes into the body
    assert body_offset < len(original_built)
    original_built[body_offset] ^= 0xFF

    with pytest.raises(D2IWriterIntegrityError, match="Section 6.*drifted"):
        writer._self_check(bytes(original_built))  # noqa: SLF001


def test_drift_in_sub_header_is_detected():
    """Even a single-byte mutation in the 20-byte sub-header must trip
    the check - documents the strict byte-equality semantics."""
    source = SOURCE_FIXTURE.read_bytes()
    stash = D2IParser(SOURCE_FIXTURE).parse()
    writer = D2IWriter.from_stash(source, stash)
    src_s6 = extract_section6(source)
    assert src_s6 is not None

    built = bytearray(writer.build())
    # Sub-header sits at body offset 0..19. Flip byte 10.
    sub_header_offset = src_s6.file_offset + 0x44 + 10
    built[sub_header_offset] ^= 0xAA

    with pytest.raises(D2IWriterIntegrityError, match="first diff at offset"):
        writer._self_check(bytes(built))  # noqa: SLF001


def test_drift_in_footer_is_detected():
    """Mutating the trailing 60-byte footer must also trip the check.

    The footer encodes per-tab summary state (the part that varies
    across separately-saved fixtures). Any unexpected change there
    means the writer overstepped."""
    source = SOURCE_FIXTURE.read_bytes()
    stash = D2IParser(SOURCE_FIXTURE).parse()
    writer = D2IWriter.from_stash(source, stash)
    src_s6 = extract_section6(source)
    assert src_s6 is not None

    built = bytearray(writer.build())
    # Footer = last 60 bytes of the page. Flip byte 5 from the end.
    footer_offset = src_s6.file_offset + src_s6.page_size - 5
    built[footer_offset] ^= 0x55

    with pytest.raises(D2IWriterIntegrityError, match="Section 6.*drifted"):
        writer._self_check(bytes(built))  # noqa: SLF001


def test_dropped_section6_is_detected():
    """If the built output keeps the trailer-byte budget but the audit
    page itself is no longer extractable (e.g. signature trashed by a
    future bug), the Section 6 check must raise.

    Crafted to bypass the existing trailer-size check (which already
    catches outright truncation): we keep the same number of trailer
    bytes but corrupt the audit page's signature so
    ``extract_section6`` returns None on the built output."""
    source = SOURCE_FIXTURE.read_bytes()
    stash = D2IParser(SOURCE_FIXTURE).parse()
    writer = D2IWriter.from_stash(source, stash)
    src_s6 = extract_section6(source)
    assert src_s6 is not None

    built = bytearray(writer.build())
    # Wipe the audit page header signature to simulate "page is gone"
    # without changing the trailer length.
    struct.pack_into("<I", built, src_s6.file_offset, 0x00000000)

    with pytest.raises(D2IWriterIntegrityError, match="dropped Section 6"):
        writer._self_check(bytes(built))  # noqa: SLF001


# ─────────────────────────────────────────────────────────────────────
# No-op: vanilla files (no audit block) must not trip the check.
# ─────────────────────────────────────────────────────────────────────


def test_check_skips_when_source_has_no_audit_block():
    """Files without an audit block (vanilla D2R, malformed Reimagined,
    or otherwise non-v105 inputs) must NOT raise. The check is a
    detection helper, not a Reimagined enforcement gate."""
    # Synthesize a "vanilla" D2I by mutating the audit marker in a
    # Reimagined fixture so extract_section6 returns None.
    source = bytearray(SOURCE_FIXTURE.read_bytes())
    src_s6 = extract_section6(bytes(source))
    assert src_s6 is not None  # premise: TC74.A is Reimagined

    # Wipe the marker AND advance the page-walk past the audit page by
    # zeroing the page-header signature too. Both together guarantee
    # extract_section6() returns None.
    audit_offset = src_s6.file_offset + 0x40
    source[audit_offset : audit_offset + 4] = b"\x00\x00\x00\x00"
    struct.pack_into("<I", source, src_s6.file_offset, 0x00000000)

    assert extract_section6(bytes(source)) is None, (
        "test premise broken: synthesised vanilla buffer still extracts " "an audit block"
    )

    # Build a writer with this synthetic vanilla source. The check must
    # be a no-op (no exception) because there's nothing to compare to.
    # We use a stripped-down writer call: just _check_section6_preserved
    # directly so we don't need a parseable file.
    writer = D2IWriter.__new__(D2IWriter)
    writer._source = bytes(source)  # noqa: SLF001
    # built can be anything - the check returns early before inspecting it.
    writer._check_section6_preserved(b"")  # noqa: SLF001 - must not raise


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    pytest.main([__file__, "-v"])

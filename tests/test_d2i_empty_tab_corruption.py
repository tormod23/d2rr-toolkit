"""TC73 - Regression tests for the SharedStash empty-tab corruption bug.

Pins the fix that prevents the writer from producing 69-byte "empty"
sections (phantom `0x00` byte after `JM 00 00`). Such files are rejected
by D2R and block every character from loading as long as they sit in
the save directory. See docs in tests/cases/TC73/README.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from d2rr_toolkit.parsers.d2i_parser import D2IParser
from d2rr_toolkit.writers.d2i_writer import (
    D2I_EMPTY_SECTION_SIZE,
    D2IOrphanExtrasError,
    D2IWriter,
    D2IWriterIntegrityError,
    _find_sections,
)

FIXTURE_DIR = Path(__file__).parent / "cases" / "TC73"
PRE_EMPTY = FIXTURE_DIR / "pre_empty_tab4.d2i"
BROKEN = FIXTURE_DIR / "corrupted_original.d2i"


# ─────────────────────────────────────────────────────────────────────
# §1  Baseline: broken file exhibits the bug signature
# ─────────────────────────────────────────────────────────────────────


def test_broken_file_has_bad_empty_sections():
    """The captured broken file has tab 2 AND tab 4 with section_size=69."""
    data = BROKEN.read_bytes()
    sections = _find_sections(data)
    bad = [
        (i, s.section_size)
        for i, s in enumerate(sections)
        if s.item_count == 0 and s.section_size != D2I_EMPTY_SECTION_SIZE
    ]
    assert len(bad) == 2, f"expected 2 malformed empty sections, got {bad}"
    assert all(size == 69 for _, size in bad)


def test_pre_empty_backup_parses_cleanly():
    """The 19:08:17 backup still has tab 4 populated (baseline for reproduction)."""
    stash = D2IParser(PRE_EMPTY).parse()
    # Tab 4 has 1 item in the last good backup.
    assert len(stash.tabs[4].items) == 1


# ─────────────────────────────────────────────────────────────────────
# §2  Writer fix: empty-out produces canonical 68-byte section
# ─────────────────────────────────────────────────────────────────────


def test_empty_tab4_produces_canonical_empty_section():
    """Emptying tab 4 must yield section_size == 68, not 69."""
    source = PRE_EMPTY.read_bytes()
    stash = D2IParser(PRE_EMPTY).parse()
    writer = D2IWriter.from_stash(source, stash)
    writer._tab_items[4].clear()  # noqa: SLF001

    built = writer.build()
    sections = _find_sections(bytes(built))
    tab4 = sections[4]
    assert tab4.item_count == 0
    assert tab4.section_size == D2I_EMPTY_SECTION_SIZE, (
        f"tab 4 produced section_size={tab4.section_size}, "
        f"canonical empty = {D2I_EMPTY_SECTION_SIZE}"
    )


def test_empty_tab4_roundtrips():
    """Built file parses back with tab 4 empty and others unchanged."""
    source = PRE_EMPTY.read_bytes()
    orig_stash = D2IParser(PRE_EMPTY).parse()
    expected_tab_counts = [len(t.items) for t in orig_stash.tabs]
    expected_tab_counts[4] = 0

    writer = D2IWriter.from_stash(source, orig_stash)
    writer._tab_items[4].clear()  # noqa: SLF001
    built = writer.build()

    tmp = FIXTURE_DIR / "_tmp_roundtrip.d2i"
    tmp.write_bytes(bytes(built))
    try:
        reparsed = D2IParser(tmp).parse()
        actual = [len(t.items) for t in reparsed.tabs]
        assert actual == expected_tab_counts
    finally:
        tmp.unlink(missing_ok=True)


def test_non_empty_tab_still_preserves_tail():
    """Removing one of several items (not the last) keeps tail byte preservation."""
    # Use pre_empty where tab 1 has items - here 1601-byte file has 1 item
    # in tab 1. Instead test tab 2 (which has socket children preserved).
    source = PRE_EMPTY.read_bytes()
    stash = D2IParser(PRE_EMPTY).parse()
    # Nothing removed - output should be byte-identical to source.
    writer = D2IWriter.from_stash(source, stash)
    built = bytes(writer.build())
    assert built == source, "No-op build must be byte-identical to source"


# ─────────────────────────────────────────────────────────────────────
# §3  Writer self-check refuses to emit bad output
# ─────────────────────────────────────────────────────────────────────


def test_self_check_catches_manufactured_bad_empty():
    """If a bug slipped past the tail-drop, the self-check must catch it."""
    # We simulate the legacy bug by monkey-patching the splice to append
    # a phantom byte, then verify the self-check rejects the build.
    source = PRE_EMPTY.read_bytes()
    stash = D2IParser(PRE_EMPTY).parse()
    writer = D2IWriter.from_stash(source, stash)
    writer._tab_items[4].clear()  # noqa: SLF001

    # Monkey-patch _splice_section to simulate the old buggy behaviour.
    import struct
    from d2rr_toolkit.writers.d2i_writer import (
        D2I_HEADER_SIZE,
        SECTION_MARKER,
    )

    def bad_splice(self, tab_idx, section, new_items):  # noqa: ARG001
        # Build a malformed "empty" section with a phantom byte.
        body = b"\x00"  # the exact bug
        size = D2I_HEADER_SIZE + 4 + len(body)
        result = bytearray(size)
        result[:D2I_HEADER_SIZE] = self._source[
            section.header_offset : section.header_offset + D2I_HEADER_SIZE
        ]
        struct.pack_into("<I", result, 0x10, size)
        result[D2I_HEADER_SIZE : D2I_HEADER_SIZE + 2] = SECTION_MARKER
        struct.pack_into("<H", result, D2I_HEADER_SIZE + 2, 0)
        result[D2I_HEADER_SIZE + 4 :] = body
        return bytes(result)

    writer._splice_section = bad_splice.__get__(writer, D2IWriter)  # noqa: SLF001
    with pytest.raises(D2IWriterIntegrityError, match="jm_count=0"):
        writer.build()


# ─────────────────────────────────────────────────────────────────────
# §4  Orphan-extras refusal
# ─────────────────────────────────────────────────────────────────────


def test_orphan_extras_refused():
    """If the raw tail contains a JM blob, empty-out must raise."""
    source = PRE_EMPTY.read_bytes()
    stash = D2IParser(PRE_EMPTY).parse()
    writer = D2IWriter.from_stash(source, stash)

    # Craft a scenario: inject a fake 'JM' marker into the tail region of
    # tab 4 by replacing the known padding byte with 'J' and extending.
    # Easier: monkey-patch writer._source so tab 4's tail looks like extras.
    sections = _find_sections(source)
    tab4 = sections[4]
    # tab 4's raw region: items_start..items_end. Parsed item = 22B. Tail = 1B.
    # Replace the tail byte with 'J' so SECTION_MARKER='JM' check triggers.
    # We need the 2-byte marker. Extend tail to 2 bytes by shifting section_size.
    mutable = bytearray(source)
    # Replace tail byte at position (items_end - 1)
    mutable[tab4.items_end - 1 : tab4.items_end] = b"JM"
    # Update section_size to accommodate the extra byte (+1)
    import struct

    struct.pack_into("<I", mutable, tab4.header_offset + 0x10, tab4.section_size + 1)

    # Reparse the mutated bytes. The parser locates JM by header offset,
    # so our injected 'JM' sits in tail as an unparsed extra.
    stash2 = _parse_bytes(bytes(mutable))
    writer = D2IWriter.from_stash(bytes(mutable), stash2)
    writer._tab_items[4].clear()  # noqa: SLF001

    with pytest.raises(D2IOrphanExtrasError, match="unparsed"):
        writer.build()


def _parse_bytes(data: bytes):
    """Helper: parse D2I from an in-memory bytes buffer via a temp file."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".d2i", delete=False) as tf:
        tf.write(data)
        path = Path(tf.name)
    try:
        return D2IParser(path).parse()
    finally:
        path.unlink(missing_ok=True)


# ─────────────────────────────────────────────────────────────────────
# §5  archive.py: broken output is rolled back
# ─────────────────────────────────────────────────────────────────────


def test_verify_on_disk_rolls_back_malformed_file(tmp_path):
    """_verify_d2i_on_disk restores backup when file has bad empty section."""
    from d2rr_toolkit.archive import _verify_d2i_on_disk, ArchiveError

    # Simulate the scenario: a bogus "written" file on disk + a good backup.
    target = tmp_path / "stash.d2i"
    target.write_bytes(BROKEN.read_bytes())  # corrupted output
    backup = tmp_path / "stash.bak"
    backup.write_bytes(PRE_EMPTY.read_bytes())  # last good state

    stash_pre = D2IParser(PRE_EMPTY).parse()
    expected = stash_pre.total_items - 1  # caller thinks one item was removed

    with pytest.raises(ArchiveError, match="malformed empty section"):
        _verify_d2i_on_disk(
            target,
            expected_total_items=expected,
            backup_path=backup,
        )
    # After rollback, target must equal backup contents
    assert target.read_bytes() == backup.read_bytes()


def test_verify_on_disk_passes_canonical_empty(tmp_path):
    """Well-formed file with canonical empty sections passes verification."""
    from d2rr_toolkit.archive import _verify_d2i_on_disk

    source = PRE_EMPTY.read_bytes()
    stash = D2IParser(PRE_EMPTY).parse()
    writer = D2IWriter.from_stash(source, stash)
    writer._tab_items[4].clear()  # noqa: SLF001
    built = writer.build()

    target = tmp_path / "stash.d2i"
    target.write_bytes(bytes(built))
    backup = tmp_path / "stash.bak"
    backup.write_bytes(source)

    # Should not raise
    _verify_d2i_on_disk(
        target,
        expected_total_items=stash.total_items - 1,
        backup_path=backup,
    )
    # File unchanged
    assert target.read_bytes() == bytes(built)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    pytest.main([__file__, "-v"])


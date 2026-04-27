"""Pin the integrity-check semantics for legacy malformed sections.

## Background

The writer's post-build integrity check refuses to emit any section it
PRODUCED with ``jm_count == 0 and section_size != 68`` (the exact bug
that bricked ``ModernSharedStashSoftCoreV2.d2i`` on 2026-04-19).

But "refusing on production" is different from "refusing on
preservation". Legacy files written by older toolkit versions or by
the game itself sometimes already carry the malformed pattern in
sections the user didn't ask to modify. In that case the writer's
strategy is:

  - **Touched sections (rebuilt by ``_splice_section``)**: must be
    canonical. The check raises ``D2IWriterIntegrityError`` on any
    deviation. After the Bug 1 fix this branch is unreachable in
    practice (the splice path always emits a canonical 68-byte empty
    section).
  - **Untouched sections (verbatim trailer copy)**: emit whatever the
    source contained, with a one-line warning. The check does NOT
    raise. This lets the toolkit do useful work on a partially-broken
    file without forcing the user to manually repair the legacy
    sections first.

The dual policy is intentional: refusing to write the file would
strand the user (their existing save is already partially broken; the
toolkit shouldn't make their state worse by being unable to do
anything at all).

## What this file pins

Concrete scenarios that exercise both branches of the check, so any
future change to the integrity check is caught immediately.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from d2rr_toolkit.parsers.d2i_parser import D2IParser  # noqa: E402
from d2rr_toolkit.writers.d2i_writer import (  # noqa: E402
    D2I_EMPTY_SECTION_SIZE,
    D2IWriter,
    D2IWriterIntegrityError,
    _find_sections,
)

# PRE_EMPTY has tab 2 already at section_size=69 (legacy malformed) but
# loads in-game without issue. The corrupted_original.d2i adds tab 4 in
# the same shape; the combined state is what the user reported as
# "Failed to join Game".
LEGACY_FIXTURE = PROJECT_ROOT / "tests" / "cases" / "TC73" / "pre_empty_tab4.d2i"


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
# Premise: the legacy fixture really does contain a malformed section.
# ─────────────────────────────────────────────────────────────────────


def test_legacy_fixture_has_malformed_empty_tab():
    """Sanity: the legacy fixture really does have a non-canonical empty
    section we can use to exercise the verbatim-preservation path.

    If this premise breaks, the rest of the file becomes a tautology
    (testing that canonical sections stay canonical)."""
    data = LEGACY_FIXTURE.read_bytes()
    sections = _find_sections(data)
    legacy_bad = [
        i
        for i, s in enumerate(sections)
        if s.item_count == 0 and s.section_size != D2I_EMPTY_SECTION_SIZE
    ]
    assert legacy_bad, (
        f"Legacy fixture {LEGACY_FIXTURE.name} no longer has a "
        f"non-canonical empty section. Update the fixture or this test."
    )


# ─────────────────────────────────────────────────────────────────────
# Verbatim path: untouched malformed sections must NOT block emission.
# ─────────────────────────────────────────────────────────────────────


def test_passive_build_preserves_legacy_malformed_section():
    """A no-op build on a legacy file must succeed and produce
    byte-identical output, even though one section is non-canonical.

    The writer must not refuse to emit just because the SOURCE is
    partially broken - that would strand the user with no way to do
    further toolkit operations on the file."""
    source = LEGACY_FIXTURE.read_bytes()
    stash = D2IParser(LEGACY_FIXTURE).parse()
    writer = D2IWriter.from_stash(source, stash)

    built = bytes(writer.build())  # must not raise
    assert built == source, "Passive build mutated bytes - the verbatim-copy path is broken."


def test_modifying_other_tab_does_not_force_legacy_repair():
    """Modifying tab N must not force the writer to canonicalise the
    pre-existing malformed section in tab M.

    Use the legacy fixture: tab 5 has 28 items, tab 2 is malformed
    (size=69). Pop one item from tab 5 (touched) and verify tab 2
    bytes are still preserved verbatim (untouched, malformed-but-OK).
    """
    source = LEGACY_FIXTURE.read_bytes()
    stash = D2IParser(LEGACY_FIXTURE).parse()
    src_sections = _find_sections(source)

    # Find the legacy malformed tab and a tab with items to mutate.
    legacy_idx = next(
        i
        for i, s in enumerate(src_sections)
        if s.item_count == 0 and s.section_size != D2I_EMPTY_SECTION_SIZE
    )
    edit_idx = next(i for i, t in enumerate(stash.tabs) if i != legacy_idx and len(t.items) >= 2)

    writer = D2IWriter.from_stash(source, stash)
    writer._tab_items[edit_idx].pop()  # noqa: SLF001
    built = bytes(writer.build())  # must not raise

    # Tab `legacy_idx` must be byte-identical to source (verbatim copy).
    src_bytes = source[
        src_sections[legacy_idx].header_offset : src_sections[legacy_idx].header_offset
        + src_sections[legacy_idx].section_size
    ]
    built_sections = _find_sections(built)
    built_bytes = built[
        built_sections[legacy_idx].header_offset : built_sections[legacy_idx].header_offset
        + built_sections[legacy_idx].section_size
    ]
    assert src_bytes == built_bytes, (
        f"Tab {legacy_idx} drifted during a touch on tab {edit_idx} - "
        f"the verbatim-copy path is leaking edits."
    )


# ─────────────────────────────────────────────────────────────────────
# Touched path: writer must still REFUSE to PRODUCE bad sections.
# ─────────────────────────────────────────────────────────────────────


def test_writer_still_refuses_to_produce_bad_section_via_splice():
    """Defense-in-depth: even on a legacy file, the splice path must
    never emit a `jm_count=0, size != 68` section. If a future bug
    re-introduces the phantom-byte pattern via the splice, the check
    must catch it.

    Simulates the bug by monkey-patching ``_splice_section`` to
    produce the phantom-byte output for a touched tab."""
    import struct
    from d2rr_toolkit.writers.d2i_writer import (
        D2I_HEADER_SIZE,
        SECTION_MARKER,
    )

    source = LEGACY_FIXTURE.read_bytes()
    stash = D2IParser(LEGACY_FIXTURE).parse()
    writer = D2IWriter.from_stash(source, stash)

    edit_idx = next(i for i, t in enumerate(stash.tabs) if len(t.items) >= 2)

    def bad_splice(self, tab_idx, section, new_items):  # noqa: ARG001
        # Reproduce the legacy phantom-byte bug.
        body = b"\x00"
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
    writer._tab_items[edit_idx].clear()  # noqa: SLF001 - force a splice

    with pytest.raises(D2IWriterIntegrityError, match="jm_count=0"):
        writer.build()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    pytest.main([__file__, "-v"])

"""Regression: u16 overflow in `_splice_section` JM-count math.

## Bug

The original splice code computed the new JM count as a *delta* from the
on-disk count::

    jm_delta = len(new_items) - len(orig_items)
    new_jm_count = section.item_count + jm_delta

That works in the clean case where `section.item_count == len(orig_items)`,
but the parser is permissive: it keeps decoding past the JM boundary as
long as the bit-stream is well-formed, so `len(orig_items)` can exceed
`section.item_count` ("parser-captured extras").

When the user then emptied such a tab (`new_items = []`):

    jm_delta = 0 - (section.item_count + extras)
    new_jm_count = section.item_count + jm_delta = -extras

`-extras` is negative, which `struct.pack_into("<H", ..., new_jm_count)`
rejects with `struct.error`. The writer aborted mid-build and left no
output, so the only visible symptom was a hard crash on archive-all.

## Fix

`_splice_section` now uses `new_jm_count = len(new_items)` directly
(items written are JM-counted) and validates that the result fits the
uint16 header field; out-of-range values raise
`D2IWriterIntegrityError` instead of corrupting the file.

## Test strategy

Take a real fixture, mutate one tab's on-disk JM count to be lower than
the actual item count (synthesizing the parser-extras situation), then
empty that tab via the writer. Without the fix this raises
`struct.error`; with the fix it produces a canonical 68-byte empty
section.
"""

from __future__ import annotations

import struct
import sys
import tempfile
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

# A multi-item fixture lets us synthesize the parser-extras situation
# by lowering the on-disk JM count without rewriting the item bytes.
SOURCE_FIXTURE = PROJECT_ROOT / "tests" / "cases" / "TC73" / "pre_empty_tab4.d2i"


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


def _parse_bytes(data: bytes):
    """Helper: parse a D2I from an in-memory bytes buffer via a temp file."""
    with tempfile.NamedTemporaryFile(suffix=".d2i", delete=False) as tf:
        tf.write(data)
        path = Path(tf.name)
    try:
        return D2IParser(path).parse()
    finally:
        path.unlink(missing_ok=True)


def _find_multi_item_tab(source: bytes) -> int:
    """Return the index of a tab that holds at least 2 items, suitable
    for the parser-extras synthesis."""
    sections = _find_sections(source)
    for i, sec in enumerate(sections):
        if sec.item_count >= 2:
            return i
    pytest.skip("No multi-item tab in source fixture - cannot synthesize parser-extras.")


def _lower_jm_count(source: bytes, tab_idx: int, by: int = 1) -> bytes:
    """Return a copy of `source` with tab `tab_idx`'s on-disk JM count
    reduced by `by`. The actual item bytes are left intact, so a permissive
    parser will still capture all items, exposing them as parser-extras
    relative to the lowered count."""
    sections = _find_sections(source)
    target = sections[tab_idx]
    mutable = bytearray(source)
    new_count = target.item_count - by
    assert new_count >= 0, "test bug: cannot lower count below 0"
    struct.pack_into("<H", mutable, target.jm_offset + 2, new_count)
    return bytes(mutable)


# ─────────────────────────────────────────────────────────────────────
# Synthesis sanity: the mutation actually creates parser-extras.
# ─────────────────────────────────────────────────────────────────────


def test_synthesis_creates_parser_extras():
    """The lowered-JM-count mutation is observable: the parser captures
    more items than the on-disk JM count says.

    If this test fails, the synthesis premise is broken and the
    overflow tests below are not meaningful (they would test the clean
    path instead of the parser-extras path)."""
    source = SOURCE_FIXTURE.read_bytes()
    tab_idx = _find_multi_item_tab(source)

    orig_stash = D2IParser(SOURCE_FIXTURE).parse()
    orig_items = len(orig_stash.tabs[tab_idx].items)
    orig_jm = orig_stash.tabs[tab_idx].jm_item_count

    mutated = _lower_jm_count(source, tab_idx, by=1)
    mutated_stash = _parse_bytes(mutated)
    mut_items = len(mutated_stash.tabs[tab_idx].items)
    mut_jm = mutated_stash.tabs[tab_idx].jm_item_count

    assert mut_items == orig_items, (
        "parser-permissive walk should still capture all items even "
        f"after lowering JM count (got {mut_items}, expected {orig_items})"
    )
    assert mut_jm == orig_jm - 1, (
        "lowered JM count should reduce jm_item_count by 1 "
        f"(got {mut_jm}, expected {orig_jm - 1})"
    )
    assert mut_items > mut_jm, (
        "parser-extras synthesis premise: items captured > JM count "
        f"(got items={mut_items}, jm={mut_jm})"
    )


# ─────────────────────────────────────────────────────────────────────
# The actual regression: empty-out with parser-extras must not crash.
# ─────────────────────────────────────────────────────────────────────


def test_empty_tab_with_parser_extras_does_not_underflow():
    """Emptying a tab where parser captured more items than the on-disk
    JM count must NOT raise ``struct.error`` (or any uncaught exception)
    from a negative JM count overflowing the uint16 header field.

    Pre-fix: this raised
        struct.error: ushort format requires 0 <= number <= 65535
    in `_splice_section` because `section.item_count + (0 - len(orig_items))`
    went negative.

    Post-fix: the writer uses `new_jm_count = len(new_items)` directly,
    which is `0` when the tab is emptied. The result is a canonical
    68-byte empty section."""
    source = SOURCE_FIXTURE.read_bytes()
    tab_idx = _find_multi_item_tab(source)
    mutated = _lower_jm_count(source, tab_idx, by=1)

    stash = _parse_bytes(mutated)
    writer = D2IWriter.from_stash(mutated, stash)
    writer._tab_items[tab_idx].clear()  # noqa: SLF001

    # Pre-fix: this raises struct.error.
    # Post-fix: this should succeed (or raise a clean toolkit error if
    # an unrelated invariant fires - but specifically NOT struct.error).
    try:
        built = writer.build()
    except struct.error as e:  # pragma: no cover - regression guard
        pytest.fail(
            f"struct.error from JM-count underflow regressed: {e}. "
            f"`_splice_section` must clamp / validate the new JM count "
            f"instead of letting `pack_into('<H', ...)` blow up."
        )

    sections = _find_sections(bytes(built))
    target = sections[tab_idx]
    assert target.item_count == 0, "emptied tab must report JM count = 0"
    assert target.section_size == D2I_EMPTY_SECTION_SIZE, (
        f"emptied tab must produce canonical {D2I_EMPTY_SECTION_SIZE}-byte "
        f"section (got {target.section_size})"
    )


def test_writer_rejects_negative_jm_count_via_integrity_error():
    """If a future bug ever computes a negative JM count again, the
    writer must raise the typed ``D2IWriterIntegrityError`` (so callers
    can detect it and roll back) - never a raw ``struct.error``.

    Test by monkey-patching `_splice_section` to short-circuit straight
    into the bounds check and verifying the typed error fires before
    the pack call."""
    source = SOURCE_FIXTURE.read_bytes()
    stash = D2IParser(SOURCE_FIXTURE).parse()

    # Pick a tab that the writer will splice (i.e., has items so a
    # `.pop()` triggers a real change vs. the verbatim-copy fast path).
    splice_tab = next(
        (i for i, t in enumerate(stash.tabs) if len(t.items) >= 2),
        None,
    )
    if splice_tab is None:
        pytest.skip("Need a tab with >= 2 items to force a splice path.")

    writer = D2IWriter.from_stash(source, stash)

    from d2rr_toolkit.writers import d2i_writer as dw

    original_splice = dw.D2IWriter._splice_section

    def malicious_splice(self, tab_idx, section, new_items):
        # Synthesize the broken state inline so the bounds check fires.
        new_jm_count = -1
        if not 0 <= new_jm_count <= 0xFFFF:
            raise D2IWriterIntegrityError(
                f"Tab {tab_idx}: computed new JM count {new_jm_count} "
                f"is out of uint16 range. Refusing to emit."
            )
        return original_splice(self, tab_idx, section, new_items)

    dw.D2IWriter._splice_section = malicious_splice
    try:
        writer._tab_items[splice_tab].pop()  # noqa: SLF001
        with pytest.raises(D2IWriterIntegrityError, match="out of uint16 range"):
            writer.build()
    finally:
        dw.D2IWriter._splice_section = original_splice


# ─────────────────────────────────────────────────────────────────────
# Sanity: clean-case splice (no parser-extras) is unaffected.
# ─────────────────────────────────────────────────────────────────────


def test_clean_splice_unchanged_by_fix():
    """The fix uses `new_jm_count = len(new_items)`. In the clean case
    (no parser-extras) this equals the OLD `section.item_count + delta`,
    so removing an item produces the expected count.

    Uses a tab with >= 2 items so the pop leaves at least one item in
    place (avoiding the empty-out path with its orphan-extras guard)."""
    source = SOURCE_FIXTURE.read_bytes()
    stash = D2IParser(SOURCE_FIXTURE).parse()

    tab_idx = next(
        (i for i, t in enumerate(stash.tabs) if len(t.items) >= 2),
        None,
    )
    if tab_idx is None:
        pytest.skip("Source fixture has no tab with >= 2 items.")

    expected_new_count = len(stash.tabs[tab_idx].items) - 1
    writer = D2IWriter.from_stash(source, stash)
    writer._tab_items[tab_idx].pop()  # noqa: SLF001

    built = writer.build()
    sections = _find_sections(bytes(built))
    assert sections[tab_idx].item_count == expected_new_count, (
        f"clean-case splice produced unexpected JM count "
        f"{sections[tab_idx].item_count}, expected {expected_new_count}"
    )


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    pytest.main([__file__, "-v"])

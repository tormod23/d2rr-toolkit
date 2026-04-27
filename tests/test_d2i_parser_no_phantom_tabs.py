"""Regression - parser must never produce a phantom tab from trailing metadata.

Spec (``docs/spec/d2s_format_spec.md`` §4) says a .d2i file has exactly
**7 sections**: 6 JM-delimited tab sections followed by 1 trailing
metadata block (148 bytes of game-internal timestamps / session IDs,
updated by the game on every save).

The trailing block has **no signature and no structural JM marker**,
but its unstructured bytes can coincidentally contain the byte pair
``0x4A 0x4D`` ("JM"). The previous parser implementation forward-scanned
for those bytes and produced a phantom 7th tab whose "items" were
whatever random bytes followed the accidental JM. This:

  * surfaced as ``Ignoring unknown d2i tab index 6 (N items)`` in
    consumer logs,
  * let CLI ``archive extract --tab 6 ...`` pull garbage into the
    archive DB (through the bounds check, which only asserted
    ``tab_index < len(stash.tabs)``),
  * was silently discarded by the writer on the way back to disk
    (the writer enumerates by 0xAA55AA55 signature, so file bytes
    stayed safe) - but the parser / writer disagreement was a latent
    trap for every other consumer.

This suite pins the fix: the parser must enumerate sections via the
same signature-driven walk the writer uses. A file whose trailing
metadata happens to contain ``0x4A 0x4D`` must yield exactly 6 tabs,
and a parse -> write round-trip must reproduce the original bytes
including the trailing block verbatim.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from d2rr_toolkit.parsers.d2i_parser import D2IParser
from d2rr_toolkit.writers.d2i_writer import D2IWriter, _find_sections

_D2I_SIGNATURE = 0xAA55AA55
_SECTION_HEADER_SIZE = 64
_EMPTY_SECTION_SIZE = 68  # header + "JM" + uint16 count
_TRAILING_SIZE = 148  # per the spec


def _build_d2i_with_trailing_jm() -> bytes:
    """Build a 6-tab .d2i whose trailing metadata contains a literal 'JM'.

    The trailing block is 148 bytes of deliberately adversarial content:
      * Leading bytes imitate the timestamp / session-ID pattern the
        real game writes.
      * An embedded ``0x4A 0x4D`` (the ASCII "JM") at internal offset
        50 - exactly the shape that would have tripped the old
        forward-scan parser.
      * A ``uint16`` = 2 immediately after, so a broken parser would
        report "tab 6 (2 items)".
      * The rest is varied non-zero bytes so a naive item-parser would
        have something to feed on.
    """
    out = bytearray()

    # Six canonical empty tab sections.
    for _ in range(6):
        section = bytearray(_EMPTY_SECTION_SIZE)
        struct.pack_into("<I", section, 0x00, _D2I_SIGNATURE)
        struct.pack_into("<I", section, 0x10, _EMPTY_SECTION_SIZE)
        section[_SECTION_HEADER_SIZE : _SECTION_HEADER_SIZE + 2] = b"JM"
        # uint16 count at offset 66 stays zero.
        out.extend(section)

    # Trailing metadata - 148 bytes, no signature, deliberately hostile.
    trailing = bytearray(_TRAILING_SIZE)
    trailing[:10] = bytes([0x00, 0x01, 0x02, 0x03, 0x04, 0xFE, 0xFD, 0xFC, 0xFB, 0xFA])
    # Insert "JM" + plausible uint16 count at offset 50.
    trailing[50:52] = b"JM"
    struct.pack_into("<H", trailing, 52, 2)
    # Fill the rest with varied non-zero bytes (pseudo-random but deterministic).
    for i in range(54, _TRAILING_SIZE):
        trailing[i] = (i * 37) & 0xFF

    out.extend(trailing)
    return bytes(out)


@pytest.fixture
def synthetic_stash(tmp_path: Path) -> tuple[Path, bytes]:
    """Write the synthetic fixture and return (path, raw_bytes)."""
    data = _build_d2i_with_trailing_jm()
    path = tmp_path / "synthetic_stash.d2i"
    path.write_bytes(data)
    return path, data


# ─────────────────────────────────────────────────────────────────────
# §1  Baseline invariants for the synthetic fixture itself
# ─────────────────────────────────────────────────────────────────────


def test_fixture_has_6_signature_sections() -> None:
    """Sanity: the synthetic file really has 6 real sections + trailer."""
    data = _build_d2i_with_trailing_jm()
    sections = _find_sections(data)
    assert len(sections) == 6, (
        f"Expected 6 real sections (signature-delimited); "
        f"writer's _find_sections returned {len(sections)}."
    )


def test_fixture_trailing_contains_literal_JM() -> None:
    """Sanity: the trailing region we built really contains the 'JM' trap."""
    data = _build_d2i_with_trailing_jm()
    trailing_start = 6 * _EMPTY_SECTION_SIZE
    trailing = data[trailing_start:]
    assert len(trailing) == _TRAILING_SIZE
    assert b"JM" in trailing, (
        "Fixture must contain a 'JM' byte pair in the trailing metadata "
        "or it isn't exercising the phantom-tab regression path."
    )


# ─────────────────────────────────────────────────────────────────────
# §2  Parser must produce exactly 6 tabs - no phantom tab 6
# ─────────────────────────────────────────────────────────────────────


def test_parser_returns_exactly_six_tabs(synthetic_stash: tuple[Path, bytes]) -> None:
    """Core guarantee: trailing 'JM' never becomes a phantom tab."""
    path, _ = synthetic_stash
    stash = D2IParser(path).parse()
    assert len(stash.tabs) == 6, (
        f"Parser produced {len(stash.tabs)} tabs; expected exactly 6 "
        f"(6 JM-delimited sections, trailing metadata must not be parsed). "
        f"Tab indices: {[t.tab_index for t in stash.tabs]}"
    )


def test_parser_tab_indices_are_zero_through_five(
    synthetic_stash: tuple[Path, bytes],
) -> None:
    """Every tab_index must fall in the canonical 0-5 range."""
    path, _ = synthetic_stash
    stash = D2IParser(path).parse()
    assert [t.tab_index for t in stash.tabs] == [0, 1, 2, 3, 4, 5]


def test_parser_all_tabs_empty(synthetic_stash: tuple[Path, bytes]) -> None:
    """The synthetic fixture has 0 real items - parser must agree."""
    path, _ = synthetic_stash
    stash = D2IParser(path).parse()
    for tab in stash.tabs:
        assert tab.jm_item_count == 0, (
            f"Tab {tab.tab_index} reported jm_item_count={tab.jm_item_count}; "
            f"synthetic fixture has zero items in every tab."
        )
        assert tab.items == [], (
            f"Tab {tab.tab_index} returned {len(tab.items)} items from an "
            f"empty fixture - likely consuming bytes from the trailing "
            f"metadata section."
        )


def test_parser_total_items_is_zero(synthetic_stash: tuple[Path, bytes]) -> None:
    """``stash.total_items`` must reflect only real tab items."""
    path, _ = synthetic_stash
    stash = D2IParser(path).parse()
    assert stash.total_items == 0


# ─────────────────────────────────────────────────────────────────────
# §3  Round-trip safety: trailing metadata preserved verbatim
# ─────────────────────────────────────────────────────────────────────


def test_roundtrip_preserves_every_byte(
    synthetic_stash: tuple[Path, bytes],
) -> None:
    """Parse -> write must reproduce the source file exactly.

    The trailing 148 bytes - including the embedded 'JM' + count=2 -
    must survive a no-op round-trip byte-for-byte. This is the
    invariant that makes the writer's section-6 handling safe even
    when the source file contains hostile patterns.
    """
    path, source_bytes = synthetic_stash
    stash = D2IParser(path).parse()
    writer = D2IWriter.from_stash(source_bytes, stash)
    built = bytes(writer.build())
    assert built == source_bytes, (
        f"Round-trip produced {len(built)} bytes but source was "
        f"{len(source_bytes)} bytes. Bytes-differ count: "
        f"{sum(1 for a, b in zip(built, source_bytes) if a != b)}"
    )


def test_roundtrip_preserves_trailing_metadata(
    synthetic_stash: tuple[Path, bytes],
) -> None:
    """Specifically pin: the 148-byte trailer comes through untouched.

    Guards against a future regression where the writer might decide to
    "normalise" the trailing block on rebuild - the game overwrites it
    anyway, but mutating it mid-flight is a latent file-corruption
    vector if D2R ever validates the trailing data cross-save.
    """
    path, source_bytes = synthetic_stash
    stash = D2IParser(path).parse()
    writer = D2IWriter.from_stash(source_bytes, stash)
    built = bytes(writer.build())

    trailing_start = 6 * _EMPTY_SECTION_SIZE
    assert built[trailing_start:] == source_bytes[trailing_start:], (
        "Trailing metadata diverged on round-trip. Source (hex): "
        f"{source_bytes[trailing_start:trailing_start + 56].hex()} ... "
        f"Built (hex): {built[trailing_start:trailing_start + 56].hex()} ..."
    )


def test_roundtrip_trailing_size_is_148_bytes(
    synthetic_stash: tuple[Path, bytes],
) -> None:
    """The writer must not grow or shrink the trailing block."""
    path, source_bytes = synthetic_stash
    stash = D2IParser(path).parse()
    writer = D2IWriter.from_stash(source_bytes, stash)
    built = bytes(writer.build())

    built_sections = _find_sections(built)
    assert built_sections, "Expected at least one section in the built output."
    last_end = built_sections[-1].header_offset + built_sections[-1].section_size
    built_trailing = built[last_end:]
    assert len(built_trailing) == _TRAILING_SIZE, (
        f"Trailing block size drifted: expected {_TRAILING_SIZE}, got " f"{len(built_trailing)}."
    )

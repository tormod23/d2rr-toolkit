"""Section 6 (Reimagined audit-block) analyzer.

The 7th page of every Reimagined v105 SharedStash file is a structurally
valid page (same 64-byte page header as the regular tabs) that does NOT
carry the standard ``JM`` marker at offset 0x40 - instead it carries the
4-byte sequence ``0xC0 0xED 0xEA 0xC0`` (``D2I_AUDIT_BLOCK_MARKER``).

This module decodes the page into structured records WITHOUT modifying
the file.

## Key invariant (TC74-verified)

**Section 6 is byte-identical under item add / remove / move
operations.** A controlled in-game fixture sequence (TC74 A-E) covers
empty stash, +1 item, +2 items, -1 item, item moved between tabs:
across all five snapshots the audit-block body is byte-for-byte
identical.

This is the foundation for the toolkit's verbatim-preservation
strategy in :class:`d2rr_toolkit.writers.d2i_writer.D2IWriter`. Item
edits cannot drift the audit-block as long as the writer copies the
page bytes verbatim from source to output.

The records inside the audit block evidently track something else
(character progression, vendor interactions, multiplayer events,
session state) - not stash item history. Decoding their semantics is
not currently needed for safe writes.

Empirical findings on the body layout (derived from cross-fixture
analysis - see ``tests/test_section6_decoder.py`` and the dataset
under ``tests/cases/**/*.d2i``):

  * **Body layout**: ``sub_header(20) + records(N x 10) + footer(60)``.
  * **Empty stash**: N = 0, body = 80 bytes total. Truly-empty stashes
    (no items AND no records) share an identical 80-byte signature
    across fixtures; populated stashes carry varying footer / sub-
    header tail data even when records = 0.
  * **Record stride**: 10 bytes.
  * **Record layout**:
      bytes 0..3   field_a    u32 LE
      bytes 4..5   marker     u16 LE = 0x01C3 (constant per record)
      bytes 6..9   field_b    u32 LE
  * **Footer**: 60 bytes total, structured as 6 entries of 10 bytes
    (one per stash tab 0..5). Per-tab content varies with item
    presence in that tab.
  * The semantic interpretation of field_a / field_b and the per-tab
    footer entries is still being pinned down; the analyzer surfaces
    enough metadata to test candidate hypotheses against any d2i.
"""

import struct
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from d2rr_toolkit.constants import (
    D2I_AUDIT_BLOCK_MARKER,
    D2I_AUDIT_RECORD_MARKER,
    D2I_AUDIT_RECORD_SIZE,
    D2I_PAGE_HEADER_SIZE,
    D2I_PAGE_OFFSET_HEADER_FLAG,
    D2I_PAGE_OFFSET_JM_MARKER,
    D2I_PAGE_OFFSET_PAGE_LENGTH,
    D2I_PAGE_OFFSET_VERSION,
)

if TYPE_CHECKING:
    pass


D2I_SIGNATURE: int = 0xAA55AA55


@dataclass(slots=True)
class Section6Record:
    """One 10-byte record from the Reimagined audit block.

    Fields ``field_a`` and ``field_b`` are exposed as raw u32 LE values;
    callers can re-interpret them as item-IDs / hashes / counters once
    the semantic mapping is known.
    """

    index: int  # 0-based position in the record list
    file_offset: int  # absolute byte offset in the d2i file
    field_a: int  # u32 LE
    marker: int  # u16 LE, expected to be D2I_AUDIT_RECORD_MARKER (0x01C3)
    field_b: int  # u32 LE

    @property
    def is_marker_valid(self) -> bool:
        """Return ``True`` iff ``marker == 0x01C3`` (every game-written
        record observed so far has this marker)."""
        return self.marker == D2I_AUDIT_RECORD_MARKER


@dataclass(slots=True)
class Section6Page:
    """Decoded representation of the Reimagined audit-block page.

    Three-region layout (verified across the entire fixture corpus):

      ``sub_header`` (20 bytes, always)
      ``records``   (N * 10 bytes, each carrying the 0x01C3 marker)
      ``footer``    (60 bytes, always - 6 entries of 10 bytes,
                    one per stash tab)

    Empty stashes have N = 0, so the body is exactly 80 bytes.
    Non-empty stashes have body = 20 + N*10 + 60 bytes.

    Use :func:`extract_section6` to obtain the raw bytes, then
    :func:`parse_section6` to decode into this dataclass.
    """

    file_offset: int
    """Absolute byte offset of the page header (start of the
    ``0x55AA55AA`` magic) in the source d2i file."""

    page_size: int
    """Total page size in bytes (read from the page-header
    ``page_length`` field at +0x10)."""

    header_flag: int
    """``header_format_flag`` value at page-header +0x04. Always
    observed as ``D2I_HEADER_FLAG_REIMAGINED`` (= 2) on Reimagined
    v105 audit-block pages."""

    version: int
    """File-format version at page-header +0x08. Always observed as
    105 (=0x69) on Reimagined v105."""

    audit_marker: bytes
    """The 4 bytes at +0x40. Should equal :data:`D2I_AUDIT_BLOCK_MARKER`
    (``0xC0 0xED 0xEA 0xC0``)."""

    body: bytes
    """All bytes from +0x44 (after the 4-byte audit marker) through the
    end of the page. Always equal to ``sub_header + records + footer``."""

    sub_header: bytes
    """First 20 bytes of ``body``. Decoded by :func:`decode_sub_header`
    into named u16 / u32 fields whose semantics are still under
    investigation."""

    records: list[Section6Record] = field(default_factory=list)
    """Decoded 10-byte records carrying the ``0x01C3`` marker, in file
    order. Sit between ``sub_header`` and ``footer``."""

    footer: bytes = b""
    """Last 60 bytes of ``body`` - 6 entries of 10 bytes each, one per
    stash tab (tabs 0..5). The per-tab entry format has not been fully
    decoded yet; on empty stashes it appears to be a zero-tab template
    with five ``ff ff 00 00`` slots in the upper portion."""

    @property
    def record_count(self) -> int:
        """Number of decoded 10-byte records in this Section 6 page."""
        return len(self.records)

    @property
    def all_markers_valid(self) -> bool:
        """``True`` iff every record's marker equals ``0x01C3``.

        With the corrected body layout (records sit BEFORE the 60-byte
        footer), this should now always be True for game-written files.
        Returning False would indicate corruption or a missed format
        feature."""
        return all(r.is_marker_valid for r in self.records)


def extract_section6(d2i_bytes: bytes) -> Section6Page | None:
    """Locate the Reimagined audit-block page in a .d2i byte buffer.

    Walks the file as a sequence of pages (each starting with the
    ``0x55AA55AA`` magic). The audit page is the FIRST page whose
    +0x40 marker is :data:`D2I_AUDIT_BLOCK_MARKER` instead of ``"JM"``.

    Returns the decoded :class:`Section6Page` or ``None`` when the
    file does not contain an audit block (vanilla D2R, or malformed
    Reimagined files).
    """
    pos = 0
    while pos + D2I_PAGE_HEADER_SIZE <= len(d2i_bytes):
        sig = struct.unpack_from("<I", d2i_bytes, pos)[0]
        if sig != D2I_SIGNATURE:
            return None  # ran off the end of the page sequence
        page_size = struct.unpack_from(
            "<I", d2i_bytes, pos + D2I_PAGE_OFFSET_PAGE_LENGTH
        )[0]
        if page_size <= 0 or pos + page_size > len(d2i_bytes):
            return None  # malformed page
        marker = d2i_bytes[
            pos + D2I_PAGE_OFFSET_JM_MARKER : pos + D2I_PAGE_OFFSET_JM_MARKER + 4
        ]
        if marker.startswith(D2I_AUDIT_BLOCK_MARKER):
            return parse_section6(d2i_bytes, pos)
        pos += page_size
    return None


def parse_section6(d2i_bytes: bytes, page_offset: int) -> Section6Page:
    """Decode the audit-block page at ``page_offset`` of ``d2i_bytes``.

    Caller must verify ``page_offset`` points at an audit-block page;
    this function double-checks the page-header magic ``0x55AA55AA`` and
    the audit marker at +0x40 and raises ``ValueError`` on either
    mismatch.
    """
    if page_offset + D2I_PAGE_HEADER_SIZE > len(d2i_bytes):
        raise ValueError(
            f"page_offset 0x{page_offset:X} + header size exceeds "
            f"buffer length {len(d2i_bytes)}"
        )

    sig = struct.unpack_from("<I", d2i_bytes, page_offset)[0]
    if sig != D2I_SIGNATURE:
        raise ValueError(
            f"page_offset 0x{page_offset:X}: expected magic 0x{D2I_SIGNATURE:08X}, "
            f"found 0x{sig:08X}"
        )

    header_flag = struct.unpack_from(
        "<I", d2i_bytes, page_offset + D2I_PAGE_OFFSET_HEADER_FLAG
    )[0]
    version = struct.unpack_from(
        "<I", d2i_bytes, page_offset + D2I_PAGE_OFFSET_VERSION
    )[0]
    page_size = struct.unpack_from(
        "<I", d2i_bytes, page_offset + D2I_PAGE_OFFSET_PAGE_LENGTH
    )[0]

    audit_marker = d2i_bytes[
        page_offset + D2I_PAGE_OFFSET_JM_MARKER :
        page_offset + D2I_PAGE_OFFSET_JM_MARKER + 4
    ]
    if not audit_marker.startswith(D2I_AUDIT_BLOCK_MARKER):
        raise ValueError(
            f"page_offset 0x{page_offset:X}: not an audit page "
            f"(marker at +0x40 = {audit_marker.hex()}, expected "
            f"{D2I_AUDIT_BLOCK_MARKER.hex()})"
        )

    body_start = page_offset + D2I_PAGE_OFFSET_JM_MARKER + 4
    body_end = page_offset + page_size
    body = d2i_bytes[body_start:body_end]

    # Layout (verified across the entire fixture corpus):
    #   - 20-byte sub-header
    #   - N * 10-byte records (each carrying the 0x01C3 marker)
    #   - 60-byte trailing footer (6 per-tab entries of 10 bytes each)
    #
    # Empty stashes have N = 0, so the body is exactly 80 bytes
    # (20 sub-header + 0 records + 60 footer).
    SUB_HEADER_SIZE = 20
    FOOTER_SIZE = 60  # 6 stash tabs * 10 bytes each

    if len(body) < SUB_HEADER_SIZE + FOOTER_SIZE:
        # Truncated audit page - return what we can without
        # synthesizing structure that isn't there.
        return Section6Page(
            file_offset=page_offset,
            page_size=page_size,
            header_flag=header_flag,
            version=version,
            audit_marker=audit_marker,
            body=body,
            sub_header=body[:min(len(body), SUB_HEADER_SIZE)],
            records=[],
            footer=body[max(SUB_HEADER_SIZE, len(body) - FOOTER_SIZE):]
                   if len(body) > SUB_HEADER_SIZE else b"",
        )

    sub_header = body[:SUB_HEADER_SIZE]
    footer = body[len(body) - FOOTER_SIZE:]
    record_region = body[SUB_HEADER_SIZE : len(body) - FOOTER_SIZE]

    n_records = len(record_region) // D2I_AUDIT_RECORD_SIZE
    records: list[Section6Record] = []
    for i in range(n_records):
        rec_start = i * D2I_AUDIT_RECORD_SIZE
        record_bytes = record_region[rec_start : rec_start + D2I_AUDIT_RECORD_SIZE]
        field_a = struct.unpack_from("<I", record_bytes, 0)[0]
        marker = struct.unpack_from("<H", record_bytes, 4)[0]
        field_b = struct.unpack_from("<I", record_bytes, 6)[0]
        records.append(
            Section6Record(
                index=i,
                file_offset=body_start + SUB_HEADER_SIZE + rec_start,
                field_a=field_a,
                marker=marker,
                field_b=field_b,
            )
        )

    return Section6Page(
        file_offset=page_offset,
        page_size=page_size,
        header_flag=header_flag,
        version=version,
        audit_marker=audit_marker,
        body=body,
        sub_header=sub_header,
        records=records,
        footer=footer,
    )


def decode_sub_header(sub_header: bytes) -> dict[str, int]:
    """Decode the 20-byte non-empty sub-header into named u16 / u32 fields.

    The semantic meaning of these fields is still under investigation;
    this helper just gives them stable names so cross-fixture diffs are
    easier to compare. The naming is conservative (``u16_at_offset_N``)
    because we do not yet know what each slot encodes.
    """
    if len(sub_header) < 20:
        raise ValueError(f"sub_header too short: {len(sub_header)} bytes (need 20)")
    return {
        "u16_at_0": struct.unpack_from("<H", sub_header, 0)[0],
        "u16_at_2": struct.unpack_from("<H", sub_header, 2)[0],
        "u16_at_4": struct.unpack_from("<H", sub_header, 4)[0],
        "u16_at_6": struct.unpack_from("<H", sub_header, 6)[0],
        "u32_at_8": struct.unpack_from("<I", sub_header, 8)[0],
        "u32_at_12": struct.unpack_from("<I", sub_header, 12)[0],
        "u32_at_16": struct.unpack_from("<I", sub_header, 16)[0],
    }

"""D2I Shared Stash Writer - serialize stash modifications back to binary.

Uses **byte-splice preservation**: the ORIGINAL source file structure is kept
intact. Only tabs whose items actually changed are surgically modified. Tabs
where no items were added or removed are copied verbatim from the source -
including any items the parser could not decode (socket children, items with
unknown encodings, etc.).

This is critical because the D2I parser returns only the items it can fully
parse (typically the root items). Socket children and items with complex
encodings are embedded in the raw section bytes but NOT represented in the
parsed item list. A naïve "rebuild from parsed items" would drop those bytes
and corrupt the file.

D2I Binary Structure (discovered from TC04/TC05/TC06 analysis):
    The file consists of consecutive SECTIONS, each with:
    - 64-byte header (signature 0xAA55AA55, version, section_size at offset 0x10)
    - 'JM' marker (2 bytes)
    - Item count (uint16 LE)
    - Item data (variable length)

    Section size at header offset 0x10 = total section bytes (header + JM + count + items).
"""

import logging
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from d2rr_toolkit.models.character import ParsedItem

if TYPE_CHECKING:
    from d2rr_toolkit.parsers.d2i_parser import ParsedSharedStash
from d2rr_toolkit.writers.item_utils import (  # noqa: F401 - patch_item_position is re-exported for backwards compat
    clear_d2s_only_flags,
    ensure_unique_uids,
    patch_item_position,
)
import hashlib
from d2rr_toolkit.analysis.section6 import extract_section6
from d2rr_toolkit.backup import create_backup

logger = logging.getLogger(__name__)

D2I_SIGNATURE = 0xAA55AA55
D2I_HEADER_SIZE = 64
SECTION_MARKER = b"JM"

# Canonical empty-section size = 64-byte header + 'JM' marker (2B) + count uint16 (2B).
# Any section with jm_count == 0 MUST be exactly this size or D2R refuses to load
# saves while a malformed SharedStash is present in the save directory.
D2I_EMPTY_SECTION_SIZE = D2I_HEADER_SIZE + 4  # = 68


class D2IWriterIntegrityError(RuntimeError):
    """Raised when the writer's post-build self-check detects a malformed section.

    Indicates a bug in the writer or the input data. The writer refuses to emit
    the output rather than corrupt the SharedStash file - losing a single
    archive operation is recoverable; a non-loadable SharedStash blocks every
    character in the save directory.
    """


class D2IOrphanExtrasError(RuntimeError):
    """Raised when an empty-out operation would orphan unparsed JM extras.

    The parser sometimes preserves items in the section's raw-tail region
    that it could not fully decode. If the caller empties the section (removes
    every parsed root item) while such extras still exist, writing count=0
    would silently destroy them AND leave stale JM blobs in the tail - a
    guaranteed file corruption. The writer refuses the operation.
    """


# [BV] The Shared Stash Section 5 (Gems/Materials/Runes sub-tabs)
# accepts exactly ONE stack per item_code. If the game sees duplicates on load,
# it silently keeps the first and drops the rest on next save. The writer
# refuses to produce files that would trigger this behaviour.
SECTION5_TAB_INDEX = 5


class DuplicateSection5ItemError(ValueError):
    """Raised when a Section 5 tab contains multiple items with the same item_code."""


@dataclass(slots=True)
class D2ISectionInfo:
    """Metadata about one section in a D2I file."""

    header_offset: int
    section_size: int
    jm_offset: int
    item_count: int
    items_start: int
    items_end: int


def _find_sections(data: bytes) -> list[D2ISectionInfo]:
    """Parse the D2I file to find all section boundaries."""
    sections: list[D2ISectionInfo] = []
    pos = 0

    while pos + D2I_HEADER_SIZE + 4 <= len(data):
        sig = int.from_bytes(data[pos : pos + 4], "little")
        if sig != D2I_SIGNATURE:
            break

        section_size = int.from_bytes(data[pos + 16 : pos + 20], "little")
        jm_offset = pos + D2I_HEADER_SIZE

        if jm_offset + 4 > len(data):
            break
        if data[jm_offset : jm_offset + 2] != SECTION_MARKER:
            pos += section_size if section_size > 0 else D2I_HEADER_SIZE
            continue

        item_count = int.from_bytes(data[jm_offset + 2 : jm_offset + 4], "little")
        items_start = jm_offset + 4
        items_end = pos + section_size

        sections.append(
            D2ISectionInfo(
                header_offset=pos,
                section_size=section_size,
                jm_offset=jm_offset,
                item_count=item_count,
                items_start=items_start,
                items_end=items_end,
            )
        )

        pos += section_size if section_size > 0 else D2I_HEADER_SIZE + 4

    return sections


class D2IWriter:
    """Serialize a modified shared stash to a .d2i binary file.

    Preserves the original file structure. Only the specific tab(s) where
    items were added, removed, or modified get their section bytes spliced.
    All other tabs - including any items the parser could NOT decode - are
    copied verbatim from the source file.

    Byte-splicing preserves socket children and incompletely-parsed items.
    JM count excludes socket children (location_id=6). D2S-only flags
    (bit 13) are cleared on every item written to D2I. [BV TC67]
    """

    def __init__(
        self,
        source_data: bytes,
        tab_items: list[list[ParsedItem]],
        *,
        _original_items: list[list[ParsedItem]] | None = None,
    ) -> None:
        """Initialize with the original file data and modified tab item lists.

        Args:
            source_data:     Original .d2i file bytes.
            tab_items:       Root-item lists per tab (socket children live
                             inside each ParsedItem.socket_children).
            _original_items: Snapshot of the parsed item lists BEFORE any
                             modifications. Used for change detection.
                             Populated automatically by :meth:`from_stash`.
        """
        self._source = source_data
        self._tab_items = tab_items
        self._original_items = _original_items
        # Set of tab indices whose section was rewritten by this writer.
        # The integrity self-check only enforces canonical layout on THESE
        # sections - verbatim-copied tabs may carry pre-existing source
        # corruption that the writer cannot fix without touching them.
        self._touched_sections: set[int] = set()

    def _mark_section_touched(self, tab_idx: int) -> None:
        """Record that a section was rewritten (not verbatim-copied)."""
        self._touched_sections.add(tab_idx)

    def build(self) -> bytearray:
        """Assemble the modified .d2i binary.

        Strategy: for each section, check if the parsed items changed
        compared to the original parse. If unchanged -> copy section verbatim.
        If changed -> byte-splice the original section data (add/remove items
        while preserving all unparsed bytes).

        Raises:
            DuplicateSection5ItemError: if the Section 5 tab contains two or
                more items sharing an item_code.
        """
        self._validate_section5_no_duplicates()

        # NOTE: unique_item_id deduplication was previously enforced here,
        # but empirical evidence shows the game accepts D2I files with
        # duplicate UIDs (verified: monday_test D2I has two jewels sharing
        # UID 0x043197DC0 and loads fine in-game). Rerolling UIDs on every
        # write mutates the source_data unnecessarily. UIDs are preserved.

        sections = _find_sections(self._source)
        result = bytearray()

        for i, section in enumerate(sections):
            if i < len(self._tab_items):
                items = self._tab_items[i]
                if self._tab_unchanged(i, section, items):
                    # Tab NOT modified -> copy original section bytes verbatim.
                    # This preserves ALL items including those the parser
                    # could not decode (socket children, complex encodings).
                    result.extend(
                        self._source[
                            section.header_offset : section.header_offset + section.section_size
                        ]
                    )
                else:
                    # Tab WAS modified -> byte-splice the changes into the
                    # original section data.
                    result.extend(self._splice_section(i, section, items))
                    self._mark_section_touched(i)
            else:
                result.extend(
                    self._source[
                        section.header_offset : section.header_offset + section.section_size
                    ]
                )

        # Handle any trailing data after the last known section
        if sections:
            last_end = sections[-1].header_offset + sections[-1].section_size
            if last_end < len(self._source):
                result.extend(self._source[last_end:])

        # ── Post-build integrity self-check ──────────────────────────────
        # Re-parse the just-built bytes and assert every section is
        # well-formed. Raises D2IWriterIntegrityError if ANY section is
        # malformed - the file is NOT returned in that case, so a buggy
        # splice cannot clobber a loadable save file on disk.
        self._self_check(bytes(result))

        logger.info("D2I assembled: %d bytes (original: %d)", len(result), len(self._source))
        return result

    # ──────────────────────────────────────────────────────────────────────
    # Post-build self-check
    # ──────────────────────────────────────────────────────────────────────

    def _self_check(self, built: bytes) -> None:
        """Verify the built file has a structurally valid section layout.

        Raises D2IWriterIntegrityError on ANY anomaly:
          - Section signature mismatch
          - JM marker missing
          - Any ``jm_count == 0`` section whose ``section_size != 68``
            (the exact bug that bricked ModernSharedStashSoftCoreV2.d2i)
          - Section sizes don't sum to ``len(built) - trailer_bytes``
          - Number of sections differs from the source file
          - Reimagined audit block (Section 6) drifted from the source
            (the writer is supposed to copy it verbatim as part of the
            trailer; any mismatch indicates a writer bug)

        The check is cheap: a single re-parse plus constant-time asserts.
        """
        try:
            built_sections = _find_sections(built)
        except Exception as e:  # pragma: no cover - parser is tolerant
            raise D2IWriterIntegrityError(f"Built file failed to re-parse: {e}") from e

        src_sections = _find_sections(self._source)
        if len(built_sections) != len(src_sections):
            raise D2IWriterIntegrityError(
                f"Section count changed: source had {len(src_sections)}, "
                f"built has {len(built_sections)}"
            )

        for idx, sec in enumerate(built_sections):
            if sec.item_count == 0 and sec.section_size != D2I_EMPTY_SECTION_SIZE:
                # Dual policy on `jm_count=0, section_size != 68`:
                #
                #   - PRODUCED by us (touched): the splice path is
                #     supposed to emit a canonical 68-byte empty section
                #     when a tab becomes empty. Anything else means a
                #     splice bug and we refuse to emit, so no corrupted
                #     bytes ever hit disk.
                #
                #   - VERBATIM-copied from source (untouched): the
                #     legacy state predates this check. Refusing to emit
                #     would strand the user on a partially-broken file
                #     with no toolkit operations possible. Warn instead.
                #
                # Pinned by test_d2i_writer_legacy_malformed_sections.py.
                if idx in self._touched_sections:
                    raise D2IWriterIntegrityError(
                        f"Section {idx} has jm_count=0 but section_size="
                        f"{sec.section_size} (canonical empty = "
                        f"{D2I_EMPTY_SECTION_SIZE}). Writing this file would "
                        f"corrupt the SharedStash and block character loading. "
                        f"Refusing to emit."
                    )
                else:
                    logger.warning(
                        "Source file has pre-existing malformed empty section "
                        "%d (size=%d, canonical=%d) - passed through verbatim. "
                        "Character loading may be affected. Consider restoring "
                        "from a clean backup.",
                        idx,
                        sec.section_size,
                        D2I_EMPTY_SECTION_SIZE,
                    )
            # Section must fit within the emitted bytes
            if sec.header_offset + sec.section_size > len(built):
                raise D2IWriterIntegrityError(
                    f"Section {idx} overruns file: header_offset="
                    f"{sec.header_offset}, section_size={sec.section_size}, "
                    f"file length={len(built)}"
                )

        # Trailer-size conservation: the number of bytes after the last
        # section must match the source file. Any drift indicates a
        # splice arithmetic bug.
        src_trailer = (
            len(self._source) - (src_sections[-1].header_offset + src_sections[-1].section_size)
            if src_sections
            else len(self._source)
        )
        built_trailer = (
            len(built) - (built_sections[-1].header_offset + built_sections[-1].section_size)
            if built_sections
            else len(built)
        )
        if src_trailer != built_trailer:
            raise D2IWriterIntegrityError(
                f"Trailer size changed: source={src_trailer} bytes, "
                f"built={built_trailer} bytes. Splice arithmetic is wrong."
            )

        # ── Section 6 (Reimagined audit block) drift check ──────────────
        # The audit block is a 7th page (marker 0xC0EDEAC0 instead of
        # 'JM') the v105 game writes after the six tab pages. The writer
        # never edits it - the trailer-copy path picks it up verbatim
        # along with anything else past the last JM section. If the
        # built file's audit-block bytes differ from the source's, the
        # writer corrupted the page somewhere along the way; refuse to
        # emit so the SharedStash isn't silently broken.
        #
        # Pinned by tests/test_section6_invariance.py (TC74 A-E): item
        # add / remove / move never touches Section 6 in-game, so the
        # toolkit must not touch it either.
        self._check_section6_preserved(built)

    def _check_section6_preserved(self, built: bytes) -> None:
        """Verify the Reimagined audit block is byte-identical in source and built.

        No-op when the source has no audit block (vanilla D2R or other
        non-Reimagined files - the toolkit's writer can still emit those,
        we just have nothing to compare).
        """
        # Local import: section6 lives in `analysis/`, which would create
        # an import cycle if pulled in at module top.

        src_s6 = extract_section6(self._source)
        if src_s6 is None:
            return  # nothing to check (vanilla D2R or malformed Reimagined)

        built_s6 = extract_section6(built)
        if built_s6 is None:
            raise D2IWriterIntegrityError(
                "Source has a Reimagined audit block but the built output "
                "does not. The writer dropped Section 6 - refusing to emit "
                "a file that would brick the SharedStash."
            )

        src_page = self._source[src_s6.file_offset : src_s6.file_offset + src_s6.page_size]
        built_page = built[built_s6.file_offset : built_s6.file_offset + built_s6.page_size]

        if src_page != built_page:

            src_hash = hashlib.sha256(src_page).hexdigest()[:16]
            built_hash = hashlib.sha256(built_page).hexdigest()[:16]
            # Pinpoint the first byte that diverges so a future
            # investigation has a starting point.
            first_diff = next(
                (
                    i
                    for i in range(min(len(src_page), len(built_page)))
                    if src_page[i] != built_page[i]
                ),
                -1,
            )
            raise D2IWriterIntegrityError(
                f"Section 6 (Reimagined audit block) drifted between "
                f"source and built output: src len={len(src_page)} "
                f"hash={src_hash}, built len={len(built_page)} "
                f"hash={built_hash}, first diff at offset "
                f"{first_diff if first_diff >= 0 else 'len-only'}. "
                f"The writer must preserve the audit page verbatim "
                f"(see TC74). Refusing to emit."
            )

    def _validate_section5_no_duplicates(self) -> None:
        """Fail fast if Section 5 contains multiple items with the same item_code."""
        if len(self._tab_items) <= SECTION5_TAB_INDEX:
            return
        section5 = self._tab_items[SECTION5_TAB_INDEX]
        seen: dict[str, int] = {}
        duplicates: list[str] = []
        for item in section5:
            code = item.item_code
            seen[code] = seen.get(code, 0) + 1
            if seen[code] == 2:
                duplicates.append(code)
        if duplicates:
            raise DuplicateSection5ItemError(
                f"Section 5 contains duplicate item_codes: {sorted(set(duplicates))}. "
                f"The game would silently drop duplicate stacks on next save. "
                f"Merge stacks (cap at 99) before writing."
            )

    def write(self, output_path: Path) -> None:
        """Assemble and write to a file using atomic write.

        **Automatically creates a timestamped backup** of the existing file
        at ``~/.d2rr_toolkit/backups/<filename>/`` before overwriting it.
        """

        if output_path.exists():
            create_backup(output_path)

        data = self.build()
        temp_path = output_path.with_suffix(".d2i.tmp")
        try:
            temp_path.write_bytes(data)
            temp_path.replace(output_path)
        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            raise

    # ──────────────────────────────────────────────────────────────────────
    # Change detection
    # ──────────────────────────────────────────────────────────────────────

    def _tab_unchanged(
        self, tab_idx: int, section: D2ISectionInfo, items: list[ParsedItem]
    ) -> bool:
        """Check if a tab's items are identical to what the parser originally returned.

        Compares the current item list against the snapshot taken at
        construction time (via ``_original_items``). A tab is "unchanged"
        when every item's ``source_data`` blob is byte-identical AND
        the list length matches.

        If no original snapshot is available (legacy callers that don't use
        ``from_stash``), falls back to comparing concatenated blobs against
        the original section's item data prefix.
        """
        if self._original_items is not None and tab_idx < len(self._original_items):
            orig = self._original_items[tab_idx]
            if len(items) != len(orig):
                return False
            return all(
                a.source_data is not None
                and b.source_data is not None
                and a.source_data == b.source_data
                for a, b in zip(items, orig)
            )

        # Legacy fallback
        rebuilt = bytearray()
        for item in items:
            if item.source_data is None:
                return False
            rebuilt.extend(item.source_data)
        original_prefix = self._source[section.items_start : section.items_start + len(rebuilt)]
        return bytes(rebuilt) == bytes(original_prefix)

    # ──────────────────────────────────────────────────────────────────────
    # Byte-splice section rebuild
    # ──────────────────────────────────────────────────────────────────────

    def _splice_section(
        self, tab_idx: int, section: D2ISectionInfo, new_items: list[ParsedItem]
    ) -> bytes:
        """Rebuild a section by splicing changed items into the original data.

        D2I sections have two item regions (see SharedStashTab docstring):

        1. **JM-counted items** - covered by ``jm_item_count``. The caller
           (GUI) adds/removes items from this region only.
        2. **Extra items** - items stored after the JM boundary. These are
           part of ``items`` but NOT of the JM count. They live in the
           "extra tail" of the section and are preserved verbatim.

        The splice algorithm:
        - Splits the original item list at ``jm_item_count`` into a JM part
          and an extra part.
        - Splits the new item list at the same boundary (adjusted for any
          adds/removes - extras stay at the end).
        - Rewrites the JM-items region with the modified list.
        - Appends the extra items + any unparsed tail verbatim.
        - Computes the new JM count as
          ``section.item_count + (new_jm_count - orig_jm_count)``.

        When ``_original_items`` is not available (legacy callers), falls
        back to a full rebuild (safe only for Section 5).

        [FIX TC66 v2: correctly handles JM-counted vs extra items so the
         JM count delta matches the actual change in the JM region.]
        """
        if self._original_items is None or tab_idx >= len(self._original_items):
            return self._full_rebuild_section(section, new_items, tab_idx)

        orig_items = self._original_items[tab_idx]

        # tab.items now contains ONLY root items (socket children live
        # inside each parent's socket_children list). No JM/extra split
        # needed - new_items IS the JM item list. [BV TC69]

        # Compute the byte region of the original items (root + children)
        # in the source file. Everything after this = extra-items tail.
        pos = section.items_start
        for it in orig_items:
            if it.source_data:
                pos += len(it.source_data)
            for child in it.socket_children:
                if child.source_data:
                    pos += len(child.source_data)
        original_tail = self._source[pos : section.items_end]

        # ── Tail classification ──────────────────────────────────────────
        # The tail region can contain TWO kinds of bytes:
        #   (a) Section padding - usually a handful of 0x00 bytes the game
        #       writes after the last item. Not semantic.
        #   (b) "Extra items" - real items the parser could not fully
        #       decode, preserved so they survive a splice.
        #
        # Detection: extras are non-padding. Items in D2I DO NOT carry a
        # per-item 'JM' prefix (only the SECTION starts with 'JM'), so the
        # naive `b'JM' in tail` check misses inline items entirely. The
        # forensic analysis of Tab 1 in ModernSharedStashSoftCoreV2.d2i
        # surfaced exactly this: 81-byte tail, no 'JM', yet three item-like
        # 10-00-xx-00 flag headers - real items the parser missed.
        #
        # Safe definition: tail is "pure padding" iff it contains only 0x00
        # bytes. ANY non-zero byte in the tail is treated as potentially-
        # meaningful data and the writer refuses to silently drop it.
        # This is strictly stronger than the old JM-only check.
        tail_has_extras = any(b != 0x00 for b in original_tail)

        # ── SAFETY GUARD (loss-of-save prevention) ───────────────────────
        # When the caller emptied the JM region (no new root items) we must
        # NOT blindly append the tail:
        #   - If tail is pure padding: appending it makes the section larger
        #     than the canonical 68-byte empty form -> D2R refuses to load
        #     the save -> every character becomes inaccessible.
        #     (This is exactly how ModernSharedStashSoftCoreV2.d2i got
        #      corrupted: 69-byte "empty" tabs with a phantom 0x00 byte.)
        #   - If tail contains unparsed extras: writing count=0 while the
        #     extras still sit in the section would silently destroy them
        #     AND leave orphaned JM blobs inside a "zero-item" section.
        if not new_items:
            if tail_has_extras:
                # Count JM markers (real items with a JM prefix) separately
                # from inline flag headers (items stored without JM, which
                # happens in D2I). Both indicate unparsed extras.
                jm_count = original_tail.count(SECTION_MARKER)
                nonzero_bytes = sum(1 for b in original_tail if b != 0x00)
                raise D2IOrphanExtrasError(
                    f"Refusing to empty tab {tab_idx}: the section's raw tail "
                    f"holds {len(original_tail)} bytes of which "
                    f"{nonzero_bytes} are non-zero (likely unparsed items - "
                    f"{jm_count} carry a 'JM' prefix, the rest look like "
                    f"inline item blobs). Clearing the parsed list would "
                    f"orphan them and corrupt the file. Investigate the "
                    f"section before proceeding - this usually means the "
                    f"parser missed items and should be fixed, not the "
                    f"writer worked around."
                )
            # Safe to drop pure padding. Emit canonical 68-byte empty section.
            original_tail = b""

        # Build new item data: each root item + its socket children.
        # Clear D2S-only flags (bit 13) from every blob. [BV TC67]
        new_item_data = bytearray()
        for it in new_items:
            if it.source_data is None:
                raise ValueError(f"Item '{it.item_code}' has no source_data - cannot write.")
            new_item_data.extend(clear_d2s_only_flags(it.source_data))
            for child in it.socket_children:
                if child.source_data is None:
                    raise ValueError(f"Socket child '{child.item_code}' has no source_data.")
                new_item_data.extend(clear_d2s_only_flags(child.source_data))
        new_item_data.extend(original_tail)

        # JM count = number of root items the writer is putting into the
        # JM-counted region of the section. Socket children are inline
        # children of their parent and are NOT counted separately.
        #
        # Why `len(new_items)` rather than `section.item_count + delta`:
        #   The on-disk JM count (`section.item_count`) sometimes UNDER-
        #   counts what the parser captured. The parser is permissive and
        #   keeps decoding past the JM boundary as long as the bit-stream
        #   is well-formed - those "parser-captured extras" land in
        #   `orig_items` even though the on-disk JM header doesn't include
        #   them.
        #
        #   The old delta-style formula (`section.item_count + (len(new) -
        #   len(orig))`) underflowed in that case: emptying a tab with
        #   parser-captured extras computed a NEGATIVE JM count, which
        #   then raised `struct.error` from `pack_into("<H", ...)` when
        #   the user tried to archive every item in such a tab.
        #
        # Promoting parser-captured extras to JM-counted on splice is
        # semantically safe: those items ARE present in the new file and
        # the game reads them as JM-counted on next load. No item data
        # is lost, and the file ends up in canonical (extras-free) shape.
        # Bytes the parser could NOT decode at all stay in `original_tail`
        # and remain uncounted (true tail extras).
        new_jm_count = len(new_items)

        # The JM count is a uint16 in the section header. Refuse to emit
        # rather than silently truncate via `pack_into("<H", ...)`.
        if not 0 <= new_jm_count <= 0xFFFF:
            raise D2IWriterIntegrityError(
                f"Tab {tab_idx}: computed new JM count {new_jm_count} "
                f"is out of uint16 range [0, 65535]. "
                f"(orig items={len(orig_items)}, new items={len(new_items)}, "
                f"section.item_count={section.item_count}). "
                f"Refusing to emit a malformed section."
            )

        # Build new section
        new_section_size = D2I_HEADER_SIZE + 4 + len(new_item_data)
        result = bytearray(new_section_size)

        # Copy original 64-byte header verbatim
        result[:D2I_HEADER_SIZE] = self._source[
            section.header_offset : section.header_offset + D2I_HEADER_SIZE
        ]
        # Update section_size
        struct.pack_into("<I", result, 0x10, new_section_size)
        # JM marker + count
        result[D2I_HEADER_SIZE : D2I_HEADER_SIZE + 2] = SECTION_MARKER
        struct.pack_into("<H", result, D2I_HEADER_SIZE + 2, new_jm_count)
        # Item data
        result[D2I_HEADER_SIZE + 4 :] = new_item_data

        parser_extras = max(0, len(orig_items) - section.item_count)
        logger.info(
            "Spliced tab %d: JM count %d -> %d (%+d), "
            "items %d -> %d, section %d -> %d bytes (%+d), "
            "parser-extras=%d, tail=%d bytes",
            tab_idx,
            section.item_count,
            new_jm_count,
            new_jm_count - section.item_count,
            len(orig_items),
            len(new_items),
            section.section_size,
            new_section_size,
            new_section_size - section.section_size,
            parser_extras,
            len(original_tail),
        )

        return bytes(result)

    def _full_rebuild_section(
        self, original: D2ISectionInfo, items: list[ParsedItem], tab_idx: int
    ) -> bytes:
        """Rebuild a section from scratch using only the parsed items.

        This is the LEGACY path used when ``_original_items`` is not
        available. It works correctly ONLY for Section 5 (Gems / Materials
        / Runes), where every item is a fully-parsed simple stackable
        with no socket children and no unparsed tail.

        For grid tabs (0..4) the parser typically returns a subset of the
        actual binary content (socket children inline, complex encodings,
        section padding) - a full rebuild from parsed items would silently
        drop those bytes and corrupt the file. To prevent that, this
        method hard-fails for any non-Section-5 tab; callers MUST use
        :meth:`from_stash` to enable the byte-splice path instead.
        """
        if tab_idx != SECTION5_TAB_INDEX:
            raise RuntimeError(
                f"_full_rebuild_section refuses to rebuild grid tab {tab_idx}: "
                f"this path loses socket children and unparsed bytes. "
                f"Construct the writer via D2IWriter.from_stash(source, stash) "
                f"so the byte-splice path is used."
            )
        item_data = bytearray()
        for item in items:
            if item.source_data is None:
                raise ValueError(f"Item '{item.item_code}' has no source_data - cannot write.")
            item_data.extend(clear_d2s_only_flags(item.source_data))
            for child in item.socket_children:
                if child.source_data is None:
                    raise ValueError(f"Socket child '{child.item_code}' has no source_data.")
                item_data.extend(clear_d2s_only_flags(child.source_data))

        new_section_size = D2I_HEADER_SIZE + 4 + len(item_data)
        section = bytearray(new_section_size)

        orig_header = self._source[
            original.header_offset : original.header_offset + D2I_HEADER_SIZE
        ]
        section[:D2I_HEADER_SIZE] = orig_header

        struct.pack_into("<I", section, 0x10, new_section_size)

        section[D2I_HEADER_SIZE : D2I_HEADER_SIZE + 2] = SECTION_MARKER
        struct.pack_into("<H", section, D2I_HEADER_SIZE + 2, len(items))

        section[D2I_HEADER_SIZE + 4 :] = item_data
        return bytes(section)

    @classmethod
    def from_stash(cls, source_data: bytes, stash: "ParsedSharedStash") -> "D2IWriter":
        """Create a writer with a snapshot of the current stash state.

        Args:
            source_data: Original .d2i file bytes.
            stash:       ParsedSharedStash from D2IParser.parse()
        """
        tabs = [list(tab.items) for tab in stash.tabs]
        original = [list(tab.items) for tab in stash.tabs]
        return cls(source_data, tabs, _original_items=original)

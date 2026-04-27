"""
Parser for D2RR (Reimagined) SharedStash files (.d2i).

## Verified file structure (TC04 / TC05 / TC06 - [BV])

The .d2i file is a sequence of **section-header-delimited** sections. Per
the spec (docs/spec/d2s_format_spec.md §4), every .d2i contains exactly
**7 sections**: 6 JM-delimited tab sections followed by 1 block of
trailing metadata.

Each of the 6 tab sections:
  * 64-byte section header (starts with signature ``0xAA55AA55``,
    stores ``section_size`` as a ``uint32`` at offset 0x10).
  * ``'JM'`` marker (2 bytes) + item count (``uint16`` LE) at header+64.
  * N items in standard .d2s item format (shared by .d2i and .d2s).

Section 6 (trailing metadata) is **148 bytes with no signature and no
JM marker** - game-internal tracking data (timestamps, session IDs)
that the game overwrites on every save. Preserved verbatim by the
writer; not parsed into the item model.

Sections 0-4 are grid tabs; section 5 is the Gems/Materials/Runes
special tab; section 6 is the trailing metadata block.

Sources:
  TC04 (empty stash):       6 canonical empty tab sections + trailer  [BV]
  TC05 (populated tabs):    6 tab sections + trailer                   [BV]
  TC06 (dense stash):       6 tab sections + trailer                   [BV]
  TC58 (write-read roundtrip): section sizes 131,68,68,68,68,68,148    [BV]

Section enumeration is signature-driven (not a JM byte-pair scan) so
that coincidental ``0x4A 0x4D`` bytes inside section 6's tracking data
cannot produce a phantom 7th tab.

Item fidelity:
  Items parsed from .d2i have the same bit-range tracking as .d2s items
  (source_start_bit, source_bit_length, raw_bits) - required by the writer
  for restore operations.
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass, field
from pathlib import Path

from d2rr_toolkit.constants import D2I_TAB_GOLD_MAX
from d2rr_toolkit.models.character import ParsedItem
from d2rr_toolkit.parsers.d2s_parser import D2SParser

logger = logging.getLogger(__name__)

# [BV] D2I file constants
_D2I_SIGNATURE = 0xAA55AA55  # same as .d2s
_D2I_HEADER_SIZE = 64  # header is always 64 bytes (0x40)
_JM_MARKER = b"JM"


@dataclass
class SharedStashTab:
    """One tab of the shared stash.

    The D2I binary format stores items in two regions per section:

    1. **JM-counted items** - the uint16 after the JM marker tells the
       game how many items follow inline. Socket children of socketed
       items are included in this count.
    2. **Extra items** - some sections contain additional items AFTER the
       JM-counted region (same binary format, but not included in the
       count). These are real stash items that the game writes past the
       JM boundary.

    ``items`` contains ALL items from both regions.
    ``jm_item_count`` records how many came from region 1 so the writer
    can compute correct JM-count deltas when items are added or removed.

    [BINARY_VERIFIED 2026-04-12: Tab 0 has 36 JM + 0 extra; Tab 3 has
     27 JM (1 parse failure) + 10 extra; Tab 4 has 34 JM + 8 extra.]

    Per-tab ``gold`` is read from offset 0x0C of the page header (u32 LE).
    Reimagined v105 caps gold at 2,500,000 per tab; the parser logs a
    warning if a parsed value exceeds that cap. The gold field is purely
    informational on read - the writer preserves the original page header
    bytes verbatim, so gold round-trips automatically.
    """

    tab_index: int
    items: list[ParsedItem] = field(default_factory=list)
    jm_count_byte_offset: int = 0  # byte offset of the JM count uint16 in the file
    jm_item_count: int = 0  # number of items that came from the JM-counted region
    gold: int = 0  # per-tab gold (u32 LE at page header offset 0x0C). [BV]


@dataclass
class ParsedSharedStash:
    """Complete parsed shared stash from a .d2i file."""

    source_path: Path
    tabs: list[SharedStashTab] = field(default_factory=list)

    @property
    def all_items(self) -> list[ParsedItem]:
        """All items across all tabs."""
        result: list[ParsedItem] = []
        for tab in self.tabs:
            result.extend(tab.items)
        return result

    @property
    def total_items(self) -> int:
        """Return the sum of ``len(tab.items)`` across every tab."""

        return sum(len(tab.items) for tab in self.tabs)


class D2IParseError(Exception):
    """Raised when parsing a .d2i file fails."""


class D2IParser:
    """Parser for D2RR (Reimagined) SharedStash files (.d2i).

    Reuses D2SParser.parse_d2i_tab_from_bytes() so item parsing logic
    is never duplicated.

    Usage::

        parser = D2IParser(Path("SharedStashSoftCoreV2.d2i"))
        stash = parser.parse()
        print(f"{stash.total_items} items across {len(stash.tabs)} tabs")
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    def parse(self) -> ParsedSharedStash:
        """Parse the .d2i file and return all stash tabs with their items.

        ## How tab discovery works

        Sections are enumerated via a **signature-driven walk** - the same
        algorithm :func:`d2rr_toolkit.writers.d2i_writer._find_sections`
        uses, so parser and writer agree on section boundaries by
        construction.

        For each section:
          1. Read the ``0xAA55AA55`` signature at ``pos``. If absent, we
             have reached the trailing metadata (spec section 6) and
             stop - that block is preserved verbatim by the writer and
             is not meaningful to the item model.
          2. Read ``section_size`` as a ``uint32`` at ``pos + 0x10``.
          3. The ``'JM'`` marker must appear at ``pos + 64``; the
             ``uint16`` item count follows.
          4. Parse items bounded by ``pos + section_size``.
          5. Advance ``pos`` by ``section_size`` and repeat.

        This is strictly stronger than the previous forward-JM-scan
        approach: the trailing metadata (148 bytes of timestamps +
        session IDs) can legitimately contain the byte pair
        ``0x4A 0x4D`` anywhere, which the old algorithm misinterpreted
        as a phantom 7th tab. The signature check terminates the loop
        cleanly at the end of the real sections.

        Returns:
            ParsedSharedStash with tabs and items populated.

        Raises:
            D2IParseError:     Structural error in the file.
            FileNotFoundError: File does not exist.
        """
        if not self._path.exists():
            raise FileNotFoundError(f"Stash file not found: {self._path}")

        data = self._path.read_bytes()
        logger.info("Parsing .d2i stash: %s (%d bytes)", self._path, len(data))

        self._validate_header(data)

        stash = ParsedSharedStash(source_path=self._path)

        pos = 0
        tab_index = 0

        while pos + _D2I_HEADER_SIZE + 4 <= len(data):
            sig = struct.unpack_from("<I", data, pos)[0]
            if sig != _D2I_SIGNATURE:
                # Trailing metadata (spec section 6, no signature).
                # Preserved verbatim by the writer; not parsed here.
                logger.debug(
                    "Stopping section walk at byte 0x%X - no 0xAA55AA55 "
                    "signature (trailing metadata begins here, %d bytes).",
                    pos,
                    len(data) - pos,
                )
                break

            section_size = struct.unpack_from("<I", data, pos + 16)[0]
            if section_size <= 0 or pos + section_size > len(data):
                logger.warning(
                    "Section %d at byte 0x%X has invalid section_size=%d "
                    "(file length=%d) - stopping.",
                    tab_index,
                    pos,
                    section_size,
                    len(data),
                )
                break

            jm_offset = pos + _D2I_HEADER_SIZE
            section_end = pos + section_size

            # Per-page gold lives at offset 0x0C of the page header. Read
            # it before the JM check so we can observe / log gold even on
            # pages we end up skipping (e.g. the v105 trailing audit page,
            # which has gold=0 by convention).
            page_gold = struct.unpack_from("<I", data, pos + 0x0C)[0]
            if page_gold > D2I_TAB_GOLD_MAX:
                logger.warning(
                    "Section %d at byte 0x%X: gold=%d exceeds the per-tab "
                    "cap of %d. The game enforces this cap on save; the "
                    "value will be preserved verbatim by the writer but "
                    "may be silently re-clamped on next in-game save.",
                    tab_index,
                    pos,
                    page_gold,
                    D2I_TAB_GOLD_MAX,
                )

            if data[jm_offset : jm_offset + 2] != _JM_MARKER:
                logger.warning(
                    "Section %d at byte 0x%X: expected 'JM' at 0x%X but "
                    "found %r - skipping section.",
                    tab_index,
                    pos,
                    jm_offset,
                    data[jm_offset : jm_offset + 2],
                )
                pos += section_size
                continue

            logger.debug(
                "Parsing stash tab %d at byte 0x%X (section 0x%X..0x%X, %d bytes)",
                tab_index,
                jm_offset,
                pos,
                section_end,
                section_size,
            )
            try:
                items, jm_count_offset, _end_byte, jm_item_count = (
                    D2SParser.parse_d2i_tab_from_bytes(
                        data,
                        start_byte=jm_offset,
                        section_end_byte=section_end,
                    )
                )
            except Exception as e:
                logger.warning(
                    "Failed to parse stash tab %d at byte 0x%X: %s - stopping.",
                    tab_index,
                    jm_offset,
                    e,
                )
                break

            tab = SharedStashTab(
                tab_index=tab_index,
                items=items,
                jm_count_byte_offset=jm_count_offset,
                jm_item_count=jm_item_count,
                gold=page_gold,
            )
            stash.tabs.append(tab)
            logger.info(
                "Stash tab %d: %d item(s) (%d JM-counted + %d extra)",
                tab_index,
                len(items),
                jm_item_count,
                len(items) - jm_item_count,
            )

            pos += section_size
            tab_index += 1

        if not stash.tabs:
            logger.warning("No stash tabs found in %s", self._path)

        return stash

    # ──────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _validate_header(data: bytes) -> None:
        """Check the signature and minimum size. [BV]"""
        if len(data) < _D2I_HEADER_SIZE:
            raise D2IParseError(
                f"File too small ({len(data)} bytes) - minimum is "
                f"{_D2I_HEADER_SIZE} bytes for the .d2i header."
            )
        sig = struct.unpack_from("<I", data, 0)[0]
        if sig != _D2I_SIGNATURE:
            raise D2IParseError(
                f"Unexpected signature 0x{sig:08X} at offset 0. "
                f"Expected 0x{_D2I_SIGNATURE:08X}. "
                f"Is this a valid D2R SharedStash file?"
            )

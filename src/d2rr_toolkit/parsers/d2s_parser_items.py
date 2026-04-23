"""Item parsing - mixin extracted from D2SParser.

The largest chunk of the parser - item-list iteration + single-item
parse + type-specific data + property list + Reimagined-specific
retries. Every method moved verbatim (no body changes) so the
byte-exact golden diff stays green.

The public surface on :class:`D2SParser` is unchanged: it now simply
inherits these methods via :class:`ItemsParserMixin`.

All [BV] / [BINARY_VERIFIED] / [TC##] tags preserved at their new
line numbers.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from d2rr_toolkit.constants import (
    ITEM_BIT_EQUIPPED_SLOT,
    ITEM_BIT_ETHEREAL,
    ITEM_BIT_HUFFMAN_START,
    ITEM_BIT_IDENTIFIED,
    ITEM_BIT_LOCATION_ID,
    ITEM_BIT_PANEL_ID,
    ITEM_BIT_PERSONALIZED,
    ITEM_BIT_POSITION_X,
    ITEM_BIT_POSITION_Y,
    ITEM_BIT_RUNEWORD,
    ITEM_BIT_SIMPLE,
    ITEM_BIT_SOCKETED,
    ITEM_BIT_STARTER_ITEM,
    EXT_WIDTH_ILVL,
    EXT_WIDTH_QUALITY,
    EXT_WIDTH_UNIQUE_ID,
    ARMOR_SAVE_ADD_DEFENSE,
    ARMOR_WIDTH_CUR_DUR,
    ARMOR_WIDTH_DEFENSE,
    ARMOR_WIDTH_DURABILITY,
    ARMOR_WIDTH_MAX_DUR,
    WEAPON_WIDTH_CUR_DUR,
    WEAPON_WIDTH_MAX_DUR,
    WEAPON_WIDTH_POST_DUR,
    ITEM_STATS_TERMINATOR,
    SECTION_MARKER_ITEMS,
    SIMPLE_ITEM_SOCKET_BIT_WIDTH,
    QUALITY_NAMES,
)
from d2rr_toolkit.exceptions import (
    HuffmanDecodeError,
    SpecVerificationError,
)
from d2rr_toolkit.game_data.item_names import get_item_names_db
from d2rr_toolkit.game_data.item_stat_cost import get_isc_db
from d2rr_toolkit.game_data.item_types import ItemCategory, get_item_type_db
from d2rr_toolkit.game_data.skills import get_skill_db
from d2rr_toolkit.models.character import (
    ItemArmorData,
    ItemDurability,
    ItemExtendedHeader,
    ItemFlags,
    ParsedItem,
)
from d2rr_toolkit.parsers.exceptions import GameDataNotLoadedError
from d2rr_toolkit.parsers.huffman import decode_item_code

if TYPE_CHECKING:
    from collections.abc import Callable

    from d2rr_toolkit.parsers.bit_reader import BitReader

logger = logging.getLogger(__name__)


# ── Quality-specific-data dispatch table ─────────────────────────────────────
# Maps the 4-bit quality value to the ItemsParserMixin method that reads
# the quality's extra bits. Unknown qualities return {} (zero bits read).
# The ladder this replaces lived in _read_quality_specific_data; each
# per-quality reader is now <20 LOC and unit-testable in isolation.
#
# Rare (6) and Crafted (8) share a reader - both are 8+8 name IDs +
# 6*(1+opt 11) affix slots. The Reimagined 7th-slot extension for MISC
# rare items fires later via the retry path in _parse_single_item (see
# project_rare_misc_7slot_qsd.md).
_QUALITY_READERS: dict[int, Any] = {}  # populated at module tail, after class body


class ItemsParserMixin:
    """Mixin hosting every item-parsing method previously on :class:`D2SParser`.

    Depends on parser-owned state:
      * ``self._reader: BitReader``
      * ``self._data: bytes``
      * ``self._section_end_byte: int | None``  (D2I tab-bound)
      * ``self._trailing_item_bytes: bytes | None``
      * per-item ephemeral state (``self._item_start_bit``,
        ``self._current_item_properties``, ``self._set_bonus_mask``,
        ``self._total_nr_of_sockets``, ``self._misc_qty``,
        ``self._misc_qty_bit_offset``,
        ``self._current_set_bonus_properties``,
        ``self._qsd_rare_retry_needed``,
        ``self._skip_corpse_and_merc`` - the last one is a D2I tab
        parse shortcut surfaced by :meth:`parse_d2i_tab_from_bytes`).

    Every method body is byte-identical to the pre-move version - see
    the golden-diff gate (``tests/test_d2s_parse_snapshot.py``) for
    continuous verification.

    Attribute declarations below are PEP 526 annotation-only (no
    assignment, no ``__init__``) so mypy can resolve ``self._...``
    accesses when this mixin is type-checked in isolation. The real
    instances are populated by :meth:`D2SParser.__init__` and by the
    per-item code paths below; see the docstring bullet list above.
    """

    # ── Parser-owned state (populated by D2SParser.__init__) ────────────
    _reader: "BitReader | None"
    _data: bytes
    _section_end_byte: int | None
    _trailing_item_bytes: bytes | None

    # ── Per-item / section ephemeral state (populated during parsing) ──
    _item_start_bit: int
    _current_item_properties: list[dict[str, Any]]
    _current_set_bonus_properties: list[dict[str, Any]]
    _set_bonus_mask: int
    _total_nr_of_sockets: int
    _misc_qty: int | None
    _misc_qty_bit_offset: int | None
    _qsd_rare_retry_needed: bool
    _skip_corpse_and_merc: bool
    _jm_count_byte_offset: int | None
    _corpse_jm_byte_offset: int | None

    # ── Helpers defined on the concrete parser / sibling mixins ─────────
    _require_reader: "Callable[[], BitReader]"

    def _parse_item_list(self) -> list[ParsedItem]:
        """Parse the complete D2S item section: JM items + socket children + extra items.

        Orchestrates three phases:
          1. _parse_jm_items(): Read JM header + parse counted items
          2. _parse_socket_children(): Parse socket children after JM items
          3. _parse_extra_items(): Parse remaining items until 2nd JM + validate

        Returns:
            Complete list of all parsed items.
        """
        items, self._jm_count_byte_offset = self._parse_jm_items()
        # D2S note: socket children of EQUIPPED items are already included
        # in the JM count (inline after their parent). Socket children of
        # STASH items are in the extra items section.
        items.extend(self._parse_extra_items(last_parent=items[-1] if items else None))
        self._validate_2nd_jm_marker()
        return items

    # ──────────────────────────────────────────────────────────
    # Item list sub-parsers (shared between D2S and D2I)
    # ──────────────────────────────────────────────────────────

    def _parse_jm_items(self) -> tuple[list[ParsedItem], int]:
        """Parse the JM-counted item list.

        Reads the JM header (2 bytes 'JM' + uint16 count), then parses
        exactly `count` items with inter-item padding detection.

        On parse error: attempts byte-level recovery to find the next item.
        If recovery fails, returns the items parsed so far.

        Returns:
            (items, jm_count_byte_offset) tuple.
        """
        reader = self._require_reader()

        # Verify 'JM' marker [BV]
        marker = reader.peek_bytes(2)
        if marker != SECTION_MARKER_ITEMS:
            raise SpecVerificationError(
                field="item_list_marker",
                byte_offset=reader.byte_pos,
                bit_offset=reader.bit_pos,
                expected=SECTION_MARKER_ITEMS.hex(),
                found=marker.hex(),
                context="'JM' item list marker expected.",
            )

        reader.read_bytes_raw(2)  # skip 'JM'
        jm_count_byte_offset = reader.byte_pos
        item_count = reader.read_uint16_le()
        logger.info("Item list: %d items", item_count)

        items: list[ParsedItem] = []
        for i in range(item_count):
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "Parsing item %d/%d at bit %d", i + 1, item_count, reader.bit_pos
                )
            try:
                item = self._parse_single_item()
                # Assign socket children to their parent: items with
                # location_id=6 belong to the preceding root item.
                if item.flags.location_id == 6 and items:
                    items[-1].socket_children.append(item)
                else:
                    items.append(item)
                # For the last JM item, enable marker-fallback scanning:
                # if no extras follow, the next bytes are the 2nd JM marker
                # (corpse list) and the Huffman probe alone cannot detect the
                # 1-7 padding bytes that still belong to this item. Without
                # check_jm=True they would be silently dropped.
                is_last = i == item_count - 1
                self._skip_inter_item_padding(item, check_jm=is_last)
            except (HuffmanDecodeError, Exception) as e:
                logger.warning(
                    "Parse failed on item %d/%d: %s - attempting recovery.",
                    i + 1,
                    item_count,
                    e,
                )
                if not self._try_recover_item_alignment(item_count - i - 1):
                    logger.error(
                        "Recovery failed - returning %d of %d items.",
                        len(items),
                        item_count,
                    )
                    break

        return items, jm_count_byte_offset

    def _parse_socket_children(self, parents: list[ParsedItem]) -> list[ParsedItem]:
        """Parse socket children for all socketed parent items.

        Socket children are stored AFTER the JM-counted items in both D2S
        and D2I files. The number of children is determined by the parent's
        total_nr_of_sockets field (only for filled sockets - parents with
        empty sockets have no children in the binary).

        [BV]

        Args:
            parents: Previously parsed parent items (from _parse_jm_items).

        Returns:
            List of socket child items (may be empty).
        """
        reader = self._require_reader()

        # Count expected socket children: total sockets of all parents that
        # are SOCKETED, MINUS any socket children that already appeared in
        # the JM item list (location_id=6). D2I JM count is root-items-only
        # but some children may appear within the JM byte range. [BV TC67]
        total_sockets: int = sum(
            (it.total_nr_of_sockets or 0)
            for it in parents
            if it.flags is not None
            and it.flags.socketed
            and it.location_name != "Socketed"
        )
        already_in_jm: int = sum(
            1
            for it in parents
            if it.flags is not None and it.flags.location_id == 6  # SOCKETED
        )
        expected = total_sockets - already_in_jm
        if expected < 0:
            expected = 0

        # Read ALL remaining items in the section, not just `expected`.
        # The D2I format stores regular items after the JM-counted region,
        # and the only way to find them all is to keep reading until no
        # more valid Huffman codes can be decoded. The `expected` count is
        # used as a MINIMUM: we always read at least that many, then
        # continue if more valid items are found.
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Parsing socket children: expected=%d (total_sockets=%d, already_in_jm=%d)",
                expected,
                total_sockets,
                already_in_jm,
            )
        extras: list[ParsedItem] = []
        consecutive_failures = 0
        successful_reads = 0
        max_items = expected + 200  # safety limit
        exit_reason = "loop-end"
        # Track the last root item for child assignment. If extras
        # start with a socket child, it belongs to the last JM parent.
        last_root: ParsedItem | None = parents[-1] if parents else None
        for child_idx in range(max_items):
            if reader.bits_remaining < 80:
                exit_reason = f"bits_remaining<80 at idx {child_idx}"
                break
            # Respect section boundary
            if (
                self._section_end_byte is not None
                and reader.bit_pos >= self._section_end_byte * 8 - 53
            ):
                exit_reason = f"section-boundary at idx {child_idx}"
                break
            try:
                item = self._parse_single_item()
                # Assign socket children to their parent.
                if item.flags.location_id == 6 and last_root is not None:
                    last_root.socket_children.append(item)
                else:
                    extras.append(item)
                    last_root = item
                consecutive_failures = 0
                successful_reads += 1
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "Extra item %d: %s (location=%d)",
                        child_idx + 1,
                        item.item_code,
                        item.flags.location_id if item.flags else -1,
                    )
                self._skip_inter_item_padding(item)
            except Exception as e:
                consecutive_failures += 1
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "Extra-items parse failed at attempt %d "
                        "(consecutive=%d, successful=%d, expected=%d): %s",
                        child_idx + 1,
                        consecutive_failures,
                        successful_reads,
                        expected,
                        e,
                    )
                # Exit conditions:
                #  - 2 consecutive failures: likely reading past real data.
                #  - Past the expected count: next read is allowed to fail
                #    without signalling a parser regression.
                # When we exit BELOW the expected count with failures, that
                # is a surprising outcome - surface it so regressions in
                # the upstream parser path (like the item 25 rare-MISC bug)
                # don't silently truncate the extras list again.
                if consecutive_failures >= 2:
                    exit_reason = (
                        f"2 consecutive failures at idx {child_idx} "
                        f"(successful={successful_reads}, expected={expected})"
                    )
                    break
                if child_idx >= expected:
                    exit_reason = (
                        f"past expected count at idx {child_idx} "
                        f"(successful={successful_reads}, expected={expected})"
                    )
                    break

        if successful_reads < expected and logger.isEnabledFor(logging.INFO):
            logger.info(
                "Socket-children loop exited with %d/%d expected items "
                "(reason: %s). If the tail contains real items, this is "
                "an upstream parser bug - NOT a socket-loop bug.",
                successful_reads,
                expected,
                exit_reason,
            )

        # Ghost item cleanup: Set/Unique items produce 6-7 bytes of
        # inter-item padding at D2I section boundaries.
        db = get_item_type_db()
        while extras and not db.contains(extras[-1].item_code):
            ghost = extras.pop()
            target = extras[-1] if extras else (parents[-1] if parents else None)
            if target and ghost.source_data and target.source_data:
                target.source_data = target.source_data + ghost.source_data
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "Ghost item '%s' (%d bytes) appended as padding to '%s'",
                        ghost.item_code,
                        len(ghost.source_data),
                        target.item_code,
                    )

        return extras

    def _parse_extra_items(self, *, last_parent: ParsedItem | None = None) -> list[ParsedItem]:
        """Parse extra items after the JM list (D2S only).

        In D2S files, additional items (socket children of stash items,
        misc items like OnyxGrabber, Gem Bag, Horadric Cube) are stored
        after the JM-counted items and before the 2nd JM marker. These
        items are NOT counted in the JM header.

        Args:
            last_parent: Last root item from the JM list. Socket children
                at the start of the extras region are assigned to this parent.

        [BV]

        Returns:
            List of extra items (may be empty).
        """
        reader = self._require_reader()

        extras: list[ParsedItem] = []
        if reader.bits_remaining < 16:
            return extras

        while reader.peek_bytes(2) != SECTION_MARKER_ITEMS:
            if reader.bits_remaining < 80:
                break
            child_start = reader.bit_pos

            # [BV] Pre-validate: probe the Huffman code at
            # bit 53 to check if the data ahead is a valid item.  If the
            # decoded code is not in the item database, we have reached the
            # end of the item region (trailing padding before 2nd JM marker).
            try:
                reader.seek_bit(child_start + ITEM_BIT_HUFFMAN_START)
                probe_code, _ = decode_item_code(reader)
                probe_valid = get_item_type_db().contains(probe_code)
            except Exception:
                probe_valid = False
            reader.seek_bit(child_start)
            if not probe_valid:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "Extra item probe at bit %d: no valid item code - "
                        "end of item region, scanning to 2nd JM.",
                        child_start,
                    )
                # Skip remaining padding bytes until the 2nd JM marker.
                reader.skip_to_byte_boundary()
                while reader.bits_remaining >= 16:
                    if reader.peek_bytes(2) == SECTION_MARKER_ITEMS:
                        break
                    reader.read(8)
                break

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Parsing extra item at bit %d", child_start)
            try:
                child = self._parse_single_item()
                # Assign socket children to their parent (last root
                # in extras, or last_parent from JM list as fallback).
                if child.flags.location_id == 6:
                    target = extras[-1] if extras else last_parent
                    if target is not None:
                        target.socket_children.append(child)
                    else:
                        extras.append(child)  # orphan - shouldn't happen
                else:
                    extras.append(child)
                    last_parent = child  # update for subsequent children
                logger.info(
                    "Extra item after JM list: %s (location=%d)",
                    child.item_code,
                    child.flags.location_id,
                )
                self._skip_inter_item_padding(child, check_jm=True)
            except Exception as e:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "Extra item parse ended at bit %d: %s. Scanning for 2nd JM.",
                        child_start,
                        e,
                    )
                reader.seek_bit(child_start)
                reader.skip_to_byte_boundary()
                trail_start = reader.byte_pos
                while reader.bits_remaining >= 16:
                    if reader.peek_bytes(2) == SECTION_MARKER_ITEMS:
                        break
                    reader.read(8)
                trail_end = reader.byte_pos
                if trail_end > trail_start:
                    self._trailing_item_bytes = self._data[trail_start:trail_end]
                    logger.info(
                        "Captured %d trailing item bytes (byte %d..%d) for writer preservation.",
                        len(self._trailing_item_bytes),
                        trail_start,
                        trail_end,
                    )
                break

        return extras

    def _skip_inter_item_padding(self, item: ParsedItem, check_jm: bool = False) -> None:
        """Detect, skip, and PRESERVE inter-item padding after an item.

        [BV]
        [BV] Applies to simple items too - when a simple
        item's (53 + huffman + 1 [+ 9]) bits happen to land on an exact
        byte boundary (e.g. hp2/mp2 with 18-bit Huffman codes), the game
        still pads with a full trailing byte. Without this helper, the
        parser stays on the boundary, skipping zero bits, and cascades
        into the next item mid-stream. See test fixture SimpleItems.d2s.

        Some items have 8-56 bits of padding after the property list
        terminator. This padding is REQUIRED by the game when writing
        items back to D2I files - without it, the game crashes.

        The padding bytes are deterministic per item (same item always
        produces the same padding). They are appended to the item's
        source_data blob so that the D2I writer preserves them.

        Detection: probe for valid Huffman codes at 8-bit intervals.

        Args:
            item:     The item just parsed (source_data will be extended).
            check_jm: If True, also check for JM marker before probing.
        """
        reader = self._require_reader()
        if not (item.item_code and reader.bits_remaining >= 80):
            return
        if check_jm and reader.peek_bytes(2) == SECTION_MARKER_ITEMS:
            return

        # D2I section boundary: do NOT probe past this byte offset.
        # Without this limit, the last item in a D2I section would "see" the
        # next section's 64-byte header (starting with 0xAA55AA55) and
        # mistakenly append up to 20 bytes of header data as "padding" to the
        # item's source_data. When that blob is later written into a D2S file,
        # the embedded section header bytes corrupt the item stream.
        section_end_bit = self._section_end_byte * 8 if self._section_end_byte is not None else None

        db = get_item_type_db()
        save_pos = reader.bit_pos
        found_padding = 0
        # Collect ALL valid Huffman candidates, then pick the
        # one with the most plausible item flags. The old "stop at first hit"
        # approach fell victim to false positives: obsolete item codes (e.g.
        # 'scs' from an old Reimagined version) in misc.txt that happen to
        # appear in the padding byte stream at an earlier offset than the real
        # next item. The false positive had location_id=2 (BELT) which is
        # impossible for a stash item - the plausibility check rejects it.
        candidates: list[tuple[int, str]] = []  # (pad_test, code)
        for pad_test in range(0, 64, 8):
            probe_bit = save_pos + pad_test + 53
            # Stop if the probe would read past the section boundary.
            if section_end_bit is not None and probe_bit >= section_end_bit:
                break
            try:
                reader.seek_bit(probe_bit)
                test_code, _ = decode_item_code(reader)
                if db.contains(test_code):
                    candidates.append((pad_test, test_code))
            except Exception:
                continue
        # Pick the best candidate: prefer items with plausible location_id.
        # Valid locations: 0=STORED, 1=EQUIPPED, 6=SOCKETED.
        # Invalid in stash/inventory context: 2=BELT, 3/4/5/7=other.
        for pad_test, test_code in candidates:
            # Read location_id (3 bits at item-relative bit 35)
            try:
                reader.seek_bit(save_pos + pad_test + 35)
                loc_id = reader.read(3)
                if loc_id in (0, 1, 6):  # STORED, EQUIPPED, SOCKETED
                    found_padding = pad_test
                    break
            except Exception:
                continue
        if found_padding == 0 and candidates:
            # Fallback: if no plausible candidate, take the first one anyway
            # (better than nothing - at least it's a valid Huffman code)
            found_padding = candidates[0][0]
        # If no next item was found via Huffman probe, check if a section
        # marker (JM/jf/kf) follows after the padding.  This handles the
        # last item before the corpse/merc/golem section where no next item
        # exists but inter-item padding bytes still need to be captured.
        if found_padding == 0 and check_jm:
            for pad_test in range(8, 64, 8):
                try:
                    reader.seek_bit(save_pos + pad_test)
                    if (save_pos + pad_test) % 8 != 0:
                        continue
                    marker = reader.peek_bytes(2)
                    if marker in (SECTION_MARKER_ITEMS, b"jf", b"kf"):
                        found_padding = pad_test
                        break
                except Exception:
                    continue
        reader.seek_bit(save_pos)
        if found_padding > 0:
            # Extract the padding bytes and append to item's source_data.
            # This keeps the padding attached so the D2I writer puts it back when
            # writing items, preventing game crashes from missing padding.
            padding_start_byte = save_pos // 8
            padding_end_byte = (save_pos + found_padding + 7) // 8
            padding_bytes = reader._data[padding_start_byte:padding_end_byte]
            if item.source_data is not None:
                item.source_data = item.source_data + padding_bytes
            reader.read(found_padding)
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "Inter-item padding: %d bits (%d bytes) after '%s' - appended to source_data",
                    found_padding,
                    len(padding_bytes),
                    item.item_code,
                )

    def _validate_2nd_jm_marker(self) -> None:
        """Validate the 2nd JM marker (corpse item list) at end of D2S items.

        [BV] After all items (JM + socket children + extras),
        the corpse list JM marker should be present (normally count=0).

        Stores the byte offset of the corpse JM marker for writer use.
        """
        reader = self._require_reader()
        self._corpse_jm_byte_offset: int | None = None
        if reader.bits_remaining >= 16:
            next2 = reader.peek_bytes(2)
            if next2 == SECTION_MARKER_ITEMS:
                self._corpse_jm_byte_offset = reader.byte_pos
                reader.read_bytes_raw(2)
                corpse_count = reader.read_uint16_le()
                logger.info(
                    "Post-parse OK: 2nd JM marker found (corpse list, count=%d) at byte %d",
                    corpse_count,
                    self._corpse_jm_byte_offset,
                )
                if corpse_count > 0:
                    logger.warning(
                        "Character has non-empty corpse (count=%d). Corpse item "
                        "parsing is not yet implemented; skipping merc section too.",
                        corpse_count,
                    )
                    self._skip_corpse_and_merc = True
            else:
                logger.warning(
                    "POST-PARSE VALIDATION FAILED: Expected 2nd 'JM' marker at "
                    "byte %d (bit %d), but found %s.",
                    reader.byte_pos,
                    reader.bit_pos,
                    next2.hex(),
                )
        else:
            logger.warning(
                "POST-PARSE VALIDATION: Not enough bits remaining (%d) for 2nd JM marker.",
                reader.bits_remaining,
            )

    # _parse_merc_section moved to d2s_parser_merc.py.

    # ──────────────────────────────────────────────────────────
    # Single item parsing [BV]
    # ──────────────────────────────────────────────────────────

    def _parse_single_item(self) -> ParsedItem:
        """Parse one item from the current reader position.

        Reads flag bits 0-52, then Huffman code at bit 53.
        For simple items: reads socket bit, pads to byte boundary.
        For extended items: reads full extended header and type-specific data.

        All bit positions [BV] (TC01-TC10).

        Returns:
            ParsedItem with all available fields populated.
        """
        reader = self._require_reader()
        item_start_bit = reader.bit_pos
        # Instance-scoped copy so nested _parse_type_specific_data helpers can compute
        # blob-relative bit offsets (needed for quantity patch metadata, feature TC61).
        self._item_start_bit = item_start_bit

        flags = self._read_item_flags(item_start_bit)
        code = self._read_item_code(item_start_bit)

        # ── Simple item handling [BV] ────────────
        if flags.simple:
            return self._parse_simple_item_body(flags, code, item_start_bit)

        # ── Extended item header + gfx/class + automod dispatch [BV] ────
        unique_id, ilvl, quality = self._read_extended_header()
        has_gfx, gfx_index, has_class = self._read_gfx_and_class()
        automod_id, prefix_carry_from_automod = self._read_automod_dispatch(
            code=code, has_gfx=has_gfx, has_class=has_class, quality=quality,
        )
        extended = ItemExtendedHeader(
            unique_item_id=unique_id,
            item_level=ilvl,
            quality=quality,
            quality_name=QUALITY_NAMES.get(quality, f"unknown({quality})"),
            has_custom_graphics=has_gfx,
            gfx_index=gfx_index,
            has_class_specific_data=has_class,
        )

        # ── Quality-specific data + bridge fields [SPEC_ONLY/BV] ──────
        # [BINARY_VERIFIED TC24 J2] Save position before QSD so we can retry
        # with a 7-slot affix layout if the 6-slot parse fails (Reimagined
        # Rare misc items like jewels have an extra 10-bit affix slot).
        pre_qsd_pos = reader.bit_pos if quality in (6, 8) else -1
        self._qsd_rare_retry_needed = False
        qsd = self._read_quality_specific_data(quality)
        runeword_id = self._read_bridge_fields(flags)

        # ── Type-specific data + magical properties (with rare-MISC 7-slot retry)
        armor_data, magical_properties, qsd = self._parse_type_specific_with_retry(
            flags=flags, code=code, quality=quality, has_gfx=has_gfx,
            pre_qsd_pos=pre_qsd_pos, qsd=qsd, item_start_bit=item_start_bit,
        )

        # ── Byte-align after base property list [BV TC08 / BV TC24 uhn] ─
        # Non-runeword: pad to byte boundary. Runeword: the RW ISC slot
        # starts IMMEDIATELY after the base 0x1FF - NO byte-alignment.
        if not flags.runeword:
            reader.skip_to_byte_boundary()

        runeword_properties, magical_properties = self._read_runeword_property_list(
            flags=flags, code=code, magical_properties=magical_properties,
        )

        # [BV TC16/TC19] Non-bf1 misc inter-item padding handled in _parse_item_list().
        item_end_bit = self._clamp_to_section_end(reader.bit_pos, code)
        return self._assemble_parsed_item(
            code=code, flags=flags, item_start_bit=item_start_bit,
            item_end_bit=item_end_bit, extended=extended, armor_data=armor_data,
            magical_properties=magical_properties, qsd=qsd, automod_id=automod_id,
            prefix_carry_from_automod=prefix_carry_from_automod, has_gfx=has_gfx,
            has_class=has_class, quality=quality, runeword_id=runeword_id,
            runeword_properties=runeword_properties,
        )

    def _validate_rare_misc_7slot_retry(
        self,
        *,
        item_start_bit: int,
        code: str,
        quality: int,
    ) -> None:
        """Validate the outcome of a Rare-MISC 7-slot QSD retry.

        After the retry consumed QSD + type-specific data + the first
        property list, three invariants must hold. Any violation means
        the retry produced a malformed parse and the bit-reader is now
        pointing at garbage -- subsequent items would cascade-corrupt.

        Invariants:
            1. ``item_end_bit <= section_end_bit`` (no overshoot past
               the D2I / D2S section boundary).
            2. The last property terminator read was ``0x1FF`` -- this
               is pinned indirectly by checking the parser's terminator
               state (``_last_prop_terminator`` when exposed).
            3. Reader is still byte-alignable from here (sanity: the
               bit position is a valid offset within ``_reader._data``).

        Raises:
            SpecVerificationError: if any invariant fails.
        """
        reader = self._require_reader()
        item_end_bit = reader.bit_pos
        byte_offset = item_end_bit // 8
        # Invariant 1: section-boundary containment.
        if self._section_end_byte is not None:
            section_end_bit = self._section_end_byte * 8
            if item_end_bit > section_end_bit:
                raise SpecVerificationError(
                    field="rare_misc_7slot_retry",
                    byte_offset=byte_offset,
                    bit_offset=item_end_bit,
                    expected=f"item ending within section (<= bit {section_end_bit})",
                    found=f"overshoot by {item_end_bit - section_end_bit} bits",
                    context=(
                        f"item_code={code!r} quality={quality} "
                        f"item_start_bit={item_start_bit}"
                    ),
                )
        # Invariant 3: reader position is inside the data buffer.
        reader_bytes = len(getattr(reader, "_data", b""))
        if reader_bytes and byte_offset > reader_bytes:
            raise SpecVerificationError(
                field="rare_misc_7slot_retry",
                byte_offset=byte_offset,
                bit_offset=item_end_bit,
                expected=f"item ending within buffer (<= byte {reader_bytes})",
                found=f"bit offset {item_end_bit} past end-of-data",
                context=(
                    f"item_code={code!r} quality={quality} "
                    f"item_start_bit={item_start_bit}"
                ),
            )
        # Invariant 2 is enforced inside _read_property_list_with_isc
        # (the 0x1FF terminator is required for the loop to exit), so
        # reaching this point already implies the terminator was found.

    def _read_bridge_fields(self, flags: ItemFlags) -> int | None:
        """Read the bridge fields between QSD and type-specific data.

        Sequence (all present if the corresponding flag is set, in this
        fixed order):

          1. runeword_id (12 bits, runes.txt row) + 4-bit padding
             [SPEC_ONLY] when ``flags.runeword``.
          2. null-terminated personalization string [SPEC_ONLY] when
             ``flags.personalized``.
          3. Timestamp bit (1 bit) - ALWAYS present, both has_gfx=0
             and has_gfx=1. Must be read here - NOT part of gfx_extra.
             Omitting this bit shifts all type-specific fields by 1,
             causing cascading failures.
             [BINARY_VERIFIED TC40/UniqueJewel/OnlyCharm/Spirit.d2s]

        Args:
            flags: Parsed item flags.

        Returns:
            The runeword_id (runes.txt row index) if ``flags.runeword``,
            else ``None``.
        """
        reader = self._require_reader()
        runeword_id: int | None = None
        if flags.runeword:
            runeword_id = reader.read(12)  # row index into runes.txt [SPEC_ONLY]
            _rw_unknownnown_padding = reader.read(4)  # purpose unknown [BV] (always 5?)
        if flags.personalized:
            self._read_null_terminated_string()  # [SPEC_ONLY]
        # ── Timestamp bit [BINARY_VERIFIED TC40/UniqueJewel/OnlyCharm/Spirit.d2s]
        _timestamp = reader.read(1)
        return runeword_id

    def _clamp_to_section_end(self, item_end_bit: int, code: str) -> int:
        """Clamp an item's end bit to the current section boundary.

        D2I section boundary: clamp item_end_bit so that source_data
        never includes bytes from the next section's header. When the
        last item in a D2I section is a Set item, the set-bonus reader
        can overshoot into the next section's 64-byte header (starting
        with 0xAA55AA55). Without this clamp, the extra bytes get baked
        into source_data and corrupt the D2S file when the item is
        transferred from stash to character.

        Emits a warning on clamp - silently losing bytes would hide a
        genuine parser bug. Message shape matches the simple-item clamp
        so log-analysis tools can treat both uniformly.

        Args:
            item_end_bit: The raw post-parse reader bit position.
            code: Item type code, for the diagnostic log line.

        Returns:
            The clamped ``item_end_bit`` (equal to input when no clamp needed).
        """
        if self._section_end_byte is not None:
            section_end_bit = self._section_end_byte * 8
            if item_end_bit > section_end_bit:
                logger.warning(
                    "Extended item '%s' parse overshot section boundary by "
                    "%d bits (item_end=%d, section_end=%d). Clamping - "
                    "item data will be truncated. Investigate!",
                    code,
                    item_end_bit - section_end_bit,
                    item_end_bit,
                    section_end_bit,
                )
                item_end_bit = section_end_bit
        return item_end_bit

    def _assemble_parsed_item(
        self,
        *,
        code: str,
        flags: ItemFlags,
        item_start_bit: int,
        item_end_bit: int,
        extended: ItemExtendedHeader,
        armor_data: ItemArmorData | None,
        magical_properties: list[dict[str, Any]],
        qsd: dict[str, Any],
        automod_id: int | None,
        prefix_carry_from_automod: int | None,
        has_gfx: bool,
        has_class: bool,
        quality: int,
        runeword_id: int | None,
        runeword_properties: list[dict[str, Any]],
    ) -> ParsedItem:
        """Build the final ParsedItem with quality-specific ID decoding.

        [BINARY_VERIFIED SpinelFacet/DiamondFacet/UniqueJewel/EasyJewel/TC39/TC40]

        For has_gfx=0 items: QSD values are direct binary values.
          Unique/Set: use binary_to_star_id() lookup table (handles
          GoMule "Expansion skip" row indexing and Reimagined separator rows).
          Magic: raw - 1 for 0-based txt index.
          Rare: raw - 156 (prefix), raw - 1 (suffix) per GoMule namespace.

        For has_gfx=1 items: the gfx_extra(1) bit shifts the QSD bit
        stream by 1 position. The raw QSD values contain carry-chain
        artifacts from this shift. Compensation formulas:
          Unique: *ID = binary_to_star_id(uid_12 * 2 + has_class)
          Set:    *ID = set_id_12 * 2 + has_class
          Magic prefix: (has_class | (raw_prefix & 0x3FF) << 1) - 1
          Magic suffix: (raw_prefix >> 10 | (raw_suffix & 0x3FF) << 1) - 1
          Rare name_id1: (has_class | (raw_id1 & 0x7F) << 1) - 156
          Rare name_id2: (raw_id1 >> 7 | (raw_id2 & 0x7F) << 1) - 1

        For Unique items: the carry-chain value is a RAW binary index
        that still needs Expansion-separator-row correction via
        binary_to_star_id(). The old "-2" was a fixed approximation
        that failed for IDs below the separator rows. [BV]

        Args:
            code: Item type code.
            flags: Parsed flag block.
            item_start_bit: Absolute bit start for source_data slicing.
            item_end_bit: Absolute bit end (clamped to section).
            extended: The ItemExtendedHeader.
            armor_data: Armor-specific block, if any.
            magical_properties: Base property list.
            qsd: Quality-specific-data dict (may be from 6- or 7-slot retry).
            automod_id: Automagic row index or ``None``.
            prefix_carry_from_automod: The split carry bit from the
                has_gfx=1 automod MSB; falls back to ``has_class`` when
                ``None``.
            has_gfx: Custom-graphics flag - gates the carry-chain branches.
            has_class: Class-info flag - default carry when automod wasn't read.
            quality: Extended-header quality code.
            runeword_id: runes.txt row, if this is a runeword.
            runeword_properties: Display props of the RW ISC slot.

        Returns:
            Fully populated ``ParsedItem``.
        """
        return ParsedItem(
            item_code=code,
            flags=flags,
            source_data=self._extract_item_bytes(item_start_bit, item_end_bit),
            extended=extended,
            armor_data=armor_data,
            magical_properties=magical_properties,
            set_bonus_properties=self._current_set_bonus_properties,
            # _misc_qty is initialized to 0 in _reset_item_state; the `| None`
            # annotation is defensive. ParsedItem.quantity is non-optional int
            # (default 0), so coalesce here at the model boundary.
            quantity=self._misc_qty or 0,
            quantity_bit_offset=self._misc_qty_bit_offset,
            quantity_bit_width=(7 if self._misc_qty_bit_offset is not None else 0),
            total_nr_of_sockets=self._total_nr_of_sockets,
            automod_id=automod_id,
            superior_type=qsd.get("superior_type"),
            set_bonus_mask=self._set_bonus_mask if (extended and extended.quality == 5) else 0,
            # ── Quality-specific ID decoding ──────────────────────
            # [BINARY_VERIFIED SpinelFacet/DiamondFacet/UniqueJewel/EasyJewel/TC39/TC40]
            # (see method docstring for the carry-chain formulas.)
            # [BV]
            unique_type_id=(
                get_item_names_db().unique_binary_to_star_id(
                    qsd["unique_type_id"] * 2
                    + (
                        prefix_carry_from_automod
                        if prefix_carry_from_automod is not None
                        else (1 if has_class else 0)
                    )
                )
                if quality == 7 and has_gfx and "unique_type_id" in qsd
                else (
                    get_item_names_db().unique_binary_to_star_id(qsd["unique_type_id"])
                    if quality == 7 and "unique_type_id" in qsd
                    else qsd.get("unique_type_id")
                )
            ),
            set_item_id=(
                qsd["set_item_id"] * 2
                + (
                    prefix_carry_from_automod
                    if prefix_carry_from_automod is not None
                    else (1 if has_class else 0)
                )
                if quality == 5 and has_gfx and "set_item_id" in qsd
                else (
                    get_item_names_db().set_binary_to_star_id(qsd["set_item_id"])
                    if quality == 5 and "set_item_id" in qsd
                    else qsd.get("set_item_id")
                )
            ),
            # Magic (q=4) affix IDs: carry-chain for has_gfx=1.
            # ``prefix_carry`` is the LSB that the encoder split off the
            # real 12-bit prefix index into the preceding field.  When
            # automod(11) was read the MSB of that read is the carry
            # (recovered above as ``prefix_carry_from_automod``); when
            # automod wasn't read the carry falls back to ``has_class``
            # (the last bit right before the prefix field in the stream).
            # [BV VikingBarbie.d2s Coral Grand Charm of Balance].
            prefix_id=(
                max(
                    0,
                    (
                        (
                            prefix_carry_from_automod
                            if prefix_carry_from_automod is not None
                            else (1 if has_class else 0)
                        )
                        | ((qsd["prefix_id"] & 0x3FF) << 1)
                    )
                    - 1,
                )
                if quality == 4 and has_gfx and "prefix_id" in qsd
                else (
                    qsd["prefix_id"] - 1
                    if quality == 4 and "prefix_id" in qsd
                    else qsd.get("prefix_id")
                )
            ),
            suffix_id=(
                max(0, ((qsd["prefix_id"] >> 10) | ((qsd["suffix_id"] & 0x3FF) << 1)) - 1)
                if quality == 4 and has_gfx and "prefix_id" in qsd and "suffix_id" in qsd
                else (
                    qsd["suffix_id"] - 1
                    if quality == 4 and "suffix_id" in qsd
                    else qsd.get("suffix_id")
                )
            ),
            # Rare/Crafted (q=6/8) name IDs with carry-chain for has_gfx=1.
            rare_name_id1=(
                qsd["rare_name_id1"]
                if qsd.get("_rare_ids_already_decoded")
                else (
                    (
                        (
                            (
                                prefix_carry_from_automod
                                if prefix_carry_from_automod is not None
                                else (1 if has_class else 0)
                            )
                            | ((qsd["rare_name_id1"] & 0x7F) << 1)
                        )
                        - 156
                    )
                    if "rare_name_id1" in qsd and qsd["rare_name_id1"] is not None and has_gfx
                    else (
                        qsd["rare_name_id1"] - 156
                        if "rare_name_id1" in qsd and qsd["rare_name_id1"] is not None
                        else None
                    )
                )
            ),
            rare_name_id2=(
                qsd["rare_name_id2"]
                if qsd.get("_rare_ids_already_decoded")
                else (
                    ((qsd["rare_name_id1"] >> 7) | ((qsd["rare_name_id2"] & 0x7F) << 1)) - 1
                    if "rare_name_id1" in qsd
                    and "rare_name_id2" in qsd
                    and qsd["rare_name_id1"] is not None
                    and qsd["rare_name_id2"] is not None
                    and has_gfx
                    else (
                        qsd["rare_name_id2"] - 1
                        if "rare_name_id2" in qsd and qsd["rare_name_id2"] is not None
                        else None
                    )
                )
            ),
            rare_affix_ids=[aid - 1 for aid in qsd.get("rare_affix_ids", [])],
            rare_affix_slots=list(qsd.get("rare_affix_slots", [])),
            runeword_id=runeword_id,
            runeword_properties=runeword_properties,
        )

    def _read_runeword_property_list(
        self,
        *,
        flags: ItemFlags,
        code: str,
        magical_properties: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Read the runeword second-property list (RW ISC slot).

        [BINARY_VERIFIED TC24/TC38/TC39/TC56] Runeword items normally
        have TWO 0x1FF-terminated property lists:
          1. Base magical properties -> 0x1FF
          2. RW ISC slot: [internal state] + [display props] -> 0x1FF

        EXCEPTION: Superior (quality=3) runeword items have NO separate
        base-props 0x1FF. The game merges everything into a single list:
          [RW ISC stats including stat 386] -> 0x1FF
        The Superior modifier (+N% max durability) is implicit from the
        superiority_type field, not stored as an explicit stat.
        [BINARY_VERIFIED TC56 VikingBarbie: Superior Spirit Monarch,
         quality=3, stat 386 appears as first stat at bit 208, single
         0x1FF at bit 344, no preceding base-props terminator.]

        Detection: if _read_magical_properties already consumed stat 386
        (stacked_gem, the RW internal state marker), the base property
        list IS the RW ISC slot. Extract display props from it directly
        instead of scanning for a non-existent second 0x1FF.

        No-op for non-runeword items (returns ``([], magical_properties)``).

        Args:
            flags: Parsed item flags (``flags.runeword`` gates the whole path).
            code: Item type code, for diagnostic logging.
            magical_properties: Base-props list, possibly containing the
                stat-386 marker for single-list runewords.

        Returns:
            Tuple ``(runeword_properties, magical_properties)`` - the
            latter may be emptied when the base list is reclassified as
            the RW ISC slot.
        """
        reader = self._require_reader()
        _STAT_STACKED_GEM = 386
        runeword_properties: list[dict[str, Any]] = []
        if flags.runeword:
            base_has_rw_marker = any(p["stat_id"] == _STAT_STACKED_GEM for p in magical_properties)

            if base_has_rw_marker:
                # ── Single-list runeword (Superior or similar) ──
                # The base property list already contains the RW ISC stats.
                # Split: stat 386 = internal state, rest = display properties.
                runeword_properties = [
                    p for p in magical_properties if p["stat_id"] != _STAT_STACKED_GEM
                ]
                # Clear base props since they are RW-owned, not base-item.
                magical_properties = []
                logger.info(
                    "Runeword '%s': single-list format (stat 386 in base props). "
                    "%d display props extracted.",
                    code,
                    len(runeword_properties),
                )
                # Reader is already past the 0x1FF - byte-align and continue.
                rw_term_pos_mod = reader.bit_pos % 8
                reader.skip_to_byte_boundary()
                if rw_term_pos_mod == 0:
                    reader.read(8)
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(
                            "Runeword '%s': byte-aligned single RW term -> skipped 8 extra null bits",
                            code,
                        )
            else:
                # ── Two-list runeword (Normal, Crafted, etc.) ──
                # Read the RW ISC slot as a regular property list.
                # _read_magical_properties handles engine-internal stats
                # (unknown IDs) gracefully and stops at 0x1FF correctly -
                # unlike _bit_scan_for_terminator which scans bit-by-bit
                # and can mistake stat VALUES of 0x1FF (e.g. +511% ED in
                # a 9-bit save_bits field) for the terminator.
                # [BV FrozenOrbHydra Infinity: stat 17 value=511=0x1FF
                #  caused _bit_scan_for_terminator to find false terminator]
                pos_before_rw = reader.bit_pos  # noqa: F841 - retained for parity
                rw_all_props = self._read_magical_properties()
                scan_end_pos = reader.bit_pos

                # Split internal state (unknown/engine stats were consumed
                # by the scan) from display properties (known ISC stats).
                # Display props are all properties that were successfully
                # decoded (everything in rw_all_props).
                runeword_properties = rw_all_props

                rw_term_pos_mod = scan_end_pos % 8
                reader.skip_to_byte_boundary()
                if rw_term_pos_mod == 0:
                    # Terminator was already byte-aligned: 8 null padding bits follow
                    reader.read(8)
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(
                            "Runeword '%s': byte-aligned RW term -> skipped 8 extra null bits", code
                        )
        return runeword_properties, magical_properties

    def _parse_type_specific_with_retry(
        self,
        *,
        flags: ItemFlags,
        code: str,
        quality: int,
        has_gfx: bool,
        pre_qsd_pos: int,
        qsd: dict[str, Any],
        item_start_bit: int,
    ) -> tuple[ItemArmorData | None, list[dict[str, Any]], dict[str, Any]]:
        """Run _parse_type_specific_data with Reimagined 7-slot QSD retry.

        Uses ItemTypeDatabase to determine armor/weapon/misc. For armor:
        reads defense+durability, then properties to 0x1FF. For
        weapon/misc/unknown: reads type fields, then properties to 0x1FF.

        [BINARY_VERIFIED TC24/TC40] Reimagined Rare MISC items may have
        a 7th affix slot (extra 1+opt10 bits in QSD). Retry triggered by:

        1. Unknown stat during property parsing (TC24 fix).
        2. has_gfx=1: gfx_extra carry-chain shifts affix slots.
        3. NEW (initial_6303.d2i item 25 'rin'): the initial 6-slot parse
           misaligns the bit cursor for has_gfx=1 rare MISC items, which
           can produce EITHER "Unknown stat_id" (setting the retry flag)
           OR an outright exception before the retry flag is set. Both
           paths must reach the retry block - otherwise recovery skips
           bytes and drops the item. See below for the try/except.

        Post-retry invariants: after the 7-slot retry consumes QSD +
        type-specific data + the first property list, validate the
        outcome via :meth:`_validate_rare_misc_7slot_retry`. Without this,
        a malformed retry silently returns a bad ParsedItem and the
        parser drifts through every subsequent item in the section.

        Args:
            flags: Parsed item flags (controls runeword/personalized
                bridge-field re-reads after the retry seek).
            code: Item type code.
            quality: Extended-header quality (retry only fires for 6/8).
            has_gfx: Custom-graphics flag (adjusts retry seek by -1 bit).
            pre_qsd_pos: Reader bit position saved just before the initial
                QSD read - used as the rewind point. ``-1`` disables retry.
            qsd: QSD dict from the initial 6-slot read. Replaced on retry.
            item_start_bit: Absolute bit start for the post-retry validator.

        Returns:
            Tuple ``(armor_data, magical_properties, qsd)``.
        """
        reader = self._require_reader()
        db = get_item_type_db()
        self._current_item_properties: list[dict[str, Any]] = []
        self._current_set_bonus_properties: list[dict[str, Any]] = []
        self._set_bonus_mask = 0
        self._total_nr_of_sockets = 0
        self._misc_qty = 0
        self._misc_qty_bit_offset: int | None = None  # blob-relative, set if 7-bit tail present
        # [BINARY_VERIFIED TC24/TC40] Reimagined Rare MISC items may have a
        # 7th affix slot (extra 1+opt10 bits in QSD). Retry triggered by:
        # 1. Unknown stat during property parsing (TC24 fix)
        # 2. has_gfx=1: gfx_extra carry-chain shifts affix slots
        # 3. NEW (initial_6303.d2i item 25 'rin'): the initial 6-slot parse
        #    misaligns the bit cursor for has_gfx=1 rare MISC items, which
        #    can produce EITHER "Unknown stat_id" (setting the retry flag)
        #    OR an outright exception before the retry flag is set. Both
        #    paths must reach the retry block - otherwise recovery skips
        #    bytes and drops the item. See below for the try/except.
        _force_retry = (
            has_gfx
            and quality in (6, 8)
            and db.classify(code) == ItemCategory.MISC
            and not db.is_stackable(code)
            and pre_qsd_pos >= 0
        )

        # Snapshot reader state so we can rewind on exception without
        # bubbling up a misleading failure.
        _snapshot_bit = reader.bit_pos  # noqa: F841 - retained for parity with original body
        _initial_parse_exception: Exception | None = None
        try:
            armor_data = self._parse_type_specific_data(
                code, flags.socketed, quality, flags.runeword
            )
            magical_properties = self._current_item_properties
        except Exception as _exc:
            # On a retry-eligible item we can recover by running the 7-slot
            # QSD path. For non-eligible items, re-raise to preserve the
            # original diagnostic.
            if not _force_retry:
                raise
            _initial_parse_exception = _exc
            armor_data = None
            magical_properties = []
            self._current_item_properties = []
            self._qsd_rare_retry_needed = True  # guarantee retry below
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "Rare misc '%s': initial 6-slot parse raised %s - triggering 7-slot QSD retry.",
                    code,
                    _exc,
                )

        if (
            (self._qsd_rare_retry_needed or _force_retry)
            and quality in (6, 8)
            and pre_qsd_pos >= 0
            and db.classify(code) == ItemCategory.MISC
            and not db.is_stackable(code)
        ):
            retry_pos = pre_qsd_pos - 1 if has_gfx else pre_qsd_pos
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "Rare misc '%s': retrying 7-slot QSD from bit %d (has_gfx=%s)",
                    code,
                    retry_pos,
                    has_gfx,
                )
            reader.seek_bit(retry_pos)
            self._qsd_rare_retry_needed = False
            # 7-slot layout: 8+8 name IDs, 6*(1+opt 11-bit ID), 1*(1+opt 10-bit ID)
            # Capture IDs for name look-up (overwrites qsd from the failed 6-slot attempt).
            # For has_gfx=1 retry, the seek position is 1 bit earlier (gfx_extra absorbed),
            # so the read values are ALREADY shifted - apply GoMule offsets directly
            # instead of letting the carry-chain formula in ParsedItem creation run.
            qsd = {}
            raw_id1 = reader.read(8)
            raw_id2 = reader.read(8)
            if has_gfx:
                # Retry from shifted position: values already compensated.
                qsd["rare_name_id1"] = raw_id1 - 156
                qsd["rare_name_id2"] = raw_id2 - 1
                qsd["_rare_ids_already_decoded"] = True
            else:
                qsd["rare_name_id1"] = raw_id1
                qsd["rare_name_id2"] = raw_id2
            retry_affix_ids: list[int] = []
            retry_affix_slots: list[int] = []
            for slot in range(6):  # slots 0-5: standard 11-bit affix IDs
                if reader.read(1):
                    retry_affix_ids.append(reader.read(11))
                    retry_affix_slots.append(slot)
            if reader.read(1):  # slot 6: 10-bit affix ID [BV]
                retry_affix_ids.append(reader.read(10))
                retry_affix_slots.append(6)
            qsd["rare_affix_ids"] = retry_affix_ids
            qsd["rare_affix_slots"] = retry_affix_slots
            # Re-read the fields that appear between QSD and type-specific data
            if flags.runeword:
                reader.read(12)  # rw_str_index (already captured above)
                reader.read(4)  # rw_unknownnown
            if flags.personalized:
                self._read_null_terminated_string()
            reader.read(1)  # timestamp bit (always present)
            # Re-run type-specific parse so misc quantity fields (jewel
            # quality bits etc.) and the property list start from the
            # correct position.  If this ALSO fails, surface the error
            # so upstream recovery (byte-skip scan) can kick in rather
            # than silently returning a partial/wrong item.
            try:
                armor_data = self._parse_type_specific_data(
                    code,
                    flags.socketed,
                    quality,
                    flags.runeword,
                )
                magical_properties = self._current_item_properties
            except Exception as _retry_exc:
                if _initial_parse_exception is not None:
                    # Prefer the original diagnostic - it points to the
                    # real bit position where things went wrong.
                    raise _initial_parse_exception
                raise _retry_exc

            # ── Post-retry invariants ─────────────────────────────
            # After the 7-slot retry consumes QSD + type-specific data +
            # the first property list, validate the outcome. Without
            # these checks, a malformed retry silently returns a bad
            # ParsedItem and the parser drifts through every subsequent
            # item in the section.
            self._validate_rare_misc_7slot_retry(
                item_start_bit=item_start_bit,
                code=code,
                quality=quality,
            )

        return armor_data, magical_properties, qsd

    def _parse_simple_item_body(
        self,
        flags: ItemFlags,
        code: str,
        item_start_bit: int,
    ) -> ParsedItem:
        """Parse the body of a simple (non-extended) item.

        Simple items have a fixed bit layout after the Huffman code:
        1 socket-count bit, optional 9-bit quantity for stackables,
        then byte-alignment padding. No extended header, no QSD, no
        property lists.

        Preserves all binary-verification tags from the inline
        implementation (TC07, TC11/TC61/TC62).

        Args:
            flags: Item flag bits 0-52 (already read).
            code: Huffman-decoded item type code.
            item_start_bit: Absolute bit position of the item start, used
                for section-boundary clamping and blob-relative offsets.

        Returns:
            Fully populated ``ParsedItem`` for the simple item.
        """
        reader = self._require_reader()
        # Read 1 unknown bit [BINARY_VERIFIED TC07]
        _socket_count_bit = reader.read(SIMPLE_ITEM_SOCKET_BIT_WIDTH)
        # [BINARY_VERIFIED TC11/TC61/TC62] Stackable items have a 9-bit quantity field.
        # Bit 0 is an alignment/flag bit (always 1 in D2R v105) - NOT part of
        # the display value. The upper 8 bits (bits 1-8) carry the display count.
        # Raw value ~ 2*display + 1. Use ParsedItem.display_quantity for the
        # user-visible count. The writer preserves the existing bit 0 via
        # _display_to_raw_quantity().
        _quantity = 0
        _qty_bit_offset: int | None = None
        _qty_bit_width = 0
        if get_item_type_db().is_quantity_item(code):
            # Remember the blob-relative bit offset before reading so the writer
            # can patch the quantity in-place. [BV]
            _qty_bit_offset = reader.bit_pos - item_start_bit
            _qty_bit_width = 9
            _quantity = reader.read(9)
        reader.skip_to_byte_boundary()
        item_end_bit = reader.bit_pos
        # Clamp to section boundary (same as extended item path)
        if self._section_end_byte is not None:
            section_end_bit = self._section_end_byte * 8
            if item_end_bit > section_end_bit:
                # Simple items overshooting the section boundary is
                # a parser bug - simple items have fixed-layout bits
                # and should not overshoot. Warn loudly if seen.
                logger.warning(
                    "Simple item '%s' parse overshot section boundary by "
                    "%d bits (item_end=%d, section_end=%d). Clamping - "
                    "this may truncate the item. Investigate!",
                    code,
                    item_end_bit - section_end_bit,
                    item_end_bit,
                    section_end_bit,
                )
                item_end_bit = section_end_bit
        return ParsedItem(
            item_code=code,
            flags=flags,
            quantity=_quantity,
            quantity_bit_offset=_qty_bit_offset,
            quantity_bit_width=_qty_bit_width,
            source_data=self._extract_item_bytes(item_start_bit, item_end_bit),
        )

    def _extract_item_bytes(self, start_bit: int, end_bit: int) -> bytes:
        """Extract the raw bytes of an item from the source data.

        The item occupies bits [start_bit, end_bit). This includes any
        byte-alignment padding at the end.  The extraction is byte-aligned
        (full bytes from the start byte to the end byte).
        """
        reader = self._require_reader()
        start_byte = start_bit // 8
        end_byte = (end_bit + 7) // 8  # round up
        return bytes(reader._data[start_byte:end_byte])

    def _read_item_flags(self, item_start_bit: int) -> ItemFlags:
        """Read item flag bits 0-52.

        All bit positions [BV] (TC01-TC10).

        Args:
            item_start_bit: Absolute bit position of the item start.

        Returns:
            ItemFlags with all fields populated.
        """
        reader = self._require_reader()
        r = reader
        s = item_start_bit  # alias for brevity

        return ItemFlags(
            identified=bool(r._read_bits_at(s + ITEM_BIT_IDENTIFIED, 1)),
            socketed=bool(r._read_bits_at(s + ITEM_BIT_SOCKETED, 1)),
            starter_item=bool(r._read_bits_at(s + ITEM_BIT_STARTER_ITEM, 1)),
            simple=bool(r._read_bits_at(s + ITEM_BIT_SIMPLE, 1)),
            ethereal=bool(r._read_bits_at(s + ITEM_BIT_ETHEREAL, 1)),
            personalized=bool(r._read_bits_at(s + ITEM_BIT_PERSONALIZED, 1)),
            runeword=bool(r._read_bits_at(s + ITEM_BIT_RUNEWORD, 1)),
            location_id=r._read_bits_at(s + ITEM_BIT_LOCATION_ID, 3),
            equipped_slot=r._read_bits_at(s + ITEM_BIT_EQUIPPED_SLOT, 4),
            position_x=r._read_bits_at(s + ITEM_BIT_POSITION_X, 4),
            position_y=r._read_bits_at(s + ITEM_BIT_POSITION_Y, 4),
            panel_id=r._read_bits_at(s + ITEM_BIT_PANEL_ID, 3),
        )

    def _read_automod_dispatch(
        self,
        *,
        code: str,
        has_gfx: bool,
        has_class: bool,
        quality: int,
    ) -> tuple[int | None, int | None]:
        """Dispatch the 11-bit automod (class_data) read per item type.

        The 11-bit automod field (index into automagic.txt) is present
        only for items that have the "auto prefix" flag set in armor.txt/
        weapons.txt/misc.txt. The reading depends on the bf1 flag:

          bf1=True items (armor, weapons, rings, amulets, jewels):
            Read 11 bits ONLY when has_class=1. [BV]

          bf1=False items (charms, tools, orbs):
            ALWAYS read 11 bits, UNLESS quality=7 (Unique).
            The engine always writes automod for bf1=False items even
            when has_class=0 - the flag just indicates whether the
            automod is "active" (visible), not whether it's present.
            [BV]

          Items WITHOUT has_auto_prefix (jewels, rings, amulets when
          has_auto_prefix is false in the txt file):
            NEVER read automod. The has_class bit flows into the
            carry-chain instead, shifting QSD field boundaries.
            [BV UniqueJewel.d2s (hc=1, no automod -> uid carry-chain)]
            [BV]

        Carry-bit that flows INTO the prefix_id read for has_gfx=1
        magic items.  By default it's has_class (stream position is
        just before prefix for jewels / rings / amulets where automod
        isn't read).  When automod IS read (charms / tools / orbs /
        bf1=True weapons+armor with auto-prefix slot), the 11-bit
        automod field actually stores [10-bit automod, 1-bit carry
        for prefix] - the carry bit sits in automod's MSB and
        everything below is the real automod ID.

        This was empirically verified against VikingBarbie + Charms +
        Laktana live saves: automagic.txt only has 71 rows, yet the
        parser was reading values like 1046/1047 (= 22/23 + 0x400).
        Masking to 10 bits recovers the real "Shimmering" / "Rainbow"
        automods, and the salvaged MSB bit matches the LSB needed to
        disambiguate adjacent prefix rows (e.g. Coral=1003 vs
        Amber=1004 for the "Coral Grand Charm of Balance" bug).

        Args:
            code: Item type code (for the item-type database lookups).
            has_gfx: Graphics flag - enables carry-chain mask extraction.
            has_class: Class-info flag - gates the bf1=True read.
            quality: Extended-header quality (0-15).

        Returns:
            Tuple ``(automod_id, prefix_carry_from_automod)``. Either or
            both may be ``None`` when no read fires.
        """
        reader = self._require_reader()
        db = get_item_type_db()
        automod_id: int | None = None
        prefix_carry_from_automod: int | None = None
        if db.has_auto_prefix(code):
            if db.has_bitfield1(code):
                if has_class:
                    automod_id = reader.read(11)
                    if has_gfx:
                        prefix_carry_from_automod = (automod_id >> 10) & 1
                        automod_id = automod_id & 0x3FF
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug("Automod ID: %d (11 bits, bf1=True)", automod_id)
            else:
                if quality != 7:
                    automod_id = reader.read(11)
                    if has_gfx:
                        prefix_carry_from_automod = (automod_id >> 10) & 1
                        automod_id = automod_id & 0x3FF
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug("Automod ID: %d (11 bits, bf1=False always)", automod_id)
        elif (
            db.has_bitfield1(code)
            and db.classify(code) in (ItemCategory.WEAPON, ItemCategory.ARMOR)
            and has_class
        ):
            # [BV] Crystal Sword (crs) and a handful of base
            # armor types (cap, hlm, skp, stu, brs, lbl, vgl, vbt, ...) have an
            # empty "auto prefix" field in weapons.txt / armor.txt, yet the
            # 11-bit automod slot is still present in the binary whenever
            # has_class=1. The auto-prefix flag controls whether the game
            # auto-rolls an automod on creation - the slot itself always
            # exists for bf1=True weapons and armor. Without this branch the
            # parser reads the durability 11 bits too early, producing
            # impossible values (e.g. max_dur=131/cur_dur=209 instead of
            # 250/200) and a 1-socket count instead of the real 6 for
            # Knurpsi's crs.
            automod_id = reader.read(11)
            if has_gfx:
                prefix_carry_from_automod = (automod_id >> 10) & 1
                automod_id = automod_id & 0x3FF
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "Automod ID: %d (11 bits, weapon/armor hc=1 no auto_prefix)", automod_id
                )
        return automod_id, prefix_carry_from_automod

    def _read_gfx_and_class(self) -> tuple[bool, int, bool]:
        """Read the graphics + class-info block from the extended header.

        Layout: has_gfx(1) -> [if 1: gfx_index(3) + gfx_extra(1)]
                -> has_class(1) -> [automod(11) per rules below]

        [BINARY_VERIFIED EasyJewel/UniqueJewel/OnlyCharm/AllThree/
         Spirit/OrnatePlate/SetSocket/BigStats/MrLockhart.d2s]

        The gfx_extra(1) bit creates a CARRY-CHAIN effect: it shifts
        the interpretation of all subsequent QSD fields by 1 bit.
        Quality-specific formulas compensate for this shift (see
        ParsedItem creation below for Unique/Set/Magic/Rare formulas).

        Automod (class_data) 11-bit reading rules:
          Items WITH has_auto_prefix (armor, weapons, charms, orbs):
            bf1=True:  read ONLY when has_class=1
            bf1=False: ALWAYS read (except Unique quality q=7)
          Items WITHOUT has_auto_prefix (jewels, rings, amulets):
            NEVER read - has_class flows into the carry-chain instead

        Returns:
            Tuple ``(has_gfx, gfx_index, has_class)``. ``gfx_extra`` is
            consumed from the bit stream when ``has_gfx=True`` but not
            returned - no downstream caller reads it, only its side
            effect on reader position matters.
        """
        reader = self._require_reader()
        has_gfx = bool(reader.read(1))
        gfx_index = 0
        gfx_extra = 0  # noqa: F841 - read for reader advance; carry-chain side-effect is semantic
        if has_gfx:
            gfx_index = reader.read(3)  # graphic variant index (0-7)
            gfx_extra = reader.read(1)  # carry-chain bit [BV EasyJewel/UniqueJewel]  # noqa: F841

        has_class = bool(reader.read(1))
        return has_gfx, gfx_index, has_class

    def _read_extended_header(self) -> tuple[int, int, int]:
        """Read the three fixed-width extended-header fields.

        Reads unique_item_id (35 bits), item_level (7 bits), and
        quality (4 bits) from the current reader position. All widths
        are [BV].

        Returns:
            Tuple ``(unique_id, ilvl, quality)``.
        """
        reader = self._require_reader()
        unique_id = reader.read(EXT_WIDTH_UNIQUE_ID)  # 35 bits [BV]
        ilvl = reader.read(EXT_WIDTH_ILVL)  # 7 bits  [BV]
        quality = reader.read(EXT_WIDTH_QUALITY)  # 4 bits  [BV]
        return unique_id, ilvl, quality

    def _read_item_code(self, item_start_bit: int) -> str:
        """Seek to the Huffman start and decode the item type code.

        Huffman code starts at item-relative bit 53 [BV]. Returns the
        decoded item code (e.g. ``"ring"``, ``"crs"``). All bit
        positions [BV] (TC01-TC10).

        Args:
            item_start_bit: Absolute bit position of the item start.

        Returns:
            The decoded item code string.
        """
        reader = self._require_reader()
        # ── Seek to Huffman start [BV] ──────────
        # Huffman code starts at item-relative bit 53 [BV]
        reader.seek_bit(item_start_bit + ITEM_BIT_HUFFMAN_START)

        # ── Huffman item code [BV] ───────────────
        code, huffman_bits = decode_item_code(reader)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Item code: '%s' (%d bits)", code, huffman_bits)
        return code

    # Per-quality reader functions (dispatch table). Each
    # reads the quality-specific bits and returns a dict of name IDs
    # the formatter and set/unique/rare lookups consume. Kept as
    # bound methods so they can share ``reader`` without
    # threading it through every call - this is a pure refactor,
    # the bit layout is unchanged.

    def _read_qsd_low(self) -> dict[str, Any]:
        """Low Quality (q=1) - 3 bits (low_quality_type). [SPEC_ONLY]"""
        reader = self._require_reader()
        return {"low_quality_type": reader.read(3)}

    def _read_qsd_normal(self) -> dict[str, Any]:
        """Normal (q=2) - no extra bits at the QSD layer.

        [BINARY_VERIFIED TC08/TC09/TC10] covers the armor / weapon paths.
        Alternate implementations treat rune codes matching
        ``/^[rs]\\d{2}$/`` as a +1-bit QSD case, but in this parser the
        matching bit is consumed one step later by
        ``_parse_type_specific_data`` via the MISC branch:

          - non-stackable runes (r##): the 1-bit
            ``_unknown_misc_normal_prefix`` [BINARY_VERIFIED TC16/TC19]
          - stackable runes (s##, Reimagined Rune Stack): the scan-forward
            ``_read_quantity_before_terminator`` is self-aligning and
            absorbs the bit implicitly [BINARY_VERIFIED TC67/TC69,
            game-written ground truth, stacked-rune qty=4 and qty=7
            recovered byte-exact]
        """
        return {}

    def _read_qsd_superior(self) -> dict[str, Any]:
        """Superior (q=3) - 3 bits (superior_type). [BINARY_VERIFIED TC02/TC11]"""
        reader = self._require_reader()
        return {"superior_type": reader.read(3)}

    def _read_qsd_magic(self) -> dict[str, Any]:
        """Magic (q=4) - 11+11 bits (prefix_id + suffix_id). [BINARY_VERIFIED TC02]"""
        reader = self._require_reader()
        return {
            "prefix_id": reader.read(11),  # 0 = no prefix
            "suffix_id": reader.read(11),  # 0 = no suffix
        }

    def _read_qsd_set(self) -> dict[str, Any]:
        """Set (q=5) - 12 bits (set_item_id). [BINARY_VERIFIED TC02]"""
        reader = self._require_reader()
        return {"set_item_id": reader.read(12)}

    def _read_qsd_unique(self) -> dict[str, Any]:
        """Unique (q=7) - 12 bits (unique_type_id). [BINARY_VERIFIED TC02]"""
        reader = self._require_reader()
        return {"unique_type_id": reader.read(12)}

    def _read_qsd_rare_or_crafted(self) -> dict[str, Any]:
        """Rare (q=6) and Crafted (q=8) share the same reader:
        8+8 name IDs + 6*(1+opt 11) affix slots. [BINARY_VERIFIED TC02]

        The Reimagined 7th-slot extension fires later in
        _parse_single_item via the retry path (see
        project_rare_misc_7slot_qsd.md).
        """
        reader = self._require_reader()
        name_id1 = reader.read(8)  # first rare name part
        name_id2 = reader.read(8)  # second rare name part
        affix_ids: list[int] = []
        affix_slots: list[int] = []
        # Six fixed slots: slot N uses magicprefix.txt when N is even,
        # magicsuffix.txt when N is odd. Empty slots are skipped in the
        # output list, so we track the slot position explicitly.
        for slot in range(6):
            if reader.read(1):
                affix_ids.append(reader.read(11))
                affix_slots.append(slot)
        return {
            "rare_name_id1": name_id1,
            "rare_name_id2": name_id2,
            "rare_affix_ids": affix_ids,
            "rare_affix_slots": affix_slots,
        }

    def _read_quality_specific_data(self, quality: int) -> dict[str, Any]:
        """Read quality-specific extra bits via the dispatch table.

        Delegates to per-quality readers keyed by the 4-bit quality
        value. Unknown qualities return an empty dict (zero bits
        read) - matches the pre-refactor behaviour.

        Returns a dict with the quality-specific IDs for name look-up:
          quality=4 (Magic):       {'prefix_id': int, 'suffix_id': int}
          quality=5 (Set):         {'set_item_id': int}
          quality=6/8 (Rare/Crafted): {'rare_name_id1': int,
                                       'rare_name_id2': int,
                                       'rare_affix_ids': list[int],
                                       'rare_affix_slots': list[int]}
          quality=7 (Unique):      {'unique_type_id': int}
          quality=1 (Low):         {'low_quality_type': int}
          quality=3 (Superior):    {'superior_type': int}
          quality=2 (Normal):      {}

        Args:
            quality: The 4-bit quality value.

        Returns:
            dict with quality-specific IDs (may be empty for Normal).
        """
        self._require_reader()  # guard only - dispatched reader uses self._reader
        reader_fn = _QUALITY_READERS.get(quality)
        if reader_fn is None:
            return {}
        result: dict[str, Any] = reader_fn(self)
        return result

    def _parse_type_specific_data(
        self, item_code: str, socketed: bool = False, quality: int = 0, runeword: bool = False
    ) -> ItemArmorData | None:
        """Read type-specific item fields based on item category.

        ## Binary Layout Summary (all [BV])

        **ARMOR** (armor.txt items):
          defense(11) + dur(8+8) + unknown(2) + [shield_unknown(2) if shield+socketed]
          + [sock_unknown(4/20/22) if socketed, width depends on quality+RW flag]
          + [set_mask(5) if set quality]
          + ISC_properties + 0x1FF + [set_bonus_lists]
          + [RW_ISC_properties + 0x1FF if runeword] [BINARY_VERIFIED TC24]

        **MELEE WEAPON** (weapons.txt, stackable=0):
          dur(8+8) + unknown(2)
          - Normal quality: [sock_unknown(4) if socketed] + constant(24) + 0x1FF
          - Other qualities: ISC_properties + 0x1FF

        **THROWING WEAPON** (weapons.txt, stackable=1):
          dur(8+8) + unknown(2) + qty(9) + [sock_unknown(4) if socketed]
          + ISC_properties + 0x1FF  (ALL quality levels have ISC properties)

        **MISC** (misc.txt items):
          Varies by stackable/quality - see inline comments.

        ## ISC Property Encoding
          - Encode 0: stat_id(9) + [param(save_param_bits)] + value(save_bits)
          - Encode 1: stat_id(9) + [param(save_param_bits)] + value(save_bits)
                      If save_param_bits==0: paired stat(id+1) value follows
          - Encode 2: stat_id(9) + param(save_param_bits) -> contains level(6)+skill(10)
                      Then value(save_bits) = chance
          - Encode 3: stat_id(9) + param(save_param_bits) -> contains level(6)+skill(10)
                      Then max_charges(8) + charges(8)
          - Encode 4: stat_id(9) + extra(save_bits or 14 if save_bits==0)
          - Hardcoded pairs: 17->18, 48->49, 50->51, 52->53, 54->55->56, 57->58->59

        Uses ItemTypeDatabase to determine whether the item is an armor,
        weapon, or misc item - then reads the appropriate fields.

        [BV] for Armor.txt items (TC08/TC10).
        [SPEC_ONLY] for weapon items.
        [SPEC_ONLY] for misc items.

        Args:
            item_code: Decoded item type code.

        Returns:
            ItemArmorData for armor items, None for weapons/misc/unknown.
        """
        reader = self._require_reader()
        db = get_item_type_db()
        category = db.classify(item_code)

        if category == ItemCategory.ARMOR:
            armor = self._parse_armor_fields(
                item_code, socketed=socketed, quality=quality, runeword=runeword
            )
            self._current_item_properties = self._read_magical_properties(socketed=socketed)
            # [BINARY_VERIFIED TC02] Set items have additional bonus property
            # lists after the main 0x1FF, one per set bit in the 5-bit mask.
            if quality == 5 and hasattr(self, "_set_bonus_mask"):
                mask = self._set_bonus_mask
                set_bonus_props: list[dict[str, Any]] = []
                for i in range(5):
                    if mask & (1 << i):
                        bonus_props = self._read_magical_properties(socketed=False)
                        set_bonus_props.extend(bonus_props)
                        if logger.isEnabledFor(logging.DEBUG):
                            logger.debug("Set bonus list %d (aprop%d) read", i + 1, i + 1)
                self._current_set_bonus_properties = set_bonus_props
                # No byte-alignment or trailing skip after set
                # bonus lists. The next field (runeword props or item-end alignment)
                # starts at the exact bit position after the last 0x1FF. GoMule does
                # the same - no inter-list alignment. The old _skip_set_trailing_data()
                # byte-aligned here and then scanned forward for the next item, which
                # was a workaround that corrupted the source_data extraction and caused
                # the entire "padding" cascade bug in the D2I writer.
            return armor

        if category == ItemCategory.WEAPON:
            # [BINARY_VERIFIED TC33] Weapon type-specific data layout:
            #
            # THROWING WEAPONS (stackable=1 in weapons.txt):
            #   Uses Quantity instead of Durability - layout TBD.
            #
            # MELEE WEAPONS:
            #   max_dur(8) + cur_dur(8) + unknown_post_dur(2)
            #
            #   Then quality-dependent:
            #     Normal (quality=2): [sock_unknown(4) if socketed] + constant(24) + 0x1FF
            #       The 24-bit constant is identical across all Normal weapons
            #       (verified: TC09 Short Sword, TC23 all 5 weapons, TC33 War Swords).
            #       Normal weapons have NO ISC magical properties.
            #
            #     Magic/Rare/Set/Unique: ISC_properties + 0x1FF
            #       Properties start immediately after unknown_post_dur(2).
            #       Socketed weapons do NOT have +20 extra bits like armor.
            #       [BINARY_VERIFIED TC33: stat 17 (item_maxdamage_percent) at
            #        dur_end+2 for Magic, Rare, and Unique War Swords]
            if db.is_throwing_weapon(item_code):
                # [BINARY_VERIFIED TC33] Throwing weapons (stackable=1 in weapons.txt)
                # have durability AND quantity fields:
                #   max_dur(8) + cur_dur(8) + unknown_post_dur(2) + quantity(9)
                #   + [sock_unknown(4) if socketed]
                #   + ISC_properties + 0x1FF
                #
                # Unlike Normal melee weapons, Normal throwing weapons DO have
                # ISC properties (e.g. stat 253 item_replenish_quantity, stat 97).
                # All quality levels use the same layout with ISC property reading.
                #
                # Verified: all 6 TC33 throwing weapons (Normal, Magic, Rare,
                # Unique, socketed) decode correctly with this layout.
                # [INVARIANT] Every throwing weapon in Reimagined 3.0.7
                # has ``durability=2`` in weapons.txt - none hit the
                # ``max_dur==0`` sentinel that would omit ``cur_dur``
                # (see the melee-weapon branch below + the Phase Blade
                # case for the full sentinel rule).  If a mod update
                # ever introduces a durability=0 throwing weapon, this
                # branch needs the same ``if max_dur > 0`` gating
                # applied to the melee-weapon path.  The ``[BV TC33]``
                # marker remains accurate for the current data.
                throw_max_dur = reader.read(WEAPON_WIDTH_MAX_DUR)  # 8 bits [BV TC33]
                throw_cur_dur = reader.read(WEAPON_WIDTH_CUR_DUR)  # 8 bits [BV TC33]
                # Weapon-specific 2-bit tail after cur_dur. [BV TC33 width]; the
                # VALUE can be 0b00/0b01/0b10 across the fixture corpus, with
                # 0b10 ("always=2") being the common case for throwing weapons
                # specifically - see constants.WEAPON_WIDTH_POST_DUR for the
                # distribution across all 429 weapon fixtures.
                _throw_weapon_post_dur = reader.read(WEAPON_WIDTH_POST_DUR)
                _throw_qty = reader.read(9)  # [BINARY_VERIFIED TC33] quantity
                if socketed:
                    self._total_nr_of_sockets = reader.read(
                        4
                    )  # [BINARY_VERIFIED TC33] total socket count
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "Throwing weapon '%s': dur=%d/%d qty=%d",
                        item_code,
                        throw_cur_dur,
                        throw_max_dur,
                        _throw_qty,
                    )
                self._current_item_properties = self._read_magical_properties(socketed=socketed)
                return ItemArmorData(
                    defense_raw=0,
                    defense_display=0,
                    durability=ItemDurability(
                        max_durability=throw_max_dur,
                        current_durability=throw_cur_dur,
                    ),
                )
            # [BINARY_VERIFIED Lightsabre/FrozenOrbHydra + TC33 bows]
            # Weapon durability block layout, correctly depends on whether
            # max_dur is the D2R "no durability at all" sentinel:
            #
            #   max_dur > 0   (normal weapons, bows, etc.):
            #       max_dur(8) + cur_dur(8) + unk_post_dur(2)     = 18 bits
            #   max_dur == 0  (Phase Blade - the only weapon with
            #       ``durability=0`` in weapons.txt):
            #       max_dur(8)               + unk_post_dur(1)    =  9 bits
            #
            # The ``unk_post_dur`` width itself shifts with the
            # presence/absence of ``cur_dur``: 2 bits when cur_dur is
            # present, 1 bit when omitted.  The root cause of the
            # Lightsabre parse regression was reading the weapon path
            # as if max_dur > 0 always held - Phase Blade's 0-max_dur
            # then drifted every downstream stat by 10 bits and
            # surfaced as absurd values (fire_dam=2.9M, cold_dam=3.9M,
            # +3686540% Enhanced Defense, ...).  The 9-bit vs 18-bit
            # contrast was derived from a bit-sweep of Lightsabre's
            # 46-byte source_data; see the regression test in
            # ``tests/test_phase_blade_durability.py`` for the
            # full derivation and the expected-vs-actual walkthrough.
            max_dur = reader.read(WEAPON_WIDTH_MAX_DUR)  # 8 bits [BV TC09/TC33]
            if max_dur > 0:
                cur_dur = reader.read(WEAPON_WIDTH_CUR_DUR)  # 8 bits [BV TC09/TC33]
                # [BV TC33 width]; see constants.WEAPON_WIDTH_POST_DUR for the
                # observed value distribution - non-zero in 38 / 429 items, so
                # these bits are NOT padding and cannot be folded into cur_dur.
                _weapon_post_dur = reader.read(WEAPON_WIDTH_POST_DUR)
            else:
                cur_dur = 0
                _weapon_post_dur = reader.read(1)  # 1 bit [BV Lightsabre]
            if socketed:
                self._total_nr_of_sockets = reader.read(
                    4
                )  # [BINARY_VERIFIED TC33/TC34] total socket count
            if quality == 2:
                # Normal quality weapons: read ISC properties until 0x1FF.
                # Un-corrupted Normal weapons have an empty property list (immediate
                # 0x1FF after some padding bits). Corrupted/Enchanted Normal weapons
                # have actual properties (FCR, Elemental Skill Damage, corruption stats).
                # Previously read a hardcoded 24-bit constant + 0x1FF check,
                # which failed for corrupted Normal weapons (consuming property data as
                # "constant", causing cascading misalignment for all subsequent items).
                self._current_item_properties = self._read_magical_properties(socketed=socketed)
            elif quality == 5:
                # [BINARY_VERIFIED TC34] Set weapons have a 5-bit set_bonus_mask
                # immediately after unknown_post_dur(2), before ISC properties.
                # This mirrors set armor (where set_bonus_mask is also 5 bits,
                # read inside _parse_armor_fields after unknown_post_dur).
                # After the main 0x1FF, bonus property lists are present for each
                # bit set in the mask (same as set armor logic).
                self._set_bonus_mask = reader.read(5)
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "Set weapon '%s': set_bonus_mask=%d",
                        item_code,
                        self._set_bonus_mask,
                    )
                self._current_item_properties = self._read_magical_properties(socketed=socketed)
                # Read set bonus property lists (like armor set items)
                mask = self._set_bonus_mask
                set_bonus_props_w: list[dict[str, Any]] = []
                for i in range(5):
                    if mask & (1 << i):
                        bonus_props = self._read_magical_properties(socketed=False)
                        set_bonus_props_w.extend(bonus_props)
                        if logger.isEnabledFor(logging.DEBUG):
                            logger.debug("Set weapon bonus list %d (aprop%d) read", i + 1, i + 1)
                self._current_set_bonus_properties = set_bonus_props_w
                # Same as armor: no trailing skip after set bonus lists.
            else:
                # Magic/Rare/Unique (and Low/Superior): ISC properties start immediately
                self._current_item_properties = self._read_magical_properties(socketed=socketed)
            return ItemArmorData(
                defense_raw=0,
                defense_display=0,
                durability=ItemDurability(
                    max_durability=max_dur,
                    current_durability=cur_dur,
                ),
            )
        if category == ItemCategory.MISC:
            # [BINARY_VERIFIED TC29] Extended stackable items have a pre-property
            # quantity field. The layout depends on quality and item type:
            #
            # Normal quality (2) stackable:
            #   unknown(2) + [tome_prefix(5)] + qty(9) + 0x1FF
            #   - Rune stacks (s06/s07): unknown(2) + qty(9) + 0x1FF
            #   - Arrows/Bolts (aqv/cqv): unknown(2) + qty(9) + 0x1FF
            #   - Tomes (ibk/tbk): unknown(2) + prefix(5)=16 + qty(9) + 0x1FF
            #
            # Unique quality (7) stackable:
            #   unknown(1) + qty(9) + ISC_properties + 0x1FF
            #
            # Non-stackable Normal quality (2) misc:
            #   unknown(1) + ISC_properties + 0x1FF  [BINARY_VERIFIED TC16]
            #
            # Other misc (Magic/Rare/etc.):
            #   ISC_properties + 0x1FF

            if db.is_stackable(item_code):
                if quality == 2:
                    # Normal stackable: scan forward for 0x1FF terminator,
                    # then read 9-bit quantity directly before it.
                    # The bits between the current position and qty are
                    # an unknown prefix (variable width per item type).
                    self._misc_qty = self._read_quantity_before_terminator()
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug("Stackable item '%s' quantity: %d", item_code, self._misc_qty)
                    return None
                elif quality == 7:
                    # [BINARY_VERIFIED TC29] Unique stackable: unknown(1) + qty(9) + properties
                    _unknown_unique_stack_prefix = reader.read(1)  # purpose unknown [BV]
                    self._misc_qty = reader.read(9)
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(
                            "Unique stackable '%s' quantity: %d", item_code, self._misc_qty
                        )
                    self._current_item_properties = self._read_magical_properties(socketed=socketed)
                    return None
                else:
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(
                            "Stackable item '%s' quality=%d - reading properties",
                            item_code,
                            quality,
                        )
                    self._current_item_properties = self._read_magical_properties(socketed=socketed)
                    return None
            elif quality == 2:
                # [BINARY_VERIFIED TC16/TC19] Non-stackable Normal quality misc
                _unknown_misc_normal_prefix = reader.read(1)  # purpose unknown [BV] [BV]

            # [BINARY_VERIFIED Baals_Amu] Set quality misc items (amulets, rings)
            # have a 5-bit set_bonus_mask before properties, same as armor/weapon.
            if quality == 5:
                self._set_bonus_mask = reader.read(5)
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "Set misc '%s': set_bonus_mask=%d", item_code, self._set_bonus_mask
                    )

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Misc item '%s' - reading properties", item_code)
            self._current_item_properties = self._read_magical_properties(socketed=socketed)

            # Set bonus property lists (same logic as armor/weapon Set items)
            if quality == 5 and hasattr(self, "_set_bonus_mask"):
                mask = self._set_bonus_mask
                set_bonus_props_m: list[dict[str, Any]] = []
                for i in range(5):
                    if mask & (1 << i):
                        bonus_props = self._read_magical_properties(socketed=False)
                        set_bonus_props_m.extend(bonus_props)
                        if logger.isEnabledFor(logging.DEBUG):
                            logger.debug("Set bonus list %d for misc '%s'", i + 1, item_code)
                self._current_set_bonus_properties = set_bonus_props_m

            # [BINARY_VERIFIED testStash] AdvancedStashStackable items that are NOT
            # stackable in misc.txt (keys, worldstone shards, statues, pliers, etc.)
            # store their quantity AFTER the 0x1FF ISC terminator:
            #   1 extra bit + 7-bit quantity
            # This is a Reimagined/ROTW extension for stash-stackable quest items.
            if db.is_quantity_item(item_code) and not db.is_stackable(item_code):
                _qty_extra = reader.read(1)
                # Record blob-relative bit offset BEFORE reading the 7-bit quantity
                # so the writer can patch it in place. [BV]
                self._misc_qty_bit_offset = reader.bit_pos - self._item_start_bit
                self._misc_qty = reader.read(7)
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "AdvancedStashStackable '%s': quantity=%d (7 bits after 0x1FF)",
                        item_code,
                        self._misc_qty,
                    )
            return None

        # UNKNOWN category
        #
        # Before falling back to speculative property reading, fail-loud if
        # the databases needed for classification are not loaded - that is
        # the far more common cause of getting here with a perfectly valid
        # item code. Silent fallback on a missing ItemTypeDatabase silently
        # loses 90%+ of items on real SharedStash files (forensic report
        # 2026-04-20, Tab 0 of ModernSharedStashSoftCoreV2.d2i: 5 of 57).
        if not get_item_type_db().is_loaded():
            raise GameDataNotLoadedError(
                f"Cannot classify item code '{item_code}': "
                f"ItemTypeDatabase is not loaded. Call load_item_types() "
                f"before parsing, or use D2IParser/D2SParser.parse() which "
                f"auto-load. Parsing further in this state would silently "
                f"produce bit-misaligned garbage."
            )
        # Genuinely unknown code: the DB is loaded but this code is absent.
        # Could be a Reimagined addition the DB doesn't know, or actual
        # garbage from upstream bit-misalignment. Legacy speculative path
        # remains for now but is clearly marked.
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Unknown item category for '%s' - DB is loaded but code not "
                "present; falling back to speculative property read. "
                "This is a best-effort path and may produce misaligned data.",
                item_code,
            )
        self._current_item_properties = self._read_magical_properties(socketed=socketed)
        return None

    def _parse_armor_fields(
        self, item_code: str, socketed: bool = False, quality: int = 0, runeword: bool = False
    ) -> ItemArmorData:
        """Read armor-specific fields: defense + durability + socket data.

        ## Binary Layout (all [BV])

        Base fields (ALL armor items):
          defense(11) + max_dur(8) + cur_dur(10) = 29 bits

        The cur_dur field is read as a single 10-bit unsigned integer.
        Empirically the upper 2 bits are always zero across every armor
        item in the test corpus (612 items) because the base item
        durability is capped at 250 in Reimagined, but the 10-bit
        encoding is the canonical interpretation - it avoids inventing
        a "2 unknown bits" gap that an otherwise densely-packed
        format would be surprising to contain.

        Note: the WEAPON branch uses a different layout (max(8) +
        cur(8) + post(2)) because weapons DO exhibit non-zero values
        in those trailing 2 bits (38 out of 429 weapon items),
        meaning those bits carry semantics that cannot be absorbed
        into cur_dur without producing impossible cur > max values.

        Socketed items add variable-width socket data after the durability block:

          +----------------------------+-------------------------------------------+
          | Item Type                  | Socket Data Layout                        |
          +----------------------------+-------------------------------------------+
          | Non-RW, non-Unique Shield  | shield_unknown(2) + sock_count(4) = 6 bits    |
          | RW Shield                  | sock_count(4) + rw_data(24) = 28 bits     |
          | Superior non-RW non-shield | sock_unknown(20) = count(4) + quality(16)     |
          | All others*                | sock_count(4)                             |
          +----------------------------+-------------------------------------------+
          * Normal, Magic, Rare, Set, Unique, Crafted, RW non-shield, Unique shield

        Set quality (q=5) adds set_bonus_mask(5) after socket data.

        Verified against: TC02 (Set mask), TC08/TC10 (defense/dur), TC11
        (Superior sock=20), TC24 (Normal sock=4), TC32 (shield_unknown=2),
        TC37 (Set sock=4), Spirit.d2s (RW shield=28), OrnatePlate.d2s
        (Magic sock=4), SetSocket.d2s (Set sock=4).
        """
        reader = self._require_reader()
        db = get_item_type_db()
        # [INVARIANT] Every armor row in Reimagined 3.0.7 armor.txt
        # has ``durability > 0`` (0 of 218 rows hit the "no durability
        # at all" sentinel).  The armor format therefore always carries
        # the full 18-bit ``max_dur + cur_dur`` block, unlike weapons
        # where Phase Blade (``7cr``, durability=0) omits ``cur_dur``
        # - see the melee-weapon branch upstream for the variable-width
        # rule.  If a mod update ever introduces a ``durability=0``
        # armor, apply the same ``if max_dur > 0`` gating here.
        defense_raw = reader.read(ARMOR_WIDTH_DEFENSE)  # 11 bits [BV]
        max_dur = reader.read(ARMOR_WIDTH_MAX_DUR)  #  8 bits [BV]
        cur_dur = reader.read(ARMOR_WIDTH_CUR_DUR)  # 10 bits [BV TC-wide, upper 2 always 0]
        if socketed:
            is_shield = db.is_shield(item_code)
            if is_shield and not runeword and quality not in (3, 7):
                # [BV] Socketed non-RW, non-Unique, non-Superior shields
                # have 2 extra unknown bits before the socket count field.
                # Unique (q=7) and Superior (q=3) shields do NOT have these bits.
                # [BV]
                # [BV]
                _unknown_shield_socketed = reader.read(2)  # purpose unknown [BV]
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "Socketed shield extra bits: %d (2 bits)", _unknown_shield_socketed
                    )
            # [BINARY_VERIFIED TC24/TC37/Spirit.d2s] Sock_unknown width:
            #   Normal (q=2) non-shield: 4 bits [BV]
            #   Set    (q=5): 4 bits [BV]
            #   RW shield: sock(4) + unknown(24) = 28 bits [BV Spirit.d2s]
            #   Superior (q=3) + non-RW: 20 bits [BV]
            if is_shield and runeword:
                # [BINARY_VERIFIED Spirit.d2s] RW shields: NO shield_unknown,
                # but 28-bit sock field (4 socket count + 24 RW data).
                self._total_nr_of_sockets = reader.read(4)
                _rw_shield_unknownnown_data = reader.read(
                    24
                )  # purpose unknown [BV] (RW-specific data)
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "Socketed RW shield '%s': total_sockets=%d, rw_unknownnown=0x%06X",
                        item_code,
                        self._total_nr_of_sockets,
                        _rw_shield_unknownnown_data,
                    )
            elif quality == 3 and not runeword and not is_shield:
                # [BINARY_VERIFIED TC11] Superior non-runeword non-shield armor:
                # 20 bits = 4-bit socket count + 16 extra quality bits.
                # Shields are excluded because they already have shield_unk(2)
                # which accounts for the extra quality data.
                # [BINARY_VERIFIED TC56 TestSorc: Superior Monarch (shield) has
                #  shield_unk(2) + sock_count(4) = 6 bits, NOT 20]
                _raw_socketed = reader.read(20)
                self._total_nr_of_sockets = _raw_socketed & 0xF  # first 4 bits
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "Socketed Superior armor '%s': sock_unknown=20 bits, total_sockets=%d",
                        item_code,
                        self._total_nr_of_sockets,
                    )
            else:
                # [BINARY_VERIFIED TC37/TC24/OrnatePlate.d2s] All other qualities
                # (Normal q=2, Magic q=4, Set q=5, Rare q=6, Unique q=7, Crafted q=8)
                # and Runeword items: 4-bit sock_unknown = total socket count.
                self._total_nr_of_sockets = reader.read(4)
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "Socketed armor '%s' (q=%d, rw=%s): total_sockets=%d",
                        item_code,
                        quality,
                        runeword,
                        self._total_nr_of_sockets,
                    )
        if quality == 5:
            # [BINARY_VERIFIED TC02] 5-bit set bonus list mask.
            # Each bit indicates if the corresponding bonus property list
            # (aprop1-aprop5 from setitems.txt) is present after the main
            # property list. TC02 mask=2 (binary 00010) -> only aprop2 present.
            self._set_bonus_mask = reader.read(5)
        return ItemArmorData(
            defense_raw=defense_raw,
            defense_display=defense_raw - ARMOR_SAVE_ADD_DEFENSE,
            durability=ItemDurability(
                max_durability=max_dur,
                current_durability=cur_dur,
            ),
        )

    def _skip_to_terminator_safe(self) -> None:
        """Safely advance past unknown type-specific fields to the 0x1FF terminator.

        For item types where type-specific field widths are [SPEC_ONLY] or unknown,
        this method reads past those fields by scanning for the property list.

        Strategy: if ItemStatCost.txt is loaded, read the property list properly
        (9-bit stat ID -> look up bit width -> read value -> repeat until 0x1FF).
        If not loaded, fall back to bit-by-bit scan (unreliable for complex items).
        """
        reader = self._require_reader()
        isc = get_isc_db()

        if isc.is_loaded():
            self._read_property_list_with_isc()
        else:
            # Fallback: bit-by-bit scan. Unreliable for items with magical properties.
            # Load excel/reimagined/itemstatcost.txt for correct parsing.
            logger.warning(
                "ItemStatCost.txt not loaded - using bit-scan fallback. "
                "Items with magical properties may parse incorrectly."
            )
            self._bit_scan_for_terminator()

    def _read_property_list_with_isc(self) -> None:
        """Read the magical property list using ItemStatCost.txt definitions.

        Reads 9-bit stat IDs until 0x1FF terminator. For each stat ID,
        looks up the bit width from ItemStatCost.txt and reads (skips) the value.

        This is the correct and reliable method. Requires ItemStatCost.txt loaded.
        """
        reader = self._require_reader()
        isc = get_isc_db()

        for _ in range(256):  # safety limit
            stat_id = reader.read(9)
            if stat_id == ITEM_STATS_TERMINATOR:
                return  # This method is a stub; real logic in _read_magical_properties

            stat_def = isc.get(stat_id)
            if stat_def is None:
                logger.warning(
                    "Unknown stat ID %d at bit %d in property list - "
                    "cannot continue reading properties.",
                    stat_id,
                    reader.bit_pos,
                )
                # Fall back to bit-scan from current position
                self._bit_scan_for_terminator()
                return

            # Read param bits if present
            if stat_def.save_param_bits > 0:
                _param = reader.read(stat_def.save_param_bits)

            # For encode type 1 (min-max pair): two values share one stat ID
            if stat_def.encode == 1:
                _val1 = reader.read(stat_def.save_bits)
                # [BINARY_VERIFIED TC17] Only read paired stat when no param bits
                if stat_def.save_param_bits == 0:
                    paired = isc.get(stat_id + 1)
                    if paired:
                        _val2 = reader.read(paired.save_bits)
            elif stat_def.encode in (2, 3):
                # Skill-on-event / charged skill: all bits in save_bits
                _val = reader.read(stat_def.save_bits)
            else:
                # Default: single value
                _val = reader.read(stat_def.save_bits)

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "Property stat_id=%d (%s), bits=%d", stat_id, stat_def.name, stat_def.save_bits
                )

    def _bit_scan_for_terminator(self) -> None:
        """Last-resort bit-by-bit scan for the 0x1FF terminator.

        Only used when ItemStatCost.txt is not loaded.
        Unreliable for items with non-empty property lists.
        """
        reader = self._require_reader()
        max_scan = min(1024, reader.bits_remaining - 9)
        for _ in range(max_scan):
            if reader.bits_remaining < 9:
                return
            val = reader.peek(9)
            if val == ITEM_STATS_TERMINATOR:
                reader.read(9)
                return
            reader.read(1)

    def _skip_set_trailing_data(self) -> None:
        """Skip unknown trailing data after set bonus property lists.

        [UNKNOWN] After all set bonus lists are read, there are additional
        bits before the next item whose structure is not yet understood.
        TC02 shows 54 bits between the last bonus list 0x1FF and the next item.

        Strategy: byte-align first, then scan forward byte by byte for a
        position where the Huffman decoder can successfully read an item code.
        This is a safe fallback that doesn't require understanding the data.
        """
        reader = self._require_reader()
        reader.skip_to_byte_boundary()

        # Scan forward byte by byte for a valid item start
        for _ in range(20):  # max 20 bytes forward
            if reader.bits_remaining < 80:  # minimum item size
                break
            # [BINARY_VERIFIED TC34] Stop immediately if the next 2 bytes are the
            # JM section marker - this means we are at the end of the item list
            # (last item was a set item). Do NOT overshoot into the next section.
            if reader.peek_bytes(2) == SECTION_MARKER_ITEMS:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "Set trailing skip: JM marker found at bit %d - stopping",
                        reader.bit_pos,
                    )
                return
            pos = reader.bit_pos
            # Try Huffman decode at bit 53 - valid only if the decoded
            # item code exists in the game data (armor/weapon/misc).
            try:
                reader.seek_bit(pos + 53)
                from d2rr_toolkit.parsers.huffman import decode_item_code

                code, _ = decode_item_code(reader)
                db = get_item_type_db()
                if db.contains(code):  # silent probe - no WARNING log
                    reader.seek_bit(pos)  # restore to item start
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(
                            "Set trailing skip: found valid item at bit %d (code=%s)",
                            pos,
                            code,
                        )
                    return
                # [BINARY_VERIFIED TC36] Do NOT use simple-flag heuristic here.
                # Bit 21 of random trailing data can be 1 by coincidence, causing
                # false-positive "simple item" detection that terminates the scan
                # too early (before the JM end-of-list marker is reached).
                # The inter-item padding detection in _parse_item_list() reliably
                # handles simple items as socket children after the skip.
            except Exception:
                pass
            reader.seek_bit(pos)  # restore on failure

            # Not a valid item start, advance one byte
            reader.read(8)

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Set trailing data: could not find next item within 20 bytes at bit %d",
                reader.bit_pos,
            )

    def _decode_rw_display_props(
        self,
        pos_before_rw: int,
        scan_end_pos: int,
    ) -> list[dict[str, Any]]:
        """Decode runeword display properties from the RW ISC property slot.

        The RW ISC slot has the structure:
            [internal state stats] + [display property stats] + 0x1FF

        Internal state stats may include unknown stat IDs (D2R/Reimagined
        internal tracking stats). Display properties use only known ISC stats
        and form the last contiguous block before the terminator.

        Strategy: scan forward from pos_before_rw, trying each bit position
        as a candidate start for the display property block.  For each
        candidate we attempt a clean ISC decode (no unknown stat IDs).
        The first candidate where the clean decode ends exactly at
        scan_end_pos (the position after the 0x1FF terminator) is accepted.

        As an optimisation, when _read_magical_properties() aborts due to an
        unknown stat and its fallback scan (Priority 2) repositions the reader
        at the next known stat, we jump directly to that position instead of
        advancing one bit at a time.  This reduces the typical case to ~2
        attempts rather than N.

        [BINARY_VERIFIED TC38]: display props at bit 7457 (Reimagined Insight),
        confirmed via full sequential decode of all 12 display-property stats.

        Args:
            pos_before_rw: Start of the RW ISC property slot.
            scan_end_pos:  Position after the 0x1FF terminator (from bit-scan).

        Returns:
            Decoded display property list, or [] if no clean decode is found.
        """
        reader = self._require_reader()
        # Maximum plausible internal state prefix: 300 bits covers all observed
        # cases (TC24/TC38/TC39 largest internal state is ~90 bits).
        term_start = scan_end_pos - 9
        max_search = min(300, max(0, term_start - pos_before_rw))

        candidate = pos_before_rw
        for _attempt in range(50):  # safety cap
            if candidate > pos_before_rw + max_search:
                break

            reader.seek_bit(candidate)

            saved_flag = self._qsd_rare_retry_needed
            self._qsd_rare_retry_needed = False
            props = self._read_magical_properties()
            had_unknown = self._qsd_rare_retry_needed
            actual_end = reader.bit_pos
            self._qsd_rare_retry_needed = saved_flag

            if not had_unknown and actual_end == scan_end_pos:
                # Clean decode ending at the correct terminator.
                # Validate that it looks like real display props, not internal
                # state data that happens to decode cleanly.
                #
                # Heuristic 1: bytime stats (encode=4) have save_bits=22 and
                # can produce values up to ~4M; internal-state bytime values are
                # always far above any plausible item bonus.  Real runeword
                # bytime bonuses (e.g. regen per second) are small (< 1000).
                # [BINARY_VERIFIED TC24: internal state has bytime values ~1.5M+]
                #
                # Heuristic 2: elemental damage stats are stored as consecutive
                # min/max pairs in the binary.  A physically impossible value
                # (min > max) means the data is internal state that happens to
                # decode as damage stats.
                # [BINARY_VERIFIED TC24 ltp: coldmindam=138 > coldmaxdam=74]
                # Pairs (min_id, max_id): fire(48,49) light(50,51) poison(52,53)
                # cold(54,55).  min_id is always one below max_id.
                _DAMAGE_PAIRS = {48: 49, 50: 51, 52: 53, 54: 55}
                isc_db = get_isc_db()
                is_internal_state = False
                _stat_val: dict[int, int] = {}
                _prev_sid = -1
                for p in props:
                    sid = p["stat_id"]
                    _stat_val[sid] = p.get("value", 0)
                    sd = isc_db.get(sid)
                    if sd and sd.encode == 4:
                        v = p.get("value", 0)
                        if isinstance(v, int) and abs(v) > 10_000:
                            is_internal_state = True
                            if logger.isEnabledFor(logging.DEBUG):
                                logger.debug(
                                    "RW display props: candidate at bit %d rejected"
                                    " (internal-state bytime value: stat %d=%d)",
                                    candidate,
                                    sid,
                                    v,
                                )
                            break
                    # Heuristic 3: D2 always writes stats in ascending stat ID
                    # order within a property list.  A decrease in stat ID means
                    # the decode has drifted into internal-state data that
                    # happens to look like valid ISC entries.
                    # [BV]
                    if sid < _prev_sid:
                        is_internal_state = True
                        if logger.isEnabledFor(logging.DEBUG):
                            logger.debug(
                                "RW display props: candidate at bit %d rejected"
                                " (non-ascending stat IDs: %d after %d)",
                                candidate,
                                sid,
                                _prev_sid,
                            )
                        break
                    _prev_sid = sid
                if not is_internal_state:
                    for min_id, max_id in _DAMAGE_PAIRS.items():
                        if min_id in _stat_val and max_id in _stat_val:
                            if _stat_val[min_id] > _stat_val[max_id]:
                                is_internal_state = True
                                if logger.isEnabledFor(logging.DEBUG):
                                    logger.debug(
                                        "RW display props: candidate at bit %d rejected"
                                        " (damage pair min>max: stat %d=%d > stat %d=%d)",
                                        candidate,
                                        min_id,
                                        _stat_val[min_id],
                                        max_id,
                                        _stat_val[max_id],
                                    )
                                break
                if not is_internal_state:
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(
                            "RW display props: found at offset +%d (bit %d), %d props decoded",
                            candidate - pos_before_rw,
                            candidate,
                            len(props),
                        )
                    return props
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "RW display props: candidate at bit %d rejected (internal-state bytime values)",
                        candidate,
                    )

            # Advance to the next candidate.
            # If the fallback scan (Priority 2) repositioned the reader at a
            # known stat inside the slot, jump there directly.
            if had_unknown and pos_before_rw < actual_end < scan_end_pos:
                # Priority 2 gave us a promising start - try it directly.
                candidate = actual_end
            else:
                candidate += 1

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "RW display props: no clean decode in %d-bit window from bit %d",
                max_search,
                pos_before_rw,
            )
        return []

    def _read_quantity_before_terminator(self) -> int:
        """Scan forward for 0x1FF terminator, read 9-bit quantity before it.

        Normal-quality stackable MISC items have variable-width unknown bits
        between the extended header and the quantity. Instead of guessing the
        prefix width, we scan for the 0x1FF terminator and read 9 bits of
        quantity directly before it. The reader position advances past 0x1FF.
        """
        reader = self._require_reader()
        start_pos = reader.bit_pos
        # Scan forward for 0x1FF (max 50 bits should be enough)
        for offset in range(50):
            val = 0
            for i in range(9):
                bit_pos = start_pos + offset + i
                byte_idx = bit_pos // 8
                bit_idx = bit_pos % 8
                if byte_idx < len(reader._data) and reader._data[byte_idx] & (
                    1 << bit_idx
                ):
                    val |= 1 << i
            if val == ITEM_STATS_TERMINATOR:
                # Found! Read 9-bit quantity right before it
                qty_start = start_pos + offset - 9
                qty = 0
                for i in range(9):
                    bit_pos = qty_start + i
                    byte_idx = bit_pos // 8
                    bit_idx = bit_pos % 8
                    if reader._data[byte_idx] & (1 << bit_idx):
                        qty |= 1 << i
                # Advance reader past the terminator
                reader.seek_bit(start_pos + offset + 9)
                return qty
        # Terminator not found - advance reader and return 0
        logger.warning("0x1FF terminator not found within 50 bits for stackable quantity")
        return 0

    def _read_magical_properties(self, socketed: bool = False, is_set: bool = False) -> list[dict[str, Any]]:
        """Read the magical property list using ItemStatCost.txt.

        Reads 9-bit stat IDs until 0x1FF terminator. For each stat,
        reads param bits (if any) and value bits using Save Param Bits
        and Save Bits from ItemStatCost.txt.

        Handles all Encode types:
          Encode 0: normal single value
          Encode 1: min/max pair - read FIRST stat value, then IMMEDIATELY
                    read SECOND stat value (stat_id+1) WITHOUT a new 9-bit ID
          Encode 2: skill-on-event - 6 bits level + 10 bits skill_id + remaining
          Encode 3: charged skill - 6 level + 10 skill_id + 8 charges + 8 max_charges

        [BV] 0x1FF terminator position confirmed TC08/TC10.
        [SPEC_ONLY] individual property values - ISC must be loaded.

        Returns:
            List of raw property dicts (stat_id, param, raw_value).
        """
        reader = self._require_reader()
        isc = get_isc_db()
        properties: list[dict[str, Any]] = []

        for _ in range(512):
            stat_id = reader.read(9)

            # ── Terminator check FIRST - before any ISC lookup ──
            # [BV]: 0x1FF immediately after armor fields (no properties)
            # [BV]: 0x1FF after magical property values
            if stat_id == ITEM_STATS_TERMINATOR:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "Property list terminator 0x1FF at bit %d",
                        reader.bit_pos,
                    )
                return properties

            stat_def = isc.get(stat_id)
            if stat_def is None:
                # Unknown stat - engine-internal tracking data (stat_id > 435),
                # a 7-slot Rare QSD misparse, or a bit alignment issue.
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "Unknown stat_id=%d at bit %d",
                        stat_id,
                        reader.bit_pos,
                    )

                # Signal QSD retry for 7-slot Rare items [BINARY_VERIFIED TC24 J2]
                self._qsd_rare_retry_needed = True

                # ── Engine-internal stat: scan for 0x1FF terminator ────
                # [BINARY_VERIFIED MrLockhart.d2s]
                # The D2R engine writes internal tracking data (aura timers,
                # skill-link tracking, cooldowns, etc.) as pseudo-stat-IDs
                # 436-510 into property list slots. The data after these
                # IDs has UNKNOWN and VARIABLE bit widths - the remaining
                # bits between here and the 0x1FF are ALL engine-internal
                # (even if bit patterns coincidentally match valid stat_ids).
                #
                # Two-phase scan:
                # Phase 1 (conservative): scan -9..+200 bits for 0x1FF.
                #   This covers the common case where the terminator is
                #   close by (observed: 7-123 bits in MrLockhart.d2s).
                # Phase 2 (extended + validated): if Phase 1 fails, scan
                #   up to +500 bits but validate each 0x1FF candidate by
                #   checking that the next byte-aligned position has a
                #   valid Huffman item code. This prevents false positives
                #   from coincidental 0x1FF patterns in other items' data.
                save_pos = reader.bit_pos
                search_start = max(0, save_pos - 9)

                # ── Phase 1: conservative scan (original 200-bit range) ──
                found_terminator = False
                for n in range(9 + 200):
                    pos = search_start + n
                    if pos + 9 > reader._total_bits:
                        break
                    if reader._read_bits_at(pos, 9) == ITEM_STATS_TERMINATOR:
                        reader.seek_bit(pos + 9)
                        if logger.isEnabledFor(logging.DEBUG):
                            logger.debug(
                                "Engine-internal stat %d: 0x1FF at bit %d (skip=%d bits)",
                                stat_id,
                                pos,
                                pos - save_pos,
                            )
                        found_terminator = True
                        break

                if found_terminator:
                    return properties

                # ── Phase 2: legacy fallback (Priority 2 known stat) ──
                # Use _scan_for_terminator_from_here which has:
                #   Priority 1: 0x1FF with back-look (already tried in Phase 1)
                #   Priority 2: find known stat_id with save_bits > 0
                # Priority 2 is needed by _decode_rw_display_props which
                # uses the reader position to advance its candidate.
                self._scan_for_terminator_from_here(socketed=socketed)

                distance = reader.bit_pos - save_pos
                if 0 < distance <= 250:
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(
                            "Terminator scan: skipped %d bits for unknown stat %d",
                            distance,
                            stat_id,
                        )
                    return properties

                # Scan failed or distance=0 (known stat at current pos) -
                # raise for item-level recovery.
                raise ValueError(
                    f"Unknown stat_id={stat_id} at bit {save_pos} - "
                    f"ISC has no definition. Terminator scan unreliable "
                    f"(distance={distance})."
                )

            # Read param bits if present [SPEC_ONLY]
            param = 0
            if stat_def.save_param_bits > 0:
                param = reader.read(stat_def.save_param_bits)

            encode = stat_def.encode

            if encode == 1:
                # Encode=1: paired value handling depends on save_param_bits.
                # [BINARY_VERIFIED TC17] When save_param_bits > 0 (e.g. stat 97
                # item_nonclassskill), the paired stat is NOT read - the param
                # bits contain the skill/state info instead of a min/max pair.
                # When save_param_bits == 0 (e.g. mindamage/maxdamage), the
                # paired stat (stat_id+1) IS read immediately after.
                val1 = reader.read(stat_def.save_bits) if stat_def.save_bits > 0 else 0
                val2 = 0
                if stat_def.save_param_bits == 0:
                    paired = isc.get(stat_id + 1)
                    val2 = (
                        reader.read(paired.save_bits)
                        if paired and paired.save_bits > 0
                        else 0
                    )
                properties.append(
                    {
                        "stat_id": stat_id,
                        "name": stat_def.name,
                        "param": param,
                        "value": val1 - stat_def.save_add,
                        "paired_value": val2,
                    }
                )
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "Property(Enc1): %s=%d / paired=%d",
                        stat_def.name,
                        val1 - stat_def.save_add,
                        val2,
                    )

            elif encode == 2:
                # [BINARY_VERIFIED TC21] Skill-on-event (e.g. "20% Chance to Cast
                # Level 5 Dim Vision When Struck").
                #
                # When save_param_bits > 0 (Reimagined ISC: save_param=16):
                #   The param field already contains level(6) + skill_id(10) packed.
                #   save_bits contains just the chance/modifier value.
                #   Total: 9(id) + 16(param) + 7(value) = 32 bits
                #
                # When save_param_bits == 0 (legacy D2 format):
                #   6 bits level + 10 bits skill_id + (save_bits-16) bits chance
                #   Total: 9(id) + save_bits bits
                if stat_def.save_param_bits > 0:
                    # [BINARY_VERIFIED TC21] param packs level(6) + skill_id(10)
                    level = param & 0x3F
                    skill_id = (param >> 6) & 0x3FF
                    chance = reader.read(stat_def.save_bits) if stat_def.save_bits > 0 else 0
                else:
                    level = reader.read(6)
                    skill_id = reader.read(10)
                    chance = (
                        reader.read(stat_def.save_bits - 16) if stat_def.save_bits > 16 else 0
                    )
                properties.append(
                    {
                        "stat_id": stat_id,
                        "name": stat_def.name,
                        "level": level,
                        "skill_id": skill_id,
                        "chance": chance,
                        "skill_name": get_skill_db().name(skill_id),
                    }
                )

            elif encode == 3:
                # [BINARY_VERIFIED TC21] Charged skill (e.g. "Level 2 War Cry
                # (200/200 Charges)").
                #
                # When save_param_bits > 0 (Reimagined ISC: save_param=16):
                #   param contains level(6) + skill_id(10) packed.
                #   save_bits contains charges(8) + max_charges(8) = 16 bits.
                #
                # When save_param_bits == 0 (legacy D2 format):
                #   6 level + 10 skill_id + 8 charges + 8 max_charges = 32 bits
                if stat_def.save_param_bits > 0:
                    level = param & 0x3F
                    skill_id = (param >> 6) & 0x3FF
                    charges = reader.read(8)
                    max_chg = reader.read(8)
                else:
                    level = reader.read(6)
                    skill_id = reader.read(10)
                    charges = reader.read(8)
                    max_chg = reader.read(8)
                properties.append(
                    {
                        "stat_id": stat_id,
                        "name": stat_def.name,
                        "level": level,
                        "skill_id": skill_id,
                        "charges": charges,
                        "max_charges": max_chg,
                        "skill_name": get_skill_db().name(skill_id),
                    }
                )

            elif encode == 4:
                # [BINARY_VERIFIED TC01] encode=4 with save_bits=0 consumes 5 extra bits.
                # encode=4 with save_bits>0 (IDs 268-303): consume save_bits bits.
                extra = (
                    stat_def.save_bits if stat_def.save_bits > 0 else 14
                )  # [BINARY_VERIFIED TC01]
                raw_value = reader.read(extra) if extra > 0 else 0
                properties.append(
                    {
                        "stat_id": stat_id,
                        "name": stat_def.name,
                        "param": param,
                        "value": raw_value,
                    }
                )
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "Property(Enc4): %s(id=%d) extra=%d", stat_def.name, stat_id, extra
                    )

            else:
                # Encode 0: normal single value
                raw_value = reader.read(stat_def.save_bits) if stat_def.save_bits > 0 else 0
                display_value = raw_value - stat_def.save_add
                properties.append(
                    {
                        "stat_id": stat_id,
                        "name": stat_def.name,
                        "param": param,
                        "value": display_value,
                    }
                )
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug("Property: %s(id=%d)=%d", stat_def.name, stat_id, display_value)

                # [BINARY_VERIFIED TC19/TC33] Hardcoded stat groups: certain
                # stats are ALWAYS followed by their paired stats WITHOUT a
                # separate 9-bit stat_id. This is a game engine behavior, not
                # indicated by the encode field in itemstatcost.txt.
                #
                # [BINARY_VERIFIED TC33] stat 17 (item_maxdamage_percent) is
                # paired with 18 (item_mindamage_percent). The Reimagined ISC
                # sets encode=0 for both, but the game engine still writes them
                # as a hardcoded pair. Verified: Magic War Sword +156% ED
                # decodes correctly with pairing, landing exactly at 0x1FF.
                HARDCODED_PAIRS = {
                    17: [18],  # item_maxdamage_percent -> item_mindamage_percent [BV]
                    48: [49],  # fire min -> max
                    50: [51],  # lightning min -> max
                    52: [53],  # magic min -> max
                    54: [55, 56],  # cold min -> max -> length
                    57: [58, 59],  # poison min -> max -> length
                }
                if stat_id in HARDCODED_PAIRS:
                    for paired_id in HARDCODED_PAIRS[stat_id]:
                        paired_def = isc.get(paired_id)
                        if paired_def and paired_def.save_bits > 0:
                            paired_raw = reader.read(paired_def.save_bits)
                            paired_display = paired_raw - paired_def.save_add
                            properties.append(
                                {
                                    "stat_id": paired_id,
                                    "name": paired_def.name,
                                    "param": 0,
                                    "value": paired_display,
                                }
                            )
                            if logger.isEnabledFor(logging.DEBUG):
                                logger.debug(
                                    "  Paired: %s(id=%d)=%d",
                                    paired_def.name,
                                    paired_id,
                                    paired_display,
                                )

        logger.error("Property list did not terminate within 512 reads")
        return properties

    def _scan_for_terminator_from_here(self, socketed: bool = False) -> None:
        """Fallback: find terminator when an unknown stat is encountered.

        Called when _read_magical_properties encounters a stat_id that is
        not in ItemStatCost.txt (e.g. Reimagined-specific stats > 435).

        The reader is positioned AFTER the 9-bit unknown stat_id was read.
        We must find the 0x1FF terminator and advance past it.

        Priority 1: look for 0x1FF in a window starting 9 bits BEFORE `start`.
          The -9 offset is critical: an unknown stat_id's 9 read bits may
          partially overlap with the 0x1FF terminator.  For example in TC06
          the DFS set armor's bonus list has an unknown stat whose last 2 bits
          are the first 2 bits of the 0x1FF at that position.  Without the -9
          back-look, the terminator is missed and Priority 2 kicks in -
          then it falsely resumes parsing from the FLAGS of the next item
          (rvl/rup in TC06), consuming those items as ISC property data.
          [BINARY_VERIFIED TC06: back-look recovers 0x1FF at bit 4114 for DFS]

        Priority 2 (fallback): find any known stat_id with save_bits > 0.
          Used when no 0x1FF exists nearby (truncated/malformed data).
          Resumes ISC parsing from that position.
        """
        reader = self._require_reader()
        isc = get_isc_db()
        start = reader.bit_pos

        # Priority 1: find 0x1FF, searching from (start - 9) to (start + 200).
        # The -9 back-look handles overlap between the unknown stat_id bits and
        # the terminator bits.  We clamp to 0 so we never read before the data.
        search_start = max(0, start - 9)
        for n in range(0, 9 + 200):  # 9 extra iterations to cover the back-look
            pos = search_start + n
            if pos + 9 > reader._total_bits:
                break
            if reader._read_bits_at(pos, 9) == ITEM_STATS_TERMINATOR:
                reader.seek_bit(pos + 9)
                # [BV] byte-align after terminator
                reader.skip_to_byte_boundary()
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "Fallback terminator: skipped %d bits at bit %d",
                        pos - start,
                        start,
                    )
                return

        # Priority 2: find a known stat_id with save_bits > 0
        for n in range(0, 200):
            if start + n + 9 > reader._total_bits:
                break
            nv = reader._read_bits_at(start + n, 9)
            s = isc.get(nv)
            if s and s.save_bits > 0:
                reader.seek_bit(start + n)
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug("Fallback known stat %d: skipped %d bits at bit %d", nv, n, start)
                return

        logger.error(
            "Cannot find terminator or known stat within 40 bits at bit %d. "
            "Add missing stat_id to isc_reimagined_patch.txt.",
            start,
        )

    def _try_recover_item_alignment(self, remaining_items: int) -> bool:
        """Attempt to recover parser alignment after a failed item parse.

        Scans forward byte-by-byte, probing for valid Huffman codes at each
        byte boundary. A valid Huffman code at a byte boundary strongly suggests
        the start of the next item (since items are byte-aligned in d2s files).

        Args:
            remaining_items: Number of items still expected to parse.

        Returns:
            True if a valid item start was found and the reader is positioned there.
        """
        reader = self._require_reader()
        from d2rr_toolkit.parsers.huffman import decode_item_code

        # Align to next byte boundary first
        reader.skip_to_byte_boundary()
        start_byte = reader.bit_pos // 8

        # Scan up to 4KB ahead looking for valid item flags + Huffman code
        db = get_item_type_db()
        for offset in range(0, 4096):
            probe_bit = (start_byte + offset) * 8
            if probe_bit + 80 > reader._total_bits:
                break

            # Quick check: read 53 bits as flags, then try Huffman
            save_pos = reader.bit_pos
            reader.seek_bit(probe_bit)
            try:
                # Skip 53 flag bits, try Huffman decode
                reader.read(53)
                code, _bits = decode_item_code(reader)
                # If we got a valid known item code, this is likely a real item
                if code and db.contains(code):
                    reader.seek_bit(probe_bit)
                    logger.info(
                        "Recovery: found valid item code '%s' at byte %d (skipped %d bytes)",
                        code,
                        start_byte + offset,
                        offset,
                    )
                    return True
            except Exception:
                pass
            reader.seek_bit(save_pos)

        return False

    def _read_null_terminated_string(self) -> str:
        """Read a null-terminated ASCII string from the bit stream.

        Used for personalized item names. [SPEC_ONLY] - not yet tested.

        Returns:
            Decoded string (without null terminator).
        """
        reader = self._require_reader()
        chars = []
        for _ in range(16):  # max 15 chars + null
            byte_val = reader.read(8)
            if byte_val == 0:
                break
            chars.append(chr(byte_val))
        return "".join(chars)


# ══════════════════════════════════════════════════════════════════════════
# Fast-path bulk header parser
# ══════════════════════════════════════════════════════════════════════════
#
# These functions are the fast path for character-select screens. They read
# only the first HEADER_SIZE_V105 (833) bytes of each .d2s file and decode
# just the CharacterHeader fields -- no Stats/Skills/Items/Mercs/Corpse
# sections are touched. No BitReader is instantiated, no Huffman decoding
# is performed, and no per-bit logging is emitted.
#
# Only load_charstats() needs to be called before using these APIs (for
# character_class_name lookup). The item/stat/skill game data loaders are
# NOT required.
#
# Performance target: <100 ms for 50 files on NVMe SSD.
# ══════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════
# Single-item re-parse from source_data bytes
# ══════════════════════════════════════════════════════════════════════════


# ── Quality-dispatch table population ────────────────────────────────────────
# Kept at module-tail so the mixin methods are defined. Dict values are
# unbound methods - the caller invokes them as reader_fn(self). Any class
# that inherits ItemsParserMixin (primarily D2SParser) gets the dispatch
# via attribute lookup, so the table doesn't need to reference the
# concrete subclass.
_QUALITY_READERS.update(
    {
        1: ItemsParserMixin._read_qsd_low,  # Low Quality
        2: ItemsParserMixin._read_qsd_normal,  # Normal
        3: ItemsParserMixin._read_qsd_superior,  # Superior
        4: ItemsParserMixin._read_qsd_magic,  # Magic
        5: ItemsParserMixin._read_qsd_set,  # Set
        6: ItemsParserMixin._read_qsd_rare_or_crafted,  # Rare
        7: ItemsParserMixin._read_qsd_unique,  # Unique
        8: ItemsParserMixin._read_qsd_rare_or_crafted,  # Crafted (same layout as Rare)
    }
)



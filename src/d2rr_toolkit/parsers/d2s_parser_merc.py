"""Mercenary section parser - mixin extracted from D2SParser.

Hosts:
  * ``_parse_mercenary_header`` - the 14-byte block at byte 0xA1
  * ``_parse_merc_section``     - the 'jf' section + merc items

Both rely on parser-owned state (``self._reader``, ``self._data``,
``self._corpse_jm_byte_offset``, ``self._skip_corpse_and_merc``) plus
item-parsing helpers inherited from other mixins
(``_parse_single_item``, ``_skip_inter_item_padding``). Byte-exact
golden diff is the safety gate.
"""

from __future__ import annotations

import logging
import struct
from typing import TYPE_CHECKING

from d2rr_toolkit.constants import (
    ITEM_BIT_HUFFMAN_START,
    OFFSET_MERC_CONTROL,
    OFFSET_MERC_DEAD,
    OFFSET_MERC_EXP,
    OFFSET_MERC_NAME_ID,
    OFFSET_MERC_TYPE,
    SECTION_MARKER_ITEMS,
)
from d2rr_toolkit.game_data.hireling import get_hireling_db
from d2rr_toolkit.game_data.item_types import get_item_type_db
from d2rr_toolkit.models.character import MercenaryHeader, ParsedItem
from d2rr_toolkit.parsers.huffman import decode_item_code

if TYPE_CHECKING:
    from collections.abc import Callable

    from d2rr_toolkit.parsers.bit_reader import BitReader

logger = logging.getLogger(__name__)


class MercenaryParserMixin:
    """Mixin providing ``_parse_mercenary_header`` + ``_parse_merc_section``.

    Expected parser-owned state:
      * ``self._reader: BitReader``
      * ``self._data: bytes``
      * ``self._corpse_jm_byte_offset: int | None``
      * ``self._skip_corpse_and_merc: bool`` (D2I tab parse shortcut)

    Side-effects it produces (used by the facade's ``parse`` method):
      * ``self._merc_items``
      * ``self._merc_jm_byte_offset``

    Requires inherited helpers from the items-parser mixin:
      * ``_parse_single_item``
      * ``_skip_inter_item_padding``
    """

    # Parser-owned state populated by D2SParser.__init__ / sibling mixins;
    # declaration-only (PEP 526) so mypy resolves self-attribute access
    # when the mixin is type-checked in isolation.
    _reader: "BitReader | None"
    _data: bytes
    _corpse_jm_byte_offset: int | None
    _merc_items: list[ParsedItem]
    _merc_jm_byte_offset: int | None
    _require_reader: "Callable[[], BitReader]"

    def _parse_mercenary_header(self) -> MercenaryHeader | None:
        """Parse the 14-byte mercenary header block starting at offset 0xA1.

        Layout (all LE):
            0xA1 u16 dead
            0xA3 u32 control_seed
            0xA7 u16 name_id
            0xA9 u16 type_id        (row index into hireling.txt)
            0xAB u32 experience

        Returns ``None`` if the character never hired a merc (the entire
        14-byte block is zero in that case - verified on all "no merc"
        test saves: TC01, TC08, TC18, TC62, TC41 et al.).

        Otherwise returns a :class:`MercenaryHeader` with the raw fields
        plus the hireling.txt-resolved class/subtype/difficulty. Name
        resolution happens via :mod:`d2rr_toolkit.display.merc_names` in
        a later pass (requires the localized string table).

        [BINARY_VERIFIED v105 TC49/TC55/TC56/TC63 - offsets validated
         against 5 saves spanning all 4 merc types.]
        """
        data = self._data
        if len(data) < OFFSET_MERC_EXP + 4:
            return None

        dead = struct.unpack_from("<H", data, OFFSET_MERC_DEAD)[0]
        control_seed = struct.unpack_from("<I", data, OFFSET_MERC_CONTROL)[0]
        name_id = struct.unpack_from("<H", data, OFFSET_MERC_NAME_ID)[0]
        type_id = struct.unpack_from("<H", data, OFFSET_MERC_TYPE)[0]
        experience = struct.unpack_from("<I", data, OFFSET_MERC_EXP)[0]

        # "No merc hired": the whole 14-byte block is zero. The control
        # seed is a random 32-bit number and is never zero for a real merc,
        # so its value alone is a reliable discriminator.
        if control_seed == 0 and dead == 0 and name_id == 0 and type_id == 0 and experience == 0:
            return None

        # Resolve hireling.txt row for display fields. If the DB is not
        # loaded (consumer chose to skip game-data loading) we still
        # return a MercenaryHeader with empty display fields - the raw
        # ids are the canonical truth.
        hdb = get_hireling_db()
        class_name = ""
        subtype = ""
        difficulty = 0
        version = 0
        base_level = 0
        if hdb.is_loaded():
            row = hdb.get_row(type_id)
            if row is not None:
                class_name = row.class_name
                subtype = row.subtype
                difficulty = row.difficulty
                version = row.version
                base_level = row.base_level

        resolved_name: str | None = None
        if hdb.is_loaded():
            resolved_name = hdb.resolve_merc_name(type_id, name_id)

        return MercenaryHeader(
            is_dead=bool(dead),
            control_seed=control_seed,
            name_id=name_id,
            type_id=type_id,
            experience=experience,
            hireling_class=class_name,
            hireling_subtype=subtype,
            hireling_difficulty=difficulty,
            hireling_version=version,
            hireling_base_level=base_level,
            resolved_name=resolved_name,
        )

    def _parse_merc_section(self) -> None:
        """Parse the 'jf' mercenary item section following the corpse JM.

        D2S file layout at this point:
            [jf(2)]                    mercenary section marker
            [JM(2)]                    merc item list marker (only if merc has items)
            [uint16 merc_count]
            [merc_count item blobs]    all equipped (socket children inline, counted)
            [kf(2)]                    next section (iron golem)

        If the character has no merc, 'jf' is followed directly by 'kf' and
        merc_count is effectively zero. Socket children of merc-equipped items
        are included in merc_count and parsed inline, same as player equipped
        items in the main JM list.

        Populates ``self._merc_items`` and ``self._merc_jm_byte_offset``.

        [BV feature/merc-items TC49/TC55/TC56]
        """
        reader = self._require_reader()
        self._merc_items = []
        self._merc_jm_byte_offset = None

        if getattr(self, "_skip_corpse_and_merc", False):
            return
        if self._corpse_jm_byte_offset is None:
            # 2nd JM was not found - don't try the merc section either.
            return

        if reader.bits_remaining < 16:
            return
        jf_marker = reader.peek_bytes(2)
        if jf_marker != b"jf":
            logger.warning(
                "Expected 'jf' marker at byte %d, found %s - skipping merc section.",
                reader.byte_pos,
                jf_marker.hex(),
            )
            return
        reader.read_bytes_raw(2)  # consume 'jf'

        # After 'jf', either the merc JM follows (merc has items) or the next
        # section marker 'kf' (no merc items, or no merc at all).
        if reader.bits_remaining < 16:
            return
        next2 = reader.peek_bytes(2)
        if next2 == b"kf":
            logger.info("No merc items (jf immediately followed by kf).")
            return
        if next2 != SECTION_MARKER_ITEMS:
            logger.warning(
                "Expected 'JM' or 'kf' after 'jf' marker at byte %d, found %s - "
                "skipping merc section.",
                reader.byte_pos,
                next2.hex(),
            )
            return

        self._merc_jm_byte_offset = reader.byte_pos
        reader.read_bytes_raw(2)  # consume 'JM'
        merc_count = reader.read_uint16_le()
        logger.info("Merc section: %d items at byte %d", merc_count, self._merc_jm_byte_offset)

        for i in range(merc_count):
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "Parsing merc item %d/%d at bit %d", i + 1, merc_count, reader.bit_pos
                )
            try:
                item = self._parse_single_item()  # type: ignore[attr-defined]
                if item.flags.location_id == 6 and self._merc_items:
                    self._merc_items[-1].socket_children.append(item)
                else:
                    self._merc_items.append(item)
                self._skip_inter_item_padding(item)  # type: ignore[attr-defined]
            except Exception as e:
                logger.warning(
                    "Parse failed on merc item %d/%d: %s - stopping merc parse.",
                    i + 1,
                    merc_count,
                    e,
                )
                break

        logger.info("Parsed %d of %d JM-counted merc items", len(self._merc_items), merc_count)

        # ── Extra merc items after JM count [BV] ──
        # Like the player item section, merc items can have additional items
        # stored AFTER the JM-counted items (socket children of stash items,
        # extra equipped items, etc.). Parse until the 'kf' marker is found.
        while reader.bits_remaining >= 80:
            if reader.peek_bytes(2) == b"kf":
                break

            probe_start = reader.bit_pos
            # Pre-validate: probe the Huffman code to check if this is a real item.
            try:
                reader.seek_bit(probe_start + ITEM_BIT_HUFFMAN_START)
                probe_code, _ = decode_item_code(reader)
                probe_valid = get_item_type_db().contains(probe_code)
            except Exception:
                probe_valid = False
            reader.seek_bit(probe_start)
            if not probe_valid:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "Merc extra item probe at bit %d: no valid item code - "
                        "end of merc item region, scanning to 'kf'.",
                        probe_start,
                    )
                # Skip remaining padding bytes to 'kf' marker.
                reader.skip_to_byte_boundary()
                while reader.bits_remaining >= 16:
                    if reader.peek_bytes(2) == b"kf":
                        break
                    reader.read(8)
                break

            try:
                item = self._parse_single_item()  # type: ignore[attr-defined]
                if item.flags.location_id == 6 and self._merc_items:
                    self._merc_items[-1].socket_children.append(item)
                else:
                    self._merc_items.append(item)
                logger.info(
                    "Extra merc item: %s (location=%d)",
                    item.item_code,
                    item.flags.location_id,
                )
                self._skip_inter_item_padding(item)  # type: ignore[attr-defined]
            except Exception as e:
                logger.warning(
                    "Extra merc item parse failed at bit %d: %s - stopping.",
                    probe_start,
                    e,
                )
                break

        if len(self._merc_items) > merc_count:
            logger.info(
                "Merc section: %d extra items after JM count (total: %d)",
                len(self._merc_items) - merc_count,
                len(self._merc_items),
            )


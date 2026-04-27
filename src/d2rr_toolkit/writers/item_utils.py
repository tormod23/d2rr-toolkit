"""Shared item binary utilities for D2S and D2I writers.

Provides bit-level write operations and item position patching used by
both the D2S writer (character files) and D2I writer (shared stash).
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from d2rr_toolkit.constants import HUFFMAN_TABLE
from d2rr_toolkit.exceptions import D2SWriteError

if TYPE_CHECKING:
    from d2rr_toolkit.models.character import ParsedItem


# ── Huffman encoder -----------------------------------------------------------
#
# Mirror of parsers/huffman.py's decoder. HUFFMAN_TABLE already maps
# char -> tree-path string where '0'/'1' characters denote the bit at each
# tree step in the order a decoder would read them. The on-disk bits are
# stored LSB-first within bytes, so the encoder must emit the table's
# string in the same order the decoder reads them - character by character,
# left-to-right within each character's bit string. Confirmed against
# TC61 r01 blob via manual decode. [BV]

_HUFFMAN_ENCODE: dict[str, tuple[int, ...]] = {
    ch: tuple(1 if c == "1" else 0 for c in bits) for ch, bits in HUFFMAN_TABLE.items()
}


def encode_huffman_code(code: str) -> list[int]:
    """Huffman-encode a type code + trailing space terminator into bits.

    Produces the LSB-first bit sequence ready for insertion into an
    item blob at bit position 53 (``ITEM_BIT_HUFFMAN_START``).

    Args:
        code: 3-character item code (e.g. ``"r01"``, ``"gmr"``). Trailing
              space is appended automatically so callers pass just the
              3-char code.

    Returns:
        List of 0/1 ints to write at successive bit positions.

    Raises:
        ValueError: if any character is not in the Huffman table.

    [BV] cross-verified against our own decoder on the r01 blob from TC61.
    """
    bits: list[int] = []
    for ch in code + " ":
        enc = _HUFFMAN_ENCODE.get(ch)
        if enc is None:
            # The Huffman alphabet covers exactly 36 glyphs: a-z, 0-9, space.
            # Common bugs: callers passing uppercase codes (e.g. "R01" instead
            # of "r01"), codes with underscore separators ("class_skill"),
            # or stale codes from non-Reimagined excel data. Fail loud rather
            # than emit silently-wrong bits.
            extra = ""
            if ch == "_":
                extra = (
                    " - underscore is NOT in the Huffman alphabet across "
                    "all known reference implementations; the input code "
                    "is likely from a non-binary table or has been "
                    "transformed before reaching the encoder."
                )
            elif ch.isupper():
                extra = (
                    " - the alphabet contains lowercase a-z only; the input "
                    "code may have been case-mangled."
                )
            raise ValueError(
                f"Character {ch!r} (in code {code!r}) has no Huffman "
                f"encoding.{extra} Valid glyphs: "
                f"{sorted(_HUFFMAN_ENCODE.keys())}"
            )
        bits.extend(enc)
    return bits


# ── Simple-item synthesis -----------------------------------------------------
#
# Layout of a simple item in D2R v105 (see parsers/d2s_parser_items.py
# _parse_simple_item and constants ITEM_BIT_*):
#
#   bit  4       identified flag = 1
#   bit 21       simple flag = 1
#   bit 23       "always-1" marker
#   bit 32, 34   "always-1" padding
#   bits 35-37   location_id (3 bits)
#   bits 38-41   equipped_slot (4 bits)
#   bits 42-45   position_x (4 bits)
#   bits 46-49   position_y (4 bits)
#   bits 50-52   panel_id (3 bits)
#   bits 53+     Huffman-encoded (3-char code + ' ')
#   next 1 bit   SIMPLE_ITEM_SOCKET_BIT_WIDTH (always 0 for non-socketed simples)
#   next 9 bits  quantity field (only when is_quantity_item is True).
#                Raw encoding: (display << 1) | 1  -- bit 0 is always 1.
#   pad          to byte boundary
#
# Verified against TC61 r01 blob (10 00 a0 00 05 08 f4 7c 7f 32 01, 11 bytes):
#   - 53+22 Huffman("r01 ")+1 socket_bit+9 qty = 85 bits, pad to 88 bits = 11 B [OK]
#   - qty raw=19 -> display=9 matches parsed ParsedItem.display_quantity [OK]
# [BV]


def synthesize_simple_item_blob(
    code: str,
    *,
    display_quantity: int = 1,
    is_quantity_item: bool | None = None,
    position_x: int = 0,
    position_y: int = 0,
    panel_id: int = 5,
    location_id: int = 0,
    equipped_slot: int = 0,
    identified: bool = True,
) -> bytes:
    """Build a simple-item byte blob from scratch (no source template needed).

    Intended for the rune cube-up feature and later gem synthesis. Emits
    bits in the exact game-written layout so both our parser and any
    other compliant D2R v105 reader can round-trip it.

    Args:
        code:              3-character item type code.
        display_quantity:  User-visible stack size (1..99). Only written when
                           ``is_quantity_item`` is True.
        is_quantity_item:  Whether to emit the 9-bit quantity field. If
                           ``None`` (default), autodetected from
                           item_types.txt via
                           :func:`get_item_type_db().is_quantity_item`.
                           Pass ``True`` / ``False`` to override.
        position_x/y:      Grid position (Section 5 ignores these but
                           the bits are written anyway; 0/0 is fine).
        panel_id:          5 = stash (Section 5 archive). [BV]
        location_id:       0 = stored. [BV]
        equipped_slot:     0 for Section 5 items. [BV]
        identified:        True for Section 5 items (always). [BV]

    Returns:
        Byte blob suitable for attaching to a freshly-constructed
        ``ParsedItem.source_data``.

    Raises:
        ValueError: if code has no Huffman encoding, display_quantity is
                    out of range, or any position / panel / slot value
                    exceeds its bit width.
    """
    if is_quantity_item is None:
        from d2rr_toolkit.game_data.item_types import get_item_type_db

        is_quantity_item = bool(get_item_type_db().is_quantity_item(code))

    if is_quantity_item:
        if not 1 <= display_quantity <= SECTION5_MAX_QUANTITY:
            raise ValueError(
                f"display_quantity {display_quantity} out of range "
                f"(1..{SECTION5_MAX_QUANTITY}) for Section 5 simple item."
            )
    if not 0 <= position_x < 16:
        raise ValueError(f"position_x {position_x} out of range (0..15)")
    if not 0 <= position_y < 16:
        raise ValueError(f"position_y {position_y} out of range (0..15)")
    if not 0 <= panel_id < 8:
        raise ValueError(f"panel_id {panel_id} out of range (0..7)")
    if not 0 <= location_id < 8:
        raise ValueError(f"location_id {location_id} out of range (0..7)")
    if not 0 <= equipped_slot < 16:
        raise ValueError(f"equipped_slot {equipped_slot} out of range (0..15)")

    huff_bits = encode_huffman_code(code)

    # Total bit count: 53 header + huffman + 1 socket bit + (9 qty if applicable)
    total_bits = 53 + len(huff_bits) + 1 + (9 if is_quantity_item else 0)
    total_bytes = (total_bits + 7) // 8
    buf = bytearray(total_bytes)

    # --- Header flags at fixed bit positions ---
    if identified:
        buf[0] |= 1 << 4  # bit 4 = identified
    buf[2] |= 1 << 5  # bit 21 = simple  [fixed]
    buf[2] |= 1 << 7  # bit 23 = always-1 marker  [BV]
    buf[4] |= 1 << 0  # bit 32 = always-1 marker  [BV]
    buf[4] |= 1 << 2  # bit 34 = always-1 marker  [BV]

    # --- Location / position fields ---
    write_bits(buf, ITEM_BIT_LOCATION, 3, location_id)
    write_bits(buf, ITEM_BIT_EQUIPPED, 4, equipped_slot)
    write_bits(buf, ITEM_BIT_POSITION_X, 4, position_x)
    write_bits(buf, ITEM_BIT_POSITION_Y, 4, position_y)
    write_bits(buf, ITEM_BIT_PANEL, 3, panel_id)

    # --- Huffman code at bit 53 ---
    pos = ITEM_BIT_HUFFMAN_START
    for b in huff_bits:
        if b:
            buf[pos >> 3] |= 1 << (pos & 7)
        pos += 1

    # --- Post-Huffman 1 bit (SIMPLE_ITEM_SOCKET_BIT_WIDTH, always 0 for runes) ---
    pos += 1  # write 0 - buf is already zero-filled

    # --- 9-bit quantity field (is_quantity_item only) ---
    if is_quantity_item:
        raw = (display_quantity << 1) | 1  # bit 0 always 1, bits 1-8 = display
        write_bits(buf, pos, 9, raw)
        pos += 9

    # Trailing bits beyond `pos` are already zero (buffer default), serving
    # as byte-alignment padding. No further work needed.

    return bytes(buf)


# Item flag bit positions within the item binary blob (LSB-first).
# These encode WHERE the item is stored (location, grid position, panel).
ITEM_BIT_LOCATION = 35  # 3 bits: 0=Stored, 1=Equipped, 2=Belt, 6=Socketed
ITEM_BIT_EQUIPPED = 38  # 4 bits: equipped slot (0=none, 1=head, etc.)
ITEM_BIT_POSITION_X = 42  # 4 bits: grid column
ITEM_BIT_POSITION_Y = 46  # 4 bits: grid row
ITEM_BIT_PANEL = 50  # 3 bits: panel/stash page

# Section 5 (Shared Stash Gems/Materials/Runes) quantity field widths.
# [BV]
#   Simple items:   9-bit field. Bit 0 = alignment/flag (always 1 in D2R v105).
#                   Bits 1-8 = display value (max 255, game caps at 99).
#                   Raw = (display << 1) | 1.  Display = raw >> 1.
#   Extended items: 7-bit field, direct display value (max 127, game caps at 99).
SIMPLE_QTY_WIDTH = 9
EXTENDED_QTY_WIDTH = 7
SECTION5_MIN_QUANTITY = 1  # minimum: 0 is rejected because the game treats 0-stacks as
# hidden-but-present "zombie" entries that still occupy the
# item_code slot (see project_section5_no_duplicates.md).
# Callers wanting to remove an item must drop it from the tab list.
SECTION5_MAX_QUANTITY = 99  # game-enforced cap per stack


def write_bits(buf: bytearray, bit_pos: int, width: int, value: int) -> None:
    """Write a value into a bytearray at a specific bit position (LSB-first).

    Fails fast with IndexError when the write range exceeds the buffer,
    preventing silent truncation or corruption of adjacent data.

    Args:
        buf: Mutable byte buffer.
        bit_pos: Starting bit offset (LSB-first).
        width: Number of bits to write.
        value: Value to write (only lowest `width` bits used).

    Raises:
        IndexError: If the write range (bit_pos .. bit_pos+width) exceeds
            the buffer. This indicates an upstream truncation of the
            item blob - the caller must fix the blob length, not suppress
            the error.
    """
    required_bytes = (bit_pos + width + 7) // 8
    if required_bytes > len(buf):
        raise IndexError(
            f"write_bits: buffer too small for requested write. "
            f"bit_pos={bit_pos}, width={width} -> requires {required_bytes} bytes, "
            f"but buffer has {len(buf)}. This usually means the source_data blob "
            f"was truncated upstream (check parser section clamping / parse_item_from_bytes)."
        )
    for i in range(width):
        byte_idx = (bit_pos + i) // 8
        bit_idx = (bit_pos + i) % 8
        if value & (1 << i):
            buf[byte_idx] |= 1 << bit_idx
        else:
            buf[byte_idx] &= ~(1 << bit_idx)


def patch_item_position(
    blob: bytes,
    position_x: int = 0,
    position_y: int = 0,
    panel_id: int = 5,
    location_id: int = 0,
    equipped_slot: int = 0,
) -> bytes:
    """Patch the position fields in an item's binary blob.

    Modifies bits 35-52 of the item blob to update location fields.
    Used when moving items between save files or between equipment slots.

    [BV]

    Args:
        blob: Original item binary blob.
        position_x: Target grid column (0-15).
        position_y: Target grid row (0-15).
        panel_id: Target panel (1=inventory, 4=cube, 5=stash).
        location_id: Location type (0=Stored, 1=Equipped, 2=Belt).
        equipped_slot: Equipment slot (0=none, 1-12 for equipped items).

    Returns:
        New blob with patched position fields.
    """
    data = bytearray(blob)

    write_bits(data, ITEM_BIT_LOCATION, 3, location_id)
    write_bits(data, ITEM_BIT_EQUIPPED, 4, equipped_slot)
    write_bits(data, ITEM_BIT_POSITION_X, 4, position_x)
    write_bits(data, ITEM_BIT_POSITION_Y, 4, position_y)
    write_bits(data, ITEM_BIT_PANEL, 3, panel_id)

    return bytes(data)


ITEM_BIT_PICKED_UP = 13  # Bit 13: "picked up since last save" - D2S only
ITEM_BIT_SIMPLE = 21  # Bit 21: simple (no extended header = no UID)
ITEM_BIT_HUFFMAN_START = 53
UID_WIDTH_BITS = 35  # unique_item_id width


def _get_uid_bit_position(blob: bytes) -> int | None:
    """Return the bit position of the unique_item_id within the blob.

    Returns None for simple items (flag bit 21 set) - those have no
    extended header and thus no UID.
    """
    if read_bits(blob, ITEM_BIT_SIMPLE, 1):
        return None
    from d2rr_toolkit.parsers.bit_reader import BitReader
    from d2rr_toolkit.parsers.huffman import decode_item_code

    reader = BitReader(blob)
    reader.seek_bit(ITEM_BIT_HUFFMAN_START)
    try:
        _code, huffman_bits = decode_item_code(reader)
    except Exception:
        return None
    return ITEM_BIT_HUFFMAN_START + huffman_bits


def read_unique_item_id(blob: bytes) -> int | None:
    """Read the 35-bit unique_item_id from an item blob, or None if simple."""
    pos = _get_uid_bit_position(blob)
    if pos is None:
        return None
    return read_bits(blob, pos, UID_WIDTH_BITS)


def write_unique_item_id(blob: bytes, new_uid: int) -> bytes:
    """Write a specific unique_item_id into an item blob.

    Returns the original blob unchanged if the item is simple (no UID).
    """
    pos = _get_uid_bit_position(blob)
    if pos is None:
        return blob
    data = bytearray(blob)
    write_bits(data, pos, UID_WIDTH_BITS, new_uid)
    return bytes(data)


def ensure_unique_uids(
    mutable_items: list["ParsedItem"],
    readonly_items: list["ParsedItem"] | None = None,
) -> int:
    """Guarantee that all unique_item_ids in the item set are distinct.

    D2R's anti-dupe system rejects save files containing two items
    with identical 35-bit unique_item_ids. This function walks every
    item (and its socket_children) in order, collects seen UIDs, and
    rerolls any collision with a cryptographically random value until
    it no longer collides. Simple items (no UID) are skipped.

    Rerolled UIDs are written back into the item's ``source_data``
    in-place so the writer's normal blob-copy path picks them up.
    Items without a collision retain their original UID - this keeps
    unchanged saves byte-stable for diffing and debugging.

    Args:
        mutable_items: Items whose UIDs may be rerolled on collision.
            Each item's ``socket_children`` are also processed.
        readonly_items: Items whose UIDs must be considered for
            collision detection but will NOT be rerolled (e.g. merc
            items in a D2S where the writer copies the merc section
            verbatim). Defaults to none. Processed first so that
            mutable items yield on collision with these.

    Returns:
        The number of UIDs that were rerolled (0 when no collisions).
    """
    seen: set[int] = set()
    rerolled = 0

    # Phase 1: seed the seen set with readonly UIDs (no mutation).
    if readonly_items:
        for item in readonly_items:
            if item.source_data is not None:
                uid = read_unique_item_id(item.source_data)
                if uid is not None:
                    seen.add(uid)
            for child in item.socket_children:
                if child.source_data is not None:
                    uid = read_unique_item_id(child.source_data)
                    if uid is not None:
                        seen.add(uid)

    # Phase 2: walk mutable items. Reroll any collision.
    def _process(item: "ParsedItem") -> None:
        nonlocal rerolled
        if item.source_data is None:
            return
        uid = read_unique_item_id(item.source_data)
        if uid is None:  # simple item, no UID
            return
        if uid in seen:
            # Collision - reroll until unique. With 2^35 values and
            # typically <1000 items per file, retries are negligible.
            while uid in seen:
                uid = secrets.randbits(UID_WIDTH_BITS)
            item.source_data = write_unique_item_id(item.source_data, uid)
            rerolled += 1
        seen.add(uid)

    for item in mutable_items:
        _process(item)
        for child in item.socket_children:
            _process(child)

    return rerolled


def reroll_unique_item_id(blob: bytes) -> bytes:
    """Generate a new random unique_item_id for a single item blob.

    Low-level helper that unconditionally rerolls without checking
    collisions against other items. Most callers should use
    :func:`ensure_unique_uids` on the final item set instead - the
    writer calls that automatically in build().
    """
    pos = _get_uid_bit_position(blob)
    if pos is None:
        return blob
    data = bytearray(blob)
    write_bits(data, pos, UID_WIDTH_BITS, secrets.randbits(UID_WIDTH_BITS))
    return bytes(data)


def clear_d2s_only_flags(blob: bytes) -> bytes:
    """Clear D2S-specific flags when writing items to D2I.

    Bit 13 ("picked up since last save") is set in D2S files but NEVER
    in D2I files. Verified across 2818 items: 0 D2I items have bit 13
    set, while D2S files commonly have it set on gems, runes, and rings.

    Must be called on every item blob written to a D2I section to avoid
    writing D2S-only metadata into the shared stash. [BV TC67]
    """
    data = bytearray(blob)
    write_bits(data, ITEM_BIT_PICKED_UP, 1, 0)
    return bytes(data)


def read_bits(data: bytes, bit_pos: int, width: int) -> int:
    """Read a `width`-bit value from a byte buffer at `bit_pos` (LSB-first)."""
    value = 0
    for i in range(width):
        byte_idx = (bit_pos + i) // 8
        bit_idx = (bit_pos + i) % 8
        if data[byte_idx] & (1 << bit_idx):
            value |= 1 << i
    return value


def _display_to_raw_quantity(item: "ParsedItem", new_display: int) -> int:
    """Convert a display quantity (what the user sees) to the raw bit value.

    Simple items:   raw = (display << 1) | (existing_lsb)
                    - the lowest bit is a flag/alignment artifact, preserved.
    Extended items: raw = display
                    - 7-bit field, direct value.

    Args:
        item:        ParsedItem whose source_data + quantity_bit_* metadata is
                     used to derive the current LSB (simple items only).
        new_display: Target display quantity (0..99 per Section 5 game cap).

    Returns:
        Raw bit-field value ready for write_bits().
    """
    if item.quantity_bit_offset is None:
        raise ValueError(
            f"Item '{item.item_code}' has no quantity metadata - parser did not "
            f"record a patchable quantity field. Was it parsed as stackable?"
        )
    if item.flags.simple:
        if item.quantity_bit_width != SIMPLE_QTY_WIDTH:
            raise D2SWriteError(
                f"Simple item {item.item_code!r} has quantity_bit_width="
                f"{item.quantity_bit_width}, expected {SIMPLE_QTY_WIDTH}. "
                f"Parser state is inconsistent with the write path."
            )
        if item.source_data is None:
            raise D2SWriteError(
                f"Simple item {item.item_code!r} lacks source_data; "
                f"patch_item_quantity cannot proceed - the quantity field "
                f"is patched IN the stored blob."
            )
        old_raw = read_bits(item.source_data, item.quantity_bit_offset, SIMPLE_QTY_WIDTH)
        lsb = old_raw & 1
        return ((new_display & 0xFF) << 1) | lsb
    # Extended: direct value
    if item.quantity_bit_width != EXTENDED_QTY_WIDTH:
        raise D2SWriteError(
            f"Extended item {item.item_code!r} has quantity_bit_width="
            f"{item.quantity_bit_width}, expected {EXTENDED_QTY_WIDTH}. "
            f"Parser state is inconsistent with the write path."
        )
    return new_display & 0x7F


def patch_item_quantity(item: "ParsedItem", new_display_quantity: int) -> bytes:
    """Return a copy of item.source_data with the quantity field patched.

    Validates: the item must have parsed quantity metadata, and the target
    value must fit in [SECTION5_MIN_QUANTITY, SECTION5_MAX_QUANTITY] = [1, 99].

    Quantity=0 is forbidden: the game silently keeps 0-stack entries in the
    file as hidden-but-present "zombie" items that still block their
    item_code slot against duplicates. To remove an item from Section 5,
    drop it from the tab's item list instead of setting its quantity to 0.
    [BV]

    Args:
        item:                 ParsedItem parsed from a .d2i (Section 5) or .d2s.
        new_display_quantity: New stack size (1-99 inclusive).

    Returns:
        New bytes blob (same length as item.source_data) with the quantity
        field overwritten. Original blob untouched.

    Raises:
        ValueError: if the item has no quantity metadata, or the target is
                    out of the 1..99 range, or source_data is missing.

    [BV]
    """
    if item.source_data is None:
        raise ValueError(f"Item '{item.item_code}' has no source_data.")
    if item.quantity_bit_offset is None:
        raise ValueError(
            f"Item '{item.item_code}' has no patchable quantity field "
            f"(not stackable, or parser did not record metadata)."
        )
    if not SECTION5_MIN_QUANTITY <= new_display_quantity <= SECTION5_MAX_QUANTITY:
        raise ValueError(
            f"Quantity {new_display_quantity} out of range "
            f"({SECTION5_MIN_QUANTITY}..{SECTION5_MAX_QUANTITY}) for Section 5. "
            f"To remove an item, drop it from the tab list; quantity=0 would "
            f"create a hidden zombie entry."
        )

    raw = _display_to_raw_quantity(item, new_display_quantity)
    buf = bytearray(item.source_data)
    write_bits(buf, item.quantity_bit_offset, item.quantity_bit_width, raw)
    return bytes(buf)


def clone_with_quantity(item: "ParsedItem", new_display_quantity: int) -> "ParsedItem":
    """Create a copy of the item with its quantity field set to a new value.

    This is the main public entry point for Section 5 writer operations:
    split a stack (clone twice with a+b=original), inject from DB (clone a
    template with the desired count), or resize an in-place entry.

    The returned item keeps the original's `quantity_bit_offset`,
    `quantity_bit_width`, and `flags`, so it can itself be cloned or patched
    again. The display `quantity` attribute is updated to the new raw value.

    Args:
        item:                 Source/template ParsedItem.
        new_display_quantity: Target display stack size (0-99).

    Returns:
        A new ParsedItem with patched source_data and updated quantity.

    [BV]
    """
    new_blob = patch_item_quantity(item, new_display_quantity)
    # model_copy preserves the pydantic field semantics including private-like
    # excluded fields; update the mutable fields we changed.
    raw_value = _display_to_raw_quantity(item, new_display_quantity)
    return item.model_copy(
        update={
            "source_data": new_blob,
            "quantity": raw_value,
        }
    )

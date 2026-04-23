"""Shared item binary utilities for D2S and D2I writers.

Provides bit-level write operations and item position patching used by
both the D2S writer (character files) and D2I writer (shared stash).
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from d2rr_toolkit.exceptions import D2SWriteError

if TYPE_CHECKING:
    from d2rr_toolkit.models.character import ParsedItem

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


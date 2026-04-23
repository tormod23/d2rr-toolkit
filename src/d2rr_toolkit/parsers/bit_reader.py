"""
LSB-first bit reader for D2S binary parsing.

This is the single most important class in the entire project.
ALL bit-level reads go through this class - never read bits inline.

Bit reading convention (confirmed [BV]):
  - Bytes are little-endian.
  - Bits within a byte are numbered 0 (LSB) to 7 (MSB).
  - Bit field N starts at byte N//8, bit offset N%8.
  - Multi-byte fields span naturally across byte boundaries.
  - NO bit-reversal is applied (spec claimed reversal was needed - it is not).

Example:
  data = [0b10110001]   (byte value 0xB1 = 177)
  bit 0 = 1 (LSB)
  bit 1 = 0
  bit 2 = 0
  bit 3 = 0
  bit 4 = 1
  bit 5 = 1
  bit 6 = 0
  bit 7 = 1 (MSB)
  read_bits(offset=0, count=4) = 0b0001 = 1  (bits 3,2,1,0 = 1,0,0,0 -> 0001)

Sources confirming this convention:
  - Trevin's v1.09 docs (original reference)
  - d2itemreader (squeek502)
  - [BV] stats decoded correctly with plain LSB-first
"""

from __future__ import annotations

import logging

from d2rr_toolkit.exceptions import BitReaderError

logger = logging.getLogger(__name__)


class BitReader:
    """LSB-first bit reader for D2S binary data.

    Maintains a current bit position and advances it with each read.
    Supports peek operations (read without advancing) for verification.

    All reads are [BV] to use plain LSB-first ordering
    with no byte-level bit reversal.

    Example usage:
        reader = BitReader(file_bytes, start_byte=907)
        identified = reader.read(1)    # read 1 bit
        location   = reader.read(3)    # read 3 bits
        item_code  = reader.decode_huffman()
    """

    def __init__(self, data: bytes, start_byte: int = 0) -> None:
        """Initialize the BitReader.

        Args:
            data:       Raw file bytes (the entire file or a slice).
            start_byte: Byte offset to begin reading from.
                        The bit position is set to start_byte * 8.
        """
        self._data = data
        self._bit_pos: int = start_byte * 8
        self._total_bits: int = len(data) * 8

    # ──────────────────────────────────────────────────────────
    # Position properties
    # ──────────────────────────────────────────────────────────

    @property
    def bit_pos(self) -> int:
        """Current bit position (absolute, from byte 0)."""
        return self._bit_pos

    @property
    def byte_pos(self) -> int:
        """Current byte position (bit_pos // 8)."""
        return self._bit_pos // 8

    @property
    def bit_offset_in_byte(self) -> int:
        """Bit offset within the current byte (bit_pos % 8)."""
        return self._bit_pos % 8

    @property
    def bits_remaining(self) -> int:
        """Number of bits remaining in the data."""
        return self._total_bits - self._bit_pos

    # ──────────────────────────────────────────────────────────
    # Core read operations
    # ──────────────────────────────────────────────────────────

    def read(self, count: int) -> int:
        """Read `count` bits LSB-first and advance the bit position.

        Args:
            count: Number of bits to read (1-64 recommended).

        Returns:
            Unsigned integer value of the read bits.

        Raises:
            BitReaderError: If reading would go past end of data.

        Verification:
            [BV] LSB-first ordering confirmed.
            Stats section decoded correctly with this method: Str=30, Dex=20, etc.
        """
        if count <= 0:
            raise BitReaderError(f"count must be positive, got {count}", self._bit_pos)
        if self._bit_pos + count > self._total_bits:
            raise BitReaderError(
                f"Attempted to read {count} bits but only {self.bits_remaining} remain",
                self._bit_pos,
            )

        result = self._read_bits_at(self._bit_pos, count)
        # Hot-path trace: guard against formatting cost when DEBUG disabled.
        # Without the guard this format string is built on every read call
        # (thousands per item, tens of thousands per character), causing
        # significant CPU and I/O overhead even when logging is off.
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "read(%d bits) at bit %d (byte 0x%04X): value=%d (0x%X)",
                count,
                self._bit_pos,
                self._bit_pos // 8,
                result,
                result,
            )
        self._bit_pos += count
        return result

    def read_signed(self, count: int) -> int:
        """Read `count` bits as a two's-complement signed integer.

        Args:
            count: Number of bits to read.

        Returns:
            Signed integer value.
        """
        value = self.read(count)
        if value >= (1 << (count - 1)):
            value -= 1 << count
        return value

    def peek(self, count: int) -> int:
        """Read `count` bits WITHOUT advancing the bit position.

        Use for lookahead and verification checks.

        Args:
            count: Number of bits to peek.

        Returns:
            Unsigned integer value (bit position unchanged).
        """
        if self._bit_pos + count > self._total_bits:
            raise BitReaderError(
                f"Attempted to peek {count} bits but only {self.bits_remaining} remain",
                self._bit_pos,
            )
        return self._read_bits_at(self._bit_pos, count)

    def peek_bytes(self, count: int) -> bytes:
        """Peek at the next `count` bytes (must be byte-aligned).

        Used for section marker verification (e.g. checking for b'gf').

        Args:
            count: Number of bytes to peek.

        Returns:
            Bytes object with the peeked data.
        """
        byte_offset = self._bit_pos // 8
        return self._data[byte_offset : byte_offset + count]

    def read_bytes_raw(self, count: int) -> bytes:
        """Read `count` complete bytes (must be byte-aligned).

        This is a fast path for reading byte-aligned multi-byte fields.

        Args:
            count: Number of bytes to read.

        Returns:
            Bytes object.

        Raises:
            BitReaderError: If not byte-aligned or insufficient data.
        """
        if self._bit_pos % 8 != 0:
            raise BitReaderError(
                f"read_bytes_raw requires byte alignment, "
                f"but current bit offset within byte is {self.bit_offset_in_byte}",
                self._bit_pos,
            )
        byte_offset = self._bit_pos // 8
        result = self._data[byte_offset : byte_offset + count]
        if len(result) < count:
            raise BitReaderError(
                f"Requested {count} bytes but only {len(result)} available",
                self._bit_pos,
            )
        self._bit_pos += count * 8
        return result

    def read_uint8(self) -> int:
        """Read one unsigned byte (byte-aligned fast path)."""
        return self.read_bytes_raw(1)[0]

    def read_uint16_le(self) -> int:
        """Read a little-endian uint16 (byte-aligned fast path)."""
        raw = self.read_bytes_raw(2)
        return int.from_bytes(raw, "little")

    def read_uint32_le(self) -> int:
        """Read a little-endian uint32 (byte-aligned fast path)."""
        raw = self.read_bytes_raw(4)
        return int.from_bytes(raw, "little")

    def skip_to_byte_boundary(self) -> int:
        """Advance bit position to the next byte boundary.

        Used after simple items to align for the next item.

        Returns:
            Number of bits skipped (0-7).
        """
        remainder = self._bit_pos % 8
        if remainder == 0:
            return 0
        skip = 8 - remainder
        self._bit_pos += skip
        return skip

    # ──────────────────────────────────────────────────────────
    # Position management
    # ──────────────────────────────────────────────────────────

    def seek_bit(self, bit_pos: int) -> None:
        """Jump to an absolute bit position.

        Use sparingly - prefer sequential reading.
        Needed for jumping to known section starts (e.g. stats at bit 833*8).

        Args:
            bit_pos: Absolute bit position to seek to.
        """
        if bit_pos < 0 or bit_pos > self._total_bits:
            raise BitReaderError(
                f"Seek to bit {bit_pos} out of range [0, {self._total_bits}]",
                self._bit_pos,
            )
        self._bit_pos = bit_pos

    def seek_byte(self, byte_pos: int) -> None:
        """Jump to a byte offset (sets bit position to byte_pos * 8).

        Args:
            byte_pos: Absolute byte offset to seek to.
        """
        self.seek_bit(byte_pos * 8)

    def save_position(self) -> int:
        """Save the current bit position for later restore.

        Returns:
            Current bit position.
        """
        return self._bit_pos

    def restore_position(self, saved: int) -> None:
        """Restore a previously saved bit position.

        Args:
            saved: Bit position returned by save_position().
        """
        self._bit_pos = saved

    # ──────────────────────────────────────────────────────────
    # Internal implementation
    # ──────────────────────────────────────────────────────────

    def _read_bits_at(self, start_bit: int, count: int) -> int:
        """Read bits at an absolute position without changing _bit_pos.

        This is the core implementation used by read() and peek().
        Uses the [BV] LSB-first ordering.

        Args:
            start_bit: Absolute bit offset from byte 0.
            count:     Number of bits to read.

        Returns:
            Unsigned integer value.
        """
        result = 0
        for i in range(count):
            byte_idx = (start_bit + i) // 8
            bit_idx = (start_bit + i) % 8
            if (self._data[byte_idx] >> bit_idx) & 1:
                result |= 1 << i
        return result

    # ──────────────────────────────────────────────────────────
    # Diagnostic helpers
    # ──────────────────────────────────────────────────────────

    def hex_context(self, before_bytes: int = 2, after_bytes: int = 6) -> str:
        """Return a hex string of bytes around the current position.

        Useful for error messages and debugging.

        Args:
            before_bytes: Bytes to show before current position.
            after_bytes:  Bytes to show after current position.

        Returns:
            Human-readable hex context string.
        """
        start = max(0, self.byte_pos - before_bytes)
        end = min(len(self._data), self.byte_pos + after_bytes)
        chunk = self._data[start:end]
        hex_str = " ".join(f"{b:02X}" for b in chunk)
        ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        cursor_pos = self.byte_pos - start
        pointer = "   " * cursor_pos + "^^"
        return (
            f"byte 0x{self.byte_pos:04X} (bit {self._bit_pos})\n"
            f"  {hex_str}  |{ascii_str}|\n"
            f"  {pointer}"
        )

    def __repr__(self) -> str:
        return (
            f"BitReader(bit_pos={self._bit_pos}, "
            f"byte_pos=0x{self.byte_pos:04X}, "
            f"bits_remaining={self.bits_remaining})"
        )


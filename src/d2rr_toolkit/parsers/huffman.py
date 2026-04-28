"""
Huffman decoder for D2R item codes.

In D2R (v97+), item type codes are Huffman-encoded instead of plain
4-character ASCII. This is a major change from classic Diablo 2.

Verification status:
  - Table source: d07riv Phrozen Keep post
  - Bit offset (53) confirmed: [BV]-TC10
  - Space terminator (code '10'): [BV]
  - Confirmed item codes: hp1, stu, qui, lgl, ssd

The Huffman tree is built once at module load and reused for all decodes.
Each character in the item code is decoded by traversing the tree bit-by-bit
(LSB-first) until a leaf node (character) is reached. The process repeats
until the space character (terminator) is decoded.

Item codes are typically 3-4 characters (e.g. 'hp1', 'stu', 'r01', 'lgl').
"""

from dataclasses import dataclass, field

from d2rr_toolkit.constants import HUFFMAN_TABLE
from d2rr_toolkit.exceptions import HuffmanDecodeError
from d2rr_toolkit.parsers.bit_reader import BitReader


# ── Huffman Tree Node ────────────────────────────────────────


@dataclass(slots=True)
class _HuffmanNode:
    """Internal node or leaf in the Huffman decoding tree."""

    children: dict[int, _HuffmanNode] = field(default_factory=dict)
    character: str | None = None

    @property
    def is_leaf(self) -> bool:
        """True if this node represents a decoded character."""
        return self.character is not None


# ── Tree Construction ────────────────────────────────────────


def _build_tree(table: dict[str, str]) -> _HuffmanNode:
    """Build the Huffman decoding tree from the code table.

    Each entry in the table maps a character to its bit pattern string.
    The pattern is read left-to-right, where each character ('0' or '1')
    represents a branch direction in the tree.

    This left-to-right order corresponds to LSB-first reading from the file
    (the first bit read from the file = the leftmost character in the pattern).

    Args:
        table: Dict mapping characters to their bit pattern strings.

    Returns:
        Root node of the Huffman decoding tree.
    """
    root = _HuffmanNode()
    for char, pattern in table.items():
        node = root
        for bit_char in pattern:
            bit = int(bit_char)
            if bit not in node.children:
                node.children[bit] = _HuffmanNode()
            node = node.children[bit]
        node.character = char
    return root


# Module-level singleton tree - built once, reused for all decodes.
# [BV] table from d07riv, confirmed TC01-TC10.
_HUFFMAN_ROOT: _HuffmanNode = _build_tree(HUFFMAN_TABLE)


# ── Public Decoder ───────────────────────────────────────────


def decode_item_code(reader: BitReader, max_chars: int = 8) -> tuple[str, int]:
    """Decode a Huffman-encoded item code from the bit stream.

    Reads bits one at a time, traversing the Huffman tree until a leaf
    node is reached. Repeats until the space character (terminator) is
    decoded. The space character is NOT included in the returned code.

    Args:
        reader:    BitReader positioned at the start of the item code.
                   [BV] This should be at item-relative bit 53.
        max_chars: Safety limit on decoded characters (default 8).
                   Real item codes are 3-4 chars; 8 provides safety margin.

    Returns:
        Tuple of (item_code, bits_consumed) where:
          - item_code:     The decoded item code string (e.g. 'hp1', 'lgl').
          - bits_consumed: Total bits read including the space terminator.

    Raises:
        HuffmanDecodeError: If the bit stream does not produce a valid code
                            within max_chars characters or 80 bits.

    Example:
        reader = BitReader(data, start_byte=907)
        reader.seek_bit(reader.bit_pos + 53)  # skip flag bits
        code, bits = decode_item_code(reader)
        # code = 'hp1', bits = 19

    Verification:
        [BV] Offset 53, table from d07riv, confirmed TC01-TC10.
        TC01: 'hp1' (19 bits), TC08: 'lgl' (17 bits), TC09: 'ssd' (16 bits).
    """
    start_bit = reader.bit_pos
    node: _HuffmanNode = _HUFFMAN_ROOT
    chars: list[str] = []
    bits_consumed = 0
    max_bits = (max_chars + 1) * 9  # generous upper bound

    while bits_consumed < max_bits:
        bit = reader.read(1)
        bits_consumed += 1

        if bit not in node.children:
            raise HuffmanDecodeError(start_bit, bits_consumed)

        node = node.children[bit]

        if node.is_leaf:
            assert node.character is not None
            if node.character == " ":
                # Space = terminator, decoding complete
                return ("".join(chars), bits_consumed)
            chars.append(node.character)
            node = _HUFFMAN_ROOT  # reset to root for next character

            if len(chars) > max_chars:
                raise HuffmanDecodeError(start_bit, bits_consumed)

    raise HuffmanDecodeError(start_bit, bits_consumed)


def is_valid_item_code(code: str) -> bool:
    """Check if a decoded string looks like a plausible D2 item code.

    This is a structural check only - it does not verify the code against
    game data files. Use item type loaders for full validation.

    Valid item codes are 2-4 alphanumeric characters (letters and digits).

    Args:
        code: Decoded string to check.

    Returns:
        True if the string matches the expected pattern.
    """
    return 2 <= len(code) <= 4 and all(c.isalnum() or c == "_" for c in code)

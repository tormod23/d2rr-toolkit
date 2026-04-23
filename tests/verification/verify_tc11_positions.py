"""
tests/verification/verify_tc11_positions.py
============================================
PURPOSE : Findet die echten Bit-Positionen von gmd und stu in TC11
          durch direkten Binary-Scan. Keine Annahmen über Item-Struktur.

          Scannt JEDEN Bit ab items_start und dekodiert Huffman.
          Zeigt alle Positionen wo 'stu' oder 'gmd' mit richtigen Flags auftaucht.

          Außerdem: zeigt die RAW-BITS von Item #1 (gmd) für manuelle Analyse.

USAGE   : python tests/verification/verify_tc11_positions.py tests/cases/TC11/TestWarlock.d2s
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")


def read_bits(data, start_bit, count):
    result = 0
    for i in range(count):
        byte_idx = (start_bit + i) // 8
        bit_idx = (start_bit + i) % 8
        if byte_idx < len(data) and (data[byte_idx] >> bit_idx) & 1:
            result |= 1 << i
    return result


def bits_str(data, start_bit, count):
    return " ".join(str(read_bits(data, start_bit + i, 1)) for i in range(count))


HUFFMAN_TABLE = {
    " ": "10",
    "0": "11111011",
    "1": "1111100",
    "2": "001100",
    "3": "1101101",
    "4": "11111010",
    "5": "00010110",
    "6": "1101111",
    "7": "01111",
    "8": "000100",
    "9": "01110",
    "a": "11110",
    "b": "0101",
    "c": "01000",
    "d": "110001",
    "e": "110000",
    "f": "010011",
    "g": "11010",
    "h": "00011",
    "i": "1111110",
    "j": "000101110",
    "k": "010010",
    "l": "11101",
    "m": "01101",
    "n": "001101",
    "o": "1111111",
    "p": "11001",
    "q": "11011001",
    "r": "11100",
    "s": "0010",
    "t": "01100",
    "u": "00001",
    "v": "1101110",
    "w": "00000",
    "x": "00111",
    "y": "0001010",
    "z": "11011000",
}


def build_tree():
    root = {}
    for char, pattern in HUFFMAN_TABLE.items():
        node = root
        for b in pattern[:-1]:
            node = node.setdefault(b, {})
        node[pattern[-1]] = char
    return root


TREE = build_tree()


def decode_huffman(data, start_bit):
    node = TREE
    result = []
    bits = 0
    while bits < 80:
        b = read_bits(data, start_bit + bits, 1)
        bits += 1
        bc = str(b)
        if bc not in node:
            return None, bits
        node = node[bc]
        if isinstance(node, str):
            if node == " ":
                return "".join(result), bits
            result.append(node)
            node = TREE
    return None, bits


if len(sys.argv) < 2:
    print("Usage: python verify_tc11_positions.py <TestWarlock.d2s>")
    sys.exit(1)

data = Path(sys.argv[1]).read_bytes()
print(f"Datei: {sys.argv[1]} ({len(data)} bytes)\n")

# Find items start
gf_pos = data.find(b"gf")
jm_pos = data.find(b"JM", gf_pos)
item_count = int.from_bytes(data[jm_pos + 2 : jm_pos + 4], "little")
items_start = (jm_pos + 4) * 8
print(f"JM bei Byte {jm_pos}, {item_count} Items, items_start = bit {items_start}\n")

# ── TEIL 1: Raw bits of first item ──────────────────────────────────────────
print("═" * 65)
print("TEIL 1: RAW BITS von Item #1 (erste 80 Bits ab items_start)")
print("═" * 65)
print()
pos = items_start
for row in range(0, 80, 8):
    abs_bit = pos + row
    raw = bits_str(data, abs_bit, min(8, 80 - row))
    uint8 = read_bits(data, abs_bit, min(8, 80 - row))
    annots = []
    if row == 4:
        annots.append("<- bit 4 (identified)")
    if row == 11:
        annots.append("<- bit 11 (socketed)")
    if row == 17:
        annots.append("<- bit 17 (starter)")
    if row == 21:
        annots.append("<- bit 21 (SIMPLE)")
    if row == 53:
        annots.append("<- bit 53 (Huffman start)")
    print(f"  bit {pos+row:5d} (+{row:3d}): {raw:<24} uint={uint8:3d}  {'  '.join(annots)}")

# Specific flag bits
print()
print(f"  Bit  4 (identified): {read_bits(data, pos+4, 1)}")
print(f"  Bit 11 (socketed):   {read_bits(data, pos+11, 1)}")
print(f"  Bit 21 (SIMPLE):     {read_bits(data, pos+21, 1)}")
code1, hbits1 = decode_huffman(data, pos + 53)
print(f"  Huffman at +53: '{code1}' ({hbits1} bits)")

# ── TEIL 2: Scan for stu and gmd with correct flags ─────────────────────────
print()
print("═" * 65)
print("TEIL 2: Scan für 'stu' und 'gmd' ab items_start")
print("═" * 65)
print()
print(
    f"  {'Bit':>7}  {'Byte':>6}  {'Code':<6}  {'loc':>4}  {'panel':>6}  {'px,py':>6}  {'ident':>5}  {'simple':>7}"
)
print(f"  {'─'*7}  {'─'*6}  {'─'*6}  {'─'*4}  {'─'*6}  {'─'*6}  {'─'*5}  {'─'*7}")

gmd_positions = []
stu_positions = []

# Only scan byte-aligned positions for efficiency
for bit in range(items_start, min(items_start + 4000, len(data) * 8 - 53)):
    code, hbits = decode_huffman(data, bit + 53)
    if code not in ("gmd", "stu", "ooc", "oos"):
        continue
    loc = read_bits(data, bit + 35, 3)
    panel = read_bits(data, bit + 50, 3)
    px = read_bits(data, bit + 42, 4)
    py = read_bits(data, bit + 46, 4)
    ident = read_bits(data, bit + 4, 1)
    simp = read_bits(data, bit + 21, 1)
    byte_align = "[OK]" if bit % 8 == 0 else f"*(+{bit%8})"
    print(
        f"  {bit:>7}  {bit//8:>6}  {code:<6}  {loc:>4}  {panel:>6}  ({px},{py})   {ident:>5}  {simp:>7}  {byte_align}"
    )
    if code == "gmd":
        gmd_positions.append(bit)
    if code == "stu":
        stu_positions.append(bit)

print()
print(f"  gmd positions (byte-aligned only): {[b for b in gmd_positions if b%8==0]}")
print(f"  stu positions (byte-aligned only): {[b for b in stu_positions if b%8==0]}")

# ── TEIL 3: Expected vs actual ───────────────────────────────────────────────
print()
print("═" * 65)
print("TEIL 3: Erwartete Reihenfolge vs tatsächliche Positionen")
print("═" * 65)
print()
print("  Aus README erwartet:")
print("  1. gmd Inventory(0,0)")
print("  2. stu Inventory(1,0) [empty socket]")
print("  3. gmd Inventory(3,0)")
print("  4. stu Inventory(4,0) [filled socket]")
print("  5. gmd Inventory(6,0)")
print("  (+1 gmd socketed child)")
print()
print("  Tatsächliche byte-aligned Positionen:")

# Find items at specific expected positions
expected = [
    ("gmd", 0, 1, 0, 0, "gmd Inventory(0,0)"),
    ("stu", 0, 1, 1, 0, "stu Inventory(1,0)"),
    ("gmd", 0, 1, 3, 0, "gmd Inventory(3,0)"),
    ("stu", 0, 1, 4, 0, "stu Inventory(4,0)"),
    ("gmd", 0, 1, 6, 0, "gmd Inventory(6,0)"),
]

for scan_bit in range(items_start, min(items_start + 4000, len(data) * 8 - 53)):
    code, _ = decode_huffman(data, scan_bit + 53)
    if code not in ("gmd", "stu"):
        continue
    if scan_bit % 8 != 0:
        continue
    loc = read_bits(data, scan_bit + 35, 3)
    panel = read_bits(data, scan_bit + 50, 3)
    px = read_bits(data, scan_bit + 42, 4)
    py = read_bits(data, scan_bit + 46, 4)
    ident = read_bits(data, scan_bit + 4, 1)
    for exp_code, exp_loc, exp_panel, exp_px, exp_py, desc in expected:
        if (
            code == exp_code
            and loc == exp_loc
            and panel == exp_panel
            and px == exp_px
            and py == exp_py
        ):
            prev = None
            # find previous entry
            print(f"  [OK] {desc:<30} -> bit {scan_bit} (byte {scan_bit//8})")

# ── TEIL 4: Gaps between items ───────────────────────────────────────────────
print()
print("═" * 65)
print("TEIL 4: Abstände zwischen den gefundenen byte-aligned Items")
print("═" * 65)
all_found = []
for scan_bit in range(items_start, min(items_start + 4000, len(data) * 8 - 53)):
    code, _ = decode_huffman(data, scan_bit + 53)
    if code not in ("gmd", "stu"):
        continue
    if scan_bit % 8 != 0:
        continue
    loc = read_bits(data, scan_bit + 35, 3)
    panel = read_bits(data, scan_bit + 50, 3)
    px = read_bits(data, scan_bit + 42, 4)
    py = read_bits(data, scan_bit + 46, 4)
    simp = read_bits(data, scan_bit + 21, 1)
    sock = read_bits(data, scan_bit + 11, 1)
    all_found.append((scan_bit, code, loc, panel, px, py, simp, sock))

all_found.sort()
prev_bit = None
for bit, code, loc, panel, px, py, simp, sock in all_found:
    loc_str = f"({px},{py})" if loc == 0 else f"loc={loc}"
    if prev_bit:
        diff = bit - prev_bit
        print(
            f"  bit {bit:6d}: '{code}' {loc_str:<8} simp={simp} sock={sock}  Δ={diff} bits ({diff//8} bytes + {diff%8} bits)"
        )
    else:
        print(f"  bit {bit:6d}: '{code}' {loc_str:<8} simp={simp} sock={sock}  (first)")
    prev_bit = bit

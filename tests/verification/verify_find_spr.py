"""
tests/verification/verify_find_spr.py
======================================
PURPOSE : Findet durch Binary-Analyse den exakten Startbit des Vicious Spear (spr)
          in TC01. Scannt ab bit 7850 nach einem Item mit:
          - code='spr'
          - location=Inventory (panel=1, px=1, py=0)
          - identified=1
          - quality=Magic (qual=4)

USAGE   : python tests/verification/verify_find_spr.py tests/cases/TC01/TestABC.d2s
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
    print("Usage: python verify_find_spr.py <d2s_file>")
    sys.exit(1)

data = Path(sys.argv[1]).read_bytes()
print(f"Datei: {sys.argv[1]} ({len(data)} bytes)\n")

# Scan from bit 7860 to 8200 for valid spr item start
print("Scanning für spr-Item mit korrekten Flags...")
print(
    f"\n{'Bit':>7}  {'Code':<6}  {'loc':>4}  {'panel':>6}  {'px,py':>6}  {'ident':>6}  {'qual':>5}  Match?"
)
print(f"{'─'*7}  {'─'*6}  {'─'*4}  {'─'*6}  {'─'*6}  {'─'*6}  {'─'*5}  {'─'*20}")

for bit in range(7860, 8200):
    code, hbits = decode_huffman(data, bit + 53)
    if code != "spr":
        continue

    loc = read_bits(data, bit + 35, 3)
    panel = read_bits(data, bit + 50, 3)
    px = read_bits(data, bit + 42, 4)
    py = read_bits(data, bit + 46, 4)
    ident = read_bits(data, bit + 4, 1)
    simp = read_bits(data, bit + 21, 1)
    qual_raw = read_bits(data, bit + 53 + hbits + 42, 4) if not simp else 0

    is_inventory = loc == 0 and panel == 1 and px == 1 and py == 0
    is_ident = ident == 1

    match = ""
    if is_inventory and is_ident:
        match = "*** PERFECT MATCH ***"
    elif code == "spr":
        match = "code=spr [OK]"

    print(
        f"{bit:>7}  {code:<6}  {loc:>4}  {panel:>6}  ({px},{py}):>5  {ident:>6}  {qual_raw:>5}  {match}"
    )

print()
print("─" * 60)
print("Auch: Suche nach 'cb' mit Inventory(1,0) identified:")
print(
    f"\n{'Bit':>7}  {'Code':<6}  {'loc':>4}  {'panel':>6}  {'px,py':>6}  {'ident':>6}  {'qual':>5}"
)
for bit in range(7860, 8200):
    code, hbits = decode_huffman(data, bit + 53)
    if code not in ("cb", "spr"):
        continue
    loc = read_bits(data, bit + 35, 3)
    panel = read_bits(data, bit + 50, 3)
    px = read_bits(data, bit + 42, 4)
    py = read_bits(data, bit + 46, 4)
    ident = read_bits(data, bit + 4, 1)
    qual_raw = read_bits(data, bit + 53 + hbits + 42, 4)
    annot = ""
    if loc == 0 and panel == 1 and px == 1 and py == 0 and ident == 1:
        annot = "<- INVENTORY(1,0) IDENTIFIED!"
    print(
        f"{bit:>7}  {code:<6}  {loc:>4}  {panel:>6}  ({px},{py})  {ident:>6}  {qual_raw:>5}  {annot}"
    )

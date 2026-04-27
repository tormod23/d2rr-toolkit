"""
tests/verification/verify_find_tc03_items.py
=============================================
PURPOSE : Findet die tatsächlichen Startbits ALLER TC03 Items durch Binary-Scan.
          Sucht nach jedem bekannten Item-Code aus der README mit den richtigen Flags.

USAGE   : python tests/verification/verify_find_tc03_items.py tests/cases/TC03/TestWarlock.d2s
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


LOCATION_NAMES = {0: "Stored", 1: "Equipped", 2: "Belt", 4: "Cursor", 6: "Socketed"}
PANEL_NAMES = {0: "None", 1: "Inventory", 4: "Cube", 5: "Stash"}

# Expected items from TC03 README (code, location, panel, px, py, slot, ident)
# location: 1=Equipped, 0=Stored
# panel: 0=none(equipped), 1=inventory, 5=stash
EXPECTED_ITEMS = [
    # Equipped items (location=1, various slots)
    ("skp", 1, 0, 0, 0, 1, 1, "Head slot 1"),
    ("amu", 1, 0, 0, 0, 2, 1, "Amulet slot 2"),  # amulet code
    ("qui", 1, 0, 0, 0, 3, 1, "Torso slot 3"),
    ("spc", 1, 0, 0, 0, 4, 1, "Right Hand slot 4"),
    ("buc", 1, 0, 0, 0, 5, 1, "Left Hand slot 5"),
    ("rin", 1, 0, 0, 0, 6, 1, "Right Ring slot 6"),
    ("rin", 1, 0, 0, 0, 7, 1, "Left Ring slot 7"),
    ("vbl", 1, 0, 0, 0, 8, 1, "Belt slot 8"),
    ("lbt", 1, 0, 0, 0, 9, 1, "Boots slot 9"),
    ("lgl", 1, 0, 0, 0, 10, 1, "Gloves slot 10"),
    # Inventory (location=0, panel=1)
    ("stu", 0, 1, 0, 0, 0, 1, "Inventory (0,0)"),
    ("ooc", 0, 1, 9, 0, 0, 1, "Inventory (9,0)"),
    ("gmd", 0, 1, 0, 7, 0, 1, "Inventory (0,7)"),
    ("oos", 0, 1, 9, 7, 0, 1, "Inventory (9,7)"),
    # Stash (location=0, panel=5)
    ("gmk", 0, 5, 0, 0, 0, 1, "Stash (0,0)"),
    ("ooc", 0, 5, 15, 0, 0, 1, "Stash (15,0)"),
    ("rup", 0, 5, 4, 1, 0, 1, "Stash (4,1)"),
    ("ooa", 0, 5, 6, 1, 0, 1, "Stash (6,1)"),
    ("1gc", 0, 5, 5, 2, 0, 1, "Stash (5,2)"),
    ("ooi", 0, 5, 4, 3, 0, 1, "Stash (4,3)"),
    ("jwp", 0, 5, 6, 3, 0, 1, "Stash (6,3)"),
    ("oor", 0, 5, 12, 9, 0, 1, "Stash (12,9)"),
    ("ooe", 0, 5, 0, 12, 0, 1, "Stash (0,12)"),
    ("ka3", 0, 5, 15, 12, 0, 1, "Stash (15,12)"),
]

# Also: amulet code might be 'amu' not a named item
# Let me check: Eye of Kahn is a Unique Amulet - code 'amu'

if len(sys.argv) < 2:
    print("Usage: python verify_find_tc03_items.py <TestWarlock.d2s>")
    sys.exit(1)

data = Path(sys.argv[1]).read_bytes()
print(f"Datei: {sys.argv[1]} ({len(data)} bytes)\n")

# Scan range: items start at byte 925, file ends at byte 1434
SCAN_FROM = 925 * 8
SCAN_TO = len(data) * 8 - 53

print(f"Scanning von bit {SCAN_FROM} bis {SCAN_TO}...")
print()

# Build a map: bit_position -> (code, loc, panel, px, py, slot)
found_items: dict[str, list[int]] = {}  # code -> list of matching bit positions

for bit in range(SCAN_FROM, SCAN_TO):
    code, hbits = decode_huffman(data, bit + 53)
    if code is None:
        continue

    loc = read_bits(data, bit + 35, 3)
    panel = read_bits(data, bit + 50, 3)
    px = read_bits(data, bit + 42, 4)
    py = read_bits(data, bit + 46, 4)
    slot = read_bits(data, bit + 38, 4)
    ident = read_bits(data, bit + 4, 1)
    simp = read_bits(data, bit + 21, 1)

    if code not in found_items:
        found_items[code] = []
    found_items[code].append((bit, loc, panel, px, py, slot, ident, simp))

print("=" * 70)
print("ERGEBNIS: Gefundene Item-Positionen nach README")
print("=" * 70)
print()

found_count = 0
for exp_code, exp_loc, exp_panel, exp_px, exp_py, exp_slot, exp_ident, desc in EXPECTED_ITEMS:
    candidates = found_items.get(exp_code, [])

    # Find best match
    best = None
    for bit, loc, panel, px, py, slot, ident, simp in candidates:
        # For equipped items check location+slot
        if exp_loc == 1:
            if loc == 1 and slot == exp_slot and ident == exp_ident:
                best = (bit, loc, panel, px, py, slot, ident)
                break
        else:
            # For stored items check panel+px+py
            if loc == 0 and panel == exp_panel and px == exp_px and py == exp_py:
                best = (bit, loc, panel, px, py, slot, ident)
                break

    if best:
        bit = best[0]
        found_count += 1
        byte_aligned = "[OK] byte-aligned" if bit % 8 == 0 else f"NOT ALIGNED (bit%8={bit%8})"
        print(f"  [OK] '{exp_code}' {desc:<25} -> bit {bit:6d} (byte {bit//8:4d})  {byte_aligned}")
    else:
        # Show all occurrences
        print(f"  [NO] '{exp_code}' {desc:<25} -> NOT FOUND with expected flags")
        if candidates:
            for bit, loc, panel, px, py, slot, ident, simp in candidates[:3]:
                print(
                    f"       (found at {bit}: loc={loc} panel={panel} pos=({px},{py}) slot={slot} ident={ident})"
                )

print()
print(f"Gefunden: {found_count}/{len(EXPECTED_ITEMS)}")

# Show consecutive spacings
print()
print("=" * 70)
print("ITEM-ABSTÄNDE (sollten konsistent sein)")
print("=" * 70)
found_bits = []
for exp_code, exp_loc, exp_panel, exp_px, exp_py, exp_slot, exp_ident, desc in EXPECTED_ITEMS:
    candidates = found_items.get(exp_code, [])
    for bit, loc, panel, px, py, slot, ident, simp in candidates:
        if exp_loc == 1 and loc == 1 and slot == exp_slot:
            found_bits.append((bit, exp_code, desc))
            break
        elif exp_loc == 0 and loc == 0 and panel == exp_panel and px == exp_px and py == exp_py:
            found_bits.append((bit, exp_code, desc))
            break

found_bits.sort()
prev_bit = None
for bit, code, desc in found_bits:
    if prev_bit is not None:
        diff = bit - prev_bit
        print(
            f"  bit {bit:6d}  '{code}'  {desc:<25}  Δ={diff} bits  ({diff//8} bytes + {diff%8} bits)"
        )
    else:
        print(f"  bit {bit:6d}  '{code}'  {desc:<25}  (first)")
    prev_bit = bit

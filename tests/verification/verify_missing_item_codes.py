"""
tests/verification/verify_missing_item_codes.py
================================================
PURPOSE : Finds all item codes in a .d2s file that are NOT classified
          in the game data Excel files (armor.txt, weapons.txt, misc.txt).

          The parser cannot correctly skip type-specific fields for unknown
          item codes, causing misalignment in the property list which produces
          spurious stat_ids > 435 ("unknown stat_id").

          This script reports WHICH codes are missing so the user can verify
          their item type (armor/weapon/misc) and add them to the database.

USAGE   : python tests/verification/verify_missing_item_codes.py <path.d2s>
          python tests/verification/verify_missing_item_codes.py tests/cases/TC01/TestABC.d2s
          python tests/verification/verify_missing_item_codes.py tests/cases/TC03/TestWarlock.d2s
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


def load_item_db(excel_base):
    """Load all item codes from armor/weapons/misc.txt."""
    armor, weapons, misc = set(), set(), set()
    for fname, target in [("armor.txt", armor), ("weapons.txt", weapons), ("misc.txt", misc)]:
        for subdir in ("reimagined", "original"):
            path = Path(excel_base) / subdir / fname
            if not path.exists():
                continue
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            if not lines:
                break
            headers = lines[0].strip().split("\t")
            try:
                code_idx = headers.index("code")
            except ValueError:
                break
            for line in lines[1:]:
                parts = line.strip().split("\t")
                if len(parts) > code_idx:
                    code = parts[code_idx].strip().lower()
                    if code and code != "expansion":
                        target.add(code)
            break  # use reimagined if found, else original
    return armor, weapons, misc


def decode_item_flags(data, item_start):
    return {
        "simple": read_bits(data, item_start + 21, 1),
        "location": read_bits(data, item_start + 35, 3),
        "panel": read_bits(data, item_start + 50, 3),
        "pos_x": read_bits(data, item_start + 42, 4),
        "pos_y": read_bits(data, item_start + 46, 4),
        "equipped_slot": read_bits(data, item_start + 38, 4),
        "quality_from_ext": None,  # filled later for extended items
    }


LOCATION_NAMES = {0: "Stored", 1: "Equipped", 2: "Belt", 4: "Cursor", 6: "Socketed"}
PANEL_NAMES = {0: "None", 1: "Inventory", 4: "Cube", 5: "Stash"}

if len(sys.argv) < 2:
    print("Usage: python verify_missing_item_codes.py <path.d2s>")
    sys.exit(1)

data = Path(sys.argv[1]).read_bytes()
print(f"Datei: {sys.argv[1]} ({len(data)} bytes)")

# Find excel/
excel_base = None
for c in [Path.cwd() / "excel", Path(sys.argv[1]).parent.parent.parent / "excel"]:
    if c.exists():
        excel_base = c
        break
if not excel_base:
    print("FEHLER: excel/ nicht gefunden")
    sys.exit(1)

armor_codes, weapon_codes, misc_codes = load_item_db(excel_base)
print(
    f"Spieldaten: {len(armor_codes)} Armor / {len(weapon_codes)} Weapon / {len(misc_codes)} Misc Codes"
)

# Find items
gf_pos = data.find(b"gf")
jm_pos = data.find(b"JM", gf_pos)
item_count = int.from_bytes(data[jm_pos + 2 : jm_pos + 4], "little")
items_start = (jm_pos + 4) * 8
print(f"JM bei Byte {jm_pos}, {item_count} Items\n")

print(f"{'#':>3}  {'Bit':>7}  {'Byte':>6}  {'Code':<8}  {'Type':<8}  {'Location':<12}  {'Status'}")
print(f"{'─'*3}  {'─'*7}  {'─'*6}  {'─'*8}  {'─'*8}  {'─'*12}  {'─'*30}")

missing_codes = {}  # code -> [(item_num, bit_pos)]
pos = items_start

for i in range(item_count):
    item_start = pos
    flags = decode_item_flags(data, item_start)

    code, hbits = decode_huffman(data, item_start + 53)
    if code is None:
        print(f"{i+1:>3}  {pos:>7}  {pos//8:>6}  {'???':<8}  {'HUFFMAN ERROR':<8}")
        break

    loc_name = LOCATION_NAMES.get(flags["location"], f"loc={flags['location']}")
    if flags["location"] == 0:
        loc_detail = f"{PANEL_NAMES.get(flags['panel'], '?')} ({flags['pos_x']},{flags['pos_y']})"
    elif flags["location"] == 1:
        loc_detail = f"Equip slot {flags['equipped_slot']}"
    else:
        loc_detail = loc_name

    code_lower = code.lower()
    if flags["simple"]:
        item_type = "SIMPLE"
        status = "[OK] simple (no type detection needed)"
        # Simple item size
        total_before_pad = 53 + hbits + 1
        pad = (8 - total_before_pad % 8) % 8
        pos = item_start + total_before_pad + pad
    elif code_lower in armor_codes:
        item_type = "ARMOR"
        status = "[OK] in armor.txt"
        pos = None  # skip to next item using terminator scan
    elif code_lower in weapon_codes:
        item_type = "WEAPON"
        status = "[OK] in weapons.txt"
        pos = None
    elif code_lower in misc_codes:
        item_type = "MISC"
        status = "[OK] in misc.txt"
        pos = None
    else:
        item_type = "???"
        status = "[NO] NOT IN ANY GAME DATA FILE  <- ADD TO DATABASE!"
        if code not in missing_codes:
            missing_codes[code] = []
        missing_codes[code].append(i + 1)
        pos = None

    print(
        f"{i+1:>3}  {item_start:>7}  {item_start//8:>6}  {code:<8}  {item_type:<8}  {loc_detail:<20}  {status}"
    )

    # Advance position for non-simple items: use 0x1FF scan
    if pos is None:
        ext_start = item_start + 53 + hbits
        ext_pos = ext_start
        ext_pos += 35  # uid
        ilvl = read_bits(data, ext_pos, 7)
        ext_pos += 7
        qual = read_bits(data, ext_pos, 4)
        ext_pos += 4
        hgfx = read_bits(data, ext_pos, 1)
        ext_pos += 1
        if hgfx:
            ext_pos += 3
        hcls = read_bits(data, ext_pos, 1)
        ext_pos += 1
        if hcls:
            ext_pos += 11
        # Quality specific
        if qual in (1, 3):
            ext_pos += 3
        elif qual == 4:
            ext_pos += 22
        elif qual == 5:
            ext_pos += 12
        elif qual in (6, 8):
            ext_pos += 16
            for _ in range(6):
                if read_bits(data, ext_pos, 1):
                    ext_pos += 12
                else:
                    ext_pos += 1
        elif qual == 7:
            ext_pos += 12
        if read_bits(data, item_start + 26, 1):
            ext_pos += 16
        if read_bits(data, item_start + 24, 1):
            while ext_pos + 8 <= len(data) * 8:
                b = read_bits(data, ext_pos, 8)
                ext_pos += 8
                if b == 0:
                    break
        ext_pos += 1  # timestamp

        # Find 0x1FF from ext_pos (after all known optional fields)
        found = False
        for off in range(0, 512):
            if ext_pos + off + 9 > len(data) * 8:
                break
            if read_bits(data, ext_pos + off, 9) == 0x1FF:
                pos = ext_pos + off + 9
                found = True
                break
        if not found:
            print(f"     ERROR: 0x1FF not found for item {i+1}")
            break

print()
print(f"{'='*65}")
print("FEHLENDE ITEM-CODES (nicht in Excel-Dateien)")
print(f"{'='*65}")
if missing_codes:
    print("\nDiese Codes müssen zur korrekten Item-Typ-Erkennung klassifiziert werden.")
    print("Bitte prüfe in der Reimagined Mod ob diese Armor, Weapon oder Misc sind:\n")
    for code, item_nums in sorted(missing_codes.items()):
        print(f"  '{code}' (in Item #{', '.join(str(n) for n in item_nums)})")
    print()
    print("  -> armor.txt:   Item hat Defense + Durability Felder")
    print("  -> weapons.txt: Item hat Durability Felder (kein Defense)")
    print("  -> misc.txt:    Stackable/Potion/Charm/Misc (keine Dur-Felder)")
else:
    print("\nAlle Item-Codes bekannt! Kein Klassifikations-Problem.")

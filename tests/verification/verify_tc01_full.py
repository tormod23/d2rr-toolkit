"""
tests/verification/verify_tc01_full.py
=======================================
PURPOSE : Vollständiger Trace ALLER 6 Items in TC01 mit exakten Bit-Positionen.
          Zeigt ob Item #6 (Vicious Spear spr) korrekt dekodiert wird.

          Mit encode=4 Fix muss ssd bei Bit 7891 enden.
          Item #6 muss bei Bit 7891 starten und als 'spr' dekodieren.

USAGE   : python tests/verification/verify_tc01_full.py tests/cases/TC01/TestABC.d2s
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


def load_isc(excel_base):
    ISC = {}
    for subdir in ("reimagined", "original"):
        path = Path(excel_base) / subdir / "itemstatcost.txt"
        if not path.exists():
            continue
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        headers = lines[0].strip().split("\t")

        def col(n):
            try:
                return headers.index(n)
            except:
                return None

        idx_id = col("*ID")
        idx_sb = col("Save Bits")
        idx_sa = col("Save Add")
        idx_sp = col("Save Param Bits")
        idx_enc = col("Encode")
        idx_name = col("Stat")
        for line in lines[1:]:
            p = line.strip().split("\t")
            if not p or not p[0].strip():
                continue
            try:
                sid = int(p[idx_id].strip())

                def gi(idx, default=0):
                    if idx is None or idx >= len(p):
                        return default
                    v = p[idx].strip()
                    try:
                        return int(v) if v else default
                    except:
                        return default

                ISC[sid] = {
                    "name": p[idx_name].strip() if idx_name and idx_name < len(p) else "",
                    "save_bits": gi(idx_sb),
                    "save_add": gi(idx_sa),
                    "save_param": gi(idx_sp),
                    "encode": gi(idx_enc),
                }
            except:
                pass
        return ISC
    return ISC


LOCATION_NAMES = {0: "Stored", 1: "Equipped", 2: "Belt", 4: "Cursor", 6: "Socketed"}
PANEL_NAMES = {0: "None", 1: "Inventory", 4: "Cube", 5: "Stash"}
QUALITY_NAMES = {
    1: "Low",
    2: "Normal",
    3: "Superior",
    4: "Magic",
    5: "Set",
    6: "Rare",
    7: "Unique",
    8: "Crafted",
}


def parse_properties(data, pos, ISC, item_name=""):
    """Parse property list. Returns final bit position after 0x1FF."""
    for _ in range(30):
        stat_id = read_bits(data, pos, 9)
        if stat_id == 0x1FF:
            pos += 9
            print(f"      0x1FF TERMINATOR -> props end at bit {pos}")
            return pos, True
        s = ISC.get(stat_id)
        if s is None:
            print(
                f"      stat_id={stat_id} UNKNOWN at bit {pos} <- MISALIGNMENT or missing ISC entry"
            )
            # scan for terminator
            for off in range(0, 100):
                if read_bits(data, pos + off, 9) == 0x1FF:
                    print(f"      0x1FF found at +{off} bits (bit {pos+off}) -> skip to {pos+off+9}")
                    return pos + off + 9, False
            return pos, False

        enc = s["encode"]
        sb = s["save_bits"]
        sp = s["save_param"]
        if enc == 1:
            paired = ISC.get(stat_id + 1)
            pb = paired["save_bits"] if paired else 0
            val = read_bits(data, pos + 9 + sp, sb)
            val2 = read_bits(data, pos + 9 + sp + sb, pb)
            print(
                f"      stat={stat_id:3d} '{s['name']:<25}' enc=1 val={val-s['save_add']}/{val2-(paired['save_add'] if paired else 0)}"
            )
            pos += 9 + sp + sb + pb
        elif enc == 4:
            extra = sb if sb > 0 else 5  # [BINARY_VERIFIED]
            val = read_bits(data, pos + 9, extra)
            print(
                f"      stat={stat_id:3d} '{s['name']:<25}' enc=4 sb={sb} extra={extra} val={val}"
            )
            pos += 9 + sp + extra
        elif enc in (2, 3):
            pos += 9 + sb
            print(f"      stat={stat_id:3d} '{s['name']:<25}' enc={enc}")
        else:
            val = read_bits(data, pos + 9 + sp, sb) - s["save_add"] if sb > 0 else 0
            print(f"      stat={stat_id:3d} '{s['name']:<25}' enc={enc} sb={sb} val={val}")
            pos += 9 + sp + sb
    return pos, False


if len(sys.argv) < 2:
    print("Usage: python verify_tc01_full.py <TestABC.d2s>")
    sys.exit(1)

data = Path(sys.argv[1]).read_bytes()
excel_base = None
for c in [Path.cwd() / "excel", Path(sys.argv[1]).parent.parent.parent / "excel"]:
    if c.exists():
        excel_base = c
        break
ISC = load_isc(excel_base) if excel_base else {}
print(f"Datei: {sys.argv[1]} ({len(data)} bytes), ISC: {len(ISC)} Stats\n")

# TC01: Items start at byte 920
ITEMS_START = 920 * 8


# Load item codes
def load_codes(excel_base):
    armor, weapons, misc = set(), set(), set()
    for fname, s in [("armor.txt", armor), ("weapons.txt", weapons), ("misc.txt", misc)]:
        for sd in ("reimagined", "original"):
            p = Path(excel_base) / sd / fname
            if not p.exists():
                continue
            with open(p, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            headers = lines[0].strip().split("\t")
            try:
                ci = headers.index("code")
            except:
                break
            for line in lines[1:]:
                parts = line.strip().split("\t")
                if len(parts) > ci:
                    code = parts[ci].strip().lower()
                    if code:
                        s.add(code)
            break
    return armor, weapons, misc


armor_codes, weapon_codes, misc_codes = (
    load_codes(excel_base) if excel_base else (set(), set(), set())
)

pos = ITEMS_START
for item_num in range(6):
    item_start = pos
    print(f"{'='*60}")
    print(f"ITEM #{item_num+1} at bit {item_start} (byte {item_start//8})")
    print(f"{'='*60}")

    # Flags
    loc = read_bits(data, pos + 35, 3)
    panel = read_bits(data, pos + 50, 3)
    px = read_bits(data, pos + 42, 4)
    py = read_bits(data, pos + 46, 4)
    slot = read_bits(data, pos + 38, 4)
    simp = read_bits(data, pos + 21, 1)
    sock = read_bits(data, pos + 11, 1)
    ident = read_bits(data, pos + 4, 1)

    loc_str = LOCATION_NAMES.get(loc, f"loc={loc}")
    if loc == 0:
        loc_detail = f"{PANEL_NAMES.get(panel,'?')} ({px},{py})"
    elif loc == 1:
        loc_detail = f"Equip slot {slot}"
    else:
        loc_detail = f"{loc_str}"
    print(f"  Location: {loc_detail}  simple={simp}  socketed={sock}  ident={ident}")

    # Huffman
    code, hbits = decode_huffman(data, pos + 53)
    print(f"  Code: '{code}' ({hbits} bits)")

    if simp:
        total = 53 + hbits + 1
        pad = (8 - total % 8) % 8
        pos = item_start + total + pad
        print(f"  SIMPLE item: {total}+{pad}pad = {total+pad} bits -> next at {pos}")
        continue

    # Extended
    ext = item_start + 53 + hbits
    uid = read_bits(data, ext + 0, 35)
    ilvl = read_bits(data, ext + 35, 7)
    qual = read_bits(data, ext + 42, 4)
    hgfx = read_bits(data, ext + 46, 1)
    hcls = read_bits(data, ext + 47, 1)
    print(
        f"  Extended: ilvl={ilvl} qual={qual}({QUALITY_NAMES.get(qual,'?')}) hgfx={hgfx} hcls={hcls}"
    )

    cur = ext + 48  # after has_class
    if hgfx:
        cur += 3
    cur += 1  # has_class was already peeked at ext+47, advance past it
    if hcls:
        cur += 11
    # Wait - we need to read sequentially:
    cur = ext + 35 + 7 + 4 + 1  # after uid+ilvl+qual+has_gfx
    if hgfx:
        cur += 3
    cur += 1  # has_class
    if hcls:
        cur += 11

    # Quality specific
    if qual == 1 or qual == 3:
        cur += 3
    elif qual == 2:
        pass
    elif qual == 4:
        cur += 22
        print("  Magic: +22 bits (prefix+suffix)")
    elif qual == 5:
        cur += 12
    elif qual in (6, 8):
        cur += 16
        for i in range(6):
            if read_bits(data, cur, 1):
                cur += 12
            else:
                cur += 1
    elif qual == 7:
        cur += 12

    # Runeword/personalized
    if read_bits(data, item_start + 26, 1):
        cur += 16
    if read_bits(data, item_start + 24, 1):
        while cur + 8 <= len(data) * 8:
            b = read_bits(data, cur, 8)
            cur += 8
            if b == 0:
                break

    cur += 1  # timestamp
    type_start = cur
    print(f"  type_start = {type_start} (ext_start+{type_start-ext})")

    # Determine type
    cl = (code or "").lower()
    if cl in armor_codes:
        cat = "ARMOR"
        def_raw = read_bits(data, cur, 11)
        max_dur = read_bits(data, cur + 11, 8)
        cur_dur = read_bits(data, cur + 19, 8)
        print(f"  ARMOR: def_raw={def_raw}(disp={def_raw-10}) max_dur={max_dur} cur_dur={cur_dur}")
        cur += 29  # 11+8+8+2
    elif cl in weapon_codes:
        cat = "WEAPON"
        max_dur = read_bits(data, cur, 8)
        cur_dur = read_bits(data, cur + 8, 8)
        print(f"  WEAPON: max_dur={max_dur} cur_dur={cur_dur}")
        cur += 16
    elif cl in misc_codes:
        cat = "MISC"
        print("  MISC: no type-specific fields")
    else:
        cat = f"UNKNOWN ({cl!r} not in Excel)"
        print(f"  {cat}: treating as 0 type-specific bits")

    # Properties
    print(f"  Properties start at bit {cur}:")
    pos, clean = parse_properties(data, cur, ISC)
    print(f"  Item ends at bit {pos}  {'[OK] CLEAN' if clean else '[!] FALLBACK USED'}")
    print()

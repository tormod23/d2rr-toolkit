"""
tests/verification/verify_tc03_trace.py
=========================================
PURPOSE : Tracet TC03 Item für Item. Für jedes Item:
          1. Dekodiert Huffman-Code
          2. Zeigt alle Flags
          3. Scannt ab dem Item-Start nach dem ECHTEN 0x1FF Terminator
          4. Zeigt den Unterschied zwischen Parser-Position und echtem Ende
          5. Identifiziert exakt wo das erste Missalignment auftritt

USAGE   : python tests/verification/verify_tc03_trace.py tests/cases/TC03/TestWarlock.d2s
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


def load_item_codes(excel_base):
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


def find_real_terminator(data, from_bit, search_range=600):
    """Find the REAL 0x1FF terminator by scanning bit-by-bit."""
    for off in range(0, search_range):
        if from_bit + off + 9 > len(data) * 8:
            break
        if read_bits(data, from_bit + off, 9) == 0x1FF:
            return from_bit + off
    return None


def parse_properties_sim(data, pos, ISC):
    """Simulate property parsing. Returns (end_pos, props_found, first_unknown)."""
    props = []
    for _ in range(30):
        if pos + 9 > len(data) * 8:
            return pos, props, None
        sid = read_bits(data, pos, 9)
        if sid == 0x1FF:
            pos += 9
            # byte align
            rem = pos % 8
            if rem:
                pos += 8 - rem
            return pos, props, None
        s = ISC.get(sid)
        if s is None:
            return pos, props, sid  # first unknown stat_id
        enc = s["encode"]
        sb = s["save_bits"]
        sp = s["save_param"]
        if enc == 1:
            paired = ISC.get(sid + 1)
            pb = paired["save_bits"] if paired else 0
            props.append(sid)
            pos += 9 + sp + sb + pb
        elif enc == 4:
            extra = sb if sb > 0 else 14
            props.append(sid)
            pos += 9 + sp + extra
        else:
            props.append(sid)
            pos += 9 + sp + sb
    return pos, props, None


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
LOCATION_NAMES = {0: "Stored", 1: "Equipped", 2: "Belt"}
PANEL_NAMES = {0: "None(equip)", 1: "Inventory", 4: "Cube", 5: "Stash"}

if len(sys.argv) < 2:
    print("Usage: python verify_tc03_trace.py <TestWarlock.d2s>")
    sys.exit(1)

data = Path(sys.argv[1]).read_bytes()
excel_base = None
for c in [Path.cwd() / "excel", Path(sys.argv[1]).parent.parent.parent / "excel"]:
    if c.exists():
        excel_base = c
        break
ISC = load_isc(excel_base) if excel_base else {}
armor_codes, weapon_codes, misc_codes = (
    load_item_codes(excel_base) if excel_base else (set(), set(), set())
)
print(f"Datei: {sys.argv[1]} ({len(data)} bytes), ISC: {len(ISC)} Stats\n")

# TC03: items start at byte 925
pos = 925 * 8
ITEM_COUNT = 24

for item_num in range(1, ITEM_COUNT + 1):
    item_start = pos

    # Read flags
    loc = read_bits(data, pos + 35, 3)
    panel = read_bits(data, pos + 50, 3)
    px = read_bits(data, pos + 42, 4)
    py = read_bits(data, pos + 46, 4)
    slot = read_bits(data, pos + 38, 4)
    simp = read_bits(data, pos + 21, 1)
    ident = read_bits(data, pos + 4, 1)
    sock = read_bits(data, pos + 11, 1)

    code, hbits = decode_huffman(data, pos + 53)

    # Location string
    if loc == 1:
        loc_str = f"Equip slot {slot}"
    elif loc == 0:
        loc_str = f"{PANEL_NAMES.get(panel,'?')} ({px},{py})"
    else:
        loc_str = "Belt"

    print(
        f"Item #{item_num:2d} | bit {pos:6d} | '{code}' | {loc_str} | simple={simp} ident={ident} sock={sock}",
        end="",
    )

    if simp:
        total = 53 + hbits + 1
        pad = (8 - total % 8) % 8
        pos = item_start + total + pad
        print(f" | SIMPLE -> next at {pos}")
        continue

    # Extended item
    ext = item_start + 53 + hbits
    qual = read_bits(data, ext + 42, 4)
    hgfx = read_bits(data, ext + 46, 1)
    hcls = read_bits(data, ext + 47, 1)
    print(f" | qual={qual}({QUALITY_NAMES.get(qual,'?')}) hgfx={hgfx} hcls={hcls}", end="")

    # Compute type_start
    cur = ext + 35 + 7 + 4  # uid+ilvl+qual
    cur += 1  # has_gfx
    if hgfx:
        cur += 3
    cur += 1  # has_cls
    if hcls:
        cur += 11
    # quality specific
    if qual in (1, 3):
        cur += 3
    elif qual == 2:
        pass
    elif qual == 4:
        cur += 22
    elif qual == 5:
        cur += 12
    elif qual in (6, 8):
        cur += 16
        for _ in range(6):
            if read_bits(data, cur, 1):
                cur += 12
            else:
                cur += 1
    elif qual == 7:
        cur += 12
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

    # Determine category
    cl = (code or "").lower()
    if cl in armor_codes:
        cat = "ARMOR"
    elif cl in weapon_codes:
        cat = "WEAPON"
    elif cl in misc_codes:
        cat = "MISC"
    else:
        cat = "UNKNOWN"

    # Skip type-specific fields based on category
    if cat == "ARMOR":
        props_start = type_start + 29  # 11+8+8+2
    elif cat == "WEAPON":
        props_start = type_start + 16  # 8+8 (VER-006e pending)
    else:
        props_start = type_start  # MISC/UNKNOWN: no type fields

    # Simulate property parsing
    parser_end, props_found, first_unknown = parse_properties_sim(data, props_start, ISC)

    # Find real terminator
    real_term = find_real_terminator(data, props_start, 400)
    if real_term:
        real_end = real_term + 9
        rem = real_end % 8
        if rem:
            real_end += 8 - rem
    else:
        real_end = None

    # Verdict
    if first_unknown is not None:
        diff = real_end - parser_end if real_end else "?"
        print(f"\n         cat={cat} props_start={props_start}")
        print(
            f"         [NO] UNKNOWN stat_id={first_unknown} (>435) - parser MISALIGNED at bit {parser_end}"
        )
        print(f"         Real 0x1FF at bit {real_term}, real_end at bit {real_end}")
        print(f"         Parser off by: {diff} bits  <- THIS is the bug!")
        # Show what's between props_start and real_term
        print(f"         Bits {props_start} to {real_term}: {real_term-props_start} total")
        print("         First few 9-bit values from props_start:")
        p = props_start
        for i in range(8):
            v = read_bits(data, p, 9)
            s = ISC.get(v)
            sname = s["name"] if s else ("0x1FF" if v == 0x1FF else f"UNKNOWN({v})")
            print(f"           [{i}] bit {p}: stat_id={v:3d} '{sname}'")
            if s:
                p += (
                    9
                    + s["save_param"]
                    + (
                        s["save_bits"]
                        if s["encode"] != 1
                        else s["save_bits"]
                        + (
                            ISC.get(v + 1, {}).get("save_bits", 0)
                            if isinstance(ISC.get(v + 1), dict)
                            else 0
                        )
                    )
                )
            elif v == 0x1FF:
                break
            else:
                break
    else:
        print(f" | cat={cat} | props={len(props_found)} | end={parser_end}", end="")
        if real_end and parser_end != real_end:
            print(f" | [NO] real_end={real_end} DIFF={parser_end-real_end}")
        else:
            print(" | [OK]")

    pos = real_end if real_end else parser_end

print(f"\nFinal position: bit {pos} (byte {pos//8})")
print(f"File size: {len(data)*8} bits ({len(data)} bytes)")


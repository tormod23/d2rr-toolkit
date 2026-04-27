"""
tests/verification/verify_tc11_exact.py
=========================================
PURPOSE : Misst exakt die Item-Struktur von gmd und stu in TC11.

          BEKANNT (aus verify_tc11_positions):
          - gmd(0,0) bei Bit 7400 -> stu(1,0) bei Bit 7488: Δ=88 Bits
          - stu(1,0) bei Bit 7488 -> gmd(3,0) bei Bit 7672: Δ=184 Bits
          - gmd(3,0) bei Bit 7672 -> gmd(6,0) bei Bit 7760: Δ=88 Bits
          - stu(4,0) bei Bit 7848 -> gmd(loc=6) bei Bit 8032: Δ=184 Bits

          ZU PRÜFEN:
          A) gmd: 88 bits = 53+18+1+9(qty)+7(pad)? -> quantity=1?
          B) stu: was steckt in 184 bits?
          C) socket_count: 4 bits nach 0x1FF? Wann byte-align?

USAGE   : python tests/verification/verify_tc11_exact.py tests/cases/TC11/TestWarlock.d2s
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
    return "".join(str(read_bits(data, start_bit + i, 1)) for i in range(count))


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

if len(sys.argv) < 2:
    print("Usage: python verify_tc11_exact.py <TestWarlock.d2s>")
    sys.exit(1)
data = Path(sys.argv[1]).read_bytes()
excel_base = None
for c in [Path.cwd() / "excel", Path(sys.argv[1]).parent.parent.parent / "excel"]:
    if c.exists():
        excel_base = c
        break
ISC = load_isc(excel_base) if excel_base else {}
print(f"Datei: {sys.argv[1]} ({len(data)} bytes), ISC: {len(ISC)} Stats\n")

# Known positions [BINARY_VERIFIED from verify_tc11_positions]
GDM1_START = 7400  # gmd Inventory(0,0) - simple
STU1_START = 7488  # stu Inventory(1,0) - empty socket
GDM2_START = 7672  # gmd Inventory(3,0) - simple
GDM3_START = 7760  # gmd Inventory(6,0) - simple
STU2_START = 7848  # stu Inventory(4,0) - filled socket
GDM_SOCK = 8032  # gmd loc=6 socketed child

print("═" * 65)
print("TEIL A: gmd simple item - Quantity-Feld?")
print("═" * 65)
print(f"\n  gmd starts at bit {GDM1_START}, next item at {STU1_START}")
print(f"  Total = {STU1_START - GDM1_START} bits")
print()
code, hbits = decode_huffman(data, GDM1_START + 53)
print(f"  code='{code}' ({hbits} bits), ext_start = 53+{hbits} = {53+hbits}")
simple = read_bits(data, GDM1_START + 21, 1)
print(f"  simple={simple}")
print()
# Standard simple formula
standard_end = 53 + hbits + 1  # flags + huffman + socket_bit
pad1 = (8 - standard_end % 8) % 8
print(f"  Standard formula: 53+{hbits}+1 = {standard_end} -> +{pad1} pad = {standard_end+pad1} bits")
print(f"  Actual:           {STU1_START - GDM1_START} bits")
extra = (STU1_START - GDM1_START) - (standard_end + pad1)
print(f"  Extra bits after standard formula: {extra}")
print()

# Test: quantity field (9 bits) at position standard_end
qty_pos = GDM1_START + standard_end
qty_9 = read_bits(data, qty_pos, 9)
print(f"  9-bit quantity at bit {qty_pos} (pos +{standard_end}):")
print(f"  Bits: {bits_str(data, qty_pos, 9)}")
print(f"  Value = {qty_9}  (expected: 1 for one Diamond)")

# Verify: standard_end + 9 bit qty + padding = actual?
after_qty = standard_end + 9
pad2 = (8 - after_qty % 8) % 8
total_with_qty = after_qty + pad2
print(f"\n  With 9-bit quantity: {standard_end}+9+{pad2}pad = {total_with_qty} bits")
match = (
    "[OK] MATCHES!"
    if total_with_qty == STU1_START - GDM1_START
    else f"[NO] expected {STU1_START - GDM1_START}"
)
print(f"  {match}")

# Verify all 3 gmd items have quantity=1
print("\n  Quantity check for all 3 free gmd items:")
for name, start in [("gmd(0,0)", GDM1_START), ("gmd(3,0)", GDM2_START), ("gmd(6,0)", GDM3_START)]:
    c, hb = decode_huffman(data, start + 53)
    q_start = start + 53 + hb + 1  # after socket bit
    qty = read_bits(data, q_start, 9)
    print(f"  {name} at {start}: code='{c}' qty={qty}")

print(f"\n  Socketed child gmd at {GDM_SOCK}:")
c, hb = decode_huffman(data, GDM_SOCK + 53)
q_start = GDM_SOCK + 53 + hb + 1
qty = read_bits(data, q_start, 9)
print(f"  code='{c}' qty={qty}")

print()
print("═" * 65)
print("TEIL B: stu extended item - vollständiger Trace")
print("═" * 65)
print(f"\n  stu(1,0) starts at bit {STU1_START}, next item at {GDM2_START}")
print(f"  Total = {GDM2_START - STU1_START} bits")

code2, hbits2 = decode_huffman(data, STU1_START + 53)
ext2 = STU1_START + 53 + hbits2
print(f"\n  code='{code2}' ({hbits2} bits), ext_start = {ext2}")

pos = ext2
uid = read_bits(data, pos, 35)
pos += 35
ilvl = read_bits(data, pos, 7)
pos += 7
qual = read_bits(data, pos, 4)
pos += 4
hgfx = read_bits(data, pos, 1)
pos += 1
if hgfx:
    pos += 3
hcls = read_bits(data, pos, 1)
pos += 1
if hcls:
    pos += 11
print(f"  uid={uid} ilvl={ilvl} qual={qual}({QUALITY_NAMES.get(qual,'?')}) hgfx={hgfx} hcls={hcls}")

# Quality specific
if qual in (1, 3):
    pos += 3
    print(f"  +3 bits quality-specific ({QUALITY_NAMES.get(qual)})")
elif qual == 2:
    pass
elif qual == 4:
    pos += 22
    print("  +22 bits magic prefix+suffix")
elif qual == 5:
    pos += 12
    print("  +12 bits set id")
elif qual in (6, 8):
    pos += 16
    for i in range(6):
        if read_bits(data, pos, 1):
            pos += 12
        else:
            pos += 1
elif qual == 7:
    pos += 12
    print("  +12 bits unique id")

# Runeword/personalized
rw = read_bits(data, STU1_START + 26, 1)
pe = read_bits(data, STU1_START + 24, 1)
if rw:
    pos += 16
if pe:
    while pos + 8 <= len(data) * 8:
        b = read_bits(data, pos, 8)
        pos += 8
        if b == 0:
            break

ts = read_bits(data, pos, 1)
pos += 1
type_start = pos
print(f"  timestamp={ts}, type_start={type_start} (item_offset={type_start-STU1_START})")

# Armor fields [BINARY_VERIFIED]
def_raw = read_bits(data, pos, 11)
max_dur = read_bits(data, pos + 11, 8)
cur_dur = read_bits(data, pos + 19, 8)
unk_post = read_bits(data, pos + 27, 2)
pos += 29
print(f"  def_raw={def_raw}(disp={def_raw-10}) max_dur={max_dur} cur_dur={cur_dur} unk={unk_post}")
print(f"  props_start={pos} (item_offset={pos-STU1_START})")

# Decode properties
print("\n  --- Properties ---")
for i in range(15):
    sid = read_bits(data, pos, 9)
    if sid == 0x1FF:
        pos += 9
        print(f"  [{i}] 0x1FF at {pos-9} -> TERMINATOR consumed, pos={pos}")
        break
    s = ISC.get(sid)
    if s is None:
        print(f"  [{i}] UNKNOWN stat_id={sid} at {pos}!")
        break
    enc = s["encode"]
    sb = s["save_bits"]
    sp = s["save_param"]
    val = read_bits(data, pos + 9 + sp, sb) - s["save_add"] if sb > 0 else 0
    print(f"  [{i}] stat={sid} '{s['name']}' sb={sb} val={val}")
    if enc == 1:
        paired = ISC.get(sid + 1)
        pb = paired["save_bits"] if paired else 0
        pos += 9 + sp + sb + pb
    elif enc == 4:
        extra = sb if sb > 0 else 14
        pos += 9 + sp + extra
    else:
        pos += 9 + sp + sb

after_term = pos
print(f"\n  After 0x1FF: pos={after_term} (item_offset={after_term-STU1_START})")

print("\n  --- Socket Count Field Test ---")
print(f"  Testing: 4 bits at pos {after_term}")
sock_count = read_bits(data, after_term, 4)
print(f"  Bits: {bits_str(data, after_term, 4)}")
print(f"  4-bit socket_count = {sock_count} (expected: 1)")

after_sock = after_term + 4
rem = after_sock % 8
pad = (8 - rem) % 8
after_pad = after_sock + pad
print(f"  After socket_count(4)+pad({pad}): pos={after_pad} (item_offset={after_pad-STU1_START})")
print(f"  Expected next item at: {GDM2_START}")
match = (
    "[OK] MATCH!"
    if after_pad == GDM2_START
    else f"[NO] expected {GDM2_START}, diff={after_pad-GDM2_START}"
)
print(f"  {match}")

# Same for stu2 (filled socket)
print()
print("═" * 65)
print("TEIL C: stu(4,0) mit gefülltem Socket - gleiche Struktur?")
print("═" * 65)
print(f"\n  stu(4,0) starts at bit {STU2_START}, next=gmd(socketed) at {GDM_SOCK}")
print(f"  Total = {GDM_SOCK - STU2_START} bits")

code3, hbits3 = decode_huffman(data, STU2_START + 53)
ext3 = STU2_START + 53 + hbits3
pos3 = ext3
pos3 += 35  # uid
ilvl3 = read_bits(data, pos3, 7)
pos3 += 7
qual3 = read_bits(data, pos3, 4)
pos3 += 4
hgfx3 = read_bits(data, pos3, 1)
pos3 += 1
if hgfx3:
    pos3 += 3
hcls3 = read_bits(data, pos3, 1)
pos3 += 1
if hcls3:
    pos3 += 11
if qual3 in (1, 3):
    pos3 += 3
elif qual3 == 2:
    pass
elif qual3 == 4:
    pos3 += 22
elif qual3 == 5:
    pos3 += 12
elif qual3 in (6, 8):
    pos3 += 16
    for _ in range(6):
        if read_bits(data, pos3, 1):
            pos3 += 12
        else:
            pos3 += 1
elif qual3 == 7:
    pos3 += 12
pos3 += 1  # timestamp

def_raw3 = read_bits(data, pos3, 11)
max_dur3 = read_bits(data, pos3 + 11, 8)
cur_dur3 = read_bits(data, pos3 + 19, 8)
pos3 += 29

print(
    f"  code='{code3}' qual={qual3}({QUALITY_NAMES.get(qual3,'?')}) def={def_raw3-10} dur={max_dur3}/{cur_dur3}"
)

# Scan to 0x1FF
for _ in range(15):
    sid = read_bits(data, pos3, 9)
    if sid == 0x1FF:
        pos3 += 9
        break
    s = ISC.get(sid)
    if s is None:
        print(f"  UNKNOWN stat {sid}!")
        break
    enc = s["encode"]
    sb = s["save_bits"]
    sp = s["save_param"]
    if enc == 1:
        paired = ISC.get(sid + 1)
        pb = paired["save_bits"] if paired else 0
        pos3 += 9 + sp + sb + pb
    elif enc == 4:
        pos3 += 9 + (sb if sb > 0 else 14)
    else:
        pos3 += 9 + sp + sb

sock3 = read_bits(data, pos3, 4)
after_sock3 = pos3 + 4
pad3 = (8 - after_sock3 % 8) % 8
after_pad3 = after_sock3 + pad3
print(f"  socket_count={sock3} -> after_sock+pad: pos={after_pad3}")
match3 = (
    "[OK] MATCH!" if after_pad3 == GDM_SOCK else f"[NO] expected {GDM_SOCK}, diff={after_pad3-GDM_SOCK}"
)
print(f"  Expected: {GDM_SOCK}  {match3}")

print()
print("═" * 65)
print("SUMMARY - für VERIFICATION_LOG.md")
print("═" * 65)
print()
print("  gmd (simple misc, stackable):")
print("    simple_item_size = 53 + huffman_bits + 1(socket_bit) + 9(quantity) + pad")
print(f"    quantity for single gmd = {qty_9}")
print()
print("  stu (extended armor, socketed):")
print("    After 0x1FF terminator: 4-bit socket_count, then byte_align")
print(f"    socket_count value: {sock_count} (stu1) and {sock3} (stu2)")

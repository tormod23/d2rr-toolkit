"""
tests/verification/verify_item_properties.py
=============================================
PURPOSE : Trace item extended structure + properties for TC01 item 5 (ssd Superior)
          using the real ISC to identify exactly where the misalignment occurs.

USAGE   : python tests/verification/verify_item_properties.py tests/cases/TC01/TestABC.d2s | Out-File tests/cases/TC01/verify_properties_output.txt -Encoding utf8
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
        idx_name = col("Stat")
        idx_sb = col("Save Bits")
        idx_sa = col("Save Add")
        idx_sp = col("Save Param Bits")
        idx_enc = col("Encode")
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
                    "name": p[idx_name].strip() if idx_name and idx_name < len(p) else str(sid),
                    "save_bits": gi(idx_sb),
                    "save_add": gi(idx_sa),
                    "save_param": gi(idx_sp),
                    "encode": gi(idx_enc),
                }
            except:
                pass
        print(f"ISC geladen aus '{subdir}': {len(ISC)} Stats")
        return ISC
    print("FEHLER: ISC nicht gefunden!")
    return ISC


if len(sys.argv) < 2:
    print("Usage: python verify_item_properties.py <path.d2s>")
    sys.exit(1)

data = Path(sys.argv[1]).read_bytes()
print(f"Datei: {sys.argv[1]} ({len(data)} bytes)")

# Find excel/ directory
excel_base = None
for candidate in [Path.cwd() / "excel", Path(sys.argv[1]).parent.parent.parent / "excel"]:
    if candidate.exists():
        excel_base = candidate
        break
if not excel_base:
    print("FEHLER: excel/ nicht gefunden")
    sys.exit(1)

ISC = load_isc(excel_base)

# TC01: Items starten bei Byte 920
# Items 1-4: hp1 simple (4x80 bits = 320 bits)
# Item 5 startet bei Bit 7360 + 320 = 7680
item5_start = 7680
print(f"\n=== Item #5 (ssd Superior) bei Bit {item5_start} ===")

code, hbits = decode_huffman(data, item5_start + 53)
print(f"Code: '{code}' ({hbits} Bits)")

# Sequential lesen genau wie der Parser
pos = item5_start + 53 + hbits  # ext_start
print(f"ext_start: {pos}")

uid = read_bits(data, pos, 35)
pos += 35
ilvl = read_bits(data, pos, 7)
pos += 7
qual = read_bits(data, pos, 4)
pos += 4
hgfx = read_bits(data, pos, 1)
pos += 1
if hgfx:
    gfx = read_bits(data, pos, 3)
    pos += 3
    print(f"  gfx_index={gfx}")
hcls = read_bits(data, pos, 1)
pos += 1
if hcls:
    cls_data = read_bits(data, pos, 11)
    pos += 11
    print(f"  class_data={cls_data} ({pos-11} bis {pos})")

print(
    f"Nach uid/ilvl/qual/gfx/cls: pos={pos}  (uid={uid} ilvl={ilvl} qual={qual} hgfx={hgfx} hcls={hcls})"
)

# Quality-specific: qual=3=Superior -> 3 bits
if qual == 1:
    v = read_bits(data, pos, 3)
    pos += 3
    print(f"  LowQual type={v}")
elif qual == 2:
    pass
elif qual == 3:
    v = read_bits(data, pos, 3)
    pos += 3
    print(f"  Superior type={v}")
elif qual == 4:
    pfx = read_bits(data, pos, 11)
    pos += 11
    sfx = read_bits(data, pos, 11)
    pos += 11
    print(f"  Magic: prefix={pfx} suffix={sfx}")
elif qual == 5:
    v = read_bits(data, pos, 12)
    pos += 12
    print(f"  Set id={v}")
elif qual in (6, 8):
    n1 = read_bits(data, pos, 8)
    pos += 8
    n2 = read_bits(data, pos, 8)
    pos += 8
    print(f"  Rare/Craft names: {n1},{n2}")
    for i in range(6):
        has_aff = read_bits(data, pos, 1)
        pos += 1
        if has_aff:
            aff = read_bits(data, pos, 11)
            pos += 11
            print(f"    affix[{i}]={aff}")
elif qual == 7:
    v = read_bits(data, pos, 12)
    pos += 12
    print(f"  Unique id={v}")

# Runeword/Personalized
runeword = read_bits(data, item5_start + 26, 1)
personalized = read_bits(data, item5_start + 24, 1)
if runeword:
    v = read_bits(data, pos, 12)
    pos += 12
    u = read_bits(data, pos, 4)
    pos += 4
    print(f"  Runeword: str_idx={v} unknown={u}")
if personalized:
    print("  Personalisiert: Name lesen...")

# Timestamp
ts = read_bits(data, pos, 1)
pos += 1
print(f"Timestamp={ts}, type_start={pos}")

type_start = pos
print(f"\n=== Weapon type_start={type_start} ===")

# Weapon: max_dur + cur_dur
max_dur = read_bits(data, pos, 8)
pos += 8
cur_dur = read_bits(data, pos, 8)
pos += 8
print(f"max_dur={max_dur} cur_dur={cur_dur}")
print(f"Properties ab Bit {pos}")

# Properties mit ISC
print("\n=== Properties ===")
TERMINATOR = 0x1FF
for i in range(30):
    stat_id = read_bits(data, pos, 9)
    if stat_id == TERMINATOR:
        print(f"[{i}] 0x1FF TERMINATOR bei Bit {pos}")
        pos += 9
        break
    s = ISC.get(stat_id)
    if s is None:
        print(f"[{i}] UNBEKANNTE stat_id={stat_id} bei Bit {pos} - MISALIGNMENT!")
        # Zeige die nächsten 40 Bits zur Diagnose
        print(f"     Nächste 40 Bits: {''.join(str(read_bits(data,pos+j,1)) for j in range(40))}")
        # Suche nach dem Terminator
        print("     Suche 0x1FF...")
        for off in range(0, 200):
            if read_bits(data, pos + off, 9) == TERMINATOR:
                print(f"     0x1FF gefunden bei Bit {pos+off} (Offset +{off})")
                break
        break

    param = 0
    if s["save_param"] > 0:
        param = read_bits(data, pos + 9, s["save_param"])

    enc = s["encode"]
    if enc == 1:
        val1 = read_bits(data, pos + 9 + s["save_param"], s["save_bits"])
        paired = ISC.get(stat_id + 1)
        val2_bits = paired["save_bits"] if paired else 0
        val2 = read_bits(data, pos + 9 + s["save_param"] + s["save_bits"], val2_bits)
        print(
            f"[{i}] id={stat_id} '{s['name']}' val1={val1-s['save_add']} / paired(id={stat_id+1}) val2={val2-(paired['save_add'] if paired else 0)} [Enc=1]"
        )
        pos += 9 + s["save_param"] + s["save_bits"] + val2_bits
    elif enc == 2:
        total = s["save_bits"]
        level = read_bits(data, pos + 9, 6)
        skill_id = read_bits(data, pos + 15, 10)
        chance = read_bits(data, pos + 25, total - 16) if total > 16 else 0
        print(
            f"[{i}] id={stat_id} '{s['name']}' level={level} skill={skill_id} chance={chance} [Enc=2]"
        )
        pos += 9 + total
    elif enc == 3:
        level = read_bits(data, pos + 9, 6)
        skill_id = read_bits(data, pos + 15, 10)
        charges = read_bits(data, pos + 25, 8)
        max_chg = read_bits(data, pos + 33, 8)
        print(
            f"[{i}] id={stat_id} '{s['name']}' level={level} skill={skill_id} charges={charges}/{max_chg} [Enc=3]"
        )
        pos += 9 + 32
    else:
        raw = read_bits(data, pos + 9 + s["save_param"], s["save_bits"])
        display = raw - s["save_add"]
        print(
            f"[{i}] id={stat_id} '{s['name']}' raw={raw} display={display} ({s['save_bits']}bits add={s['save_add']})"
        )
        pos += 9 + s["save_param"] + s["save_bits"]

print(f"\nNach Properties: Bit {pos} (Byte {pos//8})")

# Item 6 prüfen
print(f"\n=== Item #6 bei Bit {pos} ===")
code6, hbits6 = decode_huffman(data, pos + 53)
loc6 = read_bits(data, pos + 35, 3)
panel6 = read_bits(data, pos + 50, 3)
px6 = read_bits(data, pos + 42, 4)
py6 = read_bits(data, pos + 46, 4)
simp6 = read_bits(data, pos + 21, 1)
qual_raw6 = read_bits(data, pos + 53 + hbits6 + 42, 4) if code6 else 0
print(f"Code: '{code6}' loc={loc6} panel={panel6} pos=({px6},{py6}) simple={simp6}")
print("  Erwartet: spear (Magic, loc=0 panel=1 pos=(1,0))")


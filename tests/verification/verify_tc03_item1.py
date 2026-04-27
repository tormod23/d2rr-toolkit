"""
tests/verification/verify_tc03_item1.py
========================================
PURPOSE : Traced TC03 Item #1 (qui = Quilted Armor, Magic quality) Schritt
          für Schritt und vergleicht Parser-Position mit tatsächlichem 0x1FF.

          Wir wissen aus verify_missing_codes.py:
          - Item #1 bei Bit 7400 (Byte 925)
          - Nächstes Item bei Bit 7617 (Byte 952)  [via 0x1FF scan]
          - Item #1 hat also 217 Bits

          Der Parser muss EXAKT bei Bit 7617 enden.
          Dieses Skript zeigt wo er tatsächlich endet und warum.

USAGE   : python tests/verification/verify_tc03_item1.py tests/cases/TC03/TestWarlock.d2s
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
    print("Usage: python verify_tc03_item1.py <TestWarlock.d2s>")
    sys.exit(1)

data = Path(sys.argv[1]).read_bytes()
excel_base = None
for c in [Path.cwd() / "excel", Path(sys.argv[1]).parent.parent.parent / "excel"]:
    if c.exists():
        excel_base = c
        break
ISC = load_isc(excel_base) if excel_base else {}
print(f"Datei: {sys.argv[1]} ({len(data)} bytes), ISC: {len(ISC)} Stats\n")

# ── Known from verify_missing_codes [BINARY_VERIFIED] ───────────────────────
ITEM1_START_BIT = 7400
ITEM2_START_BIT = 7617  # confirmed via 0x1FF scan
ITEM1_TOTAL_BITS = ITEM2_START_BIT - ITEM1_START_BIT  # = 217

print(f"[BINARY_VERIFIED] Item #1 start: bit {ITEM1_START_BIT}")
print(f"[BINARY_VERIFIED] Item #2 start: bit {ITEM2_START_BIT} (via 0x1FF scan)")
print(f"[BINARY_VERIFIED] Item #1 total: {ITEM1_TOTAL_BITS} bits")
print()

# ── Step-by-step parse ───────────────────────────────────────────────────────
pos = ITEM1_START_BIT


def read(label, n_bits, note=""):
    global pos
    val = read_bits(data, pos, n_bits)
    raw = bits_str(data, pos, min(n_bits, 16))
    print(f"  bit {pos:5d}: {label:<35} = {val:>8}  ({n_bits} bits)  {note}")
    pos += n_bits
    return val


print("═" * 65)
print("STEP-BY-STEP PARSE: TC03 Item #1 (qui)")
print("═" * 65)

# Flags (peek, don't advance)
ident = read_bits(data, pos + 4, 1)
socketed = read_bits(data, pos + 11, 1)
starter = read_bits(data, pos + 17, 1)
simple = read_bits(data, pos + 21, 1)
ethereal = read_bits(data, pos + 22, 1)
personal = read_bits(data, pos + 24, 1)
runeword = read_bits(data, pos + 26, 1)
location = read_bits(data, pos + 35, 3)
slot = read_bits(data, pos + 38, 4)
px = read_bits(data, pos + 42, 4)
py = read_bits(data, pos + 46, 4)
panel = read_bits(data, pos + 50, 3)
print("\n  Flags (peek):")
print(f"    identified={ident} socketed={socketed} starter={starter} simple={simple}")
print(f"    ethereal={ethereal} personal={personal} runeword={runeword}")
print(f"    location={location} slot={slot} pos=({px},{py}) panel={panel}")
print()

# Advance to Huffman (bit 53)
pos += 53
code, hbits = decode_huffman(data, pos)
print(f"  bit {pos:5d}: Huffman code                      = '{code}'  ({hbits} bits)")
pos += hbits
ext_start = pos
print(f"  ext_start = {ext_start}")
print()

# Extended header [BINARY_VERIFIED]
print("  --- Extended Header [BINARY_VERIFIED] ---")
uid = read("unique_item_id (35 bits)", 35, "[BINARY_VERIFIED]")
ilvl = read("item_level", 7, "[BINARY_VERIFIED]")
qual = read(
    "quality", 4, f"[BINARY_VERIFIED] = {QUALITY_NAMES.get(int(read_bits(data, pos-4, 4)), '?')}"
)
has_gfx = read("has_custom_graphics", 1, "[BINARY_VERIFIED]")
if has_gfx:
    gfx_idx = read("  graphic_index", 3, "[SPEC_ONLY]")
has_cls = read("has_class_specific_data", 1, "[BINARY_VERIFIED]")
if has_cls:
    cls_data = read("  class_specific_data", 11, "[SPEC_ONLY]")

print(f"\n  Quality = {qual} = {QUALITY_NAMES.get(qual, '?')}")

# Quality-specific data
print(f"\n  --- Quality-Specific Data (qual={qual}) ---")
if qual == 1:
    v = read("  low_quality_type", 3, "[SPEC_ONLY]")
elif qual == 2:
    print(f"  bit {pos:5d}: Normal quality - no extra bits")
elif qual == 3:
    v = read("  superior_type", 3, "[SPEC_ONLY]")
elif qual == 4:
    pfx = read("  magic_prefix_id", 11, "[SPEC_ONLY]")
    sfx = read("  magic_suffix_id", 11, "[SPEC_ONLY]")
    print(f"            prefix={pfx} suffix={sfx}")
elif qual == 5:
    v = read("  set_item_id", 12, "[SPEC_ONLY]")
elif qual in (6, 8):
    n1 = read("  rare_name1_id", 8, "[SPEC_ONLY]")
    n2 = read("  rare_name2_id", 8, "[SPEC_ONLY]")
    for i in range(6):
        has_a = read(f"  has_affix[{i}]", 1)
        if has_a:
            read(f"    affix_id[{i}]", 11, "[SPEC_ONLY]")
elif qual == 7:
    v = read("  unique_item_id", 12, "[SPEC_ONLY]")

# Runeword / Personalized
if runeword:
    print("\n  --- Runeword Data ---")
    read("  runeword_str_index", 12, "[SPEC_ONLY]")
    read("  runeword_unknown", 4, "[SPEC_ONLY]")
if personal:
    print("\n  --- Personalization ---")
    while pos + 8 <= len(data) * 8:
        b = read("  name_char", 8, "[SPEC_ONLY]")
        if b == 0:
            break

# Timestamp
print("\n  --- Timestamp ---")
ts = read("timestamp_unknown_bit", 1, "[BINARY_VERIFIED]")
type_start = pos
print(f"\n  type_start = {pos}")
print(
    f"  Expected by parser: ext_start({ext_start}) + 49 = {ext_start+49}  {'[OK]' if pos == ext_start+49 else f'[NO] DIFF={pos-(ext_start+49)}'}"
)

# Type-specific (armor)
print("\n  --- Armor Type-Specific Fields [BINARY_VERIFIED] ---")
defense_raw = read("armor_defense_raw (11 bits)", 11, "[BINARY_VERIFIED]")
print(f"            display = {defense_raw} - 10 = {defense_raw-10}")
max_dur = read("max_durability (8 bits)", 8, "[BINARY_VERIFIED]")
cur_dur = read("cur_durability (8 bits)", 8, "[BINARY_VERIFIED]")
unk_post = read("unknown_post_dur (2 bits)", 2, "[UNKNOWN]")

props_start = pos
print(f"\n  Properties start at bit {props_start}")
print(f"  Expected item end: bit {ITEM2_START_BIT}")
print(f"  Remaining bits for properties: {ITEM2_START_BIT - props_start}")
print()

# Decode properties
print("  --- Properties ---")
for i in range(20):
    stat_id = read_bits(data, pos, 9)
    if stat_id == 0x1FF:
        pos += 9
        print(f"  bit {pos-9:5d}: 0x1FF TERMINATOR  <- item ends at bit {pos}")
        break
    s = ISC.get(stat_id)
    if s is None:
        print(f"  bit {pos:5d}: stat_id={stat_id} UNBEKANNT - ISC fehlt oder MISALIGNMENT!")
        # Show what the next few bits look like
        print(f"             Nächste 30 Bits: {bits_str(data, pos, 30)}")
        # Scan for 0x1FF
        for off in range(1, 100):
            if read_bits(data, pos + off, 9) == 0x1FF:
                print(
                    f"             0x1FF bei +{off} (bit {pos+off}) -> item würde bei bit {pos+off+9} enden"
                )
                print(
                    f"             {'[OK] KORREKT' if pos+off+9 == ITEM2_START_BIT else f'[NO] FALSCH (erwartet {ITEM2_START_BIT})'}"
                )
                break
        break

    enc = s["encode"]
    sb = s["save_bits"]
    sp = s["save_param"]
    consumed = 9 + sp + sb

    if enc == 1:
        paired = ISC.get(stat_id + 1)
        pb = paired["save_bits"] if paired else 0
        val1 = read_bits(data, pos + 9 + sp, sb)
        val2 = read_bits(data, pos + 9 + sp + sb, pb)
        print(
            f"  bit {pos:5d}: stat={stat_id:3d} '{s['name']:<28}' "
            f"val={val1-s['save_add']}/{val2-(paired['save_add'] if paired else 0)} [Enc=1]"
        )
        consumed += pb
    elif enc == 4:
        # [BINARY_VERIFIED TC01]: encode=4 with save_bits=0 needs 5 extra bits
        extra = sb if sb > 0 else 5
        val = read_bits(data, pos + 9 + sp, extra)
        print(
            f"  bit {pos:5d}: stat={stat_id:3d} '{s['name']:<28}' "
            f"val={val} [Enc=4 sb={sb} extra={extra}]  <- [BINARY_VERIFIED: +5bits wenn sb=0]"
        )
        consumed = 9 + sp + extra
    else:
        val = read_bits(data, pos + 9 + sp, sb) - s["save_add"] if sb > 0 else 0
        print(
            f"  bit {pos:5d}: stat={stat_id:3d} '{s['name']:<28}' " f"val={val} [Enc={enc} sb={sb}]"
        )
    pos += consumed

print(f"\n  Parser ends at: bit {pos}")
print(f"  Expected end:   bit {ITEM2_START_BIT}")
diff = pos - ITEM2_START_BIT
if diff == 0:
    print("  [OK] PERFECT MATCH - parser is correct for this item!")
else:
    print(f"  [NO] OFF BY {diff} bits ({'zu viel' if diff > 0 else 'zu wenig'})")
    print("\n  Root cause: find which field consumed wrong number of bits above.")

print("\n  [Summary]")
print(f"  type_start offset from ext_start: {type_start - ext_start} bits (parser assumes 49)")
print(
    f"  defense_raw={defense_raw-10+10} (display={defense_raw-10}) max_dur={max_dur} cur_dur={cur_dur}"
)

"""
tests/verification/verify_property_bits.py
==========================================
PURPOSE : Präzise Diagnose der Property-Liste für TC01 Item 5 (ssd Superior).
          Zeigt für JEDEN gelesenen Stat ALLE ISC-Felder und die rohen Bits.
          Testet außerdem verschiedene defense-Breiten (10 vs 11 bits).

USAGE   : python tests/verification/verify_property_bits.py tests/cases/TC01/TestABC.d2s
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
        idx_name = col("Stat")
        idx_sb = col("Save Bits")
        idx_sa = col("Save Add")
        idx_sp = col("Save Param Bits")
        idx_enc = col("Encode")
        idx_saved = col("Saved")
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

                def gs(idx, default=""):
                    if idx is None or idx >= len(p):
                        return default
                    return p[idx].strip()

                ISC[sid] = {
                    "name": gs(idx_name),
                    "save_bits": gi(idx_sb),
                    "save_add": gi(idx_sa),
                    "save_param": gi(idx_sp),
                    "encode": gi(idx_enc),
                    "saved": gs(idx_saved),
                    # Raw column values for debugging
                    "raw_sb": gs(idx_sb, "?"),
                    "raw_sp": gs(idx_sp, "?"),
                    "raw_enc": gs(idx_enc, "?"),
                }
            except:
                pass
        print(f"ISC: {len(ISC)} Stats geladen (max={max(ISC.keys())})")
        return ISC
    print("ISC nicht gefunden!")
    return ISC


if len(sys.argv) < 2:
    print("Usage: python verify_property_bits.py <path.d2s>")
    sys.exit(1)

data = Path(sys.argv[1]).read_bytes()
print(f"Datei: {sys.argv[1]} ({len(data)} bytes)")

excel_base = None
for c in [Path.cwd() / "excel", Path(sys.argv[1]).parent.parent.parent / "excel"]:
    if c.exists():
        excel_base = c
        break
if not excel_base:
    print("excel/ nicht gefunden")
    sys.exit(1)

ISC = load_isc(excel_base)

# Item 5 (ssd Superior) starts at bit 7680
item5_start = 7680
print(f"\n{'='*65}")
print(f"ITEM 5 (ssd Superior) bei Bit {item5_start}")
print(f"{'='*65}")

# Compute type_start exactly
code, hbits = decode_huffman(data, item5_start + 53)
pos = item5_start + 53 + hbits  # ext_start
pos += 35  # uid
ilvl = read_bits(data, pos, 7)
pos += 7
qual = read_bits(data, pos, 4)
pos += 4
has_gfx = read_bits(data, pos, 1)
pos += 1
if has_gfx:
    pos += 3
has_cls = read_bits(data, pos, 1)
pos += 1
if has_cls:
    pos += 11
# Superior = 3 bits
sup_type = read_bits(data, pos, 3)
pos += 3
pos += 1  # timestamp
type_start = pos
print(f"type_start = {type_start}")

# ─── TEST 1: Defense = 10 bits (spec) vs 11 bits (our BINARY_VERIFIED) ───────
print("\n--- Test: defense field breite ---")
for def_bits in [10, 11]:
    def_raw = read_bits(data, type_start, def_bits)
    def_disp = def_raw - 10
    max_dur_bit = type_start + def_bits
    max_dur = read_bits(data, max_dur_bit, 8)
    cur_dur = read_bits(data, max_dur_bit + 8, 8)
    prop_start = max_dur_bit + 16
    first_stat = read_bits(data, prop_start, 9)
    s = ISC.get(first_stat)
    s_name = s["name"] if s else "UNBEKANNT"
    print(
        f"  {def_bits} bits: def_raw={def_raw} (display={def_disp})"
        f" max_dur={max_dur} cur_dur={cur_dur}"
        f" -> 1st stat_id={first_stat} '{s_name}'"
    )

# Our binary-verified type_start for weapon: no defense field
print(
    f"\n  0 bits (weapon, kein defense): max_dur={read_bits(data,type_start,8)}"
    f" cur_dur={read_bits(data,type_start+8,8)}"
    f" -> 1st stat_id={read_bits(data,type_start+16,9)}"
    f" '{ISC.get(read_bits(data,type_start+16,9), {}).get('name','UNBEKANNT')}'"
)

# ─── TEST 2: Vollständige Property-Dekodierung mit ISC-Details ───────────────
print(f"\n--- Vollständige Properties ab Bit {type_start+16} (weapon: max+cur_dur+props) ---")
print(
    f"{'Bit':>7}  {'stat_id':>8}  {'Name':<30}  {'enc':>4}  {'param':>6}  {'sb':>4}  {'Value':>8}  Status"
)
print(f"{'-'*7}  {'-'*8}  {'-'*30}  {'-'*4}  {'-'*6}  {'-'*4}  {'-'*8}  {'-'*10}")

pos = type_start + 16  # after weapon max_dur+cur_dur

for i in range(25):
    stat_id = read_bits(data, pos, 9)
    raw_bits_str = bits_str(data, pos, 9)

    if stat_id == 0x1FF:
        print(f"{pos:>7}  {'0x1FF':>8}  {'TERMINATOR':<30}  {'':>4}  {'':>6}  {'':>4}  {'':>8}  [OK]")
        print(f"\n  -> Nächstes Item bei Bit {pos+9}")
        break

    s = ISC.get(stat_id)
    if s is None:
        print(
            f"{pos:>7}  {stat_id:>8}  {'??? UNBEKANNT':<30}  {'':>4}  {'':>6}  {'':>4}  {'':>8}  [NO] ISC fehlt!"
        )
        # Show raw bits for investigation
        print(f"         Rohbits (9): {raw_bits_str}")
        print(f"         Kontext +0..+30: {bits_str(data, pos, 30)}")

        # Show what bit-values give known stats
        print("         Was käme danach bei save_bits=0..20?")
        for n in range(0, 21):
            next_9 = read_bits(data, pos + 9 + n, 9)
            ns = ISC.get(next_9)
            if next_9 == 0x1FF:
                print(f"           +{n:2d} bits -> 0x1FF <- TERMINATOR")
            elif ns and ns["save_bits"] >= 0:
                print(
                    f"           +{n:2d} bits -> stat_id={next_9:3d} '{ns['name']}' (enc={ns['raw_enc']} sb={ns['raw_sb']})"
                )
        break

    # Known stat - show all ISC fields
    param = 0
    bits_consumed = 9

    enc = s["encode"]
    sb = s["save_bits"]
    sp = s["save_param"]

    if sp > 0:
        param = read_bits(data, pos + 9, sp)
        bits_consumed += sp

    if enc == 1:
        # Min/max pair
        val1 = read_bits(data, pos + bits_consumed, sb)
        bits_consumed += sb
        paired = ISC.get(stat_id + 1)
        pb = paired["save_bits"] if paired else 0
        val2 = read_bits(data, pos + bits_consumed, pb)
        bits_consumed += pb
        display = f"{val1-s['save_add']}/{val2-(paired['save_add'] if paired else 0)}"
        status = f"Enc=1 pair+{stat_id+1}"
    elif enc == 2:
        # Skill on event: 6+10+rest
        total = sb
        lvl = read_bits(data, pos + bits_consumed, 6)
        bits_consumed += 6
        skl = read_bits(data, pos + bits_consumed, 10)
        bits_consumed += 10
        rest = max(0, total - 16)
        if rest:
            bits_consumed += rest
        display = f"lvl={lvl} skl={skl}"
        status = "Enc=2"
    elif enc == 3:
        # Charged skill: 6+10+8+8
        lvl = read_bits(data, pos + bits_consumed, 6)
        bits_consumed += 6
        skl = read_bits(data, pos + bits_consumed, 10)
        bits_consumed += 10
        ch = read_bits(data, pos + bits_consumed, 8)
        bits_consumed += 8
        mc = read_bits(data, pos + bits_consumed, 8)
        bits_consumed += 8
        display = f"lvl={lvl} skl={skl} {ch}/{mc}"
        status = "Enc=3"
    elif enc == 4:
        # Encode 4 - unbekannt, wie viele bits?
        # Versuche save_bits zu lesen wenn > 0
        if sb > 0:
            raw = read_bits(data, pos + bits_consumed, sb)
            bits_consumed += sb
            display = f"raw={raw} (enc4!)"
        else:
            display = "sb=0 enc=4"
        status = f"Enc=4 RAW_SP='{s['raw_sp']}' RAW_SB='{s['raw_sb']}'"
    else:
        raw = read_bits(data, pos + bits_consumed, sb) if sb > 0 else 0
        bits_consumed += sb
        display = f"{raw-s['save_add']}" if sb > 0 else "n/a"
        status = "OK"

    print(
        f"{pos:>7}  {stat_id:>8}  {s['name']:<30}  {enc:>4}  {param:>6}  {sb:>4}  {display:>8}  {status}"
    )
    pos += bits_consumed
else:
    print("  Kein Terminator nach 25 Stats!")

# ─── TEST 3: Zeige ISC-Details für kritische Stats ────────────────────────────
print(f"\n{'='*65}")
print("ISC-Details für alle gelesenen Stats")
print(f"{'='*65}")
print(f"{'ID':>5}  {'Name':<30}  {'Saved':>6}  {'Enc':>4}  {'SP':>4}  {'SB':>4}  {'SA':>5}")
print(f"{'-'*5}  {'-'*30}  {'-'*6}  {'-'*4}  {'-'*4}  {'-'*4}  {'-'*5}")
for sid in [17, 18, 19, 20, 21, 22, 76, 83, 84, 256, 304, 384, 430, 431]:
    s = ISC.get(sid)
    if s:
        print(
            f"{sid:>5}  {s['name']:<30}  {s['saved']:>6}  {s['raw_enc']:>4}  {s['raw_sp']:>4}  {s['raw_sb']:>4}  {s['save_add']:>5}"
        )


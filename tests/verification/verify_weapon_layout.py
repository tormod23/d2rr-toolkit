"""
tests/verification/verify_weapon_layout.py
==========================================
PURPOSE : Findet die exakte Bit-Position von max_dur, cur_dur und den
          Properties bei Waffen durch Binary-Analyse.

          BEKANNT (aus VERIFICATION_LOG):
          - TC09 (ssd Normal): type_start an ext_start+49, max_dur bei +11
          - TC09: 11 unbekannte Bits VOR max_dur
          - TC09: 26 unbekannte Bits NACH cur_dur, dann 0x1FF

          ZU PRÜFEN:
          - TC01 ssd Superior: Hat dieselbe Struktur wie TC09?
          - Warum liest der Parser 250 bei type_start+0?
          - Wo beginnen die echten Properties (stat17=+1maxdmg, stat19=+1AR)?

          METHODE: Suche in den Rohbits nach den Stat-IDs 17/18/19
          die für Superior-Properties typisch sind.

USAGE   : python tests/verification/verify_weapon_layout.py tests/cases/TC01/TestABC.d2s
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
    print("Usage: python verify_weapon_layout.py <d2s_file>")
    sys.exit(1)

data = Path(sys.argv[1]).read_bytes()
excel_base = None
for c in [Path.cwd() / "excel", Path(sys.argv[1]).parent.parent.parent / "excel"]:
    if c.exists():
        excel_base = c
        break
ISC = load_isc(excel_base) if excel_base else {}
print(f"Datei: {sys.argv[1]} ({len(data)} bytes), ISC: {len(ISC)} Stats\n")

# [BINARY_VERIFIED] ssd type_start = 7812
TYPE_START = 7812

print("═" * 65)
print("TEIL 1: Rohbits von type_start bis +80")
print("═" * 65)
print()
print(
    f"  {'Offset':>7}  {'abs bit':>8}  {'Bits (8)':>24}  {'uint8':>6}  {'als 9-bit ID':>14}  ISC-Treffer?"
)
print(f"  {'─'*7}  {'─'*8}  {'─'*24}  {'─'*6}  {'─'*14}  {'─'*20}")
for off in range(0, 81, 1):
    abs_bit = TYPE_START + off
    raw8 = read_bits(data, abs_bit, 8)
    id9 = read_bits(data, abs_bit, 9)
    s = ISC.get(id9)
    annot = f"-> '{s['name']}' sb={s['save_bits']}" if s else ""
    if id9 == 0x1FF:
        annot = "<- 0x1FF TERMINATOR"
    # Only print interesting lines
    if s or id9 == 0x1FF or raw8 == 250 or off % 8 == 0:
        b_str = bits_str(data, abs_bit, min(8, 81 - off))
        print(f"  +{off:>6}  {abs_bit:>8}  {b_str:<24}  {raw8:>6}  {id9:>14}  {annot}")

print()
print("═" * 65)
print("TEIL 2: Suche nach 250 (max/cur durability = 250)")
print("═" * 65)
print()
print("  8-bit Wert 250 = 0 1 0 1 1 1 1 1 (LSB-first)")
print("  Suche in Offsets 0..60 von type_start:")
print()
for off in range(0, 61):
    val8 = read_bits(data, TYPE_START + off, 8)
    if val8 == 250:
        next8 = read_bits(data, TYPE_START + off + 8, 8)
        print(f"  type_start+{off:2d}: val8=250  nächste 8 bits={next8}")
        if next8 == 250:
            print(f"    *** ZWEI AUFEINANDERFOLGENDE 250er! max_dur+{off}, cur_dur+{off+8} ***")

print()
print("═" * 65)
print("TEIL 3: Suche nach Stat-IDs 17 und 19 (Superior Properties)")
print("═" * 65)
print()
# Superior Short Sword: "+1 to Maximum Weapon Damage" (stat17 or 18) and "+1 to AR" (stat19 or 20)
# Scan all 9-bit windows from type_start to type_start+100
print("  Suche stat_id=17 (max_dam) und stat_id=19 (tohit) in type_start+0 bis +100:")
for off in range(0, 101):
    id9 = read_bits(data, TYPE_START + off, 9)
    if id9 in [17, 18, 19, 20]:
        s = ISC.get(id9)
        next9 = read_bits(data, TYPE_START + off + 9 + (s["save_bits"] if s else 0), 9)
        next_s = ISC.get(next9)
        next_annot = (
            f"-> stat_id={next9} '{next_s['name'] if next_s else '?'}'"
            if next9 != 0x1FF
            else "-> 0x1FF"
        )
        print(
            f"  type_start+{off:2d}: stat_id={id9} '{s['name'] if s else '?'}' sb={s['save_bits'] if s else '?'}  {next_annot}"
        )

print()
print("═" * 65)
print("TEIL 4: Vollständige Property-Dekodierung ab verschiedenen Offsets")
print("═" * 65)
print()


def try_props_from(start_abs, label):
    """Try to decode a valid property list from start_abs."""
    pos = start_abs
    props = []
    for _ in range(15):
        sid = read_bits(data, pos, 9)
        if sid == 0x1FF:
            props.append(("TERM", 0x1FF, 0))
            return props, pos + 9
        s = ISC.get(sid)
        if s is None:
            props.append(("UNK", sid, 0))
            return props, pos
        enc = s["encode"]
        sb = s["save_bits"]
        sp = s["save_param"]
        if enc == 1:
            paired = ISC.get(sid + 1)
            pb = paired["save_bits"] if paired else 0
            val = read_bits(data, pos + 9 + sp, sb)
            props.append((s["name"], sid, val - s["save_add"]))
            pos += 9 + sp + sb + pb
        elif enc == 4:
            extra = sb if sb > 0 else 5
            val = read_bits(data, pos + 9, extra)
            props.append((f"enc4:{s['name']}", sid, val))
            pos += 9 + extra
        else:
            val = read_bits(data, pos + 9 + sp, sb) - s["save_add"] if sb > 0 else 0
            props.append((s["name"], sid, val))
            pos += 9 + sp + sb
    return props, pos


# From TC09: 11+8+8+26 = 53 bits type-specific before properties
# From TC09: 11+8+8 = 27 bits for dur fields, then 26 unknown, then terminator
# Hypothesis: TC01 ssd = same 53 bits, then properties
candidates_for_props = [
    (0, "Parser aktuell: max_dur+0, cur_dur+8, props+16"),
    (11, "TC09 Hypothese: 11unknown+maxdur(8)+curdur(8) = +27, props+27"),
    (27, "TC09 + TC01 props: 11unk+8+8, dann props (kein extra-unknown)"),
    (53, "TC09 komplett: 11+8+8+26=53 bits, dann props"),
]

for offset, label in candidates_for_props:
    props_start = TYPE_START + offset
    props, end_pos = try_props_from(props_start, label)
    print(f"  Ab type_start+{offset:2d} ({label}):")
    for name, sid, val in props[:6]:
        status = "[OK]" if sid in [17, 18, 19, 20] else ("0x1FF [OK]" if sid == 0x1FF else "?")
        print(f"    {status} stat={sid:3d} '{name}' val={val}")

    # Check if item #6 starts at end_pos correctly
    if end_pos < len(data) * 8 - 53:
        code6, _ = decode_huffman(data, end_pos + 53)
        loc6 = read_bits(data, end_pos + 35, 3)
        panel6 = read_bits(data, end_pos + 50, 3)
        px6 = read_bits(data, end_pos + 42, 4)
        py6 = read_bits(data, end_pos + 46, 4)
        ident6 = read_bits(data, end_pos + 4, 1)
        match = (
            "*** MATCH!"
            if code6 == "spr" and loc6 == 0 and panel6 == 1 and px6 == 1 and py6 == 0
            else ""
        )
        print(
            f"    -> Item #6 bei bit {end_pos}: code='{code6}' loc={loc6} panel={panel6} pos=({px6},{py6}) ident={ident6} {match}"
        )
    print()

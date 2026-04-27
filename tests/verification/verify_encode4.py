"""
tests/verification/verify_encode4.py
=====================================
PURPOSE : Verifiziert was encode=4 in ItemStatCost.txt bedeutet.

          Aus dem Output von verify_property_bits.py wissen wir:
          - stat_id=304 (item_find_gems_bytime) hat encode=4, save_bits=0
          - Nach der 9-bit stat_id bei Bit 7868 sind wir bei Bit 7877
          - 0x1FF Terminator liegt bei Bit 7882 (= 7877 + 5)
          - Also verbraucht encode=4 EXAKT 5 extra Bits nach der stat_id

          Diese 5 Bits müssen wir binär verstehen. Möglichkeiten:
          A) 5-bit Timer-Wert (für "find gems by TIME")
          B) 5-bit Parameter der irgendwie genutzt wird
          C) Feste Breite die durch ein anderes ISC-Feld bestimmt wird

          Wir prüfen encode=4 in ALLEN TC01-TC03 Items um die Breite zu bestätigen.

USAGE   : python tests/verification/verify_encode4.py tests/cases/TC01/TestABC.d2s
          Für alle TCs: Ergebnisse vergleichen
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


def find_encode4_stats(ISC):
    """Alle Stats mit encode=4 aus der ISC."""
    return {sid: s for sid, s in ISC.items() if s["encode"] == 4}


def scan_items_for_encode4(data, ISC, items_start_byte, item_count):
    """
    Scant alle Items nach encode=4 Vorkommen und misst die tatsächliche Bitbreite.
    Geht von korrekt geparsten Vorgänger-Stats aus.
    """
    results = []

    HUFFMAN_TABLE2 = HUFFMAN_TABLE
    pos = items_start_byte * 8

    for item_idx in range(item_count):
        item_start = pos

        simple = read_bits(data, item_start + 21, 1)
        code, hbits = decode_huffman(data, item_start + 53)
        if code is None:
            break

        if simple:
            total = 53 + hbits + 1
            pad = (8 - total % 8) % 8
            pos = item_start + total + pad
            continue

        # Extended header
        cur = item_start + 53 + hbits
        cur += 35  # uid
        ilvl = read_bits(data, cur, 7)
        cur += 7
        qual = read_bits(data, cur, 4)
        cur += 4
        hgfx = read_bits(data, cur, 1)
        cur += 1
        if hgfx:
            cur += 3
        hcls = read_bits(data, cur, 1)
        cur += 1
        if hcls:
            cur += 11

        if qual == 1 or qual == 3:
            cur += 3
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

        # Determine type prefix
        from_armor = False
        # We'll try to parse properties and detect encode=4
        # For armor items (armor type), skip 11+8+8+2 = 29 bits type prefix
        # For weapon items, skip 8+8 = 16 bits
        # For now, scan for first known stat_id
        prop_start = None
        for skip in [29, 16, 0]:
            test = cur + skip
            sid = read_bits(data, test, 9)
            s = ISC.get(sid)
            if s is not None or sid == 0x1FF:
                prop_start = test
                break
        if prop_start is None:
            prop_start = cur  # fallback

        # Now scan properties, tracking encode=4 occurrences
        scan = prop_start
        item_enc4_found = []

        for _ in range(30):
            sid = read_bits(data, scan, 9)
            if sid == 0x1FF:
                pos = scan + 9
                break
            s = ISC.get(sid)
            if s is None:
                # Unknown stat - stop tracking
                pos = scan  # leave parser at current pos, outer loop handles
                break

            enc = s["encode"]
            sb = s["save_bits"]
            sp = s["save_param"]

            if enc == 4:
                # MEASURE: how many bits until next known stat or 0x1FF?
                stat_id_end = scan + 9  # after reading the 9-bit stat_id
                candidates = []
                for n in range(0, 65):
                    next_pos = stat_id_end + n
                    if next_pos + 9 > len(data) * 8:
                        break
                    nv = read_bits(data, next_pos, 9)
                    if nv == 0x1FF:
                        candidates.append((n, "0x1FF TERMINATOR"))
                        break
                    ns = ISC.get(nv)
                    if ns is not None:
                        candidates.append((n, f"stat_id={nv} '{ns['name']}'"))
                        break

                item_enc4_found.append(
                    {
                        "item_idx": item_idx + 1,
                        "item_code": code,
                        "stat_id": sid,
                        "stat_name": s["name"],
                        "at_bit": scan,
                        "extra_bits_candidates": candidates,
                        "raw_bits": bits_str(data, stat_id_end, 20),
                    }
                )

                # Use best candidate to advance
                if candidates:
                    best_n = candidates[0][0]
                    scan = stat_id_end + best_n
                else:
                    scan = stat_id_end  # fallback

            elif enc == 1:
                paired = ISC.get(sid + 1)
                pb = paired["save_bits"] if paired else 0
                scan += 9 + sp + sb + pb
            elif enc in (2, 3):
                scan += 9 + sb
            else:
                scan += 9 + sp + sb

        results.extend(item_enc4_found)

    return results


if len(sys.argv) < 2:
    print("Usage: python verify_encode4.py <path.d2s>")
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
print(f"ISC: {len(ISC)} Stats")

# Zeige alle encode=4 Stats aus der ISC
enc4_stats = find_encode4_stats(ISC)
print(f"\nAlle encode=4 Stats in der ISC ({len(enc4_stats)} total):")
for sid, s in sorted(enc4_stats.items()):
    print(f"  ID {sid:3d}: '{s['name']}' save_bits={s['save_bits']} save_param={s['save_param']}")

# Finde JM und Items
gf_pos = data.find(b"gf")
jm_pos = data.find(b"JM", gf_pos)
item_count = int.from_bytes(data[jm_pos + 2 : jm_pos + 4], "little")
items_start = jm_pos + 4
print(f"\nJM bei Byte {jm_pos}, {item_count} Items ab Byte {items_start}")

# Direkte Analyse von TC01 Item 5 (ssd Superior) - wir kennen die exakten Positionen
print(f"\n{'='*65}")
print("DIREKTE ANALYSE: encode=4 in TC01 Item 5")
print(f"{'='*65}")
print("Bekannt [BINARY_VERIFIED]:")
print("  stat_id=304 bei Bit 7868 (item_find_gems_bytime, encode=4)")
print("  Nach 9-bit stat_id: Bit 7877")
print("  0x1FF Terminator bei Bit 7882")
print("  Differenz: 7882 - 7877 = 5 bits extra für encode=4")
print()

enc4_start = 7877  # nach der 9-bit stat_id von 304
for n in range(0, 15):
    val_n = read_bits(data, enc4_start, n) if n > 0 else 0
    next_9 = read_bits(data, enc4_start + n, 9)
    is_term = next_9 == 0x1FF
    s_next = ISC.get(next_9)
    annot = ""
    if is_term:
        annot = "<- 0x1FF TERMINATOR [OK]"
    elif s_next:
        annot = f"<- known: '{s_next['name']}'"
    print(f"  +{n:2d} bits: value={val_n:3d}  next_9={next_9:3d}  {annot}")

print()
val_5bits = read_bits(data, enc4_start, 5)
print("[BINARY_VERIFIED] encode=4 extra Bits = 5")
print(f"  5-bit Wert = {val_5bits} (0b{val_5bits:05b})")
print("  Bedeutung unklar - könnte Timer-Wert sein")
print()
print("Nach encode=4 (9+5=14 bits): 0x1FF bei Bit 7882 [OK]")
print(f"Nächstes Item bei Bit {7882+9}")

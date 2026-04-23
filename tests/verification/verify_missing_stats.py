"""
tests/verification/verify_missing_stats.py
==========================================
PURPOSE : Discover stat IDs present in .d2s files but missing from ISC.
          For each unknown stat_id, determines how many bits it consumes
          by brute-force: tries all save_bits values 0-32 and checks
          if the result matches 0x1FF terminator or a known next stat.

USAGE   : python tests/verification/verify_missing_stats.py <path.d2s>
          python tests/verification/verify_missing_stats.py tests/cases/TC01/TestABC.d2s
          python tests/verification/verify_missing_stats.py tests/cases/TC03/TestWarlock.d2s
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
        print(f"ISC geladen: {len(ISC)} Stats (max_id={max(ISC.keys())})")
        return ISC
    print("ISC nicht gefunden!")
    return ISC


def try_read_props(data, pos, ISC, max_depth=30):
    """
    Try to read the property list from pos using ISC.
    Returns (success, end_pos, unknown_stats) where:
      success = True if 0x1FF was found cleanly
      end_pos = bit after 0x1FF
      unknown_stats = list of (stat_id, pos_before_statid)
    """
    unknown_stats = []
    cur = pos
    for _ in range(max_depth):
        stat_id = read_bits(data, cur, 9)
        if stat_id == 0x1FF:
            return True, cur + 9, unknown_stats
        s = ISC.get(stat_id)
        if s is None:
            unknown_stats.append((stat_id, cur))
            return False, cur, unknown_stats
        param_bits = s["save_param"]
        val_bits = s["save_bits"]
        enc = s["encode"]
        if enc == 1:
            paired = ISC.get(stat_id + 1)
            val2_bits = paired["save_bits"] if paired else 0
            cur += 9 + param_bits + val_bits + val2_bits
        elif enc in (2, 3):
            cur += 9 + val_bits
        else:
            cur += 9 + param_bits + val_bits
    return False, cur, unknown_stats


def find_stat_save_bits(data, pos_after_statid, ISC, search_bits=40):
    """
    Given that we just read an unknown stat_id at (pos_after_statid - 9),
    scan bits 0..search_bits to find how many value bits this stat has.
    For each candidate n, check if the remaining bits align cleanly
    to 0x1FF or to a known stat_id.

    Returns list of (n_bits, reason) that seem valid.
    """
    candidates = []
    for n in range(0, search_bits + 1):
        next_pos = pos_after_statid + n
        if next_pos + 9 > len(data) * 8:
            break
        next_val = read_bits(data, next_pos, 9)
        if next_val == 0x1FF:
            candidates.append((n, f"-> 0x1FF terminator at bit {next_pos}"))
        elif next_val in ISC:
            s = ISC[next_val]
            candidates.append((n, f"-> known stat_id={next_val} '{s['name']}' at bit {next_pos}"))
    return candidates


def parse_item(data, item_start, ISC):
    """Parse one item fully, returning (code, next_item_start, unknown_stats_found)."""
    unknown_stats = []

    simple = read_bits(data, item_start + 21, 1)
    code, hbits = decode_huffman(data, item_start + 53)
    if code is None:
        return None, None, []

    if simple:
        total_before_pad = 53 + hbits + 1
        pad = (8 - total_before_pad % 8) % 8
        return code, item_start + total_before_pad + pad, []

    # Extended header
    pos = item_start + 53 + hbits
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

    # Quality-specific
    if qual == 1 or qual == 3:
        pos += 3
    elif qual == 4:
        pos += 22
    elif qual == 5:
        pos += 12
    elif qual in (6, 8):
        pos += 16
        for _ in range(6):
            if read_bits(data, pos, 1):
                pos += 12
            else:
                pos += 1
    elif qual == 7:
        pos += 12

    # Runeword/personalized
    if read_bits(data, item_start + 26, 1):
        pos += 16
    if read_bits(data, item_start + 24, 1):
        while pos + 8 <= len(data) * 8:
            b = read_bits(data, pos, 8)
            pos += 8
            if b == 0:
                break

    pos += 1  # timestamp

    # Weapon (8+8) vs armor (11+8+8+2) - try to determine from item code
    # For now: skip to property list using ISC, trying both layouts
    # We try armor layout first, then weapon, then no prefix
    type_start = pos
    found_end = None

    for skip_bits in [29, 16, 0]:  # armor=11+8+8+2=29, weapon=8+8=16, misc=0
        test_pos = type_start + skip_bits
        ok, end_pos, unknowns = try_read_props(data, test_pos, ISC)
        if ok:
            found_end = end_pos
            unknown_stats = unknowns
            break
        elif unknowns:
            # Unknown stat found - try to determine its save_bits
            sid, sid_pos = unknowns[0]
            candidates = find_stat_save_bits(data, sid_pos + 9, ISC)
            if candidates:
                # Use the first valid candidate
                n_bits, reason = candidates[0]
                unknown_stats.append(
                    {
                        "stat_id": sid,
                        "at_bit": sid_pos,
                        "skip_bits_before": skip_bits,
                        "candidates": candidates[:5],
                    }
                )
                # Try to continue from here with the first candidate
                test_pos2 = sid_pos + 9 + n_bits
                ok2, end_pos2, unknowns2 = try_read_props(data, test_pos2, ISC)
                if ok2:
                    found_end = end_pos2
                    break
            else:
                unknown_stats.append(
                    {
                        "stat_id": sid,
                        "at_bit": sid_pos,
                        "skip_bits_before": skip_bits,
                        "candidates": [],
                    }
                )

    if found_end is None:
        # Last resort: scan for 0x1FF from type_start
        for off in range(0, 300):
            if read_bits(data, type_start + off, 9) == 0x1FF:
                found_end = type_start + off + 9
                break

    return code, found_end, unknown_stats


def main():
    if len(sys.argv) < 2:
        print("Usage: python verify_missing_stats.py <path.d2s>")
        sys.exit(1)

    data = Path(sys.argv[1]).read_bytes()
    print(f"Datei: {sys.argv[1]} ({len(data)} bytes)")

    excel_base = None
    for c in [Path.cwd() / "excel", Path(sys.argv[1]).parent.parent.parent / "excel"]:
        if c.exists():
            excel_base = c
            break
    if not excel_base:
        print("FEHLER: excel/ nicht gefunden")
        sys.exit(1)
    ISC = load_isc(excel_base)

    # Find JM and items start
    jm_pos = data.find(b"gf")
    if jm_pos < 0:
        print("'gf' nicht gefunden")
        sys.exit(1)
    # Find first JM after gf
    jm_item = data.find(b"JM", jm_pos)
    items_start = jm_item + 4
    item_count = int.from_bytes(data[jm_item + 2 : jm_item + 4], "little")
    print(f"JM bei Byte {jm_item}, {item_count} Items, Start Byte {items_start}\n")

    pos = items_start * 8
    all_unknown = {}  # stat_id -> set of candidate save_bits

    for i in range(item_count):
        code, next_pos, unknown_stats = parse_item(data, pos, ISC)
        print(f"Item #{i+1:2d} bei Bit {pos:6d} (Byte {pos//8:4d}): code='{code}'", end="")
        if next_pos:
            print(f" -> nächstes Item bei Bit {next_pos} (Byte {next_pos//8})")
        else:
            print(" -> FEHLER: Ende nicht gefunden")

        for u in unknown_stats:
            sid = u["stat_id"]
            print(
                f"  [!]  Unbekannte stat_id={sid} bei Bit {u['at_bit']} (skip_bits={u['skip_bits_before']})"
            )
            for n, reason in u["candidates"]:
                print(f"     Kandidat: save_bits={n:2d}  {reason}")
            if u["candidates"]:
                best = u["candidates"][0][0]
                if sid not in all_unknown:
                    all_unknown[sid] = {}
                best_reason = u["candidates"][0][1]
                all_unknown[sid][best] = all_unknown[sid].get(best, 0) + 1

        if next_pos:
            pos = next_pos
        else:
            print("  Abbruch - konnte Item-Ende nicht bestimmen")
            break

    print(f"\n{'='*60}")
    print("ERGEBNIS: Fehlende Stats in ISC")
    print(f"{'='*60}")
    if all_unknown:
        print("\nFüge folgendes zu einer ISC-Patch-Datei hinzu:")
        for sid in sorted(all_unknown.keys()):
            votes = all_unknown[sid]
            best_bits = max(votes, key=votes.get)
            print(f"  stat_id={sid:3d}  save_bits={best_bits}  (belegt {votes[best_bits]}x)")
    else:
        print("Alle Stats bekannt - ISC vollständig!")


if __name__ == "__main__":
    main()


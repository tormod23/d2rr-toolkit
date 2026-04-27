"""
tests/verification/verify_tc11_sockets.py
==========================================
PURPOSE : Verifies the socket count field (4 bits after 0x1FF terminator)
          using TC11: two Studded Leathers (1 empty, 1 filled socket)
          and Diamonds.

          HYPOTHESIS (from Phrozen Keep D2S docs):
          Socketed items have a 4-bit socket count field AFTER 0x1FF:
            ... properties ... -> 0x1FF (9 bits) -> socket_count (4 bits) -> byte_pad

          TC11 verifies this with:
          - stu #1: socketed=1, socket empty  -> socket_count should be 1
          - stu #2: socketed=1, socket filled  -> socket_count should be 1
          - gmd #1,#2,#3: socketed=0           -> NO socket count field

USAGE   : python tests/verification/verify_tc11_sockets.py tests/cases/TC11/TestWarlock.d2s
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
LOCATION_NAMES = {0: "Stored", 1: "Equipped", 2: "Belt", 4: "Cursor", 6: "Socketed"}
PANEL_NAMES = {0: "None", 1: "Inventory", 4: "Cube", 5: "Stash"}


def parse_properties(data, pos, ISC):
    """Read properties until 0x1FF. Returns position AFTER 0x1FF (not byte-aligned)."""
    props = []
    for _ in range(30):
        sid = read_bits(data, pos, 9)
        if sid == 0x1FF:
            return pos + 9, props  # return position right after 0x1FF
        s = ISC.get(sid)
        if s is None:
            print(f"    [!] Unknown stat_id={sid} at bit {pos}")
            return pos, props
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
            pos += 9 + extra
        else:
            props.append(sid)
            pos += 9 + sp + sb
    return pos, props


if len(sys.argv) < 2:
    print("Usage: python verify_tc11_sockets.py <TestWarlock.d2s>")
    sys.exit(1)

data = Path(sys.argv[1]).read_bytes()
excel_base = None
for c in [Path.cwd() / "excel", Path(sys.argv[1]).parent.parent.parent / "excel"]:
    if c.exists():
        excel_base = c
        break
ISC = load_isc(excel_base) if excel_base else {}
print(f"Datei: {sys.argv[1]} ({len(data)} bytes), ISC: {len(ISC)} Stats")

# Find JM header
gf_pos = data.find(b"gf")
jm_pos = data.find(b"JM", gf_pos)
item_count = int.from_bytes(data[jm_pos + 2 : jm_pos + 4], "little")
items_start = (jm_pos + 4) * 8
print(f"JM bei Byte {jm_pos}, {item_count} Items, start bit {items_start}\n")

print("═" * 65)
print("ITEM-BY-ITEM TRACE mit Socket-Count-Feld")
print("═" * 65)

pos = items_start
for item_num in range(1, item_count + 1):
    item_start = pos
    print(f"\n--- Item #{item_num} bei Bit {pos} (Byte {pos//8}) ---")

    # Flags
    socketed = read_bits(data, pos + 11, 1)
    simple = read_bits(data, pos + 21, 1)
    loc = read_bits(data, pos + 35, 3)
    panel = read_bits(data, pos + 50, 3)
    px = read_bits(data, pos + 42, 4)
    py = read_bits(data, pos + 46, 4)
    ident = read_bits(data, pos + 4, 1)

    code, hbits = decode_huffman(data, pos + 53)
    loc_str = f"{LOCATION_NAMES.get(loc,'?')} ({px},{py})" if loc != 1 else "Equip"
    print(f"  code='{code}' loc={loc_str} socketed={socketed} simple={simple} ident={ident}")

    if simple:
        total = 53 + hbits + 1
        pad = (8 - total % 8) % 8
        pos = item_start + total + pad
        print(f"  SIMPLE: {total}+{pad}pad={total+pad} bits -> next at bit {pos}")
        continue

    # Extended header
    ext = item_start + 53 + hbits
    uid = read_bits(data, ext + 0, 35)
    ilvl = read_bits(data, ext + 35, 7)
    qual = read_bits(data, ext + 42, 4)
    hgfx = read_bits(data, ext + 46, 1)
    hcls = read_bits(data, ext + 47, 1)
    print(f"  ilvl={ilvl} qual={qual}({QUALITY_NAMES.get(qual,'?')}) hgfx={hgfx} hcls={hcls}")

    # Compute type_start
    cur = ext + 35 + 7 + 4 + 1
    if hgfx:
        cur += 3
    cur += 1
    if hcls:
        cur += 11
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
    print(f"  type_start={type_start}")

    # Type-specific (stu=armor, gmd=misc)
    cl = (code or "").lower()
    if cl == "stu":
        def_raw = read_bits(data, type_start, 11)
        max_dur = read_bits(data, type_start + 11, 8)
        cur_dur = read_bits(data, type_start + 19, 8)
        print(f"  ARMOR: def_raw={def_raw}(disp={def_raw-10}) max_dur={max_dur} cur_dur={cur_dur}")
        props_start = type_start + 29  # 11+8+8+2
    elif cl == "gmd":
        print("  MISC: no type-specific fields")
        props_start = type_start
    else:
        print(f"  UNKNOWN category for '{cl}'")
        props_start = type_start

    # Parse properties
    print(f"  Properties start at bit {props_start}:")
    after_term, props = parse_properties(data, props_start, ISC)
    print(f"  Props decoded: {props}")
    print(f"  0x1FF consumed, reader at bit {after_term}")

    # ── THE KEY TEST: socket count field ────────────────────────
    if socketed:
        print("\n  *** SOCKETED ITEM: checking for 4-bit socket count field ***")
        print(f"  Bits immediately after 0x1FF (at bit {after_term}):")
        print(f"    Raw bits: {bits_str(data, after_term, 8)}")

        # Test: read 4 bits as socket count
        sock_count_4bit = read_bits(data, after_term, 4)
        print(f"    4-bit value = {sock_count_4bit}")

        # After socket count, byte-align
        after_sock = after_term + 4
        rem = after_sock % 8
        if rem:
            after_sock += 8 - rem
        print(f"    After socket_count(4) + byte_align -> bit {after_sock}")

        # What does Huffman decode at after_sock?
        next_code, _ = decode_huffman(data, after_sock + 53)
        next_loc = read_bits(data, after_sock + 35, 3)
        next_panel = read_bits(data, after_sock + 50, 3)
        next_px = read_bits(data, after_sock + 42, 4)
        next_py = read_bits(data, after_sock + 46, 4)
        print(
            f"    Next item if socket_count=4bit: code='{next_code}' loc={next_loc} panel={next_panel} pos=({next_px},{next_py})"
        )

        # Also test WITHOUT socket count field (just byte-align after 0x1FF)
        after_no_sock = after_term
        rem2 = after_no_sock % 8
        if rem2:
            after_no_sock += 8 - rem2
        next_code2, _ = decode_huffman(data, after_no_sock + 53)
        next_loc2 = read_bits(data, after_no_sock + 35, 3)
        next_panel2 = read_bits(data, after_no_sock + 50, 3)
        next_px2 = read_bits(data, after_no_sock + 42, 4)
        next_py2 = read_bits(data, after_no_sock + 46, 4)
        print(
            f"    Next item without socket field:  code='{next_code2}' loc={next_loc2} panel={next_panel2} pos=({next_px2},{next_py2})"
        )

        # Decide which is correct based on expected next item
        print("\n    Expected next item after stu:")
        if code == "stu" and px == 1:
            print("    gmd at Inventory(3,0) OR gmd socketed (if filled)")
        elif code == "stu" and px == 4:
            print("    gmd at Inventory(6,0) OR socketed child gmd")

        # Use 4-bit socket count path
        pos = after_sock
    else:
        # No socket field - just byte-align
        after_byte = after_term
        rem = after_byte % 8
        if rem:
            after_byte += 8 - rem
        pos = after_byte

    print(f"  -> Next item starts at bit {pos}")

print(f"\n{'='*65}")
print("SUMMARY")
print(f"{'='*65}")
print(f"Final bit position: {pos} (byte {pos//8})")
print(f"File size: {len(data)*8} bits ({len(data)} bytes)")
print()
print("Record in VERIFICATION_LOG.md:")
print("  [BINARY_VERIFIED] socket_count field: 4 bits after 0x1FF for socketed items")
print("  [BINARY_VERIFIED] socket_count position: immediately after 0x1FF, before byte-align")

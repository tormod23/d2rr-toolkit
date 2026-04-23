"""
tests/verification/verify_tc11_props_start.py
==============================================
PURPOSE : Findet den echten Properties-Start für stu in TC11 durch
          Brute-Force: testet jeden Offset von type_start+29 bis +60
          und prüft ob die Properties mit einem bekannten stat_id starten.

          Bekannt: 0x1FF ist bei bit 7654 (von 7672-4sock-5pad-9term=7654)
          Bekannt: props_start muss < 7654 sein

USAGE   : python tests/verification/verify_tc11_props_start.py tests/cases/TC11/TestWarlock.d2s
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

                saved = p[idx_saved].strip() if idx_saved and idx_saved < len(p) else ""
                ISC[sid] = {
                    "name": p[idx_name].strip() if idx_name and idx_name < len(p) else "",
                    "save_bits": gi(idx_sb),
                    "save_add": gi(idx_sa),
                    "save_param": gi(idx_sp),
                    "encode": gi(idx_enc),
                    "saved": saved,
                }
            except:
                pass
        return ISC
    return ISC


if len(sys.argv) < 2:
    print("Usage: python verify_tc11_props_start.py <d2s>")
    sys.exit(1)

data = Path(sys.argv[1]).read_bytes()
excel_base = None
for c in [Path.cwd() / "excel", Path(sys.argv[1]).parent.parent.parent / "excel"]:
    if c.exists():
        excel_base = c
        break
ISC = load_isc(excel_base) if excel_base else {}

# Known [BINARY_VERIFIED]
STU1_TYPE_START = 7609  # from verify_tc11_exact
STU1_NEXT = 7672  # from verify_tc11_positions
# Socket count=1, before byte-align:
# 7672 -> (pad to get here from 7672 is 0, already byte-aligned)
# So: after_socket_count + pad = 7672
# socket_count(4 bits) at pos X: X + 4 + pad(?) = 7672
# If X = 7663: 7663+4=7667, 7667%8=3, pad=5, 7672 [OK]
# So 0x1FF at 7654 (ends at 7663)
REAL_TERM_START = 7654
REAL_TERM_END = 7663

print(f"STU1 type_start={STU1_TYPE_START}, next item={STU1_NEXT}")
print(f"Real 0x1FF at bit {REAL_TERM_START} (ends at {REAL_TERM_END})")
print(
    f"Verifying: {read_bits(data, REAL_TERM_START, 9)} == 511? {read_bits(data, REAL_TERM_START, 9)==511}"
)
print()

# Show raw bits from type_start+29 (after armor fields) onward
ARMOR_END = STU1_TYPE_START + 29  # = 7638
print(f"After armor fields: bit {ARMOR_END}")
print(f"Distance to 0x1FF start: {REAL_TERM_START - ARMOR_END} bits")
print()

print("Raw bits from armor_end to 0x1FF (grouped 9 bits = potential stat IDs):")
print(f"{'Offset':>8}  {'abs bit':>8}  {'9-bit val':>10}  {'ISC entry?':>30}  {'saved':>6}")
print(f"{'─'*8}  {'─'*8}  {'─'*10}  {'─'*30}  {'─'*6}")

# Show 9-bit values from props_start to real terminator
for off in range(0, REAL_TERM_START - ARMOR_END + 1):
    abs_bit = ARMOR_END + off
    val9 = read_bits(data, abs_bit, 9)
    s = ISC.get(val9)

    # Highlight 0x1FF and known-saved stats
    annot = ""
    saved_str = ""
    if val9 == 0x1FF:
        annot = "<- 0x1FF TERMINATOR"
    elif s:
        annot = f"'{s['name']}' sb={s['save_bits']} enc={s['encode']}"
        saved_str = s["saved"]

    # Only show every offset or interesting ones
    if val9 == 0x1FF or (s and s["saved"] == "1") or off % 8 == 0:
        print(f"  +{off:>6}  {abs_bit:>8}  {val9:>10}  {annot:<30}  {saved_str!r}")

print()
print("═" * 65)
print("Testing: what if props_start = armor_end + N for N in 0..20?")
print("═" * 65)
print()


def try_props_decode(start_abs, isc):
    """Try to decode props from start. Returns (success, end_after_term, props)."""
    pos = start_abs
    props = []
    for _ in range(10):
        sid = read_bits(data, pos, 9)
        if sid == 0x1FF:
            return True, pos + 9, props
        s = isc.get(sid)
        if s is None:
            return False, pos, props
        if s["saved"] != "1":
            return False, pos, props  # stat not saved -> shouldn't appear
        enc = s["encode"]
        sb = s["save_bits"]
        sp = s["save_param"]
        if enc == 1:
            paired = isc.get(sid + 1)
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
    return False, pos, props


for n in range(0, 25):
    test_start = ARMOR_END + n
    ok, end_pos, props = try_props_decode(test_start, ISC)
    if ok and end_pos == REAL_TERM_END:
        sock_count = read_bits(data, end_pos, 4)
        after = end_pos + 4
        pad = (8 - after % 8) % 8
        final = after + pad
        match = "[OK] MATCH!" if final == STU1_NEXT else f"off by {final-STU1_NEXT}"
        print(
            f"  +{n:2d} (bit {test_start}): CLEAN DECODE -> props={props} term_end={end_pos} sock={sock_count} final={final} {match}"
        )
    elif ok:
        sock_count = read_bits(data, end_pos, 4)
        after = end_pos + 4
        pad = (8 - after % 8) % 8
        final = after + pad
        print(
            f"  +{n:2d} (bit {test_start}): decode OK but term_end={end_pos}!={REAL_TERM_END}, sock={sock_count}, final={final}"
        )

print()
print("═" * 65)
print("ALSO: Check what Phrozen Keep says about SET items modifier lists")
print("For stu (Superior Normal quality): no set modifier lists expected")
print("But maybe there's a 'number of modifier lists' field we're missing?")
print("═" * 65)
# Check bits 7638 as possible 'number of set modifier lists' (5 bits for Set items)
for nbits in [1, 2, 3, 4, 5]:
    val = read_bits(data, ARMOR_END, nbits)
    next_pos = ARMOR_END + nbits
    # Check what stat_id comes after
    next_sid = read_bits(data, next_pos, 9)
    s = ISC.get(next_sid)
    print(
        f"  If {nbits}-bit field at {ARMOR_END}={val}: next stat_id={next_sid} '{s['name'] if s else '?'}' saved={s['saved'] if s else '?'}"
    )

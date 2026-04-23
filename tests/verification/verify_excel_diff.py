"""
tests/verification/verify_excel_diff.py
========================================
PURPOSE : Vergleicht original vs reimagined Versionen von
          armor.txt, weapons.txt und misc.txt.

          Zeigt:
          - Neue Item-Codes die nur in Reimagined existieren
          - Entfernte Codes die nur in Original existieren
          - Geänderte Felder bei bestehenden Codes

USAGE   : python tests/verification/verify_excel_diff.py
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

EXCEL_BASE = Path.cwd() / "excel"
ORIGINAL = EXCEL_BASE / "original"
REIMAGINED = EXCEL_BASE / "reimagined"


def load_file(path):
    """Load tab-delimited txt file. Returns (headers, {code: row_dict})."""
    if not path.exists():
        print(f"  FEHLER: {path} nicht gefunden!")
        return [], {}
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    if not lines:
        return [], {}
    headers = lines[0].strip().split("\t")
    try:
        code_idx = headers.index("code")
    except ValueError:
        print(f"  FEHLER: Keine 'code' Spalte in {path}")
        return headers, {}
    rows = {}
    for line in lines[1:]:
        p = line.strip().split("\t")
        if len(p) <= code_idx:
            continue
        code = p[code_idx].strip().lower()
        if not code or code == "expansion":
            continue
        row = {}
        for i, h in enumerate(headers):
            row[h] = p[i].strip() if i < len(p) else ""
        rows[code] = row
    return headers, rows


def diff_file(fname, key_fields=None):
    """Compare original vs reimagined for one file."""
    orig_path = ORIGINAL / fname
    reim_path = REIMAGINED / fname

    print(f"\n{'='*70}")
    print(f"  DIFF: {fname}")
    print(f"{'='*70}")

    orig_headers, orig = load_file(orig_path)
    reim_headers, reim = load_file(reim_path)

    if not orig and not reim:
        return []

    print(f"  Original:   {len(orig)} Codes")
    print(f"  Reimagined: {len(reim)} Codes")

    orig_set = set(orig.keys())
    reim_set = set(reim.keys())

    only_in_reim = sorted(reim_set - orig_set)
    only_in_orig = sorted(orig_set - reim_set)
    in_both = orig_set & reim_set

    # ── Neue Codes (nur in Reimagined) ──────────────────────────────────
    print(f"\n  [+] NUR IN REIMAGINED ({len(only_in_reim)} neue Codes):")
    if only_in_reim:
        # Show relevant fields: code, name, type (if exists)
        fields_to_show = ["code", "name", "type", "type2", "compactsave"]
        for code in only_in_reim:
            row = reim[code]
            info_parts = []
            for f in fields_to_show:
                if f in row and row[f]:
                    info_parts.append(f"{f}={row[f]!r}")
            print(f"    + {code:<10}  {', '.join(info_parts)}")
    else:
        print("    (keine)")

    # ── Entfernte Codes (nur in Original) ────────────────────────────────
    print(f"\n  [-] NUR IN ORIGINAL ({len(only_in_orig)} entfernte Codes):")
    if only_in_orig:
        for code in only_in_orig:
            row = orig[code]
            name = row.get("name", "")
            print(f"    - {code:<10}  name={name!r}")
    else:
        print("    (keine)")

    # ── Geänderte Felder ─────────────────────────────────────────────────
    changed = []
    for code in sorted(in_both):
        orig_row = orig[code]
        reim_row = reim[code]
        all_keys = set(orig_row.keys()) | set(reim_row.keys())
        diffs = []
        for k in sorted(all_keys):
            ov = orig_row.get(k, "")
            rv = reim_row.get(k, "")
            if ov != rv:
                diffs.append((k, ov, rv))
        if diffs:
            changed.append((code, diffs))

    print(f"\n  [~] GEÄNDERTE CODES ({len(changed)} Codes mit Unterschieden):")
    if changed:
        for code, diffs in changed[:30]:  # Show max 30
            print(f"    ~ {code}:")
            for field, oval, rval in diffs[:5]:  # Max 5 fields per item
                print(f"        {field}: {oval!r} -> {rval!r}")
        if len(changed) > 30:
            print(f"    ... und {len(changed)-30} weitere")
    else:
        print("    (keine Änderungen)")

    return only_in_reim


# Run diff for all three files
all_new_codes = {}

new_armor = diff_file("armor.txt")
new_weapons = diff_file("weapons.txt")
new_misc = diff_file("misc.txt")

for code in new_armor:
    all_new_codes[code] = "ARMOR"
for code in new_weapons:
    all_new_codes[code] = "WEAPON"
for code in new_misc:
    all_new_codes[code] = "MISC"

# Summary: classify the TC03 missing codes
print(f"\n{'='*70}")
print("  KLASSIFIKATION DER FEHLENDEN ITEM-CODES AUS TC01/TC03")
print(f"{'='*70}")

missing_from_tc = [
    "cb",
    "wxbb",
    "wvbl",
    "h",
    "wkb",
    "8stu",
    "wjew",
    "97d",
    "wamu",
    "w97d",
    "mnd",
    "wbwx",
    "wbwup",
    "",
]

print()
found_count = 0
for code in sorted(missing_from_tc):
    if not code:
        print("  (leer):  nicht in Diff gefunden")
        continue
    typ = all_new_codes.get(code.lower())
    if typ:
        print(f"  '{code}': {typ}  <- jetzt klassifiziert!")
        found_count += 1
    else:
        print(f"  '{code}': IMMER NOCH NICHT GEFUNDEN")

print(f"\n  Gefunden: {found_count}/{len([c for c in missing_from_tc if c])}")
if found_count < len([c for c in missing_from_tc if c]):
    print("\n  Noch nicht gefundene Codes könnten in anderen Excel-Dateien")
    print("  stehen (z.B. uniqueitems.txt, setitems.txt) oder haben")
    print("  einen anderen Code als erwartet.")

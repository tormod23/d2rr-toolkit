"""
tests/verification/verify_find_missing_codes.py
================================================
PURPOSE : Durchsucht ALLE Excel-Dateien in excel/reimagined/ und excel/original/
          nach den fehlenden Item-Codes aus TC01/TC03.

USAGE   : python tests/verification/verify_find_missing_codes.py
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

EXCEL_BASE = Path.cwd() / "excel"
MISSING = [
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
]

print("Suche nach fehlenden Codes in ALLEN Excel-Dateien")
print(f"Gesuchte Codes: {MISSING}")
print()

for subdir in ("reimagined", "original"):
    excel_dir = EXCEL_BASE / subdir
    if not excel_dir.exists():
        print(f"  {subdir}/: nicht gefunden")
        continue

    txt_files = sorted(excel_dir.glob("*.txt"))
    print(f"{'='*60}")
    print(f"  {subdir}/ ({len(txt_files)} .txt Dateien)")
    print(f"{'='*60}")

    for txt_file in txt_files:
        try:
            with open(txt_file, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception:
            continue
        if not lines:
            continue

        headers = lines[0].strip().split("\t")

        # Find all columns that might contain item codes
        code_columns = []
        for i, h in enumerate(headers):
            if h.lower() in (
                "code",
                "code1",
                "code2",
                "code3",
                "item",
                "itype1",
                "itype2",
                "itype3",
                "etype1",
                "etype2",
            ):
                code_columns.append(i)

        if not code_columns:
            # Fallback: check column 0 and 1
            code_columns = [0, 1, 2]

        # Search each row for matching codes
        found_in_file = {}
        for line_num, line in enumerate(lines[1:], 2):
            p = line.strip().split("\t")
            for col_idx in code_columns:
                if col_idx >= len(p):
                    continue
                cell_val = p[col_idx].strip().lower()
                if cell_val in [c.lower() for c in MISSING]:
                    original_code = next(c for c in MISSING if c.lower() == cell_val)
                    col_name = headers[col_idx] if col_idx < len(headers) else f"col{col_idx}"
                    # Get name column if available
                    name = ""
                    for ni, nh in enumerate(headers):
                        if nh.lower() == "name" and ni < len(p):
                            name = p[ni].strip()
                            break
                    if original_code not in found_in_file:
                        found_in_file[original_code] = []
                    found_in_file[original_code].append(
                        f"  Zeile {line_num}, Spalte '{col_name}', name='{name}'"
                    )

        if found_in_file:
            print(f"\n  *** {txt_file.name} ***")
            for code, locations in sorted(found_in_file.items()):
                print(f"    Code '{code}':")
                for loc in locations[:3]:
                    print(f"      {loc}")
    print()

# Also do a raw text search as backup
print(f"{'='*60}")
print("  RAW TEXT SUCHE (Backup)")
print(f"{'='*60}")
for subdir in ("reimagined", "original"):
    excel_dir = EXCEL_BASE / subdir
    if not excel_dir.exists():
        continue
    for txt_file in sorted(excel_dir.glob("*.txt")):
        try:
            content = txt_file.read_text(encoding="utf-8", errors="replace").lower()
        except:
            continue
        for code in MISSING:
            # Check for tab-delimited exact match
            if (
                f"\t{code.lower()}\t" in content
                or f"\t{code.lower()}\n" in content
                or content.startswith(f"{code.lower()}\t")
            ):
                print(f"  Raw match: '{code}' in {subdir}/{txt_file.name}")

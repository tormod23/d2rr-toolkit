"""
tests/verification/verify_header.py
====================================
PURPOSE : Verify the most fundamental D2S header fields against real binary data.
          This is the FIRST script to run in the entire project.
          It uses ZERO parser logic - only raw byte reads and hex dumps.

STATUS  : [SPEC_ONLY] - running this script produces [BINARY_VERIFIED] evidence.
          Update VERIFICATION_LOG.md with the output before writing any parser code.

COVERS  : VER-001 (Signature, Version)
          VER-002 (Character Name)
          VER-003 (Header size / "gf" location)
          VER-004 (Character Class ID)

USAGE   : python tests/verification/verify_header.py <path_to_d2s_file>
          python tests/verification/verify_header.py C:/path/to/character.d2s

OUTPUT  : Human-readable hex dumps + PASS/FAIL for each verifiable field.
          Copy this output into VERIFICATION_LOG.md entry.

RULES   : - This script MUST NOT import anything from src/d2rr_toolkit/
          - No parsing logic, no Construct, no BitReader
          - Only stdlib + hashlib for SHA256 fingerprinting
          - When in doubt: dump more bytes, not fewer

DATE    : 2026-03-24
"""

import hashlib
import sys
from pathlib import Path

# Force UTF-8 output - required on Windows where default encoding is cp1252
sys.stdout.reconfigure(encoding="utf-8")

# ============================================================
# SPEC CONSTANTS - ALL [SPEC_ONLY] UNTIL VERIFIED
# These values are used ONLY to check against, not to parse with.
# ============================================================

SPEC_SIGNATURE = 0xAA55AA55  # [SPEC_ONLY] Magic bytes at offset 0
SPEC_VERSION_CLASSIC_MAX = 96  # [SPEC_ONLY] Highest classic LoD version
SPEC_VERSION_D2R_V97 = 97  # [SPEC_ONLY] D2R launch version
SPEC_VERSION_D2R_V98 = 98  # [SPEC_ONLY] RotW version (per D2CE project)
SPEC_VERSION_REIMAGINED = 105  # [SPEC_ONLY] Reimagined mod (user report - VERIFY!)
SPEC_NAME_OFFSET = 0x14  # [SPEC_ONLY] Character name starts here
SPEC_NAME_LENGTH = 16  # [SPEC_ONLY] 16 bytes, null-terminated
SPEC_CLASS_OFFSET = 0x28  # [SPEC_ONLY] Character class byte
SPEC_LEVEL_OFFSET = 0x2B  # [SPEC_ONLY] Character level byte
SPEC_STATS_HEADER = b"gf"  # [SPEC_ONLY] Stats section magic bytes
SPEC_HEADER_SIZE_V97 = 765  # [SPEC_ONLY] Header size for v97
SPEC_HEADER_SIZE_V98 = 813  # [SPEC_ONLY] Possible v98 size (765 + 48 extended)
SPEC_SEARCH_LIMIT = 1024  # Max bytes to search for "gf" marker

# [SPEC_ONLY] Class names - verify class byte 0x28
CLASS_NAMES = {
    0: "Amazon",
    1: "Sorceress",
    2: "Necromancer",
    3: "Paladin",
    4: "Barbarian",
    5: "Druid",
    6: "Assassin",
    7: "Warlock",  # [SPEC_ONLY] Reign of the Warlock new class
}


# ============================================================
# DISPLAY HELPERS
# ============================================================


def print_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def hex_dump(data: bytes, start_offset: int, length: int, label: str) -> None:
    """Dump bytes as annotated hex - the core verification tool.

    Format: [LABEL] offset=0x00AB (171d): AA 55 AA 55 ...  |..U.|
    """
    chunk = data[start_offset : start_offset + length]
    hex_part = " ".join(f"{b:02X}" for b in chunk)
    ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
    print(
        f"  [{label:30s}] "
        f"offset=0x{start_offset:04X} ({start_offset:4d}d)  "
        f"{hex_part:<48s}  |{ascii_part}|"
    )


def uint32_le(data: bytes, offset: int) -> int:
    """Read a 4-byte little-endian unsigned integer from data."""
    return int.from_bytes(data[offset : offset + 4], "little")


def check(label: str, condition: bool, found: str, expected: str) -> bool:
    """Print a PASS/FAIL line and return the result."""
    status = "[OK] PASS" if condition else "[NO] FAIL"
    print(f"  {status}  {label}")
    if not condition:
        print(f"         Expected: {expected}")
        print(f"         Found:    {found}")
    return condition


# ============================================================
# VERIFICATION FUNCTIONS
# ============================================================


def verify_file_fingerprint(path: Path, data: bytes) -> None:
    """Compute and display SHA256 hash of the test file.

    Add this hash to VERIFICATION_LOG.md so the verification is reproducible.
    """
    sha256 = hashlib.sha256(data).hexdigest()
    print(f"  File path   : {path}")
    print(f"  File size   : {len(data)} bytes (0x{len(data):X})")
    print(f"  SHA256      : {sha256}")
    print()
    print("  *** COPY THIS SHA256 INTO VERIFICATION_LOG.md ***")


def verify_signature(data: bytes) -> bool:
    """VER-001a: Verify the magic signature bytes at offset 0.

    [SPEC_ONLY] Expected: 0xAA55AA55
    """
    print_section("VER-001a: File Signature (offset 0x0000)")
    hex_dump(data, 0x00, 4, "Signature bytes")
    found = uint32_le(data, 0x00)
    return check(
        label="Signature == 0xAA55AA55",
        condition=(found == SPEC_SIGNATURE),
        found=f"0x{found:08X}",
        expected=f"0x{SPEC_SIGNATURE:08X}",
    )


def verify_version(data: bytes) -> int:
    """VER-001b: Read and report the version number at offset 0x04.

    [SPEC_ONLY] Possible values:
      97  = D2R launch
      98  = Reign of the Warlock (per D2CE project)
      105 = D2R Reimagined (user report - the PRIMARY thing to verify!)

    Returns the actual version found for downstream use.
    """
    print_section("VER-001b: Version Number (offset 0x0004)")
    hex_dump(data, 0x04, 4, "Version bytes (raw)")
    version = uint32_le(data, 0x04)
    print(f"  Version (decimal) : {version}")
    print(f"  Version (hex)     : 0x{version:02X}")
    print()

    known_versions = {
        96: "Classic LoD 1.10-1.14d",
        97: "D2R v1.0-v2.5",
        98: "D2R Reign of the Warlock (vanilla)",
        105: "D2R Reimagined mod (user report)",
    }
    if version in known_versions:
        print(f"  KNOWN VERSION: {known_versions[version]}")
    else:
        print(f"  UNKNOWN VERSION: {version} - NOT in spec! Update spec immediately.")

    print()
    print("  *** RECORD THIS IN VERIFICATION_LOG.md VER-001 ***")
    print("  *** This version number determines ALL subsequent parsing! ***")
    return version


def verify_character_name(data: bytes) -> None:
    """VER-002: Read and display the character name field.

    [SPEC_ONLY] Offset 0x14, up to 16 bytes, null-terminated.
    For v98+: UTF-8 encoded. For v97: 7-bit ASCII.
    """
    print_section("VER-002: Character Name (offset 0x0014)")
    hex_dump(data, SPEC_NAME_OFFSET, SPEC_NAME_LENGTH, "Name bytes (raw)")

    # Attempt null-terminated read
    raw = data[SPEC_NAME_OFFSET : SPEC_NAME_OFFSET + SPEC_NAME_LENGTH]
    null_pos = raw.find(0x00)
    name_bytes = raw[:null_pos] if null_pos != -1 else raw

    # Try UTF-8 first, fall back to ASCII
    try:
        name_utf8 = name_bytes.decode("utf-8")
        print(f"  Decoded (UTF-8)   : '{name_utf8}'")
    except UnicodeDecodeError:
        print("  UTF-8 decode FAILED")

    try:
        name_ascii = name_bytes.decode("ascii")
        print(f"  Decoded (ASCII)   : '{name_ascii}'")
    except UnicodeDecodeError:
        print("  ASCII decode FAILED (non-ASCII bytes present)")

    print(f"  Name length       : {len(name_bytes)} chars (excl. null terminator)")
    print(f"  Null terminator   : at position {null_pos} in 16-byte field")


def verify_class_and_level(data: bytes) -> None:
    """VER-004: Read character class ID and level.

    [SPEC_ONLY] Class at offset 0x28. Level at offset 0x2B.
    Class 7 = Warlock (user report, VERIFY).
    """
    print_section("VER-004: Character Class & Level")

    # Show surrounding bytes for context (0x24 = status byte)
    hex_dump(data, 0x24, 16, "Status..Class..Level region")

    class_id = data[SPEC_CLASS_OFFSET]
    level = data[SPEC_LEVEL_OFFSET]
    class_name = CLASS_NAMES.get(class_id, f"UNKNOWN (id={class_id})")

    print(f"  Class ID  (0x{SPEC_CLASS_OFFSET:02X}): {class_id} = {class_name}")
    print(f"  Level     (0x{SPEC_LEVEL_OFFSET:02X}): {level}")

    if class_id == 7:
        print()
        print("  *** Warlock class ID=7 confirmed! Update VER-004 in log. ***")
    elif class_id > 7:
        print()
        print(f"  *** UNKNOWN CLASS ID {class_id} - spec may be wrong! ***")


def verify_stats_header_location(data: bytes) -> None:
    """VER-003: Search for the 'gf' stats section header to determine header size.

    [SPEC_ONLY] The stats section should start with bytes 0x67 0x66 ('gf').
    Spec assumes this is at offset 765 for v97.
    For v98+ (or v105?) the header may be larger due to extended appearance data.

    This function searches all occurrences and reports them - the human must
    decide which is correct.
    """
    print_section("VER-003: Stats Header 'gf' Location (CRITICAL)")
    print(f"  Searching for bytes 0x67 0x66 ('gf') in first {SPEC_SEARCH_LIMIT} bytes...")
    print()

    occurrences: list[int] = []
    search_region = data[:SPEC_SEARCH_LIMIT]

    for i in range(len(search_region) - 1):
        if search_region[i] == 0x67 and search_region[i + 1] == 0x66:
            occurrences.append(i)

    if not occurrences:
        print(f"  [NO] FAIL: 'gf' NOT FOUND in first {SPEC_SEARCH_LIMIT} bytes!")
        print(f"         Either header > {SPEC_SEARCH_LIMIT} bytes, or spec is wrong.")
    else:
        print(f"  Found {len(occurrences)} occurrence(s) of 'gf':")
        for offset in occurrences:
            notes = []
            if offset == SPEC_HEADER_SIZE_V97:
                notes.append("[MATCHES spec v97 = 765]")
            elif offset == SPEC_HEADER_SIZE_V98:
                notes.append("[MATCHES spec v98 = 813 with +48 byte extension]")
            else:
                notes.append("[DOES NOT MATCH any known spec value]")

            hex_dump(data, offset, 8, f"At offset {offset}")
            print(f"           ^ offset {offset} (0x{offset:03X}) {' '.join(notes)}")
            print()

    print(f"  Spec expected offsets: v97={SPEC_HEADER_SIZE_V97}, v98={SPEC_HEADER_SIZE_V98}")
    print("  *** RECORD THE CORRECT OFFSET IN VERIFICATION_LOG.md VER-003 ***")
    print("  *** This is a GATE: all item/stat parsing depends on this! ***")


def dump_first_bytes_context(data: bytes) -> None:
    """Dump the first 96 bytes as a general orientation hex dump.

    This gives a quick overview of the header structure for manual inspection.
    """
    print_section("RAW HEX DUMP: First 96 bytes (orientation)")
    for row_start in range(0, 96, 16):
        chunk = data[row_start : row_start + 16]
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print(f"  0x{row_start:04X}:  {hex_part:<48s}  |{ascii_part}|")


# ============================================================
# MAIN
# ============================================================


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python verify_header.py <path_to_d2s_file>")
        print(
            "Example: python verify_header.py "
            '"C:/Users/You/Saved Games/Diablo II Resurrected/mods/ReimaginedThree/char.d2s"'
        )
        return 1

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"ERROR: File not found: {path}")
        return 1
    if path.suffix.lower() != ".d2s":
        print(f"WARNING: File does not have .d2s extension: {path.suffix}")
        print("         Proceeding anyway...")

    with open(path, "rb") as f:
        data = f.read()

    if len(data) < 64:
        print(f"ERROR: File too small ({len(data)} bytes) to be a valid D2S file.")
        return 1

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  D2RR Toolkit - D2S Header Verification Script          ║")
    print("║  VER-001 / VER-002 / VER-003 / VER-004                  ║")
    print("║  Status: [SPEC_ONLY] -> generating [BINARY_VERIFIED] data ║")
    print("╚══════════════════════════════════════════════════════════╝")

    print_section("FILE FINGERPRINT")
    verify_file_fingerprint(path, data)

    dump_first_bytes_context(data)

    sig_ok = verify_signature(data)
    if not sig_ok:
        print()
        print("[NO] CRITICAL: Signature check FAILED.")
        print("  This file may not be a valid D2S save file.")
        print("  Proceeding with remaining checks for diagnostic purposes...")

    version = verify_version(data)
    verify_character_name(data)
    verify_class_and_level(data)
    verify_stats_header_location(data)

    print_section("SUMMARY")
    print("  Steps to complete after running this script:")
    print()
    print("  1. Copy the SHA256 hash into VERIFICATION_LOG.md (File Registry)")
    print("  2. Record the version number in VER-001")
    print("  3. Record the 'gf' offset in VER-003 (CRITICAL!)")
    print("  4. If version == 105: update SPEC_VERSION_REIMAGINED in constants.py")
    print("  5. If 'gf' is NOT at offset 765: update all header size constants")
    print("  6. Mark verified fields as [BINARY_VERIFIED] in VERIFICATION_LOG.md")
    print()
    print("  Do NOT write any parser code until VER-003 is resolved.")

    return 0


if __name__ == "__main__":
    sys.exit(main())


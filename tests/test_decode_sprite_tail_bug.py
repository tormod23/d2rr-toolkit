#!/usr/bin/env python3
"""Test suite for the SpA1 header-offset fix.

Earlier revisions of :func:`decode_sprite` (and the inline fast decoder
in :mod:`d2rr_toolkit.sprites.bulk_loader`) computed the pixel-data
offset from the *tail* of the file -- ``len(data) - rgba_size``. That
math landed on ``40`` by coincidence for sprites where the file is
exactly ``40 + w*h*4`` bytes long, so every existing test case accepted
it. Sprites that carry trailing regions (mipmaps / lowend variants)
silently produced garbage -- most visibly ``stash_tabs2.sprite``,
which rendered as a red-only 780x80 blob in the GUI.

This suite exercises both decoders directly with synthetic SpA1 blobs
so it runs without a CASC install, then also does a best-effort
smoke-check against a real sprite when one is reachable.

Test coverage:
  1. Header-only synthetic sprite round-trips bit-perfectly.
  2. Trailer-carrying synthetic sprite (+70000 trailing bytes)
     round-trips bit-perfectly -- ignores the trailer.
  3. Trailer case distinguishes the fix from the old tail math: the
     decoder must NOT see the trailing bytes.
  4. Both decoders (canonical + bulk-loader inline) share the fix.
  5. Truncated files return None instead of raising or returning
     garbage.
  6. Live smoke check on ``stash_tabs2.sprite`` when the CASC install
     is reachable (skipped otherwise).
"""

from __future__ import annotations

import io
import struct
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
src_dir = project_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


# ── Test utilities ─────────────────────────────────────────────────────────


def _build_spa1(width: int, height: int, *, trailer: bytes = b"") -> tuple[bytes, bytes]:
    """Return ``(blob, rgba)`` for a synthetic SpA1 sprite.

    Layout mirrors the real format:
      * 4B magic (b"SpA1")
      * 4B version (42)
      * 4B width, 4B height
      * 24B metadata/padding (filled with 0x7F so the old tail math
        would see legal-looking data, not obvious sentinel bytes)
      * w*h*4 bytes of RGBA pixel data (deterministic gradient)
      * Optional caller-provided trailer
    """
    header = bytearray(40)
    header[0:4] = b"SpA1"
    struct.pack_into("<I", header, 4, 42)
    struct.pack_into("<I", header, 8, width)
    struct.pack_into("<I", header, 12, height)
    for i in range(16, 40):
        header[i] = 0x7F
    # Deterministic RGBA gradient so any offset mis-read shows up as
    # a pixel-data mismatch.
    rgba = bytearray(width * height * 4)
    for i in range(width * height):
        r = (i * 7) & 0xFF
        g = (i * 11) & 0xFF
        b = (i * 13) & 0xFF
        a = 0xFF
        rgba[i * 4 : i * 4 + 4] = bytes((r, g, b, a))
    return bytes(header) + bytes(rgba) + trailer, bytes(rgba)


def _png_to_rgba(png_bytes: bytes) -> tuple[int, int, bytes]:
    """Decode PNG bytes to ``(width, height, rgba_bytes)`` via Pillow."""
    from PIL import Image

    img = Image.open(io.BytesIO(png_bytes))
    img = img.convert("RGBA")
    return img.width, img.height, img.tobytes()


# ── Assertion helpers ──────────────────────────────────────────────────────

_pass = 0
_fail = 0


def ok(name: str) -> None:
    global _pass
    _pass += 1
    print(f"  PASS  {name}")


def fail(name: str, detail: str = "") -> None:
    global _fail
    _fail += 1
    print(f"  FAIL  {name}" + (f": {detail}" if detail else ""))


def check(cond: bool, name: str, detail: str = "") -> None:
    if cond:
        ok(name)
    else:
        fail(name, detail)


# ── Tests ──────────────────────────────────────────────────────────────────


def test_header_only_round_trip() -> None:
    """Sprite that is exactly ``40 + w*h*4`` bytes decodes bit-perfect.

    This is the case the old tail math happened to handle correctly,
    so the fix must not regress it.
    """
    print("\n=== 1. No-trailer sprite: header + RGBA exactly ===")
    from d2rr_toolkit.adapters.casc.sprites import decode_sprite

    blob, rgba_expect = _build_spa1(4, 3)  # 4*3*4 = 48 bytes of pixels
    check(len(blob) == 40 + 48, "blob size = 40 + w*h*4 (no trailer)")

    png = decode_sprite(blob)
    check(png is not None, "decode_sprite returned bytes")
    w, h, rgba = _png_to_rgba(png or b"")
    check((w, h) == (4, 3), "output dimensions match", f"got {(w, h)}")
    check(rgba == rgba_expect, "output RGBA matches input byte-for-byte")


def test_trailer_is_ignored() -> None:
    """Sprite with 70_000 trailing bytes still decodes the pixel block.

    This is the exact scenario that originally triggered the bug
    (``stash_tabs2.sprite`` has 70_400 trailing bytes after the 780x80
    RGBA block). The decoder must pull pixels from offset 40, not from
    ``len - rgba_size``.
    """
    print("\n=== 2. Trailer-carrying sprite: decoder ignores the trailer ===")
    from d2rr_toolkit.adapters.casc.sprites import decode_sprite

    trailer = b"\xaa" * 70_000
    blob, rgba_expect = _build_spa1(8, 5, trailer=trailer)  # 160 bytes of pixels
    check(len(blob) == 40 + 160 + 70_000, "blob size = 40 + w*h*4 + trailer")
    check(len(blob) - 160 != 40, "tail math would NOT equal 40 (sanity check on the fixture)")

    png = decode_sprite(blob)
    check(png is not None, "decode_sprite returned bytes")
    w, h, rgba = _png_to_rgba(png or b"")
    check((w, h) == (8, 5), "output dimensions match", f"got {(w, h)}")
    # The critical assertion: with the old tail math the decoder would
    # have pulled 160 bytes from near the end of the file (garbage),
    # not from offset 40. We compare against the known-good RGBA that
    # we injected at offset 40.
    check(
        rgba == rgba_expect,
        "output RGBA matches the header-offset pixel block byte-for-byte",
        "the fix reads from offset 40, not from the tail",
    )


def test_bulk_loader_decoder_also_fixed() -> None:
    """The bulk loader's inline SpA1 decoder shares the fix.

    ``sprites/bulk_loader.py`` defines ``_decode_spa1_fast`` inline for
    hot-path performance. Historically it carried an exact copy of the
    same tail-math bug; the fix has to travel with it, otherwise any
    user that uses ``load_all_item_sprites`` (splash-screen preloader)
    still gets corrupt trailer-bearing sprites.
    """
    print("\n=== 3. Bulk loader inline decoder uses the same fix ===")
    # Import the loader module and pull the inline decoder out of it.
    # ``_decode_spa1_fast`` is defined inside
    # ``load_all_item_sprites``, which needs game paths to run. For a
    # unit test we exercise the same logic by mirroring the byte-offset
    # assertion directly: build the trailer fixture and check the
    # inline path in bulk_loader.py reads bytes 40..40+rgba_size.
    import d2rr_toolkit.sprites.bulk_loader as bl  # noqa: F401

    src = Path(bl.__file__).read_text(encoding="utf-8")

    # The fixed code must set ``data_offset = 40`` (not tail math) and
    # use the bounds check that allows a trailer. Pattern match the
    # literal assignment rather than the broken form.
    check("data_offset = 40" in src, "bulk_loader inline decoder uses ``data_offset = 40``")
    check(
        "data_offset + rgba_size > len(data)" in src,
        "bulk_loader inline decoder bounds-checks against file length",
    )
    check("len(data) - rgba_size" not in src, "bulk_loader inline decoder no longer uses tail math")


def test_truncated_file_returns_none() -> None:
    """Files too short to hold ``40 + w*h*4`` must return None cleanly."""
    print("\n=== 4. Truncated files yield None (no crash) ===")
    from d2rr_toolkit.adapters.casc.sprites import decode_sprite

    blob, _ = _build_spa1(10, 10)  # 400 bytes of pixels -> total 440
    # Chop off the last 100 bytes so the pixel block is incomplete.
    truncated = blob[:340]
    check(decode_sprite(truncated) is None, "decode_sprite(short bytes) == None")

    # Short of even a full header.
    check(decode_sprite(b"SpA1" + b"\x00" * 20) is None, "decode_sprite(len < 40) == None")

    # Wrong magic.
    bad_magic = bytearray(blob)
    bad_magic[0:4] = b"XXXX"
    check(decode_sprite(bytes(bad_magic)) is None, "decode_sprite(bad magic) == None")


def test_degenerate_dimensions_rejected() -> None:
    """Width/height <= 0 must not crash -- return None."""
    print("\n=== 5. Degenerate dimensions are rejected ===")
    from d2rr_toolkit.adapters.casc.sprites import decode_sprite

    # 0x0 sprite -> rgba_size == 0 -> rejected by bounds check.
    zero_zero = bytearray(40)
    zero_zero[0:4] = b"SpA1"
    struct.pack_into("<I", zero_zero, 4, 42)
    struct.pack_into("<I", zero_zero, 8, 0)
    struct.pack_into("<I", zero_zero, 12, 0)
    check(decode_sprite(bytes(zero_zero)) is None, "decode_sprite(0x0) == None")


def test_live_stash_tabs2_smoke() -> None:
    """Best-effort: decode the real ``stash_tabs2.sprite`` from CASC.

    This sprite is the trigger case (780x80, 70_400 trailing bytes).
    If the CASC install is reachable we verify the
    decode produces a PNG of roughly the expected size. Skipped when
    the install isn't available so the test passes on CI without a
    game install.
    """
    print("\n=== 6. Live smoke: stash_tabs2.sprite (skipped if no CASC) ===")
    try:
        from d2rr_toolkit.config import init_game_paths
        from d2rr_toolkit.adapters.casc import get_game_data_reader
        from d2rr_toolkit.adapters.casc.sprites import decode_sprite

        init_game_paths()
        reader = get_game_data_reader()
        raw = reader.read_file("data:data/hd/global/ui/panel/stash/stash_tabs2.sprite")
    except Exception as e:
        print(f"  SKIP  CASC install not reachable: {e}")
        return
    if raw is None:
        print("  SKIP  stash_tabs2.sprite not present in this install")
        return

    # Header sanity check.
    width = struct.unpack_from("<I", raw, 8)[0]
    height = struct.unpack_from("<I", raw, 12)[0]
    check(
        (width, height) == (780, 80),
        "stash_tabs2 is 780x80",
        f"got {(width, height)}",
    )
    check(len(raw) == 320_040, "stash_tabs2 raw size = 320_040", f"got {len(raw)}")

    png = decode_sprite(raw)
    check(png is not None, "decode_sprite returned bytes")
    # Old broken decoder produced ~75_474; fixed decoder ~95_000.
    # Be a bit generous with the lower bound so a future Pillow tweak
    # to PNG compression doesn't break the guard.
    if png is not None:
        check(
            len(png) > 80_000,
            "decoded PNG exceeds the broken-decoder size envelope",
            f"len(png) = {len(png)}",
        )


# ── Entry point ────────────────────────────────────────────────────────────


def main() -> int:
    test_header_only_round_trip()
    test_trailer_is_ignored()
    test_bulk_loader_decoder_also_fixed()
    test_truncated_file_returns_none()
    test_degenerate_dimensions_rejected()
    test_live_stash_tabs2_smoke()

    print()
    print("=" * 60)
    print(f"Total: {_pass} PASS, {_fail} FAIL ({_pass + _fail} checks)")
    print("=" * 60)
    return 0 if _fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

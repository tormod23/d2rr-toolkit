"""TC80 - Unit tests for bulk_loader private helpers.

The 461-LOC ``load_all_item_sprites`` was decomposed into
module-private step functions. This suite pins the extracted helpers
independently so future refactors cannot silently change their
contract.

Helpers covered:
  - ``_decode_spa1_fast``            - SpA1 -> PNG decoder
  - ``_build_mod_hd_index``          - mod sprite filename -> Path map
  - ``_SpriteResolver``              - mod-overlay + CASC + PNG cache
"""

from __future__ import annotations

import struct
import sys

import pytest


@pytest.fixture
def spa1_blob():
    """Return a minimal-but-valid 2*2 SpA1 blob (40-byte header + 16 B RGBA)."""
    header = b"SpA1" + b"\x00" * 4 + struct.pack("<II", 2, 2) + b"\x00" * 24
    pixels = b"\xff\x00\x00\xff" * 4  # 4 opaque red pixels
    return header + pixels


# ─────────────────────────────────────────────────────────────────────
# §1  _decode_spa1_fast
# ─────────────────────────────────────────────────────────────────────


def test_decode_spa1_fast_valid_input(spa1_blob):
    from d2rr_toolkit.sprites.bulk_loader import _decode_spa1_fast

    png = _decode_spa1_fast(spa1_blob)
    assert png is not None
    assert png[:8] == b"\x89PNG\r\n\x1a\n", "must be a PNG signature"


def test_decode_spa1_fast_rejects_non_spa1():
    from d2rr_toolkit.sprites.bulk_loader import _decode_spa1_fast

    assert _decode_spa1_fast(b"") is None
    assert _decode_spa1_fast(b"JUNK") is None
    assert _decode_spa1_fast(b"\x00" * 40) is None  # right size, wrong magic


def test_decode_spa1_fast_rejects_truncated_payload():
    """A header that claims 2*2 RGBA but carries no pixel bytes -> None."""
    from d2rr_toolkit.sprites.bulk_loader import _decode_spa1_fast

    header_only = b"SpA1" + b"\x00" * 4 + struct.pack("<II", 2, 2) + b"\x00" * 24
    assert _decode_spa1_fast(header_only) is None


# ─────────────────────────────────────────────────────────────────────
# §2  _build_mod_hd_index
# ─────────────────────────────────────────────────────────────────────


def test_build_mod_hd_index_maps_stems_to_paths(tmp_path):
    from d2rr_toolkit.sprites.bulk_loader import _build_mod_hd_index

    d = tmp_path / "hd" / "items"
    (d / "weapons").mkdir(parents=True)
    (d / "armor").mkdir()
    (d / "weapons" / "axe.sprite").write_bytes(b"SpA1")
    (d / "armor" / "helm.sprite").write_bytes(b"SpA1")
    (d / "armor" / "helm.lowend.sprite").write_bytes(b"SpA1")  # must be skipped

    index = _build_mod_hd_index(d)
    assert "axe" in index
    assert "helm" in index
    assert "helm.lowend" not in index
    assert index["axe"].name == "axe.sprite"


def test_build_mod_hd_index_missing_dir_returns_empty(tmp_path):
    from d2rr_toolkit.sprites.bulk_loader import _build_mod_hd_index

    missing = tmp_path / "does" / "not" / "exist"
    assert _build_mod_hd_index(missing) == {}


# ─────────────────────────────────────────────────────────────────────
# §3  _SpriteResolver
# ─────────────────────────────────────────────────────────────────────


class _FakeCasc:
    def __init__(self, blobs: dict[bytes, bytes]) -> None:
        self._blobs = blobs

    def read_by_ckey(self, ckey: bytes) -> bytes | None:
        return self._blobs.get(ckey)


def test_sprite_resolver_mod_beats_casc(tmp_path, spa1_blob):
    """If a sprite exists in the mod index AND CASC, the mod file wins."""
    from d2rr_toolkit.sprites.bulk_loader import _SpriteResolver

    mod_path = tmp_path / "modaxe.sprite"
    mod_path.write_bytes(spa1_blob)

    # CASC blob would also decode, but should never be consulted.
    casc = _FakeCasc({b"CKEY": b"JUNK"})
    resolver = _SpriteResolver(
        mod_index={"axe": mod_path},
        casc_index={"axe": b"CKEY"},
        casc_reader=casc,  # type: ignore[arg-type]
        skip_errors=True,
    )
    png = resolver.load("axe")
    assert png is not None
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_sprite_resolver_falls_back_to_casc(spa1_blob):
    from d2rr_toolkit.sprites.bulk_loader import _SpriteResolver

    casc = _FakeCasc({b"CKEY": spa1_blob})
    resolver = _SpriteResolver(
        mod_index={},  # no mod override
        casc_index={"axe": b"CKEY"},
        casc_reader=casc,  # type: ignore[arg-type]
        skip_errors=True,
    )
    png = resolver.load("axe")
    assert png is not None


def test_sprite_resolver_caches_decoded_png(tmp_path, spa1_blob):
    """A second call for the same basename must hit the cache, not re-decode."""
    from d2rr_toolkit.sprites.bulk_loader import _SpriteResolver

    p = tmp_path / "axe.sprite"
    p.write_bytes(spa1_blob)
    resolver = _SpriteResolver(
        mod_index={"axe": p},
        casc_index={},
        casc_reader=None,  # type: ignore[arg-type]
        skip_errors=True,
    )
    png1 = resolver.load("axe")
    p.write_bytes(b"JUNK")  # any subsequent read would fail - cache must hide it
    png2 = resolver.load("axe")
    assert png1 is png2, "resolver must return the cached instance"


def test_sprite_resolver_missing_everywhere_returns_none():
    from d2rr_toolkit.sprites.bulk_loader import _SpriteResolver

    resolver = _SpriteResolver(
        mod_index={},
        casc_index={},
        casc_reader=None,  # type: ignore[arg-type]
        skip_errors=True,
    )
    assert resolver.load("nonexistent") is None


def test_sprite_resolver_all_names_is_union(tmp_path):
    from d2rr_toolkit.sprites.bulk_loader import _SpriteResolver

    resolver = _SpriteResolver(
        mod_index={"a": tmp_path, "b": tmp_path},
        casc_index={"b": b"K", "c": b"K"},
        casc_reader=None,  # type: ignore[arg-type]
        skip_errors=True,
    )
    assert resolver.all_names == {"a", "b", "c"}


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    pytest.main([__file__, "-v"])


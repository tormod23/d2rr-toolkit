"""Regression tests for path-traversal hardening in
``CASCReader._resolve_mod_path``.

These tests pin CWE-22 containment: every rejection path must return
``None`` silently, and every legitimate mod-overlay lookup must still
resolve to a path strictly inside ``mod_dir``.

The tests bypass ``CASCReader.__init__`` via ``object.__new__`` because a
full init loads a real CASC archive from disk. Only ``_mod_dir`` is
needed for the method under test, and no other state is touched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from d2rr_toolkit.adapters.casc.reader import CASCReader


def _make_reader(mod_dir: Path | None) -> CASCReader:
    """Instantiate a CASCReader without running the heavy ``__init__``."""
    reader = object.__new__(CASCReader)
    reader._mod_dir = mod_dir  # type: ignore[attr-defined]
    return reader


@pytest.fixture
def mod_dir(tmp_path: Path) -> Path:
    """Create a populated mod-overlay directory."""
    root = tmp_path / "mod"
    excel = root / "data" / "global" / "excel"
    excel.mkdir(parents=True)
    (excel / "weapons.txt").write_text("weapons\n", encoding="utf-8")
    # Also create a file outside mod_dir to prove escape is blocked.
    (tmp_path / "secret.txt").write_text("pwned\n", encoding="utf-8")
    return root


def test_no_mod_dir_returns_none(tmp_path: Path) -> None:
    reader = _make_reader(None)
    assert reader._resolve_mod_path("data:data/global/excel/weapons.txt") is None


def test_happy_path(mod_dir: Path) -> None:
    reader = _make_reader(mod_dir)
    result = reader._resolve_mod_path("data:data/global/excel/weapons.txt")
    assert result is not None
    assert result.is_file()
    assert result.name == "weapons.txt"
    # Must be strictly inside mod_dir after resolution.
    result.relative_to(mod_dir.resolve())


def test_no_prefix_legit(mod_dir: Path) -> None:
    reader = _make_reader(mod_dir)
    result = reader._resolve_mod_path("data/global/excel/weapons.txt")
    assert result is not None
    assert result.name == "weapons.txt"


@pytest.mark.parametrize(
    "evil_path",
    [
        "data:../../../etc/passwd",
        "data:..\\..\\..\\Windows\\System32\\config\\SAM",
        "data:/etc/passwd",
        "data:C:\\Windows\\System32\\notepad.exe",
        "data:a/../../b",  # normalises outside mod_dir
        "..",
        ":/etc/passwd",  # empty prefix + absolute
        "data:../secret.txt",
        # Explicit traversal via mid-path dotdot chains.
        "data:data/../../../outside",
        "data:data/global/../../../outside",
    ],
)
def test_traversal_rejected(mod_dir: Path, evil_path: str) -> None:
    reader = _make_reader(mod_dir)
    assert reader._resolve_mod_path(evil_path) is None


def test_rejection_does_not_leak_via_read_file(mod_dir: Path) -> None:
    """A rejected overlay path must behave like a cache miss: the CASC
    archive fallback runs, not the escaped file.

    Here we stub the CASC path map to empty, so ``read_file`` on a
    rejected path must return ``None`` and never read ``secret.txt``.
    """
    reader = _make_reader(mod_dir)
    reader._path_map = {}  # type: ignore[attr-defined]
    assert reader.read_file("data:../secret.txt") is None
    assert reader.has_file("data:../secret.txt") is False


def test_subtle_dotdot_inside_then_out(mod_dir: Path) -> None:
    """``foo/../../bar`` resolves to ``../bar`` -- must be rejected
    even though each individual segment looks benign."""
    reader = _make_reader(mod_dir)
    assert reader._resolve_mod_path("data:data/../../bar") is None


def test_resolve_mod_path_preserves_path_segments(tmp_path: Path) -> None:
    """Forward slashes must produce a proper multi-segment path
    on every platform -- not one filename containing literal backslashes
    (the POSIX bug from the pre-fix ``rel.replace("/", "\\\\")`` code).
    """
    reader = _make_reader(tmp_path)
    resolved = reader._resolve_mod_path("data:data/global/excel/weapons.txt")
    assert resolved is not None
    expected_suffix = Path("data") / "global" / "excel" / "weapons.txt"
    assert resolved.parts[-len(expected_suffix.parts) :] == expected_suffix.parts


def test_legit_dotdot_stays_inside(mod_dir: Path) -> None:
    """``foo/../weapons.txt`` normalises inside mod_dir -- must succeed."""
    reader = _make_reader(mod_dir)
    result = reader._resolve_mod_path("data:data/global/excel/../excel/weapons.txt")
    assert result is not None
    assert result.name == "weapons.txt"

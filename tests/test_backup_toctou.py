"""TC79 - backup._backup_dir refuses symlinked or foreign-owned dirs (CWE-367).

POSIX-only test: planting a symlink at `BACKUP_ROOT / "victim.d2s"`
between mkdir and copy would redirect the backup write to an
attacker-controlled location. _backup_dir now lstats the path and
raises RuntimeError unless it is a real directory owned by the
current user. On Windows the UID check is skipped; the
directory-vs-symlink check still fires (but the symlink attack itself
isn't practical there).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_backup_dir_rejects_symlink(tmp_path, monkeypatch):
    fake_root = tmp_path / "backups"
    fake_root.mkdir()
    monkeypatch.setattr("d2rr_toolkit.backup.BACKUP_ROOT", fake_root)

    # Plant a symlink where _backup_dir would create a directory
    target = tmp_path / "attacker-controlled"
    target.mkdir()
    (fake_root / "victim.d2s").symlink_to(target)

    from d2rr_toolkit.backup import _backup_dir

    with pytest.raises(RuntimeError, match="not a real directory|owned by another uid"):
        _backup_dir(Path("victim.d2s"))


def test_backup_dir_accepts_real_directory(tmp_path, monkeypatch):
    """The happy path still works."""
    fake_root = tmp_path / "backups"
    monkeypatch.setattr("d2rr_toolkit.backup.BACKUP_ROOT", fake_root)
    from d2rr_toolkit.backup import _backup_dir

    d = _backup_dir(Path("test.d2s"))
    assert d.is_dir()
    assert d.name == "test.d2s"


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    pytest.main([__file__, "-v"])

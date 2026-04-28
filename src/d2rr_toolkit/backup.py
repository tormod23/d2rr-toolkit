"""Backup system - creates timestamped backups before every write operation.

Every D2S/D2I modification MUST go through this module to keep user data safe.
Backups are stored in a **central** directory at ``~/.d2rr_toolkit/backups/``
so that the save-game directory is not cluttered with auxiliary files.

Each call to :func:`create_backup` produces a new uniquely-timestamped copy
(microsecond resolution) - no previous backup is ever overwritten. This keeps
a full audit trail of every write until we are confident the writer is 100%
correct, at which point old backups can be pruned manually or via
:func:`cleanup_old_backups`.

Usage::

    from d2rr_toolkit.backup import create_backup, list_backups, rollback

    backup_path = create_backup(save_path)  # ALWAYS call before writing
    # ... perform write operation ...
    # If something goes wrong:
    rollback(save_path, backup_path)
"""

import logging
import os
import stat
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Central backup location - outside the save-game directory so it doesn't
# clutter the user's mod folder. Created on first use.
BACKUP_ROOT = Path.home() / ".d2rr_toolkit" / "backups"


def _backup_dir(save_path: Path) -> Path:
    """Return the backup sub-directory for a specific save file.

    Structure: ``~/.d2rr_toolkit/backups/<filename>/``
    where ``<filename>`` is the full name (stem + extension) of the save file.
    This keeps backups for different saves separated without collisions.
    """
    # Use the full filename (e.g. "CubeContents.d2s") as the subdirectory
    # name so backups of different files don't intermingle.
    backup_dir = BACKUP_ROOT / save_path.name
    backup_dir.mkdir(parents=True, exist_ok=True)

    # TOCTOU hardening (CWE-367): between mkdir returning and the
    # subsequent Path.copy call, an attacker with write access to
    # BACKUP_ROOT could replace backup_dir with a symlink to an
    # attacker-controlled location. Lstat the path (no symlink follow)
    # and refuse to proceed unless it's a real directory owned by us.
    # On Windows the UID check is skipped - the stdlib doesn't expose
    # the owning SID conveniently and the ACL model differs; the
    # directory-vs-symlink check still fires.
    st = backup_dir.lstat()
    if not stat.S_ISDIR(st.st_mode):
        raise RuntimeError(
            f"Backup path exists but is not a real directory (possibly a symlink): {backup_dir}"
        )
    # os.getuid() is POSIX-only; mypy on a stub-platform doesn't see it.
    # The os.name guard makes sure this branch never runs on Windows.
    if os.name != "nt" and st.st_uid != os.getuid():  # type: ignore[attr-defined]
        raise RuntimeError(
            f"Backup path owned by another uid ({st.st_uid}); refusing "
            f"to write backups into {backup_dir}."
        )
    return backup_dir


def create_backup(save_path: Path) -> Path:
    """Create a timestamped backup of a save file.

    MUST be called before every write operation. Each call creates a
    **new** file - no previous backup is overwritten.

    The backup is stored at::

        ~/.d2rr_toolkit/backups/<filename>/<stem>.<timestamp><suffix>.bak

    Args:
        save_path: Path to the save file to back up.

    Returns:
        Path to the backup file.

    Raises:
        FileNotFoundError: If save_path does not exist.
    """
    if not save_path.exists():
        raise FileNotFoundError(f"Cannot backup: {save_path} does not exist")

    backup_dir = _backup_dir(save_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_name = f"{save_path.stem}.{timestamp}{save_path.suffix}.bak"
    backup_path = backup_dir / backup_name

    save_path.copy(backup_path, preserve_metadata=True)
    logger.info("Backup created: %s", backup_path)
    return backup_path


def list_backups(save_path: Path) -> list[Path]:
    """List all backups for a save file, newest first.

    Args:
        save_path: Path to the save file.

    Returns:
        List of backup paths, sorted newest first (by filename timestamp).
    """
    backup_dir = BACKUP_ROOT / save_path.name
    if not backup_dir.exists():
        return []

    stem = save_path.stem
    ext = save_path.suffix
    pattern = f"{stem}.*{ext}.bak"
    backups = sorted(backup_dir.glob(pattern), reverse=True)
    return backups


def rollback(save_path: Path, backup_path: Path) -> None:
    """Restore a save file from a backup.

    Args:
        save_path:   Path to the save file to restore.
        backup_path: Path to the backup to restore from.

    Raises:
        FileNotFoundError: If backup_path does not exist.
    """
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup not found: {backup_path}")

    backup_path.copy(save_path, preserve_metadata=True)
    logger.info("Rollback complete: %s restored from %s", save_path, backup_path)


def cleanup_old_backups(save_path: Path, *, keep: int = 20) -> int:
    """Remove oldest backups for a save file, keeping the N newest.

    Intended for future use once we have high confidence in the writer.
    Until then, all backups should be kept as an audit trail.

    Args:
        save_path: Path to the save file.
        keep:      Number of newest backups to keep.

    Returns:
        Number of backups removed.
    """
    all_backups = list_backups(save_path)
    to_remove = all_backups[keep:]
    for p in to_remove:
        p.unlink()
        logger.info("Removed old backup: %s", p)
    return len(to_remove)

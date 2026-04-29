"""TC76b - bulk_extract_from_d2s atomicity + per-selection outcomes.

Parallel to ``test_bulk_extract_from_d2i.py`` for the D2S character
file variant. Pins the same atomicity contract (one backup, one
write, one verify, compensating rollback on failure) and the same
per-selection outcome semantics, adapted to the D2S model where
items live in a single flat ``character.items`` list (no tabs).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from d2rr_toolkit.archive import (  # noqa: E402
    ArchiveError,
    BulkArchiveSelectionD2S,
    BulkArchiveStatus,
    bulk_extract_from_d2s,
)
from d2rr_toolkit.database.item_db import ItemDatabase  # noqa: E402
from d2rr_toolkit.parsers.d2s_parser import D2SParser  # noqa: E402

D2S_FIXTURE = PROJECT_ROOT / "tests" / "cases" / "TC01" / "TestABC.d2s"


@pytest.fixture(scope="module", autouse=True)
def _bootstrap_game_data():
    """Trigger the parser's lazy game-data load."""
    from d2rr_toolkit.game_data.item_types import get_item_type_db

    if get_item_type_db().is_loaded():
        return
    try:
        D2SParser(D2S_FIXTURE).parse()
    except Exception:
        pytest.skip("Reimagined Excel base not resolvable (no D2RR install).")


@pytest.fixture
def workspace(tmp_path: Path) -> tuple[Path, ItemDatabase, list[int]]:
    """Yield (writable D2S copy, fresh DB, archivable indices).

    ``archivable indices`` lists item indices in ``character.items``
    that are eligible for the bulk path (identified, has source_data,
    not a phantom). Tests pick subsets of these for known-good
    selections.
    """
    work = tmp_path / "char.d2s"
    shutil.copy(D2S_FIXTURE, work)
    db = ItemDatabase(tmp_path / "archive.db", mode="softcore")

    char = D2SParser(work).parse()
    archivable = [
        i for i, it in enumerate(char.items) if it.flags.identified and it.source_data is not None
    ]
    yield work, db, archivable
    db.close()


# ─────────────────────────────────────────────────────────────────────
# Empty + happy path
# ─────────────────────────────────────────────────────────────────────


def test_empty_selection_is_noop(workspace):
    """Empty selection list returns an empty result and does not
    write a backup or touch the source file."""
    work, db, _ = workspace
    src_before = work.read_bytes()

    result = bulk_extract_from_d2s(work, [], db)

    assert result.outcomes == []
    assert result.backup_path is None
    assert result.archived_count == 0
    assert work.read_bytes() == src_before


def test_single_selection_archives_one_item(workspace):
    """One valid selection archives one item, file gets written
    once, outcome reports ARCHIVED."""
    work, db, archivable = workspace
    if not archivable:
        pytest.skip("D2S fixture has no archivable items.")

    char_before = D2SParser(work).parse()
    total_before = len(char_before.items)

    result = bulk_extract_from_d2s(
        work,
        [BulkArchiveSelectionD2S(item_index=archivable[0], display_name="test")],
        db,
    )

    assert len(result.outcomes) == 1
    o = result.outcomes[0]
    assert o.archived
    assert o.status == BulkArchiveStatus.ARCHIVED
    assert o.parent_db_id is not None

    char_after = D2SParser(work).parse()
    assert len(char_after.items) == total_before - 1


# ─────────────────────────────────────────────────────────────────────
# Filtering paths
# ─────────────────────────────────────────────────────────────────────


def test_invalid_indices_skipped_without_aborting_batch(workspace):
    """Out-of-range selections are skipped with SKIPPED_INVALID_INDEX
    while the rest of the batch proceeds."""
    work, db, archivable = workspace
    if len(archivable) < 2:
        pytest.skip("Need at least 2 archivable items.")

    selections = [
        BulkArchiveSelectionD2S(item_index=archivable[0]),
        BulkArchiveSelectionD2S(item_index=99999),
        BulkArchiveSelectionD2S(item_index=archivable[1]),
    ]
    result = bulk_extract_from_d2s(work, selections, db)

    statuses = [o.status for o in result.outcomes]
    assert statuses == [
        BulkArchiveStatus.ARCHIVED,
        BulkArchiveStatus.SKIPPED_INVALID_INDEX,
        BulkArchiveStatus.ARCHIVED,
    ]
    assert result.archived_count == 2


# ─────────────────────────────────────────────────────────────────────
# Atomicity guarantees
# ─────────────────────────────────────────────────────────────────────


def test_one_backup_per_call_regardless_of_count(workspace, monkeypatch):
    """Spy on ``archive.create_backup`` to confirm exactly ONE
    invocation per bulk call regardless of selection count.

    The D2SWriter creates its OWN backup inside ``write()`` via
    ``writers.d2s_writer.create_backup`` (different module
    reference); our spy only counts the archive-module call,
    matching the invariant pinned for the d2i variant."""
    work, db, archivable = workspace
    if len(archivable) < 3:
        pytest.skip("Need at least 3 archivable items.")

    call_count = {"n": 0}
    from d2rr_toolkit import archive as archive_mod

    real_backup = archive_mod.create_backup

    def _spy(p):
        call_count["n"] += 1
        return real_backup(p)

    monkeypatch.setattr(archive_mod, "create_backup", _spy)

    selections = [BulkArchiveSelectionD2S(item_index=i) for i in archivable[:3]]
    result = bulk_extract_from_d2s(work, selections, db)

    assert result.backup_path is not None
    assert call_count["n"] == 1, (
        f"expected exactly one create_backup call from the bulk endpoint, got {call_count['n']}"
    )


def test_total_items_drops_by_archived_count_only(workspace):
    """Re-parsed file has ``total - archived_count`` items."""
    work, db, archivable = workspace
    if len(archivable) < 2:
        pytest.skip("Need at least 2 archivable items.")

    total_before = len(D2SParser(work).parse().items)

    selections = [BulkArchiveSelectionD2S(item_index=i) for i in archivable[:2]]
    result = bulk_extract_from_d2s(work, selections, db)

    assert result.archived_count == 2
    assert len(D2SParser(work).parse().items) == total_before - 2


def test_write_failure_rolls_back_db_inserts(workspace, monkeypatch):
    """Force a writer failure and verify both the file AND the DB
    are rolled back to the pre-call state."""
    work, db, archivable = workspace
    if not archivable:
        pytest.skip("D2S fixture has no archivable items.")

    src_before = work.read_bytes()
    db_count_before = db.count()

    from d2rr_toolkit.writers import d2s_writer as dw

    def _raise(self, *_a, **_kw):
        raise RuntimeError("synthetic d2s write failure")

    monkeypatch.setattr(dw.D2SWriter, "write", _raise)

    selections = [BulkArchiveSelectionD2S(item_index=i) for i in archivable[:2]]
    with pytest.raises(ArchiveError, match="Failed to write"):
        bulk_extract_from_d2s(work, selections, db)

    assert db.count() == db_count_before, "DB rows leaked past failed bulk d2s write"
    assert work.read_bytes() == src_before, "source file mutated on failed bulk d2s write"


def test_per_item_db_failure_keeps_batch_going(workspace, monkeypatch):
    """A transient DB failure on one selection skips that item
    with ERROR_DB_INSERT; the rest of the batch proceeds."""
    work, db, archivable = workspace
    if len(archivable) < 3:
        pytest.skip("Need at least 3 archivable items.")

    real_store = db.store_item
    call_count = {"n": 0}

    def _flaky_store(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("synthetic d2s DB error")
        return real_store(*args, **kwargs)

    monkeypatch.setattr(db, "store_item", _flaky_store)

    selections = [BulkArchiveSelectionD2S(item_index=i) for i in archivable[:3]]
    result = bulk_extract_from_d2s(work, selections, db)

    statuses = [o.status for o in result.outcomes]
    assert statuses == [
        BulkArchiveStatus.ARCHIVED,
        BulkArchiveStatus.ERROR_DB_INSERT,
        BulkArchiveStatus.ARCHIVED,
    ]
    assert result.archived_count == 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    pytest.main([__file__, "-v"])

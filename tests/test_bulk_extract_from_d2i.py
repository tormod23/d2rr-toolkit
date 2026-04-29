"""Bulk archive endpoint atomicity + per-selection outcomes (D2I).

Pins the contract of :func:`d2rr_toolkit.archive.bulk_extract_from_d2i`:

  * **One backup** per call, regardless of selection count.
  * **One write** at the end (writer's self-check fires before
    the temp-file rename, so a malformed batch never reaches disk).
  * **One verify** by re-parsing the written file.
  * **Per-selection outcome** in the result: ARCHIVED for items
    that made it all the way through;
    SKIPPED_UNIDENTIFIED / SKIPPED_INVALID_INDEX /
    SKIPPED_NO_SOURCE_DATA for refused inputs;
    ERROR_DB_INSERT for transient DB failures.
  * **Compensating rollback** on a write or verify failure: every
    DB row inserted during the call is deleted, the file is
    restored from the backup, the DB and the .d2i end up in the
    pre-call state.
  * **Empty selection list** is a no-op that returns an empty
    result (no backup written).

Uses TC76's clean SetThrowingWeapon fixture (2 items in tab 5: a
Set Balrog Spear + an HP1 separator). The 7s7 also happens to
exercise the Set-throwing-weapon parser path so this test
indirectly verifies that path stays correct in the writer's
verbatim copy.
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
    BulkArchiveSelection,
    BulkArchiveStatus,
    bulk_extract_from_d2i,
)
from d2rr_toolkit.database.item_db import ItemDatabase  # noqa: E402
from d2rr_toolkit.parsers.d2i_parser import D2IParser  # noqa: E402

FIXTURE = PROJECT_ROOT / "tests" / "cases" / "TC76" / "SetThrowingWeapon.d2i"
ITEMS_TAB = 0  # the fixture has the 7s7 + HP1 in tab 0


@pytest.fixture(scope="module", autouse=True)
def _bootstrap_game_data():
    """Trigger the parser's lazy game-data load."""
    from d2rr_toolkit.game_data.item_types import get_item_type_db
    from d2rr_toolkit.parsers.d2s_parser import D2SParser

    probe = next(PROJECT_ROOT.glob("tests/cases/**/*.d2s"), None)
    if probe is None:
        pytest.skip("No .d2s fixture available to bootstrap game data.")
    if get_item_type_db().is_loaded():
        return
    try:
        D2SParser(probe).parse()
    except Exception:
        pytest.skip("Reimagined Excel base not resolvable (no D2RR install).")


@pytest.fixture
def workspace(tmp_path: Path) -> tuple[Path, ItemDatabase]:
    """Yield a fresh writable copy of the TC76 fixture + a fresh DB."""
    work = tmp_path / "stash.d2i"
    shutil.copy(FIXTURE, work)
    db = ItemDatabase(tmp_path / "archive.db", mode="softcore")
    yield work, db
    db.close()


# --------------------------------------------------------------------- #
# Empty selection list - no-op
# --------------------------------------------------------------------- #


def test_empty_selection_is_noop(workspace):
    """An empty selection list returns an empty result and does NOT
    write a backup or touch the source file."""
    work, db = workspace
    src_bytes_before = work.read_bytes()

    result = bulk_extract_from_d2i(work, [], db)

    assert result.outcomes == []
    assert result.backup_path is None
    assert result.archived_count == 0
    assert result.total_count == 0
    assert work.read_bytes() == src_bytes_before


# --------------------------------------------------------------------- #
# Single happy-path selection
# --------------------------------------------------------------------- #


def test_single_selection_archives_one_item(workspace):
    """One valid selection archives the item, writes the file once,
    and reports ARCHIVED in the outcome."""
    work, db = workspace
    sh_before = D2IParser(work).parse()
    total_before = sh_before.total_items

    result = bulk_extract_from_d2i(
        work,
        [BulkArchiveSelection(tab_index=ITEMS_TAB, item_index=0, display_name="test-item")],
        db,
    )

    assert len(result.outcomes) == 1
    o = result.outcomes[0]
    assert o.archived
    assert o.status == BulkArchiveStatus.ARCHIVED
    assert o.parent_db_id is not None
    sh_after = D2IParser(work).parse()
    assert sh_after.total_items == total_before - 1


# --------------------------------------------------------------------- #
# Filtering paths
# --------------------------------------------------------------------- #


def test_bulk_filters_invalid_indices_without_aborting_batch(workspace):
    """A batch with one out-of-range selection AND valid selections
    archives the valid ones and reports the invalid one with
    SKIPPED_INVALID_INDEX. One bad selection does not poison the
    whole batch."""
    work, db = workspace
    selections = [
        BulkArchiveSelection(tab_index=ITEMS_TAB, item_index=0),
        BulkArchiveSelection(tab_index=ITEMS_TAB, item_index=99999),
        BulkArchiveSelection(tab_index=99, item_index=0),
        BulkArchiveSelection(tab_index=ITEMS_TAB, item_index=1),
    ]
    result = bulk_extract_from_d2i(work, selections, db)

    statuses = [o.status for o in result.outcomes]
    assert statuses == [
        BulkArchiveStatus.ARCHIVED,
        BulkArchiveStatus.SKIPPED_INVALID_INDEX,
        BulkArchiveStatus.SKIPPED_INVALID_INDEX,
        BulkArchiveStatus.ARCHIVED,
    ]
    assert result.archived_count == 2


# --------------------------------------------------------------------- #
# Per-call invariants - exactly one backup
# --------------------------------------------------------------------- #


def test_one_backup_per_call_regardless_of_count(workspace, monkeypatch):
    """A multi-item call invokes ``archive_module.create_backup`` exactly
    ONCE. Looping the single-item ``extract_from_d2i`` would invoke it
    once per item - this is the headline reason the bulk endpoint
    exists."""
    work, db = workspace
    call_count = {"n": 0}

    from d2rr_toolkit import archive as archive_mod

    real_backup = archive_mod.create_backup

    def _spy(p):
        call_count["n"] += 1
        return real_backup(p)

    monkeypatch.setattr(archive_mod, "create_backup", _spy)

    selections = [BulkArchiveSelection(tab_index=ITEMS_TAB, item_index=i) for i in range(2)]
    result = bulk_extract_from_d2i(work, selections, db)

    assert result.backup_path is not None
    assert result.backup_path.exists()
    assert call_count["n"] == 1, f"expected exactly one create_backup call, got {call_count['n']}"


def test_total_items_drops_by_archived_count_only(workspace):
    """The on-disk file's total item count after the call is
    ``original_total - archived_count`` - skips do NOT reduce the
    count."""
    work, db = workspace
    sh_before = D2IParser(work).parse()
    total_before = sh_before.total_items

    selections = [
        BulkArchiveSelection(tab_index=ITEMS_TAB, item_index=0),  # ARCHIVED
        BulkArchiveSelection(tab_index=99, item_index=0),  # SKIPPED_INVALID_INDEX
        BulkArchiveSelection(tab_index=ITEMS_TAB, item_index=1),  # ARCHIVED
    ]
    result = bulk_extract_from_d2i(work, selections, db)

    sh_after = D2IParser(work).parse()
    assert result.archived_count == 2
    assert sh_after.total_items == total_before - 2


# --------------------------------------------------------------------- #
# Atomicity - rollback on write/verify failure
# --------------------------------------------------------------------- #


def test_write_failure_rolls_back_db_inserts(workspace, monkeypatch):
    """Force a writer failure (monkey-patch ``D2IWriter.write`` to
    raise) and verify that NO DB rows survive and the source
    file is unchanged."""
    work, db = workspace
    src_before = work.read_bytes()
    db_count_before = db.count()

    from d2rr_toolkit.writers import d2i_writer as dw

    def _raise(self, *_a, **_kw):
        raise dw.D2IWriterIntegrityError("synthetic write failure")

    monkeypatch.setattr(dw.D2IWriter, "write", _raise)

    selections = [BulkArchiveSelection(tab_index=ITEMS_TAB, item_index=i) for i in range(2)]
    with pytest.raises(ArchiveError, match="refused to avoid SharedStash corruption"):
        bulk_extract_from_d2i(work, selections, db)

    assert db.count() == db_count_before, "DB rows leaked past a failed bulk write"
    assert work.read_bytes() == src_before, "source file mutated on failed bulk write"


def test_per_item_db_failure_keeps_batch_going(workspace, monkeypatch):
    """A transient DB failure on ONE selection skips that item with
    ERROR_DB_INSERT but allows the rest of the batch to proceed."""
    work, db = workspace

    real_store = db.store_item
    call_count = {"n": 0}

    def _flaky_store(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("synthetic DB error on second insert")
        return real_store(*args, **kwargs)

    monkeypatch.setattr(db, "store_item", _flaky_store)

    selections = [BulkArchiveSelection(tab_index=ITEMS_TAB, item_index=i) for i in range(2)]
    result = bulk_extract_from_d2i(work, selections, db)

    statuses = [o.status for o in result.outcomes]
    # First insert succeeds, second fails on the parent item store.
    assert statuses[0] == BulkArchiveStatus.ARCHIVED
    assert statuses[1] == BulkArchiveStatus.ERROR_DB_INSERT
    assert "synthetic DB error" in result.outcomes[1].error
    assert result.archived_count == 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    pytest.main([__file__, "-v"])

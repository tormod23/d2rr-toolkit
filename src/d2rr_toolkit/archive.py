"""Archive Operations - high-level extract/restore for the Infinite Archive.

Combines parser, writer, backup, and database layers to provide safe
item transfer between save files and the external database.

SAFETY: Every write operation is preceded by an automatic backup.
The written file is verified by re-parsing before completion.

## Single-item vs bulk API

For single-item operations use :func:`extract_from_d2i`. For
multi-item operations (the GUI's "Archive all" button, future
multi-select archival) use :func:`bulk_extract_from_d2i` - it
runs ONE backup, ONE write, ONE verify and rolls back ALL
inserts on failure, instead of N independent transactions.
Calling :func:`extract_from_d2i` in a loop is correct but slow
and emits N backup files. Prefer the bulk path for any list of
two or more items.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from d2rr_toolkit.backup import create_backup
from d2rr_toolkit.database.item_db import ItemDatabase
from d2rr_toolkit.exceptions import D2SWriteError
from d2rr_toolkit.models.character import ItemFlags, ParsedItem
from d2rr_toolkit.parsers.d2i_parser import D2IParser
from d2rr_toolkit.parsers.d2s_parser import D2SParser
from d2rr_toolkit.writers.d2i_writer import (
    D2I_EMPTY_SECTION_SIZE,
    D2IOrphanExtrasError,
    D2IWriter,
    D2IWriterIntegrityError,
    _find_sections,
)
from d2rr_toolkit.writers.d2s_writer import D2SWriter

logger = logging.getLogger(__name__)


class ArchiveError(Exception):
    """Raised when an archive operation fails."""


def _verify_d2i_on_disk(
    d2i_path: Path,
    *,
    expected_total_items: int,
    backup_path: Path,
) -> None:
    """Hardened post-write verification for .d2i files.

    Checks THREE things, each of which catches a real corruption class:

    1. **Structural**: every section re-parses, every ``jm_count == 0``
       section has ``section_size == 68`` (canonical empty form). Catches
       the phantom-padding bug that bricked ModernSharedStashSoftCoreV2.d2i.
    2. **Size conservation**: the sum of section sizes + trailer equals the
       file length. Catches byte-splice arithmetic errors.
    3. **Semantic**: the parsed ``total_items`` matches the caller's
       expectation. Catches lost items.

    On ANY failure: restore the original file from ``backup_path`` and raise
    :class:`ArchiveError`. A broken SharedStash in the save directory blocks
    every character from loading - auto-restore is the only safe default.

    Args:
        d2i_path:             File path that was just written.
        expected_total_items: What the caller expects ``stash.total_items``
                              to be after the operation.
        backup_path:          Path to the pre-write backup used for rollback.
    """

    def _rollback(reason: str) -> None:
        try:
            data = backup_path.read_bytes()
            d2i_path.write_bytes(data)
            logger.error(
                "Post-write verification failed (%s). Restored %s from backup %s.",
                reason,
                d2i_path,
                backup_path,
            )
        except Exception as restore_err:  # pragma: no cover
            logger.critical(
                "POST-WRITE VERIFICATION FAILED AND ROLLBACK ALSO FAILED: %s "
                "(original reason: %s). Manual restore required from %s.",
                restore_err,
                reason,
                backup_path,
            )

    # 1+2. Structural + size conservation
    try:
        raw = d2i_path.read_bytes()
        sections = _find_sections(raw)
    except Exception as e:
        _rollback(f"cannot re-read written file: {e}")
        raise ArchiveError(
            f"Written file {d2i_path} is unreadable - restored from {backup_path}."
        ) from e

    # Load backup sections to distinguish pre-existing corruption (passed
    # through verbatim) from newly introduced corruption (writer bug).
    try:
        backup_raw = backup_path.read_bytes()
        backup_sections = _find_sections(backup_raw)
    except Exception:
        backup_sections = []

    def _section_was_already_broken(idx: int) -> bool:
        """True if the backup has the same section with the same malformation."""
        if idx >= len(backup_sections):
            return False
        bsec = backup_sections[idx]
        return bsec.item_count == 0 and bsec.section_size != D2I_EMPTY_SECTION_SIZE

    for idx, sec in enumerate(sections):
        if sec.item_count == 0 and sec.section_size != D2I_EMPTY_SECTION_SIZE:
            if _section_was_already_broken(idx):
                logger.warning(
                    "Pre-existing malformed empty section %d in %s "
                    "(size=%d, canonical=%d) - passed through from backup. "
                    "Not a new writer bug.",
                    idx,
                    d2i_path.name,
                    sec.section_size,
                    D2I_EMPTY_SECTION_SIZE,
                )
                continue
            _rollback(
                f"section {idx}: jm_count=0 but section_size={sec.section_size} "
                f"(canonical={D2I_EMPTY_SECTION_SIZE})"
            )
            raise ArchiveError(
                f"Writer produced malformed empty section {idx} "
                f"(size={sec.section_size}, expected={D2I_EMPTY_SECTION_SIZE}). "
                f"File restored from {backup_path}. "
                f"This is a writer bug - please file a report."
            )
        if sec.header_offset + sec.section_size > len(raw):
            _rollback(f"section {idx} overruns file")
            raise ArchiveError(
                f"Writer produced section {idx} that overruns the file. "
                f"Restored from {backup_path}."
            )

    if sections:
        sections_end = sections[-1].header_offset + sections[-1].section_size
        if sections_end > len(raw):
            _rollback("sections exceed file length")
            raise ArchiveError(f"Section layout exceeds file length. Restored from {backup_path}.")

    # 3. Semantic
    try:
        verify_stash = D2IParser(d2i_path).parse()
    except Exception as e:
        _rollback(f"re-parse failed: {e}")
        raise ArchiveError(
            f"Written file failed re-parse: {e} - restored from {backup_path}."
        ) from e

    if verify_stash.total_items != expected_total_items:
        _rollback(
            f"item count mismatch (got={verify_stash.total_items}, expected={expected_total_items})"
        )
        raise ArchiveError(
            f"Item count mismatch after write: expected {expected_total_items}, "
            f"got {verify_stash.total_items}. Restored from {backup_path}."
        )


def extract_from_d2i(
    d2i_path: Path,
    tab_index: int,
    item_index: int,
    db: ItemDatabase,
    display_name: str = "",
) -> int:
    """Extract an item from a D2I shared stash into the database.

    Steps:
    1. BACKUP the save file
    2. Parse the stash
    3. Remove the item from the tab
    4. Store item (display + blob) in database
    5. Write the modified stash
    6. Verify by re-parsing

    Args:
        d2i_path:    Path to the .d2i file.
        tab_index:   Tab to extract from (0-based).
        item_index:  Item index within the tab (0-based).
        db:          ItemDatabase instance.
        display_name: Human-readable name for the item.

    Returns:
        Database row ID of the stored item.

    Raises:
        ArchiveError: If extraction fails at any step.
    """

    # Step 1: BACKUP
    backup_path = create_backup(d2i_path)
    logger.info("Backup created before extraction: %s", backup_path)

    # Step 2: Parse
    try:
        stash = D2IParser(d2i_path).parse()
    except Exception as e:
        raise ArchiveError(f"Failed to parse {d2i_path}: {e}") from e

    # Step 3: Validate and remove
    if tab_index < 0 or tab_index >= len(stash.tabs):
        raise ArchiveError(f"Tab index {tab_index} out of range (0-{len(stash.tabs) - 1})")
    tab = stash.tabs[tab_index]
    if item_index < 0 or item_index >= len(tab.items):
        raise ArchiveError(f"Item index {item_index} out of range (0-{len(tab.items) - 1})")

    item = tab.items[item_index]
    if item.source_data is None:
        raise ArchiveError(f"Item '{item.item_code}' has no source_data - cannot extract")

    # Refuse unidentified items.  The archive is a forever-inventory,
    # so an unidentified blob would permanently obscure its true
    # identity (set / unique / rare affixes) and lock the user out of
    # seeing the roll.  Defense-in-depth: the GUI should also filter,
    # but the archive layer enforces regardless of caller.
    if item.flags is not None and not item.flags.identified:
        raise ArchiveError(
            f"Item '{item.item_code}' is unidentified - identify it in-game "
            f"before archiving so the archive captures the resolved stats."
        )

    # Step 4: Store in database
    db_id = db.store_item(
        item,
        display_name=display_name,
        source_file=str(d2i_path),
        source_tab=tab_index,
    )

    # Step 5: Write modified stash (item removed)
    # Use from_stash() so the writer captures an _original_items snapshot
    # for change detection and uses the byte-splice path. The bare
    # 2-arg constructor would force the legacy full-rebuild path which
    # silently drops socket children and unparsed bytes on grid tabs.
    source_data = d2i_path.read_bytes()
    writer = D2IWriter.from_stash(source_data, stash)
    writer._tab_items[tab_index].pop(item_index)  # noqa: SLF001
    try:
        writer.write(d2i_path)
    except (D2IWriterIntegrityError, D2IOrphanExtrasError) as e:
        # Writer refused to emit malformed output. Nothing was written to
        # disk (the writer's integrity check fires inside build(), before
        # the temp-file rename). Roll the DB insert back.
        db.delete_item(db_id)
        raise ArchiveError(f"Extraction refused to avoid SharedStash corruption: {e}") from e
    except Exception as e:
        # Unknown write failure - item is in DB but stash not modified.
        # Remove from DB to avoid duplication.
        db.delete_item(db_id)
        raise ArchiveError(f"Failed to write {d2i_path}: {e}") from e

    # Step 6: HARDENED post-write verification. Restores from backup on
    # any integrity failure (structural, size-conservation, or semantic).
    try:
        _verify_d2i_on_disk(
            d2i_path,
            expected_total_items=stash.total_items - 1,
            backup_path=backup_path,
        )
    except ArchiveError:
        # File was rolled back; undo the DB insert so caller's view stays
        # consistent with on-disk state.
        db.delete_item(db_id)
        raise

    logger.info(
        "Extracted '%s' (%s) from %s tab %d -> DB id=%d",
        display_name,
        item.item_code,
        d2i_path.name,
        tab_index,
        db_id,
    )
    return db_id


# ─────────────────────────────────────────────────────────────────────────────
# Bulk extract - one atomic operation for multi-item archival
# ─────────────────────────────────────────────────────────────────────────────


class BulkArchiveStatus(str, Enum):
    """Why a single selection in a bulk-archive call ended up in the
    state it did. Stable string values so callers can serialise the
    result (logs, JSON, GUI status text) without round-tripping
    through the enum."""

    ARCHIVED = "archived"
    SKIPPED_UNIDENTIFIED = "skipped_unidentified"
    SKIPPED_INVALID_INDEX = "skipped_invalid_index"
    SKIPPED_NO_SOURCE_DATA = "skipped_no_source_data"
    ERROR_DB_INSERT = "error_db_insert"


@dataclass(frozen=True)
class BulkArchiveSelection:
    """One item to archive in a :func:`bulk_extract_from_d2i` call.

    Items are identified by ``(tab_index, item_index)`` into the
    parsed stash, NOT by live ``ParsedItem`` references - those
    would dangle after the parse-modify-write cycle the bulk
    operation runs internally. The bulk path resolves the
    selection back to a ``ParsedItem`` after parsing.

    The optional metadata fields (``display_name``, ``sprite_key``,
    ``invtransform``) are written verbatim into the DB row. Callers
    that have a richer name resolver (the GUI's
    ``_resolve_display_name`` etc.) should pre-resolve and pass
    the strings; otherwise the toolkit falls back to the item's
    ``item_code`` for ``display_name`` and empty strings for the
    other two so the DB row is well-formed.
    """

    tab_index: int
    item_index: int
    display_name: str = ""
    sprite_key: str = ""
    invtransform: str = ""


@dataclass
class BulkArchiveOutcome:
    """Per-selection result of a bulk-archive operation.

    ``parent_db_id`` is set iff the parent item was successfully
    stored. ``child_db_ids`` lists the database IDs of the parent's
    socket children (runes / gems / jewels) that were stored
    alongside; an empty list either means the item had no children
    or the parent itself was skipped.
    """

    selection: BulkArchiveSelection
    status: BulkArchiveStatus
    item_code: str = ""
    position: tuple[int, int] | None = None  # grid (x, y) for diagnostics
    parent_db_id: int | None = None
    child_db_ids: list[int] = field(default_factory=list)
    error: str = ""

    @property
    def archived(self) -> bool:
        return self.status == BulkArchiveStatus.ARCHIVED


@dataclass
class BulkArchiveResult:
    """Aggregated result of a bulk-archive operation.

    The ``outcomes`` list is in the same order as the input
    selections so callers can correlate by index. The ``by_status``
    helper groups them for the common "summary popup" use case.
    """

    outcomes: list[BulkArchiveOutcome]
    backup_path: Path | None = None

    @property
    def archived(self) -> list[BulkArchiveOutcome]:
        return [o for o in self.outcomes if o.archived]

    def by_status(self, status: BulkArchiveStatus) -> list[BulkArchiveOutcome]:
        return [o for o in self.outcomes if o.status == status]

    @property
    def archived_count(self) -> int:
        return sum(1 for o in self.outcomes if o.archived)

    @property
    def total_count(self) -> int:
        return len(self.outcomes)

    @property
    def has_failures(self) -> bool:
        """True if any selection ended in a non-ARCHIVED state.

        Note: this includes legitimate skips (phantom / unidentified)
        which are NOT errors per se - callers that only want true
        errors should check ``by_status(BulkArchiveStatus.ERROR_*)``
        explicitly.
        """
        return any(not o.archived for o in self.outcomes)


def bulk_extract_from_d2i(
    d2i_path: Path,
    selections: list[BulkArchiveSelection],
    db: ItemDatabase,
) -> BulkArchiveResult:
    """Atomically archive multiple items from a SharedStash file.

    Runs the full extract pipeline ONCE for the whole batch:

      1. **Backup** the source file (one ``.bak`` for the whole batch).
      2. **Parse** the stash.
      3. **Validate** every selection (index in range, item has
         source_data, not a phantom, identified). Selections that
         fail validation are reported in the result with a status
         code; valid selections proceed.
      4. **DB insert** parent items + their socket children. Each
         insert tracks its row id so a later failure can compensate
         (see step 7).
      5. **Build & write** the modified stash. The writer's
         post-build self-check fires before the temp-file rename,
         so a malformed splice never reaches disk.
      6. **Verify** the on-disk file by re-parsing and comparing
         total item counts.
      7. **Rollback on failure** at any of steps 5/6: restore the
         file from the backup AND ``delete_item`` every DB id
         inserted in this call. The DB and the on-disk file end
         up in the pre-call state.

    Single-item ``store_item`` calls are still each their own SQL
    transaction (the existing ``ItemDatabase`` API does
    ``commit()`` per insert), so true SQL-level atomicity would
    require a refactor of ``ItemDatabase``. The compensating
    rollback covers the same correctness goal: any failure leaves
    the persistent state untouched.

    Args:
        d2i_path: Path to the ``.d2i`` file to extract from.
        selections: Items to archive. Each selection refers to a
            position in the parsed stash via ``(tab_index,
            item_index)`` - these are 0-based indices into
            ``ParsedSharedStash.tabs[tab_index].items``.
        db: ``ItemDatabase`` to insert into. Caller owns the
            handle (open/close).

    Returns:
        :class:`BulkArchiveResult` with one outcome per input
        selection (same order). ``archived`` outcomes have
        ``parent_db_id`` set; skipped outcomes carry a status
        code explaining why.

    Raises:
        ArchiveError: Backup, parse, write, or verify failure.
            Individual item-level skips do NOT raise; they
            propagate via the result.
    """
    if not selections:
        return BulkArchiveResult(outcomes=[])

    # ── Step 1: backup ─────────────────────────────────────────────
    try:
        backup_path = create_backup(d2i_path)
    except Exception as e:
        raise ArchiveError(f"Failed to backup {d2i_path}: {e}") from e
    logger.info(
        "Bulk archive: backup created (%d selection(s)): %s",
        len(selections),
        backup_path,
    )

    # ── Step 2: parse ──────────────────────────────────────────────
    try:
        stash = D2IParser(d2i_path).parse()
    except Exception as e:
        raise ArchiveError(f"Failed to parse {d2i_path}: {e}") from e

    source_data = d2i_path.read_bytes()

    # ── Step 3: validate every selection ───────────────────────────
    # Outcomes are kept in INPUT ORDER so callers can correlate by
    # index. We pre-allocate ``None`` slots and fill in as each
    # selection is classified (validated / skipped / archived).
    #
    # Item references resolved here remain valid through the writer
    # pass below: the writer mutates list membership, not items, so
    # an in-list reference still works after siblings are removed.
    outcomes_by_idx: list[BulkArchiveOutcome | None] = [None] * len(selections)
    valid: list[tuple[int, BulkArchiveSelection, ParsedItem]] = []
    for idx, sel in enumerate(selections):
        if sel.tab_index < 0 or sel.tab_index >= len(stash.tabs):
            outcomes_by_idx[idx] = BulkArchiveOutcome(
                selection=sel,
                status=BulkArchiveStatus.SKIPPED_INVALID_INDEX,
                error=(f"tab_index {sel.tab_index} out of range (0..{len(stash.tabs) - 1})"),
            )
            continue
        tab = stash.tabs[sel.tab_index]
        if sel.item_index < 0 or sel.item_index >= len(tab.items):
            outcomes_by_idx[idx] = BulkArchiveOutcome(
                selection=sel,
                status=BulkArchiveStatus.SKIPPED_INVALID_INDEX,
                error=(
                    f"item_index {sel.item_index} out of range "
                    f"(0..{len(tab.items) - 1}) for tab {sel.tab_index}"
                ),
            )
            continue
        item = tab.items[sel.item_index]
        pos = (item.flags.position_x, item.flags.position_y) if item.flags else None
        common = {
            "selection": sel,
            "item_code": item.item_code or "",
            "position": pos,
        }
        if item.source_data is None:
            outcomes_by_idx[idx] = BulkArchiveOutcome(
                status=BulkArchiveStatus.SKIPPED_NO_SOURCE_DATA,
                error="item has no source_data",
                **common,
            )
            continue
        if item.flags is not None and not item.flags.identified:
            outcomes_by_idx[idx] = BulkArchiveOutcome(
                status=BulkArchiveStatus.SKIPPED_UNIDENTIFIED,
                error="item is unidentified; identify it in-game first",
                **common,
            )
            continue
        valid.append((idx, sel, item))

    # If nothing was valid, exit early - no DB writes, no stash
    # write, no rollback needed. Backup file stays (cheap and
    # informative for forensics).
    if not valid:
        outcomes = [o for o in outcomes_by_idx if o is not None]
        return BulkArchiveResult(outcomes=outcomes, backup_path=backup_path)

    # ── Step 4: DB insert pass (parent + children) ────────────────
    # Track every row we write so a later failure can compensate.
    inserted_db_ids: list[int] = []
    archived_indices: list[int] = []
    for idx, sel, item in valid:
        children: list[ParsedItem] = list(item.socket_children or [])
        pos = (item.flags.position_x, item.flags.position_y) if item.flags else None
        try:
            parent_id = db.store_item(
                item,
                display_name=sel.display_name or item.item_code,
                source_file=str(d2i_path),
                source_tab=sel.tab_index,
                sprite_key=sel.sprite_key,
                invtransform=sel.invtransform,
                child_count=len(children),
            )
            inserted_db_ids.append(parent_id)
            child_ids: list[int] = []
            for child in children:
                if child.source_data is None:
                    # Skip children with no source_data but keep the
                    # parent. Logged so it's diagnosable; doesn't
                    # fail the batch.
                    logger.warning(
                        "Bulk archive: child of %s at tab %d index %d "
                        "has no source_data; not inserted",
                        item.item_code,
                        sel.tab_index,
                        sel.item_index,
                    )
                    continue
                child_id = db.store_item(
                    child,
                    display_name=child.item_code,
                    source_file=str(d2i_path),
                    source_tab=-2,  # sentinel: socket child
                )
                inserted_db_ids.append(child_id)
                child_ids.append(child_id)
        except Exception as e:  # noqa: BLE001 - DB layer can raise anything
            outcomes_by_idx[idx] = BulkArchiveOutcome(
                selection=sel,
                status=BulkArchiveStatus.ERROR_DB_INSERT,
                item_code=item.item_code or "",
                position=pos,
                error=str(e),
            )
            # On a per-item DB failure: keep the rest of the batch
            # going. The error item didn't get fully inserted, so
            # don't try to remove it from the stash either.
            continue
        outcomes_by_idx[idx] = BulkArchiveOutcome(
            selection=sel,
            status=BulkArchiveStatus.ARCHIVED,
            item_code=item.item_code or "",
            position=pos,
            parent_db_id=parent_id,
            child_db_ids=child_ids,
        )
        archived_indices.append(idx)

    if not archived_indices:
        # All valid selections failed at DB insert. Bail without
        # touching the stash file. Compensating-delete every
        # already-inserted row.
        _rollback_db_inserts(db, inserted_db_ids)
        outcomes = [o for o in outcomes_by_idx if o is not None]
        return BulkArchiveResult(outcomes=outcomes, backup_path=backup_path)

    # ── Step 5: build + write the modified stash ───────────────────
    writer = D2IWriter.from_stash(source_data, stash)
    # Resolve item references for removal. We do this AFTER the DB
    # insert pass so that the writer's tab_items lists don't shift
    # underneath the indices we used to locate the items.
    items_to_remove_per_tab: dict[int, list[ParsedItem]] = {}
    for idx in archived_indices:
        sel = selections[idx]
        items_to_remove_per_tab.setdefault(sel.tab_index, []).append(
            stash.tabs[sel.tab_index].items[sel.item_index],
        )
    for tab_idx, items in items_to_remove_per_tab.items():
        for item in items:
            try:
                writer._tab_items[tab_idx].remove(item)  # noqa: SLF001
            except ValueError:
                # Should be unreachable after step 3 validation; log
                # and continue so a single bad selection doesn't
                # poison the whole batch.
                logger.warning(
                    "Bulk archive: item not found in writer tab %d "
                    "during removal pass (already removed?)",
                    tab_idx,
                )

    try:
        writer.write(d2i_path)
    except (D2IWriterIntegrityError, D2IOrphanExtrasError) as e:
        # Writer refused to emit malformed output. Nothing reached
        # disk; rollback DB inserts so the caller's view stays
        # consistent.
        _rollback_db_inserts(db, inserted_db_ids)
        raise ArchiveError(
            f"Bulk extraction refused to avoid SharedStash corruption: {e}",
        ) from e
    except Exception as e:
        _rollback_db_inserts(db, inserted_db_ids)
        raise ArchiveError(f"Failed to write {d2i_path}: {e}") from e

    # ── Step 6: verify on disk ─────────────────────────────────────
    archived_count = len(archived_indices)
    try:
        _verify_d2i_on_disk(
            d2i_path,
            expected_total_items=stash.total_items - archived_count,
            backup_path=backup_path,
        )
    except ArchiveError:
        _rollback_db_inserts(db, inserted_db_ids)
        raise

    outcomes = [o for o in outcomes_by_idx if o is not None]
    logger.info(
        "Bulk archive: %d/%d items archived from %s (backup=%s)",
        archived_count,
        len(selections),
        d2i_path.name,
        backup_path.name,
    )
    return BulkArchiveResult(outcomes=outcomes, backup_path=backup_path)


def _rollback_db_inserts(db: ItemDatabase, db_ids: list[int]) -> None:
    """Compensating-delete every row in ``db_ids`` from the database.

    Used by :func:`bulk_extract_from_d2i` when a write or verify
    step fails after the DB-insert pass. Best-effort: a failure to
    delete one row does NOT abort cleaning up the rest, so the
    caller-visible state is "as close to pre-call as possible".
    """
    for db_id in db_ids:
        try:
            db.delete_item(db_id)
        except Exception:  # noqa: BLE001 - cleanup must not raise
            logger.exception(
                "Failed to compensate-delete DB id=%d during bulk-archive "
                "rollback; orphan row left in the database",
                db_id,
            )


# ─────────────────────────────────────────────────────────────────────────────
# Bulk extract - D2S character-file variant
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BulkArchiveSelectionD2S:
    """One item to archive in a :func:`bulk_extract_from_d2s` call.

    D2S character files store items as a single flat list (no tabs),
    so selections only need an ``item_index`` into
    ``ParsedCharacter.items``. Callers that want to operate on a
    specific container (Personal stash, Inventory, Cube, ...) filter
    the input list themselves using ``flags.location_id`` /
    ``flags.panel_id`` before assembling selections - the toolkit
    does not enforce a container filter.

    Optional metadata fields (``display_name``, ``sprite_key``,
    ``invtransform``) flow verbatim into the DB row, the same way
    they do for the D2I variant.
    """

    item_index: int
    display_name: str = ""
    sprite_key: str = ""
    invtransform: str = ""


def _verify_d2s_on_disk(
    d2s_path: Path,
    *,
    expected_total_items: int,
    backup_path: Path,
) -> None:
    """Light post-write verification for .d2s files.

    Re-parses the written file and checks that the total parsed
    item count matches the caller's expectation. On mismatch the
    file is rolled back from ``backup_path`` and an
    :class:`ArchiveError` is raised.

    Less involved than :func:`_verify_d2i_on_disk` because D2S
    does not have the section / JM-count surface area that
    surfaces the empty-tab corruption class.  The semantic count
    check is the load-bearing verification: it catches every bug
    where the writer drops or duplicates an item silently.
    """

    def _rollback(reason: str) -> None:
        try:
            d2s_path.write_bytes(backup_path.read_bytes())
            logger.error(
                "D2S post-write verification failed (%s). Restored %s from %s.",
                reason,
                d2s_path,
                backup_path,
            )
        except Exception as restore_err:  # pragma: no cover
            logger.critical(
                "D2S post-write verification failed AND rollback failed: "
                "%s (original: %s). Manual restore from %s required.",
                restore_err,
                reason,
                backup_path,
            )

    try:
        verify_char = D2SParser(d2s_path).parse()
    except Exception as e:
        _rollback(f"re-parse failed: {e}")
        raise ArchiveError(
            f"Written D2S file failed re-parse: {e} - restored from {backup_path}.",
        ) from e

    actual = len(verify_char.items)
    if actual != expected_total_items:
        _rollback(
            f"item count mismatch (got={actual}, expected={expected_total_items})",
        )
        raise ArchiveError(
            f"D2S item count mismatch after write: expected "
            f"{expected_total_items}, got {actual}. "
            f"Restored from {backup_path}.",
        )


def bulk_extract_from_d2s(
    d2s_path: Path,
    selections: list[BulkArchiveSelectionD2S],
    db: ItemDatabase,
) -> BulkArchiveResult:
    """Atomically archive multiple items from a D2S character file.

    Parallel to :func:`bulk_extract_from_d2i` for the personal-
    stash / inventory / cube containers that live inside a .d2s
    character save. Pipeline:

      1. **Backup** the source file once (one ``.bak`` for the
         whole batch; the ``D2SWriter`` then creates its own
         backup inside ``write()`` as a separate safety net,
         matching the d2i path's two-backup pattern).
      2. **Parse** the character.
      3. **Validate** every selection (item_index in range,
         source_data present, not a phantom, identified). Skips
         are reported via the result, NOT raised.
      4. **DB insert** each valid parent item + its socket
         children. Tracked db_ids enable compensating rollback.
      5. **Build & write** through ``D2SWriter.remove_items_by_indices``
         + ``write()`` (atomic temp-file rename inside).
      6. **Verify** by re-parsing and matching item count.
      7. **Rollback on failure**: restore file from backup AND
         delete every db_id inserted in this call.

    Args:
        d2s_path: Path to the ``.d2s`` character file.
        selections: Items to archive, identified by
            ``(item_index)`` into ``character.items``.
        db: ``ItemDatabase`` for the inserts.

    Returns:
        :class:`BulkArchiveResult` with one outcome per input
        selection (in input order).

    Raises:
        ArchiveError: Backup, parse, write, or verify failure.
            Per-item skips do NOT raise.
    """
    if not selections:
        return BulkArchiveResult(outcomes=[])

    # ── Step 1: backup ─────────────────────────────────────────────
    try:
        backup_path = create_backup(d2s_path)
    except Exception as e:
        raise ArchiveError(f"Failed to backup {d2s_path}: {e}") from e
    logger.info(
        "Bulk archive (d2s): backup created (%d selection(s)): %s",
        len(selections),
        backup_path,
    )

    # ── Step 2: parse ──────────────────────────────────────────────
    try:
        character = D2SParser(d2s_path).parse()
    except Exception as e:
        raise ArchiveError(f"Failed to parse {d2s_path}: {e}") from e

    source_data = d2s_path.read_bytes()
    items = character.items

    # ── Step 3: validate every selection ───────────────────────────
    # Outcomes pre-allocated so the result preserves input order.
    outcomes_by_idx: list[BulkArchiveOutcome | None] = [None] * len(selections)
    valid: list[tuple[int, BulkArchiveSelectionD2S, ParsedItem]] = []
    for idx, sel in enumerate(selections):
        # Wrap the d2s selection in a synthetic d2i-shaped selection
        # for the outcome record so callers using both variants get
        # a uniform ``BulkArchiveOutcome.selection`` interface (the
        # outcome carries the d2s selection unchanged via this
        # adapter; tab_index is set to -1 to mark "d2s, no tabs").
        adapter_sel = BulkArchiveSelection(
            tab_index=-1,
            item_index=sel.item_index,
            display_name=sel.display_name,
            sprite_key=sel.sprite_key,
            invtransform=sel.invtransform,
        )
        if sel.item_index < 0 or sel.item_index >= len(items):
            outcomes_by_idx[idx] = BulkArchiveOutcome(
                selection=adapter_sel,
                status=BulkArchiveStatus.SKIPPED_INVALID_INDEX,
                error=(f"item_index {sel.item_index} out of range (0..{len(items) - 1})"),
            )
            continue
        item = items[sel.item_index]
        pos = (item.flags.position_x, item.flags.position_y) if item.flags else None
        common = {
            "selection": adapter_sel,
            "item_code": item.item_code or "",
            "position": pos,
        }
        if item.source_data is None:
            outcomes_by_idx[idx] = BulkArchiveOutcome(
                status=BulkArchiveStatus.SKIPPED_NO_SOURCE_DATA,
                error="item has no source_data",
                **common,
            )
            continue
        if item.flags is not None and not item.flags.identified:
            outcomes_by_idx[idx] = BulkArchiveOutcome(
                status=BulkArchiveStatus.SKIPPED_UNIDENTIFIED,
                error="item is unidentified; identify it in-game first",
                **common,
            )
            continue
        valid.append((idx, sel, item))

    if not valid:
        outcomes = [o for o in outcomes_by_idx if o is not None]
        return BulkArchiveResult(outcomes=outcomes, backup_path=backup_path)

    # ── Step 4: DB insert (parent + socket children) ───────────────
    inserted_db_ids: list[int] = []
    archived_indices: list[int] = []
    for idx, sel, item in valid:
        children: list[ParsedItem] = list(item.socket_children or [])
        pos = (item.flags.position_x, item.flags.position_y) if item.flags else None
        adapter_sel = BulkArchiveSelection(
            tab_index=-1,
            item_index=sel.item_index,
            display_name=sel.display_name,
            sprite_key=sel.sprite_key,
            invtransform=sel.invtransform,
        )
        try:
            parent_id = db.store_item(
                item,
                display_name=sel.display_name or item.item_code,
                source_file=str(d2s_path),
                source_tab=-1,  # sentinel: d2s personal-stash / inventory / cube
                sprite_key=sel.sprite_key,
                invtransform=sel.invtransform,
                child_count=len(children),
            )
            inserted_db_ids.append(parent_id)
            child_ids: list[int] = []
            for child in children:
                if child.source_data is None:
                    logger.warning(
                        "Bulk archive (d2s): child of %s at index %d has no "
                        "source_data; not inserted",
                        item.item_code,
                        sel.item_index,
                    )
                    continue
                child_id = db.store_item(
                    child,
                    display_name=child.item_code,
                    source_file=str(d2s_path),
                    source_tab=-2,  # sentinel: socket child
                )
                inserted_db_ids.append(child_id)
                child_ids.append(child_id)
        except Exception as e:  # noqa: BLE001
            outcomes_by_idx[idx] = BulkArchiveOutcome(
                selection=adapter_sel,
                status=BulkArchiveStatus.ERROR_DB_INSERT,
                item_code=item.item_code or "",
                position=pos,
                error=str(e),
            )
            continue
        outcomes_by_idx[idx] = BulkArchiveOutcome(
            selection=adapter_sel,
            status=BulkArchiveStatus.ARCHIVED,
            item_code=item.item_code or "",
            position=pos,
            parent_db_id=parent_id,
            child_db_ids=child_ids,
        )
        archived_indices.append(idx)

    if not archived_indices:
        _rollback_db_inserts(db, inserted_db_ids)
        outcomes = [o for o in outcomes_by_idx if o is not None]
        return BulkArchiveResult(outcomes=outcomes, backup_path=backup_path)

    # ── Step 5: build + write through D2SWriter ────────────────────
    writer = D2SWriter(source_data, character)
    archived_item_indices = {selections[idx].item_index for idx in archived_indices}
    try:
        writer.remove_items_by_indices(archived_item_indices)
    except D2SWriteError as e:
        _rollback_db_inserts(db, inserted_db_ids)
        raise ArchiveError(
            f"Bulk D2S extraction refused: writer rejected the index set: {e}",
        ) from e

    try:
        writer.write(d2s_path)
    except Exception as e:  # noqa: BLE001
        _rollback_db_inserts(db, inserted_db_ids)
        raise ArchiveError(f"Failed to write {d2s_path}: {e}") from e

    # ── Step 6: verify ─────────────────────────────────────────────
    archived_count = len(archived_indices)
    try:
        _verify_d2s_on_disk(
            d2s_path,
            expected_total_items=len(items) - archived_count,
            backup_path=backup_path,
        )
    except ArchiveError:
        _rollback_db_inserts(db, inserted_db_ids)
        raise

    outcomes = [o for o in outcomes_by_idx if o is not None]
    logger.info(
        "Bulk archive (d2s): %d/%d items archived from %s (backup=%s)",
        archived_count,
        len(selections),
        d2s_path.name,
        backup_path.name,
    )
    return BulkArchiveResult(outcomes=outcomes, backup_path=backup_path)


def restore_to_d2i(
    db_item_id: int,
    d2i_path: Path,
    tab_index: int,
    db: ItemDatabase,
) -> None:
    """Restore an item from the database into a D2I shared stash.

    Steps:
    1. BACKUP the save file
    2. Parse the stash
    3. Get item blob from database
    4. Create a minimal ParsedItem with the blob
    5. Insert into the target tab
    6. Write the modified stash
    7. Verify by re-parsing
    8. Mark item as 'restored' in database

    Args:
        db_item_id:  Database row ID of the item to restore.
        d2i_path:    Path to the .d2i file.
        tab_index:   Tab to insert into (0-based).
        db:          ItemDatabase instance.

    Raises:
        ArchiveError: If restoration fails.
    """

    # Step 1: BACKUP
    backup_path = create_backup(d2i_path)
    logger.info("Backup created before restoration: %s", backup_path)

    # Step 2: Parse
    try:
        stash = D2IParser(d2i_path).parse()
    except Exception as e:
        raise ArchiveError(f"Failed to parse {d2i_path}: {e}") from e

    # Step 3: Get item from database
    stored = db.get_item(db_item_id)
    if stored is None:
        raise ArchiveError(f"Item id={db_item_id} not found in database")
    if stored.status != "available":
        raise ArchiveError(f"Item id={db_item_id} is not available (status={stored.status})")

    # Step 4: Create minimal ParsedItem with the blob
    # We need at minimum: item_code, flags, source_data.
    # The source_data IS the complete binary blob.
    placeholder_item = ParsedItem(
        item_code=stored.item_code,
        flags=ItemFlags(
            identified=True,
            socketed=stored.is_socketed,
            starter_item=False,
            simple=False,
            ethereal=stored.is_ethereal,
            personalized=False,
            runeword=stored.is_runeword,
            location_id=0,
            equipped_slot=0,
            position_x=0,
            position_y=0,
            panel_id=1,
        ),
        source_data=stored.source_data,
    )

    # Step 5: Insert into target tab
    if tab_index < 0 or tab_index >= len(stash.tabs):
        raise ArchiveError(f"Tab index {tab_index} out of range (0-{len(stash.tabs) - 1})")

    # Step 6: Write
    # from_stash() captures the pre-mutation snapshot in _original_items;
    # the append below then registers as the only change against that
    # snapshot, triggering the safe byte-splice path.
    source_data = d2i_path.read_bytes()
    writer = D2IWriter.from_stash(source_data, stash)
    writer._tab_items[tab_index].append(placeholder_item)  # noqa: SLF001
    try:
        writer.write(d2i_path)
    except (D2IWriterIntegrityError, D2IOrphanExtrasError) as e:
        raise ArchiveError(f"Restoration refused to avoid SharedStash corruption: {e}") from e
    except Exception as e:
        raise ArchiveError(f"Failed to write {d2i_path}: {e}") from e

    # Step 7: HARDENED post-write verification (restores from backup on
    # any integrity failure).
    _verify_d2i_on_disk(
        d2i_path,
        expected_total_items=stash.total_items + 1,
        backup_path=backup_path,
    )

    # Step 8: Mark restored
    db.mark_restored(db_item_id)
    logger.info(
        "Restored '%s' (%s) from DB id=%d -> %s tab %d",
        stored.item_name,
        stored.item_code,
        db_item_id,
        d2i_path.name,
        tab_index,
    )

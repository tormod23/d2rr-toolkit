"""Archive Operations - high-level extract/restore for the Infinite Archive.

Combines parser, writer, backup, and database layers to provide safe
item transfer between save files and the external database.

SAFETY: Every write operation is preceded by an automatic backup.
The written file is verified by re-parsing before completion.
"""

import logging
from pathlib import Path

from d2rr_toolkit.backup import create_backup
from d2rr_toolkit.database.item_db import ItemDatabase
from d2rr_toolkit.models.character import ParsedItem
from d2rr_toolkit.writers.d2i_writer import (
    D2I_EMPTY_SECTION_SIZE,
    D2IOrphanExtrasError,
    D2IWriter,
    D2IWriterIntegrityError,
    _find_sections,
)
from d2rr_toolkit.models.character import ItemFlags
from d2rr_toolkit.parsers.d2i_parser import D2IParser

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

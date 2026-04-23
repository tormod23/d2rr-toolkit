"""D2S Character Writer - byte-splice item injection into .d2s files.

Uses blob preservation: the ORIGINAL source file structure is preserved.
Only the item section is replaced. Header, stats, skills, corpse, merc, and
golem sections remain byte-identical to the source file.

D2S Item Section Layout:
    [JM(2) + count(2) + item_blobs...]     <- player items (1st JM)
    [JM(2) + count(2) + corpse_items...]   <- corpse items (2nd JM)
    [jf(2) + merc JM + merc_items...]      <- mercenary
    [kf(2) + golem_byte + golem_item?]     <- iron golem

The writer replaces only the 1st JM section (player items) and preserves
everything from the 2nd JM onward.
"""

from __future__ import annotations

import logging
import struct
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from d2rr_toolkit.constants import (
    LOCATION_BELT,
    LOCATION_EQUIPPED,
    SECTION_MARKER_ITEMS,
)
from d2rr_toolkit.models.character import ParsedCharacter, ParsedItem
from d2rr_toolkit.writers.checksum import patch_checksum, patch_file_size, patch_timestamp

if TYPE_CHECKING:
    from d2rr_toolkit.game_data.item_names import ItemNamesDatabase

logger = logging.getLogger(__name__)


# D2SWriteError moved to d2rr_toolkit.exceptions so the writer helper
# module (item_utils.py) can import it without a circular dependency.
# Re-exported here for backwards compatibility with callers that
# imported it from this module.
from d2rr_toolkit.exceptions import D2SWriteError  # noqa: E402,F401


class D2SWriter:
    """Byte-splice D2S writer for item injection and removal.

    Takes the original .d2s file bytes and a ParsedCharacter (from the parser),
    then allows adding/removing items before building the modified file.

    Usage:
        source_data = Path("char.d2s").read_bytes()
        character = D2SParser(Path("char.d2s")).parse()
        writer = D2SWriter(source_data, character)
        writer.inject_items(cool_items)
        writer.write(Path("char_modified.d2s"))
    """

    def __init__(
        self,
        source_data: bytes,
        character: ParsedCharacter,
        item_names_db: ItemNamesDatabase | None = None,
    ) -> None:
        if character.items_jm_byte_offset is None:
            raise D2SWriteError(
                "ParsedCharacter has no items_jm_byte_offset - was it parsed with the latest parser?"
            )
        # corpse_jm_byte_offset may be None if the parser's extra-items
        # recovery could not locate the 2nd JM marker. The unmodified
        # fast-path in build() doesn't need it; append_item() checks it
        # explicitly. Only the full rebuild path in build() requires it.
        # Trailing bytes between last parsed item and corpse JM are now
        # captured by the parser and preserved during rebuild.

        self._source = source_data
        self._character = character
        self._items: list[ParsedItem] = list(character.items)
        self._items_jm_offset = character.items_jm_byte_offset
        self._corpse_jm_offset = character.corpse_jm_byte_offset
        self._item_names_db = item_names_db
        # Tracks whether the item list has been changed since construction.
        # build() short-circuits to byte-identical source output when False,
        # which is both faster and resilient to parser edge-cases that drop
        # trailing padding or unparsed items from source_data (see
        # project_d2s_parser_trailing_items_bug.md).
        self._modified = False
        self._trailing_item_bytes = character.trailing_item_bytes or b""

    def inject_items(self, items: list[ParsedItem]) -> None:
        """Add root items (with embedded socket children) to the character.

        Each item carries its own socket children in ``socket_children``.
        The writer serialises parent + children sequentially.

        Validates:
        - Every item and child has source_data
        - carry1 restrictions (unique items)
        - Socket children completeness

        Args:
            items: Root items with source_data and correct positions.

        Raises:
            D2SWriteError: If any item/child lacks source_data, violates
                carry1, or has incomplete socket children.
        """
        for item in items:
            if not item.source_data:
                raise D2SWriteError(f"Item '{item.item_code}' has no source_data - cannot inject.")
            for child in item.socket_children:
                if not child.source_data:
                    raise D2SWriteError(
                        f"Socket child '{child.item_code}' of '{item.item_code}' "
                        f"has no source_data - cannot inject."
                    )

        # Validate socket children completeness.
        for item in items:
            if not item.flags.socketed or (item.total_nr_of_sockets or 0) == 0:
                continue
            expected = item.total_nr_of_sockets
            actual = len(item.socket_children)
            if actual < expected:
                raise D2SWriteError(
                    f"Socketed item '{item.item_code}' has {expected} sockets "
                    f"but only {actual} children in socket_children."
                )

        # carry1 validation happens in build() on the FINAL item list -
        # this is idempotent and catches conflicts whether items arrived
        # via inject_items() or via direct character.items mutation.

        self._items.extend(items)
        self._modified = True
        logger.info("Injected %d items (total now: %d)", len(items), len(self._items))

    def _validate_carry1(self, items: list[ParsedItem] | None = None) -> None:
        """Check that no carry1 group appears more than once in the item list.

        Operates on the FINAL item list (self._items by default) - idempotent
        and resilient to any mutation pattern. Raises D2SWriteError on
        conflict (two items with the same carry1 group).
        """
        if self._item_names_db is None:
            raise D2SWriteError(
                "_validate_carry1 invoked before _item_names_db was set; "
                "this is a writer-lifecycle bug, please report."
            )
        db = self._item_names_db
        items_to_check = items if items is not None else self._items

        seen: dict[str, str] = {}  # carry1_group -> item description
        for item in items_to_check:
            carry1 = self._get_carry1(item, db)
            if carry1 is None:
                continue
            name = (
                db.get_unique_name(item.unique_type_id)
                if item.unique_type_id is not None
                else item.item_code
            )
            item_desc = name or item.item_code
            if carry1 in seen:
                raise D2SWriteError(
                    f"carry1 conflict: two items with carry1={carry1} "
                    f"('{item_desc}' and '{seen[carry1]}'). "
                    f"Only one item per carry1 group is allowed per character."
                )
            seen[carry1] = item_desc

    @staticmethod
    def _get_carry1(item: ParsedItem, db: ItemNamesDatabase) -> str | None:
        """Return the carry1 group for an item, or None if unrestricted."""
        if item.unique_type_id is not None and item.extended and item.extended.quality == 7:
            return db.get_unique_carry1(item.unique_type_id)
        return None

    def remove_items_by_indices(self, indices: set[int]) -> list[ParsedItem]:
        """Remove specific items by their indices in self._items.

        Automatically expands the removal set to include socket children of
        any selected socketed parent: all consecutive items with
        location_id == LOCATION_SOCKETED immediately following a parent are
        included. This matches the D2S convention where equipped socket
        children are stored inline after their parent.

        Args:
            indices: Set of 0-based indices into self._items.

        Returns:
            List of removed items (including auto-expanded socket children).

        Raises:
            D2SWriteError: If any index is out of range.
        """
        if not indices:
            return []

        max_idx = len(self._items) - 1
        for idx in indices:
            if idx < 0 or idx > max_idx:
                raise D2SWriteError(f"Item index {idx} out of range (0..{max_idx}).")

        # Items already carry their socket children - no expansion needed.
        expanded = set(indices)

        keep = []
        removed = []
        for i, item in enumerate(self._items):
            if i in expanded:
                removed.append(item)
            else:
                keep.append(item)
        self._items = keep
        if removed:
            self._modified = True
        logger.info("Removed %d items by index", len(removed))
        return removed

    def remove_stored_items(self) -> list[ParsedItem]:
        """Remove all inventory/stash/cube items, keeping equipped, belt, and socketed.

        Returns:
            List of removed items.
        """
        keep = []
        removed = []
        for item in self._items:
            loc = item.flags.location_id
            if loc in (LOCATION_EQUIPPED, LOCATION_BELT):
                keep.append(item)
            else:
                removed.append(item)
        self._items = keep
        if removed:
            self._modified = True
        logger.info("Removed %d stored items, keeping %d", len(removed), len(keep))
        return removed

    def append_item(self, item: ParsedItem, item_count: int = 1) -> bytes:
        """Append an item (optionally with socket children) by byte-splicing.

        Unlike inject_items() + build() which rebuilds the entire item section,
        this method inserts the blob at the correct position and increments the
        JM count in-place. The rest of the file stays byte-identical.

        ## Insert position

        The D2S item region between the 1st JM and 2nd JM (corpse) contains:
            [JM(2) + count(2)]
            [JM-counted items: count * variable-length blobs]
            [Extra items: stash socket children, misc items - NOT in JM count]
            [2nd JM (corpse)]

        The new blob is inserted AFTER the last JM-counted item (i.e. at the
        boundary between counted items and extras). This keeps the JM count
        accurately reflects the new item(s) and the parser re-reads correctly.

        ## Socketed items

        For items with socket children, `item.source_data` should contain the
        concatenated blobs of parent + all children. Set `item_count` to
        `1 + child_count` so the JM count is incremented by the correct total
        (parent + children are all individually counted in the JM header).

        Args:
            item: ParsedItem with source_data (may be concatenated parent+children).
            item_count: Number of logical items in the blob (1 for unsocketed,
                        1+child_count for socketed items with children).

        Returns:
            Complete modified .d2s file as bytes.

        Raises:
            D2SWriteError: if item has no source_data.
        """
        if not item.source_data:
            raise D2SWriteError(f"Item '{item.item_code}' has no source_data.")

        blob = item.source_data

        # Read current JM count from the source
        count_offset = self._items_jm_offset + 2
        old_count = struct.unpack_from("<H", self._source, count_offset)[0]

        # Compute insert position: after ALL parsed items (root + children).
        insert_offset = self._items_jm_offset + 4  # after JM(2) + count(2)
        for root in self._items:
            if root.source_data:
                insert_offset += len(root.source_data)
            for child in root.socket_children:
                if child.source_data:
                    insert_offset += len(child.source_data)

        # Splice: [before insert] + [new blob] + [from insert onward]
        result = bytearray(self._source[:insert_offset])
        result += blob
        result += self._source[insert_offset:]

        # Increment the JM item count by the full item_count (parent + children)
        new_count = old_count + item_count
        struct.pack_into("<H", result, count_offset, new_count)

        # Update timestamp, file size, and checksum.
        # Timestamp MUST be updated before checksum - the game rejects files
        # with a stale 'last saved' timestamp at offset 0x20 as corrupt.
        # [BV]
        patch_timestamp(result)
        patch_file_size(result)
        checksum = patch_checksum(result)
        logger.info(
            "Appended item '%s' (%d bytes, %d logical items) at offset 0x%X. Count: %d -> %d, checksum=0x%08X",
            item.item_code,
            len(blob),
            item_count,
            insert_offset,
            old_count,
            new_count,
            checksum,
        )
        return bytes(result)

    def build(self) -> bytes:
        """Assemble the modified .d2s file.

        Rebuilds the player item section with the current item list,
        preserves all other sections, and updates file size + checksum.

        When the item list has not been modified since construction (no
        `inject_items` or `remove_stored_items` calls), returns the source
        bytes verbatim. This guarantees byte-identical round trips for
        pass-through workflows and sidesteps a parser edge case where
        trailing items in some D2S files are not captured in source_data
        (see project_d2s_parser_trailing_items_bug.md).

        Returns:
            Complete .d2s file as bytes.
        """
        if not self._modified:
            logger.info(
                "D2SWriter.build(): no modifications - returning source verbatim (%d bytes)",
                len(self._source),
            )
            return bytes(self._source)

        # The rebuild path requires corpse_jm_byte_offset to know where
        # the item section ends. If missing, we cannot rebuild safely.
        if self._corpse_jm_offset is None:
            raise D2SWriteError(
                "Cannot rebuild item section: corpse_jm_byte_offset is None. "
                "Use append_item() for single-item additions instead."
            )

        # Validate all items have source_data
        for i, item in enumerate(self._items):
            if not item.source_data:
                raise D2SWriteError(f"Item {i} ('{item.item_code}') has no source_data.")

        # Validate carry1 on the FINAL item list (idempotent - works
        # regardless of whether items arrived via inject or direct mutation).
        if self._item_names_db is not None:
            self._validate_carry1()

        # NOTE: unique_item_id deduplication was previously enforced here,
        # but empirical evidence shows the game accepts files with duplicate
        # UIDs (verified: monday_test D2I has two jewels sharing UID
        # 0x043197DC0 and loads fine in-game). Rerolling UIDs on every
        # write mutates the source_data unnecessarily and can cause other
        # subtle issues. UIDs are preserved verbatim.

        # JM count = number of ROOT items. Socket children are NOT
        # counted in the JM header - they live in extras (for stash/
        # inventory items) or inline after their equipped parent.
        # Either way, JM covers only root items. [BV TC67: JM=16 with
        # 16 roots + 4 children = 20 flat; CubeContents.GAME: JM=1,
        # 1 root + 0 children]
        #
        # This survives GUI pre-mutation: when the GUI
        # mutates character.items (add/remove) before constructing
        # the writer, _items reflects the new state and len(_items)
        # IS the correct new JM count. [BV minimal.d2s: empty + 1 = 1]
        jm_count = len(self._items)

        # Build new item section: JM(2) + count(2) + item blobs
        item_section = bytearray()
        item_section += SECTION_MARKER_ITEMS  # 'JM'
        item_section += struct.pack("<H", jm_count)  # item count

        # Write each root item followed by its socket children.
        for item in self._items:
            item_section += item.source_data
            for child in item.socket_children:
                item_section += child.source_data

        # Append trailing bytes that the parser could not decode but that
        # belong to the item region (between last parsed item and corpse JM).
        if self._trailing_item_bytes:
            item_section += self._trailing_item_bytes
            logger.info(
                "Appended %d trailing item bytes to rebuilt item section.",
                len(self._trailing_item_bytes),
            )

        # Splice: [before items] + [new item section] + [from corpse JM onward]
        before_items = self._source[: self._items_jm_offset]
        after_items = self._source[self._corpse_jm_offset :]

        result = bytearray(before_items + item_section + after_items)

        # Update timestamp, file size, and checksum.
        # Timestamp MUST be updated before checksum - the game rejects files
        # with a stale 'last saved' timestamp at offset 0x20 as corrupt.
        # [BV]
        patch_timestamp(result)
        patch_file_size(result)
        checksum = patch_checksum(result)
        total_children = sum(len(it.socket_children) for it in self._items)
        logger.info(
            "Built D2S: %d bytes, %d root + %d children, checksum=0x%08X",
            len(result),
            len(self._items),
            total_children,
            checksum,
        )

        return bytes(result)

    def write(self, output_path: Path) -> None:
        """Build and write the modified .d2s file atomically.

        **Automatically creates a timestamped backup** of the existing file
        at ``~/.d2rr_toolkit/backups/<filename>/`` before overwriting it.
        This keeps a full audit trail of every write operation until we
        have high confidence the writer is 100% correct.

        Uses a temporary file + rename to prevent corruption on write failure.

        Args:
            output_path: Destination file path.
        """
        # Safety net: back up the original file BEFORE building the new one.
        # If the target doesn't exist yet (first write), skip the backup.
        from d2rr_toolkit.backup import create_backup

        if output_path.exists():
            backup_path = create_backup(output_path)
            logger.info("Pre-write backup: %s", backup_path)

        data = self.build()

        # Atomic write via temp file
        tmp_fd = tempfile.NamedTemporaryFile(
            dir=output_path.parent,
            suffix=".d2s.tmp",
            delete=False,
        )
        tmp_path = Path(tmp_fd.name)
        try:
            tmp_fd.write(data)
            tmp_fd.close()
            tmp_path.replace(output_path)
            logger.info("Written: %s (%d bytes)", output_path, len(data))
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise


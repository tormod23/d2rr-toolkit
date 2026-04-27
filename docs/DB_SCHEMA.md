# Database Schema

> Verify against source before trusting.

The D2RR Toolkit keeps **one SQLite database per game mode** on disk
- a softcore file and a hardcore file, completely isolated from
each other. Each file holds both the archive (`items` table) and the
Section 5 stash (`section5_stacks`, `gem_pool`, `gem_templates`
tables); the two `*Database` classes cooperate on a shared `meta`
table inside the same file.

## Storage location

By design the DB files live **alongside the D2RR (Reimagined) save
files**, so that a single backup of the
`Saved Games/.../mods/ReimaginedThree/` directory captures both the
user's characters and the toolkit's archive of their items. Note
this is the **modded** save dir - the base-game D2R save dir (without
the `mods/ReimaginedThree` subpath) is never touched by the toolkit.
The default location is resolved via
`d2rr_toolkit.config.resolve_save_dir()`:

| Source (in order)                          | Value |
|--------------------------------------------|-------|
| `D2RR_SAVE_DIR` env var                    | used verbatim |
| Windows heuristic (no env var)             | `%USERPROFILE%\Saved Games\Diablo II Resurrected\mods\ReimaginedThree\` |
| POSIX (no env var)                         | `ConfigurationError` - caller must set the env var or pass `--db` |

The path can always be overridden per-invocation with the CLI's
`--db` flag. The toolkit **never** stores the archive anywhere else
by default (no `~/.d2rr_toolkit/`, no current-working-directory
fallback) - co-locating with saves is the invariant.

| DB file                        | Contents                                                    |
|--------------------------------|-------------------------------------------------------------|
| `d2rr_archive_softcore.db`     | SC archive items + Section 5 stackables (gems / runes / mats). |
| `d2rr_archive_hardcore.db`     | HC counterpart. Physically separate file.                   |

**SC / HC isolation** is enforced at two layers:
1. Physical file separation (above).
2. A meta-table tag inside each database (`game_mode` row in the
   `meta` table) - see
   `src/d2rr_toolkit/database/modes.py` for the `bind_database_mode`
   helper. `open_item_db(mode)` and `open_section5_db(mode)` refuse
   to open a file whose tag disagrees with the requested mode.

## `items` table (`d2rr_archive_{mode}.db`)

Defined in `src/d2rr_toolkit/database/item_db.py`.

| Column             | Type    | Description                                                         |
|--------------------|---------|---------------------------------------------------------------------|
| `id`               | INTEGER | Primary key, autoincrement.                                         |
| `item_code`        | TEXT    | Huffman-decoded item code (e.g. `hbt` for Heavy Boots).             |
| `item_name`        | TEXT    | Resolved display name at extract time.                              |
| `quality`          | INTEGER | 4-bit quality code (2=Normal, 4=Magic, 5=Set, 6=Rare, 7=Unique, 8=Crafted). |
| `quality_name`     | TEXT    | Human label for `quality`.                                          |
| `item_level`       | INTEGER | The item's ilvl (7-bit field).                                      |
| `is_ethereal`      | INTEGER | 0/1 flag.                                                           |
| `is_socketed`      | INTEGER | 0/1 flag.                                                           |
| `is_runeword`      | INTEGER | 0/1 flag.                                                           |
| `properties_json`  | TEXT    | Serialised magical-properties list for search.                      |
| `source_data`      | BLOB    | Raw item bytes (parent + socket children concatenated if socketed). |
| `child_count`      | INTEGER | Number of socket children in `source_data` (0 = no children).       |
| `sprite_key`       | TEXT    | Precomputed sprite key for GUI display (avoid re-parsing blobs).    |
| `invtransform`     | TEXT    | Precomputed invtransform hint.                                      |
| `source_file`      | TEXT    | Original save-file path.                                            |
| `source_tab`       | INTEGER | Tab index the item came from (-1 when extracted from a character inventory). |
| `extracted_at`     | TEXT    | ISO-8601 timestamp.                                                 |
| `status`           | TEXT    | `available` (default) or `restored`.                                |

**Indexes** (defined at `item_db.py:64-67`):
- `idx_items_name` on `item_name`
- `idx_items_code` on `item_code`
- `idx_items_quality` on `quality`
- `idx_items_status` on `status`

## Section 5 tables (same `d2rr_archive_{mode}.db`)

Defined in `src/d2rr_toolkit/database/section5_db.py`. Both the
archive classes and the Section 5 classes open the same file per
mode and cooperate on the shared `meta` table.

### `section5_stacks`

Stackable items (gems, materials, runes) that D2R represents as a
`quantity` field rather than a slot per unit.

| Column                 | Type    | Description                                              |
|------------------------|---------|----------------------------------------------------------|
| `item_code`            | TEXT PK | Item code (e.g. `gcv` for Chipped Topaz).                |
| `total_count`          | INTEGER | Current stack size (0-99, per-item_code).                |
| `template_blob`        | BLOB    | Canonical stored blob to clone when rebuilding Section 5. |
| `quantity_bit_offset`  | INTEGER | Bit offset of the quantity field inside `template_blob`. |
| `quantity_bit_width`   | INTEGER | Width of that field (8 or 9, see `SIMPLE_QTY_WIDTH` / `EXTENDED_QTY_WIDTH` in writer). |
| `flags_simple`         | INTEGER | 0/1 - whether the item uses the simple-item layout.      |
| `first_seen_at`        | TEXT    | ISO-8601.                                                |
| `last_modified_at`     | TEXT    | ISO-8601.                                                |

### `gem_pool`

Singleton row holding the total pooled gem count. See
`section5_db.py:154-158`.

| Column             | Type    | Description                                     |
|--------------------|---------|-------------------------------------------------|
| `id`               | INTEGER | Always 1 (`CHECK (id = 1)`).                    |
| `total_count`      | INTEGER | Pool size across all gem types.                 |
| `last_modified_at` | TEXT    | ISO-8601.                                       |

### `gem_templates`

Template blobs for gem re-insertion (a rebuild consults these). See
`section5_db.py:160-168`.

| Column                 | Type    | Description                        |
|------------------------|---------|------------------------------------|
| `gem_code`             | TEXT PK | Gem item code.                     |
| `template_blob`        | BLOB    | Canonical gem blob.                |
| `quantity_bit_offset`  | INTEGER | Bit offset of the quantity field.  |
| `quantity_bit_width`   | INTEGER | Width of that field.               |
| `flags_simple`         | INTEGER | 0/1.                               |
| `first_seen_at`        | TEXT    | ISO-8601.                          |

## Migrations

Tracked as plain `ALTER TABLE` strings in `item_db.py:69-71`.

| Migration constant                        | Effect                                                                |
|-------------------------------------------|-----------------------------------------------------------------------|
| `_MIGRATION_ADD_SPRITE_KEY`               | Adds `sprite_key TEXT NOT NULL DEFAULT ''` to `items`.                |
| `_MIGRATION_ADD_INVTRANSFORM`             | Adds `invtransform TEXT NOT NULL DEFAULT ''` to `items`.              |
| `_MIGRATION_ADD_CHILD_COUNT`              | Adds `child_count INTEGER NOT NULL DEFAULT 0` to `items`.             |

Migrations are applied in `ItemDatabase.__init__` via `_migrate`.
A `PRAGMA table_info(items)` pre-check skips every column that
already exists, so re-running against an already-migrated DB is a
no-op. Any remaining `sqlite3.OperationalError` (disk full, lock
contention, read-only filesystem, corrupt DB) is **fail-loud**: it
is logged at `ERROR` level and re-raised out of `ItemDatabase(...)`.
Callers must be prepared to handle the exception - there is no
silent fallback.

`section5_db.py` currently has no migration constants (the schema
is v1).

### Migration history

| Date       | Migration                                   | Motivation                                                      |
|------------|---------------------------------------------|-----------------------------------------------------------------|
| 2026-04-07 | `_MIGRATION_ADD_SPRITE_KEY`                 | Pre-compute sprite keys so the GUI does not re-parse blobs.     |
| 2026-04-07 | `_MIGRATION_ADD_INVTRANSFORM`               | Pre-compute invtransform hint for tinted sprite rendering.      |
| 2026-04-07 | `_MIGRATION_ADD_CHILD_COUNT`                | Record number of socket children inside `source_data`.          |
| 2026-04-11 | `game_mode` meta-tag via `bind_database_mode` | SoftCore / HardCore isolation enforcement (no shared archive).  |
| 2026-04-21 | `_migrate` fail-loud on OperationalError    | Surface disk-full / lock / read-only errors instead of swallowing. |

## Operational notes

- **Location.** Default DB files live in the D2RR (Reimagined) save
  directory (see "Storage location" above). Windows heuristic:
  `%USERPROFILE%\Saved Games\Diablo II Resurrected\mods\ReimaginedThree\`.
  Override per invocation with the CLI's `--db` flag, or globally
  via the `D2RR_SAVE_DIR` environment variable. The base-game D2R
  save dir (`~\Saved Games\Diablo II Resurrected\` without the
  `mods\ReimaginedThree` subpath) is intentionally never used.
- **Why colocated with saves.** The archive is keyed to the user's
  characters and shared stashes. Putting the DB next to the saves
  means a standard backup of the Saved Games directory captures both
  the game state AND the toolkit's archive of items extracted from
  it - they never drift out of sync.
- **Save-file backup strategy.** The CLI calls
  `create_backup(save_path)` before every write (see
  `src/d2rr_toolkit/backup.py`). Save-file backups go to a *separate*
  central location at `~/.d2rr_toolkit/backups/<filename>/` so the
  save directory itself stays uncluttered. The SQLite DBs are NOT
  auto-backed-up - they are append-only and every `items` row retains
  `source_data` for full reconstruction.
- **Retention.** Save-file backups accumulate indefinitely; prune
  manually or call `cleanup_old_backups(keep_last=N)` from
  `d2rr_toolkit.backup`.
- **SC / HC cross-contamination.** Intentionally impossible -
  softcore and hardcore DBs are separate files AND carry a
  `game_mode` meta-tag that `open_item_db(mode)` /
  `open_section5_db(mode)` verify on every open.
  `DatabaseModeMismatchError` fires if someone manually swaps files.

## Integrity and atomicity

- SQLite is used with its default ACID guarantees; no WAL-mode
  tweaks.
- Writers use the file's connection cursor directly; no explicit
  transactions are opened beyond the implicit-per-statement
  autocommit. This is acceptable for the usage pattern (one row
  per archive op, no batch throughput).
- The archive-layer verify step (`_verify_d2i_on_disk`) is
  independent of SQLite - it operates on the post-write D2I bytes
  and rolls BOTH the file AND the DB insert back on any anomaly.

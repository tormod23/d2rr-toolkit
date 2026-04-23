# CLI Reference

> Generated: 2026-04-21 from `d2rr-toolkit --help`.
> Re-generate when commands change with (Windows users run under
> Git Bash, WSL, or PowerShell's `bash.exe` shim):
>
> ```bash
> d2rr-toolkit --help > cli_help.txt
> for c in parse dump-header inspect archive stash; do
>   d2rr-toolkit $c --help >> cli_help.txt
> done
> # then hand-transcribe cli_help.txt into this file.
> ```

## Synopsis

```
d2rr-toolkit [OPTIONS] COMMAND [ARGS]...
```

The Infinite Archive of Sanctuary - D2R Reimagined item parser.

### Global options

| Flag    | Description               |
|---------|---------------------------|
| `--help`| Show CLI help and exit.   |

## Commands

- [`parse`](#parse) - parse a `.d2s` save and list items.
- [`dump-header`](#dump-header) - raw header fields only.
- [`inspect`](#inspect) - full tooltip-style item display.
- [`archive`](#archive) - item archive (extract / restore / list /
  backups / rollback).
- [`stash`](#stash) - Section 5 gems / runes / materials DB.

---

## `parse`

```
d2rr-toolkit parse [OPTIONS] D2S_FILE
```

Parse a `.d2s` character save file and list all items.

**Arguments**

| Name       | Type | Required | Description                     |
|------------|------|----------|---------------------------------|
| `d2s_file` | PATH | yes      | Path to the `.d2s` save file.   |

**Options**

| Flag              | Description                |
|-------------------|----------------------------|
| `--verbose, -v`   | Show debug output.         |
| `--help`          | Show sub-command help.     |

**Examples**

```bash
d2rr-toolkit parse character.d2s
d2rr-toolkit parse character.d2s --verbose
```

---

## `dump-header`

```
d2rr-toolkit dump-header [OPTIONS] D2S_FILE
```

Dump raw header fields for verification purposes. Reads only the
fixed header fields without parsing items or stats. Useful for
quick inspection and verification-script output comparison.

**Arguments**

| Name       | Type | Required | Description                     |
|------------|------|----------|---------------------------------|
| `d2s_file` | PATH | yes      | Path to the `.d2s` save file.   |

**Example**

```bash
d2rr-toolkit dump-header character.d2s
```

---

## `inspect`

```
d2rr-toolkit inspect [OPTIONS] SAVE_FILE
```

Inspect items in detail - full tooltip-style display with properties
and set bonuses. Supports both `.d2s` (character) and `.d2i`
(shared-stash) files.

**Arguments**

| Name        | Type | Required | Description                          |
|-------------|------|----------|--------------------------------------|
| `save_file` | PATH | yes      | Path to `.d2s` or `.d2i` file.       |

**Options**

| Flag              | Description            |
|-------------------|------------------------|
| `--verbose, -v`   | Show debug output.     |
| `--help`          | Show sub-command help. |

**Examples**

```bash
d2rr-toolkit inspect character.d2s
d2rr-toolkit inspect ModernSharedStashSoftCoreV2.d2i
```

---

## `archive`

```
d2rr-toolkit archive [OPTIONS] COMMAND [ARGS]...
```

The Infinite Archive - extract, store, restore items. Sub-commands:

- [`extract`](#archive-extract)
- [`restore`](#archive-restore)
- [`list`](#archive-list)
- [`backups`](#archive-backups)
- [`rollback`](#archive-rollback)

### `archive extract`

```
d2rr-toolkit archive extract [OPTIONS] SAVE_FILE
```

Extract an item from a stash into the Infinite Archive. Creates a
backup of the save file before modification. The item is removed
from the stash and stored in the database. SoftCore and HardCore
archives are kept in physically separate files so a hardcore
character's items can never leak into the softcore pool.

**Options**

| Flag               | Type                 | Required | Description                                                               |
|--------------------|----------------------|----------|---------------------------------------------------------------------------|
| `--tab, -t`        | INTEGER              | yes      | Tab index (0-based).                                                      |
| `--item, -i`       | INTEGER              | yes      | Item index within tab (0-based).                                          |
| `--db`             | PATH                 |          | Override the mode-derived archive DB path.                                |
| `--mode, -m`       | softcore \| hardcore |          | Game mode; auto-detected from filename if omitted.                        |
| `--name`           | TEXT                 |          | Override the stored display name.                                         |

**Example**

```bash
d2rr-toolkit archive extract ModernSharedStashSoftCoreV2.d2i \
    --tab 0 --item 2
```

**Notes:** Refuses to archive unidentified items (`ArchiveError`
with "unidentified" in the message). Refuses to emit malformed
empty sections (writer `D2IWriterIntegrityError` -> rolled back
from backup).

### `archive restore`

```
d2rr-toolkit archive restore [OPTIONS] ITEM_ID SAVE_FILE
```

Restore an item from the Infinite Archive into a stash. Creates a
backup of the save file before modification. Game mode auto-detected
from the stash filename so a softcore item cannot be restored into
a hardcore stash.

**Arguments**

| Name        | Type    | Required | Description                       |
|-------------|---------|----------|-----------------------------------|
| `item_id`   | INTEGER | yes      | Database item ID.                 |
| `save_file` | PATH    | yes      | Path to `.d2i` stash file.        |

**Options**

| Flag           | Type                 | Default | Description                     |
|----------------|----------------------|---------|---------------------------------|
| `--tab, -t`    | INTEGER              | 0       | Tab index to insert into.       |
| `--db`         | PATH                 |         | Override DB path.               |
| `--mode, -m`   | softcore \| hardcore |         | Game mode override.             |

### `archive list`

```
d2rr-toolkit archive list [OPTIONS]
```

Browse or search the Infinite Archive. `--mode` defaults to
`softcore`; pass `--mode hardcore` to see the HC archive.

**Options**

| Flag              | Type                 | Default  | Description          |
|-------------------|----------------------|----------|----------------------|
| `--db`            | PATH                 |          | Override DB path.    |
| `--mode, -m`      | softcore \| hardcore | softcore | Game mode.           |
| `--search, -s`    | TEXT                 |          | Search by item name. |
| `--quality, -q`   | INTEGER              |          | Filter by quality.   |

### `archive backups`

```
d2rr-toolkit archive backups [OPTIONS] SAVE_FILE
```

List available backups for a save file. Backups live at
`~/.d2rr_toolkit/backups/<filename>/`.

### `archive rollback`

Restore a save file from a backup. (Full help via
`d2rr-toolkit archive rollback --help`.)

---

## `stash`

```
d2rr-toolkit stash [OPTIONS] COMMAND [ARGS]...
```

Section 5 DB - push gems / runes / materials into the archive, pull
them back out. Sub-commands:

### `stash status`

```
d2rr-toolkit stash status [OPTIONS]
```

Show the current Section 5 DB contents: stacks, gem pool, gem
templates. Defaults to `softcore`.

**Options**

| Flag         | Type                 | Default  | Description       |
|--------------|----------------------|----------|-------------------|
| `--db`       | PATH                 |          | Override DB path. |
| `--mode, -m` | softcore \| hardcore | softcore | Game mode.        |

### `stash seed`

Seed the Section 5 DB with the entire contents of a stash file's
Section 5.

### `stash convert`

Convert runes within the DB (pure arithmetic, no save-file
involvement).

---

## Exit codes

| Code | Meaning                                                           |
|------|-------------------------------------------------------------------|
| 0    | Success.                                                          |
| 1    | Known error (`ArchiveError`, `D2SWriteError`, mode mismatch, etc.). Message printed to stderr. |
| 2    | Typer usage error (unknown flag, missing argument).               |
| 130  | Interrupted by Ctrl-C / signal.                                   |

## Common error types

- `ArchiveError` - wraps any failure from the archive layer; the
  message names the cause. Unidentified-item refusal, writer
  integrity failure, tab/index out of range all surface here.
- `D2SWriteError` - writer invariant violation (wrong
  `quantity_bit_width`, missing `source_data`, carry1 conflict).
- `D2IWriterIntegrityError` - post-build self-check failed; the
  temp file was never renamed into place.
- `D2IOrphanExtrasError` - caller tried to empty a section whose
  raw tail holds unparsed item blobs.
- `GameDataNotLoadedError` - parser prerequisites missing; the
  CLI auto-loads so this should only fire in library use.


# D2RR Toolkit

_"Stay a while, and listen..."_

In these latter days, the **Reimagined** mod has stirred the bones of
Sanctuary - waking forgotten runes, rekindling lost weapon-craft, and
stitching new legends into the weave of the world. But every
re-shaping of Sanctuary carries peril. The scrolls that bind a hero's
soul to their deeds - the `.d2s` saves and the `.d2i` shared stash -
were never meant to hold these new truths, and one careless stroke of
the wrong tool can undo a champion's entire journey.

Consider this toolkit my Horadric satchel: a careful, bit-by-bit
scholar's workbench for the D2RR save format. It reads and re-writes
every last bit faithfully, so no relic is bent in the telling. It
keeps a sober archive of every found item and, as any wise Horadrim
would, holds the treasures of the living forever apart from those of
the fallen - no coin from the Hardcore side shall ever sully the
Softcore pool, and the reverse is equally forbidden. Before every
write it stamps a backup; should its own hand falter, it will roll
the scroll back before your eyes ever see the damage.

And where old Cain would unroll a dusty tome and whisper:
_"Ah yes, I have seen this before..."_, this toolkit reads the CASC
archives of the game itself - so every item, every stat, every set
bonus speaks its true name.

The night is long, and growing longer.

## Scope

A parser, writer, and archive toolkit for **D2R Reimagined** (D2RR)
save files - usable as a Python library **and** as a ready-made
`d2rr-toolkit` CLI.

> **Scope:** this toolkit targets the **Reimagined mod**
> ([Nexus page](https://www.nexusmods.com/diablo2resurrected/mods/503)),
> not the unmodded Diablo II: Resurrected base game. "D2R" refers to
> the base game; "D2RR" refers to D2R with Reimagined installed. The
> two are **not interchangeable** - Reimagined adds new items, stats,
> and mechanics, and the toolkit will mis-parse a plain D2R save.

## Features

- Parses and rewrites D2RR character (`.d2s`) and shared-stash
  (`.d2i`) save files at the bit level - no data loss on round-trip.
- Item archive with strict SoftCore / HardCore isolation (items from
  a hardcore character can never leak into the softcore pool).
- Section 5 (Gems / Materials / Runes) stash management with duplicate
  detection.
- Automatic timestamped backups before every write; D2I integrity
  self-check + auto-rollback on writer failure.
- Reads Reimagined game data directly from the local CASC archive
  (mod first, vanilla fallback); persistent per-user pickle cache
  for fast warm starts.
- Rich terminal display with in-game-accurate item colouring, set /
  runeword bonus rendering, and per-stat roll-range attribution.

## Requirements

- Python 3.14 or Higher
- A local installation of **Diablo II: Resurrected (D2R)** with the
  **Reimagined mod** installed on top - this is what "D2RR" means.
  The base D2R install typically lives at
  `C:\Program Files (x86)\Diablo II Resurrected\`; Reimagined sits
  underneath it at `.\mods\Reimagined\`. Paths are resolved by the
  toolkit at runtime (see [Environment variables](#environment-variables)).
- Read access to both the D2R CASC archive (base-game data) and the
  Reimagined mod directory (modded data files) - not shipped with
  this package.

## Install

The project uses [`uv`](https://docs.astral.sh/uv/) for
deterministic, lockfile-driven installs:

```bash
uv sync --all-extras
```

For a classic `pip` install without the lockfile:

```bash
pip install -e ".[dev]"
```

## Quickstart

```bash
# Parse a character save and print its item list
d2rr-toolkit parse path/to/Character.d2s

# Render the full inspectable view of one character
d2rr-toolkit inspect path/to/Character.d2s

# List every item currently stored in the archive database
d2rr-toolkit archive list

# Inspect a SharedStash file
d2rr-toolkit stash status path/to/SharedStash.d2i
```

## Environment variables

| Variable                         | Effect                                                                 |
|----------------------------------|------------------------------------------------------------------------|
| `D2RR_D2R_INSTALL`               | Overrides the **base-game D2R** install root (required on Linux / macOS). |
| `D2RR_MOD_DIR`                   | Overrides the **Reimagined mod** directory (defaults to `<D2R install>/mods/Reimagined`). |
| `D2RR_SAVE_DIR`                  | Overrides the **D2RR save directory** - where the Reimagined-modded game stores `.d2s` / `.d2i` files AND where the toolkit keeps its archive DB by default. Windows default: `%USERPROFILE%\Saved Games\Diablo II Resurrected\mods\ReimaginedThree\`. The toolkit never writes to the base-game D2R save dir. |
| `D2RR_DISABLE_GAME_DATA_CACHE=1` | Disables the persistent pickle cache globally (CI / debugging).        |

On Windows all three path vars have sensible defaults. On POSIX
they MUST be set (otherwise `init_game_paths()` / `resolve_save_dir()`
raise `ConfigurationError`).

## Running the tests

```bash
pytest
```

Known-flaky test suites (timing-dependent, pre-existing) can be
skipped explicitly:

```bash
pytest --ignore=tests/test_toolkit_logging_hygiene.py \
       --ignore=tests/test_game_data_cache.py
```

## Project layout

- `src/d2rr_toolkit/` - the full toolkit: parsers, writers, game-data
  loaders, display, archive orchestration, and the `d2rr-toolkit`
  Typer CLI (`d2rr_toolkit.cli`). Importable as `import d2rr_toolkit`.
- `docs/spec/d2s_format_spec.md` - binary format reference for `.d2s`
  and `.d2i`.
- `VERIFICATION_LOG.md` - running log of binary-verified assertions
  (each entry cross-references a test case or live save).
- `tests/cases/TCxx/` - fixtures for regression pins.

## Documentation

**Onboarding:**

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) - package layout, data flow, dependency rules.
- [`docs/CLI_REFERENCE.md`](docs/CLI_REFERENCE.md) - every command and option, with examples.
- [`docs/DB_SCHEMA.md`](docs/DB_SCHEMA.md) - archive + Section 5 SQLite schemas and migrations.

**Binary format + verification:**

- [`docs/spec/d2s_format_spec.md`](docs/spec/d2s_format_spec.md) - `.d2s` / `.d2i` binary format.
- [`VERIFICATION_LOG.md`](VERIFICATION_LOG.md) - per-field / per-stat verification history.

**External-GUI consumer contracts:**

- [`docs/GUI_STAT_BREAKDOWN_API.md`](docs/GUI_STAT_BREAKDOWN_API.md) - integration guide for the stat-breakdown resolver (covers per-stat breakdown, modifier-block summary, and known decomposition gaps).

## License

MIT - see `LICENSE`.

## Contributing

PRs welcome; all code, comments and commits must be in English. See
`CONTRIBUTING.md`.

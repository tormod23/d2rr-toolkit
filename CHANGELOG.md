# Changelog

All notable changes to D2RR Toolkit are recorded here.
This project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed (BREAKING)
- **Minimum Python version raised to 3.14** (was 3.10).
  3.10 reaches EOL in October 2026; 3.14 is the current stable line
  with PEP 649 deferred annotations, PEP 695 type aliases, PEP 758
  parenthesis-free `except`, native `StrEnum`, and `typing.Self` /
  `typing.override` in stdlib.

### Architecture
- **No lazy imports anywhere in the codebase.** All 159
  in-function imports promoted to module top-of-file. Two new
  pytest checks in
  [`tests/test_no_lazy_imports_or_cycles.py`](tests/test_no_lazy_imports_or_cycles.py)
  enforce the rule on every run.
- **Runtime import graph is now a DAG.** A previously-hidden
  ``affix_rolls -> property_formatter -> stat_breakdown ->
  affix_rolls`` cycle was broken in two steps:
  - New leaf module `game_data/_roll_types.py` hosts the shared
    `RollSource` / `StatRollRange` / `ItemRollContext` types so
    `affix_rolls` no longer imports back into `property_formatter`.
  - `PropertyFormatter.format_properties_grouped(breakdown=True)`
    now goes through a hook installed on `property_formatter` by
    `stat_breakdown` at its module-load time, so `property_formatter`
    no longer imports `stat_breakdown` directly.
  Public API (`format_properties_grouped(breakdown=True)`) is
  unchanged - callers just need `import d2rr_toolkit.game_data.stat_breakdown`
  somewhere in their entry path (the CLI does this transitively).
- `docs/ARCHITECTURE.md` § "Dependency rules" updated with the new
  invariants.

### Modernised
- `_CliMode` migrated from the `class X(str, Enum)` multi-inheritance
  pattern to native `enum.StrEnum` (PEP 663, 3.11).
- All 56 dataclasses now declare `slots=True` for ~30-50% smaller
  memory footprint and stricter attribute discipline.
- Manual `__slots__` classes (`D2ISectionInfo`, `_HuffmanNode`)
  converted to `@dataclass(slots=True)`.
- Context-manager `__enter__` methods in `ItemDatabase` /
  `Section5Database` now annotated with `typing.Self` (PEP 673).
- Custom `Exception` subclasses with overriding `__init__` decorated
  with `@typing.override` (PEP 698).
- Six existing `Literal[...]` aliases plus two newly-extracted
  aliases (`Gender`, `Ambiguity`) converted to PEP 695
  `type X = Y` syntax.
- `shutil.copy2` calls in `backup.py` replaced with
  `Path.copy(..., preserve_metadata=True)` (PEP 706, 3.14).
- 69 `from __future__ import annotations` imports removed; PEP 649
  deferred-evaluation handles forward references natively in 3.14.
- `parsers.d2s_parser` now uses `Exception.add_note()` (PEP 678) to
  attach the savefile path so the original exception type
  (`InvalidSignatureError`, `UnsupportedVersionError`, ...) is
  preserved instead of being wrapped in a generic `RuntimeError`.
- 7 `except (A, B):` handlers without `as` clauses converted to
  PEP 758 syntax (`except A, B:`).
- 3 dispatch chains (BLTE encoding byte, gem-mod special func codes)
  refactored to `match`/`case`.

### Fixed
- **mypy --strict on 83 source files now passes with 0 errors**
  (down from 155). Surfaced and fixed real runtime bugs along the
  way: `cli/_parse.py:dump_header` referenced an undefined `cs`
  (CharStats DB now loaded inline); `cli/_archive.py:archive_list`
  was missing `get_title_color` import; `cli/_archive.py:rollback`
  used a non-existent `BACKUP_DIR_NAME` constant (corrected to use
  `BACKUP_ROOT`); `cli/_stash.py` was missing its `logger`
  declaration; `game_data/properties.py:load_properties` referenced
  an unimported `SourceVersions` forward type;
  `cli/_inspect.py:_render_materials_tab` was annotated `-> None`
  but actually returned a list; the same file used a `tier`
  variable name shadowed across scopes; the same file dereferenced
  `item.extended` without a None-guard. mypy on the CI runner is
  no longer informational and now blocks merges.
- Removed 7 unused `# type: ignore` comments.
- Tightened generic types throughout: 49 bare `dict` / `list` /
  `tuple` / `re.Match` annotations now declare their inner types
  (e.g. `dict[str, Any]`, `re.Match[str]`).
- Added explicit annotations to 30 function signatures (database
  parameters now properly typed against `ItemTypeDatabase`,
  `ItemNamesDatabase`, `ItemStatCostDatabase`, etc.).

### Tooling
- `pyproject.toml`: `requires-python = ">=3.14"`,
  `[tool.ruff] target-version = "py314"`,
  `[tool.mypy] python_version = "3.14"`,
  `pydantic >= 2.10` (was `>= 2.0`).
- `.pre-commit-config.yaml`: ruff hook bumped from `v0.5.0`
  to `v0.15.12`.
- `uv.lock` regenerated; transitive `exceptiongroup` and `tomli`
  dependencies dropped (both are stdlib in 3.11+ / 3.14).
- New `.github/workflows/ci.yml` (was previously absent): pytest +
  ruff + import-linter + interrogate matrix on
  ubuntu-latest / windows-latest / Python 3.14, plus a strict mypy
  job that blocks merges on type errors.

### Security
- Harden `CASCReader._resolve_mod_path` against path-traversal
  (CWE-22). User-supplied CASC paths are now normalised and rejected
  silently when they escape `mod_dir` via `..` segments, absolute
  paths, drive letters, or URL-like schemes.

### Added
- HMAC-signed pickle cache for game data (CWE-502 mitigation).
- `ParsedItem.is_identified` public accessor for the GUI consumer
  contract.
- Archive refusal of unidentified items (`extract_from_d2i` raises
  `ArchiveError` before DB insert).
- D2I writer post-build integrity self-check and archive-path
  auto-rollback (file rolled back from backup on any malformation).
- Parser fail-loud guard + auto-load of required game-data
  singletons (`GameDataNotLoadedError`).
- Rare-MISC 7-slot QSD retry now fires on exception path too, not
  only on "unknown stat_id" flag.
- `LICENSE` (MIT), `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`,
  `SECURITY.md` at repo root.
- `uv.lock` lockfile; CI pipeline (ruff + mypy + pytest on Python
  3.10 / 3.11 / 3.12).
- Completeness health-check warning when parsed items don't cover
  the full D2I section payload.

### Documentation
- README `## Install` section now documents the canonical `uv sync
  --all-extras` path alongside the legacy `pip install -e ".[dev]"`
  fallback, matching CI and CONTRIBUTING.
- `docs/DB_SCHEMA.md` now carries a migration-history table with
  landing dates + motivation for every `ALTER TABLE` constant and
  the mode-isolation meta-tag.

### Changed
- **BREAKING:** Archive database default location moved from the
  current working directory to the D2RR (Reimagined) save directory
  (so a `mods/ReimaginedThree` backup captures the archive alongside
  the characters and shared stash). Resolution order:
  `D2RR_SAVE_DIR` env var -> Windows heuristic
  `%USERPROFILE%\Saved Games\Diablo II Resurrected\mods\ReimaginedThree\`
  -> `ConfigurationError` (no silent fallback to `~/.d2rr_toolkit/`,
  CWD, or the base-game D2R save dir). Users who relied on the old
  CWD default must now pass `--db` explicitly or set
  `D2RR_SAVE_DIR`. `DB_SCHEMA.md` rewritten to reflect the correct
  storage layout (one file per mode, shared between the archive and
  Section 5 tables).
- `_parse_single_item` decomposed into 9 focused helpers (`_read_item_flags`, `_read_item_code`, `_read_extended_header`, `_read_gfx_and_class`, `_read_automod_dispatch`, `_read_bridge_fields`, `_parse_type_specific_with_retry`, `_read_runeword_property_list`, `_assemble_parsed_item`, `_clamp_to_section_end`); no behaviour change, all snapshots + round-trips byte-identical.
- game_data loaders: defensive `except Exception: # pragma: no cover`
  blankets replaced by targeted handlers with `logger.warning`
  context. Affected: `property_formatter.py` (6 sites),
  `stat_breakdown.py` (4 sites), `skills.py` (2 sites). Narrowed to
  `ImportError` for lazy imports and `(OSError, ValueError, KeyError,
  TypeError, AttributeError)` subsets for data lookups so real bugs
  stop getting swallowed.
- Parser `assert self._reader is not None` narrowing replaced with
  a new `_require_reader()` helper that raises `RuntimeError` with
  a message you can act on. Survives `python -O` (asserts are stripped
  there); 31 sites touched across header / items / merc / stats
  mixins. Mirrors the writer-side fix landed earlier.
- CLI refactor: extracted the material-item one-liner branch of
  `_render_item_panel` into a new `_render_material_panel` helper.
  No behaviour change.
- Parser refactor: extracted the simple-item body of
  `D2SParser._parse_single_item` into a new `_parse_simple_item_body`
  helper. No behaviour change -- 62/62 snapshot + round-trip fixtures
  byte-identical.
- Writer `assert` statements replaced with explicit
  `D2SWriteError` raises (survives `python -O`).
- Func-only property codes (`dmg%`, `dmg-min`, `dmg-max`,
  `indestruct`, `ethereal`) in set bonuses now route through the
  canonical ISC template machinery instead of falling back to raw
  codes.
- Build: adopted `uv` as the lockfile-driven install path.
- Pillow declared as a runtime dependency.
- Quality-specific-data reader replaced the if/elif ladder with
  a dispatch table.

### Removed
- GUI subsystem - the project is now CLI-only (2026-04-11).
- Stale `construct` and `sqlalchemy` references from
  `requires.txt` (egg-info regenerated from current `pyproject.toml`).
- `ItemNamesDatabase.load_directory` and `PropertyFormatter.load`
  backward-compat disk-reading fallbacks. Both violated the CASC-
  boundary rule (`docs/ARCHITECTURE.md` §"Dependency rules") and had no in-tree callers after
  the 2026-04-14 Iron-Rule migration. Callers must now hand raw bytes
  to `load_json_bytes` / `load_from_bytes` via the CASC reader.
- Graveyard comment block in `config.py` documenting the 2026-04-14
  removal of `prepare_excel_base()`. The function is already gone;
  the comment memo was a drift risk -- git log is the canonical
  record.

### Fixed
- `D2IParser.parse` no longer produces a phantom 7th tab when the
  trailing metadata section (spec section 6, 148 bytes of
  game-internal timestamps / session IDs) coincidentally contains
  the byte pair `0x4A 0x4D` ("JM"). Section enumeration now walks
  the file by `0xAA55AA55` section signatures - the same algorithm
  `D2IWriter._find_sections` uses - and terminates cleanly at the
  trailing block. File bytes on disk are unchanged (the writer
  already preserved the trailer verbatim); the fix removes a UX
  trap where CLI `archive extract --tab 6 ...` could pull
  noise-parsed "items" into the archive DB, and eliminates the
  `Ignoring unknown d2i tab index 6 (N items)` message downstream
  consumers had to filter. New regression suite
  `tests/test_d2i_parser_no_phantom_tabs.py` pins the behaviour
  against a synthetic fixture whose trailing block embeds a
  literal "JM" byte pair.
- `import-linter` now enforces the 5 import-layering rules from
  `docs/ARCHITECTURE.md` §"Dependency rules" in CI. Catches
  boundary violations automatically instead of via code
  review. Configuration in `[tool.importlinter]` of pyproject.toml;
  `uv run lint-imports` to run locally.
- `ItemDatabase` and `Section5Database` are now context managers
  (support `with ItemDatabase(...) as db:`). Existing CLI sites
  already use `try / finally: db.close()` which is functionally
  equivalent; rewriting them to `with` is left as cosmetic
  follow-up.
- Game-path configuration is now OS-aware and honours
  `D2RR_D2R_INSTALL` / `D2RR_MOD_DIR` environment variables on
  every platform. On POSIX with no env var + no explicit argument,
  `init_game_paths()` now raises a new
  `d2rr_toolkit.exceptions.ConfigurationError` instead of silently
  returning a `GamePaths` pointing at a non-existent
  `C:\Program Files (x86)\...` path. Windows behaviour is unchanged
  when no env vars are set.
- Cache tmp-file cleanup now runs in `try/finally` for both
  `_try_write_cache` and `_get_or_create_cache_key`. Inner
  unlink failures are logged at DEBUG with the tmp filename so a
  leaked `.pid.uuid.tmp` file in the cache dir is diagnosable
  (CWE-459).
- `ItemDatabase._migrate` no longer swallows schema-migration
  errors. Any `sqlite3.OperationalError` that survives the
  "column already exists" pre-check is now logged at ERROR and
  re-raised, so silent DB-inconsistency (disk-full, lock
  contention, read-only FS) stops producing INSERT-time blowups
  with no operator-visible cause.
- Rare-MISC 7-slot QSD retry path now validates its outcome
  post-retry: section-boundary overshoot and buffer-past-end now
  raise `SpecVerificationError` instead of silently returning a
  malformed `ParsedItem`. Prevents cascading corruption of every
  item following a bad retry in the same section.
- D2I empty-tab corruption that rendered the SharedStash unloadable
  after a chain of archive operations (phantom 0x00 trailing byte
  produced a 69-byte "empty" section; D2R refused to load the
  directory while that file was present).
- Charm affix carry-bit misidentification on `has_gfx=1` items
  (VikingBarbie Coral charm -> previously reported as Amber).
- Phase Blade parse (variable-width durability block; Phase Blade
  is the only weapon with `durability=0` in Reimagined 3.0.7).
- Orphan-extras detection in the D2I splice: previously checked
  only for `JM` prefix, now rejects any non-zero tail byte.
- CLI `stash status` silent `except Exception: pass` now logs a
  WARNING + user-visible notice.

## [0.1.0-dev] - unreleased

First pre-release. Parsing and archiving of D2R Reimagined save
files; no public version has been cut yet.

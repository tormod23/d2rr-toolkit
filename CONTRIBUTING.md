# Contributing to D2RR Toolkit

Thanks for your interest. This project parses binary save-file formats
of a specific Diablo II Resurrected mod; a wrong assumption in the
parser can silently corrupt a user's save. Please read the conventions
below before opening a PR.

## Language

All source code, comments, docstrings, commit messages, and
documentation must be in **English**. Direct quotes of user
communication preserved for context are the only exception - and even
those should be paraphrased or translated in-line.

## Development environment

```bash
# Create a fresh venv (Python 3.14)
python -m venv .venv
source .venv/bin/activate        # or .venv\Scripts\activate on Windows

# Install with dev extras
uv sync --all-extras             # preferred - uses uv.lock
pip install -e ".[dev]"          # classic pip fallback
```

After editing `pyproject.toml` dependencies, regenerate the egg-info
and lockfile:

```bash
rm -rf src/d2rr_toolkit.egg-info
pip install -e .
uv lock
```

## Quality gates

Before pushing:

```bash
ruff check .
mypy src/
lint-imports                       # architectural import layers
pytest -m "not needs_game_data"    # CI-friendly subset
pytest                             # full local run
```

CI enforces the first four on every PR. Tests marked
`@pytest.mark.needs_game_data` require a local D2R + Reimagined install
and are skipped in CI.

> **Dev-dep note:** `interrogate` pulls the deprecated `py` 1.11.0 as
> a transitive dependency. Known upstream issue; `py` has no active
> CVEs and is dev-only (never imported by runtime code). Revisit if
> `py` ever becomes un-installable on supported Python versions.

## Binary parsing discipline

The project parses tightly packed binary save files where one wrong
bit assumption silently corrupts every byte that follows. The rules
below are non-negotiable and exist to prevent that class of bug.

### Verification tags

Every non-trivial binary-format claim in parser / writer code MUST
carry one of these tags in a comment on the same or adjacent line:

| Tag | Meaning |
|---|---|
| `[BV]` / `[BINARY_VERIFIED]` | Confirmed against real `.d2s` / `.d2i` files in `tests/cases/`. Safe for production parser / writer code. |
| `[BV TC##]` | Confirmed against the specific test case `TC##` fixture. |
| `[TC##]` | Exercised by the named test case (tighter than `[SPEC_ONLY]`, less formal than `[BV]`). |
| `[SPEC_ONLY]` | Sourced from the public D2S format spec but not yet binary-verified against a real file. **Treat with caution.** Never the final form - must be upgraded to `[BV]` before a release. |
| `[UNKNOWN]` | Not in the spec, not yet researched. Region MUST be preserved (read into a named field, never silently skipped). |

Every new parser claim must carry one of the first three tags AND land
a matching fixture in `tests/cases/TC##/` + an entry in
[`VERIFICATION_LOG.md`](VERIFICATION_LOG.md). See
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#verification-tag-system)
for the full contract.

### Non-negotiables

- **Never guess** a binary offset, field width, or encoding. If you
  don't have a `[BV]` / `[BV TC##]` tag, the answer is "ask first" or
  "write a verification script first" - not "assume".
- **Never treat prior knowledge of D2 / D2R formats as authoritative.**
  This project targets D2R + the Reimagined mod. Field widths and
  encodings diverge from both classic Diablo II and vanilla D2R.
- **Every `BitReader.read(n)` call** whose width or semantic meaning
  is not obvious from the surrounding spec must reference its
  verification status in a comment.
- **Never silently skip unknown regions.** Read them into a named
  field so the writer can round-trip them verbatim.
- **Never write code that modifies a save file** before the relevant
  read-only parsing is fully `[BV]`-verified.

### Workflow for a new field

1. Check [`VERIFICATION_LOG.md`](VERIFICATION_LOG.md) - is the field
   already verified?
2. If not: add a standalone verification script in
   `tests/verification/` that reads the field from a real save and
   prints a human-readable diagnostic.
3. Run the script against a real `.d2s` / `.d2i` (or a TC fixture) and
   record the result in `VERIFICATION_LOG.md` - byte offset, hex
   value, interpretation, test-file reference, date.
4. Upgrade the field's tag from `[SPEC_ONLY]` to `[BV]` / `[BV TC##]`
   in the source.
5. **Only then** write the production parser / writer code that
   depends on the field.

## Writer safety

Any change under `src/d2rr_toolkit/writers/` must preserve the
backup-before-write invariant:

1. `create_backup(path)` is called before the write.
2. The writer's post-build integrity check runs before the temp file
   is renamed into place.
3. The `archive.py` verify-on-disk step with auto-rollback is never
   bypassed.

## Import conventions

Every Python module lives under the single `d2rr_toolkit` package.
Library surface (parsers, writers, game data, models, display, ...) plus
the Typer CLI (`d2rr_toolkit.cli`) and archive orchestrator
(`d2rr_toolkit.archive`) all share one namespace. Always import from
`d2rr_toolkit.*`.

The architectural dependency rules are machine-enforced by
`import-linter` on every CI build (`uv run lint-imports` to run
locally). See
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#dependency-rules) for
the full rule set.

## Pull requests

- One logical change per PR.
- Commit messages in imperative mood: "Add merc items", not
  "Added merc items".
- Include a `Test plan` section in the PR description with bulleted
  TODOs.
- Do not change the public CLI surface without updating
  [`docs/CLI_REFERENCE.md`](docs/CLI_REFERENCE.md).
- Link any related entries in `VERIFICATION_LOG.md` or `CHANGELOG.md`.

## Pre-commit hooks

Install once per clone:

```bash
pip install pre-commit
pre-commit install
```

From then on `git commit` runs ruff + file-hygiene checks (trailing
whitespace, EOL, large-file guard) before accepting the commit. mypy
is intentionally left off the pre-commit chain because it's slow on a
cold cache; CI runs it on every push. Uncomment the `mirrors-mypy`
block in `.pre-commit-config.yaml` to enable it locally.

`.editorconfig` sets LF line endings + UTF-8 + 4-space indent so
editors stay consistent across OSes.

## Reporting issues

Use GitHub issues for bugs and feature requests. For security issues,
see [`SECURITY.md`](SECURITY.md) - report privately first.

See also [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) for community
standards and enforcement.

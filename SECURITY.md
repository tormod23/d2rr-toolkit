# Security Policy

## Supported versions

The project is pre-1.0 and no long-term supported branch exists yet.
Fixes land on `main`.

## Reporting a vulnerability

Please report security issues privately by opening a **private**
security advisory on the project's GitHub repository
(Security -> Report a vulnerability), or by emailing the maintainer
directly. Do **not** file a public issue for security-relevant
defects.

We will acknowledge the report within 7 days and aim to ship a fix
within 30 days of confirmation.

## Scope

In scope:

- The code in `src/d2rr_toolkit/` and `src/d2rr_toolkit/`.
- The CLI entry point `d2rr-toolkit`.
- Save-file read/write correctness (data-integrity bugs that could
  corrupt a user's `.d2s` / `.d2i` save).
- The game-data pickle cache (default:
  `~/.cache/d2rr-toolkit/data_cache/` on Linux; platformdirs
  default on other OSes).
- The archive SQLite databases co-located with D2RR (Reimagined)
  save files in the mod's save directory (SC and HC isolation
  invariants). Default location is resolved via
  `d2rr_toolkit.config.resolve_save_dir()`; see `docs/DB_SCHEMA.md`
  for the full lookup order. The toolkit never writes to the
  base-game D2R save directory.

Out of scope:

- Vulnerabilities that require write access to the user's home
  directory (on a single-user desktop, an attacker at that level
  already controls the process).
- The external GUI consumer (separate project / repository).
- Diablo II Resurrected itself and Blizzard's CASC archive - we
  read those but cannot patch them.

## Threat model highlights

- **CWE-502 (Deserialisation of Untrusted Data):** the game-data
  pickle cache is HMAC-signed with a per-user key
  (`<cache_dir>/cache.key`, 32 random bytes, `0o600` on POSIX).
  `pickle.loads` is only reached after
  `hmac.compare_digest` on the stored MAC succeeds.
- **CWE-367 (TOCTOU):** the backup directory creation path
  rejects symlinks and foreign-owned paths on POSIX before writing.
- **CWE-390 (Stripped preconditions):** writer invariants are
  expressed as explicit `raise D2SWriteError(...)` statements so
  they survive `python -O`.

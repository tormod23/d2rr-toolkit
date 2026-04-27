"""Persistent pickle cache for parsed game-data tables.

Every ``load_*()`` in :mod:`d2rr_toolkit.game_data` follows the same
shape: read a TSV / JSON source through the Iron Rule, construct
~hundreds of small dataclass instances, index them in a
module-level singleton.  On a typical install this parses ~15 files
and costs 1-2 seconds of cold startup; the cache replaces that with
a ~270 ms pickle load for a 5* warm-launch speedup.

This module supplies the **one** helper every loader delegates to.
A cache hit deserialises a pickled snapshot of the populated
singleton and restores it in place; a miss runs the legacy parse
and writes a fresh snapshot for next time.

Reader-facing documentation
---------------------------

* End-to-end reference, benchmark table, and full invalidation
  contract: see ``src/d2rr_toolkit/GAME_DATA_CACHE.md`` at the
  toolkit root.
* Loader-facing API: :func:`cached_load`.
* Invalidation oracle: :mod:`d2rr_toolkit.meta.source_versions`.

The rest of this docstring is the **implementation** reference -
file layout, concurrency discipline, and the helper internals -
for maintainers extending the cache or auditing a race.

## Cache layout

```
<user_cache_dir>/d2rr-toolkit/data_cache/
    item_stat_cost.pkl
    item_types.pkl
    skills.pkl
    ...
```

``<user_cache_dir>`` resolves to :func:`platformdirs.user_cache_dir`
when available, else a ``~/.cache/d2rr-toolkit`` fallback that
keeps the library runnable without the optional dependency.  Tests
override the location via the ``cache_dir=`` kwarg on every loader.

## File format

Each ``*.pkl`` stores a 4-tuple::

    (CACHE_FORMAT_VERSION, schema_version, source_versions, payload)

where:

* ``CACHE_FORMAT_VERSION`` is bumped only when this module's
  wrapper layout changes (e.g. we switch to msgpack, add an
  HMAC, ...).  Per-loader schema changes do NOT touch it.
* ``schema_version`` is a per-loader integer bumped in the same
  commit that changes a dataclass field.  A regression test in
  ``tests/test_game_data_cache.py`` walks every loader's
  ``dataclasses.fields()`` and fails the suite if a structural
  change happened without a matching bump - see §"Schema
  invariant" there.
* ``source_versions`` is the :class:`SourceVersions` frozen pair
  captured at write time.  The contract: a cache hit fires iff
  the on-disk tuple's ``source_versions`` is structurally equal
  to the caller's current :class:`SourceVersions`.
* ``payload`` is the populated singleton instance itself.  Pickle
  natively supports the toolkit's dataclass + plain-class DB
  shapes, so there's no custom serialiser.

## Invalidation contract

```
Cache hit  <=>  (on-disk cache_format == CACHE_FORMAT_VERSION
                AND on-disk schema == caller's schema_version
                AND on-disk source_versions == caller's SourceVersions)
```

A mismatch in any dimension silently falls through to a fresh
parse - corruption, schema drift, or a game/mod update are all
handled uniformly and transparently.  The loader never surfaces a
cache error to its caller: the worst case is a one-off cold parse
identical to today's baseline.

## Concurrency

Cache files are written via write-to-``.tmp`` + ``os.replace``,
which is atomic on both POSIX and Windows (PEP 428, Python 3.3+).
Two concurrent loaders can race freely: both may write, the second
atomic replace wins, and because both wrote identical bytes, any
reader sees either the pre-write state or the correct post-write
state - never a torn file.

Readers open, read into memory, then close the file before calling
:func:`pickle.loads`, so a concurrent ``os.replace`` can never
invalidate a file handle mid-deserialise.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import pickle
import secrets
import threading
import uuid
from pathlib import Path
from typing import Callable

from d2rr_toolkit.meta.source_versions import (
    SourceVersions,
    SourceVersionsError,
    get_source_versions,
)

logger = logging.getLogger(__name__)

# Wrapper-format marker. Only bump when the OUTER tuple layout changes
# (e.g. adding a header, switching serialiser, HMAC). Per-loader
# dataclass changes use the per-loader ``schema_version`` instead.
#
# Bumped from 1 -> 2 in the HMAC-signed-cache change: version 1 caches
# are raw pickle blobs and fail the magic-prefix check on read, so
# they get silently rebuilt with the new signed layout.
CACHE_FORMAT_VERSION: int = 2

# ── HMAC-signed cache layout ────────────────────────────────────────────────
# Every cache file is now:
#
#   MAGIC (5 bytes)  |  HMAC-SHA256(payload) (32 bytes)  |  pickled payload
#
# The reader refuses to call pickle.loads unless
# hmac.compare_digest(stored_mac, computed_mac) succeeds - this closes
# CWE-502 (deserialisation of untrusted data) against any attacker who
# can write to the user's cache dir but not to the machine-local
# key file.
#
# The key lives at <cache_dir>/cache.key (32 random bytes, 0o600 on
# POSIX). First use generates it; subsequent runs load it. Losing the
# key forces a one-off cache rebuild - acceptable since every cache
# entry can be regenerated from the on-disk game files.
_MAGIC = b"D2RR\x02"
_HMAC_SIZE = hashlib.sha256().digest_size  # 32 bytes
_HEADER_SIZE = len(_MAGIC) + _HMAC_SIZE


def _get_or_create_cache_key(cache_dir: Path) -> bytes:
    """Load the machine-local HMAC key, generating it on first use.

    The key is written atomically via a tmp-file + rename so a
    concurrent loader never sees a half-written key. On POSIX the
    permissions are locked down to 0o600; Windows relies on the
    user's home-directory ACLs (os.chmod is a no-op for permission
    bits on Windows).
    """
    key_path = cache_dir / "cache.key"
    try:
        return key_path.read_bytes()
    except FileNotFoundError:
        pass
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    tmp = key_path.with_suffix(f".key.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        try:
            tmp.write_bytes(key)
            if os.name != "nt":
                os.chmod(tmp, 0o600)
            os.replace(tmp, key_path)
        except OSError as e:
            logger.warning("cannot persist cache key at %s: %s", key_path, e)
            # Fall back to the in-memory key so this process still
            # benefits from signing; next process will retry the
            # persistence.
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError as unlink_err:
            logger.debug(
                "cache-key tmp cleanup failed for %s: %s",
                tmp.name,
                unlink_err,
            )
    # A concurrent writer may have raced us - prefer whatever landed
    # on disk so every process in the machine agrees on one key.
    try:
        return key_path.read_bytes()
    except OSError:
        return key


# Env-var kill switch honoured by every cached_load call. CI uses it to
# run against fresh parses without threading ``use_cache=False`` through
# every test fixture.
_ENV_DISABLE = "D2RR_DISABLE_GAME_DATA_CACHE"

# Default cache directory (lazy-resolved on first use so tests that
# override via ``cache_dir=`` never trigger the platformdirs import).
_default_cache_dir: Path | None = None

# Guards the default source-versions resolution so repeated cold loaders
# don't each re-read .build.info / modinfo.json. Opt-in callers that
# pass source_versions= explicitly bypass this entirely.
_default_versions_lock = threading.Lock()
_default_versions_cache: tuple[Path | None, Path | None, SourceVersions] | None = None


# ── Public API ──────────────────────────────────────────────────────────────


def cached_load(
    *,
    name: str,
    schema_version: int,
    singleton: object,
    build: Callable[[], None],
    use_cache: bool = True,
    source_versions: SourceVersions | None = None,
    cache_dir: Path | None = None,
) -> None:
    """Run ``build`` with a transparent on-disk cache.

    Args:
        name: Stable loader identifier.  Used verbatim as the
            filename stem (``{name}.pkl``).  Must not change once a
            loader ships - renaming orphans existing cache files,
            which is harmless but wastes a warm-up.
        schema_version: Integer bumped whenever the singleton's
            in-memory shape changes (new / renamed / removed
            dataclass field).  Mismatches trigger a silent rebuild.
        singleton: The module-level DB instance ``build`` populates.
            On cache hit its ``__dict__`` is replaced in-place with
            the pickled snapshot so pre-existing module-level
            references stay valid.
        build: The loader's legacy parse path.  Called exactly once
            on cache miss or when caching is disabled.  Return value
            is ignored - the helper pickles ``singleton``, not the
            return of ``build``.
        use_cache: ``False`` short-circuits to ``build()`` without
            touching disk.  Default ``True``.  Also honoured via the
            ``D2RR_DISABLE_GAME_DATA_CACHE=1`` environment variable.
        source_versions: Optional explicit version pair.  When
            ``None`` the helper resolves it from the current
            :class:`GamePaths` via :func:`get_source_versions` - a
            process-wide lazy cache keeps the cost at two small
            file reads for a whole batch of cold loaders.  Passing
            the same instance into every loader is still the
            recommended pattern; it eliminates the lock contention
            and makes the invalidation key explicit at the call
            site.
        cache_dir: Optional override for the cache root.  Tests use
            a ``tmp_path`` fixture.  Production callers should rely
            on the platformdirs default.

    Returns:
        ``None`` - mirrors the legacy loader signature exactly.  The
        populated singleton is the side effect callers already
        expect.
    """
    if not use_cache or os.environ.get(_ENV_DISABLE) == "1":
        build()
        return

    versions = source_versions or _resolve_default_versions()
    if versions is None:
        # Game paths misconfigured / SourceVersionsError caught.
        # Proceed with a normal parse and skip caching entirely -
        # we refuse to pollute the cache with a "don't know" key.
        build()
        return

    cache_file = _resolve_cache_dir(cache_dir) / f"{name}.pkl"

    if _try_load_from_cache(cache_file, schema_version, versions, singleton):
        logger.debug(
            "game_data cache hit: %s (%s)",
            name,
            versions.cache_key(),
        )
        return

    build()

    _try_write_cache(cache_file, schema_version, versions, singleton)


# ── Internal helpers ─────────────────────────────────────────────────────────


def _try_load_from_cache(
    path: Path,
    schema_version: int,
    versions: SourceVersions,
    singleton: object,
) -> bool:
    """Return ``True`` on a successful cache hit + restore.

    Any failure (missing file, corrupt pickle, schema drift,
    version mismatch) returns ``False`` silently - the caller falls
    through to a fresh parse.  We never raise from this path.
    """
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return False
    except OSError as e:
        logger.debug("cache read failed for %s: %s", path.name, e)
        return False

    # ── HMAC verification ────────────────────────────────────────────────
    # Refuse pickle.loads unless a local HMAC-SHA256 MAC on the payload
    # matches. This is the CWE-502 mitigation - any attacker who can
    # write to the cache dir but cannot forge the HMAC (because the key
    # file is 0o600) cannot trigger arbitrary code execution through
    # a crafted pickle.
    if len(raw) < _HEADER_SIZE or raw[: len(_MAGIC)] != _MAGIC:
        logger.debug(
            "cache %s is missing the signed-format magic prefix - "
            "rebuilding (pre-v2 caches look this way)",
            path.name,
        )
        return False
    stored_mac = raw[len(_MAGIC) : _HEADER_SIZE]
    payload_bytes = raw[_HEADER_SIZE:]
    try:
        key = _get_or_create_cache_key(path.parent)
    except OSError as e:  # pragma: no cover - defensive
        logger.debug("cannot resolve cache key for %s: %s", path.name, e)
        return False
    expected_mac = hmac.new(key, payload_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(stored_mac, expected_mac):
        logger.debug(
            "cache %s HMAC mismatch - rebuilding (tampered file or rotated key)",
            path.name,
        )
        return False

    try:
        unpacked = pickle.loads(payload_bytes)
    except Exception as e:  # noqa: BLE001 - pickle can raise anything
        logger.debug("cache unpickle failed for %s: %s", path.name, e)
        return False

    if not (isinstance(unpacked, tuple) and len(unpacked) == 4):
        logger.debug("cache shape mismatch for %s", path.name)
        return False

    fmt, stored_schema, stored_versions, payload = unpacked
    if fmt != CACHE_FORMAT_VERSION:
        logger.debug(
            "cache format %s != %s for %s - rebuilding",
            fmt,
            CACHE_FORMAT_VERSION,
            path.name,
        )
        return False
    if stored_schema != schema_version:
        logger.debug(
            "cache schema %s != %s for %s - rebuilding",
            stored_schema,
            schema_version,
            path.name,
        )
        return False
    if not isinstance(stored_versions, SourceVersions):
        logger.debug("cache version type mismatch for %s", path.name)
        return False
    if stored_versions != versions:
        logger.debug(
            "cache version mismatch for %s: stored %s, current %s",
            path.name,
            stored_versions.cache_key(),
            versions.cache_key(),
        )
        return False

    if not isinstance(payload, type(singleton)):
        logger.debug(
            "cache payload type %s is not %s for %s",
            type(payload).__name__,
            type(singleton).__name__,
            path.name,
        )
        return False

    _restore_singleton_state(singleton, payload)
    return True


def _restore_singleton_state(singleton: object, payload: object) -> None:
    """Replace ``singleton``'s state with ``payload``'s state in place.

    Module-level references to the singleton stay valid - we
    deliberately mutate the existing instance rather than swapping
    the module attribute.  Uses ``__dict__`` because every DB in
    the toolkit is a plain Python class (``__slots__`` would need a
    different path, but no current loader uses them).
    """
    try:
        state = vars(payload)
    except TypeError:
        # Slotted dataclass - reconstruct via state/replace protocol.
        logger.debug(
            "singleton %s has no __dict__; skipping in-place restore",
            type(singleton).__name__,
        )
        raise
    vars(singleton).clear()
    vars(singleton).update(state)


def _try_write_cache(
    path: Path,
    schema_version: int,
    versions: SourceVersions,
    singleton: object,
) -> None:
    """Atomic write.  Any failure is logged at WARNING and swallowed.

    A cache-write failure must never break the loader - the parse
    already succeeded; we just lose the speedup for next time.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.warning("cannot create cache dir %s: %s", path.parent, e)
        return

    payload = (CACHE_FORMAT_VERSION, schema_version, versions, singleton)
    try:
        payload_bytes = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as e:  # noqa: BLE001
        logger.warning("cannot pickle %s: %s", path.name, e)
        return

    # Sign the payload with the machine-local key. The reader will
    # refuse to unpickle any file whose prefix/MAC doesn't line up.
    try:
        key = _get_or_create_cache_key(path.parent)
    except OSError as e:  # pragma: no cover - defensive
        logger.warning("cannot resolve cache key for %s: %s", path.name, e)
        return
    mac = hmac.new(key, payload_bytes, hashlib.sha256).digest()
    blob = _MAGIC + mac + payload_bytes

    # Per-caller unique tmp suffix so two threads racing on the same
    # cache name don't step on each other's intermediate file.  Both
    # ``os.replace`` calls target the same final path; whichever lands
    # second wins, and because both wrote byte-identical payloads the
    # result is correct regardless of ordering.
    tmp = path.with_suffix(f"{path.suffix}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        try:
            tmp.write_bytes(blob)
            os.replace(tmp, path)
        except OSError as e:
            logger.warning("cannot write cache %s: %s", path.name, e)
    finally:
        # If os.replace succeeded, tmp is already gone -- missing_ok
        # covers that. Otherwise we unlink any partial file so it does
        # not leak into the cache dir. Log at DEBUG if the unlink
        # itself fails: rare, but diagnosable without adding noise in
        # the steady state.
        try:
            tmp.unlink(missing_ok=True)
        except OSError as unlink_err:
            logger.debug(
                "cache tmp-cleanup failed for %s: %s",
                tmp.name,
                unlink_err,
            )


# ── Cache dir resolution ─────────────────────────────────────────────────────


def _resolve_cache_dir(override: Path | None) -> Path:
    """Resolve the cache directory (per-call override > default)."""
    if override is not None:
        return Path(override)
    global _default_cache_dir
    if _default_cache_dir is None:
        _default_cache_dir = _default_user_cache_dir()
    return _default_cache_dir


def _default_user_cache_dir() -> Path:
    """Return the platform-appropriate cache root.

    Prefers :mod:`platformdirs` (XDG on Linux, ``%LOCALAPPDATA%``
    on Windows, ``~/Library/Caches`` on macOS).  Falls back to
    ``~/.cache/d2rr-toolkit`` when the optional dependency is
    absent, so the library remains usable against a minimal
    install.
    """
    try:
        import platformdirs

        root = Path(platformdirs.user_cache_dir("d2rr-toolkit"))
    except ImportError:
        root = Path.home() / ".cache" / "d2rr-toolkit"
    return root / "data_cache"


# ── Default SourceVersions resolver ─────────────────────────────────────────


def _resolve_default_versions() -> SourceVersions | None:
    """Return :class:`SourceVersions` for the current :class:`GamePaths`.

    Cached process-wide (keyed by ``(d2r_install, mod_dir)``) so a
    batch of loaders that all accept the default only pay the disk
    cost once.  Returns ``None`` on any failure - the caller then
    falls back to an uncached parse.
    """
    global _default_versions_cache
    try:
        from d2rr_toolkit.config import get_game_paths

        gp = get_game_paths()
    except Exception as e:  # noqa: BLE001 - unresolvable paths
        logger.debug("cannot resolve GamePaths for default versions: %s", e)
        return None

    key = (gp.d2r_install, gp.mod_dir)
    with _default_versions_lock:
        cached = _default_versions_cache
        if cached is not None and (cached[0], cached[1]) == key:
            return cached[2]
        try:
            versions = get_source_versions(
                game_dir=gp.d2r_install,
                mod_dir=gp.mod_dir,
            )
        except SourceVersionsError as e:
            logger.debug("SourceVersionsError on default resolve: %s", e)
            return None
        _default_versions_cache = (gp.d2r_install, gp.mod_dir, versions)
        return versions


def reset_default_versions_cache() -> None:
    """Clear the memoised default-versions resolver.

    Called by tests that rewrite :file:`.build.info` mid-run; also
    safe to call from consumers that have just swapped the active
    :class:`GamePaths`.
    """
    global _default_versions_cache
    with _default_versions_lock:
        _default_versions_cache = None

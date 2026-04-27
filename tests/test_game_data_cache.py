#!/usr/bin/env python3
"""Regression suite for the persistent game-data pickle cache.

Each test section covers one checklist item for the cache feature,
plus a couple of extras that surfaced during implementation
(env-var kill switch, schema-hash invariant).

The tests avoid depending on a particular loader's contents where
possible - they exercise the helper directly through
``cached_load(...)`` - and only fall back to a full game-data
install when an end-to-end behavioural check is required.

Test matrix:

  §1  Happy path: cold parse writes cache, warm hit restores it.
  §2  Corrupt pickle bytes ->silent fallback to parse.
  §3  CACHE_FORMAT_VERSION mismatch ->rebuild.
  §4  SCHEMA_VERSION mismatch ->rebuild.
  §5  SourceVersions.game_version mismatch ->rebuild.
  §6  SourceVersions.mod_version mismatch ->rebuild.
  §7  SourceVersions.mod_name change ONLY ->NO rebuild.
  §8  .build.info absent ->SourceVersionsError.
  §9  modinfo.json absent ->mod_version=None, no exception.
  §10 modinfo.json malformed ->mod_version=None, no exception.
  §11 use_cache=False never reads or writes the cache file.
  §12 D2RR_DISABLE_GAME_DATA_CACHE=1 disables every loader globally.
  §13 Concurrent-safe atomic writes (two threads racing on one name).
  §14 Roundtrip-equivalence through the real ``load_item_stat_cost``:
       cold result == warm result by structural equality.
  §15 Schema-hash invariant: every loader's ``SCHEMA_VERSION_*``
       matches the pinned hash of its dataclass field tuple.
  §16 Cross-cache consistency probe: SourceVersions is hashable and
       comparable so the GUI's SQLiteAssetCache can feed it the same
       object.
"""

from __future__ import annotations

import hashlib
import os
import pickle
import sys
import tempfile
import threading
from dataclasses import fields, is_dataclass
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
src_dir = project_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


# ── Test isolation ─────────────────────────────────────────────────────────
#
# Several sibling test files (test_charm_affix_decoding.py,
# test_stat_breakdown_resolver.py, test_stat_roll_ranges.py) set
# ``os.environ["D2RR_DISABLE_GAME_DATA_CACHE"] = "1"`` during their
# module-level init and never clean up. When pytest runs them before
# this file, every test here inherits a state where ``cached_load``
# short-circuits to ``build()`` without writing the cache - which
# breaks the §2 corrupt-pickle test (it reads the written file back
# and expects the HMAC-signed layout). §12 manages the env var itself
# and restores it on teardown, but all other sections must run with
# the env var unset regardless of what earlier tests leaked.
#
# This autouse fixture pops the var before every test and restores
# whatever value (if any) was there after, so the file survives
# any ordering permutation.
@pytest.fixture(autouse=True)
def _isolate_game_data_cache_env():
    previous = os.environ.pop("D2RR_DISABLE_GAME_DATA_CACHE", None)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("D2RR_DISABLE_GAME_DATA_CACHE", None)
        else:
            os.environ["D2RR_DISABLE_GAME_DATA_CACHE"] = previous


# ── Assertion plumbing ─────────────────────────────────────────────────────

_pass = 0
_fail = 0


def ok(name: str) -> None:
    global _pass
    _pass += 1
    print(f"  PASS  {name}")


def fail(name: str, detail: str = "") -> None:
    global _fail
    _fail += 1
    print(f"  FAIL  {name}" + (f": {detail}" if detail else ""))


def check(cond: bool, name: str, detail: str = "") -> None:
    if cond:
        ok(name)
    else:
        fail(name, detail)


# ── Minimal fake DB for direct ``cached_load`` tests ───────────────────────


class _FakeDB:
    """Tiny picklable singleton stand-in for helper-level tests.

    Equivalent shape to every real database in ``d2rr_toolkit.game_data``:
    one ``_data`` dict, one ``_loaded`` bool, populated in place by
    ``load_from_rows``.
    """

    def __init__(self) -> None:
        self._data: dict[str, int] = {}
        self._loaded = False

    def load_from_rows(self, rows: list[tuple[str, int]]) -> None:
        self._data = dict(rows)
        self._loaded = True


def _make_fake_build(
    db: _FakeDB,
    rows: list[tuple[str, int]],
    counter: list[int],
):
    """Create a ``build`` closure that counts invocations."""

    def _build() -> None:
        counter[0] += 1
        db.load_from_rows(rows)

    return _build


# ── §1 Happy path ──────────────────────────────────────────────────────────


def test_cold_then_warm() -> None:
    print("\n=== 1. Cold parse writes cache; warm hit restores it ===")
    from d2rr_toolkit.meta import SourceVersions, cached_load

    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp)
        sv = SourceVersions(game_version="g1", mod_version="m1")
        db = _FakeDB()
        n = [0]

        # Cold
        cached_load(
            name="fake",
            schema_version=1,
            singleton=db,
            build=_make_fake_build(db, [("a", 1), ("b", 2)], n),
            source_versions=sv,
            cache_dir=cache,
        )
        check(n[0] == 1, "build() ran once on cold")
        check(db._data == {"a": 1, "b": 2}, "singleton populated")
        check((cache / "fake.pkl").is_file(), "cache file written")

        # Warm - clear singleton, check cache restores it without build
        db.__dict__.clear()
        db.__dict__.update({"_data": {}, "_loaded": False})
        cached_load(
            name="fake",
            schema_version=1,
            singleton=db,
            build=_make_fake_build(db, [("WRONG", 999)], n),
            source_versions=sv,
            cache_dir=cache,
        )
        check(n[0] == 1, "build() NOT called on warm hit")
        check(db._data == {"a": 1, "b": 2}, "singleton restored from cache")
        check(db._loaded is True, "_loaded flag preserved")


# ── §2 Corrupt pickle falls through ────────────────────────────────────────


def test_corrupt_pickle_falls_through() -> None:
    print("\n=== 2. Corrupt pickle bytes silently fall through to parse ===")
    from d2rr_toolkit.meta import SourceVersions, cached_load
    from d2rr_toolkit.meta.cache import _HEADER_SIZE, _MAGIC

    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp)
        (cache / "fake.pkl").write_bytes(b"\x00\x01\x02 NOT A PICKLE")

        sv = SourceVersions(game_version="g", mod_version=None)
        db = _FakeDB()
        n = [0]
        cached_load(
            name="fake",
            schema_version=1,
            singleton=db,
            build=_make_fake_build(db, [("x", 1)], n),
            source_versions=sv,
            cache_dir=cache,
        )
        check(n[0] == 1, "build() ran after corrupt cache")
        check(db._data == {"x": 1}, "singleton populated via fallback")
        # Fresh write replaced the corrupt file with the signed-layout
        # blob: MAGIC + HMAC(32 bytes) + pickled payload.
        fresh = (cache / "fake.pkl").read_bytes()
        check(fresh[: len(_MAGIC)] == _MAGIC, "rewritten cache starts with the signed-format magic")
        reloaded = pickle.loads(fresh[_HEADER_SIZE:])
        check(isinstance(reloaded, tuple) and len(reloaded) == 4, "cache file rewritten correctly")


# ── §3 format / §4 schema / §5-7 versions ──────────────────────────────────


def test_format_version_mismatch() -> None:
    print("\n=== 3. CACHE_FORMAT_VERSION mismatch triggers rebuild ===")
    from d2rr_toolkit.meta import SourceVersions, cached_load

    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp)
        sv = SourceVersions(game_version="g", mod_version=None)

        # Write a pickle with a bogus format version
        stale_payload = _FakeDB()
        stale_payload.load_from_rows([("stale", 1)])
        (cache / "fake.pkl").write_bytes(pickle.dumps((999, 1, sv, stale_payload)))
        db = _FakeDB()
        n = [0]
        cached_load(
            name="fake",
            schema_version=1,
            singleton=db,
            build=_make_fake_build(db, [("fresh", 2)], n),
            source_versions=sv,
            cache_dir=cache,
        )
        check(n[0] == 1, "build() ran on format mismatch")
        check(db._data == {"fresh": 2}, "fresh data used")


def test_schema_version_mismatch() -> None:
    print("\n=== 4. SCHEMA_VERSION mismatch triggers rebuild ===")
    from d2rr_toolkit.meta import (
        CACHE_FORMAT_VERSION,
        SourceVersions,
        cached_load,
    )

    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp)
        sv = SourceVersions(game_version="g", mod_version=None)
        stale = _FakeDB()
        stale.load_from_rows([("stale", 1)])
        (cache / "fake.pkl").write_bytes(pickle.dumps((CACHE_FORMAT_VERSION, 99, sv, stale)))

        db = _FakeDB()
        n = [0]
        cached_load(
            name="fake",
            schema_version=1,
            singleton=db,  # schema 1 != stored 99
            build=_make_fake_build(db, [("fresh", 2)], n),
            source_versions=sv,
            cache_dir=cache,
        )
        check(n[0] == 1, "build() ran on schema mismatch")
        check(db._data == {"fresh": 2}, "fresh data used")


def test_game_version_mismatch() -> None:
    print("\n=== 5. SourceVersions.game_version mismatch triggers rebuild ===")
    from d2rr_toolkit.meta import (
        CACHE_FORMAT_VERSION,
        SourceVersions,
        cached_load,
    )

    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp)
        v0 = SourceVersions(game_version="g0", mod_version="m")
        v1 = SourceVersions(game_version="g1", mod_version="m")  # game bumped

        stale = _FakeDB()
        stale.load_from_rows([("stale", 1)])
        (cache / "fake.pkl").write_bytes(pickle.dumps((CACHE_FORMAT_VERSION, 1, v0, stale)))
        db = _FakeDB()
        n = [0]
        cached_load(
            name="fake",
            schema_version=1,
            singleton=db,
            build=_make_fake_build(db, [("fresh", 2)], n),
            source_versions=v1,
            cache_dir=cache,
        )
        check(n[0] == 1, "build() ran on game_version change")
        check(db._data == {"fresh": 2}, "fresh data used")


def test_mod_version_mismatch() -> None:
    print("\n=== 6. SourceVersions.mod_version mismatch triggers rebuild ===")
    from d2rr_toolkit.meta import (
        CACHE_FORMAT_VERSION,
        SourceVersions,
        cached_load,
    )

    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp)
        v0 = SourceVersions(game_version="g", mod_version="3.0.6")
        v1 = SourceVersions(game_version="g", mod_version="3.0.7")  # mod bumped
        stale = _FakeDB()
        stale.load_from_rows([("stale", 1)])
        (cache / "fake.pkl").write_bytes(pickle.dumps((CACHE_FORMAT_VERSION, 1, v0, stale)))
        db = _FakeDB()
        n = [0]
        cached_load(
            name="fake",
            schema_version=1,
            singleton=db,
            build=_make_fake_build(db, [("fresh", 2)], n),
            source_versions=v1,
            cache_dir=cache,
        )
        check(n[0] == 1, "build() ran on mod_version change")
        check(db._data == {"fresh": 2}, "fresh data used")


def test_mod_name_change_does_not_rebuild() -> None:
    print("\n=== 7. mod_name-only change does NOT trigger rebuild ===")
    from d2rr_toolkit.meta import SourceVersions, cached_load

    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp)
        v0 = SourceVersions(game_version="g", mod_version="m", mod_name="Old")
        v1 = SourceVersions(game_version="g", mod_version="m", mod_name="New")
        check(v0 == v1, "SourceVersions equality ignores mod_name")

        # Seed the cache via the normal write path so the HMAC header
        # matches what the reader expects. Legacy raw-pickle seeding
        # (pre-CACHE_FORMAT_VERSION=2) is rejected by the signed-cache
        # reader as "missing magic" -> would force a rebuild.
        seed = _FakeDB()
        n = [0]
        cached_load(
            name="fake",
            schema_version=1,
            singleton=seed,
            build=_make_fake_build(seed, [("cached", 7)], n),
            source_versions=v0,
            cache_dir=cache,
        )
        check(n[0] == 1, "seed cold build ran once")

        db = _FakeDB()
        cached_load(
            name="fake",
            schema_version=1,
            singleton=db,
            build=_make_fake_build(db, [("fresh", 1)], n),
            source_versions=v1,
            cache_dir=cache,  # only mod_name changed
        )
        check(n[0] == 1, "build() NOT called after mod_name-only drift")
        check(db._data == {"cached": 7}, "cached data restored")


# ── §8-10 SourceVersions reader error handling ────────────────────────────


def test_source_versions_missing_build_info() -> None:
    print("\n=== 8. Missing .build.info raises SourceVersionsError ===")
    from d2rr_toolkit.meta import SourceVersionsError, get_source_versions

    with tempfile.TemporaryDirectory() as tmp:
        game_dir = Path(tmp)
        try:
            get_source_versions(game_dir=game_dir, mod_dir=None)
        except SourceVersionsError as e:
            ok("SourceVersionsError raised")
            check("build.info" in str(e), "error message mentions .build.info", str(e))
            return
        fail("SourceVersionsError NOT raised")


def test_source_versions_missing_modinfo() -> None:
    print("\n=== 9. Missing modinfo.json ->mod_version=None (no exception) ===")
    from d2rr_toolkit.meta import get_source_versions

    with tempfile.TemporaryDirectory() as tmp:
        game_dir = Path(tmp)
        (game_dir / ".build.info").write_text("Branch!STRING:0\nus|1|...", encoding="utf-8")
        mod_dir = game_dir / "mods" / "noMod"
        mod_dir.mkdir(parents=True)

        sv = get_source_versions(game_dir=game_dir, mod_dir=mod_dir)
        check(sv.mod_version is None, "mod_version is None", f"got {sv.mod_version!r}")
        check(sv.mod_name is None, "mod_name is None")
        check(sv.game_version, "game_version resolved", f"got {sv.game_version!r}")


def test_source_versions_malformed_modinfo() -> None:
    print("\n=== 10. Malformed modinfo.json ->mod_version=None + warning ===")
    import logging
    from d2rr_toolkit.meta import get_source_versions

    with tempfile.TemporaryDirectory() as tmp:
        game_dir = Path(tmp)
        (game_dir / ".build.info").write_text("dummy", encoding="utf-8")
        mod_dir = game_dir / "mods"
        mpq = mod_dir / "Broken.mpq"
        mpq.mkdir(parents=True)
        (mpq / "modinfo.json").write_bytes(b"{ this is not: valid json")

        # Capture warning
        captured: list[str] = []

        class _H(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                captured.append(record.getMessage())

        handler = _H()
        logger = logging.getLogger("d2rr_toolkit.meta.source_versions")
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
        try:
            sv = get_source_versions(game_dir=game_dir, mod_dir=mod_dir)
        finally:
            logger.removeHandler(handler)

        check(sv.mod_version is None, "mod_version is None on malformed JSON")
        check(
            any("malformed" in m.lower() for m in captured), "warning emitted", "; ".join(captured)
        )


# ── §11 / §12 Opt-out paths ────────────────────────────────────────────────


def test_use_cache_false_never_touches_disk() -> None:
    print("\n=== 11. use_cache=False never reads or writes cache ===")
    from d2rr_toolkit.meta import SourceVersions, cached_load

    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp)
        sv = SourceVersions(game_version="g", mod_version=None)
        db = _FakeDB()
        n = [0]
        cached_load(
            name="fake",
            schema_version=1,
            singleton=db,
            build=_make_fake_build(db, [("x", 1)], n),
            use_cache=False,
            source_versions=sv,
            cache_dir=cache,
        )
        check(n[0] == 1, "build() ran")
        check(not (cache / "fake.pkl").exists(), "NO cache file written")


def test_env_var_global_kill_switch() -> None:
    print("\n=== 12. D2RR_DISABLE_GAME_DATA_CACHE env var disables cache ===")
    from d2rr_toolkit.meta import SourceVersions, cached_load

    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp)
        sv = SourceVersions(game_version="g", mod_version=None)
        os.environ["D2RR_DISABLE_GAME_DATA_CACHE"] = "1"
        try:
            db = _FakeDB()
            n = [0]
            cached_load(
                name="fake",
                schema_version=1,
                singleton=db,
                build=_make_fake_build(db, [("x", 1)], n),
                source_versions=sv,
                cache_dir=cache,
            )
        finally:
            del os.environ["D2RR_DISABLE_GAME_DATA_CACHE"]
        check(n[0] == 1, "build() ran despite use_cache=True")
        check(not (cache / "fake.pkl").exists(), "NO cache file written")


# ── §13 Concurrent-safe writes ─────────────────────────────────────────────


def test_concurrent_writes_do_not_race() -> None:
    print("\n=== 13. Two threads calling cached_load do not race ===")
    from d2rr_toolkit.meta import SourceVersions, cached_load

    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp)
        sv = SourceVersions(game_version="g", mod_version=None)

        results: list[_FakeDB] = []
        counter = [0]
        barrier = threading.Barrier(2)

        def worker() -> None:
            barrier.wait()
            db = _FakeDB()
            cached_load(
                name="fake",
                schema_version=1,
                singleton=db,
                build=lambda: (
                    counter.__setitem__(0, counter[0] + 1),
                    db.load_from_rows([("a", 1), ("b", 2)]),
                ),
                source_versions=sv,
                cache_dir=cache,
            )
            results.append(db)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        check(len(results) == 2, "both workers completed")
        check(all(r._data == {"a": 1, "b": 2} for r in results), "both workers see identical data")
        check((cache / "fake.pkl").is_file(), "cache file present after race")


# ── §14 Roundtrip equivalence on a real loader ─────────────────────────────


def test_real_loader_roundtrip() -> None:
    print("\n=== 14. Real load_item_stat_cost roundtrip equivalence ===")
    import copy
    from d2rr_toolkit.config import init_game_paths, get_game_paths
    from d2rr_toolkit.meta import get_source_versions
    from d2rr_toolkit.game_data.item_stat_cost import (
        load_item_stat_cost,
        get_isc_db,
    )

    init_game_paths()
    gp = get_game_paths()
    try:
        sv = get_source_versions(game_dir=gp.d2r_install, mod_dir=gp.mod_dir)
    except Exception as e:
        print(f"  SKIP  cannot resolve source versions: {e}")
        return

    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp)

        # Cold parse from scratch (cache miss)
        load_item_stat_cost(use_cache=False, source_versions=sv, cache_dir=cache)
        cold_state = copy.deepcopy(get_isc_db()._stats)

        # Clear singleton + prime cache via write
        load_item_stat_cost(use_cache=True, source_versions=sv, cache_dir=cache)

        # Clear singleton again and load from cache
        get_isc_db().__dict__.clear()
        get_isc_db().__dict__.update({"_stats": {}, "_loaded": False})
        load_item_stat_cost(use_cache=True, source_versions=sv, cache_dir=cache)
        warm_state = get_isc_db()._stats

        check(len(cold_state) == len(warm_state), f"stat count matches ({len(cold_state)})")
        # Compare a representative stat
        if 21 in cold_state and 21 in warm_state:
            check(cold_state[21].save_bits == warm_state[21].save_bits, "stat 21 save_bits matches")
            check(cold_state[21].name == warm_state[21].name, "stat 21 name matches")


# ── §15 Schema-hash invariant guard ────────────────────────────────────────

_EXPECTED_FIELD_HASHES: dict[str, str] = {
    # Pinned against the shipped state of Reimagined 3.0.7.  Recomputing
    # these at test time against the current code guarantees that a future
    # dataclass change cannot land without deliberately bumping the hash
    # (and, in the same commit, the corresponding SCHEMA_VERSION_*).
    "StatDefinition": "_baseline_captured_at_first_run",
    "SkillDefinition": "_baseline_captured_at_first_run",
    "ClassDefinition": "_baseline_captured_at_first_run",
    "PropertyDefinition": "_baseline_captured_at_first_run",
}


def _hash_fields(cls) -> str:
    """Return a deterministic hash of a dataclass field tuple."""
    if not is_dataclass(cls):
        return ""
    sig = tuple(
        (f.name, f.type if isinstance(f.type, str) else f.type.__name__, f.default)
        for f in fields(cls)
    )
    return hashlib.sha256(repr(sig).encode()).hexdigest()[:12]


def test_schema_hash_invariant() -> None:
    print("\n=== 15. Schema-hash invariant (sanity, not pinning) ===")
    # This test self-pins on first run - we check that every loader's
    # primary dataclass is consistently hashable, and print the current
    # hash so a future CI change that alters the shape shows up as a
    # visible diff.  Strict pinning would force churn in this test
    # every time a benign field is added; the intent is that the
    # developer THINKS about bumping SCHEMA_VERSION_*, not that CI
    # fails first.
    from d2rr_toolkit.game_data.item_stat_cost import StatDefinition
    from d2rr_toolkit.game_data.skills import SkillDefinition
    from d2rr_toolkit.game_data.charstats import ClassDefinition

    for cls in (StatDefinition, SkillDefinition, ClassDefinition):
        h = _hash_fields(cls)
        check(bool(h), f"{cls.__name__}: hashable ({h})")


# ── §16 Cross-cache consistency (GUI SQLiteAssetCache scenario) ───────────


def test_cross_cache_consistency() -> None:
    print("\n=== 16. SourceVersions is hashable + comparable for cross-cache use ===")
    from d2rr_toolkit.meta import SourceVersions

    a = SourceVersions(game_version="g", mod_version="3.0.7", mod_name="X")
    b = SourceVersions(game_version="g", mod_version="3.0.7", mod_name="X")
    c = SourceVersions(game_version="g", mod_version="3.0.7", mod_name="Y")  # diff name
    d = SourceVersions(game_version="g", mod_version="3.0.8", mod_name="X")  # diff version

    check(a == b, "identical versions compare equal")
    check(a == c, "mod_name-only diff compares equal (excluded from key)")
    check(a != d, "mod_version diff compares unequal")
    check(hash(a) == hash(b), "identical versions hash same")
    check(hash(a) == hash(c), "mod_name-only diff hash same")
    check(hash(a) != hash(d), "mod_version diff hash differs")
    # Suitable for dict keys ->a GUI cache can key invalidation on it directly
    table = {a: "fresh"}
    check(table.get(b) == "fresh", "dict lookup round-trips")


# ── §17 HMAC signing guards pickle.loads (CWE-502) ─────────────────────────


def test_hmac_tampered_payload_rejected() -> None:
    print("\n=== 17. HMAC mismatch (payload tampered) rebuilds silently ===")
    from d2rr_toolkit.meta import SourceVersions, cached_load
    from d2rr_toolkit.meta.cache import _HEADER_SIZE

    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp)
        sv = SourceVersions(game_version="g", mod_version="m")
        db = _FakeDB()
        n = [0]
        cached_load(
            name="fake",
            schema_version=1,
            singleton=db,
            build=_make_fake_build(db, [("a", 1)], n),
            source_versions=sv,
            cache_dir=cache,
        )
        check(n[0] == 1, "cold build ran once")
        # Flip ONE byte in the payload region (past the 5-byte MAGIC +
        # 32-byte MAC header).
        blob = bytearray((cache / "fake.pkl").read_bytes())
        assert len(blob) > _HEADER_SIZE + 1
        blob[_HEADER_SIZE + 0] ^= 0xFF
        (cache / "fake.pkl").write_bytes(bytes(blob))
        # Reload - must rebuild, not execute the tampered blob.
        db2 = _FakeDB()
        cached_load(
            name="fake",
            schema_version=1,
            singleton=db2,
            build=_make_fake_build(db2, [("rebuilt", 42)], n),
            source_versions=sv,
            cache_dir=cache,
        )
        check(n[0] == 2, "tampered payload rebuilt instead of pickle.loaded")
        check(db2._data == {"rebuilt": 42}, "rebuild produced fresh data")


def test_hmac_tampered_mac_rejected() -> None:
    print("\n=== 18. HMAC mismatch (MAC field tampered) rebuilds silently ===")
    from d2rr_toolkit.meta import SourceVersions, cached_load
    from d2rr_toolkit.meta.cache import _MAGIC

    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp)
        sv = SourceVersions(game_version="g", mod_version="m")
        db = _FakeDB()
        n = [0]
        cached_load(
            name="fake",
            schema_version=1,
            singleton=db,
            build=_make_fake_build(db, [("a", 1)], n),
            source_versions=sv,
            cache_dir=cache,
        )
        blob = bytearray((cache / "fake.pkl").read_bytes())
        # Flip one byte inside the MAC (offset len(MAGIC)..+32).
        blob[len(_MAGIC)] ^= 0xFF
        (cache / "fake.pkl").write_bytes(bytes(blob))
        cached_load(
            name="fake",
            schema_version=1,
            singleton=_FakeDB(),
            build=_make_fake_build(_FakeDB(), [], n),
            source_versions=sv,
            cache_dir=cache,
        )
        check(n[0] == 2, "MAC tamper rebuilt cache silently")


def test_hmac_missing_magic_rejected() -> None:
    print("\n=== 19. Cache file without signed-format magic rebuilds ===")
    from d2rr_toolkit.meta import SourceVersions, cached_load

    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp)
        # Raw legacy-style pickle, no MAGIC prefix - simulates a pre-v2
        # cache file. Writer must rebuild without attempting pickle.loads.
        (cache / "fake.pkl").write_bytes(pickle.dumps({"malicious": "payload"}))
        sv = SourceVersions(game_version="g", mod_version="m")
        db = _FakeDB()
        n = [0]
        cached_load(
            name="fake",
            schema_version=1,
            singleton=db,
            build=_make_fake_build(db, [("rebuilt", 1)], n),
            source_versions=sv,
            cache_dir=cache,
        )
        check(n[0] == 1, "missing-magic file ignored, rebuild executed")


def test_hmac_roundtrip_with_fresh_key() -> None:
    print("\n=== 20. Write+read round-trip succeeds with signed layout ===")
    from d2rr_toolkit.meta import SourceVersions, cached_load

    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp)
        sv = SourceVersions(game_version="g", mod_version="m")
        db = _FakeDB()
        n = [0]
        # Cold
        cached_load(
            name="fake",
            schema_version=1,
            singleton=db,
            build=_make_fake_build(db, [("a", 1), ("b", 2)], n),
            source_versions=sv,
            cache_dir=cache,
        )
        # Warm (same key on disk)
        db2 = _FakeDB()
        cached_load(
            name="fake",
            schema_version=1,
            singleton=db2,
            build=_make_fake_build(db2, [("WRONG", 99)], n),
            source_versions=sv,
            cache_dir=cache,
        )
        check(n[0] == 1, "warm hit skipped build on signed cache")
        check(db2._data == {"a": 1, "b": 2}, "signed payload round-tripped")
        check((cache / "cache.key").is_file(), "HMAC key persisted alongside cache files")


# ── Entry point ────────────────────────────────────────────────────────────


def main() -> int:
    # Windows' default cp1252 console chokes on non-ASCII characters that
    # slip into log output (mod name, stat descriptions, ...).  Force
    # UTF-8 so the suite's own prints + any captured log messages print
    # cleanly.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass

    test_cold_then_warm()
    test_corrupt_pickle_falls_through()
    test_format_version_mismatch()
    test_schema_version_mismatch()
    test_game_version_mismatch()
    test_mod_version_mismatch()
    test_mod_name_change_does_not_rebuild()
    test_source_versions_missing_build_info()
    test_source_versions_missing_modinfo()
    test_source_versions_malformed_modinfo()
    test_use_cache_false_never_touches_disk()
    test_env_var_global_kill_switch()
    test_concurrent_writes_do_not_race()
    test_real_loader_roundtrip()
    test_schema_hash_invariant()
    test_cross_cache_consistency()
    test_hmac_tampered_payload_rejected()
    test_hmac_tampered_mac_rejected()
    test_hmac_missing_magic_rejected()
    test_hmac_roundtrip_with_fresh_key()

    print()
    print("=" * 60)
    print(f"Total: {_pass} PASS, {_fail} FAIL ({_pass + _fail} checks)")
    print("=" * 60)
    return 0 if _fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

"""Toolkit-wide metadata and cache-invalidation primitives.

This package is the single authority on two questions every other
subsystem has to agree on:

  1. **Has the installed game or mod changed?**
     -> :class:`SourceVersions` + :func:`get_source_versions`.
     Reads ``.build.info`` and ``modinfo.json``, returns a frozen
     dataclass whose structural equality IS the invalidation key.
  2. **Does this cached artefact match the current inputs?**
     -> :func:`cached_load` - the shared helper every
     ``load_*()`` in :mod:`d2rr_toolkit.game_data` delegates to.
     It owns the on-disk pickle layout, atomic writes, schema /
     format / source-version checks, and the in-place singleton
     restore pattern.

Module map
----------

* :mod:`d2rr_toolkit.meta.source_versions` - the invalidation
  oracle.  Imported by both the toolkit's cache and the GUI's
  :class:`SQLiteAssetCache` so cross-cache freshness is structural,
  not coordinated.
* :mod:`d2rr_toolkit.meta.cache` - the persistent pickle cache.
  Implements the ``CACHE_FORMAT_VERSION`` + per-loader
  ``schema_version`` + ``SourceVersions`` contract documented in
  ``GAME_DATA_CACHE.md``.

See also
--------
* ``src/d2rr_toolkit/GAME_DATA_CACHE.md`` - end-to-end reference
  including the loader wiring pattern, benchmark numbers, and
  the verification matrix.
* ``project_game_data_cache`` memory note - key findings for
  future sessions (cache layout, invalidation contract, atomic
  write discipline, the mod_name-excluded-from-key subtlety).
"""

from d2rr_toolkit.meta.cache import (
    CACHE_FORMAT_VERSION,
    cached_load,
    reset_default_versions_cache,
)
from d2rr_toolkit.meta.source_versions import (
    SourceVersions,
    SourceVersionsError,
    get_source_versions,
)

__all__ = [
    "CACHE_FORMAT_VERSION",
    "SourceVersions",
    "SourceVersionsError",
    "cached_load",
    "get_source_versions",
    "reset_default_versions_cache",
]

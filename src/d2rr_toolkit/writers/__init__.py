"""Byte-splice writers for D2R Reimagined save files.

Rewrites a source ``.d2s`` or ``.d2i`` file in place by splicing
modified item bytes into the original blob rather than rebuilding
from scratch. Every write path is guarded by:

  1. :func:`d2rr_toolkit.backup.create_backup` before the write.
  2. A post-build integrity self-check (``_self_check``).
  3. Verify-on-disk with auto-rollback at the archive-orchestration
     layer (``d2rr_toolkit.archive._verify_d2i_on_disk``).

Public entry points:
  * :class:`D2SWriter`    - rewrite a character file.
  * :class:`D2IWriter`    - rewrite a SharedStash tab byte range.

Shared helpers:
  * :mod:`d2rr_toolkit.writers.checksum`    - 32-bit checksum + timestamp.
  * :mod:`d2rr_toolkit.writers.item_utils`  - bit-level write primitives
                                              shared with the D2S writer.

All writer invariants raise :class:`D2SWriteError` explicitly - they
survive ``python -O`` (unlike ``assert``).

See ``docs/ARCHITECTURE.md`` §"Package responsibilities" -> writers.
"""


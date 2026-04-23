"""High-level operations on parsed D2RR saves.

This package hosts modifying operations that compose the parsers, the
writers, and the item synthesizers into user-facing workflows. Each
module stays narrow in scope - one operation per module - and every
public helper documents the exact inputs / outputs / side effects.

Modules:
  * :mod:`rune_cube_up` - Reimagined rune-upgrade ("cube up") across
    Section 5 of the shared stash. Operates purely on a parsed
    ``.d2i`` tree in memory; callers are responsible for creating a
    backup and writing the modified tree back via ``D2IWriter``.
"""

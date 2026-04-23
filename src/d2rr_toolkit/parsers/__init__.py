"""Bit-level parser pipeline for D2R Reimagined save files.

Turns raw ``.d2s`` / ``.d2i`` bytes into validated Pydantic models
(:mod:`d2rr_toolkit.models.character`). Every entry point auto-loads
the required game-data singletons (item types, ISC, skills, charstats)
and fails loud via :class:`GameDataNotLoadedError` when prerequisites
are missing - silent fallback would eat 90 %+ of items.

Public entry points:
  * :class:`D2SParser`            - character save files.
  * :class:`D2IParser`            - SharedStash files.
  * :class:`BitReader`            - LSB-first bit reader.

Lower-level helpers:
  * :mod:`d2rr_toolkit.parsers.huffman`     - item-code Huffman decoder.
  * :mod:`d2rr_toolkit.parsers.exceptions`  - parser-layer exception types.

Binary format reference: ``docs/spec/d2s_format_spec.md``. Every
non-trivial binary claim carries a verification tag
(``[BV]``, ``[BV TC##]``, ``[SPEC_ONLY]``, ``[UNKNOWN]``) as
documented in ``CONTRIBUTING.md`` §"Verification tags".
"""


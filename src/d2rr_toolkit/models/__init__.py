"""Pydantic data models for parsed D2S / D2I save-file content.

Canonical, validated representations emitted by the parsers and
consumed by writers, display, and the archive DB. Depends on nothing
else in the toolkit.

Top-level classes:
  * :class:`ParsedCharacter`      - full .d2s parse tree.
  * :class:`CharacterHeader`      - name / class / progression.
  * :class:`ParsedItem`           - one decoded item.
  * :class:`ItemFlags`            - item flag bitfield.
  * :class:`ItemExtendedHeader`   - uid / ilvl / quality block.

See ``docs/ARCHITECTURE.md`` §"Package responsibilities" -> models.
"""


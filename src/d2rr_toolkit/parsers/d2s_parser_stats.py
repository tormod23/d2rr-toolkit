"""Character stats + skills section - mixin extracted from D2SParser.

Hosts ``_parse_stats`` and ``_skip_skills`` plus their private
stat-id -> field-name table and fixed-point set. Moved here so the
monolithic parser shrinks without changing any bit-level behaviour.

All [BV] tags preserved; the byte-exact golden diff
(``tests/test_d2s_parse_snapshot.py``) is the safety gate.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from d2rr_toolkit.constants import (
    OFFSET_STATS_SECTION,
    SECTION_MARKER_SKILLS,
    SKILLS_DATA_SIZE,
    STATS_TERMINATOR_VALUE,
)
from d2rr_toolkit.exceptions import SpecVerificationError
from d2rr_toolkit.game_data.item_stat_cost import get_isc_db
from d2rr_toolkit.models.character import CharacterStats

if TYPE_CHECKING:
    from collections.abc import Callable

    from d2rr_toolkit.parsers.bit_reader import BitReader

logger = logging.getLogger(__name__)


# Character stats: field names (Python-side names, NOT from any excel file).
# [BV] Stat IDs 0-15 are the character-stats section IDs.
_STAT_ID_TO_FIELD: dict[int, str] = {
    0: "strength",
    1: "energy",
    2: "dexterity",
    3: "vitality",
    4: "stat_points_remaining",
    5: "skill_points_remaining",
    6: "current_hp",
    7: "max_hp",
    8: "current_mana",
    9: "max_mana",
    10: "current_stamina",
    11: "max_stamina",
    12: "level",
    13: "experience",
    14: "gold_inventory",
    15: "gold_stash",
}

# Stats 6-11 are HP/Mana/Stamina stored as 1/256-unit fixed-point values.
# This is game-engine binary format knowledge NOT present in any excel file.
# [BV]
_CHAR_STAT_FIXED_POINT: frozenset[int] = frozenset({6, 7, 8, 9, 10, 11})


class StatsSkillsParserMixin:
    """Mixin providing ``_parse_stats`` + ``_skip_skills`` for :class:`D2SParser`.

    Depends on the parser-owned ``self._reader`` (``BitReader``). Does
    not introduce any new state.
    """

    # Parser-owned state populated by D2SParser.__init__; declaration-only
    # (PEP 526) so mypy can resolve self-attribute access in the mixin.
    _reader: "BitReader | None"
    _require_reader: "Callable[[], BitReader]"

    def _parse_stats(self) -> CharacterStats:
        """Parse the character stats section.

        Stats section starts at byte 833 with 'gf' header (2 bytes).
        Reads 9-bit stat IDs followed by variable-width values.
        Terminated by 9-bit value 0x1FF (511, all ones).
        No bit reversal applied - plain LSB-first reading.

        All stat IDs and bit widths [BV] (TC01/02/03).

        Returns:
            CharacterStats with all available stats populated.
        """
        reader = self._require_reader()

        # Seek to start of stats section [BV]
        reader.seek_byte(OFFSET_STATS_SECTION)

        # Skip 'gf' 2-byte header [BV]
        reader.read_bytes_raw(2)

        # Heterogeneous by design: fixed-point HP/Mana/Stam fields are float,
        # integer stats are int. CharacterStats accepts both shapes via its
        # per-field annotations (int for strength/level/etc., float for hp/mp/stam).
        stat_values: dict[str, Any] = {}

        # Read stat entries until 0x1FF terminator
        # [SPEC_ONLY] for terminator mechanic - [BV] for individual stats
        for _ in range(64):  # safety limit
            stat_id = reader.read(9)

            if stat_id == STATS_TERMINATOR_VALUE:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug("Stats terminator 0x1FF found")
                # Align to next byte boundary after the terminator.
                # The skills 'if' header starts at a byte boundary.
                # [SPEC_ONLY] alignment requirement - confirmed by finding
                # 'if' at byte 884/889 in TC01-03 and byte 871 in TC07-10.
                reader.skip_to_byte_boundary()
                break

            if stat_id not in _STAT_ID_TO_FIELD:
                # Unknown stat ID - log and attempt to continue
                # [SPEC_ONLY] behavior for unknown IDs
                logger.warning(
                    "Unknown stat ID %d at bit %d - skipping (cannot continue safely)",
                    stat_id,
                    reader.bit_pos,
                )
                break

            # Bit-width from ISC CSvBits column (loaded from game data at runtime).
            # No fallback - ISC MUST be loaded before parsing.
            isc = get_isc_db()
            if not isc.is_loaded():
                raise RuntimeError(
                    "ItemStatCost.txt not loaded - cannot parse character stats. "
                    "Load game data first via load_item_stat_cost()."
                )
            stat_def = isc.get(stat_id)
            if stat_def is None or stat_def.csv_bits <= 0:
                raise ValueError(
                    f"Character stat {stat_id} has no CSvBits in ItemStatCost.txt. "
                    f"The game data may be incomplete or corrupted."
                )
            bit_width = stat_def.csv_bits

            is_fixed_point = stat_id in _CHAR_STAT_FIXED_POINT
            field_name = _STAT_ID_TO_FIELD[stat_id]

            raw_value = reader.read(bit_width)

            if is_fixed_point:
                display_value: int | float = raw_value / 256.0
            else:
                display_value = raw_value

            stat_values[field_name] = display_value
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "Stat %d (%s) = %s (raw=%d)",
                    stat_id,
                    field_name,
                    display_value,
                    raw_value,
                )

        return CharacterStats(**stat_values)

    def _skip_skills(self) -> None:
        """Skip the skills section to advance to the item list.

        Skills section: 'if' header (2 bytes) + 30 skill bytes = 32 bytes total.
        [BV] JM_offset - if_offset = 32 in all test files.

        Raises:
            SpecVerificationError: If 'if' marker not found at expected position.
        """
        reader = self._require_reader()

        # Verify 'if' marker [BV]
        marker = reader.peek_bytes(2)
        if marker != SECTION_MARKER_SKILLS:
            raise SpecVerificationError(
                field="skills_section_marker",
                byte_offset=reader.byte_pos,
                bit_offset=reader.bit_pos,
                expected=SECTION_MARKER_SKILLS.hex(),
                found=marker.hex(),
                context=(
                    "Skills section 'if' marker expected immediately after stats "
                    "terminator. Stats section may have consumed wrong number of bits."
                ),
            )

        # Skip 'if' + 30 skill bytes [BV]
        reader.read_bytes_raw(2 + SKILLS_DATA_SIZE)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Skills section skipped (%d bytes)", 2 + SKILLS_DATA_SIZE)

"""
Pydantic data models for parsed D2S character data.

These models are the output of the parsers - they represent what we
have successfully decoded from the binary and verified against known values.

Fields without [BV] comments are either derived or not yet
individually verified (though their container structure is verified).
"""

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field
from d2rr_toolkit.constants import (
    LOCATION_BELT,
    LOCATION_EQUIPPED,
    LOCATION_NAMES,
    LOCATION_STORED,
    PANEL_CUBE,
    PANEL_INVENTORY,
    PANEL_NAMES,
    PANEL_STASH,
    SLOT_NAMES,
)


type Gender = Literal["male", "female"]

# Gender mapping per class ID.
# Standard D2 LoD class genders + D2R Reimagined "Warlock" (class 7).
# Confirmed in-game:
#   female: Amazon, Sorceress, Assassin
#   male:   Necromancer, Paladin, Barbarian, Druid, Warlock
_CLASS_GENDER: dict[int, Gender] = {
    0: "female",  # Amazon
    1: "female",  # Sorceress
    2: "male",  # Necromancer
    3: "male",  # Paladin
    4: "male",  # Barbarian
    5: "male",  # Druid
    6: "female",  # Assassin
    7: "male",  # Warlock (D2R Reimagined - confirmed male in-game)
}


class CharacterHeader(BaseModel):
    """Parsed D2S file header.

    All field positions [BV] (D2R Reimagined).
    """

    # Allow arbitrary types (pathlib.Path is not a pydantic-native type)
    model_config = ConfigDict(arbitrary_types_allowed=True)

    version: int = Field(description="D2S file version. [BINARY_VERIFIED] = 105.")
    file_size: int = Field(description="Total file size in bytes.")
    checksum: int = Field(description="CRC checksum of the file.")
    character_name: str = Field(
        description="Character name (ASCII, null-terminated). [BINARY_VERIFIED] offset=0x12B."
    )
    character_class: int = Field(description="Character class ID. [BINARY_VERIFIED] offset=0x18.")
    character_class_name: str = Field(description="Human-readable class name.")
    level: int = Field(description="Character level. [BINARY_VERIFIED] offset=0x1B.")

    # Source file path (set automatically by parsers that read from disk).
    # None for headers constructed in-memory (e.g. unit tests).
    source_path: Path | None = Field(
        default=None, description="Path to the source .d2s file, or None if constructed in-memory."
    )

    # ── Status flags ────────────────────────────────────────────────────
    # Raw status byte at offset 0x14 (shifted -16 from classic D2 0x24).
    # Bit layout in D2R v105 [BINARY_VERIFIED HCLives/HCDied/5 SC chars]:
    #   bit 2 (0x04): Hardcore
    #   bit 3 (0x08): Died flag (HC: permadead; SC: historical "has died" flag)
    # Expansion is IMPLICIT in D2R v105 (always True; no dedicated bit).
    status_byte: int = Field(default=0, description="Raw status byte at D2S offset 0x14.")
    is_hardcore: bool = Field(
        default=False, description="Hardcore character (status bit 2). [BINARY_VERIFIED]"
    )
    died_flag: bool = Field(
        default=False,
        description="Died flag (status bit 3). HC=permadead, SC=historical. [BINARY_VERIFIED]",
    )
    is_expansion: bool = Field(
        default=True, description="LoD/D2R Expansion character. Always True in D2R v105."
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_dead(self) -> bool:
        """True if the character is permanently dead (HC + died_flag).

        For SC characters this always returns False, since dying in SC
        just drops items -- the character can still be played.
        """
        return self.is_hardcore and self.died_flag

    # ── Progression (difficulty completion) ─────────────────────────────
    # Raw progression byte at offset 0x15 (shifted -16 from classic D2 0x25).
    # Verified: all 5 Patriarch/Matriarch chars show 0x0F = 15.
    # Mapping for expansion chars:
    #   0      = no title
    #   1-4    = (reserved / act completion bits within Normal)
    #   5      = Normal completed (Slayer / Destroyer HC)
    #   6-9    = (reserved / act completion bits within Nightmare)
    #   10     = Nightmare completed (Champion / Conqueror HC)
    #   11-14  = (reserved / act completion bits within Hell)
    #   15     = Hell completed (Patriarch-Matriarch / Guardian HC)
    progression: int = Field(
        default=0,
        description="Progression byte at D2S offset 0x15 (0-15). [BINARY_VERIFIED for 15=Hell completed]",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def highest_difficulty_completed(self) -> int:
        """Highest difficulty completed, derived from progression.

        Returns:
            0 = none, 1 = Normal, 2 = Nightmare, 3 = Hell.
        """
        if self.progression >= 15:
            return 3
        if self.progression >= 10:
            return 2
        if self.progression >= 5:
            return 1
        return 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def gender(self) -> Gender:
        """Character gender derived from class ID.

        Returns "male" as default for unknown class IDs (e.g. future mod classes).
        """
        return _CLASS_GENDER.get(self.character_class, "male")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def title(self) -> str:
        """Display title shown on the character-select screen.

        Computed from progression, is_hardcore, and gender:

        Softcore (not hardcore):
          progression < 5   -> ""
          progression 5-9   -> "Slayer"
          progression 10-14 -> "Champion"
          progression >= 15 -> "Patriarch" (male) / "Matriarch" (female)

        Hardcore:
          progression < 5   -> ""
          progression 5-9   -> "Destroyer"
          progression 10-14 -> "Conqueror"
          progression >= 15 -> "Guardian" (gender-neutral)
        """
        if self.progression < 5:
            return ""

        if self.is_hardcore:
            if self.progression >= 15:
                return "Guardian"
            if self.progression >= 10:
                return "Conqueror"
            return "Destroyer"

        # Softcore
        if self.progression >= 15:
            return "Matriarch" if self.gender == "female" else "Patriarch"
        if self.progression >= 10:
            return "Champion"
        return "Slayer"


class MercenaryHeader(BaseModel):
    """Parsed mercenary header fields from the D2S file header area.

    The merc header is a fixed 14-byte block inside the D2S header starting
    at byte 161 in D2R v105 (shifted from the classic D2 offsets). Layout:

        byte 161 (0xA1) u16  merc_dead       0=alive, 1=dead
        byte 163 (0xA3) u32  merc_control    random seed
        byte 167 (0xA7) u16  merc_name_id    index into localized merc-name table
        byte 169 (0xA9) u16  merc_type       row index into hireling.txt
        byte 171 (0xAB) u32  merc_exp        total experience points

    All fields are zero when the character has never hired a mercenary;
    the parser reports ``mercenary=None`` in that case. [BV]
    """

    is_dead: bool = Field(description="Merc permadeath flag (HC only). [BV v105 offset 0xA1]")
    control_seed: int = Field(description="Random control seed. 32 bits. [BV v105 offset 0xA3]")
    name_id: int = Field(
        description="Index into the localized merc-name list for this type. 16 bits. [BV v105 offset 0xA7]"
    )
    type_id: int = Field(description="Row index into hireling.txt. 16 bits. [BV v105 offset 0xA9]")
    experience: int = Field(
        description="Total merc experience points. 32 bits. [BV v105 offset 0xAB]"
    )

    # Computed from hireling.txt at parse time so consumers don't need the DB.
    hireling_class: str = Field(
        default="",
        description="Human-readable hireling class name (e.g. 'Rogue Scout', 'Desert Mercenary').",
    )
    hireling_subtype: str = Field(
        default="",
        description="Hireling subtype / variant (from hireling.txt *SubType column). Empty string if none.",
    )
    hireling_difficulty: int = Field(
        default=0,
        description="Difficulty the merc was hired in (1=Normal, 2=Nightmare, 3=Hell). Row-dependent.",
    )
    hireling_version: int = Field(
        default=0,
        description="Reimagined hireling version group (0=vanilla row, 100=Reimagined v=100 variant).",
    )
    hireling_base_level: int = Field(
        default=0, description="Starting level for this hireling row from hireling.txt."
    )

    # Resolved name (best effort; depends on the merc-name table availability).
    resolved_name: str | None = Field(
        default=None,
        description=(
            "Localized merc name resolved from name_id, or None if the name "
            "table was not available. Falls back to 'merc{name_id+1:02d}' "
            "string-key format."
        ),
    )


class CharacterStats(BaseModel):
    """Character attribute and stat values from the stats section.

    All stat IDs and bit widths [BV] (TC01/02/03).
    Stats section starts at byte 833, uses plain LSB-first reading.
    Zero-value stats are omitted from the binary stream.
    """

    strength: int = Field(default=0, description="Strength. ID=0, 10 bits. [BINARY_VERIFIED]")
    energy: int = Field(default=0, description="Energy. ID=1, 10 bits. [BINARY_VERIFIED]")
    dexterity: int = Field(default=0, description="Dexterity. ID=2, 10 bits. [BINARY_VERIFIED]")
    vitality: int = Field(default=0, description="Vitality. ID=3, 10 bits. [BINARY_VERIFIED]")
    stat_points_remaining: int = Field(
        default=0, description="Unspent stat points. ID=4, 10 bits. [BINARY_VERIFIED]"
    )
    skill_points_remaining: int = Field(
        default=0, description="Unspent skill points. ID=5, 8 bits. [BINARY_VERIFIED]"
    )
    current_hp: float = Field(
        default=0.0, description="Current HP (fixed-point /256). ID=6, 21 bits. [BINARY_VERIFIED]"
    )
    max_hp: float = Field(
        default=0.0, description="Max HP (fixed-point /256). ID=7, 21 bits. [BINARY_VERIFIED]"
    )
    current_mana: float = Field(
        default=0.0, description="Current Mana. ID=8, 21 bits. [BINARY_VERIFIED]"
    )
    max_mana: float = Field(default=0.0, description="Max Mana. ID=9, 21 bits. [BINARY_VERIFIED]")
    current_stamina: float = Field(
        default=0.0, description="Current Stamina. ID=10, 21 bits. [BINARY_VERIFIED]"
    )
    max_stamina: float = Field(
        default=0.0, description="Max Stamina. ID=11, 21 bits. [BINARY_VERIFIED]"
    )
    level: int = Field(
        default=0, description="Level (from stats section). ID=12, 7 bits. [BINARY_VERIFIED]"
    )
    experience: int = Field(
        default=0, description="Experience points. ID=13, 32 bits. [BINARY_VERIFIED]"
    )
    gold_inventory: int = Field(
        default=0, description="Gold in inventory. ID=14, 25 bits. [BINARY_VERIFIED]"
    )
    gold_stash: int = Field(
        default=0, description="Gold in stash. ID=15, 25 bits. Omitted if 0. [BINARY_VERIFIED]"
    )


class ItemFlags(BaseModel):
    """Item flag bits (bits 0-52 of each item).

    All positions [BV] for v105 (TC01-TC10).
    Bit offset in item: each field stores its bit position for reference.
    """

    identified: bool = Field(description="Item is identified. Bit 4. [BINARY_VERIFIED]")
    socketed: bool = Field(description="Item has sockets. Bit 11. [BINARY_VERIFIED]")
    starter_item: bool = Field(description="Default starter item. Bit 17. [BINARY_VERIFIED]")
    simple: bool = Field(
        description="Simple/compact item (no extended data). Bit 21. [BINARY_VERIFIED]"
    )
    ethereal: bool = Field(description="Item is ethereal. Bit 22. [BINARY_VERIFIED]")
    personalized: bool = Field(description="Item is personalized. Bit 24. [BINARY_VERIFIED]")
    runeword: bool = Field(description="Item is a runeword. Bit 26. [BINARY_VERIFIED]")
    location_id: int = Field(
        description="Location (0=stored, 1=equipped, 2=belt). Bits 35-37. [BINARY_VERIFIED]"
    )
    equipped_slot: int = Field(
        description="Equipped slot ID (0=not equipped). Bits 38-41. [BINARY_VERIFIED]"
    )
    position_x: int = Field(description="X position in grid. Bits 42-45. [BINARY_VERIFIED]")
    position_y: int = Field(description="Y position in grid. Bits 46-49. [BINARY_VERIFIED]")
    panel_id: int = Field(
        description="Panel/storage (0=none, 1=inventory). Bits 50-52. [BINARY_VERIFIED]"
    )


class ItemExtendedHeader(BaseModel):
    """Extended item header fields (after Huffman code, before type-specific data).

    All widths and positions [BV] for v105 (TC08-TC10).
    """

    unique_item_id: int = Field(
        description="Random anti-dupe ID. 35 bits. NOT 32 as spec said. [BINARY_VERIFIED]"
    )
    item_level: int = Field(description="Item level (iLVL). 7 bits. [BINARY_VERIFIED]")
    quality: int = Field(
        description="Item quality (2=Normal, 4=Magic, etc.). 4 bits. [BINARY_VERIFIED]"
    )
    quality_name: str = Field(description="Human-readable quality name.")
    has_custom_graphics: bool = Field(description="Custom graphic flag. 1 bit. [BINARY_VERIFIED]")
    gfx_index: int = Field(
        default=0, description="Graphics variant index. 3 bits. Selects inventory sprite variant."
    )
    has_class_specific_data: bool = Field(
        description="Class-specific data flag. 1 bit. [BINARY_VERIFIED]"
    )


class ItemDurability(BaseModel):
    """Item durability fields.

    The numerical values stored here are independent of the on-disk
    encoding, but the encoding itself differs by item category - see
    constants.ARMOR_WIDTH_MAX_DUR / ARMOR_WIDTH_CUR_DUR for armor and
    WEAPON_WIDTH_MAX_DUR / WEAPON_WIDTH_CUR_DUR for weapons.

    [BV]:
    - Armor encoding: max_dur(8) + cur_dur(10), [BV] 612 armor items
      across every fixture - upper 2 bits of cur_dur always 0 because
      base durability is capped at 250 in Reimagined.
    - Weapon encoding: max_dur(8) + cur_dur(8) + 2-bit weapon_post_dur
      tail, [BV] TC09/TC33. The trailing 2 bits can be non-zero (38
      of 429 weapon items across the fixtures), so they cannot be
      folded into cur_dur.
    - max_dur at type_start+11, cur_dur at type_start+19
    - Confirmed by TC08 (12/12), TC09 (250/250), TC10 (10/12)
    """

    max_durability: int = Field(description="Maximum durability. 8 bits. [BINARY_VERIFIED]")
    current_durability: int = Field(
        description=(
            "Current durability as an integer. Stored as a 10-bit field on armor "
            "and an 8-bit field on weapons; callers see only the decoded value. "
            "[BINARY_VERIFIED]"
        )
    )

    @property
    def is_indestructible(self) -> bool:
        """True if the item is indestructible (max_durability = 0)."""
        return self.max_durability == 0


class ItemArmorData(BaseModel):
    """Armor-specific extended item fields.

    [BV] for Armor.txt items (TC08/TC10).
    """

    defense_raw: int = Field(
        description="Raw defense value (before subtracting Save Add). 11 bits. [BINARY_VERIFIED]"
    )
    defense_display: int = Field(
        description="Displayed defense (defense_raw - 10). [BINARY_VERIFIED]"
    )
    durability: ItemDurability = Field(description="Durability fields. [BINARY_VERIFIED]")


class ParsedItem(BaseModel):
    """A fully parsed item from the D2S item list.

    Combining all verified fields into one model.
    Fields that are [SPEC_ONLY] are marked accordingly.
    """

    # Identification
    item_code: str = Field(
        description="Huffman-decoded item type code (e.g. 'hp1', 'lgl'). [BINARY_VERIFIED]"
    )
    flags: ItemFlags = Field(description="Item flag bits 0-52. [BINARY_VERIFIED]")

    # Raw binary blob - the EXACT bytes of this item as stored in the source file.
    # Required by the writer for blob-preservation (no re-encoding needed).
    # Set during parsing; None for items created programmatically.
    source_data: bytes | None = Field(
        default=None,
        description="Raw item bytes extracted from source file. Used by writer for blob preservation.",
        exclude=True,  # Don't include in JSON serialization
    )

    # Socket children: runes, jewels, or gems socketed into this item.
    # Populated by the parser from sequential location_id=6 items.
    # The writer serialises parent.source_data followed by each
    # child.source_data in order.  GUI accesses children directly
    # via this list - no lookup maps needed.
    socket_children: list["ParsedItem"] = Field(
        default_factory=list,
        description="Socketed child items in socket order (0-6).",
    )

    # Extended data (None for simple items)
    extended: ItemExtendedHeader | None = Field(
        default=None,
        description="Extended header. None for simple items. [BINARY_VERIFIED]",
    )
    armor_data: ItemArmorData | None = Field(
        default=None,
        description="Armor-specific data. Set for Armor.txt items. [BINARY_VERIFIED]",
    )

    # Quantity for stackable items (runes, keys, potions, etc.)
    # This is the RAW bit-field value - NOT the display quantity.
    # Simple items store a 9-bit field where bit 0 is an alignment/flag
    # bit (always 1 in D2R v105). The upper 8 bits carry the display
    # value. Use the ``display_quantity`` property for the user-visible
    # count.
    quantity: int = Field(
        default=0,
        description=(
            "Raw stack quantity as stored in the binary. "
            "For simple items, the display value is ``quantity >> 1``. "
            "For extended items, the raw value IS the display value. "
            "Prefer ``display_quantity`` for user-facing code."
        ),
    )

    # Bit-offset of the quantity field INSIDE source_data (item-relative).
    # Populated by the parser for any stackable item. Required by the writer
    # to patch quantities in place (feature/d2i-section5-writer).
    #   Simple items:   width=9, bit 0 = alignment/flag (always 1), bits 1-8 = display value
    #   Extended items: width=7, direct display value (Section 5 AdvancedStashStackables)
    # [BINARY_VERIFIED: 42 simple items across ModernSharedStashSoftCoreV2.d2i
    #  all have bit 0 = 1; raw >> 1 matches in-game quantities observed via
    #  the character screen.]
    quantity_bit_offset: int | None = Field(
        default=None,
        description="Bit offset of the quantity field inside source_data. None if no quantity.",
        exclude=True,
    )
    quantity_bit_width: int = Field(
        default=0,
        description="Width of the quantity field in bits (9 for simple, 7 for extended).",
        exclude=True,
    )

    @property
    def display_quantity(self) -> int:
        """Return the user-visible stack quantity.

        Simple items store a 9-bit raw value where bit 0 is an
        alignment/flag bit (always 1 in D2R v105). This property
        strips it so callers never need to know about the binary
        encoding.

        Extended items store the display value directly in a
        7-bit field - no conversion needed.

        Returns 0 for non-stackable items (quantity field absent).

        [BINARY_VERIFIED: 42 simple items, r10 raw=129->display=64,
         rvs raw=171->display=85, all matching in-game values.]
        """
        if self.quantity <= 0:
            return 0
        if self.flags.simple:
            return self.quantity >> 1
        return self.quantity

    # Total number of sockets (4 bits from binary, read when socketed flag is set).
    # This is the MAXIMUM socket count, not the filled count.
    total_nr_of_sockets: int = Field(
        default=0,
        description="Total socket count (4-bit field from binary). 0 for non-socketed items.",
    )

    # Automod ID: 11-bit row index (1-based) into automagic.txt.
    # Present for items with 'auto prefix' in game data (weapons, some misc).
    # Lookup: automagic.txt[automod_id - 1] -> mod properties.
    automod_id: int | None = Field(
        default=None,
        description="11-bit automod row index (1-based) into automagic.txt.",
    )

    # Properties placeholder - populated after ItemStatCost.txt is loaded
    magical_properties: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Magical property list. [SPEC_ONLY] - ItemStatCost.txt needed.",
    )
    set_bonus_properties: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Active per-item set bonus properties from the binary (decoded via bonus_mask). "
            "These are the aprop1-5 tiers from setitems.txt that are active for this item "
            "based on how many set pieces are equipped. Separated from magical_properties "
            "for correct quality-color display (blue=own, gold=set bonus). [BINARY_VERIFIED TC36]"
        ),
    )
    set_bonus_mask: int = Field(
        default=0,
        description=(
            "5-bit set bonus mask read from binary for Set items (quality=5). "
            "Bit i set = aprop tier (i+1) is active = i+2 set pieces equipped. "
            "Example: mask=0b00011 -> 2-piece and 3-piece tiers are active. [BINARY_VERIFIED TC36]"
        ),
    )

    # Superior quality type (3-bit value from QSD, quality=3 only).
    # Determines which Superior bonus the item has (ED%, durability%, both, etc.)
    superior_type: int | None = Field(
        default=None,
        description="Superior quality sub-type (3 bits). None for non-Superior items.",
    )

    # ── Quality-specific IDs (read from binary, used for name look-ups) ──────
    # These are set only when the item has the matching quality; otherwise None.
    # Look up display names via game_data.item_names.ItemNamesDatabase.

    unique_type_id: int | None = Field(
        default=None,
        description=(
            "12-bit unique-item-type ID (quality=7). "
            "Row index into uniqueitems.txt (0-based). [SPEC_ONLY]"
        ),
    )
    set_item_id: int | None = Field(
        default=None,
        description=(
            "12-bit set-item ID (quality=5). Row index into setitems.txt (0-based). [SPEC_ONLY]"
        ),
    )
    prefix_id: int | None = Field(
        default=None,
        description=(
            "11-bit magic-prefix ID (quality=4). "
            "Row index into magicprefix.txt (0-based). 0 = no prefix. [SPEC_ONLY]"
        ),
    )
    suffix_id: int | None = Field(
        default=None,
        description=(
            "11-bit magic-suffix ID (quality=4). "
            "Row index into magicsuffix.txt (0-based). 0 = no suffix. [SPEC_ONLY]"
        ),
    )
    rare_name_id1: int | None = Field(
        default=None,
        description=(
            "8-bit first-part rare name ID (quality=6/8). "
            "[SPEC_ONLY] - rareprefix.txt not available; display is TBD."
        ),
    )
    rare_name_id2: int | None = Field(
        default=None,
        description=(
            "8-bit second-part rare name ID (quality=6/8). "
            "[SPEC_ONLY] - raresuffix.txt not available; display is TBD."
        ),
    )
    rare_affix_ids: list[int] = Field(
        default_factory=list,
        description=(
            "Affix IDs for Rare/Crafted items (quality=6/8). "
            "Up to 6 standard 11-bit IDs + optional 7th 10-bit ID "
            "(Reimagined MISC items only). [SPEC_ONLY]"
        ),
    )
    rare_affix_slots: list[int] = Field(
        default_factory=list,
        description=(
            "Slot position (0..6) of each entry in ``rare_affix_ids`` - "
            "parallel list of the same length. The binary stores 6 "
            "(or 7 for Reimagined MISC) slots where slot N is reserved "
            "for a magicprefix.txt row if N is even and a magicsuffix.txt "
            "row if N is odd. Because empty slots are skipped in "
            "``rare_affix_ids``, the slot index is required to route each "
            "id into the correct table. [SPEC_ONLY]"
        ),
    )
    runeword_id: int | None = Field(
        default=None,
        description=(
            "12-bit runeword index (when flags.runeword=True). "
            "Row index into runes.txt (0-based). [SPEC_ONLY]"
        ),
    )
    runeword_properties: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Runeword-specific property list (second ISC prop block for runeword items). "
            "These are the mods granted by the runeword itself, separate from base item props. "
            "[BINARY_VERIFIED TC24 ltp] - captured via double-read with bit-scan verification. "
            "May be empty if ISC reading fails (e.g. stat save_bits mismatch in TC24 uhn)."
        ),
    )

    @property
    def is_simple(self) -> bool:
        """True if this is a simple/compact item with no extended data."""
        return self.flags.simple

    @property
    def location_name(self) -> str:
        """Human-readable location name."""

        return LOCATION_NAMES.get(self.flags.location_id, f"unknown({self.flags.location_id})")

    @property
    def panel_name(self) -> str:
        """Human-readable panel/storage name."""

        return PANEL_NAMES.get(self.flags.panel_id, f"unknown({self.flags.panel_id})")

    @property
    def slot_name(self) -> str:
        """Human-readable equipped slot name."""

        return SLOT_NAMES.get(self.flags.equipped_slot, f"slot({self.flags.equipped_slot})")

    @property
    def is_identified(self) -> bool:
        """True when the item has been identified in-game.

        GUIs and archivers should refuse to archive unidentified items -
        their affix / unique / set identity is not yet resolved, so
        stashing them permanently would lock the player out of the
        final roll. Archive-layer also enforces this, but checking here
        first gives callers a cleaner error path and lets them disable
        the "archive" UI affordance for unidentified items.

        Equivalent to ``item.flags.identified`` - exposed at the top
        level for discoverability and to centralise the semantic
        contract (if the underlying flag layout ever changes, this
        property insulates callers).
        """
        return bool(self.flags.identified)


class ParsedCharacter(BaseModel):
    """Top-level parsed character save file.

    Combines all sections of the D2S file into one model.
    """

    header: CharacterHeader
    stats: CharacterStats
    mercenary: MercenaryHeader | None = Field(
        default=None,
        description=(
            "Parsed mercenary header (name, type, experience, ...) read from "
            "bytes 161-174 of the D2S header. None if the character never "
            "hired a merc. [BV v105 TC49/TC55/TC56/TC63]"
        ),
    )
    items: list[ParsedItem] = Field(default_factory=list)
    merc_items: list[ParsedItem] = Field(
        default_factory=list,
        description=(
            "Mercenary-equipped items read from the 'jf' section (3rd JM marker "
            "inside it). Empty if the character has no merc or the merc carries "
            "nothing. [BV feature/merc-items TC49/TC55/TC56]"
        ),
    )

    # Writer support: byte offsets into the source file, set by parser.
    items_jm_byte_offset: int | None = Field(
        default=None,
        exclude=True,
        description="Byte offset of the 1st 'JM' item list marker in the source file.",
    )
    corpse_jm_byte_offset: int | None = Field(
        default=None,
        exclude=True,
        description="Byte offset of the 2nd 'JM' (corpse list) marker in the source file.",
    )
    merc_jm_byte_offset: int | None = Field(
        default=None,
        exclude=True,
        description=(
            "Byte offset of the merc 'JM' marker INSIDE the 'jf' section. "
            "None if the character has no merc (2-byte jf+kf with nothing between)."
        ),
    )
    trailing_item_bytes: bytes | None = Field(
        default=None,
        exclude=True,
        description=(
            "Raw bytes between the last successfully parsed item and the "
            "corpse JM marker that the parser could not decode. Preserved "
            "by the writer during rebuild to avoid data loss."
        ),
    )

    @property
    def class_name(self) -> str:
        """Human-readable class name."""
        return self.header.character_class_name

    def items_in_inventory(self) -> list[ParsedItem]:
        """All items stored in the personal inventory."""

        return [
            item
            for item in self.items
            if item.flags.location_id == LOCATION_STORED and item.flags.panel_id == PANEL_INVENTORY
        ]

    def items_in_belt(self) -> list[ParsedItem]:
        """All items in the belt slots."""

        return [item for item in self.items if item.flags.location_id == LOCATION_BELT]

    def items_equipped(self) -> list[ParsedItem]:
        """All equipped items."""

        return [item for item in self.items if item.flags.location_id == LOCATION_EQUIPPED]

    def items_in_cube(self) -> list[ParsedItem]:
        """All items stored inside the Horadric Cube.

        The Horadric Cube itself is a normal ``box`` item stored in the
        inventory or stash. Items INSIDE the cube use ``panel_id == 4``
        (PANEL_CUBE) with ``location_id == LOCATION_STORED``. This helper
        does NOT return the cube container itself - only its contents.
        """

        return [
            item
            for item in self.items
            if item.flags.location_id == LOCATION_STORED and item.flags.panel_id == PANEL_CUBE
        ]

    def items_in_stash_d2s(self) -> list[ParsedItem]:
        """All items stored in the character's *personal* stash tab.

        This is the stash page that lives inside the d2s file (not the
        shared stash tabs - those live in the d2i file and are parsed by
        :class:`D2IParser` separately).
        """

        return [
            item
            for item in self.items
            if item.flags.location_id == LOCATION_STORED and item.flags.panel_id == PANEL_STASH
        ]

    def merc_equipped(self) -> list[ParsedItem]:
        """Items the mercenary is currently wearing.

        In Reimagined, the merc's paperdoll supports every slot a hero
        has: Head, Amulet, Body Armor, Right Hand (weapon), Left Hand
        (shield or quiver, empty when the weapon is two-handed),
        Right Ring, Left Ring, Belt, Boots, Gloves.
        """

        return [item for item in self.merc_items if item.flags.location_id == LOCATION_EQUIPPED]

    def merc_socketed_children(self) -> list[ParsedItem]:
        """Socket children (gems / runes / jewels) of merc-equipped items.

        Since the socket_children refactor, children live nested inside
        their parent's ``socket_children`` list - they are NOT separate
        entries in ``merc_items``. This helper flattens them across all
        merc parents in parser order so existing callers that expected
        the old flat representation keep working.
        """
        return [child for parent in self.merc_items for child in parent.socket_children]

    def all_location_buckets(self) -> dict[str, list[ParsedItem]]:
        """Return a dict mapping every storage bucket to its items.

        Keys:
            ``inventory``            - personal character inventory (panel=1)
            ``equipped``             - items worn by the character
            ``belt``                 - belt slots
            ``cube``                 - items inside the Horadric Cube
            ``stash_d2s``            - the personal stash tab in the d2s
            ``merc_equipped``        - items worn by the mercenary
            ``merc_socketed``        - socket children of merc items

        Shared stash tabs (d2i file) are NOT included because they live in
        a separate file and are parsed by :class:`D2IParser`.
        """
        return {
            "inventory": self.items_in_inventory(),
            "equipped": self.items_equipped(),
            "belt": self.items_in_belt(),
            "cube": self.items_in_cube(),
            "stash_d2s": self.items_in_stash_d2s(),
            "merc_equipped": self.merc_equipped(),
            "merc_socketed": self.merc_socketed_children(),
        }

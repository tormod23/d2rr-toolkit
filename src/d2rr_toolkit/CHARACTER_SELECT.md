# Character Select Screen - CharacterHeader Fields

New fields on `CharacterHeader` for building a character-select screen.
Everything you need to display name, title, class, level, HC/SC status,
and alive/dead state.

## Quick Example

```python
from d2rr_toolkit.parsers.d2s_parser import D2SParser
from pathlib import Path

character = D2SParser(Path("MrLockhart.d2s")).parse()
h = character.header

# Example GUI output:
# "MrLockhart the Patriarch
#  Level 98 Warlock - Softcore"

print(f"{h.character_name} the {h.title}")
print(f"Level {h.level} {h.character_class_name}"
      f" - {'Hardcore' if h.is_hardcore else 'Softcore'}"
      f"{' (DEAD)' if h.is_dead else ''}")
```

## Available Fields

### Stored fields (populated directly by the parser)

| Field | Type | Description |
|---|---|---|
| `version` | `int` | D2S file version (105 for D2R Reimagined) |
| `file_size` | `int` | Total file size in bytes |
| `checksum` | `int` | CRC checksum of the file |
| `character_name` | `str` | Character name (in-game display name) |
| `character_class` | `int` | Class ID (0-7) |
| `character_class_name` | `str` | Human-readable class name |
| `level` | `int` | Character level (1-100) |
| `status_byte` | `int` | Raw status byte at D2S offset 0x14 |
| `is_hardcore` | `bool` | `True` if Hardcore character |
| `died_flag` | `bool` | Raw died bit (**not what you want to display!**) |
| `is_expansion` | `bool` | Always `True` in D2R v105 |
| `progression` | `int` | 0-15, difficulty completion byte |

### Computed properties (derived automatically)

| Property | Type | Description |
|---|---|---|
| `is_dead` | `bool` | `True` **only** for HC characters that have died (permanently dead) |
| `highest_difficulty_completed` | `int` | `0`=none, `1`=Normal, `2`=Nightmare, `3`=Hell |
| `gender` | `"male"\|"female"` | Derived from class ID |
| `title` | `str` | Display title (empty string if none) |

## Important: `is_dead` vs `died_flag`

- **Use `is_dead`** for your GUI. It is only `True` when an HC character is permanently dead.
- **Avoid `died_flag` directly.** It's the raw bit from the file and is also set for
  Softcore characters that have died at any point in the past (they respawned and can still
  be played - they just "had a death" once).

```python
# [OK] Correct - only HC permadead shows as dead
if h.is_dead:
    show_dead_overlay()

# [NO] Wrong - would also mark SC chars that died once as "dead"
if h.died_flag:
    show_dead_overlay()
```

## Gender -> Title Mapping

Gender is derived from class ID, not stored in the save file.

| Class ID | Class Name | Gender | Patriarch/Matriarch |
|---|---|---|---|
| 0 | Amazon | female | Matriarch |
| 1 | Sorceress | female | Matriarch |
| 2 | Necromancer | male | Patriarch |
| 3 | Paladin | male | Patriarch |
| 4 | Barbarian | male | Patriarch |
| 5 | Druid | male | Patriarch |
| 6 | Assassin | female | Matriarch |
| 7 | Warlock (Reimagined) | male | Patriarch |

## Title Mapping

### Softcore Titles

| Progression | Highest Diff | Title |
|---|---|---|
| 0-4 | none | `""` (empty) |
| 5-9 | Normal | `"Slayer"` |
| 10-14 | Nightmare | `"Champion"` |
| 15 | Hell | `"Patriarch"` (male) / `"Matriarch"` (female) |

### Hardcore Titles (gender-neutral)

| Progression | Highest Diff | Title |
|---|---|---|
| 0-4 | none | `""` (empty) |
| 5-9 | Normal | `"Destroyer"` |
| 10-14 | Nightmare | `"Conqueror"` |
| 15 | Hell | `"Guardian"` |

## Full Example: Rendering a Character Row

```python
from d2rr_toolkit.parsers.d2s_parser import D2SParser
from pathlib import Path

def format_character_row(d2s_path: Path) -> dict:
    """Return data needed to render one character in the select screen."""
    char = D2SParser(d2s_path).parse()
    h = char.header

    # Display name with optional title
    if h.title:
        display_name = f"{h.character_name} the {h.title}"
    else:
        display_name = h.character_name

    # Mode label
    if h.is_hardcore:
        mode = "Hardcore (DEAD)" if h.is_dead else "Hardcore"
    else:
        mode = "Softcore"

    return {
        "name": display_name,
        "level": h.level,
        "class": h.character_class_name,
        "mode": mode,
        "gender": h.gender,
        "is_dead": h.is_dead,
        "is_hardcore": h.is_hardcore,
        "difficulty_completed": h.highest_difficulty_completed,
        # Useful for icons / sorting / filtering:
        "character_class": h.character_class,  # 0-7
        "progression": h.progression,          # 0-15
    }
```

## Typical GUI States

| Character | `title` | `is_hardcore` | `is_dead` | Display |
|---|---|---|---|---|
| Fresh SC level 1 | `""` | `False` | `False` | "NewChar - Lvl 1 Paladin - Softcore" |
| SC Hell Sorc | `"Matriarch"` | `False` | `False` | "MySorc the Matriarch - Lvl 92 Sorceress - Softcore" |
| SC Hell Warlock | `"Patriarch"` | `False` | `False` | "MrLockhart the Patriarch - Lvl 98 Warlock - Softcore" |
| HC alive level 1 | `""` | `True` | `False` | "HCLives - Lvl 1 Warlock - Hardcore" |
| HC dead level 1 | `""` | `True` | `True` | "HCDied - Lvl 1 Warlock - Hardcore (DEAD)" |
| HC Hell Barb | `"Guardian"` | `True` | `False` | "BigBarb the Guardian - Lvl 95 Barbarian - Hardcore" |
| HC Hell Barb (dead) | `"Guardian"` | `True` | `True` | "BigBarb the Guardian - Lvl 95 Barbarian - Hardcore (DEAD)" |

## Style Hints

- Dead HC characters: typically rendered **greyed out** or with a **skull icon**
- Hardcore characters: typically rendered with a **red tint** or **HC badge**
- Titles: shown in a lighter/smaller font under the name, or after "the"
- Class icons: use `character_class` (0-7) for reliable icon lookup

## Backend Verification

All fields are `[BINARY_VERIFIED]` against 7 real D2S files:
- `HCLives`, `HCDied` (HC Warlock level 1)
- `MrLockhart` (SC Warlock 98, Patriarch)
- `FrozenOrbHydra`, `VikingBarbie` (SC Sorceress 100, Matriarch)
- `StraFoHdin` (SC Paladin 97, Patriarch)
- `AAAAA` (SC Warlock test copy)

No manual verification needed - just import and use.


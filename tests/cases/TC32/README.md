# TC32 - Spike Thorn - Unique Shield Isolation (.d2s)

## Summary

This scenario provides a .d2s character file with a single Spike Thorn (Unique Blade Barrier) in the inventory. It serves as the definitive reference parse for the same item that appears in TC06 and TC31 (shared stash).

- **File:** TestSorc.d2s
- **Mod:** D2R Reimagined
- **Character:** TestSorc (Sorceress, Level 1)
- **Goal:** Verify correct parsing of a Unique socketed shield with custom graphics, including all magical properties, in the proven .d2s parsing path.

## Character Overview

- **Name:** TestSorc
- **Class:** Sorceress
- **Level:** 1
- **Gold:** 0

## Inventory Contents

### Inventory
- **Spike Thorn** - Position: (0,0)

### Equipped / Stash / Cube / Belt
- *(all empty)*

## Item Details

1. **Spike Thorn**
   - **Base Type:** Blade Barrier [E]
   - **Quality:** Unique
   - **Item Level:** 99
   - **Custom Graphics:** Yes (visible unique appearance)
   - **Defense:** 410
   - **Chance To Block:** 45%
   - **Durability:** 41 Of 83
   - **Required Strength:** 118
   - **Required Level:** 80
   - **Sockets:** 3 (empty)
   - **Properties:**
     - Level 29 Thorns Aura When Equipped
     - +30% Faster Hit Recovery
     - +150% Enhanced Defense
     - +17% Physical Damage Reduction
     - Attacker Takes Damage Of 3 (Based On Character Level)

## CLI Reference (Machine Readable)

```yaml
expected_values:
  file_type: "d2s_character"
  mod: "D2R Reimagined"
  character:
    name: "TestSorc"
    class: "Sorceress"
    level: 1
    gold: 0

  items:
    - name: "Spike Thorn"
      base_type: "Blade Barrier [E]"
      location: "inventory"
      pos: [0, 0]
      quality: "unique"
      item_level: 99
      custom_graphics: true
      defense: 410
      chance_to_block: 45
      durability_current: 41
      durability_max: 83
      required_strength: 118
      required_level: 80
      sockets: 3
      socket_contents: []
      properties:
        - "Level 29 Thorns Aura When Equipped"
        - "+30% Faster Hit Recovery"
        - "+150% Enhanced Defense"
        - "+17% Physical Damage Reduction"
        - "Attacker Takes Damage Of 3"
```

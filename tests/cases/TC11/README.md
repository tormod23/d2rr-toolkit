# TC11 - Socketed Items

## Summary

Targeted test case to verify parsing of socketed items. Contains two identical
Studded Leather armors - one with an empty socket, one with a Diamond socketed
into it - plus three loose Diamonds in the inventory.

- **File:** TestWarlock.d2s
- **Character:** Warlock (same as TC03), Level 12
- **Goal:** Verify correct parsing of socketed items, including the parent-child
  relationship between a socketed armor and its inserted gem.

## Character Profile

Same as TC03:
- **Name:** TestWarlock
- **Class:** Warlock
- **Level:** 12
- **Experience:** 90,180
- **Gold (Inventory):** 67,655
- **Gold (Stash):** 14,545
- **Stat Points Remaining:** 55
- **Skill Points Remaining:** 11

## Items

### Equipped Items
ALL equipment slots are **empty**.

### Inventory Grid (10x8)

```
   C0    C1    C2    C3    C4    C5    C6    C7    ...
R0  [Di]  [SL ] [SL ] [Di]  [SL ] [SL ] [Di]  .
R1   .    [SL ] [SL ]  .    [SL ] [SL ]  .     .
R2   .    [SL ] [SL ]  .    [SL ] [SL ]  .     .
R3   .     .     .     .     .     .     .     .
```

- **[Di]**: Diamond (1x1)
- **[SL]**: Studded Leather (2x3)

### Belt, Stash
Both completely empty.

## Item Details

### Diamond at (0,0)
- **Quality:** Normal
- **Position:** Inventory (0,0)

### Studded Leather at (1,0) - 1 empty socket
- **Quality:** Normal or Superior (whatever the game assigned)
- **Position:** Inventory (1,0)
- **Size:** 2x3
- **Sockets:** 1 total, 0 filled (empty)

### Diamond at (3,0)
- **Quality:** Normal
- **Position:** Inventory (3,0)

### Studded Leather at (4,0) - 1 filled socket
- **Quality:** Normal or Superior (whatever the game assigned)
- **Position:** Inventory (4,0)
- **Size:** 2x3
- **Sockets:** 1 total, 1 filled
- **Socket contents:** Diamond

### Diamond at (6,0)
- **Quality:** Normal
- **Position:** Inventory (6,0)

### Diamond inside socket of Studded Leather at (4,0)
- **Quality:** Normal
- This Diamond is socketed into the armor above. It is not a free-standing
  inventory item - it exists as a child of the Studded Leather at (4,0).

## CLI Reference (Machine Readable)

```yaml
expected_values:
  character:
    name: "TestWarlock"
    class: "Warlock"
    level: 12
  inventory_items:
    - name: "Diamond"
      pos: [0, 0]
    - name: "Studded Leather"
      pos: [1, 0]
      sockets_total: 1
      sockets_filled: 0
    - name: "Diamond"
      pos: [3, 0]
    - name: "Studded Leather"
      pos: [4, 0]
      sockets_total: 1
      sockets_filled: 1
      socket_contents:
        - name: "Diamond"
    - name: "Diamond"
      pos: [6, 0]
  belt_empty: true
  stash_empty: true
  equipped_empty: true
```


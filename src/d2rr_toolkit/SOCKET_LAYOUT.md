# Socket Layout & Fill Order

How the toolkit maps an item's socket count to the exact grid
positions and fill order that D2R Reimagined uses in-game.  Lives in
`d2rr_toolkit.display.item_display`; the single public entry point is

```python
from d2rr_toolkit.display.item_display import get_socket_positions
positions: list[SocketPosition] = get_socket_positions(inv_w, inv_h, num_sockets)
```

`SocketPosition.x` and `.y` are floats in **cell-unit coordinates**
(0..inv_w, 0..inv_h) - the GUI multiplies by its per-cell pixel size
and adds half-cell offsets to centre the socket overlay.

## Two layers - grid layout + fill order

A socket rendering has two independent questions:

1. **Layout**   - *where* on the item grid do sockets sit?
   (e.g. "2x2 with 3 sockets -> top row of 2, one centred below")
2. **Fill order** - *which slot index* does each runeword rune or
   gem socket-child go into?
   (e.g. "Spirit in a 2x3 shield: Tal=TL, Thul=BR, Ort=BL, Amn=TR")

The toolkit models these separately:

```python
_SOCKET_ROW_COUNTS[(inv_w, inv_h, num_sockets)]  # -> [row0_count, row1_count, ...]
_SOCKET_FILL_ORDER[(inv_w, inv_h, num_sockets)]  # -> permutation of [0..n-1]
```

`get_socket_positions` builds the reading-order positions from the
row counts, then permutes them according to the fill order.

## Layout - row count tables

`_SOCKET_ROW_COUNTS` maps `(inv_w, inv_h, num_sockets)` to a list of
per-row socket counts.  A zero entry produces an empty row that
advances the y-coordinate without placing a socket - this is how the
`(2, 4, 2)` case draws a visible vertical gap between its two
sockets.

| `(w, h, n)` | Rows | In-game visual |
|---|---|---|
| `(2, 2, 3)` | `[2, 1]` | `oo / o` (TL, TR, centred below) |
| `(2, 2, 4)` | `[2, 2]` | `oo / oo` |
| `(2, 3, 4)` | `[2, 0, 2]` | `oo / _ / oo` (empty middle row for spacing) |
| `(2, 3, 5)` | `[2, 1, 2]` | `oo / o / oo` |
| `(2, 3, 6)` | `[2, 2, 2]` | `oo / oo / oo` |
| `(2, 4, 2)` | `[1, 0, 1]` | `o / _ / o` (outer positions only) |
| `(2, 4, 3)` | `[1, 1, 1]` | `o / o / o` (vertical stack) |
| `(2, 4, 4)` | `[1, 1, 1, 1]` | `o / o / o / o` (vertical, NOT a 2x2 Z-pattern) |
| `(2, 4, 5)` | `[2, 1, 2]` | `oo / o / oo` (centred vertically) |
| `(2, 4, 6)` | `[2, 2, 2]` | `oo / oo / oo` (centred vertically) |

The `(2, 4, 4)` case is worth calling out: it is **not** a 2x2 cluster
despite having an even socket count.  In-game, 4 sockets on a
`2 wide * 4 tall` item stack vertically in a single column.

## Fill order - permutation tables

`_SOCKET_FILL_ORDER` maps the same key to a permutation of the
reading-order position indices.  An entry of `[0, 3, 2, 1]` means
"the first rune goes to reading-index 0 (top-left), the second to
reading-index 3 (bottom-right), ...".

```python
_SOCKET_FILL_ORDER: dict[tuple[int, int, int], list[int]] = {
    # Z-pattern (4 corners): TL, BR, BL, TR
    (2, 2, 4): [0, 3, 2, 1],
    (2, 3, 4): [0, 3, 2, 1],

    # 5-socket: middle first, then 4 corners in Z-pattern
    (2, 3, 5): [2, 0, 4, 3, 1],
    (2, 4, 5): [2, 0, 4, 3, 1],

    # 6-socket: column-major (TL, CL, BL, TR, CR, BR)
    (2, 3, 6): [0, 2, 4, 1, 3, 5],
    (2, 4, 6): [0, 2, 4, 1, 3, 5],
}
```

Tuples without an entry use the identity permutation - reading
order (top-to-bottom, left-to-right) matches the game for:

- 1-socket items (trivially)
- Vertical stacks: `(1, N, k)` and `(2, N, k)` with k <= 3
- `(2, 2, 3)` -> TL, TR, bottom-centre
- `(2, 4, 4)` -> top-to-bottom

## Defensive fallback

`get_socket_positions` rejects malformed `_SOCKET_FILL_ORDER`
entries silently: wrong length, out-of-range indices, or duplicate
entries all cause the function to emit reading-order positions
instead.  A typo in the table can therefore never crash the GUI or
blank out sockets - the worst-case degradation is "sockets render
in reading order", which is still a valid layout.

## Verification table

Every tuple with a custom layout or fill order has been confirmed
against live D2R Reimagined gameplay:

| `(w, h, n)` | Layout | Fill order | Worked example |
|---|---|---|---|
| `(2, 2, 3)` | `oo / o` | TL, TR, BC | - |
| `(2, 2, 4)` | `oo / oo` | TL, BR, BL, TR | - |
| `(2, 3, 4)` | `oo / _ / oo` | TL, BR, BL, TR | Spirit Monarch (Tal/Thul/Ort/Amn) |
| `(2, 3, 5)` | `oo / o / oo` | MC, TL, BR, BL, TR | - |
| `(2, 3, 6)` | `oo / oo / oo` | TL, CL, BL, TR, CR, BR | - |
| `(2, 4, 4)` | `o / o / o / o` | reading order | - |
| `(2, 4, 5)` | `oo / o / oo` (centred) | MC, TL, BR, BL, TR | - |
| `(2, 4, 6)` | `oo / oo / oo` (centred) | TL, CL, BL, TR, CR, BR | - |

### Spirit Monarch worked example

A 2x3 Shield with the 4-rune Spirit runeword (Tal, Thul, Ort, Amn)
renders as:

```
[Tal]  [Amn]      slot indices:  (1)  (4)
[Ort]  [Thul]                    (3)  (2)
```

The runes are written into the save file in runeword order
(Tal -> Thul -> Ort -> Amn) but the game displays them at the
Z-pattern positions via the fill-order permutation.

## Test coverage

`tests/test_socket_layout.py` - 135 checks:

- §4 Horizontal centring (row-count correctness)
- §12 Every user-verified `(w, h, n)` tuple produces the expected
  position list
- §12b Explicit fill-order regression cases - one per verified
  tuple, each asserting the full expected `[(x, y), ...]`
- §12c Self-consistency: every `_SOCKET_FILL_ORDER` entry has the
  right length, is a valid permutation of `0..n-1`, and has a
  matching `_SOCKET_ROW_COUNTS` entry.

## Consumers

All callers share the same public API and automatically inherit
correct layout + fill order without any local bookkeeping:

- `d2rr_toolkit.cli` inspect rendering (per-item socket overlay)
- the D2RR ToolkitGUI tooltip renderer
- the bulk sprite / socket overlay compositor

`SocketPosition` dataclass fields (`x`, `y` floats) and the return
shape `list[SocketPosition]` are the stable public contract - the
internal tables can grow to cover new layout shapes without any
call-site changes.

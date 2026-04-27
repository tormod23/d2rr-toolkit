# TC73 - D2I empty-tab corruption regression

(See also TC74 in `tests/test_parser_prerequisites.py` - parser
prerequisites, auto-load, orphan-extras, rare-MISC 7-slot retry
fallback. Share the fixtures listed below.)



Captures the real-world corruption observed in `ModernSharedStashSoftCoreV2.d2i`
after a chain of archive operations on 2026-04-19.

## Fixtures

- `pre_empty_tab4.d2i` (1601 bytes) - **last good backup**. Tab 4 holds
  exactly one parsed root item whose raw section region ends in a single
  `0x00` padding byte (inter-item padding that the parser never returns).
- `corrupted_original.d2i` (1579 bytes) - **actual broken output** written
  by the legacy splice path. Tab 2 AND tab 4 are "empty" (`jm_count==0`)
  but their `section_size` is 69 instead of the canonical 68 because the
  writer appended the original tail byte even when the parsed item list
  was emptied.

## What the bug did

Running `writer._tab_items[4].clear(); writer.build()` on the 1601-byte
backup produced a byte-identical reproduction of the broken file (agent
forensic report, 2026-04-20). D2R refuses to load any character from the
save directory while such a file is present.

## What the test pins

`tests/test_d2i_empty_tab_corruption.py`:

1. The fixed writer produces a canonical 68-byte empty section when the
   last item is removed from tab 4 (no phantom `0x00` byte).
2. The writer's post-build self-check raises `D2IWriterIntegrityError`
   if any section ends up with `jm_count=0, section_size>68`.
3. `archive._verify_d2i_on_disk` detects the broken file and rolls back
   to the pre-write backup.
4. Full round-trip of the pre_empty_tab4 -> empty-tab-4 operation parses
   back to the expected item layout.

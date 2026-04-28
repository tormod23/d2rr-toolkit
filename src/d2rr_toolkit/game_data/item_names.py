"""
Multilingual item display-name lookups.

Loads and cross-references item-data txt files plus the string JSON files
in excel/reimagined/strings/ so that every quality-specific item ID read
from the binary can be resolved to a human-readable display name.

## Sources

| Quality  | ID bits | txt file               | string file             |
|----------|---------|------------------------|-------------------------|
| Unique   | 12-bit  | uniqueitems.txt        | item-names.json         |
| Set      | 12-bit  | setitems.txt           | item-names.json         |
| Magic    | 11+11   | magicprefix/suffix.txt | item-nameaffixes.json   |
| Rare/Crafted | 8+8 | rareprefix/suffix.txt  | item-nameaffixes.json * |
| Runeword | 12-bit  | runes.txt              | item-runes.json         |
| Any      | -       | armor/weapons/misc.txt | item-names.json (base)  |

\\* Same indirection as magicprefix/suffix: the ``name`` column is a
string-table key, not display text. See "Rare item names" below.

## Lookup chain (unique example)
  binary 12-bit ID -> row index 0 in uniqueitems.txt -> index column = "The Gnasher"
  -> item-names.json Key=="The Gnasher" -> enUS value = "The Gnasher"

## Row indexing
All txt tables are 0-indexed from the first DATA row (skip header):
  row 0 = first data row = binary ID 0

## Rare item names
rareprefix.txt and raresuffix.txt are NOT shipped by D2R Reimagined.
They are read from excel/original/ as a fallback.  The `name` column
contains the **string-table key**, not the display text - the same
indirection pattern as magicprefix/magicsuffix. For most rows the
key happens to coincide with the enUS display string ("Beast", "Eagle"
etc.), so a raw passthrough produces the right output. Reimagined
however has ~160 rows where the key differs:

  * Pseudo-inflected keys: GhoulRI -> Ghoul, PlagueRI -> Plague,
    Wraithra -> Wraith, Fiendra -> Fiend, Empyrion -> Empyrian
  * Completely different target: Holocaust -> Armageddon
  * Lowercase-suffix keys that need proper casing: bite -> Bite,
    razor -> Razor, ...

Resolution path (mirrors get_prefix_name / get_suffix_name):

  rare_name_id1 (8-bit) -> rareprefix.txt row -> key -> StringsDatabase
                                             -> display (e.g. "Ghoul")
  rare_name_id2 (8-bit) -> raresuffix.txt row -> key -> StringsDatabase
                                             -> display (e.g. "Bite")
  Display name: "<prefix> <suffix>" (e.g. "Ghoul Bite")

Fallback: if the StringsDatabase has no entry for the key (unlikely in
practice, but possible for future mod revisions), the raw key is used
with capitalize() applied so lowercase suffix tables still render.

## Color-code stripping
D2R string entries contain in-game color markup (ÿcX sequences).  These
are stripped before returning display strings to the caller.

[SOURCE: excel/reimagined/ and excel/reimagined/strings/ for most files;
 excel/original/ for rareprefix.txt + raresuffix.txt - always read at
 runtime, never cached as hardcoded constants]
"""

import csv
import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from d2rr_toolkit.meta.source_versions import SourceVersions
from d2rr_toolkit.adapters.casc import (
    get_game_data_reader,
    list_game_data_files,
    read_game_data_bytes,
    read_game_data_rows,
)
from d2rr_toolkit.meta import cached_load

logger = logging.getLogger(__name__)

# Regex for D2R in-game color-markup sequences (e.g. ÿc1, ÿc0, ÿc;)
_COLOR_CODE_RE = re.compile(r"[ÿ\xff]c.", re.DOTALL)


def _strip_color_codes(text: str) -> str:
    """Remove ÿcX color-markup sequences from a D2R string."""
    return _COLOR_CODE_RE.sub("", text).strip()


# ──────────────────────────────────────────────────────────────────────────────
# StringsDatabase - loads all JSON string files from strings/ directory
# ──────────────────────────────────────────────────────────────────────────────


class StringsDatabase:
    """Indexed lookup over all JSON string files in excel/reimagined/strings/.

    Each JSON file is an array of objects with fields:
        { "id": <int>, "Key": "<str>", "enUS": "<str>", "deDE": "<str>", ... }

    Entries are indexed by their ``Key`` field for fast O(1) look-ups.
    Multiple files may be loaded; later files override earlier ones on
    duplicate keys (in practice keys are unique across files).

    Supported language codes:
        enUS, zhTW, deDE, esES, frFR, itIT, koKR, plPL, esMX, jaJP,
        ptBR, ruRU, zhCN
    """

    SUPPORTED_LANGS: tuple[str, ...] = (
        "enUS",
        "zhTW",
        "deDE",
        "esES",
        "frFR",
        "itIT",
        "koKR",
        "plPL",
        "esMX",
        "jaJP",
        "ptBR",
        "ruRU",
        "zhCN",
    )

    def __init__(self) -> None:
        # Key -> {lang: text}
        self._by_key: dict[str, dict[str, str]] = {}
        self._loaded = False

    def load_json_bytes(self, raw: bytes, *, source: str = "<bytes>") -> None:
        """Merge a single strings-JSON payload into the database.

        Used by the Iron-Rule load path which hands over raw bytes read
        through :class:`CASCReader`. Later calls override earlier keys
        on collision - the caller decides iteration order when both
        mod-disk and CASC JSONs are involved (the mod entry should come
        second so it wins).
        """
        text = raw.decode("utf-8-sig", errors="replace")
        try:
            entries = json.loads(text)
        except (ValueError, json.JSONDecodeError):
            # Reimagined ships some strings JSON files with trailing
            # commas (e.g. skills.json line 40239) that the stdlib
            # JSON parser rejects.  Strip ``,}`` and ``,]`` runs and
            # retry - these are always the benign kind of trailing
            # comma produced by machine-generated exports, not a
            # semantic ambiguity.

            cleaned = re.sub(r",(\s*[}\]])", r"\1", text)
            try:
                entries = json.loads(cleaned)
            except (ValueError, json.JSONDecodeError) as e2:
                logger.error(
                    "Cannot parse strings JSON %s even after trailing-comma cleanup: %s",
                    source,
                    e2,
                )
                return
        if not isinstance(entries, list):
            logger.warning(
                "Unexpected JSON structure in %s (expected array)",
                source,
            )
            return
        for entry in entries:
            key = entry.get("Key")
            if not key:
                continue
            lang_map: dict[str, str] = {}
            for lang in self.SUPPORTED_LANGS:
                val = entry.get(lang)
                if val:
                    lang_map[lang] = _strip_color_codes(str(val))
            if lang_map:
                self._by_key[key] = lang_map
        self._loaded = True

    def is_loaded(self) -> bool:
        """Return True if the database has been populated."""
        return self._loaded

    def get(self, key: str, lang: str = "enUS") -> str | None:
        """Return the localised text for key in the requested language.

        Falls back to enUS if the requested language is not available.
        Returns None if the key is not found at all.

        Args:
            key:  String table key (e.g. "The Gnasher", "Friendship").
            lang: BCP-47-style language code (e.g. "enUS", "deDE").

        Returns:
            Localised display string, or None.
        """
        entry = self._by_key.get(key)
        if entry is None:
            return None
        return entry.get(lang) or entry.get("enUS")

    def __len__(self) -> int:
        return len(self._by_key)


# ──────────────────────────────────────────────────────────────────────────────
# ItemNamesDatabase - loads txt tables and provides display-name look-ups
# ──────────────────────────────────────────────────────────────────────────────


class ItemNamesDatabase:
    """Maps quality-specific binary IDs to human-readable item display names.

    After calling load(), the database supports these look-ups:

        get_unique_name(unique_type_id, lang) -> "Jalal's Mane"
        get_set_item_name(set_item_id, lang)  -> "Sigon's Visor"
        get_prefix_name(prefix_id, lang)      -> "Jagged"
        get_suffix_name(suffix_id, lang)      -> "of Defense"
        get_runeword_name(runeword_id, lang)  -> "Grief"
        get_base_item_name(item_code, lang)   -> "Antlers"

    Unique and set item IDs are looked up by the ``*ID`` column in their
    respective txt files (NOT by row index - Reimagined has gaps where
    row index != ``*ID``).  Magic prefix/suffix use row index (no ``*ID``
    column in those files).
    """

    def __init__(self) -> None:
        self._strings = StringsDatabase()

        # *ID-keyed lookup tables: dict[int, str]
        # Key is the *ID column value from the txt file (NOT the row index).
        # Reimagined txt files have gaps where row index != *ID.
        self._unique_keys: dict[int, str] = {}  # *ID -> uniqueitems.txt `index`
        self._set_item_keys: dict[int, str] = {}  # *ID -> setitems.txt `index`
        self._prefix_names: list[str] = []  # magicprefix.txt `name` column (EN)
        self._prefix_lvl_reqs: list[int] = []  # magicprefix.txt `levelreq` column
        self._prefix_transformcolors: list[str] = []  # magicprefix.txt `transformcolor` column
        self._suffix_names: list[str] = []  # magicsuffix.txt `name` column (EN)
        self._suffix_lvl_reqs: list[int] = []  # magicsuffix.txt `levelreq` column
        self._suffix_transformcolors: list[str] = []  # magicsuffix.txt `transformcolor` column
        self._runeword_keys: list[str] = []  # runes.txt `Name` column
        # Recipe-based lookup: rune_codes tuple -> name key.
        # E.g. ("r24", "r24", "r24", "r24") -> "Glory"
        # Used to resolve runeword names independent of stale binary row indices
        # (version-drift workaround: Reimagined adds new runewords over time,
        # shifting row positions while binary stores old indices).
        self._runeword_recipe: dict[tuple[str, ...], str] = {}
        self._base_names: dict[str, str] = {}  # item_code -> string key

        # Unique item level requirements: *ID -> lvl req from uniqueitems.txt.
        self._unique_lvl_req: dict[int, int] = {}
        # Unique item invfile overrides: *ID -> invfile from uniqueitems.txt.
        self._unique_invfile: dict[int, str] = {}
        # Unique item invtransform: *ID -> color transform code (e.g. "cgrn", "bwht").
        self._unique_invtransform: dict[int, str] = {}
        # Unique item carry1 restriction: *ID -> carry1 group value.
        # Items with the same non-empty carry1 value can only be carried once
        # per character (inventory + personal stash). Enforced by game engine
        # and D2S writer validation.
        self._unique_carry1: dict[int, str] = {}

        # Binary UID -> *ID conversion tables.
        # uniqueitems.txt / setitems.txt contain separator rows ("Expansion",
        # "Armor", "Warlock Class Pack", ...) that have no *ID.  The game binary
        # stores a value that equals the row index with ONLY the "Expansion"
        # separator skipped (GoMule's searchByID logic).  For vanilla D2 items
        # this equals the *ID, but Reimagined adds extra separator rows that
        # create a growing offset between binary value and *ID.
        # These dicts map: binary_value -> *ID  for fast O(1) lookup.
        self._unique_binary_to_star_id: dict[int, int] = {}
        self._set_binary_to_star_id: dict[int, int] = {}

        # Rare/Crafted item name parts - from rareprefix.txt + raresuffix.txt
        # D2R Reimagined does not ship these; loaded from excel/original/ instead.
        self._rareprefix_names: list[str] = []  # 8-bit rare_name_id1 -> prefix part
        self._raresuffix_names: list[str] = []  # 8-bit rare_name_id2 -> suffix part

        self._loaded = False

    # ── Loading ────────────────────────────────────────────────────────────────

    def load(self) -> None:
        """Load all item-name tables via the Iron Rule.

        Every tab-delimited file is served through
        :class:`d2rr_toolkit.adapters.casc.CASCReader`: Reimagined mod
        install first, D2R Resurrected CASC second. No arguments - the
        shared singleton already knows where both sources live.
        """

        # ── Strings: merge mod + CASC JSONs ─────────────────────────────────
        for casc_path in list_game_data_files("data:data/local/lng/strings/*.json"):
            raw = read_game_data_bytes(casc_path)
            if raw is None:
                continue
            self._strings.load_json_bytes(raw, source=casc_path)

        # ── Per-file tabular loads ─────────────────────────────────────────
        self._load_uniqueitems_rows(read_game_data_rows("data:data/global/excel/uniqueitems.txt"))
        self._load_setitems_rows(read_game_data_rows("data:data/global/excel/setitems.txt"))
        self._load_magicaffixes_rows(
            read_game_data_rows("data:data/global/excel/magicprefix.txt"),
            read_game_data_rows("data:data/global/excel/magicsuffix.txt"),
        )
        self._load_runes_rows(read_game_data_rows("data:data/global/excel/runes.txt"))
        for fname in ("armor.txt", "weapons.txt", "misc.txt"):
            for row in read_game_data_rows(f"data:data/global/excel/{fname}"):
                code = row.get("code", "").strip()
                name = row.get("name", "").strip()
                if code and name:
                    self._base_names[code] = name

        # Rare-affix tables live in vanilla CASC (Reimagined ships no
        # override); Iron Rule handles it transparently via the same read.
        self._rareprefix_names = [
            (r.get("name") or "").strip()
            for r in read_game_data_rows("data:data/global/excel/rareprefix.txt")
            if (r.get("name") or "").strip()
        ]
        self._raresuffix_names = [
            (r.get("name") or "").strip()
            for r in read_game_data_rows("data:data/global/excel/raresuffix.txt")
            if (r.get("name") or "").strip()
        ]

        self._loaded = True
        reader = get_game_data_reader()
        logger.info(
            "ItemNamesDatabase loaded (Iron Rule): %d unique | %d set | "
            "%d prefix | %d suffix | %d runewords | %d base codes | "
            "%d strings | %d rareprefix | %d raresuffix (mod_dir=%s)",
            len(self._unique_keys),
            len(self._set_item_keys),
            len(self._prefix_names),
            len(self._suffix_names),
            len(self._runeword_keys),
            len(self._base_names),
            len(self._strings),
            len(self._rareprefix_names),
            len(self._raresuffix_names),
            reader.mod_dir,
        )

    def _load_uniqueitems(self, path: Path) -> None:
        """Populate ``self._unique_names`` from uniqueitems.txt rows."""

        if not path.exists():
            logger.warning("uniqueitems.txt not found at %s", path)
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                rows = list(csv.DictReader(f, delimiter="\t"))
        except (OSError, KeyError) as e:
            logger.error("Cannot read %s: %s", path, e)
            return
        self._load_uniqueitems_rows(rows)

    def _load_uniqueitems_rows(self, rows: list[dict[str, str]]) -> None:
        """Populate unique-item lookup structures from pre-parsed rows."""
        result: dict[int, str] = {}
        # Track row indices to build binary->*ID mapping.
        # The file has separator rows (no *ID); the "Expansion" row
        # is the only one the game/GoMule skips when computing the
        # binary value stored in save files.
        expansion_row: int | None = None
        tracked_rows: list[tuple[int, int, str]] = []  # (file_row, *ID, key)
        for file_row, row in enumerate(rows):
            key = row.get("index", "").strip()
            star_id = row.get("*ID", "").strip()
            if key == "Expansion" and not star_id.isdigit():
                expansion_row = file_row
            elif key and star_id.isdigit():
                sid = int(star_id)
                result[sid] = key
                tracked_rows.append((file_row, sid, key))
                # Load lvl req and invfile for unique items
                lvl_req_str = row.get("lvl req", "").strip()
                if lvl_req_str:
                    try:
                        self._unique_lvl_req[sid] = int(lvl_req_str)
                    except ValueError:
                        pass
                invfile = row.get("invfile", "").strip()
                if invfile:
                    self._unique_invfile[sid] = invfile
                invtransform = row.get("invtransform", "").strip()
                if invtransform:
                    self._unique_invtransform[sid] = invtransform
                carry1 = row.get("carry1", "").strip()
                if carry1:
                    self._unique_carry1[sid] = carry1
        self._unique_keys = result

        # Build binary_value -> *ID mapping.
        # binary_value = file_row  if file_row < expansion_row
        #              = file_row - 1  if file_row > expansion_row
        binary_map: dict[int, int] = {}
        for fr, sid, _key in tracked_rows:
            if expansion_row is not None and fr > expansion_row:
                binary_val = fr - 1
            else:
                binary_val = fr
            binary_map[binary_val] = sid
        self._unique_binary_to_star_id = binary_map
        logger.debug(
            "uniqueitems binary->*ID map: %d entries, expansion at row %s",
            len(binary_map),
            expansion_row,
        )

    def _load_setitems(self, path: Path) -> None:
        """Populate ``self._set_item_names`` from setitems.txt rows."""

        if not path.exists():
            logger.warning("setitems.txt not found at %s", path)
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                rows = list(csv.DictReader(f, delimiter="\t"))
        except (OSError, KeyError) as e:
            logger.error("Cannot read %s: %s", path, e)
            return
        self._load_setitems_rows(rows)

    def _load_setitems_rows(self, rows: list[dict[str, str]]) -> None:
        """Populate set-item lookup + binary->*ID mapping from pre-parsed rows."""
        result: dict[int, str] = {}
        expansion_row: int | None = None
        tracked: list[tuple[int, int, str]] = []
        for file_row, row in enumerate(rows):
            key = row.get("index", "").strip()
            star_id = row.get("*ID", "").strip()
            if key == "Expansion" and not star_id.isdigit():
                expansion_row = file_row
            elif key and star_id.isdigit():
                sid = int(star_id)
                result[sid] = key
                tracked.append((file_row, sid, key))
        self._set_item_keys = result

        # Build binary_value -> *ID mapping (same logic as uniqueitems).
        binary_map: dict[int, int] = {}
        for fr, sid, _key in tracked:
            if expansion_row is not None and fr > expansion_row:
                binary_val = fr - 1
            else:
                binary_val = fr
            binary_map[binary_val] = sid
        self._set_binary_to_star_id = binary_map
        logger.debug(
            "setitems binary->*ID map: %d entries, expansion at row %s",
            len(binary_map),
            expansion_row,
        )

    def _load_magicaffixes(self, prefix_path: Path, suffix_path: Path) -> None:
        """Populate ``self._magic_prefixes`` / ``self._magic_suffixes`` from magicprefix+magicsuffix rows."""

        def _read(path: Path) -> list[dict[str, str]]:
            if not path.exists():
                logger.warning("%s not found at %s", path.name, path)
                return []
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    return list(csv.DictReader(f, delimiter="\t"))
            except (OSError, KeyError) as e:
                logger.error("Cannot read %s: %s", path, e)
                return []

        self._load_magicaffixes_rows(_read(prefix_path), _read(suffix_path))

    def _load_magicaffixes_rows(
        self,
        prefix_rows: list[dict[str, str]],
        suffix_rows: list[dict[str, str]],
    ) -> None:
        """Populate magic prefix / suffix tables from pre-parsed rows."""

        def _split(rows: list[dict[str, str]]) -> tuple[list[str], list[int], list[str]]:
            names: list[str] = []
            lvl_reqs: list[int] = []
            transformcolors: list[str] = []
            for row in rows:
                n = row.get("name", "").strip()
                if not n:
                    continue
                names.append(n)
                try:
                    lvl_reqs.append(int(row.get("levelreq", "0").strip() or "0"))
                except ValueError:
                    lvl_reqs.append(0)
                transformcolors.append(row.get("transformcolor", "").strip())
            return names, lvl_reqs, transformcolors

        (self._prefix_names, self._prefix_lvl_reqs, self._prefix_transformcolors) = _split(
            prefix_rows
        )
        (self._suffix_names, self._suffix_lvl_reqs, self._suffix_transformcolors) = _split(
            suffix_rows
        )

    def _load_runes(self, path: Path) -> None:
        """Populate ``self._runeword_names`` + the rune-recipe index from runes.txt rows."""

        if not path.exists():
            logger.warning("runes.txt not found at %s", path)
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                rows = list(csv.DictReader(f, delimiter="\t"))
        except (OSError, KeyError) as e:
            logger.error("Cannot read %s: %s", path, e)
            return
        self._load_runes_rows(rows)

    def _load_runes_rows(self, rows: list[dict[str, str]]) -> None:
        """Populate runeword name list + recipe lookup from pre-parsed rows."""
        for row in rows:
            name = row.get("Name", "").strip()
            if not name:
                continue
            self._runeword_keys.append(name)
            # Build recipe -> name mapping from Rune1..Rune6 columns
            rune_codes = []
            for slot in range(1, 7):
                code = row.get(f"Rune{slot}", "").strip().lower()
                if code:
                    rune_codes.append(code)
            if rune_codes:
                self._runeword_recipe[tuple(rune_codes)] = name

    def _load_base_item_names(self, base: Path) -> None:
        """Build item_code -> display-name-key from armor, weapons, misc txt files."""
        for fname in ("armor.txt", "weapons.txt", "misc.txt"):
            path = base / fname
            if not path.exists():
                continue
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    reader = csv.DictReader(f, delimiter="\t")
                    for row in reader:
                        code = row.get("code", "").strip()
                        name = row.get("name", "").strip()
                        if code and name:
                            self._base_names[code] = name
            except (OSError, KeyError) as e:
                logger.error("Cannot read %s: %s", path, e)

    # The legacy ``_load_rare_affixes(excel_base)`` helper was removed
    # together with :func:`prepare_excel_base`. Rare-prefix and
    # raresuffix files are read in :meth:`load` via the Iron Rule
    # directly (they ship in CASC, not in the Reimagined mod).

    # ── Public look-up API ─────────────────────────────────────────────────────

    def is_loaded(self) -> bool:
        """Return True if the database has been populated."""
        return self._loaded

    def unique_binary_to_star_id(self, binary_value: int) -> int:
        """Convert a raw 12-bit unique-ID binary value to the *ID from uniqueitems.txt.

        The game binary stores a row index with only the "Expansion" separator
        row removed (GoMule's ``searchByID`` logic).  For vanilla D2 items this
        equals the ``*ID`` column, but Reimagined adds extra separator rows
        (Warlock Class Pack, Talonrage, ...) that shift the mapping.

        Used for **has_gfx=0** unique items where the 12-bit value is stored
        directly.  (has_gfx=1 items use the ``uid*2+has_class-2`` formula which
        produces the ``*ID`` directly.)

        Returns the ``*ID`` value, or *binary_value* unchanged if the mapping
        is unknown (graceful degradation).
        """
        return self._unique_binary_to_star_id.get(binary_value, binary_value)

    def get_affix_lvl_req(
        self,
        affix_ids: list[int] | None,
        affix_slots: list[int] | None = None,
    ) -> int:
        """Compute the maximum level requirement from rare/crafted affix IDs.

        Rare/Crafted items reserve 6 (or 7 for Reimagined MISC) binary
        slots. Even slots index into magicprefix.txt, odd slots index
        into magicsuffix.txt. Empty slots are skipped in ``affix_ids``,
        so the slot position for each entry is REQUIRED to route the
        lookup into the correct table: iterating with ``enumerate`` over
        a compact id list produces wrong results as soon as any earlier
        slot was empty.

        Args:
            affix_ids:   List of 11-bit affix IDs from the binary (only
                         filled slots).
            affix_slots: Parallel list of slot positions (0..6). Optional
                         for backward compat: when omitted, the function
                         falls back to the "even index = prefix" heuristic
                         that happens to be correct only when every slot
                         is filled.

        Returns:
            Maximum level requirement across all resolvable affixes, or
            0 if nothing can be looked up.
        """
        if not affix_ids:
            return 0
        max_lvl = 0
        for i, aid in enumerate(affix_ids):
            slot = affix_slots[i] if affix_slots and i < len(affix_slots) else i
            if slot % 2 == 0:
                if 0 <= aid < len(self._prefix_lvl_reqs):
                    max_lvl = max(max_lvl, self._prefix_lvl_reqs[aid])
            else:
                if 0 <= aid < len(self._suffix_lvl_reqs):
                    max_lvl = max(max_lvl, self._suffix_lvl_reqs[aid])
        return max_lvl

    def get_prefix_transformcolor(self, prefix_id: int) -> str | None:
        """Return the transformcolor for a magic prefix, or None."""
        if 0 <= prefix_id < len(self._prefix_transformcolors):
            c = self._prefix_transformcolors[prefix_id]
            return c if c else None
        return None

    def get_suffix_transformcolor(self, suffix_id: int) -> str | None:
        """Return the transformcolor for a magic suffix, or None."""
        if 0 <= suffix_id < len(self._suffix_transformcolors):
            c = self._suffix_transformcolors[suffix_id]
            return c if c else None
        return None

    def get_unique_invfile(self, star_id: int) -> str | None:
        """Return the invfile override for a unique item, or None."""
        return self._unique_invfile.get(star_id)

    def get_unique_invtransform(self, star_id: int) -> str | None:
        """Return the invtransform color code for a unique item, or None."""
        return self._unique_invtransform.get(star_id)

    def get_unique_lvl_req(self, star_id: int) -> int:
        """Return the required level for a unique item, or 0 if unknown."""
        return self._unique_lvl_req.get(star_id, 0)

    def get_unique_carry1(self, star_id: int) -> str | None:
        """Return the carry1 group for a unique item, or None if unrestricted.

        Items with the same carry1 value can only be carried once per character.
        """
        return self._unique_carry1.get(star_id)

    def set_binary_to_star_id(self, binary_value: int) -> int:
        """Convert a raw 12-bit set-item binary value to the *ID from setitems.txt.

        Same logic as :meth:`unique_binary_to_star_id` but for set items.
        Currently setitems.txt has only one separator (Expansion) so the
        mapping is identity, but this future-proofs against additional separators.
        """
        return self._set_binary_to_star_id.get(binary_value, binary_value)

    def get_unique_name(self, unique_type_id: int, lang: str = "enUS") -> str | None:
        """Return display name for a Unique item from its 12-bit type ID.

        The binary stores the ``*ID`` column value from uniqueitems.txt
        (NOT the row index - Reimagined has gaps where these differ).

        Args:
            unique_type_id: 12-bit *ID read from the binary (quality=7).
            lang:           Language code (default "enUS").

        Returns:
            Localised unique-item name, or None if ID not found / DB not loaded.
        """
        key = self._unique_keys.get(unique_type_id)
        if key is None:
            return None
        # Try strings JSON first; fall back to the key itself (which is already EN)
        return self._strings.get(key, lang) or key or None

    def get_set_item_name(self, set_item_id: int, lang: str = "enUS") -> str | None:
        """Return display name for a Set item from its 12-bit ID.

        The binary stores the ``*ID`` column value from setitems.txt
        (NOT the row index - Reimagined has gaps where these differ).

        Args:
            set_item_id: 12-bit *ID read from the binary (quality=5).
            lang:        Language code.

        Returns:
            Localised set-item name, or None.
        """
        key = self._set_item_keys.get(set_item_id)
        if key is None:
            return None
        return self._strings.get(key, lang) or key or None

    def get_prefix_name(self, prefix_id: int, lang: str = "enUS") -> str | None:
        """Return magic-prefix display name from its 11-bit ID.

        Note: magicprefix.txt `name` values are stored as English strings
        directly.  Localised look-up via the strings JSON is performed when
        the strings database is loaded; otherwise the raw name is returned.

        Args:
            prefix_id: 11-bit prefix ID read from the binary (quality=4).
            lang:      Language code.

        Returns:
            Prefix name (e.g. "Jagged"), or None if ID out of range.
        """
        if not 0 <= prefix_id < len(self._prefix_names):
            return None
        name = self._prefix_names[prefix_id]
        if not name:
            return None
        # The `name` column IS the string key in item-nameaffixes.json
        return self._strings.get(name, lang) or name

    def get_suffix_name(self, suffix_id: int, lang: str = "enUS") -> str | None:
        """Return magic-suffix display name from its 11-bit ID.

        Args:
            suffix_id: 11-bit suffix ID read from the binary (quality=4).
            lang:      Language code.

        Returns:
            Suffix name (e.g. "of Defense"), or None if ID out of range.
        """
        if not 0 <= suffix_id < len(self._suffix_names):
            return None
        name = self._suffix_names[suffix_id]
        if not name:
            return None
        return self._strings.get(name, lang) or name

    def get_rare_name(
        self,
        name_id1: int,
        name_id2: int,
        lang: str = "enUS",
    ) -> str | None:
        """Return the display name for a Rare or Crafted item.

        Rare/Crafted names are composed from two parts:
          rare_name_id1 (8-bit) -> rareprefix.txt row -> e.g. "Beast"
          rare_name_id2 (8-bit) -> raresuffix.txt row -> e.g. "Bite"
          -> combined display name: "Beast Bite"

        Name resolution mirrors :meth:`get_prefix_name` /
        :meth:`get_suffix_name`: the raw ``name`` cell in rareprefix.txt /
        raresuffix.txt is a **string-table key**, not a display string.
        For most entries the key and the localised display text coincide
        (``"Beast"`` -> ``"Beast"``), but Reimagined carries a fair number
        of keys where they do not - e.g. ``GhoulRI`` -> ``Ghoul``,
        ``Wraithra`` -> ``Wraith``, ``Holocaust`` -> ``Armageddon``. Taking
        the raw key verbatim produced display names like ``Ghoulri Eye``
        that do not match the in-game tooltip.

        This method therefore looks the key up in the strings database
        first; if no entry exists (or the strings DB is not loaded), it
        falls back to the raw key with ``capitalize()`` applied, preserving
        the previous behaviour for those non-localised entries.

        Args:
            name_id1: 8-bit rare name prefix ID read from the binary.
            name_id2: 8-bit rare name suffix ID read from the binary.
            lang:     Language code (e.g. ``"enUS"``, ``"deDE"``). Unknown
                      codes fall through to ``enUS`` in the strings DB.

        Returns:
            Combined rare name string (e.g. "Beast Bite"), or None if both
            ID lookups fail or the tables are not loaded.
        """

        def _resolve(key: str | None) -> str | None:
            if not key:
                return None
            # Prefer the localised entry (already correctly cased by the
            # string table). Fall back to the raw key if no entry exists,
            # applying capitalize() only in that fallback branch because
            # many raw suffix keys are lowercase ("bite", "fang", ...) but
            # their string-table counterparts are not.
            localised = self._strings.get(key, lang)
            return localised if localised else key.capitalize()

        prefix = (
            self._rareprefix_names[name_id1]
            if 0 <= name_id1 < len(self._rareprefix_names)
            else None
        )
        suffix = (
            self._raresuffix_names[name_id2]
            if 0 <= name_id2 < len(self._raresuffix_names)
            else None
        )
        parts = [p for p in (_resolve(prefix), _resolve(suffix)) if p]
        return " ".join(parts) if parts else None

    def get_runeword_name(self, runeword_id: int, lang: str = "enUS") -> str | None:
        """Return runeword display name from its 12-bit ID.

        The 12-bit value read from the binary (the ``rw_str_index`` field)
        is a 0-based row index into runes.txt.

        Args:
            runeword_id: 12-bit runeword index read from the binary.
            lang:        Language code.

        Returns:
            Runeword name (e.g. "Grief"), or None if ID out of range.
        """
        if not 0 <= runeword_id < len(self._runeword_keys):
            return None
        key = self._runeword_keys[runeword_id]
        return self._strings.get(key, lang) or key or None

    def get_runeword_name_by_recipe(
        self,
        rune_codes: list[str],
        lang: str = "enUS",
    ) -> str | None:
        """Return runeword display name by matching rune recipe codes.

        Resolves the runeword name by comparing the actual rune codes of the
        socketed child items against the Rune1..Rune6 columns in runes.txt.
        This is the preferred lookup when child item codes are available,
        as it is immune to version-drift (binary row indices can become stale
        when Reimagined adds new runewords, shifting existing rows).

        Args:
            rune_codes: Ordered list of rune item codes (e.g. ["r24","r24","r24","r24"]).
                        Codes are compared case-insensitively.
            lang:       Language code for display.

        Returns:
            Runeword name (e.g. "Glory"), or None if not found.
        """
        key = tuple(c.lower().strip() for c in rune_codes)
        name = self._runeword_recipe.get(key)
        if name is None:
            return None
        return self._strings.get(name, lang) or name

    def get_base_item_name(self, item_code: str, lang: str = "enUS") -> str | None:
        """Return the base item display name for a given item code.

        D2R Reimagined strings use the item CODE as the JSON key (e.g. "7fb")
        and the value includes a tier suffix like "[E]" or "[N]" - we strip it
        because the CLI adds the tier suffix separately.

        Falls back to the ``name`` column from armor/weapons/misc.txt if the
        strings JSON has no entry for this code.

        Args:
            item_code: Huffman-decoded item code (e.g. "ghm", "hax").
            lang:      Language code.

        Returns:
            Base item name (e.g. "Colossus Sword", "Hand Axe"), or None.
        """

        # Primary: look up by item code in strings JSON (D2R uses code as key)
        s = self._strings.get(item_code, lang)
        if s:
            # Strip tier suffix like " [E]", " [X]", " [N]" that D2R includes
            s = re.sub(r"\s*\[[NXE]\]\s*$", "", s)
            return s
        # Fallback: use the txt file `name` column (raw English name)
        key = self._base_names.get(item_code)
        if key is None:
            return None
        # Try the txt name as a strings key (rare but possible)
        return self._strings.get(key, lang) or key or None

    def build_display_name(
        self,
        item_code: str,
        quality: int,
        *,
        unique_type_id: int | None = None,
        set_item_id: int | None = None,
        prefix_id: int | None = None,
        suffix_id: int | None = None,
        rare_name_id1: int | None = None,
        rare_name_id2: int | None = None,
        runeword_id: int | None = None,
        is_runeword: bool = False,
        rune_codes: list[str] | None = None,
        tier_suffix: str = "",
        identified: bool = True,
        lang: str = "enUS",
    ) -> str | None:
        """Build the full display name for an item given its quality IDs.

        Quality-specific name construction:
          - Unique (7):        "[UniqueName]"           e.g. "Jalal's Mane"
          - Set (5):           "[SetItemName]"          e.g. "Sigon's Visor"
          - Magic (4):         "[Prefix] [Base] [Suffix]" e.g. "Jagged Antlers of Defense"
                               (omits prefix/suffix parts if ID is 0 or not found)
          - Rare/Crafted (6/8): "[RarePrefix] [RareSuffix]" e.g. "Beast Bite"
                               (falls back to base item name if tables not loaded)
          - Runeword:          "[RunewordName]"         e.g. "Grief"
                               (overrides quality-based name when flag is set)
          - Normal/Superior/Low: "[BaseName]"           e.g. "Antlers"

        Args:
            item_code:      Huffman-decoded 3-character item code.
            quality:        Quality ID (1=Low, 2=Normal, 3=Superior, 4=Magic,
                            5=Set, 6=Rare, 7=Unique, 8=Crafted).
            unique_type_id: 12-bit unique-type ID (quality=7).
            set_item_id:    12-bit set-item ID (quality=5).
            prefix_id:      11-bit magic prefix ID (quality=4).
            suffix_id:      11-bit magic suffix ID (quality=4).
            rare_name_id1:  8-bit rare name prefix ID (quality=6/8).
            rare_name_id2:  8-bit rare name suffix ID (quality=6/8).
            runeword_id:    12-bit runeword index (when is_runeword=True).
            is_runeword:    True if item has the runeword flag set.
            lang:           Language code for localised output.

        Returns:
            Display name string, or None if no name can be determined.
        """
        # ── Unidentified items ────────────────────────────────────────────
        # In D2R, unidentified items show ONLY the base item name (with
        # tier suffix) - no prefix/suffix, no unique/set/runeword label.
        # The quality colour stays (a Set item still renders green), but
        # the header text is just "Heavy Boots [N]" even if the item is
        # a specific Set piece. Identification reveals the full name.
        if not identified:
            base = self.get_base_item_name(item_code, lang)
            return f"{base}{tier_suffix}" if tier_suffix else base

        # Runeword overrides quality-based name.
        # Prefer recipe-based lookup (immune to version-drift) over row-index lookup.
        if is_runeword:
            if rune_codes:
                rw_name = self.get_runeword_name_by_recipe(rune_codes, lang)
                if rw_name:
                    return rw_name
            if runeword_id is not None:
                rw_name = self.get_runeword_name(runeword_id, lang)
                if rw_name:
                    return rw_name

        base = self.get_base_item_name(item_code, lang)

        if quality == 7 and unique_type_id is not None:  # Unique
            name = self.get_unique_name(unique_type_id, lang)
            return name if name else base

        if quality == 5 and set_item_id is not None:  # Set
            name = self.get_set_item_name(set_item_id, lang)
            return name if name else base

        if quality == 4:  # Magic - "[Prefix] [Base] [Tier] [Suffix]"
            prefix = self.get_prefix_name(prefix_id, lang) if prefix_id else None
            suffix = self.get_suffix_name(suffix_id, lang) if suffix_id else None
            # Insert tier suffix after base name: "Archon Staff [E]"
            base_tier = f"{base}{tier_suffix}" if tier_suffix else base
            parts = [p for p in (prefix, base_tier, suffix) if p]
            return " ".join(parts) if parts else None

        if quality in (6, 8) and rare_name_id1 is not None and rare_name_id2 is not None:
            # Rare or Crafted - two-part name from rareprefix/raresuffix tables
            name = self.get_rare_name(rare_name_id1, rare_name_id2, lang)
            return name if name else base

        # Normal / Superior / Low / Rare without IDs: return base item name + tier
        return f"{base}{tier_suffix}" if tier_suffix else base


# ──────────────────────────────────────────────────────────────────────────────
# Module-level singleton + public API
# ──────────────────────────────────────────────────────────────────────────────

_ITEM_NAMES_DB = ItemNamesDatabase()


def get_item_names_db() -> ItemNamesDatabase:
    """Return the global ItemNamesDatabase singleton."""
    return _ITEM_NAMES_DB


SCHEMA_VERSION_ITEM_NAMES: int = 2  # +trailing-comma JSON retry (skills.json loads now)


def load_item_names(
    *,
    use_cache: bool = True,
    source_versions: "SourceVersions | None" = None,
    cache_dir: "Path | None" = None,
) -> None:
    """Populate the :class:`ItemNamesDatabase` from the strings tables.

    Ingests every string-table JSON under
    ``data/local/lng/strings/`` plus the affix tables
    (``magicprefix.txt``, ``magicsuffix.txt``, ``rareprefix.txt``,
    ``raresuffix.txt``) and the top-level
    ``uniqueitems.txt`` / ``setitems.txt``.  Produces the full
    name resolution chain used by ``build_display_name()``:

        item_code + quality + (unique_type_id | set_item_id |
        prefix_id | suffix_id | rare_name_ids) -> localised string

    Transparently backed by the persistent pickle cache - see
    :mod:`d2rr_toolkit.meta.cache` for the invalidation contract.
    This loader is unusual in that it populates TWO singletons
    (:class:`StringsDatabase` nested inside
    :class:`ItemNamesDatabase`) in one pass; the cache snapshots
    the outer :class:`ItemNamesDatabase` which already carries its
    :class:`StringsDatabase` in its ``_strings`` attribute.  At
    ~7 MB pickle size this is the largest cached table - it still
    warms in ~125 ms vs ~900 ms cold parse.

    Args:
        use_cache: ``False`` disables the cache for this call.
        source_versions: Optional :class:`SourceVersions`; shared
            instance preferred across batched loaders.
        cache_dir: Optional cache root override.
    """

    def _build() -> None:
        _ITEM_NAMES_DB.load()

    cached_load(
        name="item_names",
        schema_version=SCHEMA_VERSION_ITEM_NAMES,
        singleton=_ITEM_NAMES_DB,
        build=_build,
        use_cache=use_cache,
        source_versions=source_versions,
        cache_dir=cache_dir,
    )

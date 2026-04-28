"""Enchantment recipe tables - deterministic mapping from cubemain.txt recipes
to the exact stat bundle each enchant applies.

D2R Reimagined's "Item Enchantment" feature lets players add capped
bonus mods to equipment via cube recipes.  Capacity is tracked by four
fake ISC stats (``upgrade_minor`` 392 / ``upgrade_medium`` 393 /
``upgrade_major`` 394 / ``upgrade_uber`` 395) - each enchant recipe
outputs exactly one of these markers plus the actual stat mods.

The full pool lives in ``cubemain.txt`` at lines 635-975 (341 rows in
Reimagined 3.0.7) keyed by ``input 1`` (item-type token: ``amu`` /
``rin`` / ``belt`` / ``boot`` / ``glov`` / ``helm`` / ``shld`` /
``tors`` / ``slam`` / ``sppl`` / ``miss`` / ``1wep``).

Each row has up to 5 ``mod N`` slots:
  * ``mod 1`` = ``upgrade/minor`` | ``upgrade/medium`` | ``upgrade/major`` | ``upgrade/uber``
    (the capacity-tier marker, filtered out of :attr:`EnchantmentRecipe.mods`)
  * ``mod 2``..``mod 5`` = actual bonus effects with fixed values
    (``chance=100``, ``min == max`` universally - no rolled ranges)

Unlike corruption, enchants are NOT identifiable from the item's
binary after-the-fact: there's no stat that records which recipe
fired.  But we CAN enumerate every recipe whose output mods could
explain a residual stat value, and when only one recipe's mods fit
the residual exactly, the attribution is unique.  When multiple
recipes could explain it, :class:`StatBreakdownResolver` returns
``ambiguity="multiple"`` and lets the caller disambiguate.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from d2rr_toolkit.meta.source_versions import SourceVersions
from d2rr_toolkit.adapters.casc import read_game_data_rows
from d2rr_toolkit.meta import cached_load

logger = logging.getLogger(__name__)

SCHEMA_VERSION_ENCHANTMENT_RECIPES: int = 2  # +par on EnchantmentMod

_MAX_MOD_SLOTS = 5

# The four capacity-tier markers in cubemain.  Stripped from
# :attr:`EnchantmentRecipe.mods` because they encode "I applied this
# tier of enchant", not a bonus the player's stats reflect.
_CAPACITY_TIERS: dict[str, int] = {
    "upgrade/minor": 392,  # max 2 enchants allowed
    "upgrade/medium": 393,  # max 3
    "upgrade/major": 394,  # max 5
    "upgrade/uber": 395,  # max 10
}


# ── Dataclasses ─────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class EnchantmentMod:
    """One stat contribution from an applied enchantment recipe.

    Mirrors :class:`CorruptionMod`.  ``par`` carries the parameter
    column from cubemain (typically empty for plain mods, populated
    with a skill name for ``oskill``/``hit-skill`` variants or a
    class code for class-specific bonuses).  ``min_value == max_value``
    holds for every enchant in Reimagined 3.0.7 (fixed values, not
    ranges), but the pair is kept for schema symmetry and future-
    proofing.
    """

    code: str
    par: str
    min_value: float
    max_value: float

    @property
    def is_fixed(self) -> bool:
        """Return True if this mod has a fixed (non-random) value."""
        return self.min_value == self.max_value


@dataclass(frozen=True, slots=True)
class EnchantmentRecipe:
    """One ENCHANT ITEM cube recipe.

    ``item_type`` is the short token from ``input 1`` (``amu``,
    ``1wep``, ``tors``, ...).  ``inputs`` is the reagent chain in
    display order (gems, runes, orbs) - useful for the GUI when
    surfacing "this item was enchanted with Amulet + Topaz".
    ``capacity_tier`` is the ISC stat id (392/393/394/395) the
    recipe occupies on the item.  ``mods`` are the actual
    stat-bonus effects, stripped of the capacity marker.
    """

    item_type: str
    capacity_tier: int
    inputs: tuple[str, ...]
    mods: tuple[EnchantmentMod, ...]
    description: str
    row_index: int


# ── Database ────────────────────────────────────────────────────────────────


class EnchantmentRecipeDatabase:
    """In-memory index of enchant recipes by item type."""

    def __init__(self) -> None:
        # item_type -> list of recipes in insertion order (matches cubemain)
        self._by_type: dict[str, list[EnchantmentRecipe]] = {}
        # reverse lookup: stat_code -> list of (recipe, mod) touching that stat
        self._by_mod_code: dict[str, list[tuple[EnchantmentRecipe, EnchantmentMod]]] = {}
        self._loaded = False

    def load_from_rows(
        self,
        cubemain_rows: list[dict[str, str]],
        *,
        source: str = "<rows>",
    ) -> None:
        """Populate the database from pre-parsed cubemain.txt rows."""
        self._by_type.clear()
        self._by_mod_code.clear()

        for i, row in enumerate(cubemain_rows):
            if (row.get("op") or "").strip() != "16":
                continue
            try:
                param = int((row.get("param") or "").strip())
            except ValueError:
                continue
            if param not in _CAPACITY_TIERS.values():
                continue

            tier_marker = (row.get("mod 1") or "").strip()
            if tier_marker not in _CAPACITY_TIERS:
                # Not all op=16/param=392-395 rows are enchants -
                # skip anything whose first mod isn't a capacity tier.
                continue
            capacity_tier = _CAPACITY_TIERS[tier_marker]

            item_type = (row.get("input 1") or "").strip()
            if not item_type:
                continue

            inputs: list[str] = []
            for ic in ("input 1", "input 2", "input 3", "input 4", "input 5", "input 6", "input 7"):
                val = (row.get(ic) or "").strip()
                if val:
                    inputs.append(val)

            mods = _extract_mods(row, skip_codes=frozenset(_CAPACITY_TIERS))

            recipe = EnchantmentRecipe(
                item_type=item_type,
                capacity_tier=capacity_tier,
                inputs=tuple(inputs),
                mods=mods,
                description=(row.get("description") or "").strip(),
                row_index=i,
            )
            self._by_type.setdefault(item_type, []).append(recipe)
            for m in mods:
                self._by_mod_code.setdefault(m.code, []).append((recipe, m))

        self._loaded = True
        total = sum(len(v) for v in self._by_type.values())
        logger.info(
            "EnchantmentRecipeDatabase: %d types, %d recipes (from %s)",
            len(self._by_type),
            total,
            source,
        )

    def is_loaded(self) -> bool:
        """Return True if the database has been populated."""
        return self._loaded

    # ── Lookup API ──────────────────────────────────────────────────────

    def recipes_for_type(
        self,
        item_type: str,
    ) -> tuple[EnchantmentRecipe, ...]:
        """Every recipe whose ``input 1`` matches ``item_type``."""
        return tuple(self._by_type.get(item_type, ()))

    def recipes_touching_code(
        self,
        prop_code: str,
    ) -> tuple[tuple[EnchantmentRecipe, EnchantmentMod], ...]:
        """Every (recipe, mod) pair that applies ``prop_code``.

        The caller still needs to cross-check the recipe's item_type
        against the item under analysis - this view is indexed by
        property code only for O(1) candidate discovery.
        """
        return tuple(self._by_mod_code.get(prop_code, ()))

    def candidates_for(
        self,
        item_type: str,
        prop_code: str,
    ) -> tuple[tuple[EnchantmentRecipe, EnchantmentMod], ...]:
        """Narrow ``recipes_touching_code`` to those matching item_type."""
        candidates = self._by_mod_code.get(prop_code, ())
        if not candidates:
            return ()
        return tuple((r, m) for r, m in candidates if r.item_type == item_type)

    def recipes_touching_code_for_stat(
        self,
        *,
        stat_id: int,
        stat_ids_for_code: Callable[[str], set[int]],
        bucket: str,
    ) -> list[tuple[EnchantmentRecipe, EnchantmentMod]]:
        """Return every (recipe, mod) pair for a given bucket whose mod's
        property code expands to include ``stat_id``.

        ``stat_ids_for_code`` is a callable ``code -> set[int]`` - the
        caller passes in an expansion helper (typically
        :meth:`StatBreakdownResolver._stat_ids_for_code`) so this
        module doesn't need to know about PropertiesDatabase / ISC.
        The indirection keeps the enchant loader dependency-free for
        downstream code that only needs the raw recipe data.
        """
        out: list[tuple[EnchantmentRecipe, EnchantmentMod]] = []
        recipes = self._by_type.get(bucket, ())
        for recipe in recipes:
            for mod in recipe.mods:
                ids = stat_ids_for_code(mod.code)
                if stat_id in ids:
                    out.append((recipe, mod))
        return out

    # ── Item-code bucketing ─────────────────────────────────────────────

    def map_item_code(
        self,
        item_code: str,
        item_types: "set[str]",
    ) -> list[str]:
        """Return every cubemain bucket the item could be enchanted as.

        Unlike corruption (one bucket per item), enchantment buckets
        overlap for weapons: a one-handed sword qualifies for both
        ``1wep`` and the weapon-class buckets (``slam`` for melee,
        ``miss`` for missile, ``sppl`` for spell-pole staves).  We
        return all applicable buckets and let the resolver try each.

        Cubemain input tokens mix item codes (``amu``, ``rin``) and
        itype names (``shld``, ``1wep``, ``miss`` ...).  We therefore
        check the item code itself first, then walk its itype ancestor
        set - both may contribute matching buckets.
        """
        buckets = {
            "amu",
            "rin",
            "belt",
            "boot",
            "glov",
            "helm",
            "shld",
            "tors",
            "slam",
            "sppl",
            "miss",
            "1wep",
        }
        matches: list[str] = []
        if item_code in buckets:
            matches.append(item_code)
        for t in item_types:
            if t in buckets and t not in matches:
                matches.append(t)
        return matches


# ── Helpers ─────────────────────────────────────────────────────────────────


def _extract_mods(
    row: dict[str, str],
    *,
    skip_codes: frozenset[str] = frozenset(),
) -> tuple[EnchantmentMod, ...]:
    """Extract the (op, par, min, max) 4-tuple for each mod slot in a cubemain row."""
    out: list[EnchantmentMod] = []
    for i in range(1, _MAX_MOD_SLOTS + 1):
        code = (row.get(f"mod {i}") or "").strip()
        if not code or code in skip_codes:
            continue
        mn = _parse_numeric(row.get(f"mod {i} min"))
        mx = _parse_numeric(row.get(f"mod {i} max"))
        if mn is None or mx is None:
            continue
        par = (row.get(f"mod {i} param") or "").strip()
        out.append(
            EnchantmentMod(
                code=code,
                par=par,
                min_value=mn,
                max_value=mx,
            )
        )
    return tuple(out)


def _parse_numeric(v: object | None) -> float | None:
    """Return the first numeric token in ``s`` as an int, or None."""

    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ── Module-level singleton + loader ─────────────────────────────────────────

_ENCHANT_DB = EnchantmentRecipeDatabase()


def get_enchantment_db() -> EnchantmentRecipeDatabase:
    """Return the module-level :class:`EnchantmentRecipeDatabase` singleton."""
    return _ENCHANT_DB


def load_enchantment_recipes(
    *,
    use_cache: bool = True,
    source_versions: "SourceVersions | None" = None,
    cache_dir: "Path | None" = None,
) -> None:
    """Populate the process-wide :class:`EnchantmentRecipeDatabase`."""

    def _build() -> None:

        rows = read_game_data_rows("data:data/global/excel/cubemain.txt")
        if not rows:
            logger.warning(
                "enchantment_recipes: cubemain.txt returned no rows - enchant attribution disabled."
            )
            return
        _ENCHANT_DB.load_from_rows(
            rows,
            source="data:data/global/excel/cubemain.txt",
        )

    cached_load(
        name="enchantment_recipes",
        schema_version=SCHEMA_VERSION_ENCHANTMENT_RECIPES,
        singleton=_ENCHANT_DB,
        build=_build,
        use_cache=use_cache,
        source_versions=source_versions,
        cache_dir=cache_dir,
    )

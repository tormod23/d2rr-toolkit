"""Game-data loader layer for D2R Reimagined.

Reads the Reimagined mod's and vanilla D2R's ``.txt`` / ``.json`` data
files through the CASC reader (Iron Rule: mod install first, CASC
fallback) and exposes typed, cached lookups for every downstream
consumer (parsers, writers, display, catalog).

Each loader backs a process-wide singleton restored from an
HMAC-signed pickle cache; see :mod:`d2rr_toolkit.meta.cache`.

Main loaders:
  * :func:`load_item_types`           - item type classification.
  * :func:`load_item_stat_cost`       - ISC stat table (436 stats).
  * :func:`load_item_names`           - multilingual display names.
  * :func:`load_skills`               - skills.txt.
  * :func:`load_charstats`            - per-class stat defaults.
  * :func:`load_sets`                 - set bonus definitions.
  * :func:`load_properties` /
    :func:`load_property_formatter`   - prop-code -> ISC stats and
                                        human-readable formatters.
  * :func:`load_automagic`            - automod tables.
  * :func:`load_cubemain`             - Reimagined corruption /
                                        enchantment recipes.
  * :func:`load_gems`                 - gem and rune stats.
  * :func:`load_affix_rolls`          - stat roll-range resolver.
  * :func:`load_hireling`             - mercenary roster.

See ``docs/ARCHITECTURE.md`` §"Package responsibilities" -> game_data.
"""


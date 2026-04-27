"""Adapter layer - isolates d2rr_toolkit from external resources.

Every subpackage under ``d2rr_toolkit.adapters`` wraps an external system
so the rest of the toolkit (models, parsing, writing, game data, display,
services, persistence) can stay free of third-party coupling. Swap an
adapter, and the core domain keeps working unchanged.

Current adapters:

* :mod:`d2rr_toolkit.adapters.casc` - pure-Python CASC archive reader
  for the D2R install directory. Reads TVFS roots, BLTE-encoded blobs,
  and exposes item sprite and palette assets.

The rule of thumb: if a module imports ``PIL``, ``sqlite3``, a native
binary, or touches the filesystem in a product-specific way, it belongs
under adapters. The core domain modules must not.
"""

"""Architectural enforcement: no lazy imports, no import cycles.

Two checks, both run as standard pytest tests so a regression fails CI
the same way a unit test would:

1. **No lazy imports.**  Every internal ``import d2rr_toolkit.x`` /
   ``from d2rr_toolkit.x import y`` must live at module top, not inside
   a function or method body.  TYPE_CHECKING-gated imports are the only
   allowed exception (they exist for type checkers and never run at
   runtime).
2. **Acyclic top-level import graph.**  After excluding TYPE_CHECKING
   blocks, the directed graph of internal imports must be a DAG.  A
   cycle here means two modules try to load each other at module
   import time, which works only by accident (Python's partial-module
   trick) and breaks at the first refactor that reorders the load.

The check operates on the AST so it does not need to actually import
the project.  Both rules grew out of a 2026-04 audit that surfaced
158 lazy imports masking a real ``affix_rolls / property_formatter /
stat_breakdown`` cycle - see the migration notes in ``CHANGELOG.md``.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "d2rr_toolkit"


def _module_name(fp: Path) -> str:
    rel = fp.relative_to(SRC.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _is_internal(mod: str) -> bool:
    return mod.startswith("d2rr_toolkit")


def _collect_lazy_imports(tree: ast.Module) -> list[tuple[int, str, str]]:
    """Return (lineno, function_name, imported_module) for every internal
    import nested inside a function or method body.
    """
    out: list[tuple[int, str, str]] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _is_internal(alias.name):
                        out.append((node.lineno, fn.name, alias.name))
            elif isinstance(node, ast.ImportFrom):
                if node.module is not None and _is_internal(node.module):
                    out.append((node.lineno, fn.name, node.module))
    return out


def _collect_top_level_internal_imports(tree: ast.Module) -> set[str]:
    """Return the set of internal modules imported at module top-level
    (excluding TYPE_CHECKING-only imports which are not runtime edges).
    """
    out: set[str] = set()
    if not isinstance(tree, ast.Module):
        return out
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_internal(alias.name):
                    out.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None and _is_internal(node.module):
                out.add(node.module)
        elif isinstance(node, ast.If):
            test = node.test
            is_tc = (
                isinstance(test, ast.Name)
                and test.id == "TYPE_CHECKING"
            ) or (
                isinstance(test, ast.Attribute)
                and test.attr == "TYPE_CHECKING"
            )
            if is_tc:
                # TYPE_CHECKING imports are intentionally excluded from
                # the runtime graph - they exist only for static type
                # checkers and never execute at runtime.
                continue
            # Other top-level if-blocks (sys.platform == "win32") DO
            # produce runtime edges; recurse into them.
            for inner in node.body:
                if isinstance(inner, ast.Import):
                    for alias in inner.names:
                        if _is_internal(alias.name):
                            out.add(alias.name)
                elif isinstance(inner, ast.ImportFrom):
                    if inner.module is not None and _is_internal(inner.module):
                        out.add(inner.module)
    return out


def _find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Tarjan's SCC.  Returns every SCC of size > 1 (and any self-loops)."""
    index_counter = [0]
    stack: list[str] = []
    on_stack: set[str] = set()
    indexes: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    cycles: list[list[str]] = []

    def strongconnect(v: str) -> None:
        indexes[v] = index_counter[0]
        lowlinks[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in graph.get(v, ()):
            if w not in indexes:
                strongconnect(w)
                lowlinks[v] = min(lowlinks[v], lowlinks[w])
            elif w in on_stack:
                lowlinks[v] = min(lowlinks[v], indexes[w])
        if lowlinks[v] == indexes[v]:
            scc: list[str] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                scc.append(w)
                if w == v:
                    break
            if len(scc) > 1 or scc[0] in graph.get(scc[0], ()):
                cycles.append(sorted(scc))

    nodes: set[str] = set(graph.keys())
    for vs in graph.values():
        nodes.update(vs)
    for v in sorted(nodes):
        if v not in indexes:
            strongconnect(v)
    return cycles


def _build_graph_and_lazy_inventory() -> tuple[
    dict[str, set[str]], dict[str, list[tuple[int, str, str]]]
]:
    graph: dict[str, set[str]] = defaultdict(set)
    lazy: dict[str, list[tuple[int, str, str]]] = {}
    for fp in sorted(SRC.rglob("*.py")):
        text = fp.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(fp))
        m = _module_name(fp)
        graph[m] = _collect_top_level_internal_imports(tree)
        items = _collect_lazy_imports(tree)
        if items:
            lazy[m] = items
    return graph, lazy


def test_no_lazy_imports_inside_functions() -> None:
    """Every internal import must be at module top-level.

    Lazy imports inside function bodies hide cycles from the load-time
    import system: they "work" because Python's late-binding means the
    cycle never triggers a partial-module read.  Promote them to top-of-
    file so cycles surface as ImportErrors at load time, not as silent
    architectural debt.

    Two narrow exceptions remain admissible (and are NOT in the codebase
    today): module-attribute lookup that genuinely happens only on first
    call and would create a true import-time cycle no refactor can break.
    Those would be tracked here as an explicit allow-list - currently
    empty.
    """
    _graph, lazy = _build_graph_and_lazy_inventory()
    if not lazy:
        return
    lines = ["Lazy imports found (must move to module top-of-file):"]
    for mod, items in sorted(lazy.items()):
        lines.append(f"\n  {mod}")
        for lineno, fn, imp in sorted(items):
            lines.append(f"    line {lineno:5d}  in {fn}()  ->  {imp}")
    raise AssertionError("\n".join(lines))


def test_top_level_import_graph_is_acyclic() -> None:
    """The runtime import graph must be a DAG.

    Python's import machinery handles cycles by returning a partially-
    initialised module - that's the same machinery that lets two files
    ``import`` each other at the top of the file.  It is fragile: any
    name accessed during module body execution that happens to be on
    the still-loading half of the cycle raises ImportError.  Refactors
    that reorder a class definition or move a decorator can flip a
    working import into a broken one.

    The fix is to never have the cycle in the first place - extract a
    leaf module that both sides depend on, or invert the dependency.
    """
    graph, _lazy = _build_graph_and_lazy_inventory()
    cycles = _find_cycles(graph)
    if not cycles:
        return
    lines = ["Top-level import cycles found:"]
    for c in cycles:
        lines.append("  cycle: " + " -> ".join(c) + " -> " + c[0])
    raise AssertionError("\n".join(lines))

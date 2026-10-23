"""Import-time dependency graph of the Python source packages (``so101_demo`` and ``so101_teleop``).

Only module-level imports count: they run when the module is first imported, so they are the ones that can
deadlock into a cycle. Imports inside functions and ``if TYPE_CHECKING`` blocks are lazy and are not edges.
"""

from __future__ import annotations

import ast
from pathlib import Path

from paths import REPOSITORY

SOURCE_PACKAGES = {
    "so101_demo": REPOSITORY / "src" / "so101_demo_py" / "src",
    "so101_teleop": REPOSITORY / "src" / "so101_teleop" / "so101_teleop",
}


def module_files() -> dict[str, Path]:
    modules: dict[str, Path] = {}
    for package, root in SOURCE_PACKAGES.items():
        for path in root.rglob("*.py"):
            parts = [package, *path.relative_to(root).with_suffix("").parts]
            if parts[-1] == "__init__":
                parts = parts[:-1]
            modules[".".join(parts)] = path
    return modules


def _module_level_imports(body: list[ast.stmt]) -> list[ast.stmt]:
    found: list[ast.stmt] = []
    for node in body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            found.append(node)
        elif isinstance(node, ast.If):
            if "TYPE_CHECKING" not in ast.dump(node.test):
                found += _module_level_imports(node.body) + _module_level_imports(node.orelse)
        elif isinstance(node, ast.Try):
            found += _module_level_imports(node.body)
            for handler in node.handlers:
                found += _module_level_imports(handler.body)
            found += _module_level_imports(node.orelse)
    return found


def import_graph() -> dict[str, set[str]]:
    modules = module_files()
    graph: dict[str, set[str]] = {name: set() for name in modules}
    for name, path in modules.items():
        package = name if path.name == "__init__.py" else name.rpartition(".")[0]
        for node in _module_level_imports(ast.parse(path.read_text(encoding="utf-8")).body):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = alias.name
                    while target and target not in modules:
                        target = target.rpartition(".")[0]
                    if target:
                        graph[name].add(target)
                continue
            module = node.module or ""
            if node.level:
                base = package.split(".")
                base = base[: len(base) - (node.level - 1)]
                module = ".".join([*base, *([module] if module else [])])
            if module in modules:
                graph[name].add(module)
            for alias in node.names:
                if f"{module}.{alias.name}" in modules:
                    graph[name].add(f"{module}.{alias.name}")
    return graph


def import_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Strongly connected components with more than one module (iterative Tarjan)."""

    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    cycles: list[list[str]] = []
    counter = 0
    for root in sorted(graph):
        if root in index:
            continue
        work = [(root, iter(sorted(graph[root])))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, children = work[-1]
            advanced = False
            for child in children:
                if child not in index:
                    index[child] = low[child] = counter
                    counter += 1
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, iter(sorted(graph[child]))))
                    advanced = True
                    break
                if child in on_stack:
                    low[node] = min(low[node], index[child])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                component = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                if len(component) > 1:
                    cycles.append(sorted(component))
    return sorted(cycles)

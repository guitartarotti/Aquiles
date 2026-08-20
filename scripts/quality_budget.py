"""Enforce the repository's ratcheting quality budget."""

from __future__ import annotations

import ast
import io
import re
import sys
import tokenize
import tomllib
from collections.abc import Iterable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BUDGET_PATH = REPO_ROOT / "quality-budget.toml"


def load_budget(path: Path = BUDGET_PATH) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _relative_path(repo_root: Path, path: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def _source_files(
    repo_root: Path,
    relative_root: str,
    extensions: Iterable[str],
    exclude_parts: Iterable[str] = (),
) -> list[Path]:
    root = repo_root / relative_root
    allowed_extensions = set(extensions)
    excluded = set(exclude_parts)
    if not root.exists():
        return []
    return [
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix in allowed_extensions
        and not excluded.intersection(path.relative_to(root).parts)
    ]


def check_file_sizes(repo_root: Path, budget: dict[str, Any]) -> list[str]:
    config = budget["file_size"]
    legacy = {str(path): int(limit) for path, limit in config.get("legacy", {}).items()}
    violations: list[str] = []
    visited_allowances: set[str] = set()

    for rule in config.get("rules", []):
        default_limit = int(rule["max_lines"])
        for path in _source_files(
            repo_root,
            str(rule["root"]),
            rule["extensions"],
            rule.get("exclude_parts", []),
        ):
            relative = _relative_path(repo_root, path)
            line_count = len(path.read_text(encoding="utf-8-sig", errors="replace").splitlines())
            limit = legacy.get(relative, default_limit)
            if relative in legacy:
                visited_allowances.add(relative)
            if line_count > limit:
                violations.append(f"file-size: {relative} has {line_count} lines; budget is {limit}")

    stale = sorted(set(legacy) - visited_allowances)
    violations.extend(f"file-size: stale legacy allowance for {path}" for path in stale)
    return violations


def _count_pattern(paths: Iterable[Path], pattern: re.Pattern[str]) -> int:
    return sum(
        len(pattern.findall(path.read_text(encoding="utf-8-sig", errors="replace")))
        for path in paths
    )


def _count_python_comment_pattern(paths: Iterable[Path], pattern: re.Pattern[str]) -> int:
    count = 0
    for path in paths:
        source = path.read_text(encoding="utf-8-sig", errors="replace")
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        count += sum(
            len(pattern.findall(token.string))
            for token in tokens
            if token.type == tokenize.COMMENT
        )
    return count


def check_suppressions(repo_root: Path, budget: dict[str, Any]) -> list[str]:
    config = budget["suppressions"]
    python_files = _source_files(
        repo_root,
        "backend",
        [".py"],
        [".venv", "__pycache__", "logs", "raw", "uploads"],
    )
    frontend_files = _source_files(
        repo_root,
        "frontend/src",
        [".js", ".ts", ".vue"],
        ["vendor"],
    )
    frontend_files.extend(
        _source_files(repo_root, "frontend/tests", [".js", ".ts", ".vue"])
    )
    frontend_files.extend(_source_files(repo_root, "frontend/e2e", [".js", ".ts"]))

    actual = {
        "type_ignore": _count_python_comment_pattern(
            python_files, re.compile(r"#\s*type:\s*ignore\b")
        ),
        "noqa": _count_python_comment_pattern(python_files, re.compile(r"#\s*noqa\b")),
        "eslint_disable": _count_pattern(
            frontend_files, re.compile(r"\beslint-disable(?:-next-line|-line)?\b")
        ),
    }
    violations = []
    for name, count in actual.items():
        limit = int(config[f"{name}_max"])
        if count > limit:
            violations.append(f"suppressions: {name} increased to {count}; budget is {limit}")
    return violations


def _module_map(app_root: Path) -> dict[str, Path]:
    modules: dict[str, Path] = {}
    for path in app_root.rglob("*.py"):
        relative = path.relative_to(app_root.parent).with_suffix("")
        parts = list(relative.parts)
        if parts[-1] == "__init__":
            parts.pop()
        modules[".".join(parts)] = path
    return modules


def _resolved_imports(module: str, path: Path, tree: ast.AST) -> set[str]:
    package = module if path.stem == "__init__" else module.rpartition(".")[0]
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:
            base = package.split(".") if package else []
            if node.level > 1:
                base = base[: -(node.level - 1)]
            if node.module:
                base.extend(node.module.split("."))
            target = ".".join(base)
        else:
            target = node.module or ""
        if target:
            targets.add(target)
        if not node.module:
            targets.update(
                f"{target}.{alias.name}" if target else alias.name for alias in node.names
            )
    return targets


def _strongly_connected_components(graph: dict[str, set[str]]) -> list[list[str]]:
    next_index = 0
    indices: dict[str, int] = {}
    low_links: dict[str, int] = {}
    stack: list[str] = []
    active: set[str] = set()
    components: list[list[str]] = []

    def visit(module: str) -> None:
        nonlocal next_index
        indices[module] = next_index
        low_links[module] = next_index
        next_index += 1
        stack.append(module)
        active.add(module)

        for dependency in graph[module]:
            if dependency not in indices:
                visit(dependency)
                low_links[module] = min(low_links[module], low_links[dependency])
            elif dependency in active:
                low_links[module] = min(low_links[module], indices[dependency])

        if low_links[module] != indices[module]:
            return
        component: list[str] = []
        while stack:
            dependency = stack.pop()
            active.remove(dependency)
            component.append(dependency)
            if dependency == module:
                break
        if len(component) > 1 or module in graph[module]:
            components.append(sorted(component))

    for module in graph:
        if module not in indices:
            visit(module)
    return components


def backend_cycle_signatures(repo_root: Path, budget: dict[str, Any]) -> set[str]:
    app_root = repo_root / "backend" / "app"
    modules = _module_map(app_root)
    ignored = tuple(str(value) for value in budget["dependencies"].get("ignored_backend_prefixes", []))

    def is_ignored(module: str) -> bool:
        return any(module == prefix or module.startswith(f"{prefix}.") for prefix in ignored)

    graph: dict[str, set[str]] = {
        module: set() for module in modules if not is_ignored(module)
    }
    for module, path in modules.items():
        if module not in graph:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        graph[module] = {
            target
            for target in _resolved_imports(module, path, tree)
            if target in graph and target != module
        }
    return {"|".join(component) for component in _strongly_connected_components(graph)}


def check_backend_cycles(repo_root: Path, budget: dict[str, Any]) -> list[str]:
    allowed = set(budget["dependencies"].get("backend_cycle_signatures", []))
    actual = backend_cycle_signatures(repo_root, budget)
    return [f"dependencies: new backend cycle: {cycle}" for cycle in sorted(actual - allowed)]


def check_domain_boundaries(repo_root: Path) -> list[str]:
    domains_root = repo_root / "backend" / "app" / "domains"
    violations: list[str] = []
    for path in domains_root.glob("*/domain/**/*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        module = ".".join(path.relative_to(domains_root.parent.parent).with_suffix("").parts)
        for target in _resolved_imports(module, path, tree):
            if "infrastructure" in target.split("."):
                violations.append(
                    f"domain-boundary: {_relative_path(repo_root, path)} imports {target}"
                )
    return violations


def check_component_http_calls(repo_root: Path) -> list[str]:
    src_root = repo_root / "frontend" / "src"
    call_pattern = re.compile(r"\b(?:fetch|axios)\s*\(")
    import_pattern = re.compile(r"\bfrom\s+['\"]axios['\"]|\bimport\s*\(\s*['\"]axios['\"]")
    violations: list[str] = []
    for path in src_root.rglob("*"):
        if not path.is_file() or path.suffix not in {".js", ".ts", ".vue"}:
            continue
        if "components" not in path.relative_to(src_root).parts or "vendor" in path.parts:
            continue
        source = path.read_text(encoding="utf-8-sig", errors="replace")
        if call_pattern.search(source) or import_pattern.search(source):
            violations.append(f"frontend-boundary: direct HTTP transport in {_relative_path(repo_root, path)}")
    return violations


def check_obsolete_compatibility(repo_root: Path, budget: dict[str, Any]) -> list[str]:
    return [
        f"obsolete-compatibility: removed facade was recreated: {relative_path}"
        for relative_path in budget.get("obsolete_compatibility", {}).get("paths", [])
        if (repo_root / str(relative_path)).exists()
    ]


def check_coverage_contract(repo_root: Path, budget: dict[str, Any]) -> list[str]:
    workflow = (repo_root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    violations: list[str] = []
    for step_name, minimum in budget["coverage"]["ci_steps"].items():
        marker = f"- name: {step_name}"
        start = workflow.find(marker)
        if start < 0:
            violations.append(f"coverage: CI step is missing: {step_name}")
            continue
        next_step = workflow.find("\n      - name:", start + len(marker))
        block = workflow[start : next_step if next_step >= 0 else len(workflow)]
        expected = f"--cov-fail-under={int(minimum)}"
        if expected not in block:
            violations.append(f"coverage: {step_name} must retain {expected}")
    return violations


def collect_violations(repo_root: Path, budget: dict[str, Any]) -> list[str]:
    return [
        *check_file_sizes(repo_root, budget),
        *check_suppressions(repo_root, budget),
        *check_backend_cycles(repo_root, budget),
        *check_domain_boundaries(repo_root),
        *check_component_http_calls(repo_root),
        *check_obsolete_compatibility(repo_root, budget),
        *check_coverage_contract(repo_root, budget),
    ]


def main() -> int:
    budget = load_budget()
    violations = collect_violations(REPO_ROOT, budget)
    if violations:
        print("Quality budget failed:")
        for violation in violations:
            print(f"- {violation}")
        return 1
    print("Quality budget passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

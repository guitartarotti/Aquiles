from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_quality_budget_module() -> ModuleType:
    path = REPO_ROOT / "scripts" / "quality_budget.py"
    spec = importlib.util.spec_from_file_location("quality_budget", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


QUALITY_BUDGET = _load_quality_budget_module()


def _minimal_budget(*, max_lines: int = 5) -> dict[str, Any]:
    return {
        "file_size": {
            "rules": [
                {
                    "root": "backend/app",
                    "extensions": [".py"],
                    "max_lines": max_lines,
                    "exclude_parts": [],
                }
            ],
            "legacy": {},
        },
        "suppressions": {
            "type_ignore_max": 0,
            "noqa_max": 0,
            "eslint_disable_max": 0,
        },
        "dependencies": {
            "ignored_backend_prefixes": [],
            "backend_cycle_signatures": [],
        },
        "obsolete_compatibility": {"paths": []},
        "coverage": {"ci_steps": {}},
    }


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_repository_respects_the_quality_budget() -> None:
    budget = QUALITY_BUDGET.load_budget(REPO_ROOT / "quality-budget.toml")

    assert QUALITY_BUDGET.collect_violations(REPO_ROOT, budget) == []


def test_file_size_budget_rejects_new_oversized_files(tmp_path: Path) -> None:
    _write(tmp_path / "backend/app/new_service.py", "\n".join(f"line_{index} = 1" for index in range(6)))

    violations = QUALITY_BUDGET.check_file_sizes(tmp_path, _minimal_budget())

    assert violations == ["file-size: backend/app/new_service.py has 6 lines; budget is 5"]


def test_suppression_budget_rejects_increases(tmp_path: Path) -> None:
    _write(tmp_path / "backend/app/service.py", "value = call()  # type: ignore\nvalue = 1  # noqa: F841")
    _write(
        tmp_path / "frontend/src/components/Panel.vue",
        "<script>// eslint-disable-next-line no-console\nconsole.log('x')</script>",
    )

    violations = QUALITY_BUDGET.check_suppressions(tmp_path, _minimal_budget())

    assert violations == [
        "suppressions: type_ignore increased to 1; budget is 0",
        "suppressions: noqa increased to 1; budget is 0",
        "suppressions: eslint_disable increased to 1; budget is 0",
    ]


def test_dependency_budget_rejects_new_backend_cycles(tmp_path: Path) -> None:
    _write(tmp_path / "backend/app/__init__.py", "")
    _write(tmp_path / "backend/app/alpha.py", "import app.beta")
    _write(tmp_path / "backend/app/beta.py", "import app.alpha")

    violations = QUALITY_BUDGET.check_backend_cycles(tmp_path, _minimal_budget())

    assert violations == ["dependencies: new backend cycle: app.alpha|app.beta"]


def test_architecture_budget_rejects_outer_domain_imports_and_component_http(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "backend/app/domains/example/domain/model.py",
        "from app.domains.example.infrastructure.repository import Repository",
    )
    _write(
        tmp_path / "frontend/src/components/Panel.vue",
        "<script>fetch('/api/data')</script>",
    )

    domain_violations = QUALITY_BUDGET.check_domain_boundaries(tmp_path)
    frontend_violations = QUALITY_BUDGET.check_component_http_calls(tmp_path)

    assert domain_violations == [
        "domain-boundary: backend/app/domains/example/domain/model.py imports "
        "app.domains.example.infrastructure.repository"
    ]
    assert frontend_violations == [
        "frontend-boundary: direct HTTP transport in frontend/src/components/Panel.vue"
    ]


def test_quality_budget_rejects_recreated_compatibility_facades(tmp_path: Path) -> None:
    relative_path = "backend/app/api/options.py"
    _write(tmp_path / relative_path, "from . import options_routes\n")
    budget = _minimal_budget()
    budget["obsolete_compatibility"]["paths"] = [relative_path]

    violations = QUALITY_BUDGET.check_obsolete_compatibility(tmp_path, budget)

    assert violations == [
        "obsolete-compatibility: removed facade was recreated: backend/app/api/options.py"
    ]


def test_coverage_budget_rejects_a_lower_ci_floor(tmp_path: Path) -> None:
    workflow = """
jobs:
  quality:
    steps:
      - name: Test backend
        run: pytest --cov-fail-under=30
"""
    _write(tmp_path / ".github/workflows/ci.yml", workflow)
    budget = _minimal_budget()
    budget["coverage"]["ci_steps"] = {"Test backend": 31}

    violations = QUALITY_BUDGET.check_coverage_contract(tmp_path, budget)

    assert violations == ["coverage: Test backend must retain --cov-fail-under=31"]

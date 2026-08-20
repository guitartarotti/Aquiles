from __future__ import annotations

import ast
import json
import tomllib
from fnmatch import fnmatchcase
from pathlib import Path

from flask import Flask

from app.domains.catalog import DOMAIN_CATALOG

EXPECTED_DOMAINS = {
    "auth",
    "funds_flow",
    "graph",
    "macro",
    "market_data",
    "options",
    "reports",
    "simulations",
}


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _imports_api_layer(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.startswith("app.api") for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").startswith("app.api"):
                return True
            if node.level and node.module == "api":
                return True
    return False


def _import_targets(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            targets.add(node.module)
    return targets


def test_domain_catalog_has_unique_names_routes_and_prefixes() -> None:
    names = [domain.name for domain in DOMAIN_CATALOG]
    routes = [route for domain in DOMAIN_CATALOG for route in domain.routes]

    assert set(names) == EXPECTED_DOMAINS
    assert len(names) == len(set(names))
    assert len({id(route.blueprint) for route in routes}) == len(routes)
    assert len({route.url_prefix for route in routes}) == len(routes)
    assert all(route.url_prefix.startswith("/api/") for route in routes)


def test_every_api_module_is_owned_by_exactly_one_domain() -> None:
    api_dir = _backend_root() / "app" / "api"
    discovered = {
        f"app.api.{path.stem}" for path in api_dir.glob("*.py") if path.stem != "__init__"
    }
    ownership = [
        module
        for domain in DOMAIN_CATALOG
        for module in domain.owned_api_modules
        if module.startswith("app.api.")
    ]

    assert set(ownership) == discovered
    assert len(ownership) == len(set(ownership))


def test_services_do_not_depend_on_http_api_modules() -> None:
    service_paths = (_backend_root() / "app" / "services").rglob("*.py")
    offenders = [
        str(path.relative_to(_backend_root())) for path in service_paths if _imports_api_layer(path)
    ]

    assert offenders == []


def test_http_routes_do_not_import_concrete_infrastructure_adapters() -> None:
    app_root = _backend_root() / "app"
    route_paths = list((app_root / "api").rglob("*.py"))
    route_paths.extend(
        path
        for path in (app_root / "domains").rglob("*.py")
        if "api" in path.relative_to(app_root).parts
    )
    offenders = []

    for path in route_paths:
        for target in _import_targets(path):
            if "infrastructure" in target.split("."):
                offenders.append(f"{path.relative_to(app_root)} -> {target}")

    assert offenders == []


def test_runtime_code_does_not_call_global_singleton_accessors() -> None:
    app_root = _backend_root() / "app"
    offenders: list[str] = []

    for path in app_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get_instance"
            ):
                offenders.append(f"{path.relative_to(app_root)}:{node.lineno}")

    assert offenders == []


def test_api_factory_does_not_start_background_collectors() -> None:
    app_factory = (_backend_root() / "app" / "__init__.py").read_text(encoding="utf-8")

    assert "start_background_services" not in app_factory
    assert "threading.Thread" not in app_factory
    assert not (_backend_root() / "app" / "startup.py").exists()


def test_funds_flow_routes_are_domain_owned() -> None:
    from app.domains.funds_flow.api import routes

    assert routes.funds_flow_local_dashboard.__module__ == "app.domains.funds_flow.api.routes"
    assert not (_backend_root() / "app" / "api" / "funds_flow_local.py").exists()


def test_funds_flow_contains_the_required_internal_layers() -> None:
    domain_root = _backend_root() / "app" / "domains" / "funds_flow"
    expected = {"api", "application", "contracts", "domain", "infrastructure"}

    assert {path.name for path in domain_root.iterdir() if path.is_dir()} >= expected
    assert (domain_root / "api" / "routes.py").is_file()
    assert (domain_root / "application" / "use_cases.py").is_file()
    assert (domain_root / "contracts" / "models.py").is_file()
    assert (domain_root / "domain" / "rules.py").is_file()
    assert (domain_root / "infrastructure" / "json_repositories.py").is_file()


def test_inner_funds_flow_layers_do_not_depend_on_outer_layers() -> None:
    domain_root = _backend_root() / "app" / "domains" / "funds_flow"
    forbidden_by_layer = {
        "domain": {
            "api",
            "application",
            "contracts",
            "infrastructure",
            "flask",
            "pydantic",
            "services",
        },
        "application": {"api", "infrastructure", "flask", "services"},
        "contracts": {"api", "application", "infrastructure", "flask", "services"},
        "infrastructure": {"api", "application", "flask"},
    }
    offenders: list[str] = []

    for layer, forbidden in forbidden_by_layer.items():
        for path in (domain_root / layer).rglob("*.py"):
            for target in _import_targets(path):
                if forbidden.intersection(target.split(".")):
                    offenders.append(f"{path.relative_to(domain_root)} -> {target}")

    assert offenders == []


def test_cvm_cda_domain_core_is_pure_and_owned_by_market_data() -> None:
    app_root = _backend_root() / "app"
    domain_path = app_root / "domains" / "market_data" / "domain" / "cvm_cda.py"
    service_path = app_root / "services" / "cvm_cda_service.py"
    forbidden = {
        "api",
        "flask",
        "infrastructure",
        "pandas",
        "requests",
        "services",
        "sqlite3",
    }

    assert domain_path.is_file()
    assert all(
        not forbidden.intersection(target.split(".")) for target in _import_targets(domain_path)
    )

    service_tree = ast.parse(
        service_path.read_text(encoding="utf-8-sig"), filename=str(service_path)
    )
    migrated_functions = {
        "_asset_class_for",
        "_clamp",
        "_first_nonempty",
        "_maturity_bucket",
        "_month_from_text",
        "_month_label",
        "_norm_key",
        "_norm_text",
        "_parse_date_text",
        "_parse_iso_datetime",
        "_previous_months",
        "_safe_div",
        "_safe_float",
        "_source_block",
    }
    locally_defined = {node.name for node in service_tree.body if isinstance(node, ast.FunctionDef)}
    assert migrated_functions.isdisjoint(locally_defined)


def test_funds_flow_orchestrator_uses_official_source_adapters() -> None:
    service_path = _backend_root() / "app" / "services" / "funds_flow_local_service.py"
    tree = ast.parse(service_path.read_text(encoding="utf-8-sig"), filename=str(service_path))
    collect_method = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "collect"
    )
    calls = {
        ast.unparse(node.func) for node in ast.walk(collect_method) if isinstance(node, ast.Call)
    }

    assert {
        "self.cvm_source.load_informe_diario",
        "self.cvm_source.load_fund_registry",
        "self.anbima_source.load_funds",
        "self.b3_source.load_etfs",
        "self.b3_source.load_investor_participation",
        "self.b3_source.load_open_interest",
        "self.b3_source.load_monthly_investor_participation",
        "self.b3_source.load_market_data_report",
        "self.ici_source.load_global_flows",
    } <= calls
    assert not {
        "self._load_informe_diario",
        "self._load_cadastro",
        "self._load_anbima_funds",
        "self._load_b3_etfs",
        "self._load_b3_investor_participation",
        "self._load_b3_open_interest",
        "self._load_b3_investor_participation_monthly",
        "self._load_b3_market_data_report",
        "self._load_ici_global_flows",
    }.intersection(calls)


def test_official_source_adapters_do_not_delegate_to_legacy_service() -> None:
    app_root = _backend_root() / "app"
    service_path = app_root / "services" / "funds_flow_local_service.py"
    infrastructure_root = app_root / "domains" / "funds_flow" / "infrastructure"
    provider_files = {
        "anbima_source.py",
        "b3_source.py",
        "cvm_source.py",
        "ici_source.py",
    }
    legacy_entrypoints = {
        "_load_anbima_funds",
        "_load_b3_etfs",
        "_load_b3_investor_participation",
        "_load_b3_investor_participation_monthly",
        "_load_b3_market_data_report",
        "_load_b3_open_interest",
        "_load_cadastro",
        "_load_ici_global_flows",
        "_load_informe_diario",
    }

    service_tree = ast.parse(service_path.read_text(encoding="utf-8-sig"))
    service_methods = {
        node.name for node in ast.walk(service_tree) if isinstance(node, ast.FunctionDef)
    }

    assert legacy_entrypoints.isdisjoint(service_methods)
    assert not (app_root / "services" / "funds_flow_anbima_ici.py").exists()
    assert {path.name for path in infrastructure_root.glob("*_source.py")} >= provider_files
    for file_name in provider_files:
        source_path = infrastructure_root / file_name
        assert all("services" not in target.split(".") for target in _import_targets(source_path))


def test_strict_typing_gate_covers_domains_composition_and_collectors() -> None:
    config_path = _backend_root() / "pyproject.toml"
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    mypy_config = config["tool"]["mypy"]
    typed_paths = set(mypy_config["files"])

    assert mypy_config["strict"] is True
    required_paths = {
        "app/domains",
        "app/infrastructure",
        "app/workers",
        "app/container.py",
        "app/services/cvm_cda_manager.py",
        "app/services/funds_flow_local_manager.py",
        "app/services/macro_participant_heatmap_manager.py",
    }
    assert all(
        any(fnmatchcase(required_path, configured_path) for configured_path in typed_paths)
        for required_path in required_paths
    )


def test_modular_route_packages_have_no_compatibility_facades() -> None:
    api_root = _backend_root() / "app" / "api"

    for facade_name in ("options.py", "simulation.py"):
        assert not (api_root / facade_name).exists()

    expected_modules = {
        "options_routes": {
            "market.py",
            "modeling.py",
            "open_interest.py",
            "shared.py",
            "snapshots.py",
            "volatility.py",
            "volume.py",
        },
        "simulation_routes": {
            "activity.py",
            "catalog.py",
            "entities.py",
            "execution.py",
            "interviews.py",
            "preparation.py",
            "shared.py",
        },
    }
    for package_name, expected_files in expected_modules.items():
        package = api_root / package_name
        actual_files = {path.name for path in package.glob("*.py") if path.name != "__init__.py"}
        assert actual_files == expected_files
        assert all(
            len(path.read_text(encoding="utf-8").splitlines()) < 600
            for path in package.glob("*.py")
        )
        assert all(
            "../../uploads" not in path.read_text(encoding="utf-8")
            for path in package.glob("*.py")
        )


def test_options_and_simulation_route_inventory_is_stable() -> None:
    from app.api import options_bp, simulation_bp

    app = Flask(__name__)
    app.register_blueprint(options_bp, url_prefix="/api/options")
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    options_rules = [
        rule for rule in app.url_map.iter_rules() if rule.rule.startswith("/api/options")
    ]
    simulation_rules = [
        rule for rule in app.url_map.iter_rules() if rule.rule.startswith("/api/simulation")
    ]

    assert len(options_rules) == 64
    assert len(simulation_rules) == 31
    assert len({(rule.rule, tuple(sorted(rule.methods))) for rule in options_rules}) == 64
    assert len({(rule.rule, tuple(sorted(rule.methods))) for rule in simulation_rules}) == 31


def test_simulation_report_lookup_uses_configured_upload_folder(
    tmp_path: Path, monkeypatch
) -> None:
    from app.api.simulation_routes import shared

    reports_root = tmp_path / "reports"
    for report_id, created_at in (("older", "2026-08-18T10:00:00"), ("latest", "2026-08-19T10:00:00")):
        report_root = reports_root / report_id
        report_root.mkdir(parents=True)
        (report_root / "meta.json").write_text(
            json.dumps(
                {
                    "simulation_id": "simulation-1",
                    "report_id": report_id,
                    "created_at": created_at,
                }
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr(shared.Config, "UPLOAD_FOLDER", str(tmp_path))

    assert shared._get_report_id_for_simulation("simulation-1") == "latest"

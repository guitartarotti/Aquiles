from __future__ import annotations

import math

from app.services.cvm_cda_graph_service import CvmCdaGraphService


def _service() -> CvmCdaGraphService:
    service = CvmCdaGraphService.__new__(CvmCdaGraphService)
    service.group_id = "funds_flow_local:cvm_cda:test"
    return service


class _Driver:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def execute_query(self, query: str, **params):
        self.calls.append((query, params))
        return [], None, None


class _Node(dict):
    def __init__(self, labels, **props):
        super().__init__(props)
        self.labels = set(labels)


class _Rel(dict):
    def __init__(self, rel_type: str, element_id: str, **props):
        super().__init__(props)
        self.type = rel_type
        self.element_id = element_id


def test_cda_graph_prepares_deterministic_nodes_edges_and_counts() -> None:
    service = _service()
    month = "2026-07"
    funds = [
        {
            "fund_cnpj": "12.345.678/0001-90",
            "fund_name": "Fundo Alpha",
            "fund_type": "FIF / Acoes",
            "dt_comptc": "2026-07-31",
            "pl": 100_000_000,
            "position_value": 80_000_000,
            "abs_position_value": 82_000_000,
            "holding_count": 2,
            "issuer_count": 2,
            "asset_count": 2,
        }
    ]
    target_edges = [
        {
            "fund_cnpj": "12.345.678/0001-90",
            "target": "foreign",
            "target_label": "Exterior",
            "long_value": 20_000_000,
            "short_value": -2_000_000,
            "net_value": 18_000_000,
            "gross_value": 22_000_000,
            "target_pct_pl": 18,
            "holdings_count": 1,
            "issuers_count": 1,
            "assets_count": 1,
        }
    ]
    positions = [
        {
            "fund_cnpj": "12.345.678/0001-90",
            "asset_code": "PETR4",
            "asset_desc": "PETROBRAS PN",
            "isin": "BRPETRACNPR6",
            "asset_class": "Acoes",
            "asset_subclass": "Acoes locais",
            "issuer_name": "Petrobras",
            "issuer_doc": "33.000.167/0001-01",
            "country": "Brasil",
            "country_code": "BR",
            "value_market": 30_000_000,
            "pl": 100_000_000,
            "source_block": "BLOCO_4",
            "position_rank": 1,
            "is_foreign": False,
            "is_derivative": False,
        },
        {
            "fund_cnpj": "12.345.678/0001-90",
            "asset_code": "DOLQ26",
            "asset_desc": "Futuro de dolar",
            "asset_class": "Derivativos",
            "issuer_name": "B3",
            "country": "Brasil",
            "value_market": -2_000_000,
            "pl": 100_000_000,
            "source_block": "BLOCO_8",
            "position_rank": 2,
            "is_foreign": True,
            "is_derivative": True,
        },
    ]

    payload = service._prepare_graph_payload(
        month,
        {
            "imported_at": "2026-08-10T10:00:00Z",
            "latest_dt": "2026-07-31",
            "total_pl": 100_000_000,
            "total_rows": 2,
            "total_position_value": 28_000_000,
            "total_confidential_value": 0,
        },
        funds,
        target_edges,
        positions,
    )

    assert payload["month_node"]["name"] == "2026-07"
    assert payload["fund_nodes"][0]["cnpj"] == "12345678000190"
    assert payload["counts"]["funds"] == 1
    assert payload["counts"]["assets"] == 2
    assert payload["counts"]["issuers"] == 2
    assert payload["counts"]["positions"] == 2
    assert payload["position_edges"][0]["side"] == "long"
    assert payload["position_edges"][1]["side"] == "short"
    assert payload["position_edges"][0]["pct_pl"] == 30
    assert payload["target_edges"][0]["net_value"] == 18_000_000

    second = service._prepare_graph_payload(month, {}, funds, target_edges, positions)
    assert [row["id"] for row in second["asset_nodes"]] == [
        row["id"] for row in payload["asset_nodes"]
    ]


def test_cda_graph_writes_payload_and_formats_neo4j_records() -> None:
    service = _service()
    payload = service._prepare_graph_payload(
        "2026-07",
        {},
        [{"fund_cnpj": "123", "fund_name": "Fundo", "fund_type": "FIF"}],
        [],
        [
            {
                "fund_cnpj": "123",
                "asset_code": "VALE3",
                "asset_desc": "Vale ON",
                "asset_class": "Acoes",
                "issuer_name": "Vale",
                "country": "Brasil",
                "value_market": 100,
                "pl": 1_000,
            }
        ],
    )
    driver = _Driver()
    service._ensure_constraints(driver)
    service._write_payload(driver, payload)
    assert len(driver.calls) >= 20
    assert any("MERGE (n:CdaFund" in query for query, _params in driver.calls)
    assert any("HOLDS_POSITION" in query for query, _params in driver.calls)

    source = _Node(["CdaFund"], id="fund-1", uuid="fund-1", name="Fundo", cnpj="123", pl=1_000)
    target = _Node(
        ["CdaAsset"],
        id="asset-1",
        uuid="asset-1",
        name="Vale ON",
        asset_class="Acoes",
    )
    rel = _Rel(
        "HOLDS_POSITION",
        "rel-1",
        id="rel-1",
        side="long",
        value_market=100,
        pct_pl=10,
        asset_class="Acoes",
    )
    graph = service._records_to_graph([{"source": source, "rel": rel, "target": target}])
    assert graph["node_count"] == 2
    assert graph["edge_count"] == 1
    assert "R$ 100" in graph["edges"][0]["fact"]
    assert "PL reportado" in graph["nodes"][0]["summary"]

    service._append_context_edges(driver, graph, "2026-07")
    assert graph["node_count"] == 2


def test_cda_graph_normalizes_labels_symbols_ids_and_rankings() -> None:
    service = _service()
    assert service.schema()["graph"]["group_id"] == service.group_id
    assert service._fund_in_clause(["123", "", "456"]) == ("?,?", ["123", "456"])
    assert service._fund_in_clause([]) == ("''", [])
    assert service._activity_direction(10) == "inflow"
    assert service._activity_direction(-1) == "outflow"
    assert service._activity_direction("bad") == "neutral"
    assert service._is_generic_asset_text("Valores a pagar")
    assert not service._is_generic_asset_text("PETR4")
    assert service._option_side_from_row({"asset_desc": "Opcao de compra CALL"}) == "call"
    assert service._option_side_from_row({"asset_desc": "Opcao de venda PUT"}) == "put"
    assert service._option_position_role_from_row({"tp_aplic": "Lancador"}) == "written"
    assert service._option_position_role_from_row({"tp_aplic": "Titular"}) == "holder"
    assert service._infer_option_underlying({"asset_code": "PETRA320"}) == "PETR"
    assert service._infer_equity_underlying({"asset_code": "VALE3"}) == "VALE"
    assert service._infer_symbol_prefix("DOLQ26") == "USD/BRL"
    assert service._infer_symbol_prefix("BOVA11") == "BOVA11"
    assert service._infer_symbol_prefix("33.000.167/0001-01") == ""
    assert service._symbol_text("Ação", "petr4") == "ACAO PETR4"
    assert service._digits("12.345/0001-90") == "12345000190"
    assert service._clean_label("  Alpha  ", "fallback") == "Alpha"
    assert service._clean_label("", "fallback") == "fallback"
    assert service._num("1.5") == 1.5
    assert service._num("bad") == 0
    assert service._bool("1") is True
    assert service._bool("0") is False
    assert math.isnan(service._json_value(float("nan")))
    assert service._month_label("2026-07") == "2026-07"
    assert service._month_label("bad") == "bad"
    assert service._fmt_brl(1_500_000) == "R$ 1.5 mi"
    assert service._fmt_pct(12.345) == "12.35%"
    assert len(service._hash("a", "b")) == 24
    assert list(service._chunks(list(range(5)), 2)) == [[0, 1], [2, 3], [4]]

    ranked = service._rank_rows(
        [{"reported_activity": 10}, {"reported_activity": -5}, {"reported_activity": 0}]
    )
    assert [row["rank"] for row in ranked] == [1, 2, 3]
    assert [row["activity_direction"] for row in ranked] == ["inflow", "outflow", "neutral"]
    assert service._asset_trail_key("PETR4", "Acoes", "long") == service._asset_trail_key(
        "PETR4", "Acoes", "long"
    )


def test_cda_graph_serialization_and_fact_formatting_cover_edge_cases() -> None:
    service = _service()
    assert service._clean_value(None) is None
    assert service._clean_value(True) is True
    assert service._clean_value(3) == 3
    assert service._clean_value(float("inf")) is None
    assert service._clean_value([1, None, float("nan"), "x"]) == [1, "x"]
    assert service._clean_value({"key": "value"}) == '{"key": "value"}'
    assert service._props({"ok": 1, "missing": None}) == {"ok": 1}
    assert service._json_value([1, 2]) == "[1, 2]"
    assert service._asset_key({"isin": "BRTEST"}) == "BRTEST"
    assert service._asset_key(
        {"source_block": "BLOCO_9", "fund_cnpj": "123", "position_rank": 4}
    ) == "BLOCO_9:123:4"
    assert service._fund_id("2026-07", "12.3").startswith("cda:2026-07:fund:")
    assert service._asset_id("2026-07", "PETR4", "Acoes").startswith(
        "cda:2026-07:asset:"
    )
    assert service._issuer_id("2026-07", "Petrobras", "33000167").startswith(
        "cda:2026-07:issuer:"
    )
    assert service._target_id("2026-07", "foreign").startswith("cda:2026-07:target:")
    assert service._edge_id("position", "a", "b").startswith("cda:edge:")

    assert service._node_summary(["CdaAsset"], {"asset_class": "Credito"}).startswith(
        "Ativo CDA"
    )
    assert "Emissor" in service._node_summary(["CdaIssuer"], {})
    assert service._node_summary(["CdaMonth"], {}) == "No deterministico do grafo CVM CDA."
    source = {"name": "Fundo Alpha"}
    target = {"name": "Exterior"}
    assert "valor liquido" in service._edge_fact(
        "HAS_TARGET_EXPOSURE",
        source,
        target,
        {"net_value": 10, "gross_value": 12, "target_pct_pl": 1.2},
    )
    assert "emissor" in service._edge_fact("ISSUED_BY", source, target, {}).lower()
    assert "camada" in service._edge_fact("CLASSIFIED_AS", source, target, {})
    assert "geografica" in service._edge_fact("LOCATED_IN", source, target, {})
    assert "REPORTED_IN" in service._edge_fact("REPORTED_IN", source, target, {})

    assert service._fmt_brl(2_000_000_000_000) == "R$ 2.00 tri"
    assert service._fmt_brl(-2_000_000_000) == "-R$ 2.0 bi"
    assert service._fmt_brl(999) == "R$ 999"
    assert service._fmt_brl("bad") == "R$ 0"
    assert service._fmt_pct("bad") == "0.00%"
    assert service._month_label("202607") == "2026-07"

    driver = _Driver()
    service._merge_nodes(driver, "CdaFund", [])
    service._merge_relationships(driver, "HOLDS_POSITION", [])
    assert driver.calls == []

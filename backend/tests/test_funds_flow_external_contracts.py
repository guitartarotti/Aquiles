from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from app.domains.funds_flow.contracts.source_catalog import (
    ANBIMA_CONSOLIDATED_DAILY_ENDPOINT,
    ANBIMA_PUBLICATION_POPULATE,
    ANBIMA_STRAPI_BASE_URL,
    B3_FUNDS_LISTED_SEARCH_URL,
    CVM_CKAN_PACKAGE_URL,
)
from app.domains.funds_flow.infrastructure import (
    AnbimaFundsFlowAdapter,
    B3FundsFlowAdapter,
    CvmFundsFlowAdapter,
    IciFundsFlowAdapter,
    anbima_source,
    b3_source,
    cvm_source,
    ici_source,
)


class FakeResponse:
    def __init__(
        self,
        *,
        payload: dict[str, Any] | None = None,
        text: str = "",
        url: str = "https://example.test/source",
    ) -> None:
        self._payload = payload or {}
        self.text = text
        self.content = text.encode("utf-8")
        self.url = url

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


def test_cvm_ckan_contract_discovers_monthly_resources_and_uses_memory_cache(
    tmp_path: Path, monkeypatch: Any
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_get(url: str, **kwargs: Any) -> FakeResponse:
        calls.append((url, kwargs))
        return FakeResponse(
            payload={
                "success": True,
                "result": {
                    "resources": [
                        {
                            "name": "inf_diario_fi_202607.zip",
                            "url": "https://dados.cvm.gov.br/inf_diario_fi_202607.zip",
                        }
                    ]
                },
            }
        )

    monkeypatch.setattr(cvm_source.requests, "get", fake_get)
    adapter = CvmFundsFlowAdapter(raw_dir=str(tmp_path / "raw"), timeout_seconds=13.0)

    first = adapter._discover_cvm_informe_resources()
    second = adapter._discover_cvm_informe_resources()

    assert first == second == {"202607": "https://dados.cvm.gov.br/inf_diario_fi_202607.zip"}
    assert calls == [
        (
            CVM_CKAN_PACKAGE_URL,
            {"params": {"id": "fi-doc-inf_diario"}, "timeout": 13.0},
        )
    ]


def test_anbima_strapi_contract_normalizes_publication_and_document_links(
    tmp_path: Path, monkeypatch: Any
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_get(url: str, **kwargs: Any) -> FakeResponse:
        calls.append((url, kwargs))
        return FakeResponse(
            url=f"{url}?populate=template",
            payload={
                "data": {
                    "attributes": {
                        "updatedAt": "2026-08-20T10:00:00Z",
                        "publishedAt": "2026-08-20T09:00:00Z",
                        "template": {
                            "title": "Consolidado diario",
                            "content": "Fluxo <strong>oficial</strong>",
                            "publication_document": [
                                {
                                    "id": 7,
                                    "title": "Arquivo diario",
                                    "display_date": "2026-08-20T00:00:00Z",
                                    "file": {
                                        "data": [
                                            {
                                                "attributes": {
                                                    "url": "/uploads/consolidado.xlsx",
                                                    "name": "consolidado.xlsx",
                                                    "mime": "application/vnd.ms-excel",
                                                }
                                            }
                                        ]
                                    },
                                }
                            ],
                        },
                    }
                }
            },
        )

    monkeypatch.setattr(anbima_source.requests, "get", fake_get)
    adapter = AnbimaFundsFlowAdapter(raw_dir=str(tmp_path / "raw"), timeout_seconds=11.0)

    publication = adapter._fetch_anbima_publication(ANBIMA_CONSOLIDATED_DAILY_ENDPOINT)

    assert publication["title"] == "Consolidado diario"
    assert publication["content_text"] == "Fluxo oficial"
    assert publication["documents"][0]["file_url"] == (
        f"{ANBIMA_STRAPI_BASE_URL}/uploads/consolidado.xlsx"
    )
    assert calls == [
        (
            f"{ANBIMA_STRAPI_BASE_URL}{ANBIMA_CONSOLIDATED_DAILY_ENDPOINT}",
            {
                "params": {"populate": ANBIMA_PUBLICATION_POPULATE},
                "timeout": 45,
            },
        )
    ]


def test_b3_listed_funds_contract_encodes_request_and_preserves_response_shape(
    tmp_path: Path, monkeypatch: Any
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_get(url: str, **kwargs: Any) -> FakeResponse:
        calls.append((url, kwargs))
        return FakeResponse(
            payload={
                "page": {"totalPages": 1},
                "results": [{"id": 1, "acronym": "BOVA11", "name": "ETF Ibovespa"}],
            }
        )

    monkeypatch.setattr(b3_source.requests, "get", fake_get)
    adapter = B3FundsFlowAdapter(raw_dir=str(tmp_path / "raw"), timeout_seconds=9.0)
    request_payload = {
        "language": "pt-br",
        "typeFund": "ETF",
        "pageNumber": 1,
        "pageSize": 120,
    }

    response = adapter._request_b3_funds_listed(request_payload)

    encoded = calls[0][0].rsplit("/", 1)[-1]
    decoded = json.loads(base64.b64decode(encoded).decode("utf-8"))
    assert decoded == request_payload
    assert calls[0][0].startswith(f"{B3_FUNDS_LISTED_SEARCH_URL}/GetListFunds/")
    assert calls[0][1]["timeout"] == 60
    assert response["results"][0]["acronym"] == "BOVA11"


def test_ici_html_contract_is_cached_and_resolves_encoded_relative_links(
    tmp_path: Path, monkeypatch: Any
) -> None:
    calls: list[str] = []
    html = (
        '<a href="/research/stats/etf/etfs_07_26?x=1&amp;y=2">Release</a>'
        "<table><tr><th>Segment</th><th>Assets</th></tr>"
        "<tr><td>Equity</td><td>10.5</td></tr></table>"
    )

    def fake_get(url: str, **_kwargs: Any) -> FakeResponse:
        calls.append(url)
        return FakeResponse(text=html, url=url)

    monkeypatch.setattr(ici_source.requests, "get", fake_get)
    adapter = IciFundsFlowAdapter(raw_dir=str(tmp_path / "raw"), timeout_seconds=8.0)
    cache_path = tmp_path / "raw" / "ici" / "release.html"

    first = adapter._download_text_cached(
        "https://www.ici.org/releases", str(cache_path), force=False
    )
    second = adapter._download_text_cached(
        "https://www.ici.org/releases", str(cache_path), force=False
    )
    release_url = adapter._first_ici_href(
        first,
        "https://www.ici.org/releases",
        r"/research/stats/etf/etfs_[0-9]{2}_[0-9]{2}",
    )

    assert first == second == html
    assert calls == ["https://www.ici.org/releases"]
    assert release_url == "https://www.ici.org/research/stats/etf/etfs_07_26?x=1&y=2"
    assert adapter._html_tables(first) == [[["Segment", "Assets"], ["Equity", "10.5"]]]

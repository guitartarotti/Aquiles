"""
B3OpenInterestScraper
=====================
Faz scraping diario da pagina de Posicoes em Aberto de Opcoes da B3:

  https://www.b3.com.br/.../posicoes-em-aberto-....htm?dataConsulta=DD/MM/YYYY&f=0

A pagina e server-side rendered (SSR) — os dados ja vem no HTML,
porem protegida por Cloudflare. Por isso usa Playwright (headless Chromium)
para garantir o fingerprint correto.

Retorna lista de dict com campos:
  symbol          str   ticker B3 (ex: "IBOVE180E2")
  strike          float preco de exercicio (ex: 181000.0)
  oi_total        int   quantidade total em aberto (coberto + trava + descoberto)
  oi_coberto      int
  oi_trava        int
  oi_descoberto   int
  n_titular       int   numero de clientes titulares (long)
  n_lancador      int   numero de clientes lancadores (short)
  type            str   "CALL" | "PUT" (inferido do serie_id)
  date            str   YYYY-MM-DD

Uso:
  scraper = B3OpenInterestScraper()
  rows = scraper.fetch(date="2026-05-14")   # -> list[dict]
"""
from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any

from ..utils.logger import get_logger

logger = get_logger("aquiles.b3_oi_scraper")

# URL base da pagina B3 de posicoes em aberto de opcoes de indices
_B3_OI_URL = (
    "https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/"
    "market-data/consultas/mercado-a-vista/opcoes/posicoes-em-aberto/"
    "posicoes-em-aberto-8AA8D0CC9D71B1D8019D787F6DE95B34.htm"
)

# Headers de navegador realista para evitar bloqueio Cloudflare (fallback requests)
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def _parse_br_int(value: str) -> int:
    """Converte string no formato brasileiro '10.040' para int 10040."""
    if not value or not value.strip():
        return 0
    clean = value.strip().replace(".", "").replace(",", "").replace("\xa0", "")
    try:
        return int(clean)
    except ValueError:
        return 0


def _parse_br_float(value: str) -> float:
    """Converte '181.000,00' para 181000.0"""
    if not value or not value.strip():
        return 0.0
    clean = value.strip().replace(".", "").replace(",", ".").replace("\xa0", "")
    try:
        return float(clean)
    except ValueError:
        return 0.0


def _infer_type(symbol: str) -> str:
    """
    Infere CALL/PUT pelo codigo de serie B3.
    Opcoes de IBOV: IBOVE = CALL, IBOVQ = PUT (convencionalmente)
    Regra geral: letras A-L = CALL, M-Z = PUT (codificacao B3 para opcoes).
    """
    if not symbol or len(symbol) < 5:
        return "UNKNOWN"
    # Pega o 5o caractere (ex: IBOV[E]180E2 -> 'E')
    series_char = symbol[4].upper() if len(symbol) > 4 else ""
    return "CALL" if series_char in "ABCDEFGHIJKL" else "PUT"


def _parse_tables_from_html(html: str, trade_date: str) -> list[dict[str, Any]]:
    """
    Extrai todas as linhas de OI das tabelas HTML da B3.
    Ignora linhas de cabecalho, subtotais e totais.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("beautifulsoup4 nao instalado — pip install beautifulsoup4")
        return []

    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    logger.info("B3 OI scraper: %d tabelas encontradas no HTML", len(tables))

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for table in tables:
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if len(cells) < 7:
                continue

            symbol_raw = cells[0].strip()

            # Filtra: cabecalhos, totais, linhas vazias
            if not symbol_raw:
                continue
            if symbol_raw.lower() in {"serie", "série", "total", "subtotal"}:
                continue
            if not re.match(r"^[A-Z]{4,}", symbol_raw):
                continue
            if symbol_raw in seen:
                continue
            seen.add(symbol_raw)

            try:
                strike = _parse_br_float(cells[1])
                oi_coberto    = _parse_br_int(cells[2])
                oi_trava      = _parse_br_int(cells[3])
                oi_descoberto = _parse_br_int(cells[4])
                oi_total      = _parse_br_int(cells[5])
                n_titular     = _parse_br_int(cells[6]) if len(cells) > 6 else 0
                n_lancador    = _parse_br_int(cells[7]) if len(cells) > 7 else 0
            except (IndexError, ValueError):
                continue

            rows.append({
                "symbol":        symbol_raw,
                "strike":        strike,
                "oi_total":      oi_total,
                "oi_coberto":    oi_coberto,
                "oi_trava":      oi_trava,
                "oi_descoberto": oi_descoberto,
                "n_titular":     n_titular,
                "n_lancador":    n_lancador,
                "type":          _infer_type(symbol_raw),
                "date":          trade_date,
            })

    return rows


class B3OpenInterestScraper:
    """
    Scraper de Posicao em Aberto de Opcoes da B3.
    Usa Playwright (headless) como motor principal — necessario para
    passar o Cloudflare. Faz fallback para requests se Playwright
    nao estiver disponivel.
    """

    def __init__(self, timeout_ms: int = 30_000, wait_for_idle: bool = True):
        self.timeout_ms = timeout_ms
        self.wait_for_idle = wait_for_idle

    # ─── API publica ─────────────────────────────────────────────────────

    def fetch(self, date: str | None = None) -> list[dict[str, Any]]:
        """
        Busca posicoes em aberto da B3 para a data informada.

        Parametros
        ----------
        date : str, opcional
            Data no formato 'YYYY-MM-DD'. Padrao: hoje.

        Retorna
        -------
        list[dict]
            Lista de registros de OI. Vazia se a data nao tiver dados
            (feriado, fim de semana, etc.).
        """
        trade_date = date or datetime.now().date().isoformat()
        date_br = _iso_to_br(trade_date)
        url = f"{_B3_OI_URL}?dataConsulta={date_br}&f=0"

        logger.info("B3 OI scraper: buscando posicoes para %s", trade_date)

        html = self._fetch_html_playwright(url)
        if not html:
            logger.warning("B3 OI scraper: sem HTML via Playwright — tentando requests")
            html = self._fetch_html_requests(url)

        if not html:
            logger.error("B3 OI scraper: nao foi possivel obter o HTML da B3 para %s", trade_date)
            return []

        rows = _parse_tables_from_html(html, trade_date)
        logger.info("B3 OI scraper: %d contratos com OI para %s", len(rows), trade_date)
        return rows

    def fetch_range(
        self,
        date_from: str,
        date_to: str,
        business_days_only: bool = True,
        sleep_between_s: float = 2.0,
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Busca OI para um intervalo de datas.
        Retorna dict: {YYYY-MM-DD -> lista de rows}.
        Util para backfill historico.
        """
        from datetime import timedelta

        start = datetime.fromisoformat(date_from).date()
        end   = datetime.fromisoformat(date_to).date()
        result: dict[str, list[dict[str, Any]]] = {}

        current = start
        while current <= end:
            if business_days_only and current.weekday() >= 5:
                current += timedelta(days=1)
                continue
            iso = current.isoformat()
            rows = self.fetch(iso)
            if rows:
                result[iso] = rows
            time.sleep(sleep_between_s)
            current += timedelta(days=1)

        return result

    # ─── Internos ─────────────────────────────────────────────────────────

    def _fetch_html_playwright(self, url: str) -> str | None:
        """Usa Playwright headless para renderizar a pagina e retornar o HTML."""
        try:
            from playwright.sync_api import TimeoutError as PWTimeout
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.debug("Playwright nao disponivel")
            return None

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
                context = browser.new_context(
                    user_agent=_BROWSER_HEADERS["User-Agent"],
                    locale="pt-BR",
                    extra_http_headers={"Accept-Language": "pt-BR,pt;q=0.9"},
                )
                page = context.new_page()
                try:
                    page.goto(url, timeout=self.timeout_ms, wait_until="networkidle")
                    # Aguarda a tabela de dados aparecer
                    page.wait_for_selector("table tr td", timeout=15_000)
                except PWTimeout:
                    logger.warning("B3 OI scraper Playwright: timeout aguardando tabela")
                html = page.content()
                browser.close()
                return html
        except Exception as exc:
            logger.error("B3 OI scraper Playwright: erro — %s", exc)
            return None

    def _fetch_html_requests(self, url: str) -> str | None:
        """Fallback: usa requests (pode falhar por Cloudflare)."""
        try:
            import requests as _req

            session = _req.Session()
            session.headers.update(_BROWSER_HEADERS)

            # Acessa home primeiro para pegar cookies Cloudflare
            session.get("https://www.b3.com.br/", timeout=10)
            r = session.get(url, timeout=20)
            if r.status_code == 200 and "<table" in r.text:
                return r.text
            logger.warning("B3 OI scraper requests: HTTP %s ou sem tabela", r.status_code)
            return None
        except Exception as exc:
            logger.error("B3 OI scraper requests: erro — %s", exc)
            return None


# ─── Utilitarios ────────────────────────────────────────────────────────────

def _iso_to_br(date_iso: str) -> str:
    """'2026-05-14' -> '14/05/2026'"""
    try:
        d = datetime.fromisoformat(date_iso).date()
        return d.strftime("%d/%m/%Y")
    except Exception:
        return date_iso

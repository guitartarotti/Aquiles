"""
Usa Playwright para renderizar a pagina da B3 e capturar as chamadas de API
de Posicoes em Aberto (Open Interest).
"""
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright

DATE = "14/05/2026"
PAGE_URL = (
    "https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/"
    "consultas/mercado-a-vista/opcoes/posicoes-em-aberto/"
    "posicoes-em-aberto-8AA8D0CC9D71B1D8019D787F6DE95B34.htm"
    f"?dataConsulta={DATE}&f=0"
)

api_calls = []

def on_request(request):
    url = request.url
    if any(kw in url.lower() for kw in ["position", "aberto", "opcao", "option", "sistemaswebb3", "api"]):
        api_calls.append({"type": "request", "method": request.method, "url": url})

def on_response(response):
    url = response.url
    if any(kw in url.lower() for kw in ["position", "aberto", "opcao", "option", "sistemaswebb3"]):
        try:
            body = response.body()
            if body and len(body) > 50:
                api_calls.append({
                    "type": "response",
                    "status": response.status,
                    "url": url,
                    "preview": body[:500].decode("utf-8", errors="replace")
                })
        except Exception:
            pass

print("Iniciando Playwright...")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        locale="pt-BR",
        extra_http_headers={
            "Accept-Language": "pt-BR,pt;q=0.9",
        }
    )
    page = context.new_page()

    # Captura todas as requests/responses
    page.on("request", on_request)
    page.on("response", on_response)

    print(f"Navegando para: {PAGE_URL}")
    page.goto(PAGE_URL, timeout=30000, wait_until="networkidle")

    # Espera a tabela carregar
    try:
        page.wait_for_selector("table, .datatable, [class*='table'], [class*='grid']", timeout=10000)
        print("Tabela encontrada!")
    except Exception:
        print("Tabela nao encontrada via selector")

    # Pega o conteudo atual da pagina
    content = page.content()

    # Extrai dados visiveis da pagina
    try:
        # Tenta pegar o texto de qualquer tabela
        tables = page.query_selector_all("table")
        print(f"Tabelas na pagina: {len(tables)}")
        for i, t in enumerate(tables[:3]):
            print(f"\n  Tabela {i+1}:")
            rows = t.query_selector_all("tr")
            for row in rows[:5]:
                cells = row.query_selector_all("td, th")
                print(f"    {[c.inner_text().strip() for c in cells]}")
    except Exception as e:
        print(f"Erro ao extrair tabelas: {e}")

    # Extrai o texto geral para encontrar dados
    body_text = page.inner_text("body")
    # Procura por palavras-chave de OI
    lines_with_data = [l.strip() for l in body_text.split("\n") if any(
        kw in l for kw in ["IBOV", "posicao", "aberto", "contratos", "OI", "000"]
    ) and len(l.strip()) > 10]
    print(f"\nLinhas com dados relevantes: {len(lines_with_data)}")
    for l in lines_with_data[:20]:
        print(f"  {l[:120]}")

    browser.close()

print("\n" + "=" * 60)
print("  CHAMADAS DE API CAPTURADAS")
print("=" * 60)
if api_calls:
    for call in api_calls:
        print(f"\n[{call['type'].upper()}]")
        if "method" in call:
            print(f"  {call['method']} {call['url']}")
        else:
            print(f"  [{call.get('status')}] {call['url']}")
            if "preview" in call:
                print(f"  {call['preview'][:300]}")
else:
    print("Nenhuma chamada de API relevante capturada")

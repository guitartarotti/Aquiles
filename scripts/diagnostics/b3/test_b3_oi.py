"""
Descobre e testa endpoints da B3 para Posicoes em Aberto (Open Interest) de Opcoes.
Tambem testa o arquivo COTAHIST diario.
"""
import sys, os, io, re, json, zipfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import requests

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Referer": "https://www.b3.com.br/",
    "Origin": "https://www.b3.com.br",
    "X-Requested-With": "XMLHttpRequest",
})

DATE_STR = "14/05/2026"
DATE_ISO = "2026-05-14"

print("=" * 60)
print("  PARTE 1 — Descobre API B3 de Posicoes em Aberto")
print("=" * 60)

# 1. Carrega pagina principal para pegar cookies
page_url = f"https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/consultas/mercado-a-vista/opcoes/posicoes-em-aberto/posicoes-em-aberto-8AA8D0CC9D71B1D8019D787F6DE95B34.htm?dataConsulta={DATE_STR}&f=0"
main = session.get(page_url, timeout=15)
print(f"Pagina principal: HTTP {main.status_code}")
print(f"Cookies: {dict(session.cookies)}")

# Extrai referencias a APIs no HTML
api_refs = re.findall(r'sistemaswebb3[a-zA-Z0-9\-\.]*\.b3\.com\.br[^\s"\'<>]*', main.text)
print(f"Referencias sistemaswebb3: {set(api_refs)}")

# Extrai qualquer URL de endpoint
all_urls = re.findall(r'https?://[a-zA-Z0-9\-\.]+\.b3\.com\.br/[^\s"\'<>]+', main.text)
print(f"URLs B3 no HTML: {set(all_urls)}")

# Procura padroes de endpoint
endpoints = re.findall(r'["\']/((?:open|position|posicao|aberto|opcoes|option)[^"\']+)["\']', main.text, re.I)
print(f"Padroes de endpoint: {endpoints[:10]}")

print()
print("=" * 60)
print("  PARTE 2 — Testa endpoints sistemaswebb3")
print("=" * 60)

test_endpoints = [
    f"https://sistemaswebb3-listados.b3.com.br/openPositionProxy/openPosition/GetOpenPosition?language=pt-br&pageNumber=1&pageSize=100&dateRef={DATE_ISO}",
    f"https://sistemaswebb3-listados.b3.com.br/openPositionProxy/openPosition/GetOpenPosition?language=pt-br&pageNumber=1&pageSize=100&dateRef={DATE_ISO}&market=70",
    f"https://sistemaswebb3-listados.b3.com.br/openPositionProxy/openPosition/GetOpenPosition?language=pt-br&pageNumber=1&pageSize=100&dateRef={DATE_STR}",
    f"https://sistemaswebb3-derivativos.b3.com.br/openPositionProxy/openPosition/GetOpenPosition?language=pt-br&pageNumber=1&pageSize=100&dateRef={DATE_ISO}",
    # Tenta com header Accept diferente
]

for url in test_endpoints:
    try:
        r = session.get(url, timeout=10)
        qs = url.split("?")[1][:70] if "?" in url else url[-50:]
        if r.status_code == 200 and len(r.text) > 50:
            print(f"  [OK {r.status_code}] {qs}")
            print(f"     {r.text[:400]}")
        else:
            print(f"  [{r.status_code}] {qs}")
    except Exception as e:
        print(f"  [ERR] {e}")

print()
print("=" * 60)
print("  PARTE 3 — COTAHIST diario (arquivo B3 com OI embutido?)")
print("=" * 60)

# O COTAHIST diario contem dados de todas as negociacoes
cot_url = f"https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_D14052026.ZIP"
try:
    r = session.get(cot_url, timeout=30)
    print(f"COTAHIST: HTTP {r.status_code}, tamanho={len(r.content)} bytes")
    if r.status_code == 200:
        # Descomprime e le as primeiras linhas
        import io as _io
        z = zipfile.ZipFile(_io.BytesIO(r.content))
        print(f"  Arquivos no ZIP: {z.namelist()}")
        txt = z.read(z.namelist()[0]).decode("latin-1")
        lines = txt.split("\n")
        print(f"  Total de linhas: {len(lines)}")
        # Mostra o header (linha 0) e primeiras linhas de opcoes
        print(f"  Header: {lines[0][:100]}")
        # TIPO=1 sao dados de mercado; busca linhas de opcoes (TIPOMT=070 opcoes sobre ind)
        opcoes = [l for l in lines[1:] if len(l) > 10 and l[0:2] == "01" and l[24:27].strip() in ("70","071","074")]
        print(f"  Registros tipo opcoes (mercado=70): {len(opcoes)}")
        if opcoes:
            print(f"  Exemplo: {opcoes[0][:120]}")
            # Campos do COTAHIST (formato fixo)
            ex = opcoes[0]
            print(f"    DATPRE={ex[2:10]}  CODBDI={ex[10:12]}  CODNEG={ex[12:24]}  NOMRES={ex[27:39]}  TIPOMT={ex[24:27]}")
            print(f"    PREOFV={ex[49:59]}  PREMIN={ex[59:69]}  PREMED={ex[69:79]}  PREULT={ex[79:89]}  PREOFC={ex[89:99]}")
            print(f"    TOTNEG={ex[147:152]}  QUATOT={ex[152:170]}  VOLTOT={ex[170:188]}")
            # Nota: QUATOT = quantidade total negociada (NAO eh open interest)
            print("\n  NOTA: COTAHIST tem QUATOT (vol negociado) mas NAO tem open interest diretamente")
except Exception as e:
    print(f"  ERRO: {e}")
    import traceback; traceback.print_exc()

print()
print("=" * 60)
print("  PARTE 4 — Testa scraping direto da pagina com Selenium-like")
print("=" * 60)

# Tenta usar requests com session para simular o browser mais fielmente
session2 = requests.Session()
session2.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
})

# Primeiro acessa pagina principal
r0 = session2.get("https://www.b3.com.br/", timeout=10)
print(f"Home: HTTP {r0.status_code}")

# Agora tenta o JSON endpoint com a sessao completa
api_candidates = [
    "https://sistemaswebb3-listados.b3.com.br/openPositionProxy/openPosition/GetOpenPosition?language=pt-br&pageNumber=1&pageSize=50&dateRef=2026-05-14",
]
session2.headers.update({
    "Accept": "application/json, */*",
    "X-Requested-With": "XMLHttpRequest",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Referer": page_url,
})
for url in api_candidates:
    r = session2.get(url, timeout=10)
    print(f"  [{r.status_code}] OI endpoint: {r.text[:200] if r.status_code == 200 else ''}")

"""
Investiga o arquivo COTAHIST e descobre o formato real das opcoes.
Tambem descobre a URL correta do OI da B3 via engenharia reversa do JS.
"""
import sys, os, io, re, json, zipfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import requests

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Referer": "https://www.b3.com.br/",
})

# ─── 1. Inspeciona COTAHIST em detalhe ────────────────────────────────────
print("=" * 60)
print("  PARTE 1 — COTAHIST: tipos de mercado e opcoes")
print("=" * 60)

cot_url = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_D14052026.ZIP"
r = session.get(cot_url, timeout=30)
z = zipfile.ZipFile(io.BytesIO(r.content))
txt = z.read(z.namelist()[0]).decode("latin-1")
lines = [l for l in txt.split("\n") if l.startswith("01")]  # so registros diarios

print(f"Total de registros diarios: {len(lines)}")

# Mostra distribuicao de TPMERC (posicoes [24:27] no registro)
from collections import Counter
tpmerc = Counter(l[24:27] for l in lines if len(l) > 27)
print("\nDistribuicao TPMERC:")
for k, v in sorted(tpmerc.items()):
    label = {
        "010": "A Vista",
        "012": "Exercicio Call",
        "013": "Exercicio Put",
        "017": "Leilao",
        "020": "Fracionario",
        "030": "Termo",
        "050": "Futuro retencao",
        "060": "Futuro mov cont",
        "070": "Opcao Compra (CALL)",
        "080": "Opcao Venda (PUT)",
    }.get(k, "?")
    print(f"  {k}: {v:6d} registros  ({label})")

# Extrai opcoes de indices (CODBDI=82 = opcoes de indices)
calls = [l for l in lines if len(l) > 27 and l[24:27] == "070"]
puts  = [l for l in lines if len(l) > 27 and l[24:27] == "080"]
print(f"\nTotal CALLS no COTAHIST: {len(calls)}")
print(f"Total PUTS  no COTAHIST: {len(puts)}")

# Mostra exemplo de call de IBOV
ibov_calls = [l for l in calls if "IBOV" in l[12:24].upper()]
print(f"\nCALLS com 'IBOV' no ticker: {len(ibov_calls)}")
if ibov_calls:
    ex = ibov_calls[0]
    print(f"  Exemplo raw: {ex[:200]}")
    # Layout COTAHIST (1-indexed no manual, 0-indexed em Python):
    # 01-02: TIPREG  [0:2]
    # 03-10: DATPRE  [2:10]
    # 11-12: CODBDI  [10:12]
    # 13-24: CODNEG  [12:24]  (ticker)
    # 25-27: TPMERC  [24:27]
    # 28-39: NOMRES  [27:39]
    # 40-49: ESPECI  [39:49]
    # 50-52: PRAZOT  [49:52]
    # 53-56: MODREF  [52:56]
    # 57-69: PREOFV  [56:69]  preco abertura
    # 70-82: PREMIN  [69:82]  preco minimo
    # 83-95: PREMED  [82:95]  preco medio
    # 96-108: PREULT [95:108] preco ultimo (fechamento)
    # 109-121: PREOFC [108:121] preco melhor oferta compra
    # 122-134: PREOFI [121:134] preco melhor oferta venda
    # 135-147: TOTNEG [134:147] total negocios
    # 148-162: QUATOT [147:162] quantidade total de titulos
    # 163-181: VOLTOT [162:181] volume total
    # 182-202: PREOFV (strike para opcoes) [181:202]
    # 203-202: INDOPC [202:210] indicador de correcao
    # 211-221: DATVEN [210:221] data de vencimento
    # 231-245: FATCOT [230:245]
    # 246-249: PTOEXE [245:252] preco de exercicio em pontos
    # 253:     CODISI [252:264]
    # 265:     DISMES [264:270]
    print(f"  DATPRE={ex[2:10]}  CODBDI={ex[10:12]}  CODNEG={ex[12:24].strip()}")
    print(f"  TPMERC={ex[24:27]}  NOMRES={ex[27:39].strip()}  ESPECI={ex[39:49].strip()}")
    print(f"  PREABR={ex[56:69].strip()}  PREMIN={ex[69:82].strip()}  PREMED={ex[82:95].strip()}")
    print(f"  PREULT={ex[95:108].strip()}  TOTNEG={ex[134:147].strip()}  QUATOT={ex[147:162].strip()}")
    print(f"  VOLTOT={ex[162:181].strip()}")
    print(f"  STRIKE={ex[181:202].strip()}  DATVEN={ex[210:221].strip()}")

print("\nNOTA: COTAHIST tem QUATOT (volume negociado) mas NAO tem Open Interest!")

# ─── 2. Descobre arquivo especifico de OI da B3 ───────────────────────────
print()
print("=" * 60)
print("  PARTE 2 — Busca arquivo especifico de OI da B3")
print("=" * 60)

# B3 publica dados de posicao em aberto em arquivos separados
# Formato tipico: PA (posicao em aberto)
oi_candidates = [
    "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/PA14052026.ZIP",
    "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/PA140526.ZIP",
    "https://bvmf.bmfbovespa.com.br/InstDados/PABOV14052026.ZIP",
    "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/PosicaoAberto14052026.ZIP",
    # Formato alternativo
    "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/NEGOCIOS_D14052026.ZIP",
    "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/OpcoesPosicaoAberto14052026.ZIP",
    "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/OpcoesPosicaoAberto.zip",
]
for url in oi_candidates:
    try:
        rr = session.get(url, timeout=8)
        fname = url.split("/")[-1]
        if rr.status_code == 200 and not rr.text.startswith("<!"):
            print(f"  [OK] {fname} ({len(rr.content)} bytes)")
        else:
            print(f"  [{rr.status_code}] {fname}")
    except Exception as e:
        print(f"  [ERR] {url.split('/')[-1]}: {e}")

# ─── 3. Inspeciona JS do portal para achar API real ───────────────────────
print()
print("=" * 60)
print("  PARTE 3 — Engenharia reversa do JS do portal B3")
print("=" * 60)

# Pega a pagina e extrai scripts
page = session.get(
    "https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/consultas/mercado-a-vista/opcoes/posicoes-em-aberto/posicoes-em-aberto-8AA8D0CC9D71B1D8019D787F6DE95B34.htm",
    timeout=15
)
# Extrai URLs de scripts
script_srcs = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', page.text, re.I)
print(f"Scripts externos: {len(script_srcs)}")
for s in script_srcs[:10]:
    print(f"  {s}")

# Procura por qualquer referencia a API/dados nos scripts externos
for src in script_srcs[:5]:
    if src.startswith("//"):
        src = "https:" + src
    elif src.startswith("/"):
        src = "https://www.b3.com.br" + src
    try:
        js = session.get(src, timeout=10)
        if js.status_code == 200:
            # Busca por URLs de API
            api_hits = re.findall(r'["\']https?://sistemaswebb3[^"\']+["\']', js.text)
            open_pos = re.findall(r'["\'][^"\']*(?:openPosition|posicao|aberto|GetOpen)[^"\']*["\']', js.text, re.I)
            if api_hits or open_pos:
                print(f"\n  ENCONTRADO em {src.split('/')[-1][:50]}:")
                for h in (api_hits + open_pos)[:5]:
                    print(f"    {h}")
    except Exception as e:
        pass

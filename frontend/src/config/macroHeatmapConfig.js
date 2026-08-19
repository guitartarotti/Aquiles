export const FAIR_VALUE_DISPLAY_STABILITY_WINDOW_MINUTES = 15
export const FAIR_VALUE_DISPLAY_STABILITY_SAMPLE_LIMIT = 3

export const RANGE_OPTIONS = [
  { key: 'day', label: 'dia', minutes: null },
  { key: '60m', label: '60m', minutes: 60 },
  { key: '30m', label: '30m', minutes: 30 },
]

export const TIMEFRAME_OPTIONS = [
  { minutes: 1, label: '1m' },
  { minutes: 3, label: '3m' },
  { minutes: 5, label: '5m' },
  { minutes: 10, label: '10m' },
]

export const PARTICIPANT_SCOPE_OPTIONS = [
  { value: 'foreign', label: 'estrangeiro' },
  { value: 'retail', label: 'varejo' },
]

export const PARTICIPANT_SIDE_OPTIONS = [
  { value: 'buy', label: 'compras' },
  { value: 'sell', label: 'vendas' },
  { value: 'both', label: 'os dois' },
]

export const PRESSURE_COHORTS = [
  { key: 'net', label: 'net' },
  { key: 'foreign', label: 'foreign' },
  { key: 'retail', label: 'retail' },
]

export const VALUE_COHORT_OPTIONS = PRESSURE_COHORTS

export const VALUE_LEVEL_TYPE_OPTIONS = [
  { key: 'poc', label: 'POC' },
  { key: 'value_area_low', label: 'VAL' },
  { key: 'value_area_high', label: 'VAH' },
]

export const INDICATOR_METRIC_OPTIONS = [
  { key: 'pressure', label: 'inv pressure' },
  { key: 'efficiency', label: 'delta eff' },
]

export const INDICATOR_COHORT_OPTIONS = PRESSURE_COHORTS

export const HISTOGRAM_MODE_OPTIONS = [
  { key: 'off', label: 'ocultar' },
  { key: 'cumulative', label: 'acumulado' },
]

export const REGIME_CHART_MODE_OPTIONS = [
  { key: 'off', label: 'ocultar' },
  { key: 'on', label: 'mostrar' },
]

export const CORRELATION_LOOKBACK_OPTIONS = [
  { days: 1, label: '1 dia' },
  { days: 2, label: '2 dias' },
  { days: 3, label: '3 dias' },
]

export const CORRELATION_HORIZON_OPTIONS = [
  { minutes: 1, label: '1m' },
  { minutes: 5, label: '5m' },
  { minutes: 15, label: '15m' },
]

export const CORRELATION_MODE_OPTIONS = [
  { key: 'pure', label: 'puro' },
  { key: 'neural', label: 'rede neural' },
]

export const CAPTURED_FACTOR_DISPLAY_OPTIONS = [
  { key: 'day_pct', label: 'var % dia' },
  { key: 'rebase_100', label: 'rebase 100' },
  { key: 'delta_raw', label: 'delta abs' },
]

export const CORRELATION_SERIES_COLORS = [
  '#38bdf8',
  '#f97316',
  '#22c55e',
  '#fbbf24',
  '#a78bfa',
  '#fb7185',
  '#14b8a6',
  '#f43f5e',
  '#84cc16',
  '#e879f9',
  '#f59e0b',
  '#60a5fa',
]

export const ANNOTATION_LEGEND_ITEMS = [
  { type: 'bull_trap', shortLabel: 'BT', label: 'bull trap' },
  { type: 'sell_trap', shortLabel: 'ST', label: 'sell trap' },
  { type: 'retail_buying_top', shortLabel: 'VT', label: 'varejo compra topo' },
  { type: 'retail_selling_bottom', shortLabel: 'VF', label: 'varejo vende fundo' },
  { type: 'foreign_buy_aligned', shortLabel: 'FC', label: 'gringa compra cenario' },
  { type: 'foreign_sell_aligned', shortLabel: 'FV', label: 'gringa vende cenario' },
  { type: 'short_squeeze', shortLabel: 'SQ', label: 'short squeeze' },
  { type: 'long_flush', shortLabel: 'LF', label: 'long flush' },
  { type: 'thin_liquidity', shortLabel: 'LQ', label: 'liquidez fina' },
  { type: 'foreign_absorption_buy', shortLabel: 'AB', label: 'absorcao compra' },
  { type: 'foreign_absorption_sell', shortLabel: 'AV', label: 'absorcao venda' },
  { type: 'stop_above', shortLabel: 'SA', label: 'stop acima' },
  { type: 'stop_below', shortLabel: 'SB', label: 'stop abaixo' },
  { type: 'retail_contra_trend', shortLabel: 'CT', label: 'varejo contratendencia' },
]

export const POOL_OVERLAY_OPTIONS = [
  { key: 'short_cover', label: 'short cover', shortLabel: 'SC', color: '#60a5fa', description: 'zona de cobertura de shorts acima do preco' },
  { key: 'long_flush', label: 'long flush', shortLabel: 'LF', color: '#f97316', description: 'zona de liquidacao de longs abaixo do preco' },
  { key: 'traps', label: 'traps', shortLabel: 'TR', color: '#fbbf24', description: 'armadilhas de bull trap ou sell trap em regioes vulneraveis' },
  { key: 'walls', label: 'walls', shortLabel: 'WL', color: '#a78bfa', description: 'parede de liquidez proxima do preco, de bid ou oferta' },
  { key: 'inventory_poc', label: 'inventory POC', shortLabel: 'POC', color: '#22c55e', description: 'ponto de maior concentracao de inventario sintetico' },
  { key: 'two_way', label: 'two-way', shortLabel: 'TW', color: '#94a3b8', description: 'inventario bilateral, briga de dois lados sem dominancia clara' },
]

export const GAMMA_OVERLAY_OPTIONS = [
  { key: 'positive', label: 'gamma positiva', shortLabel: 'G+', color: '#38bdf8', description: 'regioes de pinning e amortecimento de movimento' },
  { key: 'negative', label: 'gamma negativa', shortLabel: 'G-', color: '#fb7185', description: 'regioes de aceleracao e chase de dealer' },
  { key: 'special', label: 'faixas especiais', shortLabel: 'SP', color: '#fbbf24', description: 'zero pressure, pinning, acceleration e decompression bands' },
]

export const FAIR_VALUE_FEATURE_OPTIONS = [
  { key: 'price', label: 'preco', shortLabel: 'PX', color: '#e2e8f0' },
  { key: 'fair_value', label: 'fv novo', shortLabel: 'FV2', color: '#fbbf24' },
  { key: 'legacy_fair_value', label: 'fv antigo', shortLabel: 'FV1', color: '#94a3b8' },
  { key: 'legacy_bands', label: 'bandas antigas', shortLabel: 'B1', color: '#64748b' },
  { key: 'quality_adjusted', label: 'fv quality', shortLabel: 'QFV', color: '#34d399' },
  { key: 'bands', label: 'bandas', shortLabel: 'BND', color: '#38bdf8' },
  { key: 'quality_ribbon', label: 'quality ribbon', shortLabel: 'QRB', color: '#22c55e' },
  { key: 'gamma', label: 'gamma', shortLabel: 'GAM', color: '#a78bfa' },
  { key: 'distortion', label: 'distorcao', shortLabel: 'DIS', color: '#f97316' },
  { key: 'macro_legs', label: 'pernas macro', shortLabel: 'LEG', color: '#34d399' },
]

export const FAIR_VALUE_CORE_LEG_OPTIONS = [
  { key: 'rates', label: 'Core Rates', shortLabel: 'RT', color: '#38bdf8', description: 'curva DI local e pressao de juros Brasil' },
  { key: 'curve_medium_long', label: 'Core Curve Medium Long', shortLabel: 'CML', color: '#60a5fa', description: 'trecho medio-longo da curva DI e risco de duration/fiscal' },
  { key: 'equity', label: 'Core Equity', shortLabel: 'EQ', color: '#22c55e', description: 'equities globais, EWZ e EEM puxando beta de risco' },
  { key: 'equity_brazil', label: 'Core Brazil Equity', shortLabel: 'BRQ', color: '#16a34a', description: 'setores domesticos, breadth local e heavyweights de Brasil' },
  { key: 'credit', label: 'Core Credit', shortLabel: 'CR', color: '#f59e0b', description: 'credito soberano e spread Brasil no bloco core' },
  { key: 'credit_brazil', label: 'Core Brazil Credit', shortLabel: 'BRC', color: '#f97316', description: 'CDS Brasil, bonds soberanos e corporativos locais' },
  { key: 'fx', label: 'Core FX', shortLabel: 'FX', color: '#ef4444', description: 'dolar, funding e pressao cambial direta sobre o indice' },
  { key: 'commodities', label: 'Core Commodities', shortLabel: 'CM', color: '#a78bfa', description: 'minerio, petroleo e cobre como suporte macro do Brasil' },
  { key: 'us_rates', label: 'Core US Rates', shortLabel: 'USR', color: '#14b8a6', description: 'Treasuries e OIS dos EUA como perna de juros globais' },
]

export const FAIR_VALUE_SHADOW_LEG_OPTIONS = [
  { key: 'credit_shadow', label: 'Shadow Credit', shortLabel: 'SCR', color: '#f97316', description: 'stress de credito que ajusta qualidade e convergencia' },
  { key: 'bond_quality', label: 'Shadow Bonds BR', shortLabel: 'SBD', color: '#84cc16', description: 'qualidade dos bonds Brasil e suporte de duration local' },
  { key: 'corporate_credit', label: 'Shadow Corporate Credit', shortLabel: 'SCC', color: '#fb7185', description: 'credito corporativo EM/HY deteriorando ou melhorando o sinal' },
  { key: 'em_stress', label: 'Shadow EM Stress', shortLabel: 'SEM', color: '#f43f5e', description: 'stress relativo de emergentes que fragiliza o beta Brasil' },
  { key: 'funding', label: 'Shadow Funding', shortLabel: 'SFD', color: '#eab308', description: 'funding global, DXY, yen e liquidez implicita' },
  { key: 'volatility', label: 'Shadow Volatility', shortLabel: 'SVL', color: '#c084fc', description: 'volatilidade implicita e risco de ampliacao de bandas' },
  { key: 'brazil_relative', label: 'Shadow Brazil Relative', shortLabel: 'SBR', color: '#2dd4bf', description: 'Brasil relativo ao resto de EM no bloco de qualidade' },
  { key: 'sovereign_credit', label: 'Shadow Sovereign', shortLabel: 'SSV', color: '#fda4af', description: 'risco soberano Brasil como penalizacao shadow dedicada' },
]

export const FAIR_VALUE_RANKING_WINDOW_OPTIONS = [
  { key: 'session', label: 'Dia geral', minutes: null },
  { key: '5m', label: 'Ultimos 5m', minutes: 5 },
  { key: '15m', label: 'Ultimos 15m', minutes: 15 },
]

export const FAIR_VALUE_HELP_TEXT = {
  core_fv: 'Preco teorico do modelo core, sem aplicar os ajustes de qualidade e shadow.',
  quality_fv: 'Fair value ajustado pelo shadow. E o core apos penalidades ou reforcos de qualidade.',
  distortion: 'Distancia entre o preco atual e o fair value. Negativo = preco abaixo do fair value; positivo = acima.',
  quality_pulse: 'Combina a mudanca do quality FV contra o core, a saude do bloco e o implicit sentiment. Serve para mostrar se o shadow esta ficando mais comprador, mais vendedor ou neutro na janela recente.',
  ribbon: 'Faixa de tolerancia do fair value ajustado. Quando alarga, a leitura esta menos convicta.',
  risk_quality: 'Penalidade qualitativa do shadow sobre o sinal. Baixo = pouca fragilidade; alto = mais stress no sinal.',
  coherence: 'Quanto core, shadow e preco contam a mesma historia. Mais alto = leitura mais consistente.',
  convergence_probability: 'Probabilidade estimada de o preco caminhar de volta para o fair value.',
  regime_break_probability: 'Probabilidade estimada de ruptura do regime atual, reduzindo a validade do fair value.',
  briefing_distortion: 'Dist = distancia em pontos entre o preco atual do indice e o fair value principal do modelo.',
  briefing_convergence: 'Conv = probabilidade estimada de o preco caminhar de volta para o fair value nas condicoes atuais.',
  briefing_break: 'Break = probabilidade de o regime atual falhar ou romper antes da convergencia do preco.',
}

export const CURVE_HELP_TEXT = {
  shape: 'Shape do dia usando os ODFs da planilha. Bear steepening = toda a curva abre, mas o miolo/longa abrem mais do que a curta. Bull flattening = curva alivia e achata.',
  regime: 'Regime macro provavel inferido do desenho curto-belly-longo e da curva de inflacao implicita: inflacionario, fiscal/duration, contracao, desinflacionario ou misto.',
  inclination: 'Termometro da inclinacao do dia. Combina o steepening/flattening intraday com a inclinacao geometrica da curva nominal por vertice.',
  medium_long: 'Leitura do trecho medio-longo da DI. Pressionando indica duration, fiscal ou premio de prazo dominando essa parte da curva.',
  fiscal: 'Acende quando a abertura relativa da longa e do slope sugere risco fiscal/duration mais forte que um simples movimento paralelo.',
  curve_impact: 'Quanto a leitura de curva local esta contribuindo, em pontos, para o fair value do indice.',
  short_change: 'Variacao media da ponta curta do dia (F27/F28).',
  belly_change: 'Variacao media do belly do dia (F29-F32). Quando lidera a alta, costuma sinalizar aperto/inflação mais concentrado no miolo.',
  long_change: 'Variacao media da ponta longa do dia (F33/F35).',
  level_change: 'Movimento medio da curva inteira no dia.',
  slope_change: 'Mudanca da inclinacao entre longa e curta. Positivo = mais inclinada; negativo = mais achatada.',
  twist_change: 'Movimento relativo do belly contra curta e longa.',
  geometric_angle: 'Angulo geometrico da curva nominal usando os niveis atuais por vertice. Ajuda a ver o shape absoluto, nao so a variacao do dia.',
  absolute_shape: 'Shape absoluto da curva nominal neste instante: positiva, invertida ou flat.',
  implied_inflation: 'Curva das taxas implicitas de inflacao (BRII). Ajuda a separar risco inflacionario de risco fiscal puro.',
  probable_driver: 'Explicacao curta do principal vetor do movimento da curva hoje.',
  curve_confidence: 'Confianca da classificacao atual de curva.',
  rates_contribution: 'Impacto total do bloco de juros/rates no fair value.',
  fiscal_score: 'Intensidade do componente fiscal/duration dentro da leitura da curva.',
  duration_score: 'Pressao do trecho medio-longo sobre o regime local.',
}

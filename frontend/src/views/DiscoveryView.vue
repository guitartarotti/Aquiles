<template>
  <div
    class="discovery-root"
    :class="{ 'capture-mode': isCaptureMode }"
    @mousemove="onMouseMove"
    @mouseup="onMouseUp"
    @mouseenter="discoveryHovered = true"
    @mouseleave="discoveryHovered = false"
  >

    <!-- Status bar -->
    <DiscoveryStatusBar
      v-if="!isCaptureMode"
      :oplab="connOplab"
      :backend="connBackend"
      :tracker="trackerRunning"
      :spot="spotPrice"
      :trackedSymbols="trackedSymbols"
      :eventCount="eventCount"
      @refresh="refreshAll"
    />

    <!-- Toolbar -->
    <div v-if="!isCaptureMode" class="discovery-toolbar">
      <div class="toolbar-left">
        <button class="tb-btn primary" @click="openPicker()">
          <span>＋</span> Adicionar widget
        </button>
        <button class="tb-btn" @click="arrangeGrid" title="Organizar em grade">⊞ Grade</button>
        <button class="tb-btn" @click="clearAll" title="Limpar tela">✕ Limpar</button>
      </div>
      <div class="toolbar-center">
        <select class="tb-select" v-model="activeUnderlying" @change="refreshModel">
          <option v-for="u in underlyings" :key="u.value" :value="u.value">{{ u.label }}</option>
        </select>
        <span class="tb-refresh-info" v-if="lastFetch">
          Dados: {{ timeSinceFetch }}
        </span>
      </div>
      <div class="toolbar-right">
        <button class="tb-btn" @click="refreshModel" :class="{ loading: fetchingModel }">
          {{ fetchingModel ? '…' : '⟳' }} Atualizar modelo
        </button>
      </div>
    </div>

    <!-- Canvas -->
    <div class="discovery-canvas" ref="canvasEl">
      <WidgetShell
        v-for="w in widgets"
        :key="w.id"
        :widget="w"
        @start-drag="startDrag"
        @start-resize="startResize"
        @close="closeWidget"
        @reload="reloadWidget"
      >
        <!-- Route to correct widget component -->
        <component
          :is="widgetComponent(w.type)"
          v-bind="widgetProps(w)"
        />
      </WidgetShell>

      <!-- Empty state -->
      <div v-if="!widgets.length && !isCaptureMode" class="discovery-empty">
        <div class="empty-icon">◈</div>
        <div class="empty-title">Discovery vazio</div>
        <div class="empty-sub">Clique em <b>+ Adicionar widget</b> para começar</div>
        <div class="empty-presets">
          <button class="preset-btn" @click="loadPreset('overview')">Vista Geral</button>
          <button class="preset-btn" @click="loadPreset('greeks')">Greeks Dashboard</button>
          <button class="preset-btn" @click="loadPreset('flow')">Flow Monitor</button>
        </div>
      </div>
    </div>

    <!-- Keyboard-triggered widget search -->
    <div v-if="quickSearchOpen" class="quick-search-panel" @mousedown.stop>
      <div class="quick-search-box">
        <div class="quick-search-kicker">Adicionar widget</div>
        <input
          ref="quickSearchInput"
          v-model="quickSearchQuery"
          class="quick-search-input"
          type="search"
          autocomplete="off"
          spellcheck="false"
          placeholder="Digite sigla, nome ou descricao do widget..."
          @keydown.enter.prevent="addQuickSearchSelection"
          @keydown.esc.prevent="closeQuickSearch"
          @keydown.down.prevent="moveQuickSearch(1)"
          @keydown.up.prevent="moveQuickSearch(-1)"
          @input="quickSearchIndex = 0"
        />
        <div class="quick-search-help">Enter adiciona o melhor resultado · Esc fecha</div>
        <div class="quick-search-results">
          <button
            v-for="(def, index) in quickSearchResults"
            :key="def.type"
            class="quick-result-card"
            :class="{ active: index === quickSearchIndex }"
            @mousemove="quickSearchIndex = index"
            @click="addWidget(def)"
          >
            <span class="quick-result-preview" aria-hidden="true">
              <img v-if="widgetPreviewUrl(def)" :src="widgetPreviewUrl(def)" :alt="def.title" />
              <span v-else>{{ def.icon }}</span>
            </span>
            <span class="quick-result-copy">
              <span class="quick-result-title">
                <span class="quick-result-icon">{{ def.icon }}</span>
                {{ def.title }}
              </span>
              <span class="quick-result-desc">{{ def.desc }}</span>
            </span>
          </button>
          <div v-if="!quickSearchResults.length" class="quick-search-empty">
            Nenhum widget encontrado para "{{ quickSearchQuery }}".
          </div>
        </div>
      </div>
    </div>

    <!-- Widget picker modal -->
    <Teleport to="body">
      <div v-if="showPicker" class="modal-overlay" @click.self="closePicker">
        <div class="modal-box">
          <div class="modal-header">
            <span class="modal-title">Adicionar widget</span>
            <button class="modal-close" @click="closePicker">✕</button>
          </div>
          <div class="modal-search">
            <input
              ref="pickerSearchInput"
              v-model="pickerQuery"
              class="modal-search-input"
              type="search"
              autocomplete="off"
              spellcheck="false"
              placeholder="Busque por sigla, nome, tema ou descricao..."
              @keydown.enter.prevent="addPickerSelection"
              @keydown.esc.prevent="closePicker"
            />
            <span class="modal-search-count">{{ filteredWidgetDefs.length }} widgets</span>
          </div>
          <div class="modal-grid" :class="{ 'modal-list': pickerHasQuery }">
            <button
              v-for="def in filteredWidgetDefs"
              :key="def.type"
              class="picker-card"
              @click="addWidget(def)"
            >
              <span class="picker-preview" aria-hidden="true">
                <img v-if="widgetPreviewUrl(def)" :src="widgetPreviewUrl(def)" :alt="def.title" />
                <span v-else>{{ def.icon }}</span>
              </span>
              <span class="picker-content">
                <span class="picker-topline">
                  <span class="picker-icon">{{ def.icon }}</span>
                  <span class="picker-name">{{ def.title }}</span>
                </span>
                <span class="picker-desc">{{ def.desc }}</span>
                <span v-if="pickerHasQuery" class="picker-details">{{ def.details }}</span>
                <span v-if="pickerHasQuery" class="picker-keywords">{{ formatKeywords(def) }}</span>
              </span>
            </button>
            <div v-if="!filteredWidgetDefs.length" class="modal-empty">
              Nenhum widget encontrado para "{{ pickerQuery }}".
            </div>
          </div>
        </div>
      </div>
    </Teleport>

  </div>
</template>

<script setup>
import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, ref } from 'vue'
import DiscoveryStatusBar from '@/components/discovery/DiscoveryStatusBar.vue'
import WidgetShell        from '@/components/discovery/WidgetShell.vue'
import {
  arrangeDiscoveryGrid,
  DISCOVERY_LAYOUT_STORAGE_KEY,
  getNextWidgetSequence,
  normalizeDiscoveryZStack,
  parseDiscoveryLayout,
  serializeDiscoveryLayout,
} from '@/utils/discoveryLayout'

import {
  getLatestOptionsModel,
  getVolumeTrackerStatus,
  startVolumeTracker,
  getSnapshotByStrike,
  getB3OiLatest,
  getLiveSpot,
} from '@/api/options'

const WIDGET_PREVIEWS = import.meta.glob('../assets/discovery/widget-previews/*.png', {
  eager: true,
  query: '?url',
  import: 'default',
})

// ─── Widget registry ─────────────────────────────────────────────────────────

const WIDGET_DEFS = [
  {
    type: 'exposure_summary', icon: 'EXP', title: 'Exposição (DEX/GEX/VEX/CEX)',
    desc: 'Resumo dos quatro indicadores de exposição do dealer',
    defaultW: 420, defaultH: 280,
  },
  {
    type: 'gex_by_strike', icon: 'GEX', title: 'GEX por Strike',
    desc: 'Barras de gamma exposure por nível de strike',
    defaultW: 520, defaultH: 270,
  },
  {
    type: 'pressure_curve', icon: 'PRC', title: 'Curva de Pressão',
    desc: 'Net pressure, call e put pressure ao longo dos strikes',
    defaultW: 520, defaultH: 260,
  },
  {
    type: 'volume_activity', icon: 'VOL', title: 'Atividade de Volume',
    desc: 'Feed ao vivo de mudanças de volume em opções',
    defaultW: 440, defaultH: 320,
  },
  {
    type: 'market_context', icon: 'MKT', title: 'Contexto de Mercado',
    desc: 'Spot, forward, taxa, dividendos, basis, IV rank',
    defaultW: 320, defaultH: 340,
  },
  {
    type: 'iv_smile', icon: 'IVS', title: 'IV Smile',
    desc: 'Curva de volatilidade implícita por strike',
    defaultW: 520, defaultH: 260,
  },
  {
    type: 'oi_distribution', icon: 'OID', title: 'Distribuição de OI',
    desc: 'Open interest de calls e puts por strike',
    defaultW: 520, defaultH: 270,
  },
  {
    type: 'dealer_bias', icon: 'DLB', title: 'Bias do Dealer',
    desc: 'Inferência da posição do dealer (long/short gamma)',
    defaultW: 400, defaultH: 360,
  },
  {
    type: 'movements', icon: 'MOV', title: 'Movimentações de Opções',
    desc: 'Tabela completa de todas as movimentações capturadas (put/call, strike, volume, bid/ask)',
    defaultW: 700, defaultH: 400,
  },
  {
    type: 'vol_surface', icon: 'V3D', title: 'Superfície de Vol 3D',
    desc: 'Superfície de volatilidade implícita 3D interativa — arraste para rotacionar',
    defaultW: 580, defaultH: 400,
  },
  {
    type: 'vol_surface_distortion_radar', icon: 'VDR', title: 'Vol Surface Distortion Radar',
    desc: 'Radar de distorcoes em ATM, asas, skew, convexidade, prazo e liquidez da superficie de IV',
    defaultW: 860, defaultH: 620,
  },
  {
    type: 'intraday_gamma', icon: 'XBG', title: 'Candles XB1 + Gamma',
    desc: 'Gráfico intraday de candles 5min do XB1 com níveis de gamma, zero GEX, pinning band e Fair Value inferido',
    defaultW: 720, defaultH: 480,
  },
  {
    type: 'option_flow', icon: 'OFL', title: 'Fluxo de Opções',
    desc: 'Evolução temporal do volume de puts e calls com filtro por moneyness (ATM/Near/Mid/≤30d)',
    defaultW: 660, defaultH: 370,
  },
  {
    type: 'pcr', icon: 'PCR', title: 'PCR — Put/Call Ratio',
    desc: 'Tabela PCR por moneyness (ATM/Near/Mid) × vencimento (1/5/15/30/60du) + evolução temporal das séries selecionadas',
    defaultW: 680, defaultH: 440,
  },
  {
    type: 'headlines', icon: 'HDL', title: 'Headlines',
    desc: 'Feed de headlines macro capturadas no dia via WebSocket, com filtro por relevância, escopo e busca livre',
    defaultW: 560, defaultH: 480,
  },
  {
    type: 'curve_discovery', icon: 'CUR', title: 'Curvas Macro',
    desc: 'OIS, Treasury, DI e inflacao implicita BR: variacao por vertice, slope geometrico 1m, shapes e opiniao IA',
    defaultW: 860, defaultH: 650,
  },
  {
    type: 'fair_value_legs', icon: 'FVL', title: 'Fair Value por Pernas',
    desc: 'Candles 5min do XB1 com linhas de Core, Shadow, pernas configuraveis, range e sentimento do fair value',
    defaultW: 900, defaultH: 640,
  },
  {
    type: 'fair_value_markov_regime', icon: 'FVM', title: 'Regime Markov FV',
    desc: 'Modelo Markov robusto sobre XB1, pernas do fair value, RPC, outliers e dislocation',
    defaultW: 960, defaultH: 680,
  },
  {
    type: 'atemporal_price_chart', icon: '10P', title: 'Grafico Atemporal',
    desc: 'Candles 10p do XB1 por deslocamento de preco, com MA271 e bandas de volatilidade implicita',
    defaultW: 900, defaultH: 620,
  },
  {
    type: 'flow_activity_radar', icon: 'FAR', title: 'Flow Activity Radar',
    desc: 'Radar de montagens por participante, com deteccao de robos, pace, projecao ate o fim do pregao e reader de fluxo',
    defaultW: 980, defaultH: 700,
  },
  {
    type: 'report_source_discovery', icon: 'RSD', title: 'Fontes LEV/HSBC',
    desc: 'Monitor diario das fontes publicas e proxies do relatorio, com historico minimo de 30 dias',
    defaultW: 940, defaultH: 620,
  },
  {
    type: 'funds_flow_local', icon: 'FFL', title: 'Funds Flow Local',
    desc: 'Fluxo de fundos locais via CVM, rankings, stress, heatmap e comparacao global preparada',
    defaultW: 980, defaultH: 680,
  },
  {
    type: 'vol_index', icon: 'VIX', title: 'Volatility Index',
    desc: 'Histórico de IV (ATM, 25Δ, 10Δ, interpolada), RV GARCH(1,1)-GED e Volatility Risk Premium',
    defaultW: 720, defaultH: 560,
  },
  {
    type: 'vol_of_vol', icon: 'VOV', title: 'Vol of Vol',
    desc: 'Estabilidade da superfície de IV, score de instabilidade e leitura de stress nas asas',
    defaultW: 700, defaultH: 380,
  },
  {
    type: 'dealer_pain_map', icon: 'DPM', title: 'Dealer Pain Map',
    desc: 'Mapa de regioes onde o dealer pode acelerar hedge, perder convexidade e sofrer stress de liquidez',
    defaultW: 760, defaultH: 560,
  },
  {
    type: 'pinning_expansion_battle', icon: 'PVE', title: 'Pinning vs Expansion',
    desc: 'Disputa entre compressao de gamma/OI e forcas de rompimento, continuidade e stress de superficie',
    defaultW: 760, defaultH: 540,
  },
  {
    type: 'dex_neutral', icon: 'DXN', title: 'DEX Neutral',
    desc: 'Curva de Delta Exposure (DEX) por nível de spot — ponto neutro, regime de dealer e breakdown por strike',
    defaultW: 660, defaultH: 480,
  },
  {
    type: 'hedge_pressure', icon: 'HPS', title: 'Hedge Pressure HP(S)',
    desc: 'Curva de pressão de hedge (HP) por nível de spot — zero HP, centro de massa, bandas de pinning, aceleração e descompressão',
    defaultW: 680, defaultH: 440,
  },
  {
    type: 'mm_hedge', icon: 'MMH', title: 'MM Hedge Pressure',
    desc: 'Estimativa intradiária dos contratos futuros que o market maker precisa comprar/vender — histograma de movimentações + acumulado da sessão',
    defaultW: 700, defaultH: 500,
  },
  {
    type: 'option_regime_classifier', icon: 'ORC', title: 'Option Regime Classifier',
    desc: 'Classificador hibrido do regime dominante de opcoes, com confianca, transicao e proximo estado provavel',
    defaultW: 780, defaultH: 620,
  },
  {
    type: 'volatility_ignition_detector', icon: 'IGN', title: 'Volatility Ignition Detector',
    desc: 'Detector de ignicao de volatilidade, com score, direcao, checklist e confirmacoes estruturais',
    defaultW: 760, defaultH: 560,
  },
]

const WIDGET_METADATA = {
  exposure_summary: {
    details: 'Consolida DEX, GEX, VEX e CEX para dar leitura rapida da exposicao do dealer, do regime de convexidade e do risco de aceleracao do hedge.',
    keywords: ['exposicao', 'exposure', 'dex', 'gex', 'vex', 'cex', 'dealer', 'resumo', 'greeks'],
  },
  gex_by_strike: {
    details: 'Mostra onde a gamma esta concentrada por strike, ajudando a localizar zonas de pinning, magnetismo, repulsao e possiveis aceleradores de movimento.',
    keywords: ['gex', 'gamma', 'strike', 'pinning', 'magnet', 'dealer', 'barra'],
  },
  pressure_curve: {
    details: 'Compara pressao liquida, calls e puts ao longo dos strikes para entender onde o fluxo tende a comprimir ou liberar movimento no indice.',
    keywords: ['pressao', 'pressure', 'curva', 'call pressure', 'put pressure', 'strikes'],
  },
  volume_activity: {
    details: 'Acompanha mudancas de volume em opcoes quase em tempo real, destacando onde o mercado esta adicionando atividade nova durante a sessao.',
    keywords: ['volume', 'atividade', 'opcoes', 'live', 'tempo real', 'mudancas'],
  },
  market_context: {
    details: 'Resume os parametros de mercado usados pelo modelo, como spot, forward, taxa, dividendos, basis e IV rank, para checar o pano de fundo.',
    keywords: ['market', 'contexto', 'spot', 'forward', 'taxa', 'dividendos', 'basis', 'iv rank'],
  },
  iv_smile: {
    details: 'Plota o smile de volatilidade implicita por strike para identificar assimetria, asas caras/baratas e regioes com distorcao de precificacao.',
    keywords: ['iv', 'smile', 'volatilidade', 'skew', 'asas', 'strike'],
  },
  oi_distribution: {
    details: 'Mostra o open interest de calls e puts por strike, util para encontrar concentracoes estruturais, strikes magneticos e barreiras de posicao.',
    keywords: ['oi', 'open interest', 'distribuicao', 'calls', 'puts', 'strike'],
  },
  dealer_bias: {
    details: 'Infere se o dealer esta mais long ou short gamma e traduz essa posicao em bias operacional de compressao, amplificacao ou transicao.',
    keywords: ['dealer', 'bias', 'long gamma', 'short gamma', 'regime', 'posicao'],
  },
  movements: {
    details: 'Tabela detalhada das movimentacoes capturadas em opcoes, com tipo, strike, volume, bid/ask e filtros para auditoria fina do fluxo.',
    keywords: ['movimentacoes', 'movements', 'opcoes', 'tabela', 'bid', 'ask', 'volume'],
  },
  vol_surface: {
    details: 'Visualiza a superficie de volatilidade implicita em 3D por strike/moneyness e vencimento para enxergar curvatura e termo em conjunto.',
    keywords: ['v3d', 'superficie', 'vol surface', 'volatilidade', '3d', 'moneyness', 'vencimento'],
  },
  vol_surface_distortion_radar: {
    details: 'Radar proprietario de distorcoes da superficie, separando ATM, put wing, call wing, skew, convexidade, termo e stress de liquidez.',
    keywords: ['vdr', 'vol surface distortion', 'radar', 'atm', 'put wing', 'call wing', 'skew', 'convexidade', 'termo'],
  },
  intraday_gamma: {
    details: 'Combina candles de 5 minutos do XB1 com gamma, zero GEX, bandas de pinning e fair value inferido para leitura intraday do indice.',
    keywords: ['xbg', 'xb1', 'candles', 'gamma', 'zero gex', 'pinning', 'fair value'],
  },
  option_flow: {
    details: 'Mostra a evolucao temporal do fluxo de puts e calls com recortes por moneyness e prazo, ajudando a separar hedge, especulacao e protecao.',
    keywords: ['ofl', 'option flow', 'fluxo', 'puts', 'calls', 'moneyness', 'prazo'],
  },
  pcr: {
    details: 'Calcula Put/Call Ratio por moneyness e vencimento, com historico das series selecionadas para detectar mudanca de demanda relativa.',
    keywords: ['pcr', 'put call ratio', 'puts', 'calls', 'sentimento', 'moneyness'],
  },
  headlines: {
    details: 'Feed de noticias macro do dia com busca livre e filtros de relevancia, pensado para conectar evento, horario e reacao dos widgets.',
    keywords: ['headlines', 'noticias', 'macro', 'feed', 'relevancia', 'evento'],
  },
  curve_discovery: {
    details: 'Analisa curvas OIS, Treasury, DI e inflacao implicita, exibindo variacao por vertice, slope geometrico, shapes e leitura de IA.',
    keywords: ['cur', 'curvas', 'ois', 'treasury', 'di', 'inflacao', 'slope', 'shape', 'ia'],
  },
  fair_value_legs: {
    details: 'Projeta o XB1 por pernas macro e equity, com core, shadow, bandas e sentimento para avaliar distorcao entre preco real e fair value.',
    keywords: ['fvl', 'fair value', 'pernas', 'core', 'shadow', 'xb1', 'macro', 'equity', 'bandas'],
  },
  fair_value_markov_regime: {
    details: 'Classifica regimes Markov robustos do XB1 contra as pernas do fair value, separando risk-on, risk-off, stress e dislocation.',
    keywords: ['fvm', 'markov', 'regime', 'fair value', 'outlier', 'dislocation', 'rpc', 'student t'],
  },
  atemporal_price_chart: {
    details: 'Monta candles atemporais do XB1 por deslocamento de 10 ticks, preservando candle parcial e plotando MA271 com banda de volatilidade implicita.',
    keywords: ['10p', 'atemporal', 'range bar', 'xb1', 'vol implicita', 'ma271', 'candles', 'pontos'],
  },
  flow_activity_radar: {
    details: 'Cataloga montagens relevantes por participante no futuro, separa runs ativos e historicos, mede contratos por minuto e projeta quanto ainda falta ate o fechamento.',
    keywords: ['far', 'flow activity', 'radar', 'robo', 'cta', 'montagem', 'participante', 'goldman', 'morgan', 'agressao', 'vwap'],
  },
  report_source_discovery: {
    details: 'Monitora fontes publicas e proxies usados em relatorios, com historico minimo para checar disponibilidade, mudanca e confianca dos dados.',
    keywords: ['rsd', 'fontes', 'relatorio', 'lev', 'hsbc', 'proxies', 'historico'],
  },
  funds_flow_local: {
    details: 'Painel de fluxo de fundos locais via CVM, com rankings, stress, heatmap e comparacoes globais preparadas para leitura de alocacao.',
    keywords: ['ffl', 'funds flow', 'fundos', 'cvm', 'fluxo local', 'ranking', 'heatmap'],
  },
  vol_index: {
    details: 'Construi indices de volatilidade com IV ATM, 25 delta, 10 delta, RV GARCH e VRP para comparar volatilidade implicita e realizada.',
    keywords: ['vix', 'vol index', 'iv', 'rv', 'garch', 'vrp', 'volatilidade'],
  },
  vol_of_vol: {
    details: 'Mede a instabilidade da propria volatilidade, detectando quando a superficie fica nervosa mesmo antes do spot refletir totalmente.',
    keywords: ['vov', 'vol of vol', 'instabilidade', 'superficie', 'stress', 'asas'],
  },
  dealer_pain_map: {
    details: 'Mapeia regioes de dor do dealer onde hedge, convexidade e liquidez podem forcar aceleracao, defesa ou transicao de regime.',
    keywords: ['dpm', 'dealer pain', 'dor', 'hedge', 'convexidade', 'liquidez'],
  },
  pinning_expansion_battle: {
    details: 'Compara forcas de pinning contra forcas de expansao para entender se o mercado tende a ficar preso ou romper com continuidade.',
    keywords: ['pve', 'pinning', 'expansion', 'rompimento', 'compressao', 'continuidade'],
  },
  dex_neutral: {
    details: 'Calcula a curva de Delta Exposure por nivel de spot e destaca o ponto neutro onde o regime de hedge direcional pode mudar.',
    keywords: ['dxn', 'dex neutral', 'delta exposure', 'ponto neutro', 'spot', 'dealer'],
  },
  hedge_pressure: {
    details: 'Plota a pressao de hedge HP(S), zero HP, centro de massa e bandas, mostrando onde o ajuste de futuros pode intensificar o movimento.',
    keywords: ['hps', 'hedge pressure', 'hp', 'zero hp', 'pinning', 'descompressao'],
  },
  mm_hedge: {
    details: 'Estima contratos futuros que o market maker precisaria comprar ou vender, com histograma de mudancas e acumulado intradiario.',
    keywords: ['mmh', 'market maker', 'hedge', 'futuros', 'contratos', 'acumulado'],
  },
  option_regime_classifier: {
    details: 'Classifica o regime dominante de opcoes, a confianca e a transicao provavel, juntando gamma, fluxo, superficie e confirmacoes.',
    keywords: ['orc', 'regime', 'classifier', 'opcoes', 'transicao', 'confianca'],
  },
  volatility_ignition_detector: {
    details: 'Detecta ignicao de volatilidade com score, direcao, checklist e confirmacoes estruturais para alertar mudanca brusca de tom.',
    keywords: ['ign', 'ignition', 'volatility ignition', 'volatilidade', 'detector', 'alerta'],
  },
}

WIDGET_DEFS.forEach(def => Object.assign(def, WIDGET_METADATA[def.type] ?? { details: def.desc, keywords: [] }))

const WIDGET_DEF_MAP = Object.fromEntries(WIDGET_DEFS.map(def => [def.type, def]))

const lazyWidget = loader => defineAsyncComponent({ loader, delay: 100, timeout: 30_000 })

const COMPONENT_MAP = {
  exposure_summary: lazyWidget(() => import('@/components/discovery/widgets/ExposureSummaryWidget.vue')),
  gex_by_strike: lazyWidget(() => import('@/components/discovery/widgets/GexByStrikeWidget.vue')),
  pressure_curve: lazyWidget(() => import('@/components/discovery/widgets/PressureCurveWidget.vue')),
  volume_activity: lazyWidget(() => import('@/components/discovery/widgets/VolumeActivityWidget.vue')),
  market_context: lazyWidget(() => import('@/components/discovery/widgets/MarketContextWidget.vue')),
  iv_smile: lazyWidget(() => import('@/components/discovery/widgets/IvSmileWidget.vue')),
  oi_distribution: lazyWidget(() => import('@/components/discovery/widgets/OiDistributionWidget.vue')),
  dealer_bias: lazyWidget(() => import('@/components/discovery/widgets/DealerBiasWidget.vue')),
  movements: lazyWidget(() => import('@/components/discovery/widgets/MovementsWidget.vue')),
  vol_surface: lazyWidget(() => import('@/components/discovery/widgets/VolSurface3DWidget.vue')),
  vol_surface_distortion_radar: lazyWidget(() => import('@/components/discovery/widgets/VolSurfaceDistortionRadarWidget.vue')),
  vol_index: lazyWidget(() => import('@/components/discovery/widgets/VolIndexWidget.vue')),
  vol_of_vol: lazyWidget(() => import('@/components/discovery/widgets/VolOfVolWidget.vue')),
  volatility_ignition_detector: lazyWidget(() => import('@/components/discovery/widgets/VolatilityIgnitionDetectorWidget.vue')),
  dealer_pain_map: lazyWidget(() => import('@/components/discovery/widgets/DealerPainMapWidget.vue')),
  pinning_expansion_battle: lazyWidget(() => import('@/components/discovery/widgets/PinningExpansionBattleWidget.vue')),
  option_regime_classifier: lazyWidget(() => import('@/components/discovery/widgets/OptionRegimeClassifierWidget.vue')),
  intraday_gamma: lazyWidget(() => import('@/components/discovery/widgets/IntradayGammaWidget.vue')),
  option_flow: lazyWidget(() => import('@/components/discovery/widgets/OptionFlowWidget.vue')),
  pcr: lazyWidget(() => import('@/components/discovery/widgets/PcrWidget.vue')),
  headlines: lazyWidget(() => import('@/components/discovery/widgets/HeadlinesWidget.vue')),
  curve_discovery: lazyWidget(() => import('@/components/discovery/widgets/CurveDiscoveryWidget.vue')),
  fair_value_legs: lazyWidget(() => import('@/components/discovery/widgets/FairValueLegsWidget.vue')),
  fair_value_markov_regime: lazyWidget(() => import('@/components/discovery/widgets/FairValueMarkovRegimeWidget.vue')),
  atemporal_price_chart: lazyWidget(() => import('@/components/discovery/widgets/AtemporalPriceChartWidget.vue')),
  flow_activity_radar: lazyWidget(() => import('@/components/discovery/widgets/FlowActivityRadarWidget.vue')),
  report_source_discovery: lazyWidget(() => import('@/components/discovery/widgets/ReportSourceDiscoveryWidget.vue')),
  funds_flow_local: lazyWidget(() => import('@/features/funds-flow/components/FundsFlowLocalWidget.vue')),
  dex_neutral: lazyWidget(() => import('@/components/discovery/widgets/DexNeutralWidget.vue')),
  hedge_pressure: lazyWidget(() => import('@/components/discovery/widgets/HedgePressureWidget.vue')),
  mm_hedge: lazyWidget(() => import('@/components/discovery/widgets/MarketMakerHedgeWidget.vue')),
}

function widgetComponent(type) { return COMPONENT_MAP[type] ?? null }

function normalizeWidgetConfig(widget) {
  const def = WIDGET_DEF_MAP[widget?.type]
  if (!def) return { ...widget }
  return {
    ...widget,
    icon: def.icon,
    title: def.title,
  }
}

function normalizeSearchValue(value) {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
}

function widgetSearchBlob(def) {
  return [
    def.type,
    def.icon,
    def.title,
    def.desc,
    def.details,
    ...(def.keywords ?? []),
  ].join(' ')
}

function scoreWidgetDef(def, query) {
  const q = normalizeSearchValue(query).trim()
  if (!q) return 1

  const tokens = q.split(/\s+/).filter(Boolean)
  const blob = normalizeSearchValue(widgetSearchBlob(def))
  if (!tokens.every(token => blob.includes(token))) return 0

  const icon = normalizeSearchValue(def.icon)
  const type = normalizeSearchValue(def.type)
  const title = normalizeSearchValue(def.title)
  const keywords = (def.keywords ?? []).map(normalizeSearchValue)
  let score = 10

  if (icon === q) score += 120
  else if (icon.startsWith(q)) score += 85
  if (type === q) score += 100
  else if (type.includes(q)) score += 45
  if (title === q) score += 100
  else if (title.startsWith(q)) score += 70
  else if (title.includes(q)) score += 35
  if (keywords.some(keyword => keyword === q)) score += 75
  if (keywords.some(keyword => keyword.startsWith(q))) score += 45

  score += tokens.reduce((sum, token) => sum + (title.includes(token) ? 12 : 4), 0)
  return score
}

function searchWidgetDefs(query, limit = WIDGET_DEFS.length) {
  const q = normalizeSearchValue(query).trim()
  if (!q) return WIDGET_DEFS.slice(0, limit)
  return WIDGET_DEFS
    .map((def, index) => ({ def, index, score: scoreWidgetDef(def, q) }))
    .filter(item => item.score > 0)
    .sort((a, b) => b.score - a.score || a.index - b.index)
    .slice(0, limit)
    .map(item => item.def)
}

function formatKeywords(def) {
  return (def.keywords ?? []).slice(0, 6).join(' · ')
}

function widgetPreviewUrl(def) {
  return WIDGET_PREVIEWS[`../assets/discovery/widget-previews/${def.type}.png`] ?? ''
}

// ─── Data normalisation ───────────────────────────────────────────────────────
// The API returns data keyed on the raw OpLab / model field names.
// Widgets expect a canonical shape; we map it once here so widgets stay simple.

const normalizedModelData = computed(() => {
  const raw      = modelData.value
  if (!raw) return null

  const ctx      = raw.market_context     ?? {}
  const pressure = raw.pressure           ?? {}
  const cp       = pressure.current_point ?? {}
  const profiles = raw.strike_profiles    ?? []

  // ── Fontes externas ───────────────────────────────────────────────────────
  // B3 OI: { by_strike: [{strike, call_oi, put_oi, total_oi, ...}] }
  const b3ByStrike = (b3OiData.value?.by_strike ?? [])
  const b3Map      = {}
  b3ByStrike.forEach(r => { b3Map[r.strike] = r })

  // Snapshot IV: { by_strike: [{strike, iv_call, iv_put, ...}] }
  const snapByStrike = (snapshotStrike.value?.by_strike ?? [])
  const snapMap      = {}
  snapByStrike.forEach(r => { snapMap[r.strike] = r })

  // Multiplier do modelo
  const multiplier = raw.config?.option_multiplier ?? 1.0

  // Rate curve — dict {"21": 0.135, ...} → precisamos antes do Camada 3
  const rateDict = ctx.rate_curve_points ?? {}
  const rateKeys = Object.keys(rateDict).map(Number).sort((a, b) => a - b)
  const riskFree = rateKeys.length ? rateDict[String(rateKeys[0])] : null

  // ── aggregates.by_strike ──────────────────────────────────────────────────
  // Estratégia em duas camadas:
  //   1. Snapshot (tier=all) como base → gamma para TODOS os strikes disponíveis.
  //      Só inclui strikes onde B3 tem OI (senão GEX = 0 e não é útil).
  //   2. strike_profiles do modelo sobrescreve → grega completa (+ VEX/CEX) para
  //      os ~8 strikes ATM onde o modelo roda.
  //
  // Resultado: GEX para todos os strikes com gamma+OI disponíveis.

  const byStrikeMap = new Map()

  // Camada 1: snapshot (todos os tiers mesclados)
  snapByStrike.forEach(snap => {
    const strike = parseFloat(snap.strike)
    if (!strike) return
    const b3     = b3Map[strike] ?? {}
    const callOi = b3.call_oi ?? 0
    const putOi  = b3.put_oi  ?? 0
    // Só inclui se tiver OI real da B3 E gamma do snapshot
    const gCall  = parseFloat(snap.gamma_call ?? 0) || 0
    const gPut   = parseFloat(snap.gamma_put  ?? 0) || 0
    if ((callOi === 0 && putOi === 0) || (gCall === 0 && gPut === 0)) return

    const dCall  = parseFloat(snap.delta_call ?? 0) || 0
    const dPut   = parseFloat(snap.delta_put  ?? 0) || 0

    const gexCall = gCall * callOi * multiplier
    const gexPut  = gPut  * putOi  * multiplier
    const gexNet  = gexCall - gexPut
    const dexNet  = (dCall * callOi + dPut * putOi) * multiplier

    byStrikeMap.set(strike, {
      key:      String(strike),
      strike,
      gex:      gexNet,  dex: dexNet,  vex: 0,  cex: 0,
      gex_call: gexCall, gex_put: gexPut,
      dex_call: dCall * callOi * multiplier,
      dex_put:  dPut  * putOi  * multiplier,
      call_oi:  callOi, put_oi: putOi,
      iv_call:  snap.iv_call ?? null,
      iv_put:   snap.iv_put  ?? null,
      iv_mid:   snap.iv_call != null && snap.iv_put != null
                ? (snap.iv_call + snap.iv_put) / 2
                : (snap.iv_call ?? snap.iv_put ?? null),
    })
  })

  // Camada 2: strike_profiles do modelo (sobrescreve ATM strikes com grega completa)
  profiles.forEach(sp => {
    const strike = sp.strike
    const b3     = b3Map[strike] ?? {}
    const snap   = snapMap[strike] ?? {}
    const callOi = b3.call_oi ?? sp.open_interest_call ?? 0
    const putOi  = b3.put_oi  ?? sp.open_interest_put  ?? 0

    const gCall  = sp.gamma_call ?? 0
    const gPut   = sp.gamma_put  ?? 0
    const dCall  = sp.delta_call ?? 0
    const dPut   = sp.delta_put  ?? 0
    const vCall  = sp.vanna_call ?? 0
    const vPut   = sp.vanna_put  ?? 0

    const gexCall = gCall * callOi * multiplier
    const gexPut  = gPut  * putOi  * multiplier
    const gexNet  = gexCall - gexPut
    const dexCall = dCall  * callOi * multiplier
    const dexPut  = dPut   * putOi  * multiplier
    const dexNet  = dexCall + dexPut
    const vexNet  = (vCall * callOi - vPut * putOi) * multiplier
    const cexNet  = (sp.cex_net ?? 0) !== 0
      ? sp.cex_net
      : ((sp.charm_call ?? 0) * callOi - (sp.charm_put ?? 0) * putOi) * multiplier

    byStrikeMap.set(strike, {
      key:      String(strike),
      strike,
      gex:      gexNet,  dex: dexNet,  vex: vexNet, cex: cexNet,
      gex_call: gexCall, gex_put: gexPut,
      dex_call: dexCall, dex_put: dexPut,
      call_oi:  callOi,  put_oi: putOi,
      iv_call:  snap.iv_call ?? null,
      iv_put:   snap.iv_put  ?? null,
      iv_mid:   snap.iv_call != null && snap.iv_put != null
                ? (snap.iv_call + snap.iv_put) / 2
                : (snap.iv_call ?? snap.iv_put ?? null),
    })
  })

  // ── Camada 3: BS gamma para strikes B3 sem cobertura de snapshot ────────────
  // Garante que TODOS os strikes B3 com OI apareçam no GEX.
  // Gregas menos precisas que o modelo, mas melhores que zero.
  const _S   = ctx.spot_price
  const _T   = Math.max(((ctx.days_to_expiry ?? 21) / 252), 1 / 252)
  const _r   = riskFree ?? 0.115
  const _iv0 = ctx.implied_vol ?? 0.25

  // IV smile para interpolação (snapshot strikes com iv_mid)
  const _ivRows = snapByStrike
    .filter(r => (r.iv_mid ?? r.iv_call ?? r.iv_put) != null)
    .map(r => ({ strike: r.strike, iv: r.iv_mid ?? r.iv_call ?? r.iv_put }))
    .sort((a, b) => a.strike - b.strike)

  function _interpIV(k) {
    if (!_ivRows.length) return _iv0
    if (_ivRows.length === 1) return _ivRows[0].iv
    const lo = [..._ivRows].reverse().find(r => r.strike <= k)
    const hi = _ivRows.find(r => r.strike > k)
    if (!lo) return hi.iv
    if (!hi) return lo.iv
    const t = (k - lo.strike) / (hi.strike - lo.strike)
    return lo.iv + t * (hi.iv - lo.iv)
  }

  function _npdf(x) { return Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI) }
  function _bsGamma(S, K, sigma, T, r) {
    if (S <= 0 || K <= 0 || sigma <= 0 || T <= 0) return 0
    const d1 = (Math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * Math.sqrt(T))
    return _npdf(d1) / (S * sigma * Math.sqrt(T))
  }

  b3ByStrike.forEach(b3r => {
    if (byStrikeMap.has(b3r.strike)) return   // já coberto pelo snapshot/modelo
    const callOi = b3r.call_oi ?? 0
    const putOi  = b3r.put_oi  ?? 0
    if ((callOi === 0 && putOi === 0) || !_S || !_T) return

    const iv       = _interpIV(b3r.strike)
    const g        = _bsGamma(_S, b3r.strike, iv, _T, _r)
    const gexCall  = g * callOi * multiplier
    const gexPut   = g * putOi  * multiplier
    const gexNet   = gexCall - gexPut

    byStrikeMap.set(b3r.strike, {
      key:      String(b3r.strike),
      strike:   b3r.strike,
      gex:      gexNet,  dex: 0,  vex: 0,  cex: 0,
      gex_call: gexCall, gex_put: gexPut,
      dex_call: 0,       dex_put: 0,
      call_oi:  callOi,  put_oi: putOi,
      iv_call:  null,    iv_put: null, iv_mid: iv,
      _bs: true,   // marcador: gamma via Black-Scholes
    })
  })

  const byStrike = Array.from(byStrikeMap.values()).sort((a, b) => a.strike - b.strike)

  // ── b3_by_strike: todos os 107+ strikes da B3 (para OI Distribution) ─────
  // A OI Distribution usa dados B3 porque cobre toda a cadeia (não só ATM)
  const b3AllStrikes = b3ByStrike.map(r => ({
    key:             String(r.strike),
    strike:          r.strike,
    call_oi:         r.call_oi         ?? 0,
    put_oi:          r.put_oi          ?? 0,
    call_coberto:    r.call_coberto    ?? 0,
    call_trava:      r.call_trava      ?? 0,
    call_descoberto: r.call_descoberto ?? 0,
    put_coberto:     r.put_coberto     ?? 0,
    put_trava:       r.put_trava       ?? 0,
    put_descoberto:  r.put_descoberto  ?? 0,
    // GEX só onde temos gamma do modelo
    gex: (() => {
      const sp = profiles.find(p => p.strike === r.strike)
      if (!sp) return 0
      return ((sp.gamma_call ?? 0) * (r.call_oi ?? 0) -
              (sp.gamma_put  ?? 0) * (r.put_oi  ?? 0)) * multiplier
    })(),
  }))

  // ── aggregates.totals ─────────────────────────────────────────────────────
  const sumGex    = byStrike.reduce((s, r) => s + r.gex, 0)
  const sumDex    = byStrike.reduce((s, r) => s + r.dex, 0)
  const sumVex    = byStrike.reduce((s, r) => s + r.vex, 0)
  const sumCallOi = b3ByStrike.reduce((s, r) => s + (r.call_oi ?? 0), 0)
  const sumPutOi  = b3ByStrike.reduce((s, r) => s + (r.put_oi  ?? 0), 0)
  const totalContracts = profiles.reduce((s, sp) => s + (sp.contracts ?? 0), 0)

  const totals = {
    gex:          sumGex || (cp.gex ?? 0),
    dex:          sumDex || (cp.dex ?? 0),
    vex:          sumVex || (cp.vex ?? 0),
    cex:          cp.cex ?? 0,
    gex_notional: sumGex,
    dex_notional: sumDex,
    vex_notional: sumVex,
    cex_notional: 0,
    call_oi:      sumCallOi,
    put_oi:       sumPutOi,
    contracts:    totalContracts || (sumCallOi + sumPutOi),
  }

  // ── market_context ────────────────────────────────────────────────────────
  const normalizedCtx = {
    ...ctx,
    // Prefer live spot (polled every 5 min) over the model snapshot
    spot_price:     liveSpot.value ?? ctx.spot_price,
    forward_price:  ctx.forward_price,
    risk_free_rate: riskFree,
    dividend_yield: ctx.dividend_yield ?? ctx.dividend_proxy_level ?? null,
    basis:          ctx.basis         ?? ctx.future_basis_pct    ?? null,
    days_to_expiry: ctx.days_to_expiry ?? null,
    implied_vol:    ctx.implied_vol    ?? null,
    iv_rank:        ctx.iv_rank        ?? null,
    rate_curve:     rateKeys.map(k => ({ dte: k, rate: rateDict[String(k)] })),
  }

  // ── pressure.curve ────────────────────────────────────────────────────────
  const normalizedCurve = (pressure.curve ?? []).map(pt => ({
    key:          String(pt.spot),
    strike:       pt.spot,
    spot:         pt.spot,
    gex_score:    pt.gex ?? 0,
    net_pressure: pt.hp  ?? 0,
    call_pressure: pt.by_put_call?.Call?.gex ?? ((pt.gex ?? 0) > 0 ? pt.gex : 0),
    put_pressure:  pt.by_put_call?.Put?.gex  ?? ((pt.gex ?? 0) < 0 ? pt.gex : 0),
    dex: pt.dex ?? 0, gex: pt.gex ?? 0, vex: pt.vex ?? 0, cex: pt.cex ?? 0,
    by_put_call: pt.by_put_call ?? {},
    by_expiry: pt.by_expiry ?? {},
  }))

  // ── pressure ──────────────────────────────────────────────────────────────
  // Calcula call/put pressure a partir do byStrike real (B3 OI × gamma),
  // não do current_point do modelo (que tem OI = 0 para IBOV no OpLab).
  const sumGexCall  = byStrike.reduce((s, r) => s + (r.gex_call ?? 0), 0)
  const sumGexPut   = byStrike.reduce((s, r) => s + (r.gex_put  ?? 0), 0)
  const callPressure = sumGexCall || cp.by_put_call?.Call?.gex || Math.max(0, cp.gex ?? 0)
  const putPressure  = sumGexPut  || cp.by_put_call?.Put?.gex  || Math.abs(Math.min(0, cp.gex ?? 0))
  const normalizedPressure = {
    ...pressure,
    curve:         normalizedCurve,
    dominant_side: pressure.dominant_side ?? (sumCallOi > sumPutOi ? 'call' : 'put'),
    call_pressure: callPressure,
    put_pressure:  putPressure,
    net_pressure:  sumGex || cp.hp || cp.gex || 0,
    gex_score:     sumGex || cp.gex || 0,
  }

  // ── dealer_inference ──────────────────────────────────────────────────────
  const di    = raw.dealer_inference ?? {}
  const score = sumGex || cp.gex || 0

  // Gauge score in [-1, +1]: net GEX / total GEX across all strikes.
  // +1 = 100% call gamma (long gamma), -1 = 100% put gamma (short gamma).
  const totalGex   = byStrike.reduce((s, r) => s + (r.gex_call ?? 0) + (r.gex_put ?? 0), 0)
  const gaugeScore = totalGex > 0
    ? Math.max(-1, Math.min(1, score / totalGex))
    : 0

  const normalizedDealer = {
    ...di,
    dealer_bias: score >  0 ? 'long_gamma'  :
                 score <  0 ? 'short_gamma'  : 'neutral',
    score: gaugeScore,
  }

  return {
    ...raw,
    market_context:   normalizedCtx,
    pressure:         normalizedPressure,
    dealer_inference: normalizedDealer,
    aggregates:       { by_strike: byStrike, totals, b3_by_strike: b3AllStrikes },
    b3_oi_date:       b3OiData.value?.date ?? null,
    captured_at:      raw.captured_at,
  }
})

const optionsAlignedModelData = computed(() => {
  const raw = modelData.value
  if (!raw) return null

  const rawPressure = raw.pressure ?? {}
  const strikeProfiles = (raw.strike_profiles ?? [])
    .filter(row => Number(row?.open_interest_total || 0) > 0)
    .sort((a, b) => Number(a?.strike || 0) - Number(b?.strike || 0))

  const alignedByStrike = strikeProfiles.map(row => ({
    key:      String(row.strike),
    strike:   Number(row.strike || 0),
    gex:      Number(row.gex_net || 0),
    dex:      Number(row.dex_net || 0),
    vex:      Number(row.vex_net || 0),
    cex:      Number(row.cex_net || 0),
    gex_call: Number(row.gex_call || 0),
    gex_put:  Number(row.gex_put || 0),
    call_oi:  Number(row.open_interest_call || 0),
    put_oi:   Number(row.open_interest_put || 0),
    _bs:      false,
  }))

  const alignedTotals = {
    gex:       alignedByStrike.reduce((sum, row) => sum + Number(row.gex || 0), 0),
    dex:       alignedByStrike.reduce((sum, row) => sum + Number(row.dex || 0), 0),
    vex:       alignedByStrike.reduce((sum, row) => sum + Number(row.vex || 0), 0),
    cex:       alignedByStrike.reduce((sum, row) => sum + Number(row.cex || 0), 0),
    call_oi:   alignedByStrike.reduce((sum, row) => sum + Number(row.call_oi || 0), 0),
    put_oi:    alignedByStrike.reduce((sum, row) => sum + Number(row.put_oi || 0), 0),
    gex_call:  alignedByStrike.reduce((sum, row) => sum + Number(row.gex_call || 0), 0),
    gex_put:   alignedByStrike.reduce((sum, row) => sum + Number(row.gex_put || 0), 0),
    contracts: alignedByStrike.length,
  }

  const normalizedPressureCurve = (rawPressure.curve ?? []).map(point => {
    const callPressure = Number(point?.by_put_call?.Call?.gex || 0)
    const putPressure = Number(point?.by_put_call?.Put?.gex || 0)
    return {
      key:           String(point.spot),
      strike:        Number(point.spot || 0),
      spot:          Number(point.spot || 0),
      gex_score:     Number(point.gex || 0),
      net_pressure:  Number(point.hp || 0),
      call_pressure: callPressure,
      put_pressure:  putPressure,
      dex:           Number(point.dex || 0),
      gex:           Number(point.gex || 0),
      vex:           Number(point.vex || 0),
      cex:           Number(point.cex || 0),
      by_put_call:   point?.by_put_call ?? {},
      by_expiry:     point?.by_expiry ?? {},
    }
  })

  const currentCallPressure = Number(rawPressure.current_point?.by_put_call?.Call?.gex || 0)
  const currentPutPressure = Number(rawPressure.current_point?.by_put_call?.Put?.gex || 0)
  const currentNetPressure = Number(rawPressure.current_point?.hp || rawPressure.current_point?.gex || 0)

  return {
    ...raw,
    aggregates: {
      by_strike: alignedByStrike,
      totals: alignedTotals,
    },
    pressure: {
      ...rawPressure,
      curve: normalizedPressureCurve,
      dominant_side: rawPressure.dominant_side ?? (alignedTotals.gex_call >= alignedTotals.gex_put ? 'call' : 'put'),
      call_pressure: alignedTotals.gex_call || currentCallPressure,
      put_pressure: alignedTotals.gex_put || currentPutPressure,
      net_pressure: alignedTotals.gex || currentNetPressure,
      gex_score: alignedTotals.gex || Number(rawPressure.current_point?.gex || 0),
    },
    b3_oi_date: raw.diagnostics?.b3_oi_trade_date ?? b3OiData.value?.date ?? null,
    captured_at: raw.captured_at,
  }
})

function widgetProps(w) {
  if (w.type === 'volume_activity') {
    return {
      underlying:  activeUnderlying.value,
      autoRefresh: true,
      spotPrice:   spotPrice.value ?? null,
    }
  }
  if (w.type === 'movements') {
    return { underlying: activeUnderlying.value, autoRefresh: true }
  }
  if (w.type === 'vol_of_vol') {
    return {
      underlyingSecurity: activeUnderlying.value,
      refreshNonce: lastFetch.value ? lastFetch.value.getTime() : 0,
    }
  }
  if (w.type === 'curve_discovery') {
    return {
      refreshNonce: lastFetch.value ? lastFetch.value.getTime() : 0,
    }
  }
  if (w.type === 'fair_value_legs') {
    return {
      modelData: normalizedModelData.value,
      refreshNonce: lastFetch.value ? lastFetch.value.getTime() : 0,
    }
  }
  if (w.type === 'fair_value_markov_regime') {
    return {
      modelData: normalizedModelData.value,
      refreshNonce: lastFetch.value ? lastFetch.value.getTime() : 0,
    }
  }
  if (w.type === 'atemporal_price_chart') {
    return {
      modelData: normalizedModelData.value,
      underlyingSecurity: activeUnderlying.value,
      refreshNonce: lastFetch.value ? lastFetch.value.getTime() : 0,
    }
  }
  if (w.type === 'flow_activity_radar') {
    return {
      refreshNonce: lastFetch.value ? lastFetch.value.getTime() : 0,
    }
  }
  if (w.type === 'report_source_discovery') {
    return {
      refreshNonce: w.reloadNonce ?? 0,
    }
  }
  if (w.type === 'funds_flow_local') {
    return {
      refreshNonce: w.reloadNonce ?? 0,
    }
  }
  if (w.type === 'vol_surface_distortion_radar') {
    return {
      modelData: normalizedModelData.value,
      underlyingSecurity: activeUnderlying.value,
      refreshNonce: lastFetch.value ? lastFetch.value.getTime() : 0,
    }
  }
  if (w.type === 'volatility_ignition_detector') {
    return {
      modelData: normalizedModelData.value,
      underlyingSecurity: activeUnderlying.value,
      refreshNonce: lastFetch.value ? lastFetch.value.getTime() : 0,
    }
  }
  if (w.type === 'dealer_pain_map') {
    return {
      modelData: normalizedModelData.value,
      rawModelData: modelData.value,
      underlyingSecurity: activeUnderlying.value,
      refreshNonce: lastFetch.value ? lastFetch.value.getTime() : 0,
    }
  }
  if (w.type === 'pinning_expansion_battle') {
    return {
      modelData: normalizedModelData.value,
      underlyingSecurity: activeUnderlying.value,
      refreshNonce: lastFetch.value ? lastFetch.value.getTime() : 0,
    }
  }
  if (w.type === 'option_regime_classifier') {
    return {
      modelData: normalizedModelData.value,
      underlyingSecurity: activeUnderlying.value,
      refreshNonce: lastFetch.value ? lastFetch.value.getTime() : 0,
    }
  }
  if (w.type === 'gex_by_strike' || w.type === 'pressure_curve') {
    return { modelData: optionsAlignedModelData.value ?? normalizedModelData.value }
  }
  return { modelData: normalizedModelData.value }
}

// ─── Data ────────────────────────────────────────────────────────────────────

const underlyings = ref([
  { label: 'IBOV',  value: 'IBOVE Index' },
  { label: 'SPX',   value: 'SPX Index'   },
])
const activeUnderlying = ref('IBOVE Index')

const modelData      = ref(null)   // /model/latest (full 90DU)
const snapshotStrike = ref(null)   // /snapshot/by-strike (full 90DU)
const b3OiData       = ref(null)   // /b3-oi/latest        (OI real da B3)
const lastGoodModelData = ref(null)
const lastGoodSnapshotStrike = ref(null)
const lastGoodB3OiData = ref(null)
const fetchingModel  = ref(false)
const lastFetch      = ref(null)
const now            = ref(new Date())
let clockTimer       = null

const timeSinceFetch = computed(() => {
  if (!lastFetch.value) return ''
  const sec = Math.floor((now.value - lastFetch.value) / 1000)
  if (sec < 60) return `${sec}s atrás`
  return `${Math.floor(sec / 60)}m atrás`
})

// Live spot — updated every 5 minutes independently of the heavy model fetch
const liveSpot  = ref(null)
const spotPrice = computed(() => liveSpot.value ?? modelData.value?.market_context?.spot_price ?? null)

async function pollLiveSpot() {
  try {
    // Derive the OpLab underlying symbol from the active underlying security
    // 'IBOVE Index' → 'IBOV', 'BOVA11 Index' → 'BOVA11'
    const symbolMap = { 'IBOVE Index': 'IBOV', 'BOVA11 Index': 'BOVA11' }
    const underlying = symbolMap[activeUnderlying.value] ?? 'IBOV'
    const res = await getLiveSpot(underlying)
    const spot = res?.data?.spot
    if (spot && spot > 0) liveSpot.value = spot
  } catch {
    // silently ignore — spotPrice falls back to modelData
  }
}

// Tracker status
const trackerRunning   = ref(false)
const trackedSymbols   = ref(0)
const eventCount       = ref(0)

// Connection status
const connBackend = ref('unknown')
const connOplab   = ref('unknown')

async function refreshModel() {
  try {
    fetchingModel.value = true

    // Busca paralela das três fontes de dados
    const [modelRes, snapRes, b3Res] = await Promise.allSettled([
      getLatestOptionsModel({ underlying_security: activeUnderlying.value, universe_tier: 'full' }),
      getSnapshotByStrike({ underlying_security: activeUnderlying.value, tier: 'full' }),
      getB3OiLatest(),
    ])

    const nextModelData = modelRes.status === 'fulfilled' ? (modelRes.value?.data ?? null) : null
    const nextSnapshotStrike = snapRes.status === 'fulfilled' ? (snapRes.value?.data ?? null) : null
    const nextB3OiData = b3Res.status === 'fulfilled' ? (b3Res.value?.data ?? null) : null

    if (nextModelData) {
      modelData.value = nextModelData
      lastGoodModelData.value = nextModelData
    } else if (!modelData.value && lastGoodModelData.value) {
      modelData.value = lastGoodModelData.value
    }

    if (nextSnapshotStrike) {
      snapshotStrike.value = nextSnapshotStrike
      lastGoodSnapshotStrike.value = nextSnapshotStrike
    } else if (!snapshotStrike.value && lastGoodSnapshotStrike.value) {
      snapshotStrike.value = lastGoodSnapshotStrike.value
    }

    if (nextB3OiData) {
      b3OiData.value = nextB3OiData
      lastGoodB3OiData.value = nextB3OiData
    } else if (!b3OiData.value && lastGoodB3OiData.value) {
      b3OiData.value = lastGoodB3OiData.value
    }

    // Seed liveSpot from model if the 5-min poller hasn't fired yet
    if (liveSpot.value == null) {
      const modelSpot = modelData.value?.market_context?.spot_price
      if (modelSpot && modelSpot > 0) liveSpot.value = modelSpot
    }

    const fulfilledCount = [modelRes, snapRes, b3Res].filter(result => result.status === 'fulfilled').length
    connBackend.value = fulfilledCount > 0 ? 'ok' : 'error'
    connOplab.value = (modelData.value || snapshotStrike.value) ? 'ok' : 'error'
    if (fulfilledCount > 0) {
      lastFetch.value = new Date()
    }
  } catch {
    connBackend.value = 'error'
  } finally {
    fetchingModel.value = false
  }
}

async function refreshTracker() {
  try {
    const res = await getVolumeTrackerStatus()
    const d = (res?.data && (res.data.running !== undefined || res.data.tracked_symbols !== undefined))
      ? res.data
      : (res?.data?.data ?? res?.data ?? res ?? {})
    const running = d?.running
    trackerRunning.value = running === true || running === 'true'
    trackedSymbols.value = Number(d?.tracked_symbols ?? 0) || 0
    eventCount.value     = Number(d?.event_count ?? d?.events_today ?? 0) || 0
    if (!trackerRunning.value) {
      // Auto-start tracker if not running
      await startVolumeTracker().catch(() => {})
    }
  } catch {
    trackerRunning.value = false
  }
}

function refreshAll() {
  refreshModel()
  refreshTracker()
}

let modelTimer   = null
let trackerTimer = null
let spotTimer    = null

const captureWidgetType = typeof window !== 'undefined'
  ? new URLSearchParams(window.location.search).get('captureWidget')
  : null
const isCaptureMode = Boolean(captureWidgetType)

function applyCaptureWidgetLayout() {
  const def = WIDGET_DEF_MAP[captureWidgetType]
  if (!def) return
  widgets.value = [normalizeWidgetConfig({
    id: 'capture-widget',
    type: def.type,
    icon: def.icon,
    title: def.title,
    x: 16,
    y: 16,
    w: Math.min(def.defaultW ?? 720, 760),
    h: Math.min(def.defaultH ?? 480, 560),
    z: 1,
  })]
}

onMounted(() => {
  if (isCaptureMode) {
    applyCaptureWidgetLayout()
    refreshAll()
    pollLiveSpot()
    clockTimer = setInterval(() => { now.value = new Date() }, 5_000)
    return
  }

  refreshAll()
  pollLiveSpot()   // fetch spot immediately on mount
  modelTimer   = setInterval(refreshModel,   30_000)
  trackerTimer = setInterval(refreshTracker, 20_000)
  spotTimer    = setInterval(pollLiveSpot,  5 * 60_000)  // 5 min
  clockTimer   = setInterval(() => { now.value = new Date() }, 5_000)
  loadLayout()
  window.addEventListener('keydown', onGlobalDiscoveryKeydown)
})

onUnmounted(() => {
  clearInterval(modelTimer)
  clearInterval(trackerTimer)
  clearInterval(spotTimer)
  clearInterval(clockTimer)
  window.removeEventListener('keydown', onGlobalDiscoveryKeydown)
})

// ─── Widget management ────────────────────────────────────────────────────────

const widgets = ref([])
const showPicker = ref(false)
const pickerSearchInput = ref(null)
const pickerQuery = ref('')
const quickSearchInput = ref(null)
const quickSearchOpen = ref(false)
const quickSearchQuery = ref('')
const quickSearchIndex = ref(0)
const discoveryHovered = ref(false)
let nextId = 1
let zTop = 10

const pickerHasQuery = computed(() => pickerQuery.value.trim().length > 0)
const filteredWidgetDefs = computed(() => searchWidgetDefs(pickerQuery.value))
const quickSearchResults = computed(() => searchWidgetDefs(quickSearchQuery.value, 7))

function openPicker(initialQuery = '') {
  normalizeWidgetZStack()
  closeQuickSearch()
  pickerQuery.value = initialQuery
  showPicker.value = true
  nextTick(() => pickerSearchInput.value?.focus())
}

function closePicker() {
  showPicker.value = false
  pickerQuery.value = ''
}

function addPickerSelection() {
  const def = filteredWidgetDefs.value[0]
  if (def) addWidget(def)
}

function openQuickSearch(initialQuery = '') {
  if (showPicker.value) return
  normalizeWidgetZStack()
  quickSearchQuery.value = initialQuery
  quickSearchIndex.value = 0
  quickSearchOpen.value = true
  nextTick(() => {
    const input = quickSearchInput.value
    input?.focus()
    input?.setSelectionRange?.(quickSearchQuery.value.length, quickSearchQuery.value.length)
  })
}

function closeQuickSearch() {
  quickSearchOpen.value = false
  quickSearchQuery.value = ''
  quickSearchIndex.value = 0
}

function moveQuickSearch(direction) {
  const count = quickSearchResults.value.length
  if (!count) return
  quickSearchIndex.value = (quickSearchIndex.value + direction + count) % count
}

function addQuickSearchSelection() {
  const results = quickSearchResults.value
  if (!results.length) return
  const index = Math.min(Math.max(quickSearchIndex.value, 0), results.length - 1)
  addWidget(results[index])
}

function isEditableElement(el) {
  if (!el) return false
  const tag = el.tagName
  return tag === 'INPUT'
    || tag === 'TEXTAREA'
    || tag === 'SELECT'
    || el.isContentEditable
    || Boolean(el.closest?.('[contenteditable="true"]'))
}

function isSearchStartKey(event) {
  return event.key?.length === 1 && !/\s/.test(event.key)
}

function onGlobalDiscoveryKeydown(event) {
  if (!discoveryHovered.value) return
  if (showPicker.value || quickSearchOpen.value) return
  if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey || event.isComposing) return
  if (isEditableElement(document.activeElement)) return
  if (dragging.value || resizing.value) return
  if (!isSearchStartKey(event)) return

  event.preventDefault()
  openQuickSearch(event.key)
}

function addWidget(def, opts = {}) {
  const id = `w${nextId++}`
  // Cascade position to avoid complete overlap
  const offset = (widgets.value.length % 6) * 24
  widgets.value.push(normalizeWidgetConfig({
    id,
    type: def.type,
    icon: def.icon,
    title: def.title,
    x: opts.x ?? 60 + offset,
    y: opts.y ?? 60 + offset,
    w: opts.w ?? def.defaultW,
    h: opts.h ?? def.defaultH,
    z: ++zTop,
  }))
  closePicker()
  closeQuickSearch()
  saveLayout()
}

function closeWidget(id) {
  widgets.value = widgets.value.filter(w => w.id !== id)
  saveLayout()
}

function reloadWidget(w) {
  if (w.type === 'report_source_discovery' || w.type === 'funds_flow_local') {
    w.reloadNonce = Date.now()
    return
  }
  // volume_activity and movements manage their own auto-refresh; others use the model
  const selfRefreshing = ['volume_activity', 'movements']
  if (!selfRefreshing.includes(w.type)) refreshModel()
}

function clearAll() {
  if (!confirm('Limpar todos os widgets?')) return
  widgets.value = []
  saveLayout()
}

function bringToFront(id) {
  if (zTop >= 500) {
    normalizeWidgetZStack()
  }
  const w = widgets.value.find(w => w.id === id)
  if (w) { w.z = ++zTop }
}

function normalizeWidgetZStack() {
  zTop = normalizeDiscoveryZStack(widgets.value)
}

// ─── Drag engine ──────────────────────────────────────────────────────────────

const dragging = ref(null)  // { widget, startX, startY, origX, origY }

function startDrag(e, widget) {
  bringToFront(widget.id)
  dragging.value = {
    widget,
    startX: e.clientX,
    startY: e.clientY,
    origX:  widget.x,
    origY:  widget.y,
  }
}

// ─── Resize engine ────────────────────────────────────────────────────────────

const resizing = ref(null)  // { widget, startX, startY, origW, origH }

function startResize(e, widget) {
  bringToFront(widget.id)
  resizing.value = {
    widget,
    startX: e.clientX,
    startY: e.clientY,
    origW:  widget.w,
    origH:  widget.h,
  }
}

// ─── Mouse handlers (shared) ──────────────────────────────────────────────────

function onMouseMove(e) {
  discoveryHovered.value = true
  if (dragging.value) {
    const d = dragging.value
    const dx = e.clientX - d.startX
    const dy = e.clientY - d.startY
    d.widget.x = Math.max(0, d.origX + dx)
    d.widget.y = Math.max(0, d.origY + dy)
  }
  if (resizing.value) {
    const r = resizing.value
    const dx = e.clientX - r.startX
    const dy = e.clientY - r.startY
    r.widget.w = Math.max(220, r.origW + dx)
    r.widget.h = Math.max(140, r.origH + dy)
  }
}

function onMouseUp() {
  if (dragging.value || resizing.value) {
    dragging.value = null
    resizing.value = null
    saveLayout()
  }
}

// ─── Layout persistence ───────────────────────────────────────────────────────

function saveLayout() {
  try {
    localStorage.setItem(
      DISCOVERY_LAYOUT_STORAGE_KEY,
      serializeDiscoveryLayout(widgets.value, activeUnderlying.value),
    )
  } catch { /* storage full or unavailable */ }
}

function loadLayout() {
  let rawLayout = null
  try {
    rawLayout = localStorage.getItem(DISCOVERY_LAYOUT_STORAGE_KEY)
  } catch {
    return
  }
  const saved = parseDiscoveryLayout(
    rawLayout,
    normalizeWidgetConfig,
  )
  if (!saved) return
  if (saved.underlying) activeUnderlying.value = saved.underlying
  widgets.value = saved.widgets
  nextId = Math.max(getNextWidgetSequence(widgets.value), nextId)
  normalizeWidgetZStack()
}

// ─── Auto-arrange ─────────────────────────────────────────────────────────────

function arrangeGrid() {
  arrangeDiscoveryGrid(widgets.value)
  normalizeWidgetZStack()
  saveLayout()
}

// ─── Presets ──────────────────────────────────────────────────────────────────

function loadPreset(name) {
  widgets.value = []
  nextId = 1

  const presets = {
    overview: [
      { type: 'exposure_summary', x: 16,  y: 16, w: 400, h: 280 },
      { type: 'market_context',   x: 432, y: 16, w: 300, h: 340 },
      { type: 'gex_by_strike',    x: 16,  y: 312, w: 716, h: 270 },
      { type: 'vol_of_vol',       x: 748, y: 312, w: 620, h: 420 },
      { type: 'report_source_discovery', x: 16, y: 748, w: 940, h: 620 },
      { type: 'funds_flow_local', x: 972, y: 748, w: 980, h: 680 },
    ],
    greeks: [
      { type: 'gex_by_strike',  x: 16,  y: 16,  w: 500, h: 260 },
      { type: 'pressure_curve', x: 532, y: 16,  w: 500, h: 260 },
      { type: 'iv_smile',       x: 16,  y: 292, w: 500, h: 260 },
      { type: 'oi_distribution',x: 532, y: 292, w: 500, h: 260 },
    ],
    flow: [
      { type: 'movements',        x: 16,  y: 16, w: 720, h: 420 },
      { type: 'dealer_bias',      x: 752, y: 16, w: 380, h: 420 },
      { type: 'exposure_summary', x: 16,  y: 452, w: 500, h: 260 },
      { type: 'volume_activity',  x: 532, y: 452, w: 600, h: 260 },
    ],
  }

  const defs = presets[name] ?? []
  defs.forEach(opts => {
    const def = WIDGET_DEFS.find(d => d.type === opts.type)
    if (def) addWidget(def, opts)
  })
}
</script>

<style scoped>
/* ─── Root ─── */
.discovery-root {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #060b15;
  color: #e2e8f0;
  overflow: hidden;
  user-select: none;
}
.discovery-root.capture-mode {
  background:
    radial-gradient(circle at 22% 18%, rgba(247,185,85,0.10), transparent 32%),
    radial-gradient(circle at 80% 12%, rgba(59,130,246,0.11), transparent 34%),
    #060b15;
}
.capture-mode :deep(.widget-controls),
.capture-mode :deep(.resize-handle) {
  display: none;
}

/* ─── Toolbar ─── */
.discovery-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 14px;
  background: #080e1a;
  border-bottom: 1px solid rgba(59,130,246,0.12);
  flex-shrink: 0;
}
.toolbar-left  { display: flex; gap: 6px; }
.toolbar-center { flex: 1; display: flex; align-items: center; gap: 10px; justify-content: center; }
.toolbar-right { display: flex; gap: 6px; }

.tb-btn {
  padding: 4px 12px;
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 5px;
  background: rgba(255,255,255,0.03);
  color: #94a3b8;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  display: flex; align-items: center; gap: 5px;
}
.tb-btn:hover { background: rgba(255,255,255,0.07); color: #e2e8f0; border-color: rgba(255,255,255,0.18); }
.tb-btn.primary { background: rgba(99,102,241,0.12); border-color: rgba(99,102,241,0.35); color: #a5b4fc; }
.tb-btn.primary:hover { background: rgba(99,102,241,0.22); }
.tb-btn.loading { opacity: 0.6; cursor: wait; }

.tb-select {
  padding: 4px 10px;
  background: #0a1120;
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 5px;
  color: #e2e8f0;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer; outline: none;
}
.tb-select:focus { border-color: #6366f1; }
.tb-refresh-info { font-size: 10px; color: #334155; }

/* ─── Canvas ─── */
.discovery-canvas {
  flex: 1;
  position: relative;
  overflow: auto;
  min-height: 0;
}

/* ─── Empty state ─── */
.discovery-empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  pointer-events: none;
}
.empty-icon  { font-size: 48px; color: #1e293b; }
.empty-title { font-size: 20px; font-weight: 700; color: #1e293b; }
.empty-sub   { font-size: 13px; color: #1e2d40; }
.empty-sub b { color: #2d3f5a; }
.empty-presets {
  display: flex; gap: 8px; margin-top: 12px;
  pointer-events: all;
}
.preset-btn {
  padding: 6px 16px;
  border: 1px solid rgba(99,102,241,0.3);
  border-radius: 6px;
  background: rgba(99,102,241,0.08);
  color: #6366f1;
  font-size: 12px; font-weight: 600;
  cursor: pointer; transition: all 0.15s;
}
.preset-btn:hover { background: rgba(99,102,241,0.18); border-color: rgba(99,102,241,0.5); }

/* ─── Quick search ─── */
.quick-search-panel {
  position: fixed;
  inset: 0;
  z-index: 100000;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 86px;
  pointer-events: none;
}
.quick-search-box {
  width: min(680px, calc(100vw - 32px));
  padding: 14px;
  border: 1px solid rgba(247,185,85,0.28);
  border-radius: 18px;
  background:
    radial-gradient(circle at 12% 0%, rgba(247,185,85,0.13), transparent 38%),
    linear-gradient(145deg, rgba(12,20,34,0.98), rgba(5,10,18,0.98));
  box-shadow: 0 22px 70px rgba(0,0,0,0.65), 0 0 0 1px rgba(255,255,255,0.03) inset;
  pointer-events: all;
}
.quick-search-kicker {
  margin-bottom: 8px;
  color: #f7b955;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}
.quick-search-input {
  width: 100%;
  padding: 12px 14px;
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 12px;
  background: rgba(2,6,14,0.78);
  color: #f8fafc;
  font-size: 15px;
  font-weight: 700;
  outline: none;
  user-select: text;
}
.quick-search-input:focus {
  border-color: rgba(247,185,85,0.6);
  box-shadow: 0 0 0 3px rgba(247,185,85,0.12);
}
.quick-search-help {
  padding: 7px 2px 10px;
  color: #64748b;
  font-size: 10px;
}
.quick-search-results {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: min(420px, 58vh);
  overflow: auto;
}
.quick-result-card {
  position: relative;
  display: grid;
  grid-template-columns: 98px 1fr;
  gap: 12px;
  align-items: center;
  padding: 10px 12px;
  border: 1px solid rgba(255,255,255,0.07);
  border-radius: 13px;
  background: rgba(10,17,32,0.82);
  text-align: left;
  cursor: pointer;
  transition: all 0.12s ease;
  overflow: hidden;
}
.quick-result-card:hover,
.quick-result-card.active {
  border-color: rgba(247,185,85,0.5);
  background: rgba(247,185,85,0.08);
  transform: translateY(-1px);
}
.quick-result-preview,
.picker-preview {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  align-self: stretch;
  min-height: 76px;
  margin: -10px 0 -10px -12px;
  overflow: hidden;
  background:
    radial-gradient(circle at 25% 20%, rgba(247,185,85,0.18), transparent 35%),
    linear-gradient(145deg, rgba(15,23,42,0.96), rgba(2,6,14,0.96));
  color: #f7b955;
  font-family: "JetBrains Mono", "IBM Plex Mono", "SFMono-Regular", Consolas, monospace;
  font-size: 17px;
  font-weight: 900;
  letter-spacing: -0.08em;
}
.quick-result-preview img,
.picker-preview img {
  position: absolute;
  inset: 0;
  width: 145%;
  height: 100%;
  object-fit: cover;
  object-position: left center;
  filter: saturate(0.9) brightness(0.72) contrast(1.08);
  transform: scale(1.03);
}
.quick-result-preview::before,
.picker-preview::before {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 1;
  backdrop-filter: blur(2.5px);
  -webkit-backdrop-filter: blur(2.5px);
  background: linear-gradient(135deg, transparent 0%, rgba(8,14,25,0.18) 38%, rgba(8,14,25,0.72) 100%);
  -webkit-mask-image: linear-gradient(135deg, transparent 0%, rgba(0,0,0,0.35) 44%, #000 76%);
  mask-image: linear-gradient(135deg, transparent 0%, rgba(0,0,0,0.35) 44%, #000 76%);
}
.quick-result-preview::after,
.picker-preview::after {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 2;
  background: linear-gradient(105deg, transparent 0%, transparent 45%, rgba(10,17,32,0.90) 78%, rgba(10,17,32,0.98) 100%);
}
.quick-result-preview span,
.picker-preview span {
  position: relative;
  z-index: 3;
  text-shadow: 0 0 18px rgba(247,185,85,0.32);
}
.quick-result-icon {
  color: #f7b955;
  font-family: "JetBrains Mono", "IBM Plex Mono", "SFMono-Regular", Consolas, monospace;
  font-size: 11px;
  font-weight: 900;
  letter-spacing: -0.08em;
  transform: scaleX(0.88);
  transform-origin: left center;
}
.quick-result-copy {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}
.quick-result-title {
  display: flex;
  align-items: center;
  gap: 7px;
  color: #f8fafc;
  font-size: 12px;
  font-weight: 800;
}
.quick-result-desc { color: #94a3b8; font-size: 10px; line-height: 1.35; }
.quick-search-empty {
  padding: 18px;
  border: 1px dashed rgba(255,255,255,0.12);
  border-radius: 12px;
  color: #64748b;
  font-size: 12px;
  text-align: center;
}

/* ─── Modal ─── */
.modal-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.65);
  display: flex; align-items: center; justify-content: center;
  z-index: 100100;
}
.modal-box {
  background: #0e1420;
  border: 1px solid rgba(59,130,246,0.25);
  border-radius: 10px;
  padding: 20px;
  width: 780px;
  max-width: 95vw;
  max-height: 80vh;
  display: flex; flex-direction: column; gap: 16px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.7);
}
.modal-header {
  display: flex; align-items: center; justify-content: space-between;
}
.modal-title { font-size: 14px; font-weight: 700; color: #e2e8f0; letter-spacing: 0.04em; }
.modal-close {
  background: none; border: none; color: #64748b;
  cursor: pointer; font-size: 14px; padding: 2px 6px;
  border-radius: 4px; transition: all 0.1s;
}
.modal-close:hover { background: rgba(239,68,68,0.15); color: #f87171; }

.modal-search {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 12px;
  background: rgba(2,6,14,0.48);
}
.modal-search-input {
  flex: 1;
  min-width: 0;
  border: none;
  background: transparent;
  color: #e2e8f0;
  font-size: 12px;
  font-weight: 700;
  outline: none;
  user-select: text;
}
.modal-search-input::placeholder { color: #475569; }
.modal-search-count {
  color: #64748b;
  font-size: 10px;
  font-weight: 700;
  white-space: nowrap;
}

.modal-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 10px;
  overflow-y: auto;
  padding-right: 4px;
}
.modal-grid.modal-list {
  grid-template-columns: 1fr;
}

.picker-card {
  position: relative;
  display: grid;
  grid-template-columns: 82px 1fr;
  gap: 10px;
  padding: 12px 14px;
  background: #0a1120;
  border: 1px solid rgba(255,255,255,0.07);
  border-radius: 10px;
  cursor: pointer;
  text-align: left;
  transition: all 0.15s;
  overflow: hidden;
  min-height: 108px;
}
.picker-card:hover {
  border-color: rgba(99,102,241,0.45);
  background: rgba(99,102,241,0.07);
}
.picker-topline {
  display: flex;
  align-items: center;
  gap: 10px;
}
.picker-preview {
  min-height: 108px;
  margin: -12px 0 -12px -14px;
}
.modal-list .picker-card {
  grid-template-columns: 130px 1fr;
  min-height: 136px;
}
.modal-list .picker-preview {
  min-height: 136px;
}
.picker-content {
  position: relative;
  z-index: 3;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}
.picker-icon {
  display: inline-block;
  width: fit-content;
  padding: 0;
  background: transparent;
  border: none;
  box-shadow: none;
  color: #f7b955;
  font-family: "JetBrains Mono", "IBM Plex Mono", "SFMono-Regular", Consolas, monospace;
  font-size: 13px;
  font-weight: 800;
  letter-spacing: -0.08em;
  font-stretch: condensed;
  text-transform: uppercase;
  text-shadow: 0 0 12px rgba(247, 185, 85, 0.18);
  transform: scaleX(0.92);
  transform-origin: left center;
  line-height: 1;
}
.picker-name { font-size: 11px; font-weight: 700; color: #e2e8f0; }
.picker-desc { font-size: 10px; color: #475569; line-height: 1.4; }
.picker-details {
  color: #94a3b8;
  font-size: 11px;
  line-height: 1.45;
}
.picker-keywords {
  color: #64748b;
  font-family: "JetBrains Mono", "IBM Plex Mono", "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
  line-height: 1.3;
}
.modal-empty {
  padding: 24px;
  border: 1px dashed rgba(255,255,255,0.1);
  border-radius: 12px;
  color: #64748b;
  font-size: 12px;
  text-align: center;
}
</style>

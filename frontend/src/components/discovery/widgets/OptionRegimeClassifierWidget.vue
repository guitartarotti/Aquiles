<template>
  <div class="orc-root">
    <div class="orc-header">
      <span class="orc-title">Option Regime Classifier</span>
      <div class="orc-controls">
        <span class="orc-underlying">{{ shortUnderlying }}</span>
        <button type="button" class="orc-btn" :class="{ loading }" :disabled="loading" @click="reload">
          {{ loading ? '...' : 'Reload' }}
        </button>
      </div>
    </div>

    <div v-if="error && !snapshot" class="orc-empty">{{ error }}</div>
    <div v-else-if="loading && !snapshot" class="orc-empty">Loading option regime inputs...</div>
    <div v-else-if="!snapshot" class="orc-empty">Waiting for enough model, IV and intraday flow data.</div>

    <template v-else>
      <div class="orc-top-grid">
        <div class="orc-hero-card">
          <div class="orc-hero-head">
            <span class="orc-badge" :class="snapshot.tone">{{ snapshot.regimeLabel }}</span>
            <span class="orc-confidence">{{ formatScore(snapshot.confidence) }}%</span>
          </div>

          <div class="orc-subregime">{{ snapshot.subRegime }}</div>
          <div class="orc-reading">{{ snapshot.marketReading }}</div>
          <div class="orc-current-explain">{{ snapshot.currentRegimeExplanation }}</div>

          <div class="orc-next-card">
            <span class="orc-next-label">Se o regime virar</span>
            <span class="orc-next-title">{{ snapshot.nextLikelyRegime }}</span>
            <span class="orc-next-reading">{{ snapshot.nextLikelyExplanation }}</span>
          </div>

          <div class="orc-hero-meta">
            <span>Próximo regime provável: <b>{{ snapshot.nextLikelyRegime }}</b></span>
            <span>Confirma acima/abaixo: <b>{{ snapshot.confirmText }}</b></span>
            <span>Invalida em: <b>{{ snapshot.invalidateText }}</b></span>
          </div>
        </div>

        <div class="orc-kpi-grid">
          <div class="orc-kpi">
            <span class="orc-kpi-label">Confiança</span>
            <span class="orc-kpi-value">{{ formatScore(snapshot.confidence) }}%</span>
            <span class="orc-kpi-sub">{{ snapshot.confidenceLabel }}</span>
          </div>
          <div class="orc-kpi">
            <span class="orc-kpi-label">Risco de transição</span>
            <span class="orc-kpi-value" :class="snapshot.transitionTone">{{ formatScore(snapshot.transitionRisk) }}%</span>
            <span class="orc-kpi-sub">{{ snapshot.transitionHint }}</span>
          </div>
          <div class="orc-kpi">
            <span class="orc-kpi-label">Pinning</span>
            <span class="orc-kpi-value">{{ formatScore(snapshot.signalScores.pinning) }}</span>
            <span class="orc-kpi-sub">{{ snapshot.pinningLabel }}</span>
          </div>
          <div class="orc-kpi">
            <span class="orc-kpi-label">Expansion</span>
            <span class="orc-kpi-value">{{ formatScore(snapshot.signalScores.expansion) }}</span>
            <span class="orc-kpi-sub">{{ snapshot.expansionLabel }}</span>
          </div>
          <div class="orc-kpi">
            <span class="orc-kpi-label">Dealer pain</span>
            <span class="orc-kpi-value">{{ formatScore(snapshot.signalScores.dealerPain) }}</span>
            <span class="orc-kpi-sub">{{ snapshot.dealerPainLabel }}</span>
          </div>
          <div class="orc-kpi">
            <span class="orc-kpi-label">Vol ignition</span>
            <span class="orc-kpi-value">{{ formatScore(snapshot.signalScores.volIgnition) }}</span>
            <span class="orc-kpi-sub">{{ snapshot.volIgnitionLabel }}</span>
          </div>
          <div class="orc-kpi">
            <span class="orc-kpi-label">Spot</span>
            <span class="orc-kpi-value">{{ formatLevel(snapshot.spot) }}</span>
            <span class="orc-kpi-sub">{{ snapshot.sessionStamp }}</span>
          </div>
          <div class="orc-kpi">
            <span class="orc-kpi-label">Sub-regime</span>
            <span class="orc-kpi-value orc-kpi-text">{{ snapshot.subRegimeShort }}</span>
            <span class="orc-kpi-sub">{{ snapshot.microReading }}</span>
          </div>
        </div>
      </div>

      <div v-if="snapshot.alerts.length" class="orc-alerts">
        <span v-for="alert in snapshot.alerts" :key="alert" class="orc-alert-pill">{{ alert }}</span>
      </div>

      <div class="orc-main-grid">
        <div class="orc-panel">
          <div class="orc-panel-head">
            <span class="orc-panel-title">Por quê?</span>
            <span class="orc-panel-sub">3 a 5 fatores explicativos</span>
          </div>
          <div class="orc-explain-list">
            <div v-for="item in snapshot.explanations" :key="item.label" class="orc-explain-row">
              <span class="orc-explain-rank">{{ item.rank }}</span>
              <div class="orc-explain-copy">
                <span class="orc-explain-label">{{ item.label }}</span>
                <span class="orc-explain-note">{{ item.note }}</span>
              </div>
              <span class="orc-explain-score">{{ formatScore(item.score) }}</span>
            </div>
          </div>
        </div>

        <div class="orc-panel">
          <div class="orc-panel-head">
            <span class="orc-panel-title">Sinais estruturais</span>
            <span class="orc-panel-sub">blend 70% regras · 30% perfil estatístico</span>
          </div>
          <div v-for="item in snapshot.signalBars" :key="item.key" class="orc-signal-row">
            <span class="orc-signal-name">{{ item.label }}</span>
            <div class="orc-signal-track">
              <div class="orc-signal-fill" :class="item.tone" :style="{ width: `${clamp(item.score, 0, 100)}%` }"></div>
            </div>
            <span class="orc-signal-score">{{ formatScore(item.score) }}</span>
          </div>
        </div>
      </div>

      <div class="orc-timeline-panel">
        <div class="orc-panel-head">
          <span class="orc-panel-title">Timeline intraday</span>
          <div class="orc-hover-panel" v-if="displayTimelinePoint">
            <span class="orc-hover-label">{{ timelineHoverPoint ? 'Hover' : 'Latest' }}</span>
            <span class="orc-hover-chip">{{ displayTimelinePoint.axisLabel }}</span>
            <span class="orc-hover-chip">{{ displayTimelinePoint.regimeLabel }}</span>
            <span class="orc-hover-chip">{{ formatScore(displayTimelinePoint.confidence) }}%</span>
          </div>
        </div>
        <div class="orc-timeline-wrap" ref="timelineWrap">
          <canvas
            v-if="timelineSeries.length > 1"
            ref="timelineCanvas"
            class="orc-timeline-canvas"
            @mouseenter="handleTimelineEnter"
            @mousemove="handleTimelineMove"
            @mouseleave="handleTimelineLeave"
          ></canvas>
          <div v-if="timelineTooltip" class="orc-tooltip" :style="timelineTooltipStyle">
            <div class="orc-tooltip-time">{{ timelineTooltip.axisLabel }}</div>
            <div class="orc-tooltip-regime">{{ timelineTooltip.regimeLabel }}</div>
            <div class="orc-tooltip-copy">{{ timelineTooltip.regimeDescription }}</div>
            <div class="orc-tooltip-meta">
              <span>Conf. {{ formatScore(timelineTooltip.confidence) }}%</span>
              <span>Trans. {{ formatScore(timelineTooltip.transitionRisk) }}%</span>
            </div>
            <div class="orc-tooltip-next">Próximo: {{ timelineTooltip.nextLikelyLabel }}</div>
          </div>
          <div v-else class="orc-empty-inline">Waiting for 1m regime history from today.</div>
        </div>
        <div class="orc-timeline-footer">
          <span class="orc-line-key"><i class="orc-line-chip conf"></i> Confiança</span>
          <span class="orc-line-key"><i class="orc-line-chip trans"></i> Transições</span>
          <span v-for="item in timelineLegendItems" :key="item.key" class="orc-line-key">
            <i class="orc-line-chip regime" :style="{ background: item.color }"></i>{{ item.label }}
          </span>
        </div>
        <div class="orc-panel-sub orc-timeline-label">{{ timelineLabel }}</div>
      </div>

      <div class="orc-bottom-grid">
        <div class="orc-panel">
          <div class="orc-panel-head">
            <span class="orc-panel-title">Próximos regimes</span>
            <span class="orc-panel-sub">matriz de probabilidade</span>
          </div>
          <div class="orc-prob-list">
            <div v-for="item in snapshot.nextProbabilities" :key="item.key" class="orc-prob-row">
              <span class="orc-prob-name">{{ item.label }}</span>
              <div class="orc-prob-track">
                <div class="orc-prob-fill" :class="item.tone" :style="{ width: `${clamp(item.probability, 0, 100)}%` }"></div>
              </div>
              <span class="orc-prob-value">{{ formatScore(item.probability) }}%</span>
            </div>
          </div>
        </div>

        <div class="orc-panel">
          <div class="orc-panel-head">
            <span class="orc-panel-title">Mudanças recentes</span>
            <span class="orc-panel-sub">transições da sessão</span>
          </div>
          <div v-if="snapshot.recentTransitions.length" class="orc-transition-list">
            <div v-for="item in snapshot.recentTransitions" :key="`${item.epoch}-${item.regimeKey}`" class="orc-transition-row">
              <span class="orc-transition-time">{{ item.label }}</span>
              <div class="orc-transition-copy">
                <span class="orc-transition-regime">{{ item.regimeLabel }}</span>
                <span class="orc-transition-note">{{ item.description }}</span>
              </div>
              <span class="orc-transition-confidence">{{ formatScore(item.confidence) }}%</span>
            </div>
          </div>
          <div v-else class="orc-empty-inline">Nenhuma troca de regime relevante na sessão.</div>
        </div>
      </div>

      <div class="orc-footer-note">
        Future aggression, dealer pain, options-led e volatility flow usam proxies intraday do XB1, fluxo de opções e estrutura de gamma já disponível na Discovery.
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { getVolIndexHistory, getVolumeActivity, getVolumeIvHistory } from '@/api/options'

const props = defineProps({
  modelData: { type: Object, default: null },
  underlyingSecurity: { type: String, default: 'IBOVE Index' },
  refreshNonce: { type: Number, default: 0 },
})

const VOV_COMPONENTS = [
  { key: 'atm', mode: 'log', weight: 0.25 },
  { key: 'skew', mode: 'diff', weight: 0.25 },
  { key: 'putWing', mode: 'log', weight: 0.20 },
  { key: 'callWing', mode: 'log', weight: 0.15 },
  { key: 'term', mode: 'diff', weight: 0.15 },
]

const WINDOW_5 = { minutes: 5, weight: 0.38 }
const WINDOW_15 = { minutes: 15, weight: 0.62 }
const AUTO_REFRESH_MS = 120_000
const MIN_FETCH_INTERVAL_MS = 75_000
const TIMELINE_HEIGHT = 86
const TIMELINE_PAD = { top: 12, right: 12, bottom: 24, left: 12 }

const REGIME_META = {
  pinning_compression: { label: 'Pinning / Compressão', tone: 'cool', reading: 'Mercado preso' },
  long_gamma_mean_reversion: { label: 'Long Gamma Mean Reversion', tone: 'cool', reading: 'Long gamma mean reversion' },
  short_gamma_expansion: { label: 'Short Gamma Expansion', tone: 'hot', reading: 'Mercado em expansão' },
  downside_hedge_pressure: { label: 'Downside Hedge Pressure', tone: 'hot', reading: 'Mercado dominado por proteção' },
  upside_call_chase: { label: 'Upside Call Chase / Squeeze', tone: 'warm', reading: 'Mercado dominado por squeeze' },
  volatility_ignition: { label: 'Volatility Ignition', tone: 'hot', reading: 'Volatilidade acelerando' },
  volatility_crush: { label: 'Volatility Crush', tone: 'cool', reading: 'Volatilidade comprimindo' },
  put_protection_demand: { label: 'Put Protection Demand', tone: 'hot', reading: 'Demanda por proteção' },
  call_overwriting: { label: 'Call Overwriting / Venda de Call', tone: 'cool', reading: 'Oferta de upside' },
  risk_reversal_bullish: { label: 'Risk Reversal Bullish', tone: 'warm', reading: 'Assimetria bullish' },
  skew_panic: { label: 'Skew Panic', tone: 'hot', reading: 'Skew em pânico' },
  dealer_pain_zone: { label: 'Dealer Pain Zone', tone: 'warn', reading: 'Dealer pain zone' },
  expiry_dominated: { label: 'Expiry Dominated', tone: 'warn', reading: 'Regime puxado por expiração' },
  futures_led_move: { label: 'Futures-Led Move', tone: 'warm', reading: 'Movimento liderado pelo futuro' },
  options_led_move: { label: 'Options-Led Move', tone: 'warm', reading: 'Movimento liderado por opções' },
  balanced_no_clear_edge: { label: 'Balanced / No Clear Edge', tone: 'neutral', reading: 'Mercado sem leitura clara' },
  transition_regime: { label: 'Transition Regime', tone: 'warn', reading: 'Regime em transição' },
}

const REGIME_COLORS = {
  pinning_compression: '#34d399',
  long_gamma_mean_reversion: '#22c55e',
  short_gamma_expansion: '#fb7185',
  downside_hedge_pressure: '#ef4444',
  upside_call_chase: '#f59e0b',
  volatility_ignition: '#f97316',
  volatility_crush: '#38bdf8',
  put_protection_demand: '#dc2626',
  call_overwriting: '#14b8a6',
  risk_reversal_bullish: '#facc15',
  skew_panic: '#e11d48',
  dealer_pain_zone: '#a78bfa',
  expiry_dominated: '#f472b6',
  futures_led_move: '#93c5fd',
  options_led_move: '#fde047',
  balanced_no_clear_edge: '#64748b',
  transition_regime: '#fb923c',
}

const REGIME_GUIDE = {
  pinning_compression: {
    description: 'Gamma local positivo, OI perto do spot e preço orbitando uma região magnética.',
    nextMove: 'Se perder o cluster ou a IV reacender, a transição natural é para expansão ou dealer pain.',
  },
  long_gamma_mean_reversion: {
    description: 'Livro em long gamma absorvendo o preço e favorecendo reversões curtas.',
    nextMove: 'Se a eficiência direcional subir e o spot escapar do centro, a leitura tende a migrar para short gamma expansion.',
  },
  short_gamma_expansion: {
    description: 'Pouca absorção local de gamma, preço fora da zona de conforto e continuidade mais provável.',
    nextMove: 'Se a superfície acelerar mais, o próximo estágio costuma ser volatility ignition ou hedge pressure.',
  },
  downside_hedge_pressure: {
    description: 'Compra de puts, skew abrindo e transmissão de proteção para o preço.',
    nextMove: 'Se o fluxo persistir e o futuro vender junto, pode evoluir para skew panic ou volatility ignition.',
  },
  upside_call_chase: {
    description: 'Calls puxando upside, call wing reprecificando e spot tentando alongar a perna.',
    nextMove: 'Se o chase ganhar corpo e o futuro acompanhar, pode virar squeeze/expansão reflexiva.',
  },
  volatility_ignition: {
    description: 'IV, vol of vol e realized acelerando ao mesmo tempo em torno de um rompimento relevante.',
    nextMove: 'Se sustentar, tende a caminhar para short gamma expansion ou stress reflexivo.',
  },
  volatility_crush: {
    description: 'IV cai, vol of vol esfria e o mercado volta a um regime mais estável de prêmio.',
    nextMove: 'Se o pinning continuar, o passo seguinte costuma ser compressão ou call overwriting.',
  },
  put_protection_demand: {
    description: 'Proteção downside em destaque, com puts e skew puxando a microestrutura.',
    nextMove: 'Se o hedge ganhar urgência, o próximo estado provável é downside hedge pressure ou skew panic.',
  },
  call_overwriting: {
    description: 'Oferta de upside via calls, compressão de IV e mercado mais travado.',
    nextMove: 'Se o preço insistir na alta, esse regime tende a ceder para upside call chase.',
  },
  risk_reversal_bullish: {
    description: 'Assimetria pró-upside, calls mais demandadas e proteção menos cara.',
    nextMove: 'Se o preço confirmar, pode evoluir para upside call chase ou options-led move.',
  },
  skew_panic: {
    description: 'Skew de puts abrindo rápido e asa de baixa distorcida de forma agressiva.',
    nextMove: 'Se contaminar ATM e realized, costuma andar para volatility ignition ou dealer pain zone.',
  },
  dealer_pain_zone: {
    description: 'Spot perto de áreas onde hedge pode acelerar e a liquidez estrutural fica mais sensível.',
    nextMove: 'Uma saída desordenada dessa zona costuma empurrar o regime para expansão ou transição reflexiva.',
  },
  expiry_dominated: {
    description: 'Expiração e concentração de OI dominam mais do que fluxo novo ou vol.',
    nextMove: 'Se passar o vencimento ou o preço escapar do pin, o regime tende a voltar para balanceado ou compressão.',
  },
  futures_led_move: {
    description: 'O futuro faz preço primeiro e as opções respondem depois.',
    nextMove: 'Se as opções começarem a amplificar o movimento, pode migrar para options-led move ou expansion.',
  },
  options_led_move: {
    description: 'O fluxo de opções está liderando a leitura e transmitindo direção para o preço.',
    nextMove: 'Se isso vier com IV e vol of vol subindo, pode avançar para volatility ignition.',
  },
  balanced_no_clear_edge: {
    description: 'Pinning e expansão próximos, sem um bloco claramente dominante.',
    nextMove: 'O próximo regime nasce quando uma das forças ganha inclinação suficiente para romper esse equilíbrio.',
  },
  transition_regime: {
    description: 'Regime híbrido, com duas leituras fortes coexistindo e risco alto de mudança de controle.',
    nextMove: 'O próximo estado costuma ser o segundo regime mais provável, desde que o nível de confirmação seja rompido.',
  },
}

const PROFILE_MAP = {
  pinning_compression: { pinning: 86, expansion: 26, skewStress: 20, callChase: 18, volIgnition: 18, dealerPain: 34, flow: 24, futureAggression: 18, expiry: 40, optionsLed: 18, futuresLed: 18, transition: 22, balanced: 22 },
  long_gamma_mean_reversion: { pinning: 82, expansion: 32, skewStress: 18, callChase: 20, volIgnition: 24, dealerPain: 30, flow: 28, futureAggression: 24, expiry: 30, optionsLed: 22, futuresLed: 26, transition: 24, balanced: 26 },
  short_gamma_expansion: { pinning: 28, expansion: 86, skewStress: 44, callChase: 42, volIgnition: 66, dealerPain: 74, flow: 62, futureAggression: 72, expiry: 20, optionsLed: 46, futuresLed: 58, transition: 40, balanced: 12 },
  downside_hedge_pressure: { pinning: 24, expansion: 78, skewStress: 82, callChase: 12, volIgnition: 72, dealerPain: 68, flow: 72, futureAggression: 66, expiry: 18, optionsLed: 62, futuresLed: 44, transition: 36, balanced: 10 },
  upside_call_chase: { pinning: 22, expansion: 82, skewStress: 18, callChase: 84, volIgnition: 64, dealerPain: 54, flow: 70, futureAggression: 62, expiry: 16, optionsLed: 58, futuresLed: 40, transition: 32, balanced: 10 },
  volatility_ignition: { pinning: 18, expansion: 84, skewStress: 52, callChase: 48, volIgnition: 90, dealerPain: 70, flow: 62, futureAggression: 72, expiry: 12, optionsLed: 50, futuresLed: 54, transition: 42, balanced: 8 },
  volatility_crush: { pinning: 68, expansion: 24, skewStress: 18, callChase: 16, volIgnition: 14, dealerPain: 24, flow: 22, futureAggression: 16, expiry: 26, optionsLed: 16, futuresLed: 18, transition: 18, balanced: 30 },
  put_protection_demand: { pinning: 28, expansion: 70, skewStress: 80, callChase: 10, volIgnition: 64, dealerPain: 60, flow: 74, futureAggression: 54, expiry: 16, optionsLed: 64, futuresLed: 36, transition: 34, balanced: 8 },
  call_overwriting: { pinning: 72, expansion: 18, skewStress: 16, callChase: 26, volIgnition: 12, dealerPain: 20, flow: 32, futureAggression: 18, expiry: 30, optionsLed: 24, futuresLed: 20, transition: 20, balanced: 24 },
  risk_reversal_bullish: { pinning: 28, expansion: 68, skewStress: 14, callChase: 72, volIgnition: 54, dealerPain: 46, flow: 62, futureAggression: 52, expiry: 16, optionsLed: 58, futuresLed: 34, transition: 28, balanced: 10 },
  skew_panic: { pinning: 20, expansion: 74, skewStress: 90, callChase: 8, volIgnition: 70, dealerPain: 64, flow: 68, futureAggression: 56, expiry: 14, optionsLed: 60, futuresLed: 34, transition: 30, balanced: 8 },
  dealer_pain_zone: { pinning: 50, expansion: 58, skewStress: 40, callChase: 32, volIgnition: 48, dealerPain: 88, flow: 34, futureAggression: 30, expiry: 26, optionsLed: 26, futuresLed: 24, transition: 52, balanced: 14 },
  expiry_dominated: { pinning: 78, expansion: 22, skewStress: 20, callChase: 16, volIgnition: 12, dealerPain: 38, flow: 14, futureAggression: 14, expiry: 92, optionsLed: 10, futuresLed: 10, transition: 16, balanced: 30 },
  futures_led_move: { pinning: 24, expansion: 72, skewStress: 24, callChase: 32, volIgnition: 46, dealerPain: 42, flow: 26, futureAggression: 86, expiry: 10, optionsLed: 18, futuresLed: 88, transition: 24, balanced: 8 },
  options_led_move: { pinning: 22, expansion: 72, skewStress: 46, callChase: 48, volIgnition: 62, dealerPain: 46, flow: 84, futureAggression: 32, expiry: 12, optionsLed: 88, futuresLed: 20, transition: 28, balanced: 8 },
  balanced_no_clear_edge: { pinning: 46, expansion: 44, skewStress: 24, callChase: 22, volIgnition: 18, dealerPain: 28, flow: 22, futureAggression: 20, expiry: 18, optionsLed: 18, futuresLed: 18, transition: 18, balanced: 86 },
  transition_regime: { pinning: 64, expansion: 66, skewStress: 48, callChase: 44, volIgnition: 60, dealerPain: 62, flow: 56, futureAggression: 52, expiry: 16, optionsLed: 40, futuresLed: 42, transition: 92, balanced: 14 },
}

const loading = ref(false)
const error = ref(null)
const dailyHistory = ref([])
const intradayHistory = ref([])
const flowEvents = ref([])
const timelineWrap = ref(null)
const timelineCanvas = ref(null)
const timelineHoverIndex = ref(null)
const timelineMetrics = ref(null)

let refreshTimer = null
let lastLoadAt = 0

const underlying = computed(() => props.underlyingSecurity || props.modelData?.underlying_security || 'IBOVE Index')
const shortUnderlying = computed(() => String(underlying.value || '').replace(/\s+Index$/i, '') || 'IBOV')

function clamp(value, low, high) {
  return Math.max(low, Math.min(high, Number(value)))
}

function safeNumber(value) {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

function mean(values) {
  if (!values.length) return null
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

function std(values) {
  if (values.length < 2) return null
  const avg = mean(values)
  if (avg == null) return null
  const variance = values.reduce((sum, value) => sum + ((value - avg) ** 2), 0) / values.length
  return Math.sqrt(Math.max(variance, 0))
}

function weightedScore(entries) {
  let totalWeight = 0
  let total = 0
  for (const entry of entries) {
    const score = clamp(entry?.score ?? 0, 0, 100)
    const weight = Number(entry?.weight ?? 0)
    if (!Number.isFinite(weight) || weight <= 0) continue
    total += score * weight
    totalWeight += weight
  }
  return totalWeight > 0 ? total / totalWeight : 0
}

function erf(value) {
  const sign = value < 0 ? -1 : 1
  const abs = Math.abs(value)
  const t = 1 / (1 + 0.3275911 * abs)
  const a1 = 0.254829592
  const a2 = -0.284496736
  const a3 = 1.421413741
  const a4 = -1.453152027
  const a5 = 1.061405429
  const poly = (((((a5 * t) + a4) * t) + a3) * t + a2) * t + a1
  const y = 1 - (poly * t * Math.exp(-(abs * abs)))
  return sign * y
}

function normalCdf(z) {
  return 0.5 * (1 + erf(z / Math.sqrt(2)))
}

function scoreFromZ(z) {
  return clamp(normalCdf(z) * 100, 0, 100)
}

function softmax(entries) {
  if (!entries.length) return []
  const maxValue = Math.max(...entries.map(item => item.value))
  const exps = entries.map(item => Math.exp(item.value - maxValue))
  const total = exps.reduce((sum, value) => sum + value, 0) || 1
  return entries.map((item, index) => ({
    ...item,
    probability: (exps[index] / total) * 100,
  }))
}

function scoreRatio(value, pivot, maxRatio = 1.0) {
  if (pivot <= 0) return 0
  return clamp((value / pivot) / maxRatio, 0, 1) * 100
}

function scoreInverseRatio(value, pivot, maxRatio = 1.0) {
  if (pivot <= 0) return 0
  return clamp(1 - ((value / pivot) / maxRatio), 0, 1) * 100
}

function scoreDistance(value, band) {
  if (band <= 0) return 0
  return clamp(1 - (Math.abs(value) / band), 0, 1) * 100
}

function signedDirectionalScore(value, pivot) {
  if (!Number.isFinite(value) || pivot <= 0) return { up: 0, down: 0 }
  return {
    up: clamp((value / pivot) * 100, 0, 100),
    down: clamp((-value / pivot) * 100, 0, 100),
  }
}

function normalizePercentileLike(value) {
  const numeric = safeNumber(value)
  if (numeric == null) return null
  return numeric <= 1 ? numeric * 100 : numeric
}

function percentileRank(values, current) {
  if (!values.length || current == null) return null
  const ordered = values.slice().sort((left, right) => left - right)
  const count = ordered.filter(value => value <= current).length
  return clamp((count / ordered.length) * 100, 0, 100)
}

function trendEfficiency(values) {
  if (!Array.isArray(values) || values.length < 2) return 0
  const first = safeNumber(values[0])
  const last = safeNumber(values[values.length - 1])
  if (first == null || last == null) return 0
  let path = 0
  for (let index = 1; index < values.length; index += 1) {
    const previous = safeNumber(values[index - 1])
    const current = safeNumber(values[index])
    if (previous == null || current == null) continue
    path += Math.abs(current - previous)
  }
  if (path <= 0) return 0
  return clamp(Math.abs(last - first) / path, 0, 1)
}

function normalizeVolRecord(record) {
  const normalized = { ...(record || {}) }
  const capturedAt = String(normalized.captured_at || normalized.reference_price_at || '').trim()
  const date = String(normalized.date || capturedAt.slice(0, 10) || '').trim()
  const parsed = capturedAt ? new Date(capturedAt) : null
  normalized.captured_at = capturedAt || null
  normalized.date = date || null
  normalized._epoch = parsed && !Number.isNaN(parsed.getTime()) ? parsed.getTime() : null
  normalized._sessionDate = date || null
  normalized._price = safeNumber(normalized.reference_price ?? normalized.spot ?? normalized.reference_spot)
  return normalized
}

function normalizeFlowEvent(event) {
  const normalized = { ...(event || {}) }
  const capturedAt = String(normalized.captured_at || '').trim()
  const parsed = capturedAt ? new Date(capturedAt) : null
  normalized._epoch = parsed && !Number.isNaN(parsed.getTime()) ? parsed.getTime() : null
  normalized._sessionDate = String(normalized.session_date || capturedAt.slice(0, 10) || '').trim() || null
  normalized._spot = safeNumber(normalized.spot_price)
  normalized._strike = safeNumber(normalized.strike)
  normalized._volume = Math.max(safeNumber(normalized.volume_delta) || 0, 0)
  normalized._delta = Math.abs(safeNumber(normalized.observed_delta) || 0.5)
  normalized._days = safeNumber(normalized.days_to_maturity) || null
  normalized._side = String(normalized.put_call || '').toUpperCase() === 'P' ? 'P' : 'C'
  return normalized
}

function buildDailyHistoryFromIntraday(records) {
  const latestByDate = new Map()
  for (const record of records) {
    const date = String(record?._sessionDate || record?.date || '').trim()
    if (!date) continue
    const previous = latestByDate.get(date)
    const previousEpoch = previous?._epoch ?? -Infinity
    const currentEpoch = record?._epoch ?? -Infinity
    if (!previous || currentEpoch >= previousEpoch) {
      latestByDate.set(date, record)
    }
  }
  return Array.from(latestByDate.values()).sort((left, right) => {
    const leftDate = String(left?.date || left?._sessionDate || '')
    const rightDate = String(right?.date || right?._sessionDate || '')
    return leftDate.localeCompare(rightDate)
  })
}

function withLocalTimeout(promise, label, timeoutMs = 12_000) {
  return Promise.race([
    promise,
    new Promise((_, reject) => {
      window.setTimeout(() => reject(new Error(`${label} timeout`)), timeoutMs)
    }),
  ])
}

function bucketRecordsByMinute(records) {
  const minuteMap = new Map()
  for (const record of records) {
    const epoch = record?._epoch
    if (epoch == null) continue
    const minuteEpoch = Math.floor(epoch / 60_000) * 60_000
    const existing = minuteMap.get(minuteEpoch)
    if (!existing || (record._epoch || 0) >= (existing._epoch || 0)) {
      minuteMap.set(minuteEpoch, {
        ...record,
        _epoch: minuteEpoch,
        _minuteEpoch: minuteEpoch,
      })
    }
  }
  return Array.from(minuteMap.values()).sort((left, right) => (left._epoch || 0) - (right._epoch || 0))
}

function trailingRecords(records, index, minutes) {
  if (minutes == null) return records.slice(0, index + 1)
  const currentEpoch = records[index]?._epoch
  if (currentEpoch == null) return []
  const minEpoch = currentEpoch - (minutes * 60 * 1000)
  let start = index
  while (start > 0) {
    const epoch = records[start - 1]?._epoch
    if (epoch == null || epoch < minEpoch) break
    start -= 1
  }
  return records.slice(start, index + 1)
}

function nearestByMinutesAtIndex(series, endIndex, targetMinutesAgo) {
  const last = series[endIndex]
  const currentEpoch = last?._epoch ?? last?.epoch
  if (currentEpoch == null) return last || null
  const targetEpoch = currentEpoch - (targetMinutesAgo * 60 * 1000)
  let candidate = last || null
  for (let index = endIndex; index >= 0; index -= 1) {
    const item = series[index]
    const epoch = item?._epoch ?? item?.epoch
    if (epoch == null) continue
    candidate = item
    if (epoch <= targetEpoch) return item
  }
  return candidate
}

function levelFor(componentKey, record) {
  if (!record) return null
  if (componentKey === 'atm') return safeNumber(record.iv_atm)
  if (componentKey === 'skew') {
    const skew = safeNumber(record.skew_25d)
    if (skew != null) return skew
    const put25 = safeNumber(record.iv_25d_put)
    const call25 = safeNumber(record.iv_25d_call)
    return put25 != null && call25 != null ? (put25 - call25) : null
  }
  if (componentKey === 'putWing') return safeNumber(record.iv_10d_put ?? record.iv_15d_put)
  if (componentKey === 'callWing') return safeNumber(record.iv_10d_call ?? record.iv_15d_call)
  if (componentKey === 'term') {
    const term = Array.isArray(record.term_structure) ? record.term_structure : []
    const values = term
      .map(item => safeNumber(item?.iv_atm))
      .filter(value => value != null)
    if (values.length >= 2) {
      const near = values[0]
      const rest = values.slice(1)
      const restMean = mean(rest)
      return restMean == null ? null : near - restMean
    }
    const nearAtm = safeNumber(record.iv_atm)
    const medium = safeNumber(record.monthly_term_30d_iv)
    return nearAtm != null && medium != null ? (nearAtm - medium) : null
  }
  return null
}

function buildReturns(values, mode) {
  const returns = []
  for (let index = 1; index < values.length; index += 1) {
    const previous = values[index - 1]
    const current = values[index]
    if (previous == null || current == null) continue
    if (mode === 'log') {
      if (previous <= 0 || current <= 0) continue
      returns.push(Math.log(current / previous))
    } else {
      returns.push(current - previous)
    }
  }
  return returns
}

function computeWindowSeries(records, windowMinutes) {
  const output = {}
  VOV_COMPONENTS.forEach(component => {
    output[component.key] = new Array(records.length).fill(null)
  })
  for (let index = 0; index < records.length; index += 1) {
    const sample = trailingRecords(records, index, windowMinutes)
    VOV_COMPONENTS.forEach(component => {
      const levels = sample
        .map(record => levelFor(component.key, record))
        .filter(value => value != null)
      const returns = buildReturns(levels, component.mode)
      output[component.key][index] = returns.length >= 2 ? std(returns) : null
    })
  }
  return output
}

function computeStats(seriesMap) {
  const stats = {}
  VOV_COMPONENTS.forEach(component => {
    const values = (seriesMap[component.key] || []).filter(value => value != null)
    stats[component.key] = { mean: mean(values), std: std(values) }
  })
  return stats
}

function computeZScore(value, stats) {
  if (value == null || !stats || stats.mean == null || stats.std == null || stats.std <= 1e-12) return 0
  return (value - stats.mean) / stats.std
}

function buildWindowScoreSeries(records, windowDef, baselineRecords = records) {
  const rawSeries = computeWindowSeries(records, windowDef.minutes)
  const baselineRaw = computeWindowSeries(baselineRecords, windowDef.minutes)
  const stats = computeStats(baselineRaw)
  const scoreSeries = []
  for (let index = 0; index < records.length; index += 1) {
    let totalWeight = 0
    let totalZ = 0
    const componentScores = {}
    VOV_COMPONENTS.forEach(component => {
      const z = computeZScore(rawSeries[component.key][index], stats[component.key])
      componentScores[component.key] = scoreFromZ(z)
      totalWeight += component.weight
      totalZ += component.weight * z
    })
    const z = totalWeight > 0 ? totalZ / totalWeight : 0
    scoreSeries.push({
      epoch: records[index]?._epoch,
      timestamp: records[index]?.captured_at || null,
      z,
      score: scoreFromZ(z),
      componentScores,
    })
  }
  return {
    scoreSeries,
    latest: scoreSeries[scoreSeries.length - 1] || null,
  }
}

const latestSessionDate = computed(() => {
  const last = intradayHistory.value[intradayHistory.value.length - 1]
  return last?._sessionDate || null
})

const intradayMinuteHistory = computed(() => bucketRecordsByMinute(intradayHistory.value))

const sessionHistory = computed(() => {
  const sessionDate = latestSessionDate.value
  if (!sessionDate) return []
  return intradayMinuteHistory.value.filter(item => item._sessionDate === sessionDate)
})

const sessionFlow = computed(() => {
  const sessionDate = latestSessionDate.value
  return flowEvents.value
    .filter(item => (sessionDate ? item._sessionDate === sessionDate : true))
    .filter(item => item._epoch != null && item._volume > 0)
    .sort((left, right) => (left._epoch || 0) - (right._epoch || 0))
})

const marketContext = computed(() => props.modelData?.market_context ?? {})
const aggregates = computed(() => props.modelData?.aggregates ?? {})
const pressure = computed(() => props.modelData?.pressure ?? {})

const baseByStrike = computed(() => {
  const rows = aggregates.value?.by_strike ?? []
  return rows
    .map(row => {
      const strike = safeNumber(row.strike ?? row.key)
      const gex = safeNumber(row.gex) || 0
      const callOi = safeNumber(row.call_oi) || 0
      const putOi = safeNumber(row.put_oi) || 0
      const vex = safeNumber(row.vex) || 0
      const cex = safeNumber(row.cex) || 0
      return {
        strike,
        gex,
        callOi,
        putOi,
        totalOi: callOi + putOi,
        vex,
        cex,
      }
    })
    .filter(row => row.strike != null && row.totalOi > 0)
    .sort((left, right) => left.strike - right.strike)
})

function bandCenter(band) {
  const low = safeNumber(band?.low)
  const high = safeNumber(band?.high)
  if (low == null || high == null) return null
  return (low + high) / 2
}

function bandWidth(band) {
  const low = safeNumber(band?.low)
  const high = safeNumber(band?.high)
  if (low == null || high == null) return null
  return Math.max(high - low, 0)
}

function insideBand(spot, band) {
  const low = safeNumber(band?.low)
  const high = safeNumber(band?.high)
  if (spot == null || low == null || high == null) return false
  return spot >= low && spot <= high
}

function distanceToBand(spot, band) {
  const low = safeNumber(band?.low)
  const high = safeNumber(band?.high)
  if (spot == null || low == null || high == null) return null
  if (spot < low) return low - spot
  if (spot > high) return spot - high
  return 0
}

function nearestZeroCross(points, field) {
  const rows = Array.isArray(points) ? points : []
  let best = null
  for (let index = 1; index < rows.length; index += 1) {
    const prev = rows[index - 1]
    const next = rows[index]
    const prevSpot = safeNumber(prev?.spot ?? prev?.strike)
    const nextSpot = safeNumber(next?.spot ?? next?.strike)
    const prevValue = safeNumber(prev?.[field])
    const nextValue = safeNumber(next?.[field])
    if (prevSpot == null || nextSpot == null || prevValue == null || nextValue == null) continue
    if (prevValue === 0) return prevSpot
    if (nextValue === 0) return nextSpot
    if ((prevValue < 0 && nextValue > 0) || (prevValue > 0 && nextValue < 0)) {
      const ratio = Math.abs(prevValue) / (Math.abs(prevValue) + Math.abs(nextValue))
      const level = prevSpot + ((nextSpot - prevSpot) * ratio)
      if (best == null || Math.abs(level) < Math.abs(best)) best = level
    }
  }
  return best
}

function nearestGammaFlipDistance(spot, points) {
  if (spot == null || !points.length) return null
  return points.reduce((best, level) => {
    const distance = Math.abs(level - spot)
    return best == null || distance < best ? distance : best
  }, null)
}

function bestMagnetForSpot(meta, spot) {
  const localBand = Math.max((spot || 0) * 0.005, 1000)
  const searchBand = Math.max(localBand * 3, 3500)
  let best = null
  for (const row of meta.rows) {
    const distance = Math.abs(row.strike - spot)
    const proximity = clamp(1 - (distance / searchBand), 0, 1)
    if (proximity <= 0) continue
    const strength = (0.60 * (row.totalOi / meta.maxOi)) + (0.40 * (Math.abs(row.gex) / meta.maxAbsRowGex))
    const score = proximity * strength
    if (!best || score > best.score) {
      best = {
        strike: row.strike,
        distance,
        proximity,
        strength,
        score,
        gex: row.gex,
        totalOi: row.totalOi,
      }
    }
  }
  return best
}

function bestWall(meta, spot, direction) {
  const candidates = meta.rows.filter(row => direction > 0 ? row.strike >= spot : row.strike <= spot)
  let best = null
  for (const row of candidates) {
    const strength = (0.60 * (row.totalOi / meta.maxOi)) + (0.40 * (Math.abs(row.gex) / meta.maxAbsRowGex))
    const distance = Math.abs(row.strike - spot)
    const score = strength * clamp(1 - (distance / Math.max(spot * 0.02, 4000)), 0, 1)
    if (!best || score > best.score) best = { strike: row.strike, score, totalOi: row.totalOi, gex: row.gex, distance }
  }
  return best
}

const dexNeutralLevel = computed(() => nearestZeroCross(pressure.value?.curve ?? [], 'dex'))

const structureMeta = computed(() => {
  const rows = baseByStrike.value
  const totalOi = rows.reduce((sum, row) => sum + row.totalOi, 0)
  const totalAbsGex = rows.reduce((sum, row) => sum + Math.abs(row.gex), 0)
  const maxOi = Math.max(...rows.map(row => row.totalOi), 1)
  const maxAbsRowGex = Math.max(...rows.map(row => Math.abs(row.gex)), 1)
  const gammaFlipPoints = (props.modelData?.gamma_flip_history?.latest_flip_points ?? [])
    .map(value => safeNumber(value))
    .filter(value => value != null)
  const totals = aggregates.value?.totals ?? {}
  return {
    rows,
    totalOi,
    totalAbsGex,
    maxOi,
    maxAbsRowGex,
    totals,
    pinningBand: pressure.value?.pinning_band ?? {},
    accelerationBand: pressure.value?.acceleration_band ?? {},
    decompressionBand: pressure.value?.decompression_band ?? {},
    gammaFlipPoints,
    dexNeutral: dexNeutralLevel.value,
  }
})

function structureSnapshot(meta, spot) {
  if (!meta.rows.length || spot == null) {
    return {
      localBand: 1000,
      localGex: 0,
      dominantMagnet: null,
      pinningComponents: {},
      expansionComponents: {},
      gammaLevelBreakScore: 0,
      airPocketScore: 0,
      flipProximityScore: 0,
      upperWall: null,
      lowerWall: null,
      directionBias: 1,
    }
  }

  const localBand = Math.max(spot * 0.005, 1000)
  const shellBand = Math.max(spot * 0.012, 2500)
  const localRows = meta.rows.filter(row => Math.abs(row.strike - spot) <= localBand)
  const shellRows = meta.rows.filter(row => Math.abs(row.strike - spot) > localBand && Math.abs(row.strike - spot) <= shellBand)
  const localGex = localRows.reduce((sum, row) => sum + row.gex, 0)
  const localAbsGex = localRows.reduce((sum, row) => sum + Math.abs(row.gex), 0)
  const localOi = localRows.reduce((sum, row) => sum + row.totalOi, 0)
  const shellAbsGex = shellRows.reduce((sum, row) => sum + Math.abs(row.gex), 0)
  const shellOi = shellRows.reduce((sum, row) => sum + row.totalOi, 0)
  const dominantMagnet = bestMagnetForSpot(meta, spot)
  const pinCenter = bandCenter(meta.pinningBand)
  const pinWidth = bandWidth(meta.pinningBand)
  const pinDistance = pinCenter != null ? Math.abs(spot - pinCenter) : null
  const insidePin = insideBand(spot, meta.pinningBand)
  const distanceInsideCluster = insidePin
    ? 72 + (28 * clamp(1 - ((pinDistance || 0) / Math.max((pinWidth || 1) / 2, 1)), 0, 1))
    : scoreDistance(distanceToBand(spot, meta.pinningBand) ?? (localBand * 1.6), localBand * 1.4)

  const localLongGammaScore = scoreRatio(Math.max(localGex, 0), Math.max(meta.totalAbsGex * 0.10, 1), 1.0)
  const localShortGammaScore = scoreRatio(Math.max(-localGex, 0), Math.max(meta.totalAbsGex * 0.10, 1), 1.0)
  const lowGammaScore = scoreInverseRatio(localAbsGex, Math.max(meta.totalAbsGex * 0.12, 1), 1.0)
  const oiConcentrationScore = scoreRatio(localOi, Math.max(meta.totalOi * 0.22, 1), 1.0)
  const strikeMagnetScore = dominantMagnet
    ? clamp(dominantMagnet.proximity * dominantMagnet.strength * 140, 0, 100)
    : 0

  const airPocketScore = clamp(
    (
      (1 - clamp(shellOi / Math.max(meta.totalOi * 0.22, 1), 0, 1)) * 0.55
      + (1 - clamp(shellAbsGex / Math.max(meta.totalAbsGex * 0.20, 1), 0, 1)) * 0.45
    ) * 100,
    0,
    100,
  )

  const flipDistance = nearestGammaFlipDistance(spot, meta.gammaFlipPoints)
  const flipProximityScore = flipDistance != null ? scoreDistance(flipDistance, localBand * 0.85) : 0
  const upperWall = bestWall(meta, spot, 1)
  const lowerWall = bestWall(meta, spot, -1)

  let gammaLevelBreakScore = 12
  if (insideBand(spot, meta.decompressionBand)) gammaLevelBreakScore = 86
  else if (insideBand(spot, meta.accelerationBand)) gammaLevelBreakScore = 72
  else if (!insidePin) gammaLevelBreakScore = 54
  gammaLevelBreakScore = clamp(gammaLevelBreakScore + (flipProximityScore * 0.16), 0, 100)

  const dexNeutralDistance = meta.dexNeutral != null ? Math.abs(meta.dexNeutral - spot) : null
  const dexNeutralScore = dexNeutralDistance != null ? scoreDistance(dexNeutralDistance, localBand * 1.0) : 0
  const directionBias = Math.sign((dominantMagnet?.strike ?? pinCenter ?? spot) - spot) || Math.sign(localGex) || 1

  return {
    localBand,
    localGex,
    dominantMagnet,
    upperWall,
    lowerWall,
    pinCenter,
    flipDistance,
    dexNeutralDistance,
    pinningComponents: {
      localLongGammaScore,
      oiConcentrationScore,
      strikeMagnetScore,
      distanceInsideCluster,
      dexNeutralScore,
    },
    expansionComponents: {
      shortGammaOrLowGammaScore: Math.max(localShortGammaScore, lowGammaScore),
      gammaLevelBreakScore,
      airPocketScore,
      flipProximityScore,
    },
    gammaLevelBreakScore,
    airPocketScore,
    flipProximityScore,
    dexNeutralScore,
    directionBias,
  }
}

function flowScoreForEvent(item, fallbackSpot) {
  const eventSpot = item._spot || fallbackSpot
  const strike = item._strike || eventSpot || fallbackSpot
  const distPct = eventSpot > 0 ? Math.abs(strike - eventSpot) / eventSpot : 0
  const proxWeight = distPct <= 0.015 ? 1.2 : distPct <= 0.04 ? 1.0 : distPct <= 0.08 ? 0.65 : 0.35
  const daysWeight = item._days != null ? (item._days <= 30 ? 1.0 : item._days <= 60 ? 0.8 : 0.6) : 0.85
  const deltaWeight = 0.55 + (0.45 * clamp(item._delta, 0, 1))
  return item._volume * proxWeight * daysWeight * deltaWeight
}

function buildFlowWindowSnapshots(records, flow, fallbackSpot) {
  if (!records.length) return []
  const prepared = flow
    .filter(item => item._epoch != null && item._volume > 0)
    .map(item => ({
      epoch: item._epoch,
      side: item._side,
      score: flowScoreForEvent(item, fallbackSpot),
    }))
    .filter(item => item.score > 0)
    .sort((left, right) => left.epoch - right.epoch)

  let start = 0
  let end = 0
  let callFlow = 0
  let putFlow = 0

  return records.map(record => {
    const currentEpoch = record?._epoch
    if (currentEpoch == null) {
      return { callFlow: 0, putFlow: 0, totalFlow: 0, flowImbalance: 0, directionalFlowScore: 0 }
    }
    while (end < prepared.length && prepared[end].epoch <= currentEpoch) {
      if (prepared[end].side === 'P') putFlow += prepared[end].score
      else callFlow += prepared[end].score
      end += 1
    }
    const cutoffEpoch = currentEpoch - (30 * 60 * 1000)
    while (start < end && prepared[start].epoch < cutoffEpoch) {
      if (prepared[start].side === 'P') putFlow -= prepared[start].score
      else callFlow -= prepared[start].score
      start += 1
    }
    callFlow = Math.max(callFlow, 0)
    putFlow = Math.max(putFlow, 0)
    const totalFlow = callFlow + putFlow
    const flowImbalance = totalFlow > 0 ? (callFlow - putFlow) / totalFlow : 0
    const directionalFlowScore = totalFlow > 0
      ? clamp(Math.abs(flowImbalance) * Math.sqrt(totalFlow / 2500) * 100, 0, 100)
      : 0
    return { callFlow, putFlow, totalFlow, flowImbalance, directionalFlowScore }
  })
}

function formatScore(value) {
  const numeric = safeNumber(value)
  if (numeric == null) return '--'
  return `${Math.round(clamp(numeric, 0, 100))}`
}

function formatLevel(value) {
  const numeric = safeNumber(value)
  if (numeric == null) return '--'
  return Math.round(numeric).toLocaleString('pt-BR')
}

function sessionStampText(record) {
  const value = String(record?.captured_at || '').trim()
  if (!value) return 'sem timestamp'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function buildFeaturePoint(records, index, surfacePack, meta, flowWindow, openPrice, dailyIvPercentile) {
  const record = records[index]
  const spot = safeNumber(record?._price)
  if (spot == null) return null

  const structure = structureSnapshot(meta, spot)
  const fifteenSlice = trailingRecords(records, index, 15)
  const thirtySlice = trailingRecords(records, index, 30)
  const prices15 = fifteenSlice.map(item => item?._price).filter(value => value != null)
  const prices30 = thirtySlice.map(item => item?._price).filter(value => value != null)
  const trendEff15 = trendEfficiency(prices15)
  const trendEff30 = trendEfficiency(prices30)
  const latestPrice = prices15.length ? prices15[prices15.length - 1] : spot

  const prev15 = nearestByMinutesAtIndex(records, index, 15)
  const prev30 = nearestByMinutesAtIndex(records, index, 30)
  const ivCurrent = safeNumber(record.iv_atm)
  const rvCurrent = safeNumber(record.rv_garch_intraday ?? record.rv_live_3d ?? record.rv_live_5d)
  const ivPrev15 = safeNumber(prev15?.iv_atm)
  const ivDelta15mPts = ivCurrent != null && ivPrev15 != null ? (ivCurrent - ivPrev15) * 100 : 0

  const skewCurrent = levelFor('skew', record)
  const skewPrev15 = levelFor('skew', prev15)
  const skewDelta15m = skewCurrent != null && skewPrev15 != null ? (skewCurrent - skewPrev15) : 0

  const putWingCurrent = levelFor('putWing', record)
  const putWingPrev15 = levelFor('putWing', prev15)
  const putWingDelta15mPts = putWingCurrent != null && putWingPrev15 != null ? (putWingCurrent - putWingPrev15) * 100 : 0

  const callWingCurrent = levelFor('callWing', record)
  const callWingPrev15 = levelFor('callWing', prev15)
  const callWingDelta15mPts = callWingCurrent != null && callWingPrev15 != null ? (callWingCurrent - callWingPrev15) * 100 : 0

  const score5 = surfacePack.five.scoreSeries[index]?.score ?? null
  const score15 = surfacePack.fifteen.scoreSeries[index]?.score ?? null
  const surfaceMotionScore = (
    ((score5 ?? score15 ?? 0) * WINDOW_5.weight)
    + ((score15 ?? score5 ?? 0) * WINDOW_15.weight)
  ) / (WINDOW_5.weight + WINDOW_15.weight)

  const prevSurface15 = nearestByMinutesAtIndex(surfacePack.fifteenAligned, index, 15)
  const surfaceMotionDelta = surfaceMotionScore - (safeNumber(prevSurface15?.score) || 0)

  const flowImbalance = flowWindow?.flowImbalance || 0
  const directionalFlowScore = flowWindow?.directionalFlowScore || 0
  const totalFlow = flowWindow?.totalFlow || 0
  const totalOi = Math.max(meta.totalOi, 1)
  const volumeOiScore = scoreRatio(totalFlow, totalOi * 0.018, 1.0)

  const pinAnchor = structure.dominantMagnet?.strike ?? structure.pinCenter ?? latestPrice
  const dayPrices = records.slice(0, index + 1).map(item => safeNumber(item?._price)).filter(value => value != null)
  const dayRange = dayPrices.length ? Math.max(...dayPrices) - Math.min(...dayPrices) : 0
  const open = openPrice ?? latestPrice
  const spot15 = safeNumber(prev15?._price) ?? open
  const spot30 = safeNumber(prev30?._price) ?? open
  const move15 = spot - spot15
  const move30 = spot - spot30
  const directionalDistance = Math.abs(latestPrice - pinAnchor)
  const priceWindowMaxAnchorDist = prices30.length
    ? Math.max(...prices30.map(price => Math.abs(price - pinAnchor)))
    : directionalDistance
  const meanReversionScore = clamp((1 - trendEff15) * (1 - clamp(directionalDistance / Math.max(priceWindowMaxAnchorDist || structure.localBand, 1), 0, 1)) * 120, 0, 100)
  const rangeExtension = dayRange > 0 ? Math.abs(latestPrice - open) / dayRange : 0
  const futureAggressionScore = clamp(((trendEff30 * 0.62) + (clamp(directionalDistance / structure.localBand, 0, 1) * 0.23) + (clamp(rangeExtension, 0, 1) * 0.15)) * 100, 0, 100)

  const rvGap = ivCurrent != null && rvCurrent != null ? ivCurrent - rvCurrent : null
  const lowRealizedVolScore = rvGap != null
    ? clamp((clamp(rvGap / Math.max(ivCurrent * 0.35, 0.02), 0, 1) * 0.65 + (1 - trendEff15) * 0.35) * 100, 0, 100)
    : clamp((1 - trendEff15) * 70, 0, 100)
  const rvExpansionScore = rvGap != null
    ? clamp(((1 - clamp(rvGap / Math.max(ivCurrent * 0.25, 0.015), 0, 1)) * 0.45 + trendEff30 * 0.55) * 100, 0, 100)
    : clamp(trendEff30 * 70, 0, 100)

  const stableWingScore = clamp(1 - ((Math.abs(putWingDelta15mPts) + Math.abs(callWingDelta15mPts) + Math.abs(skewDelta15m * 100)) / 3.0), 0, 1) * 100
  const ivCompressionScore = clamp(
    (
      clamp((-ivDelta15mPts) / 0.7, 0, 1) * 0.40
      + (1 - (surfaceMotionScore / 100)) * 0.35
      + (stableWingScore / 100) * 0.25
    ) * 100,
    0,
    100,
  )
  const ivExpansionScore = clamp(
    (
      clamp(ivDelta15mPts / 0.8, 0, 1) * 0.38
      + (surfaceMotionScore / 100) * 0.34
      + clamp((Math.max(putWingDelta15mPts, callWingDelta15mPts, Math.abs(skewDelta15m * 100))) / 1.0, 0, 1) * 0.28
    ) * 100,
    0,
    100,
  )

  const skewStressScore = clamp(Math.max(skewDelta15m * 100, 0) * 56, 0, 100)
  const skewClosingScore = clamp(Math.max((-skewDelta15m) * 100, 0) * 56, 0, 100)
  const putWingStressScore = clamp(Math.max(putWingDelta15mPts, 0) * 65, 0, 100)
  const callWingStressScore = clamp(Math.max(callWingDelta15mPts, 0) * 65, 0, 100)
  const surfaceDistortionScore = weightedScore([
    { score: surfaceMotionScore, weight: 0.45 },
    { score: Math.max(skewStressScore, skewClosingScore * 0.35), weight: 0.18 },
    { score: putWingStressScore, weight: 0.22 },
    { score: callWingStressScore, weight: 0.15 },
  ])

  const callBiasScore = clamp(directionalFlowScore * Math.max(flowImbalance, 0), 0, 100)
  const putBiasScore = clamp(directionalFlowScore * Math.max(-flowImbalance, 0), 0, 100)

  const upMoveScore = clamp((move15 / structure.localBand) * 100, 0, 100)
  const downMoveScore = clamp((-move15 / structure.localBand) * 100, 0, 100)
  const move30Scores = signedDirectionalScore(move30, Math.max(structure.localBand * 1.4, 1))

  const volatilityFlowScore = weightedScore([
    { score: Math.max(putBiasScore, callBiasScore), weight: 0.30 },
    { score: surfaceDistortionScore, weight: 0.25 },
    { score: Math.max(putWingStressScore, callWingStressScore, skewStressScore), weight: 0.25 },
    { score: ivExpansionScore, weight: 0.20 },
  ])

  const expiryDays = safeNumber(marketContext.value?.days_to_expiry) || 999
  const expiryDominatedScore = expiryDays <= 1 ? 100
    : expiryDays <= 3 ? 86
      : expiryDays <= 5 ? 68
        : expiryDays <= 10 ? 40
          : 12

  const vannaPressureScore = scoreRatio(Math.abs(safeNumber(meta.totals?.vex) || 0), Math.max(meta.totalAbsGex * 0.08, 1), 1.0)
  const charmPressureScore = scoreRatio(Math.abs(safeNumber(meta.totals?.cex) || 0), Math.max(meta.totalAbsGex * 0.08, 1), 1.0)
  const gexPositiveScore = scoreRatio(Math.max(safeNumber(meta.totals?.gex) || 0, 0), Math.max(meta.totalAbsGex * 0.14, 1), 1.0)
  const gexNegativeScore = scoreRatio(Math.max(-(safeNumber(meta.totals?.gex) || 0), 0), Math.max(meta.totalAbsGex * 0.14, 1), 1.0)
  const dexPositiveScore = scoreRatio(Math.max(safeNumber(meta.totals?.dex) || 0, 0), Math.max(Math.abs(safeNumber(meta.totals?.dex) || 0), 1) * 0.45, 1.0)
  const dexNegativeScore = scoreRatio(Math.max(-(safeNumber(meta.totals?.dex) || 0), 0), Math.max(Math.abs(safeNumber(meta.totals?.dex) || 0), 1) * 0.45, 1.0)

  const pinningComponents = [
    { label: 'Local long gamma', score: structure.pinningComponents.localLongGammaScore || 0 },
    { label: 'OI perto do spot', score: structure.pinningComponents.oiConcentrationScore || 0 },
    { label: 'Strike magnet', score: structure.pinningComponents.strikeMagnetScore || 0 },
    { label: 'IV compression', score: ivCompressionScore },
    { label: 'Low realized vol', score: lowRealizedVolScore },
    { label: 'Mean reversion', score: meanReversionScore },
    { label: 'Dentro do cluster', score: structure.pinningComponents.distanceInsideCluster || 0 },
  ]
  const expansionComponents = [
    { label: 'Short/low gamma', score: structure.expansionComponents.shortGammaOrLowGammaScore || 0 },
    { label: 'IV expansion', score: ivExpansionScore },
    { label: 'Vol of vol rising', score: surfaceMotionScore },
    { label: 'Trend efficiency', score: clamp(trendEff30 * 100, 0, 100) },
    { label: 'Gamma level break', score: structure.gammaLevelBreakScore || 0 },
    { label: 'Directional flow', score: directionalFlowScore },
    { label: 'Future aggression', score: futureAggressionScore },
    { label: 'Air pocket', score: structure.airPocketScore || 0 },
  ]
  const pinningScore = mean(pinningComponents.map(item => item.score)) || 0
  const expansionScore = mean(expansionComponents.map(item => item.score)) || 0

  const dealerPainScore = weightedScore([
    { score: structure.gammaLevelBreakScore || 0, weight: 0.24 },
    { score: structure.airPocketScore || 0, weight: 0.16 },
    { score: structure.flipProximityScore || 0, weight: 0.12 },
    { score: structure.pinningComponents.dexNeutralScore || 0, weight: 0.08 },
    { score: surfaceDistortionScore, weight: 0.14 },
    { score: vannaPressureScore, weight: 0.12 },
    { score: charmPressureScore, weight: 0.10 },
    { score: futureAggressionScore, weight: 0.04 },
  ])

  const volIgnitionScore = weightedScore([
    { score: ivExpansionScore, weight: 0.24 },
    { score: surfaceMotionScore, weight: 0.24 },
    { score: rvExpansionScore, weight: 0.18 },
    { score: structure.gammaLevelBreakScore || 0, weight: 0.16 },
    { score: futureAggressionScore, weight: 0.18 },
  ])

  const optionsLedScore = weightedScore([
    { score: directionalFlowScore, weight: 0.32 },
    { score: volatilityFlowScore, weight: 0.28 },
    { score: surfaceDistortionScore, weight: 0.20 },
    { score: volumeOiScore, weight: 0.10 },
    { score: clamp(directionalFlowScore - (futureAggressionScore * 0.5), 0, 100), weight: 0.10 },
  ])

  const futuresLedScore = weightedScore([
    { score: futureAggressionScore, weight: 0.42 },
    { score: clamp(trendEff30 * 100, 0, 100), weight: 0.22 },
    { score: structure.gammaLevelBreakScore || 0, weight: 0.16 },
    { score: clamp(100 - directionalFlowScore, 0, 100), weight: 0.20 },
  ])

  const putProtectionDemandScore = weightedScore([
    { score: putBiasScore, weight: 0.26 },
    { score: skewStressScore, weight: 0.24 },
    { score: putWingStressScore, weight: 0.24 },
    { score: dexNegativeScore, weight: 0.12 },
    { score: ivExpansionScore, weight: 0.14 },
  ])

  const callOverwritingScore = weightedScore([
    { score: callBiasScore, weight: 0.24 },
    { score: ivCompressionScore, weight: 0.24 },
    { score: pinningScore, weight: 0.22 },
    { score: lowRealizedVolScore, weight: 0.18 },
    { score: clamp(100 - callWingStressScore, 0, 100), weight: 0.12 },
  ])

  const riskReversalBullishScore = weightedScore([
    { score: callBiasScore, weight: 0.26 },
    { score: skewClosingScore, weight: 0.24 },
    { score: dexPositiveScore, weight: 0.18 },
    { score: upMoveScore, weight: 0.16 },
    { score: expansionScore, weight: 0.16 },
  ])

  const volCrushScore = weightedScore([
    { score: ivCompressionScore, weight: 0.28 },
    { score: clamp(100 - surfaceMotionScore, 0, 100), weight: 0.22 },
    { score: lowRealizedVolScore, weight: 0.18 },
    { score: skewClosingScore, weight: 0.12 },
    { score: pinningScore, weight: 0.20 },
  ])

  const transitionPressureScore = weightedScore([
    { score: clamp(100 - Math.abs(pinningScore - expansionScore), 0, 100), weight: 0.42 },
    { score: Math.min(pinningScore, expansionScore), weight: 0.18 },
    { score: surfaceMotionScore, weight: 0.16 },
    { score: structure.gammaLevelBreakScore || 0, weight: 0.14 },
    { score: directionalFlowScore, weight: 0.10 },
  ])

  const balancedScore = weightedScore([
    { score: clamp(100 - Math.abs(pinningScore - expansionScore), 0, 100), weight: 0.56 },
    { score: clamp(100 - Math.max(volIgnitionScore, directionalFlowScore, futureAggressionScore, dealerPainScore), 0, 100), weight: 0.44 },
  ])

  const ivRankScore = normalizePercentileLike(marketContext.value?.iv_rank)
  const ivPercentileScore = normalizePercentileLike(marketContext.value?.iv_percentile ?? dailyIvPercentile)
  const vrpRichScore = rvGap != null
    ? clamp((rvGap / Math.max(ivCurrent * 0.30, 0.02)) * 100, 0, 100)
    : 0
  const vrpTightScore = rvGap != null
    ? clamp(100 - ((Math.abs(rvGap) / Math.max(ivCurrent * 0.35, 0.02)) * 100), 0, 100)
    : 0

  return {
    epoch: record._epoch,
    timestamp: record.captured_at,
    spot,
    sessionDate: record._sessionDate,
    open,
    latestPrice,
    spotReturn15m: move15,
    spotReturn30m: move30,
    dayRange,
    flowImbalance,
    totalFlow,
    volumeOiScore,
    ivAtm: ivCurrent,
    ivRankScore,
    ivPercentileScore,
    rvCurrent,
    ivDelta15mPts,
    skewDelta15m,
    putWingDelta15mPts,
    callWingDelta15mPts,
    pinningScore,
    expansionScore,
    dealerPainScore,
    volIgnitionScore,
    surfaceMotionScore,
    surfaceMotionDelta,
    surfaceDistortionScore,
    directionalFlowScore,
    volatilityFlowScore,
    optionsLedScore,
    futuresLedScore,
    putProtectionDemandScore,
    callOverwritingScore,
    riskReversalBullishScore,
    transitionPressureScore,
    balancedScore,
    volCrushScore,
    skewStressScore,
    skewClosingScore,
    putWingStressScore,
    callWingStressScore,
    lowRealizedVolScore,
    rvExpansionScore,
    ivCompressionScore,
    ivExpansionScore,
    callBiasScore,
    putBiasScore,
    futureAggressionScore,
    meanReversionScore,
    trendEfficiencyScore: clamp(trendEff30 * 100, 0, 100),
    trendEfficiency15Score: clamp(trendEff15 * 100, 0, 100),
    upMoveScore,
    downMoveScore,
    upMove30Score: move30Scores.up,
    downMove30Score: move30Scores.down,
    expiryDominatedScore,
    vannaPressureScore,
    charmPressureScore,
    gexPositiveScore,
    gexNegativeScore,
    dexPositiveScore,
    dexNegativeScore,
    vrpRichScore,
    vrpTightScore,
    structure,
  }
}

function makeEntry(label, score, weight, note) {
  return { label, score: clamp(score ?? 0, 0, 100), weight, note }
}

function profileScore(key, features) {
  const profile = PROFILE_MAP[key]
  if (!profile) return 0
  const currentProfile = {
    pinning: features.pinningScore,
    expansion: features.expansionScore,
    skewStress: Math.max(features.skewStressScore, features.putWingStressScore),
    callChase: Math.max(features.callBiasScore, features.callWingStressScore),
    volIgnition: features.volIgnitionScore,
    dealerPain: features.dealerPainScore,
    flow: features.directionalFlowScore,
    futureAggression: features.futureAggressionScore,
    expiry: features.expiryDominatedScore,
    optionsLed: features.optionsLedScore,
    futuresLed: features.futuresLedScore,
    transition: features.transitionPressureScore,
    balanced: features.balancedScore,
  }
  const entries = Object.entries(profile).map(([metricKey, target]) => {
    const current = safeNumber(currentProfile[metricKey]) ?? 50
    return {
      score: clamp(100 - Math.abs(current - target), 0, 100),
      weight: 1,
    }
  })
  return weightedScore(entries)
}

function ruleEntriesForRegime(key, f) {
  switch (key) {
    case 'pinning_compression':
      return [
        makeEntry('GEX local positivo', f.structure.pinningComponents.localLongGammaScore || 0, 0.18, 'Gamma local absorvendo'),
        makeEntry('OI concentrado perto do spot', f.structure.pinningComponents.oiConcentrationScore || 0, 0.16, 'Cluster perto do spot'),
        makeEntry('Spot perto do magneto', f.structure.pinningComponents.strikeMagnetScore || 0, 0.14, 'Preço orbitando o strike dominante'),
        makeEntry('IV estável ou caindo', f.ivCompressionScore, 0.16, 'Superfície sem expansão relevante'),
        makeEntry('RV abaixo da IV', f.lowRealizedVolScore, 0.14, 'Realized comportada'),
        makeEntry('Pinning maior que expansion', clamp(50 + (f.pinningScore - f.expansionScore), 0, 100), 0.12, 'Compressão ainda domina'),
        makeEntry('Futuro sem agressão persistente', clamp(100 - f.futureAggressionScore, 0, 100), 0.10, 'Sem drive direcional limpo'),
      ]
    case 'long_gamma_mean_reversion':
      return [
        makeEntry('Livro em long gamma', Math.max(f.gexPositiveScore, f.structure.pinningComponents.localLongGammaScore || 0), 0.20, 'Absorção perto do spot'),
        makeEntry('Comportamento de reversão', f.meanReversionScore, 0.18, 'Preço volta ao centro'),
        makeEntry('Spot dentro do cluster', f.structure.pinningComponents.distanceInsideCluster || 0, 0.16, 'Faixa ainda segura'),
        makeEntry('IV comportada', f.ivCompressionScore, 0.12, 'Sem estresse na vol'),
        makeEntry('Trend efficiency baixa', clamp(100 - f.trendEfficiencyScore, 0, 100), 0.12, 'Movimento sem persistência'),
        makeEntry('Charm e vanna contidos', clamp(100 - Math.max(f.vannaPressureScore, f.charmPressureScore), 0, 100), 0.10, 'Secundários sem aceleração'),
        makeEntry('RV abaixo da IV', f.lowRealizedVolScore, 0.12, 'Fade ainda favorecido'),
      ]
    case 'short_gamma_expansion':
      return [
        makeEntry('GEX local negativo ou baixo', f.structure.expansionComponents.shortGammaOrLowGammaScore || 0, 0.18, 'Gamma não segura mais'),
        makeEntry('Spot fora do conforto do gamma', f.structure.gammaLevelBreakScore || 0, 0.16, 'Nível relevante rompido'),
        makeEntry('Expansion score alto', f.expansionScore, 0.16, 'Forças de expansão dominam'),
        makeEntry('RV acelerando', f.rvExpansionScore, 0.12, 'Realized ganhando tração'),
        makeEntry('IV subindo', f.ivExpansionScore, 0.12, 'Superfície reprecificando'),
        makeEntry('Futuro confirmando', f.futureAggressionScore, 0.14, 'Continuidade no futuro'),
        makeEntry('Dealer pain alto', f.dealerPainScore, 0.12, 'Hedge pode ficar reflexivo'),
      ]
    case 'downside_hedge_pressure':
      return [
        makeEntry('Compra de puts dominante', f.putBiasScore, 0.22, 'Fluxo puxa para proteção'),
        makeEntry('Skew abrindo', f.skewStressScore, 0.20, 'Proteção fica mais cara'),
        makeEntry('Put wing subindo', f.putWingStressScore, 0.18, 'Asa de baixa sendo reprecificada'),
        makeEntry('DEX mais negativo', f.dexNegativeScore, 0.12, 'Perfil delta piora'),
        makeEntry('Futuro vendendo', Math.max(f.futureAggressionScore * 0.75, f.downMoveScore), 0.14, 'Direção confirma downside'),
        makeEntry('Transmissão opções->preço', f.optionsLedScore, 0.14, 'Fluxo de opções liderando'),
      ]
    case 'upside_call_chase':
      return [
        makeEntry('Compra agressiva de calls', f.callBiasScore, 0.22, 'Fluxo direcional para upside'),
        makeEntry('Call wing subindo', f.callWingStressScore, 0.18, 'Asa de call reprecificando'),
        makeEntry('Spot rompendo resistência', Math.max(f.upMoveScore, f.upMove30Score), 0.14, 'Preço já andando'),
        makeEntry('DEX positivo', f.dexPositiveScore, 0.12, 'Delta puxa para cima'),
        makeEntry('Futuro comprando', f.futureAggressionScore, 0.14, 'Continuação acompanhada no futuro'),
        makeEntry('Pouca resistência acima', f.structure.airPocketScore || 0, 0.10, 'Menos travas acima do spot'),
        makeEntry('Expansion confirmada', f.expansionScore, 0.10, 'Breakout com continuidade'),
      ]
    case 'volatility_ignition':
      return [
        makeEntry('Vol ignition score', f.volIgnitionScore, 0.24, 'Aceleração conjunta de preço e vol'),
        makeEntry('Vol of vol subindo', f.surfaceMotionScore, 0.18, 'Instabilidade da superfície'),
        makeEntry('IV acelerando', f.ivExpansionScore, 0.16, 'ATM e asas expandindo'),
        makeEntry('Vega/vanna pressionando', f.vannaPressureScore, 0.10, 'Sensibilidade de vol aumentando'),
        makeEntry('RV acelerando', f.rvExpansionScore, 0.14, 'Realized valida o rompimento'),
        makeEntry('Break relevante', f.structure.gammaLevelBreakScore || 0, 0.18, 'Preço saindo da zona de compressão'),
      ]
    case 'volatility_crush':
      return [
        makeEntry('IV caindo', f.ivCompressionScore, 0.22, 'Vol sendo esmagada'),
        makeEntry('Vol of vol caindo', clamp(100 - f.surfaceMotionScore, 0, 100), 0.18, 'Superfície estabilizando'),
        makeEntry('RV abaixo da IV', f.lowRealizedVolScore, 0.16, 'Prêmio continua gordo'),
        makeEntry('Skew fechando', f.skewClosingScore, 0.14, 'Proteção sendo desmontada'),
        makeEntry('Pinning alto', f.pinningScore, 0.16, 'Mercado contido'),
        makeEntry('Fluxo de venda de vol', f.volCrushScore, 0.14, 'Crush com absorção'),
      ]
    case 'put_protection_demand':
      return [
        makeEntry('Demanda por puts', f.putProtectionDemandScore, 0.22, 'Proteção em destaque'),
        makeEntry('Skew abrindo', f.skewStressScore, 0.18, 'Smile ficando mais defensivo'),
        makeEntry('Put wing distorcida', f.putWingStressScore, 0.18, 'Asa de baixa sob demanda'),
        makeEntry('IV geral subindo', f.ivExpansionScore, 0.14, 'Proteção puxa a vol'),
        makeEntry('Fluxo liderando o movimento', f.optionsLedScore, 0.14, 'Opções empurrando o regime'),
        makeEntry('DEX negativo', f.dexNegativeScore, 0.14, 'Delta confirma defesa'),
      ]
    case 'call_overwriting':
      return [
        makeEntry('Venda/cobertura de calls', f.callOverwritingScore, 0.22, 'Upside sendo ofertado'),
        makeEntry('Pinning alto', f.pinningScore, 0.18, 'Livro absorve perto do spot'),
        makeEntry('IV caindo', f.ivCompressionScore, 0.18, 'Vol comprimida'),
        makeEntry('RV baixa', f.lowRealizedVolScore, 0.14, 'Pouca necessidade de hedge'),
        makeEntry('Call wing comportada', clamp(100 - f.callWingStressScore, 0, 100), 0.12, 'Sem chase relevante'),
        makeEntry('Fluxo direcional limitado', clamp(100 - f.directionalFlowScore, 0, 100), 0.16, 'Sem corrida por upside'),
      ]
    case 'risk_reversal_bullish':
      return [
        makeEntry('Assimetria de call', f.riskReversalBullishScore, 0.24, 'Calls dominam a estrutura'),
        makeEntry('Skew fechando', f.skewClosingScore, 0.18, 'Proteção perdendo prêmio'),
        makeEntry('DEX positivo', f.dexPositiveScore, 0.16, 'Delta acompanha o upside'),
        makeEntry('Spot subindo', Math.max(f.upMoveScore, f.upMove30Score), 0.14, 'Preço valida o viés'),
        makeEntry('Call flow direcional', f.callBiasScore, 0.16, 'Upside procurado via opções'),
        makeEntry('Expansion controlada', f.expansionScore, 0.12, 'Sem virar pânico de vol'),
      ]
    case 'skew_panic':
      return [
        makeEntry('Put skew abrindo rápido', f.skewStressScore, 0.24, 'Assimetria piora rápido'),
        makeEntry('Put wing distorcida', f.putWingStressScore, 0.22, 'Asa de baixa explode'),
        makeEntry('IV das puts > ATM', Math.max(f.putWingStressScore, f.ivExpansionScore), 0.18, 'Proteção de cauda precificada'),
        makeEntry('Fluxo defensivo', f.putBiasScore, 0.16, 'Compra de puts sustentada'),
        makeEntry('Preço caindo ou hedge preventivo', Math.max(f.downMoveScore, f.putProtectionDemandScore), 0.20, 'Mercado paga caro por downside'),
      ]
    case 'dealer_pain_zone':
      return [
        makeEntry('Dealer pain score', f.dealerPainScore, 0.28, 'Zona estrutural sensível'),
        makeEntry('Spot perto do flip/neutral', Math.max(f.structure.flipProximityScore || 0, f.structure.pinningComponents.dexNeutralScore || 0), 0.16, 'Preço encostado em ponto crítico'),
        makeEntry('Hedge acceleration', f.structure.gammaLevelBreakScore || 0, 0.16, 'Hedge pode acelerar'),
        makeEntry('Liquidez estrutural fraca', f.structure.airPocketScore || 0, 0.12, 'Livro rarefeito'),
        makeEntry('Vanna/charm elevadas', Math.max(f.vannaPressureScore, f.charmPressureScore), 0.14, 'Secundários ampliam dor'),
        makeEntry('Futuro sem absorção clara', clamp(100 - f.volumeOiScore, 0, 100), 0.14, 'Menor conforto para hedge'),
      ]
    case 'expiry_dominated':
      return [
        makeEntry('Dias para expirar baixos', f.expiryDominatedScore, 0.26, 'Expiração domina o micro'),
        makeEntry('Pinning alto', f.pinningScore, 0.18, 'OI/grupo de strikes prende'),
        makeEntry('OI concentrado', f.structure.pinningComponents.oiConcentrationScore || 0, 0.18, 'Livro concentrado'),
        makeEntry('Fluxo modesto', clamp(100 - f.directionalFlowScore, 0, 100), 0.14, 'Pouca ruptura direcional'),
        makeEntry('IV sem stress', clamp(100 - f.ivExpansionScore, 0, 100), 0.12, 'Vol não ignita'),
        makeEntry('Dealer pain residual', clamp(100 - (f.dealerPainScore * 0.6), 0, 100), 0.12, 'Predomínio de vencimento sobre choque'),
      ]
    case 'futures_led_move':
      return [
        makeEntry('Agressão do futuro', f.futureAggressionScore, 0.28, 'Futuro puxa a direção'),
        makeEntry('Trend efficiency alta', f.trendEfficiencyScore, 0.18, 'Movimento limpo'),
        makeEntry('Fluxo de opções secundário', clamp(100 - f.optionsLedScore, 0, 100), 0.18, 'Opções não lideram'),
        makeEntry('Break estrutural', f.structure.gammaLevelBreakScore || 0, 0.16, 'Preço saiu da compressão'),
        makeEntry('Directional flow menos dominante', clamp(100 - (f.directionalFlowScore * 0.6), 0, 100), 0.10, 'Futuro vem antes'),
        makeEntry('Expansion moderada/alta', f.expansionScore, 0.10, 'Continuidade direcional'),
      ]
    case 'options_led_move':
      return [
        makeEntry('Fluxo direcional de opções', f.directionalFlowScore, 0.24, 'Fluxo já faz preço'),
        makeEntry('Volatility flow', f.volatilityFlowScore, 0.20, 'Vol acompanha o fluxo'),
        makeEntry('Surface distortion', f.surfaceDistortionScore, 0.16, 'Superfície se move junto'),
        makeEntry('Options-led score', f.optionsLedScore, 0.20, 'Opções dominando a leitura'),
        makeEntry('Futuro atrás do fluxo', clamp(100 - (f.futuresLedScore * 0.5), 0, 100), 0.08, 'Futuro menos dominante'),
        makeEntry('Expansion confirmada', f.expansionScore, 0.12, 'Movimento se transmite ao preço'),
      ]
    case 'balanced_no_clear_edge':
      return [
        makeEntry('Gap baixo entre pinning e expansion', clamp(100 - Math.abs(f.pinningScore - f.expansionScore), 0, 100), 0.28, 'Placar próximo'),
        makeEntry('Sem ignição de vol', clamp(100 - f.volIgnitionScore, 0, 100), 0.16, 'Vol não destrava'),
        makeEntry('Fluxo misto', clamp(100 - f.directionalFlowScore, 0, 100), 0.16, 'Sem dominância clara'),
        makeEntry('Dealer pain contida', clamp(100 - f.dealerPainScore, 0, 100), 0.14, 'Estrutura sem dor extrema'),
        makeEntry('Futuro sem drive limpo', clamp(100 - f.futureAggressionScore, 0, 100), 0.12, 'Sem trend day claro'),
        makeEntry('Balanced score', f.balancedScore, 0.14, 'Mercado neutro'),
      ]
    case 'transition_regime':
      return [
        makeEntry('Pinning e expansion altos', Math.min(f.pinningScore, f.expansionScore), 0.22, 'Coexistência de forças'),
        makeEntry('Transição estrutural', f.transitionPressureScore, 0.22, 'Placar perto e instável'),
        makeEntry('Vol of vol subindo', f.surfaceMotionScore, 0.14, 'Superfície perde estabilidade'),
        makeEntry('Break gamma parcial', f.structure.gammaLevelBreakScore || 0, 0.14, 'Estrutura saindo do eixo'),
        makeEntry('Fluxo começando a tomar conta', f.directionalFlowScore, 0.14, 'Mudança em curso'),
        makeEntry('Dealer pain aumenta', f.dealerPainScore, 0.14, 'Risco de mudança reflexiva'),
      ]
    default:
      return []
  }
}

function evaluateRegimes(features) {
  const scores = Object.keys(REGIME_META).map(key => {
    const entries = ruleEntriesForRegime(key, features)
    const ruleScore = weightedScore(entries)
    const statScore = profileScore(key, features)
    return {
      key,
      ruleScore,
      statScore,
      finalScore: (ruleScore * 0.70) + (statScore * 0.30),
      entries,
      meta: REGIME_META[key],
    }
  }).sort((left, right) => right.finalScore - left.finalScore)

  const withProbabilities = softmax(scores.map(item => ({
    ...item,
    value: item.finalScore / 12,
  }))).sort((left, right) => right.probability - left.probability)

  return withProbabilities
}

function confidenceLabel(value) {
  if (value >= 80) return 'convicção alta'
  if (value >= 65) return 'convicção boa'
  if (value >= 50) return 'convicção média'
  return 'convicção frágil'
}

function regimeFamily(key) {
  if (['pinning_compression', 'long_gamma_mean_reversion', 'call_overwriting', 'volatility_crush', 'expiry_dominated'].includes(key)) return 'pinning'
  if (['short_gamma_expansion', 'upside_call_chase', 'downside_hedge_pressure', 'volatility_ignition', 'options_led_move', 'futures_led_move'].includes(key)) return 'expansion'
  if (key === 'transition_regime') return 'transition'
  if (['put_protection_demand', 'skew_panic', 'dealer_pain_zone'].includes(key)) return 'stress'
  return 'neutral'
}

function regimeGuide(key) {
  return REGIME_GUIDE[key] || {
    description: 'Regime sem biblioteca dedicada ainda.',
    nextMove: 'Sem transição típica mapeada.',
  }
}

function buildSubRegime(scores) {
  const secondary = scores.find(item => !['balanced_no_clear_edge', 'transition_regime'].includes(item.key))
  if (!secondary) return {
    label: 'Sem subtese dominante',
    short: 'sem viés',
    note: 'estruturas seguem neutras',
  }
  const probability = safeNumber(secondary.probability) || 0
  const baseLabel = secondary.meta?.label || secondary.key
  if (secondary.key === 'put_protection_demand' || secondary.key === 'downside_hedge_pressure' || secondary.key === 'skew_panic') {
    return {
      label: probability >= 45 ? 'Put Protection relevante' : 'Put Protection moderada',
      short: 'proteção',
      note: 'skew e downside puxando a microestrutura',
    }
  }
  if (secondary.key === 'upside_call_chase' || secondary.key === 'risk_reversal_bullish') {
    return {
      label: probability >= 45 ? 'Upside pursuit relevante' : 'Upside pursuit moderada',
      short: 'upside',
      note: 'calls e upside tentando dominar',
    }
  }
  if (secondary.key === 'call_overwriting') {
    return { label: 'Venda de call moderada', short: 'overwrite', note: 'upside ofertado pela estrutura' }
  }
  if (secondary.key === 'volatility_ignition' || secondary.key === 'volatility_crush') {
    return { label: baseLabel, short: 'vol', note: 'volatilidade define a micro leitura' }
  }
  return { label: baseLabel, short: 'mix', note: 'pressão secundária mais provável' }
}

function buildLevels(top, next, features, meta) {
  const family = regimeFamily(top.key)
  const pinBand = meta.pinningBand ?? {}
  const accelBand = meta.accelerationBand ?? {}
  const decompBand = meta.decompressionBand ?? {}
  const spot = features.spot
  const dominantMagnet = features.structure?.dominantMagnet?.strike ?? features.structure?.pinCenter ?? spot
  const upperWall = features.structure?.upperWall?.strike ?? safeNumber(accelBand.high ?? decompBand.high)
  const lowerWall = features.structure?.lowerWall?.strike ?? safeNumber(accelBand.low ?? decompBand.low)
  const upBias = (features.callBiasScore + features.upMove30Score) >= (features.putBiasScore + features.downMove30Score)
  const preferredDirection = upBias ? 1 : -1

  let confirmLevel = null
  let invalidateLevel = null
  let confirmText = ''
  let invalidateText = ''

  if (family === 'pinning') {
    confirmLevel = dominantMagnet
    invalidateLevel = preferredDirection > 0
      ? safeNumber(accelBand.high ?? decompBand.high ?? upperWall)
      : safeNumber(accelBand.low ?? decompBand.low ?? lowerWall)
    confirmText = `segura perto de ${formatLevel(confirmLevel)}`
    invalidateText = invalidateLevel != null
      ? `${preferredDirection > 0 ? 'acima' : 'abaixo'} de ${formatLevel(invalidateLevel)}`
      : '--'
  } else if (family === 'expansion' || family === 'stress' || family === 'transition') {
    confirmLevel = preferredDirection > 0
      ? safeNumber(accelBand.high ?? decompBand.high ?? upperWall)
      : safeNumber(accelBand.low ?? decompBand.low ?? lowerWall)
    invalidateLevel = dominantMagnet ?? safeNumber(pinBand[preferredDirection > 0 ? 'high' : 'low'])
    confirmText = confirmLevel != null
      ? `${preferredDirection > 0 ? 'acima' : 'abaixo'} de ${formatLevel(confirmLevel)}`
      : '--'
    invalidateText = invalidateLevel != null
      ? `volta para ${formatLevel(invalidateLevel)}`
      : '--'
  } else {
    confirmLevel = dominantMagnet
    invalidateLevel = next ? (preferredDirection > 0 ? upperWall : lowerWall) : dominantMagnet
    confirmText = confirmLevel != null ? `centro em ${formatLevel(confirmLevel)}` : '--'
    invalidateText = invalidateLevel != null ? `sai de ${formatLevel(invalidateLevel)}` : '--'
  }

  return {
    confirmLevel,
    invalidateLevel,
    confirmText,
    invalidateText,
    direction: preferredDirection,
  }
}

function buildSnapshotFromTimelinePoint(point, timeline) {
  if (!point) return null
  const top = point.scores[0]
  const second = point.scores[1]
  const topGuide = regimeGuide(top?.key)
  const secondGuide = regimeGuide(second?.key)
  const confidence = clamp((top.finalScore * 0.65) + ((safeNumber(top.probability) || 0) * 0.35), 0, 100)
  const gap = Math.max((top.finalScore || 0) - (second?.finalScore || 0), 0)
  const transitionRisk = clamp(((point.features.transitionPressureScore * 0.55) + ((100 - gap) * 0.45)), 0, 100)
  const subRegime = buildSubRegime(point.scores.filter(item => item.key !== top.key))
  const levels = buildLevels(top, second, point.features, point.meta)
  const family = regimeFamily(top.key)
  const nextLikely = second?.meta?.label || 'Sem sucessor claro'
  const explain = top.entries
    .slice()
    .sort((left, right) => ((right.score * right.weight) - (left.score * left.weight)))
    .slice(0, 5)
    .map((item, index) => ({
      rank: index + 1,
      label: item.label,
      score: item.score,
      note: item.note,
    }))

  const currentIndex = timeline.findIndex(item => item.epoch === point.epoch)
  const previous = currentIndex > 0 ? timeline[currentIndex - 1] : null
  const alerts = []
  if (previous && previous.regimeKey !== point.regimeKey) alerts.push('Mudança de regime')
  if (confidence >= 70) alerts.push(`Confiança ${Math.round(confidence)}%`)
  if (top.key === 'transition_regime') alerts.push('Regime entrou em transição')
  if (previous && regimeFamily(previous.regimeKey) !== family && previous.confidence >= 65) alerts.push('Regime anterior invalidado')
  if ((second?.probability || 0) > 60) alerts.push(`Próximo regime ${Math.round(second.probability)}%`)

  const probabilities = point.scores
    .filter(item => item.key !== top.key)
    .slice(0, 5)
    .map(item => ({
      key: item.key,
      label: item.meta?.label || item.key,
      probability: item.probability,
      tone: item.meta?.tone || 'neutral',
    }))

  const transitions = timeline
    .filter((item, index) => index === 0 || timeline[index - 1].regimeKey !== item.regimeKey)
    .slice(-6)
    .map(item => ({
      ...item,
      regimeLabel: REGIME_META[item.regimeKey]?.label || item.regimeKey,
      description: regimeGuide(item.regimeKey).description,
      label: item.axisLabel,
    }))

  return {
    regimeKey: top.key,
    regimeLabel: top.meta?.label || top.key,
    tone: top.meta?.tone || 'neutral',
    confidence,
    confidenceLabel: confidenceLabel(confidence),
    transitionRisk,
    transitionTone: transitionRisk >= 70 ? 'hot' : transitionRisk >= 50 ? 'warn' : '',
    subRegime: subRegime.label,
    subRegimeShort: subRegime.short,
    microReading: subRegime.note,
    marketReading: `${top.meta?.reading || 'Regime dominante'} com ${confidenceLabel(confidence)}; ${nextLikely.toLowerCase()} é a transição mais provável se ${levels.confirmText.replace(/^segura /, '')}.`,
    currentRegimeExplanation: topGuide.description,
    nextLikelyRegime: nextLikely,
    nextLikelyExplanation: second?.key
      ? `${secondGuide.description} ${secondGuide.nextMove}`
      : 'Ainda nao ha um regime sucessor com probabilidade suficiente para ser lido com confianca.',
    confirmLevel: levels.confirmLevel,
    invalidateLevel: levels.invalidateLevel,
    confirmText: levels.confirmText,
    invalidateText: levels.invalidateText,
    transitionHint: levels.confirmText,
    explanations: explain,
    signalBars: [
      { key: 'pinning', label: 'Pinning', score: point.features.pinningScore, tone: 'cool' },
      { key: 'expansion', label: 'Expansion', score: point.features.expansionScore, tone: 'hot' },
      { key: 'dealerPain', label: 'Dealer Pain', score: point.features.dealerPainScore, tone: 'warn' },
      { key: 'volIgnition', label: 'Vol Ignition', score: point.features.volIgnitionScore, tone: 'hot' },
      { key: 'surfaceDistortion', label: 'Surface Distortion', score: point.features.surfaceDistortionScore, tone: 'warn' },
      { key: 'directionalFlow', label: 'Directional Flow', score: point.features.directionalFlowScore, tone: 'warm' },
      { key: 'volatilityFlow', label: 'Volatility Flow', score: point.features.volatilityFlowScore, tone: 'warm' },
      { key: 'optionsLed', label: 'Options-Led', score: point.features.optionsLedScore, tone: 'warm' },
      { key: 'futuresLed', label: 'Futures-Led', score: point.features.futuresLedScore, tone: 'cool' },
    ],
    signalScores: {
      pinning: point.features.pinningScore,
      expansion: point.features.expansionScore,
      dealerPain: point.features.dealerPainScore,
      volIgnition: point.features.volIgnitionScore,
    },
    pinningLabel: point.features.pinningScore >= point.features.expansionScore ? 'compressão dominante' : 'pinning secundário',
    expansionLabel: point.features.expansionScore > point.features.pinningScore ? 'rompimento ganhando' : 'expansão ainda contida',
    dealerPainLabel: point.features.dealerPainScore >= 70 ? 'zona sensível' : 'dor sob controle',
    volIgnitionLabel: point.features.volIgnitionScore >= 70 ? 'risco de trend day' : 'sem ignição plena',
    nextProbabilities: probabilities,
    recentTransitions: transitions,
    alerts,
    spot: point.features.spot,
    sessionStamp: sessionStampText({ captured_at: point.timestamp }),
    features: point.features,
  }
}

function drawCenteredMessage(ctx, width, height, message) {
  ctx.save()
  ctx.fillStyle = '#6f8399'
  ctx.font = '10px monospace'
  ctx.textAlign = 'center'
  ctx.fillText(message, width / 2, height / 2)
  ctx.restore()
}

const analytics = computed(() => {
  const records = sessionHistory.value
  const meta = structureMeta.value
  if (records.length < 8 || !meta.rows.length) return null

  const dailyIvValues = dailyHistory.value
    .slice(-20)
    .map(item => safeNumber(item.iv_atm))
    .filter(value => value != null)

  const openPrice = safeNumber(records[0]?._price)
  const surfacePack = {
    five: buildWindowScoreSeries(records, WINDOW_5, intradayMinuteHistory.value),
    fifteen: buildWindowScoreSeries(records, WINDOW_15, intradayMinuteHistory.value),
  }
  const fifteenAligned = surfacePack.fifteen.scoreSeries.map((item, innerIndex) => ({
    ...item,
    _epoch: records[innerIndex]?._epoch,
  }))
  const flowWindows = buildFlowWindowSnapshots(records, sessionFlow.value, openPrice)

  const timeline = []
  for (let index = 0; index < records.length; index += 1) {
    const record = records[index]
    const dailyIvPercentile = percentileRank(dailyIvValues, safeNumber(record?.iv_atm))
    const features = buildFeaturePoint(
      records,
      index,
      { ...surfacePack, fifteenAligned },
      meta,
      flowWindows[index],
      openPrice,
      dailyIvPercentile,
    )
    if (!features) continue
    const scores = evaluateRegimes(features)
    const top = scores[0]
    const second = scores[1]
    const gap = Math.max((top?.finalScore || 0) - (second?.finalScore || 0), 0)
    const transitionRisk = clamp(((features.transitionPressureScore * 0.55) + ((100 - gap) * 0.45)), 0, 100)
    const stamp = new Date(record?._epoch || 0)
    timeline.push({
      epoch: record?._epoch,
      timestamp: record?.captured_at,
      sessionDate: record?._sessionDate || latestSessionDate.value,
      axisLabel: Number.isNaN(stamp.getTime())
        ? (latestSessionDate.value || 'today')
        : stamp.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }),
      regimeKey: top?.key || 'balanced_no_clear_edge',
      regimeLabel: top?.meta?.label || top?.key || 'Balanced / No Clear Edge',
      regimeDescription: regimeGuide(top?.key).description,
      confidence: clamp((top?.finalScore || 0) * 0.65 + ((safeNumber(top?.probability) || 0) * 0.35), 0, 100),
      transitionRisk,
      nextLikelyKey: second?.key || null,
      nextLikelyLabel: second?.meta?.label || 'Sem sucessor claro',
      features,
      scores,
      meta,
    })
  }

  const latest = timeline[timeline.length - 1]
  if (!latest) return null
  const snapshot = buildSnapshotFromTimelinePoint(latest, timeline)
  if (!snapshot) return null

  return {
    snapshot,
    timeline,
  }
})

const snapshot = computed(() => analytics.value?.snapshot || null)
const timelineSeries = computed(() => analytics.value?.timeline || [])
const timelineHoverPoint = computed(() => {
  const index = timelineHoverIndex.value
  if (index == null) return null
  return timelineSeries.value[index] || null
})
const displayTimelinePoint = computed(() => timelineHoverPoint.value || timelineSeries.value[timelineSeries.value.length - 1] || null)
const timelineLegendItems = computed(() => {
  const seen = new Set()
  return timelineSeries.value
    .map(item => item?.regimeKey)
    .filter(key => {
      if (!key || seen.has(key)) return false
      seen.add(key)
      return true
    })
    .map(key => ({
      key,
      label: REGIME_META[key]?.label || key,
      color: REGIME_COLORS[key] || '#64748b',
    }))
})
const timelineTooltip = computed(() => timelineHoverPoint.value)
const timelineTooltipStyle = computed(() => {
  const point = timelineHoverPoint.value
  const metrics = timelineMetrics.value
  if (!point || !metrics) return {}
  const x = metrics.xPositions?.[timelineHoverIndex.value] ?? metrics.plotX
  const tooltipWidth = 220
  const left = clamp(x - (tooltipWidth / 2), 8, Math.max(metrics.width - tooltipWidth - 8, 8))
  const top = Math.max(metrics.plotY + 4, 6)
  return {
    left: `${left}px`,
    top: `${top}px`,
  }
})

const timelineLabel = computed(() => {
  const sessionDate = latestSessionDate.value
  const count = timelineSeries.value.length
  if (!sessionDate) return '1m / sem base'
  return `${sessionDate} / 1m / ${count} pontos`
})

function updateTimelineHover(clientX) {
  const wrap = timelineWrap.value
  const metrics = timelineMetrics.value
  const data = timelineSeries.value
  if (!wrap || !metrics || data.length <= 1) return
  const rect = wrap.getBoundingClientRect()
  const localX = clientX - rect.left
  const rawIndex = Math.round(((localX - metrics.plotX) / Math.max(metrics.plotW, 1)) * (data.length - 1))
  timelineHoverIndex.value = clamp(rawIndex, 0, data.length - 1)
}

function handleTimelineEnter(event) {
  updateTimelineHover(event.clientX)
}

function handleTimelineMove(event) {
  updateTimelineHover(event.clientX)
}

function handleTimelineLeave() {
  timelineHoverIndex.value = null
}

function drawTimeline() {
  const canvas = timelineCanvas.value
  const wrap = timelineWrap.value
  const data = timelineSeries.value
  if (!canvas || !wrap) return

  const width = Math.max(wrap.clientWidth || 0, 320)
  const height = Math.max(wrap.clientHeight || 0, TIMELINE_HEIGHT)
  const dpr = window.devicePixelRatio || 1

  canvas.width = width * dpr
  canvas.height = height * dpr
  canvas.style.width = `${width}px`
  canvas.style.height = `${height}px`

  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, width, height)

  ctx.fillStyle = '#07111a'
  ctx.fillRect(0, 0, width, height)

  if (data.length < 2) {
    timelineMetrics.value = null
    drawCenteredMessage(ctx, width, height, 'waiting for intraday regime history')
    return
  }

  const plotX = TIMELINE_PAD.left
  const plotY = TIMELINE_PAD.top
  const plotW = Math.max(width - TIMELINE_PAD.left - TIMELINE_PAD.right, 10)
  const plotH = Math.max(height - TIMELINE_PAD.top - TIMELINE_PAD.bottom, 12)
  const bandH = Math.min(22, plotH * 0.42)
  const lineTop = plotY + bandH + 12
  const lineH = plotH - bandH - 12

  const xOf = index => {
    if (data.length <= 1) return plotX
    return plotX + ((index / (data.length - 1)) * plotW)
  }
  const yOfConfidence = value => lineTop + ((1 - clamp(value, 0, 100) / 100) * Math.max(lineH, 1))
  const xPositions = data.map((_, index) => xOf(index))

  ctx.strokeStyle = '#142334'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(plotX, lineTop + (lineH / 2))
  ctx.lineTo(plotX + plotW, lineTop + (lineH / 2))
  ctx.stroke()

  const blockWidth = Math.max(plotW / data.length, 1)
  data.forEach((item, index) => {
    const x = xPositions[index]
    const color = REGIME_COLORS[item.regimeKey] || '#64748b'
    ctx.fillStyle = color
    ctx.fillRect(x, plotY, blockWidth + 1, bandH)
    if (index > 0 && data[index - 1].regimeKey !== item.regimeKey) {
      ctx.fillStyle = 'rgba(248, 250, 252, 0.9)'
      ctx.fillRect(x - 1, plotY - 2, 2, bandH + 4)
    }
  })

  ctx.beginPath()
  ctx.lineWidth = 1.6
  ctx.strokeStyle = '#f8fafc'
  data.forEach((item, index) => {
    const x = xPositions[index]
    const y = yOfConfidence(item.confidence)
    if (index === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  })
  ctx.stroke()

  const hoverPoint = timelineHoverPoint.value
  if (hoverPoint) {
    const hoverIndex = timelineHoverIndex.value ?? data.length - 1
    const hoverX = xPositions[hoverIndex]
    const hoverY = yOfConfidence(hoverPoint.confidence)
    ctx.save()
    ctx.strokeStyle = 'rgba(248, 250, 252, 0.35)'
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(hoverX, plotY - 2)
    ctx.lineTo(hoverX, lineTop + lineH + 2)
    ctx.stroke()
    ctx.fillStyle = '#f8fafc'
    ctx.beginPath()
    ctx.arc(hoverX, hoverY, 3, 0, Math.PI * 2)
    ctx.fill()
    ctx.restore()
  }

  ctx.fillStyle = '#9fb3c8'
  ctx.font = '10px monospace'
  ctx.textAlign = 'left'
  ctx.fillText(data[0]?.axisLabel || '--', plotX, height - 8)
  ctx.textAlign = 'right'
  ctx.fillText(data[data.length - 1]?.axisLabel || '--', plotX + plotW, height - 8)

  ctx.textAlign = 'left'
  ctx.fillStyle = '#f8fafc'
  ctx.fillText('100%', plotX, lineTop + 8)
  ctx.fillStyle = '#5f7387'
  ctx.fillText('0%', plotX, lineTop + lineH)

  timelineMetrics.value = {
    width,
    height,
    plotX,
    plotY,
    plotW,
    plotH,
    bandH,
    lineTop,
    lineH,
    xPositions,
  }
}

async function load({ force = false } = {}) {
  const now = Date.now()
  if (!force && now - lastLoadAt < MIN_FETCH_INTERVAL_MS) return
  loading.value = true
  error.value = null
  try {
    let hasAnyData = false

    const [volResponse, flowResponse] = await Promise.allSettled([
      withLocalTimeout(
        getVolIndexHistory({
          underlying: underlying.value,
          days: 20,
          intraday_days: 2,
        }),
        'vol history',
      ),
      getVolumeActivity({
        underlying_security: underlying.value,
        limit: 1500,
        lookback_days: 1,
      }),
    ])

    if (volResponse.status === 'fulfilled') {
      const payload = volResponse.value?.data || {}
      dailyHistory.value = (payload.daily_history || payload.history || []).map(normalizeVolRecord)
      intradayHistory.value = (payload.intraday_history || []).map(normalizeVolRecord)
      hasAnyData = dailyHistory.value.length > 0 || intradayHistory.value.length > 0
    } else {
      const ivResponse = await withLocalTimeout(
        getVolumeIvHistory({
          underlying_security: underlying.value,
          limit: 1800,
          lookback_days: 1,
        }),
        'volume iv history',
        10_000,
      ).catch(() => null)
      const fallbackHistory = (ivResponse?.data?.history || []).map(normalizeVolRecord)
      if (fallbackHistory.length) {
        intradayHistory.value = fallbackHistory
        dailyHistory.value = buildDailyHistoryFromIntraday(fallbackHistory)
        hasAnyData = true
      }
    }

    if (flowResponse.status === 'fulfilled') {
      const payload = flowResponse.value?.data
      const rows = Array.isArray(payload) ? payload : Array.isArray(payload?.rows) ? payload.rows : []
      flowEvents.value = rows.map(normalizeFlowEvent)
      hasAnyData = hasAnyData || flowEvents.value.length > 0
    }

    if (!hasAnyData && volResponse.status !== 'fulfilled' && flowResponse.status !== 'fulfilled') {
      throw new Error('Failed to load option regime history')
    }

    lastLoadAt = Date.now()
    await nextTick()
    drawTimeline()
  } catch (err) {
    error.value = err?.response?.data?.error || err?.message || 'Failed to load option regime inputs'
  } finally {
    loading.value = false
  }
}

async function reload() {
  await load({ force: true })
}

watch(() => props.underlyingSecurity, async (next, previous) => {
  if (!next || next === previous) return
  await load({ force: true })
})

watch(() => props.refreshNonce, async (next, previous) => {
  if (!next || next === previous) return
  await load()
})

watch(timelineSeries, async () => {
  await nextTick()
  drawTimeline()
})

watch(timelineHoverIndex, async () => {
  await nextTick()
  drawTimeline()
})

onMounted(async () => {
  await load({ force: true })
  refreshTimer = setInterval(load, AUTO_REFRESH_MS)
})

onUnmounted(() => {
  clearInterval(refreshTimer)
})
</script>

<style scoped>
.orc-root {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  background: #08111a;
  color: #dbe7f3;
  font-family: monospace;
  overflow: auto;
}

.orc-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-bottom: 1px solid #162235;
}

.orc-title {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #fbbf24;
}

.orc-controls {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}

.orc-underlying {
  padding: 3px 7px;
  border: 1px solid #243243;
  border-radius: 999px;
  font-size: 11px;
  color: #9fb3c8;
}

.orc-btn {
  border: 1px solid #26425f;
  background: #0d1a27;
  color: #dbe7f3;
  border-radius: 8px;
  padding: 4px 8px;
  cursor: pointer;
  font: inherit;
}

.orc-btn.loading {
  opacity: 0.7;
  cursor: default;
}

.orc-empty,
.orc-empty-inline {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 140px;
  color: #7b91a8;
  padding: 16px;
  text-align: center;
}

.orc-top-grid {
  display: grid;
  grid-template-columns: minmax(320px, 1.15fr) minmax(380px, 1fr);
  gap: 12px;
  padding: 12px;
}

.orc-hero-card,
.orc-panel,
.orc-timeline-panel {
  border: 1px solid #172635;
  background: linear-gradient(180deg, rgba(10, 19, 29, 0.98), rgba(7, 14, 22, 0.98));
  border-radius: 14px;
  box-shadow: 0 0 0 1px rgba(14, 21, 31, 0.45) inset;
}

.orc-hero-card {
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.orc-hero-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.orc-badge {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 5px 10px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  border: 1px solid #304255;
  background: #112132;
  color: #dbe7f3;
}

.orc-badge.cool {
  color: #86efac;
  border-color: rgba(34, 197, 94, 0.32);
  background: rgba(20, 83, 45, 0.18);
}

.orc-badge.hot {
  color: #fda4af;
  border-color: rgba(244, 63, 94, 0.34);
  background: rgba(127, 29, 29, 0.18);
}

.orc-badge.warm {
  color: #fdba74;
  border-color: rgba(249, 115, 22, 0.34);
  background: rgba(124, 45, 18, 0.18);
}

.orc-badge.warn {
  color: #c4b5fd;
  border-color: rgba(168, 85, 247, 0.34);
  background: rgba(76, 29, 149, 0.18);
}

.orc-badge.neutral {
  color: #cbd5e1;
}

.orc-confidence {
  margin-left: auto;
  font-size: 26px;
  font-weight: 700;
  color: #f8fafc;
}

.orc-subregime {
  font-size: 18px;
  font-weight: 700;
  color: #f8fafc;
}

.orc-reading {
  font-size: 12px;
  line-height: 1.55;
  color: #b7c7d8;
}

.orc-current-explain {
  font-size: 11px;
  line-height: 1.5;
  color: #96acc1;
}

.orc-next-card {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid rgba(251, 191, 36, 0.16);
  background: rgba(251, 191, 36, 0.05);
  border-radius: 12px;
}

.orc-next-label {
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #fbbf24;
}

.orc-next-title {
  font-size: 13px;
  font-weight: 700;
  color: #f8fafc;
}

.orc-next-reading {
  font-size: 11px;
  line-height: 1.5;
  color: #c7d6e5;
}

.orc-hero-meta {
  display: grid;
  gap: 6px;
  padding-top: 4px;
  font-size: 11px;
  color: #8ea3b8;
}

.orc-kpi-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.orc-kpi {
  border: 1px solid #172635;
  background: #0a141f;
  border-radius: 12px;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.orc-kpi-label,
.orc-panel-sub,
.orc-kpi-sub,
.orc-line-key,
.orc-footer-note,
.orc-explain-note,
.orc-transition-time {
  color: #7c92a9;
}

.orc-kpi-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.07em;
}

.orc-kpi-value {
  font-size: 20px;
  font-weight: 700;
  color: #f8fafc;
}

.orc-kpi-value.hot {
  color: #fb7185;
}

.orc-kpi-value.warn {
  color: #fdba74;
}

.orc-kpi-text {
  font-size: 14px;
}

.orc-alerts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 12px 12px;
}

.orc-alert-pill {
  padding: 5px 9px;
  border-radius: 999px;
  font-size: 10px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #f8fafc;
  background: rgba(239, 68, 68, 0.14);
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.orc-main-grid,
.orc-bottom-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  padding: 0 12px 12px;
}

.orc-panel,
.orc-timeline-panel {
  padding: 12px;
}

.orc-panel-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.orc-hover-panel {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.orc-hover-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #7c92a9;
}

.orc-hover-chip {
  display: inline-flex;
  align-items: center;
  padding: 3px 7px;
  border-radius: 999px;
  border: 1px solid #213042;
  background: #0c1721;
  color: #dbe7f3;
  font-size: 10px;
}

.orc-panel-title {
  font-size: 12px;
  font-weight: 700;
  color: #f8fafc;
  letter-spacing: 0.03em;
}

.orc-panel-sub {
  font-size: 10px;
}

.orc-explain-list,
.orc-prob-list,
.orc-transition-list {
  display: grid;
  gap: 8px;
}

.orc-explain-row,
.orc-transition-row {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 10px;
  align-items: center;
  border: 1px solid #132130;
  background: rgba(9, 17, 25, 0.7);
  border-radius: 10px;
  padding: 8px 10px;
}

.orc-explain-rank {
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: rgba(251, 191, 36, 0.16);
  color: #fcd34d;
  font-size: 11px;
  font-weight: 700;
}

.orc-explain-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.orc-transition-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.orc-explain-label,
.orc-transition-regime,
.orc-prob-name,
.orc-signal-name {
  color: #d8e3ee;
}

.orc-transition-note {
  font-size: 10px;
  line-height: 1.45;
  color: #8ea3b8;
}

.orc-explain-score,
.orc-transition-confidence,
.orc-prob-value,
.orc-signal-score {
  color: #f8fafc;
  font-weight: 700;
}

.orc-signal-row,
.orc-prob-row {
  display: grid;
  grid-template-columns: minmax(112px, 1fr) minmax(120px, 2fr) auto;
  gap: 10px;
  align-items: center;
}

.orc-signal-track,
.orc-prob-track {
  position: relative;
  overflow: hidden;
  height: 10px;
  border-radius: 999px;
  background: #0e1924;
  border: 1px solid #172635;
}

.orc-signal-fill,
.orc-prob-fill {
  height: 100%;
  border-radius: inherit;
}

.orc-signal-fill.cool,
.orc-prob-fill.cool {
  background: linear-gradient(90deg, #16a34a, #4ade80);
}

.orc-signal-fill.hot,
.orc-prob-fill.hot {
  background: linear-gradient(90deg, #ef4444, #fb7185);
}

.orc-signal-fill.warn,
.orc-prob-fill.warn {
  background: linear-gradient(90deg, #a855f7, #c4b5fd);
}

.orc-signal-fill.warm,
.orc-prob-fill.warm {
  background: linear-gradient(90deg, #f97316, #fdba74);
}

.orc-timeline-panel {
  margin: 0 12px 12px;
}

.orc-timeline-wrap {
  position: relative;
  width: 100%;
  min-height: 86px;
}

.orc-timeline-canvas {
  display: block;
  width: 100%;
  height: 86px;
}

.orc-timeline-footer {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  margin-top: 8px;
  font-size: 10px;
}

.orc-line-chip {
  display: inline-block;
  width: 12px;
  height: 3px;
  border-radius: 999px;
  margin-right: 5px;
  vertical-align: middle;
}

.orc-line-chip.conf {
  background: #f8fafc;
}

.orc-line-chip.trans {
  background: #fb923c;
}

.orc-line-chip.band {
  background: #64748b;
}

.orc-line-chip.regime {
  width: 12px;
  height: 8px;
}

.orc-timeline-label {
  margin-top: 6px;
}

.orc-tooltip {
  position: absolute;
  width: 220px;
  padding: 9px 10px;
  border-radius: 10px;
  border: 1px solid rgba(248, 250, 252, 0.12);
  background: rgba(7, 14, 22, 0.96);
  box-shadow: 0 12px 30px rgba(0, 0, 0, 0.28);
  pointer-events: none;
  z-index: 2;
}

.orc-tooltip-time,
.orc-tooltip-regime {
  color: #f8fafc;
}

.orc-tooltip-time {
  font-size: 10px;
}

.orc-tooltip-regime {
  font-size: 12px;
  font-weight: 700;
  margin-top: 2px;
}

.orc-tooltip-copy {
  font-size: 11px;
  line-height: 1.45;
  color: #c7d6e5;
  margin-top: 4px;
}

.orc-tooltip-meta {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 10px;
  color: #90a4b9;
  margin-top: 6px;
}

.orc-tooltip-next {
  font-size: 10px;
  color: #fbbf24;
  margin-top: 4px;
}

.orc-footer-note {
  padding: 0 12px 12px;
  font-size: 10px;
  line-height: 1.5;
}

@media (max-width: 1200px) {
  .orc-top-grid,
  .orc-main-grid,
  .orc-bottom-grid {
    grid-template-columns: 1fr;
  }

  .orc-kpi-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .orc-kpi-grid {
    grid-template-columns: 1fr;
  }

  .orc-signal-row,
  .orc-prob-row {
    grid-template-columns: 1fr;
  }

  .orc-transition-row,
  .orc-explain-row {
    grid-template-columns: 1fr;
  }
}
</style>

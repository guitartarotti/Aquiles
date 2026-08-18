<template>
  <div class="fvl-root">
    <div class="fvl-toolbar">
      <span class="fvl-badge" :class="sentimentTone">
        RPC {{ formatScore(latestRiskPressureScore) }}
        <em>{{ sentimentRegime }}</em>
      </span>
      <span class="fvl-pill">XB1 {{ formatPrice(latestRow?.close) }}</span>
      <span class="fvl-pill core">Core {{ formatPrice(latestRow?.fair_value_core) }}</span>
      <span class="fvl-pill shadow">Shadow {{ formatPrice(latestRow?.fair_value_shadow) }}</span>

      <div class="fvl-sep" />
      <label class="fvl-check"><input type="checkbox" v-model="showCore" /> Core</label>
      <label class="fvl-check"><input type="checkbox" v-model="showShadow" /> Shadow</label>
      <label class="fvl-check"><input type="checkbox" v-model="showLegs" /> Pernas</label>
      <label class="fvl-check"><input type="checkbox" v-model="showRange" /> Range</label>
      <label class="fvl-check"><input type="checkbox" v-model="showSentiment" /> RPC</label>

      <button class="fvl-btn" @click="showComposer = !showComposer">
        {{ showComposer ? 'Fechar composicao' : 'Composicao' }}
      </button>
      <button class="fvl-btn" @click="reload({ forceRefresh: true })">Atualizar</button>

      <div class="fvl-spacer" />
      <span class="fvl-meta" v-if="sessionLabel">{{ sessionLabel }}</span>
      <span class="fvl-loading" v-if="loading">Carregando...</span>
      <span class="fvl-error" v-if="errorMsg && !loading">{{ errorMsg }}</span>
    </div>

    <div class="fvl-composer" v-if="showComposer">
      <div
        v-for="leg in legConfig"
        :key="leg.key"
        class="fvl-leg-card"
        :class="leg.layer"
      >
        <div class="fvl-leg-head">
          <label class="fvl-leg-toggle">
            <input type="checkbox" v-model="leg.enabled" />
            <span>{{ leg.label }}</span>
          </label>
          <span class="fvl-layer">{{ leg.layer }}</span>
          <label class="fvl-plot">
            <input type="checkbox" v-model="leg.visible" />
            plotar
          </label>
          <label class="fvl-plot">
            <input type="checkbox" v-model="leg.bandVisible" :disabled="!leg.visible" />
            banda
          </label>
        </div>
        <div class="fvl-leg-actions">
          <button @click="selectLegAssets(leg, true)">todos</button>
          <button @click="selectLegAssets(leg, false)">zerar</button>
          <span>{{ selectedAssetCount(leg) }}/{{ leg.assets.length }} ativos</span>
        </div>
        <div class="fvl-assets">
          <label
            v-for="asset in leg.assets"
            :key="`${leg.key}-${asset.symbol}`"
            class="fvl-asset"
            :class="{ off: !asset.selected }"
          >
            <input type="checkbox" v-model="asset.selected" />
            <span class="fvl-asset-symbol">{{ asset.symbol }}</span>
            <span class="fvl-asset-beta">{{ formatBeta(asset.stats?.effective_beta) }}</span>
          </label>
        </div>
      </div>
    </div>

    <div class="fvl-chart-wrap" ref="wrapEl">
      <div ref="chartEl" class="fvl-chart" />
      <div class="fvl-empty" v-if="!loading && !chartRows.length">
        {{ errorMsg || 'Sem candles validos para montar o fair value.' }}
      </div>
    </div>

    <div class="fvl-footer">
      <span>{{ methodologyText }}</span>
      <span v-if="latestGapText">{{ latestGapText }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  init,
  dispose,
  CandleType,
  LineType,
  YAxisPosition,
  YAxisType,
  TooltipShowRule,
  TooltipShowType,
  CandleTooltipRectPosition,
  registerIndicator,
} from '@/vendor/equicharts/equicharts.esm.js'
import { getFairValueLegsChartPanel, getFairValueLegsLatestPoint } from '@/api/macro.js'

const props = defineProps({
  modelData: { type: Object, default: null },
  refreshNonce: { type: Number, default: 0 },
})

const FAIR_VALUE_REQUEST_TIMEOUT_MS = 75_000
const FAIR_VALUE_HOT_REFRESH_MS = 2_500
const FAIR_VALUE_HOT_TIMEOUT_MS = 6_000
const FAIR_VALUE_NONCE_THROTTLE_MS = 45_000
const FAIR_VALUE_SNAPSHOT_FOLLOW_UP_MS = 6_000
const FAIR_VALUE_CACHE_KEY = 'discovery:fair-value-legs:latest:v5'
const CANDLE_PANE_ID = 'candle_pane'
const LEG_SERIES = [
  { key: 'credit', figureKey: 'credit', valueKey: 'legCredit', upperKey: 'legCreditUpper', lowerKey: 'legCreditLower', title: 'Credit', color: '#f59e0b' },
  { key: 'equity_foreign', figureKey: 'equityForeign', valueKey: 'legEquityForeign', upperKey: 'legEquityForeignUpper', lowerKey: 'legEquityForeignLower', title: 'Eq Ext', color: '#22c55e' },
  { key: 'equity_local', figureKey: 'equityLocal', valueKey: 'legEquityLocal', upperKey: 'legEquityLocalUpper', lowerKey: 'legEquityLocalLower', title: 'Eq Loc', color: '#10b981' },
  { key: 'di', figureKey: 'di', valueKey: 'legDi', upperKey: 'legDiUpper', lowerKey: 'legDiLower', title: 'DIs', color: '#c084fc' },
  { key: 'commodities', figureKey: 'commodities', valueKey: 'legCommodities', upperKey: 'legCommoditiesUpper', lowerKey: 'legCommoditiesLower', title: 'Comdty', color: '#eab308' },
  { key: 'fx', figureKey: 'fx', valueKey: 'legFx', upperKey: 'legFxUpper', lowerKey: 'legFxLower', title: 'FX', color: '#60a5fa' },
  { key: 'funding', figureKey: 'funding', valueKey: 'legFunding', upperKey: 'legFundingUpper', lowerKey: 'legFundingLower', title: 'Funding', color: '#a78bfa' },
  { key: 'risk', figureKey: 'risk', valueKey: 'legRisk', upperKey: 'legRiskUpper', lowerKey: 'legRiskLower', title: 'Risk', color: '#fb7185' },
  { key: 'sentiment', figureKey: 'sentiment', valueKey: 'legSentiment', upperKey: 'legSentimentUpper', lowerKey: 'legSentimentLower', title: 'Sent', color: '#14b8a6' },
]

function priceLineStyle(color) {
  return { color, size: 1.25, style: LineType.Solid, dashedValue: [2, 2], smooth: false }
}

function bandLineStyle(color) {
  return { color, size: 0.9, style: LineType.Dashed, dashedValue: [3, 5], smooth: false }
}

const PRICE_LINE_STYLES = [
  { color: '#38bdf8', size: 2.2, style: LineType.Solid, dashedValue: [2, 2], smooth: false },
  { color: 'rgba(56,189,248,0.34)', size: 1, style: LineType.Dashed, dashedValue: [4, 4] },
  { color: 'rgba(56,189,248,0.34)', size: 1, style: LineType.Dashed, dashedValue: [4, 4] },
  { color: '#f472b6', size: 1.8, style: LineType.Dashed, dashedValue: [6, 4] },
  ...LEG_SERIES.flatMap(leg => [
    priceLineStyle(leg.color),
    bandLineStyle(leg.color),
    bandLineStyle(leg.color),
  ]),
]
const SENTIMENT_LINE_STYLES = [
  { color: '#f8fafc', size: 1.8, style: LineType.Solid, dashedValue: [2, 2], smooth: false },
  { color: 'rgba(20,184,166,0.78)', size: 1.35, style: LineType.Dashed, dashedValue: [6, 4], smooth: false },
  { color: 'rgba(148,163,184,0.42)', size: 1, style: LineType.Dashed, dashedValue: [5, 5] },
]

const loading = ref(false)
const errorMsg = ref('')
const payload = ref(null)
const legConfig = ref([])
const customComposition = ref(false)
const showComposer = ref(false)
const showCore = ref(true)
const showShadow = ref(true)
const showLegs = ref(true)
const showRange = ref(true)
const showSentiment = ref(true)

const wrapEl = ref(null)
const chartEl = ref(null)
let chart = null
let resizeObserver = null
let reloadTimer = null
let compositionTimer = null
let reloadPromise = null
let hotReloadPromise = null
let snapshotFollowUpTimer = null
let hydrating = false
let lastReloadStartedAt = 0
let queuedForceReload = false

const chartRows = computed(() => payload.value?.chart_rows || [])
const latestRow = computed(() => payload.value?.latest || chartRows.value[chartRows.value.length - 1] || null)
const latestRiskPressureScore = computed(() => latestRow.value?.rpc_pressure_score ?? latestRow.value?.sentiment_score)
const sessionLabel = computed(() => {
  const sessions = payload.value?.sessions || []
  if (!sessions.length) return ''
  const first = sessions[0]?.date
  const last = sessions[sessions.length - 1]?.date
  return `${sessions.length} sessoes validas: ${first} a ${last} - 5min`
})
const sentimentTone = computed(() => {
  const score = Number(latestRiskPressureScore.value)
  if (!Number.isFinite(score)) return 'neutral'
  if (score >= 20) return 'positive'
  if (score <= -20) return 'negative'
  return 'neutral'
})
const sentimentRegime = computed(() => latestRow.value?.rpc_regime || latestRow.value?.sentiment_regime || 'Neutral')
const latestGapText = computed(() => {
  const row = latestRow.value
  const close = Number(row?.close)
  const core = Number(row?.fair_value_core)
  if (!Number.isFinite(close) || !Number.isFinite(core)) return ''
  const gap = core - close
  return `Gap Core vs XB1: ${gap >= 0 ? '+' : ''}${gap.toFixed(0)} pts`
})
const methodologyText = computed(() => {
  const text = payload.value?.methodology?.risk_pressure_composite
  return text || 'RPC = positivo indica suporte/risk-on; negativo indica pressao/risk-off, com componentes normalizados por regime e peso adaptativo.'
})
const compositionSignature = computed(() => JSON.stringify(legConfig.value.map(leg => ({
  key: leg.key,
  enabled: Boolean(leg.enabled),
  assets: (leg.assets || [])
    .filter(asset => asset.selected)
    .map(asset => asset.symbol),
}))))
const displaySignature = computed(() => JSON.stringify(legConfig.value.map(leg => ({
  key: leg.key,
  visible: Boolean(leg.visible),
  bandVisible: Boolean(leg.bandVisible),
}))))

function isPlausibleFairValueRow(row) {
  const close = Number(row?.close)
  if (!Number.isFinite(close) || close <= 0) return true
  const limit = close * 0.35
  for (const key of ['fair_value_core', 'fair_value_shadow']) {
    const value = Number(row?.[key])
    if (Number.isFinite(value) && Math.abs(value - close) > limit) return false
  }
  return true
}

function sanitizeFairValuePayload(sourcePayload) {
  if (!sourcePayload || !Array.isArray(sourcePayload.chart_rows)) return sourcePayload
  const rows = sourcePayload.chart_rows.filter(isPlausibleFairValueRow)
  if (rows.length === sourcePayload.chart_rows.length) return sourcePayload
  return {
    ...sourcePayload,
    chart_rows: rows,
    latest: rows[rows.length - 1] || null,
  }
}

function withLocalTimeout(promise, label, timeoutMs = FAIR_VALUE_REQUEST_TIMEOUT_MS) {
  let timerId = null
  const timeoutPromise = new Promise((_, reject) => {
    timerId = setTimeout(() => {
      reject(new Error(`${label} timed out after ${timeoutMs}ms`))
    }, timeoutMs)
  })
  return Promise.race([promise, timeoutPromise]).finally(() => {
    if (timerId) clearTimeout(timerId)
  })
}

const chartData = computed(() => chartRows.value.map(row => {
  const visibleLeg = key => {
    const leg = legConfig.value.find(item => item.key === key)
    return Boolean(showLegs.value && leg?.enabled && leg?.visible)
  }
  const visibleLegBand = key => {
    const leg = legConfig.value.find(item => item.key === key)
    return Boolean(showLegs.value && leg?.enabled && leg?.visible && leg?.bandVisible)
  }
  const item = {
    timestamp: row.timestamp_ms,
    open: row.open,
    high: row.high,
    low: row.low,
    close: row.close,
    volume: row.volume || 0,
    fvCore: showCore.value ? row.fair_value_core : null,
    fvCoreUpper: showCore.value && showRange.value ? row.fair_value_core_upper : null,
    fvCoreLower: showCore.value && showRange.value ? row.fair_value_core_lower : null,
    fvShadow: showShadow.value ? row.fair_value_shadow : null,
    sentimentScore: showSentiment.value ? (row.rpc_pressure_score ?? row.sentiment_score) : null,
    sentimentScoreV1: showSentiment.value ? row.rpc_v1_pressure_score : null,
    sentimentZero: showSentiment.value ? 0 : null,
  }
  for (const leg of LEG_SERIES) {
    item[leg.valueKey] = visibleLeg(leg.key) ? row[`leg_${leg.key}`] : null
    item[leg.upperKey] = visibleLegBand(leg.key) ? row[`leg_${leg.key}_upper`] : null
    item[leg.lowerKey] = visibleLegBand(leg.key) ? row[`leg_${leg.key}_lower`] : null
  }
  return item
}))

function finite(value) {
  if (value === null || value === undefined || value === '') return undefined
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : undefined
}

let indicatorsRegistered = false
function ensureIndicators() {
  if (indicatorsRegistered) return
  registerIndicator({
    name: 'FV_PRICE_LINES',
    shortName: 'FV Legs',
    series: 'price',
    precision: 2,
    shouldOhlc: false,
    figures: [
      { key: 'core', title: 'Core: ', type: 'line' },
      { key: 'upper', title: 'Core +: ', type: 'line' },
      { key: 'lower', title: 'Core -: ', type: 'line' },
      { key: 'shadow', title: 'Shadow: ', type: 'line' },
      ...LEG_SERIES.flatMap(leg => [
        { key: leg.figureKey, title: `${leg.title}: `, type: 'line' },
        { key: `${leg.figureKey}Upper`, title: `${leg.title} +: `, type: 'line' },
        { key: `${leg.figureKey}Lower`, title: `${leg.title} -: `, type: 'line' },
      ]),
    ],
    calc: data => data.map(item => {
      const row = {
        core: finite(item.fvCore),
        upper: finite(item.fvCoreUpper),
        lower: finite(item.fvCoreLower),
        shadow: finite(item.fvShadow),
      }
      for (const leg of LEG_SERIES) {
        row[leg.figureKey] = finite(item[leg.valueKey])
        row[`${leg.figureKey}Upper`] = finite(item[leg.upperKey])
        row[`${leg.figureKey}Lower`] = finite(item[leg.lowerKey])
      }
      return row
    }),
  })
  registerIndicator({
    name: 'FV_SENTIMENT',
    shortName: 'RPC',
    precision: 1,
    minValue: -100,
    maxValue: 100,
    figures: [
      { key: 'score', title: 'RPC v2: ', type: 'line' },
      { key: 'scoreV1', title: 'RPC v1: ', type: 'line' },
      { key: 'zero', title: 'Zero: ', type: 'line' },
    ],
    calc: data => data.map(item => ({
      score: finite(item.sentimentScore),
      scoreV1: finite(item.sentimentScoreV1),
      zero: finite(item.sentimentZero),
    })),
  })
  indicatorsRegistered = true
}

function buildVolContext() {
  const ctx = props.modelData?.market_context || {}
  const summary = props.modelData?.summary || {}
  return {
    implied_vol: ctx.implied_vol || ctx.atm_implied_vol || summary.implied_vol || summary.atm_implied_vol || null,
    vol_of_vol_daily_pct: summary.vol_of_vol_daily_pct || ctx.vol_of_vol_daily_pct || null,
  }
}

function buildRequestConfig() {
  const legs = {}
  for (const leg of legConfig.value) {
    legs[leg.key] = {
      enabled: Boolean(leg.enabled),
      assets: (leg.assets || [])
        .filter(asset => asset.selected)
        .map(asset => asset.symbol),
    }
  }
  return { legs }
}

function buildRequestPayload(forceRefresh = false) {
  const hasComposition = customComposition.value && legConfig.value.length > 0
  return {
    sessions: 3,
    bar_minutes: 5,
    session_start: '09:00',
    session_end: '18:30',
    rolling_window_points: 60,
    config: hasComposition ? buildRequestConfig() : {},
    vol_context: buildVolContext(),
    force_refresh: Boolean(forceRefresh),
  }
}

function sessionDateOf(row) {
  return String(row?.session_date || '').trim()
}

function payloadSessionRowCount(sourcePayload, sessionDate) {
  if (!sessionDate) return 0
  return (sourcePayload?.chart_rows || []).filter(row => sessionDateOf(row) === sessionDate).length
}

function payloadSessionMetadataHas(sourcePayload, sessionDate) {
  if (!sessionDate) return false
  return (sourcePayload?.sessions || []).some(item => (
    String(item?.date || item?.session_date || '').trim() === sessionDate
  ))
}

function hasOnlyHotSessionRow(sourcePayload) {
  const latestSession = sessionDateOf(sourcePayload?.latest)
  if (!latestSession) return false
  return (
    payloadSessionRowCount(sourcePayload, latestSession) <= 1
    && !payloadSessionMetadataHas(sourcePayload, latestSession)
  )
}

function hydrateLegConfig(nextLegs) {
  hydrating = true
  const previous = new Map(legConfig.value.map(leg => [leg.key, leg]))
  legConfig.value = (nextLegs || []).map(leg => {
    const old = previous.get(leg.key)
    const oldAssets = new Map((old?.assets || []).map(asset => [asset.symbol, asset]))
    return {
      key: leg.key,
      label: leg.label,
      layer: leg.layer,
      enabled: old ? Boolean(old.enabled) : Boolean(leg.enabled ?? true),
      visible: old ? Boolean(old.visible) : Boolean(leg.visible ?? leg.default_visible ?? true),
      bandVisible: old ? Boolean(old.bandVisible) : Boolean(leg.band_visible ?? leg.default_band_visible ?? false),
      assets: (leg.assets || []).map(asset => {
        const oldAsset = oldAssets.get(asset.symbol)
        return {
          symbol: asset.symbol,
          selected: oldAsset ? Boolean(oldAsset.selected) : Boolean(asset.selected ?? true),
          stats: asset.stats || {},
        }
      }),
    }
  })
  nextTick(() => { hydrating = false })
}

function persistPayloadCache() {
  if (typeof window === 'undefined') return
  try {
    const cleanPayload = sanitizeFairValuePayload(payload.value)
    if (!cleanPayload?.chart_rows?.length) {
      window.localStorage.removeItem(FAIR_VALUE_CACHE_KEY)
      return
    }
    if (cleanPayload !== payload.value) payload.value = cleanPayload
    if (hasOnlyHotSessionRow(cleanPayload)) return
    window.localStorage.setItem(FAIR_VALUE_CACHE_KEY, JSON.stringify({
      savedAt: Date.now(),
      payload: cleanPayload,
    }))
  } catch {}
}

function restorePayloadCache() {
  if (typeof window === 'undefined') return false
  try {
    const raw = window.localStorage.getItem(FAIR_VALUE_CACHE_KEY)
    if (!raw) return false
    const parsed = JSON.parse(raw)
    const cachedPayload = parsed?.payload
    const savedAt = Number(parsed?.savedAt || 0)
    if (!cachedPayload || !Array.isArray(cachedPayload?.chart_rows) || !cachedPayload.chart_rows.length) return false
    const cleanPayload = sanitizeFairValuePayload(cachedPayload)
    if (!cleanPayload?.chart_rows?.length) {
      window.localStorage.removeItem(FAIR_VALUE_CACHE_KEY)
      return false
    }
    if (!Number.isFinite(savedAt) || (Date.now() - savedAt) > 24 * 60 * 60 * 1000) return false
    if (hasOnlyHotSessionRow(cleanPayload)) {
      window.localStorage.removeItem(FAIR_VALUE_CACHE_KEY)
      return false
    }
    payload.value = cleanPayload
    hydrateLegConfig(cleanPayload?.legs || [])
    return true
  } catch {
    return false
  }
}

function scheduleSnapshotFollowUp(nextPayload) {
  clearTimeout(snapshotFollowUpTimer)
  if (!nextPayload?.snapshot_refresh_pending) return
  snapshotFollowUpTimer = setTimeout(() => {
    reload({ background: true, forceRefresh: true })
  }, FAIR_VALUE_SNAPSHOT_FOLLOW_UP_MS)
}

async function reload({ background = false, forceRefresh = false } = {}) {
  if (reloadPromise) {
    if (forceRefresh) queuedForceReload = true
    return reloadPromise
  }
  reloadPromise = runReload({ background, forceRefresh }).finally(() => {
    reloadPromise = null
    if (queuedForceReload) {
      queuedForceReload = false
      reload({ background: true, forceRefresh: true })
    }
  })
  return reloadPromise
}

async function runReload({ background = false, forceRefresh = false } = {}) {
  if (!background) loading.value = true
  lastReloadStartedAt = Date.now()
  if (!background || !payload.value?.chart_rows?.length) {
    errorMsg.value = ''
  }
  try {
    const res = await withLocalTimeout(
      getFairValueLegsChartPanel(buildRequestPayload(forceRefresh)),
      'Fair value legs',
    )
    const nextPayload = res?.data || res
    payload.value = nextPayload
    persistPayloadCache()
    hydrateLegConfig(nextPayload?.legs || [])
    scheduleSnapshotFollowUp(nextPayload)
    await nextTick()
    refreshChartData({ reset: true, scrollToLatest: true })
    refreshLatestPoint()
  } catch (error) {
    if (payload.value?.chart_rows?.length) {
      errorMsg.value = 'Atualizacao lenta; mantendo ultimo snapshot'
    } else {
      errorMsg.value = error?.message || 'Erro ao carregar fair value'
    }
    console.error('[FairValueLegsWidget] load error', error)
  } finally {
    loading.value = false
  }
}

function applyLatestRow(nextRow, sourcePayload = {}) {
  if (!nextRow || !payload.value?.chart_rows?.length) return false
  const timestampMs = Number(nextRow.timestamp_ms)
  if (!Number.isFinite(timestampMs)) return false
  if (!isPlausibleFairValueRow(nextRow)) return false

  const currentPayload = sanitizeFairValuePayload(payload.value)
  const removedBadRows = currentPayload?.chart_rows?.length !== payload.value?.chart_rows?.length
  const rows = [...(currentPayload?.chart_rows || [])]
  const lastTimestamp = Number(rows[rows.length - 1]?.timestamp_ms || 0)
  if (lastTimestamp && timestampMs < lastTimestamp) return false
  const nextSession = sessionDateOf(nextRow)
  const lastSession = sessionDateOf(rows[rows.length - 1])
  const nextSessionCount = rows.filter(row => sessionDateOf(row) === nextSession).length
  if (nextSession && lastSession && nextSession !== lastSession && nextSessionCount <= 0) {
    scheduleSnapshotFollowUp({ snapshot_refresh_pending: true })
  }

  const existingIndex = rows.findIndex(row => Number(row?.timestamp_ms) === timestampMs)
  let reset = Boolean(removedBadRows)
  if (existingIndex >= 0) {
    if (existingIndex !== rows.length - 1) return false
    rows[existingIndex] = { ...rows[existingIndex], ...nextRow }
  } else {
    rows.push(nextRow)
  }
  rows.sort((left, right) => Number(left?.timestamp_ms || 0) - Number(right?.timestamp_ms || 0))
  payload.value = {
    ...currentPayload,
    chart_rows: rows,
    latest: rows[rows.length - 1],
    generated_at: sourcePayload.generated_at || payload.value.generated_at,
    live_overlay: true,
    live_source_timestamp: nextRow.live_source_timestamp || sourcePayload.live_source_timestamp || payload.value.live_source_timestamp,
  }
  refreshChartData({ reset, scrollToLatest: !reset })
  return true
}

async function refreshLatestPoint() {
  if (hotReloadPromise) return hotReloadPromise
  hotReloadPromise = runRefreshLatestPoint().finally(() => {
    hotReloadPromise = null
  })
  return hotReloadPromise
}

async function runRefreshLatestPoint() {
  if (!payload.value?.chart_rows?.length) return
  try {
    const res = await withLocalTimeout(
      getFairValueLegsLatestPoint(buildRequestPayload(false)),
      'Fair value latest',
      FAIR_VALUE_HOT_TIMEOUT_MS,
    )
    const nextPayload = res?.data || res
    if (Array.isArray(nextPayload?.chart_rows) && nextPayload.chart_rows.length) {
      payload.value = nextPayload
      hydrateLegConfig(nextPayload?.legs || [])
      await nextTick()
      refreshChartData({ reset: true, scrollToLatest: true })
      return
    }
    const nextRow = nextPayload?.latest
    if (nextRow) {
      applyLatestRow(nextRow, nextPayload)
      if (errorMsg.value === 'Atualizacao lenta; mantendo ultimo snapshot') {
        errorMsg.value = ''
      }
    }
  } catch (error) {
    console.debug('[FairValueLegsWidget] hot update skipped', error)
  }
}

function scheduleCompositionReload() {
  if (hydrating) return
  customComposition.value = true
  clearTimeout(compositionTimer)
  compositionTimer = setTimeout(() => {
    reload({ background: true })
  }, 550)
}

function mountChart() {
  destroyChart()
  if (!chartEl.value || !chartData.value.length) return
  ensureIndicators()
  chart = init(chartEl.value, {
    timezone: 'America/Sao_Paulo',
    yScrolling: false,
    styles: buildStyles(),
    layout: [
      { type: 'candle' },
      { type: 'xAxis', options: { position: 'bottom' } },
    ],
  })
  if (!chart) return
  chart.applyNewData(chartData.value, true)
  chart.createIndicator(
    { name: 'FV_PRICE_LINES', styles: { lines: PRICE_LINE_STYLES } },
    true,
    { id: CANDLE_PANE_ID },
  )
  chart.createIndicator(
    { name: 'FV_SENTIMENT', styles: { lines: SENTIMENT_LINE_STYLES } },
    false,
    { height: showSentiment.value ? 118 : 1 },
  )
  chart.scrollToRealTime()
  chart.resize()
}

function refreshChartData({ reset = false, scrollToLatest = false } = {}) {
  if (!chartData.value.length) {
    destroyChart()
    return
  }
  if (!chart) {
    mountChart()
    return
  }
  if (reset) {
    chart.clearData()
    chart.applyNewData(chartData.value, true)
  } else {
    const last = chartData.value[chartData.value.length - 1]
    if (last) chart.updateData(last)
  }
  if (scrollToLatest) chart.scrollToRealTime()
  chart.resize()
}

function destroyChart() {
  if (!chart) return
  try { dispose(chartEl.value) } catch {}
  chart = null
}

function buildStyles() {
  return {
    grid: {
      show: true,
      horizontal: { show: true, size: 1, color: 'rgba(148,163,184,0.10)', style: LineType.Dashed, dashedValue: [4, 6] },
      vertical: { show: true, size: 1, color: 'rgba(148,163,184,0.06)', style: LineType.Dashed, dashedValue: [4, 8] },
    },
    candle: {
      type: CandleType.CandleSolid,
      bar: {
        upColor: '#22c55e',
        downColor: '#ef4444',
        noChangeColor: '#94a3b8',
        upBorderColor: '#16a34a',
        downBorderColor: '#dc2626',
        noChangeBorderColor: '#64748b',
        upWickColor: '#16a34a',
        downWickColor: '#dc2626',
        noChangeWickColor: '#64748b',
      },
      priceMark: {
        show: true,
        high: { show: false },
        low: { show: false },
        last: {
          show: true,
          upColor: '#22c55e',
          downColor: '#ef4444',
          noChangeColor: '#94a3b8',
          line: { show: true, style: LineType.Dashed, dashedValue: [5, 6], size: 1 },
          text: {
            show: true,
            style: 'fill',
            size: 11,
            paddingLeft: 6,
            paddingTop: 4,
            paddingRight: 6,
            paddingBottom: 4,
            borderSize: 0,
            borderColor: 'transparent',
            borderRadius: 6,
            color: '#08111f',
            family: '"JetBrains Mono", monospace',
            weight: 'bold',
          },
        },
      },
      tooltip: {
        showRule: TooltipShowRule.FollowCross,
        showType: TooltipShowType.Standard,
        defaultValue: '--',
        custom: [
          { title: 'H', value: '{high}' },
          { title: 'O', value: '{open}' },
          { title: 'C', value: '{close}' },
          { title: 'L', value: '{low}' },
        ],
        rect: {
          position: CandleTooltipRectPosition.Fixed,
          paddingLeft: 6,
          paddingRight: 6,
          paddingTop: 6,
          paddingBottom: 6,
          offsetLeft: 6,
          offsetTop: 6,
          offsetRight: 6,
          offsetBottom: 6,
          borderRadius: 8,
          borderSize: 1,
          borderColor: 'rgba(148,163,184,0.24)',
          color: '#07111f',
        },
        text: {
          size: 11,
          family: '"JetBrains Mono", monospace',
          weight: 'normal',
          color: '#d7e6f5',
          marginLeft: 6,
          marginTop: 4,
          marginRight: 8,
          marginBottom: 4,
        },
        icons: [],
      },
    },
    indicator: {
      lines: PRICE_LINE_STYLES,
      lastValueMark: {
        show: true,
        text: {
          show: true,
          color: '#dbeafe',
          backgroundColor: '#08111f',
          size: 10,
          paddingLeft: 5,
          paddingRight: 5,
          paddingTop: 3,
          paddingBottom: 3,
          borderRadius: 4,
        },
      },
    },
    xAxis: {
      show: true,
      axisLine: { show: true, color: 'rgba(148,163,184,0.18)', size: 1 },
      tictView: { show: true, size: 1, length: 3, color: 'rgba(148,163,184,0.18)' },
      tickText: { show: true, color: '#8aa2b7', family: '"JetBrains Mono", monospace', weight: 'normal', size: 10, marginStart: 4, marginEnd: 4 },
    },
    yAxis: {
      show: true,
      position: YAxisPosition.Right,
      type: YAxisType.Normal,
      inside: false,
      reverse: false,
      axisLine: { show: true, color: 'rgba(148,163,184,0.18)', size: 1 },
      tictView: { show: true, size: 1, length: 2, color: 'rgba(148,163,184,0.18)' },
      tickText: { show: true, color: '#dbe7f3', family: '"JetBrains Mono", monospace', weight: 'normal', size: 10, marginStart: 4, marginEnd: 4 },
    },
    crosshair: {
      show: true,
      horizontal: {
        show: true,
        line: { show: true, style: LineType.Dashed, dashedValue: [4, 6], size: 1, color: 'rgba(226,232,240,0.28)' },
      },
      vertical: {
        show: true,
        line: { show: true, style: LineType.Dashed, dashedValue: [4, 6], size: 1, color: 'rgba(226,232,240,0.24)' },
      },
    },
  }
}

function selectLegAssets(leg, selected) {
  for (const asset of leg.assets || []) {
    asset.selected = selected
  }
}

function selectedAssetCount(leg) {
  return (leg.assets || []).filter(asset => asset.selected).length
}

function formatPrice(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return '--'
  return Math.round(parsed).toLocaleString('pt-BR')
}

function formatScore(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return '--'
  return `${parsed >= 0 ? '+' : ''}${parsed.toFixed(1)}`
}

function formatBeta(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return 'b --'
  return `b ${parsed >= 0 ? '+' : ''}${parsed.toFixed(2)}`
}

onMounted(async () => {
  await nextTick()
  const restored = restorePayloadCache()
  if (restored) {
    await nextTick()
    refreshChartData({ reset: true, scrollToLatest: true })
  }
  await reload({ background: restored })
  reloadTimer = setInterval(() => refreshLatestPoint(), FAIR_VALUE_HOT_REFRESH_MS)
  if (wrapEl.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => chart?.resize())
    resizeObserver.observe(wrapEl.value)
  }
})

onUnmounted(() => {
  clearInterval(reloadTimer)
  clearTimeout(compositionTimer)
  clearTimeout(snapshotFollowUpTimer)
  resizeObserver?.disconnect()
  destroyChart()
})

watch(compositionSignature, scheduleCompositionReload)
watch(displaySignature, () => {
  refreshChartData({ reset: true })
})
watch([showCore, showShadow, showLegs, showRange, showSentiment], () => {
  refreshChartData({ reset: true })
})
watch(() => props.refreshNonce, () => {
  if (!payload.value?.chart_rows?.length) {
    reload({ background: true })
    return
  }
  const elapsedSinceReload = Date.now() - (lastReloadStartedAt || 0)
  if (elapsedSinceReload < FAIR_VALUE_NONCE_THROTTLE_MS) {
    return
  }
  reload({ background: true })
})
</script>

<style scoped>
.fvl-root {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 7px;
  background: #06111e;
  color: #dbeafe;
}

.fvl-toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  flex-shrink: 0;
}

.fvl-badge,
.fvl-pill,
.fvl-btn,
.fvl-meta {
  font-family: "JetBrains Mono", monospace;
}

.fvl-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 800;
  border: 1px solid rgba(148, 163, 184, 0.18);
}

.fvl-badge em {
  font-style: normal;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.02em;
  opacity: 0.72;
}

.fvl-badge.positive {
  color: #4ade80;
  background: rgba(34, 197, 94, 0.12);
  border-color: rgba(34, 197, 94, 0.35);
}

.fvl-badge.negative {
  color: #fb7185;
  background: rgba(244, 63, 94, 0.12);
  border-color: rgba(244, 63, 94, 0.35);
}

.fvl-badge.neutral {
  color: #cbd5e1;
  background: rgba(148, 163, 184, 0.10);
}

.fvl-pill {
  font-size: 10px;
  color: #94a3b8;
  padding: 3px 7px;
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.72);
  border: 1px solid rgba(148, 163, 184, 0.10);
}

.fvl-pill.core { color: #38bdf8; }
.fvl-pill.shadow { color: #f472b6; }

.fvl-sep {
  width: 1px;
  height: 18px;
  background: rgba(255, 255, 255, 0.09);
}

.fvl-check,
.fvl-plot,
.fvl-leg-toggle,
.fvl-asset {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  user-select: none;
}

.fvl-check {
  font-size: 10px;
  color: #7f95aa;
}

.fvl-check input,
.fvl-plot input,
.fvl-leg-toggle input,
.fvl-asset input {
  accent-color: #38bdf8;
}

.fvl-btn {
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(15, 23, 42, 0.75);
  color: #cbd5e1;
  border-radius: 7px;
  padding: 4px 8px;
  font-size: 10px;
  cursor: pointer;
}

.fvl-btn:hover {
  border-color: rgba(56, 189, 248, 0.38);
  color: #e0f2fe;
}

.fvl-spacer { flex: 1; }
.fvl-meta { font-size: 10px; color: #64748b; }
.fvl-loading { font-size: 10px; color: #f59e0b; }
.fvl-error { font-size: 10px; color: #fb7185; }

.fvl-composer {
  flex-shrink: 0;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(245px, 1fr));
  gap: 8px;
  max-height: 255px;
  overflow: auto;
  padding: 8px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  background:
    radial-gradient(circle at top left, rgba(56, 189, 248, 0.10), transparent 28%),
    rgba(3, 7, 18, 0.58);
}

.fvl-leg-card {
  border-radius: 11px;
  padding: 8px;
  background: rgba(15, 23, 42, 0.72);
  border: 1px solid rgba(148, 163, 184, 0.11);
}

.fvl-leg-card.shadow {
  border-color: rgba(244, 114, 182, 0.22);
}

.fvl-leg-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.fvl-leg-toggle {
  font-size: 12px;
  font-weight: 800;
  color: #e2e8f0;
}

.fvl-layer {
  margin-left: auto;
  font-size: 9px;
  text-transform: uppercase;
  color: #64748b;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 999px;
  padding: 2px 6px;
}

.fvl-plot {
  font-size: 10px;
  color: #94a3b8;
}

.fvl-leg-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  color: #64748b;
  font-size: 10px;
}

.fvl-leg-actions button {
  border: 1px solid rgba(148, 163, 184, 0.14);
  background: rgba(2, 6, 23, 0.55);
  color: #94a3b8;
  border-radius: 6px;
  padding: 2px 6px;
  cursor: pointer;
}

.fvl-assets {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.fvl-asset {
  max-width: 100%;
  padding: 3px 6px;
  border-radius: 999px;
  background: rgba(2, 6, 23, 0.70);
  border: 1px solid rgba(148, 163, 184, 0.10);
  font-size: 10px;
  color: #cbd5e1;
}

.fvl-asset.off {
  opacity: 0.48;
}

.fvl-asset-symbol {
  max-width: 145px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fvl-asset-beta {
  color: #64748b;
  font-family: "JetBrains Mono", monospace;
}

.fvl-chart-wrap {
  flex: 1;
  min-height: 0;
  position: relative;
  border-radius: 14px;
  overflow: hidden;
  background:
    radial-gradient(circle at 18% 0%, rgba(20, 184, 166, 0.08), transparent 28%),
    radial-gradient(circle at 100% 0%, rgba(244, 114, 182, 0.08), transparent 24%),
    linear-gradient(180deg, #08111c 0%, #040c14 100%);
  border: 1px solid rgba(148, 163, 184, 0.11);
}

.fvl-chart {
  width: 100%;
  height: 100%;
}

.fvl-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #64748b;
  font-size: 12px;
  text-align: center;
  padding: 24px;
}

.fvl-footer {
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 10px;
  color: #64748b;
}

@media (max-width: 760px) {
  .fvl-toolbar {
    align-items: flex-start;
  }

  .fvl-spacer {
    display: none;
  }

  .fvl-composer {
    grid-template-columns: 1fr;
    max-height: 220px;
  }

  .fvl-footer {
    flex-direction: column;
  }
}
</style>

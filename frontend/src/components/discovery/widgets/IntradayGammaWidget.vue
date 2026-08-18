<template>
  <div class="igw-root">

    <!-- ── Controls ──────────────────────────────────────────────────────────── -->
    <div class="igw-controls">
      <!-- Gamma state badge -->
      <span class="igw-badge" :class="gammaPositive ? 'pos' : 'neg'">
        {{ gammaPositive ? 'Γ+' : 'Γ−' }}&nbsp;{{ gammaGexLabel }}
      </span>

      <div class="igw-sep" />

      <!-- Overlay toggles -->
      <label class="igw-chk"><input type="checkbox" v-model="showGamma"  /> Γ Níveis</label>
      <label class="igw-chk"><input type="checkbox" v-model="showZero"   /> Zero GEX</label>
      <label class="igw-chk"><input type="checkbox" v-model="showBand"   /> Pinning</label>
      <label class="igw-chk"><input type="checkbox" v-model="showFV"     /> Fair Value</label>

      <div class="igw-sep" />

      <!-- Fair value pill (live) -->
      <span v-if="fvPrice" class="igw-fv">
        FV {{ fmtStrike(fvPrice) }}
        <span :class="fvAbove ? 'fv-above' : 'fv-below'">
          {{ fvAbove ? '▲' : '▼' }} {{ Math.abs(fvMispricing).toFixed(0) }}pts
        </span>
      </span>

      <div style="margin-left:auto" />
      <span class="igw-live" :class="liveQuoteStale ? 'stale' : 'ok'" v-if="latestSpotPrice != null">
        XB1 {{ fmtStrike(latestSpotPrice) }} · {{ latestSpotTimeLabel }}
      </span>
      <span class="igw-info" v-if="!loading && bars.length">{{ bars.length }} barras · {{ CANDLE_TIMEFRAME_MINUTES }}min</span>
      <span class="igw-loading" v-if="loading">Carregando…</span>
      <span class="igw-error"  v-if="errorMsg && !loading">{{ errorMsg }}</span>
      <button class="igw-btn" @click="reload({ force: true })">↺</button>
    </div>

    <!-- ── Chart area ─────────────────────────────────────────────────────────── -->
    <div class="igw-wrap" ref="wrapEl">
      <div ref="chartEl" class="igw-chart" />
      <div class="igw-empty" v-if="!loading && !bars.length">
        {{ errorMsg || 'Sem dados de preço (Bloomberg screen capture necessário)' }}
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import {
  init, dispose,
  CandleType, LineType,
  YAxisPosition, YAxisType,
  TooltipShowRule, TooltipShowType, CandleTooltipRectPosition,
  registerOverlay, registerStyles
} from '@/vendor/equicharts/equicharts.esm.js'
import { getMarketScreenBenchmarkCandles, getLatestW32BasicaScreenCapture, getLatestW32BasicaSymbol } from '@/api/macro.js'

const props = defineProps({ modelData: { type: Object, default: null } })
const LIVE_PRICE_POLL_MS = 1_000
const LIVE_PRICE_TIMEOUT_MS = 4_500
const HISTORY_REQUEST_TIMEOUT_MS = 12_000
const HISTORY_LOOKBACK_MINUTES = 10_080
const HISTORY_MAX_CANDLES = 360
const CANDLE_TIMEFRAME_MINUTES = 5
const XB1_HISTORY_CACHE_KEY = 'discovery:intraday-gamma:xb1-history:v4'
const SESSION_TIMEZONE = 'America/Sao_Paulo'
const SESSION_START_MINUTES = 9 * 60
const SESSION_END_MINUTES = 18 * 60

// ─── UI state ──────────────────────────────────────────────────────────────────
const loading  = ref(false)
const errorMsg = ref('')
const bars     = ref([])   // resampled 30-min OHLCV
const latestSpotPrice = ref(null)
const latestSpotCapturedAt = ref(null)
const liveClock = ref(Date.now())

// ─── Overlay toggles ───────────────────────────────────────────────────────────
const showGamma = ref(true)
const showZero  = ref(true)
const showBand  = ref(true)
const showFV    = ref(true)

// ─── DOM refs ──────────────────────────────────────────────────────────────────
const wrapEl  = ref(null)
const chartEl = ref(null)
let chart = null
let historyReloadInFlight = false
let historyReadyForSession = false
let cachedSessionDate = ''
let lastLiveQuote = null

const sessionDateFormatter = new Intl.DateTimeFormat('en-CA', {
  timeZone: SESSION_TIMEZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
})

const sessionClockFormatter = new Intl.DateTimeFormat('en-GB', {
  timeZone: SESSION_TIMEZONE,
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

function withLocalTimeout(promise, label, timeoutMs = HISTORY_REQUEST_TIMEOUT_MS) {
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

function currentSessionDate() {
  return sessionDateFormatter.format(new Date())
}

function sessionDateForTimestamp(timestampMs) {
  return sessionDateFormatter.format(new Date(timestampMs))
}

function sessionMinutesForTimestamp(timestampMs) {
  const parts = sessionClockFormatter.formatToParts(new Date(timestampMs))
  const hour = Number(parts.find(part => part.type === 'hour')?.value || 0)
  const minute = Number(parts.find(part => part.type === 'minute')?.value || 0)
  return (hour * 60) + minute
}

function isWithinSessionWindow(timestampMs) {
  const minutes = sessionMinutesForTimestamp(timestampMs)
  return minutes >= SESSION_START_MINUTES && minutes <= SESSION_END_MINUTES
}

function filterBarsToHistory(nextBars) {
  return (Array.isArray(nextBars) ? nextBars : [])
    .filter((bar) => {
      const ts = Number(bar?.timestamp)
      if (!Number.isFinite(ts)) return false
      return isWithinSessionWindow(ts)
    })
    .sort((left, right) => Number(left.timestamp) - Number(right.timestamp))
    .slice(-HISTORY_MAX_CANDLES)
}

function ensureSessionState(sessionDate = currentSessionDate()) {
  if (cachedSessionDate && cachedSessionDate === sessionDate) return
  cachedSessionDate = sessionDate
  historyReadyForSession = false
  lastLiveCaptureAt = ''
  lastLiveQuote = null
  bars.value = []
  if (typeof window !== 'undefined') {
    try { window.localStorage.removeItem(XB1_HISTORY_CACHE_KEY) } catch {}
  }
}

// ─── Model data helpers ────────────────────────────────────────────────────────
const dealerInferenceRows = computed(() => props.modelData?.dealer_inference?.rows ?? [])
const pressure       = computed(() => props.modelData?.pressure ?? {})
const summary        = computed(() => props.modelData?.summary ?? {})

const gammaPositive = computed(() => (pressure.value?.current_point?.gex ?? 0) >= 0)
const gammaGexLabel = computed(() => {
  const g = pressure.value?.current_point?.gex
  return g != null && isFinite(g) ? fmtBig(g) : '—'
})

const fvPrice = computed(() => summary.value?.fair_value_final_future ?? null)
const fvAbove = computed(() => {
  const cur = summary.value?.current_future_price
  return fvPrice.value != null && cur != null ? cur > fvPrice.value : null
})
const fvMispricing = computed(() => {
  const cur = summary.value?.current_future_price
  return (cur != null && fvPrice.value != null) ? cur - fvPrice.value : 0
})
const futureBasisPoints = computed(() => {
  const basis = Number(summary.value?.future_basis_points)
  return Number.isFinite(basis) ? basis : 0
})
const latestSpotTimeLabel = computed(() => {
  const ts = latestSpotCapturedAt.value
  if (!Number.isFinite(ts)) return 'sem tick'
  return new Intl.DateTimeFormat('pt-BR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    timeZone: 'America/Sao_Paulo',
  }).format(new Date(ts))
})
const liveQuoteStale = computed(() => {
  const ts = latestSpotCapturedAt.value
  if (!Number.isFinite(ts)) return true
  return (liveClock.value - ts) > (LIVE_PRICE_POLL_MS * 3)
})

const dealerGammaRows = computed(() => [...dealerInferenceRows.value]
  .filter((row) => {
    const futureValue = Number(row?.dealer_inference_future_value)
    return Number.isFinite(futureValue) && futureValue > 0
  })
  .sort((a, b) => {
    const confidenceDiff = Number(b?.dealer_inference_confidence || 0) - Number(a?.dealer_inference_confidence || 0)
    if (Math.abs(confidenceDiff) > 1e-9) return confidenceDiff
    const shiftDiff = Math.abs(Number(b?.dealer_inference_shift || 0)) - Math.abs(Number(a?.dealer_inference_shift || 0))
    if (Math.abs(shiftDiff) > 1e-9) return shiftDiff
    const oiDiff = (Number(b?.oi_call || 0) + Number(b?.oi_put || 0)) - (Number(a?.oi_call || 0) + Number(a?.oi_put || 0))
    return oiDiff
  })
  .slice(0, 24))

const maxGammaOverlayMagnitude = computed(() => {
  const vals = dealerGammaRows.value
    .map((row) => Math.max(
      Math.abs(Number(row?.gamma_score || 0)),
      Math.abs(Number(row?.gex_score || 0)),
      Number(row?.dealer_inference_confidence || 0),
    ))
    .filter(Number.isFinite)
  return vals.length ? Math.max(...vals) : 1
})

// ─── Overlay text style helper ────────────────────────────────────────────────
// EquiCharts defaults overlay text to blue bg (#1677FF). We always override
// these fields so labels look clean against the dark chart background.
function mkText(color, bold = false) {
  return {
    color,
    size: 9,
    family: '"JetBrains Mono", monospace',
    weight: bold ? 'bold' : 'normal',
    // Kill the default blue background / border
    backgroundColor: 'rgba(4, 11, 20, 0.78)',
    borderColor:     color,
    borderSize:      1,
    borderRadius:    3,
    paddingLeft:     4,
    paddingRight:    4,
    paddingTop:      2,
    paddingBottom:   2,
  }
}

// ─── Register custom gammaLevel overlay (idempotent) ──────────────────────────
let _overlayRegistered = false
function ensureOverlay() {
  if (_overlayRegistered) return
  try {
    // Neutralise the global blue default for all overlay point markers
    registerStyles({ overlay: { point: { borderColor: 'transparent', color: 'transparent' } } })
  } catch {}
  try {
    registerOverlay({
      name: 'gammaLevel',
      totalStep: 2,
      needDefaultPointFigure: false,
      needDefaultXAxisFigure: false,
      needDefaultYAxisFigure: true,   // show price tick on Y-axis
      createPointFigures: ({ overlay, coordinates, bounding }) => {
        if (!coordinates?.length) return []
        const y = coordinates[0].y
        if (!isFinite(y)) return []
        const figs = [
          {
            type: 'line',
            ignoreEvent: true,
            attrs: { coordinates: [{ x: 0, y }, { x: bounding.width, y }] }
          }
        ]
        const lbl = overlay.extendData?.label
        if (lbl) {
          figs.push({
            type: 'text',
            ignoreEvent: true,
            attrs: { x: 6, y: y - 3, text: lbl, align: 'left', baseline: 'bottom' }
          })
        }
        return figs
      }
    })
    _overlayRegistered = true
  } catch {
    _overlayRegistered = true   // already registered
  }
}

// ─── Load intraday price data ──────────────────────────────────────────────────
async function reload({ background = false, force = false } = {}) {
  const sessionDate = currentSessionDate()
  ensureSessionState(sessionDate)
  if (!force && historyReadyForSession && bars.value.length) {
    return
  }
  if (historyReloadInFlight) return
  historyReloadInFlight = true
  if (!background) {
    loading.value = true
  }
  errorMsg.value = ''
  try {
    const res = await withLocalTimeout(
      getMarketScreenBenchmarkCandles({
        benchmark_symbol: 'XB1',
        symbol: 'XB1',
        lookback_minutes: HISTORY_LOOKBACK_MINUTES,
        max_points: HISTORY_MAX_CANDLES,
        bar_minutes: CANDLE_TIMEFRAME_MINUTES,
      }),
      'XB1 intraday history',
    )
    // axios wraps JSON: res.data = { ok, series, ... }  (no extra 'data' key here)
    const payload = res?.data ?? {}
    const rawCandles = payload?.series?.benchmark_candles ?? []
    const rawPts = payload?.series?.benchmark_points ?? []

    if (!rawCandles.length && !rawPts.length) {
      if (!bars.value.length) {
        errorMsg.value = 'Dados de preço indisponíveis'
        bars.value = []
      }
      return
    }

    const coldBars = rawCandles.length
      ? normalizeBackendCandles(rawCandles)
      : resampleToTimeframe(rawPts)
    bars.value = filterBarsToHistory(coldBars)
    historyReadyForSession = bars.value.length > 0
    persistBarsCache()
    if (lastLiveQuote) {
      applyLatestPriceToBars(lastLiveQuote)
    }
    await nextTick()
    refreshChartData({ reset: true, scrollToLatest: true })
  } catch (e) {
    if (!bars.value.length) {
      errorMsg.value = e?.message || 'Erro ao carregar'
    } else if (!background) {
      errorMsg.value = 'Historico XB1 lento; mantendo ultimo snapshot'
    }
    console.error('[IntradayGamma] load error', e)
  } finally {
    historyReloadInFlight = false
    if (!background) {
      loading.value = false
    }
  }
}

// ─── Resample raw price captures → 30-min OHLCV ───────────────────────────────
function normalizeBackendCandles(rawCandles) {
  return (Array.isArray(rawCandles) ? rawCandles : [])
    .map((bar) => {
      const ts = Number(bar?.timestamp_ms ?? Date.parse(bar?.timestamp))
      const open = Number(bar?.open)
      const high = Number(bar?.high)
      const low = Number(bar?.low)
      const close = Number(bar?.close ?? bar?.price)
      if (!Number.isFinite(ts) || !Number.isFinite(close)) return null
      const fallbackOpen = Number.isFinite(open) ? open : close
      return {
        timestamp: ts,
        open: fallbackOpen,
        high: Number.isFinite(high) ? high : Math.max(fallbackOpen, close),
        low: Number.isFinite(low) ? low : Math.min(fallbackOpen, close),
        close,
        volume: 0,
        turnover: 0,
        dailyChangePct: bar?.daily_change_pct ?? null,
      }
    })
    .filter(Boolean)
    .sort((a, b) => a.timestamp - b.timestamp)
}

function resampleToTimeframe(rawPts) {
  const buckets = new Map()
  for (const p of rawPts) {
    const ts = p.timestamp_ms ?? p.timestamp
    if (!ts) continue
    const price = p.close ?? p.price
    if (price == null || !isFinite(+price)) continue
    const key = toCandleBucket(+ts)
    const c = +price
    const o = +(p.open  ?? price)
    const h = +(p.high  ?? price)
    const l = +(p.low   ?? price)
    if (!buckets.has(key)) {
      buckets.set(key, {
        timestamp: key,
        open:  o, high: Math.max(h, c), low: Math.min(l, c),
        close: c, volume: 0, turnover: 0,
        dailyChangePct: p.daily_change_pct ?? null
      })
    } else {
      const b = buckets.get(key)
      b.high  = Math.max(b.high, h, c)
      b.low   = Math.min(b.low,  l, c)
      b.close = c
      if (p.daily_change_pct != null) b.dailyChangePct = p.daily_change_pct
    }
  }
  return [...buckets.values()].sort((a, b) => a.timestamp - b.timestamp)
}

function toCandleBucket(timestampMs) {
  const d = new Date(+timestampMs)
  const mins = Math.floor(d.getUTCMinutes() / CANDLE_TIMEFRAME_MINUTES) * CANDLE_TIMEFRAME_MINUTES
  return Date.UTC(
    d.getUTCFullYear(),
    d.getUTCMonth(),
    d.getUTCDate(),
    d.getUTCHours(),
    mins,
    0,
    0,
  )
}

function refreshChartData({ reset = false, scrollToLatest = false } = {}) {
  if (!bars.value.length) {
    destroyChart()
    return
  }
  if (!chart) {
    mountChart()
    return
  }
  if (reset) {
    chart.clearData()
    chart.applyNewData(bars.value, true)
    if (scrollToLatest) chart.scrollToRealTime()
    chart.resize()
    applyOverlays()
    return
  }
  const lastBar = bars.value[bars.value.length - 1]
  if (!lastBar) return
  chart.updateData(lastBar)
  if (scrollToLatest) chart.scrollToRealTime()
}

function persistBarsCache() {
  if (typeof window === 'undefined') return
  try {
    if (!bars.value.length) {
      window.localStorage.removeItem(XB1_HISTORY_CACHE_KEY)
      return
    }
    const sessionDate = cachedSessionDate || currentSessionDate()
    window.localStorage.setItem(XB1_HISTORY_CACHE_KEY, JSON.stringify({
      savedAt: Date.now(),
      sessionDate,
      historyReady: historyReadyForSession,
      bars: filterBarsToHistory(bars.value),
    }))
  } catch {}
}

function restoreBarsCache() {
  if (typeof window === 'undefined') return false
  try {
    const raw = window.localStorage.getItem(XB1_HISTORY_CACHE_KEY)
    if (!raw) return false
    const parsed = JSON.parse(raw)
    const cachedBars = Array.isArray(parsed?.bars) ? parsed.bars : []
    const savedAt = Number(parsed?.savedAt || 0)
    const sessionDate = String(parsed?.sessionDate || '')
    if (!cachedBars.length || !Number.isFinite(savedAt) || !sessionDate) return false
    if ((Date.now() - savedAt) > 18 * 60 * 60 * 1000) return false
    if (sessionDate !== currentSessionDate()) return false
    cachedSessionDate = sessionDate
    historyReadyForSession = Boolean(parsed?.historyReady)
    bars.value = filterBarsToHistory(cachedBars)
    if (!bars.value.length) return false
    return true
  } catch {
    return false
  }
}

function normalizeCaptureSymbol(row) {
  const raw = String(row?.symbol_normalized || row?.symbol || row?.symbol_raw || '')
  return raw.toUpperCase().replace(/[^A-Z0-9]/g, '')
}

function findLatestXb1Row(payload) {
  const rows = Array.isArray(payload?.rows) ? payload.rows : []
  return rows.find((row) => normalizeCaptureSymbol(row) === 'XB1') ?? null
}

async function fetchLatestW32Xb1() {
  const res = await withLocalTimeout(
    getLatestW32BasicaSymbol({ symbol: 'XB1' }),
    'XB1 W32 latest',
    LIVE_PRICE_TIMEOUT_MS,
  )
  const payload = res?.data ?? {}
  const capturedAt = String(payload?.captured_at || '')
  const price = Number(payload?.price)
  if (!capturedAt || !Number.isFinite(price)) {
    return null
  }
  return {
    capturedAt,
    price,
    dailyChangePct: payload?.daily_change_pct ?? null,
    signature: `${capturedAt}:${price}`,
    source: 'w32-symbol',
  }
}

function applyLatestPriceToBars({ capturedAt, price, dailyChangePct }) {
  const capturedTs = Date.parse(capturedAt)
  const numericPrice = Number(price)
  if (!Number.isFinite(capturedTs) || !Number.isFinite(numericPrice)) {
    return
  }
  const sessionDate = sessionDateForTimestamp(capturedTs)
  ensureSessionState(sessionDate)
  if (!isWithinSessionWindow(capturedTs)) {
    return
  }

  lastLiveQuote = {
    capturedAt,
    price: numericPrice,
    dailyChangePct: dailyChangePct ?? null,
  }

  latestSpotPrice.value = numericPrice
  latestSpotCapturedAt.value = capturedTs

  const bucket = toCandleBucket(capturedTs)
  const currentBars = bars.value
  if (!currentBars.length) {
    bars.value = [{
      timestamp: bucket,
      open: numericPrice,
      high: numericPrice,
      low: numericPrice,
      close: numericPrice,
      volume: 0,
      turnover: 0,
      dailyChangePct: dailyChangePct ?? null,
    }]
    persistBarsCache()
    refreshChartData({ reset: true, scrollToLatest: true })
    return
  }

  const lastIndex = currentBars.length - 1
  const lastBar = currentBars[lastIndex]
  if (!lastBar || bucket < Number(lastBar.timestamp)) {
    return
  }

  if (bucket === Number(lastBar.timestamp)) {
    const nextBar = {
      ...lastBar,
      high: Math.max(Number(lastBar.high ?? lastBar.close ?? numericPrice), numericPrice),
      low: Math.min(Number(lastBar.low ?? lastBar.close ?? numericPrice), numericPrice),
      close: numericPrice,
      dailyChangePct: dailyChangePct ?? lastBar.dailyChangePct ?? null,
    }
    bars.value.splice(lastIndex, 1, nextBar)
    persistBarsCache()
    refreshChartData()
    return
  }

  const open = Number(lastBar.close ?? lastBar.open ?? numericPrice)
  const nextBar = {
    timestamp: bucket,
    open,
    high: Math.max(open, numericPrice),
    low: Math.min(open, numericPrice),
    close: numericPrice,
    volume: 0,
    turnover: 0,
    dailyChangePct: dailyChangePct ?? null,
  }
  bars.value = [...currentBars, nextBar].slice(-HISTORY_MAX_CANDLES)
  persistBarsCache()
  refreshChartData({ scrollToLatest: true })
}

let liveTickInFlight = false
let lastLiveCaptureAt = ''

async function refreshLatestXb1Price() {
  if (liveTickInFlight) return
  liveTickInFlight = true
  try {
    let latestQuote = null
    try {
      latestQuote = await fetchLatestW32Xb1()
    } catch (error) {
      console.debug('[IntradayGamma] W32 symbol latest unavailable, falling back to latest capture', error)
    }

    if (!latestQuote) {
      const res = await withLocalTimeout(
        getLatestW32BasicaScreenCapture(),
        'W32 latest capture',
        LIVE_PRICE_TIMEOUT_MS,
      )
      const payload = res?.data ?? {}
      const capturedAt = String(payload?.captured_at || '')
      const row = findLatestXb1Row(payload)
      if (!capturedAt || !row) {
        return
      }
      latestQuote = {
        capturedAt,
        price: Number(row.price ?? row.last ?? 0),
        dailyChangePct: row.daily_change_pct,
        signature: `${capturedAt}:${Number(row.price ?? row.last ?? 0)}`,
        source: 'w32',
      }
    }

    if (!latestQuote?.capturedAt || !Number.isFinite(Number(latestQuote?.price))) {
      return
    }

    if (latestQuote.signature === lastLiveCaptureAt) {
      return
    }
    lastLiveCaptureAt = latestQuote.signature
    applyLatestPriceToBars({
      capturedAt: latestQuote.capturedAt,
      price: latestQuote.price,
      dailyChangePct: latestQuote.dailyChangePct,
    })
  } catch (e) {
    console.debug('[IntradayGamma] live XB1 refresh skipped', e)
  } finally {
    liveTickInFlight = false
  }
}

// ─── Chart mount / destroy ────────────────────────────────────────────────────
function destroyChart() {
  if (chart) { try { dispose(chartEl.value) } catch {} ; chart = null }
}

function mountChart() {
  destroyChart()
  if (!chartEl.value || !bars.value.length) return
  ensureOverlay()

  chart = init(chartEl.value, {
    timezone: 'America/Sao_Paulo',
    yScrolling: false,
    styles: buildStyles(),
    layout: [
      { type: 'candle' },
      { type: 'xAxis', options: { position: 'bottom' } }
    ]
  })
  if (!chart) return

  chart.applyNewData(bars.value, true)
  // Scroll to the most recent candle (end of trading session visible on right)
  chart.scrollToRealTime()
  chart.resize()

  applyOverlays()
}

// ─── Add / refresh all gamma overlays ────────────────────────────────────────
function applyOverlays() {
  if (!chart) return
  // Remove all previous overlays cleanly
  chart.removeOverlay()

  if (!bars.value.length) return
  // Use first bar's timestamp as anchor (overlay spans the whole chart)
  const anchor = bars.value[0].timestamp

  // ── 1. Strike gamma profiles ──────────────────────────────────────────────
  if (showGamma.value && dealerGammaRows.value.length) {
    for (const row of dealerGammaRows.value) {
      const inferenceFuture = Number(row.dealer_inference_future_value || 0)
      const gammaScore = Number(row.gamma_score || 0)
      const gexScore = Number(row.gex_score || 0)
      const confidence = Number(row.dealer_inference_confidence || 0)
      const oiTotal = Number(row.oi_call || 0) + Number(row.oi_put || 0)
      const magnitude = Math.max(Math.abs(gammaScore), Math.abs(gexScore), confidence)
      const isPos = gammaScore >= 0
      const norm = maxGammaOverlayMagnitude.value > 0
        ? Math.min(magnitude / maxGammaOverlayMagnitude.value, 1)
        : 0.5
      const alpha = 0.30 + norm * 0.60
      const size = 0.8 + norm * 1.6
      const color = isPos
        ? `rgba(34,197,94,${alpha.toFixed(2)})`
        : `rgba(239,68,68,${alpha.toFixed(2)})`
      const style = isPos ? 'solid' : 'dashed'
      const label = [
        `${isPos ? 'Γ+' : 'Γ−'} ${fmtStrike(inferenceFuture)}`,
        `K ${fmtStrike(row.strike)}`,
        fmtOI(oiTotal),
        `GEX ${fmtScore(gexScore)}`,
        `Γ ${fmtScore(gammaScore)}`,
      ].filter(Boolean).join('  ')

      chart.createOverlay({
        name: 'gammaLevel',
        lock: true,
        points: [{ value: inferenceFuture, timestamp: anchor }],
        styles: {
          line: { color, size, style, dashedValue: [4, 3] },
          text: mkText(color)
        },
        extendData: { label }
      })
    }
  }

  // ── 2. Zero GEX level ─────────────────────────────────────────────────────
  if (showZero.value && pressure.value.zero_pressure) {
    const zp = pressure.value.zero_pressure
    chart.createOverlay({
      name: 'gammaLevel',
      lock: true,
      points: [{ value: zp, timestamp: anchor }],
      styles: {
        line: { color: 'rgba(251,191,36,0.75)', size: 1.5, style: 'dashed', dashedValue: [6, 4] },
        text: mkText('rgba(251,191,36,0.90)', true)
      },
      extendData: { label: `Zero GEX  ${fmtStrike(zp)}` }
    })
  }

  // ── 3. Pinning band ───────────────────────────────────────────────────────
  if (showBand.value) {
    const band = { ...(pressure.value.pinning_band ?? {}) }
    if (band.low) band.low = Number(band.low) + futureBasisPoints.value
    if (band.high) band.high = Number(band.high) + futureBasisPoints.value
    if (band.low) {
      const projectedLow = Number(band.low)
      chart.createOverlay({
        name: 'gammaLevel', lock: true,
        points: [{ value: projectedLow, timestamp: anchor }],
        styles: {
          line: { color: 'rgba(251,146,60,0.55)', size: 1.0, style: 'dashed', dashedValue: [3, 3] },
          text: mkText('rgba(251,146,60,0.85)')
        },
        extendData: { label: `Pinning ↓  ${fmtStrike(band.low)}` }
      })
    }
    if (band.high) {
      const projectedHigh = Number(band.high)
      chart.createOverlay({
        name: 'gammaLevel', lock: true,
        points: [{ value: projectedHigh, timestamp: anchor }],
        styles: {
          line: { color: 'rgba(251,146,60,0.55)', size: 1.0, style: 'dashed', dashedValue: [3, 3] },
          text: mkText('rgba(251,146,60,0.85)')
        },
        extendData: { label: `Pinning ↑  ${fmtStrike(band.high)}` }
      })
    }
  }

  // ── 4. Fair Value (Inference) line ────────────────────────────────────────
  if (showFV.value && fvPrice.value) {
    const fv = fvPrice.value
    const mis = fvMispricing.value
    const dir = mis >= 0 ? '▲' : '▼'
    chart.createOverlay({
      name: 'gammaLevel', lock: true,
      points: [{ value: fv, timestamp: anchor }],
      styles: {
        line: { color: 'rgba(139,92,246,0.80)', size: 1.5, style: 'dashed', dashedValue: [5, 5] },
        text: mkText('rgba(167,139,250,0.95)')
      },
      extendData: { label: `Inferência FV  ${fmtStrike(fv)}  ${dir} ${Math.abs(mis).toFixed(0)}pts` }
    })
  }
}

// ─── Chart styles ─────────────────────────────────────────────────────────────
function buildStyles() {
  return {
    grid: {
      show: true,
      horizontal: { show: true, size: 1, color: 'rgba(148,163,184,0.10)', style: LineType.Dashed, dashedValue: [4, 6] },
      vertical:   { show: true, size: 1, color: 'rgba(148,163,184,0.06)', style: LineType.Dashed, dashedValue: [4, 8] }
    },
    candle: {
      type: CandleType.CandleSolid,
      bar: {
        upColor:            '#22c55e',
        downColor:          '#ef4444',
        noChangeColor:      '#94a3b8',
        upBorderColor:      '#16a34a',
        downBorderColor:    '#dc2626',
        noChangeBorderColor:'#64748b',
        upWickColor:        '#16a34a',
        downWickColor:      '#dc2626',
        noChangeWickColor:  '#64748b'
      },
      priceMark: {
        show: true,
        high: { show: false },
        low:  { show: false },
        last: {
          show: true,
          upColor:       '#22c55e',
          downColor:     '#ef4444',
          noChangeColor: '#94a3b8',
          line: { show: true, style: LineType.Dashed, dashedValue: [5, 6], size: 1 },
          text: {
            show: true, style: 'fill', size: 11,
            paddingLeft: 6, paddingTop: 4, paddingRight: 6, paddingBottom: 4,
            borderSize: 0, borderColor: 'transparent', borderRadius: 6,
            color: '#08111f', family: '"JetBrains Mono", monospace', weight: 'bold'
          }
        }
      },
      tooltip: {
        showRule: TooltipShowRule.FollowCross,
        showType: TooltipShowType.Standard,
        defaultValue: '--',
        custom: [
          { title: 'H', value: '{high}'  },
          { title: 'O', value: '{open}'  },
          { title: 'C', value: '{close}' },
          { title: 'L', value: '{low}'   }
        ],
        rect: {
          position: CandleTooltipRectPosition.Fixed,
          paddingLeft: 6, paddingRight: 6, paddingTop: 6, paddingBottom: 6,
          offsetLeft: 6, offsetTop: 6, offsetRight: 6, offsetBottom: 6,
          borderRadius: 8, borderSize: 1,
          borderColor: 'rgba(148,163,184,0.24)', color: '#07111f'
        },
        text: {
          size: 11, family: '"JetBrains Mono", monospace', weight: 'normal',
          color: '#d7e6f5',
          marginLeft: 6, marginTop: 4, marginRight: 8, marginBottom: 4
        },
        icons: []
      }
    },
    xAxis: {
      show: true,
      axisLine: { show: true, color: 'rgba(148,163,184,0.18)', size: 1 },
      tictView:  { show: true, size: 1, length: 3, color: 'rgba(148,163,184,0.18)' },
      tickText:  { show: true, color: '#8aa2b7', family: '"JetBrains Mono", monospace', weight: 'normal', size: 10, marginStart: 4, marginEnd: 4 }
    },
    yAxis: {
      show: true,
      position: YAxisPosition.Right,
      type: YAxisType.Normal,
      inside: false, reverse: false,
      axisLine: { show: true, color: 'rgba(148,163,184,0.18)', size: 1 },
      tictView:  { show: true, size: 1, length: 2, color: 'rgba(148,163,184,0.18)' },
      tickText:  { show: true, color: '#dbe7f3', family: '"JetBrains Mono", monospace', weight: 'normal', size: 10, marginStart: 4, marginEnd: 4 }
    },
    crosshair: {
      show: true,
      horizontal: {
        show: true,
        line: { show: true, style: LineType.Dashed, dashedValue: [4, 6], size: 1, color: 'rgba(226,232,240,0.28)' },
        text: {
          show: true, style: 'fill', color: '#e2e8f0', size: 10,
          family: '"JetBrains Mono", monospace', weight: 'normal',
          borderStyle: LineType.Solid, borderDashedValue: [2, 2], borderSize: 1,
          borderColor: 'rgba(148,163,184,0.32)', borderRadius: 6,
          paddingLeft: 6, paddingRight: 6, paddingTop: 4, paddingBottom: 4,
          backgroundColor: '#08111f'
        }
      },
      vertical: {
        show: true,
        line: { show: true, style: LineType.Dashed, dashedValue: [4, 6], size: 1, color: 'rgba(226,232,240,0.24)' },
        text: {
          show: true, style: 'fill', color: '#e2e8f0', size: 10,
          family: '"JetBrains Mono", monospace', weight: 'normal',
          borderStyle: LineType.Solid, borderDashedValue: [2, 2], borderSize: 1,
          borderColor: 'rgba(148,163,184,0.32)', borderRadius: 6,
          paddingLeft: 6, paddingRight: 6, paddingTop: 4, paddingBottom: 4,
          backgroundColor: '#08111f'
        }
      }
    }
  }
}

// ─── Format helpers ───────────────────────────────────────────────────────────
function fmtStrike(v) {
  if (v == null || !isFinite(+v)) return '—'
  return Math.round(+v).toLocaleString('pt-BR')
}
function fmtBig(v) {
  if (v == null || !isFinite(+v)) return '—'
  const a = Math.abs(+v), s = +v >= 0 ? '+' : ''
  if (a >= 1e9) return `${s}${(+v / 1e9).toFixed(1)}B`
  if (a >= 1e6) return `${s}${(+v / 1e6).toFixed(1)}M`
  if (a >= 1e3) return `${s}${(+v / 1e3).toFixed(0)}k`
  return `${s}${(+v).toFixed(1)}`
}
function fmtScore(v) {
  if (v == null || !isFinite(+v)) return 'â€”'
  return `${+v >= 0 ? '+' : ''}${(+v).toFixed(2)}`
}
function fmtOI(v) {
  if (v == null || !isFinite(+v)) return ''
  const a = Math.abs(+v)
  if (a >= 1e6) return `OI ${(+v / 1e6).toFixed(1)}M`
  if (a >= 1e3) return `OI ${(+v / 1e3).toFixed(0)}k`
  return `OI ${Math.round(+v)}`
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────
let ro = null
let liveTimer = null

onMounted(async () => {
  await nextTick()
  ensureSessionState(currentSessionDate())
  const restored = restoreBarsCache()
  if (restored) {
    refreshChartData({ reset: true, scrollToLatest: true })
  }
  await refreshLatestXb1Price()
  if (!historyReadyForSession || bars.value.length < 4) {
    reload({ background: restored }).then(() => refreshLatestXb1Price())
  }

  liveTimer = setInterval(() => {
    liveClock.value = Date.now()
    refreshLatestXb1Price()
  }, LIVE_PRICE_POLL_MS)

  // Resize observer so chart fills container on layout changes
  if (wrapEl.value && typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(() => chart?.resize())
    ro.observe(wrapEl.value)
  }
})

onUnmounted(() => {
  clearInterval(liveTimer)
  ro?.disconnect()
  destroyChart()
})

// Re-draw overlays when model data updates (new model run)
watch(() => props.modelData?.captured_at, () => applyOverlays())

// Re-apply overlays when toggles change
watch([showGamma, showZero, showBand, showFV], () => applyOverlays())
</script>

<style scoped>
.igw-root {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 6px;
  gap: 4px;
  background: #06111e;
}

/* ── Controls ────────────────────────────────────────────────────────────────── */
.igw-controls {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  flex-wrap: wrap;
}

.igw-sep {
  width: 1px;
  height: 16px;
  background: rgba(255, 255, 255, 0.08);
  margin: 0 2px;
}

.igw-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 700;
  font-family: "JetBrains Mono", monospace;
  letter-spacing: 0.05em;
  border: 1px solid transparent;
}
.igw-badge.pos { background: rgba(34, 197, 94, 0.12);  border-color: rgba(34, 197, 94, 0.30);  color: #4ade80; }
.igw-badge.neg { background: rgba(239, 68, 68, 0.12);  border-color: rgba(239, 68, 68, 0.30);  color: #f87171; }

.igw-chk {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 10px;
  color: #64748b;
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}
.igw-chk input { accent-color: #6366f1; }

.igw-fv {
  font-size: 10px;
  font-family: "JetBrains Mono", monospace;
  color: #a78bfa;
  white-space: nowrap;
}
.fv-above { color: #4ade80; }
.fv-below { color: #f87171; }

.igw-btn {
  padding: 2px 7px;
  border-radius: 4px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: transparent;
  color: #64748b;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.igw-btn:hover { background: rgba(255, 255, 255, 0.05); color: #94a3b8; }

.igw-info    { font-size: 10px; color: #475569; white-space: nowrap; }
.igw-live    { font-size: 10px; font-family: "JetBrains Mono", monospace; white-space: nowrap; }
.igw-live.ok { color: #38bdf8; }
.igw-live.stale { color: #f59e0b; }
.igw-loading { font-size: 10px; color: #f59e0b; }
.igw-error   { font-size: 10px; color: #f87171; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ── Chart wrap ──────────────────────────────────────────────────────────────── */
.igw-wrap {
  flex: 1;
  min-height: 0;
  position: relative;
  border-radius: 12px;
  overflow: hidden;
  background:
    radial-gradient(circle at top right, rgba(37, 99, 235, 0.08), transparent 30%),
    linear-gradient(180deg, #08111c 0%, #040c14 100%);
  border: 1px solid rgba(148, 163, 184, 0.10);
}

.igw-chart {
  width: 100%;
  height: 100%;
}

.igw-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #475569;
  font-size: 12px;
  text-align: center;
  padding: 20px;
}
</style>

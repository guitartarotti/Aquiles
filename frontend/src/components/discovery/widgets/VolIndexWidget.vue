<template>
  <div class="viw-root">
    <div class="viw-header">
      <span class="viw-title">Volatility Index</span>
      <div class="viw-controls">
        <select v-model="underlying" class="viw-select">
          <option v-for="item in UNDERLYINGS" :key="item.value" :value="item.value">{{ item.label }}</option>
        </select>
        <select v-model="expiryScope" class="viw-select" disabled>
          <option v-for="item in EXPIRY_SCOPES" :key="item.value" :value="item.value">{{ item.label }}</option>
        </select>
        <button type="button" class="viw-btn" :class="{ loading: collecting }" :disabled="collecting" @click="collect({ force: true })">
          {{ collecting ? '...' : 'Run' }}
        </button>
      </div>
      <span v-if="error" class="viw-error">{{ error }}</span>
    </div>

    <div v-if="latest" class="viw-snapshot">
      <div class="viw-snapshot-meta">
        <span>{{ latest.date || dash }}</span>
        <span>{{ latest.n_options ?? dash }} options</span>
        <span v-if="latest.reference_symbol">
          {{ latest.reference_symbol }} {{ fmtPrice(latest.reference_price) }}
        </span>
        <span v-if="latest.reference_price_at">{{ fmtStamp(latest.reference_price_at) }}</span>
        <span v-if="latest.selected_expiry_date">
          mensal {{ latest.selected_expiry_date }} ({{ latest.selected_days_to_expiry ?? dash }}d)
        </span>
        <span v-if="latest.iv_source">{{ latest.iv_source }}</span>
        <span v-if="latest.garch_mode">{{ latest.garch_mode }}</span>
        <span v-if="latest.garch_intraday_mode">{{ latest.garch_intraday_mode }}</span>
      </div>

      <div class="viw-source-row">
        <span class="viw-source-pill">Base {{ expiryScopeLabel }}</span>
        <span v-if="latest.selected_expiry_date" class="viw-source-pill">
          Próx. mensal {{ latest.selected_expiry_date }} ({{ latest.selected_days_to_expiry ?? dash }}d)
        </span>
      </div>

      <div class="viw-snap-grid">
        <div class="viw-snap-col">
          <div class="viw-snap-label">IVM Mensal</div>
          <div class="viw-snap-val" :style="{ color: COLOR.interp }">{{ pct(latest.iv_interpolated) }}</div>
        </div>
        <div class="viw-snap-col">
          <div class="viw-snap-label">ATM Mensal</div>
          <div class="viw-snap-val" :style="{ color: COLOR.atm }">{{ pct(latest.iv_atm) }}</div>
        </div>
        <div class="viw-snap-col">
          <div class="viw-snap-label">25D Put M</div>
          <div class="viw-snap-val" :style="{ color: COLOR.put25 }">{{ pct(latest.iv_25d_put) }}</div>
        </div>
        <div class="viw-snap-col">
          <div class="viw-snap-label">25D Call M</div>
          <div class="viw-snap-val" :style="{ color: COLOR.call25 }">{{ pct(latest.iv_25d_call) }}</div>
        </div>
        <div class="viw-snap-col">
          <div class="viw-snap-label">15D Put M</div>
          <div class="viw-snap-val" :style="{ color: COLOR.put10 }">{{ pct(latest.iv_15d_put) }}</div>
        </div>
        <div class="viw-snap-col">
          <div class="viw-snap-label">15D Call M</div>
          <div class="viw-snap-val" :style="{ color: COLOR.call10 }">{{ pct(latest.iv_15d_call) }}</div>
        </div>
        <div class="viw-snap-col">
          <div class="viw-snap-label">GARCH 5D</div>
          <div class="viw-snap-val" :style="{ color: COLOR.garch }">{{ pct(latest.rv_garch_5d) }}</div>
        </div>
        <div class="viw-snap-col">
          <div class="viw-snap-label">Gmicro</div>
          <div class="viw-snap-val" :style="{ color: COLOR.garchMicro }">{{ pct(latest.rv_garch_intraday) }}</div>
        </div>
        <div class="viw-snap-col">
          <div class="viw-snap-label">RV 5D</div>
          <div class="viw-snap-val" :style="{ color: COLOR.rv5 }">{{ pct(latest.rv_live_5d) }}</div>
        </div>
        <div class="viw-snap-col">
          <div class="viw-snap-label">RV 3D</div>
          <div class="viw-snap-val" :style="{ color: COLOR.rv3 }">{{ pct(latest.rv_live_3d) }}</div>
        </div>
        <div class="viw-snap-col">
          <div class="viw-snap-label">Skew 25D</div>
          <div class="viw-snap-val">{{ pct(latest.skew_25d, true) }}</div>
        </div>
        <div class="viw-snap-col">
          <div class="viw-snap-label">Skew 15D</div>
          <div class="viw-snap-val">{{ pct(latest.skew_15d, true) }}</div>
        </div>
        <div class="viw-snap-col">
          <div class="viw-snap-label">VRP</div>
          <div class="viw-snap-val" :style="{ color: vrpColor(latest.vrp_raw) }">{{ pct(latest.vrp_raw, true) }}</div>
        </div>
      </div>

      <div v-if="latest.recent_closes?.length" class="viw-price-row">
        <span class="viw-price-label">{{ latest.reference_symbol || 'XB1' }} closes</span>
        <span v-for="item in latest.recent_closes" :key="item.date" class="viw-price-pill">
          {{ item.date?.slice(5) }} {{ fmtPrice(item.close) }}
        </span>
      </div>
    </div>

    <div v-if="latest" class="viw-toggle-groups">
      <div class="viw-toggle-group viw-toggle-group-history">
        <span class="viw-toggle-title">Histórico</span>
        <button
          v-for="item in TIMEFRAMES"
          :key="item.value"
          type="button"
          class="viw-chip"
          :class="{ active: timeframe === item.value }"
          @click="timeframe = item.value"
        >
          {{ item.label }}
        </button>
      </div>

      <div class="viw-toggle-group">
        <span class="viw-toggle-title">Vols</span>
        <button
          v-for="series in VOL_SERIES"
          :key="series.key"
          type="button"
          class="viw-chip"
          :class="{ active: selectedVolKeys.includes(series.key) }"
          @click="toggleVolSeries(series.key)"
        >
          <span class="viw-chip-dot" :style="{ background: series.color }"></span>
          {{ series.label }}
        </button>
      </div>

      <div class="viw-toggle-group">
        <span class="viw-toggle-title">Skews</span>
        <button
          v-for="series in SPREAD_SERIES"
          :key="series.key"
          type="button"
          class="viw-chip"
          :class="{ active: selectedSpreadKeys.includes(series.key) }"
          @click="toggleSpreadSeries(series.key)"
        >
          <span class="viw-chip-dot" :style="{ background: series.color }"></span>
          {{ series.label }}
        </button>
      </div>
    </div>

    <div v-if="loading && !latest" class="viw-empty">Loading volatility history...</div>
    <div v-else-if="!latest" class="viw-empty">No volatility data yet. Run the widget to collect the first snapshot.</div>
    <div v-else-if="chartHistory.length < 2" class="viw-empty viw-empty-inline">
      Waiting for more points in {{ timeframeLabel.toLowerCase() }} to draw the history.
    </div>

    <div v-if="latest && chartHistory.length > 1" class="viw-chart-wrap" ref="volWrap">
      <div class="viw-chart-title">Vol history</div>
      <canvas ref="volCanvas"></canvas>
    </div>

    <div v-if="latest && chartHistory.length > 1" class="viw-chart-wrap viw-chart-spread" ref="spreadWrap">
      <div class="viw-chart-title">Skew and VRP</div>
      <canvas ref="spreadCanvas"></canvas>
    </div>

    <div v-if="latest?.term_structure?.length > 1" class="viw-term">
      <div class="viw-term-title">Term Structure</div>
      <div class="viw-term-items">
        <div v-for="item in latest.term_structure" :key="item.dte" class="viw-term-item">
          <div class="viw-term-dte">{{ item.dte }}d</div>
          <div class="viw-term-bar-wrap">
            <div class="viw-term-bar" :style="{ width: termBarWidth(item.iv_atm) + '%', background: COLOR.atm }"></div>
          </div>
          <div class="viw-term-iv">{{ pct(item.iv_atm) }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { collectVolIndex, getVolIndexHistory, getVolIndexLatest } from '@/api/options'

const dash = '—'
const PAD = { top: 16, right: 14, bottom: 30, left: 52 }
const HISTORY_REFRESH_MS = 30_000
const UNDERLYINGS = [
  { value: 'IBOVE Index', label: 'IBOV' },
  { value: 'IBOVB3 Index', label: 'IBOVB3' },
  { value: 'WIN Index', label: 'WIN' },
  { value: 'WDO Index', label: 'WDO' },
]

const EXPIRY_SCOPES = [
  { value: 'next_monthly', label: 'Mensal' },
]

const TIMEFRAMES = [
  { value: 'session', label: 'Pregao' },
  { value: '5d', label: '5d' },
  { value: '30d', label: '30d' },
  { value: '63d', label: '63d' },
  { value: '126d', label: '6m' },
  { value: '252d', label: '1a' },
]

const COLOR = {
  interp: '#00e5ff',
  atm: '#ffffff',
  put25: '#ff6b6b',
  call25: '#69f0ae',
  put10: '#ffb74d',
  call10: '#c6ff00',
  garch: '#ffd54f',
  garchMicro: '#4dd0e1',
  rv21: '#ffca28',
  rv5: '#ff8a65',
  rv3: '#ff5252',
  skew25: '#ce93d8',
  skew10: '#ab47bc',
  vrp: '#80cbc4',
  vrp20: '#26a69a',
  grid: '#1e2b38',
  axis: '#607d8b',
  zero: '#546e7a',
}

const VOL_SERIES = [
  { key: 'iv_interpolated', label: 'Interp', color: COLOR.interp, enabled: true },
  { key: 'iv_atm', label: 'ATM', color: COLOR.atm, enabled: true },
  { key: 'iv_25d_put', label: '25P', color: COLOR.put25, enabled: false },
  { key: 'iv_25d_call', label: '25C', color: COLOR.call25, enabled: false },
  { key: 'iv_15d_put', label: '15P', color: COLOR.put10, enabled: false },
  { key: 'iv_15d_call', label: '15C', color: COLOR.call10, enabled: false },
  { key: 'rv_garch_5d', label: 'GARCH5', color: COLOR.garch, enabled: true, dash: [5, 4], width: 2.2 },
  { key: 'rv_garch_intraday', label: 'Gmicro', color: COLOR.garchMicro, enabled: true, dash: [2, 3], width: 2 },
  { key: 'rv_garch_30d', label: 'G30', color: '#fbc02d', enabled: false, dash: [6, 5], width: 1.6 },
  { key: 'rv_simple_21d', label: 'RV21', color: COLOR.rv21, enabled: false, dash: [2, 3] },
  { key: 'rv_live_5d', label: 'RV5', color: COLOR.rv5, enabled: true },
  { key: 'rv_live_3d', label: 'RV3', color: COLOR.rv3, enabled: false },
]

const SPREAD_SERIES = [
  { key: 'skew_25d', label: 'Skew25', color: COLOR.skew25, enabled: true },
  { key: 'skew_15d', label: 'Skew15', color: COLOR.skew10, enabled: true },
  { key: 'vrp_raw', label: 'VRP', color: COLOR.vrp, enabled: true },
  { key: 'vrp_rolling_20d', label: 'VRP20', color: COLOR.vrp20, enabled: false, dash: [5, 3] }, // gitleaks:allow - metric identifier
]

const underlying = ref('IBOVE Index')
const expiryScope = ref('next_monthly')
const timeframe = ref('session')
const dailyHistory = ref([])
const intradayHistory = ref([])
const loading = ref(false)
const collecting = ref(false)
const error = ref(null)
const selectedVolKeys = ref(VOL_SERIES.filter(item => item.enabled).map(item => item.key))
const selectedSpreadKeys = ref(SPREAD_SERIES.filter(item => item.enabled).map(item => item.key))

const volWrap = ref(null)
const volCanvas = ref(null)
const spreadWrap = ref(null)
const spreadCanvas = ref(null)

const timeframeLabel = computed(() => TIMEFRAMES.find(item => item.value === timeframe.value)?.label || 'Pregao')
const expiryScopeLabel = computed(() => EXPIRY_SCOPES.find(item => item.value === expiryScope.value)?.label || 'Mensal')

const latest = computed(() => {
  const intraday = intradayHistory.value[intradayHistory.value.length - 1]
  return intraday || dailyHistory.value[dailyHistory.value.length - 1] || null
})

const latestSessionDate = computed(() => {
  const candidate = latest.value
  return candidate?._sessionDate || candidate?.date || null
})

const sessionHistory = computed(() => {
  if (!latestSessionDate.value) return []
  return intradayHistory.value.filter(item => item._sessionDate === latestSessionDate.value)
})

const fiveDayIntradayHistory = computed(() => {
  const allDates = Array.from(new Set(intradayHistory.value.map(item => item._sessionDate).filter(Boolean)))
  const allowed = new Set(allDates.slice(-5))
  return intradayHistory.value.filter(item => allowed.has(item._sessionDate))
})

const chartHistory = computed(() => {
  if (timeframe.value === 'session') {
    return sessionHistory.value
  }
  if (timeframe.value === '5d') {
    return fiveDayIntradayHistory.value.length ? fiveDayIntradayHistory.value : dailyHistory.value.slice(-5)
  }
  const requested = Number.parseInt(timeframe.value, 10) || 252
  return dailyHistory.value.slice(-requested)
})

function normalizeRecord(record) {
  const normalized = { ...(record || {}) }
  const capturedAt = String(normalized.captured_at || '').trim()
  const date = String(normalized.date || capturedAt.slice(0, 10) || '').trim()
  if (normalized.rv_garch_5d == null && normalized.rv_garch_30d != null) {
    normalized.rv_garch_5d = normalized.rv_garch_30d
  }
  normalized.captured_at = capturedAt || null
  normalized.date = date || null
  normalized._sessionDate = date || capturedAt.slice(0, 10) || null
  normalized._displayStamp = capturedAt || date || null
  return normalized
}

function pct(value, signed = false) {
  if (value == null || Number.isNaN(Number(value))) return dash
  const numeric = Number(value)
  const prefix = signed && numeric > 0 ? '+' : ''
  return `${prefix}${(numeric * 100).toFixed(2)}%`
}

function fmtPrice(value) {
  if (value == null || Number.isNaN(Number(value))) return dash
  return Number(value).toLocaleString('pt-BR', { maximumFractionDigits: 2 })
}

function fmtStamp(value) {
  if (!value) return dash
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function vrpColor(value) {
  if (value == null || Number.isNaN(Number(value))) return '#9e9e9e'
  return Number(value) >= 0 ? '#81c784' : '#ef9a9a'
}

function termBarWidth(value) {
  const maxIv = Math.max(...(latest.value?.term_structure || []).map(item => Number(item.iv_atm || 0)), 0.001)
  return Math.max(2, Math.round((Number(value || 0) / maxIv) * 100))
}

function toggleSeries(targetRef, key) {
  const currentValues = Array.isArray(targetRef?.value) ? targetRef.value : []
  const next = new Set(currentValues)
  if (next.has(key)) {
    next.delete(key)
  } else {
    next.add(key)
  }
  targetRef.value = Array.from(next)
}

function toggleVolSeries(key) {
  toggleSeries(selectedVolKeys, key)
}

function toggleSpreadSeries(key) {
  toggleSeries(selectedSpreadKeys, key)
}

function historyRequestDays() {
  if (timeframe.value === 'session' || timeframe.value === '5d') return 30
  return Number.parseInt(timeframe.value, 10) || 252
}

function sortRecords(records, key) {
  return [...records].sort((left, right) => String(left?.[key] || '').localeCompare(String(right?.[key] || '')))
}

function trimIntradayHistory(records, maxSessions = 5) {
  const sessionDates = Array.from(new Set(
    records
      .map(item => item?._sessionDate)
      .filter(Boolean),
  ))
  const allowed = new Set(sessionDates.slice(-maxSessions))
  return records.filter(item => allowed.has(item?._sessionDate))
}

function mergeDailyRecord(record) {
  const normalized = normalizeRecord(record)
  const date = normalized.date || normalized._sessionDate
  if (!date) return false

  const next = [...dailyHistory.value]
  const index = next.findIndex(item => String(item?.date || '') === date)
  if (index >= 0) next[index] = { ...next[index], ...normalized }
  else next.push(normalized)

  dailyHistory.value = sortRecords(next, 'date').slice(-Math.max(historyRequestDays(), 252))
  return true
}

function mergeIntradayRecord(record) {
  const normalized = normalizeRecord(record)
  const capturedAt = String(normalized.captured_at || '').trim()
  if (!capturedAt) return false

  const next = [...intradayHistory.value]
  const index = next.findIndex(item => String(item?.captured_at || '') === capturedAt)
  if (index >= 0) next[index] = { ...next[index], ...normalized }
  else next.push(normalized)

  intradayHistory.value = trimIntradayHistory(sortRecords(next, 'captured_at'))
  return true
}

async function load({ silent = false } = {}) {
  if (loading.value) return
  loading.value = true
  if (!silent) error.value = null
  try {
    const res = await getVolIndexHistory({
      underlying: underlying.value,
      days: historyRequestDays(),
      intraday_days: 5,
    })
    const payload = res.data || {}
    dailyHistory.value = (payload.daily_history || payload.history || []).map(normalizeRecord)
    intradayHistory.value = (payload.intraday_history || []).map(normalizeRecord)
    await nextTick()
    drawAll()
  } catch (err) {
    if (!silent) {
      error.value = err?.response?.data?.error || err?.message || 'Failed to load vol history'
    }
  } finally {
    loading.value = false
  }
}

async function refreshLatest({ silent = true } = {}) {
  if (!silent) error.value = null
  try {
    const res = await getVolIndexLatest({
      underlying: underlying.value,
    })
    const payload = res.data || {}
    if (!Object.keys(payload).length) return
    mergeDailyRecord(payload)
    mergeIntradayRecord(payload)
    await nextTick()
    drawAll()
  } catch (err) {
    if (!silent) {
      error.value = err?.response?.data?.error || err?.message || 'Failed to refresh vol history'
    }
  }
}

async function collect({ force = false, showError = true } = {}) {
  if (collecting.value) return
  collecting.value = true
  if (showError) error.value = null
  try {
    const res = await collectVolIndex({ underlying: underlying.value, force })
    const payload = res.data || {}
    if (Object.keys(payload).length) {
      mergeDailyRecord(payload)
      mergeIntradayRecord(payload)
      await nextTick()
      drawAll()
    } else {
      await refreshLatest({ silent: true })
    }
  } catch (err) {
    if (showError) {
      error.value = err?.response?.data?.error || err?.message || 'Failed to collect vol index'
    }
  } finally {
    collecting.value = false
  }
}

function axisLabel(item) {
  const stamp = item?.captured_at ? new Date(item.captured_at) : null
  if (stamp && !Number.isNaN(stamp.getTime())) {
    if (timeframe.value === 'session') {
      return stamp.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
    }
    if (timeframe.value === '5d') {
      return stamp.toLocaleString('pt-BR', {
        day: '2-digit',
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      })
    }
  }
  return String(item?.date || '').slice(5)
}

function collectSelectedValues(data, series) {
  const values = []
  for (const item of series) {
    for (const row of data) {
      const numeric = Number(row[item.key])
      if (Number.isFinite(numeric)) values.push(numeric)
    }
  }
  return values
}

function drawSeriesChart({ canvas, wrap, data, series, negativeCentered = false, height = 220, label = '' }) {
  if (!canvas || !wrap) return

  const activeSeries = series.filter(item => item)
  const values = collectSelectedValues(data, activeSeries)
  const W = wrap.clientWidth
  const H = wrap.clientHeight || height

  canvas.width = W * devicePixelRatio
  canvas.height = H * devicePixelRatio
  canvas.style.width = `${W}px`
  canvas.style.height = `${H}px`

  const ctx = canvas.getContext('2d')
  ctx.scale(devicePixelRatio, devicePixelRatio)
  ctx.clearRect(0, 0, W, H)
  ctx.fillStyle = '#0a0e14'
  ctx.fillRect(0, 0, W, H)

  if (!values.length || data.length < 2) {
    drawCenteredMessage(ctx, W, H, 'No plotted values yet')
    return
  }

  let yMin = 0
  let yMax = 1
  if (negativeCentered) {
    const absMax = Math.max(...values.map(value => Math.abs(value)), 0.001) * 1.15
    yMin = -absMax
    yMax = absMax
  } else {
    yMin = Math.max(0, Math.min(...values) * 0.92)
    yMax = Math.max(...values) * 1.08
    if (Math.abs(yMax - yMin) < 1e-6) yMax = yMin + 0.01
  }

  const chartWidth = W - PAD.left - PAD.right
  const chartHeight = H - PAD.top - PAD.bottom
  const pointCount = data.length

  const xp = index => PAD.left + (index / Math.max(pointCount - 1, 1)) * chartWidth
  const yp = value => PAD.top + (1 - (value - yMin) / Math.max(yMax - yMin, 1e-9)) * chartHeight

  drawGrid(ctx, W, H, yMin, yMax, negativeCentered)
  drawAxisLabels(ctx, data, W, H, chartWidth)

  if (negativeCentered && yMin < 0 && yMax > 0) {
    const y0 = yp(0)
    ctx.save()
    ctx.strokeStyle = COLOR.zero
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(PAD.left, y0)
    ctx.lineTo(W - PAD.right, y0)
    ctx.stroke()
    ctx.restore()
  }

  activeSeries.forEach(item => {
    drawLine(ctx, data, item, xp, yp)
  })

  ctx.save()
  ctx.fillStyle = COLOR.axis
  ctx.font = '10px monospace'
  ctx.fillText(label, 4, PAD.top + 8)
  ctx.restore()
}

function drawGrid(ctx, W, H, yMin, yMax, signed) {
  const chartHeight = H - PAD.top - PAD.bottom
  ctx.save()
  ctx.strokeStyle = COLOR.grid
  ctx.fillStyle = COLOR.axis
  ctx.lineWidth = 1
  ctx.font = '9px monospace'

  for (let index = 0; index <= 5; index += 1) {
    const ratio = index / 5
    const value = yMin + ratio * (yMax - yMin)
    const y = PAD.top + (1 - ratio) * chartHeight
    ctx.setLineDash([2, 4])
    ctx.beginPath()
    ctx.moveTo(PAD.left, y)
    ctx.lineTo(W - PAD.right, y)
    ctx.stroke()
    ctx.setLineDash([])
    const numeric = `${signed && value > 0 ? '+' : ''}${(value * 100).toFixed(1)}%`
    ctx.fillText(numeric, 2, y + 3)
  }
  ctx.restore()
}

function drawAxisLabels(ctx, data, W, H, chartWidth) {
  ctx.save()
  ctx.fillStyle = COLOR.axis
  ctx.font = '9px monospace'

  const step = Math.max(1, Math.floor(data.length / 6))
  for (let index = 0; index < data.length; index += step) {
    const x = PAD.left + (index / Math.max(data.length - 1, 1)) * chartWidth
    ctx.fillText(axisLabel(data[index]), x - 18, H - 6)
  }
  ctx.fillText(axisLabel(data[data.length - 1]), W - PAD.right - 36, H - 6)
  ctx.restore()
}

function drawLine(ctx, data, series, xp, yp) {
  ctx.save()
  ctx.strokeStyle = series.color
  ctx.lineWidth = series.width || 1.8
  ctx.lineJoin = 'round'
  ctx.lineCap = 'round'
  ctx.setLineDash(series.dash || [])
  ctx.beginPath()

  let started = false
  data.forEach((row, index) => {
    const value = Number(row[series.key])
    if (!Number.isFinite(value)) {
      started = false
      return
    }
    const x = xp(index)
    const y = yp(value)
    if (!started) {
      ctx.moveTo(x, y)
      started = true
      return
    }
    ctx.lineTo(x, y)
  })

  ctx.stroke()
  ctx.restore()
}

function drawCenteredMessage(ctx, width, height, text) {
  ctx.save()
  ctx.fillStyle = '#607d8b'
  ctx.font = '11px monospace'
  ctx.textAlign = 'center'
  ctx.fillText(text, width / 2, height / 2)
  ctx.restore()
}

function drawAll() {
  const volSeries = VOL_SERIES.filter(item => selectedVolKeys.value.includes(item.key))
  const spreadSeries = SPREAD_SERIES.filter(item => selectedSpreadKeys.value.includes(item.key))
  drawSeriesChart({
    canvas: volCanvas.value,
    wrap: volWrap.value,
    data: chartHistory.value,
    series: volSeries,
    negativeCentered: false,
    height: 180,
    label: 'VOL',
  })
  drawSeriesChart({
    canvas: spreadCanvas.value,
    wrap: spreadWrap.value,
    data: chartHistory.value,
    series: spreadSeries,
    negativeCentered: true,
    height: 120,
    label: 'SKEW',
  })
}

let resizeObserver = null
let loadTimer = null

onMounted(async () => {
  await refreshLatest({ silent: true })
  await load()
  resizeObserver = new ResizeObserver(() => drawAll())
  if (volWrap.value) resizeObserver.observe(volWrap.value)
  if (spreadWrap.value) resizeObserver.observe(spreadWrap.value)
  loadTimer = setInterval(() => refreshLatest({ silent: true }), HISTORY_REFRESH_MS)
})

onUnmounted(() => {
  resizeObserver?.disconnect()
  clearInterval(loadTimer)
})

watch(underlying, async () => {
  await refreshLatest({ silent: true })
  await load()
})

watch(timeframe, async () => {
  if (dailyHistory.value.length < historyRequestDays()) {
    await load({ silent: true })
  }
  await nextTick()
  drawAll()
})
watch(
  [chartHistory, selectedVolKeys, selectedSpreadKeys],
  () => nextTick(drawAll),
  { deep: true },
)
</script>

<style scoped>
.viw-root {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  background: #0a0e14;
  color: #cdd6e3;
  font-family: monospace;
  overflow: auto;
}

.viw-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px 5px;
  border-bottom: 1px solid #1e2b38;
  flex-shrink: 0;
}

.viw-title {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: #90caf9;
  text-transform: uppercase;
}

.viw-controls {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
}

.viw-select,
.viw-btn,
.viw-chip {
  background: #0d1620;
  border: 1px solid #1e2b38;
  color: #cdd6e3;
  font-family: monospace;
  border-radius: 4px;
}

.viw-select {
  font-size: 10px;
  padding: 2px 4px;
  cursor: pointer;
}

.viw-select[disabled] {
  opacity: 1;
  cursor: default;
  color: #90caf9;
  border-color: #27405a;
}

.viw-btn {
  padding: 3px 8px;
  color: #90caf9;
  font-size: 10px;
  cursor: pointer;
}

.viw-btn.loading {
  opacity: 0.6;
  cursor: wait;
}

.viw-error {
  color: #ef9a9a;
  font-size: 10px;
}

.viw-snapshot {
  padding: 6px 10px;
  border-bottom: 1px solid #1e2b38;
  flex-shrink: 0;
}

.viw-snapshot-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 9px;
  color: #78909c;
  margin-bottom: 6px;
}

.viw-source-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.viw-source-pill {
  font-size: 9px;
  padding: 2px 6px;
  border-radius: 999px;
  color: #9fd6ff;
  background: rgba(46, 103, 160, 0.16);
  border: 1px solid rgba(159, 214, 255, 0.18);
}

.viw-snap-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px 10px;
}

.viw-snap-col {
  min-width: 0;
}

.viw-snap-label {
  font-size: 9px;
  color: #607d8b;
  text-transform: uppercase;
}

.viw-snap-val {
  font-size: 12px;
  font-weight: 700;
  color: #eceff1;
}

.viw-price-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.viw-price-label {
  font-size: 9px;
  color: #607d8b;
  text-transform: uppercase;
  align-self: center;
}

.viw-price-pill {
  font-size: 9px;
  padding: 2px 5px;
  border-radius: 999px;
  background: rgba(144, 202, 249, 0.08);
  border: 1px solid rgba(144, 202, 249, 0.22);
}

.viw-toggle-groups {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 6px 10px;
  border-bottom: 1px solid #1e2b38;
  flex-shrink: 0;
}

.viw-toggle-group {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.viw-toggle-title {
  min-width: 42px;
  font-size: 9px;
  color: #607d8b;
  text-transform: uppercase;
}

.viw-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 6px;
  font-size: 9px;
  cursor: pointer;
  opacity: 0.65;
}

.viw-chip.active {
  opacity: 1;
  border-color: #3f566d;
  background: #122130;
}

.viw-chip-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.viw-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 18px 10px;
  color: #78909c;
  font-size: 10px;
  border-bottom: 1px solid #1e2b38;
  flex-shrink: 0;
}

.viw-empty-inline {
  padding-top: 8px;
  padding-bottom: 8px;
}

.viw-chart-wrap {
  position: relative;
  min-height: 180px;
  border-bottom: 1px solid #1e2b38;
  flex-shrink: 0;
}

.viw-chart-spread {
  min-height: 120px;
}

.viw-chart-title {
  position: absolute;
  top: 6px;
  right: 10px;
  z-index: 1;
  font-size: 9px;
  color: #607d8b;
  text-transform: uppercase;
}

.viw-chart-wrap canvas {
  width: 100%;
  height: 100%;
  display: block;
}

.viw-term {
  padding: 8px 10px 10px;
  overflow: auto;
}

.viw-term-title {
  font-size: 9px;
  color: #90caf9;
  text-transform: uppercase;
  margin-bottom: 6px;
}

.viw-term-items {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.viw-term-item {
  display: grid;
  grid-template-columns: 36px 1fr 48px;
  gap: 8px;
  align-items: center;
  font-size: 9px;
}

.viw-term-dte,
.viw-term-iv {
  color: #b0bec5;
}

.viw-term-bar-wrap {
  width: 100%;
  height: 8px;
  border-radius: 999px;
  background: #13202c;
  overflow: hidden;
}

.viw-term-bar {
  height: 100%;
  border-radius: 999px;
}

@media (max-width: 720px) {
  .viw-snap-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>

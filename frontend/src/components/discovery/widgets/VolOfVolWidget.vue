<template>
  <div class="vov-root">
    <div class="vov-header">
      <div class="vov-header-copy">
        <span class="vov-title">Vol of Vol</span>
        <span class="vov-subtitle">ATM vol of vol intraday</span>
      </div>

      <div class="vov-controls">
        <select v-model="underlying" class="vov-select">
          <option v-for="item in UNDERLYINGS" :key="item.value" :value="item.value">{{ item.label }}</option>
        </select>
        <button type="button" class="vov-btn" :class="{ loading: collecting }" :disabled="collecting" @click="refreshNow">
          {{ collecting ? '...' : 'Run' }}
        </button>
      </div>

      <span class="vov-hours-pill">09:00-18:00</span>
      <span v-if="error" class="vov-error">{{ error }}</span>
    </div>

    <div v-if="loading && !scoreSnapshot" class="vov-empty">Loading vol of vol history...</div>
    <div v-else-if="!chartPoints.length" class="vov-empty">No intraday volatility history inside market hours yet.</div>
    <div v-else-if="!scoreSnapshot" class="vov-empty">Waiting for enough ATM IV changes to compute vol of vol.</div>

    <template v-else>
      <div class="vov-score-card">
        <div class="vov-score-ring" :style="scoreRingStyle">
          <div class="vov-score-value">{{ formatScore(scoreSnapshot.score) }}</div>
          <div class="vov-score-max">/100</div>
        </div>

        <div class="vov-score-meta">
          <div class="vov-state-row">
            <span class="vov-state" :class="scoreSnapshot.tone">{{ scoreSnapshot.state }}</span>
            <span class="vov-badge" :class="scoreSnapshot.tone">ATM VoV</span>
          </div>
          <div class="vov-reading">{{ scoreSnapshot.reading }}</div>
          <div class="vov-latest-row">
            <span>Now {{ formatVolOfVol(scoreSnapshot.latestValue) }}</span>
            <span>{{ latestStampLabel }}</span>
          </div>
        </div>
      </div>

      <div class="vov-chart-card">
        <div class="vov-chart-head">
          <div class="vov-chart-copy">
            <div class="vov-chart-title">ATM vol of vol history</div>
            <div class="vov-chart-subtitle">Current session only, cash hours only.</div>
          </div>
          <div v-if="displaySnapshot" class="vov-hover-panel">
            <span class="vov-hover-label">{{ hoverSnapshot ? 'Hover' : 'Latest' }}</span>
            <span class="vov-hover-chip">{{ displaySnapshot.time }}</span>
            <span class="vov-hover-chip">{{ displaySnapshot.value }}</span>
            <span class="vov-hover-chip">{{ displaySnapshot.session }}</span>
          </div>
        </div>

        <div class="vov-chart-wrap" ref="chartWrap">
          <canvas
            ref="chartCanvas"
            @mouseenter="handlePointerEnter"
            @mousemove="handlePointerMove"
            @mouseleave="handlePointerLeave"
          ></canvas>

          <div v-if="hoverSnapshot" class="vov-tooltip" :style="tooltipStyle">
            <div class="vov-tooltip-time">{{ hoverSnapshot.time }}</div>
            <div class="vov-tooltip-value">{{ hoverSnapshot.value }}</div>
            <div class="vov-tooltip-meta">{{ hoverSnapshot.session }}</div>
          </div>
        </div>
      </div>

      <div class="vov-footer">
        <span>{{ sessionLabel }}</span>
        <span>{{ latestStampLabel }}</span>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  getVolumeIvHistory,
  pollVolume,
} from '@/api/options'

const HISTORY_REFRESH_MS = 5_000
const TRACKER_STALE_MS = 75_000
const TRACKER_POLL_COOLDOWN_MS = 30_000
const TRACKER_POLL_SOFT_WAIT_MS = 8_000
const HISTORY_SOURCE_LIMIT = 2_400
const LATEST_SOURCE_LIMIT = 12
const CHART_HEIGHT = 220
const PAD = { top: 18, right: 20, bottom: 36, left: 56 }
const ROLLING_WINDOW_MINUTES = 30
const MARKET_OPEN_MINUTES = 9 * 60
const MARKET_CLOSE_MINUTES = 18 * 60
const BRT_TIME_ZONE = 'America/Sao_Paulo'
const HISTORY_CACHE_VERSION = 3
const HISTORY_CACHE_MAX_SESSIONS = 1
const HISTORY_CACHE_PREFIX = 'discovery:vov'
const COLOR = {
  bg: '#09111a',
  panel: '#0d1620',
  border: '#1e2b38',
  text: '#cdd6e3',
  muted: '#607d8b',
  line: '#38bdf8',
  lineGlow: 'rgba(56, 189, 248, 0.24)',
  areaTop: 'rgba(56, 189, 248, 0.22)',
  areaBottom: 'rgba(56, 189, 248, 0.02)',
  grid: '#1e2b38',
  divider: 'rgba(148, 163, 184, 0.28)',
  hover: '#7dd3fc',
  tooltipBg: 'rgba(8, 15, 24, 0.96)',
  tooltipBorder: 'rgba(56, 189, 248, 0.3)',
}

const UNDERLYINGS = [
  { value: 'IBOVE Index', label: 'IBOV' },
  { value: 'IBOVB3 Index', label: 'IBOVB3' },
  { value: 'WIN Index', label: 'WIN' },
  { value: 'WDO Index', label: 'WDO' },
]

const props = defineProps({
  underlyingSecurity: { type: String, default: 'IBOVE Index' },
  refreshNonce: { type: Number, default: 0 },
})

const BRT_FORMATTER = new Intl.DateTimeFormat('en-CA', {
  timeZone: BRT_TIME_ZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

const underlying = ref(props.underlyingSecurity || 'IBOVE Index')
const intradayHistory = ref([])
const loading = ref(false)
const collecting = ref(false)
const error = ref(null)

const chartWrap = ref(null)
const chartCanvas = ref(null)
const hoverIndex = ref(null)
const chartMetrics = ref(null)

const historyCache = new Map()

let resizeObserver = null
let loadTimer = null
let latestRefreshToken = 0
let lastForcedTrackerPollAt = 0
let trackerPollPromise = null

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

function erf(value) {
  const sign = value < 0 ? -1 : 1
  const abs = Math.abs(value)
  const t = 1 / (1 + (0.3275911 * abs))
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

function normalizeRecord(record) {
  const normalized = { ...(record || {}) }
  const capturedAt = String(normalized.captured_at || '').trim()
  const date = String(normalized.date || normalized.session_date || capturedAt.slice(0, 10) || '').trim()
  const parsed = capturedAt ? new Date(capturedAt) : null
  normalized.captured_at = capturedAt || null
  normalized.date = date || null
  normalized._sessionDate = date || capturedAt.slice(0, 10) || null
  normalized._epoch = parsed && !Number.isNaN(parsed.getTime()) ? parsed.getTime() : null
  return normalized
}

function brtPartsFromStamp(value) {
  const text = String(value || '').trim()
  if (!text) return null
  const stamp = new Date(text)
  if (Number.isNaN(stamp.getTime())) return null
  const parts = Object.fromEntries(
    BRT_FORMATTER
      .formatToParts(stamp)
      .filter(part => part.type !== 'literal')
      .map(part => [part.type, part.value]),
  )
  return {
    year: Number(parts.year),
    month: Number(parts.month),
    day: Number(parts.day),
    hours: Number(parts.hour),
    minutes: Number(parts.minute),
  }
}

function clockFromStamp(value) {
  const parts = brtPartsFromStamp(value)
  if (!parts) return null
  return {
    hours: parts.hours,
    minutes: parts.minutes,
  }
}

function marketMinuteOfDay(record) {
  const clock = clockFromStamp(record?.captured_at)
  if (!clock) return null
  return (clock.hours * 60) + clock.minutes
}

function isWithinMarketHours(record) {
  const minuteOfDay = marketMinuteOfDay(record)
  return minuteOfDay != null && minuteOfDay >= MARKET_OPEN_MINUTES && minuteOfDay <= MARKET_CLOSE_MINUTES
}

function buildLogReturns(values) {
  const returns = []
  for (let index = 1; index < values.length; index += 1) {
    const previous = values[index - 1]
    const current = values[index]
    if (previous == null || current == null || previous <= 0 || current <= 0) continue
    returns.push(Math.log(current / previous))
  }
  return returns
}

function trailingRecords(records, index, minutes) {
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

function buildVolOfVolSeries(records) {
  return records.map((record, index) => {
    const sample = trailingRecords(records, index, ROLLING_WINDOW_MINUTES)
    const ivSeries = sample
      .map(item => safeNumber(item.iv_atm ?? item.iv_interpolated))
      .filter(value => value != null)
    const returns = buildLogReturns(ivSeries)
    return {
      ...record,
      value: returns.length >= 2 ? std(returns) : null,
    }
  })
}

function formatScore(value) {
  const numeric = safeNumber(value)
  if (numeric == null) return '--'
  return `${Math.round(clamp(numeric, 0, 100))}`
}

function formatVolOfVol(value) {
  const numeric = safeNumber(value)
  if (numeric == null) return '--'
  return `${(numeric * 100).toFixed(2)}%`
}

function formatStamp(value) {
  const parts = brtPartsFromStamp(value)
  if (!parts) return '--'
  return `${String(parts.day).padStart(2, '0')}/${String(parts.month).padStart(2, '0')} ${String(parts.hours).padStart(2, '0')}:${String(parts.minutes).padStart(2, '0')}`
}

function formatSessionDate(value) {
  if (!value) return '--'
  const [year, month, day] = String(value).split('-')
  if (!year || !month || !day) return String(value)
  return `${day}/${month}`
}

function formatTime(value) {
  const clock = clockFromStamp(value)
  if (!clock) return '--'
  return `${String(clock.hours).padStart(2, '0')}:${String(clock.minutes).padStart(2, '0')}`
}

function currentBrtSessionDate() {
  const parts = brtPartsFromStamp(new Date().toISOString())
  if (!parts) return null
  return `${String(parts.year).padStart(4, '0')}-${String(parts.month).padStart(2, '0')}-${String(parts.day).padStart(2, '0')}`
}

function isMarketOpenNow() {
  const nowMinute = marketMinuteOfDay({ captured_at: new Date().toISOString() })
  return nowMinute != null && nowMinute >= MARKET_OPEN_MINUTES && nowMinute <= MARKET_CLOSE_MINUTES
}

function recordAgeMs(record) {
  const epoch = safeNumber(normalizeRecord(record)?._epoch)
  if (epoch == null) return Number.POSITIVE_INFINITY
  return Math.max(Date.now() - epoch, 0)
}

function wait(ms) {
  return new Promise(resolve => window.setTimeout(resolve, ms))
}

function latestSourceRecord(payload) {
  const latest = normalizeRecord(payload?.latest || payload?.history?.[0] || null)
  return latest?.captured_at ? latest : null
}

async function fetchVolumeIvPayload(
  underlyingSecurity,
  {
    limit = LATEST_SOURCE_LIMIT,
    forceRefresh = false,
    sessionDate = currentBrtSessionDate(),
  } = {},
) {
  const response = await getVolumeIvHistory({
    underlying_security: underlyingSecurity,
    session_date: sessionDate || undefined,
    lookback_days: 1,
    limit,
    refresh: forceRefresh,
  })
  return response?.data || {}
}

function triggerTrackerPoll(
  underlyingSecurity,
  {
    waitMs = 0,
  } = {},
) {
  if (!trackerPollPromise) {
    lastForcedTrackerPollAt = Date.now()
    trackerPollPromise = Promise.resolve()
      .then(() => pollVolume(underlyingSecurity))
      .catch(err => {
        console.warn('Vol of Vol tracker poll failed:', err)
      })
      .then(async () => {
        if (underlying.value !== underlyingSecurity) return
        await refreshLatest({ silent: true, allowTrackerPoll: false })
      })
      .finally(() => {
        trackerPollPromise = null
      })
  }

  if (!(waitMs > 0)) return trackerPollPromise

  return Promise.race([
    trackerPollPromise,
    wait(waitMs),
  ])
}

function scoreColor(score) {
  if (score >= 85) return '#ef4444'
  if (score >= 70) return '#fb7185'
  if (score >= 45) return '#f59e0b'
  return '#22c55e'
}

function classifyScore(score) {
  if (score >= 85) return ['Stress', 'hot']
  if (score >= 70) return ['Elevated', 'warm']
  if (score >= 45) return ['Balanced', 'neutral']
  return ['Calm', 'cool']
}

function buildReading(score) {
  if (score >= 85) return 'ATM vol of vol is stretched, signaling unstable IV repricing.'
  if (score >= 70) return 'ATM vol of vol is elevated and worth monitoring.'
  if (score >= 45) return 'ATM vol of vol is running near its recent range.'
  return 'ATM vol of vol is contained for now.'
}

const sessionDates = computed(() => Array.from(
  new Set(
    intradayHistory.value
      .filter(item => isWithinMarketHours(item))
      .map(item => item._sessionDate)
      .filter(Boolean),
  ),
))

const activeSessionDate = computed(() => {
  if (!sessionDates.value.length) return null
  const today = currentBrtSessionDate()
  if (today && sessionDates.value.includes(today)) return today
  return sessionDates.value[sessionDates.value.length - 1]
})

const chartHistory = computed(() => {
  if (!activeSessionDate.value) return []
  return intradayHistory.value.filter(
    item => item._sessionDate === activeSessionDate.value && isWithinMarketHours(item),
  )
})

const chartPoints = computed(() => buildVolOfVolSeries(chartHistory.value))

const latestStampLabel = computed(() => {
  const lastPoint = chartPoints.value[chartPoints.value.length - 1]
  return `Updated ${formatStamp(lastPoint?.captured_at)}`
})

const sessionLabel = computed(() => {
  if (activeSessionDate.value) {
    return `Session ${formatSessionDate(activeSessionDate.value)} · 09:00-18:00`
  }
  return 'No sessions loaded'
})

const scoreSnapshot = computed(() => {
  const finitePoints = chartPoints.value.filter(item => safeNumber(item.value) != null)
  if (finitePoints.length < 3) return null

  const latestPoint = finitePoints[finitePoints.length - 1]
  const baselineValues = finitePoints.slice(0, -1).map(item => item.value)
  const fallbackValues = finitePoints.map(item => item.value)
  const values = baselineValues.length >= 5 ? baselineValues : fallbackValues
  const latestValue = safeNumber(latestPoint?.value)
  const avg = mean(values)
  const sigma = std(values)
  const z = latestValue != null && avg != null && sigma != null && sigma > 1e-12
    ? ((latestValue - avg) / sigma)
    : 0
  const score = clamp(normalCdf(z) * 100, 0, 100)
  const [state, tone] = classifyScore(score)

  return {
    score,
    state,
    tone,
    latestValue,
    reading: buildReading(score),
  }
})

const scoreRingStyle = computed(() => {
  const score = scoreSnapshot.value?.score || 0
  return {
    background: `conic-gradient(${scoreColor(score)} 0 ${score}%, rgba(30, 41, 59, 0.95) ${score}% 100%)`,
  }
})

function buildPointSnapshot(point) {
  if (!point) return null
  const value = safeNumber(point?.value)
  if (value == null) return null
  const atmIv = safeNumber(point?.iv_atm ?? point?.iv_interpolated)
  return {
    time: `${formatSessionDate(point?._sessionDate)} ${formatTime(point?.captured_at)}`,
    value: `VoV ${formatVolOfVol(value)}`,
    session: `ATM IV ${formatVolOfVol(atmIv)}`,
  }
}

const latestPointSnapshot = computed(() => {
  const lastFinitePoint = [...chartPoints.value].reverse().find(point => safeNumber(point?.value) != null)
  return buildPointSnapshot(lastFinitePoint || null)
})

const hoverSnapshot = computed(() => {
  const index = hoverIndex.value
  if (index == null || index < 0 || index >= chartPoints.value.length) return null
  return buildPointSnapshot(chartPoints.value[index] || null)
})

const displaySnapshot = computed(() => hoverSnapshot.value || latestPointSnapshot.value)

function chartX(index, total, metrics) {
  return PAD.left + ((index / Math.max(total - 1, 1)) * metrics.chartWidth)
}

function chartY(value, metrics) {
  return PAD.top + ((1 - ((value - metrics.yMin) / Math.max(metrics.yMax - metrics.yMin, 1e-9))) * metrics.chartHeight)
}

const tooltipStyle = computed(() => {
  if (!hoverSnapshot.value || hoverIndex.value == null || !chartMetrics.value) return {}
  const point = chartPoints.value[hoverIndex.value]
  const value = safeNumber(point?.value)
  if (value == null) return {}
  const metrics = chartMetrics.value
  const pointX = chartX(hoverIndex.value, chartPoints.value.length, metrics)
  const pointY = chartY(value, metrics)
  const tooltipWidth = 176
  const tooltipHeight = 72
  let left = pointX + 14
  if ((left + tooltipWidth) > (metrics.width - 10)) {
    left = pointX - tooltipWidth - 14
  }
  return {
    left: `${left}px`,
    top: `${clamp(pointY - (tooltipHeight / 2), 12, metrics.height - tooltipHeight - 12)}px`,
  }
})

function axisLabel(item, previousItem = null) {
  if (!item) return ''
  if (!previousItem || previousItem._sessionDate !== item._sessionDate) {
    return `${formatSessionDate(item._sessionDate)} ${formatTime(item.captured_at)}`
  }
  return formatTime(item.captured_at)
}

function nearestFiniteIndex(data, targetIndex) {
  if (!data.length) return null
  for (let offset = 0; offset < data.length; offset += 1) {
    const left = targetIndex - offset
    if (left >= 0 && safeNumber(data[left]?.value) != null) return left
    const right = targetIndex + offset
    if (right < data.length && safeNumber(data[right]?.value) != null) return right
  }
  return null
}

function drawCenteredMessage(ctx, width, height, text) {
  ctx.save()
  ctx.fillStyle = COLOR.muted
  ctx.font = '11px monospace'
  ctx.textAlign = 'center'
  ctx.fillText(text, width / 2, height / 2)
  ctx.restore()
}

function drawGrid(ctx, width, metrics) {
  const { yMin, yMax, chartHeight } = metrics
  ctx.save()
  ctx.strokeStyle = COLOR.grid
  ctx.fillStyle = COLOR.muted
  ctx.lineWidth = 1
  ctx.font = '9px monospace'
  ctx.textAlign = 'left'

  for (let index = 0; index <= 5; index += 1) {
    const ratio = index / 5
    const value = yMin + (ratio * (yMax - yMin))
    const y = PAD.top + ((1 - ratio) * chartHeight)
    ctx.setLineDash([2, 4])
    ctx.beginPath()
    ctx.moveTo(PAD.left, y)
    ctx.lineTo(width - PAD.right, y)
    ctx.stroke()
    ctx.setLineDash([])
    ctx.fillText(`${(value * 100).toFixed(2)}%`, 6, y + 3)
  }

  ctx.restore()
}

function drawAxisLabels(ctx, data, width, height, chartWidth) {
  ctx.save()
  ctx.fillStyle = COLOR.muted
  ctx.font = '9px monospace'
  ctx.textAlign = 'left'

  const step = Math.max(1, Math.floor(data.length / 6))
  for (let index = 0; index < data.length; index += step) {
    const x = PAD.left + ((index / Math.max(data.length - 1, 1)) * chartWidth)
    const label = axisLabel(data[index], data[index - 1])
    ctx.fillText(label, clamp(x - 24, PAD.left - 8, width - PAD.right - 52), height - 8)
  }

  if (data.length) {
    ctx.fillText(axisLabel(data[data.length - 1], data[data.length - 2]), width - PAD.right - 52, height - 8)
  }

  ctx.restore()
}

function drawSeries(ctx, data, xPoint, yPoint, height) {
  const finitePoints = data.filter(item => safeNumber(item.value) != null)
  if (finitePoints.length < 2) return

  const firstFiniteIndex = data.findIndex(point => safeNumber(point.value) != null)
  const reverseIndex = [...data].reverse().findIndex(point => safeNumber(point.value) != null)
  const lastFiniteIndex = reverseIndex < 0 ? -1 : (data.length - 1 - reverseIndex)

  const areaPath = new Path2D()
  let areaStarted = false
  data.forEach((point, index) => {
    const value = safeNumber(point.value)
    if (value == null) {
      areaStarted = false
      return
    }
    const x = xPoint(index)
    const y = yPoint(value)
    if (!areaStarted) {
      areaPath.moveTo(x, height - PAD.bottom)
      areaPath.lineTo(x, y)
      areaStarted = true
      return
    }
    areaPath.lineTo(x, y)
  })

  if (firstFiniteIndex >= 0 && lastFiniteIndex >= firstFiniteIndex) {
    areaPath.lineTo(xPoint(lastFiniteIndex), height - PAD.bottom)
    areaPath.closePath()
    const gradient = ctx.createLinearGradient(0, PAD.top, 0, height - PAD.bottom)
    gradient.addColorStop(0, COLOR.areaTop)
    gradient.addColorStop(1, COLOR.areaBottom)
    ctx.save()
    ctx.fillStyle = gradient
    ctx.fill(areaPath)
    ctx.restore()
  }

  ctx.save()
  ctx.shadowColor = COLOR.lineGlow
  ctx.shadowBlur = 14
  ctx.strokeStyle = COLOR.line
  ctx.lineWidth = 2
  ctx.lineJoin = 'round'
  ctx.lineCap = 'round'
  ctx.beginPath()

  let started = false
  data.forEach((point, index) => {
    const value = safeNumber(point.value)
    if (value == null) {
      started = false
      return
    }
    const x = xPoint(index)
    const y = yPoint(value)
    if (!started) {
      ctx.moveTo(x, y)
      started = true
      return
    }
    ctx.lineTo(x, y)
  })

  ctx.stroke()
  ctx.shadowBlur = 0

  const lastPoint = finitePoints[finitePoints.length - 1]
  const lastIndexPosition = data.findIndex(point => point.captured_at === lastPoint.captured_at)
  if (lastIndexPosition >= 0) {
    ctx.beginPath()
    ctx.fillStyle = COLOR.line
    ctx.arc(xPoint(lastIndexPosition), yPoint(lastPoint.value), 3, 0, Math.PI * 2)
    ctx.fill()
  }

  ctx.restore()
}

function drawHoverGuide(ctx, data, metrics) {
  if (hoverIndex.value == null) return
  const point = data[hoverIndex.value]
  const value = safeNumber(point?.value)
  if (value == null) return

  const x = chartX(hoverIndex.value, data.length, metrics)
  const y = chartY(value, metrics)

  ctx.save()
  ctx.strokeStyle = 'rgba(125, 211, 252, 0.45)'
  ctx.lineWidth = 1
  ctx.setLineDash([4, 4])
  ctx.beginPath()
  ctx.moveTo(x, PAD.top)
  ctx.lineTo(x, metrics.height - PAD.bottom)
  ctx.moveTo(PAD.left, y)
  ctx.lineTo(metrics.width - PAD.right, y)
  ctx.stroke()
  ctx.setLineDash([])

  ctx.beginPath()
  ctx.fillStyle = COLOR.bg
  ctx.strokeStyle = COLOR.hover
  ctx.lineWidth = 2
  ctx.arc(x, y, 5, 0, Math.PI * 2)
  ctx.fill()
  ctx.stroke()

  const label = formatVolOfVol(value)
  ctx.font = '10px monospace'
  ctx.textAlign = 'left'
  const labelWidth = ctx.measureText(label).width + 14
  const boxX = metrics.width - PAD.right - labelWidth
  const boxY = clamp(y - 10, PAD.top + 4, metrics.height - PAD.bottom - 22)
  ctx.fillStyle = COLOR.tooltipBg
  ctx.fillRect(boxX, boxY, labelWidth, 20)
  ctx.strokeStyle = COLOR.tooltipBorder
  ctx.strokeRect(boxX, boxY, labelWidth, 20)
  ctx.fillStyle = '#dff7ff'
  ctx.fillText(label, boxX + 7, boxY + 13)

  ctx.restore()
}

function drawChart() {
  const wrap = chartWrap.value
  const canvas = chartCanvas.value
  const data = chartPoints.value
  if (!wrap || !canvas) return

  const width = wrap.clientWidth
  const height = wrap.clientHeight || CHART_HEIGHT
  const ratio = window.devicePixelRatio || 1

  canvas.width = width * ratio
  canvas.height = height * ratio
  canvas.style.width = `${width}px`
  canvas.style.height = `${height}px`

  const ctx = canvas.getContext('2d')
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0)
  ctx.clearRect(0, 0, width, height)
  ctx.fillStyle = COLOR.bg
  ctx.fillRect(0, 0, width, height)

  const finiteValues = data.map(point => safeNumber(point.value)).filter(value => value != null)
  if (finiteValues.length < 2) {
    chartMetrics.value = null
    drawCenteredMessage(ctx, width, height, 'Not enough points to draw yet')
    return
  }

  const yMinRaw = Math.min(...finiteValues)
  const yMaxRaw = Math.max(...finiteValues)
  const yMin = Math.max(0, yMinRaw * 0.9)
  const yMax = Math.max(yMin + 0.0005, yMaxRaw * 1.1)

  const chartWidth = width - PAD.left - PAD.right
  const chartHeight = height - PAD.top - PAD.bottom
  const metrics = { width, height, chartWidth, chartHeight, yMin, yMax }
  chartMetrics.value = metrics
  const xPoint = index => chartX(index, data.length, metrics)
  const yPoint = value => chartY(value, metrics)

  drawGrid(ctx, width, metrics)
  drawAxisLabels(ctx, data, width, height, chartWidth)
  drawSeries(ctx, data, xPoint, yPoint, height)
  drawHoverGuide(ctx, data, metrics)

  ctx.save()
  ctx.font = '10px monospace'
  ctx.fillStyle = COLOR.muted
  ctx.fillText('VoV (left)', 6, PAD.top + 8)
  ctx.restore()
}

function handlePointerMove(event) {
  const data = chartPoints.value
  const metrics = chartMetrics.value
  const canvas = chartCanvas.value
  if (!canvas || !metrics || data.length < 2) return

  const rect = canvas.getBoundingClientRect()
  const mouseX = clamp(event.clientX - rect.left, PAD.left, rect.width - PAD.right)
  const relative = (mouseX - PAD.left) / Math.max(metrics.chartWidth, 1)
  const rawIndex = Math.round(relative * Math.max(data.length - 1, 0))
  const nextIndex = nearestFiniteIndex(data, rawIndex)
  if (nextIndex == null || nextIndex === hoverIndex.value) return

  hoverIndex.value = nextIndex
  drawChart()
}

function handlePointerEnter() {
  if (hoverIndex.value != null || !chartPoints.value.length) return
  const nextIndex = nearestFiniteIndex(chartPoints.value, chartPoints.value.length - 1)
  if (nextIndex == null) return
  hoverIndex.value = nextIndex
  drawChart()
}

function handlePointerLeave() {
  if (hoverIndex.value == null) return
  hoverIndex.value = null
  drawChart()
}

function sortByCapturedAt(records) {
  return [...records].sort((left, right) => String(left?.captured_at || '').localeCompare(String(right?.captured_at || '')))
}

function combineHistoryRecords(...groups) {
  const byStamp = new Map()

  for (const group of groups) {
    for (const rawRecord of group || []) {
      const normalized = normalizeRecord(rawRecord)
      const capturedAt = String(normalized?.captured_at || '').trim()
      if (!capturedAt) continue

      byStamp.set(capturedAt, {
        ...(byStamp.get(capturedAt) || {}),
        ...normalized,
      })
    }
  }

  return sortByCapturedAt([...byStamp.values()])
}

function trimHistoryToRecentSessions(records, maxSessions = HISTORY_CACHE_MAX_SESSIONS) {
  const sessionDates = Array.from(new Set(
    records
      .map(item => item?._sessionDate)
      .filter(Boolean),
  ))
  const allowed = new Set(sessionDates.slice(-maxSessions))
  return records.filter(item => allowed.has(item?._sessionDate))
}

function sanitizeHistoryRecords(records, { maxSessions = HISTORY_CACHE_MAX_SESSIONS } = {}) {
  return trimHistoryToRecentSessions(combineHistoryRecords(records), maxSessions)
}

function historyCacheKey(kind, underlyingSecurity) {
  return `${HISTORY_CACHE_PREFIX}:${kind}:${String(underlyingSecurity || '').trim() || 'unknown'}`
}

function serializeHistoryRecord(kind, record) {
  const normalized = normalizeRecord(record)
  const serialized = {
    captured_at: normalized.captured_at,
    date: normalized.date || normalized._sessionDate || null,
  }

  if (kind === 'vol') {
    const ivAtm = safeNumber(normalized.iv_atm)
    const ivInterpolated = safeNumber(normalized.iv_interpolated)
    if (ivAtm != null) serialized.iv_atm = ivAtm
    if (ivInterpolated != null) serialized.iv_interpolated = ivInterpolated
  }

  return serialized
}

function readHistoryCache(kind, underlyingSecurity) {
  const key = historyCacheKey(kind, underlyingSecurity)
  const cached = historyCache.get(key)
  if (cached?.version === HISTORY_CACHE_VERSION && Array.isArray(cached.records)) {
    return sanitizeHistoryRecords(cached.records)
  }

  try {
    if (typeof window === 'undefined' || !window.localStorage) return []
    const raw = window.localStorage.getItem(key)
    if (!raw) return []

    const parsed = JSON.parse(raw)
    if (parsed?.version !== HISTORY_CACHE_VERSION || !Array.isArray(parsed.records)) return []

    const records = sanitizeHistoryRecords(parsed.records)
    historyCache.set(key, { version: HISTORY_CACHE_VERSION, records })
    return records
  } catch (err) {
    console.warn(`Vol of Vol ${kind} cache read failed:`, err)
    return []
  }
}

function writeHistoryCache(kind, underlyingSecurity, records, { maxSessions = HISTORY_CACHE_MAX_SESSIONS } = {}) {
  const key = historyCacheKey(kind, underlyingSecurity)
  const sanitized = sanitizeHistoryRecords(records, { maxSessions })
  const entry = {
    version: HISTORY_CACHE_VERSION,
    records: sanitized.map(record => serializeHistoryRecord(kind, record)),
  }

  historyCache.set(key, entry)

  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      window.localStorage.setItem(key, JSON.stringify(entry))
    }
  } catch (err) {
    console.warn(`Vol of Vol ${kind} cache write failed:`, err)
  }

  return sanitized
}

function hydrateHistoryCache(underlyingSecurity) {
  const cachedVol = readHistoryCache('vol', underlyingSecurity)
  intradayHistory.value = cachedVol
  hoverIndex.value = null
  return cachedVol.length > 0
}

function mergeLatestRecord(
  recordsRef,
  record,
  {
    maxSessions = HISTORY_CACHE_MAX_SESSIONS,
    cacheKind = null,
    underlyingSecurity = underlying.value,
  } = {},
) {
  const normalized = normalizeRecord(record)
  const capturedAt = String(normalized?.captured_at || '').trim()
  if (!capturedAt) return false

  const next = [...recordsRef.value]
  const existingIndex = next.findIndex(item => String(item?.captured_at || '') === capturedAt)
  if (existingIndex >= 0) {
    next[existingIndex] = { ...next[existingIndex], ...normalized }
  } else {
    next.push(normalized)
  }

  const sanitized = sanitizeHistoryRecords(next, { maxSessions })
  recordsRef.value = sanitized
  if (cacheKind) writeHistoryCache(cacheKind, underlyingSecurity, sanitized, { maxSessions })
  return true
}

function replaceHistory(
  recordsRef,
  records,
  {
    maxSessions = HISTORY_CACHE_MAX_SESSIONS,
    cacheKind = null,
    underlyingSecurity = underlying.value,
    preserveExisting = false,
  } = {},
) {
  const incoming = sanitizeHistoryRecords(records, { maxSessions })
  const next = preserveExisting && recordsRef.value.length
    ? sanitizeHistoryRecords(combineHistoryRecords(recordsRef.value, incoming), { maxSessions })
    : incoming

  recordsRef.value = next
  if (cacheKind) writeHistoryCache(cacheKind, underlyingSecurity, next, { maxSessions })
}

async function loadInitialHistory({ silent = false } = {}) {
  if (loading.value) return
  loading.value = true
  if (!silent) error.value = null
  const requestedUnderlying = underlying.value
  try {
    const sessionDate = currentBrtSessionDate() || activeSessionDate.value
    const volResponse = await fetchVolumeIvPayload(requestedUnderlying, {
      sessionDate,
      limit: HISTORY_SOURCE_LIMIT,
      forceRefresh: true,
    })
    if (underlying.value !== requestedUnderlying) return
    replaceHistory(intradayHistory, volResponse.history || [], {
      cacheKind: 'vol',
      underlyingSecurity: requestedUnderlying,
      preserveExisting: true,
    })
    hoverIndex.value = null
    await nextTick()
    drawChart()
    void refreshLatest({ silent: true })
  } catch (err) {
    if (!silent) {
      error.value = err?.response?.data?.error || err?.message || 'Failed to load vol history'
    }
  } finally {
    loading.value = false
  }
}

async function refreshLatest({ silent = true, allowTrackerPoll = true } = {}) {
  const requestedUnderlying = underlying.value
  const refreshToken = ++latestRefreshToken
  if (!silent) error.value = null
  try {
    const sessionDate = currentBrtSessionDate() || activeSessionDate.value
    let volPayload = await fetchVolumeIvPayload(requestedUnderlying, {
      sessionDate,
      limit: LATEST_SOURCE_LIMIT,
    })
    let latestRecord = latestSourceRecord(volPayload)

    const shouldPollTracker = (
      allowTrackerPoll
      && isMarketOpenNow()
      && recordAgeMs(latestRecord) >= TRACKER_STALE_MS
      && (Date.now() - lastForcedTrackerPollAt) >= TRACKER_POLL_COOLDOWN_MS
    )

    if (shouldPollTracker) {
      void triggerTrackerPoll(requestedUnderlying)
    }

    if (refreshToken !== latestRefreshToken || underlying.value !== requestedUnderlying) return

    if (Array.isArray(volPayload.history) && volPayload.history.length) {
      replaceHistory(intradayHistory, volPayload.history, {
        cacheKind: 'vol',
        underlyingSecurity: requestedUnderlying,
        preserveExisting: true,
      })
    } else if (latestRecord) {
      mergeLatestRecord(intradayHistory, latestRecord, {
        cacheKind: 'vol',
        underlyingSecurity: requestedUnderlying,
      })
    } else if (!silent) {
      error.value = 'Failed to refresh vol history'
    }

    await nextTick()
    drawChart()
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
    if (force || isMarketOpenNow()) {
      await triggerTrackerPoll(underlying.value, { waitMs: TRACKER_POLL_SOFT_WAIT_MS })
    }
    await loadInitialHistory({ silent: true })
    await refreshLatest({ silent: true, allowTrackerPoll: false })
  } catch (err) {
    if (showError) {
      error.value = err?.response?.data?.error || err?.message || 'Failed to refresh vol tracker'
    }
  } finally {
    collecting.value = false
  }
}

async function refreshNow() {
  await collect({ force: true, showError: true })
}

onMounted(async () => {
  hydrateHistoryCache(underlying.value)
  await nextTick()
  drawChart()
  await loadInitialHistory()
  resizeObserver = new ResizeObserver(() => drawChart())
  if (chartWrap.value) resizeObserver.observe(chartWrap.value)
  loadTimer = setInterval(() => refreshLatest({ silent: true }), HISTORY_REFRESH_MS)
})

onUnmounted(() => {
  resizeObserver?.disconnect()
  clearInterval(loadTimer)
})

watch(() => props.underlyingSecurity, async (next) => {
  if (!next || next === underlying.value) return
  underlying.value = next
})

watch(() => props.refreshNonce, async (next, previous) => {
  if (!next || next === previous) return
  if (!chartPoints.value.length) {
    await loadInitialHistory({ silent: true })
  }
  await refreshLatest({ silent: true })
})

watch(underlying, async () => {
  error.value = null
  hydrateHistoryCache(underlying.value)
  await nextTick()
  drawChart()
  await loadInitialHistory()
})

watch(chartPoints, () => {
  if (hoverIndex.value != null) {
    const point = chartPoints.value[hoverIndex.value]
    if (!point || safeNumber(point.value) == null) {
      hoverIndex.value = null
    }
  }
  nextTick(drawChart)
})
</script>

<style scoped>
.vov-root {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  min-height: 0;
  padding: 12px;
  gap: 12px;
  box-sizing: border-box;
  background:
    radial-gradient(circle at top left, rgba(56, 189, 248, 0.08), transparent 26%),
    linear-gradient(180deg, #081019 0%, #0a0e14 100%);
  color: #cdd6e3;
  font-family: monospace;
  overflow: hidden;
}

.vov-header,
.vov-score-card,
.vov-chart-card {
  border: 1px solid rgba(30, 43, 56, 0.95);
  border-radius: 16px;
  background: rgba(10, 18, 28, 0.92);
  box-shadow: inset 0 1px 0 rgba(148, 163, 184, 0.06);
}

.vov-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px 12px;
  padding: 12px 14px;
  flex-shrink: 0;
}

.vov-header-copy {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.vov-title {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: #90caf9;
  text-transform: uppercase;
}

.vov-subtitle {
  font-size: 10px;
  color: #7d8ea3;
}

.vov-controls {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}

.vov-hours-pill {
  padding: 4px 8px;
  border-radius: 999px;
  border: 1px solid rgba(56, 189, 248, 0.18);
  background: rgba(56, 189, 248, 0.08);
  color: #7dd3fc;
  font-size: 10px;
  letter-spacing: 0.04em;
}

.vov-select,
.vov-btn {
  background: rgba(13, 22, 32, 0.96);
  border: 1px solid rgba(30, 43, 56, 0.95);
  color: #cdd6e3;
  font-family: monospace;
  border-radius: 8px;
}

.vov-select {
  font-size: 10px;
  padding: 5px 8px;
  cursor: pointer;
}

.vov-btn {
  font-size: 10px;
  font-weight: 700;
  padding: 5px 10px;
  cursor: pointer;
  transition: opacity 0.18s ease, border-color 0.18s ease;
}

.vov-btn.loading,
.vov-btn:disabled {
  opacity: 0.55;
  cursor: wait;
}

.vov-btn:not(:disabled):hover,
.vov-select:hover {
  border-color: #38bdf8;
}

.vov-error {
  width: 100%;
  color: #fda4af;
  font-size: 10px;
}

.vov-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  min-height: 160px;
  padding: 24px;
  border: 1px dashed rgba(96, 125, 139, 0.28);
  border-radius: 16px;
  color: #607d8b;
  font-size: 11px;
  text-align: center;
}

.vov-score-card {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr);
  gap: 16px;
  align-items: center;
  padding: 16px;
  flex-shrink: 0;
}

.vov-score-ring {
  position: relative;
  width: 96px;
  height: 96px;
  margin: 0 auto;
  border-radius: 50%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.vov-score-ring::after {
  content: '';
  position: absolute;
  inset: 10px;
  border-radius: 50%;
  background: #0a0e14;
  box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.14);
}

.vov-score-value,
.vov-score-max {
  position: relative;
  z-index: 1;
}

.vov-score-value {
  font-size: 26px;
  font-weight: 800;
  line-height: 1;
  color: #f8fafc;
}

.vov-score-max {
  margin-top: 4px;
  font-size: 10px;
  color: #607d8b;
}

.vov-score-meta {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.vov-state-row,
.vov-latest-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.vov-state,
.vov-badge {
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.vov-state.hot,
.vov-badge.hot {
  background: rgba(239, 68, 68, 0.16);
  color: #fca5a5;
}

.vov-state.warm,
.vov-badge.warm {
  background: rgba(245, 158, 11, 0.16);
  color: #fcd34d;
}

.vov-state.neutral,
.vov-badge.neutral {
  background: rgba(56, 189, 248, 0.14);
  color: #7dd3fc;
}

.vov-state.cool,
.vov-badge.cool {
  background: rgba(34, 197, 94, 0.14);
  color: #86efac;
}

.vov-reading {
  font-size: 11px;
  line-height: 1.45;
  color: #dbe4ee;
}

.vov-latest-row {
  font-size: 10px;
  color: #94a3b8;
}

.vov-chart-card {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  padding: 14px;
  gap: 12px;
}

.vov-chart-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.vov-chart-copy {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.vov-chart-title {
  font-size: 11px;
  font-weight: 700;
  color: #dbe4ee;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.vov-chart-subtitle {
  font-size: 10px;
  color: #7d8ea3;
}

.vov-hover-panel {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
  max-width: 52%;
}

.vov-hover-label,
.vov-hover-chip {
  padding: 4px 8px;
  border-radius: 999px;
  font-size: 10px;
  white-space: nowrap;
}

.vov-hover-label {
  border: 1px solid rgba(56, 189, 248, 0.18);
  background: rgba(56, 189, 248, 0.08);
  color: #7dd3fc;
}

.vov-hover-chip {
  border: 1px solid rgba(30, 43, 56, 0.95);
  background: rgba(13, 22, 32, 0.96);
  color: #dbe4ee;
}

.vov-chart-wrap {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  border: 1px solid rgba(30, 43, 56, 0.95);
  border-radius: 14px;
  background:
    linear-gradient(180deg, rgba(56, 189, 248, 0.05) 0%, rgba(8, 14, 21, 0) 30%),
    #09111a;
}

.vov-chart-wrap canvas {
  display: block;
  width: 100%;
  height: 100%;
  min-height: 220px;
  background: transparent;
  cursor: crosshair;
}

.vov-tooltip {
  position: absolute;
  z-index: 2;
  min-width: 156px;
  padding: 10px 12px;
  border: 1px solid rgba(56, 189, 248, 0.28);
  border-radius: 12px;
  background: rgba(8, 15, 24, 0.96);
  box-shadow: 0 12px 30px rgba(0, 0, 0, 0.3);
  pointer-events: none;
}

.vov-tooltip-time {
  font-size: 10px;
  color: #94a3b8;
}

.vov-tooltip-value {
  margin-top: 4px;
  font-size: 15px;
  font-weight: 700;
  color: #e0f2fe;
}

.vov-tooltip-meta {
  margin-top: 4px;
  font-size: 10px;
  color: #7dd3fc;
}

.vov-footer {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 0 4px;
  color: #607d8b;
  font-size: 10px;
  flex-shrink: 0;
}

@media (max-width: 720px) {
  .vov-score-card {
    grid-template-columns: 1fr;
  }

  .vov-header,
  .vov-footer,
  .vov-chart-head {
    flex-wrap: wrap;
  }

  .vov-controls {
    width: 100%;
    margin-left: 0;
    justify-content: flex-end;
  }

  .vov-chart-wrap canvas {
    min-height: 200px;
  }

  .vov-hover-panel {
    max-width: 100%;
    justify-content: flex-start;
  }
}
</style>

<template>
  <div class="pcr-root">

    <!-- ── Header ───────────────────────────────────────────────────────────── -->
    <div class="pcr-header">
      <span class="pcr-title">PCR — Put/Call Ratio</span>
      <div class="h-spacer"/>
      <span class="pcr-badge" v-if="!loading && validEvents.length">{{ validEvents.length }} ev</span>
      <span class="pcr-stale" v-if="!loading && isStaleData" :title="`Dados de ${dataDate} (sessão anterior)`">
        ⚠ {{ dataDate }}
      </span>
      <select class="pcr-sel" v-model="binMin">
        <option :value="5">5min</option>
        <option :value="15">15min</option>
        <option :value="30">30min</option>
      </select>
      <span class="pcr-loading" v-if="loading || backfilling">{{ backfilling ? 'Backfill…' : '…' }}</span>
      <span class="pcr-err"     v-if="errMsg && !loading && !backfilling">{{ errMsg }}</span>
      <button class="pcr-btn pcr-backfill" v-if="isStaleData && !backfilling"
              @click="runBackfill" title="Reconstruir dados de hoje via poll">⟳</button>
      <button class="pcr-btn"   @click="reload">↺</button>
    </div>

    <!-- ── PCR Matrix ─────────────────────────────────────────────────────────── -->
    <div class="pcr-matrix">
      <div class="pm-row">
        <div class="pm-cell corner"></div>
        <div class="pm-cell hdr" v-for="d in DU_VALS" :key="d">≤{{ d }}du</div>
      </div>
      <div class="pm-row" v-for="m in MONO_KEYS" :key="m">
        <div class="pm-cell mono-lbl">{{ MONO_LABELS[m] }}</div>
        <div v-for="d in DU_VALS" :key="d"
             class="pm-cell pcr-val"
             :class="[pcrColorClass(getPcr(m, d)), { 'series-on': visibleSeries.has(`${m}-${d}`) }]"
             :title="`${MONO_LABELS[m]} ≤${d}du  PCR=${fmtPcr(getPcr(m, d))}  vol=${fmtVol(getVol(m, d))}`"
             @click="toggleSeries(`${m}-${d}`)">
          <div class="pcr-cell-body">
            <span class="pcr-num">{{ fmtPcr(getPcr(m, d)) }}</span>
            <span class="pcr-vol">{{ fmtVol(getVol(m, d)) }}</span>
          </div>
          <span class="pcr-dot" :style="{ background: SERIES_COLORS[`${m}-${d}`] }"></span>
        </div>
      </div>
    </div>

    <!-- ── Series toggles ────────────────────────────────────────────────────── -->
    <div class="pcr-legend">
      <div class="pcr-leg-group" v-for="m in MONO_KEYS" :key="m">
        <span class="pcr-leg-lbl">{{ MONO_LABELS[m] }}</span>
        <button v-for="d in DU_VALS" :key="d"
                class="pcr-leg-btn"
                :class="{ on: visibleSeries.has(`${m}-${d}`) }"
                :style="{ '--lc': SERIES_COLORS[`${m}-${d}`] }"
                @click="toggleSeries(`${m}-${d}`)">{{ d }}du</button>
      </div>
      <button class="pcr-leg-util" style="margin-left:auto" @click="selectDefaultSeries">padrão</button>
      <button class="pcr-leg-util" @click="clearSeries">✕</button>
    </div>

    <!-- ── Time-evolution chart ───────────────────────────────────────────────── -->
    <div class="pcr-chart-wrap" ref="wrapEl">
      <canvas ref="canvasEl" class="pcr-canvas"
              @mousemove="onMouseMove"
              @mouseleave="onMouseLeave"/>

      <!-- Hover tooltip -->
      <div v-if="tooltip.visible"
           class="pcr-tooltip"
           :style="{ left: tooltip.x + 'px', top: tooltip.y + 'px' }">
        <div class="pcr-tt-time">{{ tooltip.time }}</div>
        <div v-for="row in tooltip.rows" :key="row.key" class="pcr-tt-row">
          <span class="pcr-tt-swatch" :style="{ background: row.color }"></span>
          <span class="pcr-tt-lbl">{{ row.label }}</span>
          <span class="pcr-tt-val" :style="{ color: row.color }">{{ row.pcr }}</span>
        </div>
        <div class="pcr-tt-sep" v-if="tooltip.rows.length"/>
        <div class="pcr-tt-neutral">ref&nbsp;<span>1.00</span></div>
      </div>

      <div class="pcr-empty" v-if="!loading && !validEvents.length">
        {{ errMsg || 'Sem dados de fluxo para hoje' }}
      </div>
      <div class="pcr-no-series" v-else-if="!loading && validEvents.length && !chartSeries.length">
        Selecione séries acima para visualizar a evolução do PCR
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { getVolumeActivity, backfillVolumeActivity } from '@/api/options'

const props = defineProps({ modelData: { type: Object, default: null } })

// ─── Constants ────────────────────────────────────────────────────────────────
const DU_VALS    = [1, 5, 15, 30, 60]
const MONO_KEYS  = ['atm', 'near', 'mid']
const MONO_LABELS = { atm: 'ATM', near: 'Near', mid: 'Mid' }

const SERIES_COLORS = {
  'atm-1':   '#c4b5fd',
  'atm-5':   '#a78bfa',
  'atm-15':  '#8b5cf6',
  'atm-30':  '#7c3aed',
  'atm-60':  '#5b21b6',
  'near-1':  '#6ee7b7',
  'near-5':  '#34d399',
  'near-15': '#10b981',
  'near-30': '#059669',
  'near-60': '#047857',
  'mid-1':   '#fde68a',
  'mid-5':   '#fcd34d',
  'mid-15':  '#fbbf24',
  'mid-30':  '#f59e0b',
  'mid-60':  '#d97706',
}

const ALL_SERIES = Object.keys(SERIES_COLORS).map(key => {
  const [mono, duStr] = key.split('-')
  return { key, mono, du: +duStr, color: SERIES_COLORS[key] }
})

const DEFAULT_VISIBLE = new Set(['atm-5', 'atm-15', 'atm-30', 'near-15', 'near-30'])

const PAD_L = 44, PAD_R = 14, PAD_T = 14, PAD_B = 24

// ─── State ────────────────────────────────────────────────────────────────────
const loading       = ref(false)
const backfilling   = ref(false)
const errMsg        = ref('')
const events        = ref([])
const dataDate      = ref('')   // session date of the returned dataset
const binMin        = ref(15)
const visibleSeries = ref(new Set(DEFAULT_VISIBLE))

const wrapEl   = ref(null)
const canvasEl = ref(null)
let cw = 600, ch = 260
let animFrame    = null
let refreshTimer = null
let ro           = null
const REFRESH_MS = 15_000

function handleVisibilityRefresh() {
  if (document.visibilityState === 'visible') reload()
}

function handleWindowFocus() {
  reload()
}

// Render state for mouse hit-testing (set every frame)
let _rs = null       // { tsMin, tsRange, areaX, areaW, areaH, pcrMin, pcrRange }
let _hoverX = null

// Tooltip
const tooltip = ref({ visible: false, x: 0, y: 0, time: '', rows: [] })

// ─── Underlying ───────────────────────────────────────────────────────────────
const underlying = computed(() => props.modelData?.underlying_security || 'IBOVE Index')

// Today in BRT (UTC-3)
function todayBRT() {
  const d = new Date(Date.now() - 3 * 3600_000)
  return d.toISOString().slice(0, 10)
}

// ─── Load data ────────────────────────────────────────────────────────────────
async function reload() {
  loading.value = true
  errMsg.value  = ''
  try {
    const res  = await getVolumeActivity({
      underlying_security: underlying.value,
      limit: 6000
    })
    const data = res?.data?.data ?? res?.data ?? []
    const arr  = Array.isArray(data) ? data : []
    events.value = arr
    dataDate.value = arr.length ? (arr[0].session_date || arr[0].captured_at?.slice(0, 10) || '') : ''
  } catch (e) {
    errMsg.value = e?.message || 'Erro ao carregar'
    console.error('[PCRWidget]', e)
  } finally {
    loading.value = false
  }
}

const isStaleData = computed(() => dataDate.value && dataDate.value < todayBRT())

async function runBackfill() {
  backfilling.value = true
  errMsg.value = ''
  try {
    await backfillVolumeActivity()
    await new Promise(r => setTimeout(r, 2000))
    await reload()
  } catch (e) {
    errMsg.value = e?.message || 'Erro no backfill'
  } finally {
    backfilling.value = false
  }
}

// ─── Pre-process events ───────────────────────────────────────────────────────
const validEvents = computed(() => {
  return events.value
    .filter(e => {
      const ts  = new Date(e.captured_at).getTime()
      const vol = +(e.volume_delta) || 0
      const pc  = String(e.put_call || '').toUpperCase()
      return isFinite(ts) && vol > 0 && (pc === 'C' || pc === 'P')
    })
    .map(e => {
      const spot = +e.spot_price || 0
      return {
        ts:  new Date(e.captured_at).getTime(),
        vol: +(e.volume_delta),
        pc:  String(e.put_call || '').toUpperCase(),
        am:  spot > 0 ? Math.abs((+e.strike - spot) / spot) : 999,
        dtm: +e.days_to_maturity || 999,
      }
    })
    .sort((a, b) => a.ts - b.ts)
})

// ─── Moneyness filter ─────────────────────────────────────────────────────────
function matchMono(e, mono) {
  if (mono === 'atm')  return e.am <= 0.015
  if (mono === 'near') return e.am <= 0.04
  if (mono === 'mid')  return e.am > 0.04 && e.am <= 0.12
  return true
}

// ─── PCR matrix ───────────────────────────────────────────────────────────────
const pcrMatrix = computed(() => {
  const m = {}
  for (const mono of MONO_KEYS)
    for (const du of DU_VALS)
      m[`${mono}-${du}`] = { calls: 0, puts: 0 }

  for (const e of validEvents.value) {
    for (const mono of MONO_KEYS) {
      if (!matchMono(e, mono)) continue
      for (const du of DU_VALS) {
        if (e.dtm > du) continue
        const b = m[`${mono}-${du}`]
        if (e.pc === 'C') b.calls += e.vol
        else              b.puts  += e.vol
      }
    }
  }
  const out = {}
  for (const k of Object.keys(m)) {
    const { calls, puts } = m[k]
    out[k] = { pcr: calls > 0 ? puts / calls : null, vol: calls + puts, calls, puts }
  }
  return out
})

function getPcr(mono, du)  { return pcrMatrix.value[`${mono}-${du}`]?.pcr ?? null }
function getVol(mono, du)  { return pcrMatrix.value[`${mono}-${du}`]?.vol ?? 0 }
function fmtPcr(v)         { return (v == null) ? '—' : v.toFixed(2) }
function fmtVol(v) {
  if (!v || !isFinite(v)) return ''
  const a = Math.abs(v)
  if (a >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`
  if (a >= 1_000)     return `${(v / 1_000).toFixed(0)}k`
  return String(Math.round(v))
}

function pcrColorClass(v) {
  if (v == null)    return 'pcr-nil'
  if (v < 0.70)    return 'pcr-strong-call'
  if (v < 0.90)    return 'pcr-call'
  if (v < 1.10)    return 'pcr-neutral'
  if (v < 1.35)    return 'pcr-put'
  return 'pcr-strong-put'
}

// ─── Series visibility ────────────────────────────────────────────────────────
function toggleSeries(key) {
  const s = new Set(visibleSeries.value)
  s.has(key) ? s.delete(key) : s.add(key)
  visibleSeries.value = s
}
function clearSeries()         { visibleSeries.value = new Set() }
function selectDefaultSeries() { visibleSeries.value = new Set(DEFAULT_VISIBLE) }

// ─── Chart series (cumulative PCR per bin) ────────────────────────────────────
const chartSeries = computed(() => {
  const binMs = binMin.value * 60_000
  return ALL_SERIES
    .filter(s => visibleSeries.value.has(s.key))
    .map(s => {
      const evs = validEvents.value.filter(e => matchMono(e, s.mono) && e.dtm <= s.du)
      if (!evs.length) return null

      const map = new Map()
      for (const e of evs) {
        const key = Math.floor(e.ts / binMs) * binMs
        if (!map.has(key)) map.set(key, { ts: key, calls: 0, puts: 0 })
        const b = map.get(key)
        if (e.pc === 'C') b.calls += e.vol
        else              b.puts  += e.vol
      }
      const sorted = [...map.values()].sort((a, b) => a.ts - b.ts)

      let cumCalls = 0, cumPuts = 0
      const points = sorted.map(b => {
        cumCalls += b.calls
        cumPuts  += b.puts
        return { ts: b.ts + binMs, pcr: cumCalls > 0 ? cumPuts / cumCalls : null }
      }).filter(p => p.pcr !== null)

      return points.length ? { ...s, points } : null
    })
    .filter(Boolean)
})

// ─── Mouse hover ─────────────────────────────────────────────────────────────
const BRT_OFF = -3 * 3_600_000

function onMouseMove(e) {
  const canvas = canvasEl.value
  if (!canvas || !_rs) return
  const rect = canvas.getBoundingClientRect()
  const mx = e.clientX - rect.left
  const { tsMin, tsRange, areaX, areaW } = _rs

  if (mx < areaX || mx > areaX + areaW) {
    if (tooltip.value.visible) { tooltip.value = { ...tooltip.value, visible: false }; _hoverX = null; scheduleRender() }
    return
  }

  const hoveredTs = tsMin + ((mx - areaX) / areaW) * tsRange
  _hoverX = mx

  // Find last known PCR for each series at or before hoveredTs
  const rows = chartSeries.value.map(s => {
    let nearest = null
    for (const p of s.points) {
      if (p.ts <= hoveredTs) nearest = p
      else break
    }
    if (!nearest && s.points.length) nearest = s.points[0]
    if (!nearest) return null
    return {
      key:   s.key,
      color: s.color,
      label: `${MONO_LABELS[s.mono]} ${s.du}du`,
      pcr:   fmtPcr(nearest.pcr),
      pcrVal: nearest.pcr,
    }
  }).filter(Boolean)

  // Sort rows by PCR descending for readability
  rows.sort((a, b) => b.pcrVal - a.pcrVal)

  const d   = new Date(hoveredTs + BRT_OFF)
  const hh  = String(d.getUTCHours()).padStart(2, '0')
  const mm  = String(d.getUTCMinutes()).padStart(2, '0')
  const time = `${hh}:${mm}`

  // Position tooltip — avoid right/bottom overflow
  const wrap = wrapEl.value
  if (!wrap) return
  const wRect = wrap.getBoundingClientRect()
  const TT_W = 150, TT_H = rows.length * 20 + 44
  let tx = e.clientX - wRect.left + 16
  let ty = e.clientY - wRect.top  - 16
  if (tx + TT_W > wRect.width  - 6) tx = e.clientX - wRect.left - TT_W - 10
  if (ty + TT_H > wRect.height - 6) ty = wRect.height - TT_H - 6
  ty = Math.max(6, ty)

  tooltip.value = { visible: true, x: tx, y: ty, time, rows }
  scheduleRender()
}

function onMouseLeave() {
  if (tooltip.value.visible || _hoverX !== null) {
    tooltip.value = { ...tooltip.value, visible: false }
    _hoverX = null
    scheduleRender()
  }
}

// ─── Canvas sizing ────────────────────────────────────────────────────────────
function syncSize() {
  const wrap = wrapEl.value, c = canvasEl.value
  if (!wrap || !c) return
  const w = wrap.clientWidth, h = wrap.clientHeight
  if (w < 10 || h < 10) return
  const dpr = window.devicePixelRatio || 1
  c.width  = w * dpr; c.height = h * dpr
  c.style.width = w + 'px'; c.style.height = h + 'px'
  c.getContext('2d').scale(dpr, dpr)
  cw = w; ch = h
  scheduleRender()
}

function scheduleRender() {
  if (animFrame) cancelAnimationFrame(animFrame)
  animFrame = requestAnimationFrame(render)
}

// ─── Canvas helper: rounded rect ─────────────────────────────────────────────
function rrect(ctx, x, y, w, h, r) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.lineTo(x + w - r, y)
  ctx.quadraticCurveTo(x + w, y, x + w, y + r)
  ctx.lineTo(x + w, y + h - r)
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h)
  ctx.lineTo(x + r, y + h)
  ctx.quadraticCurveTo(x, y + h, x, y + h - r)
  ctx.lineTo(x, y + r)
  ctx.quadraticCurveTo(x, y, x + r, y)
  ctx.closePath()
}

// ─── Render ───────────────────────────────────────────────────────────────────
function render() {
  const canvas = canvasEl.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  ctx.clearRect(0, 0, cw, ch)

  const series = chartSeries.value
  if (!series.length) { _rs = null; return }

  const areaX = PAD_L
  const areaW = cw - PAD_L - PAD_R
  const areaH = ch - PAD_T - PAD_B
  if (areaW < 20 || areaH < 20) return

  // ── X range ───────────────────────────────────────────────────────────────
  let tsMin = Infinity, tsMax = -Infinity
  for (const s of series)
    for (const p of s.points) {
      if (p.ts < tsMin) tsMin = p.ts
      if (p.ts > tsMax) tsMax = p.ts
    }
  if (!isFinite(tsMin)) return
  const tsRange = tsMax - tsMin || 1

  // ── Y range — always include 1.0, symmetry hint ────────────────────────
  let pcrMin = 1, pcrMax = 1
  for (const s of series)
    for (const p of s.points) {
      if (p.pcr < pcrMin) pcrMin = p.pcr
      if (p.pcr > pcrMax) pcrMax = p.pcr
    }
  pcrMin = Math.max(0, pcrMin - 0.06)
  pcrMax = pcrMax + 0.06
  const pcrRange = pcrMax - pcrMin || 1

  // Save for hit-testing
  _rs = { tsMin, tsRange, areaX, areaW, areaH, pcrMin, pcrRange }

  const tsToX  = ts => areaX + ((ts - tsMin) / tsRange) * areaW
  const pcrToY = v  => PAD_T + areaH - ((v - pcrMin) / pcrRange) * areaH

  // ── Background tints ──────────────────────────────────────────────────
  const yRef = pcrToY(1)
  if (yRef > PAD_T) {
    ctx.fillStyle = 'rgba(239,68,68,0.04)'
    ctx.fillRect(areaX, PAD_T, areaW, Math.min(yRef, PAD_T + areaH) - PAD_T)
  }
  if (yRef < PAD_T + areaH) {
    ctx.fillStyle = 'rgba(34,197,94,0.04)'
    ctx.fillRect(areaX, Math.max(yRef, PAD_T), areaW, PAD_T + areaH - Math.max(yRef, PAD_T))
  }

  // ── Y grid ────────────────────────────────────────────────────────────
  const step = pcrRange <= 0.3 ? 0.05 : pcrRange <= 0.8 ? 0.10 : pcrRange <= 1.5 ? 0.25 : 0.50
  const yTicks = []
  for (let v = Math.ceil(pcrMin / step) * step; v <= pcrMax + 1e-9; v += step)
    yTicks.push(Math.round(v * 1000) / 1000)

  ctx.save()
  ctx.strokeStyle = 'rgba(148,163,184,0.07)'
  ctx.lineWidth   = 1
  ctx.setLineDash([3, 5])
  for (const v of yTicks) {
    const y = pcrToY(v)
    if (y < PAD_T || y > PAD_T + areaH) continue
    ctx.beginPath(); ctx.moveTo(areaX, y); ctx.lineTo(areaX + areaW, y); ctx.stroke()
  }
  ctx.setLineDash([])
  ctx.restore()

  // ── PCR = 1.0 reference ───────────────────────────────────────────────
  if (yRef >= PAD_T && yRef <= PAD_T + areaH) {
    ctx.save()
    ctx.strokeStyle = 'rgba(148,163,184,0.35)'
    ctx.lineWidth   = 1
    ctx.setLineDash([5, 4])
    ctx.beginPath(); ctx.moveTo(areaX, yRef); ctx.lineTo(areaX + areaW, yRef); ctx.stroke()
    ctx.setLineDash([])
    ctx.restore()
  }

  // ── Series polylines ──────────────────────────────────────────────────
  for (const s of series) {
    if (!s.points.length) continue
    ctx.save()
    ctx.strokeStyle = s.color
    ctx.lineWidth   = 1.8
    ctx.lineJoin    = 'round'
    ctx.beginPath()
    let first = true
    for (const p of s.points) {
      const x = tsToX(p.ts), y = pcrToY(p.pcr)
      first ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
      first = false
    }
    ctx.stroke()
    // Endpoint dot only (no label)
    const last = s.points[s.points.length - 1]
    ctx.fillStyle = s.color
    ctx.beginPath()
    ctx.arc(tsToX(last.ts), pcrToY(last.pcr), 2.5, 0, Math.PI * 2)
    ctx.fill()
    ctx.restore()
  }

  // ── Hover crosshair + dots ────────────────────────────────────────────
  if (_hoverX !== null && _hoverX >= areaX && _hoverX <= areaX + areaW) {
    const hovTs = tsMin + ((_hoverX - areaX) / areaW) * tsRange
    // Vertical line
    ctx.save()
    ctx.strokeStyle = 'rgba(148,163,184,0.40)'
    ctx.lineWidth   = 1
    ctx.setLineDash([3, 3])
    ctx.beginPath(); ctx.moveTo(_hoverX, PAD_T); ctx.lineTo(_hoverX, ch - PAD_B); ctx.stroke()
    ctx.setLineDash([])
    // Intersection dots
    for (const s of series) {
      let nearest = null
      for (const p of s.points) { if (p.ts <= hovTs) nearest = p; else break }
      if (!nearest && s.points.length) nearest = s.points[0]
      if (!nearest) continue
      const y = pcrToY(nearest.pcr)
      ctx.fillStyle   = '#060c18'
      ctx.strokeStyle = s.color
      ctx.lineWidth   = 1.5
      ctx.beginPath(); ctx.arc(_hoverX, y, 4, 0, Math.PI * 2)
      ctx.fill(); ctx.stroke()
    }
    ctx.restore()
  }

  // ── Y-axis strip ──────────────────────────────────────────────────────
  ctx.save()
  ctx.fillStyle = 'rgba(6,12,24,0.90)'
  ctx.fillRect(0, 0, PAD_L, ch)
  ctx.strokeStyle = 'rgba(148,163,184,0.16)'
  ctx.lineWidth   = 1
  ctx.beginPath(); ctx.moveTo(PAD_L, PAD_T); ctx.lineTo(PAD_L, ch - PAD_B); ctx.stroke()

  ctx.font      = '9px monospace'
  ctx.textAlign = 'right'
  for (const v of yTicks) {
    const y = pcrToY(v)
    if (y < PAD_T || y > PAD_T + areaH) continue
    ctx.strokeStyle = 'rgba(148,163,184,0.18)'; ctx.lineWidth = 1
    ctx.beginPath(); ctx.moveTo(PAD_L - 3, y); ctx.lineTo(PAD_L, y); ctx.stroke()
    const isRef = Math.abs(v - 1.0) < step * 0.4
    ctx.fillStyle = isRef ? 'rgba(148,163,184,0.90)' : 'rgba(148,163,184,0.50)'
    ctx.font = isRef ? 'bold 9px monospace' : '9px monospace'
    ctx.fillText(v.toFixed(2), PAD_L - 5, y + 3)
  }
  ctx.restore()

  // ── X-axis strip ──────────────────────────────────────────────────────
  ctx.save()
  ctx.fillStyle = 'rgba(6,12,24,0.90)'
  ctx.fillRect(0, ch - PAD_B, cw, PAD_B)
  ctx.strokeStyle = 'rgba(148,163,184,0.16)'
  ctx.lineWidth   = 1
  ctx.beginPath(); ctx.moveTo(areaX, ch - PAD_B); ctx.lineTo(areaX + areaW, ch - PAD_B); ctx.stroke()

  ctx.font      = '9px monospace'
  ctx.textAlign = 'center'
  ctx.fillStyle = 'rgba(148,163,184,0.55)'

  const tickMs = tsRange < 2 * 3_600_000 ? 30 * 60_000
               : tsRange < 8 * 3_600_000 ? 60 * 60_000
               : 2 * 3_600_000
  const firstTick = Math.ceil(tsMin / tickMs) * tickMs
  for (let ts = firstTick; ts <= tsMax; ts += tickMs) {
    const x = tsToX(ts)
    if (x < areaX + 14 || x > areaX + areaW - 6) continue
    const d  = new Date(ts + BRT_OFF)
    const lbl = `${String(d.getUTCHours()).padStart(2,'0')}:${String(d.getUTCMinutes()).padStart(2,'0')}`
    ctx.strokeStyle = 'rgba(148,163,184,0.10)'; ctx.lineWidth = 1
    ctx.setLineDash([2, 4])
    ctx.beginPath(); ctx.moveTo(x, PAD_T); ctx.lineTo(x, ch - PAD_B); ctx.stroke()
    ctx.setLineDash([])
    ctx.beginPath(); ctx.moveTo(x, ch - PAD_B); ctx.lineTo(x, ch - PAD_B + 3); ctx.stroke()
    ctx.fillText(lbl, x, ch - PAD_B + 14)
  }
  ctx.restore()

  // ── Compact legend panel (top-right corner) ───────────────────────────
  drawLegend(ctx, series, areaX, areaW)
}

// ─── In-canvas legend ────────────────────────────────────────────────────────
function drawLegend(ctx, series, areaX, areaW) {
  if (!series.length) return
  const LPAD  = 7
  const LROW  = 15
  const SW    = 18   // swatch width (small colored line)
  const GAP   = 5
  // Measure widest label to set panel width
  ctx.save()
  ctx.font = '9px monospace'
  let maxLblW = 0
  for (const s of series) {
    const lbl = `${MONO_LABELS[s.mono]} ${s.du}du`
    const w   = ctx.measureText(lbl).width
    if (w > maxLblW) maxLblW = w
  }
  const VAL_W  = ctx.measureText('0.00').width + 4
  const panelW = LPAD + SW + GAP + maxLblW + GAP + VAL_W + LPAD
  const panelH = series.length * LROW + LPAD * 2

  const lx = areaX + areaW - panelW - 4
  const ly = PAD_T + 4

  // Panel background
  rrect(ctx, lx, ly, panelW, panelH, 4)
  ctx.fillStyle   = 'rgba(6,12,24,0.82)'
  ctx.fill()
  ctx.strokeStyle = 'rgba(148,163,184,0.12)'
  ctx.lineWidth   = 1
  ctx.stroke()

  // Rows
  for (let i = 0; i < series.length; i++) {
    const s    = series[i]
    const ry   = ly + LPAD + i * LROW
    const midY = ry + LROW / 2 - 1

    // Color swatch (short line)
    ctx.strokeStyle = s.color
    ctx.lineWidth   = 2
    ctx.beginPath(); ctx.moveTo(lx + LPAD, midY); ctx.lineTo(lx + LPAD + SW, midY); ctx.stroke()

    // Series label
    const lbl = `${MONO_LABELS[s.mono]} ${s.du}du`
    ctx.font      = '9px monospace'
    ctx.textAlign = 'left'
    ctx.fillStyle = 'rgba(148,163,184,0.65)'
    ctx.fillText(lbl, lx + LPAD + SW + GAP, midY + 3)

    // Current PCR value
    const last = s.points[s.points.length - 1]
    ctx.font      = 'bold 9px monospace'
    ctx.textAlign = 'right'
    ctx.fillStyle = s.color
    ctx.fillText(fmtPcr(last.pcr), lx + panelW - LPAD, midY + 3)
  }
  ctx.restore()
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────
onMounted(async () => {
  await nextTick()
  ro = new ResizeObserver(syncSize)
  if (wrapEl.value) ro.observe(wrapEl.value)
  syncSize()
  await reload()
  refreshTimer = setInterval(reload, REFRESH_MS)
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', handleVisibilityRefresh)
  }
  if (typeof window !== 'undefined') {
    window.addEventListener('focus', handleWindowFocus)
  }
})

onUnmounted(() => {
  if (animFrame)    cancelAnimationFrame(animFrame)
  if (refreshTimer) clearInterval(refreshTimer)
  if (ro)           ro.disconnect()
  if (typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', handleVisibilityRefresh)
  }
  if (typeof window !== 'undefined') {
    window.removeEventListener('focus', handleWindowFocus)
  }
})

watch(chartSeries, scheduleRender, { deep: false })
watch(binMin,      scheduleRender)
watch(underlying,  () => reload())
</script>

<style scoped>
/* ─── Root ─────────────────────────────────────────────────────────────────── */
.pcr-root {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #060c18;
  color: #e2e8f0;
  font-family: "JetBrains Mono", monospace;
  overflow: hidden;
  user-select: none;
}

/* ─── Header ──────────────────────────────────────────────────────────────── */
.pcr-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border-bottom: 1px solid rgba(148,163,184,0.10);
  flex-shrink: 0;
  font-size: 11px;
}
.pcr-title   { font-weight: 700; color: #94a3b8; letter-spacing: .04em; }
.h-spacer    { flex: 1; }
.pcr-badge   { font-size: 9px; color: #475569; }
.pcr-loading  { color: #64748b; }
.pcr-err      { color: #f87171; font-size: 9px; }
.pcr-stale    { font-size: 9px; color: #f59e0b; font-weight: 700; }
.pcr-backfill { color: #fbbf24; border-color: rgba(251,191,36,0.35); }
.pcr-backfill:hover { background: rgba(251,191,36,0.10); }
.pcr-sel {
  background: rgba(148,163,184,0.08);
  border: 1px solid rgba(148,163,184,0.14);
  border-radius: 4px;
  color: #cbd5e1;
  font-size: 10px;
  font-family: inherit;
  padding: 1px 4px;
  cursor: pointer;
}
.pcr-btn {
  background: rgba(148,163,184,0.08);
  border: 1px solid rgba(148,163,184,0.14);
  border-radius: 4px;
  color: #94a3b8;
  cursor: pointer;
  font-size: 11px;
  padding: 1px 7px;
  font-family: inherit;
}
.pcr-btn:hover { background: rgba(148,163,184,0.16); }

/* ─── Matrix ──────────────────────────────────────────────────────────────── */
.pcr-matrix {
  flex-shrink: 0;
  padding: 7px 10px 4px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.pm-row {
  display: grid;
  grid-template-columns: 42px repeat(5, 1fr);
  gap: 3px;
}
.pm-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  font-size: 10px;
  padding: 5px 2px;
}
.pm-cell.hdr {
  background: rgba(148,163,184,0.06);
  color: #475569;
  font-weight: 600;
  font-size: 9px;
}
.pm-cell.mono-lbl {
  font-weight: 700;
  color: #94a3b8;
  justify-content: flex-end;
  padding-right: 6px;
}
.pm-cell.pcr-val {
  cursor: pointer;
  gap: 4px;
  border: 1px solid transparent;
  transition: filter 0.12s, border-color 0.12s;
}
.pm-cell.pcr-val:hover     { filter: brightness(1.25); }
.pm-cell.pcr-val.series-on { border-color: rgba(255,255,255,0.20); }

.pcr-cell-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  line-height: 1;
}
.pcr-num { font-weight: 700; font-size: 11px; }
.pcr-vol {
  font-size: 8px;
  font-weight: 400;
  color: rgba(148,163,184,0.42);
  letter-spacing: 0;
}
.pcr-dot { width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0; opacity: 0.70; }

.pcr-nil           { background: rgba(148,163,184,0.06); }
.pcr-nil .pcr-num  { color: #475569; }
.pcr-strong-call           { background: rgba(34,197,94,0.18); }
.pcr-strong-call .pcr-num  { color: #4ade80; }
.pcr-call           { background: rgba(34,197,94,0.09); }
.pcr-call .pcr-num  { color: #86efac; }
.pcr-neutral           { background: rgba(148,163,184,0.09); }
.pcr-neutral .pcr-num  { color: #cbd5e1; }
.pcr-put           { background: rgba(239,68,68,0.10); }
.pcr-put .pcr-num  { color: #fca5a5; }
.pcr-strong-put           { background: rgba(239,68,68,0.22); }
.pcr-strong-put .pcr-num  { color: #f87171; }

/* ─── Series toggles ──────────────────────────────────────────────────────── */
.pcr-legend {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 10px;
  border-top: 1px solid rgba(148,163,184,0.07);
  border-bottom: 1px solid rgba(148,163,184,0.07);
  flex-shrink: 0;
  overflow-x: auto;
}
.pcr-leg-group { display: flex; align-items: center; gap: 3px; flex-shrink: 0; }
.pcr-leg-lbl   { font-size: 9px; color: #475569; font-weight: 700; min-width: 28px; }
.pcr-leg-btn {
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 9px;
  font-family: inherit;
  cursor: pointer;
  border: 1px solid rgba(148,163,184,0.14);
  background: rgba(148,163,184,0.05);
  color: #64748b;
  transition: all 0.1s;
}
.pcr-leg-btn.on {
  background: color-mix(in srgb, var(--lc) 18%, transparent);
  border-color: var(--lc);
  color: var(--lc);
}
.pcr-leg-btn:hover { filter: brightness(1.3); }
.pcr-leg-util {
  padding: 1px 7px;
  border-radius: 3px;
  font-size: 9px;
  font-family: inherit;
  cursor: pointer;
  border: 1px solid rgba(148,163,184,0.14);
  background: rgba(148,163,184,0.05);
  color: #64748b;
  flex-shrink: 0;
}
.pcr-leg-util:hover { background: rgba(148,163,184,0.12); color: #94a3b8; }

/* ─── Chart ───────────────────────────────────────────────────────────────── */
.pcr-chart-wrap {
  flex: 1;
  position: relative;
  min-height: 0;
}
.pcr-canvas {
  display: block;
  width: 100%;
  height: 100%;
  cursor: crosshair;
}
.pcr-empty,
.pcr-no-series {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #475569;
  font-size: 11px;
  pointer-events: none;
  text-align: center;
  padding: 12px;
}

/* ─── Hover tooltip ───────────────────────────────────────────────────────── */
.pcr-tooltip {
  position: absolute;
  z-index: 10;
  pointer-events: none;
  background: rgba(8, 16, 32, 0.94);
  border: 1px solid rgba(148,163,184,0.18);
  border-radius: 6px;
  padding: 8px 10px;
  min-width: 130px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.55);
  backdrop-filter: blur(4px);
}
.pcr-tt-time {
  font-size: 10px;
  font-weight: 700;
  color: #94a3b8;
  margin-bottom: 6px;
  letter-spacing: .04em;
}
.pcr-tt-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  padding: 1px 0;
}
.pcr-tt-swatch {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.pcr-tt-lbl  { flex: 1; color: rgba(148,163,184,0.70); font-size: 9px; }
.pcr-tt-val  { font-weight: 700; font-size: 10px; font-family: inherit; }
.pcr-tt-sep  { border-top: 1px solid rgba(148,163,184,0.10); margin: 5px 0 3px; }
.pcr-tt-neutral {
  font-size: 9px;
  color: rgba(148,163,184,0.40);
  display: flex;
  justify-content: space-between;
}
.pcr-tt-neutral span { color: rgba(148,163,184,0.60); }
</style>

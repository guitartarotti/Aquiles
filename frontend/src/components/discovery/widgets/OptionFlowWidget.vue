<template>
  <div class="ofw-root">

    <!-- ── Controls ──────────────────────────────────────────────────────────── -->
    <div class="ofw-controls">

      <!-- Moneyness / expiry filter -->
      <button v-for="f in MONO_FILTERS" :key="f.key"
              class="ofw-btn" :class="{ active: monoFilter === f.key }"
              @click="monoFilter = f.key">{{ f.label }}</button>

      <div class="ofw-sep" />

      <!-- Side filter (call / put / both) -->
      <button v-for="s in SIDE_FILTERS" :key="s.key"
              class="ofw-btn sm" :class="{ active: sideFilter === s.key, [s.cls]: true }"
              @click="sideFilter = s.key">{{ s.label }}</button>

      <div class="ofw-sep" />

      <!-- Running totals -->
      <span class="ofw-pill call">C {{ fmtVol(totCalls) }}</span>
      <span class="ofw-pill put" >P {{ fmtVol(totPuts)  }}</span>
      <span class="ofw-pill net" :class="netFlow >= 0 ? 'pos' : 'neg'">
        {{ netFlow >= 0 ? '▲' : '▼' }}&nbsp;{{ fmtVol(Math.abs(netFlow)) }}
      </span>

      <div style="margin-left: auto" />

      <!-- Cumulative lines toggle -->
      <label class="ofw-chk"><input type="checkbox" v-model="showCum" /> Acum</label>

      <!-- Bin size selector -->
      <select class="ofw-sel" v-model="binMin">
        <option :value="5">5min</option>
        <option :value="15">15min</option>
        <option :value="30">30min</option>
      </select>

      <span class="ofw-info" v-if="!loading && events.length">
        {{ filteredEvents.length }}/{{ events.length }} ev.
      </span>
      <span class="ofw-stale" v-if="!loading && isStaleData" :title="`Dados de ${dataDate} (sessão anterior)`">
        ⚠ {{ dataDate }}
      </span>
      <span class="ofw-loading" v-if="loading || backfilling">{{ backfilling ? 'Backfill…' : 'Carregando…' }}</span>
      <span class="ofw-err"     v-if="errMsg && !loading && !backfilling">{{ errMsg }}</span>
      <button class="ofw-btn ofw-backfill" v-if="isStaleData && !backfilling"
              @click="runBackfill" title="Reconstruir dados de hoje via poll">⟳ Hoje</button>
      <button class="ofw-btn"   @click="reload">↺</button>
    </div>

    <!-- ── Chart ──────────────────────────────────────────────────────────────── -->
    <div class="ofw-wrap" ref="wrapEl">
      <canvas ref="canvasEl" class="ofw-canvas" />
      <div class="ofw-empty" v-if="!loading && !bins.length">
        {{ errMsg || 'Sem dados de fluxo para hoje' }}
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { getVolumeActivity, backfillVolumeActivity } from '@/api/options'

const props = defineProps({ modelData: { type: Object, default: null } })

// ─── Constants ────────────────────────────────────────────────────────────────
const PAD_L = 54, PAD_R = 8, PAD_T = 12, PAD_B = 26

const MONO_FILTERS = [
  { key: 'all',  label: 'Todas'  },
  { key: 'atm',  label: 'ATM'   },
  { key: 'near', label: 'Near'  },
  { key: 'mid',  label: 'Mid'   },
  { key: 'venc', label: '≤30d'  },
]
const SIDE_FILTERS = [
  { key: 'both', label: 'C+P',  cls: '' },
  { key: 'call', label: 'Call', cls: 'call' },
  { key: 'put',  label: 'Put',  cls: 'put'  },
]

// ─── State ────────────────────────────────────────────────────────────────────
const loading     = ref(false)
const backfilling = ref(false)
const errMsg      = ref('')
const events      = ref([])   // raw activity records
const dataDate    = ref('')   // date of the returned data (YYYY-MM-DD)

const monoFilter  = ref('all')
const sideFilter  = ref('both')
const showCum     = ref(true)
const binMin      = ref(15)   // minutes per bin

const wrapEl      = ref(null)
const canvasEl    = ref(null)
let cw = 600, ch = 320
let animFrame = null
let refreshTimer = null
const REFRESH_MS = 15_000

function handleVisibilityRefresh() {
  if (document.visibilityState === 'visible') reload()
}

function handleWindowFocus() {
  reload()
}

// ─── Underlying ───────────────────────────────────────────────────────────────
const underlying = computed(
  () => props.modelData?.underlying_security || 'IBOVE Index'
)

// ─── Load data ────────────────────────────────────────────────────────────────
// Today in BRT (UTC-3)
function todayBRT() {
  const d = new Date(Date.now() - 3 * 3600_000)
  return d.toISOString().slice(0, 10)
}

async function reload() {
  loading.value = true
  errMsg.value  = ''
  try {
    const res  = await getVolumeActivity({
      underlying_security: underlying.value,
      limit: 3000
    })
    const data = res?.data?.data ?? res?.data ?? []
    const arr  = Array.isArray(data) ? data : []
    events.value = arr
    // Detect the session date of the returned data
    dataDate.value = arr.length ? (arr[0].session_date || arr[0].captured_at?.slice(0, 10) || '') : ''
  } catch (e) {
    errMsg.value = e?.message || 'Erro ao carregar'
    console.error('[OptionFlow]', e)
  } finally {
    loading.value = false
  }
}

// Is the returned data from a previous session (not today BRT)?
const isStaleData = computed(() => dataDate.value && dataDate.value < todayBRT())

async function runBackfill() {
  backfilling.value = true
  errMsg.value = ''
  try {
    await backfillVolumeActivity()
    // Give tracker a moment to write the file, then reload
    await new Promise(r => setTimeout(r, 2000))
    await reload()
  } catch (e) {
    errMsg.value = e?.message || 'Erro no backfill'
  } finally {
    backfilling.value = false
  }
}

// ─── Filter events by moneyness / expiry ────────────────────────────────────
const filteredEvents = computed(() => {
  return events.value.filter(e => {
    // Moneyness filter
    const spot = +e.spot_price || 0
    const m    = spot > 0 ? (+e.strike - spot) / spot : 0
    const am   = Math.abs(m)
    switch (monoFilter.value) {
      case 'atm':  if (am > 0.015)  return false; break
      case 'near': if (am > 0.04)   return false; break
      case 'mid':  if (am <= 0.04 || am > 0.12) return false; break
      case 'venc': if ((+e.days_to_maturity || 999) > 30) return false; break
    }
    // Side filter
    const pc = String(e.put_call || '').toUpperCase()
    if (sideFilter.value === 'call' && pc !== 'C') return false
    if (sideFilter.value === 'put'  && pc !== 'P') return false
    // Only positive volume deltas
    if ((+e.volume_delta || 0) <= 0) return false
    return true
  })
})

// ─── Bin filtered events into time buckets ───────────────────────────────────
const bins = computed(() => {
  const MSBIN = binMin.value * 60 * 1000
  const map   = new Map()

  for (const e of filteredEvents.value) {
    const ts  = new Date(e.captured_at).getTime()
    if (!isFinite(ts)) continue
    const key = Math.floor(ts / MSBIN) * MSBIN
    if (!map.has(key)) map.set(key, { ts: key, callVol: 0, putVol: 0, n: 0 })
    const b   = map.get(key)
    const vol = +(e.volume_delta) || 0
    if (String(e.put_call || '').toUpperCase() === 'C') b.callVol += vol
    else                                                 b.putVol  += vol
    b.n++
  }
  return [...map.values()].sort((a, b) => a.ts - b.ts)
})

// ─── Aggregate totals ─────────────────────────────────────────────────────────
const totCalls = computed(() => bins.value.reduce((s, b) => s + b.callVol, 0))
const totPuts  = computed(() => bins.value.reduce((s, b) => s + b.putVol,  0))
const netFlow  = computed(() => totCalls.value - totPuts.value)

// ─── Render ───────────────────────────────────────────────────────────────────
function scheduleRender() {
  if (animFrame) cancelAnimationFrame(animFrame)
  animFrame = requestAnimationFrame(render)
}

function render() {
  const canvas = canvasEl.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  cw = canvas.width
  ch = canvas.height
  ctx.clearRect(0, 0, cw, ch)
  if (!bins.value.length) return

  const bList = bins.value
  const areaX = PAD_L
  const areaW = cw - PAD_L - PAD_R
  const areaH = ch - PAD_T - PAD_B
  const midY  = PAD_T + areaH / 2   // zero line

  // ── Scale: max per-bin volume (symmetric axis) ────────────────────────────
  const maxVol = Math.max(
    ...bList.map(b => Math.max(b.callVol, b.putVol)), 1
  )

  // ── Grid ──────────────────────────────────────────────────────────────────
  ctx.save()
  ctx.strokeStyle = 'rgba(148,163,184,0.08)'
  ctx.lineWidth   = 1
  ctx.setLineDash([3, 5])
  for (const frac of [0.25, 0.5, 0.75]) {
    const yUp   = midY - frac * (areaH / 2)
    const yDown = midY + frac * (areaH / 2)
    for (const y of [yUp, yDown]) {
      ctx.beginPath(); ctx.moveTo(areaX, y); ctx.lineTo(areaX + areaW, y); ctx.stroke()
    }
  }
  ctx.setLineDash([])
  ctx.restore()

  // ── Zero line ─────────────────────────────────────────────────────────────
  ctx.save()
  ctx.strokeStyle = 'rgba(148,163,184,0.30)'
  ctx.lineWidth   = 1
  ctx.beginPath(); ctx.moveTo(areaX, midY); ctx.lineTo(areaX + areaW, midY); ctx.stroke()
  ctx.restore()

  // ── Bars ──────────────────────────────────────────────────────────────────
  const barSlot = areaW / bList.length
  const barW    = Math.max(1, barSlot * 0.72)
  const halfH   = areaH / 2

  for (let i = 0; i < bList.length; i++) {
    const b  = bList[i]
    const cx = areaX + i * barSlot + barSlot / 2

    // Call bar (green, above center)
    if (b.callVol > 0) {
      const h = (b.callVol / maxVol) * halfH
      ctx.fillStyle = 'rgba(34,197,94,0.75)'
      ctx.fillRect(cx - barW / 2, midY - h, barW, h)
    }

    // Put bar (red, below center)
    if (b.putVol > 0) {
      const h = (b.putVol / maxVol) * halfH
      ctx.fillStyle = 'rgba(239,68,68,0.75)'
      ctx.fillRect(cx - barW / 2, midY, barW, h)
    }
  }

  // ── Cumulative lines ──────────────────────────────────────────────────────
  if (showCum.value && bList.length >= 2) {
    let cumC = 0, cumP = 0
    const maxCumC = totCalls.value || 1
    const maxCumP = totPuts.value  || 1

    const ptsC = [], ptsP = []
    for (let i = 0; i < bList.length; i++) {
      const b  = bList[i]
      const cx = areaX + i * barSlot + barSlot / 2
      cumC += b.callVol
      cumP += b.putVol
      ptsC.push({ x: cx, y: midY - (cumC / maxCumC) * halfH * 0.90 })
      ptsP.push({ x: cx, y: midY + (cumP / maxCumP) * halfH * 0.90 })
    }

    const drawLine = (pts, color) => {
      if (pts.length < 2) return
      ctx.save()
      ctx.strokeStyle = color
      ctx.lineWidth   = 1.5
      ctx.lineJoin    = 'round'
      ctx.beginPath()
      ctx.moveTo(pts[0].x, pts[0].y)
      for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y)
      ctx.stroke()
      // dot at last point
      const last = pts[pts.length - 1]
      ctx.fillStyle = color
      ctx.beginPath(); ctx.arc(last.x, last.y, 2.5, 0, Math.PI * 2); ctx.fill()
      ctx.restore()
    }

    drawLine(ptsC, 'rgba(74,222,128,0.90)')
    drawLine(ptsP, 'rgba(248,113,113,0.90)')
  }

  // ── Y-axis labels (left strip) ────────────────────────────────────────────
  ctx.save()
  ctx.fillStyle = 'rgba(6,12,24,0.82)'
  ctx.fillRect(0, 0, PAD_L, ch)   // opaque strip
  ctx.font      = '9px monospace'
  ctx.textAlign = 'right'

  // Axis line
  ctx.strokeStyle = 'rgba(148,163,184,0.20)'
  ctx.lineWidth   = 1
  ctx.beginPath(); ctx.moveTo(PAD_L, PAD_T); ctx.lineTo(PAD_L, ch - PAD_B); ctx.stroke()

  for (const [frac, side] of [[0.5, 1], [1, 1], [0.5, -1], [1, -1]]) {
    const vol = frac * maxVol
    const y   = midY - side * frac * halfH
    // tick
    ctx.strokeStyle = 'rgba(148,163,184,0.22)'; ctx.lineWidth = 1
    ctx.beginPath(); ctx.moveTo(PAD_L - 3, y); ctx.lineTo(PAD_L, y); ctx.stroke()
    const clr = side > 0 ? 'rgba(74,222,128,0.80)' : 'rgba(248,113,113,0.80)'
    ctx.fillStyle = clr
    ctx.fillText(fmtVol(vol), PAD_L - 5, y + 3)
  }

  // "CALLS" / "PUTS" labels on axis
  ctx.save()
  ctx.translate(11, midY - halfH * 0.5)
  ctx.rotate(-Math.PI / 2)
  ctx.textAlign = 'center'; ctx.fillStyle = 'rgba(74,222,128,0.45)'; ctx.font = '8px monospace'
  ctx.fillText('CALLS', 0, 0)
  ctx.restore()
  ctx.save()
  ctx.translate(11, midY + halfH * 0.5)
  ctx.rotate(-Math.PI / 2)
  ctx.textAlign = 'center'; ctx.fillStyle = 'rgba(248,113,113,0.45)'; ctx.font = '8px monospace'
  ctx.fillText('PUTS', 0, 0)
  ctx.restore()

  ctx.restore()

  // ── X-axis labels (bottom strip) ─────────────────────────────────────────
  ctx.save()
  ctx.fillStyle = 'rgba(6,12,24,0.82)'
  ctx.fillRect(PAD_L, ch - PAD_B, cw - PAD_L, PAD_B)

  ctx.strokeStyle = 'rgba(148,163,184,0.20)'
  ctx.lineWidth   = 1
  ctx.beginPath(); ctx.moveTo(areaX, ch - PAD_B); ctx.lineTo(areaX + areaW, ch - PAD_B); ctx.stroke()

  ctx.font      = '9px monospace'
  ctx.textAlign = 'center'
  ctx.fillStyle = 'rgba(148,163,184,0.65)'

  // Show label for every Nth bin to avoid overlap
  const maxLabels = Math.floor(areaW / 42)
  const step      = Math.max(1, Math.ceil(bList.length / maxLabels))

  for (let i = 0; i < bList.length; i += step) {
    const b  = bList[i]
    const cx = areaX + i * barSlot + barSlot / 2
    // BRT = UTC - 3
    const d  = new Date(b.ts - 3 * 3600_000)
    const hh = String(d.getUTCHours()).padStart(2, '0')
    const mm = String(d.getUTCMinutes()).padStart(2, '0')
    ctx.fillText(`${hh}:${mm}`, cx, ch - PAD_B + 14)
    ctx.strokeStyle = 'rgba(148,163,184,0.15)'
    ctx.lineWidth = 1; ctx.setLineDash([2, 4])
    ctx.beginPath(); ctx.moveTo(cx, PAD_T); ctx.lineTo(cx, ch - PAD_B); ctx.stroke()
    ctx.setLineDash([])
  }
  ctx.restore()
}

// ─── Resize ───────────────────────────────────────────────────────────────────
let ro = null
function setupResize() {
  if (!wrapEl.value || typeof ResizeObserver === 'undefined') return
  ro = new ResizeObserver(() => {
    const c = canvasEl.value, w = wrapEl.value
    if (!c || !w) return
    c.width  = w.clientWidth  || 600
    c.height = w.clientHeight || 300
    scheduleRender()
  })
  ro.observe(wrapEl.value)
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function fmtVol(v) {
  if (!v || !isFinite(v)) return '—'
  const a = Math.abs(v)
  if (a >= 1e6) return `${(v / 1e6).toFixed(1)}M`
  if (a >= 1e3) return `${(v / 1e3).toFixed(0)}k`
  return String(Math.round(v))
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────
onMounted(async () => {
  await nextTick()
  const c = canvasEl.value, w = wrapEl.value
  if (c && w) { c.width = w.clientWidth || 600; c.height = w.clientHeight || 300 }
  setupResize()
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
  if (ro) ro.disconnect()
  if (animFrame) cancelAnimationFrame(animFrame)
  if (refreshTimer) clearInterval(refreshTimer)
  if (typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', handleVisibilityRefresh)
  }
  if (typeof window !== 'undefined') {
    window.removeEventListener('focus', handleWindowFocus)
  }
})

watch(bins,    scheduleRender)
watch(showCum, scheduleRender)
watch(() => props.modelData?.underlying_security, (v, old) => {
  if (v && v !== old) reload()
})
</script>

<style scoped>
.ofw-root {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 6px;
  gap: 4px;
  background: #05101c;
}

/* ── Controls ──────────────────────────────────────────────────────────────── */
.ofw-controls {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  flex-wrap: wrap;
}

.ofw-sep {
  width: 1px; height: 16px;
  background: rgba(255,255,255,0.08);
  margin: 0 2px;
}

.ofw-btn {
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid rgba(255,255,255,0.08);
  background: transparent;
  color: #64748b;
  font-size: 10px; font-weight: 600;
  cursor: pointer; transition: all 0.15s;
  white-space: nowrap;
}
.ofw-btn.sm { padding: 2px 6px; font-size: 9px; }
.ofw-btn.active { background: #1e1b4b; border-color: #6366f1; color: #a5b4fc; }
.ofw-btn.call.active { background: rgba(21,128,61,0.25); border-color: #22c55e; color: #4ade80; }
.ofw-btn.put.active  { background: rgba(153,27,27,0.25);  border-color: #ef4444; color: #f87171; }
.ofw-btn:hover:not(.active) { background: rgba(255,255,255,0.05); color: #94a3b8; }

.ofw-chk {
  display: flex; align-items: center; gap: 3px;
  font-size: 10px; color: #64748b; cursor: pointer; user-select: none;
}
.ofw-chk input { accent-color: #6366f1; }

.ofw-sel {
  font-size: 9px; color: #64748b; background: transparent;
  border: 1px solid rgba(255,255,255,0.08); border-radius: 4px;
  padding: 2px 4px; cursor: pointer;
  color-scheme: dark;
}

.ofw-pill {
  padding: 1px 7px; border-radius: 20px; font-size: 10px;
  font-family: "JetBrains Mono", monospace; font-weight: 700;
  border: 1px solid transparent; white-space: nowrap;
}
.ofw-pill.call { background: rgba(34,197,94,0.10); border-color: rgba(34,197,94,0.25); color: #4ade80; }
.ofw-pill.put  { background: rgba(239,68,68,0.10);  border-color: rgba(239,68,68,0.25);  color: #f87171; }
.ofw-pill.net.pos { background: rgba(34,197,94,0.08); border-color: rgba(34,197,94,0.20); color: #86efac; }
.ofw-pill.net.neg { background: rgba(239,68,68,0.08); border-color: rgba(239,68,68,0.20); color: #fca5a5; }

.ofw-info    { font-size: 10px; color: #475569; }
.ofw-loading { font-size: 10px; color: #f59e0b; }
.ofw-err     { font-size: 10px; color: #f87171; max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ofw-stale   { font-size: 10px; color: #f59e0b; font-weight: 600; }
.ofw-backfill { color: #fbbf24; border-color: rgba(251,191,36,0.35); font-size: 9px; }
.ofw-backfill:hover { background: rgba(251,191,36,0.10) !important; }

/* ── Chart wrap ────────────────────────────────────────────────────────────── */
.ofw-wrap {
  flex: 1; min-height: 0; position: relative;
  border-radius: 10px; overflow: hidden;
  background:
    radial-gradient(circle at 20% 80%, rgba(34,197,94,0.04), transparent 40%),
    radial-gradient(circle at 80% 20%, rgba(239,68,68,0.04), transparent 40%),
    linear-gradient(180deg, #07111d 0%, #040c14 100%);
  border: 1px solid rgba(148,163,184,0.08);
}

.ofw-canvas {
  display: block; width: 100%; height: 100%;
}

.ofw-empty {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  color: #475569; font-size: 12px; text-align: center; padding: 20px;
}
</style>

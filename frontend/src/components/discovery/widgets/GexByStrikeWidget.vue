<template>
  <div class="gex-widget" ref="rootEl">
    <div v-if="!bars.length" class="gex-empty">Sem dados de modelo</div>
    <template v-else>
      <!-- Metric selector -->
      <div class="gex-controls">
        <button v-for="m in metrics" :key="m.key"
                class="gex-btn" :class="{ active: selected === m.key }"
                @click="selected = m.key">{{ m.label }}</button>
        <span class="gex-spot-label">Spot: {{ spotFmt }}</span>
        <span class="gex-src-label">OI B3 {{ dataDate || '—' }} · {{ bars.length }} strikes</span>
      </div>

      <!-- Chart wrap (position: relative for tooltip) -->
      <div class="gex-chart-wrap">
        <svg class="gex-svg" :viewBox="`0 0 ${W} ${H}`" preserveAspectRatio="none"
             @mousemove="onHover" @mouseleave="hoverData = null">
          <!-- Zero line -->
          <line :x1="padL" :x2="W - padR" :y1="yZero" :y2="yZero"
                stroke="rgba(255,255,255,0.15)" stroke-width="1" stroke-dasharray="3,3" />

          <!-- Bars -->
          <rect v-for="b in bars" :key="b.strike"
                :x="b.x" :y="b.barY"
                :width="barW - 1" :height="b.barH"
                :fill="b.color" :fill-opacity="b.isSpotNear ? 1 : 0.7"
                rx="1" />

          <!-- Spot line -->
          <line v-if="spotX != null" :x1="spotX" :x2="spotX" :y1="padT" :y2="H - padB"
                stroke="#f59e0b" stroke-width="1.5" />
          <text v-if="spotX != null" :x="spotX + 3" :y="padT + 10"
                fill="#f59e0b" font-size="9" font-weight="600">↑ Spot</text>

          <!-- Hover crosshair -->
          <line v-if="hoverData" :x1="hoverData.svgX" :x2="hoverData.svgX"
                :y1="padT" :y2="H - padB"
                stroke="rgba(255,255,255,0.3)" stroke-width="1" stroke-dasharray="2,2" />

          <!-- X labels (sampled) -->
          <text v-for="b in labelBars" :key="'l' + b.strike"
                :x="b.x + barW / 2" :y="H - padB + 12"
                fill="#475569" font-size="8" text-anchor="middle">
            {{ (b.strike / 1000).toFixed(0) }}k
          </text>

          <!-- Y labels -->
          <text v-for="y in yTicks" :key="'y' + y.val"
                :x="padL - 4" :y="y.py"
                fill="#334155" font-size="8" text-anchor="end" dominant-baseline="middle">
            {{ y.label }}
          </text>
        </svg>

        <!-- Tooltip -->
        <div class="gex-tt" v-if="hoverData"
             :style="ttStyle(hoverData.px, hoverData.py)">
          <div class="tt-head">{{ (hoverData.bar.strike / 1000).toFixed(0) }}k
            <span class="tt-bs" v-if="hoverData.bar._bs">~BS</span>
          </div>
          <div class="tt-row">
            <span class="tt-lbl">{{ metricLabel }}</span>
            <span class="tt-val" :class="hoverData.bar.val >= 0 ? 'tt-pos' : 'tt-neg'">
              {{ fmtTick(hoverData.bar.val) }}
            </span>
          </div>
          <template v-if="selected === 'gex'">
            <div class="tt-row">
              <span class="tt-lbl">Call OI</span>
              <span class="tt-pos">{{ fmtK(hoverData.bar.call_oi) }}</span>
            </div>
            <div class="tt-row">
              <span class="tt-lbl">Put OI</span>
              <span class="tt-neg">{{ fmtK(hoverData.bar.put_oi) }}</span>
            </div>
          </template>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({ modelData: { type: Object, default: null } })

const selected  = ref('gex')
const hoverData = ref(null)
const rootEl    = ref(null)
const W = 600; const H = 240
const padL = 38; const padR = 10; const padT = 16; const padB = 24

const metrics = [
  { key: 'gex', label: 'GEX' },
  { key: 'dex', label: 'DEX' },
  { key: 'vex', label: 'VEX' },
  { key: 'cex', label: 'CEX' },
]

const dataDate   = computed(() => props.modelData?.b3_oi_date ?? null)
const metricLabel = computed(() => metrics.find(m => m.key === selected.value)?.label ?? selected.value)

const byStrike = computed(() => {
  const rows = props.modelData?.aggregates?.by_strike ?? []
  return rows
    .map(r => ({
      strike:   parseFloat(r.key ?? r.strike),
      val:      r[selected.value] ?? 0,
      call_oi:  r.call_oi ?? 0,
      put_oi:   r.put_oi  ?? 0,
      _bs:      r._bs ?? false,
    }))
    .filter(r => r.strike > 0)
    .sort((a, b) => a.strike - b.strike)
})

const spot    = computed(() => props.modelData?.market_context?.spot_price ?? null)
const spotFmt = computed(() => spot.value ? (spot.value / 1000).toFixed(1) + 'k' : '—')

const maxAbs = computed(() => Math.max(...byStrike.value.map(r => Math.abs(r.val)), 1))
const barW   = computed(() => byStrike.value.length ? (W - padL - padR) / byStrike.value.length : 0)

const yZero = computed(() => padT + (H - padT - padB) / 2)

function yOf(v) {
  const range = H - padT - padB
  return yZero.value - (v / maxAbs.value) * (range / 2)
}

const bars = computed(() => byStrike.value.map((r, i) => {
  const y1 = yOf(r.val); const y0 = yZero.value
  const barY = Math.min(y1, y0); const barH = Math.max(Math.abs(y1 - y0), 1)
  const isSpotNear = spot.value && Math.abs(r.strike - spot.value) / spot.value < 0.01
  return {
    strike:  r.strike,
    x:       padL + i * barW.value,
    barY, barH,
    color:   r.val >= 0 ? '#6366f1' : '#ef4444',
    isSpotNear,
    val:     r.val,
    call_oi: r.call_oi,
    put_oi:  r.put_oi,
    _bs:     r._bs,
  }
}))

const labelBars = computed(() => {
  const step = Math.max(1, Math.floor(bars.value.length / 10))
  return bars.value.filter((_, i) => i % step === 0)
})

// Spot x — index-based interpolation (bars are evenly spaced by index, not by strike value)
const spotX = computed(() => {
  if (!spot.value || !byStrike.value.length) return null
  const bs = byStrike.value
  let loIdx = -1
  for (let i = 0; i < bs.length; i++) {
    if (bs[i].strike <= spot.value) loIdx = i
  }
  if (loIdx < 0 || loIdx >= bs.length - 1) return null
  const hiIdx = loIdx + 1
  const t = (spot.value - bs[loIdx].strike) / (bs[hiIdx].strike - bs[loIdx].strike)
  const loX = padL + loIdx * barW.value + barW.value / 2
  const hiX = padL + hiIdx * barW.value + barW.value / 2
  return loX + t * (hiX - loX)
})

const yTicks = computed(() => {
  const m = maxAbs.value
  const labels = [m, m / 2, 0, -m / 2, -m]
  return labels.map(v => ({ val: v, py: yOf(v), label: fmtTick(v) }))
})

// ─── Hover ────────────────────────────────────────────────────────────────────

function onHover(e) {
  if (!bars.value.length) return
  const rect  = e.currentTarget.getBoundingClientRect()
  const px    = e.clientX - rect.left
  const py    = e.clientY - rect.top
  const svgX  = px / rect.width * W
  if (svgX < padL || svgX > W - padR) { hoverData.value = null; return }
  const i = Math.max(0, Math.min(bars.value.length - 1, Math.floor((svgX - padL) / barW.value)))
  hoverData.value = { px, py, svgX: padL + i * barW.value + barW.value / 2, bar: bars.value[i] }
}

function ttStyle(px, py) {
  const rootW = rootEl.value?.offsetWidth ?? 400
  const x = Math.max(60, Math.min(rootW - 60, px))
  return { left: x + 'px', top: Math.max(8, py - 80) + 'px' }
}

// ─── Formatters ───────────────────────────────────────────────────────────────

function fmtTick(v) {
  const abs = Math.abs(v)
  if (abs >= 1e9) return (v / 1e9).toFixed(1) + 'B'
  if (abs >= 1e6) return (v / 1e6).toFixed(1) + 'M'
  if (abs >= 1e3) return (v / 1e3).toFixed(1) + 'K'
  return v.toFixed(1)
}

function fmtK(v) {
  if (v == null) return '—'
  if (v >= 1e6) return (v / 1e6).toFixed(1) + 'M'
  if (v >= 1e3) return (v / 1e3).toFixed(0) + 'K'
  return String(v)
}
</script>

<style scoped>
.gex-widget { height: 100%; display: flex; flex-direction: column; padding: 8px; gap: 6px; }
.gex-empty  { color: #475569; font-size: 12px; padding: 20px; text-align: center; }

.gex-controls { display: flex; gap: 4px; align-items: center; flex-shrink: 0; }
.gex-btn {
  padding: 3px 8px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.08);
  background: transparent; color: #64748b; font-size: 10px; font-weight: 600;
  cursor: pointer; transition: all 0.15s;
}
.gex-btn.active { background: #1e1b4b; border-color: #6366f1; color: #a5b4fc; }
.gex-btn:hover:not(.active) { background: rgba(255,255,255,0.05); color: #94a3b8; }

.gex-spot-label { margin-left: auto; font-size: 10px; color: #f59e0b; font-weight: 600; }
.gex-src-label  { font-size: 9px; color: #334155; margin-left: 8px; }

/* Chart area */
.gex-chart-wrap { position: relative; flex: 1; min-height: 0; display: flex; flex-direction: column; }
.gex-svg { flex: 1; width: 100%; min-height: 0; cursor: crosshair; }

/* Tooltip */
.gex-tt {
  position: absolute; pointer-events: none;
  transform: translateX(-50%);
  background: #0a1120; border: 1px solid rgba(255,255,255,0.14);
  border-radius: 5px; padding: 5px 9px;
  font-size: 10px; color: #e2e8f0;
  white-space: nowrap; z-index: 20; min-width: 130px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.5);
}
.tt-head { font-weight: 700; color: #f59e0b; margin-bottom: 3px; font-size: 11px; }
.tt-bs   { font-size: 8px; color: #6366f1; margin-left: 4px; opacity: 0.7; }
.tt-row  { display: flex; justify-content: space-between; gap: 14px; line-height: 1.6; }
.tt-lbl  { color: #475569; }
.tt-val  { font-variant-numeric: tabular-nums; }
.tt-pos  { color: #10b981; }
.tt-neg  { color: #f87171; }
</style>

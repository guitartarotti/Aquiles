<template>
  <div class="oi-widget" ref="rootEl">
    <div v-if="!bars.length" class="oi-empty">Sem dados de OI</div>
    <template v-else>
      <div class="oi-controls">
        <button v-for="m in modes" :key="m.key"
                class="oi-btn" :class="{ active: mode === m.key }"
                @click="mode = m.key">{{ m.label }}</button>
        <label class="oi-toggle">
          <input type="checkbox" v-model="stacked" />
          <span>Empilhado</span>
        </label>
        <span class="oi-spot">Spot: {{ spotFmt }}</span>
        <span class="oi-date" v-if="dataDate">B3 {{ dataDate }}</span>
      </div>

      <div class="oi-chart-wrap">
        <svg class="oi-svg" :viewBox="`0 0 ${W} ${H}`" preserveAspectRatio="none"
             @mousemove="onHover" @mouseleave="hoverData = null">
          <!-- Grid lines -->
          <line v-for="t in yTicks" :key="'yg' + t.val"
                :x1="padL" :x2="W - padR" :y1="t.py" :y2="t.py"
                stroke="rgba(255,255,255,0.04)" stroke-width="1" />

          <!-- Bars: stacked or side-by-side -->
          <template v-if="stacked">
            <rect v-for="b in bars" :key="'p' + b.strike"
                  :x="b.x" :y="b.putY" :width="barW - 1" :height="b.putH"
                  fill="#f87171" fill-opacity="0.75" rx="1" />
            <rect v-for="b in bars" :key="'c' + b.strike"
                  :x="b.x" :y="b.callY" :width="barW - 1" :height="b.callH"
                  fill="#10b981" fill-opacity="0.75" rx="1" />
          </template>
          <template v-else>
            <rect v-for="b in bars" :key="'p' + b.strike"
                  :x="b.x" :y="b.putY" :width="halfW - 1" :height="b.putH"
                  fill="#f87171" fill-opacity="0.75" rx="1" />
            <rect v-for="b in bars" :key="'c' + b.strike"
                  :x="b.x + halfW" :y="b.callY" :width="halfW - 1" :height="b.callH"
                  fill="#10b981" fill-opacity="0.75" rx="1" />
          </template>

          <!-- Spot line — index-interpolated to match bar pixel positions -->
          <line v-if="spotX != null" :x1="spotX" :x2="spotX" :y1="padT" :y2="H - padB"
                stroke="#f59e0b" stroke-width="1.5" />
          <text v-if="spotX != null" :x="spotX + 3" :y="padT + 10"
                fill="#f59e0b" font-size="9" font-weight="600">↑ Spot</text>

          <!-- Hover crosshair -->
          <line v-if="hoverData"
                :x1="hoverData.svgX" :x2="hoverData.svgX" :y1="padT" :y2="H - padB"
                stroke="rgba(255,255,255,0.25)" stroke-width="1" stroke-dasharray="2,2" />

          <!-- X labels (sampled) -->
          <text v-for="b in xLabels" :key="'xl' + b.strike"
                :x="b.x + barW / 2" :y="H - padB + 12"
                fill="#475569" font-size="8" text-anchor="middle">
            {{ (b.strike / 1000).toFixed(0) }}k
          </text>

          <!-- Y labels -->
          <text v-for="t in yTicks" :key="'yl' + t.val"
                :x="padL - 4" :y="t.py"
                fill="#334155" font-size="8" text-anchor="end" dominant-baseline="middle">
            {{ t.label }}
          </text>

          <!-- Legend -->
          <rect x="4" y="4" width="7" height="7" rx="1" fill="#10b981" fill-opacity="0.75" />
          <text x="14" y="11" fill="#94a3b8" font-size="8">{{ legendCall }}</text>
          <rect x="66" y="4" width="7" height="7" rx="1" fill="#f87171" fill-opacity="0.75" />
          <text x="76" y="11" fill="#94a3b8" font-size="8">{{ legendPut }}</text>
        </svg>

        <!-- Tooltip -->
        <div class="oi-tt" v-if="hoverData" :style="ttStyle(hoverData.px, hoverData.py)">
          <div class="tt-head">{{ (hoverData.bar.strike / 1000).toFixed(0) }}k</div>
          <div class="tt-row">
            <span class="tt-lbl">{{ legendCall }}</span>
            <span class="tt-pos">{{ fmtTick(hoverData.bar.call) }}</span>
          </div>
          <div class="tt-row">
            <span class="tt-lbl">{{ legendPut }}</span>
            <span class="tt-neg">{{ fmtTick(hoverData.bar.put) }}</span>
          </div>
          <div class="tt-row" v-if="hoverData.bar.total > 0">
            <span class="tt-lbl">Total</span>
            <span>{{ fmtTick(hoverData.bar.total) }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({ modelData: { type: Object, default: null } })

const mode      = ref('oi')
const stacked   = ref(false)
const hoverData = ref(null)
const rootEl    = ref(null)
const W = 600; const H = 230
const padL = 40; const padR = 10; const padT = 20; const padB = 24

const modes = [
  { key: 'oi',         label: 'OI Total'     },
  { key: 'coberto',    label: 'Coberto/Trava' },
  { key: 'descoberto', label: 'Descoberto'   },
]

const legendCall = computed(() => {
  if (mode.value === 'coberto')    return 'Call Cob.'
  if (mode.value === 'descoberto') return 'Call Desc.'
  return 'Call OI'
})
const legendPut = computed(() => {
  if (mode.value === 'coberto')    return 'Put Cob.'
  if (mode.value === 'descoberto') return 'Put Desc.'
  return 'Put OI'
})

const spot     = computed(() => props.modelData?.market_context?.spot_price ?? null)
const spotFmt  = computed(() => spot.value ? (spot.value / 1000).toFixed(1) + 'k' : '—')
const dataDate = computed(() => props.modelData?.b3_oi_date ?? null)

const byStrike = computed(() => {
  const agg  = props.modelData?.aggregates
  const rows = agg?.b3_by_strike ?? agg?.by_strike ?? []
  return rows
    .map(r => {
      const strike = parseFloat(r.key ?? r.strike)
      let call, put
      if (mode.value === 'coberto') {
        call = (r.call_coberto ?? 0) + (r.call_trava ?? 0)
        put  = (r.put_coberto  ?? 0) + (r.put_trava  ?? 0)
      } else if (mode.value === 'descoberto') {
        call = r.call_descoberto ?? 0
        put  = r.put_descoberto  ?? 0
      } else {
        call = r.call_oi ?? 0
        put  = r.put_oi  ?? 0
      }
      return { strike, call, put, total: call + put }
    })
    .filter(r => r.strike > 0 && (r.call > 0 || r.put > 0))
    .sort((a, b) => a.strike - b.strike)
})

const maxVal = computed(() => {
  if (!byStrike.value.length) return 1
  if (stacked.value) return Math.max(...byStrike.value.map(r => r.call + r.put), 1)
  return Math.max(...byStrike.value.flatMap(r => [r.call, r.put]), 1)
})

const barW   = computed(() => byStrike.value.length ? (W - padL - padR) / byStrike.value.length : 0)
const halfW  = computed(() => barW.value / 2)
const chartH = computed(() => H - padT - padB)

function barHeight(v) { return Math.max((v / maxVal.value) * chartH.value, 1) }

const bars = computed(() => byStrike.value.map((r, i) => {
  const x      = padL + i * barW.value
  const bottom = H - padB
  if (stacked.value) {
    const putH  = barHeight(r.put)
    const callH = barHeight(r.call)
    const putY  = bottom - putH
    return { strike: r.strike, x, putY, putH, callY: putY - callH, callH, call: r.call, put: r.put, total: r.total }
  } else {
    const putH  = barHeight(r.put)
    const callH = barHeight(r.call)
    return { strike: r.strike, x, putY: bottom - putH, putH, callY: bottom - callH, callH, call: r.call, put: r.put, total: r.total }
  }
}))

// Spot x — index-based interpolation so it aligns with bar pixel positions
const spotX = computed(() => {
  if (!spot.value || !byStrike.value.length) return null
  const bs = byStrike.value
  let loIdx = -1
  for (let i = 0; i < bs.length; i++) {
    if (bs[i].strike <= spot.value) loIdx = i
  }
  if (loIdx < 0 || loIdx >= bs.length - 1) return null
  const hiIdx = loIdx + 1
  const t     = (spot.value - bs[loIdx].strike) / (bs[hiIdx].strike - bs[loIdx].strike)
  const loX   = padL + loIdx * barW.value + barW.value / 2
  const hiX   = padL + hiIdx * barW.value + barW.value / 2
  return loX + t * (hiX - loX)
})

const xLabels = computed(() => {
  const step = Math.max(1, Math.floor(bars.value.length / 12))
  return bars.value.filter((_, i) => i % step === 0)
})

const yTicks = computed(() => {
  const m = maxVal.value
  return [m, m * 0.75, m * 0.5, m * 0.25, 0].map(v => ({
    val: v,
    py:  H - padB - (v / m) * chartH.value,
    label: fmtTick(v),
  }))
})

// ─── Hover ────────────────────────────────────────────────────────────────────

function onHover(e) {
  if (!bars.value.length) return
  const rect = e.currentTarget.getBoundingClientRect()
  const px   = e.clientX - rect.left
  const py   = e.clientY - rect.top
  const svgX = px / rect.width * W
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
  if (v == null) return '—'
  if (v >= 1e6) return (v / 1e6).toFixed(1) + 'M'
  if (v >= 1e3) return (v / 1e3).toFixed(0) + 'K'
  return v.toFixed(0)
}
</script>

<style scoped>
.oi-widget { height: 100%; display: flex; flex-direction: column; padding: 8px; gap: 6px; }
.oi-empty  { color: #475569; font-size: 12px; padding: 20px; text-align: center; }

.oi-controls { display: flex; gap: 4px; align-items: center; flex-shrink: 0; flex-wrap: wrap; }
.oi-btn {
  padding: 3px 8px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.08);
  background: transparent; color: #64748b; font-size: 10px; font-weight: 600;
  cursor: pointer; transition: all 0.15s;
}
.oi-btn.active { background: #1e1b4b; border-color: #6366f1; color: #a5b4fc; }
.oi-btn:hover:not(.active) { background: rgba(255,255,255,0.05); }

.oi-toggle { display: flex; align-items: center; gap: 4px; font-size: 10px; color: #64748b; cursor: pointer; margin-left: 4px; }
.oi-toggle input { accent-color: #6366f1; cursor: pointer; }
.oi-spot  { margin-left: auto; font-size: 10px; color: #f59e0b; font-weight: 600; }
.oi-date  { font-size: 9px; color: #334155; margin-left: 6px; }

/* Chart area */
.oi-chart-wrap { position: relative; flex: 1; min-height: 0; display: flex; flex-direction: column; }
.oi-svg  { flex: 1; width: 100%; min-height: 0; cursor: crosshair; }

/* Tooltip */
.oi-tt {
  position: absolute; pointer-events: none;
  transform: translateX(-50%);
  background: #0a1120; border: 1px solid rgba(255,255,255,0.14);
  border-radius: 5px; padding: 5px 9px;
  font-size: 10px; color: #e2e8f0;
  white-space: nowrap; z-index: 20; min-width: 120px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.5);
}
.tt-head { font-weight: 700; color: #f59e0b; margin-bottom: 3px; font-size: 11px; }
.tt-row  { display: flex; justify-content: space-between; gap: 14px; line-height: 1.6; }
.tt-lbl  { color: #475569; }
.tt-pos  { color: #10b981; }
.tt-neg  { color: #f87171; }
</style>

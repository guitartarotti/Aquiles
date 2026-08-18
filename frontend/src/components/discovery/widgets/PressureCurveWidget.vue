<template>
  <div class="pc-widget" ref="rootEl">
    <div v-if="!hasData" class="pc-empty">Sem dados de pressão</div>
    <template v-else>
      <div class="pc-controls">
        <button v-for="m in modes" :key="m.key"
                class="pc-btn" :class="{ active: mode === m.key }"
                @click="mode = m.key">{{ m.label }}</button>
        <span class="pc-spot-label">Spot: {{ spotFmt }}</span>
      </div>

      <div class="pc-summary">
        <div class="pc-summary-head">
          <span class="pc-summary-mode">{{ modeLabel }}</span>
          <span class="pc-summary-meta">{{ modelStampLabel }}</span>
        </div>
        <div class="pc-summary-def">{{ modeDefinition }}</div>
        <div class="pc-summary-insight">{{ modeInsight }}</div>
      </div>

      <div class="pc-chart-wrap">
        <svg class="pc-svg" :viewBox="`0 0 ${W} ${H}`" preserveAspectRatio="none"
             @mousemove="onHover" @mouseleave="hoverData = null">
          <!-- Zero reference -->
          <line :x1="padL" :x2="W - padR" :y1="yZero" :y2="yZero"
                stroke="rgba(255,255,255,0.12)" stroke-width="1" stroke-dasharray="4,3" />

          <!-- Filled area -->
          <path v-if="areaPath" :d="areaPath" :fill="fillColor" fill-opacity="0.18" />

          <!-- Main line -->
          <path v-if="linePath" :d="linePath" :stroke="lineColor"
                stroke-width="2" fill="none" stroke-linejoin="round" stroke-linecap="round" />

          <!-- Zero-cross markers -->
          <circle v-for="p in zeroCrossings" :key="p.x"
                  :cx="p.x" :cy="yZero" r="3"
                  fill="#f59e0b" opacity="0.9" />

          <!-- Spot line -->
          <line v-if="spotX" :x1="spotX" :x2="spotX" :y1="padT" :y2="H - padB"
                stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="2,2" />
          <text v-if="spotX" :x="spotX + 3" :y="padT + 10"
                fill="#f59e0b" font-size="9" font-weight="600">Spot</text>

          <!-- Hover crosshair -->
          <line v-if="hoverData"
                :x1="hoverData.svgX" :x2="hoverData.svgX" :y1="padT" :y2="H - padB"
                stroke="rgba(255,255,255,0.25)" stroke-width="1" stroke-dasharray="2,2" />
          <circle v-if="hoverData"
                  :cx="hoverData.svgX" :cy="hoverData.svgY" r="3.5"
                  fill="#f59e0b" fill-opacity="0.9" />

          <!-- Acceleration bands -->
          <line v-for="band in accelBands" :key="'b' + band.y"
                :x1="padL" :x2="W - padR" :y1="band.y" :y2="band.y"
                stroke="rgba(99,102,241,0.15)" stroke-width="1" stroke-dasharray="2,4" />

          <!-- X labels -->
          <text v-for="b in xLabels" :key="'xl' + b.strike"
                :x="b.px" :y="H - padB + 12"
                fill="#475569" font-size="8" text-anchor="middle">
            {{ (b.strike / 1000).toFixed(0) }}k
          </text>

          <!-- Y labels -->
          <text v-for="t in yTicks" :key="'yt' + t.val"
                :x="padL - 4" :y="t.py"
                fill="#334155" font-size="8" text-anchor="end" dominant-baseline="middle">
            {{ t.label }}
          </text>
        </svg>

        <!-- Tooltip -->
        <div class="pc-tt" v-if="hoverData" :style="ttStyle(hoverData.px, hoverData.py)">
          <div class="tt-head">{{ (hoverData.strike / 1000).toFixed(1) }}k</div>
          <div class="tt-row">
            <span class="tt-lbl">{{ modeLabel }}</span>
            <span class="tt-val" :class="hoverData.val >= 0 ? 'tt-pos' : 'tt-neg'">
              {{ fmtTick(hoverData.val) }}
            </span>
          </div>
          <div class="tt-row" v-if="hoverData.dval != null">
            <span class="tt-lbl">vs Spot</span>
            <span :class="hoverData.dval >= 0 ? 'tt-pos' : 'tt-neg'">
              {{ hoverData.dval >= 0 ? '+' : '' }}{{ ((hoverData.dval) * 100 / Math.max(Math.abs(hoverData.val), 1)).toFixed(1) }}%
            </span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({ modelData: { type: Object, default: null } })

const mode      = ref('net_pressure')
const hoverData = ref(null)
const rootEl    = ref(null)
const W = 600; const H = 220
const padL = 42; const padR = 12; const padT = 16; const padB = 24

const modes = [
  { key: 'net_pressure', label: 'Net Pressure'  },
  { key: 'call_pressure', label: 'Call'         },
  { key: 'put_pressure',  label: 'Put'          },
]

const modeLabel = computed(() => modes.find(m => m.key === mode.value)?.label ?? mode.value)

const pressure = computed(() => props.modelData?.pressure ?? null)
const spot     = computed(() => props.modelData?.market_context?.spot_price ?? null)
const spotFmt  = computed(() => spot.value ? (spot.value / 1000).toFixed(1) + 'k' : '—')
const modelCapturedAt = computed(() => props.modelData?.captured_at ?? null)

const hasData = computed(() => {
  const c = pressure.value?.curve
  return Array.isArray(c) && c.length > 0
})

const curve = computed(() => {
  const raw = pressure.value?.curve ?? []
  return raw
    .map(p => ({ strike: parseFloat(p.strike ?? p.key ?? 0), val: p[mode.value] ?? 0 }))
    .filter(p => p.strike > 0)
    .sort((a, b) => a.strike - b.strike)
})

const currentPoint = computed(() => pressure.value?.current_point ?? null)
const zeroPressureSpot = computed(() => {
  const spotValue = Number(pressure.value?.zero_pressure?.spot)
  return Number.isFinite(spotValue) ? spotValue : null
})
const pinningBand = computed(() => pressure.value?.pinning_band ?? {})
const accelerationBand = computed(() => pressure.value?.acceleration_band ?? {})
const decompressionBand = computed(() => pressure.value?.decompression_band ?? {})
const dominantSide = computed(() => String(pressure.value?.dominant_side || 'balanced'))

const minS   = computed(() => curve.value[0]?.strike ?? 0)
const maxS   = computed(() => curve.value[curve.value.length - 1]?.strike ?? 1)
const maxAbs = computed(() => Math.max(...curve.value.map(p => Math.abs(p.val)), 1))

const yZero = computed(() => padT + (H - padT - padB) / 2)

function xOf(strike) {
  const range = maxS.value - minS.value || 1
  return padL + ((strike - minS.value) / range) * (W - padL - padR)
}
function yOf(v) {
  const half = (H - padT - padB) / 2
  return yZero.value - (v / maxAbs.value) * half
}

const points = computed(() =>
  curve.value.map(p => ({ x: xOf(p.strike), y: yOf(p.val), val: p.val, strike: p.strike }))
)

const linePath = computed(() => {
  if (!points.value.length) return null
  return points.value.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
})

const areaPath = computed(() => {
  if (!points.value.length) return null
  const yz    = yZero.value
  const first = points.value[0]
  const last  = points.value[points.value.length - 1]
  const line  = points.value.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
  return `${line} L${last.x.toFixed(1)},${yz} L${first.x.toFixed(1)},${yz} Z`
})

const lineColor = computed(() => {
  if (mode.value === 'call_pressure') return '#10b981'
  if (mode.value === 'put_pressure') return '#f87171'
  const last = points.value[points.value.length - 1]
  return last && last.val < 0 ? '#ef4444' : '#6366f1'
})
const fillColor = computed(() => lineColor.value)

function modeValueFromPoint(point) {
  const row = point || {}
  if (mode.value === 'call_pressure') {
    const direct = Number(row.call_pressure)
    if (Number.isFinite(direct)) return direct
    const byCall = Number(row.by_put_call?.Call?.gex)
    if (Number.isFinite(byCall)) return byCall
    const gex = Number(row.gex)
    return Number.isFinite(gex) ? Math.max(gex, 0) : 0
  }
  if (mode.value === 'put_pressure') {
    const direct = Number(row.put_pressure)
    if (Number.isFinite(direct)) return direct
    const byPut = Number(row.by_put_call?.Put?.gex)
    if (Number.isFinite(byPut)) return byPut
    const gex = Number(row.gex)
    return Number.isFinite(gex) ? Math.min(gex, 0) : 0
  }
  const direct = Number(row.net_pressure)
  if (Number.isFinite(direct)) return direct
  const hp = Number(row.hp)
  return Number.isFinite(hp) ? hp : 0
}

function fmtLevel(value) {
  const num = Number(value)
  if (!Number.isFinite(num)) return '—'
  return (num / 1000).toFixed(1) + 'k'
}

function fmtBand(low, high) {
  const lowNum = Number(low)
  const highNum = Number(high)
  if (!Number.isFinite(lowNum) || !Number.isFinite(highNum)) return '—'
  return `${fmtLevel(lowNum)}–${fmtLevel(highNum)}`
}

function formatModelStamp(value) {
  if (!value) return 'sem leitura'
  const stamp = new Date(value)
  if (Number.isNaN(stamp.getTime())) return 'sem leitura'
  const parts = new Intl.DateTimeFormat('pt-BR', {
    timeZone: 'America/Sao_Paulo',
    hour: '2-digit',
    minute: '2-digit',
    day: '2-digit',
    month: '2-digit',
    hour12: false,
  }).formatToParts(stamp)
  const map = Object.fromEntries(parts.filter(item => item.type !== 'literal').map(item => [item.type, item.value]))
  return `${map.day}/${map.month} ${map.hour}:${map.minute}`
}

const modePeak = computed(() => {
  if (!curve.value.length) return null
  return [...curve.value].sort((left, right) => Math.abs(right.val) - Math.abs(left.val))[0] || null
})

const modeDefinition = computed(() => {
  if (mode.value === 'call_pressure') {
    return 'Mostra a contribuição das calls para a pressão de hedge ao longo dos strikes. Ajuda a localizar onde a asa de calls pode puxar ajuste na alta.'
  }
  if (mode.value === 'put_pressure') {
    return 'Mostra a contribuição das puts para a pressão de hedge ao longo dos strikes. Ajuda a localizar onde a asa de puts pode acelerar defesa e ajuste na queda.'
  }
  return 'É a pressão líquida de hedge do dealer na grade de preços, combinando gamma, vanna/vega/charm no hp do modelo. É a leitura mais útil para ver onde o livro tende a absorver ou acelerar.'
})

const modelStampLabel = computed(() => `Leitura ${formatModelStamp(modelCapturedAt.value)}`)

const modeInsight = computed(() => {
  const cp = currentPoint.value || {}
  const currentValue = modeValueFromPoint(cp)
  const peak = modePeak.value
  const spotValue = Number(spot.value)
  const zeroSpot = Number(zeroPressureSpot.value)
  const pinLow = Number(pinningBand.value?.low)
  const pinHigh = Number(pinningBand.value?.high)
  const accelLow = Number(accelerationBand.value?.low)
  const accelHigh = Number(accelerationBand.value?.high)
  const decompLow = Number(decompressionBand.value?.low)
  const peakLabel = peak ? `${fmtLevel(peak.strike)} (${fmtTick(peak.val)})` : '—'

  const spotVsZero = Number.isFinite(spotValue) && Number.isFinite(zeroSpot)
    ? (
      spotValue > zeroSpot
        ? `Spot acima do zero pressure em ${fmtLevel(zeroSpot)}.`
        : spotValue < zeroSpot
          ? `Spot abaixo do zero pressure em ${fmtLevel(zeroSpot)}.`
          : `Spot exatamente no zero pressure em ${fmtLevel(zeroSpot)}.`
    )
    : 'Zero pressure indisponível.'

  const bandState = Number.isFinite(spotValue) && Number.isFinite(pinLow) && Number.isFinite(pinHigh) && spotValue >= pinLow && spotValue <= pinHigh
    ? `Spot dentro da banda de pinning ${fmtBand(pinLow, pinHigh)}.`
    : Number.isFinite(spotValue) && Number.isFinite(accelLow) && Number.isFinite(accelHigh) && spotValue >= accelLow && spotValue <= accelHigh
      ? `Spot dentro da acceleration band ${fmtBand(accelLow, accelHigh)}.`
      : Number.isFinite(decompLow)
        ? `Faixa de decompression monitorada a partir de ${fmtLevel(decompLow)}.`
        : 'Sem banda operacional dominante agora.'

  if (mode.value === 'call_pressure') {
    const tone = currentValue >= 0 ? 'pressão compradora/defensiva de calls' : 'alívio de calls'
    return `O modelo vê ${tone} perto do spot, com pico principal em ${peakLabel}. ${spotVsZero} ${bandState}`
  }
  if (mode.value === 'put_pressure') {
    const tone = currentValue <= 0 ? 'pressão defensiva de puts' : 'alívio de puts'
    return `O modelo vê ${tone} perto do spot, com pico principal em ${peakLabel}. ${spotVsZero} ${bandState}`
  }
  const sideText = dominantSide.value.includes('positive')
    ? 'viés de absorção/hedge positivo'
    : dominantSide.value.includes('negative')
      ? 'viés de ajuste defensivo'
      : 'viés equilibrado'
  return `A leitura líquida está em ${fmtTick(currentValue)} no ponto atual, com ${sideText}. O maior bolsão da curva está em ${peakLabel}. ${spotVsZero} ${bandState}`
})

const zeroCrossings = computed(() => {
  const pts = points.value
  return pts.slice(1).reduce((acc, pt, i) => {
    if ((pts[i].val >= 0) !== (pt.val >= 0)) {
      const t = pts[i].val / (pts[i].val - pt.val)
      acc.push({ x: pts[i].x + t * (pt.x - pts[i].x) })
    }
    return acc
  }, [])
})

const spotX = computed(() => {
  if (!spot.value || !curve.value.length) return null
  if (spot.value < minS.value || spot.value > maxS.value) return null
  return xOf(spot.value)
})

const xLabels = computed(() => {
  const step = Math.max(1, Math.floor(points.value.length / 8))
  return points.value.filter((_, i) => i % step === 0)
    .map(p => ({ strike: p.strike, px: p.x }))
})

const yTicks = computed(() => {
  const m = maxAbs.value
  return [m, m / 2, 0, -m / 2, -m].map(v => ({
    val: v, py: yOf(v), label: fmtTick(v),
  }))
})

const accelBands = computed(() => {
  const m = maxAbs.value
  return [m * 0.5, -m * 0.5].map(v => ({ y: yOf(v) }))
})

// ─── Hover ────────────────────────────────────────────────────────────────────

function onHover(e) {
  if (!points.value.length) return
  const rect = e.currentTarget.getBoundingClientRect()
  const px   = e.clientX - rect.left
  const py   = e.clientY - rect.top
  const svgX = px / rect.width * W

  // Find nearest point by svgX
  let nearest = null, minD = Infinity
  for (const p of points.value) {
    const d = Math.abs(p.x - svgX)
    if (d < minD) { minD = d; nearest = p }
  }
  if (!nearest) { hoverData.value = null; return }

  // Value at spot for comparison
  const spotVal = spotX.value != null
    ? points.value.reduce((a, b) =>
        Math.abs(b.x - spotX.value) < Math.abs(a.x - spotX.value) ? b : a
      ).val
    : null

  hoverData.value = {
    px, py,
    svgX:   nearest.x,
    svgY:   nearest.y,
    strike: nearest.strike,
    val:    nearest.val,
    dval:   spotVal != null ? nearest.val - spotVal : null,
  }
}

function ttStyle(px, py) {
  const rootW = rootEl.value?.offsetWidth ?? 400
  const x = Math.max(60, Math.min(rootW - 60, px))
  return { left: x + 'px', top: Math.max(8, py - 80) + 'px' }
}

function fmtTick(v) {
  const abs = Math.abs(v)
  if (abs >= 1e9) return (v / 1e9).toFixed(1) + 'B'
  if (abs >= 1e6) return (v / 1e6).toFixed(1) + 'M'
  if (abs >= 1e3) return (v / 1e3).toFixed(1) + 'K'
  return v.toFixed(2)
}
</script>

<style scoped>
.pc-widget { height: 100%; display: flex; flex-direction: column; padding: 8px; gap: 6px; }
.pc-empty  { color: #475569; font-size: 12px; padding: 20px; text-align: center; }

.pc-controls { display: flex; gap: 4px; align-items: center; flex-shrink: 0; }
.pc-btn {
  padding: 3px 8px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.08);
  background: transparent; color: #64748b; font-size: 10px; font-weight: 600;
  cursor: pointer; transition: all 0.15s;
}
.pc-btn.active { background: #1e1b4b; border-color: #6366f1; color: #a5b4fc; }
.pc-btn:hover:not(.active) { background: rgba(255,255,255,0.05); color: #94a3b8; }
.pc-spot-label { margin-left: auto; font-size: 10px; color: #f59e0b; font-weight: 600; }

.pc-summary {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 8px 10px;
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 8px;
  background: rgba(10,17,32,0.72);
}
.pc-summary-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.pc-summary-mode {
  font-size: 10px;
  font-weight: 700;
  color: #cbd5e1;
}
.pc-summary-meta {
  font-size: 9px;
  color: #64748b;
}
.pc-summary-def {
  font-size: 10px;
  line-height: 1.45;
  color: #94a3b8;
}
.pc-summary-insight {
  font-size: 10px;
  line-height: 1.5;
  color: #e2e8f0;
}

.pc-chart-wrap { position: relative; flex: 1; min-height: 0; display: flex; flex-direction: column; }
.pc-svg { flex: 1; width: 100%; min-height: 0; cursor: crosshair; }

/* Tooltip */
.pc-tt {
  position: absolute; pointer-events: none;
  transform: translateX(-50%);
  background: #0a1120; border: 1px solid rgba(255,255,255,0.14);
  border-radius: 5px; padding: 5px 9px;
  font-size: 10px; color: #e2e8f0;
  white-space: nowrap; z-index: 20; min-width: 130px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.5);
}
.tt-head { font-weight: 700; color: #f59e0b; margin-bottom: 3px; font-size: 11px; }
.tt-row  { display: flex; justify-content: space-between; gap: 14px; line-height: 1.6; }
.tt-lbl  { color: #475569; }
.tt-val  { font-variant-numeric: tabular-nums; }
.tt-pos  { color: #10b981; }
.tt-neg  { color: #f87171; }
</style>

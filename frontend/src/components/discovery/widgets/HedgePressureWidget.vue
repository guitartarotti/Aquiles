<template>
  <div class="hp-widget" ref="rootEl">
    <div v-if="!hasData" class="hp-empty">Sem dados de pressão de hedge</div>
    <template v-else>

      <!-- ── KPI header ──────────────────────────────────────────────────────── -->
      <div class="hp-header">

        <!-- Zero Pressure level -->
        <div class="hp-kpi">
          <span class="hp-kpi-lbl">Zero HP</span>
          <span class="hp-kpi-val" :class="zpDist != null ? (zpDist > 0 ? 'emerald' : 'rose') : ''">
            {{ zpFmt }}
          </span>
          <span class="hp-kpi-sub" v-if="zpDist != null">
            {{ zpDist >= 0 ? '+' : '' }}{{ zpDist.toFixed(0) }}pts
            ({{ (zpPct * 100).toFixed(2) }}%)
          </span>
        </div>

        <div class="hp-sep" />

        <!-- HP at current spot -->
        <div class="hp-kpi">
          <span class="hp-kpi-lbl">HP @ Spot</span>
          <span class="hp-kpi-val" :class="hpAtSpot >= 0 ? 'emerald' : 'rose'">
            {{ fmtHp(hpAtSpot) }}
          </span>
          <span class="hp-kpi-sub" :class="hpAtSpot >= 0 ? 'emerald' : 'rose'">
            {{ hpAtSpot >= 0 ? 'estabiliza' : 'amplifica' }}
          </span>
        </div>

        <div class="hp-sep" />

        <!-- Dominant side -->
        <div class="hp-kpi">
          <span class="hp-kpi-lbl">Lado</span>
          <span class="hp-regime" :class="dominantSide === 'call' ? 'regime-call' : 'regime-put'">
            {{ dominantSide === 'call' ? '▲ Call' : '▼ Put' }}
          </span>
          <span class="hp-kpi-sub">pressão dominante</span>
        </div>

        <div class="hp-sep" />

        <!-- Max acceleration -->
        <div class="hp-kpi">
          <span class="hp-kpi-lbl">Max ∂HP/∂S</span>
          <span class="hp-kpi-val amber">{{ maxAccelFmt }}</span>
          <span class="hp-kpi-sub" v-if="maxAccelDist != null">
            {{ maxAccelDist >= 0 ? '+' : '' }}{{ maxAccelDist.toFixed(0) }}pts
          </span>
        </div>

        <div class="hp-sep" />

        <!-- Center of mass -->
        <div class="hp-kpi">
          <span class="hp-kpi-lbl">C. Massa</span>
          <span class="hp-kpi-val violet">{{ comFmt }}</span>
          <span class="hp-kpi-sub">dealer ref</span>
        </div>

        <div style="flex:1" />

        <!-- Legend pills -->
        <div class="hp-legend">
          <div class="hp-leg-item" v-if="zeroPressureSpot">
            <span class="leg-dot" style="background:#10b981"></span>
            <span>Zero HP</span>
          </div>
          <div class="hp-leg-item" v-if="centerOfMass">
            <span class="leg-dot" style="background:#a855f7"></span>
            <span>CoM</span>
          </div>
          <div class="hp-leg-item" v-if="maxAccelSpot">
            <span class="leg-dot" style="background:#fbbf24"></span>
            <span>Accel</span>
          </div>
        </div>

        <span class="hp-meta">Spot: <b>{{ spotFmt }}</b></span>
      </div>

      <!-- ── Band legend ──────────────────────────────────────────────────────── -->
      <div class="hp-band-legend">
        <div class="hp-band-pill pin" v-if="hasPinning">
          <span class="bpill-dot pin"></span>
          Pinning {{ fmtLevel(pinningBand.low) }}–{{ fmtLevel(pinningBand.high) }}
        </div>
        <div class="hp-band-pill accel" v-if="hasAccel">
          <span class="bpill-dot accel"></span>
          Aceleração {{ fmtLevel(accelBand.low) }}–{{ fmtLevel(accelBand.high) }}
        </div>
        <div class="hp-band-pill decomp" v-if="hasDecomp">
          <span class="bpill-dot decomp"></span>
          Descompressão {{ fmtLevel(decompBand.low) }}–{{ fmtLevel(decompBand.high) }}
        </div>
        <div class="hp-mode-btns">
          <button class="hp-btn" :class="{ active: showGex }" @click="showGex = !showGex">GEX</button>
          <button class="hp-btn" :class="{ active: showBands }" @click="showBands = !showBands">Bandas</button>
        </div>
      </div>

      <!-- ── HP(S) Curve ──────────────────────────────────────────────────────── -->
      <div class="hp-chart-wrap">
        <svg class="hp-svg" :viewBox="`0 0 ${CW} ${CH}`" preserveAspectRatio="none"
             @mousemove="onHover" @mouseleave="hover = null">

          <!-- defs: clip paths for above/below zero fill -->
          <defs>
            <clipPath id="hp-clip-pos">
              <rect :x="padL" :y="padT" :width="CW - padL - padR" :height="yZero - padT" />
            </clipPath>
            <clipPath id="hp-clip-neg">
              <rect :x="padL" :y="yZero" :width="CW - padL - padR" :height="CH - padB - yZero" />
            </clipPath>
          </defs>

          <!-- Shaded bands (rendered behind everything) -->
          <template v-if="showBands">
            <!-- Decompression band (widest, rendered first) -->
            <rect v-if="hasDecomp && decompX1 != null"
                  :x="decompX1" :y="padT" :width="Math.max(0, decompX2 - decompX1)" :height="CH - padT - padB"
                  fill="#a855f7" fill-opacity="0.05"
                  stroke="#a855f7" stroke-opacity="0.15" stroke-width="1" stroke-dasharray="2,4" />

            <!-- Acceleration band -->
            <rect v-if="hasAccel && accelX1 != null"
                  :x="accelX1" :y="padT" :width="Math.max(0, accelX2 - accelX1)" :height="CH - padT - padB"
                  fill="#fbbf24" fill-opacity="0.06"
                  stroke="#fbbf24" stroke-opacity="0.20" stroke-width="1" stroke-dasharray="2,4" />

            <!-- Pinning band (narrowest, on top) -->
            <rect v-if="hasPinning && pinX1 != null"
                  :x="pinX1" :y="padT" :width="Math.max(0, pinX2 - pinX1)" :height="CH - padT - padB"
                  fill="#10b981" fill-opacity="0.07"
                  stroke="#10b981" stroke-opacity="0.25" stroke-width="1" stroke-dasharray="2,3" />
          </template>

          <!-- Y grid lines -->
          <line v-for="t in yTicks" :key="'hg' + t.val"
                :x1="padL" :x2="CW - padR" :y1="t.py" :y2="t.py"
                stroke="rgba(148,163,184,0.06)" stroke-width="1" stroke-dasharray="3,5" />

          <!-- Zero line -->
          <line :x1="padL" :x2="CW - padR" :y1="yZero" :y2="yZero"
                stroke="rgba(148,163,184,0.22)" stroke-width="1" stroke-dasharray="4,3" />

          <!-- HP area fill — positive (stabilising) green -->
          <path v-if="areaPath"
                :d="areaPath" fill="#10b981" fill-opacity="0.15"
                clip-path="url(#hp-clip-pos)" />
          <!-- HP area fill — negative (amplifying) rose -->
          <path v-if="areaPath"
                :d="areaPath" fill="#f43f5e" fill-opacity="0.15"
                clip-path="url(#hp-clip-neg)" />

          <!-- HP line positive (emerald) -->
          <path v-if="linePath"
                :d="linePath" stroke="#10b981" stroke-width="2"
                fill="none" stroke-linejoin="round" stroke-linecap="round"
                clip-path="url(#hp-clip-pos)" />
          <!-- HP line negative (rose) -->
          <path v-if="linePath"
                :d="linePath" stroke="#f43f5e" stroke-width="2"
                fill="none" stroke-linejoin="round" stroke-linecap="round"
                clip-path="url(#hp-clip-neg)" />

          <!-- GEX score overlay (dashed, secondary axis scaled) -->
          <path v-if="showGex && gexPath"
                :d="gexPath" stroke="#f97316" stroke-width="1.5"
                fill="none" stroke-dasharray="4,3" opacity="0.7" />

          <!-- Zero-pressure vertical marker -->
          <g v-if="zpX != null">
            <line :x1="zpX" :x2="zpX" :y1="padT" :y2="CH - padB"
                  stroke="#10b981" stroke-width="1.5" stroke-dasharray="3,3" stroke-opacity="0.85" />
            <circle :cx="zpX" :cy="yZero" r="4.5"
                    fill="#10b981" fill-opacity="0.95" stroke="#060c18" stroke-width="1.5" />
            <text :x="zpX + 5" :y="padT + 12"
                  fill="#10b981" font-size="9" font-weight="700">
              HP=0 {{ fmtLevel(zeroPressureSpot) }}
            </text>
          </g>

          <!-- Center of mass (dealer ref) vertical marker -->
          <g v-if="comX != null">
            <line :x1="comX" :x2="comX" :y1="padT" :y2="CH - padB"
                  stroke="#a855f7" stroke-width="1.5" stroke-dasharray="5,3" stroke-opacity="0.80" />
            <text :x="comX + 4" :y="padT + 24"
                  fill="#a855f7" font-size="9" font-weight="700">
              CoM {{ fmtLevel(centerOfMass) }}
            </text>
          </g>

          <!-- Max acceleration marker (triangle + dashed) -->
          <g v-if="accelX != null">
            <line :x1="accelX" :x2="accelX" :y1="padT" :y2="CH - padB"
                  stroke="#fbbf24" stroke-width="1" stroke-dasharray="2,4" stroke-opacity="0.70" />
            <!-- Triangle pointing down -->
            <polygon :points="`${accelX},${padT + 6} ${accelX - 5},${padT} ${accelX + 5},${padT}`"
                     fill="#fbbf24" fill-opacity="0.90" />
            <text :x="accelX + 5" :y="padT + 36"
                  fill="#fbbf24" font-size="8" font-weight="600">
              ∂HP {{ fmtLevel(maxAccelSpot) }}
            </text>
          </g>

          <!-- Spot line -->
          <line v-if="spotX != null" :x1="spotX" :x2="spotX" :y1="padT" :y2="CH - padB"
                stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="2,2" />
          <text v-if="spotX != null" :x="spotX + 3" :y="CH - padB - 4"
                fill="#f59e0b" font-size="9" font-weight="600">Spot</text>

          <!-- Hover crosshair -->
          <line v-if="hover"
                :x1="hover.svgX" :x2="hover.svgX" :y1="padT" :y2="CH - padB"
                stroke="rgba(255,255,255,0.25)" stroke-width="1" stroke-dasharray="2,2" />
          <circle v-if="hover"
                  :cx="hover.svgX" :cy="hover.svgY" r="3.5"
                  :fill="hover.hp >= 0 ? '#10b981' : '#f43f5e'" fill-opacity="0.95" />

          <!-- GEX hover dot -->
          <circle v-if="showGex && hover && hover.gexY != null"
                  :cx="hover.svgX" :cy="hover.gexY" r="3"
                  fill="#f97316" fill-opacity="0.85" />

          <!-- X labels -->
          <text v-for="p in xLabels" :key="'hxl' + p.strike"
                :x="p.px" :y="CH - padB + 13"
                fill="#475569" font-size="8" text-anchor="middle">
            {{ fmtLevel(p.strike) }}
          </text>

          <!-- Y labels -->
          <text v-for="t in yTicks" :key="'hyl' + t.val"
                :x="padL - 4" :y="t.py"
                fill="#334155" font-size="8" text-anchor="end" dominant-baseline="middle">
            {{ t.label }}
          </text>

          <!-- GEX Y labels (right axis) -->
          <template v-if="showGex">
            <text v-for="t in gexYTicks" :key="'gyl' + t.val"
                  :x="CW - padR + 3" :y="t.py"
                  fill="#f97316" fill-opacity="0.60" font-size="7" text-anchor="start" dominant-baseline="middle">
              {{ t.label }}
            </text>
          </template>

        </svg>

        <!-- Hover tooltip -->
        <div class="hp-tt" v-if="hover" :style="ttStyle(hover.px, hover.py)">
          <div class="tt-head">{{ fmtLevel(hover.strike) }}</div>
          <div class="tt-row">
            <span class="tt-lbl">HP(S)</span>
            <span :class="hover.hp >= 0 ? 'tt-emerald' : 'tt-rose'">{{ fmtHp(hover.hp) }}</span>
          </div>
          <div class="tt-row" v-if="showGex">
            <span class="tt-lbl">GEX</span>
            <span class="tt-orange">{{ fmtHp(hover.gex) }}</span>
          </div>
          <div class="tt-row" v-if="zeroPressureSpot != null">
            <span class="tt-lbl">vs Zero HP</span>
            <span class="tt-val">
              {{ (hover.strike - zeroPressureSpot) >= 0 ? '+' : '' }}{{ (hover.strike - zeroPressureSpot).toFixed(0) }}pts
            </span>
          </div>
          <div class="tt-row" v-if="centerOfMass != null">
            <span class="tt-lbl">vs CoM</span>
            <span class="tt-val">
              {{ (hover.strike - centerOfMass) >= 0 ? '+' : '' }}{{ (hover.strike - centerOfMass).toFixed(0) }}pts
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

// ─── Layout ───────────────────────────────────────────────────────────────────
const CW = 600; const CH = 240
const padL = 48; const padR = 36; const padT = 22; const padB = 28

// ─── UI state ─────────────────────────────────────────────────────────────────
const showGex   = ref(false)
const showBands = ref(true)
const hover     = ref(null)
const rootEl    = ref(null)

// ─── Source data ──────────────────────────────────────────────────────────────
const pressure = computed(() => props.modelData?.pressure ?? null)
const spot     = computed(() => props.modelData?.market_context?.spot_price ?? null)
const spotFmt  = computed(() => spot.value ? fmtLevel(spot.value) : '—')

const hasData  = computed(() => {
  const c = pressure.value?.curve
  return Array.isArray(c) && c.length > 0
})

// ─── Pressure band anchors ────────────────────────────────────────────────────
const zeroPressureSpot = computed(() => pressure.value?.zero_pressure?.spot ?? null)
const centerOfMass     = computed(() => pressure.value?.center_of_mass      ?? null)
const maxAccelSpot     = computed(() => pressure.value?.max_acceleration?.spot ?? null)
const pinningBand      = computed(() => pressure.value?.pinning_band       ?? null)
const accelBand        = computed(() => pressure.value?.acceleration_band  ?? null)
const decompBand       = computed(() => pressure.value?.decompression_band ?? null)

const hasPinning = computed(() => pinningBand.value?.low != null && pinningBand.value?.high != null)
const hasAccel   = computed(() => accelBand.value?.low  != null && accelBand.value?.high  != null)
const hasDecomp  = computed(() => decompBand.value?.low != null && decompBand.value?.high != null)

// ─── KPI helpers ──────────────────────────────────────────────────────────────
const dominantSide = computed(() => pressure.value?.dominant_side ?? 'call')

const hpAtSpot = computed(() => {
  if (!spot.value || !curvePts.value.length) return 0
  return curvePts.value.reduce((best, p) =>
    Math.abs(p.strike - spot.value) < Math.abs(best.strike - spot.value) ? p : best
  ).hp
})

const zpDist = computed(() => {
  if (!zeroPressureSpot.value || !spot.value) return null
  return zeroPressureSpot.value - spot.value
})
const zpPct  = computed(() => (!zpDist.value || !spot.value) ? null : zpDist.value / spot.value)
const zpFmt  = computed(() => zeroPressureSpot.value ? fmtLevel(zeroPressureSpot.value) : '—')

const maxAccelDist = computed(() => {
  if (!maxAccelSpot.value || !spot.value) return null
  return maxAccelSpot.value - spot.value
})
const maxAccelFmt = computed(() => maxAccelSpot.value ? fmtLevel(maxAccelSpot.value) : '—')
const comFmt      = computed(() => centerOfMass.value ? fmtLevel(centerOfMass.value) : '—')

// ─── Curve data ───────────────────────────────────────────────────────────────
const curvePts = computed(() => {
  const raw = pressure.value?.curve ?? []
  return raw
    .map(p => ({
      strike: parseFloat(p.strike ?? p.key ?? 0),
      hp:     p.net_pressure ?? 0,
      gex:    p.gex_score    ?? 0,
    }))
    .filter(p => p.strike > 0)
    .sort((a, b) => a.strike - b.strike)
})

const minS   = computed(() => curvePts.value[0]?.strike ?? 0)
const maxS   = computed(() => curvePts.value[curvePts.value.length - 1]?.strike ?? 1)
const maxAbsHp  = computed(() => Math.max(...curvePts.value.map(p => Math.abs(p.hp)), 1))
const maxAbsGex = computed(() => Math.max(...curvePts.value.map(p => Math.abs(p.gex)), 1))

const yZero = computed(() => padT + (CH - padT - padB) / 2)

function xOf(s) {
  const range = maxS.value - minS.value || 1
  return padL + ((s - minS.value) / range) * (CW - padL - padR)
}
function yHpOf(v) {
  const half = (CH - padT - padB) / 2
  return yZero.value - (v / maxAbsHp.value) * half
}
function yGexOf(v) {
  const half = (CH - padT - padB) / 2
  return yZero.value - (v / maxAbsGex.value) * half
}

// Mapped SVG points
const svgPts = computed(() =>
  curvePts.value.map(p => ({
    x: xOf(p.strike), y: yHpOf(p.hp), gexY: yGexOf(p.gex),
    hp: p.hp, gex: p.gex, strike: p.strike,
  }))
)

// Area fill path for HP
const areaPath = computed(() => {
  const pts = svgPts.value
  if (!pts.length) return null
  const yz = yZero.value
  const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
  return `${line} L${pts[pts.length - 1].x.toFixed(1)},${yz} L${pts[0].x.toFixed(1)},${yz} Z`
})

// Line path for HP
const linePath = computed(() => {
  const pts = svgPts.value
  if (!pts.length) return null
  return pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
})

// GEX score path (secondary overlay)
const gexPath = computed(() => {
  const pts = svgPts.value
  if (!pts.length) return null
  return pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.gexY.toFixed(1)}`).join(' ')
})

// ─── Reference level x-positions ──────────────────────────────────────────────
function xForLevel(level) {
  if (level == null || !curvePts.value.length) return null
  if (level < minS.value || level > maxS.value) return null
  return xOf(level)
}

const zpX     = computed(() => xForLevel(zeroPressureSpot.value))
const comX    = computed(() => xForLevel(centerOfMass.value))
const accelX  = computed(() => xForLevel(maxAccelSpot.value))
const spotX   = computed(() => xForLevel(spot.value))

// Band x-positions
const pinX1   = computed(() => hasPinning.value ? xForLevel(pinningBand.value.low)  : null)
const pinX2   = computed(() => hasPinning.value ? xForLevel(pinningBand.value.high) : null)
const accelX1 = computed(() => hasAccel.value   ? xForLevel(accelBand.value.low)   : null)
const accelX2 = computed(() => hasAccel.value   ? xForLevel(accelBand.value.high)  : null)
const decompX1 = computed(() => hasDecomp.value ? xForLevel(decompBand.value.low)  : null)
const decompX2 = computed(() => hasDecomp.value ? xForLevel(decompBand.value.high) : null)

// ─── Axis ticks ───────────────────────────────────────────────────────────────
const yTicks = computed(() => {
  const m = maxAbsHp.value
  return [m, m * 0.5, 0, -m * 0.5, -m].map(v => ({
    val: v, py: yHpOf(v), label: fmtHp(v),
  }))
})

const gexYTicks = computed(() => {
  const m = maxAbsGex.value
  return [m, 0, -m].map(v => ({
    val: v, py: yGexOf(v), label: fmtHp(v),
  }))
})

const xLabels = computed(() => {
  const step = Math.max(1, Math.floor(svgPts.value.length / 8))
  return svgPts.value.filter((_, i) => i % step === 0).map(p => ({ strike: p.strike, px: p.x }))
})

// ─── Hover ────────────────────────────────────────────────────────────────────
function onHover(e) {
  if (!svgPts.value.length) return
  const rect = e.currentTarget.getBoundingClientRect()
  const px   = e.clientX - rect.left
  const py   = e.clientY - rect.top
  const svgX = px / rect.width * CW
  if (svgX < padL || svgX > CW - padR) { hover.value = null; return }
  let nearest = null, minD = Infinity
  for (const p of svgPts.value) {
    const d = Math.abs(p.x - svgX)
    if (d < minD) { minD = d; nearest = p }
  }
  if (!nearest) return
  hover.value = {
    px, py,
    svgX: nearest.x, svgY: nearest.y,
    gexY: showGex.value ? nearest.gexY : null,
    hp: nearest.hp, gex: nearest.gex, strike: nearest.strike,
  }
}

function ttStyle(px, py) {
  const rootW = rootEl.value?.offsetWidth ?? 400
  const x = Math.max(80, Math.min(rootW - 80, px))
  return { left: x + 'px', top: Math.max(8, py - 100) + 'px' }
}

// ─── Formatters ───────────────────────────────────────────────────────────────
function fmtHp(v) {
  if (v == null || !isFinite(v)) return '—'
  const abs = Math.abs(v)
  const sign = v < 0 ? '-' : ''
  if (abs >= 1e9) return sign + (abs / 1e9).toFixed(2) + 'B'
  if (abs >= 1e6) return sign + (abs / 1e6).toFixed(2) + 'M'
  if (abs >= 1e3) return sign + (abs / 1e3).toFixed(1) + 'K'
  return v.toFixed(2)
}

function fmtLevel(v) {
  if (v == null) return '—'
  if (Math.abs(v) >= 1000) return (v / 1000).toFixed(2) + 'k'
  return v.toFixed(0)
}
</script>

<style scoped>
.hp-widget {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 8px;
  gap: 5px;
  background: #05101c;
  color: #e2e8f0;
  font-family: "JetBrains Mono", monospace;
  overflow: hidden;
}

.hp-empty {
  color: #475569;
  font-size: 12px;
  padding: 24px;
  text-align: center;
}

/* ── KPI Header ─────────────────────────────────────────────────────────────── */
.hp-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  background: rgba(255,255,255,0.02);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 7px;
  padding: 7px 12px;
  flex-wrap: wrap;
}

.hp-sep {
  width: 1px; height: 32px;
  background: rgba(255,255,255,0.07);
  flex-shrink: 0;
}

.hp-kpi {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 72px;
}
.hp-kpi-lbl {
  font-size: 8px;
  font-weight: 700;
  color: #334155;
  letter-spacing: .07em;
  text-transform: uppercase;
}
.hp-kpi-val {
  font-size: 14px;
  font-weight: 700;
  color: #e2e8f0;
  letter-spacing: .01em;
  line-height: 1.1;
}
.hp-kpi-sub {
  font-size: 9px;
  color: #475569;
  letter-spacing: .02em;
}

/* Color helpers */
.emerald { color: #10b981 !important; }
.rose    { color: #f43f5e !important; }
.amber   { color: #fbbf24 !important; }
.violet  { color: #a855f7 !important; }

.hp-regime {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
}
.regime-call { background: rgba(16,185,129,0.12); color: #10b981; border: 1px solid rgba(16,185,129,0.25); }
.regime-put  { background: rgba(244,63,94,0.12);  color: #f43f5e; border: 1px solid rgba(244,63,94,0.25); }

.hp-legend {
  display: flex;
  gap: 10px;
  align-items: center;
}
.hp-leg-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 9px;
  color: #64748b;
}
.leg-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.hp-meta {
  font-size: 10px;
  color: #f59e0b;
  white-space: nowrap;
  margin-left: 4px;
}
.hp-meta b { font-weight: 700; }

/* ── Band legend bar ─────────────────────────────────────────────────────────── */
.hp-band-legend {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  flex-wrap: wrap;
}

.hp-band-pill {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 9px;
  padding: 3px 8px;
  border-radius: 4px;
  letter-spacing: .03em;
  border: 1px solid transparent;
}
.hp-band-pill.pin   { background: rgba(16,185,129,0.07); color: #10b981; border-color: rgba(16,185,129,0.20); }
.hp-band-pill.accel { background: rgba(251,191,36,0.07); color: #fbbf24; border-color: rgba(251,191,36,0.20); }
.hp-band-pill.decomp{ background: rgba(168,85,247,0.07); color: #a855f7; border-color: rgba(168,85,247,0.20); }

.bpill-dot {
  width: 6px; height: 6px;
  border-radius: 2px;
  flex-shrink: 0;
}
.bpill-dot.pin   { background: #10b981; }
.bpill-dot.accel { background: #fbbf24; }
.bpill-dot.decomp{ background: #a855f7; }

.hp-mode-btns { display: flex; gap: 3px; margin-left: auto; }
.hp-btn {
  padding: 3px 8px;
  border-radius: 4px;
  border: 1px solid rgba(255,255,255,0.08);
  background: transparent;
  color: #64748b;
  font-size: 9px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
}
.hp-btn.active { background: #0c1e38; border-color: #64748b; color: #94a3b8; }
.hp-btn:hover:not(.active) { background: rgba(255,255,255,0.05); color: #94a3b8; }

/* ── Chart ───────────────────────────────────────────────────────────────────── */
.hp-chart-wrap {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.hp-svg {
  flex: 1;
  width: 100%;
  min-height: 0;
  cursor: crosshair;
  overflow: visible;
}

/* ── Tooltip ──────────────────────────────────────────────────────────────────── */
.hp-tt {
  position: absolute;
  pointer-events: none;
  transform: translateX(-50%);
  background: #080f1e;
  border: 1px solid rgba(255,255,255,0.13);
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 10px;
  color: #e2e8f0;
  white-space: nowrap;
  z-index: 20;
  min-width: 160px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.55);
}
.tt-head    { font-weight: 700; color: #f59e0b; margin-bottom: 4px; font-size: 11px; }
.tt-row     { display: flex; justify-content: space-between; gap: 14px; line-height: 1.65; }
.tt-lbl     { color: #475569; }
.tt-val     { font-variant-numeric: tabular-nums; color: #94a3b8; }
.tt-emerald { color: #10b981; font-weight: 700; font-variant-numeric: tabular-nums; }
.tt-rose    { color: #f43f5e; font-weight: 700; font-variant-numeric: tabular-nums; }
.tt-orange  { color: #f97316; font-weight: 700; font-variant-numeric: tabular-nums; }
</style>

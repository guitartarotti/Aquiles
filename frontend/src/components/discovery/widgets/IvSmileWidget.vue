<template>
  <div class="iv-widget" ref="rootEl">
    <div v-if="!hasData" class="iv-empty">Sem dados de volatilidade</div>
    <template v-else>
      <div class="iv-controls">
        <select class="iv-select" v-model="selectedExpiry">
          <option v-for="e in expiries" :key="e.key" :value="e.key">{{ e.label }}</option>
        </select>
        <button class="iv-btn" :class="{ active: showFit }" @click="showFit = !showFit" title="Mostrar fit polinomial">
          ≈ Fit
        </button>
        <button class="iv-btn" :class="{ active: showRaw }" @click="showRaw = !showRaw" title="Mostrar pontos brutos">
          ● Raw
        </button>
        <span class="iv-atm-label" v-if="atmIv != null">
          ATM: <b>{{ (atmIv * 100).toFixed(1) }}%</b>
        </span>
        <span class="iv-skew-label" v-if="skew25 != null">
          25Δ skew: <b :class="skew25 > 0 ? 'skew-pos' : 'skew-neg'">{{ skew25 > 0 ? '+' : '' }}{{ (skew25 * 100).toFixed(1) }}%</b>
        </span>
        <span class="iv-spot-label">{{ spotFmt }}</span>
      </div>

      <div class="iv-chart-wrap">
        <svg class="iv-svg" :viewBox="`0 0 ${W} ${H}`" preserveAspectRatio="none"
             @mousemove="onHover" @mouseleave="hoverData = null">

          <!-- Horizontal grid -->
          <line v-for="t in yTicks" :key="'yg' + t.val"
                :x1="padL" :x2="W - padR" :y1="t.py" :y2="t.py"
                stroke="rgba(255,255,255,0.04)" stroke-width="1" />

          <!-- ATM vertical line -->
          <line v-if="spotX != null" :x1="spotX" :x2="spotX" :y1="padT" :y2="H - padB"
                stroke="#f59e0b" stroke-width="1" stroke-dasharray="3,2" opacity="0.7" />
          <text v-if="spotX != null" :x="spotX + 3" :y="padT + 9"
                fill="#f59e0b" font-size="8" font-weight="600">ATM</text>

          <!-- ─── Raw data dots ─────────────────────────────────────────── -->
          <template v-if="showRaw">
            <circle v-for="p in rawCallPts" :key="'rc' + p.strike"
                    :cx="p.x" :cy="p.y" r="2.5"
                    fill="#10b981" fill-opacity="0.75" />
            <circle v-for="p in rawPutPts" :key="'rp' + p.strike"
                    :cx="p.x" :cy="p.y" r="2.5"
                    fill="#f87171" fill-opacity="0.75" />
          </template>

          <!-- ─── Polynomial fit curves ─────────────────────────────────── -->
          <template v-if="showFit">
            <!-- Call fit fill area -->
            <path v-if="callFitPath && putFitPath" :d="combinedFillPath"
                  fill="rgba(99,102,241,0.07)" />
            <!-- Put fit line -->
            <path v-if="putFitPath" :d="putFitPath"
                  stroke="#f87171" stroke-width="2" fill="none"
                  stroke-linejoin="round" stroke-linecap="round" />
            <!-- Call fit line -->
            <path v-if="callFitPath" :d="callFitPath"
                  stroke="#10b981" stroke-width="2" fill="none"
                  stroke-linejoin="round" stroke-linecap="round" />
            <!-- Mid fit line -->
            <path v-if="midFitPath" :d="midFitPath"
                  stroke="#6366f1" stroke-width="2.5" fill="none"
                  stroke-linejoin="round" stroke-linecap="round"
                  stroke-dasharray="none" />
          </template>

          <!-- ─── Raw paths (when fit off) ─────────────────────────────── -->
          <template v-if="!showFit">
            <path v-if="putRawPath" :d="putRawPath"
                  stroke="#f87171" stroke-width="1.5" fill="none" stroke-linejoin="round" />
            <path v-if="callRawPath" :d="callRawPath"
                  stroke="#10b981" stroke-width="1.5" fill="none" stroke-linejoin="round" />
            <path v-if="midRawPath" :d="midRawPath"
                  stroke="#6366f1" stroke-width="2" fill="none" stroke-linejoin="round" />
          </template>

          <!-- Hover crosshair -->
          <line v-if="hoverData"
                :x1="hoverData.svgX" :x2="hoverData.svgX" :y1="padT" :y2="H - padB"
                stroke="rgba(255,255,255,0.2)" stroke-width="1" stroke-dasharray="2,2" />
          <circle v-if="hoverData && hoverData.svgY != null"
                  :cx="hoverData.svgX" :cy="hoverData.svgY" r="4"
                  fill="#f59e0b" fill-opacity="0.9" />

          <!-- X labels (moneyness) -->
          <text v-for="lbl in xLabels" :key="'xl' + lbl.m"
                :x="lbl.x" :y="H - padB + 12"
                fill="#475569" font-size="8" text-anchor="middle">
            {{ lbl.label }}
          </text>

          <!-- Y labels (% IV) -->
          <text v-for="t in yTicks" :key="'yl' + t.val"
                :x="padL - 4" :y="t.py"
                fill="#334155" font-size="8" text-anchor="end" dominant-baseline="middle">
            {{ (t.val * 100).toFixed(0) }}%
          </text>

          <!-- Legend -->
          <rect x="4" y="4" width="7" height="7" rx="1" fill="#10b981" opacity="0.9" />
          <text x="14" y="11" fill="#94a3b8" font-size="8">Call</text>
          <rect x="36" y="4" width="7" height="7" rx="1" fill="#f87171" opacity="0.9" />
          <text x="46" y="11" fill="#94a3b8" font-size="8">Put</text>
          <rect x="68" y="4" width="7" height="7" rx="1" fill="#6366f1" opacity="0.9" />
          <text x="78" y="11" fill="#94a3b8" font-size="8">Mid</text>
        </svg>

        <!-- Tooltip -->
        <div class="iv-tt" v-if="hoverData" :style="ttStyle(hoverData.px, hoverData.py)">
          <div class="tt-head">
            {{ hoverData.mPct >= 0 ? '+' : '' }}{{ hoverData.mPct.toFixed(1) }}%
            <span class="tt-strike"> ({{ (hoverData.strike / 1000).toFixed(0) }}k)</span>
          </div>
          <div class="tt-row" v-if="hoverData.ivCall != null">
            <span class="tt-lbl">Call IV</span>
            <span class="tt-pos">{{ (hoverData.ivCall * 100).toFixed(2) }}%</span>
          </div>
          <div class="tt-row" v-if="hoverData.ivPut != null">
            <span class="tt-lbl">Put IV</span>
            <span class="tt-neg">{{ (hoverData.ivPut * 100).toFixed(2) }}%</span>
          </div>
          <div class="tt-row" v-if="hoverData.ivMid != null">
            <span class="tt-lbl">Mid IV</span>
            <span>{{ (hoverData.ivMid * 100).toFixed(2) }}%</span>
          </div>
          <div class="tt-row" v-if="hoverData.ivCall != null && hoverData.ivPut != null">
            <span class="tt-lbl">Skew (P-C)</span>
            <span :class="(hoverData.ivPut - hoverData.ivCall) > 0 ? 'tt-neg' : 'tt-pos'">
              {{ ((hoverData.ivPut - hoverData.ivCall) * 100).toFixed(2) }}%
            </span>
          </div>
          <div class="tt-row" v-if="showFit && hoverData.fitMid != null">
            <span class="tt-lbl">Fit IV</span>
            <span class="tt-fit">{{ (hoverData.fitMid * 100).toFixed(2) }}%</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({ modelData: { type: Object, default: null } })

const W = 600; const H = 220
const padL = 38; const padR = 12; const padT = 20; const padB = 26

const selectedExpiry = ref(null)
const hoverData      = ref(null)
const rootEl         = ref(null)
const showFit        = ref(true)
const showRaw        = ref(false)

// ─── Source data ─────────────────────────────────────────────────────────────

const spot    = computed(() => props.modelData?.market_context?.spot_price ?? null)
const spotFmt = computed(() => spot.value ? (spot.value / 1000).toFixed(1) + 'k' : '—')

// Parse rows from aggregates.by_strike — normalised in DiscoveryView
const optionIvRows = computed(() => {
  const surfacePoints = props.modelData?.vol_surface_points ?? []
  if (Array.isArray(surfacePoints) && surfacePoints.length) {
    return surfacePoints
      .map(r => ({
        strike: parseFloat(r.strike ?? 0),
        expiry: r.expiry ?? null,
        dte: Number(r.dte ?? null),
        putCall: String(r.put_call ?? '').trim(),
        iv: _pos(r.iv),
      }))
      .filter(r => r.strike > 0 && r.expiry && r.iv != null)
  }

  const prepared = props.modelData?.prepared_options ?? []
  return prepared
    .map(r => ({
      strike: parseFloat(r.strike ?? 0),
      expiry: r.expiry_date ?? null,
      dte: Number(r.days_to_expiry_business ?? r.days_to_expiry_calendar ?? null),
      putCall: String(r.put_call ?? '').trim(),
      iv: _pos(r.selected_iv ?? r.iv_mid ?? r.iv_last ?? r.iv_bid ?? r.iv_ask),
    }))
    .filter(r => r.strike > 0 && r.expiry && r.iv != null)
})

const strikeRows = computed(() => {
  const grouped = new Map()

  optionIvRows.value.forEach(r => {
    const key = `${r.expiry}::${r.strike}`
    if (!grouped.has(key)) {
      grouped.set(key, {
        strike: r.strike,
        expiry: r.expiry,
        dte: Number.isFinite(r.dte) ? r.dte : null,
        ivCall: null,
        ivPut: null,
      })
    }
    const row = grouped.get(key)
    if (/^call$/i.test(r.putCall)) row.ivCall = r.iv
    if (/^put$/i.test(r.putCall)) row.ivPut = r.iv
  })

  return Array.from(grouped.values())
    .map(r => {
      const ivMid = r.ivCall != null && r.ivPut != null ? (r.ivCall + r.ivPut) / 2
        : (r.ivCall ?? r.ivPut ?? null)
      const S = spot.value
      const mono = S && r.strike > 0 ? Math.log(r.strike / S) : null
      return { ...r, ivMid, mono }
    })
    .filter(r => r.strike > 0 && (r.ivCall != null || r.ivPut != null))
    .sort((a, b) => {
      const dteDiff = Number(a.dte ?? 9999) - Number(b.dte ?? 9999)
      if (dteDiff !== 0) return dteDiff
      if (a.expiry !== b.expiry) return String(a.expiry).localeCompare(String(b.expiry))
      return a.strike - b.strike
    })
})

function _pos(v) {
  const n = parseFloat(v)
  return !isNaN(n) && n > 0.001 && n < 5 ? n : null
}

// ─── Expiry selector ─────────────────────────────────────────────────────────

const expiries = computed(() => {
  const set = new Map()
  strikeRows.value.forEach(r => {
    if (r.expiry && !set.has(r.expiry)) {
      set.set(r.expiry, {
        key: r.expiry,
        label: Number.isFinite(r.dte) ? `${r.expiry} · ${r.dte}du` : r.expiry,
        dte: Number.isFinite(r.dte) ? r.dte : 9999,
      })
    }
  })
  const sorted = Array.from(set.values()).sort((a, b) => {
    const dteDiff = Number(a.dte ?? 9999) - Number(b.dte ?? 9999)
    if (dteDiff !== 0) return dteDiff
    return String(a.key).localeCompare(String(b.key))
  })
  return [
    { key: 'all', label: 'Todos venc.' },
    ...sorted.map(e => ({ key: e.key, label: e.label })),
  ]
})

watch(expiries, (v) => {
  if (!v.find(e => e.key === selectedExpiry.value)) {
    selectedExpiry.value = v.find(e => e.key !== 'all')?.key ?? v[0]?.key ?? 'all'
  }
}, { immediate: true })

const filtered = computed(() => {
  if (!selectedExpiry.value || selectedExpiry.value === 'all') return strikeRows.value
  return strikeRows.value.filter(r => r.expiry === selectedExpiry.value)
})

const hasData = computed(() => filtered.value.length >= 3)

// ─── Axis domain ──────────────────────────────────────────────────────────────

// x-axis: log-moneyness from -15% to +15% (clipped at data range)
const MONO_RANGE = 0.15
const xDomain = computed(() => {
  const monos = filtered.value.map(r => r.mono).filter(m => m != null)
  if (!monos.length) return { lo: -MONO_RANGE, hi: MONO_RANGE }
  const lo = Math.max(-MONO_RANGE, Math.min(...monos) - 0.01)
  const hi = Math.min( MONO_RANGE, Math.max(...monos) + 0.01)
  return { lo, hi }
})

function xOf(mono) {
  const { lo, hi } = xDomain.value
  const range = hi - lo || 0.01
  return padL + ((mono - lo) / range) * (W - padL - padR)
}
// y-axis: IV domain
const allIvs = computed(() =>
  filtered.value.flatMap(r => [r.ivCall, r.ivPut, r.ivMid].filter(v => v != null))
)
const minIv = computed(() => Math.max(0.01, (Math.min(...allIvs.value, 0.05) - 0.02)))
const maxIv = computed(() => Math.max(...allIvs.value, 0.12) + 0.03)

function yOf(iv) {
  const range = maxIv.value - minIv.value || 0.01
  return padT + (1 - (iv - minIv.value) / range) * (H - padT - padB)
}

// ─── Polynomial smile fit (weighted, degree 3 in log-moneyness) ──────────────

/**
 * Weighted least-squares polynomial fit.
 * Weights: gaussian ATM (σ=0.10) + floor 0.1 to keep wing curvature.
 * Returns coefficients [c0, c1, c2, c3] such that IV(m) = c0 + c1*m + c2*m² + c3*m³
 */
function fitPoly(pts) {
  if (pts.length < 4) return null
  const degree = 3
  const n = degree + 1

  // Weights: centre ATM options more heavily
  const w = pts.map(p => Math.exp(-50 * p.m * p.m) + 0.15)

  // Build weighted Vandermonde normal equations: (A^T W A) c = A^T W y
  // A_ij = m_i^j
  const AtWA = Array.from({ length: n }, () => new Array(n).fill(0))
  const AtWy = new Array(n).fill(0)

  for (let i = 0; i < pts.length; i++) {
    const mi  = pts[i].m
    const yi  = pts[i].iv
    const wi  = w[i]
    const row = Array.from({ length: n }, (_, j) => Math.pow(mi, j))
    for (let r = 0; r < n; r++) {
      AtWy[r] += wi * row[r] * yi
      for (let c = 0; c < n; c++) {
        AtWA[r][c] += wi * row[r] * row[c]
      }
    }
  }

  // Gaussian elimination with partial pivoting
  const aug = AtWA.map((row, i) => [...row, AtWy[i]])
  for (let col = 0; col < n; col++) {
    // Find pivot
    let maxRow = col
    for (let r = col + 1; r < n; r++) {
      if (Math.abs(aug[r][col]) > Math.abs(aug[maxRow][col])) maxRow = r
    }
    ;[aug[col], aug[maxRow]] = [aug[maxRow], aug[col]]
    if (Math.abs(aug[col][col]) < 1e-14) return null
    for (let r = 0; r < n; r++) {
      if (r === col) continue
      const factor = aug[r][col] / aug[col][col]
      for (let c = col; c <= n; c++) {
        aug[r][c] -= factor * aug[col][c]
      }
    }
  }
  return aug.map((row, i) => row[n] / row[i])
}

function evalPoly(coeffs, m) {
  return coeffs.reduce((sum, c, i) => sum + c * Math.pow(m, i), 0)
}

// Build smooth fit points across the x domain
const FIT_COLS = 80

function buildFitCurve(rawPts) {
  const validPts = rawPts.filter(p => p.m != null && p.iv != null && isFinite(p.iv))
  if (validPts.length < 4) return null
  const coeffs = fitPoly(validPts)
  if (!coeffs) return null
  const { lo, hi } = xDomain.value
  const step = (hi - lo) / (FIT_COLS - 1)
  const pts = []
  for (let i = 0; i < FIT_COLS; i++) {
    const m  = lo + i * step
    const iv = evalPoly(coeffs, m)
    if (iv >= 0.005 && iv < 5) pts.push({ m, iv, x: xOf(m), y: yOf(iv) })
  }
  return { pts, coeffs }
}

const callFitData = computed(() => {
  const pts = filtered.value
    .filter(r => r.ivCall != null && r.mono != null)
    .map(r => ({ m: r.mono, iv: r.ivCall }))
  return buildFitCurve(pts)
})

const putFitData = computed(() => {
  const pts = filtered.value
    .filter(r => r.ivPut != null && r.mono != null)
    .map(r => ({ m: r.mono, iv: r.ivPut }))
  return buildFitCurve(pts)
})

const midFitData = computed(() => {
  const pts = filtered.value
    .filter(r => r.mono != null)
    .map(r => ({
      m:  r.mono,
      iv: r.ivMid ?? ((r.ivCall != null && r.ivPut != null)
                      ? (r.ivCall + r.ivPut) / 2
                      : (r.ivCall ?? r.ivPut))
    }))
    .filter(p => p.iv != null)
  return buildFitCurve(pts)
})

function pathFromPts(pts) {
  if (!pts || pts.length < 2) return null
  return pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
}

const callFitPath = computed(() => pathFromPts(callFitData.value?.pts))
const putFitPath  = computed(() => pathFromPts(putFitData.value?.pts))
const midFitPath  = computed(() => pathFromPts(midFitData.value?.pts))

const combinedFillPath = computed(() => {
  const cp = callFitData.value?.pts
  const pp = putFitData.value?.pts
  if (!cp?.length || !pp?.length) return null
  const forward  = cp.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
  const backward = [...pp].reverse().map(p => `L${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
  return `${forward} ${backward} Z`
})

// ─── Raw paths ───────────────────────────────────────────────────────────────

const rawCallPts = computed(() =>
  filtered.value
    .filter(r => r.ivCall != null && r.mono != null)
    .map(r => ({ strike: r.strike, x: xOf(r.mono), y: yOf(r.ivCall) }))
)
const rawPutPts = computed(() =>
  filtered.value
    .filter(r => r.ivPut != null && r.mono != null)
    .map(r => ({ strike: r.strike, x: xOf(r.mono), y: yOf(r.ivPut) }))
)

function rawPath(key) {
  const pts = filtered.value.filter(r => r[key] != null && r.mono != null)
  if (pts.length < 2) return null
  return pts.map((r, i) => `${i === 0 ? 'M' : 'L'}${xOf(r.mono).toFixed(1)},${yOf(r[key]).toFixed(1)}`).join(' ')
}

const callRawPath = computed(() => rawPath('ivCall'))
const putRawPath  = computed(() => rawPath('ivPut'))
const midRawPath  = computed(() => rawPath('ivMid'))

// ─── Summary stats ────────────────────────────────────────────────────────────

const atmIv = computed(() => {
  if (!spot.value || !filtered.value.length) return null
  const closest = filtered.value.reduce((a, b) =>
    Math.abs(b.strike - spot.value) < Math.abs(a.strike - spot.value) ? b : a
  )
  return closest.ivMid ?? closest.ivCall ?? closest.ivPut ?? null
})

// 25-delta skew approximation: IV at log-moneyness = ±0.10 (≈ ±10%)
const skew25 = computed(() => {
  const cd = callFitData.value?.coeffs
  const pd = putFitData.value?.coeffs
  if (!cd || !pd) return null
  const ivCall10 = evalPoly(cd,  0.10)  // OTM call (10% above ATM)
  const ivPut10  = evalPoly(pd, -0.10)  // OTM put (10% below ATM)
  const skew = ivPut10 - ivCall10
  return isFinite(skew) ? skew : null
})

// ─── Spot line ────────────────────────────────────────────────────────────────

const spotX = computed(() => {
  if (!spot.value) return null
  return xOf(0)  // log(S/S) = 0
})

// ─── Axis labels ─────────────────────────────────────────────────────────────

const yTicks = computed(() => {
  const mn = minIv.value, mx = maxIv.value
  const step = (mx - mn) / 4
  return Array.from({ length: 5 }, (_, i) => {
    const v = mn + i * step
    return { val: v, py: yOf(v) }
  })
})

// x labels: moneyness %
const xLabels = computed(() => {
  const { lo, hi } = xDomain.value
  const steps = [-0.12, -0.08, -0.04, 0, 0.04, 0.08, 0.12]
    .filter(m => m >= lo - 0.005 && m <= hi + 0.005)
  return steps.map(m => ({
    m,
    x: xOf(m),
    label: m === 0 ? 'ATM' : `${m > 0 ? '+' : ''}${(m * 100).toFixed(0)}%`,
  }))
})

// ─── Hover ────────────────────────────────────────────────────────────────────

function onHover(e) {
  if (!filtered.value.length) return
  const rect = e.currentTarget.getBoundingClientRect()
  const px   = e.clientX - rect.left
  const py   = e.clientY - rect.top
  const svgX = (px / rect.width) * W
  const { lo, hi } = xDomain.value
  const monoHover = lo + ((svgX - padL) / (W - padL - padR)) * (hi - lo)

  // Find nearest raw data point
  let nearest = null, minD = Infinity
  for (const r of filtered.value) {
    if (r.mono == null) continue
    const d = Math.abs(r.mono - monoHover)
    if (d < minD) { minD = d; nearest = r }
  }
  if (!nearest) { hoverData.value = null; return }

  const svgXn = xOf(nearest.mono)
  const ivMidHover = nearest.ivMid ?? ((nearest.ivCall != null && nearest.ivPut != null)
    ? (nearest.ivCall + nearest.ivPut) / 2
    : (nearest.ivCall ?? nearest.ivPut))
  const svgY = ivMidHover != null ? yOf(ivMidHover) : null

  // Fit IV at this moneyness
  const coeffsMid = midFitData.value?.coeffs
  const fitMid = coeffsMid ? evalPoly(coeffsMid, nearest.mono) : null

  hoverData.value = {
    px, py, svgX: svgXn, svgY,
    strike:  nearest.strike,
    mPct:    nearest.mono * 100,
    ivCall:  nearest.ivCall,
    ivPut:   nearest.ivPut,
    ivMid:   ivMidHover,
    fitMid:  fitMid != null && fitMid > 0.001 ? fitMid : null,
  }
}

function ttStyle(px, py) {
  const rootW = rootEl.value?.offsetWidth ?? 400
  const x = Math.max(60, Math.min(rootW - 60, px))
  return { left: x + 'px', top: Math.max(8, py - 110) + 'px' }
}
</script>

<style scoped>
.iv-widget { height: 100%; display: flex; flex-direction: column; padding: 8px; gap: 6px; }
.iv-empty  { color: #475569; font-size: 12px; padding: 20px; text-align: center; }

.iv-controls {
  display: flex; align-items: center; gap: 6px; flex-shrink: 0;
  flex-wrap: wrap;
}
.iv-select {
  padding: 2px 6px; border-radius: 4px;
  background: #0a1120; border: 1px solid rgba(255,255,255,0.1);
  color: #94a3b8; font-size: 10px; cursor: pointer; outline: none;
}
.iv-select:focus { border-color: #6366f1; }

.iv-btn {
  padding: 2px 7px; border-radius: 4px;
  border: 1px solid rgba(255,255,255,0.08);
  background: transparent; color: #64748b;
  font-size: 10px; font-weight: 600; cursor: pointer; transition: all 0.15s;
}
.iv-btn.active { background: #1e1b4b; border-color: #6366f1; color: #a5b4fc; }
.iv-btn:hover:not(.active) { background: rgba(255,255,255,0.05); color: #94a3b8; }

.iv-atm-label   { font-size: 10px; color: #f59e0b; }
.iv-atm-label b { font-size: 11px; }
.iv-skew-label  { font-size: 10px; color: #94a3b8; }
.iv-skew-label b { font-size: 11px; }
.skew-pos { color: #ef4444; }
.skew-neg { color: #10b981; }
.iv-spot-label  { margin-left: auto; font-size: 10px; color: #f59e0b; font-weight: 600; }

.iv-chart-wrap { position: relative; flex: 1; min-height: 0; display: flex; flex-direction: column; }
.iv-svg { flex: 1; width: 100%; min-height: 0; cursor: crosshair; }

/* Tooltip */
.iv-tt {
  position: absolute; pointer-events: none;
  transform: translateX(-50%);
  background: #0a1120; border: 1px solid rgba(255,255,255,0.14);
  border-radius: 5px; padding: 6px 10px;
  font-size: 10px; color: #e2e8f0;
  white-space: nowrap; z-index: 20; min-width: 150px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.5);
}
.tt-head { font-weight: 700; color: #f59e0b; margin-bottom: 4px; font-size: 11px; }
.tt-strike { font-weight: 400; color: #64748b; font-size: 9px; }
.tt-row  { display: flex; justify-content: space-between; gap: 14px; line-height: 1.7; }
.tt-lbl  { color: #475569; }
.tt-pos  { color: #10b981; }
.tt-neg  { color: #f87171; }
.tt-fit  { color: #818cf8; }
</style>

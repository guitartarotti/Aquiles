<template>
  <div class="vsdr-root">
    <div class="vsdr-header">
      <div class="vsdr-title-block">
        <span class="vsdr-title">Vol Surface Distortion Radar</span>
        <span class="vsdr-subtitle">ATM, wings, skew, convexity, term e liquidez</span>
      </div>
      <div class="vsdr-controls">
        <span class="vsdr-underlying">{{ shortUnderlying }}</span>
        <button type="button" class="vsdr-btn" :class="{ loading }" :disabled="loading" @click="loadSurface(true)">
          {{ loading ? '...' : 'Reload' }}
        </button>
      </div>
    </div>

    <div v-if="error && !snapshot" class="vsdr-empty">{{ error }}</div>
    <div v-else-if="loading && !snapshot" class="vsdr-empty">Loading vol surface...</div>
    <div v-else-if="!snapshot" class="vsdr-empty">Waiting for IV surface points with strike, expiry and bid/ask.</div>

    <template v-else>
      <div class="vsdr-hero">
        <div class="vsdr-score-card">
          <div class="vsdr-score-ring" :style="scoreRingStyle">
            <span class="vsdr-score-value">{{ formatScore(snapshot.score) }}</span>
            <span class="vsdr-score-max">/100</span>
          </div>
          <div class="vsdr-score-copy">
            <span class="vsdr-badge" :class="snapshot.tone">{{ snapshot.classification }}</span>
            <span class="vsdr-reading">{{ snapshot.reading }}</span>
            <span class="vsdr-stamp">{{ surfaceStamp }}</span>
          </div>
        </div>

        <div class="vsdr-metric-grid">
          <div class="vsdr-metric">
            <span class="vsdr-metric-label">Dominante</span>
            <span class="vsdr-metric-value">{{ snapshot.dominant.label }}</span>
            <span class="vsdr-metric-sub">score {{ formatScore(snapshot.dominant.score) }}</span>
          </div>
          <div class="vsdr-metric">
            <span class="vsdr-metric-label">Regiao</span>
            <span class="vsdr-metric-value">{{ snapshot.affectedRegion }}</span>
            <span class="vsdr-metric-sub">{{ snapshot.affectedExpiry }}</span>
          </div>
          <div class="vsdr-metric">
            <span class="vsdr-metric-label">Z-score</span>
            <span class="vsdr-metric-value" :class="zTone(snapshot.dominant.z)">{{ formatZ(snapshot.dominant.z) }}</span>
            <span class="vsdr-metric-sub">{{ snapshot.pointCount }} pontos validos</span>
          </div>
          <div class="vsdr-metric">
            <span class="vsdr-metric-label">Confianca</span>
            <span class="vsdr-metric-value">{{ formatScore(snapshot.confidence) }}%</span>
            <span class="vsdr-metric-sub">{{ snapshot.confidenceLabel }}</span>
          </div>
        </div>
      </div>

      <div v-if="snapshot.alerts.length" class="vsdr-alerts">
        <span v-for="alert in snapshot.alerts" :key="alert" class="vsdr-alert">{{ alert }}</span>
      </div>

      <div class="vsdr-main-grid">
        <div class="vsdr-panel radar-panel">
          <div class="vsdr-panel-head">
            <span class="vsdr-panel-title">Radar</span>
            <span class="vsdr-panel-sub">score por componente</span>
          </div>
          <svg class="vsdr-radar" viewBox="-130 -120 260 250" role="img" aria-label="Surface distortion radar">
            <polygon
              v-for="level in radarLevels"
              :key="level"
              class="vsdr-radar-grid"
              :points="radarGridPoints(level)"
            />
            <g v-for="axis in radarAxes" :key="axis.key">
              <line class="vsdr-radar-axis" x1="0" y1="0" :x2="axis.end.x" :y2="axis.end.y" />
              <circle class="vsdr-radar-dot" :cx="axis.valuePoint.x" :cy="axis.valuePoint.y" r="2.6" />
              <text class="vsdr-radar-label" :x="axis.labelPoint.x" :y="axis.labelPoint.y" text-anchor="middle">
                {{ axis.label }}
              </text>
            </g>
            <polygon class="vsdr-radar-fill" :points="radarValuePoints" />
            <polygon class="vsdr-radar-line" :points="radarValuePoints" />
          </svg>
        </div>

        <div class="vsdr-panel heatmap-panel">
          <div class="vsdr-panel-head">
            <span class="vsdr-panel-title">Heatmap da distorcao</span>
            <span class="vsdr-panel-sub">cor = z-score observado vs teorico</span>
          </div>
          <div class="vsdr-heatmap">
            <div class="vsdr-heat-corner">DTE</div>
            <div v-for="bucket in HEATMAP_BUCKETS" :key="bucket.key" class="vsdr-heat-x">{{ bucket.label }}</div>
            <template v-for="row in heatmapRows" :key="row.key">
              <div class="vsdr-heat-y">{{ row.label }}</div>
              <div
                v-for="cell in row.cells"
                :key="cell.key"
                class="vsdr-heat-cell"
                :class="{ empty: !cell.count }"
                :title="cell.title"
                :style="{ backgroundColor: heatColor(cell.z, cell.count) }"
              >
                <span v-if="cell.count">{{ formatHeatZ(cell.z) }}</span>
              </div>
            </template>
          </div>
          <div class="vsdr-legend">
            <span>barato</span>
            <i class="vsdr-grad"></i>
            <span>caro</span>
          </div>
        </div>
      </div>

      <div class="vsdr-component-strip">
        <div v-for="component in snapshot.components" :key="component.key" class="vsdr-component">
          <div class="vsdr-component-head">
            <span>{{ component.label }}</span>
            <b>{{ formatScore(component.score) }}</b>
          </div>
          <div class="vsdr-component-track">
            <div class="vsdr-component-fill" :class="component.tone" :style="{ width: `${component.score}%` }"></div>
          </div>
          <span class="vsdr-component-sub">{{ formatZ(component.z) }} z</span>
        </div>
      </div>

      <div class="vsdr-bottom-grid">
        <div class="vsdr-panel">
          <div class="vsdr-panel-head">
            <span class="vsdr-panel-title">Top 5 distorcoes</span>
            <span class="vsdr-panel-sub">liquidez ajusta o ranking</span>
          </div>
          <div class="vsdr-table">
            <div class="vsdr-row head">
              <span>Ticker</span>
              <span>Strike</span>
              <span>Venc.</span>
              <span>IV obs.</span>
              <span>IV teor.</span>
              <span>Z</span>
              <span>Vol</span>
              <span>OI</span>
            </div>
            <div v-for="item in snapshot.topDistortions" :key="item.key" class="vsdr-row">
              <span class="ticker" :title="item.ticker">{{ item.ticker }}</span>
              <span>{{ formatStrike(item.strike) }}</span>
              <span>{{ formatExpiry(item.expiry, item.dte) }}</span>
              <span>{{ formatPct(item.iv) }}</span>
              <span>{{ formatPct(item.theoreticalIv) }}</span>
              <span :class="zTone(item.z)">{{ formatZ(item.z) }}</span>
              <span>{{ formatInt(item.volume) }}</span>
              <span>{{ formatInt(item.openInt) }}</span>
            </div>
          </div>
        </div>

        <div class="vsdr-panel">
          <div class="vsdr-panel-head">
            <span class="vsdr-panel-title">Leitura operacional</span>
            <span class="vsdr-panel-sub">o que a superficie esta dizendo</span>
          </div>
          <div class="vsdr-explain">
            <div class="vsdr-explain-main">{{ snapshot.explanation }}</div>
            <div class="vsdr-explain-list">
              <span v-for="item in snapshot.notes" :key="item">{{ item }}</span>
            </div>
            <div class="vsdr-method">
              IV teorica por polinomio robusto no smile de cada vencimento; quando ha historico intraday suficiente, os componentes usam blend com z-score historico. Pontos sem liquidez perdem peso.
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { getVolSurface, getVolumeIvHistory } from '@/api/options'

const props = defineProps({
  modelData: { type: Object, default: null },
  underlyingSecurity: { type: String, default: 'IBOVE Index' },
  refreshNonce: { type: Number, default: 0 },
})

const HEATMAP_BUCKETS = [
  { key: 'put10', label: '10D P', min: -0.16, max: -0.075 },
  { key: 'put25', label: '25D P', min: -0.075, max: -0.035 },
  { key: 'putBody', label: 'Put', min: -0.035, max: -0.015 },
  { key: 'atm', label: 'ATM', min: -0.015, max: 0.015 },
  { key: 'callBody', label: 'Call', min: 0.015, max: 0.035 },
  { key: 'call25', label: '25D C', min: 0.035, max: 0.075 },
  { key: 'call10', label: '10D C', min: 0.075, max: 0.16 },
]

const RADAR_LABELS = [
  { key: 'atm', label: 'ATM' },
  { key: 'putWing', label: 'Put Wing' },
  { key: 'callWing', label: 'Call Wing' },
  { key: 'skew', label: 'Skew' },
  { key: 'convexity', label: 'Convexity' },
  { key: 'term', label: 'Term' },
  { key: 'liquidity', label: 'Liquidity' },
]

const SCORE_WEIGHTS = {
  atm: 0.16,
  putWing: 0.18,
  callWing: 0.14,
  skew: 0.16,
  convexity: 0.12,
  term: 0.14,
  liquidity: 0.10,
}

const loading = ref(false)
const error = ref('')
const surfaceData = ref(null)
const historyRows = ref([])
const loadedAt = ref(null)

const underlying = computed(() =>
  props.underlyingSecurity || props.modelData?.underlying_security || 'IBOVE Index'
)

const shortUnderlying = computed(() => {
  const value = String(underlying.value || '')
  return value.replace(/\s+Index$/i, '').replace(/^IBOVE$/i, 'IBOV')
})

const surfaceStamp = computed(() => {
  if (!loadedAt.value) return 'surface snapshot'
  return `surface ${loadedAt.value.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}`
})

async function loadSurface(force = false) {
  loading.value = true
  error.value = ''
  try {
    const [surfaceResult, historyResult] = await Promise.allSettled([
      getVolSurface({
        underlying_security: underlying.value,
        tier: 'all',
        min_dte: 1,
        max_dte: 180,
        refresh: force ? 1 : 0,
      }),
      getVolumeIvHistory({
        underlying_security: underlying.value,
        lookback_days: 5,
        limit: 1200,
      }),
    ])

    if (surfaceResult.status === 'rejected') throw surfaceResult.reason
    const res = surfaceResult.value
    const payload = res?.data ?? res
    if (payload?.success === false) throw new Error(payload.error || 'Erro ao carregar superficie')
    const data = payload?.data ?? payload
    surfaceData.value = data

    if (historyResult.status === 'fulfilled') {
      const historyPayload = historyResult.value?.data ?? historyResult.value
      historyRows.value = Array.isArray(historyPayload?.data?.history)
        ? historyPayload.data.history
        : []
    } else {
      historyRows.value = []
    }

    loadedAt.value = new Date()
  } catch (exc) {
    error.value = exc?.message || 'Erro ao carregar superficie de volatilidade'
  } finally {
    loading.value = false
  }
}

onMounted(() => loadSurface(false))

watch(underlying, () => loadSurface(false))
watch(() => props.refreshNonce, (next, prev) => {
  if (next && next !== prev) loadSurface(false)
})

const rawPoints = computed(() => {
  const slices = Array.isArray(surfaceData.value?.slices) ? surfaceData.value.slices : []
  const forward = safeNumber(surfaceData.value?.forward) || safeNumber(surfaceData.value?.spot) || safeNumber(props.modelData?.market_context?.forward_price) || safeNumber(props.modelData?.market_context?.spot_price)
  const flattened = []

  for (const slice of slices) {
    const rows = Array.isArray(slice?.all)
      ? slice.all
      : [...(slice?.calls || []), ...(slice?.puts || [])]
    for (const row of rows) {
      const iv = safeNumber(row.iv_observed ?? row.iv)
      const strike = safeNumber(row.strike)
      const dte = safeNumber(row.dte ?? slice.dte)
      if (!(iv > 0.005 && iv < 4) || !(strike > 0) || !(dte >= 1)) continue

      const logM = safeNumber(row.log_m)
        ?? ((forward && strike > 0) ? Math.log(strike / forward) : null)
      if (!Number.isFinite(logM) || Math.abs(logM) > 0.24) continue

      const bid = safeNumber(row.bid)
      const ask = safeNumber(row.ask)
      const spreadPct = normalizeSpreadPct(row.spread_pct, bid, ask)
      const volume = safeNumber(row.volume)
      const openInt = safeNumber(row.open_int)
      const pc = String(row.put_call || '').trim().toLowerCase()

      flattened.push({
        key: `${row.ticker || row.symbol || strike}-${row.expiry || slice.expiry}-${pc}`,
        ticker: String(row.ticker || row.symbol || row.option_id || `${pc || 'OPT'} ${strike}`).trim(),
        strike,
        expiry: row.expiry || slice.expiry || '',
        dte,
        pc,
        iv,
        logM,
        moneyness: safeNumber(row.moneyness) ?? (Math.exp(logM) - 1),
        delta: safeNumber(row.delta),
        bid,
        ask,
        spreadPct,
        volume,
        openInt,
        marketOk: Boolean(row.market_ok),
      })
    }
  }

  return flattened
})

const analyzedPoints = computed(() => {
  const base = rawPoints.value
  if (base.length < 8) return []

  const liquidityMarks = buildLiquidityMarks(base)
  const fits = buildSmileFits(base)
  const preliminary = base.map((point) => {
    const fit = fits.get(point.expiry) || fits.get(String(point.dte))
    const theoreticalIv = fit ? clamp(evalPoly(fit.coeffs, point.logM), fit.floor, fit.cap) : point.iv
    const region = classifyRegion(point)
    const tenor = tenorBucket(point.dte)
    const liquidityScore = liquidityMarks.get(point.key) ?? 0
    const spreadPenalty = clamp((point.spreadPct ?? 0) / 0.22, 0, 1)
    const weight = (0.25 + (0.75 * liquidityScore)) * (1 - (0.45 * spreadPenalty))
    return {
      ...point,
      region,
      tenor,
      theoreticalIv,
      distortion: point.iv - theoreticalIv,
      liquidityScore,
      weight: Math.max(0.05, weight),
    }
  })

  const sigmaLookup = buildDistortionSigmas(preliminary)
  return preliminary.map((point) => {
    const sigma = sigmaLookup.get(`${point.region}:${point.tenor}`)
      || sigmaLookup.get(point.region)
      || sigmaLookup.get('global')
      || 0.006
    const z = clamp(point.distortion / Math.max(sigma, 0.0025), -5, 5)
    return { ...point, z }
  })
})

const historyStats = computed(() => buildHistoryStats(historyRows.value))

const snapshot = computed(() => {
  const points = analyzedPoints.value
  if (points.length < 8) return null

  const features = currentSurfaceFeatures(points)
  const hist = historyStats.value
  const atm = blendHistoricalComponent(summarizeRegion(points, 'atm', 'ATM'), hist.atm, features.atm)
  const putWing = blendHistoricalComponent(summarizeRegion(points, 'putWing', 'Put Wing'), hist.putWing, features.putWing)
  const callWing = blendHistoricalComponent(summarizeRegion(points, 'callWing', 'Call Wing'), hist.callWing, features.callWing)
  const skewBase = summarizeSynthetic('skew', 'Skew', putWing.z - callWing.z, Math.abs(putWing.z - callWing.z), Math.min(putWing.count, callWing.count))
  const skew = blendHistoricalComponent(skewBase, hist.skew, features.skew, 0.42)
  const convexityZ = ((putWing.z + callWing.z) / 2) - atm.z
  const convexityBase = summarizeSynthetic('convexity', 'Convexity', convexityZ, Math.abs(convexityZ), putWing.count + callWing.count)
  const convexity = blendHistoricalComponent(convexityBase, hist.convexity, features.convexity, 0.42)
  const term = blendHistoricalComponent(summarizeTerm(points), hist.term, features.term, 0.42)
  const liquidity = summarizeLiquidity(points)

  const components = [atm, putWing, callWing, skew, convexity, term, liquidity]
  const score = clamp(components.reduce((sum, component) => (
    sum + (component.score * (SCORE_WEIGHTS[component.key] || 0))
  ), 0), 0, 100)

  const dominant = [...components].sort((a, b) => b.score - a.score)[0]
  const topDistortions = topDistortionRows(points)
  const confidence = computeConfidence(points, topDistortions)
  const classification = classifySurface({ score, components, dominant, confidence })
  const reading = readingFor(classification)
  const affectedRegion = affectedStrikeRange(topDistortions)
  const affectedExpiry = affectedExpiryLabel(topDistortions)
  const tone = score >= 75 ? 'hot' : score >= 55 ? 'warm' : 'cool'
  const alerts = buildAlerts({ score, components, topDistortions, term })
  const notes = buildNotes({ components, topDistortions, confidence })

  return {
    score,
    tone,
    components,
    dominant,
    confidence,
    confidenceLabel: confidence >= 75 ? 'alta' : confidence >= 55 ? 'media' : 'baixa',
    classification,
    reading,
    explanation: explanationFor(classification, dominant),
    affectedRegion,
    affectedExpiry,
    topDistortions,
    alerts,
    notes,
    pointCount: points.length,
  }
})

const scoreRingStyle = computed(() => {
  const score = snapshot.value?.score ?? 0
  const color = score >= 75 ? '#fb7185' : score >= 55 ? '#f59e0b' : '#22c55e'
  return {
    background: `conic-gradient(${color} ${score * 3.6}deg, rgba(30, 41, 59, 0.92) 0deg)`,
  }
})

const radarLevels = [0.25, 0.5, 0.75, 1]

const radarAxes = computed(() => RADAR_LABELS.map((item, index) => {
  const component = snapshot.value?.components.find((candidate) => candidate.key === item.key)
  const score = component?.score ?? 0
  return {
    ...item,
    score,
    end: radarPoint(index, 1),
    valuePoint: radarPoint(index, score / 100),
    labelPoint: radarPoint(index, 1.17),
  }
}))

const radarValuePoints = computed(() =>
  radarAxes.value.map((axis, index) => pointString(radarPoint(index, axis.score / 100))).join(' ')
)

const heatmapRows = computed(() => {
  const points = analyzedPoints.value
  if (!points.length) return []

  const byExpiry = new Map()
  for (const point of points) {
    const key = point.expiry || String(point.dte)
    if (!byExpiry.has(key)) byExpiry.set(key, { key, expiry: point.expiry, dte: point.dte, pts: [] })
    byExpiry.get(key).pts.push(point)
  }

  const rows = Array.from(byExpiry.values()).sort((a, b) => a.dte - b.dte)
  const selected = rows.length > 10
    ? [...rows.slice(0, 7), ...rows.slice(-3)]
    : rows

  return selected.map((row) => ({
    key: row.key,
    label: `${Math.round(row.dte)}d`,
    cells: HEATMAP_BUCKETS.map((bucket) => {
      const bucketPoints = row.pts.filter((point) => point.logM >= bucket.min && point.logM < bucket.max)
      const z = weightedMedian(bucketPoints.map((point) => point.z), bucketPoints.map((point) => point.weight))
      return {
        key: `${row.key}:${bucket.key}`,
        z: z ?? 0,
        count: bucketPoints.length,
        title: bucketPoints.length
          ? `${row.expiry || `${Math.round(row.dte)}d`} ${bucket.label}: ${formatZ(z)} (${bucketPoints.length} pts)`
          : `${row.expiry || `${Math.round(row.dte)}d`} ${bucket.label}: sem pontos`,
      }
    }),
  }))
})

function buildHistoryStats(rows) {
  const clean = Array.isArray(rows) ? rows : []
  const values = {
    atm: [],
    putWing: [],
    callWing: [],
    skew: [],
    convexity: [],
    term: [],
  }

  for (const row of clean) {
    const atm = safeNumber(row.iv_atm ?? row.iv_interpolated)
    const put25 = safeNumber(row.iv_25d_put ?? row.iv_15d_put ?? row.iv_10d_put)
    const call25 = safeNumber(row.iv_25d_call ?? row.iv_15d_call ?? row.iv_10d_call)
    const put10 = safeNumber(row.iv_10d_put ?? row.iv_25d_put)
    const call10 = safeNumber(row.iv_10d_call ?? row.iv_25d_call)
    const skew = safeNumber(row.skew_25d) ?? ((put25 != null && call25 != null) ? put25 - call25 : null)
    const convexity = (put10 != null && call10 != null && atm != null)
      ? ((put10 + call10) / 2) - atm
      : null
    const term = historyTermSlope(row)

    if (atm != null) values.atm.push(atm)
    if (put25 != null) values.putWing.push(put25)
    if (call25 != null) values.callWing.push(call25)
    if (skew != null) values.skew.push(skew)
    if (convexity != null) values.convexity.push(convexity)
    if (term != null) values.term.push(term)
  }

  return Object.fromEntries(Object.entries(values).map(([key, series]) => [key, historyStat(series)]))
}

function historyTermSlope(row) {
  const termStructure = Array.isArray(row.term_structure) ? row.term_structure : []
  const short = termStructure
    .filter((item) => safeNumber(item.dte) != null && safeNumber(item.dte) <= 15)
    .map((item) => safeNumber(item.iv_atm))
    .filter(Number.isFinite)
  const medium = termStructure
    .filter((item) => {
      const dte = safeNumber(item.dte)
      return dte != null && dte > 20 && dte <= 70
    })
    .map((item) => safeNumber(item.iv_atm))
    .filter(Number.isFinite)
  const shortIv = mean(short) ?? safeNumber(row.iv_atm)
  const mediumIv = mean(medium) ?? safeNumber(row.monthly_term_30d_iv)
  return shortIv != null && mediumIv != null ? shortIv - mediumIv : null
}

function historyStat(values) {
  const clean = values.filter(Number.isFinite)
  if (clean.length < 8) return null
  const center = median(clean)
  const sigma = Math.max(robustSigma(clean) || std(clean) || 0, 0.0025)
  return center != null ? { center, sigma, count: clean.length } : null
}

function blendHistoricalComponent(component, stat, currentValue, histWeight = 0.34) {
  if (!stat || currentValue == null || !Number.isFinite(currentValue)) return component
  const histZ = clamp((currentValue - stat.center) / stat.sigma, -5, 5)
  const blendedZ = clamp((component.z * (1 - histWeight)) + (histZ * histWeight), -5, 5)
  const blendedAbs = (Math.abs(component.z) * (1 - histWeight)) + (Math.abs(histZ) * histWeight)
  return {
    ...component,
    z: blendedZ,
    score: Math.max(component.score * 0.78, scoreFromZ(blendedAbs)),
    historyCount: stat.count,
  }
}

function currentSurfaceFeatures(points) {
  const atm = regionIv(points, 'atm')
  const putWing = regionIv(points, 'putWing')
  const callWing = regionIv(points, 'callWing')
  return {
    atm,
    putWing,
    callWing,
    skew: putWing != null && callWing != null ? putWing - callWing : null,
    convexity: putWing != null && callWing != null && atm != null ? ((putWing + callWing) / 2) - atm : null,
    term: termSlopeFromPoints(points),
  }
}

function regionIv(points, region) {
  const sample = points.filter((point) => point.region === region)
  return weightedMean(sample.map((point) => point.iv), sample.map((point) => point.weight))
}

function termSlopeFromPoints(points) {
  const near = points.filter((point) => point.dte <= 15 && (point.region === 'atm' || Math.abs(point.logM) <= 0.035))
  const mid = points.filter((point) => point.dte > 20 && point.dte <= 70 && (point.region === 'atm' || Math.abs(point.logM) <= 0.035))
  const nearIv = weightedMean(near.map((point) => point.iv), near.map((point) => point.weight))
  const midIv = weightedMean(mid.map((point) => point.iv), mid.map((point) => point.weight))
  return nearIv != null && midIv != null ? nearIv - midIv : null
}

function buildSmileFits(points) {
  const grouped = new Map()
  for (const point of points) {
    const key = point.expiry || String(point.dte)
    if (!grouped.has(key)) grouped.set(key, [])
    grouped.get(key).push(point)
  }

  const fits = new Map()
  for (const [key, pts] of grouped.entries()) {
    const clean = pts
      .filter((point) => Number.isFinite(point.logM) && Number.isFinite(point.iv))
      .sort((a, b) => a.logM - b.logM)
    if (!clean.length) continue

    const ivs = clean.map((point) => point.iv)
    const med = median(ivs) ?? 0.22
    const sigma = robustSigma(ivs) || Math.max(med * 0.18, 0.015)
    const inliers = clean.filter((point) => Math.abs(point.iv - med) <= (3.5 * sigma))
    const sample = inliers.length >= 4 ? inliers : clean
    const coeffs = fitWeightedPoly(sample)
    fits.set(key, {
      coeffs,
      floor: Math.max(0.01, med - (3.0 * sigma), med * 0.35),
      cap: Math.min(3, med + (3.0 * sigma), med * 2.8),
    })
  }
  return fits
}

function fitWeightedPoly(points) {
  const degree = Math.min(3, Math.max(1, points.length - 1))
  const n = degree + 1
  const weights = points.map((point) => {
    const spreadPenalty = clamp((point.spreadPct ?? 0) / 0.25, 0, 1)
    const liq = Math.log1p(Math.max(point.volume || 0, 0)) + (0.35 * Math.log1p(Math.max(point.openInt || 0, 0)))
    return (0.65 + Math.min(liq / 8, 1.2)) * (1 - (0.45 * spreadPenalty))
  })
  const matrix = Array.from({ length: n }, () => Array.from({ length: n }, () => 0))
  const vector = Array.from({ length: n }, () => 0)

  for (let row = 0; row < points.length; row += 1) {
    const x = points[row].logM
    const y = points[row].iv
    const w = Math.max(weights[row], 0.05)
    const powers = Array.from({ length: n * 2 }, (_, index) => x ** index)
    for (let i = 0; i < n; i += 1) {
      vector[i] += w * y * powers[i]
      for (let j = 0; j < n; j += 1) {
        matrix[i][j] += w * powers[i + j]
      }
    }
  }

  return gaussSolve(matrix, vector) || [median(points.map((point) => point.iv)) || 0.22, 0, 0, 0]
}

function evalPoly(coeffs, x) {
  return coeffs.reduce((sum, coeff, index) => sum + (coeff * (x ** index)), 0)
}

function gaussSolve(matrix, vector) {
  const n = vector.length
  const m = matrix.map((row, index) => [...row, vector[index]])
  for (let col = 0; col < n; col += 1) {
    let pivot = col
    for (let row = col + 1; row < n; row += 1) {
      if (Math.abs(m[row][col]) > Math.abs(m[pivot][col])) pivot = row
    }
    if (Math.abs(m[pivot][col]) < 1e-10) return null
    ;[m[col], m[pivot]] = [m[pivot], m[col]]
    const divisor = m[col][col]
    for (let j = col; j <= n; j += 1) m[col][j] /= divisor
    for (let row = 0; row < n; row += 1) {
      if (row === col) continue
      const factor = m[row][col]
      for (let j = col; j <= n; j += 1) m[row][j] -= factor * m[col][j]
    }
  }
  return m.map((row) => row[n])
}

function buildLiquidityMarks(points) {
  const raw = points.map((point) => (
    Math.log1p(Math.max(point.volume || 0, 0)) + (0.35 * Math.log1p(Math.max(point.openInt || 0, 0)))
  ))
  const high = quantile(raw, 0.92) || Math.max(...raw, 1)
  const marks = new Map()
  points.forEach((point, index) => {
    const fallback = point.marketOk ? 0.45 : 0.25
    const score = high > 0 ? clamp(raw[index] / high, 0, 1) : fallback
    marks.set(point.key, Math.max(score, fallback))
  })
  return marks
}

function buildDistortionSigmas(points) {
  const lookup = new Map()
  const groups = new Map()
  const globalValues = []
  for (const point of points) {
    const keys = [`${point.region}:${point.tenor}`, point.region, 'global']
    for (const key of keys) {
      if (!groups.has(key)) groups.set(key, [])
      groups.get(key).push(point.distortion)
    }
    globalValues.push(point.distortion)
  }

  const globalSigma = Math.max(robustSigma(globalValues) || std(globalValues) || 0.006, 0.0035)
  for (const [key, values] of groups.entries()) {
    const sigma = values.length >= 5 ? robustSigma(values) : null
    lookup.set(key, Math.max(sigma || globalSigma, globalSigma * 0.45, 0.0025))
  }
  lookup.set('global', globalSigma)
  return lookup
}

function classifyRegion(point) {
  const absDelta = Math.abs(point.delta || 0)
  const isPut = point.pc.startsWith('p')
  const isCall = point.pc.startsWith('c')
  if (Math.abs(point.logM) <= 0.015 || (absDelta >= 0.42 && absDelta <= 0.58)) return 'atm'
  if ((isPut && point.logM < -0.025) || (isPut && absDelta > 0 && absDelta <= 0.35)) return 'putWing'
  if ((isCall && point.logM > 0.025) || (isCall && absDelta > 0 && absDelta <= 0.35)) return 'callWing'
  if (point.logM < -0.025) return 'putWing'
  if (point.logM > 0.025) return 'callWing'
  return 'body'
}

function tenorBucket(dte) {
  if (dte <= 12) return 'short'
  if (dte <= 45) return 'medium'
  return 'long'
}

function summarizeRegion(points, region, label) {
  const sample = points.filter((point) => point.region === region)
  if (!sample.length) return summarizeSynthetic(region, label, 0, 0, 0)
  const weights = sample.map((point) => point.weight)
  const signedZ = weightedMean(sample.map((point) => point.z), weights) ?? 0
  const absZ = weightedMean(sample.map((point) => Math.abs(point.z)), weights) ?? 0
  return {
    key: region,
    label,
    z: signedZ,
    score: scoreFromZ(absZ),
    count: sample.length,
    tone: signedZ >= 0 ? 'hot' : 'cool',
  }
}

function summarizeSynthetic(key, label, signedZ, absZ, count) {
  return {
    key,
    label,
    z: clamp(signedZ || 0, -5, 5),
    score: count > 0 ? scoreFromZ(absZ || Math.abs(signedZ || 0)) : 0,
    count,
    tone: signedZ >= 0 ? 'hot' : 'cool',
  }
}

function summarizeTerm(points) {
  const near = points.filter((point) => point.dte <= 15 && (point.region === 'atm' || Math.abs(point.logM) <= 0.035))
  const mid = points.filter((point) => point.dte > 20 && point.dte <= 70 && (point.region === 'atm' || Math.abs(point.logM) <= 0.035))
  const long = points.filter((point) => point.dte > 70 && (point.region === 'atm' || Math.abs(point.logM) <= 0.04))
  const nearIv = weightedMean(near.map((point) => point.iv), near.map((point) => point.weight))
  const midIv = weightedMean(mid.map((point) => point.iv), mid.map((point) => point.weight))
  const longIv = weightedMean(long.map((point) => point.iv), long.map((point) => point.weight))
  const termValues = [nearIv, midIv, longIv].filter((value) => value != null)
  const scale = Math.max(robustSigma(termValues) || 0.012, 0.006)
  const anchor = midIv ?? longIv ?? nearIv
  const z = nearIv != null && anchor != null ? clamp((nearIv - anchor) / scale, -5, 5) : 0
  return summarizeSynthetic('term', 'Term', z, Math.abs(z), near.length + mid.length + long.length)
}

function summarizeLiquidity(points) {
  const active = [...points].sort((a, b) => Math.abs(b.z) - Math.abs(a.z)).slice(0, Math.max(5, Math.ceil(points.length * 0.22)))
  const spreads = active.map((point) => point.spreadPct ?? 0).filter((value) => Number.isFinite(value))
  const weightedSpread = weightedMean(spreads, active.map((point) => Math.abs(point.z) + 0.5)) ?? 0
  const z = clamp(weightedSpread / 0.055, 0, 5)
  return {
    key: 'liquidity',
    label: 'Liquidity',
    z,
    score: clamp((1 - Math.exp(-z / 1.45)) * 100, 0, 100),
    count: active.length,
    tone: z >= 1.4 ? 'hot' : 'cool',
  }
}

function topDistortionRows(points) {
  return [...points]
    .map((point) => ({
      ...point,
      rankingScore: Math.abs(point.z) * (0.45 + (0.55 * point.liquidityScore)),
    }))
    .sort((a, b) => b.rankingScore - a.rankingScore)
    .slice(0, 5)
}

function computeConfidence(points, topRows) {
  const countScore = clamp(points.length / 160, 0, 1)
  const topLiquidity = topRows.length
    ? mean(topRows.map((point) => point.liquidityScore)) ?? 0
    : 0
  const spreadQuality = 1 - clamp(mean(topRows.map((point) => point.spreadPct ?? 0)) ?? 0, 0, 0.25) / 0.25
  return clamp(30 + (28 * countScore) + (27 * topLiquidity) + (15 * spreadQuality), 0, 100)
}

function classifySurface({ score, components, dominant, confidence }) {
  const byKey = Object.fromEntries(components.map((component) => [component.key, component]))
  if (confidence < 38 && score >= 60) return 'Illiquid Noise'
  if (byKey.term.score >= 78 && byKey.term.z >= 1.1) return 'Short-Term Event Pricing'
  if (byKey.term.score >= 72 && byKey.term.z <= -1.1) return 'Long-Term Repricing'
  if (byKey.putWing.score >= 80 && byKey.putWing.z > 0.7 && byKey.skew.score >= 60) return 'Skew Panic'
  if (byKey.putWing.score >= 72 && byKey.putWing.z > 0.6) return 'Put Wing Bid'
  if (byKey.callWing.score >= 72 && byKey.callWing.z > 0.6) return 'Call Wing Chase'
  if (byKey.atm.score >= 72 && byKey.atm.z > 0.7) return 'ATM Panic Bid'
  if (byKey.atm.score >= 64 && byKey.atm.z < -0.7) return 'ATM Compression'
  if (byKey.convexity.score >= 76 && byKey.convexity.z > 0.8) return 'Convexity Shock'
  if (byKey.skew.score >= 72 && byKey.skew.z > 0.8) return 'Smile Steepening'
  if (byKey.skew.score >= 72 && byKey.skew.z < -0.8) return 'Smile Flattening'
  if (score >= 75 || dominant.score >= 82) return 'Surface Dislocation'
  return 'Surface Normal'
}

function readingFor(classification) {
  const readings = {
    'Put Wing Bid': 'mercado pagando protecao de cauda',
    'Call Wing Chase': 'mercado pagando convexidade de alta',
    'ATM Compression': 'miolo barato, straddle pode estar subprecificado',
    'ATM Panic Bid': 'demanda direta por gamma no centro',
    'Short-Term Event Pricing': 'curto prazo caro, evento imediato no radar',
    'Long-Term Repricing': 'premio longo abrindo, risco estrutural sendo remarcado',
    'Smile Steepening': 'puts ganhando premio relativo contra calls',
    'Smile Flattening': 'desmonte de protecao ou venda de puts',
    'Convexity Shock': 'asas caras contra ATM, mercado comprando cauda',
    'Skew Panic': 'protecao de queda encarecendo com forca',
    'Surface Dislocation': 'um bloco da superficie saiu do padrao',
    'Illiquid Noise': 'distorcao existe, mas liquidez nao confirma',
    'Surface Normal': 'sem distorcao estatistica dominante',
  }
  return readings[classification] || readings['Surface Normal']
}

function explanationFor(classification, dominant) {
  if (classification === 'Surface Normal') {
    return 'A superficie esta relativamente coerente entre miolo, asas e prazo. O radar segue mais informativo do que acionavel agora.'
  }
  return `${classification}: ${readingFor(classification)}. O componente dominante e ${dominant.label}, com ${formatZ(dominant.z)} z e score ${formatScore(dominant.score)}.`
}

function affectedStrikeRange(rows) {
  if (!rows.length) return '-'
  const strikes = rows.map((row) => row.strike).filter(Number.isFinite)
  if (!strikes.length) return '-'
  const minStrike = Math.min(...strikes)
  const maxStrike = Math.max(...strikes)
  if (minStrike === maxStrike) return formatStrike(minStrike)
  return `${formatStrike(minStrike)}-${formatStrike(maxStrike)}`
}

function affectedExpiryLabel(rows) {
  if (!rows.length) return 'sem vencimento dominante'
  const avgDte = mean(rows.map((row) => row.dte).filter(Number.isFinite)) ?? 0
  if (avgDte <= 15) return 'vencimento curto'
  if (avgDte <= 60) return 'vencimento medio'
  return 'vencimento longo'
}

function buildAlerts({ score, components, topDistortions, term }) {
  const byKey = Object.fromEntries(components.map((component) => [component.key, component]))
  const alerts = []
  if (score > 75) alerts.push('SurfaceDistortionScore > 75')
  if (byKey.putWing.score > 80) alerts.push('PutWingDistortion > 80')
  if (byKey.callWing.score > 80) alerts.push('CallWingDistortion > 80')
  if (term.score > 75 && term.z > 0) alerts.push('Term inversion detectada')
  if (topDistortions.some((point) => point.liquidityScore > 0.65 && Math.abs(point.z) > 2)) alerts.push('Distorcao com volume relevante')
  if (topDistortions.some((point) => Math.abs(point.logM) < 0.025 && Math.abs(point.z) > 1.6)) alerts.push('Distorcao proxima ao spot')
  return alerts
}

function buildNotes({ components, topDistortions, confidence }) {
  const byKey = Object.fromEntries(components.map((component) => [component.key, component]))
  const notes = []
  if (byKey.putWing.z > 0.8) notes.push('Put wing acima do teorico: protecao de downside tem premio.')
  if (byKey.callWing.z > 0.8) notes.push('Call wing acima do teorico: mercado paga upside/squeeze.')
  if (byKey.atm.z < -0.8) notes.push('ATM comprimido: miolo barato contra as asas.')
  if (byKey.term.z > 1.0) notes.push('Curto prazo acima do medio: evento ou stress imediato.')
  if (confidence < 50) notes.push('Confianca baixa: priorize pontos com volume/OI antes de agir.')
  if (!notes.length && topDistortions.length) notes.push('Distorcoes estao dispersas; ainda sem concentracao operacional clara.')
  return notes
}

function radarPoint(index, ratio) {
  const radius = 86 * clamp(ratio, 0, 1.25)
  const angle = (-Math.PI / 2) + ((Math.PI * 2 * index) / RADAR_LABELS.length)
  return { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius }
}

function radarGridPoints(level) {
  return RADAR_LABELS.map((_, index) => pointString(radarPoint(index, level))).join(' ')
}

function pointString(point) {
  return `${point.x.toFixed(2)},${point.y.toFixed(2)}`
}

function scoreFromZ(z) {
  return clamp((1 - Math.exp(-Math.abs(z) / 1.65)) * 100, 0, 100)
}

function normalizeSpreadPct(value, bid, ask) {
  const direct = safeNumber(value)
  if (direct != null) return direct > 2 ? direct / 100 : Math.abs(direct)
  if (bid != null && ask != null && ask > bid && (ask + bid) > 0) {
    return Math.abs(ask - bid) / ((ask + bid) / 2)
  }
  return null
}

function heatColor(z, count) {
  if (!count) return 'rgba(30, 41, 59, 0.24)'
  const capped = clamp(z, -3, 3)
  if (Math.abs(capped) < 0.15) return 'rgba(30, 41, 59, 0.72)'
  if (capped >= 0) {
    const t = (capped - 0.15) / 2.85
    return `rgba(${Math.round(78 + (173 * t))}, ${Math.round(86 - (22 * t))}, ${Math.round(101 - (19 * t))}, ${0.46 + (0.49 * t)})`
  }
  const t = (Math.abs(capped) - 0.15) / 2.85
  return `rgba(${Math.round(51 - (17 * t))}, ${Math.round(111 + (86 * t))}, ${Math.round(128 - (34 * t))}, ${0.44 + (0.48 * t)})`
}

function zTone(value) {
  if (value > 0.75) return 'hot'
  if (value < -0.75) return 'cool'
  return ''
}

function safeNumber(value) {
  if (value === null || value === undefined || value === '') return null
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

function clamp(value, low, high) {
  return Math.max(low, Math.min(high, Number(value) || 0))
}

function mean(values) {
  const clean = values.filter(Number.isFinite)
  if (!clean.length) return null
  return clean.reduce((sum, value) => sum + value, 0) / clean.length
}

function std(values) {
  const avg = mean(values)
  if (avg == null) return null
  const clean = values.filter(Number.isFinite)
  if (clean.length < 2) return null
  return Math.sqrt(clean.reduce((sum, value) => sum + ((value - avg) ** 2), 0) / clean.length)
}

function median(values) {
  return quantile(values, 0.5)
}

function quantile(values, q) {
  const clean = values.filter(Number.isFinite).sort((a, b) => a - b)
  if (!clean.length) return null
  const pos = (clean.length - 1) * q
  const base = Math.floor(pos)
  const rest = pos - base
  return clean[base + 1] !== undefined
    ? clean[base] + (rest * (clean[base + 1] - clean[base]))
    : clean[base]
}

function robustSigma(values) {
  const med = median(values)
  if (med == null) return null
  const deviations = values.map((value) => Math.abs(value - med)).filter(Number.isFinite)
  const mad = median(deviations)
  return mad != null ? mad * 1.4826 : null
}

function weightedMean(values, weights) {
  let num = 0
  let den = 0
  values.forEach((value, index) => {
    if (!Number.isFinite(value)) return
    const weight = Math.max(Number(weights[index]) || 0, 0)
    num += value * weight
    den += weight
  })
  return den > 0 ? num / den : null
}

function weightedMedian(values, weights) {
  const pairs = values
    .map((value, index) => ({ value, weight: Math.max(Number(weights[index]) || 0, 0) }))
    .filter((item) => Number.isFinite(item.value) && item.weight > 0)
    .sort((a, b) => a.value - b.value)
  if (!pairs.length) return null
  const total = pairs.reduce((sum, item) => sum + item.weight, 0)
  let running = 0
  for (const item of pairs) {
    running += item.weight
    if (running >= total / 2) return item.value
  }
  return pairs[pairs.length - 1].value
}

function formatScore(value) {
  return Math.round(clamp(value, 0, 100)).toString()
}

function formatZ(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '0.0'
  return `${numeric > 0 ? '+' : ''}${numeric.toFixed(1)}`
}

function formatHeatZ(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return ''
  return Math.abs(numeric) >= 1 ? formatZ(numeric) : numeric.toFixed(1)
}

function formatPct(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '-'
  return `${(numeric * 100).toFixed(1)}%`
}

function formatStrike(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '-'
  if (Math.abs(numeric) >= 1000) return `${Math.round(numeric / 1000)}k`
  return Math.round(numeric).toString()
}

function formatExpiry(expiry, dte) {
  if (expiry) return String(expiry).slice(5) || expiry
  return `${Math.round(dte || 0)}d`
}

function formatInt(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric) || numeric <= 0) return '-'
  if (numeric >= 1_000_000) return `${(numeric / 1_000_000).toFixed(1)}m`
  if (numeric >= 1_000) return `${(numeric / 1_000).toFixed(1)}k`
  return Math.round(numeric).toString()
}
</script>

<style scoped>
.vsdr-root {
  width: 100%;
  height: 100%;
  min-height: 440px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  color: #d9e4ee;
  background:
    radial-gradient(circle at 16% 6%, rgba(20, 184, 166, 0.16), transparent 30%),
    radial-gradient(circle at 92% 12%, rgba(251, 113, 133, 0.12), transparent 34%),
    linear-gradient(145deg, #071019 0%, #0b1320 52%, #090f17 100%);
  overflow: auto;
}

.vsdr-header,
.vsdr-hero,
.vsdr-main-grid,
.vsdr-bottom-grid {
  display: grid;
  gap: 10px;
}

.vsdr-header {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
}

.vsdr-title-block,
.vsdr-score-copy,
.vsdr-panel-head,
.vsdr-explain {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.vsdr-title {
  font-size: 14px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #f8fafc;
}

.vsdr-subtitle,
.vsdr-panel-sub,
.vsdr-metric-sub,
.vsdr-component-sub,
.vsdr-stamp,
.vsdr-method {
  font-size: 11px;
  color: #7f96aa;
}

.vsdr-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.vsdr-underlying,
.vsdr-btn,
.vsdr-badge,
.vsdr-alert {
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.72);
}

.vsdr-underlying {
  padding: 5px 9px;
  color: #9fd5ff;
  font-size: 11px;
  font-weight: 800;
}

.vsdr-btn {
  padding: 5px 10px;
  color: #dbeafe;
  cursor: pointer;
}

.vsdr-btn:hover:not(:disabled) {
  border-color: rgba(56, 189, 248, 0.55);
  color: #fff;
}

.vsdr-btn.loading {
  opacity: 0.65;
}

.vsdr-empty {
  flex: 1;
  display: grid;
  place-items: center;
  min-height: 220px;
  color: #7f96aa;
  border: 1px dashed rgba(148, 163, 184, 0.22);
  border-radius: 18px;
  background: rgba(15, 23, 42, 0.45);
}

.vsdr-hero {
  grid-template-columns: minmax(260px, 0.8fr) minmax(360px, 1.2fr);
}

.vsdr-score-card,
.vsdr-metric,
.vsdr-panel,
.vsdr-component {
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(8, 15, 24, 0.78);
  box-shadow: 0 18px 45px rgba(0, 0, 0, 0.18);
}

.vsdr-score-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px;
  border-radius: 20px;
}

.vsdr-score-ring {
  width: 92px;
  height: 92px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  position: relative;
  flex: 0 0 auto;
}

.vsdr-score-ring::before {
  content: '';
  position: absolute;
  inset: 8px;
  border-radius: 50%;
  background: #08111b;
  border: 1px solid rgba(148, 163, 184, 0.16);
}

.vsdr-score-value,
.vsdr-score-max {
  position: relative;
  z-index: 1;
}

.vsdr-score-value {
  font-size: 28px;
  font-weight: 900;
  color: #f8fafc;
  line-height: 1;
}

.vsdr-score-max {
  margin-top: -24px;
  font-size: 10px;
  color: #7f96aa;
}

.vsdr-badge {
  width: fit-content;
  padding: 5px 9px;
  font-size: 11px;
  font-weight: 900;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.vsdr-badge.hot,
.vsdr-component-fill.hot,
.vsdr-metric-value.hot {
  color: #fecdd3;
}

.vsdr-badge.hot {
  border-color: rgba(251, 113, 133, 0.42);
  background: rgba(127, 29, 29, 0.34);
}

.vsdr-badge.warm {
  color: #fde68a;
  border-color: rgba(245, 158, 11, 0.42);
  background: rgba(120, 53, 15, 0.34);
}

.vsdr-badge.cool {
  color: #bbf7d0;
  border-color: rgba(34, 197, 94, 0.35);
  background: rgba(20, 83, 45, 0.30);
}

.vsdr-reading {
  font-size: 13px;
  color: #dbeafe;
}

.vsdr-metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.vsdr-metric {
  min-width: 0;
  padding: 12px;
  border-radius: 16px;
}

.vsdr-metric-label {
  display: block;
  color: #7f96aa;
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.vsdr-metric-value {
  display: block;
  margin-top: 6px;
  color: #f8fafc;
  font-size: 16px;
  font-weight: 850;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.vsdr-metric-value.cool {
  color: #86efac;
}

.vsdr-alerts {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.vsdr-alert {
  padding: 5px 8px;
  color: #fda4af;
  font-size: 11px;
  border-color: rgba(251, 113, 133, 0.28);
  background: rgba(127, 29, 29, 0.2);
}

.vsdr-main-grid {
  grid-template-columns: minmax(280px, 0.9fr) minmax(360px, 1.1fr);
}

.vsdr-panel {
  min-width: 0;
  padding: 12px;
  border-radius: 18px;
}

.vsdr-panel-title {
  font-size: 12px;
  color: #f8fafc;
  font-weight: 850;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.radar-panel {
  min-height: 270px;
}

.vsdr-radar {
  width: 100%;
  height: 225px;
  margin-top: 8px;
  overflow: visible;
}

.vsdr-radar-grid {
  fill: none;
  stroke: rgba(148, 163, 184, 0.14);
  stroke-width: 1;
}

.vsdr-radar-axis {
  stroke: rgba(148, 163, 184, 0.18);
  stroke-width: 1;
}

.vsdr-radar-fill {
  fill: rgba(56, 189, 248, 0.22);
  stroke: none;
  filter: drop-shadow(0 0 10px rgba(56, 189, 248, 0.18));
}

.vsdr-radar-line {
  fill: none;
  stroke: #38bdf8;
  stroke-width: 2;
}

.vsdr-radar-dot {
  fill: #e0f2fe;
  stroke: #0f172a;
  stroke-width: 1;
}

.vsdr-radar-label {
  fill: #9eb3c7;
  font-size: 9px;
  font-weight: 800;
}

.vsdr-heatmap {
  display: grid;
  grid-template-columns: 46px repeat(7, minmax(42px, 1fr));
  gap: 4px;
  margin-top: 10px;
}

.vsdr-heat-corner,
.vsdr-heat-x,
.vsdr-heat-y,
.vsdr-heat-cell {
  min-height: 26px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  font-size: 10px;
}

.vsdr-heat-corner,
.vsdr-heat-x,
.vsdr-heat-y {
  color: #7f96aa;
  background: rgba(15, 23, 42, 0.74);
}

.vsdr-heat-cell {
  color: #f8fafc;
  border: 1px solid rgba(255, 255, 255, 0.04);
  font-weight: 850;
}

.vsdr-heat-cell.empty {
  color: transparent;
}

.vsdr-legend {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  color: #7f96aa;
  font-size: 10px;
}

.vsdr-grad {
  width: 130px;
  height: 8px;
  border-radius: 999px;
  background: linear-gradient(90deg, #22c55e, #1e293b, #fb7185);
}

.vsdr-component-strip {
  display: grid;
  grid-template-columns: repeat(7, minmax(96px, 1fr));
  gap: 8px;
}

.vsdr-component {
  padding: 9px;
  border-radius: 14px;
}

.vsdr-component-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  color: #dbeafe;
  font-size: 11px;
  font-weight: 800;
}

.vsdr-component-track {
  height: 6px;
  margin: 8px 0 5px;
  border-radius: 999px;
  overflow: hidden;
  background: rgba(30, 41, 59, 0.92);
}

.vsdr-component-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #38bdf8, #fb7185);
}

.vsdr-component-fill.cool {
  background: linear-gradient(90deg, #22c55e, #38bdf8);
}

.vsdr-bottom-grid {
  grid-template-columns: minmax(420px, 1.2fr) minmax(300px, 0.8fr);
}

.vsdr-table {
  display: grid;
  gap: 4px;
  margin-top: 8px;
}

.vsdr-row {
  display: grid;
  grid-template-columns: minmax(86px, 1.5fr) 0.8fr 0.8fr 0.75fr 0.75fr 0.55fr 0.6fr 0.6fr;
  gap: 8px;
  align-items: center;
  padding: 7px 8px;
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.58);
  color: #cbd5e1;
  font-size: 11px;
}

.vsdr-row.head {
  color: #7f96aa;
  font-size: 10px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  background: rgba(30, 41, 59, 0.64);
}

.vsdr-row .ticker {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #e0f2fe;
  font-weight: 800;
}

.vsdr-row .hot {
  color: #fda4af;
  font-weight: 900;
}

.vsdr-row .cool {
  color: #86efac;
  font-weight: 900;
}

.vsdr-explain-main {
  color: #e2e8f0;
  font-size: 13px;
  line-height: 1.45;
}

.vsdr-explain-list {
  display: grid;
  gap: 6px;
  margin-top: 8px;
}

.vsdr-explain-list span {
  padding: 8px;
  border-radius: 10px;
  color: #b9c7d6;
  background: rgba(15, 23, 42, 0.58);
  font-size: 11px;
  line-height: 1.35;
}

.vsdr-method {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(148, 163, 184, 0.12);
  line-height: 1.35;
}

@media (max-width: 920px) {
  .vsdr-hero,
  .vsdr-main-grid,
  .vsdr-bottom-grid {
    grid-template-columns: 1fr;
  }

  .vsdr-metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .vsdr-component-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .vsdr-row {
    grid-template-columns: minmax(92px, 1.4fr) 0.8fr 0.7fr 0.7fr 0.7fr 0.55fr;
  }

  .vsdr-row span:nth-child(7),
  .vsdr-row span:nth-child(8) {
    display: none;
  }
}
</style>

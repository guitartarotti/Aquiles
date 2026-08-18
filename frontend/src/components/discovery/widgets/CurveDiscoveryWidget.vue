<template>
  <div class="cdw-root">
    <div class="cdw-toolbar">
      <div class="cdw-curve-group">
        <button
          v-for="curve in curveOptions"
          :key="curve.key"
          type="button"
          class="cdw-chip"
          :class="{ active: selectedCurves.includes(curve.key) }"
          :style="{ '--curve-color': curve.color }"
          @click="toggleCurve(curve.key)"
        >
          <span class="cdw-dot"></span>
          {{ curve.short_label || curve.label }}
        </button>
      </div>

      <div class="cdw-spacer"></div>

      <button
        type="button"
        class="cdw-chip cdw-chip-soft"
        :class="{ active: showShapePoints }"
        @click="showShapePoints = !showShapePoints"
      >
        Shapes
      </button>
      <button type="button" class="cdw-btn" :disabled="loading" @click="reload">
        {{ loading ? '...' : 'Refresh' }}
      </button>
      <button type="button" class="cdw-btn cdw-ai-btn" :disabled="aiLoading" @click="openAiPanel">
        {{ aiLoading ? 'IA...' : aiAnalysis ? 'Opiniao IA' : 'Gerar IA' }}
      </button>
    </div>

    <div v-if="aiOpen && aiAnalysis" class="cdw-ai-panel">
      <div class="cdw-ai-head">
        <div>
          <div class="cdw-ai-kicker">Opiniao IA</div>
          <div class="cdw-ai-title">{{ aiAnalysis.headline || 'Leitura das curvas' }}</div>
        </div>
        <div class="cdw-ai-actions">
          <button type="button" class="cdw-mini-btn" :disabled="aiLoading" @click="refreshAi">
            {{ aiLoading ? 'Atualizando...' : 'Atualizar opiniao IA' }}
          </button>
          <button type="button" class="cdw-mini-btn ghost" @click="aiOpen = false">Fechar</button>
        </div>
      </div>
      <div v-if="aiStale" class="cdw-ai-stale">
        A selecao mudou depois desta leitura. Ela fica em cache ate voce clicar em atualizar.
      </div>
      <p class="cdw-ai-text">{{ aiAnalysis.overall_view }}</p>
      <div class="cdw-ai-grid">
        <div v-for="view in aiCurveViews" :key="view.curve_key || view.label" class="cdw-ai-card">
          <div class="cdw-ai-card-title">{{ view.label || view.curve_key }}</div>
          <div class="cdw-ai-card-shape">{{ view.shape }}</div>
          <div class="cdw-ai-card-read">{{ view.read }}</div>
          <div class="cdw-ai-card-meaning">{{ view.what_it_means }}</div>
        </div>
      </div>
      <div class="cdw-ai-footer">
        <span v-for="point in aiPoints" :key="point" class="cdw-ai-pill">{{ point }}</span>
      </div>
    </div>

    <div v-if="loading && !payload" class="cdw-empty">Carregando curvas da W32...</div>
    <div v-else-if="error" class="cdw-empty error">{{ error }}</div>
    <div v-else-if="!hasData" class="cdw-empty">
      {{ payload?.reason || 'Sem vertices suficientes para montar as curvas.' }}
    </div>

    <template v-else>
      <div class="cdw-meta">
        <span>Sessao {{ payload.session_date || '-' }}</span>
        <span>{{ fmtTime(payload.latest_capture_at) }}</span>
        <span>{{ payload.model?.label || 'Regressao geometrica' }}</span>
      </div>

      <div ref="chartsEl" class="cdw-charts">
        <section class="cdw-chart-section" :style="{ flexBasis: topBasis }">
          <div class="cdw-chart-title">
            <span>Variacao por vertice</span>
            <span class="cdw-chart-sub">{{ topSubtitle }}</span>
          </div>
          <svg class="cdw-svg" viewBox="0 0 1000 300" preserveAspectRatio="none">
            <defs>
              <linearGradient id="cdwTopGrid" x1="0" x2="1" y1="0" y2="0">
                <stop offset="0%" stop-color="rgba(56,189,248,0.06)" />
                <stop offset="100%" stop-color="rgba(244,114,182,0.06)" />
              </linearGradient>
            </defs>
            <rect x="0" y="0" width="1000" height="300" fill="url(#cdwTopGrid)" />
            <line
              v-for="tick in topTicks"
              :key="`top-grid-${tick.value}`"
              :x1="CHART_PAD.left"
              :x2="1000 - CHART_PAD.right"
              :y1="tick.y"
              :y2="tick.y"
              class="cdw-grid-line"
            />
            <text
              v-for="tick in topTicks"
              :key="`top-label-${tick.value}`"
              :x="CHART_PAD.left - 10"
              :y="tick.y + 4"
              text-anchor="end"
              class="cdw-axis-label"
            >
              {{ fmtBpShort(tick.value) }}
            </text>
            <line
              :x1="CHART_PAD.left"
              :x2="1000 - CHART_PAD.right"
              :y1="topZeroY"
              :y2="topZeroY"
              class="cdw-zero-line"
            />

            <g v-for="series in topSeries" :key="series.key">
              <path :d="series.path" class="cdw-top-path" :style="{ stroke: series.color }" />
              <g v-for="point in series.points" :key="`${series.key}-${point.symbol}`">
                <line
                  :x1="point.x"
                  :x2="point.x"
                  :y1="point.yMin"
                  :y2="point.yMax"
                  class="cdw-range-line"
                  :style="{ stroke: series.color }"
                />
                <line
                  :x1="point.x - 6"
                  :x2="point.x + 6"
                  :y1="point.yMin"
                  :y2="point.yMin"
                  class="cdw-range-cap"
                  :style="{ stroke: series.color }"
                />
                <line
                  :x1="point.x - 6"
                  :x2="point.x + 6"
                  :y1="point.yMax"
                  :y2="point.yMax"
                  class="cdw-range-cap"
                  :style="{ stroke: series.color }"
                />
                <circle
                  :cx="point.x"
                  :cy="point.y"
                  r="5"
                  class="cdw-top-point"
                  :style="{ fill: series.color }"
                >
                  <title>
                    {{ series.label }} {{ point.label }} {{ basisLabel(point.changeBasis) }} {{ fmtBp(point.change) }} | min {{ fmtBp(point.min) }} | max {{ fmtBp(point.max) }}
                  </title>
                </circle>
                <text
                  :x="point.x"
                  :y="278"
                  text-anchor="middle"
                  class="cdw-x-label"
                >
                  {{ point.label }}
                </text>
              </g>
            </g>
          </svg>
          <div class="cdw-legend">
            <span v-for="series in topSeries" :key="`legend-${series.key}`" class="cdw-legend-item">
              <span class="cdw-legend-dot" :style="{ background: series.color }"></span>
              {{ series.label }}
            </span>
          </div>
        </section>

        <button
          type="button"
          class="cdw-divider"
          title="Arraste para redistribuir os graficos"
          @pointerdown.stop.prevent="startSplitDrag"
        >
          <span></span>
        </button>

        <section class="cdw-chart-section cdw-chart-section-bottom">
          <div class="cdw-chart-title">
            <span>Historico da inclinacao geometrica</span>
            <span class="cdw-chart-sub">slope change, amostra 1 minuto</span>
          </div>
          <svg class="cdw-svg" viewBox="0 0 1000 300" preserveAspectRatio="none">
            <line
              v-for="tick in bottomTicks"
              :key="`bottom-grid-${tick.value}`"
              :x1="CHART_PAD.left"
              :x2="1000 - CHART_PAD.right"
              :y1="tick.y"
              :y2="tick.y"
              class="cdw-grid-line"
            />
            <text
              v-for="tick in bottomTicks"
              :key="`bottom-label-${tick.value}`"
              :x="CHART_PAD.left - 10"
              :y="tick.y + 4"
              text-anchor="end"
              class="cdw-axis-label"
            >
              {{ fmtBpShort(tick.value) }}
            </text>
            <line
              :x1="CHART_PAD.left"
              :x2="1000 - CHART_PAD.right"
              :y1="bottomZeroY"
              :y2="bottomZeroY"
              class="cdw-zero-line"
            />
            <path
              v-for="series in bottomSeries"
              :key="series.key"
              :d="series.path"
              class="cdw-bottom-path"
              :style="{ stroke: series.color }"
            />
            <g v-if="showShapePoints">
              <g v-for="point in bottomShapeMarkers" :key="point.key">
                <line
                  :x1="point.x"
                  :x2="point.x"
                  :y1="CHART_PAD.top"
                  :y2="300 - CHART_PAD.bottom"
                  class="cdw-shape-marker-line"
                  :style="{ stroke: point.color }"
                />
                <circle
                  :cx="point.x"
                  :cy="point.y"
                  r="5"
                  class="cdw-shape-marker"
                  :style="{ fill: point.color }"
                >
                  <title>{{ point.label }} - {{ fmtTime(point.timestamp) }}</title>
                </circle>
              </g>
            </g>
            <text
              v-for="tick in bottomTimeTicks"
              :key="`time-${tick.label}`"
              :x="tick.x"
              y="282"
              text-anchor="middle"
              class="cdw-x-label"
            >
              {{ tick.label }}
            </text>
          </svg>
        </section>
      </div>

      <div v-if="showShapePoints" class="cdw-shape-grid">
        <div
          v-for="curve in selectedAvailableCurves"
          :key="`shape-${curve.key}`"
          class="cdw-shape-card"
          :class="curve.current_shape?.tone || 'neutral'"
          :style="{ '--curve-color': curve.color }"
        >
          <div class="cdw-shape-top">
            <span class="cdw-shape-name">{{ curve.short_label || curve.label }}</span>
            <span class="cdw-shape-label">{{ curve.current_shape?.label || '-' }}</span>
          </div>
          <div class="cdw-shape-stats">
            <span>Slope {{ fmtBp(curve.summary?.current_slope_change_bp) }}</span>
            <span>{{ basisLabel(curve.summary?.change_basis || curve.change_basis) }} {{ fmtBp(curve.summary?.current_level_change_bp) }}</span>
          </div>
          <div class="cdw-shape-meaning">{{ curve.current_shape?.risk_read || curve.current_shape?.meaning }}</div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { getCurveDiscoveryAi, getCurveDiscoveryPanel } from '@/api/macro'

const props = defineProps({
  refreshNonce: { type: Number, default: 0 },
})

const FALLBACK_CURVES = [
  { key: 'ois', label: 'OIS USD', short_label: 'OIS', color: '#38bdf8' },
  { key: 'treasury', label: 'Treasury USD', short_label: 'UST', color: '#f59e0b' },
  { key: 'di', label: 'DI Brasil', short_label: 'DI', color: '#22c55e' },
  { key: 'br_inflation', label: 'Inflacao Imp BR', short_label: 'BRII', color: '#f472b6' },
]

const CHART_PAD = Object.freeze({ top: 24, right: 28, bottom: 38, left: 58 })
const SVG_W = 1000
const SVG_H = 300

const selectedCurves = ref(['ois', 'treasury', 'di', 'br_inflation'])
const showShapePoints = ref(true)
const payload = ref(null)
const loading = ref(false)
const error = ref('')
const topRatio = ref(0.55)
const chartsEl = ref(null)
const aiOpen = ref(false)
const aiLoading = ref(false)
const aiAnalysis = ref(null)
const aiSelectionSignature = ref('')
let timer = null
let splitDragging = false

const selectedSignature = computed(() => selectedCurves.value.slice().sort().join('|'))
const aiStale = computed(() => Boolean(aiAnalysis.value) && aiSelectionSignature.value !== selectedSignature.value)
const curveOptions = computed(() => payload.value?.available_curves?.length ? payload.value.available_curves : FALLBACK_CURVES)
const hasData = computed(() => Boolean(payload.value?.ok && selectedAvailableCurves.value.length))
const topBasis = computed(() => `${Math.round(topRatio.value * 100)}%`)
const topSubtitle = computed(() => {
  const bases = new Set(
    selectedAvailableCurves.value
      .map(curve => curve.summary?.change_basis || curve.change_basis)
      .filter(Boolean),
  )
  if (bases.has('daily_w32_pct')) {
    return 'DI em variacao diaria W32; demais curvas em base intraday'
  }
  return 'range min/max da sessao, base = 1o ponto'
})

const selectedAvailableCurves = computed(() => {
  const selected = new Set(selectedCurves.value)
  return (payload.value?.curves || [])
    .filter(curve => selected.has(curve.key))
    .filter(curve => curve.available && (curve.vertices || []).some(vertex => vertex.available))
})

const topDomain = computed(() => {
  const values = [0]
  for (const curve of selectedAvailableCurves.value) {
    for (const vertex of curve.vertices || []) {
      if (!vertex.available) continue
      values.push(Number(vertex.change_bp || 0))
      values.push(Number(vertex.min_change_bp || 0))
      values.push(Number(vertex.max_change_bp || 0))
    }
  }
  return paddedDomain(values)
})

const tenorDomain = computed(() => {
  const tenors = []
  for (const curve of selectedAvailableCurves.value) {
    for (const vertex of curve.vertices || []) {
      if (vertex.available && Number(vertex.tenor_years) > 0) tenors.push(Math.log(Number(vertex.tenor_years)))
    }
  }
  if (!tenors.length) return [0, 1]
  const min = Math.min(...tenors)
  const max = Math.max(...tenors)
  return min === max ? [min - 0.5, max + 0.5] : [min, max]
})

const topSeries = computed(() => {
  return selectedAvailableCurves.value.map(curve => {
    const points = (curve.vertices || [])
      .filter(vertex => vertex.available && Number(vertex.tenor_years) > 0)
      .sort((a, b) => Number(a.tenor_years) - Number(b.tenor_years))
      .map(vertex => {
        const x = xFromLogTenor(Number(vertex.tenor_years))
        return {
          symbol: vertex.symbol,
          label: vertex.label,
          x,
          y: topY(Number(vertex.change_bp || 0)),
          yMin: topY(Number(vertex.min_change_bp || 0)),
          yMax: topY(Number(vertex.max_change_bp || 0)),
          change: vertex.change_bp,
          min: vertex.min_change_bp,
          max: vertex.max_change_bp,
          changeBasis: vertex.change_basis || curve.summary?.change_basis || curve.change_basis,
        }
      })
    return {
      key: curve.key,
      label: curve.short_label || curve.label,
      color: curve.color,
      points,
      path: linePath(points),
    }
  }).filter(series => series.points.length)
})

const topTicks = computed(() => buildTicks(topDomain.value, 5).map(value => ({ value, y: topY(value) })))
const topZeroY = computed(() => topY(0))

const bottomDomain = computed(() => {
  const values = [0]
  for (const curve of selectedAvailableCurves.value) {
    for (const point of curve.history || []) {
      values.push(Number(point.slope_change_bp || 0))
    }
  }
  return paddedDomain(values)
})

const timeDomain = computed(() => {
  const times = []
  for (const curve of selectedAvailableCurves.value) {
    for (const point of curve.history || []) {
      if (point.timestamp_ms != null) times.push(Number(point.timestamp_ms))
    }
  }
  if (!times.length) {
    const now = Date.now()
    return [now - 60_000, now]
  }
  const min = Math.min(...times)
  const max = Math.max(...times)
  return min === max ? [min - 60_000, max + 60_000] : [min, max]
})

const bottomSeries = computed(() => {
  return selectedAvailableCurves.value.map(curve => {
    const points = (curve.history || [])
      .filter(point => point.timestamp_ms != null && point.slope_change_bp != null)
      .map(point => ({
        x: timeX(Number(point.timestamp_ms)),
        y: bottomY(Number(point.slope_change_bp || 0)),
      }))
    return {
      key: curve.key,
      color: curve.color,
      path: linePath(points),
    }
  }).filter(series => series.path)
})

const bottomTicks = computed(() => buildTicks(bottomDomain.value, 5).map(value => ({ value, y: bottomY(value) })))
const bottomZeroY = computed(() => bottomY(0))

const bottomTimeTicks = computed(() => {
  const [min, max] = timeDomain.value
  const ticks = []
  for (let i = 0; i < 4; i += 1) {
    const value = min + ((max - min) * i / 3)
    ticks.push({
      x: timeX(value),
      label: new Date(value).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }),
    })
  }
  return ticks
})

const bottomShapeMarkers = computed(() => {
  if (!showShapePoints.value) return []
  const markers = []
  for (const curve of selectedAvailableCurves.value) {
    for (const point of curve.shape_points || []) {
      if (point.timestamp_ms == null) continue
      markers.push({
        key: `${curve.key}-${point.timestamp_ms}-${point.shape?.id}`,
        x: timeX(Number(point.timestamp_ms)),
        y: bottomY(Number(point.slope_change_bp || 0)),
        color: curve.color,
        label: `${curve.short_label || curve.label}: ${point.shape?.label || 'shape'}`,
        timestamp: point.timestamp,
      })
    }
  }
  return markers
})

const aiCurveViews = computed(() => Array.isArray(aiAnalysis.value?.curve_views) ? aiAnalysis.value.curve_views : [])
const aiPoints = computed(() => {
  const items = [
    ...(Array.isArray(aiAnalysis.value?.key_points) ? aiAnalysis.value.key_points : []),
    ...(Array.isArray(aiAnalysis.value?.monitor) ? aiAnalysis.value.monitor : []),
  ]
  return items.slice(0, 5)
})

watch(selectedCurves, () => {
  reload()
}, { deep: true })

watch(showShapePoints, () => {
  reload()
})

watch(() => props.refreshNonce, () => {
  reload()
})

onMounted(() => {
  reload()
  timer = setInterval(reload, 60_000)
})

onUnmounted(() => {
  clearInterval(timer)
  stopSplitDrag()
})

async function reload() {
  if (!selectedCurves.value.length) return
  loading.value = true
  error.value = ''
  try {
    const res = await getCurveDiscoveryPanel({
      curves: selectedCurves.value.join(','),
      lookback_minutes: 720,
      max_points: 720,
      include_shape_points: showShapePoints.value,
    })
    payload.value = res?.data ?? res ?? null
  } catch (err) {
    error.value = err?.message || 'Falha ao carregar curvas.'
  } finally {
    loading.value = false
  }
}

function toggleCurve(key) {
  if (selectedCurves.value.includes(key)) {
    if (selectedCurves.value.length === 1) return
    selectedCurves.value = selectedCurves.value.filter(item => item !== key)
  } else {
    selectedCurves.value = [...selectedCurves.value, key]
  }
}

async function openAiPanel() {
  if (aiAnalysis.value) {
    aiOpen.value = true
    return
  }
  await refreshAi()
}

async function refreshAi() {
  aiLoading.value = true
  aiOpen.value = true
  try {
    const res = await getCurveDiscoveryAi({
      curves: selectedCurves.value,
      lookback_minutes: 720,
      session_date: payload.value?.session_date || null,
    })
    aiAnalysis.value = res?.data?.analysis ?? res?.analysis ?? null
    aiSelectionSignature.value = selectedSignature.value
  } catch (err) {
    aiAnalysis.value = {
      headline: 'Nao foi possivel gerar a opiniao IA.',
      overall_view: err?.message || 'Verifique a configuracao do LLM no backend.',
      curve_views: [],
      key_points: [],
      monitor: [],
      source: 'error',
    }
  } finally {
    aiLoading.value = false
  }
}

function startSplitDrag() {
  splitDragging = true
  window.addEventListener('pointermove', onSplitMove)
  window.addEventListener('pointerup', stopSplitDrag)
}

function onSplitMove(event) {
  if (!splitDragging || !chartsEl.value) return
  const rect = chartsEl.value.getBoundingClientRect()
  if (!rect.height) return
  const next = (event.clientY - rect.top) / rect.height
  topRatio.value = Math.max(0.28, Math.min(0.72, next))
}

function stopSplitDrag() {
  splitDragging = false
  window.removeEventListener('pointermove', onSplitMove)
  window.removeEventListener('pointerup', stopSplitDrag)
}

function paddedDomain(values) {
  const clean = values.map(Number).filter(Number.isFinite)
  if (!clean.length) return [-1, 1]
  let min = Math.min(...clean)
  let max = Math.max(...clean)
  if (min === max) {
    min -= 1
    max += 1
  }
  const pad = Math.max((max - min) * 0.12, 0.5)
  return [min - pad, max + pad]
}

function buildTicks(domain, count) {
  const [min, max] = domain
  if (!Number.isFinite(min) || !Number.isFinite(max) || count <= 1) return [0]
  const ticks = []
  for (let i = 0; i < count; i += 1) {
    ticks.push(min + ((max - min) * i / (count - 1)))
  }
  return ticks
}

function linePath(points) {
  if (!points.length) return ''
  return points.map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(' ')
}

function xFromLogTenor(tenorYears) {
  const [min, max] = tenorDomain.value
  const value = Math.log(Math.max(tenorYears, 0.05))
  return scale(value, min, max, CHART_PAD.left, SVG_W - CHART_PAD.right)
}

function topY(value) {
  const [min, max] = topDomain.value
  return scale(value, min, max, SVG_H - CHART_PAD.bottom, CHART_PAD.top)
}

function bottomY(value) {
  const [min, max] = bottomDomain.value
  return scale(value, min, max, SVG_H - CHART_PAD.bottom, CHART_PAD.top)
}

function timeX(value) {
  const [min, max] = timeDomain.value
  return scale(value, min, max, CHART_PAD.left, SVG_W - CHART_PAD.right)
}

function scale(value, d0, d1, r0, r1) {
  if (d0 === d1) return (r0 + r1) / 2
  return r0 + ((value - d0) / (d1 - d0)) * (r1 - r0)
}

function fmtBp(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return 'n/a'
  return `${parsed >= 0 ? '+' : ''}${parsed.toFixed(1)} bp`
}

function fmtBpShort(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return ''
  return `${parsed >= 0 ? '+' : ''}${parsed.toFixed(0)}`
}

function fmtTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}

function basisLabel(value) {
  return value === 'daily_w32_pct' ? 'Dia W32' : 'Sessao'
}
</script>

<style scoped>
.cdw-root {
  height: 100%;
  padding: 9px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  color: #dbeafe;
  background:
    radial-gradient(circle at 12% 8%, rgba(56,189,248,0.12), transparent 28%),
    radial-gradient(circle at 88% 16%, rgba(244,114,182,0.10), transparent 24%),
    #07101e;
  overflow: hidden;
}

.cdw-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.cdw-curve-group {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.cdw-spacer { flex: 1; }

.cdw-chip,
.cdw-btn,
.cdw-mini-btn {
  border: 1px solid rgba(148,163,184,0.18);
  border-radius: 999px;
  background: rgba(15,23,42,0.78);
  color: #94a3b8;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  cursor: pointer;
  transition: all 0.15s ease;
}

.cdw-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 9px;
}

.cdw-chip.active {
  color: #e0f2fe;
  border-color: color-mix(in srgb, var(--curve-color, #38bdf8) 64%, transparent);
  background: color-mix(in srgb, var(--curve-color, #38bdf8) 16%, #0f172a);
  box-shadow: 0 0 18px color-mix(in srgb, var(--curve-color, #38bdf8) 18%, transparent);
}

.cdw-chip-soft.active {
  --curve-color: #a3e635;
}

.cdw-dot,
.cdw-legend-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--curve-color, #38bdf8);
  box-shadow: 0 0 10px var(--curve-color, #38bdf8);
}

.cdw-btn {
  padding: 5px 10px;
}

.cdw-btn:hover,
.cdw-chip:hover,
.cdw-mini-btn:hover {
  color: #f8fafc;
  border-color: rgba(226,232,240,0.32);
}

.cdw-ai-btn {
  color: #fef3c7;
  border-color: rgba(245,158,11,0.34);
  background: linear-gradient(135deg, rgba(245,158,11,0.18), rgba(14,165,233,0.12));
}

.cdw-ai-panel {
  flex-shrink: 0;
  max-height: 205px;
  overflow: auto;
  border: 1px solid rgba(245,158,11,0.25);
  border-radius: 12px;
  background:
    linear-gradient(135deg, rgba(15,23,42,0.96), rgba(30,41,59,0.88)),
    radial-gradient(circle at top left, rgba(245,158,11,0.16), transparent 32%);
  box-shadow: 0 18px 38px rgba(0,0,0,0.35);
  padding: 10px;
}

.cdw-ai-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  justify-content: space-between;
}

.cdw-ai-kicker {
  font-size: 9px;
  color: #fbbf24;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  font-weight: 900;
}

.cdw-ai-title {
  margin-top: 2px;
  font-size: 13px;
  color: #f8fafc;
  font-weight: 900;
}

.cdw-ai-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.cdw-mini-btn {
  padding: 4px 8px;
  border-radius: 7px;
}

.cdw-mini-btn.ghost {
  background: rgba(255,255,255,0.03);
}

.cdw-ai-stale {
  margin-top: 7px;
  color: #fde68a;
  font-size: 11px;
}

.cdw-ai-text {
  margin: 8px 0;
  color: #cbd5e1;
  font-size: 12px;
  line-height: 1.45;
}

.cdw-ai-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 7px;
}

.cdw-ai-card {
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 8px;
  background: rgba(2,6,23,0.42);
  padding: 7px;
}

.cdw-ai-card-title {
  font-size: 11px;
  color: #e2e8f0;
  font-weight: 900;
}

.cdw-ai-card-shape {
  margin-top: 2px;
  font-size: 10px;
  color: #38bdf8;
  font-weight: 800;
}

.cdw-ai-card-read,
.cdw-ai-card-meaning {
  margin-top: 4px;
  font-size: 10px;
  color: #94a3b8;
  line-height: 1.35;
}

.cdw-ai-footer {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.cdw-ai-pill {
  padding: 3px 7px;
  border-radius: 999px;
  color: #bfdbfe;
  background: rgba(59,130,246,0.10);
  font-size: 10px;
}

.cdw-empty {
  flex: 1;
  display: grid;
  place-items: center;
  color: #64748b;
  font-size: 12px;
  text-align: center;
}

.cdw-empty.error {
  color: #f87171;
}

.cdw-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: #64748b;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  flex-shrink: 0;
}

.cdw-meta span {
  padding: 3px 7px;
  border-radius: 999px;
  background: rgba(15,23,42,0.7);
  border: 1px solid rgba(148,163,184,0.08);
}

.cdw-charts {
  min-height: 225px;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow: hidden;
}

.cdw-chart-section {
  min-height: 96px;
  display: flex;
  flex-direction: column;
  border: 1px solid rgba(148,163,184,0.10);
  border-radius: 10px;
  background: rgba(2,6,23,0.36);
  overflow: hidden;
}

.cdw-chart-section-bottom {
  flex: 1;
}

.cdw-chart-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 5px 9px 0;
  color: #e2e8f0;
  font-size: 11px;
  font-weight: 900;
}

.cdw-chart-sub {
  color: #64748b;
  font-size: 9px;
  font-weight: 700;
}

.cdw-svg {
  width: 100%;
  flex: 1;
  min-height: 0;
}

.cdw-grid-line {
  stroke: rgba(148,163,184,0.12);
  stroke-width: 1;
}

.cdw-zero-line {
  stroke: rgba(226,232,240,0.65);
  stroke-width: 1.1;
  stroke-dasharray: 7 7;
}

.cdw-axis-label,
.cdw-x-label {
  fill: #64748b;
  font-size: 10px;
  font-weight: 700;
}

.cdw-top-path,
.cdw-bottom-path {
  fill: none;
  stroke-width: 2.4;
  stroke-linecap: round;
  stroke-linejoin: round;
  filter: drop-shadow(0 0 6px rgba(56,189,248,0.18));
}

.cdw-bottom-path {
  stroke-width: 2.1;
}

.cdw-range-line {
  stroke-width: 1.4;
  opacity: 0.5;
}

.cdw-range-cap {
  stroke-width: 1.8;
  opacity: 0.8;
}

.cdw-top-point {
  stroke: rgba(2,6,23,0.9);
  stroke-width: 2;
}

.cdw-shape-marker-line {
  stroke-width: 1;
  opacity: 0.32;
  stroke-dasharray: 4 5;
}

.cdw-shape-marker {
  stroke: #020617;
  stroke-width: 2;
}

.cdw-divider {
  height: 12px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  cursor: row-resize;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}

.cdw-divider span {
  width: 78px;
  height: 3px;
  border-radius: 999px;
  background: linear-gradient(90deg, transparent, rgba(148,163,184,0.6), transparent);
}

.cdw-legend {
  display: flex;
  gap: 9px;
  flex-wrap: wrap;
  padding: 0 9px 6px;
  color: #94a3b8;
  font-size: 10px;
}

.cdw-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.cdw-shape-grid {
  flex-shrink: 0;
  max-height: 128px;
  overflow: auto;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 7px;
}

.cdw-shape-card {
  border: 1px solid rgba(148,163,184,0.12);
  border-left: 3px solid var(--curve-color);
  border-radius: 9px;
  background: rgba(15,23,42,0.72);
  padding: 8px;
}

.cdw-shape-card.risk,
.cdw-shape-card.tightening {
  background: linear-gradient(135deg, rgba(127,29,29,0.26), rgba(15,23,42,0.72));
}

.cdw-shape-card.constructive {
  background: linear-gradient(135deg, rgba(20,83,45,0.24), rgba(15,23,42,0.72));
}

.cdw-shape-card.defensive,
.cdw-shape-card.watch {
  background: linear-gradient(135deg, rgba(30,64,175,0.20), rgba(15,23,42,0.72));
}

.cdw-shape-top,
.cdw-shape-stats {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.cdw-shape-name {
  color: #f8fafc;
  font-size: 11px;
  font-weight: 900;
}

.cdw-shape-label {
  color: var(--curve-color);
  font-size: 11px;
  font-weight: 900;
}

.cdw-shape-stats {
  margin-top: 5px;
  color: #94a3b8;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}

.cdw-shape-meaning {
  margin-top: 5px;
  color: #cbd5e1;
  font-size: 10px;
  line-height: 1.35;
}

@media (max-width: 640px) {
  .cdw-toolbar,
  .cdw-ai-head {
    align-items: stretch;
    flex-direction: column;
  }

  .cdw-spacer {
    display: none;
  }

  .cdw-chart-sub {
    display: none;
  }
}
</style>

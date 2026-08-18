<template>
  <div ref="rootEl" class="fvm-root">
    <div class="fvm-toolbar">
      <span class="fvm-state-badge" :style="{ '--state-color': latestStateColor }">
        {{ latestStateName }}
      </span>
      <span class="fvm-pill">XB1 {{ formatPrice(displayRow?.close) }}</span>
      <span class="fvm-pill">Prob {{ formatPct(latestStateProbability) }}</span>
      <span class="fvm-pill warn">Out {{ formatScore(displayRow?.outlier_score) }}</span>
      <span class="fvm-pill disloc">Disloc {{ formatScore(displayRow?.dislocation_score) }}</span>

      <div class="fvm-sep" />
      <div class="fvm-mode-switch" role="group" aria-label="Modelo de regime">
        <button type="button" :class="{ active: viewMode === 'legacy' }" @click="viewMode = 'legacy'">FV Markov</button>
        <button type="button" :class="{ active: viewMode === 'tape' }" @click="viewMode = 'tape'">Tape DI</button>
      </div>
      <label class="fvm-check"><input type="checkbox" v-model="showRegimeBands" /> Regime</label>
      <label v-if="isTapeMode" class="fvm-check"><input type="checkbox" v-model="showTapeLine" /> DI regime</label>
      <label class="fvm-check"><input type="checkbox" v-model="showCore" /> Core</label>
      <label class="fvm-check"><input type="checkbox" v-model="showExpected" /> Exp</label>
      <label class="fvm-check"><input type="checkbox" v-model="showProbabilities" /> Prob</label>
      <label class="fvm-check"><input type="checkbox" v-model="showCurrentSessionOnly" /> Sessao atual</label>

      <button type="button" class="fvm-btn" :disabled="loading" @click="reload({ forceRefresh: true })">
        {{ loading ? '...' : 'Atualizar' }}
      </button>

      <div class="fvm-spacer" />
      <span class="fvm-meta" v-if="sessionLabel">{{ sessionLabel }}</span>
      <span class="fvm-error" v-if="errorMsg && !loading">{{ errorMsg }}</span>
    </div>

    <div v-if="loading && !payload" class="fvm-empty">Carregando regime Markov...</div>
    <div v-else-if="!payload && errorMsg" class="fvm-empty">{{ errorMsg }}</div>
    <div v-else-if="!plotRows.length" class="fvm-empty">Sem historico suficiente para o modelo.</div>

    <template v-else>
      <div class="fvm-kpi-grid">
        <div class="fvm-kpi">
          <span class="fvm-kpi-label">Regime</span>
          <span class="fvm-kpi-value" :style="{ color: latestStateColor }">{{ latestStateName }}</span>
          <span class="fvm-kpi-sub">{{ formatTime(displayRow?.timestamp_ms) }}</span>
        </div>
        <div class="fvm-kpi">
          <span class="fvm-kpi-label">Retorno esperado</span>
          <span class="fvm-kpi-value" :class="signedTone(displayRow?.expected_return_bps)">
            {{ formatBps(displayRow?.expected_return_bps) }}
          </span>
          <span class="fvm-kpi-sub">{{ formatPoints(displayRow?.expected_move_points) }} pts</span>
        </div>
        <div class="fvm-kpi">
          <span class="fvm-kpi-label">Residuo</span>
          <span class="fvm-kpi-value" :class="signedTone(displayRow?.residual_z)">
            {{ formatScore(displayRow?.residual_z) }}z
          </span>
          <span class="fvm-kpi-sub">{{ formatBps(displayRow?.residual_bps ?? displayRow?.return_bps) }}</span>
        </div>
        <div class="fvm-kpi">
          <span class="fvm-kpi-label">FV gap</span>
          <span class="fvm-kpi-value" :class="signedTone(displayRow?.fair_value_gap_z)">
            {{ formatScore(displayRow?.fair_value_gap_z) }}z
          </span>
          <span class="fvm-kpi-sub">RPC {{ formatScore((displayRow?.rpc_pressure || 0) * 100) }}</span>
        </div>
      </div>

      <div v-if="riskThermometer" class="fvm-risk-thermo" :class="riskThermometerTone">
        <div class="fvm-risk-head">
          <span>Termometro Risk-on/off</span>
          <b :style="{ color: riskThermometer.color || '#94a3b8' }">{{ riskThermometer.label }}</b>
          <em>{{ formatSignedLevel(riskThermometer.score) }}</em>
        </div>
        <div class="fvm-risk-track">
          <span class="fvm-risk-mid"></span>
          <span class="fvm-risk-needle" :style="riskNeedleStyle"></span>
        </div>
        <div class="fvm-risk-scale">
          <span>Risk-off {{ formatLevel(riskThermometer.risk_off_level) }}</span>
          <span>Conf {{ formatLevel(riskThermometer.confidence) }}</span>
          <span>Risk-on {{ formatLevel(riskThermometer.risk_on_level) }}</span>
        </div>
        <div class="fvm-risk-components">
          <span v-for="item in riskComponentItems" :key="item.key" :class="signedTone(item.value)">
            {{ item.label }} {{ formatSignedLevel(item.value) }}
          </span>
        </div>
      </div>

      <div v-if="metaRegimeSummary" class="fvm-meta-card">
        <div class="fvm-meta-card-copy">
          <div class="fvm-meta-card-head">
            <span class="fvm-meta-card-label">Meta-regime</span>
            <b :style="{ color: metaRegimeSummary.color || '#94a3b8' }">{{ metaRegimeSummary.name }}</b>
            <small>Conf {{ formatLevel(metaRegimeSummary.confidence) }}</small>
          </div>
          <div class="fvm-meta-card-tags">
            <span v-if="metaRegimeFlowText" class="fvm-meta-chip">{{ metaRegimeFlowText }}</span>
            <span v-if="metaRegimeCoreText" class="fvm-meta-chip">{{ metaRegimeCoreText }}</span>
            <span v-if="metaRegimePositiveLegsText" class="fvm-meta-chip positive">{{ metaRegimePositiveLegsText }}</span>
            <span v-if="metaRegimeNegativeLegsText" class="fvm-meta-chip negative">{{ metaRegimeNegativeLegsText }}</span>
            <span
              v-for="item in metaRegimeDriverItems.slice(0, 2)"
              :key="`meta-driver-${item.key}`"
              class="fvm-meta-chip soft"
              :title="metaDriverDescription(item.key)"
            >
              {{ metaDriverLabel(item.key) }}
            </span>
          </div>
        </div>
        <button type="button" class="fvm-meta-open" @click="showMetaHistoryModal = true">Hist ></button>
      </div>

      <div class="fvm-main-grid">
        <div class="fvm-panel fvm-price-panel">
          <div class="fvm-panel-head">
            <span class="fvm-panel-title">XB1 / Fair Value / Regime</span>
            <span class="fvm-panel-sub">{{ modelName }}</span>
          </div>
          <div class="fvm-canvas-wrap">
            <canvas
              ref="priceCanvas"
              class="fvm-price-canvas"
              @mousemove="handlePriceMove"
              @mouseleave="handleCanvasLeave"
            />
            <div v-if="displayRow" class="fvm-tooltip" :style="tooltipStyle">
              <span class="fvm-tooltip-time">{{ formatTime(displayRow.timestamp_ms) }}</span>
              <span class="fvm-tooltip-state" :style="{ color: stateColor(activeStateKey(displayRow)) }">
                {{ activeStateName(displayRow) }}
              </span>
              <span v-if="isTapeMode">DI {{ formatPrice(displayRow.tape_line_value) }}</span>
              <span>XB1 {{ formatPrice(displayRow.close) }}</span>
              <span>Exp {{ formatBps(displayRow.expected_return_bps) }}</span>
              <span v-if="riskThermometer">Risk {{ formatSignedLevel(riskThermometer.score) }}</span>
              <span>Out {{ formatScore(displayRow.outlier_score) }} / Disloc {{ formatScore(displayRow.dislocation_score) }}</span>
            </div>
          </div>
        </div>

        <div class="fvm-panel fvm-side-panel">
          <div class="fvm-panel-head">
            <span class="fvm-panel-title">Probabilidades</span>
            <span class="fvm-panel-sub">estado filtrado</span>
          </div>
          <div class="fvm-state-list">
            <div v-for="item in stateProbabilityItems" :key="item.key" class="fvm-state-row">
              <span class="fvm-state-dot" :style="{ background: item.color }"></span>
              <span class="fvm-state-name">{{ item.name }}</span>
              <div class="fvm-state-track">
                <div class="fvm-state-fill" :style="{ width: `${item.probabilityPct}%`, background: item.color }"></div>
              </div>
              <span class="fvm-state-value">{{ formatPct(item.probability) }}</span>
            </div>
          </div>

          <div class="fvm-transition">
            <div class="fvm-panel-head compact">
              <span class="fvm-panel-title">Transicao</span>
              <span class="fvm-panel-sub">stay prob.</span>
            </div>
            <div v-for="item in stateDwellItems" :key="`dwell-${item.key}`" class="fvm-dwell-row">
              <span>{{ item.name }}</span>
              <b>{{ formatPct(item.stay_probability) }}</b>
              <em>{{ formatBars(item.expected_dwell_bars) }}</em>
            </div>
          </div>
        </div>
      </div>

      <div class="fvm-prob-panel fvm-panel" v-if="showProbabilities">
        <div class="fvm-panel-head">
          <span class="fvm-panel-title">Stack de regimes</span>
          <span class="fvm-panel-sub">probabilidade no tempo</span>
        </div>
        <canvas ref="probCanvas" class="fvm-prob-canvas" />
      </div>

      <div class="fvm-bottom-grid">
        <div class="fvm-panel fvm-heatmap-panel">
          <div class="fvm-panel-head">
            <span class="fvm-panel-title">Betas por regime</span>
            <span class="fvm-panel-sub">{{ heatmapFeatures.length }} fatores</span>
          </div>
          <div class="fvm-heatmap" :style="{ gridTemplateColumns: heatmapGridColumns }">
            <div class="fvm-heat-head"></div>
            <div v-for="feature in heatmapFeatures" :key="`h-${feature.key}`" class="fvm-heat-head">
              {{ feature.shortLabel }}
            </div>
            <template v-for="state in stateRows" :key="`row-${state.key}`">
              <div class="fvm-heat-state">
                <i :style="{ background: state.color }"></i>
                <span>{{ state.name }}</span>
              </div>
              <div
                v-for="feature in heatmapFeatures"
                :key="`${state.key}-${feature.key}`"
                class="fvm-heat-cell"
                :style="heatmapCellStyle(state.key, feature.key)"
                :title="`${state.name} / ${feature.label}: ${formatScore(heatmapCellValue(state.key, feature.key))}`"
              >
                {{ formatCompact(heatmapCellValue(state.key, feature.key)) }}
              </div>
            </template>
          </div>
        </div>

        <div class="fvm-panel fvm-strip-panel">
          <div class="fvm-panel-head">
            <span class="fvm-panel-title">Outlier / Dislocation</span>
            <span class="fvm-panel-sub">residuo Student-t</span>
          </div>
          <canvas
            ref="stripCanvas"
            class="fvm-strip-canvas"
            @mousemove="handlePriceMove"
            @mouseleave="handleCanvasLeave"
          />
          <div class="fvm-strip-legend">
            <span><i class="out"></i> Outlier</span>
            <span><i class="dis"></i> Dislocation</span>
            <span><i class="thr"></i> Limiares</span>
          </div>
        </div>
      </div>

      <div v-if="showMetaHistoryModal" class="fvm-modal-overlay" @click.self="showMetaHistoryModal = false">
        <div class="fvm-modal-card">
          <div class="fvm-modal-head">
            <div>
              <div class="fvm-panel-title">Historico do Meta-regime</div>
              <div class="fvm-panel-sub">{{ showCurrentSessionOnly ? 'sessao atual' : 'janela do widget' }}</div>
            </div>
            <button type="button" class="fvm-modal-close" @click="showMetaHistoryModal = false">x</button>
          </div>
          <div v-if="metaRegimeChart" class="fvm-meta-chart-wrap">
            <div class="fvm-panel-head compact">
              <span class="fvm-panel-title">Conviccao do Meta-regime</span>
              <span class="fvm-panel-sub">{{ metaRegimeChart.rangeLabel }}</span>
            </div>
            <svg
              class="fvm-meta-chart"
              :viewBox="`0 0 ${metaRegimeChart.width} ${metaRegimeChart.height}`"
              preserveAspectRatio="none"
            >
              <line
                v-for="tick in metaRegimeChart.yTicks"
                :key="`meta-tick-${tick.value}`"
                :x1="metaRegimeChart.marginLeft"
                :x2="metaRegimeChart.width - metaRegimeChart.marginRight"
                :y1="tick.y"
                :y2="tick.y"
                class="fvm-meta-chart-grid"
              />
              <text
                v-for="tick in metaRegimeChart.yTicks"
                :key="`meta-label-${tick.value}`"
                :x="10"
                :y="tick.y + 4"
                class="fvm-meta-chart-axis"
              >
                {{ tick.label }}
              </text>
              <rect
                v-for="band in metaRegimeChart.bands"
                :key="`meta-band-${band.index}`"
                :x="band.x"
                :y="metaRegimeChart.marginTop"
                :width="band.width"
                :height="metaRegimeChart.plotHeight"
                :fill="band.fill"
              >
                <title>{{ band.title }}</title>
              </rect>
              <path :d="metaRegimeChart.path" class="fvm-meta-chart-line" />
              <circle
                v-for="dot in metaRegimeChart.dots"
                :key="`meta-dot-${dot.index}`"
                :cx="dot.x"
                :cy="dot.y"
                :r="dot.r"
                :fill="dot.fill"
                class="fvm-meta-chart-dot"
              >
                <title>{{ dot.title }}</title>
              </circle>
              <text
                v-for="label in metaRegimeChart.xLabels"
                :key="`meta-x-${label.key}`"
                :x="label.x"
                :y="metaRegimeChart.height - 10"
                class="fvm-meta-chart-axis"
                :text-anchor="label.anchor"
              >
                {{ label.text }}
              </text>
            </svg>
          </div>
          <div class="fvm-meta-counts">
            <span
              v-for="item in metaRegimeCounts"
              :key="`meta-count-${item.key}`"
              class="fvm-meta-count"
              :style="{ '--meta-color': item.color }"
              :title="item.description"
            >
              {{ item.name }} {{ item.count }}
            </span>
          </div>
          <div class="fvm-meta-history">
            <div v-for="row in metaRegimeHistoryRows" :key="`meta-row-${row.timestamp_ms}`" class="fvm-meta-history-row">
              <div class="fvm-meta-history-main">
                <span class="fvm-meta-history-time">{{ formatTime(row.timestamp_ms) }}</span>
                <span class="fvm-meta-history-badge" :style="{ '--meta-color': row.meta_regime_color || '#94a3b8' }">
                  {{ row.meta_regime_name || row.meta_regime_key }}
                </span>
                <span class="fvm-meta-history-conf">Conf {{ formatLevel(row.meta_regime_confidence) }}</span>
              </div>
              <div class="fvm-meta-history-sub">
                <span>{{ rowMetaCoreSummary(row) }}</span>
                <span v-if="rowMetaLegText(row, 'positive_legs', '+')">{{ rowMetaLegText(row, 'positive_legs', '+') }}</span>
                <span v-if="rowMetaLegText(row, 'negative_legs', '-')">{{ rowMetaLegText(row, 'negative_legs', '-') }}</span>
                <span
                  v-for="item in (row.meta_regime_drivers || []).slice(0, 2)"
                  :key="`meta-history-driver-${row.timestamp_ms}-${item.key}`"
                  :title="metaDriverDescription(item.key)"
                >
                  {{ metaDriverLabel(item.key) }}
                </span>
              </div>
            </div>
            <div v-if="!metaRegimeHistoryRows.length" class="fvm-empty compact">Sem historico do meta-regime nesta janela.</div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { getFairValueMarkovRegime, getFairValueMarkovRegimeLatest } from '@/api/macro.js'

const props = defineProps({
  modelData: { type: Object, default: null },
  refreshNonce: { type: Number, default: 0 },
})

const CACHE_KEY = 'discovery:fair-value-markov-regime:latest:v8'
const FULL_TIMEOUT_MS = 30_000
const HOT_TIMEOUT_MS = 7_500
const HOT_REFRESH_MS = 4_000
const NONCE_THROTTLE_MS = 45_000
const SNAPSHOT_REFRESH_RETRY_MS = 25_000
const CURRENT_SESSION_FORCE_REFRESH_MS = 30_000
const MAX_PLOT_ROWS = 360

const FALLBACK_STATES = [
  { id: 0, key: 'risk_on', name: 'Risk-on', color: '#22c55e' },
  { id: 1, key: 'risk_off', name: 'Risk-off', color: '#f59e0b' },
  { id: 2, key: 'local_stress', name: 'Local stress', color: '#f97316' },
  { id: 3, key: 'local_relief', name: 'Alivio local', color: '#14b8a6' },
  { id: 4, key: 'stress', name: 'Stress', color: '#ef4444' },
  { id: 5, key: 'dislocation', name: 'Dislocation', color: '#8b5cf6' },
]

const TAPE_FALLBACK_STATES = [
  { id: 0, key: 'expansion', name: 'Expansao', color: '#38bdf8' },
  { id: 1, key: 'lateral', name: 'Lateralidade', color: '#94a3b8' },
  { id: 2, key: 'stop_hunt', name: 'Stop hunt', color: '#f59e0b' },
  { id: 3, key: 'trend', name: 'Tendencia clara', color: '#22c55e' },
  { id: 4, key: 'panic', name: 'Panico', color: '#ef4444' },
]

const rootEl = ref(null)
const priceCanvas = ref(null)
const probCanvas = ref(null)
const stripCanvas = ref(null)
const payload = ref(null)
const loading = ref(false)
const errorMsg = ref('')
const viewMode = ref('legacy')
const showRegimeBands = ref(true)
const showTapeLine = ref(true)
const showCore = ref(true)
const showExpected = ref(true)
const showProbabilities = ref(true)
const showCurrentSessionOnly = ref(false)
const showMetaHistoryModal = ref(false)
const hoverIndex = ref(null)
const tooltipPosition = ref({ x: 16, y: 16 })

let resizeObserver = null
let drawRaf = 0
let reloadPromise = null
let hotReloadPromise = null
let hotTimer = null
let snapshotRefreshTimer = null
let lastReloadStartedAt = 0
let lastCurrentSessionForceRefreshAt = 0

const macroStates = computed(() => {
  const raw = Array.isArray(payload.value?.states) && payload.value.states.length
    ? payload.value.states
    : FALLBACK_STATES
  return raw.map((item, index) => ({
    id: Number.isFinite(Number(item.id)) ? Number(item.id) : index,
    key: String(item.key || `state_${index}`),
    name: String(item.name || item.key || `State ${index + 1}`),
    color: String(item.color || FALLBACK_STATES[index]?.color || '#94a3b8'),
    latest_probability: finite(item.latest_probability, 0),
    stay_probability: finite(item.stay_probability, 0),
    expected_dwell_bars: finite(item.expected_dwell_bars, 0),
  }))
})

const tapeStates = computed(() => {
  const raw = Array.isArray(payload.value?.tape_regime?.states) && payload.value.tape_regime.states.length
    ? payload.value.tape_regime.states
    : TAPE_FALLBACK_STATES
  return raw.map((item, index) => ({
    id: Number.isFinite(Number(item.id)) ? Number(item.id) : index,
    key: String(item.key || `tape_state_${index}`),
    name: String(item.name || item.key || `Tape ${index + 1}`),
    color: String(item.color || TAPE_FALLBACK_STATES[index]?.color || '#94a3b8'),
    latest_probability: finite(item.latest_probability, 0),
    stay_probability: finite(item.stay_probability, 0),
    expected_dwell_bars: finite(item.expected_dwell_bars, 0),
  }))
})

const isTapeMode = computed(() => viewMode.value === 'tape')
const states = computed(() => (isTapeMode.value ? tapeStates.value : macroStates.value))
const stateRows = computed(() => macroStates.value)
const rows = computed(() => {
  const rawRows = Array.isArray(payload.value?.rows) ? payload.value.rows : []
  return rawRows
    .filter(row => Number.isFinite(Number(row?.timestamp_ms)) && Number.isFinite(Number(row?.close)))
    .sort((left, right) => Number(left.timestamp_ms) - Number(right.timestamp_ms))
})
const latestRow = computed(() => payload.value?.latest || rows.value[rows.value.length - 1] || null)
const sessionRowCounts = computed(() => {
  const counts = new Map()
  for (const row of rows.value) {
    const sessionDate = String(row?.session_date || '').trim()
    if (!sessionDate) continue
    counts.set(sessionDate, (counts.get(sessionDate) || 0) + 1)
  }
  return counts
})
const latestSessionDate = computed(() => {
  const sessions = Array.isArray(payload.value?.sessions) ? payload.value.sessions : []
  for (let index = sessions.length - 1; index >= 0; index -= 1) {
    const sessionDate = String(sessions[index]?.date || sessions[index]?.session_date || '').trim()
    const candleCount = Number(sessions[index]?.candle_count)
    if (sessionDate && (!Number.isFinite(candleCount) || candleCount > 0)) return sessionDate
  }
  for (let index = rows.value.length - 1; index >= 0; index -= 1) {
    const value = String(rows.value[index]?.session_date || '').trim()
    if (value && (sessionRowCounts.value.get(value) || 0) > 1) return value
  }
  const latestSession = String(latestRow.value?.session_date || '').trim()
  if (latestSession) return latestSession
  return ''
})
const filteredRows = computed(() => {
  if (!showCurrentSessionOnly.value || !latestSessionDate.value) return rows.value
  return rows.value.filter(row => String(row?.session_date || '').trim() === latestSessionDate.value)
})
const plotRows = computed(() => filteredRows.value.slice(-MAX_PLOT_ROWS))
const displayRow = computed(() => {
  const index = hoverIndex.value
  if (index !== null && plotRows.value[index]) return plotRows.value[index]
  return plotRows.value[plotRows.value.length - 1] || latestRow.value
})
const modelName = computed(() => (
  isTapeMode.value
    ? (payload.value?.tape_regime?.model || 'sticky_student_t_xb1_tape_regime')
    : (payload.value?.model || 'robust_sticky_student_t_markov_regression')
))
const latestState = computed(() => stateForRow(displayRow.value || latestRow.value))
const latestStateName = computed(() => latestState.value?.name || activeStateName(displayRow.value || latestRow.value))
const latestStateColor = computed(() => latestState.value?.color || '#94a3b8')
const latestStateProbability = computed(() => {
  const row = displayRow.value || latestRow.value
  const state = stateForRow(row)
  const probs = activeProbabilities(row)
  return finite(probs[state?.id ?? 0], state?.latest_probability || 0) || 0
})
const sessionLabel = computed(() => {
  if (showCurrentSessionOnly.value && latestSessionDate.value) {
    return `Sessao atual: ${latestSessionDate.value} (${plotRows.value.length} barras)`
  }
  const sessions = payload.value?.sessions || []
  if (!sessions.length) return ''
  const first = sessions[0]?.date || sessions[0]?.session_date
  const last = sessions[sessions.length - 1]?.date || sessions[sessions.length - 1]?.session_date
  return `${sessions.length} sessoes: ${first || '-'} a ${last || '-'}`
})
const stateProbabilityItems = computed(() => {
  const row = displayRow.value || latestRow.value
  const probs = activeProbabilities(row)
  return states.value.map((state, index) => {
    const probability = finite(probs[index], state.latest_probability || 0) || 0
    return {
      ...state,
      probability,
      probabilityPct: clamp(probability * 100, 0, 100),
    }
  })
})
const stateDwellItems = computed(() => states.value.map(state => ({
  ...state,
  stay_probability: finite(state.stay_probability, 0) || 0,
  expected_dwell_bars: finite(state.expected_dwell_bars, 0) || 0,
})))
const riskThermometer = computed(() => (
  displayRow.value?.risk_thermometer
  || payload.value?.risk_thermometer?.latest
  || null
))
const riskThermometerTone = computed(() => {
  const score = finite(riskThermometer.value?.score, 0) || 0
  if (score >= 35) return 'risk-on'
  if (score <= -35) return 'risk-off'
  if (score > 10) return 'constructive'
  if (score < -10) return 'defensive'
  return 'neutral'
})
const riskNeedleStyle = computed(() => {
  const score = finite(riskThermometer.value?.score, 0) || 0
  return {
    left: `${clamp((score + 100) / 2, 0, 100)}%`,
    background: riskThermometer.value?.color || '#94a3b8',
  }
})
const riskComponentItems = computed(() => {
  const components = riskThermometer.value?.components || {}
  const meta = Array.isArray(payload.value?.risk_thermometer?.components)
    ? payload.value.risk_thermometer.components
    : []
  const labels = new Map(meta.map(item => [item.key, item.label]))
  const orderedKeys = meta.length
    ? meta.map(item => item.key)
    : ['markov', 'legs', 'flow', 'local', 'correlation', 'trend', 'stress']
  return orderedKeys
    .filter(key => components[key] !== undefined && components[key] !== null)
    .map(key => ({
      key,
      label: labels.get(key) || {
        markov: 'Markov',
        legs: 'Pernas',
        flow: 'RPC',
        local: 'Brasil local',
        correlation: 'Correlacao',
        trend: 'Trend',
        stress: 'Stress',
      }[key] || key,
      value: finite(components[key], 0) || 0,
    }))
})
const metaRegimeSummary = computed(() => {
  const latest = payload.value?.meta_regime?.latest
  if (latest?.key) return latest
  const row = displayRow.value || latestRow.value
  if (!row?.meta_regime_key) return null
  return {
    key: row.meta_regime_key,
    name: row.meta_regime_name || row.meta_regime_key,
    color: row.meta_regime_color || '#94a3b8',
    description: row.meta_regime_description || '',
    confidence: finite(row.meta_regime_confidence, 0) || 0,
    drivers: Array.isArray(row.meta_regime_drivers) ? row.meta_regime_drivers : [],
    scores: row.meta_regime_scores || {},
    flow_activity: row.meta_regime_flow_activity || null,
    core_legs: row.core_leg_context || null,
  }
})
const metaRegimeFlow = computed(() => (
  metaRegimeSummary.value?.flow_activity
  || latestRow.value?.meta_regime_flow_activity
  || null
))
const metaRegimeCore = computed(() => (
  metaRegimeSummary.value?.core_legs
  || displayRow.value?.core_leg_context
  || latestRow.value?.core_leg_context
  || null
))
const metaRegimeDriverItems = computed(() => (
  Array.isArray(metaRegimeSummary.value?.drivers) ? metaRegimeSummary.value.drivers : []
))
const metaRegimeTimelineRows = computed(() => {
  const targetSessionDate = latestSessionDate.value
  const sessionRows = targetSessionDate
    ? rows.value.filter(row => String(row?.session_date || '').trim() === targetSessionDate)
    : plotRows.value
  const sessionStartRows = sessionRows.filter(row => {
    const parsed = Number(row?.timestamp_ms)
    if (!Number.isFinite(parsed)) return false
    const stamp = new Date(parsed)
    return stamp.getHours() > 9 || (stamp.getHours() === 9 && stamp.getMinutes() >= 0)
  })
  const baseRows = sessionStartRows.length ? sessionStartRows : sessionRows
  return [...baseRows]
    .filter(row => row?.meta_regime_key)
    .slice(-180)
})
const metaRegimeCounts = computed(() => {
  const counts = {}
  const states = Array.isArray(payload.value?.meta_regime?.states) ? payload.value.meta_regime.states : []
  const byKey = new Map(states.map(item => [item.key, item]))
  for (const row of metaRegimeTimelineRows.value) {
    const key = String(row?.meta_regime_key || '').trim()
    if (!key) continue
    counts[key] = (counts[key] || 0) + 1
  }
  return Object.entries(counts)
    .map(([key, count]) => ({
      key,
      count: Number(count) || 0,
      name: byKey.get(key)?.name || key,
      color: byKey.get(key)?.color || '#94a3b8',
      description: byKey.get(key)?.description || key,
    }))
    .sort((left, right) => right.count - left.count)
})
const metaRegimeHistoryRows = computed(() => (
  [...metaRegimeTimelineRows.value]
    .reverse()
))
const metaRegimeChart = computed(() => {
  const rows = metaRegimeTimelineRows.value
  if (!rows.length) return null
  const width = 760
  const height = 168
  const marginLeft = 28
  const marginRight = 10
  const marginTop = 12
  const marginBottom = 24
  const plotWidth = width - marginLeft - marginRight
  const plotHeight = height - marginTop - marginBottom
  const bandWidth = plotWidth / Math.max(rows.length, 1)
  const clampConf = value => clamp(finite(value, 0) || 0, 0, 100)
  const yForConf = conf => marginTop + ((100 - clampConf(conf)) / 100) * plotHeight
  const bands = rows.map((row, index) => {
    const x = marginLeft + (index * bandWidth)
    const conf = clampConf(row.meta_regime_confidence)
    return {
      index,
      x,
      width: Math.max(bandWidth - 0.75, 1),
      fill: withAlpha(row.meta_regime_color || '#94a3b8', 0.16),
      title: `${formatTime(row.timestamp_ms)} · ${row.meta_regime_name || row.meta_regime_key} · Conf ${formatLevel(conf)}`,
    }
  })
  const dots = rows.map((row, index) => {
    const x = marginLeft + (index * bandWidth) + (bandWidth / 2)
    const conf = clampConf(row.meta_regime_confidence)
    return {
      index,
      x,
      y: yForConf(conf),
      r: index === rows.length - 1 ? 3.4 : 2.3,
      fill: row.meta_regime_color || '#94a3b8',
      title: `${formatTime(row.timestamp_ms)} · ${row.meta_regime_name || row.meta_regime_key} · Conf ${formatLevel(conf)}`,
    }
  })
  const path = dots.map((dot, index) => `${index === 0 ? 'M' : 'L'} ${dot.x.toFixed(2)} ${dot.y.toFixed(2)}`).join(' ')
  const first = rows[0]
  const last = rows[rows.length - 1]
  return {
    width,
    height,
    marginLeft,
    marginRight,
    marginTop,
    marginBottom,
    plotHeight,
    bands,
    dots,
    path,
    yTicks: [0, 50, 100].map(value => ({ value, y: yForConf(value), label: `${value}` })),
    xLabels: [
      { key: 'first', x: marginLeft, text: formatTime(first?.timestamp_ms), anchor: 'start' },
      { key: 'last', x: width - marginRight, text: formatTime(last?.timestamp_ms), anchor: 'end' },
    ],
    rangeLabel: `${rows.length} candles`,
  }
})
const metaRegimeFlowText = computed(() => {
  const flow = metaRegimeFlow.value
  if (!flow) return ''
  const projected = finite(flow.projected_net_close)
  if (projected === undefined) return String(flow.bias_label || '')
  return `${flow.bias_label || 'Fluxo'} ${projected >= 0 ? '+' : ''}${formatCompact(projected)}`
})
const metaRegimeCoreText = computed(() => {
  const core = metaRegimeCore.value
  const leaders = Array.isArray(core?.leaders) ? core.leaders.filter(item => item?.label).slice(0, 2) : []
  if (!leaders.length) return ''
  return `${core?.direction_label || 'Core'}: ${leaders.map(item => item.label).join(' + ')}`
})
const metaRegimePositiveLegsText = computed(() => (
  rowMetaLegText({ core_leg_context: metaRegimeCore.value }, 'positive_legs', '+')
))
const metaRegimeNegativeLegsText = computed(() => (
  rowMetaLegText({ core_leg_context: metaRegimeCore.value }, 'negative_legs', '-')
))
const heatmapFeatures = computed(() => {
  const betas = payload.value?.state_betas || {}
  const featureMap = new Map()
  Object.values(betas).forEach(statePayload => {
    const features = statePayload?.features || {}
    Object.entries(features).forEach(([key, value]) => {
      const label = value?.label || prettyFeatureLabel(key)
      const score = Math.abs(finite(value?.beta_score, value?.beta) || 0)
      const current = featureMap.get(key) || { key, label, maxAbs: 0 }
      current.maxAbs = Math.max(current.maxAbs, score)
      featureMap.set(key, current)
    })
  })
  return [...featureMap.values()]
    .sort((left, right) => {
      const leftLeg = left.key.startsWith('leg_') ? 0 : 1
      const rightLeg = right.key.startsWith('leg_') ? 0 : 1
      if (leftLeg !== rightLeg) return leftLeg - rightLeg
      return right.maxAbs - left.maxAbs
    })
    .slice(0, 12)
    .map(item => ({ ...item, shortLabel: shortFeatureLabel(item.key, item.label) }))
})
const heatmapGridColumns = computed(() => `minmax(92px, 1.2fr) repeat(${Math.max(heatmapFeatures.value.length, 1)}, minmax(52px, 1fr))`)
const tooltipStyle = computed(() => ({
  left: `${tooltipPosition.value.x}px`,
  top: `${tooltipPosition.value.y}px`,
}))

function finite(value, fallback = undefined) {
  if (value === null || value === undefined || value === '') return fallback
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function clamp(value, lower, upper) {
  return Math.min(Math.max(Number(value) || 0, lower), upper)
}

function stateForRow(row) {
  if (!row) return states.value[0] || null
  const key = activeStateKey(row)
  const id = Number(isTapeMode.value ? row.tape_regime : row.dominant_state)
  return states.value.find(item => item.key === key)
    || states.value.find(item => item.id === id)
    || states.value[0]
}

function stateColor(keyOrId) {
  const state = states.value.find(item => item.key === keyOrId || item.id === Number(keyOrId))
  return state?.color || '#94a3b8'
}

function activeProbabilities(row) {
  if (!row) return []
  return isTapeMode.value ? (row.tape_state_probabilities || []) : (row.state_probabilities || [])
}

function activeStateKey(row) {
  if (!row) return ''
  return isTapeMode.value ? row.tape_regime_key : row.dominant_state_key
}

function activeStateName(row) {
  if (!row) return '-'
  return isTapeMode.value
    ? (row.tape_regime_name || row.tape_regime_key || '-')
    : (row.dominant_state_name || row.dominant_state_key || '-')
}

function withAlpha(color, alpha) {
  if (!color || !String(color).startsWith('#')) return `rgba(148,163,184,${alpha})`
  const hex = String(color).replace('#', '')
  const full = hex.length === 3 ? hex.split('').map(char => `${char}${char}`).join('') : hex
  const int = Number.parseInt(full, 16)
  if (!Number.isFinite(int)) return `rgba(148,163,184,${alpha})`
  const r = (int >> 16) & 255
  const g = (int >> 8) & 255
  const b = int & 255
  return `rgba(${r},${g},${b},${alpha})`
}

function buildVolContext() {
  const context = props.modelData?.market_context || props.modelData?.raw?.market_context || {}
  const summary = props.modelData?.summary || props.modelData?.raw?.summary || {}
  return {
    implied_vol_atm: context.implied_vol_atm ?? summary.implied_vol_atm ?? summary.iv_atm,
    implied_vol_daily_pct: context.implied_vol_daily_pct ?? summary.implied_vol_daily_pct,
    vol_of_vol_daily_pct: context.vol_of_vol_daily_pct ?? summary.vol_of_vol_daily_pct,
  }
}

function buildRequestPayload(forceRefresh = false) {
  return {
    sessions: 5,
    bar_minutes: 1,
    session_start: '09:00',
    session_end: '18:30',
    rolling_window_points: 60,
    vol_context: buildVolContext(),
    force_refresh: forceRefresh,
  }
}

function withLocalTimeout(promise, label, timeoutMs) {
  let timerId = null
  const timeoutPromise = new Promise((_, reject) => {
    timerId = setTimeout(() => reject(new Error(`${label} timed out after ${timeoutMs}ms`)), timeoutMs)
  })
  return Promise.race([promise, timeoutPromise]).finally(() => {
    if (timerId) clearTimeout(timerId)
  })
}

async function reload({ background = false, forceRefresh = false } = {}) {
  if (reloadPromise) return reloadPromise
  reloadPromise = runReload({ background, forceRefresh }).finally(() => {
    reloadPromise = null
  })
  return reloadPromise
}

async function runReload({ background = false, forceRefresh = false } = {}) {
  if (!background) loading.value = true
  if (!background || !payload.value?.rows?.length) errorMsg.value = ''
  lastReloadStartedAt = Date.now()
  try {
    const res = await withLocalTimeout(
      getFairValueMarkovRegime(buildRequestPayload(forceRefresh)),
      'Fair Value Markov',
      FULL_TIMEOUT_MS,
    )
    const nextPayload = res?.data?.data || res?.data || res
    payload.value = nextPayload
    persistCache()
    await nextTick()
    scheduleDraw()
    refreshLatestPoint()
    scheduleSnapshotRefreshFollowUp(nextPayload)
  } catch (error) {
    if (payload.value?.rows?.length) {
      errorMsg.value = 'Atualizacao lenta; mantendo ultimo snapshot'
    } else {
      errorMsg.value = error?.message || 'Erro ao carregar regime Markov'
    }
    console.error('[FairValueMarkovRegimeWidget] load error', error)
  } finally {
    loading.value = false
  }
}

function scheduleSnapshotRefreshFollowUp(sourcePayload = {}) {
  if (!sourcePayload?.background_refresh_started && !sourcePayload?.cache_stale) return
  if (snapshotRefreshTimer) clearTimeout(snapshotRefreshTimer)
  snapshotRefreshTimer = setTimeout(() => {
    snapshotRefreshTimer = null
    reload({ background: true })
  }, SNAPSHOT_REFRESH_RETRY_MS)
}

function ensureCurrentSessionHistory() {
  if (!showCurrentSessionOnly.value) return
  const liveSessionDate = String(latestRow.value?.session_date || '').trim()
  const targetSessionDate = liveSessionDate || latestSessionDate.value
  if (!targetSessionDate) return
  const currentSessionCount = rows.value.filter(row => (
    String(row?.session_date || '').trim() === targetSessionDate
  )).length
  const sessionMetadataHasTarget = (payload.value?.sessions || []).some(item => (
    String(item?.date || item?.session_date || '').trim() === targetSessionDate
  ))
  if (currentSessionCount > 1 && sessionMetadataHasTarget) return
  const now = Date.now()
  if (now - lastCurrentSessionForceRefreshAt < CURRENT_SESSION_FORCE_REFRESH_MS) return
  lastCurrentSessionForceRefreshAt = now
  reload({ background: true, forceRefresh: true })
}

function applyLatestRow(nextRow, sourcePayload = {}) {
  if (!nextRow || !payload.value?.rows?.length) return false
  const timestampMs = Number(nextRow.timestamp_ms)
  if (!Number.isFinite(timestampMs)) return false
  const nextRows = [...(payload.value.rows || [])]
  const lastTimestamp = Number(nextRows[nextRows.length - 1]?.timestamp_ms || 0)
  if (lastTimestamp && timestampMs < lastTimestamp) return false
  const existingIndex = nextRows.findIndex(row => Number(row?.timestamp_ms) === timestampMs)
  if (existingIndex >= 0) {
    nextRows[existingIndex] = { ...nextRows[existingIndex], ...nextRow }
  } else {
    nextRows.push(nextRow)
  }
  nextRows.sort((left, right) => Number(left?.timestamp_ms || 0) - Number(right?.timestamp_ms || 0))
  payload.value = {
    ...payload.value,
    rows: nextRows,
    latest: nextRows[nextRows.length - 1],
    generated_at: sourcePayload.generated_at || payload.value.generated_at,
    meta_regime: sourcePayload.meta_regime || payload.value.meta_regime,
    risk_thermometer: sourcePayload.risk_thermometer || payload.value.risk_thermometer,
    hot_overlay: true,
  }
  persistCache()
  scheduleDraw()
  ensureCurrentSessionHistory()
  return true
}

async function refreshLatestPoint() {
  if (hotReloadPromise || !payload.value?.rows?.length) return hotReloadPromise
  hotReloadPromise = runRefreshLatestPoint().finally(() => {
    hotReloadPromise = null
  })
  return hotReloadPromise
}

async function runRefreshLatestPoint() {
  try {
    const res = await withLocalTimeout(
      getFairValueMarkovRegimeLatest(buildRequestPayload(false)),
      'Fair Value Markov latest',
      HOT_TIMEOUT_MS,
    )
    const nextPayload = res?.data?.data || res?.data || res
    const nextRow = nextPayload?.latest || (Array.isArray(nextPayload?.rows) ? nextPayload.rows[0] : null)
    if (nextRow) {
      applyLatestRow(nextRow, nextPayload)
      if (errorMsg.value === 'Atualizacao lenta; mantendo ultimo snapshot') errorMsg.value = ''
    }
  } catch (error) {
    console.debug('[FairValueMarkovRegimeWidget] hot update skipped', error)
  }
}

function persistCache() {
  try {
    if (!payload.value?.rows?.length) return
    localStorage.setItem(CACHE_KEY, JSON.stringify({
      storedAt: Date.now(),
      payload: payload.value,
    }))
  } catch {
    // Ignore localStorage failures.
  }
}

function restoreCache() {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw)
    if (!parsed?.payload || Date.now() - Number(parsed.storedAt || 0) > 24 * 60 * 60 * 1000) return
    payload.value = parsed.payload
  } catch {
    // Ignore corrupted cache.
  }
}

function setupCanvas(canvas) {
  if (!canvas) return null
  const rect = canvas.getBoundingClientRect()
  const width = Math.max(1, Math.floor(rect.width || canvas.clientWidth || 1))
  const height = Math.max(1, Math.floor(rect.height || canvas.clientHeight || 1))
  const dpr = Math.max(window.devicePixelRatio || 1, 1)
  if (canvas.width !== Math.floor(width * dpr) || canvas.height !== Math.floor(height * dpr)) {
    canvas.width = Math.floor(width * dpr)
    canvas.height = Math.floor(height * dpr)
  }
  const ctx = canvas.getContext('2d')
  if (!ctx) return null
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, width, height)
  return { ctx, width, height }
}

function scheduleDraw() {
  if (drawRaf) cancelAnimationFrame(drawRaf)
  drawRaf = requestAnimationFrame(() => {
    drawRaf = 0
    drawPriceCanvas()
    drawProbabilityCanvas()
    drawStripCanvas()
  })
}

function priceValue(row, key, fallback) {
  return finite(row?.[key], fallback)
}

function collectPriceValues(series) {
  const values = []
  series.forEach(row => {
    const keys = ['open', 'high', 'low', 'close', 'fair_value_core', 'fair_value_shadow']
    if (isTapeMode.value) keys.push('tape_line_value')
    keys.forEach(key => {
      const value = finite(row?.[key])
      if (value !== undefined) values.push(value)
    })
    const expectedClose = finite(row?.close) + finite(row?.expected_move_points, 0)
    if (Number.isFinite(expectedClose)) values.push(expectedClose)
  })
  return values
}

function drawPriceCanvas() {
  const setup = setupCanvas(priceCanvas.value)
  const series = plotRows.value
  if (!setup || !series.length) return
  const { ctx, width, height } = setup
  const pad = { left: 54, right: 18, top: 16, bottom: 30 }
  const plotW = Math.max(1, width - pad.left - pad.right)
  const plotH = Math.max(1, height - pad.top - pad.bottom)
  const values = collectPriceValues(series)
  let min = Math.min(...values)
  let max = Math.max(...values)
  if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) {
    min = (finite(series[0]?.close, 0) || 0) - 10
    max = min + 20
  }
  const margin = Math.max((max - min) * 0.08, 8)
  min -= margin
  max += margin
  const xAt = index => pad.left + (series.length === 1 ? plotW / 2 : (index / (series.length - 1)) * plotW)
  const yAt = value => pad.top + ((max - value) / Math.max(max - min, 1e-9)) * plotH
  const step = plotW / Math.max(series.length, 1)

  ctx.fillStyle = '#07111f'
  ctx.fillRect(0, 0, width, height)
  ctx.strokeStyle = 'rgba(148,163,184,0.12)'
  ctx.lineWidth = 1
  for (let i = 0; i <= 4; i += 1) {
    const y = pad.top + (plotH * i) / 4
    ctx.beginPath()
    ctx.moveTo(pad.left, y)
    ctx.lineTo(width - pad.right, y)
    ctx.stroke()
  }

  if (showRegimeBands.value) {
    series.forEach((row, index) => {
      const state = stateForRow(row)
      const probs = activeProbabilities(row)
      const prob = finite(probs?.[state?.id ?? 0], 0.45) || 0.45
      ctx.fillStyle = withAlpha(state?.color || '#94a3b8', 0.06 + clamp(prob, 0, 1) * 0.14)
      ctx.fillRect(pad.left + index * step, pad.top, Math.ceil(step) + 1, plotH)
    })
  }

  if (series.length > 180) {
    drawLine(ctx, series.map((row, index) => [xAt(index), yAt(finite(row.close, 0))]), '#e5e7eb', 1.4)
  } else {
    const candleW = clamp(step * 0.58, 2, 8)
    series.forEach((row, index) => {
      const open = priceValue(row, 'open', row.close)
      const high = priceValue(row, 'high', Math.max(open, row.close))
      const low = priceValue(row, 'low', Math.min(open, row.close))
      const close = priceValue(row, 'close', open)
      const x = xAt(index)
      const up = close >= open
      ctx.strokeStyle = up ? '#34d399' : '#fb7185'
      ctx.fillStyle = up ? 'rgba(52,211,153,0.72)' : 'rgba(251,113,133,0.72)'
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(x, yAt(high))
      ctx.lineTo(x, yAt(low))
      ctx.stroke()
      const yOpen = yAt(open)
      const yClose = yAt(close)
      ctx.fillRect(x - candleW / 2, Math.min(yOpen, yClose), candleW, Math.max(Math.abs(yClose - yOpen), 1.3))
    })
  }

  if (showCore.value) {
    drawLine(ctx, series.map((row, index) => [xAt(index), yAt(finite(row.fair_value_core, row.close))]), '#38bdf8', 1.6)
    drawLine(ctx, series.map((row, index) => [xAt(index), yAt(finite(row.fair_value_shadow, row.close))]), '#f472b6', 1.2, [5, 4])
  }
  if (showExpected.value) {
    drawLine(ctx, series.map((row, index) => {
      const expected = finite(row.close, 0) + finite(row.expected_move_points, 0)
      return [xAt(index), yAt(expected)]
    }), '#fde68a', 1.4, [3, 4])
  }
  if (isTapeMode.value && showTapeLine.value) {
    drawSegmentedTapeLine(ctx, series, xAt, yAt)
  }

  ctx.fillStyle = 'rgba(203,213,225,0.72)'
  ctx.font = '11px Inter, system-ui, sans-serif'
  ctx.textAlign = 'right'
  ctx.textBaseline = 'middle'
  for (let i = 0; i <= 4; i += 1) {
    const value = max - ((max - min) * i) / 4
    ctx.fillText(formatPrice(value), pad.left - 7, pad.top + (plotH * i) / 4)
  }

  drawTimeAxis(ctx, series, xAt, height - 12)
  drawHoverLine(ctx, xAt, pad.top, plotH)
}

function drawProbabilityCanvas() {
  const setup = setupCanvas(probCanvas.value)
  const series = plotRows.value
  if (!setup || !series.length || !showProbabilities.value) return
  const { ctx, width, height } = setup
  const pad = { left: 42, right: 12, top: 10, bottom: 20 }
  const plotW = Math.max(1, width - pad.left - pad.right)
  const plotH = Math.max(1, height - pad.top - pad.bottom)
  const step = plotW / Math.max(series.length, 1)
  ctx.fillStyle = '#07111f'
  ctx.fillRect(0, 0, width, height)
  ctx.strokeStyle = 'rgba(148,163,184,0.12)'
  ctx.beginPath()
  ctx.moveTo(pad.left, pad.top + plotH / 2)
  ctx.lineTo(width - pad.right, pad.top + plotH / 2)
  ctx.stroke()
  series.forEach((row, index) => {
    let y = pad.top + plotH
    const probs = activeProbabilities(row)
    states.value.forEach((state, stateIndex) => {
      const probability = clamp(finite(probs[stateIndex], 0) || 0, 0, 1)
      const barH = probability * plotH
      ctx.fillStyle = withAlpha(state.color, 0.68)
      ctx.fillRect(pad.left + index * step, y - barH, Math.ceil(step) + 1, barH)
      y -= barH
    })
  })
  ctx.fillStyle = 'rgba(203,213,225,0.72)'
  ctx.font = '11px Inter, system-ui, sans-serif'
  ctx.textAlign = 'right'
  ctx.fillText('100%', pad.left - 6, pad.top + 4)
  ctx.fillText('50%', pad.left - 6, pad.top + plotH / 2 + 4)
  drawHoverLine(ctx, index => pad.left + (index / Math.max(series.length - 1, 1)) * plotW, pad.top, plotH)
}

function drawStripCanvas() {
  const setup = setupCanvas(stripCanvas.value)
  const series = plotRows.value
  if (!setup || !series.length) return
  const { ctx, width, height } = setup
  const pad = { left: 38, right: 12, top: 12, bottom: 18 }
  const plotW = Math.max(1, width - pad.left - pad.right)
  const plotH = Math.max(1, height - pad.top - pad.bottom)
  const mid = pad.top + plotH / 2
  const step = plotW / Math.max(series.length, 1)
  const maxOut = Math.max(3.2, ...series.map(row => finite(row.outlier_score, 0) || 0))
  const maxDis = Math.max(100, ...series.map(row => finite(row.dislocation_score, 0) || 0))
  ctx.fillStyle = '#07111f'
  ctx.fillRect(0, 0, width, height)
  ctx.strokeStyle = 'rgba(148,163,184,0.18)'
  ctx.beginPath()
  ctx.moveTo(pad.left, mid)
  ctx.lineTo(width - pad.right, mid)
  ctx.stroke()

  series.forEach((row, index) => {
    const x = pad.left + index * step
    const outlier = clamp((finite(row.outlier_score, 0) || 0) / maxOut, 0, 1)
    const dislocation = clamp((finite(row.dislocation_score, 0) || 0) / maxDis, 0, 1)
    ctx.fillStyle = 'rgba(56,189,248,0.72)'
    ctx.fillRect(x, mid - outlier * (plotH / 2), Math.ceil(step) + 1, outlier * (plotH / 2))
    ctx.fillStyle = 'rgba(139,92,246,0.72)'
    ctx.fillRect(x, mid, Math.ceil(step) + 1, dislocation * (plotH / 2))
  })

  drawThreshold(ctx, pad.left, width - pad.right, mid - (2 / maxOut) * (plotH / 2), '#38bdf8')
  drawThreshold(ctx, pad.left, width - pad.right, mid + (70 / maxDis) * (plotH / 2), '#8b5cf6')
  drawHoverLine(ctx, index => pad.left + (index / Math.max(series.length - 1, 1)) * plotW, pad.top, plotH)
}

function drawLine(ctx, points, color, width = 1, dash = []) {
  const valid = points.filter(point => Number.isFinite(point[0]) && Number.isFinite(point[1]))
  if (valid.length < 2) return
  ctx.save()
  ctx.strokeStyle = color
  ctx.lineWidth = width
  ctx.setLineDash(dash)
  ctx.beginPath()
  valid.forEach(([x, y], index) => {
    if (index === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  })
  ctx.stroke()
  ctx.restore()
}

function drawSegmentedTapeLine(ctx, series, xAt, yAt) {
  if (!series.length) return
  ctx.save()
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  for (let index = 1; index < series.length; index += 1) {
    const previous = series[index - 1]
    const current = series[index]
    const y0Value = finite(previous.tape_line_value)
    const y1Value = finite(current.tape_line_value)
    if (y0Value === undefined || y1Value === undefined) continue
    const color = current.tape_regime_color || stateColor(current.tape_regime_key)
    ctx.strokeStyle = 'rgba(2,6,23,0.72)'
    ctx.lineWidth = 5.4
    ctx.beginPath()
    ctx.moveTo(xAt(index - 1), yAt(y0Value))
    ctx.lineTo(xAt(index), yAt(y1Value))
    ctx.stroke()
    ctx.strokeStyle = color
    ctx.lineWidth = 2.6
    ctx.beginPath()
    ctx.moveTo(xAt(index - 1), yAt(y0Value))
    ctx.lineTo(xAt(index), yAt(y1Value))
    ctx.stroke()
  }
  const latest = series[series.length - 1]
  const latestValue = finite(latest?.tape_line_value)
  if (latestValue !== undefined) {
    ctx.fillStyle = latest.tape_regime_color || stateColor(latest.tape_regime_key)
    ctx.beginPath()
    ctx.arc(xAt(series.length - 1), yAt(latestValue), 4, 0, Math.PI * 2)
    ctx.fill()
  }
  ctx.restore()
}

function drawThreshold(ctx, left, right, y, color) {
  ctx.save()
  ctx.strokeStyle = withAlpha(color, 0.58)
  ctx.lineWidth = 1
  ctx.setLineDash([4, 4])
  ctx.beginPath()
  ctx.moveTo(left, y)
  ctx.lineTo(right, y)
  ctx.stroke()
  ctx.restore()
}

function drawHoverLine(ctx, xAt, top, plotH) {
  if (hoverIndex.value === null || !plotRows.value[hoverIndex.value]) return
  const x = xAt(hoverIndex.value)
  ctx.save()
  ctx.strokeStyle = 'rgba(248,250,252,0.38)'
  ctx.lineWidth = 1
  ctx.setLineDash([3, 3])
  ctx.beginPath()
  ctx.moveTo(x, top)
  ctx.lineTo(x, top + plotH)
  ctx.stroke()
  ctx.restore()
}

function drawTimeAxis(ctx, series, xAt, y) {
  if (!series.length) return
  const indices = [0, Math.floor(series.length / 2), series.length - 1]
  ctx.fillStyle = 'rgba(203,213,225,0.72)'
  ctx.font = '11px Inter, system-ui, sans-serif'
  ctx.textBaseline = 'middle'
  indices.forEach((index, itemIndex) => {
    ctx.textAlign = itemIndex === 0 ? 'left' : itemIndex === indices.length - 1 ? 'right' : 'center'
    ctx.fillText(formatTime(series[index]?.timestamp_ms), xAt(index), y)
  })
}

function handlePriceMove(event) {
  const canvas = event.currentTarget
  const rect = canvas.getBoundingClientRect()
  const series = plotRows.value
  if (!series.length) return
  const padLeft = canvas === priceCanvas.value ? 54 : 38
  const padRight = canvas === priceCanvas.value ? 18 : 12
  const plotW = Math.max(1, rect.width - padLeft - padRight)
  const ratio = clamp((event.clientX - rect.left - padLeft) / plotW, 0, 1)
  hoverIndex.value = Math.round(ratio * Math.max(series.length - 1, 0))
  tooltipPosition.value = {
    x: clamp(event.clientX - rect.left + 14, 12, Math.max(rect.width - 218, 12)),
    y: clamp(event.clientY - rect.top + 14, 12, Math.max(rect.height - 108, 12)),
  }
}

function handleCanvasLeave() {
  hoverIndex.value = null
}

function heatmapCellValue(stateKey, featureKey) {
  const value = payload.value?.state_betas?.[stateKey]?.features?.[featureKey]
  return finite(value?.beta_score, value?.beta) || 0
}

function heatmapCellStyle(stateKey, featureKey) {
  const value = heatmapCellValue(stateKey, featureKey)
  const strength = Math.min(Math.abs(value) / 2.2, 1)
  const color = value >= 0
    ? `rgba(34,197,94,${0.12 + strength * 0.58})`
    : `rgba(244,63,94,${0.12 + strength * 0.58})`
  return {
    background: color,
    borderColor: value >= 0 ? 'rgba(34,197,94,0.42)' : 'rgba(244,63,94,0.42)',
  }
}

function prettyFeatureLabel(key) {
  return String(key || '')
    .replace(/^leg_/, '')
    .replace(/_impact$/, '')
    .replace(/_/g, ' ')
}

function shortFeatureLabel(key, label) {
  const text = prettyFeatureLabel(key || label)
  const aliases = {
    equity_foreign: 'Eq ext',
    equity_local: 'Eq loc',
    commodities: 'Cmdty',
    private_credit: 'Credit',
    fair_value_gap_z: 'FV gap',
    core_shadow_gap: 'C/S gap',
    rpc_pressure: 'RPC',
    rpc_acceleration: 'RPC acc',
    rpc_slope: 'RPC slp',
    edge_bias: 'Edge',
  }
  return aliases[key?.replace(/^leg_/, '').replace(/_impact$/, '')] || text.split(' ').map(part => part.slice(0, 4)).join(' ')
}

function signedTone(value) {
  const parsed = finite(value, 0) || 0
  if (parsed > 0.05) return 'pos'
  if (parsed < -0.05) return 'neg'
  return ''
}

function formatPrice(value) {
  const parsed = finite(value)
  if (parsed === undefined) return '-'
  return parsed.toLocaleString('pt-BR', { maximumFractionDigits: 0 })
}

function formatPct(value) {
  const parsed = finite(value)
  if (parsed === undefined) return '-'
  return `${(parsed * 100).toFixed(0)}%`
}

function formatScore(value) {
  const parsed = finite(value)
  if (parsed === undefined) return '-'
  return Math.abs(parsed) >= 100 ? parsed.toFixed(0) : parsed.toFixed(1)
}

function formatSignedLevel(value) {
  const parsed = finite(value)
  if (parsed === undefined) return '-'
  return `${parsed >= 0 ? '+' : ''}${Math.round(parsed)}`
}

function formatLevel(value) {
  const parsed = finite(value)
  if (parsed === undefined) return '-'
  return Math.round(parsed).toString()
}

function formatCompact(value) {
  const parsed = finite(value, 0) || 0
  if (Math.abs(parsed) >= 10) return parsed.toFixed(0)
  if (Math.abs(parsed) >= 1) return parsed.toFixed(1)
  return parsed.toFixed(2)
}

function formatBps(value) {
  const parsed = finite(value)
  if (parsed === undefined) return '-'
  return `${parsed >= 0 ? '+' : ''}${parsed.toFixed(1)} bps`
}

function formatPoints(value) {
  const parsed = finite(value)
  if (parsed === undefined) return '-'
  return `${parsed >= 0 ? '+' : ''}${parsed.toFixed(0)}`
}

function formatBars(value) {
  const parsed = finite(value, 0) || 0
  if (parsed <= 0) return '-'
  return `${parsed.toFixed(parsed >= 10 ? 0 : 1)} bars`
}

function formatTime(timestampMs) {
  const parsed = Number(timestampMs)
  if (!Number.isFinite(parsed)) return '-'
  try {
    return new Intl.DateTimeFormat('pt-BR', {
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(parsed))
  } catch {
    return '-'
  }
}

function metaDriverLabel(key) {
  return {
    trend_support: 'trend',
    supportive_equity: 'equity',
    defensive_internal: 'interno',
    state_defensive: 'markov',
    positive_state: 'alivio',
    dislocation_drag: 'disloc',
    flow_drag: 'fluxo',
    corr_fracture: 'corr break',
    aligned_support: 'alinhado',
    panic_tail: 'panic',
    core_alignment: 'core',
    core_conflict: 'core contra',
    flow_positive: 'fluxo +',
    flow_negative: 'fluxo -',
  }[key] || key
}

function metaDriverDescription(key) {
  return {
    trend_support: 'Tape direcional e persistencia de movimento estao sustentando o estado atual.',
    supportive_equity: 'As pernas de bolsa e risco estao ajudando a leitura do meta-regime.',
    defensive_internal: 'DI, FX, funding ou credito seguem com assinatura mais defensiva.',
    state_defensive: 'O Markov principal ainda esta inclinado para risk-off, stress ou dislocation.',
    positive_state: 'Ha alivio estatistico nas probabilidades principais do regime.',
    dislocation_drag: 'Preco e fair value continuam desalinhados, com gap e dislocation relevantes.',
    flow_drag: 'Fluxo/RPC seguem atrapalhando a sustentacao do movimento.',
    corr_fracture: 'A correlacao entre os blocos local e externo esta quebrada ou instavel.',
    aligned_support: 'Local, externo e fair value estao andando mais alinhados.',
    panic_tail: 'Cauda de stress, range extremo ou pressao abrupta seguem presentes.',
    core_alignment: 'As pernas lideres do core estao alinhadas com a direcao esperada do fair value.',
    core_conflict: 'As pernas contrarias ao core estao fortes e disputando a direcao.',
    flow_positive: 'O Flow Activity Radar esta enxergando montagem de fluxo na direcao favoravel.',
    flow_negative: 'O Flow Activity Radar esta enxergando montagem de fluxo contra a leitura favoravel.',
  }[key] || key
}

function rowMetaCoreSummary(row) {
  const core = row?.core_leg_context
  const leaders = Array.isArray(core?.leaders) ? core.leaders.filter(item => item?.label).slice(0, 2) : []
  if (!leaders.length) return core?.direction_label || '-'
  return `${core?.direction_label || 'Core'}: ${leaders.map(item => item.label).join(' + ')}`
}

function rowMetaLegText(row, key, prefix) {
  const core = row?.core_leg_context
  const items = Array.isArray(core?.[key]) ? core[key].filter(item => item?.label).slice(0, 2) : []
  if (!items.length) return ''
  return `${prefix} ${items.map(item => item.label).join(' / ')}`
}

watch([
  plotRows,
  states,
  viewMode,
  showRegimeBands,
  showTapeLine,
  showCore,
  showExpected,
  showProbabilities,
  showCurrentSessionOnly,
  hoverIndex,
], () => scheduleDraw())

watch(showCurrentSessionOnly, () => {
  hoverIndex.value = null
  ensureCurrentSessionHistory()
})

watch(() => props.refreshNonce, value => {
  if (!value) return
  if (Date.now() - lastReloadStartedAt < NONCE_THROTTLE_MS) return
  reload({ background: true })
})

onMounted(async () => {
  restoreCache()
  await nextTick()
  if (rootEl.value) {
    resizeObserver = new ResizeObserver(() => scheduleDraw())
    resizeObserver.observe(rootEl.value)
  }
  scheduleDraw()
  reload({ background: Boolean(payload.value?.rows?.length) })
  hotTimer = setInterval(() => refreshLatestPoint(), HOT_REFRESH_MS)
})

onUnmounted(() => {
  if (hotTimer) clearInterval(hotTimer)
  if (snapshotRefreshTimer) clearTimeout(snapshotRefreshTimer)
  if (resizeObserver) resizeObserver.disconnect()
  if (drawRaf) cancelAnimationFrame(drawRaf)
})
</script>

<style scoped>
.fvm-root {
  position: relative;
  height: 100%;
  min-height: 420px;
  display: flex;
  flex-direction: column;
  color: #e5edf8;
  background: #08111f;
}

.fvm-toolbar {
  min-height: 38px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(15, 23, 42, 0.94);
  flex-wrap: wrap;
}

.fvm-state-badge,
.fvm-pill,
.fvm-btn {
  height: 24px;
  display: inline-flex;
  align-items: center;
  border-radius: 6px;
  font-size: 11px;
  line-height: 1;
  white-space: nowrap;
}

.fvm-state-badge {
  padding: 0 9px;
  color: #f8fafc;
  background: color-mix(in srgb, var(--state-color) 32%, #0f172a);
  border: 1px solid color-mix(in srgb, var(--state-color) 68%, transparent);
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0;
}

.fvm-pill {
  padding: 0 8px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  background: rgba(15, 23, 42, 0.82);
  color: #cbd5e1;
}

.fvm-pill.warn { color: #fbbf24; }
.fvm-pill.disloc { color: #c4b5fd; }

.fvm-sep {
  width: 1px;
  height: 22px;
  background: rgba(148, 163, 184, 0.2);
}

.fvm-mode-switch {
  height: 26px;
  display: inline-flex;
  align-items: center;
  padding: 2px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 7px;
  background: rgba(2, 6, 23, 0.36);
}

.fvm-mode-switch button {
  height: 20px;
  display: inline-flex;
  align-items: center;
  padding: 0 8px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: #94a3b8;
  font-size: 11px;
  line-height: 1;
  cursor: pointer;
  white-space: nowrap;
}

.fvm-mode-switch button.active {
  background: rgba(56, 189, 248, 0.18);
  color: #e0f2fe;
  box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.28);
}

.fvm-check {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: #9fb0c5;
  user-select: none;
  white-space: nowrap;
}

.fvm-check input {
  width: 13px;
  height: 13px;
  accent-color: #38bdf8;
}

.fvm-btn {
  padding: 0 10px;
  border: 1px solid rgba(56, 189, 248, 0.36);
  background: rgba(14, 165, 233, 0.14);
  color: #dff6ff;
  cursor: pointer;
}

.fvm-btn:disabled {
  opacity: 0.58;
  cursor: default;
}

.fvm-spacer {
  flex: 1 1 auto;
}

.fvm-meta,
.fvm-error {
  font-size: 11px;
  color: #94a3b8;
  white-space: nowrap;
}

.fvm-error {
  color: #fca5a5;
}

.fvm-empty {
  flex: 1;
  display: grid;
  place-items: center;
  min-height: 240px;
  color: #94a3b8;
  font-size: 13px;
}

.fvm-kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 8px;
  padding: 10px 10px 0;
}

.fvm-kpi {
  min-width: 0;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(15, 23, 42, 0.62);
  border-radius: 7px;
  padding: 8px 9px;
  display: grid;
  gap: 4px;
}

.fvm-kpi-label,
.fvm-panel-sub,
.fvm-kpi-sub {
  color: #8fa1b8;
  font-size: 11px;
}

.fvm-kpi-value {
  min-width: 0;
  color: #f8fafc;
  font-size: 18px;
  font-weight: 800;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fvm-kpi-value.pos { color: #5eead4; }
.fvm-kpi-value.neg { color: #fb7185; }

.fvm-risk-thermo {
  margin: 8px 10px 0;
  padding: 9px 10px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 7px;
  background: rgba(15, 23, 42, 0.58);
  display: grid;
  gap: 7px;
}

.fvm-risk-head,
.fvm-risk-scale,
.fvm-risk-components {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.fvm-risk-head span {
  color: #9fb0c5;
  font-size: 11px;
  font-weight: 700;
}

.fvm-risk-head b {
  font-size: 15px;
  line-height: 1;
}

.fvm-risk-head em {
  margin-left: auto;
  color: #f8fafc;
  font-style: normal;
  font-size: 18px;
  font-weight: 900;
  font-variant-numeric: tabular-nums;
}

.fvm-risk-track {
  position: relative;
  height: 12px;
  border-radius: 999px;
  background:
    linear-gradient(90deg,
      #ef4444 0%,
      #f97316 22%,
      #94a3b8 50%,
      #14b8a6 72%,
      #22c55e 100%);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.14);
}

.fvm-risk-mid {
  position: absolute;
  left: 50%;
  top: -3px;
  width: 1px;
  height: 18px;
  background: rgba(248, 250, 252, 0.48);
}

.fvm-risk-needle {
  position: absolute;
  top: 50%;
  width: 12px;
  height: 20px;
  border: 2px solid #08111f;
  border-radius: 999px;
  transform: translate(-50%, -50%);
  box-shadow: 0 0 0 1px rgba(248, 250, 252, 0.46), 0 5px 14px rgba(0, 0, 0, 0.34);
}

.fvm-risk-scale {
  justify-content: space-between;
  color: #8fa1b8;
  font-size: 11px;
}

.fvm-risk-components {
  flex-wrap: wrap;
}

.fvm-risk-components span {
  height: 21px;
  display: inline-flex;
  align-items: center;
  padding: 0 7px;
  border: 1px solid rgba(148, 163, 184, 0.15);
  border-radius: 6px;
  color: #cbd5e1;
  background: rgba(2, 6, 23, 0.26);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.fvm-risk-components span.pos {
  color: #5eead4;
  border-color: rgba(45, 212, 191, 0.24);
}

.fvm-risk-components span.neg {
  color: #fb7185;
  border-color: rgba(251, 113, 133, 0.24);
}

.fvm-meta-card {
  margin: 8px 10px 0;
  padding: 9px 10px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 7px;
  background: rgba(15, 23, 42, 0.5);
  display: flex;
  align-items: center;
  gap: 10px;
}

.fvm-meta-card-copy {
  min-width: 0;
  flex: 1 1 auto;
  display: grid;
  gap: 6px;
}

.fvm-meta-card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.fvm-meta-card-label,
.fvm-meta-card-head small {
  color: #8fa1b8;
  font-size: 11px;
}

.fvm-meta-card-head b {
  min-width: 0;
  font-size: 14px;
  line-height: 1;
  font-weight: 800;
}

.fvm-meta-card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.fvm-meta-chip {
  min-height: 22px;
  display: inline-flex;
  align-items: center;
  padding: 0 7px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 6px;
  color: #cbd5e1;
  background: rgba(2, 6, 23, 0.26);
  font-size: 11px;
}

.fvm-meta-chip.soft {
  color: #93c5fd;
  cursor: help;
}

.fvm-meta-chip.positive {
  color: #86efac;
}

.fvm-meta-chip.negative {
  color: #fdba74;
}

.fvm-meta-open {
  height: 24px;
  display: inline-flex;
  align-items: center;
  padding: 0 9px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 6px;
  background: rgba(2, 6, 23, 0.3);
  color: #dbeafe;
  font-size: 11px;
  cursor: pointer;
  white-space: nowrap;
}

.fvm-main-grid {
  display: grid;
  grid-template-columns: minmax(0, 2.4fr) minmax(230px, 0.8fr);
  gap: 10px;
  padding: 10px;
  min-height: 0;
}

.fvm-panel {
  min-width: 0;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(15, 23, 42, 0.46);
  border-radius: 7px;
  overflow: hidden;
}

.fvm-panel-head {
  min-height: 34px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
}

.fvm-panel-head.compact {
  padding: 8px 0 6px;
  border-bottom: 0;
}

.fvm-panel-title {
  color: #dbeafe;
  font-size: 12px;
  font-weight: 800;
}

.fvm-canvas-wrap {
  position: relative;
  height: 284px;
  min-height: 220px;
}

.fvm-price-canvas,
.fvm-prob-canvas,
.fvm-strip-canvas {
  width: 100%;
  height: 100%;
  display: block;
}

.fvm-tooltip {
  position: absolute;
  z-index: 2;
  width: 204px;
  display: grid;
  gap: 3px;
  padding: 8px;
  border: 1px solid rgba(148, 163, 184, 0.26);
  border-radius: 7px;
  background: rgba(2, 6, 23, 0.92);
  color: #cbd5e1;
  font-size: 11px;
  pointer-events: none;
  box-shadow: 0 12px 28px rgba(0, 0, 0, 0.24);
}

.fvm-tooltip-time {
  color: #93c5fd;
  font-weight: 800;
}

.fvm-tooltip-state {
  font-weight: 800;
}

.fvm-side-panel {
  padding: 0 10px 10px;
}

.fvm-state-list {
  display: grid;
  gap: 8px;
  padding-top: 8px;
}

.fvm-state-row {
  display: grid;
  grid-template-columns: 10px minmax(58px, 0.8fr) minmax(70px, 1.4fr) 38px;
  align-items: center;
  gap: 7px;
  min-width: 0;
}

.fvm-state-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.fvm-state-name,
.fvm-state-value,
.fvm-dwell-row {
  color: #cbd5e1;
  font-size: 11px;
}

.fvm-state-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fvm-state-track {
  height: 7px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.14);
  overflow: hidden;
}

.fvm-state-fill {
  height: 100%;
  min-width: 2px;
  border-radius: 999px;
}

.fvm-transition {
  margin-top: 12px;
  border-top: 1px solid rgba(148, 163, 184, 0.12);
}

.fvm-dwell-row {
  display: grid;
  grid-template-columns: minmax(72px, 1fr) 44px 54px;
  gap: 8px;
  padding: 5px 0;
  border-top: 1px solid rgba(148, 163, 184, 0.08);
}

.fvm-dwell-row b {
  color: #e2e8f0;
  font-weight: 800;
}

.fvm-dwell-row em {
  color: #94a3b8;
  font-style: normal;
  text-align: right;
}

.fvm-prob-panel {
  height: 118px;
  margin: 0 10px 10px;
}

.fvm-prob-canvas {
  height: 84px;
}

.fvm-bottom-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(260px, 0.75fr);
  gap: 10px;
  padding: 0 10px 10px;
  min-height: 0;
}

.fvm-heatmap {
  display: grid;
  gap: 4px;
  padding: 10px;
  overflow: auto;
}

.fvm-heat-head {
  min-width: 0;
  color: #8fa1b8;
  font-size: 10px;
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fvm-heat-state {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  color: #dbeafe;
  font-size: 11px;
  font-weight: 700;
}

.fvm-heat-state i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex: 0 0 auto;
}

.fvm-heat-state span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fvm-heat-cell {
  height: 28px;
  display: grid;
  place-items: center;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 5px;
  color: #f8fafc;
  font-size: 10px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}

.fvm-strip-panel {
  min-height: 168px;
}

.fvm-strip-canvas {
  height: 112px;
}

.fvm-strip-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 0 10px 10px;
  color: #94a3b8;
  font-size: 11px;
}

.fvm-strip-legend span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.fvm-strip-legend i {
  width: 10px;
  height: 3px;
  border-radius: 999px;
}

.fvm-strip-legend .out { background: #38bdf8; }
.fvm-strip-legend .dis { background: #8b5cf6; }
.fvm-strip-legend .thr { background: #e2e8f0; }

.fvm-modal-overlay {
  position: absolute;
  inset: 0;
  z-index: 24;
  display: grid;
  place-items: center;
  padding: 18px;
  background: rgba(2, 6, 23, 0.58);
}

.fvm-modal-card {
  width: min(860px, 100%);
  max-height: min(82vh, 720px);
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 9px;
  background: #07111f;
  box-shadow: 0 18px 44px rgba(0, 0, 0, 0.34);
  display: grid;
  grid-template-rows: auto auto auto minmax(0, 1fr);
  overflow: hidden;
}

.fvm-modal-head {
  min-height: 42px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 12px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
}

.fvm-modal-close {
  width: 24px;
  height: 24px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 6px;
  background: rgba(15, 23, 42, 0.76);
  color: #cbd5e1;
  cursor: pointer;
  line-height: 1;
}

.fvm-meta-counts {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 10px 12px 0;
  align-content: start;
}

.fvm-meta-chart-wrap {
  display: grid;
  gap: 8px;
  padding: 8px 12px 0;
}

.fvm-meta-chart {
  width: 100%;
  height: 168px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 8px;
  background:
    linear-gradient(180deg, rgba(15, 23, 42, 0.78), rgba(2, 6, 23, 0.7));
}

.fvm-meta-chart-grid {
  stroke: rgba(148, 163, 184, 0.16);
  stroke-width: 1;
}

.fvm-meta-chart-axis {
  fill: #8fa1b8;
  font-size: 10px;
}

.fvm-meta-chart-line {
  fill: none;
  stroke: #e2e8f0;
  stroke-width: 2.25;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.fvm-meta-chart-dot {
  stroke: rgba(2, 6, 23, 0.8);
  stroke-width: 1.2;
}

.fvm-meta-count {
  min-height: 22px;
  display: inline-flex;
  align-items: center;
  padding: 0 7px;
  border-radius: 6px;
  font-size: 11px;
  color: #e2e8f0;
  background: color-mix(in srgb, var(--meta-color) 16%, #0f172a);
  border: 1px solid color-mix(in srgb, var(--meta-color) 46%, transparent);
}

.fvm-meta-history {
  display: grid;
  gap: 8px;
  padding: 10px 12px 12px;
  overflow: auto;
}

.fvm-meta-history-row {
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 7px;
  padding: 8px 9px;
  display: grid;
  gap: 6px;
  background: rgba(15, 23, 42, 0.46);
}

.fvm-meta-history-main,
.fvm-meta-history-sub {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.fvm-meta-history-time,
.fvm-meta-history-conf,
.fvm-meta-history-sub {
  color: #94a3b8;
  font-size: 11px;
}

.fvm-meta-history-badge {
  min-height: 22px;
  display: inline-flex;
  align-items: center;
  padding: 0 7px;
  border-radius: 6px;
  font-size: 11px;
  color: #f8fafc;
  background: color-mix(in srgb, var(--meta-color) 18%, #0f172a);
  border: 1px solid color-mix(in srgb, var(--meta-color) 54%, transparent);
}

.fvm-empty.compact {
  min-height: 120px;
}

@media (max-width: 820px) {
  .fvm-kpi-grid,
  .fvm-main-grid,
  .fvm-bottom-grid {
    grid-template-columns: 1fr;
  }

  .fvm-canvas-wrap {
    height: 250px;
  }

  .fvm-modal-overlay {
    padding: 10px;
  }
}
</style>

<template>
  <div class="far-root">
    <div class="far-toolbar">
      <span class="far-badge">FAR</span>
      <span class="far-pill">{{ payload?.ticker || 'WIN' }}</span>
      <span class="far-pill" v-if="sessionDateLabel">Sessao {{ sessionDateLabel }}</span>
      <span class="far-pill" v-if="payload?.session?.latest_bucket_label">Ate {{ payload.session.latest_bucket_label }}</span>
      <span class="far-pill" v-if="summary">Ativos {{ summary.active_runs }}</span>
      <div class="far-spacer"></div>
      <button type="button" class="far-btn" :disabled="loading" @click="reload(true)">
        {{ loading ? '...' : 'Atualizar' }}
      </button>
      <span class="far-meta" v-if="payload?.source?.latest_snapshot_at">Fonte {{ formatTime(payload.source.latest_snapshot_at) }}</span>
      <span class="far-loading" v-if="loading">Carregando...</span>
      <span class="far-error" v-if="error && !loading">{{ error }}</span>
    </div>

    <div v-if="error && !payload" class="far-empty">{{ error }}</div>
    <div v-else-if="loading && !payload" class="far-empty">Carregando o radar de atividade relevante...</div>
    <div v-else-if="!payload?.ok" class="far-empty">
      {{ payload?.message || 'Ainda sem fluxo relevante catalogado para a sessao atual.' }}
    </div>

    <template v-else>
      <section class="far-reader" :class="readerToneClass">
        <div class="far-reader-copy">
          <div class="far-reader-kicker">Reader de fluxo</div>
          <div class="far-reader-title">{{ reader.headline }}</div>
          <p class="far-reader-text">{{ reader.summary }}</p>
          <ul class="far-reader-bullets">
            <li v-for="item in reader.bullets || []" :key="item">{{ item }}</li>
          </ul>
        </div>
        <div class="far-reader-side">
          <div class="far-side-card">
            <span class="far-side-label">{{ summary?.has_live_projection ? 'Net projetado' : 'Net historico' }}</span>
            <strong :class="valueTone(summary?.projected_net_close)">{{ formatContracts(summary?.projected_net_close) }}</strong>
            <small>{{ summary?.has_live_projection ? `${summary?.remaining_minutes_to_close || 0}min ate o fim` : 'sem projecao ativa' }}</small>
          </div>
          <div class="far-side-card">
            <span class="far-side-label">Holding medio</span>
            <strong>{{ formatScore(summary?.holding_score_mean ?? summary?.robot_score_mean) }}</strong>
            <small>confianca {{ formatScore(summary?.confidence_mean) }}</small>
          </div>
          <div class="far-side-card">
            <span class="far-side-label">Concentracao</span>
            <strong>{{ formatPct(summary?.concentration) }}</strong>
            <small>{{ concentrationRead }}</small>
          </div>
        </div>
      </section>

      <section class="far-kpis">
        <div class="far-kpi-card">
          <span>Runs ao vivo</span>
          <strong>{{ summary?.active_runs || 0 }}</strong>
          <small>{{ summary?.cooling_runs || 0 }} desacelerando</small>
        </div>
        <div class="far-kpi-card">
          <span>Runs historicos</span>
          <strong>{{ summary?.inactive_runs || 0 }}</strong>
          <small>mantem o historico na lista</small>
        </div>
        <div class="far-kpi-card">
          <span>Bias dominante</span>
          <strong :class="valueTone(summary?.projected_net_close)">{{ dominantSideLabel }}</strong>
          <small>{{ summary?.buy_runs || 0 }} buys / {{ summary?.sell_runs || 0 }} sells</small>
        </div>
        <div class="far-kpi-card">
          <span>{{ summary?.has_live_projection ? 'Projecao viva' : 'Historico vivo' }}</span>
          <strong :class="valueTone(summary?.has_live_projection ? summary?.active_projection_remaining : summary?.current_net_contracts)">
            {{ formatContracts(summary?.has_live_projection ? summary?.active_projection_remaining : summary?.current_net_contracts) }}
          </strong>
          <small>{{ summary?.has_live_projection ? 'contratos restantes no run-rate atual' : 'saldo das trilhas selecionadas' }}</small>
        </div>
        <div class="far-kpi-card">
          <span>VWAP fluxo</span>
          <strong>{{ formatLevel(payload?.source?.vwap) }}</strong>
          <small>RLP {{ formatLevel(payload?.source?.rlp_vwap) }}</small>
        </div>
        <div class="far-kpi-card">
          <span>Participantes</span>
          <strong>{{ payload?.source?.agent_count ?? 0 }}</strong>
          <small>snapshot mais recente</small>
        </div>
      </section>

      <div class="far-main-grid">
        <aside class="far-list-panel">
          <div class="far-panel-head">
            <div>
              <div class="far-panel-title">Catalogo de montagens</div>
              <div class="far-panel-sub">detecta e separa runs ativos, desacelerando e historicos</div>
            </div>
            <div class="far-tabs">
              <button
                v-for="tab in filterTabs"
                :key="tab.key"
                type="button"
                class="far-tab"
                :class="{ active: statusFilter === tab.key }"
                @click="statusFilter = tab.key"
              >
                {{ tab.label }} {{ tab.count }}
              </button>
            </div>
          </div>
          <div class="far-run-list">
            <button
              v-for="run in filteredRuns"
              :key="run.run_id"
              type="button"
              class="far-run-card"
              :class="[run.status, { selected: selectedRunId === run.run_id }]"
              @click="selectRun(run)"
            >
              <div class="far-run-head">
                <span class="far-run-name">{{ run.display_name }}</span>
                <span class="far-run-status">{{ run.status_label }}</span>
              </div>
              <div class="far-run-sub">
                <span>{{ run.run_scope_label }}</span>
                <span>{{ run.style?.label }}</span>
              </div>
              <div class="far-run-metrics">
                <span :class="valueTone(run.delta_contracts)">{{ run.side === 'buy' ? 'Compra' : 'Venda' }} {{ formatContracts(run.delta_contracts) }}</span>
                <span>{{ formatRate(run.contracts_per_minute) }}/min</span>
                <span>{{ hasLiveProjection(run) ? `proj ${formatContracts(run.projected_total_contracts)}` : 'historico' }}</span>
              </div>
              <div class="far-run-foot">
                <span>hold {{ formatScore(run.holding_score ?? run.robot_score) }}</span>
                <span>pulse {{ formatPulse(run.aggression_pulse) }}</span>
                <span v-if="run.history_runs_count">hist {{ run.history_runs_count }}</span>
                <span>{{ run.start_label }} -> {{ run.last_active_label }}</span>
              </div>
              <svg class="far-sparkline" viewBox="0 0 240 42" preserveAspectRatio="none" aria-hidden="true">
                <path :d="sparklinePath(run.chart)" class="far-sparkline-path" :class="run.side" />
              </svg>
            </button>
            <div v-if="!filteredRuns.length" class="far-list-empty">
              Nenhuma assinatura nesse filtro ainda.
            </div>
          </div>
        </aside>

        <section class="far-detail-panel">
          <template v-if="selectedRun">
            <div class="far-detail-head">
              <div>
                <div class="far-detail-title">{{ selectedRun.display_name }}</div>
                <div class="far-detail-sub">
                  <span class="far-detail-pill" :class="selectedRun.side">{{ selectedRun.side === 'buy' ? 'Montagem compradora' : 'Montagem vendedora' }}</span>
                  <span class="far-detail-pill neutral">{{ selectedRun.status_label }}</span>
                  <span class="far-detail-pill neutral">{{ selectedRun.run_scope_label }}</span>
                  <span class="far-detail-pill neutral">{{ selectedRun.style?.label }}</span>
                  <span v-if="selectedRun.history_runs_count" class="far-detail-pill neutral">historico {{ selectedRun.history_runs_count }}</span>
                </div>
              </div>
              <div class="far-detail-range">
                {{ selectedRun.start_label }} -> {{ selectedRun.last_active_label }}
              </div>
            </div>

            <div class="far-detail-kpis">
              <div class="far-detail-card">
                <span>Contratos</span>
                <strong :class="valueTone(selectedRun.delta_contracts)">{{ formatContracts(selectedRun.delta_contracts) }}</strong>
                <small>acumulado do run</small>
              </div>
              <div class="far-detail-card">
                <span>Ritmo</span>
                <strong :class="valueTone(selectedRun.contracts_per_minute)">{{ formatRate(selectedRun.contracts_per_minute) }}/min</strong>
                <small>{{ formatRate(selectedRun.contracts_per_hour) }}/h</small>
              </div>
              <div class="far-detail-card">
                <span>Projecao</span>
                <strong :class="valueTone(selectedRun.projected_total_contracts)">{{ hasLiveProjection(selectedRun) ? formatContracts(selectedRun.projected_total_contracts) : 'sem projecao' }}</strong>
                <small>{{ hasLiveProjection(selectedRun) ? `faltam ${formatContracts(selectedRun.projected_remaining_contracts)}` : 'run encerrado, apenas historico' }}</small>
              </div>
              <div class="far-detail-card">
                <span>Holding score</span>
                <strong>{{ formatScore(selectedRun.holding_score ?? selectedRun.robot_score) }}</strong>
                <small>confianca {{ formatScore(selectedRun.confidence) }}</small>
              </div>
              <div class="far-detail-card">
                <span>Agressao pulse</span>
                <strong>{{ formatPulse(selectedRun.aggression_pulse) }}</strong>
                <small>{{ selectedRun.momentum?.label }}</small>
              </div>
              <div class="far-detail-card">
                <span>Persistencia</span>
                <strong>{{ formatPct(selectedRun.directional_persistence / 100) }}</strong>
                <small>gap {{ selectedRun.inactive_gap_minutes }}min</small>
              </div>
            </div>

            <div class="far-chart-panel">
              <div class="far-chart-head">
                <span>{{ hasLiveProjection(selectedRun) ? 'Curva de montagem e projecao' : 'Curva de montagem historica' }}</span>
                <strong>{{ selectedRun.style?.description }}</strong>
              </div>
              <svg
                v-if="curveChart"
                class="far-detail-chart"
                viewBox="0 0 760 262"
                preserveAspectRatio="none"
                aria-hidden="true"
              >
                <line
                  v-for="tick in curveChart.yTicks"
                  :key="`curve-y-${tick.value}`"
                  x1="54"
                  x2="742"
                  :y1="tick.y"
                  :y2="tick.y"
                  class="far-grid"
                />
                <line
                  v-for="tick in curveChart.xTicks"
                  :key="`curve-x-${tick.label}`"
                  :x1="tick.x"
                  :x2="tick.x"
                  y1="18"
                  y2="228"
                  class="far-grid far-grid-vertical"
                />
                <line x1="54" x2="742" :y1="curveChart.zeroY" :y2="curveChart.zeroY" class="far-zero-line" />
                <path :d="curveChart.actualPath" class="far-curve-path" :class="selectedRun.side" />
                <path v-if="curveChart.projectionPath" :d="curveChart.projectionPath" class="far-projection-path" :class="selectedRun.side" />
                <circle v-if="curveChart.lastPoint" :cx="curveChart.lastPoint.x" :cy="curveChart.lastPoint.y" r="3.4" class="far-last-dot" :class="selectedRun.side" />
                <text
                  v-for="tick in curveChart.yTicks"
                  :key="`curve-y-label-${tick.value}`"
                  x="46"
                  :y="tick.y + 3"
                  class="far-axis-label"
                  text-anchor="end"
                >{{ formatAxisNumber(tick.value) }}</text>
                <text
                  v-for="tick in curveChart.xTicks"
                  :key="`curve-x-label-${tick.label}`"
                  :x="tick.x"
                  y="248"
                  class="far-axis-label"
                  text-anchor="middle"
                >{{ tick.label }}</text>
              </svg>
            </div>

            <div class="far-chart-panel compact">
              <div class="far-chart-head">
                <span>Pace minuto a minuto</span>
                <strong>barra = delta qty | linha = agressao</strong>
              </div>
              <svg
                v-if="paceChart"
                class="far-pace-chart"
                viewBox="0 0 760 176"
                preserveAspectRatio="none"
                aria-hidden="true"
              >
                <line
                  v-for="tick in paceChart.yTicks"
                  :key="`pace-y-${tick.value}`"
                  x1="54"
                  x2="742"
                  :y1="tick.y"
                  :y2="tick.y"
                  class="far-grid"
                />
                <line x1="54" x2="742" :y1="paceChart.zeroY" :y2="paceChart.zeroY" class="far-zero-line" />
                <rect
                  v-for="bar in paceChart.bars"
                  :key="`bar-${bar.index}`"
                  :x="bar.x"
                  :y="bar.y"
                  :width="bar.width"
                  :height="bar.height"
                  class="far-bar"
                  :class="bar.tone"
                />
                <path :d="paceChart.aggressionPath" class="far-aggr-line" :class="selectedRun.side" />
                <text
                  v-for="tick in paceChart.yTicks"
                  :key="`pace-y-label-${tick.value}`"
                  x="46"
                  :y="tick.y + 3"
                  class="far-axis-label"
                  text-anchor="end"
                >{{ formatAxisNumber(tick.value) }}</text>
                <text
                  v-for="tick in paceChart.xTicks"
                  :key="`pace-x-label-${tick.label}`"
                  :x="tick.x"
                  y="164"
                  class="far-axis-label"
                  text-anchor="middle"
                >{{ tick.label }}</text>
              </svg>
            </div>

            <div v-if="selectedRun.history_runs?.length" class="far-history-panel">
              <div class="far-chart-head">
                <span>Historico da trilha</span>
                <strong>mesma corretora e mesma direcao, sem projecao ativa</strong>
              </div>
              <div class="far-history-list">
                <div
                  v-for="historyRun in selectedRun.history_runs"
                  :key="historyRun.run_id"
                  class="far-history-row"
                >
                  <span class="far-history-time">{{ historyRun.start_label }} -> {{ historyRun.last_active_label }}</span>
                  <span :class="valueTone(historyRun.delta_contracts)">{{ formatContracts(historyRun.delta_contracts) }}</span>
                  <span>{{ historyRun.active_minutes }}min</span>
                  <span>hold {{ formatScore(historyRun.holding_score) }}</span>
                </div>
              </div>
            </div>
          </template>
          <div v-else class="far-empty far-empty-inline">Selecione uma assinatura para abrir a curva de montagem.</div>
        </section>
      </div>

      <div class="far-footnote">
        O radar usa buckets de 1 minuto do microsservico de flow por participante, detecta runs por persistencia de `delta_qty`, separa agressao, maker e RLP e projeta o fim do pregao pela inclinacao atual da curva.
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { getFlowActivityRadar } from '@/api/macro.js'

const props = defineProps({
  refreshNonce: { type: Number, default: 0 },
})

const REQUEST_TIMEOUT_MS = 45_000
const AUTO_REFRESH_MS = 15_000
const TOP_RUNS = 24

const loading = ref(false)
const error = ref('')
const payload = ref(null)
const selectedRunId = ref('')
const statusFilter = ref('all')
let refreshTimer = null
let inFlight = null

const summary = computed(() => payload.value?.summary || null)
const reader = computed(() => payload.value?.reader || { headline: '', summary: '', bullets: [], tone: 'neutral' })
const runs = computed(() => payload.value?.detections || [])
const session = computed(() => payload.value?.session || {})
const sessionDateLabel = computed(() => {
  const raw = String(session.value?.date || '').trim()
  if (!raw) return ''
  const [year, month, day] = raw.split('-')
  return year && month && day ? `${day}/${month}` : raw
})
const readerToneClass = computed(() => {
  if (reader.value?.tone === 'buy') return 'buy'
  if (reader.value?.tone === 'sell') return 'sell'
  return 'mixed'
})
const dominantSideLabel = computed(() => {
  if (summary.value?.dominant_side === 'buy') return 'comprador'
  if (summary.value?.dominant_side === 'sell') return 'vendedor'
  return 'misto'
})
const concentrationRead = computed(() => {
  const concentration = Number(summary.value?.concentration || 0)
  if (concentration >= 0.72) return 'bem concentrado'
  if (concentration >= 0.52) return 'concentrado'
  return 'distribuido'
})
const filterTabs = computed(() => {
  const all = runs.value.length
  const live = runs.value.filter(item => item.status === 'active' || item.status === 'cooling').length
  const history = runs.value.filter(item => item.status === 'inactive' || Number(item.history_runs_count || 0) > 0).length
  return [
    { key: 'live', label: 'Ao vivo', count: live },
    { key: 'all', label: 'Todos', count: all },
    { key: 'history', label: 'Historico', count: history },
  ]
})
const filteredRuns = computed(() => {
  if (statusFilter.value === 'history') {
    return runs.value.filter(item => item.status === 'inactive' || Number(item.history_runs_count || 0) > 0)
  }
  if (statusFilter.value === 'live') return runs.value.filter(item => item.status === 'active' || item.status === 'cooling')
  return runs.value
})
const selectedRun = computed(() => filteredRuns.value.find(item => item.run_id === selectedRunId.value) || filteredRuns.value[0] || null)
const curveChart = computed(() => buildCurveChart(selectedRun.value, session.value))
const paceChart = computed(() => buildPaceChart(selectedRun.value))

watch(filteredRuns, nextRuns => {
  if (!nextRuns.length) {
    selectedRunId.value = ''
    return
  }
  if (!nextRuns.some(item => item.run_id === selectedRunId.value)) {
    selectedRunId.value = nextRuns[0].run_id
  }
})

watch(() => props.refreshNonce, () => {
  load({ force: false, silent: true })
})

function withTimeout(promise, ms) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Timeout ao carregar activity radar.')), ms)
    Promise.resolve(promise)
      .then(value => {
        clearTimeout(timer)
        resolve(value)
      })
      .catch(err => {
        clearTimeout(timer)
        reject(err)
      })
  })
}

async function load({ force = false, silent = false } = {}) {
  if (inFlight) return inFlight
  if (!silent) loading.value = true
  error.value = ''
  const request = withTimeout(
    getFlowActivityRadar({
      bucket_minutes: 1,
      top_runs: TOP_RUNS,
      force_refresh: force ? 1 : 0,
      _ts: force ? Date.now() : undefined,
    }),
    REQUEST_TIMEOUT_MS,
  )
    .then(response => {
      const nextPayload = response?.data?.data || response?.data || null
      payload.value = nextPayload
      if (!nextPayload?.ok) {
        error.value = nextPayload?.message || ''
      }
      const nextRuns = nextPayload?.detections || []
      if (nextRuns.length && !nextRuns.some(item => item.run_id === selectedRunId.value)) {
        selectedRunId.value = nextRuns[0].run_id
      }
      return nextPayload
    })
    .catch(err => {
      error.value = err?.response?.data?.error || err?.message || 'Falha ao carregar activity radar.'
      throw err
    })
    .finally(() => {
      if (!silent) loading.value = false
      inFlight = null
    })
  inFlight = request
  return request
}

async function reload(forceRefresh = false) {
  try {
    await load({ force: forceRefresh, silent: false })
  } catch {
    // handled by state
  }
}

function selectRun(run) {
  selectedRunId.value = run?.run_id || ''
}

function hasLiveProjection(run) {
  return Boolean(run?.has_live_projection)
}

function scheduleRefresh() {
  clearInterval(refreshTimer)
  refreshTimer = setInterval(() => {
    load({ force: false, silent: true }).catch(() => {})
  }, AUTO_REFRESH_MS)
}

function valueTone(value) {
  const numeric = safeNumber(value)
  if (numeric == null) return ''
  if (numeric > 0) return 'pos'
  if (numeric < 0) return 'neg'
  return ''
}

function formatContracts(value) {
  const numeric = safeNumber(value)
  if (numeric == null) return '--'
  const sign = numeric > 0 ? '+' : ''
  return `${sign}${Math.round(numeric).toLocaleString('pt-BR')}`
}

function formatRate(value) {
  const numeric = safeNumber(value)
  if (numeric == null) return '--'
  const sign = numeric > 0 ? '+' : ''
  return `${sign}${numeric.toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}`
}

function formatScore(value) {
  const numeric = safeNumber(value)
  if (numeric == null) return '--'
  return Math.round(numeric).toLocaleString('pt-BR')
}

function formatPct(value) {
  const numeric = safeNumber(value)
  if (numeric == null) return '--'
  return `${(numeric * 100).toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}%`
}

function formatPulse(value) {
  const numeric = safeNumber(value)
  if (numeric == null) return '--'
  return `${numeric.toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}x`
}

function formatLevel(value) {
  const numeric = safeNumber(value)
  if (numeric == null) return '--'
  return numeric.toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 1 })
}

function formatAxisNumber(value) {
  const numeric = safeNumber(value)
  if (numeric == null) return '--'
  if (Math.abs(numeric) >= 1000) return `${Math.round(numeric / 1000)}k`
  return Math.round(numeric).toString()
}

function formatTime(value) {
  const parsed = parseTime(value)
  if (parsed == null) return '--'
  return new Intl.DateTimeFormat('pt-BR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    timeZone: 'America/Sao_Paulo',
  }).format(parsed)
}

function sparklinePath(points) {
  const chartPoints = Array.isArray(points) ? points : []
  if (!chartPoints.length) return ''
  const values = chartPoints.map(point => safeNumber(point?.cumulative_qty) ?? 0)
  const min = Math.min(0, ...values)
  const max = Math.max(0, ...values)
  const range = max - min || 1
  return chartPoints
    .map((point, index) => {
      const x = (index / Math.max(chartPoints.length - 1, 1)) * 240
      const y = 36 - (((values[index] - min) / range) * 30)
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(' ')
}

function buildCurveChart(run, currentSession) {
  if (!run || !Array.isArray(run.chart) || !run.chart.length) return null
  const chart = run.chart
  const pad = { top: 18, right: 18, bottom: 34, left: 54 }
  const width = 760
  const innerWidth = width - pad.left - pad.right
  const innerHeight = 210
  const startIndex = Number(chart[0]?.minute_index ?? 0)
  const closeIndex = Math.max(startIndex + 1, Number(currentSession?.total_buckets ?? chart.length) - 1)
  const actualEndIndex = Number(chart[chart.length - 1]?.minute_index ?? startIndex)
  const projectedTotal = hasLiveProjection(run)
    ? (safeNumber(run.projected_total_contracts) ?? safeNumber(chart[chart.length - 1]?.cumulative_qty) ?? 0)
    : (safeNumber(chart[chart.length - 1]?.cumulative_qty) ?? 0)
  const values = [0, projectedTotal, ...chart.map(point => safeNumber(point?.cumulative_qty) ?? 0)]
  const minValue = Math.min(...values)
  const maxValue = Math.max(...values)
  const domainPadding = Math.max((maxValue - minValue) * 0.12, 120)
  const domainMin = minValue - domainPadding
  const domainMax = maxValue + domainPadding
  const span = Math.max(closeIndex - startIndex, 1)
  const xForIndex = minuteIndex => pad.left + (((minuteIndex - startIndex) / span) * innerWidth)
  const yForValue = value => pad.top + ((domainMax - value) / Math.max(domainMax - domainMin, 1)) * innerHeight
  const actualPath = chart
    .map((point, index) => `${index === 0 ? 'M' : 'L'}${xForIndex(Number(point.minute_index)).toFixed(2)},${yForValue(safeNumber(point.cumulative_qty) ?? 0).toFixed(2)}`)
    .join(' ')
  const projectionPath = hasLiveProjection(run) && closeIndex > actualEndIndex
    ? [
        `M${xForIndex(actualEndIndex).toFixed(2)},${yForValue(safeNumber(chart[chart.length - 1]?.cumulative_qty) ?? 0).toFixed(2)}`,
        `L${xForIndex(closeIndex).toFixed(2)},${yForValue(projectedTotal).toFixed(2)}`,
      ].join(' ')
    : ''
  const lastValue = safeNumber(chart[chart.length - 1]?.cumulative_qty) ?? 0
  const yTicks = buildLinearTicks(domainMin, domainMax, 5).map(value => ({ value, y: yForValue(value) }))
  const xTickIndices = uniqueTickIndices([
    startIndex,
    Math.round((startIndex + actualEndIndex) / 2),
    actualEndIndex,
    closeIndex,
  ])
  const xTicks = xTickIndices.map(index => ({ x: xForIndex(index), label: minuteLabelFromIndex(currentSession, index) }))
  return {
    actualPath,
    projectionPath,
    lastPoint: { x: xForIndex(actualEndIndex), y: yForValue(lastValue) },
    zeroY: yForValue(0),
    yTicks,
    xTicks,
  }
}

function buildPaceChart(run) {
  if (!run || !Array.isArray(run.chart) || !run.chart.length) return null
  const chart = run.chart
  const pad = { top: 14, right: 18, bottom: 26, left: 54 }
  const width = 760
  const innerWidth = width - pad.left - pad.right
  const innerHeight = 120
  const deltas = chart.map(point => safeNumber(point.delta_qty) ?? 0)
  const aggressions = chart.map(point => safeNumber(point.delta_agression_balance) ?? 0)
  const domainAbs = Math.max(
    1,
    ...deltas.map(value => Math.abs(value)),
    ...aggressions.map(value => Math.abs(value)),
  )
  const yForValue = value => pad.top + (((domainAbs - value) / (domainAbs * 2)) * innerHeight)
  const zeroY = yForValue(0)
  const slot = innerWidth / Math.max(chart.length, 1)
  const bars = chart.map((point, index) => {
    const value = safeNumber(point.delta_qty) ?? 0
    const x = pad.left + (index * slot) + (slot * 0.12)
    const y = value >= 0 ? yForValue(value) : zeroY
    const heightPx = Math.max(1.5, Math.abs(zeroY - yForValue(value)))
    return {
      index,
      x,
      y,
      width: Math.max(1.5, slot * 0.76),
      height: heightPx,
      tone: value >= 0 ? 'pos' : 'neg',
    }
  })
  const aggressionPath = chart
    .map((point, index) => {
      const x = pad.left + (index * slot) + (slot / 2)
      const y = yForValue(safeNumber(point.delta_agression_balance) ?? 0)
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(' ')
  const yTicks = buildLinearTicks(-domainAbs, domainAbs, 5).map(value => ({ value, y: yForValue(value) }))
  const xTickIndices = uniqueTickIndices([
    0,
    Math.round((chart.length - 1) * 0.33),
    Math.round((chart.length - 1) * 0.66),
    chart.length - 1,
  ])
  const xTicks = xTickIndices.map(index => ({
    x: pad.left + (index * slot) + (slot / 2),
    label: chart[index]?.label || '',
  }))
  return {
    bars,
    aggressionPath,
    yTicks,
    xTicks,
    zeroY,
  }
}

function buildLinearTicks(min, max, count = 5) {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return []
  if (min === max) return [min]
  const step = (max - min) / Math.max(count - 1, 1)
  return Array.from({ length: count }, (_, index) => min + (step * index))
}

function uniqueTickIndices(indices) {
  return Array.from(new Set(indices.map(value => Math.max(0, Math.round(value))))).sort((left, right) => left - right)
}

function minuteLabelFromIndex(currentSession, index) {
  const startAt = parseTime(currentSession?.start_at)
  if (startAt == null) return ''
  const bucketMinutes = Number(currentSession?.bucket_minutes || 1)
  const instant = new Date(startAt.getTime() + (index * bucketMinutes * 60 * 1000))
  return new Intl.DateTimeFormat('pt-BR', {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'America/Sao_Paulo',
  }).format(instant)
}

function parseTime(value) {
  if (!value) return null
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

function safeNumber(value) {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

onMounted(() => {
  load({ force: false, silent: false }).catch(() => {})
  scheduleRefresh()
})

onUnmounted(() => {
  clearInterval(refreshTimer)
})
</script>

<style scoped>
.far-root {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  color: #dbe6f3;
}

.far-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.far-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 38px;
  height: 24px;
  border-radius: 7px;
  background: linear-gradient(135deg, rgba(14,165,233,0.20), rgba(59,130,246,0.28));
  border: 1px solid rgba(56,189,248,0.26);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.08em;
}

.far-pill,
.far-meta,
.far-loading,
.far-error {
  font-size: 11px;
  color: #8ca1bb;
}

.far-pill {
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(15,23,42,0.72);
  border: 1px solid rgba(148,163,184,0.14);
}

.far-spacer { flex: 1; }

.far-btn {
  border: 1px solid rgba(59,130,246,0.24);
  background: rgba(37,99,235,0.16);
  color: #dbeafe;
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
}

.far-btn:disabled {
  cursor: wait;
  opacity: 0.65;
}

.far-empty {
  flex: 1;
  min-height: 180px;
  display: grid;
  place-items: center;
  border-radius: 14px;
  border: 1px dashed rgba(148,163,184,0.18);
  background: rgba(2,6,23,0.36);
  color: #8ca1bb;
  text-align: center;
  padding: 24px;
}

.far-empty-inline {
  min-height: 320px;
}

.far-reader {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(240px, 0.8fr);
  gap: 12px;
  padding: 14px;
  border-radius: 16px;
  border: 1px solid rgba(148,163,184,0.12);
  background:
    radial-gradient(circle at top left, rgba(59,130,246,0.16), transparent 42%),
    linear-gradient(180deg, rgba(15,23,42,0.92), rgba(9,13,24,0.96));
}

.far-reader.buy {
  box-shadow: inset 0 0 0 1px rgba(16,185,129,0.08);
}

.far-reader.sell {
  box-shadow: inset 0 0 0 1px rgba(248,113,113,0.08);
}

.far-reader-copy {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.far-reader-kicker {
  font-size: 10px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #7dd3fc;
}

.far-reader-title {
  font-size: 22px;
  font-weight: 800;
  line-height: 1.1;
}

.far-reader-text {
  margin: 0;
  color: #a9b8cb;
  font-size: 12px;
  line-height: 1.55;
}

.far-reader-bullets {
  margin: 0;
  padding-left: 18px;
  color: #dbe6f3;
  display: grid;
  gap: 5px;
  font-size: 11px;
  line-height: 1.45;
}

.far-reader-side {
  display: grid;
  gap: 10px;
}

.far-side-card,
.far-kpi-card,
.far-detail-card,
.far-list-panel,
.far-detail-panel,
.far-chart-panel {
  border-radius: 14px;
  border: 1px solid rgba(148,163,184,0.12);
  background: rgba(7,11,20,0.88);
}

.far-side-card {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.far-side-label,
.far-kpi-card span,
.far-detail-card span {
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #7b8ca3;
}

.far-side-card strong,
.far-kpi-card strong,
.far-detail-card strong {
  font-size: 20px;
  line-height: 1;
}

.far-side-card small,
.far-kpi-card small,
.far-detail-card small {
  color: #8ca1bb;
  font-size: 11px;
}

.far-kpis {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
}

.far-kpi-card,
.far-detail-card {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.far-main-grid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(300px, 0.92fr) minmax(0, 1.6fr);
  gap: 10px;
}

.far-list-panel,
.far-detail-panel {
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.far-panel-head,
.far-detail-head,
.far-chart-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.far-panel-head {
  padding: 12px 12px 10px;
  border-bottom: 1px solid rgba(148,163,184,0.08);
}

.far-panel-title {
  font-size: 14px;
  font-weight: 700;
}

.far-panel-sub,
.far-detail-range,
.far-chart-head strong {
  color: #8ca1bb;
  font-size: 11px;
  font-weight: 500;
}

.far-tabs {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.far-tab {
  border: 1px solid rgba(148,163,184,0.14);
  background: rgba(15,23,42,0.72);
  color: #8ca1bb;
  border-radius: 999px;
  padding: 5px 10px;
  font-size: 11px;
  cursor: pointer;
}

.far-tab.active {
  color: #eff6ff;
  background: rgba(30,64,175,0.34);
  border-color: rgba(96,165,250,0.24);
}

.far-run-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 10px 12px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.far-run-card {
  width: 100%;
  text-align: left;
  padding: 10px;
  border-radius: 12px;
  border: 1px solid rgba(148,163,184,0.12);
  background: rgba(15,23,42,0.82);
  display: flex;
  flex-direction: column;
  gap: 6px;
  cursor: pointer;
}

.far-run-card.selected {
  border-color: rgba(59,130,246,0.38);
  box-shadow: inset 0 0 0 1px rgba(59,130,246,0.18);
}

.far-run-card.active {
  background: linear-gradient(180deg, rgba(11,18,32,0.96), rgba(12,20,34,0.90));
}

.far-run-card.cooling {
  background: linear-gradient(180deg, rgba(22,16,10,0.94), rgba(15,23,42,0.86));
}

.far-run-card.inactive {
  opacity: 0.78;
}

.far-run-head,
.far-run-sub,
.far-run-metrics,
.far-run-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.far-run-name {
  font-size: 12px;
  font-weight: 700;
}

.far-run-status,
.far-run-sub,
.far-run-foot {
  font-size: 10px;
  color: #8ca1bb;
}

.far-run-metrics {
  font-size: 11px;
  color: #dbe6f3;
}

.far-sparkline {
  width: 100%;
  height: 42px;
}

.far-sparkline-path,
.far-curve-path,
.far-projection-path,
.far-last-dot,
.far-aggr-line {
  fill: none;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.far-sparkline-path.buy,
.far-curve-path.buy,
.far-aggr-line.buy {
  stroke: #34d399;
}

.far-sparkline-path.sell,
.far-curve-path.sell,
.far-aggr-line.sell {
  stroke: #f87171;
}

.far-sparkline-path {
  stroke-width: 2.3;
}

.far-projection-path {
  stroke-width: 2;
  stroke-dasharray: 8 6;
  opacity: 0.82;
}

.far-projection-path.buy {
  stroke: rgba(52,211,153,0.9);
}

.far-projection-path.sell {
  stroke: rgba(248,113,113,0.9);
}

.far-detail-panel {
  padding: 12px;
  gap: 10px;
}

.far-detail-head {
  align-items: flex-start;
}

.far-detail-title {
  font-size: 20px;
  font-weight: 800;
  line-height: 1.1;
}

.far-detail-sub {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.far-detail-pill {
  padding: 4px 9px;
  border-radius: 999px;
  font-size: 10px;
  border: 1px solid rgba(148,163,184,0.12);
}

.far-detail-pill.buy {
  color: #bbf7d0;
  background: rgba(22,163,74,0.14);
}

.far-detail-pill.sell {
  color: #fecaca;
  background: rgba(220,38,38,0.14);
}

.far-detail-pill.neutral {
  color: #cbd5e1;
  background: rgba(71,85,105,0.18);
}

.far-detail-kpis {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
}

.far-chart-panel {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.far-history-panel {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.far-chart-panel.compact {
  margin-top: auto;
}

.far-detail-chart,
.far-pace-chart {
  width: 100%;
  height: 252px;
}

.far-pace-chart {
  height: 166px;
}

.far-grid {
  stroke: rgba(148,163,184,0.12);
  stroke-width: 1;
}

.far-grid-vertical {
  stroke-dasharray: 4 6;
}

.far-zero-line {
  stroke: rgba(226,232,240,0.28);
  stroke-width: 1.2;
}

.far-curve-path {
  stroke-width: 2.6;
}

.far-last-dot {
  stroke-width: 0;
}

.far-last-dot.buy {
  fill: #34d399;
}

.far-last-dot.sell {
  fill: #f87171;
}

.far-axis-label {
  fill: #7b8ca3;
  font-size: 10px;
}

.far-bar.pos {
  fill: rgba(52,211,153,0.68);
}

.far-bar.neg {
  fill: rgba(248,113,113,0.68);
}

.far-aggr-line {
  stroke-width: 1.8;
  opacity: 0.88;
}

.far-list-empty {
  padding: 18px 10px;
  color: #8ca1bb;
  text-align: center;
  border: 1px dashed rgba(148,163,184,0.14);
  border-radius: 12px;
}

.far-history-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.far-history-row {
  display: grid;
  grid-template-columns: minmax(120px, 1.2fr) 1fr 70px 70px;
  gap: 10px;
  align-items: center;
  padding: 9px 10px;
  border-radius: 10px;
  border: 1px solid rgba(148,163,184,0.10);
  background: rgba(15,23,42,0.56);
  font-size: 11px;
  color: #dbe6f3;
}

.far-history-time {
  color: #8ca1bb;
  font-size: 10px;
}

.far-footnote {
  font-size: 10px;
  color: #7b8ca3;
  line-height: 1.5;
}

.pos { color: #34d399; }
.neg { color: #f87171; }

@media (max-width: 1280px) {
  .far-reader,
  .far-main-grid {
    grid-template-columns: 1fr;
  }

  .far-kpis,
  .far-detail-kpis {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 860px) {
  .far-kpis,
  .far-detail-kpis {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .far-history-row {
    grid-template-columns: 1fr 1fr;
  }
}
</style>

<template>
  <div class="rsdw-root">
    <div class="rsdw-toolbar">
      <div class="rsdw-tabs" role="tablist">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          type="button"
          class="rsdw-tab"
          :class="{ active: activeTab === tab.key }"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
        </button>
      </div>
      <div class="rsdw-spacer"></div>
      <span class="rsdw-state" :class="{ ok: panel?.ok, error: hasErrors }">
        {{ statusLabel }}
      </span>
      <button type="button" class="rsdw-btn" :disabled="loading || collecting" @click="refresh(true)">
        {{ loading || collecting ? '...' : 'Atualizar' }}
      </button>
    </div>

    <div v-if="loading && !panel" class="rsdw-empty">Carregando fontes...</div>
    <div v-else-if="error && !panel" class="rsdw-empty error">{{ error }}</div>

    <template v-else-if="panel">
      <div class="rsdw-kpis">
        <div class="rsdw-kpi">
          <span>Series OK</span>
          <strong>{{ coverage.series_ok ?? 0 }}/{{ coverage.series_total ?? 0 }}</strong>
        </div>
        <div class="rsdw-kpi">
          <span>Janela</span>
          <strong>{{ panel.lookback_days || 30 }}d</strong>
        </div>
        <div class="rsdw-kpi">
          <span>Coleta</span>
          <strong>{{ collectorRunning ? 'diaria' : 'manual' }}</strong>
        </div>
        <div class="rsdw-kpi wide">
          <span>Ultima base</span>
          <strong>{{ fmtDateTime(panel.generated_at) }}</strong>
        </div>
      </div>

      <div class="rsdw-body">
        <section class="rsdw-series">
          <article
            v-for="item in filteredSeries"
            :key="item.id"
            class="rsdw-card"
            :class="toneClass(item)"
          >
            <div class="rsdw-card-head">
              <div>
                <div class="rsdw-card-title">{{ item.label }}</div>
                <div class="rsdw-card-sub">{{ item.provider }}</div>
              </div>
              <span class="rsdw-pill" :class="{ error: item.status !== 'ok' }">
                {{ item.status === 'ok' ? item.confidenceLabel : 'erro' }}
              </span>
            </div>

            <div class="rsdw-card-values">
              <div>
                <span>Ultimo</span>
                <strong>{{ fmtValue(item) }}</strong>
              </div>
              <div>
                <span>{{ item.unit === 'yield_pct' ? '1d bp' : '1d %' }}</span>
                <strong :class="moveClass(item.summary?.change_1d_pct ?? item.summary?.change_1d)">
                  {{ fmtMove(item, '1d') }}
                </strong>
              </div>
              <div>
                <span>{{ item.unit === 'yield_pct' ? '30d bp' : '30d %' }}</span>
                <strong :class="moveClass(item.summary?.change_window_pct ?? item.summary?.change_window)">
                  {{ fmtMove(item, 'window') }}
                </strong>
              </div>
            </div>

            <svg class="rsdw-spark" viewBox="0 0 240 56" preserveAspectRatio="none" aria-hidden="true">
              <line x1="0" x2="240" y1="42" y2="42" class="rsdw-spark-base" />
              <path v-if="sparkPath(item)" :d="sparkPath(item)" class="rsdw-spark-line" />
              <circle
                v-if="sparkLast(item)"
                :cx="sparkLast(item).x"
                :cy="sparkLast(item).y"
                r="3"
                class="rsdw-spark-dot"
              />
            </svg>

            <div class="rsdw-card-foot">
              <span>{{ item.summary?.latest_date || '-' }}</span>
              <span>{{ coveragePct(item) }} cobertura</span>
              <span v-if="item.error" class="rsdw-error-mini">{{ shortError(item.error) }}</span>
            </div>
          </article>
        </section>

        <aside class="rsdw-sources">
          <div class="rsdw-side-head">
            <span>Fontes do relatorio</span>
            <strong>{{ sourceCounts.active }}/{{ sources.length }}</strong>
          </div>
          <div class="rsdw-source-list">
            <div v-for="source in filteredSources" :key="source.id" class="rsdw-source-row">
              <div>
                <strong>{{ source.label }}</strong>
                <span>{{ source.role }}</span>
              </div>
              <em :class="source.kind">{{ sourceKindLabel(source.kind) }}</em>
            </div>
          </div>
          <div class="rsdw-collector">
            <span>Proxima busca</span>
            <strong>{{ fmtDateTime(collector.next_run_at) }}</strong>
            <span v-if="collector.last_error" class="rsdw-error-mini">{{ shortError(collector.last_error) }}</span>
          </div>
        </aside>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { collectReportSourceDiscovery, getReportSourceDiscoveryPanel } from '@/api/macro'

const props = defineProps({
  refreshNonce: {
    type: Number,
    default: 0,
  },
})

const tabs = [
  { key: 'all', label: 'Todos' },
  { key: 'lev', label: 'LEV' },
  { key: 'hsbc', label: 'HSBC' },
  { key: 'sources', label: 'Fontes' },
]

const activeTab = ref('all')
const panel = ref(null)
const loading = ref(false)
const collecting = ref(false)
const error = ref('')
let timer = null

const coverage = computed(() => panel.value?.coverage || {})
const sources = computed(() => panel.value?.sources || [])
const collector = computed(() => panel.value?.collector || {})
const collectorRunning = computed(() => Boolean(collector.value?.running))
const hasErrors = computed(() => (coverage.value.series_error || 0) > 0)

const statusLabel = computed(() => {
  if (loading.value || collecting.value) return 'coletando'
  if (!panel.value) return 'sem base'
  if (panel.value.ok && hasErrors.value) return 'parcial'
  if (panel.value.ok) return 'online'
  return 'erro'
})

const normalizedSeries = computed(() => {
  return (panel.value?.series || []).map(item => ({
    ...item,
    confidenceLabel: confidenceLabel(item.confidence, item.source_kind),
  }))
})

const filteredSeries = computed(() => {
  const key = activeTab.value
  if (key === 'sources') return normalizedSeries.value
  if (key === 'lev') {
    return normalizedSeries.value.filter(item => String(item.block || '').toLowerCase().includes('lev'))
  }
  if (key === 'hsbc') {
    return normalizedSeries.value.filter(item => String(item.block || '').toLowerCase().includes('hsbc'))
  }
  return normalizedSeries.value
})

const filteredSources = computed(() => {
  if (activeTab.value === 'lev') {
    return sources.value.filter(source => ['cvm_inf_diario', 'cvm_fund_registry', 'anbima_ima', 'b3_ibov', 'fred_yields', 'yahoo_market'].includes(source.id))
  }
  if (activeTab.value === 'hsbc') {
    return sources.value.filter(source => ['fred_yields', 'yahoo_market', 'eia_brent', 'hsbc_private'].includes(source.id))
  }
  return sources.value
})

const sourceCounts = computed(() => {
  const active = sources.value.filter(source => ['active_time_series', 'validated_by_proxy'].includes(source.collection)).length
  return { active }
})

async function refresh(force = false) {
  if (force) {
    await collect()
    return
  }
  try {
    loading.value = true
    error.value = ''
    const res = await getReportSourceDiscoveryPanel({ lookback_days: 30 })
    panel.value = res?.data?.data ?? res?.data ?? null
  } catch (err) {
    error.value = friendlyError(err)
  } finally {
    loading.value = false
  }
}

async function collect() {
  try {
    collecting.value = true
    error.value = ''
    const res = await collectReportSourceDiscovery({ lookback_days: 30, force: true })
    panel.value = res?.data?.data ?? res?.data ?? null
  } catch (err) {
    error.value = friendlyError(err)
  } finally {
    collecting.value = false
  }
}

function sparkPath(item) {
  const points = sparkPoints(item)
  if (points.length < 2) return ''
  return points.map((point, idx) => `${idx ? 'L' : 'M'}${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ')
}

function sparkLast(item) {
  const points = sparkPoints(item)
  return points.length ? points[points.length - 1] : null
}

function sparkPoints(item) {
  const rows = item?.summary?.sparkline || []
  const values = rows.map(row => Number(row.value)).filter(value => Number.isFinite(value))
  if (values.length < 2) return []
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = Math.max(max - min, Math.abs(max) * 0.001, 0.000001)
  return values.map((value, idx) => ({
    x: values.length === 1 ? 120 : (idx / (values.length - 1)) * 238 + 1,
    y: 50 - ((value - min) / span) * 42,
  }))
}

function fmtValue(item) {
  const value = item?.summary?.latest_value
  if (value == null) return '-'
  if (item.unit === 'yield_pct') return `${Number(value).toFixed(2)}%`
  if (Math.abs(value) >= 1000) return Number(value).toLocaleString('en-US', { maximumFractionDigits: 0 })
  if (Math.abs(value) >= 100) return Number(value).toFixed(2)
  return Number(value).toFixed(4)
}

function fmtMove(item, mode) {
  const summary = item?.summary || {}
  if (item.unit === 'yield_pct') {
    const value = mode === '1d' ? summary.change_1d : summary.change_window
    return signed(value, 1)
  }
  const value = mode === '1d' ? summary.change_1d_pct : summary.change_window_pct
  return `${signed(value, 2)}%`
}

function signed(value, digits = 2) {
  if (value == null || value === '') return '-'
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return '-'
  return `${parsed > 0 ? '+' : ''}${parsed.toFixed(digits)}`
}

function moveClass(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || Math.abs(parsed) < 0.0001) return 'flat'
  return parsed > 0 ? 'up' : 'down'
}

function toneClass(item) {
  if (item.status !== 'ok') return 'error'
  const change = item.unit === 'yield_pct' ? item.summary?.change_window : item.summary?.change_window_pct
  const parsed = Number(change)
  if (!Number.isFinite(parsed) || Math.abs(parsed) < 0.05) return 'flat'
  return parsed > 0 ? 'up' : 'down'
}

function coveragePct(item) {
  const ratio = Number(item?.summary?.coverage_ratio)
  if (!Number.isFinite(ratio)) return '0%'
  return `${Math.round(ratio * 100)}%`
}

function fmtDateTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function confidenceLabel(confidence, kind) {
  if (confidence === 'official_public' || kind === 'official_public') return 'oficial'
  if (confidence === 'proxy_public' || kind === 'public_proxy') return 'proxy'
  return 'fonte'
}

function sourceKindLabel(kind) {
  if (kind === 'official_public') return 'oficial'
  if (kind === 'public_proxy') return 'proxy'
  if (kind === 'official_or_authenticated') return 'api/xls'
  if (kind === 'official_or_licensed') return 'licenca'
  if (kind === 'proprietary') return 'privado'
  return 'fonte'
}

function shortError(value) {
  const text = String(value || '').replace(/\s+/g, ' ').trim()
  return text.length > 72 ? `${text.slice(0, 69)}...` : text
}

function friendlyError(err) {
  return err?.response?.data?.error || err?.message || 'Falha ao carregar fontes.'
}

watch(() => props.refreshNonce, () => refresh(true))

onMounted(() => {
  refresh(false)
  timer = setInterval(() => refresh(false), 5 * 60_000)
})

onUnmounted(() => {
  clearInterval(timer)
})
</script>

<style scoped>
.rsdw-root {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #080e17;
  color: #dbeafe;
  overflow: hidden;
  font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

.rsdw-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
  background: #0a1220;
  flex-shrink: 0;
}

.rsdw-tabs {
  display: flex;
  gap: 4px;
}

.rsdw-tab,
.rsdw-btn {
  height: 24px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 5px;
  background: rgba(15, 23, 42, 0.72);
  color: #94a3b8;
  font-size: 10px;
  font-weight: 700;
  cursor: pointer;
}

.rsdw-tab {
  padding: 0 9px;
}

.rsdw-tab.active {
  color: #e0f2fe;
  border-color: rgba(20, 184, 166, 0.45);
  background: rgba(20, 184, 166, 0.12);
}

.rsdw-btn {
  min-width: 72px;
  color: #bae6fd;
}

.rsdw-btn:disabled {
  opacity: 0.6;
  cursor: wait;
}

.rsdw-spacer {
  flex: 1;
}

.rsdw-state {
  height: 22px;
  display: inline-flex;
  align-items: center;
  padding: 0 8px;
  border-radius: 5px;
  background: rgba(245, 158, 11, 0.12);
  color: #fbbf24;
  font-size: 10px;
  font-weight: 800;
  text-transform: uppercase;
}

.rsdw-state.ok {
  color: #5eead4;
  background: rgba(20, 184, 166, 0.12);
}

.rsdw-state.error {
  color: #fca5a5;
  background: rgba(239, 68, 68, 0.12);
}

.rsdw-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  text-align: center;
  color: #64748b;
  font-size: 12px;
}

.rsdw-empty.error {
  color: #fca5a5;
}

.rsdw-kpis {
  display: grid;
  grid-template-columns: repeat(3, minmax(80px, 1fr)) minmax(130px, 1.5fr);
  gap: 8px;
  padding: 10px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.1);
  flex-shrink: 0;
}

.rsdw-kpi {
  min-height: 54px;
  padding: 8px 9px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  border-radius: 6px;
  background: rgba(15, 23, 42, 0.58);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.rsdw-kpi span {
  color: #64748b;
  font-size: 9px;
  font-weight: 800;
  text-transform: uppercase;
}

.rsdw-kpi strong {
  color: #f8fafc;
  font-size: 15px;
  line-height: 1.1;
}

.rsdw-body {
  min-height: 0;
  flex: 1;
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(210px, 0.8fr);
  gap: 10px;
  padding: 10px;
}

.rsdw-series,
.rsdw-source-list {
  min-height: 0;
  overflow: auto;
}

.rsdw-series {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
  gap: 8px;
  align-content: start;
  padding-right: 2px;
}

.rsdw-card {
  min-height: 172px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  border-radius: 6px;
  background: linear-gradient(180deg, rgba(15, 23, 42, 0.82), rgba(8, 13, 22, 0.92));
  padding: 9px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rsdw-card.up {
  border-color: rgba(34, 197, 94, 0.26);
}

.rsdw-card.down {
  border-color: rgba(248, 113, 113, 0.24);
}

.rsdw-card.error {
  border-color: rgba(239, 68, 68, 0.32);
}

.rsdw-card-head,
.rsdw-card-foot,
.rsdw-side-head,
.rsdw-source-row,
.rsdw-collector {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.rsdw-card-title {
  color: #f8fafc;
  font-size: 13px;
  font-weight: 800;
}

.rsdw-card-sub {
  color: #64748b;
  font-size: 10px;
  margin-top: 2px;
}

.rsdw-pill {
  flex-shrink: 0;
  padding: 3px 6px;
  border-radius: 5px;
  background: rgba(14, 165, 233, 0.12);
  color: #7dd3fc;
  font-size: 9px;
  font-weight: 800;
  text-transform: uppercase;
}

.rsdw-pill.error {
  background: rgba(239, 68, 68, 0.13);
  color: #fca5a5;
}

.rsdw-card-values {
  display: grid;
  grid-template-columns: 1.2fr 1fr 1fr;
  gap: 6px;
}

.rsdw-card-values div {
  min-width: 0;
}

.rsdw-card-values span {
  display: block;
  color: #64748b;
  font-size: 9px;
  font-weight: 800;
  text-transform: uppercase;
}

.rsdw-card-values strong {
  display: block;
  color: #e2e8f0;
  font-size: 12px;
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rsdw-card-values strong.up {
  color: #86efac;
}

.rsdw-card-values strong.down {
  color: #fca5a5;
}

.rsdw-card-values strong.flat {
  color: #cbd5e1;
}

.rsdw-spark {
  width: 100%;
  height: 56px;
  border-radius: 4px;
  background: rgba(2, 6, 23, 0.55);
}

.rsdw-spark-base {
  stroke: rgba(148, 163, 184, 0.12);
  stroke-width: 1;
}

.rsdw-spark-line {
  fill: none;
  stroke: #2dd4bf;
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
}

.rsdw-spark-dot {
  fill: #facc15;
  stroke: rgba(2, 6, 23, 0.9);
  stroke-width: 1.5;
}

.rsdw-card-foot {
  color: #64748b;
  font-size: 9px;
  margin-top: auto;
}

.rsdw-sources {
  min-height: 0;
  border: 1px solid rgba(148, 163, 184, 0.12);
  border-radius: 6px;
  background: rgba(15, 23, 42, 0.48);
  display: flex;
  flex-direction: column;
}

.rsdw-side-head {
  padding: 9px 10px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.1);
}

.rsdw-side-head span {
  color: #94a3b8;
  font-size: 11px;
  font-weight: 800;
}

.rsdw-side-head strong {
  color: #f8fafc;
  font-size: 12px;
}

.rsdw-source-list {
  padding: 6px;
}

.rsdw-source-row {
  align-items: flex-start;
  padding: 8px 6px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.08);
}

.rsdw-source-row:last-child {
  border-bottom: 0;
}

.rsdw-source-row strong {
  display: block;
  color: #e2e8f0;
  font-size: 10px;
}

.rsdw-source-row span {
  display: block;
  color: #64748b;
  font-size: 9px;
  line-height: 1.35;
  margin-top: 2px;
}

.rsdw-source-row em {
  flex-shrink: 0;
  font-style: normal;
  color: #bae6fd;
  background: rgba(14, 165, 233, 0.11);
  border-radius: 4px;
  padding: 3px 5px;
  font-size: 8px;
  font-weight: 900;
  text-transform: uppercase;
}

.rsdw-source-row em.official_public {
  color: #86efac;
  background: rgba(34, 197, 94, 0.11);
}

.rsdw-source-row em.public_proxy {
  color: #7dd3fc;
}

.rsdw-source-row em.proprietary {
  color: #fca5a5;
  background: rgba(239, 68, 68, 0.11);
}

.rsdw-collector {
  align-items: flex-start;
  flex-direction: column;
  padding: 9px 10px;
  border-top: 1px solid rgba(148, 163, 184, 0.1);
}

.rsdw-collector span {
  color: #64748b;
  font-size: 9px;
  font-weight: 800;
  text-transform: uppercase;
}

.rsdw-collector strong {
  color: #e2e8f0;
  font-size: 11px;
}

.rsdw-error-mini {
  color: #fca5a5 !important;
}

@media (max-width: 720px) {
  .rsdw-kpis {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .rsdw-body {
    grid-template-columns: minmax(0, 1fr);
  }

  .rsdw-sources {
    min-height: 220px;
  }
}
</style>

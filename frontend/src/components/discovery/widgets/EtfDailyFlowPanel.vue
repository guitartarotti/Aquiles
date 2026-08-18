<template>
  <section class="edf-root">
    <header class="edf-hero">
      <div>
        <div class="edf-eyebrow">ETF Daily Flow</div>
        <h4>Fluxo diario inferido por emissor e universo</h4>
        <p>
          Snapshot agregado do microservico de captura dos emissores globais. O painel mistura cobertura,
          net flow, AUM e cortes por pais, desenvolvimento, segmento, tipo e faixa de tamanho.
        </p>
      </div>
      <div class="edf-hero-actions">
        <div class="edf-meta-pill" :class="{ bad: Boolean(error) }">
          <span>Status</span>
          <strong>{{ statusLabel }}</strong>
        </div>
        <button type="button" class="edf-refresh" :disabled="loading" @click="load(true)">
          {{ loading ? '...' : 'Atualizar' }}
        </button>
      </div>
    </header>

    <div v-if="loading && !payload" class="edf-state">Carregando ETF Daily Flow...</div>
    <div v-else-if="error && !payload" class="edf-state error">{{ error }}</div>

    <template v-else-if="payload">
      <section class="edf-cards">
        <article v-for="card in payload.cards || []" :key="card.key" class="edf-card">
          <span>{{ card.label }}</span>
          <strong :class="cardTone(card)">{{ formatCardValue(card) }}</strong>
          <em>{{ card.detail }}</em>
        </article>
      </section>

      <section class="edf-meta-grid">
        <div class="edf-meta-box">
          <span>Ultima captura</span>
          <strong>{{ fmtDateTime(payload.latest_capture_at) }}</strong>
        </div>
        <div class="edf-meta-box">
          <span>Ultima data de flow</span>
          <strong>{{ fmtDate(payload.latest_flow_date) }}</strong>
        </div>
        <div class="edf-meta-box">
          <span>Run</span>
          <strong>{{ payload.last_run?.status || 'n/d' }}</strong>
        </div>
        <div class="edf-meta-box">
          <span>Cobertura</span>
          <strong>{{ fmtCount(payload.summary?.flow_funds) }} / {{ fmtCount(payload.summary?.active_funds) }}</strong>
        </div>
      </section>

      <section class="edf-grid">
        <article class="edf-panel edf-panel-wide">
          <div class="edf-panel-head">
            <span>Heatmap emissor x segmento</span>
            <strong>net flow latest</strong>
          </div>
          <div class="edf-heatmap" :style="heatmapStyle">
            <div class="edf-heat-corner"></div>
            <div v-for="column in payload.heatmap?.x || []" :key="`hx-${column}`" class="edf-heat-x">{{ column }}</div>
            <template v-for="row in heatmapRows" :key="`hy-${row.label}`">
              <div class="edf-heat-y">{{ row.label }}</div>
              <div
                v-for="cell in row.cells"
                :key="`${row.label}-${cell.column}`"
                class="edf-heat-cell"
                :style="{ background: heatColor(cell.value) }"
                :title="`${row.label} | ${cell.column} | ${fmtUsd(cell.value)}`"
              >
                {{ shortMoney(cell.value) }}
              </div>
            </template>
          </div>
        </article>

        <article class="edf-panel">
          <div class="edf-panel-head">
            <span>Por emissor</span>
            <strong>{{ issuerRows.length }} linhas</strong>
          </div>
          <table class="edf-table">
            <thead>
              <tr>
                <th>Emissor</th>
                <th>Funds</th>
                <th>Flow</th>
                <th>Net</th>
                <th>AUM</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in issuerRows" :key="item.key">
                <td>{{ item.label }}</td>
                <td>{{ fmtCount(item.funds) }}</td>
                <td>{{ fmtCount(item.flow_funds) }}</td>
                <td :class="moveClass(item.net_flow_usd)">{{ fmtUsd(item.net_flow_usd) }}</td>
                <td>{{ fmtUsd(item.total_aum_usd) }}</td>
              </tr>
            </tbody>
          </table>
        </article>

        <article class="edf-panel">
          <div class="edf-panel-head">
            <span>Paises / ETFs de pais</span>
            <strong>{{ countryRows.length }} focos</strong>
          </div>
          <table class="edf-table">
            <thead>
              <tr>
                <th>Foco</th>
                <th>Funds</th>
                <th>Net</th>
                <th>AUM</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in countryRows" :key="item.key">
                <td>{{ item.label }}</td>
                <td>{{ fmtCount(item.funds) }}</td>
                <td :class="moveClass(item.net_flow_usd)">{{ fmtUsd(item.net_flow_usd) }}</td>
                <td>{{ fmtUsd(item.total_aum_usd) }}</td>
              </tr>
            </tbody>
          </table>
        </article>

        <article class="edf-panel">
          <div class="edf-panel-head">
            <span>Emergentes x desenvolvidos</span>
            <strong>{{ developmentRows.length }} buckets</strong>
          </div>
          <table class="edf-table">
            <thead>
              <tr>
                <th>Bucket</th>
                <th>Funds</th>
                <th>Net</th>
                <th>Nav-only</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in developmentRows" :key="item.key">
                <td>{{ item.label }}</td>
                <td>{{ fmtCount(item.funds) }}</td>
                <td :class="moveClass(item.net_flow_usd)">{{ fmtUsd(item.net_flow_usd) }}</td>
                <td>{{ fmtCount(item.nav_only_funds) }}</td>
              </tr>
            </tbody>
          </table>
        </article>

        <article class="edf-panel">
          <div class="edf-panel-head">
            <span>Por segmento</span>
            <strong>{{ segmentRows.length }} buckets</strong>
          </div>
          <table class="edf-table">
            <thead>
              <tr>
                <th>Segmento</th>
                <th>Funds</th>
                <th>Net</th>
                <th>AUM</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in segmentRows" :key="item.key">
                <td>{{ item.label }}</td>
                <td>{{ fmtCount(item.funds) }}</td>
                <td :class="moveClass(item.net_flow_usd)">{{ fmtUsd(item.net_flow_usd) }}</td>
                <td>{{ fmtUsd(item.total_aum_usd) }}</td>
              </tr>
            </tbody>
          </table>
        </article>

        <article class="edf-panel">
          <div class="edf-panel-head">
            <span>Por tipo</span>
            <strong>{{ typeRows.length }} buckets</strong>
          </div>
          <table class="edf-table">
            <thead>
              <tr>
                <th>Tipo</th>
                <th>Funds</th>
                <th>Net</th>
                <th>AUM</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in typeRows" :key="item.key">
                <td>{{ item.label }}</td>
                <td>{{ fmtCount(item.funds) }}</td>
                <td :class="moveClass(item.net_flow_usd)">{{ fmtUsd(item.net_flow_usd) }}</td>
                <td>{{ fmtUsd(item.total_aum_usd) }}</td>
              </tr>
            </tbody>
          </table>
        </article>

        <article class="edf-panel">
          <div class="edf-panel-head">
            <span>Por tamanho de AUM</span>
            <strong>{{ aumBucketRows.length }} faixas</strong>
          </div>
          <table class="edf-table">
            <thead>
              <tr>
                <th>Faixa</th>
                <th>Funds</th>
                <th>Net</th>
                <th>Flow funds</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in aumBucketRows" :key="item.key">
                <td>{{ item.label }}</td>
                <td>{{ fmtCount(item.funds) }}</td>
                <td :class="moveClass(item.net_flow_usd)">{{ fmtUsd(item.net_flow_usd) }}</td>
                <td>{{ fmtCount(item.flow_funds) }}</td>
              </tr>
            </tbody>
          </table>
        </article>

        <article class="edf-panel edf-panel-wide">
          <div class="edf-panel-head">
            <span>Top 20 inflows</span>
            <strong>{{ inflowRows.length }} ETFs</strong>
          </div>
          <table class="edf-table edf-table-wide">
            <thead>
              <tr>
                <th>Ticker</th>
                <th>ETF</th>
                <th>Emissor</th>
                <th>Pais</th>
                <th>Segmento</th>
                <th>Tipo</th>
                <th>Flow</th>
                <th>AUM</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in inflowRows" :key="`in-${item.provider}-${item.ticker}`">
                <td>{{ item.ticker }}</td>
                <td>{{ item.name }}</td>
                <td>{{ item.issuer }}</td>
                <td>{{ item.country_focus }}</td>
                <td>{{ item.segment }}</td>
                <td>{{ item.type_label }}</td>
                <td class="up">{{ fmtUsd(item.flow_usd) }}</td>
                <td>{{ fmtUsd(item.aum_usd) }}</td>
              </tr>
            </tbody>
          </table>
        </article>

        <article class="edf-panel edf-panel-wide">
          <div class="edf-panel-head">
            <span>Top 20 outflows</span>
            <strong>{{ outflowRows.length }} ETFs</strong>
          </div>
          <table class="edf-table edf-table-wide">
            <thead>
              <tr>
                <th>Ticker</th>
                <th>ETF</th>
                <th>Emissor</th>
                <th>Pais</th>
                <th>Segmento</th>
                <th>Tipo</th>
                <th>Flow</th>
                <th>AUM</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in outflowRows" :key="`out-${item.provider}-${item.ticker}`">
                <td>{{ item.ticker }}</td>
                <td>{{ item.name }}</td>
                <td>{{ item.issuer }}</td>
                <td>{{ item.country_focus }}</td>
                <td>{{ item.segment }}</td>
                <td>{{ item.type_label }}</td>
                <td class="down">{{ fmtUsd(item.flow_usd) }}</td>
                <td>{{ fmtUsd(item.aum_usd) }}</td>
              </tr>
            </tbody>
          </table>
        </article>
      </section>
    </template>
  </section>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { getEtfDailyFlowDashboard } from '@/api/etfDailyFlow'

const props = defineProps({
  active: {
    type: Boolean,
    default: false,
  },
  refreshNonce: {
    type: Number,
    default: 0,
  },
})

const payload = ref(null)
const loading = ref(false)
const error = ref('')

const issuerRows = computed(() => payload.value?.tables?.by_issuer || [])
const countryRows = computed(() => payload.value?.tables?.by_country || [])
const developmentRows = computed(() => payload.value?.tables?.by_development || [])
const segmentRows = computed(() => payload.value?.tables?.by_segment || [])
const typeRows = computed(() => payload.value?.tables?.by_type || [])
const aumBucketRows = computed(() => payload.value?.tables?.by_aum_bucket || [])
const inflowRows = computed(() => payload.value?.top_inflows || [])
const outflowRows = computed(() => payload.value?.top_outflows || [])

const statusLabel = computed(() => {
  if (loading.value && !payload.value) return 'carregando'
  if (error.value) return 'erro'
  if (!payload.value) return 'vazio'
  return `${fmtCount(payload.value.summary?.flow_funds)} flows`
})

const heatmapRows = computed(() => {
  const columns = payload.value?.heatmap?.x || []
  const labels = payload.value?.heatmap?.y || []
  const matrix = payload.value?.heatmap?.z || []
  return labels.map((label, rowIndex) => ({
    label,
    cells: columns.map((column, columnIndex) => ({
      column,
      value: matrix?.[rowIndex]?.[columnIndex] ?? 0,
    })),
  }))
})

const heatmapStyle = computed(() => ({
  gridTemplateColumns: `136px repeat(${Math.max((payload.value?.heatmap?.x || []).length, 1)}, minmax(72px, 1fr))`,
}))

async function load(force = false) {
  if (loading.value) return
  try {
    loading.value = true
    error.value = ''
    payload.value = await getEtfDailyFlowDashboard({
      top_n: 20,
      _ts: force ? Date.now() : undefined,
    })
  } catch (err) {
    error.value = err?.response?.data?.error || err?.message || 'Falha ao carregar ETF Daily Flow.'
  } finally {
    loading.value = false
  }
}

function cardTone(card) {
  if (!card) return ''
  if (card.key === 'outflow') return 'down'
  if (card.key === 'inflow') return 'up'
  if (card.key === 'net') return moveClass(card.value)
  return ''
}

function formatCardValue(card) {
  if (!card) return '-'
  if (['active', 'flow_ready', 'computed'].includes(card.key)) return fmtCount(card.value)
  return fmtUsd(card.value)
}

function moveClass(value) {
  const number = Number(value || 0)
  if (number > 0) return 'up'
  if (number < 0) return 'down'
  return 'flat'
}

function fmtCount(value) {
  const number = Number(value || 0)
  return Number.isFinite(number)
    ? new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 }).format(number)
    : '-'
}

function fmtUsd(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '-'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    notation: 'compact',
    maximumFractionDigits: 2,
  }).format(number)
}

function shortMoney(value) {
  const number = Number(value)
  if (!Number.isFinite(number) || Math.abs(number) < 1000000) return ''
  const compact = new Intl.NumberFormat('en-US', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(number)
  return compact.replace('B', 'b').replace('M', 'm')
}

function fmtDate(value) {
  if (!value) return 'n/d'
  const date = new Date(`${value}T00:00:00`)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('pt-BR').format(date)
}

function fmtDateTime(value) {
  if (!value) return 'n/d'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('pt-BR', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(date)
}

function heatColor(value) {
  const number = Number(value || 0)
  const scale = Math.min(Math.abs(number) / 500000000, 1)
  if (number > 0) return `rgba(34, 197, 94, ${0.18 + scale * 0.72})`
  if (number < 0) return `rgba(248, 113, 113, ${0.18 + scale * 0.72})`
  return 'rgba(100, 116, 139, 0.16)'
}

watch(() => props.active, active => {
  if (active && !payload.value && !loading.value) {
    load(false)
  }
})

watch(() => props.refreshNonce, () => {
  if (props.active) {
    load(true)
  }
})

onMounted(() => {
  if (props.active) {
    load(false)
  }
})
</script>

<style scoped>
.edf-root {
  display: grid;
  gap: 14px;
}

.edf-hero,
.edf-panel,
.edf-card,
.edf-meta-box {
  border: 1px solid rgba(148, 163, 184, 0.16);
  background:
    linear-gradient(180deg, rgba(15, 23, 42, 0.98), rgba(10, 16, 28, 0.98)),
    linear-gradient(135deg, rgba(56, 189, 248, 0.08), rgba(16, 185, 129, 0.05));
  border-radius: 8px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.02);
}

.edf-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 16px;
  padding: 16px 18px;
}

.edf-eyebrow {
  color: #7dd3fc;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.edf-hero h4 {
  margin: 6px 0 8px;
  color: #f8fafc;
  font-size: 18px;
  font-weight: 800;
}

.edf-hero p {
  margin: 0;
  max-width: 780px;
  color: #94a3b8;
  font-size: 12px;
  line-height: 1.5;
}

.edf-hero-actions {
  display: grid;
  align-content: start;
  gap: 10px;
}

.edf-meta-pill,
.edf-refresh {
  border-radius: 7px;
  border: 1px solid rgba(125, 211, 252, 0.18);
  background: rgba(15, 23, 42, 0.84);
}

.edf-meta-pill {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  min-width: 152px;
}

.edf-meta-pill span {
  color: #64748b;
  font-size: 10px;
  font-weight: 800;
  text-transform: uppercase;
}

.edf-meta-pill strong {
  color: #dbeafe;
  font-size: 13px;
}

.edf-meta-pill.bad strong {
  color: #fecaca;
}

.edf-refresh {
  color: #e2e8f0;
  font-size: 11px;
  font-weight: 800;
  padding: 10px 12px;
  cursor: pointer;
}

.edf-refresh:disabled {
  opacity: 0.6;
  cursor: wait;
}

.edf-state {
  padding: 18px;
  border-radius: 8px;
  color: #cbd5e1;
  background: rgba(15, 23, 42, 0.82);
  border: 1px dashed rgba(148, 163, 184, 0.24);
}

.edf-state.error {
  color: #fecaca;
  border-color: rgba(248, 113, 113, 0.28);
}

.edf-cards,
.edf-meta-grid {
  display: grid;
  gap: 10px;
}

.edf-cards {
  grid-template-columns: repeat(7, minmax(0, 1fr));
}

.edf-meta-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.edf-card,
.edf-meta-box {
  padding: 12px 14px;
}

.edf-card span,
.edf-meta-box span {
  display: block;
  color: #64748b;
  font-size: 10px;
  font-weight: 800;
  text-transform: uppercase;
}

.edf-card strong,
.edf-meta-box strong {
  display: block;
  margin-top: 7px;
  color: #f8fafc;
  font-size: 18px;
  font-weight: 800;
}

.edf-card em {
  display: block;
  margin-top: 6px;
  color: #94a3b8;
  font-size: 10px;
  font-style: normal;
}

.edf-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.edf-panel {
  padding: 12px 14px 14px;
  overflow: hidden;
}

.edf-panel-wide {
  grid-column: 1 / -1;
}

.edf-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.edf-panel-head span {
  color: #cbd5e1;
  font-size: 12px;
  font-weight: 800;
}

.edf-panel-head strong {
  color: #64748b;
  font-size: 10px;
  font-weight: 800;
  text-transform: uppercase;
}

.edf-table {
  width: 100%;
  border-collapse: collapse;
}

.edf-table th,
.edf-table td {
  padding: 8px 6px;
  border-top: 1px solid rgba(148, 163, 184, 0.09);
  text-align: left;
  font-size: 11px;
}

.edf-table th {
  color: #64748b;
  font-size: 10px;
  font-weight: 800;
  text-transform: uppercase;
}

.edf-table td {
  color: #e2e8f0;
}

.edf-table td.up,
.edf-card strong.up {
  color: #86efac;
}

.edf-table td.down,
.edf-card strong.down {
  color: #fda4af;
}

.edf-card strong.flat {
  color: #f8fafc;
}

.edf-table-wide td:nth-child(2) {
  max-width: 320px;
}

.edf-heatmap {
  display: grid;
  gap: 6px;
  align-items: stretch;
}

.edf-heat-corner,
.edf-heat-x,
.edf-heat-y,
.edf-heat-cell {
  min-height: 46px;
  border-radius: 6px;
}

.edf-heat-corner {
  background: transparent;
}

.edf-heat-x,
.edf-heat-y {
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: #94a3b8;
  font-size: 10px;
  font-weight: 800;
  padding: 4px 6px;
}

.edf-heat-y {
  justify-content: flex-start;
}

.edf-heat-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #f8fafc;
  font-size: 10px;
  font-weight: 800;
  padding: 4px;
}

@media (max-width: 1180px) {
  .edf-cards {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .edf-meta-grid,
  .edf-grid,
  .edf-hero {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 760px) {
  .edf-cards,
  .edf-meta-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .edf-table {
    display: block;
    overflow-x: auto;
    white-space: nowrap;
  }

  .edf-heatmap {
    overflow-x: auto;
  }
}
</style>

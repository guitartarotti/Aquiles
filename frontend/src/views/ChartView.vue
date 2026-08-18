<template>
  <div class="chart-shell">
    <header class="header">
      <div class="header-copy">
        <AquilesBrand variant="desk" subtitle="PLATAFORMA QUANT" clickable @click="goHome" />
        <div class="eyebrow">Macro Chart Desk</div>
        <h1>Chart</h1>
        <p>
          Histórico vivo dos ativos capturados na `W 32: Básica`, com leitura do preço em tempo real
          e Pearson rolante contra `XB1`.
        </p>
      </div>
      <div class="actions">
        <button class="ghost" @click="goHome">Home</button>
        <button class="ghost" @click="goOptions">Options</button>
        <button class="ghost" @click="goHeatmap">Heatmap</button>
        <button class="ghost" :class="{ active: autoRefresh }" @click="toggleAutoRefresh">
          {{ autoRefresh ? 'Auto refresh ativo' : 'Auto refresh pausado' }}
        </button>
        <button class="ghost compact-btn" :disabled="compacting" @click="runCompactCsv"
                title="Remove linhas sem símbolo dos CSVs de histórico (libera disco e acelera o carregamento)">
          {{ compacting ? '⟳ Compactando…' : '⚡ Compactar CSVs' }}
        </button>
        <button class="primary" :disabled="loading" @click="loadPanel()">
          {{ loading ? 'Atualizando...' : 'Atualizar agora' }}
        </button>
      </div>
    </header>

    <div v-if="compactResult" class="compact-result" :class="compactResult.ok ? 'compact-ok' : 'compact-err'">
      {{ compactResult.msg }}
      <button class="compact-dismiss" @click="compactResult = null">✕</button>
    </div>

    <section class="meta-strip">
      <div><strong>Status:</strong> {{ collectorStatus.running ? 'coletor online' : 'coletor parado' }}</div>
      <div><strong>Benchmark:</strong> {{ benchmarkSymbol }}</div>
      <div><strong>Ultima foto:</strong> {{ latestCaptureLabel }}</div>
      <div><strong>Ativos:</strong> {{ assets.length }}</div>
      <div><strong>Polling:</strong> {{ collectorStatus.poll_interval_seconds || '--' }}s</div>
      <div><strong>Max age:</strong> {{ collectorStatus.max_age_seconds || '--' }}s</div>
    </section>

    <section class="control-strip">
      <div class="control-block">
        <span class="control-label">Janela</span>
        <div class="chip-row">
          <button
            v-for="option in lookbackOptions"
            :key="option.value"
            class="chip"
            :class="{ active: lookbackMinutes === option.value }"
            @click="setLookback(option.value)"
          >
            {{ option.label }}
          </button>
        </div>
      </div>
      <div class="control-block">
        <span class="control-label">Pearson</span>
        <div class="chip-row">
          <button
            v-for="option in rollingOptions"
            :key="option.value"
            class="chip"
            :class="{ active: rollingWindowPoints === option.value }"
            @click="setRollingWindow(option.value)"
          >
            {{ option.label }}
          </button>
        </div>
      </div>
      <label class="search-block">
        <span class="control-label">Buscar ativo</span>
        <input v-model="searchQuery" type="text" placeholder="Ex.: IBOV, DXY, ODF27" />
      </label>
    </section>

    <div v-if="errorMessage" class="error-state">{{ errorMessage }}</div>

    <div class="content-grid">
      <aside class="asset-rail">
        <div class="asset-rail-head">
          <div>
            <div class="asset-rail-eyebrow">Universe</div>
            <strong>{{ filteredAssets.length }} ativos</strong>
          </div>
          <span>{{ lookbackLabel }}</span>
        </div>

        <button
          v-for="asset in filteredAssets"
          :key="asset.symbol"
          class="asset-card"
          :class="{
            active: asset.symbol === selectedSymbol,
            benchmark: asset.is_benchmark,
            pending: loading && asset.symbol === selectedSymbol
          }"
          @click="selectSymbol(asset.symbol)"
        >
          <div class="asset-card-top">
            <strong>{{ asset.symbol }}</strong>
            <span :class="toneClass(asset.latest_daily_change_pct)">
              {{ formatSignedPercent(asset.latest_daily_change_pct) }}
            </span>
          </div>
          <div class="asset-card-price">{{ formatSmartNumber(asset.latest_price) }}</div>
          <div class="asset-card-meta">
            <span>Pearson {{ formatSignedNumber(asset.latest_pearson_vs_xb1, 3) }}</span>
            <span>{{ asset.sample_count }} pts</span>
          </div>
          <div v-if="loading && asset.symbol === selectedSymbol" class="asset-card-loading">
            <span class="asset-card-dot" />
            <span>{{ loadingHeadline }}</span>
          </div>
        </button>
      </aside>

      <main class="main-column" :class="{ 'is-loading': loading }">
        <transition name="chart-loading-fade">
          <section v-if="loading" class="chart-loading-overlay">
            <div class="chart-loading-head">
              <div>
                <div class="panel-eyebrow">Carregando</div>
                <h3>{{ loadingHeadline }}</h3>
                <p>{{ loadingDescription }}</p>
              </div>
              <div class="chart-loading-target">
                <span>Ativo</span>
                <strong>{{ loadingTargetSymbol }}</strong>
              </div>
            </div>
            <div class="chart-loading-steps">
              <div
                v-for="(step, index) in loadingSteps"
                :key="`${loadingReason}-${index}`"
                class="chart-loading-step"
                :class="step.status"
              >
                <span class="chart-loading-step-icon">{{ stepIcon(step.status) }}</span>
                <div>
                  <strong>{{ step.label }}</strong>
                  <p>{{ step.description }}</p>
                </div>
              </div>
            </div>
          </section>
        </transition>

        <section class="summary-hero">
          <div class="summary-copy">
            <div class="summary-eyebrow">Selecionado</div>
            <h2>{{ selectedAsset?.symbol || '--' }}</h2>
            <p>
              {{ selectedAsset?.symbol === benchmarkSymbol
                ? 'Benchmark base da mesa. O painel de Pearson fica desabilitado quando o próprio XB1 está selecionado.'
                : 'Série histórica do ativo capturado pela OCR residente, com leitura de dependência intraday frente ao XB1.' }}
            </p>
          </div>
          <div class="summary-grid">
            <div class="summary-pill">
              <span>Ultimo preco</span>
              <strong>{{ formatSmartNumber(selectedAsset?.latest_price) }}</strong>
            </div>
            <div class="summary-pill">
              <span>Variacao 1d</span>
              <strong :class="toneClass(selectedAsset?.latest_daily_change_pct)">
                {{ formatSignedPercent(selectedAsset?.latest_daily_change_pct) }}
              </strong>
            </div>
            <div class="summary-pill">
              <span>Pearson vs {{ benchmarkSymbol }}</span>
              <strong :class="toneClass(selectedAsset?.latest_pearson_vs_xb1)">
                {{ formatSignedNumber(selectedAsset?.latest_pearson_vs_xb1, 3) }}
              </strong>
            </div>
            <div class="summary-pill">
              <span>Ultima leitura</span>
              <strong>{{ selectedAssetTimestampLabel }}</strong>
            </div>
            <div class="summary-pill">
              <span>Benchmark agora</span>
              <strong>{{ formatSmartNumber(benchmarkAsset?.latest_price) }}</strong>
            </div>
            <div class="summary-pill">
              <span>Amostras</span>
              <strong>{{ selectedAsset?.sample_count || 0 }}</strong>
            </div>
          </div>
        </section>

        <section class="panel">
          <div class="panel-head">
            <div>
              <div class="panel-eyebrow">Price history</div>
              <h3>{{ selectedAsset?.symbol || '--' }} intraday</h3>
            </div>
            <div class="panel-note">{{ pricePoints.length }} pontos exibidos</div>
          </div>
          <EquiLineChart
            :points="pricePoints"
            chart-mode="price"
            :height="360"
            line-color="#93c5fd"
            fill-top-color="rgba(147, 197, 253, 0.02)"
            fill-bottom-color="rgba(96, 165, 250, 0.18)"
            empty-message="Sem histórico suficiente para o ativo selecionado."
          />
        </section>

        <section class="panel">
          <div class="panel-head">
            <div>
              <div class="panel-eyebrow">Pearson history</div>
              <h3>{{ selectedAsset?.symbol || '--' }} vs {{ benchmarkSymbol }}</h3>
            </div>
            <div class="panel-note">
              Janela rolante de {{ rollingWindowPoints }} observações
            </div>
          </div>
          <div v-if="pearsonMessage" class="panel-empty-message">{{ pearsonMessage }}</div>
          <EquiLineChart
            v-else
            :points="pearsonPoints"
            chart-mode="pearson"
            :height="260"
            line-color="#fbbf24"
            fill-top-color="rgba(251, 191, 36, 0.02)"
            fill-bottom-color="rgba(245, 158, 11, 0.10)"
            empty-message="Sem janela suficiente para calcular Pearson nesse intervalo."
          />
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AquilesBrand from '../components/AquilesBrand.vue'
import EquiLineChart from '../components/EquiLineChart.vue'
import { getMarketScreenChartPanel, compactScreenCaptureCsv } from '../api/macro'

const router = useRouter()
const route = useRoute()

const lookbackOptions = [
  { label: '1h', value: 60 },
  { label: '4h', value: 240 },
  { label: '6h', value: 360 },
  { label: '1d', value: 1440 },
  { label: '3d', value: 4320 }
]

const rollingOptions = [
  { label: '24 pts', value: 24 },
  { label: '60 pts', value: 60 },
  { label: '120 pts', value: 120 },
  { label: '240 pts', value: 240 }
]

const loading = ref(false)
const autoRefresh = ref(true)
const errorMessage = ref('')
const compacting = ref(false)
const compactResult = ref(null)
const searchQuery = ref('')
const panel = ref(null)
const requestInFlight = ref(false)
const pendingLoadRequest = ref(null)
const loadingReason = ref('initial')
const loadingStageIndex = ref(0)
const selectedSymbol = ref(String(route.query.symbol || '').toUpperCase())
const lookbackMinutes = ref(Number(route.query.lookback_minutes || 360) || 360)
const rollingWindowPoints = ref(Number(route.query.rolling_window_points || 60) || 60)

let refreshTimer = null
let requestSequence = 0
let loadingStageTimer = null

const LOADING_STEP_PRESETS = {
  initial: [
    { label: 'Descobrindo o universo', description: 'Lendo a última foto do coletor e definindo o ativo inicial.' },
    { label: 'Buscando histórico bruto', description: 'Carregando os pontos capturados na janela solicitada.' },
    { label: 'Montando série intraday', description: 'Convertendo o histórico em pontos prontos para o chart.' },
    { label: 'Calculando Pearson', description: 'Atualizando a correlação rolante contra o XB1.' },
    { label: 'Publicando o painel', description: 'Sincronizando cards, lista lateral e gráficos.' }
  ],
  symbol: [
    { label: 'Confirmando seleção', description: 'Travando o novo ativo selecionado para evitar fallback visual.' },
    { label: 'Buscando histórico do ativo', description: 'Carregando a série intraday do símbolo pedido.' },
    { label: 'Montando candles e pontos', description: 'Preparando o gráfico principal com o recorte escolhido.' },
    { label: 'Calculando Pearson vs XB1', description: 'Atualizando a dependência intraday com a janela rolante atual.' },
    { label: 'Atualizando a tela', description: 'Sincronizando cards, lista lateral e gráficos com o ativo novo.' }
  ],
  lookback: [
    { label: 'Aplicando nova janela', description: 'Atualizando o recorte temporal solicitado.' },
    { label: 'Buscando histórico bruto', description: 'Recarregando os pontos dentro da nova janela.' },
    { label: 'Reamostrando a série', description: 'Montando o gráfico intraday com o novo período.' },
    { label: 'Recalculando Pearson', description: 'Ajustando a série de correlação para o recorte novo.' },
    { label: 'Atualizando a tela', description: 'Publicando cards e gráficos já com a nova janela.' }
  ],
  rolling: [
    { label: 'Aplicando nova janela Pearson', description: 'Atualizando o tamanho da correlação rolante.' },
    { label: 'Buscando base de preços', description: 'Reaproveitando a série capturada para o cálculo novo.' },
    { label: 'Recalculando correlação', description: 'Gerando a nova curva de Pearson contra o XB1.' },
    { label: 'Sincronizando leitura lateral', description: 'Atualizando Pearson dos ativos na lista e nos cards.' },
    { label: 'Publicando a tela', description: 'Atualizando os painéis com a nova configuração.' }
  ],
  refresh: [
    { label: 'Sincronizando parâmetros', description: 'Conferindo ativo, janela e benchmark atuais.' },
    { label: 'Buscando a foto mais recente', description: 'Atualizando o histórico vivo do coletor.' },
    { label: 'Montando a série intraday', description: 'Recriando o gráfico de preço com a nova captura.' },
    { label: 'Recalculando Pearson', description: 'Atualizando a leitura estatística contra o XB1.' },
    { label: 'Atualizando a tela', description: 'Publicando cards, lista lateral e gráficos.' }
  ]
}

const collectorStatus = computed(() => panel.value?.collector || {})
const benchmarkSymbol = computed(() => panel.value?.benchmark_symbol || 'XB1')
const benchmarkAvailable = computed(() => panel.value?.benchmark_available !== false)
const assets = computed(() => panel.value?.assets || [])
const selectedAsset = computed(() => panel.value?.selected_asset || null)
const benchmarkAsset = computed(() => panel.value?.benchmark_asset || null)
const pricePoints = computed(() => panel.value?.series?.price_points || [])
const pearsonPoints = computed(() => panel.value?.series?.pearson_points || [])

const filteredAssets = computed(() => {
  const query = searchQuery.value.trim().toUpperCase()
  if (!query) {
    return assets.value
  }
  return assets.value.filter((asset) => String(asset.symbol || '').includes(query))
})

const latestCaptureLabel = computed(() => formatDateTime(panel.value?.latest_capture_at))
const selectedAssetTimestampLabel = computed(() => formatDateTime(selectedAsset.value?.latest_timestamp))
const lookbackLabel = computed(() => {
  const hours = Math.round(lookbackMinutes.value / 60)
  if (lookbackMinutes.value >= 1440) {
    return `${Math.round(lookbackMinutes.value / 1440)}d`
  }
  return `${hours}h`
})
const loadingPreset = computed(() => LOADING_STEP_PRESETS[loadingReason.value] || LOADING_STEP_PRESETS.refresh)
const loadingTargetSymbol = computed(() => selectedSymbol.value || panel.value?.selected_symbol || '--')
const loadingHeadline = computed(() => {
  if (loadingReason.value === 'symbol') return `Trocando para ${loadingTargetSymbol.value}`
  if (loadingReason.value === 'lookback') return `Atualizando janela para ${lookbackLabel.value}`
  if (loadingReason.value === 'rolling') return `Recalculando Pearson de ${rollingWindowPoints.value} pontos`
  if (loadingReason.value === 'initial') return 'Montando o Chart Desk'
  return 'Atualizando o painel'
})
const loadingDescription = computed(() => {
  if (loadingReason.value === 'symbol') {
    return 'A seleção nova fica travada até a resposta correta chegar, sem deixar a resposta antiga sobrescrever a tela.'
  }
  if (loadingReason.value === 'lookback') {
    return 'O recorte temporal está sendo reaplicado no histórico bruto e nos gráficos derivados.'
  }
  if (loadingReason.value === 'rolling') {
    return 'A janela rolante está sendo recalculada sem perder o ativo atualmente selecionado.'
  }
  if (loadingReason.value === 'initial') {
    return 'A tela está carregando a última foto disponível, preparando o histórico e calculando as métricas base.'
  }
  return 'Estamos sincronizando a captura mais recente e recalculando os painéis do chart.'
})
const loadingSteps = computed(() => loadingPreset.value.map((step, index) => ({
  ...step,
  status: index < loadingStageIndex.value
    ? 'done'
    : index === loadingStageIndex.value
      ? 'active'
      : 'pending'
})))

const pearsonMessage = computed(() => {
  if (!selectedAsset.value) {
    return 'Selecione um ativo para carregar o histórico.'
  }
  if (!benchmarkAvailable.value) {
    return `O benchmark ${benchmarkSymbol.value} não apareceu na captura atual da W32 Básica. O histórico de preço segue disponível, mas o Pearson fica desabilitado até o benchmark voltar.`
  }
  if (selectedAsset.value.symbol === benchmarkSymbol.value) {
    return 'O benchmark XB1 não precisa de Pearson contra ele mesmo. Escolha outro ativo na coluna da esquerda.'
  }
  if (!pearsonPoints.value.length) {
    return 'Ainda não há janela suficiente para calcular Pearson nesse recorte.'
  }
  return ''
})

function goHome() {
  router.push({ name: 'Home' })
}

function goOptions() {
  router.push({ name: 'OptionsDashboard' })
}

function goHeatmap() {
  router.push({ name: 'MacroHeatmap' })
}

function syncRouteQuery() {
  router.replace({
    query: {
      ...route.query,
      symbol: selectedSymbol.value || undefined,
      lookback_minutes: String(lookbackMinutes.value),
      rolling_window_points: String(rollingWindowPoints.value)
    }
  })
}

function currentRequestState() {
  return JSON.stringify({
    symbol: selectedSymbol.value || '',
    lookback_minutes: lookbackMinutes.value,
    rolling_window_points: rollingWindowPoints.value
  })
}

function queueLoadRequest(requestOptions = {}) {
  const next = {
    silent: Boolean(requestOptions.silent),
    reason: requestOptions.reason || 'refresh'
  }
  const existing = pendingLoadRequest.value
  if (!existing) {
    pendingLoadRequest.value = next
    return
  }
  const reasonPriority = {
    refresh: 1,
    initial: 1,
    rolling: 2,
    lookback: 2,
    symbol: 3
  }
  if (!existing.silent && next.silent) {
    return
  }
  if (
    reasonPriority[existing.reason] > reasonPriority[next.reason]
    || (reasonPriority[existing.reason] === reasonPriority[next.reason] && !existing.silent && next.silent)
  ) {
    return
  }
  pendingLoadRequest.value = next
}

function startLoadingStages(reason = 'refresh') {
  loadingReason.value = reason
  loadingStageIndex.value = 0
  if (loadingStageTimer) {
    clearInterval(loadingStageTimer)
  }
  loadingStageTimer = setInterval(() => {
    const lastIndex = Math.max(loadingPreset.value.length - 1, 0)
    if (loadingStageIndex.value >= lastIndex) {
      clearInterval(loadingStageTimer)
      loadingStageTimer = null
      return
    }
    loadingStageIndex.value += 1
  }, 520)
}

function finishLoadingStages() {
  if (loadingStageTimer) {
    clearInterval(loadingStageTimer)
    loadingStageTimer = null
  }
  loadingStageIndex.value = Math.max(loadingPreset.value.length - 1, 0)
}

function stepIcon(status) {
  if (status === 'done') return '•'
  if (status === 'active') return '◌'
  return '·'
}

async function loadPanel({ silent = false, reason = 'refresh' } = {}) {
  if (requestInFlight.value) {
    queueLoadRequest({ silent, reason })
    return
  }
  const currentRequest = ++requestSequence
  const requestState = currentRequestState()
  requestInFlight.value = true
  if (!silent) {
    loading.value = true
    startLoadingStages(reason)
  }
  errorMessage.value = ''
  const useSlimPayload = reason === 'symbol' && Boolean(panel.value)

  try {
    const response = await getMarketScreenChartPanel({
      symbol: selectedSymbol.value || undefined,
      lookback_minutes: lookbackMinutes.value,
      rolling_window_points: rollingWindowPoints.value,
      max_points: 1200,
      include_assets: useSlimPayload ? 'false' : 'true',
      include_collector: useSlimPayload ? 'false' : 'true'
    })

    if (currentRequest !== requestSequence) {
      return
    }
    if (requestState !== currentRequestState()) {
      queueLoadRequest({ silent: false, reason })
      return
    }

    const nextPanel = response.data || {}
    panel.value = {
      ...(panel.value || {}),
      ...nextPanel,
      assets: Array.isArray(nextPanel.assets) ? nextPanel.assets : (panel.value?.assets || []),
      collector: nextPanel.collector || panel.value?.collector || {}
    }
    if (panel.value?.selected_symbol && panel.value.selected_symbol !== selectedSymbol.value) {
      selectedSymbol.value = panel.value.selected_symbol
    }
    syncRouteQuery()
    resetRefreshTimer()
  } catch (error) {
    if (currentRequest !== requestSequence) {
      return
    }
    errorMessage.value = error?.message || 'Falha ao carregar o painel de charts.'
  } finally {
    if (currentRequest === requestSequence) {
      requestInFlight.value = false
    }
    if (!silent && currentRequest === requestSequence) {
      finishLoadingStages()
      loading.value = false
    }
    if (currentRequest === requestSequence && pendingLoadRequest.value) {
      const nextRequest = pendingLoadRequest.value
      pendingLoadRequest.value = null
      void loadPanel(nextRequest)
    }
  }
}

function setLookback(value) {
  if (lookbackMinutes.value === value) {
    return
  }
  lookbackMinutes.value = value
  syncRouteQuery()
  void loadPanel({ reason: 'lookback' })
}

function setRollingWindow(value) {
  if (rollingWindowPoints.value === value) {
    return
  }
  rollingWindowPoints.value = value
  syncRouteQuery()
  void loadPanel({ reason: 'rolling' })
}

function selectSymbol(symbol) {
  if (!symbol || selectedSymbol.value === symbol) {
    return
  }
  selectedSymbol.value = symbol
  syncRouteQuery()
  void loadPanel({ reason: 'symbol' })
}

function formatDateTime(value) {
  if (!value) {
    return '--'
  }
  try {
    return new Intl.DateTimeFormat('pt-BR', {
      dateStyle: 'short',
      timeStyle: 'medium'
    }).format(new Date(value))
  } catch {
    return '--'
  }
}

function formatSmartNumber(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) {
    return '--'
  }
  let decimals = 2
  if (Math.abs(numeric) >= 1000) {
    decimals = 0
  } else if (Math.abs(numeric) < 10) {
    decimals = 4
  }
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  }).format(numeric)
}

function formatSignedPercent(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) {
    return '--'
  }
  return `${numeric >= 0 ? '+' : ''}${numeric.toFixed(2)}%`
}

function formatSignedNumber(value, decimals = 2) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) {
    return '--'
  }
  return `${numeric >= 0 ? '+' : ''}${numeric.toFixed(decimals)}`
}

function toneClass(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric) || numeric === 0) {
    return 'tone-flat'
  }
  return numeric > 0 ? 'tone-up' : 'tone-down'
}

function resetRefreshTimer() {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
  if (!autoRefresh.value) {
    return
  }
  const refreshIntervalMs = Math.max(
    Number(collectorStatus.value?.poll_interval_seconds || 5) * 1000,
    5000
  )
  refreshTimer = setInterval(() => {
    if (loading.value || requestInFlight.value) {
      return
    }
    void loadPanel({ silent: true })
  }, refreshIntervalMs)
}

function toggleAutoRefresh() {
  autoRefresh.value = !autoRefresh.value
  resetRefreshTimer()
}

async function runCompactCsv() {
  if (compacting.value) return
  compacting.value = true
  compactResult.value = null
  try {
    const res = await compactScreenCaptureCsv({ days: 7 })
    const files = res?.data?.files ?? []
    const saved = files.reduce((acc, f) => acc + ((f.original_mb || 0) - (f.compact_mb || 0)), 0)
    compactResult.value = {
      ok: true,
      msg: `${files.length} arquivo(s) compactado(s) — ${saved.toFixed(1)} MB liberados`,
      files
    }
    // Reload panel after compaction
    void loadPanel({ reason: 'refresh' })
  } catch (e) {
    compactResult.value = { ok: false, msg: e?.message || 'Falha ao compactar' }
  } finally {
    compacting.value = false
  }
}

onMounted(async () => {
  await loadPanel({ reason: 'initial' })
  resetRefreshTimer()
})

onBeforeUnmount(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
  }
  if (loadingStageTimer) {
    clearInterval(loadingStageTimer)
  }
})
</script>

<style scoped>
.chart-shell {
  min-height: 100vh;
  padding: 28px;
  background:
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.12), transparent 24%),
    linear-gradient(180deg, #09111a 0%, #04080f 100%);
  color: #edf3fb;
}

.header {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: flex-start;
  margin-bottom: 18px;
}

.header-copy {
  display: grid;
  gap: 8px;
  max-width: 760px;
}

.eyebrow,
.panel-eyebrow,
.summary-eyebrow,
.asset-rail-eyebrow,
.control-label {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #8aa2b7;
}

.header-copy h1 {
  margin: 0;
  font-size: 3.4rem;
  line-height: 0.94;
  letter-spacing: -0.05em;
}

.header-copy p {
  margin: 0;
  color: #aac0d4;
  line-height: 1.65;
  max-width: 680px;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: flex-end;
}

.ghost,
.primary,
.chip {
  appearance: none;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 999px;
  padding: 10px 14px;
  background: rgba(8, 15, 24, 0.72);
  color: #dce7f3;
  cursor: pointer;
  font-size: 0.84rem;
  transition: transform 0.18s ease, border-color 0.18s ease, background 0.18s ease;
}

.ghost:hover,
.primary:hover,
.chip:hover {
  transform: translateY(-1px);
  border-color: rgba(96, 165, 250, 0.38);
}

.ghost.active,
.chip.active {
  background: rgba(30, 64, 175, 0.34);
  border-color: rgba(96, 165, 250, 0.44);
}

.primary {
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
  border-color: rgba(96, 165, 250, 0.46);
  color: #f8fbff;
  font-weight: 700;
}

.meta-strip,
.control-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 16px;
  margin-bottom: 18px;
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(7, 12, 20, 0.78);
  border: 1px solid rgba(148, 163, 184, 0.10);
}

.meta-strip {
  font-size: 0.84rem;
  color: #b9cad8;
}

.control-strip {
  align-items: end;
}

.control-block,
.search-block {
  display: grid;
  gap: 8px;
}

.search-block {
  margin-left: auto;
  min-width: min(100%, 280px);
}

.search-block input {
  min-width: 260px;
  padding: 11px 14px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(4, 10, 18, 0.9);
  color: #e6eef7;
  outline: none;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.error-state,
.panel-empty-message {
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(248, 113, 113, 0.22);
  background: rgba(69, 18, 18, 0.36);
  color: #f5c7c7;
}

.error-state {
  margin-bottom: 18px;
}

.content-grid {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 18px;
}

.asset-rail,
.summary-hero,
.panel {
  border-radius: 22px;
  background:
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.08), transparent 24%),
    rgba(7, 12, 20, 0.82);
  border: 1px solid rgba(148, 163, 184, 0.10);
  box-shadow: 0 24px 60px rgba(2, 6, 23, 0.28);
}

.asset-rail {
  padding: 16px;
  display: grid;
  gap: 10px;
  align-content: start;
  max-height: calc(100vh - 190px);
  overflow: auto;
}

.asset-rail-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: end;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.08);
  color: #8aa2b7;
  font-size: 0.82rem;
}

.asset-card {
  width: 100%;
  appearance: none;
  display: grid;
  gap: 6px;
  padding: 13px 14px;
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, 0.08);
  background: rgba(10, 17, 28, 0.84);
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.asset-card:hover {
  border-color: rgba(96, 165, 250, 0.26);
}

.asset-card.active {
  border-color: rgba(147, 197, 253, 0.42);
  background: linear-gradient(180deg, rgba(30, 41, 59, 0.88), rgba(10, 17, 28, 0.92));
}

.asset-card.pending {
  position: relative;
  overflow: hidden;
}

.asset-card.pending::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, transparent 0%, rgba(147, 197, 253, 0.12) 50%, transparent 100%);
  animation: chart-card-sheen 1.2s linear infinite;
  pointer-events: none;
}

.asset-card.benchmark {
  box-shadow: inset 0 0 0 1px rgba(251, 191, 36, 0.12);
}

.asset-card-top,
.asset-card-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.asset-card-price {
  font-size: 1.05rem;
  font-weight: 700;
  color: #f8fbff;
}

.asset-card-meta {
  color: #8da4b8;
  font-size: 0.78rem;
}

.asset-card-loading {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.74rem;
  color: #9dc3ff;
}

.asset-card-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: #60a5fa;
  box-shadow: 0 0 0 0 rgba(96, 165, 250, 0.45);
  animation: chart-pulse 1.1s ease-in-out infinite;
}

.main-column {
  position: relative;
  display: grid;
  gap: 18px;
}

.main-column.is-loading > :not(.chart-loading-overlay) {
  filter: blur(1.6px);
  opacity: 0.64;
  transition: filter 0.18s ease, opacity 0.18s ease;
}

.chart-loading-overlay {
  position: absolute;
  inset: 0;
  z-index: 3;
  display: grid;
  align-content: start;
  gap: 14px;
  padding: 18px;
  border-radius: 22px;
  background: rgba(3, 9, 17, 0.74);
  border: 1px solid rgba(147, 197, 253, 0.16);
  backdrop-filter: blur(10px);
}

.chart-loading-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: start;
}

.chart-loading-head h3 {
  margin: 6px 0 8px;
  font-size: 1.42rem;
}

.chart-loading-head p {
  margin: 0;
  max-width: 620px;
  color: #b8cadb;
  line-height: 1.6;
}

.chart-loading-target {
  min-width: 130px;
  display: grid;
  gap: 6px;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(8, 16, 28, 0.88);
  border: 1px solid rgba(148, 163, 184, 0.14);
}

.chart-loading-target span {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: #8aa2b7;
}

.chart-loading-target strong {
  font-size: 1.14rem;
  color: #f8fbff;
}

.chart-loading-steps {
  display: grid;
  gap: 10px;
}

.chart-loading-step {
  display: grid;
  grid-template-columns: 26px minmax(0, 1fr);
  gap: 12px;
  align-items: start;
  padding: 12px 14px;
  border-radius: 16px;
  background: rgba(8, 16, 28, 0.76);
  border: 1px solid rgba(148, 163, 184, 0.12);
  transition: border-color 0.18s ease, background 0.18s ease, transform 0.18s ease;
}

.chart-loading-step strong {
  display: block;
  margin-bottom: 4px;
  color: #eef4fb;
}

.chart-loading-step p {
  margin: 0;
  color: #9fb4c8;
  font-size: 0.84rem;
  line-height: 1.45;
}

.chart-loading-step-icon {
  width: 26px;
  height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  font-size: 0.95rem;
  font-weight: 700;
  background: rgba(148, 163, 184, 0.16);
  color: #8aa2b7;
}

.chart-loading-step.done {
  border-color: rgba(74, 222, 128, 0.24);
}

.chart-loading-step.done .chart-loading-step-icon {
  background: rgba(34, 197, 94, 0.18);
  color: #86efac;
}

.chart-loading-step.active {
  border-color: rgba(96, 165, 250, 0.34);
  background: rgba(12, 21, 36, 0.88);
  transform: translateY(-1px);
}

.chart-loading-step.active .chart-loading-step-icon {
  background: rgba(59, 130, 246, 0.18);
  color: #bfdbfe;
  animation: chart-pulse 1.1s ease-in-out infinite;
}

.chart-loading-fade-enter-active,
.chart-loading-fade-leave-active {
  transition: opacity 0.18s ease;
}

.chart-loading-fade-enter-from,
.chart-loading-fade-leave-to {
  opacity: 0;
}

.summary-hero {
  display: grid;
  grid-template-columns: minmax(0, 0.92fr) minmax(0, 1.08fr);
  gap: 18px;
  padding: 20px;
}

.summary-copy h2 {
  margin: 8px 0 10px;
  font-size: 2.4rem;
  line-height: 0.94;
  letter-spacing: -0.05em;
}

.summary-copy p {
  margin: 0;
  color: #aec2d5;
  line-height: 1.65;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.summary-pill {
  display: grid;
  gap: 6px;
  padding: 12px 13px;
  border-radius: 14px;
  background: rgba(9, 18, 29, 0.72);
  border: 1px solid rgba(148, 163, 184, 0.08);
}

.summary-pill span {
  font-size: 0.76rem;
  text-transform: uppercase;
  letter-spacing: 0.10em;
  color: #8aa2b7;
}

.summary-pill strong {
  font-size: 1rem;
  color: #f8fbff;
}

.panel {
  padding: 18px;
  display: grid;
  gap: 14px;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: end;
}

.panel-head h3 {
  margin: 6px 0 0;
  font-size: 1.28rem;
}

.panel-note {
  color: #8aa2b7;
  font-size: 0.82rem;
}

.tone-up {
  color: #7dd3a4;
}

.tone-down {
  color: #fca5a5;
}

.tone-flat {
  color: #dce7f3;
}

@media (max-width: 1180px) {
  .content-grid,
  .summary-hero {
    grid-template-columns: 1fr;
  }

  .asset-rail {
    max-height: none;
  }

  .chart-loading-head {
    display: grid;
    grid-template-columns: 1fr;
  }
}

@media (max-width: 780px) {
  .chart-shell {
    padding: 18px;
  }

  .header,
  .panel-head {
    flex-direction: column;
    align-items: flex-start;
  }

  .header-copy h1 {
    font-size: 2.7rem;
  }

  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .search-block {
    margin-left: 0;
    width: 100%;
  }

  .search-block input {
    min-width: 0;
    width: 100%;
  }

  .chart-loading-overlay {
    padding: 14px;
  }
}

@media (max-width: 560px) {
  .summary-grid {
    grid-template-columns: 1fr;
  }
}

@keyframes chart-pulse {
  0%,
  100% {
    opacity: 0.72;
    transform: scale(1);
  }
  50% {
    opacity: 1;
    transform: scale(1.06);
  }
}

@keyframes chart-card-sheen {
  0% {
    transform: translateX(-120%);
  }
  100% {
    transform: translateX(120%);
  }
}

.compact-btn {
  color: #fbbf24;
  border-color: rgba(251, 191, 36, 0.28);
}
.compact-btn:hover:not(:disabled) {
  border-color: rgba(251, 191, 36, 0.5);
  background: rgba(251, 191, 36, 0.08);
}
.compact-btn:disabled {
  opacity: 0.55;
  cursor: wait;
}

.compact-result {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 16px;
  border-radius: 12px;
  margin-bottom: 12px;
  font-size: 0.86rem;
}
.compact-ok {
  background: rgba(16, 185, 129, 0.08);
  border: 1px solid rgba(16, 185, 129, 0.22);
  color: #6ee7b7;
}
.compact-err {
  background: rgba(248, 113, 113, 0.08);
  border: 1px solid rgba(248, 113, 113, 0.22);
  color: #fca5a5;
}
.compact-dismiss {
  appearance: none;
  border: none;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font-size: 0.88rem;
  opacity: 0.6;
  padding: 0 4px;
}
.compact-dismiss:hover { opacity: 1; }
</style>

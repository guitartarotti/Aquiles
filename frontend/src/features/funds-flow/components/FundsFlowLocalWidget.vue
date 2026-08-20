<template>
  <div class="ffl-root">
    <div class="ffl-toolbar">
      <div class="ffl-tabs" role="tablist">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          type="button"
          class="ffl-tab"
          :class="{ active: activeTab === tab.key }"
          @click="selectTab(tab.key)"
        >
          {{ tab.label }}
        </button>
      </div>
      <div class="ffl-spacer"></div>
      <select v-model="period" class="ffl-select" @change="refresh(false)">
        <option value="21d">21d</option>
        <option value="63d">63d</option>
        <option value="ytd">YTD</option>
      </select>
      <select v-model="metric" class="ffl-select">
        <option value="nominal">R$</option>
        <option value="pct_pl">% PL</option>
        <option value="zscore">Z</option>
      </select>
      <span class="ffl-state" :class="{ ok: payload?.ok, error: Boolean(error) }">{{ statusLabel }}</span>
      <button type="button" class="ffl-btn" :disabled="loading || collecting" @click="refresh(true)">
        {{ loading || collecting ? '...' : 'Atualizar' }}
      </button>
    </div>

    <div v-if="loading && !payload" class="ffl-empty">Carregando Funds Flow Local...</div>
    <div v-else-if="error && !payload" class="ffl-empty error">{{ error }}</div>

    <template v-else-if="payload">
      <header v-if="activeTab !== 'graph'" class="ffl-header">
        <div>
          <h3>Funds Flow Local</h3>
          <p>Dados ate {{ fmtDate(report.as_of_date) }} | Fonte primaria: {{ report.primary_source || 'CVM Informe Diario' }}</p>
        </div>
        <div class="ffl-regime" :class="regimeClass(kpis.regime)">
          <span>Regime</span>
          <strong>{{ regimeLabel(kpis.regime) }}</strong>
        </div>
      </header>

      <section v-if="activeTab !== 'graph'" class="ffl-kpis">
        <div v-for="card in kpiCards" :key="card.key" class="ffl-kpi">
          <span>{{ card.label }}</span>
          <strong :class="moveClass(card.raw)">{{ card.value }}</strong>
        </div>
      </section>

      <FundsFlowOverviewView v-if="activeTab === 'overview'" />
      <FundsFlowB3View v-else-if="activeTab === 'b3'" />
      <FundsFlowEtfView v-else-if="activeTab === 'etf'" />
      <FundsFlowMapView v-else-if="activeTab === 'map'" />
      <FundsFlowStressView v-else-if="activeTab === 'stress'" />
      <FundsFlowAnbimaView v-else-if="activeTab === 'anbima'" />
      <FundsFlowGlobalView v-else-if="activeTab === 'global'" />
      <FundsFlowCftcView v-else-if="activeTab === 'cftc'" />
      <FundsFlowNportView v-else-if="activeTab === 'nport'" />
      <FundsFlowCdaView v-else-if="activeTab === 'cda'" />
      <FundsFlowCdaRadarView v-else-if="activeTab === 'radar_cda'" />
      <FundsFlowGraphView v-else-if="activeTab === 'graph'" />
      <FundsFlowSourcesView v-else-if="activeTab === 'sources'" />
    </template>

    <FundsFlowModals />
  </div>
</template>

<script setup>
import FundsFlowAnbimaView from './FundsFlowAnbimaView.vue'
import FundsFlowB3View from './FundsFlowB3View.vue'
import FundsFlowCdaRadarView from './FundsFlowCdaRadarView.vue'
import FundsFlowCdaView from './FundsFlowCdaView.vue'
import FundsFlowCftcView from './FundsFlowCftcView.vue'
import FundsFlowEtfView from './FundsFlowEtfView.vue'
import FundsFlowGlobalView from './FundsFlowGlobalView.vue'
import FundsFlowGraphView from './FundsFlowGraphView.vue'
import FundsFlowMapView from './FundsFlowMapView.vue'
import FundsFlowModals from './FundsFlowModals.vue'
import FundsFlowNportView from './FundsFlowNportView.vue'
import FundsFlowOverviewView from './FundsFlowOverviewView.vue'
import FundsFlowSourcesView from './FundsFlowSourcesView.vue'
import FundsFlowStressView from './FundsFlowStressView.vue'
import { createFundsFlowActions } from '../actions'
import { FUNDS_FLOW_CONTEXT } from '../context'
import { computed, nextTick, onMounted, onUnmounted, provide, ref, watch } from 'vue'
import {
  linePath,
  heatColor,
  flowHeatColor,
  radarBurnColor,
  radarHeatTitle,
  nportDivergingColor,
  nportCellTint,
  nportRowTint,
  nportTileBackground,
  nportCountryPillStyle,
  totalPages,
  nportTargetLabel,
  nportSideLabel,
  cdaTargetLabel,
  cdaSideLabel,
  edgeFactMetricLabel,
  portfolioSharedFactorText,
  cdaHeatTitle,
  cdaScatterTitle,
  nportHeatTitle,
  nportScatterTitle,
  nportCountryOrbitTitle,
  heatTitle,
  iciHeatTitle,
  expirationRank,
  ratioTone,
  regimeClass,
  regimeLabel,
  stressLabel,
} from '../models/widgetModels'
import {
  tabs,
  colors,
  gridLines,
  b3FocusAssets,
  b3AssetTabs,
  FUNDS_FLOW_HISTORY_DAYS,
  nportTargets,
  nportSides,
  cdaTargets,
  cdaSides,
  cdaGraphTargets,
  moneyFlowModes,
} from '../models/config'
import {
  buildCdaGraph,
  getCdaAssetTrailDetail,
  getCdaBridgePathDetail,
  getCdaGraphNetwork,
  getCdaMoneyTrails,
  getCdaGraphStatus,
  getCdaIssuerCrowding,
} from '../api'
import {
  getCvmCdaAssets,
  getCvmCdaDashboard,
  getCvmCdaFundHoldings,
  getCvmCdaFunds,
  getCvmCdaPositioning,
  getCvmCdaRadar,
  getFundsFlowLocalDashboard,
  getNportDashboard,
  getNportFundHoldings,
  getNportPerformance,
  getNportPositioning,
  getNportRegionAssets,
  getNportRegionFunds,
  ingestCvmCda,
  ingestNportLocal,
} from '../api'
import {
  formatBrlMillion as fmtBrlMillion,
  formatBytes as fmtBytes,
  formatCount as fmtCount,
  formatDate as fmtDate,
  formatDateTime as fmtDateTime,
  formatDays as fmtDays,
  formatLatency as fmtLatency,
  formatMoney as fmtMoney,
  formatNumber as fmtNum,
  formatPercent as fmtPctPlain,
  formatPeriodDate as fmtPeriodDate,
  formatRatio as fmtPct,
  formatSignedCount as signedCount,
  formatUsd as fmtUsd,
  formatUsdMillions as fmtUsdMn,
  movementClass as moveClass,
  ratioPercent as ratioPct,
  shortDate,
} from '../models/formatters'
import {
  formatSourceCadence as cadenceLabel,
  getSourceStatusClass as sourceStatusClass,
  getSourceStatusLabel as sourceStatusLabel,
  hasPublicationGap as sourcePublicationGap,
} from '../models/sourceStatus'
import {
  buildCdaGraphOverlay,
  countGraphEdgesByType,
  countGraphNodesByLabel,
  inferCdaAssetBucket,
  normalizeCdaKey,
} from '../models/cdaGraphOverlay'

const props = defineProps({
  refreshNonce: {
    type: Number,
    default: 0,
  },
})

const activeTab = ref('overview')
const etfViewMode = ref('local_global')
const etfDailyFlowRefreshNonce = ref(0)
const b3AssetFilter = ref('ALL')
const b3EtfCategoryFilter = ref('ALL')
const period = ref('21d')
const metric = ref('nominal')
const rankingWindow = ref('21d')
const selectedIciSeries = ref(['combined|total', 'etf|total', 'mutual_fund|total_long_term', 'etf|equity', 'etf|bond'])
const refreshingSource = ref('')
const payload = ref(null)
const nportPayload = ref(null)
const cdaPayload = ref(null)
const cdaGraphStatus = ref(null)
const cdaGraphNetwork = ref(null)
const cdaGraphCrowding = ref(null)
const cdaGraphTrails = ref(null)
const loading = ref(false)
const nportLoading = ref(false)
const cdaLoading = ref(false)
const cdaRadarLoading = ref(false)
const cdaGraphLoading = ref(false)
const cdaGraphBuilding = ref(false)
const collecting = ref(false)
const error = ref('')
const nportError = ref('')
const cdaError = ref('')
const cdaRadarError = ref('')
const cdaGraphError = ref('')
const nportLoaded = ref(false)
const nportAnalyticsLoaded = ref(false)
const nportAnalyticsLoading = ref(false)
const cdaLoaded = ref(false)
const cdaAnalyticsLoaded = ref(false)
const cdaAnalyticsLoading = ref(false)
const cdaRadarLoaded = ref(false)
const cdaGraphLoaded = ref(false)
const nportPerformance = ref(null)
const nportPositioning = ref(null)
const nportRegionFunds = ref(null)
const nportRegionAssets = ref(null)
const nportFundHoldings = ref(null)
const cdaPositioning = ref(null)
const cdaFunds = ref(null)
const cdaAssets = ref(null)
const cdaFundHoldings = ref(null)
const cdaRadarPayload = ref(null)
const nportPerfWeighted = ref(false)
const nportPerfPage = ref(1)
const nportExposureTarget = ref('brazil')
const nportExposureSide = ref('long')
const nportExposurePage = ref(1)
const nportAssetTarget = ref('emerging')
const nportAssetSide = ref('long')
const nportAssetPage = ref(1)
const nportSelectedFund = ref(null)
const cdaFundTarget = ref('foreign')
const cdaFundSide = ref('long')
const cdaFundPage = ref(1)
const cdaAssetTarget = ref('private_credit')
const cdaAssetSide = ref('long')
const cdaAssetPage = ref(1)
const cdaSelectedFund = ref(null)
const cdaRadarScenario = ref('stress')
const cdaRadarMacroFilter = ref('ALL')
const cdaGraphTarget = ref('all')
const cdaGraphLimit = ref(260)
const cdaGraphIssuerFilter = ref('')
const cdaGraphFundFilter = ref('')
const cdaAssetLensFilter = ref('equity')
const cdaAssetTrailTypeFilter = ref('all')
const cdaSelectedBridgePath = ref(null)
const cdaBridgePathDetailCache = ref({})
const cdaBridgePathDetailLoading = ref(false)
const cdaBridgePathDetailError = ref('')
const cdaSelectedAssetTrail = ref(null)
const cdaAssetTrailDetailCache = ref({})
const cdaAssetTrailDetailLoading = ref(false)
const cdaAssetTrailDetailError = ref('')
const cdaSelectedCoherenceRow = ref(null)
const moneyFlowMode = ref('mixed')
let timer = null

const report = computed(() => payload.value?.report || {})
const kpis = computed(() => payload.value?.kpis || {})
const insights = computed(() => payload.value?.ai_insights || {})
const heatmap = computed(() => payload.value?.heatmap || {})
const topInflows = computed(() => payload.value?.top_inflows || [])
const topOutflows = computed(() => payload.value?.top_outflows || [])
const classRanking = computed(() => payload.value?.rankings?.by_class || [])
const fundRanking = computed(() => payload.value?.rankings?.by_fund || [])
const rankingWindowOptions = [
  { value: '1d', label: '1d' },
  { value: '5d', label: '5d' },
  { value: '21d', label: '21d' },
]
const rankingWindowLabel = computed(() => rankingWindowOptions.find(option => option.value === rankingWindow.value)?.label || '21d')
const overviewClassRanking = computed(() => (classRanking.value || []).map(item => ({
  ...item,
  displayFlow: rankingWindowFlowValue(item, rankingWindow.value),
})))
const overviewTopInflows = computed(() => overviewClassRanking.value
  .filter(item => Number(item.displayFlow || 0) > 0)
  .sort((a, b) => Number(b.displayFlow || 0) - Number(a.displayFlow || 0))
  .slice(0, 5)
  .map((item, index) => ({ ...item, rank: index + 1 })))
const overviewTopOutflows = computed(() => overviewClassRanking.value
  .filter(item => Number(item.displayFlow || 0) < 0)
  .sort((a, b) => Number(a.displayFlow || 0) - Number(b.displayFlow || 0))
  .slice(0, 5)
  .map((item, index) => ({ ...item, rank: index + 1 })))
const sources = computed(() => payload.value?.source_status || payload.value?.source_inventory || [])
const stress = computed(() => payload.value?.stress_panel || {})
const anbimaFunds = computed(() => payload.value?.anbima_funds || {})
const anbimaDaily = computed(() => anbimaFunds.value?.consolidated_daily || {})
const anbimaDailySummary = computed(() => anbimaDaily.value?.summary || {})
const anbimaValidation = computed(() => anbimaFunds.value?.validation || {})
const anbimaValidationRows = computed(() => anbimaValidation.value?.rows || [])
const anbimaTopInflows = computed(() => (anbimaDaily.value?.top_type_inflows_mtd || []).slice(0, 5))
const anbimaTopOutflows = computed(() => (anbimaDaily.value?.top_type_outflows_mtd || []).slice(0, 5))
const anbimaBulletin = computed(() => anbimaFunds.value?.bulletin || {})
const anbimaLatestArticle = computed(() => (anbimaBulletin.value?.latest_articles || [])[0] || {})
const anbimaRankings = computed(() => anbimaFunds.value?.rankings || {})
const anbimaAdminRanking = computed(() => anbimaRankings.value?.administrators || {})
const anbimaManagerRanking = computed(() => anbimaRankings.value?.managers || {})
const anbimaAdminRows = computed(() => (anbimaAdminRanking.value?.top_aum || []).slice(0, 6))
const anbimaManagerRows = computed(() => (anbimaManagerRanking.value?.top_aum || []).slice(0, 6))
const b3Investor = computed(() => payload.value?.b3_investor_participation || {})
const b3Participants = computed(() => b3Investor.value?.participants || [])
const b3TrendMap = computed(() => Object.fromEntries(
  (b3Investor.value?.trend_by_participant || []).map(item => [item.participant_type, item]),
))
const b3OpenInterest = computed(() => payload.value?.b3_open_interest || {})
const b3OiSummary = computed(() => b3OpenInterest.value?.product_summary || [])
const b3InvestorMonthly = computed(() => payload.value?.b3_investor_participation_monthly || {})
const b3MonthlyRows = computed(() => b3InvestorMonthly.value?.rows || [])
const b3MarketData = computed(() => payload.value?.b3_market_data_report || {})
const b3Etfs = computed(() => payload.value?.b3_etfs || {})
const bcbMacro = computed(() => payload.value?.bcb_macro || {})
const etfPanel = computed(() => payload.value?.etf_panel || {})
const brazilVsGlobal = computed(() => payload.value?.brazil_vs_global || {})
const iciGlobal = computed(() => brazilVsGlobal.value?.ici_global_flows || {})
const iciWeekly = computed(() => iciGlobal.value?.weekly || {})
const iciLatestByVehicle = computed(() => iciWeekly.value?.latest_by_vehicle || {})
const iciMonthlyEtf = computed(() => iciGlobal.value?.monthly_etf || {})
const iciWorldwide = computed(() => iciGlobal.value?.worldwide_quarterly || {})
const cftcPositioning = computed(() => brazilVsGlobal.value?.cftc_positioning || {})
const nportReport = computed(() => nportPayload.value?.report || {})
const nportKpis = computed(() => nportPayload.value?.kpis || {})
const nportSummaries = computed(() => nportPayload.value?.summaries || {})
const nportInsights = computed(() => nportPayload.value?.ai_readiness || {})
const nportManifest = computed(() => nportPayload.value?.manifest || [])
const nportLogs = computed(() => nportPayload.value?.logs || [])
const nportAssetRows = computed(() => nportSummaries.value?.asset_cat || [])
const nportCountryRows = computed(() => nportSummaries.value?.country || [])
const nportCurrencyRows = computed(() => nportSummaries.value?.currency || [])
const nportDerivativeRows = computed(() => nportSummaries.value?.derivative_cat || [])
const nportFairValueRows = computed(() => nportSummaries.value?.fair_value_level || [])
const nportIssuerRows = computed(() => nportPayload.value?.top_issuers || [])
const nportSecurityRows = computed(() => nportPayload.value?.top_securities || [])
const nportFundRows = computed(() => nportPayload.value?.top_funds || [])
const nportRegistrantRows = computed(() => nportPayload.value?.top_registrants || [])
const nportDebtRows = computed(() => nportPayload.value?.debt_maturity || [])
const nportPerformanceRows = computed(() => nportPerformance.value?.rows || [])
const nportRegionFundRows = computed(() => nportRegionFunds.value?.rows || [])
const nportRegionAssetRows = computed(() => nportRegionAssets.value?.rows || [])
const nportHoldingRows = computed(() => nportFundHoldings.value?.rows || [])
const nportCountryImbalanceRows = computed(() => nportPositioning.value?.country_imbalance || [])
const nportSqueezeRows = computed(() => nportPositioning.value?.squeeze_radar || [])
const nportEdgeRows = computed(() => nportPositioning.value?.edge_funds || [])
const cdaReport = computed(() => cdaPayload.value?.report || {})
const cdaKpis = computed(() => cdaPayload.value?.kpis || {})
const cdaSummaries = computed(() => cdaPayload.value?.summaries || {})
const cdaInsights = computed(() => cdaPayload.value?.ai_readiness || {})
const cdaManifest = computed(() => cdaPayload.value?.manifest || [])
const cdaLogs = computed(() => cdaPayload.value?.logs || [])
const cdaTopFunds = computed(() => cdaPayload.value?.top_funds || [])
const cdaIssuerRows = computed(() => cdaPayload.value?.top_issuers || [])
const cdaAssetSummaryRows = computed(() => cdaSummaries.value?.asset_class || [])
const cdaFundRows = computed(() => cdaFunds.value?.rows || [])
const cdaAssetRows = computed(() => cdaAssets.value?.rows || [])
const cdaHoldingRows = computed(() => cdaFundHoldings.value?.rows || [])
const cdaRadarReport = computed(() => cdaRadarPayload.value?.report || {})
const cdaRadarCoverage = computed(() => cdaRadarPayload.value?.coverage || {})
const cdaRadarSummary = computed(() => cdaRadarPayload.value?.summary || {})
const cdaRadarScenarios = computed(() => cdaRadarPayload.value?.scenarios || [])
const cdaRadarScenarioMap = computed(() => Object.fromEntries(cdaRadarScenarios.value.map(item => [item.key, item])))
const cdaRadarScenarioActive = computed(() => cdaRadarScenarioMap.value[cdaRadarScenario.value] || cdaRadarScenarios.value[0] || {})
const cdaRadarClassSummary = computed(() => cdaRadarPayload.value?.class_summary || [])
const cdaRadarBucketSummary = computed(() => cdaRadarPayload.value?.bucket_summary || [])
const cdaRadarFundAllRows = computed(() => cdaRadarPayload.value?.fund_rows || [])
const cdaRadarHeatmap = computed(() => cdaRadarPayload.value?.heatmap || {})
const cdaRadarMacroOptions = computed(() => [
  { key: 'ALL', label: 'Todos' },
  ...cdaRadarClassSummary.value
    .map(item => item?.radar_group || item?.fund_type_group || item?.macro_classe)
    .filter(Boolean)
    .map(label => ({ key: label, label })),
])
const cdaRadarFundRows = computed(() => {
  const scenarioKey = cdaRadarScenario.value || 'stress'
  const selectedClass = cdaRadarMacroFilter.value
  const rows = cdaRadarFundAllRows.value.filter(item => {
    const group = item?.radar_group || item?.fund_type_group || item?.macro_classe
    return selectedClass === 'ALL' || group === selectedClass
  })
  return [...rows]
    .sort((a, b) => {
      const aRunway = Number(a?.[`runway_days_${scenarioKey}`] ?? 999)
      const bRunway = Number(b?.[`runway_days_${scenarioKey}`] ?? 999)
      if (aRunway !== bRunway) return aRunway - bRunway
      return Number(b?.inventory_burn_pct || 0) - Number(a?.inventory_burn_pct || 0)
    })
    .slice(0, 40)
})
const cdaRadarSelectedClassSummary = computed(() => {
  if (cdaRadarMacroFilter.value === 'ALL') return cdaRadarClassSummary.value
  return cdaRadarClassSummary.value.filter((item) => {
    const group = item?.radar_group || item?.fund_type_group || item?.macro_classe
    return group === cdaRadarMacroFilter.value
  })
})
const cdaRadarTopPressureRows = computed(() => cdaRadarSelectedClassSummary.value.slice(0, 8))
const cdaRadarCards = computed(() => [
  {
    key: 'coverage_pl',
    label: 'PL coberto',
    value: fmtMoney(cdaRadarCoverage.value.matched_cda_pl),
    detail: `${fmtPctPlain(Number(cdaRadarCoverage.value.matched_cda_pl_pct || 0) * 100)} do CDA`,
    tone: 'flat',
  },
  {
    key: 'net_since',
    label: 'Fluxo desde CDA',
    value: fmtMoney(cdaRadarSummary.value.total_net_flow_since_cda),
    detail: `${fmtCount(cdaRadarSummary.value.redemption_period_days || cdaRadarCoverage.value.days_since_cda)} dias comuns`,
    tone: moveClass(cdaRadarSummary.value.total_net_flow_since_cda),
  },
  {
    key: 'gross_redemption_since',
    label: 'Resgates desde CDA',
    value: fmtMoney(cdaRadarSummary.value.total_gross_redemption_since_cda),
    detail: `${fmtCount(cdaRadarSummary.value.redemption_period_days || cdaRadarCoverage.value.days_since_cda)} dias comuns`,
    tone: Number(cdaRadarSummary.value.total_gross_redemption_since_cda || 0) > 0 ? 'down' : 'flat',
  },
  {
    key: 'sellable_technical',
    label: 'Estoque tecnico',
    value: fmtMoney(cdaRadarSummary.value.sellable_inventory_remaining),
    detail: `${fmtPctPlain(Number(cdaRadarSummary.value.inventory_burn_pct || 0) * 100)} ja consumido`,
    tone: 'flat',
  },
  {
    key: 'sellable_plausible',
    label: `Vendavel plausivel ${fmtCount(cdaRadarSummary.value.plausible_horizon_days || 30)}d`,
    value: fmtMoney(cdaRadarSummary.value.plausible_inventory_remaining),
    detail: `${fmtPctPlain(Number(cdaRadarSummary.value.plausible_inventory_burn_pct || 0) * 100)} ja consumido`,
    tone: 'flat',
  },
  {
    key: 'runway_plausible',
    label: 'Runway plausivel',
    value: fmtDays(cdaRadarScenarioMap.value.stress?.plausible_runway_days),
    detail: `tec ${fmtDays(cdaRadarScenarioMap.value.stress?.runway_days)} | ${fmtCount(cdaRadarScenarioMap.value.stress?.plausible_funds_under_5d)} fundos <5d`,
    tone: Number(cdaRadarScenarioMap.value.stress?.plausible_runway_days || 999) <= 15 ? 'warn' : 'flat',
  },
  {
    key: 'top_class',
    label: 'Tipo no radar',
    value: cdaRadarSummary.value.top_pressure_class || '-',
    detail: cdaRadarReport.value.flow_as_of_date ? `fluxo ate ${fmtDate(cdaRadarReport.value.flow_as_of_date)}` : 'cruzamento CDA x fluxo',
    tone: 'flat',
  },
  {
    key: 'negative_21d',
    label: 'Fundos 21d negativo',
    value: fmtCount(cdaRadarSummary.value.funds_with_negative_21d),
    detail: `${fmtCount(cdaRadarSummary.value.funds_at_risk_stress_5d)} em stress curto`,
    tone: Number(cdaRadarSummary.value.funds_at_risk_stress_5d || 0) > 0 ? 'warn' : 'flat',
  },
])
const cdaHeatmap = computed(() => cdaPositioning.value?.heatmap || cdaPayload.value?.heatmap || {})
const cdaConcentrationRows = computed(() => cdaPositioning.value?.concentration || cdaTopFunds.value || [])
const cdaGraphData = computed(() => {
  const graph = cdaGraphNetwork.value || {}
  if (!Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) return null
  const augmented = buildCdaGraphOverlay(
    graph,
    cdaGraphTrails.value || {},
    cdaGraphMonth.value || 'latest',
  )
  return {
    graph_id: `cvm-cda-${graph.month || 'latest'}-overlay`,
    nodes: augmented.nodes,
    edges: augmented.edges,
    node_count: augmented.nodes.length,
    edge_count: augmented.edges.length,
  }
})
const cdaGraphNodeCounts = computed(() => cdaGraphStatus.value?.graph?.nodes_by_label || [])
const cdaGraphEdgeCounts = computed(() => cdaGraphStatus.value?.graph?.edges_by_type || [])
const cdaVisibleGraphNodeCounts = computed(() => countGraphNodesByLabel(cdaGraphData.value?.nodes || []))
const cdaVisibleGraphEdgeCounts = computed(() => countGraphEdgesByType(cdaGraphData.value?.edges || []))
const cdaGraphCrowdingRows = computed(() => cdaGraphCrowding.value?.rows || [])
const cdaMoneyLayers = computed(() => cdaGraphTrails.value?.layers || [])
const cdaMoneyActivityLayers = computed(() => cdaGraphTrails.value?.activity_layers || [])
const cdaAssetClassActivity = computed(() => cdaGraphTrails.value?.asset_class_activity || [])
const cdaFundQuotaBreakdown = computed(() => cdaGraphTrails.value?.fund_quota_breakdown || [])
const cdaTargetDetails = computed(() => cdaGraphTrails.value?.target_details || {})
const cdaBridgePathDetails = computed(() => ({
  ...(cdaGraphTrails.value?.bridge_path_details || {}),
  ...cdaBridgePathDetailCache.value,
}))
const cdaAssetTrailSets = computed(() => cdaGraphTrails.value?.asset_trails || {})
const cdaAssetTrailRawCovetedRows = computed(() => cdaAssetTrailSets.value?.coveted || [])
const cdaAssetTrailRawShortedRows = computed(() => cdaAssetTrailSets.value?.shorted || [])
const cdaAssetTrailDetails = computed(() => cdaAssetTrailDetailCache.value || {})
const cdaAssetLenses = computed(() => cdaGraphTrails.value?.asset_lenses || {})
const cdaAssetLensBuckets = computed(() => cdaAssetLenses.value?.buckets || [])
const cdaAssetTrailTypeOptions = computed(() => {
  const buckets = cdaAssetLensBuckets.value
    .filter(item => item.bucket && item.bucket !== 'all')
    .filter(item => Number(item.asset_count || 0) > 0)
  return [
    {
      bucket: 'all',
      label: 'Todos',
      asset_count: cdaAssetTrailRawCovetedRows.value.length + cdaAssetTrailRawShortedRows.value.length,
    },
    ...buckets,
  ]
})
const cdaAssetTrailTypeLabel = computed(() =>
  cdaAssetTrailTypeOptions.value.find(item => item.bucket === cdaAssetTrailTypeFilter.value)?.label || 'Todos',
)
const cdaActiveAssetLensKey = computed(() => {
  const available = new Set(cdaAssetLensBuckets.value.map(item => item.bucket))
  if (available.has(cdaAssetLensFilter.value)) return cdaAssetLensFilter.value
  return cdaAssetLenses.value?.default_bucket || cdaAssetLensBuckets.value?.[0]?.bucket || 'all'
})
const cdaActiveAssetLensLabel = computed(() =>
  cdaAssetLensBuckets.value.find(item => item.bucket === cdaActiveAssetLensKey.value)?.label || 'Ativos',
)
const cdaAssetLensRows = computed(() => {
  const rows = cdaAssetLenses.value?.rows || []
  if (cdaActiveAssetLensKey.value === 'all') return rows.slice(0, 24)
  return rows.filter(item => item.bucket === cdaActiveAssetLensKey.value).slice(0, 24)
})
const cdaAssetTrailCovetedRows = computed(() =>
  cdaFilteredAssetTrailRows('coveted', cdaAssetTrailTypeFilter.value),
)
const cdaAssetTrailShortedRows = computed(() =>
  cdaFilteredAssetTrailRows('shorted', cdaAssetTrailTypeFilter.value),
)
const cdaParticipantAssetCoherence = computed(() => cdaGraphTrails.value?.participant_asset_coherence || {})
const cdaParticipantCoherenceRows = computed(() => cdaParticipantAssetCoherence.value?.rows || [])
const cdaSelectedCoherenceAssets = computed(() => cdaSelectedCoherenceRow.value?.sample_assets || [])
const cdaSelectedCoherenceEvidence = computed(() => {
  const row = cdaSelectedCoherenceRow.value || {}
  return [
    {
      label: 'B3 1d',
      value: fmtMoney(row.participant_daily_flow_brl),
      tone: moveClass(row.participant_daily_flow_brl),
    },
    {
      label: 'B3 5d',
      value: fmtMoney(row.participant_flow_5d_brl),
      tone: moveClass(row.participant_flow_5d_brl),
    },
    {
      label: 'B3 21d',
      value: fmtMoney(row.participant_flow_21d_brl),
      tone: moveClass(row.participant_flow_21d_brl),
    },
    {
      label: 'CDA compras',
      value: fmtMoney(row.bucket_buy_value),
      tone: moveClass(row.bucket_buy_value),
    },
    {
      label: 'CDA vendas',
      value: fmtMoney(row.bucket_sell_value),
      tone: Number(row.bucket_sell_value || 0) > 0 ? 'down' : 'flat',
    },
    {
      label: 'CDA liquido',
      value: fmtMoney(row.bucket_net_value),
      tone: moveClass(row.bucket_net_value),
    },
    {
      label: 'Gross CDA',
      value: fmtMoney(row.bucket_gross_value),
      tone: 'flat',
    },
    {
      label: 'Fundos / ativos',
      value: `${fmtCount(row.fund_count)} / ${fmtCount(row.asset_count)}`,
      tone: 'flat',
    },
  ]
})
const cdaOptionTriangulation = computed(() => cdaGraphTrails.value?.option_triangulation || {})
const cdaOptionTriangulationSummary = computed(() => cdaOptionTriangulation.value?.summary || {})
const cdaOptionUnderlyingRows = computed(() => cdaOptionTriangulation.value?.underlying_rows || [])
const cdaOptionPairRows = computed(() => cdaOptionTriangulation.value?.asset_pair_rows || [])
const cdaOptionFundLinkRows = computed(() => cdaOptionTriangulation.value?.fund_option_equity_links || [])
const cdaPortfolioSimilarity = computed(() => cdaGraphTrails.value?.portfolio_similarity || {})
const cdaPortfolioSummary = computed(() => cdaPortfolioSimilarity.value?.summary || {})
const cdaPortfolioPairRows = computed(() => cdaPortfolioSimilarity.value?.pairs || [])
const cdaPortfolioStructureRows = computed(() => cdaPortfolioSimilarity.value?.structures || [])
const cdaPortfolioFactorRows = computed(() => cdaPortfolioSimilarity.value?.factors || [])
const cdaPortfolioFundProfileRows = computed(() => cdaPortfolioSimilarity.value?.fund_profiles || [])
const cdaBridgePathRows = computed(() => cdaGraphTrails.value?.bridge_paths || [])
const cdaGraphExplanatoryRows = computed(() => cdaGraphTrails.value?.explanatory_connections || [])
const cdaSelectedBridgeDetail = computed(() => {
  const selected = cdaSelectedBridgePath.value
  if (!selected) return {}
  return cdaBridgePathDetails.value?.[bridgePathKey(selected)] || {}
})
const cdaSelectedBridgeFunds = computed(() => cdaSelectedBridgeDetail.value?.funds || [])
const cdaSelectedBridgeIssuers = computed(() => cdaSelectedBridgeDetail.value?.issuers || [])
const cdaSelectedBridgeAssets = computed(() => cdaSelectedBridgeDetail.value?.assets || [])
const cdaSelectedAssetTrailDetail = computed(() => {
  const selected = cdaSelectedAssetTrail.value
  if (!selected) return {}
  return cdaAssetTrailDetails.value?.[assetTrailKey(selected)] || {}
})
const cdaSelectedAssetFundLinks = computed(() => cdaSelectedAssetTrailDetail.value?.fund_links || [])
const cdaGraphMonth = computed(() =>
  cdaGraphNetwork.value?.month
  || cdaGraphStatus.value?.graph?.latest_month
  || cdaReport.value.period_label
  || 'latest')
const cdaGraphCards = computed(() => {
  const nodeCount = cdaGraphNodeCounts.value.reduce((sum, item) => sum + Number(item.count || 0), 0)
  const edgeCount = cdaGraphEdgeCounts.value.reduce((sum, item) => sum + Number(item.count || 0), 0)
  return [
    {
      key: 'nodes',
      label: 'Nos Neo4j',
      value: fmtCount(nodeCount),
      detail: `${fmtCount(cdaGraphNodeCount('CdaFund'))} fundos | ${fmtCount(cdaGraphNodeCount('CdaAsset'))} ativos`,
      tone: nodeCount > 0 ? 'up' : 'flat',
    },
    {
      key: 'edges',
      label: 'Relacoes',
      value: fmtCount(edgeCount),
      detail: `${fmtCount(cdaGraphEdgeCount('HOLDS_POSITION'))} posicoes`,
      tone: edgeCount > 0 ? 'up' : 'flat',
    },
    {
      key: 'network',
      label: 'Grafo exibido',
      value: `${fmtCount(cdaGraphNetwork.value?.node_count)} / ${fmtCount(cdaGraphNetwork.value?.edge_count)}`,
      detail: cdaGraphTarget.value === 'all' ? 'Todos os temas' : cdaTargetLabel(cdaGraphTarget.value),
      tone: 'flat',
    },
    {
      key: 'crowding',
      label: 'Crowding emissor',
      value: fmtCount(cdaGraphCrowdingRows.value.length),
      detail: cdaGraphCrowdingRows.value[0]?.issuer_name || 'sem ranking',
      tone: 'warn',
    },
  ]
})
function cdaFilteredAssetTrailRows(side, bucket) {
  const selectedBucket = bucket || 'all'
  const rawRows = side === 'shorted' ? cdaAssetTrailRawShortedRows.value : cdaAssetTrailRawCovetedRows.value
  if (selectedBucket === 'all') {
    return rawRows.map(row => normalizeCdaAssetTrailRow(row, side)).slice(0, 18)
  }

  const metric = side === 'shorted' ? 'short_value' : 'long_value'
  const rowsByLens = (cdaAssetLenses.value?.rows || [])
    .filter(row => row.bucket === selectedBucket)
    .filter(row => Math.abs(Number(row?.[metric] || 0)) > 0)
    .map(row => normalizeCdaAssetTrailRow(row, side))

  const rowsByRaw = rawRows
    .filter(row => cdaAssetTrailBucket(row) === selectedBucket)
    .map(row => normalizeCdaAssetTrailRow(row, side))

  return dedupeCdaAssetTrailRows([...rowsByLens, ...rowsByRaw])
    .sort((a, b) => Math.abs(Number(b?.[metric] || b.gross_value || 0)) - Math.abs(Number(a?.[metric] || a.gross_value || 0)))
    .slice(0, 18)
}

function normalizeCdaAssetTrailRow(row, side) {
  const bucket = row?.bucket || cdaAssetTrailBucket(row)
  const bucketLabel = row?.bucket_label || cdaAssetLensBuckets.value.find(item => item.bucket === bucket)?.label || row?.asset_class || 'Ativo'
  const resolvedSide = side === 'shorted' ? 'shorted' : 'coveted'
  const assetKey = row?.asset_key || row?.display_name || row?.asset_desc || row?.issuer_name || bucketLabel
  const assetClass = row?.asset_class || row?.tp_ativo || bucketLabel
  return {
    ...row,
    asset_key: assetKey,
    display_name: row?.display_name || row?.asset_desc || assetKey,
    asset_class: assetClass,
    bucket,
    bucket_label: bucketLabel,
    side: resolvedSide,
    trail_key: row?.trail_key || `asset-trail-${resolvedSide}-${bucket}-${assetKey}-${assetClass}`,
    tone: resolvedSide === 'shorted' ? 'down' : 'up',
  }
}

function dedupeCdaAssetTrailRows(rows) {
  const seen = new Set()
  const cleaned = []
  rows.forEach(row => {
    const key = normalizeCdaKey(`${row.asset_key}|${row.asset_class}|${row.side}`)
    if (!key || seen.has(key)) return
    seen.add(key)
    cleaned.push(row)
  })
  return cleaned
}

function cdaAssetTrailBucket(row) {
  return row?.bucket || inferCdaAssetBucket(row || {}, row?.asset_key || row?.asset_desc || row?.display_name || '')
}


const cdaMoneyModeOption = computed(() => moneyFlowModes.find(item => item.key === moneyFlowMode.value) || moneyFlowModes[0])
const cdaMoneyModeDetail = computed(() => cdaMoneyModeOption.value.detail)
const cdaMixedMoneyTargets = computed(() => cdaMoneyLayers.value.slice(0, 6).map(item => ({
  ...item,
  display: fmtMoney(item.net_value),
  secondary_display: `${fmtMoney(item.gross_value)} gross`,
})))
const cdaQuarterlyCdaTargets = computed(() => cdaMoneyActivityLayers.value
  .slice()
  .sort((a, b) => Math.abs(Number(b.reported_activity ?? b.net_value ?? 0)) - Math.abs(Number(a.reported_activity ?? a.net_value ?? 0)))
  .slice(0, 3)
  .map(item => {
    const net = Number(item.reported_activity ?? item.net_value ?? 0)
    const gross = Number(item.buy_value || 0) + Number(item.sell_value || 0) || Number(item.gross_value || 0)
    return {
      ...item,
      target: `cda-${item.target}`,
      target_label: `CDA ${item.target_label || item.target}`,
      net_value: net,
      gross_value: gross,
      display: fmtMoney(net),
      secondary_display: `${fmtMoney(gross)} giro`,
      top_issuers: [item.top_issuer].filter(Boolean),
      top_asset_classes: [item.top_asset_class].filter(Boolean),
    }
  }))
const cdaNportCountryRows = computed(() => nportCountryImbalanceRows.value
  .slice()
  .sort((a, b) => Math.abs(Number(b.net_value || 0)) - Math.abs(Number(a.net_value || 0)))
  .slice(0, 8))
const cdaQuarterlyNportTargets = computed(() => cdaNportCountryRows.value.slice(0, 3).map(item => ({
  target: `nport-${item.investment_country}`,
  target_label: `NPORT ${item.investment_country}`,
  name: item.investment_country,
  net_value: Number(item.net_value || 0),
  gross_value: Number(item.gross_value || 0),
  display: fmtUsd(item.net_value),
  secondary_display: `${fmtCount(item.fund_count)} fundos`,
  fund_count: item.fund_count,
  holding_count: item.holding_count,
  top_issuers: [],
  top_asset_classes: [],
})))
const cdaQuarterlyMoneyTargets = computed(() => [
  ...cdaQuarterlyCdaTargets.value,
  ...cdaQuarterlyNportTargets.value,
].slice(0, 6))
const cdaDailyClassRows = computed(() => {
  const rows = [
    ...topInflows.value.slice(0, 4).map((item, index) => ({ item, index, side: 'in' })),
    ...topOutflows.value.slice(0, 4).map((item, index) => ({ item, index, side: 'out' })),
  ]
  const seen = new Set()
  return rows
    .map(({ item, index, side }) => {
      const name = item.name || item.macro_classe || item.subclasse || `Classe ${index + 1}`
      const key = `${side}-${name}`
      if (seen.has(key)) return null
      seen.add(key)
      const value = classFlowValue(item)
      return {
        key,
        name,
        value,
        detail: `${side === 'in' ? 'entrada' : 'saida'} | z ${fmtNum(item.zscore_21d ?? item.zscore ?? 0, 2)}`,
      }
    })
    .filter(item => item && Number.isFinite(item.value) && item.value !== 0)
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
    .slice(0, 8)
})
const cdaDailyParticipantRows = computed(() => b3ParticipantBars.value.slice(0, 8))
const cdaDailyOiRows = computed(() => b3OiMainSummary.value
  .slice()
  .sort((a, b) => Math.abs(Number(b.rolling_21d_variation_open_interest || 0)) - Math.abs(Number(a.rolling_21d_variation_open_interest || 0)))
  .slice(0, 8))
const cdaDailyWeeklyMoneyTargets = computed(() => {
  const iciTargets = [...cdaIciInflowLegs.value.slice(0, 2), ...cdaIciOutflowLegs.value.slice(0, 2)]
    .slice(0, 3)
    .map(item => ({
      target: `ici-${item.key}`,
      target_label: item.label.replace('combined | ', 'ICI '),
      net_value: Number(item.value || 0),
      gross_value: Math.abs(Number(item.value || 0)),
      display: fmtUsdMn(item.value),
      secondary_display: 'semanal',
    }))
  const localTargets = cdaDailyClassRows.value.slice(0, 2).map(item => ({
    target: `local-${item.key}`,
    target_label: item.name,
    net_value: Number(item.value || 0) / 1_000_000,
    gross_value: Math.abs(Number(item.value || 0)) / 1_000_000,
    display: fmtMoney(item.value),
    secondary_display: period.value,
  }))
  const b3Targets = cdaDailyParticipantRows.value.slice(0, 1).map(item => ({
    target: `b3-${item.participant_type}`,
    target_label: `B3 ${item.participant_type}`,
    net_value: Number(item.rolling_21d_net_flow_brl || 0) / 1_000_000,
    gross_value: Math.abs(Number(item.rolling_21d_net_flow_brl || 0)) / 1_000_000,
    display: fmtMoney(item.rolling_21d_net_flow_brl),
    secondary_display: 'participante 21d',
  }))
  const oiTargets = cdaDailyOiRows.value.slice(0, 1).map(item => ({
    target: `oi-${item.asset}`,
    target_label: `OI ${item.asset}`,
    net_value: Number(item.rolling_21d_variation_open_interest || 0) / 1_000,
    gross_value: Math.abs(Number(item.rolling_21d_variation_open_interest || 0)) / 1_000,
    display: signedCount(item.rolling_21d_variation_open_interest),
    secondary_display: 'contratos 21d',
  }))
  return [...iciTargets, ...localTargets, ...b3Targets, ...oiTargets].slice(0, 6)
})
const cdaMoneyMapTargets = computed(() => {
  if (moneyFlowMode.value === 'quarterly') return cdaQuarterlyMoneyTargets.value
  if (moneyFlowMode.value === 'daily_weekly') return cdaDailyWeeklyMoneyTargets.value
  return cdaMixedMoneyTargets.value
})
const cdaMoneySideLayers = computed(() => cdaMoneyMapTargets.value.slice(0, 7))
const cdaMoneyLayerMax = computed(() => Math.max(
  1,
  ...cdaMoneyMapTargets.value.map(item => Math.abs(Number(item.gross_value || item.abs_value || 0))),
))
const cdaMoneyNetMax = computed(() => Math.max(
  1,
  ...cdaMoneySideLayers.value.map(item => Math.abs(Number(item.net_value || 0))),
))
const cdaMoneyTotalGross = computed(() => cdaMoneyMapTargets.value.reduce((sum, item) => sum + Math.abs(Number(item.gross_value || 0)), 0))
const cdaMoneyCore = computed(() => {
  if (moneyFlowMode.value === 'quarterly') {
    return {
      label: 'CDA + N-PORT',
      value: `${fmtCount(cdaGraphNodeCount('CdaFund'))} BR | ${fmtCount(nportKpis.value.funds)} US`,
      detail: `${cdaGraphMonth.value} + ${nportReport.value.quarter || 'NPORT'}`,
    }
  }
  if (moneyFlowMode.value === 'daily_weekly') {
    return {
      label: 'Fluxos freq. alta',
      value: `${fmtDate(report.value.as_of_date)} | ${fmtDate(iciLatestDate.value)}`,
      detail: `B3 ${fmtDate(b3OpenInterest.value?.date || b3Investor.value?.data_until)}`,
    }
  }
  return {
    label: 'Carteiras CDA Brasil',
    value: `${fmtCount(cdaGraphNodeCount('CdaFund'))} fundos`,
    detail: `${fmtMoney(cdaMoneyTotalGross.value)} gross mapeado`,
  }
})
const cdaReductionRows = computed(() => cdaAssetClassActivity.value
  .filter(item => Number(item.net_reduction_value || item.sell_value || 0) > 0)
  .slice()
  .sort((a, b) => Number(b.net_reduction_value || b.sell_value || 0) - Number(a.net_reduction_value || a.sell_value || 0))
  .slice(0, 8))
const cdaFundQuotaRows = computed(() => cdaFundQuotaBreakdown.value
  .slice()
  .sort((a, b) => Math.abs(Number(b.reported_activity || 0)) - Math.abs(Number(a.reported_activity || 0)))
  .slice(0, 8))
const cdaSelectedTargetKey = computed(() => (cdaGraphTarget.value === 'all' ? 'fund_quotas' : cdaGraphTarget.value) || 'foreign')
const cdaSelectedTargetDetail = computed(() => cdaTargetDetails.value?.[cdaSelectedTargetKey.value] || {})
const cdaSelectedTargetLabel = computed(() => cdaSelectedTargetDetail.value?.target_label || cdaTargetLabel(cdaSelectedTargetKey.value))
const cdaSelectedTargetBuys = computed(() => (cdaSelectedTargetDetail.value?.top_buy_funds || []).slice(0, 5))
const cdaSelectedTargetSells = computed(() => (cdaSelectedTargetDetail.value?.top_sell_funds || []).slice(0, 5))
const cdaIciFlowLegs = computed(() => {
  const rows = iciLatestWeeklyRows.value.length
    ? iciLatestWeeklyRows.value
    : iciGlobalRows.value
  return rows.map(item => ({
    key: `${item.vehicle || item.source || 'ici'}-${item.category_key || item.category || item.date}`,
    label: `${item.vehicle || item.source || 'ICI'} | ${item.category || item.category_key || 'Total'}`,
    value: Number(item.flow_usd_mn ?? item.total_flow_usd_mn ?? 0),
  })).filter(item => Number.isFinite(item.value) && item.value !== 0)
})
const cdaIciInflowLegs = computed(() => cdaIciFlowLegs.value
  .filter(item => item.value > 0)
  .sort((a, b) => b.value - a.value)
  .slice(0, 6))
const cdaIciOutflowLegs = computed(() => cdaIciFlowLegs.value
  .filter(item => item.value < 0)
  .sort((a, b) => a.value - b.value)
  .slice(0, 6))
const cdaMixedMoneySources = computed(() => {
  const iciCombined = Number(iciLatestByVehicle.value.combined?.total_flow_usd_mn || 0)
  const b3Foreign = Number(b3MarketSummary.value?.foreign_balance_brl_million || 0) * 1_000_000
  const localFlow = Number(kpis.value.net_flow_21d || 0)
  const totalReductions = cdaReductionRows.value.reduce((sum, item) => sum + Number(item.net_reduction_value || item.sell_value || 0), 0)
  const equityReductionRow = cdaAssetClassActivity.value.find(item => item.asset_class === 'Acoes') || {}
  const equityReduction = Number(equityReductionRow.net_reduction_value || equityReductionRow.sell_value || 0)
  const ratesReduction = cdaAssetClassActivity.value
    .filter(item => ['Titulos Publicos', 'Credito Privado', 'Depositos e IF', 'Agronegocio/Credito'].includes(item.asset_class))
    .reduce((sum, item) => sum + Number(item.net_reduction_value || item.sell_value || 0), 0)
  return [
    {
      key: 'ici',
      label: 'Fluxo externo ICI',
      value: iciCombined,
      abs_value: Math.abs(iciCombined),
      display: fmtUsdMn(iciCombined),
      tone: moveClass(iciCombined),
    },
    {
      key: 'b3_foreign',
      label: 'Estrangeiro B3',
      value: b3Foreign,
      abs_value: Math.abs(b3Foreign),
      display: fmtMoney(b3Foreign),
      tone: moveClass(b3Foreign),
    },
    {
      key: 'local_funds',
      label: 'Fluxo Brasil fundos',
      value: localFlow,
      abs_value: Math.abs(localFlow),
      display: fmtMoney(localFlow),
      tone: moveClass(localFlow),
    },
    {
      key: 'reductions',
      label: 'Reducoes CDA',
      value: -Math.abs(totalReductions),
      abs_value: Math.abs(totalReductions),
      display: fmtMoney(-Math.abs(totalReductions)),
      tone: totalReductions > 0 ? 'down' : 'flat',
    },
    {
      key: 'equity_reduction',
      label: 'Diminuicao acoes',
      value: -Math.abs(equityReduction),
      abs_value: Math.abs(equityReduction),
      display: fmtMoney(-Math.abs(equityReduction)),
      tone: equityReduction > 0 ? 'down' : 'flat',
    },
    {
      key: 'rates_credit_reduction',
      label: 'Reducao titulos/credito',
      value: -Math.abs(ratesReduction),
      abs_value: Math.abs(ratesReduction),
      display: fmtMoney(-Math.abs(ratesReduction)),
      tone: ratesReduction > 0 ? 'down' : 'flat',
    },
  ]
})
const cdaQuarterlyMoneySources = computed(() => {
  const buy = cdaMoneyActivityLayers.value.reduce((sum, item) => sum + Number(item.buy_value || 0), 0)
  const sell = cdaMoneyActivityLayers.value.reduce((sum, item) => sum + Number(item.sell_value || item.reductions_value || 0), 0)
  const net = cdaMoneyActivityLayers.value.reduce((sum, item) => sum + Number(item.reported_activity || 0), 0)
  const nportFlow = Number(nportKpis.value.net_flow_3m || 0)
  const nportShort = -Math.abs(Number(nportKpis.value.short_value || 0))
  const nportDerivatives = Number(nportKpis.value.derivative_value || 0)
  return [
    {
      key: 'cda_buy',
      label: 'CDA compras',
      value: buy,
      abs_value: Math.abs(buy),
      display: fmtMoney(buy),
      tone: 'up',
    },
    {
      key: 'cda_sell',
      label: 'CDA vendas/reduc.',
      value: -Math.abs(sell),
      abs_value: Math.abs(sell),
      display: fmtMoney(-Math.abs(sell)),
      tone: sell > 0 ? 'down' : 'flat',
    },
    {
      key: 'cda_net',
      label: 'CDA saldo atividade',
      value: net,
      abs_value: Math.abs(net),
      display: fmtMoney(net),
      tone: moveClass(net),
    },
    {
      key: 'nport_flow',
      label: 'N-PORT fluxo 3m',
      value: nportFlow,
      abs_value: Math.abs(nportFlow),
      display: fmtUsd(nportFlow),
      tone: moveClass(nportFlow),
    },
    {
      key: 'nport_short',
      label: 'N-PORT short book',
      value: nportShort,
      abs_value: Math.abs(nportShort),
      display: fmtUsd(nportShort),
      tone: nportShort < 0 ? 'down' : 'flat',
    },
    {
      key: 'nport_deriv',
      label: 'N-PORT derivativos',
      value: nportDerivatives,
      abs_value: Math.abs(nportDerivatives),
      display: fmtUsd(nportDerivatives),
      tone: moveClass(nportDerivatives),
    },
  ]
})
const cdaDailyWeeklyMoneySources = computed(() => {
  const iciCombined = Number(iciLatestByVehicle.value.combined?.total_flow_usd_mn || 0)
  const iciEtf = Number(iciLatestByVehicle.value.etf?.total_flow_usd_mn || 0)
  const b3Foreign = Number(b3MarketSummary.value?.foreign_balance_brl_million || 0) * 1_000_000
  const participantNet = cdaDailyParticipantRows.value.reduce((sum, item) => sum + Number(item.rolling_21d_net_flow_brl || 0), 0)
  const oiNet = cdaDailyOiRows.value.reduce((sum, item) => sum + Number(item.rolling_21d_variation_open_interest || 0), 0)
  const localFlow = Number(kpis.value.net_flow_21d || 0)
  const anbimaDay = Number(anbimaDailySummary.value.net_flow_day_brl || 0)
  return [
    {
      key: 'ici_weekly',
      label: 'ICI semanal',
      value: iciCombined,
      abs_value: Math.abs(iciCombined),
      display: fmtUsdMn(iciCombined),
      tone: moveClass(iciCombined),
    },
    {
      key: 'ici_etf',
      label: 'ICI ETF semanal',
      value: iciEtf,
      abs_value: Math.abs(iciEtf),
      display: fmtUsdMn(iciEtf),
      tone: moveClass(iciEtf),
    },
    {
      key: 'b3_foreign_daily', // gitleaks:allow - public dataset identifier
      label: 'B3 estrangeiro',
      value: b3Foreign,
      abs_value: Math.abs(b3Foreign) / 1_000_000,
      display: fmtMoney(b3Foreign),
      tone: moveClass(b3Foreign),
    },
    {
      key: 'b3_participants',
      label: 'B3 participantes',
      value: participantNet,
      abs_value: Math.abs(participantNet) / 1_000_000,
      display: fmtMoney(participantNet),
      tone: moveClass(participantNet),
    },
    {
      key: 'local_cvm',
      label: 'CVM fundos 21d',
      value: localFlow,
      abs_value: Math.abs(localFlow) / 1_000_000,
      display: fmtMoney(localFlow),
      tone: moveClass(localFlow),
    },
    {
      key: 'b3_oi',
      label: 'OI futuros 21d',
      value: oiNet,
      abs_value: Math.abs(oiNet) / 1_000,
      display: signedCount(oiNet),
      tone: moveClass(oiNet),
    },
    {
      key: 'anbima_day',
      label: 'ANBIMA dia',
      value: anbimaDay,
      abs_value: Math.abs(anbimaDay) / 1_000_000,
      display: fmtMoney(anbimaDay),
      tone: moveClass(anbimaDay),
    },
  ].filter(item => Number.isFinite(Number(item.value)) && (item.value !== 0 || item.key === 'b3_oi'))
})
const cdaMoneyMapSources = computed(() => {
  if (moneyFlowMode.value === 'quarterly') return cdaQuarterlyMoneySources.value
  if (moneyFlowMode.value === 'daily_weekly') return cdaDailyWeeklyMoneySources.value
  return cdaMixedMoneySources.value
})
const cdaMoneySourceMax = computed(() => Math.max(
  1,
  ...cdaMoneyMapSources.value.map(item => Math.abs(Number(item.abs_value || 0))),
))
const cdaGraphEdgeFacts = computed(() => {
  const rows = []
  const seen = new Set()
  const add = (item, priority = 0) => {
    if (!item?.fact) return
    const key = `${item.name || item.fact_type || ''}|${item.fact}`.toLowerCase()
    if (seen.has(key)) return
    seen.add(key)
    const metrics = item.metrics || item.attributes || {}
    const score = Number(item.score ?? metrics.gross_value ?? metrics.abs_value_market ?? metrics.value_market ?? 0)
    const directionValue = metrics.reported_activity ?? metrics.net_value ?? metrics.value_market ?? score
    rows.push({
      uuid: item.uuid || `cda-edge-fact-${rows.length}`,
      name: item.name || item.fact_type || 'CONEXAO',
      fact: item.fact,
      fact_type: item.fact_type,
      category: item.category,
      tone: item.tone || moveClass(directionValue),
      score: Number.isFinite(score) ? Math.abs(score) : 0,
      priority,
      metric_label: item.metric_label || edgeFactMetricLabel(metrics),
    })
  }

  cdaGraphExplanatoryRows.value.forEach(item => add(item, 2))
  ;(cdaGraphNetwork.value?.edges || [])
    .slice()
    .sort((a, b) => Math.abs(Number(b.attributes?.abs_value_market || b.attributes?.gross_value || 0)) - Math.abs(Number(a.attributes?.abs_value_market || a.attributes?.gross_value || 0)))
    .forEach(edge => add({
      ...edge,
      category: edge.fact_type === 'HOLDS_POSITION' ? 'Aresta visivel' : 'Contexto',
      score: Math.abs(Number(edge.attributes?.abs_value_market || edge.attributes?.gross_value || edge.attributes?.value_market || 0)),
    }, 1))

  return rows
    .sort((a, b) => (b.priority - a.priority) || (b.score - a.score))
    .slice(0, 24)
})
const cdaFundMax = computed(() => Math.max(1, ...cdaFundRows.value.map(item => Math.abs(Number(item.selected_value || 0)))))
const cdaAssetMax = computed(() => Math.max(1, ...cdaAssetRows.value.map(item => Math.abs(Number(item.selected_value || 0)))))
const cdaHoldingMax = computed(() => Math.max(1, ...cdaHoldingRows.value.map(item => Math.abs(Number(item.value_market || 0)))))
const cdaHeatmapMax = computed(() => Math.max(
  1,
  ...(cdaHeatmap.value.cells || []).map(cell => Math.abs(Number(cell.value || 0))),
))
const cdaHeatmapRows = computed(() => {
  const xs = cdaHeatmap.value.x || []
  const ys = cdaHeatmap.value.y || []
  const cells = new Map((cdaHeatmap.value.cells || []).map(cell => [`${cell.fund_type}|${cell.asset_class}`, cell]))
  return ys.map(fundType => ({
    fund_type: fundType,
    cells: xs.map(asset => cells.get(`${fundType}|${asset}`) || {
      fund_type: fundType,
      asset_class: asset,
      value: 0,
      abs_value: 0,
      fund_count: 0,
      holding_count: 0,
    }),
  }))
})
const cdaHeatmapStyle = computed(() => ({
  gridTemplateColumns: `136px repeat(${Math.max((cdaHeatmap.value.x || []).length, 1)}, minmax(78px, 1fr))`,
}))
const cdaRadarHeatmapRows = computed(() => {
  const xs = cdaRadarHeatmap.value.x || []
  const ys = cdaRadarHeatmap.value.y || []
  const cells = new Map((cdaRadarHeatmap.value.cells || []).map((cell) => {
    const group = cell.radar_group || cell.fund_type_group || cell.macro_classe
    return [`${group}|${cell.bucket_label}`, cell]
  }))
  return ys.map(macro => ({
    macro_classe: macro,
    cells: xs.map(bucket => cells.get(`${macro}|${bucket}`) || {
      macro_classe: macro,
      radar_group: macro,
      fund_type_group: macro,
      bucket_label: bucket,
      burn_pct: 0,
      plausible_burn_pct: 0,
      remaining_inventory: 0,
      plausible_remaining_inventory: 0,
      consumed_since_cda: 0,
      plausible_consumed_since_cda: 0,
      fund_count: 0,
    }),
  }))
})
const cdaRadarHeatmapStyle = computed(() => ({
  gridTemplateColumns: `164px repeat(${Math.max((cdaRadarHeatmap.value.x || []).length, 1)}, minmax(92px, 1fr))`,
}))
const cdaRadarBucketMax = computed(() => Math.max(
  1,
  ...(cdaRadarBucketSummary.value || []).map(item => Math.abs(Number(item.free_inventory_remaining || 0))),
))
const cdaSelectedFundName = computed(() =>
  cdaSelectedFund.value?.fund_name
  || cdaFundHoldings.value?.fund?.fund_name
  || cdaFundHoldings.value?.fund?.fund_cnpj
  || 'Selecione um fundo')
const cdaCards = computed(() => [
  {
    key: 'funds',
    label: 'Fundos',
    value: fmtCount(cdaKpis.value.funds),
    detail: `${fmtCount(cdaKpis.value.holdings)} posicoes`,
    tone: 'flat',
  },
  {
    key: 'pl',
    label: 'PL reportado',
    value: fmtMoney(cdaKpis.value.total_pl),
    detail: cdaReport.value.period_label || '-',
    tone: 'flat',
  },
  {
    key: 'value',
    label: 'Valor carteira',
    value: fmtMoney(cdaKpis.value.reported_abs_value),
    detail: `${fmtCount(cdaKpis.value.securities)} ativos`,
    tone: 'flat',
  },
  {
    key: 'foreign',
    label: 'Exterior',
    value: fmtMoney(cdaKpis.value.foreign_value),
    detail: 'estoque CDA',
    tone: moveClass(cdaKpis.value.foreign_value),
  },
  {
    key: 'conf',
    label: 'Confidencial',
    value: fmtMoney(cdaKpis.value.confidential_value),
    detail: `${fmtCount(cdaKpis.value.funds_confidential_gt_10)} fundos >10%`,
    tone: Number(cdaKpis.value.confidential_value || 0) > 0 ? 'warn' : 'flat',
  },
  {
    key: 'concentration',
    label: 'Concentracao media',
    value: fmtPctPlain(cdaKpis.value.avg_concentration_pct),
    detail: `${fmtCount(cdaKpis.value.funds_concentration_gt_25)} fundos >25%`,
    tone: Number(cdaKpis.value.avg_concentration_pct || 0) > 25 ? 'warn' : 'flat',
  },
])
const cdaScatterScale = computed(() => {
  const rows = cdaConcentrationRows.value.slice(0, 100)
  const xMax = Math.max(1, ...rows.map(item => Math.abs(Number(item.concentration_pct || 0))))
  const yMax = Math.max(1, ...rows.map(item => Math.abs(Number(item.foreign_pct_pl || 0) + Number(item.confidential_pct_pl || 0))))
  return { xMax, yMax }
})
const cdaScatterPoints = computed(() => cdaConcentrationRows.value.slice(0, 100).map((item, index) => {
  const width = 706
  const height = 230
  const xValue = Number(item.concentration_pct || 0)
  const yValue = Number(item.foreign_pct_pl || 0) + Number(item.confidential_pct_pl || 0)
  const pl = Math.max(Number(item.pl || 0), 1)
  return {
    ...item,
    x: 42 + Math.min(xValue / cdaScatterScale.value.xMax, 1) * width,
    y: 258 - Math.min(yValue / cdaScatterScale.value.yMax, 1) * height,
    r: 3 + Math.min(Math.log10(pl) / 13, 1) * 8,
    color: yValue > 30 ? '#fb7185' : index % 2 ? '#60a5fa' : '#2dd4bf',
  }
}))
const cdaClassTiles = computed(() => {
  const rows = cdaAssetSummaryRows.value.slice(0, 18)
  const maxValue = Math.max(1, ...rows.map(item => Math.abs(Number(item.abs_value || item.value || 0))))
  return rows.map(item => {
    const value = Math.abs(Number(item.abs_value || item.value || 0))
    const strength = Math.min(value / maxValue, 1)
    return {
      ...item,
      style: {
        flexGrow: `${0.7 + strength * 4.4}`,
        flexBasis: `${120 + strength * 130}px`,
        minHeight: `${70 + strength * 50}px`,
        background: nportTileBackground(Number(item.value || 0), strength),
        borderColor: 'rgba(45, 212, 191, 0.24)',
      },
      title: `${item.label} | ${fmtMoney(item.value)} | ${fmtCount(item.fund_count)} fundos`,
    }
  })
})
const nportHeatmap = computed(() => nportPositioning.value?.heatmap || {})
const nportHeatmapMax = computed(() => Math.max(
  1,
  ...(nportHeatmap.value.cells || []).map(cell => Math.abs(Number(cell.net_value || 0))),
))
const nportHeatmapRows = computed(() => {
  const xs = nportHeatmap.value.x || []
  const ys = nportHeatmap.value.y || []
  const cells = new Map((nportHeatmap.value.cells || []).map(cell => [`${cell.country}|${cell.asset_cat}`, cell]))
  return ys.map(country => ({
    country,
    cells: xs.map(asset => cells.get(`${country}|${asset}`) || {
      country,
      asset_cat: asset,
      net_value: 0,
      long_value: 0,
      short_value: 0,
      gross_value: 0,
      fund_count: 0,
    }),
  }))
})
const nportHeatmapStyle = computed(() => ({
  gridTemplateColumns: `76px repeat(${Math.max((nportHeatmap.value.x || []).length, 1)}, minmax(58px, 1fr))`,
}))
const nportSelectedFundName = computed(() =>
  nportSelectedFund.value?.series_name
  || nportFundHoldings.value?.fund?.series_name
  || nportFundHoldings.value?.fund?.accession_number
  || 'Selecione um fundo')
const nportQuadrantRows = computed(() => (nportPositioning.value?.fund_quadrant || []).slice(0, 90))
const nportQuadrantScale = computed(() => {
  const xValues = nportQuadrantRows.value.map(item => Number(item.max_holding_pct || 0)).filter(Number.isFinite)
  const yValues = nportQuadrantRows.value.map(item => Number(item.net_pct_aum || 0)).filter(Number.isFinite)
  const xMax = Math.max(1, ...xValues)
  let yMin = Math.min(0, ...yValues)
  let yMax = Math.max(1, ...yValues)
  if (yMin === yMax) {
    yMin -= 1
    yMax += 1
  }
  return { xMax, yMin, yMax }
})
const nportScatterPoints = computed(() => {
  const width = 706
  const height = 230
  const left = 42
  const top = 28
  const scale = nportQuadrantScale.value
  return nportQuadrantRows.value.map((item, index) => {
    const xValue = Number(item.max_holding_pct || 0)
    const yValue = Number(item.net_pct_aum || 0)
    const aum = Math.max(Number(item.net_assets || 0), 1)
    const radius = 3 + Math.min(Math.log10(aum) / 12, 1) * 8
    return {
      ...item,
      color: Number(item.return_3m_pct || 0) >= 0 ? '#34d399' : '#fb7185',
      x: left + Math.min(xValue / Math.max(scale.xMax, 1), 1) * width,
      y: top + height - ((yValue - scale.yMin) / Math.max(scale.yMax - scale.yMin, 1)) * height,
      r: radius,
      opacity: 0.42 + Math.min(index / Math.max(nportQuadrantRows.value.length, 1), 1) * 0.12,
    }
  })
})
const nportScatterZeroY = computed(() => {
  const scale = nportQuadrantScale.value
  return 28 + 230 - ((0 - scale.yMin) / Math.max(scale.yMax - scale.yMin, 1)) * 230
})
const nportCountryOrbitPoints = computed(() => {
  const rows = nportCountryImbalanceRows.value.slice(0, 18)
  const grossMax = Math.max(1, ...rows.map(item => Math.abs(Number(item.gross_value || 0))))
  return rows.map((item, index) => {
    const angle = -Math.PI / 2 + (index / Math.max(rows.length, 1)) * Math.PI * 2
    const gross = Math.abs(Number(item.gross_value || 0))
    const radius = 58 + Math.sqrt(gross / grossMax) * 106
    const x = 395 + Math.cos(angle) * radius
    const y = 165 + Math.sin(angle) * radius
    const bubble = 5 + Math.sqrt(gross / grossMax) * 14
    const net = Number(item.net_to_gross_pct || 0)
    const shortIntensity = Number(item.short_intensity_pct || 0)
    return {
      ...item,
      x,
      y,
      r: bubble,
      labelX: x + (Math.cos(angle) >= 0 ? bubble + 6 : -bubble - 6),
      labelY: y + 3,
      anchor: Math.cos(angle) >= 0 ? 'start' : 'end',
      color: nportDivergingColor(net, 100),
      opacity: 0.22 + Math.min(shortIntensity / 70, 1) * 0.58,
    }
  })
})
const nportCountryBarbellRows = computed(() => {
  const rows = nportCountryImbalanceRows.value.slice(0, 16)
  const maxValue = Math.max(
    1,
    ...rows.flatMap(item => [Math.abs(Number(item.long_value || 0)), Math.abs(Number(item.short_value || 0))]),
  )
  return rows.map(item => ({
    ...item,
    longWidth: Math.min(Math.abs(Number(item.long_value || 0)) / maxValue, 1) * 48,
    shortWidth: Math.min(Math.abs(Number(item.short_value || 0)) / maxValue, 1) * 48,
  }))
})
const nportCrowdingTiles = computed(() => {
  const rows = nportRegionAssetRows.value.slice(0, 18)
  const maxValue = Math.max(1, ...rows.map(item => Math.abs(Number(item.selected_value || 0))))
  return rows.map(item => {
    const value = Math.abs(Number(item.selected_value || 0))
    const signed = nportAssetSide.value === 'short' ? -value : value
    const strength = Math.min(value / maxValue, 1)
    const label = item.issuer_title || item.issuer_name || item.security_key || '-'
    return {
      ...item,
      label,
      style: {
        flexGrow: `${0.7 + strength * 3.8}`,
        flexBasis: `${116 + strength * 124}px`,
        minHeight: `${72 + strength * 42}px`,
        background: nportTileBackground(signed, strength),
        borderColor: nportAssetSide.value === 'short' ? 'rgba(248, 113, 113, 0.32)' : 'rgba(45, 212, 191, 0.3)',
      },
      title: `${label} | ${item.investment_country} | ${fmtUsd(item.selected_value)} | fundos ${fmtCount(item.fund_count)}`,
    }
  })
})
const nportRidgeRows = computed(() => {
  const rows = nportEdgeRows.value.slice(0, 14)
  const maxExposure = Math.max(1, ...rows.map(item => Math.abs(Number(item.net_pct_aum || 0))))
  const maxReturn = Math.max(1, ...rows.map(item => Math.abs(Number(item.return_3m_pct || 0))))
  return rows.map(item => ({
    ...item,
    exposureWidth: Math.min(Math.abs(Number(item.net_pct_aum || 0)) / maxExposure, 1) * 100,
    returnWidth: Math.min(Math.abs(Number(item.return_3m_pct || 0)) / maxReturn, 1) * 100,
  }))
})
const b3MarketSummary = computed(() => {
  const summary = b3MarketData.value?.summary || null
  return summary && Object.keys(summary).length ? summary : null
})
const b3OiMainSummary = computed(() => {
  const byAsset = Object.fromEntries((b3OiSummary.value || []).map(item => [item.asset, item]))
  return b3FocusAssets.map(asset => byAsset[asset]).filter(Boolean)
})
const b3OiOverviewRows = computed(() => b3OiMainSummary.value.map(item => ({
  ...item,
  variation_open_interest: Number(item.variation_open_interest || 0),
  open_interest: Number(item.open_interest || 0),
})))
const b3PositioningStatus = computed(() => b3OpenInterest.value?.participant_positioning || {})
const b3ParticipantBars = computed(() => (b3Investor.value?.trend_by_participant || [])
  .slice()
  .sort((a, b) => Math.abs(Number(b.rolling_21d_net_flow_brl || 0)) - Math.abs(Number(a.rolling_21d_net_flow_brl || 0))))
const b3ParticipantOverviewRows = computed(() => (b3Investor.value?.trend_by_participant || [])
  .slice()
  .map(item => ({
    ...item,
    daily_net_flow_brl: Number(item.daily_net_flow_brl || 0),
    net_flow_brl_mtd: Number(item.net_flow_brl_mtd || 0),
  }))
  .sort((a, b) => Math.abs(Number(b.daily_net_flow_brl || 0)) - Math.abs(Number(a.daily_net_flow_brl || 0))))
const oiOverviewBarMax = computed(() => Math.max(
  ...b3OiOverviewRows.value.map(item => Math.abs(Number(item.variation_open_interest || 0))),
  1,
))
const participantOverviewBarMax = computed(() => Math.max(
  ...b3ParticipantOverviewRows.value.map(item => Math.abs(Number(item.daily_net_flow_brl || 0))),
  1,
))
const b3ContractTotals = computed(() => Object.fromEntries(
  b3OiMainSummary.value.map(item => [item.asset, Number(item.open_interest || 0)]),
))
const b3ContractRows = computed(() => {
  const rows = (b3OpenInterest.value?.latest_contracts || [])
    .filter(item => b3FocusAssets.includes(item.asset))
    .filter(item => b3AssetFilter.value === 'ALL' || item.asset === b3AssetFilter.value)
    .map(item => ({
      ...item,
      share_open_interest: Number(item.open_interest || 0) / Math.max(Number(b3ContractTotals.value[item.asset] || 0), 1) * 100,
    }))
  return rows.sort((a, b) => {
    const assetDiff = b3FocusAssets.indexOf(a.asset) - b3FocusAssets.indexOf(b.asset)
    if (assetDiff) return assetDiff
    return expirationRank(a.expiration_code) - expirationRank(b.expiration_code)
  })
})

const b3EtfCategoryTabs = computed(() => {
  const categories = [...new Set((b3Etfs.value?.funds || []).map(item => item.category).filter(Boolean))]
  return ['ALL', ...categories]
})

const b3EtfRows = computed(() => (b3Etfs.value?.funds || [])
  .filter(item => b3EtfCategoryFilter.value === 'ALL' || item.category === b3EtfCategoryFilter.value)
  .slice()
  .sort((a, b) => String(a.category || '').localeCompare(String(b.category || '')) || String(a.ticker || '').localeCompare(String(b.ticker || ''))))

const etfLocal = computed(() => etfPanel.value?.local || {})
const etfLocalSummary = computed(() => etfLocal.value?.summary || {})
const etfTopFunds = computed(() => (etfLocal.value?.top_funds || []).slice(0, 8))
const etfLocalSeries = computed(() => etfLocal.value?.timeseries || [])
const etfLocalSeriesPreview = computed(() => etfLocalSeries.value.slice(-18))
const etfFlowBarMax = computed(() => Math.max(
  ...etfLocalSeriesPreview.value.map(item => Math.abs(Number(item.rolling_flow_21d || 0))),
  1,
))
const etfAnbimaRows = computed(() => [
  ...(etfPanel.value?.anbima?.categories || []),
  ...(etfPanel.value?.anbima?.types || []).slice(0, 5),
].slice(0, 8))
const etfIciRows = computed(() => (etfPanel.value?.ici?.weekly_categories || [])
  .filter(item => item.category_key !== 'total')
  .slice(0, 8))

const bcbLatestBySeries = computed(() => bcbMacro.value?.latest_by_series || {})
const bcbMacroCards = computed(() => {
  const ptax = bcbMacro.value?.summary?.latest_usdbrl_ptax || {}
  const usd = bcbLatestBySeries.value.usdbrl_sgs || {}
  const selic = bcbLatestBySeries.value.selic_target || {}
  const daily = bcbLatestBySeries.value.selic_daily || {}
  const ipca = bcbLatestBySeries.value.ipca_monthly || {}
  return [
    { key: 'ptax', label: 'PTAX venda', value: fmtNum(ptax.cotacao_venda, 4), date: fmtDate(ptax.date) },
    { key: 'usd', label: 'USD SGS', value: fmtNum(usd.value, 4), date: fmtDate(usd.date) },
    { key: 'selic', label: 'Selic meta', value: fmtPctPlain(selic.value), date: fmtDate(selic.date) },
    { key: 'selic_daily', label: 'Selic diaria', value: fmtPctPlain(daily.value), date: fmtDate(daily.date) },
    { key: 'ipca', label: 'IPCA', value: fmtPctPlain(ipca.value), date: fmtDate(ipca.date) },
  ].filter(item => item.value !== '-')
})

const etfCards = computed(() => {
  const b3Summary = b3Etfs.value?.summary || {}
  const anbimaEtf = (etfPanel.value?.anbima?.categories || [])[0] || {}
  const iciEtf = etfPanel.value?.ici?.latest_weekly || {}
  return [
    {
      key: 'b3_total',
      label: 'ETFs B3',
      value: fmtCount(b3Summary.total_listed),
      detail: `${fmtCount(b3Summary.category_count)} segmentos`,
      tone: 'flat',
    },
    {
      key: 'local_flow',
      label: 'ETF CVM 21d',
      value: fmtMoney(etfLocalSummary.value.net_flow_21d),
      detail: `${fmtCount(etfLocalSummary.value.num_funds)} fundos`,
      tone: moveClass(etfLocalSummary.value.net_flow_21d),
    },
    {
      key: 'local_aum',
      label: 'PL ETF local',
      value: fmtMoney(etfLocalSummary.value.aum),
      detail: fmtDate(etfLocalSummary.value.date),
      tone: 'flat',
    },
    {
      key: 'anbima_mtd',
      label: 'ANBIMA ETF mes',
      value: fmtMoney(anbimaEtf.net_flow_month_brl),
      detail: fmtMoney(anbimaEtf.aum_brl),
      tone: moveClass(anbimaEtf.net_flow_month_brl),
    },
    {
      key: 'ici_weekly',
      label: 'ICI ETF semanal',
      value: fmtUsdMn(iciEtf.total_flow_usd_mn),
      detail: fmtDate(iciEtf.date),
      tone: moveClass(iciEtf.total_flow_usd_mn),
    },
  ]
})

const statusLabel = computed(() => {
  if (loading.value || collecting.value) return 'coletando'
  if (error.value) return 'erro'
  if (payload.value?.ok) return 'online'
  return 'sem base'
})

const metricLabel = computed(() => {
  if (metric.value === 'pct_pl') return '% do PL 21d'
  if (metric.value === 'zscore') return 'z-score 21d'
  return 'R$ bi, rolling 21d'
})

const kpiCards = computed(() => [
  { key: 'd1', label: 'Captacao 1d', value: fmtMoney(kpis.value.net_flow_1d), raw: kpis.value.net_flow_1d },
  { key: 'd5', label: 'Captacao 5d', value: fmtMoney(kpis.value.net_flow_5d), raw: kpis.value.net_flow_5d },
  { key: 'd21', label: 'Captacao 21d', value: fmtMoney(kpis.value.net_flow_21d), raw: kpis.value.net_flow_21d },
  { key: 'ytd', label: 'Captacao YTD', value: fmtMoney(kpis.value.net_flow_ytd), raw: kpis.value.net_flow_ytd },
  { key: 'aum', label: 'PL industria', value: fmtMoney(kpis.value.industry_aum), raw: kpis.value.industry_aum },
  { key: 'cotistas', label: 'Cotistas', value: fmtCount(kpis.value.total_shareholders), raw: kpis.value.delta_shareholders_21d },
  { key: 'pressure', label: 'Pressao', value: fmtNum(kpis.value.pressure_index, 2), raw: kpis.value.pressure_index },
])

const stressCards = computed(() => [
  { label: 'Fundos negativos', value: fmtPct(stress.value.pct_funds_negative), tone: ratioTone(stress.value.pct_funds_negative) },
  { label: 'PL sob resgate', value: fmtPct(stress.value.pct_aum_negative), tone: ratioTone(stress.value.pct_aum_negative) },
  { label: 'HHI resgates', value: fmtNum(stress.value.hhi_redemptions, 3), tone: Number(stress.value.hhi_redemptions || 0) > 0.25 ? 'down' : 'flat' },
  { label: 'Maior resgate', value: fmtPct(stress.value.largest_redemption_share), tone: Number(stress.value.largest_redemption_share || 0) > 0.25 ? 'down' : 'flat' },
  { label: 'Nivel', value: stressLabel(stress.value.stress_level), tone: stress.value.stress_level === 'high' ? 'down' : stress.value.stress_level === 'medium' ? 'warn' : 'up' },
])

const anbimaCards = computed(() => [
  { label: 'PL ANBIMA', value: fmtMoney(anbimaDailySummary.value.aum_brl), tone: 'flat' },
  { label: 'Captação dia', value: fmtMoney(anbimaDailySummary.value.net_flow_day_brl), tone: moveClass(anbimaDailySummary.value.net_flow_day_brl) },
  { label: 'Captação mês', value: fmtMoney(anbimaDailySummary.value.net_flow_month_brl), tone: moveClass(anbimaDailySummary.value.net_flow_month_brl) },
  { label: 'Captação ano', value: fmtMoney(anbimaDailySummary.value.net_flow_ytd_brl), tone: moveClass(anbimaDailySummary.value.net_flow_ytd_brl) },
  { label: 'Tipos ANBIMA', value: fmtCount((anbimaDaily.value?.types || []).length), tone: 'flat' },
  { label: 'Validação', value: fmtCount(anbimaValidationRows.value.length), tone: anbimaValidationRows.value.length ? 'up' : 'flat' },
])

const globalStatus = computed(() => {
  if (iciGlobal.value?.status === 'ok') return 'ICI active'
  return brazilVsGlobal.value?.status?.ici || 'configured'
})

const iciLatestDate = computed(() => {
  const weeklyDates = [...new Set(
    (brazilVsGlobal.value?.global || [])
      .filter(item => item.frequency === 'W' && item.date)
      .map(item => item.date),
  )].sort()
  return weeklyDates[weeklyDates.length - 1] || iciWeekly.value?.latest_date || ''
})

const cftcStatusLabel = computed(() => {
  if (cftcPositioning.value?.status === 'ok') {
    return `${fmtDate(cftcPositioning.value.report_date)} posicao | ${fmtDate(cftcPositioning.value.publication_date)} release`
  }
  return cftcPositioning.value?.status || 'configured'
})

const cftcParticipants = computed(() => cftcPositioning.value?.participant_summary || [])

const cftcDatasets = computed(() => (cftcPositioning.value?.datasets || [])
  .slice()
  .sort((a, b) => String(a.family || '').localeCompare(String(b.family || '')) || String(a.variant || '').localeCompare(String(b.variant || ''))))

const cftcFamilies = computed(() => (cftcPositioning.value?.family_summaries || [])
  .slice()
  .sort((a, b) => Number(b.open_interest || 0) - Number(a.open_interest || 0)))

const cftcBuckets = computed(() => (cftcPositioning.value?.asset_bucket_summary || [])
  .slice()
  .sort((a, b) => Math.abs(Number(b.lev_money_net || 0)) - Math.abs(Number(a.lev_money_net || 0))))

const cftcContracts = computed(() => (cftcPositioning.value?.focus_contracts || cftcPositioning.value?.latest_contracts || [])
  .slice()
  .sort((a, b) => Math.abs(Number(b.lev_money_net || 0)) - Math.abs(Number(a.lev_money_net || 0)))
  .slice(0, 24))

const cftcFocusContracts = computed(() => (cftcPositioning.value?.focus_contracts || cftcPositioning.value?.latest_contracts || [])
  .slice()
  .sort((a, b) => Number(b.open_interest || 0) - Number(a.open_interest || 0)))

const cftcRatesContracts = computed(() => cftcFocusContracts.value
  .filter(item => item.asset_bucket === 'Rates')
  .slice(0, 8))

const cftcEquityContracts = computed(() => cftcFocusContracts.value
  .filter(item => item.asset_bucket === 'Equity Index')
  .slice(0, 8))

const cftcFxContracts = computed(() => cftcFocusContracts.value
  .filter(item => item.asset_bucket === 'FX')
  .slice(0, 8))

const cftcExtendedParticipants = computed(() => (cftcPositioning.value?.extended_participant_summary || [])
  .slice()
  .sort((a, b) => Math.abs(Number(b.net || 0)) - Math.abs(Number(a.net || 0)))
  .slice(0, 28))

const cftcExtendedBuckets = computed(() => (cftcPositioning.value?.extended_asset_bucket_summary || [])
  .slice()
  .sort((a, b) => Math.abs(Number(b.primary_net || 0)) - Math.abs(Number(a.primary_net || 0)))
  .slice(0, 28))

const cftcExtendedContracts = computed(() => (cftcPositioning.value?.extended_contracts || [])
  .slice()
  .sort((a, b) => Math.abs(Number(b.primary_net || 0)) - Math.abs(Number(a.primary_net || 0)))
  .slice(0, 40))

const cftcCards = computed(() => {
  const lev = cftcParticipants.value.find(item => item.participant_key === 'lev_money') || {}
  const assetMgr = cftcParticipants.value.find(item => item.participant_key === 'asset_mgr') || {}
  const rates = cftcBuckets.value.find(item => item.asset_bucket === 'Rates') || {}
  const managedMoney = cftcExtendedParticipants.value.find(item => item.participant_key === 'managed_money') || {}
  const cit = cftcExtendedParticipants.value.find(item => item.participant_key === 'cit') || {}
  return [
    {
      key: 'report',
      label: 'Data COT',
      value: fmtDate(cftcPositioning.value.report_date),
      detail: `Release ${fmtDate(cftcPositioning.value.publication_date)}`,
      tone: 'flat',
    },
    {
      key: 'lev',
      label: 'Leveraged funds net',
      value: signedCount(lev.net),
      detail: `semana ${signedCount(lev.weekly_net_change)}`,
      tone: moveClass(lev.net),
    },
    {
      key: 'asset_mgr',
      label: 'Asset managers net',
      value: signedCount(assetMgr.net),
      detail: `semana ${signedCount(assetMgr.weekly_net_change)}`,
      tone: moveClass(assetMgr.net),
    },
    {
      key: 'rates',
      label: 'Rates lev funds',
      value: signedCount(rates.lev_money_net),
      detail: `OI ${fmtCount(rates.open_interest)}`,
      tone: moveClass(rates.lev_money_net),
    },
    {
      key: 'datasets',
      label: 'Datasets PRE',
      value: fmtCount(cftcDatasets.value.length),
      detail: `${fmtCount(cftcFamilies.value.length)} familias`,
      tone: cftcDatasets.value.length >= 7 ? 'up' : 'flat',
    },
    {
      key: 'managed_money',
      label: 'Managed money',
      value: signedCount(managedMoney.net),
      detail: `${managedMoney.family_label || 'Disaggregated'} semana ${signedCount(managedMoney.weekly_net_change)}`,
      tone: moveClass(managedMoney.net),
    },
    {
      key: 'cit',
      label: 'Commodity index',
      value: signedCount(cit.net),
      detail: `${cit.family_label || 'CIT'} semana ${signedCount(cit.weekly_net_change)}`,
      tone: moveClass(cit.net),
    },
  ]
})

function cftcParticipantLabel(family, participantKey) {
  const map = {
    tff: {
      dealer: 'Dealer',
      asset_mgr: 'Asset mgr',
      lev_money: 'Lev funds',
      other_rept: 'Other rept',
      nonrept: 'Nonreportable',
    },
    disaggregated: {
      prod_merc: 'Producer/Merchant',
      swap: 'Swap dealer',
      managed_money: 'Managed money',
      other_rept: 'Other rept',
      nonrept: 'Nonreportable',
    },
    legacy: {
      noncomm: 'Non-commercial',
      commercial: 'Commercial',
      nonrept: 'Nonreportable',
    },
    supplemental_cit: {
      noncomm_nocit: 'Non-comm ex-CIT',
      commercial_nocit: 'Commercial ex-CIT',
      cit: 'CIT',
      nonrept: 'Nonreportable',
    },
  }
  return map[family]?.[participantKey] || participantKey || '-'
}

const nportCards = computed(() => [
  {
    key: 'holdings',
    label: 'Holdings',
    value: fmtCount(nportKpis.value.holdings),
    detail: `${fmtCount(nportKpis.value.filings)} filings`,
    tone: 'flat',
  },
  {
    key: 'value',
    label: 'Valor reportado',
    value: fmtUsd(nportKpis.value.reported_value),
    detail: `AUM ${fmtUsd(nportKpis.value.net_assets)}`,
    tone: 'flat',
  },
  {
    key: 'flow',
    label: 'Fluxo 3m reportado',
    value: fmtUsd(nportKpis.value.net_flow_3m),
    detail: 'sales + reinv. - redemptions',
    tone: moveClass(nportKpis.value.net_flow_3m),
  },
  {
    key: 'restricted',
    label: 'Restritos',
    value: fmtUsd(nportKpis.value.restricted_value),
    detail: `${fmtPctPlain(ratioPct(nportKpis.value.restricted_value, nportKpis.value.reported_value))} do valor`,
    tone: 'warn',
  },
  {
    key: 'level3',
    label: 'Level 3',
    value: fmtUsd(nportKpis.value.level3_value),
    detail: `${fmtPctPlain(ratioPct(nportKpis.value.level3_value, nportKpis.value.reported_value))} do valor`,
    tone: 'warn',
  },
  {
    key: 'derivatives',
    label: 'Derivativos',
    value: fmtUsd(nportKpis.value.derivative_value),
    detail: `short ${fmtUsd(nportKpis.value.short_value)}`,
    tone: moveClass(nportKpis.value.derivative_value),
  },
])

const iciLatestCards = computed(() => [
  {
    key: 'combined',
    label: 'Global MF+ETF',
    value: iciLatestByVehicle.value.combined?.total_flow_usd_mn,
    date: iciLatestByVehicle.value.combined?.date,
  },
  {
    key: 'etf',
    label: 'ETF net issuance',
    value: iciLatestByVehicle.value.etf?.total_flow_usd_mn,
    date: iciLatestByVehicle.value.etf?.date,
  },
  {
    key: 'mutual',
    label: 'Mutual funds',
    value: iciLatestByVehicle.value.mutual_fund?.total_flow_usd_mn,
    date: iciLatestByVehicle.value.mutual_fund?.date,
  },
].filter(card => Number.isFinite(Number(card.value))))

const iciMonthlyEtfRows = computed(() => (iciMonthlyEtf.value?.assets_by_type || [])
  .filter(item => item.segment_key !== 'all')
  .slice(0, 8))

const iciWorldwideRegions = computed(() => (iciWorldwide.value?.regions || [])
  .filter(item => item.region !== 'World')
  .slice()
  .sort((a, b) => Math.abs(Number(b.net_sales_total_usd_mn || 0)) - Math.abs(Number(a.net_sales_total_usd_mn || 0))))

const iciRegionInflows = computed(() => iciWorldwideRegions.value
  .filter(item => Number(item.net_sales_total_usd_mn || 0) > 0)
  .sort((a, b) => Number(b.net_sales_total_usd_mn || 0) - Number(a.net_sales_total_usd_mn || 0)))

const iciRegionOutflows = computed(() => iciWorldwideRegions.value
  .filter(item => Number(item.net_sales_total_usd_mn || 0) < 0)
  .sort((a, b) => Number(a.net_sales_total_usd_mn || 0) - Number(b.net_sales_total_usd_mn || 0)))

const iciGlobalRows = computed(() => brazilVsGlobal.value?.global || [])

const iciSeriesOptions = computed(() => {
  const byKey = new Map()
  iciGlobalRows.value
    .filter(item => item.frequency === 'W')
    .forEach(item => {
      const key = `${item.vehicle}|${item.category_key}`
      if (byKey.has(key)) return
      byKey.set(key, {
        key,
        vehicle: item.vehicle,
        label: `${item.vehicle_label}: ${item.category}`,
        category: item.category,
      })
    })
  const vehicleOrder = { combined: 0, etf: 1, mutual_fund: 2 }
  return [...byKey.values()]
    .sort((a, b) => (vehicleOrder[a.vehicle] ?? 9) - (vehicleOrder[b.vehicle] ?? 9) || a.label.localeCompare(b.label))
    .slice(0, 18)
})

const iciChartDates = computed(() => [...new Set(iciGlobalRows.value
  .filter(item => item.frequency === 'W')
  .map(item => item.date))]
  .sort())

const iciChartRawSeries = computed(() => {
  const selected = selectedIciSeries.value.length
    ? selectedIciSeries.value
    : iciSeriesOptions.value.slice(0, 4).map(item => item.key)
  const rowsByKey = new Map()
  iciGlobalRows.value
    .filter(item => item.frequency === 'W')
    .forEach(item => {
      const key = `${item.vehicle}|${item.category_key}`
      if (!selected.includes(key)) return
      if (!rowsByKey.has(key)) rowsByKey.set(key, { meta: item, values: new Map() })
      rowsByKey.get(key).values.set(item.date, Number(item.net_flow || 0) / 1000)
    })
  return [...rowsByKey.entries()].map(([key, item], index) => ({
    key,
    name: `${item.meta.vehicle_label}: ${item.meta.category}`,
    color: colors[index % colors.length],
    values: iciChartDates.value.map(date => item.values.get(date) ?? null),
  }))
})

const iciChartScale = computed(() => {
  const values = iciChartRawSeries.value.flatMap(series => series.values).filter(value => Number.isFinite(value))
  if (!values.length) return { min: -1, max: 1 }
  let min = Math.min(...values)
  let max = Math.max(...values)
  if (min === max) {
    min -= 1
    max += 1
  }
  const pad = Math.max((max - min) * 0.1, 0.1)
  return { min: min - pad, max: max + pad }
})

const iciChartSeries = computed(() => {
  const width = 702
  const height = 188
  const left = 42
  const top = 30
  const scale = iciChartScale.value
  const count = Math.max(...iciChartRawSeries.value.map(series => series.values.length), 1)
  return iciChartRawSeries.value.map(series => ({
    ...series,
    points: series.values.map((value, index) => ({
      x: left + (count === 1 ? width : (index / (count - 1)) * width),
      y: top + height - ((value - scale.min) / (scale.max - scale.min)) * height,
      value,
    })).filter(point => Number.isFinite(point.value)),
  }))
})

const iciChartLastPoints = computed(() => iciChartSeries.value
  .map(series => {
    const point = series.points[series.points.length - 1]
    return point ? { ...point, name: series.name, color: series.color } : null
  })
  .filter(Boolean))

const iciLatestWeeklyRows = computed(() => {
  const latestDate = iciLatestDate.value
  return iciGlobalRows.value
    .filter(item => item.frequency === 'W' && item.date === latestDate)
    .map(item => ({ ...item, flow_usd_mn: item.net_flow }))
    .slice()
    .sort((a, b) => {
      const vehicleOrder = { combined: 0, etf: 1, mutual_fund: 2 }
      return (vehicleOrder[a.vehicle] ?? 9) - (vehicleOrder[b.vehicle] ?? 9)
        || Math.abs(Number(b.net_flow || 0)) - Math.abs(Number(a.net_flow || 0))
    })
})

const iciCountryRows = computed(() => (iciWorldwide.value?.countries || [])
  .slice()
  .sort((a, b) => Math.abs(Number(b.net_sales_total_usd_mn || 0)) - Math.abs(Number(a.net_sales_total_usd_mn || 0))))

const iciCountryInflows = computed(() => iciCountryRows.value
  .filter(item => Number(item.net_sales_total_usd_mn || 0) > 0)
  .sort((a, b) => Number(b.net_sales_total_usd_mn || 0) - Number(a.net_sales_total_usd_mn || 0)))

const iciCountryOutflows = computed(() => iciCountryRows.value
  .filter(item => Number(item.net_sales_total_usd_mn || 0) < 0)
  .sort((a, b) => Number(a.net_sales_total_usd_mn || 0) - Number(b.net_sales_total_usd_mn || 0)))

const iciCountryHeatmapColumns = [
  { key: 'net_sales_total_usd_mn', label: 'Total' },
  { key: 'net_sales_equity_usd_mn', label: 'Equity' },
  { key: 'net_sales_bond_usd_mn', label: 'Bond' },
  { key: 'net_sales_money_market_usd_mn', label: 'Money' },
  { key: 'net_sales_etfs_usd_mn', label: 'ETF' },
]

const iciCountryHeatmapRows = computed(() => iciCountryRows.value.slice(0, 24).map(row => ({
  ...row,
  cells: iciCountryHeatmapColumns.map(column => ({
    ...column,
    value: Number(row[column.key] || 0),
  })),
})))

const iciCountryHeatmapMax = computed(() => Math.max(
  ...iciCountryHeatmapRows.value.flatMap(row => row.cells.map(cell => Math.abs(Number(cell.value || 0)))),
  1,
))

const iciCountryHeatmapStyle = computed(() => ({
  gridTemplateColumns: `128px repeat(${iciCountryHeatmapColumns.length}, minmax(92px, 1fr))`,
}))

const sourceCards = computed(() => sources.value.map(rawSource => {
  const source = rawSource.id === 'cvm_cda' && cdaPayload.value?.ok
    ? {
        ...rawSource,
        ok: true,
        status: 'active',
        rows: cdaKpis.value.holdings || rawSource.rows,
        latency_ms: rawSource.latency_ms || 0,
        cached_path: cdaReport.value.db_path || rawSource.cached_path,
        latest_data_date: cdaReport.value?.as_of_date || rawSource.latest_data_date,
        reference_label: cdaReport.value?.period_label || rawSource.reference_label,
        last_captured_at: cdaReport.value?.generated_at || cdaPayload.value?.generated_at || rawSource.last_captured_at,
      }
    : rawSource
  const statusClass = sourceStatusClass(source)
  return {
    ...source,
    statusClass,
    statusLabel: sourceStatusLabel(source),
    cadenceLabel: cadenceLabel(source.cadence),
    officialDate: sourceOfficialDate(source),
    secondaryReference: sourceReference(source),
    capturedAt: sourceCapturedAt(source),
    technicalSummary: sourceTechnicalSummary(source),
    rows: Number(source.rows || 0),
  }
}))

const activeSourceCount = computed(() => sourceCards.value.filter(item => item.statusClass === 'active').length)

const chartRows = computed(() => payload.value?.timeseries?.flow_by_class || [])

const chartClasses = computed(() => {
  const byClass = new Map()
  chartRows.value.forEach(row => {
    const current = byClass.get(row.macro_classe) || 0
    byClass.set(row.macro_classe, Math.max(current, Math.abs(Number(row.rolling_flow_21d || 0))))
  })
  return [...byClass.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 7)
    .map(([name]) => name)
})

const chartRawSeries = computed(() => {
  const dates = [...new Set(chartRows.value.map(row => row.date))].sort()
  const rowsByClass = new Map()
  chartRows.value.forEach(row => {
    if (!chartClasses.value.includes(row.macro_classe)) return
    if (!rowsByClass.has(row.macro_classe)) rowsByClass.set(row.macro_classe, new Map())
    rowsByClass.get(row.macro_classe).set(row.date, row)
  })
  return chartClasses.value.map((name, index) => ({
    name,
    color: colors[index % colors.length],
    values: dates.map(date => metricValue(rowsByClass.get(name)?.get(date))),
  }))
})

const chartScale = computed(() => {
  const values = chartRawSeries.value.flatMap(series => series.values).filter(value => Number.isFinite(value))
  if (!values.length) return { min: -1, max: 1 }
  let min = Math.min(...values)
  let max = Math.max(...values)
  if (min === max) {
    min -= 1
    max += 1
  }
  const pad = Math.max((max - min) * 0.08, 0.0001)
  return { min: min - pad, max: max + pad }
})

const chartSeries = computed(() => {
  const width = 702
  const height = 188
  const left = 42
  const top = 30
  const scale = chartScale.value
  const count = Math.max(...chartRawSeries.value.map(series => series.values.length), 1)
  return chartRawSeries.value.map(series => ({
    ...series,
    points: series.values.map((value, index) => ({
      x: left + (count === 1 ? width : (index / (count - 1)) * width),
      y: top + height - ((value - scale.min) / (scale.max - scale.min)) * height,
      value,
    })).filter(point => Number.isFinite(point.value)),
  }))
})

const chartLastPoints = computed(() => chartSeries.value
  .map(series => {
    const point = series.points[series.points.length - 1]
    return point ? { ...point, name: series.name, color: series.color } : null
  })
  .filter(Boolean))

const heatmapRows = computed(() => {
  const xs = heatmap.value.x || []
  const ys = heatmap.value.y || []
  const matrix = heatmap.value.z || []
  const cellMap = new Map((heatmap.value.cells || []).map(cell => [`${cell.date}|${cell.macro_classe}`, cell]))
  return ys.map((name, rowIndex) => ({
    name,
    cells: xs.map((date, colIndex) => ({
      date,
      name,
      value: matrix?.[rowIndex]?.[colIndex] ?? null,
      detail: cellMap.get(`${date}|${name}`) || null,
    })),
  }))
})

const heatmapStyle = computed(() => ({
  gridTemplateColumns: `112px repeat(${Math.max((heatmap.value.x || []).length, 1)}, minmax(30px, 1fr))`,
}))

async function refresh(force = false) {
  try {
    error.value = ''
    loading.value = true
    const res = await getFundsFlowLocalDashboard({
      period: period.value,
      history_days: FUNDS_FLOW_HISTORY_DAYS,
      _ts: force ? Date.now() : undefined,
    })
    payload.value = res?.data?.data ?? res?.data ?? res ?? null
  } catch (err) {
    error.value = friendlyError(err)
  } finally {
    loading.value = false
    collecting.value = false
    if (activeTab.value === 'etf' && etfViewMode.value === 'daily_flow') {
      etfDailyFlowRefreshNonce.value += 1
    }
  }
}

async function loadNportDashboard(force = false) {
  if (nportLoading.value) return
  try {
    nportError.value = ''
    nportLoading.value = true
    const res = await getNportDashboard({
      quarter: 'latest',
      _ts: force ? Date.now() : undefined,
    })
    nportPayload.value = res?.data?.data ?? res?.data ?? res ?? null
    nportLoaded.value = true
    if (nportPayload.value?.ok) {
      await loadNportAnalytics(force)
    }
  } catch (err) {
    nportError.value = err?.response?.data?.error || err?.message || 'Falha ao carregar N-PORT.'
    nportLoaded.value = true
  } finally {
    nportLoading.value = false
    if (activeTab.value === 'nport') {
      nextTick(() => {
        document.querySelectorAll('.ffl-nport-view').forEach(el => {
          el.scrollTop = 0
          el.scrollLeft = 0
          el?.scrollTo?.({ top: 0, left: 0 })
        })
      })
    }
  }
}

function unwrapResponse(res) {
  return res?.data?.data ?? res?.data ?? res ?? null
}

async function loadNportAnalytics(force = false) {
  if (nportAnalyticsLoading.value) return
  try {
    nportAnalyticsLoading.value = true
    const [performance, funds, assets, positioning] = await Promise.all([
      getNportPerformance({
        quarter: 'latest',
        page: nportPerfPage.value,
        per_page: 18,
        weighted: nportPerfWeighted.value,
        _ts: force ? Date.now() : undefined,
      }),
      getNportRegionFunds({
        quarter: 'latest',
        target: nportExposureTarget.value,
        side: nportExposureSide.value,
        page: nportExposurePage.value,
        per_page: 18,
        _ts: force ? Date.now() : undefined,
      }),
      getNportRegionAssets({
        quarter: 'latest',
        target: nportAssetTarget.value,
        side: nportAssetSide.value,
        page: nportAssetPage.value,
        per_page: 18,
        _ts: force ? Date.now() : undefined,
      }),
      getNportPositioning({
        quarter: 'latest',
        _ts: force ? Date.now() : undefined,
      }),
    ])
    nportPerformance.value = unwrapResponse(performance)
    nportRegionFunds.value = unwrapResponse(funds)
    nportRegionAssets.value = unwrapResponse(assets)
    nportPositioning.value = unwrapResponse(positioning)
    nportAnalyticsLoaded.value = true
  } catch (err) {
    nportError.value = err?.response?.data?.error || err?.message || 'Falha ao carregar analytics N-PORT.'
  } finally {
    nportAnalyticsLoading.value = false
  }
}

async function loadNportPerformancePanel() {
  try {
    const res = await getNportPerformance({
      quarter: 'latest',
      page: nportPerfPage.value,
      per_page: 18,
      weighted: nportPerfWeighted.value,
    })
    nportPerformance.value = unwrapResponse(res)
  } catch (err) {
    nportError.value = err?.response?.data?.error || err?.message || 'Falha ao carregar performance N-PORT.'
  }
}

async function loadNportRegionFundsPanel() {
  try {
    nportSelectedFund.value = null
    nportFundHoldings.value = null
    const res = await getNportRegionFunds({
      quarter: 'latest',
      target: nportExposureTarget.value,
      side: nportExposureSide.value,
      page: nportExposurePage.value,
      per_page: 18,
    })
    nportRegionFunds.value = unwrapResponse(res)
  } catch (err) {
    nportError.value = err?.response?.data?.error || err?.message || 'Falha ao carregar fundos por regiao.'
  }
}

async function loadNportRegionAssetsPanel() {
  try {
    const res = await getNportRegionAssets({
      quarter: 'latest',
      target: nportAssetTarget.value,
      side: nportAssetSide.value,
      page: nportAssetPage.value,
      per_page: 18,
    })
    nportRegionAssets.value = unwrapResponse(res)
  } catch (err) {
    nportError.value = err?.response?.data?.error || err?.message || 'Falha ao carregar ativos por regiao.'
  }
}

async function selectNportFund(item) {
  if (!item?.accession_number) return
  try {
    nportSelectedFund.value = item
    const res = await getNportFundHoldings(item.accession_number, {
      quarter: 'latest',
      target: nportExposureTarget.value,
      side: nportExposureSide.value,
      page: 1,
      per_page: 30,
    })
    nportFundHoldings.value = unwrapResponse(res)
  } catch (err) {
    nportError.value = err?.response?.data?.error || err?.message || 'Falha ao abrir holdings do fundo.'
  }
}

function toggleNportWeighted() {
  nportPerfWeighted.value = !nportPerfWeighted.value
  nportPerfPage.value = 1
  loadNportPerformancePanel()
}

function setNportPerfPage(delta) {
  const nextPage = Math.min(Math.max(nportPerfPage.value + delta, 1), totalPages(nportPerformance.value))
  if (nextPage === nportPerfPage.value) return
  nportPerfPage.value = nextPage
  loadNportPerformancePanel()
}

function setNportExposureTarget(key) {
  if (nportExposureTarget.value === key) return
  nportExposureTarget.value = key
  nportExposurePage.value = 1
  loadNportRegionFundsPanel()
}

function setNportExposureSide(key) {
  if (nportExposureSide.value === key) return
  nportExposureSide.value = key
  nportExposurePage.value = 1
  loadNportRegionFundsPanel()
}

function setNportExposurePage(delta) {
  const nextPage = Math.min(Math.max(nportExposurePage.value + delta, 1), totalPages(nportRegionFunds.value))
  if (nextPage === nportExposurePage.value) return
  nportExposurePage.value = nextPage
  loadNportRegionFundsPanel()
}

function setNportAssetTarget(key) {
  if (nportAssetTarget.value === key) return
  nportAssetTarget.value = key
  nportAssetPage.value = 1
  loadNportRegionAssetsPanel()
}

function setNportAssetSide(key) {
  if (nportAssetSide.value === key) return
  nportAssetSide.value = key
  nportAssetPage.value = 1
  loadNportRegionAssetsPanel()
}

function setNportAssetPage(delta) {
  const nextPage = Math.min(Math.max(nportAssetPage.value + delta, 1), totalPages(nportRegionAssets.value))
  if (nextPage === nportAssetPage.value) return
  nportAssetPage.value = nextPage
  loadNportRegionAssetsPanel()
}

async function ingestLocalNport() {
  try {
    nportError.value = ''
    nportLoading.value = true
    const res = await ingestNportLocal({ force: true })
    const data = res?.data?.data ?? res?.data ?? res ?? null
    nportPayload.value = data?.dashboard || data || null
    nportLoaded.value = true
    if (nportPayload.value?.ok) {
      await loadNportAnalytics(true)
    }
  } catch (err) {
    nportError.value = err?.response?.data?.error || err?.message || 'Falha ao importar N-PORT local.'
  } finally {
    nportLoading.value = false
    if (activeTab.value === 'nport') {
      nextTick(() => {
        document.querySelectorAll('.ffl-nport-view').forEach(el => {
          el.scrollTop = 0
          el.scrollLeft = 0
          el?.scrollTo?.({ top: 0, left: 0 })
        })
      })
    }
  }
}

async function loadCdaDashboard(force = false) {
  if (cdaLoading.value) return
  try {
    cdaError.value = ''
    cdaLoading.value = true
    if (force) cdaRadarLoaded.value = false
    const res = await getCvmCdaDashboard({
      month: 'latest',
      _ts: force ? Date.now() : undefined,
    })
    cdaPayload.value = unwrapResponse(res)
    cdaLoaded.value = true
    if (cdaPayload.value?.ok) {
      await loadCdaAnalytics(force)
    }
  } catch (err) {
    cdaError.value = err?.response?.data?.error || err?.message || 'Falha ao carregar CVM CDA.'
    cdaLoaded.value = true
  } finally {
    cdaLoading.value = false
    if (activeTab.value === 'cda') {
      resetTabScroll('.ffl-cda-view')
    }
  }
}

async function loadCdaAnalytics(force = false) {
  if (cdaAnalyticsLoading.value) return
  try {
    cdaAnalyticsLoading.value = true
    const [funds, assets, positioning] = await Promise.all([
      getCvmCdaFunds({
        month: 'latest',
        target: cdaFundTarget.value,
        side: cdaFundSide.value,
        page: cdaFundPage.value,
        per_page: 18,
        _ts: force ? Date.now() : undefined,
      }),
      getCvmCdaAssets({
        month: 'latest',
        target: cdaAssetTarget.value,
        side: cdaAssetSide.value,
        page: cdaAssetPage.value,
        per_page: 18,
        _ts: force ? Date.now() : undefined,
      }),
      getCvmCdaPositioning({
        month: 'latest',
        _ts: force ? Date.now() : undefined,
      }),
    ])
    cdaFunds.value = unwrapResponse(funds)
    cdaAssets.value = unwrapResponse(assets)
    cdaPositioning.value = unwrapResponse(positioning)
    cdaAnalyticsLoaded.value = true
  } catch (err) {
    cdaError.value = err?.response?.data?.error || err?.message || 'Falha ao carregar analytics CVM CDA.'
  } finally {
    cdaAnalyticsLoading.value = false
  }
}

async function loadCdaRadar(force = false) {
  if (cdaRadarLoading.value) return
  try {
    cdaRadarError.value = ''
    cdaRadarLoading.value = true
    const res = await getCvmCdaRadar({
      month: 'latest',
      force,
      _ts: force ? Date.now() : undefined,
    })
    cdaRadarPayload.value = unwrapResponse(res)
    cdaRadarLoaded.value = true
    const defaultScenario = cdaRadarPayload.value?.default_scenario
    if (defaultScenario) cdaRadarScenario.value = defaultScenario
  } catch (err) {
    cdaRadarError.value = err?.response?.data?.error || err?.message || 'Falha ao carregar Radar CDA.'
    cdaRadarLoaded.value = true
  } finally {
    cdaRadarLoading.value = false
    if (activeTab.value === 'radar_cda') {
      resetTabScroll('.ffl-cda-radar-view')
    }
  }
}

async function loadCdaFundsPanel() {
  try {
    cdaSelectedFund.value = null
    cdaFundHoldings.value = null
    const res = await getCvmCdaFunds({
      month: 'latest',
      target: cdaFundTarget.value,
      side: cdaFundSide.value,
      page: cdaFundPage.value,
      per_page: 18,
    })
    cdaFunds.value = unwrapResponse(res)
  } catch (err) {
    cdaError.value = err?.response?.data?.error || err?.message || 'Falha ao carregar fundos CVM CDA.'
  }
}

async function loadCdaAssetsPanel() {
  try {
    const res = await getCvmCdaAssets({
      month: 'latest',
      target: cdaAssetTarget.value,
      side: cdaAssetSide.value,
      page: cdaAssetPage.value,
      per_page: 18,
    })
    cdaAssets.value = unwrapResponse(res)
  } catch (err) {
    cdaError.value = err?.response?.data?.error || err?.message || 'Falha ao carregar ativos CVM CDA.'
  }
}

async function selectCdaFund(item) {
  if (!item?.fund_cnpj) return
  try {
    cdaSelectedFund.value = item
    const res = await getCvmCdaFundHoldings(item.fund_cnpj, {
      month: 'latest',
      target: cdaFundTarget.value,
      side: cdaFundSide.value,
      page: 1,
      per_page: 34,
    })
    cdaFundHoldings.value = unwrapResponse(res)
  } catch (err) {
    cdaError.value = err?.response?.data?.error || err?.message || 'Falha ao abrir carteira do fundo.'
  }
}

async function openCdaRadarFund(item) {
  if (!item?.fund_cnpj) return
  activeTab.value = 'cda'
  if (!cdaLoaded.value) {
    await loadCdaDashboard(false)
  }
  await selectCdaFund({
    fund_cnpj: item.fund_cnpj,
    fund_name: item.fund_name,
  })
}

async function ingestCdaLatest() {
  try {
    cdaError.value = ''
    cdaLoading.value = true
    cdaRadarLoaded.value = false
    const res = await ingestCvmCda({ force: true, lookback_months: 1 })
    const data = unwrapResponse(res)
    cdaPayload.value = data?.dashboard || data || null
    cdaLoaded.value = true
    if (cdaPayload.value?.ok) {
      await loadCdaAnalytics(true)
    }
  } catch (err) {
    cdaError.value = err?.response?.data?.error || err?.message || 'Falha ao capturar CVM CDA.'
  } finally {
    cdaLoading.value = false
    if (activeTab.value === 'cda') {
      resetTabScroll('.ffl-cda-view')
    }
  }
}

function setCdaFundTarget(key) {
  if (cdaFundTarget.value === key) return
  cdaFundTarget.value = key
  cdaFundPage.value = 1
  loadCdaFundsPanel()
}

function setCdaFundSide(key) {
  if (cdaFundSide.value === key) return
  cdaFundSide.value = key
  cdaFundPage.value = 1
  loadCdaFundsPanel()
}

function setCdaFundPage(delta) {
  const nextPage = Math.min(Math.max(cdaFundPage.value + delta, 1), totalPages(cdaFunds.value))
  if (nextPage === cdaFundPage.value) return
  cdaFundPage.value = nextPage
  loadCdaFundsPanel()
}

function setCdaAssetTarget(key) {
  if (cdaAssetTarget.value === key) return
  cdaAssetTarget.value = key
  cdaAssetPage.value = 1
  loadCdaAssetsPanel()
}

function setCdaAssetSide(key) {
  if (cdaAssetSide.value === key) return
  cdaAssetSide.value = key
  cdaAssetPage.value = 1
  loadCdaAssetsPanel()
}

function setCdaAssetPage(delta) {
  const nextPage = Math.min(Math.max(cdaAssetPage.value + delta, 1), totalPages(cdaAssets.value))
  if (nextPage === cdaAssetPage.value) return
  cdaAssetPage.value = nextPage
  loadCdaAssetsPanel()
}

async function loadCdaGraph(force = false) {
  if (cdaGraphLoading.value) return
  try {
    cdaGraphError.value = ''
    cdaGraphLoading.value = true
    const params = {
      limit: cdaGraphLimit.value,
      target: cdaGraphTarget.value === 'all' ? undefined : cdaGraphTarget.value,
      issuer: cdaGraphIssuerFilter.value?.trim() || undefined,
      fund_cnpj: cdaGraphFundFilter.value?.trim() || undefined,
      _ts: force ? Date.now() : undefined,
    }
    const [status, network, crowding, trails] = await Promise.all([
      getCdaGraphStatus(),
      getCdaGraphNetwork(params),
      getCdaIssuerCrowding({ limit: 10, _ts: force ? Date.now() : undefined }),
      getCdaMoneyTrails({ limit: 36, _ts: force ? Date.now() : undefined }),
    ])
    cdaGraphStatus.value = unwrapResponse(status)
    cdaGraphNetwork.value = unwrapResponse(network)
    cdaGraphCrowding.value = unwrapResponse(crowding)
    cdaGraphTrails.value = unwrapResponse(trails)
    cdaGraphLoaded.value = true
  } catch (err) {
    cdaGraphError.value = err?.response?.data?.error || err?.message || 'Falha ao carregar grafo CDA.'
    cdaGraphLoaded.value = true
  } finally {
    cdaGraphLoading.value = false
  }
}

async function rebuildCdaGraph() {
  try {
    cdaGraphError.value = ''
    cdaGraphBuilding.value = true
    await buildCdaGraph({
      reset: true,
      max_funds: 180,
      max_positions_per_fund: 20,
      min_abs_value: 25_000_000,
      target_funds_per_theme: 30,
    })
    await loadCdaGraph(true)
  } catch (err) {
    cdaGraphError.value = err?.response?.data?.error || err?.message || 'Falha ao reconstruir grafo CDA.'
  } finally {
    cdaGraphBuilding.value = false
  }
}

function setCdaGraphTarget(key) {
  if (cdaGraphTarget.value === key) return
  cdaGraphTarget.value = key
  loadCdaGraph(true)
}

function applyCdaGraphFilters() {
  loadCdaGraph(true)
}

function clearCdaGraphFilters() {
  cdaGraphIssuerFilter.value = ''
  cdaGraphFundFilter.value = ''
  cdaGraphTarget.value = 'all'
  loadCdaGraph(true)
}

function bridgePathKey(item) {
  return `${item?.target || ''}|${item?.fund_type || ''}`
}

function assetTrailKey(item) {
  return item?.trail_key || `${item?.asset_key || ''}|${item?.asset_class || ''}|${item?.side || ''}`
}

async function openCdaBridgeModal(item) {
  cdaSelectedBridgePath.value = item || null
  cdaBridgePathDetailError.value = ''
  if (!item) return
  const key = bridgePathKey(item)
  if (cdaBridgePathDetails.value?.[key]) return
  try {
    cdaBridgePathDetailLoading.value = true
    const res = await getCdaBridgePathDetail({
      target: item.target,
      fund_type: item.fund_type,
      month: cdaGraphMonth.value === 'latest' ? undefined : cdaGraphMonth.value,
      limit: 18,
    })
    const data = unwrapResponse(res)
    if (data?.detail) {
      cdaBridgePathDetailCache.value = {
        ...cdaBridgePathDetailCache.value,
        [key]: data.detail,
      }
    }
  } catch (err) {
    cdaBridgePathDetailError.value = err?.response?.data?.error || err?.message || 'Falha ao carregar detalhe da trilha.'
  } finally {
    cdaBridgePathDetailLoading.value = false
  }
}

function closeCdaBridgeModal() {
  cdaSelectedBridgePath.value = null
}

function filterGraphByBridgePath() {
  if (!cdaSelectedBridgePath.value?.target) return
  cdaGraphTarget.value = cdaSelectedBridgePath.value.target
  closeCdaBridgeModal()
  loadCdaGraph(true)
}

async function openCdaAssetTrailModal(item) {
  cdaSelectedAssetTrail.value = item || null
  cdaAssetTrailDetailError.value = ''
  if (!item) return
  const key = assetTrailKey(item)
  if (cdaAssetTrailDetails.value?.[key]) return
  try {
    cdaAssetTrailDetailLoading.value = true
    const res = await getCdaAssetTrailDetail({
      asset_key: item.asset_key,
      asset_class: item.asset_class,
      side: item.side || 'coveted',
      month: cdaGraphMonth.value === 'latest' ? undefined : cdaGraphMonth.value,
      limit: 24,
    })
    const data = unwrapResponse(res)
    if (data?.detail) {
      cdaAssetTrailDetailCache.value = {
        ...cdaAssetTrailDetailCache.value,
        [key]: data.detail,
      }
    }
  } catch (err) {
    cdaAssetTrailDetailError.value = err?.response?.data?.error || err?.message || 'Falha ao carregar conexoes do ativo.'
  } finally {
    cdaAssetTrailDetailLoading.value = false
  }
}

function closeCdaAssetTrailModal() {
  cdaSelectedAssetTrail.value = null
}

function filterGraphByAssetTrail() {
  const issuer = cdaSelectedAssetTrail.value?.issuer_name
  if (issuer) {
    cdaGraphIssuerFilter.value = issuer
  }
  closeCdaAssetTrailModal()
  loadCdaGraph(true)
}

function openCdaCoherenceModal(item) {
  cdaSelectedCoherenceRow.value = item || null
}

function closeCdaCoherenceModal() {
  cdaSelectedCoherenceRow.value = null
}

function filterGraphByCoherence() {
  const row = cdaSelectedCoherenceRow.value
  if (!row) return
  cdaAssetLensFilter.value = row.bucket || cdaAssetLensFilter.value
  cdaGraphIssuerFilter.value = ''
  cdaGraphFundFilter.value = ''
  closeCdaCoherenceModal()
  loadCdaGraph(true)
}

function setMoneyFlowMode(key) {
  if (!moneyFlowModes.some(item => item.key === key)) return
  moneyFlowMode.value = key
  if (key === 'quarterly' && !nportLoaded.value) {
    loadNportDashboard(false)
  } else if (key === 'quarterly' && nportLoaded.value && !nportAnalyticsLoaded.value) {
    loadNportAnalytics(false)
  }
}

function openSelectedCdaFundGraph() {
  if (!cdaSelectedFund.value?.fund_cnpj) {
    activeTab.value = 'graph'
    loadCdaGraph(true)
    return
  }
  cdaGraphFundFilter.value = cdaSelectedFund.value.fund_cnpj
  activeTab.value = 'graph'
  loadCdaGraph(true)
}

function cdaGraphNodeCount(label) {
  return Number(cdaGraphNodeCounts.value.find(item => item.label === label)?.count || 0)
}

function cdaGraphEdgeCount(type) {
  return Number(cdaGraphEdgeCounts.value.find(item => item.type === type)?.count || 0)
}

function moneySourceY(index, total) {
  const count = Math.max(Number(total || 1), 1)
  return 31 + (index * (186 / Math.max(count - 1, 1)))
}

function moneyTargetY(index, total) {
  const count = Math.max(Number(total || 1), 1)
  return 33 + (index * (182 / Math.max(count - 1, 1)))
}

function moneySourcePath(index, total) {
  const y = moneySourceY(index, total)
  return `M 200 ${y} C 254 ${y}, 292 128, 336 128`
}

function moneyLayerPath(index, total) {
  const y = moneyTargetY(index, total)
  return `M 484 128 C 532 128, 558 ${y}, 590 ${y}`
}

function moneyStrokeWidth(value, maxValue) {
  const ratio = Math.min(Math.abs(Number(value || 0)) / Math.max(Math.abs(Number(maxValue || 0)), 1), 1)
  return 1.2 + ratio * 7.2
}

function moneyLayerTitle(layer) {
  const issuers = (layer.top_issuers || []).filter(Boolean).slice(0, 4).join(', ')
  const classes = (layer.top_asset_classes || []).filter(Boolean).slice(0, 4).join(', ')
  return `${layer.target_label || layer.name}: ${layer.display || fmtMoney(layer.net_value)} | ${layer.secondary_display || fmtMoney(layer.gross_value)} | fundos ${fmtCount(layer.fund_count)} | emissores ${issuers || '-'} | classes ${classes || '-'}`
}

function resetTabScroll(selector) {
  nextTick(() => {
    const scrollActiveTab = () => {
      document.querySelectorAll(selector).forEach(el => {
        el.scrollTop = 0
        el.scrollLeft = 0
        el?.scrollTo?.({ top: 0, left: 0 })
      })
    }
    scrollActiveTab()
    window.requestAnimationFrame(scrollActiveTab)
    window.setTimeout(scrollActiveTab, 0)
    window.setTimeout(scrollActiveTab, 120)
  })
}

const {
    selectTab, refreshSource, toggleIciSeries, metricValue, rankingWindowFlowValue, classFlowValue, b3Trend, divergingBarStyle,
    etfFlowBarHeight, sourceLastCapture, sourceOfficialDate, sourceReference, sourceCapturedAt, sourceTechnicalSummary, sourceTemporalDetail, sourceHealthDetail,
    sourceComponents, sourceLogText, payloadSummaryCollector, friendlyError, handleKeydown,
} = createFundsFlowActions({
    Date, FUNDS_FLOW_HISTORY_DAYS, Set, activeTab, anbimaDaily, b3Investor, b3InvestorMonthly, b3MarketData,
    b3MarketSummary, b3OpenInterest, b3TrendMap, bcbLatestBySeries, bcbMacro, cadenceLabel, cdaAnalyticsLoaded, cdaGraphLoaded,
    cdaLoaded, cdaRadarLoaded, cdaReport, cdaSelectedAssetTrail, cdaSelectedBridgePath, cdaSelectedCoherenceRow, cftcPositioning, closeCdaAssetTrailModal,
    closeCdaBridgeModal, closeCdaCoherenceModal, error, etfFlowBarMax, fmtCount, fmtDate, fmtDateTime, fmtLatency,
    getFundsFlowLocalDashboard, iciLatestDate, iciMonthlyEtf, iciWorldwide, loadCdaAnalytics, loadCdaDashboard, loadCdaGraph, loadCdaRadar,
    loadNportAnalytics, loadNportDashboard, metric, moneyFlowMode, nextTick, nportAnalyticsLoaded, nportLoaded, payload,
    period, refreshingSource, report, resetTabScroll, selectedIciSeries, sourcePublicationGap, sourceStatusClass, sourceStatusLabel,
})

watch(() => props.refreshNonce, () => refresh(true))

onMounted(() => {
  refresh(false)
  timer = setInterval(() => refresh(false), 5 * 60_000)
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  clearInterval(timer)
  window.removeEventListener('keydown', handleKeydown)
})
provide(FUNDS_FLOW_CONTEXT, {
  FUNDS_FLOW_HISTORY_DAYS, activeSourceCount, activeTab, anbimaAdminRanking, anbimaAdminRows, anbimaBulletin, anbimaCards, anbimaDaily,
  anbimaDailySummary, anbimaFunds, anbimaLatestArticle, anbimaManagerRanking, anbimaManagerRows, anbimaRankings, anbimaTopInflows, anbimaTopOutflows,
  anbimaValidation, anbimaValidationRows, applyCdaGraphFilters, assetTrailKey, b3AssetFilter, b3AssetTabs, b3ContractRows, b3ContractTotals,
  b3EtfCategoryFilter, b3EtfCategoryTabs, b3EtfRows, b3Etfs, b3FocusAssets, b3Investor, b3InvestorMonthly, b3MarketData,
  b3MarketSummary, b3MonthlyRows, b3OiMainSummary, b3OiOverviewRows, b3OiSummary, b3OpenInterest, b3ParticipantBars, b3ParticipantOverviewRows,
  b3Participants, b3PositioningStatus, b3Trend, b3TrendMap, bcbLatestBySeries, bcbMacro, bcbMacroCards, brazilVsGlobal,
  bridgePathKey, buildCdaGraph, buildCdaGraphOverlay, cadenceLabel, cdaActiveAssetLensKey, cdaActiveAssetLensLabel, cdaAnalyticsLoaded, cdaAnalyticsLoading,
  cdaAssetClassActivity, cdaAssetLensBuckets, cdaAssetLensFilter, cdaAssetLensRows, cdaAssetLenses, cdaAssetMax, cdaAssetPage, cdaAssetRows,
  cdaAssetSide, cdaAssetSummaryRows, cdaAssetTarget, cdaAssetTrailBucket, cdaAssetTrailCovetedRows, cdaAssetTrailDetailCache, cdaAssetTrailDetailError, cdaAssetTrailDetailLoading,
  cdaAssetTrailDetails, cdaAssetTrailRawCovetedRows, cdaAssetTrailRawShortedRows, cdaAssetTrailSets, cdaAssetTrailShortedRows, cdaAssetTrailTypeFilter, cdaAssetTrailTypeLabel, cdaAssetTrailTypeOptions,
  cdaAssets, cdaBridgePathDetailCache, cdaBridgePathDetailError, cdaBridgePathDetailLoading, cdaBridgePathDetails, cdaBridgePathRows, cdaCards, cdaClassTiles,
  cdaConcentrationRows, cdaDailyClassRows, cdaDailyOiRows, cdaDailyParticipantRows, cdaDailyWeeklyMoneySources, cdaDailyWeeklyMoneyTargets, cdaError, cdaFilteredAssetTrailRows,
  cdaFundHoldings, cdaFundMax, cdaFundPage, cdaFundQuotaBreakdown, cdaFundQuotaRows, cdaFundRows, cdaFundSide, cdaFundTarget,
  cdaFunds, cdaGraphBuilding, cdaGraphCards, cdaGraphCrowding, cdaGraphCrowdingRows, cdaGraphData, cdaGraphEdgeCount, cdaGraphEdgeCounts,
  cdaGraphEdgeFacts, cdaGraphError, cdaGraphExplanatoryRows, cdaGraphFundFilter, cdaGraphIssuerFilter, cdaGraphLimit, cdaGraphLoaded, cdaGraphLoading,
  cdaGraphMonth, cdaGraphNetwork, cdaGraphNodeCount, cdaGraphNodeCounts, cdaGraphStatus, cdaGraphTarget, cdaGraphTargets, cdaGraphTrails,
  cdaHeatTitle, cdaHeatmap, cdaHeatmapMax, cdaHeatmapRows, cdaHeatmapStyle, cdaHoldingMax, cdaHoldingRows, cdaIciFlowLegs,
  cdaIciInflowLegs, cdaIciOutflowLegs, cdaInsights, cdaIssuerRows, cdaKpis, cdaLoaded, cdaLoading, cdaLogs,
  cdaManifest, cdaMixedMoneySources, cdaMixedMoneyTargets, cdaMoneyActivityLayers, cdaMoneyCore, cdaMoneyLayerMax, cdaMoneyLayers, cdaMoneyMapSources,
  cdaMoneyMapTargets, cdaMoneyModeDetail, cdaMoneyModeOption, cdaMoneyNetMax, cdaMoneySideLayers, cdaMoneySourceMax, cdaMoneyTotalGross, cdaNportCountryRows,
  cdaOptionFundLinkRows, cdaOptionPairRows, cdaOptionTriangulation, cdaOptionTriangulationSummary, cdaOptionUnderlyingRows, cdaParticipantAssetCoherence, cdaParticipantCoherenceRows, cdaPayload,
  cdaPortfolioFactorRows, cdaPortfolioFundProfileRows, cdaPortfolioPairRows, cdaPortfolioSimilarity, cdaPortfolioStructureRows, cdaPortfolioSummary, cdaPositioning, cdaQuarterlyCdaTargets,
  cdaQuarterlyMoneySources, cdaQuarterlyMoneyTargets, cdaQuarterlyNportTargets, cdaRadarBucketMax, cdaRadarBucketSummary, cdaRadarCards, cdaRadarClassSummary, cdaRadarCoverage,
  cdaRadarError, cdaRadarFundAllRows, cdaRadarFundRows, cdaRadarHeatmap, cdaRadarHeatmapRows, cdaRadarHeatmapStyle, cdaRadarLoaded, cdaRadarLoading,
  cdaRadarMacroFilter, cdaRadarMacroOptions, cdaRadarPayload, cdaRadarReport, cdaRadarScenario, cdaRadarScenarioActive, cdaRadarScenarioMap, cdaRadarScenarios,
  cdaRadarSelectedClassSummary, cdaRadarSummary, cdaRadarTopPressureRows, cdaReductionRows, cdaReport, cdaScatterPoints, cdaScatterScale, cdaScatterTitle,
  cdaSelectedAssetFundLinks, cdaSelectedAssetTrail, cdaSelectedAssetTrailDetail, cdaSelectedBridgeAssets, cdaSelectedBridgeDetail, cdaSelectedBridgeFunds, cdaSelectedBridgeIssuers, cdaSelectedBridgePath,
  cdaSelectedCoherenceAssets, cdaSelectedCoherenceEvidence, cdaSelectedCoherenceRow, cdaSelectedFund, cdaSelectedFundName, cdaSelectedTargetBuys, cdaSelectedTargetDetail, cdaSelectedTargetKey,
  cdaSelectedTargetLabel, cdaSelectedTargetSells, cdaSideLabel, cdaSides, cdaSummaries, cdaTargetDetails, cdaTargetLabel, cdaTargets,
  cdaTopFunds, cdaVisibleGraphEdgeCounts, cdaVisibleGraphNodeCounts, cftcBuckets, cftcCards, cftcContracts, cftcDatasets, cftcEquityContracts,
  cftcExtendedBuckets, cftcExtendedContracts, cftcExtendedParticipants, cftcFamilies, cftcFocusContracts, cftcFxContracts, cftcParticipantLabel, cftcParticipants,
  cftcPositioning, cftcRatesContracts, cftcStatusLabel, chartClasses, chartLastPoints, chartRawSeries, chartRows, chartScale,
  chartSeries, classFlowValue, classRanking, clearCdaGraphFilters, closeCdaAssetTrailModal, closeCdaBridgeModal, closeCdaCoherenceModal, collecting,
  colors, countGraphEdgesByType, countGraphNodesByLabel, dedupeCdaAssetTrailRows, divergingBarStyle, edgeFactMetricLabel, error, etfAnbimaRows,
  etfCards, etfDailyFlowRefreshNonce, etfFlowBarHeight, etfFlowBarMax, etfIciRows, etfLocal, etfLocalSeries, etfLocalSeriesPreview,
  etfLocalSummary, etfPanel, etfTopFunds, etfViewMode, expirationRank, filterGraphByAssetTrail, filterGraphByBridgePath, filterGraphByCoherence,
  flowHeatColor, fmtBrlMillion, fmtBytes, fmtCount, fmtDate, fmtDateTime, fmtDays, fmtLatency,
  fmtMoney, fmtNum, fmtPct, fmtPctPlain, fmtPeriodDate, fmtUsd, fmtUsdMn, friendlyError,
  fundRanking, getCdaAssetTrailDetail, getCdaBridgePathDetail, getCdaGraphNetwork, getCdaGraphStatus, getCdaIssuerCrowding, getCdaMoneyTrails, getCvmCdaAssets,
  getCvmCdaDashboard, getCvmCdaFundHoldings, getCvmCdaFunds, getCvmCdaPositioning, getCvmCdaRadar, getFundsFlowLocalDashboard, getNportDashboard, getNportFundHoldings,
  getNportPerformance, getNportPositioning, getNportRegionAssets, getNportRegionFunds, globalStatus, gridLines, handleKeydown, heatColor,
  heatTitle, heatmap, heatmapRows, heatmapStyle, iciChartDates, iciChartLastPoints, iciChartRawSeries, iciChartScale,
  iciChartSeries, iciCountryHeatmapColumns, iciCountryHeatmapMax, iciCountryHeatmapRows, iciCountryHeatmapStyle, iciCountryInflows, iciCountryOutflows, iciCountryRows,
  iciGlobal, iciGlobalRows, iciHeatTitle, iciLatestByVehicle, iciLatestCards, iciLatestDate, iciLatestWeeklyRows, iciMonthlyEtf,
  iciMonthlyEtfRows, iciRegionInflows, iciRegionOutflows, iciSeriesOptions, iciWeekly, iciWorldwide, iciWorldwideRegions, inferCdaAssetBucket,
  ingestCdaLatest, ingestCvmCda, ingestLocalNport, ingestNportLocal, insights, kpiCards, kpis, linePath,
  loadCdaAnalytics, loadCdaAssetsPanel, loadCdaDashboard, loadCdaFundsPanel, loadCdaGraph, loadCdaRadar, loadNportAnalytics, loadNportDashboard,
  loadNportPerformancePanel, loadNportRegionAssetsPanel, loadNportRegionFundsPanel, loading, metric, metricLabel, metricValue, moneyFlowMode,
  moneyFlowModes, moneyLayerPath, moneyLayerTitle, moneySourcePath, moneySourceY, moneyStrokeWidth, moneyTargetY, moveClass,
  normalizeCdaAssetTrailRow, normalizeCdaKey, nportAnalyticsLoaded, nportAnalyticsLoading, nportAssetPage, nportAssetRows, nportAssetSide, nportAssetTarget,
  nportCards, nportCellTint, nportCountryBarbellRows, nportCountryImbalanceRows, nportCountryOrbitPoints, nportCountryOrbitTitle, nportCountryPillStyle, nportCountryRows,
  nportCrowdingTiles, nportCurrencyRows, nportDebtRows, nportDerivativeRows, nportDivergingColor, nportEdgeRows, nportError, nportExposurePage,
  nportExposureSide, nportExposureTarget, nportFairValueRows, nportFundHoldings, nportFundRows, nportHeatTitle, nportHeatmap, nportHeatmapMax,
  nportHeatmapRows, nportHeatmapStyle, nportHoldingRows, nportInsights, nportIssuerRows, nportKpis, nportLoaded, nportLoading,
  nportLogs, nportManifest, nportPayload, nportPerfPage, nportPerfWeighted, nportPerformance, nportPerformanceRows, nportPositioning,
  nportQuadrantRows, nportQuadrantScale, nportRegionAssetRows, nportRegionAssets, nportRegionFundRows, nportRegionFunds, nportRegistrantRows, nportReport,
  nportRidgeRows, nportRowTint, nportScatterPoints, nportScatterTitle, nportScatterZeroY, nportSecurityRows, nportSelectedFund, nportSelectedFundName,
  nportSideLabel, nportSides, nportSqueezeRows, nportSummaries, nportTargetLabel, nportTargets, nportTileBackground, oiOverviewBarMax,
  openCdaAssetTrailModal, openCdaBridgeModal, openCdaCoherenceModal, openCdaRadarFund, openSelectedCdaFundGraph, overviewClassRanking, overviewTopInflows, overviewTopOutflows,
  participantOverviewBarMax, payload, payloadSummaryCollector, period, portfolioSharedFactorText, props, radarBurnColor, radarHeatTitle,
  rankingWindow, rankingWindowFlowValue, rankingWindowLabel, rankingWindowOptions, ratioPct, ratioTone, rebuildCdaGraph, refresh,
  refreshSource, refreshingSource, regimeClass, regimeLabel, report, resetTabScroll, selectCdaFund, selectNportFund,
  selectTab, selectedIciSeries, setCdaAssetPage, setCdaAssetSide, setCdaAssetTarget, setCdaFundPage, setCdaFundSide, setCdaFundTarget,
  setCdaGraphTarget, setMoneyFlowMode, setNportAssetPage, setNportAssetSide, setNportAssetTarget, setNportExposurePage, setNportExposureSide, setNportExposureTarget,
  setNportPerfPage, shortDate, signedCount, sourceCapturedAt, sourceCards, sourceComponents, sourceHealthDetail, sourceLastCapture,
  sourceLogText, sourceOfficialDate, sourcePublicationGap, sourceReference, sourceStatusClass, sourceStatusLabel, sourceTechnicalSummary, sourceTemporalDetail,
  sources, statusLabel, stress, stressCards, stressLabel, tabs, timer, toggleIciSeries,
  toggleNportWeighted, topInflows, topOutflows, totalPages, unwrapResponse,
})
</script>

<style scoped src="./FundsFlowLocalWidget.css"></style>
<style scoped src="./FundsFlowLocalWidgetDetails.css"></style>

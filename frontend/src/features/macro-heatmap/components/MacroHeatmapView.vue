<template>
  <div class="heatmap-shell">
    <header class="header">
      <div class="header-copy">
        <AquilesBrand variant="desk" subtitle="PLATAFORMA QUANT" clickable @click="goHome" />
        <div class="eyebrow">Macro Desk</div>
        <h1>Participant Heatmap</h1>
        <p>
          Candles intraday de `WIN`, `WDO` e `DI` com range do dia inteiro, hover OHLC e navegacao horizontal.
        </p>
      </div>
      <div class="actions">
        <button class="ghost" @click="goHome">Home</button>
        <button class="ghost" @click="goBack">Voltar</button>
        <button class="ghost" :disabled="loading || hardReloadingOptions" @click="hardReloadOptionsBaseNow">
          {{ hardReloadingOptions ? 'Hard reload opcoes...' : 'Hard reload opcoes' }}
        </button>
        <button class="primary" :disabled="loading" @click="loadHeatmap(true)">
          {{ loading ? 'Atualizando...' : 'Atualizar agora' }}
        </button>
      </div>
    </header>

    <section class="meta-strip">
      <div><strong>Status:</strong> {{ loading ? 'Atualizando' : 'Pronto' }}</div>
      <div><strong>Intervalo:</strong> {{ panelData?.sample_interval_seconds || '--' }}s</div>
      <div><strong>Historico:</strong> {{ panelData?.history_minutes || '--' }}m</div>
      <div><strong>Ultima foto:</strong> {{ timestampLabel }}</div>
      <div><strong>Ativos:</strong> {{ assetCount }}</div>
      <div><strong>Collector:</strong> {{ panelData?.collector?.running ? 'ativo' : 'parado' }}</div>
      <div><strong>Samples:</strong> {{ panelData?.collector?.sample_count || 0 }}</div>
    </section>

    <section class="filter-strip">
      <div class="filter-block">
        <span class="filter-label">Segmento</span>
        <div class="toolbar-group">
          <button
            v-for="option in PARTICIPANT_SCOPE_OPTIONS"
            :key="option.value"
            class="chip"
            :class="{ active: participantScope === option.value }"
            @click="participantScope = option.value"
          >
            {{ option.label }}
          </button>
        </div>
      </div>
      <div class="filter-block">
        <span class="filter-label">Lado</span>
        <div class="toolbar-group">
          <button
            v-for="option in PARTICIPANT_SIDE_OPTIONS"
            :key="option.value"
            class="chip"
            :class="{ active: participantSide === option.value }"
            @click="participantSide = option.value"
          >
            {{ option.label }}
          </button>
        </div>
      </div>
      <div class="filter-block">
        <span class="filter-label">Coortes value</span>
        <div class="toolbar-group">
          <button
            class="chip"
            :class="{ active: !selectedValueCohortKeys.length }"
            @click="clearValueCohortSelection"
          >
            todas
          </button>
          <button
            v-for="cohort in VALUE_COHORT_OPTIONS"
            :key="cohort.key"
            class="chip"
            :class="{ active: selectedValueCohortKeys.includes(cohort.key) }"
            @click="toggleValueCohortSelection(cohort.key)"
          >
            {{ cohort.label }}
          </button>
        </div>
      </div>
      <div class="filter-block">
        <span class="filter-label">Linhas value</span>
        <div class="toolbar-group">
          <button
            class="chip"
            :class="{ active: !selectedValueLevelKeys.length }"
            @click="clearValueLevelSelection"
          >
            todas
          </button>
          <button
            v-for="level in VALUE_LEVEL_TYPE_OPTIONS"
            :key="level.key"
            class="chip"
            :class="{ active: selectedValueLevelKeys.includes(level.key) }"
            @click="toggleValueLevelSelection(level.key)"
          >
            {{ level.label }}
          </button>
        </div>
      </div>
      <div class="filter-block">
        <span class="filter-label">Indicador 2</span>
        <div class="toolbar-group">
          <button
            class="chip"
            :class="{ active: !selectedIndicatorMetricKeys.length }"
            @click="clearIndicatorMetricSelection"
          >
            ocultar
          </button>
          <button
            v-for="metric in INDICATOR_METRIC_OPTIONS"
            :key="metric.key"
            class="chip"
            :class="{ active: selectedIndicatorMetricKeys.includes(metric.key) }"
            @click="toggleIndicatorMetricSelection(metric.key)"
          >
            {{ metric.label }}
          </button>
        </div>
      </div>
      <div class="filter-block">
        <span class="filter-label">Coortes ind.</span>
        <div class="toolbar-group">
          <button
            class="chip"
            :class="{ active: !selectedIndicatorCohortKeys.length }"
            @click="clearIndicatorCohortSelection"
          >
            todas
          </button>
          <button
            v-for="cohort in INDICATOR_COHORT_OPTIONS"
            :key="cohort.key"
            class="chip"
            :class="{ active: selectedIndicatorCohortKeys.includes(cohort.key) }"
            @click="toggleIndicatorCohortSelection(cohort.key)"
          >
            {{ cohort.label }}
          </button>
        </div>
      </div>
      <div class="filter-block">
        <span class="filter-label">Histograma</span>
        <div class="toolbar-group">
          <button
            v-for="mode in HISTOGRAM_MODE_OPTIONS"
            :key="mode.key"
            class="chip"
            :class="{ active: selectedHistogramMode === mode.key }"
            @click="selectedHistogramMode = mode.key"
          >
            {{ mode.label }}
          </button>
        </div>
      </div>
      <div class="filter-block">
        <span class="filter-label">Regime 2</span>
        <div class="toolbar-group">
          <button
            v-for="mode in REGIME_CHART_MODE_OPTIONS"
            :key="mode.key"
            class="chip"
            :class="{ active: selectedRegimeChartMode === mode.key }"
            @click="selectedRegimeChartMode = mode.key"
          >
            {{ mode.label }}
          </button>
        </div>
      </div>
      <div class="filter-block broker-filter-block">
        <span class="filter-label">Corretoras</span>
        <div class="toolbar-group broker-chip-group">
          <button
            class="chip"
            :class="{ active: !selectedBrokerKeys.length }"
            @click="clearBrokerSelection"
          >
            todas
          </button>
          <button
            v-for="option in availableBrokerOptions"
            :key="option.key"
            class="chip"
            :class="{ active: selectedBrokerKeys.includes(option.key) }"
            @click="toggleBrokerSelection(option.key)"
          >
            {{ option.label }}
          </button>
        </div>
      </div>
    </section>

    <div v-if="errorMessage" class="error-state">{{ errorMessage }}</div>

    <MacroOperationalSummary
      :win-trade-thermometer="winTradeThermometer"
      :options-flow-alignment-model="optionsFlowAlignmentModel"
      :liquidity-pool-model="liquidityPoolModel"
      :liquidity-intelligence-model="liquidityIntelligenceModel"
    />

    <MacroMarketStructureSummary
      :cross-asset-flow-package="crossAssetFlowPackage"
      :structural-divergence-model="structuralDivergenceModel"
      :continuation-reversal-model="continuationReversalModel"
    />

    <section v-if="quickCharts.length" class="quick-chart-grid">
      <MacroQuickChartCard v-for="asset in quickCharts" :key="asset.key" :asset="asset" />
    </section>
    <section v-else-if="!loading && !errorMessage" class="empty-state">
      Nenhum candle intraday disponivel ainda.
    </section>
  </div>
</template>

<script setup>
import MacroQuickChartCard from './MacroQuickChartCard.vue'
import { createMacroHeatmapControls } from '../controls'
import { createMacroChartFlow } from '../chartFlow'
import { createMacroChartMetrics } from '../chartMetrics'
import { createMacroChartAnnotations } from '../chartAnnotations'
import { MACRO_HEATMAP_CONTEXT } from '../context'
import { computed, onBeforeUnmount, onMounted, provide, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AquilesBrand from '@/components/AquilesBrand.vue'
import MacroMarketStructureSummary from './MacroMarketStructureSummary.vue'
import MacroOperationalSummary from './MacroOperationalSummary.vue'
import {
  getLatestIntradayCorrelationHistory,
  getLatestOptionsHeatmapContext,
  getParticipantHeatmap,
  hardRefreshOptionsBase,
} from '../api'
import {
  formatCompactFloat,
  formatPressureScore,
  formatPrice,
  formatSignedBps,
  formatSignedFloat,
  formatSignedPoints,
  formatSignedQuantity,
  toNumber,
} from '@/utils/marketFormatters'
import {
  formatBiasLabel,
  formatCurveAbsoluteShape,
  formatCurveAngle,
  formatCurveMacroRegime,
  formatCurvePercent,
  formatCurveProbability,
  formatCurveShapeLabel,
  getCurveRegimeRanking,
} from '../models/macroCurve'
import {
  buildOptionsContextFallbackPanel,
  normalizeHeatmapPayload,
} from '../models/heatmapPayload'
import {
  formatTime,
  formatAxisTime,
  scopeSamplesToTradingSession,
  clamp,
  formatImplicitSentiment,
  fairValueSentimentClass,
  fairValueGaugeClass,
  buildCurveVisualization,
  formatFlexibleConfidence,
  getFairValueLegRanking,
  getFairValueShadowRanking,
  getStableQualityWindowSamples,
  buildStableLegMap,
  buildQualityPulse,
  buildQualityHistory,
  buildIntradayCorrelationHistoryPanel,
  buildCapturedFactorHistoryPanel,
  getFairValueShadowHaircutPoints,
  getFairValueGrossGap,
  getFairValueNetGap,
  getFairValueFollowThroughStateLabel,
  getFairValueCompositeRegimeLabel,
  getFairValueLocalAcceptanceLabel,
  buildFairValueSupportBalanceCommentary,
  buildFairValuePriceDriverCommentary,
  buildFairValueCompositeRegimeCommentary,
  buildFairValueLocalConfirmationCommentary,
  buildFairValueModelCommentary,
  buildFairValueReactionCommentary,
  buildFairValueConvergenceCommentary,
  buildFairValueCurveDeskCommentary,
  buildFairValueShadowCommentary,
  buildFairValueShadowSectionLead,
  formatValuePosition,
  formatFlowRegimeLabel,
  formatConfidenceScore,
  formatCompactSignedQuantity,
  formatProjectedMove,
  getValueCohortColor,
  getPoolOverlayKey,
  getPoolOverlayMeta,
  getGammaOverlayKey,
  getGammaOverlayMeta,
  getAssetFairValueSummary,
  formatPoolTriggerLabel,
  formatPoolDirectionLabel,
  formatPoolAggregationScopeLabel,
  getValueLevelTypeMeta,
  getIndicatorMetricMeta,
  pressureClass,
  flowRegimeClass,
  formatLevelDefenseStateLabel,
  levelDefenseClass,
  formatConcentrationStateLabel,
  concentrationClass,
  formatLiquidityProviderLabel,
  formatTrapStateLabel,
  formatSqueezeStateLabel,
  formatStopRunStateLabel,
  formatRetailMicrostructureLabel,
  formatLiquidityRegionRoleLabel,
  formatLiquidityPoolStateLabel,
  formatLiquidityPoolTypeLabel,
  formatGammaRoleLabel,
  formatFairValueStateLabel,
  formatLocationLabel,
  liquidityIntelClass,
  liquidityPoolClass,
  formatAnnotationTypeLabel,
  formatAnnotationShortLabel,
  annotationToneClass,
  formatDivergenceStateLabel,
  divergenceClass,
  computeBucketDivergenceMetrics,
  classifyBucketResponse,
  classifyBucketEfficiency,
  resolveBucketValuePosition,
  classifyBucketFlowRegime,
} from '../models/heatmapModels'
import {
  RANGE_OPTIONS,
  TIMEFRAME_OPTIONS,
  PARTICIPANT_SCOPE_OPTIONS,
  PARTICIPANT_SIDE_OPTIONS,
  PRESSURE_COHORTS,
  VALUE_COHORT_OPTIONS,
  VALUE_LEVEL_TYPE_OPTIONS,
  INDICATOR_METRIC_OPTIONS,
  INDICATOR_COHORT_OPTIONS,
  HISTOGRAM_MODE_OPTIONS,
  REGIME_CHART_MODE_OPTIONS,
  CORRELATION_LOOKBACK_OPTIONS,
  CORRELATION_HORIZON_OPTIONS,
  CORRELATION_MODE_OPTIONS,
  CAPTURED_FACTOR_DISPLAY_OPTIONS,
  ANNOTATION_LEGEND_ITEMS,
  POOL_OVERLAY_OPTIONS,
  GAMMA_OVERLAY_OPTIONS,
  FAIR_VALUE_FEATURE_OPTIONS,
  FAIR_VALUE_CORE_LEG_OPTIONS,
  FAIR_VALUE_SHADOW_LEG_OPTIONS,
  FAIR_VALUE_RANKING_WINDOW_OPTIONS,
  FAIR_VALUE_HELP_TEXT,
  CURVE_HELP_TEXT,
} from '../models/config'

const router = useRouter()

const panelData = ref(null)
const loading = ref(false)
const loadingOptionsContext = ref(false)
const loadingIntradayCorrelation = ref(false)
const hardReloadingOptions = ref(false)
const errorMessage = ref('')
const viewportState = ref({})
const hoverState = ref({})
const dragState = ref({})
const participantScope = ref('foreign')
const participantSide = ref('both')
const selectedBrokerKeys = ref([])
const selectedValueCohortKeys = ref([])
const selectedValueLevelKeys = ref([])
const selectedIndicatorMetricKeys = ref(['pressure', 'efficiency'])
const selectedIndicatorCohortKeys = ref([])
const selectedAnnotationTypeKeys = ref([])
const selectedPoolOverlayKeys = ref([])
const poolOverlayEnabled = ref(true)
const selectedGammaOverlayKeys = ref([])
const gammaOverlayEnabled = ref(true)
const fairValueOverlayEnabled = ref(true)
const selectedFairValueFeatureKeys = ref([
  'price',
  'fair_value',
  'legacy_fair_value',
  'legacy_bands',
  'quality_adjusted',
  'bands',
  'quality_ribbon',
  'gamma',
  'distortion',
  'macro_legs',
])
const selectedFairValueCoreLegKeys = ref([
  'rates',
  'curve_medium_long',
  'equity',
  'equity_brazil',
  'credit',
  'credit_brazil',
  'fx',
  'commodities',
  'us_rates',
])
const selectedFairValueShadowLegKeys = ref([
  'credit_shadow',
  'bond_quality',
  'corporate_credit',
  'em_stress',
  'funding',
  'volatility',
  'brazil_relative',
  'sovereign_credit',
])
const expandedFairValueRankingWindowKeys = ref([])
const selectedHistogramMode = ref('off')
const selectedRegimeChartMode = ref('on')
const intradayCorrelationHistory = ref(null)
const correlationLookbackDays = ref(1)
const correlationHorizonMinutes = ref(5)
const selectedCorrelationModes = ref(['pure', 'neural'])
const selectedCorrelationFactorKeys = ref([])
const selectedCapturedFactorKeys = ref([])
const capturedFactorDisplayMode = ref('day_pct')
const capturedFactorFilterText = ref('')
let capturedFactorSelectionTouched = false
let refreshTimer = null
let optionsContextTimer = null
let correlationHistoryTimer = null
let lastOptionsContextLoadedAt = 0
let lastCorrelationLoadedAt = 0
let lastCorrelationRequestKey = ''
let syncingCorrelationSelection = false

const CHART_WIDTH = 920
const CHART_HEIGHT = 300
const PLOT_LEFT = 64
const PLOT_RIGHT = CHART_WIDTH - 20
const PLOT_TOP = 20
const PLOT_BOTTOM = CHART_HEIGHT - 44
const OPTIONS_CONTEXT_REFRESH_MS = 5 * 60 * 1000
const INTRADAY_CORRELATION_REFRESH_MS = 5 * 60 * 1000
const timestampLabel = computed(() => {
  const value = panelData.value?.generated_at
  if (!value) return '--'
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return '--'
  return dt.toLocaleString('pt-BR', {
    hour12: false,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
})

const assetCount = computed(() => {
  const assets = panelData.value?.assets
  return Array.isArray(assets) ? assets.length : 0
})

const crossAssetFlowPackage = computed(() => (
  panelData.value?.cross_asset_flow_package && typeof panelData.value.cross_asset_flow_package === 'object'
    ? panelData.value.cross_asset_flow_package
    : null
))

const structuralDivergenceModel = computed(() => (
  panelData.value?.structural_divergence_model && typeof panelData.value.structural_divergence_model === 'object'
    ? panelData.value.structural_divergence_model
    : null
))

const continuationReversalModel = computed(() => (
  panelData.value?.continuation_reversal_model && typeof panelData.value.continuation_reversal_model === 'object'
    ? panelData.value.continuation_reversal_model
    : null
))

const winTradeThermometer = computed(() => (
  panelData.value?.win_trade_thermometer && typeof panelData.value.win_trade_thermometer === 'object'
    ? panelData.value.win_trade_thermometer
    : null
))

const liquidityIntelligenceModel = computed(() => (
  panelData.value?.liquidity_intelligence_model && typeof panelData.value.liquidity_intelligence_model === 'object'
    ? panelData.value.liquidity_intelligence_model
    : null
))

const liquidityPoolModel = computed(() => (
  panelData.value?.liquidity_pool_model && typeof panelData.value.liquidity_pool_model === 'object'
    ? panelData.value.liquidity_pool_model
    : null
))

const intradayCorrelationHistoryPanel = computed(() => (
  buildIntradayCorrelationHistoryPanel(intradayCorrelationHistory.value, {
    loading: loadingIntradayCorrelation.value,
    selectedModes: selectedCorrelationModes.value,
  })
))

const optionsFlowAlignmentModel = computed(() => (
  panelData.value?.options_flow_alignment_model && typeof panelData.value.options_flow_alignment_model === 'object'
    ? panelData.value.options_flow_alignment_model
    : null
))

const macroNewsTimeline = computed(() => (
  Array.isArray(panelData.value?.news_thermometer_context?.timeline)
    ? panelData.value.news_thermometer_context.timeline
    : []
))

const normalizedAssets = computed(() => {
  const assets = panelData.value?.assets
  return Array.isArray(assets) ? assets : []
})

const currentWinAsset = computed(() => (
  normalizedAssets.value.find((asset) => asset?.key === 'win') || null
))

const capturedFactorHistoryPanel = computed(() => (
  buildCapturedFactorHistoryPanel(currentWinAsset.value, intradayCorrelationHistory.value, {
    displayMode: capturedFactorDisplayMode.value,
    filterText: capturedFactorFilterText.value,
    selectedFactorKeys: selectedCapturedFactorKeys.value,
  })
))

const selectedScopeLabel = computed(() => (
  PARTICIPANT_SCOPE_OPTIONS.find((option) => option.value === participantScope.value)?.label || 'estrangeiro'
))

const selectedSideLabel = computed(() => (
  PARTICIPANT_SIDE_OPTIONS.find((option) => option.value === participantSide.value)?.label || 'os dois'
))

const {
    availableBrokerOptions, getBrokerFilterKey, matchesBrokerSelection, clearBrokerSelection, toggleBrokerSelection, clearValueCohortSelection, toggleValueCohortSelection, clearValueLevelSelection,
    toggleValueLevelSelection, clearIndicatorMetricSelection, toggleIndicatorMetricSelection, clearIndicatorCohortSelection, toggleIndicatorCohortSelection, clearAnnotationTypeSelection, toggleAnnotationTypeSelection, clearPoolOverlaySelection,
    disablePoolOverlay, togglePoolOverlaySelection, clearGammaOverlaySelection, disableGammaOverlay, toggleGammaOverlaySelection, clearFairValueFeatureSelection, toggleFairValueFeatureSelection, clearFairValueCoreLegSelection,
    toggleFairValueCoreLegSelection, clearFairValueShadowLegSelection, toggleFairValueShadowLegSelection, toggleFairValueRankingWindow, getRangeKey, getTimeframeMinutes, getRangeOption, getHover,
    clampTagX, ensureViewport, setRange, setTimeframe, shiftWindow, resetWindow, stopDrag, handlePointerLeave,
    startDrag,
} = createMacroHeatmapControls({
    FAIR_VALUE_FEATURE_OPTIONS, PLOT_LEFT, PLOT_RIGHT, RANGE_OPTIONS, capturedFactorHistoryPanel, capturedFactorSelectionTouched, clamp, computed,
    dragState, expandedFairValueRankingWindowKeys, gammaOverlayEnabled, hoverState, matchesParticipantScope, normalizedAssets, participantScope, poolOverlayEnabled,
    selectedAnnotationTypeKeys, selectedBrokerKeys, selectedCapturedFactorKeys, selectedFairValueCoreLegKeys, selectedFairValueFeatureKeys, selectedFairValueShadowLegKeys, selectedGammaOverlayKeys, selectedIndicatorCohortKeys,
    selectedIndicatorMetricKeys, selectedPoolOverlayKeys, selectedValueCohortKeys, selectedValueLevelKeys, viewportState, watch,
})

const {
    floorBucketTs, toIso, aggregateCandles, classifyExecutionHint, resolveHeatAnchorPrice, matchesParticipantScope, matchesParticipantSide, buildScopedFlowSummary,
    getDisplayFlowSummary, buildFlowMap,
} = createMacroChartFlow({
    clamp, formatAxisTime, getHover, matchesBrokerSelection, participantScope, participantSide, selectedBrokerKeys, toNumber,
})

const {
    computeBucketIndicatorMetrics, computeBucketConcentrationMetrics, collectAnnotationPlayers, summarizeAnnotationPlayers,
} = createMacroChartMetrics({
    PRESSURE_COHORTS, clamp, classifyBucketEfficiency, classifyBucketResponse, formatSignedQuantity, toNumber,
})

const {
    resolveNewsEventForTs, buildLiquidityAnnotations,
} = createMacroChartAnnotations({
    clamp, classifyBucketFlowRegime, collectAnnotationPlayers, computeBucketConcentrationMetrics, computeBucketDivergenceMetrics, formatAnnotationShortLabel, formatAnnotationTypeLabel, formatDivergenceStateLabel,
    formatLevelDefenseStateLabel, formatPressureScore, resolveBucketValuePosition, summarizeAnnotationPlayers, toNumber,
})

const quickCharts = computed(() => {
  return normalizedAssets.value.map((asset) => {
    const rawCandles = (asset.candles_1m || [])
      .map((candle) => ({
        time: candle.time,
        ts: new Date(candle.time).getTime(),
        open: toNumber(candle.open),
        high: toNumber(candle.high),
        low: toNumber(candle.low),
        close: toNumber(candle.close),
        volume: toNumber(candle.volume),
      }))
      .filter((candle) => Number.isFinite(candle.ts))
      .sort((a, b) => a.ts - b.ts)
    const timeframeMinutes = getTimeframeMinutes(asset.key)
    const candles = aggregateCandles(rawCandles, timeframeMinutes)
    const flowMap = buildFlowMap(asset, candles, timeframeMinutes)

    const plotWidth = PLOT_RIGHT - PLOT_LEFT
    const plotHeight = PLOT_BOTTOM - PLOT_TOP
    const minTs = candles.length ? candles[0].ts : Date.now()
    const maxTs = candles.length ? candles[candles.length - 1].ts : Date.now()
    const totalSpan = Math.max(maxTs - minTs, 60 * 1000)

    const state = viewportState.value[asset.key] || { rangeKey: 'day', endTs: maxTs }
    const range = getRangeOption(state.rangeKey)
    const requestedSpan = range.minutes == null ? totalSpan : Math.max(range.minutes * 60 * 1000, 5 * 60 * 1000)
    const visibleMaxTs = range.minutes == null ? maxTs : clamp(state.endTs || maxTs, minTs + requestedSpan, maxTs)
    const visibleMinTs = range.minutes == null ? minTs : Math.max(minTs, visibleMaxTs - requestedSpan)
    const visibleSpan = Math.max(visibleMaxTs - visibleMinTs, 60 * 1000)

    const visibleCandles = candles.filter((candle) => candle.ts >= visibleMinTs && candle.ts <= visibleMaxTs)
    const chartCandlesRaw = visibleCandles.length ? visibleCandles : candles.slice(-1)

    const activeValueCohorts = new Set(
      selectedValueCohortKeys.value.length
        ? selectedValueCohortKeys.value
        : VALUE_COHORT_OPTIONS.map((option) => option.key),
    )
    const activeValueLevels = new Set(
      selectedValueLevelKeys.value.length
        ? selectedValueLevelKeys.value
        : VALUE_LEVEL_TYPE_OPTIONS.map((option) => option.key),
    )
    const activePoolOverlays = new Set(
      !poolOverlayEnabled.value
        ? []
        : selectedPoolOverlayKeys.value.length
          ? selectedPoolOverlayKeys.value
          : POOL_OVERLAY_OPTIONS.map((option) => option.key),
    )
    const activeGammaOverlays = new Set(
      !gammaOverlayEnabled.value
        ? []
        : selectedGammaOverlayKeys.value.length
          ? selectedGammaOverlayKeys.value
          : GAMMA_OVERLAY_OPTIONS.map((option) => option.key),
    )
    const activeFairValueFeatures = new Set(
      selectedFairValueFeatureKeys.value,
    )
    const activeFairValueCoreLegs = new Set(selectedFairValueCoreLegKeys.value)
    const activeFairValueShadowLegs = new Set(selectedFairValueShadowLegKeys.value)
    const rawValueLevelLines = []
    for (const cohort of VALUE_COHORT_OPTIONS) {
      if (!activeValueCohorts.has(cohort.key)) continue
      const cohortValue = asset?.cohort_value_map?.cohorts?.[cohort.key]
      if (!cohortValue) continue
      for (const levelKey of activeValueLevels) {
        const price = toNumber(cohortValue?.[levelKey])
        if (!Number.isFinite(price)) continue
        const meta = getValueLevelTypeMeta(levelKey)
        rawValueLevelLines.push({
          key: `${asset.key}-${cohort.key}-${levelKey}`,
          cohortKey: cohort.key,
          cohortLabel: cohort.label,
          levelKey,
          levelLabel: meta.label,
          shortLabel: `${cohort.label.toUpperCase()} ${meta.label}`,
          price,
          color: getValueCohortColor(cohort.key),
          dashArray: meta.dashArray,
          strokeWidth: meta.strokeWidth,
        })
      }
    }

    const liquidityPoolWindow = (
      (Array.isArray(asset?.liquidity_pools?.windows)
        ? asset.liquidity_pools.windows.find((window) => Number(window?.minutes) === timeframeMinutes)
        : null)
      || asset?.liquidity_pools?.primary
      || null
    )
    const rawLiquidityPoolBands = []
    for (const pool of (liquidityPoolWindow?.pools || [])) {
      const overlayKey = getPoolOverlayKey(pool?.pool_type)
      if (!activePoolOverlays.has(overlayKey)) continue
      const bandLow = toNumber(pool?.band_low)
      const bandHigh = toNumber(pool?.band_high)
      const price = toNumber(pool?.price)
      if (!Number.isFinite(bandLow) || !Number.isFinite(bandHigh) || !Number.isFinite(price)) continue
      const meta = getPoolOverlayMeta(pool?.pool_type)
      rawLiquidityPoolBands.push({
        key: `${asset.key}-pool-band-${overlayKey}-${pool.cohort}-${price}`,
        overlayKey,
        poolType: pool?.pool_type,
        shortLabel: meta.shortLabel,
        fill: meta.fill,
        stroke: meta.stroke,
        price,
        bandLow,
        bandHigh,
        cascadeProbability: toNumber(pool?.cascade_probability) || 0,
        stopContracts: toNumber(pool?.estimated_stop_closure_contracts) || 0,
        openContracts: toNumber(pool?.synthetic_open_inventory_contracts) || 0,
      })
    }

    const rawGammaRegions = asset.key === 'win'
      ? [
        ...((asset?.gamma_context?.regions || []).map((region) => ({ ...region, kind: 'strike_region' }))),
        ...((asset?.gamma_context?.special_regions || []).map((region) => ({ ...region, kind: 'special_region' }))),
      ]
        .filter((region) => activeGammaOverlays.has(getGammaOverlayKey(region)))
        .map((region, index) => {
          const meta = getGammaOverlayMeta(region)
          const price = toNumber(region?.price)
          const bandLow = Number.isFinite(toNumber(region?.band_low)) ? toNumber(region?.band_low) : price
          const bandHigh = Number.isFinite(toNumber(region?.band_high)) ? toNumber(region?.band_high) : price
          if (!Number.isFinite(price) || !Number.isFinite(bandLow) || !Number.isFinite(bandHigh)) return null
          return {
            key: `${asset.key}-gamma-${region.region_key || index}`,
            regionKey: region.region_key || `${index}`,
            symbol: region.symbol || meta.shortLabel,
            shortLabel: region.symbol || meta.shortLabel,
            displayLabel: region.display_label || region.short_label || meta.label,
            role: region.role || region.region_type,
            kind: region.kind,
            fill: meta.color,
            stroke: meta.color,
            dashArray: region.kind === 'special_region' ? '7 5' : '0',
            price,
            bandLow: Math.min(bandLow, bandHigh),
            bandHigh: Math.max(bandLow, bandHigh),
            description: region.description,
            commentary: region.commentary,
            openInterestTotal: toNumber(region.open_interest_total) || 0,
            gexNotionalFutureNet: toNumber(region.gex_notional_future_net) || 0,
            relevanceScore: toNumber(region.relevance_score) || 0,
            distanceToPricePoints: toNumber(region.distance_to_price_points),
            color: meta.color,
          }
        })
        .filter(Boolean)
      : []

    const aggregateFairValueSamplesByMinute = (samples) => {
      if (!Array.isArray(samples) || !samples.length) return []
      const minuteBuckets = new Map()
      samples
        .filter((sample) => Number.isFinite(sample?.ts))
        .sort((left, right) => left.ts - right.ts)
        .forEach((sample) => {
          const minuteBucketTs = Math.floor(sample.ts / 60000) * 60000
          const previous = minuteBuckets.get(minuteBucketTs)
          if (!previous || sample.ts >= previous.ts) {
            minuteBuckets.set(minuteBucketTs, {
              ...sample,
              minuteBucketTs,
            })
          }
        })
      return [...minuteBuckets.values()]
        .sort((left, right) => left.ts - right.ts)
        .map((sample, index) => ({
          ...sample,
          key: `${sample.key}-m${sample.minuteBucketTs || index}`,
        }))
    }

    const rawFairValueSamples = asset.key === 'win'
      ? aggregateFairValueSamplesByMinute(((asset?.fair_value_history?.samples || [])
        .map((sample, index) => ({
          key: `${asset.key}-fv-${index}`,
          ts: new Date(sample?.captured_at || '').getTime(),
          price: toNumber(sample?.fair_value_final_future),
          coreFairValue: toNumber(sample?.core_fair_value_xb1),
          legacyFairValue: toNumber(sample?.legacy_fair_value_xb1)
            ?? toNumber(sample?.legacy_core_fair_value_xb1)
            ?? toNumber(sample?.core_fair_value_xb1),
          qualityAdjustedPrice: toNumber(sample?.quality_adjusted_fair_value_xb1),
          shadowHaircutPoints: toNumber(sample?.shadow_haircut_points),
          bandLow: toNumber(sample?.fair_value_band_low),
          bandHigh: toNumber(sample?.fair_value_band_high),
          legacyBandLow: toNumber(sample?.legacy_fair_value_band_low)
            ?? toNumber(sample?.legacy_band_low)
            ?? toNumber(sample?.fair_value_band_low),
          legacyBandHigh: toNumber(sample?.legacy_fair_value_band_high)
            ?? toNumber(sample?.legacy_band_high)
            ?? toNumber(sample?.fair_value_band_high),
          qualityRibbonLow: toNumber(sample?.quality_ribbon?.lower),
          qualityRibbonHigh: toNumber(sample?.quality_ribbon?.upper),
          qualityRibbonReason: String(sample?.quality_ribbon?.reason || ''),
          currentPrice: toNumber(sample?.current_future_price),
          currentPriceSource: String(sample?.current_price_source || ''),
          mispricingValue: toNumber(sample?.mispricing_value),
          mispricingZscore: toNumber(sample?.mispricing_zscore),
          confidence: toNumber(sample?.confidence),
          riskQualityScore: toNumber(sample?.risk_quality_score),
          implicitSentiment: String(sample?.implicit_sentiment || ''),
          sentimentConfidence: toNumber(sample?.sentiment_confidence),
          coreShadowAlignment: toNumber(sample?.core_shadow_alignment),
          divergenceScore: toNumber(sample?.divergence_score),
          coherenceScore: toNumber(sample?.coherence_score),
          convergenceProbability: toNumber(sample?.convergence_probability),
          regimeBreakProbability: toNumber(sample?.regime_break_probability),
          qualityGauge: toNumber(sample?.quality_gauge),
          curveConditions: sample?.curve_conditions && typeof sample.curve_conditions === 'object'
            ? sample.curve_conditions
            : {},
          modelVersion: String(sample?.fair_value_model_version || 'fair_value_legacy_v1'),
          modelLabel: String(sample?.fair_value_model_label || 'fair value legacy'),
          blockTones: Array.isArray(sample?.block_tones) ? sample.block_tones : [],
          coreLegs: sample?.core_legs && typeof sample.core_legs === 'object' ? sample.core_legs : {},
          shadowLegs: sample?.shadow_legs && typeof sample.shadow_legs === 'object' ? sample.shadow_legs : {},
          rankingUp: Array.isArray(sample?.ranking_up) ? sample.ranking_up : [],
          rankingDown: Array.isArray(sample?.ranking_down) ? sample.ranking_down : [],
          qualityExplanation: sample?.quality_explanation && typeof sample.quality_explanation === 'object'
            ? sample.quality_explanation
            : {},
        }))
        .filter((sample) => Number.isFinite(sample.ts) && Number.isFinite(sample.price))))
      : []

    const rawLivePriceSamples = asset.key === 'win'
      ? aggregateFairValueSamplesByMinute(((asset?.live_capture_history?.snapshots || [])
        .map((snapshot, index) => ({
          key: `${asset.key}-live-px-${index}`,
          ts: new Date(snapshot?.captured_at || '').getTime(),
          currentPrice: toNumber(snapshot?.current_future_price),
          currentPriceSource: String(snapshot?.current_price_source || ''),
        }))
        .filter((sample) => Number.isFinite(sample.ts) && Number.isFinite(sample.currentPrice))))
      : []
    const dayScopedRawFairValueSamples = scopeSamplesToTradingSession(rawFairValueSamples)
    const dayScopedRawLivePriceSamples = scopeSamplesToTradingSession(rawLivePriceSamples)

    const isTrustedFairValuePriceSource = (source) => {
      const normalized = String(source || '')
      return normalized.startsWith('live_reference:excel_fair_value_basket:')
    }
    const isRenderableFairValueLeg = (leg, sample) => {
      if (!leg || typeof leg !== 'object') return false
      if (leg.enabled === false) return false
      const impliedValue = toNumber(leg.implied_fair_value_xb1)
      if (!Number.isFinite(impliedValue)) return false
      const confidence = toNumber(leg.confidence)
      const contribution = toNumber(leg.contribution_points ?? leg.quality_impact)
      const currentPrice = toNumber(sample?.currentPrice)
      const distanceToPrice = Number.isFinite(currentPrice) ? Math.abs(impliedValue - currentPrice) : Infinity
      if (Number.isFinite(contribution) && Math.abs(contribution) < 0.75 && distanceToPrice <= 4) return false
      if (Number.isFinite(confidence) && confidence <= 0.41 && (!Number.isFinite(contribution) || Math.abs(contribution) < 6)) return false
      return true
    }
    const getLegClusterInspection = (sample, legType) => {
      const options = legType === 'shadow' ? FAIR_VALUE_SHADOW_LEG_OPTIONS : FAIR_VALUE_CORE_LEG_OPTIONS
      const legs = legType === 'shadow' ? sample?.shadowLegs : sample?.coreLegs
      const values = options
        .map((option) => toNumber(legs?.[option.key]?.implied_fair_value_xb1))
        .filter((value) => Number.isFinite(value))
      if (values.length < 3) {
        return { suspicious: false, dominantValue: null, dominantShare: 0 }
      }
      const buckets = new Map()
      values.forEach((value) => {
        const rounded = Math.round(value * 10) / 10
        const bucket = buckets.get(rounded) || { value: rounded, count: 0 }
        bucket.count += 1
        buckets.set(rounded, bucket)
      })
      const dominantBucket = [...buckets.values()].sort((left, right) => right.count - left.count)[0]
      const dominantShare = dominantBucket ? dominantBucket.count / values.length : 0
      const referenceCandidates = [
        sample?.currentPrice,
        sample?.coreFairValue,
        sample?.qualityAdjustedPrice,
        sample?.price,
      ].filter((value) => Number.isFinite(value))
      const distanceToReference = referenceCandidates.length && dominantBucket
        ? Math.min(...referenceCandidates.map((reference) => Math.abs(reference - dominantBucket.value)))
        : 0
      return {
        suspicious: dominantShare >= 0.66 && distanceToReference >= 180,
        dominantValue: dominantBucket?.value ?? null,
        dominantShare,
      }
    }
    const currentFairValueSamplesAll = rawFairValueSamples
      .filter((sample) => sample.modelVersion === 'fair_value_ois_v2')
    const stabilizedCurrentFairValueSamplesAll = (() => {
      let lastTrustedLivePrice = null
      const lastGoodCoreLegValues = {}
      const lastGoodShadowLegValues = {}
      return currentFairValueSamplesAll.map((sample) => {
        const trustedPriceSource = isTrustedFairValuePriceSource(sample.currentPriceSource)
        let effectiveCurrentPrice = Number.isFinite(sample.currentPrice) ? sample.currentPrice : null
        if (trustedPriceSource && Number.isFinite(sample.currentPrice)) {
          lastTrustedLivePrice = sample.currentPrice
        } else if (Number.isFinite(lastTrustedLivePrice)) {
          effectiveCurrentPrice = lastTrustedLivePrice
        }
        const sampleWithEffectivePrice = {
          ...sample,
          currentPrice: effectiveCurrentPrice,
        }
        const coreCluster = getLegClusterInspection(sampleWithEffectivePrice, 'core')
        const shadowCluster = getLegClusterInspection(sampleWithEffectivePrice, 'shadow')
        const stabilizedCoreLegs = {}
        FAIR_VALUE_CORE_LEG_OPTIONS.forEach((option) => {
          const leg = sample.coreLegs?.[option.key]
          const rawValue = toNumber(leg?.implied_fair_value_xb1)
          const previousValue = lastGoodCoreLegValues[option.key]
          const shouldCarryForward = (coreCluster.suspicious || !Number.isFinite(rawValue)) && Number.isFinite(previousValue)
          const effectiveValue = shouldCarryForward ? previousValue : rawValue
          if (leg && Number.isFinite(effectiveValue)) {
            stabilizedCoreLegs[option.key] = {
              ...leg,
              implied_fair_value_xb1: effectiveValue,
            }
            lastGoodCoreLegValues[option.key] = effectiveValue
          } else if (leg && Number.isFinite(rawValue)) {
            stabilizedCoreLegs[option.key] = { ...leg }
            lastGoodCoreLegValues[option.key] = rawValue
          } else if (leg) {
            stabilizedCoreLegs[option.key] = { ...leg }
          }
        })
        const stabilizedShadowLegs = {}
        FAIR_VALUE_SHADOW_LEG_OPTIONS.forEach((option) => {
          const leg = sample.shadowLegs?.[option.key]
          const rawValue = toNumber(leg?.implied_fair_value_xb1)
          const previousValue = lastGoodShadowLegValues[option.key]
          const shouldCarryForward = (shadowCluster.suspicious || !Number.isFinite(rawValue)) && Number.isFinite(previousValue)
          const effectiveValue = shouldCarryForward ? previousValue : rawValue
          if (leg && Number.isFinite(effectiveValue)) {
            stabilizedShadowLegs[option.key] = {
              ...leg,
              implied_fair_value_xb1: effectiveValue,
            }
            lastGoodShadowLegValues[option.key] = effectiveValue
          } else if (leg && Number.isFinite(rawValue)) {
            stabilizedShadowLegs[option.key] = { ...leg }
            lastGoodShadowLegValues[option.key] = rawValue
          } else if (leg) {
            stabilizedShadowLegs[option.key] = { ...leg }
          }
        })
        return {
          ...sample,
          currentPrice: effectiveCurrentPrice,
          currentPriceTrusted: trustedPriceSource,
          coreLegs: stabilizedCoreLegs,
          shadowLegs: stabilizedShadowLegs,
          coreLegsSuspicious: coreCluster.suspicious,
          shadowLegsSuspicious: shadowCluster.suspicious,
        }
      })
    })()
    const dayScopedCurrentFairValueSamplesAll = scopeSamplesToTradingSession(stabilizedCurrentFairValueSamplesAll)

    const prices = chartCandlesRaw
      .flatMap((candle) => [candle.open, candle.high, candle.low, candle.close])
      .concat([toNumber(asset.latest_price)])
      .concat(rawValueLevelLines.map((line) => line.price))
      .concat(rawLiquidityPoolBands.flatMap((band) => [band.bandLow, band.bandHigh, band.price]))
      .filter((value) => Number.isFinite(value))

    const rawMinPrice = prices.length ? Math.min(...prices) : 0
    const rawMaxPrice = prices.length ? Math.max(...prices) : 1
    const padding = Math.max((rawMaxPrice - rawMinPrice) * 0.08, Math.abs(rawMaxPrice) * 0.0015 || 1)
    const minPrice = rawMinPrice - padding
    const maxPrice = rawMaxPrice + padding
    const priceSpan = Math.max(maxPrice - minPrice, 0.0001)

    const xFromTs = (ts) => {
      if (!Number.isFinite(ts)) return PLOT_LEFT + plotWidth / 2
      return PLOT_LEFT + ((ts - visibleMinTs) / visibleSpan) * plotWidth
    }
    const yFromPrice = (price) => {
      if (!Number.isFinite(price)) return PLOT_BOTTOM
      return PLOT_BOTTOM - ((price - minPrice) / priceSpan) * plotHeight
    }
    const priceFromY = (y) => {
      const ratio = clamp((PLOT_BOTTOM - y) / plotHeight, 0, 1)
      return minPrice + ratio * priceSpan
    }

    const candleWidth = clamp((plotWidth / Math.max(chartCandlesRaw.length, 18)) * 0.68, 5, 12)
    const chartCandles = chartCandlesRaw.map((candle) => ({
      ...candle,
      x: xFromTs(candle.ts),
      width: candleWidth,
      openY: yFromPrice(candle.open),
      closeY: yFromPrice(candle.close),
      highY: yFromPrice(candle.high),
      lowY: yFromPrice(candle.low),
      direction: candle.close >= candle.open ? 'up' : 'down',
    }))

    const bucketMetricsByCandle = chartCandles.map((candle) => {
      const flowSummary = flowMap.get(String(candle.bucketStartTs || candle.ts))
      return {
        candle,
        flowSummary,
        metrics: computeBucketIndicatorMetrics(flowSummary, candle),
      }
    })

    const activeIndicatorMetrics = selectedIndicatorMetricKeys.value
    const activeIndicatorCohorts = new Set(
      selectedIndicatorCohortKeys.value.length
        ? selectedIndicatorCohortKeys.value
        : INDICATOR_COHORT_OPTIONS.map((option) => option.key),
    )
    const indicatorSeries = []
    if (activeIndicatorMetrics.length) {
      for (const metricKey of activeIndicatorMetrics) {
        const metricMeta = getIndicatorMetricMeta(metricKey)
        for (const cohort of INDICATOR_COHORT_OPTIONS) {
          if (!activeIndicatorCohorts.has(cohort.key)) continue
          const points = bucketMetricsByCandle
            .map((entry) => {
              const value = toNumber(entry.metrics?.[cohort.key]?.[metricKey === 'pressure' ? 'pressureScore' : 'efficiencyScore'])
              if (!Number.isFinite(value)) return null
              return {
                x: entry.candle.x,
                value,
              }
            })
            .filter(Boolean)
          if (!points.length) continue
          indicatorSeries.push({
            key: `${asset.key}-${metricKey}-${cohort.key}`,
            shortLabel: `${cohort.label} ${metricMeta.label}`,
            metricKey,
            cohortKey: cohort.key,
            color: getValueCohortColor(cohort.key),
            dashArray: metricMeta.dashArray,
            opacity: metricMeta.opacity,
            points,
            lastValue: points[points.length - 1]?.value ?? null,
          })
        }
      }
    }

    let regimeChart = {
      width: CHART_WIDTH,
      height: 126,
      plotLeft: PLOT_LEFT,
      plotRight: PLOT_RIGHT,
      plotTop: 12,
      plotBottom: 100,
      yTicks: [],
      series: [],
      hasVisibleLines: false,
    }
    if (selectedRegimeChartMode.value === 'on') {
      const regimePlotLeft = PLOT_LEFT
      const regimePlotRight = PLOT_RIGHT
      const regimePlotTop = 12
      const regimePlotBottom = 100
      const regimeValueToY = (value) => {
        const safe = clamp(toNumber(value) || 0, -100, 100)
        const ratio = (safe + 100) / 200
        return regimePlotBottom - (ratio * (regimePlotBottom - regimePlotTop))
      }
      const regimeSeries = []
      for (const cohort of INDICATOR_COHORT_OPTIONS) {
        if (!activeIndicatorCohorts.has(cohort.key)) continue
        const cohortValue = asset?.cohort_value_map?.cohorts?.[cohort.key]
        const points = bucketMetricsByCandle
          .map((entry) => {
            const regime = classifyBucketFlowRegime(entry.metrics?.[cohort.key], cohortValue, entry.candle)
            if (!regime?.hasSignal) return null
            const score = toNumber(regime?.regimeScore)
            if (!Number.isFinite(score)) return null
            return {
              x: entry.candle.x,
              value: score,
              regimeState: regime.regimeState,
              confidenceScore: regime.confidenceScore,
              rationale: regime.rationale,
            }
          })
          .filter(Boolean)
        if (!points.length) continue
        regimeSeries.push({
          key: `${asset.key}-regime-${cohort.key}`,
          shortLabel: `${cohort.label} regime`,
          cohortKey: cohort.key,
          color: getValueCohortColor(cohort.key),
          points,
          lastValue: points[points.length - 1]?.value ?? null,
          lastState: points[points.length - 1]?.regimeState ?? null,
        })
      }
      regimeChart = {
        width: CHART_WIDTH,
        height: 126,
        plotLeft: regimePlotLeft,
        plotRight: regimePlotRight,
        plotTop: regimePlotTop,
        plotBottom: regimePlotBottom,
        yTicks: [
          { value: -100, label: 'break sell' },
          { value: -50, label: 'abs sell' },
          { value: 0, label: 'neutro' },
          { value: 50, label: 'abs buy' },
          { value: 100, label: 'break buy' },
        ].map((tick) => ({
          ...tick,
          y: regimeValueToY(tick.value),
        })),
        series: regimeSeries.map((series) => ({
          ...series,
          path: series.points
            .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${regimeValueToY(point.value).toFixed(2)}`)
            .join(' '),
        })),
        hasVisibleLines: regimeSeries.length > 0,
      }
    }

    const divergencePlotLeft = PLOT_LEFT
    const divergencePlotRight = PLOT_RIGHT
    const divergencePlotTop = 12
    const divergencePlotBottom = 100
    const divergenceValueToY = (value) => {
      const safe = clamp(toNumber(value) || 0, -100, 100)
      const ratio = (safe + 100) / 200
      return divergencePlotBottom - (ratio * (divergencePlotBottom - divergencePlotTop))
    }
    const bucketDivergenceByCandle = bucketMetricsByCandle.map((entry) => ({
      candle: entry.candle,
      metrics: computeBucketDivergenceMetrics(entry.metrics),
    }))
    const divergenceSeries = [
      {
        key: `${asset.key}-div-alignment`,
        shortLabel: 'alignment',
        color: '#fbbf24',
        dashArray: '0',
        opacity: 0.92,
        points: bucketDivergenceByCandle
          .map((entry) => ({
            x: entry.candle.x,
            value: entry.metrics.alignmentScore,
            state: entry.metrics.state,
          }))
          .filter((point) => Number.isFinite(toNumber(point.value))),
      },
      {
        key: `${asset.key}-div-divergence`,
        shortLabel: 'divergence',
        color: '#f97316',
        dashArray: '7 5',
        opacity: 0.9,
        points: bucketDivergenceByCandle
          .map((entry) => ({
            x: entry.candle.x,
            value: entry.metrics.divergenceScore,
            state: entry.metrics.state,
          }))
          .filter((point) => Number.isFinite(toNumber(point.value))),
      },
    ]
      .filter((series) => series.points.length > 0)
      .map((series) => ({
        ...series,
        lastValue: series.points[series.points.length - 1]?.value ?? null,
        lastState: series.points[series.points.length - 1]?.state ?? null,
        path: series.points
          .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${divergenceValueToY(point.value).toFixed(2)}`)
          .join(' '),
      }))
    const divergenceChart = {
      width: CHART_WIDTH,
      height: 126,
      plotLeft: divergencePlotLeft,
      plotRight: divergencePlotRight,
      plotTop: divergencePlotTop,
      plotBottom: divergencePlotBottom,
      yTicks: [
        { value: -100, label: 'div sell' },
        { value: -50, label: 'sell' },
        { value: 0, label: 'neutro' },
        { value: 50, label: 'buy' },
        { value: 100, label: 'div buy' },
      ].map((tick) => ({
        ...tick,
        y: divergenceValueToY(tick.value),
      })),
      series: divergenceSeries,
      hasVisibleLines: divergenceSeries.length > 0,
    }

    const activeAnnotationTypes = new Set(
      selectedAnnotationTypeKeys.value.length
        ? selectedAnnotationTypeKeys.value
        : ANNOTATION_LEGEND_ITEMS.map((item) => item.type),
    )
    const annotationEvents = bucketMetricsByCandle.flatMap((entry) => (
      buildLiquidityAnnotations(entry, asset, macroNewsTimeline.value).map((annotation, index) => ({
        ...annotation,
        key: `${asset.key}-annot-${entry.candle.bucketStartTs || entry.candle.ts}-${annotation.type}-${index}`,
      }))
    )).filter((annotation) => activeAnnotationTypes.has(annotation.type))
    const annotationMap = new Map()
    for (const annotation of annotationEvents) {
      const key = String(annotation.ts)
      const current = annotationMap.get(key) || []
      current.push(annotation)
      annotationMap.set(key, current)
    }
    const annotationCountsByTs = new Map()
    const annotationMarkers = annotationEvents.map((annotation) => {
      const tsKey = String(annotation.ts)
      const count = annotationCountsByTs.get(tsKey) || 0
      annotationCountsByTs.set(tsKey, count + 1)
      const anchorY = yFromPrice(annotation.anchorPrice)
      const candleForMarker = chartCandles.find((item) => item.ts === annotation.ts) || null
      const candleTopY = candleForMarker ? Math.min(candleForMarker.openY, candleForMarker.closeY, candleForMarker.highY) : anchorY
      const candleBottomY = candleForMarker ? Math.max(candleForMarker.openY, candleForMarker.closeY, candleForMarker.lowY) : anchorY
      const clusterOffsetX = ((count % 3) - 1) * 10
      const clusterRow = Math.floor(count / 3)
      const tone = annotationToneClass(annotation.type)
      let centerY = anchorY
      if (tone === 'sell') {
        centerY = candleTopY - 7 - (clusterRow * 9)
      } else if (tone === 'buy') {
        centerY = candleBottomY + 7 + (clusterRow * 9)
      } else {
        centerY = anchorY + ((clusterRow % 2 === 0 ? 1 : -1) * (6 + clusterRow * 6))
      }
      centerY = clamp(centerY, PLOT_TOP + 8, PLOT_BOTTOM - 8)
      return {
        ...annotation,
        x: annotation.x + clusterOffsetX,
        y: centerY,
        width: 18,
        height: 12,
      }
    })

    let histogramChart = {
      width: CHART_WIDTH,
      height: 126,
      plotLeft: PLOT_LEFT,
      plotRight: PLOT_RIGHT,
      plotTop: 12,
      plotBottom: 100,
      yTicks: [],
      series: [],
      bars: [],
      hasVisibleBars: false,
      zeroY: null,
    }
    if (selectedHistogramMode.value === 'cumulative') {
      const cumulativeSeries = []
      for (const cohort of INDICATOR_COHORT_OPTIONS) {
        if (!activeIndicatorCohorts.has(cohort.key)) continue
        let running = 0
        const points = bucketMetricsByCandle.map((entry) => {
          running += toNumber(entry.metrics?.[cohort.key]?.netQuantity) || 0
          return {
            x: entry.candle.x,
            ts: entry.candle.ts,
            value: running,
          }
        })
        if (!points.length) continue
        cumulativeSeries.push({
          key: `${asset.key}-hist-${cohort.key}`,
          cohortKey: cohort.key,
          shortLabel: `${cohort.label} cum`,
          color: getValueCohortColor(cohort.key),
          points,
          lastValue: points[points.length - 1]?.value ?? null,
        })
      }

      const histogramMaxAbs = Math.max(
        1,
        ...cumulativeSeries.flatMap((series) => series.points.map((point) => Math.abs(point.value))),
      )
      const histogramPlotLeft = PLOT_LEFT
      const histogramPlotRight = PLOT_RIGHT
      const histogramPlotTop = 12
      const histogramPlotBottom = 100
      const histogramValueToY = (value) => {
        const clamped = clamp(toNumber(value) || 0, -histogramMaxAbs, histogramMaxAbs)
        const ratio = (clamped + histogramMaxAbs) / (histogramMaxAbs * 2)
        return histogramPlotBottom - (ratio * (histogramPlotBottom - histogramPlotTop))
      }
      const seriesCount = Math.max(cumulativeSeries.length, 1)
      const zeroY = histogramValueToY(0)
      const barWidth = Math.max(Math.min(candleWidth * 0.42, 8), 3)
      const clusterWidth = barWidth * seriesCount
      const bars = cumulativeSeries.flatMap((series, seriesIndex) => (
        series.points.map((point) => {
          const x = point.x - (clusterWidth / 2) + (seriesIndex * barWidth)
          const y = histogramValueToY(point.value)
          return {
            key: `${series.key}-${point.ts}`,
            x,
            y: Math.min(y, zeroY),
            width: barWidth,
            height: Math.max(Math.abs(zeroY - y), 1.5),
            fill: series.color,
            opacity: 0.34,
          }
        })
      ))
      histogramChart = {
        width: CHART_WIDTH,
        height: 126,
        plotLeft: histogramPlotLeft,
        plotRight: histogramPlotRight,
        plotTop: histogramPlotTop,
        plotBottom: histogramPlotBottom,
        yTicks: [-histogramMaxAbs, -histogramMaxAbs / 2, 0, histogramMaxAbs / 2, histogramMaxAbs].map((value) => ({
          value,
          y: histogramValueToY(value),
          label: formatCompactSignedQuantity(value),
        })),
        series: cumulativeSeries,
        bars,
        hasVisibleBars: cumulativeSeries.length > 0,
        zeroY,
      }
    }

    const visibleParticipantEvents = chartCandles
      .flatMap((candle) => {
        const flowSummary = flowMap.get(String(candle.bucketStartTs || candle.ts))
        const scopedEvents = participantScope.value === 'retail'
          ? (flowSummary?.retailHeatEvents || [])
          : (flowSummary?.foreignHeatEvents || [])
        return scopedEvents
          .filter((event) => matchesBrokerSelection(event, selectedBrokerKeys.value))
          .filter((event) => {
            const delta = toNumber(event.deltaQuantity) || 0
            if (participantSide.value === 'buy') return delta > 0
            if (participantSide.value === 'sell') return delta < 0
            return delta !== 0
          })
          .filter((event) => Number.isFinite(toNumber(event.averagePrice)))
          .map((event, index) => ({
            ...event,
            key: `${asset.key}-${candle.bucketStartTs || candle.ts}-${event.broker_id}-${index}`,
            candle,
          }))
      })

    const maxParticipantDelta = Math.max(
      1,
      ...visibleParticipantEvents.map((event) => Math.abs(toNumber(event.deltaQuantity) || 0)),
    )

    const participantHeatCells = visibleParticipantEvents.map((event) => {
      const absDelta = Math.abs(toNumber(event.deltaQuantity) || 0)
      const intensity = clamp(absDelta / maxParticipantDelta, 0.12, 1)
      const centerX = event.candle.x
      const anchorPrice = resolveHeatAnchorPrice(event, event.candle)
      const centerY = yFromPrice(anchorPrice)
      const candleTopY = Math.min(event.candle.openY, event.candle.closeY, event.candle.highY)
      const candleBottomY = Math.max(event.candle.openY, event.candle.closeY, event.candle.lowY)
      const candleHeight = Math.max(candleBottomY - candleTopY, 0)
      const availableHeight = candleHeight > 0 ? candleHeight : 4
      const desiredHeight = Math.max(availableHeight * (0.42 + intensity * 0.34), 4)
      const cellHeight = candleHeight > 0 ? Math.min(desiredHeight, candleHeight) : desiredHeight
      const unclampedY = centerY - cellHeight / 2
      const minY = candleHeight > 0 ? candleTopY : unclampedY
      const maxY = candleHeight > 0 ? candleBottomY - cellHeight : unclampedY
      const clampedY = clamp(unclampedY, minY, Math.max(minY, maxY))
      return {
        key: event.key,
        x: centerX - Math.max(event.candle.width * 0.6, 5),
        y: clampedY,
        width: Math.max(event.candle.width * 1.2, 10),
        height: cellHeight,
        opacity: 0.12 + intensity * 0.28,
        fill: (toNumber(event.deltaQuantity) || 0) >= 0 ? '#4fc3f7' : '#ff7043',
        anchorPrice,
      }
    })

    const liquidityPoolBands = rawLiquidityPoolBands
      .sort((left, right) => {
        const rightWeight = (right.cascadeProbability || 0) + ((right.stopContracts || 0) / 1000)
        const leftWeight = (left.cascadeProbability || 0) + ((left.stopContracts || 0) / 1000)
        return rightWeight - leftWeight
      })
      .map((band, index) => {
        const yTop = yFromPrice(band.bandHigh)
        const yBottom = yFromPrice(band.bandLow)
        const rawHeight = Math.abs(yBottom - yTop)
        const intensityBoost = clamp(((band.cascadeProbability || 0) / 100) * 8, 0, 8)
        const height = Math.max(rawHeight, 8 + intensityBoost)
        const rawCenterY = (yTop + yBottom) / 2
        const top = clamp(rawCenterY - (height / 2), PLOT_TOP + 2, PLOT_BOTTOM - height - 2)
        const centerY = top + (height / 2)
        const opacity = clamp(0.10 + ((band.cascadeProbability || 0) / 100) * 0.16, 0.10, 0.26)
        return {
          ...band,
          yTop: top,
          yBottom: top + height,
          height,
          centerY,
          opacity,
          strokeOpacity: clamp(opacity + 0.12, 0.22, 0.54),
          lineOpacity: clamp(opacity + 0.14, 0.24, 0.62),
          showTag: index < 6,
        }
      })

    const liquidityPoolLines = liquidityPoolBands
      .slice(0, 6)
      .map((band) => ({
        key: `${band.key}-line`,
        y: band.centerY,
        stroke: band.stroke,
        opacity: clamp((band.lineOpacity || 0.5) + 0.12, 0.45, 0.95),
        label: `${band.shortLabel} ${formatPrice(band.price)}`,
      }))

    const gammaVisibilityPadding = Math.max(priceSpan * 0.18, 220)
    const gammaRegionBands = rawGammaRegions
      .filter((region) => (
        region.bandHigh >= (minPrice - gammaVisibilityPadding)
        && region.bandLow <= (maxPrice + gammaVisibilityPadding)
      ))
      .sort((left, right) => (right.relevanceScore || 0) - (left.relevanceScore || 0))
      .map((region, index) => {
        const yTop = yFromPrice(region.bandHigh)
        const yBottom = yFromPrice(region.bandLow)
        const rawHeight = Math.abs(yBottom - yTop)
        const height = Math.max(rawHeight, region.kind === 'special_region' ? 4 : 7)
        const rawCenterY = (yTop + yBottom) / 2
        const top = clamp(rawCenterY - (height / 2), PLOT_TOP + 2, PLOT_BOTTOM - height - 2)
        return {
          ...region,
          yTop: top,
          height,
          centerY: top + (height / 2),
          opacity: region.kind === 'special_region' ? 0.08 : 0.06,
          lineOpacity: region.kind === 'special_region' ? 0.58 : 0.42,
          showTag: index < 5,
        }
      })

    const gammaCards = gammaRegionBands
      .slice(0, 6)
      .map((region) => ({
        ...region,
      }))

    const fairValueVisibilityPadding = Math.max(priceSpan * 0.15, 180)
    const fairValueLinePoints = fairValueOverlayEnabled.value
      ? dayScopedRawFairValueSamples
        .filter((sample) => sample.ts >= (visibleMinTs - 10 * 60 * 1000) && sample.ts <= (visibleMaxTs + 10 * 60 * 1000))
        .filter((sample) => sample.price >= (minPrice - fairValueVisibilityPadding) && sample.price <= (maxPrice + fairValueVisibilityPadding))
        .map((sample) => ({
          ...sample,
          x: xFromTs(sample.ts),
          y: yFromPrice(sample.price),
        }))
      : []
    const fairValueLine = fairValueLinePoints.length >= 2
      ? {
        path: fairValueLinePoints
          .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
          .join(' '),
        points: fairValueLinePoints,
        stroke: '#fbbf24',
        opacity: 0.72,
        lastY: fairValueLinePoints[fairValueLinePoints.length - 1]?.y ?? null,
      }
      : {
        path: '',
        points: fairValueLinePoints,
        stroke: '#fbbf24',
        opacity: 0.72,
        lastY: fairValueLinePoints[fairValueLinePoints.length - 1]?.y ?? null,
      }

    const sharedTickCount = Math.min(6, Math.max(chartCandles.length, 2))
    const sharedXTicks = Array.from({ length: sharedTickCount }, (_, index) => {
      const ratio = sharedTickCount === 1 ? 0.5 : index / (sharedTickCount - 1)
      const ts = visibleMinTs + visibleSpan * ratio
      return {
        x: xFromTs(ts),
        label: formatAxisTime(new Date(ts).toISOString()),
      }
    })

    let fairValueFeatureChart = {
      available: false,
      width: CHART_WIDTH,
      height: 184,
      plotLeft: PLOT_LEFT,
      plotRight: PLOT_RIGHT,
      plotTop: 12,
      plotBottom: 144,
      yTicks: [],
      xTicks: [],
      pricePath: '',
      fairValuePath: '',
      legacyFairValuePath: '',
      legacyUpperBandPath: '',
      legacyLowerBandPath: '',
      legacyBandAreaPath: '',
      qualityAdjustedPath: '',
      upperBandPath: '',
      lowerBandPath: '',
      bandAreaPath: '',
      qualityRibbonUpperPath: '',
      qualityRibbonLowerPath: '',
      qualityRibbonAreaPath: '',
      gammaMarkers: [],
      distortionBars: [],
      legBars: [],
      legLineSeries: [],
      currentPrice: null,
      currentFairValue: null,
      legacyFairValue: null,
      currentLegacyBandLow: null,
      currentLegacyBandHigh: null,
      currentQualityAdjusted: null,
      currentBandLow: null,
      currentBandHigh: null,
      currentQualityRibbonLow: null,
      currentQualityRibbonHigh: null,
      currentDislocation: null,
      dominantLegLabel: null,
      qualityModel: null,
    }
    if (asset.key === 'win') {
      const fairChartWidth = CHART_WIDTH
      const fairChartHeight = 248
      const fairPlotLeft = PLOT_LEFT
      const fairPlotRight = PLOT_RIGHT
      const fairPlotTop = 12
      const fairPlotBottom = 194
      const fairPlotHeight = fairPlotBottom - fairPlotTop
      const fairPlotWidth = fairPlotRight - fairPlotLeft
      const visibleFairValueSamples = dayScopedRawFairValueSamples
      const visibleLivePriceSamples = dayScopedRawLivePriceSamples
      const visibleCurrentFairValueSamples = dayScopedCurrentFairValueSamplesAll
      const visibleLegacyFairValueSamples = visibleFairValueSamples
        .filter((sample) => (
          Number.isFinite(sample.legacyFairValue)
          || (Number.isFinite(sample.legacyBandLow) && Number.isFinite(sample.legacyBandHigh))
        ))
      const fairChartTsCandidates = [
        ...visibleFairValueSamples.map((sample) => sample.ts),
        ...visibleLivePriceSamples.map((sample) => sample.ts),
        ...visibleCurrentFairValueSamples.map((sample) => sample.ts),
      ].filter((value) => Number.isFinite(value))
      if (!fairChartTsCandidates.length) {
        fairChartTsCandidates.push(...chartCandlesRaw.map((candle) => candle.ts).filter((value) => Number.isFinite(value)))
      }
      const fairVisibleMinTs = fairChartTsCandidates.length ? Math.min(...fairChartTsCandidates) : visibleMinTs
      const fairVisibleMaxTs = fairChartTsCandidates.length ? Math.max(...fairChartTsCandidates) : visibleMaxTs
      const fairVisibleSpan = Math.max(fairVisibleMaxTs - fairVisibleMinTs, 60 * 1000)
      const fairXFromTs = (ts) => {
        if (!Number.isFinite(ts)) return fairPlotLeft + fairPlotWidth / 2
        return fairPlotLeft + ((ts - fairVisibleMinTs) / fairVisibleSpan) * fairPlotWidth
      }
      const fairTickCount = Math.min(6, Math.max(Math.floor(fairVisibleSpan / (30 * 60 * 1000)) + 1, 2))
      const fairXTicks = Array.from({ length: fairTickCount }, (_, index) => {
        const ratio = fairTickCount === 1 ? 0.5 : index / (fairTickCount - 1)
        const ts = fairVisibleMinTs + fairVisibleSpan * ratio
        return {
          x: fairXFromTs(ts),
          label: formatAxisTime(new Date(ts).toISOString()),
        }
      })
      const fairSessionReferencePrices = [
        ...chartCandlesRaw.flatMap((candle) => [candle.open, candle.high, candle.low, candle.close]),
        ...visibleLivePriceSamples.map((sample) => sample.currentPrice),
        ...visibleFairValueSamples.map((sample) => sample.currentPrice),
      ].filter((value) => Number.isFinite(value) && value > 0)
      const fairSessionRefMin = fairSessionReferencePrices.length ? Math.min(...fairSessionReferencePrices) : null
      const fairSessionRefMax = fairSessionReferencePrices.length ? Math.max(...fairSessionReferencePrices) : null
      const fairSessionRefMid = (
        Number.isFinite(fairSessionRefMin) && Number.isFinite(fairSessionRefMax)
          ? (fairSessionRefMin + fairSessionRefMax) / 2
          : null
      )
      const fairSessionAllowedDistance = (
        Number.isFinite(fairSessionRefMin) && Number.isFinite(fairSessionRefMax) && Number.isFinite(fairSessionRefMid)
          ? Math.max((fairSessionRefMax - fairSessionRefMin) * 8, Math.abs(fairSessionRefMid) * 0.18, 4500)
          : Infinity
      )
      const isRenderableFairValuePrice = (value) => {
        if (!Number.isFinite(value) || value <= 0) return false
        if (!Number.isFinite(fairSessionRefMid)) return true
        return Math.abs(value - fairSessionRefMid) <= fairSessionAllowedDistance
      }
      const fvPriceCandidates = []
      if (activeFairValueFeatures.has('price')) {
        fvPriceCandidates.push(...chartCandlesRaw.flatMap((candle) => [candle.open, candle.high, candle.low, candle.close]))
        fvPriceCandidates.push(...visibleLivePriceSamples.map((sample) => sample.currentPrice).filter(isRenderableFairValuePrice))
        fvPriceCandidates.push(...visibleFairValueSamples.map((sample) => sample.currentPrice).filter(isRenderableFairValuePrice))
      }
      if (activeFairValueFeatures.has('fair_value')) {
        fvPriceCandidates.push(...visibleCurrentFairValueSamples.map((sample) => sample.price).filter(isRenderableFairValuePrice))
      }
      if (activeFairValueFeatures.has('legacy_fair_value')) {
        fvPriceCandidates.push(...visibleLegacyFairValueSamples.map((sample) => sample.legacyFairValue).filter(isRenderableFairValuePrice))
      }
      if (activeFairValueFeatures.has('legacy_bands')) {
        fvPriceCandidates.push(
          ...visibleLegacyFairValueSamples.flatMap((sample) => [sample.legacyBandLow, sample.legacyBandHigh]).filter(isRenderableFairValuePrice),
        )
      }
      if (activeFairValueFeatures.has('quality_adjusted')) {
        fvPriceCandidates.push(...visibleCurrentFairValueSamples.map((sample) => sample.qualityAdjustedPrice).filter(isRenderableFairValuePrice))
      }
      if (activeFairValueFeatures.has('bands')) {
        fvPriceCandidates.push(
          ...visibleFairValueSamples.flatMap((sample) => [sample.bandLow, sample.bandHigh]).filter(isRenderableFairValuePrice),
        )
      }
      if (activeFairValueFeatures.has('quality_ribbon')) {
        fvPriceCandidates.push(
          ...visibleCurrentFairValueSamples.flatMap((sample) => [sample.qualityRibbonLow, sample.qualityRibbonHigh]).filter(isRenderableFairValuePrice),
        )
      }
      if (activeFairValueFeatures.has('gamma')) {
        fvPriceCandidates.push(
          ...rawGammaRegions.flatMap((region) => [region.price, region.bandLow, region.bandHigh]).filter(isRenderableFairValuePrice),
        )
      }
      const fairRawMin = fvPriceCandidates.length ? Math.min(...fvPriceCandidates) : minPrice
      const fairRawMax = fvPriceCandidates.length ? Math.max(...fvPriceCandidates) : maxPrice
      const fairPadding = Math.max((fairRawMax - fairRawMin) * 0.12, Math.abs(fairRawMax) * 0.0015 || 1)
      const fairMinPrice = fairRawMin - fairPadding
      const fairMaxPrice = fairRawMax + fairPadding
      const fairPriceSpan = Math.max(fairMaxPrice - fairMinPrice, 0.0001)
      const fairYFromPrice = (price) => {
        if (!Number.isFinite(price)) return fairPlotBottom
        return fairPlotBottom - (((price - fairMinPrice) / fairPriceSpan) * fairPlotHeight)
      }
      const buildLinePath = (points) => (
        points.length >= 2
          ? points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(' ')
          : ''
      )
      const liveFairPriceLinePoints = []
      if (activeFairValueFeatures.has('price')) {
        let lastTrustedLivePrice = null
        let lastSeenPrice = null
        const priceSourceSamples = visibleLivePriceSamples.length
          ? visibleLivePriceSamples
          : visibleCurrentFairValueSamples.length
          ? visibleCurrentFairValueSamples
          : visibleFairValueSamples
        for (const sample of priceSourceSamples) {
          const isTrustedLiveSource = isTrustedFairValuePriceSource(sample?.currentPriceSource)
          if (isTrustedLiveSource && Number.isFinite(sample.currentPrice)) {
            lastTrustedLivePrice = sample.currentPrice
          }
          const effectivePrice = Number.isFinite(sample.currentPrice)
            ? sample.currentPrice
            : (Number.isFinite(lastSeenPrice) ? lastSeenPrice : lastTrustedLivePrice)
          if (!isRenderableFairValuePrice(effectivePrice)) continue
          lastSeenPrice = effectivePrice
          liveFairPriceLinePoints.push({
            x: fairXFromTs(sample.ts),
            y: fairYFromPrice(effectivePrice),
            price: effectivePrice,
            ts: sample.ts,
            source: sample.currentPriceSource,
          })
        }
      }
      const fairPriceLinePoints = liveFairPriceLinePoints.length >= 2
        ? liveFairPriceLinePoints
        : activeFairValueFeatures.has('price')
          ? chartCandlesRaw.map((candle) => ({
            x: fairXFromTs(candle.ts),
            y: fairYFromPrice(candle.close),
            price: candle.close,
            ts: candle.ts,
          }))
          : []
      const fairValueFeaturePoints = activeFairValueFeatures.has('fair_value')
        ? visibleCurrentFairValueSamples
          .filter((sample) => isRenderableFairValuePrice(sample.price))
          .map((sample) => ({
            ...sample,
            x: fairXFromTs(sample.ts),
            y: fairYFromPrice(sample.price),
          }))
        : []
      const legacyFairValueFeaturePoints = activeFairValueFeatures.has('legacy_fair_value')
        ? visibleLegacyFairValueSamples
          .filter((sample) => isRenderableFairValuePrice(sample.legacyFairValue))
          .map((sample) => ({
            ...sample,
            x: fairXFromTs(sample.ts),
            y: fairYFromPrice(sample.legacyFairValue),
          }))
        : []
      const legacyBandPoints = activeFairValueFeatures.has('legacy_bands')
        ? visibleLegacyFairValueSamples
          .filter((sample) => isRenderableFairValuePrice(sample.legacyBandLow) && isRenderableFairValuePrice(sample.legacyBandHigh))
          .map((sample) => ({
            ...sample,
            x: fairXFromTs(sample.ts),
            lowY: fairYFromPrice(sample.legacyBandLow),
            highY: fairYFromPrice(sample.legacyBandHigh),
          }))
        : []
      const qualityAdjustedFeaturePoints = activeFairValueFeatures.has('quality_adjusted')
        ? visibleCurrentFairValueSamples
          .filter((sample) => isRenderableFairValuePrice(sample.qualityAdjustedPrice))
          .map((sample) => ({
            ...sample,
            x: fairXFromTs(sample.ts),
            y: fairYFromPrice(sample.qualityAdjustedPrice),
          }))
        : []
      const bandPoints = activeFairValueFeatures.has('bands')
        ? visibleCurrentFairValueSamples
          .filter((sample) => isRenderableFairValuePrice(sample.bandLow) && isRenderableFairValuePrice(sample.bandHigh))
          .map((sample) => ({
            ...sample,
            x: fairXFromTs(sample.ts),
            lowY: fairYFromPrice(sample.bandLow),
            highY: fairYFromPrice(sample.bandHigh),
          }))
        : []
      const upperBandPath = buildLinePath(bandPoints.map((point) => ({ x: point.x, y: point.highY })))
      const lowerBandPath = buildLinePath(bandPoints.map((point) => ({ x: point.x, y: point.lowY })))
      const bandAreaPath = bandPoints.length >= 2
        ? [
          ...bandPoints.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${point.highY.toFixed(2)}`),
          ...bandPoints.slice().reverse().map((point) => `L ${point.x.toFixed(2)} ${point.lowY.toFixed(2)}`),
          'Z',
        ].join(' ')
        : ''
      const legacyUpperBandPath = buildLinePath(legacyBandPoints.map((point) => ({ x: point.x, y: point.highY })))
      const legacyLowerBandPath = buildLinePath(legacyBandPoints.map((point) => ({ x: point.x, y: point.lowY })))
      const legacyBandAreaPath = legacyBandPoints.length >= 2
        ? [
          ...legacyBandPoints.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${point.highY.toFixed(2)}`),
          ...legacyBandPoints.slice().reverse().map((point) => `L ${point.x.toFixed(2)} ${point.lowY.toFixed(2)}`),
          'Z',
        ].join(' ')
        : ''
      const qualityRibbonPoints = activeFairValueFeatures.has('quality_ribbon')
        ? visibleCurrentFairValueSamples
          .filter((sample) => isRenderableFairValuePrice(sample.qualityRibbonLow) && isRenderableFairValuePrice(sample.qualityRibbonHigh))
          .map((sample) => ({
            ...sample,
            x: fairXFromTs(sample.ts),
            lowY: fairYFromPrice(sample.qualityRibbonLow),
            highY: fairYFromPrice(sample.qualityRibbonHigh),
          }))
        : []
      const qualityRibbonUpperPath = buildLinePath(qualityRibbonPoints.map((point) => ({ x: point.x, y: point.highY })))
      const qualityRibbonLowerPath = buildLinePath(qualityRibbonPoints.map((point) => ({ x: point.x, y: point.lowY })))
      const qualityRibbonAreaPath = qualityRibbonPoints.length >= 2
        ? [
          ...qualityRibbonPoints.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${point.highY.toFixed(2)}`),
          ...qualityRibbonPoints.slice().reverse().map((point) => `L ${point.x.toFixed(2)} ${point.lowY.toFixed(2)}`),
          'Z',
        ].join(' ')
        : ''
      const gammaMarkers = activeFairValueFeatures.has('gamma')
        ? rawGammaRegions
          .filter((region) => region.price >= fairMinPrice && region.price <= fairMaxPrice)
          .slice(0, 8)
          .map((region) => ({
            key: `${asset.key}-fv-gamma-${region.regionKey}`,
            y: fairYFromPrice(region.price),
            color: region.stroke,
            opacity: region.kind === 'special_region' ? 0.48 : 0.34,
            dashArray: region.kind === 'special_region' ? '7 5' : '0',
            label: `${region.shortLabel} ${formatPrice(region.price)}`,
          }))
        : []
      const distortionScale = Math.max(
        1,
        ...visibleFairValueSamples.map((sample) => Math.abs(toNumber(sample.mispricingValue) || 0)),
      )
      const distortionLaneZeroY = fairPlotBottom - 18
      const distortionLaneMaxHeight = 14
      const distortionBars = activeFairValueFeatures.has('distortion')
        ? visibleFairValueSamples
          .filter((sample) => Number.isFinite(sample.mispricingValue))
          .map((sample) => {
            const x = fairXFromTs(sample.ts)
            const magnitude = Math.abs(toNumber(sample.mispricingValue) || 0)
            const ratio = clamp(magnitude / distortionScale, 0, 1)
            const height = Math.max(4, ratio * distortionLaneMaxHeight)
            const isPositive = sample.mispricingValue >= 0
            return {
              key: `${sample.key}-dist`,
              x: x - 2,
              y: isPositive ? distortionLaneZeroY - height : distortionLaneZeroY,
              width: 4,
              height,
              fill: sample.mispricingValue >= 0 ? '#f97316' : '#22c55e',
              opacity: 0.45,
            }
          })
        : []
      const legLaneY = fairPlotBottom - 8
      const legBars = activeFairValueFeatures.has('macro_legs')
        ? visibleFairValueSamples
          .map((sample) => {
            const dominantLeg = Array.isArray(sample.blockTones) ? sample.blockTones[0] : null
            if (!dominantLeg) return null
            const contribution = toNumber(dominantLeg.contribution_points) || 0
            return {
              key: `${sample.key}-leg`,
              x: fairXFromTs(sample.ts) - 3,
              y: legLaneY,
              width: 6,
              height: 6,
              fill: contribution >= 0 ? '#34d399' : '#fb7185',
              opacity: 0.65,
              label: `${dominantLeg.block || 'macro'} ${formatSignedPoints(contribution)}`,
            }
          })
          .filter(Boolean)
        : []
      const legLineSeries = [
        ...FAIR_VALUE_CORE_LEG_OPTIONS
          .filter((option) => activeFairValueCoreLegs.has(option.key))
          .map((option) => {
            const points = visibleCurrentFairValueSamples
              .map((sample) => {
                const leg = sample.coreLegs?.[option.key]
                if (!isRenderableFairValueLeg(leg, sample)) return null
                const value = toNumber(leg?.implied_fair_value_xb1)
                if (!Number.isFinite(value)) return null
                return {
                  x: fairXFromTs(sample.ts),
                  y: fairYFromPrice(value),
                  ts: sample.ts,
                  value,
                }
              })
              .filter(Boolean)
            if (points.length < 2) return null
            return {
              key: `core-${option.key}`,
              label: option.label,
              shortLabel: option.shortLabel,
              description: option.description,
              color: option.color,
              dashArray: '0',
              opacity: 0.42,
              path: buildLinePath(points),
              lastValue: points[points.length - 1]?.value ?? null,
            }
          })
          .filter(Boolean),
        ...FAIR_VALUE_SHADOW_LEG_OPTIONS
          .filter((option) => activeFairValueShadowLegs.has(option.key))
          .map((option) => {
            const points = visibleCurrentFairValueSamples
              .map((sample) => {
                const leg = sample.shadowLegs?.[option.key]
                if (!isRenderableFairValueLeg(leg, sample)) return null
                const value = toNumber(leg?.implied_fair_value_xb1)
                if (!Number.isFinite(value)) return null
                return {
                  x: fairXFromTs(sample.ts),
                  y: fairYFromPrice(value),
                  ts: sample.ts,
                  value,
                }
              })
              .filter(Boolean)
            if (points.length < 2) return null
            return {
              key: `shadow-${option.key}`,
              label: option.label,
              shortLabel: option.shortLabel,
              description: option.description,
              color: option.color,
              dashArray: '5 4',
              opacity: 0.34,
              path: buildLinePath(points),
              lastValue: points[points.length - 1]?.value ?? null,
            }
          })
          .filter(Boolean),
      ]
      const latestCurrentFeatureSample = visibleCurrentFairValueSamples[visibleCurrentFairValueSamples.length - 1]
        || stabilizedCurrentFairValueSamplesAll.slice(-1)[0]
        || null
      const allCurrentQualitySamples = stabilizedCurrentFairValueSamplesAll
      const latestLegacyFeatureSample = visibleLegacyFairValueSamples[visibleLegacyFairValueSamples.length - 1]
        || rawFairValueSamples.filter((sample) => (
          Number.isFinite(sample.legacyFairValue)
          || (Number.isFinite(sample.legacyBandLow) && Number.isFinite(sample.legacyBandHigh))
        )).slice(-1)[0]
        || null
      const latestFeatureSample = latestCurrentFeatureSample || latestLegacyFeatureSample || rawFairValueSamples[rawFairValueSamples.length - 1] || null
      const hasMeaningfulFairValueQuality = (sample) => {
        if (!sample || sample.modelVersion !== 'fair_value_ois_v2') return false
        const rankingItems = [
          ...(Array.isArray(sample.rankingUp) ? sample.rankingUp : []),
          ...(Array.isArray(sample.rankingDown) ? sample.rankingDown : []),
        ]
        if (rankingItems.some((item) => Math.abs(toNumber(item?.contribution_points)) >= 0.5)) return true
        if (Object.values(sample.coreLegs || {}).some((leg) => Math.abs(toNumber(leg?.contribution_points)) >= 0.5)) return true
        if (Object.values(sample.shadowLegs || {}).some((leg) => (
          Math.abs(toNumber(leg?.quality_impact)) >= 0.25
          || Math.abs(toNumber(leg?.band_impact)) >= 0.01
          || Math.abs(toNumber(leg?.convergence_impact)) >= 0.01
        ))) return true
        return false
      }
      const latestQualityPanelSample = [...visibleCurrentFairValueSamples].reverse().find((sample) => hasMeaningfulFairValueQuality(sample))
        || [...allCurrentQualitySamples].reverse().find((sample) => hasMeaningfulFairValueQuality(sample))
        || latestCurrentFeatureSample
        || null
      const stableQualitySamples = getStableQualityWindowSamples(
        allCurrentQualitySamples.filter((sample) => hasMeaningfulFairValueQuality(sample)),
        latestQualityPanelSample?.ts ?? latestCurrentFeatureSample?.ts ?? null,
      )
      const stableCoreLegs = buildStableLegMap(
        stableQualitySamples.length ? stableQualitySamples : [latestQualityPanelSample].filter(Boolean),
        'core',
      )
      const stableShadowLegs = buildStableLegMap(
        stableQualitySamples.length ? stableQualitySamples : [latestQualityPanelSample].filter(Boolean),
        'shadow',
      )
      const qualityPulse = buildQualityPulse(
        stableQualitySamples.length ? stableQualitySamples : [latestQualityPanelSample].filter(Boolean),
      )
      const qualityHistory = buildQualityHistory(
        allCurrentQualitySamples.filter((sample) => hasMeaningfulFairValueQuality(sample)),
        qualityPulse,
      )
      const normalizeQualityRanking = (items, direction, fallbackLegs) => {
        const minContribution = 0.5
        const filtered = (Array.isArray(items) ? items : [])
          .filter((item) => {
            const contribution = toNumber(item?.contribution_points)
            return direction === 'up'
              ? contribution >= minContribution
              : contribution <= -minContribution
          })
          .sort((left, right) => (
            direction === 'up'
              ? toNumber(right?.contribution_points) - toNumber(left?.contribution_points)
              : toNumber(left?.contribution_points) - toNumber(right?.contribution_points)
          ))
          .slice(0, 4)
        if (filtered.length) return filtered
        return Object.values(fallbackLegs || {})
          .filter((leg) => {
            const contribution = toNumber(leg?.contribution_points)
            return direction === 'up'
              ? contribution >= minContribution
              : contribution <= -minContribution
          })
          .sort((left, right) => (
            direction === 'up'
              ? toNumber(right?.contribution_points) - toNumber(left?.contribution_points)
              : toNumber(left?.contribution_points) - toNumber(right?.contribution_points)
          ))
          .slice(0, 4)
      }
      const buildQualityRankingWindow = (windowConfig) => {
        const endTs = latestQualityPanelSample?.ts ?? latestCurrentFeatureSample?.ts ?? null
        if (!Number.isFinite(endTs)) {
          return {
            key: windowConfig.key,
            label: windowConfig.label,
            sampleCount: 0,
            rankingUp: [],
            rankingDown: [],
            topUp: null,
            topDown: null,
          }
        }
        const startTs = Number.isFinite(windowConfig.minutes)
          ? endTs - (windowConfig.minutes * 60 * 1000)
          : -Infinity
        const scopedSamples = allCurrentQualitySamples
          .filter((sample) => Number.isFinite(sample.ts) && sample.ts <= endTs && sample.ts >= startTs)
        const aggregatedLegs = FAIR_VALUE_CORE_LEG_OPTIONS
          .map((option) => {
            const supportingLegs = scopedSamples
              .map((sample) => sample.coreLegs?.[option.key])
              .filter((leg) => Number.isFinite(toNumber(leg?.contribution_points)))
            if (!supportingLegs.length) return null
            const contributionPoints = supportingLegs.reduce((sum, leg) => sum + (toNumber(leg?.contribution_points) || 0), 0) / supportingLegs.length
            const confidence = supportingLegs.reduce((sum, leg) => sum + (toNumber(leg?.confidence) || 0), 0) / supportingLegs.length
            return {
              ...option,
              name: option.key,
              enabled: true,
              confidence,
              contribution_points: contributionPoints,
              direction: contributionPoints > 0 ? 'bullish' : contributionPoints < 0 ? 'bearish' : 'neutral',
            }
          })
          .filter(Boolean)
        const rankingUp = aggregatedLegs
          .filter((leg) => (toNumber(leg?.contribution_points) || 0) >= 0.5)
          .sort((left, right) => (toNumber(right?.contribution_points) || 0) - (toNumber(left?.contribution_points) || 0))
          .slice(0, 4)
        const rankingDown = aggregatedLegs
          .filter((leg) => (toNumber(leg?.contribution_points) || 0) <= -0.5)
          .sort((left, right) => (toNumber(left?.contribution_points) || 0) - (toNumber(right?.contribution_points) || 0))
          .slice(0, 4)
        return {
          key: windowConfig.key,
          label: windowConfig.label,
          sampleCount: scopedSamples.length,
          rankingUp,
          rankingDown,
          topUp: rankingUp[0] || null,
          topDown: rankingDown[0] || null,
        }
      }
      const rankingWindows = FAIR_VALUE_RANKING_WINDOW_OPTIONS.map((windowConfig) => buildQualityRankingWindow(windowConfig))
      const dominantLegLabel = Array.isArray(latestFeatureSample?.blockTones) && latestFeatureSample.blockTones[0]
        ? `${latestFeatureSample.blockTones[0].block || 'macro'} ${formatSignedPoints(latestFeatureSample.blockTones[0].contribution_points)}`
        : null
      const qualityModel = latestQualityPanelSample
        ? {
          implicitSentiment: latestQualityPanelSample.implicitSentiment,
          sentimentConfidence: latestQualityPanelSample.sentimentConfidence,
          confidence: latestQualityPanelSample.confidence,
          riskQualityScore: latestQualityPanelSample.riskQualityScore,
          qualityGauge: latestQualityPanelSample.qualityGauge,
          coreShadowAlignment: latestQualityPanelSample.coreShadowAlignment,
          divergenceScore: latestQualityPanelSample.divergenceScore,
          coherenceScore: latestQualityPanelSample.coherenceScore,
          shadowHaircutPoints: latestQualityPanelSample.shadowHaircutPoints,
          convergenceProbability: latestQualityPanelSample.convergenceProbability,
          regimeBreakProbability: latestQualityPanelSample.regimeBreakProbability,
          qualityRibbonReason: latestQualityPanelSample.qualityRibbonReason,
          curveConditions: latestQualityPanelSample.curveConditions || {},
          rankingUp: normalizeQualityRanking(latestQualityPanelSample.rankingUp, 'up', stableCoreLegs),
          rankingDown: normalizeQualityRanking(latestQualityPanelSample.rankingDown, 'down', stableCoreLegs),
          rankingWindows,
          explanation: latestQualityPanelSample.qualityExplanation || {},
          coreLegs: Object.keys(stableCoreLegs).length ? stableCoreLegs : (latestQualityPanelSample.coreLegs || {}),
          shadowLegs: Object.keys(stableShadowLegs).length ? stableShadowLegs : (latestQualityPanelSample.shadowLegs || {}),
          qualityPulse,
          qualityHistory,
        }
        : null
      fairValueFeatureChart = {
        available: fairPriceLinePoints.length > 0
          || fairValueFeaturePoints.length > 0
          || legacyFairValueFeaturePoints.length > 0
          || qualityAdjustedFeaturePoints.length > 0,
        width: fairChartWidth,
        height: fairChartHeight,
        plotLeft: fairPlotLeft,
        plotRight: fairPlotRight,
        plotTop: fairPlotTop,
        plotBottom: fairPlotBottom,
        yTicks: Array.from({ length: 5 }, (_, index) => {
          const ratio = index / 4
          const value = fairMaxPrice - fairPriceSpan * ratio
          return {
            value,
            y: fairYFromPrice(value),
            label: formatPrice(value),
          }
        }),
        xTicks: fairXTicks,
        pricePath: buildLinePath(fairPriceLinePoints),
        fairValuePath: buildLinePath(fairValueFeaturePoints),
        legacyFairValuePath: buildLinePath(legacyFairValueFeaturePoints),
        legacyUpperBandPath,
        legacyLowerBandPath,
        legacyBandAreaPath,
        qualityAdjustedPath: buildLinePath(qualityAdjustedFeaturePoints),
        upperBandPath,
        lowerBandPath,
        bandAreaPath,
        qualityRibbonUpperPath,
        qualityRibbonLowerPath,
        qualityRibbonAreaPath,
        gammaMarkers,
        distortionBars,
        legBars,
        legLineSeries,
        currentPrice: liveFairPriceLinePoints[liveFairPriceLinePoints.length - 1]?.price
          ?? latestCurrentFeatureSample?.currentPrice
          ?? latestFeatureSample?.currentPrice
          ?? fairPriceLinePoints[fairPriceLinePoints.length - 1]?.price
          ?? toNumber(asset.latest_price),
        currentFairValue: latestCurrentFeatureSample?.price ?? latestFeatureSample?.price ?? null,
        legacyFairValue: latestLegacyFeatureSample?.legacyFairValue ?? null,
        currentLegacyBandLow: latestLegacyFeatureSample?.legacyBandLow ?? null,
        currentLegacyBandHigh: latestLegacyFeatureSample?.legacyBandHigh ?? null,
        currentQualityAdjusted: latestCurrentFeatureSample?.qualityAdjustedPrice ?? null,
        currentBandLow: latestFeatureSample?.bandLow ?? null,
        currentBandHigh: latestFeatureSample?.bandHigh ?? null,
        currentQualityRibbonLow: latestCurrentFeatureSample?.qualityRibbonLow ?? null,
        currentQualityRibbonHigh: latestCurrentFeatureSample?.qualityRibbonHigh ?? null,
        currentDislocation: latestFeatureSample?.mispricingValue ?? null,
        dominantLegLabel,
        qualityModel,
      }
    }

    const liquidityPoolCards = (liquidityPoolWindow?.pools || [])
      .filter((pool) => activePoolOverlays.has(getPoolOverlayKey(pool?.pool_type)))
      .map((pool) => {
        const meta = getPoolOverlayMeta(pool?.pool_type)
        const primaryPool = asset?.liquidity_pools?.primary || {}
        const liquidityPrimary = asset?.liquidity_intelligence?.primary || {}
        const currentPrice = toNumber(asset?.latest_price) || toNumber(primaryPool?.current_price) || toNumber(pool?.price) || 0
        const bandLow = toNumber(pool?.band_low) || toNumber(pool?.price) || 0
        const bandHigh = toNumber(pool?.band_high) || toNumber(pool?.price) || 0
        const bandWidth = Math.max(Math.abs(bandHigh - bandLow), Math.abs(currentPrice) * 0.00018, 0.01)
        const contractsAtRisk = Math.max(toNumber(primaryPool?.contracts_at_risk_total) || toNumber(primaryPool?.market_inventory_contracts) || 1, 1)
        const closureContracts = Math.max(toNumber(pool?.estimated_stop_closure_contracts) || 0, 0)
        const dayElasticityScore = clamp(
          ((Math.abs(toNumber(primaryPool?.delta_efficiency_score) || 0) * 0.32)
          + ((toNumber(primaryPool?.fragility_score) || 0) * 0.36)
          + ((toNumber(liquidityPrimary?.thin_liquidity_score) || 0) * 0.20)
          + ((toNumber(primaryPool?.breadth_score) || 0) * 0.12)),
          0,
          100,
        )
        const regionElasticityScore = clamp(
          ((toNumber(pool?.unwind_intensity_score) || 0) * 0.44)
          + ((toNumber(pool?.cascade_probability) || 0) * 0.34)
          + ((toNumber(pool?.proximity_score) || 0) * 0.22),
          0,
          100,
        )
        const closureShare = closureContracts / contractsAtRisk
        const projectionBase = 1
          + (dayElasticityScore / 100) * 1.15
          + (regionElasticityScore / 100) * 1.05
          + clamp(closureShare * 3.1, 0, 1.35)
        const projectedStopMove = Math.max(
          bandWidth * projectionBase,
          bandWidth + ((toNumber(pool?.estimated_contracts_to_clear_band) || 0) / Math.max(contractsAtRisk, 1)) * bandWidth * 8,
        )
        const triggerSide = String(pool?.trigger_side || 'neutral')
        const projectedDirection = triggerSide === 'buy' ? 'up' : triggerSide === 'sell' ? 'down' : 'flat'
        const projectedTarget1Price = projectedDirection === 'up'
          ? (toNumber(pool?.price) || currentPrice) + projectedStopMove
          : projectedDirection === 'down'
            ? (toNumber(pool?.price) || currentPrice) - projectedStopMove
            : (toNumber(pool?.price) || currentPrice)
        const projectedTarget2Price = projectedDirection === 'up'
          ? (toNumber(pool?.price) || currentPrice) + (projectedStopMove * 1.75)
          : projectedDirection === 'down'
            ? (toNumber(pool?.price) || currentPrice) - (projectedStopMove * 1.75)
            : (toNumber(pool?.price) || currentPrice)
        const projectionRationale = [
          `elasticidade dia ${Math.round(dayElasticityScore)}%`,
          `elasticidade regiao ${Math.round(regionElasticityScore)}%`,
          `share ${Math.round(closureShare * 100)}%`,
          `move proj ${formatProjectedMove(projectedStopMove)}`,
        ].join(' | ')
        return {
          ...pool,
          shortLabel: meta.shortLabel,
          overlayLabel: meta.label,
          overlayDescription: meta.description,
          stroke: meta.stroke,
          dayElasticityScore,
          regionElasticityScore,
          projectedStopMove,
          projectedDirection,
          projectedTarget1Price,
          projectedTarget2Price,
          projectionRationale,
        }
      })
      .sort((left, right) => {
        const rightWeight = (toNumber(right?.estimated_stop_closure_contracts) || 0) + ((toNumber(right?.cascade_probability) || 0) * 100)
        const leftWeight = (toNumber(left?.estimated_stop_closure_contracts) || 0) + ((toNumber(left?.cascade_probability) || 0) * 100)
        return rightWeight - leftWeight
      })
      .slice(0, 6)

    const valueLevelLines = rawValueLevelLines.map((line) => ({
      ...line,
      y: yFromPrice(line.price),
    }))

    const indicatorPlotLeft = PLOT_LEFT
    const indicatorPlotRight = PLOT_RIGHT
    const indicatorPlotTop = 12
    const indicatorPlotBottom = 92
    const indicatorHeight = 110
    const indicatorValueToY = (value) => {
      const safe = clamp(toNumber(value) || 0, -100, 100)
      const ratio = (safe + 100) / 200
      return indicatorPlotBottom - (ratio * (indicatorPlotBottom - indicatorPlotTop))
    }
    const indicatorYTicks = [-100, -50, 0, 50, 100].map((value) => ({
      value,
      y: indicatorValueToY(value),
      label: formatPressureScore(value),
    }))
    const indicatorSeriesWithPath = indicatorSeries.map((series) => ({
      ...series,
      path: series.points
        .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${indicatorValueToY(point.value).toFixed(2)}`)
        .join(' '),
    }))

    const yTicks = Array.from({ length: 5 }, (_, index) => {
      const ratio = index / 4
      const value = maxPrice - priceSpan * ratio
      return {
        value,
        y: yFromPrice(value),
        label: formatPrice(value),
      }
    })

    const xTicks = sharedXTicks

    return {
      ...asset,
      candles,
      flowMap,
      timeframeMinutes,
      chart: {
        width: CHART_WIDTH,
        height: CHART_HEIGHT,
        plotLeft: PLOT_LEFT,
        plotRight: PLOT_RIGHT,
        plotTop: PLOT_TOP,
        plotBottom: PLOT_BOTTOM,
        visibleMinTs,
        visibleMaxTs,
        visibleSpan,
        candles: chartCandles,
        participantHeatCells,
        gammaRegionBands,
        gammaCards,
        fairValueLine,
        liquidityPoolBands,
        liquidityPoolLines,
        liquidityPoolCards,
        annotationMarkers,
        valueLevelLines,
        yTicks,
        xTicks,
        latestPriceY: yFromPrice(toNumber(asset.latest_price)),
        priceFromY,
      },
      indicatorChart: {
        width: CHART_WIDTH,
        height: indicatorHeight,
        plotLeft: indicatorPlotLeft,
        plotRight: indicatorPlotRight,
        plotTop: indicatorPlotTop,
        plotBottom: indicatorPlotBottom,
        yTicks: indicatorYTicks,
        series: indicatorSeriesWithPath,
        hasVisibleLines: indicatorSeriesWithPath.length > 0,
      },
      fairValueFeatureChart,
      regimeChart,
      divergenceChart,
      annotationMap,
      histogramChart,
    }
  }).filter(Boolean)
})

function handlePointerMove(assetKey, event, asset) {
  const drag = dragState.value[assetKey]
  if (drag) {
    const deltaPixels = event.clientX - drag.startClientX
    const deltaMs = (deltaPixels / Math.max(drag.plotWidth, 1)) * drag.spanMs
    const nextEndTs = clamp(drag.startEndTs - deltaMs, drag.minTs + drag.spanMs, drag.maxTs)
    viewportState.value = {
      ...viewportState.value,
      [assetKey]: {
        ...(viewportState.value[assetKey] || {}),
        endTs: nextEndTs,
      },
    }
    return
  }

  const svg = event.currentTarget
  if (!svg || !asset?.chart?.candles?.length) return
  const rect = svg.getBoundingClientRect()
  if (!rect.width || !rect.height) return

  const x = ((event.clientX - rect.left) / rect.width) * asset.chart.width
  const y = ((event.clientY - rect.top) / rect.height) * asset.chart.height
  const boundedX = clamp(x, asset.chart.plotLeft, asset.chart.plotRight)
  const boundedY = clamp(y, asset.chart.plotTop, asset.chart.plotBottom)
  const ratio = (boundedX - asset.chart.plotLeft) / Math.max(asset.chart.plotRight - asset.chart.plotLeft, 1)
  const hoverTs = asset.chart.visibleMinTs + ratio * asset.chart.visibleSpan
  const candle = [...asset.chart.candles].sort((a, b) => Math.abs(a.ts - hoverTs) - Math.abs(b.ts - hoverTs))[0] || null

  hoverState.value = {
    ...hoverState.value,
    [assetKey]: {
      x: candle?.x ?? boundedX,
      y: boundedY,
      candle,
      flowSummary: asset.flowMap?.get(String(candle?.bucketStartTs || candle?.ts)) || null,
      annotations: asset.annotationMap?.get(String(candle?.bucketStartTs || candle?.ts)) || [],
      priceLabel: formatPrice(asset.chart.priceFromY(boundedY)),
      timeLabel: candle?.bucketLabel || formatAxisTime(new Date(candle?.ts || hoverTs).toISOString()),
      timeFullLabel: candle?.bucketLabel || formatTime(new Date(candle?.ts || hoverTs).toISOString()),
    },
  }
}

function goHome() {
  router.push({ name: 'Home' })
}

function goBack() {
  router.back()
}

async function loadHeatmap(forceReload = false) {
  if (loading.value && !forceReload) return
  loading.value = true
  errorMessage.value = ''

  try {
    const json = await getParticipantHeatmap({ refresh: forceReload })
    if (json && json.success === false) {
      throw new Error(json.error || 'Heatmap backend returned an error.')
    }

    const payload = normalizeHeatmapPayload(json?.data || json || null)
    panelData.value = payload
    if (!payload || !Array.isArray(payload.assets)) {
      errorMessage.value = 'Participant heatmap payload came back empty.'
    } else {
      void loadOptionsHeatmapContext(forceReload, !forceReload)
    }
  } catch (err) {
    errorMessage.value = err?.code === 'ECONNABORTED'
      ? 'Heatmap request timed out after 30s.'
      : (err.message || 'Failed to load participant heatmap.')
    void loadOptionsHeatmapContext(forceReload, false)
  } finally {
    loading.value = false
  }
}

function mergeOptionsHeatmapContext(context) {
  if (!context || typeof context !== 'object') return
  if (!panelData.value) {
    panelData.value = normalizeHeatmapPayload(buildOptionsContextFallbackPanel(context))
    return
  }
  const currentPanel = panelData.value || {}
  const mergedAssets = Array.isArray(currentPanel.assets)
    ? currentPanel.assets.map((asset) => {
      const existingHistory = asset?.fair_value_history && typeof asset.fair_value_history === 'object'
        ? asset.fair_value_history
        : {}
      const incomingHistory = context.fair_value_history && typeof context.fair_value_history === 'object'
        ? context.fair_value_history
        : null
      const mergedHistory = (() => {
        if (!incomingHistory) return asset.fair_value_history
        const mergedByTs = new Map()
        const pushSample = (sample) => {
          const ts = String(sample?.captured_at || '')
          if (!ts) return
          mergedByTs.set(ts, JSON.parse(JSON.stringify(sample)))
        }
        ;((existingHistory.samples || [])).forEach(pushSample)
        ;((incomingHistory.samples || [])).forEach(pushSample)
        const mergedSamples = [...mergedByTs.values()]
          .sort((left, right) => String(left?.captured_at || '').localeCompare(String(right?.captured_at || '')))
        return {
          ...JSON.parse(JSON.stringify(existingHistory || {})),
          ...JSON.parse(JSON.stringify(incomingHistory || {})),
          samples: mergedSamples,
          samples_total: Math.max(
            mergedSamples.length,
            toNumber(existingHistory.samples_total) || 0,
            toNumber(incomingHistory.samples_total) || 0,
          ),
          samples_payload_count: mergedSamples.length,
          latest_sample: mergedSamples[mergedSamples.length - 1]
            || incomingHistory.latest_sample
            || existingHistory.latest_sample
            || null,
        }
      })()
      return {
        ...asset,
        gamma_context: context.gamma_context ? JSON.parse(JSON.stringify(context.gamma_context)) : asset.gamma_context,
        fair_value_history: mergedHistory,
        live_capture_history: context.live_capture_history ? JSON.parse(JSON.stringify(context.live_capture_history)) : asset.live_capture_history,
        options_flow_alignment: currentPanel.options_flow_alignment_model
          ? JSON.parse(JSON.stringify(currentPanel.options_flow_alignment_model))
          : asset.options_flow_alignment,
      }
    })
    : currentPanel.assets

  panelData.value = {
    ...currentPanel,
    options_heatmap_context: context,
    assets: mergedAssets,
  }
}

async function loadOptionsHeatmapContext(forceRefresh = false, skipIfFresh = false) {
  if (loadingOptionsContext.value) return
  if (skipIfFresh && !forceRefresh && lastOptionsContextLoadedAt && (Date.now() - lastOptionsContextLoadedAt) < OPTIONS_CONTEXT_REFRESH_MS) {
    return
  }
  loadingOptionsContext.value = true
  try {
    const response = await getLatestOptionsHeatmapContext({ refresh: forceRefresh })
    const payload = response?.data || null
    if (payload) {
      mergeOptionsHeatmapContext(payload)
      lastOptionsContextLoadedAt = Date.now()
    }
  } catch {
    // Keep the last good fair value/gamma state on screen if the lightweight refresh fails.
  } finally {
    loadingOptionsContext.value = false
  }
}

function correlationRequestKey() {
  return [
    correlationLookbackDays.value,
    correlationHorizonMinutes.value,
    [...selectedCorrelationFactorKeys.value].sort().join(','),
  ].join('|')
}

function silentlySyncCorrelationFactors(nextKeys) {
  syncingCorrelationSelection = true
  selectedCorrelationFactorKeys.value = [...nextKeys]
  window.setTimeout(() => {
    syncingCorrelationSelection = false
  }, 0)
}

async function loadIntradayCorrelationHistory(forceRefresh = false, skipIfFresh = true) {
  if (loadingIntradayCorrelation.value) return
  const requestKey = correlationRequestKey()
  if (
    skipIfFresh
    && !forceRefresh
    && lastCorrelationLoadedAt
    && requestKey === lastCorrelationRequestKey
    && (Date.now() - lastCorrelationLoadedAt) < INTRADAY_CORRELATION_REFRESH_MS
  ) {
    return
  }
  loadingIntradayCorrelation.value = true
  try {
    const response = await getLatestIntradayCorrelationHistory({
      underlying_security: 'IBOVE Index',
      lookback_days: correlationLookbackDays.value,
      horizon_minutes: correlationHorizonMinutes.value,
      factors: selectedCorrelationFactorKeys.value.join(','),
      modes: 'pure,neural',
      refresh: forceRefresh,
    })
    const payload = response?.data || null
    intradayCorrelationHistory.value = payload
    const validFactors = new Set(
      Array.isArray(payload?.available_factors)
        ? payload.available_factors
          .map((item) => String(item?.factor || '').trim())
          .filter(Boolean)
        : [],
    )
    let nextFactors = selectedCorrelationFactorKeys.value.filter((key) => validFactors.has(key))
    if (!nextFactors.length) {
      nextFactors = Array.isArray(payload?.default_factors)
        ? payload.default_factors
          .map((item) => String(item || '').trim())
          .filter((key) => key && validFactors.has(key))
        : []
    }
    if (nextFactors.join(',') !== selectedCorrelationFactorKeys.value.join(',')) {
      silentlySyncCorrelationFactors(nextFactors)
    }
    lastCorrelationLoadedAt = Date.now()
    lastCorrelationRequestKey = requestKey
  } catch {
    // Keep the last good correlation panel on screen if the historical model refresh fails.
  } finally {
    loadingIntradayCorrelation.value = false
  }
}

function setCorrelationLookbackDays(days) {
  const nextValue = Number(days) || 1
  if (correlationLookbackDays.value === nextValue) return
  correlationLookbackDays.value = nextValue
  void loadIntradayCorrelationHistory(false, false)
}

function setCorrelationHorizonMinutes(minutes) {
  const nextValue = Number(minutes) || 1
  if (correlationHorizonMinutes.value === nextValue) return
  correlationHorizonMinutes.value = nextValue
  void loadIntradayCorrelationHistory(false, false)
}

function toggleCorrelationMode(modeKey) {
  const key = String(modeKey || '')
  if (!key) return
  const active = new Set(selectedCorrelationModes.value)
  if (active.has(key)) {
    if (active.size === 1) return
    active.delete(key)
  } else {
    active.add(key)
  }
  selectedCorrelationModes.value = [...active]
}

function toggleCorrelationFactor(factorKey) {
  const key = String(factorKey || '')
  if (!key || syncingCorrelationSelection) return
  const active = new Set(selectedCorrelationFactorKeys.value)
  if (active.has(key)) {
    if (active.size === 1) return
    active.delete(key)
  } else {
    active.add(key)
  }
  selectedCorrelationFactorKeys.value = [...active]
  void loadIntradayCorrelationHistory(false, false)
}

function setCapturedFactorDisplayMode(modeKey) {
  const key = String(modeKey || '').trim()
  if (!key || capturedFactorDisplayMode.value === key) return
  capturedFactorDisplayMode.value = key
}

function toggleCapturedFactorSelection(factorKey) {
  const key = String(factorKey || '').trim()
  if (!key) return
  capturedFactorSelectionTouched = true
  const active = new Set(selectedCapturedFactorKeys.value)
  if (active.has(key)) {
    active.delete(key)
  } else {
    active.add(key)
  }
  selectedCapturedFactorKeys.value = [...active]
}

function selectAllCapturedFactors() {
  const panel = capturedFactorHistoryPanel.value
  if (!panel) return
  capturedFactorSelectionTouched = true
  selectedCapturedFactorKeys.value = panel.availableFactors.map((item) => item.factor)
}

function selectCapturedTopMovers() {
  const panel = capturedFactorHistoryPanel.value
  if (!panel) return
  capturedFactorSelectionTouched = true
  selectedCapturedFactorKeys.value = [...panel.defaultFactors]
}

function clearCapturedFactorSelection() {
  capturedFactorSelectionTouched = true
  selectedCapturedFactorKeys.value = []
}

async function hardReloadOptionsBaseNow() {
  if (hardReloadingOptions.value) return
  hardReloadingOptions.value = true
  errorMessage.value = ''

  try {
    await hardRefreshOptionsBase({
      underlying_security: 'IBOVE Index',
    })
    await loadHeatmap(false)
    await loadOptionsHeatmapContext(true)
    await loadIntradayCorrelationHistory(true, false)
  } catch (err) {
    errorMessage.value = err?.message || 'Falha ao fazer hard reload da base de opcoes.'
  } finally {
    hardReloadingOptions.value = false
  }
}

onMounted(() => {
  void loadHeatmap(false)
  void loadOptionsHeatmapContext(false)
  void loadIntradayCorrelationHistory(false, false)
  refreshTimer = window.setInterval(() => {
    void loadHeatmap(false)
  }, 15000)
  optionsContextTimer = window.setInterval(() => {
    void loadOptionsHeatmapContext(false)
  }, OPTIONS_CONTEXT_REFRESH_MS)
  correlationHistoryTimer = window.setInterval(() => {
    void loadIntradayCorrelationHistory(false, true)
  }, INTRADAY_CORRELATION_REFRESH_MS)
})

onBeforeUnmount(() => {
  if (refreshTimer) {
    window.clearInterval(refreshTimer)
    refreshTimer = null
  }
  if (optionsContextTimer) {
    window.clearInterval(optionsContextTimer)
    optionsContextTimer = null
  }
  if (correlationHistoryTimer) {
    window.clearInterval(correlationHistoryTimer)
    correlationHistoryTimer = null
  }
})
provide(MACRO_HEATMAP_CONTEXT, {
  ANNOTATION_LEGEND_ITEMS, AquilesBrand, CAPTURED_FACTOR_DISPLAY_OPTIONS, CHART_HEIGHT, CHART_WIDTH, CORRELATION_HORIZON_OPTIONS, CORRELATION_LOOKBACK_OPTIONS, CORRELATION_MODE_OPTIONS,
  CURVE_HELP_TEXT, FAIR_VALUE_CORE_LEG_OPTIONS, FAIR_VALUE_FEATURE_OPTIONS, FAIR_VALUE_HELP_TEXT, FAIR_VALUE_RANKING_WINDOW_OPTIONS, FAIR_VALUE_SHADOW_LEG_OPTIONS, GAMMA_OVERLAY_OPTIONS, HISTOGRAM_MODE_OPTIONS,
  INDICATOR_COHORT_OPTIONS, INDICATOR_METRIC_OPTIONS, INTRADAY_CORRELATION_REFRESH_MS, MacroMarketStructureSummary, MacroOperationalSummary, OPTIONS_CONTEXT_REFRESH_MS, PARTICIPANT_SCOPE_OPTIONS, PARTICIPANT_SIDE_OPTIONS,
  PLOT_BOTTOM, PLOT_LEFT, PLOT_RIGHT, PLOT_TOP, POOL_OVERLAY_OPTIONS, PRESSURE_COHORTS, RANGE_OPTIONS, REGIME_CHART_MODE_OPTIONS,
  TIMEFRAME_OPTIONS, VALUE_COHORT_OPTIONS, VALUE_LEVEL_TYPE_OPTIONS, aggregateCandles, annotationToneClass, assetCount, availableBrokerOptions, buildCapturedFactorHistoryPanel,
  buildCurveVisualization, buildFairValueCompositeRegimeCommentary, buildFairValueConvergenceCommentary, buildFairValueCurveDeskCommentary, buildFairValueLocalConfirmationCommentary, buildFairValueModelCommentary, buildFairValuePriceDriverCommentary, buildFairValueReactionCommentary,
  buildFairValueShadowCommentary, buildFairValueShadowSectionLead, buildFairValueSupportBalanceCommentary, buildFlowMap, buildIntradayCorrelationHistoryPanel, buildLiquidityAnnotations, buildOptionsContextFallbackPanel, buildQualityHistory,
  buildQualityPulse, buildScopedFlowSummary, buildStableLegMap, capturedFactorDisplayMode, capturedFactorFilterText, capturedFactorHistoryPanel, capturedFactorSelectionTouched, clamp,
  clampTagX, classifyBucketEfficiency, classifyBucketFlowRegime, classifyBucketResponse, classifyExecutionHint, clearAnnotationTypeSelection, clearBrokerSelection, clearCapturedFactorSelection,
  clearFairValueCoreLegSelection, clearFairValueFeatureSelection, clearFairValueShadowLegSelection, clearGammaOverlaySelection, clearIndicatorCohortSelection, clearIndicatorMetricSelection, clearPoolOverlaySelection, clearValueCohortSelection,
  clearValueLevelSelection, collectAnnotationPlayers, computeBucketConcentrationMetrics, computeBucketDivergenceMetrics, computeBucketIndicatorMetrics, concentrationClass, continuationReversalModel, correlationHistoryTimer,
  correlationHorizonMinutes, correlationLookbackDays, correlationRequestKey, crossAssetFlowPackage, currentWinAsset, disableGammaOverlay, disablePoolOverlay, divergenceClass,
  dragState, ensureViewport, errorMessage, expandedFairValueRankingWindowKeys, fairValueGaugeClass, fairValueOverlayEnabled, fairValueSentimentClass, floorBucketTs,
  flowRegimeClass, formatAnnotationShortLabel, formatAnnotationTypeLabel, formatAxisTime, formatBiasLabel, formatCompactFloat, formatCompactSignedQuantity, formatConcentrationStateLabel,
  formatConfidenceScore, formatCurveAbsoluteShape, formatCurveAngle, formatCurveMacroRegime, formatCurvePercent, formatCurveProbability, formatCurveShapeLabel, formatDivergenceStateLabel,
  formatFairValueStateLabel, formatFlexibleConfidence, formatFlowRegimeLabel, formatGammaRoleLabel, formatImplicitSentiment, formatLevelDefenseStateLabel, formatLiquidityPoolStateLabel, formatLiquidityPoolTypeLabel,
  formatLiquidityProviderLabel, formatLiquidityRegionRoleLabel, formatLocationLabel, formatPoolAggregationScopeLabel, formatPoolDirectionLabel, formatPoolTriggerLabel, formatPressureScore, formatPrice,
  formatProjectedMove, formatRetailMicrostructureLabel, formatSignedBps, formatSignedFloat, formatSignedPoints, formatSignedQuantity, formatSqueezeStateLabel, formatStopRunStateLabel,
  formatTime, formatTrapStateLabel, formatValuePosition, gammaOverlayEnabled, getAssetFairValueSummary, getBrokerFilterKey, getCurveRegimeRanking, getDisplayFlowSummary,
  getFairValueCompositeRegimeLabel, getFairValueFollowThroughStateLabel, getFairValueGrossGap, getFairValueLegRanking, getFairValueLocalAcceptanceLabel, getFairValueNetGap, getFairValueShadowHaircutPoints, getFairValueShadowRanking,
  getGammaOverlayKey, getGammaOverlayMeta, getHover, getIndicatorMetricMeta, getLatestIntradayCorrelationHistory, getLatestOptionsHeatmapContext, getParticipantHeatmap, getPoolOverlayKey,
  getPoolOverlayMeta, getRangeKey, getRangeOption, getStableQualityWindowSamples, getTimeframeMinutes, getValueCohortColor, getValueLevelTypeMeta, goBack,
  goHome, handlePointerLeave, handlePointerMove, hardRefreshOptionsBase, hardReloadOptionsBaseNow, hardReloadingOptions, hoverState, intradayCorrelationHistory,
  intradayCorrelationHistoryPanel, lastCorrelationLoadedAt, lastCorrelationRequestKey, lastOptionsContextLoadedAt, levelDefenseClass, liquidityIntelClass, liquidityIntelligenceModel, liquidityPoolClass,
  liquidityPoolModel, loadHeatmap, loadIntradayCorrelationHistory, loadOptionsHeatmapContext, loading, loadingIntradayCorrelation, loadingOptionsContext, macroNewsTimeline,
  matchesBrokerSelection, matchesParticipantScope, matchesParticipantSide, mergeOptionsHeatmapContext, normalizeHeatmapPayload, normalizedAssets, onBeforeUnmount, optionsContextTimer,
  optionsFlowAlignmentModel, panelData, participantScope, participantSide, poolOverlayEnabled, pressureClass, quickCharts, refreshTimer,
  resetWindow, resolveBucketValuePosition, resolveHeatAnchorPrice, resolveNewsEventForTs, router, scopeSamplesToTradingSession, selectAllCapturedFactors, selectCapturedTopMovers,
  selectedAnnotationTypeKeys, selectedBrokerKeys, selectedCapturedFactorKeys, selectedCorrelationFactorKeys, selectedCorrelationModes, selectedFairValueCoreLegKeys, selectedFairValueFeatureKeys, selectedFairValueShadowLegKeys,
  selectedGammaOverlayKeys, selectedHistogramMode, selectedIndicatorCohortKeys, selectedIndicatorMetricKeys, selectedPoolOverlayKeys, selectedRegimeChartMode, selectedScopeLabel, selectedSideLabel,
  selectedValueCohortKeys, selectedValueLevelKeys, setCapturedFactorDisplayMode, setCorrelationHorizonMinutes, setCorrelationLookbackDays, setRange, setTimeframe, shiftWindow,
  silentlySyncCorrelationFactors, startDrag, stopDrag, structuralDivergenceModel, summarizeAnnotationPlayers, syncingCorrelationSelection, timestampLabel, toIso,
  toNumber, toggleAnnotationTypeSelection, toggleBrokerSelection, toggleCapturedFactorSelection, toggleCorrelationFactor, toggleCorrelationMode, toggleFairValueCoreLegSelection, toggleFairValueFeatureSelection,
  toggleFairValueRankingWindow, toggleFairValueShadowLegSelection, toggleGammaOverlaySelection, toggleIndicatorCohortSelection, toggleIndicatorMetricSelection, togglePoolOverlaySelection, toggleValueCohortSelection, toggleValueLevelSelection,
  useRouter, viewportState, winTradeThermometer,
})
</script>

<style scoped src="./MacroHeatmapView.css"></style>

<template>
  <section v-if="winTradeThermometer?.primary" class="package-strip">
    <div class="pressure-head">
      <div class="pressure-title">
        WIN trade thermometer {{ winTradeThermometer.primary.window_label || winTradeThermometer.primary_window_label || '' }}
      </div>
      <div class="pressure-meta">
        {{ formatTradeSignalLabel(winTradeThermometer.primary.signal) }}
        | {{ formatTradeActionLabel(winTradeThermometer.primary.action) }}
        | {{ formatEntryStyleLabel(winTradeThermometer.primary.entry_style) }}
      </div>
    </div>
    <div class="pressure-window-row">
      <span class="pressure-window-label">leitura dominante</span>
      <span>{{ winTradeThermometer.primary.rationale || '--' }}</span>
    </div>
    <div class="pressure-pill-row">
      <div class="pressure-pill" :class="thermometerClass(winTradeThermometer.primary)">
        <span class="pressure-pill-label">sinal</span>
        <strong>{{ formatTradeSignalLabel(winTradeThermometer.primary.signal) }}</strong>
        <span>{{ formatTradeActionLabel(winTradeThermometer.primary.action) }} | {{ formatEntryStyleLabel(winTradeThermometer.primary.entry_style) }}</span>
      </div>
      <div class="pressure-pill" :class="thermometerClass(winTradeThermometer.primary)">
        <span class="pressure-pill-label">scores</span>
        <strong>dir {{ formatPressureScore(winTradeThermometer.primary.directional_score) }}</strong>
        <span>conv {{ formatConfidenceScore(winTradeThermometer.primary.conviction_score) }} | timing {{ formatConfidenceScore(winTradeThermometer.primary.timing_score) }}</span>
      </div>
      <div class="pressure-pill" :class="riskClass(winTradeThermometer.primary.risk_score)">
        <span class="pressure-pill-label">risco</span>
        <strong>{{ formatConfidenceScore(winTradeThermometer.primary.risk_score) }}</strong>
        <span>RR {{ formatCompactFloat(winTradeThermometer.primary.risk_reward_ratio) }}</span>
      </div>
    </div>
    <div class="pressure-pill-row">
      <div class="pressure-pill balanced">
        <span class="pressure-pill-label">referencias</span>
        <strong>preco {{ formatPrice(winTradeThermometer.primary.current_price) }}</strong>
        <span>POC {{ formatPrice(winTradeThermometer.primary.poc_reference?.price) }} | pos {{ formatValuePosition(winTradeThermometer.primary.current_position) }}</span>
      </div>
      <div class="pressure-pill balanced">
        <span class="pressure-pill-label">target / inval</span>
        <strong>{{ formatPrice(winTradeThermometer.primary.target_price) }} / {{ formatPrice(winTradeThermometer.primary.invalidation_price) }}</strong>
        <span>{{ formatSignedPoints(winTradeThermometer.primary.price_to_target_points) }} | {{ formatSignedPoints(winTradeThermometer.primary.price_to_invalidation_points) }}</span>
      </div>
      <div class="pressure-pill balanced">
        <span class="pressure-pill-label">suporte / resistencia</span>
        <strong>{{ formatPrice(winTradeThermometer.primary.support_reference?.price) }} / {{ formatPrice(winTradeThermometer.primary.resistance_reference?.price) }}</strong>
        <span>{{ formatReferenceLabel(winTradeThermometer.primary.support_reference) }} | {{ formatReferenceLabel(winTradeThermometer.primary.resistance_reference) }}</span>
      </div>
    </div>
    <div v-if="winTradeThermometer.primary.news_context?.available" class="pressure-pill-row">
      <div class="pressure-pill" :class="newsBiasClass(winTradeThermometer.primary.news_context)">
        <span class="pressure-pill-label">macro news</span>
        <strong>{{ formatNewsMarkerLabel(winTradeThermometer.primary.news_context.marker) }}</strong>
        <span>{{ formatNewsBiasLabel(winTradeThermometer.primary.news_context.bias) }} | score {{ formatPressureScore(winTradeThermometer.primary.news_directional_score) }}</span>
      </div>
      <div class="pressure-pill" :class="newsAlignmentClass(winTradeThermometer.primary.news_alignment_state)">
        <span class="pressure-pill-label">pareamento</span>
        <strong>{{ formatNewsAlignmentLabel(winTradeThermometer.primary.news_alignment_state) }}</strong>
        <span>fresh {{ formatConfidenceScore(winTradeThermometer.primary.news_freshness_score) }} | conf {{ formatConfidenceScore(winTradeThermometer.primary.news_confidence_score) }}</span>
      </div>
      <div class="pressure-pill balanced">
        <span class="pressure-pill-label">driver macro</span>
        <strong>{{ winTradeThermometer.primary.news_context.driver_title || '--' }}</strong>
        <span>{{ winTradeThermometer.primary.news_context.headline || winTradeThermometer.primary.news_context.summary || '--' }}</span>
      </div>
    </div>
    <div class="pressure-window-grid">
      <div
        v-for="window in (winTradeThermometer.windows || [])"
        :key="`thermo-${window.minutes}`"
        class="pressure-window-row"
      >
        <span class="pressure-window-label">{{ window.window_label }}</span>
        <span>{{ formatTradeSignalLabel(window.signal) }}</span>
        <span>dir {{ formatPressureScore(window.directional_score) }}</span>
        <span>conv {{ formatConfidenceScore(window.conviction_score) }}</span>
        <span>risk {{ formatConfidenceScore(window.risk_score) }}</span>
      </div>
    </div>
  </section>

  <section v-if="optionsFlowAlignmentModel?.available" class="package-strip">
    <div class="pressure-head">
      <div class="pressure-title">Gamma x fair value x flow</div>
      <div class="pressure-meta">
        {{ formatTradeActionLabel(optionsFlowAlignmentModel.action_bias) }}
        | {{ formatGammaStateLabel(optionsFlowAlignmentModel.gamma_state) }}
        | {{ formatFairValueStateLabel(optionsFlowAlignmentModel.fair_value_state) }}
      </div>
    </div>
    <div class="pressure-window-row">
      <span class="pressure-window-label">leitura dominante</span>
      <span>{{ optionsFlowAlignmentModel.commentary || '--' }}</span>
    </div>
    <div class="pressure-pill-row">
      <div class="pressure-pill" :class="pressureClass(optionsFlowAlignmentModel.directional_score)">
        <span class="pressure-pill-label">score combinado</span>
        <strong>{{ formatPressureScore(optionsFlowAlignmentModel.directional_score) }}</strong>
        <span>conf {{ formatConfidenceScore(optionsFlowAlignmentModel.confidence_score) }}</span>
      </div>
      <div class="pressure-pill balanced">
        <span class="pressure-pill-label">fair value</span>
        <strong>{{ formatPrice(optionsFlowAlignmentModel.fair_value_price) }}</strong>
        <span>{{ formatSignedPoints(optionsFlowAlignmentModel.mispricing_value) }} | z {{ formatCompactFloat(optionsFlowAlignmentModel.mispricing_zscore) }}</span>
      </div>
      <div class="pressure-pill balanced">
        <span class="pressure-pill-label">gamma foco</span>
        <strong>{{ optionsFlowAlignmentModel.nearest_region?.display_label || '--' }}</strong>
        <span>{{ formatPrice(optionsFlowAlignmentModel.nearest_region?.price) }} | {{ formatGammaRoleLabel(optionsFlowAlignmentModel.nearest_region?.role) }}</span>
      </div>
    </div>
    <div class="pressure-pill-row">
      <div
        v-for="region in (optionsFlowAlignmentModel.region_focus || []).slice(0, 3)"
        :key="`opt-align-${region.display_label}-${region.price}`"
        class="pressure-pill balanced"
      >
        <span class="pressure-pill-label">{{ region.display_label }}</span>
        <strong>{{ formatPrice(region.price) }}</strong>
        <span>{{ formatGammaRoleLabel(region.role) }} | dist {{ formatSignedPoints(region.distance_to_price_points) }}</span>
        <span class="pressure-micro">OI {{ formatCompactSignedQuantity(region.open_interest_total, false) }} | gex {{ formatCompactFloat(region.gex_notional_future_net) }}</span>
      </div>
    </div>
  </section>

  <section v-if="liquidityPoolModel?.primary_asset?.primary" class="package-strip">
    <div class="pressure-head">
      <div class="pressure-title">
        Synthetic liquidity pools {{ liquidityPoolModel.primary_asset.primary.window_label || liquidityPoolModel.primary_asset.primary_window_label || '' }}
      </div>
      <div class="pressure-meta">
        {{ formatLiquidityPoolStateLabel(liquidityPoolModel.primary_asset.primary.state) }}
        | risco {{ formatCompactSignedQuantity(liquidityPoolModel.primary_asset.primary.contracts_at_risk_total) }}
      </div>
    </div>
    <div class="pressure-window-row">
      <span class="pressure-window-label">comentario</span>
      <span>{{ liquidityPoolModel.primary_asset.primary.commentary || '--' }}</span>
    </div>
    <div class="pressure-pill-row">
      <div class="pressure-pill" :class="liquidityPoolClass(liquidityPoolModel.primary_asset.primary)">
        <span class="pressure-pill-label">inventario em risco</span>
        <strong>{{ formatCompactSignedQuantity(liquidityPoolModel.primary_asset.primary.market_inventory_contracts) }}</strong>
        <span>gringa {{ formatCompactSignedQuantity(liquidityPoolModel.primary_asset.primary.foreign_inventory_contracts) }} | varejo {{ formatCompactSignedQuantity(liquidityPoolModel.primary_asset.primary.retail_inventory_contracts) }}</span>
      </div>
      <div class="pressure-pill" :class="pressureClass(liquidityPoolModel.primary_asset.primary.short_cover_risk_score)">
        <span class="pressure-pill-label">short cover</span>
        <strong>{{ formatCompactSignedQuantity(liquidityPoolModel.primary_asset.primary.short_cover_closure_contracts) }}</strong>
        <span>risco {{ formatConfidenceScore(liquidityPoolModel.primary_asset.primary.short_cover_risk_score) }} | acima {{ formatCompactSignedQuantity(liquidityPoolModel.primary_asset.primary.short_cover_inventory_above) }}</span>
      </div>
      <div class="pressure-pill" :class="pressureClass(-1 * (liquidityPoolModel.primary_asset.primary.long_flush_risk_score || 0))">
        <span class="pressure-pill-label">long flush</span>
        <strong>{{ formatCompactSignedQuantity(liquidityPoolModel.primary_asset.primary.long_flush_closure_contracts) }}</strong>
        <span>risco {{ formatConfidenceScore(liquidityPoolModel.primary_asset.primary.long_flush_risk_score) }} | abaixo {{ formatCompactSignedQuantity(liquidityPoolModel.primary_asset.primary.long_flush_inventory_below) }}</span>
      </div>
    </div>
    <div class="pressure-pill-row">
      <div
        v-for="pool in (liquidityPoolModel.primary_asset.primary.pools || []).slice(0, 3)"
        :key="`pool-top-${pool.cohort}-${pool.pool_type}-${pool.price}`"
        class="pressure-pill"
        :class="pressureClass(pool.trigger_side === 'buy' ? (pool.cascade_probability || 0) : pool.trigger_side === 'sell' ? -1 * (pool.cascade_probability || 0) : 0)"
      >
        <span class="pressure-pill-label">{{ pool.cohort_label }}</span>
        <strong>{{ formatLiquidityPoolTypeLabel(pool.pool_type) }}</strong>
        <span>{{ formatPrice(pool.price) }} | {{ formatLocationLabel(pool.relative_location) }} | stop {{ formatCompactSignedQuantity(pool.estimated_stop_closure_contracts) }}</span>
        <span class="pressure-micro">cascade {{ formatConfidenceScore(pool.cascade_probability) }} | open {{ formatCompactSignedQuantity(pool.synthetic_open_inventory_contracts) }}</span>
      </div>
    </div>
    <div class="pressure-window-grid">
      <div v-for="window in (liquidityPoolModel.primary_asset.windows || [])" :key="`liq-pools-${window.minutes}`" class="pressure-window-row">
        <span class="pressure-window-label">{{ window.window_label }}</span>
        <span>{{ formatLiquidityPoolStateLabel(window.state) }}</span>
        <span>short {{ formatCompactSignedQuantity(window.short_cover_closure_contracts) }}</span>
        <span>long {{ formatCompactSignedQuantity(window.long_flush_closure_contracts) }}</span>
        <span>coil {{ formatConfidenceScore(window.two_sided_stop_coil_score) }}</span>
      </div>
    </div>
  </section>

  <section v-if="liquidityIntelligenceModel?.primary_asset?.primary" class="package-strip">
    <div class="pressure-head">
      <div class="pressure-title">
        Liquidity intelligence {{ liquidityIntelligenceModel.primary_asset.primary.window_label || liquidityIntelligenceModel.primary_asset.primary_window_label || '' }}
      </div>
      <div class="pressure-meta">
        {{ formatLiquidityProviderLabel(liquidityIntelligenceModel.primary_asset.primary.liquidity_provider_state) }}
        | {{ formatTrapStateLabel(liquidityIntelligenceModel.primary_asset.primary.trap_state) }}
        | {{ formatSqueezeStateLabel(liquidityIntelligenceModel.primary_asset.primary.squeeze_state) }}
      </div>
    </div>
    <div class="pressure-window-row">
      <span class="pressure-window-label">comentario operacional</span>
      <span>{{ liquidityIntelligenceModel.primary_asset.primary.commentary || '--' }}</span>
    </div>
    <div class="pressure-pill-row">
      <div class="pressure-pill" :class="liquidityIntelClass(liquidityIntelligenceModel.primary_asset.primary)">
        <span class="pressure-pill-label">liquidez</span>
        <strong>{{ formatLiquidityProviderLabel(liquidityIntelligenceModel.primary_asset.primary.liquidity_provider_state) }}</strong>
        <span>dens {{ formatConfidenceScore(liquidityIntelligenceModel.primary_asset.primary.liquidity_density_score) }} | thin {{ formatConfidenceScore(liquidityIntelligenceModel.primary_asset.primary.thin_liquidity_score) }}</span>
      </div>
      <div class="pressure-pill" :class="liquidityIntelClass(liquidityIntelligenceModel.primary_asset.primary)">
        <span class="pressure-pill-label">traps / squeeze</span>
        <strong>{{ formatTrapStateLabel(liquidityIntelligenceModel.primary_asset.primary.trap_state) }}</strong>
        <span>{{ formatSqueezeStateLabel(liquidityIntelligenceModel.primary_asset.primary.squeeze_state) }} | stop {{ formatStopRunStateLabel(liquidityIntelligenceModel.primary_asset.primary.stop_run_state) }}</span>
      </div>
      <div class="pressure-pill" :class="pressureClass(liquidityIntelligenceModel.primary_asset.primary.retail_contra_trend_score)">
        <span class="pressure-pill-label">varejo</span>
        <strong>{{ formatRetailMicrostructureLabel(liquidityIntelligenceModel.primary_asset.primary.retail_microstructure_state) }}</strong>
        <span>contra {{ formatConfidenceScore(liquidityIntelligenceModel.primary_asset.primary.retail_contra_trend_score) }} | trap {{ formatConfidenceScore(liquidityIntelligenceModel.primary_asset.primary.retail_trapped_score) }}</span>
      </div>
    </div>
    <div class="pressure-window-grid">
      <div v-for="window in (liquidityIntelligenceModel.primary_asset.windows || [])" :key="`liq-intel-${window.minutes}`" class="pressure-window-row">
        <span class="pressure-window-label">{{ window.window_label }}</span>
        <span>{{ formatTrapStateLabel(window.trap_state) }}</span>
        <span>{{ formatSqueezeStateLabel(window.squeeze_state) }}</span>
        <span>liq {{ formatConfidenceScore(window.liquidity_density_score) }}</span>
        <span>ret {{ formatConfidenceScore(window.retail_contra_trend_score) }}</span>
      </div>
    </div>
  </section>
</template>

<script setup>
import {
  formatCompactFloat,
  formatPressureScore,
  formatPrice,
  formatSignedPoints,
} from '@/utils/marketFormatters'
import {
  formatCompactSignedQuantity,
  formatConfidenceScore,
  formatEntryStyleLabel,
  formatFairValueStateLabel,
  formatGammaRoleLabel,
  formatGammaStateLabel,
  formatLiquidityPoolStateLabel,
  formatLiquidityPoolTypeLabel,
  formatLiquidityProviderLabel,
  formatLocationLabel,
  formatNewsAlignmentLabel,
  formatNewsBiasLabel,
  formatNewsMarkerLabel,
  formatReferenceLabel,
  formatRetailMicrostructureLabel,
  formatSqueezeStateLabel,
  formatStopRunStateLabel,
  formatTradeActionLabel,
  formatTradeSignalLabel,
  formatTrapStateLabel,
  formatValuePosition,
  liquidityIntelClass,
  liquidityPoolClass,
  newsAlignmentClass,
  newsBiasClass,
  pressureClass,
  riskClass,
  thermometerClass,
} from '../models/heatmapModels'

defineProps({
  winTradeThermometer: { type: Object, default: null },
  optionsFlowAlignmentModel: { type: Object, default: null },
  liquidityPoolModel: { type: Object, default: null },
  liquidityIntelligenceModel: { type: Object, default: null },
})
</script>

<style scoped src="./MacroSummaryPanels.css"></style>

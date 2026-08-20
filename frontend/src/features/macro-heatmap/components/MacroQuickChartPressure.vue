<template>
        <div class="quick-chart-head">
          <div>
            <div class="quick-chart-title">{{ asset.label }} <span>{{ asset.ticker }}</span></div>
            <div class="quick-chart-meta">
              <span>ultimo {{ formatPrice(asset.latest_price) }}</span>
              <span>{{ asset.candles.length }} candles</span>
              <span>{{ asset.chart?.liquidityPoolBands?.length || 0 }} pools</span>
              <span>sessao {{ asset.session_date || '--' }}</span>
            </div>
          </div>
          <div class="quick-chart-badges">
            <span class="mini-badge">{{ asset.price_source || 'snapshot' }}</span>
            <span class="mini-badge muted">{{ formatTime(asset.generated_at) }}</span>
          </div>
        </div>

        <div v-if="asset.pressure_model?.primary" class="pressure-strip">
          <div class="pressure-head">
            <div class="pressure-title">
              Inventory pressure {{ asset.pressure_model.primary.window_label }}
            </div>
            <div class="pressure-meta">
              move {{ formatSignedPoints(asset.pressure_model.primary.price_move_points) }}
              | {{ formatSignedBps(asset.pressure_model.primary.price_move_bps) }}
              | gross {{ formatSignedQuantity(asset.pressure_model.primary.total_gross_quantity, false) }}
            </div>
          </div>
          <div class="pressure-pill-row">
            <div
              v-for="cohort in PRESSURE_COHORTS"
              :key="`${asset.key}-${cohort.key}`"
              class="pressure-pill"
              :class="pressureClass(asset.pressure_model.primary.cohorts?.[cohort.key]?.pressure_score)"
            >
              <span class="pressure-pill-label">{{ cohort.label }}</span>
              <strong>{{ formatPressureScore(asset.pressure_model.primary.cohorts?.[cohort.key]?.pressure_score) }}</strong>
              <span>{{ asset.pressure_model.primary.cohorts?.[cohort.key]?.response_state || 'balanced' }}</span>
            </div>
          </div>
          <div class="pressure-window-grid">
            <div
              v-for="window in (asset.pressure_model.windows || [])"
              :key="`${asset.key}-pressure-${window.minutes}`"
              class="pressure-window-row"
            >
              <span class="pressure-window-label">{{ window.window_label }}</span>
              <span>net {{ formatPressureScore(window.cohorts?.net?.pressure_score) }}</span>
              <span>foreign {{ formatPressureScore(window.cohorts?.foreign?.pressure_score) }}</span>
              <span>retail {{ formatPressureScore(window.cohorts?.retail?.pressure_score) }}</span>
              <span>move {{ formatSignedPoints(window.price_move_points) }}</span>
            </div>
          </div>
        </div>

        <div v-if="asset.pressure_model?.primary" class="pressure-strip efficiency-strip">
          <div class="pressure-head">
            <div class="pressure-title">
              Delta efficiency {{ asset.pressure_model.primary.window_label }}
            </div>
            <div class="pressure-meta">
              dominante {{ asset.pressure_model.primary.dominant_flow_cohort || '--' }}
              | {{ asset.pressure_model.primary.dominant_efficiency_state || 'mixed' }}
            </div>
          </div>
          <div class="pressure-pill-row">
            <div
              v-for="cohort in PRESSURE_COHORTS"
              :key="`${asset.key}-eff-${cohort.key}`"
              class="pressure-pill"
              :class="pressureClass(asset.pressure_model.primary.cohorts?.[cohort.key]?.delta_efficiency_score)"
            >
              <span class="pressure-pill-label">{{ cohort.label }}</span>
              <strong>{{ formatPressureScore(asset.pressure_model.primary.cohorts?.[cohort.key]?.delta_efficiency_score) }}</strong>
              <span>{{ asset.pressure_model.primary.cohorts?.[cohort.key]?.efficiency_state || 'mixed' }}</span>
              <span class="pressure-micro">
                abs {{ formatPressureScore(asset.pressure_model.primary.cohorts?.[cohort.key]?.absorption_score) }}
                | frag {{ formatPressureScore(asset.pressure_model.primary.cohorts?.[cohort.key]?.fragility_score) }}
              </span>
              <span class="pressure-micro">
                pts/1k {{ formatCompactFloat(asset.pressure_model.primary.cohorts?.[cohort.key]?.points_per_1k_net) }}
              </span>
            </div>
          </div>
        </div>

        <div v-if="asset.cohort_value_map?.cohorts" class="pressure-strip value-map-strip">
          <div class="pressure-head">
            <div class="pressure-title">
              Cohort value map
            </div>
            <div class="pressure-meta">
              bin {{ formatPrice(asset.cohort_value_map.bin_size) }}
              | value {{ formatCompactFloat((asset.cohort_value_map.value_area_ratio || 0) * 100) }}%
              | eventos {{ asset.cohort_value_map.event_count || 0 }}
            </div>
          </div>
          <div class="pressure-pill-row">
            <div
              v-for="cohort in PRESSURE_COHORTS"
              :key="`${asset.key}-value-${cohort.key}`"
              class="pressure-pill"
              :class="pressureClass(asset.cohort_value_map.cohorts?.[cohort.key]?.net_ratio_score)"
            >
              <span class="pressure-pill-label">{{ cohort.label }}</span>
              <strong>POC {{ formatPrice(asset.cohort_value_map.cohorts?.[cohort.key]?.poc_price) }}</strong>
              <span>
                VA {{ formatPrice(asset.cohort_value_map.cohorts?.[cohort.key]?.value_area_low) }}
                -> {{ formatPrice(asset.cohort_value_map.cohorts?.[cohort.key]?.value_area_high) }}
              </span>
              <span class="pressure-micro">
                {{ formatValuePosition(asset.cohort_value_map.cohorts?.[cohort.key]?.current_position) }}
                | net {{ formatSignedQuantity(asset.cohort_value_map.cohorts?.[cohort.key]?.net_quantity) }}
              </span>
              <span class="pressure-micro">
                dist POC {{ formatSignedPoints(asset.cohort_value_map.cohorts?.[cohort.key]?.distance_to_poc_points) }}
                | skew {{ formatPressureScore(asset.cohort_value_map.cohorts?.[cohort.key]?.net_ratio_score) }}
              </span>
            </div>
          </div>
        </div>

        <div v-if="asset.flow_regime_classifier?.cohorts" class="pressure-strip regime-strip">
          <div class="pressure-head">
            <div class="pressure-title">
              Absorption vs initiative {{ asset.flow_regime_classifier.window_label || asset.pressure_model?.primary?.window_label || '' }}
            </div>
            <div class="pressure-meta">
              dominante {{ asset.flow_regime_classifier.primary_cohort || '--' }}
              | {{ formatFlowRegimeLabel(asset.flow_regime_classifier.primary_regime_state) }}
              | conf {{ formatConfidenceScore(asset.flow_regime_classifier.primary_confidence_score) }}
            </div>
          </div>
          <div class="pressure-window-row">
            <span class="pressure-window-label">leitura dominante</span>
            <span>{{ asset.flow_regime_classifier.primary_rationale || '--' }}</span>
          </div>
          <div class="pressure-pill-row">
            <div
              v-for="cohort in PRESSURE_COHORTS"
              :key="`${asset.key}-regime-${cohort.key}`"
              class="pressure-pill"
              :class="flowRegimeClass(asset.flow_regime_classifier.cohorts?.[cohort.key])"
            >
              <span class="pressure-pill-label">{{ cohort.label }}</span>
              <strong>{{ formatFlowRegimeLabel(asset.flow_regime_classifier.cohorts?.[cohort.key]?.regime_state) }}</strong>
              <span>
                conf {{ formatConfidenceScore(asset.flow_regime_classifier.cohorts?.[cohort.key]?.confidence_score) }}
                | {{ formatValuePosition(asset.flow_regime_classifier.cohorts?.[cohort.key]?.current_position) }}
              </span>
              <span class="pressure-micro">
                {{ asset.flow_regime_classifier.cohorts?.[cohort.key]?.response_state || 'balanced' }}
                | {{ asset.flow_regime_classifier.cohorts?.[cohort.key]?.efficiency_state || 'mixed' }}
              </span>
              <span class="pressure-micro">
                {{ asset.flow_regime_classifier.cohorts?.[cohort.key]?.rationale || '--' }}
              </span>
            </div>
          </div>
        </div>

        <div v-if="asset.divergence_model?.primary" class="pressure-strip divergence-strip">
          <div class="pressure-head">
            <div class="pressure-title">
              Foreign vs retail divergence {{ asset.divergence_model.primary.window_label || asset.pressure_model?.primary?.window_label || '' }}
            </div>
            <div class="pressure-meta">
              {{ formatDivergenceStateLabel(asset.divergence_model.primary.state) }}
              | align {{ formatPressureScore(asset.divergence_model.primary.alignment_score) }}
              | div {{ formatPressureScore(asset.divergence_model.primary.divergence_score) }}
            </div>
          </div>
          <div class="pressure-pill-row">
            <div
              class="pressure-pill"
              :class="divergenceClass(asset.divergence_model.primary.lead_score)"
            >
              <span class="pressure-pill-label">lead</span>
              <strong>{{ formatPressureScore(asset.divergence_model.primary.lead_score) }}</strong>
              <span>{{ asset.divergence_model.primary.bias_side || 'neutral' }}</span>
              <span class="pressure-micro">{{ asset.divergence_model.primary.rationale || '--' }}</span>
            </div>
            <div
              class="pressure-pill"
              :class="divergenceClass(asset.divergence_model.primary.foreign_pressure_score)"
            >
              <span class="pressure-pill-label">foreign</span>
              <strong>{{ formatPressureScore(asset.divergence_model.primary.foreign_pressure_score) }}</strong>
              <span>net {{ formatSignedQuantity(asset.divergence_model.primary.foreign_net_quantity) }}</span>
            </div>
            <div
              class="pressure-pill"
              :class="divergenceClass(asset.divergence_model.primary.retail_pressure_score)"
            >
              <span class="pressure-pill-label">retail</span>
              <strong>{{ formatPressureScore(asset.divergence_model.primary.retail_pressure_score) }}</strong>
              <span>net {{ formatSignedQuantity(asset.divergence_model.primary.retail_net_quantity) }}</span>
            </div>
          </div>
          <div class="pressure-window-grid">
            <div
              v-for="window in (asset.divergence_model.windows || [])"
              :key="`${asset.key}-divergence-${window.minutes}`"
              class="pressure-window-row"
            >
              <span class="pressure-window-label">{{ window.window_label }}</span>
              <span>{{ formatDivergenceStateLabel(window.state) }}</span>
              <span>align {{ formatPressureScore(window.alignment_score) }}</span>
              <span>div {{ formatPressureScore(window.divergence_score) }}</span>
              <span>lead {{ formatPressureScore(window.lead_score) }}</span>
            </div>
          </div>
        </div>

        <div v-if="asset.level_defense_model?.cohorts" class="pressure-strip level-defense-strip">
          <div class="pressure-head">
            <div class="pressure-title">
              Level defense
            </div>
            <div class="pressure-meta">
              dominante {{ asset.level_defense_model.primary_cohort || '--' }}
              | {{ formatLevelDefenseStateLabel(asset.level_defense_model.primary_state) }}
              | score {{ formatPressureScore(asset.level_defense_model.primary_score) }}
            </div>
          </div>
          <div class="pressure-window-row">
            <span class="pressure-window-label">leitura dominante</span>
            <span>{{ asset.level_defense_model.primary_rationale || '--' }}</span>
          </div>
          <div class="pressure-pill-row">
            <div
              v-for="cohort in PRESSURE_COHORTS"
              :key="`${asset.key}-defense-${cohort.key}`"
              class="pressure-pill"
              :class="levelDefenseClass(asset.level_defense_model.cohorts?.[cohort.key])"
            >
              <span class="pressure-pill-label">{{ cohort.label }}</span>
              <strong>{{ formatLevelDefenseStateLabel(asset.level_defense_model.cohorts?.[cohort.key]?.primary_state) }}</strong>
              <span>
                sup {{ formatPrice(asset.level_defense_model.cohorts?.[cohort.key]?.support_level?.price) }}
                | res {{ formatPrice(asset.level_defense_model.cohorts?.[cohort.key]?.resistance_level?.price) }}
              </span>
              <span class="pressure-micro">
                def {{ formatPressureScore(asset.level_defense_model.cohorts?.[cohort.key]?.defense_score) }}
                | acc {{ formatPressureScore(asset.level_defense_model.cohorts?.[cohort.key]?.acceptance_score) }}
                | rej {{ formatPressureScore(asset.level_defense_model.cohorts?.[cohort.key]?.rejection_score) }}
              </span>
              <span class="pressure-micro">
                ativo {{ formatPrice(asset.level_defense_model.cohorts?.[cohort.key]?.active_level?.price) }}
                | {{ asset.level_defense_model.cohorts?.[cohort.key]?.bias_side || 'neutral' }}
              </span>
              <span class="pressure-micro">
                {{ asset.level_defense_model.cohorts?.[cohort.key]?.rationale || '--' }}
              </span>
            </div>
          </div>
        </div>

        <div v-if="asset.concentration_model?.primary" class="pressure-strip concentration-strip">
          <div class="pressure-head">
            <div class="pressure-title">
              Player concentration / breadth {{ asset.concentration_model.primary.window_label || asset.concentration_model.primary_window_label || '' }}
            </div>
            <div class="pressure-meta">
              dominante {{ asset.concentration_model.primary.primary_cohort || '--' }}
              | {{ formatConcentrationStateLabel(asset.concentration_model.primary.state) }}
              | breadth {{ formatPressureScore(asset.concentration_model.primary.primary_breadth_score) }}
            </div>
          </div>
          <div class="pressure-window-row">
            <span class="pressure-window-label">leitura dominante</span>
            <span>{{ asset.concentration_model.primary.primary_rationale || '--' }}</span>
          </div>
          <div class="pressure-pill-row">
            <div
              v-for="cohort in PRESSURE_COHORTS"
              :key="`${asset.key}-conc-${cohort.key}`"
              class="pressure-pill"
              :class="concentrationClass(asset.concentration_model.cohorts?.[cohort.key])"
            >
              <span class="pressure-pill-label">{{ cohort.label }}</span>
              <strong>{{ formatConcentrationStateLabel(asset.concentration_model.cohorts?.[cohort.key]?.state) }}</strong>
              <span>
                players {{ asset.concentration_model.cohorts?.[cohort.key]?.active_player_count ?? 0 }}
                | eff {{ formatCompactFloat(asset.concentration_model.cohorts?.[cohort.key]?.effective_player_count) }}
              </span>
              <span class="pressure-micro">
                breadth {{ formatPressureScore(asset.concentration_model.cohorts?.[cohort.key]?.breadth_score) }}
                | conc {{ formatPressureScore(asset.concentration_model.cohorts?.[cohort.key]?.concentration_score) }}
              </span>
              <span class="pressure-micro">
                hhi {{ formatCompactFloat(asset.concentration_model.cohorts?.[cohort.key]?.concentration_hhi) }}
                | top {{ formatCompactFloat((asset.concentration_model.cohorts?.[cohort.key]?.top_player_share || 0) * 100) }}%
              </span>
              <span class="pressure-micro">
                lead {{ asset.concentration_model.cohorts?.[cohort.key]?.dominant_player_name || '--' }}
              </span>
              <span class="pressure-micro">
                {{ asset.concentration_model.cohorts?.[cohort.key]?.rationale || '--' }}
              </span>
            </div>
          </div>
        </div>

        <div v-if="asset.liquidity_pools?.primary" class="pressure-strip liquidity-intelligence-strip">
          <div class="pressure-head">
            <div class="pressure-title">
              Synthetic liquidity pools {{ asset.liquidity_pools.primary.window_label || asset.liquidity_pools.primary_window_label || '' }}
            </div>
            <div class="pressure-meta">
              {{ formatLiquidityPoolStateLabel(asset.liquidity_pools.primary.state) }}
              | risco {{ formatCompactSignedQuantity(asset.liquidity_pools.primary.contracts_at_risk_total) }}
            </div>
          </div>
          <div class="pressure-window-row">
            <span class="pressure-window-label">comentario</span>
            <span>{{ asset.liquidity_pools.primary.commentary || '--' }}</span>
          </div>
          <div class="pressure-pill-row">
            <div class="pressure-pill" :class="liquidityPoolClass(asset.liquidity_pools.primary)">
              <span class="pressure-pill-label">inventario</span>
              <strong>{{ formatCompactSignedQuantity(asset.liquidity_pools.primary.market_inventory_contracts) }}</strong>
              <span>gringa {{ formatCompactSignedQuantity(asset.liquidity_pools.primary.foreign_inventory_contracts) }} | varejo {{ formatCompactSignedQuantity(asset.liquidity_pools.primary.retail_inventory_contracts) }}</span>
            </div>
            <div class="pressure-pill" :class="pressureClass(asset.liquidity_pools.primary.short_cover_risk_score)">
              <span class="pressure-pill-label">short cover</span>
              <strong>{{ formatCompactSignedQuantity(asset.liquidity_pools.primary.short_cover_closure_contracts) }}</strong>
              <span>risco {{ formatConfidenceScore(asset.liquidity_pools.primary.short_cover_risk_score) }}</span>
            </div>
            <div class="pressure-pill" :class="pressureClass(-1 * (asset.liquidity_pools.primary.long_flush_risk_score || 0))">
              <span class="pressure-pill-label">long flush</span>
              <strong>{{ formatCompactSignedQuantity(asset.liquidity_pools.primary.long_flush_closure_contracts) }}</strong>
              <span>risco {{ formatConfidenceScore(asset.liquidity_pools.primary.long_flush_risk_score) }}</span>
            </div>
          </div>
          <div class="pressure-pill-row">
            <div
              v-for="pool in (asset.liquidity_pools.primary.pools || []).slice(0, 3)"
              :key="`${asset.key}-pool-${pool.cohort}-${pool.pool_type}-${pool.price}`"
              class="pressure-pill"
              :class="pressureClass(pool.trigger_side === 'buy' ? (pool.cascade_probability || 0) : pool.trigger_side === 'sell' ? -1 * (pool.cascade_probability || 0) : 0)"
            >
              <span class="pressure-pill-label">{{ pool.cohort_label }}</span>
              <strong>{{ formatLiquidityPoolTypeLabel(pool.pool_type) }}</strong>
              <span>{{ formatPrice(pool.price) }} | {{ formatLocationLabel(pool.relative_location) }} | stop {{ formatCompactSignedQuantity(pool.estimated_stop_closure_contracts) }}</span>
              <span class="pressure-micro">open {{ formatCompactSignedQuantity(pool.synthetic_open_inventory_contracts) }} | cascade {{ formatConfidenceScore(pool.cascade_probability) }}</span>
            </div>
          </div>
        </div>

        <div v-if="asset.liquidity_intelligence?.primary" class="pressure-strip liquidity-intelligence-strip">
          <div class="pressure-head">
            <div class="pressure-title">
              Liquidity intelligence {{ asset.liquidity_intelligence.primary.window_label || asset.liquidity_intelligence.primary_window_label || '' }}
            </div>
            <div class="pressure-meta">
              {{ formatLiquidityProviderLabel(asset.liquidity_intelligence.primary.liquidity_provider_state) }}
              | {{ formatTrapStateLabel(asset.liquidity_intelligence.primary.trap_state) }}
              | {{ formatSqueezeStateLabel(asset.liquidity_intelligence.primary.squeeze_state) }}
            </div>
          </div>
          <div class="pressure-window-row">
            <span class="pressure-window-label">comentario</span>
            <span>{{ asset.liquidity_intelligence.primary.commentary || '--' }}</span>
          </div>
          <div class="pressure-pill-row">
            <div class="pressure-pill" :class="liquidityIntelClass(asset.liquidity_intelligence.primary)">
              <span class="pressure-pill-label">liquidez</span>
              <strong>{{ formatLiquidityProviderLabel(asset.liquidity_intelligence.primary.liquidity_provider_state) }}</strong>
              <span>dens {{ formatConfidenceScore(asset.liquidity_intelligence.primary.liquidity_density_score) }} | thin {{ formatConfidenceScore(asset.liquidity_intelligence.primary.thin_liquidity_score) }}</span>
            </div>
            <div class="pressure-pill" :class="liquidityIntelClass(asset.liquidity_intelligence.primary)">
              <span class="pressure-pill-label">trap / squeeze</span>
              <strong>{{ formatTrapStateLabel(asset.liquidity_intelligence.primary.trap_state) }}</strong>
              <span>{{ formatSqueezeStateLabel(asset.liquidity_intelligence.primary.squeeze_state) }} | {{ formatStopRunStateLabel(asset.liquidity_intelligence.primary.stop_run_state) }}</span>
            </div>
            <div class="pressure-pill" :class="pressureClass(asset.liquidity_intelligence.primary.retail_contra_trend_score)">
              <span class="pressure-pill-label">varejo</span>
              <strong>{{ formatRetailMicrostructureLabel(asset.liquidity_intelligence.primary.retail_microstructure_state) }}</strong>
              <span>contra {{ formatConfidenceScore(asset.liquidity_intelligence.primary.retail_contra_trend_score) }} | trap {{ formatConfidenceScore(asset.liquidity_intelligence.primary.retail_trapped_score) }}</span>
            </div>
          </div>
          <div class="pressure-pill-row">
            <div
              v-for="region in (asset.liquidity_intelligence.estimated_regions || []).slice(0, 3)"
              :key="`${asset.key}-liq-region-${region.cohort}-${region.price}-${region.region_role}`"
              class="pressure-pill"
              :class="pressureClass(region.net_ratio_score)"
            >
              <span class="pressure-pill-label">{{ region.cohort_label }}</span>
              <strong>{{ formatLiquidityRegionRoleLabel(region.region_role) }}</strong>
              <span>{{ formatPrice(region.price) }} | gross {{ formatSignedQuantity(region.gross_quantity, false) }}</span>
              <span class="pressure-micro">net {{ formatSignedQuantity(region.net_quantity) }} | share {{ formatCompactFloat((region.share || 0) * 100) }}%</span>
            </div>
          </div>
        </div>

</template>

<script>
import { injectMacroHeatmapContext } from '../context'

export default {
  name: 'MacroQuickChartPressure',
  props: { asset: { type: Object, required: true } },
  setup() {
    return injectMacroHeatmapContext()
  },
}
</script>

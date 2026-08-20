<template>
        <div class="toolbar">
          <div class="toolbar-group">
            <button
              v-for="timeframe in TIMEFRAME_OPTIONS"
              :key="`${asset.key}-tf-${timeframe.minutes}`"
              class="chip"
              :class="{ active: getTimeframeMinutes(asset.key) === timeframe.minutes }"
              @click="setTimeframe(asset.key, timeframe.minutes, asset)"
            >
              {{ timeframe.label }}
            </button>
          </div>
          <div class="toolbar-group">
            <button
              v-for="range in RANGE_OPTIONS"
              :key="`${asset.key}-${range.key}`"
              class="chip"
              :class="{ active: getRangeKey(asset.key) === range.key }"
              @click="setRange(asset.key, range.key, asset)"
            >
              {{ range.label }}
            </button>
          </div>
        <div class="toolbar-group">
          <button class="chip" @click="shiftWindow(asset.key, -1, asset)">&lt;</button>
          <button class="chip" @click="resetWindow(asset.key, asset)">dia</button>
          <button class="chip" @click="shiftWindow(asset.key, 1, asset)">&gt;</button>
        </div>
      </div>

        <div v-if="asset.key === 'win'" class="tag-filter-strip">
          <template v-if="getAssetFairValueSummary(asset)">
            <span class="filter-label">fair value</span>
            <span class="fair-value-mini-pill" :class="pressureClass(getAssetFairValueSummary(asset)?.mispricingValue || 0)">
              <strong>{{ formatPrice(getAssetFairValueSummary(asset)?.fairValuePrice) }}</strong>
              <span>justo</span>
            </span>
            <span class="fair-value-mini-pill" :class="pressureClass(getAssetFairValueSummary(asset)?.mispricingValue || 0)">
              <strong>{{ formatSignedPoints(getAssetFairValueSummary(asset)?.mispricingValue) }}</strong>
              <span>distorcao</span>
            </span>
            <span class="fair-value-mini-pill muted">
              <strong>z {{ formatCompactFloat(getAssetFairValueSummary(asset)?.mispricingZscore) }}</strong>
              <span>{{ formatFairValueStateLabel(getAssetFairValueSummary(asset)?.fairValueState) }}</span>
            </span>
            <span v-if="getAssetFairValueSummary(asset)?.nearestRegionLabel" class="fair-value-mini-pill muted">
              <strong>{{ getAssetFairValueSummary(asset)?.nearestRegionLabel }}</strong>
              <span>{{ formatPrice(getAssetFairValueSummary(asset)?.nearestRegionPrice) }}</span>
            </span>
          </template>
          <span class="filter-label">gamma</span>
          <button
            class="chip"
            :class="{ active: !gammaOverlayEnabled }"
            @click="disableGammaOverlay()"
          >
            off
          </button>
          <button
            class="chip"
            :class="{ active: gammaOverlayEnabled && !selectedGammaOverlayKeys.length }"
            @click="clearGammaOverlaySelection()"
          >
            todas
          </button>
          <button
            v-for="item in GAMMA_OVERLAY_OPTIONS"
            :key="`${asset.key}-gamma-filter-${item.key}`"
            class="chip"
            :class="{ active: gammaOverlayEnabled && selectedGammaOverlayKeys.includes(item.key) }"
            @click="toggleGammaOverlaySelection(item.key)"
          >
            {{ item.shortLabel }}
          </button>
          <span class="filter-label">fair value</span>
          <button
            class="chip"
            :class="{ active: !fairValueOverlayEnabled }"
            @click="fairValueOverlayEnabled = false"
          >
            off
          </button>
          <button
            class="chip"
            :class="{ active: fairValueOverlayEnabled }"
            @click="fairValueOverlayEnabled = true"
          >
            on
          </button>
        </div>

        <div v-if="asset.key === 'win' && asset.chart?.gammaCards?.length" class="pool-card-list gamma-card-list">
          <div
            v-for="region in asset.chart.gammaCards"
            :key="`${asset.key}-gamma-card-${region.region_key}`"
            class="pool-card"
          >
            <div class="pool-card-head">
              <span class="pool-card-badge" :style="{ color: region.color, borderColor: `${region.color}55` }">
                {{ region.symbol }}
              </span>
              <div class="pool-card-title">
                <strong>{{ region.displayLabel }}</strong>
                <span>{{ formatGammaRoleLabel(region.role) }}</span>
              </div>
            </div>
            <div class="pool-card-grid">
              <span>preco {{ formatPrice(region.price) }}</span>
              <span>banda {{ formatPrice(region.bandLow) }} -> {{ formatPrice(region.bandHigh) }}</span>
              <span>OI {{ formatCompactSignedQuantity(region.openInterestTotal, false) }}</span>
              <span>gex fut {{ formatCompactFloat(region.gexNotionalFutureNet) }}</span>
              <span>dist {{ formatSignedPoints(region.distanceToPricePoints) }}</span>
              <span>relev {{ formatConfidenceScore(region.relevanceScore) }}</span>
            </div>
            <div class="pool-card-detail">
              <span>{{ region.description }}</span>
              <span>{{ region.commentary }}</span>
            </div>
          </div>
        </div>

        <div class="tag-filter-strip">
          <span class="filter-label">pools</span>
          <button
            class="chip"
            :class="{ active: !poolOverlayEnabled }"
            @click="disablePoolOverlay()"
          >
            off
          </button>
          <button
            class="chip"
            :class="{ active: poolOverlayEnabled && !selectedPoolOverlayKeys.length }"
            @click="clearPoolOverlaySelection()"
          >
            todas
          </button>
          <button
            v-for="item in POOL_OVERLAY_OPTIONS"
            :key="`${asset.key}-pool-filter-${item.key}`"
            class="chip chip-pool-filter"
            :class="{ active: poolOverlayEnabled && selectedPoolOverlayKeys.includes(item.key) }"
            @click="togglePoolOverlaySelection(item.key)"
          >
            {{ item.shortLabel }}
          </button>
        </div>

        <div class="pool-legend-strip">
          <span class="filter-label">legenda pools</span>
          <div class="pool-legend-items">
            <span
              v-for="item in POOL_OVERLAY_OPTIONS"
              :key="`${asset.key}-pool-legend-${item.key}`"
              class="pool-legend-item"
            >
              <span class="pool-legend-badge" :style="{ color: item.color, borderColor: `${item.color}55` }">
                {{ item.shortLabel }}
              </span>
              <span class="pool-legend-copy">
                <strong>{{ item.label }}</strong>
                <span>{{ item.description }}</span>
              </span>
            </span>
          </div>
        </div>

        <div v-if="asset.chart?.liquidityPoolCards?.length" class="pool-card-list">
          <div
            v-for="pool in asset.chart.liquidityPoolCards"
            :key="`${asset.key}-pool-card-${pool.cohort}-${pool.pool_type}-${pool.price}`"
            class="pool-card"
            :class="pressureClass(pool.trigger_side === 'buy' ? (pool.cascade_probability || 0) : pool.trigger_side === 'sell' ? -1 * (pool.cascade_probability || 0) : 0)"
          >
            <div class="pool-card-head">
              <span class="pool-card-badge" :style="{ color: pool.stroke, borderColor: `${pool.stroke}66` }">
                {{ pool.shortLabel }}
              </span>
              <div class="pool-card-title">
                <strong>{{ pool.overlayLabel }}</strong>
                <span>{{ pool.cohort_label }} | {{ formatPoolTriggerLabel(pool.trigger_side) }}</span>
              </div>
            </div>
            <div class="pool-card-grid">
              <span>preco {{ formatPrice(pool.price) }}</span>
              <span>banda {{ formatPrice(pool.band_low) }} -> {{ formatPrice(pool.band_high) }}</span>
              <span>stop close {{ formatCompactSignedQuantity(pool.estimated_stop_closure_contracts) }}</span>
              <span>open sint {{ formatCompactSignedQuantity(pool.synthetic_open_inventory_contracts) }}</span>
              <span>clear band {{ formatCompactSignedQuantity(pool.estimated_contracts_to_clear_band) }}</span>
              <span>cascade {{ formatConfidenceScore(pool.cascade_probability) }}</span>
              <span>unwind {{ formatConfidenceScore(pool.unwind_intensity_score) }}</span>
              <span>{{ pool.relative_location_label || formatLocationLabel(pool.relative_location) }} | {{ formatPoolAggregationScopeLabel(pool.aggregation_scope) }}</span>
              <span>elas dia {{ formatConfidenceScore(pool.dayElasticityScore) }}</span>
              <span>elas reg {{ formatConfidenceScore(pool.regionElasticityScore) }}</span>
              <span>stop move {{ formatProjectedMove(pool.projectedStopMove) }}</span>
              <span>alvo 1 {{ formatPrice(pool.projectedTarget1Price) }}</span>
              <span>alvo 2 {{ formatPrice(pool.projectedTarget2Price) }}</span>
              <span>lado {{ formatPoolDirectionLabel(pool.projectedDirection) }}</span>
            </div>
            <div class="pool-card-detail">
              <span>{{ pool.overlayDescription }}</span>
              <span>{{ pool.projectionRationale }}</span>
              <span>{{ pool.rationale || '--' }}</span>
            </div>
          </div>
        </div>

        <div class="tag-filter-strip">
          <span class="filter-label">tags</span>
          <button
            class="chip"
            :class="{ active: !selectedAnnotationTypeKeys.length }"
            @click="clearAnnotationTypeSelection()"
          >
            todas
          </button>
          <button
            v-for="item in ANNOTATION_LEGEND_ITEMS"
            :key="`${asset.key}-annot-filter-${item.type}`"
            class="chip chip-annotation-filter"
            :class="{ active: selectedAnnotationTypeKeys.includes(item.type) }"
            @click="toggleAnnotationTypeSelection(item.type)"
          >
            {{ item.shortLabel }}
          </button>
        </div>

</template>

<script>
import { injectMacroHeatmapContext } from '../context'

export default {
  name: 'MacroQuickChartControls',
  props: { asset: { type: Object, required: true } },
  setup() {
    return injectMacroHeatmapContext()
  },
}
</script>

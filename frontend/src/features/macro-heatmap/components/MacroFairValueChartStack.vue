<template>
            <div class="fair-value-chart-stack">
              <div class="indicator-chart-head fair-value-feature-head">
                <div class="indicator-chart-title">Fair value dedicado</div>
                <div class="indicator-chart-legend">
                  <span class="indicator-legend-item">
                    <span class="indicator-legend-swatch fair-value-swatch-price" />
                    preco
                    <strong>{{ formatPrice(asset.fairValueFeatureChart.currentPrice) }}</strong>
                  </span>
                  <span class="indicator-legend-item">
                    <span class="indicator-legend-swatch fair-value-swatch-fv" />
                    fv core
                    <strong>{{ formatPrice(asset.fairValueFeatureChart.currentFairValue) }}</strong>
                  </span>
                  <span class="indicator-legend-item">
                    <span class="indicator-legend-swatch fair-value-swatch-quality" />
                    q adj
                    <strong>{{ formatPrice(asset.fairValueFeatureChart.currentQualityAdjusted) }}</strong>
                  </span>
                  <span class="indicator-legend-item">
                    <span class="indicator-legend-swatch fair-value-swatch-fv-legacy" />
                    fv antigo
                    <strong>{{ formatPrice(asset.fairValueFeatureChart.legacyFairValue) }}</strong>
                  </span>
                  <span class="indicator-legend-item">
                    <span class="indicator-legend-swatch fair-value-swatch-band-legacy" />
                    banda antiga
                    <strong>{{ formatPrice(asset.fairValueFeatureChart.currentLegacyBandLow) }} -> {{ formatPrice(asset.fairValueFeatureChart.currentLegacyBandHigh) }}</strong>
                  </span>
                  <span class="indicator-legend-item">
                    <span class="indicator-legend-swatch fair-value-swatch-band" />
                    banda
                    <strong>{{ formatPrice(asset.fairValueFeatureChart.currentBandLow) }} -> {{ formatPrice(asset.fairValueFeatureChart.currentBandHigh) }}</strong>
                  </span>
                  <span class="indicator-legend-item">
                    <span class="indicator-legend-swatch fair-value-swatch-ribbon" />
                    ribbon
                    <strong>{{ formatPrice(asset.fairValueFeatureChart.currentQualityRibbonLow) }} -> {{ formatPrice(asset.fairValueFeatureChart.currentQualityRibbonHigh) }}</strong>
                  </span>
                  <span class="indicator-legend-item">
                    <span class="indicator-legend-swatch fair-value-swatch-distortion" />
                    dist
                    <strong>{{ formatSignedPoints(asset.fairValueFeatureChart.currentDislocation) }}</strong>
                  </span>
                  <span class="indicator-legend-item">
                    <span class="indicator-legend-swatch fair-value-swatch-leg" />
                    perna
                    <strong>{{ asset.fairValueFeatureChart.dominantLegLabel || '--' }}</strong>
                  </span>
                  <span
                    v-for="series in asset.fairValueFeatureChart.legLineSeries"
                    :key="`${asset.key}-${series.key}-legend`"
                    class="indicator-legend-item"
                    :title="series.description || series.label"
                  >
                    <span class="indicator-legend-swatch" :style="{ backgroundColor: series.color, opacity: series.opacity }" />
                    {{ series.shortLabel }}
                    <strong>{{ formatPrice(series.lastValue) }}</strong>
                  </span>
                </div>
              </div>

              <div class="fair-value-leg-help-strip">
                <div class="fair-value-leg-help-group">
                  <span class="fair-value-leg-help-title">core</span>
                  <div class="fair-value-leg-help-items">
                    <div
                      v-for="item in FAIR_VALUE_CORE_LEG_OPTIONS"
                      :key="`${asset.key}-fv-core-help-${item.key}`"
                      class="fair-value-leg-help-item"
                      :title="item.description"
                    >
                      <span class="fair-value-leg-help-badge" :style="{ color: item.color, borderColor: `${item.color}33` }">
                        {{ item.shortLabel }}
                      </span>
                      <div class="fair-value-leg-help-copy">
                        <strong>{{ item.label }}</strong>
                        <span>{{ item.description }}</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div class="fair-value-leg-help-group">
                  <span class="fair-value-leg-help-title">shadow</span>
                  <div class="fair-value-leg-help-items">
                    <div
                      v-for="item in FAIR_VALUE_SHADOW_LEG_OPTIONS"
                      :key="`${asset.key}-fv-shadow-help-${item.key}`"
                      class="fair-value-leg-help-item shadow"
                      :title="item.description"
                    >
                      <span class="fair-value-leg-help-badge" :style="{ color: item.color, borderColor: `${item.color}33` }">
                        {{ item.shortLabel }}
                      </span>
                      <div class="fair-value-leg-help-copy">
                        <strong>{{ item.label }}</strong>
                        <span>{{ item.description }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <svg
                :viewBox="`0 0 ${asset.fairValueFeatureChart.width} ${asset.fairValueFeatureChart.height}`"
                class="indicator-chart fair-value-feature-chart"
              >
                <rect
                  :x="asset.fairValueFeatureChart.plotLeft"
                  :y="asset.fairValueFeatureChart.plotTop"
                  :width="asset.fairValueFeatureChart.plotRight - asset.fairValueFeatureChart.plotLeft"
                  :height="asset.fairValueFeatureChart.plotBottom - asset.fairValueFeatureChart.plotTop"
                  class="plot-bg indicator-plot-bg"
                  rx="12"
                />

                <g v-for="tick in asset.fairValueFeatureChart.yTicks" :key="`${asset.key}-fv-y-${tick.value}`">
                  <line
                    :x1="asset.fairValueFeatureChart.plotLeft"
                    :x2="asset.fairValueFeatureChart.plotRight"
                    :y1="tick.y"
                    :y2="tick.y"
                    class="grid indicator-grid"
                  />
                  <text
                    :x="asset.fairValueFeatureChart.plotLeft - 8"
                    :y="tick.y + 4"
                    class="axis-label"
                    text-anchor="end"
                  >
                    {{ tick.label }}
                  </text>
                </g>

                <g v-for="tick in asset.fairValueFeatureChart.xTicks" :key="`${asset.key}-fv-x-${tick.label}-${tick.x}`">
                  <line
                    :x1="tick.x"
                    :x2="tick.x"
                    :y1="asset.fairValueFeatureChart.plotTop"
                    :y2="asset.fairValueFeatureChart.plotBottom"
                    class="grid indicator-grid vertical"
                  />
                  <text
                    :x="tick.x"
                    :y="asset.fairValueFeatureChart.plotBottom + 16"
                    class="axis-label time"
                    text-anchor="middle"
                  >
                    {{ tick.label }}
                  </text>
                </g>

                <path
                  v-if="asset.fairValueFeatureChart.qualityRibbonAreaPath"
                  :d="asset.fairValueFeatureChart.qualityRibbonAreaPath"
                  class="fair-value-feature-ribbon-area"
                />
                <path
                  v-if="asset.fairValueFeatureChart.qualityRibbonUpperPath"
                  :d="asset.fairValueFeatureChart.qualityRibbonUpperPath"
                  class="fair-value-feature-ribbon-line"
                />
                <path
                  v-if="asset.fairValueFeatureChart.qualityRibbonLowerPath"
                  :d="asset.fairValueFeatureChart.qualityRibbonLowerPath"
                  class="fair-value-feature-ribbon-line"
                />
                <path
                  v-if="asset.fairValueFeatureChart.legacyBandAreaPath"
                  :d="asset.fairValueFeatureChart.legacyBandAreaPath"
                  class="fair-value-feature-legacy-band-area"
                />
                <path
                  v-if="asset.fairValueFeatureChart.legacyUpperBandPath"
                  :d="asset.fairValueFeatureChart.legacyUpperBandPath"
                  class="fair-value-feature-legacy-band-line"
                />
                <path
                  v-if="asset.fairValueFeatureChart.legacyLowerBandPath"
                  :d="asset.fairValueFeatureChart.legacyLowerBandPath"
                  class="fair-value-feature-legacy-band-line"
                />
                <path
                  v-if="asset.fairValueFeatureChart.bandAreaPath"
                  :d="asset.fairValueFeatureChart.bandAreaPath"
                  class="fair-value-feature-band-area"
                />
                <path
                  v-if="asset.fairValueFeatureChart.upperBandPath"
                  :d="asset.fairValueFeatureChart.upperBandPath"
                  class="fair-value-feature-band-line"
                />
                <path
                  v-if="asset.fairValueFeatureChart.lowerBandPath"
                  :d="asset.fairValueFeatureChart.lowerBandPath"
                  class="fair-value-feature-band-line"
                />

                <path
                  v-for="series in asset.fairValueFeatureChart.legLineSeries"
                  :key="`${asset.key}-${series.key}-path`"
                  :d="series.path"
                  class="fair-value-feature-leg-line"
                  :stroke="series.color"
                  :stroke-opacity="series.opacity"
                  :stroke-dasharray="series.dashArray"
                />

                <path
                  v-if="asset.fairValueFeatureChart.pricePath"
                  :d="asset.fairValueFeatureChart.pricePath"
                  class="fair-value-feature-price-line"
                />
                <path
                  v-if="asset.fairValueFeatureChart.fairValuePath"
                  :d="asset.fairValueFeatureChart.fairValuePath"
                  class="fair-value-feature-fv-line"
                />
                <path
                  v-if="asset.fairValueFeatureChart.qualityAdjustedPath"
                  :d="asset.fairValueFeatureChart.qualityAdjustedPath"
                  class="fair-value-feature-quality-line"
                />
                <path
                  v-if="asset.fairValueFeatureChart.legacyFairValuePath"
                  :d="asset.fairValueFeatureChart.legacyFairValuePath"
                  class="fair-value-feature-fv-legacy-line"
                />

                <g v-for="marker in asset.fairValueFeatureChart.gammaMarkers" :key="marker.key">
                  <line
                    :x1="asset.fairValueFeatureChart.plotLeft"
                    :x2="asset.fairValueFeatureChart.plotRight"
                    :y1="marker.y"
                    :y2="marker.y"
                    class="fair-value-feature-gamma-line"
                    :stroke="marker.color"
                    :stroke-opacity="marker.opacity"
                    :stroke-dasharray="marker.dashArray"
                  />
                  <text
                    :x="asset.fairValueFeatureChart.plotLeft + 10"
                    :y="marker.y - 2"
                    class="fair-value-feature-gamma-tag"
                    :fill="marker.color"
                    text-anchor="start"
                  >
                    {{ marker.label }}
                  </text>
                </g>

                <g v-for="bar in asset.fairValueFeatureChart.distortionBars" :key="bar.key">
                  <rect
                    :x="bar.x"
                    :y="bar.y"
                    :width="bar.width"
                    :height="bar.height"
                    :fill="bar.fill"
                    :fill-opacity="bar.opacity"
                    rx="2"
                  />
                </g>

                <g v-for="leg in asset.fairValueFeatureChart.legBars" :key="leg.key">
                  <rect
                    :x="leg.x"
                    :y="leg.y"
                    :width="leg.width"
                    :height="leg.height"
                    :fill="leg.fill"
                    :fill-opacity="leg.opacity"
                    rx="3"
                  />
                </g>
              </svg>
            </div>
</template>

<script>
import { injectMacroHeatmapContext } from '../context'

export default {
  name: 'MacroFairValueChartStack',
  props: { asset: { type: Object, required: true } },
  setup() {
    return injectMacroHeatmapContext()
  },
}
</script>

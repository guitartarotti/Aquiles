<template>
        <div v-if="asset.indicatorChart?.hasVisibleLines" class="indicator-chart-wrap">
          <div class="indicator-chart-head">
            <div class="indicator-chart-title">Indicadores secundarios</div>
            <div class="indicator-chart-legend">
              <span
                v-for="series in asset.indicatorChart.series"
                :key="series.key"
                class="indicator-legend-item"
              >
                <span
                  class="indicator-legend-swatch"
                  :style="{ backgroundColor: series.color, opacity: series.opacity }"
                />
                {{ series.shortLabel }}
                <strong>{{ formatPressureScore(series.lastValue) }}</strong>
              </span>
            </div>
          </div>
          <svg
            :viewBox="`0 0 ${asset.indicatorChart.width} ${asset.indicatorChart.height}`"
            class="indicator-chart"
          >
            <rect
              :x="asset.indicatorChart.plotLeft"
              :y="asset.indicatorChart.plotTop"
              :width="asset.indicatorChart.plotRight - asset.indicatorChart.plotLeft"
              :height="asset.indicatorChart.plotBottom - asset.indicatorChart.plotTop"
              class="plot-bg indicator-plot-bg"
              rx="12"
            />

            <g v-for="tick in asset.indicatorChart.yTicks" :key="`${asset.key}-ind-y-${tick.value}`">
              <line
                :x1="asset.indicatorChart.plotLeft"
                :x2="asset.indicatorChart.plotRight"
                :y1="tick.y"
                :y2="tick.y"
                class="grid indicator-grid"
              />
              <text
                :x="asset.indicatorChart.plotLeft - 8"
                :y="tick.y + 4"
                class="axis-label"
                text-anchor="end"
              >
                {{ tick.label }}
              </text>
            </g>

            <g v-for="series in asset.indicatorChart.series" :key="series.key">
              <path
                :d="series.path"
                class="indicator-line"
                :stroke="series.color"
                :stroke-dasharray="series.dashArray"
                :stroke-opacity="series.opacity"
              />
            </g>
          </svg>
        </div>

        <div v-if="asset.histogramChart?.hasVisibleBars" class="indicator-chart-wrap histogram-chart-wrap">
          <div class="indicator-chart-head">
            <div class="indicator-chart-title">Histograma acumulado</div>
            <div class="indicator-chart-legend">
              <span
                v-for="series in asset.histogramChart.series"
                :key="series.key"
                class="indicator-legend-item"
              >
                <span
                  class="indicator-legend-swatch"
                  :style="{ backgroundColor: series.color, opacity: 0.5 }"
                />
                {{ series.shortLabel }}
                <strong>{{ formatCompactSignedQuantity(series.lastValue) }}</strong>
              </span>
            </div>
          </div>
          <svg
            :viewBox="`0 0 ${asset.histogramChart.width} ${asset.histogramChart.height}`"
            class="indicator-chart"
          >
            <rect
              :x="asset.histogramChart.plotLeft"
              :y="asset.histogramChart.plotTop"
              :width="asset.histogramChart.plotRight - asset.histogramChart.plotLeft"
              :height="asset.histogramChart.plotBottom - asset.histogramChart.plotTop"
              class="plot-bg indicator-plot-bg"
              rx="12"
            />

            <g v-for="tick in asset.histogramChart.yTicks" :key="`${asset.key}-hist-y-${tick.value}`">
              <line
                :x1="asset.histogramChart.plotLeft"
                :x2="asset.histogramChart.plotRight"
                :y1="tick.y"
                :y2="tick.y"
                class="grid indicator-grid"
              />
              <text
                :x="asset.histogramChart.plotLeft - 8"
                :y="tick.y + 4"
                class="axis-label"
                text-anchor="end"
              >
                {{ tick.label }}
              </text>
            </g>

            <line
              v-if="asset.histogramChart.zeroY != null"
              :x1="asset.histogramChart.plotLeft"
              :x2="asset.histogramChart.plotRight"
              :y1="asset.histogramChart.zeroY"
              :y2="asset.histogramChart.zeroY"
              class="zero-line"
            />

            <g v-for="bar in asset.histogramChart.bars" :key="bar.key">
              <rect
                :x="bar.x"
                :y="bar.y"
                :width="bar.width"
                :height="bar.height"
                class="histogram-bar"
                :fill="bar.fill"
                :fill-opacity="bar.opacity"
                rx="2"
              />
            </g>
          </svg>
        </div>

        <div v-if="asset.regimeChart?.hasVisibleLines" class="indicator-chart-wrap regime-chart-wrap">
          <div class="indicator-chart-head">
            <div class="indicator-chart-title">Absorption vs initiative no tempo</div>
            <div class="indicator-chart-legend">
              <span
                v-for="series in asset.regimeChart.series"
                :key="series.key"
                class="indicator-legend-item"
              >
                <span
                  class="indicator-legend-swatch"
                  :style="{ backgroundColor: series.color, opacity: 0.92 }"
                />
                {{ series.shortLabel }}
                <strong>{{ formatFlowRegimeLabel(series.lastState) }}</strong>
              </span>
            </div>
          </div>
          <svg
            :viewBox="`0 0 ${asset.regimeChart.width} ${asset.regimeChart.height}`"
            class="indicator-chart"
          >
            <rect
              :x="asset.regimeChart.plotLeft"
              :y="asset.regimeChart.plotTop"
              :width="asset.regimeChart.plotRight - asset.regimeChart.plotLeft"
              :height="asset.regimeChart.plotBottom - asset.regimeChart.plotTop"
              class="plot-bg indicator-plot-bg"
              rx="12"
            />

            <g v-for="tick in asset.regimeChart.yTicks" :key="`${asset.key}-regime-y-${tick.value}`">
              <line
                :x1="asset.regimeChart.plotLeft"
                :x2="asset.regimeChart.plotRight"
                :y1="tick.y"
                :y2="tick.y"
                class="grid indicator-grid"
              />
              <text
                :x="asset.regimeChart.plotLeft - 8"
                :y="tick.y + 4"
                class="axis-label"
                text-anchor="end"
              >
                {{ tick.label }}
              </text>
            </g>

            <g v-for="series in asset.regimeChart.series" :key="series.key">
              <path
                :d="series.path"
                class="indicator-line"
                :stroke="series.color"
                stroke-dasharray="0"
                stroke-opacity="0.94"
              />
            </g>
          </svg>
        </div>

        <div v-if="asset.divergenceChart?.hasVisibleLines" class="indicator-chart-wrap divergence-chart-wrap">
          <div class="indicator-chart-head">
            <div class="indicator-chart-title">Foreign vs retail divergence no tempo</div>
            <div class="indicator-chart-legend">
              <span
                v-for="series in asset.divergenceChart.series"
                :key="series.key"
                class="indicator-legend-item"
              >
                <span
                  class="indicator-legend-swatch"
                  :style="{ backgroundColor: series.color, opacity: 0.92 }"
                />
                {{ series.shortLabel }}
                <strong>{{ formatPressureScore(series.lastValue) }}</strong>
              </span>
            </div>
          </div>
          <svg
            :viewBox="`0 0 ${asset.divergenceChart.width} ${asset.divergenceChart.height}`"
            class="indicator-chart"
          >
            <rect
              :x="asset.divergenceChart.plotLeft"
              :y="asset.divergenceChart.plotTop"
              :width="asset.divergenceChart.plotRight - asset.divergenceChart.plotLeft"
              :height="asset.divergenceChart.plotBottom - asset.divergenceChart.plotTop"
              class="plot-bg indicator-plot-bg"
              rx="12"
            />

            <g v-for="tick in asset.divergenceChart.yTicks" :key="`${asset.key}-div-y-${tick.value}`">
              <line
                :x1="asset.divergenceChart.plotLeft"
                :x2="asset.divergenceChart.plotRight"
                :y1="tick.y"
                :y2="tick.y"
                class="grid indicator-grid"
              />
              <text
                :x="asset.divergenceChart.plotLeft - 8"
                :y="tick.y + 4"
                class="axis-label"
                text-anchor="end"
              >
                {{ tick.label }}
              </text>
            </g>

            <g v-for="series in asset.divergenceChart.series" :key="series.key">
              <path
                :d="series.path"
                class="indicator-line"
                :stroke="series.color"
                :stroke-dasharray="series.dashArray"
                :stroke-opacity="series.opacity"
              />
            </g>
          </svg>
        </div>

</template>

<script>
import { injectMacroHeatmapContext } from '../context'

export default {
  name: 'MacroQuickChartIndicators',
  props: { asset: { type: Object, required: true } },
  setup() {
    return injectMacroHeatmapContext()
  },
}
</script>

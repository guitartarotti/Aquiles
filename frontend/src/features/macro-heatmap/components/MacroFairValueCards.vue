<template>
            <div
              v-if="asset.fairValueFeatureChart.qualityModel?.qualityPulse"
              class="fair-value-quality-pulse"
            >
              <div class="fair-value-quality-pulse-head">
                <div class="fair-value-quality-pulse-copy">
                  <span class="metric-label-with-help fair-value-quality-pulse-eyebrow">
                    <span>Qualidade geral</span>
                    <span class="info-help" tabindex="0" role="note" :aria-label="FAIR_VALUE_HELP_TEXT.quality_pulse">
                      i
                      <span class="info-help-tooltip">{{ FAIR_VALUE_HELP_TEXT.quality_pulse }}</span>
                    </span>
                  </span>
                  <strong>{{ asset.fairValueFeatureChart.qualityModel.qualityPulse.headline }}</strong>
                  <span class="fair-value-quality-pulse-summary">{{ asset.fairValueFeatureChart.qualityModel.qualityPulse.summary }}</span>
                </div>
                <div
                  class="fair-value-quality-pulse-badge"
                  :class="asset.fairValueFeatureChart.qualityModel.qualityPulse.toneClass"
                >
                  {{ asset.fairValueFeatureChart.qualityModel.qualityPulse.directionLabel }}
                </div>
              </div>

              <div class="fair-value-quality-pulse-track">
                <div
                  class="fair-value-quality-pulse-fill"
                  :class="asset.fairValueFeatureChart.qualityModel.qualityPulse.toneClass"
                  :style="{ width: `${asset.fairValueFeatureChart.qualityModel.qualityPulse.strengthPercent}%` }"
                />
              </div>

              <div class="fair-value-quality-pulse-meta">
                <span>forca {{ asset.fairValueFeatureChart.qualityModel.qualityPulse.strengthLabel }}</span>
                <span>estado {{ asset.fairValueFeatureChart.qualityModel.qualityPulse.sentimentLabel }}</span>
                <span>janela {{ asset.fairValueFeatureChart.qualityModel.qualityPulse.windowLabel }}</span>
              </div>

              <div class="fair-value-quality-pulse-grid">
                <div class="fair-value-quality-pulse-pill">
                  <span>qualidade delta</span>
                  <strong>{{ asset.fairValueFeatureChart.qualityModel.qualityPulse.healthDeltaLabel }}</strong>
                </div>
                <div class="fair-value-quality-pulse-pill">
                  <span>shadow gap</span>
                  <strong>{{ asset.fairValueFeatureChart.qualityModel.qualityPulse.shadowGapLabel }}</strong>
                </div>
                <div class="fair-value-quality-pulse-pill">
                  <span>gap delta</span>
                  <strong>{{ asset.fairValueFeatureChart.qualityModel.qualityPulse.shadowGapDeltaLabel }}</strong>
                </div>
                <div class="fair-value-quality-pulse-pill">
                  <span>preco delta</span>
                  <strong>{{ asset.fairValueFeatureChart.qualityModel.qualityPulse.priceDeltaLabel }}</strong>
                </div>
              </div>

              <div class="fair-value-quality-pulse-foot">
                <div class="fair-value-quality-pulse-spark" aria-hidden="true">
                  <span
                    v-for="point in asset.fairValueFeatureChart.qualityModel.qualityPulse.series"
                    :key="point.key"
                    class="fair-value-quality-pulse-bar"
                    :class="point.toneClass"
                    :style="{ height: `${point.heightPercent}%` }"
                  />
                </div>
                <div
                  class="fair-value-quality-pulse-follow"
                  :class="asset.fairValueFeatureChart.qualityModel.qualityPulse.followThroughClass"
                >
                  {{ asset.fairValueFeatureChart.qualityModel.qualityPulse.followThroughLabel }}
                </div>
              </div>
            </div>

            <div
              v-if="asset.fairValueFeatureChart.qualityModel?.qualityHistory"
              class="fair-value-quality-history"
            >
              <div class="fair-value-quality-history-head">
                <div class="fair-value-quality-history-copy">
                  <span class="fair-value-quality-history-eyebrow">Historico da qualidade</span>
                  <strong>{{ asset.fairValueFeatureChart.qualityModel.qualityHistory.headline }}</strong>
                  <span class="fair-value-quality-history-summary">{{ asset.fairValueFeatureChart.qualityModel.qualityHistory.summary }}</span>
                </div>
                <div
                  class="fair-value-quality-history-badge"
                  :class="asset.fairValueFeatureChart.qualityModel.qualityHistory.toneClass"
                >
                  {{ asset.fairValueFeatureChart.qualityModel.qualityHistory.deltaLabel }}
                </div>
              </div>

              <div class="fair-value-quality-history-grid">
                <div class="fair-value-quality-history-pill">
                  <span>score atual</span>
                  <strong>{{ asset.fairValueFeatureChart.qualityModel.qualityHistory.latestScoreLabel }}</strong>
                </div>
                <div class="fair-value-quality-history-pill">
                  <span>impulso</span>
                  <strong>{{ asset.fairValueFeatureChart.qualityModel.qualityHistory.impulseLabel }}</strong>
                </div>
                <div class="fair-value-quality-history-pill">
                  <span>shadow gap</span>
                  <strong>{{ asset.fairValueFeatureChart.qualityModel.qualityHistory.latestGapLabel }}</strong>
                </div>
                <div class="fair-value-quality-history-pill">
                  <span>janela</span>
                  <strong>{{ asset.fairValueFeatureChart.qualityModel.qualityHistory.windowLabel }}</strong>
                </div>
              </div>

              <svg
                :viewBox="`0 0 ${asset.fairValueFeatureChart.qualityModel.qualityHistory.width} ${asset.fairValueFeatureChart.qualityModel.qualityHistory.height}`"
                class="fair-value-quality-history-chart"
                aria-hidden="true"
              >
                <rect
                  :x="asset.fairValueFeatureChart.qualityModel.qualityHistory.plotLeft"
                  :y="asset.fairValueFeatureChart.qualityModel.qualityHistory.plotTop"
                  :width="asset.fairValueFeatureChart.qualityModel.qualityHistory.plotRight - asset.fairValueFeatureChart.qualityModel.qualityHistory.plotLeft"
                  :height="asset.fairValueFeatureChart.qualityModel.qualityHistory.plotBottom - asset.fairValueFeatureChart.qualityModel.qualityHistory.plotTop"
                  class="fair-value-quality-history-plot"
                  rx="16"
                />
                <g
                  v-for="guide in asset.fairValueFeatureChart.qualityModel.qualityHistory.guideLines"
                  :key="`quality-history-guide-${guide.value}`"
                >
                  <line
                    :x1="asset.fairValueFeatureChart.qualityModel.qualityHistory.plotLeft"
                    :x2="asset.fairValueFeatureChart.qualityModel.qualityHistory.plotRight"
                    :y1="guide.y"
                    :y2="guide.y"
                    class="fair-value-quality-history-guide"
                    :class="{ emphasis: guide.emphasis }"
                  />
                  <text
                    :x="asset.fairValueFeatureChart.qualityModel.qualityHistory.plotRight - 2"
                    :y="guide.y - 4"
                    class="fair-value-quality-history-guide-label"
                    text-anchor="end"
                  >
                    {{ guide.label }}
                  </text>
                </g>
                <line
                  :x1="asset.fairValueFeatureChart.qualityModel.qualityHistory.plotLeft"
                  :x2="asset.fairValueFeatureChart.qualityModel.qualityHistory.plotRight"
                  :y1="asset.fairValueFeatureChart.qualityModel.qualityHistory.baselineY"
                  :y2="asset.fairValueFeatureChart.qualityModel.qualityHistory.baselineY"
                  class="fair-value-quality-history-baseline"
                />
                <path
                  :d="asset.fairValueFeatureChart.qualityModel.qualityHistory.areaPath"
                  class="fair-value-quality-history-area"
                  :class="asset.fairValueFeatureChart.qualityModel.qualityHistory.toneClass"
                />
                <path
                  :d="asset.fairValueFeatureChart.qualityModel.qualityHistory.linePath"
                  class="fair-value-quality-history-line"
                  :class="asset.fairValueFeatureChart.qualityModel.qualityHistory.toneClass"
                />
                <circle
                  v-for="point in asset.fairValueFeatureChart.qualityModel.qualityHistory.points"
                  :key="point.key"
                  :cx="point.x"
                  :cy="point.y"
                  :r="point.radius"
                  class="fair-value-quality-history-point"
                  :class="[point.toneClass, { latest: point.isLatest }]"
                />
              </svg>

              <div class="fair-value-quality-history-axis">
                <span
                  v-for="tick in asset.fairValueFeatureChart.qualityModel.qualityHistory.ticks"
                  :key="tick.key"
                >
                  {{ tick.label }}
                </span>
              </div>
            </div>
</template>

<script>
import { injectMacroHeatmapContext } from '../context'

export default {
  name: 'MacroFairValueCards',
  props: { asset: { type: Object, required: true } },
  setup() {
    return injectMacroHeatmapContext()
  },
}
</script>

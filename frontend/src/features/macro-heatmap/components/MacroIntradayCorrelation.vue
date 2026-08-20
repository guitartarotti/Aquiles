<template>
          <div
            v-if="asset.key === 'win' && intradayCorrelationHistoryPanel"
            class="intraday-correlation-card"
          >
            <div class="intraday-correlation-head">
              <div class="intraday-correlation-copy">
                <span class="intraday-correlation-eyebrow">Correlacao historica</span>
                <strong>{{ intradayCorrelationHistoryPanel.headline }}</strong>
                <span class="intraday-correlation-summary">{{ intradayCorrelationHistoryPanel.summary }}</span>
              </div>
              <div
                class="intraday-correlation-badge"
                :class="intradayCorrelationHistoryPanel.toneClass"
              >
                {{ intradayCorrelationHistoryPanel.statusLabel }}
              </div>
            </div>

            <div class="intraday-correlation-toolbar">
              <div class="intraday-correlation-toolbar-group">
                <span class="filter-label">dias</span>
                <button
                  v-for="option in CORRELATION_LOOKBACK_OPTIONS"
                  :key="`corr-day-${option.days}`"
                  type="button"
                  class="chip"
                  :class="{ active: correlationLookbackDays === option.days }"
                  @click="setCorrelationLookbackDays(option.days)"
                >
                  {{ option.label }}
                </button>
              </div>
              <div class="intraday-correlation-toolbar-group">
                <span class="filter-label">janela</span>
                <button
                  v-for="option in CORRELATION_HORIZON_OPTIONS"
                  :key="`corr-h-${option.minutes}`"
                  type="button"
                  class="chip"
                  :class="{ active: correlationHorizonMinutes === option.minutes }"
                  @click="setCorrelationHorizonMinutes(option.minutes)"
                >
                  {{ option.label }}
                </button>
              </div>
              <div class="intraday-correlation-toolbar-group">
                <span class="filter-label">modo</span>
                <button
                  v-for="option in CORRELATION_MODE_OPTIONS"
                  :key="`corr-mode-${option.key}`"
                  type="button"
                  class="chip"
                  :class="{ active: selectedCorrelationModes.includes(option.key) }"
                  @click="toggleCorrelationMode(option.key)"
                >
                  {{ option.label }}
                </button>
              </div>
            </div>

            <div class="intraday-correlation-factor-strip">
              <span class="filter-label">ativos</span>
              <div class="intraday-correlation-factor-chips">
                <button
                  v-for="factor in intradayCorrelationHistoryPanel.availableFactors"
                  :key="`corr-factor-${factor.factor}`"
                  type="button"
                  class="chip"
                  :class="{ active: selectedCorrelationFactorKeys.includes(factor.factor) }"
                  @click="toggleCorrelationFactor(factor.factor)"
                >
                  {{ factor.label }}
                </button>
              </div>
            </div>

            <div class="intraday-correlation-meta">
              <span>sessoes {{ intradayCorrelationHistoryPanel.sessionsLabel }}</span>
              <span>{{ intradayCorrelationHistoryPanel.rowCountLabel }}</span>
              <span>{{ intradayCorrelationHistoryPanel.neuralLabel }}</span>
            </div>

            <svg
              v-if="intradayCorrelationHistoryPanel.hasSeries"
              :viewBox="`0 0 ${intradayCorrelationHistoryPanel.width} ${intradayCorrelationHistoryPanel.height}`"
              class="intraday-correlation-chart"
              aria-hidden="true"
            >
              <rect
                :x="intradayCorrelationHistoryPanel.plotLeft"
                :y="intradayCorrelationHistoryPanel.plotTop"
                :width="intradayCorrelationHistoryPanel.plotRight - intradayCorrelationHistoryPanel.plotLeft"
                :height="intradayCorrelationHistoryPanel.plotBottom - intradayCorrelationHistoryPanel.plotTop"
                class="intraday-correlation-plot"
                rx="16"
              />
              <g
                v-for="guide in intradayCorrelationHistoryPanel.guideLines"
                :key="`corr-guide-${guide.value}`"
              >
                <line
                  :x1="intradayCorrelationHistoryPanel.plotLeft"
                  :x2="intradayCorrelationHistoryPanel.plotRight"
                  :y1="guide.y"
                  :y2="guide.y"
                  class="intraday-correlation-guide"
                  :class="{ emphasis: guide.emphasis }"
                />
                <text
                  :x="intradayCorrelationHistoryPanel.plotRight - 2"
                  :y="guide.y - 4"
                  class="intraday-correlation-guide-label"
                  text-anchor="end"
                >
                  {{ guide.label }}
                </text>
              </g>
              <line
                :x1="intradayCorrelationHistoryPanel.plotLeft"
                :x2="intradayCorrelationHistoryPanel.plotRight"
                :y1="intradayCorrelationHistoryPanel.baselineY"
                :y2="intradayCorrelationHistoryPanel.baselineY"
                class="intraday-correlation-baseline"
              />
              <path
                v-for="series in intradayCorrelationHistoryPanel.series"
                :key="`${series.key}-path`"
                :d="series.path"
                class="intraday-correlation-line"
                :stroke="series.color"
                :stroke-dasharray="series.dashArray"
              />
              <circle
                v-for="series in intradayCorrelationHistoryPanel.series"
                :key="`${series.key}-latest`"
                :cx="series.latestPoint?.x"
                :cy="series.latestPoint?.y"
                r="3.8"
                class="intraday-correlation-point"
                :fill="series.color"
              />
              <g
                v-for="tick in intradayCorrelationHistoryPanel.ticks"
                :key="tick.key"
              >
                <text
                  :x="tick.x"
                  :y="intradayCorrelationHistoryPanel.plotBottom + 16"
                  class="intraday-correlation-tick"
                  text-anchor="middle"
                >
                  {{ tick.label }}
                </text>
              </g>
            </svg>

            <div v-else class="intraday-correlation-empty">
              Historico ainda curto para gerar a serie completa neste recorte.
            </div>

            <div v-if="intradayCorrelationHistoryPanel.series.length" class="intraday-correlation-legend">
              <span
                v-for="series in intradayCorrelationHistoryPanel.series"
                :key="`${series.key}-legend`"
                class="intraday-correlation-legend-item"
              >
                <span class="intraday-correlation-legend-swatch" :style="{ background: series.color }" />
                <span>{{ series.legendLabel }}</span>
                <strong>{{ formatSignedFloat(series.latestValue) }}</strong>
              </span>
            </div>

            <div class="intraday-correlation-note">
              {{ intradayCorrelationHistoryPanel.note }}
            </div>
          </div>
</template>

<script>
import { injectMacroHeatmapContext } from '../context'

export default {
  name: 'MacroIntradayCorrelation',
  props: { asset: { type: Object, required: true } },
  setup() {
    return injectMacroHeatmapContext()
  },
}
</script>

<template>
          <div
            v-if="asset.key === 'win' && capturedFactorHistoryPanel"
            class="intraday-correlation-card captured-factor-history-card"
          >
            <div class="intraday-correlation-head">
              <div class="intraday-correlation-copy">
                <span class="intraday-correlation-eyebrow">Ativos da planilha</span>
                <strong>{{ capturedFactorHistoryPanel.headline }}</strong>
                <span class="intraday-correlation-summary">{{ capturedFactorHistoryPanel.summary }}</span>
              </div>
              <div
                class="intraday-correlation-badge"
                :class="capturedFactorHistoryPanel.toneClass"
              >
                {{ capturedFactorHistoryPanel.statusLabel }}
              </div>
            </div>

            <div class="intraday-correlation-toolbar">
              <div class="intraday-correlation-toolbar-group">
                <span class="filter-label">escala</span>
                <button
                  v-for="option in CAPTURED_FACTOR_DISPLAY_OPTIONS"
                  :key="`captured-mode-${option.key}`"
                  type="button"
                  class="chip"
                  :class="{ active: capturedFactorDisplayMode === option.key }"
                  @click="setCapturedFactorDisplayMode(option.key)"
                >
                  {{ option.label }}
                </button>
              </div>
              <div class="intraday-correlation-toolbar-group">
                <span class="filter-label">atalhos</span>
                <button type="button" class="chip" @click="selectCapturedTopMovers">
                  top movers
                </button>
                <button type="button" class="chip" @click="selectAllCapturedFactors">
                  todas
                </button>
                <button type="button" class="chip" @click="clearCapturedFactorSelection">
                  limpar
                </button>
              </div>
            </div>

            <div class="intraday-correlation-factor-strip">
              <div class="captured-factor-history-strip-head">
                <span class="filter-label">ativos capturados</span>
                <input
                  v-model="capturedFactorFilterText"
                  type="text"
                  class="captured-factor-history-filter"
                  placeholder="filtrar ativo"
                >
              </div>
              <div class="intraday-correlation-factor-chips">
                <button
                  v-for="factor in capturedFactorHistoryPanel.visibleFactors"
                  :key="`captured-factor-${factor.factor}`"
                  type="button"
                  class="chip"
                  :class="{ active: selectedCapturedFactorKeys.includes(factor.factor) }"
                  @click="toggleCapturedFactorSelection(factor.factor)"
                >
                  {{ factor.label }}
                </button>
              </div>
              <div v-if="!capturedFactorHistoryPanel.visibleFactors.length" class="intraday-correlation-empty">
                Nenhum ativo bate com o filtro atual.
              </div>
            </div>

            <div class="intraday-correlation-meta">
              <span>{{ capturedFactorHistoryPanel.selectionLabel }}</span>
              <span>{{ capturedFactorHistoryPanel.searchLabel }}</span>
              <span>{{ capturedFactorHistoryPanel.rowCountLabel }}</span>
              <span>escala {{ capturedFactorHistoryPanel.modeLabel }}</span>
            </div>

            <svg
              v-if="capturedFactorHistoryPanel.hasSeries"
              :viewBox="`0 0 ${capturedFactorHistoryPanel.width} ${capturedFactorHistoryPanel.height}`"
              class="intraday-correlation-chart"
              aria-hidden="true"
            >
              <rect
                :x="capturedFactorHistoryPanel.plotLeft"
                :y="capturedFactorHistoryPanel.plotTop"
                :width="capturedFactorHistoryPanel.plotRight - capturedFactorHistoryPanel.plotLeft"
                :height="capturedFactorHistoryPanel.plotBottom - capturedFactorHistoryPanel.plotTop"
                class="intraday-correlation-plot"
                rx="16"
              />
              <g
                v-for="guide in capturedFactorHistoryPanel.guideLines"
                :key="`captured-guide-${guide.value}`"
              >
                <line
                  :x1="capturedFactorHistoryPanel.plotLeft"
                  :x2="capturedFactorHistoryPanel.plotRight"
                  :y1="guide.y"
                  :y2="guide.y"
                  class="intraday-correlation-guide"
                  :class="{ emphasis: guide.emphasis }"
                />
                <text
                  :x="capturedFactorHistoryPanel.plotRight - 2"
                  :y="guide.y - 4"
                  class="intraday-correlation-guide-label"
                  text-anchor="end"
                >
                  {{ guide.label }}
                </text>
              </g>
              <line
                :x1="capturedFactorHistoryPanel.plotLeft"
                :x2="capturedFactorHistoryPanel.plotRight"
                :y1="capturedFactorHistoryPanel.baselineY"
                :y2="capturedFactorHistoryPanel.baselineY"
                class="intraday-correlation-baseline"
              />
              <path
                v-for="series in capturedFactorHistoryPanel.series"
                :key="`${series.key}-path`"
                :d="series.path"
                class="intraday-correlation-line"
                :stroke="series.color"
              />
              <circle
                v-for="series in capturedFactorHistoryPanel.series"
                :key="`${series.key}-latest`"
                :cx="series.latestPoint?.x"
                :cy="series.latestPoint?.y"
                r="3.8"
                class="intraday-correlation-point"
                :fill="series.color"
              />
              <g
                v-for="tick in capturedFactorHistoryPanel.ticks"
                :key="tick.key"
              >
                <text
                  :x="tick.x"
                  :y="capturedFactorHistoryPanel.plotBottom + 16"
                  class="intraday-correlation-tick"
                  text-anchor="middle"
                >
                  {{ tick.label }}
                </text>
              </g>
            </svg>

            <div v-else class="intraday-correlation-empty">
              Selecione um ou mais ativos com histórico suficiente para desenhar a série.
            </div>

            <div v-if="capturedFactorHistoryPanel.series.length" class="intraday-correlation-legend">
              <span
                v-for="series in capturedFactorHistoryPanel.series"
                :key="`${series.key}-legend`"
                class="intraday-correlation-legend-item"
              >
                <span class="intraday-correlation-legend-swatch" :style="{ background: series.color }" />
                <span>{{ series.legendLabel }}</span>
                <strong>{{ series.latestValueLabel }}</strong>
              </span>
            </div>

            <div class="intraday-correlation-note">
              {{ capturedFactorHistoryPanel.note }}
            </div>
          </div>
</template>

<script>
import { injectMacroHeatmapContext } from '../context'

export default {
  name: 'MacroCapturedFactorHistory',
  props: { asset: { type: Object, required: true } },
  setup() {
    return injectMacroHeatmapContext()
  },
}
</script>

<template>
            <aside v-if="asset.fairValueFeatureChart.qualityModel" class="fair-value-quality-panel">
              <div class="fair-value-quality-head">
                <span class="fair-value-quality-eyebrow">Fair Value Quality</span>
                <div
                  class="fair-value-quality-badge"
                  :class="fairValueSentimentClass(asset.fairValueFeatureChart.qualityModel.implicitSentiment)"
                >
                  {{ formatImplicitSentiment(asset.fairValueFeatureChart.qualityModel.implicitSentiment) }}
                </div>
              </div>

              <div class="fair-value-quality-kpis">
                <div class="fair-value-quality-kpi">
                  <span class="metric-label-with-help">
                    <span class="fair-value-quality-kpi-label">core fv</span>
                    <span class="info-help" tabindex="0" role="note" :aria-label="FAIR_VALUE_HELP_TEXT.core_fv">
                      i
                      <span class="info-help-tooltip">{{ FAIR_VALUE_HELP_TEXT.core_fv }}</span>
                    </span>
                  </span>
                  <strong>{{ formatPrice(asset.fairValueFeatureChart.currentFairValue) }}</strong>
                </div>
                <div class="fair-value-quality-kpi">
                  <span class="metric-label-with-help">
                    <span class="fair-value-quality-kpi-label">quality fv</span>
                    <span class="info-help" tabindex="0" role="note" :aria-label="FAIR_VALUE_HELP_TEXT.quality_fv">
                      i
                      <span class="info-help-tooltip">{{ FAIR_VALUE_HELP_TEXT.quality_fv }}</span>
                    </span>
                  </span>
                  <strong>{{ formatPrice(asset.fairValueFeatureChart.currentQualityAdjusted) }}</strong>
                </div>
                <div class="fair-value-quality-kpi">
                  <span class="fair-value-quality-kpi-label">distorção</span>
                  <strong>{{ formatSignedPoints(asset.fairValueFeatureChart.currentDislocation) }}</strong>
                </div>
                <div class="fair-value-quality-kpi">
                  <span class="metric-label-with-help">
                    <span class="fair-value-quality-kpi-label">ribbon</span>
                    <span class="info-help" tabindex="0" role="note" :aria-label="FAIR_VALUE_HELP_TEXT.ribbon">
                      i
                      <span class="info-help-tooltip">{{ FAIR_VALUE_HELP_TEXT.ribbon }}</span>
                    </span>
                  </span>
                  <strong>{{ formatPrice(asset.fairValueFeatureChart.currentQualityRibbonLow) }} → {{ formatPrice(asset.fairValueFeatureChart.currentQualityRibbonHigh) }}</strong>
                </div>
              </div>

              <div class="fair-value-gauge">
                <div class="fair-value-gauge-head">
                  <span>Quality gauge</span>
                  <strong>{{ formatCompactFloat(asset.fairValueFeatureChart.qualityModel.qualityGauge) }}</strong>
                </div>
                <div class="fair-value-gauge-track">
                  <div
                    class="fair-value-gauge-fill"
                    :class="fairValueGaugeClass(asset.fairValueFeatureChart.qualityModel.qualityGauge)"
                    :style="{ width: `${Math.max(0, Math.min(asset.fairValueFeatureChart.qualityModel.qualityGauge || 0, 100))}%` }"
                  />
                </div>
                <div class="fair-value-gauge-meta">
                  <span>conf {{ formatConfidenceScore(asset.fairValueFeatureChart.qualityModel.confidence) }}</span>
                  <span>sent {{ formatConfidenceScore(asset.fairValueFeatureChart.qualityModel.sentimentConfidence) }}</span>
                  <span>align {{ formatCompactFloat((asset.fairValueFeatureChart.qualityModel.coreShadowAlignment || 0) * 100) }}</span>
                </div>
              </div>

              <div class="fair-value-quality-grid">
                <div class="fair-value-quality-pill">
                  <span class="metric-label-with-help">
                    <span class="fair-value-quality-kpi-label">risk quality</span>
                    <span class="info-help" tabindex="0" role="note" :aria-label="FAIR_VALUE_HELP_TEXT.risk_quality">
                      i
                      <span class="info-help-tooltip">{{ FAIR_VALUE_HELP_TEXT.risk_quality }}</span>
                    </span>
                  </span>
                  <strong>{{ formatConfidenceScore(asset.fairValueFeatureChart.qualityModel.riskQualityScore) }}</strong>
                </div>
                <div class="fair-value-quality-pill">
                  <span class="metric-label-with-help">
                    <span class="fair-value-quality-kpi-label">coherence</span>
                    <span class="info-help" tabindex="0" role="note" :aria-label="FAIR_VALUE_HELP_TEXT.coherence">
                      i
                      <span class="info-help-tooltip">{{ FAIR_VALUE_HELP_TEXT.coherence }}</span>
                    </span>
                  </span>
                  <strong>{{ formatCompactFloat((asset.fairValueFeatureChart.qualityModel.coherenceScore || 0) * 100) }}</strong>
                </div>
                <div class="fair-value-quality-pill">
                  <span class="metric-label-with-help">
                    <span class="fair-value-quality-kpi-label">conv prob</span>
                    <span class="info-help" tabindex="0" role="note" :aria-label="FAIR_VALUE_HELP_TEXT.convergence_probability">
                      i
                      <span class="info-help-tooltip">{{ FAIR_VALUE_HELP_TEXT.convergence_probability }}</span>
                    </span>
                  </span>
                  <strong>{{ formatConfidenceScore((asset.fairValueFeatureChart.qualityModel.convergenceProbability || 0) * 100) }}</strong>
                </div>
                <div class="fair-value-quality-pill">
                  <span class="metric-label-with-help">
                    <span class="fair-value-quality-kpi-label">break prob</span>
                    <span class="info-help" tabindex="0" role="note" :aria-label="FAIR_VALUE_HELP_TEXT.regime_break_probability">
                      i
                      <span class="info-help-tooltip">{{ FAIR_VALUE_HELP_TEXT.regime_break_probability }}</span>
                    </span>
                  </span>
                  <strong>{{ formatConfidenceScore((asset.fairValueFeatureChart.qualityModel.regimeBreakProbability || 0) * 100) }}</strong>
                </div>
              </div>

              <div
                v-if="asset.fairValueFeatureChart.qualityModel.curveConditions && Object.keys(asset.fairValueFeatureChart.qualityModel.curveConditions).length"
                class="fair-value-curve-conditions"
              >
                <div class="fair-value-curve-head">
                  <div class="fair-value-curve-head-copy">
                    <span class="fair-value-curve-title">Curva DI do dia</span>
                    <span class="fair-value-curve-subtitle">
                      {{ formatCurveMacroRegime(asset.fairValueFeatureChart.qualityModel.curveConditions) }}
                    </span>
                  </div>
                  <strong>{{ formatCurveShapeLabel(asset.fairValueFeatureChart.qualityModel.curveConditions.state) }}</strong>
                </div>
                <div class="fair-value-curve-regime-strip">
                  <span
                    v-for="entry in getCurveRegimeRanking(asset.fairValueFeatureChart.qualityModel.curveConditions)"
                    :key="`${asset.key}-curve-regime-${entry.key}`"
                    class="fair-value-curve-regime-chip"
                  >
                    {{ entry.label }} {{ formatCurveProbability(entry.probability) }}
                  </span>
                </div>
                <div class="fair-value-curve-visual-panel">
                  <div
                    v-for="curveViz in [buildCurveVisualization(asset.fairValueFeatureChart.qualityModel.curveConditions)]"
                    :key="`${asset.key}-curve-viz-${curveViz ? 'ready' : 'empty'}`"
                    class="fair-value-curve-viz-card"
                  >
                    <svg
                      v-if="curveViz"
                      :viewBox="`0 0 ${curveViz.width} ${curveViz.height}`"
                      class="fair-value-curve-viz"
                      role="img"
                      aria-label="Mini grafico da variacao do dia da curva DI"
                    >
                      <line
                        v-if="Number.isFinite(curveViz.zeroLineY)"
                        :x1="18"
                        :x2="curveViz.width - 18"
                        :y1="curveViz.zeroLineY"
                        :y2="curveViz.zeroLineY"
                        class="fair-value-curve-viz-zero-line"
                      />
                      <path
                        v-if="curveViz.nominal?.path"
                        :d="curveViz.nominal.path"
                        class="fair-value-curve-viz-line nominal"
                      />
                      <path
                        v-if="curveViz.inflation?.path"
                        :d="curveViz.inflation.path"
                        class="fair-value-curve-viz-line inflation"
                      />
                      <g
                        v-for="point in (curveViz.nominal?.nodes || [])"
                        :key="`${asset.key}-curve-point-${point.label}`"
                      >
                        <circle :cx="point.x" :cy="point.y" r="3.2" class="fair-value-curve-viz-dot nominal" />
                        <text :x="point.x" :y="curveViz.height - 6" class="fair-value-curve-viz-label">{{ point.label }}</text>
                      </g>
                      <g
                        v-for="point in (curveViz.inflation?.nodes || [])"
                        :key="`${asset.key}-infl-point-${point.label}`"
                      >
                        <circle :cx="point.x" :cy="point.y" r="2.6" class="fair-value-curve-viz-dot inflation" />
                      </g>
                    </svg>
                    <div class="fair-value-curve-viz-legend">
                      <span><span class="fair-value-curve-viz-swatch nominal" /> curva nominal var % dia</span>
                      <span><span class="fair-value-curve-viz-swatch inflation" /> inflacao implicita var % dia</span>
                      <span v-if="asset.fairValueFeatureChart.qualityModel.curveConditions.probable_driver">
                        driver {{ asset.fairValueFeatureChart.qualityModel.curveConditions.probable_driver }}
                      </span>
                    </div>
                  </div>
                  <div class="fair-value-curve-thermometer">
                    <div class="fair-value-curve-thermo-head">
                      <span class="metric-label-with-help">
                        <span>termometro de inclinacao</span>
                        <span class="info-help" tabindex="0" role="note" :aria-label="CURVE_HELP_TEXT.inclination">
                          i
                          <span class="info-help-tooltip">{{ CURVE_HELP_TEXT.inclination }}</span>
                        </span>
                      </span>
                      <strong>{{ formatCompactFloat(asset.fairValueFeatureChart.qualityModel.curveConditions.inclination_score) }}/100</strong>
                    </div>
                    <div class="fair-value-curve-thermo-track">
                      <div
                        class="fair-value-curve-thermo-fill"
                        :style="{ width: `${Math.max(0, Math.min(asset.fairValueFeatureChart.qualityModel.curveConditions.inclination_score || 0, 100))}%` }"
                      />
                    </div>
                    <div class="fair-value-curve-thermo-meta">
                      <span>angulo {{ formatCurveAngle(asset.fairValueFeatureChart.qualityModel.curveConditions.geometric_angle_degrees) }}</span>
                      <span>shape abs {{ formatCurveAbsoluteShape(asset.fairValueFeatureChart.qualityModel.curveConditions.absolute_curve_shape) }}</span>
                      <span>conf {{ formatConfidenceScore((asset.fairValueFeatureChart.qualityModel.curveConditions.state_confidence || 0) * 100) }}</span>
                    </div>
                  </div>
                </div>
                <div class="fair-value-curve-grid">
                  <div class="fair-value-curve-pill">
                    <span class="metric-label-with-help">
                      <span class="fair-value-quality-kpi-label">shape</span>
                      <span class="info-help" tabindex="0" role="note" :aria-label="CURVE_HELP_TEXT.shape">
                        i
                        <span class="info-help-tooltip">{{ CURVE_HELP_TEXT.shape }}</span>
                      </span>
                    </span>
                    <strong>{{ formatCurveShapeLabel(asset.fairValueFeatureChart.qualityModel.curveConditions.state) }}</strong>
                  </div>
                  <div class="fair-value-curve-pill">
                    <span class="metric-label-with-help">
                      <span class="fair-value-quality-kpi-label">regime</span>
                      <span class="info-help" tabindex="0" role="note" :aria-label="CURVE_HELP_TEXT.regime">
                        i
                        <span class="info-help-tooltip">{{ CURVE_HELP_TEXT.regime }}</span>
                      </span>
                    </span>
                    <strong>{{ formatCurveMacroRegime(asset.fairValueFeatureChart.qualityModel.curveConditions) }}</strong>
                  </div>
                  <div class="fair-value-curve-pill">
                    <span class="metric-label-with-help">
                      <span class="fair-value-quality-kpi-label">inclinacao</span>
                      <span class="info-help" tabindex="0" role="note" :aria-label="CURVE_HELP_TEXT.inclination">
                        i
                        <span class="info-help-tooltip">{{ CURVE_HELP_TEXT.inclination }}</span>
                      </span>
                    </span>
                    <strong>{{ asset.fairValueFeatureChart.qualityModel.curveConditions.inclination_label || '--' }}</strong>
                  </div>
                  <div class="fair-value-curve-pill">
                    <span class="metric-label-with-help">
                      <span class="fair-value-quality-kpi-label">shape abs</span>
                      <span class="info-help" tabindex="0" role="note" :aria-label="CURVE_HELP_TEXT.absolute_shape">
                        i
                        <span class="info-help-tooltip">{{ CURVE_HELP_TEXT.absolute_shape }}</span>
                      </span>
                    </span>
                    <strong>{{ formatCurveAbsoluteShape(asset.fairValueFeatureChart.qualityModel.curveConditions.absolute_curve_shape) }}</strong>
                  </div>
                  <div class="fair-value-curve-pill">
                    <span class="metric-label-with-help">
                      <span class="fair-value-quality-kpi-label">medio-longo</span>
                      <span class="info-help" tabindex="0" role="note" :aria-label="CURVE_HELP_TEXT.medium_long">
                        i
                        <span class="info-help-tooltip">{{ CURVE_HELP_TEXT.medium_long }}</span>
                      </span>
                    </span>
                    <strong>{{ formatBiasLabel(asset.fairValueFeatureChart.qualityModel.curveConditions.medium_long_bias) }}</strong>
                  </div>
                  <div class="fair-value-curve-pill">
                    <span class="metric-label-with-help">
                      <span class="fair-value-quality-kpi-label">fiscal</span>
                      <span class="info-help" tabindex="0" role="note" :aria-label="CURVE_HELP_TEXT.fiscal">
                        i
                        <span class="info-help-tooltip">{{ CURVE_HELP_TEXT.fiscal }}</span>
                      </span>
                    </span>
                    <strong>{{ asset.fairValueFeatureChart.qualityModel.curveConditions.fiscal_risk_flag ? 'alerta fiscal' : 'sem stress forte' }}</strong>
                  </div>
                  <div class="fair-value-curve-pill">
                    <span class="metric-label-with-help">
                      <span class="fair-value-quality-kpi-label">infl implicita</span>
                      <span class="info-help" tabindex="0" role="note" :aria-label="CURVE_HELP_TEXT.implied_inflation">
                        i
                        <span class="info-help-tooltip">{{ CURVE_HELP_TEXT.implied_inflation }}</span>
                      </span>
                    </span>
                    <strong>{{ formatCurvePercent(asset.fairValueFeatureChart.qualityModel.curveConditions.inflation_day_change_pct) }}</strong>
                  </div>
                  <div class="fair-value-curve-pill">
                    <span class="metric-label-with-help">
                      <span class="fair-value-quality-kpi-label">driver</span>
                      <span class="info-help" tabindex="0" role="note" :aria-label="CURVE_HELP_TEXT.probable_driver">
                        i
                        <span class="info-help-tooltip">{{ CURVE_HELP_TEXT.probable_driver }}</span>
                      </span>
                    </span>
                    <strong>{{ asset.fairValueFeatureChart.qualityModel.curveConditions.probable_driver || '--' }}</strong>
                  </div>
                  <div class="fair-value-curve-pill">
                    <span class="metric-label-with-help">
                      <span class="fair-value-quality-kpi-label">impacto curva</span>
                      <span class="info-help" tabindex="0" role="note" :aria-label="CURVE_HELP_TEXT.curve_impact">
                        i
                        <span class="info-help-tooltip">{{ CURVE_HELP_TEXT.curve_impact }}</span>
                      </span>
                    </span>
                    <strong>{{ formatSignedPoints(asset.fairValueFeatureChart.qualityModel.curveConditions.curve_contribution_points) }}</strong>
                  </div>
                </div>
                <div class="fair-value-curve-metrics">
                  <span>curta {{ formatCurvePercent(asset.fairValueFeatureChart.qualityModel.curveConditions.short_day_change_pct) }}</span>
                  <span>belly {{ formatCurvePercent(asset.fairValueFeatureChart.qualityModel.curveConditions.belly_day_change_pct) }}</span>
                  <span>longa {{ formatCurvePercent(asset.fairValueFeatureChart.qualityModel.curveConditions.long_day_change_pct) }}</span>
                  <span>nivel {{ formatCurvePercent(asset.fairValueFeatureChart.qualityModel.curveConditions.level_day_change_pct) }}</span>
                  <span>slope {{ formatCurvePercent(asset.fairValueFeatureChart.qualityModel.curveConditions.slope_change) }}</span>
                  <span>twist {{ formatCurvePercent(asset.fairValueFeatureChart.qualityModel.curveConditions.twist_change) }}</span>
                </div>
                <div class="fair-value-curve-metrics emphasis">
                  <span>dominante {{ formatCurveProbability(getCurveRegimeRanking(asset.fairValueFeatureChart.qualityModel.curveConditions, 1)[0]?.probability) }}</span>
                  <span>angulo {{ formatCurveAngle(asset.fairValueFeatureChart.qualityModel.curveConditions.geometric_angle_degrees) }}</span>
                  <span>rates {{ formatSignedPoints(asset.fairValueFeatureChart.qualityModel.curveConditions.rates_contribution_points) }}</span>
                  <span>fiscal score {{ formatCompactFloat(asset.fairValueFeatureChart.qualityModel.curveConditions.fiscal_risk_score) }}</span>
                  <span>duration score {{ formatCompactFloat(asset.fairValueFeatureChart.qualityModel.curveConditions.duration_pressure_score) }}</span>
                </div>
                <div class="fair-value-quality-note">
                  <div class="fair-value-quality-note-item">
                    {{ asset.fairValueFeatureChart.qualityModel.curveConditions.summary || '--' }}
                  </div>
                  <div class="fair-value-quality-note-item">
                    {{ asset.fairValueFeatureChart.qualityModel.curveConditions.fiscal_message || '--' }}
                  </div>
                </div>
              </div>

              <div class="fair-value-ranking-window-list">
                <div
                  v-for="window in asset.fairValueFeatureChart.qualityModel.rankingWindows"
                  :key="`${asset.key}-ranking-window-${window.key}`"
                  class="fair-value-ranking-window-card"
                  :class="{ expanded: expandedFairValueRankingWindowKeys.includes(window.key) }"
                >
                  <button
                    type="button"
                    class="fair-value-ranking-window-head"
                    @click="toggleFairValueRankingWindow(window.key)"
                  >
                    <div class="fair-value-ranking-window-head-copy">
                      <strong>{{ window.label }}</strong>
                      <span>{{ window.sampleCount }} fotos uteis</span>
                    </div>
                    <div class="fair-value-ranking-window-summary">
                      <span class="bullish">
                        ↑ {{ window.topUp ? `${window.topUp.shortLabel} ${formatSignedPoints(window.topUp.contribution_points)}` : '--' }}
                      </span>
                      <span class="bearish">
                        ↓ {{ window.topDown ? `${window.topDown.shortLabel} ${formatSignedPoints(window.topDown.contribution_points)}` : '--' }}
                      </span>
                    </div>
                    <span class="fair-value-ranking-window-toggle">
                      {{ expandedFairValueRankingWindowKeys.includes(window.key) ? 'recolher' : 'expandir' }}
                    </span>
                  </button>

                  <div v-if="expandedFairValueRankingWindowKeys.includes(window.key)" class="fair-value-ranking">
                    <div class="fair-value-ranking-col">
                      <div class="fair-value-ranking-title">Puxando para cima</div>
                      <div
                        v-for="item in window.rankingUp"
                        :key="`${window.key}-up-${item.name || item.label}`"
                        class="fair-value-ranking-item bullish"
                      >
                        <span>{{ item.label || item.name }}</span>
                        <strong>{{ formatSignedPoints(item.contribution_points) }}</strong>
                      </div>
                      <div v-if="!window.rankingUp.length" class="fair-value-ranking-empty">
                        Sem perna core positiva relevante nessa janela.
                      </div>
                    </div>
                    <div class="fair-value-ranking-col">
                      <div class="fair-value-ranking-title">Puxando para baixo</div>
                      <div
                        v-for="item in window.rankingDown"
                        :key="`${window.key}-down-${item.name || item.label}`"
                        class="fair-value-ranking-item bearish"
                      >
                        <span>{{ item.label || item.name }}</span>
                        <strong>{{ formatSignedPoints(item.contribution_points) }}</strong>
                      </div>
                      <div v-if="!window.rankingDown.length" class="fair-value-ranking-empty">
                        Sem perna core negativa relevante nessa janela.
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div
                v-if="asset.fairValueFeatureChart.qualityModel.explanation?.divergences?.length"
                class="fair-value-quality-note"
              >
                <div class="fair-value-quality-note-title">Divergências</div>
                <div
                  v-for="(item, index) in asset.fairValueFeatureChart.qualityModel.explanation.divergences"
                  :key="`div-${index}`"
                  class="fair-value-quality-note-item"
                >
                  {{ item }}
                </div>
              </div>

              <div
                v-if="asset.fairValueFeatureChart.qualityModel.explanation?.warnings?.length"
                class="fair-value-quality-note warning"
              >
                <div class="fair-value-quality-note-title">Warnings</div>
                <div
                  v-for="(item, index) in asset.fairValueFeatureChart.qualityModel.explanation.warnings"
                  :key="`warn-${index}`"
                  class="fair-value-quality-note-item"
                >
                  {{ item }}
                </div>
              </div>

              <div class="fair-value-quality-summary">
                {{ asset.fairValueFeatureChart.qualityModel.explanation?.summary || '--' }}
              </div>
            </aside>
</template>

<script>
import { injectMacroHeatmapContext } from '../context'

export default {
  name: 'MacroFairValueQuality',
  props: { asset: { type: Object, required: true } },
  setup() {
    return injectMacroHeatmapContext()
  },
}
</script>

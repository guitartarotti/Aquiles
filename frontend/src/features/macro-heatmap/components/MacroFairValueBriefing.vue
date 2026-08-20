<template>
          <div v-if="asset.fairValueFeatureChart.qualityModel" class="fair-value-briefing-card">
            <div class="fair-value-briefing-head">
              <div class="fair-value-briefing-head-copy">
                <span class="fair-value-briefing-eyebrow">Macro Fair Value Briefing</span>
                <strong>Leitura integrada do dia</strong>
                <span>{{ buildFairValueCompositeRegimeCommentary(asset.fairValueFeatureChart, asset.fairValueFeatureChart.qualityModel) }}</span>
              </div>
              <div
                class="fair-value-briefing-badge"
                :class="fairValueSentimentClass(asset.fairValueFeatureChart.qualityModel.implicitSentiment)"
              >
                {{ formatImplicitSentiment(asset.fairValueFeatureChart.qualityModel.implicitSentiment) }}
              </div>
            </div>

            <div class="fair-value-briefing-grid">
              <section class="fair-value-briefing-section wide">
                <div class="fair-value-briefing-section-title">Tese do modelo</div>
                <p>{{ buildFairValueModelCommentary(asset.fairValueFeatureChart, asset.fairValueFeatureChart.qualityModel) }}</p>
                <p>{{ buildFairValueSupportBalanceCommentary(asset.fairValueFeatureChart, asset.fairValueFeatureChart.qualityModel) }}</p>
                <p>{{ buildFairValuePriceDriverCommentary(asset.fairValueFeatureChart, asset.fairValueFeatureChart.qualityModel) }}</p>
                <div class="fair-value-briefing-chip-row">
                  <span class="fair-value-briefing-chip">
                    regime <strong>{{ getFairValueCompositeRegimeLabel(asset.fairValueFeatureChart, asset.fairValueFeatureChart.qualityModel) }}</strong>
                  </span>
                  <span class="fair-value-briefing-chip">
                    preco <strong>{{ getFairValueFollowThroughStateLabel(asset.fairValueFeatureChart.qualityModel) }}</strong>
                  </span>
                  <span class="fair-value-briefing-chip">
                    Brasil <strong>{{ getFairValueLocalAcceptanceLabel(asset.fairValueFeatureChart, asset.fairValueFeatureChart.qualityModel) }}</strong>
                  </span>
                </div>
                <div class="fair-value-briefing-note">
                  {{ buildFairValueReactionCommentary(asset.fairValueFeatureChart, asset.fairValueFeatureChart.qualityModel) }}
                </div>
              </section>

              <section class="fair-value-briefing-section">
                <div class="fair-value-briefing-section-title">Curva DI e regime local</div>
                <p>{{ buildFairValueCurveDeskCommentary(asset.fairValueFeatureChart.qualityModel.curveConditions) }}</p>
                <div class="fair-value-briefing-stat-row">
                  <span>shape <strong>{{ formatCurveShapeLabel(asset.fairValueFeatureChart.qualityModel.curveConditions.state) }}</strong></span>
                  <span>regime <strong>{{ formatCurveMacroRegime(asset.fairValueFeatureChart.qualityModel.curveConditions) }}</strong></span>
                </div>
                <div class="fair-value-briefing-stat-row">
                  <span>curta <strong>{{ formatCurvePercent(asset.fairValueFeatureChart.qualityModel.curveConditions.short_day_change_pct) }}</strong></span>
                  <span>belly <strong>{{ formatCurvePercent(asset.fairValueFeatureChart.qualityModel.curveConditions.belly_day_change_pct) }}</strong></span>
                  <span>longa <strong>{{ formatCurvePercent(asset.fairValueFeatureChart.qualityModel.curveConditions.long_day_change_pct) }}</strong></span>
                </div>
                <div class="fair-value-briefing-stat-row">
                  <span>medium-long <strong>{{ formatBiasLabel(asset.fairValueFeatureChart.qualityModel.curveConditions.medium_long_bias) }}</strong></span>
                  <span>fiscal <strong>{{ asset.fairValueFeatureChart.qualityModel.curveConditions.fiscal_risk_flag ? 'alerta' : 'ok' }}</strong></span>
                  <span>slope <strong>{{ formatCurvePercent(asset.fairValueFeatureChart.qualityModel.curveConditions.slope_change) }}</strong></span>
                  <span>impacto <strong>{{ formatSignedPoints(asset.fairValueFeatureChart.qualityModel.curveConditions.curve_contribution_points) }}</strong></span>
                </div>
              </section>

              <section class="fair-value-briefing-section">
                <div class="fair-value-briefing-section-title">Qualidade e reacao do preco</div>
                <p>{{ buildFairValueShadowCommentary(asset.fairValueFeatureChart.qualityModel, asset.fairValueFeatureChart) }}</p>
                <div class="fair-value-briefing-stat-row">
                  <span>preco <strong>{{ formatPrice(asset.fairValueFeatureChart.currentPrice) }}</strong></span>
                  <span>core fv <strong>{{ formatPrice(asset.fairValueFeatureChart.currentFairValue) }}</strong></span>
                  <span>q adj <strong>{{ formatPrice(asset.fairValueFeatureChart.currentQualityAdjusted) }}</strong></span>
                </div>
                <div class="fair-value-briefing-stat-row">
                  <span>gap bruto <strong>{{ formatSignedPoints(getFairValueGrossGap(asset.fairValueFeatureChart)) }}</strong></span>
                  <span>haircut <strong>{{ formatSignedPoints(getFairValueShadowHaircutPoints(asset.fairValueFeatureChart, asset.fairValueFeatureChart.qualityModel)) }}</strong></span>
                  <span>gap liquido <strong>{{ formatSignedPoints(getFairValueNetGap(asset.fairValueFeatureChart)) }}</strong></span>
                </div>
                <div class="fair-value-briefing-stat-row with-help">
                  <span class="metric-inline-help">
                    <span>dist <strong>{{ formatSignedPoints(asset.fairValueFeatureChart.currentDislocation) }}</strong></span>
                    <span class="info-help" tabindex="0" role="note" :aria-label="FAIR_VALUE_HELP_TEXT.briefing_distortion">
                      i
                      <span class="info-help-tooltip">{{ FAIR_VALUE_HELP_TEXT.briefing_distortion }}</span>
                    </span>
                  </span>
                  <span class="metric-inline-help">
                    <span>conv <strong>{{ formatConfidenceScore((asset.fairValueFeatureChart.qualityModel.convergenceProbability || 0) * 100) }}</strong></span>
                    <span class="info-help" tabindex="0" role="note" :aria-label="FAIR_VALUE_HELP_TEXT.briefing_convergence">
                      i
                      <span class="info-help-tooltip">{{ FAIR_VALUE_HELP_TEXT.briefing_convergence }}</span>
                    </span>
                  </span>
                  <span class="metric-inline-help">
                    <span>break <strong>{{ formatConfidenceScore((asset.fairValueFeatureChart.qualityModel.regimeBreakProbability || 0) * 100) }}</strong></span>
                    <span class="info-help" tabindex="0" role="note" :aria-label="FAIR_VALUE_HELP_TEXT.briefing_break">
                      i
                      <span class="info-help-tooltip">{{ FAIR_VALUE_HELP_TEXT.briefing_break }}</span>
                    </span>
                  </span>
                </div>
                <div v-if="asset.fairValueFeatureChart.qualityModel.explanation?.core_message" class="fair-value-briefing-note">
                  {{ asset.fairValueFeatureChart.qualityModel.explanation.core_message }}
                </div>
                <div v-if="asset.fairValueFeatureChart.qualityModel.explanation?.shadow_message" class="fair-value-briefing-note">
                  {{ asset.fairValueFeatureChart.qualityModel.explanation.shadow_message }}
                </div>
              </section>

              <section class="fair-value-briefing-section">
                <div class="fair-value-briefing-section-title">Confirmacao local e aceitacao Brasil</div>
                <p>{{ buildFairValueLocalConfirmationCommentary(asset.fairValueFeatureChart, asset.fairValueFeatureChart.qualityModel) }}</p>
                <div class="fair-value-briefing-stat-row">
                  <span>Brasil eq <strong>{{ formatSignedPoints(asset.fairValueFeatureChart.qualityModel.coreLegs?.equity_brazil?.contribution_points) }}</strong></span>
                  <span>Brasil credit <strong>{{ formatSignedPoints(asset.fairValueFeatureChart.qualityModel.coreLegs?.credit_brazil?.contribution_points) }}</strong></span>
                  <span>estado <strong>{{ getFairValueLocalAcceptanceLabel(asset.fairValueFeatureChart, asset.fairValueFeatureChart.qualityModel) }}</strong></span>
                </div>
              </section>

              <section class="fair-value-briefing-section wide">
                <div class="fair-value-briefing-section-title">O que precisa destravar para convergir</div>
                <p>{{ buildFairValueConvergenceCommentary(asset.fairValueFeatureChart, asset.fairValueFeatureChart.qualityModel) }}</p>
                <div class="fair-value-briefing-warning-grid">
                  <div class="fair-value-briefing-warning-block">
                    <strong>Blockers dominantes</strong>
                    <div
                      v-for="(item, index) in (asset.fairValueFeatureChart.qualityModel.explanation?.dominant_blockers || [])"
                      :key="`${asset.key}-brief-blocker-${index}`"
                      class="fair-value-briefing-blocker-row"
                    >
                      <div class="fair-value-briefing-leg-copy">
                        <strong>{{ item.label }}</strong>
                        <span>{{ item.message }}</span>
                      </div>
                      <div class="fair-value-briefing-leg-values warning">
                        <span>{{ item.type === 'shadow' ? 'shadow' : 'core' }}</span>
                        <span>impacto {{ formatSignedPoints(item.impact_points) }}</span>
                        <span>conf {{ formatFlexibleConfidence(item.confidence) }}</span>
                      </div>
                    </div>
                    <div v-if="!(asset.fairValueFeatureChart.qualityModel.explanation?.dominant_blockers || []).length" class="fair-value-briefing-empty">
                      Nao ha bloqueio dominante material na janela util atual.
                    </div>
                  </div>
                  <div class="fair-value-briefing-warning-block">
                    <strong>Gatilhos de confirmacao</strong>
                    <div
                      v-for="(item, index) in (asset.fairValueFeatureChart.qualityModel.explanation?.confirmation_triggers || [])"
                      :key="`${asset.key}-brief-trigger-${index}`"
                      class="fair-value-briefing-trigger-item"
                    >
                      <strong>{{ item.label }}</strong>
                      <span>{{ item.message }}</span>
                    </div>
                    <div v-if="!(asset.fairValueFeatureChart.qualityModel.explanation?.confirmation_triggers || []).length" class="fair-value-briefing-empty">
                      Sem gatilho dominante novo alem do proprio alinhamento ja visto no snapshot.
                    </div>
                  </div>
                </div>
              </section>

              <section class="fair-value-briefing-section">
                <div class="fair-value-briefing-section-title">Pernas core em destaque</div>
                <div class="fair-value-briefing-leg-columns">
                  <div class="fair-value-briefing-leg-column">
                    <span class="fair-value-briefing-leg-title bullish">Puxando para cima</span>
                    <div
                      v-for="leg in getFairValueLegRanking(asset.fairValueFeatureChart.qualityModel.coreLegs, 'core', 'up', 4)"
                      :key="`${asset.key}-brief-core-up-${leg.key}`"
                      class="fair-value-briefing-leg-row"
                    >
                      <div class="fair-value-briefing-leg-copy">
                        <strong>{{ leg.label }}</strong>
                        <span>{{ leg.description }}</span>
                      </div>
                      <div class="fair-value-briefing-leg-values bullish">
                        <span>{{ formatSignedPoints(leg.contributionValue) }}</span>
                        <span>fv {{ formatPrice(leg.implied_fair_value_xb1) }}</span>
                        <span>conf {{ formatFlexibleConfidence(leg.confidence) }}</span>
                      </div>
                    </div>
                    <div v-if="!getFairValueLegRanking(asset.fairValueFeatureChart.qualityModel.coreLegs, 'core', 'up', 4).length" class="fair-value-briefing-empty">
                      Nenhuma perna core compradora com relevância material neste momento.
                    </div>
                  </div>
                  <div class="fair-value-briefing-leg-column">
                    <span class="fair-value-briefing-leg-title bearish">Puxando para baixo</span>
                    <div
                      v-for="leg in getFairValueLegRanking(asset.fairValueFeatureChart.qualityModel.coreLegs, 'core', 'down', 4)"
                      :key="`${asset.key}-brief-core-down-${leg.key}`"
                      class="fair-value-briefing-leg-row"
                    >
                      <div class="fair-value-briefing-leg-copy">
                        <strong>{{ leg.label }}</strong>
                        <span>{{ leg.description }}</span>
                      </div>
                      <div class="fair-value-briefing-leg-values bearish">
                        <span>{{ formatSignedPoints(leg.contributionValue) }}</span>
                        <span>fv {{ formatPrice(leg.implied_fair_value_xb1) }}</span>
                        <span>conf {{ formatFlexibleConfidence(leg.confidence) }}</span>
                      </div>
                    </div>
                    <div v-if="!getFairValueLegRanking(asset.fairValueFeatureChart.qualityModel.coreLegs, 'core', 'down', 4).length" class="fair-value-briefing-empty">
                      Nenhuma perna core vendedora com relevância material neste momento.
                    </div>
                  </div>
                </div>
              </section>

              <section class="fair-value-briefing-section">
                <div class="fair-value-briefing-section-title">Shadow, fragilidade e assimetria</div>
                <p>{{ buildFairValueShadowSectionLead(asset.fairValueFeatureChart.qualityModel.shadowLegs) }}</p>
                <div
                  v-for="leg in getFairValueShadowRanking(asset.fairValueFeatureChart.qualityModel.shadowLegs, 6)"
                  :key="`${asset.key}-brief-shadow-${leg.key}`"
                  class="fair-value-briefing-shadow-row"
                >
                  <div class="fair-value-briefing-leg-copy">
                    <strong>{{ leg.label }}</strong>
                    <span>{{ leg.description }}</span>
                  </div>
                  <div class="fair-value-briefing-leg-values">
                    <span>qual {{ formatSignedPoints(leg.qualityImpactValue) }}</span>
                    <span>band {{ formatCompactFloat(leg.bandImpactValue) }}</span>
                    <span>conv {{ formatCompactFloat(leg.convergenceImpactValue) }}</span>
                    <span>fv {{ formatPrice(leg.implied_fair_value_xb1) }}</span>
                  </div>
                </div>
              </section>

              <section class="fair-value-briefing-section wide">
                <div class="fair-value-briefing-section-title">Divergências, riscos e pontos de atenção</div>
                <div class="fair-value-briefing-warning-grid">
                  <div class="fair-value-briefing-warning-block">
                    <strong>Divergências</strong>
                    <div
                      v-for="(item, index) in (asset.fairValueFeatureChart.qualityModel.explanation?.divergences || [])"
                      :key="`${asset.key}-brief-div-${index}`"
                      class="fair-value-briefing-warning-item"
                    >
                      {{ item }}
                    </div>
                    <div v-if="!(asset.fairValueFeatureChart.qualityModel.explanation?.divergences || []).length" class="fair-value-briefing-empty">
                      Sem divergência textual relevante no snapshot útil atual.
                    </div>
                  </div>
                  <div class="fair-value-briefing-warning-block">
                    <strong>Warnings</strong>
                    <div
                      v-for="(item, index) in (asset.fairValueFeatureChart.qualityModel.explanation?.warnings || [])"
                      :key="`${asset.key}-brief-warn-${index}`"
                      class="fair-value-briefing-warning-item warning"
                    >
                      {{ item }}
                    </div>
                    <div v-if="!(asset.fairValueFeatureChart.qualityModel.explanation?.warnings || []).length" class="fair-value-briefing-empty">
                      Sem warning textual relevante no snapshot útil atual.
                    </div>
                  </div>
                </div>
              </section>
            </div>
          </div>
</template>

<script>
import { injectMacroHeatmapContext } from '../context'

export default {
  name: 'MacroFairValueBriefing',
  props: { asset: { type: Object, required: true } },
  setup() {
    return injectMacroHeatmapContext()
  },
}
</script>

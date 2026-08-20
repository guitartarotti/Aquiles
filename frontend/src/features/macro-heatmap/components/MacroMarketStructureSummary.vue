<template>
  <section v-if="crossAssetFlowPackage?.primary" class="package-strip">
    <div class="pressure-head">
      <div class="pressure-title">
        Local flow package {{ crossAssetFlowPackage.primary.window_label || crossAssetFlowPackage.primary_window_label || '' }}
      </div>
      <div class="pressure-meta">
        {{ formatLocalPackageStateLabel(crossAssetFlowPackage.primary.state) }}
        | local {{ formatPressureScore(crossAssetFlowPackage.primary.local_package_score) }}
        | foreign {{ formatPressureScore(crossAssetFlowPackage.primary.foreign_package_score) }}
      </div>
    </div>
    <div class="pressure-window-row">
      <span class="pressure-window-label">leitura dominante</span>
      <span>{{ crossAssetFlowPackage.primary.rationale || '--' }}</span>
    </div>
    <div class="pressure-pill-row">
      <div class="pressure-pill" :class="localPackageClass(crossAssetFlowPackage.primary.win_component_score)">
        <span class="pressure-pill-label">WIN</span>
        <strong>{{ formatPressureScore(crossAssetFlowPackage.primary.win_component_score) }}</strong>
        <span>componente bolsa</span>
      </div>
      <div class="pressure-pill" :class="localPackageClass(crossAssetFlowPackage.primary.wdo_component_score)">
        <span class="pressure-pill-label">WDO</span>
        <strong>{{ formatPressureScore(crossAssetFlowPackage.primary.wdo_component_score) }}</strong>
        <span>invertido para risco local</span>
      </div>
      <div class="pressure-pill" :class="localPackageClass(crossAssetFlowPackage.primary.di_curve_component_score)">
        <span class="pressure-pill-label">Curva DI</span>
        <strong>{{ formatPressureScore(crossAssetFlowPackage.primary.di_curve_component_score) }}</strong>
        <span>F28/F29/F30/F31/F35</span>
      </div>
    </div>
    <div class="pressure-pill-row">
      <div class="pressure-pill balanced">
        <span class="pressure-pill-label">Confirmacao</span>
        <strong>{{ crossAssetFlowPackage.primary.on_confirmations || 0 }} on / {{ crossAssetFlowPackage.primary.off_confirmations || 0 }} off</strong>
        <span>driver {{ crossAssetFlowPackage.primary.dominant_driver || '--' }}</span>
      </div>
      <div class="pressure-pill balanced">
        <span class="pressure-pill-label">Breadth curva</span>
        <strong>{{ formatPressureScore(crossAssetFlowPackage.primary.curve_breadth_score) }}</strong>
        <span>slope {{ formatPressureScore(crossAssetFlowPackage.primary.curve_slope_score) }}</span>
      </div>
      <div class="pressure-pill balanced">
        <span class="pressure-pill-label">DI short/long</span>
        <strong>{{ formatPressureScore(crossAssetFlowPackage.primary.short_di_average_score) }} / {{ formatPressureScore(crossAssetFlowPackage.primary.long_di_average_score) }}</strong>
        <span>media por bloco</span>
      </div>
    </div>
    <div class="pressure-window-grid">
      <div v-for="window in (crossAssetFlowPackage.windows || [])" :key="`package-${window.minutes}`" class="pressure-window-row">
        <span class="pressure-window-label">{{ window.window_label }}</span>
        <span>{{ formatLocalPackageStateLabel(window.state) }}</span>
        <span>local {{ formatPressureScore(window.local_package_score) }}</span>
        <span>foreign {{ formatPressureScore(window.foreign_package_score) }}</span>
        <span>breadth {{ formatPressureScore(window.curve_breadth_score) }}</span>
      </div>
    </div>
    <div class="pressure-pill-row">
      <div
        v-for="leg in (crossAssetFlowPackage.primary.di_legs || [])"
        :key="leg.ticker"
        class="pressure-pill"
        :class="localPackageClass(leg.net_pressure_score)"
      >
        <span class="pressure-pill-label">{{ leg.label }}</span>
        <strong>{{ formatPressureScore(leg.net_pressure_score) }}</strong>
        <span>foreign {{ formatPressureScore(leg.foreign_pressure_score) }}</span>
      </div>
    </div>
  </section>

  <section v-if="structuralDivergenceModel?.primary" class="package-strip">
    <div class="pressure-head">
      <div class="pressure-title">
        SMT / structural divergence {{ structuralDivergenceModel.primary.window_label || structuralDivergenceModel.primary_window_label || '' }}
      </div>
      <div class="pressure-meta">
        {{ formatStructuralDivergenceStateLabel(structuralDivergenceModel.primary.state) }}
        | conf {{ formatPressureScore(structuralDivergenceModel.primary.confirmation_score) }}
        | non-conf {{ formatPressureScore(structuralDivergenceModel.primary.non_confirmation_score) }}
      </div>
    </div>
    <div class="pressure-window-row">
      <span class="pressure-window-label">leitura dominante</span>
      <span>{{ structuralDivergenceModel.primary.rationale || '--' }}</span>
    </div>
    <div class="pressure-pill-row">
      <div v-for="item in structuralDivergenceCards" :key="item.key" class="pressure-pill" :class="structuralDivergenceClass(structuralDivergenceModel.primary)">
        <span class="pressure-pill-label">{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
        <span>{{ item.detail }}</span>
      </div>
    </div>
    <div class="pressure-window-grid">
      <div v-for="window in (structuralDivergenceModel.windows || [])" :key="`smt-${window.minutes}`" class="pressure-window-row">
        <span class="pressure-window-label">{{ window.window_label }}</span>
        <span>{{ formatStructuralDivergenceStateLabel(window.state) }}</span>
        <span>conf {{ formatPressureScore(window.confirmation_score) }}</span>
        <span>non {{ formatPressureScore(window.non_confirmation_score) }}</span>
        <span>pkg {{ formatPressureScore(window.package_score) }}</span>
      </div>
    </div>
  </section>

  <section v-if="continuationReversalModel?.primary" class="package-strip">
    <div class="pressure-head">
      <div class="pressure-title">
        Continuation vs reversal {{ continuationReversalModel.primary.window_label || continuationReversalModel.primary_window_label || '' }}
      </div>
      <div class="pressure-meta">
        {{ formatContinuationStateLabel(continuationReversalModel.primary.state) }}
        | cont {{ formatConfidenceScore(continuationReversalModel.primary.continuation_probability) }}
        | rev {{ formatConfidenceScore(continuationReversalModel.primary.reversal_probability) }}
      </div>
    </div>
    <div class="pressure-window-row">
      <span class="pressure-window-label">leitura dominante</span>
      <span>{{ continuationReversalModel.primary.rationale || '--' }}</span>
    </div>
    <div class="pressure-pill-row">
      <div v-for="item in continuationCards" :key="item.key" class="pressure-pill" :class="continuationClass(continuationReversalModel.primary)">
        <span class="pressure-pill-label">{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
        <span>{{ item.detail }}</span>
      </div>
    </div>
    <div class="pressure-window-grid">
      <div v-for="window in (continuationReversalModel.windows || [])" :key="`contrev-${window.minutes}`" class="pressure-window-row">
        <span class="pressure-window-label">{{ window.window_label }}</span>
        <span>{{ formatContinuationStateLabel(window.state) }}</span>
        <span>cont {{ formatConfidenceScore(window.continuation_probability) }}</span>
        <span>rev {{ formatConfidenceScore(window.reversal_probability) }}</span>
        <span>pkg {{ formatPressureScore(window.package_score) }}</span>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

import { formatPressureScore } from '@/utils/marketFormatters'
import {
  continuationClass,
  formatConfidenceScore,
  formatContinuationStateLabel,
  formatLocalPackageStateLabel,
  formatStructuralDivergenceStateLabel,
  localPackageClass,
  structuralDivergenceClass,
} from '../models/heatmapModels'

const props = defineProps({
  crossAssetFlowPackage: { type: Object, default: null },
  structuralDivergenceModel: { type: Object, default: null },
  continuationReversalModel: { type: Object, default: null },
})

const structuralDivergenceCards = computed(() => {
  const primary = props.structuralDivergenceModel?.primary
  if (!primary) return []
  return [
    { key: 'state', label: 'estado', value: formatStructuralDivergenceStateLabel(primary.state), detail: primary.bias_side || 'neutral' },
    { key: 'package', label: 'WIN x pacote', value: formatPressureScore(primary.win_net_score), detail: `pkg ${formatPressureScore(primary.package_score)}` },
    { key: 'foreign', label: 'foreign', value: formatPressureScore(primary.foreign_package_score), detail: `lead ${formatPressureScore(primary.lead_score)}` },
  ]
})

const continuationCards = computed(() => {
  const primary = props.continuationReversalModel?.primary
  if (!primary) return []
  return [
    { key: 'state', label: 'estado', value: formatContinuationStateLabel(primary.state), detail: primary.bias_side || 'neutral' },
    { key: 'probability', label: 'prob.', value: formatConfidenceScore(primary.continuation_probability), detail: `rev ${formatConfidenceScore(primary.reversal_probability)}` },
    { key: 'drivers', label: 'drivers', value: `eff ${formatPressureScore(primary.efficiency_score)}`, detail: `abs ${formatPressureScore(primary.absorption_score)} | frag ${formatPressureScore(primary.fragility_score)}` },
  ]
})
</script>

<style scoped src="./MacroSummaryPanels.css"></style>

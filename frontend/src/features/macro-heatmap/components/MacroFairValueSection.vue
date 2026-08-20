<template>
  <div v-if="asset.fairValueFeatureChart?.available" class="fair-value-feature-wrap">
          <div class="tag-filter-strip fair-value-feature-filter">
            <span class="filter-label">fair value map</span>
            <button
              class="chip"
              :class="{ active: selectedFairValueFeatureKeys.length === FAIR_VALUE_FEATURE_OPTIONS.length }"
              @click="clearFairValueFeatureSelection()"
            >
              todas
            </button>
            <button
              v-for="item in FAIR_VALUE_FEATURE_OPTIONS"
              :key="`${asset.key}-fv-feature-${item.key}`"
              class="chip"
              :class="{ active: selectedFairValueFeatureKeys.includes(item.key) }"
              @click="toggleFairValueFeatureSelection(item.key)"
            >
              {{ item.shortLabel }}
            </button>
          </div>

          <div class="tag-filter-strip fair-value-feature-filter secondary">
            <span class="filter-label">pernas core</span>
            <button
              class="chip"
              :class="{ active: !selectedFairValueCoreLegKeys.length }"
              @click="clearFairValueCoreLegSelection()"
            >
              ocultar
            </button>
            <button
              v-for="item in FAIR_VALUE_CORE_LEG_OPTIONS"
              :key="`${asset.key}-fv-core-leg-${item.key}`"
              class="chip"
              :class="{ active: selectedFairValueCoreLegKeys.includes(item.key) }"
              @click="toggleFairValueCoreLegSelection(item.key)"
            >
              {{ item.shortLabel }}
            </button>
          </div>

          <div class="tag-filter-strip fair-value-feature-filter secondary">
            <span class="filter-label">pernas shadow</span>
            <button
              class="chip"
              :class="{ active: !selectedFairValueShadowLegKeys.length }"
              @click="clearFairValueShadowLegSelection()"
            >
              ocultar
            </button>
            <button
              v-for="item in FAIR_VALUE_SHADOW_LEG_OPTIONS"
              :key="`${asset.key}-fv-shadow-leg-${item.key}`"
              class="chip"
              :class="{ active: selectedFairValueShadowLegKeys.includes(item.key) }"
              @click="toggleFairValueShadowLegSelection(item.key)"
            >
              {{ item.shortLabel }}
            </button>
          </div>

    <div class="fair-value-feature-layout">
      <MacroFairValueQuality :asset="asset" />
      <MacroFairValueChartStack :asset="asset" />
      <MacroFairValueCards :asset="asset" />
    </div>
    <MacroIntradayCorrelation :asset="asset" />
    <MacroCapturedFactorHistory :asset="asset" />
    <MacroFairValueBriefing :asset="asset" />
  </div>
</template>

<script>
import { injectMacroHeatmapContext } from '../context'
import MacroCapturedFactorHistory from './MacroCapturedFactorHistory.vue'
import MacroFairValueBriefing from './MacroFairValueBriefing.vue'
import MacroFairValueCards from './MacroFairValueCards.vue'
import MacroFairValueChartStack from './MacroFairValueChartStack.vue'
import MacroFairValueQuality from './MacroFairValueQuality.vue'
import MacroIntradayCorrelation from './MacroIntradayCorrelation.vue'

export default {
  name: 'MacroFairValueSection',
  components: {
    MacroCapturedFactorHistory, MacroFairValueBriefing, MacroFairValueCards,
    MacroFairValueChartStack, MacroFairValueQuality, MacroIntradayCorrelation,
  },
  props: { asset: { type: Object, required: true } },
  setup() {
    return injectMacroHeatmapContext()
  },
}
</script>

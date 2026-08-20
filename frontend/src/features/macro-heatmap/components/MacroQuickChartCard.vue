<template>
  <article class="quick-chart-card">
    <MacroQuickChartPressure :asset="asset" />
    <MacroQuickChartControls :asset="asset" />
    <MacroQuickChartPrice :asset="asset" />
    <MacroFairValueSection :asset="asset" />
    <MacroQuickChartIndicators :asset="asset" />
  </article>
</template>

<script setup>
import MacroFairValueSection from './MacroFairValueSection.vue'
import MacroQuickChartControls from './MacroQuickChartControls.vue'
import MacroQuickChartIndicators from './MacroQuickChartIndicators.vue'
import MacroQuickChartPressure from './MacroQuickChartPressure.vue'
import MacroQuickChartPrice from './MacroQuickChartPrice.vue'

defineProps({ asset: { type: Object, required: true } })
</script>

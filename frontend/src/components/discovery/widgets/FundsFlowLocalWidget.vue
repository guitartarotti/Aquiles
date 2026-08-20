<template>
  <FundsFlowFeature v-bind="$attrs" />
</template>

<script setup>
import FundsFlowFeature from '@/features/funds-flow/components/FundsFlowLocalWidget.vue'

defineOptions({ inheritAttrs: false })
</script>

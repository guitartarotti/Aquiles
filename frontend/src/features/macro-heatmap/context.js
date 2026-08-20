import { inject } from 'vue'

export const MACRO_HEATMAP_CONTEXT = Symbol('macro-heatmap-context')

export function injectMacroHeatmapContext() {
  const context = inject(MACRO_HEATMAP_CONTEXT)
  if (!context) throw new Error('Macro Heatmap context is unavailable')
  return context
}

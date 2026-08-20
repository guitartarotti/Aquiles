import { inject } from 'vue'

export const FUNDS_FLOW_CONTEXT = Symbol('funds-flow-context')

export function injectFundsFlowContext() {
  const context = inject(FUNDS_FLOW_CONTEXT)
  if (!context) throw new Error('Funds Flow context is unavailable')
  return context
}

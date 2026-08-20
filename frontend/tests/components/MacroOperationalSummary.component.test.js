import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import MacroOperationalSummary from '../../src/features/macro-heatmap/components/MacroOperationalSummary.vue'

describe('MacroOperationalSummary', () => {
  it('renders the available operational models without requiring page state', () => {
    const wrapper = mount(MacroOperationalSummary, {
      props: {
        winTradeThermometer: {
          primary_window_label: '5m',
          primary: {
            signal: 'buy',
            action: 'enter_long',
            entry_style: 'pullback',
            rationale: 'Fluxo comprador confirmado.',
            directional_score: 62,
            conviction_score: 74,
            timing_score: 68,
            risk_score: 31,
          },
          windows: [],
        },
        optionsFlowAlignmentModel: {
          available: true,
          action_bias: 'hold',
          gamma_state: 'positive',
          fair_value_state: 'inside_band',
          commentary: 'Gamma reduz a amplitude esperada.',
          region_focus: [],
        },
      },
    })

    expect(wrapper.text()).toContain('WIN trade thermometer 5m')
    expect(wrapper.text()).toContain('Fluxo comprador confirmado.')
    expect(wrapper.text()).toContain('Gamma x fair value x flow')
    expect(wrapper.text()).toContain('Gamma reduz a amplitude esperada.')
    expect(wrapper.text()).not.toContain('Synthetic liquidity pools')
  })

  it('renders no panels when all provider models are absent', () => {
    const wrapper = mount(MacroOperationalSummary)

    expect(wrapper.findAll('.package-strip')).toHaveLength(0)
  })
})

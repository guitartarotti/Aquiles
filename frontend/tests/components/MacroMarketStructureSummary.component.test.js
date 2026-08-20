import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import MacroMarketStructureSummary from '../../src/features/macro-heatmap/components/MacroMarketStructureSummary.vue'

describe('MacroMarketStructureSummary', () => {
  it('renders cross-asset, divergence, and continuation models independently', () => {
    const wrapper = mount(MacroMarketStructureSummary, {
      props: {
        crossAssetFlowPackage: {
          primary_window_label: '15m',
          primary: {
            state: 'risk_on',
            rationale: 'WIN e curva confirmam o fluxo local.',
            on_confirmations: 3,
            off_confirmations: 1,
            di_legs: [],
          },
          windows: [],
        },
        structuralDivergenceModel: {
          primary_window_label: '5m',
          primary: {
            state: 'bullish_divergence',
            rationale: 'Pacote antecede a recuperação do índice.',
            bias_side: 'buy',
            win_net_score: 21,
            package_score: 48,
            foreign_package_score: 52,
            lead_score: 31,
          },
          windows: [],
        },
        continuationReversalModel: {
          primary_window_label: '5m',
          primary: {
            state: 'continuation',
            rationale: 'Eficiência favorece continuação.',
            continuation_probability: 72,
            reversal_probability: 28,
            efficiency_score: 45,
            absorption_score: 12,
            fragility_score: 9,
          },
          windows: [],
        },
      },
    })

    expect(wrapper.text()).toContain('Local flow package 15m')
    expect(wrapper.text()).toContain('SMT / structural divergence 5m')
    expect(wrapper.text()).toContain('Continuation vs reversal 5m')
    expect(wrapper.text()).toContain('WIN x pacote')
    expect(wrapper.text()).toContain('drivers')
  })

  it('does not create empty presentation sections', () => {
    const wrapper = mount(MacroMarketStructureSummary)

    expect(wrapper.findAll('.package-strip')).toHaveLength(0)
  })
})

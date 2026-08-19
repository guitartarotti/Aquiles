import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import DiscoveryStatusBar from '../../src/components/discovery/DiscoveryStatusBar.vue'

describe('DiscoveryStatusBar', () => {
  it('renders connection health and tracker metrics', () => {
    const wrapper = mount(DiscoveryStatusBar, {
      props: {
        backend: 'ok',
        oplab: 'error',
        tracker: true,
        trackedSymbols: 18,
        eventCount: 247,
        spot: 138_450,
      },
    })

    const connections = wrapper.findAll('.status-conn')
    expect(connections).toHaveLength(4)
    expect(connections[0].find('.conn-dot').classes()).toContain('ok')
    expect(connections[1].find('.conn-dot').classes()).toContain('error')
    expect(wrapper.text()).toContain('18 sym · 247 ev')
    expect(wrapper.text()).toContain('138.450')
  })

  it('emits refresh from the status action', async () => {
    const wrapper = mount(DiscoveryStatusBar)

    await wrapper.get('button[title="Atualizar todos"]').trigger('click')

    expect(wrapper.emitted('refresh')).toHaveLength(1)
  })
})

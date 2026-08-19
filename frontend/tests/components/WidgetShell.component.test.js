import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import WidgetShell from '../../src/components/discovery/WidgetShell.vue'

const widget = {
  id: 'w12',
  icon: 'FLOW',
  title: 'Funds Flow',
  x: 40,
  y: 60,
  w: 720,
  h: 480,
  z: 7,
}

describe('WidgetShell', () => {
  it('applies persisted geometry and renders slot content', () => {
    const wrapper = mount(WidgetShell, {
      props: { widget },
      slots: { default: '<div class="test-content">conteúdo</div>' },
    })

    expect(wrapper.attributes('style')).toContain('left: 40px')
    expect(wrapper.attributes('style')).toContain('width: 720px')
    expect(wrapper.get('.widget-title').text()).toBe('Funds Flow')
    expect(wrapper.get('.test-content').text()).toBe('conteúdo')
  })

  it('forwards window commands with the expected widget identity', async () => {
    const wrapper = mount(WidgetShell, { props: { widget } })

    await wrapper.get('.wctl-reload').trigger('click')
    await wrapper.get('.wctl-close').trigger('click')
    await wrapper.get('.widget-titlebar').trigger('mousedown')
    await wrapper.get('.resize-handle').trigger('mousedown')

    expect(wrapper.emitted('reload')[0]).toEqual([widget])
    expect(wrapper.emitted('close')[0]).toEqual(['w12'])
    expect(wrapper.emitted('start-drag')[0][1]).toEqual(widget)
    expect(wrapper.emitted('start-resize')[0][1]).toEqual(widget)
  })
})

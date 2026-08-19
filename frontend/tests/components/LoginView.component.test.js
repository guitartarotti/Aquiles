import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  replace: vi.fn(),
  route: { query: {} },
}))

vi.mock('../../src/api', () => ({
  default: { post: mocks.post },
}))

vi.mock('vue-router', () => ({
  useRoute: () => mocks.route,
  useRouter: () => ({ replace: mocks.replace }),
}))

import { clearAuthSession, hasAuthSession } from '../../src/auth/session'
import LoginView from '../../src/views/LoginView.vue'

describe('LoginView', () => {
  beforeEach(() => {
    clearAuthSession()
    mocks.post.mockReset()
    mocks.replace.mockReset()
    mocks.route.query = {}
  })

  it('submits credentials, stores the session and restores the protected route', async () => {
    mocks.route.query = { redirect: '/discovery' }
    mocks.post.mockResolvedValue({
      data: {
        access_token: 'component-token',
        user: { username: 'analista' },
      },
    })
    const wrapper = mount(LoginView)

    await wrapper.get('#username').setValue('analista')
    await wrapper.get('#password').setValue('segredo')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(mocks.post).toHaveBeenCalledWith('/api/auth/login', {
      username: 'analista',
      password: 'segredo',
    })
    expect(hasAuthSession()).toBe(true)
    expect(mocks.replace).toHaveBeenCalledWith('/discovery')
    expect(wrapper.get('#password').element.value).toBe('')
  })

  it('shows the backend error and re-enables submission', async () => {
    mocks.post.mockRejectedValue(new Error('Credenciais inválidas.'))
    const wrapper = mount(LoginView)

    await wrapper.get('#username').setValue('analista')
    await wrapper.get('#password').setValue('incorreta')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toBe('Credenciais inválidas.')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
    expect(hasAuthSession()).toBe(false)
  })

  it('rejects protocol-relative redirect targets', async () => {
    mocks.route.query = { redirect: '//host-malicioso.test' }
    mocks.post.mockResolvedValue({
      data: {
        access_token: 'component-token',
        user: { username: 'analista' },
      },
    })
    const wrapper = mount(LoginView)

    await wrapper.get('#username').setValue('analista')
    await wrapper.get('#password').setValue('segredo')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(mocks.replace).toHaveBeenCalledWith('/')
  })
})

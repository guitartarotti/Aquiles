import { expect, test } from '@playwright/test'

const session = {
  accessToken: 'e2e-access-token',
  user: { username: 'analista.e2e' },
}

async function useAuthenticatedSession(page) {
  await page.addInitScript(value => {
    window.sessionStorage.setItem('aquiles.auth.session', JSON.stringify(value))
  }, session)
}

async function mockAquilesApis(page, { rejectLogin = false } = {}) {
  await page.route(url => url.pathname.startsWith('/api/'), async route => {
    const requestUrl = new URL(route.request().url())
    const headers = {
      'access-control-allow-origin': '*',
      'content-type': 'application/json',
    }

    if (requestUrl.pathname === '/api/auth/login') {
      if (rejectLogin) {
        await route.fulfill({
          status: 401,
          headers,
          body: JSON.stringify({ error: 'Credenciais inválidas.' }),
        })
        return
      }
      await route.fulfill({
        status: 200,
        headers,
        body: JSON.stringify({
          success: true,
          data: {
            access_token: session.accessToken,
            user: session.user,
          },
        }),
      })
      return
    }

    await route.fulfill({
      status: 200,
      headers,
      body: JSON.stringify({
        success: true,
        data: {
          running: true,
          tracked_symbols: 12,
          event_count: 84,
          spot: 138450,
          items: [],
          rows: [],
        },
      }),
    })
  })
}

test('redireciona visitante sem sessão para o login', async ({ page }) => {
  await page.goto('/discovery')

  await expect(page).toHaveURL(/\/login\?redirect=\/discovery$/)
  await expect(page.getByRole('heading', { name: 'Acesso seguro' })).toBeVisible()
})

test('mantém o usuário no login quando as credenciais falham', async ({ page }) => {
  await mockAquilesApis(page, { rejectLogin: true })
  await page.goto('/login')

  await page.getByLabel('Usuário').fill('analista')
  await page.getByLabel('Senha').fill('incorreta')
  await page.getByRole('button', { name: 'Entrar' }).click()

  await expect(page.getByRole('alert')).toHaveText('Credenciais inválidas.')
  await expect(page).toHaveURL(/\/login$/)
})

test('autentica e retorna para a rota protegida solicitada', async ({ page }) => {
  await mockAquilesApis(page)
  await page.goto('/options')

  await page.getByLabel('Usuário').fill('analista')
  await page.getByLabel('Senha').fill('segredo')
  await page.getByRole('button', { name: 'Entrar' }).click()

  await expect(page).toHaveURL(/\/options$/)
  await expect(page.getByRole('heading', { name: 'Options Dashboard' })).toBeVisible()
  await expect(page.getByLabel('Sessão atual')).toContainText('analista.e2e')
})

test('navega da página inicial para o Discovery', async ({ page }) => {
  await useAuthenticatedSession(page)
  await mockAquilesApis(page)
  await page.goto('/')

  await page.getByRole('button', { name: 'Open Discovery' }).click()

  await expect(page).toHaveURL(/\/discovery$/)
  await expect(page.getByRole('button', { name: /Adicionar widget/ })).toBeVisible()
})

test('adiciona um widget e restaura o layout após recarregar', async ({ page }) => {
  await useAuthenticatedSession(page)
  await mockAquilesApis(page)
  await page.goto('/discovery')

  await page.getByRole('button', { name: /Adicionar widget/ }).click()
  await page.getByPlaceholder('Busque por sigla, nome, tema ou descricao...').fill('Exposição')
  await page.locator('.picker-card').filter({ hasText: 'Exposição (DEX/GEX/VEX/CEX)' }).click()
  await expect(page.locator('.widget-title')).toHaveText('Exposição (DEX/GEX/VEX/CEX)')

  await page.reload()

  await expect(page.locator('.widget-title')).toHaveText('Exposição (DEX/GEX/VEX/CEX)')
})

test('encerra a sessão e bloqueia novamente as rotas privadas', async ({ page }) => {
  await useAuthenticatedSession(page)
  await mockAquilesApis(page)
  await page.goto('/')

  await page.getByRole('button', { name: 'Sair' }).click()

  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByRole('heading', { name: 'Acesso seguro' })).toBeVisible()
  const storedSession = await page.evaluate(() => window.sessionStorage.getItem('aquiles.auth.session'))
  expect(storedSession).toBeNull()
})

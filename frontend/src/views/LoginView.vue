<template>
  <main class="login-page">
    <section class="login-panel" aria-labelledby="login-title">
      <header class="login-brand">
        <span class="brand-mark" aria-hidden="true">A</span>
        <div>
          <p class="brand-name">AQUILES</p>
          <p class="brand-context">Market intelligence</p>
        </div>
      </header>

      <div class="login-heading">
        <h1 id="login-title">Acesso seguro</h1>
        <p>Entre com sua identidade autorizada.</p>
      </div>

      <form class="login-form" @submit.prevent="submitLogin">
        <label for="username">Usuário</label>
        <input
          id="username"
          ref="usernameInput"
          v-model.trim="username"
          name="username"
          type="text"
          autocomplete="username"
          maxlength="128"
          required
        />

        <label for="password">Senha</label>
        <input
          id="password"
          v-model="password"
          name="password"
          type="password"
          autocomplete="current-password"
          maxlength="1024"
          required
        />

        <p v-if="errorMessage" class="login-error" role="alert">{{ errorMessage }}</p>

        <button type="submit" :disabled="submitting">
          {{ submitting ? 'Validando...' : 'Entrar' }}
        </button>
      </form>
    </section>
  </main>
</template>

<script setup>
import { nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import service from '../api'
import { setAuthSession } from '../auth/session'

const route = useRoute()
const router = useRouter()
const usernameInput = ref(null)
const username = ref('')
const password = ref('')
const submitting = ref(false)
const errorMessage = ref('')

onMounted(() => nextTick(() => usernameInput.value?.focus()))

function safeRedirect() {
  const redirect = String(route.query.redirect || '')
  return redirect.startsWith('/') && !redirect.startsWith('//') ? redirect : '/'
}

async function submitLogin() {
  submitting.value = true
  errorMessage.value = ''
  try {
    const response = await service.post('/api/auth/login', {
      username: username.value,
      password: password.value,
    })
    setAuthSession(response.data.access_token, response.data.user)
    password.value = ''
    await router.replace(safeRedirect())
  } catch (error) {
    errorMessage.value = error?.message || 'Não foi possível validar o acesso.'
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 32px 20px;
  background: #eef2f5;
  color: #151a20;
}

.login-panel {
  width: min(100%, 390px);
  padding: 32px;
  background: #ffffff;
  border: 1px solid #ccd4dc;
  border-top: 4px solid #bc2634;
  border-radius: 6px;
  box-shadow: 0 18px 48px rgba(25, 34, 43, 0.12);
}

.login-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-bottom: 24px;
  border-bottom: 1px solid #e1e6eb;
}

.brand-mark {
  display: grid;
  width: 40px;
  height: 40px;
  place-items: center;
  background: #151a20;
  color: #ffffff;
  font-size: 21px;
  font-weight: 700;
}

.brand-name {
  color: #151a20;
  font-size: 17px;
  font-weight: 700;
}

.brand-context {
  margin-top: 2px;
  color: #66717d;
  font-size: 12px;
}

.login-heading {
  margin: 28px 0 24px;
}

.login-heading h1 {
  font-size: 24px;
  font-weight: 650;
}

.login-heading p {
  margin-top: 7px;
  color: #66717d;
  font-size: 14px;
}

.login-form {
  display: grid;
  gap: 9px;
}

.login-form label {
  margin-top: 7px;
  color: #3d4650;
  font-size: 13px;
  font-weight: 600;
}

.login-form input {
  width: 100%;
  height: 44px;
  padding: 0 12px;
  border: 1px solid #aeb8c2;
  border-radius: 4px;
  background: #ffffff;
  color: #151a20;
  font: inherit;
  outline: none;
}

.login-form input:focus {
  border-color: #151a20;
  box-shadow: 0 0 0 3px rgba(21, 26, 32, 0.12);
}

.login-form button {
  height: 44px;
  margin-top: 15px;
  border: 0;
  border-radius: 4px;
  background: #bc2634;
  color: #ffffff;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
}

.login-form button:hover:not(:disabled) {
  background: #9f1f2b;
}

.login-form button:disabled {
  cursor: wait;
  opacity: 0.65;
}

.login-error {
  margin-top: 7px;
  padding: 10px 12px;
  border-left: 3px solid #bc2634;
  background: #fff1f2;
  color: #8f1f2b;
  font-size: 13px;
}

@media (max-width: 480px) {
  .login-panel {
    padding: 26px 22px;
  }
}
</style>

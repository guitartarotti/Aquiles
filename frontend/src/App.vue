<template>
  <router-view />
  <aside v-if="showSessionControl" class="session-control" aria-label="Sessão atual">
    <span>{{ authState.user?.username }}</span>
    <button type="button" title="Encerrar sessão" @click="logout">Sair</button>
  </aside>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { authState, clearAuthSession } from './auth/session'

const route = useRoute()
const router = useRouter()
const showSessionControl = computed(() => Boolean(authState.user && route.name !== 'Login'))

function logout() {
  clearAuthSession()
  router.replace({ name: 'Login' })
}

function requireAuthentication() {
  if (route.name !== 'Login') {
    router.replace({ name: 'Login', query: { redirect: route.fullPath } })
  }
}

onMounted(() => window.addEventListener('aquiles:auth-required', requireAuthentication))
onBeforeUnmount(() => window.removeEventListener('aquiles:auth-required', requireAuthentication))
</script>

<style>
:root {
  --aquiles-obsidian: #07090d;
  --aquiles-ink: #11161d;
  --aquiles-panel: #f7f9fc;
  --aquiles-border: #d7dde7;
  --aquiles-steel: #7b8798;
  --aquiles-platinum: #eef2f7;
}
/* 全局样式重置 */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  background: linear-gradient(180deg, #f8fafc 0%, #eef2f7 100%);
}

#app {
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color: var(--aquiles-ink);
  background-color: transparent;
}

.session-control {
  position: fixed;
  z-index: 10000;
  top: 12px;
  right: 12px;
  display: flex;
  align-items: center;
  gap: 9px;
  min-height: 34px;
  padding: 5px 6px 5px 11px;
  border: 1px solid rgba(132, 145, 159, 0.58);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 5px 16px rgba(12, 18, 24, 0.12);
  color: #38424d;
  font-size: 12px;
}

.session-control button {
  height: 25px;
  padding: 0 9px;
  border: 0;
  border-radius: 4px;
  background: #202832;
  color: #ffffff;
  cursor: pointer;
  font-size: 12px;
}

/* 滚动条样式 */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: rgba(215, 221, 231, 0.6);
}

::-webkit-scrollbar-thumb {
  background: #6f7c8d;
  border-radius: 999px;
}

::-webkit-scrollbar-thumb:hover {
  background: #576272;
}

/* 全局按钮样式 */
button {
  font-family: inherit;
}
</style>

<template>
  <div class="status-bar">
    <div class="status-left">
      <span class="status-brand">
        <svg class="brand-icon" viewBox="0 0 100 100" fill="none"
             stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"
             xmlns="http://www.w3.org/2000/svg">

          <!-- Anel externo (estático — moldura) -->
          <circle cx="50" cy="50" r="43" stroke-width="2"/>

          <!-- Anel vertical: gira lentamente no sentido horário -->
          <ellipse cx="50" cy="50" rx="16" ry="43" stroke-width="2">
            <animateTransform attributeName="transform" type="rotate"
              from="0 50 50" to="360 50 50"
              dur="9s" repeatCount="indefinite"/>
          </ellipse>

          <!-- Anel horizontal: gira em sentido anti-horário, velocidade diferente -->
          <ellipse cx="50" cy="50" rx="43" ry="16" stroke-width="2">
            <animateTransform attributeName="transform" type="rotate"
              from="0 50 50" to="-360 50 50"
              dur="13s" repeatCount="indefinite"/>
          </ellipse>

          <!-- Planeta: orbita sobre o anel externo -->
          <g>
            <circle cx="93" cy="50" r="5.5" fill="currentColor" stroke="none"/>
            <animateTransform attributeName="transform" type="rotate"
              from="0 50 50" to="360 50 50"
              dur="6s" repeatCount="indefinite"/>
          </g>
        </svg>
        DISCOVERY
      </span>
    </div>
    <div class="status-center">
      <div v-for="conn in connections" :key="conn.id" class="status-conn">
        <span class="conn-dot" :class="conn.state" />
        <span class="conn-label">{{ conn.label }}</span>
        <span v-if="conn.value" class="conn-value">{{ conn.value }}</span>
      </div>
    </div>
    <div class="status-right">
      <span class="status-time">{{ timeStr }}</span>
      <button class="btn-refresh" @click="$emit('refresh')" title="Atualizar todos">⟳</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  oplab:   { type: String, default: 'unknown' },   // 'ok' | 'error' | 'unknown'
  backend: { type: String, default: 'unknown' },
  tracker: { type: Boolean, default: false },
  spot:    { type: Number, default: null },
  trackedSymbols: { type: Number, default: 0 },
  eventCount: { type: Number, default: 0 },
})
defineEmits(['refresh'])

const now = ref(new Date())
let timer = null
onMounted(() => { timer = setInterval(() => { now.value = new Date() }, 1000) })
onUnmounted(() => clearInterval(timer))

const timeStr = computed(() => now.value.toLocaleTimeString('pt-BR', { hour12: false }))

const connections = computed(() => [
  {
    id: 'backend',
    label: 'Backend',
    state: props.backend === 'ok' ? 'ok' : props.backend === 'error' ? 'error' : 'idle',
    value: null
  },
  {
    id: 'oplab',
    label: 'OpLab',
    state: props.oplab === 'ok' ? 'ok' : props.oplab === 'error' ? 'error' : 'idle',
    value: null
  },
  {
    id: 'tracker',
    label: 'Volume Tracker',
    state: props.tracker ? 'ok' : 'idle',
    value: props.tracker ? `${props.trackedSymbols} sym · ${props.eventCount} ev` : 'parado'
  },
  {
    id: 'spot',
    label: 'Spot',
    state: props.spot ? 'ok' : 'idle',
    value: props.spot ? props.spot.toLocaleString('pt-BR') : '—'
  },
])
</script>

<style scoped>
.status-bar {
  display: flex;
  align-items: center;
  height: 32px;
  padding: 0 14px;
  background: #070b14;
  border-bottom: 1px solid rgba(59,130,246,0.15);
  font-size: 11px;
  gap: 20px;
  flex-shrink: 0;
}
.status-left  { flex: 0 0 auto; }
.status-center { flex: 1; display: flex; gap: 16px; }
.status-right { flex: 0 0 auto; display: flex; align-items: center; gap: 8px; }

.status-brand {
  display: flex;
  align-items: center;
  gap: 7px;
  font-weight: 700;
  letter-spacing: 0.12em;
  color: #6366f1;
  font-size: 11px;
}
.brand-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  opacity: 0.92;
}

.status-conn {
  display: flex; align-items: center; gap: 4px;
  color: #64748b;
}
.conn-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: #374151;
}
.conn-dot.ok    { background: #10b981; box-shadow: 0 0 4px #10b981; }
.conn-dot.error { background: #ef4444; }
.conn-dot.idle  { background: #4b5563; }

.conn-label { color: #94a3b8; }
.conn-value { color: #e2e8f0; font-variant-numeric: tabular-nums; }

.status-time {
  color: #475569;
  font-variant-numeric: tabular-nums;
  font-size: 10px;
  letter-spacing: 0.05em;
}
.btn-refresh {
  background: none; border: none;
  color: #475569; cursor: pointer;
  font-size: 14px; padding: 2px 4px;
  border-radius: 4px;
  transition: color 0.15s;
}
.btn-refresh:hover { color: #6366f1; }
</style>

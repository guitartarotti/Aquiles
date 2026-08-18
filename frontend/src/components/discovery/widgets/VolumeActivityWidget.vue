<template>
  <div class="va-widget">

    <!-- ── Linha 1: tipo + stats ── -->
    <div class="va-header">
      <div class="va-type-btns">
        <button class="va-btn" :class="{ active: typeFilter === 'all' }"  @click="typeFilter = 'all'">Todos</button>
        <button class="va-btn call" :class="{ active: typeFilter === 'C' }" @click="typeFilter = 'C'">Call</button>
        <button class="va-btn put"  :class="{ active: typeFilter === 'P' }" @click="typeFilter = 'P'">Put</button>
      </div>

      <div class="va-stats">
        <span class="va-pill">{{ filtered.length }}<span class="dim">/{{ events.length }}</span></span>
        <span class="va-pill accent">Δ {{ totalDelta }}</span>
      </div>

      <button class="va-filter-toggle" :class="{ open: showFilters }" @click="showFilters = !showFilters"
              :title="showFilters ? 'Ocultar filtros' : 'Mostrar filtros'">
        ⚙ <span>{{ activeFilterCount > 0 ? activeFilterCount : '' }}</span>
      </button>
    </div>

    <!-- ── Linha 2: filtros avançados (colapsável) ── -->
    <div class="va-filters-panel" v-show="showFilters">

      <!-- Δ Volume mínimo -->
      <div class="va-filter-row">
        <span class="va-filter-label">Δ Mínimo</span>
        <div class="va-chips">
          <button v-for="opt in volOpts" :key="opt.value"
                  class="va-chip" :class="{ active: minVol === opt.value }"
                  @click="minVol = opt.value">{{ opt.label }}</button>
        </div>
      </div>

      <!-- Proximidade de strike -->
      <div class="va-filter-row">
        <span class="va-filter-label">Strike</span>
        <div class="va-chips">
          <button v-for="opt in strikeOpts" :key="opt.value"
                  class="va-chip" :class="{ active: strikeProx === opt.value }"
                  @click="strikeProx = opt.value">{{ opt.label }}</button>
        </div>
        <span class="va-spot-hint" v-if="effectiveSpot">spot {{ fmtSpot }}</span>
      </div>

      <!-- Dias úteis até vencimento -->
      <div class="va-filter-row">
        <span class="va-filter-label">Venc.</span>
        <div class="va-chips">
          <button v-for="opt in duOpts" :key="opt.value"
                  class="va-chip" :class="{ active: maxDu === opt.value }"
                  @click="maxDu = opt.value">{{ opt.label }}</button>
        </div>
      </div>

      <!-- Reset -->
      <button v-if="activeFilterCount > 0" class="va-reset" @click="resetFilters">
        ✕ limpar filtros
      </button>
    </div>

    <!-- ── Lista de eventos ── -->
    <div class="va-list">
      <div v-if="loading && !events.length" class="va-empty">Carregando…</div>
      <div v-else-if="!filtered.length" class="va-empty">
        {{ events.length ? 'Nenhum evento com esses filtros' : 'Nenhuma atividade recente' }}
      </div>

      <transition-group v-else name="va-slide" tag="div" class="va-items">
        <div v-for="ev in filtered" :key="ev.event_id || ev.symbol + ev.captured_at"
             class="va-event" :class="putCallClass(ev.put_call)">

          <!-- Badge tipo -->
          <span class="va-badge" :class="putCallClass(ev.put_call)">
            {{ ev.put_call === 'C' ? 'C' : ev.put_call === 'P' ? 'P' : '?' }}
          </span>

          <!-- Símbolo -->
          <span class="va-symbol">{{ ev.symbol }}</span>

          <!-- Strike + % do spot -->
          <span class="va-strike-wrap">
            <span class="va-strike">{{ fmtStrike(ev.strike) }}</span>
            <span class="va-dist" :class="distClass(ev)">{{ fmtDist(ev) }}</span>
          </span>

          <!-- DU -->
          <span class="va-du" :title="fmtExpiry(ev.expiry_date)">
            {{ ev.days_to_maturity != null ? ev.days_to_maturity + ' du' : '—' }}
          </span>

          <!-- Δ Volume -->
          <span class="va-delta" :class="putCallClass(ev.put_call)">
            +{{ fmtVol(ev.volume_delta) }}
          </span>

          <!-- Horário -->
          <span class="va-time">{{ fmtTime(ev.captured_at) }}</span>
        </div>
      </transition-group>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { getVolumeActivity } from '@/api/options'

const props = defineProps({
  underlying:  { type: String,  default: 'IBOVE Index' },
  autoRefresh: { type: Boolean, default: true },
  limit:       { type: Number,  default: 200 },
  spotPrice:   { type: Number,  default: null },   // spot atual do mercado
})

// ─── Estado ────────────────────────────────────────────────────────────────────
const events      = ref([])
const loading     = ref(false)
const showFilters = ref(false)

// Filtros
const typeFilter  = ref('all')   // 'all' | 'C' | 'P'
const minVol      = ref(0)       // volume_delta mínimo
const strikeProx  = ref(null)    // % máx de distância do spot (null = sem filtro)
const maxDu       = ref(null)    // DU máximo até vencimento (null = sem filtro)

let timer = null

function normalizeRows(payload) {
  const rows = Array.isArray(payload) ? payload.slice() : []
  rows.sort((a, b) => String(b?.captured_at || '').localeCompare(String(a?.captured_at || '')))
  return rows
}

function handleVisibilityRefresh() {
  if (document.visibilityState === 'visible') load()
}

function handleWindowFocus() {
  load()
}

// ─── Opções dos filtros ────────────────────────────────────────────────────────

const volOpts = [
  { label: 'Todos',  value: 0     },
  { label: '>100',   value: 100   },
  { label: '>500',   value: 500   },
  { label: '>1k',    value: 1000  },
  { label: '>5k',    value: 5000  },
  { label: '>10k',   value: 10000 },
]

const strikeOpts = [
  { label: 'Todos', value: null },
  { label: '≤1%',   value: 0.01 },
  { label: '≤2%',   value: 0.02 },
  { label: '≤5%',   value: 0.05 },
  { label: '≤10%',  value: 0.10 },
]

const duOpts = [
  { label: 'Todos', value: null },
  { label: '≤5 du', value: 5   },
  { label: '≤21',   value: 21  },
  { label: '≤42',   value: 42  },
  { label: '≤63',   value: 63  },
]

// ─── Spot (prop ou derivado dos eventos) ──────────────────────────────────────
const effectiveSpot = computed(() => {
  if (props.spotPrice) return props.spotPrice
  // fallback: pega do evento mais recente
  const ev = events.value.find(e => e.spot_price)
  return ev?.spot_price ?? null
})

const fmtSpot = computed(() => {
  const s = effectiveSpot.value
  if (!s) return '—'
  return (s / 1000).toFixed(1) + 'k'
})

// ─── Filtro principal ─────────────────────────────────────────────────────────
const filtered = computed(() => {
  let rows = events.value

  // Tipo call/put
  if (typeFilter.value !== 'all') {
    rows = rows.filter(e => (e.put_call ?? '').toUpperCase() === typeFilter.value)
  }

  // Δ volume mínimo
  if (minVol.value > 0) {
    rows = rows.filter(e => (e.volume_delta ?? 0) >= minVol.value)
  }

  // Proximidade de strike (% em relação ao spot)
  if (strikeProx.value != null && effectiveSpot.value) {
    const spot = effectiveSpot.value
    rows = rows.filter(e => {
      const s = parseFloat(e.strike ?? 0)
      if (!s) return true   // sem strike → não filtra
      return Math.abs(s - spot) / spot <= strikeProx.value
    })
  }

  // DU máximo
  if (maxDu.value != null) {
    rows = rows.filter(e => {
      const du = e.days_to_maturity
      if (du == null) return true  // sem DU → não filtra
      return du <= maxDu.value
    })
  }

  return rows
})

const activeFilterCount = computed(() => {
  let n = 0
  if (typeFilter.value !== 'all') n++
  if (minVol.value > 0) n++
  if (strikeProx.value != null) n++
  if (maxDu.value != null) n++
  return n
})

const totalDelta = computed(() => {
  const sum = filtered.value.reduce((s, e) => s + (e.volume_delta ?? 0), 0)
  return fmtVol(sum)
})

function resetFilters() {
  typeFilter.value = 'all'
  minVol.value     = 0
  strikeProx.value = null
  maxDu.value      = null
}

// ─── Carga de dados ────────────────────────────────────────────────────────────
async function load() {
  try {
    loading.value = true
    const res = await getVolumeActivity({
      underlying_security: props.underlying,
      limit: props.limit,
    })
    events.value = normalizeRows(res?.data)
  } catch {
    // silent retry
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  load()
  if (props.autoRefresh) timer = setInterval(load, 15_000)
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', handleVisibilityRefresh)
  }
  if (typeof window !== 'undefined') {
    window.addEventListener('focus', handleWindowFocus)
  }
})
onUnmounted(() => {
  clearInterval(timer)
  if (typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', handleVisibilityRefresh)
  }
  if (typeof window !== 'undefined') {
    window.removeEventListener('focus', handleWindowFocus)
  }
})
watch(() => props.underlying, load)

// ─── Helpers de formatação ────────────────────────────────────────────────────
function putCallClass(pc) {
  if (!pc) return ''
  return pc.toUpperCase() === 'C' ? 'call' : pc.toUpperCase() === 'P' ? 'put' : ''
}

function fmtStrike(v) {
  if (!v) return '—'
  const n = parseFloat(v)
  return n >= 1000 ? (n / 1000).toFixed(0) + 'k' : n.toFixed(0)
}

// % de distância do strike em relação ao spot
function distPct(ev) {
  const s = parseFloat(ev.strike ?? 0)
  const spot = ev.spot_price ?? effectiveSpot.value
  if (!s || !spot) return null
  return (s - spot) / spot   // negativo = abaixo do spot
}

function fmtDist(ev) {
  const pct = distPct(ev)
  if (pct == null) return ''
  const sign = pct >= 0 ? '+' : ''
  return sign + (pct * 100).toFixed(1) + '%'
}

function distClass(ev) {
  const pct = distPct(ev)
  if (pct == null) return ''
  const abs = Math.abs(pct)
  if (abs <= 0.01) return 'atm'
  if (abs <= 0.03) return 'near'
  return 'far'
}

function fmtExpiry(v) {
  if (!v) return '—'
  try {
    const s = String(v).replace(/-/g, '')
    if (s.length === 8) return s.slice(6, 8) + '/' + s.slice(4, 6) + '/' + s.slice(0, 4)
    return new Date(v).toLocaleDateString('pt-BR')
  } catch { return v }
}

function fmtVol(v) {
  if (v == null) return '—'
  const n = Number(v)
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M'
  if (n >= 1e3) return (n / 1e3).toFixed(0) + 'K'
  return n.toLocaleString('pt-BR')
}

function fmtTime(v) {
  if (!v) return ''
  try { return new Date(v).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) }
  catch { return v }
}
</script>

<style scoped>
.va-widget { height: 100%; display: flex; flex-direction: column; padding: 6px 8px; gap: 4px; font-size: 11px; }

/* ── Header ── */
.va-header { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }

.va-type-btns { display: flex; gap: 2px; }
.va-btn {
  padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.08);
  background: transparent; color: #64748b; font-size: 10px; font-weight: 600;
  cursor: pointer; transition: all 0.15s;
}
.va-btn.active          { background: #1e1b4b; border-color: #6366f1; color: #a5b4fc; }
.va-btn.call.active     { background: rgba(16,185,129,0.12); border-color: #10b981; color: #10b981; }
.va-btn.put.active      { background: rgba(248,113,113,0.12); border-color: #f87171; color: #f87171; }
.va-btn:hover:not(.active) { background: rgba(255,255,255,0.05); color: #94a3b8; }

.va-stats { margin-left: auto; display: flex; gap: 4px; align-items: center; }
.va-pill {
  font-size: 10px; color: #64748b;
  padding: 1px 6px; border-radius: 8px;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.06);
}
.va-pill .dim { color: #334155; }
.va-pill.accent { color: #6366f1; border-color: rgba(99,102,241,0.3); background: rgba(99,102,241,0.07); }

.va-filter-toggle {
  padding: 2px 7px; border-radius: 4px;
  border: 1px solid rgba(255,255,255,0.08);
  background: transparent; color: #475569;
  font-size: 10px; cursor: pointer; transition: all 0.15s;
  display: flex; align-items: center; gap: 3px;
}
.va-filter-toggle span { font-size: 9px; font-weight: 700; color: #6366f1; }
.va-filter-toggle:hover,
.va-filter-toggle.open { background: rgba(99,102,241,0.08); border-color: rgba(99,102,241,0.3); color: #a5b4fc; }

/* ── Painel de filtros ── */
.va-filters-panel {
  flex-shrink: 0;
  background: rgba(0,0,0,0.2);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 6px;
  padding: 8px 10px;
  display: flex; flex-direction: column; gap: 6px;
}

.va-filter-row { display: flex; align-items: center; gap: 6px; }
.va-filter-label {
  font-size: 9px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.07em; color: #475569;
  min-width: 40px; flex-shrink: 0;
}
.va-chips { display: flex; gap: 3px; flex-wrap: wrap; }
.va-chip {
  padding: 2px 7px; border-radius: 10px;
  border: 1px solid rgba(255,255,255,0.07);
  background: transparent; color: #475569;
  font-size: 10px; cursor: pointer; transition: all 0.12s;
  white-space: nowrap;
}
.va-chip:hover { border-color: rgba(99,102,241,0.3); color: #94a3b8; }
.va-chip.active { background: rgba(99,102,241,0.15); border-color: #6366f1; color: #a5b4fc; font-weight: 700; }

.va-spot-hint { font-size: 9px; color: #475569; margin-left: auto; }
.va-reset {
  align-self: flex-start; margin-top: 2px;
  padding: 2px 8px; border-radius: 4px;
  border: 1px solid rgba(239,68,68,0.2);
  background: rgba(239,68,68,0.06); color: #f87171;
  font-size: 9px; cursor: pointer; transition: all 0.12s;
}
.va-reset:hover { background: rgba(239,68,68,0.12); }

/* ── Lista ── */
.va-list { flex: 1; overflow-y: auto; min-height: 0; }
.va-list::-webkit-scrollbar { width: 3px; }
.va-list::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 2px; }

.va-empty { color: #334155; font-size: 11px; padding: 20px; text-align: center; }

.va-items { display: flex; flex-direction: column; gap: 2px; }

.va-event {
  display: grid;
  grid-template-columns: 18px 90px 1fr auto auto auto;
  align-items: center; gap: 6px;
  padding: 5px 8px; border-radius: 5px;
  background: #0a1120;
  border: 1px solid rgba(255,255,255,0.04);
  transition: background 0.1s;
  border-left: 2px solid transparent;
}
.va-event:hover    { background: #0d1520; }
.va-event.call     { border-left-color: rgba(16,185,129,0.5); }
.va-event.put      { border-left-color: rgba(248,113,113,0.5); }

.va-badge {
  font-size: 9px; font-weight: 800; letter-spacing: 0.05em;
  width: 14px; text-align: center;
}
.va-badge.call { color: #10b981; }
.va-badge.put  { color: #f87171; }

.va-symbol {
  color: #e2e8f0; font-weight: 600; font-size: 11px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

.va-strike-wrap { display: flex; flex-direction: column; gap: 1px; }
.va-strike  { color: #94a3b8; font-variant-numeric: tabular-nums; font-size: 11px; }
.va-dist    { font-size: 9px; font-variant-numeric: tabular-nums; }
.va-dist.atm  { color: #f59e0b; font-weight: 700; }
.va-dist.near { color: #6366f1; }
.va-dist.far  { color: #334155; }

.va-du {
  font-size: 10px; color: #475569;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.va-delta {
  font-weight: 700; font-size: 11px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.va-delta.call { color: #10b981; }
.va-delta.put  { color: #f87171; }

.va-time { font-size: 9px; color: #334155; font-variant-numeric: tabular-nums; white-space: nowrap; }

/* Transition */
.va-slide-enter-active { transition: all 0.2s ease; }
.va-slide-enter-from   { opacity: 0; transform: translateY(-4px); }
</style>

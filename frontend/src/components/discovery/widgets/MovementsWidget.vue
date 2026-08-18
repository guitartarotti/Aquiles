<template>
  <div class="mv-widget">

    <!-- Controls -->
    <div class="mv-controls">
      <div class="mv-filters">
        <button class="mv-btn" :class="{ active: filter === 'all' }"  @click="filter = 'all'">Todos</button>
        <button class="mv-btn" :class="{ active: filter === 'C' }"    @click="filter = 'C'">Call</button>
        <button class="mv-btn" :class="{ active: filter === 'P' }"    @click="filter = 'P'">Put</button>
      </div>
      <div class="mv-search-wrap">
        <input v-model="search" class="mv-search" placeholder="Buscar símbolo…" />
      </div>
      <div class="mv-summary">
        <span class="mv-pill">{{ filtered.length }} mov.</span>
        <span class="mv-pill call">+{{ callDelta }}</span>
        <span class="mv-pill put">+{{ putDelta }}</span>
      </div>
    </div>

    <!-- Table -->
    <div class="mv-table-wrap">
      <table class="mv-table">
        <thead>
          <tr>
            <th @click="sort('put_call')"    :class="sortCls('put_call')">Tipo</th>
            <th @click="sort('symbol')"      :class="sortCls('symbol')">Símbolo</th>
            <th @click="sort('strike')"      :class="sortCls('strike')">Strike</th>
            <th @click="sort('expiry_date')" :class="sortCls('expiry_date')">Venc.</th>
            <th @click="sort('days_to_maturity')" :class="sortCls('days_to_maturity')">DU</th>
            <th @click="sort('volume_delta')" :class="sortCls('volume_delta')">Δ Vol</th>
            <th @click="sort('volume_after')" :class="sortCls('volume_after')">Vol Total</th>
            <th @click="sort('spot_price')"  :class="sortCls('spot_price')">Spot</th>
            <th>Bid</th>
            <th>Ask</th>
            <th @click="sort('captured_at')" :class="sortCls('captured_at')">Horário</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td colspan="11" class="mv-loading">Carregando…</td>
          </tr>
          <tr v-else-if="!filtered.length">
            <td colspan="11" class="mv-empty">Nenhuma movimentação</td>
          </tr>
          <tr v-for="ev in paged" :key="ev.event_id || ev.symbol + ev.captured_at"
              class="mv-row" :class="putCallClass(ev.put_call)">
            <td>
              <span class="mv-badge" :class="putCallClass(ev.put_call)">
                {{ ev.put_call === 'C' ? 'CALL' : ev.put_call === 'P' ? 'PUT' : ev.put_call || '—' }}
              </span>
            </td>
            <td class="mv-symbol">{{ ev.symbol }}</td>
            <td class="mv-num">{{ fmtStrike(ev.strike) }}</td>
            <td class="mv-date">{{ fmtExpiry(ev.expiry_date) }}</td>
            <td class="mv-num dim">{{ ev.days_to_maturity ?? '—' }}</td>
            <td class="mv-num delta" :class="putCallClass(ev.put_call)">
              +{{ (ev.volume_delta ?? 0).toLocaleString('pt-BR') }}
            </td>
            <td class="mv-num dim">{{ fmtVol(ev.volume_after) }}</td>
            <td class="mv-num">{{ fmtNum(ev.spot_price, 0) }}</td>
            <td class="mv-num dim">{{ fmtNum(ev.bid, 2) }}</td>
            <td class="mv-num dim">{{ fmtNum(ev.ask, 2) }}</td>
            <td class="mv-time">{{ fmtTime(ev.captured_at) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    <div class="mv-footer" v-if="totalPages > 1">
      <button class="mv-page-btn" :disabled="page === 1" @click="page--">‹</button>
      <span class="mv-page-info">{{ page }} / {{ totalPages }}</span>
      <button class="mv-page-btn" :disabled="page === totalPages" @click="page++">›</button>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { getVolumeActivity } from '@/api/options'

const props = defineProps({
  underlying:  { type: String,  default: 'IBOVE Index' },
  autoRefresh: { type: Boolean, default: true },
  limit:       { type: Number,  default: 500 },
  pageSize:    { type: Number,  default: 30 },
})

const events  = ref([])
const loading = ref(false)
const filter  = ref('all')
const search  = ref('')
const page    = ref(1)
const sortKey = ref('captured_at')
const sortDir = ref(-1)   // -1 = desc, 1 = asc
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

// ─── Load ─────────────────────────────────────────────────────────────────────

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
watch(() => props.underlying, () => { page.value = 1; load() })

// ─── Filtering & sorting ───────────────────────────────────────────────────────

function putCallClass(pc) {
  if (!pc) return ''
  return pc.toUpperCase() === 'C' ? 'call' : pc.toUpperCase() === 'P' ? 'put' : ''
}

const filtered = computed(() => {
  let rows = events.value
  if (filter.value !== 'all') rows = rows.filter(e => (e.put_call ?? '').toUpperCase() === filter.value)
  if (search.value.trim()) {
    const q = search.value.trim().toUpperCase()
    rows = rows.filter(e => (e.symbol ?? '').toUpperCase().includes(q))
  }
  // sort
  return rows.slice().sort((a, b) => {
    const av = a[sortKey.value] ?? 0
    const bv = b[sortKey.value] ?? 0
    if (av < bv) return -sortDir.value
    if (av > bv) return  sortDir.value
    return 0
  })
})

const callDelta = computed(() => {
  const sum = events.value.filter(e => e.put_call === 'C').reduce((s, e) => s + (e.volume_delta ?? 0), 0)
  return fmtVol(sum)
})
const putDelta = computed(() => {
  const sum = events.value.filter(e => e.put_call === 'P').reduce((s, e) => s + (e.volume_delta ?? 0), 0)
  return fmtVol(sum)
})

// ─── Pagination ───────────────────────────────────────────────────────────────

const totalPages = computed(() => Math.max(1, Math.ceil(filtered.value.length / props.pageSize)))
const paged = computed(() => {
  const start = (page.value - 1) * props.pageSize
  return filtered.value.slice(start, start + props.pageSize)
})

watch(filtered, () => { page.value = 1 })

// ─── Column sort ──────────────────────────────────────────────────────────────

function sort(key) {
  if (sortKey.value === key) { sortDir.value *= -1 }
  else { sortKey.value = key; sortDir.value = -1 }
}

function sortCls(key) {
  if (sortKey.value !== key) return 'sortable'
  return sortDir.value === -1 ? 'sort-desc' : 'sort-asc'
}

// ─── Formatters ───────────────────────────────────────────────────────────────

function fmtStrike(v) {
  if (v == null) return '—'
  const n = parseFloat(v)
  return n >= 1000 ? (n / 1000).toFixed(0) + 'k' : n.toFixed(0)
}

function fmtExpiry(v) {
  if (!v) return '—'
  const s = String(v).replace(/-/g, '')
  if (s.length === 8) return s.slice(4, 6) + '/' + s.slice(6, 8) + '/' + s.slice(2, 4)
  return v
}

function fmtVol(v) {
  if (v == null) return '—'
  const n = Number(v)
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M'
  if (n >= 1e3) return (n / 1e3).toFixed(0) + 'K'
  return n.toLocaleString('pt-BR')
}

function fmtNum(v, dec = 2) {
  if (v == null) return '—'
  return Number(v).toLocaleString('pt-BR', { minimumFractionDigits: dec, maximumFractionDigits: dec })
}

function fmtTime(v) {
  if (!v) return '—'
  try { return new Date(v).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) }
  catch { return v }
}
</script>

<style scoped>
.mv-widget {
  height: 100%; display: flex; flex-direction: column;
  padding: 6px 8px; gap: 6px; font-size: 11px;
}

/* Controls */
.mv-controls { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.mv-filters  { display: flex; gap: 3px; }
.mv-btn {
  padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.08);
  background: transparent; color: #64748b; font-size: 10px; font-weight: 600;
  cursor: pointer; transition: all 0.15s;
}
.mv-btn.active { background: #1e1b4b; border-color: #6366f1; color: #a5b4fc; }
.mv-btn:hover:not(.active) { background: rgba(255,255,255,0.05); }

.mv-search-wrap { flex: 1; }
.mv-search {
  width: 100%; padding: 3px 8px;
  background: #0a1120; border: 1px solid rgba(255,255,255,0.08);
  border-radius: 4px; color: #e2e8f0; font-size: 10px; outline: none;
}
.mv-search:focus { border-color: rgba(99,102,241,0.5); }
.mv-search::placeholder { color: #334155; }

.mv-summary { display: flex; gap: 4px; }
.mv-pill {
  font-size: 10px; padding: 1px 7px; border-radius: 8px;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.06);
  color: #64748b;
}
.mv-pill.call { color: #10b981; border-color: rgba(16,185,129,0.25); background: rgba(16,185,129,0.07); }
.mv-pill.put  { color: #f87171; border-color: rgba(248,113,113,0.25); background: rgba(248,113,113,0.07); }

/* Table */
.mv-table-wrap { flex: 1; overflow: auto; min-height: 0; }
.mv-table-wrap::-webkit-scrollbar { width: 4px; height: 4px; }
.mv-table-wrap::-webkit-scrollbar-track { background: transparent; }
.mv-table-wrap::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 2px; }

.mv-table { width: 100%; border-collapse: collapse; }
.mv-table th {
  position: sticky; top: 0; z-index: 1;
  padding: 5px 8px; text-align: right;
  background: #080e1a; color: #475569;
  font-size: 9px; font-weight: 700;
  letter-spacing: 0.06em; text-transform: uppercase;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  white-space: nowrap; cursor: pointer; user-select: none;
}
.mv-table th:first-child,
.mv-table th:nth-child(2) { text-align: left; }
.mv-table th.sortable { color: #334155; }
.mv-table th.sort-asc::after  { content: ' ↑'; color: #6366f1; }
.mv-table th.sort-desc::after { content: ' ↓'; color: #6366f1; }
.mv-table th:hover { color: #94a3b8; }

.mv-row { border-bottom: 1px solid rgba(255,255,255,0.03); transition: background 0.1s; }
.mv-row:hover { background: rgba(255,255,255,0.03); }
.mv-row.call { border-left: 2px solid rgba(16,185,129,0.4); }
.mv-row.put  { border-left: 2px solid rgba(248,113,113,0.4); }

.mv-table td { padding: 5px 8px; text-align: right; color: #94a3b8; white-space: nowrap; }
.mv-table td:first-child,
.mv-table td:nth-child(2) { text-align: left; }

.mv-badge {
  font-size: 9px; font-weight: 700; letter-spacing: 0.05em;
  padding: 1px 5px; border-radius: 3px;
}
.mv-badge.call { background: rgba(16,185,129,0.12); color: #10b981; }
.mv-badge.put  { background: rgba(248,113,113,0.12); color: #f87171; }

.mv-symbol { color: #e2e8f0; font-weight: 600; }
.mv-num    { font-variant-numeric: tabular-nums; }
.mv-num.dim { color: #475569; }
.mv-num.delta { font-weight: 700; }
.mv-num.delta.call { color: #10b981; }
.mv-num.delta.put  { color: #f87171; }
.mv-date   { color: #64748b; font-size: 10px; }
.mv-time   { color: #475569; font-size: 9px; font-variant-numeric: tabular-nums; }

.mv-loading, .mv-empty {
  text-align: center; padding: 24px;
  color: #334155; font-size: 11px;
}

/* Footer / pagination */
.mv-footer {
  display: flex; align-items: center; justify-content: center;
  gap: 8px; flex-shrink: 0; padding-top: 4px;
  border-top: 1px solid rgba(255,255,255,0.05);
}
.mv-page-btn {
  background: none; border: 1px solid rgba(255,255,255,0.08);
  border-radius: 4px; color: #64748b; cursor: pointer;
  padding: 2px 8px; font-size: 14px; line-height: 1;
  transition: all 0.1s;
}
.mv-page-btn:hover:not(:disabled) { border-color: #6366f1; color: #a5b4fc; }
.mv-page-btn:disabled { opacity: 0.3; cursor: default; }
.mv-page-info { font-size: 10px; color: #475569; min-width: 50px; text-align: center; }
</style>

<template>
  <div class="hnw-root">

    <!-- ── Header / controls ─────────────────────────────────────────────────── -->
    <div class="hnw-header">
      <span class="hnw-title">Headlines</span>

      <!-- Relevance filter -->
      <div class="hnw-pills">
        <button v-for="f in REL_FILTERS" :key="f.key"
                class="hnw-pill"
                :class="[`rel-${f.key}`, { active: relFilter === f.key }]"
                @click="relFilter = f.key">{{ f.label }}</button>
      </div>

      <!-- Scope filter -->
      <div class="hnw-pills">
        <button v-for="f in SCOPE_FILTERS" :key="f.key"
                class="hnw-pill sm"
                :class="{ active: scopeFilter === f.key }"
                @click="scopeFilter = f.key">{{ f.label }}</button>
      </div>

      <div class="hnw-spacer"/>

      <!-- Search -->
      <div class="hnw-search-wrap">
        <span class="hnw-search-icon">⌕</span>
        <input v-model="search" class="hnw-search" placeholder="buscar…" />
        <button v-if="search" class="hnw-search-clear" @click="search = ''">✕</button>
      </div>

      <!-- Refresh -->
      <span class="hnw-loading" v-if="loading">…</span>
      <button class="hnw-btn" @click="reload" :title="lastUpdate ? `Atualizado ${lastUpdate}` : ''">↺</button>
    </div>

    <!-- ── Feed ──────────────────────────────────────────────────────────────── -->
    <div class="hnw-list" ref="listEl">

      <div v-if="loading && !events.length" class="hnw-empty">Carregando…</div>
      <div v-else-if="!filtered.length" class="hnw-empty">
        {{ errMsg || 'Nenhuma headline encontrada' }}
      </div>

      <div v-for="ev in paginated" :key="ev.event_id || ev.headline"
           class="hnw-item"
           :class="`rel-${ev.relevance}`">

        <!-- Left accent bar (colored by relevance) -->
        <div class="hnw-bar" :class="`bar-${ev.relevance}`"></div>

        <!-- Card body -->
        <div class="hnw-body">

          <!-- Row 1: time + badges -->
          <div class="hnw-meta">
            <span class="hnw-time">{{ fmtTime(ev.event_time) }}</span>
            <span class="hnw-badge" :class="`badge-${ev.relevance}`">
              {{ REL_LABEL[ev.relevance] || ev.relevance }}
            </span>
            <span class="hnw-badge sig" :class="`sig-${ev.signal_strength}`"
                  v-if="ev.signal_strength && ev.signal_strength !== 'technical_low'">
              {{ SIG_LABEL[ev.signal_strength] || ev.signal_strength }}
            </span>
            <span class="hnw-scenario" v-if="ev.scenario_classification">
              {{ SCENARIO_LABEL[ev.scenario_classification] || ev.scenario_classification }}
            </span>
            <span class="hnw-score"
                  v-if="ev.macro_transmission_score != null"
                  :class="scoreClass(ev.macro_transmission_score)">
              ▲{{ (+ev.macro_transmission_score).toFixed(1) }}
            </span>
          </div>

          <!-- Row 2: headline text -->
          <div class="hnw-text">{{ ev.headline }}</div>

          <!-- Row 3: tags -->
          <div class="hnw-tags" v-if="hasTags(ev)">
            <span class="hnw-tag contract"
                  v-for="c in (ev.linked_contracts || []).slice(0, 4)" :key="c">
              {{ c }}
            </span>
            <span class="hnw-tag bucket"
                  v-for="b in (ev.linked_buckets || []).slice(0, 3)" :key="b">
              {{ BUCKET_LABEL[b] || b }}
            </span>
            <span class="hnw-tag theme"
                  v-for="t in (ev.themes || []).slice(0, 2)" :key="t">
              {{ t.replace(/_/g, ' ') }}
            </span>
            <span class="hnw-source">{{ ev.posted_by }}</span>
          </div>
          <div class="hnw-source-only" v-else>{{ ev.posted_by }}</div>

        </div>
      </div>
    </div>

    <!-- ── Paginação ─────────────────────────────────────────────────────────── -->
    <div class="hnw-pager" v-if="total > 0">

      <!-- Botões de navegação — só aparecem quando há mais de 1 página -->
      <template v-if="totalPages > 1">
        <button class="hnw-pg-btn" :disabled="page === 1"          @click="goPage(1)">«</button>
        <button class="hnw-pg-btn" :disabled="page === 1"          @click="goPage(page - 1)">‹</button>

        <template v-for="p in pageRange" :key="p">
          <span v-if="p === '…'" class="hnw-pg-ellipsis">…</span>
          <button v-else class="hnw-pg-btn num" :class="{ active: p === page }"
                  @click="goPage(p)">{{ p }}</button>
        </template>

        <button class="hnw-pg-btn" :disabled="page === totalPages" @click="goPage(page + 1)">›</button>
        <button class="hnw-pg-btn" :disabled="page === totalPages" @click="goPage(totalPages)">»</button>
      </template>

      <!-- Contador sempre visível -->
      <span class="hnw-pg-info">
        <span class="hnw-pg-range">{{ (page - 1) * PER_PAGE + 1 }}–{{ Math.min(page * PER_PAGE, total) }}</span>
        <span class="hnw-pg-sep">de</span>
        <span class="hnw-pg-total">{{ total }} notícias hoje</span>
        <span class="hnw-pg-pages" v-if="totalPages > 1">· pág {{ page }}/{{ totalPages }}</span>
        <span class="hnw-pg-warn" v-if="usingFallback" title="Reinicie o backend para ativar paginação completa">
          ⚠ reinicie o backend para ver todas
        </span>
      </span>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { getMacroEventsToday, getMacroEvents } from '@/api/macro'

// ─── Constants ────────────────────────────────────────────────────────────────
const REL_FILTERS = [
  { key: 'all',       label: 'Todas'     },
  { key: 'breaking',  label: 'Breaking'  },
  { key: 'important', label: 'Important' },
  { key: 'relevant',  label: 'Relevant'  },
]
const SCOPE_FILTERS = [
  { key: 'all',              label: 'Todos'     },
  { key: 'macro',            label: 'Macro'     },
  { key: 'tracked_security', label: 'Rastreado' },
]
const REL_LABEL = {
  breaking:  'BREAKING',
  important: 'IMPORT',
  relevant:  'RELEV',
}
const SIG_LABEL = {
  high:          '▲ ALTO',
  medium:        '▲ MED',
  low:           '▾ BAIXO',
  idiosyncratic: '◆ IDIO',
}
const SCENARIO_LABEL = {
  regime_shift:      'Regime',
  tradable_catalyst: 'Catalisador',
  secondary_echo:    'Eco',
  technical_noise:   'Ruído',
}
const BUCKET_LABEL = {
  index:        'IBOV',
  dollar:       'USD',
  curve_short:  'DI curto',
  curve_long:   'DI longo',
}

const BRT_OFF = -3 * 3_600_000

// ─── State ────────────────────────────────────────────────────────────────────
const loading    = ref(false)
const errMsg     = ref('')
const events     = ref([])
const lastUpdate = ref('')
const relFilter  = ref('all')
const scopeFilter = ref('all')
const search     = ref('')

const page      = ref(1)
const total     = ref(0)
const usingFallback = ref(false)
const PER_PAGE  = 100

const listEl = ref(null)
let refreshTimer = null

// ─── Load ─────────────────────────────────────────────────────────────────────
async function reload(resetPage = false) {
  if (resetPage) page.value = 1
  loading.value = true
  errMsg.value  = ''
  try {
    const offset = (page.value - 1) * PER_PAGE
    let payload  = null

    try {
      const res = await getMacroEventsToday({ limit: PER_PAGE, offset })
      payload = res?.data?.data ?? res?.data ?? {}
      usingFallback.value = false
    } catch (err) {
      const status = err?.response?.status
      if (status === 404 || status === 405) {
        // Endpoint novo ainda não disponível — reinicie o backend
        const res = await getMacroEvents({ limit: 100 })
        payload = res?.data?.data ?? res?.data ?? {}
        page.value = 1
        usingFallback.value = true
      } else {
        throw err
      }
    }

    const data   = payload?.events ?? (Array.isArray(payload) ? payload : [])
    events.value = Array.isArray(data) ? data : []
    total.value  = payload?.total ?? events.value.length
    if (listEl.value) listEl.value.scrollTop = 0
    const d = new Date(Date.now() + BRT_OFF)
    lastUpdate.value = `${String(d.getUTCHours()).padStart(2,'0')}:${String(d.getUTCMinutes()).padStart(2,'0')}`
  } catch (e) {
    errMsg.value = e?.message || 'Erro ao carregar'
    console.error('[Headlines]', e)
  } finally {
    loading.value = false
  }
}

// ─── Filtered list ────────────────────────────────────────────────────────────
const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  return events.value.filter(ev => {
    if (relFilter.value  !== 'all' && ev.relevance  !== relFilter.value)  return false
    if (scopeFilter.value !== 'all' && ev.macro_scope !== scopeFilter.value) return false
    if (q) {
      const hay = [ev.headline, ev.posted_by, ...(ev.linked_contracts || []),
                   ...(ev.themes || [])].join(' ').toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })
})

// ─── Pagination (server-side) ────────────────────────────────────────────────
// filtered ainda aplica os filtros locais sobre a página carregada
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PER_PAGE)))

// Os itens exibidos são sempre os da página atual já carregada,
// com filtros de relevância/escopo/busca aplicados localmente
const paginated = computed(() => filtered.value)

// Gera array de páginas com reticências: [1, '…', 4, 5, 6, '…', 12]
const pageRange = computed(() => {
  const tp  = totalPages.value
  const cur = page.value
  if (tp <= 7) return Array.from({ length: tp }, (_, i) => i + 1)
  const pages = new Set([1, tp, cur, cur - 1, cur + 1].filter(p => p >= 1 && p <= tp))
  const sorted = [...pages].sort((a, b) => a - b)
  const result = []
  for (let i = 0; i < sorted.length; i++) {
    if (i > 0 && sorted[i] - sorted[i - 1] > 1) result.push('…')
    result.push(sorted[i])
  }
  return result
})

function goPage(p) {
  page.value = Math.max(1, Math.min(p, totalPages.value))
  reload()
}

// Ao mudar filtros de UI recarrega do início
watch([relFilter, scopeFilter, search], () => reload(true))

// ─── Helpers ──────────────────────────────────────────────────────────────────
function fmtTime(iso) {
  if (!iso) return '—'
  try {
    const ts = new Date(iso).getTime()
    const d  = new Date(ts + BRT_OFF)
    return `${String(d.getUTCHours()).padStart(2,'0')}:${String(d.getUTCMinutes()).padStart(2,'0')}`
  } catch { return '—' }
}

function hasTags(ev) {
  return (ev.linked_contracts?.length || ev.linked_buckets?.length || ev.themes?.length)
}

function scoreClass(s) {
  const v = +s
  if (v >= 7)  return 'score-high'
  if (v >= 4)  return 'score-mid'
  return 'score-low'
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────
onMounted(() => {
  reload()
  // Auto-refresh: se estiver na página 1 recarrega normalmente,
  // nas demais apenas atualiza o total sem mudar de página
  refreshTimer = setInterval(() => reload(), 30_000)
})
onUnmounted(() => { if (refreshTimer) clearInterval(refreshTimer) })
</script>

<style scoped>
/* ─── Root ─────────────────────────────────────────────────────────────────── */
.hnw-root {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #060c18;
  color: #e2e8f0;
  font-family: "JetBrains Mono", monospace;
  overflow: hidden;
}

/* ─── Header ──────────────────────────────────────────────────────────────── */
.hnw-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border-bottom: 1px solid rgba(148,163,184,0.10);
  flex-shrink: 0;
  flex-wrap: wrap;
  overflow: hidden;
}
.hnw-title {
  font-size: 11px;
  font-weight: 700;
  color: #94a3b8;
  letter-spacing: .05em;
  flex-shrink: 0;
}
.hnw-spacer { flex: 1; min-width: 8px; }
.hnw-count  { font-size: 9px; color: #475569; flex-shrink: 0; }
.hnw-loading { font-size: 10px; color: #64748b; }
.hnw-btn {
  background: rgba(148,163,184,0.08);
  border: 1px solid rgba(148,163,184,0.14);
  border-radius: 4px;
  color: #94a3b8;
  cursor: pointer;
  font-size: 11px;
  padding: 1px 7px;
  font-family: inherit;
  flex-shrink: 0;
}
.hnw-btn:hover { background: rgba(148,163,184,0.16); }

/* Pills */
.hnw-pills { display: flex; gap: 3px; flex-shrink: 0; }
.hnw-pill {
  padding: 1px 7px;
  border-radius: 3px;
  font-size: 9px;
  font-family: inherit;
  cursor: pointer;
  border: 1px solid rgba(148,163,184,0.14);
  background: rgba(148,163,184,0.05);
  color: #64748b;
  transition: all 0.1s;
}
.hnw-pill.sm { padding: 1px 5px; font-size: 9px; }
.hnw-pill.active               { color: #e2e8f0; background: rgba(148,163,184,0.15); border-color: rgba(148,163,184,0.30); }
.hnw-pill.rel-breaking.active  { color: #fca5a5; background: rgba(239,68,68,0.15);   border-color: rgba(239,68,68,0.40); }
.hnw-pill.rel-important.active { color: #fdba74; background: rgba(249,115,22,0.15);  border-color: rgba(249,115,22,0.40); }
.hnw-pill.rel-relevant.active  { color: #fde68a; background: rgba(234,179,8,0.15);   border-color: rgba(234,179,8,0.40); }

/* Search */
.hnw-search-wrap {
  display: flex;
  align-items: center;
  gap: 4px;
  background: rgba(148,163,184,0.07);
  border: 1px solid rgba(148,163,184,0.14);
  border-radius: 4px;
  padding: 1px 6px;
  flex-shrink: 0;
}
.hnw-search-icon { font-size: 11px; color: #475569; }
.hnw-search {
  background: none;
  border: none;
  outline: none;
  color: #cbd5e1;
  font-size: 10px;
  font-family: inherit;
  width: 90px;
}
.hnw-search::placeholder { color: #475569; }
.hnw-search-clear { background: none; border: none; color: #475569; cursor: pointer; font-size: 9px; padding: 0; }

/* ─── Feed list ───────────────────────────────────────────────────────────── */
.hnw-list {
  flex: 1;
  min-height: 0;        /* ← crítico: permite que o flexbox respeite a altura do pai */
  overflow-y: auto;
  overflow-x: hidden;
  padding: 6px 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.hnw-list::-webkit-scrollbar       { width: 6px; }
.hnw-list::-webkit-scrollbar-track { background: rgba(148,163,184,0.06); border-radius: 3px; }
.hnw-list::-webkit-scrollbar-thumb { background: rgba(148,163,184,0.35); border-radius: 3px; }
.hnw-list::-webkit-scrollbar-thumb:hover { background: rgba(148,163,184,0.55); }

.hnw-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #475569;
  font-size: 11px;
}

/* ─── Headline item ───────────────────────────────────────────────────────── */
.hnw-item {
  display: flex;
  flex-shrink: 0;          /* ← não deixa o flexbox comprimir o item */
  margin: 0 8px;
  border-radius: 5px;
  overflow: hidden;
  background: rgba(148,163,184,0.04);
  border: 1px solid rgba(148,163,184,0.07);
  transition: background 0.12s;
}
.hnw-item:hover { background: rgba(148,163,184,0.08); }

/* Accent bar */
.hnw-bar { width: 3px; flex-shrink: 0; }
.bar-breaking  { background: #ef4444; }
.bar-important { background: #f97316; }
.bar-relevant  { background: #eab308; }

/* Card body */
.hnw-body {
  flex: 1;
  padding: 6px 8px 5px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

/* Meta row */
.hnw-meta {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
}
.hnw-time {
  font-size: 9px;
  color: #475569;
  font-weight: 600;
  letter-spacing: .04em;
  flex-shrink: 0;
}

/* Relevance badges */
.hnw-badge {
  font-size: 8px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 2px;
  letter-spacing: .06em;
  flex-shrink: 0;
}
.badge-breaking  { background: rgba(239,68,68,0.18);  color: #fca5a5; border: 1px solid rgba(239,68,68,0.30); }
.badge-important { background: rgba(249,115,22,0.18); color: #fdba74; border: 1px solid rgba(249,115,22,0.30); }
.badge-relevant  { background: rgba(234,179,8,0.15);  color: #fde68a; border: 1px solid rgba(234,179,8,0.30); }

/* Signal strength badges */
.hnw-badge.sig { border: none; }
.sig-high          { background: rgba(34,197,94,0.14);  color: #86efac; }
.sig-medium        { background: rgba(148,163,184,0.10); color: #94a3b8; }
.sig-low           { background: rgba(100,116,139,0.10); color: #64748b; }
.sig-idiosyncratic { background: rgba(139,92,246,0.14); color: #c4b5fd; }

/* Scenario label */
.hnw-scenario {
  font-size: 8px;
  color: #475569;
  padding: 1px 4px;
  background: rgba(148,163,184,0.06);
  border-radius: 2px;
  flex-shrink: 0;
}

/* Transmission score */
.hnw-score {
  font-size: 8px;
  font-weight: 700;
  flex-shrink: 0;
}
.score-high { color: #f87171; }
.score-mid  { color: #fb923c; }
.score-low  { color: #64748b; }

/* Headline text */
.hnw-text {
  font-size: 11px;
  color: #e2e8f0;
  line-height: 1.45;
  word-break: break-word;
}

/* Tags row */
.hnw-tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}
.hnw-tag {
  font-size: 8px;
  padding: 1px 5px;
  border-radius: 2px;
  white-space: nowrap;
}
.hnw-tag.contract { background: rgba(59,130,246,0.15); color: #93c5fd; border: 1px solid rgba(59,130,246,0.22); font-weight: 700; }
.hnw-tag.bucket   { background: rgba(16,185,129,0.12); color: #6ee7b7; border: 1px solid rgba(16,185,129,0.20); }
.hnw-tag.theme    { background: rgba(139,92,246,0.12); color: #c4b5fd; border: 1px solid rgba(139,92,246,0.20); }

.hnw-source {
  font-size: 8px;
  color: #334155;
  margin-left: auto;
  white-space: nowrap;
  flex-shrink: 0;
}
.hnw-source-only {
  font-size: 8px;
  color: #334155;
  text-align: right;
}

/* ─── Paginação ───────────────────────────────────────────────────────────── */
.hnw-pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
  padding: 5px 10px;
  border-top: 1px solid rgba(148,163,184,0.10);
  flex-shrink: 0;
  flex-wrap: wrap;
}
.hnw-pg-btn {
  min-width: 24px;
  height: 22px;
  padding: 0 5px;
  background: rgba(148,163,184,0.06);
  border: 1px solid rgba(148,163,184,0.13);
  border-radius: 3px;
  color: #64748b;
  font-size: 10px;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.1s;
}
.hnw-pg-btn:hover:not(:disabled) {
  background: rgba(148,163,184,0.14);
  color: #94a3b8;
}
.hnw-pg-btn:disabled { opacity: 0.28; cursor: default; }
.hnw-pg-btn.num.active {
  background: rgba(148,163,184,0.20);
  border-color: rgba(148,163,184,0.35);
  color: #e2e8f0;
  font-weight: 700;
}
.hnw-pg-ellipsis { color: #475569; font-size: 10px; padding: 0 2px; }

/* Contador */
.hnw-pg-info {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 9px;
  margin-left: 8px;
  white-space: nowrap;
}
.hnw-pg-range { color: #64748b; }
.hnw-pg-sep   { color: #334155; }
.hnw-pg-total { color: #94a3b8; font-weight: 600; }
.hnw-pg-pages { color: #475569; }
.hnw-pg-warn  { color: #f59e0b; font-size: 9px; margin-left: 4px; }
</style>

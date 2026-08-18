<template>
  <div class="exp-widget">
    <div v-if="!totals" class="exp-loading">Aguardando modelo…</div>
    <template v-else>
      <div class="exp-grid">
        <div v-for="item in cards" :key="item.key" class="exp-card" :class="item.tone">
          <div class="exp-label">{{ item.label }}</div>
          <div class="exp-value">{{ item.value }}</div>
          <div class="exp-sub">{{ item.notional }}</div>
          <div class="exp-bar-wrap">
            <div class="exp-bar" :style="{ width: item.pct + '%', background: item.color }" />
          </div>
        </div>
      </div>

      <div class="exp-footer">
        <div class="exp-meta">
          <span class="exp-side" :class="dominantSide">{{ dominantSide === 'call' ? '▲ Call dominant' : '▼ Put dominant' }}</span>
          <span class="exp-contracts">{{ contracts }} contratos</span>
        </div>
        <div class="exp-ts">{{ ts }}</div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelData: { type: Object, default: null },
})

const totals = computed(() => props.modelData?.aggregates?.totals ?? null)
const dominantSide = computed(() => props.modelData?.pressure?.dominant_side ?? 'neutral')
const contracts = computed(() => totals.value?.contracts?.toLocaleString('pt-BR') ?? '—')
const ts = computed(() => {
  const t = props.modelData?.captured_at
  if (!t) return ''
  return new Date(t).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
})

function fmt(v) {
  if (v == null) return '—'
  const abs = Math.abs(v)
  if (abs >= 1e9) return (v / 1e9).toFixed(2) + 'B'
  if (abs >= 1e6) return (v / 1e6).toFixed(2) + 'M'
  if (abs >= 1e3) return (v / 1e3).toFixed(1) + 'K'
  return v.toFixed(2)
}

const cards = computed(() => {
  if (!totals.value) return []
  const t = totals.value
  const vals = [
    { key: 'dex', label: 'DEX', raw: t.dex, notional: t.dex_notional },
    { key: 'gex', label: 'GEX', raw: t.gex, notional: t.gex_notional },
    { key: 'vex', label: 'VEX', raw: t.vex, notional: t.vex_notional },
    { key: 'cex', label: 'CEX', raw: t.cex, notional: t.cex_notional },
  ]
  const maxAbs = Math.max(...vals.map(v => Math.abs(v.notional || 0)), 1)
  return vals.map(v => {
    const pos = (v.raw ?? 0) >= 0
    return {
      ...v,
      value: fmt(v.raw),
      notional: fmt(v.notional) + ' not.',
      tone: pos ? 'pos' : 'neg',
      color: pos ? '#10b981' : '#ef4444',
      pct: Math.min(100, (Math.abs(v.notional || 0) / maxAbs) * 100),
    }
  })
})
</script>

<style scoped>
.exp-widget {
  height: 100%; padding: 10px;
  display: flex; flex-direction: column; gap: 8px;
  color: #e2e8f0;
}
.exp-loading { color: #475569; font-size: 12px; padding: 20px; text-align: center; }

.exp-grid {
  display: grid; grid-template-columns: 1fr 1fr;
  gap: 8px; flex: 1;
}
.exp-card {
  background: #0a1120;
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 6px;
  padding: 8px 10px;
  display: flex; flex-direction: column; gap: 3px;
}
.exp-card.pos { border-left: 2px solid #10b981; }
.exp-card.neg { border-left: 2px solid #ef4444; }

.exp-label {
  font-size: 10px; font-weight: 700;
  letter-spacing: 0.08em; color: #64748b;
  text-transform: uppercase;
}
.exp-value {
  font-size: 18px; font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}
.exp-card.pos .exp-value { color: #10b981; }
.exp-card.neg .exp-value { color: #ef4444; }

.exp-sub { font-size: 10px; color: #475569; }
.exp-bar-wrap {
  height: 3px; background: rgba(255,255,255,0.05);
  border-radius: 2px; overflow: hidden; margin-top: 2px;
}
.exp-bar { height: 100%; border-radius: 2px; transition: width 0.4s; }

.exp-footer {
  display: flex; justify-content: space-between; align-items: center;
  padding-top: 4px; border-top: 1px solid rgba(255,255,255,0.05);
}
.exp-meta { display: flex; gap: 10px; align-items: center; }
.exp-side {
  font-size: 11px; font-weight: 600;
  padding: 2px 7px; border-radius: 10px;
}
.exp-side.call { color: #10b981; background: rgba(16,185,129,0.1); }
.exp-side.put  { color: #f87171; background: rgba(248,113,113,0.1); }
.exp-side.neutral { color: #94a3b8; background: rgba(148,163,184,0.1); }
.exp-contracts { font-size: 10px; color: #475569; }
.exp-ts { font-size: 10px; color: #334155; }
</style>

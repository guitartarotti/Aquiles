<template>
  <div class="db-widget">
    <div v-if="!inference" class="db-empty">Sem inferência de dealer</div>
    <template v-else>

      <!-- Main bias indicator -->
      <div class="db-bias-row">
        <div class="db-bias-badge" :class="biasClass">
          {{ biasIcon }} {{ biasLabel }}
        </div>
        <div class="db-score">
          Score: <b>{{ scoreDisplay }}</b>
        </div>
      </div>

      <!-- Gauge bar -->
      <div class="db-gauge-wrap">
        <span class="db-gauge-lbl">Short Gamma</span>
        <div class="db-gauge-track">
          <div class="db-gauge-fill" :style="gaugeFillStyle" />
          <div class="db-gauge-center" />
        </div>
        <span class="db-gauge-lbl">Long Gamma</span>
      </div>

      <!-- Detail cards -->
      <div class="db-cards">
        <div class="db-card" v-for="item in details" :key="item.label">
          <div class="db-card-label">{{ item.label }}</div>
          <div class="db-card-value" :class="item.cls">{{ item.value }}</div>
        </div>
      </div>

      <!-- Data source note -->
      <div class="db-source-note">
        <span>GEX = gamma (modelo) × OI B3 {{ dataDate || '—' }}</span>
        <span class="db-source-sep">·</span>
        <span>OI é snapshot diário. Fluxo intraday → widget Movimentações</span>
      </div>

      <!-- Explanation text -->
      <div class="db-insight">
        <div class="db-insight-icon">💡</div>
        <div class="db-insight-text">{{ insightText }}</div>
      </div>

    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ modelData: { type: Object, default: null } })

const inference = computed(() => props.modelData?.dealer_inference ?? null)
const pressure  = computed(() => props.modelData?.pressure ?? null)
const totals    = computed(() => props.modelData?.aggregates?.totals ?? null)
const dataDate  = computed(() => props.modelData?.b3_oi_date ?? null)

// bias: 'long_gamma' | 'short_gamma' | 'neutral'
const bias = computed(() => inference.value?.dealer_bias ?? pressure.value?.dealer_position ?? 'neutral')

const biasLabel = computed(() => {
  if (bias.value === 'long_gamma')  return 'Long Gamma'
  if (bias.value === 'short_gamma') return 'Short Gamma'
  return 'Neutro'
})

const biasIcon = computed(() => {
  if (bias.value === 'long_gamma')  return '▲'
  if (bias.value === 'short_gamma') return '▼'
  return '◆'
})

const biasClass = computed(() => {
  if (bias.value === 'long_gamma')  return 'long'
  if (bias.value === 'short_gamma') return 'short'
  return 'neutral'
})

// Score: -1 (extreme short) to +1 (extreme long)
const score = computed(() => {
  const raw = inference.value?.score ?? pressure.value?.gex_score ?? null
  if (raw == null) return 0
  // Normalize if it's not already in -1..1
  if (Math.abs(raw) <= 1) return raw
  return Math.max(-1, Math.min(1, raw / 100))
})

const scoreDisplay = computed(() => {
  const s = score.value
  return (s >= 0 ? '+' : '') + (s * 100).toFixed(0)
})

const gaugeFillStyle = computed(() => {
  const ratio = (score.value + 1) / 2  // 0..1, 0.5 = center
  const pct = Math.max(0, Math.min(100, ratio * 100))
  const color = score.value > 0 ? '#10b981' : '#f87171'
  if (pct >= 50) return { left: '50%', width: (pct - 50) + '%', background: color }
  return { right: '50%', width: (50 - pct) + '%', background: color }
})

function fmt(v) {
  if (v == null) return '—'
  const abs = Math.abs(v)
  if (abs >= 1e9) return (v / 1e9).toFixed(1) + 'B'
  if (abs >= 1e6) return (v / 1e6).toFixed(1) + 'M'
  if (abs >= 1e3) return (v / 1e3).toFixed(1) + 'K'
  return v.toFixed(2)
}

const details = computed(() => {
  const t = totals.value ?? {}
  const p = pressure.value ?? {}
  return [
    { label: 'GEX Total',       value: fmt(t.gex),            cls: (t.gex ?? 0) >= 0 ? 'pos' : 'neg' },
    { label: 'DEX Total',       value: fmt(t.dex),            cls: (t.dex ?? 0) >= 0 ? 'pos' : 'neg' },
    { label: 'Net Pressure',    value: fmt(p.net_pressure),   cls: (p.net_pressure ?? 0) >= 0 ? 'pos' : 'neg' },
    { label: 'Dominant Side',   value: p.dominant_side ?? '—', cls: p.dominant_side === 'call' ? 'pos' : p.dominant_side === 'put' ? 'neg' : '' },
    { label: 'Call Pressure',   value: fmt(p.call_pressure),  cls: 'pos' },
    { label: 'Put Pressure',    value: fmt(p.put_pressure),   cls: 'neg' },
  ]
})

const insightText = computed(() => {
  const b = bias.value
  const s = score.value
  if (b === 'long_gamma') {
    if (s > 0.6) return 'Dealer fortemente long gamma: movimento pode ser amortecido, mercado tende a reverter em extremos.'
    return 'Dealer long gamma: pressão vendedora em altas e compradora em quedas — movimento limitado.'
  }
  if (b === 'short_gamma') {
    if (s < -0.6) return 'Dealer extremamente short gamma: movimentos podem ser amplificados — cuidado com breakouts.'
    return 'Dealer short gamma: pode amplificar tendências, seguir o movimento é estratégia mais segura.'
  }
  return 'Posição do dealer neutra: sem viés direcional claro derivado das gregas de opções.'
})
</script>

<style scoped>
.db-widget { height: 100%; display: flex; flex-direction: column; padding: 10px 12px; gap: 10px; }
.db-empty  { color: #475569; font-size: 12px; padding: 20px; text-align: center; }

/* Bias badge */
.db-bias-row { display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
.db-bias-badge {
  font-size: 14px; font-weight: 700; letter-spacing: 0.04em;
  padding: 6px 14px; border-radius: 6px;
}
.db-bias-badge.long    { background: rgba(16,185,129,0.12); color: #10b981; border: 1px solid rgba(16,185,129,0.25); }
.db-bias-badge.short   { background: rgba(248,113,113,0.12); color: #f87171; border: 1px solid rgba(248,113,113,0.25); }
.db-bias-badge.neutral { background: rgba(148,163,184,0.08); color: #94a3b8; border: 1px solid rgba(148,163,184,0.15); }

.db-score { font-size: 12px; color: #64748b; }
.db-score b { color: #e2e8f0; font-size: 16px; font-variant-numeric: tabular-nums; }

/* Gauge */
.db-gauge-wrap { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.db-gauge-lbl  { font-size: 9px; color: #475569; white-space: nowrap; }
.db-gauge-track {
  flex: 1; position: relative; height: 8px;
  background: rgba(255,255,255,0.06); border-radius: 4px; overflow: hidden;
}
.db-gauge-fill { position: absolute; top: 0; bottom: 0; border-radius: 4px; transition: all 0.4s; }
.db-gauge-center {
  position: absolute; left: 50%; top: 0; bottom: 0; width: 1px;
  background: rgba(255,255,255,0.25); transform: translateX(-50%);
}

/* Details grid */
.db-cards {
  display: grid; grid-template-columns: 1fr 1fr 1fr;
  gap: 6px;
}
.db-card {
  background: #0a1120; border: 1px solid rgba(255,255,255,0.06);
  border-radius: 5px; padding: 6px 8px;
}
.db-card-label { font-size: 9px; color: #475569; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; margin-bottom: 2px; }
.db-card-value { font-size: 13px; font-weight: 700; font-variant-numeric: tabular-nums; color: #e2e8f0; }
.db-card-value.pos { color: #10b981; }
.db-card-value.neg { color: #f87171; }

/* Source note */
.db-source-note {
  display: flex; align-items: center; gap: 4px; flex-wrap: wrap;
  font-size: 9px; color: #334155; padding: 4px 6px;
  background: rgba(255,255,255,0.02);
  border: 1px solid rgba(255,255,255,0.04);
  border-radius: 4px;
}
.db-source-sep { color: #1e293b; }

/* Insight */
.db-insight {
  display: flex; gap: 8px; align-items: flex-start;
  padding: 8px 10px; border-radius: 6px;
  background: rgba(99,102,241,0.06);
  border: 1px solid rgba(99,102,241,0.15);
  margin-top: auto;
}
.db-insight-icon { font-size: 14px; flex-shrink: 0; margin-top: 1px; }
.db-insight-text { font-size: 10px; color: #94a3b8; line-height: 1.5; }
</style>

<template>
  <div class="mc-widget">
    <div v-if="!ctx" class="mc-empty">Sem contexto de mercado</div>
    <template v-else>
      <div class="mc-grid">
        <div v-for="item in items" :key="item.label" class="mc-row">
          <div class="mc-row-label">{{ item.label }}</div>
          <div class="mc-row-value" :class="item.cls">{{ item.value }}</div>
          <div v-if="item.sub" class="mc-row-sub">{{ item.sub }}</div>
        </div>
      </div>

      <!-- Skew bar (call/put pressure ratio) -->
      <div class="mc-skew-wrap">
        <div class="mc-skew-label">
          <span>Put</span>
          <span class="mc-skew-title">Pressão Direcional</span>
          <span>Call</span>
        </div>
        <div class="mc-skew-track">
          <div class="mc-skew-bar" :style="skewBarStyle" />
          <div class="mc-skew-center" />
        </div>
        <div class="mc-skew-pct">
          <span style="color:#f87171">{{ putPct }}%</span>
          <span style="color:#10b981">{{ callPct }}%</span>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ modelData: { type: Object, default: null } })

const ctx = computed(() => props.modelData?.market_context ?? null)
const pressure = computed(() => props.modelData?.pressure ?? null)

function fmt(v, digits = 2) {
  if (v == null) return '—'
  return Number(v).toLocaleString('pt-BR', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

function fmtPct(v) {
  if (v == null) return '—'
  return (v * 100).toFixed(2) + '%'
}

const items = computed(() => {
  if (!ctx.value) return []
  const c = ctx.value
  return [
    { label: 'Spot',         value: fmt(c.spot_price, 0),      cls: 'highlight', sub: null },
    { label: 'Forward',      value: fmt(c.forward_price, 0),   cls: '',          sub: null },
    { label: 'Taxa Livre',   value: fmtPct(c.risk_free_rate),  cls: '',          sub: null },
    { label: 'Dividend Yld', value: fmtPct(c.dividend_yield),  cls: '',          sub: null },
    { label: 'Basis',        value: fmtPct(c.basis),           cls: basisCls(c.basis), sub: null },
    { label: 'Days to Exp',  value: c.days_to_expiry != null ? c.days_to_expiry + ' du' : '—', cls: '', sub: null },
    { label: 'IV Implícita', value: fmtPct(c.implied_vol),     cls: 'iv',        sub: null },
    { label: 'IV Rank',      value: c.iv_rank != null ? c.iv_rank.toFixed(0) + ' %ile' : '—', cls: ivRankCls(c.iv_rank), sub: null },
  ]
})

function basisCls(v) {
  if (v == null) return ''
  return v > 0.001 ? 'pos' : v < -0.001 ? 'neg' : ''
}

function ivRankCls(v) {
  if (v == null) return ''
  return v > 70 ? 'iv-high' : v < 30 ? 'iv-low' : 'iv-mid'
}

const callPressure = computed(() => pressure.value?.call_pressure ?? 0)
const putPressure  = computed(() => pressure.value?.put_pressure ?? 0)
const totalP = computed(() => Math.abs(callPressure.value) + Math.abs(putPressure.value) || 1)
const callPct = computed(() => ((Math.abs(callPressure.value) / totalP.value) * 100).toFixed(0))
const putPct  = computed(() => ((Math.abs(putPressure.value)  / totalP.value) * 100).toFixed(0))

const skewBarStyle = computed(() => {
  const ratio = Math.abs(callPressure.value) / totalP.value  // 0..1
  // bar goes from center; >50% shifts right (call dominant), <50% shifts left (put dominant)
  const offset = (ratio - 0.5) * 100  // -50..+50
  const width = Math.abs(offset)
  if (offset >= 0) return { left: '50%', width: width + '%', background: '#10b981' }
  return { right: '50%', width: width + '%', background: '#f87171' }
})
</script>

<style scoped>
.mc-widget { height: 100%; display: flex; flex-direction: column; padding: 10px 12px; gap: 10px; }
.mc-empty  { color: #475569; font-size: 12px; padding: 20px; text-align: center; }

.mc-grid { display: flex; flex-direction: column; gap: 4px; }

.mc-row {
  display: grid; grid-template-columns: 110px 1fr auto;
  align-items: center; gap: 6px;
  padding: 3px 0;
  border-bottom: 1px solid rgba(255,255,255,0.04);
}
.mc-row:last-child { border-bottom: none; }

.mc-row-label { font-size: 10px; color: #64748b; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
.mc-row-value { font-size: 13px; font-weight: 700; color: #e2e8f0; font-variant-numeric: tabular-nums; }
.mc-row-value.highlight { color: #a5b4fc; font-size: 15px; }
.mc-row-value.pos { color: #10b981; }
.mc-row-value.neg { color: #f87171; }
.mc-row-value.iv  { color: #f59e0b; }
.mc-row-value.iv-high { color: #ef4444; }
.mc-row-value.iv-low  { color: #10b981; }
.mc-row-value.iv-mid  { color: #f59e0b; }
.mc-row-sub { font-size: 9px; color: #475569; }

/* Skew bar */
.mc-skew-wrap {
  display: flex; flex-direction: column; gap: 4px;
  padding: 6px 0 0;
  border-top: 1px solid rgba(255,255,255,0.05);
}
.mc-skew-label { display: flex; justify-content: space-between; align-items: center; font-size: 10px; color: #475569; }
.mc-skew-title { font-weight: 600; color: #64748b; letter-spacing: 0.05em; }
.mc-skew-track {
  position: relative; height: 6px; border-radius: 3px;
  background: rgba(255,255,255,0.06);
  overflow: hidden;
}
.mc-skew-bar { position: absolute; top: 0; bottom: 0; border-radius: 3px; transition: all 0.4s; }
.mc-skew-center {
  position: absolute; left: 50%; top: 0; bottom: 0;
  width: 1px; background: rgba(255,255,255,0.2);
  transform: translateX(-50%);
}
.mc-skew-pct { display: flex; justify-content: space-between; font-size: 10px; font-weight: 700; }
</style>

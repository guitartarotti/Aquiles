<template>
  <div class="participant-panel">
    <div class="panel-head">
      <div>
        <div class="panel-title">Participant Intraday</div>
        <div class="panel-subtitle">Candles do dia para WIN, WDO e DI com hover, eixos e pan horizontal. Abaixo, a trilha das movimentacoes dos players usando a mesma base que ja vinha sendo capturada.</div>
      </div>
      <div class="head-actions">
        <span v-if="panelData?.sample_interval_seconds" class="badge">{{ panelData.sample_interval_seconds }}s</span>
        <button class="action-btn" :disabled="loading" @click="$emit('refresh')">{{ loading ? 'Atualizando...' : 'Atualizar painel' }}</button>
      </div>
    </div>

    <div v-if="error" class="state error">{{ error }}</div>
    <div v-else-if="loading && !hasAssets" class="state">Montando a trilha intraday de WIN, WDO e DI.</div>
    <div v-else-if="!hasAssets" class="state">Ainda nao ha amostras suficientes para construir os graficos intraday.</div>

    <div v-else class="asset-list">
      <section v-for="asset in assetViews" :key="asset.key" class="asset-card">
        <div class="asset-head">
          <div>
            <div class="asset-title">{{ asset.label }} <span class="ticker">{{ asset.ticker }}</span></div>
            <div class="asset-meta">
              <span>ultimo {{ formatPrice(asset.latest_price) }}</span>
              <span>{{ asset.price_source || 'snapshot' }}</span>
              <span>{{ formatTime(asset.generated_at) }}</span>
            </div>
          </div>
          <div class="asset-meta right">
            <span class="badge muted">{{ asset.chart.candles.length }} candles</span>
            <span class="badge muted">{{ asset.latest_participants.length }} players</span>
            <span class="badge muted">{{ asset.heat_points.length }} movimentos</span>
          </div>
        </div>

        <div class="toolbar">
          <div class="toolbar-group">
            <button
              v-for="range in RANGE_OPTIONS"
              :key="`${asset.key}-${range.key}`"
              class="chip"
              :class="{ active: getRangeKey(asset.key) === range.key }"
              @click="setRange(asset.key, range.key, asset)"
            >
              {{ range.label }}
            </button>
          </div>
          <div class="toolbar-group">
            <button class="chip" @click="shiftWindow(asset.key, -1, asset)">←</button>
            <button class="chip" @click="resetWindow(asset.key, asset)">hoje</button>
            <button class="chip" @click="shiftWindow(asset.key, 1, asset)">→</button>
          </div>
        </div>

        <div class="chart-card">
          <div v-if="!asset.chart.candles.length" class="chart-empty">Ainda nao ha candles suficientes para este ativo.</div>
          <svg
            v-else
            :viewBox="`0 0 ${asset.chart.width} ${asset.chart.height}`"
            class="chart"
            @mousedown="startDrag(asset.key, $event, asset)"
            @mousemove="handlePointerMove(asset.key, $event, asset)"
            @mouseleave="handlePointerLeave(asset.key)"
            @mouseup="stopDrag(asset.key)"
          >
            <rect
              :x="asset.chart.plotLeft"
              :y="asset.chart.plotTop"
              :width="asset.chart.plotRight - asset.chart.plotLeft"
              :height="asset.chart.plotBottom - asset.chart.plotTop"
              class="plot-bg"
              rx="12"
            />

            <g v-for="tick in asset.chart.yTicks" :key="`${asset.key}-y-${tick.value}`">
              <line :x1="asset.chart.plotLeft" :x2="asset.chart.plotRight" :y1="tick.y" :y2="tick.y" class="grid" />
              <text :x="asset.chart.plotLeft - 10" :y="tick.y + 4" class="axis-label" text-anchor="end">{{ tick.label }}</text>
            </g>

            <g v-for="tick in asset.chart.xTicks" :key="`${asset.key}-x-${tick.label}-${tick.x}`">
              <line :x1="tick.x" :x2="tick.x" :y1="asset.chart.plotTop" :y2="asset.chart.plotBottom" class="grid vertical" />
              <text :x="tick.x" :y="asset.chart.plotBottom + 18" class="axis-label time" text-anchor="middle">{{ tick.label }}</text>
            </g>

            <text :x="asset.chart.plotLeft - 26" :y="asset.chart.plotTop - 6" class="axis-title">preco</text>
            <text :x="asset.chart.plotRight" :y="asset.chart.plotBottom + 32" class="axis-title" text-anchor="end">tempo</text>

            <line
              v-if="Number.isFinite(asset.chart.latestPriceY)"
              :x1="asset.chart.plotLeft"
              :x2="asset.chart.plotRight"
              :y1="asset.chart.latestPriceY"
              :y2="asset.chart.latestPriceY"
              class="last-line"
            />

            <g v-for="candle in asset.chart.candles" :key="`${asset.key}-${candle.time}`">
              <line :x1="candle.x" :x2="candle.x" :y1="candle.highY" :y2="candle.lowY" class="wick" :class="candle.direction" />
              <rect
                :x="candle.x - candle.width / 2"
                :y="Math.min(candle.openY, candle.closeY)"
                :width="candle.width"
                :height="Math.max(Math.abs(candle.closeY - candle.openY), 2)"
                class="body"
                :class="candle.direction"
                rx="2"
              />
            </g>

            <g v-if="getHover(asset.key)">
              <line :x1="getHover(asset.key).x" :x2="getHover(asset.key).x" :y1="asset.chart.plotTop" :y2="asset.chart.plotBottom" class="crosshair" />
              <line :x1="asset.chart.plotLeft" :x2="asset.chart.plotRight" :y1="getHover(asset.key).y" :y2="getHover(asset.key).y" class="crosshair" />

              <rect :x="asset.chart.plotLeft - 54" :y="getHover(asset.key).y - 10" width="48" height="18" rx="6" class="axis-tag-bg" />
              <text :x="asset.chart.plotLeft - 30" :y="getHover(asset.key).y + 3" class="axis-tag" text-anchor="middle">{{ getHover(asset.key).priceLabel }}</text>

              <rect :x="clampTagX(getHover(asset.key).x, asset.chart)" :y="asset.chart.plotBottom + 8" width="58" height="18" rx="6" class="axis-tag-bg" />
              <text :x="clampTagX(getHover(asset.key).x, asset.chart) + 29" :y="asset.chart.plotBottom + 21" class="axis-tag" text-anchor="middle">{{ getHover(asset.key).timeLabel }}</text>
            </g>
          </svg>
        </div>

        <div v-if="getHover(asset.key)" class="hover-card">
          <div class="hover-card-head">
            <span>{{ asset.label }}</span>
            <span>{{ getHover(asset.key).timeFullLabel }}</span>
          </div>
          <div class="hover-row">
            <span class="hover-label">candle</span>
            <span class="hover-value">
              O {{ formatPrice(getHover(asset.key).candle?.open) }}
              H {{ formatPrice(getHover(asset.key).candle?.high) }}
              L {{ formatPrice(getHover(asset.key).candle?.low) }}
              C {{ formatPrice(getHover(asset.key).candle?.close) }}
            </span>
          </div>
          <div class="hover-row">
            <span class="hover-label">cursor</span>
            <span class="hover-value">{{ getHover(asset.key).priceLabel }}</span>
          </div>
        </div>

        <div class="players-grid">
          <div class="table-card">
            <div class="table-title">Players agora</div>
            <div class="table-wrap">
              <table class="mini-table">
                <thead>
                  <tr>
                    <th>Player</th>
                    <th>Saldo</th>
                    <th>Px medio</th>
                    <th>Rel%</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in asset.latest_participants.slice(0, 10)" :key="`${asset.key}-latest-${row.broker_id}`">
                    <td>{{ row.broker_name || `Broker ${row.broker_id || '--'}` }}</td>
                    <td :class="balanceClass(row.quantity_float)">{{ formatCompactNumber(row.quantity_float) }}</td>
                    <td>{{ formatPrice(row.average_price_float) }}</td>
                    <td>{{ formatSigned(row.relative_percentage_float, 2) }}%</td>
                  </tr>
                  <tr v-if="!asset.latest_participants.length">
                    <td colspan="4" class="empty-cell">Sem snapshot de players para este ativo.</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div class="table-card">
            <div class="table-title">Movimentacoes recentes</div>
            <div class="table-wrap">
              <table class="mini-table">
                <thead>
                  <tr>
                    <th>Hora</th>
                    <th>Player</th>
                    <th>Lado</th>
                    <th>Saldo</th>
                    <th>Px medio</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="move in asset.recentMoves" :key="move.point_id">
                    <td>{{ formatTime(move.captured_at) }}</td>
                    <td>{{ move.broker_name || `Broker ${move.broker_id || '--'}` }}</td>
                    <td :class="sideClass(move.side)">{{ sideLabel(move.side) }}</td>
                    <td :class="balanceClass(move.quantity_float)">{{ formatCompactNumber(move.quantity_float) }}</td>
                    <td>{{ formatPrice(move.average_price_float) }}</td>
                  </tr>
                  <tr v-if="!asset.recentMoves.length">
                    <td colspan="5" class="empty-cell">Sem trilha recente de movimentacoes.</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </section>
    </div>

    <div v-if="panelData?.notes?.length" class="panel-foot">
      <p v-for="note in panelData.notes" :key="note">{{ note }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  panelData: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
})

defineEmits(['refresh'])

const CHART_WIDTH = 920
const CHART_HEIGHT = 320
const PLOT_LEFT = 68
const PLOT_RIGHT = CHART_WIDTH - 24
const PLOT_TOP = 20
const PLOT_BOTTOM = CHART_HEIGHT - 48

const RANGE_OPTIONS = [
  { key: '15m', label: '15m', minutes: 15 },
  { key: '30m', label: '30m', minutes: 30 },
  { key: '60m', label: '60m', minutes: 60 },
  { key: 'all', label: 'dia', minutes: null },
]

const viewportState = ref({})
const hoverState = ref({})
const dragState = ref({})

const normalizedAssets = computed(() => {
  const assets = props.panelData?.assets
  if (Array.isArray(assets)) return assets
  if (assets && typeof assets === 'object') return Object.values(assets)
  return []
})

const hasAssets = computed(() => normalizedAssets.value.length > 0)

function toNumber(value) {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

function clamp(value, minValue, maxValue) {
  return Math.max(minValue, Math.min(maxValue, value))
}

function parseTs(value) {
  const dt = new Date(value)
  return Number.isNaN(dt.getTime()) ? NaN : dt.getTime()
}

function formatTime(value) {
  const dt = new Date(value)
  return Number.isNaN(dt.getTime())
    ? '--:--'
    : dt.toLocaleTimeString('pt-BR', {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
}

function formatAxisTime(value) {
  const dt = new Date(value)
  return Number.isNaN(dt.getTime())
    ? '--:--'
    : dt.toLocaleTimeString('pt-BR', {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
      })
}

function formatPrice(value) {
  const numeric = toNumber(value)
  if (!Number.isFinite(numeric)) return '--'
  const fractionDigits = Math.abs(numeric) >= 1000 ? 0 : 3
  return numeric.toLocaleString('pt-BR', {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  })
}

function formatCompactNumber(value) {
  const numeric = toNumber(value)
  if (!Number.isFinite(numeric)) return '--'
  return new Intl.NumberFormat('pt-BR', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(numeric)
}

function formatSigned(value, digits = 2) {
  const numeric = toNumber(value)
  if (!Number.isFinite(numeric)) return '--'
  return `${numeric > 0 ? '+' : ''}${numeric.toFixed(digits)}`
}

function balanceClass(value) {
  const numeric = toNumber(value)
  if (!Number.isFinite(numeric) || numeric === 0) return 'neutral'
  return numeric > 0 ? 'buy' : 'sell'
}

function sideClass(side) {
  if (side === 'buy') return 'buy'
  if (side === 'sell') return 'sell'
  return 'neutral'
}

function sideLabel(side) {
  if (side === 'buy') return 'compra'
  if (side === 'sell') return 'venda'
  return 'flat'
}

function getRangeKey(assetKey) {
  return viewportState.value[assetKey]?.rangeKey || 'all'
}

function getRangeOption(rangeKey) {
  return RANGE_OPTIONS.find((item) => item.key === rangeKey) || RANGE_OPTIONS[RANGE_OPTIONS.length - 1]
}

function getHover(assetKey) {
  return hoverState.value[assetKey] || null
}

function clampTagX(x, chart) {
  return clamp(x - 29, chart.plotLeft, chart.plotRight - 58)
}

function ensureViewport(assetKey, asset) {
  const candles = Array.isArray(asset?.candles_1m) ? asset.candles_1m : []
  const timestamps = candles.map((candle) => parseTs(candle.time)).filter(Number.isFinite).sort((a, b) => a - b)
  const maxTs = timestamps.length ? timestamps[timestamps.length - 1] : Date.now()
  const state = viewportState.value[assetKey]
  if (!state) {
    viewportState.value = {
      ...viewportState.value,
      [assetKey]: {
        rangeKey: 'all',
        endTs: maxTs,
      },
    }
    return
  }

  const nextState = { ...state }
  if (!Number.isFinite(nextState.endTs)) {
    nextState.endTs = maxTs
  }
  if (nextState.endTs > maxTs) {
    nextState.endTs = maxTs
  }
  viewportState.value = {
    ...viewportState.value,
    [assetKey]: nextState,
  }
}

watch(
  () => props.panelData?.assets,
  (assets) => {
    const list = Array.isArray(assets) ? assets : (assets && typeof assets === 'object' ? Object.values(assets) : [])
    if (!list.length) return
    for (const asset of list) {
      ensureViewport(asset.key, asset)
    }
  },
  { immediate: true },
)

function setRange(assetKey, rangeKey, asset) {
  ensureViewport(assetKey, asset)
  const candles = Array.isArray(asset?.candles_1m) ? asset.candles_1m : []
  const timestamps = candles.map((candle) => parseTs(candle.time)).filter(Number.isFinite).sort((a, b) => a - b)
  const maxTs = timestamps.length ? timestamps[timestamps.length - 1] : Date.now()
  viewportState.value = {
    ...viewportState.value,
    [assetKey]: {
      rangeKey,
      endTs: maxTs,
    },
  }
}

function shiftWindow(assetKey, direction, asset) {
  ensureViewport(assetKey, asset)
  const rangeKey = getRangeKey(assetKey)
  const range = getRangeOption(rangeKey)
  if (range.minutes == null) return

  const candles = Array.isArray(asset?.candles_1m) ? asset.candles_1m : []
  const timestamps = candles.map((candle) => parseTs(candle.time)).filter(Number.isFinite).sort((a, b) => a - b)
  if (!timestamps.length) return

  const minTs = timestamps[0]
  const maxTs = timestamps[timestamps.length - 1]
  const spanMs = range.minutes * 60 * 1000
  const stepMs = Math.max(60 * 1000, Math.round(spanMs * 0.35))
  const currentEnd = viewportState.value[assetKey]?.endTs || maxTs
  const nextEnd = clamp(currentEnd + direction * stepMs, minTs + spanMs, maxTs)

  viewportState.value = {
    ...viewportState.value,
    [assetKey]: {
      rangeKey,
      endTs: nextEnd,
    },
  }
}

function resetWindow(assetKey, asset) {
  setRange(assetKey, 'all', asset)
}

function stopDrag(assetKey) {
  if (!dragState.value[assetKey]) return
  const next = { ...dragState.value }
  delete next[assetKey]
  dragState.value = next
}

function handlePointerLeave(assetKey) {
  stopDrag(assetKey)
  hoverState.value = {
    ...hoverState.value,
    [assetKey]: null,
  }
}

function startDrag(assetKey, event, asset) {
  ensureViewport(assetKey, asset)
  const range = getRangeOption(getRangeKey(assetKey))
  if (range.minutes == null) return

  const candles = Array.isArray(asset?.candles_1m) ? asset.candles_1m : []
  const timestamps = candles.map((candle) => parseTs(candle.time)).filter(Number.isFinite).sort((a, b) => a - b)
  if (!timestamps.length) return

  const spanMs = range.minutes * 60 * 1000
  dragState.value = {
    ...dragState.value,
    [assetKey]: {
      startClientX: event.clientX,
      startEndTs: viewportState.value[assetKey]?.endTs || timestamps[timestamps.length - 1],
      minTs: timestamps[0],
      maxTs: timestamps[timestamps.length - 1],
      spanMs,
      plotWidth: PLOT_RIGHT - PLOT_LEFT,
    },
  }
}

const assetViews = computed(() => {
  const assets = normalizedAssets.value
  return assets.map((asset) => {
    const candles = (asset.candles_1m || [])
      .map((candle) => ({
        time: candle.time,
        ts: parseTs(candle.time),
        open: toNumber(candle.open),
        high: toNumber(candle.high),
        low: toNumber(candle.low),
        close: toNumber(candle.close),
        volume: toNumber(candle.volume),
      }))
      .filter((candle) => Number.isFinite(candle.ts))
      .sort((a, b) => a.ts - b.ts)

    const heatPoints = (asset.heat_points || [])
      .map((point) => ({
        ...point,
        ts: parseTs(point.captured_at),
        quantity_float: toNumber(point.quantity_float),
        average_price_float: toNumber(point.average_price_float),
        relative_percentage_float: toNumber(point.relative_percentage_float),
      }))
      .filter((point) => Number.isFinite(point.ts))
      .sort((a, b) => b.ts - a.ts)

    const timestamps = candles.map((candle) => candle.ts)
    const minTs = timestamps.length ? timestamps[0] : Date.now()
    const maxTs = timestamps.length ? timestamps[timestamps.length - 1] : Date.now()
    const totalSpan = Math.max(maxTs - minTs, 60 * 1000)

    const state = viewportState.value[asset.key] || { rangeKey: 'all', endTs: maxTs }
    const range = getRangeOption(state.rangeKey)
    const requestedSpan = range.minutes == null ? totalSpan : Math.max(range.minutes * 60 * 1000, 5 * 60 * 1000)

    const visibleMaxTs = range.minutes == null ? maxTs : clamp(state.endTs || maxTs, minTs + requestedSpan, maxTs)
    const visibleMinTs = range.minutes == null ? minTs : Math.max(minTs, visibleMaxTs - requestedSpan)
    const visibleSpan = Math.max(visibleMaxTs - visibleMinTs, 60 * 1000)

    const visibleCandles = candles.filter((candle) => candle.ts >= visibleMinTs && candle.ts <= visibleMaxTs)
    const chartCandlesRaw = visibleCandles.length ? visibleCandles : candles.slice(-1)

    const prices = chartCandlesRaw
      .flatMap((candle) => [candle.open, candle.high, candle.low, candle.close])
      .concat([toNumber(asset.latest_price)])
      .filter((value) => Number.isFinite(value))

    const rawMinPrice = prices.length ? Math.min(...prices) : 0
    const rawMaxPrice = prices.length ? Math.max(...prices) : 1
    const padding = Math.max((rawMaxPrice - rawMinPrice) * 0.08, Math.abs(rawMaxPrice) * 0.0015 || 1)
    const minPrice = rawMinPrice - padding
    const maxPrice = rawMaxPrice + padding
    const priceSpan = Math.max(maxPrice - minPrice, 0.0001)
    const plotWidth = PLOT_RIGHT - PLOT_LEFT
    const plotHeight = PLOT_BOTTOM - PLOT_TOP

    const xFromTs = (ts) => {
      if (!Number.isFinite(ts)) return PLOT_LEFT + plotWidth / 2
      return PLOT_LEFT + ((ts - visibleMinTs) / visibleSpan) * plotWidth
    }

    const yFromPrice = (price) => {
      if (!Number.isFinite(price)) return PLOT_BOTTOM
      return PLOT_BOTTOM - ((price - minPrice) / priceSpan) * plotHeight
    }

    const priceFromY = (y) => {
      const ratio = clamp((PLOT_BOTTOM - y) / plotHeight, 0, 1)
      return minPrice + ratio * priceSpan
    }

    const candleWidth = clamp((plotWidth / Math.max(chartCandlesRaw.length, 18)) * 0.68, 5, 12)
    const chartCandles = chartCandlesRaw.map((candle) => ({
      ...candle,
      x: xFromTs(candle.ts),
      width: candleWidth,
      openY: yFromPrice(candle.open),
      closeY: yFromPrice(candle.close),
      highY: yFromPrice(candle.high),
      lowY: yFromPrice(candle.low),
      direction: candle.close >= candle.open ? 'up' : 'down',
    }))

    const yTicks = Array.from({ length: 5 }, (_, index) => {
      const ratio = index / 4
      const value = maxPrice - priceSpan * ratio
      return {
        value,
        y: yFromPrice(value),
        label: formatPrice(value),
      }
    })

    const xTicks = Array.from({ length: Math.min(6, Math.max(chartCandles.length, 2)) }, (_, index, arr) => {
      const ratio = arr.length === 1 ? 0.5 : index / (arr.length - 1)
      const ts = visibleMinTs + visibleSpan * ratio
      return {
        x: xFromTs(ts),
        label: formatAxisTime(new Date(ts).toISOString()),
      }
    })

    return {
      ...asset,
      heat_points: heatPoints,
      recentMoves: heatPoints.slice(0, 12),
      chart: {
        width: CHART_WIDTH,
        height: CHART_HEIGHT,
        plotLeft: PLOT_LEFT,
        plotRight: PLOT_RIGHT,
        plotTop: PLOT_TOP,
        plotBottom: PLOT_BOTTOM,
        visibleMinTs,
        visibleMaxTs,
        visibleSpan,
        minPrice,
        maxPrice,
        priceSpan,
        yTicks,
        xTicks,
        candles: chartCandles,
        latestPriceY: yFromPrice(toNumber(asset.latest_price)),
        priceFromY,
      },
    }
  })
})

function handlePointerMove(assetKey, event, asset) {
  const drag = dragState.value[assetKey]
  if (drag) {
    const deltaPixels = event.clientX - drag.startClientX
    const deltaMs = (deltaPixels / Math.max(drag.plotWidth, 1)) * drag.spanMs
    const nextEndTs = clamp(drag.startEndTs - deltaMs, drag.minTs + drag.spanMs, drag.maxTs)
    viewportState.value = {
      ...viewportState.value,
      [assetKey]: {
        ...(viewportState.value[assetKey] || {}),
        endTs: nextEndTs,
      },
    }
    return
  }

  const svg = event.currentTarget
  if (!svg || !asset?.chart?.candles?.length) return

  const rect = svg.getBoundingClientRect()
  if (!rect.width || !rect.height) return

  const x = ((event.clientX - rect.left) / rect.width) * asset.chart.width
  const y = ((event.clientY - rect.top) / rect.height) * asset.chart.height
  const boundedX = clamp(x, asset.chart.plotLeft, asset.chart.plotRight)
  const boundedY = clamp(y, asset.chart.plotTop, asset.chart.plotBottom)
  const ratio = (boundedX - asset.chart.plotLeft) / Math.max(asset.chart.plotRight - asset.chart.plotLeft, 1)
  const hoverTs = asset.chart.visibleMinTs + ratio * asset.chart.visibleSpan
  const candle = [...asset.chart.candles].sort((a, b) => Math.abs(a.ts - hoverTs) - Math.abs(b.ts - hoverTs))[0] || null

  hoverState.value = {
    ...hoverState.value,
    [assetKey]: {
      x: candle?.x ?? boundedX,
      y: boundedY,
      candle,
      priceLabel: formatPrice(asset.chart.priceFromY(boundedY)),
      timeLabel: formatAxisTime(new Date(candle?.ts || hoverTs).toISOString()),
      timeFullLabel: formatTime(new Date(candle?.ts || hoverTs).toISOString()),
    },
  }
}
</script>

<style scoped>
.participant-panel {
  margin-top: 18px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background:
    radial-gradient(circle at top left, rgba(65, 105, 225, 0.14), transparent 24%),
    radial-gradient(circle at top right, rgba(255, 140, 0, 0.08), transparent 28%),
    linear-gradient(180deg, #08111d, #07101a 45%, #050a12);
  padding: 18px;
  color: #f4f7fb;
}

.panel-head,
.head-actions,
.asset-head,
.toolbar,
.toolbar-group,
.asset-meta,
.hover-card-head,
.hover-row {
  display: flex;
  flex-wrap: wrap;
}

.panel-head,
.asset-head,
.toolbar,
.hover-card-head {
  justify-content: space-between;
}

.panel-head,
.asset-head,
.toolbar {
  gap: 12px;
  align-items: flex-start;
}

.panel-title,
.asset-title,
.table-title {
  font-weight: 700;
  color: #fff;
}

.panel-title {
  font-size: 16px;
}

.panel-subtitle,
.asset-meta,
.panel-foot p,
.state {
  font-size: 12px;
  line-height: 1.6;
  color: #c9d5e2;
}

.panel-head {
  margin-bottom: 14px;
}

.head-actions,
.asset-meta,
.toolbar-group {
  gap: 8px;
  align-items: center;
}

.asset-meta.right {
  justify-content: flex-end;
}

.badge,
.chip,
.action-btn {
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.05);
  color: #fff;
  border-radius: 999px;
  font-size: 11px;
}

.badge,
.chip {
  padding: 6px 10px;
}

.badge.muted {
  color: #d6dee7;
}

.action-btn {
  padding: 8px 14px;
  cursor: pointer;
}

.action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.chip {
  cursor: pointer;
}

.chip.active {
  border-color: rgba(255, 183, 77, 0.9);
  background: rgba(255, 183, 77, 0.18);
}

.state {
  margin-top: 8px;
  border-radius: 12px;
  border: 1px dashed rgba(255, 255, 255, 0.15);
  padding: 16px;
}

.state.error {
  border-color: rgba(255, 112, 67, 0.38);
  color: #ffd3c6;
}

.asset-list {
  display: grid;
  gap: 18px;
}

.asset-card {
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  padding: 14px;
}

.asset-title {
  font-size: 15px;
}

.ticker,
.axis-label,
.axis-title,
.axis-tag {
  font-family: 'JetBrains Mono', monospace;
}

.ticker {
  margin-left: 10px;
  font-size: 11px;
  color: #aeb8c4;
}

.chart-card {
  margin-top: 10px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: linear-gradient(180deg, rgba(6, 13, 22, 0.96), rgba(5, 11, 18, 0.98));
  overflow-x: auto;
}

.chart-empty {
  min-height: 250px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 18px;
  color: #cad6e2;
  text-align: center;
}

.chart {
  width: 100%;
  min-width: 880px;
  display: block;
  cursor: grab;
}

.plot-bg {
  fill: #0d1624;
}

.grid {
  stroke: rgba(255, 255, 255, 0.08);
  stroke-width: 1;
}

.grid.vertical {
  stroke-dasharray: 4 6;
}

.axis-label {
  fill: #b0bcc9;
  font-size: 10px;
}

.axis-label.time {
  fill: #dde6ef;
}

.axis-title {
  fill: #8fa3b6;
  font-size: 10px;
  text-transform: uppercase;
}

.last-line {
  stroke: rgba(255, 255, 255, 0.36);
  stroke-width: 1;
  stroke-dasharray: 5 5;
}

.wick {
  stroke-width: 1.2;
}

.wick.up {
  stroke: rgba(102, 187, 106, 0.84);
}

.wick.down {
  stroke: rgba(239, 83, 80, 0.82);
}

.body.up {
  fill: rgba(102, 187, 106, 0.9);
}

.body.down {
  fill: rgba(239, 83, 80, 0.9);
}

.crosshair {
  stroke: rgba(255, 255, 255, 0.24);
  stroke-width: 1;
  stroke-dasharray: 4 6;
}

.axis-tag-bg {
  fill: rgba(8, 15, 24, 0.95);
  stroke: rgba(255, 255, 255, 0.12);
}

.axis-tag {
  fill: #f4f7fb;
  font-size: 10px;
}

.hover-card {
  margin-top: 10px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
  padding: 10px 12px;
}

.hover-card-head {
  gap: 10px;
  margin-bottom: 8px;
  font-size: 11px;
  color: #dde6ef;
}

.hover-row {
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
}

.hover-row + .hover-row {
  margin-top: 6px;
}

.hover-label {
  color: #8fa3b8;
  text-transform: uppercase;
  font-size: 10px;
}

.hover-value {
  color: #f5f7fa;
}

.players-grid {
  margin-top: 12px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.table-card {
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  padding: 12px;
}

.table-title {
  margin-bottom: 8px;
  font-size: 13px;
}

.table-wrap {
  overflow-x: auto;
}

.mini-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}

.mini-table th,
.mini-table td {
  padding: 8px 10px;
  text-align: left;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.mini-table th {
  color: #aab6c4;
  font-weight: 600;
}

.mini-table td {
  color: #f3f6fb;
}

.mini-table td.buy {
  color: #7ddc8b;
}

.mini-table td.sell {
  color: #ff8c74;
}

.mini-table td.neutral {
  color: #d3dde8;
}

.empty-cell {
  color: #b3bfcb;
  text-align: center;
}

.panel-foot {
  margin-top: 14px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  padding-top: 12px;
}

.panel-foot p {
  margin: 0;
}

.panel-foot p + p {
  margin-top: 6px;
}

@media (max-width: 1024px) {
  .players-grid {
    grid-template-columns: 1fr;
  }

  .panel-head,
  .asset-head,
  .toolbar {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>

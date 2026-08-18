<template>
  <div class="equi-chart-card">
    <div v-if="normalizedPoints.length" ref="containerRef" class="equi-chart-stage" :style="{ height: `${height}px` }"></div>
    <div v-else class="equi-chart-empty" :style="{ height: `${height}px` }">
      {{ emptyMessage }}
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import {
  CandleTooltipRectPosition,
  CandleType,
  LineType,
  TooltipShowRule,
  TooltipShowType,
  YAxisPosition,
  YAxisType,
  dispose,
  init
} from '../vendor/equicharts/equicharts.esm.js'

const props = defineProps({
  points: {
    type: Array,
    default: () => []
  },
  chartMode: {
    type: String,
    default: 'price'
  },
  height: {
    type: Number,
    default: 320
  },
  lineColor: {
    type: String,
    default: '#8fb5ff'
  },
  fillTopColor: {
    type: String,
    default: 'rgba(143, 181, 255, 0.04)'
  },
  fillBottomColor: {
    type: String,
    default: 'rgba(143, 181, 255, 0.22)'
  },
  emptyMessage: {
    type: String,
    default: 'Sem pontos suficientes para exibir o gráfico.'
  }
})

const containerRef = ref(null)
const chartRef = shallowRef(null)
const resizeObserverRef = shallowRef(null)

const normalizedPoints = computed(() =>
  (props.points || [])
    .map((point) => {
      const baseValue = Number(point?.close ?? point?.price ?? point?.value)
      const timestamp = Number(point?.timestamp_ms ?? point?.timestamp)
      if (!Number.isFinite(baseValue) || !Number.isFinite(timestamp)) {
        return null
      }

      const open = Number(point?.open)
      const high = Number(point?.high)
      const low = Number(point?.low)

      return {
        timestamp,
        open: Number.isFinite(open) ? open : baseValue,
        high: Number.isFinite(high) ? high : baseValue,
        low: Number.isFinite(low) ? low : baseValue,
        close: baseValue,
        volume: 0,
        turnover: 0,
        dailyChangePct: point?.daily_change_pct ?? null
      }
    })
    .filter(Boolean)
)

function buildTooltipConfig() {
  if (props.chartMode === 'pearson') {
    return {
      showRule: TooltipShowRule.FollowCross,
      showType: TooltipShowType.Standard,
      defaultValue: '--',
      custom: [
        { title: 'time', value: '{time}' },
        { title: 'pearson', value: '{close}' }
      ],
      rect: {
        position: CandleTooltipRectPosition.Fixed,
        paddingLeft: 6,
        paddingRight: 6,
        paddingTop: 6,
        paddingBottom: 6,
        offsetLeft: 6,
        offsetTop: 6,
        offsetRight: 6,
        offsetBottom: 6,
        borderRadius: 8,
        borderSize: 1,
        borderColor: 'rgba(148, 163, 184, 0.24)',
        color: '#07111f'
      },
      text: {
        size: 11,
        family: '"JetBrains Mono", monospace',
        weight: 'normal',
        color: '#d7e6f5',
        marginLeft: 6,
        marginTop: 4,
        marginRight: 8,
        marginBottom: 4
      },
      icons: []
    }
  }

  return {
    showRule: TooltipShowRule.FollowCross,
    showType: TooltipShowType.Standard,
    defaultValue: '--',
    custom: [
      { title: 'time', value: '{time}' },
      { title: 'price', value: '{close}' },
      { title: '1d', value: '{dailyChangePct}' }
    ],
    rect: {
      position: CandleTooltipRectPosition.Fixed,
      paddingLeft: 6,
      paddingRight: 6,
      paddingTop: 6,
      paddingBottom: 6,
      offsetLeft: 6,
      offsetTop: 6,
      offsetRight: 6,
      offsetBottom: 6,
      borderRadius: 8,
      borderSize: 1,
      borderColor: 'rgba(148, 163, 184, 0.24)',
      color: '#07111f'
    },
    text: {
      size: 11,
      family: '"JetBrains Mono", monospace',
      weight: 'normal',
      color: '#d7e6f5',
      marginLeft: 6,
      marginTop: 4,
      marginRight: 8,
      marginBottom: 4
    },
    icons: []
  }
}

function buildStyles() {
  const isPriceChart = props.chartMode === 'price'

  return {
    grid: {
      show: true,
      horizontal: {
        show: true,
        size: 1,
        color: 'rgba(148, 163, 184, 0.12)',
        style: LineType.Dashed,
        dashedValue: [4, 6]
      },
      vertical: {
        show: true,
        size: 1,
        color: 'rgba(148, 163, 184, 0.08)',
        style: LineType.Dashed,
        dashedValue: [4, 8]
      }
    },
    candle: {
      type: isPriceChart ? CandleType.Area : CandleType.Line,
      area: {
        value: 'close',
        lineColor: props.lineColor,
        lineSize: 2,
        smooth: true,
        backgroundColor: [
          { offset: 0, color: props.fillTopColor },
          { offset: 1, color: props.fillBottomColor }
        ],
        point: {
          show: false,
          color: props.lineColor,
          radius: 0,
          rippleColor: 'transparent',
          rippleRadius: 0,
          animation: false,
          animationDuration: 0
        }
      },
      line: {
        value: 'close',
        lineColor: props.lineColor,
        lineSize: 2,
        smooth: true,
        point: {
          show: false,
          color: props.lineColor,
          radius: 0,
          rippleColor: 'transparent',
          rippleRadius: 0,
          animation: false,
          animationDuration: 0
        }
      },
      priceMark: {
        show: true,
        high: {
          show: false,
          color: props.lineColor,
          textOffset: 0,
          textSize: 0,
          textFamily: '"JetBrains Mono", monospace',
          textWeight: 'normal'
        },
        low: {
          show: false,
          color: props.lineColor,
          textOffset: 0,
          textSize: 0,
          textFamily: '"JetBrains Mono", monospace',
          textWeight: 'normal'
        },
        last: {
          show: true,
          upColor: props.lineColor,
          downColor: props.lineColor,
          noChangeColor: props.lineColor,
          line: {
            show: true,
            style: LineType.Dashed,
            dashedValue: [5, 6],
            size: 1
          },
          text: {
            show: true,
            style: 'fill',
            size: 11,
            paddingLeft: 6,
            paddingTop: 4,
            paddingRight: 6,
            paddingBottom: 4,
            borderStyle: LineType.Solid,
            borderSize: 0,
            borderColor: 'transparent',
            borderDashedValue: [2, 2],
            color: '#08111f',
            family: '"JetBrains Mono", monospace',
            weight: 'bold',
            borderRadius: 6
          }
        }
      },
      tooltip: buildTooltipConfig()
    },
    xAxis: {
      show: true,
      size: 'auto',
      axisLine: {
        show: true,
        color: 'rgba(148, 163, 184, 0.18)',
        size: 1
      },
      tictView: {
        show: true,
        size: 1,
        length: 3,
        color: 'rgba(148, 163, 184, 0.18)'
      },
      tickText: {
        show: true,
        color: '#8aa2b7',
        family: '"JetBrains Mono", monospace',
        weight: 'normal',
        size: 10,
        marginStart: 4,
        marginEnd: 4
      }
    },
    yAxis: {
      show: true,
      size: 'auto',
      position: YAxisPosition.Right,
      type: YAxisType.Normal,
      inside: false,
      reverse: false,
      axisLine: {
        show: true,
        color: 'rgba(148, 163, 184, 0.18)',
        size: 1
      },
      tictView: {
        show: true,
        size: 1,
        length: 2,
        color: 'rgba(148, 163, 184, 0.18)'
      },
      tickText: {
        show: true,
        color: '#dbe7f3',
        family: '"JetBrains Mono", monospace',
        weight: 'normal',
        size: 10,
        marginStart: 4,
        marginEnd: 4
      }
    },
    crosshair: {
      show: true,
      horizontal: {
        show: true,
        line: {
          show: true,
          style: LineType.Dashed,
          dashedValue: [4, 6],
          size: 1,
          color: 'rgba(226, 232, 240, 0.28)'
        },
        text: {
          show: true,
          style: 'fill',
          color: '#e2e8f0',
          size: 10,
          family: '"JetBrains Mono", monospace',
          weight: 'normal',
          borderStyle: LineType.Solid,
          borderDashedValue: [2, 2],
          borderSize: 1,
          borderColor: 'rgba(148, 163, 184, 0.32)',
          borderRadius: 6,
          paddingLeft: 6,
          paddingRight: 6,
          paddingTop: 4,
          paddingBottom: 4,
          backgroundColor: '#08111f'
        }
      },
      vertical: {
        show: true,
        line: {
          show: true,
          style: LineType.Dashed,
          dashedValue: [4, 6],
          size: 1,
          color: 'rgba(226, 232, 240, 0.24)'
        },
        text: {
          show: true,
          style: 'fill',
          color: '#e2e8f0',
          size: 10,
          family: '"JetBrains Mono", monospace',
          weight: 'normal',
          borderStyle: LineType.Solid,
          borderDashedValue: [2, 2],
          borderSize: 1,
          borderColor: 'rgba(148, 163, 184, 0.32)',
          borderRadius: 6,
          paddingLeft: 6,
          paddingRight: 6,
          paddingTop: 4,
          paddingBottom: 4,
          backgroundColor: '#08111f'
        }
      }
    }
  }
}

function destroyChart() {
  try {
    if (containerRef.value) {
      dispose(containerRef.value)
    }
  } catch (error) {
    console.warn('Failed to dispose EquiCharts instance', error)
  }
  chartRef.value = null
}

async function mountChart() {
  destroyChart()
  if (!containerRef.value || !normalizedPoints.value.length) {
    return
  }

  await nextTick()
  const chart = init(containerRef.value, {
    styles: buildStyles(),
    timezone: 'America/Sao_Paulo',
    yScrolling: false,
    layout: [
      { type: 'candle' },
      { type: 'xAxis', options: { position: 'bottom' } }
    ]
  })

  if (!chart) {
    return
  }

  chart.applyNewData(normalizedPoints.value, true)
  chart.resize()
  chartRef.value = chart
}

function refreshChart() {
  if (!chartRef.value) {
    void mountChart()
    return
  }

  if (!normalizedPoints.value.length) {
    destroyChart()
    return
  }

  chartRef.value.clearData()
  chartRef.value.applyNewData(normalizedPoints.value, true)
  chartRef.value.resize()
}

function handleResize() {
  chartRef.value?.resize()
}

onMounted(async () => {
  await mountChart()
  if (typeof ResizeObserver !== 'undefined' && containerRef.value) {
    resizeObserverRef.value = new ResizeObserver(() => {
      handleResize()
    })
    resizeObserverRef.value.observe(containerRef.value)
  }
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  resizeObserverRef.value?.disconnect?.()
  window.removeEventListener('resize', handleResize)
  destroyChart()
})

watch(
  () => props.chartMode,
  () => {
    void mountChart()
  }
)

watch(
  () => props.points,
  () => {
    refreshChart()
  }
)
</script>

<style scoped>
.equi-chart-card {
  width: 100%;
}

.equi-chart-stage,
.equi-chart-empty {
  width: 100%;
  border-radius: 18px;
  overflow: hidden;
  background:
    radial-gradient(circle at top right, rgba(37, 99, 235, 0.12), transparent 28%),
    linear-gradient(180deg, #09111c 0%, #050a12 100%);
  border: 1px solid rgba(148, 163, 184, 0.12);
}

.equi-chart-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  color: #93a8bc;
  font-size: 0.92rem;
  text-align: center;
}
</style>

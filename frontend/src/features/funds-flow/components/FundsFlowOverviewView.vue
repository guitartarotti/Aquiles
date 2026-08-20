<template>
      <main class="ffl-overview">
        <section class="ffl-chart-panel">
          <div class="ffl-section-head">
            <span>Fluxo acumulado por classe</span>
            <strong>{{ metricLabel }}</strong>
          </div>
          <svg class="ffl-line-chart" viewBox="0 0 760 260" preserveAspectRatio="none" aria-hidden="true">
            <line v-for="y in gridLines" :key="`g${y}`" x1="42" x2="744" :y1="y" :y2="y" class="ffl-grid" />
            <line x1="42" x2="744" y1="218" y2="218" class="ffl-axis" />
            <path
              v-for="series in chartSeries"
              :key="series.name"
              :d="linePath(series.points)"
              class="ffl-line"
              :style="{ stroke: series.color }"
            />
            <circle
              v-for="point in chartLastPoints"
              :key="`${point.name}-${point.x}`"
              :cx="point.x"
              :cy="point.y"
              r="3.2"
              class="ffl-dot"
              :style="{ fill: point.color }"
            />
          </svg>
          <div class="ffl-legend">
            <span v-for="series in chartSeries" :key="series.name">
              <i :style="{ background: series.color }"></i>{{ series.name }}
            </span>
          </div>
        </section>

        <aside class="ffl-rankings">
          <div class="ffl-rank-toolbar">
            <span>Janela</span>
            <div class="ffl-rank-switch">
              <button
                v-for="option in rankingWindowOptions"
                :key="option.value"
                type="button"
                class="ffl-rank-switch-btn"
                :class="{ active: rankingWindow === option.value }"
                @click="rankingWindow = option.value"
              >
                {{ option.label }}
              </button>
            </div>
          </div>
          <div class="ffl-rank-box">
            <div class="ffl-section-head">
              <span>Top entradas</span>
              <strong>{{ rankingWindowLabel }}</strong>
            </div>
            <div v-for="item in overviewTopInflows" :key="`in-${item.name}`" class="ffl-rank-row">
              <span>{{ item.rank }}. {{ item.name }}</span>
              <strong :class="moveClass(item.displayFlow)">{{ fmtMoney(item.displayFlow) }}</strong>
            </div>
          </div>
          <div class="ffl-rank-box">
            <div class="ffl-section-head">
              <span>Top saidas</span>
              <strong>{{ rankingWindowLabel }}</strong>
            </div>
            <div v-for="item in overviewTopOutflows" :key="`out-${item.name}`" class="ffl-rank-row">
              <span>{{ item.rank }}. {{ item.name }}</span>
              <strong :class="moveClass(item.displayFlow)">{{ fmtMoney(item.displayFlow) }}</strong>
            </div>
          </div>
        </aside>

        <section v-if="b3OiMainSummary.length || b3ParticipantBars.length" class="ffl-overview-b3">
          <div class="ffl-b3-mini-panel">
            <div class="ffl-section-head compact">
              <span>OI futuros B3</span>
              <strong>OI do dia | var d/d</strong>
            </div>
            <div class="ffl-diverging-list">
              <div v-for="item in b3OiOverviewRows" :key="`oi-${item.asset}`" class="ffl-diverging-row">
                <span>{{ item.asset }}</span>
                <div class="ffl-diverging-track">
                  <i :class="moveClass(item.variation_open_interest)" :style="divergingBarStyle(item.variation_open_interest, oiOverviewBarMax)"></i>
                </div>
                <div class="ffl-diverging-metric">
                  <strong>{{ fmtCount(item.open_interest) }}</strong>
                  <em :class="moveClass(item.variation_open_interest)">{{ signedCount(item.variation_open_interest) }} d/d</em>
                </div>
              </div>
            </div>
          </div>
          <div class="ffl-b3-mini-panel">
            <div class="ffl-section-head compact">
              <span>Participantes B3</span>
              <strong>fluxo do dia</strong>
            </div>
            <div class="ffl-diverging-list">
              <div v-for="item in b3ParticipantOverviewRows" :key="`part-${item.participant_type}`" class="ffl-diverging-row participant">
                <span>{{ item.participant_type }}</span>
                <div class="ffl-diverging-track">
                  <i :class="moveClass(item.daily_net_flow_brl)" :style="divergingBarStyle(item.daily_net_flow_brl, participantOverviewBarMax)"></i>
                </div>
                <div class="ffl-diverging-metric">
                  <strong :class="moveClass(item.daily_net_flow_brl)">{{ fmtMoney(item.daily_net_flow_brl) }}</strong>
                  <em :class="moveClass(item.net_flow_brl_mtd)">{{ fmtMoney(item.net_flow_brl_mtd) }} MTD</em>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section class="ffl-insights">
          <div class="ffl-section-head"><span>Leitura automatica</span><strong>{{ insights.agent || 'FundsFlowInsightAgent' }}</strong></div>
          <ul>
            <li v-for="item in insights.quick_read || []" :key="item">{{ item }}</li>
          </ul>
          <p>{{ insights.diagnosis }}</p>
        </section>
      </main>

</template>

<script>
import { injectFundsFlowContext } from '../context'
export default {
  name: 'FundsFlowOverviewView',
  setup: injectFundsFlowContext,
}
</script>

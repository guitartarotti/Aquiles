<template>
      <main class="ffl-map-view">
        <section class="ffl-heatmap-panel">
          <div class="ffl-section-head"><span>Mapa de fluxo</span><strong>{{ heatmap.metric || 'flow_zscore_21d' }}</strong></div>
          <div class="ffl-heatmap" :style="heatmapStyle">
            <div class="ffl-heat-corner"></div>
            <div v-for="x in heatmap.x || []" :key="`hx-${x}`" class="ffl-heat-x">{{ shortDate(x) }}</div>
            <template v-for="row in heatmapRows" :key="row.name">
              <div class="ffl-heat-y">{{ row.name }}</div>
              <div
                v-for="cell in row.cells"
                :key="`${row.name}-${cell.date}`"
                class="ffl-heat-cell"
                :style="{ background: heatColor(cell.value) }"
                :title="heatTitle(cell)"
              ></div>
            </template>
          </div>
        </section>
        <section class="ffl-table-panel">
          <div class="ffl-section-head"><span>Ranking por classe</span></div>
          <table>
            <thead>
              <tr>
                <th>Classe</th>
                <th>21d</th>
                <th>% PL</th>
                <th>Z</th>
                <th>PL</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in classRanking" :key="item.name">
                <td>{{ item.name }}</td>
                <td :class="moveClass(item.net_flow_21d)">{{ fmtMoney(item.net_flow_21d) }}</td>
                <td>{{ fmtPct(item.flow_pct_pl_21d) }}</td>
                <td>{{ fmtNum(item.zscore_21d, 2) }}</td>
                <td>{{ fmtMoney(item.aum) }}</td>
              </tr>
            </tbody>
          </table>
        </section>
      </main>

</template>

<script>
import { injectFundsFlowContext } from '../context'
export default {
  name: 'FundsFlowMapView',
  setup: injectFundsFlowContext,
}
</script>

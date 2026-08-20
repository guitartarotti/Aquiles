<template>
      <main class="ffl-stress-view">
        <section class="ffl-stress-grid">
          <div v-for="card in stressCards" :key="card.label" class="ffl-stress-card">
            <span>{{ card.label }}</span>
            <strong :class="card.tone">{{ card.value }}</strong>
          </div>
        </section>
        <section class="ffl-table-panel">
          <div class="ffl-section-head"><span>Fundos com maior fluxo absoluto 21d</span></div>
          <table>
            <thead>
              <tr>
                <th>Fundo</th>
                <th>Classe</th>
                <th>21d</th>
                <th>% PL</th>
                <th>PL</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in fundRanking" :key="item.cnpj_fundo">
                <td>{{ item.name }}</td>
                <td>{{ item.macro_classe }}</td>
                <td :class="moveClass(item.net_flow_21d)">{{ fmtMoney(item.net_flow_21d) }}</td>
                <td>{{ fmtPct(item.flow_pct_pl_21d) }}</td>
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
  name: 'FundsFlowStressView',
  setup: injectFundsFlowContext,
}
</script>

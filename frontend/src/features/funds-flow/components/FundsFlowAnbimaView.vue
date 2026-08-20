<template>
      <main class="ffl-anbima-view">
        <section class="ffl-global-panel">
          <div class="ffl-section-head">
            <span>ANBIMA fundos</span>
            <strong>{{ fmtDate(anbimaDaily.reference_date) || 'oficial' }}</strong>
          </div>
          <div class="ffl-anbima-cards">
            <div v-for="card in anbimaCards" :key="card.label" class="ffl-anbima-card">
              <span>{{ card.label }}</span>
              <strong :class="card.tone">{{ card.value }}</strong>
            </div>
          </div>

          <section class="ffl-b3-panel">
            <div class="ffl-section-head compact">
              <span>Validação CVM x ANBIMA</span>
              <strong>{{ anbimaValidation.status || 'n/d' }}</strong>
            </div>
            <table class="ffl-anbima-table">
              <thead>
                <tr>
                  <th>Classe</th>
                  <th>CVM PL</th>
                  <th>ANBIMA PL</th>
                  <th>Dif.</th>
                  <th>CVM 1d</th>
                  <th>ANBIMA 1d</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in anbimaValidationRows" :key="item.macro_classe">
                  <td>{{ item.macro_classe }}</td>
                  <td>{{ fmtMoney(item.cvm_aum_brl) }}</td>
                  <td>{{ fmtMoney(item.anbima_aum_brl) }}</td>
                  <td :class="moveClass(item.aum_diff_brl)">{{ fmtPct(item.aum_diff_pct) }}</td>
                  <td :class="moveClass(item.cvm_net_flow_1d_brl)">{{ fmtMoney(item.cvm_net_flow_1d_brl) }}</td>
                  <td :class="moveClass(item.anbima_net_flow_day_brl)">{{ fmtMoney(item.anbima_net_flow_day_brl) }}</td>
                </tr>
              </tbody>
            </table>
          </section>

          <section class="ffl-b3-panel">
            <div class="ffl-section-head compact">
              <span>Tipos ANBIMA em destaque</span>
              <strong>MTD</strong>
            </div>
            <div class="ffl-anbima-split">
              <div>
                <span>Entradas</span>
                <div v-for="item in anbimaTopInflows" :key="`ai-${item.name}`" class="ffl-rank-row compact">
                  <em>{{ item.name }}</em>
                  <strong class="up">{{ fmtMoney(item.net_flow_month_brl) }}</strong>
                </div>
              </div>
              <div>
                <span>Saídas</span>
                <div v-for="item in anbimaTopOutflows" :key="`ao-${item.name}`" class="ffl-rank-row compact">
                  <em>{{ item.name }}</em>
                  <strong class="down">{{ fmtMoney(item.net_flow_month_brl) }}</strong>
                </div>
              </div>
            </div>
          </section>
        </section>

        <aside class="ffl-anbima-side">
          <section class="ffl-b3-panel inline">
            <div class="ffl-section-head compact">
              <span>Boletim mensal</span>
              <strong>{{ fmtDate(anbimaLatestArticle.display_date_text) }}</strong>
            </div>
            <div class="ffl-anbima-article">
              <strong>{{ anbimaLatestArticle.title || 'Sem boletim carregado' }}</strong>
              <p>{{ anbimaLatestArticle.summary }}</p>
            </div>
          </section>
          <section class="ffl-b3-panel inline">
            <div class="ffl-section-head compact">
              <span>Ranking administradores</span>
              <strong>{{ anbimaAdminRanking.period_label || 'mensal' }}</strong>
            </div>
            <div v-for="item in anbimaAdminRows" :key="`adm-${item.rank}`" class="ffl-b3-row anbima-ranking">
              <span>{{ item.rank }}. {{ item.name }}</span>
              <strong>{{ fmtMoney(item.total_aum_brl) }}</strong>
              <em>{{ item.dominant_class }}</em>
            </div>
          </section>
          <section class="ffl-b3-panel inline">
            <div class="ffl-section-head compact">
              <span>Ranking gestores</span>
              <strong>{{ anbimaManagerRanking.period_label || 'mensal' }}</strong>
            </div>
            <div v-for="item in anbimaManagerRows" :key="`mgr-${item.rank}`" class="ffl-b3-row anbima-ranking">
              <span>{{ item.rank }}. {{ item.name }}</span>
              <strong>{{ fmtMoney(item.total_aum_brl) }}</strong>
              <em>{{ item.dominant_class }}</em>
            </div>
          </section>
        </aside>
      </main>

</template>

<script>
import { injectFundsFlowContext } from '../context'
export default {
  name: 'FundsFlowAnbimaView',
  setup: injectFundsFlowContext,
}
</script>

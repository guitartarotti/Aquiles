<template>
      <main class="ffl-etf-view">
        <section class="ffl-table-panel ffl-etf-mode-panel">
          <div class="ffl-section-head">
            <span>Modos ETF</span>
            <strong>{{ etfViewMode === 'daily_flow' ? 'Daily Flow' : 'Local + global' }}</strong>
          </div>
          <div class="ffl-asset-tabs">
            <button
              type="button"
              :class="{ active: etfViewMode === 'local_global' }"
              @click="etfViewMode = 'local_global'"
            >
              Local + global
            </button>
            <button
              type="button"
              :class="{ active: etfViewMode === 'daily_flow' }"
              @click="etfViewMode = 'daily_flow'"
            >
              ETF Daily Flow
            </button>
          </div>
        </section>

        <template v-if="etfViewMode === 'local_global'">
          <section class="ffl-global-panel ffl-etf-hero">
            <div class="ffl-section-head">
              <span>ETF local e global</span>
              <strong>B3 + CVM + ANBIMA + ICI</strong>
            </div>
            <div class="ffl-global-cards compact">
              <div v-for="card in etfCards" :key="card.key" class="ffl-global-card">
                <span>{{ card.label }}</span>
                <strong :class="card.tone">{{ card.value }}</strong>
                <em>{{ card.detail }}</em>
              </div>
            </div>
            <div class="ffl-etf-flow-strip">
              <div v-for="item in etfLocalSeriesPreview" :key="item.date" class="ffl-etf-flow-day">
                <span>{{ shortDate(item.date) }}</span>
                <i :class="moveClass(item.rolling_flow_21d)" :style="{ height: etfFlowBarHeight(item.rolling_flow_21d) }"></i>
                <strong :class="moveClass(item.rolling_flow_21d)">{{ fmtMoney(item.rolling_flow_21d) }}</strong>
              </div>
            </div>
          </section>

          <section class="ffl-table-panel ffl-etf-list">
            <div class="ffl-section-head">
              <span>ETFs listados B3</span>
              <strong>{{ b3EtfRows.length }} fundos</strong>
            </div>
            <div class="ffl-asset-tabs">
              <button
                v-for="category in b3EtfCategoryTabs"
                :key="category"
                type="button"
                :class="{ active: b3EtfCategoryFilter === category }"
                @click="b3EtfCategoryFilter = category"
              >
                {{ category === 'ALL' ? 'Todos' : category }}
              </button>
            </div>
            <table>
              <thead>
                <tr>
                  <th>Codigo</th>
                  <th>Categoria</th>
                  <th>Fundo</th>
                  <th>Negociacao</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in b3EtfRows" :key="`${item.fund_type}-${item.ticker}`">
                  <td>{{ item.ticker }}</td>
                  <td>{{ item.category }}</td>
                  <td>{{ item.fund_name }}</td>
                  <td>{{ item.trading_name }}</td>
                </tr>
                <tr v-if="!b3EtfRows.length">
                  <td colspan="4" class="ffl-empty-row">Sem ETFs B3 carregados.</td>
                </tr>
              </tbody>
            </table>
          </section>

          <aside class="ffl-b3-side">
            <section class="ffl-b3-panel inline">
              <div class="ffl-section-head compact">
                <span>Top ETF CVM</span>
                <strong>fluxo 21d</strong>
              </div>
              <div v-for="item in etfTopFunds" :key="item.cnpj_fundo" class="ffl-b3-row anbima-ranking">
                <span>{{ item.rank }}. {{ item.name }}</span>
                <strong :class="moveClass(item.net_flow_21d)">{{ fmtMoney(item.net_flow_21d) }}</strong>
                <em>{{ fmtMoney(item.aum) }}</em>
              </div>
              <div v-if="!etfTopFunds.length" class="ffl-panel-empty">Sem ranking ETF local.</div>
            </section>

            <section class="ffl-b3-panel inline">
              <div class="ffl-section-head compact">
                <span>ANBIMA ETF</span>
                <strong>{{ fmtDate(etfPanel.anbima?.reference_date) || 'oficial' }}</strong>
              </div>
              <div v-for="item in etfAnbimaRows" :key="item.name" class="ffl-b3-row participant-position">
                <span>{{ item.name }}</span>
                <strong :class="moveClass(item.net_flow_month_brl)">{{ fmtMoney(item.net_flow_month_brl) }}</strong>
                <em>{{ fmtMoney(item.aum_brl) }}</em>
              </div>
              <div v-if="!etfAnbimaRows.length" class="ffl-panel-empty">Sem bloco ANBIMA ETF.</div>
            </section>

            <section class="ffl-b3-panel inline">
              <div class="ffl-section-head compact">
                <span>ICI ETF global</span>
                <strong>{{ fmtDate(etfPanel.ici?.latest_weekly?.date) || 'weekly' }}</strong>
              </div>
              <div v-for="item in etfIciRows" :key="item.category_key || item.category" class="ffl-b3-row participant-position">
                <span>{{ item.category }}</span>
                <strong :class="moveClass(item.flow_usd_mn)">{{ fmtUsdMn(item.flow_usd_mn) }}</strong>
                <em>US$ mi</em>
              </div>
              <div v-if="!etfIciRows.length" class="ffl-panel-empty">Sem ICI ETF semanal.</div>
            </section>

            <section class="ffl-b3-panel inline">
              <div class="ffl-section-head compact">
                <span>BCB macro local</span>
                <strong>{{ bcbMacro.status || 'status' }}</strong>
              </div>
              <div v-for="item in bcbMacroCards" :key="item.key" class="ffl-b3-row participant-position">
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
                <em>{{ item.date }}</em>
              </div>
            </section>
          </aside>
        </template>

        <EtfDailyFlowPanel
          v-else
          class="ffl-etf-daily-panel"
          :active="activeTab === 'etf' && etfViewMode === 'daily_flow'"
          :refresh-nonce="refreshNonce + etfDailyFlowRefreshNonce"
        />
      </main>

</template>

<script>
import EtfDailyFlowPanel from './EtfDailyFlowPanel.vue'
import { injectFundsFlowContext } from '../context'

export default {
  name: 'FundsFlowEtfView',
  components: { EtfDailyFlowPanel },
  setup: injectFundsFlowContext,
}
</script>

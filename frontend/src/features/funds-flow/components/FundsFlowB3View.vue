<template>
      <main class="ffl-b3-view">
        <section class="ffl-table-panel">
          <div class="ffl-section-head">
            <span>Contratos DI/DDI/DOL/WDO/WIN</span>
            <strong>{{ b3ContractRows.length }} contratos | {{ fmtDate(b3OpenInterest.date) }}</strong>
          </div>
          <div class="ffl-asset-tabs">
            <button
              v-for="asset in b3AssetTabs"
              :key="asset"
              type="button"
              :class="{ active: b3AssetFilter === asset }"
              @click="b3AssetFilter = asset"
            >
              {{ asset === 'ALL' ? 'Todos' : asset }}
            </button>
          </div>
          <table class="ffl-contract-table">
            <thead>
              <tr>
                <th>Contrato</th>
                <th>Ativo</th>
                <th>Venc.</th>
                <th>OI</th>
                <th>Var d/d</th>
                <th>% ativo</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in b3ContractRows" :key="item.ticker">
                <td>{{ item.ticker }}</td>
                <td>{{ item.asset }}</td>
                <td>{{ item.expiration_code }}</td>
                <td>{{ fmtCount(item.open_interest) }}</td>
                <td :class="moveClass(item.variation_open_interest)">{{ signedCount(item.variation_open_interest) }}</td>
                <td>{{ fmtPctPlain(item.share_open_interest) }}</td>
              </tr>
            </tbody>
          </table>
        </section>
        <aside class="ffl-b3-side">
          <section v-if="b3MarketSummary" class="ffl-b3-panel inline">
            <div class="ffl-section-head compact">
              <span>CSV dados de mercado</span>
              <strong>{{ b3MarketSummary.period || b3MarketData.data_until || 'B3' }}</strong>
            </div>
            <div class="ffl-market-cards">
              <div>
                <span>Volume total</span>
                <strong>{{ fmtBrlMillion(b3MarketSummary.total_volume_brl_million) }}</strong>
              </div>
              <div>
                <span>ADV</span>
                <strong>{{ fmtBrlMillion(b3MarketSummary.average_daily_brl_million) }}</strong>
              </div>
              <div>
                <span>Negocios</span>
                <strong>{{ fmtCount(b3MarketSummary.total_trades) }}</strong>
              </div>
              <div>
                <span>Estrangeiro</span>
                <strong :class="moveClass(b3MarketSummary.foreign_balance_brl_million)">
                  {{ fmtBrlMillion(b3MarketSummary.foreign_balance_brl_million) }}
                </strong>
              </div>
            </div>
          </section>
          <section class="ffl-b3-panel inline">
            <div class="ffl-section-head compact">
              <span>Resumo por ativo</span>
              <strong>open interest</strong>
            </div>
            <div v-for="item in b3OiMainSummary" :key="`sum-${item.asset}`" class="ffl-b3-row open-interest">
              <span>{{ item.asset }} <small>{{ item.leader_contract }}</small></span>
              <strong>{{ fmtCount(item.open_interest) }}</strong>
              <em :class="moveClass(item.variation_open_interest)">{{ signedCount(item.variation_open_interest) }} d/d</em>
              <em :class="moveClass(item.rolling_21d_variation_open_interest)">{{ signedCount(item.rolling_21d_variation_open_interest) }} 21d</em>
              <em>{{ fmtCount(item.contracts) }} venc.</em>
            </div>
          </section>
          <section class="ffl-b3-panel inline">
            <div class="ffl-section-head compact">
              <span>Posicao por participante</span>
              <strong>BDI agregado</strong>
            </div>
            <div v-for="item in b3Participants" :key="`b3p-${item.participant_type}`" class="ffl-b3-row participant-position">
              <span>{{ item.participant_type }}</span>
              <strong :class="moveClass(item.net_flow_brl)">{{ fmtMoney(item.net_flow_brl) }}</strong>
              <em :class="moveClass(b3Trend(item.participant_type)?.rolling_21d_net_flow_brl)">
                {{ fmtMoney(b3Trend(item.participant_type)?.rolling_21d_net_flow_brl) }} 21d
              </em>
            </div>
          </section>
          <section v-if="b3MonthlyRows.length" class="ffl-b3-panel inline">
            <div class="ffl-section-head compact">
              <span>Participacao mensal por mercado</span>
              <strong>{{ b3InvestorMonthly.period_label || fmtDate(b3InvestorMonthly.date) }}</strong>
            </div>
            <div class="ffl-monthly-wrap">
              <table class="ffl-b3-monthly-table">
                <thead>
                  <tr>
                    <th>Tipo</th>
                    <th>Vista</th>
                    <th>Termo</th>
                    <th>Opcoes</th>
                    <th>Exerc.</th>
                    <th>Blocos</th>
                    <th>Total</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in b3MonthlyRows" :key="`month-${item.participant_type}`">
                    <td>{{ item.participant_type }}</td>
                    <td :title="fmtMoney(item.cash_brl)">{{ fmtPctPlain(item.cash_participation_pct) }}</td>
                    <td :title="fmtMoney(item.forward_brl)">{{ fmtPctPlain(item.forward_participation_pct) }}</td>
                    <td :title="fmtMoney(item.options_brl)">{{ fmtPctPlain(item.options_participation_pct) }}</td>
                    <td :title="fmtMoney(item.options_exercise_brl)">{{ fmtPctPlain(item.options_exercise_participation_pct) }}</td>
                    <td :title="fmtMoney(item.blocks_brl)">{{ fmtPctPlain(item.blocks_participation_pct) }}</td>
                    <td :title="fmtMoney(item.total_brl)">{{ fmtPctPlain(item.total_participation_pct) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
          <section class="ffl-b3-note">
            <strong>{{ b3PositioningStatus.label || 'Categoria de investidor por contrato' }}</strong>
            <span>{{ b3PositioningStatus.note || 'Fonte por contrato aguardando integracao.' }}</span>
          </section>
        </aside>
      </main>

</template>

<script>
import { injectFundsFlowContext } from '../context'
export default {
  name: 'FundsFlowB3View',
  setup: injectFundsFlowContext,
}
</script>

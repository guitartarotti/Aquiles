<template>
      <main class="ffl-cftc-view">
        <section class="ffl-global-panel">
          <div class="ffl-section-head">
            <span>CFTC COT/PRE weekly positioning</span>
            <strong>{{ cftcStatusLabel }}</strong>
          </div>
          <p>Proxy semanal de posicionamento em futuros, opcoes e commodities: posicoes de terca-feira, publicacao usual na sexta. Valores em contratos, nao fluxo de fundos.</p>
          <div class="ffl-cftc-cards">
            <div v-for="card in cftcCards" :key="card.key" class="ffl-global-card">
              <span>{{ card.label }}</span>
              <strong :class="card.tone">{{ card.value }}</strong>
              <em>{{ card.detail }}</em>
            </div>
          </div>
        </section>

        <section class="ffl-global-split embedded cftc-wide">
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Cobertura PRE/API</span>
              <strong>{{ cftcDatasets.length }} datasets</strong>
            </div>
            <table class="ffl-global-table cftc-datasets">
              <thead>
                <tr>
                  <th>Dataset</th>
                  <th>Familia</th>
                  <th>Variante</th>
                  <th>Linhas</th>
                  <th>Campos</th>
                  <th>Data</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in cftcDatasets" :key="item.key">
                  <td>{{ item.key }}</td>
                  <td>{{ item.family_label }}</td>
                  <td>{{ item.variant_label }}</td>
                  <td>{{ fmtCount(item.rows) }}</td>
                  <td>{{ fmtCount(item.fields) }}</td>
                  <td>{{ fmtDate(item.latest_report_date) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Familias COT</span>
              <strong>latest week</strong>
            </div>
            <table class="ffl-global-table">
              <thead>
                <tr>
                  <th>Familia</th>
                  <th>Contratos</th>
                  <th>OI</th>
                  <th>Var OI</th>
                  <th>Bucket</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in cftcFamilies" :key="item.family">
                  <td>{{ item.family_label }}</td>
                  <td>{{ fmtCount(item.contracts) }}</td>
                  <td>{{ fmtCount(item.open_interest) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.open_interest_change)">{{ signedCount(item.open_interest_change) }}</td>
                  <td>{{ item.top_bucket || '-' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="ffl-global-split embedded">
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Participantes</span>
              <strong>net agregado</strong>
            </div>
            <table class="ffl-global-table">
              <thead>
                <tr>
                  <th>Participante</th>
                  <th>Net</th>
                  <th>Var sem.</th>
                  <th>% OI</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in cftcParticipants" :key="item.participant_key">
                  <td>{{ item.participant }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.net)">{{ signedCount(item.net) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.weekly_net_change)">{{ signedCount(item.weekly_net_change) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.net_pct_open_interest)">{{ fmtPctPlain(item.net_pct_open_interest) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Resumo por bucket</span>
              <strong>Combined</strong>
            </div>
            <table class="ffl-global-table">
              <thead>
                <tr>
                  <th>Bucket</th>
                  <th>OI</th>
                  <th>Asset mgr net</th>
                  <th>Lev funds net</th>
                  <th>Var lev.</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in cftcBuckets" :key="item.asset_bucket">
                  <td>{{ item.asset_bucket }}</td>
                  <td>{{ fmtCount(item.open_interest) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.asset_mgr_net)">{{ signedCount(item.asset_mgr_net) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.lev_money_net)">{{ signedCount(item.lev_money_net) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.lev_money_change_net)">{{ signedCount(item.lev_money_change_net) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="ffl-global-split embedded cftc-focus-grid">
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Rates foco</span>
              <strong>{{ cftcRatesContracts.length }} contratos</strong>
            </div>
            <table class="ffl-global-table cftc-contracts">
              <thead>
                <tr>
                  <th>Contrato</th>
                  <th>OI</th>
                  <th>Asset mgr</th>
                  <th>Lev funds</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in cftcRatesContracts" :key="`rates-${item.contract_code}`">
                  <td>{{ item.market_name }}</td>
                  <td>{{ fmtCount(item.open_interest) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.asset_mgr_net)">{{ signedCount(item.asset_mgr_net) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.lev_money_net)">{{ signedCount(item.lev_money_net) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Equities foco</span>
              <strong>{{ cftcEquityContracts.length }} contratos</strong>
            </div>
            <table class="ffl-global-table cftc-contracts">
              <thead>
                <tr>
                  <th>Contrato</th>
                  <th>OI</th>
                  <th>Asset mgr</th>
                  <th>Lev funds</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in cftcEquityContracts" :key="`equity-${item.contract_code}`">
                  <td>{{ item.market_name }}</td>
                  <td>{{ fmtCount(item.open_interest) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.asset_mgr_net)">{{ signedCount(item.asset_mgr_net) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.lev_money_net)">{{ signedCount(item.lev_money_net) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>FX foco</span>
              <strong>{{ cftcFxContracts.length }} contratos</strong>
            </div>
            <table class="ffl-global-table cftc-contracts">
              <thead>
                <tr>
                  <th>Contrato</th>
                  <th>OI</th>
                  <th>Asset mgr</th>
                  <th>Lev funds</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in cftcFxContracts" :key="`fx-${item.contract_code}`">
                  <td>{{ item.market_name }}</td>
                  <td>{{ fmtCount(item.open_interest) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.asset_mgr_net)">{{ signedCount(item.asset_mgr_net) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.lev_money_net)">{{ signedCount(item.lev_money_net) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="ffl-global-split embedded cftc-wide">
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Participantes ampliados</span>
              <strong>{{ cftcExtendedParticipants.length }} cortes</strong>
            </div>
            <table class="ffl-global-table cftc-contracts">
              <thead>
                <tr>
                  <th>Familia / participante</th>
                  <th>Long</th>
                  <th>Short</th>
                  <th>Net</th>
                  <th>Var sem.</th>
                  <th>% OI</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in cftcExtendedParticipants" :key="`${item.family}-${item.participant_key}`">
                  <td>{{ item.family_label }} - {{ item.participant }}</td>
                  <td>{{ fmtCount(item.long) }}</td>
                  <td>{{ fmtCount(item.short) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.net)">{{ signedCount(item.net) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.weekly_net_change)">{{ signedCount(item.weekly_net_change) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.net_pct_open_interest)">{{ fmtPctPlain(item.net_pct_open_interest) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Buckets ampliados</span>
              <strong>primary participant</strong>
            </div>
            <table class="ffl-global-table">
              <thead>
                <tr>
                  <th>Familia / bucket</th>
                  <th>Contratos</th>
                  <th>OI</th>
                  <th>Net primario</th>
                  <th>Var sem.</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in cftcExtendedBuckets" :key="`${item.family}-${item.asset_bucket}`">
                  <td>{{ item.family_label }} - {{ item.asset_bucket }}</td>
                  <td>{{ fmtCount(item.contracts) }}</td>
                  <td>{{ fmtCount(item.open_interest) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.primary_net)">{{ signedCount(item.primary_net) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.primary_weekly_net_change)">{{ signedCount(item.primary_weekly_net_change) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="ffl-global-panel">
          <div class="ffl-section-head compact">
            <span>Contratos principais</span>
            <strong>{{ cftcContracts.length }} mercados</strong>
          </div>
          <table class="ffl-global-table cftc-contracts">
            <thead>
              <tr>
                <th>Contrato</th>
                <th>Bucket</th>
                <th>OI</th>
                <th>Dealer net</th>
                <th>Asset mgr net</th>
                <th>Lev funds net</th>
                <th>Var lev.</th>
                <th>Z lev.</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in cftcContracts" :key="item.contract_code">
                <td>{{ item.market_name }}</td>
                <td>{{ item.asset_bucket }}</td>
                <td>{{ fmtCount(item.open_interest) }}</td>
                <td class="ffl-flow-value" :class="moveClass(item.dealer_net)">{{ signedCount(item.dealer_net) }}</td>
                <td class="ffl-flow-value" :class="moveClass(item.asset_mgr_net)">{{ signedCount(item.asset_mgr_net) }}</td>
                <td class="ffl-flow-value" :class="moveClass(item.lev_money_net)">{{ signedCount(item.lev_money_net) }}</td>
                <td class="ffl-flow-value" :class="moveClass(item.lev_money_change_net)">{{ signedCount(item.lev_money_change_net) }}</td>
                <td class="ffl-flow-value" :class="moveClass(item.lev_money_net_zscore_156w)">{{ fmtNum(item.lev_money_net_zscore_156w, 2) }}</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section class="ffl-global-panel">
          <div class="ffl-section-head compact">
            <span>Contratos COT ampliados</span>
            <strong>{{ cftcExtendedContracts.length }} mercados</strong>
          </div>
          <table class="ffl-global-table cftc-contracts">
            <thead>
              <tr>
                <th>Contrato</th>
                <th>Familia</th>
                <th>Bucket</th>
                <th>OI</th>
                <th>Participante foco</th>
                <th>Net</th>
                <th>Var sem.</th>
                <th>% OI</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in cftcExtendedContracts" :key="`${item.dataset_key}-${item.contract_code}`">
                <td>{{ item.market_name }}</td>
                <td>{{ item.family_label }}</td>
                <td>{{ item.asset_bucket }}</td>
                <td>{{ fmtCount(item.open_interest) }}</td>
                <td>{{ cftcParticipantLabel(item.family, item.primary_participant_key) }}</td>
                <td class="ffl-flow-value" :class="moveClass(item.primary_net)">{{ signedCount(item.primary_net) }}</td>
                <td class="ffl-flow-value" :class="moveClass(item.primary_weekly_net_change)">{{ signedCount(item.primary_weekly_net_change) }}</td>
                <td class="ffl-flow-value" :class="moveClass(item.primary_pct_oi_net)">{{ fmtPctPlain(item.primary_pct_oi_net) }}</td>
              </tr>
            </tbody>
          </table>
        </section>
      </main>

</template>

<script>
import { injectFundsFlowContext } from '../context'
export default {
  name: 'FundsFlowCftcView',
  setup: injectFundsFlowContext,
}
</script>

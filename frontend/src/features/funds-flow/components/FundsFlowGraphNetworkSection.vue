<template>
        <section class="ffl-graph-layout">
          <div class="ffl-global-panel ffl-cda-graph-panel">
            <GraphPanel
              :graph-data="cdaGraphData"
              :loading="cdaGraphLoading || cdaGraphBuilding"
              :current-phase="2"
              :is-simulating="false"
              :default-show-edge-labels="false"
              @refresh="loadCdaGraph(true)"
            />
            <div v-if="!cdaGraphLoading && !cdaGraphData" class="ffl-graph-empty">
              Grafo ainda nao carregado. Use Recarregar ou Reconstruir Neo4j.
            </div>
          </div>

          <aside class="ffl-graph-side">
            <section class="ffl-global-panel">
              <div class="ffl-section-head compact">
                <span>Tipos de nos</span>
                <strong>{{ fmtCount(cdaVisibleGraphNodeCounts.length) }}</strong>
              </div>
              <div class="ffl-graph-count-list">
                <button
                  v-for="item in cdaVisibleGraphNodeCounts"
                  :key="`cgn-${item.label}`"
                  type="button"
                  class="ffl-graph-count"
                >
                  <span>{{ item.label }}</span>
                  <strong>{{ fmtCount(item.count) }}</strong>
                </button>
              </div>
            </section>

            <section class="ffl-global-panel">
              <div class="ffl-section-head compact">
                <span>Relacoes</span>
                <strong>{{ fmtCount(cdaVisibleGraphEdgeCounts.length) }}</strong>
              </div>
              <div class="ffl-graph-count-list">
                <button
                  v-for="item in cdaVisibleGraphEdgeCounts"
                  :key="`cge-${item.type}`"
                  type="button"
                  class="ffl-graph-count edge"
                >
                  <span>{{ item.type }}</span>
                  <strong>{{ fmtCount(item.count) }}</strong>
                </button>
              </div>
            </section>

            <section class="ffl-global-panel">
              <div class="ffl-section-head compact">
                <span>Crowding por emissor</span>
                <strong>fundos conectados</strong>
              </div>
              <div class="ffl-graph-table-scroll">
                <table class="ffl-global-table">
                  <thead>
                    <tr>
                      <th>Emissor</th>
                      <th>Fundos</th>
                      <th>Gross</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="item in cdaGraphCrowdingRows"
                      :key="`cgcr-${item.issuer_id}`"
                      class="clickable"
                      @click="cdaGraphIssuerFilter = item.issuer_name; applyCdaGraphFilters()"
                    >
                      <td>{{ item.issuer_name }}</td>
                      <td>{{ fmtCount(item.fund_count) }}</td>
                      <td>{{ fmtMoney(item.gross_value) }}</td>
                    </tr>
                    <tr v-if="!cdaGraphCrowdingRows.length">
                      <td colspan="3" class="ffl-empty-row">Sem ranking de emissor.</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>
          </aside>
        </section>

        <section class="ffl-graph-intelligence">
          <section class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Perfis semelhantes</span>
              <strong>{{ fmtCount(cdaPortfolioSummary.pair_count) }} pares</strong>
            </div>
            <div class="ffl-trail-list">
              <button
                v-for="item in cdaPortfolioPairRows"
                :key="`profile-sim-${item.fund_a_cnpj}-${item.fund_b_cnpj}`"
                type="button"
                class="ffl-trail-row"
                @click="cdaGraphFundFilter = item.fund_a_cnpj || ''; applyCdaGraphFilters()"
              >
                <span>
                  <strong>{{ item.fund_a }}</strong>
                  <em>{{ item.fund_a_type }} -> {{ item.fund_b_type }}</em>
                </span>
                <span>
                  <strong>{{ item.fund_b }}</strong>
                  <em>{{ portfolioSharedFactorText(item) }}</em>
                </span>
                <b>{{ fmtPctPlain(item.similarity_pct) }}</b>
                <b>{{ item.profile_label }}</b>
              </button>
              <div v-if="!cdaPortfolioPairRows.length" class="ffl-panel-empty">Sem pares com perfil de carteira semelhante carregado.</div>
            </div>
          </section>

          <section class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Trilhas explicativas</span>
              <strong>tipo -> tema -> emissor</strong>
            </div>
            <div class="ffl-trail-list compact">
              <button
                v-for="item in cdaBridgePathRows"
                :key="`bridge-${item.fund_type}-${item.target}`"
                type="button"
                class="ffl-trail-row bridge"
                @click="openCdaBridgeModal(item)"
              >
                <span>
                  <strong>{{ item.fund_type }}</strong>
                  <em>{{ item.target_label }}</em>
                </span>
                <span>
                  <strong>{{ (item.top_issuers || []).filter(Boolean).slice(0, 2).join(' | ') || 'sem emissor lider' }}</strong>
                  <em>{{ (item.top_asset_classes || []).filter(Boolean).slice(0, 3).join(', ') }}</em>
                </span>
                <b>{{ fmtCount(item.fund_count) }} fundos</b>
                <b :class="moveClass(item.net_value)">{{ fmtMoney(item.net_value) }}</b>
              </button>
            </div>
          </section>
        </section>

        <section class="ffl-graph-profile-similarity">
          <section class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Estruturas detectadas</span>
              <strong>opcoes, RF e cotas</strong>
            </div>
            <div class="ffl-profile-structure-list">
              <button
                v-for="item in cdaPortfolioStructureRows"
                :key="`portfolio-structure-${item.structure_key}`"
                type="button"
                class="ffl-profile-structure-row"
              >
                <span>
                  <strong>{{ item.label }}</strong>
                  <em>{{ (item.sample_underlyings || []).slice(0, 4).join(' | ') || (item.sample_funds || []).slice(0, 2).join(' | ') }}</em>
                </span>
                <b>{{ fmtCount(item.fund_count) }} fundos</b>
                <b>{{ fmtMoney(item.gross_value) }}</b>
              </button>
              <div v-if="!cdaPortfolioStructureRows.length" class="ffl-panel-empty">Sem estruturas detectadas nesse recorte.</div>
            </div>
          </section>

          <section class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Fatores compartilhados</span>
              <strong>{{ fmtCount(cdaPortfolioSummary.factor_count) }} fatores</strong>
            </div>
            <div class="ffl-profile-factor-list">
              <button
                v-for="item in cdaPortfolioFactorRows"
                :key="`portfolio-factor-${item.feature_id}`"
                type="button"
                class="ffl-profile-factor-row"
                @click="cdaGraphIssuerFilter = item.feature_type === 'issuer' ? item.label : ''; applyCdaGraphFilters()"
              >
                <span>
                  <strong>{{ item.label }}</strong>
                  <em>{{ item.feature_type }} | {{ item.bucket || 'perfil' }}</em>
                </span>
                <b>{{ fmtCount(item.fund_count) }} fundos</b>
                <b>{{ fmtMoney(item.gross_proxy) }}</b>
              </button>
              <div v-if="!cdaPortfolioFactorRows.length" class="ffl-panel-empty">Sem fatores compartilhados carregados.</div>
            </div>
          </section>

          <section class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Fundos perfilados</span>
              <strong>{{ fmtCount(cdaPortfolioSummary.candidate_fund_count) }} candidatos</strong>
            </div>
            <div class="ffl-profile-fund-list">
              <button
                v-for="item in cdaPortfolioFundProfileRows"
                :key="`portfolio-profile-${item.fund_cnpj}`"
                type="button"
                class="ffl-profile-fund-row"
                @click="cdaGraphFundFilter = item.fund_cnpj; applyCdaGraphFilters()"
              >
                <span>
                  <strong>{{ item.fund_name }}</strong>
                  <em>{{ (item.structures || []).map(row => row.label).slice(0, 2).join(' | ') }}</em>
                </span>
                <b>{{ fmtCount(item.structure_count) }} estruturas</b>
                <b>{{ fmtMoney(item.gross_total) }}</b>
              </button>
              <div v-if="!cdaPortfolioFundProfileRows.length" class="ffl-panel-empty">Sem fundos perfilados.</div>
            </div>
          </section>
        </section>

</template>

<script>
import GraphPanel from '@/components/GraphPanel.vue'
import { injectFundsFlowContext } from '../context'

export default {
  name: 'FundsFlowGraphNetworkSection',
  components: { GraphPanel },
  setup: injectFundsFlowContext,
}
</script>

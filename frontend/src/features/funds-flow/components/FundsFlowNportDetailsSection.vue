<template>
        <section v-if="nportPayload?.ok" class="ffl-global-split">
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Crowding x fragilidade</span>
              <strong>concentracao, EM net e retorno</strong>
            </div>
            <svg class="ffl-nport-scatter" viewBox="0 0 790 292" role="img">
              <line x1="42" y1="258" x2="748" y2="258" />
              <line x1="42" y1="28" x2="42" y2="258" />
              <line x1="42" :y1="nportScatterZeroY" x2="748" :y2="nportScatterZeroY" class="zero" />
              <text x="44" y="22">EM net % AUM</text>
              <text x="600" y="282">max holding %</text>
              <circle
                v-for="point in nportScatterPoints"
                :key="`npsp-${point.accession_number}`"
                :cx="point.x"
                :cy="point.y"
                :r="point.r"
                :fill="point.color"
                :opacity="point.opacity"
              >
                <title>{{ nportScatterTitle(point) }}</title>
              </circle>
            </svg>
          </div>

          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Radar short squeeze EM</span>
              <strong>short concentrado em poucos ativos</strong>
            </div>
            <table class="ffl-global-table">
              <thead>
                <tr>
                  <th>Ativo</th>
                  <th>Pais</th>
                  <th>Short</th>
                  <th>% gross</th>
                  <th>Fundos</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in nportSqueezeRows.slice(0, 14)" :key="`npsq-${item.security_key}-${item.asset_cat}`">
                  <td :title="`${item.issuer_name} | ${item.security_key}`">{{ item.issuer_title || item.issuer_name || item.security_key }}</td>
                  <td>{{ item.investment_country }}</td>
                  <td>{{ fmtUsd(item.short_value) }}</td>
                  <td>{{ fmtPctPlain(item.short_intensity_pct) }}</td>
                  <td>{{ fmtCount(item.fund_count) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section v-if="nportPayload?.ok" class="ffl-global-split">
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Momentum latente EM</span>
              <strong>retorno 3m positivo + exposicao EM</strong>
            </div>
            <table class="ffl-global-table">
              <thead>
                <tr>
                  <th>Fundo</th>
                  <th>EM % AUM</th>
                  <th>Ret. 3m</th>
                  <th>Score</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in nportEdgeRows.slice(0, 14)" :key="`npedge-${item.accession_number}`">
                  <td :title="`${item.series_name} | ${item.registrant_name}`">{{ item.series_name || item.accession_number }}</td>
                  <td>{{ fmtPctPlain(item.net_pct_aum) }}</td>
                  <td :class="moveClass(item.return_3m_pct)">{{ fmtPctPlain(item.return_3m_pct) }}</td>
                  <td>{{ fmtNum(item.edge_score, 1) }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Mapa de assimetria por pais</span>
              <strong>long, short e net/gross</strong>
            </div>
            <table class="ffl-global-table">
              <thead>
                <tr>
                  <th>Pais</th>
                  <th>Long</th>
                  <th>Short</th>
                  <th>Net/Gross</th>
                  <th>Fundos</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in nportCountryImbalanceRows.slice(0, 14)" :key="`npcimb-${item.investment_country}`">
                  <td>{{ item.investment_country }}</td>
                  <td>{{ fmtUsd(item.long_value) }}</td>
                  <td>{{ fmtUsd(item.short_value) }}</td>
                  <td :class="moveClass(item.net_to_gross_pct)">{{ fmtPctPlain(item.net_to_gross_pct) }}</td>
                  <td>{{ fmtCount(item.fund_count) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section v-if="nportPayload?.ok" class="ffl-global-split">
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Classe de ativo</span>
              <strong>valor reportado</strong>
            </div>
            <table class="ffl-global-table">
              <thead>
                <tr>
                  <th>Classe</th>
                  <th>Valor</th>
                  <th>%</th>
                  <th>Filings</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in nportAssetRows.slice(0, 12)" :key="`npa-${item.key}`">
                  <td>{{ item.label }}</td>
                  <td>{{ fmtUsd(item.value) }}</td>
                  <td>{{ fmtPctPlain(item.share_value_pct) }}</td>
                  <td>{{ fmtCount(item.fund_count) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Paises e moedas</span>
              <strong>top exposicoes</strong>
            </div>
            <div class="ffl-nport-dual-table">
              <table class="ffl-global-table">
                <thead>
                  <tr><th>Pais</th><th>Valor</th><th>%</th></tr>
                </thead>
                <tbody>
                  <tr v-for="item in nportCountryRows.slice(0, 8)" :key="`npc-${item.key}`">
                    <td>{{ item.label }}</td>
                    <td>{{ fmtUsd(item.value) }}</td>
                    <td>{{ fmtPctPlain(item.share_value_pct) }}</td>
                  </tr>
                </tbody>
              </table>
              <table class="ffl-global-table">
                <thead>
                  <tr><th>Moeda</th><th>Valor</th><th>%</th></tr>
                </thead>
                <tbody>
                  <tr v-for="item in nportCurrencyRows.slice(0, 8)" :key="`npcu-${item.key}`">
                    <td>{{ item.label }}</td>
                    <td>{{ fmtUsd(item.value) }}</td>
                    <td>{{ fmtPctPlain(item.share_value_pct) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </section>

        <section v-if="nportPayload?.ok" class="ffl-global-split">
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Top emissores</span>
              <strong>crowding agregado</strong>
            </div>
            <table class="ffl-global-table">
              <thead>
                <tr>
                  <th>Emissor</th>
                  <th>Valor</th>
                  <th>Filings</th>
                  <th>%</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in nportIssuerRows.slice(0, 14)" :key="`npi-${item.key}`">
                  <td>{{ item.label || item.key }}</td>
                  <td>{{ fmtUsd(item.value) }}</td>
                  <td>{{ fmtCount(item.fund_count) }}</td>
                  <td>{{ fmtPctPlain(item.share_value_pct) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Top securities</span>
              <strong>CUSIP/holding key</strong>
            </div>
            <table class="ffl-global-table">
              <thead>
                <tr>
                  <th>Security</th>
                  <th>Valor</th>
                  <th>Filings</th>
                  <th>%</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in nportSecurityRows.slice(0, 14)" :key="`nps-${item.key}`">
                  <td>{{ item.label || item.key }}</td>
                  <td>{{ fmtUsd(item.value) }}</td>
                  <td>{{ fmtCount(item.fund_count) }}</td>
                  <td>{{ fmtPctPlain(item.share_value_pct) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section v-if="nportPayload?.ok" class="ffl-global-split">
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Maiores fundos</span>
              <strong>net assets</strong>
            </div>
            <table class="ffl-global-table">
              <thead>
                <tr>
                  <th>Fundo</th>
                  <th>Registrante</th>
                  <th>AUM</th>
                  <th>Max pos.</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in nportFundRows.slice(0, 12)" :key="`npf-${item.accession_number}`">
                  <td>{{ item.series_name || item.accession_number }}</td>
                  <td>{{ item.registrant_name }}</td>
                  <td>{{ fmtUsd(item.net_assets) }}</td>
                  <td>{{ fmtPctPlain(item.max_holding_pct) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Gestoras / registrants</span>
              <strong>consolidado</strong>
            </div>
            <table class="ffl-global-table">
              <thead>
                <tr>
                  <th>Registrante</th>
                  <th>AUM</th>
                  <th>Fundos</th>
                  <th>Fluxo 3m</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in nportRegistrantRows.slice(0, 12)" :key="`npr-${item.registrant_name}`">
                  <td>{{ item.registrant_name }}</td>
                  <td>{{ fmtUsd(item.net_assets) }}</td>
                  <td>{{ fmtCount(item.funds) }}</td>
                  <td :class="moveClass(item.net_flow_3m)">{{ fmtUsd(item.net_flow_3m) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section v-if="nportPayload?.ok" class="ffl-global-split">
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Credito e vencimentos</span>
              <strong>debt security</strong>
            </div>
            <table class="ffl-global-table">
              <thead>
                <tr>
                  <th>Bucket</th>
                  <th>Valor</th>
                  <th>Cupom ponderado</th>
                  <th>Default</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in nportDebtRows" :key="`npd-${item.maturity_bucket}`">
                  <td>{{ item.maturity_bucket }}</td>
                  <td>{{ fmtUsd(item.value) }}</td>
                  <td>{{ fmtPctPlain(item.weighted_coupon) }}</td>
                  <td>{{ fmtUsd(item.default_value) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Risco operacional dos dados</span>
              <strong>fair value / derivativos</strong>
            </div>
            <div class="ffl-nport-dual-table">
              <table class="ffl-global-table">
                <thead>
                  <tr><th>Fair value</th><th>Valor</th><th>%</th></tr>
                </thead>
                <tbody>
                  <tr v-for="item in nportFairValueRows" :key="`npfv-${item.key}`">
                    <td>{{ item.label }}</td>
                    <td>{{ fmtUsd(item.value) }}</td>
                    <td>{{ fmtPctPlain(item.share_value_pct) }}</td>
                  </tr>
                </tbody>
              </table>
              <table class="ffl-global-table">
                <thead>
                  <tr><th>Derivativo</th><th>Valor</th><th>Filings</th></tr>
                </thead>
                <tbody>
                  <tr v-for="item in nportDerivativeRows" :key="`npdv-${item.key}`">
                    <td>{{ item.label }}</td>
                    <td :class="moveClass(item.value)">{{ fmtUsd(item.value) }}</td>
                    <td>{{ fmtCount(item.fund_count) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </section>

        <section v-if="nportPayload?.ok" class="ffl-global-split">
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Leitura estrategica</span>
              <strong>payload auditavel</strong>
            </div>
            <ul class="ffl-nport-list">
              <li v-for="item in nportInsights.quick_read || []" :key="item">{{ item }}</li>
              <li v-for="item in nportInsights.risk_flags || []" :key="item">{{ item }}</li>
            </ul>
          </div>
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Modelo de grafo sugerido</span>
              <strong>pronto para tela dedicada</strong>
            </div>
            <ul class="ffl-nport-list">
              <li>Fund -> Registrant -> Issuer -> Security -> Country -> Currency -> AssetClass.</li>
              <li>Edges: reports_holding, issued_by, exposed_to_country, denominated_in, belongs_to_asset_class.</li>
              <li>Pesos: currency_value, percentage, net_assets, restricted_value e derivative_value.</li>
              <li v-for="item in nportInsights.recommended_views || []" :key="item">{{ item }}</li>
            </ul>
          </div>
        </section>

        <section v-if="nportPayload?.ok" class="ffl-global-panel">
          <div class="ffl-section-head compact">
            <span>Lineage e tabelas importadas</span>
            <strong>{{ nportManifest.length }} arquivos</strong>
          </div>
          <table class="ffl-global-table">
            <thead>
              <tr>
                <th>Tabela</th>
                <th>Arquivo</th>
                <th>Linhas</th>
                <th>Colunas</th>
                <th>Tamanho</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in nportManifest" :key="item.table_name">
                <td>{{ item.raw_table_name }}</td>
                <td>{{ item.file_name }}</td>
                <td>{{ fmtCount(item.row_count) }}</td>
                <td>{{ fmtCount(item.column_count) }}</td>
                <td>{{ fmtBytes(item.file_size_bytes) }}</td>
              </tr>
            </tbody>
          </table>
          <details class="ffl-source-logs nport">
            <summary>Logs recentes da ingestao</summary>
            <pre>{{ JSON.stringify(nportLogs, null, 2) }}</pre>
          </details>
        </section>
</template>

<script>
import { injectFundsFlowContext } from '../context'
export default {
  name: 'FundsFlowNportDetailsSection',
  setup: injectFundsFlowContext,
}
</script>

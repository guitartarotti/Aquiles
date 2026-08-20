<template>
      <main class="ffl-cda-view">
        <section class="ffl-global-panel">
          <div class="ffl-section-head">
            <span>CVM CDA Brasil</span>
            <strong>{{ cdaReport.period_label || 'base mensal' }} | {{ fmtDate(cdaReport.as_of_date) }}</strong>
          </div>
          <p>Carteira mensal dos fundos brasileiros: posicoes por ativo, emissor, pais, classe de ativo, PL, negociacoes e blocos confidenciais. E o equivalente brasileiro mais proximo do N-PORT, mas com sazonalidade mensal e confidencialidade nas posicoes recentes.</p>
          <div class="ffl-nport-actions">
            <button type="button" class="ffl-btn tiny" :disabled="cdaLoading" @click="loadCdaDashboard(true)">
              {{ cdaLoading ? '...' : 'Recarregar' }}
            </button>
            <button type="button" class="ffl-btn tiny" :disabled="cdaLoading" @click="ingestCdaLatest">
              {{ cdaLoading ? 'Capturando...' : 'Capturar CVM' }}
            </button>
            <button type="button" class="ffl-btn tiny" :disabled="cdaLoading" @click="openSelectedCdaFundGraph">
              Ver grafo
            </button>
            <span v-if="cdaError" class="ffl-inline-error">{{ cdaError }}</span>
          </div>
          <div v-if="cdaLoading && !cdaPayload" class="ffl-empty">Carregando CVM CDA...</div>
          <div v-else-if="cdaPayload?.ok" class="ffl-global-cards compact">
            <div v-for="card in cdaCards" :key="card.key" class="ffl-global-card">
              <span>{{ card.label }}</span>
              <strong :class="card.tone">{{ card.value }}</strong>
              <em>{{ card.detail }}</em>
            </div>
          </div>
          <div v-else class="ffl-empty">
            Banco CVM CDA ainda vazio. Use Capturar CVM para baixar o mes mais recente via CKAN e materializar o banco local.
          </div>
        </section>

        <section v-if="cdaPayload?.ok" class="ffl-global-split">
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Fundos por exposicao</span>
              <strong>{{ cdaTargetLabel(cdaFundTarget) }} | {{ cdaSideLabel(cdaFundSide) }}</strong>
            </div>
            <div class="ffl-nport-controls wrap">
              <button
                v-for="target in cdaTargets"
                :key="`cdft-${target.key}`"
                type="button"
                :class="{ active: cdaFundTarget === target.key }"
                @click="setCdaFundTarget(target.key)"
              >
                {{ target.label }}
              </button>
              <button
                v-for="side in cdaSides"
                :key="`cdfside-${side.key}`"
                type="button"
                :class="{ active: cdaFundSide === side.key }"
                @click="setCdaFundSide(side.key)"
              >
                {{ side.label }}
              </button>
            </div>
            <table class="ffl-global-table nport-clickable">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Fundo</th>
                  <th>Exposicao</th>
                  <th>% PL</th>
                  <th>Concentr.</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="item in cdaFundRows"
                  :key="`cdaf-${item.fund_cnpj}`"
                  :class="{ active: cdaSelectedFund?.fund_cnpj === item.fund_cnpj }"
                  :style="nportRowTint(cdaFundSide === 'short' ? -item.selected_value : item.selected_value, cdaFundMax)"
                  @click="selectCdaFund(item)"
                >
                  <td>{{ item.rank }}</td>
                  <td :title="`${item.fund_name} | ${item.fund_cnpj}`">{{ item.fund_name || item.fund_cnpj }}</td>
                  <td :style="nportCellTint(cdaFundSide === 'short' ? -item.selected_value : item.selected_value, cdaFundMax)">{{ fmtMoney(item.selected_value) }}</td>
                  <td>{{ fmtPctPlain(item.target_pct_pl) }}</td>
                  <td>{{ fmtPctPlain(item.concentration_pct) }}</td>
                </tr>
                <tr v-if="!cdaFundRows.length">
                  <td colspan="5" class="ffl-empty-row">{{ cdaAnalyticsLoading ? 'Carregando...' : 'Sem fundos nesse recorte.' }}</td>
                </tr>
              </tbody>
            </table>
            <div class="ffl-nport-pagination">
              <button type="button" :disabled="cdaFundPage <= 1" @click="setCdaFundPage(-1)">Anterior</button>
              <span>Pagina {{ cdaFundPage }} / {{ totalPages(cdaFunds) }}</span>
              <button type="button" :disabled="cdaFundPage >= totalPages(cdaFunds)" @click="setCdaFundPage(1)">Proxima</button>
            </div>
          </div>

          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Ativos / emissores mais carregados</span>
              <strong>{{ cdaTargetLabel(cdaAssetTarget) }} | {{ cdaSideLabel(cdaAssetSide) }}</strong>
            </div>
            <div class="ffl-nport-controls wrap">
              <button
                v-for="target in cdaTargets"
                :key="`cdat-${target.key}`"
                type="button"
                :class="{ active: cdaAssetTarget === target.key }"
                @click="setCdaAssetTarget(target.key)"
              >
                {{ target.label }}
              </button>
              <button
                v-for="side in cdaSides"
                :key="`cdaside-${side.key}`"
                type="button"
                :class="{ active: cdaAssetSide === side.key }"
                @click="setCdaAssetSide(side.key)"
              >
                {{ side.label }}
              </button>
            </div>
            <table class="ffl-global-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Ativo</th>
                  <th>Classe</th>
                  <th>Valor</th>
                  <th>Fundos</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in cdaAssetRows" :key="`cdaa-${item.rank}-${item.security_key}-${item.asset_class}`" :style="nportRowTint(cdaAssetSide === 'short' ? -item.selected_value : item.selected_value, cdaAssetMax)">
                  <td>{{ item.rank }}</td>
                  <td :title="`${item.issuer_name} | ${item.security_key}`">{{ item.asset_desc || item.issuer_name || item.security_key }}</td>
                  <td>{{ item.asset_class }}</td>
                  <td :style="nportCellTint(cdaAssetSide === 'short' ? -item.selected_value : item.selected_value, cdaAssetMax)">{{ fmtMoney(item.selected_value) }}</td>
                  <td>{{ fmtCount(item.fund_count) }}</td>
                </tr>
                <tr v-if="!cdaAssetRows.length">
                  <td colspan="5" class="ffl-empty-row">Sem ativos nesse recorte.</td>
                </tr>
              </tbody>
            </table>
            <div class="ffl-nport-pagination">
              <button type="button" :disabled="cdaAssetPage <= 1" @click="setCdaAssetPage(-1)">Anterior</button>
              <span>Pagina {{ cdaAssetPage }} / {{ totalPages(cdaAssets) }}</span>
              <button type="button" :disabled="cdaAssetPage >= totalPages(cdaAssets)" @click="setCdaAssetPage(1)">Proxima</button>
            </div>
          </div>
        </section>

        <section v-if="cdaPayload?.ok" class="ffl-global-split">
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Drilldown do fundo</span>
              <strong>{{ cdaSelectedFundName }}</strong>
            </div>
            <table class="ffl-global-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Ativo</th>
                  <th>Emissor</th>
                  <th>Classe</th>
                  <th>Valor</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in cdaHoldingRows" :key="`cdah-${item.rank}-${item.asset_code}-${item.asset_class}`">
                  <td>{{ item.rank }}</td>
                  <td :title="`${item.asset_code} | ${item.country}`">{{ item.asset_desc || item.asset_code }}</td>
                  <td>{{ item.issuer_name }}</td>
                  <td><span class="ffl-nport-pill country" :style="nportCountryPillStyle(item.asset_class)">{{ item.asset_class }}</span></td>
                  <td :class="moveClass(item.value_market)" :style="nportCellTint(item.value_market, cdaHoldingMax)">{{ fmtMoney(item.value_market) }}</td>
                </tr>
                <tr v-if="!cdaHoldingRows.length">
                  <td colspan="5" class="ffl-empty-row">Clique em um fundo acima para abrir a carteira reportada nesse recorte.</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Heatmap Brasil</span>
              <strong>tipo de fundo x classe de ativo</strong>
            </div>
            <div class="ffl-nport-heatmap" :style="cdaHeatmapStyle">
              <div class="ffl-heat-x"></div>
              <div v-for="asset in cdaHeatmap.x || []" :key="`cdahx-${asset}`" class="ffl-heat-x">{{ asset }}</div>
              <template v-for="row in cdaHeatmapRows" :key="`cdahy-${row.fund_type}`">
                <div class="ffl-heat-y country">{{ row.fund_type }}</div>
                <div
                  v-for="cell in row.cells"
                  :key="`cdahc-${cell.fund_type}-${cell.asset_class}`"
                  class="ffl-heat-cell country nport"
                  :style="{ background: flowHeatColor(cell.value, cdaHeatmapMax) }"
                  :title="cdaHeatTitle(cell)"
                >
                  {{ fmtMoney(cell.value) }}
                </div>
              </template>
            </div>
          </div>
        </section>

        <section v-if="cdaPayload?.ok" class="ffl-global-split">
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Fragilidade de carteira</span>
              <strong>concentracao x exterior/confidencial</strong>
            </div>
            <svg class="ffl-nport-scatter" viewBox="0 0 790 292" role="img">
              <line x1="42" y1="258" x2="748" y2="258" />
              <line x1="42" y1="28" x2="42" y2="258" />
              <text x="44" y="22">exterior + confidencial % PL</text>
              <text x="575" y="282">maior posicao % carteira</text>
              <circle
                v-for="point in cdaScatterPoints"
                :key="`cdasp-${point.fund_cnpj}`"
                :cx="point.x"
                :cy="point.y"
                :r="point.r"
                :fill="point.color"
                :opacity="0.62"
              >
                <title>{{ cdaScatterTitle(point) }}</title>
              </circle>
            </svg>
          </div>

          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Mosaico de classes</span>
              <strong>estoque reportado</strong>
            </div>
            <div class="ffl-nport-mosaic">
              <div
                v-for="tile in cdaClassTiles"
                :key="`cdatile-${tile.key}`"
                class="ffl-nport-tile"
                :style="tile.style"
                :title="tile.title"
              >
                <strong>{{ tile.label }}</strong>
                <span>{{ fmtCount(tile.fund_count) }} fundos | {{ fmtCount(tile.row_count) }} pos.</span>
                <em>{{ fmtMoney(tile.value) }}</em>
              </div>
            </div>
          </div>
        </section>

        <section v-if="cdaPayload?.ok" class="ffl-global-split">
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Maiores fundos</span>
              <strong>PL e composicao</strong>
            </div>
            <table class="ffl-global-table">
              <thead>
                <tr>
                  <th>Fundo</th>
                  <th>PL</th>
                  <th>Exterior</th>
                  <th>Cred. priv.</th>
                  <th>Confid.</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in cdaTopFunds.slice(0, 14)" :key="`cdatf-${item.fund_cnpj}`">
                  <td :title="item.fund_name">{{ item.fund_name || item.fund_cnpj }}</td>
                  <td>{{ fmtMoney(item.pl) }}</td>
                  <td>{{ fmtPctPlain(item.foreign_pct_pl) }}</td>
                  <td>{{ fmtPctPlain(item.private_credit_pct_pl) }}</td>
                  <td>{{ fmtPctPlain(item.confidential_pct_pl) }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Emissores mais presentes</span>
              <strong>crowding agregado</strong>
            </div>
            <table class="ffl-global-table">
              <thead>
                <tr>
                  <th>Emissor</th>
                  <th>Valor</th>
                  <th>Fundos</th>
                  <th>% base</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in cdaIssuerRows.slice(0, 14)" :key="`cdai-${item.key}`">
                  <td>{{ item.label || item.key }}</td>
                  <td>{{ fmtMoney(item.value) }}</td>
                  <td>{{ fmtCount(item.fund_count) }}</td>
                  <td>{{ fmtPctPlain(item.share_value_pct) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section v-if="cdaPayload?.ok" class="ffl-global-split">
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Leitura tecnica</span>
              <strong>payload auditavel</strong>
            </div>
            <ul class="ffl-nport-list">
              <li v-for="item in cdaInsights.quick_read || []" :key="item">{{ item }}</li>
              <li v-for="item in cdaInsights.risk_flags || []" :key="item">{{ item }}</li>
              <li v-for="item in cdaInsights.recommended_views || []" :key="item">{{ item }}</li>
            </ul>
          </div>

          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Lineage e logs</span>
              <strong>{{ cdaManifest.length }} arquivos</strong>
            </div>
            <table class="ffl-global-table">
              <thead>
                <tr>
                  <th>Arquivo</th>
                  <th>Bloco</th>
                  <th>Linhas</th>
                  <th>Tamanho</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in cdaManifest" :key="item.source_file">
                  <td>{{ item.source_file }}</td>
                  <td>{{ item.source_block }}</td>
                  <td>{{ fmtCount(item.row_count) }}</td>
                  <td>{{ fmtBytes(item.file_size_bytes) }}</td>
                </tr>
              </tbody>
            </table>
            <details class="ffl-source-logs nport">
              <summary>Logs recentes da ingestao</summary>
              <pre>{{ JSON.stringify(cdaLogs, null, 2) }}</pre>
            </details>
          </div>
        </section>
      </main>

</template>

<script>
import { injectFundsFlowContext } from '../context'
export default {
  name: 'FundsFlowCdaView',
  setup: injectFundsFlowContext,
}
</script>

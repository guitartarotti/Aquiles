<template>
        <section class="ffl-global-panel">
          <div class="ffl-section-head">
            <span>SEC N-PORT quarterly holdings</span>
            <strong>{{ nportReport.quarter || 'sem trimestre importado' }} | {{ fmtDate(nportReport.as_of_date) }}</strong>
          </div>
          <p>Base separada para holdings trimestrais de fundos registrados na SEC. Ela serve para crowding, concentracao, mapa geografico, emissor/security e risco de liquidez; nao e fluxo diario de mercado.</p>
          <div class="ffl-nport-actions">
            <button type="button" class="ffl-btn tiny" :disabled="nportLoading" @click="loadNportDashboard(true)">
              {{ nportLoading ? '...' : 'Recarregar' }}
            </button>
            <button type="button" class="ffl-btn tiny" :disabled="nportLoading" @click="ingestLocalNport">
              {{ nportLoading ? 'Importando...' : 'Ingerir pasta local' }}
            </button>
            <button type="button" class="ffl-btn tiny" :disabled="nportAnalyticsLoading" @click="loadNportAnalytics(true)">
              {{ nportAnalyticsLoading ? '...' : 'Atualizar analytics' }}
            </button>
            <span v-if="nportError" class="ffl-inline-error">{{ nportError }}</span>
          </div>
          <div v-if="nportLoading && !nportPayload" class="ffl-empty">Carregando N-PORT...</div>
          <div v-else-if="nportPayload?.ok" class="ffl-global-cards compact">
            <div v-for="card in nportCards" :key="card.key" class="ffl-global-card">
              <span>{{ card.label }}</span>
              <strong :class="card.tone">{{ card.value }}</strong>
              <em>{{ card.detail }}</em>
            </div>
          </div>
          <div v-else class="ffl-empty">
            Banco N-PORT ainda vazio. A importacao local usa o pacote em Downloads e depois materializa o dashboard.
          </div>
        </section>

        <section v-if="nportPayload?.ok" class="ffl-global-split">
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Fundos mais bem performados</span>
              <strong>{{ nportPerformance?.quarter || nportReport.quarter }} | {{ nportPerformance?.total || 0 }} fundos</strong>
            </div>
            <div class="ffl-nport-controls">
              <button type="button" :class="{ active: !nportPerfWeighted }" @click="toggleNportWeighted">Retorno 3m</button>
              <button type="button" :class="{ active: nportPerfWeighted }" @click="toggleNportWeighted">Ponderar AUM</button>
              <span>score: {{ nportPerfWeighted ? 'retorno x AUM' : 'retorno percentual' }}</span>
            </div>
            <table class="ffl-global-table nport-clickable">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Fundo</th>
                  <th>AUM</th>
                  <th>Ret. 3m</th>
                  <th>Score</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in nportPerformanceRows" :key="`npp-${item.accession_number}`" :style="nportRowTint(item.return_3m_pct, 240)">
                  <td>{{ item.rank }}</td>
                  <td :title="item.series_name">{{ item.series_name || item.accession_number }}</td>
                  <td>{{ fmtUsd(item.net_assets) }}</td>
                  <td :class="moveClass(item.return_3m_pct)" :style="nportCellTint(item.return_3m_pct, 120)">{{ fmtPctPlain(item.return_3m_pct) }}</td>
                  <td :style="nportCellTint(nportPerfWeighted ? item.score : item.return_3m_pct, nportPerfWeighted ? 50_000_000_000 : 120)">{{ nportPerfWeighted ? fmtUsd(item.score) : fmtPctPlain(item.score) }}</td>
                </tr>
                <tr v-if="!nportPerformanceRows.length">
                  <td colspan="5" class="ffl-empty-row">{{ nportAnalyticsLoading ? 'Carregando...' : 'Sem dados de performance.' }}</td>
                </tr>
              </tbody>
            </table>
            <div class="ffl-nport-pagination">
              <button type="button" :disabled="nportPerfPage <= 1" @click="setNportPerfPage(-1)">Anterior</button>
              <span>Pagina {{ nportPerfPage }} / {{ totalPages(nportPerformance) }}</span>
              <button type="button" :disabled="nportPerfPage >= totalPages(nportPerformance)" @click="setNportPerfPage(1)">Proxima</button>
            </div>
          </div>

          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Fundos por exposicao</span>
              <strong>{{ nportTargetLabel(nportExposureTarget) }} | {{ nportSideLabel(nportExposureSide) }}</strong>
            </div>
            <div class="ffl-nport-controls wrap">
              <button
                v-for="target in nportTargets"
                :key="`npet-${target.key}`"
                type="button"
                :class="{ active: nportExposureTarget === target.key }"
                @click="setNportExposureTarget(target.key)"
              >
                {{ target.label }}
              </button>
              <button
                v-for="side in nportSides"
                :key="`npes-${side.key}`"
                type="button"
                :class="{ active: nportExposureSide === side.key }"
                @click="setNportExposureSide(side.key)"
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
                  <th>% AUM</th>
                  <th>Ret. 3m</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="item in nportRegionFundRows"
                  :key="`nprf-${item.accession_number}`"
                  :class="{ active: nportSelectedFund?.accession_number === item.accession_number }"
                  :style="nportRowTint(nportExposureSide === 'short' ? -item.selected_value : item.selected_value, 8_000_000_000)"
                  @click="selectNportFund(item)"
                >
                  <td>{{ item.rank }}</td>
                  <td :title="`${item.series_name} | ${item.registrant_name}`">{{ item.series_name || item.accession_number }}</td>
                  <td :style="nportCellTint(nportExposureSide === 'short' ? -item.selected_value : item.selected_value, 8_000_000_000)">{{ fmtUsd(item.selected_value) }}</td>
                  <td :style="nportCellTint(nportExposureSide === 'short' ? -item.short_pct_aum : item.long_pct_aum, 8)">{{ fmtPctPlain(nportExposureSide === 'short' ? item.short_pct_aum : item.long_pct_aum) }}</td>
                  <td :class="moveClass(item.return_3m_pct)">{{ fmtPctPlain(item.return_3m_pct) }}</td>
                </tr>
                <tr v-if="!nportRegionFundRows.length">
                  <td colspan="5" class="ffl-empty-row">{{ nportAnalyticsLoading ? 'Carregando...' : 'Sem fundos nesse recorte.' }}</td>
                </tr>
              </tbody>
            </table>
            <div class="ffl-nport-pagination">
              <button type="button" :disabled="nportExposurePage <= 1" @click="setNportExposurePage(-1)">Anterior</button>
              <span>Pagina {{ nportExposurePage }} / {{ totalPages(nportRegionFunds) }}</span>
              <button type="button" :disabled="nportExposurePage >= totalPages(nportRegionFunds)" @click="setNportExposurePage(1)">Proxima</button>
            </div>
          </div>
        </section>

        <section v-if="nportPayload?.ok" class="ffl-global-split">
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Drilldown do fundo</span>
              <strong>{{ nportSelectedFundName }}</strong>
            </div>
            <table class="ffl-global-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Ativo</th>
                  <th>Pais</th>
                  <th>Side</th>
                  <th>Valor</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in nportHoldingRows" :key="`nph-${item.holding_id}`">
                  <td>{{ item.rank }}</td>
                  <td :title="`${item.issuer_name} | ${item.security_key}`">{{ item.issuer_title || item.issuer_name || item.security_key }}</td>
                  <td><span class="ffl-nport-pill country" :style="nportCountryPillStyle(item.investment_country)">{{ item.investment_country }}</span></td>
                  <td><span class="ffl-nport-pill" :class="item.position_side">{{ item.position_side }}</span></td>
                  <td :class="moveClass(item.currency_value)" :style="nportCellTint(item.position_side === 'short' ? -Math.abs(item.currency_value) : item.currency_value, 3_000_000_000)">{{ fmtUsd(item.currency_value) }}</td>
                </tr>
                <tr v-if="!nportHoldingRows.length">
                  <td colspan="5" class="ffl-empty-row">Clique em um fundo acima para abrir os ativos comprados ou shorteados.</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Ativos mais comprados / shorteados</span>
              <strong>{{ nportTargetLabel(nportAssetTarget) }} | {{ nportSideLabel(nportAssetSide) }}</strong>
            </div>
            <div class="ffl-nport-controls wrap">
              <button
                v-for="target in nportTargets"
                :key="`npat-${target.key}`"
                type="button"
                :class="{ active: nportAssetTarget === target.key }"
                @click="setNportAssetTarget(target.key)"
              >
                {{ target.label }}
              </button>
              <button
                v-for="side in nportSides"
                :key="`npas-${side.key}`"
                type="button"
                :class="{ active: nportAssetSide === side.key }"
                @click="setNportAssetSide(side.key)"
              >
                {{ side.label }}
              </button>
            </div>
            <table class="ffl-global-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Ativo</th>
                  <th>Pais</th>
                  <th>Valor</th>
                  <th>Fundos</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in nportRegionAssetRows" :key="`npae-${item.rank}-${item.security_key}-${item.asset_cat}`" :style="nportRowTint(nportAssetSide === 'short' ? -item.selected_value : item.selected_value, 700_000_000)">
                  <td>{{ item.rank }}</td>
                  <td :title="`${item.issuer_name} | ${item.security_key}`">{{ item.issuer_title || item.issuer_name || item.security_key }}</td>
                  <td><span class="ffl-nport-pill country" :style="nportCountryPillStyle(item.investment_country)">{{ item.investment_country }}</span></td>
                  <td :style="nportCellTint(nportAssetSide === 'short' ? -item.selected_value : item.selected_value, 700_000_000)">{{ fmtUsd(item.selected_value) }}</td>
                  <td>{{ fmtCount(item.fund_count) }}</td>
                </tr>
                <tr v-if="!nportRegionAssetRows.length">
                  <td colspan="5" class="ffl-empty-row">Sem ativos nesse recorte.</td>
                </tr>
              </tbody>
            </table>
            <div class="ffl-nport-pagination">
              <button type="button" :disabled="nportAssetPage <= 1" @click="setNportAssetPage(-1)">Anterior</button>
              <span>Pagina {{ nportAssetPage }} / {{ totalPages(nportRegionAssets) }}</span>
              <button type="button" :disabled="nportAssetPage >= totalPages(nportRegionAssets)" @click="setNportAssetPage(1)">Proxima</button>
            </div>
          </div>
        </section>

        <section v-if="nportPayload?.ok" class="ffl-global-panel">
          <div class="ffl-section-head compact">
            <span>Heatmap Emergentes</span>
            <strong>net long/short por pais x classe</strong>
          </div>
          <div class="ffl-nport-heatmap" :style="nportHeatmapStyle">
            <div class="ffl-heat-x"></div>
            <div v-for="asset in nportHeatmap.x || []" :key="`nphx-${asset}`" class="ffl-heat-x">{{ asset }}</div>
            <template v-for="row in nportHeatmapRows" :key="`nphy-${row.country}`">
              <div class="ffl-heat-y country">{{ row.country }}</div>
              <div
                v-for="cell in row.cells"
                :key="`nphc-${cell.country}-${cell.asset_cat}`"
                class="ffl-heat-cell country nport"
                :style="{ background: flowHeatColor(cell.net_value, nportHeatmapMax) }"
                :title="nportHeatTitle(cell)"
              >
                {{ fmtUsd(cell.net_value) }}
              </div>
            </template>
          </div>
        </section>

        <section v-if="nportPayload?.ok" class="ffl-global-split">
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Constelacao EM</span>
              <strong>gross, net/gross e intensidade short</strong>
            </div>
            <svg class="ffl-nport-constellation" viewBox="0 0 790 330" role="img">
              <circle cx="395" cy="165" r="118" class="orbit" />
              <circle cx="395" cy="165" r="72" class="orbit inner" />
              <line x1="395" y1="34" x2="395" y2="296" />
              <line x1="264" y1="165" x2="526" y2="165" />
              <text x="28" y="24">Pais mais distante = maior gross EM; verde/vermelho = net comprador/vendedor</text>
              <g v-for="point in nportCountryOrbitPoints" :key="`npco-${point.investment_country}`">
                <line x1="395" y1="165" :x2="point.x" :y2="point.y" class="ray" :opacity="point.opacity" />
                <circle :cx="point.x" :cy="point.y" :r="point.r" :fill="point.color" :opacity="0.82">
                  <title>{{ nportCountryOrbitTitle(point) }}</title>
                </circle>
                <text :x="point.labelX" :y="point.labelY" :text-anchor="point.anchor">{{ point.investment_country }}</text>
              </g>
            </svg>
          </div>

          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Barbell long/short</span>
              <strong>assimetria de paises emergentes</strong>
            </div>
            <div class="ffl-nport-barbell">
              <div v-for="item in nportCountryBarbellRows" :key="`npbb-${item.investment_country}`" class="ffl-nport-barbell-row">
                <span><i :style="nportCountryPillStyle(item.investment_country)"></i>{{ item.investment_country }}</span>
                <div class="ffl-nport-barbell-track">
                  <b class="short" :style="{ width: `${item.shortWidth}%` }"></b>
                  <b class="long" :style="{ width: `${item.longWidth}%` }"></b>
                </div>
                <strong :class="moveClass(item.net_to_gross_pct)">{{ fmtPctPlain(item.net_to_gross_pct) }}</strong>
              </div>
            </div>
          </div>
        </section>

        <section v-if="nportPayload?.ok" class="ffl-global-split">
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Mosaico de crowding</span>
              <strong>ativos EM por valor e side selecionado</strong>
            </div>
            <div class="ffl-nport-mosaic">
              <div
                v-for="tile in nportCrowdingTiles"
                :key="`npm-${tile.security_key}-${tile.asset_cat}-${tile.rank}`"
                class="ffl-nport-tile"
                :style="tile.style"
                :title="tile.title"
              >
                <strong>{{ tile.label }}</strong>
                <span>{{ tile.investment_country }} | {{ tile.asset_cat }}</span>
                <em>{{ fmtUsd(tile.selected_value) }}</em>
              </div>
            </div>
          </div>

          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Ridge de retorno x EM</span>
              <strong>fundos com score latente</strong>
            </div>
            <div class="ffl-nport-ridge">
              <div v-for="item in nportRidgeRows" :key="`npridge-${item.accession_number}`" class="ffl-nport-ridge-row">
                <span :title="item.series_name">{{ item.series_name || item.accession_number }}</span>
                <div class="ffl-nport-ridge-track">
                  <i class="exposure" :style="{ width: `${item.exposureWidth}%` }"></i>
                  <i class="return" :style="{ width: `${item.returnWidth}%` }"></i>
                </div>
                <strong>{{ fmtPctPlain(item.return_3m_pct) }}</strong>
              </div>
            </div>
          </div>
        </section>

</template>

<script>
import { injectFundsFlowContext } from '../context'
export default {
  name: 'FundsFlowNportOverviewSection',
  setup: injectFundsFlowContext,
}
</script>

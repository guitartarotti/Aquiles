<template>
      <main class="ffl-global-view">
        <section class="ffl-global-split top">
          <div class="ffl-global-panel ffl-global-chart-panel">
            <div class="ffl-section-head compact">
              <span>ICI Global Fund Flows</span>
              <strong>{{ globalStatus }} | US$ bi</strong>
            </div>
            <p>{{ insights.brazil_vs_global_comment }}</p>
            <div class="ffl-global-meta">
              <span>Weekly {{ fmtDate(iciLatestDate) }}</span>
              <span>ETF assets {{ iciMonthlyEtf.reference_month || '-' }}</span>
              <span>Worldwide {{ iciWorldwide.quarter || '-' }}</span>
            </div>
            <div v-if="iciLatestCards.length" class="ffl-global-cards compact">
              <div v-for="card in iciLatestCards" :key="card.key" class="ffl-global-card">
                <span>{{ card.label }}</span>
                <strong :class="moveClass(card.value)">{{ fmtUsdMn(card.value) }}</strong>
                <em>{{ fmtPeriodDate(card.date) }}</em>
              </div>
            </div>
            <div class="ffl-series-picker">
              <button
                v-for="option in iciSeriesOptions"
                :key="option.key"
                type="button"
                :class="{ active: selectedIciSeries.includes(option.key) }"
                @click="toggleIciSeries(option.key)"
              >
                {{ option.label }}
              </button>
            </div>
            <svg class="ffl-line-chart global" viewBox="0 0 760 260" preserveAspectRatio="none" aria-hidden="true">
              <line v-for="y in gridLines" :key="`ig${y}`" x1="42" x2="744" :y1="y" :y2="y" class="ffl-grid" />
              <line x1="42" x2="744" y1="218" y2="218" class="ffl-axis" />
              <path
                v-for="series in iciChartSeries"
                :key="series.name"
                :d="linePath(series.points)"
                class="ffl-line"
                :style="{ stroke: series.color }"
              />
              <circle
                v-for="point in iciChartLastPoints"
                :key="`${point.name}-${point.x}`"
                :cx="point.x"
                :cy="point.y"
                r="3.2"
                class="ffl-dot"
                :style="{ fill: point.color }"
              />
            </svg>
            <div class="ffl-legend">
              <span v-for="series in iciChartSeries" :key="series.name">
                <i :style="{ background: series.color }"></i>{{ series.name }}
              </span>
            </div>
          </div>

          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Weekly flows por veiculo e segmento</span>
              <strong>{{ fmtDate(iciLatestDate) }}</strong>
            </div>
            <table class="ffl-global-table">
              <thead>
                <tr>
                  <th>Veiculo</th>
                  <th>Segmento</th>
                  <th>Grupo</th>
                  <th>Fluxo</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in iciLatestWeeklyRows" :key="`ici-latest-${item.vehicle}-${item.category_key}`">
                  <td>{{ item.vehicle_label }}</td>
                  <td>{{ item.category }}</td>
                  <td>{{ item.category_group }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.flow_usd_mn)">{{ fmtUsdMn(item.flow_usd_mn) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="ffl-global-panel">
          <div class="ffl-section-head">
            <span>ETF assets por segmento</span>
            <strong>{{ iciMonthlyEtf.reference_month }}</strong>
          </div>
          <table class="ffl-global-table">
            <thead>
              <tr>
                <th>Segmento</th>
                <th>AUM</th>
                <th>Fundos</th>
                <th>YoY AUM</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in iciMonthlyEtfRows" :key="`ici-month-${item.segment_key}`">
                <td>{{ item.segment }}</td>
                <td>{{ fmtUsdMn(item.assets_usd_mn) }}</td>
                <td>{{ fmtCount(item.fund_count) }}</td>
                <td :class="moveClass((item.assets_usd_mn || 0) - (item.year_ago_assets_usd_mn || 0))">
                  {{ fmtUsdMn((item.assets_usd_mn || 0) - (item.year_ago_assets_usd_mn || 0)) }}
                </td>
              </tr>
            </tbody>
          </table>
        </section>

        <section class="ffl-global-panel">
          <div class="ffl-section-head">
            <span>Heatmap trimestral por pais</span>
            <strong>{{ iciWorldwide.quarter }} | net sales</strong>
          </div>
          <div class="ffl-country-heatmap" :style="iciCountryHeatmapStyle">
            <div class="ffl-heat-corner"></div>
            <div v-for="column in iciCountryHeatmapColumns" :key="`ich-${column.key}`" class="ffl-heat-x">{{ column.label }}</div>
            <template v-for="row in iciCountryHeatmapRows" :key="`country-heat-${row.country}`">
              <div class="ffl-heat-y country">{{ row.country }}</div>
              <div
                v-for="cell in row.cells"
                :key="`${row.country}-${cell.key}`"
                class="ffl-heat-cell country"
                :style="{ background: flowHeatColor(cell.value, iciCountryHeatmapMax) }"
                :title="iciHeatTitle(row, cell)"
              >
                {{ fmtUsdMn(cell.value) }}
              </div>
            </template>
          </div>
        </section>

        <section class="ffl-global-split flow-lists">
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Regioes com inflow</span>
              <strong>{{ iciRegionInflows.length }} regioes | {{ iciWorldwide.quarter }}</strong>
            </div>
            <table class="ffl-global-table flow-list">
              <thead>
                <tr>
                  <th>Regiao</th>
                  <th>Total</th>
                  <th>Equity</th>
                  <th>Bond</th>
                  <th>Money</th>
                  <th>ETF</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="!iciRegionInflows.length">
                  <td colspan="6" class="ffl-empty-row">Sem regioes com inflow no periodo.</td>
                </tr>
                <tr v-for="item in iciRegionInflows" :key="`ici-region-in-${item.region}`">
                  <td>{{ item.region }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.net_sales_total_usd_mn)">{{ fmtUsdMn(item.net_sales_total_usd_mn) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.net_sales_equity_usd_mn)">{{ fmtUsdMn(item.net_sales_equity_usd_mn) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.net_sales_bond_usd_mn)">{{ fmtUsdMn(item.net_sales_bond_usd_mn) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.net_sales_money_market_usd_mn)">{{ fmtUsdMn(item.net_sales_money_market_usd_mn) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.net_sales_etfs_usd_mn)">{{ fmtUsdMn(item.net_sales_etfs_usd_mn) }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Regioes com outflow</span>
              <strong>{{ iciRegionOutflows.length }} regioes | {{ iciWorldwide.quarter }}</strong>
            </div>
            <table class="ffl-global-table flow-list">
              <thead>
                <tr>
                  <th>Regiao</th>
                  <th>Total</th>
                  <th>Equity</th>
                  <th>Bond</th>
                  <th>Money</th>
                  <th>ETF</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="!iciRegionOutflows.length">
                  <td colspan="6" class="ffl-empty-row">Sem regioes com outflow no periodo.</td>
                </tr>
                <tr v-for="item in iciRegionOutflows" :key="`ici-region-out-${item.region}`">
                  <td>{{ item.region }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.net_sales_total_usd_mn)">{{ fmtUsdMn(item.net_sales_total_usd_mn) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.net_sales_equity_usd_mn)">{{ fmtUsdMn(item.net_sales_equity_usd_mn) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.net_sales_bond_usd_mn)">{{ fmtUsdMn(item.net_sales_bond_usd_mn) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.net_sales_money_market_usd_mn)">{{ fmtUsdMn(item.net_sales_money_market_usd_mn) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.net_sales_etfs_usd_mn)">{{ fmtUsdMn(item.net_sales_etfs_usd_mn) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="ffl-global-split flow-lists countries">
          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Paises com inflow</span>
              <strong>{{ iciCountryInflows.length }} paises | {{ iciWorldwide.quarter }}</strong>
            </div>
            <table class="ffl-global-table flow-list countries">
              <thead>
                <tr>
                  <th>Pais</th>
                  <th>Regiao</th>
                  <th>Total</th>
                  <th>Equity</th>
                  <th>Bond</th>
                  <th>Money</th>
                  <th>ETF</th>
                  <th>Fundos</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="!iciCountryInflows.length">
                  <td colspan="8" class="ffl-empty-row">Sem paises com inflow no periodo.</td>
                </tr>
                <tr v-for="item in iciCountryInflows" :key="`ici-country-in-${item.country}`">
                  <td>{{ item.country }}</td>
                  <td>{{ item.region }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.net_sales_total_usd_mn)">{{ fmtUsdMn(item.net_sales_total_usd_mn) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.net_sales_equity_usd_mn)">{{ fmtUsdMn(item.net_sales_equity_usd_mn) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.net_sales_bond_usd_mn)">{{ fmtUsdMn(item.net_sales_bond_usd_mn) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.net_sales_money_market_usd_mn)">{{ fmtUsdMn(item.net_sales_money_market_usd_mn) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.net_sales_etfs_usd_mn)">{{ fmtUsdMn(item.net_sales_etfs_usd_mn) }}</td>
                  <td>{{ fmtCount(item.fund_count_total_count) }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Paises com outflow</span>
              <strong>{{ iciCountryOutflows.length }} paises | {{ iciWorldwide.quarter }}</strong>
            </div>
            <table class="ffl-global-table flow-list countries">
              <thead>
                <tr>
                  <th>Pais</th>
                  <th>Regiao</th>
                  <th>Total</th>
                  <th>Equity</th>
                  <th>Bond</th>
                  <th>Money</th>
                  <th>ETF</th>
                  <th>Fundos</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="!iciCountryOutflows.length">
                  <td colspan="8" class="ffl-empty-row">Sem paises com outflow no periodo.</td>
                </tr>
                <tr v-for="item in iciCountryOutflows" :key="`ici-country-out-${item.country}`">
                  <td>{{ item.country }}</td>
                  <td>{{ item.region }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.net_sales_total_usd_mn)">{{ fmtUsdMn(item.net_sales_total_usd_mn) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.net_sales_equity_usd_mn)">{{ fmtUsdMn(item.net_sales_equity_usd_mn) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.net_sales_bond_usd_mn)">{{ fmtUsdMn(item.net_sales_bond_usd_mn) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.net_sales_money_market_usd_mn)">{{ fmtUsdMn(item.net_sales_money_market_usd_mn) }}</td>
                  <td class="ffl-flow-value" :class="moveClass(item.net_sales_etfs_usd_mn)">{{ fmtUsdMn(item.net_sales_etfs_usd_mn) }}</td>
                  <td>{{ fmtCount(item.fund_count_total_count) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="ffl-global-panel">
          <div class="ffl-section-head">
            <span>Paises capturados</span>
            <strong>{{ iciCountryRows.length }} paises | {{ iciWorldwide.quarter }}</strong>
          </div>
          <table class="ffl-global-table countries">
            <thead>
              <tr>
                <th>Pais</th>
                <th>Regiao</th>
                <th>Net sales</th>
                <th>ETF sales</th>
                <th>AUM total</th>
                <th>AUM ETF</th>
                <th>Fundos</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in iciCountryRows" :key="`ici-country-row-${item.country}`">
                <td>{{ item.country }}</td>
                <td>{{ item.region }}</td>
                <td class="ffl-flow-value" :class="moveClass(item.net_sales_total_usd_mn)">{{ fmtUsdMn(item.net_sales_total_usd_mn) }}</td>
                <td class="ffl-flow-value" :class="moveClass(item.net_sales_etfs_usd_mn)">{{ fmtUsdMn(item.net_sales_etfs_usd_mn) }}</td>
                <td>{{ fmtUsdMn(item.assets_total_usd_mn) }}</td>
                <td>{{ fmtUsdMn(item.assets_etfs_usd_mn) }}</td>
                <td>{{ fmtCount(item.fund_count_total_count) }}</td>
              </tr>
            </tbody>
          </table>
        </section>
      </main>

</template>

<script>
import { injectFundsFlowContext } from '../context'
export default {
  name: 'FundsFlowGlobalView',
  setup: injectFundsFlowContext,
}
</script>

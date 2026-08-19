<template>
  <div class="ffl-root">
    <div class="ffl-toolbar">
      <div class="ffl-tabs" role="tablist">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          type="button"
          class="ffl-tab"
          :class="{ active: activeTab === tab.key }"
          @click="selectTab(tab.key)"
        >
          {{ tab.label }}
        </button>
      </div>
      <div class="ffl-spacer"></div>
      <select v-model="period" class="ffl-select" @change="refresh(false)">
        <option value="21d">21d</option>
        <option value="63d">63d</option>
        <option value="ytd">YTD</option>
      </select>
      <select v-model="metric" class="ffl-select">
        <option value="nominal">R$</option>
        <option value="pct_pl">% PL</option>
        <option value="zscore">Z</option>
      </select>
      <span class="ffl-state" :class="{ ok: payload?.ok, error: Boolean(error) }">{{ statusLabel }}</span>
      <button type="button" class="ffl-btn" :disabled="loading || collecting" @click="refresh(true)">
        {{ loading || collecting ? '...' : 'Atualizar' }}
      </button>
    </div>

    <div v-if="loading && !payload" class="ffl-empty">Carregando Funds Flow Local...</div>
    <div v-else-if="error && !payload" class="ffl-empty error">{{ error }}</div>

    <template v-else-if="payload">
      <header v-if="activeTab !== 'graph'" class="ffl-header">
        <div>
          <h3>Funds Flow Local</h3>
          <p>Dados ate {{ fmtDate(report.as_of_date) }} | Fonte primaria: {{ report.primary_source || 'CVM Informe Diario' }}</p>
        </div>
        <div class="ffl-regime" :class="regimeClass(kpis.regime)">
          <span>Regime</span>
          <strong>{{ regimeLabel(kpis.regime) }}</strong>
        </div>
      </header>

      <section v-if="activeTab !== 'graph'" class="ffl-kpis">
        <div v-for="card in kpiCards" :key="card.key" class="ffl-kpi">
          <span>{{ card.label }}</span>
          <strong :class="moveClass(card.raw)">{{ card.value }}</strong>
        </div>
      </section>

      <main v-if="activeTab === 'overview'" class="ffl-overview">
        <section class="ffl-chart-panel">
          <div class="ffl-section-head">
            <span>Fluxo acumulado por classe</span>
            <strong>{{ metricLabel }}</strong>
          </div>
          <svg class="ffl-line-chart" viewBox="0 0 760 260" preserveAspectRatio="none" aria-hidden="true">
            <line v-for="y in gridLines" :key="`g${y}`" x1="42" x2="744" :y1="y" :y2="y" class="ffl-grid" />
            <line x1="42" x2="744" y1="218" y2="218" class="ffl-axis" />
            <path
              v-for="series in chartSeries"
              :key="series.name"
              :d="linePath(series.points)"
              class="ffl-line"
              :style="{ stroke: series.color }"
            />
            <circle
              v-for="point in chartLastPoints"
              :key="`${point.name}-${point.x}`"
              :cx="point.x"
              :cy="point.y"
              r="3.2"
              class="ffl-dot"
              :style="{ fill: point.color }"
            />
          </svg>
          <div class="ffl-legend">
            <span v-for="series in chartSeries" :key="series.name">
              <i :style="{ background: series.color }"></i>{{ series.name }}
            </span>
          </div>
        </section>

        <aside class="ffl-rankings">
          <div class="ffl-rank-toolbar">
            <span>Janela</span>
            <div class="ffl-rank-switch">
              <button
                v-for="option in rankingWindowOptions"
                :key="option.value"
                type="button"
                class="ffl-rank-switch-btn"
                :class="{ active: rankingWindow === option.value }"
                @click="rankingWindow = option.value"
              >
                {{ option.label }}
              </button>
            </div>
          </div>
          <div class="ffl-rank-box">
            <div class="ffl-section-head">
              <span>Top entradas</span>
              <strong>{{ rankingWindowLabel }}</strong>
            </div>
            <div v-for="item in overviewTopInflows" :key="`in-${item.name}`" class="ffl-rank-row">
              <span>{{ item.rank }}. {{ item.name }}</span>
              <strong :class="moveClass(item.displayFlow)">{{ fmtMoney(item.displayFlow) }}</strong>
            </div>
          </div>
          <div class="ffl-rank-box">
            <div class="ffl-section-head">
              <span>Top saidas</span>
              <strong>{{ rankingWindowLabel }}</strong>
            </div>
            <div v-for="item in overviewTopOutflows" :key="`out-${item.name}`" class="ffl-rank-row">
              <span>{{ item.rank }}. {{ item.name }}</span>
              <strong :class="moveClass(item.displayFlow)">{{ fmtMoney(item.displayFlow) }}</strong>
            </div>
          </div>
        </aside>

        <section v-if="b3OiMainSummary.length || b3ParticipantBars.length" class="ffl-overview-b3">
          <div class="ffl-b3-mini-panel">
            <div class="ffl-section-head compact">
              <span>OI futuros B3</span>
              <strong>OI do dia | var d/d</strong>
            </div>
            <div class="ffl-diverging-list">
              <div v-for="item in b3OiOverviewRows" :key="`oi-${item.asset}`" class="ffl-diverging-row">
                <span>{{ item.asset }}</span>
                <div class="ffl-diverging-track">
                  <i :class="moveClass(item.variation_open_interest)" :style="divergingBarStyle(item.variation_open_interest, oiOverviewBarMax)"></i>
                </div>
                <div class="ffl-diverging-metric">
                  <strong>{{ fmtCount(item.open_interest) }}</strong>
                  <em :class="moveClass(item.variation_open_interest)">{{ signedCount(item.variation_open_interest) }} d/d</em>
                </div>
              </div>
            </div>
          </div>
          <div class="ffl-b3-mini-panel">
            <div class="ffl-section-head compact">
              <span>Participantes B3</span>
              <strong>fluxo do dia</strong>
            </div>
            <div class="ffl-diverging-list">
              <div v-for="item in b3ParticipantOverviewRows" :key="`part-${item.participant_type}`" class="ffl-diverging-row participant">
                <span>{{ item.participant_type }}</span>
                <div class="ffl-diverging-track">
                  <i :class="moveClass(item.daily_net_flow_brl)" :style="divergingBarStyle(item.daily_net_flow_brl, participantOverviewBarMax)"></i>
                </div>
                <div class="ffl-diverging-metric">
                  <strong :class="moveClass(item.daily_net_flow_brl)">{{ fmtMoney(item.daily_net_flow_brl) }}</strong>
                  <em :class="moveClass(item.net_flow_brl_mtd)">{{ fmtMoney(item.net_flow_brl_mtd) }} MTD</em>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section class="ffl-insights">
          <div class="ffl-section-head"><span>Leitura automatica</span><strong>{{ insights.agent || 'FundsFlowInsightAgent' }}</strong></div>
          <ul>
            <li v-for="item in insights.quick_read || []" :key="item">{{ item }}</li>
          </ul>
          <p>{{ insights.diagnosis }}</p>
        </section>
      </main>

      <main v-else-if="activeTab === 'b3'" class="ffl-b3-view">
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

      <main v-else-if="activeTab === 'etf'" class="ffl-etf-view">
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

      <main v-else-if="activeTab === 'map'" class="ffl-map-view">
        <section class="ffl-heatmap-panel">
          <div class="ffl-section-head"><span>Mapa de fluxo</span><strong>{{ heatmap.metric || 'flow_zscore_21d' }}</strong></div>
          <div class="ffl-heatmap" :style="heatmapStyle">
            <div class="ffl-heat-corner"></div>
            <div v-for="x in heatmap.x || []" :key="`hx-${x}`" class="ffl-heat-x">{{ shortDate(x) }}</div>
            <template v-for="row in heatmapRows" :key="row.name">
              <div class="ffl-heat-y">{{ row.name }}</div>
              <div
                v-for="cell in row.cells"
                :key="`${row.name}-${cell.date}`"
                class="ffl-heat-cell"
                :style="{ background: heatColor(cell.value) }"
                :title="heatTitle(cell)"
              ></div>
            </template>
          </div>
        </section>
        <section class="ffl-table-panel">
          <div class="ffl-section-head"><span>Ranking por classe</span></div>
          <table>
            <thead>
              <tr>
                <th>Classe</th>
                <th>21d</th>
                <th>% PL</th>
                <th>Z</th>
                <th>PL</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in classRanking" :key="item.name">
                <td>{{ item.name }}</td>
                <td :class="moveClass(item.net_flow_21d)">{{ fmtMoney(item.net_flow_21d) }}</td>
                <td>{{ fmtPct(item.flow_pct_pl_21d) }}</td>
                <td>{{ fmtNum(item.zscore_21d, 2) }}</td>
                <td>{{ fmtMoney(item.aum) }}</td>
              </tr>
            </tbody>
          </table>
        </section>
      </main>

      <main v-else-if="activeTab === 'stress'" class="ffl-stress-view">
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

      <main v-else-if="activeTab === 'anbima'" class="ffl-anbima-view">
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

      <main v-else-if="activeTab === 'global'" class="ffl-global-view">
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

      <main v-else-if="activeTab === 'cftc'" class="ffl-cftc-view">
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

      <main v-else-if="activeTab === 'nport'" class="ffl-nport-view">
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
      </main>

      <main v-else-if="activeTab === 'cda'" class="ffl-cda-view">
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

      <main v-else-if="activeTab === 'radar_cda'" class="ffl-cda-radar-view">
        <section class="ffl-global-panel">
          <div class="ffl-section-head">
            <span>Radar CDA</span>
            <strong>{{ cdaRadarReport.period_label || 'CDA' }} -> {{ fmtDate(cdaRadarReport.flow_as_of_date) }}</strong>
          </div>
          <div class="ffl-global-subhead">
            <span>Estoque mensal do CDA reescalado pelo PL mais recente e confrontado com resgates brutos do Informe Diario.</span>
            <div class="ffl-inline-actions">
              <button type="button" class="ffl-btn tiny" :disabled="cdaRadarLoading" @click="loadCdaRadar(false)">
                {{ cdaRadarLoading ? 'Carregando...' : 'Recarregar' }}
              </button>
              <span v-if="cdaRadarError" class="ffl-inline-error">{{ cdaRadarError }}</span>
            </div>
          </div>
          <div v-if="cdaRadarLoading && !cdaRadarPayload" class="ffl-empty">Carregando Radar CDA...</div>
          <div v-else-if="cdaRadarPayload?.ok" class="ffl-global-cards compact">
            <div v-for="card in cdaRadarCards" :key="card.key" class="ffl-global-card">
              <span>{{ card.label }}</span>
              <strong :class="card.tone || 'flat'">{{ card.value }}</strong>
              <em>{{ card.detail }}</em>
            </div>
          </div>
        </section>

        <section v-if="cdaRadarPayload?.ok" class="ffl-global-panel">
          <div class="ffl-section-head compact">
            <span>Cenarios</span>
            <strong>{{ cdaRadarScenarioActive.label || 'Stress' }}</strong>
          </div>
          <div class="ffl-radar-toolbar">
            <div class="ffl-asset-tabs">
              <button
                v-for="scenario in cdaRadarScenarios"
                :key="`radar-scenario-${scenario.key}`"
                type="button"
                :class="{ active: cdaRadarScenario === scenario.key }"
                @click="cdaRadarScenario = scenario.key"
              >
                {{ scenario.label }}
              </button>
            </div>
            <select v-model="cdaRadarMacroFilter" class="ffl-select">
              <option v-for="option in cdaRadarMacroOptions" :key="`radar-class-${option.key}`" :value="option.key">
                {{ option.label }}
              </option>
            </select>
          </div>
          <p class="ffl-method-note">
            {{ cdaRadarScenarioActive.description }}
            Cobertura atual: {{ fmtPctPlain(Number(cdaRadarCoverage.matched_cda_pl_pct || 0) * 100) }}
            do PL CDA com match no fluxo diario; periodo comum:
            {{ fmtCount(cdaRadarSummary.redemption_period_days || cdaRadarCoverage.days_since_cda) }} dias.
          </p>
        </section>

        <section v-if="cdaRadarPayload?.ok" class="ffl-global-split">
          <section class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Mapa de exaustao</span>
              <strong>tipo de fundo x tipo de ativo</strong>
            </div>
            <div class="ffl-nport-heatmap ffl-radar-heatmap" :style="cdaRadarHeatmapStyle">
              <div class="ffl-heat-corner">Tipo</div>
              <div v-for="bucket in cdaRadarHeatmap.x || []" :key="`radarx-${bucket}`" class="ffl-heat-x">{{ bucket }}</div>
              <template v-for="row in cdaRadarHeatmapRows" :key="`radary-${row.macro_classe}`">
                <div class="ffl-heat-y">{{ row.macro_classe }}</div>
                <div
                  v-for="cell in row.cells"
                  :key="`radarc-${row.macro_classe}-${cell.bucket_label}`"
                  class="ffl-heat-cell radar"
                  :style="{ background: radarBurnColor(cell.burn_pct) }"
                  :title="radarHeatTitle(cell)"
                >
                  <strong>{{ fmtPctPlain(Number((cell.plausible_burn_pct ?? cell.burn_pct) || 0) * 100) }}</strong>
                  <span>{{ fmtMoney(cell.plausible_consumed_since_cda ?? cell.consumed_since_cda) }}</span>
                </div>
              </template>
            </div>
          </section>

          <section class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Tipos no radar</span>
              <strong>{{ fmtCount(cdaRadarSummary.redemption_period_days || cdaRadarCoverage.days_since_cda) }} dias</strong>
            </div>
            <div class="ffl-coherence-list">
              <button
                v-for="item in cdaRadarTopPressureRows"
                :key="`radar-class-row-${item.radar_group || item.fund_type_group || item.macro_classe}`"
                type="button"
                class="ffl-coherence-row"
                :class="Number(item[`runway_days_${cdaRadarScenario}`] || 999) <= 15 ? 'warn' : 'flat'"
                @click="cdaRadarMacroFilter = item.radar_group || item.fund_type_group || item.macro_classe"
              >
                <span>
                  <strong>{{ item.radar_group || item.fund_type_group || item.macro_classe }}</strong>
                  <em>
                    {{ fmtCount(item.fund_count) }} fundos |
                    burn plaus {{ fmtPctPlain(Number(item.plausible_inventory_burn_pct || 0) * 100) }} |
                    tec {{ fmtPctPlain(Number(item.inventory_burn_pct || 0) * 100) }}
                  </em>
                </span>
                <span>
                  <strong>{{ fmtMoney(item.plausible_inventory_remaining) }}</strong>
                  <em>plausivel | tec {{ fmtMoney(item.sellable_inventory_remaining) }}</em>
                </span>
                <span>
                  <strong :class="Number(item.gross_redemption_since_cda || 0) > 0 ? 'down' : 'flat'">{{ fmtMoney(item.gross_redemption_since_cda) }}</strong>
                  <em>net {{ fmtMoney(item.net_flow_since_cda) }}</em>
                </span>
                <b>
                  {{ fmtCount(item.redemption_period_days || cdaRadarSummary.redemption_period_days || cdaRadarCoverage.days_since_cda) }}d
                  <em>runway {{ fmtDays(item[`plausible_runway_days_${cdaRadarScenario}`]) }}</em>
                </b>
              </button>
            </div>
          </section>
        </section>

        <section v-if="cdaRadarPayload?.ok" class="ffl-global-split">
          <section class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Buckets de liquidez</span>
              <strong>{{ cdaRadarScenarioActive.label || 'Stress' }}</strong>
            </div>
            <table class="ffl-global-table">
              <thead>
                <tr>
                  <th>Bucket</th>
                  <th>Tecnico</th>
                  <th>Plausivel</th>
                  <th>Consumido</th>
                  <th>Burn</th>
                  <th>Vendas mes</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in cdaRadarBucketSummary" :key="`radar-bucket-${item.bucket}`" :style="nportRowTint(item.free_inventory_remaining, cdaRadarBucketMax)">
                  <td>
                    <strong>{{ item.bucket_label }}</strong>
                    <em>rank {{ fmtCount(item.liquidity_rank) }} | {{ fmtCount(item.fund_count) }} fundos</em>
                  </td>
                  <td>{{ fmtMoney(item.free_inventory_remaining) }}</td>
                  <td>{{ fmtMoney(item.plausible_inventory_remaining) }}</td>
                  <td :class="moveClass(-Number(item.consumed_since_cda || 0))">{{ fmtMoney(item.consumed_since_cda) }}</td>
                  <td>
                    {{ fmtPctPlain(Number(item.plausible_inventory_burn_pct || 0) * 100) }}
                    <em>tec {{ fmtPctPlain(Number(item.inventory_burn_pct || 0) * 100) }}</em>
                  </td>
                  <td>{{ fmtMoney(item.sell_value) }}</td>
                </tr>
              </tbody>
            </table>
          </section>

          <section class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Fundos mais pressionados</span>
              <strong>{{ cdaRadarScenarioActive.label || 'Stress' }}</strong>
            </div>
            <div class="ffl-graph-table-scroll">
              <table class="ffl-global-table">
                <thead>
                  <tr>
                    <th>Fundo</th>
                    <th>Tipo</th>
                    <th>Fluxo 21d</th>
                    <th>Desde CDA</th>
                    <th>Resgates CDA</th>
                    <th>Estoque</th>
                    <th>Runway</th>
                    <th>Bucket</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="item in cdaRadarFundRows"
                    :key="`radar-fund-${item.fund_cnpj}`"
                    class="clickable"
                    @click="openCdaRadarFund(item)"
                  >
                    <td>
                      <strong>{{ item.fund_name }}</strong>
                      <em>{{ item.coverage_flag }} | {{ item.fund_cnpj }}</em>
                    </td>
                    <td>{{ item.radar_group || item.fund_type_group || item.macro_classe }}</td>
                    <td :class="moveClass(item.net_flow_21d)">{{ fmtMoney(item.net_flow_21d) }}</td>
                    <td :class="moveClass(item.net_flow_since_cda)">{{ fmtMoney(item.net_flow_since_cda) }}</td>
                    <td :class="Number((item.gross_redemption_since_cda || item.gross_redemption_21d) || 0) > 0 ? 'down' : 'flat'">{{ fmtMoney(item.gross_redemption_since_cda || item.gross_redemption_21d) }}</td>
                    <td>
                      <strong>{{ fmtMoney(item.plausible_inventory_remaining) }}</strong>
                      <em>tec {{ fmtMoney(item.sellable_inventory_remaining) }}</em>
                    </td>
                    <td>
                      <strong>{{ fmtDays(item[`plausible_runway_days_${cdaRadarScenario}`]) }}</strong>
                      <em>tec {{ fmtDays(item[`runway_days_${cdaRadarScenario}`]) }}</em>
                    </td>
                    <td>{{ item.bucket_at_risk }}</td>
                  </tr>
                  <tr v-if="!cdaRadarFundRows.length">
                    <td colspan="8" class="ffl-empty-row">Sem fundos nesse recorte.</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </section>
      </main>

      <main v-else-if="activeTab === 'graph'" class="ffl-graph-view">
        <section class="ffl-global-panel ffl-graph-cockpit">
          <div class="ffl-graph-header">
            <div>
              <div class="ffl-section-head bare">
                <span>Grafo CDA Brasil</span>
                <strong>{{ cdaGraphMonth }}</strong>
              </div>
              <p>Rede explicativa de fundos, ativos, emissores, paises, temas e trilhas de dinheiro do CDA. Esta aba remove o cabecalho de captacao diaria para deixar o grafo respirar.</p>
            </div>
            <div class="ffl-nport-actions">
              <button type="button" class="ffl-btn tiny" :disabled="cdaGraphLoading || cdaGraphBuilding" @click="loadCdaGraph(true)">
                {{ cdaGraphLoading ? 'Carregando...' : 'Recarregar' }}
              </button>
              <button type="button" class="ffl-btn tiny" :disabled="cdaGraphBuilding || cdaGraphLoading" @click="rebuildCdaGraph">
                {{ cdaGraphBuilding ? 'Construindo...' : 'Reconstruir Neo4j' }}
              </button>
              <span v-if="cdaGraphError" class="ffl-inline-error">{{ cdaGraphError }}</span>
            </div>
          </div>
          <div class="ffl-global-cards compact">
            <div v-for="card in cdaGraphCards" :key="card.key" class="ffl-global-card">
              <span>{{ card.label }}</span>
              <strong :class="card.tone">{{ card.value }}</strong>
              <em>{{ card.detail }}</em>
            </div>
          </div>
          <div class="ffl-graph-controls">
            <div class="ffl-nport-controls wrap">
              <button
                v-for="target in cdaGraphTargets"
                :key="`cdagraph-${target.key}`"
                type="button"
                :class="{ active: cdaGraphTarget === target.key }"
                @click="setCdaGraphTarget(target.key)"
              >
                {{ target.label }}
              </button>
            </div>
            <input
              v-model="cdaGraphIssuerFilter"
              class="ffl-graph-input"
              type="text"
              placeholder="filtrar emissor"
              @keydown.enter="applyCdaGraphFilters"
            />
            <input
              v-model="cdaGraphFundFilter"
              class="ffl-graph-input cnpj"
              type="text"
              placeholder="CNPJ do fundo"
              @keydown.enter="applyCdaGraphFilters"
            />
            <select v-model.number="cdaGraphLimit" class="ffl-select" @change="applyCdaGraphFilters">
              <option :value="80">80 rel.</option>
              <option :value="140">140 rel.</option>
              <option :value="260">260 rel.</option>
              <option :value="420">420 rel.</option>
            </select>
            <button type="button" class="ffl-btn tiny" :disabled="cdaGraphLoading" @click="applyCdaGraphFilters">Aplicar</button>
            <button type="button" class="ffl-btn tiny ghost" :disabled="cdaGraphLoading" @click="clearCdaGraphFilters">Limpar</button>
          </div>
        </section>

        <section class="ffl-global-panel ffl-money-map-panel">
          <div class="ffl-section-head">
            <span>Caminho do dinheiro</span>
            <strong>{{ cdaMoneyModeDetail }}</strong>
            <div class="ffl-money-mode-controls">
              <button
                v-for="mode in moneyFlowModes"
                :key="`money-mode-${mode.key}`"
                type="button"
                :class="{ active: moneyFlowMode === mode.key }"
                @click="setMoneyFlowMode(mode.key)"
              >
                {{ mode.label }}
              </button>
            </div>
          </div>
          <div class="ffl-money-map-wrap">
            <svg class="ffl-money-map" viewBox="0 0 820 248" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
              <defs>
                <marker id="ffl-money-arrow-up" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="#34d399" />
                </marker>
                <marker id="ffl-money-arrow-down" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="#fb7185" />
                </marker>
              </defs>
              <path
                v-for="(source, index) in cdaMoneyMapSources"
                :key="`money-source-${source.key}`"
                :d="moneySourcePath(index, cdaMoneyMapSources.length)"
                class="ffl-money-edge"
                :class="source.tone"
                :stroke-width="moneyStrokeWidth(source.abs_value, cdaMoneySourceMax)"
              />
              <path
                v-for="(layer, index) in cdaMoneyMapTargets"
                :key="`money-layer-${layer.target}`"
                :d="moneyLayerPath(index, cdaMoneyMapTargets.length)"
                class="ffl-money-edge"
                :class="moveClass(layer.net_value)"
                :stroke-width="moneyStrokeWidth(layer.gross_value, cdaMoneyLayerMax)"
              />
              <g v-for="(source, index) in cdaMoneyMapSources" :key="`money-source-node-${source.key}`" :transform="`translate(48 ${moneySourceY(index, cdaMoneyMapSources.length) - 13})`">
                <rect width="152" height="26" rx="6" class="ffl-money-node source" />
                <text x="8" y="11">{{ source.label }}</text>
                <text x="8" y="22" class="value" :class="source.tone">{{ source.display }}</text>
              </g>
              <g transform="translate(336 92)">
                <rect width="148" height="72" rx="7" class="ffl-money-node core" />
                <text x="12" y="24">{{ cdaMoneyCore.label }}</text>
                <text x="12" y="42" class="value">{{ cdaMoneyCore.value }}</text>
                <text x="12" y="58" class="muted">{{ cdaMoneyCore.detail }}</text>
              </g>
              <g v-for="(layer, index) in cdaMoneyMapTargets" :key="`money-target-${layer.target}`" :transform="`translate(590 ${moneyTargetY(index, cdaMoneyMapTargets.length) - 16})`">
                <rect width="180" height="32" rx="6" class="ffl-money-node target" :class="moveClass(layer.net_value)" />
                <text x="9" y="13">{{ layer.target_label || layer.name }}</text>
                <text x="9" y="26" class="value" :class="moveClass(layer.net_value)">{{ layer.display || fmtMoney(layer.net_value) }} | {{ layer.secondary_display || fmtMoney(layer.gross_value) }}</text>
              </g>
            </svg>
            <aside class="ffl-money-map-side">
              <div v-for="layer in cdaMoneySideLayers" :key="`layer-chip-${layer.target}`" class="ffl-money-layer-row" :title="moneyLayerTitle(layer)">
                <span>{{ layer.target_label || layer.name }}</span>
                <div class="ffl-diverging-track">
                  <i :class="moveClass(layer.net_value)" :style="divergingBarStyle(layer.net_value, cdaMoneyNetMax)"></i>
                </div>
                <strong :class="moveClass(layer.net_value)">{{ layer.display || fmtMoney(layer.net_value) }}</strong>
              </div>
            </aside>
          </div>
          <div class="ffl-money-detail-grid">
            <section v-if="moneyFlowMode !== 'quarterly'" class="ffl-money-detail-card">
              <div class="ffl-section-head compact">
                <span>Pernas ICI</span>
                <strong>{{ fmtDate(iciLatestDate) || 'weekly' }}</strong>
              </div>
              <div class="ffl-money-two-cols">
                <div>
                  <b>Inflows</b>
                  <button v-for="leg in cdaIciInflowLegs" :key="`ici-in-${leg.key}`" type="button" class="ffl-money-mini-row">
                    <span>{{ leg.label }}</span>
                    <strong class="up">{{ fmtUsdMn(leg.value) }}</strong>
                  </button>
                </div>
                <div>
                  <b>Outflows</b>
                  <button v-for="leg in cdaIciOutflowLegs" :key="`ici-out-${leg.key}`" type="button" class="ffl-money-mini-row">
                    <span>{{ leg.label }}</span>
                    <strong class="down">{{ fmtUsdMn(leg.value) }}</strong>
                  </button>
                </div>
              </div>
            </section>

            <section v-else class="ffl-money-detail-card">
              <div class="ffl-section-head compact">
                <span>N-PORT paises</span>
                <strong>{{ nportReport.quarter || 'trimestral' }}</strong>
              </div>
              <div class="ffl-money-mini-list">
                <button v-for="item in cdaNportCountryRows" :key="`nport-country-${item.investment_country}`" type="button" class="ffl-money-mini-row">
                  <span>{{ item.investment_country }}</span>
                  <em>{{ fmtCount(item.fund_count) }} fundos | short {{ fmtUsd(item.short_value) }}</em>
                  <strong :class="moveClass(item.net_value)">{{ fmtUsd(item.net_value) }}</strong>
                </button>
              </div>
            </section>

            <section v-if="moneyFlowMode !== 'daily_weekly'" class="ffl-money-detail-card">
              <div class="ffl-section-head compact">
                <span>Cotas de fundos</span>
                <strong>compras x vendas</strong>
              </div>
              <div class="ffl-money-mini-list">
                <button v-for="item in cdaFundQuotaRows" :key="`quota-${item.fund_type}-${item.asset_class}`" type="button" class="ffl-money-mini-row">
                  <span>{{ item.fund_type }}</span>
                  <em>{{ fmtMoney(item.buy_value) }} compra | {{ fmtMoney(item.sell_value) }} venda</em>
                  <strong :class="moveClass(item.reported_activity)">{{ fmtMoney(item.reported_activity) }}</strong>
                </button>
              </div>
            </section>

            <section v-else class="ffl-money-detail-card">
              <div class="ffl-section-head compact">
                <span>Fluxo local classes</span>
                <strong>{{ period }}</strong>
              </div>
              <div class="ffl-money-mini-list">
                <button v-for="item in cdaDailyClassRows" :key="`daily-class-${item.key}`" type="button" class="ffl-money-mini-row">
                  <span>{{ item.name }}</span>
                  <em>{{ item.detail }}</em>
                  <strong :class="moveClass(item.value)">{{ fmtMoney(item.value) }}</strong>
                </button>
              </div>
            </section>

            <section v-if="moneyFlowMode !== 'daily_weekly'" class="ffl-money-detail-card">
              <div class="ffl-section-head compact">
                <span>Reducoes reportadas</span>
                <strong>vendas / saidas</strong>
              </div>
              <div class="ffl-money-mini-list">
                <button v-for="item in cdaReductionRows" :key="`reduction-${item.asset_class}`" type="button" class="ffl-money-mini-row">
                  <span>{{ item.asset_class }}</span>
                  <em>{{ fmtCount(item.fund_count) }} fundos | {{ fmtMoney(item.net_value) }} em carteira</em>
                  <strong class="down">{{ fmtMoney(item.net_reduction_value || item.sell_value) }}</strong>
                </button>
              </div>
            </section>

            <section v-else class="ffl-money-detail-card">
              <div class="ffl-section-head compact">
                <span>B3 participantes</span>
                <strong>21d</strong>
              </div>
              <div class="ffl-money-mini-list">
                <button v-for="item in cdaDailyParticipantRows" :key="`daily-part-${item.participant_type}`" type="button" class="ffl-money-mini-row">
                  <span>{{ item.participant_type }}</span>
                  <em>{{ fmtMoney(item.buy_value_brl || 0) }} compra | {{ fmtMoney(item.sell_value_brl || 0) }} venda</em>
                  <strong :class="moveClass(item.rolling_21d_net_flow_brl)">{{ fmtMoney(item.rolling_21d_net_flow_brl) }}</strong>
                </button>
              </div>
            </section>

            <section v-if="moneyFlowMode !== 'daily_weekly'" class="ffl-money-detail-card">
              <div class="ffl-section-head compact">
                <span>Fundos motivadores</span>
                <strong>{{ cdaSelectedTargetLabel }}</strong>
              </div>
              <div class="ffl-money-two-cols dense">
                <div>
                  <b>Entradas CDA</b>
                  <button v-for="item in cdaSelectedTargetBuys" :key="`target-buy-${item.fund_cnpj}`" type="button" class="ffl-money-mini-row" @click="cdaGraphFundFilter = item.fund_cnpj; applyCdaGraphFilters()">
                    <span>{{ item.fund_name }}</span>
                    <strong class="up">{{ fmtMoney(item.buy_value) }}</strong>
                  </button>
                </div>
                <div>
                  <b>Saidas CDA</b>
                  <button v-for="item in cdaSelectedTargetSells" :key="`target-sell-${item.fund_cnpj}`" type="button" class="ffl-money-mini-row" @click="cdaGraphFundFilter = item.fund_cnpj; applyCdaGraphFilters()">
                    <span>{{ item.fund_name }}</span>
                    <strong class="down">{{ fmtMoney(item.sell_value) }}</strong>
                  </button>
                </div>
              </div>
            </section>

            <section v-else class="ffl-money-detail-card">
              <div class="ffl-section-head compact">
                <span>OI B3 contratos</span>
                <strong>DI/DDI/DOL/WDO/WIN</strong>
              </div>
              <div class="ffl-money-mini-list">
                <button v-for="item in cdaDailyOiRows" :key="`daily-oi-${item.asset}`" type="button" class="ffl-money-mini-row">
                  <span>{{ item.asset }}</span>
                  <em>OI {{ fmtCount(item.open_interest) }} | contratos {{ fmtCount(item.contract_count) }}</em>
                  <strong :class="moveClass(item.rolling_21d_variation_open_interest)">{{ signedCount(item.rolling_21d_variation_open_interest) }}</strong>
                </button>
              </div>
            </section>
          </div>
        </section>

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

        <section class="ffl-graph-correlation">
          <section class="ffl-global-panel ffl-asset-correlation-panel">
            <div class="ffl-section-head compact">
              <span>Correlacao fundo x ativo</span>
              <strong>{{ cdaActiveAssetLensLabel }}</strong>
            </div>
            <div class="ffl-lens-tabs">
              <button
                v-for="bucket in cdaAssetLensBuckets"
                :key="`lens-${bucket.bucket}`"
                type="button"
                :class="{ active: cdaActiveAssetLensKey === bucket.bucket }"
                @click="cdaAssetLensFilter = bucket.bucket"
              >
                <span>{{ bucket.label }}</span>
                <em>{{ fmtCount(bucket.asset_count) }}</em>
              </button>
            </div>
            <div class="ffl-correlation-table-wrap">
              <table class="ffl-global-table ffl-correlation-table">
                <thead>
                  <tr>
                    <th>Ativo</th>
                    <th>Segmento</th>
                    <th>Fundos</th>
                    <th>Tipos</th>
                    <th>Long</th>
                    <th>Short</th>
                    <th>Atividade</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="item in cdaAssetLensRows"
                    :key="`lens-row-${item.bucket}-${item.asset_key}-${item.asset_class}`"
                    class="clickable"
                    @click="openCdaAssetTrailModal(item)"
                  >
                    <td>
                      <strong>{{ item.display_name || item.asset_key }}</strong>
                      <em>{{ item.asset_key }} | {{ item.issuer_name || 'sem emissor' }}</em>
                    </td>
                    <td>
                      <span class="ffl-lens-pill">{{ item.bucket_label }}</span>
                      <em>{{ item.tp_ativo || item.asset_class }}</em>
                    </td>
                    <td>{{ fmtCount(item.fund_count) }}</td>
                    <td>{{ fmtCount(item.fund_type_count) }}</td>
                    <td>{{ fmtMoney(item.long_value) }}</td>
                    <td :class="moveClass(-Number(item.short_value || 0))">{{ fmtMoney(item.short_value) }}</td>
                    <td :class="moveClass(item.reported_activity)">{{ fmtMoney(item.reported_activity) }}</td>
                  </tr>
                  <tr v-if="!cdaAssetLensRows.length">
                    <td colspan="7" class="ffl-empty-row">Sem ativos nessa lente.</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p class="ffl-method-note">{{ cdaAssetLenses.methodology }}</p>
          </section>

          <section class="ffl-global-panel ffl-flow-coherence-panel">
            <div class="ffl-section-head compact">
              <span>Coerencia B3 x CDA</span>
              <strong>participante -> segmento</strong>
            </div>
            <div class="ffl-coherence-list">
              <button
                v-for="item in cdaParticipantCoherenceRows"
                :key="`coherence-${item.rank}-${item.participant_type}-${item.bucket}`"
                type="button"
                class="ffl-coherence-row"
                :class="item.tone || 'flat'"
                @click="openCdaCoherenceModal(item)"
              >
                <span>
                  <strong>{{ item.participant_type }}</strong>
                  <em>{{ item.relationship }} com {{ item.bucket_label }}</em>
                </span>
                <span>
                  <strong>{{ item.bucket_label }}</strong>
                  <em>
                    {{ fmtCount(item.fund_count) }} fundos | {{ fmtCount(item.asset_count) }} ativos
                    <template v-if="(item.sample_assets || []).length">
                      | {{ (item.sample_assets || []).slice(0, 2).join(' | ') }}
                    </template>
                  </em>
                </span>
                <b :class="moveClass(item.participant_flow_21d_brl)">{{ fmtMoney(item.participant_flow_21d_brl) }}</b>
                <b :class="moveClass(item.bucket_activity)">{{ fmtMoney(item.bucket_activity) }}</b>
              </button>
              <div v-if="!cdaParticipantCoherenceRows.length" class="ffl-panel-empty">Sem sinal combinado B3/CDA carregado.</div>
            </div>
            <p class="ffl-method-note">{{ cdaParticipantAssetCoherence.source_note }}</p>
          </section>
        </section>

        <section class="ffl-graph-options-triangulation">
          <section class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Quadrante de opcoes</span>
              <strong>{{ fmtCount(cdaOptionTriangulationSummary.fund_option_equity_link_count) }} triangulacoes</strong>
            </div>
            <div class="ffl-option-underlying-list">
              <button
                v-for="item in cdaOptionUnderlyingRows.slice(0, 12)"
                :key="`opt-underlying-${item.underlying_key}`"
                type="button"
                class="ffl-option-underlying-row"
                @click="cdaGraphIssuerFilter = item.underlying_key; applyCdaGraphFilters()"
              >
                <span>
                  <strong>{{ item.underlying_key }}</strong>
                  <em>{{ fmtCount(item.fund_count) }} fundos | {{ fmtCount(item.option_count) }} pernas</em>
                </span>
                <b>{{ fmtMoney(item.option_gross_value) }}</b>
                <b>{{ fmtPctPlain(item.coverage_ratio) }}</b>
              </button>
              <div v-if="!cdaOptionUnderlyingRows.length" class="ffl-panel-empty">Sem opcoes trianguladas no mes.</div>
            </div>
          </section>

          <section class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Opcao -> ativo-base</span>
              <strong>pares por fundos em comum</strong>
            </div>
            <div class="ffl-option-pair-list">
              <button
                v-for="item in cdaOptionPairRows.slice(0, 14)"
                :key="`opt-pair-${item.rank}-${item.option_key}-${item.equity_key}`"
                type="button"
                class="ffl-option-pair-row"
                :class="item.tone || 'flat'"
                @click="openCdaAssetTrailModal({ ...item, asset_key: item.option_key, display_name: item.option_display, asset_class: 'Opcoes', bucket: item.option_side === 'put' ? 'options_put' : 'options_call', side: item.option_position_role === 'written' ? 'shorted' : 'coveted' })"
              >
                <span>
                  <strong>{{ item.option_key }}</strong>
                  <em>{{ item.option_side }} | {{ item.option_position_role }} | {{ item.underlying_key }}</em>
                </span>
                <span>
                  <strong>{{ item.equity_key }}</strong>
                  <em>{{ item.equity_display }}</em>
                </span>
                <b>{{ fmtCount(item.shared_fund_count) }} fundos</b>
                <b>{{ fmtMoney(item.option_gross_value) }}</b>
              </button>
              <div v-if="!cdaOptionPairRows.length" class="ffl-panel-empty">Sem pares opcao/acao carregados.</div>
            </div>
          </section>

          <section class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Fundos que triangulam</span>
              <strong>opcao + acao/ETF</strong>
            </div>
            <div class="ffl-option-fund-list">
              <button
                v-for="item in cdaOptionFundLinkRows.slice(0, 12)"
                :key="`opt-fund-${item.rank}-${item.fund_cnpj}-${item.option_key}`"
                type="button"
                class="ffl-option-fund-row"
                :class="item.tone || 'flat'"
                @click="cdaGraphFundFilter = item.fund_cnpj; applyCdaGraphFilters()"
              >
                <span>
                  <strong>{{ item.fund_name }}</strong>
                  <em>{{ item.option_key }} -> {{ item.equity_key }}</em>
                </span>
                <b :class="moveClass(item.option_net_value)">{{ fmtMoney(item.option_net_value) }}</b>
                <b>{{ fmtMoney(item.equity_gross_value) }}</b>
              </button>
              <div v-if="!cdaOptionFundLinkRows.length" class="ffl-panel-empty">Sem fundos com perna de opcao e ativo-base em comum.</div>
            </div>
          </section>
        </section>

        <section class="ffl-graph-asset-trails">
          <div class="ffl-asset-trail-filter-bar">
            <span>Tipo de ativo</span>
            <div>
              <button
                v-for="bucket in cdaAssetTrailTypeOptions"
                :key="`trail-type-${bucket.bucket}`"
                type="button"
                :class="{ active: cdaAssetTrailTypeFilter === bucket.bucket }"
                @click="cdaAssetTrailTypeFilter = bucket.bucket"
              >
                {{ bucket.label }}
                <em>{{ fmtCount(bucket.asset_count) }}</em>
              </button>
            </div>
          </div>
          <section class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Ativos cobicados</span>
              <strong>{{ cdaAssetTrailTypeLabel }}</strong>
            </div>
            <div class="ffl-asset-trail-list">
              <button
                v-for="asset in cdaAssetTrailCovetedRows"
                :key="`asset-long-${asset.trail_key}`"
                type="button"
                class="ffl-asset-trail-row up"
                @click="openCdaAssetTrailModal(asset)"
              >
                <span>
                  <strong>{{ asset.asset_key }}</strong>
                  <em>{{ asset.bucket_label || asset.asset_class }} | {{ asset.issuer_name || 'sem emissor' }}</em>
                </span>
                <b>{{ fmtCount(asset.fund_count) }} fundos</b>
                <b>{{ fmtMoney(asset.long_value) }}</b>
              </button>
              <div v-if="!cdaAssetTrailCovetedRows.length" class="ffl-panel-empty">Sem ativos comprados relevantes.</div>
            </div>
          </section>

          <section class="ffl-global-panel">
            <div class="ffl-section-head compact">
              <span>Ativos shorteados</span>
              <strong>{{ cdaAssetTrailTypeLabel }}</strong>
            </div>
            <div class="ffl-asset-trail-list">
              <button
                v-for="asset in cdaAssetTrailShortedRows"
                :key="`asset-short-${asset.trail_key}`"
                type="button"
                class="ffl-asset-trail-row down"
                @click="openCdaAssetTrailModal(asset)"
              >
                <span>
                  <strong>{{ asset.asset_key }}</strong>
                  <em>{{ asset.bucket_label || asset.asset_class }} | {{ asset.issuer_name || 'sem emissor' }}</em>
                </span>
                <b>{{ fmtCount(asset.fund_count) }} fundos</b>
                <b>{{ fmtMoney(asset.short_value || asset.gross_value) }}</b>
              </button>
              <div v-if="!cdaAssetTrailShortedRows.length" class="ffl-panel-empty">Sem shorts/derivativos relevantes.</div>
            </div>
          </section>
        </section>

        <section class="ffl-global-panel ffl-graph-edge-facts-panel">
          <div class="ffl-section-head compact">
            <span>Conexoes explicativas</span>
            <strong>arestas principais</strong>
          </div>
          <div class="ffl-edge-fact-list">
            <div v-for="edge in cdaGraphEdgeFacts" :key="edge.uuid" class="ffl-edge-fact" :class="edge.tone || 'flat'">
              <strong>
                {{ edge.name }}
                <em v-if="edge.category || edge.fact_type">{{ edge.category || edge.fact_type }}</em>
              </strong>
              <span>{{ edge.fact }}</span>
              <small v-if="edge.metric_label">{{ edge.metric_label }}</small>
            </div>
          </div>
        </section>
      </main>

      <main v-else-if="activeTab === 'sources'" class="ffl-sources-view">
        <section class="ffl-source-list">
          <div class="ffl-source-card ffl-sources-toolbar-card">
            <div>
              <div class="ffl-section-head bare">
                <span>Fontes e captura</span>
                <strong>{{ activeSourceCount }} ativas / {{ sourceCards.length }} fontes</strong>
              </div>
              <p>Status operacional das fontes do Funds Flow Local, separando data oficial da base e momento real da captura local.</p>
            </div>
            <button type="button" class="ffl-btn" :disabled="loading || collecting" @click="refresh(true)">
              {{ loading || collecting ? 'Atualizando...' : 'Recarregar snapshot' }}
            </button>
          </div>

          <details v-for="source in sourceCards" :key="source.id" class="ffl-source-card">
            <summary>
              <span class="ffl-source-chevron">›</span>
              <div>
                <strong>{{ source.label }}</strong>
                <em>{{ source.provider }} | {{ source.kind }}</em>
              </div>
              <span class="ffl-source-pill" :class="source.statusClass">{{ source.statusLabel }}</span>
              <span>{{ source.officialDate }}</span>
              <button
                type="button"
                class="ffl-btn tiny"
                :disabled="Boolean(refreshingSource)"
                @click.stop="refreshSource(source.id)"
              >
                {{ refreshingSource === source.id ? '...' : 'Recarregar' }}
              </button>
            </summary>

            <div class="ffl-source-detail">
              <div class="ffl-source-metrics">
                <div>
                  <span>Cadencia</span>
                  <strong>{{ source.cadenceLabel }}</strong>
                </div>
                <div>
                  <span>Linhas</span>
                  <strong>{{ fmtCount(source.rows) }}</strong>
                </div>
                <div>
                  <span>Latencia</span>
                  <strong>{{ fmtLatency(source.latency_ms) }}</strong>
                </div>
                <div>
                  <span>Data oficial</span>
                  <strong>{{ source.officialDate }}</strong>
                </div>
                <div>
                  <span>Capturado em</span>
                  <strong>{{ source.capturedAt }}</strong>
                </div>
              </div>

              <p>{{ source.technicalSummary }}</p>

              <div class="ffl-source-components">
                <span v-for="component in sourceComponents(source)" :key="component">{{ component }}</span>
              </div>

              <dl class="ffl-source-meta">
                <div>
                  <dt>URL</dt>
                  <dd>{{ source.url || '-' }}</dd>
                </div>
                <div>
                  <dt>Cache</dt>
                  <dd>{{ source.cached_path || '-' }}</dd>
                </div>
                <div>
                  <dt>Referencia temporal</dt>
                  <dd>{{ source.secondaryReference || '-' }}</dd>
                </div>
                <div>
                  <dt>Temporalidade</dt>
                  <dd>{{ sourceTemporalDetail(source) }}</dd>
                </div>
                <div>
                  <dt>Resumo tecnico</dt>
                  <dd>{{ sourceHealthDetail(source) }}</dd>
                </div>
              </dl>

              <details class="ffl-source-logs">
                <summary>Logs e payload operacional</summary>
                <pre>{{ sourceLogText(source) }}</pre>
              </details>
            </div>
          </details>
        </section>
      </main>
    </template>

    <div v-if="cdaSelectedBridgePath" class="ffl-modal-backdrop" @click.self="closeCdaBridgeModal">
      <section class="ffl-bridge-modal" role="dialog" aria-modal="true">
        <header class="ffl-bridge-modal-head">
          <div>
            <span>Trilha explicativa</span>
            <h3>{{ cdaSelectedBridgePath.fund_type }} -> {{ cdaSelectedBridgePath.target_label }}</h3>
            <p>Fundos, emissores e ativos que explicam o caminho selecionado no CDA.</p>
          </div>
          <button type="button" class="ffl-btn tiny" @click="closeCdaBridgeModal">Fechar</button>
        </header>

        <div class="ffl-bridge-modal-kpis">
          <div>
            <span>Fundos</span>
            <strong>{{ fmtCount(cdaSelectedBridgePath.fund_count) }}</strong>
          </div>
          <div>
            <span>Gross</span>
            <strong>{{ fmtMoney(cdaSelectedBridgePath.gross_value) }}</strong>
          </div>
          <div>
            <span>Net</span>
            <strong :class="moveClass(cdaSelectedBridgePath.net_value)">{{ fmtMoney(cdaSelectedBridgePath.net_value) }}</strong>
          </div>
          <div>
            <span>% PL medio</span>
            <strong>{{ fmtPctPlain(cdaSelectedBridgePath.avg_pct_pl) }}</strong>
          </div>
        </div>

        <div class="ffl-bridge-modal-body">
          <section class="ffl-bridge-modal-panel funds">
            <div class="ffl-section-head compact">
              <span>Fundos por materialidade</span>
              <strong>{{ fmtCount(cdaSelectedBridgeFunds.length) }}</strong>
            </div>
            <div v-if="cdaBridgePathDetailLoading" class="ffl-panel-empty">Carregando detalhes da trilha...</div>
            <div v-else-if="cdaBridgePathDetailError" class="ffl-panel-empty error">{{ cdaBridgePathDetailError }}</div>
            <div class="ffl-bridge-table-wrap">
              <table class="ffl-global-table">
                <thead>
                  <tr>
                    <th>Fundo</th>
                    <th>Gross</th>
                    <th>Net</th>
                    <th>Ativ.</th>
                    <th>% PL</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="fund in cdaSelectedBridgeFunds" :key="`bridge-fund-${fund.fund_cnpj}`">
                    <td>
                      <strong>{{ fund.fund_name || fund.fund_cnpj }}</strong>
                      <em>{{ fund.holding_count }} pos. | {{ fund.issuer_count }} emissores</em>
                    </td>
                    <td>{{ fmtMoney(fund.gross_value) }}</td>
                    <td :class="moveClass(fund.net_value)">{{ fmtMoney(fund.net_value) }}</td>
                    <td :class="moveClass(fund.reported_activity)">{{ fmtMoney(fund.reported_activity) }}</td>
                    <td>{{ fmtPctPlain(fund.target_pct_pl) }}</td>
                  </tr>
                  <tr v-if="!cdaSelectedBridgeFunds.length">
                    <td colspan="5" class="ffl-empty-row">Sem fundos detalhados para esta trilha.</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section class="ffl-bridge-modal-panel">
            <div class="ffl-section-head compact">
              <span>Emissores da trilha</span>
              <strong>{{ fmtCount(cdaSelectedBridgeIssuers.length) }}</strong>
            </div>
            <div class="ffl-bridge-mini-list">
              <button v-for="issuer in cdaSelectedBridgeIssuers" :key="`bridge-issuer-${issuer.issuer_name}`" type="button" class="ffl-bridge-mini-row" @click="cdaGraphIssuerFilter = issuer.issuer_name; applyCdaGraphFilters()">
                <span>{{ issuer.issuer_name }}</span>
                <em>{{ fmtCount(issuer.fund_count) }} fundos | {{ issuer.sample_asset_class }}</em>
                <strong>{{ fmtMoney(issuer.gross_value) }}</strong>
              </button>
              <div v-if="!cdaSelectedBridgeIssuers.length" class="ffl-panel-empty">Sem emissores detalhados.</div>
            </div>
          </section>

          <section class="ffl-bridge-modal-panel">
            <div class="ffl-section-head compact">
              <span>Ativos da trilha</span>
              <strong>{{ fmtCount(cdaSelectedBridgeAssets.length) }}</strong>
            </div>
            <div class="ffl-bridge-mini-list">
              <div v-for="asset in cdaSelectedBridgeAssets" :key="`bridge-asset-${asset.asset_key}`" class="ffl-bridge-mini-row static">
                <span>{{ asset.asset_key }}</span>
                <em>{{ asset.asset_class }} | {{ asset.issuer_name || 'sem emissor' }} | {{ fmtCount(asset.fund_count) }} fundos</em>
                <strong :class="moveClass(asset.net_value)">{{ fmtMoney(asset.net_value) }}</strong>
              </div>
              <div v-if="!cdaSelectedBridgeAssets.length" class="ffl-panel-empty">Sem ativos detalhados.</div>
            </div>
          </section>
        </div>

        <footer class="ffl-bridge-modal-actions">
          <button type="button" class="ffl-btn ghost" @click="filterGraphByBridgePath">Ver esta trilha no grafo</button>
          <button type="button" class="ffl-btn" @click="closeCdaBridgeModal">Ok</button>
        </footer>
      </section>
    </div>

    <div v-if="cdaSelectedAssetTrail" class="ffl-modal-backdrop" @click.self="closeCdaAssetTrailModal">
      <section class="ffl-bridge-modal ffl-asset-modal" role="dialog" aria-modal="true">
        <header class="ffl-bridge-modal-head">
          <div>
            <span>{{ cdaSelectedAssetTrail.side === 'shorted' ? 'Ativo shorteado' : 'Ativo cobicado' }}</span>
            <h3>{{ cdaSelectedAssetTrail.asset_key }}</h3>
            <p>{{ cdaSelectedAssetTrail.asset_class }} | {{ cdaSelectedAssetTrail.issuer_name || 'sem emissor' }} | conexoes fundo -> ativo.</p>
          </div>
          <button type="button" class="ffl-btn tiny" @click="closeCdaAssetTrailModal">Fechar</button>
        </header>

        <div class="ffl-bridge-modal-kpis">
          <div>
            <span>Fundos</span>
            <strong>{{ fmtCount(cdaSelectedAssetTrail.fund_count) }}</strong>
          </div>
          <div>
            <span>Long</span>
            <strong>{{ fmtMoney(cdaSelectedAssetTrail.long_value) }}</strong>
          </div>
          <div>
            <span>Short</span>
            <strong class="down">{{ fmtMoney(cdaSelectedAssetTrail.short_value) }}</strong>
          </div>
          <div>
            <span>Atividade</span>
            <strong :class="moveClass(cdaSelectedAssetTrail.reported_activity)">{{ fmtMoney(cdaSelectedAssetTrail.reported_activity) }}</strong>
          </div>
        </div>

        <section class="ffl-bridge-modal-panel asset-links">
          <div class="ffl-section-head compact">
            <span>Conexoes especificas fundo -> ativo</span>
            <strong>{{ fmtCount(cdaSelectedAssetFundLinks.length) }}</strong>
          </div>
          <div v-if="cdaAssetTrailDetailLoading" class="ffl-panel-empty">Carregando conexoes do ativo...</div>
          <div v-else-if="cdaAssetTrailDetailError" class="ffl-panel-empty error">{{ cdaAssetTrailDetailError }}</div>
          <div class="ffl-bridge-table-wrap">
            <table class="ffl-global-table">
              <thead>
                <tr>
                  <th>Fundo</th>
                  <th>Tipo</th>
                  <th>Long</th>
                  <th>Short</th>
                  <th>Net</th>
                  <th>% PL</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="link in cdaSelectedAssetFundLinks" :key="`asset-link-${link.fund_cnpj}`">
                  <td>
                    <strong>{{ link.fund_name || link.fund_cnpj }}</strong>
                    <em>{{ link.holding_count }} pos. | qtd {{ fmtCount(link.qty_final) }}</em>
                  </td>
                  <td>{{ link.fund_type }}</td>
                  <td>{{ fmtMoney(link.long_value) }}</td>
                  <td class="down">{{ fmtMoney(link.short_value) }}</td>
                  <td :class="moveClass(link.net_value)">{{ fmtMoney(link.net_value) }}</td>
                  <td>{{ fmtPctPlain(link.pct_pl) }}</td>
                </tr>
                <tr v-if="!cdaSelectedAssetFundLinks.length">
                  <td colspan="6" class="ffl-empty-row">Sem conexoes fundo -> ativo para este recorte.</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <footer class="ffl-bridge-modal-actions">
          <button type="button" class="ffl-btn ghost" @click="filterGraphByAssetTrail">Filtrar grafo pelo emissor</button>
          <button type="button" class="ffl-btn" @click="closeCdaAssetTrailModal">Ok</button>
        </footer>
      </section>
    </div>

    <div v-if="cdaSelectedCoherenceRow" class="ffl-modal-backdrop" @click.self="closeCdaCoherenceModal">
      <section class="ffl-bridge-modal ffl-coherence-modal" role="dialog" aria-modal="true">
        <header class="ffl-bridge-modal-head">
          <div>
            <span>Coerencia B3 x CDA</span>
            <h3>{{ cdaSelectedCoherenceRow.participant_type }} -> {{ cdaSelectedCoherenceRow.bucket_label }}</h3>
            <p>{{ cdaSelectedCoherenceRow.explanation || cdaSelectedCoherenceRow.note }}</p>
          </div>
          <button type="button" class="ffl-btn tiny" @click="closeCdaCoherenceModal">Fechar</button>
        </header>

        <div class="ffl-bridge-modal-kpis">
          <div>
            <span>Leitura</span>
            <strong :class="cdaSelectedCoherenceRow.tone || 'flat'">{{ cdaSelectedCoherenceRow.relationship }}</strong>
          </div>
          <div>
            <span>B3 21d</span>
            <strong :class="moveClass(cdaSelectedCoherenceRow.participant_flow_21d_brl)">{{ fmtMoney(cdaSelectedCoherenceRow.participant_flow_21d_brl) }}</strong>
          </div>
          <div>
            <span>CDA atividade</span>
            <strong :class="moveClass(cdaSelectedCoherenceRow.bucket_activity)">{{ fmtMoney(cdaSelectedCoherenceRow.bucket_activity) }}</strong>
          </div>
          <div>
            <span>Materialidade</span>
            <strong>{{ fmtPctPlain(Number(cdaSelectedCoherenceRow.score_share || 0) * 100) }}</strong>
          </div>
        </div>

        <div class="ffl-coherence-modal-body">
          <section class="ffl-bridge-modal-panel">
            <div class="ffl-section-head compact">
              <span>Como surgiu</span>
              <strong>regra e janela</strong>
            </div>
            <div class="ffl-coherence-explain">
              <p>{{ cdaSelectedCoherenceRow.window_note || 'B3 usa janela diaria/21d; CDA usa o mes reportado.' }}</p>
              <p>{{ cdaSelectedCoherenceRow.rule_note || 'Mesma direcao de sinal marca coerencia; sinais opostos marcam divergencia.' }}</p>
              <p>{{ cdaSelectedCoherenceRow.ranking_note || 'Ranking por materialidade combinada entre fluxo B3 e atividade CDA.' }}</p>
            </div>
          </section>

          <section class="ffl-bridge-modal-panel">
            <div class="ffl-section-head compact">
              <span>Evidencia numerica</span>
              <strong>{{ cdaSelectedCoherenceRow.bucket_label }}</strong>
            </div>
            <div class="ffl-coherence-evidence-grid">
              <div v-for="item in cdaSelectedCoherenceEvidence" :key="item.label">
                <span>{{ item.label }}</span>
                <strong :class="item.tone || 'flat'">{{ item.value }}</strong>
              </div>
            </div>
          </section>

          <section class="ffl-bridge-modal-panel ffl-coherence-modal-assets">
            <div class="ffl-section-head compact">
              <span>Ativos de amostra</span>
              <strong>{{ fmtCount(cdaSelectedCoherenceAssets.length) }}</strong>
            </div>
            <div class="ffl-bridge-mini-list">
              <button
                v-for="asset in cdaSelectedCoherenceAssets"
                :key="`coherence-asset-${asset}`"
                type="button"
                class="ffl-bridge-mini-row"
                @click="closeCdaCoherenceModal(); openCdaAssetTrailModal({ asset_key: asset, asset_class: cdaSelectedCoherenceRow.bucket_label, bucket: cdaSelectedCoherenceRow.bucket, side: cdaSelectedCoherenceRow.bucket_activity < 0 ? 'shorted' : 'coveted' })"
              >
                <span>{{ asset }}</span>
                <em>{{ cdaSelectedCoherenceRow.bucket_label }} | clique para ver fundos conectados</em>
                <strong>detalhe</strong>
              </button>
              <div v-if="!cdaSelectedCoherenceAssets.length" class="ffl-panel-empty">Sem ativos de amostra nesse agregado.</div>
            </div>
          </section>
        </div>

        <footer class="ffl-bridge-modal-actions">
          <button type="button" class="ffl-btn ghost" @click="filterGraphByCoherence">Ver relacao no grafo</button>
          <button type="button" class="ffl-btn" @click="closeCdaCoherenceModal">Ok</button>
        </footer>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import GraphPanel from '@/components/GraphPanel.vue'
import EtfDailyFlowPanel from '@/components/discovery/widgets/EtfDailyFlowPanel.vue'
import {
  linePath,
  heatColor,
  flowHeatColor,
  radarBurnColor,
  radarHeatTitle,
  nportDivergingColor,
  nportCellTint,
  nportRowTint,
  nportTileBackground,
  nportCountryPillStyle,
  totalPages,
  nportTargetLabel,
  nportSideLabel,
  cdaTargetLabel,
  cdaSideLabel,
  edgeFactMetricLabel,
  portfolioSharedFactorText,
  cdaHeatTitle,
  cdaScatterTitle,
  nportHeatTitle,
  nportScatterTitle,
  nportCountryOrbitTitle,
  heatTitle,
  iciHeatTitle,
  expirationRank,
  ratioTone,
  regimeClass,
  regimeLabel,
  stressLabel,
} from '@/utils/fundsFlowWidgetModels'
import {
  tabs,
  colors,
  gridLines,
  b3FocusAssets,
  b3AssetTabs,
  FUNDS_FLOW_HISTORY_DAYS,
  nportTargets,
  nportSides,
  cdaTargets,
  cdaSides,
  cdaGraphTargets,
  moneyFlowModes,
} from '@/config/fundsFlowWidgetConfig'
import {
  buildCdaGraph,
  getCdaAssetTrailDetail,
  getCdaBridgePathDetail,
  getCdaGraphNetwork,
  getCdaMoneyTrails,
  getCdaGraphStatus,
  getCdaIssuerCrowding,
} from '@/api/cdaGraph'
import {
  getCvmCdaAssets,
  getCvmCdaDashboard,
  getCvmCdaFundHoldings,
  getCvmCdaFunds,
  getCvmCdaPositioning,
  getCvmCdaRadar,
  getFundsFlowLocalDashboard,
  getNportDashboard,
  getNportFundHoldings,
  getNportPerformance,
  getNportPositioning,
  getNportRegionAssets,
  getNportRegionFunds,
  ingestCvmCda,
  ingestNportLocal,
} from '@/api/macro'
import {
  formatBrlMillion as fmtBrlMillion,
  formatBytes as fmtBytes,
  formatCount as fmtCount,
  formatDate as fmtDate,
  formatDateTime as fmtDateTime,
  formatDays as fmtDays,
  formatLatency as fmtLatency,
  formatMoney as fmtMoney,
  formatNumber as fmtNum,
  formatPercent as fmtPctPlain,
  formatPeriodDate as fmtPeriodDate,
  formatRatio as fmtPct,
  formatSignedCount as signedCount,
  formatUsd as fmtUsd,
  formatUsdMillions as fmtUsdMn,
  movementClass as moveClass,
  ratioPercent as ratioPct,
  shortDate,
} from '@/utils/fundsFlowFormatters'
import {
  formatSourceCadence as cadenceLabel,
  getSourceStatusClass as sourceStatusClass,
  getSourceStatusLabel as sourceStatusLabel,
  hasPublicationGap as sourcePublicationGap,
} from '@/utils/fundsFlowSourceStatus'
import {
  buildCdaGraphOverlay,
  countGraphEdgesByType,
  countGraphNodesByLabel,
  inferCdaAssetBucket,
  normalizeCdaKey,
} from '@/utils/cdaGraphOverlay'

const props = defineProps({
  refreshNonce: {
    type: Number,
    default: 0,
  },
})

const activeTab = ref('overview')
const etfViewMode = ref('local_global')
const etfDailyFlowRefreshNonce = ref(0)
const b3AssetFilter = ref('ALL')
const b3EtfCategoryFilter = ref('ALL')
const period = ref('21d')
const metric = ref('nominal')
const rankingWindow = ref('21d')
const selectedIciSeries = ref(['combined|total', 'etf|total', 'mutual_fund|total_long_term', 'etf|equity', 'etf|bond'])
const refreshingSource = ref('')
const payload = ref(null)
const nportPayload = ref(null)
const cdaPayload = ref(null)
const cdaGraphStatus = ref(null)
const cdaGraphNetwork = ref(null)
const cdaGraphCrowding = ref(null)
const cdaGraphTrails = ref(null)
const loading = ref(false)
const nportLoading = ref(false)
const cdaLoading = ref(false)
const cdaRadarLoading = ref(false)
const cdaGraphLoading = ref(false)
const cdaGraphBuilding = ref(false)
const collecting = ref(false)
const error = ref('')
const nportError = ref('')
const cdaError = ref('')
const cdaRadarError = ref('')
const cdaGraphError = ref('')
const nportLoaded = ref(false)
const nportAnalyticsLoaded = ref(false)
const nportAnalyticsLoading = ref(false)
const cdaLoaded = ref(false)
const cdaAnalyticsLoaded = ref(false)
const cdaAnalyticsLoading = ref(false)
const cdaRadarLoaded = ref(false)
const cdaGraphLoaded = ref(false)
const nportPerformance = ref(null)
const nportPositioning = ref(null)
const nportRegionFunds = ref(null)
const nportRegionAssets = ref(null)
const nportFundHoldings = ref(null)
const cdaPositioning = ref(null)
const cdaFunds = ref(null)
const cdaAssets = ref(null)
const cdaFundHoldings = ref(null)
const cdaRadarPayload = ref(null)
const nportPerfWeighted = ref(false)
const nportPerfPage = ref(1)
const nportExposureTarget = ref('brazil')
const nportExposureSide = ref('long')
const nportExposurePage = ref(1)
const nportAssetTarget = ref('emerging')
const nportAssetSide = ref('long')
const nportAssetPage = ref(1)
const nportSelectedFund = ref(null)
const cdaFundTarget = ref('foreign')
const cdaFundSide = ref('long')
const cdaFundPage = ref(1)
const cdaAssetTarget = ref('private_credit')
const cdaAssetSide = ref('long')
const cdaAssetPage = ref(1)
const cdaSelectedFund = ref(null)
const cdaRadarScenario = ref('stress')
const cdaRadarMacroFilter = ref('ALL')
const cdaGraphTarget = ref('all')
const cdaGraphLimit = ref(260)
const cdaGraphIssuerFilter = ref('')
const cdaGraphFundFilter = ref('')
const cdaAssetLensFilter = ref('equity')
const cdaAssetTrailTypeFilter = ref('all')
const cdaSelectedBridgePath = ref(null)
const cdaBridgePathDetailCache = ref({})
const cdaBridgePathDetailLoading = ref(false)
const cdaBridgePathDetailError = ref('')
const cdaSelectedAssetTrail = ref(null)
const cdaAssetTrailDetailCache = ref({})
const cdaAssetTrailDetailLoading = ref(false)
const cdaAssetTrailDetailError = ref('')
const cdaSelectedCoherenceRow = ref(null)
const moneyFlowMode = ref('mixed')
let timer = null

const report = computed(() => payload.value?.report || {})
const kpis = computed(() => payload.value?.kpis || {})
const insights = computed(() => payload.value?.ai_insights || {})
const heatmap = computed(() => payload.value?.heatmap || {})
const topInflows = computed(() => payload.value?.top_inflows || [])
const topOutflows = computed(() => payload.value?.top_outflows || [])
const classRanking = computed(() => payload.value?.rankings?.by_class || [])
const fundRanking = computed(() => payload.value?.rankings?.by_fund || [])
const rankingWindowOptions = [
  { value: '1d', label: '1d' },
  { value: '5d', label: '5d' },
  { value: '21d', label: '21d' },
]
const rankingWindowLabel = computed(() => rankingWindowOptions.find(option => option.value === rankingWindow.value)?.label || '21d')
const overviewClassRanking = computed(() => (classRanking.value || []).map(item => ({
  ...item,
  displayFlow: rankingWindowFlowValue(item, rankingWindow.value),
})))
const overviewTopInflows = computed(() => overviewClassRanking.value
  .filter(item => Number(item.displayFlow || 0) > 0)
  .sort((a, b) => Number(b.displayFlow || 0) - Number(a.displayFlow || 0))
  .slice(0, 5)
  .map((item, index) => ({ ...item, rank: index + 1 })))
const overviewTopOutflows = computed(() => overviewClassRanking.value
  .filter(item => Number(item.displayFlow || 0) < 0)
  .sort((a, b) => Number(a.displayFlow || 0) - Number(b.displayFlow || 0))
  .slice(0, 5)
  .map((item, index) => ({ ...item, rank: index + 1 })))
const sources = computed(() => payload.value?.source_status || payload.value?.source_inventory || [])
const stress = computed(() => payload.value?.stress_panel || {})
const anbimaFunds = computed(() => payload.value?.anbima_funds || {})
const anbimaDaily = computed(() => anbimaFunds.value?.consolidated_daily || {})
const anbimaDailySummary = computed(() => anbimaDaily.value?.summary || {})
const anbimaValidation = computed(() => anbimaFunds.value?.validation || {})
const anbimaValidationRows = computed(() => anbimaValidation.value?.rows || [])
const anbimaTopInflows = computed(() => (anbimaDaily.value?.top_type_inflows_mtd || []).slice(0, 5))
const anbimaTopOutflows = computed(() => (anbimaDaily.value?.top_type_outflows_mtd || []).slice(0, 5))
const anbimaBulletin = computed(() => anbimaFunds.value?.bulletin || {})
const anbimaLatestArticle = computed(() => (anbimaBulletin.value?.latest_articles || [])[0] || {})
const anbimaRankings = computed(() => anbimaFunds.value?.rankings || {})
const anbimaAdminRanking = computed(() => anbimaRankings.value?.administrators || {})
const anbimaManagerRanking = computed(() => anbimaRankings.value?.managers || {})
const anbimaAdminRows = computed(() => (anbimaAdminRanking.value?.top_aum || []).slice(0, 6))
const anbimaManagerRows = computed(() => (anbimaManagerRanking.value?.top_aum || []).slice(0, 6))
const b3Investor = computed(() => payload.value?.b3_investor_participation || {})
const b3Participants = computed(() => b3Investor.value?.participants || [])
const b3TrendMap = computed(() => Object.fromEntries(
  (b3Investor.value?.trend_by_participant || []).map(item => [item.participant_type, item]),
))
const b3OpenInterest = computed(() => payload.value?.b3_open_interest || {})
const b3OiSummary = computed(() => b3OpenInterest.value?.product_summary || [])
const b3InvestorMonthly = computed(() => payload.value?.b3_investor_participation_monthly || {})
const b3MonthlyRows = computed(() => b3InvestorMonthly.value?.rows || [])
const b3MarketData = computed(() => payload.value?.b3_market_data_report || {})
const b3Etfs = computed(() => payload.value?.b3_etfs || {})
const bcbMacro = computed(() => payload.value?.bcb_macro || {})
const etfPanel = computed(() => payload.value?.etf_panel || {})
const brazilVsGlobal = computed(() => payload.value?.brazil_vs_global || {})
const iciGlobal = computed(() => brazilVsGlobal.value?.ici_global_flows || {})
const iciWeekly = computed(() => iciGlobal.value?.weekly || {})
const iciLatestByVehicle = computed(() => iciWeekly.value?.latest_by_vehicle || {})
const iciMonthlyEtf = computed(() => iciGlobal.value?.monthly_etf || {})
const iciWorldwide = computed(() => iciGlobal.value?.worldwide_quarterly || {})
const cftcPositioning = computed(() => brazilVsGlobal.value?.cftc_positioning || {})
const nportReport = computed(() => nportPayload.value?.report || {})
const nportKpis = computed(() => nportPayload.value?.kpis || {})
const nportSummaries = computed(() => nportPayload.value?.summaries || {})
const nportInsights = computed(() => nportPayload.value?.ai_readiness || {})
const nportManifest = computed(() => nportPayload.value?.manifest || [])
const nportLogs = computed(() => nportPayload.value?.logs || [])
const nportAssetRows = computed(() => nportSummaries.value?.asset_cat || [])
const nportCountryRows = computed(() => nportSummaries.value?.country || [])
const nportCurrencyRows = computed(() => nportSummaries.value?.currency || [])
const nportDerivativeRows = computed(() => nportSummaries.value?.derivative_cat || [])
const nportFairValueRows = computed(() => nportSummaries.value?.fair_value_level || [])
const nportIssuerRows = computed(() => nportPayload.value?.top_issuers || [])
const nportSecurityRows = computed(() => nportPayload.value?.top_securities || [])
const nportFundRows = computed(() => nportPayload.value?.top_funds || [])
const nportRegistrantRows = computed(() => nportPayload.value?.top_registrants || [])
const nportDebtRows = computed(() => nportPayload.value?.debt_maturity || [])
const nportPerformanceRows = computed(() => nportPerformance.value?.rows || [])
const nportRegionFundRows = computed(() => nportRegionFunds.value?.rows || [])
const nportRegionAssetRows = computed(() => nportRegionAssets.value?.rows || [])
const nportHoldingRows = computed(() => nportFundHoldings.value?.rows || [])
const nportCountryImbalanceRows = computed(() => nportPositioning.value?.country_imbalance || [])
const nportSqueezeRows = computed(() => nportPositioning.value?.squeeze_radar || [])
const nportEdgeRows = computed(() => nportPositioning.value?.edge_funds || [])
const cdaReport = computed(() => cdaPayload.value?.report || {})
const cdaKpis = computed(() => cdaPayload.value?.kpis || {})
const cdaSummaries = computed(() => cdaPayload.value?.summaries || {})
const cdaInsights = computed(() => cdaPayload.value?.ai_readiness || {})
const cdaManifest = computed(() => cdaPayload.value?.manifest || [])
const cdaLogs = computed(() => cdaPayload.value?.logs || [])
const cdaTopFunds = computed(() => cdaPayload.value?.top_funds || [])
const cdaIssuerRows = computed(() => cdaPayload.value?.top_issuers || [])
const cdaAssetSummaryRows = computed(() => cdaSummaries.value?.asset_class || [])
const cdaFundRows = computed(() => cdaFunds.value?.rows || [])
const cdaAssetRows = computed(() => cdaAssets.value?.rows || [])
const cdaHoldingRows = computed(() => cdaFundHoldings.value?.rows || [])
const cdaRadarReport = computed(() => cdaRadarPayload.value?.report || {})
const cdaRadarCoverage = computed(() => cdaRadarPayload.value?.coverage || {})
const cdaRadarSummary = computed(() => cdaRadarPayload.value?.summary || {})
const cdaRadarScenarios = computed(() => cdaRadarPayload.value?.scenarios || [])
const cdaRadarScenarioMap = computed(() => Object.fromEntries(cdaRadarScenarios.value.map(item => [item.key, item])))
const cdaRadarScenarioActive = computed(() => cdaRadarScenarioMap.value[cdaRadarScenario.value] || cdaRadarScenarios.value[0] || {})
const cdaRadarClassSummary = computed(() => cdaRadarPayload.value?.class_summary || [])
const cdaRadarBucketSummary = computed(() => cdaRadarPayload.value?.bucket_summary || [])
const cdaRadarFundAllRows = computed(() => cdaRadarPayload.value?.fund_rows || [])
const cdaRadarHeatmap = computed(() => cdaRadarPayload.value?.heatmap || {})
const cdaRadarMacroOptions = computed(() => [
  { key: 'ALL', label: 'Todos' },
  ...cdaRadarClassSummary.value
    .map(item => item?.radar_group || item?.fund_type_group || item?.macro_classe)
    .filter(Boolean)
    .map(label => ({ key: label, label })),
])
const cdaRadarFundRows = computed(() => {
  const scenarioKey = cdaRadarScenario.value || 'stress'
  const selectedClass = cdaRadarMacroFilter.value
  const rows = cdaRadarFundAllRows.value.filter(item => {
    const group = item?.radar_group || item?.fund_type_group || item?.macro_classe
    return selectedClass === 'ALL' || group === selectedClass
  })
  return [...rows]
    .sort((a, b) => {
      const aRunway = Number(a?.[`runway_days_${scenarioKey}`] ?? 999)
      const bRunway = Number(b?.[`runway_days_${scenarioKey}`] ?? 999)
      if (aRunway !== bRunway) return aRunway - bRunway
      return Number(b?.inventory_burn_pct || 0) - Number(a?.inventory_burn_pct || 0)
    })
    .slice(0, 40)
})
const cdaRadarSelectedClassSummary = computed(() => {
  if (cdaRadarMacroFilter.value === 'ALL') return cdaRadarClassSummary.value
  return cdaRadarClassSummary.value.filter((item) => {
    const group = item?.radar_group || item?.fund_type_group || item?.macro_classe
    return group === cdaRadarMacroFilter.value
  })
})
const cdaRadarTopPressureRows = computed(() => cdaRadarSelectedClassSummary.value.slice(0, 8))
const cdaRadarCards = computed(() => [
  {
    key: 'coverage_pl',
    label: 'PL coberto',
    value: fmtMoney(cdaRadarCoverage.value.matched_cda_pl),
    detail: `${fmtPctPlain(Number(cdaRadarCoverage.value.matched_cda_pl_pct || 0) * 100)} do CDA`,
    tone: 'flat',
  },
  {
    key: 'net_since',
    label: 'Fluxo desde CDA',
    value: fmtMoney(cdaRadarSummary.value.total_net_flow_since_cda),
    detail: `${fmtCount(cdaRadarSummary.value.redemption_period_days || cdaRadarCoverage.value.days_since_cda)} dias comuns`,
    tone: moveClass(cdaRadarSummary.value.total_net_flow_since_cda),
  },
  {
    key: 'gross_redemption_since',
    label: 'Resgates desde CDA',
    value: fmtMoney(cdaRadarSummary.value.total_gross_redemption_since_cda),
    detail: `${fmtCount(cdaRadarSummary.value.redemption_period_days || cdaRadarCoverage.value.days_since_cda)} dias comuns`,
    tone: Number(cdaRadarSummary.value.total_gross_redemption_since_cda || 0) > 0 ? 'down' : 'flat',
  },
  {
    key: 'sellable_technical',
    label: 'Estoque tecnico',
    value: fmtMoney(cdaRadarSummary.value.sellable_inventory_remaining),
    detail: `${fmtPctPlain(Number(cdaRadarSummary.value.inventory_burn_pct || 0) * 100)} ja consumido`,
    tone: 'flat',
  },
  {
    key: 'sellable_plausible',
    label: `Vendavel plausivel ${fmtCount(cdaRadarSummary.value.plausible_horizon_days || 30)}d`,
    value: fmtMoney(cdaRadarSummary.value.plausible_inventory_remaining),
    detail: `${fmtPctPlain(Number(cdaRadarSummary.value.plausible_inventory_burn_pct || 0) * 100)} ja consumido`,
    tone: 'flat',
  },
  {
    key: 'runway_plausible',
    label: 'Runway plausivel',
    value: fmtDays(cdaRadarScenarioMap.value.stress?.plausible_runway_days),
    detail: `tec ${fmtDays(cdaRadarScenarioMap.value.stress?.runway_days)} | ${fmtCount(cdaRadarScenarioMap.value.stress?.plausible_funds_under_5d)} fundos <5d`,
    tone: Number(cdaRadarScenarioMap.value.stress?.plausible_runway_days || 999) <= 15 ? 'warn' : 'flat',
  },
  {
    key: 'top_class',
    label: 'Tipo no radar',
    value: cdaRadarSummary.value.top_pressure_class || '-',
    detail: cdaRadarReport.value.flow_as_of_date ? `fluxo ate ${fmtDate(cdaRadarReport.value.flow_as_of_date)}` : 'cruzamento CDA x fluxo',
    tone: 'flat',
  },
  {
    key: 'negative_21d',
    label: 'Fundos 21d negativo',
    value: fmtCount(cdaRadarSummary.value.funds_with_negative_21d),
    detail: `${fmtCount(cdaRadarSummary.value.funds_at_risk_stress_5d)} em stress curto`,
    tone: Number(cdaRadarSummary.value.funds_at_risk_stress_5d || 0) > 0 ? 'warn' : 'flat',
  },
])
const cdaHeatmap = computed(() => cdaPositioning.value?.heatmap || cdaPayload.value?.heatmap || {})
const cdaConcentrationRows = computed(() => cdaPositioning.value?.concentration || cdaTopFunds.value || [])
const cdaGraphData = computed(() => {
  const graph = cdaGraphNetwork.value || {}
  if (!Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) return null
  const augmented = buildCdaGraphOverlay(
    graph,
    cdaGraphTrails.value || {},
    cdaGraphMonth.value || 'latest',
  )
  return {
    graph_id: `cvm-cda-${graph.month || 'latest'}-overlay`,
    nodes: augmented.nodes,
    edges: augmented.edges,
    node_count: augmented.nodes.length,
    edge_count: augmented.edges.length,
  }
})
const cdaGraphNodeCounts = computed(() => cdaGraphStatus.value?.graph?.nodes_by_label || [])
const cdaGraphEdgeCounts = computed(() => cdaGraphStatus.value?.graph?.edges_by_type || [])
const cdaVisibleGraphNodeCounts = computed(() => countGraphNodesByLabel(cdaGraphData.value?.nodes || []))
const cdaVisibleGraphEdgeCounts = computed(() => countGraphEdgesByType(cdaGraphData.value?.edges || []))
const cdaGraphCrowdingRows = computed(() => cdaGraphCrowding.value?.rows || [])
const cdaMoneyLayers = computed(() => cdaGraphTrails.value?.layers || [])
const cdaMoneyActivityLayers = computed(() => cdaGraphTrails.value?.activity_layers || [])
const cdaAssetClassActivity = computed(() => cdaGraphTrails.value?.asset_class_activity || [])
const cdaFundQuotaBreakdown = computed(() => cdaGraphTrails.value?.fund_quota_breakdown || [])
const cdaTargetDetails = computed(() => cdaGraphTrails.value?.target_details || {})
const cdaBridgePathDetails = computed(() => ({
  ...(cdaGraphTrails.value?.bridge_path_details || {}),
  ...cdaBridgePathDetailCache.value,
}))
const cdaAssetTrailSets = computed(() => cdaGraphTrails.value?.asset_trails || {})
const cdaAssetTrailRawCovetedRows = computed(() => cdaAssetTrailSets.value?.coveted || [])
const cdaAssetTrailRawShortedRows = computed(() => cdaAssetTrailSets.value?.shorted || [])
const cdaAssetTrailDetails = computed(() => cdaAssetTrailDetailCache.value || {})
const cdaAssetLenses = computed(() => cdaGraphTrails.value?.asset_lenses || {})
const cdaAssetLensBuckets = computed(() => cdaAssetLenses.value?.buckets || [])
const cdaAssetTrailTypeOptions = computed(() => {
  const buckets = cdaAssetLensBuckets.value
    .filter(item => item.bucket && item.bucket !== 'all')
    .filter(item => Number(item.asset_count || 0) > 0)
  return [
    {
      bucket: 'all',
      label: 'Todos',
      asset_count: cdaAssetTrailRawCovetedRows.value.length + cdaAssetTrailRawShortedRows.value.length,
    },
    ...buckets,
  ]
})
const cdaAssetTrailTypeLabel = computed(() =>
  cdaAssetTrailTypeOptions.value.find(item => item.bucket === cdaAssetTrailTypeFilter.value)?.label || 'Todos',
)
const cdaActiveAssetLensKey = computed(() => {
  const available = new Set(cdaAssetLensBuckets.value.map(item => item.bucket))
  if (available.has(cdaAssetLensFilter.value)) return cdaAssetLensFilter.value
  return cdaAssetLenses.value?.default_bucket || cdaAssetLensBuckets.value?.[0]?.bucket || 'all'
})
const cdaActiveAssetLensLabel = computed(() =>
  cdaAssetLensBuckets.value.find(item => item.bucket === cdaActiveAssetLensKey.value)?.label || 'Ativos',
)
const cdaAssetLensRows = computed(() => {
  const rows = cdaAssetLenses.value?.rows || []
  if (cdaActiveAssetLensKey.value === 'all') return rows.slice(0, 24)
  return rows.filter(item => item.bucket === cdaActiveAssetLensKey.value).slice(0, 24)
})
const cdaAssetTrailCovetedRows = computed(() =>
  cdaFilteredAssetTrailRows('coveted', cdaAssetTrailTypeFilter.value),
)
const cdaAssetTrailShortedRows = computed(() =>
  cdaFilteredAssetTrailRows('shorted', cdaAssetTrailTypeFilter.value),
)
const cdaParticipantAssetCoherence = computed(() => cdaGraphTrails.value?.participant_asset_coherence || {})
const cdaParticipantCoherenceRows = computed(() => cdaParticipantAssetCoherence.value?.rows || [])
const cdaSelectedCoherenceAssets = computed(() => cdaSelectedCoherenceRow.value?.sample_assets || [])
const cdaSelectedCoherenceEvidence = computed(() => {
  const row = cdaSelectedCoherenceRow.value || {}
  return [
    {
      label: 'B3 1d',
      value: fmtMoney(row.participant_daily_flow_brl),
      tone: moveClass(row.participant_daily_flow_brl),
    },
    {
      label: 'B3 5d',
      value: fmtMoney(row.participant_flow_5d_brl),
      tone: moveClass(row.participant_flow_5d_brl),
    },
    {
      label: 'B3 21d',
      value: fmtMoney(row.participant_flow_21d_brl),
      tone: moveClass(row.participant_flow_21d_brl),
    },
    {
      label: 'CDA compras',
      value: fmtMoney(row.bucket_buy_value),
      tone: moveClass(row.bucket_buy_value),
    },
    {
      label: 'CDA vendas',
      value: fmtMoney(row.bucket_sell_value),
      tone: Number(row.bucket_sell_value || 0) > 0 ? 'down' : 'flat',
    },
    {
      label: 'CDA liquido',
      value: fmtMoney(row.bucket_net_value),
      tone: moveClass(row.bucket_net_value),
    },
    {
      label: 'Gross CDA',
      value: fmtMoney(row.bucket_gross_value),
      tone: 'flat',
    },
    {
      label: 'Fundos / ativos',
      value: `${fmtCount(row.fund_count)} / ${fmtCount(row.asset_count)}`,
      tone: 'flat',
    },
  ]
})
const cdaOptionTriangulation = computed(() => cdaGraphTrails.value?.option_triangulation || {})
const cdaOptionTriangulationSummary = computed(() => cdaOptionTriangulation.value?.summary || {})
const cdaOptionUnderlyingRows = computed(() => cdaOptionTriangulation.value?.underlying_rows || [])
const cdaOptionPairRows = computed(() => cdaOptionTriangulation.value?.asset_pair_rows || [])
const cdaOptionFundLinkRows = computed(() => cdaOptionTriangulation.value?.fund_option_equity_links || [])
const cdaPortfolioSimilarity = computed(() => cdaGraphTrails.value?.portfolio_similarity || {})
const cdaPortfolioSummary = computed(() => cdaPortfolioSimilarity.value?.summary || {})
const cdaPortfolioPairRows = computed(() => cdaPortfolioSimilarity.value?.pairs || [])
const cdaPortfolioStructureRows = computed(() => cdaPortfolioSimilarity.value?.structures || [])
const cdaPortfolioFactorRows = computed(() => cdaPortfolioSimilarity.value?.factors || [])
const cdaPortfolioFundProfileRows = computed(() => cdaPortfolioSimilarity.value?.fund_profiles || [])
const cdaBridgePathRows = computed(() => cdaGraphTrails.value?.bridge_paths || [])
const cdaGraphExplanatoryRows = computed(() => cdaGraphTrails.value?.explanatory_connections || [])
const cdaSelectedBridgeDetail = computed(() => {
  const selected = cdaSelectedBridgePath.value
  if (!selected) return {}
  return cdaBridgePathDetails.value?.[bridgePathKey(selected)] || {}
})
const cdaSelectedBridgeFunds = computed(() => cdaSelectedBridgeDetail.value?.funds || [])
const cdaSelectedBridgeIssuers = computed(() => cdaSelectedBridgeDetail.value?.issuers || [])
const cdaSelectedBridgeAssets = computed(() => cdaSelectedBridgeDetail.value?.assets || [])
const cdaSelectedAssetTrailDetail = computed(() => {
  const selected = cdaSelectedAssetTrail.value
  if (!selected) return {}
  return cdaAssetTrailDetails.value?.[assetTrailKey(selected)] || {}
})
const cdaSelectedAssetFundLinks = computed(() => cdaSelectedAssetTrailDetail.value?.fund_links || [])
const cdaGraphMonth = computed(() =>
  cdaGraphNetwork.value?.month
  || cdaGraphStatus.value?.graph?.latest_month
  || cdaReport.value.period_label
  || 'latest')
const cdaGraphCards = computed(() => {
  const nodeCount = cdaGraphNodeCounts.value.reduce((sum, item) => sum + Number(item.count || 0), 0)
  const edgeCount = cdaGraphEdgeCounts.value.reduce((sum, item) => sum + Number(item.count || 0), 0)
  return [
    {
      key: 'nodes',
      label: 'Nos Neo4j',
      value: fmtCount(nodeCount),
      detail: `${fmtCount(cdaGraphNodeCount('CdaFund'))} fundos | ${fmtCount(cdaGraphNodeCount('CdaAsset'))} ativos`,
      tone: nodeCount > 0 ? 'up' : 'flat',
    },
    {
      key: 'edges',
      label: 'Relacoes',
      value: fmtCount(edgeCount),
      detail: `${fmtCount(cdaGraphEdgeCount('HOLDS_POSITION'))} posicoes`,
      tone: edgeCount > 0 ? 'up' : 'flat',
    },
    {
      key: 'network',
      label: 'Grafo exibido',
      value: `${fmtCount(cdaGraphNetwork.value?.node_count)} / ${fmtCount(cdaGraphNetwork.value?.edge_count)}`,
      detail: cdaGraphTarget.value === 'all' ? 'Todos os temas' : cdaTargetLabel(cdaGraphTarget.value),
      tone: 'flat',
    },
    {
      key: 'crowding',
      label: 'Crowding emissor',
      value: fmtCount(cdaGraphCrowdingRows.value.length),
      detail: cdaGraphCrowdingRows.value[0]?.issuer_name || 'sem ranking',
      tone: 'warn',
    },
  ]
})
function cdaFilteredAssetTrailRows(side, bucket) {
  const selectedBucket = bucket || 'all'
  const rawRows = side === 'shorted' ? cdaAssetTrailRawShortedRows.value : cdaAssetTrailRawCovetedRows.value
  if (selectedBucket === 'all') {
    return rawRows.map(row => normalizeCdaAssetTrailRow(row, side)).slice(0, 18)
  }

  const metric = side === 'shorted' ? 'short_value' : 'long_value'
  const rowsByLens = (cdaAssetLenses.value?.rows || [])
    .filter(row => row.bucket === selectedBucket)
    .filter(row => Math.abs(Number(row?.[metric] || 0)) > 0)
    .map(row => normalizeCdaAssetTrailRow(row, side))

  const rowsByRaw = rawRows
    .filter(row => cdaAssetTrailBucket(row) === selectedBucket)
    .map(row => normalizeCdaAssetTrailRow(row, side))

  return dedupeCdaAssetTrailRows([...rowsByLens, ...rowsByRaw])
    .sort((a, b) => Math.abs(Number(b?.[metric] || b.gross_value || 0)) - Math.abs(Number(a?.[metric] || a.gross_value || 0)))
    .slice(0, 18)
}

function normalizeCdaAssetTrailRow(row, side) {
  const bucket = row?.bucket || cdaAssetTrailBucket(row)
  const bucketLabel = row?.bucket_label || cdaAssetLensBuckets.value.find(item => item.bucket === bucket)?.label || row?.asset_class || 'Ativo'
  const resolvedSide = side === 'shorted' ? 'shorted' : 'coveted'
  const assetKey = row?.asset_key || row?.display_name || row?.asset_desc || row?.issuer_name || bucketLabel
  const assetClass = row?.asset_class || row?.tp_ativo || bucketLabel
  return {
    ...row,
    asset_key: assetKey,
    display_name: row?.display_name || row?.asset_desc || assetKey,
    asset_class: assetClass,
    bucket,
    bucket_label: bucketLabel,
    side: resolvedSide,
    trail_key: row?.trail_key || `asset-trail-${resolvedSide}-${bucket}-${assetKey}-${assetClass}`,
    tone: resolvedSide === 'shorted' ? 'down' : 'up',
  }
}

function dedupeCdaAssetTrailRows(rows) {
  const seen = new Set()
  const cleaned = []
  rows.forEach(row => {
    const key = normalizeCdaKey(`${row.asset_key}|${row.asset_class}|${row.side}`)
    if (!key || seen.has(key)) return
    seen.add(key)
    cleaned.push(row)
  })
  return cleaned
}

function cdaAssetTrailBucket(row) {
  return row?.bucket || inferCdaAssetBucket(row || {}, row?.asset_key || row?.asset_desc || row?.display_name || '')
}


const cdaMoneyModeOption = computed(() => moneyFlowModes.find(item => item.key === moneyFlowMode.value) || moneyFlowModes[0])
const cdaMoneyModeDetail = computed(() => cdaMoneyModeOption.value.detail)
const cdaMixedMoneyTargets = computed(() => cdaMoneyLayers.value.slice(0, 6).map(item => ({
  ...item,
  display: fmtMoney(item.net_value),
  secondary_display: `${fmtMoney(item.gross_value)} gross`,
})))
const cdaQuarterlyCdaTargets = computed(() => cdaMoneyActivityLayers.value
  .slice()
  .sort((a, b) => Math.abs(Number(b.reported_activity ?? b.net_value ?? 0)) - Math.abs(Number(a.reported_activity ?? a.net_value ?? 0)))
  .slice(0, 3)
  .map(item => {
    const net = Number(item.reported_activity ?? item.net_value ?? 0)
    const gross = Number(item.buy_value || 0) + Number(item.sell_value || 0) || Number(item.gross_value || 0)
    return {
      ...item,
      target: `cda-${item.target}`,
      target_label: `CDA ${item.target_label || item.target}`,
      net_value: net,
      gross_value: gross,
      display: fmtMoney(net),
      secondary_display: `${fmtMoney(gross)} giro`,
      top_issuers: [item.top_issuer].filter(Boolean),
      top_asset_classes: [item.top_asset_class].filter(Boolean),
    }
  }))
const cdaNportCountryRows = computed(() => nportCountryImbalanceRows.value
  .slice()
  .sort((a, b) => Math.abs(Number(b.net_value || 0)) - Math.abs(Number(a.net_value || 0)))
  .slice(0, 8))
const cdaQuarterlyNportTargets = computed(() => cdaNportCountryRows.value.slice(0, 3).map(item => ({
  target: `nport-${item.investment_country}`,
  target_label: `NPORT ${item.investment_country}`,
  name: item.investment_country,
  net_value: Number(item.net_value || 0),
  gross_value: Number(item.gross_value || 0),
  display: fmtUsd(item.net_value),
  secondary_display: `${fmtCount(item.fund_count)} fundos`,
  fund_count: item.fund_count,
  holding_count: item.holding_count,
  top_issuers: [],
  top_asset_classes: [],
})))
const cdaQuarterlyMoneyTargets = computed(() => [
  ...cdaQuarterlyCdaTargets.value,
  ...cdaQuarterlyNportTargets.value,
].slice(0, 6))
const cdaDailyClassRows = computed(() => {
  const rows = [
    ...topInflows.value.slice(0, 4).map((item, index) => ({ item, index, side: 'in' })),
    ...topOutflows.value.slice(0, 4).map((item, index) => ({ item, index, side: 'out' })),
  ]
  const seen = new Set()
  return rows
    .map(({ item, index, side }) => {
      const name = item.name || item.macro_classe || item.subclasse || `Classe ${index + 1}`
      const key = `${side}-${name}`
      if (seen.has(key)) return null
      seen.add(key)
      const value = classFlowValue(item)
      return {
        key,
        name,
        value,
        detail: `${side === 'in' ? 'entrada' : 'saida'} | z ${fmtNum(item.zscore_21d ?? item.zscore ?? 0, 2)}`,
      }
    })
    .filter(item => item && Number.isFinite(item.value) && item.value !== 0)
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
    .slice(0, 8)
})
const cdaDailyParticipantRows = computed(() => b3ParticipantBars.value.slice(0, 8))
const cdaDailyOiRows = computed(() => b3OiMainSummary.value
  .slice()
  .sort((a, b) => Math.abs(Number(b.rolling_21d_variation_open_interest || 0)) - Math.abs(Number(a.rolling_21d_variation_open_interest || 0)))
  .slice(0, 8))
const cdaDailyWeeklyMoneyTargets = computed(() => {
  const iciTargets = [...cdaIciInflowLegs.value.slice(0, 2), ...cdaIciOutflowLegs.value.slice(0, 2)]
    .slice(0, 3)
    .map(item => ({
      target: `ici-${item.key}`,
      target_label: item.label.replace('combined | ', 'ICI '),
      net_value: Number(item.value || 0),
      gross_value: Math.abs(Number(item.value || 0)),
      display: fmtUsdMn(item.value),
      secondary_display: 'semanal',
    }))
  const localTargets = cdaDailyClassRows.value.slice(0, 2).map(item => ({
    target: `local-${item.key}`,
    target_label: item.name,
    net_value: Number(item.value || 0) / 1_000_000,
    gross_value: Math.abs(Number(item.value || 0)) / 1_000_000,
    display: fmtMoney(item.value),
    secondary_display: period.value,
  }))
  const b3Targets = cdaDailyParticipantRows.value.slice(0, 1).map(item => ({
    target: `b3-${item.participant_type}`,
    target_label: `B3 ${item.participant_type}`,
    net_value: Number(item.rolling_21d_net_flow_brl || 0) / 1_000_000,
    gross_value: Math.abs(Number(item.rolling_21d_net_flow_brl || 0)) / 1_000_000,
    display: fmtMoney(item.rolling_21d_net_flow_brl),
    secondary_display: 'participante 21d',
  }))
  const oiTargets = cdaDailyOiRows.value.slice(0, 1).map(item => ({
    target: `oi-${item.asset}`,
    target_label: `OI ${item.asset}`,
    net_value: Number(item.rolling_21d_variation_open_interest || 0) / 1_000,
    gross_value: Math.abs(Number(item.rolling_21d_variation_open_interest || 0)) / 1_000,
    display: signedCount(item.rolling_21d_variation_open_interest),
    secondary_display: 'contratos 21d',
  }))
  return [...iciTargets, ...localTargets, ...b3Targets, ...oiTargets].slice(0, 6)
})
const cdaMoneyMapTargets = computed(() => {
  if (moneyFlowMode.value === 'quarterly') return cdaQuarterlyMoneyTargets.value
  if (moneyFlowMode.value === 'daily_weekly') return cdaDailyWeeklyMoneyTargets.value
  return cdaMixedMoneyTargets.value
})
const cdaMoneySideLayers = computed(() => cdaMoneyMapTargets.value.slice(0, 7))
const cdaMoneyLayerMax = computed(() => Math.max(
  1,
  ...cdaMoneyMapTargets.value.map(item => Math.abs(Number(item.gross_value || item.abs_value || 0))),
))
const cdaMoneyNetMax = computed(() => Math.max(
  1,
  ...cdaMoneySideLayers.value.map(item => Math.abs(Number(item.net_value || 0))),
))
const cdaMoneyTotalGross = computed(() => cdaMoneyMapTargets.value.reduce((sum, item) => sum + Math.abs(Number(item.gross_value || 0)), 0))
const cdaMoneyCore = computed(() => {
  if (moneyFlowMode.value === 'quarterly') {
    return {
      label: 'CDA + N-PORT',
      value: `${fmtCount(cdaGraphNodeCount('CdaFund'))} BR | ${fmtCount(nportKpis.value.funds)} US`,
      detail: `${cdaGraphMonth.value} + ${nportReport.value.quarter || 'NPORT'}`,
    }
  }
  if (moneyFlowMode.value === 'daily_weekly') {
    return {
      label: 'Fluxos freq. alta',
      value: `${fmtDate(report.value.as_of_date)} | ${fmtDate(iciLatestDate.value)}`,
      detail: `B3 ${fmtDate(b3OpenInterest.value?.date || b3Investor.value?.data_until)}`,
    }
  }
  return {
    label: 'Carteiras CDA Brasil',
    value: `${fmtCount(cdaGraphNodeCount('CdaFund'))} fundos`,
    detail: `${fmtMoney(cdaMoneyTotalGross.value)} gross mapeado`,
  }
})
const cdaReductionRows = computed(() => cdaAssetClassActivity.value
  .filter(item => Number(item.net_reduction_value || item.sell_value || 0) > 0)
  .slice()
  .sort((a, b) => Number(b.net_reduction_value || b.sell_value || 0) - Number(a.net_reduction_value || a.sell_value || 0))
  .slice(0, 8))
const cdaFundQuotaRows = computed(() => cdaFundQuotaBreakdown.value
  .slice()
  .sort((a, b) => Math.abs(Number(b.reported_activity || 0)) - Math.abs(Number(a.reported_activity || 0)))
  .slice(0, 8))
const cdaSelectedTargetKey = computed(() => (cdaGraphTarget.value === 'all' ? 'fund_quotas' : cdaGraphTarget.value) || 'foreign')
const cdaSelectedTargetDetail = computed(() => cdaTargetDetails.value?.[cdaSelectedTargetKey.value] || {})
const cdaSelectedTargetLabel = computed(() => cdaSelectedTargetDetail.value?.target_label || cdaTargetLabel(cdaSelectedTargetKey.value))
const cdaSelectedTargetBuys = computed(() => (cdaSelectedTargetDetail.value?.top_buy_funds || []).slice(0, 5))
const cdaSelectedTargetSells = computed(() => (cdaSelectedTargetDetail.value?.top_sell_funds || []).slice(0, 5))
const cdaIciFlowLegs = computed(() => {
  const rows = iciLatestWeeklyRows.value.length
    ? iciLatestWeeklyRows.value
    : iciGlobalRows.value
  return rows.map(item => ({
    key: `${item.vehicle || item.source || 'ici'}-${item.category_key || item.category || item.date}`,
    label: `${item.vehicle || item.source || 'ICI'} | ${item.category || item.category_key || 'Total'}`,
    value: Number(item.flow_usd_mn ?? item.total_flow_usd_mn ?? 0),
  })).filter(item => Number.isFinite(item.value) && item.value !== 0)
})
const cdaIciInflowLegs = computed(() => cdaIciFlowLegs.value
  .filter(item => item.value > 0)
  .sort((a, b) => b.value - a.value)
  .slice(0, 6))
const cdaIciOutflowLegs = computed(() => cdaIciFlowLegs.value
  .filter(item => item.value < 0)
  .sort((a, b) => a.value - b.value)
  .slice(0, 6))
const cdaMixedMoneySources = computed(() => {
  const iciCombined = Number(iciLatestByVehicle.value.combined?.total_flow_usd_mn || 0)
  const b3Foreign = Number(b3MarketSummary.value?.foreign_balance_brl_million || 0) * 1_000_000
  const localFlow = Number(kpis.value.net_flow_21d || 0)
  const totalReductions = cdaReductionRows.value.reduce((sum, item) => sum + Number(item.net_reduction_value || item.sell_value || 0), 0)
  const equityReductionRow = cdaAssetClassActivity.value.find(item => item.asset_class === 'Acoes') || {}
  const equityReduction = Number(equityReductionRow.net_reduction_value || equityReductionRow.sell_value || 0)
  const ratesReduction = cdaAssetClassActivity.value
    .filter(item => ['Titulos Publicos', 'Credito Privado', 'Depositos e IF', 'Agronegocio/Credito'].includes(item.asset_class))
    .reduce((sum, item) => sum + Number(item.net_reduction_value || item.sell_value || 0), 0)
  return [
    {
      key: 'ici',
      label: 'Fluxo externo ICI',
      value: iciCombined,
      abs_value: Math.abs(iciCombined),
      display: fmtUsdMn(iciCombined),
      tone: moveClass(iciCombined),
    },
    {
      key: 'b3_foreign',
      label: 'Estrangeiro B3',
      value: b3Foreign,
      abs_value: Math.abs(b3Foreign),
      display: fmtMoney(b3Foreign),
      tone: moveClass(b3Foreign),
    },
    {
      key: 'local_funds',
      label: 'Fluxo Brasil fundos',
      value: localFlow,
      abs_value: Math.abs(localFlow),
      display: fmtMoney(localFlow),
      tone: moveClass(localFlow),
    },
    {
      key: 'reductions',
      label: 'Reducoes CDA',
      value: -Math.abs(totalReductions),
      abs_value: Math.abs(totalReductions),
      display: fmtMoney(-Math.abs(totalReductions)),
      tone: totalReductions > 0 ? 'down' : 'flat',
    },
    {
      key: 'equity_reduction',
      label: 'Diminuicao acoes',
      value: -Math.abs(equityReduction),
      abs_value: Math.abs(equityReduction),
      display: fmtMoney(-Math.abs(equityReduction)),
      tone: equityReduction > 0 ? 'down' : 'flat',
    },
    {
      key: 'rates_credit_reduction',
      label: 'Reducao titulos/credito',
      value: -Math.abs(ratesReduction),
      abs_value: Math.abs(ratesReduction),
      display: fmtMoney(-Math.abs(ratesReduction)),
      tone: ratesReduction > 0 ? 'down' : 'flat',
    },
  ]
})
const cdaQuarterlyMoneySources = computed(() => {
  const buy = cdaMoneyActivityLayers.value.reduce((sum, item) => sum + Number(item.buy_value || 0), 0)
  const sell = cdaMoneyActivityLayers.value.reduce((sum, item) => sum + Number(item.sell_value || item.reductions_value || 0), 0)
  const net = cdaMoneyActivityLayers.value.reduce((sum, item) => sum + Number(item.reported_activity || 0), 0)
  const nportFlow = Number(nportKpis.value.net_flow_3m || 0)
  const nportShort = -Math.abs(Number(nportKpis.value.short_value || 0))
  const nportDerivatives = Number(nportKpis.value.derivative_value || 0)
  return [
    {
      key: 'cda_buy',
      label: 'CDA compras',
      value: buy,
      abs_value: Math.abs(buy),
      display: fmtMoney(buy),
      tone: 'up',
    },
    {
      key: 'cda_sell',
      label: 'CDA vendas/reduc.',
      value: -Math.abs(sell),
      abs_value: Math.abs(sell),
      display: fmtMoney(-Math.abs(sell)),
      tone: sell > 0 ? 'down' : 'flat',
    },
    {
      key: 'cda_net',
      label: 'CDA saldo atividade',
      value: net,
      abs_value: Math.abs(net),
      display: fmtMoney(net),
      tone: moveClass(net),
    },
    {
      key: 'nport_flow',
      label: 'N-PORT fluxo 3m',
      value: nportFlow,
      abs_value: Math.abs(nportFlow),
      display: fmtUsd(nportFlow),
      tone: moveClass(nportFlow),
    },
    {
      key: 'nport_short',
      label: 'N-PORT short book',
      value: nportShort,
      abs_value: Math.abs(nportShort),
      display: fmtUsd(nportShort),
      tone: nportShort < 0 ? 'down' : 'flat',
    },
    {
      key: 'nport_deriv',
      label: 'N-PORT derivativos',
      value: nportDerivatives,
      abs_value: Math.abs(nportDerivatives),
      display: fmtUsd(nportDerivatives),
      tone: moveClass(nportDerivatives),
    },
  ]
})
const cdaDailyWeeklyMoneySources = computed(() => {
  const iciCombined = Number(iciLatestByVehicle.value.combined?.total_flow_usd_mn || 0)
  const iciEtf = Number(iciLatestByVehicle.value.etf?.total_flow_usd_mn || 0)
  const b3Foreign = Number(b3MarketSummary.value?.foreign_balance_brl_million || 0) * 1_000_000
  const participantNet = cdaDailyParticipantRows.value.reduce((sum, item) => sum + Number(item.rolling_21d_net_flow_brl || 0), 0)
  const oiNet = cdaDailyOiRows.value.reduce((sum, item) => sum + Number(item.rolling_21d_variation_open_interest || 0), 0)
  const localFlow = Number(kpis.value.net_flow_21d || 0)
  const anbimaDay = Number(anbimaDailySummary.value.net_flow_day_brl || 0)
  return [
    {
      key: 'ici_weekly',
      label: 'ICI semanal',
      value: iciCombined,
      abs_value: Math.abs(iciCombined),
      display: fmtUsdMn(iciCombined),
      tone: moveClass(iciCombined),
    },
    {
      key: 'ici_etf',
      label: 'ICI ETF semanal',
      value: iciEtf,
      abs_value: Math.abs(iciEtf),
      display: fmtUsdMn(iciEtf),
      tone: moveClass(iciEtf),
    },
    {
      key: 'b3_foreign_daily',
      label: 'B3 estrangeiro',
      value: b3Foreign,
      abs_value: Math.abs(b3Foreign) / 1_000_000,
      display: fmtMoney(b3Foreign),
      tone: moveClass(b3Foreign),
    },
    {
      key: 'b3_participants',
      label: 'B3 participantes',
      value: participantNet,
      abs_value: Math.abs(participantNet) / 1_000_000,
      display: fmtMoney(participantNet),
      tone: moveClass(participantNet),
    },
    {
      key: 'local_cvm',
      label: 'CVM fundos 21d',
      value: localFlow,
      abs_value: Math.abs(localFlow) / 1_000_000,
      display: fmtMoney(localFlow),
      tone: moveClass(localFlow),
    },
    {
      key: 'b3_oi',
      label: 'OI futuros 21d',
      value: oiNet,
      abs_value: Math.abs(oiNet) / 1_000,
      display: signedCount(oiNet),
      tone: moveClass(oiNet),
    },
    {
      key: 'anbima_day',
      label: 'ANBIMA dia',
      value: anbimaDay,
      abs_value: Math.abs(anbimaDay) / 1_000_000,
      display: fmtMoney(anbimaDay),
      tone: moveClass(anbimaDay),
    },
  ].filter(item => Number.isFinite(Number(item.value)) && (item.value !== 0 || item.key === 'b3_oi'))
})
const cdaMoneyMapSources = computed(() => {
  if (moneyFlowMode.value === 'quarterly') return cdaQuarterlyMoneySources.value
  if (moneyFlowMode.value === 'daily_weekly') return cdaDailyWeeklyMoneySources.value
  return cdaMixedMoneySources.value
})
const cdaMoneySourceMax = computed(() => Math.max(
  1,
  ...cdaMoneyMapSources.value.map(item => Math.abs(Number(item.abs_value || 0))),
))
const cdaGraphEdgeFacts = computed(() => {
  const rows = []
  const seen = new Set()
  const add = (item, priority = 0) => {
    if (!item?.fact) return
    const key = `${item.name || item.fact_type || ''}|${item.fact}`.toLowerCase()
    if (seen.has(key)) return
    seen.add(key)
    const metrics = item.metrics || item.attributes || {}
    const score = Number(item.score ?? metrics.gross_value ?? metrics.abs_value_market ?? metrics.value_market ?? 0)
    const directionValue = metrics.reported_activity ?? metrics.net_value ?? metrics.value_market ?? score
    rows.push({
      uuid: item.uuid || `cda-edge-fact-${rows.length}`,
      name: item.name || item.fact_type || 'CONEXAO',
      fact: item.fact,
      fact_type: item.fact_type,
      category: item.category,
      tone: item.tone || moveClass(directionValue),
      score: Number.isFinite(score) ? Math.abs(score) : 0,
      priority,
      metric_label: item.metric_label || edgeFactMetricLabel(metrics),
    })
  }

  cdaGraphExplanatoryRows.value.forEach(item => add(item, 2))
  ;(cdaGraphNetwork.value?.edges || [])
    .slice()
    .sort((a, b) => Math.abs(Number(b.attributes?.abs_value_market || b.attributes?.gross_value || 0)) - Math.abs(Number(a.attributes?.abs_value_market || a.attributes?.gross_value || 0)))
    .forEach(edge => add({
      ...edge,
      category: edge.fact_type === 'HOLDS_POSITION' ? 'Aresta visivel' : 'Contexto',
      score: Math.abs(Number(edge.attributes?.abs_value_market || edge.attributes?.gross_value || edge.attributes?.value_market || 0)),
    }, 1))

  return rows
    .sort((a, b) => (b.priority - a.priority) || (b.score - a.score))
    .slice(0, 24)
})
const cdaFundMax = computed(() => Math.max(1, ...cdaFundRows.value.map(item => Math.abs(Number(item.selected_value || 0)))))
const cdaAssetMax = computed(() => Math.max(1, ...cdaAssetRows.value.map(item => Math.abs(Number(item.selected_value || 0)))))
const cdaHoldingMax = computed(() => Math.max(1, ...cdaHoldingRows.value.map(item => Math.abs(Number(item.value_market || 0)))))
const cdaHeatmapMax = computed(() => Math.max(
  1,
  ...(cdaHeatmap.value.cells || []).map(cell => Math.abs(Number(cell.value || 0))),
))
const cdaHeatmapRows = computed(() => {
  const xs = cdaHeatmap.value.x || []
  const ys = cdaHeatmap.value.y || []
  const cells = new Map((cdaHeatmap.value.cells || []).map(cell => [`${cell.fund_type}|${cell.asset_class}`, cell]))
  return ys.map(fundType => ({
    fund_type: fundType,
    cells: xs.map(asset => cells.get(`${fundType}|${asset}`) || {
      fund_type: fundType,
      asset_class: asset,
      value: 0,
      abs_value: 0,
      fund_count: 0,
      holding_count: 0,
    }),
  }))
})
const cdaHeatmapStyle = computed(() => ({
  gridTemplateColumns: `136px repeat(${Math.max((cdaHeatmap.value.x || []).length, 1)}, minmax(78px, 1fr))`,
}))
const cdaRadarHeatmapRows = computed(() => {
  const xs = cdaRadarHeatmap.value.x || []
  const ys = cdaRadarHeatmap.value.y || []
  const cells = new Map((cdaRadarHeatmap.value.cells || []).map((cell) => {
    const group = cell.radar_group || cell.fund_type_group || cell.macro_classe
    return [`${group}|${cell.bucket_label}`, cell]
  }))
  return ys.map(macro => ({
    macro_classe: macro,
    cells: xs.map(bucket => cells.get(`${macro}|${bucket}`) || {
      macro_classe: macro,
      radar_group: macro,
      fund_type_group: macro,
      bucket_label: bucket,
      burn_pct: 0,
      plausible_burn_pct: 0,
      remaining_inventory: 0,
      plausible_remaining_inventory: 0,
      consumed_since_cda: 0,
      plausible_consumed_since_cda: 0,
      fund_count: 0,
    }),
  }))
})
const cdaRadarHeatmapStyle = computed(() => ({
  gridTemplateColumns: `164px repeat(${Math.max((cdaRadarHeatmap.value.x || []).length, 1)}, minmax(92px, 1fr))`,
}))
const cdaRadarBucketMax = computed(() => Math.max(
  1,
  ...(cdaRadarBucketSummary.value || []).map(item => Math.abs(Number(item.free_inventory_remaining || 0))),
))
const cdaSelectedFundName = computed(() =>
  cdaSelectedFund.value?.fund_name
  || cdaFundHoldings.value?.fund?.fund_name
  || cdaFundHoldings.value?.fund?.fund_cnpj
  || 'Selecione um fundo')
const cdaCards = computed(() => [
  {
    key: 'funds',
    label: 'Fundos',
    value: fmtCount(cdaKpis.value.funds),
    detail: `${fmtCount(cdaKpis.value.holdings)} posicoes`,
    tone: 'flat',
  },
  {
    key: 'pl',
    label: 'PL reportado',
    value: fmtMoney(cdaKpis.value.total_pl),
    detail: cdaReport.value.period_label || '-',
    tone: 'flat',
  },
  {
    key: 'value',
    label: 'Valor carteira',
    value: fmtMoney(cdaKpis.value.reported_abs_value),
    detail: `${fmtCount(cdaKpis.value.securities)} ativos`,
    tone: 'flat',
  },
  {
    key: 'foreign',
    label: 'Exterior',
    value: fmtMoney(cdaKpis.value.foreign_value),
    detail: 'estoque CDA',
    tone: moveClass(cdaKpis.value.foreign_value),
  },
  {
    key: 'conf',
    label: 'Confidencial',
    value: fmtMoney(cdaKpis.value.confidential_value),
    detail: `${fmtCount(cdaKpis.value.funds_confidential_gt_10)} fundos >10%`,
    tone: Number(cdaKpis.value.confidential_value || 0) > 0 ? 'warn' : 'flat',
  },
  {
    key: 'concentration',
    label: 'Concentracao media',
    value: fmtPctPlain(cdaKpis.value.avg_concentration_pct),
    detail: `${fmtCount(cdaKpis.value.funds_concentration_gt_25)} fundos >25%`,
    tone: Number(cdaKpis.value.avg_concentration_pct || 0) > 25 ? 'warn' : 'flat',
  },
])
const cdaScatterScale = computed(() => {
  const rows = cdaConcentrationRows.value.slice(0, 100)
  const xMax = Math.max(1, ...rows.map(item => Math.abs(Number(item.concentration_pct || 0))))
  const yMax = Math.max(1, ...rows.map(item => Math.abs(Number(item.foreign_pct_pl || 0) + Number(item.confidential_pct_pl || 0))))
  return { xMax, yMax }
})
const cdaScatterPoints = computed(() => cdaConcentrationRows.value.slice(0, 100).map((item, index) => {
  const width = 706
  const height = 230
  const xValue = Number(item.concentration_pct || 0)
  const yValue = Number(item.foreign_pct_pl || 0) + Number(item.confidential_pct_pl || 0)
  const pl = Math.max(Number(item.pl || 0), 1)
  return {
    ...item,
    x: 42 + Math.min(xValue / cdaScatterScale.value.xMax, 1) * width,
    y: 258 - Math.min(yValue / cdaScatterScale.value.yMax, 1) * height,
    r: 3 + Math.min(Math.log10(pl) / 13, 1) * 8,
    color: yValue > 30 ? '#fb7185' : index % 2 ? '#60a5fa' : '#2dd4bf',
  }
}))
const cdaClassTiles = computed(() => {
  const rows = cdaAssetSummaryRows.value.slice(0, 18)
  const maxValue = Math.max(1, ...rows.map(item => Math.abs(Number(item.abs_value || item.value || 0))))
  return rows.map(item => {
    const value = Math.abs(Number(item.abs_value || item.value || 0))
    const strength = Math.min(value / maxValue, 1)
    return {
      ...item,
      style: {
        flexGrow: `${0.7 + strength * 4.4}`,
        flexBasis: `${120 + strength * 130}px`,
        minHeight: `${70 + strength * 50}px`,
        background: nportTileBackground(Number(item.value || 0), strength),
        borderColor: 'rgba(45, 212, 191, 0.24)',
      },
      title: `${item.label} | ${fmtMoney(item.value)} | ${fmtCount(item.fund_count)} fundos`,
    }
  })
})
const nportHeatmap = computed(() => nportPositioning.value?.heatmap || {})
const nportHeatmapMax = computed(() => Math.max(
  1,
  ...(nportHeatmap.value.cells || []).map(cell => Math.abs(Number(cell.net_value || 0))),
))
const nportHeatmapRows = computed(() => {
  const xs = nportHeatmap.value.x || []
  const ys = nportHeatmap.value.y || []
  const cells = new Map((nportHeatmap.value.cells || []).map(cell => [`${cell.country}|${cell.asset_cat}`, cell]))
  return ys.map(country => ({
    country,
    cells: xs.map(asset => cells.get(`${country}|${asset}`) || {
      country,
      asset_cat: asset,
      net_value: 0,
      long_value: 0,
      short_value: 0,
      gross_value: 0,
      fund_count: 0,
    }),
  }))
})
const nportHeatmapStyle = computed(() => ({
  gridTemplateColumns: `76px repeat(${Math.max((nportHeatmap.value.x || []).length, 1)}, minmax(58px, 1fr))`,
}))
const nportSelectedFundName = computed(() =>
  nportSelectedFund.value?.series_name
  || nportFundHoldings.value?.fund?.series_name
  || nportFundHoldings.value?.fund?.accession_number
  || 'Selecione um fundo')
const nportQuadrantRows = computed(() => (nportPositioning.value?.fund_quadrant || []).slice(0, 90))
const nportQuadrantScale = computed(() => {
  const xValues = nportQuadrantRows.value.map(item => Number(item.max_holding_pct || 0)).filter(Number.isFinite)
  const yValues = nportQuadrantRows.value.map(item => Number(item.net_pct_aum || 0)).filter(Number.isFinite)
  const xMax = Math.max(1, ...xValues)
  let yMin = Math.min(0, ...yValues)
  let yMax = Math.max(1, ...yValues)
  if (yMin === yMax) {
    yMin -= 1
    yMax += 1
  }
  return { xMax, yMin, yMax }
})
const nportScatterPoints = computed(() => {
  const width = 706
  const height = 230
  const left = 42
  const top = 28
  const scale = nportQuadrantScale.value
  return nportQuadrantRows.value.map((item, index) => {
    const xValue = Number(item.max_holding_pct || 0)
    const yValue = Number(item.net_pct_aum || 0)
    const aum = Math.max(Number(item.net_assets || 0), 1)
    const radius = 3 + Math.min(Math.log10(aum) / 12, 1) * 8
    return {
      ...item,
      color: Number(item.return_3m_pct || 0) >= 0 ? '#34d399' : '#fb7185',
      x: left + Math.min(xValue / Math.max(scale.xMax, 1), 1) * width,
      y: top + height - ((yValue - scale.yMin) / Math.max(scale.yMax - scale.yMin, 1)) * height,
      r: radius,
      opacity: 0.42 + Math.min(index / Math.max(nportQuadrantRows.value.length, 1), 1) * 0.12,
    }
  })
})
const nportScatterZeroY = computed(() => {
  const scale = nportQuadrantScale.value
  return 28 + 230 - ((0 - scale.yMin) / Math.max(scale.yMax - scale.yMin, 1)) * 230
})
const nportCountryOrbitPoints = computed(() => {
  const rows = nportCountryImbalanceRows.value.slice(0, 18)
  const grossMax = Math.max(1, ...rows.map(item => Math.abs(Number(item.gross_value || 0))))
  return rows.map((item, index) => {
    const angle = -Math.PI / 2 + (index / Math.max(rows.length, 1)) * Math.PI * 2
    const gross = Math.abs(Number(item.gross_value || 0))
    const radius = 58 + Math.sqrt(gross / grossMax) * 106
    const x = 395 + Math.cos(angle) * radius
    const y = 165 + Math.sin(angle) * radius
    const bubble = 5 + Math.sqrt(gross / grossMax) * 14
    const net = Number(item.net_to_gross_pct || 0)
    const shortIntensity = Number(item.short_intensity_pct || 0)
    return {
      ...item,
      x,
      y,
      r: bubble,
      labelX: x + (Math.cos(angle) >= 0 ? bubble + 6 : -bubble - 6),
      labelY: y + 3,
      anchor: Math.cos(angle) >= 0 ? 'start' : 'end',
      color: nportDivergingColor(net, 100),
      opacity: 0.22 + Math.min(shortIntensity / 70, 1) * 0.58,
    }
  })
})
const nportCountryBarbellRows = computed(() => {
  const rows = nportCountryImbalanceRows.value.slice(0, 16)
  const maxValue = Math.max(
    1,
    ...rows.flatMap(item => [Math.abs(Number(item.long_value || 0)), Math.abs(Number(item.short_value || 0))]),
  )
  return rows.map(item => ({
    ...item,
    longWidth: Math.min(Math.abs(Number(item.long_value || 0)) / maxValue, 1) * 48,
    shortWidth: Math.min(Math.abs(Number(item.short_value || 0)) / maxValue, 1) * 48,
  }))
})
const nportCrowdingTiles = computed(() => {
  const rows = nportRegionAssetRows.value.slice(0, 18)
  const maxValue = Math.max(1, ...rows.map(item => Math.abs(Number(item.selected_value || 0))))
  return rows.map(item => {
    const value = Math.abs(Number(item.selected_value || 0))
    const signed = nportAssetSide.value === 'short' ? -value : value
    const strength = Math.min(value / maxValue, 1)
    const label = item.issuer_title || item.issuer_name || item.security_key || '-'
    return {
      ...item,
      label,
      style: {
        flexGrow: `${0.7 + strength * 3.8}`,
        flexBasis: `${116 + strength * 124}px`,
        minHeight: `${72 + strength * 42}px`,
        background: nportTileBackground(signed, strength),
        borderColor: nportAssetSide.value === 'short' ? 'rgba(248, 113, 113, 0.32)' : 'rgba(45, 212, 191, 0.3)',
      },
      title: `${label} | ${item.investment_country} | ${fmtUsd(item.selected_value)} | fundos ${fmtCount(item.fund_count)}`,
    }
  })
})
const nportRidgeRows = computed(() => {
  const rows = nportEdgeRows.value.slice(0, 14)
  const maxExposure = Math.max(1, ...rows.map(item => Math.abs(Number(item.net_pct_aum || 0))))
  const maxReturn = Math.max(1, ...rows.map(item => Math.abs(Number(item.return_3m_pct || 0))))
  return rows.map(item => ({
    ...item,
    exposureWidth: Math.min(Math.abs(Number(item.net_pct_aum || 0)) / maxExposure, 1) * 100,
    returnWidth: Math.min(Math.abs(Number(item.return_3m_pct || 0)) / maxReturn, 1) * 100,
  }))
})
const b3MarketSummary = computed(() => {
  const summary = b3MarketData.value?.summary || null
  return summary && Object.keys(summary).length ? summary : null
})
const b3OiMainSummary = computed(() => {
  const byAsset = Object.fromEntries((b3OiSummary.value || []).map(item => [item.asset, item]))
  return b3FocusAssets.map(asset => byAsset[asset]).filter(Boolean)
})
const b3OiOverviewRows = computed(() => b3OiMainSummary.value.map(item => ({
  ...item,
  variation_open_interest: Number(item.variation_open_interest || 0),
  open_interest: Number(item.open_interest || 0),
})))
const b3PositioningStatus = computed(() => b3OpenInterest.value?.participant_positioning || {})
const b3ParticipantBars = computed(() => (b3Investor.value?.trend_by_participant || [])
  .slice()
  .sort((a, b) => Math.abs(Number(b.rolling_21d_net_flow_brl || 0)) - Math.abs(Number(a.rolling_21d_net_flow_brl || 0))))
const b3ParticipantOverviewRows = computed(() => (b3Investor.value?.trend_by_participant || [])
  .slice()
  .map(item => ({
    ...item,
    daily_net_flow_brl: Number(item.daily_net_flow_brl || 0),
    net_flow_brl_mtd: Number(item.net_flow_brl_mtd || 0),
  }))
  .sort((a, b) => Math.abs(Number(b.daily_net_flow_brl || 0)) - Math.abs(Number(a.daily_net_flow_brl || 0))))
const oiOverviewBarMax = computed(() => Math.max(
  ...b3OiOverviewRows.value.map(item => Math.abs(Number(item.variation_open_interest || 0))),
  1,
))
const participantOverviewBarMax = computed(() => Math.max(
  ...b3ParticipantOverviewRows.value.map(item => Math.abs(Number(item.daily_net_flow_brl || 0))),
  1,
))
const b3ContractTotals = computed(() => Object.fromEntries(
  b3OiMainSummary.value.map(item => [item.asset, Number(item.open_interest || 0)]),
))
const b3ContractRows = computed(() => {
  const rows = (b3OpenInterest.value?.latest_contracts || [])
    .filter(item => b3FocusAssets.includes(item.asset))
    .filter(item => b3AssetFilter.value === 'ALL' || item.asset === b3AssetFilter.value)
    .map(item => ({
      ...item,
      share_open_interest: Number(item.open_interest || 0) / Math.max(Number(b3ContractTotals.value[item.asset] || 0), 1) * 100,
    }))
  return rows.sort((a, b) => {
    const assetDiff = b3FocusAssets.indexOf(a.asset) - b3FocusAssets.indexOf(b.asset)
    if (assetDiff) return assetDiff
    return expirationRank(a.expiration_code) - expirationRank(b.expiration_code)
  })
})

const b3EtfCategoryTabs = computed(() => {
  const categories = [...new Set((b3Etfs.value?.funds || []).map(item => item.category).filter(Boolean))]
  return ['ALL', ...categories]
})

const b3EtfRows = computed(() => (b3Etfs.value?.funds || [])
  .filter(item => b3EtfCategoryFilter.value === 'ALL' || item.category === b3EtfCategoryFilter.value)
  .slice()
  .sort((a, b) => String(a.category || '').localeCompare(String(b.category || '')) || String(a.ticker || '').localeCompare(String(b.ticker || ''))))

const etfLocal = computed(() => etfPanel.value?.local || {})
const etfLocalSummary = computed(() => etfLocal.value?.summary || {})
const etfTopFunds = computed(() => (etfLocal.value?.top_funds || []).slice(0, 8))
const etfLocalSeries = computed(() => etfLocal.value?.timeseries || [])
const etfLocalSeriesPreview = computed(() => etfLocalSeries.value.slice(-18))
const etfFlowBarMax = computed(() => Math.max(
  ...etfLocalSeriesPreview.value.map(item => Math.abs(Number(item.rolling_flow_21d || 0))),
  1,
))
const etfAnbimaRows = computed(() => [
  ...(etfPanel.value?.anbima?.categories || []),
  ...(etfPanel.value?.anbima?.types || []).slice(0, 5),
].slice(0, 8))
const etfIciRows = computed(() => (etfPanel.value?.ici?.weekly_categories || [])
  .filter(item => item.category_key !== 'total')
  .slice(0, 8))

const bcbLatestBySeries = computed(() => bcbMacro.value?.latest_by_series || {})
const bcbMacroCards = computed(() => {
  const ptax = bcbMacro.value?.summary?.latest_usdbrl_ptax || {}
  const usd = bcbLatestBySeries.value.usdbrl_sgs || {}
  const selic = bcbLatestBySeries.value.selic_target || {}
  const daily = bcbLatestBySeries.value.selic_daily || {}
  const ipca = bcbLatestBySeries.value.ipca_monthly || {}
  return [
    { key: 'ptax', label: 'PTAX venda', value: fmtNum(ptax.cotacao_venda, 4), date: fmtDate(ptax.date) },
    { key: 'usd', label: 'USD SGS', value: fmtNum(usd.value, 4), date: fmtDate(usd.date) },
    { key: 'selic', label: 'Selic meta', value: fmtPctPlain(selic.value), date: fmtDate(selic.date) },
    { key: 'selic_daily', label: 'Selic diaria', value: fmtPctPlain(daily.value), date: fmtDate(daily.date) },
    { key: 'ipca', label: 'IPCA', value: fmtPctPlain(ipca.value), date: fmtDate(ipca.date) },
  ].filter(item => item.value !== '-')
})

const etfCards = computed(() => {
  const b3Summary = b3Etfs.value?.summary || {}
  const anbimaEtf = (etfPanel.value?.anbima?.categories || [])[0] || {}
  const iciEtf = etfPanel.value?.ici?.latest_weekly || {}
  return [
    {
      key: 'b3_total',
      label: 'ETFs B3',
      value: fmtCount(b3Summary.total_listed),
      detail: `${fmtCount(b3Summary.category_count)} segmentos`,
      tone: 'flat',
    },
    {
      key: 'local_flow',
      label: 'ETF CVM 21d',
      value: fmtMoney(etfLocalSummary.value.net_flow_21d),
      detail: `${fmtCount(etfLocalSummary.value.num_funds)} fundos`,
      tone: moveClass(etfLocalSummary.value.net_flow_21d),
    },
    {
      key: 'local_aum',
      label: 'PL ETF local',
      value: fmtMoney(etfLocalSummary.value.aum),
      detail: fmtDate(etfLocalSummary.value.date),
      tone: 'flat',
    },
    {
      key: 'anbima_mtd',
      label: 'ANBIMA ETF mes',
      value: fmtMoney(anbimaEtf.net_flow_month_brl),
      detail: fmtMoney(anbimaEtf.aum_brl),
      tone: moveClass(anbimaEtf.net_flow_month_brl),
    },
    {
      key: 'ici_weekly',
      label: 'ICI ETF semanal',
      value: fmtUsdMn(iciEtf.total_flow_usd_mn),
      detail: fmtDate(iciEtf.date),
      tone: moveClass(iciEtf.total_flow_usd_mn),
    },
  ]
})

const statusLabel = computed(() => {
  if (loading.value || collecting.value) return 'coletando'
  if (error.value) return 'erro'
  if (payload.value?.ok) return 'online'
  return 'sem base'
})

const metricLabel = computed(() => {
  if (metric.value === 'pct_pl') return '% do PL 21d'
  if (metric.value === 'zscore') return 'z-score 21d'
  return 'R$ bi, rolling 21d'
})

const kpiCards = computed(() => [
  { key: 'd1', label: 'Captacao 1d', value: fmtMoney(kpis.value.net_flow_1d), raw: kpis.value.net_flow_1d },
  { key: 'd5', label: 'Captacao 5d', value: fmtMoney(kpis.value.net_flow_5d), raw: kpis.value.net_flow_5d },
  { key: 'd21', label: 'Captacao 21d', value: fmtMoney(kpis.value.net_flow_21d), raw: kpis.value.net_flow_21d },
  { key: 'ytd', label: 'Captacao YTD', value: fmtMoney(kpis.value.net_flow_ytd), raw: kpis.value.net_flow_ytd },
  { key: 'aum', label: 'PL industria', value: fmtMoney(kpis.value.industry_aum), raw: kpis.value.industry_aum },
  { key: 'cotistas', label: 'Cotistas', value: fmtCount(kpis.value.total_shareholders), raw: kpis.value.delta_shareholders_21d },
  { key: 'pressure', label: 'Pressao', value: fmtNum(kpis.value.pressure_index, 2), raw: kpis.value.pressure_index },
])

const stressCards = computed(() => [
  { label: 'Fundos negativos', value: fmtPct(stress.value.pct_funds_negative), tone: ratioTone(stress.value.pct_funds_negative) },
  { label: 'PL sob resgate', value: fmtPct(stress.value.pct_aum_negative), tone: ratioTone(stress.value.pct_aum_negative) },
  { label: 'HHI resgates', value: fmtNum(stress.value.hhi_redemptions, 3), tone: Number(stress.value.hhi_redemptions || 0) > 0.25 ? 'down' : 'flat' },
  { label: 'Maior resgate', value: fmtPct(stress.value.largest_redemption_share), tone: Number(stress.value.largest_redemption_share || 0) > 0.25 ? 'down' : 'flat' },
  { label: 'Nivel', value: stressLabel(stress.value.stress_level), tone: stress.value.stress_level === 'high' ? 'down' : stress.value.stress_level === 'medium' ? 'warn' : 'up' },
])

const anbimaCards = computed(() => [
  { label: 'PL ANBIMA', value: fmtMoney(anbimaDailySummary.value.aum_brl), tone: 'flat' },
  { label: 'Captação dia', value: fmtMoney(anbimaDailySummary.value.net_flow_day_brl), tone: moveClass(anbimaDailySummary.value.net_flow_day_brl) },
  { label: 'Captação mês', value: fmtMoney(anbimaDailySummary.value.net_flow_month_brl), tone: moveClass(anbimaDailySummary.value.net_flow_month_brl) },
  { label: 'Captação ano', value: fmtMoney(anbimaDailySummary.value.net_flow_ytd_brl), tone: moveClass(anbimaDailySummary.value.net_flow_ytd_brl) },
  { label: 'Tipos ANBIMA', value: fmtCount((anbimaDaily.value?.types || []).length), tone: 'flat' },
  { label: 'Validação', value: fmtCount(anbimaValidationRows.value.length), tone: anbimaValidationRows.value.length ? 'up' : 'flat' },
])

const globalStatus = computed(() => {
  if (iciGlobal.value?.status === 'ok') return 'ICI active'
  return brazilVsGlobal.value?.status?.ici || 'configured'
})

const iciLatestDate = computed(() => {
  const weeklyDates = [...new Set(
    (brazilVsGlobal.value?.global || [])
      .filter(item => item.frequency === 'W' && item.date)
      .map(item => item.date),
  )].sort()
  return weeklyDates[weeklyDates.length - 1] || iciWeekly.value?.latest_date || ''
})

const cftcStatusLabel = computed(() => {
  if (cftcPositioning.value?.status === 'ok') {
    return `${fmtDate(cftcPositioning.value.report_date)} posicao | ${fmtDate(cftcPositioning.value.publication_date)} release`
  }
  return cftcPositioning.value?.status || 'configured'
})

const cftcParticipants = computed(() => cftcPositioning.value?.participant_summary || [])

const cftcDatasets = computed(() => (cftcPositioning.value?.datasets || [])
  .slice()
  .sort((a, b) => String(a.family || '').localeCompare(String(b.family || '')) || String(a.variant || '').localeCompare(String(b.variant || ''))))

const cftcFamilies = computed(() => (cftcPositioning.value?.family_summaries || [])
  .slice()
  .sort((a, b) => Number(b.open_interest || 0) - Number(a.open_interest || 0)))

const cftcBuckets = computed(() => (cftcPositioning.value?.asset_bucket_summary || [])
  .slice()
  .sort((a, b) => Math.abs(Number(b.lev_money_net || 0)) - Math.abs(Number(a.lev_money_net || 0))))

const cftcContracts = computed(() => (cftcPositioning.value?.focus_contracts || cftcPositioning.value?.latest_contracts || [])
  .slice()
  .sort((a, b) => Math.abs(Number(b.lev_money_net || 0)) - Math.abs(Number(a.lev_money_net || 0)))
  .slice(0, 24))

const cftcFocusContracts = computed(() => (cftcPositioning.value?.focus_contracts || cftcPositioning.value?.latest_contracts || [])
  .slice()
  .sort((a, b) => Number(b.open_interest || 0) - Number(a.open_interest || 0)))

const cftcRatesContracts = computed(() => cftcFocusContracts.value
  .filter(item => item.asset_bucket === 'Rates')
  .slice(0, 8))

const cftcEquityContracts = computed(() => cftcFocusContracts.value
  .filter(item => item.asset_bucket === 'Equity Index')
  .slice(0, 8))

const cftcFxContracts = computed(() => cftcFocusContracts.value
  .filter(item => item.asset_bucket === 'FX')
  .slice(0, 8))

const cftcExtendedParticipants = computed(() => (cftcPositioning.value?.extended_participant_summary || [])
  .slice()
  .sort((a, b) => Math.abs(Number(b.net || 0)) - Math.abs(Number(a.net || 0)))
  .slice(0, 28))

const cftcExtendedBuckets = computed(() => (cftcPositioning.value?.extended_asset_bucket_summary || [])
  .slice()
  .sort((a, b) => Math.abs(Number(b.primary_net || 0)) - Math.abs(Number(a.primary_net || 0)))
  .slice(0, 28))

const cftcExtendedContracts = computed(() => (cftcPositioning.value?.extended_contracts || [])
  .slice()
  .sort((a, b) => Math.abs(Number(b.primary_net || 0)) - Math.abs(Number(a.primary_net || 0)))
  .slice(0, 40))

const cftcCards = computed(() => {
  const lev = cftcParticipants.value.find(item => item.participant_key === 'lev_money') || {}
  const assetMgr = cftcParticipants.value.find(item => item.participant_key === 'asset_mgr') || {}
  const rates = cftcBuckets.value.find(item => item.asset_bucket === 'Rates') || {}
  const managedMoney = cftcExtendedParticipants.value.find(item => item.participant_key === 'managed_money') || {}
  const cit = cftcExtendedParticipants.value.find(item => item.participant_key === 'cit') || {}
  return [
    {
      key: 'report',
      label: 'Data COT',
      value: fmtDate(cftcPositioning.value.report_date),
      detail: `Release ${fmtDate(cftcPositioning.value.publication_date)}`,
      tone: 'flat',
    },
    {
      key: 'lev',
      label: 'Leveraged funds net',
      value: signedCount(lev.net),
      detail: `semana ${signedCount(lev.weekly_net_change)}`,
      tone: moveClass(lev.net),
    },
    {
      key: 'asset_mgr',
      label: 'Asset managers net',
      value: signedCount(assetMgr.net),
      detail: `semana ${signedCount(assetMgr.weekly_net_change)}`,
      tone: moveClass(assetMgr.net),
    },
    {
      key: 'rates',
      label: 'Rates lev funds',
      value: signedCount(rates.lev_money_net),
      detail: `OI ${fmtCount(rates.open_interest)}`,
      tone: moveClass(rates.lev_money_net),
    },
    {
      key: 'datasets',
      label: 'Datasets PRE',
      value: fmtCount(cftcDatasets.value.length),
      detail: `${fmtCount(cftcFamilies.value.length)} familias`,
      tone: cftcDatasets.value.length >= 7 ? 'up' : 'flat',
    },
    {
      key: 'managed_money',
      label: 'Managed money',
      value: signedCount(managedMoney.net),
      detail: `${managedMoney.family_label || 'Disaggregated'} semana ${signedCount(managedMoney.weekly_net_change)}`,
      tone: moveClass(managedMoney.net),
    },
    {
      key: 'cit',
      label: 'Commodity index',
      value: signedCount(cit.net),
      detail: `${cit.family_label || 'CIT'} semana ${signedCount(cit.weekly_net_change)}`,
      tone: moveClass(cit.net),
    },
  ]
})

function cftcParticipantLabel(family, participantKey) {
  const map = {
    tff: {
      dealer: 'Dealer',
      asset_mgr: 'Asset mgr',
      lev_money: 'Lev funds',
      other_rept: 'Other rept',
      nonrept: 'Nonreportable',
    },
    disaggregated: {
      prod_merc: 'Producer/Merchant',
      swap: 'Swap dealer',
      managed_money: 'Managed money',
      other_rept: 'Other rept',
      nonrept: 'Nonreportable',
    },
    legacy: {
      noncomm: 'Non-commercial',
      commercial: 'Commercial',
      nonrept: 'Nonreportable',
    },
    supplemental_cit: {
      noncomm_nocit: 'Non-comm ex-CIT',
      commercial_nocit: 'Commercial ex-CIT',
      cit: 'CIT',
      nonrept: 'Nonreportable',
    },
  }
  return map[family]?.[participantKey] || participantKey || '-'
}

const nportCards = computed(() => [
  {
    key: 'holdings',
    label: 'Holdings',
    value: fmtCount(nportKpis.value.holdings),
    detail: `${fmtCount(nportKpis.value.filings)} filings`,
    tone: 'flat',
  },
  {
    key: 'value',
    label: 'Valor reportado',
    value: fmtUsd(nportKpis.value.reported_value),
    detail: `AUM ${fmtUsd(nportKpis.value.net_assets)}`,
    tone: 'flat',
  },
  {
    key: 'flow',
    label: 'Fluxo 3m reportado',
    value: fmtUsd(nportKpis.value.net_flow_3m),
    detail: 'sales + reinv. - redemptions',
    tone: moveClass(nportKpis.value.net_flow_3m),
  },
  {
    key: 'restricted',
    label: 'Restritos',
    value: fmtUsd(nportKpis.value.restricted_value),
    detail: `${fmtPctPlain(ratioPct(nportKpis.value.restricted_value, nportKpis.value.reported_value))} do valor`,
    tone: 'warn',
  },
  {
    key: 'level3',
    label: 'Level 3',
    value: fmtUsd(nportKpis.value.level3_value),
    detail: `${fmtPctPlain(ratioPct(nportKpis.value.level3_value, nportKpis.value.reported_value))} do valor`,
    tone: 'warn',
  },
  {
    key: 'derivatives',
    label: 'Derivativos',
    value: fmtUsd(nportKpis.value.derivative_value),
    detail: `short ${fmtUsd(nportKpis.value.short_value)}`,
    tone: moveClass(nportKpis.value.derivative_value),
  },
])

const iciLatestCards = computed(() => [
  {
    key: 'combined',
    label: 'Global MF+ETF',
    value: iciLatestByVehicle.value.combined?.total_flow_usd_mn,
    date: iciLatestByVehicle.value.combined?.date,
  },
  {
    key: 'etf',
    label: 'ETF net issuance',
    value: iciLatestByVehicle.value.etf?.total_flow_usd_mn,
    date: iciLatestByVehicle.value.etf?.date,
  },
  {
    key: 'mutual',
    label: 'Mutual funds',
    value: iciLatestByVehicle.value.mutual_fund?.total_flow_usd_mn,
    date: iciLatestByVehicle.value.mutual_fund?.date,
  },
].filter(card => Number.isFinite(Number(card.value))))

const iciMonthlyEtfRows = computed(() => (iciMonthlyEtf.value?.assets_by_type || [])
  .filter(item => item.segment_key !== 'all')
  .slice(0, 8))

const iciWorldwideRegions = computed(() => (iciWorldwide.value?.regions || [])
  .filter(item => item.region !== 'World')
  .slice()
  .sort((a, b) => Math.abs(Number(b.net_sales_total_usd_mn || 0)) - Math.abs(Number(a.net_sales_total_usd_mn || 0))))

const iciRegionInflows = computed(() => iciWorldwideRegions.value
  .filter(item => Number(item.net_sales_total_usd_mn || 0) > 0)
  .sort((a, b) => Number(b.net_sales_total_usd_mn || 0) - Number(a.net_sales_total_usd_mn || 0)))

const iciRegionOutflows = computed(() => iciWorldwideRegions.value
  .filter(item => Number(item.net_sales_total_usd_mn || 0) < 0)
  .sort((a, b) => Number(a.net_sales_total_usd_mn || 0) - Number(b.net_sales_total_usd_mn || 0)))

const iciGlobalRows = computed(() => brazilVsGlobal.value?.global || [])

const iciSeriesOptions = computed(() => {
  const byKey = new Map()
  iciGlobalRows.value
    .filter(item => item.frequency === 'W')
    .forEach(item => {
      const key = `${item.vehicle}|${item.category_key}`
      if (byKey.has(key)) return
      byKey.set(key, {
        key,
        vehicle: item.vehicle,
        label: `${item.vehicle_label}: ${item.category}`,
        category: item.category,
      })
    })
  const vehicleOrder = { combined: 0, etf: 1, mutual_fund: 2 }
  return [...byKey.values()]
    .sort((a, b) => (vehicleOrder[a.vehicle] ?? 9) - (vehicleOrder[b.vehicle] ?? 9) || a.label.localeCompare(b.label))
    .slice(0, 18)
})

const iciChartDates = computed(() => [...new Set(iciGlobalRows.value
  .filter(item => item.frequency === 'W')
  .map(item => item.date))]
  .sort())

const iciChartRawSeries = computed(() => {
  const selected = selectedIciSeries.value.length
    ? selectedIciSeries.value
    : iciSeriesOptions.value.slice(0, 4).map(item => item.key)
  const rowsByKey = new Map()
  iciGlobalRows.value
    .filter(item => item.frequency === 'W')
    .forEach(item => {
      const key = `${item.vehicle}|${item.category_key}`
      if (!selected.includes(key)) return
      if (!rowsByKey.has(key)) rowsByKey.set(key, { meta: item, values: new Map() })
      rowsByKey.get(key).values.set(item.date, Number(item.net_flow || 0) / 1000)
    })
  return [...rowsByKey.entries()].map(([key, item], index) => ({
    key,
    name: `${item.meta.vehicle_label}: ${item.meta.category}`,
    color: colors[index % colors.length],
    values: iciChartDates.value.map(date => item.values.get(date) ?? null),
  }))
})

const iciChartScale = computed(() => {
  const values = iciChartRawSeries.value.flatMap(series => series.values).filter(value => Number.isFinite(value))
  if (!values.length) return { min: -1, max: 1 }
  let min = Math.min(...values)
  let max = Math.max(...values)
  if (min === max) {
    min -= 1
    max += 1
  }
  const pad = Math.max((max - min) * 0.1, 0.1)
  return { min: min - pad, max: max + pad }
})

const iciChartSeries = computed(() => {
  const width = 702
  const height = 188
  const left = 42
  const top = 30
  const scale = iciChartScale.value
  const count = Math.max(...iciChartRawSeries.value.map(series => series.values.length), 1)
  return iciChartRawSeries.value.map(series => ({
    ...series,
    points: series.values.map((value, index) => ({
      x: left + (count === 1 ? width : (index / (count - 1)) * width),
      y: top + height - ((value - scale.min) / (scale.max - scale.min)) * height,
      value,
    })).filter(point => Number.isFinite(point.value)),
  }))
})

const iciChartLastPoints = computed(() => iciChartSeries.value
  .map(series => {
    const point = series.points[series.points.length - 1]
    return point ? { ...point, name: series.name, color: series.color } : null
  })
  .filter(Boolean))

const iciLatestWeeklyRows = computed(() => {
  const latestDate = iciLatestDate.value
  return iciGlobalRows.value
    .filter(item => item.frequency === 'W' && item.date === latestDate)
    .map(item => ({ ...item, flow_usd_mn: item.net_flow }))
    .slice()
    .sort((a, b) => {
      const vehicleOrder = { combined: 0, etf: 1, mutual_fund: 2 }
      return (vehicleOrder[a.vehicle] ?? 9) - (vehicleOrder[b.vehicle] ?? 9)
        || Math.abs(Number(b.net_flow || 0)) - Math.abs(Number(a.net_flow || 0))
    })
})

const iciCountryRows = computed(() => (iciWorldwide.value?.countries || [])
  .slice()
  .sort((a, b) => Math.abs(Number(b.net_sales_total_usd_mn || 0)) - Math.abs(Number(a.net_sales_total_usd_mn || 0))))

const iciCountryInflows = computed(() => iciCountryRows.value
  .filter(item => Number(item.net_sales_total_usd_mn || 0) > 0)
  .sort((a, b) => Number(b.net_sales_total_usd_mn || 0) - Number(a.net_sales_total_usd_mn || 0)))

const iciCountryOutflows = computed(() => iciCountryRows.value
  .filter(item => Number(item.net_sales_total_usd_mn || 0) < 0)
  .sort((a, b) => Number(a.net_sales_total_usd_mn || 0) - Number(b.net_sales_total_usd_mn || 0)))

const iciCountryHeatmapColumns = [
  { key: 'net_sales_total_usd_mn', label: 'Total' },
  { key: 'net_sales_equity_usd_mn', label: 'Equity' },
  { key: 'net_sales_bond_usd_mn', label: 'Bond' },
  { key: 'net_sales_money_market_usd_mn', label: 'Money' },
  { key: 'net_sales_etfs_usd_mn', label: 'ETF' },
]

const iciCountryHeatmapRows = computed(() => iciCountryRows.value.slice(0, 24).map(row => ({
  ...row,
  cells: iciCountryHeatmapColumns.map(column => ({
    ...column,
    value: Number(row[column.key] || 0),
  })),
})))

const iciCountryHeatmapMax = computed(() => Math.max(
  ...iciCountryHeatmapRows.value.flatMap(row => row.cells.map(cell => Math.abs(Number(cell.value || 0)))),
  1,
))

const iciCountryHeatmapStyle = computed(() => ({
  gridTemplateColumns: `128px repeat(${iciCountryHeatmapColumns.length}, minmax(92px, 1fr))`,
}))

const sourceCards = computed(() => sources.value.map(rawSource => {
  const source = rawSource.id === 'cvm_cda' && cdaPayload.value?.ok
    ? {
        ...rawSource,
        ok: true,
        status: 'active',
        rows: cdaKpis.value.holdings || rawSource.rows,
        latency_ms: rawSource.latency_ms || 0,
        cached_path: cdaReport.value.db_path || rawSource.cached_path,
        latest_data_date: cdaReport.value?.as_of_date || rawSource.latest_data_date,
        reference_label: cdaReport.value?.period_label || rawSource.reference_label,
        last_captured_at: cdaReport.value?.generated_at || cdaPayload.value?.generated_at || rawSource.last_captured_at,
      }
    : rawSource
  const statusClass = sourceStatusClass(source)
  return {
    ...source,
    statusClass,
    statusLabel: sourceStatusLabel(source),
    cadenceLabel: cadenceLabel(source.cadence),
    officialDate: sourceOfficialDate(source),
    secondaryReference: sourceReference(source),
    capturedAt: sourceCapturedAt(source),
    technicalSummary: sourceTechnicalSummary(source),
    rows: Number(source.rows || 0),
  }
}))

const activeSourceCount = computed(() => sourceCards.value.filter(item => item.statusClass === 'active').length)

const chartRows = computed(() => payload.value?.timeseries?.flow_by_class || [])

const chartClasses = computed(() => {
  const byClass = new Map()
  chartRows.value.forEach(row => {
    const current = byClass.get(row.macro_classe) || 0
    byClass.set(row.macro_classe, Math.max(current, Math.abs(Number(row.rolling_flow_21d || 0))))
  })
  return [...byClass.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 7)
    .map(([name]) => name)
})

const chartRawSeries = computed(() => {
  const dates = [...new Set(chartRows.value.map(row => row.date))].sort()
  const rowsByClass = new Map()
  chartRows.value.forEach(row => {
    if (!chartClasses.value.includes(row.macro_classe)) return
    if (!rowsByClass.has(row.macro_classe)) rowsByClass.set(row.macro_classe, new Map())
    rowsByClass.get(row.macro_classe).set(row.date, row)
  })
  return chartClasses.value.map((name, index) => ({
    name,
    color: colors[index % colors.length],
    values: dates.map(date => metricValue(rowsByClass.get(name)?.get(date))),
  }))
})

const chartScale = computed(() => {
  const values = chartRawSeries.value.flatMap(series => series.values).filter(value => Number.isFinite(value))
  if (!values.length) return { min: -1, max: 1 }
  let min = Math.min(...values)
  let max = Math.max(...values)
  if (min === max) {
    min -= 1
    max += 1
  }
  const pad = Math.max((max - min) * 0.08, 0.0001)
  return { min: min - pad, max: max + pad }
})

const chartSeries = computed(() => {
  const width = 702
  const height = 188
  const left = 42
  const top = 30
  const scale = chartScale.value
  const count = Math.max(...chartRawSeries.value.map(series => series.values.length), 1)
  return chartRawSeries.value.map(series => ({
    ...series,
    points: series.values.map((value, index) => ({
      x: left + (count === 1 ? width : (index / (count - 1)) * width),
      y: top + height - ((value - scale.min) / (scale.max - scale.min)) * height,
      value,
    })).filter(point => Number.isFinite(point.value)),
  }))
})

const chartLastPoints = computed(() => chartSeries.value
  .map(series => {
    const point = series.points[series.points.length - 1]
    return point ? { ...point, name: series.name, color: series.color } : null
  })
  .filter(Boolean))

const heatmapRows = computed(() => {
  const xs = heatmap.value.x || []
  const ys = heatmap.value.y || []
  const matrix = heatmap.value.z || []
  const cellMap = new Map((heatmap.value.cells || []).map(cell => [`${cell.date}|${cell.macro_classe}`, cell]))
  return ys.map((name, rowIndex) => ({
    name,
    cells: xs.map((date, colIndex) => ({
      date,
      name,
      value: matrix?.[rowIndex]?.[colIndex] ?? null,
      detail: cellMap.get(`${date}|${name}`) || null,
    })),
  }))
})

const heatmapStyle = computed(() => ({
  gridTemplateColumns: `112px repeat(${Math.max((heatmap.value.x || []).length, 1)}, minmax(30px, 1fr))`,
}))

async function refresh(force = false) {
  try {
    error.value = ''
    loading.value = true
    const res = await getFundsFlowLocalDashboard({
      period: period.value,
      history_days: FUNDS_FLOW_HISTORY_DAYS,
      _ts: force ? Date.now() : undefined,
    })
    payload.value = res?.data?.data ?? res?.data ?? res ?? null
  } catch (err) {
    error.value = friendlyError(err)
  } finally {
    loading.value = false
    collecting.value = false
    if (activeTab.value === 'etf' && etfViewMode.value === 'daily_flow') {
      etfDailyFlowRefreshNonce.value += 1
    }
  }
}

async function loadNportDashboard(force = false) {
  if (nportLoading.value) return
  try {
    nportError.value = ''
    nportLoading.value = true
    const res = await getNportDashboard({
      quarter: 'latest',
      _ts: force ? Date.now() : undefined,
    })
    nportPayload.value = res?.data?.data ?? res?.data ?? res ?? null
    nportLoaded.value = true
    if (nportPayload.value?.ok) {
      await loadNportAnalytics(force)
    }
  } catch (err) {
    nportError.value = err?.response?.data?.error || err?.message || 'Falha ao carregar N-PORT.'
    nportLoaded.value = true
  } finally {
    nportLoading.value = false
    if (activeTab.value === 'nport') {
      nextTick(() => {
        document.querySelectorAll('.ffl-nport-view').forEach(el => {
          el.scrollTop = 0
          el.scrollLeft = 0
          el?.scrollTo?.({ top: 0, left: 0 })
        })
      })
    }
  }
}

function unwrapResponse(res) {
  return res?.data?.data ?? res?.data ?? res ?? null
}

async function loadNportAnalytics(force = false) {
  if (nportAnalyticsLoading.value) return
  try {
    nportAnalyticsLoading.value = true
    const [performance, funds, assets, positioning] = await Promise.all([
      getNportPerformance({
        quarter: 'latest',
        page: nportPerfPage.value,
        per_page: 18,
        weighted: nportPerfWeighted.value,
        _ts: force ? Date.now() : undefined,
      }),
      getNportRegionFunds({
        quarter: 'latest',
        target: nportExposureTarget.value,
        side: nportExposureSide.value,
        page: nportExposurePage.value,
        per_page: 18,
        _ts: force ? Date.now() : undefined,
      }),
      getNportRegionAssets({
        quarter: 'latest',
        target: nportAssetTarget.value,
        side: nportAssetSide.value,
        page: nportAssetPage.value,
        per_page: 18,
        _ts: force ? Date.now() : undefined,
      }),
      getNportPositioning({
        quarter: 'latest',
        _ts: force ? Date.now() : undefined,
      }),
    ])
    nportPerformance.value = unwrapResponse(performance)
    nportRegionFunds.value = unwrapResponse(funds)
    nportRegionAssets.value = unwrapResponse(assets)
    nportPositioning.value = unwrapResponse(positioning)
    nportAnalyticsLoaded.value = true
  } catch (err) {
    nportError.value = err?.response?.data?.error || err?.message || 'Falha ao carregar analytics N-PORT.'
  } finally {
    nportAnalyticsLoading.value = false
  }
}

async function loadNportPerformancePanel() {
  try {
    const res = await getNportPerformance({
      quarter: 'latest',
      page: nportPerfPage.value,
      per_page: 18,
      weighted: nportPerfWeighted.value,
    })
    nportPerformance.value = unwrapResponse(res)
  } catch (err) {
    nportError.value = err?.response?.data?.error || err?.message || 'Falha ao carregar performance N-PORT.'
  }
}

async function loadNportRegionFundsPanel() {
  try {
    nportSelectedFund.value = null
    nportFundHoldings.value = null
    const res = await getNportRegionFunds({
      quarter: 'latest',
      target: nportExposureTarget.value,
      side: nportExposureSide.value,
      page: nportExposurePage.value,
      per_page: 18,
    })
    nportRegionFunds.value = unwrapResponse(res)
  } catch (err) {
    nportError.value = err?.response?.data?.error || err?.message || 'Falha ao carregar fundos por regiao.'
  }
}

async function loadNportRegionAssetsPanel() {
  try {
    const res = await getNportRegionAssets({
      quarter: 'latest',
      target: nportAssetTarget.value,
      side: nportAssetSide.value,
      page: nportAssetPage.value,
      per_page: 18,
    })
    nportRegionAssets.value = unwrapResponse(res)
  } catch (err) {
    nportError.value = err?.response?.data?.error || err?.message || 'Falha ao carregar ativos por regiao.'
  }
}

async function selectNportFund(item) {
  if (!item?.accession_number) return
  try {
    nportSelectedFund.value = item
    const res = await getNportFundHoldings(item.accession_number, {
      quarter: 'latest',
      target: nportExposureTarget.value,
      side: nportExposureSide.value,
      page: 1,
      per_page: 30,
    })
    nportFundHoldings.value = unwrapResponse(res)
  } catch (err) {
    nportError.value = err?.response?.data?.error || err?.message || 'Falha ao abrir holdings do fundo.'
  }
}

function toggleNportWeighted() {
  nportPerfWeighted.value = !nportPerfWeighted.value
  nportPerfPage.value = 1
  loadNportPerformancePanel()
}

function setNportPerfPage(delta) {
  const nextPage = Math.min(Math.max(nportPerfPage.value + delta, 1), totalPages(nportPerformance.value))
  if (nextPage === nportPerfPage.value) return
  nportPerfPage.value = nextPage
  loadNportPerformancePanel()
}

function setNportExposureTarget(key) {
  if (nportExposureTarget.value === key) return
  nportExposureTarget.value = key
  nportExposurePage.value = 1
  loadNportRegionFundsPanel()
}

function setNportExposureSide(key) {
  if (nportExposureSide.value === key) return
  nportExposureSide.value = key
  nportExposurePage.value = 1
  loadNportRegionFundsPanel()
}

function setNportExposurePage(delta) {
  const nextPage = Math.min(Math.max(nportExposurePage.value + delta, 1), totalPages(nportRegionFunds.value))
  if (nextPage === nportExposurePage.value) return
  nportExposurePage.value = nextPage
  loadNportRegionFundsPanel()
}

function setNportAssetTarget(key) {
  if (nportAssetTarget.value === key) return
  nportAssetTarget.value = key
  nportAssetPage.value = 1
  loadNportRegionAssetsPanel()
}

function setNportAssetSide(key) {
  if (nportAssetSide.value === key) return
  nportAssetSide.value = key
  nportAssetPage.value = 1
  loadNportRegionAssetsPanel()
}

function setNportAssetPage(delta) {
  const nextPage = Math.min(Math.max(nportAssetPage.value + delta, 1), totalPages(nportRegionAssets.value))
  if (nextPage === nportAssetPage.value) return
  nportAssetPage.value = nextPage
  loadNportRegionAssetsPanel()
}

async function ingestLocalNport() {
  try {
    nportError.value = ''
    nportLoading.value = true
    const res = await ingestNportLocal({ force: true })
    const data = res?.data?.data ?? res?.data ?? res ?? null
    nportPayload.value = data?.dashboard || data || null
    nportLoaded.value = true
    if (nportPayload.value?.ok) {
      await loadNportAnalytics(true)
    }
  } catch (err) {
    nportError.value = err?.response?.data?.error || err?.message || 'Falha ao importar N-PORT local.'
  } finally {
    nportLoading.value = false
    if (activeTab.value === 'nport') {
      nextTick(() => {
        document.querySelectorAll('.ffl-nport-view').forEach(el => {
          el.scrollTop = 0
          el.scrollLeft = 0
          el?.scrollTo?.({ top: 0, left: 0 })
        })
      })
    }
  }
}

async function loadCdaDashboard(force = false) {
  if (cdaLoading.value) return
  try {
    cdaError.value = ''
    cdaLoading.value = true
    if (force) cdaRadarLoaded.value = false
    const res = await getCvmCdaDashboard({
      month: 'latest',
      _ts: force ? Date.now() : undefined,
    })
    cdaPayload.value = unwrapResponse(res)
    cdaLoaded.value = true
    if (cdaPayload.value?.ok) {
      await loadCdaAnalytics(force)
    }
  } catch (err) {
    cdaError.value = err?.response?.data?.error || err?.message || 'Falha ao carregar CVM CDA.'
    cdaLoaded.value = true
  } finally {
    cdaLoading.value = false
    if (activeTab.value === 'cda') {
      resetTabScroll('.ffl-cda-view')
    }
  }
}

async function loadCdaAnalytics(force = false) {
  if (cdaAnalyticsLoading.value) return
  try {
    cdaAnalyticsLoading.value = true
    const [funds, assets, positioning] = await Promise.all([
      getCvmCdaFunds({
        month: 'latest',
        target: cdaFundTarget.value,
        side: cdaFundSide.value,
        page: cdaFundPage.value,
        per_page: 18,
        _ts: force ? Date.now() : undefined,
      }),
      getCvmCdaAssets({
        month: 'latest',
        target: cdaAssetTarget.value,
        side: cdaAssetSide.value,
        page: cdaAssetPage.value,
        per_page: 18,
        _ts: force ? Date.now() : undefined,
      }),
      getCvmCdaPositioning({
        month: 'latest',
        _ts: force ? Date.now() : undefined,
      }),
    ])
    cdaFunds.value = unwrapResponse(funds)
    cdaAssets.value = unwrapResponse(assets)
    cdaPositioning.value = unwrapResponse(positioning)
    cdaAnalyticsLoaded.value = true
  } catch (err) {
    cdaError.value = err?.response?.data?.error || err?.message || 'Falha ao carregar analytics CVM CDA.'
  } finally {
    cdaAnalyticsLoading.value = false
  }
}

async function loadCdaRadar(force = false) {
  if (cdaRadarLoading.value) return
  try {
    cdaRadarError.value = ''
    cdaRadarLoading.value = true
    const res = await getCvmCdaRadar({
      month: 'latest',
      force,
      _ts: force ? Date.now() : undefined,
    })
    cdaRadarPayload.value = unwrapResponse(res)
    cdaRadarLoaded.value = true
    const defaultScenario = cdaRadarPayload.value?.default_scenario
    if (defaultScenario) cdaRadarScenario.value = defaultScenario
  } catch (err) {
    cdaRadarError.value = err?.response?.data?.error || err?.message || 'Falha ao carregar Radar CDA.'
    cdaRadarLoaded.value = true
  } finally {
    cdaRadarLoading.value = false
    if (activeTab.value === 'radar_cda') {
      resetTabScroll('.ffl-cda-radar-view')
    }
  }
}

async function loadCdaFundsPanel() {
  try {
    cdaSelectedFund.value = null
    cdaFundHoldings.value = null
    const res = await getCvmCdaFunds({
      month: 'latest',
      target: cdaFundTarget.value,
      side: cdaFundSide.value,
      page: cdaFundPage.value,
      per_page: 18,
    })
    cdaFunds.value = unwrapResponse(res)
  } catch (err) {
    cdaError.value = err?.response?.data?.error || err?.message || 'Falha ao carregar fundos CVM CDA.'
  }
}

async function loadCdaAssetsPanel() {
  try {
    const res = await getCvmCdaAssets({
      month: 'latest',
      target: cdaAssetTarget.value,
      side: cdaAssetSide.value,
      page: cdaAssetPage.value,
      per_page: 18,
    })
    cdaAssets.value = unwrapResponse(res)
  } catch (err) {
    cdaError.value = err?.response?.data?.error || err?.message || 'Falha ao carregar ativos CVM CDA.'
  }
}

async function selectCdaFund(item) {
  if (!item?.fund_cnpj) return
  try {
    cdaSelectedFund.value = item
    const res = await getCvmCdaFundHoldings(item.fund_cnpj, {
      month: 'latest',
      target: cdaFundTarget.value,
      side: cdaFundSide.value,
      page: 1,
      per_page: 34,
    })
    cdaFundHoldings.value = unwrapResponse(res)
  } catch (err) {
    cdaError.value = err?.response?.data?.error || err?.message || 'Falha ao abrir carteira do fundo.'
  }
}

async function openCdaRadarFund(item) {
  if (!item?.fund_cnpj) return
  activeTab.value = 'cda'
  if (!cdaLoaded.value) {
    await loadCdaDashboard(false)
  }
  await selectCdaFund({
    fund_cnpj: item.fund_cnpj,
    fund_name: item.fund_name,
  })
}

async function ingestCdaLatest() {
  try {
    cdaError.value = ''
    cdaLoading.value = true
    cdaRadarLoaded.value = false
    const res = await ingestCvmCda({ force: true, lookback_months: 1 })
    const data = unwrapResponse(res)
    cdaPayload.value = data?.dashboard || data || null
    cdaLoaded.value = true
    if (cdaPayload.value?.ok) {
      await loadCdaAnalytics(true)
    }
  } catch (err) {
    cdaError.value = err?.response?.data?.error || err?.message || 'Falha ao capturar CVM CDA.'
  } finally {
    cdaLoading.value = false
    if (activeTab.value === 'cda') {
      resetTabScroll('.ffl-cda-view')
    }
  }
}

function setCdaFundTarget(key) {
  if (cdaFundTarget.value === key) return
  cdaFundTarget.value = key
  cdaFundPage.value = 1
  loadCdaFundsPanel()
}

function setCdaFundSide(key) {
  if (cdaFundSide.value === key) return
  cdaFundSide.value = key
  cdaFundPage.value = 1
  loadCdaFundsPanel()
}

function setCdaFundPage(delta) {
  const nextPage = Math.min(Math.max(cdaFundPage.value + delta, 1), totalPages(cdaFunds.value))
  if (nextPage === cdaFundPage.value) return
  cdaFundPage.value = nextPage
  loadCdaFundsPanel()
}

function setCdaAssetTarget(key) {
  if (cdaAssetTarget.value === key) return
  cdaAssetTarget.value = key
  cdaAssetPage.value = 1
  loadCdaAssetsPanel()
}

function setCdaAssetSide(key) {
  if (cdaAssetSide.value === key) return
  cdaAssetSide.value = key
  cdaAssetPage.value = 1
  loadCdaAssetsPanel()
}

function setCdaAssetPage(delta) {
  const nextPage = Math.min(Math.max(cdaAssetPage.value + delta, 1), totalPages(cdaAssets.value))
  if (nextPage === cdaAssetPage.value) return
  cdaAssetPage.value = nextPage
  loadCdaAssetsPanel()
}

async function loadCdaGraph(force = false) {
  if (cdaGraphLoading.value) return
  try {
    cdaGraphError.value = ''
    cdaGraphLoading.value = true
    const params = {
      limit: cdaGraphLimit.value,
      target: cdaGraphTarget.value === 'all' ? undefined : cdaGraphTarget.value,
      issuer: cdaGraphIssuerFilter.value?.trim() || undefined,
      fund_cnpj: cdaGraphFundFilter.value?.trim() || undefined,
      _ts: force ? Date.now() : undefined,
    }
    const [status, network, crowding, trails] = await Promise.all([
      getCdaGraphStatus(),
      getCdaGraphNetwork(params),
      getCdaIssuerCrowding({ limit: 10, _ts: force ? Date.now() : undefined }),
      getCdaMoneyTrails({ limit: 36, _ts: force ? Date.now() : undefined }),
    ])
    cdaGraphStatus.value = unwrapResponse(status)
    cdaGraphNetwork.value = unwrapResponse(network)
    cdaGraphCrowding.value = unwrapResponse(crowding)
    cdaGraphTrails.value = unwrapResponse(trails)
    cdaGraphLoaded.value = true
  } catch (err) {
    cdaGraphError.value = err?.response?.data?.error || err?.message || 'Falha ao carregar grafo CDA.'
    cdaGraphLoaded.value = true
  } finally {
    cdaGraphLoading.value = false
  }
}

async function rebuildCdaGraph() {
  try {
    cdaGraphError.value = ''
    cdaGraphBuilding.value = true
    await buildCdaGraph({
      reset: true,
      max_funds: 180,
      max_positions_per_fund: 20,
      min_abs_value: 25_000_000,
      target_funds_per_theme: 30,
    })
    await loadCdaGraph(true)
  } catch (err) {
    cdaGraphError.value = err?.response?.data?.error || err?.message || 'Falha ao reconstruir grafo CDA.'
  } finally {
    cdaGraphBuilding.value = false
  }
}

function setCdaGraphTarget(key) {
  if (cdaGraphTarget.value === key) return
  cdaGraphTarget.value = key
  loadCdaGraph(true)
}

function applyCdaGraphFilters() {
  loadCdaGraph(true)
}

function clearCdaGraphFilters() {
  cdaGraphIssuerFilter.value = ''
  cdaGraphFundFilter.value = ''
  cdaGraphTarget.value = 'all'
  loadCdaGraph(true)
}

function bridgePathKey(item) {
  return `${item?.target || ''}|${item?.fund_type || ''}`
}

function assetTrailKey(item) {
  return item?.trail_key || `${item?.asset_key || ''}|${item?.asset_class || ''}|${item?.side || ''}`
}

async function openCdaBridgeModal(item) {
  cdaSelectedBridgePath.value = item || null
  cdaBridgePathDetailError.value = ''
  if (!item) return
  const key = bridgePathKey(item)
  if (cdaBridgePathDetails.value?.[key]) return
  try {
    cdaBridgePathDetailLoading.value = true
    const res = await getCdaBridgePathDetail({
      target: item.target,
      fund_type: item.fund_type,
      month: cdaGraphMonth.value === 'latest' ? undefined : cdaGraphMonth.value,
      limit: 18,
    })
    const data = unwrapResponse(res)
    if (data?.detail) {
      cdaBridgePathDetailCache.value = {
        ...cdaBridgePathDetailCache.value,
        [key]: data.detail,
      }
    }
  } catch (err) {
    cdaBridgePathDetailError.value = err?.response?.data?.error || err?.message || 'Falha ao carregar detalhe da trilha.'
  } finally {
    cdaBridgePathDetailLoading.value = false
  }
}

function closeCdaBridgeModal() {
  cdaSelectedBridgePath.value = null
}

function filterGraphByBridgePath() {
  if (!cdaSelectedBridgePath.value?.target) return
  cdaGraphTarget.value = cdaSelectedBridgePath.value.target
  closeCdaBridgeModal()
  loadCdaGraph(true)
}

async function openCdaAssetTrailModal(item) {
  cdaSelectedAssetTrail.value = item || null
  cdaAssetTrailDetailError.value = ''
  if (!item) return
  const key = assetTrailKey(item)
  if (cdaAssetTrailDetails.value?.[key]) return
  try {
    cdaAssetTrailDetailLoading.value = true
    const res = await getCdaAssetTrailDetail({
      asset_key: item.asset_key,
      asset_class: item.asset_class,
      side: item.side || 'coveted',
      month: cdaGraphMonth.value === 'latest' ? undefined : cdaGraphMonth.value,
      limit: 24,
    })
    const data = unwrapResponse(res)
    if (data?.detail) {
      cdaAssetTrailDetailCache.value = {
        ...cdaAssetTrailDetailCache.value,
        [key]: data.detail,
      }
    }
  } catch (err) {
    cdaAssetTrailDetailError.value = err?.response?.data?.error || err?.message || 'Falha ao carregar conexoes do ativo.'
  } finally {
    cdaAssetTrailDetailLoading.value = false
  }
}

function closeCdaAssetTrailModal() {
  cdaSelectedAssetTrail.value = null
}

function filterGraphByAssetTrail() {
  const issuer = cdaSelectedAssetTrail.value?.issuer_name
  if (issuer) {
    cdaGraphIssuerFilter.value = issuer
  }
  closeCdaAssetTrailModal()
  loadCdaGraph(true)
}

function openCdaCoherenceModal(item) {
  cdaSelectedCoherenceRow.value = item || null
}

function closeCdaCoherenceModal() {
  cdaSelectedCoherenceRow.value = null
}

function filterGraphByCoherence() {
  const row = cdaSelectedCoherenceRow.value
  if (!row) return
  cdaAssetLensFilter.value = row.bucket || cdaAssetLensFilter.value
  cdaGraphIssuerFilter.value = ''
  cdaGraphFundFilter.value = ''
  closeCdaCoherenceModal()
  loadCdaGraph(true)
}

function setMoneyFlowMode(key) {
  if (!moneyFlowModes.some(item => item.key === key)) return
  moneyFlowMode.value = key
  if (key === 'quarterly' && !nportLoaded.value) {
    loadNportDashboard(false)
  } else if (key === 'quarterly' && nportLoaded.value && !nportAnalyticsLoaded.value) {
    loadNportAnalytics(false)
  }
}

function openSelectedCdaFundGraph() {
  if (!cdaSelectedFund.value?.fund_cnpj) {
    activeTab.value = 'graph'
    loadCdaGraph(true)
    return
  }
  cdaGraphFundFilter.value = cdaSelectedFund.value.fund_cnpj
  activeTab.value = 'graph'
  loadCdaGraph(true)
}

function cdaGraphNodeCount(label) {
  return Number(cdaGraphNodeCounts.value.find(item => item.label === label)?.count || 0)
}

function cdaGraphEdgeCount(type) {
  return Number(cdaGraphEdgeCounts.value.find(item => item.type === type)?.count || 0)
}

function moneySourceY(index, total) {
  const count = Math.max(Number(total || 1), 1)
  return 31 + (index * (186 / Math.max(count - 1, 1)))
}

function moneyTargetY(index, total) {
  const count = Math.max(Number(total || 1), 1)
  return 33 + (index * (182 / Math.max(count - 1, 1)))
}

function moneySourcePath(index, total) {
  const y = moneySourceY(index, total)
  return `M 200 ${y} C 254 ${y}, 292 128, 336 128`
}

function moneyLayerPath(index, total) {
  const y = moneyTargetY(index, total)
  return `M 484 128 C 532 128, 558 ${y}, 590 ${y}`
}

function moneyStrokeWidth(value, maxValue) {
  const ratio = Math.min(Math.abs(Number(value || 0)) / Math.max(Math.abs(Number(maxValue || 0)), 1), 1)
  return 1.2 + ratio * 7.2
}

function moneyLayerTitle(layer) {
  const issuers = (layer.top_issuers || []).filter(Boolean).slice(0, 4).join(', ')
  const classes = (layer.top_asset_classes || []).filter(Boolean).slice(0, 4).join(', ')
  return `${layer.target_label || layer.name}: ${layer.display || fmtMoney(layer.net_value)} | ${layer.secondary_display || fmtMoney(layer.gross_value)} | fundos ${fmtCount(layer.fund_count)} | emissores ${issuers || '-'} | classes ${classes || '-'}`
}

function resetTabScroll(selector) {
  nextTick(() => {
    const scrollActiveTab = () => {
      document.querySelectorAll(selector).forEach(el => {
        el.scrollTop = 0
        el.scrollLeft = 0
        el?.scrollTo?.({ top: 0, left: 0 })
      })
    }
    scrollActiveTab()
    window.requestAnimationFrame(scrollActiveTab)
    window.setTimeout(scrollActiveTab, 0)
    window.setTimeout(scrollActiveTab, 120)
  })
}

function selectTab(key) {
  activeTab.value = key
  if (key === 'nport' && !nportLoaded.value) {
    loadNportDashboard(false)
  } else if (key === 'nport' && nportLoaded.value && !nportAnalyticsLoaded.value) {
    loadNportAnalytics(false)
  } else if (key === 'cda' && !cdaLoaded.value) {
    loadCdaDashboard(false)
  } else if (key === 'cda' && cdaLoaded.value && !cdaAnalyticsLoaded.value) {
    loadCdaAnalytics(false)
  } else if (key === 'radar_cda' && !cdaRadarLoaded.value) {
    loadCdaRadar(false)
  } else if (key === 'graph' && !cdaGraphLoaded.value) {
    loadCdaGraph(false)
  }
  if (key === 'graph' && moneyFlowMode.value === 'quarterly' && !nportLoaded.value) {
    loadNportDashboard(false)
  } else if (key === 'graph' && moneyFlowMode.value === 'quarterly' && nportLoaded.value && !nportAnalyticsLoaded.value) {
    loadNportAnalytics(false)
  }
  nextTick(() => {
    const classByTab = {
      overview: 'ffl-overview',
      b3: 'ffl-b3-view',
      etf: 'ffl-etf-view',
      map: 'ffl-map-view',
      stress: 'ffl-stress-view',
      anbima: 'ffl-anbima-view',
      global: 'ffl-global-view',
      cftc: 'ffl-cftc-view',
      nport: 'ffl-nport-view',
      cda: 'ffl-cda-view',
      radar_cda: 'ffl-cda-radar-view',
      graph: 'ffl-graph-view',
      sources: 'ffl-sources-view',
    }
    const selector = `.${classByTab[key] || 'ffl-overview'}`
    resetTabScroll(selector)
  })
}

async function refreshSource(sourceId) {
  try {
    refreshingSource.value = sourceId
    error.value = ''
    const res = await getFundsFlowLocalDashboard({
      period: period.value,
      history_days: FUNDS_FLOW_HISTORY_DAYS,
      _ts: Date.now(),
      source: sourceId,
    })
    payload.value = res?.data?.data ?? res?.data ?? res ?? payload.value
  } catch (err) {
    error.value = friendlyError(err)
  } finally {
    refreshingSource.value = ''
  }
}

function toggleIciSeries(key) {
  const current = new Set(selectedIciSeries.value)
  if (current.has(key)) {
    current.delete(key)
  } else {
    current.add(key)
  }
  selectedIciSeries.value = [...current].slice(-8)
}

function metricValue(row) {
  if (!row) return null
  if (metric.value === 'pct_pl') return Number(row.flow_pct_pl_21d || row.flow_pct_pl || 0) * 100
  if (metric.value === 'zscore') return Number(row.zscore || 0)
  return Number(row.rolling_flow_21d || row.net_flow || 0) / 1_000_000_000
}

function rankingWindowFlowValue(row, window = '21d') {
  if (!row) return 0
  if (window === '1d') return Number(row.net_flow_1d ?? row.captacao_liquida_total ?? row.net_flow ?? 0)
  if (window === '5d') return Number(row.net_flow_5d ?? row.rolling_flow_5d ?? 0)
  return Number(row.net_flow_21d ?? row.rolling_flow_21d ?? row.captacao_liquida_total ?? row.net_flow ?? 0)
}

function classFlowValue(row) {
  if (!row) return 0
  return Number(
    row.net_flow_21d
    ?? row.captacao_liquida_total
    ?? row.net_flow
    ?? row.value
    ?? row.flow
    ?? 0
  )
}

function b3Trend(participantType) {
  return b3TrendMap.value?.[participantType] || null
}

function divergingBarStyle(value, maxAbs) {
  const parsed = Number(value)
  const max = Math.max(Number(maxAbs || 0), 1)
  if (!Number.isFinite(parsed)) return { left: '50%', width: '0%' }
  const width = Math.min(Math.abs(parsed) / max, 1) * 48
  const left = parsed < 0 ? 50 - width : 50
  return { left: `${left}%`, width: `${width}%` }
}

function etfFlowBarHeight(value) {
  const parsed = Math.abs(Number(value || 0))
  const max = Math.max(Number(etfFlowBarMax.value || 0), 1)
  return `${8 + Math.min(parsed / max, 1) * 42}px`
}

function sourceLastCapture(source) {
  if (sourcePublicationGap(source)) return 'sem publ.'
  if (source.id === 'ici_global_flows') return fmtDate(iciLatestDate.value) || iciWorldwide.value?.quarter || '-'
  if (source.id === 'cftc_cot') return fmtDate(cftcPositioning.value?.report_date)
  if (source.id === 'anbima_fundos') return fmtDate(anbimaDaily.value?.reference_date)
  if (source.id === 'bcb_macro') return fmtDate(bcbLatestBySeries.value?.selic_target?.date || bcbMacro.value?.summary?.latest_usdbrl_ptax?.date)
  if (source.id === 'b3_etfs') return fmtDate(report.value.last_updated_at)
  if (source.id === 'b3_market') return fmtDate(b3Investor.value?.data_until)
  if (source.id === 'b3_derivatives_open_interest') return fmtDate(b3OpenInterest.value?.date)
  if (source.id === 'b3_investor_participation_monthly') return b3InvestorMonthly.value?.period_label || fmtDate(b3InvestorMonthly.value?.date)
  if (source.id === 'b3_market_data_report') return b3MarketData.value?.data_until || b3MarketSummary.value?.period || '-'
  if (source.id === 'cvm_informe_diario') return fmtDate(report.value.as_of_date)
  if (source.id === 'cvm_cadastro_fi') return fmtDate(report.value.last_updated_at)
  if (source.id === 'cvm_cda') return cdaReport.value?.period_label || fmtDate(cdaReport.value?.as_of_date)
  return source.ok ? fmtDate(report.value.last_updated_at) : '-'
}

function sourceOfficialDate(source) {
  if (sourcePublicationGap(source)) return 'sem publ.'
  if (source.id === 'ici_global_flows') return fmtDate(iciLatestDate.value) || fmtDate(source.latest_data_date) || '-'
  if (source.id === 'b3_investor_participation_monthly') return source.reference_label || b3InvestorMonthly.value?.period_label || fmtDate(source.latest_data_date)
  if (source.id === 'cvm_cda') return cdaReport.value?.period_label || fmtDate(cdaReport.value?.as_of_date)
  return source.reference_label || fmtDate(source.latest_data_date) || sourceLastCapture(source)
}

function sourceReference(source) {
  if (source.id === 'ici_global_flows') {
    const refs = [
      iciMonthlyEtf.value?.reference_month ? `ETF assets ${iciMonthlyEtf.value.reference_month}` : null,
      iciWorldwide.value?.quarter ? `Worldwide ${iciWorldwide.value.quarter}` : null,
    ].filter(Boolean)
    return refs.join(' | ')
  }
  if (source.id === 'b3_investor_participation_monthly') {
    return b3InvestorMonthly.value?.period_label || source.reference_label || ''
  }
  if (source.id === 'cvm_cda') {
    return cdaReport.value?.period_label || ''
  }
  return source.reference_label || ''
}

function sourceCapturedAt(source) {
  if (source.last_captured_at) return fmtDateTime(source.last_captured_at)
  if (source.ok && report.value.last_updated_at) return fmtDateTime(report.value.last_updated_at)
  return '-'
}

function sourceTechnicalSummary(source) {
  if (sourcePublicationGap(source)) {
    return `Consulta executada, mas a fonte oficial respondeu sem linhas publicadas para a janela sondada em torno de ${fmtDate(report.value.as_of_date)}. O endpoint existe e retornou schema, porém sem dados utilizáveis nessa tabela.`
  }
  if (source.latest_error || source.error) return `Falha recente: ${source.latest_error || source.error}`
  if (sourceStatusClass(source) === 'active') {
    return `Captura operacional com ${fmtCount(source.rows)} linhas agregadas, latencia ${fmtLatency(source.latency_ms)} e cache local versionado.`
  }
  if (sourceStatusClass(source) === 'configured') {
    return 'Fonte mapeada no contrato, mas ainda sem loader ativo no pipeline diario atual.'
  }
  return 'Fonte sem captura ativa ou sem dados recentes no payload.'
}

function sourceTemporalDetail(source) {
  if (source.id === 'ici_global_flows') return 'Weekly XLS para fluxos; monthly release para ETF assets; quarterly XLS para pais/regiao.'
  if (source.id === 'cftc_cot') return 'COT/PRE semanal: posicoes de terca-feira, publicacao publica usual na sexta; TFF, Disaggregated, Legacy e CIT via API.'
  if (source.id === 'bcb_macro') return 'SGS diario/mensal por serie e PTAX OData com boletins intradiarios agregados por data.'
  if (source.id === 'b3_etfs') return 'Consulta B3 Fundos Listados por segmento ETF; rechecagem diaria no pipeline.'
  if (source.id?.startsWith('b3_') || source.id === 'b3_market') return 'BDI/CSV B3 diario, com algumas tabelas mensais acumuladas.'
  if (source.id === 'anbima_fundos') return 'Consolidado diario e boletim/rankings mensais via ANBIMA Data.'
  if (source.id === 'cvm_cda') return 'CVM CDA e mensal; meses recentes sao rechecados diariamente por possiveis reapresentacoes/confidencialidade, meses antigos semanalmente.'
  if (source.id?.startsWith('cvm_')) return 'CVM publica arquivos mensais com observacoes diarias; cadastro e informe sao rechecados na coleta.'
  return cadenceLabel(source.cadence)
}

function sourceHealthDetail(source) {
  const parts = [
    `status=${sourceStatusLabel(source)}`,
    `ok=${Boolean(source.ok)}`,
    `rows=${fmtCount(source.rows)}`,
    `latencia=${fmtLatency(source.latency_ms)}`,
    `data_oficial=${source.officialDate}`,
    `capturado_em=${source.capturedAt}`,
  ]
  if (sourcePublicationGap(source)) parts.push('sem_publicacao=true')
  if (source.latest_error) parts.push(`erro=${source.latest_error}`)
  if (source.secondaryReference) parts.push(`referencia=${source.secondaryReference}`)
  return parts.join(' | ')
}

function sourceComponents(source) {
  const map = {
    cvm_informe_diario: ['CKAN package_show', 'ZIP mensal', 'CSV informe', 'raw_cvm_informe_diario', 'analytics flow daily'],
    cvm_cadastro_fi: ['Cadastro legado', 'Registro RCVM175', 'normalizacao CNPJ', 'classificacao fallback'],
    cvm_cda: ['CKAN package_show', 'ZIP mensal CDA', 'BLC 1-8', 'PL por fundo', 'SQLite separado', 'analytics holdings Brasil'],
    anbima_fundos: ['Consolidado diario', 'Tipos ANBIMA', 'Boletim mensal', 'Rankings gestor/admin', 'validacao CVM x ANBIMA'],
    ici_global_flows: ['Weekly MF flows', 'Weekly ETF net issuance', 'Combined MF+ETF', 'Monthly ETF assets', 'Worldwide quarterly pais/regiao'],
    b3_etfs: ['Fundos Listados B3', 'ETF RV', 'ETF RF', 'ETF FII', 'ETF cripto', 'ETF internacional RF'],
    b3_market: ['BDI PDF', 'participacao investidores', 'historico 21d', 'saldo por participante'],
    b3_derivatives_open_interest: ['BDI table export', 'DI/DDI/DOL/WDO/WIN', 'open interest', 'variacao d/d', 'rolling 21d'],
    b3_investor_participation_monthly: ['BDI table export', 'vista', 'termo', 'opcoes', 'exercicios', 'blocos'],
    b3_market_data_report: ['CSV dados de mercado', 'volume', 'ADV', 'negocios', 'estrangeiro'],
    bcb_macro: ['SGS USD/BRL', 'SGS Selic diaria', 'SGS Selic meta', 'SGS IPCA', 'OData PTAX'],
    fred_macro: ['FRED API', 'Treasury yields', 'breakeven', 'commodities'],
    cftc_cot: ['CFTC PRE/API', 'TFF FutOnly', 'TFF Combined', 'Disaggregated', 'Legacy', 'Supplemental CIT', 'Tuesday position', 'Friday release'],
  }
  return map[source.id] || [source.role || 'componente configurado']
}

function sourceLogText(source) {
  const payload = {
    id: source.id,
    label: source.label,
    status: source.status,
    ok: source.ok,
    rows: source.rows,
    cadence: source.cadence,
    official_date: source.officialDate,
    captured_at: source.capturedAt,
    secondary_reference: source.secondaryReference,
    latency_ms: source.latency_ms,
    url: source.url,
    cached_path: source.cached_path,
    latest_error: source.latest_error,
    components: sourceComponents(source),
    collector: payloadSummaryCollector(),
  }
  return JSON.stringify(payload, null, 2)
}

function payloadSummaryCollector() {
  return {
    cache_status: report.value.cache_status,
    last_updated_at: report.value.last_updated_at,
    started_at: report.value.started_at,
    completed_at: report.value.completed_at,
    raw_dir: report.value.lineage?.raw_dir,
    derived_dir: report.value.lineage?.derived_dir,
  }
}

function friendlyError(err) {
  return err?.response?.data?.error || err?.message || 'Falha ao carregar Funds Flow Local.'
}

function handleKeydown(event) {
  if (event.key !== 'Escape') return
  if (cdaSelectedCoherenceRow.value) {
    closeCdaCoherenceModal()
    return
  }
  if (cdaSelectedAssetTrail.value) {
    closeCdaAssetTrailModal()
    return
  }
  if (cdaSelectedBridgePath.value) {
    closeCdaBridgeModal()
  }
}

watch(() => props.refreshNonce, () => refresh(true))

onMounted(() => {
  refresh(false)
  timer = setInterval(() => refresh(false), 5 * 60_000)
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  clearInterval(timer)
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<style scoped src="./FundsFlowLocalWidget.css"></style>

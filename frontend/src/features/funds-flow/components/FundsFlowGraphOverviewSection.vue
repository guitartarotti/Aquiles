<template>
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

</template>

<script>
import { injectFundsFlowContext } from '../context'
export default {
  name: 'FundsFlowGraphOverviewSection',
  setup: injectFundsFlowContext,
}
</script>

<template>
      <main class="ffl-cda-radar-view">
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

</template>

<script>
import { injectFundsFlowContext } from '../context'
export default {
  name: 'FundsFlowCdaRadarView',
  setup: injectFundsFlowContext,
}
</script>

<template>
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
</template>

<script>
import { injectFundsFlowContext } from '../context'
export default {
  name: 'FundsFlowGraphIntelligenceSection',
  setup: injectFundsFlowContext,
}
</script>

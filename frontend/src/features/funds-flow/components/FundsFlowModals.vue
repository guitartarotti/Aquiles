<template>
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
</template>

<script>
import { injectFundsFlowContext } from '../context'
export default {
  name: 'FundsFlowModals',
  setup: injectFundsFlowContext,
}
</script>

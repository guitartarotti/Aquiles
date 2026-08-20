<template>
      <main class="ffl-sources-view">
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

<script>
import { injectFundsFlowContext } from '../context'
export default {
  name: 'FundsFlowSourcesView',
  setup: injectFundsFlowContext,
}
</script>

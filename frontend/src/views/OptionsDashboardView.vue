<template>
  <div class="options-shell">
    <header class="header">
      <div class="header-copy">
        <AquilesBrand variant="desk" subtitle="PLATAFORMA QUANT" clickable @click="goHome" />
        <div class="eyebrow">Options Desk</div>
        <h1>Options Dashboard</h1>
        <p>
          Read the latest `IBOVE Index` model run, compare dealer inference against the spot-based
          pressure curve, and keep one tactical view of the options book.
        </p>
      </div>
      <div class="actions">
        <button class="ghost" @click="goHome">Home</button>
        <button class="ghost" @click="goChart">Chart</button>
        <button class="ghost" @click="refreshDashboard" :disabled="loading || running || globalRunning">Refresh latest</button>
        <button class="primary" @click="handleRunModel" :disabled="running">
          {{ running ? 'Running model...' : 'Run model now' }}
        </button>
        <button class="ghost" @click="handleRunGlobalModel" :disabled="globalRunning || running || !modelReady">
          {{ globalRunning ? 'Running global...' : 'Run global overlay' }}
        </button>
      </div>
    </header>

    <section class="controls">
      <label>
        <span>Underlying</span>
        <select v-model="form.underlyingSecurity">
          <option v-for="item in availableUnderlyings" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <label>
        <span>Universe tier</span>
        <select v-model="form.universeTier">
          <option value="full">Full 90DU</option>
          <option value="structural">Structural</option>
          <option value="liquid">Liquid</option>
          <option value="critical">Critical</option>
        </select>
      </label>
      <label>
        <span>Sign convention</span>
        <select v-model="form.signConvention">
          <option value="neutral">Neutral</option>
          <option value="dealer_short_optionality">Dealer short optionality</option>
          <option value="heuristic">Heuristic</option>
        </select>
      </label>
      <div class="meta">
        <div><strong>Collector:</strong> {{ collectorRunning ? 'Online' : 'Stopped' }}</div>
        <div><strong>Trade map:</strong> {{ tradeSymbol }}</div>
        <div><strong>Batch:</strong> {{ latestBatchLabel }}</div>
        <div><strong>Snapshot:</strong> {{ latestSnapshotNote }}</div>
      </div>
    </section>

    <div v-if="errorMessage" class="error">{{ errorMessage }}</div>

    <section class="cards">
      <article v-for="card in topCards" :key="card.label" class="card">
        <div class="eyebrow">{{ card.label }}</div>
        <div class="value">{{ card.value }}</div>
        <div class="note">{{ card.note }}</div>
      </article>
    </section>

    <section v-if="globalModelReady" class="overview-panel">
      <div class="panel-head">
        <div>
          <div class="eyebrow">Global triangulation overlay</div>
          <h2>Confirmação macro e quantitativa global</h2>
        </div>
        <div class="panel-note">
          {{ globalTimestampLabel }} - {{ globalSummary.global_regime || 'Sem regime' }}
        </div>
      </div>
      <div class="overview-meta">
        <div class="marker-pill">
          <span>Regime</span>
          <strong>{{ globalSummary.global_regime || '--' }}</strong>
        </div>
        <div class="marker-pill">
          <span>Confiança</span>
          <strong>{{ formatPercent(globalSummary.global_regime_confidence) }}</strong>
        </div>
        <div class="marker-pill">
          <span>Local vs global</span>
          <strong>{{ globalDeskSummary.indice_local_vs_global || '--' }}</strong>
        </div>
        <div class="marker-pill">
          <span>Distorção Z</span>
          <strong :class="toneClass(globalSummary.distortion_zscore)">{{ formatSigned(globalSummary.distortion_zscore, 2) }}</strong>
        </div>
        <div class="marker-pill">
          <span>Absorção</span>
          <strong>{{ formatNumber(globalSummary.global_absorption_score, 1) }}</strong>
        </div>
        <div class="marker-pill">
          <span>Ruptura</span>
          <strong>{{ formatNumber(globalSummary.global_breakout_score, 1) }}</strong>
        </div>
        <div class="marker-pill">
          <span>Sync</span>
          <strong>{{ formatNumber(globalSummary.global_sync_score, 1) }}</strong>
        </div>
      </div>
      <div class="comparison global-summary-grid">
        <div><span>Distortion band</span><strong>{{ formatNumber(globalSummary.distortion_band_low, 0) }} to {{ formatNumber(globalSummary.distortion_band_high, 0) }}</strong></div>
        <div><span>Correlação curta</span><strong>{{ formatPercent(globalSummary.global_corr_short) }}</strong></div>
        <div><span>Correlação suavizada</span><strong>{{ formatPercent(globalSummary.global_corr_smoothed) }}</strong></div>
        <div><span>Beta global</span><strong>{{ formatNumber(globalSummary.global_beta_now, 2) }}</strong></div>
        <div><span>Absorção global</span><strong>{{ globalDeskSummary.absorcao_global || '--' }}</strong></div>
        <div><span>Ruptura global</span><strong>{{ globalDeskSummary.ruptura_global || '--' }}</strong></div>
        <div><span>Dealer zones</span><strong>{{ globalDeskSummary.alinhamento_zonas_dealer || '--' }}</strong></div>
        <div><span>Top explainers</span><strong>{{ globalTopExplainers }}</strong></div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Ativo</th>
              <th>Suporte</th>
              <th>Spot</th>
              <th>Ret intraday</th>
              <th>Beta</th>
              <th>Corr</th>
              <th>Fonte gamma</th>
              <th>Dealer state</th>
              <th>Absorção</th>
              <th>Ruptura</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in globalAssetRows" :key="row.asset">
              <td>{{ row.label || row.asset }}</td>
              <td>{{ row.support_level || '--' }}</td>
              <td>{{ formatNumber(row.spot, 2) }}</td>
              <td :class="toneClass(row.return_intraday)">{{ formatPercent(row.return_intraday) }}</td>
              <td>{{ formatNumber(row.beta_dynamic, 2) }}</td>
              <td>{{ formatPercent(row.corr_smoothed) }}</td>
              <td>{{ row.dealer_zone_source_underlying ? `${row.dealer_zone_source_underlying}${row.dealer_zone_source_mode === 'options_model' ? '' : ' (proxy)'}` : (row.dealer_zone_source_security || '--') }}</td>
              <td>{{ row.dealer_regime_state || '--' }}</td>
              <td>{{ formatNumber(row.score_local_absorption, 2) }}</td>
              <td>{{ formatNumber(row.score_local_breakout, 2) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-if="globalModelReady && globalGammaAssets.length" class="grid">
      <article class="panel">
        <div class="panel-head">
          <div>
            <div class="eyebrow">Global gamma explorer</div>
            <h2>Escolha um ativo global</h2>
          </div>
          <div class="panel-note">{{ globalGammaAssets.length }} ativos</div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Ativo</th>
                <th>Suporte</th>
                <th>Fonte gamma</th>
                <th>Modo</th>
                <th>Spot</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in globalGammaAssets"
                :key="`selector-${row.asset}`"
                class="selectable-row"
                :class="{ 'active-row': selectedGlobalAssetRow && selectedGlobalAssetRow.asset === row.asset }"
                @click="selectedGlobalAsset = row.asset"
              >
                <td>{{ row.label || row.asset }}</td>
                <td>{{ row.support_level || '--' }}</td>
                <td>{{ row.dealer_zone_source_underlying || row.dealer_zone_source_security || '--' }}</td>
                <td>{{ formatSourceMode(row.dealer_zone_source_mode) }}</td>
                <td>{{ formatNumber(row.spot, 2) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>

      <article class="panel">
        <div class="panel-head">
          <div>
            <div class="eyebrow">Selected asset regions</div>
            <h2>{{ selectedGlobalAssetRow?.label || 'Sem ativo selecionado' }}</h2>
          </div>
          <div class="panel-note">
            {{ selectedGlobalAssetSourceLabel }}
          </div>
        </div>
        <div v-if="selectedGlobalAssetRow" class="comparison global-summary-grid">
          <div><span>Spot</span><strong>{{ formatNumber(selectedGlobalAssetRow.spot, 2) }}</strong></div>
          <div><span>Support</span><strong>{{ selectedGlobalAssetRow.support_level || '--' }}</strong></div>
          <div><span>Gamma mode</span><strong>{{ formatSourceMode(selectedGlobalAssetRow.dealer_zone_source_mode) }}</strong></div>
          <div><span>Dealer state</span><strong>{{ selectedGlobalAssetRow.dealer_regime_state || '--' }}</strong></div>
          <div><span>Beta</span><strong>{{ formatNumber(selectedGlobalAssetRow.beta_dynamic, 2) }}</strong></div>
          <div><span>Corr</span><strong>{{ formatPercent(selectedGlobalAssetRow.corr_smoothed) }}</strong></div>
        </div>
        <div v-if="selectedGlobalGammaRegions.length" class="table-wrap asset-zone-table">
          <table>
            <thead>
              <tr>
                <th>Região</th>
                <th>Nível</th>
                <th>Faixa</th>
                <th>Leitura</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="zone in selectedGlobalGammaRegions" :key="`${selectedGlobalAssetRow?.asset}-${zone.key}`">
                <td>{{ zone.label }}</td>
                <td>{{ formatNumber(zone.level, 2) }}</td>
                <td>{{ zone.rangeLabel }}</td>
                <td>{{ zone.note }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else-if="selectedGlobalAssetRow" class="chat-empty">
          Não há regiões de gamma modeladas para este ativo neste momento. A fonte atual está em
          <strong>{{ formatSourceMode(selectedGlobalAssetRow.dealer_zone_source_mode) }}</strong>,
          então o overlay só consegue trabalhar com proxy de preço/vol até existir uma modelagem de opções completa.
        </div>
        <div v-if="selectedGlobalProjectedLevels.length" class="table-wrap asset-zone-table">
          <table>
            <thead>
              <tr>
                <th>Fonte</th>
                <th>Nível origem</th>
                <th>XB1 proj.</th>
                <th>Dir.</th>
                <th>Zona local</th>
                <th>Score</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in selectedGlobalProjectedLevels" :key="`${row.asset}-${row.source_type}-${row.mapped_local_future}`">
                <td>{{ row.source_label }}</td>
                <td :class="toneClass(row.source_distance_pct)">{{ formatNumber(row.source_level, 2) }}</td>
                <td :class="toneClass(row.mapped_move_pct)">{{ formatNumber(row.mapped_local_future, 0) }}</td>
                <td :class="toneClass(row.direction === 'upside' ? 1 : -1)">{{ row.direction }}</td>
                <td>{{ row.match_label || '--' }}</td>
                <td>{{ formatNumber(row.confluence_score, 1) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>
    </section>

    <section v-if="globalModelReady && (globalMappedLevels.length || globalUpsideLevels.length || globalDownsideLevels.length)" class="grid">
      <article class="panel wide">
        <div class="panel-head">
          <div>
            <div class="eyebrow">Cross-asset mapped deviations</div>
            <h2>Níveis projetados no índice futuro</h2>
          </div>
          <div class="panel-note">
            Score de confluência {{ formatNumber(globalSummary.cross_asset_confluence_score, 1) }}
          </div>
        </div>
        <div class="comparison global-summary-grid">
          <div><span>Cluster mais forte</span><strong>{{ formatNumber(globalStrongestCluster.center_future, 0) }}</strong></div>
          <div><span>Score</span><strong>{{ formatNumber(globalStrongestCluster.score, 1) }}</strong></div>
          <div><span>Zona local</span><strong>{{ globalStrongestCluster.match_label || '--' }}</strong></div>
          <div><span>Próximo acima</span><strong>{{ formatNumber(globalNearestUpsideCluster.center_future, 0) }}</strong></div>
          <div><span>Próximo abaixo</span><strong>{{ formatNumber(globalNearestDownsideCluster.center_future, 0) }}</strong></div>
          <div><span>Desvios casados</span><strong>{{ globalDeskSummary.desvios_casados || '--' }}</strong></div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Ativo</th>
                <th>Fonte</th>
                <th>Nível origem</th>
                <th>XB1 projetado</th>
                <th>Beta</th>
                <th>Corr</th>
                <th>Zona local</th>
                <th>Score</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in globalMappedLevels" :key="`${row.asset}-${row.source_type}-${row.mapped_local_future}`">
                <td>{{ row.label || row.asset }}</td>
                <td>{{ row.source_label }}</td>
                <td :class="toneClass(row.source_distance_pct)">{{ formatNumber(row.source_level, 2) }}</td>
                <td :class="toneClass(row.mapped_move_pct)">{{ formatNumber(row.mapped_local_future, 0) }}</td>
                <td>{{ formatNumber(row.beta_dynamic, 2) }}</td>
                <td>{{ formatPercent(row.corr_smoothed) }}</td>
                <td>{{ row.match_label || '--' }}</td>
                <td>{{ formatNumber(row.confluence_score, 1) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>

      <article class="panel">
        <div class="panel-head">
          <div>
            <div class="eyebrow">Confluence clusters</div>
            <h2>Regiões casadas</h2>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Centro</th>
                <th>Faixa</th>
                <th>Dir.</th>
                <th>Ativos</th>
                <th>Zona</th>
                <th>Score</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="cluster in globalMappedClusters.slice(0, 8)" :key="`${cluster.center_future}-${cluster.direction}`">
                <td>{{ formatNumber(cluster.center_future, 0) }}</td>
                <td>{{ formatNumber(cluster.band_low, 0) }} - {{ formatNumber(cluster.band_high, 0) }}</td>
                <td :class="toneClass(cluster.direction === 'upside' ? 1 : -1)">{{ cluster.direction }}</td>
                <td>{{ (cluster.assets || []).join(', ') }}</td>
                <td>{{ cluster.match_label || '--' }}</td>
                <td>{{ formatNumber(cluster.score, 1) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>
    </section>

    <section v-if="globalModelReady && (globalUpsideLevels.length || globalDownsideLevels.length)" class="grid">
      <article class="panel">
        <div class="panel-head">
          <div>
            <div class="eyebrow">Near up</div>
            <h2>Níveis acima do preço</h2>
          </div>
          <div class="panel-note">{{ globalUpsideLevels.length }} ativos</div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Ativo</th>
                <th>Fonte</th>
                <th>XB1 proj.</th>
                <th>Dist. pts</th>
                <th>Dist. %</th>
                <th>Score</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in globalUpsideLevels" :key="`up-${row.asset}-${row.source_type}`">
                <td>{{ row.label || row.asset }}</td>
                <td>{{ row.source_label }}</td>
                <td class="positive">{{ formatNumber(row.mapped_local_future, 0) }}</td>
                <td class="positive">{{ formatSigned(row.distance_from_local_future_points, 0) }}</td>
                <td class="positive">{{ formatPercent(row.distance_from_local_future_pct) }}</td>
                <td>{{ formatNumber(row.confluence_score, 1) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>

      <article class="panel">
        <div class="panel-head">
          <div>
            <div class="eyebrow">Near down</div>
            <h2>Níveis abaixo do preço</h2>
          </div>
          <div class="panel-note">{{ globalDownsideLevels.length }} ativos</div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Ativo</th>
                <th>Fonte</th>
                <th>XB1 proj.</th>
                <th>Dist. pts</th>
                <th>Dist. %</th>
                <th>Score</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in globalDownsideLevels" :key="`down-${row.asset}-${row.source_type}`">
                <td>{{ row.label || row.asset }}</td>
                <td>{{ row.source_label }}</td>
                <td class="negative">{{ formatNumber(row.mapped_local_future, 0) }}</td>
                <td class="negative">{{ formatSigned(row.distance_from_local_future_points, 0) }}</td>
                <td class="negative">{{ formatPercent(row.distance_from_local_future_pct) }}</td>
                <td>{{ formatNumber(row.confluence_score, 1) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>
    </section>

    <section v-if="modelReady" class="overview-panel">
      <div class="panel-head">
        <div>
          <div class="eyebrow">Daily options read</div>
          <h2>Desk summary for the day</h2>
        </div>
        <div class="panel-note">
          {{ dailyInsightSourceLabel }} - generated {{ dailyInsightTimestampLabel }}
        </div>
      </div>
      <p class="overview-copy">
        {{ dailyInsights.overview || 'No cached daily view was generated yet for this trading day.' }}
      </p>
      <div class="overview-meta">
        <div class="marker-pill">
          <span>Gamma flip method</span>
          <strong>OI history + latest gamma snapshot</strong>
        </div>
        <div class="marker-pill">
          <span>Current day status</span>
          <strong>{{ gammaFlipStatusLabel }}</strong>
        </div>
      </div>
    </section>

    <section v-if="modelReady && rangeProjection.enabled" class="overview-panel">
      <div class="panel-head">
        <div>
          <div class="eyebrow">Projected range engine</div>
          <h2>6+6 asymmetric projected ranges</h2>
        </div>
        <div class="panel-note">
          {{ rangeProjection.mode }} - center {{ formatNumber(rangeCenter.hybrid_center_future, 0) }}
        </div>
      </div>
      <p class="overview-copy">
        {{ rangeProjection.methodology }}
      </p>
      <div class="overview-meta">
        <div class="marker-pill">
          <span>Hybrid center</span>
          <strong>{{ formatNumber(rangeCenter.hybrid_center_future, 0) }}</strong>
        </div>
        <div class="marker-pill">
          <span>Forward observed</span>
          <strong>{{ formatNumber(rangeCenter.forward_observed, 0) }}</strong>
        </div>
        <div class="marker-pill">
          <span>Dealer ref</span>
          <strong>{{ formatNumber(rangeCenter.dealer_reference, 0) }}</strong>
        </div>
        <div class="marker-pill">
          <span>RND center</span>
          <strong>{{ formatNumber(rangeCenter.rnd_center, 0) }}</strong>
        </div>
      </div>
      <div class="table-wrap range-table-wrap">
        <table>
          <thead>
            <tr>
              <th>Level</th>
              <th>Down future</th>
              <th>Down spot</th>
              <th>Up spot</th>
              <th>Up future</th>
              <th>Quantiles</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="band in rangeBands" :key="band.level">
              <td>{{ band.label }}</td>
              <td class="negative">{{ formatNumber(band.adjusted_lower_future, 0) }}</td>
              <td class="negative">{{ formatNumber(band.adjusted_lower_spot, 0) }}</td>
              <td class="positive">{{ formatNumber(band.adjusted_upper_spot, 0) }}</td>
              <td class="positive">{{ formatNumber(band.adjusted_upper_future, 0) }}</td>
              <td>{{ formatPercent(band.lower_quantile) }} / {{ formatPercent(band.upper_quantile) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-if="modelReady" class="grid">
      <article class="panel wide">
        <div class="panel-head">
          <div>
            <div class="eyebrow">Strike profile</div>
            <h2>Gamma + GEX by strike</h2>
          </div>
          <div class="panel-note">Bars = GEX net - Line = gamma net</div>
        </div>
        <div class="chart-box">
          <svg
            v-if="gammaGexChart.bars.length"
            class="mini-chart"
            viewBox="0 0 960 220"
            preserveAspectRatio="none"
            @mousemove="handleStrikeHover('gammaGex', gammaGexChart, $event)"
            @mouseleave="clearHover('gammaGex')"
          >
            <line
              class="zero-line"
              :x1="miniChartPadding.left"
              :x2="960 - miniChartPadding.right"
              :y1="gammaGexChart.zeroY"
              :y2="gammaGexChart.zeroY"
            />
            <line
              v-if="hoverState.gammaGex"
              class="hover-guide"
              :x1="hoverState.gammaGex.x"
              :x2="hoverState.gammaGex.x"
              :y1="miniChartPadding.top"
              :y2="220 - miniChartPadding.bottom"
            />
            <rect
              v-for="bar in gammaGexChart.bars"
              :key="`gex-${bar.strike}`"
              class="mini-bar"
              :class="bar.tone"
              :x="bar.x"
              :y="bar.y"
              :width="bar.width"
              :height="bar.height"
            />
            <path :d="gammaGexChart.linePath" class="mini-line dealer" />
            <circle
              v-if="hoverState.gammaGex"
              class="hover-point dealer"
              :cx="hoverState.gammaGex.x"
              :cy="hoverState.gammaGex.lineY"
              r="4.5"
            />
            <text
              v-for="tick in gammaGexChart.xTicks"
              :key="`gamma-tick-${tick.strike}`"
              class="tick-text"
              :x="tick.x"
              :y="210"
              text-anchor="middle"
            >
              {{ formatNumber(tick.strike, 0) }}
            </text>
          </svg>
          <div v-if="hoverState.gammaGex" class="chart-tooltip">
            <strong>Strike {{ formatNumber(hoverState.gammaGex.row.strike, 0) }}</strong>
            <span>GEX net {{ formatSignedCompact(hoverState.gammaGex.row.gex_net) }}</span>
            <span>Gamma net {{ formatSigned(hoverState.gammaGex.row.gamma_net, 4) }}</span>
            <span>Calls {{ formatCompactNumber(hoverState.gammaGex.row.gex_call) }} / Puts {{ formatCompactNumber(hoverState.gammaGex.row.gex_put) }}</span>
          </div>
        </div>
        <div class="chart-scale">{{ gammaGexChart.scaleNote }}</div>
        <p class="insight-text">{{ dailyInsightCards.gamma_gex || defaultCardText.gamma_gex }}</p>
      </article>

      <article class="panel">
        <div class="panel-head">
          <div>
            <div class="eyebrow">OI history</div>
            <h2>Estimated gamma flips</h2>
          </div>
        </div>
        <div class="note">
          Esta tabela mostra todos os gamma flips estimados detectados no histórico recente. Cada linha
          representa uma data em que o gamma líquido estimado mudou de sinal por strike, de negativo
          para positivo ou de positivo para negativo. Isso é uma heurística construída com OI diário
          salvo e a última foto de gamma das opções, não um campo direto de mercado.
        </div>
        <div class="flip-stack">
          <div v-if="latestFlipPoints.length" class="flip-points">
            <span v-for="point in latestFlipPoints" :key="point" class="flip-pill">{{ formatNumber(point, 0) }}</span>
          </div>
          <div v-else class="note">Nenhum gamma flip estimado apareceu na janela histórica disponível.</div>
          <div v-if="allGammaFlipEvents.length" class="table-wrap flip-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Data</th>
                  <th>Strike do flip</th>
                  <th>Direção</th>
                  <th>De</th>
                  <th>Para</th>
                  <th>OI total</th>
                  <th>Base do OI</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="item in allGammaFlipEvents"
                  :key="`${item.trade_date}-${item.flip_strike}-${item.direction}`"
                >
                  <td>{{ item.trade_date }}</td>
                  <td>{{ formatNumber(item.flip_strike, 0) }}</td>
                  <td :class="toneClass(item.direction === 'negative_to_positive' ? 1 : item.direction === 'positive_to_negative' ? -1 : 0)">
                    {{ formatFlipDirection(item.direction) }}
                  </td>
                  <td>{{ formatRegime(item.from_sign) }}</td>
                  <td>{{ formatRegime(item.to_sign) }}</td>
                  <td>{{ formatCompactNumber(item.total_open_interest) }}</td>
                  <td>{{ formatGammaFlipStatus(item.data_status) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="note">Nenhuma mudança de sinal estável foi detectada por strike nas datas carregadas.</div>
        </div>
        <div v-if="historicalRegimeFlips.length" class="flip-regime-box">
          <strong>Viradas históricas de regime</strong>
          <div v-for="item in historicalRegimeFlips" :key="`${item.previous_trade_date}-${item.trade_date}`" class="note">
            {{ item.previous_trade_date }} -> {{ item.trade_date }}: {{ formatRegime(item.from_regime) }} -> {{ formatRegime(item.to_regime) }}
          </div>
        </div>
        <p class="insight-text">{{ dailyInsightCards.open_interest || defaultCardText.open_interest }}</p>
      </article>
    </section>

    <section v-if="modelReady" class="grid">
      <article class="panel wide">
        <div class="panel-head">
          <div>
            <div class="eyebrow">Strike profile</div>
            <h2>Delta + DEX by strike</h2>
          </div>
          <div class="panel-note">Bars = DEX net - Line = delta net</div>
        </div>
        <div class="chart-box">
          <svg
            v-if="deltaDexChart.bars.length"
            class="mini-chart"
            viewBox="0 0 960 220"
            preserveAspectRatio="none"
            @mousemove="handleStrikeHover('deltaDex', deltaDexChart, $event)"
            @mouseleave="clearHover('deltaDex')"
          >
            <line
              class="zero-line"
              :x1="miniChartPadding.left"
              :x2="960 - miniChartPadding.right"
              :y1="deltaDexChart.zeroY"
              :y2="deltaDexChart.zeroY"
            />
            <line
              v-if="hoverState.deltaDex"
              class="hover-guide"
              :x1="hoverState.deltaDex.x"
              :x2="hoverState.deltaDex.x"
              :y1="miniChartPadding.top"
              :y2="220 - miniChartPadding.bottom"
            />
            <rect
              v-for="bar in deltaDexChart.bars"
              :key="`dex-${bar.strike}`"
              class="mini-bar"
              :class="bar.tone"
              :x="bar.x"
              :y="bar.y"
              :width="bar.width"
              :height="bar.height"
            />
            <path :d="deltaDexChart.linePath" class="mini-line accent" />
            <circle
              v-if="hoverState.deltaDex"
              class="hover-point accent"
              :cx="hoverState.deltaDex.x"
              :cy="hoverState.deltaDex.lineY"
              r="4.5"
            />
            <text
              v-for="tick in deltaDexChart.xTicks"
              :key="`delta-tick-${tick.strike}`"
              class="tick-text"
              :x="tick.x"
              :y="210"
              text-anchor="middle"
            >
              {{ formatNumber(tick.strike, 0) }}
            </text>
          </svg>
          <div v-if="hoverState.deltaDex" class="chart-tooltip">
            <strong>Strike {{ formatNumber(hoverState.deltaDex.row.strike, 0) }}</strong>
            <span>DEX net {{ formatSignedCompact(hoverState.deltaDex.row.dex_net) }}</span>
            <span>Delta net {{ formatSigned(hoverState.deltaDex.row.delta_net, 4) }}</span>
            <span>DEX future notional {{ formatSignedCompact(hoverState.deltaDex.row.dex_notional_future_net) }}</span>
          </div>
        </div>
        <div class="chart-scale">{{ deltaDexChart.scaleNote }}</div>
        <p class="insight-text">{{ dailyInsightCards.delta_dex || defaultCardText.delta_dex }}</p>
      </article>

      <article class="panel">
        <div class="panel-head">
          <div>
            <div class="eyebrow">Strike profile</div>
            <h2>Open interest</h2>
          </div>
          <div class="panel-note">Bars = total OI - Line = OI imbalance</div>
        </div>
        <div class="chart-box">
          <svg
            v-if="openInterestChart.bars.length"
            class="mini-chart"
            viewBox="0 0 960 220"
            preserveAspectRatio="none"
            @mousemove="handleStrikeHover('openInterest', openInterestChart, $event)"
            @mouseleave="clearHover('openInterest')"
          >
            <line
              class="zero-line"
              :x1="miniChartPadding.left"
              :x2="960 - miniChartPadding.right"
              :y1="openInterestChart.zeroY"
              :y2="openInterestChart.zeroY"
            />
            <line
              v-if="hoverState.openInterest"
              class="hover-guide"
              :x1="hoverState.openInterest.x"
              :x2="hoverState.openInterest.x"
              :y1="miniChartPadding.top"
              :y2="220 - miniChartPadding.bottom"
            />
            <rect
              v-for="bar in openInterestChart.bars"
              :key="`oi-${bar.strike}`"
              class="mini-bar neutral-fill"
              :x="bar.x"
              :y="bar.y"
              :width="bar.width"
              :height="bar.height"
            />
            <path :d="openInterestChart.linePath" class="mini-line spot" />
            <circle
              v-if="hoverState.openInterest"
              class="hover-point spot"
              :cx="hoverState.openInterest.x"
              :cy="hoverState.openInterest.lineY"
              r="4.5"
            />
            <text
              v-for="tick in openInterestChart.xTicks"
              :key="`oi-tick-${tick.strike}`"
              class="tick-text"
              :x="tick.x"
              :y="210"
              text-anchor="middle"
            >
              {{ formatNumber(tick.strike, 0) }}
            </text>
          </svg>
          <div v-if="hoverState.openInterest" class="chart-tooltip">
            <strong>Strike {{ formatNumber(hoverState.openInterest.row.strike, 0) }}</strong>
            <span>OI total {{ formatCompactNumber(hoverState.openInterest.row.open_interest_total) }}</span>
            <span>Calls {{ formatCompactNumber(hoverState.openInterest.row.open_interest_call) }} / Puts {{ formatCompactNumber(hoverState.openInterest.row.open_interest_put) }}</span>
            <span>Imbalance {{ formatSignedCompact(hoverState.openInterest.row.open_interest_imbalance) }}</span>
          </div>
        </div>
        <div class="chart-scale">{{ openInterestChart.scaleNote }}</div>
        <p class="insight-text">{{ dailyInsightCards.open_interest || defaultCardText.open_interest }}</p>
      </article>
    </section>

    <section v-if="modelReady" class="grid">
      <article class="panel wide">
        <div class="panel-head">
          <div>
            <div class="eyebrow">Strike profile</div>
            <h2>Vanna + CEX by strike</h2>
          </div>
          <div class="panel-note">Bars = CEX net - Line = vanna net</div>
        </div>
        <div class="chart-box">
          <svg
            v-if="vannaCexChart.bars.length"
            class="mini-chart"
            viewBox="0 0 960 220"
            preserveAspectRatio="none"
            @mousemove="handleStrikeHover('vannaCex', vannaCexChart, $event)"
            @mouseleave="clearHover('vannaCex')"
          >
            <line
              class="zero-line"
              :x1="miniChartPadding.left"
              :x2="960 - miniChartPadding.right"
              :y1="vannaCexChart.zeroY"
              :y2="vannaCexChart.zeroY"
            />
            <line
              v-if="hoverState.vannaCex"
              class="hover-guide"
              :x1="hoverState.vannaCex.x"
              :x2="hoverState.vannaCex.x"
              :y1="miniChartPadding.top"
              :y2="220 - miniChartPadding.bottom"
            />
            <rect
              v-for="bar in vannaCexChart.bars"
              :key="`cex-${bar.strike}`"
              class="mini-bar"
              :class="bar.tone"
              :x="bar.x"
              :y="bar.y"
              :width="bar.width"
              :height="bar.height"
            />
            <path :d="vannaCexChart.linePath" class="mini-line neutral" />
            <circle
              v-if="hoverState.vannaCex"
              class="hover-point neutral"
              :cx="hoverState.vannaCex.x"
              :cy="hoverState.vannaCex.lineY"
              r="4.5"
            />
            <text
              v-for="tick in vannaCexChart.xTicks"
              :key="`vanna-tick-${tick.strike}`"
              class="tick-text"
              :x="tick.x"
              :y="210"
              text-anchor="middle"
            >
              {{ formatNumber(tick.strike, 0) }}
            </text>
          </svg>
          <div v-if="hoverState.vannaCex" class="chart-tooltip">
            <strong>Strike {{ formatNumber(hoverState.vannaCex.row.strike, 0) }}</strong>
            <span>Vanna net {{ formatSigned(hoverState.vannaCex.row.vanna_net, 4) }}</span>
            <span>VEX net {{ formatSignedCompact(hoverState.vannaCex.row.vex_net) }}</span>
            <span>Charm net {{ formatSigned(hoverState.vannaCex.row.charm_net, 4) }} / CEX net {{ formatSignedCompact(hoverState.vannaCex.row.cex_net) }}</span>
          </div>
        </div>
        <div class="chart-scale">{{ vannaCexChart.scaleNote }}</div>
        <p class="insight-text">{{ dailyInsightCards.vanna_cex || defaultCardText.vanna_cex }}</p>
      </article>

      <article class="panel">
        <div class="panel-head">
          <div>
            <div class="eyebrow">Auxiliary strike layer</div>
            <h2>Dealer inference vs core</h2>
          </div>
        </div>
        <div class="comparison">
          <div><span>Reference strike</span><strong>{{ formatNumber(referenceComparison.reference_strike, 0) }}</strong></div>
          <div><span>Inference value</span><strong>{{ formatNumber(referenceComparison.reference_dealer_inference_value, 0) }}</strong></div>
          <div><span>Confidence</span><strong>{{ formatPercent(referenceComparison.reference_confidence) }}</strong></div>
          <div><span>GEX center</span><strong>{{ formatNumber(referenceComparison.gex_center_of_mass, 0) }}</strong></div>
          <div><span>Nearest zero-pressure</span><strong>{{ formatNumber(referenceComparison.nearest_full_strike_to_zero_pressure, 0) }}</strong></div>
          <div><span>Nearest max accel</span><strong>{{ formatNumber(referenceComparison.nearest_full_strike_to_max_acceleration, 0) }}</strong></div>
        </div>
        <p class="insight-text">{{ dailyInsightCards.dealer || defaultCardText.dealer }}</p>
      </article>
    </section>

    <section v-if="modelReady" class="grid">
      <article class="panel wide">
        <div class="panel-head">
          <div>
            <div class="eyebrow">Cross-spot hedge pressure</div>
            <h2>HP(S) curve</h2>
          </div>
          <div class="panel-note">
            Spot {{ formatNumber(summary.spot_price, 0) }} - Zero {{ formatNumber(summary.zero_pressure, 0) }}
          </div>
        </div>
        <div class="chart-box">
          <svg
            v-if="pressureCurve.length"
            class="chart"
            viewBox="0 0 960 320"
            preserveAspectRatio="none"
            @mousemove="handlePressureHover($event)"
            @mouseleave="clearHover('pressure')"
          >
            <line
              v-for="tick in yTicks"
              :key="`y-${tick.value}`"
              class="grid-line"
              :x1="chartPadding.left"
              :x2="960 - chartPadding.right"
              :y1="tick.y"
              :y2="tick.y"
            />
            <line
              v-for="tick in xTicks"
              :key="`x-${tick.value}`"
              class="grid-line"
              :x1="tick.x"
              :x2="tick.x"
              :y1="chartPadding.top"
              :y2="320 - chartPadding.bottom"
            />
            <line
              v-if="zeroAxisY !== null"
              class="zero-line"
              :x1="chartPadding.left"
              :x2="960 - chartPadding.right"
              :y1="zeroAxisY"
              :y2="zeroAxisY"
            />
            <line
              v-if="hoverState.pressure"
              class="hover-guide"
              :x1="hoverState.pressure.x"
              :x2="hoverState.pressure.x"
              :y1="chartPadding.top"
              :y2="320 - chartPadding.bottom"
            />
            <path :d="curvePath" class="curve" />
            <line
              v-for="marker in chartMarkers"
              :key="marker.label"
              class="marker"
              :class="marker.tone"
              :x1="marker.x"
              :x2="marker.x"
              :y1="chartPadding.top"
              :y2="320 - chartPadding.bottom"
            />
            <circle
              v-for="marker in chartMarkers"
              :key="`${marker.label}-dot`"
              :cx="marker.x"
              :cy="marker.y"
              r="5"
              class="dot"
              :class="marker.tone"
            />
            <circle
              v-if="hoverState.pressure"
              class="hover-point accent"
              :cx="hoverState.pressure.x"
              :cy="hoverState.pressure.y"
              r="5"
            />
          </svg>
          <div v-if="hoverState.pressure" class="chart-tooltip">
            <strong>Spot {{ formatNumber(hoverState.pressure.spot, 0) }}</strong>
            <span>HP {{ formatSignedCompact(hoverState.pressure.hp) }}</span>
            <span>DEX {{ formatSignedCompact(hoverState.pressure.dex) }} / GEX {{ formatSignedCompact(hoverState.pressure.gex) }}</span>
            <span>VEX {{ formatSignedCompact(hoverState.pressure.vex) }} / CEX {{ formatSignedCompact(hoverState.pressure.cex) }}</span>
          </div>
        </div>
        <div class="chart-scale">{{ pressureScaleNote }}</div>
        <div class="marker-list">
          <div v-for="marker in chartMarkers" :key="`${marker.label}-legend`" class="marker-pill">
            <span>{{ marker.label }}</span>
            <strong>{{ formatNumber(marker.value, 0) }}</strong>
          </div>
        </div>
        <p class="insight-text">{{ dailyInsightCards.pressure || defaultCardText.pressure }}</p>
      </article>

      <article class="panel">
        <div class="panel-head">
          <div>
            <div class="eyebrow">Run context</div>
            <h2>Live structure</h2>
          </div>
        </div>
        <div class="comparison">
          <div><span>Captured at</span><strong>{{ modelTimestampLabel }}</strong></div>
          <div><span>Prepared options</span><strong>{{ model?.diagnostics?.prepared_count ?? '--' }}</strong></div>
          <div><span>Full tier</span><strong>{{ tierCounts.full }}</strong></div>
          <div><span>Structural tier</span><strong>{{ tierCounts.structural }}</strong></div>
          <div><span>Liquid tier</span><strong>{{ tierCounts.liquid }}</strong></div>
          <div><span>Critical tier</span><strong>{{ tierCounts.critical }}</strong></div>
          <div><span>WIN equivalent</span><strong>{{ formatSigned(summary.win_delta_equivalent, 0) }}</strong></div>
        </div>
      </article>
    </section>

    <section v-if="modelReady" class="grid">
      <article class="panel wide">
        <div class="panel-head">
          <div>
            <div class="eyebrow">Strike table</div>
            <h2>Dealer inference rows</h2>
          </div>
          <div class="panel-note">{{ dealerRowsSummary }}</div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Strike</th>
                <th>Inference</th>
                <th>Inference Fut</th>
                <th>Shift</th>
                <th>Conf.</th>
                <th>OI total</th>
                <th>IV</th>
                <th>OI score</th>
                <th>GEX</th>
                <th>Gamma</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in dealerRows" :key="row.strike" :class="{ highlight: isReferenceStrike(row.strike) }">
                <td>{{ formatNumber(row.strike, 0) }}</td>
                <td>{{ formatNumber(row.dealer_inference_value, 0) }}</td>
                <td>{{ formatNumber(row.dealer_inference_future_value, 0) }}</td>
                <td :class="toneClass(row.dealer_inference_shift)">{{ formatSigned(row.dealer_inference_shift, 0) }}</td>
                <td>{{ formatPercent(row.dealer_inference_confidence) }}</td>
                <td>{{ formatCompactNumber((row.oi_call || 0) + (row.oi_put || 0)) }}</td>
                <td :class="toneClass(row.iv_skew_score)">{{ formatSigned(row.iv_skew_score, 2) }}</td>
                <td :class="toneClass(row.oi_imbalance_score)">{{ formatSigned(row.oi_imbalance_score, 2) }}</td>
                <td :class="toneClass(row.gex_score)">{{ formatSigned(row.gex_score, 2) }}</td>
                <td :class="toneClass(row.gamma_score)">{{ formatSigned(row.gamma_score, 2) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>
    </section>

    <section v-if="modelReady" class="grid">
      <article class="panel wide">
        <div class="panel-head">
          <div>
            <div class="eyebrow">Context chat</div>
            <h2>Converse com o agente de opções</h2>
          </div>
          <div class="panel-note">Usa o model run atual, os cards do dia e o histórico recente do chat.</div>
        </div>
        <div class="chat-shell">
          <div class="chat-messages">
            <div v-if="!chatMessages.length" class="chat-empty">
              Pergunte sobre dealer positioning, gamma flip, basis spot-futuro, strikes importantes, Vanna, CEX ou leitura operacional do dia.
            </div>
            <div v-for="(item, index) in chatMessages" :key="`${item.created_at || index}-${item.role}`" class="chat-bubble" :class="item.role">
              <div class="chat-role">{{ item.role === 'assistant' ? 'Agente' : 'Você' }}</div>
              <div class="chat-text">{{ item.content }}</div>
              <div class="chat-time">{{ formatDateTime(item.created_at) }}</div>
            </div>
          </div>
          <div class="chat-input-row">
            <textarea
              v-model="chatInput"
              class="chat-input"
              rows="3"
              placeholder="Ex.: explique a região do dealer de hoje, o que significa o gamma flip atual e como isso conversa com o WIN."
              @keydown.ctrl.enter.prevent="handleSendChat"
            ></textarea>
            <button class="primary chat-send" :disabled="chatSending || !chatInput.trim()" @click="handleSendChat">
              {{ chatSending ? 'Enviando...' : 'Enviar' }}
            </button>
          </div>
        </div>
      </article>
    </section>

    <section v-if="!modelReady && !loading" class="empty">
      {{ emptyModelMessage }}
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import AquilesBrand from '../components/AquilesBrand.vue'
import {
  getLatestOptionsGlobal,
  getLatestOptionsModel,
  getLatestSnapshot,
  getOptionsStatus,
  getOptionsUniverse,
  getOptionsChat,
  runOptionsGlobal,
  runOptionsModel,
  sendOptionsChatMessage
} from '../api/options'

const router = useRouter()
const form = reactive({ underlyingSecurity: 'IBOVE Index', universeTier: 'full', signConvention: 'neutral' })
const loading = ref(false)
const running = ref(false)
const globalRunning = ref(false)
const chatSending = ref(false)
const errorMessage = ref('')
const status = ref({})
const universe = ref({})
const model = ref(null)
const globalModel = ref(null)
const latestSnapshot = ref(null)
const selectedGlobalAsset = ref('')
const chatThread = ref({ messages: [] })
const chatInput = ref('')
const chartPadding = { top: 24, right: 32, bottom: 40, left: 64 }
const miniChartPadding = { top: 20, right: 24, bottom: 28, left: 44 }
const hoverState = reactive({
  gammaGex: null,
  deltaDex: null,
  openInterest: null,
  vannaCex: null,
  pressure: null
})

const summary = computed(() => model.value?.summary || {})
const globalSummary = computed(() => globalModel.value?.summary || {})
const globalDeskSummary = computed(() => globalSummary.value?.desk_summary || {})
const globalCrossAssetMap = computed(() => globalModel.value?.cross_asset_level_map || {})
const pressure = computed(() => model.value?.pressure || {})
const pressureCurve = computed(() => pressure.value?.curve || [])
const referenceComparison = computed(() => model.value?.dealer_inference?.comparison || summary.value?.dealer_inference_comparison || {})
const rangeProjection = computed(() => model.value?.range_projection || {})
const rangeCenter = computed(() => rangeProjection.value?.center || {})
const rangeBands = computed(() => rangeProjection.value?.bands || [])
const universeEntry = computed(() => universe.value?.underlyings?.[form.underlyingSecurity] || {})
const strikeProfiles = computed(() => (model.value?.strike_profiles || [])
  .filter((row) => Number(row?.open_interest_total || 0) > 0))
const gammaFlipHistory = computed(() => model.value?.gamma_flip_history || {})
const dailyInsights = computed(() => model.value?.daily_insights || {})
const dailyInsightCards = computed(() => dailyInsights.value?.cards || {})
const modelReady = computed(() => Boolean(model.value?.run_id))
const globalModelReady = computed(() => Boolean(globalModel.value?.run_id))
const collectorRunning = computed(() => Boolean(status.value?.collector?.running))
const tradeSymbol = computed(() => status.value?.trade_map?.[form.underlyingSecurity] || '--')
const availableUnderlyings = computed(() => status.value?.underlyings?.length ? status.value.underlyings : ['IBOVE Index'])
const tierCounts = computed(() => ({
  full: (universeEntry.value?.full || []).length,
  structural: (universeEntry.value?.structural || []).length,
  liquid: (universeEntry.value?.liquid || []).length,
  critical: (universeEntry.value?.critical || []).length
}))
const latestSnapshotBatch = computed(() => latestSnapshot.value?.batch || null)
const latestSnapshotAvailable = computed(() => Boolean(latestSnapshotBatch.value?.captured_at))
const latestBatchLabel = computed(() => {
  const batch = latestSnapshotBatch.value || status.value?.latest_batches?.[form.universeTier]
  return batch?.captured_at ? `${formatDateTime(batch.captured_at)} - ${batch.row_count || 0} rows` : '--'
})
const latestSnapshotNote = computed(() => {
  const batch = latestSnapshotBatch.value
  if (!batch?.captured_at) return `No saved ${form.universeTier} snapshot yet`
  return `${form.universeTier} | ${batch.session_date || '--'} | ${batch.batch_key || '--'}`
})
const emptyModelMessage = computed(() => (
  latestSnapshotAvailable.value
    ? `No persisted model run was found yet for this underlying. Latest ${form.universeTier} snapshot loaded from ${latestBatchLabel.value}; run the model manually when you want.`
    : 'No persisted model run or saved snapshot was found yet for this underlying. You can run the model now from this page.'
))
const modelTimestampLabel = computed(() => model.value?.captured_at ? formatDateTime(model.value.captured_at) : '--')
const globalTimestampLabel = computed(() => globalModel.value?.captured_at ? formatDateTime(globalModel.value.captured_at) : '--')
const optionsDisplaySpotPrice = computed(() => toFiniteNumber(
  summary.value?.spot_price,
  model.value?.market_context?.spot_price,
))
const optionsDisplayForwardPrice = computed(() => toFiniteNumber(
  summary.value?.forward_price,
  model.value?.market_context?.forward_price,
))
const optionsDisplayBasisPoints = computed(() => {
  const spot = optionsDisplaySpotPrice.value
  const forward = optionsDisplayForwardPrice.value
  if (Number.isFinite(spot) && Number.isFinite(forward) && spot > 0) {
    return forward - spot
  }
  return toFiniteNumber(
    summary.value?.future_basis_points,
    model.value?.market_context?.future_basis_points,
  )
})
const optionsDisplayBasisPct = computed(() => {
  const spot = optionsDisplaySpotPrice.value
  const basis = optionsDisplayBasisPoints.value
  if (Number.isFinite(spot) && Number.isFinite(basis) && spot > 0) {
    return basis / spot
  }
  return toFiniteNumber(
    summary.value?.future_basis_pct,
    model.value?.market_context?.future_basis_pct,
  )
})
const globalAssetRows = computed(() => globalSummary.value?.asset_states || [])
const globalGammaAssets = computed(() => [...globalAssetRows.value]
  .sort((a, b) => {
    const supportRank = { A: 0, B: 1, C: 2 }
    const left = supportRank[String(a.support_level || 'C').toUpperCase()] ?? 9
    const right = supportRank[String(b.support_level || 'C').toUpperCase()] ?? 9
    if (left !== right) return left - right
    return String(a.label || a.asset || '').localeCompare(String(b.label || b.asset || ''))
  }))
const selectedGlobalAssetRow = computed(() => {
  const rows = globalGammaAssets.value
  if (!rows.length) return null
  return rows.find((row) => row.asset === selectedGlobalAsset.value) || rows[0]
})
const selectedGlobalAssetSourceLabel = computed(() => {
  const row = selectedGlobalAssetRow.value
  if (!row) return '--'
  const source = row.dealer_zone_source_underlying || row.dealer_zone_source_security || '--'
  return `${source} - ${formatSourceMode(row.dealer_zone_source_mode)}`
})
const globalMappedLevels = computed(() => globalCrossAssetMap.value?.representative_levels?.length
  ? globalCrossAssetMap.value.representative_levels
  : (globalCrossAssetMap.value?.mapped_levels || []))
const globalUpsideLevels = computed(() => globalCrossAssetMap.value?.representative_upside_levels || [])
const globalDownsideLevels = computed(() => globalCrossAssetMap.value?.representative_downside_levels || [])
const globalMappedClusters = computed(() => globalCrossAssetMap.value?.clusters || [])
const globalStrongestCluster = computed(() => globalCrossAssetMap.value?.strongest_cluster || {})
const globalNearestUpsideCluster = computed(() => globalCrossAssetMap.value?.nearest_upside_cluster || {})
const globalNearestDownsideCluster = computed(() => globalCrossAssetMap.value?.nearest_downside_cluster || {})
const selectedGlobalGammaRegions = computed(() => {
  const row = selectedGlobalAssetRow.value
  if (!row) return []
  const regions = []
  const dealerCore = Number(row.dealer_core || 0)
  const zeroPressure = Number(row.zero_pressure || 0)
  const acceleration = Number(row.acceleration_level || 0)
  const pinLow = Number(row.pinning_band_low || 0)
  const pinHigh = Number(row.pinning_band_high || 0)

  if (dealerCore > 0) {
    regions.push({
      key: 'dealer_core',
      label: 'Dealer core',
      level: dealerCore,
      rangeLabel: 'Ponto',
      note: 'Centro principal de dealer e de concentração de gamma.'
    })
  }
  if (zeroPressure > 0) {
    regions.push({
      key: 'zero_pressure',
      label: 'Zero pressure',
      level: zeroPressure,
      rangeLabel: 'Ponto',
      note: 'Nível em que a pressão agregada tende a mudar de sinal.'
    })
  }
  if (acceleration > 0) {
    regions.push({
      key: 'acceleration',
      label: 'Acceleration',
      level: acceleration,
      rangeLabel: 'Ponto',
      note: 'Região em que o hedge marginal tende a acelerar mais.'
    })
  }
  if (pinLow > 0 && pinHigh > 0 && pinHigh >= pinLow) {
    regions.push({
      key: 'pinning_band',
      label: 'Pinning band',
      level: (pinLow + pinHigh) / 2,
      rangeLabel: `${formatNumber(pinLow, 2)} até ${formatNumber(pinHigh, 2)}`,
      note: 'Faixa de estabilização e absorção observada para o ativo.'
    })
  }
  return regions
})
const selectedGlobalProjectedLevels = computed(() => {
  const row = selectedGlobalAssetRow.value
  if (!row) return []
  return [...(globalCrossAssetMap.value?.mapped_levels || [])]
    .filter((item) => item.asset === row.asset)
    .sort((a, b) => Number(b.confluence_score || 0) - Number(a.confluence_score || 0))
    .slice(0, 12)
})
const globalTopExplainers = computed(() => {
  const items = globalDeskSummary.value?.ativos_que_mais_explicam || []
  return items.length ? items.join(', ') : '--'
})
const dailyInsightSourceLabel = computed(() => {
  const source = String(dailyInsights.value?.source || '').trim().toLowerCase()
  if (source === 'llm') return 'AI daily read'
  if (source === 'fallback') return 'Fallback daily read'
  if (source === 'disabled') return 'Daily read disabled'
  return 'Daily read'
})
const dailyInsightTimestampLabel = computed(() => dailyInsights.value?.generated_at ? formatDateTime(dailyInsights.value.generated_at) : '--')
const gammaFlipStatusLabel = computed(() => {
  const statusText = String(gammaFlipHistory.value?.latest_data_status || '').trim()
  if (statusText === 'provisional_snapshot_oi') return 'Current day using provisional OI from latest snapshot'
  if (statusText === 'daily_oi_history') return 'Current day using saved daily OI history'
  return 'No current-day flip state'
})
const defaultCardText = {
  pressure: 'Pressure is still the primary map. Zero-pressure and max acceleration matter more than any single strike heuristic.',
  dealer: 'Dealer inference is an auxiliary strike-level view. Use it to refine timing, not to override the core spot curve.',
  gamma_gex: 'Gamma and GEX show where convexity is concentrated. Heavy clusters tend to matter more when they sit near active spot.',
  delta_dex: 'Delta and DEX help frame the directional hedge load. Strong directional pressure matters more when basis and future confirm it.',
  open_interest: 'Open interest is structural context. It matters most when it aligns with live pressure, not in isolation.',
  vanna_cex: 'Vanna and charm are secondary accelerants. They are useful for timing and decay pressure, but still sit below the core HP map.'
}
const topCards = computed(() => [
  { label: 'IBOV', value: formatNumber(optionsDisplaySpotPrice.value, 0), note: `XB1 ${formatNumber(optionsDisplayForwardPrice.value, 0)}` },
  { label: 'Basis XB1-IBOV', value: formatSigned(optionsDisplayBasisPoints.value, 0), note: formatPercent(optionsDisplayBasisPct.value) },
  { label: 'DEX', value: formatSigned(summary.value.dex_total, 0), note: `Future notional ${formatSignedCompact(summary.value.dex_notional_future_total)}` },
  { label: 'GEX', value: formatSigned(summary.value.gex_total, 2), note: `Future notional ${formatSignedCompact(summary.value.gex_notional_future_total)}` },
  { label: 'VEX', value: formatSigned(summary.value.vex_total, 2), note: `Future notional ${formatSignedCompact(summary.value.vex_notional_future_total)}` },
  { label: 'CEX', value: formatSigned(summary.value.cex_total, 2), note: `Future notional ${formatSignedCompact(summary.value.cex_notional_future_total)}` },
  { label: 'Zero pressure', value: formatNumber(summary.value.zero_pressure, 0), note: `Pin ${formatRange(summary.value.pinning_band)}` },
  { label: 'Max acceleration', value: formatNumber(summary.value.max_acceleration, 0), note: `Accel ${formatRange(summary.value.acceleration_band)}` },
  { label: 'Dealer inference', value: formatNumber(referenceComparison.value.reference_dealer_inference_value, 0), note: `Confidence ${formatPercent(referenceComparison.value.reference_confidence)}` }
])
const dealerRowsAll = computed(() => [...(model.value?.dealer_inference?.rows || [])])
const dealerRows = computed(() => dealerRowsAll.value
  .filter((row) => Number(row.oi_total ?? ((row.oi_call || 0) + (row.oi_put || 0))) > 0 && Math.abs(Number(row.gex_net || 0)) > 0)
  .sort((a, b) => Number(a.strike || 0) - Number(b.strike || 0)))
const dealerRowsSummary = computed(() => {
  const usefulCount = dealerRows.value.length
  const totalCount = dealerRowsAll.value.length
  return `${usefulCount} rows with OI + GEX · ${totalCount} total`
})
const gammaFlipDates = computed(() => [...(gammaFlipHistory.value?.dates || [])].reverse())
const latestFlipPoints = computed(() => gammaFlipHistory.value?.latest_flip_points || [])
const historicalRegimeFlips = computed(() => gammaFlipHistory.value?.historical_regime_flips || [])
const allGammaFlipEvents = computed(() => {
  const rows = []
  for (const day of gammaFlipDates.value) {
    for (const event of (day?.flip_events || [])) {
      rows.push({
        trade_date: day.trade_date,
        total_open_interest: Number(day.total_open_interest || 0),
        data_status: day.data_status,
        flip_strike: Number(event.flip_strike || 0),
        from_sign: event.from_sign || 'neutral',
        to_sign: event.to_sign || 'neutral',
        direction: event.direction || `${event.from_sign || 'neutral'}_to_${event.to_sign || 'neutral'}`
      })
    }
  }
  return rows.sort((a, b) => {
    if (a.trade_date === b.trade_date) return Number(a.flip_strike || 0) - Number(b.flip_strike || 0)
    return String(b.trade_date || '').localeCompare(String(a.trade_date || ''))
  })
})
const chatMessages = computed(() => chatThread.value?.messages || [])

const pressureExtents = computed(() => {
  if (!pressureCurve.value.length) return null
  const spots = pressureCurve.value.map((point) => Number(point.spot || 0))
  const hpValues = pressureCurve.value.map((point) => Number(point.hp || 0))
  return {
    minSpot: Math.min(...spots),
    maxSpot: Math.max(...spots),
    minValue: Math.min(0, ...hpValues),
    maxValue: Math.max(0, ...hpValues)
  }
})
const curvePath = computed(() => {
  if (!pressureExtents.value) return ''
  return pressureCurve.value
    .map((point, index) => `${index ? 'L' : 'M'} ${scaleX(Number(point.spot || 0))} ${scaleY(Number(point.hp || 0))}`)
    .join(' ')
})
const zeroAxisY = computed(() => pressureExtents.value ? scaleY(0) : null)
const xTicks = computed(() => buildTicks(pressureExtents.value?.minSpot, pressureExtents.value?.maxSpot, 5).map((value) => ({ value, x: scaleX(value) })))
const yTicks = computed(() => buildTicks(pressureExtents.value?.minValue, pressureExtents.value?.maxValue, 5).map((value) => ({ value, y: scaleY(value) })))
const chartMarkers = computed(() => {
  if (!pressureExtents.value) return []
  const source = [
    { label: 'Spot', tone: 'spot', value: Number(summary.value.spot_price || 0), hp: interpolateHp(Number(summary.value.spot_price || 0)) },
    { label: 'Zero Pressure', tone: 'neutral', value: Number(summary.value.zero_pressure || 0), hp: 0 },
    { label: 'Max Acceleration', tone: 'accent', value: Number(summary.value.max_acceleration || 0), hp: interpolateHp(Number(summary.value.max_acceleration || 0)) },
    { label: 'Dealer Ref', tone: 'dealer', value: Number(referenceComparison.value.reference_dealer_inference_value || 0), hp: interpolateHp(Number(referenceComparison.value.reference_dealer_inference_value || 0)) }
  ]
  return source
    .filter((item) => Number.isFinite(item.value) && item.value > 0)
    .map((item) => ({ ...item, x: scaleX(item.value), y: scaleY(item.hp) }))
})
const pressureScaleNote = computed(() => {
  if (!pressureCurve.value.length || !pressureExtents.value) return '--'
  return `Spot grid ${formatNumber(pressureExtents.value.minSpot, 0)} to ${formatNumber(pressureExtents.value.maxSpot, 0)} - HP ${formatSignedCompact(pressureExtents.value.minValue)} to ${formatSignedCompact(pressureExtents.value.maxValue)}`
})

const gammaGexChart = computed(() => buildStrikeChart(strikeProfiles.value, 'gex_net', 'gamma_net', {
  barLabel: 'GEX net',
  lineLabel: 'Gamma net',
  positiveBars: false,
  barDigits: 2,
  lineDigits: 4
}))
const deltaDexChart = computed(() => buildStrikeChart(strikeProfiles.value, 'dex_net', 'delta_net', {
  barLabel: 'DEX net',
  lineLabel: 'Delta net',
  positiveBars: false,
  barDigits: 2,
  lineDigits: 4
}))
const openInterestChart = computed(() => buildStrikeChart(strikeProfiles.value, 'open_interest_total', 'open_interest_imbalance', {
  barLabel: 'Open interest total',
  lineLabel: 'OI imbalance',
  positiveBars: true,
  barDigits: 0,
  lineDigits: 0
}))
const vannaCexChart = computed(() => buildStrikeChart(strikeProfiles.value, 'cex_net', 'vanna_net', {
  barLabel: 'CEX net',
  lineLabel: 'Vanna net',
  positiveBars: false,
  barDigits: 2,
  lineDigits: 4
}))

function normalize(value, min, max) {
  return !Number.isFinite(value) || !Number.isFinite(min) || !Number.isFinite(max) || max - min <= 0
    ? 0.5
    : (value - min) / (max - min)
}

function scaleX(value) {
  return chartPadding.left + normalize(value, pressureExtents.value.minSpot, pressureExtents.value.maxSpot) * (960 - chartPadding.left - chartPadding.right)
}

function scaleY(value) {
  return 320 - chartPadding.bottom - normalize(value, pressureExtents.value.minValue, pressureExtents.value.maxValue) * (320 - chartPadding.top - chartPadding.bottom)
}

function scaleMiniValue(value, min, max, height) {
  const ratio = normalize(value, min, max)
  return 220 - miniChartPadding.bottom - ratio * height
}

function buildTicks(min, max, count) {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return []
  if (Math.abs(max - min) < 1e-9) return [min]
  const step = (max - min) / Math.max(count - 1, 1)
  return Array.from({ length: count }, (_, index) => min + step * index)
}

function buildStrikeChart(rows, barKey, lineKey, options = {}) {
  const normalizedRows = (rows || []).map((row) => ({
    ...row,
    strike: Number(row.strike || 0),
    barValue: Number(row[barKey] || 0),
    lineValue: Number(row[lineKey] || 0)
  }))
  if (!normalizedRows.length) {
    return { bars: [], linePath: '', zeroY: 110, points: [], xTicks: [], scaleNote: '--' }
  }

  const width = 960 - miniChartPadding.left - miniChartPadding.right
  const height = 220 - miniChartPadding.top - miniChartPadding.bottom
  const barMin = options.positiveBars ? 0 : Math.min(0, ...normalizedRows.map((row) => row.barValue))
  const barMax = Math.max(0, ...normalizedRows.map((row) => row.barValue))
  const lineMin = Math.min(0, ...normalizedRows.map((row) => row.lineValue))
  const lineMax = Math.max(0, ...normalizedRows.map((row) => row.lineValue))
  const slot = width / Math.max(normalizedRows.length, 1)
  const barWidth = Math.max(Math.min(slot * 0.62, 18), 4)
  const zeroY = scaleMiniValue(0, barMin, barMax, height)

  const points = normalizedRows.map((row, index) => {
    const x = miniChartPadding.left + slot * index + slot / 2
    const barYValue = scaleMiniValue(row.barValue, barMin, barMax, height)
    const lineY = scaleMiniValue(row.lineValue, lineMin, lineMax, height)
    return {
      row,
      strike: row.strike,
      x,
      lineY,
      barY: Math.min(zeroY, barYValue),
      barHeight: Math.max(Math.abs(zeroY - barYValue), 1),
      tone: row.barValue >= 0 ? 'positive-fill' : 'negative-fill'
    }
  })
  const bars = points.map((point) => ({
    strike: point.strike,
    x: point.x - barWidth / 2,
    y: point.barY,
    width: barWidth,
    height: point.barHeight,
    tone: point.tone
  }))
  const linePath = points
    .map((point, index) => `${index ? 'L' : 'M'} ${point.x} ${point.lineY}`)
    .join(' ')
  const xTickIndexes = buildTickIndexes(points.length, 5)
  const xTicks = xTickIndexes.map((index) => ({ strike: points[index].strike, x: points[index].x }))
  return {
    bars,
    linePath,
    zeroY,
    points,
    xTicks,
    scaleNote: `Strikes ${formatNumber(points[0].strike, 0)} to ${formatNumber(points[points.length - 1].strike, 0)} - ${options.barLabel || 'Bars'} ${formatSignedCompact(barMin)} to ${formatSignedCompact(barMax)} - ${options.lineLabel || 'Line'} ${formatSigned(lineMin, options.lineDigits ?? 2)} to ${formatSigned(lineMax, options.lineDigits ?? 2)}`
  }
}

function buildTickIndexes(length, desiredCount) {
  if (length <= desiredCount) return Array.from({ length }, (_, index) => index)
  const step = (length - 1) / Math.max(desiredCount - 1, 1)
  return Array.from({ length: desiredCount }, (_, index) => Math.round(index * step))
}

function chartPointerX(event, width) {
  const rect = event.currentTarget.getBoundingClientRect()
  const ratio = rect.width > 0 ? (event.clientX - rect.left) / rect.width : 0
  return Math.max(0, Math.min(width, ratio * width))
}

function handleStrikeHover(key, chart, event) {
  if (!chart?.points?.length) return
  const x = chartPointerX(event, 960)
  const nearest = chart.points.reduce((best, point) => (
    Math.abs(point.x - x) < Math.abs(best.x - x) ? point : best
  ), chart.points[0])
  hoverState[key] = nearest
}

function handlePressureHover(event) {
  if (!pressureCurve.value.length || !pressureExtents.value) return
  const x = chartPointerX(event, 960)
  const nearest = pressureCurve.value.reduce((best, point) => {
    const pointX = scaleX(Number(point.spot || 0))
    return Math.abs(pointX - x) < Math.abs(best.x - x)
      ? { ...point, x: pointX, y: scaleY(Number(point.hp || 0)) }
      : best
  }, {
    ...pressureCurve.value[0],
    x: scaleX(Number(pressureCurve.value[0].spot || 0)),
    y: scaleY(Number(pressureCurve.value[0].hp || 0))
  })
  hoverState.pressure = nearest
}

function clearHover(key) {
  hoverState[key] = null
}

function interpolateHp(spot) {
  if (!pressureCurve.value.length || !Number.isFinite(spot)) return 0
  const nearest = pressureCurve.value.reduce((best, point) => (
    Math.abs(Number(point.spot || 0) - spot) < Math.abs(Number(best.spot || 0) - spot) ? point : best
  ), pressureCurve.value[0])
  return Number(nearest.hp || 0)
}

function formatNumber(value, digits = 2) {
  return Number.isFinite(Number(value))
    ? new Intl.NumberFormat('pt-BR', { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(Number(value))
    : '--'
}

function toFiniteNumber(...values) {
  for (const value of values) {
    const numeric = Number(value)
    if (Number.isFinite(numeric)) return numeric
  }
  return Number.NaN
}

function formatSigned(value, digits = 2) {
  return Number.isFinite(Number(value))
    ? new Intl.NumberFormat('pt-BR', {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
      signDisplay: 'always'
    }).format(Number(value))
    : '--'
}

function formatCompactNumber(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '--'
  const units = [
    { value: 1e15, suffix: 'Qa' },
    { value: 1e12, suffix: 'T' },
    { value: 1e9, suffix: 'B' },
    { value: 1e6, suffix: 'M' },
    { value: 1e3, suffix: 'k' }
  ]
  const absValue = Math.abs(numeric)
  const unit = units.find((entry) => absValue >= entry.value)
  if (!unit) return formatNumber(numeric, 0)
  return `${(numeric / unit.value).toFixed(2)}${unit.suffix}`
}

function formatSignedCompact(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '--'
  const compact = formatCompactNumber(Math.abs(numeric))
  return `${numeric >= 0 ? '+' : '-'}${compact}`
}

function formatPercent(value) {
  return Number.isFinite(Number(value)) ? `${(Number(value) * 100).toFixed(1)}%` : '--'
}

function formatRange(range) {
  return range?.length ? `${formatNumber(range[0], 0)} to ${formatNumber(range[1], 0)}` : '--'
}

function formatRegime(value) {
  const text = String(value || '').trim().toLowerCase()
  if (text === 'positive') return 'gamma positivo'
  if (text === 'negative') return 'gamma negativo'
  return 'gamma neutro'
}

function formatDateTime(value) {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? (value || '--')
    : new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' }).format(date)
}

function formatFlipDirection(direction) {
  if (direction === 'negative_to_positive') return 'Negativo → positivo'
  if (direction === 'positive_to_negative') return 'Positivo → negativo'
  if (direction === 'neutral_to_positive') return 'Neutro → positivo'
  if (direction === 'neutral_to_negative') return 'Neutro → negativo'
  return String(direction || '--').replaceAll('_', ' ')
}

function formatGammaFlipStatus(status) {
  if (status === 'provisional_snapshot_oi') return 'Provisório intraday'
  if (status === 'daily_oi_history') return 'Histórico diário'
  return '--'
}

function formatSourceMode(mode) {
  if (mode === 'options_model') return 'options model'
  if (mode === 'partial_iv') return 'IV parcial'
  if (mode === 'price_proxy') return 'proxy de preço/vol'
  return '--'
}

function toneClass(value) {
  const numeric = Number(value || 0)
  return numeric > 0 ? 'positive' : numeric < 0 ? 'negative' : ''
}

function isReferenceStrike(strike) {
  return Number(strike || 0) === Number(referenceComparison.value.reference_strike || 0)
}

async function loadChatThread() {
  try {
    const response = await getOptionsChat({
      underlying_security: form.underlyingSecurity,
      sign_convention: form.signConvention
    })
    chatThread.value = response.data || { messages: [] }
  } catch {
    chatThread.value = { messages: [] }
  }
}

async function refreshDashboard() {
  loading.value = true
  errorMessage.value = ''
  try {
    const [statusResponse, universeResponse, snapshotResponse, modelResponse, globalResponse, chatResponse] = await Promise.all([
      getOptionsStatus(),
      getOptionsUniverse({ underlying_security: form.underlyingSecurity }),
      getLatestSnapshot({ underlying_security: form.underlyingSecurity, tier: form.universeTier, limit: 1 }),
      getLatestOptionsModel({ underlying_security: form.underlyingSecurity, universe_tier: form.universeTier }),
      getLatestOptionsGlobal({ underlying_security: form.underlyingSecurity }),
      getOptionsChat({ underlying_security: form.underlyingSecurity, sign_convention: form.signConvention })
    ])
    status.value = statusResponse.data || {}
    universe.value = universeResponse.data || {}
    latestSnapshot.value = snapshotResponse.data?.batch ? snapshotResponse.data : null
    model.value = modelResponse.data?.run_id ? modelResponse.data : null
    globalModel.value = globalResponse.data?.run_id ? globalResponse.data : null
    chatThread.value = chatResponse.data || { messages: [] }
  } catch (error) {
    errorMessage.value = error?.message || 'Failed to load the options dashboard.'
  } finally {
    loading.value = false
  }
}

async function handleRunModel() {
  running.value = true
  errorMessage.value = ''
  try {
    const response = await runOptionsModel({
      underlying_security: form.underlyingSecurity,
      universe_tier: form.universeTier,
      sign_convention: form.signConvention
    })
    model.value = response.data || null
    const [statusResponse, universeResponse, snapshotResponse] = await Promise.all([
      getOptionsStatus(),
      getOptionsUniverse({ underlying_security: form.underlyingSecurity }),
      getLatestSnapshot({ underlying_security: form.underlyingSecurity, tier: form.universeTier, limit: 1 })
    ])
    status.value = statusResponse.data || {}
    universe.value = universeResponse.data || {}
    latestSnapshot.value = snapshotResponse.data?.batch ? snapshotResponse.data : latestSnapshot.value
    globalModel.value = null
    await loadChatThread()
  } catch (error) {
    errorMessage.value = error?.message || 'Failed to run the options model.'
  } finally {
    running.value = false
  }
}

async function handleRunGlobalModel() {
  if (!modelReady.value) return
  globalRunning.value = true
  errorMessage.value = ''
  try {
    const response = await runOptionsGlobal({
      underlying_security: form.underlyingSecurity,
      refresh_local_model: false
    })
    globalModel.value = response.data || null
  } catch (error) {
    errorMessage.value = error?.message || 'Failed to run the global triangulation overlay.'
  } finally {
    globalRunning.value = false
  }
}

async function handleSendChat() {
  if (!chatInput.value.trim() || chatSending.value) return
  chatSending.value = true
  errorMessage.value = ''
  try {
    const response = await sendOptionsChatMessage({
      underlying_security: form.underlyingSecurity,
      sign_convention: form.signConvention,
      run_id: model.value?.run_id,
      message: chatInput.value.trim()
    })
    chatThread.value = response.data || { messages: [] }
    chatInput.value = ''
  } catch (error) {
    errorMessage.value = error?.message || 'Falha ao enviar mensagem para o agente de opções.'
  } finally {
    chatSending.value = false
  }
}

function goHome() {
  router.push({ name: 'Home' })
}

function goChart() {
  router.push({ name: 'Chart' })
}

onMounted(async () => {
  await refreshDashboard()
})
</script>

<style scoped>
.options-shell{min-height:100vh;padding:28px;background:radial-gradient(circle at top right,rgba(189,199,213,.22),transparent 28%),linear-gradient(180deg,#f9fbfd 0%,#edf2f7 100%);color:#161a21}
.header,.controls,.cards,.grid,.empty,.error,.overview-panel{width:min(1440px,100%);margin:0 auto}
.header{display:flex;justify-content:space-between;gap:24px;align-items:flex-start}
.header-copy{display:grid;gap:10px}
.header h1{margin:8px 0 10px;font-size:clamp(2.4rem,4vw,4rem);line-height:.95}
.header p{max-width:820px;line-height:1.65;color:#566171}
.eyebrow,.controls span,.panel-note span{font-size:.74rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#748093}
.actions,.controls,.cards,.grid,.comparison{display:grid;gap:14px}
.actions{grid-auto-flow:column;grid-auto-columns:max-content}
.controls{margin-top:18px;padding:18px;background:rgba(255,255,255,.88);border:1px solid #d9e0e9;border-radius:22px;grid-template-columns:repeat(3,minmax(0,220px)) minmax(320px,1fr);align-items:end;box-shadow:0 18px 40px rgba(17,24,39,.05)}
.controls label{display:flex;flex-direction:column;gap:8px}
.controls select,.ghost,.primary{border-radius:14px;font:inherit}
.controls select{padding:12px 14px;border:1px solid #d4dbe5;background:#fcfdff}
.meta{padding:12px 14px;border:1px solid #dce3ec;border-radius:16px;background:#f7f9fc;display:grid;gap:6px;color:#5a6474}
.ghost,.primary{padding:12px 16px;border:1px solid #d5dce6;font-weight:700;cursor:pointer;transition:.16s}
.ghost{background:rgba(255,255,255,.72)}
.primary{background:#11161d;color:#f8fafc;border-color:#11161d}
.ghost:hover,.primary:hover{transform:translateY(-1px);box-shadow:0 12px 24px rgba(17,24,39,.08)}
.ghost:disabled,.primary:disabled{opacity:.6;cursor:not-allowed;transform:none;box-shadow:none}
.error,.empty,.card,.panel,.overview-panel{background:rgba(255,255,255,.92);border:1px solid #dde4ed;border-radius:24px;box-shadow:0 18px 36px rgba(17,24,39,.05)}
.error{margin-top:16px;padding:14px 16px;background:#ffe7e5;border-color:#f5b8b1;color:#8a3228}
.empty{margin-top:18px;padding:28px;text-align:center;color:#606a78}
.cards{margin-top:18px;grid-template-columns:repeat(4,minmax(0,1fr))}
.card,.panel,.overview-panel{padding:18px}
.value{margin-top:8px;font-size:1.7rem;font-weight:800;line-height:1}
.note,.panel-note,.comparison span,.chart-scale{color:#5a6474}
.overview-panel{margin-top:18px}
.overview-copy{margin:0;color:#403b35;line-height:1.65;font-size:1rem}
.overview-meta{display:flex;flex-wrap:wrap;gap:10px;margin-top:14px}
.grid{margin-top:18px;grid-template-columns:minmax(0,1.4fr) minmax(340px,.9fr)}
.wide{grid-column:span 1}
.panel-head{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;margin-bottom:14px}
.panel h2,.overview-panel h2{margin:6px 0 0;font-size:1.35rem}
.chart-box{position:relative}
.chart{width:100%;height:320px;display:block;border-radius:20px;background:linear-gradient(180deg,rgba(255,255,255,.92) 0%,rgba(249,243,233,.9) 100%);border:1px solid #eadcc7}
.grid-line{stroke:rgba(113,97,76,.12);stroke-width:1}
.zero-line{stroke:rgba(17,16,14,.24);stroke-width:1.4;stroke-dasharray:5 5}
.curve{fill:none;stroke:#ff5c1a;stroke-width:3.2;stroke-linecap:round;stroke-linejoin:round}
.marker{stroke-width:1.8;stroke-dasharray:6 6}
.dot{r:5}
.hover-guide{stroke:rgba(17,16,14,.22);stroke-width:1.2;stroke-dasharray:4 4}
.hover-point{stroke:#fff9f0;stroke-width:1.5}
.spot{stroke:#111;fill:#111}
.neutral{stroke:#7f6d58;fill:#7f6d58}
.accent{stroke:#ff5c1a;fill:#ff5c1a}
.dealer{stroke:#2f78ff;fill:#2f78ff}
.mini-chart{width:100%;height:220px;display:block;border-radius:18px;background:linear-gradient(180deg,rgba(255,255,255,.92) 0%,rgba(249,243,233,.9) 100%);border:1px solid #eadcc7}
.mini-line{fill:none;stroke-width:2.5;stroke-linecap:round;stroke-linejoin:round}
.mini-bar{opacity:.9}
.positive-fill{fill:rgba(18,116,71,.72)}
.negative-fill{fill:rgba(192,58,32,.72)}
.neutral-fill{fill:rgba(127,109,88,.55)}
.tick-text{font-size:10px;fill:#7a6047}
.chart-tooltip{margin-top:10px;display:grid;gap:4px;padding:12px 14px;border-radius:14px;background:#fff7ef;border:1px solid #ead7c1;color:#3c342d}
.chart-tooltip strong{font-size:.95rem}
.chart-scale{margin-top:10px;font-size:.9rem}
.insight-text{margin:12px 0 0;color:#423a34;line-height:1.6}
.marker-list{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}
.marker-pill,.comparison>div{padding:12px 14px;border-radius:16px;background:#fbf7f0;border:1px solid #ebdece}
.comparison{grid-template-columns:repeat(2,minmax(0,1fr))}
.table-wrap{overflow:auto}
.range-table-wrap{margin-top:16px}
.asset-zone-table{margin-top:14px}
table{width:100%;border-collapse:collapse;font-size:.94rem}
th,td{padding:12px 10px;text-align:right;border-bottom:1px solid #efe3d3;white-space:nowrap}
th:first-child,td:first-child{text-align:left}
thead th{position:sticky;top:0;background:#fffaf4;z-index:1}
.selectable-row{cursor:pointer;transition:background-color .16s ease}
.selectable-row:hover{background:rgba(255,92,26,.06)}
.active-row{background:rgba(255,92,26,.10)}
.highlight{background:rgba(255,92,26,.08)}
.positive{color:#127447;font-weight:700}
.negative{color:#c03a20;font-weight:700}
.flip-stack{display:grid;gap:12px}
.flip-points{display:flex;flex-wrap:wrap;gap:8px}
.flip-pill{padding:8px 10px;border-radius:999px;background:#eef4ff;border:1px solid #c6d8ff;color:#1f4ca3;font-weight:700}
.flip-row{display:flex;justify-content:space-between;gap:12px;padding:12px 14px;border-radius:16px;background:#fbf7f0;border:1px solid #ebdece}
.flip-values{text-align:right}
.flip-regime-box{margin-top:12px;padding:12px 14px;border-radius:16px;background:#fff8ef;border:1px solid #eadcca;display:grid;gap:6px}
.chat-shell{display:grid;gap:14px}
.chat-messages{display:grid;gap:12px;max-height:440px;overflow:auto;padding-right:4px}
.chat-empty{padding:18px;border:1px dashed #d7c7b4;border-radius:16px;color:#5f584f;background:#fffaf4}
.chat-bubble{display:grid;gap:6px;padding:14px 16px;border-radius:18px;border:1px solid #ebdece;background:#fffaf4}
.chat-bubble.user{background:#f2f7ff;border-color:#cfe0ff}
.chat-bubble.assistant{background:#fff8ef;border-color:#eadcca}
.chat-role{font-size:.78rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#7a6047}
.chat-text{white-space:pre-wrap;line-height:1.6;color:#2f2924}
.chat-time{font-size:.8rem;color:#7f766b}
.chat-input-row{display:grid;grid-template-columns:minmax(0,1fr) max-content;gap:12px;align-items:end}
.chat-input{width:100%;resize:vertical;min-height:92px;padding:14px 16px;border-radius:16px;border:1px solid #d8ccbb;background:#fffdfa;font:inherit;color:#1f1b17}
.chat-send{height:max-content}
@media (max-width:1180px){.controls,.cards,.grid{grid-template-columns:1fr}.actions{grid-auto-flow:row;justify-content:start}.comparison{grid-template-columns:1fr}}
@media (max-width:760px){.chat-input-row{grid-template-columns:1fr}}
@media (max-width:760px){.options-shell{padding:18px}.header,.panel-head{flex-direction:column}}
</style>

<template>
  <div class="dpm-root" ref="rootEl">
    <div v-if="!hasData" class="dpm-empty">
      <span v-if="loadingModel">Carregando Dealer Pain Map...</span>
      <span v-else-if="modelError">{{ modelError }}</span>
      <span v-else>Sem dados suficientes para montar o Dealer Pain Map.</span>
    </div>
    <template v-else>
      <div class="dpm-header">
        <div class="dpm-title-wrap">
          <span class="dpm-title">Dealer Pain Map</span>
          <span class="dpm-subtitle">Regioes onde o hedge do dealer pode acelerar.</span>
        </div>
        <div class="dpm-header-meta">
          <span class="dpm-pill">{{ underlyingLabel }}</span>
          <span class="dpm-pill">Spot {{ formatLevel(spot) }}</span>
          <span v-if="referenceFuturePrice != null" class="dpm-pill accent">Centro fut {{ formatLevel(referenceFuturePrice) }}</span>
          <span v-if="referenceConfidence > 0" class="dpm-pill soft">Ref {{ Math.round(referenceConfidence) }}/100</span>
          <span class="dpm-pill" :class="flowLoaded ? 'ready' : 'loading'">
            {{ flowLoaded ? 'Fluxo 1d' : 'Carregando fluxo...' }}
          </span>
          <span v-if="flowError" class="dpm-pill warn">{{ flowError }}</span>
        </div>
      </div>

      <div class="dpm-kpi-grid">
        <div class="dpm-kpi current">
          <span class="dpm-kpi-label">Pain atual</span>
          <span class="dpm-kpi-value">{{ formatScore(currentPoint?.score) }}</span>
          <span class="dpm-kpi-sub">
            <span v-if="scoreDelta15m != null">{{ scoreDelta15m >= 0 ? '+' : '' }}{{ scoreDelta15m.toFixed(0) }} pts / 15m</span>
            <span v-else>sem historico de 15m</span>
          </span>
        </div>

        <div class="dpm-kpi zone">
          <span class="dpm-kpi-label">Pain zone down</span>
          <span class="dpm-kpi-value">{{ zoneRangeLabel(bestDownZone) }}</span>
          <span class="dpm-kpi-sub">{{ zoneCauseLabel(bestDownZone) }}</span>
        </div>

        <div class="dpm-kpi zone">
          <span class="dpm-kpi-label">Pain zone up</span>
          <span class="dpm-kpi-value">{{ zoneRangeLabel(bestUpZone) }}</span>
          <span class="dpm-kpi-sub">{{ zoneCauseLabel(bestUpZone) }}</span>
        </div>

        <div class="dpm-kpi next">
          <span class="dpm-kpi-label">Proxima critica</span>
          <span class="dpm-kpi-value">{{ zoneRangeLabel(nextCriticalZone) }}</span>
          <span class="dpm-kpi-sub">
            <span v-if="nextCriticalZone">{{ formatPct(nextCriticalZone.distancePct) }} do spot</span>
            <span v-else>sem zona proxima</span>
          </span>
        </div>
      </div>

      <div class="dpm-summary-grid">
        <div class="dpm-summary-card">
          <span class="dpm-summary-label">Causa dominante</span>
          <span class="dpm-summary-value">{{ currentCauseLabel }}</span>
        </div>
        <div class="dpm-summary-card">
          <span class="dpm-summary-label">Direcao provavel</span>
          <span class="dpm-summary-value" :class="riskDirectionClass">{{ hedgeDirectionLabel }}</span>
        </div>
        <div class="dpm-summary-card">
          <span class="dpm-summary-label">Confianca</span>
          <span class="dpm-summary-value">{{ confidenceLabel }}</span>
        </div>
        <div class="dpm-summary-card">
          <span class="dpm-summary-label">Gamma flip / DEX neutral</span>
          <span class="dpm-summary-value">
            {{ formatLevel(gammaFlipLevel) }} / {{ formatLevel(dexNeutralLevel) }}
          </span>
        </div>
      </div>

      <div class="dpm-heat-card">
        <div class="dpm-heat-head">
          <div>
            <div class="dpm-section-title">Heatmap de dor</div>
            <div class="dpm-section-subtitle">Spot grid, score agregado e zonas reflexivas acima/abaixo do spot.</div>
          </div>
          <div class="dpm-chip-row">
            <span class="dpm-chip">Grid {{ heatPoints.length }} pontos</span>
            <span class="dpm-chip">Threshold {{ zoneThreshold.toFixed(0) }}</span>
            <span class="dpm-chip">{{ totalFlowLabel }}</span>
            <span class="dpm-chip">Basis {{ formatLevel(basisPoints) }}</span>
          </div>

        </div>

        <div class="dpm-heat-wrap" ref="heatWrap">
          <svg
            class="dpm-heat-svg"
            :viewBox="`0 0 ${HEAT_W} ${HEAT_H}`"
            preserveAspectRatio="none"
            @mousemove="handleHeatMove"
            @mouseleave="hoverIndex = null"
          >
            <line
              v-for="tick in scoreTicks"
              :key="`tick-${tick}`"
              :x1="PAD.left"
              :x2="HEAT_W - PAD.right"
              :y1="scoreY(tick)"
              :y2="scoreY(tick)"
              class="dpm-grid-line"
            />

            <rect
              v-for="cell in heatCells"
              :key="`cell-${cell.index}`"
              :x="cell.x"
              :y="heatBarY"
              :width="cell.w"
              :height="heatBarH"
              :fill="cell.fill"
              :fill-opacity="cell.opacity"
              :stroke="cell.stroke"
              :stroke-opacity="cell.strokeOpacity"
              stroke-width="1"
              rx="2"
            />

            <rect
              v-for="zone in heatZones"
              :key="zone.key"
              :x="zone.svgX1"
              :y="heatBarY - 8"
              :width="Math.max(zone.svgX2 - zone.svgX1, 4)"
              :height="heatBarH + 16"
              :class="zone.direction === 'up' ? 'dpm-zone-box up' : 'dpm-zone-box down'"
            />

            <path v-if="scorePath" :d="scorePath" class="dpm-score-line" />

            <line
              v-if="spotX != null"
              :x1="spotX"
              :x2="spotX"
              :y1="PAD.top"
              :y2="HEAT_H - PAD.bottom"
              class="dpm-spot-line"
            />
            <text v-if="spotX != null" :x="spotX + 4" :y="PAD.top + 10" class="dpm-spot-label">Spot</text>

            <line
              v-if="referenceX != null"
              :x1="referenceX"
              :x2="referenceX"
              :y1="PAD.top"
              :y2="HEAT_H - PAD.bottom"
              class="dpm-reference-line"
            />
            <text v-if="referenceX != null" :x="referenceX + 4" :y="PAD.top + 52" class="dpm-reference-label">Centro</text>

            <line
              v-if="gammaFlipX != null"
              :x1="gammaFlipX"
              :x2="gammaFlipX"
              :y1="PAD.top + 10"
              :y2="HEAT_H - PAD.bottom"
              class="dpm-gamma-flip-line"
            />
            <text v-if="gammaFlipX != null" :x="gammaFlipX + 4" :y="PAD.top + 24" class="dpm-gamma-flip-label">Gamma flip</text>

            <line
              v-if="dexNeutralX != null"
              :x1="dexNeutralX"
              :x2="dexNeutralX"
              :y1="PAD.top + 10"
              :y2="HEAT_H - PAD.bottom"
              class="dpm-dex-neutral-line"
            />
            <text v-if="dexNeutralX != null" :x="dexNeutralX + 4" :y="PAD.top + 38" class="dpm-dex-neutral-label">DEX neutral</text>

            <line
              v-if="hoverPoint"
              :x1="pointX(hoverPoint.index)"
              :x2="pointX(hoverPoint.index)"
              :y1="PAD.top"
              :y2="HEAT_H - PAD.bottom"
              class="dpm-hover-line"
            />
            <circle
              v-if="hoverPoint"
              :cx="pointX(hoverPoint.index)"
              :cy="scoreY(hoverPoint.score)"
              r="3.5"
              class="dpm-hover-dot"
            />

            <text
              v-for="tick in scoreTicks"
              :key="`score-${tick}`"
              :x="PAD.left - 6"
              :y="scoreY(tick)"
              class="dpm-score-tick"
              text-anchor="end"
              dominant-baseline="middle"
            >
              {{ tick }}
            </text>

            <text
              v-for="label in xLabels"
              :key="`label-${label.index}`"
              :x="label.x"
              :y="HEAT_H - PAD.bottom + 14"
              class="dpm-axis-label"
              text-anchor="middle"
            >
              {{ formatLevelShort(label.price) }}
            </text>
          </svg>

          <div v-if="hoverPoint" class="dpm-tooltip" :style="tooltipStyle">
            <div class="dpm-tooltip-head">{{ formatLevel(hoverPoint.price) }}</div>
            <div class="dpm-tooltip-row">
              <span>Dealer Pain</span>
              <b>{{ formatScore(hoverPoint.score) }}</b>
            </div>
            <div class="dpm-tooltip-row">
              <span>Causa</span>
              <b>{{ causeLabel(hoverPoint.dominantKey) }}</b>
            </div>
            <div class="dpm-tooltip-row">
              <span>DEX / GEX</span>
              <b>{{ compactNumber(hoverPoint.dex) }} / {{ compactNumber(hoverPoint.gex) }}</b>
            </div>
            <div class="dpm-tooltip-row">
              <span>Vanna / Charm</span>
              <b>{{ compactNumber(hoverPoint.vex) }} / {{ compactNumber(hoverPoint.cex) }}</b>
            </div>
            <div class="dpm-tooltip-row">
              <span>Fluxo local</span>
              <b>{{ compactNumber(hoverPoint.localFlow) }}</b>
            </div>
          </div>
        </div>

        <div class="dpm-factor-row">
          <span
            v-for="factor in topCurrentFactors"
            :key="factor.key"
            class="dpm-factor-pill"
          >
            {{ factor.label }} {{ factor.score.toFixed(0) }}
          </span>
        </div>
      </div>

      <div class="dpm-band-grid">
        <div class="dpm-card dpm-ladder-card">
          <div class="dpm-section-title">Mapa de hedge por strike</div>
          <div class="dpm-section-subtitle">Centro no futuro inferido. Cada strike replica o ajuste do dealer em mini contratos a cada janela local de gamma, com composicao por vencimento.</div>
          <div v-if="false" class="dpm-ladder-wrap">
            <svg
              class="dpm-ladder-svg"
              :viewBox="`0 0 ${LADDER_W} ${LADDER_H}`"
              preserveAspectRatio="none"
            >
              <line
                v-for="tick in pricePathHedgeTicks"
                :key="`ladder-hedge-${tick}`"
                :x1="pricePathX(tick)"
                :x2="pricePathX(tick)"
                :y1="LADDER_PAD.top"
                :y2="LADDER_H - LADDER_PAD.bottom"
                :class="tick === 0 ? 'dpm-ladder-zero' : 'dpm-ladder-hedge-tick'"
              />

              <line
                v-for="tick in pricePathPriceTicks"
                :key="`ladder-price-${tick}`"
                :x1="LADDER_PAD.left"
                :x2="LADDER_W - LADDER_PAD.right"
                :y1="pricePathY(tick)"
                :y2="pricePathY(tick)"
                :class="Math.round(tick) === Math.round(spot || 0) ? 'dpm-ladder-tick spot' : 'dpm-ladder-tick'"
              />

              <line
                v-if="referenceSpotPrice != null"
                :x1="LADDER_PAD.left"
                :x2="LADDER_W - LADDER_PAD.right"
                :y1="pricePathY(referenceSpotPrice)"
                :y2="pricePathY(referenceSpotPrice)"
                class="dpm-ladder-reference"
              />

              <text
                v-for="tick in pricePathPriceTicks"
                :key="`ladder-y-label-${tick}`"
                :x="LADDER_PAD.left - 8"
                :y="pricePathY(tick)"
                class="dpm-ladder-price-label"
                text-anchor="end"
                dominant-baseline="middle"
              >
                {{ formatLevel(tick) }}
              </text>

              <text
                v-for="tick in pricePathHedgeTicks"
                :key="`ladder-x-label-${tick}`"
                :x="pricePathX(tick)"
                :y="LADDER_H - 6"
                class="dpm-ladder-axis-label"
                text-anchor="middle"
              >
                {{ formatSignedContracts(tick) }}
              </text>

              <text
                :x="LADDER_PAD.left + 6"
                :y="LADDER_PAD.top + 10"
                class="dpm-ladder-axis-label"
              >
                Preco
              </text>

              <text
                :x="pricePathZeroX + 6"
                :y="LADDER_PAD.top + 10"
                class="dpm-ladder-axis-label"
              >
                Hedge acumulado (WIN)
              </text>

              <line
                v-for="segment in pricePathSegments"
                :key="segment.key"
                :x1="segment.x1"
                :y1="segment.y1"
                :x2="segment.x2"
                :y2="segment.y2"
                :class="`dpm-path-segment ${segment.tone}`"
              />

              <circle
                v-for="node in pricePathMarkers"
                :key="`path-node-${node.offsetPoints}`"
                :cx="node.x"
                :cy="node.y"
                :r="node.offsetPoints === 0 ? 4.4 : 3.2"
                :class="node.offsetPoints === 0 ? 'dpm-ladder-dot spot' : (node.cumulativeHedgeWin >= 0 ? 'dpm-ladder-dot pos' : 'dpm-ladder-dot neg')"
              />

              <text
                v-for="node in pricePathMarkers"
                :key="`path-node-label-${node.offsetPoints}`"
                :x="node.labelX"
                :y="node.y - 1"
                class="dpm-ladder-gex-label"
                :text-anchor="node.textAnchor"
                dominant-baseline="middle"
              >
                {{ node.offsetLabel }} {{ formatSignedContracts(node.cumulativeHedgeWin) }}
              </text>

              <text
                v-if="spot != null"
                :x="LADDER_W - LADDER_PAD.right + 6"
                :y="pricePathY(spot)"
                class="dpm-ladder-spot-tag"
                dominant-baseline="middle"
              >
                Spot
              </text>

              <text
                v-if="referenceSpotPrice != null"
                :x="LADDER_W - LADDER_PAD.right + 6"
                :y="pricePathY(referenceSpotPrice)"
                class="dpm-ladder-ref-tag"
                dominant-baseline="middle"
              >
                Ref
              </text>
            </svg>
          </div>

          <div v-if="false" class="dpm-path-grid">
            <div class="dpm-path-side">
              <div class="dpm-path-side-title down">Downside</div>
              <div
                v-for="row in pricePathDownRows"
                :key="row.key"
                class="dpm-path-row"
                :class="row.actionClass"
              >
                <div class="dpm-path-row-top">
                  <span class="dpm-path-step">{{ row.stepLabel }}</span>
                  <span class="dpm-path-range">{{ row.rangeLabel }}</span>
                </div>
                <div class="dpm-path-row-main">
                  <span class="dpm-path-action" :class="row.actionClass">{{ row.actionLabel }} {{ formatAbsoluteContracts(row.incrementalWin) }} WIN</span>
                  <span>Acum {{ formatSignedContracts(row.cumulativeWin) }}</span>
                  <span>Γ/100 {{ formatSignedContracts(row.gammaHedgeWinPer100) }}</span>
                </div>
                <div class="dpm-path-row-sub">Exp {{ row.expirySummary }}</div>
                <div class="dpm-path-row-sub">Lado {{ row.sideSummary }}</div>
              </div>
            </div>

            <div class="dpm-path-side">
              <div class="dpm-path-side-title up">Upside</div>
              <div
                v-for="row in pricePathUpRows"
                :key="row.key"
                class="dpm-path-row"
                :class="row.actionClass"
              >
                <div class="dpm-path-row-top">
                  <span class="dpm-path-step">{{ row.stepLabel }}</span>
                  <span class="dpm-path-range">{{ row.rangeLabel }}</span>
                </div>
                <div class="dpm-path-row-main">
                  <span class="dpm-path-action" :class="row.actionClass">{{ row.actionLabel }} {{ formatAbsoluteContracts(row.incrementalWin) }} WIN</span>
                  <span>Acum {{ formatSignedContracts(row.cumulativeWin) }}</span>
                  <span>Γ/100 {{ formatSignedContracts(row.gammaHedgeWinPer100) }}</span>
                </div>
                <div class="dpm-path-row-sub">Exp {{ row.expirySummary }}</div>
                <div class="dpm-path-row-sub">Lado {{ row.sideSummary }}</div>
              </div>
            </div>
          </div>

          <div class="dpm-hedge-reference-row">
            <span class="dpm-chip">Spot {{ formatLevel(spot) }}</span>
            <span v-if="referenceFuturePrice != null" class="dpm-chip">Fut ref {{ formatLevel(referenceFuturePrice) }}</span>
            <span class="dpm-chip">Janela max {{ STRIKE_HEDGE_MAX_POINTS }}pts</span>
          </div>

          <div class="dpm-strike-map">
            <div
              v-for="row in strikeHedgeMapRows"
              :key="`strike-map-${row.strike}`"
              class="dpm-strike-row"
              :class="{ focus: row.isReferenceAnchor }"
            >
              <div class="dpm-strike-row-head">
                <div class="dpm-strike-row-title">
                  <span class="dpm-strike-row-price">{{ formatLevel(row.futureStrike) }}</span>
                  <span v-if="row.isReferenceAnchor" class="dpm-mini-tag ref">Fut</span>
                  <span v-if="row.isSpotAnchor" class="dpm-mini-tag spot">Spot</span>
                </div>
                <div class="dpm-strike-row-meta">
                  <span>Passo {{ row.stepPoints }}pts</span>
                  <span>GEX {{ formatSignedContracts(row.netGex) }}</span>
                  <span>Alta {{ row.upAction }} {{ row.upStepRangeLabel }} WIN</span>
                  <span>Queda {{ row.downAction }} {{ row.downStepRangeLabel }} WIN</span>
                </div>
              </div>

              <div class="dpm-strike-ladder">
                <div class="dpm-strike-side down">
                  <div
                    v-for="segment in row.downSegments"
                    :key="segment.key"
                    class="dpm-strike-cell"
                    :class="segment.tone"
                  >
                    <span class="dpm-strike-cell-step">{{ segment.label }}</span>
                    <strong>{{ formatAbsoluteContracts(segment.contracts) }}</strong>
                    <span>{{ segment.actionLabel }}</span>
                  </div>
                </div>

                <div class="dpm-strike-anchor" :class="{ ref: row.isReferenceAnchor, spot: row.isSpotAnchor }">
                  <span class="dpm-strike-anchor-price">{{ formatLevel(row.futureStrike) }}</span>
                  <span class="dpm-strike-anchor-sub">{{ row.windowLabel }}</span>
                  <span class="dpm-strike-anchor-sub">{{ formatPct(row.distancePct) }} da ref</span>
                </div>

                <div class="dpm-strike-side up">
                  <div
                    v-for="segment in row.upSegments"
                    :key="segment.key"
                    class="dpm-strike-cell"
                    :class="segment.tone"
                  >
                    <span class="dpm-strike-cell-step">{{ segment.label }}</span>
                    <strong>{{ formatAbsoluteContracts(segment.contracts) }}</strong>
                    <span>{{ segment.actionLabel }}</span>
                  </div>
                </div>
              </div>

              <div class="dpm-strike-expiry-list">
                <div
                  v-for="expiry in row.expiryLadders"
                  :key="`${row.strike}-${expiry.expiry}`"
                  class="dpm-strike-expiry-pill"
                  :class="expiry.upTone"
                >
                  <span>V {{ shortDateLabel(expiry.expiry) }}</span>
                  <span>{{ expiry.upAction }} {{ expiry.stepRangeLabel }}/passo</span>
                  <span>Total {{ formatAbsoluteContracts(expiry.totalContracts) }}</span>
                  <span>OI {{ compactNumber(expiry.totalOi) }}</span>
                </div>
                <div v-if="!row.expiryLadders.length" class="dpm-strike-expiry-pill muted">
                  Sem vencimentos dominantes nesse strike.
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="false" class="dpm-card">
          <div class="dpm-section-title">Bandas de hedge</div>
          <table class="dpm-table dpm-band-table">
            <thead>
              <tr>
                <th>Faixa</th>
                <th>Call</th>
                <th>Put</th>
                <th>Net</th>
                <th>Γ / 100pts</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="band in hedgeBands" :key="band.key">
                <td>
                  <div>{{ band.label }}</div>
                  <div class="dpm-table-sub">{{ band.strikeRange }}</div>
                </td>
                <td>{{ formatSignedContracts(band.callHedgeWin) }}</td>
                <td>{{ formatSignedContracts(band.putHedgeWin) }}</td>
                <td>{{ formatSignedContracts(band.netHedgeWin) }}</td>
                <td>
                  <div>{{ formatSignedContracts(band.gammaHedgeWinPer100) }}</div>
                  <div class="dpm-table-sub">{{ band.expirySummary }}</div>
                </td>
              </tr>
              <tr v-if="!hedgeBands.length">
                <td colspan="5">Sem bandas calculadas ainda.</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="false" class="dpm-card">
          <div class="dpm-section-title">Strikes por composicao</div>
          <table class="dpm-table">
            <thead>
              <tr>
                <th>Strike fut</th>
                <th>Hedge net</th>
                <th>Γ / 100pts</th>
                <th>Expiries dominantes</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in topCriticalStrikes" :key="`critical-${row.strike}`">
                <td>
                  <div>{{ formatLevel(row.futureStrike) }}</div>
                  <div class="dpm-table-sub">{{ row.profile?.gammaTrend }} | {{ formatPct(row.distancePct) }}</div>
                </td>
                <td>
                  <div>{{ formatSignedContracts(row.profile?.netHedgeWin) }}</div>
                  <div class="dpm-table-sub">C {{ formatSignedContracts(row.profile?.callHedgeWin) }} | P {{ formatSignedContracts(row.profile?.putHedgeWin) }}</div>
                </td>
                <td>
                  <div>{{ formatSignedContracts(row.profile?.gammaHedgeWinPer100) }}</div>
                  <div class="dpm-table-sub">slope {{ compactNumber(row.profile?.gexSlope) }}</div>
                </td>
                <td>{{ row.expirySummary }}</td>
              </tr>
              <tr v-if="!topCriticalStrikes.length">
                <td colspan="4">Sem strikes criticos proximos da referencia.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="dpm-card dpm-composition-card">
        <div class="dpm-section-title">Strikes por composicao</div>
        <table class="dpm-table">
          <thead>
            <tr>
              <th>Strike fut</th>
              <th>OI C / P</th>
              <th>Hedge / passo</th>
              <th>Vencimentos dominantes</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in nearStrikeCompositionRows" :key="`composition-${row.key}`">
              <td>
                <div>{{ formatLevel(row.futureStrike) }}</div>
                <div class="dpm-table-sub">{{ formatPct(row.distancePct) }} da ref</div>
              </td>
              <td>
                <div>C {{ compactNumber(row.callOi) }} | P {{ compactNumber(row.putOi) }}</div>
                <div class="dpm-table-sub">Total {{ compactNumber(row.totalOi) }}</div>
              </td>
              <td>
                <div>{{ row.upAction }} {{ row.stepRangeLabel }} WIN</div>
                <div class="dpm-table-sub">passo {{ row.stepPoints }}pts</div>
              </td>
              <td>{{ row.expirySummary }}</td>
            </tr>
            <tr v-if="!nearStrikeCompositionRows.length">
              <td colspan="4">Sem strikes criticos proximos da referencia.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="false" class="dpm-lower-grid">
        <div class="dpm-card">
          <div class="dpm-section-title">Top 3 pain zones</div>
          <table class="dpm-table">
            <thead>
              <tr>
                <th>Regiao</th>
                <th>Pain</th>
                <th>Causa</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="zone in topZones" :key="zone.key">
                <td>{{ zoneRangeLabel(zone) }}</td>
                <td>{{ formatScore(zone.peakScore) }}</td>
                <td>{{ zoneCauseLabel(zone) }}</td>
              </tr>
              <tr v-if="!topZones.length">
                <td colspan="3">Nenhuma zona critica formada ainda.</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="dpm-card">
          <div class="dpm-section-title">Alertas</div>
          <div class="dpm-alert-list">
            <div v-for="alert in alerts" :key="alert.key" class="dpm-alert" :class="alert.tone">
              <span class="dpm-alert-tag">{{ alert.tag }}</span>
              <span>{{ alert.message }}</span>
            </div>
            <div v-if="!alerts.length" class="dpm-alert calm">
              <span class="dpm-alert-tag">OK</span>
              <span>Sem gatilhos de dor reflexiva no momento.</span>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { getLatestOptionsModel, getVolumeActivity } from '@/api/options'

const HEAT_W = 920
const HEAT_H = 220
const PAD = { top: 20, right: 26, bottom: 36, left: 56 }
const LADDER_W = 920
const LADDER_H = 392
const LADDER_PAD = { top: 20, right: 96, bottom: 30, left: 86 }
const HEAT_REFRESH_MS = 60_000
const HISTORY_PREFIX = 'discovery:dealer-pain'
const HISTORY_VERSION = 1
const SCORE_WINDOW_MS = 15 * 60 * 1000
const SCORE_TTL_MS = 18 * 60 * 60 * 1000
const MAX_HISTORY_ROWS = 300
const ZONE_MIN_SCORE = 58
const SCORE_TICKS = [0, 25, 50, 75, 100]
const HEDGE_BANDS = [
  { key: 'near', label: '0-0.35%', low: 0.0, high: 0.0035 },
  { key: 'active', label: '0.35-0.75%', low: 0.0035, high: 0.0075 },
  { key: 'stretch', label: '0.75-1.50%', low: 0.0075, high: 0.015 },
]
const PRICE_PATH_STEP_POINTS = 100
const PRICE_PATH_BUCKETS = 4
const STRIKE_HEDGE_MAX_POINTS = 500
const STRIKE_HEDGE_MAX_STEPS = 5
const STRIKE_HEDGE_ROW_LIMIT = 14

const COMPONENT_WEIGHTS = {
  hedgeAcceleration: 0.17,
  dexAbs: 0.13,
  gexChange: 0.12,
  vannaRisk: 0.11,
  charmRisk: 0.08,
  liquidityGap: 0.12,
  ivStress: 0.09,
  gammaCliffProximity: 0.10,
  airPocket: 0.08,
}

const COMPONENT_LABELS = {
  hedgeAcceleration: 'Aceleracao de hedge',
  dexAbs: 'DEX absoluto',
  gexChange: 'Mudanca de GEX',
  vannaRisk: 'Vanna risk',
  charmRisk: 'Charm risk',
  liquidityGap: 'Gap de liquidez',
  ivStress: 'Stress de IV',
  gammaCliffProximity: 'Gamma cliff',
  airPocket: 'Air pocket',
}

const props = defineProps({
  modelData: { type: Object, default: null },
  rawModelData: { type: Object, default: null },
  underlyingSecurity: { type: String, default: 'IBOVE Index' },
  refreshNonce: { type: Number, default: 0 },
})

const rootEl = ref(null)
const heatWrap = ref(null)
const hoverIndex = ref(null)
const fallbackRawModelData = ref(null)
const fallbackModelData = ref(null)
const loadingModel = ref(false)
const modelError = ref('')
const rawFlowEvents = ref([])
const flowLoaded = ref(false)
const flowError = ref('')
const scoreHistory = ref([])

let loadTimer = null
let modelTimer = null
let lastFlowLoadAt = 0
let lastModelLoadAt = 0

function clamp(value, low, high) {
  return Math.max(low, Math.min(high, Number(value)))
}

function safeNumber(value) {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

function firstNumber(...values) {
  for (const value of values) {
    const numeric = safeNumber(value)
    if (numeric != null) return numeric
  }
  return null
}

function compactNumber(value) {
  const numeric = safeNumber(value)
  if (numeric == null) return '--'
  const abs = Math.abs(numeric)
  if (abs >= 1_000_000) return `${numeric >= 0 ? '' : '-'}${(abs / 1_000_000).toFixed(2)}M`
  if (abs >= 1_000) return `${numeric >= 0 ? '' : '-'}${(abs / 1_000).toFixed(1)}k`
  return numeric.toFixed(0)
}

function normalizeExposureBreakdown(source) {
  if (!source || typeof source !== 'object') return {}

  if (Array.isArray(source)) {
    return source.reduce((acc, item) => {
      const key = String(item?.key || item?.expiry || item?.put_call || item?.label || '').trim()
      if (!key) return acc
      acc[key] = {
        dex: safeNumber(item?.dex) || 0,
        gex: safeNumber(item?.gex) || 0,
        vex: safeNumber(item?.vex) || 0,
        cex: safeNumber(item?.cex) || 0,
      }
      return acc
    }, {})
  }

  return Object.entries(source).reduce((acc, [key, item]) => {
    const label = String(key || '').trim()
    if (!label) return acc
    acc[label] = {
      dex: safeNumber(item?.dex) || 0,
      gex: safeNumber(item?.gex) || 0,
      vex: safeNumber(item?.vex) || 0,
      cex: safeNumber(item?.cex) || 0,
    }
    return acc
  }, {})
}

function blendExposureBreakdown(left, right, ratio) {
  const merged = {}
  const keys = new Set([
    ...Object.keys(left || {}),
    ...Object.keys(right || {}),
  ])

  for (const key of keys) {
    const leftRow = left?.[key] || {}
    const rightRow = right?.[key] || {}
    merged[key] = {
      dex: ((safeNumber(leftRow.dex) || 0) * (1 - ratio)) + ((safeNumber(rightRow.dex) || 0) * ratio),
      gex: ((safeNumber(leftRow.gex) || 0) * (1 - ratio)) + ((safeNumber(rightRow.gex) || 0) * ratio),
      vex: ((safeNumber(leftRow.vex) || 0) * (1 - ratio)) + ((safeNumber(rightRow.vex) || 0) * ratio),
      cex: ((safeNumber(leftRow.cex) || 0) * (1 - ratio)) + ((safeNumber(rightRow.cex) || 0) * ratio),
    }
  }

  return merged
}

function diffExposureBreakdown(target, base) {
  const diff = {}
  const keys = new Set([
    ...Object.keys(target || {}),
    ...Object.keys(base || {}),
  ])

  for (const key of keys) {
    const targetRow = target?.[key] || {}
    const baseRow = base?.[key] || {}
    diff[key] = {
      dex: (safeNumber(targetRow.dex) || 0) - (safeNumber(baseRow.dex) || 0),
      gex: (safeNumber(targetRow.gex) || 0) - (safeNumber(baseRow.gex) || 0),
      vex: (safeNumber(targetRow.vex) || 0) - (safeNumber(baseRow.vex) || 0),
      cex: (safeNumber(targetRow.cex) || 0) - (safeNumber(baseRow.cex) || 0),
    }
  }

  return diff
}

function rankedBreakdownRows(source, field, scale, limit = 3) {
  return Object.entries(source || {})
    .map(([key, row]) => {
      const exposure = safeNumber(row?.[field]) || 0
      return {
        key,
        exposure,
        contracts: exposure / Math.max(scale, 1e-9),
      }
    })
    .filter(row => Math.abs(row.exposure) > 1e-6)
    .sort((left, right) => Math.abs(right.exposure) - Math.abs(left.exposure))
    .slice(0, limit)
}

function ordinalBucketLabel(index) {
  const numeric = Math.max(1, Math.round(index || 0))
  return `${numeric}o 100pts`
}

function mean(values) {
  if (!values.length) return 0
  return values.reduce((sum, item) => sum + item, 0) / values.length
}

function quantile(values, q) {
  const finite = [...values].filter(value => Number.isFinite(value)).sort((left, right) => left - right)
  if (!finite.length) return 0
  if (finite.length === 1) return finite[0]
  const index = clamp(q, 0, 1) * (finite.length - 1)
  const low = Math.floor(index)
  const high = Math.ceil(index)
  if (low === high) return finite[low]
  const ratio = index - low
  return finite[low] + ((finite[high] - finite[low]) * ratio)
}

function normalizeFlowEvent(event) {
  const normalized = { ...(event || {}) }
  normalized._strike = safeNumber(normalized.strike)
  normalized._volume = Math.max(safeNumber(normalized.volume_delta) || 0, 0)
  normalized._side = String(normalized.put_call || '').toUpperCase() === 'P' ? 'P' : 'C'
  normalized._days = safeNumber(normalized.days_to_maturity)
  normalized._epoch = normalized.captured_at ? new Date(normalized.captured_at).getTime() : null
  normalized._spot = safeNumber(normalized.spot_price)
  return normalized
}

function historyKey(underlying) {
  return `${HISTORY_PREFIX}:${String(underlying || '').trim() || 'unknown'}`
}

function readHistoryCache(underlying) {
  try {
    if (typeof window === 'undefined' || !window.localStorage) return []
    const raw = window.localStorage.getItem(historyKey(underlying))
    if (!raw) return []
    const payload = JSON.parse(raw)
    if (payload?.version !== HISTORY_VERSION || !Array.isArray(payload.rows)) return []
    const now = Date.now()
    return payload.rows
      .filter(item => item && Number.isFinite(item.ts) && (now - item.ts) <= SCORE_TTL_MS)
      .slice(-MAX_HISTORY_ROWS)
  } catch {
    return []
  }
}

function writeHistoryCache(underlying, rows) {
  try {
    if (typeof window === 'undefined' || !window.localStorage) return
    window.localStorage.setItem(historyKey(underlying), JSON.stringify({
      version: HISTORY_VERSION,
      rows,
    }))
  } catch {
    // noop
  }
}

const underlyingLabel = computed(() => {
  if (props.underlyingSecurity === 'IBOVE Index') return 'IBOV'
  if (props.underlyingSecurity === 'IBOVB3 Index') return 'IBOVB3'
  return String(props.underlyingSecurity || '').replace(' Index', '')
})

function hasUsableModelPayload(model) {
  const byStrikeRows = model?.aggregates?.by_strike
  const curveRows = model?.pressure?.curve
  const spotValue = safeNumber(model?.market_context?.spot_price ?? model?.pressure?.current_point?.spot)
  return Array.isArray(byStrikeRows) && byStrikeRows.length >= 10
    && Array.isArray(curveRows) && curveRows.length >= 9
    && spotValue != null
}

function hasUsableRawModelPayload(model) {
  const payload = model?.data ?? model
  const strikeProfiles = payload?.strike_profiles
  const curveRows = payload?.pressure?.curve
  const spotValue = safeNumber(payload?.market_context?.spot_price ?? payload?.pressure?.current_point?.spot)
  return Array.isArray(strikeProfiles) && strikeProfiles.length >= 10
    && Array.isArray(curveRows) && curveRows.length >= 9
    && spotValue != null
}

function normalizeStandaloneModel(rawPayload) {
  const payload = rawPayload?.data ?? rawPayload
  if (!payload || typeof payload !== 'object') return null

  const strikeProfiles = Array.isArray(payload.strike_profiles) ? payload.strike_profiles : []
  const pressureCurveRows = Array.isArray(payload?.pressure?.curve) ? payload.pressure.curve : []

  const normalizedByStrike = strikeProfiles
    .map(row => {
      const ivCall = safeNumber(row?.iv_call)
      const ivPut = safeNumber(row?.iv_put)
      return {
        strike: firstNumber(row?.strike) || 0,
        gex: firstNumber(row?.gex, row?.gex_net, row?.gamma_exposure_net) || 0,
        dex: firstNumber(row?.dex, row?.dex_net, row?.delta_exposure_net) || 0,
        vex: firstNumber(row?.vex, row?.vanna, row?.vanna_net) || 0,
        cex: firstNumber(row?.cex, row?.charm, row?.charm_net) || 0,
        gex_call: firstNumber(row?.gex_call) || 0,
        gex_put: firstNumber(row?.gex_put) || 0,
        dex_call: firstNumber(row?.dex_call) || 0,
        dex_put: firstNumber(row?.dex_put) || 0,
        vex_call: firstNumber(row?.vex_call, row?.vanna_call) || 0,
        vex_put: firstNumber(row?.vex_put, row?.vanna_put) || 0,
        cex_call: firstNumber(row?.cex_call, row?.charm_call) || 0,
        cex_put: firstNumber(row?.cex_put, row?.charm_put) || 0,
        call_oi: firstNumber(row?.call_oi, row?.open_interest_call) || 0,
        put_oi: firstNumber(row?.put_oi, row?.open_interest_put) || 0,
        open_interest_total: firstNumber(
          row?.open_interest_total,
          (firstNumber(row?.call_oi, row?.open_interest_call) || 0) + (firstNumber(row?.put_oi, row?.open_interest_put) || 0),
          0,
        ),
        iv_call: ivCall,
        iv_put: ivPut,
        iv_mid: firstNumber(
          row?.iv_mid,
          row?.iv,
          ivCall != null && ivPut != null ? ((ivCall + ivPut) / 2) : null,
          ivCall,
          ivPut,
        ),
      }
    })
    .filter(row => row.strike > 0)

  const normalizedCurve = pressureCurveRows
    .map(row => {
      const price = firstNumber(row?.spot, row?.strike)
      return {
        strike: price,
        spot: price,
        dex: firstNumber(row?.dex) || 0,
        gex: firstNumber(row?.gex, row?.gex_score) || 0,
        gex_score: firstNumber(row?.gex_score, row?.gex) || 0,
        vex: firstNumber(row?.vex, row?.vanna, row?.vanna_net) || 0,
        cex: firstNumber(row?.cex, row?.charm, row?.charm_net) || 0,
        hp: firstNumber(row?.hp, row?.net_pressure) || 0,
        net_pressure: firstNumber(row?.net_pressure, row?.hp) || 0,
        by_put_call: row?.by_put_call || {},
        by_expiry: row?.by_expiry || {},
      }
    })
    .filter(row => row.spot != null && row.spot > 0)

  return {
    captured_at: payload?.captured_at ?? null,
    market_context: payload?.market_context ?? {},
    pressure: {
      ...(payload?.pressure ?? {}),
      current_point: payload?.pressure?.current_point ?? {
        spot: payload?.market_context?.spot_price ?? null,
      },
      curve: normalizedCurve,
    },
    aggregates: {
      by_strike: normalizedByStrike,
    },
  }
}

const effectiveModelData = computed(() => {
  if (hasUsableModelPayload(props.modelData)) return props.modelData
  if (hasUsableModelPayload(fallbackModelData.value)) return fallbackModelData.value
  return null
})

const effectiveRawModelData = computed(() => {
  if (hasUsableRawModelPayload(props.rawModelData)) return props.rawModelData?.data ?? props.rawModelData
  if (hasUsableRawModelPayload(fallbackRawModelData.value)) return fallbackRawModelData.value?.data ?? fallbackRawModelData.value
  return null
})

const winPointValue = computed(() => firstNumber(effectiveRawModelData.value?.config?.win_point_value, 0.2) || 0.2)
const basisPoints = computed(() => firstNumber(
  effectiveRawModelData.value?.market_context?.future_basis_points,
  effectiveRawModelData.value?.summary?.future_basis_points,
  0,
) || 0)
const forwardPrice = computed(() => firstNumber(
  effectiveRawModelData.value?.market_context?.forward_price,
  effectiveRawModelData.value?.summary?.forward_price,
))
const dealerComparison = computed(() => (
  effectiveRawModelData.value?.dealer_inference?.comparison
  || effectiveRawModelData.value?.summary?.dealer_inference_comparison
  || {}
))

const byStrike = computed(() => {
  const rows = effectiveModelData.value?.aggregates?.by_strike ?? []
  return [...rows]
    .map(row => ({
      strike: safeNumber(row?.strike) || 0,
      gex: safeNumber(row?.gex) || 0,
      dex: safeNumber(row?.dex) || 0,
      vex: safeNumber(row?.vex) || 0,
      cex: safeNumber(row?.cex) || 0,
      callOi: safeNumber(row?.call_oi) || 0,
      putOi: safeNumber(row?.put_oi) || 0,
      ivMid: safeNumber(row?.iv_mid ?? row?.iv_call ?? row?.iv_put),
    }))
    .filter(row => row.strike > 0)
    .sort((left, right) => left.strike - right.strike)
})

const pressureCurve = computed(() => {
  const rawRows = effectiveRawModelData.value?.pressure?.curve
  const normalizedRows = effectiveModelData.value?.pressure?.curve
  const rows = Array.isArray(rawRows) && rawRows.length ? rawRows : (normalizedRows ?? [])
  return [...rows]
    .map((row, index) => ({
      index,
      price: safeNumber(row?.strike ?? row?.spot) || 0,
      dex: safeNumber(row?.dex) || 0,
      gex: safeNumber(row?.gex_score ?? row?.gex) || 0,
      vex: safeNumber(row?.vex) || 0,
      cex: safeNumber(row?.cex) || 0,
      hp: safeNumber(row?.net_pressure ?? row?.hp) || 0,
      byExpiry: normalizeExposureBreakdown(row?.by_expiry),
      byPutCall: normalizeExposureBreakdown(row?.by_put_call),
    }))
    .filter(row => row.price > 0)
    .sort((left, right) => left.price - right.price)
})

const spot = computed(() => safeNumber(
  effectiveModelData.value?.market_context?.spot_price
  ?? effectiveModelData.value?.pressure?.current_point?.spot,
))

const atmIv = computed(() => {
  const base = safeNumber(effectiveModelData.value?.market_context?.implied_vol)
  if (base != null) return base
  if (!spot.value || !byStrike.value.length) return null
  return nearestStrikeRow(spot.value)?.ivMid ?? null
})

const daysToExpiry = computed(() => {
  const numeric = safeNumber(effectiveModelData.value?.market_context?.days_to_expiry)
  if (numeric != null && numeric > 0) return numeric
  return 21
})

const referenceFuturePrice = computed(() => firstNumber(
  dealerComparison.value?.reference_dealer_inference_future_value,
  forwardPrice.value,
  spot.value != null ? spot.value + basisPoints.value : null,
))

const referenceSpotPrice = computed(() => firstNumber(
  dealerComparison.value?.reference_dealer_inference_value,
  referenceFuturePrice.value != null ? referenceFuturePrice.value - basisPoints.value : null,
  spot.value,
))

const referenceConfidence = computed(() => clamp((firstNumber(dealerComparison.value?.reference_confidence, 0) || 0) * 100, 0, 100))

const strikeProfilesRaw = computed(() => {
  const rows = Array.isArray(effectiveRawModelData.value?.strike_profiles)
    ? effectiveRawModelData.value.strike_profiles
    : []

  const baseRows = rows
    .map(row => {
      const strike = firstNumber(row?.strike) || 0
      const callOi = firstNumber(row?.open_interest_call) || 0
      const putOi = firstNumber(row?.open_interest_put) || 0
      const totalOi = firstNumber(row?.open_interest_total, callOi + putOi) || 0
      const gexCall = firstNumber(row?.gex_call) || 0
      const gexPut = firstNumber(row?.gex_put) || 0
      const gexNet = firstNumber(row?.gex_net, row?.gex) || 0
      const dexCall = firstNumber(row?.dex_call) || 0
      const dexPut = firstNumber(row?.dex_put) || 0
      const dexNet = firstNumber(row?.dex_net, row?.dex) || 0
      const vexNet = firstNumber(row?.vex_net, row?.vex) || 0
      const cexNet = firstNumber(row?.cex_net, row?.cex) || 0
      return {
        strike,
        futureStrike: strike + basisPoints.value,
        callOi,
        putOi,
        totalOi,
        gexCall,
        gexPut,
        gexNet,
        dexCall,
        dexPut,
        dexNet,
        vexNet,
        cexNet,
        callHedgeWin: dexCall / Math.max(winPointValue.value, 1e-9),
        putHedgeWin: dexPut / Math.max(winPointValue.value, 1e-9),
        netHedgeWin: dexNet / Math.max(winPointValue.value, 1e-9),
        gammaHedgeWinPer100: (gexNet * 100) / Math.max(winPointValue.value, 1e-9),
        gammaCallWinPer100: (gexCall * 100) / Math.max(winPointValue.value, 1e-9),
        gammaPutWinPer100: (gexPut * 100) / Math.max(winPointValue.value, 1e-9),
        distancePctToReference: referenceFuturePrice.value > 0
          ? Math.abs((strike + basisPoints.value) - referenceFuturePrice.value) / referenceFuturePrice.value
          : 0,
      }
    })
    .filter(row => row.strike > 0)
    .sort((left, right) => left.strike - right.strike)

  return baseRows.map((row, index) => {
    const prev = baseRows[Math.max(index - 1, 0)] || row
    const next = baseRows[Math.min(index + 1, baseRows.length - 1)] || row
    const span = Math.max(next.strike - prev.strike, 1)
    const gexSlope = (next.gexNet - prev.gexNet) / span
    const absGexSlope = (Math.abs(next.gexNet) - Math.abs(prev.gexNet)) / span
    const gexCurvature = next.gexNet - (2 * row.gexNet) + prev.gexNet
    return {
      ...row,
      gexSlope,
      absGexSlope,
      gexCurvature,
      gammaTrend: absGexSlope >= 0 ? 'cresce' : 'some',
    }
  })
})

const surfaceExposureRows = computed(() => {
  const compactRows = Array.isArray(effectiveRawModelData.value?.gex_surface_points)
    ? effectiveRawModelData.value.gex_surface_points
    : []

  if (compactRows.length) {
    return compactRows
      .map(row => ({
        strike: firstNumber(row?.strike) || 0,
        futureStrike: (firstNumber(row?.strike) || 0) + basisPoints.value,
        expiry: String(row?.expiry || ''),
        dte: firstNumber(row?.dte) || 0,
        putCall: String(row?.put_call || 'Call'),
        oi: firstNumber(row?.oi) || 0,
        gex: firstNumber(row?.gex) || 0,
        dex: firstNumber(row?.dex) || 0,
      }))
      .filter(row => row.strike > 0 && row.expiry)
  }

  const exposureRows = Array.isArray(effectiveRawModelData.value?.option_exposures)
    ? effectiveRawModelData.value.option_exposures
    : []

  return exposureRows
    .map(row => {
      const option = row?.option || {}
      const strike = firstNumber(option?.strike) || 0
      return {
        strike,
        futureStrike: strike + basisPoints.value,
        expiry: String(option?.expiry_date || ''),
        dte: firstNumber(option?.days_to_expiry_business) || 0,
        putCall: String(option?.put_call || 'Call'),
        oi: firstNumber(option?.open_int) || 0,
        gex: firstNumber(row?.gex) || 0,
        dex: firstNumber(row?.dex) || 0,
      }
    })
    .filter(row => row.strike > 0 && row.expiry)
})

const strikeCompositionRows = computed(() => {
  const grouped = new Map()
  const profileMap = new Map(strikeProfilesRaw.value.map(row => [row.strike, row]))

  for (const row of surfaceExposureRows.value) {
    if (!grouped.has(row.strike)) {
      grouped.set(row.strike, {
        strike: row.strike,
        futureStrike: row.futureStrike,
        expiryMap: new Map(),
      })
    }
    const strikeBucket = grouped.get(row.strike)
    const expiryKey = row.expiry
    if (!strikeBucket.expiryMap.has(expiryKey)) {
      strikeBucket.expiryMap.set(expiryKey, {
        expiry: expiryKey,
        dte: row.dte,
        callOi: 0,
        putOi: 0,
        totalOi: 0,
        callGex: 0,
        putGex: 0,
        netGex: 0,
        callDex: 0,
        putDex: 0,
        netDex: 0,
      })
    }
    const expiryBucket = strikeBucket.expiryMap.get(expiryKey)
    expiryBucket.totalOi += row.oi
    expiryBucket.netGex += row.gex
    expiryBucket.netDex += row.dex
    if (String(row.putCall).toLowerCase() === 'put') {
      expiryBucket.putOi += row.oi
      expiryBucket.putGex += row.gex
      expiryBucket.putDex += row.dex
    } else {
      expiryBucket.callOi += row.oi
      expiryBucket.callGex += row.gex
      expiryBucket.callDex += row.dex
    }
  }

  for (const profile of strikeProfilesRaw.value) {
    if (!grouped.has(profile.strike)) {
      grouped.set(profile.strike, {
        strike: profile.strike,
        futureStrike: profile.futureStrike,
        expiryMap: new Map(),
      })
    }
  }

  return [...grouped.values()]
    .map(entry => {
      const profile = profileMap.get(entry.strike) || null
      const expiryRows = [...entry.expiryMap.values()]
        .sort((left, right) => {
          const leftScore = Math.abs(left.netGex) + Math.abs(left.netDex) + left.totalOi
          const rightScore = Math.abs(right.netGex) + Math.abs(right.netDex) + right.totalOi
          return rightScore - leftScore
        })
      const distancePct = referenceFuturePrice.value > 0
        ? Math.abs(entry.futureStrike - referenceFuturePrice.value) / referenceFuturePrice.value
        : 0
      return {
        strike: entry.strike,
        futureStrike: entry.futureStrike,
        distancePct,
        profile,
        expiryRows,
      }
    })
    .sort((left, right) => {
      const leftGex = Math.abs(left.profile?.gexNet || 0)
      const rightGex = Math.abs(right.profile?.gexNet || 0)
      if (rightGex !== leftGex) return rightGex - leftGex
      return left.distancePct - right.distancePct
    })
})

function summarizeExpiryRows(rows, limit = 2) {
  const slice = (rows || []).slice(0, limit)
  if (!slice.length) return '--'
  return slice.map(row => `${shortDateLabel(row.expiry)} C${compactNumber(row.callOi)} P${compactNumber(row.putOi)}`).join(' · ')
}

function aggregateExpiryRows(strikeRows) {
  const grouped = new Map()
  for (const row of strikeRows || []) {
    for (const expiry of row.expiryRows || []) {
      const current = grouped.get(expiry.expiry) || {
        expiry: expiry.expiry,
        dte: expiry.dte,
        callOi: 0,
        putOi: 0,
        totalOi: 0,
        netGex: 0,
        netDex: 0,
      }
      current.callOi += expiry.callOi
      current.putOi += expiry.putOi
      current.totalOi += expiry.totalOi
      current.netGex += expiry.netGex
      current.netDex += expiry.netDex
      grouped.set(expiry.expiry, current)
    }
  }
  return [...grouped.values()].sort((left, right) => {
    const leftScore = Math.abs(left.netGex) + Math.abs(left.netDex) + left.totalOi
    const rightScore = Math.abs(right.netGex) + Math.abs(right.netDex) + right.totalOi
    return rightScore - leftScore
  })
}

const topCriticalStrikes = computed(() => {
  const rows = strikeCompositionRows.value.filter(row => row.profile && row.distancePct <= 0.03)
  const source = rows.length ? rows : strikeCompositionRows.value.filter(row => row.profile)
  return [...source]
    .sort((left, right) => {
      const leftScore = Math.abs(left.profile?.gexNet || 0) + (Math.abs(left.profile?.dexNet || 0) * 0.2)
      const rightScore = Math.abs(right.profile?.gexNet || 0) + (Math.abs(right.profile?.dexNet || 0) * 0.2)
      if (rightScore !== leftScore) return rightScore - leftScore
      return left.distancePct - right.distancePct
    })
    .slice(0, 4)
    .map(row => ({
      ...row,
      expirySummary: summarizeExpiryRows(row.expiryRows, 2),
    }))
})

function hedgeToneForDirection(gexValue, direction) {
  const gammaPositive = (safeNumber(gexValue) || 0) >= 0
  if (direction === 'up') return gammaPositive ? 'sell' : 'buy'
  return gammaPositive ? 'buy' : 'sell'
}

function hedgeActionLabel(gexValue, direction) {
  return hedgeToneForDirection(gexValue, direction) === 'sell' ? 'Vender' : 'Comprar'
}

function buildHedgeStepWeights({
  gammaValue,
  stepCount,
  localIv,
  baseIv,
  dte,
  slopeRatio = 0,
  curvatureRatio = 0,
}) {
  const safeCount = Math.max(1, Math.round(stepCount || 1))
  const ivReference = Math.max(baseIv || localIv || 0.2, 0.05)
  const ivRatio = clamp((localIv || ivReference) / ivReference, 0.55, 1.65)
  const dteRatio = clamp(21 / Math.max(dte || daysToExpiry.value || 21, 1), 0.45, 2.2)
  const power = clamp(
    1.05
    + (curvatureRatio * 0.70)
    + (slopeRatio * 0.35)
    + ((dteRatio - 1) * 0.20)
    - ((ivRatio - 1) * 0.35),
    0.7,
    2.4,
  )
  const gammaPositive = (safeNumber(gammaValue) || 0) >= 0
  const raw = Array.from({ length: safeCount }, (_, index) => {
    const rank = gammaPositive ? (safeCount - index) : (index + 1)
    return Math.max(rank ** power, 1e-6)
  })
  const total = raw.reduce((sum, value) => sum + value, 0) || 1
  return raw.map(value => value / total)
}

function buildHedgeSegments({
  strikeKey,
  direction,
  stepCount,
  stepPoints,
  totalContractsAbs,
  gammaValue,
  localIv,
  baseIv,
  dte,
  slopeRatio = 0,
  curvatureRatio = 0,
  actionLabel,
  tone,
}) {
  const weights = buildHedgeStepWeights({
    gammaValue,
    stepCount,
    localIv,
    baseIv,
    dte,
    slopeRatio,
    curvatureRatio,
  })
  const segments = weights.map((weight, index) => ({
    key: `${strikeKey}-${direction}-${index + 1}`,
    tone,
    actionLabel,
    contracts: totalContractsAbs * weight,
    weight,
    label: `${direction === 'up' ? '+' : '-'}${(index + 1) * stepPoints}`,
  }))
  return {
    segments,
    firstContractsAbs: segments[0]?.contracts || 0,
    lastContractsAbs: segments[segments.length - 1]?.contracts || 0,
  }
}

const strikeHedgeMapRows = computed(() => {
  if (!referenceFuturePrice.value || !strikeCompositionRows.value.length) return []
  const candidates = strikeCompositionRows.value
    .filter(row => row.profile && row.expiryRows?.length)
    .map(row => ({
      ...row,
      futureDistance: Math.abs((row.futureStrike || 0) - referenceFuturePrice.value),
    }))
    .sort((left, right) => left.futureDistance - right.futureDistance)
    .slice(0, STRIKE_HEDGE_ROW_LIMIT)

  if (!candidates.length) return []

  const scale = Math.max(winPointValue.value, 1e-9)
  const maxAbsGex = Math.max(...candidates.map(row => Math.abs(row.profile?.gexNet || 0)), 1)
  const maxAbsSlope = Math.max(...candidates.map(row => Math.abs(row.profile?.gexSlope || 0)), 1)
  const maxAbsCurvature = Math.max(...candidates.map(row => Math.abs(row.profile?.gexCurvature || 0)), 1)
  const futureSpotReference = referenceFuturePrice.value
  const spotFutureReference = spot.value != null ? spot.value + basisPoints.value : null
  const nearestFutureDistance = Math.min(...candidates.map(row => Math.abs((row.futureStrike || 0) - futureSpotReference)))
  const nearestSpotDistance = spotFutureReference != null
    ? Math.min(...candidates.map(row => Math.abs((row.futureStrike || 0) - spotFutureReference)))
    : null

  return [...candidates]
    .sort((left, right) => left.futureStrike - right.futureStrike)
    .map(row => {
      const profile = row.profile
      const localIv = nearestStrikeRow(row.strike)?.ivMid ?? atmIv.value ?? null
      const primaryDte = row.expiryRows?.[0]?.dte || daysToExpiry.value || 21
      const intensity = clamp(
        (0.45 * (Math.abs(profile?.gexNet || 0) / maxAbsGex))
        + (0.35 * (Math.abs(profile?.gexSlope || 0) / maxAbsSlope))
        + (0.20 * (Math.abs(profile?.gexCurvature || 0) / maxAbsCurvature)),
        0,
        1,
      )
      const slopeRatio = Math.abs(profile?.gexSlope || 0) / Math.max(maxAbsSlope, 1e-9)
      const curvatureRatio = Math.abs(profile?.gexCurvature || 0) / Math.max(maxAbsCurvature, 1e-9)
      const stepPoints = intensity >= 0.67 ? 60 : intensity >= 0.34 ? 80 : 100
      const totalPoints = Math.min(STRIKE_HEDGE_MAX_POINTS, stepPoints * STRIKE_HEDGE_MAX_STEPS)
      const totalContractsRaw = ((profile?.gexNet || 0) * totalPoints) / scale
      const totalContractsAbs = Math.abs(totalContractsRaw)
      const stepCount = Math.max(1, Math.min(STRIKE_HEDGE_MAX_STEPS, Math.round(totalPoints / stepPoints)))
      const upTone = hedgeToneForDirection(profile?.gexNet, 'up')
      const downTone = hedgeToneForDirection(profile?.gexNet, 'down')
      const upAction = hedgeActionLabel(profile?.gexNet, 'up')
      const downAction = hedgeActionLabel(profile?.gexNet, 'down')
      const upDistribution = buildHedgeSegments({
        strikeKey: row.strike,
        direction: 'up',
        stepCount,
        stepPoints,
        totalContractsAbs,
        gammaValue: profile?.gexNet,
        localIv,
        baseIv: atmIv.value ?? localIv,
        dte: primaryDte,
        slopeRatio,
        curvatureRatio,
        actionLabel: upAction,
        tone: upTone,
      })
      const downDistribution = buildHedgeSegments({
        strikeKey: row.strike,
        direction: 'down',
        stepCount,
        stepPoints,
        totalContractsAbs,
        gammaValue: profile?.gexNet,
        localIv,
        baseIv: atmIv.value ?? localIv,
        dte: primaryDte,
        slopeRatio,
        curvatureRatio,
        actionLabel: downAction,
        tone: downTone,
      })
      const expiryLadders = [...(row.expiryRows || [])]
        .map(expiry => {
          const expiryTotalRaw = ((expiry.netGex || 0) * totalPoints) / scale
          const expiryTotalAbs = Math.abs(expiryTotalRaw)
          const expiryUpAction = hedgeActionLabel(expiry.netGex, 'up')
          const expiryDistribution = buildHedgeSegments({
            strikeKey: `${row.strike}-${expiry.expiry}`,
            direction: 'up',
            stepCount,
            stepPoints,
            totalContractsAbs: expiryTotalAbs,
            gammaValue: expiry.netGex,
            localIv,
            baseIv: atmIv.value ?? localIv,
            dte: expiry.dte || primaryDte,
            slopeRatio,
            curvatureRatio,
            actionLabel: expiryUpAction,
            tone: hedgeToneForDirection(expiry.netGex, 'up'),
          })
          return {
            expiry: expiry.expiry,
            dte: expiry.dte,
            totalOi: expiry.totalOi,
            callOi: expiry.callOi,
            putOi: expiry.putOi,
            netGex: expiry.netGex,
            upTone: hedgeToneForDirection(expiry.netGex, 'up'),
            downTone: hedgeToneForDirection(expiry.netGex, 'down'),
            upAction: expiryUpAction,
            downAction: hedgeActionLabel(expiry.netGex, 'down'),
            stepContracts: expiryDistribution.firstContractsAbs,
            tailContracts: expiryDistribution.lastContractsAbs,
            totalContracts: expiryTotalAbs,
            stepRangeLabel: `${compactNumber(expiryDistribution.firstContractsAbs)} -> ${compactNumber(expiryDistribution.lastContractsAbs)}`,
          }
        })
        .filter(expiry => expiry.stepContracts > 1)
        .sort((left, right) => right.stepContracts - left.stepContracts)
        .slice(0, 4)

      return {
        ...row,
        localIv,
        stepPoints,
        totalPoints,
        stepCount,
        stepContractsAbs: upDistribution.firstContractsAbs,
        totalContractsAbs,
        netGex: profile?.gexNet || 0,
        netDex: profile?.dexNet || 0,
        totalOi: profile?.totalOi || 0,
        upTone,
        downTone,
        upAction,
        downAction,
        upSegments: upDistribution.segments,
        downSegments: downDistribution.segments,
        upStepRangeLabel: `${compactNumber(upDistribution.firstContractsAbs)} -> ${compactNumber(upDistribution.lastContractsAbs)}`,
        downStepRangeLabel: `${compactNumber(downDistribution.firstContractsAbs)} -> ${compactNumber(downDistribution.lastContractsAbs)}`,
        expiryLadders,
        expirySummary: expiryLadders.length
          ? expiryLadders.map(expiry => `V ${shortDateLabel(expiry.expiry)} ${compactNumber(expiry.totalOi)}`).join(' | ')
          : '--',
        windowLabel: `${stepPoints}pts x ${stepCount}`,
        isReferenceAnchor: Math.abs((row.futureStrike || 0) - futureSpotReference) === nearestFutureDistance,
        isSpotAnchor: spotFutureReference != null && Math.abs((row.futureStrike || 0) - spotFutureReference) === nearestSpotDistance,
      }
    })
})

const nearStrikeCompositionRows = computed(() => strikeHedgeMapRows.value.map(row => ({
  key: row.strike,
  futureStrike: row.futureStrike,
  distancePct: row.distancePct,
  totalOi: row.totalOi,
  callOi: row.profile?.callOi || 0,
  putOi: row.profile?.putOi || 0,
  stepPoints: row.stepPoints,
  upAction: row.upAction,
  stepContractsAbs: row.stepContractsAbs,
  stepRangeLabel: row.upStepRangeLabel,
  expirySummary: row.expirySummary,
})))

const hedgeBands = computed(() => {
  if (!referenceFuturePrice.value || !strikeCompositionRows.value.length) return []
  const rows = []
  for (const direction of ['down', 'up']) {
    for (const band of HEDGE_BANDS) {
      const members = strikeCompositionRows.value.filter(row => {
        if (!row.profile) return false
        const inBand = row.distancePct >= band.low && row.distancePct < band.high
        if (!inBand) return false
        return direction === 'down'
          ? row.futureStrike < referenceFuturePrice.value
          : row.futureStrike > referenceFuturePrice.value
      })
      const profiles = members.map(item => item.profile).filter(Boolean)
      const expiryRows = aggregateExpiryRows(members)
      const minStrike = profiles.length ? Math.min(...profiles.map(item => item.futureStrike)) : null
      const maxStrike = profiles.length ? Math.max(...profiles.map(item => item.futureStrike)) : null
      rows.push({
        key: `${direction}-${band.key}`,
        direction,
        label: `${direction === 'down' ? 'Down' : 'Up'} ${band.label}`,
        strikeRange: minStrike != null && maxStrike != null ? `${formatLevel(minStrike)}-${formatLevel(maxStrike)}` : '--',
        count: profiles.length,
        callHedgeWin: profiles.reduce((sum, item) => sum + (item.callHedgeWin || 0), 0),
        putHedgeWin: profiles.reduce((sum, item) => sum + (item.putHedgeWin || 0), 0),
        netHedgeWin: profiles.reduce((sum, item) => sum + (item.netHedgeWin || 0), 0),
        gammaHedgeWinPer100: profiles.reduce((sum, item) => sum + (item.gammaHedgeWinPer100 || 0), 0),
        expirySummary: summarizeExpiryRows(expiryRows, 2),
      })
    }
  }
  return rows
})

function interpolatePressurePoint(price) {
  if (price == null || !pressureCurve.value.length) return null
  const curve = pressureCurve.value
  const first = curve[0]
  const last = curve[curve.length - 1]

  if (price <= first.price) {
    return {
      ...first,
      price,
      byExpiry: blendExposureBreakdown(first.byExpiry, first.byExpiry, 0),
      byPutCall: blendExposureBreakdown(first.byPutCall, first.byPutCall, 0),
    }
  }

  if (price >= last.price) {
    return {
      ...last,
      price,
      byExpiry: blendExposureBreakdown(last.byExpiry, last.byExpiry, 0),
      byPutCall: blendExposureBreakdown(last.byPutCall, last.byPutCall, 0),
    }
  }

  for (let index = 1; index < curve.length; index += 1) {
    const left = curve[index - 1]
    const right = curve[index]
    if (price < left.price || price > right.price) continue
    const ratio = (price - left.price) / Math.max(right.price - left.price, 1e-9)
    return {
      price,
      dex: left.dex + ((right.dex - left.dex) * ratio),
      gex: left.gex + ((right.gex - left.gex) * ratio),
      vex: left.vex + ((right.vex - left.vex) * ratio),
      cex: left.cex + ((right.cex - left.cex) * ratio),
      hp: left.hp + ((right.hp - left.hp) * ratio),
      byExpiry: blendExposureBreakdown(left.byExpiry, right.byExpiry, ratio),
      byPutCall: blendExposureBreakdown(left.byPutCall, right.byPutCall, ratio),
    }
  }

  return null
}

function summarizeExpiryBreakdown(rows) {
  const slice = (rows || []).slice(0, 2)
  if (!slice.length) return '--'
  return slice.map(row => `${shortDateLabel(row.key)} ${formatSignedContracts(row.contracts)}`).join(' | ')
}

function summarizeSideBreakdown(rows) {
  const slice = (rows || []).slice(0, 2)
  if (!slice.length) return '--'
  return slice.map(row => `${row.key} ${formatSignedContracts(row.contracts)}`).join(' | ')
}

const pricePathNodes = computed(() => {
  if (spot.value == null || !pressureCurve.value.length) return []
  const centerPoint = interpolatePressurePoint(spot.value)
  if (!centerPoint) return []
  const scale = Math.max(winPointValue.value, 1e-9)
  const offsets = []

  for (let bucket = PRICE_PATH_BUCKETS; bucket >= 1; bucket -= 1) {
    offsets.push(-bucket * PRICE_PATH_STEP_POINTS)
  }
  offsets.push(0)
  for (let bucket = 1; bucket <= PRICE_PATH_BUCKETS; bucket += 1) {
    offsets.push(bucket * PRICE_PATH_STEP_POINTS)
  }

  return offsets
    .map(offsetPoints => {
      const point = interpolatePressurePoint(spot.value + offsetPoints)
      if (!point) return null
      const cumulativeDex = point.dex - centerPoint.dex
      return {
        ...point,
        offsetPoints,
        direction: offsetPoints < 0 ? 'down' : offsetPoints > 0 ? 'up' : 'spot',
        bucketIndex: Math.abs(offsetPoints) / PRICE_PATH_STEP_POINTS,
        cumulativeDex,
        cumulativeHedgeWin: cumulativeDex / scale,
        gammaHedgeWinPer100: (point.gex * PRICE_PATH_STEP_POINTS) / scale,
      }
    })
    .filter(Boolean)
    .sort((left, right) => left.price - right.price)
})

const pricePathBucketRows = computed(() => {
  if (!pricePathNodes.value.length) return []
  const nodeByOffset = new Map(pricePathNodes.value.map(node => [node.offsetPoints, node]))
  const centerNode = nodeByOffset.get(0)
  if (!centerNode) return []
  const scale = Math.max(winPointValue.value, 1e-9)
  const rows = []

  for (const direction of ['down', 'up']) {
    for (let bucketIndex = 1; bucketIndex <= PRICE_PATH_BUCKETS; bucketIndex += 1) {
      const sign = direction === 'down' ? -1 : 1
      const targetOffset = sign * bucketIndex * PRICE_PATH_STEP_POINTS
      const baseOffset = sign * (bucketIndex - 1) * PRICE_PATH_STEP_POINTS
      const targetNode = nodeByOffset.get(targetOffset)
      const baseNode = nodeByOffset.get(baseOffset)
      if (!targetNode || !baseNode) continue

      const incrementalDex = targetNode.dex - baseNode.dex
      const expiryRows = rankedBreakdownRows(
        diffExposureBreakdown(targetNode.byExpiry, baseNode.byExpiry),
        'dex',
        scale,
        3,
      )
      const sideRows = rankedBreakdownRows(
        diffExposureBreakdown(targetNode.byPutCall, baseNode.byPutCall),
        'dex',
        scale,
        2,
      )
      const incrementalWin = incrementalDex / scale
      const cumulativeWin = (targetNode.dex - centerNode.dex) / scale

      rows.push({
        key: `${direction}-${bucketIndex}`,
        direction,
        bucketIndex,
        stepLabel: ordinalBucketLabel(bucketIndex),
        rangeLabel: `${formatLevel(baseNode.price)} -> ${formatLevel(targetNode.price)}`,
        targetPrice: targetNode.price,
        basePrice: baseNode.price,
        incrementalWin,
        cumulativeWin,
        gammaHedgeWinPer100: (((targetNode.gex + baseNode.gex) / 2) * PRICE_PATH_STEP_POINTS) / scale,
        expiryRows,
        sideRows,
        expirySummary: summarizeExpiryBreakdown(expiryRows),
        sideSummary: summarizeSideBreakdown(sideRows),
        actionLabel: incrementalWin > 0 ? 'Comprar' : incrementalWin < 0 ? 'Vender' : 'Neutro',
        actionClass: incrementalWin > 0 ? 'buy' : incrementalWin < 0 ? 'sell' : 'flat',
      })
    }
  }

  return rows
})

const pricePathDownRows = computed(() => pricePathBucketRows.value.filter(row => row.direction === 'down'))
const pricePathUpRows = computed(() => pricePathBucketRows.value.filter(row => row.direction === 'up'))

const pricePathRange = computed(() => {
  if (!pricePathNodes.value.length) return null
  return {
    low: Math.min(...pricePathNodes.value.map(node => node.price)),
    high: Math.max(...pricePathNodes.value.map(node => node.price)),
  }
})

const pricePathPriceTicks = computed(() => pricePathNodes.value.map(node => node.price))

function pricePathY(price) {
  if (!pricePathRange.value) return LADDER_PAD.top
  const clampedPrice = clamp(price, pricePathRange.value.low, pricePathRange.value.high)
  const span = Math.max(pricePathRange.value.high - pricePathRange.value.low, 1)
  return LADDER_PAD.top + (((pricePathRange.value.high - clampedPrice) / span) * (LADDER_H - LADDER_PAD.top - LADDER_PAD.bottom))
}

const pricePathScale = computed(() => {
  const nodes = pricePathNodes.value
  if (!nodes.length) return 1
  return Math.max(...nodes.map(node => Math.abs(node.cumulativeHedgeWin)), 1)
})

const pricePathZeroX = LADDER_PAD.left + ((LADDER_W - LADDER_PAD.left - LADDER_PAD.right) / 2)

function pricePathX(contracts) {
  const halfWidth = (LADDER_W - LADDER_PAD.left - LADDER_PAD.right) / 2
  return pricePathZeroX + ((contracts / Math.max(pricePathScale.value, 1e-9)) * (halfWidth - 20))
}

const pricePathHedgeTicks = computed(() => {
  const rawStep = Math.max(pricePathScale.value / 2, 1)
  const magnitude = 10 ** Math.floor(Math.log10(rawStep))
  const normalized = rawStep / magnitude
  const stepBase = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10
  const step = stepBase * magnitude
  return [-2, -1, 0, 1, 2].map(multiplier => multiplier * step)
})

const pricePathMarkers = computed(() => pricePathNodes.value.map(node => {
  const x = clamp(pricePathX(node.cumulativeHedgeWin), LADDER_PAD.left + 6, LADDER_W - LADDER_PAD.right - 6)
  const y = pricePathY(node.price)
  const labelX = clamp(
    node.cumulativeHedgeWin >= 0 ? x + 8 : x - 8,
    6,
    LADDER_W - 6,
  )
  const textAnchor = node.cumulativeHedgeWin >= 0 ? 'start' : 'end'
  const offsetLabel = node.offsetPoints === 0
    ? 'Spot'
    : `${node.offsetPoints > 0 ? '+' : ''}${node.offsetPoints}pts`
  return {
    ...node,
    x,
    y,
    labelX,
    textAnchor,
    offsetLabel,
  }
}))

const pricePathSegments = computed(() => {
  if (pricePathMarkers.value.length < 2) return []
  const bucketMap = new Map(pricePathBucketRows.value.map(row => [row.key, row]))
  const segments = []

  for (let index = 1; index < pricePathMarkers.value.length; index += 1) {
    const left = pricePathMarkers.value[index - 1]
    const right = pricePathMarkers.value[index]
    const bucketKey = right.offsetPoints <= 0
      ? `down-${Math.abs(left.offsetPoints) / PRICE_PATH_STEP_POINTS}`
      : `up-${Math.abs(right.offsetPoints) / PRICE_PATH_STEP_POINTS}`
    const bucket = bucketMap.get(bucketKey)
    segments.push({
      key: `${left.offsetPoints}:${right.offsetPoints}`,
      x1: left.x,
      y1: left.y,
      x2: right.x,
      y2: right.y,
      tone: bucket?.actionClass || 'flat',
    })
  }

  return segments
})

const hasData = computed(() => spot.value != null && pressureCurve.value.length >= 9 && byStrike.value.length >= 10)

const totalFlow = computed(() => rawFlowEvents.value.reduce((sum, item) => sum + item._volume, 0))
const totalFlowLabel = computed(() => `Vol intraday ${compactNumber(totalFlow.value)}`)

const flowByStrike = computed(() => {
  const grouped = new Map()
  const now = Date.now()
  for (const event of rawFlowEvents.value) {
    const strike = event._strike
    if (strike == null || event._volume <= 0) continue
    const key = Math.round(strike)
    const current = grouped.get(key) || { strike: key, total: 0, call: 0, put: 0, recent: 0 }
    current.total += event._volume
    if (event._side === 'P') current.put += event._volume
    else current.call += event._volume
    if (event._epoch != null && (now - event._epoch) <= (30 * 60 * 1000)) {
      current.recent += event._volume
    }
    grouped.set(key, current)
  }
  return [...grouped.values()].sort((left, right) => left.strike - right.strike)
})

function nearestStrikeRow(price) {
  if (!byStrike.value.length || price == null) return null
  let best = null
  let bestDistance = Number.POSITIVE_INFINITY
  for (const row of byStrike.value) {
    const distance = Math.abs(row.strike - price)
    if (distance < bestDistance) {
      best = row
      bestDistance = distance
    }
  }
  return best
}

function localStrikeStats(price, baseStep) {
  const window = Math.max(baseStep * 2, price * 0.004)
  let oi = 0
  let absGex = 0
  let absDex = 0
  let absVex = 0
  let absCex = 0
  let ivWeighted = 0
  let ivWeight = 0
  let flowTotal = 0
  let callFlow = 0
  let putFlow = 0
  let recentFlow = 0

  for (const row of byStrike.value) {
    const distance = Math.abs(row.strike - price)
    if (distance > (window * 1.8)) continue
    const weight = Math.max(0, 1 - (distance / (window * 1.8)))
    const totalOi = row.callOi + row.putOi
    oi += totalOi * weight
    absGex += Math.abs(row.gex) * weight
    absDex += Math.abs(row.dex) * weight
    absVex += Math.abs(row.vex) * weight
    absCex += Math.abs(row.cex) * weight
    if (row.ivMid != null) {
      ivWeighted += row.ivMid * weight
      ivWeight += weight
    }
  }

  for (const row of flowByStrike.value) {
    const distance = Math.abs(row.strike - price)
    if (distance > (window * 1.8)) continue
    const weight = Math.max(0, 1 - (distance / (window * 1.8)))
    flowTotal += row.total * weight
    callFlow += row.call * weight
    putFlow += row.put * weight
    recentFlow += row.recent * weight
  }

  const centerRow = nearestStrikeRow(price)
  const centerIv = centerRow?.ivMid ?? atmIv.value ?? null
  const lower = [...byStrike.value].reverse().find(row => row.strike < price && row.ivMid != null) || null
  const upper = byStrike.value.find(row => row.strike > price && row.ivMid != null) || null
  let ivSlope = 0
  if (lower && upper && lower.ivMid != null && upper.ivMid != null && upper.strike !== lower.strike) {
    ivSlope = (upper.ivMid - lower.ivMid) / ((upper.strike - lower.strike) / price)
  }

  return {
    window,
    oi,
    absGex,
    absDex,
    absVex,
    absCex,
    localIv: ivWeight > 0 ? (ivWeighted / ivWeight) : centerIv,
    centerIv,
    ivSlope,
    flowTotal,
    callFlow,
    putFlow,
    recentFlow,
  }
}

function normalizeByPercentile(values) {
  const scale = quantile(values, 0.95) || Math.max(...values, 0) || 1
  return value => clamp(value / Math.max(scale, 1e-9), 0, 1)
}

const heatPoints = computed(() => {
  if (!hasData.value) return []
  const curve = pressureCurve.value
  const prices = curve.map(item => item.price)
  const steps = []
  for (let index = 1; index < prices.length; index += 1) {
    steps.push(prices[index] - prices[index - 1])
  }
  const baseStep = quantile(steps, 0.5) || Math.max((spot.value || 0) * 0.0018, 100)

  const baseRows = curve.map((point, index) => {
    const stats = localStrikeStats(point.price, baseStep)
    const distancePct = spot.value > 0 ? Math.abs(point.price - spot.value) / spot.value : 0
    const hedgeNeed = Math.abs(point.dex) + (0.35 * Math.abs(point.hp))
    const callPutImbalance = stats.flowTotal > 0 ? Math.abs(stats.callFlow - stats.putFlow) / stats.flowTotal : 0
    const ivShockEstimate = (
      Math.abs((stats.localIv ?? atmIv.value ?? 0) - (atmIv.value ?? stats.localIv ?? 0))
      + Math.abs(stats.ivSlope) * 0.0035
      + distancePct * 0.7
    )

    return {
      index,
      price: point.price,
      dex: point.dex,
      gex: point.gex,
      vex: point.vex,
      cex: point.cex,
      hp: point.hp,
      distancePct,
      hedgeNeed,
      localOi: stats.oi,
      localFlow: stats.flowTotal,
      localRecentFlow: stats.recentFlow,
      localIv: stats.localIv,
      ivSlope: stats.ivSlope,
      callPutImbalance,
      ivShockEstimate,
      liquidityBase: Math.sqrt(Math.max(stats.oi, 0)) + (0.75 * Math.sqrt(Math.max(stats.flowTotal, 0) + 1)),
      airPocketBase: 1 / Math.max(1, Math.sqrt(Math.max(stats.oi, 0)) + (0.65 * Math.sqrt(Math.max(stats.absGex, 0) + 1)) + (0.35 * Math.sqrt(Math.max(stats.flowTotal, 0) + 1))),
      vannaRaw: Math.abs(point.vex) * Math.max(ivShockEstimate, 0.0001),
      charmRaw: Math.abs(point.cex) * clamp(25 / Math.max(daysToExpiry.value, 1), 0.55, 2.25),
    }
  })

  const hedgeSlopeRaw = baseRows.map((row, index) => {
    const prev = baseRows[Math.max(index - 1, 0)]
    const next = baseRows[Math.min(index + 1, baseRows.length - 1)]
    const span = Math.max(next.price - prev.price, baseStep)
    return Math.abs((next.hedgeNeed - prev.hedgeNeed) / span)
  })

  const hedgeAccelerationRaw = baseRows.map((row, index) => {
    const prev = baseRows[Math.max(index - 1, 0)]
    const next = baseRows[Math.min(index + 1, baseRows.length - 1)]
    return Math.abs(next.hedgeNeed - (2 * row.hedgeNeed) + prev.hedgeNeed) / Math.max(baseStep * baseStep, 1)
  })

  const gexChangeRaw = baseRows.map((row, index) => {
    const prev = baseRows[Math.max(index - 1, 0)]
    const next = baseRows[Math.min(index + 1, baseRows.length - 1)]
    const span = Math.max(next.price - prev.price, baseStep)
    return Math.abs((next.gex - prev.gex) / span)
  })

  const cliffEvents = []
  for (let index = 1; index < baseRows.length; index += 1) {
    const prev = baseRows[index - 1]
    const current = baseRows[index]
    const signFlip = Math.sign(prev.gex || 0) !== Math.sign(current.gex || 0)
    const drop = Math.abs(Math.abs(current.gex) - Math.abs(prev.gex))
    const severity = drop + (signFlip ? (Math.max(Math.abs(prev.gex), Math.abs(current.gex)) * 0.65) : 0)
    if (severity > 0) {
      cliffEvents.push({
        price: (prev.price + current.price) / 2,
        severity,
      })
    }
  }

  const cliffScale = quantile(cliffEvents.map(item => item.severity), 0.9) || 1
  const gammaCliffRaw = baseRows.map(row => {
    if (!cliffEvents.length) return 0
    return cliffEvents.reduce((best, item) => {
      const distPct = spot.value > 0 ? Math.abs(item.price - row.price) / spot.value : 0
      const score = (item.severity / cliffScale) * Math.exp(-distPct / 0.0038)
      return Math.max(best, score)
    }, 0)
  })

  const normDex = normalizeByPercentile(baseRows.map(row => Math.abs(row.dex)))
  const normHedgeAccel = normalizeByPercentile(hedgeAccelerationRaw)
  const normGexChange = normalizeByPercentile(gexChangeRaw)
  const normVanna = normalizeByPercentile(baseRows.map(row => row.vannaRaw))
  const normCharm = normalizeByPercentile(baseRows.map(row => row.charmRaw))
  const normLiquidityGap = normalizeByPercentile(baseRows.map(row => row.hedgeNeed / Math.max(row.liquidityBase, 1)))
  const normIvStress = normalizeByPercentile(baseRows.map(row => {
    const ivGap = Math.abs((row.localIv ?? atmIv.value ?? 0) - (atmIv.value ?? row.localIv ?? 0))
    return ivGap + Math.abs(row.ivSlope) * 0.0045 + row.callPutImbalance * 0.12
  }))
  const normGammaCliff = normalizeByPercentile(gammaCliffRaw)
  const normAirPocket = normalizeByPercentile(baseRows.map(row => row.airPocketBase))

  return baseRows.map((row, index) => {
    const normalizedComponents = {
      hedgeAcceleration: normHedgeAccel(hedgeAccelerationRaw[index] + (hedgeSlopeRaw[index] * 0.35)),
      dexAbs: normDex(Math.abs(row.dex)),
      gexChange: normGexChange(gexChangeRaw[index]),
      vannaRisk: normVanna(row.vannaRaw),
      charmRisk: normCharm(row.charmRaw),
      liquidityGap: normLiquidityGap(row.hedgeNeed / Math.max(row.liquidityBase, 1)),
      ivStress: normIvStress(
        Math.abs((row.localIv ?? atmIv.value ?? 0) - (atmIv.value ?? row.localIv ?? 0))
        + Math.abs(row.ivSlope) * 0.0045
        + row.callPutImbalance * 0.12,
      ),
      gammaCliffProximity: normGammaCliff(gammaCliffRaw[index]),
      airPocket: normAirPocket(row.airPocketBase),
    }

    const weightedComponents = Object.entries(normalizedComponents).map(([key, value]) => ({
      key,
      label: COMPONENT_LABELS[key],
      score: value * 100,
      weighted: value * (COMPONENT_WEIGHTS[key] || 0),
    }))
    weightedComponents.sort((left, right) => right.weighted - left.weighted)
    const score = clamp(weightedComponents.reduce((sum, item) => sum + item.weighted, 0) * 100, 0, 100)

    return {
      ...row,
      score,
      normalizedComponents,
      weightedComponents,
      dominantKey: weightedComponents[0]?.key || 'hedgeAcceleration',
      direction: row.price >= (spot.value || row.price) ? 'up' : 'down',
    }
  })
})

const zoneThreshold = computed(() => {
  const scores = heatPoints.value.map(item => item.score)
  const p75 = quantile(scores, 0.75)
  const top = Math.max(...scores, 0)
  return clamp(Math.max(ZONE_MIN_SCORE, p75, top * 0.70), ZONE_MIN_SCORE, 82)
})

function buildZoneKey(point, startPrice, endPrice) {
  return `${point.direction}:${Math.round(startPrice)}-${Math.round(endPrice)}`
}

const zones = computed(() => {
  const threshold = zoneThreshold.value
  const points = heatPoints.value
  if (!points.length) return []

  const built = []
  let current = null

  const flush = () => {
    if (!current || !current.points.length) return
    const peakPoint = [...current.points].sort((left, right) => right.score - left.score)[0]
    const contributions = {}
    current.points.forEach(point => {
      point.weightedComponents.forEach(component => {
        contributions[component.key] = (contributions[component.key] || 0) + component.weighted
      })
    })
    const dominantKey = Object.entries(contributions).sort((left, right) => right[1] - left[1])[0]?.[0] || peakPoint.dominantKey
    const center = mean(current.points.map(point => point.price))
    const distancePct = spot.value > 0
      ? Math.max(0, Math.min(Math.abs(center - spot.value), Math.abs(current.startPrice - spot.value), Math.abs(current.endPrice - spot.value))) / spot.value
      : 0
    built.push({
      key: buildZoneKey(peakPoint, current.startPrice, current.endPrice),
      direction: peakPoint.direction,
      startPrice: current.startPrice,
      endPrice: current.endPrice,
      center,
      peakScore: peakPoint.score,
      avgScore: mean(current.points.map(point => point.score)),
      dominantKey,
      distancePct,
      points: current.points,
    })
    current = null
  }

  for (const point of points) {
    if (point.score < threshold) {
      flush()
      continue
    }
    if (!current) {
      current = {
        direction: point.direction,
        startPrice: point.price,
        endPrice: point.price,
        points: [point],
      }
      continue
    }

    const contiguous = Math.abs(point.index - current.points[current.points.length - 1].index) <= 1
    if (!contiguous || point.direction !== current.direction) {
      flush()
      current = {
        direction: point.direction,
        startPrice: point.price,
        endPrice: point.price,
        points: [point],
      }
      continue
    }

    current.endPrice = point.price
    current.points.push(point)
  }

  flush()
  return built.sort((left, right) => right.peakScore - left.peakScore)
})

const topZones = computed(() => zones.value.slice(0, 3))
const bestDownZone = computed(() => zones.value.filter(zone => zone.direction === 'down').sort((left, right) => right.peakScore - left.peakScore)[0] || null)
const bestUpZone = computed(() => zones.value.filter(zone => zone.direction === 'up').sort((left, right) => right.peakScore - left.peakScore)[0] || null)

const currentPoint = computed(() => {
  if (!heatPoints.value.length || spot.value == null) return null
  return heatPoints.value.reduce((best, point) => {
    if (!best) return point
    return Math.abs(point.price - spot.value) < Math.abs(best.price - spot.value) ? point : best
  }, null)
})

const currentZone = computed(() => {
  if (!currentPoint.value) return null
  return zones.value.find(zone => currentPoint.value.price >= zone.startPrice && currentPoint.value.price <= zone.endPrice) || null
})

const nextCriticalZone = computed(() => {
  const candidates = zones.value.filter(zone => zone.key !== currentZone.value?.key)
  if (!candidates.length) return null
  return [...candidates].sort((left, right) => left.distancePct - right.distancePct)[0] || null
})

const currentCauseLabel = computed(() => causeLabel(currentZone.value?.dominantKey || currentPoint.value?.dominantKey))

const topCurrentFactors = computed(() => (currentPoint.value?.weightedComponents || []).slice(0, 3))

const gammaFlipLevel = computed(() => sanitizeReferenceLevel(nearestZeroCrossing(heatPoints.value, 'gex')))
const dexNeutralLevel = computed(() => sanitizeReferenceLevel(nearestZeroCrossing(heatPoints.value, 'dex')))

function sanitizeReferenceLevel(value) {
  const numeric = safeNumber(value)
  if (numeric == null) return null
  return numeric >= 1000 ? numeric : null
}

function nearestZeroCrossing(points, key) {
  if (!spot.value || points.length < 2) return null
  const crossings = []
  for (let index = 1; index < points.length; index += 1) {
    const prev = points[index - 1]
    const current = points[index]
    const left = safeNumber(prev[key])
    const right = safeNumber(current[key])
    if (left == null || right == null || left === right) continue
    if (Math.sign(left) === Math.sign(right)) continue
    const ratio = Math.abs(left) / (Math.abs(left) + Math.abs(right))
    const price = prev.price + ((current.price - prev.price) * ratio)
    crossings.push(price)
  }
  if (!crossings.length) return null
  const nearest = crossings.sort((left, right) => Math.abs(left - spot.value) - Math.abs(right - spot.value))[0]
  return nearest != null && nearest > 0 ? nearest : null
}

const confidenceScore = computed(() => {
  if (!currentPoint.value) return 0
  const coverage = heatPoints.value.length ? 1 : 0
  const flowSupport = clamp((currentPoint.value.localRecentFlow || currentPoint.value.localFlow || 0) / Math.max(quantile(heatPoints.value.map(item => item.localFlow || 0), 0.85), 1), 0, 1)
  const dominantShare = currentPoint.value.weightedComponents.length
    ? (currentPoint.value.weightedComponents[0].weighted / Math.max(currentPoint.value.weightedComponents.reduce((sum, item) => sum + item.weighted, 0), 1e-9))
    : 0
  return Math.round(clamp(
    42
    + (currentPoint.value.score * 0.28)
    + (coverage * 8)
    + (flowSupport * 18)
    + (dominantShare * 18),
    20,
    97,
  ))
})

const confidenceLabel = computed(() => `${confidenceScore.value}/100`)

const hedgeDirectionLabel = computed(() => {
  const targetZone = currentZone.value || nextCriticalZone.value || bestDownZone.value || bestUpZone.value
  if (!targetZone) return 'sem direcao clara'
  return targetZone.direction === 'down' ? 'vender futuro na queda' : 'comprar futuro na alta'
})

const riskDirectionClass = computed(() => {
  const targetZone = currentZone.value || nextCriticalZone.value || null
  return targetZone?.direction === 'down' ? 'down' : targetZone?.direction === 'up' ? 'up' : ''
})

const heatZones = computed(() => zones.value.map(zone => {
  const startPoint = zone.points[0]
  const endPoint = zone.points[zone.points.length - 1]
  return {
    ...zone,
    svgX1: cellStartX(startPoint.index),
    svgX2: cellEndX(endPoint.index),
  }
}))

const scoreTicks = computed(() => SCORE_TICKS)

const heatBarY = 102
const heatBarH = 32
const lineTop = 34
const lineBottom = 88

function pointX(index) {
  const count = heatPoints.value.length
  if (count <= 1) return PAD.left
  return PAD.left + ((index / Math.max(count - 1, 1)) * (HEAT_W - PAD.left - PAD.right))
}

function cellStartX(index) {
  if (!heatPoints.value.length) return PAD.left
  if (index <= 0) return PAD.left
  return (pointX(index - 1) + pointX(index)) / 2
}

function cellEndX(index) {
  if (!heatPoints.value.length) return HEAT_W - PAD.right
  if (index >= heatPoints.value.length - 1) return HEAT_W - PAD.right
  return (pointX(index) + pointX(index + 1)) / 2
}

function scoreY(score) {
  return lineTop + ((1 - (clamp(score, 0, 100) / 100)) * (lineBottom - lineTop))
}

function scoreColor(score, direction = 'down') {
  if (direction === 'up') {
    if (score >= 85) return '#16a34a'
    if (score >= 72) return '#22c55e'
    if (score >= 58) return '#14b8a6'
    if (score >= 42) return '#38bdf8'
    if (score >= 28) return '#60a5fa'
    return '#93c5fd'
  }
  if (score >= 85) return '#ef4444'
  if (score >= 72) return '#fb7185'
  if (score >= 58) return '#f59e0b'
  if (score >= 42) return '#eab308'
  return '#0f172a'
}

function scoreOpacity(score, direction = 'down') {
  if (direction === 'up') {
    return clamp(0.34 + (score / 100) * 0.62, 0.34, 0.96)
  }
  return clamp(0.18 + (score / 100) * 0.82, 0.18, 0.96)
}

const heatCells = computed(() => heatPoints.value.map(point => ({
  index: point.index,
  x: cellStartX(point.index),
  w: Math.max(cellEndX(point.index) - cellStartX(point.index), 3),
  fill: scoreColor(point.score, point.direction),
  opacity: scoreOpacity(point.score, point.direction),
  stroke: point.direction === 'up' ? '#d9f99d' : '#fecdd3',
  strokeOpacity: point.direction === 'up'
    ? clamp(0.42 + (point.score / 100) * 0.40, 0.42, 0.88)
    : clamp(0.20 + (point.score / 100) * 0.34, 0.20, 0.66),
})))

const scorePath = computed(() => {
  if (heatPoints.value.length < 2) return ''
  return heatPoints.value
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${pointX(point.index)} ${scoreY(point.score)}`)
    .join(' ')
})

const spotX = computed(() => {
  if (!currentPoint.value) return null
  return pointX(currentPoint.value.index)
})

const referenceX = computed(() => {
  const level = referenceSpotPrice.value
  if (level == null || !heatPoints.value.length) return null
  return interpolatePriceToX(level)
})

const gammaFlipX = computed(() => {
  const level = gammaFlipLevel.value
  if (level == null || !heatPoints.value.length) return null
  return interpolatePriceToX(level)
})

const dexNeutralX = computed(() => {
  const level = dexNeutralLevel.value
  if (level == null || !heatPoints.value.length) return null
  return interpolatePriceToX(level)
})

function interpolatePriceToX(price) {
  const points = heatPoints.value
  if (!points.length) return null
  if (price <= points[0].price) return pointX(points[0].index)
  if (price >= points[points.length - 1].price) return pointX(points[points.length - 1].index)
  for (let index = 1; index < points.length; index += 1) {
    const left = points[index - 1]
    const right = points[index]
    if (price < left.price || price > right.price) continue
    const ratio = (price - left.price) / Math.max(right.price - left.price, 1)
    return pointX(left.index) + ((pointX(right.index) - pointX(left.index)) * ratio)
  }
  return null
}

const xLabels = computed(() => {
  if (!heatPoints.value.length) return []
  const maxLabels = 8
  const step = Math.max(1, Math.floor(heatPoints.value.length / maxLabels))
  const labels = []
  for (let index = 0; index < heatPoints.value.length; index += step) {
    labels.push({ index, price: heatPoints.value[index].price, x: pointX(index) })
  }
  if (labels[labels.length - 1]?.index !== heatPoints.value.length - 1) {
    labels.push({
      index: heatPoints.value.length - 1,
      price: heatPoints.value[heatPoints.value.length - 1].price,
      x: pointX(heatPoints.value.length - 1),
    })
  }
  return labels
})

const hoverPoint = computed(() => {
  if (hoverIndex.value == null || hoverIndex.value < 0 || hoverIndex.value >= heatPoints.value.length) return null
  return heatPoints.value[hoverIndex.value]
})

function handleHeatMove(event) {
  if (!heatWrap.value || !heatPoints.value.length) return
  const rect = heatWrap.value.getBoundingClientRect()
  const relativeX = clamp(((event.clientX - rect.left) / Math.max(rect.width, 1)) * HEAT_W, PAD.left, HEAT_W - PAD.right)
  let bestIndex = 0
  let bestDistance = Number.POSITIVE_INFINITY
  for (const point of heatPoints.value) {
    const distance = Math.abs(pointX(point.index) - relativeX)
    if (distance < bestDistance) {
      bestDistance = distance
      bestIndex = point.index
    }
  }
  hoverIndex.value = bestIndex
}

const tooltipStyle = computed(() => {
  if (!heatWrap.value || !hoverPoint.value) return {}
  const rect = heatWrap.value.getBoundingClientRect()
  const leftPct = pointX(hoverPoint.value.index) / HEAT_W
  const topPct = scoreY(hoverPoint.value.score) / HEAT_H
  let left = (leftPct * rect.width) + 14
  if ((left + 220) > rect.width) left -= 236
  return {
    left: `${Math.max(8, left)}px`,
    top: `${Math.max(12, (topPct * rect.height) - 36)}px`,
  }
})

function causeLabel(key) {
  return COMPONENT_LABELS[key] || 'Estrutura'
}

function zoneCauseLabel(zone) {
  if (!zone) return '--'
  return causeLabel(zone.dominantKey)
}

function zoneRangeLabel(zone) {
  if (!zone) return '--'
  return `${formatLevel(zone.startPrice)}-${formatLevel(zone.endPrice)}`
}

function formatScore(value) {
  const numeric = safeNumber(value)
  if (numeric == null) return '--'
  return `${Math.round(numeric)}/100`
}

function shortDateLabel(value) {
  const text = String(value || '').trim()
  if (!text) return '--'
  const datePart = text.slice(0, 10)
  if (/^\d{4}-\d{2}-\d{2}$/.test(datePart)) {
    return `${datePart.slice(8, 10)}/${datePart.slice(5, 7)}`
  }
  return text
}

function formatSignedContracts(value) {
  const numeric = safeNumber(value)
  if (numeric == null) return '--'
  const prefix = numeric > 0 ? '+' : ''
  return `${prefix}${compactNumber(numeric)}`
}

function formatAbsoluteContracts(value) {
  const numeric = safeNumber(value)
  if (numeric == null) return '--'
  return compactNumber(Math.abs(numeric))
}

function formatLevel(value) {
  const numeric = safeNumber(value)
  if (numeric == null) return '--'
  return new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 }).format(numeric)
}

function formatLevelShort(value) {
  const numeric = safeNumber(value)
  if (numeric == null) return '--'
  return `${(numeric / 1000).toFixed(1)}k`
}

function formatPct(value) {
  const numeric = safeNumber(value)
  if (numeric == null) return '--'
  return `${(numeric * 100).toFixed(2)}%`
}

function buildSnapshotRow() {
  const targetZone = currentZone.value || nextCriticalZone.value || topZones.value[0] || null
  if (!currentPoint.value) return null
  return {
    ts: Date.now(),
    score: currentPoint.value.score,
    zoneKey: currentZone.value?.key || null,
    topZoneKey: topZones.value[0]?.key || null,
    criticalZoneKey: targetZone?.key || null,
  }
}

function persistSnapshot() {
  const snapshot = buildSnapshotRow()
  if (!snapshot) return
  const next = [...scoreHistory.value]
  const last = next[next.length - 1]
  if (last && Math.abs(snapshot.ts - last.ts) < 45_000) {
    next[next.length - 1] = snapshot
  } else {
    next.push(snapshot)
  }
  const pruned = next
    .filter(item => item && Number.isFinite(item.ts) && (snapshot.ts - item.ts) <= SCORE_TTL_MS)
    .slice(-MAX_HISTORY_ROWS)
  scoreHistory.value = pruned
  writeHistoryCache(props.underlyingSecurity, pruned)
}

const scoreDelta15m = computed(() => {
  if (!scoreHistory.value.length || !currentPoint.value) return null
  const targetTs = Date.now() - SCORE_WINDOW_MS
  let reference = null
  for (const row of scoreHistory.value) {
    if (row.ts <= targetTs) reference = row
  }
  if (!reference) return null
  return currentPoint.value.score - reference.score
})

const alerts = computed(() => {
  const next = []
  const targetZone = currentZone.value || nextCriticalZone.value
  const previous = scoreHistory.value.length >= 2 ? scoreHistory.value[scoreHistory.value.length - 2] : null

  if (nextCriticalZone.value && nextCriticalZone.value.peakScore >= 75 && nextCriticalZone.value.distancePct <= 0.003) {
    next.push({
      key: 'near-zone',
      tone: 'warn',
      tag: 'Proxima',
      message: `Spot a ${formatPct(nextCriticalZone.value.distancePct)} de uma pain zone ${nextCriticalZone.value.direction === 'down' ? 'abaixo' : 'acima'} com score ${Math.round(nextCriticalZone.value.peakScore)}.`,
    })
  }

  if (currentZone.value && currentZone.value.peakScore >= 75) {
    next.push({
      key: 'inside-zone',
      tone: 'hot',
      tag: 'Dentro',
      message: `Spot dentro da pain zone ${zoneRangeLabel(currentZone.value)} com causa ${zoneCauseLabel(currentZone.value)}.`,
    })
  }

  if (scoreDelta15m.value != null && scoreDelta15m.value >= 20) {
    next.push({
      key: 'score-jump',
      tone: 'hot',
      tag: 'Acelerou',
      message: `Pain score subiu ${scoreDelta15m.value.toFixed(0)} pontos nos ultimos 15 minutos.`,
    })
  }

  if (previous && topZones.value[0] && previous.topZoneKey && previous.topZoneKey !== topZones.value[0].key) {
    next.push({
      key: 'new-zone',
      tone: 'warn',
      tag: 'Nova zona',
      message: `Nova pain zone dominante em ${zoneRangeLabel(topZones.value[0])} por ${zoneCauseLabel(topZones.value[0])}.`,
    })
  }

  if (targetZone && !currentZone.value && targetZone.distancePct <= 0.006 && currentPoint.value?.weightedComponents?.[0]?.key === 'airPocket') {
    next.push({
      key: 'air-pocket',
      tone: 'warn',
      tag: 'Air pocket',
      message: `Estrutura rarefeita perto de ${zoneRangeLabel(targetZone)}; risco de deslocamento rapido se o fluxo confirmar.`,
    })
  }

  return next
})

async function loadFlow({ force = false } = {}) {
  if (!props.underlyingSecurity) return
  const now = Date.now()
  if (!force && now - lastFlowLoadAt < 20_000) return
  flowError.value = ''
  try {
    const response = await getVolumeActivity({
      underlying_security: props.underlyingSecurity,
      limit: 1800,
      lookback_days: 1,
    })
    const payload = response?.data
    const rows = Array.isArray(payload) ? payload : Array.isArray(payload?.rows) ? payload.rows : []
    rawFlowEvents.value = rows.map(normalizeFlowEvent).filter(item => item._volume > 0)
    flowLoaded.value = true
    lastFlowLoadAt = Date.now()
    await nextTick()
    persistSnapshot()
  } catch (err) {
    flowLoaded.value = false
    flowError.value = err?.response?.data?.error || err?.message || 'fluxo indisponivel'
  }
}

async function loadModel({ force = false } = {}) {
  if (!props.underlyingSecurity) return
  const hasNormalizedProp = hasUsableModelPayload(props.modelData)
  const hasRawProp = hasUsableRawModelPayload(props.rawModelData)
  if (hasNormalizedProp && hasRawProp && !force) {
    modelError.value = ''
    return
  }
  const now = Date.now()
  if (!force && now - lastModelLoadAt < 20_000) return
  loadingModel.value = true
  modelError.value = ''
  try {
    const response = await getLatestOptionsModel({
      underlying_security: props.underlyingSecurity,
    })
    const raw = response?.data ?? response
    const normalized = normalizeStandaloneModel(raw)
    if (!hasUsableModelPayload(normalized)) {
      throw new Error('modelo compacto sem dados suficientes')
    }
    fallbackRawModelData.value = raw
    fallbackModelData.value = normalized
    lastModelLoadAt = Date.now()
  } catch (err) {
    if (!hasUsableModelPayload(props.modelData) && !hasUsableModelPayload(fallbackModelData.value)) {
      modelError.value = err?.response?.data?.error || err?.message || 'modelo indisponivel'
    }
  } finally {
    loadingModel.value = false
  }
}

onMounted(async () => {
  scoreHistory.value = readHistoryCache(props.underlyingSecurity)
  await Promise.all([
    loadModel(),
    loadFlow({ force: true }),
  ])
  loadTimer = setInterval(() => loadFlow({ force: true }), HEAT_REFRESH_MS)
  modelTimer = setInterval(() => loadModel(), HEAT_REFRESH_MS)
})

onUnmounted(() => {
  clearInterval(loadTimer)
  clearInterval(modelTimer)
})

watch(() => props.underlyingSecurity, async (next, previous) => {
  if (!next || next === previous) return
  scoreHistory.value = readHistoryCache(next)
  fallbackRawModelData.value = null
  fallbackModelData.value = null
  modelError.value = ''
  rawFlowEvents.value = []
  flowLoaded.value = false
  await Promise.all([
    loadModel({ force: true }),
    loadFlow({ force: true }),
  ])
})

watch(() => props.refreshNonce, async (next, previous) => {
  if (!next || next === previous) return
  await Promise.all([
    loadModel(),
    loadFlow({ force: true }),
  ])
})

watch(
  () => [effectiveModelData.value?.captured_at, currentPoint.value?.score, currentZone.value?.key, topZones.value[0]?.key].join('|'),
  () => {
    if (!currentPoint.value) return
    persistSnapshot()
  },
)
</script>


<style scoped src="./DealerPainMapWidget.css"></style>

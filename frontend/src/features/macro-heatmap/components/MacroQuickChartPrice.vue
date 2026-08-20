<template>
        <div class="quick-chart-wrap">
          <svg
            v-if="asset.chart && asset.chart.candles.length"
            :viewBox="`0 0 ${asset.chart.width} ${asset.chart.height}`"
            class="quick-chart"
            @mousedown="startDrag(asset.key, $event, asset)"
            @mousemove="handlePointerMove(asset.key, $event, asset)"
            @mouseleave="handlePointerLeave(asset.key)"
            @mouseup="stopDrag(asset.key)"
          >
            <rect
              :x="asset.chart.plotLeft"
              :y="asset.chart.plotTop"
              :width="asset.chart.plotRight - asset.chart.plotLeft"
              :height="asset.chart.plotBottom - asset.chart.plotTop"
              class="plot-bg"
              rx="12"
            />

            <g v-for="cell in asset.chart.participantHeatCells" :key="cell.key">
              <rect
                :x="cell.x"
                :y="cell.y"
                :width="cell.width"
                :height="cell.height"
                rx="4"
                class="foreign-heat-cell"
                :fill="cell.fill"
                :fill-opacity="cell.opacity"
              />
            </g>

            <g v-for="tick in asset.chart.yTicks" :key="`${asset.key}-y-${tick.value}`">
              <line :x1="asset.chart.plotLeft" :x2="asset.chart.plotRight" :y1="tick.y" :y2="tick.y" class="grid" />
              <text :x="asset.chart.plotLeft - 8" :y="tick.y + 4" class="axis-label" text-anchor="end">{{ tick.label }}</text>
            </g>

            <g v-for="tick in asset.chart.xTicks" :key="`${asset.key}-x-${tick.label}-${tick.x}`">
              <line :x1="tick.x" :x2="tick.x" :y1="asset.chart.plotTop" :y2="asset.chart.plotBottom" class="grid vertical" />
              <text :x="tick.x" :y="asset.chart.plotBottom + 16" class="axis-label time" text-anchor="middle">{{ tick.label }}</text>
            </g>

            <text :x="asset.chart.plotLeft - 22" :y="asset.chart.plotTop - 6" class="axis-title">preco</text>
            <text :x="asset.chart.plotRight" :y="asset.chart.plotBottom + 30" class="axis-title" text-anchor="end">tempo</text>

            <line
              v-if="Number.isFinite(asset.chart.latestPriceY)"
              :x1="asset.chart.plotLeft"
              :x2="asset.chart.plotRight"
              :y1="asset.chart.latestPriceY"
              :y2="asset.chart.latestPriceY"
              class="last-line"
            />

            <g v-for="candle in asset.chart.candles" :key="`${asset.key}-${candle.time}`">
              <line :x1="candle.x" :x2="candle.x" :y1="candle.highY" :y2="candle.lowY" class="wick" :class="candle.direction" />
              <rect
                :x="candle.x - candle.width / 2"
                :y="Math.min(candle.openY, candle.closeY)"
                :width="candle.width"
                :height="Math.max(Math.abs(candle.closeY - candle.openY), 2)"
                class="body"
                :class="candle.direction"
                rx="2"
              />
            </g>

            <g v-for="marker in asset.chart.annotationMarkers" :key="marker.key">
              <rect
                :x="marker.x - (marker.width / 2)"
                :y="marker.y - (marker.height / 2)"
                :width="marker.width"
                :height="marker.height"
                rx="5"
                class="annotation-marker"
                :class="annotationToneClass(marker.type)"
              />
              <text
                :x="marker.x"
                :y="marker.y + 2.5"
                class="annotation-marker-label"
                text-anchor="middle"
              >
                {{ marker.shortLabel }}
              </text>
            </g>

            <g v-for="valueLine in asset.chart.valueLevelLines" :key="valueLine.key">
              <line
                :x1="asset.chart.plotLeft"
                :x2="asset.chart.plotRight"
                :y1="valueLine.y"
                :y2="valueLine.y"
                class="value-level-line"
                :stroke="valueLine.color"
                :stroke-width="valueLine.strokeWidth"
                :stroke-dasharray="valueLine.dashArray || null"
              />
              <rect
                :x="asset.chart.plotLeft + 6"
                :y="valueLine.y - 8"
                width="104"
                height="15"
                rx="6"
                class="value-level-tag-bg"
              />
              <text
                :x="asset.chart.plotLeft + 12"
                :y="valueLine.y + 2"
                class="value-level-tag"
                text-anchor="start"
                :fill="valueLine.color"
              >
                {{ valueLine.shortLabel }} {{ formatPrice(valueLine.price) }}
              </text>
            </g>

            <g v-for="gammaBand in asset.chart.gammaRegionBands" :key="gammaBand.key">
              <rect
                :x="asset.chart.plotLeft"
                :y="gammaBand.yTop"
                :width="asset.chart.plotRight - asset.chart.plotLeft"
                :height="gammaBand.height"
                rx="3"
                class="gamma-region-band"
                :fill="gammaBand.fill"
                :fill-opacity="gammaBand.opacity"
              />
              <line
                :x1="asset.chart.plotLeft"
                :x2="asset.chart.plotRight"
                :y1="gammaBand.centerY"
                :y2="gammaBand.centerY"
                class="gamma-region-line"
                :stroke="gammaBand.stroke"
                :stroke-opacity="gammaBand.lineOpacity"
                :stroke-dasharray="gammaBand.dashArray"
              />
              <g v-if="gammaBand.showTag">
                <rect
                  :x="asset.chart.plotLeft + 6"
                  :y="gammaBand.centerY - 8"
                  width="90"
                  height="15"
                  rx="5"
                  class="gamma-region-tag-bg"
                />
                <text
                  :x="asset.chart.plotLeft + 12"
                  :y="gammaBand.centerY + 2"
                  class="gamma-region-tag"
                  text-anchor="start"
                  :fill="gammaBand.stroke"
                >
                  {{ gammaBand.shortLabel }} {{ formatPrice(gammaBand.price) }}
                </text>
              </g>
            </g>

            <g v-if="asset.chart.fairValueLine?.path">
              <path
                :d="asset.chart.fairValueLine.path"
                class="fair-value-line"
                :stroke="asset.chart.fairValueLine.stroke"
                :stroke-opacity="asset.chart.fairValueLine.opacity"
              />
              <rect
                :x="asset.chart.plotLeft + 6"
                :y="asset.chart.fairValueLine.lastY - 8"
                width="96"
                height="15"
                rx="6"
                class="fair-value-tag-bg"
              />
              <text
                :x="asset.chart.plotLeft + 12"
                :y="asset.chart.fairValueLine.lastY + 2"
                class="fair-value-tag"
                text-anchor="start"
                :fill="asset.chart.fairValueLine.stroke"
              >
                FV {{ formatPrice(asset.chart.fairValueLine.points?.[asset.chart.fairValueLine.points.length - 1]?.price) }}
              </text>
            </g>

            <g v-for="band in asset.chart.liquidityPoolBands" :key="band.key">
              <rect
                :x="asset.chart.plotLeft"
                :y="band.yTop"
                :width="asset.chart.plotRight - asset.chart.plotLeft"
                :height="band.height"
                rx="3"
                class="liquidity-pool-band"
                :fill="band.fill"
                :fill-opacity="band.opacity"
                :stroke="band.stroke"
                :stroke-opacity="band.strokeOpacity"
              />
              <line
                :x1="asset.chart.plotLeft"
                :x2="asset.chart.plotRight"
                :y1="band.centerY"
                :y2="band.centerY"
                class="liquidity-pool-band-line"
                :stroke="band.stroke"
                :stroke-opacity="band.lineOpacity"
              />
              <circle
                :cx="asset.chart.plotRight - 48"
                :cy="band.centerY"
                r="3.2"
                class="liquidity-pool-band-dot"
                :fill="band.stroke"
                :fill-opacity="band.lineOpacity"
              />
              <g v-if="band.showTag">
                <rect
                  :x="asset.chart.plotLeft + 6"
                  :y="band.centerY - 8"
                  width="90"
                  height="15"
                  rx="5"
                  class="liquidity-pool-band-tag-bg"
                />
                <text
                  :x="asset.chart.plotLeft + 12"
                  :y="band.centerY + 2"
                  class="liquidity-pool-band-tag"
                  text-anchor="start"
                  :fill="band.stroke"
                >
                  {{ band.shortLabel }} {{ formatPrice(band.price) }}
                </text>
              </g>
            </g>

            <g v-for="line in asset.chart.liquidityPoolLines" :key="line.key">
              <line
                :x1="asset.chart.plotLeft"
                :x2="asset.chart.plotRight"
                :y1="line.y"
                :y2="line.y"
                class="liquidity-pool-price-line"
                :stroke="line.stroke"
                :stroke-opacity="line.opacity"
              />
              <rect
                :x="asset.chart.plotLeft + 6"
                :y="line.y - 8"
                width="102"
                height="15"
                rx="6"
                class="liquidity-pool-price-tag-bg"
              />
              <text
                :x="asset.chart.plotLeft + 12"
                :y="line.y + 2"
                class="liquidity-pool-price-tag"
                text-anchor="start"
                :fill="line.stroke"
              >
                {{ line.label }}
              </text>
            </g>

            <g v-if="getHover(asset.key)">
              <line :x1="getHover(asset.key).x" :x2="getHover(asset.key).x" :y1="asset.chart.plotTop" :y2="asset.chart.plotBottom" class="crosshair" />
              <line :x1="asset.chart.plotLeft" :x2="asset.chart.plotRight" :y1="getHover(asset.key).y" :y2="getHover(asset.key).y" class="crosshair" />

              <rect :x="asset.chart.plotLeft - 54" :y="getHover(asset.key).y - 10" width="48" height="18" rx="6" class="axis-tag-bg" />
              <text :x="asset.chart.plotLeft - 30" :y="getHover(asset.key).y + 3" class="axis-tag" text-anchor="middle">{{ getHover(asset.key).priceLabel }}</text>

              <rect :x="clampTagX(getHover(asset.key).x, asset.chart)" :y="asset.chart.plotBottom + 8" width="58" height="18" rx="6" class="axis-tag-bg" />
              <text :x="clampTagX(getHover(asset.key).x, asset.chart) + 29" :y="asset.chart.plotBottom + 21" class="axis-tag" text-anchor="middle">{{ getHover(asset.key).timeLabel }}</text>
            </g>
          </svg>
          <div v-else class="empty-state inline">Ainda nao ha candles suficientes para {{ asset.label }}.</div>
        </div>

        <div v-if="asset.chart?.annotationMarkers?.length" class="annotation-legend-strip">
          <span
            v-for="item in ANNOTATION_LEGEND_ITEMS"
            :key="`${asset.key}-annot-legend-${item.type}`"
            class="annotation-legend-item"
            :class="annotationToneClass(item.type)"
          >
            <span class="annotation-legend-badge">{{ item.shortLabel }}</span>
            <span>{{ item.label }}</span>
          </span>
        </div>

        <div v-if="getHover(asset.key)" class="hover-card">
          <div class="hover-card-head">
            <span>{{ asset.label }}</span>
            <span>{{ getHover(asset.key).timeFullLabel }}</span>
          </div>
          <div class="hover-row">
            <span class="hover-label">candle</span>
            <span class="hover-value">
              O {{ formatPrice(getHover(asset.key).candle?.open) }}
              H {{ formatPrice(getHover(asset.key).candle?.high) }}
              L {{ formatPrice(getHover(asset.key).candle?.low) }}
              C {{ formatPrice(getHover(asset.key).candle?.close) }}
            </span>
          </div>
          <div class="hover-row">
            <span class="hover-label">cursor</span>
            <span class="hover-value">{{ getHover(asset.key).priceLabel }}</span>
          </div>
          <div class="hover-row">
            <span class="hover-label">fluxo</span>
            <span class="hover-value">
              <template v-if="participantSide === 'both'">
                {{ selectedScopeLabel }} compras {{ formatSignedQuantity(getDisplayFlowSummary(asset.key)?.buyQuantity, false) }}
                | vendas {{ formatSignedQuantity(getDisplayFlowSummary(asset.key)?.sellQuantity, false) }}
              </template>
              <template v-else>
                {{ selectedScopeLabel }} {{ selectedSideLabel }}
                {{ formatSignedQuantity(getDisplayFlowSummary(asset.key)?.selectedQuantity, false) }}
              </template>
            </span>
          </div>
          <div v-if="(getHover(asset.key).annotations || []).length" class="hover-row annotation-hover-row">
            <span class="hover-label">anotacoes</span>
            <span class="hover-value annotation-hover-stack">
              <span
                v-for="annotation in getHover(asset.key).annotations"
                :key="`${asset.key}-hover-annot-${annotation.key}`"
                class="annotation-hover-card"
                :class="annotationToneClass(annotation.type)"
              >
                <span class="annotation-hover-head">
                  <strong>{{ annotation.label }}</strong>
                  <em>{{ annotation.shortLabel }}</em>
                </span>
                <span class="annotation-hover-body">{{ annotation.detail }}</span>
                <span class="annotation-hover-meta">
                  {{ annotation.characterization }}
                </span>
                <span class="annotation-hover-meta">
                  contratos mkt {{ formatSignedQuantity(annotation.netContracts, false) }}
                  | gringa {{ formatSignedQuantity(annotation.foreignContracts, false) }}
                  | varejo {{ formatSignedQuantity(annotation.retailContracts, false) }}
                </span>
                <span v-if="annotation.foreignBrokerSummary" class="annotation-hover-meta">
                  gringa: {{ annotation.foreignBrokerSummary }}
                </span>
                <span v-if="annotation.retailBrokerSummary" class="annotation-hover-meta">
                  varejo: {{ annotation.retailBrokerSummary }}
                </span>
                <span v-if="annotation.newsTitle || annotation.newsHeadline" class="annotation-hover-meta">
                  news: {{ annotation.newsTitle || annotation.newsHeadline }}
                </span>
                <span v-if="annotation.newsHeadline && annotation.newsTitle" class="annotation-hover-meta">
                  {{ annotation.newsHeadline }}
                </span>
              </span>
            </span>
          </div>
          <div class="hover-row">
            <span class="hover-label">players</span>
            <span class="hover-value">
              {{ getDisplayFlowSummary(asset.key)?.playerCount || 0 }} no candle
              <template v-if="getDisplayFlowSummary(asset.key)?.signedConfirmed">
                - fluxo assinado
              </template>
              <template v-else>
                - fluxo derivado do saldo 15s
              </template>
            </span>
          </div>
          <div class="hover-row">
            <span class="hover-label">filtro</span>
            <span class="hover-value">
              {{ selectedScopeLabel }} | {{ selectedSideLabel }}
              | {{ getDisplayFlowSummary(asset.key)?.playerCount || 0 }} corretoras no mapa
            </span>
          </div>
          <div
            v-if="(participantSide === 'both'
              ? ((getDisplayFlowSummary(asset.key)?.topBuyers || []).length || (getDisplayFlowSummary(asset.key)?.topSellers || []).length)
              : (getDisplayFlowSummary(asset.key)?.topPlayers || []).length)"
            class="player-split"
            :class="{ single: participantSide !== 'both' }"
          >
            <div v-if="participantSide !== 'both'" class="player-column">
              <div class="player-column-title" :class="participantSide">
                Principais {{ selectedSideLabel.toLowerCase() }} {{ selectedScopeLabel.toLowerCase() }}
              </div>
              <div class="player-table-head">
                <span>Player</span>
                <span>Qty</span>
                <span>Execucao</span>
              </div>
              <div
                v-for="player in (getDisplayFlowSummary(asset.key)?.topPlayers || [])"
                :key="`${asset.key}-${getHover(asset.key).candle?.time}-${participantScope}-${participantSide}-${player.broker_id}`"
                class="player-table-row"
              >
                <span class="player-name">{{ player.broker_name }}</span>
                <span>{{ formatSignedQuantity(participantSide === 'buy' ? (player.buyDelta || player.netDelta) : (player.sellDelta || Math.abs(player.netDelta || 0)), false) }}</span>
                <span>{{ player.executionLabel }}</span>
              </div>
            </div>
            <div v-if="participantSide === 'both'" class="player-column">
              <div class="player-column-title buy">Principais compras {{ selectedScopeLabel.toLowerCase() }}</div>
              <div class="player-table-head">
                <span>Player</span>
                <span>Qty</span>
                <span>Execucao</span>
              </div>
              <div
                v-for="player in (getDisplayFlowSummary(asset.key)?.topBuyers || [])"
                :key="`${asset.key}-${getHover(asset.key).candle?.time}-${participantScope}-buy-${player.broker_id}`"
                class="player-table-row"
              >
                <span class="player-name">{{ player.broker_name }}</span>
                <span>{{ formatSignedQuantity(player.buyDelta || player.netDelta, false) }}</span>
                <span>{{ player.executionLabel }}</span>
              </div>
            </div>
            <div v-if="participantSide === 'both'" class="player-column">
              <div class="player-column-title sell">Principais vendas {{ selectedScopeLabel.toLowerCase() }}</div>
              <div class="player-table-head">
                <span>Player</span>
                <span>Qty</span>
                <span>Execucao</span>
              </div>
              <div
                v-for="player in (getDisplayFlowSummary(asset.key)?.topSellers || [])"
                :key="`${asset.key}-${getHover(asset.key).candle?.time}-${participantScope}-sell-${player.broker_id}`"
                class="player-table-row"
              >
                <span class="player-name">{{ player.broker_name }}</span>
                <span>{{ formatSignedQuantity(player.sellDelta || Math.abs(player.netDelta || 0), false) }}</span>
                <span>{{ player.executionLabel }}</span>
              </div>
            </div>
          </div>
          <div v-else class="player-empty">
            Nenhum fluxo {{ selectedSideLabel.toLowerCase() }} de {{ selectedScopeLabel.toLowerCase() }} capturado nesse candle.
          </div>
        </div>

</template>

<script>
import { injectMacroHeatmapContext } from '../context'

export default {
  name: 'MacroQuickChartPrice',
  props: { asset: { type: Object, required: true } },
  setup() {
    return injectMacroHeatmapContext()
  },
}
</script>

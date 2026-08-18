<template>
  <div class="workbench-panel">
    <div class="scroll-container">
      <!-- Step 01: Ontology -->
      <div class="step-card" :class="{ 'active': currentPhase === 0, 'completed': currentPhase > 0 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">01</span>
            <span class="step-title">
              {{ inputMode === 'macro' ? $t('step1.snapshotSyncTitle') : $t('step1.ontologyGeneration') }}
            </span>
          </div>
          <div class="step-status">
            <span v-if="currentPhase > 0" class="badge success">
              {{ inputMode === 'macro' ? $t('step1.snapshotSynced') : $t('step1.ontologyCompleted') }}
            </span>
            <span v-else-if="currentPhase === 0" class="badge processing">
              {{ inputMode === 'macro' ? $t('step1.snapshotSyncing') : $t('step1.ontologyGenerating') }}
            </span>
            <span v-else class="badge pending">
              {{ inputMode === 'macro' ? $t('step1.snapshotPending') : $t('step1.ontologyPending') }}
            </span>
          </div>
        </div>
        
        <div class="card-content">
          <p class="api-note">
            {{ inputMode === 'macro' ? 'POST /api/macro/collect -> POST /api/macro/project/sync' : 'POST /api/graph/ontology/generate' }}
          </p>
          <p class="description">
            {{ inputMode === 'macro' ? $t('step1.modeMacroDesc') : $t('step1.ontologyDesc') }}
          </p>

          <div class="source-mode-banner" :class="{ macro: inputMode === 'macro' }">
            <span class="source-mode-label">{{ $t('step1.sourceMode') }}</span>
            <div class="source-mode-title">
              {{ inputMode === 'macro' ? $t('step1.modeMacro') : $t('step1.modeDocuments') }}
            </div>
            <div class="source-mode-text">
              {{ inputMode === 'macro' ? $t('step1.modeMacroSummary') : $t('step1.modeDocumentsDesc') }}
            </div>
            <div v-if="inputMode === 'macro'" class="source-mode-pills">
              <span class="source-pill">Bleu WS</span>
              <span class="source-pill">WINJ26</span>
              <span class="source-pill">WDOK26</span>
              <span class="source-pill">DI Curta</span>
              <span class="source-pill">DI Longa</span>
            </div>
          </div>

          <!-- Loading / Progress -->
          <div v-if="currentPhase === 0 && ontologyProgress" class="progress-section">
            <div class="spinner-sm"></div>
            <span>{{ ontologyProgress.message || $t('step1.analyzingDocs') }}</span>
          </div>

          <!-- Detail Overlay -->
          <div v-if="selectedOntologyItem" class="ontology-detail-overlay">
            <div class="detail-header">
               <div class="detail-title-group">
                  <span class="detail-type-badge">{{ selectedOntologyItem.itemType === 'entity' ? 'ENTITY' : 'RELATION' }}</span>
                  <span class="detail-name">{{ selectedOntologyItem.name }}</span>
               </div>
               <button class="close-btn" @click="selectedOntologyItem = null">×</button>
            </div>
            <div class="detail-body">
               <div class="detail-desc">{{ selectedOntologyItem.description }}</div>
               
               <!-- Attributes -->
               <div class="detail-section" v-if="selectedOntologyItem.attributes?.length">
                  <span class="section-label">ATTRIBUTES</span>
                  <div class="attr-list">
                     <div v-for="attr in selectedOntologyItem.attributes" :key="attr.name" class="attr-item">
                        <span class="attr-name">{{ attr.name }}</span>
                        <span class="attr-type">({{ attr.type }})</span>
                        <span class="attr-desc">{{ attr.description }}</span>
                     </div>
                  </div>
               </div>

               <!-- Examples (Entity) -->
               <div class="detail-section" v-if="selectedOntologyItem.examples?.length">
                  <span class="section-label">EXAMPLES</span>
                  <div class="example-list">
                     <span v-for="ex in selectedOntologyItem.examples" :key="ex" class="example-tag">{{ ex }}</span>
                  </div>
               </div>

               <!-- Source/Target (Relation) -->
               <div class="detail-section" v-if="selectedOntologyItem.source_targets?.length">
                  <span class="section-label">CONNECTIONS</span>
                  <div class="conn-list">
                     <div v-for="(conn, idx) in selectedOntologyItem.source_targets" :key="idx" class="conn-item">
                        <span class="conn-node">{{ conn.source }}</span>
                        <span class="conn-arrow">→</span>
                        <span class="conn-node">{{ conn.target }}</span>
                     </div>
                  </div>
               </div>
            </div>
          </div>

          <!-- Generated Entity Tags -->
          <div v-if="projectData?.ontology?.entity_types" class="tags-container" :class="{ 'dimmed': selectedOntologyItem }">
            <span class="tag-label">GENERATED ENTITY TYPES</span>
            <div class="tags-list">
              <span 
                v-for="entity in projectData.ontology.entity_types" 
                :key="entity.name" 
                class="entity-tag clickable"
                @click="selectOntologyItem(entity, 'entity')"
              >
                {{ entity.name }}
              </span>
            </div>
          </div>

          <!-- Generated Relation Tags -->
          <div v-if="projectData?.ontology?.edge_types" class="tags-container" :class="{ 'dimmed': selectedOntologyItem }">
            <span class="tag-label">GENERATED RELATION TYPES</span>
            <div class="tags-list">
              <span 
                v-for="rel in projectData.ontology.edge_types" 
                :key="rel.name" 
                class="entity-tag clickable"
                @click="selectOntologyItem(rel, 'relation')"
              >
                {{ rel.name }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Step 02: Graph Build -->
      <div class="step-card" :class="{ 'active': currentPhase === 1, 'completed': currentPhase > 1 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">02</span>
            <span class="step-title">{{ $t('step1.graphRagBuild') }}</span>
          </div>
          <div class="step-status">
            <span v-if="currentPhase > 1" class="badge success">{{ $t('step1.ontologyCompleted') }}</span>
            <span v-else-if="currentPhase === 1" class="badge processing">{{ buildProgress?.progress || 0 }}%</span>
            <span v-else class="badge pending">{{ $t('step1.ontologyPending') }}</span>
          </div>
        </div>

        <div class="card-content">
          <p class="api-note">POST /api/graph/build</p>
          <p class="description">
            {{ $t('step1.graphRagDesc') }}
          </p>
          
          <!-- Stats Cards -->
          <div class="stats-grid">
            <div class="stat-card">
              <span class="stat-value">{{ graphStats.nodes }}</span>
              <span class="stat-label">{{ $t('step1.entityNodes') }}</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ graphStats.edges }}</span>
              <span class="stat-label">{{ $t('step1.relationEdges') }}</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ graphStats.types }}</span>
              <span class="stat-label">{{ $t('step1.schemaTypes') }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Step 03: Complete -->
      <div class="step-card" :class="{ 'active': currentPhase === 2, 'completed': currentPhase >= 2 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">03</span>
            <span class="step-title">{{ $t('step1.buildComplete') }}</span>
          </div>
          <div class="step-status">
            <span v-if="currentPhase >= 2" class="badge accent">{{ $t('step1.inProgress') }}</span>
          </div>
        </div>
        
        <div class="card-content">
          <p class="api-note">POST /api/simulation/create</p>
          <p class="description">{{ $t('step1.buildCompleteDesc') }}</p>
          <button 
            class="action-btn" 
            :disabled="currentPhase < 2 || creatingSimulation"
            @click="handleEnterEnvSetup"
          >
            <span v-if="creatingSimulation" class="spinner-sm"></span>
            {{ creatingSimulation ? $t('step1.creating') : $t('step1.enterEnvSetup') + ' ➝' }}
          </button>
        </div>
      </div>

      <div v-if="showMacroDashboard" class="step-card macro-trendboard" :class="{ active: !!focusedTrend || !!focusedDriver?.driver }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">04</span>
            <span class="step-title">Macro Trendboard</span>
          </div>
          <div class="step-status">
            <span v-if="macroTrendsLoading" class="badge processing">LOADING</span>
            <span v-else class="badge success">{{ macroTrends.length }} TRENDS</span>
          </div>
        </div>

        <div class="card-content">
          <p class="api-note">GET /api/macro/overview -> GET /api/macro/drivers -> GET /api/macro/trends</p>
          <p class="description">
            News and market flows are grouped into impact drivers first. Trends then inherit that state so simulation starts from a live market narrative instead of isolated headlines.
          </p>

          <div class="trendboard-actions">
            <button class="action-btn secondary-inline" :disabled="macroTrendsLoading || macroOverviewLoading || macroDriversLoading" @click="loadMacroDashboard(true)">
              {{ macroTrendsLoading || macroOverviewLoading || macroDriversLoading ? 'Refreshing...' : 'Refresh Macro Board' }}
            </button>
            <button class="action-btn secondary-inline" @click="openMacroHeatmap">
              Open participant heatmap
            </button>
          </div>

          <div class="collector-status-banner" :class="collectorStatusTone">
            <span class="collector-status-dot"></span>
            <span>{{ collectorStatusLabel }}</span>
          </div>

          <div v-if="macroThermometerError" class="trendboard-empty error">
            {{ macroThermometerError }}
          </div>

          <div v-else-if="macroThermometerLoading && !macroThermometer" class="trendboard-empty">
            Building the macro thermometer from news flow, flow concentration and intraday microstructure.
          </div>

          <div v-else-if="normalizedMacroThermometer" class="thermometer-card">
            <div class="thermometer-top">
              <div>
                <div class="overview-title">Macro Thermometer</div>
                <div class="overview-subtitle">
                  {{ normalizedMacroThermometer.ai_summary?.market_commentary || 'Awaiting the next usable macro sequence to populate the thermometer narrative.' }}
                </div>
              </div>
              <div class="thermometer-top-badges">
                <span class="trend-bias" :class="normalizedMacroThermometer.ai_summary?.action_bias || thermometerLatest.general?.bias">
                  {{ normalizedMacroThermometer.ai_summary?.action_bias || thermometerLatest.general?.bias || 'watch' }}
                </span>
                <span class="focus-badge muted">{{ normalizedMacroThermometer.ai_summary?.probability || thermometerLatest.general?.probability || 0 }}%</span>
              </div>
            </div>

            <div class="thermometer-kpi-grid">
              <div v-for="item in [
                thermometerLatest.general,
                thermometerLatest.credit,
                thermometerLatest.equity,
                thermometerLatest.fx
              ]" :key="item?.bucket" class="thermometer-kpi-card">
                <div class="thermometer-kpi-top">
                  <span class="thermometer-kpi-label">{{ item?.bucket || 'general' }}</span>
                  <span class="trend-bias" :class="item?.bias">{{ item?.marker || 'neutral' }}</span>
                </div>
                <div class="thermometer-kpi-value">{{ item?.score ?? 0 }}</div>
                <div class="thermometer-bar-track">
                  <div class="thermometer-bar-fill" :class="item?.bias" :style="scoreBarStyle(item?.score)"></div>
                </div>
              </div>
            </div>

            <div class="thermometer-chart-panel">
              <div class="thermometer-chart-top">
                <div class="focus-section-title">Intraday Risk Path</div>
                <div class="thermometer-chart-meta">
                  <span>{{ thermometerChart.timeRangeLabel }}</span>
                  <span>{{ thermometerTimeline.length }} events</span>
                </div>
              </div>
              <div class="thermometer-chart-stage">
                <div v-if="!thermometerTimeline.length" class="focus-loading">
                  Awaiting macro events to draw the thermometer path.
                </div>
                <svg
                  v-else
                  :viewBox="`0 0 ${thermometerChart.width} ${thermometerChart.height}`"
                  class="thermometer-chart"
                  @mouseleave="hoveredThermometerEventId = ''"
                >
                  <g v-for="tick in thermometerChart.yTicks" :key="`y-${tick.value}`">
                    <line
                      :x1="thermometerChart.plotLeft"
                      :y1="tick.y"
                      :x2="thermometerChart.plotRight"
                      :y2="tick.y"
                      class="thermometer-grid-line"
                      :class="{ baseline: tick.value === 0 }"
                    />
                    <text
                      :x="thermometerChart.plotLeft - 10"
                      :y="tick.y + 4"
                      class="thermometer-axis-label"
                    >
                      {{ tick.label }}
                    </text>
                  </g>

                  <g v-for="tick in thermometerChart.xTicks" :key="`x-${tick.label}-${tick.x}`">
                    <line
                      :x1="tick.x"
                      :y1="thermometerChart.plotTop"
                      :x2="tick.x"
                      :y2="thermometerChart.plotBottom"
                      class="thermometer-grid-line vertical"
                    />
                    <text
                      :x="tick.x"
                      :y="thermometerChart.plotBottom + 18"
                      class="thermometer-axis-label time"
                      text-anchor="middle"
                    >
                      {{ tick.label }}
                    </text>
                  </g>

                  <g v-for="series in thermometerSeriesConfig" :key="series.key">
                    <polyline
                      v-if="isThermometerSeriesVisible(series.key)"
                      :points="linePoints[series.key]"
                      class="thermometer-line"
                      :class="series.key"
                    />
                  </g>

                  <line
                    v-if="activeThermometerEventPin"
                    :x1="activeThermometerEventPin.x"
                    :y1="thermometerChart.plotTop"
                    :x2="activeThermometerEventPin.x"
                    :y2="thermometerChart.plotBottom"
                    class="thermometer-event-guide"
                  />

                  <g
                    v-for="pin in thermometerChart.eventPins"
                    :key="pin.event_id"
                    class="thermometer-event-pin"
                    :class="{
                      selected: activeThermometerEventId === pin.event_id,
                      muted: activeThermometerEventId && activeThermometerEventId !== pin.event_id
                    }"
                    @mouseenter="hoveredThermometerEventId = pin.event_id"
                    @focus="hoveredThermometerEventId = pin.event_id"
                    @blur="hoveredThermometerEventId = ''"
                    @click="selectThermometerEvent(pin.raw)"
                  >
                    <line
                      :x1="pin.x"
                      :y1="pin.y + 9"
                      :x2="pin.x"
                      :y2="thermometerChart.plotBottom"
                      class="thermometer-pin-stem"
                    />
                    <circle
                      :cx="pin.x"
                      :cy="pin.y"
                      :r="activeThermometerEventId === pin.event_id ? 6.2 : 4.4"
                      class="thermometer-pin-core"
                      :class="pin.biasClass"
                    />
                    <circle
                      :cx="pin.x"
                      :cy="pin.y"
                      :r="activeThermometerEventId === pin.event_id ? 10 : 8"
                      class="thermometer-pin-halo"
                    />
                  </g>
                </svg>
              </div>
              <div v-if="activeThermometerEvent" class="thermometer-event-detail">
                <div class="thermometer-event-detail-top">
                  <span class="trend-kind">{{ formatTime(activeThermometerEvent.time) }}</span>
                  <span
                    class="trend-bias"
                    :class="activeThermometerEvent.risk_marker?.general === 'risk-on' ? 'buy' : activeThermometerEvent.risk_marker?.general === 'risk-off' ? 'sell' : 'watch'"
                  >
                    {{ activeThermometerEvent.risk_marker?.general || 'neutral' }}
                  </span>
                </div>
                <div class="thermometer-event-detail-title">{{ activeThermometerEvent.headline }}</div>
                <div class="thermometer-event-detail-meta">
                  <span>{{ activeThermometerEvent.posted_by || 'feed' }}</span>
                  <span v-if="activeThermometerEvent.driver_title">{{ activeThermometerEvent.driver_title }}</span>
                  <span>impact {{ activeThermometerEvent.impact_score ?? 0 }}</span>
                  <span>{{ activeThermometerEvent.scenario_classification || 'secondary_echo' }}</span>
                  <span>w {{ activeThermometerEvent.importance_weight ?? 0 }}</span>
                  <span>g {{ activeThermometerEvent.scores?.general ?? 0 }}</span>
                  <span>cr {{ activeThermometerEvent.scores?.credit ?? 0 }}</span>
                  <span>eq {{ activeThermometerEvent.scores?.equity ?? 0 }}</span>
                  <span>fx {{ activeThermometerEvent.scores?.fx ?? 0 }}</span>
                </div>
                <div
                  v-if="activeThermometerEvent.recommended_action || activeThermometerEvent.market_regime || activeThermometerEvent.agent_summary || activeThermometerEvent.macro_explanation || activeThermometerEvent.importance_reason || activeThermometerEvent.expected_impact_reason || activeThermometerEvent.probable_playbook"
                  class="thermometer-event-audit"
                >
                  <div class="thermometer-event-detail-meta">
                    <span>agent {{ activeThermometerEvent.recommended_action || 'watch' }}</span>
                    <span>{{ activeThermometerEvent.market_regime || 'intraday macro reaction' }}</span>
                    <span>driver {{ activeThermometerEvent.driver_importance_score ?? 0 }}</span>
                    <span>expected {{ activeThermometerEvent.expected_impact_score ?? 0 }}</span>
                    <span>
                      consensus {{ activeThermometerEvent.directional_consensus_bias || 'watch' }}
                      | {{ activeThermometerEvent.directional_consensus_confidence ?? 0 }}
                    </span>
                  </div>
                  <div class="thermometer-event-audit-text">
                    <div v-if="activeThermometerEvent.macro_explanation" class="thermometer-timeline-audit-line">
                      <strong>Explicacao:</strong> {{ activeThermometerEvent.macro_explanation }}
                    </div>
                    <div v-if="activeThermometerEvent.driver_summary" class="thermometer-timeline-audit-line">
                      <strong>Resumo:</strong> {{ activeThermometerEvent.driver_summary }}
                    </div>
                    <div v-if="activeThermometerEvent.importance_reason" class="thermometer-timeline-audit-line">
                      <strong>Razao do score:</strong> {{ activeThermometerEvent.importance_reason }}
                    </div>
                    <div v-if="activeThermometerEvent.expected_impact_reason" class="thermometer-timeline-audit-line">
                      <strong>Razao do impacto:</strong> {{ activeThermometerEvent.expected_impact_reason }}
                    </div>
                    <div v-if="activeThermometerEvent.directional_consensus_reason" class="thermometer-timeline-audit-line">
                      <strong>Consenso:</strong> {{ activeThermometerEvent.directional_consensus_reason }}
                    </div>
                    <div v-if="activeThermometerEvent.probable_playbook" class="thermometer-timeline-audit-line">
                      <strong>Playbook:</strong> {{ activeThermometerEvent.probable_playbook }}
                    </div>
                  </div>
                </div>
              </div>
              <div class="thermometer-legend">
                <button
                  v-for="series in thermometerSeriesConfig"
                  :key="series.key"
                  type="button"
                  class="legend-item legend-button"
                  :class="{ inactive: !isThermometerSeriesVisible(series.key) }"
                  @click="toggleThermometerSeries(series.key)"
                >
                  <span class="legend-dot" :class="series.key"></span>
                  {{ series.label }}
                </button>
              </div>
            </div>

            <div class="thermometer-grid">
              <div class="overview-panel">
                <div class="focus-section-title">Timeline</div>
                <div class="thermometer-timeline-list">
                  <div
                    v-for="item in thermometerTimeline"
                    :key="item.event_id"
                    class="thermometer-timeline-item"
                    :class="{ selected: activeThermometerEventId === item.event_id }"
                    @mouseenter="hoveredThermometerEventId = item.event_id"
                    @mouseleave="hoveredThermometerEventId = ''"
                    @click="selectThermometerEvent(item)"
                  >
                    <div class="thermometer-timeline-top">
                      <span class="trend-kind">{{ formatTime(item.time) }}</span>
                      <span class="trend-bias" :class="item.risk_marker?.general === 'risk-on' ? 'buy' : item.risk_marker?.general === 'risk-off' ? 'sell' : 'watch'">
                        {{ item.risk_marker?.general || 'neutral' }}
                      </span>
                    </div>
                    <div class="thermometer-timeline-title">{{ item.headline }}</div>
                    <div class="thermometer-timeline-meta">
                      <span>{{ item.posted_by || 'feed' }}</span>
                      <span>g {{ item.scores?.general ?? 0 }}</span>
                      <span>cr {{ item.scores?.credit ?? 0 }}</span>
                      <span>eq {{ item.scores?.equity ?? 0 }}</span>
                      <span>fx {{ item.scores?.fx ?? 0 }}</span>
                    </div>
                    <div v-if="item.driver_title || item.impact_score || item.recommended_action || item.agent_summary || item.macro_explanation || item.importance_reason || item.expected_impact_reason || item.probable_playbook" class="thermometer-timeline-audit">
                      <div class="thermometer-timeline-meta">
                        <span v-if="item.driver_title">{{ item.driver_title }}</span>
                        <span>impact {{ item.impact_score ?? 0 }}</span>
                        <span>{{ item.scenario_classification || 'secondary_echo' }}</span>
                        <span>w {{ item.importance_weight ?? 0 }}</span>
                      </div>
                      <div class="thermometer-timeline-meta">
                        <span>agent {{ item.recommended_action || 'watch' }}</span>
                        <span>{{ item.market_regime || 'intraday macro reaction' }}</span>
                        <span>driver {{ item.driver_importance_score ?? 0 }}</span>
                        <span>expected {{ item.expected_impact_score ?? 0 }}</span>
                        <span>
                          consensus {{ item.directional_consensus_bias || 'watch' }}
                          | {{ item.directional_consensus_confidence ?? 0 }}
                        </span>
                      </div>
                      <div class="thermometer-timeline-audit-text">
                        <div v-if="item.macro_explanation" class="thermometer-timeline-audit-line">
                          <strong>Explicacao:</strong> {{ item.macro_explanation }}
                        </div>
                        <div v-if="item.driver_summary" class="thermometer-timeline-audit-line">
                          <strong>Resumo:</strong> {{ item.driver_summary }}
                        </div>
                        <div v-if="item.importance_reason" class="thermometer-timeline-audit-line">
                          <strong>Razao do score:</strong> {{ item.importance_reason }}
                        </div>
                        <div v-if="item.expected_impact_reason" class="thermometer-timeline-audit-line">
                          <strong>Razao do impacto:</strong> {{ item.expected_impact_reason }}
                        </div>
                        <div v-if="item.directional_consensus_reason" class="thermometer-timeline-audit-line">
                          <strong>Consenso:</strong> {{ item.directional_consensus_reason }}
                        </div>
                        <div v-if="item.probable_playbook" class="thermometer-timeline-audit-line">
                          <strong>Playbook:</strong> {{ item.probable_playbook }}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div class="overview-panel">
                <div class="focus-section-title">Entity Evolution</div>
                <div class="thermometer-entity-list">
                  <div v-for="entity in thermometerEntityViews" :key="entity.slug" class="thermometer-entity-card">
                    <div class="thermometer-entity-top">
                      <span class="overview-participant-name">{{ entity.label }}</span>
                      <span class="trend-bias" :class="entity.current_action">{{ entity.current_action }}</span>
                    </div>
                    <div class="thermometer-entity-meta">
                      <span>{{ entity.risk_marker }}</span>
                      <span>{{ entity.probability }}%</span>
                      <span>{{ entity.focus_asset || 'macro basket' }}</span>
                    </div>
                    <p class="overview-participant-comment">{{ entity.what_they_would_do }}</p>
                    <div v-if="entity.trade_plan" class="thermometer-trade-plan">
                      <span>entry {{ entity.trade_plan.entry }}</span>
                      <span>take {{ entity.trade_plan.take }}</span>
                      <span>stop {{ entity.trade_plan.stop }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div class="thermometer-ai-strip">
              <p>{{ macroThermometer.ai_summary?.execution_commentary }}</p>
            </div>
          </div>

          <div v-else class="trendboard-empty">
            Macro thermometer is waiting for the first payload.
          </div>

          <div v-if="macroCrossAssetError" class="trendboard-empty error">
            {{ macroCrossAssetError }}
          </div>

          <div v-else-if="macroCrossAssetLoading && !macroCrossAsset" class="trendboard-empty">
            Building the cross-asset engine from credit, equity, commodity, FX and rates reactions.
          </div>

          <div v-else-if="macroCrossAsset" class="cross-asset-card">
            <div class="thermometer-top">
              <div>
                <div class="overview-title">Cross-Asset Engine</div>
                <div class="overview-subtitle">
                  {{ macroCrossAsset.ai_panorama?.market_commentary }}
                </div>
              </div>
              <div class="thermometer-top-badges">
                <span class="trend-bias" :class="macroCrossAsset.ai_panorama?.action_bias || macroCrossAssetSummary.overall?.bias">
                  {{ macroCrossAsset.ai_panorama?.action_bias || macroCrossAssetSummary.overall?.bias || 'watch' }}
                </span>
                <span class="focus-badge muted">{{ macroCrossAsset.ai_panorama?.probability || macroCrossAssetSummary.overall?.probability || 0 }}%</span>
              </div>
            </div>

            <div class="thermometer-kpi-grid">
              <div
                v-for="item in [
                  macroCrossAssetSummary.overall,
                  macroCrossAssetSummary.credit,
                  macroCrossAssetSummary.equity,
                  macroCrossAssetSummary.commodity,
                  macroCrossAssetSummary.fx,
                  macroCrossAssetSummary.rates
                ]"
                :key="item?.bucket"
                class="thermometer-kpi-card"
              >
                <div class="thermometer-kpi-top">
                  <span class="thermometer-kpi-label">{{ item?.bucket || 'general' }}</span>
                  <span class="trend-bias" :class="item?.bias">{{ item?.marker || 'mixed' }}</span>
                </div>
                <div class="thermometer-kpi-value">{{ item?.score ?? 0 }}</div>
                <div class="thermometer-bar-track">
                  <div class="thermometer-bar-fill" :class="item?.bias" :style="scoreBarStyle(item?.score)"></div>
                </div>
              </div>
            </div>

            <div class="thermometer-chart-panel">
              <div class="thermometer-chart-top">
                <div class="focus-section-title">Cross-Asset Evolution</div>
                <div class="thermometer-chart-meta">
                  <span>{{ crossAssetChart.timeRangeLabel }}</span>
                  <span>{{ macroCrossAssetTimeline.length }} drivers</span>
                </div>
              </div>
              <div class="thermometer-chart-stage">
                <svg
                  :viewBox="`0 0 ${crossAssetChart.width} ${crossAssetChart.height}`"
                  class="thermometer-chart"
                  @mouseleave="hoveredCrossAssetDriverId = ''"
                >
                  <g v-for="tick in crossAssetChart.yTicks" :key="`cross-y-${tick.value}`">
                    <line
                      :x1="crossAssetChart.plotLeft"
                      :y1="tick.y"
                      :x2="crossAssetChart.plotRight"
                      :y2="tick.y"
                      class="thermometer-grid-line"
                      :class="{ baseline: tick.value === 0 }"
                    />
                    <text
                      :x="crossAssetChart.plotLeft - 10"
                      :y="tick.y + 4"
                      class="thermometer-axis-label"
                    >
                      {{ tick.label }}
                    </text>
                  </g>

                  <g v-for="tick in crossAssetChart.xTicks" :key="`cross-x-${tick.label}-${tick.x}`">
                    <line
                      :x1="tick.x"
                      :y1="crossAssetChart.plotTop"
                      :x2="tick.x"
                      :y2="crossAssetChart.plotBottom"
                      class="thermometer-grid-line vertical"
                    />
                    <text
                      :x="tick.x"
                      :y="crossAssetChart.plotBottom + 18"
                      class="thermometer-axis-label time"
                      text-anchor="middle"
                    >
                      {{ tick.label }}
                    </text>
                  </g>

                  <g v-for="series in crossAssetSeriesConfig" :key="series.key">
                    <polyline
                      v-if="isCrossAssetSeriesVisible(series.key)"
                      :points="crossAssetLinePoints[series.key]"
                      class="thermometer-line"
                      :class="series.key"
                    />
                  </g>

                  <line
                    v-if="activeCrossAssetPin"
                    :x1="activeCrossAssetPin.x"
                    :y1="crossAssetChart.plotTop"
                    :x2="activeCrossAssetPin.x"
                    :y2="crossAssetChart.plotBottom"
                    class="thermometer-event-guide"
                  />

                  <g
                    v-for="pin in crossAssetChart.eventPins"
                    :key="pin.driver_id"
                    class="thermometer-event-pin"
                    :class="{
                      selected: activeCrossAssetDriverId === pin.driver_id,
                      muted: activeCrossAssetDriverId && activeCrossAssetDriverId !== pin.driver_id
                    }"
                    @mouseenter="hoveredCrossAssetDriverId = pin.driver_id"
                    @focus="hoveredCrossAssetDriverId = pin.driver_id"
                    @blur="hoveredCrossAssetDriverId = ''"
                    @click="selectCrossAssetDriver(pin.driver_id)"
                  >
                    <line
                      :x1="pin.x"
                      :y1="pin.y + 9"
                      :x2="pin.x"
                      :y2="crossAssetChart.plotBottom"
                      class="thermometer-pin-stem"
                    />
                    <circle
                      :cx="pin.x"
                      :cy="pin.y"
                      :r="activeCrossAssetDriverId === pin.driver_id ? 6.2 : 4.4"
                      class="thermometer-pin-core"
                      :class="pin.biasClass"
                    />
                    <circle
                      :cx="pin.x"
                      :cy="pin.y"
                      :r="activeCrossAssetDriverId === pin.driver_id ? 10 : 8"
                      class="thermometer-pin-halo"
                    />
                  </g>
                </svg>
              </div>
              <div v-if="activeCrossAssetEvent" class="thermometer-event-detail">
                <div class="thermometer-event-detail-top">
                  <span class="trend-kind">{{ formatTime(activeCrossAssetEvent.time) }}</span>
                  <span class="trend-bias" :class="activeCrossAssetEvent.scores?.general > 6 ? 'buy' : activeCrossAssetEvent.scores?.general < -6 ? 'sell' : 'watch'">
                    {{ activeCrossAssetEvent.regime || 'mixed' }}
                  </span>
                </div>
                <div class="thermometer-event-detail-title">{{ activeCrossAssetEvent.title }}</div>
                <div class="thermometer-event-detail-meta">
                  <span>confirm {{ activeCrossAssetEvent.confirmation_ratio ?? 0 }}%</span>
                  <span>fake {{ activeCrossAssetEvent.fake_move_risk ?? 0 }}%</span>
                  <span>absorption {{ activeCrossAssetEvent.absorption_signal ?? 0 }}%</span>
                </div>
              </div>
              <div class="thermometer-legend">
                <button
                  v-for="series in crossAssetSeriesConfig"
                  :key="series.key"
                  type="button"
                  class="legend-item legend-button"
                  :class="{ inactive: !isCrossAssetSeriesVisible(series.key) }"
                  @click="toggleCrossAssetSeries(series.key)"
                >
                  <span class="legend-dot" :class="series.key"></span>
                  {{ series.label }}
                </button>
              </div>
            </div>

            <div class="cross-asset-grid">
              <div class="overview-panel">
                <div class="focus-section-title">Selected Driver Matrix</div>
                <div v-if="!crossAssetSelectedDriver" class="mini-empty-state">
                  Select a driver on the chart to inspect how each bucket reacted.
                </div>
                <template v-else>
                  <div class="overview-summary-top">
                    <div>
                      <div class="overview-title">{{ crossAssetSelectedDriver.title }}</div>
                      <div class="overview-subtitle">
                        {{ (crossAssetSelectedDriver.insights || [])[0]?.message || 'Cross-asset reaction matrix loaded.' }}
                      </div>
                    </div>
                    <div class="overview-badges">
                      <span class="trend-bias" :class="crossAssetSelectedDriver.general_bias">{{ crossAssetSelectedDriver.general_bias }}</span>
                      <span class="focus-badge muted">{{ crossAssetSelectedDriver.confidence }}%</span>
                    </div>
                  </div>
                  <div class="cross-asset-bucket-grid">
                    <div
                      v-for="bucket in ['credit', 'equity', 'commodity', 'fx', 'rates']"
                      :key="bucket"
                      class="cross-asset-bucket-card"
                    >
                      <div class="thermometer-kpi-top">
                        <span class="thermometer-kpi-label">{{ bucket }}</span>
                        <span class="trend-bias" :class="crossAssetSelectedDriver.bucket_reactions?.[bucket]?.bias">
                          {{ crossAssetSelectedDriver.bucket_reactions?.[bucket]?.strength || 'missing' }}
                        </span>
                      </div>
                      <div class="thermometer-kpi-value">{{ crossAssetSelectedDriver.bucket_reactions?.[bucket]?.score ?? 0 }}</div>
                      <div class="cross-asset-leaders">
                        <span
                          v-for="leader in (crossAssetSelectedDriver.bucket_reactions?.[bucket]?.leaders || []).slice(0, 2)"
                          :key="`${bucket}-${leader.asset}`"
                          class="focus-chip"
                        >
                          {{ leader.label || leader.asset }} {{ leader.delta_pct ?? 0 }}%
                        </span>
                      </div>
                    </div>
                  </div>
                  <div class="cross-asset-mini-meta">
                    <span>confirmation {{ crossAssetSelectedDriver.cross_signals?.confirmation_ratio ?? 0 }}%</span>
                    <span>fake move {{ crossAssetSelectedDriver.cross_signals?.fake_move_risk ?? 0 }}%</span>
                    <span>absorption {{ crossAssetSelectedDriver.cross_signals?.absorption_signal ?? 0 }}%</span>
                    <span>{{ crossAssetSelectedDriver.participant_context?.alignment || 'light' }} players</span>
                  </div>
                </template>
              </div>

              <div class="overview-panel">
                <div class="focus-section-title">Insight Stream</div>
                <div class="cross-asset-insight-list">
                  <button
                    v-for="insight in macroCrossAssetInsights"
                    :key="`${insight.driver_id}-${insight.title}`"
                    type="button"
                    class="cross-asset-insight-item"
                    @click="selectCrossAssetDriver(insight.driver_id)"
                  >
                    <div class="thermometer-timeline-top">
                      <span class="trend-kind">{{ insight.kind }}</span>
                      <span class="trend-bias" :class="insight.bias">{{ insight.bias }}</span>
                    </div>
                    <div class="thermometer-timeline-title">{{ insight.title }}</div>
                    <div class="thermometer-timeline-meta">
                      <span>{{ insight.driver_title }}</span>
                      <span>{{ insight.confidence }}%</span>
                    </div>
                    <p class="overview-participant-comment">{{ insight.message }}</p>
                  </button>
                </div>
              </div>

              <div class="overview-panel">
                <div class="focus-section-title">Entity Lenses</div>
                <div class="thermometer-entity-list">
                  <div v-for="entity in macroCrossAssetEntityViews" :key="entity.slug" class="thermometer-entity-card">
                    <div class="thermometer-entity-top">
                      <span class="overview-participant-name">{{ entity.label }}</span>
                      <span class="trend-bias" :class="entity.current_action">{{ entity.current_action }}</span>
                    </div>
                    <div class="thermometer-entity-meta">
                      <span>{{ entity.style }}</span>
                      <span>{{ entity.probability }}%</span>
                    </div>
                    <p class="overview-participant-comment">{{ entity.what_they_would_do }}</p>
                  </div>
                </div>
              </div>
            </div>

            <div class="thermometer-ai-strip">
              <p>{{ macroCrossAsset.ai_panorama?.divergence_commentary }}</p>
              <p>{{ macroCrossAsset.ai_panorama?.entity_commentary }}</p>
            </div>
          </div>

          <div v-if="macroOverviewError" class="trendboard-empty error">
            {{ macroOverviewError }}
          </div>

          <div v-else-if="macroOverviewLoading && !macroOverview" class="trendboard-empty">
            Compiling the market overview from flows, prices, volume, and news.
          </div>

          <div v-else-if="macroOverview" class="macro-overview-grid">
            <div class="overview-panel overview-summary-panel">
              <div class="overview-summary-top">
                <div>
                  <div class="overview-title">Market Overview</div>
                  <div class="overview-subtitle">{{ macroOverview.overall?.summary }}</div>
                </div>
                <div class="overview-badges">
                  <span class="trend-bias" :class="macroOverview.overall?.market_bias">{{ macroOverview.overall?.market_bias || 'watch' }}</span>
                  <span class="focus-badge muted">{{ macroOverview.overall?.implicit_sentiment || 'mixed' }}</span>
                </div>
              </div>

              <div class="overview-kpi-grid">
                <div class="overview-kpi">
                  <span class="overview-kpi-label">Sentiment Shift</span>
                  <span class="overview-kpi-value">{{ macroOverview.overall?.sentiment_shift || 'stable' }}</span>
                </div>
                <div class="overview-kpi">
                  <span class="overview-kpi-label">AI Bias</span>
                  <span class="overview-kpi-value">{{ macroOverview.ai_commentary?.action_bias || macroOverview.overall?.market_bias || 'watch' }}</span>
                </div>
                <div class="overview-kpi">
                  <span class="overview-kpi-label">Volume Pace</span>
                  <span class="overview-kpi-value">{{ macroOverview.asset_behavior?.volume?.pace_label || 'unknown' }}</span>
                </div>
                <div class="overview-kpi">
                  <span class="overview-kpi-label">Overview Confidence</span>
                  <span class="overview-kpi-value">{{ macroOverview.ai_commentary?.confidence || '-' }}%</span>
                </div>
              </div>

              <div class="overview-ai-block">
                <p>{{ macroOverview.ai_commentary?.market_commentary }}</p>
                <p>{{ macroOverview.ai_commentary?.sentiment_change_commentary }}</p>
                <p>{{ macroOverview.ai_commentary?.asset_volume_commentary }}</p>
                <p>{{ macroOverview.ai_commentary?.news_commentary }}</p>
              </div>
            </div>

            <div class="overview-panel">
              <div class="focus-section-title">Asset + Volume Behavior</div>
              <div class="overview-asset-list">
                <div v-for="asset in (macroOverview.asset_behavior?.contracts || []).slice(0, 6)" :key="asset.ticker" class="overview-asset-item">
                  <div class="overview-asset-top">
                    <span class="overview-asset-name">{{ asset.ticker }}</span>
                    <span class="trend-bias" :class="asset.market_bias">{{ asset.market_bias }}</span>
                  </div>
                  <div class="overview-asset-meta">
                    <span>{{ asset.bucket_label }}</span>
                    <span>{{ asset.net_change_pct_5m ?? '-' }}%</span>
                    <span>vol {{ asset.volume_5m ?? '-' }}</span>
                    <span>x{{ asset.volume_ratio_5m ? asset.volume_ratio_5m.toFixed(2) : '1.00' }}</span>
                  </div>
                </div>
              </div>
            </div>

            <div class="overview-panel">
              <div class="focus-section-title">Bloomberg Reference Basket</div>
              <div class="overview-asset-list">
                <div v-for="asset in (macroOverview.asset_behavior?.reference_assets || []).slice(0, 12)" :key="asset.ticker" class="overview-asset-item">
                  <div class="overview-asset-top">
                    <span class="overview-asset-name">{{ asset.label || asset.ticker }}</span>
                    <span class="trend-bias" :class="asset.market_bias">{{ asset.market_bias }}</span>
                  </div>
                  <div class="overview-asset-meta">
                    <span>{{ asset.ticker }}</span>
                    <span>{{ asset.bucket || asset.category || 'reference' }}</span>
                    <span>{{ asset.change_percent ?? '-' }}%</span>
                    <span>{{ asset.ok ? 'desktop ok' : 'awaiting data' }}</span>
                  </div>
                  <p class="overview-news-summary">{{ asset.summary }}</p>
                </div>
              </div>
            </div>

            <div class="overview-panel">
              <div class="focus-section-title">Participant Sentiment</div>
              <div class="overview-participant-list">
                <div v-for="participant in (macroOverview.participants?.items || []).slice(0, 8)" :key="participant.broker_name" class="overview-participant-item">
                  <div class="overview-participant-top">
                    <span class="overview-participant-name">{{ participant.broker_name }}</span>
                    <span class="trend-bias" :class="participant.market_bias">{{ participant.market_bias }}</span>
                  </div>
                  <div class="overview-participant-meta">
                    <span>{{ participant.implicit_sentiment }}</span>
                    <span>activity {{ participant.activity_score }}</span>
                  </div>
                  <p class="overview-participant-comment">{{ participant.general_comment }}</p>
                </div>
              </div>
            </div>

            <div class="overview-panel">
              <div class="focus-section-title">Most Impactful News Today</div>
              <div class="overview-news-list">
                <div v-for="item in macroOverview.impactful_news || []" :key="item.event_id" class="overview-news-item">
                  <div class="overview-news-top">
                    <span class="trend-kind">{{ item.impact_label }}</span>
                    <span class="focus-badge muted">{{ item.relevance || 'news' }}</span>
                  </div>
                  <div class="overview-news-title">{{ item.headline }}</div>
                  <div class="overview-news-meta">
                    <span>impact {{ item.impact_score }}</span>
                    <span>{{ (item.linked_assets || []).join(', ') || 'no direct asset link' }}</span>
                  </div>
                  <p class="overview-news-summary">{{ item.summary }}</p>
                </div>
              </div>
            </div>
          </div>

          <div class="overview-panel raw-news-panel">
            <div class="raw-news-top">
              <div>
                <div class="focus-section-title">Raw Captured News</div>
                <div class="driver-board-subtitle">
                  Every headline captured from the feed appears here first. Promoted items reached the risk path or driver board; captured-only items are still below threshold.
                </div>
              </div>
              <div class="driver-board-badges">
                <span class="focus-badge muted">{{ macroRawEvents.length }} captured</span>
                <span class="focus-badge muted">{{ promotedMacroEventIds.size }} promoted</span>
              </div>
            </div>

            <div v-if="macroRawEvents.length === 0" class="mini-empty-state">
              No raw feed headlines were captured yet.
            </div>
            <div v-else class="raw-news-list">
              <div
                v-for="item in macroRawEvents"
                :key="`raw-${item.event_id}`"
                class="raw-news-item"
                :class="rawEventState(item)"
              >
                <div class="driver-news-top">
                  <span class="trend-kind">{{ formatTime(item.event_time) }}</span>
                  <span class="focus-badge muted">impact {{ item.impact_score ?? 0 }}</span>
                </div>
                <div class="raw-news-title">{{ item.headline }}</div>
                <div class="raw-news-meta">
                  <span>{{ item.posted_by || 'bleu feed' }}</span>
                  <span>{{ (item.linked_contracts || []).join(', ') || (item.linked_buckets || []).join(', ') || 'no direct link yet' }}</span>
                  <span>{{ item.market_relevance ? 'market relevant' : 'captured only' }}</span>
                </div>
                <div class="raw-news-state-row">
                  <span class="trend-bias" :class="rawEventState(item) === 'promoted' ? 'buy' : 'watch'">
                    {{ rawEventState(item) === 'promoted' ? 'promoted' : rawEventState(item) === 'watch' ? 'watchlist' : 'captured' }}
                  </span>
                  <span v-if="promotedMacroEventIds.has(item.event_id)" class="raw-news-note">
                    already linked into the driver / thermometer pipeline
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div class="driver-board-header">
            <div>
              <div class="focus-section-title">Driver Radar</div>
              <div class="driver-board-subtitle">
                Each driver groups related headlines, five-minute market follow-through, and participant response into one evolving macro narrative.
              </div>
            </div>
            <div class="driver-board-badges">
              <span class="focus-badge muted">{{ macroNewsFeed.length }} news</span>
              <span class="focus-badge muted">{{ macroDrivers.length }} drivers</span>
            </div>
          </div>

          <div v-if="macroDriverError" class="trendboard-empty error">
            {{ macroDriverError }}
          </div>

          <div v-else-if="macroDriversLoading && macroDrivers.length === 0 && macroNewsFeed.length === 0" class="trendboard-empty">
            Building the impact-driver board from the live news flow and the latest five-minute market state.
          </div>

          <template v-else>
            <div class="driver-board-grid">
              <div class="overview-panel">
                <div class="focus-section-title">News Feed</div>
                <div v-if="macroNewsFeed.length === 0" class="mini-empty-state">
                  No linked macro headlines are in memory yet.
                </div>
                <div v-else class="driver-news-list">
                  <div v-for="item in macroNewsFeed" :key="item.event_id" class="driver-news-item">
                    <div class="driver-news-top">
                      <span class="trend-kind">{{ formatTime(item.event_time) }}</span>
                      <span class="focus-badge muted">impact {{ item.impact_score }}</span>
                    </div>
                    <div class="driver-news-title">{{ item.headline }}</div>
                    <div class="driver-news-meta">
                      <span>{{ item.posted_by || 'bleu feed' }}</span>
                      <span>{{ (item.linked_assets || []).join(', ') || 'macro basket' }}</span>
                    </div>
                    <div v-if="item.driver_title" class="driver-news-driver">
                      {{ item.driver_title }}
                    </div>
                  </div>
                </div>
              </div>

              <div class="overview-panel">
                <div class="focus-section-title">Impact Drivers</div>
                <div v-if="macroDrivers.length === 0" class="mini-empty-state">
                  When a relevant headline generates follow-through, it will appear here as a driver ready for scenario simulation.
                </div>
                <div v-else class="driver-list">
                  <button
                    v-for="driver in macroDrivers"
                    :key="driver.driver_id"
                    class="driver-list-item"
                    :class="{ selected: selectedDriverId === driver.driver_id }"
                    @click="handleDriverFocus(driver.driver_id)"
                  >
                    <div class="driver-item-top">
                      <span class="trend-kind">{{ driver.importance_label }}</span>
                      <span class="trend-bias" :class="driver.simulation_context?.recommended_action || 'watch'">
                        {{ driver.simulation_context?.recommended_action || 'watch' }}
                      </span>
                    </div>
                    <div class="driver-title">{{ driver.title }}</div>
                    <div class="driver-meta">
                      <span>{{ driver.headline_count }} updates</span>
                      <span>score {{ driver.importance_score }}</span>
                      <span>expected {{ driver.expected_impact_score ?? driver.importance_score }}</span>
                      <span>{{ driver.primary_asset || 'macro basket' }}</span>
                    </div>
                    <div class="driver-impact-meta">
                      <span class="focus-badge muted">{{ driver.expected_impact_band || 'secondary_echo' }}</span>
                      <span class="driver-impact-reason">{{ driver.expected_impact_reason || driver.importance_reason }}</span>
                    </div>
                    <div v-if="driver.agent_audit_report" class="driver-impact-meta">
                      <span class="focus-badge muted">agent {{ driver.agent_audit_report.recommended_action || 'watch' }}</span>
                      <span class="driver-impact-reason">
                        {{ driver.agent_audit_report.market_regime || 'intraday macro reaction' }}
                      </span>
                    </div>
                    <div class="driver-summary">{{ driver.driver_summary }}</div>
                  </button>
                </div>
              </div>
            </div>

            <div class="driver-focus-panel">
              <div v-if="focusingDriver" class="focus-loading">
                <div class="spinner-sm"></div>
                <span>Expanding driver context for simulation.</span>
              </div>

              <div v-else-if="focusedDriver?.driver" class="focus-content">
                <div class="focus-header">
                  <div>
                    <div class="focus-title">{{ focusedDriver.driver.title }}</div>
                    <div class="focus-subtitle">{{ focusedDriver.driver.macro_explanation }}</div>
                    <div v-if="refreshingFocusedDriver" class="focus-refresh-hint">
                      Refreshing driver context in the background.
                    </div>
                  </div>
                  <div class="focus-badges">
                    <span class="focus-badge">{{ focusedDriver.driver.importance_label }}</span>
                    <span class="focus-badge muted">{{ focusedDriver.driver.importance_score }}</span>
                    <span class="focus-badge muted">{{ focusedDriver.driver.expected_impact_band || 'secondary_echo' }}</span>
                  </div>
                </div>

                <div class="focus-stat-grid">
                  <div class="focus-stat">
                    <span class="focus-stat-label">Primary asset</span>
                    <span class="focus-stat-value">{{ focusedDriver.driver.primary_asset || 'macro basket' }}</span>
                  </div>
                  <div class="focus-stat">
                    <span class="focus-stat-label">Headline updates</span>
                    <span class="focus-stat-value">{{ focusedDriver.driver.headline_count }}</span>
                  </div>
                  <div class="focus-stat">
                    <span class="focus-stat-label">First event</span>
                    <span class="focus-stat-value">{{ formatTime(focusedDriver.driver.first_event_time) }}</span>
                  </div>
                  <div class="focus-stat">
                    <span class="focus-stat-label">Last update</span>
                    <span class="focus-stat-value">{{ formatTime(focusedDriver.driver.last_event_time) }}</span>
                  </div>
                  <div class="focus-stat">
                    <span class="focus-stat-label">Expected impact</span>
                    <span class="focus-stat-value">{{ focusedDriver.driver.expected_impact_score ?? focusedDriver.driver.importance_score }}</span>
                  </div>
                  <div class="focus-stat">
                    <span class="focus-stat-label">Scenario class</span>
                    <span class="focus-stat-value">{{ focusedDriver.driver.scenario_classification || focusedDriver.driver.expected_impact_band || 'secondary_echo' }}</span>
                  </div>
                  <div v-if="focusedDriverAgentAudit" class="focus-stat">
                    <span class="focus-stat-label">Agent action</span>
                    <span class="focus-stat-value">{{ focusedDriverAgentAudit.recommended_action || 'watch' }}</span>
                  </div>
                  <div v-if="focusedDriverAgentAudit" class="focus-stat">
                    <span class="focus-stat-label">Consensus</span>
                    <span class="focus-stat-value">
                      {{ focusedDriverAgentAudit.directional_consensus?.bias || 'watch' }}
                      · {{ focusedDriverAgentAudit.directional_consensus?.confidence ?? 0 }}
                    </span>
                  </div>
                </div>

                <div v-if="focusedDriverAgentAudit" class="focus-section">
                  <div class="focus-section-title">Agent Audit</div>
                  <div class="driver-asymmetry-grid">
                    <div class="driver-asymmetry-card">
                      <div class="driver-asymmetry-top">
                        <span class="driver-asymmetry-name">Agent read</span>
                        <span class="trend-bias" :class="focusedDriverAgentAudit.recommended_action || 'watch'">
                          {{ focusedDriverAgentAudit.recommended_action || 'watch' }}
                        </span>
                      </div>
                      <div class="driver-asymmetry-meta">
                        <span>regime {{ focusedDriverAgentAudit.market_regime || 'intraday macro reaction' }}</span>
                        <span>{{ focusedDriverAgentAudit.scenario_classification || 'secondary_echo' }}</span>
                      </div>
                      <p>{{ focusedDriverAgentAudit.macro_explanation || focusedDriver.driver.driver_summary }}</p>
                    </div>
                    <div class="driver-asymmetry-card">
                      <div class="driver-asymmetry-top">
                        <span class="driver-asymmetry-name">Score and impact</span>
                        <span class="focus-badge muted">{{ focusedDriverAgentAudit.expected_impact_band || 'secondary_echo' }}</span>
                      </div>
                      <div class="driver-asymmetry-meta">
                        <span>importance {{ focusedDriverAgentAudit.importance_score ?? 0 }}</span>
                        <span>impact {{ focusedDriverAgentAudit.expected_impact_score ?? 0 }}</span>
                      </div>
                      <p>{{ focusedDriverAgentAudit.expected_impact_reason || focusedDriverAgentAudit.importance_reason }}</p>
                    </div>
                    <div class="driver-asymmetry-card">
                      <div class="driver-asymmetry-top">
                        <span class="driver-asymmetry-name">Directional consensus</span>
                        <span class="trend-bias" :class="focusedDriverAgentAudit.directional_consensus?.bias || 'watch'">
                          {{ focusedDriverAgentAudit.directional_consensus?.bias || 'watch' }}
                        </span>
                      </div>
                      <div class="driver-asymmetry-meta">
                        <span>confidence {{ focusedDriverAgentAudit.directional_consensus?.confidence ?? 0 }}</span>
                        <span>{{ focusedDriverAgentAudit.generated_at ? formatTime(focusedDriverAgentAudit.generated_at) : '--' }}</span>
                      </div>
                      <p>{{ focusedDriverAgentAudit.directional_consensus?.reason || focusedDriverAgentAudit.probable_playbook }}</p>
                    </div>
                  </div>
                </div>

                <div class="driver-callout-grid">
                  <div class="driver-callout-card">
                    <div class="focus-section-title">Driver Summary</div>
                    <p>{{ focusedDriver.driver.driver_summary }}</p>
                  </div>
                  <div class="driver-callout-card">
                    <div class="focus-section-title">Expected Impact</div>
                    <p>{{ focusedDriver.driver.expected_impact_reason || focusedDriver.driver.importance_reason }}</p>
                    <div class="driver-callout-meta">
                      Score {{ focusedDriver.driver.expected_impact_score ?? focusedDriver.driver.importance_score }} · {{ focusedDriver.driver.expected_impact_band || 'secondary_echo' }}
                    </div>
                  </div>
                  <div class="driver-callout-card dark">
                    <div class="focus-section-title">Probable Playbook</div>
                    <p>{{ focusedDriver.driver.probable_playbook }}</p>
                    <div class="driver-callout-action">
                      {{ (focusedDriver.driver.simulation_context?.recommended_action || 'watch').toUpperCase() }}
                    </div>
                  </div>
                </div>

                <div class="focus-section">
                  <div class="focus-section-title">Headline Chain</div>
                  <div class="driver-update-list">
                    <div
                      v-for="update in focusedDriver.driver.headline_updates || []"
                      :key="update.event_id"
                      class="driver-update-item"
                      :class="{ active: activeFocusedDriverHeadlineEventId === update.event_id }"
                      @click="selectFocusedDriverHeadline(update.event_id)"
                      @mouseenter="hoveredFocusedDriverHeadlineEventId = update.event_id"
                      @mouseleave="hoveredFocusedDriverHeadlineEventId = ''"
                    >
                      <div class="driver-update-top">
                        <span class="trend-kind">{{ formatTime(update.event_time) }}</span>
                        <span class="focus-badge muted">impact {{ update.impact_score }}</span>
                      </div>
                      <div class="driver-update-title">{{ update.headline }}</div>
                      <div class="driver-update-meta">
                        <span>{{ update.posted_by || 'bleu feed' }}</span>
                        <span>{{ update.relevance || 'macro' }}</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div v-if="focusedDriverCrossAsset" class="driver-cross-asset-grid">
                  <div class="driver-cross-panel dark">
                    <div class="thermometer-chart-top">
                      <div>
                        <div class="focus-section-title">Driver Thermometer</div>
                        <div class="driver-cross-subtitle">
                          Headline-by-headline read of how this driver is changing implicit sentiment across buckets.
                        </div>
                      </div>
                      <div class="thermometer-chart-meta">
                        <span>{{ focusedDriverThermometerChart.timeRangeLabel }}</span>
                        <span>{{ focusedDriverThermometerTimeline.length }} headlines</span>
                      </div>
                    </div>

                    <div v-if="focusedDriverThermometerTimeline.length" class="thermometer-chart-stage driver-thermometer-stage">
                      <svg
                        :viewBox="`0 0 ${focusedDriverThermometerChart.width} ${focusedDriverThermometerChart.height}`"
                        class="thermometer-chart"
                        @mouseleave="hoveredFocusedDriverHeadlineEventId = ''"
                      >
                        <g v-for="tick in focusedDriverThermometerChart.yTicks" :key="`driver-focus-y-${tick.value}`">
                          <line
                            :x1="focusedDriverThermometerChart.plotLeft"
                            :y1="tick.y"
                            :x2="focusedDriverThermometerChart.plotRight"
                            :y2="tick.y"
                            class="thermometer-grid-line"
                            :class="{ baseline: tick.value === 0 }"
                          />
                          <text
                            :x="focusedDriverThermometerChart.plotLeft - 10"
                            :y="tick.y + 4"
                            class="thermometer-axis-label"
                            text-anchor="end"
                          >
                            {{ tick.label }}
                          </text>
                        </g>

                        <g v-for="tick in focusedDriverThermometerChart.xTicks" :key="`driver-focus-x-${tick.label}-${tick.x}`">
                          <line
                            :x1="tick.x"
                            :y1="focusedDriverThermometerChart.plotTop"
                            :x2="tick.x"
                            :y2="focusedDriverThermometerChart.plotBottom"
                            class="thermometer-grid-line vertical"
                          />
                          <text
                            :x="tick.x"
                            :y="focusedDriverThermometerChart.plotBottom + 18"
                            class="thermometer-axis-label"
                            text-anchor="middle"
                          >
                            {{ tick.label }}
                          </text>
                        </g>

                        <g v-for="series in crossAssetSeriesConfig" :key="`focus-series-${series.key}`">
                          <polyline
                            v-if="isFocusedDriverSeriesVisible(series.key)"
                            :points="focusedDriverLinePoints[series.key]"
                            class="thermometer-line"
                            :class="series.key"
                          />
                        </g>

                        <line
                          v-if="activeFocusedDriverPin"
                          :x1="activeFocusedDriverPin.x"
                          :y1="focusedDriverThermometerChart.plotTop"
                          :x2="activeFocusedDriverPin.x"
                          :y2="focusedDriverThermometerChart.plotBottom"
                          class="thermometer-active-guide"
                        />

                        <g
                          v-for="pin in focusedDriverThermometerChart.eventPins"
                          :key="`driver-focus-pin-${pin.event_id}`"
                          class="thermometer-event-pin"
                          :class="{
                            selected: activeFocusedDriverHeadlineEventId === pin.event_id,
                            muted: activeFocusedDriverHeadlineEventId && activeFocusedDriverHeadlineEventId !== pin.event_id
                          }"
                          @mouseenter="hoveredFocusedDriverHeadlineEventId = pin.event_id"
                          @focus="hoveredFocusedDriverHeadlineEventId = pin.event_id"
                          @blur="hoveredFocusedDriverHeadlineEventId = ''"
                          @click="selectFocusedDriverHeadline(pin.event_id)"
                        >
                          <line
                            :x1="pin.x"
                            :y1="pin.y"
                            :x2="pin.x"
                            :y2="focusedDriverThermometerChart.plotBottom"
                            class="thermometer-pin-stem"
                          />
                          <circle
                            :cx="pin.x"
                            :cy="pin.y"
                            :r="activeFocusedDriverHeadlineEventId === pin.event_id ? 6.2 : 4.4"
                            class="thermometer-pin-core"
                            :class="pin.biasClass"
                          />
                          <circle
                            :cx="pin.x"
                            :cy="pin.y"
                            :r="activeFocusedDriverHeadlineEventId === pin.event_id ? 10 : 8"
                            class="thermometer-pin-halo"
                          />
                        </g>
                      </svg>
                    </div>
                    <div v-else class="mini-empty-state dark">
                      Waiting for multiple headlines inside this driver to build the sentiment path.
                    </div>

                    <div v-if="activeFocusedDriverHeadlineEvent" class="thermometer-event-detail">
                      <div class="thermometer-event-detail-top">
                        <span class="trend-kind">{{ formatTime(activeFocusedDriverHeadlineEvent.time) }}</span>
                        <span class="trend-bias" :class="activeFocusedDriverHeadlineEvent.event_bias || 'watch'">
                          {{ activeFocusedDriverHeadlineEvent.event_bias || 'watch' }}
                        </span>
                      </div>
                      <div class="thermometer-event-detail-title">{{ activeFocusedDriverHeadlineEvent.headline }}</div>
                      <div class="thermometer-event-detail-meta">
                        <span>{{ activeFocusedDriverHeadlineEvent.posted_by || 'feed' }}</span>
                        <span>impact {{ activeFocusedDriverHeadlineEvent.impact_score ?? 0 }}</span>
                        <span>{{ activeFocusedDriverHeadlineEvent.scenario_classification || 'secondary_echo' }}</span>
                        <span>w {{ activeFocusedDriverHeadlineEvent.importance_weight ?? 0 }}</span>
                        <span>g {{ activeFocusedDriverHeadlineEvent.scores?.general ?? 0 }}</span>
                        <span>cr {{ activeFocusedDriverHeadlineEvent.scores?.credit ?? 0 }}</span>
                        <span>eq {{ activeFocusedDriverHeadlineEvent.scores?.equity ?? 0 }}</span>
                        <span>cm {{ activeFocusedDriverHeadlineEvent.scores?.commodity ?? 0 }}</span>
                        <span>fx {{ activeFocusedDriverHeadlineEvent.scores?.fx ?? 0 }}</span>
                        <span>rt {{ activeFocusedDriverHeadlineEvent.scores?.rates ?? 0 }}</span>
                      </div>
                      <div v-if="focusedDriverAgentAudit" class="thermometer-event-audit">
                        <div class="thermometer-event-detail-meta">
                          <span>agent {{ focusedDriverAgentAudit.recommended_action || 'watch' }}</span>
                          <span>{{ focusedDriverAgentAudit.market_regime || 'intraday macro reaction' }}</span>
                          <span>driver {{ focusedDriverAgentAudit.importance_score ?? 0 }}</span>
                          <span>expected {{ focusedDriverAgentAudit.expected_impact_score ?? 0 }}</span>
                          <span>
                            consensus {{ focusedDriverAgentAudit.directional_consensus?.bias || 'watch' }}
                            · {{ focusedDriverAgentAudit.directional_consensus?.confidence ?? 0 }}
                          </span>
                        </div>
                        <div class="thermometer-event-audit-text">
                          {{ focusedDriverAgentAudit.expected_impact_reason || focusedDriverAgentAudit.importance_reason }}
                        </div>
                      </div>
                      <div class="focus-chip-row driver-targeted-buckets">
                        <span v-for="bucket in activeFocusedDriverHeadlineEvent.targeted_buckets || []" :key="`bucket-${bucket}`" class="focus-chip">
                          {{ bucket }}
                        </span>
                      </div>
                    </div>

                    <div class="thermometer-legend">
                      <button
                        v-for="series in crossAssetSeriesConfig"
                        :key="`focus-legend-${series.key}`"
                        type="button"
                        class="legend-item legend-button"
                        :class="{ inactive: !isFocusedDriverSeriesVisible(series.key) }"
                        @click="toggleFocusedDriverSeries(series.key)"
                      >
                        <span class="legend-dot" :class="series.key"></span>
                        {{ series.label }}
                      </button>
                    </div>
                  </div>

                  <div class="driver-cross-panel">
                    <div class="focus-section-title">Driver Cross-Asset Read</div>
                    <p class="driver-cross-commentary">{{ focusedDriverCrossAsset.cross_asset_commentary }}</p>

                    <div class="cross-asset-bucket-grid driver-cross-bucket-grid">
                      <div
                        v-for="bucket in ['credit', 'equity', 'commodity', 'fx', 'rates']"
                        :key="`focus-bucket-${bucket}`"
                        class="cross-asset-bucket-card driver-cross-bucket-card"
                      >
                        <div class="thermometer-kpi-top">
                          <span>{{ bucket }}</span>
                          <span class="trend-bias" :class="focusedDriverCrossAsset.bucket_reactions?.[bucket]?.bias">
                            {{ focusedDriverCrossAsset.bucket_reactions?.[bucket]?.strength || 'missing' }}
                          </span>
                        </div>
                        <div class="thermometer-kpi-value">{{ focusedDriverCrossAsset.bucket_reactions?.[bucket]?.score ?? 0 }}</div>
                        <div class="cross-asset-leaders">
                          <span
                            v-for="leader in (focusedDriverCrossAsset.bucket_reactions?.[bucket]?.leaders || []).slice(0, 2)"
                            :key="`focus-${bucket}-${leader.asset}`"
                            class="focus-chip"
                          >
                            {{ leader.label }} {{ formatSignedPercent(leader.delta_pct) }}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div class="cross-asset-mini-meta driver-cross-meta">
                      <span>general {{ focusedDriverCrossAsset.general_score ?? focusedDriverThermometerLatest.general ?? 0 }}</span>
                      <span>confirmation {{ focusedDriverCrossAsset.cross_signals?.confirmation_ratio ?? 0 }}%</span>
                      <span>fake move {{ focusedDriverCrossAsset.cross_signals?.fake_move_risk ?? 0 }}%</span>
                      <span>absorption {{ focusedDriverCrossAsset.cross_signals?.absorption_signal ?? 0 }}%</span>
                      <span>{{ focusedDriverCrossAsset.cross_signals?.regime || 'mixed' }}</span>
                    </div>

                    <div v-if="focusedDriverCrossAsset.insights?.length" class="cross-asset-insight-list driver-insight-list">
                      <div v-for="insight in focusedDriverCrossAsset.insights" :key="`focus-insight-${insight.title}`" class="thermometer-timeline-item driver-insight-item">
                        <div class="driver-news-top">
                          <span class="trend-kind">{{ insight.kind }}</span>
                          <span class="trend-bias" :class="insight.bias">{{ insight.bias }}</span>
                        </div>
                        <div class="thermometer-timeline-title">{{ insight.title }}</div>
                        <div class="thermometer-timeline-meta">
                          <span>{{ insight.confidence }}%</span>
                          <span>{{ insight.bucket_focus?.join(', ') }}</span>
                        </div>
                        <p class="overview-participant-comment">{{ insight.message }}</p>
                      </div>
                    </div>
                  </div>
                </div>

                <div class="focus-section">
                  <div class="focus-section-title">Asset Asymmetry</div>
                  <div class="driver-asymmetry-grid">
                    <div v-for="asset in focusedDriver.driver.asset_asymmetry || []" :key="asset.asset" class="driver-asymmetry-card">
                      <div class="driver-asymmetry-top">
                        <span class="driver-asymmetry-name">{{ asset.asset }}</span>
                        <span class="trend-bias" :class="asset.bias">{{ asset.bias }}</span>
                      </div>
                      <div class="driver-asymmetry-meta">
                        <span>score {{ formatCompactNumber(asset.asymmetry_score) }}</span>
                        <span>{{ formatSignedPercent(asset.net_change_pct_5m) }}</span>
                      </div>
                      <p>{{ asset.explanation }}</p>
                    </div>
                  </div>
                </div>

                <div class="focus-section">
                  <div class="focus-section-title">WIN / DI / WDO 5m Elasticity</div>
                  <div class="driver-asymmetry-grid">
                    <div v-for="row in focusedDriverElasticityRows" :key="`${row.key}-${row.ticker}`" class="driver-asymmetry-card">
                      <div class="driver-asymmetry-top">
                        <span class="driver-asymmetry-name">{{ row.label }}</span>
                        <span class="trend-bias" :class="row.impact?.direction || 'watch'">
                          {{ row.state || 'pending' }}
                        </span>
                      </div>
                      <div class="driver-asymmetry-meta">
                        <span>{{ row.ticker }}</span>
                        <span>{{ row.elapsed_minutes ?? 0 }}m</span>
                      </div>
                      <div v-if="row.impact" class="driver-impact-pill" :class="row.impact.direction || 'watch'">
                        <span>score {{ formatCompactNumber(row.impact.elasticity_score) }}</span>
                        <span>{{ formatSignedPercent(row.impact.price_delta_pct) }}</span>
                        <span>{{ formatSignedNumber(row.impact.price_delta) }}</span>
                      </div>
                      <div class="driver-series-meta">
                        <span>pre {{ formatPrice(row.pre_event?.close) }}</span>
                        <span>now/5m {{ formatPrice(row.effective_point?.close) }}</span>
                      </div>
                      <p v-if="row.live_window_open">
                        Live window open. This row keeps updating until the 5-minute mark and then freezes.
                      </p>
                      <p v-else-if="row.impact">
                        Frozen at the effective 5-minute reading for audit and comparison.
                      </p>
                      <p v-else>
                        Waiting for enough 1-minute snapshots to estimate elasticity.
                      </p>
                    </div>
                  </div>
                </div>

                <div class="focus-section">
                  <div class="focus-section-title">Minute-by-Minute Evolution</div>
                  <div class="driver-series-grid">
                    <div v-for="series in focusedDriver.driver.price_evolution?.series || []" :key="series.ticker" class="driver-series-card">
                      <div class="driver-series-top">
                        <span class="driver-series-name">{{ series.ticker }}</span>
                        <span class="focus-badge muted">{{ series.timeline_1m?.length || 0 }} pts</span>
                      </div>
                      <div class="driver-series-meta">
                        <span>pre {{ formatPrice(series.pre_event?.close) }}</span>
                        <span>post {{ formatPrice(series.first_after_event?.close) }}</span>
                      </div>
                      <div v-if="series.impact_5m" class="driver-impact-pill" :class="series.impact_5m.direction">
                        <span>5m {{ series.impact_5m.direction }}</span>
                        <span>{{ formatSignedPercent(series.impact_5m.price_delta_pct) }}</span>
                        <span>vol {{ formatCompactNumber(series.impact_5m.volume_delta) }}</span>
                      </div>
                      <div v-if="series.timeline_1m?.length" class="driver-timeline-list">
                        <div v-for="point in series.timeline_1m" :key="`${series.ticker}-${point.time}`" class="driver-timeline-item">
                          <span>{{ formatTime(point.time) }}</span>
                          <span>{{ formatPrice(point.close) }}</span>
                          <span>vol {{ formatCompactNumber(point.volume) }}</span>
                        </div>
                      </div>
                      <div v-else class="mini-empty-state">
                        Waiting for enough snapshots around this event to build the intraday path.
                      </div>
                    </div>
                  </div>
                </div>

                <div class="focus-section">
                  <div class="focus-section-title">Participant Reaction</div>
                  <div class="driver-participant-grid">
                    <div v-for="participant in focusedDriver.driver.participant_reactions || []" :key="participant.broker_name" class="driver-participant-card">
                      <div class="driver-participant-top">
                        <span class="driver-participant-name">{{ participant.broker_name }}</span>
                        <span class="trend-bias" :class="participant.market_bias">{{ participant.market_bias }}</span>
                      </div>
                      <div class="driver-participant-meta">
                        <span>activity {{ formatCompactNumber(participant.activity_score) }}</span>
                        <span>sentiment {{ formatCompactNumber(participant.sentiment_score) }}</span>
                      </div>
                      <div class="focus-chip-row">
                        <span v-for="asset in participant.assets || []" :key="`${participant.broker_name}-${asset.ticker}`" class="focus-chip">
                          {{ asset.ticker }} {{ asset.share_percentage }}%
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                <div class="driver-graph-grid">
                  <div class="driver-graph-panel">
                    <div class="focus-section-title">Driver Graph</div>
                    <div class="driver-node-list">
                      <div v-for="node in focusedDriver.driver.driver_graph?.nodes || []" :key="node.id" class="driver-node-card">
                        <span class="trend-kind">{{ node.type }}</span>
                        <span class="driver-node-label">{{ node.label }}</span>
                      </div>
                    </div>
                  </div>

                  <div class="driver-graph-panel">
                    <div class="focus-section-title">Driver Links</div>
                    <div v-if="focusedDriver.driver.driver_graph?.edges?.length" class="driver-edge-list">
                      <div v-for="edge in focusedDriver.driver.driver_graph.edges" :key="`${edge.source}-${edge.target}-${edge.relation}`" class="driver-edge-item">
                        <span>{{ edge.source }}</span>
                        <span class="driver-edge-relation">{{ edge.relation }}</span>
                        <span>{{ edge.target }}</span>
                      </div>
                    </div>
                    <div v-else class="mini-empty-state">
                      Driver links will appear once the graph is enriched with more context.
                    </div>
                  </div>
                </div>

                <div v-if="focusedDriverCrossAsset" class="focus-section">
                  <div class="focus-section-title">Asset Interaction Graph</div>
                  <div class="driver-interaction-panel">
                    <div v-if="!focusedDriverInteractionLayout.nodes.length" class="mini-empty-state">
                      Cross-asset nodes will appear once the driver has enough transmission data.
                    </div>
                    <template v-else>
                      <div class="driver-interaction-stage">
                        <svg
                          :viewBox="`0 0 ${focusedDriverInteractionLayout.width} ${focusedDriverInteractionLayout.height}`"
                          class="driver-interaction-svg"
                        >
                          <line
                            v-for="edge in focusedDriverInteractionLayout.edges"
                            :key="`interaction-${edge.source}-${edge.target}-${edge.relation}`"
                            :x1="edge.x1"
                            :y1="edge.y1"
                            :x2="edge.x2"
                            :y2="edge.y2"
                            class="driver-interaction-edge"
                            :class="edge.relation"
                          />

                          <g
                            v-for="node in focusedDriverInteractionLayout.nodes"
                            :key="`interaction-node-${node.id}`"
                            class="driver-interaction-node"
                            :class="[node.type, node.bias || 'watch']"
                          >
                            <circle
                              :cx="node.x"
                              :cy="node.y"
                              :r="node.radius"
                              class="driver-interaction-circle"
                            />
                            <text
                              :x="node.x"
                              :y="node.y + (node.type === 'driver' ? 4 : 3)"
                              class="driver-interaction-label"
                              text-anchor="middle"
                            >
                              {{ node.displayLabel }}
                            </text>
                          </g>
                        </svg>
                      </div>

                      <div class="driver-interaction-legend">
                        <span class="focus-chip">driver</span>
                        <span class="focus-chip">bucket</span>
                        <span class="focus-chip">asset</span>
                        <span class="focus-chip">pushes / confirms / diverges</span>
                      </div>
                    </template>
                  </div>
                </div>

                <div v-if="focusedDriver.related_drivers?.length" class="focus-section">
                  <div class="focus-section-title">Related Drivers</div>
                  <div class="focus-chip-row">
                    <button
                      v-for="related in focusedDriver.related_drivers"
                      :key="related.driver_id"
                      class="focus-chip focus-chip-button"
                      @click="handleDriverFocus(related.driver_id)"
                    >
                      {{ related.title }}
                    </button>
                  </div>
                </div>
              </div>

              <div v-else class="trendboard-empty">
                Select a driver to inspect the news chain, five-minute follow-through, and participant reaction before launching a simulation.
              </div>
            </div>
          </template>

          <div v-if="!canLoadMacroTrends" class="trendboard-empty">
            Complete the graph build to convert active drivers into agent commentary and scenario-ready trend simulations.
          </div>

          <div v-else-if="macroTrendError" class="trendboard-empty error">
            {{ macroTrendError }}
          </div>

          <div v-else-if="macroTrends.length === 0 && !macroTrendsLoading" class="trendboard-empty">
            No active macro trends were detected in the latest snapshot.
          </div>

          <div v-else class="trendboard-grid">
            <div class="trend-list">
              <button
                v-for="trend in macroTrends"
                :key="trend.trend_id"
                class="trend-list-item"
                :class="{ selected: selectedTrendId === trend.trend_id }"
                @click="handleTrendFocus(trend.trend_id)"
              >
                <div class="trend-item-top">
                  <span class="trend-kind">{{ trend.kind }}</span>
                  <span class="trend-bias" :class="trend.probable_bias">{{ trend.probable_bias }}</span>
                </div>
                <div class="trend-title">{{ trend.title }}</div>
                <div class="trend-meta">
                  <span>importance {{ trend.importance_score }}</span>
                  <span>{{ trend.importance_label }}</span>
                </div>
                <div class="trend-assets">
                  {{ [...(trend.focus_contracts || []), ...(trend.focus_securities || [])].slice(0, 3).join(', ') || 'macro basket' }}
                </div>
              </button>
            </div>

            <div class="trend-focus-panel">
              <div v-if="focusingTrend" class="focus-loading">
                <div class="spinner-sm"></div>
                <span>Generating agent focus...</span>
              </div>

              <div v-else-if="focusedTrend" class="focus-content">
                <div class="focus-header">
                  <div>
                    <div class="focus-title">{{ focusedTrend.trend.title }}</div>
                    <div class="focus-subtitle">{{ focusedTrend.trend.summary }}</div>
                  </div>
                  <div class="focus-badges">
                    <span class="focus-badge">{{ focusedTrend.trend.probable_bias }}</span>
                    <span class="focus-badge muted">{{ focusedTrend.trend.confidence }}%</span>
                  </div>
                </div>

                <div class="focus-stat-grid">
                  <div class="focus-stat">
                    <span class="focus-stat-label">Primary asset</span>
                    <span class="focus-stat-value">{{ focusedTrend.trend.primary_asset || 'n/a' }}</span>
                  </div>
                  <div class="focus-stat">
                    <span class="focus-stat-label">Importance</span>
                    <span class="focus-stat-value">{{ focusedTrend.trend.importance_score }}</span>
                  </div>
                  <div class="focus-stat">
                    <span class="focus-stat-label">Direction 5m</span>
                    <span class="focus-stat-value">{{ focusedTrend.trend.direction_5m || 'watch' }}</span>
                  </div>
                  <div class="focus-stat">
                    <span class="focus-stat-label">Top 5 share</span>
                    <span class="focus-stat-value">{{ focusedTrend.trend.top_5_share_percentage || '-' }}</span>
                  </div>
                </div>

                <div class="focus-section">
                  <div class="focus-section-title">Signal Evidence</div>
                  <div class="focus-chip-row">
                    <span v-for="item in focusedTrend.trend.signal_evidence || []" :key="item" class="focus-chip">{{ item }}</span>
                  </div>
                </div>

                <div class="focus-section">
                  <div class="focus-section-title">Agent Comments</div>
                  <div class="agent-comment-list">
                    <div v-for="comment in focusedTrend.agent_comments || []" :key="comment.agent_uuid" class="agent-comment-card">
                      <div class="agent-comment-header">
                        <div>
                          <div class="agent-comment-name">{{ comment.agent_name }}</div>
                          <div class="agent-comment-role">{{ comment.entity_type }} · {{ comment.institution || 'market desk' }}</div>
                        </div>
                        <div class="agent-comment-badges">
                          <span class="trend-bias" :class="comment.bias">{{ comment.bias }}</span>
                          <span class="comment-confidence">{{ comment.confidence }}%</span>
                        </div>
                      </div>
                      <p class="agent-comment-text">{{ comment.comment }}</p>
                      <p class="agent-comment-reason">{{ comment.reason }}</p>
                    </div>
                  </div>
                </div>

                <div v-if="focusedTrend.ai_summary" class="focus-section">
                  <div class="focus-section-title">AI Summary</div>
                  <div class="ai-summary-box">
                    <div class="ai-summary-top">
                      <span class="trend-bias" :class="focusedTrend.ai_summary.bias">{{ focusedTrend.ai_summary.bias }}</span>
                      <span class="comment-confidence">{{ focusedTrend.ai_summary.confidence }}%</span>
                    </div>
                    <p class="ai-summary-scenario">{{ focusedTrend.ai_summary.probable_scenario }}</p>
                    <div class="ai-summary-action">
                      Suggested action: {{ (focusedTrend.ai_summary.recommended_action || focusedTrend.ai_summary.bias || 'watch').toUpperCase() }}
                    </div>
                    <div class="ai-summary-list">
                      <span class="ai-summary-label">Why</span>
                      <ul>
                        <li v-for="item in focusedTrend.ai_summary.why || []" :key="`why-${item}`">{{ item }}</li>
                      </ul>
                    </div>
                    <div class="ai-summary-list">
                      <span class="ai-summary-label">Risks</span>
                      <ul>
                        <li v-for="item in focusedTrend.ai_summary.risks || []" :key="`risk-${item}`">{{ item }}</li>
                      </ul>
                    </div>
                    <div class="ai-summary-list">
                      <span class="ai-summary-label">Monitor</span>
                      <ul>
                        <li v-for="item in focusedTrend.ai_summary.what_to_monitor || []" :key="`monitor-${item}`">{{ item }}</li>
                      </ul>
                    </div>
                    <div class="ai-summary-foot">
                      {{ focusedTrend.ai_summary.recommended_focus }}
                    </div>
                  </div>
                </div>
              </div>

              <div v-else class="trendboard-empty">
                Select a trend to generate agent reactions and a scenario summary.
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Bottom Info / Logs -->
    <div class="system-logs">
      <div class="log-header">
        <span class="log-title">SYSTEM DASHBOARD</span>
        <span class="log-id">{{ projectData?.project_id || 'NO_PROJECT' }}</span>
      </div>
      <div class="log-content" ref="logContent">
        <div class="log-line" v-for="(log, idx) in systemLogs" :key="idx">
          <span class="log-time">{{ log.time }}</span>
          <span class="log-msg">{{ log.msg }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { createSimulation } from '../api/simulation'
import {
  getMacroCollectorStatus,
  getMacroEvents,
  getMacroOverview,
  getMacroThermometer,
  getMacroCrossAsset,
  getMacroDrivers,
  focusMacroDriver,
  getMacroTrends,
  focusMacroTrend
} from '../api/macro'

const router = useRouter()
const { t } = useI18n()

const props = defineProps({
  currentPhase: { type: Number, default: 0 },
  inputMode: { type: String, default: 'documents' },
  projectData: Object,
  ontologyProgress: Object,
  buildProgress: Object,
  graphData: Object,
  systemLogs: { type: Array, default: () => [] }
})

defineEmits(['next-step'])

const selectedOntologyItem = ref(null)
const logContent = ref(null)
const creatingSimulation = ref(false)
const macroTrends = ref([])
const macroTrendsLoading = ref(false)
const macroTrendError = ref('')
const macroOverview = ref(null)
const macroOverviewLoading = ref(false)
const macroOverviewError = ref('')
const macroThermometer = ref(null)
const macroThermometerLoading = ref(false)
const macroThermometerError = ref('')
const macroCrossAsset = ref(null)
const macroCrossAssetLoading = ref(false)
const macroCrossAssetError = ref('')
const macroDrivers = ref([])
const macroNewsFeed = ref([])
const macroRawEvents = ref([])
const macroDriversLoading = ref(false)
const macroDriverError = ref('')
const macroCollectorStatus = ref(null)
const macroCollectorError = ref('')
const selectedDriverId = ref('')
const focusedDriver = ref(null)
const focusingDriver = ref(false)
const refreshingFocusedDriver = ref(false)
let focusedDriverElasticityTimer = null
const selectedThermometerEventId = ref('')
const hoveredThermometerEventId = ref('')
const visibleThermometerSeries = ref(['general', 'credit', 'equity', 'fx'])
const hoveredCrossAssetDriverId = ref('')
const visibleCrossAssetSeries = ref(['general', 'credit', 'equity', 'commodity', 'fx', 'rates'])
const selectedFocusedDriverHeadlineEventId = ref('')
const hoveredFocusedDriverHeadlineEventId = ref('')
const visibleFocusedDriverSeries = ref(['general', 'credit', 'equity', 'commodity', 'fx', 'rates'])
const selectedTrendId = ref('')
const focusedTrend = ref(null)
const focusingTrend = ref(false)
let macroPollingTimer = null

const THERMOMETER_CHART_WIDTH = 760
const THERMOMETER_CHART_HEIGHT = 220
const THERMOMETER_PLOT_LEFT = 46
const THERMOMETER_PLOT_RIGHT = THERMOMETER_CHART_WIDTH - 18
const THERMOMETER_PLOT_TOP = 16
const THERMOMETER_PLOT_BOTTOM = THERMOMETER_CHART_HEIGHT - 34
const thermometerSeriesConfig = [
  { key: 'general', label: 'general' },
  { key: 'credit', label: 'credit' },
  { key: 'equity', label: 'equity' },
  { key: 'fx', label: 'fx' }
]
const crossAssetSeriesConfig = [
  { key: 'general', label: 'general' },
  { key: 'credit', label: 'credit' },
  { key: 'equity', label: 'equity' },
  { key: 'commodity', label: 'commodity' },
  { key: 'fx', label: 'fx' },
  { key: 'rates', label: 'rates' }
]
const MACRO_CROSS_ASSET_LIMIT = 100
let activeDriverFocusRequestId = 0

// 进入环境搭建 - 创建 simulation 并跳转
const handleEnterEnvSetup = async () => {
  if (!props.projectData?.project_id || !props.projectData?.graph_id) {
    console.error('缺少项目或图谱信息')
    return
  }
  
  creatingSimulation.value = true
  
  try {
    const res = await createSimulation({
      project_id: props.projectData.project_id,
      graph_id: props.projectData.graph_id,
      enable_twitter: true,
      enable_reddit: true
    })
    
    if (res.success && res.data?.simulation_id) {
      // 跳转到 simulation 页面
      router.push({
        name: 'Simulation',
        params: { simulationId: res.data.simulation_id }
      })
    } else {
      console.error('创建模拟失败:', res.error)
      alert(t('step1.createSimulationFailed', { error: res.error || t('common.unknownError') }))
    }
  } catch (err) {
    console.error('创建模拟异常:', err)
    alert(t('step1.createSimulationException', { error: err.message }))
  } finally {
    creatingSimulation.value = false
  }
}

const selectOntologyItem = (item, type) => {
  selectedOntologyItem.value = { ...item, itemType: type }
}

const graphStats = computed(() => {
  const nodes = props.graphData?.node_count || props.graphData?.nodes?.length || 0
  const edges = props.graphData?.edge_count || props.graphData?.edges?.length || 0
  const types = props.projectData?.ontology?.entity_types?.length || 0
  return { nodes, edges, types }
})

const showMacroDashboard = computed(() => props.inputMode === 'macro')

const buildDriverVersionKey = (driver) => {
  if (!driver?.driver_id) return ''
  return [
    driver.driver_id,
    driver.last_event_time || '',
    driver.headline_count || 0,
    driver.importance_score || 0,
    driver.market_elasticity?.generated_at || '',
    driver.market_elasticity?.rows?.map((row) => `${row.ticker}:${row.state}:${row.effective_time || ''}:${row.impact?.elasticity_score || 0}`).join('|') || '',
  ].join('::')
}

const findLoadedDriver = (driverId) => (
  macroDrivers.value.find((item) => item.driver_id === driverId) || null
)

const canLoadMacroTrends = computed(() => (
  showMacroDashboard.value
  && props.currentPhase >= 2
  && !!props.projectData?.project_id
  && !!props.projectData?.graph_id
))

const openMacroHeatmap = () => {
  router.push({ name: 'MacroHeatmap' })
}

const collectorStatusTone = computed(() => {
  if (macroCollectorStatus.value?.running) return 'success'
  if (macroCollectorError.value) return 'error'
  return 'warning'
})

const collectorStatusLabel = computed(() => {
  if (macroCollectorStatus.value?.running) {
    const completedAt = formatTime(macroCollectorStatus.value?.last_completed_at)
    return `collector live • last run ${completedAt}`
  }
  if (macroCollectorStatus.value) {
    const completedAt = formatTime(macroCollectorStatus.value?.last_completed_at)
    return `collector stopped • last run ${completedAt}`
  }
  if (macroCollectorError.value) return macroCollectorError.value
  return 'collector status unknown'
})

const normalizeThermometerPayload = (rawPayload) => {
  if (!rawPayload || typeof rawPayload !== 'object') return null
  if (rawPayload.thermometer) return rawPayload
  if (rawPayload.data?.thermometer) return rawPayload.data
  if (rawPayload.overall || rawPayload.timeline) {
    return {
      generated_at: rawPayload.generated_at || null,
      thermometer: rawPayload,
      ai_summary: rawPayload.ai_summary || null,
      entity_views: rawPayload.entity_views || [],
      overview_bridge: rawPayload.overview_bridge || null,
      trading_plan: rawPayload.trading_plan || null
    }
  }
  return rawPayload
}

const normalizedMacroThermometer = computed(() => normalizeThermometerPayload(macroThermometer.value))
const thermometerPayload = computed(() => {
  const payload = normalizedMacroThermometer.value || {}
  return payload?.thermometer || payload?.data?.thermometer || {}
})
const thermometerTimeline = computed(() => thermometerPayload.value?.timeline || [])
const thermometerEntityViews = computed(() => {
  const payload = normalizedMacroThermometer.value || {}
  return payload?.entity_views || payload?.data?.entity_views || []
})
const promotedMacroEventIds = computed(() => {
  const promotedIds = new Set()
  for (const item of thermometerTimeline.value) {
    if (item?.event_id) promotedIds.add(item.event_id)
  }
  for (const item of macroNewsFeed.value) {
    if (item?.event_id) promotedIds.add(item.event_id)
  }
  return promotedIds
})
const thermometerLatest = computed(() => {
  const thermo = thermometerPayload.value || {}
  return {
    general: thermo.overall || null,
    credit: thermo.credit || null,
    equity: thermo.equity || null,
    fx: thermo.fx || null
  }
})
const macroCrossAssetTimeline = computed(() => {
  const items = [...(macroCrossAsset.value?.timeline || [])]
  items.sort((left, right) => {
    const leftTs = parseThermometerTimestamp(left?.last_event_time || left?.time || left?.first_event_time)
    const rightTs = parseThermometerTimestamp(right?.last_event_time || right?.time || right?.first_event_time)
    return leftTs - rightTs
  })
  return items
})
const macroCrossAssetInsights = computed(() => macroCrossAsset.value?.insights || [])
const macroCrossAssetEntityViews = computed(() => macroCrossAsset.value?.entity_views || [])
const macroCrossAssetSummary = computed(() => macroCrossAsset.value?.summary || {})
const macroCrossAssetDrivers = computed(() => macroCrossAsset.value?.drivers || [])
const crossAssetSelectedDriver = computed(() => {
  const mapped = macroCrossAssetDrivers.value.find((item) => item.driver_id === selectedDriverId.value)
  if (mapped) return mapped
  const latest = macroCrossAssetDrivers.value[0]
  return latest || null
})

const rawEventState = (item) => {
  if (promotedMacroEventIds.value.has(item?.event_id)) return 'promoted'
  if (item?.market_relevance || Number(item?.impact_score || 0) >= 2 || (item?.linked_contracts || []).length) return 'watch'
  return 'captured'
}

const loadMacroOverview = async (forceReload = false) => {
  if (!showMacroDashboard.value) return
  if (macroOverviewLoading.value && !forceReload) return

  macroOverviewLoading.value = true
  macroOverviewError.value = ''

  try {
    const res = await getMacroOverview({
      participant_limit: 12,
      news_limit: 6
    })
    macroOverview.value = res.data || null
  } catch (err) {
    macroOverviewError.value = err.message || 'Failed to load market overview.'
  } finally {
    macroOverviewLoading.value = false
  }
}

const formatTime = (dateStr) => {
  if (!dateStr) return '--:--'
  const d = new Date(dateStr)
  if (Number.isNaN(d.getTime())) return '--:--'
  return d.toLocaleTimeString('pt-BR', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

const formatAxisTime = (dateStr) => {
  if (!dateStr) return '--:--'
  const d = new Date(dateStr)
  if (Number.isNaN(d.getTime())) return '--:--'
  return d.toLocaleTimeString('pt-BR', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit'
  })
}

const formatPrice = (value) => {
  if (value === null || value === undefined || value === '') return '--'
  const num = Number(value)
  if (!Number.isFinite(num)) return '--'
  return num.toFixed(3)
}

const formatSignedPercent = (value) => {
  if (value === null || value === undefined || value === '') return '--'
  const num = Number(value)
  if (!Number.isFinite(num)) return '--'
  const sign = num > 0 ? '+' : ''
  return `${sign}${num.toFixed(3)}%`
}

const formatSignedNumber = (value) => {
  if (value === null || value === undefined || value === '') return '--'
  const num = Number(value)
  if (!Number.isFinite(num)) return '--'
  const sign = num > 0 ? '+' : ''
  return `${sign}${num.toFixed(3)}`
}

const formatCompactNumber = (value) => {
  if (value === null || value === undefined || value === '') return '--'
  const num = Number(value)
  if (!Number.isFinite(num)) return '--'
  return new Intl.NumberFormat('en-US', {
    notation: 'compact',
    maximumFractionDigits: 1
  }).format(num)
}

const scoreBarStyle = (score) => {
  const normalized = Math.max(-100, Math.min(100, Number(score || 0)))
  return {
    width: `${Math.abs(normalized)}%`,
    marginLeft: normalized < 0 ? `${50 - Math.abs(normalized) / 2}%` : '50%'
  }
}

const isThermometerSeriesVisible = (seriesKey) => visibleThermometerSeries.value.includes(seriesKey)

const toggleThermometerSeries = (seriesKey) => {
  if (isThermometerSeriesVisible(seriesKey)) {
    if (visibleThermometerSeries.value.length === 1) return
    visibleThermometerSeries.value = visibleThermometerSeries.value.filter((item) => item !== seriesKey)
    return
  }
  visibleThermometerSeries.value = [...visibleThermometerSeries.value, seriesKey]
}

const selectThermometerEvent = (item) => {
  if (!item?.event_id) return
  selectedThermometerEventId.value = item.event_id
  hoveredThermometerEventId.value = ''
}

const parseThermometerTimestamp = (value) => {
  if (!value) return NaN
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? NaN : date.getTime()
}

const chartYFromScore = (score) => {
  const normalized = Math.max(-100, Math.min(100, Number(score || 0)))
  const ratio = (normalized + 100) / 200
  return THERMOMETER_PLOT_BOTTOM - (ratio * (THERMOMETER_PLOT_BOTTOM - THERMOMETER_PLOT_TOP))
}

const thermometerChart = computed(() => {
  const items = thermometerTimeline.value
  const timestamps = items
    .map((item) => parseThermometerTimestamp(item.time))
    .filter((value) => Number.isFinite(value))

  const fallbackTs = Date.now()
  const minTs = timestamps.length ? Math.min(...timestamps) : fallbackTs
  const maxTs = timestamps.length ? Math.max(...timestamps) : fallbackTs
  const span = Math.max(maxTs - minTs, 1)
  const plotWidth = THERMOMETER_PLOT_RIGHT - THERMOMETER_PLOT_LEFT

  const xFromTimestamp = (timestamp) => {
    if (!Number.isFinite(timestamp)) return THERMOMETER_PLOT_LEFT + (plotWidth / 2)
    if (maxTs === minTs) return THERMOMETER_PLOT_LEFT + (plotWidth / 2)
    return THERMOMETER_PLOT_LEFT + (((timestamp - minTs) / span) * plotWidth)
  }

  const yTicks = [100, 50, 0, -50, -100].map((value) => ({
    value,
    label: value > 0 ? `+${value}` : `${value}`,
    y: chartYFromScore(value)
  }))

  const tickCount = items.length > 1 ? 5 : 2
  const xTicks = Array.from({ length: tickCount }, (_, index) => {
    const ratio = tickCount === 1 ? 0.5 : (index / (tickCount - 1))
    const tickTs = minTs + (span * ratio)
    return {
      x: xFromTimestamp(tickTs),
      label: formatAxisTime(new Date(tickTs).toISOString())
    }
  })

  const series = Object.fromEntries(
    thermometerSeriesConfig.map((seriesMeta) => {
      const points = items.map((item) => {
        const score = Number(item?.scores?.[seriesMeta.key] || 0)
        const x = xFromTimestamp(parseThermometerTimestamp(item.time))
        const y = chartYFromScore(score)
        return { x, y, score }
      })
      return [seriesMeta.key, points]
    })
  )

  const eventPins = items.map((item, index) => {
    const ts = parseThermometerTimestamp(item.time)
    const score = Number(item?.scores?.general || 0)
    const riskMarker = item?.risk_marker?.general || 'neutral'
    return {
      raw: item,
      index,
      event_id: item.event_id,
      x: xFromTimestamp(ts),
      y: chartYFromScore(score),
      score,
      biasClass: riskMarker === 'risk-on' ? 'buy' : riskMarker === 'risk-off' ? 'sell' : 'watch'
    }
  })

  const firstItem = items[0]
  const lastItem = items[items.length - 1]

  return {
    width: THERMOMETER_CHART_WIDTH,
    height: THERMOMETER_CHART_HEIGHT,
    plotLeft: THERMOMETER_PLOT_LEFT,
    plotRight: THERMOMETER_PLOT_RIGHT,
    plotTop: THERMOMETER_PLOT_TOP,
    plotBottom: THERMOMETER_PLOT_BOTTOM,
    yTicks,
    xTicks,
    series,
    eventPins,
    timeRangeLabel: firstItem && lastItem
      ? `${formatAxisTime(firstItem.time)} → ${formatAxisTime(lastItem.time)}`
      : 'Awaiting market-moving events'
  }
})

const activeThermometerEventId = computed(() => {
  if (hoveredThermometerEventId.value) return hoveredThermometerEventId.value
  if (selectedThermometerEventId.value) return selectedThermometerEventId.value
  const lastItem = thermometerTimeline.value[thermometerTimeline.value.length - 1]
  return lastItem?.event_id || ''
})

const activeThermometerEvent = computed(() => (
  thermometerTimeline.value.find((item) => item.event_id === activeThermometerEventId.value)
  || thermometerTimeline.value[thermometerTimeline.value.length - 1]
  || null
))

const activeThermometerEventPin = computed(() => (
  thermometerChart.value.eventPins.find((pin) => pin.event_id === activeThermometerEventId.value) || null
))

const buildLinePoints = (seriesKey) => {
  const points = thermometerChart.value.series?.[seriesKey] || []
  return points.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ')
}

const linePoints = computed(() => ({
  general: buildLinePoints('general'),
  credit: buildLinePoints('credit'),
  equity: buildLinePoints('equity'),
  fx: buildLinePoints('fx')
}))

const isCrossAssetSeriesVisible = (seriesKey) => visibleCrossAssetSeries.value.includes(seriesKey)

const toggleCrossAssetSeries = (seriesKey) => {
  if (isCrossAssetSeriesVisible(seriesKey)) {
    if (visibleCrossAssetSeries.value.length === 1) return
    visibleCrossAssetSeries.value = visibleCrossAssetSeries.value.filter((item) => item !== seriesKey)
    return
  }
  visibleCrossAssetSeries.value = [...visibleCrossAssetSeries.value, seriesKey]
}

const selectCrossAssetDriver = async (driverId) => {
  if (!driverId) return
  hoveredCrossAssetDriverId.value = ''
  await handleDriverFocus(driverId, { silent: true })
}

const crossAssetChart = computed(() => {
  const items = macroCrossAssetTimeline.value
  const timestamps = items
    .map((item) => parseThermometerTimestamp(item.last_event_time || item.time || item.first_event_time))
    .filter((value) => Number.isFinite(value))

  const fallbackTs = Date.now()
  const minTs = timestamps.length ? Math.min(...timestamps) : fallbackTs
  const maxTs = timestamps.length ? Math.max(...timestamps) : fallbackTs
  const span = Math.max(maxTs - minTs, 1)
  const plotWidth = THERMOMETER_PLOT_RIGHT - THERMOMETER_PLOT_LEFT

  const xFromTimestamp = (timestamp) => {
    if (!Number.isFinite(timestamp)) return THERMOMETER_PLOT_LEFT + (plotWidth / 2)
    if (maxTs === minTs) return THERMOMETER_PLOT_LEFT + (plotWidth / 2)
    return THERMOMETER_PLOT_LEFT + (((timestamp - minTs) / span) * plotWidth)
  }

  const yTicks = [100, 50, 0, -50, -100].map((value) => ({
    value,
    label: value > 0 ? `+${value}` : `${value}`,
    y: chartYFromScore(value)
  }))

  const tickCount = items.length > 1 ? 5 : 2
  const xTicks = Array.from({ length: tickCount }, (_, index) => {
    const ratio = tickCount === 1 ? 0.5 : (index / (tickCount - 1))
    const tickTs = minTs + (span * ratio)
    return {
      x: xFromTimestamp(tickTs),
      label: formatAxisTime(new Date(tickTs).toISOString())
    }
  })

  const series = Object.fromEntries(
    crossAssetSeriesConfig.map((seriesMeta) => {
      const points = items.map((item) => {
        const score = Number(item?.scores?.[seriesMeta.key] || 0)
        const x = xFromTimestamp(parseThermometerTimestamp(item.last_event_time || item.time || item.first_event_time))
        const y = chartYFromScore(score)
        return { x, y, score }
      })
      return [seriesMeta.key, points]
    })
  )

  const eventPins = items.map((item) => {
    const ts = parseThermometerTimestamp(item.last_event_time || item.time || item.first_event_time)
    const score = Number(item?.scores?.general || 0)
    const bias = score > 6 ? 'buy' : score < -6 ? 'sell' : 'watch'
    return {
      raw: item,
      driver_id: item.driver_id,
      x: xFromTimestamp(ts),
      y: chartYFromScore(score),
      biasClass: bias
    }
  })

  const firstItem = items[0]
  const lastItem = items[items.length - 1]
  return {
    width: THERMOMETER_CHART_WIDTH,
    height: THERMOMETER_CHART_HEIGHT,
    plotLeft: THERMOMETER_PLOT_LEFT,
    plotRight: THERMOMETER_PLOT_RIGHT,
    plotTop: THERMOMETER_PLOT_TOP,
    plotBottom: THERMOMETER_PLOT_BOTTOM,
    yTicks,
    xTicks,
    series,
    eventPins,
    timeRangeLabel: firstItem && lastItem
      ? `${formatAxisTime(firstItem.time)} -> ${formatAxisTime(lastItem.time)}`
      : 'Awaiting cross-asset reactions'
  }
})

const activeCrossAssetDriverId = computed(() => {
  if (hoveredCrossAssetDriverId.value) return hoveredCrossAssetDriverId.value
  if (selectedDriverId.value) return selectedDriverId.value
  return macroCrossAssetTimeline.value[macroCrossAssetTimeline.value.length - 1]?.driver_id || ''
})

const activeCrossAssetEvent = computed(() => (
  macroCrossAssetTimeline.value.find((item) => item.driver_id === activeCrossAssetDriverId.value)
  || macroCrossAssetTimeline.value[macroCrossAssetTimeline.value.length - 1]
  || null
))

const activeCrossAssetPin = computed(() => (
  crossAssetChart.value.eventPins.find((pin) => pin.driver_id === activeCrossAssetDriverId.value) || null
))

const buildCrossAssetLinePoints = (seriesKey) => {
  const points = crossAssetChart.value.series?.[seriesKey] || []
  return points.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ')
}

const crossAssetLinePoints = computed(() => Object.fromEntries(
  crossAssetSeriesConfig.map((seriesMeta) => [seriesMeta.key, buildCrossAssetLinePoints(seriesMeta.key)])
))

const focusedDriverCrossAsset = computed(() => focusedDriver.value?.driver_cross_asset?.driver || null)
const focusedDriverAgentAudit = computed(() => focusedDriver.value?.driver?.agent_audit_report || null)
const focusedDriverElasticityRows = computed(() => focusedDriver.value?.driver?.market_elasticity?.rows || [])
const focusedDriverElasticityLiveWindow = computed(() => Boolean(focusedDriver.value?.driver?.market_elasticity?.live_window_open))
const focusedDriverThermometerTimeline = computed(() => focusedDriverCrossAsset.value?.headline_thermometer?.timeline || [])
const focusedDriverThermometerLatest = computed(() => focusedDriverCrossAsset.value?.headline_thermometer?.latest || {})
const focusedDriverInteractionGraph = computed(() => focusedDriverCrossAsset.value?.asset_interaction_graph || { nodes: [], edges: [] })

watch(focusedDriverThermometerTimeline, (items) => {
  if (!items.length) {
    selectedFocusedDriverHeadlineEventId.value = ''
    hoveredFocusedDriverHeadlineEventId.value = ''
    return
  }

  const hasSelected = items.some((item) => item.event_id === selectedFocusedDriverHeadlineEventId.value)
  if (!hasSelected) {
    selectedFocusedDriverHeadlineEventId.value = items[items.length - 1]?.event_id || ''
  }
})

const isFocusedDriverSeriesVisible = (seriesKey) => visibleFocusedDriverSeries.value.includes(seriesKey)

const toggleFocusedDriverSeries = (seriesKey) => {
  if (isFocusedDriverSeriesVisible(seriesKey)) {
    if (visibleFocusedDriverSeries.value.length === 1) return
    visibleFocusedDriverSeries.value = visibleFocusedDriverSeries.value.filter((item) => item !== seriesKey)
    return
  }
  visibleFocusedDriverSeries.value = [...visibleFocusedDriverSeries.value, seriesKey]
}

const selectFocusedDriverHeadline = (eventId) => {
  if (!eventId) return
  selectedFocusedDriverHeadlineEventId.value = eventId
  hoveredFocusedDriverHeadlineEventId.value = ''
}

const focusedDriverThermometerChart = computed(() => {
  const items = focusedDriverThermometerTimeline.value
  const timestamps = items
    .map((item) => parseThermometerTimestamp(item.time))
    .filter((value) => Number.isFinite(value))

  const fallbackTs = Date.now()
  const minTs = timestamps.length ? Math.min(...timestamps) : fallbackTs
  const maxTs = timestamps.length ? Math.max(...timestamps) : fallbackTs
  const span = Math.max(maxTs - minTs, 1)
  const plotWidth = THERMOMETER_PLOT_RIGHT - THERMOMETER_PLOT_LEFT

  const xFromTimestamp = (timestamp) => {
    if (!Number.isFinite(timestamp)) return THERMOMETER_PLOT_LEFT + (plotWidth / 2)
    if (maxTs === minTs) return THERMOMETER_PLOT_LEFT + (plotWidth / 2)
    return THERMOMETER_PLOT_LEFT + (((timestamp - minTs) / span) * plotWidth)
  }

  const yTicks = [100, 50, 0, -50, -100].map((value) => ({
    value,
    label: value > 0 ? `+${value}` : `${value}`,
    y: chartYFromScore(value)
  }))

  const tickCount = items.length > 1 ? Math.min(6, items.length) : 2
  const xTicks = Array.from({ length: tickCount }, (_, index) => {
    const ratio = tickCount === 1 ? 0.5 : (index / (tickCount - 1))
    const tickTs = minTs + (span * ratio)
    return {
      x: xFromTimestamp(tickTs),
      label: formatAxisTime(new Date(tickTs).toISOString())
    }
  })

  const series = Object.fromEntries(
    crossAssetSeriesConfig.map((seriesMeta) => {
      const points = items.map((item) => {
        const score = Number(item?.scores?.[seriesMeta.key] || 0)
        const x = xFromTimestamp(parseThermometerTimestamp(item.time))
        const y = chartYFromScore(score)
        return { x, y, score }
      })
      return [seriesMeta.key, points]
    })
  )

  const eventPins = items.map((item) => {
    const ts = parseThermometerTimestamp(item.time)
    const score = Number(item?.scores?.general || 0)
    const bias = item?.event_bias || (score > 6 ? 'buy' : score < -6 ? 'sell' : 'watch')
    return {
      raw: item,
      event_id: item.event_id,
      x: xFromTimestamp(ts),
      y: chartYFromScore(score),
      biasClass: bias
    }
  })

  const firstItem = items[0]
  const lastItem = items[items.length - 1]
  return {
    width: THERMOMETER_CHART_WIDTH,
    height: THERMOMETER_CHART_HEIGHT,
    plotLeft: THERMOMETER_PLOT_LEFT,
    plotRight: THERMOMETER_PLOT_RIGHT,
    plotTop: THERMOMETER_PLOT_TOP,
    plotBottom: THERMOMETER_PLOT_BOTTOM,
    yTicks,
    xTicks,
    series,
    eventPins,
    timeRangeLabel: firstItem && lastItem
      ? `${formatAxisTime(firstItem.time)} -> ${formatAxisTime(lastItem.time)}`
      : 'Awaiting headline chain'
  }
})

const activeFocusedDriverHeadlineEventId = computed(() => {
  if (hoveredFocusedDriverHeadlineEventId.value) return hoveredFocusedDriverHeadlineEventId.value
  if (selectedFocusedDriverHeadlineEventId.value) return selectedFocusedDriverHeadlineEventId.value
  return focusedDriverThermometerTimeline.value[focusedDriverThermometerTimeline.value.length - 1]?.event_id || ''
})

const activeFocusedDriverHeadlineEvent = computed(() => (
  focusedDriverThermometerTimeline.value.find((item) => item.event_id === activeFocusedDriverHeadlineEventId.value)
  || focusedDriverThermometerTimeline.value[focusedDriverThermometerTimeline.value.length - 1]
  || null
))

const activeFocusedDriverPin = computed(() => (
  focusedDriverThermometerChart.value.eventPins.find((pin) => pin.event_id === activeFocusedDriverHeadlineEventId.value) || null
))

const buildFocusedDriverLinePoints = (seriesKey) => {
  const points = focusedDriverThermometerChart.value.series?.[seriesKey] || []
  return points.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ')
}

const focusedDriverLinePoints = computed(() => Object.fromEntries(
  crossAssetSeriesConfig.map((seriesMeta) => [seriesMeta.key, buildFocusedDriverLinePoints(seriesMeta.key)])
))

const focusedDriverInteractionLayout = computed(() => {
  const graph = focusedDriverInteractionGraph.value
  const nodes = graph?.nodes || []
  const edges = graph?.edges || []
  const width = 760
  const height = 360
  const centerX = width / 2
  const centerY = height / 2
  const driverNode = nodes.find((node) => node.type === 'driver') || null
  const bucketNodes = nodes.filter((node) => node.type === 'bucket')
  const assetNodes = nodes.filter((node) => node.type === 'asset')
  const innerRadius = 110
  const outerRadius = 195
  const positioned = []
  const nodeMap = new Map()

  if (driverNode) {
    const positionedNode = {
      ...driverNode,
      x: centerX,
      y: centerY,
      radius: 28,
      displayLabel: String(driverNode.label || 'driver').slice(0, 18)
    }
    positioned.push(positionedNode)
    nodeMap.set(driverNode.id, positionedNode)
  }

  bucketNodes.forEach((node, index) => {
    const angle = (-Math.PI / 2) + ((Math.PI * 2) * index / Math.max(bucketNodes.length, 1))
    const positionedNode = {
      ...node,
      x: centerX + (Math.cos(angle) * innerRadius),
      y: centerY + (Math.sin(angle) * innerRadius),
      radius: 18,
      angle,
      displayLabel: String(node.label || node.id).slice(0, 12)
    }
    positioned.push(positionedNode)
    nodeMap.set(node.id, positionedNode)
  })

  const assetBuckets = {}
  assetNodes.forEach((node) => {
    const bucket = node.bucket || 'other'
    if (!assetBuckets[bucket]) assetBuckets[bucket] = []
    assetBuckets[bucket].push(node)
  })

  Object.entries(assetBuckets).forEach(([bucket, bucketAssets]) => {
    const bucketNode = nodeMap.get(`bucket::${bucket}`)
    const baseAngle = bucketNode?.angle ?? 0
    bucketAssets.forEach((node, index) => {
      const spread = (index - ((bucketAssets.length - 1) / 2)) * 0.28
      const angle = baseAngle + spread
      const positionedNode = {
        ...node,
        x: centerX + (Math.cos(angle) * outerRadius),
        y: centerY + (Math.sin(angle) * outerRadius),
        radius: 11,
        displayLabel: String(node.label || node.id).replace('BVMF:', '').slice(0, 14)
      }
      positioned.push(positionedNode)
      nodeMap.set(node.id, positionedNode)
    })
  })

  const positionedEdges = edges
    .map((edge) => {
      const source = nodeMap.get(edge.source)
      const target = nodeMap.get(edge.target)
      if (!source || !target) return null
      return {
        ...edge,
        x1: source.x,
        y1: source.y,
        x2: target.x,
        y2: target.y,
      }
    })
    .filter(Boolean)

  return { width, height, nodes: positioned, edges: positionedEdges }
})

watch(thermometerTimeline, (items) => {
  if (!items.length) {
    selectedThermometerEventId.value = ''
    hoveredThermometerEventId.value = ''
    return
  }

  const hasSelected = items.some((item) => item.event_id === selectedThermometerEventId.value)
  if (!hasSelected) {
    selectedThermometerEventId.value = items[items.length - 1]?.event_id || ''
  }
})

const loadMacroThermometer = async (forceReload = false) => {
  if (!showMacroDashboard.value) return
  if (macroThermometerLoading.value && !forceReload) return

  macroThermometerLoading.value = true
  macroThermometerError.value = ''

  try {
    const res = await getMacroThermometer({
      refresh: Boolean(forceReload)
    })
    const payload = normalizeThermometerPayload(res?.data || res || null)
    macroThermometer.value = payload
    const thermo = payload?.thermometer || payload?.data?.thermometer || null
    if (!thermo) {
      macroThermometerError.value = 'Macro thermometer payload came back empty.'
    }
  } catch (err) {
    macroThermometerError.value = err.message || 'Failed to load thermometer.'
  } finally {
    macroThermometerLoading.value = false
  }
}

const loadMacroCrossAsset = async (forceReload = false) => {
  if (!showMacroDashboard.value) return
  if (macroCrossAssetLoading.value && !forceReload) return

  macroCrossAssetLoading.value = true
  macroCrossAssetError.value = ''

  try {
    const res = await getMacroCrossAsset({
      limit: MACRO_CROSS_ASSET_LIMIT,
      refresh: Boolean(forceReload)
    })
    macroCrossAsset.value = res.data || null
  } catch (err) {
    macroCrossAssetError.value = err.message || 'Failed to load cross-asset engine.'
  } finally {
    macroCrossAssetLoading.value = false
  }
}

const loadMacroCollectorStatus = async () => {
  if (!showMacroDashboard.value) return
  try {
    const res = await getMacroCollectorStatus()
    macroCollectorStatus.value = res.data || null
    macroCollectorError.value = ''
  } catch (err) {
    macroCollectorError.value = err.message || 'Failed to load collector status.'
  }
}

const loadMacroEvents = async () => {
  if (!showMacroDashboard.value) return
  try {
    const res = await getMacroEvents({
      limit: 100
    })
    macroRawEvents.value = res.data?.events || []
  } catch (err) {
    console.warn('Failed to load raw macro events:', err)
  }
}

const loadMacroDrivers = async (forceReload = false) => {
  if (!showMacroDashboard.value) return
  if (macroDriversLoading.value && !forceReload) return

  macroDriversLoading.value = true
  macroDriverError.value = ''

  try {
    const res = await getMacroDrivers({
      limit: 100,
      refresh: Boolean(forceReload)
    })
    const payload = res.data || {}
    macroDrivers.value = payload.drivers || []
    macroNewsFeed.value = payload.news_feed || []

    if (macroDrivers.value.length > 0) {
      const availableDriverIds = new Set(macroDrivers.value.map(item => item.driver_id))
      const desiredDriver = availableDriverIds.has(selectedDriverId.value)
        ? findLoadedDriver(selectedDriverId.value)
        : macroDrivers.value[0]

      const focusedDriverVersion = buildDriverVersionKey(focusedDriver.value?.driver)
      const desiredDriverVersion = buildDriverVersionKey(desiredDriver)
      const shouldFocusDriver = Boolean(
        desiredDriver?.driver_id && (
          forceReload
          || !focusedDriver.value?.driver
          || focusedDriver.value.driver.driver_id !== desiredDriver.driver_id
          || focusedDriverVersion !== desiredDriverVersion
        )
      )
      const sameDriverAlreadyLoading = Boolean(
        desiredDriver?.driver_id
        && (focusingDriver.value || refreshingFocusedDriver.value)
        && selectedDriverId.value === desiredDriver.driver_id
      )

      if (shouldFocusDriver && !sameDriverAlreadyLoading) {
        await handleDriverFocus(desiredDriver.driver_id, {
          silent: true,
          preserveCurrent: Boolean(
            focusedDriver.value?.driver
            && focusedDriver.value.driver.driver_id === desiredDriver.driver_id
          ),
        })
      }
    } else {
      selectedDriverId.value = ''
      focusedDriver.value = null
      focusingDriver.value = false
      refreshingFocusedDriver.value = false
    }
  } catch (err) {
    macroDriverError.value = err.message || 'Failed to load impact drivers.'
  } finally {
    macroDriversLoading.value = false
  }
}

const handleDriverFocus = async (driverId, options = {}) => {
  if (!driverId) return
  const loadedDriver = findLoadedDriver(driverId)
  const loadedDriverVersion = buildDriverVersionKey(loadedDriver)
  const focusedDriverVersion = buildDriverVersionKey(focusedDriver.value?.driver)
  const preserveCurrent = Boolean(
    options.preserveCurrent
    && focusedDriver.value?.driver
    && focusedDriver.value.driver.driver_id === driverId
  )
  const sameDriverAlreadyLoading = Boolean(
    (focusingDriver.value || refreshingFocusedDriver.value)
    && selectedDriverId.value === driverId
  )

  if (
    sameDriverAlreadyLoading
    || (
    !options.force
    && focusedDriver.value?.driver?.driver_id === driverId
    && loadedDriverVersion
    && loadedDriverVersion === focusedDriverVersion
    )
  ) {
    selectedDriverId.value = driverId
    return
  }

  selectedDriverId.value = driverId
  if (preserveCurrent) {
    refreshingFocusedDriver.value = true
  } else {
    focusingDriver.value = true
    refreshingFocusedDriver.value = false
  }
  macroDriverError.value = ''
  const requestId = ++activeDriverFocusRequestId

  try {
    const res = await focusMacroDriver({
      driver_id: driverId,
      refresh: Boolean(options.refresh)
    })
    if (requestId !== activeDriverFocusRequestId) return
    focusedDriver.value = res.data || null
  } catch (err) {
    if (requestId !== activeDriverFocusRequestId) return
    macroDriverError.value = err.message || 'Failed to focus driver.'
    if (!options.silent) {
      console.warn('Failed to focus macro driver:', err)
    }
  } finally {
    if (requestId === activeDriverFocusRequestId) {
      focusingDriver.value = false
      refreshingFocusedDriver.value = false
    }
  }
}

const loadMacroTrends = async (forceReload = false) => {
  if (!canLoadMacroTrends.value) return
  if (macroTrendsLoading.value && !forceReload) return

  macroTrendsLoading.value = true
  macroTrendError.value = ''

  try {
    const res = await getMacroTrends({
      project_id: props.projectData.project_id,
      graph_id: props.projectData.graph_id,
      limit: 8
    })
    macroTrends.value = res.data?.trends || []

    if (macroTrends.value.length > 0) {
      const desiredTrendId = selectedTrendId.value || macroTrends.value[0].trend_id
      await handleTrendFocus(desiredTrendId, { silent: true })
      if (!forceReload) {
        console.info('Macro trendboard loaded.')
      }
    } else {
      focusedTrend.value = null
      selectedTrendId.value = ''
    }
  } catch (err) {
    macroTrendError.value = err.message || 'Failed to load macro trends.'
  } finally {
    macroTrendsLoading.value = false
  }
}

const loadMacroDashboard = async (forceReload = false) => {
  const primaryLoads = [
    loadMacroCollectorStatus(),
    loadMacroEvents(),
    loadMacroCrossAsset(forceReload),
    loadMacroOverview(forceReload),
    loadMacroDrivers(forceReload),
  ]
  const secondaryLoads = [
    loadMacroThermometer(forceReload),
    loadMacroTrends(forceReload)
  ]
  await Promise.allSettled(primaryLoads)
  await Promise.allSettled(secondaryLoads)
}

const handleTrendFocus = async (trendId, options = {}) => {
  if (!trendId || !props.projectData?.project_id || !props.projectData?.graph_id) return

  selectedTrendId.value = trendId
  focusingTrend.value = true
  macroTrendError.value = ''

  try {
    const res = await focusMacroTrend({
      trend_id: trendId,
      project_id: props.projectData.project_id,
      graph_id: props.projectData.graph_id,
      comment_count: 5
    })
    focusedTrend.value = res.data
  } catch (err) {
    macroTrendError.value = err.message || 'Failed to focus trend.'
    if (!options.silent) {
      console.warn('Failed to focus macro trend:', err)
    }
  } finally {
    focusingTrend.value = false
  }
}

// Auto-scroll logs
watch(() => props.systemLogs.length, () => {
  nextTick(() => {
    if (logContent.value) {
      logContent.value.scrollTop = logContent.value.scrollHeight
    }
  })
})

watch(
  () => [showMacroDashboard.value, canLoadMacroTrends.value, props.projectData?.graph_id],
  async ([dashboardEnabled, trendEnabled, graphId], [prevDashboardEnabled, prevTrendEnabled, prevGraphId] = []) => {
    if (!dashboardEnabled) return
    if (dashboardEnabled !== prevDashboardEnabled) {
      await Promise.allSettled([
        loadMacroCollectorStatus(),
        loadMacroEvents(),
        loadMacroCrossAsset(false),
        loadMacroOverview(false),
        loadMacroDrivers(false)
      ])
      void loadMacroThermometer(false)
    }
    if (!trendEnabled || !graphId) return
    if (trendEnabled !== prevTrendEnabled || graphId !== prevGraphId) {
      await loadMacroTrends(false)
    }
  },
  { immediate: true }
)

onMounted(() => {
  macroPollingTimer = window.setInterval(async () => {
    if (!showMacroDashboard.value) return
    await Promise.allSettled([
      loadMacroCollectorStatus(),
      loadMacroEvents(),
      loadMacroCrossAsset(false),
      loadMacroDrivers(false),
    ])
    void loadMacroThermometer(false)
  }, 45000)

  focusedDriverElasticityTimer = window.setInterval(async () => {
    if (!showMacroDashboard.value) return
    if (!focusedDriverElasticityLiveWindow.value) return
    const driverId = focusedDriver.value?.driver?.driver_id
    if (!driverId) return
    await handleDriverFocus(driverId, {
      silent: true,
      preserveCurrent: true,
      force: true,
      refresh: true
    })
  }, 10000)
})

onBeforeUnmount(() => {
  if (macroPollingTimer) {
    window.clearInterval(macroPollingTimer)
    macroPollingTimer = null
  }
  if (focusedDriverElasticityTimer) {
    window.clearInterval(focusedDriverElasticityTimer)
    focusedDriverElasticityTimer = null
  }
})
</script>

<style scoped>
.workbench-panel {
  height: 100%;
  background-color: #FAFAFA;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}

.scroll-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.step-card {
  background: #FFF;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  border: 1px solid #EAEAEA;
  transition: all 0.3s ease;
  position: relative; /* For absolute overlay */
}

.step-card.active {
  border-color: #FF5722;
  box-shadow: 0 4px 12px rgba(255, 87, 34, 0.08);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.step-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.step-num {
  font-family: 'JetBrains Mono', monospace;
  font-size: 20px;
  font-weight: 700;
  color: #E0E0E0;
}

.step-card.active .step-num,
.step-card.completed .step-num {
  color: #000;
}

.step-title {
  font-weight: 600;
  font-size: 14px;
  letter-spacing: 0.5px;
}

.badge {
  font-size: 10px;
  padding: 4px 8px;
  border-radius: 4px;
  font-weight: 600;
  text-transform: uppercase;
}

.badge.success { background: #E8F5E9; color: #2E7D32; }
.badge.processing { background: #FF5722; color: #FFF; }
.badge.accent { background: #FF5722; color: #FFF; }
.badge.pending { background: #F5F5F5; color: #999; }

.api-note {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #999;
  margin-bottom: 8px;
}

.description {
  font-size: 12px;
  color: #666;
  line-height: 1.5;
  margin-bottom: 16px;
}

.source-mode-banner {
  margin-bottom: 16px;
  padding: 14px;
  border: 1px solid #EAEAEA;
  background: #FAFAFA;
  border-radius: 8px;
}

.source-mode-banner.macro {
  border-color: #111;
  background: linear-gradient(180deg, #fff 0%, #f4f4f4 100%);
}

.source-mode-label {
  display: block;
  font-size: 10px;
  font-weight: 700;
  color: #999;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin-bottom: 6px;
}

.source-mode-title {
  font-size: 13px;
  font-weight: 700;
  color: #111;
  margin-bottom: 6px;
}

.source-mode-text {
  font-size: 12px;
  color: #666;
  line-height: 1.5;
}

.source-mode-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.source-pill {
  background: #111;
  color: #fff;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  padding: 5px 8px;
  border-radius: 999px;
}

/* Step 01 Tags */
.tags-container {
  margin-top: 12px;
  transition: opacity 0.3s;
}

.tags-container.dimmed {
    opacity: 0.3;
    pointer-events: none;
}

.tag-label {
  display: block;
  font-size: 10px;
  color: #AAA;
  margin-bottom: 8px;
  font-weight: 600;
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.entity-tag {
  background: #F5F5F5;
  border: 1px solid #EEE;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 11px;
  color: #333;
  font-family: 'JetBrains Mono', monospace;
  transition: all 0.2s;
}

.entity-tag.clickable {
    cursor: pointer;
}

.entity-tag.clickable:hover {
    background: #E0E0E0;
    border-color: #CCC;
}

/* Ontology Detail Overlay */
.ontology-detail-overlay {
    position: absolute;
    top: 60px; /* Below header roughly */
    left: 20px;
    right: 20px;
    bottom: 20px;
    background: rgba(255, 255, 255, 0.98);
    backdrop-filter: blur(4px);
    z-index: 10;
    border: 1px solid #EAEAEA;
    box-shadow: 0 4px 20px rgba(0,0,0,0.05);
    border-radius: 6px;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    animation: fadeIn 0.2s ease-out;
}

@keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }

.detail-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    border-bottom: 1px solid #EAEAEA;
    background: #FAFAFA;
}

.detail-title-group {
    display: flex;
    align-items: center;
    gap: 8px;
}

.detail-type-badge {
    font-size: 9px;
    font-weight: 700;
    color: #FFF;
    background: #000;
    padding: 2px 6px;
    border-radius: 2px;
    text-transform: uppercase;
}

.detail-name {
    font-size: 14px;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
}

.close-btn {
    background: none;
    border: none;
    font-size: 18px;
    color: #999;
    cursor: pointer;
    line-height: 1;
}

.close-btn:hover {
    color: #333;
}

.detail-body {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
}

.detail-desc {
    font-size: 12px;
    color: #444;
    line-height: 1.5;
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 1px dashed #EAEAEA;
}

.detail-section {
    margin-bottom: 16px;
}

.section-label {
    display: block;
    font-size: 10px;
    font-weight: 600;
    color: #AAA;
    margin-bottom: 8px;
}

.attr-list, .conn-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.attr-item {
    font-size: 11px;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: baseline;
    padding: 4px;
    background: #F9F9F9;
    border-radius: 4px;
}

.attr-name {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 600;
    color: #000;
}

.attr-type {
    color: #999;
    font-size: 10px;
}

.attr-desc {
    color: #555;
    flex: 1;
    min-width: 150px;
}

.example-list {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
}

.example-tag {
    font-size: 11px;
    background: #FFF;
    border: 1px solid #E0E0E0;
    padding: 3px 8px;
    border-radius: 12px;
    color: #555;
}

.conn-item {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 11px;
    padding: 6px;
    background: #F5F5F5;
    border-radius: 4px;
    font-family: 'JetBrains Mono', monospace;
}

.conn-node {
    font-weight: 600;
    color: #333;
}

.conn-arrow {
    color: #BBB;
}

/* Step 02 Stats */
.stats-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
  background: #F9F9F9;
  padding: 16px;
  border-radius: 6px;
}

.stat-card {
  text-align: center;
}

.stat-value {
  display: block;
  font-size: 20px;
  font-weight: 700;
  color: #000;
  font-family: 'JetBrains Mono', monospace;
}

.stat-label {
  font-size: 9px;
  color: #999;
  text-transform: uppercase;
  margin-top: 4px;
  display: block;
}

/* Step 03 Button */
.action-btn {
  width: 100%;
  background: #000;
  color: #FFF;
  border: none;
  padding: 14px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
}

.action-btn:hover:not(:disabled) {
  opacity: 0.8;
}

.action-btn:disabled {
  background: #CCC;
  cursor: not-allowed;
}

.secondary-inline {
  width: auto;
  background: #FFF;
  color: #111;
  border: 1px solid #DDD;
  padding: 10px 12px;
}

.macro-trendboard {
  border-color: #111;
}

.macro-overview-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 18px;
}

.overview-panel {
  border: 1px solid #EAEAEA;
  border-radius: 10px;
  background: #FFF;
  padding: 14px;
}

.overview-summary-panel {
  grid-column: span 2;
  background: linear-gradient(180deg, #111 0%, #1c1c1c 100%);
  color: #FFF;
}

.overview-summary-top {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 14px;
}

.overview-title {
  font-size: 18px;
  font-weight: 700;
  margin-bottom: 6px;
}

.overview-subtitle {
  font-size: 13px;
  line-height: 1.6;
  color: #D4D4D4;
}

.overview-badges {
  display: flex;
  gap: 8px;
}

.overview-kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}

.overview-kpi {
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  padding: 10px;
  background: rgba(255, 255, 255, 0.04);
}

.overview-kpi-label {
  display: block;
  font-size: 10px;
  color: #BDBDBD;
  text-transform: uppercase;
  margin-bottom: 6px;
}

.overview-kpi-value {
  display: block;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  font-weight: 700;
  color: #FFF;
}

.overview-ai-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.overview-ai-block p,
.overview-participant-comment,
.overview-news-summary {
  margin: 0;
  font-size: 12px;
  line-height: 1.65;
}

.overview-asset-list,
.overview-participant-list,
.overview-news-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.overview-asset-item,
.overview-participant-item,
.overview-news-item {
  border: 1px solid #EEEEEE;
  border-radius: 8px;
  padding: 10px;
  background: #FAFAFA;
}

.overview-asset-top,
.overview-participant-top,
.overview-news-top {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
  margin-bottom: 6px;
}

.overview-asset-name,
.overview-participant-name,
.overview-news-title {
  font-size: 12px;
  font-weight: 700;
  color: #111;
}

.overview-asset-meta,
.overview-participant-meta,
.overview-news-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 11px;
  color: #777;
}

.trendboard-actions {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}

.collector-status-banner {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  padding: 8px 12px;
  border-radius: 999px;
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
  background: #FFF3E0;
  color: #EF6C00;
}

.collector-status-banner.success {
  background: #E8F5E9;
  color: #2E7D32;
}

.collector-status-banner.error {
  background: #FFF5F5;
  color: #C62828;
}

.collector-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
}

.thermometer-card {
  border: 1px solid #111;
  border-radius: 12px;
  background: linear-gradient(180deg, #111 0%, #1c1c1c 100%);
  color: #fff;
  padding: 18px;
  margin-bottom: 18px;
}

.cross-asset-card {
  border: 1px solid #0f172a;
  border-radius: 12px;
  background: linear-gradient(180deg, #0b1220 0%, #121c2f 100%);
  color: #fff;
  padding: 18px;
  margin-bottom: 18px;
}

.thermometer-top {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 16px;
}

.thermometer-top .overview-subtitle {
  color: #d4d4d4;
}

.thermometer-top-badges {
  display: flex;
  gap: 8px;
}

.thermometer-kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}

.thermometer-kpi-card {
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 10px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.05);
}

.thermometer-kpi-top {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  align-items: center;
}

.thermometer-kpi-label {
  font-size: 10px;
  color: #bdbdbd;
  text-transform: uppercase;
}

.thermometer-kpi-value {
  font-size: 18px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
  margin-bottom: 10px;
}

.thermometer-bar-track {
  position: relative;
  height: 10px;
  border-radius: 999px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.08);
}

.thermometer-bar-track::before {
  content: '';
  position: absolute;
  left: 50%;
  top: 0;
  bottom: 0;
  width: 1px;
  background: rgba(255, 255, 255, 0.25);
}

.thermometer-bar-fill {
  position: absolute;
  top: 0;
  bottom: 0;
  border-radius: 999px;
  background: #ffa726;
}

.thermometer-bar-fill.buy {
  background: #66bb6a;
}

.thermometer-bar-fill.sell {
  background: #ef5350;
}

.thermometer-chart-panel {
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.04);
  padding: 14px;
  margin-bottom: 16px;
}

.thermometer-chart-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.thermometer-chart-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #b9b9b9;
  text-transform: uppercase;
}

.thermometer-chart-stage {
  position: relative;
  margin-top: 10px;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.09);
  background:
    radial-gradient(circle at top, rgba(255, 255, 255, 0.06), transparent 45%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.04), rgba(255, 255, 255, 0.01));
}

.thermometer-chart {
  width: 100%;
  min-height: 220px;
  display: block;
}

.thermometer-grid-line {
  stroke: rgba(255, 255, 255, 0.09);
  stroke-width: 1;
}

.thermometer-grid-line.baseline {
  stroke: rgba(255, 255, 255, 0.2);
  stroke-dasharray: 4 4;
}

.thermometer-grid-line.vertical {
  stroke-dasharray: 3 6;
}

.thermometer-axis-label {
  fill: #a0a0a0;
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
}

.thermometer-axis-label.time {
  fill: #d8d8d8;
}

.thermometer-line {
  fill: none;
  stroke-width: 3;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.thermometer-line.general {
  stroke: #ffffff;
}

.thermometer-line.credit {
  stroke: #ffb74d;
}

.thermometer-line.equity {
  stroke: #66bb6a;
}

.thermometer-line.fx {
  stroke: #ef5350;
}

.thermometer-line.commodity {
  stroke: #29b6f6;
}

.thermometer-line.rates {
  stroke: #ab47bc;
}

.thermometer-event-guide {
  stroke: rgba(255, 255, 255, 0.28);
  stroke-width: 1;
  stroke-dasharray: 4 5;
}

.thermometer-active-guide {
  stroke: rgba(255, 255, 255, 0.34);
  stroke-width: 1;
  stroke-dasharray: 4 5;
}

.thermometer-event-pin {
  cursor: pointer;
  transition: opacity 0.18s ease;
}

.thermometer-event-pin.muted {
  opacity: 0.38;
}

.thermometer-pin-stem {
  stroke: rgba(255, 255, 255, 0.12);
  stroke-width: 1;
}

.thermometer-pin-core {
  stroke: rgba(18, 18, 18, 0.88);
  stroke-width: 1.5;
  fill: #ffb74d;
}

.thermometer-pin-core.buy {
  fill: #66bb6a;
}

.thermometer-pin-core.sell {
  fill: #ef5350;
}

.thermometer-pin-core.watch {
  fill: #ffb74d;
}

.thermometer-pin-halo {
  fill: rgba(255, 255, 255, 0.08);
  stroke: rgba(255, 255, 255, 0.08);
}

.thermometer-event-pin.selected .thermometer-pin-halo {
  fill: rgba(255, 255, 255, 0.16);
  stroke: rgba(255, 255, 255, 0.22);
}

.thermometer-event-detail {
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.04);
}

.thermometer-event-detail-top {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
  margin-bottom: 8px;
}

.thermometer-event-detail-title {
  font-size: 13px;
  font-weight: 700;
  line-height: 1.55;
  color: #ffffff;
  margin-bottom: 8px;
}

.thermometer-event-detail-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 11px;
  color: #c9c9c9;
}

.thermometer-event-audit {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.thermometer-event-audit-text {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.55;
  color: #f0f0f0;
}

.thermometer-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 8px;
  font-size: 11px;
  color: #d0d0d0;
}

.legend-item {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}

.legend-button {
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 999px;
  padding: 6px 10px;
  background: rgba(255, 255, 255, 0.04);
  color: inherit;
  cursor: pointer;
  transition: all 0.2s ease;
}

.legend-button:hover {
  border-color: rgba(255, 255, 255, 0.32);
}

.legend-button.inactive {
  opacity: 0.42;
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.legend-dot.general {
  background: #ffffff;
}

.legend-dot.credit {
  background: #ffb74d;
}

.legend-dot.equity {
  background: #66bb6a;
}

.legend-dot.fx {
  background: #ef5350;
}

.legend-dot.commodity {
  background: #29b6f6;
}

.legend-dot.rates {
  background: #ab47bc;
}

.thermometer-grid {
  display: grid;
  grid-template-columns: 1.1fr 1fr;
  gap: 16px;
}

.cross-asset-grid {
  display: grid;
  grid-template-columns: 1.2fr 1fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}

.cross-asset-bucket-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 14px;
}

.cross-asset-bucket-card {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.04);
}

.cross-asset-leaders {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.cross-asset-mini-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: rgba(255, 255, 255, 0.72);
}

.cross-asset-insight-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.cross-asset-insight-item {
  text-align: left;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
  border-radius: 10px;
  padding: 12px;
  cursor: pointer;
  transition: all 0.18s ease;
  color: #fff;
}

.cross-asset-insight-item:hover {
  border-color: rgba(255, 183, 77, 0.75);
  background: rgba(255, 183, 77, 0.08);
}

.thermometer-timeline-list,
.thermometer-entity-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 420px;
  overflow-y: auto;
}

.thermometer-timeline-item,
.thermometer-entity-card {
  border: 1px solid #eeeeee;
  border-radius: 8px;
  padding: 10px;
  background: #fafafa;
  color: #111;
}

.thermometer-timeline-item {
  cursor: pointer;
  transition: all 0.2s ease;
}

.thermometer-timeline-item:hover,
.thermometer-timeline-item.selected {
  background: #fff7f2;
  border-color: #ff5722;
}

.thermometer-timeline-top,
.thermometer-entity-top {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
  margin-bottom: 6px;
}

.thermometer-timeline-title {
  font-size: 12px;
  font-weight: 700;
  line-height: 1.5;
  margin-bottom: 6px;
}

.thermometer-timeline-meta,
.thermometer-entity-meta,
.thermometer-trade-plan {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 11px;
  color: #777;
}

.thermometer-timeline-audit {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(17, 17, 17, 0.08);
}

.thermometer-timeline-audit-text {
  margin-top: 6px;
  font-size: 11px;
  line-height: 1.55;
  color: #444;
}

.thermometer-timeline-audit-line + .thermometer-timeline-audit-line {
  margin-top: 4px;
}

.thermometer-trade-plan {
  margin-top: 8px;
}

.thermometer-ai-strip {
  margin-top: 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.12);
  padding-top: 12px;
}

.thermometer-ai-strip p {
  margin: 0;
  font-size: 12px;
  line-height: 1.65;
  color: #e8e8e8;
}

.raw-news-panel {
  margin-bottom: 18px;
}

.raw-news-top {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 14px;
}

.raw-news-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  max-height: 540px;
  overflow-y: auto;
  padding-right: 4px;
}

.raw-news-item {
  border: 1px solid #eeeeee;
  border-radius: 10px;
  padding: 12px;
  background: #fafafa;
}

.raw-news-item.promoted {
  border-color: #b7dfbf;
  background: #f4fbf5;
}

.raw-news-item.watch {
  border-color: #ffd89f;
  background: #fffaf2;
}

.raw-news-item.captured {
  border-color: #f0d5d5;
  background: #fff9f9;
}

.raw-news-title {
  font-size: 12px;
  font-weight: 700;
  color: #111;
  line-height: 1.55;
  margin-bottom: 8px;
}

.raw-news-meta,
.raw-news-state-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 11px;
  color: #777;
}

.raw-news-state-row {
  margin-top: 10px;
  align-items: center;
}

.raw-news-note {
  color: #555;
}

.driver-board-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 14px;
}

.driver-board-subtitle {
  font-size: 12px;
  line-height: 1.6;
  color: #666;
  margin-top: 6px;
}

.driver-board-badges {
  display: flex;
  gap: 8px;
}

.driver-board-grid {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.driver-focus-panel {
  border: 1px solid #EAEAEA;
  border-radius: 10px;
  background: linear-gradient(180deg, #ffffff 0%, #fafafa 100%);
  padding: 16px;
  min-height: 320px;
  margin-bottom: 18px;
}

.mini-empty-state {
  min-height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  font-size: 12px;
  color: #777;
  border: 1px dashed #DDD;
  border-radius: 8px;
  padding: 16px;
}

.mini-empty-state.dark {
  color: rgba(255, 255, 255, 0.72);
  border-color: rgba(255, 255, 255, 0.14);
}

.driver-news-list,
.driver-list,
.driver-update-list,
.driver-edge-list,
.driver-node-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.driver-news-item,
.driver-list-item,
.driver-update-item,
.driver-node-card,
.driver-edge-item {
  border: 1px solid #EEEEEE;
  border-radius: 8px;
  padding: 10px;
  background: #FAFAFA;
}

.driver-update-item {
  cursor: pointer;
  transition: all 0.18s ease;
}

.driver-update-item:hover,
.driver-update-item.active {
  border-color: #111;
  background: #FFF;
  box-shadow: 0 8px 22px rgba(0, 0, 0, 0.06);
}

.driver-list-item {
  text-align: left;
  cursor: pointer;
  transition: all 0.2s ease;
}

.driver-list-item:hover,
.driver-list-item.selected {
  background: #FFF7F2;
  border-color: #FF5722;
}

.driver-news-top,
.driver-item-top,
.driver-update-top,
.driver-asymmetry-top,
.driver-series-top,
.driver-participant-top {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
  margin-bottom: 6px;
}

.driver-news-title,
.driver-title,
.driver-update-title,
.driver-asymmetry-name,
.driver-series-name,
.driver-participant-name,
.driver-node-label {
  font-size: 12px;
  font-weight: 700;
  color: #111;
  line-height: 1.5;
}

.driver-news-meta,
.driver-meta,
.driver-update-meta,
.driver-asymmetry-meta,
.driver-series-meta,
.driver-participant-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 11px;
  color: #777;
}

.driver-news-driver,
.driver-summary {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.55;
  color: #555;
}

.driver-impact-meta {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 8px;
}

.driver-impact-reason,
.driver-callout-meta {
  font-size: 11px;
  line-height: 1.5;
  color: #777;
}

.driver-callout-grid,
.driver-graph-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.driver-cross-asset-grid {
  display: grid;
  grid-template-columns: 1.15fr 0.85fr;
  gap: 16px;
}

.driver-callout-card,
.driver-graph-panel {
  border: 1px solid #EAEAEA;
  border-radius: 10px;
  padding: 14px;
  background: #FFF;
}

.driver-cross-panel,
.driver-interaction-panel {
  border: 1px solid #EAEAEA;
  border-radius: 12px;
  padding: 14px;
  background: #FFF;
}

.driver-cross-panel.dark {
  border-color: #0f172a;
  background: linear-gradient(180deg, #0b1220 0%, #121c2f 100%);
  color: #FFF;
}

.driver-cross-panel.dark .focus-section-title {
  color: rgba(255, 255, 255, 0.72);
}

.driver-cross-subtitle {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.6;
  color: rgba(255, 255, 255, 0.72);
}

.driver-cross-commentary {
  margin: 8px 0 0 0;
  font-size: 12px;
  line-height: 1.7;
  color: #444;
}

.driver-cross-bucket-grid {
  margin-top: 12px;
}

.driver-cross-bucket-card {
  border-color: #EAEAEA;
  background: #FAFAFA;
}

.driver-cross-meta {
  margin-top: 12px;
  color: #666;
}

.driver-targeted-buckets {
  margin-top: 10px;
}

.driver-insight-list {
  margin-top: 12px;
}

.driver-insight-item {
  border-color: #EAEAEA;
  background: #FAFAFA;
}

.driver-callout-card p,
.driver-asymmetry-card p {
  margin: 8px 0 0 0;
  font-size: 12px;
  line-height: 1.65;
  color: #555;
}

.driver-callout-card.dark {
  background: #111;
  border-color: #111;
  color: #FFF;
}

.driver-callout-card.dark p {
  color: #F1F1F1;
}

.driver-callout-action {
  margin-top: 12px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  font-weight: 700;
  color: #FFD9C7;
}

.driver-asymmetry-grid,
.driver-series-grid,
.driver-participant-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.driver-asymmetry-card,
.driver-series-card,
.driver-participant-card {
  border: 1px solid #EAEAEA;
  border-radius: 10px;
  background: #FFF;
  padding: 12px;
}

.driver-timeline-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 10px;
}

.driver-thermometer-stage {
  margin-top: 12px;
}

.driver-interaction-stage {
  position: relative;
  margin-top: 12px;
  border: 1px solid #EAEAEA;
  border-radius: 12px;
  overflow: hidden;
  background:
    radial-gradient(circle at top, rgba(17, 17, 17, 0.04), transparent 42%),
    linear-gradient(180deg, #ffffff 0%, #fafafa 100%);
}

.driver-interaction-svg {
  width: 100%;
  min-height: 360px;
  display: block;
}

.driver-interaction-edge {
  stroke: rgba(15, 23, 42, 0.18);
  stroke-width: 2;
}

.driver-interaction-edge.confirms,
.driver-interaction-edge.pushes,
.driver-interaction-edge.leads {
  stroke: rgba(46, 125, 50, 0.48);
}

.driver-interaction-edge.diverges {
  stroke: rgba(198, 40, 40, 0.5);
}

.driver-interaction-edge.lags,
.driver-interaction-edge.echoes,
.driver-interaction-edge.tests {
  stroke-dasharray: 5 4;
  stroke: rgba(239, 108, 0, 0.46);
}

.driver-interaction-circle {
  stroke: rgba(15, 23, 42, 0.2);
  stroke-width: 1.4;
  fill: #fff;
}

.driver-interaction-node.driver .driver-interaction-circle {
  fill: #111;
  stroke: rgba(17, 17, 17, 0.84);
}

.driver-interaction-node.bucket.buy .driver-interaction-circle,
.driver-interaction-node.asset.buy .driver-interaction-circle {
  fill: #E8F5E9;
  stroke: #2E7D32;
}

.driver-interaction-node.bucket.sell .driver-interaction-circle,
.driver-interaction-node.asset.sell .driver-interaction-circle {
  fill: #FDECEC;
  stroke: #C62828;
}

.driver-interaction-node.bucket.watch .driver-interaction-circle,
.driver-interaction-node.asset.watch .driver-interaction-circle {
  fill: #FFF3E0;
  stroke: #EF6C00;
}

.driver-interaction-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  font-weight: 700;
  fill: #0f172a;
  pointer-events: none;
}

.driver-interaction-node.driver .driver-interaction-label {
  fill: #fff;
}

.driver-interaction-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.driver-impact-pill {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 10px;
  padding: 6px 10px;
  border-radius: 999px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  font-weight: 700;
  background: #FFF3E0;
  color: #EF6C00;
}

.driver-impact-pill.buy {
  background: #E8F5E9;
  color: #2E7D32;
}

.driver-impact-pill.sell {
  background: #FDECEC;
  color: #C62828;
}

.driver-timeline-item {
  display: grid;
  grid-template-columns: 78px 1fr 1fr;
  gap: 8px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #555;
  border-top: 1px solid #F0F0F0;
  padding-top: 6px;
}

.driver-edge-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #444;
}

.driver-edge-relation {
  color: #999;
}

.focus-chip-button {
  border: 1px solid #E6E6E6;
  cursor: pointer;
}

.focus-chip-button:hover {
  border-color: #FF5722;
  color: #111;
}

.trendboard-grid {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 16px;
}

.trend-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 760px;
  overflow-y: auto;
  padding-right: 4px;
}

.trend-list-item {
  text-align: left;
  border: 1px solid #EAEAEA;
  background: #FAFAFA;
  border-radius: 8px;
  padding: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.trend-list-item:hover,
.trend-list-item.selected {
  background: #FFF7F2;
  border-color: #FF5722;
}

.trend-item-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.trend-kind {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #999;
  text-transform: uppercase;
}

.trend-bias {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
}

.trend-bias.buy {
  background: #E8F5E9;
  color: #2E7D32;
}

.trend-bias.sell {
  background: #FDECEC;
  color: #C62828;
}

.trend-bias.watch {
  background: #FFF3E0;
  color: #EF6C00;
}

.trend-title {
  font-size: 13px;
  font-weight: 700;
  color: #111;
  line-height: 1.45;
  margin-bottom: 8px;
}

.trend-meta,
.trend-assets {
  font-size: 11px;
  color: #777;
}

.trend-meta {
  display: flex;
  gap: 10px;
  margin-bottom: 6px;
}

.trend-focus-panel {
  border: 1px solid #EAEAEA;
  border-radius: 10px;
  background: linear-gradient(180deg, #ffffff 0%, #fafafa 100%);
  padding: 16px;
  min-height: 420px;
}

.focus-loading,
.trendboard-empty {
  min-height: 220px;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: #777;
  font-size: 12px;
  border: 1px dashed #DDD;
  border-radius: 8px;
}

.trendboard-empty.error {
  color: #C62828;
  background: #FFF5F5;
  border-color: #F3C9C9;
}

.focus-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.focus-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.focus-title {
  font-size: 18px;
  font-weight: 700;
  color: #111;
  line-height: 1.35;
  margin-bottom: 6px;
}

.focus-subtitle {
  font-size: 13px;
  line-height: 1.6;
  color: #555;
}

.focus-refresh-hint {
  margin-top: 8px;
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #6d7f6f;
}

.focus-badges {
  display: flex;
  gap: 8px;
}

.focus-badge,
.comment-confidence {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 4px 8px;
  border-radius: 999px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  font-weight: 700;
  background: #111;
  color: #FFF;
  text-transform: uppercase;
}

.focus-badge.muted,
.comment-confidence {
  background: #F1F1F1;
  color: #333;
}

.focus-stat-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
}

.focus-stat {
  border: 1px solid #EAEAEA;
  border-radius: 8px;
  padding: 12px;
  background: #FFF;
}

.focus-stat-label {
  display: block;
  font-size: 10px;
  color: #999;
  text-transform: uppercase;
  margin-bottom: 6px;
}

.focus-stat-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  font-weight: 700;
  color: #111;
  word-break: break-word;
}

.focus-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.focus-section-title {
  font-size: 11px;
  color: #999;
  text-transform: uppercase;
  font-weight: 700;
  letter-spacing: 0.06em;
}

.focus-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.focus-chip {
  background: #FFF;
  border: 1px solid #E6E6E6;
  border-radius: 999px;
  padding: 6px 10px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #444;
}

.agent-comment-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.agent-comment-card {
  border: 1px solid #EAEAEA;
  border-radius: 8px;
  background: #FFF;
  padding: 12px;
}

.agent-comment-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 8px;
}

.agent-comment-name {
  font-size: 13px;
  font-weight: 700;
  color: #111;
}

.agent-comment-role {
  font-size: 11px;
  color: #777;
  margin-top: 2px;
}

.agent-comment-badges {
  display: flex;
  gap: 8px;
  align-items: center;
}

.agent-comment-text,
.agent-comment-reason {
  margin: 0;
  font-size: 12px;
  line-height: 1.65;
}

.agent-comment-text {
  color: #333;
  margin-bottom: 6px;
}

.agent-comment-reason {
  color: #777;
}

.ai-summary-box {
  border: 1px solid #111;
  border-radius: 10px;
  background: #111;
  color: #FFF;
  padding: 16px;
}

.ai-summary-top {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}

.ai-summary-box .trend-bias {
  background: #FFF;
  color: #111;
}

.ai-summary-scenario {
  margin: 0 0 14px 0;
  font-size: 14px;
  line-height: 1.6;
}

.ai-summary-action {
  margin: 0 0 14px 0;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #FFD9C7;
}

.ai-summary-list {
  margin-bottom: 12px;
}

.ai-summary-label {
  display: block;
  font-size: 10px;
  text-transform: uppercase;
  color: #BDBDBD;
  margin-bottom: 6px;
  font-weight: 700;
}

.ai-summary-list ul {
  margin: 0;
  padding-left: 18px;
}

.ai-summary-list li {
  font-size: 12px;
  line-height: 1.55;
  margin-bottom: 4px;
}

.ai-summary-foot {
  border-top: 1px solid rgba(255, 255, 255, 0.15);
  padding-top: 10px;
  font-size: 12px;
  line-height: 1.6;
  color: #F1F1F1;
}

.progress-section {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: #FF5722;
  margin-bottom: 12px;
}

.spinner-sm {
  width: 14px;
  height: 14px;
  border: 2px solid #FFCCBC;
  border-top-color: #FF5722;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

/* System Logs */
.system-logs {
  background: #000;
  color: #DDD;
  padding: 16px;
  font-family: 'JetBrains Mono', monospace;
  border-top: 1px solid #222;
  flex-shrink: 0;
}

.log-header {
  display: flex;
  justify-content: space-between;
  border-bottom: 1px solid #333;
  padding-bottom: 8px;
  margin-bottom: 8px;
  font-size: 10px;
  color: #888;
}

.log-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
  height: 80px; /* Approx 4 lines visible */
  overflow-y: auto;
  padding-right: 4px;
}

.log-content::-webkit-scrollbar {
  width: 4px;
}

.log-content::-webkit-scrollbar-thumb {
  background: #333;
  border-radius: 2px;
}

.log-line {
  font-size: 11px;
  display: flex;
  gap: 12px;
  line-height: 1.5;
}

.log-time {
  color: #666;
  min-width: 75px;
}

.log-msg {
  color: #CCC;
  word-break: break-all;
}

@media (max-width: 1100px) {
  .macro-overview-grid,
  .cross-asset-grid,
  .driver-cross-asset-grid,
  .driver-board-grid,
  .driver-callout-grid,
  .driver-graph-grid,
  .driver-asymmetry-grid,
  .driver-series-grid,
  .driver-participant-grid,
  .trendboard-grid {
    grid-template-columns: 1fr;
  }

  .overview-summary-panel {
    grid-column: span 1;
  }

  .overview-kpi-grid,
  .focus-stat-grid,
  .cross-asset-bucket-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>

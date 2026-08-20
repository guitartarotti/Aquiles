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
import { computed, ref, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { createSimulation } from '../api/simulation'
import { useMacroTrendBoard } from '../composables/useMacroTrendBoard'

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

const {
  macroTrends,
  macroTrendsLoading,
  macroTrendError,
  macroOverview,
  macroOverviewLoading,
  macroOverviewError,
  macroThermometer,
  macroThermometerLoading,
  macroThermometerError,
  macroCrossAsset,
  macroCrossAssetLoading,
  macroCrossAssetError,
  macroDrivers,
  macroNewsFeed,
  macroRawEvents,
  macroDriversLoading,
  macroDriverError,
  selectedDriverId,
  focusedDriver,
  focusingDriver,
  refreshingFocusedDriver,
  hoveredThermometerEventId,
  hoveredCrossAssetDriverId,
  hoveredFocusedDriverHeadlineEventId,
  selectedTrendId,
  focusedTrend,
  focusingTrend,
  thermometerSeriesConfig,
  crossAssetSeriesConfig,
  showMacroDashboard,
  canLoadMacroTrends,
  openMacroHeatmap,
  collectorStatusTone,
  collectorStatusLabel,
  normalizedMacroThermometer,
  thermometerTimeline,
  thermometerEntityViews,
  promotedMacroEventIds,
  thermometerLatest,
  macroCrossAssetTimeline,
  macroCrossAssetInsights,
  macroCrossAssetEntityViews,
  macroCrossAssetSummary,
  crossAssetSelectedDriver,
  rawEventState,
  formatTime,
  formatPrice,
  formatSignedPercent,
  formatSignedNumber,
  formatCompactNumber,
  scoreBarStyle,
  isThermometerSeriesVisible,
  toggleThermometerSeries,
  selectThermometerEvent,
  thermometerChart,
  activeThermometerEventId,
  activeThermometerEvent,
  activeThermometerEventPin,
  linePoints,
  isCrossAssetSeriesVisible,
  toggleCrossAssetSeries,
  selectCrossAssetDriver,
  crossAssetChart,
  activeCrossAssetDriverId,
  activeCrossAssetEvent,
  activeCrossAssetPin,
  crossAssetLinePoints,
  focusedDriverCrossAsset,
  focusedDriverAgentAudit,
  focusedDriverElasticityRows,
  focusedDriverThermometerTimeline,
  focusedDriverThermometerLatest,
  isFocusedDriverSeriesVisible,
  toggleFocusedDriverSeries,
  selectFocusedDriverHeadline,
  focusedDriverThermometerChart,
  activeFocusedDriverHeadlineEventId,
  activeFocusedDriverHeadlineEvent,
  activeFocusedDriverPin,
  focusedDriverLinePoints,
  focusedDriverInteractionLayout,
  handleDriverFocus,
  loadMacroDashboard,
  handleTrendFocus,
} = useMacroTrendBoard(props, router)

const selectedOntologyItem = ref(null)
const logContent = ref(null)
const creatingSimulation = ref(false)
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

// Auto-scroll logs
watch(() => props.systemLogs.length, () => {
  nextTick(() => {
    if (logContent.value) {
      logContent.value.scrollTop = logContent.value.scrollHeight
    }
  })
})
</script>

<style scoped src="./Step1GraphBuild.css"></style>

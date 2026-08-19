<template>
  <div class="heatmap-shell">
    <header class="header">
      <div class="header-copy">
        <AquilesBrand variant="desk" subtitle="PLATAFORMA QUANT" clickable @click="goHome" />
        <div class="eyebrow">Macro Desk</div>
        <h1>Participant Heatmap</h1>
        <p>
          Candles intraday de `WIN`, `WDO` e `DI` com range do dia inteiro, hover OHLC e navegacao horizontal.
        </p>
      </div>
      <div class="actions">
        <button class="ghost" @click="goHome">Home</button>
        <button class="ghost" @click="goBack">Voltar</button>
        <button class="ghost" :disabled="loading || hardReloadingOptions" @click="hardReloadOptionsBaseNow">
          {{ hardReloadingOptions ? 'Hard reload opcoes...' : 'Hard reload opcoes' }}
        </button>
        <button class="primary" :disabled="loading" @click="loadHeatmap(true)">
          {{ loading ? 'Atualizando...' : 'Atualizar agora' }}
        </button>
      </div>
    </header>

    <section class="meta-strip">
      <div><strong>Status:</strong> {{ loading ? 'Atualizando' : 'Pronto' }}</div>
      <div><strong>Intervalo:</strong> {{ panelData?.sample_interval_seconds || '--' }}s</div>
      <div><strong>Historico:</strong> {{ panelData?.history_minutes || '--' }}m</div>
      <div><strong>Ultima foto:</strong> {{ timestampLabel }}</div>
      <div><strong>Ativos:</strong> {{ assetCount }}</div>
      <div><strong>Collector:</strong> {{ panelData?.collector?.running ? 'ativo' : 'parado' }}</div>
      <div><strong>Samples:</strong> {{ panelData?.collector?.sample_count || 0 }}</div>
    </section>

    <section class="filter-strip">
      <div class="filter-block">
        <span class="filter-label">Segmento</span>
        <div class="toolbar-group">
          <button
            v-for="option in PARTICIPANT_SCOPE_OPTIONS"
            :key="option.value"
            class="chip"
            :class="{ active: participantScope === option.value }"
            @click="participantScope = option.value"
          >
            {{ option.label }}
          </button>
        </div>
      </div>
      <div class="filter-block">
        <span class="filter-label">Lado</span>
        <div class="toolbar-group">
          <button
            v-for="option in PARTICIPANT_SIDE_OPTIONS"
            :key="option.value"
            class="chip"
            :class="{ active: participantSide === option.value }"
            @click="participantSide = option.value"
          >
            {{ option.label }}
          </button>
        </div>
      </div>
      <div class="filter-block">
        <span class="filter-label">Coortes value</span>
        <div class="toolbar-group">
          <button
            class="chip"
            :class="{ active: !selectedValueCohortKeys.length }"
            @click="clearValueCohortSelection"
          >
            todas
          </button>
          <button
            v-for="cohort in VALUE_COHORT_OPTIONS"
            :key="cohort.key"
            class="chip"
            :class="{ active: selectedValueCohortKeys.includes(cohort.key) }"
            @click="toggleValueCohortSelection(cohort.key)"
          >
            {{ cohort.label }}
          </button>
        </div>
      </div>
      <div class="filter-block">
        <span class="filter-label">Linhas value</span>
        <div class="toolbar-group">
          <button
            class="chip"
            :class="{ active: !selectedValueLevelKeys.length }"
            @click="clearValueLevelSelection"
          >
            todas
          </button>
          <button
            v-for="level in VALUE_LEVEL_TYPE_OPTIONS"
            :key="level.key"
            class="chip"
            :class="{ active: selectedValueLevelKeys.includes(level.key) }"
            @click="toggleValueLevelSelection(level.key)"
          >
            {{ level.label }}
          </button>
        </div>
      </div>
      <div class="filter-block">
        <span class="filter-label">Indicador 2</span>
        <div class="toolbar-group">
          <button
            class="chip"
            :class="{ active: !selectedIndicatorMetricKeys.length }"
            @click="clearIndicatorMetricSelection"
          >
            ocultar
          </button>
          <button
            v-for="metric in INDICATOR_METRIC_OPTIONS"
            :key="metric.key"
            class="chip"
            :class="{ active: selectedIndicatorMetricKeys.includes(metric.key) }"
            @click="toggleIndicatorMetricSelection(metric.key)"
          >
            {{ metric.label }}
          </button>
        </div>
      </div>
      <div class="filter-block">
        <span class="filter-label">Coortes ind.</span>
        <div class="toolbar-group">
          <button
            class="chip"
            :class="{ active: !selectedIndicatorCohortKeys.length }"
            @click="clearIndicatorCohortSelection"
          >
            todas
          </button>
          <button
            v-for="cohort in INDICATOR_COHORT_OPTIONS"
            :key="cohort.key"
            class="chip"
            :class="{ active: selectedIndicatorCohortKeys.includes(cohort.key) }"
            @click="toggleIndicatorCohortSelection(cohort.key)"
          >
            {{ cohort.label }}
          </button>
        </div>
      </div>
      <div class="filter-block">
        <span class="filter-label">Histograma</span>
        <div class="toolbar-group">
          <button
            v-for="mode in HISTOGRAM_MODE_OPTIONS"
            :key="mode.key"
            class="chip"
            :class="{ active: selectedHistogramMode === mode.key }"
            @click="selectedHistogramMode = mode.key"
          >
            {{ mode.label }}
          </button>
        </div>
      </div>
      <div class="filter-block">
        <span class="filter-label">Regime 2</span>
        <div class="toolbar-group">
          <button
            v-for="mode in REGIME_CHART_MODE_OPTIONS"
            :key="mode.key"
            class="chip"
            :class="{ active: selectedRegimeChartMode === mode.key }"
            @click="selectedRegimeChartMode = mode.key"
          >
            {{ mode.label }}
          </button>
        </div>
      </div>
      <div class="filter-block broker-filter-block">
        <span class="filter-label">Corretoras</span>
        <div class="toolbar-group broker-chip-group">
          <button
            class="chip"
            :class="{ active: !selectedBrokerKeys.length }"
            @click="clearBrokerSelection"
          >
            todas
          </button>
          <button
            v-for="option in availableBrokerOptions"
            :key="option.key"
            class="chip"
            :class="{ active: selectedBrokerKeys.includes(option.key) }"
            @click="toggleBrokerSelection(option.key)"
          >
            {{ option.label }}
          </button>
        </div>
      </div>
    </section>

    <div v-if="errorMessage" class="error-state">{{ errorMessage }}</div>

    <section v-if="winTradeThermometer?.primary" class="package-strip">
      <div class="pressure-head">
        <div class="pressure-title">
          WIN trade thermometer {{ winTradeThermometer.primary.window_label || winTradeThermometer.primary_window_label || '' }}
        </div>
        <div class="pressure-meta">
          {{ formatTradeSignalLabel(winTradeThermometer.primary.signal) }}
          | {{ formatTradeActionLabel(winTradeThermometer.primary.action) }}
          | {{ formatEntryStyleLabel(winTradeThermometer.primary.entry_style) }}
        </div>
      </div>
      <div class="pressure-window-row">
        <span class="pressure-window-label">leitura dominante</span>
        <span>{{ winTradeThermometer.primary.rationale || '--' }}</span>
      </div>
      <div class="pressure-pill-row">
        <div class="pressure-pill" :class="thermometerClass(winTradeThermometer.primary)">
          <span class="pressure-pill-label">sinal</span>
          <strong>{{ formatTradeSignalLabel(winTradeThermometer.primary.signal) }}</strong>
          <span>{{ formatTradeActionLabel(winTradeThermometer.primary.action) }} | {{ formatEntryStyleLabel(winTradeThermometer.primary.entry_style) }}</span>
        </div>
        <div class="pressure-pill" :class="thermometerClass(winTradeThermometer.primary)">
          <span class="pressure-pill-label">scores</span>
          <strong>dir {{ formatPressureScore(winTradeThermometer.primary.directional_score) }}</strong>
          <span>conv {{ formatConfidenceScore(winTradeThermometer.primary.conviction_score) }} | timing {{ formatConfidenceScore(winTradeThermometer.primary.timing_score) }}</span>
        </div>
        <div class="pressure-pill" :class="riskClass(winTradeThermometer.primary.risk_score)">
          <span class="pressure-pill-label">risco</span>
          <strong>{{ formatConfidenceScore(winTradeThermometer.primary.risk_score) }}</strong>
          <span>RR {{ formatCompactFloat(winTradeThermometer.primary.risk_reward_ratio) }}</span>
        </div>
      </div>
      <div class="pressure-pill-row">
        <div class="pressure-pill balanced">
          <span class="pressure-pill-label">referencias</span>
          <strong>preco {{ formatPrice(winTradeThermometer.primary.current_price) }}</strong>
          <span>POC {{ formatPrice(winTradeThermometer.primary.poc_reference?.price) }} | pos {{ formatValuePosition(winTradeThermometer.primary.current_position) }}</span>
        </div>
        <div class="pressure-pill balanced">
          <span class="pressure-pill-label">target / inval</span>
          <strong>{{ formatPrice(winTradeThermometer.primary.target_price) }} / {{ formatPrice(winTradeThermometer.primary.invalidation_price) }}</strong>
          <span>{{ formatSignedPoints(winTradeThermometer.primary.price_to_target_points) }} | {{ formatSignedPoints(winTradeThermometer.primary.price_to_invalidation_points) }}</span>
        </div>
        <div class="pressure-pill balanced">
          <span class="pressure-pill-label">suporte / resistencia</span>
          <strong>{{ formatPrice(winTradeThermometer.primary.support_reference?.price) }} / {{ formatPrice(winTradeThermometer.primary.resistance_reference?.price) }}</strong>
          <span>{{ formatReferenceLabel(winTradeThermometer.primary.support_reference) }} | {{ formatReferenceLabel(winTradeThermometer.primary.resistance_reference) }}</span>
        </div>
      </div>
      <div v-if="winTradeThermometer.primary.news_context?.available" class="pressure-pill-row">
        <div class="pressure-pill" :class="newsBiasClass(winTradeThermometer.primary.news_context)">
          <span class="pressure-pill-label">macro news</span>
          <strong>{{ formatNewsMarkerLabel(winTradeThermometer.primary.news_context.marker) }}</strong>
          <span>{{ formatNewsBiasLabel(winTradeThermometer.primary.news_context.bias) }} | score {{ formatPressureScore(winTradeThermometer.primary.news_directional_score) }}</span>
        </div>
        <div class="pressure-pill" :class="newsAlignmentClass(winTradeThermometer.primary.news_alignment_state)">
          <span class="pressure-pill-label">pareamento</span>
          <strong>{{ formatNewsAlignmentLabel(winTradeThermometer.primary.news_alignment_state) }}</strong>
          <span>fresh {{ formatConfidenceScore(winTradeThermometer.primary.news_freshness_score) }} | conf {{ formatConfidenceScore(winTradeThermometer.primary.news_confidence_score) }}</span>
        </div>
        <div class="pressure-pill balanced">
          <span class="pressure-pill-label">driver macro</span>
          <strong>{{ winTradeThermometer.primary.news_context.driver_title || '--' }}</strong>
          <span>{{ winTradeThermometer.primary.news_context.headline || winTradeThermometer.primary.news_context.summary || '--' }}</span>
        </div>
      </div>
      <div class="pressure-window-grid">
        <div
          v-for="window in (winTradeThermometer.windows || [])"
          :key="`thermo-${window.minutes}`"
          class="pressure-window-row"
        >
          <span class="pressure-window-label">{{ window.window_label }}</span>
          <span>{{ formatTradeSignalLabel(window.signal) }}</span>
          <span>dir {{ formatPressureScore(window.directional_score) }}</span>
          <span>conv {{ formatConfidenceScore(window.conviction_score) }}</span>
          <span>risk {{ formatConfidenceScore(window.risk_score) }}</span>
        </div>
      </div>
    </section>

    <section v-if="optionsFlowAlignmentModel?.available" class="package-strip">
      <div class="pressure-head">
        <div class="pressure-title">
          Gamma x fair value x flow
        </div>
        <div class="pressure-meta">
          {{ formatTradeActionLabel(optionsFlowAlignmentModel.action_bias) }}
          | {{ formatGammaStateLabel(optionsFlowAlignmentModel.gamma_state) }}
          | {{ formatFairValueStateLabel(optionsFlowAlignmentModel.fair_value_state) }}
        </div>
      </div>
      <div class="pressure-window-row">
        <span class="pressure-window-label">leitura dominante</span>
        <span>{{ optionsFlowAlignmentModel.commentary || '--' }}</span>
      </div>
      <div class="pressure-pill-row">
        <div class="pressure-pill" :class="pressureClass(optionsFlowAlignmentModel.directional_score)">
          <span class="pressure-pill-label">score combinado</span>
          <strong>{{ formatPressureScore(optionsFlowAlignmentModel.directional_score) }}</strong>
          <span>conf {{ formatConfidenceScore(optionsFlowAlignmentModel.confidence_score) }}</span>
        </div>
        <div class="pressure-pill balanced">
          <span class="pressure-pill-label">fair value</span>
          <strong>{{ formatPrice(optionsFlowAlignmentModel.fair_value_price) }}</strong>
          <span>{{ formatSignedPoints(optionsFlowAlignmentModel.mispricing_value) }} | z {{ formatCompactFloat(optionsFlowAlignmentModel.mispricing_zscore) }}</span>
        </div>
        <div class="pressure-pill balanced">
          <span class="pressure-pill-label">gamma foco</span>
          <strong>{{ optionsFlowAlignmentModel.nearest_region?.display_label || '--' }}</strong>
          <span>{{ formatPrice(optionsFlowAlignmentModel.nearest_region?.price) }} | {{ formatGammaRoleLabel(optionsFlowAlignmentModel.nearest_region?.role) }}</span>
        </div>
      </div>
      <div class="pressure-pill-row">
        <div
          v-for="region in (optionsFlowAlignmentModel.region_focus || []).slice(0, 3)"
          :key="`opt-align-${region.display_label}-${region.price}`"
          class="pressure-pill balanced"
        >
          <span class="pressure-pill-label">{{ region.display_label }}</span>
          <strong>{{ formatPrice(region.price) }}</strong>
          <span>{{ formatGammaRoleLabel(region.role) }} | dist {{ formatSignedPoints(region.distance_to_price_points) }}</span>
          <span class="pressure-micro">OI {{ formatCompactSignedQuantity(region.open_interest_total, false) }} | gex {{ formatCompactFloat(region.gex_notional_future_net) }}</span>
        </div>
      </div>
    </section>

    <section v-if="liquidityPoolModel?.primary_asset?.primary" class="package-strip">
      <div class="pressure-head">
        <div class="pressure-title">
          Synthetic liquidity pools {{ liquidityPoolModel.primary_asset.primary.window_label || liquidityPoolModel.primary_asset.primary_window_label || '' }}
        </div>
        <div class="pressure-meta">
          {{ formatLiquidityPoolStateLabel(liquidityPoolModel.primary_asset.primary.state) }}
          | risco {{ formatCompactSignedQuantity(liquidityPoolModel.primary_asset.primary.contracts_at_risk_total) }}
        </div>
      </div>
      <div class="pressure-window-row">
        <span class="pressure-window-label">comentario</span>
        <span>{{ liquidityPoolModel.primary_asset.primary.commentary || '--' }}</span>
      </div>
      <div class="pressure-pill-row">
        <div class="pressure-pill" :class="liquidityPoolClass(liquidityPoolModel.primary_asset.primary)">
          <span class="pressure-pill-label">inventario em risco</span>
          <strong>{{ formatCompactSignedQuantity(liquidityPoolModel.primary_asset.primary.market_inventory_contracts) }}</strong>
          <span>gringa {{ formatCompactSignedQuantity(liquidityPoolModel.primary_asset.primary.foreign_inventory_contracts) }} | varejo {{ formatCompactSignedQuantity(liquidityPoolModel.primary_asset.primary.retail_inventory_contracts) }}</span>
        </div>
        <div class="pressure-pill" :class="pressureClass(liquidityPoolModel.primary_asset.primary.short_cover_risk_score)">
          <span class="pressure-pill-label">short cover</span>
          <strong>{{ formatCompactSignedQuantity(liquidityPoolModel.primary_asset.primary.short_cover_closure_contracts) }}</strong>
          <span>risco {{ formatConfidenceScore(liquidityPoolModel.primary_asset.primary.short_cover_risk_score) }} | acima {{ formatCompactSignedQuantity(liquidityPoolModel.primary_asset.primary.short_cover_inventory_above) }}</span>
        </div>
        <div class="pressure-pill" :class="pressureClass(-1 * (liquidityPoolModel.primary_asset.primary.long_flush_risk_score || 0))">
          <span class="pressure-pill-label">long flush</span>
          <strong>{{ formatCompactSignedQuantity(liquidityPoolModel.primary_asset.primary.long_flush_closure_contracts) }}</strong>
          <span>risco {{ formatConfidenceScore(liquidityPoolModel.primary_asset.primary.long_flush_risk_score) }} | abaixo {{ formatCompactSignedQuantity(liquidityPoolModel.primary_asset.primary.long_flush_inventory_below) }}</span>
        </div>
      </div>
      <div class="pressure-pill-row">
        <div
          v-for="pool in (liquidityPoolModel.primary_asset.primary.pools || []).slice(0, 3)"
          :key="`pool-top-${pool.cohort}-${pool.pool_type}-${pool.price}`"
          class="pressure-pill"
          :class="pressureClass(pool.trigger_side === 'buy' ? (pool.cascade_probability || 0) : pool.trigger_side === 'sell' ? -1 * (pool.cascade_probability || 0) : 0)"
        >
          <span class="pressure-pill-label">{{ pool.cohort_label }}</span>
          <strong>{{ formatLiquidityPoolTypeLabel(pool.pool_type) }}</strong>
          <span>{{ formatPrice(pool.price) }} | {{ formatLocationLabel(pool.relative_location) }} | stop {{ formatCompactSignedQuantity(pool.estimated_stop_closure_contracts) }}</span>
          <span class="pressure-micro">cascade {{ formatConfidenceScore(pool.cascade_probability) }} | open {{ formatCompactSignedQuantity(pool.synthetic_open_inventory_contracts) }}</span>
        </div>
      </div>
      <div class="pressure-window-grid">
        <div
          v-for="window in (liquidityPoolModel.primary_asset.windows || [])"
          :key="`liq-pools-${window.minutes}`"
          class="pressure-window-row"
        >
          <span class="pressure-window-label">{{ window.window_label }}</span>
          <span>{{ formatLiquidityPoolStateLabel(window.state) }}</span>
          <span>short {{ formatCompactSignedQuantity(window.short_cover_closure_contracts) }}</span>
          <span>long {{ formatCompactSignedQuantity(window.long_flush_closure_contracts) }}</span>
          <span>coil {{ formatConfidenceScore(window.two_sided_stop_coil_score) }}</span>
        </div>
      </div>
    </section>

    <section v-if="liquidityIntelligenceModel?.primary_asset?.primary" class="package-strip">
      <div class="pressure-head">
        <div class="pressure-title">
          Liquidity intelligence {{ liquidityIntelligenceModel.primary_asset.primary.window_label || liquidityIntelligenceModel.primary_asset.primary_window_label || '' }}
        </div>
        <div class="pressure-meta">
          {{ formatLiquidityProviderLabel(liquidityIntelligenceModel.primary_asset.primary.liquidity_provider_state) }}
          | {{ formatTrapStateLabel(liquidityIntelligenceModel.primary_asset.primary.trap_state) }}
          | {{ formatSqueezeStateLabel(liquidityIntelligenceModel.primary_asset.primary.squeeze_state) }}
        </div>
      </div>
      <div class="pressure-window-row">
        <span class="pressure-window-label">comentario operacional</span>
        <span>{{ liquidityIntelligenceModel.primary_asset.primary.commentary || '--' }}</span>
      </div>
      <div class="pressure-pill-row">
        <div class="pressure-pill" :class="liquidityIntelClass(liquidityIntelligenceModel.primary_asset.primary)">
          <span class="pressure-pill-label">liquidez</span>
          <strong>{{ formatLiquidityProviderLabel(liquidityIntelligenceModel.primary_asset.primary.liquidity_provider_state) }}</strong>
          <span>dens {{ formatConfidenceScore(liquidityIntelligenceModel.primary_asset.primary.liquidity_density_score) }} | thin {{ formatConfidenceScore(liquidityIntelligenceModel.primary_asset.primary.thin_liquidity_score) }}</span>
        </div>
        <div class="pressure-pill" :class="liquidityIntelClass(liquidityIntelligenceModel.primary_asset.primary)">
          <span class="pressure-pill-label">traps / squeeze</span>
          <strong>{{ formatTrapStateLabel(liquidityIntelligenceModel.primary_asset.primary.trap_state) }}</strong>
          <span>{{ formatSqueezeStateLabel(liquidityIntelligenceModel.primary_asset.primary.squeeze_state) }} | stop {{ formatStopRunStateLabel(liquidityIntelligenceModel.primary_asset.primary.stop_run_state) }}</span>
        </div>
        <div class="pressure-pill" :class="pressureClass(liquidityIntelligenceModel.primary_asset.primary.retail_contra_trend_score)">
          <span class="pressure-pill-label">varejo</span>
          <strong>{{ formatRetailMicrostructureLabel(liquidityIntelligenceModel.primary_asset.primary.retail_microstructure_state) }}</strong>
          <span>contra {{ formatConfidenceScore(liquidityIntelligenceModel.primary_asset.primary.retail_contra_trend_score) }} | trap {{ formatConfidenceScore(liquidityIntelligenceModel.primary_asset.primary.retail_trapped_score) }}</span>
        </div>
      </div>
      <div class="pressure-window-grid">
        <div
          v-for="window in (liquidityIntelligenceModel.primary_asset.windows || [])"
          :key="`liq-intel-${window.minutes}`"
          class="pressure-window-row"
        >
          <span class="pressure-window-label">{{ window.window_label }}</span>
          <span>{{ formatTrapStateLabel(window.trap_state) }}</span>
          <span>{{ formatSqueezeStateLabel(window.squeeze_state) }}</span>
          <span>liq {{ formatConfidenceScore(window.liquidity_density_score) }}</span>
          <span>ret {{ formatConfidenceScore(window.retail_contra_trend_score) }}</span>
        </div>
      </div>
    </section>

    <section v-if="crossAssetFlowPackage?.primary" class="package-strip">
      <div class="pressure-head">
        <div class="pressure-title">
          Local flow package {{ crossAssetFlowPackage.primary.window_label || crossAssetFlowPackage.primary_window_label || '' }}
        </div>
        <div class="pressure-meta">
          {{ formatLocalPackageStateLabel(crossAssetFlowPackage.primary.state) }}
          | local {{ formatPressureScore(crossAssetFlowPackage.primary.local_package_score) }}
          | foreign {{ formatPressureScore(crossAssetFlowPackage.primary.foreign_package_score) }}
        </div>
      </div>
      <div class="pressure-window-row">
        <span class="pressure-window-label">leitura dominante</span>
        <span>{{ crossAssetFlowPackage.primary.rationale || '--' }}</span>
      </div>
      <div class="pressure-pill-row">
        <div class="pressure-pill" :class="localPackageClass(crossAssetFlowPackage.primary.win_component_score)">
          <span class="pressure-pill-label">WIN</span>
          <strong>{{ formatPressureScore(crossAssetFlowPackage.primary.win_component_score) }}</strong>
          <span>componente bolsa</span>
        </div>
        <div class="pressure-pill" :class="localPackageClass(crossAssetFlowPackage.primary.wdo_component_score)">
          <span class="pressure-pill-label">WDO</span>
          <strong>{{ formatPressureScore(crossAssetFlowPackage.primary.wdo_component_score) }}</strong>
          <span>invertido para risco local</span>
        </div>
        <div class="pressure-pill" :class="localPackageClass(crossAssetFlowPackage.primary.di_curve_component_score)">
          <span class="pressure-pill-label">Curva DI</span>
          <strong>{{ formatPressureScore(crossAssetFlowPackage.primary.di_curve_component_score) }}</strong>
          <span>F28/F29/F30/F31/F35</span>
        </div>
      </div>
      <div class="pressure-pill-row">
        <div class="pressure-pill balanced">
          <span class="pressure-pill-label">Confirmacao</span>
          <strong>{{ crossAssetFlowPackage.primary.on_confirmations || 0 }} on / {{ crossAssetFlowPackage.primary.off_confirmations || 0 }} off</strong>
          <span>driver {{ crossAssetFlowPackage.primary.dominant_driver || '--' }}</span>
        </div>
        <div class="pressure-pill balanced">
          <span class="pressure-pill-label">Breadth curva</span>
          <strong>{{ formatPressureScore(crossAssetFlowPackage.primary.curve_breadth_score) }}</strong>
          <span>slope {{ formatPressureScore(crossAssetFlowPackage.primary.curve_slope_score) }}</span>
        </div>
        <div class="pressure-pill balanced">
          <span class="pressure-pill-label">DI short/long</span>
          <strong>{{ formatPressureScore(crossAssetFlowPackage.primary.short_di_average_score) }} / {{ formatPressureScore(crossAssetFlowPackage.primary.long_di_average_score) }}</strong>
          <span>media por bloco</span>
        </div>
      </div>
      <div class="pressure-window-grid">
        <div
          v-for="window in (crossAssetFlowPackage.windows || [])"
          :key="`package-${window.minutes}`"
          class="pressure-window-row"
        >
          <span class="pressure-window-label">{{ window.window_label }}</span>
          <span>{{ formatLocalPackageStateLabel(window.state) }}</span>
          <span>local {{ formatPressureScore(window.local_package_score) }}</span>
          <span>foreign {{ formatPressureScore(window.foreign_package_score) }}</span>
          <span>breadth {{ formatPressureScore(window.curve_breadth_score) }}</span>
        </div>
      </div>
      <div class="pressure-pill-row">
        <div
          v-for="leg in (crossAssetFlowPackage.primary.di_legs || [])"
          :key="leg.ticker"
          class="pressure-pill"
          :class="localPackageClass(leg.net_pressure_score)"
        >
          <span class="pressure-pill-label">{{ leg.label }}</span>
          <strong>{{ formatPressureScore(leg.net_pressure_score) }}</strong>
          <span>foreign {{ formatPressureScore(leg.foreign_pressure_score) }}</span>
        </div>
      </div>
    </section>

    <section v-if="structuralDivergenceModel?.primary" class="package-strip">
      <div class="pressure-head">
        <div class="pressure-title">
          SMT / structural divergence {{ structuralDivergenceModel.primary.window_label || structuralDivergenceModel.primary_window_label || '' }}
        </div>
        <div class="pressure-meta">
          {{ formatStructuralDivergenceStateLabel(structuralDivergenceModel.primary.state) }}
          | conf {{ formatPressureScore(structuralDivergenceModel.primary.confirmation_score) }}
          | non-conf {{ formatPressureScore(structuralDivergenceModel.primary.non_confirmation_score) }}
        </div>
      </div>
      <div class="pressure-window-row">
        <span class="pressure-window-label">leitura dominante</span>
        <span>{{ structuralDivergenceModel.primary.rationale || '--' }}</span>
      </div>
      <div class="pressure-pill-row">
        <div class="pressure-pill" :class="structuralDivergenceClass(structuralDivergenceModel.primary)">
          <span class="pressure-pill-label">estado</span>
          <strong>{{ formatStructuralDivergenceStateLabel(structuralDivergenceModel.primary.state) }}</strong>
          <span>{{ structuralDivergenceModel.primary.bias_side || 'neutral' }}</span>
        </div>
        <div class="pressure-pill" :class="structuralDivergenceClass(structuralDivergenceModel.primary)">
          <span class="pressure-pill-label">WIN x pacote</span>
          <strong>{{ formatPressureScore(structuralDivergenceModel.primary.win_net_score) }}</strong>
          <span>pkg {{ formatPressureScore(structuralDivergenceModel.primary.package_score) }}</span>
        </div>
        <div class="pressure-pill" :class="structuralDivergenceClass(structuralDivergenceModel.primary)">
          <span class="pressure-pill-label">foreign</span>
          <strong>{{ formatPressureScore(structuralDivergenceModel.primary.foreign_package_score) }}</strong>
          <span>lead {{ formatPressureScore(structuralDivergenceModel.primary.lead_score) }}</span>
        </div>
      </div>
      <div class="pressure-window-grid">
        <div
          v-for="window in (structuralDivergenceModel.windows || [])"
          :key="`smt-${window.minutes}`"
          class="pressure-window-row"
        >
          <span class="pressure-window-label">{{ window.window_label }}</span>
          <span>{{ formatStructuralDivergenceStateLabel(window.state) }}</span>
          <span>conf {{ formatPressureScore(window.confirmation_score) }}</span>
          <span>non {{ formatPressureScore(window.non_confirmation_score) }}</span>
          <span>pkg {{ formatPressureScore(window.package_score) }}</span>
        </div>
      </div>
    </section>

    <section v-if="continuationReversalModel?.primary" class="package-strip">
      <div class="pressure-head">
        <div class="pressure-title">
          Continuation vs reversal {{ continuationReversalModel.primary.window_label || continuationReversalModel.primary_window_label || '' }}
        </div>
        <div class="pressure-meta">
          {{ formatContinuationStateLabel(continuationReversalModel.primary.state) }}
          | cont {{ formatConfidenceScore(continuationReversalModel.primary.continuation_probability) }}
          | rev {{ formatConfidenceScore(continuationReversalModel.primary.reversal_probability) }}
        </div>
      </div>
      <div class="pressure-window-row">
        <span class="pressure-window-label">leitura dominante</span>
        <span>{{ continuationReversalModel.primary.rationale || '--' }}</span>
      </div>
      <div class="pressure-pill-row">
        <div class="pressure-pill" :class="continuationClass(continuationReversalModel.primary)">
          <span class="pressure-pill-label">estado</span>
          <strong>{{ formatContinuationStateLabel(continuationReversalModel.primary.state) }}</strong>
          <span>{{ continuationReversalModel.primary.bias_side || 'neutral' }}</span>
        </div>
        <div class="pressure-pill" :class="continuationClass(continuationReversalModel.primary)">
          <span class="pressure-pill-label">prob.</span>
          <strong>{{ formatConfidenceScore(continuationReversalModel.primary.continuation_probability) }}</strong>
          <span>rev {{ formatConfidenceScore(continuationReversalModel.primary.reversal_probability) }}</span>
        </div>
        <div class="pressure-pill" :class="continuationClass(continuationReversalModel.primary)">
          <span class="pressure-pill-label">drivers</span>
          <strong>eff {{ formatPressureScore(continuationReversalModel.primary.efficiency_score) }}</strong>
          <span>abs {{ formatPressureScore(continuationReversalModel.primary.absorption_score) }} | frag {{ formatPressureScore(continuationReversalModel.primary.fragility_score) }}</span>
        </div>
      </div>
      <div class="pressure-window-grid">
        <div
          v-for="window in (continuationReversalModel.windows || [])"
          :key="`contrev-${window.minutes}`"
          class="pressure-window-row"
        >
          <span class="pressure-window-label">{{ window.window_label }}</span>
          <span>{{ formatContinuationStateLabel(window.state) }}</span>
          <span>cont {{ formatConfidenceScore(window.continuation_probability) }}</span>
          <span>rev {{ formatConfidenceScore(window.reversal_probability) }}</span>
          <span>pkg {{ formatPressureScore(window.package_score) }}</span>
        </div>
      </div>
    </section>

    <section v-if="quickCharts.length" class="quick-chart-grid">
      <article v-for="asset in quickCharts" :key="asset.key" class="quick-chart-card">
        <div class="quick-chart-head">
          <div>
            <div class="quick-chart-title">{{ asset.label }} <span>{{ asset.ticker }}</span></div>
            <div class="quick-chart-meta">
              <span>ultimo {{ formatPrice(asset.latest_price) }}</span>
              <span>{{ asset.candles.length }} candles</span>
              <span>{{ asset.chart?.liquidityPoolBands?.length || 0 }} pools</span>
              <span>sessao {{ asset.session_date || '--' }}</span>
            </div>
          </div>
          <div class="quick-chart-badges">
            <span class="mini-badge">{{ asset.price_source || 'snapshot' }}</span>
            <span class="mini-badge muted">{{ formatTime(asset.generated_at) }}</span>
          </div>
        </div>

        <div v-if="asset.pressure_model?.primary" class="pressure-strip">
          <div class="pressure-head">
            <div class="pressure-title">
              Inventory pressure {{ asset.pressure_model.primary.window_label }}
            </div>
            <div class="pressure-meta">
              move {{ formatSignedPoints(asset.pressure_model.primary.price_move_points) }}
              | {{ formatSignedBps(asset.pressure_model.primary.price_move_bps) }}
              | gross {{ formatSignedQuantity(asset.pressure_model.primary.total_gross_quantity, false) }}
            </div>
          </div>
          <div class="pressure-pill-row">
            <div
              v-for="cohort in PRESSURE_COHORTS"
              :key="`${asset.key}-${cohort.key}`"
              class="pressure-pill"
              :class="pressureClass(asset.pressure_model.primary.cohorts?.[cohort.key]?.pressure_score)"
            >
              <span class="pressure-pill-label">{{ cohort.label }}</span>
              <strong>{{ formatPressureScore(asset.pressure_model.primary.cohorts?.[cohort.key]?.pressure_score) }}</strong>
              <span>{{ asset.pressure_model.primary.cohorts?.[cohort.key]?.response_state || 'balanced' }}</span>
            </div>
          </div>
          <div class="pressure-window-grid">
            <div
              v-for="window in (asset.pressure_model.windows || [])"
              :key="`${asset.key}-pressure-${window.minutes}`"
              class="pressure-window-row"
            >
              <span class="pressure-window-label">{{ window.window_label }}</span>
              <span>net {{ formatPressureScore(window.cohorts?.net?.pressure_score) }}</span>
              <span>foreign {{ formatPressureScore(window.cohorts?.foreign?.pressure_score) }}</span>
              <span>retail {{ formatPressureScore(window.cohorts?.retail?.pressure_score) }}</span>
              <span>move {{ formatSignedPoints(window.price_move_points) }}</span>
            </div>
          </div>
        </div>

        <div v-if="asset.pressure_model?.primary" class="pressure-strip efficiency-strip">
          <div class="pressure-head">
            <div class="pressure-title">
              Delta efficiency {{ asset.pressure_model.primary.window_label }}
            </div>
            <div class="pressure-meta">
              dominante {{ asset.pressure_model.primary.dominant_flow_cohort || '--' }}
              | {{ asset.pressure_model.primary.dominant_efficiency_state || 'mixed' }}
            </div>
          </div>
          <div class="pressure-pill-row">
            <div
              v-for="cohort in PRESSURE_COHORTS"
              :key="`${asset.key}-eff-${cohort.key}`"
              class="pressure-pill"
              :class="pressureClass(asset.pressure_model.primary.cohorts?.[cohort.key]?.delta_efficiency_score)"
            >
              <span class="pressure-pill-label">{{ cohort.label }}</span>
              <strong>{{ formatPressureScore(asset.pressure_model.primary.cohorts?.[cohort.key]?.delta_efficiency_score) }}</strong>
              <span>{{ asset.pressure_model.primary.cohorts?.[cohort.key]?.efficiency_state || 'mixed' }}</span>
              <span class="pressure-micro">
                abs {{ formatPressureScore(asset.pressure_model.primary.cohorts?.[cohort.key]?.absorption_score) }}
                | frag {{ formatPressureScore(asset.pressure_model.primary.cohorts?.[cohort.key]?.fragility_score) }}
              </span>
              <span class="pressure-micro">
                pts/1k {{ formatCompactFloat(asset.pressure_model.primary.cohorts?.[cohort.key]?.points_per_1k_net) }}
              </span>
            </div>
          </div>
        </div>

        <div v-if="asset.cohort_value_map?.cohorts" class="pressure-strip value-map-strip">
          <div class="pressure-head">
            <div class="pressure-title">
              Cohort value map
            </div>
            <div class="pressure-meta">
              bin {{ formatPrice(asset.cohort_value_map.bin_size) }}
              | value {{ formatCompactFloat((asset.cohort_value_map.value_area_ratio || 0) * 100) }}%
              | eventos {{ asset.cohort_value_map.event_count || 0 }}
            </div>
          </div>
          <div class="pressure-pill-row">
            <div
              v-for="cohort in PRESSURE_COHORTS"
              :key="`${asset.key}-value-${cohort.key}`"
              class="pressure-pill"
              :class="pressureClass(asset.cohort_value_map.cohorts?.[cohort.key]?.net_ratio_score)"
            >
              <span class="pressure-pill-label">{{ cohort.label }}</span>
              <strong>POC {{ formatPrice(asset.cohort_value_map.cohorts?.[cohort.key]?.poc_price) }}</strong>
              <span>
                VA {{ formatPrice(asset.cohort_value_map.cohorts?.[cohort.key]?.value_area_low) }}
                -> {{ formatPrice(asset.cohort_value_map.cohorts?.[cohort.key]?.value_area_high) }}
              </span>
              <span class="pressure-micro">
                {{ formatValuePosition(asset.cohort_value_map.cohorts?.[cohort.key]?.current_position) }}
                | net {{ formatSignedQuantity(asset.cohort_value_map.cohorts?.[cohort.key]?.net_quantity) }}
              </span>
              <span class="pressure-micro">
                dist POC {{ formatSignedPoints(asset.cohort_value_map.cohorts?.[cohort.key]?.distance_to_poc_points) }}
                | skew {{ formatPressureScore(asset.cohort_value_map.cohorts?.[cohort.key]?.net_ratio_score) }}
              </span>
            </div>
          </div>
        </div>

        <div v-if="asset.flow_regime_classifier?.cohorts" class="pressure-strip regime-strip">
          <div class="pressure-head">
            <div class="pressure-title">
              Absorption vs initiative {{ asset.flow_regime_classifier.window_label || asset.pressure_model?.primary?.window_label || '' }}
            </div>
            <div class="pressure-meta">
              dominante {{ asset.flow_regime_classifier.primary_cohort || '--' }}
              | {{ formatFlowRegimeLabel(asset.flow_regime_classifier.primary_regime_state) }}
              | conf {{ formatConfidenceScore(asset.flow_regime_classifier.primary_confidence_score) }}
            </div>
          </div>
          <div class="pressure-window-row">
            <span class="pressure-window-label">leitura dominante</span>
            <span>{{ asset.flow_regime_classifier.primary_rationale || '--' }}</span>
          </div>
          <div class="pressure-pill-row">
            <div
              v-for="cohort in PRESSURE_COHORTS"
              :key="`${asset.key}-regime-${cohort.key}`"
              class="pressure-pill"
              :class="flowRegimeClass(asset.flow_regime_classifier.cohorts?.[cohort.key])"
            >
              <span class="pressure-pill-label">{{ cohort.label }}</span>
              <strong>{{ formatFlowRegimeLabel(asset.flow_regime_classifier.cohorts?.[cohort.key]?.regime_state) }}</strong>
              <span>
                conf {{ formatConfidenceScore(asset.flow_regime_classifier.cohorts?.[cohort.key]?.confidence_score) }}
                | {{ formatValuePosition(asset.flow_regime_classifier.cohorts?.[cohort.key]?.current_position) }}
              </span>
              <span class="pressure-micro">
                {{ asset.flow_regime_classifier.cohorts?.[cohort.key]?.response_state || 'balanced' }}
                | {{ asset.flow_regime_classifier.cohorts?.[cohort.key]?.efficiency_state || 'mixed' }}
              </span>
              <span class="pressure-micro">
                {{ asset.flow_regime_classifier.cohorts?.[cohort.key]?.rationale || '--' }}
              </span>
            </div>
          </div>
        </div>

        <div v-if="asset.divergence_model?.primary" class="pressure-strip divergence-strip">
          <div class="pressure-head">
            <div class="pressure-title">
              Foreign vs retail divergence {{ asset.divergence_model.primary.window_label || asset.pressure_model?.primary?.window_label || '' }}
            </div>
            <div class="pressure-meta">
              {{ formatDivergenceStateLabel(asset.divergence_model.primary.state) }}
              | align {{ formatPressureScore(asset.divergence_model.primary.alignment_score) }}
              | div {{ formatPressureScore(asset.divergence_model.primary.divergence_score) }}
            </div>
          </div>
          <div class="pressure-pill-row">
            <div
              class="pressure-pill"
              :class="divergenceClass(asset.divergence_model.primary.lead_score)"
            >
              <span class="pressure-pill-label">lead</span>
              <strong>{{ formatPressureScore(asset.divergence_model.primary.lead_score) }}</strong>
              <span>{{ asset.divergence_model.primary.bias_side || 'neutral' }}</span>
              <span class="pressure-micro">{{ asset.divergence_model.primary.rationale || '--' }}</span>
            </div>
            <div
              class="pressure-pill"
              :class="divergenceClass(asset.divergence_model.primary.foreign_pressure_score)"
            >
              <span class="pressure-pill-label">foreign</span>
              <strong>{{ formatPressureScore(asset.divergence_model.primary.foreign_pressure_score) }}</strong>
              <span>net {{ formatSignedQuantity(asset.divergence_model.primary.foreign_net_quantity) }}</span>
            </div>
            <div
              class="pressure-pill"
              :class="divergenceClass(asset.divergence_model.primary.retail_pressure_score)"
            >
              <span class="pressure-pill-label">retail</span>
              <strong>{{ formatPressureScore(asset.divergence_model.primary.retail_pressure_score) }}</strong>
              <span>net {{ formatSignedQuantity(asset.divergence_model.primary.retail_net_quantity) }}</span>
            </div>
          </div>
          <div class="pressure-window-grid">
            <div
              v-for="window in (asset.divergence_model.windows || [])"
              :key="`${asset.key}-divergence-${window.minutes}`"
              class="pressure-window-row"
            >
              <span class="pressure-window-label">{{ window.window_label }}</span>
              <span>{{ formatDivergenceStateLabel(window.state) }}</span>
              <span>align {{ formatPressureScore(window.alignment_score) }}</span>
              <span>div {{ formatPressureScore(window.divergence_score) }}</span>
              <span>lead {{ formatPressureScore(window.lead_score) }}</span>
            </div>
          </div>
        </div>

        <div v-if="asset.level_defense_model?.cohorts" class="pressure-strip level-defense-strip">
          <div class="pressure-head">
            <div class="pressure-title">
              Level defense
            </div>
            <div class="pressure-meta">
              dominante {{ asset.level_defense_model.primary_cohort || '--' }}
              | {{ formatLevelDefenseStateLabel(asset.level_defense_model.primary_state) }}
              | score {{ formatPressureScore(asset.level_defense_model.primary_score) }}
            </div>
          </div>
          <div class="pressure-window-row">
            <span class="pressure-window-label">leitura dominante</span>
            <span>{{ asset.level_defense_model.primary_rationale || '--' }}</span>
          </div>
          <div class="pressure-pill-row">
            <div
              v-for="cohort in PRESSURE_COHORTS"
              :key="`${asset.key}-defense-${cohort.key}`"
              class="pressure-pill"
              :class="levelDefenseClass(asset.level_defense_model.cohorts?.[cohort.key])"
            >
              <span class="pressure-pill-label">{{ cohort.label }}</span>
              <strong>{{ formatLevelDefenseStateLabel(asset.level_defense_model.cohorts?.[cohort.key]?.primary_state) }}</strong>
              <span>
                sup {{ formatPrice(asset.level_defense_model.cohorts?.[cohort.key]?.support_level?.price) }}
                | res {{ formatPrice(asset.level_defense_model.cohorts?.[cohort.key]?.resistance_level?.price) }}
              </span>
              <span class="pressure-micro">
                def {{ formatPressureScore(asset.level_defense_model.cohorts?.[cohort.key]?.defense_score) }}
                | acc {{ formatPressureScore(asset.level_defense_model.cohorts?.[cohort.key]?.acceptance_score) }}
                | rej {{ formatPressureScore(asset.level_defense_model.cohorts?.[cohort.key]?.rejection_score) }}
              </span>
              <span class="pressure-micro">
                ativo {{ formatPrice(asset.level_defense_model.cohorts?.[cohort.key]?.active_level?.price) }}
                | {{ asset.level_defense_model.cohorts?.[cohort.key]?.bias_side || 'neutral' }}
              </span>
              <span class="pressure-micro">
                {{ asset.level_defense_model.cohorts?.[cohort.key]?.rationale || '--' }}
              </span>
            </div>
          </div>
        </div>

        <div v-if="asset.concentration_model?.primary" class="pressure-strip concentration-strip">
          <div class="pressure-head">
            <div class="pressure-title">
              Player concentration / breadth {{ asset.concentration_model.primary.window_label || asset.concentration_model.primary_window_label || '' }}
            </div>
            <div class="pressure-meta">
              dominante {{ asset.concentration_model.primary.primary_cohort || '--' }}
              | {{ formatConcentrationStateLabel(asset.concentration_model.primary.state) }}
              | breadth {{ formatPressureScore(asset.concentration_model.primary.primary_breadth_score) }}
            </div>
          </div>
          <div class="pressure-window-row">
            <span class="pressure-window-label">leitura dominante</span>
            <span>{{ asset.concentration_model.primary.primary_rationale || '--' }}</span>
          </div>
          <div class="pressure-pill-row">
            <div
              v-for="cohort in PRESSURE_COHORTS"
              :key="`${asset.key}-conc-${cohort.key}`"
              class="pressure-pill"
              :class="concentrationClass(asset.concentration_model.cohorts?.[cohort.key])"
            >
              <span class="pressure-pill-label">{{ cohort.label }}</span>
              <strong>{{ formatConcentrationStateLabel(asset.concentration_model.cohorts?.[cohort.key]?.state) }}</strong>
              <span>
                players {{ asset.concentration_model.cohorts?.[cohort.key]?.active_player_count ?? 0 }}
                | eff {{ formatCompactFloat(asset.concentration_model.cohorts?.[cohort.key]?.effective_player_count) }}
              </span>
              <span class="pressure-micro">
                breadth {{ formatPressureScore(asset.concentration_model.cohorts?.[cohort.key]?.breadth_score) }}
                | conc {{ formatPressureScore(asset.concentration_model.cohorts?.[cohort.key]?.concentration_score) }}
              </span>
              <span class="pressure-micro">
                hhi {{ formatCompactFloat(asset.concentration_model.cohorts?.[cohort.key]?.concentration_hhi) }}
                | top {{ formatCompactFloat((asset.concentration_model.cohorts?.[cohort.key]?.top_player_share || 0) * 100) }}%
              </span>
              <span class="pressure-micro">
                lead {{ asset.concentration_model.cohorts?.[cohort.key]?.dominant_player_name || '--' }}
              </span>
              <span class="pressure-micro">
                {{ asset.concentration_model.cohorts?.[cohort.key]?.rationale || '--' }}
              </span>
            </div>
          </div>
        </div>

        <div v-if="asset.liquidity_pools?.primary" class="pressure-strip liquidity-intelligence-strip">
          <div class="pressure-head">
            <div class="pressure-title">
              Synthetic liquidity pools {{ asset.liquidity_pools.primary.window_label || asset.liquidity_pools.primary_window_label || '' }}
            </div>
            <div class="pressure-meta">
              {{ formatLiquidityPoolStateLabel(asset.liquidity_pools.primary.state) }}
              | risco {{ formatCompactSignedQuantity(asset.liquidity_pools.primary.contracts_at_risk_total) }}
            </div>
          </div>
          <div class="pressure-window-row">
            <span class="pressure-window-label">comentario</span>
            <span>{{ asset.liquidity_pools.primary.commentary || '--' }}</span>
          </div>
          <div class="pressure-pill-row">
            <div class="pressure-pill" :class="liquidityPoolClass(asset.liquidity_pools.primary)">
              <span class="pressure-pill-label">inventario</span>
              <strong>{{ formatCompactSignedQuantity(asset.liquidity_pools.primary.market_inventory_contracts) }}</strong>
              <span>gringa {{ formatCompactSignedQuantity(asset.liquidity_pools.primary.foreign_inventory_contracts) }} | varejo {{ formatCompactSignedQuantity(asset.liquidity_pools.primary.retail_inventory_contracts) }}</span>
            </div>
            <div class="pressure-pill" :class="pressureClass(asset.liquidity_pools.primary.short_cover_risk_score)">
              <span class="pressure-pill-label">short cover</span>
              <strong>{{ formatCompactSignedQuantity(asset.liquidity_pools.primary.short_cover_closure_contracts) }}</strong>
              <span>risco {{ formatConfidenceScore(asset.liquidity_pools.primary.short_cover_risk_score) }}</span>
            </div>
            <div class="pressure-pill" :class="pressureClass(-1 * (asset.liquidity_pools.primary.long_flush_risk_score || 0))">
              <span class="pressure-pill-label">long flush</span>
              <strong>{{ formatCompactSignedQuantity(asset.liquidity_pools.primary.long_flush_closure_contracts) }}</strong>
              <span>risco {{ formatConfidenceScore(asset.liquidity_pools.primary.long_flush_risk_score) }}</span>
            </div>
          </div>
          <div class="pressure-pill-row">
            <div
              v-for="pool in (asset.liquidity_pools.primary.pools || []).slice(0, 3)"
              :key="`${asset.key}-pool-${pool.cohort}-${pool.pool_type}-${pool.price}`"
              class="pressure-pill"
              :class="pressureClass(pool.trigger_side === 'buy' ? (pool.cascade_probability || 0) : pool.trigger_side === 'sell' ? -1 * (pool.cascade_probability || 0) : 0)"
            >
              <span class="pressure-pill-label">{{ pool.cohort_label }}</span>
              <strong>{{ formatLiquidityPoolTypeLabel(pool.pool_type) }}</strong>
              <span>{{ formatPrice(pool.price) }} | {{ formatLocationLabel(pool.relative_location) }} | stop {{ formatCompactSignedQuantity(pool.estimated_stop_closure_contracts) }}</span>
              <span class="pressure-micro">open {{ formatCompactSignedQuantity(pool.synthetic_open_inventory_contracts) }} | cascade {{ formatConfidenceScore(pool.cascade_probability) }}</span>
            </div>
          </div>
        </div>

        <div v-if="asset.liquidity_intelligence?.primary" class="pressure-strip liquidity-intelligence-strip">
          <div class="pressure-head">
            <div class="pressure-title">
              Liquidity intelligence {{ asset.liquidity_intelligence.primary.window_label || asset.liquidity_intelligence.primary_window_label || '' }}
            </div>
            <div class="pressure-meta">
              {{ formatLiquidityProviderLabel(asset.liquidity_intelligence.primary.liquidity_provider_state) }}
              | {{ formatTrapStateLabel(asset.liquidity_intelligence.primary.trap_state) }}
              | {{ formatSqueezeStateLabel(asset.liquidity_intelligence.primary.squeeze_state) }}
            </div>
          </div>
          <div class="pressure-window-row">
            <span class="pressure-window-label">comentario</span>
            <span>{{ asset.liquidity_intelligence.primary.commentary || '--' }}</span>
          </div>
          <div class="pressure-pill-row">
            <div class="pressure-pill" :class="liquidityIntelClass(asset.liquidity_intelligence.primary)">
              <span class="pressure-pill-label">liquidez</span>
              <strong>{{ formatLiquidityProviderLabel(asset.liquidity_intelligence.primary.liquidity_provider_state) }}</strong>
              <span>dens {{ formatConfidenceScore(asset.liquidity_intelligence.primary.liquidity_density_score) }} | thin {{ formatConfidenceScore(asset.liquidity_intelligence.primary.thin_liquidity_score) }}</span>
            </div>
            <div class="pressure-pill" :class="liquidityIntelClass(asset.liquidity_intelligence.primary)">
              <span class="pressure-pill-label">trap / squeeze</span>
              <strong>{{ formatTrapStateLabel(asset.liquidity_intelligence.primary.trap_state) }}</strong>
              <span>{{ formatSqueezeStateLabel(asset.liquidity_intelligence.primary.squeeze_state) }} | {{ formatStopRunStateLabel(asset.liquidity_intelligence.primary.stop_run_state) }}</span>
            </div>
            <div class="pressure-pill" :class="pressureClass(asset.liquidity_intelligence.primary.retail_contra_trend_score)">
              <span class="pressure-pill-label">varejo</span>
              <strong>{{ formatRetailMicrostructureLabel(asset.liquidity_intelligence.primary.retail_microstructure_state) }}</strong>
              <span>contra {{ formatConfidenceScore(asset.liquidity_intelligence.primary.retail_contra_trend_score) }} | trap {{ formatConfidenceScore(asset.liquidity_intelligence.primary.retail_trapped_score) }}</span>
            </div>
          </div>
          <div class="pressure-pill-row">
            <div
              v-for="region in (asset.liquidity_intelligence.estimated_regions || []).slice(0, 3)"
              :key="`${asset.key}-liq-region-${region.cohort}-${region.price}-${region.region_role}`"
              class="pressure-pill"
              :class="pressureClass(region.net_ratio_score)"
            >
              <span class="pressure-pill-label">{{ region.cohort_label }}</span>
              <strong>{{ formatLiquidityRegionRoleLabel(region.region_role) }}</strong>
              <span>{{ formatPrice(region.price) }} | gross {{ formatSignedQuantity(region.gross_quantity, false) }}</span>
              <span class="pressure-micro">net {{ formatSignedQuantity(region.net_quantity) }} | share {{ formatCompactFloat((region.share || 0) * 100) }}%</span>
            </div>
          </div>
        </div>

        <div class="toolbar">
          <div class="toolbar-group">
            <button
              v-for="timeframe in TIMEFRAME_OPTIONS"
              :key="`${asset.key}-tf-${timeframe.minutes}`"
              class="chip"
              :class="{ active: getTimeframeMinutes(asset.key) === timeframe.minutes }"
              @click="setTimeframe(asset.key, timeframe.minutes, asset)"
            >
              {{ timeframe.label }}
            </button>
          </div>
          <div class="toolbar-group">
            <button
              v-for="range in RANGE_OPTIONS"
              :key="`${asset.key}-${range.key}`"
              class="chip"
              :class="{ active: getRangeKey(asset.key) === range.key }"
              @click="setRange(asset.key, range.key, asset)"
            >
              {{ range.label }}
            </button>
          </div>
        <div class="toolbar-group">
          <button class="chip" @click="shiftWindow(asset.key, -1, asset)">&lt;</button>
          <button class="chip" @click="resetWindow(asset.key, asset)">dia</button>
          <button class="chip" @click="shiftWindow(asset.key, 1, asset)">&gt;</button>
        </div>
      </div>

        <div v-if="asset.key === 'win'" class="tag-filter-strip">
          <template v-if="getAssetFairValueSummary(asset)">
            <span class="filter-label">fair value</span>
            <span class="fair-value-mini-pill" :class="pressureClass(getAssetFairValueSummary(asset)?.mispricingValue || 0)">
              <strong>{{ formatPrice(getAssetFairValueSummary(asset)?.fairValuePrice) }}</strong>
              <span>justo</span>
            </span>
            <span class="fair-value-mini-pill" :class="pressureClass(getAssetFairValueSummary(asset)?.mispricingValue || 0)">
              <strong>{{ formatSignedPoints(getAssetFairValueSummary(asset)?.mispricingValue) }}</strong>
              <span>distorcao</span>
            </span>
            <span class="fair-value-mini-pill muted">
              <strong>z {{ formatCompactFloat(getAssetFairValueSummary(asset)?.mispricingZscore) }}</strong>
              <span>{{ formatFairValueStateLabel(getAssetFairValueSummary(asset)?.fairValueState) }}</span>
            </span>
            <span v-if="getAssetFairValueSummary(asset)?.nearestRegionLabel" class="fair-value-mini-pill muted">
              <strong>{{ getAssetFairValueSummary(asset)?.nearestRegionLabel }}</strong>
              <span>{{ formatPrice(getAssetFairValueSummary(asset)?.nearestRegionPrice) }}</span>
            </span>
          </template>
          <span class="filter-label">gamma</span>
          <button
            class="chip"
            :class="{ active: !gammaOverlayEnabled }"
            @click="disableGammaOverlay()"
          >
            off
          </button>
          <button
            class="chip"
            :class="{ active: gammaOverlayEnabled && !selectedGammaOverlayKeys.length }"
            @click="clearGammaOverlaySelection()"
          >
            todas
          </button>
          <button
            v-for="item in GAMMA_OVERLAY_OPTIONS"
            :key="`${asset.key}-gamma-filter-${item.key}`"
            class="chip"
            :class="{ active: gammaOverlayEnabled && selectedGammaOverlayKeys.includes(item.key) }"
            @click="toggleGammaOverlaySelection(item.key)"
          >
            {{ item.shortLabel }}
          </button>
          <span class="filter-label">fair value</span>
          <button
            class="chip"
            :class="{ active: !fairValueOverlayEnabled }"
            @click="fairValueOverlayEnabled = false"
          >
            off
          </button>
          <button
            class="chip"
            :class="{ active: fairValueOverlayEnabled }"
            @click="fairValueOverlayEnabled = true"
          >
            on
          </button>
        </div>

        <div v-if="asset.key === 'win' && asset.chart?.gammaCards?.length" class="pool-card-list gamma-card-list">
          <div
            v-for="region in asset.chart.gammaCards"
            :key="`${asset.key}-gamma-card-${region.region_key}`"
            class="pool-card"
          >
            <div class="pool-card-head">
              <span class="pool-card-badge" :style="{ color: region.color, borderColor: `${region.color}55` }">
                {{ region.symbol }}
              </span>
              <div class="pool-card-title">
                <strong>{{ region.displayLabel }}</strong>
                <span>{{ formatGammaRoleLabel(region.role) }}</span>
              </div>
            </div>
            <div class="pool-card-grid">
              <span>preco {{ formatPrice(region.price) }}</span>
              <span>banda {{ formatPrice(region.bandLow) }} -> {{ formatPrice(region.bandHigh) }}</span>
              <span>OI {{ formatCompactSignedQuantity(region.openInterestTotal, false) }}</span>
              <span>gex fut {{ formatCompactFloat(region.gexNotionalFutureNet) }}</span>
              <span>dist {{ formatSignedPoints(region.distanceToPricePoints) }}</span>
              <span>relev {{ formatConfidenceScore(region.relevanceScore) }}</span>
            </div>
            <div class="pool-card-detail">
              <span>{{ region.description }}</span>
              <span>{{ region.commentary }}</span>
            </div>
          </div>
        </div>

        <div class="tag-filter-strip">
          <span class="filter-label">pools</span>
          <button
            class="chip"
            :class="{ active: !poolOverlayEnabled }"
            @click="disablePoolOverlay()"
          >
            off
          </button>
          <button
            class="chip"
            :class="{ active: poolOverlayEnabled && !selectedPoolOverlayKeys.length }"
            @click="clearPoolOverlaySelection()"
          >
            todas
          </button>
          <button
            v-for="item in POOL_OVERLAY_OPTIONS"
            :key="`${asset.key}-pool-filter-${item.key}`"
            class="chip chip-pool-filter"
            :class="{ active: poolOverlayEnabled && selectedPoolOverlayKeys.includes(item.key) }"
            @click="togglePoolOverlaySelection(item.key)"
          >
            {{ item.shortLabel }}
          </button>
        </div>

        <div class="pool-legend-strip">
          <span class="filter-label">legenda pools</span>
          <div class="pool-legend-items">
            <span
              v-for="item in POOL_OVERLAY_OPTIONS"
              :key="`${asset.key}-pool-legend-${item.key}`"
              class="pool-legend-item"
            >
              <span class="pool-legend-badge" :style="{ color: item.color, borderColor: `${item.color}55` }">
                {{ item.shortLabel }}
              </span>
              <span class="pool-legend-copy">
                <strong>{{ item.label }}</strong>
                <span>{{ item.description }}</span>
              </span>
            </span>
          </div>
        </div>

        <div v-if="asset.chart?.liquidityPoolCards?.length" class="pool-card-list">
          <div
            v-for="pool in asset.chart.liquidityPoolCards"
            :key="`${asset.key}-pool-card-${pool.cohort}-${pool.pool_type}-${pool.price}`"
            class="pool-card"
            :class="pressureClass(pool.trigger_side === 'buy' ? (pool.cascade_probability || 0) : pool.trigger_side === 'sell' ? -1 * (pool.cascade_probability || 0) : 0)"
          >
            <div class="pool-card-head">
              <span class="pool-card-badge" :style="{ color: pool.stroke, borderColor: `${pool.stroke}66` }">
                {{ pool.shortLabel }}
              </span>
              <div class="pool-card-title">
                <strong>{{ pool.overlayLabel }}</strong>
                <span>{{ pool.cohort_label }} | {{ formatPoolTriggerLabel(pool.trigger_side) }}</span>
              </div>
            </div>
            <div class="pool-card-grid">
              <span>preco {{ formatPrice(pool.price) }}</span>
              <span>banda {{ formatPrice(pool.band_low) }} -> {{ formatPrice(pool.band_high) }}</span>
              <span>stop close {{ formatCompactSignedQuantity(pool.estimated_stop_closure_contracts) }}</span>
              <span>open sint {{ formatCompactSignedQuantity(pool.synthetic_open_inventory_contracts) }}</span>
              <span>clear band {{ formatCompactSignedQuantity(pool.estimated_contracts_to_clear_band) }}</span>
              <span>cascade {{ formatConfidenceScore(pool.cascade_probability) }}</span>
              <span>unwind {{ formatConfidenceScore(pool.unwind_intensity_score) }}</span>
              <span>{{ pool.relative_location_label || formatLocationLabel(pool.relative_location) }} | {{ formatPoolAggregationScopeLabel(pool.aggregation_scope) }}</span>
              <span>elas dia {{ formatConfidenceScore(pool.dayElasticityScore) }}</span>
              <span>elas reg {{ formatConfidenceScore(pool.regionElasticityScore) }}</span>
              <span>stop move {{ formatProjectedMove(pool.projectedStopMove) }}</span>
              <span>alvo 1 {{ formatPrice(pool.projectedTarget1Price) }}</span>
              <span>alvo 2 {{ formatPrice(pool.projectedTarget2Price) }}</span>
              <span>lado {{ formatPoolDirectionLabel(pool.projectedDirection) }}</span>
            </div>
            <div class="pool-card-detail">
              <span>{{ pool.overlayDescription }}</span>
              <span>{{ pool.projectionRationale }}</span>
              <span>{{ pool.rationale || '--' }}</span>
            </div>
          </div>
        </div>

        <div class="tag-filter-strip">
          <span class="filter-label">tags</span>
          <button
            class="chip"
            :class="{ active: !selectedAnnotationTypeKeys.length }"
            @click="clearAnnotationTypeSelection()"
          >
            todas
          </button>
          <button
            v-for="item in ANNOTATION_LEGEND_ITEMS"
            :key="`${asset.key}-annot-filter-${item.type}`"
            class="chip chip-annotation-filter"
            :class="{ active: selectedAnnotationTypeKeys.includes(item.type) }"
            @click="toggleAnnotationTypeSelection(item.type)"
          >
            {{ item.shortLabel }}
          </button>
        </div>

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

        <div v-if="asset.fairValueFeatureChart?.available" class="fair-value-feature-wrap">
          <div class="tag-filter-strip fair-value-feature-filter">
            <span class="filter-label">fair value map</span>
            <button
              class="chip"
              :class="{ active: selectedFairValueFeatureKeys.length === FAIR_VALUE_FEATURE_OPTIONS.length }"
              @click="clearFairValueFeatureSelection()"
            >
              todas
            </button>
            <button
              v-for="item in FAIR_VALUE_FEATURE_OPTIONS"
              :key="`${asset.key}-fv-feature-${item.key}`"
              class="chip"
              :class="{ active: selectedFairValueFeatureKeys.includes(item.key) }"
              @click="toggleFairValueFeatureSelection(item.key)"
            >
              {{ item.shortLabel }}
            </button>
          </div>

          <div class="tag-filter-strip fair-value-feature-filter secondary">
            <span class="filter-label">pernas core</span>
            <button
              class="chip"
              :class="{ active: !selectedFairValueCoreLegKeys.length }"
              @click="clearFairValueCoreLegSelection()"
            >
              ocultar
            </button>
            <button
              v-for="item in FAIR_VALUE_CORE_LEG_OPTIONS"
              :key="`${asset.key}-fv-core-leg-${item.key}`"
              class="chip"
              :class="{ active: selectedFairValueCoreLegKeys.includes(item.key) }"
              @click="toggleFairValueCoreLegSelection(item.key)"
            >
              {{ item.shortLabel }}
            </button>
          </div>

          <div class="tag-filter-strip fair-value-feature-filter secondary">
            <span class="filter-label">pernas shadow</span>
            <button
              class="chip"
              :class="{ active: !selectedFairValueShadowLegKeys.length }"
              @click="clearFairValueShadowLegSelection()"
            >
              ocultar
            </button>
            <button
              v-for="item in FAIR_VALUE_SHADOW_LEG_OPTIONS"
              :key="`${asset.key}-fv-shadow-leg-${item.key}`"
              class="chip"
              :class="{ active: selectedFairValueShadowLegKeys.includes(item.key) }"
              @click="toggleFairValueShadowLegSelection(item.key)"
            >
              {{ item.shortLabel }}
            </button>
          </div>

          <div class="fair-value-feature-layout">
            <aside v-if="asset.fairValueFeatureChart.qualityModel" class="fair-value-quality-panel">
              <div class="fair-value-quality-head">
                <span class="fair-value-quality-eyebrow">Fair Value Quality</span>
                <div
                  class="fair-value-quality-badge"
                  :class="fairValueSentimentClass(asset.fairValueFeatureChart.qualityModel.implicitSentiment)"
                >
                  {{ formatImplicitSentiment(asset.fairValueFeatureChart.qualityModel.implicitSentiment) }}
                </div>
              </div>

              <div class="fair-value-quality-kpis">
                <div class="fair-value-quality-kpi">
                  <span class="metric-label-with-help">
                    <span class="fair-value-quality-kpi-label">core fv</span>
                    <span class="info-help" tabindex="0" role="note" :aria-label="FAIR_VALUE_HELP_TEXT.core_fv">
                      i
                      <span class="info-help-tooltip">{{ FAIR_VALUE_HELP_TEXT.core_fv }}</span>
                    </span>
                  </span>
                  <strong>{{ formatPrice(asset.fairValueFeatureChart.currentFairValue) }}</strong>
                </div>
                <div class="fair-value-quality-kpi">
                  <span class="metric-label-with-help">
                    <span class="fair-value-quality-kpi-label">quality fv</span>
                    <span class="info-help" tabindex="0" role="note" :aria-label="FAIR_VALUE_HELP_TEXT.quality_fv">
                      i
                      <span class="info-help-tooltip">{{ FAIR_VALUE_HELP_TEXT.quality_fv }}</span>
                    </span>
                  </span>
                  <strong>{{ formatPrice(asset.fairValueFeatureChart.currentQualityAdjusted) }}</strong>
                </div>
                <div class="fair-value-quality-kpi">
                  <span class="fair-value-quality-kpi-label">distorção</span>
                  <strong>{{ formatSignedPoints(asset.fairValueFeatureChart.currentDislocation) }}</strong>
                </div>
                <div class="fair-value-quality-kpi">
                  <span class="metric-label-with-help">
                    <span class="fair-value-quality-kpi-label">ribbon</span>
                    <span class="info-help" tabindex="0" role="note" :aria-label="FAIR_VALUE_HELP_TEXT.ribbon">
                      i
                      <span class="info-help-tooltip">{{ FAIR_VALUE_HELP_TEXT.ribbon }}</span>
                    </span>
                  </span>
                  <strong>{{ formatPrice(asset.fairValueFeatureChart.currentQualityRibbonLow) }} → {{ formatPrice(asset.fairValueFeatureChart.currentQualityRibbonHigh) }}</strong>
                </div>
              </div>

              <div class="fair-value-gauge">
                <div class="fair-value-gauge-head">
                  <span>Quality gauge</span>
                  <strong>{{ formatCompactFloat(asset.fairValueFeatureChart.qualityModel.qualityGauge) }}</strong>
                </div>
                <div class="fair-value-gauge-track">
                  <div
                    class="fair-value-gauge-fill"
                    :class="fairValueGaugeClass(asset.fairValueFeatureChart.qualityModel.qualityGauge)"
                    :style="{ width: `${Math.max(0, Math.min(asset.fairValueFeatureChart.qualityModel.qualityGauge || 0, 100))}%` }"
                  />
                </div>
                <div class="fair-value-gauge-meta">
                  <span>conf {{ formatConfidenceScore(asset.fairValueFeatureChart.qualityModel.confidence) }}</span>
                  <span>sent {{ formatConfidenceScore(asset.fairValueFeatureChart.qualityModel.sentimentConfidence) }}</span>
                  <span>align {{ formatCompactFloat((asset.fairValueFeatureChart.qualityModel.coreShadowAlignment || 0) * 100) }}</span>
                </div>
              </div>

              <div class="fair-value-quality-grid">
                <div class="fair-value-quality-pill">
                  <span class="metric-label-with-help">
                    <span class="fair-value-quality-kpi-label">risk quality</span>
                    <span class="info-help" tabindex="0" role="note" :aria-label="FAIR_VALUE_HELP_TEXT.risk_quality">
                      i
                      <span class="info-help-tooltip">{{ FAIR_VALUE_HELP_TEXT.risk_quality }}</span>
                    </span>
                  </span>
                  <strong>{{ formatConfidenceScore(asset.fairValueFeatureChart.qualityModel.riskQualityScore) }}</strong>
                </div>
                <div class="fair-value-quality-pill">
                  <span class="metric-label-with-help">
                    <span class="fair-value-quality-kpi-label">coherence</span>
                    <span class="info-help" tabindex="0" role="note" :aria-label="FAIR_VALUE_HELP_TEXT.coherence">
                      i
                      <span class="info-help-tooltip">{{ FAIR_VALUE_HELP_TEXT.coherence }}</span>
                    </span>
                  </span>
                  <strong>{{ formatCompactFloat((asset.fairValueFeatureChart.qualityModel.coherenceScore || 0) * 100) }}</strong>
                </div>
                <div class="fair-value-quality-pill">
                  <span class="metric-label-with-help">
                    <span class="fair-value-quality-kpi-label">conv prob</span>
                    <span class="info-help" tabindex="0" role="note" :aria-label="FAIR_VALUE_HELP_TEXT.convergence_probability">
                      i
                      <span class="info-help-tooltip">{{ FAIR_VALUE_HELP_TEXT.convergence_probability }}</span>
                    </span>
                  </span>
                  <strong>{{ formatConfidenceScore((asset.fairValueFeatureChart.qualityModel.convergenceProbability || 0) * 100) }}</strong>
                </div>
                <div class="fair-value-quality-pill">
                  <span class="metric-label-with-help">
                    <span class="fair-value-quality-kpi-label">break prob</span>
                    <span class="info-help" tabindex="0" role="note" :aria-label="FAIR_VALUE_HELP_TEXT.regime_break_probability">
                      i
                      <span class="info-help-tooltip">{{ FAIR_VALUE_HELP_TEXT.regime_break_probability }}</span>
                    </span>
                  </span>
                  <strong>{{ formatConfidenceScore((asset.fairValueFeatureChart.qualityModel.regimeBreakProbability || 0) * 100) }}</strong>
                </div>
              </div>

              <div
                v-if="asset.fairValueFeatureChart.qualityModel.curveConditions && Object.keys(asset.fairValueFeatureChart.qualityModel.curveConditions).length"
                class="fair-value-curve-conditions"
              >
                <div class="fair-value-curve-head">
                  <div class="fair-value-curve-head-copy">
                    <span class="fair-value-curve-title">Curva DI do dia</span>
                    <span class="fair-value-curve-subtitle">
                      {{ formatCurveMacroRegime(asset.fairValueFeatureChart.qualityModel.curveConditions) }}
                    </span>
                  </div>
                  <strong>{{ formatCurveShapeLabel(asset.fairValueFeatureChart.qualityModel.curveConditions.state) }}</strong>
                </div>
                <div class="fair-value-curve-regime-strip">
                  <span
                    v-for="entry in getCurveRegimeRanking(asset.fairValueFeatureChart.qualityModel.curveConditions)"
                    :key="`${asset.key}-curve-regime-${entry.key}`"
                    class="fair-value-curve-regime-chip"
                  >
                    {{ entry.label }} {{ formatCurveProbability(entry.probability) }}
                  </span>
                </div>
                <div class="fair-value-curve-visual-panel">
                  <div
                    v-for="curveViz in [buildCurveVisualization(asset.fairValueFeatureChart.qualityModel.curveConditions)]"
                    :key="`${asset.key}-curve-viz-${curveViz ? 'ready' : 'empty'}`"
                    class="fair-value-curve-viz-card"
                  >
                    <svg
                      v-if="curveViz"
                      :viewBox="`0 0 ${curveViz.width} ${curveViz.height}`"
                      class="fair-value-curve-viz"
                      role="img"
                      aria-label="Mini grafico da variacao do dia da curva DI"
                    >
                      <line
                        v-if="Number.isFinite(curveViz.zeroLineY)"
                        :x1="18"
                        :x2="curveViz.width - 18"
                        :y1="curveViz.zeroLineY"
                        :y2="curveViz.zeroLineY"
                        class="fair-value-curve-viz-zero-line"
                      />
                      <path
                        v-if="curveViz.nominal?.path"
                        :d="curveViz.nominal.path"
                        class="fair-value-curve-viz-line nominal"
                      />
                      <path
                        v-if="curveViz.inflation?.path"
                        :d="curveViz.inflation.path"
                        class="fair-value-curve-viz-line inflation"
                      />
                      <g
                        v-for="point in (curveViz.nominal?.nodes || [])"
                        :key="`${asset.key}-curve-point-${point.label}`"
                      >
                        <circle :cx="point.x" :cy="point.y" r="3.2" class="fair-value-curve-viz-dot nominal" />
                        <text :x="point.x" :y="curveViz.height - 6" class="fair-value-curve-viz-label">{{ point.label }}</text>
                      </g>
                      <g
                        v-for="point in (curveViz.inflation?.nodes || [])"
                        :key="`${asset.key}-infl-point-${point.label}`"
                      >
                        <circle :cx="point.x" :cy="point.y" r="2.6" class="fair-value-curve-viz-dot inflation" />
                      </g>
                    </svg>
                    <div class="fair-value-curve-viz-legend">
                      <span><span class="fair-value-curve-viz-swatch nominal" /> curva nominal var % dia</span>
                      <span><span class="fair-value-curve-viz-swatch inflation" /> inflacao implicita var % dia</span>
                      <span v-if="asset.fairValueFeatureChart.qualityModel.curveConditions.probable_driver">
                        driver {{ asset.fairValueFeatureChart.qualityModel.curveConditions.probable_driver }}
                      </span>
                    </div>
                  </div>
                  <div class="fair-value-curve-thermometer">
                    <div class="fair-value-curve-thermo-head">
                      <span class="metric-label-with-help">
                        <span>termometro de inclinacao</span>
                        <span class="info-help" tabindex="0" role="note" :aria-label="CURVE_HELP_TEXT.inclination">
                          i
                          <span class="info-help-tooltip">{{ CURVE_HELP_TEXT.inclination }}</span>
                        </span>
                      </span>
                      <strong>{{ formatCompactFloat(asset.fairValueFeatureChart.qualityModel.curveConditions.inclination_score) }}/100</strong>
                    </div>
                    <div class="fair-value-curve-thermo-track">
                      <div
                        class="fair-value-curve-thermo-fill"
                        :style="{ width: `${Math.max(0, Math.min(asset.fairValueFeatureChart.qualityModel.curveConditions.inclination_score || 0, 100))}%` }"
                      />
                    </div>
                    <div class="fair-value-curve-thermo-meta">
                      <span>angulo {{ formatCurveAngle(asset.fairValueFeatureChart.qualityModel.curveConditions.geometric_angle_degrees) }}</span>
                      <span>shape abs {{ formatCurveAbsoluteShape(asset.fairValueFeatureChart.qualityModel.curveConditions.absolute_curve_shape) }}</span>
                      <span>conf {{ formatConfidenceScore((asset.fairValueFeatureChart.qualityModel.curveConditions.state_confidence || 0) * 100) }}</span>
                    </div>
                  </div>
                </div>
                <div class="fair-value-curve-grid">
                  <div class="fair-value-curve-pill">
                    <span class="metric-label-with-help">
                      <span class="fair-value-quality-kpi-label">shape</span>
                      <span class="info-help" tabindex="0" role="note" :aria-label="CURVE_HELP_TEXT.shape">
                        i
                        <span class="info-help-tooltip">{{ CURVE_HELP_TEXT.shape }}</span>
                      </span>
                    </span>
                    <strong>{{ formatCurveShapeLabel(asset.fairValueFeatureChart.qualityModel.curveConditions.state) }}</strong>
                  </div>
                  <div class="fair-value-curve-pill">
                    <span class="metric-label-with-help">
                      <span class="fair-value-quality-kpi-label">regime</span>
                      <span class="info-help" tabindex="0" role="note" :aria-label="CURVE_HELP_TEXT.regime">
                        i
                        <span class="info-help-tooltip">{{ CURVE_HELP_TEXT.regime }}</span>
                      </span>
                    </span>
                    <strong>{{ formatCurveMacroRegime(asset.fairValueFeatureChart.qualityModel.curveConditions) }}</strong>
                  </div>
                  <div class="fair-value-curve-pill">
                    <span class="metric-label-with-help">
                      <span class="fair-value-quality-kpi-label">inclinacao</span>
                      <span class="info-help" tabindex="0" role="note" :aria-label="CURVE_HELP_TEXT.inclination">
                        i
                        <span class="info-help-tooltip">{{ CURVE_HELP_TEXT.inclination }}</span>
                      </span>
                    </span>
                    <strong>{{ asset.fairValueFeatureChart.qualityModel.curveConditions.inclination_label || '--' }}</strong>
                  </div>
                  <div class="fair-value-curve-pill">
                    <span class="metric-label-with-help">
                      <span class="fair-value-quality-kpi-label">shape abs</span>
                      <span class="info-help" tabindex="0" role="note" :aria-label="CURVE_HELP_TEXT.absolute_shape">
                        i
                        <span class="info-help-tooltip">{{ CURVE_HELP_TEXT.absolute_shape }}</span>
                      </span>
                    </span>
                    <strong>{{ formatCurveAbsoluteShape(asset.fairValueFeatureChart.qualityModel.curveConditions.absolute_curve_shape) }}</strong>
                  </div>
                  <div class="fair-value-curve-pill">
                    <span class="metric-label-with-help">
                      <span class="fair-value-quality-kpi-label">medio-longo</span>
                      <span class="info-help" tabindex="0" role="note" :aria-label="CURVE_HELP_TEXT.medium_long">
                        i
                        <span class="info-help-tooltip">{{ CURVE_HELP_TEXT.medium_long }}</span>
                      </span>
                    </span>
                    <strong>{{ formatBiasLabel(asset.fairValueFeatureChart.qualityModel.curveConditions.medium_long_bias) }}</strong>
                  </div>
                  <div class="fair-value-curve-pill">
                    <span class="metric-label-with-help">
                      <span class="fair-value-quality-kpi-label">fiscal</span>
                      <span class="info-help" tabindex="0" role="note" :aria-label="CURVE_HELP_TEXT.fiscal">
                        i
                        <span class="info-help-tooltip">{{ CURVE_HELP_TEXT.fiscal }}</span>
                      </span>
                    </span>
                    <strong>{{ asset.fairValueFeatureChart.qualityModel.curveConditions.fiscal_risk_flag ? 'alerta fiscal' : 'sem stress forte' }}</strong>
                  </div>
                  <div class="fair-value-curve-pill">
                    <span class="metric-label-with-help">
                      <span class="fair-value-quality-kpi-label">infl implicita</span>
                      <span class="info-help" tabindex="0" role="note" :aria-label="CURVE_HELP_TEXT.implied_inflation">
                        i
                        <span class="info-help-tooltip">{{ CURVE_HELP_TEXT.implied_inflation }}</span>
                      </span>
                    </span>
                    <strong>{{ formatCurvePercent(asset.fairValueFeatureChart.qualityModel.curveConditions.inflation_day_change_pct) }}</strong>
                  </div>
                  <div class="fair-value-curve-pill">
                    <span class="metric-label-with-help">
                      <span class="fair-value-quality-kpi-label">driver</span>
                      <span class="info-help" tabindex="0" role="note" :aria-label="CURVE_HELP_TEXT.probable_driver">
                        i
                        <span class="info-help-tooltip">{{ CURVE_HELP_TEXT.probable_driver }}</span>
                      </span>
                    </span>
                    <strong>{{ asset.fairValueFeatureChart.qualityModel.curveConditions.probable_driver || '--' }}</strong>
                  </div>
                  <div class="fair-value-curve-pill">
                    <span class="metric-label-with-help">
                      <span class="fair-value-quality-kpi-label">impacto curva</span>
                      <span class="info-help" tabindex="0" role="note" :aria-label="CURVE_HELP_TEXT.curve_impact">
                        i
                        <span class="info-help-tooltip">{{ CURVE_HELP_TEXT.curve_impact }}</span>
                      </span>
                    </span>
                    <strong>{{ formatSignedPoints(asset.fairValueFeatureChart.qualityModel.curveConditions.curve_contribution_points) }}</strong>
                  </div>
                </div>
                <div class="fair-value-curve-metrics">
                  <span>curta {{ formatCurvePercent(asset.fairValueFeatureChart.qualityModel.curveConditions.short_day_change_pct) }}</span>
                  <span>belly {{ formatCurvePercent(asset.fairValueFeatureChart.qualityModel.curveConditions.belly_day_change_pct) }}</span>
                  <span>longa {{ formatCurvePercent(asset.fairValueFeatureChart.qualityModel.curveConditions.long_day_change_pct) }}</span>
                  <span>nivel {{ formatCurvePercent(asset.fairValueFeatureChart.qualityModel.curveConditions.level_day_change_pct) }}</span>
                  <span>slope {{ formatCurvePercent(asset.fairValueFeatureChart.qualityModel.curveConditions.slope_change) }}</span>
                  <span>twist {{ formatCurvePercent(asset.fairValueFeatureChart.qualityModel.curveConditions.twist_change) }}</span>
                </div>
                <div class="fair-value-curve-metrics emphasis">
                  <span>dominante {{ formatCurveProbability(getCurveRegimeRanking(asset.fairValueFeatureChart.qualityModel.curveConditions, 1)[0]?.probability) }}</span>
                  <span>angulo {{ formatCurveAngle(asset.fairValueFeatureChart.qualityModel.curveConditions.geometric_angle_degrees) }}</span>
                  <span>rates {{ formatSignedPoints(asset.fairValueFeatureChart.qualityModel.curveConditions.rates_contribution_points) }}</span>
                  <span>fiscal score {{ formatCompactFloat(asset.fairValueFeatureChart.qualityModel.curveConditions.fiscal_risk_score) }}</span>
                  <span>duration score {{ formatCompactFloat(asset.fairValueFeatureChart.qualityModel.curveConditions.duration_pressure_score) }}</span>
                </div>
                <div class="fair-value-quality-note">
                  <div class="fair-value-quality-note-item">
                    {{ asset.fairValueFeatureChart.qualityModel.curveConditions.summary || '--' }}
                  </div>
                  <div class="fair-value-quality-note-item">
                    {{ asset.fairValueFeatureChart.qualityModel.curveConditions.fiscal_message || '--' }}
                  </div>
                </div>
              </div>

              <div class="fair-value-ranking-window-list">
                <div
                  v-for="window in asset.fairValueFeatureChart.qualityModel.rankingWindows"
                  :key="`${asset.key}-ranking-window-${window.key}`"
                  class="fair-value-ranking-window-card"
                  :class="{ expanded: expandedFairValueRankingWindowKeys.includes(window.key) }"
                >
                  <button
                    type="button"
                    class="fair-value-ranking-window-head"
                    @click="toggleFairValueRankingWindow(window.key)"
                  >
                    <div class="fair-value-ranking-window-head-copy">
                      <strong>{{ window.label }}</strong>
                      <span>{{ window.sampleCount }} fotos uteis</span>
                    </div>
                    <div class="fair-value-ranking-window-summary">
                      <span class="bullish">
                        ↑ {{ window.topUp ? `${window.topUp.shortLabel} ${formatSignedPoints(window.topUp.contribution_points)}` : '--' }}
                      </span>
                      <span class="bearish">
                        ↓ {{ window.topDown ? `${window.topDown.shortLabel} ${formatSignedPoints(window.topDown.contribution_points)}` : '--' }}
                      </span>
                    </div>
                    <span class="fair-value-ranking-window-toggle">
                      {{ expandedFairValueRankingWindowKeys.includes(window.key) ? 'recolher' : 'expandir' }}
                    </span>
                  </button>

                  <div v-if="expandedFairValueRankingWindowKeys.includes(window.key)" class="fair-value-ranking">
                    <div class="fair-value-ranking-col">
                      <div class="fair-value-ranking-title">Puxando para cima</div>
                      <div
                        v-for="item in window.rankingUp"
                        :key="`${window.key}-up-${item.name || item.label}`"
                        class="fair-value-ranking-item bullish"
                      >
                        <span>{{ item.label || item.name }}</span>
                        <strong>{{ formatSignedPoints(item.contribution_points) }}</strong>
                      </div>
                      <div v-if="!window.rankingUp.length" class="fair-value-ranking-empty">
                        Sem perna core positiva relevante nessa janela.
                      </div>
                    </div>
                    <div class="fair-value-ranking-col">
                      <div class="fair-value-ranking-title">Puxando para baixo</div>
                      <div
                        v-for="item in window.rankingDown"
                        :key="`${window.key}-down-${item.name || item.label}`"
                        class="fair-value-ranking-item bearish"
                      >
                        <span>{{ item.label || item.name }}</span>
                        <strong>{{ formatSignedPoints(item.contribution_points) }}</strong>
                      </div>
                      <div v-if="!window.rankingDown.length" class="fair-value-ranking-empty">
                        Sem perna core negativa relevante nessa janela.
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div
                v-if="asset.fairValueFeatureChart.qualityModel.explanation?.divergences?.length"
                class="fair-value-quality-note"
              >
                <div class="fair-value-quality-note-title">Divergências</div>
                <div
                  v-for="(item, index) in asset.fairValueFeatureChart.qualityModel.explanation.divergences"
                  :key="`div-${index}`"
                  class="fair-value-quality-note-item"
                >
                  {{ item }}
                </div>
              </div>

              <div
                v-if="asset.fairValueFeatureChart.qualityModel.explanation?.warnings?.length"
                class="fair-value-quality-note warning"
              >
                <div class="fair-value-quality-note-title">Warnings</div>
                <div
                  v-for="(item, index) in asset.fairValueFeatureChart.qualityModel.explanation.warnings"
                  :key="`warn-${index}`"
                  class="fair-value-quality-note-item"
                >
                  {{ item }}
                </div>
              </div>

              <div class="fair-value-quality-summary">
                {{ asset.fairValueFeatureChart.qualityModel.explanation?.summary || '--' }}
              </div>
            </aside>

            <div class="fair-value-chart-stack">
              <div class="indicator-chart-head fair-value-feature-head">
                <div class="indicator-chart-title">Fair value dedicado</div>
                <div class="indicator-chart-legend">
                  <span class="indicator-legend-item">
                    <span class="indicator-legend-swatch fair-value-swatch-price" />
                    preco
                    <strong>{{ formatPrice(asset.fairValueFeatureChart.currentPrice) }}</strong>
                  </span>
                  <span class="indicator-legend-item">
                    <span class="indicator-legend-swatch fair-value-swatch-fv" />
                    fv core
                    <strong>{{ formatPrice(asset.fairValueFeatureChart.currentFairValue) }}</strong>
                  </span>
                  <span class="indicator-legend-item">
                    <span class="indicator-legend-swatch fair-value-swatch-quality" />
                    q adj
                    <strong>{{ formatPrice(asset.fairValueFeatureChart.currentQualityAdjusted) }}</strong>
                  </span>
                  <span class="indicator-legend-item">
                    <span class="indicator-legend-swatch fair-value-swatch-fv-legacy" />
                    fv antigo
                    <strong>{{ formatPrice(asset.fairValueFeatureChart.legacyFairValue) }}</strong>
                  </span>
                  <span class="indicator-legend-item">
                    <span class="indicator-legend-swatch fair-value-swatch-band-legacy" />
                    banda antiga
                    <strong>{{ formatPrice(asset.fairValueFeatureChart.currentLegacyBandLow) }} -> {{ formatPrice(asset.fairValueFeatureChart.currentLegacyBandHigh) }}</strong>
                  </span>
                  <span class="indicator-legend-item">
                    <span class="indicator-legend-swatch fair-value-swatch-band" />
                    banda
                    <strong>{{ formatPrice(asset.fairValueFeatureChart.currentBandLow) }} -> {{ formatPrice(asset.fairValueFeatureChart.currentBandHigh) }}</strong>
                  </span>
                  <span class="indicator-legend-item">
                    <span class="indicator-legend-swatch fair-value-swatch-ribbon" />
                    ribbon
                    <strong>{{ formatPrice(asset.fairValueFeatureChart.currentQualityRibbonLow) }} -> {{ formatPrice(asset.fairValueFeatureChart.currentQualityRibbonHigh) }}</strong>
                  </span>
                  <span class="indicator-legend-item">
                    <span class="indicator-legend-swatch fair-value-swatch-distortion" />
                    dist
                    <strong>{{ formatSignedPoints(asset.fairValueFeatureChart.currentDislocation) }}</strong>
                  </span>
                  <span class="indicator-legend-item">
                    <span class="indicator-legend-swatch fair-value-swatch-leg" />
                    perna
                    <strong>{{ asset.fairValueFeatureChart.dominantLegLabel || '--' }}</strong>
                  </span>
                  <span
                    v-for="series in asset.fairValueFeatureChart.legLineSeries"
                    :key="`${asset.key}-${series.key}-legend`"
                    class="indicator-legend-item"
                    :title="series.description || series.label"
                  >
                    <span class="indicator-legend-swatch" :style="{ backgroundColor: series.color, opacity: series.opacity }" />
                    {{ series.shortLabel }}
                    <strong>{{ formatPrice(series.lastValue) }}</strong>
                  </span>
                </div>
              </div>

              <div class="fair-value-leg-help-strip">
                <div class="fair-value-leg-help-group">
                  <span class="fair-value-leg-help-title">core</span>
                  <div class="fair-value-leg-help-items">
                    <div
                      v-for="item in FAIR_VALUE_CORE_LEG_OPTIONS"
                      :key="`${asset.key}-fv-core-help-${item.key}`"
                      class="fair-value-leg-help-item"
                      :title="item.description"
                    >
                      <span class="fair-value-leg-help-badge" :style="{ color: item.color, borderColor: `${item.color}33` }">
                        {{ item.shortLabel }}
                      </span>
                      <div class="fair-value-leg-help-copy">
                        <strong>{{ item.label }}</strong>
                        <span>{{ item.description }}</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div class="fair-value-leg-help-group">
                  <span class="fair-value-leg-help-title">shadow</span>
                  <div class="fair-value-leg-help-items">
                    <div
                      v-for="item in FAIR_VALUE_SHADOW_LEG_OPTIONS"
                      :key="`${asset.key}-fv-shadow-help-${item.key}`"
                      class="fair-value-leg-help-item shadow"
                      :title="item.description"
                    >
                      <span class="fair-value-leg-help-badge" :style="{ color: item.color, borderColor: `${item.color}33` }">
                        {{ item.shortLabel }}
                      </span>
                      <div class="fair-value-leg-help-copy">
                        <strong>{{ item.label }}</strong>
                        <span>{{ item.description }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <svg
                :viewBox="`0 0 ${asset.fairValueFeatureChart.width} ${asset.fairValueFeatureChart.height}`"
                class="indicator-chart fair-value-feature-chart"
              >
                <rect
                  :x="asset.fairValueFeatureChart.plotLeft"
                  :y="asset.fairValueFeatureChart.plotTop"
                  :width="asset.fairValueFeatureChart.plotRight - asset.fairValueFeatureChart.plotLeft"
                  :height="asset.fairValueFeatureChart.plotBottom - asset.fairValueFeatureChart.plotTop"
                  class="plot-bg indicator-plot-bg"
                  rx="12"
                />

                <g v-for="tick in asset.fairValueFeatureChart.yTicks" :key="`${asset.key}-fv-y-${tick.value}`">
                  <line
                    :x1="asset.fairValueFeatureChart.plotLeft"
                    :x2="asset.fairValueFeatureChart.plotRight"
                    :y1="tick.y"
                    :y2="tick.y"
                    class="grid indicator-grid"
                  />
                  <text
                    :x="asset.fairValueFeatureChart.plotLeft - 8"
                    :y="tick.y + 4"
                    class="axis-label"
                    text-anchor="end"
                  >
                    {{ tick.label }}
                  </text>
                </g>

                <g v-for="tick in asset.fairValueFeatureChart.xTicks" :key="`${asset.key}-fv-x-${tick.label}-${tick.x}`">
                  <line
                    :x1="tick.x"
                    :x2="tick.x"
                    :y1="asset.fairValueFeatureChart.plotTop"
                    :y2="asset.fairValueFeatureChart.plotBottom"
                    class="grid indicator-grid vertical"
                  />
                  <text
                    :x="tick.x"
                    :y="asset.fairValueFeatureChart.plotBottom + 16"
                    class="axis-label time"
                    text-anchor="middle"
                  >
                    {{ tick.label }}
                  </text>
                </g>

                <path
                  v-if="asset.fairValueFeatureChart.qualityRibbonAreaPath"
                  :d="asset.fairValueFeatureChart.qualityRibbonAreaPath"
                  class="fair-value-feature-ribbon-area"
                />
                <path
                  v-if="asset.fairValueFeatureChart.qualityRibbonUpperPath"
                  :d="asset.fairValueFeatureChart.qualityRibbonUpperPath"
                  class="fair-value-feature-ribbon-line"
                />
                <path
                  v-if="asset.fairValueFeatureChart.qualityRibbonLowerPath"
                  :d="asset.fairValueFeatureChart.qualityRibbonLowerPath"
                  class="fair-value-feature-ribbon-line"
                />
                <path
                  v-if="asset.fairValueFeatureChart.legacyBandAreaPath"
                  :d="asset.fairValueFeatureChart.legacyBandAreaPath"
                  class="fair-value-feature-legacy-band-area"
                />
                <path
                  v-if="asset.fairValueFeatureChart.legacyUpperBandPath"
                  :d="asset.fairValueFeatureChart.legacyUpperBandPath"
                  class="fair-value-feature-legacy-band-line"
                />
                <path
                  v-if="asset.fairValueFeatureChart.legacyLowerBandPath"
                  :d="asset.fairValueFeatureChart.legacyLowerBandPath"
                  class="fair-value-feature-legacy-band-line"
                />
                <path
                  v-if="asset.fairValueFeatureChart.bandAreaPath"
                  :d="asset.fairValueFeatureChart.bandAreaPath"
                  class="fair-value-feature-band-area"
                />
                <path
                  v-if="asset.fairValueFeatureChart.upperBandPath"
                  :d="asset.fairValueFeatureChart.upperBandPath"
                  class="fair-value-feature-band-line"
                />
                <path
                  v-if="asset.fairValueFeatureChart.lowerBandPath"
                  :d="asset.fairValueFeatureChart.lowerBandPath"
                  class="fair-value-feature-band-line"
                />

                <path
                  v-for="series in asset.fairValueFeatureChart.legLineSeries"
                  :key="`${asset.key}-${series.key}-path`"
                  :d="series.path"
                  class="fair-value-feature-leg-line"
                  :stroke="series.color"
                  :stroke-opacity="series.opacity"
                  :stroke-dasharray="series.dashArray"
                />

                <path
                  v-if="asset.fairValueFeatureChart.pricePath"
                  :d="asset.fairValueFeatureChart.pricePath"
                  class="fair-value-feature-price-line"
                />
                <path
                  v-if="asset.fairValueFeatureChart.fairValuePath"
                  :d="asset.fairValueFeatureChart.fairValuePath"
                  class="fair-value-feature-fv-line"
                />
                <path
                  v-if="asset.fairValueFeatureChart.qualityAdjustedPath"
                  :d="asset.fairValueFeatureChart.qualityAdjustedPath"
                  class="fair-value-feature-quality-line"
                />
                <path
                  v-if="asset.fairValueFeatureChart.legacyFairValuePath"
                  :d="asset.fairValueFeatureChart.legacyFairValuePath"
                  class="fair-value-feature-fv-legacy-line"
                />

                <g v-for="marker in asset.fairValueFeatureChart.gammaMarkers" :key="marker.key">
                  <line
                    :x1="asset.fairValueFeatureChart.plotLeft"
                    :x2="asset.fairValueFeatureChart.plotRight"
                    :y1="marker.y"
                    :y2="marker.y"
                    class="fair-value-feature-gamma-line"
                    :stroke="marker.color"
                    :stroke-opacity="marker.opacity"
                    :stroke-dasharray="marker.dashArray"
                  />
                  <text
                    :x="asset.fairValueFeatureChart.plotLeft + 10"
                    :y="marker.y - 2"
                    class="fair-value-feature-gamma-tag"
                    :fill="marker.color"
                    text-anchor="start"
                  >
                    {{ marker.label }}
                  </text>
                </g>

                <g v-for="bar in asset.fairValueFeatureChart.distortionBars" :key="bar.key">
                  <rect
                    :x="bar.x"
                    :y="bar.y"
                    :width="bar.width"
                    :height="bar.height"
                    :fill="bar.fill"
                    :fill-opacity="bar.opacity"
                    rx="2"
                  />
                </g>

                <g v-for="leg in asset.fairValueFeatureChart.legBars" :key="leg.key">
                  <rect
                    :x="leg.x"
                    :y="leg.y"
                    :width="leg.width"
                    :height="leg.height"
                    :fill="leg.fill"
                    :fill-opacity="leg.opacity"
                    rx="3"
                  />
                </g>
              </svg>
            </div>

            <div
              v-if="asset.fairValueFeatureChart.qualityModel?.qualityPulse"
              class="fair-value-quality-pulse"
            >
              <div class="fair-value-quality-pulse-head">
                <div class="fair-value-quality-pulse-copy">
                  <span class="metric-label-with-help fair-value-quality-pulse-eyebrow">
                    <span>Qualidade geral</span>
                    <span class="info-help" tabindex="0" role="note" :aria-label="FAIR_VALUE_HELP_TEXT.quality_pulse">
                      i
                      <span class="info-help-tooltip">{{ FAIR_VALUE_HELP_TEXT.quality_pulse }}</span>
                    </span>
                  </span>
                  <strong>{{ asset.fairValueFeatureChart.qualityModel.qualityPulse.headline }}</strong>
                  <span class="fair-value-quality-pulse-summary">{{ asset.fairValueFeatureChart.qualityModel.qualityPulse.summary }}</span>
                </div>
                <div
                  class="fair-value-quality-pulse-badge"
                  :class="asset.fairValueFeatureChart.qualityModel.qualityPulse.toneClass"
                >
                  {{ asset.fairValueFeatureChart.qualityModel.qualityPulse.directionLabel }}
                </div>
              </div>

              <div class="fair-value-quality-pulse-track">
                <div
                  class="fair-value-quality-pulse-fill"
                  :class="asset.fairValueFeatureChart.qualityModel.qualityPulse.toneClass"
                  :style="{ width: `${asset.fairValueFeatureChart.qualityModel.qualityPulse.strengthPercent}%` }"
                />
              </div>

              <div class="fair-value-quality-pulse-meta">
                <span>forca {{ asset.fairValueFeatureChart.qualityModel.qualityPulse.strengthLabel }}</span>
                <span>estado {{ asset.fairValueFeatureChart.qualityModel.qualityPulse.sentimentLabel }}</span>
                <span>janela {{ asset.fairValueFeatureChart.qualityModel.qualityPulse.windowLabel }}</span>
              </div>

              <div class="fair-value-quality-pulse-grid">
                <div class="fair-value-quality-pulse-pill">
                  <span>qualidade delta</span>
                  <strong>{{ asset.fairValueFeatureChart.qualityModel.qualityPulse.healthDeltaLabel }}</strong>
                </div>
                <div class="fair-value-quality-pulse-pill">
                  <span>shadow gap</span>
                  <strong>{{ asset.fairValueFeatureChart.qualityModel.qualityPulse.shadowGapLabel }}</strong>
                </div>
                <div class="fair-value-quality-pulse-pill">
                  <span>gap delta</span>
                  <strong>{{ asset.fairValueFeatureChart.qualityModel.qualityPulse.shadowGapDeltaLabel }}</strong>
                </div>
                <div class="fair-value-quality-pulse-pill">
                  <span>preco delta</span>
                  <strong>{{ asset.fairValueFeatureChart.qualityModel.qualityPulse.priceDeltaLabel }}</strong>
                </div>
              </div>

              <div class="fair-value-quality-pulse-foot">
                <div class="fair-value-quality-pulse-spark" aria-hidden="true">
                  <span
                    v-for="point in asset.fairValueFeatureChart.qualityModel.qualityPulse.series"
                    :key="point.key"
                    class="fair-value-quality-pulse-bar"
                    :class="point.toneClass"
                    :style="{ height: `${point.heightPercent}%` }"
                  />
                </div>
                <div
                  class="fair-value-quality-pulse-follow"
                  :class="asset.fairValueFeatureChart.qualityModel.qualityPulse.followThroughClass"
                >
                  {{ asset.fairValueFeatureChart.qualityModel.qualityPulse.followThroughLabel }}
                </div>
              </div>
            </div>

            <div
              v-if="asset.fairValueFeatureChart.qualityModel?.qualityHistory"
              class="fair-value-quality-history"
            >
              <div class="fair-value-quality-history-head">
                <div class="fair-value-quality-history-copy">
                  <span class="fair-value-quality-history-eyebrow">Historico da qualidade</span>
                  <strong>{{ asset.fairValueFeatureChart.qualityModel.qualityHistory.headline }}</strong>
                  <span class="fair-value-quality-history-summary">{{ asset.fairValueFeatureChart.qualityModel.qualityHistory.summary }}</span>
                </div>
                <div
                  class="fair-value-quality-history-badge"
                  :class="asset.fairValueFeatureChart.qualityModel.qualityHistory.toneClass"
                >
                  {{ asset.fairValueFeatureChart.qualityModel.qualityHistory.deltaLabel }}
                </div>
              </div>

              <div class="fair-value-quality-history-grid">
                <div class="fair-value-quality-history-pill">
                  <span>score atual</span>
                  <strong>{{ asset.fairValueFeatureChart.qualityModel.qualityHistory.latestScoreLabel }}</strong>
                </div>
                <div class="fair-value-quality-history-pill">
                  <span>impulso</span>
                  <strong>{{ asset.fairValueFeatureChart.qualityModel.qualityHistory.impulseLabel }}</strong>
                </div>
                <div class="fair-value-quality-history-pill">
                  <span>shadow gap</span>
                  <strong>{{ asset.fairValueFeatureChart.qualityModel.qualityHistory.latestGapLabel }}</strong>
                </div>
                <div class="fair-value-quality-history-pill">
                  <span>janela</span>
                  <strong>{{ asset.fairValueFeatureChart.qualityModel.qualityHistory.windowLabel }}</strong>
                </div>
              </div>

              <svg
                :viewBox="`0 0 ${asset.fairValueFeatureChart.qualityModel.qualityHistory.width} ${asset.fairValueFeatureChart.qualityModel.qualityHistory.height}`"
                class="fair-value-quality-history-chart"
                aria-hidden="true"
              >
                <rect
                  :x="asset.fairValueFeatureChart.qualityModel.qualityHistory.plotLeft"
                  :y="asset.fairValueFeatureChart.qualityModel.qualityHistory.plotTop"
                  :width="asset.fairValueFeatureChart.qualityModel.qualityHistory.plotRight - asset.fairValueFeatureChart.qualityModel.qualityHistory.plotLeft"
                  :height="asset.fairValueFeatureChart.qualityModel.qualityHistory.plotBottom - asset.fairValueFeatureChart.qualityModel.qualityHistory.plotTop"
                  class="fair-value-quality-history-plot"
                  rx="16"
                />
                <g
                  v-for="guide in asset.fairValueFeatureChart.qualityModel.qualityHistory.guideLines"
                  :key="`quality-history-guide-${guide.value}`"
                >
                  <line
                    :x1="asset.fairValueFeatureChart.qualityModel.qualityHistory.plotLeft"
                    :x2="asset.fairValueFeatureChart.qualityModel.qualityHistory.plotRight"
                    :y1="guide.y"
                    :y2="guide.y"
                    class="fair-value-quality-history-guide"
                    :class="{ emphasis: guide.emphasis }"
                  />
                  <text
                    :x="asset.fairValueFeatureChart.qualityModel.qualityHistory.plotRight - 2"
                    :y="guide.y - 4"
                    class="fair-value-quality-history-guide-label"
                    text-anchor="end"
                  >
                    {{ guide.label }}
                  </text>
                </g>
                <line
                  :x1="asset.fairValueFeatureChart.qualityModel.qualityHistory.plotLeft"
                  :x2="asset.fairValueFeatureChart.qualityModel.qualityHistory.plotRight"
                  :y1="asset.fairValueFeatureChart.qualityModel.qualityHistory.baselineY"
                  :y2="asset.fairValueFeatureChart.qualityModel.qualityHistory.baselineY"
                  class="fair-value-quality-history-baseline"
                />
                <path
                  :d="asset.fairValueFeatureChart.qualityModel.qualityHistory.areaPath"
                  class="fair-value-quality-history-area"
                  :class="asset.fairValueFeatureChart.qualityModel.qualityHistory.toneClass"
                />
                <path
                  :d="asset.fairValueFeatureChart.qualityModel.qualityHistory.linePath"
                  class="fair-value-quality-history-line"
                  :class="asset.fairValueFeatureChart.qualityModel.qualityHistory.toneClass"
                />
                <circle
                  v-for="point in asset.fairValueFeatureChart.qualityModel.qualityHistory.points"
                  :key="point.key"
                  :cx="point.x"
                  :cy="point.y"
                  :r="point.radius"
                  class="fair-value-quality-history-point"
                  :class="[point.toneClass, { latest: point.isLatest }]"
                />
              </svg>

              <div class="fair-value-quality-history-axis">
                <span
                  v-for="tick in asset.fairValueFeatureChart.qualityModel.qualityHistory.ticks"
                  :key="tick.key"
                >
                  {{ tick.label }}
                </span>
              </div>
            </div>

          </div>

          <div
            v-if="asset.key === 'win' && intradayCorrelationHistoryPanel"
            class="intraday-correlation-card"
          >
            <div class="intraday-correlation-head">
              <div class="intraday-correlation-copy">
                <span class="intraday-correlation-eyebrow">Correlacao historica</span>
                <strong>{{ intradayCorrelationHistoryPanel.headline }}</strong>
                <span class="intraday-correlation-summary">{{ intradayCorrelationHistoryPanel.summary }}</span>
              </div>
              <div
                class="intraday-correlation-badge"
                :class="intradayCorrelationHistoryPanel.toneClass"
              >
                {{ intradayCorrelationHistoryPanel.statusLabel }}
              </div>
            </div>

            <div class="intraday-correlation-toolbar">
              <div class="intraday-correlation-toolbar-group">
                <span class="filter-label">dias</span>
                <button
                  v-for="option in CORRELATION_LOOKBACK_OPTIONS"
                  :key="`corr-day-${option.days}`"
                  type="button"
                  class="chip"
                  :class="{ active: correlationLookbackDays === option.days }"
                  @click="setCorrelationLookbackDays(option.days)"
                >
                  {{ option.label }}
                </button>
              </div>
              <div class="intraday-correlation-toolbar-group">
                <span class="filter-label">janela</span>
                <button
                  v-for="option in CORRELATION_HORIZON_OPTIONS"
                  :key="`corr-h-${option.minutes}`"
                  type="button"
                  class="chip"
                  :class="{ active: correlationHorizonMinutes === option.minutes }"
                  @click="setCorrelationHorizonMinutes(option.minutes)"
                >
                  {{ option.label }}
                </button>
              </div>
              <div class="intraday-correlation-toolbar-group">
                <span class="filter-label">modo</span>
                <button
                  v-for="option in CORRELATION_MODE_OPTIONS"
                  :key="`corr-mode-${option.key}`"
                  type="button"
                  class="chip"
                  :class="{ active: selectedCorrelationModes.includes(option.key) }"
                  @click="toggleCorrelationMode(option.key)"
                >
                  {{ option.label }}
                </button>
              </div>
            </div>

            <div class="intraday-correlation-factor-strip">
              <span class="filter-label">ativos</span>
              <div class="intraday-correlation-factor-chips">
                <button
                  v-for="factor in intradayCorrelationHistoryPanel.availableFactors"
                  :key="`corr-factor-${factor.factor}`"
                  type="button"
                  class="chip"
                  :class="{ active: selectedCorrelationFactorKeys.includes(factor.factor) }"
                  @click="toggleCorrelationFactor(factor.factor)"
                >
                  {{ factor.label }}
                </button>
              </div>
            </div>

            <div class="intraday-correlation-meta">
              <span>sessoes {{ intradayCorrelationHistoryPanel.sessionsLabel }}</span>
              <span>{{ intradayCorrelationHistoryPanel.rowCountLabel }}</span>
              <span>{{ intradayCorrelationHistoryPanel.neuralLabel }}</span>
            </div>

            <svg
              v-if="intradayCorrelationHistoryPanel.hasSeries"
              :viewBox="`0 0 ${intradayCorrelationHistoryPanel.width} ${intradayCorrelationHistoryPanel.height}`"
              class="intraday-correlation-chart"
              aria-hidden="true"
            >
              <rect
                :x="intradayCorrelationHistoryPanel.plotLeft"
                :y="intradayCorrelationHistoryPanel.plotTop"
                :width="intradayCorrelationHistoryPanel.plotRight - intradayCorrelationHistoryPanel.plotLeft"
                :height="intradayCorrelationHistoryPanel.plotBottom - intradayCorrelationHistoryPanel.plotTop"
                class="intraday-correlation-plot"
                rx="16"
              />
              <g
                v-for="guide in intradayCorrelationHistoryPanel.guideLines"
                :key="`corr-guide-${guide.value}`"
              >
                <line
                  :x1="intradayCorrelationHistoryPanel.plotLeft"
                  :x2="intradayCorrelationHistoryPanel.plotRight"
                  :y1="guide.y"
                  :y2="guide.y"
                  class="intraday-correlation-guide"
                  :class="{ emphasis: guide.emphasis }"
                />
                <text
                  :x="intradayCorrelationHistoryPanel.plotRight - 2"
                  :y="guide.y - 4"
                  class="intraday-correlation-guide-label"
                  text-anchor="end"
                >
                  {{ guide.label }}
                </text>
              </g>
              <line
                :x1="intradayCorrelationHistoryPanel.plotLeft"
                :x2="intradayCorrelationHistoryPanel.plotRight"
                :y1="intradayCorrelationHistoryPanel.baselineY"
                :y2="intradayCorrelationHistoryPanel.baselineY"
                class="intraday-correlation-baseline"
              />
              <path
                v-for="series in intradayCorrelationHistoryPanel.series"
                :key="`${series.key}-path`"
                :d="series.path"
                class="intraday-correlation-line"
                :stroke="series.color"
                :stroke-dasharray="series.dashArray"
              />
              <circle
                v-for="series in intradayCorrelationHistoryPanel.series"
                :key="`${series.key}-latest`"
                :cx="series.latestPoint?.x"
                :cy="series.latestPoint?.y"
                r="3.8"
                class="intraday-correlation-point"
                :fill="series.color"
              />
              <g
                v-for="tick in intradayCorrelationHistoryPanel.ticks"
                :key="tick.key"
              >
                <text
                  :x="tick.x"
                  :y="intradayCorrelationHistoryPanel.plotBottom + 16"
                  class="intraday-correlation-tick"
                  text-anchor="middle"
                >
                  {{ tick.label }}
                </text>
              </g>
            </svg>

            <div v-else class="intraday-correlation-empty">
              Historico ainda curto para gerar a serie completa neste recorte.
            </div>

            <div v-if="intradayCorrelationHistoryPanel.series.length" class="intraday-correlation-legend">
              <span
                v-for="series in intradayCorrelationHistoryPanel.series"
                :key="`${series.key}-legend`"
                class="intraday-correlation-legend-item"
              >
                <span class="intraday-correlation-legend-swatch" :style="{ background: series.color }" />
                <span>{{ series.legendLabel }}</span>
                <strong>{{ formatSignedFloat(series.latestValue) }}</strong>
              </span>
            </div>

            <div class="intraday-correlation-note">
              {{ intradayCorrelationHistoryPanel.note }}
            </div>
          </div>

          <div
            v-if="asset.key === 'win' && capturedFactorHistoryPanel"
            class="intraday-correlation-card captured-factor-history-card"
          >
            <div class="intraday-correlation-head">
              <div class="intraday-correlation-copy">
                <span class="intraday-correlation-eyebrow">Ativos da planilha</span>
                <strong>{{ capturedFactorHistoryPanel.headline }}</strong>
                <span class="intraday-correlation-summary">{{ capturedFactorHistoryPanel.summary }}</span>
              </div>
              <div
                class="intraday-correlation-badge"
                :class="capturedFactorHistoryPanel.toneClass"
              >
                {{ capturedFactorHistoryPanel.statusLabel }}
              </div>
            </div>

            <div class="intraday-correlation-toolbar">
              <div class="intraday-correlation-toolbar-group">
                <span class="filter-label">escala</span>
                <button
                  v-for="option in CAPTURED_FACTOR_DISPLAY_OPTIONS"
                  :key="`captured-mode-${option.key}`"
                  type="button"
                  class="chip"
                  :class="{ active: capturedFactorDisplayMode === option.key }"
                  @click="setCapturedFactorDisplayMode(option.key)"
                >
                  {{ option.label }}
                </button>
              </div>
              <div class="intraday-correlation-toolbar-group">
                <span class="filter-label">atalhos</span>
                <button type="button" class="chip" @click="selectCapturedTopMovers">
                  top movers
                </button>
                <button type="button" class="chip" @click="selectAllCapturedFactors">
                  todas
                </button>
                <button type="button" class="chip" @click="clearCapturedFactorSelection">
                  limpar
                </button>
              </div>
            </div>

            <div class="intraday-correlation-factor-strip">
              <div class="captured-factor-history-strip-head">
                <span class="filter-label">ativos capturados</span>
                <input
                  v-model="capturedFactorFilterText"
                  type="text"
                  class="captured-factor-history-filter"
                  placeholder="filtrar ativo"
                >
              </div>
              <div class="intraday-correlation-factor-chips">
                <button
                  v-for="factor in capturedFactorHistoryPanel.visibleFactors"
                  :key="`captured-factor-${factor.factor}`"
                  type="button"
                  class="chip"
                  :class="{ active: selectedCapturedFactorKeys.includes(factor.factor) }"
                  @click="toggleCapturedFactorSelection(factor.factor)"
                >
                  {{ factor.label }}
                </button>
              </div>
              <div v-if="!capturedFactorHistoryPanel.visibleFactors.length" class="intraday-correlation-empty">
                Nenhum ativo bate com o filtro atual.
              </div>
            </div>

            <div class="intraday-correlation-meta">
              <span>{{ capturedFactorHistoryPanel.selectionLabel }}</span>
              <span>{{ capturedFactorHistoryPanel.searchLabel }}</span>
              <span>{{ capturedFactorHistoryPanel.rowCountLabel }}</span>
              <span>escala {{ capturedFactorHistoryPanel.modeLabel }}</span>
            </div>

            <svg
              v-if="capturedFactorHistoryPanel.hasSeries"
              :viewBox="`0 0 ${capturedFactorHistoryPanel.width} ${capturedFactorHistoryPanel.height}`"
              class="intraday-correlation-chart"
              aria-hidden="true"
            >
              <rect
                :x="capturedFactorHistoryPanel.plotLeft"
                :y="capturedFactorHistoryPanel.plotTop"
                :width="capturedFactorHistoryPanel.plotRight - capturedFactorHistoryPanel.plotLeft"
                :height="capturedFactorHistoryPanel.plotBottom - capturedFactorHistoryPanel.plotTop"
                class="intraday-correlation-plot"
                rx="16"
              />
              <g
                v-for="guide in capturedFactorHistoryPanel.guideLines"
                :key="`captured-guide-${guide.value}`"
              >
                <line
                  :x1="capturedFactorHistoryPanel.plotLeft"
                  :x2="capturedFactorHistoryPanel.plotRight"
                  :y1="guide.y"
                  :y2="guide.y"
                  class="intraday-correlation-guide"
                  :class="{ emphasis: guide.emphasis }"
                />
                <text
                  :x="capturedFactorHistoryPanel.plotRight - 2"
                  :y="guide.y - 4"
                  class="intraday-correlation-guide-label"
                  text-anchor="end"
                >
                  {{ guide.label }}
                </text>
              </g>
              <line
                :x1="capturedFactorHistoryPanel.plotLeft"
                :x2="capturedFactorHistoryPanel.plotRight"
                :y1="capturedFactorHistoryPanel.baselineY"
                :y2="capturedFactorHistoryPanel.baselineY"
                class="intraday-correlation-baseline"
              />
              <path
                v-for="series in capturedFactorHistoryPanel.series"
                :key="`${series.key}-path`"
                :d="series.path"
                class="intraday-correlation-line"
                :stroke="series.color"
              />
              <circle
                v-for="series in capturedFactorHistoryPanel.series"
                :key="`${series.key}-latest`"
                :cx="series.latestPoint?.x"
                :cy="series.latestPoint?.y"
                r="3.8"
                class="intraday-correlation-point"
                :fill="series.color"
              />
              <g
                v-for="tick in capturedFactorHistoryPanel.ticks"
                :key="tick.key"
              >
                <text
                  :x="tick.x"
                  :y="capturedFactorHistoryPanel.plotBottom + 16"
                  class="intraday-correlation-tick"
                  text-anchor="middle"
                >
                  {{ tick.label }}
                </text>
              </g>
            </svg>

            <div v-else class="intraday-correlation-empty">
              Selecione um ou mais ativos com histórico suficiente para desenhar a série.
            </div>

            <div v-if="capturedFactorHistoryPanel.series.length" class="intraday-correlation-legend">
              <span
                v-for="series in capturedFactorHistoryPanel.series"
                :key="`${series.key}-legend`"
                class="intraday-correlation-legend-item"
              >
                <span class="intraday-correlation-legend-swatch" :style="{ background: series.color }" />
                <span>{{ series.legendLabel }}</span>
                <strong>{{ series.latestValueLabel }}</strong>
              </span>
            </div>

            <div class="intraday-correlation-note">
              {{ capturedFactorHistoryPanel.note }}
            </div>
          </div>

          <div v-if="asset.fairValueFeatureChart.qualityModel" class="fair-value-briefing-card">
            <div class="fair-value-briefing-head">
              <div class="fair-value-briefing-head-copy">
                <span class="fair-value-briefing-eyebrow">Macro Fair Value Briefing</span>
                <strong>Leitura integrada do dia</strong>
                <span>{{ buildFairValueCompositeRegimeCommentary(asset.fairValueFeatureChart, asset.fairValueFeatureChart.qualityModel) }}</span>
              </div>
              <div
                class="fair-value-briefing-badge"
                :class="fairValueSentimentClass(asset.fairValueFeatureChart.qualityModel.implicitSentiment)"
              >
                {{ formatImplicitSentiment(asset.fairValueFeatureChart.qualityModel.implicitSentiment) }}
              </div>
            </div>

            <div class="fair-value-briefing-grid">
              <section class="fair-value-briefing-section wide">
                <div class="fair-value-briefing-section-title">Tese do modelo</div>
                <p>{{ buildFairValueModelCommentary(asset.fairValueFeatureChart, asset.fairValueFeatureChart.qualityModel) }}</p>
                <p>{{ buildFairValueSupportBalanceCommentary(asset.fairValueFeatureChart, asset.fairValueFeatureChart.qualityModel) }}</p>
                <p>{{ buildFairValuePriceDriverCommentary(asset.fairValueFeatureChart, asset.fairValueFeatureChart.qualityModel) }}</p>
                <div class="fair-value-briefing-chip-row">
                  <span class="fair-value-briefing-chip">
                    regime <strong>{{ getFairValueCompositeRegimeLabel(asset.fairValueFeatureChart, asset.fairValueFeatureChart.qualityModel) }}</strong>
                  </span>
                  <span class="fair-value-briefing-chip">
                    preco <strong>{{ getFairValueFollowThroughStateLabel(asset.fairValueFeatureChart.qualityModel) }}</strong>
                  </span>
                  <span class="fair-value-briefing-chip">
                    Brasil <strong>{{ getFairValueLocalAcceptanceLabel(asset.fairValueFeatureChart, asset.fairValueFeatureChart.qualityModel) }}</strong>
                  </span>
                </div>
                <div class="fair-value-briefing-note">
                  {{ buildFairValueReactionCommentary(asset.fairValueFeatureChart, asset.fairValueFeatureChart.qualityModel) }}
                </div>
              </section>

              <section class="fair-value-briefing-section">
                <div class="fair-value-briefing-section-title">Curva DI e regime local</div>
                <p>{{ buildFairValueCurveDeskCommentary(asset.fairValueFeatureChart.qualityModel.curveConditions) }}</p>
                <div class="fair-value-briefing-stat-row">
                  <span>shape <strong>{{ formatCurveShapeLabel(asset.fairValueFeatureChart.qualityModel.curveConditions.state) }}</strong></span>
                  <span>regime <strong>{{ formatCurveMacroRegime(asset.fairValueFeatureChart.qualityModel.curveConditions) }}</strong></span>
                </div>
                <div class="fair-value-briefing-stat-row">
                  <span>curta <strong>{{ formatCurvePercent(asset.fairValueFeatureChart.qualityModel.curveConditions.short_day_change_pct) }}</strong></span>
                  <span>belly <strong>{{ formatCurvePercent(asset.fairValueFeatureChart.qualityModel.curveConditions.belly_day_change_pct) }}</strong></span>
                  <span>longa <strong>{{ formatCurvePercent(asset.fairValueFeatureChart.qualityModel.curveConditions.long_day_change_pct) }}</strong></span>
                </div>
                <div class="fair-value-briefing-stat-row">
                  <span>medium-long <strong>{{ formatBiasLabel(asset.fairValueFeatureChart.qualityModel.curveConditions.medium_long_bias) }}</strong></span>
                  <span>fiscal <strong>{{ asset.fairValueFeatureChart.qualityModel.curveConditions.fiscal_risk_flag ? 'alerta' : 'ok' }}</strong></span>
                  <span>slope <strong>{{ formatCurvePercent(asset.fairValueFeatureChart.qualityModel.curveConditions.slope_change) }}</strong></span>
                  <span>impacto <strong>{{ formatSignedPoints(asset.fairValueFeatureChart.qualityModel.curveConditions.curve_contribution_points) }}</strong></span>
                </div>
              </section>

              <section class="fair-value-briefing-section">
                <div class="fair-value-briefing-section-title">Qualidade e reacao do preco</div>
                <p>{{ buildFairValueShadowCommentary(asset.fairValueFeatureChart.qualityModel, asset.fairValueFeatureChart) }}</p>
                <div class="fair-value-briefing-stat-row">
                  <span>preco <strong>{{ formatPrice(asset.fairValueFeatureChart.currentPrice) }}</strong></span>
                  <span>core fv <strong>{{ formatPrice(asset.fairValueFeatureChart.currentFairValue) }}</strong></span>
                  <span>q adj <strong>{{ formatPrice(asset.fairValueFeatureChart.currentQualityAdjusted) }}</strong></span>
                </div>
                <div class="fair-value-briefing-stat-row">
                  <span>gap bruto <strong>{{ formatSignedPoints(getFairValueGrossGap(asset.fairValueFeatureChart)) }}</strong></span>
                  <span>haircut <strong>{{ formatSignedPoints(getFairValueShadowHaircutPoints(asset.fairValueFeatureChart, asset.fairValueFeatureChart.qualityModel)) }}</strong></span>
                  <span>gap liquido <strong>{{ formatSignedPoints(getFairValueNetGap(asset.fairValueFeatureChart)) }}</strong></span>
                </div>
                <div class="fair-value-briefing-stat-row with-help">
                  <span class="metric-inline-help">
                    <span>dist <strong>{{ formatSignedPoints(asset.fairValueFeatureChart.currentDislocation) }}</strong></span>
                    <span class="info-help" tabindex="0" role="note" :aria-label="FAIR_VALUE_HELP_TEXT.briefing_distortion">
                      i
                      <span class="info-help-tooltip">{{ FAIR_VALUE_HELP_TEXT.briefing_distortion }}</span>
                    </span>
                  </span>
                  <span class="metric-inline-help">
                    <span>conv <strong>{{ formatConfidenceScore((asset.fairValueFeatureChart.qualityModel.convergenceProbability || 0) * 100) }}</strong></span>
                    <span class="info-help" tabindex="0" role="note" :aria-label="FAIR_VALUE_HELP_TEXT.briefing_convergence">
                      i
                      <span class="info-help-tooltip">{{ FAIR_VALUE_HELP_TEXT.briefing_convergence }}</span>
                    </span>
                  </span>
                  <span class="metric-inline-help">
                    <span>break <strong>{{ formatConfidenceScore((asset.fairValueFeatureChart.qualityModel.regimeBreakProbability || 0) * 100) }}</strong></span>
                    <span class="info-help" tabindex="0" role="note" :aria-label="FAIR_VALUE_HELP_TEXT.briefing_break">
                      i
                      <span class="info-help-tooltip">{{ FAIR_VALUE_HELP_TEXT.briefing_break }}</span>
                    </span>
                  </span>
                </div>
                <div v-if="asset.fairValueFeatureChart.qualityModel.explanation?.core_message" class="fair-value-briefing-note">
                  {{ asset.fairValueFeatureChart.qualityModel.explanation.core_message }}
                </div>
                <div v-if="asset.fairValueFeatureChart.qualityModel.explanation?.shadow_message" class="fair-value-briefing-note">
                  {{ asset.fairValueFeatureChart.qualityModel.explanation.shadow_message }}
                </div>
              </section>

              <section class="fair-value-briefing-section">
                <div class="fair-value-briefing-section-title">Confirmacao local e aceitacao Brasil</div>
                <p>{{ buildFairValueLocalConfirmationCommentary(asset.fairValueFeatureChart, asset.fairValueFeatureChart.qualityModel) }}</p>
                <div class="fair-value-briefing-stat-row">
                  <span>Brasil eq <strong>{{ formatSignedPoints(asset.fairValueFeatureChart.qualityModel.coreLegs?.equity_brazil?.contribution_points) }}</strong></span>
                  <span>Brasil credit <strong>{{ formatSignedPoints(asset.fairValueFeatureChart.qualityModel.coreLegs?.credit_brazil?.contribution_points) }}</strong></span>
                  <span>estado <strong>{{ getFairValueLocalAcceptanceLabel(asset.fairValueFeatureChart, asset.fairValueFeatureChart.qualityModel) }}</strong></span>
                </div>
              </section>

              <section class="fair-value-briefing-section wide">
                <div class="fair-value-briefing-section-title">O que precisa destravar para convergir</div>
                <p>{{ buildFairValueConvergenceCommentary(asset.fairValueFeatureChart, asset.fairValueFeatureChart.qualityModel) }}</p>
                <div class="fair-value-briefing-warning-grid">
                  <div class="fair-value-briefing-warning-block">
                    <strong>Blockers dominantes</strong>
                    <div
                      v-for="(item, index) in (asset.fairValueFeatureChart.qualityModel.explanation?.dominant_blockers || [])"
                      :key="`${asset.key}-brief-blocker-${index}`"
                      class="fair-value-briefing-blocker-row"
                    >
                      <div class="fair-value-briefing-leg-copy">
                        <strong>{{ item.label }}</strong>
                        <span>{{ item.message }}</span>
                      </div>
                      <div class="fair-value-briefing-leg-values warning">
                        <span>{{ item.type === 'shadow' ? 'shadow' : 'core' }}</span>
                        <span>impacto {{ formatSignedPoints(item.impact_points) }}</span>
                        <span>conf {{ formatFlexibleConfidence(item.confidence) }}</span>
                      </div>
                    </div>
                    <div v-if="!(asset.fairValueFeatureChart.qualityModel.explanation?.dominant_blockers || []).length" class="fair-value-briefing-empty">
                      Nao ha bloqueio dominante material na janela util atual.
                    </div>
                  </div>
                  <div class="fair-value-briefing-warning-block">
                    <strong>Gatilhos de confirmacao</strong>
                    <div
                      v-for="(item, index) in (asset.fairValueFeatureChart.qualityModel.explanation?.confirmation_triggers || [])"
                      :key="`${asset.key}-brief-trigger-${index}`"
                      class="fair-value-briefing-trigger-item"
                    >
                      <strong>{{ item.label }}</strong>
                      <span>{{ item.message }}</span>
                    </div>
                    <div v-if="!(asset.fairValueFeatureChart.qualityModel.explanation?.confirmation_triggers || []).length" class="fair-value-briefing-empty">
                      Sem gatilho dominante novo alem do proprio alinhamento ja visto no snapshot.
                    </div>
                  </div>
                </div>
              </section>

              <section class="fair-value-briefing-section">
                <div class="fair-value-briefing-section-title">Pernas core em destaque</div>
                <div class="fair-value-briefing-leg-columns">
                  <div class="fair-value-briefing-leg-column">
                    <span class="fair-value-briefing-leg-title bullish">Puxando para cima</span>
                    <div
                      v-for="leg in getFairValueLegRanking(asset.fairValueFeatureChart.qualityModel.coreLegs, 'core', 'up', 4)"
                      :key="`${asset.key}-brief-core-up-${leg.key}`"
                      class="fair-value-briefing-leg-row"
                    >
                      <div class="fair-value-briefing-leg-copy">
                        <strong>{{ leg.label }}</strong>
                        <span>{{ leg.description }}</span>
                      </div>
                      <div class="fair-value-briefing-leg-values bullish">
                        <span>{{ formatSignedPoints(leg.contributionValue) }}</span>
                        <span>fv {{ formatPrice(leg.implied_fair_value_xb1) }}</span>
                        <span>conf {{ formatFlexibleConfidence(leg.confidence) }}</span>
                      </div>
                    </div>
                    <div v-if="!getFairValueLegRanking(asset.fairValueFeatureChart.qualityModel.coreLegs, 'core', 'up', 4).length" class="fair-value-briefing-empty">
                      Nenhuma perna core compradora com relevância material neste momento.
                    </div>
                  </div>
                  <div class="fair-value-briefing-leg-column">
                    <span class="fair-value-briefing-leg-title bearish">Puxando para baixo</span>
                    <div
                      v-for="leg in getFairValueLegRanking(asset.fairValueFeatureChart.qualityModel.coreLegs, 'core', 'down', 4)"
                      :key="`${asset.key}-brief-core-down-${leg.key}`"
                      class="fair-value-briefing-leg-row"
                    >
                      <div class="fair-value-briefing-leg-copy">
                        <strong>{{ leg.label }}</strong>
                        <span>{{ leg.description }}</span>
                      </div>
                      <div class="fair-value-briefing-leg-values bearish">
                        <span>{{ formatSignedPoints(leg.contributionValue) }}</span>
                        <span>fv {{ formatPrice(leg.implied_fair_value_xb1) }}</span>
                        <span>conf {{ formatFlexibleConfidence(leg.confidence) }}</span>
                      </div>
                    </div>
                    <div v-if="!getFairValueLegRanking(asset.fairValueFeatureChart.qualityModel.coreLegs, 'core', 'down', 4).length" class="fair-value-briefing-empty">
                      Nenhuma perna core vendedora com relevância material neste momento.
                    </div>
                  </div>
                </div>
              </section>

              <section class="fair-value-briefing-section">
                <div class="fair-value-briefing-section-title">Shadow, fragilidade e assimetria</div>
                <p>{{ buildFairValueShadowSectionLead(asset.fairValueFeatureChart.qualityModel.shadowLegs) }}</p>
                <div
                  v-for="leg in getFairValueShadowRanking(asset.fairValueFeatureChart.qualityModel.shadowLegs, 6)"
                  :key="`${asset.key}-brief-shadow-${leg.key}`"
                  class="fair-value-briefing-shadow-row"
                >
                  <div class="fair-value-briefing-leg-copy">
                    <strong>{{ leg.label }}</strong>
                    <span>{{ leg.description }}</span>
                  </div>
                  <div class="fair-value-briefing-leg-values">
                    <span>qual {{ formatSignedPoints(leg.qualityImpactValue) }}</span>
                    <span>band {{ formatCompactFloat(leg.bandImpactValue) }}</span>
                    <span>conv {{ formatCompactFloat(leg.convergenceImpactValue) }}</span>
                    <span>fv {{ formatPrice(leg.implied_fair_value_xb1) }}</span>
                  </div>
                </div>
              </section>

              <section class="fair-value-briefing-section wide">
                <div class="fair-value-briefing-section-title">Divergências, riscos e pontos de atenção</div>
                <div class="fair-value-briefing-warning-grid">
                  <div class="fair-value-briefing-warning-block">
                    <strong>Divergências</strong>
                    <div
                      v-for="(item, index) in (asset.fairValueFeatureChart.qualityModel.explanation?.divergences || [])"
                      :key="`${asset.key}-brief-div-${index}`"
                      class="fair-value-briefing-warning-item"
                    >
                      {{ item }}
                    </div>
                    <div v-if="!(asset.fairValueFeatureChart.qualityModel.explanation?.divergences || []).length" class="fair-value-briefing-empty">
                      Sem divergência textual relevante no snapshot útil atual.
                    </div>
                  </div>
                  <div class="fair-value-briefing-warning-block">
                    <strong>Warnings</strong>
                    <div
                      v-for="(item, index) in (asset.fairValueFeatureChart.qualityModel.explanation?.warnings || [])"
                      :key="`${asset.key}-brief-warn-${index}`"
                      class="fair-value-briefing-warning-item warning"
                    >
                      {{ item }}
                    </div>
                    <div v-if="!(asset.fairValueFeatureChart.qualityModel.explanation?.warnings || []).length" class="fair-value-briefing-empty">
                      Sem warning textual relevante no snapshot útil atual.
                    </div>
                  </div>
                </div>
              </section>
            </div>
          </div>
        </div>

        <div v-if="asset.indicatorChart?.hasVisibleLines" class="indicator-chart-wrap">
          <div class="indicator-chart-head">
            <div class="indicator-chart-title">Indicadores secundarios</div>
            <div class="indicator-chart-legend">
              <span
                v-for="series in asset.indicatorChart.series"
                :key="series.key"
                class="indicator-legend-item"
              >
                <span
                  class="indicator-legend-swatch"
                  :style="{ backgroundColor: series.color, opacity: series.opacity }"
                />
                {{ series.shortLabel }}
                <strong>{{ formatPressureScore(series.lastValue) }}</strong>
              </span>
            </div>
          </div>
          <svg
            :viewBox="`0 0 ${asset.indicatorChart.width} ${asset.indicatorChart.height}`"
            class="indicator-chart"
          >
            <rect
              :x="asset.indicatorChart.plotLeft"
              :y="asset.indicatorChart.plotTop"
              :width="asset.indicatorChart.plotRight - asset.indicatorChart.plotLeft"
              :height="asset.indicatorChart.plotBottom - asset.indicatorChart.plotTop"
              class="plot-bg indicator-plot-bg"
              rx="12"
            />

            <g v-for="tick in asset.indicatorChart.yTicks" :key="`${asset.key}-ind-y-${tick.value}`">
              <line
                :x1="asset.indicatorChart.plotLeft"
                :x2="asset.indicatorChart.plotRight"
                :y1="tick.y"
                :y2="tick.y"
                class="grid indicator-grid"
              />
              <text
                :x="asset.indicatorChart.plotLeft - 8"
                :y="tick.y + 4"
                class="axis-label"
                text-anchor="end"
              >
                {{ tick.label }}
              </text>
            </g>

            <g v-for="series in asset.indicatorChart.series" :key="series.key">
              <path
                :d="series.path"
                class="indicator-line"
                :stroke="series.color"
                :stroke-dasharray="series.dashArray"
                :stroke-opacity="series.opacity"
              />
            </g>
          </svg>
        </div>

        <div v-if="asset.histogramChart?.hasVisibleBars" class="indicator-chart-wrap histogram-chart-wrap">
          <div class="indicator-chart-head">
            <div class="indicator-chart-title">Histograma acumulado</div>
            <div class="indicator-chart-legend">
              <span
                v-for="series in asset.histogramChart.series"
                :key="series.key"
                class="indicator-legend-item"
              >
                <span
                  class="indicator-legend-swatch"
                  :style="{ backgroundColor: series.color, opacity: 0.5 }"
                />
                {{ series.shortLabel }}
                <strong>{{ formatCompactSignedQuantity(series.lastValue) }}</strong>
              </span>
            </div>
          </div>
          <svg
            :viewBox="`0 0 ${asset.histogramChart.width} ${asset.histogramChart.height}`"
            class="indicator-chart"
          >
            <rect
              :x="asset.histogramChart.plotLeft"
              :y="asset.histogramChart.plotTop"
              :width="asset.histogramChart.plotRight - asset.histogramChart.plotLeft"
              :height="asset.histogramChart.plotBottom - asset.histogramChart.plotTop"
              class="plot-bg indicator-plot-bg"
              rx="12"
            />

            <g v-for="tick in asset.histogramChart.yTicks" :key="`${asset.key}-hist-y-${tick.value}`">
              <line
                :x1="asset.histogramChart.plotLeft"
                :x2="asset.histogramChart.plotRight"
                :y1="tick.y"
                :y2="tick.y"
                class="grid indicator-grid"
              />
              <text
                :x="asset.histogramChart.plotLeft - 8"
                :y="tick.y + 4"
                class="axis-label"
                text-anchor="end"
              >
                {{ tick.label }}
              </text>
            </g>

            <line
              v-if="asset.histogramChart.zeroY != null"
              :x1="asset.histogramChart.plotLeft"
              :x2="asset.histogramChart.plotRight"
              :y1="asset.histogramChart.zeroY"
              :y2="asset.histogramChart.zeroY"
              class="zero-line"
            />

            <g v-for="bar in asset.histogramChart.bars" :key="bar.key">
              <rect
                :x="bar.x"
                :y="bar.y"
                :width="bar.width"
                :height="bar.height"
                class="histogram-bar"
                :fill="bar.fill"
                :fill-opacity="bar.opacity"
                rx="2"
              />
            </g>
          </svg>
        </div>

        <div v-if="asset.regimeChart?.hasVisibleLines" class="indicator-chart-wrap regime-chart-wrap">
          <div class="indicator-chart-head">
            <div class="indicator-chart-title">Absorption vs initiative no tempo</div>
            <div class="indicator-chart-legend">
              <span
                v-for="series in asset.regimeChart.series"
                :key="series.key"
                class="indicator-legend-item"
              >
                <span
                  class="indicator-legend-swatch"
                  :style="{ backgroundColor: series.color, opacity: 0.92 }"
                />
                {{ series.shortLabel }}
                <strong>{{ formatFlowRegimeLabel(series.lastState) }}</strong>
              </span>
            </div>
          </div>
          <svg
            :viewBox="`0 0 ${asset.regimeChart.width} ${asset.regimeChart.height}`"
            class="indicator-chart"
          >
            <rect
              :x="asset.regimeChart.plotLeft"
              :y="asset.regimeChart.plotTop"
              :width="asset.regimeChart.plotRight - asset.regimeChart.plotLeft"
              :height="asset.regimeChart.plotBottom - asset.regimeChart.plotTop"
              class="plot-bg indicator-plot-bg"
              rx="12"
            />

            <g v-for="tick in asset.regimeChart.yTicks" :key="`${asset.key}-regime-y-${tick.value}`">
              <line
                :x1="asset.regimeChart.plotLeft"
                :x2="asset.regimeChart.plotRight"
                :y1="tick.y"
                :y2="tick.y"
                class="grid indicator-grid"
              />
              <text
                :x="asset.regimeChart.plotLeft - 8"
                :y="tick.y + 4"
                class="axis-label"
                text-anchor="end"
              >
                {{ tick.label }}
              </text>
            </g>

            <g v-for="series in asset.regimeChart.series" :key="series.key">
              <path
                :d="series.path"
                class="indicator-line"
                :stroke="series.color"
                stroke-dasharray="0"
                stroke-opacity="0.94"
              />
            </g>
          </svg>
        </div>

        <div v-if="asset.divergenceChart?.hasVisibleLines" class="indicator-chart-wrap divergence-chart-wrap">
          <div class="indicator-chart-head">
            <div class="indicator-chart-title">Foreign vs retail divergence no tempo</div>
            <div class="indicator-chart-legend">
              <span
                v-for="series in asset.divergenceChart.series"
                :key="series.key"
                class="indicator-legend-item"
              >
                <span
                  class="indicator-legend-swatch"
                  :style="{ backgroundColor: series.color, opacity: 0.92 }"
                />
                {{ series.shortLabel }}
                <strong>{{ formatPressureScore(series.lastValue) }}</strong>
              </span>
            </div>
          </div>
          <svg
            :viewBox="`0 0 ${asset.divergenceChart.width} ${asset.divergenceChart.height}`"
            class="indicator-chart"
          >
            <rect
              :x="asset.divergenceChart.plotLeft"
              :y="asset.divergenceChart.plotTop"
              :width="asset.divergenceChart.plotRight - asset.divergenceChart.plotLeft"
              :height="asset.divergenceChart.plotBottom - asset.divergenceChart.plotTop"
              class="plot-bg indicator-plot-bg"
              rx="12"
            />

            <g v-for="tick in asset.divergenceChart.yTicks" :key="`${asset.key}-div-y-${tick.value}`">
              <line
                :x1="asset.divergenceChart.plotLeft"
                :x2="asset.divergenceChart.plotRight"
                :y1="tick.y"
                :y2="tick.y"
                class="grid indicator-grid"
              />
              <text
                :x="asset.divergenceChart.plotLeft - 8"
                :y="tick.y + 4"
                class="axis-label"
                text-anchor="end"
              >
                {{ tick.label }}
              </text>
            </g>

            <g v-for="series in asset.divergenceChart.series" :key="series.key">
              <path
                :d="series.path"
                class="indicator-line"
                :stroke="series.color"
                :stroke-dasharray="series.dashArray"
                :stroke-opacity="series.opacity"
              />
            </g>
          </svg>
        </div>

      </article>
    </section>

    <section v-else-if="!loading && !errorMessage" class="empty-state">
      Nenhum ativo com candles chegou no payload ainda.
    </section>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AquilesBrand from '../components/AquilesBrand.vue'
import { getLatestIntradayCorrelationHistory, getLatestOptionsHeatmapContext, hardRefreshOptionsBase } from '../api/options'
import { resolveApiBaseUrl } from '../api'
import {
  formatCompactFloat,
  formatPressureScore,
  formatPrice,
  formatSignedBps,
  formatSignedFloat,
  formatSignedPoints,
  formatSignedQuantity,
  toNumber,
} from '../utils/marketFormatters'
import {
  formatBiasLabel,
  formatCurveAbsoluteShape,
  formatCurveAngle,
  formatCurveMacroRegime,
  formatCurvePercent,
  formatCurveProbability,
  formatCurveShapeLabel,
  getCurveRegimeRanking,
} from '../utils/macroCurve'
import {
  buildOptionsContextFallbackPanel,
  normalizeHeatmapPayload,
} from '../utils/macroHeatmapPayload'
import {
  formatTime,
  formatAxisTime,
  scopeSamplesToTradingSession,
  clamp,
  formatImplicitSentiment,
  fairValueSentimentClass,
  fairValueGaugeClass,
  buildCurveVisualization,
  formatFlexibleConfidence,
  getFairValueLegRanking,
  getFairValueShadowRanking,
  getStableQualityWindowSamples,
  buildStableLegMap,
  buildQualityPulse,
  buildQualityHistory,
  buildIntradayCorrelationHistoryPanel,
  buildCapturedFactorHistoryPanel,
  getFairValueShadowHaircutPoints,
  getFairValueGrossGap,
  getFairValueNetGap,
  getFairValueFollowThroughStateLabel,
  getFairValueCompositeRegimeLabel,
  getFairValueLocalAcceptanceLabel,
  buildFairValueSupportBalanceCommentary,
  buildFairValuePriceDriverCommentary,
  buildFairValueCompositeRegimeCommentary,
  buildFairValueLocalConfirmationCommentary,
  buildFairValueModelCommentary,
  buildFairValueReactionCommentary,
  buildFairValueConvergenceCommentary,
  buildFairValueCurveDeskCommentary,
  buildFairValueShadowCommentary,
  buildFairValueShadowSectionLead,
  formatValuePosition,
  formatFlowRegimeLabel,
  formatConfidenceScore,
  formatCompactSignedQuantity,
  formatProjectedMove,
  getValueCohortColor,
  getPoolOverlayKey,
  getPoolOverlayMeta,
  getGammaOverlayKey,
  getGammaOverlayMeta,
  getAssetFairValueSummary,
  formatPoolTriggerLabel,
  formatPoolDirectionLabel,
  formatPoolAggregationScopeLabel,
  getValueLevelTypeMeta,
  getIndicatorMetricMeta,
  pressureClass,
  flowRegimeClass,
  formatLevelDefenseStateLabel,
  levelDefenseClass,
  formatConcentrationStateLabel,
  concentrationClass,
  formatLocalPackageStateLabel,
  localPackageClass,
  formatStructuralDivergenceStateLabel,
  structuralDivergenceClass,
  formatContinuationStateLabel,
  continuationClass,
  formatTradeSignalLabel,
  formatNewsMarkerLabel,
  formatNewsBiasLabel,
  formatNewsAlignmentLabel,
  formatTradeActionLabel,
  formatEntryStyleLabel,
  formatLiquidityProviderLabel,
  formatTrapStateLabel,
  formatSqueezeStateLabel,
  formatStopRunStateLabel,
  formatRetailMicrostructureLabel,
  formatLiquidityRegionRoleLabel,
  formatLiquidityPoolStateLabel,
  formatLiquidityPoolTypeLabel,
  formatGammaRoleLabel,
  formatGammaStateLabel,
  formatFairValueStateLabel,
  formatLocationLabel,
  formatReferenceLabel,
  thermometerClass,
  riskClass,
  newsBiasClass,
  newsAlignmentClass,
  liquidityIntelClass,
  liquidityPoolClass,
  formatAnnotationTypeLabel,
  formatAnnotationShortLabel,
  annotationToneClass,
  formatDivergenceStateLabel,
  divergenceClass,
  computeBucketDivergenceMetrics,
  classifyBucketResponse,
  classifyBucketEfficiency,
  resolveBucketValuePosition,
  classifyBucketFlowRegime,
} from '../utils/macroHeatmapModels'
import {
  RANGE_OPTIONS,
  TIMEFRAME_OPTIONS,
  PARTICIPANT_SCOPE_OPTIONS,
  PARTICIPANT_SIDE_OPTIONS,
  PRESSURE_COHORTS,
  VALUE_COHORT_OPTIONS,
  VALUE_LEVEL_TYPE_OPTIONS,
  INDICATOR_METRIC_OPTIONS,
  INDICATOR_COHORT_OPTIONS,
  HISTOGRAM_MODE_OPTIONS,
  REGIME_CHART_MODE_OPTIONS,
  CORRELATION_LOOKBACK_OPTIONS,
  CORRELATION_HORIZON_OPTIONS,
  CORRELATION_MODE_OPTIONS,
  CAPTURED_FACTOR_DISPLAY_OPTIONS,
  ANNOTATION_LEGEND_ITEMS,
  POOL_OVERLAY_OPTIONS,
  GAMMA_OVERLAY_OPTIONS,
  FAIR_VALUE_FEATURE_OPTIONS,
  FAIR_VALUE_CORE_LEG_OPTIONS,
  FAIR_VALUE_SHADOW_LEG_OPTIONS,
  FAIR_VALUE_RANKING_WINDOW_OPTIONS,
  FAIR_VALUE_HELP_TEXT,
  CURVE_HELP_TEXT,
} from '../config/macroHeatmapConfig'

const router = useRouter()

const panelData = ref(null)
const loading = ref(false)
const loadingOptionsContext = ref(false)
const loadingIntradayCorrelation = ref(false)
const hardReloadingOptions = ref(false)
const errorMessage = ref('')
const viewportState = ref({})
const hoverState = ref({})
const dragState = ref({})
const participantScope = ref('foreign')
const participantSide = ref('both')
const selectedBrokerKeys = ref([])
const selectedValueCohortKeys = ref([])
const selectedValueLevelKeys = ref([])
const selectedIndicatorMetricKeys = ref(['pressure', 'efficiency'])
const selectedIndicatorCohortKeys = ref([])
const selectedAnnotationTypeKeys = ref([])
const selectedPoolOverlayKeys = ref([])
const poolOverlayEnabled = ref(true)
const selectedGammaOverlayKeys = ref([])
const gammaOverlayEnabled = ref(true)
const fairValueOverlayEnabled = ref(true)
const selectedFairValueFeatureKeys = ref([
  'price',
  'fair_value',
  'legacy_fair_value',
  'legacy_bands',
  'quality_adjusted',
  'bands',
  'quality_ribbon',
  'gamma',
  'distortion',
  'macro_legs',
])
const selectedFairValueCoreLegKeys = ref([
  'rates',
  'curve_medium_long',
  'equity',
  'equity_brazil',
  'credit',
  'credit_brazil',
  'fx',
  'commodities',
  'us_rates',
])
const selectedFairValueShadowLegKeys = ref([
  'credit_shadow',
  'bond_quality',
  'corporate_credit',
  'em_stress',
  'funding',
  'volatility',
  'brazil_relative',
  'sovereign_credit',
])
const expandedFairValueRankingWindowKeys = ref([])
const selectedHistogramMode = ref('off')
const selectedRegimeChartMode = ref('on')
const intradayCorrelationHistory = ref(null)
const correlationLookbackDays = ref(1)
const correlationHorizonMinutes = ref(5)
const selectedCorrelationModes = ref(['pure', 'neural'])
const selectedCorrelationFactorKeys = ref([])
const selectedCapturedFactorKeys = ref([])
const capturedFactorDisplayMode = ref('day_pct')
const capturedFactorFilterText = ref('')
let capturedFactorSelectionTouched = false
let refreshTimer = null
let optionsContextTimer = null
let correlationHistoryTimer = null
let lastOptionsContextLoadedAt = 0
let lastCorrelationLoadedAt = 0
let lastCorrelationRequestKey = ''
let syncingCorrelationSelection = false

const CHART_WIDTH = 920
const CHART_HEIGHT = 300
const PLOT_LEFT = 64
const PLOT_RIGHT = CHART_WIDTH - 20
const PLOT_TOP = 20
const PLOT_BOTTOM = CHART_HEIGHT - 44
const OPTIONS_CONTEXT_REFRESH_MS = 5 * 60 * 1000
const INTRADAY_CORRELATION_REFRESH_MS = 5 * 60 * 1000
const timestampLabel = computed(() => {
  const value = panelData.value?.generated_at
  if (!value) return '--'
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return '--'
  return dt.toLocaleString('pt-BR', {
    hour12: false,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
})

const assetCount = computed(() => {
  const assets = panelData.value?.assets
  return Array.isArray(assets) ? assets.length : 0
})

const crossAssetFlowPackage = computed(() => (
  panelData.value?.cross_asset_flow_package && typeof panelData.value.cross_asset_flow_package === 'object'
    ? panelData.value.cross_asset_flow_package
    : null
))

const structuralDivergenceModel = computed(() => (
  panelData.value?.structural_divergence_model && typeof panelData.value.structural_divergence_model === 'object'
    ? panelData.value.structural_divergence_model
    : null
))

const continuationReversalModel = computed(() => (
  panelData.value?.continuation_reversal_model && typeof panelData.value.continuation_reversal_model === 'object'
    ? panelData.value.continuation_reversal_model
    : null
))

const winTradeThermometer = computed(() => (
  panelData.value?.win_trade_thermometer && typeof panelData.value.win_trade_thermometer === 'object'
    ? panelData.value.win_trade_thermometer
    : null
))

const liquidityIntelligenceModel = computed(() => (
  panelData.value?.liquidity_intelligence_model && typeof panelData.value.liquidity_intelligence_model === 'object'
    ? panelData.value.liquidity_intelligence_model
    : null
))

const liquidityPoolModel = computed(() => (
  panelData.value?.liquidity_pool_model && typeof panelData.value.liquidity_pool_model === 'object'
    ? panelData.value.liquidity_pool_model
    : null
))

const intradayCorrelationHistoryPanel = computed(() => (
  buildIntradayCorrelationHistoryPanel(intradayCorrelationHistory.value, {
    loading: loadingIntradayCorrelation.value,
    selectedModes: selectedCorrelationModes.value,
  })
))

const optionsFlowAlignmentModel = computed(() => (
  panelData.value?.options_flow_alignment_model && typeof panelData.value.options_flow_alignment_model === 'object'
    ? panelData.value.options_flow_alignment_model
    : null
))

const macroNewsTimeline = computed(() => (
  Array.isArray(panelData.value?.news_thermometer_context?.timeline)
    ? panelData.value.news_thermometer_context.timeline
    : []
))

const normalizedAssets = computed(() => {
  const assets = panelData.value?.assets
  return Array.isArray(assets) ? assets : []
})

const currentWinAsset = computed(() => (
  normalizedAssets.value.find((asset) => asset?.key === 'win') || null
))

const capturedFactorHistoryPanel = computed(() => (
  buildCapturedFactorHistoryPanel(currentWinAsset.value, intradayCorrelationHistory.value, {
    displayMode: capturedFactorDisplayMode.value,
    filterText: capturedFactorFilterText.value,
    selectedFactorKeys: selectedCapturedFactorKeys.value,
  })
))

const selectedScopeLabel = computed(() => (
  PARTICIPANT_SCOPE_OPTIONS.find((option) => option.value === participantScope.value)?.label || 'estrangeiro'
))

const selectedSideLabel = computed(() => (
  PARTICIPANT_SIDE_OPTIONS.find((option) => option.value === participantSide.value)?.label || 'os dois'
))

const availableBrokerOptions = computed(() => {
  const options = new Map()
  for (const asset of normalizedAssets.value) {
    const observedRows = [
      ...(Array.isArray(asset?.participant_catalog) ? asset.participant_catalog : []),
      ...(Array.isArray(asset?.latest_participants) ? asset.latest_participants : []),
      ...(Array.isArray(asset?.heat_points) ? asset.heat_points : []),
    ]
    for (const row of observedRows) {
      if (!matchesParticipantScope({
        isRetail: row?.origin_scope === 'retail' || row?.broker_segment === 'retail' || row?.is_retail_broker,
        isForeign: row?.origin_scope === 'foreign' || row?.broker_segment === 'foreign' || row?.is_foreign_broker,
      }, participantScope.value)) {
        continue
      }
      const key = getBrokerFilterKey(row)
      if (!key || options.has(key)) continue
      options.set(key, {
        key,
        label: row?.origin_label || row?.broker_name || key,
      })
    }
  }
  return [...options.values()].sort((left, right) => left.label.localeCompare(right.label, 'pt-BR'))
})

function getBrokerFilterKey(item) {
  if (!item) return null
  if (item.originRegistryKey) return String(item.originRegistryKey)
  if (item.origin_registry_key) return String(item.origin_registry_key)
  if (item.originLabel) return String(item.originLabel)
  if (item.origin_label) return String(item.origin_label)
  if (item.broker_name) return String(item.broker_name)
  return null
}

function matchesBrokerSelection(item, selectedKeys) {
  if (!selectedKeys?.length) return true
  const key = getBrokerFilterKey(item)
  return key ? selectedKeys.includes(key) : false
}

function clearBrokerSelection() {
  selectedBrokerKeys.value = []
}

function toggleBrokerSelection(key) {
  if (!key) return
  selectedBrokerKeys.value = selectedBrokerKeys.value.includes(key)
    ? selectedBrokerKeys.value.filter((item) => item !== key)
    : [...selectedBrokerKeys.value, key]
}

function clearValueCohortSelection() {
  selectedValueCohortKeys.value = []
}

function toggleValueCohortSelection(key) {
  if (!key) return
  selectedValueCohortKeys.value = selectedValueCohortKeys.value.includes(key)
    ? selectedValueCohortKeys.value.filter((item) => item !== key)
    : [...selectedValueCohortKeys.value, key]
}

function clearValueLevelSelection() {
  selectedValueLevelKeys.value = []
}

function toggleValueLevelSelection(key) {
  if (!key) return
  selectedValueLevelKeys.value = selectedValueLevelKeys.value.includes(key)
    ? selectedValueLevelKeys.value.filter((item) => item !== key)
    : [...selectedValueLevelKeys.value, key]
}

function clearIndicatorMetricSelection() {
  selectedIndicatorMetricKeys.value = []
}

function toggleIndicatorMetricSelection(key) {
  if (!key) return
  selectedIndicatorMetricKeys.value = selectedIndicatorMetricKeys.value.includes(key)
    ? selectedIndicatorMetricKeys.value.filter((item) => item !== key)
    : [...selectedIndicatorMetricKeys.value, key]
}

function clearIndicatorCohortSelection() {
  selectedIndicatorCohortKeys.value = []
}

function toggleIndicatorCohortSelection(key) {
  if (!key) return
  selectedIndicatorCohortKeys.value = selectedIndicatorCohortKeys.value.includes(key)
    ? selectedIndicatorCohortKeys.value.filter((item) => item !== key)
    : [...selectedIndicatorCohortKeys.value, key]
}

function clearAnnotationTypeSelection() {
  selectedAnnotationTypeKeys.value = []
}

function toggleAnnotationTypeSelection(key) {
  if (!key) return
  selectedAnnotationTypeKeys.value = selectedAnnotationTypeKeys.value.includes(key)
    ? selectedAnnotationTypeKeys.value.filter((item) => item !== key)
    : [...selectedAnnotationTypeKeys.value, key]
}

function clearPoolOverlaySelection() {
  poolOverlayEnabled.value = true
  selectedPoolOverlayKeys.value = []
}

function disablePoolOverlay() {
  poolOverlayEnabled.value = false
}

function togglePoolOverlaySelection(key) {
  if (!key) return
  poolOverlayEnabled.value = true
  selectedPoolOverlayKeys.value = selectedPoolOverlayKeys.value.includes(key)
    ? selectedPoolOverlayKeys.value.filter((item) => item !== key)
    : [...selectedPoolOverlayKeys.value, key]
}

function clearGammaOverlaySelection() {
  gammaOverlayEnabled.value = true
  selectedGammaOverlayKeys.value = []
}

function disableGammaOverlay() {
  gammaOverlayEnabled.value = false
}

function toggleGammaOverlaySelection(key) {
  if (!key) return
  gammaOverlayEnabled.value = true
  selectedGammaOverlayKeys.value = selectedGammaOverlayKeys.value.includes(key)
    ? selectedGammaOverlayKeys.value.filter((item) => item !== key)
    : [...selectedGammaOverlayKeys.value, key]
}

function clearFairValueFeatureSelection() {
  selectedFairValueFeatureKeys.value = FAIR_VALUE_FEATURE_OPTIONS.map((item) => item.key)
}

function toggleFairValueFeatureSelection(key) {
  if (!key) return
  selectedFairValueFeatureKeys.value = selectedFairValueFeatureKeys.value.includes(key)
    ? selectedFairValueFeatureKeys.value.filter((item) => item !== key)
    : [...selectedFairValueFeatureKeys.value, key]
}

function clearFairValueCoreLegSelection() {
  selectedFairValueCoreLegKeys.value = []
}

function toggleFairValueCoreLegSelection(key) {
  if (!key) return
  selectedFairValueCoreLegKeys.value = selectedFairValueCoreLegKeys.value.includes(key)
    ? selectedFairValueCoreLegKeys.value.filter((item) => item !== key)
    : [...selectedFairValueCoreLegKeys.value, key]
}

function clearFairValueShadowLegSelection() {
  selectedFairValueShadowLegKeys.value = []
}

function toggleFairValueShadowLegSelection(key) {
  if (!key) return
  selectedFairValueShadowLegKeys.value = selectedFairValueShadowLegKeys.value.includes(key)
    ? selectedFairValueShadowLegKeys.value.filter((item) => item !== key)
    : [...selectedFairValueShadowLegKeys.value, key]
}

function toggleFairValueRankingWindow(key) {
  if (!key) return
  expandedFairValueRankingWindowKeys.value = expandedFairValueRankingWindowKeys.value.includes(key)
    ? expandedFairValueRankingWindowKeys.value.filter((item) => item !== key)
    : [...expandedFairValueRankingWindowKeys.value, key]
}

function getRangeKey(assetKey) {
  return viewportState.value[assetKey]?.rangeKey || 'day'
}

function getTimeframeMinutes(assetKey) {
  return viewportState.value[assetKey]?.timeframeMinutes || 1
}

function getRangeOption(rangeKey) {
  return RANGE_OPTIONS.find((item) => item.key === rangeKey) || RANGE_OPTIONS[0]
}

function getHover(assetKey) {
  return hoverState.value[assetKey] || null
}

function clampTagX(x, chart) {
  return clamp(x - 29, chart.plotLeft, chart.plotRight - 58)
}

function ensureViewport(assetKey, asset) {
  const candles = Array.isArray(asset?.candles_1m) ? asset.candles_1m : []
  const timestamps = candles
    .map((candle) => new Date(candle.time).getTime())
    .filter(Number.isFinite)
    .sort((a, b) => a - b)
  const maxTs = timestamps.length ? timestamps[timestamps.length - 1] : Date.now()
  const state = viewportState.value[assetKey]
  if (!state) {
    viewportState.value = {
      ...viewportState.value,
      [assetKey]: {
        rangeKey: 'day',
        endTs: maxTs,
        timeframeMinutes: 1,
      },
    }
    return
  }
  const nextState = { ...state }
  if (!Number.isFinite(nextState.endTs) || nextState.endTs > maxTs) {
    nextState.endTs = maxTs
  }
  if (!Number.isFinite(nextState.timeframeMinutes) || nextState.timeframeMinutes < 1) {
    nextState.timeframeMinutes = 1
  }
  viewportState.value = {
    ...viewportState.value,
    [assetKey]: nextState,
  }
}

watch(
  () => normalizedAssets.value,
  (assets) => {
    for (const asset of assets) {
      ensureViewport(asset.key, asset)
    }
  },
  { immediate: true },
)

watch(participantScope, () => {
  selectedBrokerKeys.value = []
})

watch(availableBrokerOptions, (options) => {
  const valid = new Set(options.map((option) => option.key))
  selectedBrokerKeys.value = selectedBrokerKeys.value.filter((key) => valid.has(key))
})

watch(
  () => capturedFactorHistoryPanel.value?.availableFactors?.map((item) => item.factor).join('|') || '',
  () => {
    const panel = capturedFactorHistoryPanel.value
    if (!panel) {
      selectedCapturedFactorKeys.value = []
      return
    }
    const valid = new Set(panel.availableFactors.map((item) => item.factor))
    const persisted = selectedCapturedFactorKeys.value.filter((key) => valid.has(key))
    const next = persisted.length
      ? persisted
      : capturedFactorSelectionTouched
        ? []
        : panel.defaultFactors
    if (next.join(',') !== selectedCapturedFactorKeys.value.join(',')) {
      selectedCapturedFactorKeys.value = [...next]
    }
  },
  { immediate: true },
)

function setRange(assetKey, rangeKey, asset) {
  ensureViewport(assetKey, asset)
  const candles = Array.isArray(asset?.candles_1m) ? asset.candles_1m : []
  const timestamps = candles
    .map((candle) => new Date(candle.time).getTime())
    .filter(Number.isFinite)
    .sort((a, b) => a - b)
  const maxTs = timestamps.length ? timestamps[timestamps.length - 1] : Date.now()
  viewportState.value = {
    ...viewportState.value,
    [assetKey]: {
      rangeKey,
      endTs: maxTs,
      timeframeMinutes: viewportState.value[assetKey]?.timeframeMinutes || 1,
    },
  }
}

function setTimeframe(assetKey, minutes, asset) {
  ensureViewport(assetKey, asset)
  const candles = Array.isArray(asset?.candles_1m) ? asset.candles_1m : []
  const timestamps = candles
    .map((candle) => new Date(candle.time).getTime())
    .filter(Number.isFinite)
    .sort((a, b) => a - b)
  const maxTs = timestamps.length ? timestamps[timestamps.length - 1] : Date.now()
  viewportState.value = {
    ...viewportState.value,
    [assetKey]: {
      ...(viewportState.value[assetKey] || {}),
      timeframeMinutes: minutes,
      endTs: Math.min(viewportState.value[assetKey]?.endTs || maxTs, maxTs),
    },
  }
}

function shiftWindow(assetKey, direction, asset) {
  ensureViewport(assetKey, asset)
  const range = getRangeOption(getRangeKey(assetKey))
  if (range.minutes == null) return
  const candles = Array.isArray(asset?.candles_1m) ? asset.candles_1m : []
  const timestamps = candles
    .map((candle) => new Date(candle.time).getTime())
    .filter(Number.isFinite)
    .sort((a, b) => a - b)
  if (!timestamps.length) return

  const minTs = timestamps[0]
  const maxTs = timestamps[timestamps.length - 1]
  const spanMs = range.minutes * 60 * 1000
  const stepMs = Math.max(60 * 1000, Math.round(spanMs * 0.35))
  const currentEnd = viewportState.value[assetKey]?.endTs || maxTs
  const nextEnd = clamp(currentEnd + direction * stepMs, minTs + spanMs, maxTs)

  viewportState.value = {
    ...viewportState.value,
    [assetKey]: {
      ...(viewportState.value[assetKey] || {}),
      rangeKey: range.key,
      endTs: nextEnd,
      timeframeMinutes: viewportState.value[assetKey]?.timeframeMinutes || 1,
    },
  }
}

function resetWindow(assetKey, asset) {
  setRange(assetKey, 'day', asset)
}

function stopDrag(assetKey) {
  if (!dragState.value[assetKey]) return
  const next = { ...dragState.value }
  delete next[assetKey]
  dragState.value = next
}

function handlePointerLeave(assetKey) {
  stopDrag(assetKey)
  hoverState.value = {
    ...hoverState.value,
    [assetKey]: null,
  }
}

function startDrag(assetKey, event, asset) {
  ensureViewport(assetKey, asset)
  const range = getRangeOption(getRangeKey(assetKey))
  if (range.minutes == null) return
  const candles = Array.isArray(asset?.candles_1m) ? asset.candles_1m : []
  const timestamps = candles
    .map((candle) => new Date(candle.time).getTime())
    .filter(Number.isFinite)
    .sort((a, b) => a - b)
  if (!timestamps.length) return
  const spanMs = range.minutes * 60 * 1000
  dragState.value = {
    ...dragState.value,
    [assetKey]: {
      startClientX: event.clientX,
      startEndTs: viewportState.value[assetKey]?.endTs || timestamps[timestamps.length - 1],
      minTs: timestamps[0],
      maxTs: timestamps[timestamps.length - 1],
      spanMs,
      plotWidth: PLOT_RIGHT - PLOT_LEFT,
    },
  }
}

function floorBucketTs(ts, minutes) {
  const bucketMs = Math.max(1, minutes) * 60 * 1000
  return Math.floor(ts / bucketMs) * bucketMs
}

function toIso(ts) {
  return new Date(ts).toISOString()
}

function aggregateCandles(rawCandles, minutes) {
  const timeframe = Math.max(1, minutes)
  if (timeframe === 1) {
    return rawCandles.map((candle) => ({
      ...candle,
      bucketMinutes: 1,
      bucketStartTs: candle.ts,
      bucketEndTs: candle.ts + 60 * 1000,
      bucketLabel: formatAxisTime(candle.time),
    }))
  }

  const buckets = new Map()
  for (const candle of rawCandles) {
    const bucketStartTs = floorBucketTs(candle.ts, timeframe)
    const bucketEndTs = bucketStartTs + timeframe * 60 * 1000
    const key = String(bucketStartTs)
    const current = buckets.get(key)
    if (!current) {
      buckets.set(key, {
        time: toIso(bucketStartTs),
        ts: bucketStartTs,
        open: candle.open,
        high: candle.high,
        low: candle.low,
        close: candle.close,
        volume: toNumber(candle.volume) || 0,
        bucketMinutes: timeframe,
        bucketStartTs,
        bucketEndTs,
        bucketLabel: `${formatAxisTime(toIso(bucketStartTs))}-${formatAxisTime(toIso(bucketEndTs - 60 * 1000))}`,
      })
      continue
    }
    current.high = Math.max(current.high, candle.high)
    current.low = Math.min(current.low, candle.low)
    current.close = candle.close
    current.volume = (toNumber(current.volume) || 0) + (toNumber(candle.volume) || 0)
  }

  return [...buckets.values()].sort((a, b) => a.ts - b.ts)
}

function classifyExecutionHint(side, averagePrice, candle) {
  const avg = toNumber(averagePrice)
  const high = toNumber(candle?.high)
  const low = toNumber(candle?.low)
  if (!Number.isFinite(avg) || !Number.isFinite(high) || !Number.isFinite(low) || high <= low) {
    return 'sem leitura'
  }
  const position = (avg - low) / Math.max(high - low, 0.0000001)
  if (side === 'buy') {
    if (position >= 0.66) return 'agressao compra (est.)'
    if (position <= 0.33) return 'passivo compra (est.)'
    return 'compra mista'
  }
  if (side === 'sell') {
    if (position <= 0.33) return 'agressao venda (est.)'
    if (position >= 0.66) return 'passivo venda (est.)'
    return 'venda mista'
  }
  return 'sem leitura'
}

function resolveHeatAnchorPrice(event, candle) {
  const avg = toNumber(event?.averagePrice)
  const delta = toNumber(event?.deltaQuantity) || 0
  const high = toNumber(candle?.high)
  const low = toNumber(candle?.low)
  const close = toNumber(candle?.close)
  const open = toNumber(candle?.open)
  const bodyMid = Number.isFinite(open) && Number.isFinite(close) ? (open + close) / 2 : null

  if (Number.isFinite(high) && Number.isFinite(low)) {
    const candleLow = Math.min(low, high)
    const candleHigh = Math.max(low, high)
    const candleMid = Number.isFinite(bodyMid) ? bodyMid : (candleLow + candleHigh) / 2
    const candleRange = Math.max(candleHigh - candleLow, Math.abs(candleMid) * 0.00035, 1)
    const tolerance = Math.max(candleRange * 0.35, Math.abs(candleMid) * 0.00045)

    if (Number.isFinite(avg) && avg >= candleLow - tolerance && avg <= candleHigh + tolerance) {
      return clamp(avg, candleLow, candleHigh)
    }

    if (delta > 0) return clamp(candleMid + candleRange * 0.18, candleLow, candleHigh)
    if (delta < 0) return clamp(candleMid - candleRange * 0.18, candleLow, candleHigh)
    return clamp(candleMid, candleLow, candleHigh)
  }

  if (Number.isFinite(close)) return close
  if (Number.isFinite(bodyMid)) return bodyMid
  if (Number.isFinite(high) && Number.isFinite(low)) return (high + low) / 2
  return avg
}

function matchesParticipantScope(item, scope) {
  if (!item) return false
  if (scope === 'retail') return Boolean(item.isRetail)
  return Boolean(item.isForeign)
}

function matchesParticipantSide(item, side) {
  if (!item) return false
  if (side === 'both') {
    return ((toNumber(item.buyDelta) || 0) > 0)
      || ((toNumber(item.sellDelta) || 0) > 0)
      || ((toNumber(item.deltaQuantity) || 0) !== 0)
  }
  if (side === 'sell') {
    return (toNumber(item.sellDelta) || 0) > 0 || (toNumber(item.deltaQuantity) || 0) < 0
  }
  return (toNumber(item.buyDelta) || 0) > 0 || (toNumber(item.deltaQuantity) || 0) > 0
}

function buildScopedFlowSummary(flowSummary, scope, side, selectedKeys) {
  if (!flowSummary) {
    return {
      playerCount: 0,
      signedConfirmed: false,
      selectedQuantity: 0,
      topPlayers: [],
    }
  }

  const scopedPlayers = (Array.isArray(flowSummary.allPlayers) ? flowSummary.allPlayers : [])
    .filter((player) => matchesParticipantScope(player, scope))
    .filter((player) => matchesBrokerSelection(player, selectedKeys))

  const scopedTopPlayers = scopedPlayers
    .filter((player) => matchesParticipantSide(player, side))
    .sort((left, right) => {
      const leftValue = side === 'sell'
        ? (toNumber(left.sellDelta) || Math.abs(toNumber(left.netDelta) || 0))
        : (toNumber(left.buyDelta) || toNumber(left.netDelta) || 0)
      const rightValue = side === 'sell'
        ? (toNumber(right.sellDelta) || Math.abs(toNumber(right.netDelta) || 0))
        : (toNumber(right.buyDelta) || toNumber(right.netDelta) || 0)
      return rightValue - leftValue
    })
    .slice(0, 5)

  const topBuyers = scopedPlayers
    .filter((player) => (toNumber(player.buyDelta) || 0) > 0)
    .sort((left, right) => (toNumber(right.buyDelta) || toNumber(right.netDelta) || 0) - (toNumber(left.buyDelta) || toNumber(left.netDelta) || 0))
    .slice(0, 5)

  const topSellers = scopedPlayers
    .filter((player) => (toNumber(player.sellDelta) || 0) > 0)
    .sort((left, right) => (toNumber(right.sellDelta) || Math.abs(toNumber(right.netDelta) || 0)) - (toNumber(left.sellDelta) || Math.abs(toNumber(left.netDelta) || 0)))
    .slice(0, 5)

  const buyQuantity = scope === 'retail'
    ? (flowSummary.retailBuyQuantity || 0)
    : (flowSummary.foreignBuyQuantity || 0)
  const sellQuantity = scope === 'retail'
    ? (flowSummary.retailSellQuantity || 0)
    : (flowSummary.foreignSellQuantity || 0)
  const selectedQuantity = side === 'both'
    ? buyQuantity + sellQuantity
    : side === 'sell'
      ? sellQuantity
      : buyQuantity

  return {
    playerCount: scopedPlayers.length,
    signedConfirmed: Boolean(flowSummary.signedConfirmed),
    selectedQuantity,
    buyQuantity,
    sellQuantity,
    topPlayers: scopedTopPlayers,
    topBuyers,
    topSellers,
  }
}

function getDisplayFlowSummary(assetKey) {
  const raw = getHover(assetKey)?.flowSummary
  return buildScopedFlowSummary(raw, participantScope.value, participantSide.value, selectedBrokerKeys.value)
}

function buildFlowMap(asset, aggregatedCandles, timeframeMinutes) {
  const heatPoints = (Array.isArray(asset?.heat_points) ? asset.heat_points : [])
    .map((point) => ({
      ...point,
      capturedTs: new Date(point.captured_at).getTime(),
      sampleCandleTs: point.sample_candle_time ? new Date(point.sample_candle_time).getTime() : null,
      quantityValue: toNumber(point.quantity_float) ?? 0,
      averagePriceValue: toNumber(point.average_price_float),
    }))
    .filter((point) => Number.isFinite(point.capturedTs))
    .sort((a, b) => a.capturedTs - b.capturedTs)
  const bucketMap = new Map()
  const brokerBaseline = new Map()

  for (const point of heatPoints) {
    const brokerKey = `${point.broker_id}::${point.broker_name || 'Player'}`
    const previous = brokerBaseline.get(brokerKey)
    brokerBaseline.set(brokerKey, {
      quantityValue: point.quantityValue,
      averagePriceValue: point.averagePriceValue,
    })
    if (!previous) continue

    const deltaQuantity = point.quantityValue - previous.quantityValue
    if (!Number.isFinite(deltaQuantity) || Math.abs(deltaQuantity) < 0.000001) continue

    const referenceTs = Number.isFinite(point.sampleCandleTs) ? point.sampleCandleTs : point.capturedTs
    const bucketStartTs = floorBucketTs(referenceTs, timeframeMinutes)
    const key = String(bucketStartTs)
    let bucket = bucketMap.get(key)
    if (!bucket) {
      bucket = {
        buyQuantity: 0,
        sellQuantity: 0,
        netQuantity: 0,
        foreignBuyQuantity: 0,
        foreignSellQuantity: 0,
        foreignPlayerCount: 0,
        retailBuyQuantity: 0,
        retailSellQuantity: 0,
        retailPlayerCount: 0,
        signedConfirmed: false,
        playerCount: 0,
        topBuyers: [],
        topSellers: [],
        provisionalCount: 0,
        confirmedCount: 0,
        foreignHeatEvents: [],
        retailHeatEvents: [],
        players: new Map(),
      }
      bucketMap.set(key, bucket)
    }

    const signedDelta = deltaQuantity
    if (signedDelta > 0) bucket.buyQuantity += signedDelta
    if (signedDelta < 0) bucket.sellQuantity += Math.abs(signedDelta)
    bucket.netQuantity += signedDelta
    if (point.side === 'sell' || point.quantityValue < 0) bucket.confirmedCount += 1
    else bucket.provisionalCount += 1

    const current = bucket.players.get(brokerKey) || {
      broker_id: point.broker_id,
      broker_name: point.broker_name || `Broker ${point.broker_id ?? '--'}`,
      grossDelta: 0,
      netDelta: 0,
      buyDelta: 0,
      sellDelta: 0,
      weightedPriceSum: 0,
      weightedPriceCount: 0,
      relativePercentage: 0,
      isForeign: Boolean(point.is_foreign_broker),
      isRetail: Boolean(point.is_retail_broker),
      brokerSegment: point.broker_segment || point.origin_scope || 'local_or_unclassified',
      originRegistryKey: point.origin_registry_key || null,
      originLabel: point.origin_label || null,
    }
    current.grossDelta += Math.abs(signedDelta)
    current.netDelta += signedDelta
    current.buyDelta += Math.max(signedDelta, 0)
    current.sellDelta += Math.max(-signedDelta, 0)
    if (Number.isFinite(point.averagePriceValue) && Math.abs(signedDelta) > 0) {
      current.weightedPriceSum += point.averagePriceValue * Math.abs(signedDelta)
      current.weightedPriceCount += Math.abs(signedDelta)
    }
    current.relativePercentage = Math.max(current.relativePercentage, Math.abs(toNumber(point.relative_percentage_float) || 0))
    bucket.players.set(brokerKey, current)

    if (current.isForeign) {
      if (signedDelta > 0) bucket.foreignBuyQuantity += signedDelta
      if (signedDelta < 0) bucket.foreignSellQuantity += Math.abs(signedDelta)
      bucket.foreignHeatEvents.push({
        broker_id: point.broker_id,
        broker_name: point.broker_name || `Broker ${point.broker_id ?? '--'}`,
        deltaQuantity: signedDelta,
        averagePrice: point.averagePriceValue,
        isForeign: true,
        isRetail: false,
        originRegistryKey: point.origin_registry_key || null,
        originLabel: point.origin_label || null,
      })
    }

    if (current.isRetail) {
      if (signedDelta > 0) bucket.retailBuyQuantity += signedDelta
      if (signedDelta < 0) bucket.retailSellQuantity += Math.abs(signedDelta)
      bucket.retailHeatEvents.push({
        broker_id: point.broker_id,
        broker_name: point.broker_name || `Broker ${point.broker_id ?? '--'}`,
        deltaQuantity: signedDelta,
        averagePrice: point.averagePriceValue,
        isForeign: false,
        isRetail: true,
        originRegistryKey: point.origin_registry_key || null,
        originLabel: point.origin_label || null,
      })
    }
  }

  for (const candle of aggregatedCandles) {
    const key = String(candle.bucketStartTs || candle.ts)
    const bucket = bucketMap.get(key) || {
      buyQuantity: 0,
      sellQuantity: 0,
      netQuantity: 0,
      foreignBuyQuantity: 0,
      foreignSellQuantity: 0,
      foreignPlayerCount: 0,
      retailBuyQuantity: 0,
      retailSellQuantity: 0,
      retailPlayerCount: 0,
      signedConfirmed: false,
      playerCount: 0,
      topBuyers: [],
      topSellers: [],
      provisionalCount: 0,
      confirmedCount: 0,
      foreignHeatEvents: [],
      retailHeatEvents: [],
      players: new Map(),
    }
    const players = [...(bucket.players?.values() || [])]
      .map((player) => {
        const avgPrice = player.weightedPriceCount > 0
          ? player.weightedPriceSum / player.weightedPriceCount
          : null
        const netSide = player.netDelta > 0 ? 'buy' : player.netDelta < 0 ? 'sell' : 'flat'
        return {
          broker_id: player.broker_id,
          broker_name: player.broker_name,
          grossDelta: player.grossDelta,
          netDelta: player.netDelta,
          buyDelta: player.buyDelta,
          sellDelta: player.sellDelta,
          averagePrice: avgPrice,
          relativePercentage: player.relativePercentage,
          netSide,
          isForeign: player.isForeign,
          isRetail: player.isRetail,
          brokerSegment: player.brokerSegment,
          originRegistryKey: player.originRegistryKey,
          originLabel: player.originLabel,
          executionLabel: classifyExecutionHint(netSide, avgPrice, candle),
        }
      })
      .sort((a, b) => (b.grossDelta || 0) - (a.grossDelta || 0))

    const topBuyers = players
      .filter((player) => (player.buyDelta || 0) > 0)
      .sort((a, b) => (b.buyDelta || 0) - (a.buyDelta || 0))
      .slice(0, 5)

    const topSellers = players
      .filter((player) => (player.sellDelta || 0) > 0)
      .sort((a, b) => (b.sellDelta || 0) - (a.sellDelta || 0))
      .slice(0, 5)

    bucket.playerCount = bucket.players?.size || players.length
    bucket.foreignPlayerCount = players.filter((player) => player.isForeign).length
    bucket.retailPlayerCount = players.filter((player) => player.isRetail).length
    bucket.signedConfirmed = bucket.confirmedCount > 0
    bucket.topBuyers = topBuyers
    bucket.topSellers = topSellers
    bucket.allPlayers = players
    bucketMap.set(key, bucket)
  }

  return bucketMap
}

function computeBucketIndicatorMetrics(flowSummary, candle) {
  const open = toNumber(candle?.open) || 0
  const close = toNumber(candle?.close) || open
  const high = toNumber(candle?.high)
  const low = toNumber(candle?.low)
  const priceMovePoints = close - open
  const rangePoints = Number.isFinite(high) && Number.isFinite(low)
    ? Math.abs(high - low)
    : Math.abs(priceMovePoints)
  const effectiveRange = Math.max(rangePoints, Math.abs(priceMovePoints), 1)
  const priceRatio = clamp(priceMovePoints / effectiveRange, -1, 1)

  const totalGross = Math.max(
    0,
    (toNumber(flowSummary?.buyQuantity) || 0) + (toNumber(flowSummary?.sellQuantity) || 0),
  )

  const cohortValues = {
    net: {
      buy: toNumber(flowSummary?.buyQuantity) || 0,
      sell: toNumber(flowSummary?.sellQuantity) || 0,
      playerCount: toNumber(flowSummary?.playerCount) || 0,
    },
    foreign: {
      buy: toNumber(flowSummary?.foreignBuyQuantity) || 0,
      sell: toNumber(flowSummary?.foreignSellQuantity) || 0,
      playerCount: toNumber(flowSummary?.foreignPlayerCount) || 0,
    },
    retail: {
      buy: toNumber(flowSummary?.retailBuyQuantity) || 0,
      sell: toNumber(flowSummary?.retailSellQuantity) || 0,
      playerCount: toNumber(flowSummary?.retailPlayerCount) || 0,
    },
  }

  const result = {}
  for (const cohort of PRESSURE_COHORTS) {
    const buy = cohortValues[cohort.key]?.buy || 0
    const sell = cohortValues[cohort.key]?.sell || 0
    const gross = buy + sell
    const net = buy - sell
    const netAbs = Math.abs(net)
    const playerCount = cohortValues[cohort.key]?.playerCount || 0
    const netRatio = gross > 0 ? clamp(net / gross, -1, 1) : 0
    const grossShare = totalGross > 0 ? clamp(gross / totalGross, 0, 1) : 0
    const flowDirection = net > 0 ? 1 : net < 0 ? -1 : 0
    const priceDirection = priceMovePoints > 0 ? 1 : priceMovePoints < 0 ? -1 : 0
    const alignment = flowDirection && priceDirection
      ? (flowDirection === priceDirection ? 1 : -1)
      : 0
    const signedShare = grossShare * flowDirection
    const flowCommitment = gross > 0 ? clamp(netAbs / gross, 0, 1) : 0
    const rangeCapture = Math.abs(priceRatio)
    const pressureScore = gross > 0
      ? 100 * clamp((0.68 * netRatio) + (0.22 * signedShare) + (0.10 * alignment * Math.abs(priceRatio)), -1, 1)
      : null
    const efficiencyScore = gross > 0
      ? 100 * alignment * clamp(rangeCapture * flowCommitment, 0, 1)
      : null
    const absorptionScore = gross > 0
      ? 100 * clamp(flowCommitment * (1 - rangeCapture), 0, 1)
      : null
    const fragilityScore = gross > 0
      ? 100 * clamp(rangeCapture * (1 - flowCommitment), 0, 1)
      : null
    const confidenceScore = totalGross > 0 && gross > 0
      ? 100 * clamp((0.6 * grossShare) + (0.4 * Math.min(playerCount / 6, 1)), 0, 1)
      : null
    const responseState = classifyBucketResponse(netRatio, priceRatio, alignment)
    const efficiencyState = classifyBucketEfficiency(net, efficiencyScore || 0, absorptionScore || 0, fragilityScore || 0, alignment, priceMovePoints)

    result[cohort.key] = {
      buyQuantity: buy,
      sellQuantity: sell,
      grossQuantity: gross,
      netQuantity: net,
      grossShare,
      flowCommitment,
      pressureScore,
      efficiencyScore,
      absorptionScore,
      fragilityScore,
      confidenceScore,
      responseState,
      efficiencyState,
      eventCount: playerCount,
    }
  }
  return result
}

function computeBucketConcentrationMetrics(flowSummary) {
  const players = Array.isArray(flowSummary?.allPlayers) ? flowSummary.allPlayers : []
  const totalGross = players.reduce((sum, player) => sum + Math.abs(toNumber(player.grossDelta) || 0), 0)
  if (!players.length || totalGross <= 0) {
    return {
      state: 'inactive',
      topShare: 0,
      hhi: 0,
      breadthScore: 0,
      concentrationScore: 0,
    }
  }
  const shares = players.map((player) => Math.abs(toNumber(player.grossDelta) || 0) / totalGross)
  const hhiRaw = shares.reduce((sum, share) => sum + (share ** 2), 0)
  const hhi = hhiRaw * 10000
  const topShare = Math.max(...shares)
  const effectivePlayers = hhiRaw > 0 ? 1 / hhiRaw : 0
  const breadthScore = clamp(
    (Math.min(players.length / 6, 1) * 42)
      + (Math.min(effectivePlayers / 4.5, 1) * 38)
      + ((1 - topShare) * 20),
    0,
    100,
  )
  const concentrationScore = clamp(
    (topShare * 55) + (Math.min(hhi / 4000, 1) * 45),
    0,
    100,
  )
  let state = 'mixed_participation'
  if (players.length === 1 || topShare >= 0.74) state = 'single_name_push'
  else if (hhi >= 3200 || topShare >= 0.55) state = 'concentrated_drive'
  else if (players.length >= 4 && topShare <= 0.35 && hhi <= 2200) state = 'broad_participation'
  else if (topShare <= 0.42) state = 'two_way_participation'
  return {
    state,
    topShare,
    hhi,
    breadthScore,
    concentrationScore,
  }
}

function collectAnnotationPlayers(flowSummary, scope, side, limit = 3) {
  const players = Array.isArray(flowSummary?.allPlayers) ? flowSummary.allPlayers : []
  return players
    .filter((player) => (scope === 'retail' ? player.isRetail : player.isForeign))
    .filter((player) => (side === 'buy' ? (toNumber(player.buyDelta) || 0) > 0 : (toNumber(player.sellDelta) || 0) > 0))
    .sort((left, right) => {
      const leftValue = side === 'buy'
        ? (toNumber(left.buyDelta) || toNumber(left.netDelta) || 0)
        : (toNumber(left.sellDelta) || Math.abs(toNumber(left.netDelta) || 0))
      const rightValue = side === 'buy'
        ? (toNumber(right.buyDelta) || toNumber(right.netDelta) || 0)
        : (toNumber(right.sellDelta) || Math.abs(toNumber(right.netDelta) || 0))
      return rightValue - leftValue
    })
    .slice(0, limit)
}

function summarizeAnnotationPlayers(players, side) {
  if (!Array.isArray(players) || !players.length) return ''
  return players
    .map((player) => {
      const qty = side === 'buy'
        ? (toNumber(player.buyDelta) || toNumber(player.netDelta) || 0)
        : (toNumber(player.sellDelta) || Math.abs(toNumber(player.netDelta) || 0))
      return `${player.broker_name} ${formatSignedQuantity(qty, false)}`
    })
    .join(' | ')
}

function resolveNewsEventForTs(ts, timeline) {
  if (!Number.isFinite(ts) || !Array.isArray(timeline) || !timeline.length) return null
  const candidates = timeline
    .map((event) => {
      const eventTs = new Date(event.time).getTime()
      return Number.isFinite(eventTs) ? { ...event, eventTs } : null
    })
    .filter(Boolean)
    .filter((event) => event.eventTs <= ts && (ts - event.eventTs) <= (90 * 60 * 1000))
  return candidates.length ? candidates[candidates.length - 1] : null
}

function buildLiquidityAnnotations(entry, asset, newsTimeline) {
  const candle = entry?.candle
  const metrics = entry?.metrics || {}
  const flowSummary = entry?.flowSummary || {}
  if (!candle) return []

  const netMetric = metrics.net || {}
  const foreignMetric = metrics.foreign || {}
  const retailMetric = metrics.retail || {}
  const divergence = computeBucketDivergenceMetrics(metrics)
  const concentration = computeBucketConcentrationMetrics(entry?.flowSummary)
  const netValue = asset?.cohort_value_map?.cohorts?.net || {}
  const foreignValue = asset?.cohort_value_map?.cohorts?.foreign || {}
  const foreignRegime = classifyBucketFlowRegime(foreignMetric, foreignValue, candle)
  const netRegime = classifyBucketFlowRegime(netMetric, netValue, candle)
  const newsEvent = resolveNewsEventForTs(candle.ts, newsTimeline)
  const newsBias = String(newsEvent?.recommended_action || newsEvent?.event_bias || '').toLowerCase()
  const newsMarker = String(newsEvent?.marker || '').toLowerCase()
  const currentPosition = resolveBucketValuePosition(candle.close, netValue)
  const levelState = String(asset?.level_defense_model?.cohorts?.net?.primary_state || 'inactive')
  const supportPrice = toNumber(asset?.level_defense_model?.cohorts?.net?.support_level?.price)
  const resistancePrice = toNumber(asset?.level_defense_model?.cohorts?.net?.resistance_level?.price)
  const foreignBuyers = collectAnnotationPlayers(flowSummary, 'foreign', 'buy')
  const foreignSellers = collectAnnotationPlayers(flowSummary, 'foreign', 'sell')
  const retailBuyers = collectAnnotationPlayers(flowSummary, 'retail', 'buy')
  const retailSellers = collectAnnotationPlayers(flowSummary, 'retail', 'sell')
  const binSize = Math.max(toNumber(asset?.cohort_value_map?.bin_size) || 1, 1)
  const close = toNumber(candle.close) || 0
  const high = toNumber(candle.high) || close
  const low = toNumber(candle.low) || close
  const priceMove = (toNumber(candle.close) || 0) - (toNumber(candle.open) || 0)
  const events = []

  const pushEvent = (payload) => {
    events.push({
      lane: payload.lane,
      type: payload.type,
      label: payload.label || formatAnnotationTypeLabel(payload.type),
      severity: clamp(toNumber(payload.severity) || 0, 0, 100),
      biasSide: payload.biasSide || 'neutral',
      x: candle.x,
      ts: candle.ts,
      timeLabel: candle.bucketLabel,
      shortLabel: payload.shortLabel || formatAnnotationShortLabel(payload.type),
      detail: payload.detail || '',
      anchorPrice: Number.isFinite(toNumber(payload.anchorPrice)) ? toNumber(payload.anchorPrice) : close,
      characterization: payload.characterization || [
        `div ${formatDivergenceStateLabel(divergence.state)}`,
        `value ${String(currentPosition || 'unavailable').replaceAll('_', ' ')}`,
        `level ${formatLevelDefenseStateLabel(levelState)}`,
        `net ${formatPressureScore(netMetric.pressureScore)}`,
        `gringa ${formatPressureScore(foreignMetric.pressureScore)}`,
        `varejo ${formatPressureScore(retailMetric.pressureScore)}`,
      ].join(' | '),
      newsTitle: newsEvent?.driver_title || null,
      newsHeadline: newsEvent?.headline || null,
      newsBias: newsBias || null,
      newsMarker: newsMarker || null,
      foreignBrokerSummary: payload.foreignBrokerSummary || '',
      retailBrokerSummary: payload.retailBrokerSummary || '',
      netContracts: toNumber(netMetric.grossQuantity) || 0,
      foreignContracts: toNumber(foreignMetric.grossQuantity) || 0,
      retailContracts: toNumber(retailMetric.grossQuantity) || 0,
      grossContracts: Math.round(toNumber(payload.grossContracts) || 0),
    })
  }

  if (
    divergence.state === 'foreign_sell_vs_retail_buy'
    && (toNumber(retailMetric.pressureScore) || 0) >= 16
    && (currentPosition === 'above_value' || levelState === 'rejection_above_value' || netRegime.regimeState === 'divergence_buy' || netRegime.regimeState === 'exhaustion_buy')
  ) {
    pushEvent({
      lane: 'trap',
      type: 'bull_trap',
      severity: 82 + Math.min(Math.abs(toNumber(divergence.divergenceScore) || 0) * 0.15, 14),
      biasSide: 'sell',
      anchorPrice: high,
      detail: 'Varejo comprando com estrangeiro na venda em regiao fraca.',
      foreignBrokerSummary: summarizeAnnotationPlayers(foreignSellers, 'sell'),
      retailBrokerSummary: summarizeAnnotationPlayers(retailBuyers, 'buy'),
      grossContracts: retailMetric.grossQuantity,
    })
  }

  if (
    divergence.state === 'foreign_buy_vs_retail_sell'
    && (toNumber(retailMetric.pressureScore) || 0) <= -16
    && (currentPosition === 'below_value' || levelState === 'rejection_below_value' || netRegime.regimeState === 'divergence_sell' || netRegime.regimeState === 'exhaustion_sell')
  ) {
    pushEvent({
      lane: 'trap',
      type: 'sell_trap',
      severity: 82 + Math.min(Math.abs(toNumber(divergence.divergenceScore) || 0) * 0.15, 14),
      biasSide: 'buy',
      anchorPrice: low,
      detail: 'Varejo vendendo com estrangeiro na compra em regiao de armadilha.',
      foreignBrokerSummary: summarizeAnnotationPlayers(foreignBuyers, 'buy'),
      retailBrokerSummary: summarizeAnnotationPlayers(retailSellers, 'sell'),
      grossContracts: retailMetric.grossQuantity,
    })
  }

  if ((toNumber(retailMetric.pressureScore) || 0) >= 18 && (toNumber(foreignMetric.pressureScore) || 0) <= -8 && priceMove >= 0) {
    pushEvent({
      lane: 'retail',
      type: 'retail_buying_top',
      severity: 68 + Math.min(Math.abs(toNumber(retailMetric.pressureScore) || 0) * 0.2, 18),
      biasSide: 'sell',
      anchorPrice: high,
      detail: 'Compra de varejo desalinhada com o fluxo estrangeiro.',
      foreignBrokerSummary: summarizeAnnotationPlayers(foreignSellers, 'sell'),
      retailBrokerSummary: summarizeAnnotationPlayers(retailBuyers, 'buy'),
      grossContracts: retailMetric.grossQuantity,
    })
  }

  if ((toNumber(retailMetric.pressureScore) || 0) <= -18 && (toNumber(foreignMetric.pressureScore) || 0) >= 8 && priceMove <= 0) {
    pushEvent({
      lane: 'retail',
      type: 'retail_selling_bottom',
      severity: 68 + Math.min(Math.abs(toNumber(retailMetric.pressureScore) || 0) * 0.2, 18),
      biasSide: 'buy',
      anchorPrice: low,
      detail: 'Venda de varejo desalinhada com a compra mais institucional.',
      foreignBrokerSummary: summarizeAnnotationPlayers(foreignBuyers, 'buy'),
      retailBrokerSummary: summarizeAnnotationPlayers(retailSellers, 'sell'),
      grossContracts: retailMetric.grossQuantity,
    })
  }

  if (divergence.state === 'foreign_buy_vs_retail_sell' && ((newsBias === 'buy') || newsMarker === 'risk-on')) {
    pushEvent({
      lane: 'macro',
      type: 'foreign_buy_aligned',
      severity: 70 + Math.min(Math.abs(toNumber(divergence.leadScore) || 0) * 0.15, 18),
      biasSide: 'buy',
      anchorPrice: close,
      detail: 'Compra estrangeira alinhada com o driver macro dominante.',
      foreignBrokerSummary: summarizeAnnotationPlayers(foreignBuyers, 'buy'),
      grossContracts: foreignMetric.grossQuantity,
    })
  }

  if (divergence.state === 'foreign_sell_vs_retail_buy' && ((newsBias === 'sell') || newsMarker === 'risk-off')) {
    pushEvent({
      lane: 'macro',
      type: 'foreign_sell_aligned',
      severity: 70 + Math.min(Math.abs(toNumber(divergence.leadScore) || 0) * 0.15, 18),
      biasSide: 'sell',
      anchorPrice: close,
      detail: 'Venda estrangeira alinhada com o pano de fundo macro.',
      foreignBrokerSummary: summarizeAnnotationPlayers(foreignSellers, 'sell'),
      grossContracts: foreignMetric.grossQuantity,
    })
  }

  if (concentration.state === 'single_name_push' && (toNumber(netMetric.fragilityScore) || 0) >= 42) {
    pushEvent({
      lane: 'liq',
      type: 'thin_liquidity',
      severity: 60 + Math.min((toNumber(netMetric.fragilityScore) || 0) * 0.2, 22),
      biasSide: priceMove >= 0 ? 'buy' : 'sell',
      anchorPrice: close,
      detail: 'Movimento em liquidez fina, com pouca largura de participacao.',
      grossContracts: netMetric.grossQuantity,
    })
  }

  if (foreignRegime.regimeState === 'absorption_buy' && (toNumber(foreignMetric.absorptionScore) || 0) >= 55) {
    pushEvent({
      lane: 'liq',
      type: 'foreign_absorption_buy',
      severity: 64 + Math.min((toNumber(foreignMetric.absorptionScore) || 0) * 0.18, 18),
      biasSide: 'buy',
      anchorPrice: close,
      detail: 'Estrangeiro absorvendo venda sem ceder range.',
      foreignBrokerSummary: summarizeAnnotationPlayers(foreignBuyers, 'buy'),
      grossContracts: foreignMetric.grossQuantity,
    })
  }

  if (foreignRegime.regimeState === 'absorption_sell' && (toNumber(foreignMetric.absorptionScore) || 0) >= 55) {
    pushEvent({
      lane: 'liq',
      type: 'foreign_absorption_sell',
      severity: 64 + Math.min((toNumber(foreignMetric.absorptionScore) || 0) * 0.18, 18),
      biasSide: 'sell',
      anchorPrice: close,
      detail: 'Estrangeiro absorvendo compra sem entregar topo.',
      foreignBrokerSummary: summarizeAnnotationPlayers(foreignSellers, 'sell'),
      grossContracts: foreignMetric.grossQuantity,
    })
  }

  if (divergence.state === 'foreign_buy_vs_retail_sell' && priceMove > 0 && (toNumber(netMetric.fragilityScore) || 0) >= 38) {
    pushEvent({
      lane: 'stop',
      type: 'short_squeeze',
      severity: 70 + Math.min((toNumber(netMetric.fragilityScore) || 0) * 0.18, 16),
      biasSide: 'buy',
      anchorPrice: high,
      detail: 'Probabilidade de squeeze contra vendidos fracos.',
      foreignBrokerSummary: summarizeAnnotationPlayers(foreignBuyers, 'buy'),
      retailBrokerSummary: summarizeAnnotationPlayers(retailSellers, 'sell'),
      grossContracts: netMetric.grossQuantity,
    })
  }

  if (divergence.state === 'foreign_sell_vs_retail_buy' && priceMove < 0 && (toNumber(netMetric.fragilityScore) || 0) >= 38) {
    pushEvent({
      lane: 'stop',
      type: 'long_flush',
      severity: 70 + Math.min((toNumber(netMetric.fragilityScore) || 0) * 0.18, 16),
      biasSide: 'sell',
      anchorPrice: low,
      detail: 'Probabilidade de limpeza de comprados e flush.',
      foreignBrokerSummary: summarizeAnnotationPlayers(foreignSellers, 'sell'),
      retailBrokerSummary: summarizeAnnotationPlayers(retailBuyers, 'buy'),
      grossContracts: netMetric.grossQuantity,
    })
  }

  if (Number.isFinite(resistancePrice) && Math.abs(high - resistancePrice) <= (binSize * 1.1) && (toNumber(netMetric.fragilityScore) || 0) >= 34) {
    pushEvent({
      lane: 'stop',
      type: 'stop_above',
      severity: 58 + Math.min((toNumber(netMetric.fragilityScore) || 0) * 0.16, 16),
      biasSide: 'sell',
      anchorPrice: high,
      detail: 'Regiao de stop acima vulneravel a varredura.',
      grossContracts: netMetric.grossQuantity,
    })
  }

  if (Number.isFinite(supportPrice) && Math.abs(low - supportPrice) <= (binSize * 1.1) && (toNumber(netMetric.fragilityScore) || 0) >= 34) {
    pushEvent({
      lane: 'stop',
      type: 'stop_below',
      severity: 58 + Math.min((toNumber(netMetric.fragilityScore) || 0) * 0.16, 16),
      biasSide: 'buy',
      anchorPrice: low,
      detail: 'Regiao de stop abaixo vulneravel a varredura.',
      grossContracts: netMetric.grossQuantity,
    })
  }

  if (
    Math.sign(toNumber(foreignMetric.pressureScore) || 0) !== 0
    && Math.sign(toNumber(retailMetric.pressureScore) || 0) !== 0
    && Math.sign(toNumber(foreignMetric.pressureScore) || 0) !== Math.sign(toNumber(retailMetric.pressureScore) || 0)
  ) {
    pushEvent({
      lane: 'retail',
      type: 'retail_contra_trend',
      severity: 54 + Math.min(Math.abs(toNumber(divergence.leadScore) || 0) * 0.16, 18),
      biasSide: (toNumber(foreignMetric.pressureScore) || 0) > 0 ? 'buy' : 'sell',
      anchorPrice: close,
      detail: 'Varejo operando na direcao oposta ao fluxo dominante.',
      foreignBrokerSummary: summarizeAnnotationPlayers((toNumber(foreignMetric.pressureScore) || 0) > 0 ? foreignBuyers : foreignSellers, (toNumber(foreignMetric.pressureScore) || 0) > 0 ? 'buy' : 'sell'),
      retailBrokerSummary: summarizeAnnotationPlayers((toNumber(foreignMetric.pressureScore) || 0) > 0 ? retailSellers : retailBuyers, (toNumber(foreignMetric.pressureScore) || 0) > 0 ? 'sell' : 'buy'),
      grossContracts: retailMetric.grossQuantity,
    })
  }

  return events
    .sort((left, right) => right.severity - left.severity)
    .slice(0, 3)
}

const quickCharts = computed(() => {
  return normalizedAssets.value.map((asset) => {
    const rawCandles = (asset.candles_1m || [])
      .map((candle) => ({
        time: candle.time,
        ts: new Date(candle.time).getTime(),
        open: toNumber(candle.open),
        high: toNumber(candle.high),
        low: toNumber(candle.low),
        close: toNumber(candle.close),
        volume: toNumber(candle.volume),
      }))
      .filter((candle) => Number.isFinite(candle.ts))
      .sort((a, b) => a.ts - b.ts)
    const timeframeMinutes = getTimeframeMinutes(asset.key)
    const candles = aggregateCandles(rawCandles, timeframeMinutes)
    const flowMap = buildFlowMap(asset, candles, timeframeMinutes)

    const plotWidth = PLOT_RIGHT - PLOT_LEFT
    const plotHeight = PLOT_BOTTOM - PLOT_TOP
    const minTs = candles.length ? candles[0].ts : Date.now()
    const maxTs = candles.length ? candles[candles.length - 1].ts : Date.now()
    const totalSpan = Math.max(maxTs - minTs, 60 * 1000)

    const state = viewportState.value[asset.key] || { rangeKey: 'day', endTs: maxTs }
    const range = getRangeOption(state.rangeKey)
    const requestedSpan = range.minutes == null ? totalSpan : Math.max(range.minutes * 60 * 1000, 5 * 60 * 1000)
    const visibleMaxTs = range.minutes == null ? maxTs : clamp(state.endTs || maxTs, minTs + requestedSpan, maxTs)
    const visibleMinTs = range.minutes == null ? minTs : Math.max(minTs, visibleMaxTs - requestedSpan)
    const visibleSpan = Math.max(visibleMaxTs - visibleMinTs, 60 * 1000)

    const visibleCandles = candles.filter((candle) => candle.ts >= visibleMinTs && candle.ts <= visibleMaxTs)
    const chartCandlesRaw = visibleCandles.length ? visibleCandles : candles.slice(-1)

    const activeValueCohorts = new Set(
      selectedValueCohortKeys.value.length
        ? selectedValueCohortKeys.value
        : VALUE_COHORT_OPTIONS.map((option) => option.key),
    )
    const activeValueLevels = new Set(
      selectedValueLevelKeys.value.length
        ? selectedValueLevelKeys.value
        : VALUE_LEVEL_TYPE_OPTIONS.map((option) => option.key),
    )
    const activePoolOverlays = new Set(
      !poolOverlayEnabled.value
        ? []
        : selectedPoolOverlayKeys.value.length
          ? selectedPoolOverlayKeys.value
          : POOL_OVERLAY_OPTIONS.map((option) => option.key),
    )
    const activeGammaOverlays = new Set(
      !gammaOverlayEnabled.value
        ? []
        : selectedGammaOverlayKeys.value.length
          ? selectedGammaOverlayKeys.value
          : GAMMA_OVERLAY_OPTIONS.map((option) => option.key),
    )
    const activeFairValueFeatures = new Set(
      selectedFairValueFeatureKeys.value,
    )
    const activeFairValueCoreLegs = new Set(selectedFairValueCoreLegKeys.value)
    const activeFairValueShadowLegs = new Set(selectedFairValueShadowLegKeys.value)
    const rawValueLevelLines = []
    for (const cohort of VALUE_COHORT_OPTIONS) {
      if (!activeValueCohorts.has(cohort.key)) continue
      const cohortValue = asset?.cohort_value_map?.cohorts?.[cohort.key]
      if (!cohortValue) continue
      for (const levelKey of activeValueLevels) {
        const price = toNumber(cohortValue?.[levelKey])
        if (!Number.isFinite(price)) continue
        const meta = getValueLevelTypeMeta(levelKey)
        rawValueLevelLines.push({
          key: `${asset.key}-${cohort.key}-${levelKey}`,
          cohortKey: cohort.key,
          cohortLabel: cohort.label,
          levelKey,
          levelLabel: meta.label,
          shortLabel: `${cohort.label.toUpperCase()} ${meta.label}`,
          price,
          color: getValueCohortColor(cohort.key),
          dashArray: meta.dashArray,
          strokeWidth: meta.strokeWidth,
        })
      }
    }

    const liquidityPoolWindow = (
      (Array.isArray(asset?.liquidity_pools?.windows)
        ? asset.liquidity_pools.windows.find((window) => Number(window?.minutes) === timeframeMinutes)
        : null)
      || asset?.liquidity_pools?.primary
      || null
    )
    const rawLiquidityPoolBands = []
    for (const pool of (liquidityPoolWindow?.pools || [])) {
      const overlayKey = getPoolOverlayKey(pool?.pool_type)
      if (!activePoolOverlays.has(overlayKey)) continue
      const bandLow = toNumber(pool?.band_low)
      const bandHigh = toNumber(pool?.band_high)
      const price = toNumber(pool?.price)
      if (!Number.isFinite(bandLow) || !Number.isFinite(bandHigh) || !Number.isFinite(price)) continue
      const meta = getPoolOverlayMeta(pool?.pool_type)
      rawLiquidityPoolBands.push({
        key: `${asset.key}-pool-band-${overlayKey}-${pool.cohort}-${price}`,
        overlayKey,
        poolType: pool?.pool_type,
        shortLabel: meta.shortLabel,
        fill: meta.fill,
        stroke: meta.stroke,
        price,
        bandLow,
        bandHigh,
        cascadeProbability: toNumber(pool?.cascade_probability) || 0,
        stopContracts: toNumber(pool?.estimated_stop_closure_contracts) || 0,
        openContracts: toNumber(pool?.synthetic_open_inventory_contracts) || 0,
      })
    }

    const rawGammaRegions = asset.key === 'win'
      ? [
        ...((asset?.gamma_context?.regions || []).map((region) => ({ ...region, kind: 'strike_region' }))),
        ...((asset?.gamma_context?.special_regions || []).map((region) => ({ ...region, kind: 'special_region' }))),
      ]
        .filter((region) => activeGammaOverlays.has(getGammaOverlayKey(region)))
        .map((region, index) => {
          const meta = getGammaOverlayMeta(region)
          const price = toNumber(region?.price)
          const bandLow = Number.isFinite(toNumber(region?.band_low)) ? toNumber(region?.band_low) : price
          const bandHigh = Number.isFinite(toNumber(region?.band_high)) ? toNumber(region?.band_high) : price
          if (!Number.isFinite(price) || !Number.isFinite(bandLow) || !Number.isFinite(bandHigh)) return null
          return {
            key: `${asset.key}-gamma-${region.region_key || index}`,
            regionKey: region.region_key || `${index}`,
            symbol: region.symbol || meta.shortLabel,
            shortLabel: region.symbol || meta.shortLabel,
            displayLabel: region.display_label || region.short_label || meta.label,
            role: region.role || region.region_type,
            kind: region.kind,
            fill: meta.color,
            stroke: meta.color,
            dashArray: region.kind === 'special_region' ? '7 5' : '0',
            price,
            bandLow: Math.min(bandLow, bandHigh),
            bandHigh: Math.max(bandLow, bandHigh),
            description: region.description,
            commentary: region.commentary,
            openInterestTotal: toNumber(region.open_interest_total) || 0,
            gexNotionalFutureNet: toNumber(region.gex_notional_future_net) || 0,
            relevanceScore: toNumber(region.relevance_score) || 0,
            distanceToPricePoints: toNumber(region.distance_to_price_points),
            color: meta.color,
          }
        })
        .filter(Boolean)
      : []

    const aggregateFairValueSamplesByMinute = (samples) => {
      if (!Array.isArray(samples) || !samples.length) return []
      const minuteBuckets = new Map()
      samples
        .filter((sample) => Number.isFinite(sample?.ts))
        .sort((left, right) => left.ts - right.ts)
        .forEach((sample) => {
          const minuteBucketTs = Math.floor(sample.ts / 60000) * 60000
          const previous = minuteBuckets.get(minuteBucketTs)
          if (!previous || sample.ts >= previous.ts) {
            minuteBuckets.set(minuteBucketTs, {
              ...sample,
              minuteBucketTs,
            })
          }
        })
      return [...minuteBuckets.values()]
        .sort((left, right) => left.ts - right.ts)
        .map((sample, index) => ({
          ...sample,
          key: `${sample.key}-m${sample.minuteBucketTs || index}`,
        }))
    }

    const rawFairValueSamples = asset.key === 'win'
      ? aggregateFairValueSamplesByMinute(((asset?.fair_value_history?.samples || [])
        .map((sample, index) => ({
          key: `${asset.key}-fv-${index}`,
          ts: new Date(sample?.captured_at || '').getTime(),
          price: toNumber(sample?.fair_value_final_future),
          coreFairValue: toNumber(sample?.core_fair_value_xb1),
          legacyFairValue: toNumber(sample?.legacy_fair_value_xb1)
            ?? toNumber(sample?.legacy_core_fair_value_xb1)
            ?? toNumber(sample?.core_fair_value_xb1),
          qualityAdjustedPrice: toNumber(sample?.quality_adjusted_fair_value_xb1),
          shadowHaircutPoints: toNumber(sample?.shadow_haircut_points),
          bandLow: toNumber(sample?.fair_value_band_low),
          bandHigh: toNumber(sample?.fair_value_band_high),
          legacyBandLow: toNumber(sample?.legacy_fair_value_band_low)
            ?? toNumber(sample?.legacy_band_low)
            ?? toNumber(sample?.fair_value_band_low),
          legacyBandHigh: toNumber(sample?.legacy_fair_value_band_high)
            ?? toNumber(sample?.legacy_band_high)
            ?? toNumber(sample?.fair_value_band_high),
          qualityRibbonLow: toNumber(sample?.quality_ribbon?.lower),
          qualityRibbonHigh: toNumber(sample?.quality_ribbon?.upper),
          qualityRibbonReason: String(sample?.quality_ribbon?.reason || ''),
          currentPrice: toNumber(sample?.current_future_price),
          currentPriceSource: String(sample?.current_price_source || ''),
          mispricingValue: toNumber(sample?.mispricing_value),
          mispricingZscore: toNumber(sample?.mispricing_zscore),
          confidence: toNumber(sample?.confidence),
          riskQualityScore: toNumber(sample?.risk_quality_score),
          implicitSentiment: String(sample?.implicit_sentiment || ''),
          sentimentConfidence: toNumber(sample?.sentiment_confidence),
          coreShadowAlignment: toNumber(sample?.core_shadow_alignment),
          divergenceScore: toNumber(sample?.divergence_score),
          coherenceScore: toNumber(sample?.coherence_score),
          convergenceProbability: toNumber(sample?.convergence_probability),
          regimeBreakProbability: toNumber(sample?.regime_break_probability),
          qualityGauge: toNumber(sample?.quality_gauge),
          curveConditions: sample?.curve_conditions && typeof sample.curve_conditions === 'object'
            ? sample.curve_conditions
            : {},
          modelVersion: String(sample?.fair_value_model_version || 'fair_value_legacy_v1'),
          modelLabel: String(sample?.fair_value_model_label || 'fair value legacy'),
          blockTones: Array.isArray(sample?.block_tones) ? sample.block_tones : [],
          coreLegs: sample?.core_legs && typeof sample.core_legs === 'object' ? sample.core_legs : {},
          shadowLegs: sample?.shadow_legs && typeof sample.shadow_legs === 'object' ? sample.shadow_legs : {},
          rankingUp: Array.isArray(sample?.ranking_up) ? sample.ranking_up : [],
          rankingDown: Array.isArray(sample?.ranking_down) ? sample.ranking_down : [],
          qualityExplanation: sample?.quality_explanation && typeof sample.quality_explanation === 'object'
            ? sample.quality_explanation
            : {},
        }))
        .filter((sample) => Number.isFinite(sample.ts) && Number.isFinite(sample.price))))
      : []

    const rawLivePriceSamples = asset.key === 'win'
      ? aggregateFairValueSamplesByMinute(((asset?.live_capture_history?.snapshots || [])
        .map((snapshot, index) => ({
          key: `${asset.key}-live-px-${index}`,
          ts: new Date(snapshot?.captured_at || '').getTime(),
          currentPrice: toNumber(snapshot?.current_future_price),
          currentPriceSource: String(snapshot?.current_price_source || ''),
        }))
        .filter((sample) => Number.isFinite(sample.ts) && Number.isFinite(sample.currentPrice))))
      : []
    const dayScopedRawFairValueSamples = scopeSamplesToTradingSession(rawFairValueSamples)
    const dayScopedRawLivePriceSamples = scopeSamplesToTradingSession(rawLivePriceSamples)

    const isTrustedFairValuePriceSource = (source) => {
      const normalized = String(source || '')
      return normalized.startsWith('live_reference:excel_fair_value_basket:')
    }
    const isRenderableFairValueLeg = (leg, sample) => {
      if (!leg || typeof leg !== 'object') return false
      if (leg.enabled === false) return false
      const impliedValue = toNumber(leg.implied_fair_value_xb1)
      if (!Number.isFinite(impliedValue)) return false
      const confidence = toNumber(leg.confidence)
      const contribution = toNumber(leg.contribution_points ?? leg.quality_impact)
      const currentPrice = toNumber(sample?.currentPrice)
      const distanceToPrice = Number.isFinite(currentPrice) ? Math.abs(impliedValue - currentPrice) : Infinity
      if (Number.isFinite(contribution) && Math.abs(contribution) < 0.75 && distanceToPrice <= 4) return false
      if (Number.isFinite(confidence) && confidence <= 0.41 && (!Number.isFinite(contribution) || Math.abs(contribution) < 6)) return false
      return true
    }
    const getLegClusterInspection = (sample, legType) => {
      const options = legType === 'shadow' ? FAIR_VALUE_SHADOW_LEG_OPTIONS : FAIR_VALUE_CORE_LEG_OPTIONS
      const legs = legType === 'shadow' ? sample?.shadowLegs : sample?.coreLegs
      const values = options
        .map((option) => toNumber(legs?.[option.key]?.implied_fair_value_xb1))
        .filter((value) => Number.isFinite(value))
      if (values.length < 3) {
        return { suspicious: false, dominantValue: null, dominantShare: 0 }
      }
      const buckets = new Map()
      values.forEach((value) => {
        const rounded = Math.round(value * 10) / 10
        const bucket = buckets.get(rounded) || { value: rounded, count: 0 }
        bucket.count += 1
        buckets.set(rounded, bucket)
      })
      const dominantBucket = [...buckets.values()].sort((left, right) => right.count - left.count)[0]
      const dominantShare = dominantBucket ? dominantBucket.count / values.length : 0
      const referenceCandidates = [
        sample?.currentPrice,
        sample?.coreFairValue,
        sample?.qualityAdjustedPrice,
        sample?.price,
      ].filter((value) => Number.isFinite(value))
      const distanceToReference = referenceCandidates.length && dominantBucket
        ? Math.min(...referenceCandidates.map((reference) => Math.abs(reference - dominantBucket.value)))
        : 0
      return {
        suspicious: dominantShare >= 0.66 && distanceToReference >= 180,
        dominantValue: dominantBucket?.value ?? null,
        dominantShare,
      }
    }
    const currentFairValueSamplesAll = rawFairValueSamples
      .filter((sample) => sample.modelVersion === 'fair_value_ois_v2')
    const stabilizedCurrentFairValueSamplesAll = (() => {
      let lastTrustedLivePrice = null
      const lastGoodCoreLegValues = {}
      const lastGoodShadowLegValues = {}
      return currentFairValueSamplesAll.map((sample) => {
        const trustedPriceSource = isTrustedFairValuePriceSource(sample.currentPriceSource)
        let effectiveCurrentPrice = Number.isFinite(sample.currentPrice) ? sample.currentPrice : null
        if (trustedPriceSource && Number.isFinite(sample.currentPrice)) {
          lastTrustedLivePrice = sample.currentPrice
        } else if (Number.isFinite(lastTrustedLivePrice)) {
          effectiveCurrentPrice = lastTrustedLivePrice
        }
        const sampleWithEffectivePrice = {
          ...sample,
          currentPrice: effectiveCurrentPrice,
        }
        const coreCluster = getLegClusterInspection(sampleWithEffectivePrice, 'core')
        const shadowCluster = getLegClusterInspection(sampleWithEffectivePrice, 'shadow')
        const stabilizedCoreLegs = {}
        FAIR_VALUE_CORE_LEG_OPTIONS.forEach((option) => {
          const leg = sample.coreLegs?.[option.key]
          const rawValue = toNumber(leg?.implied_fair_value_xb1)
          const previousValue = lastGoodCoreLegValues[option.key]
          const shouldCarryForward = (coreCluster.suspicious || !Number.isFinite(rawValue)) && Number.isFinite(previousValue)
          const effectiveValue = shouldCarryForward ? previousValue : rawValue
          if (leg && Number.isFinite(effectiveValue)) {
            stabilizedCoreLegs[option.key] = {
              ...leg,
              implied_fair_value_xb1: effectiveValue,
            }
            lastGoodCoreLegValues[option.key] = effectiveValue
          } else if (leg && Number.isFinite(rawValue)) {
            stabilizedCoreLegs[option.key] = { ...leg }
            lastGoodCoreLegValues[option.key] = rawValue
          } else if (leg) {
            stabilizedCoreLegs[option.key] = { ...leg }
          }
        })
        const stabilizedShadowLegs = {}
        FAIR_VALUE_SHADOW_LEG_OPTIONS.forEach((option) => {
          const leg = sample.shadowLegs?.[option.key]
          const rawValue = toNumber(leg?.implied_fair_value_xb1)
          const previousValue = lastGoodShadowLegValues[option.key]
          const shouldCarryForward = (shadowCluster.suspicious || !Number.isFinite(rawValue)) && Number.isFinite(previousValue)
          const effectiveValue = shouldCarryForward ? previousValue : rawValue
          if (leg && Number.isFinite(effectiveValue)) {
            stabilizedShadowLegs[option.key] = {
              ...leg,
              implied_fair_value_xb1: effectiveValue,
            }
            lastGoodShadowLegValues[option.key] = effectiveValue
          } else if (leg && Number.isFinite(rawValue)) {
            stabilizedShadowLegs[option.key] = { ...leg }
            lastGoodShadowLegValues[option.key] = rawValue
          } else if (leg) {
            stabilizedShadowLegs[option.key] = { ...leg }
          }
        })
        return {
          ...sample,
          currentPrice: effectiveCurrentPrice,
          currentPriceTrusted: trustedPriceSource,
          coreLegs: stabilizedCoreLegs,
          shadowLegs: stabilizedShadowLegs,
          coreLegsSuspicious: coreCluster.suspicious,
          shadowLegsSuspicious: shadowCluster.suspicious,
        }
      })
    })()
    const dayScopedCurrentFairValueSamplesAll = scopeSamplesToTradingSession(stabilizedCurrentFairValueSamplesAll)

    const prices = chartCandlesRaw
      .flatMap((candle) => [candle.open, candle.high, candle.low, candle.close])
      .concat([toNumber(asset.latest_price)])
      .concat(rawValueLevelLines.map((line) => line.price))
      .concat(rawLiquidityPoolBands.flatMap((band) => [band.bandLow, band.bandHigh, band.price]))
      .filter((value) => Number.isFinite(value))

    const rawMinPrice = prices.length ? Math.min(...prices) : 0
    const rawMaxPrice = prices.length ? Math.max(...prices) : 1
    const padding = Math.max((rawMaxPrice - rawMinPrice) * 0.08, Math.abs(rawMaxPrice) * 0.0015 || 1)
    const minPrice = rawMinPrice - padding
    const maxPrice = rawMaxPrice + padding
    const priceSpan = Math.max(maxPrice - minPrice, 0.0001)

    const xFromTs = (ts) => {
      if (!Number.isFinite(ts)) return PLOT_LEFT + plotWidth / 2
      return PLOT_LEFT + ((ts - visibleMinTs) / visibleSpan) * plotWidth
    }
    const yFromPrice = (price) => {
      if (!Number.isFinite(price)) return PLOT_BOTTOM
      return PLOT_BOTTOM - ((price - minPrice) / priceSpan) * plotHeight
    }
    const priceFromY = (y) => {
      const ratio = clamp((PLOT_BOTTOM - y) / plotHeight, 0, 1)
      return minPrice + ratio * priceSpan
    }

    const candleWidth = clamp((plotWidth / Math.max(chartCandlesRaw.length, 18)) * 0.68, 5, 12)
    const chartCandles = chartCandlesRaw.map((candle) => ({
      ...candle,
      x: xFromTs(candle.ts),
      width: candleWidth,
      openY: yFromPrice(candle.open),
      closeY: yFromPrice(candle.close),
      highY: yFromPrice(candle.high),
      lowY: yFromPrice(candle.low),
      direction: candle.close >= candle.open ? 'up' : 'down',
    }))

    const bucketMetricsByCandle = chartCandles.map((candle) => {
      const flowSummary = flowMap.get(String(candle.bucketStartTs || candle.ts))
      return {
        candle,
        flowSummary,
        metrics: computeBucketIndicatorMetrics(flowSummary, candle),
      }
    })

    const activeIndicatorMetrics = selectedIndicatorMetricKeys.value
    const activeIndicatorCohorts = new Set(
      selectedIndicatorCohortKeys.value.length
        ? selectedIndicatorCohortKeys.value
        : INDICATOR_COHORT_OPTIONS.map((option) => option.key),
    )
    const indicatorSeries = []
    if (activeIndicatorMetrics.length) {
      for (const metricKey of activeIndicatorMetrics) {
        const metricMeta = getIndicatorMetricMeta(metricKey)
        for (const cohort of INDICATOR_COHORT_OPTIONS) {
          if (!activeIndicatorCohorts.has(cohort.key)) continue
          const points = bucketMetricsByCandle
            .map((entry) => {
              const value = toNumber(entry.metrics?.[cohort.key]?.[metricKey === 'pressure' ? 'pressureScore' : 'efficiencyScore'])
              if (!Number.isFinite(value)) return null
              return {
                x: entry.candle.x,
                value,
              }
            })
            .filter(Boolean)
          if (!points.length) continue
          indicatorSeries.push({
            key: `${asset.key}-${metricKey}-${cohort.key}`,
            shortLabel: `${cohort.label} ${metricMeta.label}`,
            metricKey,
            cohortKey: cohort.key,
            color: getValueCohortColor(cohort.key),
            dashArray: metricMeta.dashArray,
            opacity: metricMeta.opacity,
            points,
            lastValue: points[points.length - 1]?.value ?? null,
          })
        }
      }
    }

    let regimeChart = {
      width: CHART_WIDTH,
      height: 126,
      plotLeft: PLOT_LEFT,
      plotRight: PLOT_RIGHT,
      plotTop: 12,
      plotBottom: 100,
      yTicks: [],
      series: [],
      hasVisibleLines: false,
    }
    if (selectedRegimeChartMode.value === 'on') {
      const regimePlotLeft = PLOT_LEFT
      const regimePlotRight = PLOT_RIGHT
      const regimePlotTop = 12
      const regimePlotBottom = 100
      const regimeValueToY = (value) => {
        const safe = clamp(toNumber(value) || 0, -100, 100)
        const ratio = (safe + 100) / 200
        return regimePlotBottom - (ratio * (regimePlotBottom - regimePlotTop))
      }
      const regimeSeries = []
      for (const cohort of INDICATOR_COHORT_OPTIONS) {
        if (!activeIndicatorCohorts.has(cohort.key)) continue
        const cohortValue = asset?.cohort_value_map?.cohorts?.[cohort.key]
        const points = bucketMetricsByCandle
          .map((entry) => {
            const regime = classifyBucketFlowRegime(entry.metrics?.[cohort.key], cohortValue, entry.candle)
            if (!regime?.hasSignal) return null
            const score = toNumber(regime?.regimeScore)
            if (!Number.isFinite(score)) return null
            return {
              x: entry.candle.x,
              value: score,
              regimeState: regime.regimeState,
              confidenceScore: regime.confidenceScore,
              rationale: regime.rationale,
            }
          })
          .filter(Boolean)
        if (!points.length) continue
        regimeSeries.push({
          key: `${asset.key}-regime-${cohort.key}`,
          shortLabel: `${cohort.label} regime`,
          cohortKey: cohort.key,
          color: getValueCohortColor(cohort.key),
          points,
          lastValue: points[points.length - 1]?.value ?? null,
          lastState: points[points.length - 1]?.regimeState ?? null,
        })
      }
      regimeChart = {
        width: CHART_WIDTH,
        height: 126,
        plotLeft: regimePlotLeft,
        plotRight: regimePlotRight,
        plotTop: regimePlotTop,
        plotBottom: regimePlotBottom,
        yTicks: [
          { value: -100, label: 'break sell' },
          { value: -50, label: 'abs sell' },
          { value: 0, label: 'neutro' },
          { value: 50, label: 'abs buy' },
          { value: 100, label: 'break buy' },
        ].map((tick) => ({
          ...tick,
          y: regimeValueToY(tick.value),
        })),
        series: regimeSeries.map((series) => ({
          ...series,
          path: series.points
            .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${regimeValueToY(point.value).toFixed(2)}`)
            .join(' '),
        })),
        hasVisibleLines: regimeSeries.length > 0,
      }
    }

    const divergencePlotLeft = PLOT_LEFT
    const divergencePlotRight = PLOT_RIGHT
    const divergencePlotTop = 12
    const divergencePlotBottom = 100
    const divergenceValueToY = (value) => {
      const safe = clamp(toNumber(value) || 0, -100, 100)
      const ratio = (safe + 100) / 200
      return divergencePlotBottom - (ratio * (divergencePlotBottom - divergencePlotTop))
    }
    const bucketDivergenceByCandle = bucketMetricsByCandle.map((entry) => ({
      candle: entry.candle,
      metrics: computeBucketDivergenceMetrics(entry.metrics),
    }))
    const divergenceSeries = [
      {
        key: `${asset.key}-div-alignment`,
        shortLabel: 'alignment',
        color: '#fbbf24',
        dashArray: '0',
        opacity: 0.92,
        points: bucketDivergenceByCandle
          .map((entry) => ({
            x: entry.candle.x,
            value: entry.metrics.alignmentScore,
            state: entry.metrics.state,
          }))
          .filter((point) => Number.isFinite(toNumber(point.value))),
      },
      {
        key: `${asset.key}-div-divergence`,
        shortLabel: 'divergence',
        color: '#f97316',
        dashArray: '7 5',
        opacity: 0.9,
        points: bucketDivergenceByCandle
          .map((entry) => ({
            x: entry.candle.x,
            value: entry.metrics.divergenceScore,
            state: entry.metrics.state,
          }))
          .filter((point) => Number.isFinite(toNumber(point.value))),
      },
    ]
      .filter((series) => series.points.length > 0)
      .map((series) => ({
        ...series,
        lastValue: series.points[series.points.length - 1]?.value ?? null,
        lastState: series.points[series.points.length - 1]?.state ?? null,
        path: series.points
          .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${divergenceValueToY(point.value).toFixed(2)}`)
          .join(' '),
      }))
    const divergenceChart = {
      width: CHART_WIDTH,
      height: 126,
      plotLeft: divergencePlotLeft,
      plotRight: divergencePlotRight,
      plotTop: divergencePlotTop,
      plotBottom: divergencePlotBottom,
      yTicks: [
        { value: -100, label: 'div sell' },
        { value: -50, label: 'sell' },
        { value: 0, label: 'neutro' },
        { value: 50, label: 'buy' },
        { value: 100, label: 'div buy' },
      ].map((tick) => ({
        ...tick,
        y: divergenceValueToY(tick.value),
      })),
      series: divergenceSeries,
      hasVisibleLines: divergenceSeries.length > 0,
    }

    const activeAnnotationTypes = new Set(
      selectedAnnotationTypeKeys.value.length
        ? selectedAnnotationTypeKeys.value
        : ANNOTATION_LEGEND_ITEMS.map((item) => item.type),
    )
    const annotationEvents = bucketMetricsByCandle.flatMap((entry) => (
      buildLiquidityAnnotations(entry, asset, macroNewsTimeline.value).map((annotation, index) => ({
        ...annotation,
        key: `${asset.key}-annot-${entry.candle.bucketStartTs || entry.candle.ts}-${annotation.type}-${index}`,
      }))
    )).filter((annotation) => activeAnnotationTypes.has(annotation.type))
    const annotationMap = new Map()
    for (const annotation of annotationEvents) {
      const key = String(annotation.ts)
      const current = annotationMap.get(key) || []
      current.push(annotation)
      annotationMap.set(key, current)
    }
    const annotationCountsByTs = new Map()
    const annotationMarkers = annotationEvents.map((annotation) => {
      const tsKey = String(annotation.ts)
      const count = annotationCountsByTs.get(tsKey) || 0
      annotationCountsByTs.set(tsKey, count + 1)
      const anchorY = yFromPrice(annotation.anchorPrice)
      const candleForMarker = chartCandles.find((item) => item.ts === annotation.ts) || null
      const candleTopY = candleForMarker ? Math.min(candleForMarker.openY, candleForMarker.closeY, candleForMarker.highY) : anchorY
      const candleBottomY = candleForMarker ? Math.max(candleForMarker.openY, candleForMarker.closeY, candleForMarker.lowY) : anchorY
      const clusterOffsetX = ((count % 3) - 1) * 10
      const clusterRow = Math.floor(count / 3)
      const tone = annotationToneClass(annotation.type)
      let centerY = anchorY
      if (tone === 'sell') {
        centerY = candleTopY - 7 - (clusterRow * 9)
      } else if (tone === 'buy') {
        centerY = candleBottomY + 7 + (clusterRow * 9)
      } else {
        centerY = anchorY + ((clusterRow % 2 === 0 ? 1 : -1) * (6 + clusterRow * 6))
      }
      centerY = clamp(centerY, PLOT_TOP + 8, PLOT_BOTTOM - 8)
      return {
        ...annotation,
        x: annotation.x + clusterOffsetX,
        y: centerY,
        width: 18,
        height: 12,
      }
    })

    let histogramChart = {
      width: CHART_WIDTH,
      height: 126,
      plotLeft: PLOT_LEFT,
      plotRight: PLOT_RIGHT,
      plotTop: 12,
      plotBottom: 100,
      yTicks: [],
      series: [],
      bars: [],
      hasVisibleBars: false,
      zeroY: null,
    }
    if (selectedHistogramMode.value === 'cumulative') {
      const cumulativeSeries = []
      for (const cohort of INDICATOR_COHORT_OPTIONS) {
        if (!activeIndicatorCohorts.has(cohort.key)) continue
        let running = 0
        const points = bucketMetricsByCandle.map((entry) => {
          running += toNumber(entry.metrics?.[cohort.key]?.netQuantity) || 0
          return {
            x: entry.candle.x,
            ts: entry.candle.ts,
            value: running,
          }
        })
        if (!points.length) continue
        cumulativeSeries.push({
          key: `${asset.key}-hist-${cohort.key}`,
          cohortKey: cohort.key,
          shortLabel: `${cohort.label} cum`,
          color: getValueCohortColor(cohort.key),
          points,
          lastValue: points[points.length - 1]?.value ?? null,
        })
      }

      const histogramMaxAbs = Math.max(
        1,
        ...cumulativeSeries.flatMap((series) => series.points.map((point) => Math.abs(point.value))),
      )
      const histogramPlotLeft = PLOT_LEFT
      const histogramPlotRight = PLOT_RIGHT
      const histogramPlotTop = 12
      const histogramPlotBottom = 100
      const histogramValueToY = (value) => {
        const clamped = clamp(toNumber(value) || 0, -histogramMaxAbs, histogramMaxAbs)
        const ratio = (clamped + histogramMaxAbs) / (histogramMaxAbs * 2)
        return histogramPlotBottom - (ratio * (histogramPlotBottom - histogramPlotTop))
      }
      const seriesCount = Math.max(cumulativeSeries.length, 1)
      const zeroY = histogramValueToY(0)
      const barWidth = Math.max(Math.min(candleWidth * 0.42, 8), 3)
      const clusterWidth = barWidth * seriesCount
      const bars = cumulativeSeries.flatMap((series, seriesIndex) => (
        series.points.map((point) => {
          const x = point.x - (clusterWidth / 2) + (seriesIndex * barWidth)
          const y = histogramValueToY(point.value)
          return {
            key: `${series.key}-${point.ts}`,
            x,
            y: Math.min(y, zeroY),
            width: barWidth,
            height: Math.max(Math.abs(zeroY - y), 1.5),
            fill: series.color,
            opacity: 0.34,
          }
        })
      ))
      histogramChart = {
        width: CHART_WIDTH,
        height: 126,
        plotLeft: histogramPlotLeft,
        plotRight: histogramPlotRight,
        plotTop: histogramPlotTop,
        plotBottom: histogramPlotBottom,
        yTicks: [-histogramMaxAbs, -histogramMaxAbs / 2, 0, histogramMaxAbs / 2, histogramMaxAbs].map((value) => ({
          value,
          y: histogramValueToY(value),
          label: formatCompactSignedQuantity(value),
        })),
        series: cumulativeSeries,
        bars,
        hasVisibleBars: cumulativeSeries.length > 0,
        zeroY,
      }
    }

    const visibleParticipantEvents = chartCandles
      .flatMap((candle) => {
        const flowSummary = flowMap.get(String(candle.bucketStartTs || candle.ts))
        const scopedEvents = participantScope.value === 'retail'
          ? (flowSummary?.retailHeatEvents || [])
          : (flowSummary?.foreignHeatEvents || [])
        return scopedEvents
          .filter((event) => matchesBrokerSelection(event, selectedBrokerKeys.value))
          .filter((event) => {
            const delta = toNumber(event.deltaQuantity) || 0
            if (participantSide.value === 'buy') return delta > 0
            if (participantSide.value === 'sell') return delta < 0
            return delta !== 0
          })
          .filter((event) => Number.isFinite(toNumber(event.averagePrice)))
          .map((event, index) => ({
            ...event,
            key: `${asset.key}-${candle.bucketStartTs || candle.ts}-${event.broker_id}-${index}`,
            candle,
          }))
      })

    const maxParticipantDelta = Math.max(
      1,
      ...visibleParticipantEvents.map((event) => Math.abs(toNumber(event.deltaQuantity) || 0)),
    )

    const participantHeatCells = visibleParticipantEvents.map((event) => {
      const absDelta = Math.abs(toNumber(event.deltaQuantity) || 0)
      const intensity = clamp(absDelta / maxParticipantDelta, 0.12, 1)
      const centerX = event.candle.x
      const anchorPrice = resolveHeatAnchorPrice(event, event.candle)
      const centerY = yFromPrice(anchorPrice)
      const candleTopY = Math.min(event.candle.openY, event.candle.closeY, event.candle.highY)
      const candleBottomY = Math.max(event.candle.openY, event.candle.closeY, event.candle.lowY)
      const candleHeight = Math.max(candleBottomY - candleTopY, 0)
      const availableHeight = candleHeight > 0 ? candleHeight : 4
      const desiredHeight = Math.max(availableHeight * (0.42 + intensity * 0.34), 4)
      const cellHeight = candleHeight > 0 ? Math.min(desiredHeight, candleHeight) : desiredHeight
      const unclampedY = centerY - cellHeight / 2
      const minY = candleHeight > 0 ? candleTopY : unclampedY
      const maxY = candleHeight > 0 ? candleBottomY - cellHeight : unclampedY
      const clampedY = clamp(unclampedY, minY, Math.max(minY, maxY))
      return {
        key: event.key,
        x: centerX - Math.max(event.candle.width * 0.6, 5),
        y: clampedY,
        width: Math.max(event.candle.width * 1.2, 10),
        height: cellHeight,
        opacity: 0.12 + intensity * 0.28,
        fill: (toNumber(event.deltaQuantity) || 0) >= 0 ? '#4fc3f7' : '#ff7043',
        anchorPrice,
      }
    })

    const liquidityPoolBands = rawLiquidityPoolBands
      .sort((left, right) => {
        const rightWeight = (right.cascadeProbability || 0) + ((right.stopContracts || 0) / 1000)
        const leftWeight = (left.cascadeProbability || 0) + ((left.stopContracts || 0) / 1000)
        return rightWeight - leftWeight
      })
      .map((band, index) => {
        const yTop = yFromPrice(band.bandHigh)
        const yBottom = yFromPrice(band.bandLow)
        const rawHeight = Math.abs(yBottom - yTop)
        const intensityBoost = clamp(((band.cascadeProbability || 0) / 100) * 8, 0, 8)
        const height = Math.max(rawHeight, 8 + intensityBoost)
        const rawCenterY = (yTop + yBottom) / 2
        const top = clamp(rawCenterY - (height / 2), PLOT_TOP + 2, PLOT_BOTTOM - height - 2)
        const centerY = top + (height / 2)
        const opacity = clamp(0.10 + ((band.cascadeProbability || 0) / 100) * 0.16, 0.10, 0.26)
        return {
          ...band,
          yTop: top,
          yBottom: top + height,
          height,
          centerY,
          opacity,
          strokeOpacity: clamp(opacity + 0.12, 0.22, 0.54),
          lineOpacity: clamp(opacity + 0.14, 0.24, 0.62),
          showTag: index < 6,
        }
      })

    const liquidityPoolLines = liquidityPoolBands
      .slice(0, 6)
      .map((band) => ({
        key: `${band.key}-line`,
        y: band.centerY,
        stroke: band.stroke,
        opacity: clamp((band.lineOpacity || 0.5) + 0.12, 0.45, 0.95),
        label: `${band.shortLabel} ${formatPrice(band.price)}`,
      }))

    const gammaVisibilityPadding = Math.max(priceSpan * 0.18, 220)
    const gammaRegionBands = rawGammaRegions
      .filter((region) => (
        region.bandHigh >= (minPrice - gammaVisibilityPadding)
        && region.bandLow <= (maxPrice + gammaVisibilityPadding)
      ))
      .sort((left, right) => (right.relevanceScore || 0) - (left.relevanceScore || 0))
      .map((region, index) => {
        const yTop = yFromPrice(region.bandHigh)
        const yBottom = yFromPrice(region.bandLow)
        const rawHeight = Math.abs(yBottom - yTop)
        const height = Math.max(rawHeight, region.kind === 'special_region' ? 4 : 7)
        const rawCenterY = (yTop + yBottom) / 2
        const top = clamp(rawCenterY - (height / 2), PLOT_TOP + 2, PLOT_BOTTOM - height - 2)
        return {
          ...region,
          yTop: top,
          height,
          centerY: top + (height / 2),
          opacity: region.kind === 'special_region' ? 0.08 : 0.06,
          lineOpacity: region.kind === 'special_region' ? 0.58 : 0.42,
          showTag: index < 5,
        }
      })

    const gammaCards = gammaRegionBands
      .slice(0, 6)
      .map((region) => ({
        ...region,
      }))

    const fairValueVisibilityPadding = Math.max(priceSpan * 0.15, 180)
    const fairValueLinePoints = fairValueOverlayEnabled.value
      ? dayScopedRawFairValueSamples
        .filter((sample) => sample.ts >= (visibleMinTs - 10 * 60 * 1000) && sample.ts <= (visibleMaxTs + 10 * 60 * 1000))
        .filter((sample) => sample.price >= (minPrice - fairValueVisibilityPadding) && sample.price <= (maxPrice + fairValueVisibilityPadding))
        .map((sample) => ({
          ...sample,
          x: xFromTs(sample.ts),
          y: yFromPrice(sample.price),
        }))
      : []
    const fairValueLine = fairValueLinePoints.length >= 2
      ? {
        path: fairValueLinePoints
          .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
          .join(' '),
        points: fairValueLinePoints,
        stroke: '#fbbf24',
        opacity: 0.72,
        lastY: fairValueLinePoints[fairValueLinePoints.length - 1]?.y ?? null,
      }
      : {
        path: '',
        points: fairValueLinePoints,
        stroke: '#fbbf24',
        opacity: 0.72,
        lastY: fairValueLinePoints[fairValueLinePoints.length - 1]?.y ?? null,
      }

    const sharedTickCount = Math.min(6, Math.max(chartCandles.length, 2))
    const sharedXTicks = Array.from({ length: sharedTickCount }, (_, index) => {
      const ratio = sharedTickCount === 1 ? 0.5 : index / (sharedTickCount - 1)
      const ts = visibleMinTs + visibleSpan * ratio
      return {
        x: xFromTs(ts),
        label: formatAxisTime(new Date(ts).toISOString()),
      }
    })

    let fairValueFeatureChart = {
      available: false,
      width: CHART_WIDTH,
      height: 184,
      plotLeft: PLOT_LEFT,
      plotRight: PLOT_RIGHT,
      plotTop: 12,
      plotBottom: 144,
      yTicks: [],
      xTicks: [],
      pricePath: '',
      fairValuePath: '',
      legacyFairValuePath: '',
      legacyUpperBandPath: '',
      legacyLowerBandPath: '',
      legacyBandAreaPath: '',
      qualityAdjustedPath: '',
      upperBandPath: '',
      lowerBandPath: '',
      bandAreaPath: '',
      qualityRibbonUpperPath: '',
      qualityRibbonLowerPath: '',
      qualityRibbonAreaPath: '',
      gammaMarkers: [],
      distortionBars: [],
      legBars: [],
      legLineSeries: [],
      currentPrice: null,
      currentFairValue: null,
      legacyFairValue: null,
      currentLegacyBandLow: null,
      currentLegacyBandHigh: null,
      currentQualityAdjusted: null,
      currentBandLow: null,
      currentBandHigh: null,
      currentQualityRibbonLow: null,
      currentQualityRibbonHigh: null,
      currentDislocation: null,
      dominantLegLabel: null,
      qualityModel: null,
    }
    if (asset.key === 'win') {
      const fairChartWidth = CHART_WIDTH
      const fairChartHeight = 248
      const fairPlotLeft = PLOT_LEFT
      const fairPlotRight = PLOT_RIGHT
      const fairPlotTop = 12
      const fairPlotBottom = 194
      const fairPlotHeight = fairPlotBottom - fairPlotTop
      const fairPlotWidth = fairPlotRight - fairPlotLeft
      const visibleFairValueSamples = dayScopedRawFairValueSamples
      const visibleLivePriceSamples = dayScopedRawLivePriceSamples
      const visibleCurrentFairValueSamples = dayScopedCurrentFairValueSamplesAll
      const visibleLegacyFairValueSamples = visibleFairValueSamples
        .filter((sample) => (
          Number.isFinite(sample.legacyFairValue)
          || (Number.isFinite(sample.legacyBandLow) && Number.isFinite(sample.legacyBandHigh))
        ))
      const fairChartTsCandidates = [
        ...visibleFairValueSamples.map((sample) => sample.ts),
        ...visibleLivePriceSamples.map((sample) => sample.ts),
        ...visibleCurrentFairValueSamples.map((sample) => sample.ts),
      ].filter((value) => Number.isFinite(value))
      if (!fairChartTsCandidates.length) {
        fairChartTsCandidates.push(...chartCandlesRaw.map((candle) => candle.ts).filter((value) => Number.isFinite(value)))
      }
      const fairVisibleMinTs = fairChartTsCandidates.length ? Math.min(...fairChartTsCandidates) : visibleMinTs
      const fairVisibleMaxTs = fairChartTsCandidates.length ? Math.max(...fairChartTsCandidates) : visibleMaxTs
      const fairVisibleSpan = Math.max(fairVisibleMaxTs - fairVisibleMinTs, 60 * 1000)
      const fairXFromTs = (ts) => {
        if (!Number.isFinite(ts)) return fairPlotLeft + fairPlotWidth / 2
        return fairPlotLeft + ((ts - fairVisibleMinTs) / fairVisibleSpan) * fairPlotWidth
      }
      const fairTickCount = Math.min(6, Math.max(Math.floor(fairVisibleSpan / (30 * 60 * 1000)) + 1, 2))
      const fairXTicks = Array.from({ length: fairTickCount }, (_, index) => {
        const ratio = fairTickCount === 1 ? 0.5 : index / (fairTickCount - 1)
        const ts = fairVisibleMinTs + fairVisibleSpan * ratio
        return {
          x: fairXFromTs(ts),
          label: formatAxisTime(new Date(ts).toISOString()),
        }
      })
      const fairSessionReferencePrices = [
        ...chartCandlesRaw.flatMap((candle) => [candle.open, candle.high, candle.low, candle.close]),
        ...visibleLivePriceSamples.map((sample) => sample.currentPrice),
        ...visibleFairValueSamples.map((sample) => sample.currentPrice),
      ].filter((value) => Number.isFinite(value) && value > 0)
      const fairSessionRefMin = fairSessionReferencePrices.length ? Math.min(...fairSessionReferencePrices) : null
      const fairSessionRefMax = fairSessionReferencePrices.length ? Math.max(...fairSessionReferencePrices) : null
      const fairSessionRefMid = (
        Number.isFinite(fairSessionRefMin) && Number.isFinite(fairSessionRefMax)
          ? (fairSessionRefMin + fairSessionRefMax) / 2
          : null
      )
      const fairSessionAllowedDistance = (
        Number.isFinite(fairSessionRefMin) && Number.isFinite(fairSessionRefMax) && Number.isFinite(fairSessionRefMid)
          ? Math.max((fairSessionRefMax - fairSessionRefMin) * 8, Math.abs(fairSessionRefMid) * 0.18, 4500)
          : Infinity
      )
      const isRenderableFairValuePrice = (value) => {
        if (!Number.isFinite(value) || value <= 0) return false
        if (!Number.isFinite(fairSessionRefMid)) return true
        return Math.abs(value - fairSessionRefMid) <= fairSessionAllowedDistance
      }
      const fvPriceCandidates = []
      if (activeFairValueFeatures.has('price')) {
        fvPriceCandidates.push(...chartCandlesRaw.flatMap((candle) => [candle.open, candle.high, candle.low, candle.close]))
        fvPriceCandidates.push(...visibleLivePriceSamples.map((sample) => sample.currentPrice).filter(isRenderableFairValuePrice))
        fvPriceCandidates.push(...visibleFairValueSamples.map((sample) => sample.currentPrice).filter(isRenderableFairValuePrice))
      }
      if (activeFairValueFeatures.has('fair_value')) {
        fvPriceCandidates.push(...visibleCurrentFairValueSamples.map((sample) => sample.price).filter(isRenderableFairValuePrice))
      }
      if (activeFairValueFeatures.has('legacy_fair_value')) {
        fvPriceCandidates.push(...visibleLegacyFairValueSamples.map((sample) => sample.legacyFairValue).filter(isRenderableFairValuePrice))
      }
      if (activeFairValueFeatures.has('legacy_bands')) {
        fvPriceCandidates.push(
          ...visibleLegacyFairValueSamples.flatMap((sample) => [sample.legacyBandLow, sample.legacyBandHigh]).filter(isRenderableFairValuePrice),
        )
      }
      if (activeFairValueFeatures.has('quality_adjusted')) {
        fvPriceCandidates.push(...visibleCurrentFairValueSamples.map((sample) => sample.qualityAdjustedPrice).filter(isRenderableFairValuePrice))
      }
      if (activeFairValueFeatures.has('bands')) {
        fvPriceCandidates.push(
          ...visibleFairValueSamples.flatMap((sample) => [sample.bandLow, sample.bandHigh]).filter(isRenderableFairValuePrice),
        )
      }
      if (activeFairValueFeatures.has('quality_ribbon')) {
        fvPriceCandidates.push(
          ...visibleCurrentFairValueSamples.flatMap((sample) => [sample.qualityRibbonLow, sample.qualityRibbonHigh]).filter(isRenderableFairValuePrice),
        )
      }
      if (activeFairValueFeatures.has('gamma')) {
        fvPriceCandidates.push(
          ...rawGammaRegions.flatMap((region) => [region.price, region.bandLow, region.bandHigh]).filter(isRenderableFairValuePrice),
        )
      }
      const fairRawMin = fvPriceCandidates.length ? Math.min(...fvPriceCandidates) : minPrice
      const fairRawMax = fvPriceCandidates.length ? Math.max(...fvPriceCandidates) : maxPrice
      const fairPadding = Math.max((fairRawMax - fairRawMin) * 0.12, Math.abs(fairRawMax) * 0.0015 || 1)
      const fairMinPrice = fairRawMin - fairPadding
      const fairMaxPrice = fairRawMax + fairPadding
      const fairPriceSpan = Math.max(fairMaxPrice - fairMinPrice, 0.0001)
      const fairYFromPrice = (price) => {
        if (!Number.isFinite(price)) return fairPlotBottom
        return fairPlotBottom - (((price - fairMinPrice) / fairPriceSpan) * fairPlotHeight)
      }
      const buildLinePath = (points) => (
        points.length >= 2
          ? points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(' ')
          : ''
      )
      const liveFairPriceLinePoints = []
      if (activeFairValueFeatures.has('price')) {
        let lastTrustedLivePrice = null
        let lastSeenPrice = null
        const priceSourceSamples = visibleLivePriceSamples.length
          ? visibleLivePriceSamples
          : visibleCurrentFairValueSamples.length
          ? visibleCurrentFairValueSamples
          : visibleFairValueSamples
        for (const sample of priceSourceSamples) {
          const isTrustedLiveSource = isTrustedFairValuePriceSource(sample?.currentPriceSource)
          if (isTrustedLiveSource && Number.isFinite(sample.currentPrice)) {
            lastTrustedLivePrice = sample.currentPrice
          }
          const effectivePrice = Number.isFinite(sample.currentPrice)
            ? sample.currentPrice
            : (Number.isFinite(lastSeenPrice) ? lastSeenPrice : lastTrustedLivePrice)
          if (!isRenderableFairValuePrice(effectivePrice)) continue
          lastSeenPrice = effectivePrice
          liveFairPriceLinePoints.push({
            x: fairXFromTs(sample.ts),
            y: fairYFromPrice(effectivePrice),
            price: effectivePrice,
            ts: sample.ts,
            source: sample.currentPriceSource,
          })
        }
      }
      const fairPriceLinePoints = liveFairPriceLinePoints.length >= 2
        ? liveFairPriceLinePoints
        : activeFairValueFeatures.has('price')
          ? chartCandlesRaw.map((candle) => ({
            x: fairXFromTs(candle.ts),
            y: fairYFromPrice(candle.close),
            price: candle.close,
            ts: candle.ts,
          }))
          : []
      const fairValueFeaturePoints = activeFairValueFeatures.has('fair_value')
        ? visibleCurrentFairValueSamples
          .filter((sample) => isRenderableFairValuePrice(sample.price))
          .map((sample) => ({
            ...sample,
            x: fairXFromTs(sample.ts),
            y: fairYFromPrice(sample.price),
          }))
        : []
      const legacyFairValueFeaturePoints = activeFairValueFeatures.has('legacy_fair_value')
        ? visibleLegacyFairValueSamples
          .filter((sample) => isRenderableFairValuePrice(sample.legacyFairValue))
          .map((sample) => ({
            ...sample,
            x: fairXFromTs(sample.ts),
            y: fairYFromPrice(sample.legacyFairValue),
          }))
        : []
      const legacyBandPoints = activeFairValueFeatures.has('legacy_bands')
        ? visibleLegacyFairValueSamples
          .filter((sample) => isRenderableFairValuePrice(sample.legacyBandLow) && isRenderableFairValuePrice(sample.legacyBandHigh))
          .map((sample) => ({
            ...sample,
            x: fairXFromTs(sample.ts),
            lowY: fairYFromPrice(sample.legacyBandLow),
            highY: fairYFromPrice(sample.legacyBandHigh),
          }))
        : []
      const qualityAdjustedFeaturePoints = activeFairValueFeatures.has('quality_adjusted')
        ? visibleCurrentFairValueSamples
          .filter((sample) => isRenderableFairValuePrice(sample.qualityAdjustedPrice))
          .map((sample) => ({
            ...sample,
            x: fairXFromTs(sample.ts),
            y: fairYFromPrice(sample.qualityAdjustedPrice),
          }))
        : []
      const bandPoints = activeFairValueFeatures.has('bands')
        ? visibleCurrentFairValueSamples
          .filter((sample) => isRenderableFairValuePrice(sample.bandLow) && isRenderableFairValuePrice(sample.bandHigh))
          .map((sample) => ({
            ...sample,
            x: fairXFromTs(sample.ts),
            lowY: fairYFromPrice(sample.bandLow),
            highY: fairYFromPrice(sample.bandHigh),
          }))
        : []
      const upperBandPath = buildLinePath(bandPoints.map((point) => ({ x: point.x, y: point.highY })))
      const lowerBandPath = buildLinePath(bandPoints.map((point) => ({ x: point.x, y: point.lowY })))
      const bandAreaPath = bandPoints.length >= 2
        ? [
          ...bandPoints.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${point.highY.toFixed(2)}`),
          ...bandPoints.slice().reverse().map((point) => `L ${point.x.toFixed(2)} ${point.lowY.toFixed(2)}`),
          'Z',
        ].join(' ')
        : ''
      const legacyUpperBandPath = buildLinePath(legacyBandPoints.map((point) => ({ x: point.x, y: point.highY })))
      const legacyLowerBandPath = buildLinePath(legacyBandPoints.map((point) => ({ x: point.x, y: point.lowY })))
      const legacyBandAreaPath = legacyBandPoints.length >= 2
        ? [
          ...legacyBandPoints.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${point.highY.toFixed(2)}`),
          ...legacyBandPoints.slice().reverse().map((point) => `L ${point.x.toFixed(2)} ${point.lowY.toFixed(2)}`),
          'Z',
        ].join(' ')
        : ''
      const qualityRibbonPoints = activeFairValueFeatures.has('quality_ribbon')
        ? visibleCurrentFairValueSamples
          .filter((sample) => isRenderableFairValuePrice(sample.qualityRibbonLow) && isRenderableFairValuePrice(sample.qualityRibbonHigh))
          .map((sample) => ({
            ...sample,
            x: fairXFromTs(sample.ts),
            lowY: fairYFromPrice(sample.qualityRibbonLow),
            highY: fairYFromPrice(sample.qualityRibbonHigh),
          }))
        : []
      const qualityRibbonUpperPath = buildLinePath(qualityRibbonPoints.map((point) => ({ x: point.x, y: point.highY })))
      const qualityRibbonLowerPath = buildLinePath(qualityRibbonPoints.map((point) => ({ x: point.x, y: point.lowY })))
      const qualityRibbonAreaPath = qualityRibbonPoints.length >= 2
        ? [
          ...qualityRibbonPoints.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${point.highY.toFixed(2)}`),
          ...qualityRibbonPoints.slice().reverse().map((point) => `L ${point.x.toFixed(2)} ${point.lowY.toFixed(2)}`),
          'Z',
        ].join(' ')
        : ''
      const gammaMarkers = activeFairValueFeatures.has('gamma')
        ? rawGammaRegions
          .filter((region) => region.price >= fairMinPrice && region.price <= fairMaxPrice)
          .slice(0, 8)
          .map((region) => ({
            key: `${asset.key}-fv-gamma-${region.regionKey}`,
            y: fairYFromPrice(region.price),
            color: region.stroke,
            opacity: region.kind === 'special_region' ? 0.48 : 0.34,
            dashArray: region.kind === 'special_region' ? '7 5' : '0',
            label: `${region.shortLabel} ${formatPrice(region.price)}`,
          }))
        : []
      const distortionScale = Math.max(
        1,
        ...visibleFairValueSamples.map((sample) => Math.abs(toNumber(sample.mispricingValue) || 0)),
      )
      const distortionLaneZeroY = fairPlotBottom - 18
      const distortionLaneMaxHeight = 14
      const distortionBars = activeFairValueFeatures.has('distortion')
        ? visibleFairValueSamples
          .filter((sample) => Number.isFinite(sample.mispricingValue))
          .map((sample) => {
            const x = fairXFromTs(sample.ts)
            const magnitude = Math.abs(toNumber(sample.mispricingValue) || 0)
            const ratio = clamp(magnitude / distortionScale, 0, 1)
            const height = Math.max(4, ratio * distortionLaneMaxHeight)
            const isPositive = sample.mispricingValue >= 0
            return {
              key: `${sample.key}-dist`,
              x: x - 2,
              y: isPositive ? distortionLaneZeroY - height : distortionLaneZeroY,
              width: 4,
              height,
              fill: sample.mispricingValue >= 0 ? '#f97316' : '#22c55e',
              opacity: 0.45,
            }
          })
        : []
      const legLaneY = fairPlotBottom - 8
      const legBars = activeFairValueFeatures.has('macro_legs')
        ? visibleFairValueSamples
          .map((sample) => {
            const dominantLeg = Array.isArray(sample.blockTones) ? sample.blockTones[0] : null
            if (!dominantLeg) return null
            const contribution = toNumber(dominantLeg.contribution_points) || 0
            return {
              key: `${sample.key}-leg`,
              x: fairXFromTs(sample.ts) - 3,
              y: legLaneY,
              width: 6,
              height: 6,
              fill: contribution >= 0 ? '#34d399' : '#fb7185',
              opacity: 0.65,
              label: `${dominantLeg.block || 'macro'} ${formatSignedPoints(contribution)}`,
            }
          })
          .filter(Boolean)
        : []
      const legLineSeries = [
        ...FAIR_VALUE_CORE_LEG_OPTIONS
          .filter((option) => activeFairValueCoreLegs.has(option.key))
          .map((option) => {
            const points = visibleCurrentFairValueSamples
              .map((sample) => {
                const leg = sample.coreLegs?.[option.key]
                if (!isRenderableFairValueLeg(leg, sample)) return null
                const value = toNumber(leg?.implied_fair_value_xb1)
                if (!Number.isFinite(value)) return null
                return {
                  x: fairXFromTs(sample.ts),
                  y: fairYFromPrice(value),
                  ts: sample.ts,
                  value,
                }
              })
              .filter(Boolean)
            if (points.length < 2) return null
            return {
              key: `core-${option.key}`,
              label: option.label,
              shortLabel: option.shortLabel,
              description: option.description,
              color: option.color,
              dashArray: '0',
              opacity: 0.42,
              path: buildLinePath(points),
              lastValue: points[points.length - 1]?.value ?? null,
            }
          })
          .filter(Boolean),
        ...FAIR_VALUE_SHADOW_LEG_OPTIONS
          .filter((option) => activeFairValueShadowLegs.has(option.key))
          .map((option) => {
            const points = visibleCurrentFairValueSamples
              .map((sample) => {
                const leg = sample.shadowLegs?.[option.key]
                if (!isRenderableFairValueLeg(leg, sample)) return null
                const value = toNumber(leg?.implied_fair_value_xb1)
                if (!Number.isFinite(value)) return null
                return {
                  x: fairXFromTs(sample.ts),
                  y: fairYFromPrice(value),
                  ts: sample.ts,
                  value,
                }
              })
              .filter(Boolean)
            if (points.length < 2) return null
            return {
              key: `shadow-${option.key}`,
              label: option.label,
              shortLabel: option.shortLabel,
              description: option.description,
              color: option.color,
              dashArray: '5 4',
              opacity: 0.34,
              path: buildLinePath(points),
              lastValue: points[points.length - 1]?.value ?? null,
            }
          })
          .filter(Boolean),
      ]
      const latestCurrentFeatureSample = visibleCurrentFairValueSamples[visibleCurrentFairValueSamples.length - 1]
        || stabilizedCurrentFairValueSamplesAll.slice(-1)[0]
        || null
      const allCurrentQualitySamples = stabilizedCurrentFairValueSamplesAll
      const latestLegacyFeatureSample = visibleLegacyFairValueSamples[visibleLegacyFairValueSamples.length - 1]
        || rawFairValueSamples.filter((sample) => (
          Number.isFinite(sample.legacyFairValue)
          || (Number.isFinite(sample.legacyBandLow) && Number.isFinite(sample.legacyBandHigh))
        )).slice(-1)[0]
        || null
      const latestFeatureSample = latestCurrentFeatureSample || latestLegacyFeatureSample || rawFairValueSamples[rawFairValueSamples.length - 1] || null
      const hasMeaningfulFairValueQuality = (sample) => {
        if (!sample || sample.modelVersion !== 'fair_value_ois_v2') return false
        const rankingItems = [
          ...(Array.isArray(sample.rankingUp) ? sample.rankingUp : []),
          ...(Array.isArray(sample.rankingDown) ? sample.rankingDown : []),
        ]
        if (rankingItems.some((item) => Math.abs(toNumber(item?.contribution_points)) >= 0.5)) return true
        if (Object.values(sample.coreLegs || {}).some((leg) => Math.abs(toNumber(leg?.contribution_points)) >= 0.5)) return true
        if (Object.values(sample.shadowLegs || {}).some((leg) => (
          Math.abs(toNumber(leg?.quality_impact)) >= 0.25
          || Math.abs(toNumber(leg?.band_impact)) >= 0.01
          || Math.abs(toNumber(leg?.convergence_impact)) >= 0.01
        ))) return true
        return false
      }
      const latestQualityPanelSample = [...visibleCurrentFairValueSamples].reverse().find((sample) => hasMeaningfulFairValueQuality(sample))
        || [...allCurrentQualitySamples].reverse().find((sample) => hasMeaningfulFairValueQuality(sample))
        || latestCurrentFeatureSample
        || null
      const stableQualitySamples = getStableQualityWindowSamples(
        allCurrentQualitySamples.filter((sample) => hasMeaningfulFairValueQuality(sample)),
        latestQualityPanelSample?.ts ?? latestCurrentFeatureSample?.ts ?? null,
      )
      const stableCoreLegs = buildStableLegMap(
        stableQualitySamples.length ? stableQualitySamples : [latestQualityPanelSample].filter(Boolean),
        'core',
      )
      const stableShadowLegs = buildStableLegMap(
        stableQualitySamples.length ? stableQualitySamples : [latestQualityPanelSample].filter(Boolean),
        'shadow',
      )
      const qualityPulse = buildQualityPulse(
        stableQualitySamples.length ? stableQualitySamples : [latestQualityPanelSample].filter(Boolean),
      )
      const qualityHistory = buildQualityHistory(
        allCurrentQualitySamples.filter((sample) => hasMeaningfulFairValueQuality(sample)),
        qualityPulse,
      )
      const normalizeQualityRanking = (items, direction, fallbackLegs) => {
        const minContribution = 0.5
        const filtered = (Array.isArray(items) ? items : [])
          .filter((item) => {
            const contribution = toNumber(item?.contribution_points)
            return direction === 'up'
              ? contribution >= minContribution
              : contribution <= -minContribution
          })
          .sort((left, right) => (
            direction === 'up'
              ? toNumber(right?.contribution_points) - toNumber(left?.contribution_points)
              : toNumber(left?.contribution_points) - toNumber(right?.contribution_points)
          ))
          .slice(0, 4)
        if (filtered.length) return filtered
        return Object.values(fallbackLegs || {})
          .filter((leg) => {
            const contribution = toNumber(leg?.contribution_points)
            return direction === 'up'
              ? contribution >= minContribution
              : contribution <= -minContribution
          })
          .sort((left, right) => (
            direction === 'up'
              ? toNumber(right?.contribution_points) - toNumber(left?.contribution_points)
              : toNumber(left?.contribution_points) - toNumber(right?.contribution_points)
          ))
          .slice(0, 4)
      }
      const buildQualityRankingWindow = (windowConfig) => {
        const endTs = latestQualityPanelSample?.ts ?? latestCurrentFeatureSample?.ts ?? null
        if (!Number.isFinite(endTs)) {
          return {
            key: windowConfig.key,
            label: windowConfig.label,
            sampleCount: 0,
            rankingUp: [],
            rankingDown: [],
            topUp: null,
            topDown: null,
          }
        }
        const startTs = Number.isFinite(windowConfig.minutes)
          ? endTs - (windowConfig.minutes * 60 * 1000)
          : -Infinity
        const scopedSamples = allCurrentQualitySamples
          .filter((sample) => Number.isFinite(sample.ts) && sample.ts <= endTs && sample.ts >= startTs)
        const aggregatedLegs = FAIR_VALUE_CORE_LEG_OPTIONS
          .map((option) => {
            const supportingLegs = scopedSamples
              .map((sample) => sample.coreLegs?.[option.key])
              .filter((leg) => Number.isFinite(toNumber(leg?.contribution_points)))
            if (!supportingLegs.length) return null
            const contributionPoints = supportingLegs.reduce((sum, leg) => sum + (toNumber(leg?.contribution_points) || 0), 0) / supportingLegs.length
            const confidence = supportingLegs.reduce((sum, leg) => sum + (toNumber(leg?.confidence) || 0), 0) / supportingLegs.length
            return {
              ...option,
              name: option.key,
              enabled: true,
              confidence,
              contribution_points: contributionPoints,
              direction: contributionPoints > 0 ? 'bullish' : contributionPoints < 0 ? 'bearish' : 'neutral',
            }
          })
          .filter(Boolean)
        const rankingUp = aggregatedLegs
          .filter((leg) => (toNumber(leg?.contribution_points) || 0) >= 0.5)
          .sort((left, right) => (toNumber(right?.contribution_points) || 0) - (toNumber(left?.contribution_points) || 0))
          .slice(0, 4)
        const rankingDown = aggregatedLegs
          .filter((leg) => (toNumber(leg?.contribution_points) || 0) <= -0.5)
          .sort((left, right) => (toNumber(left?.contribution_points) || 0) - (toNumber(right?.contribution_points) || 0))
          .slice(0, 4)
        return {
          key: windowConfig.key,
          label: windowConfig.label,
          sampleCount: scopedSamples.length,
          rankingUp,
          rankingDown,
          topUp: rankingUp[0] || null,
          topDown: rankingDown[0] || null,
        }
      }
      const rankingWindows = FAIR_VALUE_RANKING_WINDOW_OPTIONS.map((windowConfig) => buildQualityRankingWindow(windowConfig))
      const dominantLegLabel = Array.isArray(latestFeatureSample?.blockTones) && latestFeatureSample.blockTones[0]
        ? `${latestFeatureSample.blockTones[0].block || 'macro'} ${formatSignedPoints(latestFeatureSample.blockTones[0].contribution_points)}`
        : null
      const qualityModel = latestQualityPanelSample
        ? {
          implicitSentiment: latestQualityPanelSample.implicitSentiment,
          sentimentConfidence: latestQualityPanelSample.sentimentConfidence,
          confidence: latestQualityPanelSample.confidence,
          riskQualityScore: latestQualityPanelSample.riskQualityScore,
          qualityGauge: latestQualityPanelSample.qualityGauge,
          coreShadowAlignment: latestQualityPanelSample.coreShadowAlignment,
          divergenceScore: latestQualityPanelSample.divergenceScore,
          coherenceScore: latestQualityPanelSample.coherenceScore,
          shadowHaircutPoints: latestQualityPanelSample.shadowHaircutPoints,
          convergenceProbability: latestQualityPanelSample.convergenceProbability,
          regimeBreakProbability: latestQualityPanelSample.regimeBreakProbability,
          qualityRibbonReason: latestQualityPanelSample.qualityRibbonReason,
          curveConditions: latestQualityPanelSample.curveConditions || {},
          rankingUp: normalizeQualityRanking(latestQualityPanelSample.rankingUp, 'up', stableCoreLegs),
          rankingDown: normalizeQualityRanking(latestQualityPanelSample.rankingDown, 'down', stableCoreLegs),
          rankingWindows,
          explanation: latestQualityPanelSample.qualityExplanation || {},
          coreLegs: Object.keys(stableCoreLegs).length ? stableCoreLegs : (latestQualityPanelSample.coreLegs || {}),
          shadowLegs: Object.keys(stableShadowLegs).length ? stableShadowLegs : (latestQualityPanelSample.shadowLegs || {}),
          qualityPulse,
          qualityHistory,
        }
        : null
      fairValueFeatureChart = {
        available: fairPriceLinePoints.length > 0
          || fairValueFeaturePoints.length > 0
          || legacyFairValueFeaturePoints.length > 0
          || qualityAdjustedFeaturePoints.length > 0,
        width: fairChartWidth,
        height: fairChartHeight,
        plotLeft: fairPlotLeft,
        plotRight: fairPlotRight,
        plotTop: fairPlotTop,
        plotBottom: fairPlotBottom,
        yTicks: Array.from({ length: 5 }, (_, index) => {
          const ratio = index / 4
          const value = fairMaxPrice - fairPriceSpan * ratio
          return {
            value,
            y: fairYFromPrice(value),
            label: formatPrice(value),
          }
        }),
        xTicks: fairXTicks,
        pricePath: buildLinePath(fairPriceLinePoints),
        fairValuePath: buildLinePath(fairValueFeaturePoints),
        legacyFairValuePath: buildLinePath(legacyFairValueFeaturePoints),
        legacyUpperBandPath,
        legacyLowerBandPath,
        legacyBandAreaPath,
        qualityAdjustedPath: buildLinePath(qualityAdjustedFeaturePoints),
        upperBandPath,
        lowerBandPath,
        bandAreaPath,
        qualityRibbonUpperPath,
        qualityRibbonLowerPath,
        qualityRibbonAreaPath,
        gammaMarkers,
        distortionBars,
        legBars,
        legLineSeries,
        currentPrice: liveFairPriceLinePoints[liveFairPriceLinePoints.length - 1]?.price
          ?? latestCurrentFeatureSample?.currentPrice
          ?? latestFeatureSample?.currentPrice
          ?? fairPriceLinePoints[fairPriceLinePoints.length - 1]?.price
          ?? toNumber(asset.latest_price),
        currentFairValue: latestCurrentFeatureSample?.price ?? latestFeatureSample?.price ?? null,
        legacyFairValue: latestLegacyFeatureSample?.legacyFairValue ?? null,
        currentLegacyBandLow: latestLegacyFeatureSample?.legacyBandLow ?? null,
        currentLegacyBandHigh: latestLegacyFeatureSample?.legacyBandHigh ?? null,
        currentQualityAdjusted: latestCurrentFeatureSample?.qualityAdjustedPrice ?? null,
        currentBandLow: latestFeatureSample?.bandLow ?? null,
        currentBandHigh: latestFeatureSample?.bandHigh ?? null,
        currentQualityRibbonLow: latestCurrentFeatureSample?.qualityRibbonLow ?? null,
        currentQualityRibbonHigh: latestCurrentFeatureSample?.qualityRibbonHigh ?? null,
        currentDislocation: latestFeatureSample?.mispricingValue ?? null,
        dominantLegLabel,
        qualityModel,
      }
    }

    const liquidityPoolCards = (liquidityPoolWindow?.pools || [])
      .filter((pool) => activePoolOverlays.has(getPoolOverlayKey(pool?.pool_type)))
      .map((pool) => {
        const meta = getPoolOverlayMeta(pool?.pool_type)
        const primaryPool = asset?.liquidity_pools?.primary || {}
        const liquidityPrimary = asset?.liquidity_intelligence?.primary || {}
        const currentPrice = toNumber(asset?.latest_price) || toNumber(primaryPool?.current_price) || toNumber(pool?.price) || 0
        const bandLow = toNumber(pool?.band_low) || toNumber(pool?.price) || 0
        const bandHigh = toNumber(pool?.band_high) || toNumber(pool?.price) || 0
        const bandWidth = Math.max(Math.abs(bandHigh - bandLow), Math.abs(currentPrice) * 0.00018, 0.01)
        const contractsAtRisk = Math.max(toNumber(primaryPool?.contracts_at_risk_total) || toNumber(primaryPool?.market_inventory_contracts) || 1, 1)
        const closureContracts = Math.max(toNumber(pool?.estimated_stop_closure_contracts) || 0, 0)
        const dayElasticityScore = clamp(
          ((Math.abs(toNumber(primaryPool?.delta_efficiency_score) || 0) * 0.32)
          + ((toNumber(primaryPool?.fragility_score) || 0) * 0.36)
          + ((toNumber(liquidityPrimary?.thin_liquidity_score) || 0) * 0.20)
          + ((toNumber(primaryPool?.breadth_score) || 0) * 0.12)),
          0,
          100,
        )
        const regionElasticityScore = clamp(
          ((toNumber(pool?.unwind_intensity_score) || 0) * 0.44)
          + ((toNumber(pool?.cascade_probability) || 0) * 0.34)
          + ((toNumber(pool?.proximity_score) || 0) * 0.22),
          0,
          100,
        )
        const closureShare = closureContracts / contractsAtRisk
        const projectionBase = 1
          + (dayElasticityScore / 100) * 1.15
          + (regionElasticityScore / 100) * 1.05
          + clamp(closureShare * 3.1, 0, 1.35)
        const projectedStopMove = Math.max(
          bandWidth * projectionBase,
          bandWidth + ((toNumber(pool?.estimated_contracts_to_clear_band) || 0) / Math.max(contractsAtRisk, 1)) * bandWidth * 8,
        )
        const triggerSide = String(pool?.trigger_side || 'neutral')
        const projectedDirection = triggerSide === 'buy' ? 'up' : triggerSide === 'sell' ? 'down' : 'flat'
        const projectedTarget1Price = projectedDirection === 'up'
          ? (toNumber(pool?.price) || currentPrice) + projectedStopMove
          : projectedDirection === 'down'
            ? (toNumber(pool?.price) || currentPrice) - projectedStopMove
            : (toNumber(pool?.price) || currentPrice)
        const projectedTarget2Price = projectedDirection === 'up'
          ? (toNumber(pool?.price) || currentPrice) + (projectedStopMove * 1.75)
          : projectedDirection === 'down'
            ? (toNumber(pool?.price) || currentPrice) - (projectedStopMove * 1.75)
            : (toNumber(pool?.price) || currentPrice)
        const projectionRationale = [
          `elasticidade dia ${Math.round(dayElasticityScore)}%`,
          `elasticidade regiao ${Math.round(regionElasticityScore)}%`,
          `share ${Math.round(closureShare * 100)}%`,
          `move proj ${formatProjectedMove(projectedStopMove)}`,
        ].join(' | ')
        return {
          ...pool,
          shortLabel: meta.shortLabel,
          overlayLabel: meta.label,
          overlayDescription: meta.description,
          stroke: meta.stroke,
          dayElasticityScore,
          regionElasticityScore,
          projectedStopMove,
          projectedDirection,
          projectedTarget1Price,
          projectedTarget2Price,
          projectionRationale,
        }
      })
      .sort((left, right) => {
        const rightWeight = (toNumber(right?.estimated_stop_closure_contracts) || 0) + ((toNumber(right?.cascade_probability) || 0) * 100)
        const leftWeight = (toNumber(left?.estimated_stop_closure_contracts) || 0) + ((toNumber(left?.cascade_probability) || 0) * 100)
        return rightWeight - leftWeight
      })
      .slice(0, 6)

    const valueLevelLines = rawValueLevelLines.map((line) => ({
      ...line,
      y: yFromPrice(line.price),
    }))

    const indicatorPlotLeft = PLOT_LEFT
    const indicatorPlotRight = PLOT_RIGHT
    const indicatorPlotTop = 12
    const indicatorPlotBottom = 92
    const indicatorHeight = 110
    const indicatorValueToY = (value) => {
      const safe = clamp(toNumber(value) || 0, -100, 100)
      const ratio = (safe + 100) / 200
      return indicatorPlotBottom - (ratio * (indicatorPlotBottom - indicatorPlotTop))
    }
    const indicatorYTicks = [-100, -50, 0, 50, 100].map((value) => ({
      value,
      y: indicatorValueToY(value),
      label: formatPressureScore(value),
    }))
    const indicatorSeriesWithPath = indicatorSeries.map((series) => ({
      ...series,
      path: series.points
        .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${indicatorValueToY(point.value).toFixed(2)}`)
        .join(' '),
    }))

    const yTicks = Array.from({ length: 5 }, (_, index) => {
      const ratio = index / 4
      const value = maxPrice - priceSpan * ratio
      return {
        value,
        y: yFromPrice(value),
        label: formatPrice(value),
      }
    })

    const xTicks = sharedXTicks

    return {
      ...asset,
      candles,
      flowMap,
      timeframeMinutes,
      chart: {
        width: CHART_WIDTH,
        height: CHART_HEIGHT,
        plotLeft: PLOT_LEFT,
        plotRight: PLOT_RIGHT,
        plotTop: PLOT_TOP,
        plotBottom: PLOT_BOTTOM,
        visibleMinTs,
        visibleMaxTs,
        visibleSpan,
        candles: chartCandles,
        participantHeatCells,
        gammaRegionBands,
        gammaCards,
        fairValueLine,
        liquidityPoolBands,
        liquidityPoolLines,
        liquidityPoolCards,
        annotationMarkers,
        valueLevelLines,
        yTicks,
        xTicks,
        latestPriceY: yFromPrice(toNumber(asset.latest_price)),
        priceFromY,
      },
      indicatorChart: {
        width: CHART_WIDTH,
        height: indicatorHeight,
        plotLeft: indicatorPlotLeft,
        plotRight: indicatorPlotRight,
        plotTop: indicatorPlotTop,
        plotBottom: indicatorPlotBottom,
        yTicks: indicatorYTicks,
        series: indicatorSeriesWithPath,
        hasVisibleLines: indicatorSeriesWithPath.length > 0,
      },
      fairValueFeatureChart,
      regimeChart,
      divergenceChart,
      annotationMap,
      histogramChart,
    }
  }).filter(Boolean)
})

function handlePointerMove(assetKey, event, asset) {
  const drag = dragState.value[assetKey]
  if (drag) {
    const deltaPixels = event.clientX - drag.startClientX
    const deltaMs = (deltaPixels / Math.max(drag.plotWidth, 1)) * drag.spanMs
    const nextEndTs = clamp(drag.startEndTs - deltaMs, drag.minTs + drag.spanMs, drag.maxTs)
    viewportState.value = {
      ...viewportState.value,
      [assetKey]: {
        ...(viewportState.value[assetKey] || {}),
        endTs: nextEndTs,
      },
    }
    return
  }

  const svg = event.currentTarget
  if (!svg || !asset?.chart?.candles?.length) return
  const rect = svg.getBoundingClientRect()
  if (!rect.width || !rect.height) return

  const x = ((event.clientX - rect.left) / rect.width) * asset.chart.width
  const y = ((event.clientY - rect.top) / rect.height) * asset.chart.height
  const boundedX = clamp(x, asset.chart.plotLeft, asset.chart.plotRight)
  const boundedY = clamp(y, asset.chart.plotTop, asset.chart.plotBottom)
  const ratio = (boundedX - asset.chart.plotLeft) / Math.max(asset.chart.plotRight - asset.chart.plotLeft, 1)
  const hoverTs = asset.chart.visibleMinTs + ratio * asset.chart.visibleSpan
  const candle = [...asset.chart.candles].sort((a, b) => Math.abs(a.ts - hoverTs) - Math.abs(b.ts - hoverTs))[0] || null

  hoverState.value = {
    ...hoverState.value,
    [assetKey]: {
      x: candle?.x ?? boundedX,
      y: boundedY,
      candle,
      flowSummary: asset.flowMap?.get(String(candle?.bucketStartTs || candle?.ts)) || null,
      annotations: asset.annotationMap?.get(String(candle?.bucketStartTs || candle?.ts)) || [],
      priceLabel: formatPrice(asset.chart.priceFromY(boundedY)),
      timeLabel: candle?.bucketLabel || formatAxisTime(new Date(candle?.ts || hoverTs).toISOString()),
      timeFullLabel: candle?.bucketLabel || formatTime(new Date(candle?.ts || hoverTs).toISOString()),
    },
  }
}

function goHome() {
  router.push({ name: 'Home' })
}

function goBack() {
  router.back()
}

async function loadHeatmap(forceReload = false) {
  if (loading.value && !forceReload) return
  loading.value = true
  errorMessage.value = ''

  try {
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => controller.abort(), 30000)
    const apiBase = resolveApiBaseUrl()
    const url = new URL('/api/macro/participant-heatmap', apiBase)
    url.searchParams.set('refresh', forceReload ? 'true' : 'false')
    url.searchParams.set('_ts', String(Date.now()))

    const response = await fetch(url.toString(), {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    })
    window.clearTimeout(timeoutId)

    if (!response.ok) {
      throw new Error(`Heatmap request failed with ${response.status}`)
    }

    const json = await response.json()
    if (json && json.success === false) {
      throw new Error(json.error || 'Heatmap backend returned an error.')
    }

    const payload = normalizeHeatmapPayload(json?.data || json || null)
    panelData.value = payload
    if (!payload || !Array.isArray(payload.assets)) {
      errorMessage.value = 'Participant heatmap payload came back empty.'
    } else {
      void loadOptionsHeatmapContext(forceReload, !forceReload)
    }
  } catch (err) {
    errorMessage.value = err?.name === 'AbortError'
      ? 'Heatmap request timed out after 30s.'
      : (err.message || 'Failed to load participant heatmap.')
    void loadOptionsHeatmapContext(forceReload, false)
  } finally {
    loading.value = false
  }
}

function mergeOptionsHeatmapContext(context) {
  if (!context || typeof context !== 'object') return
  if (!panelData.value) {
    panelData.value = normalizeHeatmapPayload(buildOptionsContextFallbackPanel(context))
    return
  }
  const currentPanel = panelData.value || {}
  const mergedAssets = Array.isArray(currentPanel.assets)
    ? currentPanel.assets.map((asset) => {
      const existingHistory = asset?.fair_value_history && typeof asset.fair_value_history === 'object'
        ? asset.fair_value_history
        : {}
      const incomingHistory = context.fair_value_history && typeof context.fair_value_history === 'object'
        ? context.fair_value_history
        : null
      const mergedHistory = (() => {
        if (!incomingHistory) return asset.fair_value_history
        const mergedByTs = new Map()
        const pushSample = (sample) => {
          const ts = String(sample?.captured_at || '')
          if (!ts) return
          mergedByTs.set(ts, JSON.parse(JSON.stringify(sample)))
        }
        ;((existingHistory.samples || [])).forEach(pushSample)
        ;((incomingHistory.samples || [])).forEach(pushSample)
        const mergedSamples = [...mergedByTs.values()]
          .sort((left, right) => String(left?.captured_at || '').localeCompare(String(right?.captured_at || '')))
        return {
          ...JSON.parse(JSON.stringify(existingHistory || {})),
          ...JSON.parse(JSON.stringify(incomingHistory || {})),
          samples: mergedSamples,
          samples_total: Math.max(
            mergedSamples.length,
            toNumber(existingHistory.samples_total) || 0,
            toNumber(incomingHistory.samples_total) || 0,
          ),
          samples_payload_count: mergedSamples.length,
          latest_sample: mergedSamples[mergedSamples.length - 1]
            || incomingHistory.latest_sample
            || existingHistory.latest_sample
            || null,
        }
      })()
      return {
        ...asset,
        gamma_context: context.gamma_context ? JSON.parse(JSON.stringify(context.gamma_context)) : asset.gamma_context,
        fair_value_history: mergedHistory,
        live_capture_history: context.live_capture_history ? JSON.parse(JSON.stringify(context.live_capture_history)) : asset.live_capture_history,
        options_flow_alignment: currentPanel.options_flow_alignment_model
          ? JSON.parse(JSON.stringify(currentPanel.options_flow_alignment_model))
          : asset.options_flow_alignment,
      }
    })
    : currentPanel.assets

  panelData.value = {
    ...currentPanel,
    options_heatmap_context: context,
    assets: mergedAssets,
  }
}

async function loadOptionsHeatmapContext(forceRefresh = false, skipIfFresh = false) {
  if (loadingOptionsContext.value) return
  if (skipIfFresh && !forceRefresh && lastOptionsContextLoadedAt && (Date.now() - lastOptionsContextLoadedAt) < OPTIONS_CONTEXT_REFRESH_MS) {
    return
  }
  loadingOptionsContext.value = true
  try {
    const response = await getLatestOptionsHeatmapContext({ refresh: forceRefresh })
    const payload = response?.data || null
    if (payload) {
      mergeOptionsHeatmapContext(payload)
      lastOptionsContextLoadedAt = Date.now()
    }
  } catch {
    // Keep the last good fair value/gamma state on screen if the lightweight refresh fails.
  } finally {
    loadingOptionsContext.value = false
  }
}

function correlationRequestKey() {
  return [
    correlationLookbackDays.value,
    correlationHorizonMinutes.value,
    [...selectedCorrelationFactorKeys.value].sort().join(','),
  ].join('|')
}

function silentlySyncCorrelationFactors(nextKeys) {
  syncingCorrelationSelection = true
  selectedCorrelationFactorKeys.value = [...nextKeys]
  window.setTimeout(() => {
    syncingCorrelationSelection = false
  }, 0)
}

async function loadIntradayCorrelationHistory(forceRefresh = false, skipIfFresh = true) {
  if (loadingIntradayCorrelation.value) return
  const requestKey = correlationRequestKey()
  if (
    skipIfFresh
    && !forceRefresh
    && lastCorrelationLoadedAt
    && requestKey === lastCorrelationRequestKey
    && (Date.now() - lastCorrelationLoadedAt) < INTRADAY_CORRELATION_REFRESH_MS
  ) {
    return
  }
  loadingIntradayCorrelation.value = true
  try {
    const response = await getLatestIntradayCorrelationHistory({
      underlying_security: 'IBOVE Index',
      lookback_days: correlationLookbackDays.value,
      horizon_minutes: correlationHorizonMinutes.value,
      factors: selectedCorrelationFactorKeys.value.join(','),
      modes: 'pure,neural',
      refresh: forceRefresh,
    })
    const payload = response?.data || null
    intradayCorrelationHistory.value = payload
    const validFactors = new Set(
      Array.isArray(payload?.available_factors)
        ? payload.available_factors
          .map((item) => String(item?.factor || '').trim())
          .filter(Boolean)
        : [],
    )
    let nextFactors = selectedCorrelationFactorKeys.value.filter((key) => validFactors.has(key))
    if (!nextFactors.length) {
      nextFactors = Array.isArray(payload?.default_factors)
        ? payload.default_factors
          .map((item) => String(item || '').trim())
          .filter((key) => key && validFactors.has(key))
        : []
    }
    if (nextFactors.join(',') !== selectedCorrelationFactorKeys.value.join(',')) {
      silentlySyncCorrelationFactors(nextFactors)
    }
    lastCorrelationLoadedAt = Date.now()
    lastCorrelationRequestKey = requestKey
  } catch {
    // Keep the last good correlation panel on screen if the historical model refresh fails.
  } finally {
    loadingIntradayCorrelation.value = false
  }
}

function setCorrelationLookbackDays(days) {
  const nextValue = Number(days) || 1
  if (correlationLookbackDays.value === nextValue) return
  correlationLookbackDays.value = nextValue
  void loadIntradayCorrelationHistory(false, false)
}

function setCorrelationHorizonMinutes(minutes) {
  const nextValue = Number(minutes) || 1
  if (correlationHorizonMinutes.value === nextValue) return
  correlationHorizonMinutes.value = nextValue
  void loadIntradayCorrelationHistory(false, false)
}

function toggleCorrelationMode(modeKey) {
  const key = String(modeKey || '')
  if (!key) return
  const active = new Set(selectedCorrelationModes.value)
  if (active.has(key)) {
    if (active.size === 1) return
    active.delete(key)
  } else {
    active.add(key)
  }
  selectedCorrelationModes.value = [...active]
}

function toggleCorrelationFactor(factorKey) {
  const key = String(factorKey || '')
  if (!key || syncingCorrelationSelection) return
  const active = new Set(selectedCorrelationFactorKeys.value)
  if (active.has(key)) {
    if (active.size === 1) return
    active.delete(key)
  } else {
    active.add(key)
  }
  selectedCorrelationFactorKeys.value = [...active]
  void loadIntradayCorrelationHistory(false, false)
}

function setCapturedFactorDisplayMode(modeKey) {
  const key = String(modeKey || '').trim()
  if (!key || capturedFactorDisplayMode.value === key) return
  capturedFactorDisplayMode.value = key
}

function toggleCapturedFactorSelection(factorKey) {
  const key = String(factorKey || '').trim()
  if (!key) return
  capturedFactorSelectionTouched = true
  const active = new Set(selectedCapturedFactorKeys.value)
  if (active.has(key)) {
    active.delete(key)
  } else {
    active.add(key)
  }
  selectedCapturedFactorKeys.value = [...active]
}

function selectAllCapturedFactors() {
  const panel = capturedFactorHistoryPanel.value
  if (!panel) return
  capturedFactorSelectionTouched = true
  selectedCapturedFactorKeys.value = panel.availableFactors.map((item) => item.factor)
}

function selectCapturedTopMovers() {
  const panel = capturedFactorHistoryPanel.value
  if (!panel) return
  capturedFactorSelectionTouched = true
  selectedCapturedFactorKeys.value = [...panel.defaultFactors]
}

function clearCapturedFactorSelection() {
  capturedFactorSelectionTouched = true
  selectedCapturedFactorKeys.value = []
}

async function hardReloadOptionsBaseNow() {
  if (hardReloadingOptions.value) return
  hardReloadingOptions.value = true
  errorMessage.value = ''

  try {
    await hardRefreshOptionsBase({
      underlying_security: 'IBOVE Index',
    })
    await loadHeatmap(false)
    await loadOptionsHeatmapContext(true)
    await loadIntradayCorrelationHistory(true, false)
  } catch (err) {
    errorMessage.value = err?.message || 'Falha ao fazer hard reload da base de opcoes.'
  } finally {
    hardReloadingOptions.value = false
  }
}

onMounted(() => {
  void loadHeatmap(false)
  void loadOptionsHeatmapContext(false)
  void loadIntradayCorrelationHistory(false, false)
  refreshTimer = window.setInterval(() => {
    void loadHeatmap(false)
  }, 15000)
  optionsContextTimer = window.setInterval(() => {
    void loadOptionsHeatmapContext(false)
  }, OPTIONS_CONTEXT_REFRESH_MS)
  correlationHistoryTimer = window.setInterval(() => {
    void loadIntradayCorrelationHistory(false, true)
  }, INTRADAY_CORRELATION_REFRESH_MS)
})

onBeforeUnmount(() => {
  if (refreshTimer) {
    window.clearInterval(refreshTimer)
    refreshTimer = null
  }
  if (optionsContextTimer) {
    window.clearInterval(optionsContextTimer)
    optionsContextTimer = null
  }
  if (correlationHistoryTimer) {
    window.clearInterval(correlationHistoryTimer)
    correlationHistoryTimer = null
  }
})
</script>


<style scoped src="./MacroHeatmapView.css"></style>

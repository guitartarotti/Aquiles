export function createMacroHeatmapControls(context) {
  const {
    FAIR_VALUE_FEATURE_OPTIONS,
    PLOT_LEFT,
    PLOT_RIGHT,
    RANGE_OPTIONS,
    capturedFactorHistoryPanel,
    capturedFactorSelectionTouched,
    clamp,
    computed,
    dragState,
    expandedFairValueRankingWindowKeys,
    gammaOverlayEnabled,
    hoverState,
    matchesParticipantScope,
    normalizedAssets,
    participantScope,
    poolOverlayEnabled,
    selectedAnnotationTypeKeys,
    selectedBrokerKeys,
    selectedCapturedFactorKeys,
    selectedFairValueCoreLegKeys,
    selectedFairValueFeatureKeys,
    selectedFairValueShadowLegKeys,
    selectedGammaOverlayKeys,
    selectedIndicatorCohortKeys,
    selectedIndicatorMetricKeys,
    selectedPoolOverlayKeys,
    selectedValueCohortKeys,
    selectedValueLevelKeys,
    viewportState,
    watch,
  } = context;

  const availableBrokerOptions = computed(() => {
    const options = new Map();
    for (const asset of normalizedAssets.value) {
      const observedRows = [
        ...(Array.isArray(asset?.participant_catalog) ? asset.participant_catalog : []),
        ...(Array.isArray(asset?.latest_participants) ? asset.latest_participants : []),
        ...(Array.isArray(asset?.heat_points) ? asset.heat_points : []),
      ];
      for (const row of observedRows) {
        if (
          !matchesParticipantScope(
            {
              isRetail: row?.origin_scope === "retail" || row?.broker_segment === "retail" || row?.is_retail_broker,
              isForeign: row?.origin_scope === "foreign" || row?.broker_segment === "foreign" || row?.is_foreign_broker,
            },
            participantScope.value,
          )
        ) {
          continue;
        }
        const key = getBrokerFilterKey(row);
        if (!key || options.has(key)) continue;
        options.set(key, {
          key,
          label: row?.origin_label || row?.broker_name || key,
        });
      }
    }
    return [...options.values()].sort((left, right) => left.label.localeCompare(right.label, "pt-BR"));
  });

  function getBrokerFilterKey(item) {
    if (!item) return null;
    if (item.originRegistryKey) return String(item.originRegistryKey);
    if (item.origin_registry_key) return String(item.origin_registry_key);
    if (item.originLabel) return String(item.originLabel);
    if (item.origin_label) return String(item.origin_label);
    if (item.broker_name) return String(item.broker_name);
    return null;
  }

  function matchesBrokerSelection(item, selectedKeys) {
    if (!selectedKeys?.length) return true;
    const key = getBrokerFilterKey(item);
    return key ? selectedKeys.includes(key) : false;
  }

  function clearBrokerSelection() {
    selectedBrokerKeys.value = [];
  }

  function toggleBrokerSelection(key) {
    if (!key) return;
    selectedBrokerKeys.value = selectedBrokerKeys.value.includes(key)
      ? selectedBrokerKeys.value.filter((item) => item !== key)
      : [...selectedBrokerKeys.value, key];
  }

  function clearValueCohortSelection() {
    selectedValueCohortKeys.value = [];
  }

  function toggleValueCohortSelection(key) {
    if (!key) return;
    selectedValueCohortKeys.value = selectedValueCohortKeys.value.includes(key)
      ? selectedValueCohortKeys.value.filter((item) => item !== key)
      : [...selectedValueCohortKeys.value, key];
  }

  function clearValueLevelSelection() {
    selectedValueLevelKeys.value = [];
  }

  function toggleValueLevelSelection(key) {
    if (!key) return;
    selectedValueLevelKeys.value = selectedValueLevelKeys.value.includes(key)
      ? selectedValueLevelKeys.value.filter((item) => item !== key)
      : [...selectedValueLevelKeys.value, key];
  }

  function clearIndicatorMetricSelection() {
    selectedIndicatorMetricKeys.value = [];
  }

  function toggleIndicatorMetricSelection(key) {
    if (!key) return;
    selectedIndicatorMetricKeys.value = selectedIndicatorMetricKeys.value.includes(key)
      ? selectedIndicatorMetricKeys.value.filter((item) => item !== key)
      : [...selectedIndicatorMetricKeys.value, key];
  }

  function clearIndicatorCohortSelection() {
    selectedIndicatorCohortKeys.value = [];
  }

  function toggleIndicatorCohortSelection(key) {
    if (!key) return;
    selectedIndicatorCohortKeys.value = selectedIndicatorCohortKeys.value.includes(key)
      ? selectedIndicatorCohortKeys.value.filter((item) => item !== key)
      : [...selectedIndicatorCohortKeys.value, key];
  }

  function clearAnnotationTypeSelection() {
    selectedAnnotationTypeKeys.value = [];
  }

  function toggleAnnotationTypeSelection(key) {
    if (!key) return;
    selectedAnnotationTypeKeys.value = selectedAnnotationTypeKeys.value.includes(key)
      ? selectedAnnotationTypeKeys.value.filter((item) => item !== key)
      : [...selectedAnnotationTypeKeys.value, key];
  }

  function clearPoolOverlaySelection() {
    poolOverlayEnabled.value = true;
    selectedPoolOverlayKeys.value = [];
  }

  function disablePoolOverlay() {
    poolOverlayEnabled.value = false;
  }

  function togglePoolOverlaySelection(key) {
    if (!key) return;
    poolOverlayEnabled.value = true;
    selectedPoolOverlayKeys.value = selectedPoolOverlayKeys.value.includes(key)
      ? selectedPoolOverlayKeys.value.filter((item) => item !== key)
      : [...selectedPoolOverlayKeys.value, key];
  }

  function clearGammaOverlaySelection() {
    gammaOverlayEnabled.value = true;
    selectedGammaOverlayKeys.value = [];
  }

  function disableGammaOverlay() {
    gammaOverlayEnabled.value = false;
  }

  function toggleGammaOverlaySelection(key) {
    if (!key) return;
    gammaOverlayEnabled.value = true;
    selectedGammaOverlayKeys.value = selectedGammaOverlayKeys.value.includes(key)
      ? selectedGammaOverlayKeys.value.filter((item) => item !== key)
      : [...selectedGammaOverlayKeys.value, key];
  }

  function clearFairValueFeatureSelection() {
    selectedFairValueFeatureKeys.value = FAIR_VALUE_FEATURE_OPTIONS.map((item) => item.key);
  }

  function toggleFairValueFeatureSelection(key) {
    if (!key) return;
    selectedFairValueFeatureKeys.value = selectedFairValueFeatureKeys.value.includes(key)
      ? selectedFairValueFeatureKeys.value.filter((item) => item !== key)
      : [...selectedFairValueFeatureKeys.value, key];
  }

  function clearFairValueCoreLegSelection() {
    selectedFairValueCoreLegKeys.value = [];
  }

  function toggleFairValueCoreLegSelection(key) {
    if (!key) return;
    selectedFairValueCoreLegKeys.value = selectedFairValueCoreLegKeys.value.includes(key)
      ? selectedFairValueCoreLegKeys.value.filter((item) => item !== key)
      : [...selectedFairValueCoreLegKeys.value, key];
  }

  function clearFairValueShadowLegSelection() {
    selectedFairValueShadowLegKeys.value = [];
  }

  function toggleFairValueShadowLegSelection(key) {
    if (!key) return;
    selectedFairValueShadowLegKeys.value = selectedFairValueShadowLegKeys.value.includes(key)
      ? selectedFairValueShadowLegKeys.value.filter((item) => item !== key)
      : [...selectedFairValueShadowLegKeys.value, key];
  }

  function toggleFairValueRankingWindow(key) {
    if (!key) return;
    expandedFairValueRankingWindowKeys.value = expandedFairValueRankingWindowKeys.value.includes(key)
      ? expandedFairValueRankingWindowKeys.value.filter((item) => item !== key)
      : [...expandedFairValueRankingWindowKeys.value, key];
  }

  function getRangeKey(assetKey) {
    return viewportState.value[assetKey]?.rangeKey || "day";
  }

  function getTimeframeMinutes(assetKey) {
    return viewportState.value[assetKey]?.timeframeMinutes || 1;
  }

  function getRangeOption(rangeKey) {
    return RANGE_OPTIONS.find((item) => item.key === rangeKey) || RANGE_OPTIONS[0];
  }

  function getHover(assetKey) {
    return hoverState.value[assetKey] || null;
  }

  function clampTagX(x, chart) {
    return clamp(x - 29, chart.plotLeft, chart.plotRight - 58);
  }

  function ensureViewport(assetKey, asset) {
    const candles = Array.isArray(asset?.candles_1m) ? asset.candles_1m : [];
    const timestamps = candles
      .map((candle) => new Date(candle.time).getTime())
      .filter(Number.isFinite)
      .sort((a, b) => a - b);
    const maxTs = timestamps.length ? timestamps[timestamps.length - 1] : Date.now();
    const state = viewportState.value[assetKey];
    if (!state) {
      viewportState.value = {
        ...viewportState.value,
        [assetKey]: {
          rangeKey: "day",
          endTs: maxTs,
          timeframeMinutes: 1,
        },
      };
      return;
    }
    const nextState = { ...state };
    if (!Number.isFinite(nextState.endTs) || nextState.endTs > maxTs) {
      nextState.endTs = maxTs;
    }
    if (!Number.isFinite(nextState.timeframeMinutes) || nextState.timeframeMinutes < 1) {
      nextState.timeframeMinutes = 1;
    }
    viewportState.value = {
      ...viewportState.value,
      [assetKey]: nextState,
    };
  }

  watch(
    () => normalizedAssets.value,
    (assets) => {
      for (const asset of assets) {
        ensureViewport(asset.key, asset);
      }
    },
    { immediate: true },
  );

  watch(participantScope, () => {
    selectedBrokerKeys.value = [];
  });

  watch(availableBrokerOptions, (options) => {
    const valid = new Set(options.map((option) => option.key));
    selectedBrokerKeys.value = selectedBrokerKeys.value.filter((key) => valid.has(key));
  });

  watch(
    () => capturedFactorHistoryPanel.value?.availableFactors?.map((item) => item.factor).join("|") || "",
    () => {
      const panel = capturedFactorHistoryPanel.value;
      if (!panel) {
        selectedCapturedFactorKeys.value = [];
        return;
      }
      const valid = new Set(panel.availableFactors.map((item) => item.factor));
      const persisted = selectedCapturedFactorKeys.value.filter((key) => valid.has(key));
      const next = persisted.length ? persisted : capturedFactorSelectionTouched ? [] : panel.defaultFactors;
      if (next.join(",") !== selectedCapturedFactorKeys.value.join(",")) {
        selectedCapturedFactorKeys.value = [...next];
      }
    },
    { immediate: true },
  );

  function setRange(assetKey, rangeKey, asset) {
    ensureViewport(assetKey, asset);
    const candles = Array.isArray(asset?.candles_1m) ? asset.candles_1m : [];
    const timestamps = candles
      .map((candle) => new Date(candle.time).getTime())
      .filter(Number.isFinite)
      .sort((a, b) => a - b);
    const maxTs = timestamps.length ? timestamps[timestamps.length - 1] : Date.now();
    viewportState.value = {
      ...viewportState.value,
      [assetKey]: {
        rangeKey,
        endTs: maxTs,
        timeframeMinutes: viewportState.value[assetKey]?.timeframeMinutes || 1,
      },
    };
  }

  function setTimeframe(assetKey, minutes, asset) {
    ensureViewport(assetKey, asset);
    const candles = Array.isArray(asset?.candles_1m) ? asset.candles_1m : [];
    const timestamps = candles
      .map((candle) => new Date(candle.time).getTime())
      .filter(Number.isFinite)
      .sort((a, b) => a - b);
    const maxTs = timestamps.length ? timestamps[timestamps.length - 1] : Date.now();
    viewportState.value = {
      ...viewportState.value,
      [assetKey]: {
        ...(viewportState.value[assetKey] || {}),
        timeframeMinutes: minutes,
        endTs: Math.min(viewportState.value[assetKey]?.endTs || maxTs, maxTs),
      },
    };
  }

  function shiftWindow(assetKey, direction, asset) {
    ensureViewport(assetKey, asset);
    const range = getRangeOption(getRangeKey(assetKey));
    if (range.minutes == null) return;
    const candles = Array.isArray(asset?.candles_1m) ? asset.candles_1m : [];
    const timestamps = candles
      .map((candle) => new Date(candle.time).getTime())
      .filter(Number.isFinite)
      .sort((a, b) => a - b);
    if (!timestamps.length) return;

    const minTs = timestamps[0];
    const maxTs = timestamps[timestamps.length - 1];
    const spanMs = range.minutes * 60 * 1000;
    const stepMs = Math.max(60 * 1000, Math.round(spanMs * 0.35));
    const currentEnd = viewportState.value[assetKey]?.endTs || maxTs;
    const nextEnd = clamp(currentEnd + direction * stepMs, minTs + spanMs, maxTs);

    viewportState.value = {
      ...viewportState.value,
      [assetKey]: {
        ...(viewportState.value[assetKey] || {}),
        rangeKey: range.key,
        endTs: nextEnd,
        timeframeMinutes: viewportState.value[assetKey]?.timeframeMinutes || 1,
      },
    };
  }

  function resetWindow(assetKey, asset) {
    setRange(assetKey, "day", asset);
  }

  function stopDrag(assetKey) {
    if (!dragState.value[assetKey]) return;
    const next = { ...dragState.value };
    delete next[assetKey];
    dragState.value = next;
  }

  function handlePointerLeave(assetKey) {
    stopDrag(assetKey);
    hoverState.value = {
      ...hoverState.value,
      [assetKey]: null,
    };
  }

  function startDrag(assetKey, event, asset) {
    ensureViewport(assetKey, asset);
    const range = getRangeOption(getRangeKey(assetKey));
    if (range.minutes == null) return;
    const candles = Array.isArray(asset?.candles_1m) ? asset.candles_1m : [];
    const timestamps = candles
      .map((candle) => new Date(candle.time).getTime())
      .filter(Number.isFinite)
      .sort((a, b) => a - b);
    if (!timestamps.length) return;
    const spanMs = range.minutes * 60 * 1000;
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
    };
  }

  return {
    availableBrokerOptions,
    getBrokerFilterKey,
    matchesBrokerSelection,
    clearBrokerSelection,
    toggleBrokerSelection,
    clearValueCohortSelection,
    toggleValueCohortSelection,
    clearValueLevelSelection,
    toggleValueLevelSelection,
    clearIndicatorMetricSelection,
    toggleIndicatorMetricSelection,
    clearIndicatorCohortSelection,
    toggleIndicatorCohortSelection,
    clearAnnotationTypeSelection,
    toggleAnnotationTypeSelection,
    clearPoolOverlaySelection,
    disablePoolOverlay,
    togglePoolOverlaySelection,
    clearGammaOverlaySelection,
    disableGammaOverlay,
    toggleGammaOverlaySelection,
    clearFairValueFeatureSelection,
    toggleFairValueFeatureSelection,
    clearFairValueCoreLegSelection,
    toggleFairValueCoreLegSelection,
    clearFairValueShadowLegSelection,
    toggleFairValueShadowLegSelection,
    toggleFairValueRankingWindow,
    getRangeKey,
    getTimeframeMinutes,
    getRangeOption,
    getHover,
    clampTagX,
    ensureViewport,
    setRange,
    setTimeframe,
    shiftWindow,
    resetWindow,
    stopDrag,
    handlePointerLeave,
    startDrag,
  };
}

import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  focusMacroDriver,
  focusMacroTrend,
  getMacroCollectorStatus,
  getMacroCrossAsset,
  getMacroDrivers,
  getMacroEvents,
  getMacroOverview,
  getMacroThermometer,
  getMacroTrends,
} from "../api/macro";

export function useMacroTrendBoard(props, router) {
  const macroTrends = ref([]);
  const macroTrendsLoading = ref(false);
  const macroTrendError = ref("");
  const macroOverview = ref(null);
  const macroOverviewLoading = ref(false);
  const macroOverviewError = ref("");
  const macroThermometer = ref(null);
  const macroThermometerLoading = ref(false);
  const macroThermometerError = ref("");
  const macroCrossAsset = ref(null);
  const macroCrossAssetLoading = ref(false);
  const macroCrossAssetError = ref("");
  const macroDrivers = ref([]);
  const macroNewsFeed = ref([]);
  const macroRawEvents = ref([]);
  const macroDriversLoading = ref(false);
  const macroDriverError = ref("");
  const macroCollectorStatus = ref(null);
  const macroCollectorError = ref("");
  const selectedDriverId = ref("");
  const focusedDriver = ref(null);
  const focusingDriver = ref(false);
  const refreshingFocusedDriver = ref(false);
  let focusedDriverElasticityTimer = null;
  const selectedThermometerEventId = ref("");
  const hoveredThermometerEventId = ref("");
  const visibleThermometerSeries = ref(["general", "credit", "equity", "fx"]);
  const hoveredCrossAssetDriverId = ref("");
  const visibleCrossAssetSeries = ref([
    "general",
    "credit",
    "equity",
    "commodity",
    "fx",
    "rates",
  ]);
  const selectedFocusedDriverHeadlineEventId = ref("");
  const hoveredFocusedDriverHeadlineEventId = ref("");
  const visibleFocusedDriverSeries = ref([
    "general",
    "credit",
    "equity",
    "commodity",
    "fx",
    "rates",
  ]);
  const selectedTrendId = ref("");
  const focusedTrend = ref(null);
  const focusingTrend = ref(false);
  let macroPollingTimer = null;

  const THERMOMETER_CHART_WIDTH = 760;
  const THERMOMETER_CHART_HEIGHT = 220;
  const THERMOMETER_PLOT_LEFT = 46;
  const THERMOMETER_PLOT_RIGHT = THERMOMETER_CHART_WIDTH - 18;
  const THERMOMETER_PLOT_TOP = 16;
  const THERMOMETER_PLOT_BOTTOM = THERMOMETER_CHART_HEIGHT - 34;
  const thermometerSeriesConfig = [
    { key: "general", label: "general" },
    { key: "credit", label: "credit" },
    { key: "equity", label: "equity" },
    { key: "fx", label: "fx" },
  ];
  const crossAssetSeriesConfig = [
    { key: "general", label: "general" },
    { key: "credit", label: "credit" },
    { key: "equity", label: "equity" },
    { key: "commodity", label: "commodity" },
    { key: "fx", label: "fx" },
    { key: "rates", label: "rates" },
  ];
  const MACRO_CROSS_ASSET_LIMIT = 100;
  let activeDriverFocusRequestId = 0;

  // 进入环境搭建 - 创建 simulation 并跳转

  const showMacroDashboard = computed(() => props.inputMode === "macro");

  const buildDriverVersionKey = (driver) => {
    if (!driver?.driver_id) return "";
    return [
      driver.driver_id,
      driver.last_event_time || "",
      driver.headline_count || 0,
      driver.importance_score || 0,
      driver.market_elasticity?.generated_at || "",
      driver.market_elasticity?.rows
        ?.map(
          (row) =>
            `${row.ticker}:${row.state}:${row.effective_time || ""}:${row.impact?.elasticity_score || 0}`,
        )
        .join("|") || "",
    ].join("::");
  };

  const findLoadedDriver = (driverId) =>
    macroDrivers.value.find((item) => item.driver_id === driverId) || null;

  const canLoadMacroTrends = computed(
    () =>
      showMacroDashboard.value &&
      props.currentPhase >= 2 &&
      !!props.projectData?.project_id &&
      !!props.projectData?.graph_id,
  );

  const openMacroHeatmap = () => {
    router.push({ name: "MacroHeatmap" });
  };

  const collectorStatusTone = computed(() => {
    if (macroCollectorStatus.value?.running) return "success";
    if (macroCollectorError.value) return "error";
    return "warning";
  });

  const collectorStatusLabel = computed(() => {
    if (macroCollectorStatus.value?.running) {
      const completedAt = formatTime(
        macroCollectorStatus.value?.last_completed_at,
      );
      return `collector live • last run ${completedAt}`;
    }
    if (macroCollectorStatus.value) {
      const completedAt = formatTime(
        macroCollectorStatus.value?.last_completed_at,
      );
      return `collector stopped • last run ${completedAt}`;
    }
    if (macroCollectorError.value) return macroCollectorError.value;
    return "collector status unknown";
  });

  const normalizeThermometerPayload = (rawPayload) => {
    if (!rawPayload || typeof rawPayload !== "object") return null;
    if (rawPayload.thermometer) return rawPayload;
    if (rawPayload.data?.thermometer) return rawPayload.data;
    if (rawPayload.overall || rawPayload.timeline) {
      return {
        generated_at: rawPayload.generated_at || null,
        thermometer: rawPayload,
        ai_summary: rawPayload.ai_summary || null,
        entity_views: rawPayload.entity_views || [],
        overview_bridge: rawPayload.overview_bridge || null,
        trading_plan: rawPayload.trading_plan || null,
      };
    }
    return rawPayload;
  };

  const normalizedMacroThermometer = computed(() =>
    normalizeThermometerPayload(macroThermometer.value),
  );
  const thermometerPayload = computed(() => {
    const payload = normalizedMacroThermometer.value || {};
    return payload?.thermometer || payload?.data?.thermometer || {};
  });
  const thermometerTimeline = computed(
    () => thermometerPayload.value?.timeline || [],
  );
  const thermometerEntityViews = computed(() => {
    const payload = normalizedMacroThermometer.value || {};
    return payload?.entity_views || payload?.data?.entity_views || [];
  });
  const promotedMacroEventIds = computed(() => {
    const promotedIds = new Set();
    for (const item of thermometerTimeline.value) {
      if (item?.event_id) promotedIds.add(item.event_id);
    }
    for (const item of macroNewsFeed.value) {
      if (item?.event_id) promotedIds.add(item.event_id);
    }
    return promotedIds;
  });
  const thermometerLatest = computed(() => {
    const thermo = thermometerPayload.value || {};
    return {
      general: thermo.overall || null,
      credit: thermo.credit || null,
      equity: thermo.equity || null,
      fx: thermo.fx || null,
    };
  });
  const macroCrossAssetTimeline = computed(() => {
    const items = [...(macroCrossAsset.value?.timeline || [])];
    items.sort((left, right) => {
      const leftTs = parseThermometerTimestamp(
        left?.last_event_time || left?.time || left?.first_event_time,
      );
      const rightTs = parseThermometerTimestamp(
        right?.last_event_time || right?.time || right?.first_event_time,
      );
      return leftTs - rightTs;
    });
    return items;
  });
  const macroCrossAssetInsights = computed(
    () => macroCrossAsset.value?.insights || [],
  );
  const macroCrossAssetEntityViews = computed(
    () => macroCrossAsset.value?.entity_views || [],
  );
  const macroCrossAssetSummary = computed(
    () => macroCrossAsset.value?.summary || {},
  );
  const macroCrossAssetDrivers = computed(
    () => macroCrossAsset.value?.drivers || [],
  );
  const crossAssetSelectedDriver = computed(() => {
    const mapped = macroCrossAssetDrivers.value.find(
      (item) => item.driver_id === selectedDriverId.value,
    );
    if (mapped) return mapped;
    const latest = macroCrossAssetDrivers.value[0];
    return latest || null;
  });

  const rawEventState = (item) => {
    if (promotedMacroEventIds.value.has(item?.event_id)) return "promoted";
    if (
      item?.market_relevance ||
      Number(item?.impact_score || 0) >= 2 ||
      (item?.linked_contracts || []).length
    )
      return "watch";
    return "captured";
  };

  const loadMacroOverview = async (forceReload = false) => {
    if (!showMacroDashboard.value) return;
    if (macroOverviewLoading.value && !forceReload) return;

    macroOverviewLoading.value = true;
    macroOverviewError.value = "";

    try {
      const res = await getMacroOverview({
        participant_limit: 12,
        news_limit: 6,
      });
      macroOverview.value = res.data || null;
    } catch (err) {
      macroOverviewError.value =
        err.message || "Failed to load market overview.";
    } finally {
      macroOverviewLoading.value = false;
    }
  };

  const formatTime = (dateStr) => {
    if (!dateStr) return "--:--";
    const d = new Date(dateStr);
    if (Number.isNaN(d.getTime())) return "--:--";
    return d.toLocaleTimeString("pt-BR", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  };

  const formatAxisTime = (dateStr) => {
    if (!dateStr) return "--:--";
    const d = new Date(dateStr);
    if (Number.isNaN(d.getTime())) return "--:--";
    return d.toLocaleTimeString("pt-BR", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const formatPrice = (value) => {
    if (value === null || value === undefined || value === "") return "--";
    const num = Number(value);
    if (!Number.isFinite(num)) return "--";
    return num.toFixed(3);
  };

  const formatSignedPercent = (value) => {
    if (value === null || value === undefined || value === "") return "--";
    const num = Number(value);
    if (!Number.isFinite(num)) return "--";
    const sign = num > 0 ? "+" : "";
    return `${sign}${num.toFixed(3)}%`;
  };

  const formatSignedNumber = (value) => {
    if (value === null || value === undefined || value === "") return "--";
    const num = Number(value);
    if (!Number.isFinite(num)) return "--";
    const sign = num > 0 ? "+" : "";
    return `${sign}${num.toFixed(3)}`;
  };

  const formatCompactNumber = (value) => {
    if (value === null || value === undefined || value === "") return "--";
    const num = Number(value);
    if (!Number.isFinite(num)) return "--";
    return new Intl.NumberFormat("en-US", {
      notation: "compact",
      maximumFractionDigits: 1,
    }).format(num);
  };

  const scoreBarStyle = (score) => {
    const normalized = Math.max(-100, Math.min(100, Number(score || 0)));
    return {
      width: `${Math.abs(normalized)}%`,
      marginLeft: normalized < 0 ? `${50 - Math.abs(normalized) / 2}%` : "50%",
    };
  };

  const isThermometerSeriesVisible = (seriesKey) =>
    visibleThermometerSeries.value.includes(seriesKey);

  const toggleThermometerSeries = (seriesKey) => {
    if (isThermometerSeriesVisible(seriesKey)) {
      if (visibleThermometerSeries.value.length === 1) return;
      visibleThermometerSeries.value = visibleThermometerSeries.value.filter(
        (item) => item !== seriesKey,
      );
      return;
    }
    visibleThermometerSeries.value = [
      ...visibleThermometerSeries.value,
      seriesKey,
    ];
  };

  const selectThermometerEvent = (item) => {
    if (!item?.event_id) return;
    selectedThermometerEventId.value = item.event_id;
    hoveredThermometerEventId.value = "";
  };

  const parseThermometerTimestamp = (value) => {
    if (!value) return NaN;
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? NaN : date.getTime();
  };

  const chartYFromScore = (score) => {
    const normalized = Math.max(-100, Math.min(100, Number(score || 0)));
    const ratio = (normalized + 100) / 200;
    return (
      THERMOMETER_PLOT_BOTTOM -
      ratio * (THERMOMETER_PLOT_BOTTOM - THERMOMETER_PLOT_TOP)
    );
  };

  const thermometerChart = computed(() => {
    const items = thermometerTimeline.value;
    const timestamps = items
      .map((item) => parseThermometerTimestamp(item.time))
      .filter((value) => Number.isFinite(value));

    const fallbackTs = Date.now();
    const minTs = timestamps.length ? Math.min(...timestamps) : fallbackTs;
    const maxTs = timestamps.length ? Math.max(...timestamps) : fallbackTs;
    const span = Math.max(maxTs - minTs, 1);
    const plotWidth = THERMOMETER_PLOT_RIGHT - THERMOMETER_PLOT_LEFT;

    const xFromTimestamp = (timestamp) => {
      if (!Number.isFinite(timestamp))
        return THERMOMETER_PLOT_LEFT + plotWidth / 2;
      if (maxTs === minTs) return THERMOMETER_PLOT_LEFT + plotWidth / 2;
      return THERMOMETER_PLOT_LEFT + ((timestamp - minTs) / span) * plotWidth;
    };

    const yTicks = [100, 50, 0, -50, -100].map((value) => ({
      value,
      label: value > 0 ? `+${value}` : `${value}`,
      y: chartYFromScore(value),
    }));

    const tickCount = items.length > 1 ? 5 : 2;
    const xTicks = Array.from({ length: tickCount }, (_, index) => {
      const ratio = tickCount === 1 ? 0.5 : index / (tickCount - 1);
      const tickTs = minTs + span * ratio;
      return {
        x: xFromTimestamp(tickTs),
        label: formatAxisTime(new Date(tickTs).toISOString()),
      };
    });

    const series = Object.fromEntries(
      thermometerSeriesConfig.map((seriesMeta) => {
        const points = items.map((item) => {
          const score = Number(item?.scores?.[seriesMeta.key] || 0);
          const x = xFromTimestamp(parseThermometerTimestamp(item.time));
          const y = chartYFromScore(score);
          return { x, y, score };
        });
        return [seriesMeta.key, points];
      }),
    );

    const eventPins = items.map((item, index) => {
      const ts = parseThermometerTimestamp(item.time);
      const score = Number(item?.scores?.general || 0);
      const riskMarker = item?.risk_marker?.general || "neutral";
      return {
        raw: item,
        index,
        event_id: item.event_id,
        x: xFromTimestamp(ts),
        y: chartYFromScore(score),
        score,
        biasClass:
          riskMarker === "risk-on"
            ? "buy"
            : riskMarker === "risk-off"
              ? "sell"
              : "watch",
      };
    });

    const firstItem = items[0];
    const lastItem = items[items.length - 1];

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
      timeRangeLabel:
        firstItem && lastItem
          ? `${formatAxisTime(firstItem.time)} → ${formatAxisTime(lastItem.time)}`
          : "Awaiting market-moving events",
    };
  });

  const activeThermometerEventId = computed(() => {
    if (hoveredThermometerEventId.value) return hoveredThermometerEventId.value;
    if (selectedThermometerEventId.value)
      return selectedThermometerEventId.value;
    const lastItem =
      thermometerTimeline.value[thermometerTimeline.value.length - 1];
    return lastItem?.event_id || "";
  });

  const activeThermometerEvent = computed(
    () =>
      thermometerTimeline.value.find(
        (item) => item.event_id === activeThermometerEventId.value,
      ) ||
      thermometerTimeline.value[thermometerTimeline.value.length - 1] ||
      null,
  );

  const activeThermometerEventPin = computed(
    () =>
      thermometerChart.value.eventPins.find(
        (pin) => pin.event_id === activeThermometerEventId.value,
      ) || null,
  );

  const buildLinePoints = (seriesKey) => {
    const points = thermometerChart.value.series?.[seriesKey] || [];
    return points
      .map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`)
      .join(" ");
  };

  const linePoints = computed(() => ({
    general: buildLinePoints("general"),
    credit: buildLinePoints("credit"),
    equity: buildLinePoints("equity"),
    fx: buildLinePoints("fx"),
  }));

  const isCrossAssetSeriesVisible = (seriesKey) =>
    visibleCrossAssetSeries.value.includes(seriesKey);

  const toggleCrossAssetSeries = (seriesKey) => {
    if (isCrossAssetSeriesVisible(seriesKey)) {
      if (visibleCrossAssetSeries.value.length === 1) return;
      visibleCrossAssetSeries.value = visibleCrossAssetSeries.value.filter(
        (item) => item !== seriesKey,
      );
      return;
    }
    visibleCrossAssetSeries.value = [
      ...visibleCrossAssetSeries.value,
      seriesKey,
    ];
  };

  const selectCrossAssetDriver = async (driverId) => {
    if (!driverId) return;
    hoveredCrossAssetDriverId.value = "";
    await handleDriverFocus(driverId, { silent: true });
  };

  const crossAssetChart = computed(() => {
    const items = macroCrossAssetTimeline.value;
    const timestamps = items
      .map((item) =>
        parseThermometerTimestamp(
          item.last_event_time || item.time || item.first_event_time,
        ),
      )
      .filter((value) => Number.isFinite(value));

    const fallbackTs = Date.now();
    const minTs = timestamps.length ? Math.min(...timestamps) : fallbackTs;
    const maxTs = timestamps.length ? Math.max(...timestamps) : fallbackTs;
    const span = Math.max(maxTs - minTs, 1);
    const plotWidth = THERMOMETER_PLOT_RIGHT - THERMOMETER_PLOT_LEFT;

    const xFromTimestamp = (timestamp) => {
      if (!Number.isFinite(timestamp))
        return THERMOMETER_PLOT_LEFT + plotWidth / 2;
      if (maxTs === minTs) return THERMOMETER_PLOT_LEFT + plotWidth / 2;
      return THERMOMETER_PLOT_LEFT + ((timestamp - minTs) / span) * plotWidth;
    };

    const yTicks = [100, 50, 0, -50, -100].map((value) => ({
      value,
      label: value > 0 ? `+${value}` : `${value}`,
      y: chartYFromScore(value),
    }));

    const tickCount = items.length > 1 ? 5 : 2;
    const xTicks = Array.from({ length: tickCount }, (_, index) => {
      const ratio = tickCount === 1 ? 0.5 : index / (tickCount - 1);
      const tickTs = minTs + span * ratio;
      return {
        x: xFromTimestamp(tickTs),
        label: formatAxisTime(new Date(tickTs).toISOString()),
      };
    });

    const series = Object.fromEntries(
      crossAssetSeriesConfig.map((seriesMeta) => {
        const points = items.map((item) => {
          const score = Number(item?.scores?.[seriesMeta.key] || 0);
          const x = xFromTimestamp(
            parseThermometerTimestamp(
              item.last_event_time || item.time || item.first_event_time,
            ),
          );
          const y = chartYFromScore(score);
          return { x, y, score };
        });
        return [seriesMeta.key, points];
      }),
    );

    const eventPins = items.map((item) => {
      const ts = parseThermometerTimestamp(
        item.last_event_time || item.time || item.first_event_time,
      );
      const score = Number(item?.scores?.general || 0);
      const bias = score > 6 ? "buy" : score < -6 ? "sell" : "watch";
      return {
        raw: item,
        driver_id: item.driver_id,
        x: xFromTimestamp(ts),
        y: chartYFromScore(score),
        biasClass: bias,
      };
    });

    const firstItem = items[0];
    const lastItem = items[items.length - 1];
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
      timeRangeLabel:
        firstItem && lastItem
          ? `${formatAxisTime(firstItem.time)} -> ${formatAxisTime(lastItem.time)}`
          : "Awaiting cross-asset reactions",
    };
  });

  const activeCrossAssetDriverId = computed(() => {
    if (hoveredCrossAssetDriverId.value) return hoveredCrossAssetDriverId.value;
    if (selectedDriverId.value) return selectedDriverId.value;
    return (
      macroCrossAssetTimeline.value[macroCrossAssetTimeline.value.length - 1]
        ?.driver_id || ""
    );
  });

  const activeCrossAssetEvent = computed(
    () =>
      macroCrossAssetTimeline.value.find(
        (item) => item.driver_id === activeCrossAssetDriverId.value,
      ) ||
      macroCrossAssetTimeline.value[macroCrossAssetTimeline.value.length - 1] ||
      null,
  );

  const activeCrossAssetPin = computed(
    () =>
      crossAssetChart.value.eventPins.find(
        (pin) => pin.driver_id === activeCrossAssetDriverId.value,
      ) || null,
  );

  const buildCrossAssetLinePoints = (seriesKey) => {
    const points = crossAssetChart.value.series?.[seriesKey] || [];
    return points
      .map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`)
      .join(" ");
  };

  const crossAssetLinePoints = computed(() =>
    Object.fromEntries(
      crossAssetSeriesConfig.map((seriesMeta) => [
        seriesMeta.key,
        buildCrossAssetLinePoints(seriesMeta.key),
      ]),
    ),
  );

  const focusedDriverCrossAsset = computed(
    () => focusedDriver.value?.driver_cross_asset?.driver || null,
  );
  const focusedDriverAgentAudit = computed(
    () => focusedDriver.value?.driver?.agent_audit_report || null,
  );
  const focusedDriverElasticityRows = computed(
    () => focusedDriver.value?.driver?.market_elasticity?.rows || [],
  );
  const focusedDriverElasticityLiveWindow = computed(() =>
    Boolean(focusedDriver.value?.driver?.market_elasticity?.live_window_open),
  );
  const focusedDriverThermometerTimeline = computed(
    () => focusedDriverCrossAsset.value?.headline_thermometer?.timeline || [],
  );
  const focusedDriverThermometerLatest = computed(
    () => focusedDriverCrossAsset.value?.headline_thermometer?.latest || {},
  );
  const focusedDriverInteractionGraph = computed(
    () =>
      focusedDriverCrossAsset.value?.asset_interaction_graph || {
        nodes: [],
        edges: [],
      },
  );

  watch(focusedDriverThermometerTimeline, (items) => {
    if (!items.length) {
      selectedFocusedDriverHeadlineEventId.value = "";
      hoveredFocusedDriverHeadlineEventId.value = "";
      return;
    }

    const hasSelected = items.some(
      (item) => item.event_id === selectedFocusedDriverHeadlineEventId.value,
    );
    if (!hasSelected) {
      selectedFocusedDriverHeadlineEventId.value =
        items[items.length - 1]?.event_id || "";
    }
  });

  const isFocusedDriverSeriesVisible = (seriesKey) =>
    visibleFocusedDriverSeries.value.includes(seriesKey);

  const toggleFocusedDriverSeries = (seriesKey) => {
    if (isFocusedDriverSeriesVisible(seriesKey)) {
      if (visibleFocusedDriverSeries.value.length === 1) return;
      visibleFocusedDriverSeries.value =
        visibleFocusedDriverSeries.value.filter((item) => item !== seriesKey);
      return;
    }
    visibleFocusedDriverSeries.value = [
      ...visibleFocusedDriverSeries.value,
      seriesKey,
    ];
  };

  const selectFocusedDriverHeadline = (eventId) => {
    if (!eventId) return;
    selectedFocusedDriverHeadlineEventId.value = eventId;
    hoveredFocusedDriverHeadlineEventId.value = "";
  };

  const focusedDriverThermometerChart = computed(() => {
    const items = focusedDriverThermometerTimeline.value;
    const timestamps = items
      .map((item) => parseThermometerTimestamp(item.time))
      .filter((value) => Number.isFinite(value));

    const fallbackTs = Date.now();
    const minTs = timestamps.length ? Math.min(...timestamps) : fallbackTs;
    const maxTs = timestamps.length ? Math.max(...timestamps) : fallbackTs;
    const span = Math.max(maxTs - minTs, 1);
    const plotWidth = THERMOMETER_PLOT_RIGHT - THERMOMETER_PLOT_LEFT;

    const xFromTimestamp = (timestamp) => {
      if (!Number.isFinite(timestamp))
        return THERMOMETER_PLOT_LEFT + plotWidth / 2;
      if (maxTs === minTs) return THERMOMETER_PLOT_LEFT + plotWidth / 2;
      return THERMOMETER_PLOT_LEFT + ((timestamp - minTs) / span) * plotWidth;
    };

    const yTicks = [100, 50, 0, -50, -100].map((value) => ({
      value,
      label: value > 0 ? `+${value}` : `${value}`,
      y: chartYFromScore(value),
    }));

    const tickCount = items.length > 1 ? Math.min(6, items.length) : 2;
    const xTicks = Array.from({ length: tickCount }, (_, index) => {
      const ratio = tickCount === 1 ? 0.5 : index / (tickCount - 1);
      const tickTs = minTs + span * ratio;
      return {
        x: xFromTimestamp(tickTs),
        label: formatAxisTime(new Date(tickTs).toISOString()),
      };
    });

    const series = Object.fromEntries(
      crossAssetSeriesConfig.map((seriesMeta) => {
        const points = items.map((item) => {
          const score = Number(item?.scores?.[seriesMeta.key] || 0);
          const x = xFromTimestamp(parseThermometerTimestamp(item.time));
          const y = chartYFromScore(score);
          return { x, y, score };
        });
        return [seriesMeta.key, points];
      }),
    );

    const eventPins = items.map((item) => {
      const ts = parseThermometerTimestamp(item.time);
      const score = Number(item?.scores?.general || 0);
      const bias =
        item?.event_bias || (score > 6 ? "buy" : score < -6 ? "sell" : "watch");
      return {
        raw: item,
        event_id: item.event_id,
        x: xFromTimestamp(ts),
        y: chartYFromScore(score),
        biasClass: bias,
      };
    });

    const firstItem = items[0];
    const lastItem = items[items.length - 1];
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
      timeRangeLabel:
        firstItem && lastItem
          ? `${formatAxisTime(firstItem.time)} -> ${formatAxisTime(lastItem.time)}`
          : "Awaiting headline chain",
    };
  });

  const activeFocusedDriverHeadlineEventId = computed(() => {
    if (hoveredFocusedDriverHeadlineEventId.value)
      return hoveredFocusedDriverHeadlineEventId.value;
    if (selectedFocusedDriverHeadlineEventId.value)
      return selectedFocusedDriverHeadlineEventId.value;
    return (
      focusedDriverThermometerTimeline.value[
        focusedDriverThermometerTimeline.value.length - 1
      ]?.event_id || ""
    );
  });

  const activeFocusedDriverHeadlineEvent = computed(
    () =>
      focusedDriverThermometerTimeline.value.find(
        (item) => item.event_id === activeFocusedDriverHeadlineEventId.value,
      ) ||
      focusedDriverThermometerTimeline.value[
        focusedDriverThermometerTimeline.value.length - 1
      ] ||
      null,
  );

  const activeFocusedDriverPin = computed(
    () =>
      focusedDriverThermometerChart.value.eventPins.find(
        (pin) => pin.event_id === activeFocusedDriverHeadlineEventId.value,
      ) || null,
  );

  const buildFocusedDriverLinePoints = (seriesKey) => {
    const points =
      focusedDriverThermometerChart.value.series?.[seriesKey] || [];
    return points
      .map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`)
      .join(" ");
  };

  const focusedDriverLinePoints = computed(() =>
    Object.fromEntries(
      crossAssetSeriesConfig.map((seriesMeta) => [
        seriesMeta.key,
        buildFocusedDriverLinePoints(seriesMeta.key),
      ]),
    ),
  );

  const focusedDriverInteractionLayout = computed(() => {
    const graph = focusedDriverInteractionGraph.value;
    const nodes = graph?.nodes || [];
    const edges = graph?.edges || [];
    const width = 760;
    const height = 360;
    const centerX = width / 2;
    const centerY = height / 2;
    const driverNode = nodes.find((node) => node.type === "driver") || null;
    const bucketNodes = nodes.filter((node) => node.type === "bucket");
    const assetNodes = nodes.filter((node) => node.type === "asset");
    const innerRadius = 110;
    const outerRadius = 195;
    const positioned = [];
    const nodeMap = new Map();

    if (driverNode) {
      const positionedNode = {
        ...driverNode,
        x: centerX,
        y: centerY,
        radius: 28,
        displayLabel: String(driverNode.label || "driver").slice(0, 18),
      };
      positioned.push(positionedNode);
      nodeMap.set(driverNode.id, positionedNode);
    }

    bucketNodes.forEach((node, index) => {
      const angle =
        -Math.PI / 2 + (Math.PI * 2 * index) / Math.max(bucketNodes.length, 1);
      const positionedNode = {
        ...node,
        x: centerX + Math.cos(angle) * innerRadius,
        y: centerY + Math.sin(angle) * innerRadius,
        radius: 18,
        angle,
        displayLabel: String(node.label || node.id).slice(0, 12),
      };
      positioned.push(positionedNode);
      nodeMap.set(node.id, positionedNode);
    });

    const assetBuckets = {};
    assetNodes.forEach((node) => {
      const bucket = node.bucket || "other";
      if (!assetBuckets[bucket]) assetBuckets[bucket] = [];
      assetBuckets[bucket].push(node);
    });

    Object.entries(assetBuckets).forEach(([bucket, bucketAssets]) => {
      const bucketNode = nodeMap.get(`bucket::${bucket}`);
      const baseAngle = bucketNode?.angle ?? 0;
      bucketAssets.forEach((node, index) => {
        const spread = (index - (bucketAssets.length - 1) / 2) * 0.28;
        const angle = baseAngle + spread;
        const positionedNode = {
          ...node,
          x: centerX + Math.cos(angle) * outerRadius,
          y: centerY + Math.sin(angle) * outerRadius,
          radius: 11,
          displayLabel: String(node.label || node.id)
            .replace("BVMF:", "")
            .slice(0, 14),
        };
        positioned.push(positionedNode);
        nodeMap.set(node.id, positionedNode);
      });
    });

    const positionedEdges = edges
      .map((edge) => {
        const source = nodeMap.get(edge.source);
        const target = nodeMap.get(edge.target);
        if (!source || !target) return null;
        return {
          ...edge,
          x1: source.x,
          y1: source.y,
          x2: target.x,
          y2: target.y,
        };
      })
      .filter(Boolean);

    return { width, height, nodes: positioned, edges: positionedEdges };
  });

  watch(thermometerTimeline, (items) => {
    if (!items.length) {
      selectedThermometerEventId.value = "";
      hoveredThermometerEventId.value = "";
      return;
    }

    const hasSelected = items.some(
      (item) => item.event_id === selectedThermometerEventId.value,
    );
    if (!hasSelected) {
      selectedThermometerEventId.value =
        items[items.length - 1]?.event_id || "";
    }
  });

  const loadMacroThermometer = async (forceReload = false) => {
    if (!showMacroDashboard.value) return;
    if (macroThermometerLoading.value && !forceReload) return;

    macroThermometerLoading.value = true;
    macroThermometerError.value = "";

    try {
      const res = await getMacroThermometer({
        refresh: Boolean(forceReload),
      });
      const payload = normalizeThermometerPayload(res?.data || res || null);
      macroThermometer.value = payload;
      const thermo = payload?.thermometer || payload?.data?.thermometer || null;
      if (!thermo) {
        macroThermometerError.value =
          "Macro thermometer payload came back empty.";
      }
    } catch (err) {
      macroThermometerError.value =
        err.message || "Failed to load thermometer.";
    } finally {
      macroThermometerLoading.value = false;
    }
  };

  const loadMacroCrossAsset = async (forceReload = false) => {
    if (!showMacroDashboard.value) return;
    if (macroCrossAssetLoading.value && !forceReload) return;

    macroCrossAssetLoading.value = true;
    macroCrossAssetError.value = "";

    try {
      const res = await getMacroCrossAsset({
        limit: MACRO_CROSS_ASSET_LIMIT,
        refresh: Boolean(forceReload),
      });
      macroCrossAsset.value = res.data || null;
    } catch (err) {
      macroCrossAssetError.value =
        err.message || "Failed to load cross-asset engine.";
    } finally {
      macroCrossAssetLoading.value = false;
    }
  };

  const loadMacroCollectorStatus = async () => {
    if (!showMacroDashboard.value) return;
    try {
      const res = await getMacroCollectorStatus();
      macroCollectorStatus.value = res.data || null;
      macroCollectorError.value = "";
    } catch (err) {
      macroCollectorError.value =
        err.message || "Failed to load collector status.";
    }
  };

  const loadMacroEvents = async () => {
    if (!showMacroDashboard.value) return;
    try {
      const res = await getMacroEvents({
        limit: 100,
      });
      macroRawEvents.value = res.data?.events || [];
    } catch (err) {
      console.warn("Failed to load raw macro events:", err);
    }
  };

  const loadMacroDrivers = async (forceReload = false) => {
    if (!showMacroDashboard.value) return;
    if (macroDriversLoading.value && !forceReload) return;

    macroDriversLoading.value = true;
    macroDriverError.value = "";

    try {
      const res = await getMacroDrivers({
        limit: 100,
        refresh: Boolean(forceReload),
      });
      const payload = res.data || {};
      macroDrivers.value = payload.drivers || [];
      macroNewsFeed.value = payload.news_feed || [];

      if (macroDrivers.value.length > 0) {
        const availableDriverIds = new Set(
          macroDrivers.value.map((item) => item.driver_id),
        );
        const desiredDriver = availableDriverIds.has(selectedDriverId.value)
          ? findLoadedDriver(selectedDriverId.value)
          : macroDrivers.value[0];

        const focusedDriverVersion = buildDriverVersionKey(
          focusedDriver.value?.driver,
        );
        const desiredDriverVersion = buildDriverVersionKey(desiredDriver);
        const shouldFocusDriver = Boolean(
          desiredDriver?.driver_id &&
          (forceReload ||
            !focusedDriver.value?.driver ||
            focusedDriver.value.driver.driver_id !== desiredDriver.driver_id ||
            focusedDriverVersion !== desiredDriverVersion),
        );
        const sameDriverAlreadyLoading = Boolean(
          desiredDriver?.driver_id &&
          (focusingDriver.value || refreshingFocusedDriver.value) &&
          selectedDriverId.value === desiredDriver.driver_id,
        );

        if (shouldFocusDriver && !sameDriverAlreadyLoading) {
          await handleDriverFocus(desiredDriver.driver_id, {
            silent: true,
            preserveCurrent: Boolean(
              focusedDriver.value?.driver &&
              focusedDriver.value.driver.driver_id === desiredDriver.driver_id,
            ),
          });
        }
      } else {
        selectedDriverId.value = "";
        focusedDriver.value = null;
        focusingDriver.value = false;
        refreshingFocusedDriver.value = false;
      }
    } catch (err) {
      macroDriverError.value = err.message || "Failed to load impact drivers.";
    } finally {
      macroDriversLoading.value = false;
    }
  };

  const handleDriverFocus = async (driverId, options = {}) => {
    if (!driverId) return;
    const loadedDriver = findLoadedDriver(driverId);
    const loadedDriverVersion = buildDriverVersionKey(loadedDriver);
    const focusedDriverVersion = buildDriverVersionKey(
      focusedDriver.value?.driver,
    );
    const preserveCurrent = Boolean(
      options.preserveCurrent &&
      focusedDriver.value?.driver &&
      focusedDriver.value.driver.driver_id === driverId,
    );
    const sameDriverAlreadyLoading = Boolean(
      (focusingDriver.value || refreshingFocusedDriver.value) &&
      selectedDriverId.value === driverId,
    );

    if (
      sameDriverAlreadyLoading ||
      (!options.force &&
        focusedDriver.value?.driver?.driver_id === driverId &&
        loadedDriverVersion &&
        loadedDriverVersion === focusedDriverVersion)
    ) {
      selectedDriverId.value = driverId;
      return;
    }

    selectedDriverId.value = driverId;
    if (preserveCurrent) {
      refreshingFocusedDriver.value = true;
    } else {
      focusingDriver.value = true;
      refreshingFocusedDriver.value = false;
    }
    macroDriverError.value = "";
    const requestId = ++activeDriverFocusRequestId;

    try {
      const res = await focusMacroDriver({
        driver_id: driverId,
        refresh: Boolean(options.refresh),
      });
      if (requestId !== activeDriverFocusRequestId) return;
      focusedDriver.value = res.data || null;
    } catch (err) {
      if (requestId !== activeDriverFocusRequestId) return;
      macroDriverError.value = err.message || "Failed to focus driver.";
      if (!options.silent) {
        console.warn("Failed to focus macro driver:", err);
      }
    } finally {
      if (requestId === activeDriverFocusRequestId) {
        focusingDriver.value = false;
        refreshingFocusedDriver.value = false;
      }
    }
  };

  const loadMacroTrends = async (forceReload = false) => {
    if (!canLoadMacroTrends.value) return;
    if (macroTrendsLoading.value && !forceReload) return;

    macroTrendsLoading.value = true;
    macroTrendError.value = "";

    try {
      const res = await getMacroTrends({
        project_id: props.projectData.project_id,
        graph_id: props.projectData.graph_id,
        limit: 8,
      });
      macroTrends.value = res.data?.trends || [];

      if (macroTrends.value.length > 0) {
        const desiredTrendId =
          selectedTrendId.value || macroTrends.value[0].trend_id;
        await handleTrendFocus(desiredTrendId, { silent: true });
        if (!forceReload) {
          console.info("Macro trendboard loaded.");
        }
      } else {
        focusedTrend.value = null;
        selectedTrendId.value = "";
      }
    } catch (err) {
      macroTrendError.value = err.message || "Failed to load macro trends.";
    } finally {
      macroTrendsLoading.value = false;
    }
  };

  const loadMacroDashboard = async (forceReload = false) => {
    const primaryLoads = [
      loadMacroCollectorStatus(),
      loadMacroEvents(),
      loadMacroCrossAsset(forceReload),
      loadMacroOverview(forceReload),
      loadMacroDrivers(forceReload),
    ];
    const secondaryLoads = [
      loadMacroThermometer(forceReload),
      loadMacroTrends(forceReload),
    ];
    await Promise.allSettled(primaryLoads);
    await Promise.allSettled(secondaryLoads);
  };

  const handleTrendFocus = async (trendId, options = {}) => {
    if (
      !trendId ||
      !props.projectData?.project_id ||
      !props.projectData?.graph_id
    )
      return;

    selectedTrendId.value = trendId;
    focusingTrend.value = true;
    macroTrendError.value = "";

    try {
      const res = await focusMacroTrend({
        trend_id: trendId,
        project_id: props.projectData.project_id,
        graph_id: props.projectData.graph_id,
        comment_count: 5,
      });
      focusedTrend.value = res.data;
    } catch (err) {
      macroTrendError.value = err.message || "Failed to focus trend.";
      if (!options.silent) {
        console.warn("Failed to focus macro trend:", err);
      }
    } finally {
      focusingTrend.value = false;
    }
  };

  watch(
    () => [
      showMacroDashboard.value,
      canLoadMacroTrends.value,
      props.projectData?.graph_id,
    ],
    async (
      [dashboardEnabled, trendEnabled, graphId],
      [prevDashboardEnabled, prevTrendEnabled, prevGraphId] = [],
    ) => {
      if (!dashboardEnabled) return;
      if (dashboardEnabled !== prevDashboardEnabled) {
        await Promise.allSettled([
          loadMacroCollectorStatus(),
          loadMacroEvents(),
          loadMacroCrossAsset(false),
          loadMacroOverview(false),
          loadMacroDrivers(false),
        ]);
        void loadMacroThermometer(false);
      }
      if (!trendEnabled || !graphId) return;
      if (trendEnabled !== prevTrendEnabled || graphId !== prevGraphId) {
        await loadMacroTrends(false);
      }
    },
    { immediate: true },
  );

  onMounted(() => {
    macroPollingTimer = window.setInterval(async () => {
      if (!showMacroDashboard.value) return;
      await Promise.allSettled([
        loadMacroCollectorStatus(),
        loadMacroEvents(),
        loadMacroCrossAsset(false),
        loadMacroDrivers(false),
      ]);
      void loadMacroThermometer(false);
    }, 45000);

    focusedDriverElasticityTimer = window.setInterval(async () => {
      if (!showMacroDashboard.value) return;
      if (!focusedDriverElasticityLiveWindow.value) return;
      const driverId = focusedDriver.value?.driver?.driver_id;
      if (!driverId) return;
      await handleDriverFocus(driverId, {
        silent: true,
        preserveCurrent: true,
        force: true,
        refresh: true,
      });
    }, 10000);
  });

  onBeforeUnmount(() => {
    if (macroPollingTimer) {
      window.clearInterval(macroPollingTimer);
      macroPollingTimer = null;
    }
    if (focusedDriverElasticityTimer) {
      window.clearInterval(focusedDriverElasticityTimer);
      focusedDriverElasticityTimer = null;
    }
  });

  return {
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
  };
}

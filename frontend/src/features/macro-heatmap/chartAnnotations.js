export function createMacroChartAnnotations(context) {
  const {
    clamp,
    classifyBucketFlowRegime,
    collectAnnotationPlayers,
    computeBucketConcentrationMetrics,
    computeBucketDivergenceMetrics,
    formatAnnotationShortLabel,
    formatAnnotationTypeLabel,
    formatDivergenceStateLabel,
    formatLevelDefenseStateLabel,
    formatPressureScore,
    resolveBucketValuePosition,
    summarizeAnnotationPlayers,
    toNumber,
  } = context;

  function resolveNewsEventForTs(ts, timeline) {
    if (!Number.isFinite(ts) || !Array.isArray(timeline) || !timeline.length)
      return null;
    const candidates = timeline
      .map((event) => {
        const eventTs = new Date(event.time).getTime();
        return Number.isFinite(eventTs) ? { ...event, eventTs } : null;
      })
      .filter(Boolean)
      .filter(
        (event) => event.eventTs <= ts && ts - event.eventTs <= 90 * 60 * 1000,
      );
    return candidates.length ? candidates[candidates.length - 1] : null;
  }

  function buildLiquidityAnnotations(entry, asset, newsTimeline) {
    const candle = entry?.candle;
    const metrics = entry?.metrics || {};
    const flowSummary = entry?.flowSummary || {};
    if (!candle) return [];

    const netMetric = metrics.net || {};
    const foreignMetric = metrics.foreign || {};
    const retailMetric = metrics.retail || {};
    const divergence = computeBucketDivergenceMetrics(metrics);
    const concentration = computeBucketConcentrationMetrics(entry?.flowSummary);
    const netValue = asset?.cohort_value_map?.cohorts?.net || {};
    const foreignValue = asset?.cohort_value_map?.cohorts?.foreign || {};
    const foreignRegime = classifyBucketFlowRegime(
      foreignMetric,
      foreignValue,
      candle,
    );
    const netRegime = classifyBucketFlowRegime(netMetric, netValue, candle);
    const newsEvent = resolveNewsEventForTs(candle.ts, newsTimeline);
    const newsBias = String(
      newsEvent?.recommended_action || newsEvent?.event_bias || "",
    ).toLowerCase();
    const newsMarker = String(newsEvent?.marker || "").toLowerCase();
    const currentPosition = resolveBucketValuePosition(candle.close, netValue);
    const levelState = String(
      asset?.level_defense_model?.cohorts?.net?.primary_state || "inactive",
    );
    const supportPrice = toNumber(
      asset?.level_defense_model?.cohorts?.net?.support_level?.price,
    );
    const resistancePrice = toNumber(
      asset?.level_defense_model?.cohorts?.net?.resistance_level?.price,
    );
    const foreignBuyers = collectAnnotationPlayers(
      flowSummary,
      "foreign",
      "buy",
    );
    const foreignSellers = collectAnnotationPlayers(
      flowSummary,
      "foreign",
      "sell",
    );
    const retailBuyers = collectAnnotationPlayers(flowSummary, "retail", "buy");
    const retailSellers = collectAnnotationPlayers(
      flowSummary,
      "retail",
      "sell",
    );
    const binSize = Math.max(
      toNumber(asset?.cohort_value_map?.bin_size) || 1,
      1,
    );
    const close = toNumber(candle.close) || 0;
    const high = toNumber(candle.high) || close;
    const low = toNumber(candle.low) || close;
    const priceMove =
      (toNumber(candle.close) || 0) - (toNumber(candle.open) || 0);
    const events = [];

    const pushEvent = (payload) => {
      events.push({
        lane: payload.lane,
        type: payload.type,
        label: payload.label || formatAnnotationTypeLabel(payload.type),
        severity: clamp(toNumber(payload.severity) || 0, 0, 100),
        biasSide: payload.biasSide || "neutral",
        x: candle.x,
        ts: candle.ts,
        timeLabel: candle.bucketLabel,
        shortLabel:
          payload.shortLabel || formatAnnotationShortLabel(payload.type),
        detail: payload.detail || "",
        anchorPrice: Number.isFinite(toNumber(payload.anchorPrice))
          ? toNumber(payload.anchorPrice)
          : close,
        characterization:
          payload.characterization ||
          [
            `div ${formatDivergenceStateLabel(divergence.state)}`,
            `value ${String(currentPosition || "unavailable").replaceAll("_", " ")}`,
            `level ${formatLevelDefenseStateLabel(levelState)}`,
            `net ${formatPressureScore(netMetric.pressureScore)}`,
            `gringa ${formatPressureScore(foreignMetric.pressureScore)}`,
            `varejo ${formatPressureScore(retailMetric.pressureScore)}`,
          ].join(" | "),
        newsTitle: newsEvent?.driver_title || null,
        newsHeadline: newsEvent?.headline || null,
        newsBias: newsBias || null,
        newsMarker: newsMarker || null,
        foreignBrokerSummary: payload.foreignBrokerSummary || "",
        retailBrokerSummary: payload.retailBrokerSummary || "",
        netContracts: toNumber(netMetric.grossQuantity) || 0,
        foreignContracts: toNumber(foreignMetric.grossQuantity) || 0,
        retailContracts: toNumber(retailMetric.grossQuantity) || 0,
        grossContracts: Math.round(toNumber(payload.grossContracts) || 0),
      });
    };

    if (
      divergence.state === "foreign_sell_vs_retail_buy" &&
      (toNumber(retailMetric.pressureScore) || 0) >= 16 &&
      (currentPosition === "above_value" ||
        levelState === "rejection_above_value" ||
        netRegime.regimeState === "divergence_buy" ||
        netRegime.regimeState === "exhaustion_buy")
    ) {
      pushEvent({
        lane: "trap",
        type: "bull_trap",
        severity:
          82 +
          Math.min(
            Math.abs(toNumber(divergence.divergenceScore) || 0) * 0.15,
            14,
          ),
        biasSide: "sell",
        anchorPrice: high,
        detail: "Varejo comprando com estrangeiro na venda em regiao fraca.",
        foreignBrokerSummary: summarizeAnnotationPlayers(
          foreignSellers,
          "sell",
        ),
        retailBrokerSummary: summarizeAnnotationPlayers(retailBuyers, "buy"),
        grossContracts: retailMetric.grossQuantity,
      });
    }

    if (
      divergence.state === "foreign_buy_vs_retail_sell" &&
      (toNumber(retailMetric.pressureScore) || 0) <= -16 &&
      (currentPosition === "below_value" ||
        levelState === "rejection_below_value" ||
        netRegime.regimeState === "divergence_sell" ||
        netRegime.regimeState === "exhaustion_sell")
    ) {
      pushEvent({
        lane: "trap",
        type: "sell_trap",
        severity:
          82 +
          Math.min(
            Math.abs(toNumber(divergence.divergenceScore) || 0) * 0.15,
            14,
          ),
        biasSide: "buy",
        anchorPrice: low,
        detail:
          "Varejo vendendo com estrangeiro na compra em regiao de armadilha.",
        foreignBrokerSummary: summarizeAnnotationPlayers(foreignBuyers, "buy"),
        retailBrokerSummary: summarizeAnnotationPlayers(retailSellers, "sell"),
        grossContracts: retailMetric.grossQuantity,
      });
    }

    if (
      (toNumber(retailMetric.pressureScore) || 0) >= 18 &&
      (toNumber(foreignMetric.pressureScore) || 0) <= -8 &&
      priceMove >= 0
    ) {
      pushEvent({
        lane: "retail",
        type: "retail_buying_top",
        severity:
          68 +
          Math.min(
            Math.abs(toNumber(retailMetric.pressureScore) || 0) * 0.2,
            18,
          ),
        biasSide: "sell",
        anchorPrice: high,
        detail: "Compra de varejo desalinhada com o fluxo estrangeiro.",
        foreignBrokerSummary: summarizeAnnotationPlayers(
          foreignSellers,
          "sell",
        ),
        retailBrokerSummary: summarizeAnnotationPlayers(retailBuyers, "buy"),
        grossContracts: retailMetric.grossQuantity,
      });
    }

    if (
      (toNumber(retailMetric.pressureScore) || 0) <= -18 &&
      (toNumber(foreignMetric.pressureScore) || 0) >= 8 &&
      priceMove <= 0
    ) {
      pushEvent({
        lane: "retail",
        type: "retail_selling_bottom",
        severity:
          68 +
          Math.min(
            Math.abs(toNumber(retailMetric.pressureScore) || 0) * 0.2,
            18,
          ),
        biasSide: "buy",
        anchorPrice: low,
        detail: "Venda de varejo desalinhada com a compra mais institucional.",
        foreignBrokerSummary: summarizeAnnotationPlayers(foreignBuyers, "buy"),
        retailBrokerSummary: summarizeAnnotationPlayers(retailSellers, "sell"),
        grossContracts: retailMetric.grossQuantity,
      });
    }

    if (
      divergence.state === "foreign_buy_vs_retail_sell" &&
      (newsBias === "buy" || newsMarker === "risk-on")
    ) {
      pushEvent({
        lane: "macro",
        type: "foreign_buy_aligned",
        severity:
          70 +
          Math.min(Math.abs(toNumber(divergence.leadScore) || 0) * 0.15, 18),
        biasSide: "buy",
        anchorPrice: close,
        detail: "Compra estrangeira alinhada com o driver macro dominante.",
        foreignBrokerSummary: summarizeAnnotationPlayers(foreignBuyers, "buy"),
        grossContracts: foreignMetric.grossQuantity,
      });
    }

    if (
      divergence.state === "foreign_sell_vs_retail_buy" &&
      (newsBias === "sell" || newsMarker === "risk-off")
    ) {
      pushEvent({
        lane: "macro",
        type: "foreign_sell_aligned",
        severity:
          70 +
          Math.min(Math.abs(toNumber(divergence.leadScore) || 0) * 0.15, 18),
        biasSide: "sell",
        anchorPrice: close,
        detail: "Venda estrangeira alinhada com o pano de fundo macro.",
        foreignBrokerSummary: summarizeAnnotationPlayers(
          foreignSellers,
          "sell",
        ),
        grossContracts: foreignMetric.grossQuantity,
      });
    }

    if (
      concentration.state === "single_name_push" &&
      (toNumber(netMetric.fragilityScore) || 0) >= 42
    ) {
      pushEvent({
        lane: "liq",
        type: "thin_liquidity",
        severity:
          60 + Math.min((toNumber(netMetric.fragilityScore) || 0) * 0.2, 22),
        biasSide: priceMove >= 0 ? "buy" : "sell",
        anchorPrice: close,
        detail:
          "Movimento em liquidez fina, com pouca largura de participacao.",
        grossContracts: netMetric.grossQuantity,
      });
    }

    if (
      foreignRegime.regimeState === "absorption_buy" &&
      (toNumber(foreignMetric.absorptionScore) || 0) >= 55
    ) {
      pushEvent({
        lane: "liq",
        type: "foreign_absorption_buy",
        severity:
          64 +
          Math.min((toNumber(foreignMetric.absorptionScore) || 0) * 0.18, 18),
        biasSide: "buy",
        anchorPrice: close,
        detail: "Estrangeiro absorvendo venda sem ceder range.",
        foreignBrokerSummary: summarizeAnnotationPlayers(foreignBuyers, "buy"),
        grossContracts: foreignMetric.grossQuantity,
      });
    }

    if (
      foreignRegime.regimeState === "absorption_sell" &&
      (toNumber(foreignMetric.absorptionScore) || 0) >= 55
    ) {
      pushEvent({
        lane: "liq",
        type: "foreign_absorption_sell",
        severity:
          64 +
          Math.min((toNumber(foreignMetric.absorptionScore) || 0) * 0.18, 18),
        biasSide: "sell",
        anchorPrice: close,
        detail: "Estrangeiro absorvendo compra sem entregar topo.",
        foreignBrokerSummary: summarizeAnnotationPlayers(
          foreignSellers,
          "sell",
        ),
        grossContracts: foreignMetric.grossQuantity,
      });
    }

    if (
      divergence.state === "foreign_buy_vs_retail_sell" &&
      priceMove > 0 &&
      (toNumber(netMetric.fragilityScore) || 0) >= 38
    ) {
      pushEvent({
        lane: "stop",
        type: "short_squeeze",
        severity:
          70 + Math.min((toNumber(netMetric.fragilityScore) || 0) * 0.18, 16),
        biasSide: "buy",
        anchorPrice: high,
        detail: "Probabilidade de squeeze contra vendidos fracos.",
        foreignBrokerSummary: summarizeAnnotationPlayers(foreignBuyers, "buy"),
        retailBrokerSummary: summarizeAnnotationPlayers(retailSellers, "sell"),
        grossContracts: netMetric.grossQuantity,
      });
    }

    if (
      divergence.state === "foreign_sell_vs_retail_buy" &&
      priceMove < 0 &&
      (toNumber(netMetric.fragilityScore) || 0) >= 38
    ) {
      pushEvent({
        lane: "stop",
        type: "long_flush",
        severity:
          70 + Math.min((toNumber(netMetric.fragilityScore) || 0) * 0.18, 16),
        biasSide: "sell",
        anchorPrice: low,
        detail: "Probabilidade de limpeza de comprados e flush.",
        foreignBrokerSummary: summarizeAnnotationPlayers(
          foreignSellers,
          "sell",
        ),
        retailBrokerSummary: summarizeAnnotationPlayers(retailBuyers, "buy"),
        grossContracts: netMetric.grossQuantity,
      });
    }

    if (
      Number.isFinite(resistancePrice) &&
      Math.abs(high - resistancePrice) <= binSize * 1.1 &&
      (toNumber(netMetric.fragilityScore) || 0) >= 34
    ) {
      pushEvent({
        lane: "stop",
        type: "stop_above",
        severity:
          58 + Math.min((toNumber(netMetric.fragilityScore) || 0) * 0.16, 16),
        biasSide: "sell",
        anchorPrice: high,
        detail: "Regiao de stop acima vulneravel a varredura.",
        grossContracts: netMetric.grossQuantity,
      });
    }

    if (
      Number.isFinite(supportPrice) &&
      Math.abs(low - supportPrice) <= binSize * 1.1 &&
      (toNumber(netMetric.fragilityScore) || 0) >= 34
    ) {
      pushEvent({
        lane: "stop",
        type: "stop_below",
        severity:
          58 + Math.min((toNumber(netMetric.fragilityScore) || 0) * 0.16, 16),
        biasSide: "buy",
        anchorPrice: low,
        detail: "Regiao de stop abaixo vulneravel a varredura.",
        grossContracts: netMetric.grossQuantity,
      });
    }

    if (
      Math.sign(toNumber(foreignMetric.pressureScore) || 0) !== 0 &&
      Math.sign(toNumber(retailMetric.pressureScore) || 0) !== 0 &&
      Math.sign(toNumber(foreignMetric.pressureScore) || 0) !==
        Math.sign(toNumber(retailMetric.pressureScore) || 0)
    ) {
      pushEvent({
        lane: "retail",
        type: "retail_contra_trend",
        severity:
          54 +
          Math.min(Math.abs(toNumber(divergence.leadScore) || 0) * 0.16, 18),
        biasSide:
          (toNumber(foreignMetric.pressureScore) || 0) > 0 ? "buy" : "sell",
        anchorPrice: close,
        detail: "Varejo operando na direcao oposta ao fluxo dominante.",
        foreignBrokerSummary: summarizeAnnotationPlayers(
          (toNumber(foreignMetric.pressureScore) || 0) > 0
            ? foreignBuyers
            : foreignSellers,
          (toNumber(foreignMetric.pressureScore) || 0) > 0 ? "buy" : "sell",
        ),
        retailBrokerSummary: summarizeAnnotationPlayers(
          (toNumber(foreignMetric.pressureScore) || 0) > 0
            ? retailSellers
            : retailBuyers,
          (toNumber(foreignMetric.pressureScore) || 0) > 0 ? "sell" : "buy",
        ),
        grossContracts: retailMetric.grossQuantity,
      });
    }

    return events
      .sort((left, right) => right.severity - left.severity)
      .slice(0, 3);
  }

  return {
    resolveNewsEventForTs,
    buildLiquidityAnnotations,
  };
}

export function createMacroChartFlow(context) {
  const {
    clamp,
    formatAxisTime,
    getHover,
    matchesBrokerSelection,
    participantScope,
    participantSide,
    selectedBrokerKeys,
    toNumber,
  } = context;

  function floorBucketTs(ts, minutes) {
    const bucketMs = Math.max(1, minutes) * 60 * 1000;
    return Math.floor(ts / bucketMs) * bucketMs;
  }

  function toIso(ts) {
    return new Date(ts).toISOString();
  }

  function aggregateCandles(rawCandles, minutes) {
    const timeframe = Math.max(1, minutes);
    if (timeframe === 1) {
      return rawCandles.map((candle) => ({
        ...candle,
        bucketMinutes: 1,
        bucketStartTs: candle.ts,
        bucketEndTs: candle.ts + 60 * 1000,
        bucketLabel: formatAxisTime(candle.time),
      }));
    }

    const buckets = new Map();
    for (const candle of rawCandles) {
      const bucketStartTs = floorBucketTs(candle.ts, timeframe);
      const bucketEndTs = bucketStartTs + timeframe * 60 * 1000;
      const key = String(bucketStartTs);
      const current = buckets.get(key);
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
        });
        continue;
      }
      current.high = Math.max(current.high, candle.high);
      current.low = Math.min(current.low, candle.low);
      current.close = candle.close;
      current.volume =
        (toNumber(current.volume) || 0) + (toNumber(candle.volume) || 0);
    }

    return [...buckets.values()].sort((a, b) => a.ts - b.ts);
  }

  function classifyExecutionHint(side, averagePrice, candle) {
    const avg = toNumber(averagePrice);
    const high = toNumber(candle?.high);
    const low = toNumber(candle?.low);
    if (
      !Number.isFinite(avg) ||
      !Number.isFinite(high) ||
      !Number.isFinite(low) ||
      high <= low
    ) {
      return "sem leitura";
    }
    const position = (avg - low) / Math.max(high - low, 0.0000001);
    if (side === "buy") {
      if (position >= 0.66) return "agressao compra (est.)";
      if (position <= 0.33) return "passivo compra (est.)";
      return "compra mista";
    }
    if (side === "sell") {
      if (position <= 0.33) return "agressao venda (est.)";
      if (position >= 0.66) return "passivo venda (est.)";
      return "venda mista";
    }
    return "sem leitura";
  }

  function resolveHeatAnchorPrice(event, candle) {
    const avg = toNumber(event?.averagePrice);
    const delta = toNumber(event?.deltaQuantity) || 0;
    const high = toNumber(candle?.high);
    const low = toNumber(candle?.low);
    const close = toNumber(candle?.close);
    const open = toNumber(candle?.open);
    const bodyMid =
      Number.isFinite(open) && Number.isFinite(close)
        ? (open + close) / 2
        : null;

    if (Number.isFinite(high) && Number.isFinite(low)) {
      const candleLow = Math.min(low, high);
      const candleHigh = Math.max(low, high);
      const candleMid = Number.isFinite(bodyMid)
        ? bodyMid
        : (candleLow + candleHigh) / 2;
      const candleRange = Math.max(
        candleHigh - candleLow,
        Math.abs(candleMid) * 0.00035,
        1,
      );
      const tolerance = Math.max(
        candleRange * 0.35,
        Math.abs(candleMid) * 0.00045,
      );

      if (
        Number.isFinite(avg) &&
        avg >= candleLow - tolerance &&
        avg <= candleHigh + tolerance
      ) {
        return clamp(avg, candleLow, candleHigh);
      }

      if (delta > 0)
        return clamp(candleMid + candleRange * 0.18, candleLow, candleHigh);
      if (delta < 0)
        return clamp(candleMid - candleRange * 0.18, candleLow, candleHigh);
      return clamp(candleMid, candleLow, candleHigh);
    }

    if (Number.isFinite(close)) return close;
    if (Number.isFinite(bodyMid)) return bodyMid;
    if (Number.isFinite(high) && Number.isFinite(low)) return (high + low) / 2;
    return avg;
  }

  function matchesParticipantScope(item, scope) {
    if (!item) return false;
    if (scope === "retail") return Boolean(item.isRetail);
    return Boolean(item.isForeign);
  }

  function matchesParticipantSide(item, side) {
    if (!item) return false;
    if (side === "both") {
      return (
        (toNumber(item.buyDelta) || 0) > 0 ||
        (toNumber(item.sellDelta) || 0) > 0 ||
        (toNumber(item.deltaQuantity) || 0) !== 0
      );
    }
    if (side === "sell") {
      return (
        (toNumber(item.sellDelta) || 0) > 0 ||
        (toNumber(item.deltaQuantity) || 0) < 0
      );
    }
    return (
      (toNumber(item.buyDelta) || 0) > 0 ||
      (toNumber(item.deltaQuantity) || 0) > 0
    );
  }

  function buildScopedFlowSummary(flowSummary, scope, side, selectedKeys) {
    if (!flowSummary) {
      return {
        playerCount: 0,
        signedConfirmed: false,
        selectedQuantity: 0,
        topPlayers: [],
      };
    }

    const scopedPlayers = (
      Array.isArray(flowSummary.allPlayers) ? flowSummary.allPlayers : []
    )
      .filter((player) => matchesParticipantScope(player, scope))
      .filter((player) => matchesBrokerSelection(player, selectedKeys));

    const scopedTopPlayers = scopedPlayers
      .filter((player) => matchesParticipantSide(player, side))
      .sort((left, right) => {
        const leftValue =
          side === "sell"
            ? toNumber(left.sellDelta) || Math.abs(toNumber(left.netDelta) || 0)
            : toNumber(left.buyDelta) || toNumber(left.netDelta) || 0;
        const rightValue =
          side === "sell"
            ? toNumber(right.sellDelta) ||
              Math.abs(toNumber(right.netDelta) || 0)
            : toNumber(right.buyDelta) || toNumber(right.netDelta) || 0;
        return rightValue - leftValue;
      })
      .slice(0, 5);

    const topBuyers = scopedPlayers
      .filter((player) => (toNumber(player.buyDelta) || 0) > 0)
      .sort(
        (left, right) =>
          (toNumber(right.buyDelta) || toNumber(right.netDelta) || 0) -
          (toNumber(left.buyDelta) || toNumber(left.netDelta) || 0),
      )
      .slice(0, 5);

    const topSellers = scopedPlayers
      .filter((player) => (toNumber(player.sellDelta) || 0) > 0)
      .sort(
        (left, right) =>
          (toNumber(right.sellDelta) ||
            Math.abs(toNumber(right.netDelta) || 0)) -
          (toNumber(left.sellDelta) || Math.abs(toNumber(left.netDelta) || 0)),
      )
      .slice(0, 5);

    const buyQuantity =
      scope === "retail"
        ? flowSummary.retailBuyQuantity || 0
        : flowSummary.foreignBuyQuantity || 0;
    const sellQuantity =
      scope === "retail"
        ? flowSummary.retailSellQuantity || 0
        : flowSummary.foreignSellQuantity || 0;
    const selectedQuantity =
      side === "both"
        ? buyQuantity + sellQuantity
        : side === "sell"
          ? sellQuantity
          : buyQuantity;

    return {
      playerCount: scopedPlayers.length,
      signedConfirmed: Boolean(flowSummary.signedConfirmed),
      selectedQuantity,
      buyQuantity,
      sellQuantity,
      topPlayers: scopedTopPlayers,
      topBuyers,
      topSellers,
    };
  }

  function getDisplayFlowSummary(assetKey) {
    const raw = getHover(assetKey)?.flowSummary;
    return buildScopedFlowSummary(
      raw,
      participantScope.value,
      participantSide.value,
      selectedBrokerKeys.value,
    );
  }

  function buildFlowMap(asset, aggregatedCandles, timeframeMinutes) {
    const heatPoints = (
      Array.isArray(asset?.heat_points) ? asset.heat_points : []
    )
      .map((point) => ({
        ...point,
        capturedTs: new Date(point.captured_at).getTime(),
        sampleCandleTs: point.sample_candle_time
          ? new Date(point.sample_candle_time).getTime()
          : null,
        quantityValue: toNumber(point.quantity_float) ?? 0,
        averagePriceValue: toNumber(point.average_price_float),
      }))
      .filter((point) => Number.isFinite(point.capturedTs))
      .sort((a, b) => a.capturedTs - b.capturedTs);
    const bucketMap = new Map();
    const brokerBaseline = new Map();

    for (const point of heatPoints) {
      const brokerKey = `${point.broker_id}::${point.broker_name || "Player"}`;
      const previous = brokerBaseline.get(brokerKey);
      brokerBaseline.set(brokerKey, {
        quantityValue: point.quantityValue,
        averagePriceValue: point.averagePriceValue,
      });
      if (!previous) continue;

      const deltaQuantity = point.quantityValue - previous.quantityValue;
      if (!Number.isFinite(deltaQuantity) || Math.abs(deltaQuantity) < 0.000001)
        continue;

      const referenceTs = Number.isFinite(point.sampleCandleTs)
        ? point.sampleCandleTs
        : point.capturedTs;
      const bucketStartTs = floorBucketTs(referenceTs, timeframeMinutes);
      const key = String(bucketStartTs);
      let bucket = bucketMap.get(key);
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
        };
        bucketMap.set(key, bucket);
      }

      const signedDelta = deltaQuantity;
      if (signedDelta > 0) bucket.buyQuantity += signedDelta;
      if (signedDelta < 0) bucket.sellQuantity += Math.abs(signedDelta);
      bucket.netQuantity += signedDelta;
      if (point.side === "sell" || point.quantityValue < 0)
        bucket.confirmedCount += 1;
      else bucket.provisionalCount += 1;

      const current = bucket.players.get(brokerKey) || {
        broker_id: point.broker_id,
        broker_name: point.broker_name || `Broker ${point.broker_id ?? "--"}`,
        grossDelta: 0,
        netDelta: 0,
        buyDelta: 0,
        sellDelta: 0,
        weightedPriceSum: 0,
        weightedPriceCount: 0,
        relativePercentage: 0,
        isForeign: Boolean(point.is_foreign_broker),
        isRetail: Boolean(point.is_retail_broker),
        brokerSegment:
          point.broker_segment || point.origin_scope || "local_or_unclassified",
        originRegistryKey: point.origin_registry_key || null,
        originLabel: point.origin_label || null,
      };
      current.grossDelta += Math.abs(signedDelta);
      current.netDelta += signedDelta;
      current.buyDelta += Math.max(signedDelta, 0);
      current.sellDelta += Math.max(-signedDelta, 0);
      if (
        Number.isFinite(point.averagePriceValue) &&
        Math.abs(signedDelta) > 0
      ) {
        current.weightedPriceSum +=
          point.averagePriceValue * Math.abs(signedDelta);
        current.weightedPriceCount += Math.abs(signedDelta);
      }
      current.relativePercentage = Math.max(
        current.relativePercentage,
        Math.abs(toNumber(point.relative_percentage_float) || 0),
      );
      bucket.players.set(brokerKey, current);

      if (current.isForeign) {
        if (signedDelta > 0) bucket.foreignBuyQuantity += signedDelta;
        if (signedDelta < 0)
          bucket.foreignSellQuantity += Math.abs(signedDelta);
        bucket.foreignHeatEvents.push({
          broker_id: point.broker_id,
          broker_name: point.broker_name || `Broker ${point.broker_id ?? "--"}`,
          deltaQuantity: signedDelta,
          averagePrice: point.averagePriceValue,
          isForeign: true,
          isRetail: false,
          originRegistryKey: point.origin_registry_key || null,
          originLabel: point.origin_label || null,
        });
      }

      if (current.isRetail) {
        if (signedDelta > 0) bucket.retailBuyQuantity += signedDelta;
        if (signedDelta < 0) bucket.retailSellQuantity += Math.abs(signedDelta);
        bucket.retailHeatEvents.push({
          broker_id: point.broker_id,
          broker_name: point.broker_name || `Broker ${point.broker_id ?? "--"}`,
          deltaQuantity: signedDelta,
          averagePrice: point.averagePriceValue,
          isForeign: false,
          isRetail: true,
          originRegistryKey: point.origin_registry_key || null,
          originLabel: point.origin_label || null,
        });
      }
    }

    for (const candle of aggregatedCandles) {
      const key = String(candle.bucketStartTs || candle.ts);
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
      };
      const players = [...(bucket.players?.values() || [])]
        .map((player) => {
          const avgPrice =
            player.weightedPriceCount > 0
              ? player.weightedPriceSum / player.weightedPriceCount
              : null;
          const netSide =
            player.netDelta > 0 ? "buy" : player.netDelta < 0 ? "sell" : "flat";
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
          };
        })
        .sort((a, b) => (b.grossDelta || 0) - (a.grossDelta || 0));

      const topBuyers = players
        .filter((player) => (player.buyDelta || 0) > 0)
        .sort((a, b) => (b.buyDelta || 0) - (a.buyDelta || 0))
        .slice(0, 5);

      const topSellers = players
        .filter((player) => (player.sellDelta || 0) > 0)
        .sort((a, b) => (b.sellDelta || 0) - (a.sellDelta || 0))
        .slice(0, 5);

      bucket.playerCount = bucket.players?.size || players.length;
      bucket.foreignPlayerCount = players.filter(
        (player) => player.isForeign,
      ).length;
      bucket.retailPlayerCount = players.filter(
        (player) => player.isRetail,
      ).length;
      bucket.signedConfirmed = bucket.confirmedCount > 0;
      bucket.topBuyers = topBuyers;
      bucket.topSellers = topSellers;
      bucket.allPlayers = players;
      bucketMap.set(key, bucket);
    }

    return bucketMap;
  }

  return {
    floorBucketTs,
    toIso,
    aggregateCandles,
    classifyExecutionHint,
    resolveHeatAnchorPrice,
    matchesParticipantScope,
    matchesParticipantSide,
    buildScopedFlowSummary,
    getDisplayFlowSummary,
    buildFlowMap,
  };
}

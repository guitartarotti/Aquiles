export function createMacroChartMetrics(context) {
  const {
    PRESSURE_COHORTS,
    clamp,
    classifyBucketEfficiency,
    classifyBucketResponse,
    formatSignedQuantity,
    toNumber,
  } = context;

  function computeBucketIndicatorMetrics(flowSummary, candle) {
    const open = toNumber(candle?.open) || 0;
    const close = toNumber(candle?.close) || open;
    const high = toNumber(candle?.high);
    const low = toNumber(candle?.low);
    const priceMovePoints = close - open;
    const rangePoints =
      Number.isFinite(high) && Number.isFinite(low)
        ? Math.abs(high - low)
        : Math.abs(priceMovePoints);
    const effectiveRange = Math.max(rangePoints, Math.abs(priceMovePoints), 1);
    const priceRatio = clamp(priceMovePoints / effectiveRange, -1, 1);

    const totalGross = Math.max(
      0,
      (toNumber(flowSummary?.buyQuantity) || 0) +
        (toNumber(flowSummary?.sellQuantity) || 0),
    );

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
    };

    const result = {};
    for (const cohort of PRESSURE_COHORTS) {
      const buy = cohortValues[cohort.key]?.buy || 0;
      const sell = cohortValues[cohort.key]?.sell || 0;
      const gross = buy + sell;
      const net = buy - sell;
      const netAbs = Math.abs(net);
      const playerCount = cohortValues[cohort.key]?.playerCount || 0;
      const netRatio = gross > 0 ? clamp(net / gross, -1, 1) : 0;
      const grossShare = totalGross > 0 ? clamp(gross / totalGross, 0, 1) : 0;
      const flowDirection = net > 0 ? 1 : net < 0 ? -1 : 0;
      const priceDirection =
        priceMovePoints > 0 ? 1 : priceMovePoints < 0 ? -1 : 0;
      const alignment =
        flowDirection && priceDirection
          ? flowDirection === priceDirection
            ? 1
            : -1
          : 0;
      const signedShare = grossShare * flowDirection;
      const flowCommitment = gross > 0 ? clamp(netAbs / gross, 0, 1) : 0;
      const rangeCapture = Math.abs(priceRatio);
      const pressureScore =
        gross > 0
          ? 100 *
            clamp(
              0.68 * netRatio +
                0.22 * signedShare +
                0.1 * alignment * Math.abs(priceRatio),
              -1,
              1,
            )
          : null;
      const efficiencyScore =
        gross > 0
          ? 100 * alignment * clamp(rangeCapture * flowCommitment, 0, 1)
          : null;
      const absorptionScore =
        gross > 0
          ? 100 * clamp(flowCommitment * (1 - rangeCapture), 0, 1)
          : null;
      const fragilityScore =
        gross > 0
          ? 100 * clamp(rangeCapture * (1 - flowCommitment), 0, 1)
          : null;
      const confidenceScore =
        totalGross > 0 && gross > 0
          ? 100 *
            clamp(0.6 * grossShare + 0.4 * Math.min(playerCount / 6, 1), 0, 1)
          : null;
      const responseState = classifyBucketResponse(
        netRatio,
        priceRatio,
        alignment,
      );
      const efficiencyState = classifyBucketEfficiency(
        net,
        efficiencyScore || 0,
        absorptionScore || 0,
        fragilityScore || 0,
        alignment,
        priceMovePoints,
      );

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
      };
    }
    return result;
  }

  function computeBucketConcentrationMetrics(flowSummary) {
    const players = Array.isArray(flowSummary?.allPlayers)
      ? flowSummary.allPlayers
      : [];
    const totalGross = players.reduce(
      (sum, player) => sum + Math.abs(toNumber(player.grossDelta) || 0),
      0,
    );
    if (!players.length || totalGross <= 0) {
      return {
        state: "inactive",
        topShare: 0,
        hhi: 0,
        breadthScore: 0,
        concentrationScore: 0,
      };
    }
    const shares = players.map(
      (player) => Math.abs(toNumber(player.grossDelta) || 0) / totalGross,
    );
    const hhiRaw = shares.reduce((sum, share) => sum + share ** 2, 0);
    const hhi = hhiRaw * 10000;
    const topShare = Math.max(...shares);
    const effectivePlayers = hhiRaw > 0 ? 1 / hhiRaw : 0;
    const breadthScore = clamp(
      Math.min(players.length / 6, 1) * 42 +
        Math.min(effectivePlayers / 4.5, 1) * 38 +
        (1 - topShare) * 20,
      0,
      100,
    );
    const concentrationScore = clamp(
      topShare * 55 + Math.min(hhi / 4000, 1) * 45,
      0,
      100,
    );
    let state = "mixed_participation";
    if (players.length === 1 || topShare >= 0.74) state = "single_name_push";
    else if (hhi >= 3200 || topShare >= 0.55) state = "concentrated_drive";
    else if (players.length >= 4 && topShare <= 0.35 && hhi <= 2200)
      state = "broad_participation";
    else if (topShare <= 0.42) state = "two_way_participation";
    return {
      state,
      topShare,
      hhi,
      breadthScore,
      concentrationScore,
    };
  }

  function collectAnnotationPlayers(flowSummary, scope, side, limit = 3) {
    const players = Array.isArray(flowSummary?.allPlayers)
      ? flowSummary.allPlayers
      : [];
    return players
      .filter((player) =>
        scope === "retail" ? player.isRetail : player.isForeign,
      )
      .filter((player) =>
        side === "buy"
          ? (toNumber(player.buyDelta) || 0) > 0
          : (toNumber(player.sellDelta) || 0) > 0,
      )
      .sort((left, right) => {
        const leftValue =
          side === "buy"
            ? toNumber(left.buyDelta) || toNumber(left.netDelta) || 0
            : toNumber(left.sellDelta) ||
              Math.abs(toNumber(left.netDelta) || 0);
        const rightValue =
          side === "buy"
            ? toNumber(right.buyDelta) || toNumber(right.netDelta) || 0
            : toNumber(right.sellDelta) ||
              Math.abs(toNumber(right.netDelta) || 0);
        return rightValue - leftValue;
      })
      .slice(0, limit);
  }

  function summarizeAnnotationPlayers(players, side) {
    if (!Array.isArray(players) || !players.length) return "";
    return players
      .map((player) => {
        const qty =
          side === "buy"
            ? toNumber(player.buyDelta) || toNumber(player.netDelta) || 0
            : toNumber(player.sellDelta) ||
              Math.abs(toNumber(player.netDelta) || 0);
        return `${player.broker_name} ${formatSignedQuantity(qty, false)}`;
      })
      .join(" | ");
  }

  return {
    computeBucketIndicatorMetrics,
    computeBucketConcentrationMetrics,
    collectAnnotationPlayers,
    summarizeAnnotationPlayers,
  };
}

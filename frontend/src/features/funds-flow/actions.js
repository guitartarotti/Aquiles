export function createFundsFlowActions(context) {
  const {
    Date,
    FUNDS_FLOW_HISTORY_DAYS,
    Set,
    activeTab,
    anbimaDaily,
    b3Investor,
    b3InvestorMonthly,
    b3MarketData,
    b3MarketSummary,
    b3OpenInterest,
    b3TrendMap,
    bcbLatestBySeries,
    bcbMacro,
    cadenceLabel,
    cdaAnalyticsLoaded,
    cdaGraphLoaded,
    cdaLoaded,
    cdaRadarLoaded,
    cdaReport,
    cdaSelectedAssetTrail,
    cdaSelectedBridgePath,
    cdaSelectedCoherenceRow,
    cftcPositioning,
    closeCdaAssetTrailModal,
    closeCdaBridgeModal,
    closeCdaCoherenceModal,
    error,
    etfFlowBarMax,
    fmtCount,
    fmtDate,
    fmtDateTime,
    fmtLatency,
    getFundsFlowLocalDashboard,
    iciLatestDate,
    iciMonthlyEtf,
    iciWorldwide,
    loadCdaAnalytics,
    loadCdaDashboard,
    loadCdaGraph,
    loadCdaRadar,
    loadNportAnalytics,
    loadNportDashboard,
    metric,
    moneyFlowMode,
    nextTick,
    nportAnalyticsLoaded,
    nportLoaded,
    payload,
    period,
    refreshingSource,
    report,
    resetTabScroll,
    selectedIciSeries,
    sourcePublicationGap,
    sourceStatusClass,
    sourceStatusLabel,
  } = context;

  function selectTab(key) {
    activeTab.value = key;
    if (key === "nport" && !nportLoaded.value) {
      loadNportDashboard(false);
    } else if (key === "nport" && nportLoaded.value && !nportAnalyticsLoaded.value) {
      loadNportAnalytics(false);
    } else if (key === "cda" && !cdaLoaded.value) {
      loadCdaDashboard(false);
    } else if (key === "cda" && cdaLoaded.value && !cdaAnalyticsLoaded.value) {
      loadCdaAnalytics(false);
    } else if (key === "radar_cda" && !cdaRadarLoaded.value) {
      loadCdaRadar(false);
    } else if (key === "graph" && !cdaGraphLoaded.value) {
      loadCdaGraph(false);
    }
    if (key === "graph" && moneyFlowMode.value === "quarterly" && !nportLoaded.value) {
      loadNportDashboard(false);
    } else if (
      key === "graph" &&
      moneyFlowMode.value === "quarterly" &&
      nportLoaded.value &&
      !nportAnalyticsLoaded.value
    ) {
      loadNportAnalytics(false);
    }
    nextTick(() => {
      const classByTab = {
        overview: "ffl-overview",
        b3: "ffl-b3-view",
        etf: "ffl-etf-view",
        map: "ffl-map-view",
        stress: "ffl-stress-view",
        anbima: "ffl-anbima-view",
        global: "ffl-global-view",
        cftc: "ffl-cftc-view",
        nport: "ffl-nport-view",
        cda: "ffl-cda-view",
        radar_cda: "ffl-cda-radar-view",
        graph: "ffl-graph-view",
        sources: "ffl-sources-view",
      };
      const selector = `.${classByTab[key] || "ffl-overview"}`;
      resetTabScroll(selector);
    });
  }

  async function refreshSource(sourceId) {
    try {
      refreshingSource.value = sourceId;
      error.value = "";
      const res = await getFundsFlowLocalDashboard({
        period: period.value,
        history_days: FUNDS_FLOW_HISTORY_DAYS,
        _ts: Date.now(),
        source: sourceId,
      });
      payload.value = res?.data?.data ?? res?.data ?? res ?? payload.value;
    } catch (err) {
      error.value = friendlyError(err);
    } finally {
      refreshingSource.value = "";
    }
  }

  function toggleIciSeries(key) {
    const current = new Set(selectedIciSeries.value);
    if (current.has(key)) {
      current.delete(key);
    } else {
      current.add(key);
    }
    selectedIciSeries.value = [...current].slice(-8);
  }

  function metricValue(row) {
    if (!row) return null;
    if (metric.value === "pct_pl") return Number(row.flow_pct_pl_21d || row.flow_pct_pl || 0) * 100;
    if (metric.value === "zscore") return Number(row.zscore || 0);
    return Number(row.rolling_flow_21d || row.net_flow || 0) / 1_000_000_000;
  }

  function rankingWindowFlowValue(row, window = "21d") {
    if (!row) return 0;
    if (window === "1d") return Number(row.net_flow_1d ?? row.captacao_liquida_total ?? row.net_flow ?? 0);
    if (window === "5d") return Number(row.net_flow_5d ?? row.rolling_flow_5d ?? 0);
    return Number(row.net_flow_21d ?? row.rolling_flow_21d ?? row.captacao_liquida_total ?? row.net_flow ?? 0);
  }

  function classFlowValue(row) {
    if (!row) return 0;
    return Number(row.net_flow_21d ?? row.captacao_liquida_total ?? row.net_flow ?? row.value ?? row.flow ?? 0);
  }

  function b3Trend(participantType) {
    return b3TrendMap.value?.[participantType] || null;
  }

  function divergingBarStyle(value, maxAbs) {
    const parsed = Number(value);
    const max = Math.max(Number(maxAbs || 0), 1);
    if (!Number.isFinite(parsed)) return { left: "50%", width: "0%" };
    const width = Math.min(Math.abs(parsed) / max, 1) * 48;
    const left = parsed < 0 ? 50 - width : 50;
    return { left: `${left}%`, width: `${width}%` };
  }

  function etfFlowBarHeight(value) {
    const parsed = Math.abs(Number(value || 0));
    const max = Math.max(Number(etfFlowBarMax.value || 0), 1);
    return `${8 + Math.min(parsed / max, 1) * 42}px`;
  }

  function sourceLastCapture(source) {
    if (sourcePublicationGap(source)) return "sem publ.";
    if (source.id === "ici_global_flows") return fmtDate(iciLatestDate.value) || iciWorldwide.value?.quarter || "-";
    if (source.id === "cftc_cot") return fmtDate(cftcPositioning.value?.report_date);
    if (source.id === "anbima_fundos") return fmtDate(anbimaDaily.value?.reference_date);
    if (source.id === "bcb_macro")
      return fmtDate(bcbLatestBySeries.value?.selic_target?.date || bcbMacro.value?.summary?.latest_usdbrl_ptax?.date);
    if (source.id === "b3_etfs") return fmtDate(report.value.last_updated_at);
    if (source.id === "b3_market") return fmtDate(b3Investor.value?.data_until);
    if (source.id === "b3_derivatives_open_interest") return fmtDate(b3OpenInterest.value?.date);
    if (source.id === "b3_investor_participation_monthly")
      return b3InvestorMonthly.value?.period_label || fmtDate(b3InvestorMonthly.value?.date);
    if (source.id === "b3_market_data_report")
      return b3MarketData.value?.data_until || b3MarketSummary.value?.period || "-";
    if (source.id === "cvm_informe_diario") return fmtDate(report.value.as_of_date);
    if (source.id === "cvm_cadastro_fi") return fmtDate(report.value.last_updated_at);
    if (source.id === "cvm_cda") return cdaReport.value?.period_label || fmtDate(cdaReport.value?.as_of_date);
    return source.ok ? fmtDate(report.value.last_updated_at) : "-";
  }

  function sourceOfficialDate(source) {
    if (sourcePublicationGap(source)) return "sem publ.";
    if (source.id === "ici_global_flows")
      return fmtDate(iciLatestDate.value) || fmtDate(source.latest_data_date) || "-";
    if (source.id === "b3_investor_participation_monthly")
      return source.reference_label || b3InvestorMonthly.value?.period_label || fmtDate(source.latest_data_date);
    if (source.id === "cvm_cda") return cdaReport.value?.period_label || fmtDate(cdaReport.value?.as_of_date);
    return source.reference_label || fmtDate(source.latest_data_date) || sourceLastCapture(source);
  }

  function sourceReference(source) {
    if (source.id === "ici_global_flows") {
      const refs = [
        iciMonthlyEtf.value?.reference_month ? `ETF assets ${iciMonthlyEtf.value.reference_month}` : null,
        iciWorldwide.value?.quarter ? `Worldwide ${iciWorldwide.value.quarter}` : null,
      ].filter(Boolean);
      return refs.join(" | ");
    }
    if (source.id === "b3_investor_participation_monthly") {
      return b3InvestorMonthly.value?.period_label || source.reference_label || "";
    }
    if (source.id === "cvm_cda") {
      return cdaReport.value?.period_label || "";
    }
    return source.reference_label || "";
  }

  function sourceCapturedAt(source) {
    if (source.last_captured_at) return fmtDateTime(source.last_captured_at);
    if (source.ok && report.value.last_updated_at) return fmtDateTime(report.value.last_updated_at);
    return "-";
  }

  function sourceTechnicalSummary(source) {
    if (sourcePublicationGap(source)) {
      return `Consulta executada, mas a fonte oficial respondeu sem linhas publicadas para a janela sondada em torno de ${fmtDate(report.value.as_of_date)}. O endpoint existe e retornou schema, porém sem dados utilizáveis nessa tabela.`;
    }
    if (source.latest_error || source.error) return `Falha recente: ${source.latest_error || source.error}`;
    if (sourceStatusClass(source) === "active") {
      return `Captura operacional com ${fmtCount(source.rows)} linhas agregadas, latencia ${fmtLatency(source.latency_ms)} e cache local versionado.`;
    }
    if (sourceStatusClass(source) === "configured") {
      return "Fonte mapeada no contrato, mas ainda sem loader ativo no pipeline diario atual.";
    }
    return "Fonte sem captura ativa ou sem dados recentes no payload.";
  }

  function sourceTemporalDetail(source) {
    if (source.id === "ici_global_flows")
      return "Weekly XLS para fluxos; monthly release para ETF assets; quarterly XLS para pais/regiao.";
    if (source.id === "cftc_cot")
      return "COT/PRE semanal: posicoes de terca-feira, publicacao publica usual na sexta; TFF, Disaggregated, Legacy e CIT via API.";
    if (source.id === "bcb_macro")
      return "SGS diario/mensal por serie e PTAX OData com boletins intradiarios agregados por data.";
    if (source.id === "b3_etfs") return "Consulta B3 Fundos Listados por segmento ETF; rechecagem diaria no pipeline.";
    if (source.id?.startsWith("b3_") || source.id === "b3_market")
      return "BDI/CSV B3 diario, com algumas tabelas mensais acumuladas.";
    if (source.id === "anbima_fundos") return "Consolidado diario e boletim/rankings mensais via ANBIMA Data.";
    if (source.id === "cvm_cda")
      return "CVM CDA e mensal; meses recentes sao rechecados diariamente por possiveis reapresentacoes/confidencialidade, meses antigos semanalmente.";
    if (source.id?.startsWith("cvm_"))
      return "CVM publica arquivos mensais com observacoes diarias; cadastro e informe sao rechecados na coleta.";
    return cadenceLabel(source.cadence);
  }

  function sourceHealthDetail(source) {
    const parts = [
      `status=${sourceStatusLabel(source)}`,
      `ok=${Boolean(source.ok)}`,
      `rows=${fmtCount(source.rows)}`,
      `latencia=${fmtLatency(source.latency_ms)}`,
      `data_oficial=${source.officialDate}`,
      `capturado_em=${source.capturedAt}`,
    ];
    if (sourcePublicationGap(source)) parts.push("sem_publicacao=true");
    if (source.latest_error) parts.push(`erro=${source.latest_error}`);
    if (source.secondaryReference) parts.push(`referencia=${source.secondaryReference}`);
    return parts.join(" | ");
  }

  function sourceComponents(source) {
    const map = {
      cvm_informe_diario: [
        "CKAN package_show",
        "ZIP mensal",
        "CSV informe",
        "raw_cvm_informe_diario",
        "analytics flow daily",
      ],
      cvm_cadastro_fi: ["Cadastro legado", "Registro RCVM175", "normalizacao CNPJ", "classificacao fallback"],
      cvm_cda: [
        "CKAN package_show",
        "ZIP mensal CDA",
        "BLC 1-8",
        "PL por fundo",
        "SQLite separado",
        "analytics holdings Brasil",
      ],
      anbima_fundos: [
        "Consolidado diario",
        "Tipos ANBIMA",
        "Boletim mensal",
        "Rankings gestor/admin",
        "validacao CVM x ANBIMA",
      ],
      ici_global_flows: [
        "Weekly MF flows",
        "Weekly ETF net issuance",
        "Combined MF+ETF",
        "Monthly ETF assets",
        "Worldwide quarterly pais/regiao",
      ],
      b3_etfs: ["Fundos Listados B3", "ETF RV", "ETF RF", "ETF FII", "ETF cripto", "ETF internacional RF"],
      b3_market: ["BDI PDF", "participacao investidores", "historico 21d", "saldo por participante"],
      b3_derivatives_open_interest: [
        "BDI table export",
        "DI/DDI/DOL/WDO/WIN",
        "open interest",
        "variacao d/d",
        "rolling 21d",
      ],
      b3_investor_participation_monthly: ["BDI table export", "vista", "termo", "opcoes", "exercicios", "blocos"],
      b3_market_data_report: ["CSV dados de mercado", "volume", "ADV", "negocios", "estrangeiro"],
      bcb_macro: ["SGS USD/BRL", "SGS Selic diaria", "SGS Selic meta", "SGS IPCA", "OData PTAX"],
      fred_macro: ["FRED API", "Treasury yields", "breakeven", "commodities"],
      cftc_cot: [
        "CFTC PRE/API",
        "TFF FutOnly",
        "TFF Combined",
        "Disaggregated",
        "Legacy",
        "Supplemental CIT",
        "Tuesday position",
        "Friday release",
      ],
    };
    return map[source.id] || [source.role || "componente configurado"];
  }

  function sourceLogText(source) {
    const payload = {
      id: source.id,
      label: source.label,
      status: source.status,
      ok: source.ok,
      rows: source.rows,
      cadence: source.cadence,
      official_date: source.officialDate,
      captured_at: source.capturedAt,
      secondary_reference: source.secondaryReference,
      latency_ms: source.latency_ms,
      url: source.url,
      cached_path: source.cached_path,
      latest_error: source.latest_error,
      components: sourceComponents(source),
      collector: payloadSummaryCollector(),
    };
    return JSON.stringify(payload, null, 2);
  }

  function payloadSummaryCollector() {
    return {
      cache_status: report.value.cache_status,
      last_updated_at: report.value.last_updated_at,
      started_at: report.value.started_at,
      completed_at: report.value.completed_at,
      raw_dir: report.value.lineage?.raw_dir,
      derived_dir: report.value.lineage?.derived_dir,
    };
  }

  function friendlyError(err) {
    return err?.response?.data?.error || err?.message || "Falha ao carregar Funds Flow Local.";
  }

  function handleKeydown(event) {
    if (event.key !== "Escape") return;
    if (cdaSelectedCoherenceRow.value) {
      closeCdaCoherenceModal();
      return;
    }
    if (cdaSelectedAssetTrail.value) {
      closeCdaAssetTrailModal();
      return;
    }
    if (cdaSelectedBridgePath.value) {
      closeCdaBridgeModal();
    }
  }

  return {
    selectTab,
    refreshSource,
    toggleIciSeries,
    metricValue,
    rankingWindowFlowValue,
    classFlowValue,
    b3Trend,
    divergingBarStyle,
    etfFlowBarHeight,
    sourceLastCapture,
    sourceOfficialDate,
    sourceReference,
    sourceCapturedAt,
    sourceTechnicalSummary,
    sourceTemporalDetail,
    sourceHealthDetail,
    sourceComponents,
    sourceLogText,
    payloadSummaryCollector,
    friendlyError,
    handleKeydown,
  };
}

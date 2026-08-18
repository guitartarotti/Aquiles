import service, { atemporalChartService, discoveryService, fairValueMarkovService, flowReplicatorService, requestWithRetry } from './index'

const sharedRequestCache = new Map()
const sharedInFlightRequests = new Map()

function normalizeRequestKey(value) {
  if (Array.isArray(value)) {
    return value.map(normalizeRequestKey)
  }
  if (value && typeof value === 'object') {
    return Object.keys(value)
      .filter(key => value[key] !== undefined)
      .sort()
      .reduce((acc, key) => {
        acc[key] = normalizeRequestKey(value[key])
        return acc
      }, {})
  }
  return value
}

function buildSharedRequestKey(scope, payload = {}) {
  return `${scope}:${JSON.stringify(normalizeRequestKey(payload))}`
}

function getSharedCacheValue(key) {
  const entry = sharedRequestCache.get(key)
  if (!entry) return null
  if (entry.expiresAt <= Date.now()) {
    sharedRequestCache.delete(key)
    return null
  }
  return entry.value
}

function setSharedCacheValue(key, value, ttlMs) {
  if (!(ttlMs > 0)) return
  sharedRequestCache.set(key, {
    value,
    expiresAt: Date.now() + ttlMs,
  })
}

function sharedRequest({
  scope,
  payload = {},
  ttlMs = 0,
  forceRefresh = false,
  requestFn,
}) {
  const key = buildSharedRequestKey(scope, payload)
  const inFlight = sharedInFlightRequests.get(key)
  if (inFlight) return inFlight

  if (!forceRefresh && ttlMs > 0) {
    const cached = getSharedCacheValue(key)
    if (cached != null) return Promise.resolve(cached)
  }

  const promise = Promise.resolve()
    .then(requestFn)
    .then(result => {
      if (!forceRefresh && ttlMs > 0) {
        setSharedCacheValue(key, result, ttlMs)
      }
      return result
    })
    .finally(() => {
      sharedInFlightRequests.delete(key)
    })

  sharedInFlightRequests.set(key, promise)
  return promise
}

export function getMacroSnapshot(params = {}) {
  return service({
    url: '/api/macro/snapshot',
    method: 'get',
    params
  })
}

export function collectMacroSnapshot(data = {}) {
  return requestWithRetry(() =>
    service({
      url: '/api/macro/collect',
      method: 'post',
      data
    }),
  2, 1500)
}

export function syncMacroProject(data = {}) {
  return requestWithRetry(() =>
    service({
      url: '/api/macro/project/sync',
      method: 'post',
      data
    }),
  2, 1500)
}

export function getMacroCollectorStatus() {
  return service({
    url: '/api/macro/collector/status',
    method: 'get'
  })
}

export function getMacroEvents(params = {}) {
  return requestWithRetry(() =>
    service({
      url: '/api/macro/events',
      method: 'get',
      params
    }),
  2, 1000)
}

export function getMacroEventsToday(params = {}) {
  return requestWithRetry(() =>
    service({
      url: '/api/macro/events/today',
      method: 'get',
      params
    }),
  2, 1500)
}

export function getMacroOverview(params = {}) {
  return requestWithRetry(() =>
    service({
      url: '/api/macro/overview',
      method: 'get',
      params
    }),
  2, 1000)
}

export function getMacroThermometer(params = {}) {
  return requestWithRetry(() =>
    service({
      url: '/api/macro/thermometer',
      method: 'get',
      params
    }),
  2, 1000)
}

export function getMacroCrossAsset(params = {}) {
  return requestWithRetry(() =>
    service({
      url: '/api/macro/cross-asset',
      method: 'get',
      params
    }),
  2, 1000)
}

export function getMacroParticipantHeatmap(params = {}) {
  return requestWithRetry(() =>
    service({
      url: '/api/macro/participant-heatmap',
      method: 'get',
      params
    }),
  2, 1000)
}

export function getMacroDrivers(params = {}) {
  return requestWithRetry(() =>
    service({
      url: '/api/macro/drivers',
      method: 'get',
      params
    }),
  2, 1000)
}

export function focusMacroDriver(data = {}) {
  return requestWithRetry(() =>
    service({
      url: '/api/macro/drivers/focus',
      method: 'post',
      data
    }),
  2, 1500)
}

export function getMacroTrends(params = {}) {
  return requestWithRetry(() =>
    service({
      url: '/api/macro/trends',
      method: 'get',
      params
    }),
  2, 1000)
}

export function focusMacroTrend(data = {}) {
  return requestWithRetry(() =>
    service({
      url: '/api/macro/trends/focus',
      method: 'post',
      data
    }),
  2, 1500)
}

export function getMarketScreenChartPanel(params = {}) {
  const payload = { ...params }
  const forceRefresh = Boolean(payload.refresh)
  return sharedRequest({
    scope: 'macro-w32-chart',
    payload,
    ttlMs: forceRefresh ? 0 : 12_000,
    forceRefresh,
    requestFn: () => requestWithRetry(() =>
      service({
        url: '/api/macro/screen-capture/w32-basica/chart',
        method: 'get',
        params: payload
      }),
    2, 1000),
  })
}

export function getMarketScreenBenchmarkCandles(params = {}) {
  const payload = { ...params, _ts: Date.now() }
  return discoveryService({
    url: '/api/macro/screen-capture/w32-basica/benchmark-candles',
    method: 'get',
    params: payload
  })
}

export function getFlowReplicatorStatus() {
  return flowReplicatorService({
    url: '/api/flow/replicator/status',
    method: 'get'
  })
}

export function startFlowReplicator(data = {}) {
  return flowReplicatorService({
    url: '/api/flow/replicator/start',
    method: 'post',
    data
  })
}

export function stopFlowReplicator(data = {}) {
  return flowReplicatorService({
    url: '/api/flow/replicator/stop',
    method: 'post',
    data
  })
}

export function getFlowAgentsLatest(params = {}) {
  return flowReplicatorService({
    url: '/api/flow/agents/latest',
    method: 'get',
    params
  })
}

export function getFlowDeltaWindows(data = {}) {
  return requestWithRetry(() =>
    flowReplicatorService({
      url: '/api/flow/deltas/windows',
      method: 'post',
      data
    }),
  1, 800)
}

export function getFlowActivityRadar(params = {}) {
  return requestWithRetry(() =>
    flowReplicatorService({
      url: '/api/flow/activity-radar',
      method: 'get',
      params
    }),
  1, 800)
}

export function getCurveDiscoveryPanel(params = {}) {
  return requestWithRetry(() =>
    discoveryService({
      url: '/api/macro/curves/discovery',
      method: 'get',
      params
    }),
  2, 1000)
}

export function getCurveDiscoveryAi(data = {}) {
  return requestWithRetry(() =>
    discoveryService({
      url: '/api/macro/curves/discovery/ai',
      method: 'post',
      data
    }),
  1, 1000)
}

export function getReportSourceDiscoveryPanel(params = {}) {
  const payload = { ...params }
  const forceRefresh = Boolean(payload.refresh)
  return sharedRequest({
    scope: 'macro-report-sources-panel',
    payload,
    ttlMs: forceRefresh ? 0 : 60_000,
    forceRefresh,
    requestFn: () => requestWithRetry(() =>
      service({
        url: '/api/macro/report-sources/panel',
        method: 'get',
        params: payload
      }),
    1, 1500),
  })
}

export function collectReportSourceDiscovery(data = {}) {
  return requestWithRetry(() =>
    service({
      url: '/api/macro/report-sources/collect',
      method: 'post',
      data
    }),
  1, 1500)
}

export function getReportSourceDiscoveryStatus() {
  return service({
    url: '/api/macro/report-sources/status',
    method: 'get'
  })
}

export function getFundsFlowLocalDashboard(params = {}) {
  const payload = { ...params, _ts: params._ts ?? Date.now() }
  return requestWithRetry(() =>
    service({
      url: '/api/v1/funds-flow-local/dashboard',
      method: 'get',
      params: payload
    }),
  1, 1500)
}

export function collectFundsFlowLocal(data = {}) {
  return requestWithRetry(() =>
    service({
      url: '/api/v1/funds-flow-local/collect',
      method: 'post',
      data
    }),
  1, 1500)
}

export function refreshFundsFlowLocalSource(sourceId, data = {}) {
  return requestWithRetry(() =>
    service({
      url: `/api/v1/funds-flow-local/sources/${encodeURIComponent(sourceId)}/refresh`,
      method: 'post',
      data
    }),
  1, 1500)
}

export function getFundsFlowLocalStatus() {
  return service({
    url: '/api/v1/funds-flow-local/status',
    method: 'get'
  })
}

export function getNportDashboard(params = {}) {
  const payload = { ...params, _ts: params._ts ?? Date.now() }
  return requestWithRetry(() =>
    service({
      url: '/api/v1/nport/dashboard',
      method: 'get',
      params: payload
    }),
  1, 1500)
}

export function getNportPerformance(params = {}) {
  const payload = { ...params, _ts: params._ts ?? Date.now() }
  return requestWithRetry(() =>
    service({
      url: '/api/v1/nport/analytics/performance',
      method: 'get',
      params: payload
    }),
  1, 1500)
}

export function getNportRegionFunds(params = {}) {
  const payload = { ...params, _ts: params._ts ?? Date.now() }
  return requestWithRetry(() =>
    service({
      url: '/api/v1/nport/analytics/funds',
      method: 'get',
      params: payload
    }),
  1, 1500)
}

export function getNportRegionAssets(params = {}) {
  const payload = { ...params, _ts: params._ts ?? Date.now() }
  return requestWithRetry(() =>
    service({
      url: '/api/v1/nport/analytics/assets',
      method: 'get',
      params: payload
    }),
  1, 1500)
}

export function getNportFundHoldings(accessionNumber, params = {}) {
  const payload = { ...params, _ts: params._ts ?? Date.now() }
  return requestWithRetry(() =>
    service({
      url: `/api/v1/nport/analytics/fund-holdings/${encodeURIComponent(accessionNumber)}`,
      method: 'get',
      params: payload
    }),
  1, 1500)
}

export function getNportPositioning(params = {}) {
  const payload = { ...params, _ts: params._ts ?? Date.now() }
  return requestWithRetry(() =>
    service({
      url: '/api/v1/nport/analytics/positioning',
      method: 'get',
      params: payload
    }),
  1, 1500)
}

export function rebuildNportAnalytics(data = {}) {
  return requestWithRetry(() =>
    service({
      url: '/api/v1/nport/analytics/rebuild',
      method: 'post',
      data
    }),
  1, 1500)
}

export function ingestNportLocal(data = {}) {
  return requestWithRetry(() =>
    service({
      url: '/api/v1/nport/ingest-local',
      method: 'post',
      data
    }),
  1, 1500)
}

export function getNportRemote(params = {}) {
  return requestWithRetry(() =>
    service({
      url: '/api/v1/nport/remote',
      method: 'get',
      params
    }),
  1, 1500)
}

export function downloadNportQuarter(data = {}) {
  return requestWithRetry(() =>
    service({
      url: '/api/v1/nport/download',
      method: 'post',
      data
    }),
  1, 1500)
}

export function getCvmCdaDashboard(params = {}) {
  const payload = { ...params, _ts: params._ts ?? Date.now() }
  return requestWithRetry(() =>
    service({
      url: '/api/v1/cvm-cda/dashboard',
      method: 'get',
      params: payload
    }),
  1, 1500)
}

export function getCvmCdaFunds(params = {}) {
  const payload = { ...params, _ts: params._ts ?? Date.now() }
  return requestWithRetry(() =>
    service({
      url: '/api/v1/cvm-cda/analytics/funds',
      method: 'get',
      params: payload
    }),
  1, 1500)
}

export function getCvmCdaAssets(params = {}) {
  const payload = { ...params, _ts: params._ts ?? Date.now() }
  return requestWithRetry(() =>
    service({
      url: '/api/v1/cvm-cda/analytics/assets',
      method: 'get',
      params: payload
    }),
  1, 1500)
}

export function getCvmCdaFundHoldings(fundCnpj, params = {}) {
  const payload = { ...params, _ts: params._ts ?? Date.now() }
  return requestWithRetry(() =>
    service({
      url: `/api/v1/cvm-cda/analytics/fund-holdings/${encodeURIComponent(fundCnpj)}`,
      method: 'get',
      params: payload
    }),
  1, 1500)
}

export function getCvmCdaPositioning(params = {}) {
  const payload = { ...params, _ts: params._ts ?? Date.now() }
  return requestWithRetry(() =>
    service({
      url: '/api/v1/cvm-cda/analytics/positioning',
      method: 'get',
      params: payload
    }),
  1, 1500)
}

export function getCvmCdaRadar(params = {}) {
  const payload = { ...params, _ts: params._ts ?? Date.now() }
  return requestWithRetry(() =>
    service({
      url: '/api/v1/cvm-cda/analytics/radar',
      method: 'get',
      params: payload
    }),
  1, 1500)
}

export function ingestCvmCda(data = {}) {
  return requestWithRetry(() =>
    service({
      url: '/api/v1/cvm-cda/ingest',
      method: 'post',
      data
    }),
  1, 1500)
}

export function getCvmCdaStatus() {
  return service({
    url: '/api/v1/cvm-cda/status',
    method: 'get'
  })
}

export function getFairValueLegsChartPanel(data = {}) {
  const payload = { ...data }
  const hasCustomComposition = Boolean(payload?.config?.legs)
  const forceRefresh = Boolean(payload.force_refresh)
  return sharedRequest({
    scope: 'macro-fair-value-legs',
    payload,
    ttlMs: forceRefresh ? 0 : (hasCustomComposition ? 2_500 : 4_000),
    forceRefresh,
    requestFn: () => requestWithRetry(() =>
      discoveryService({
        url: '/api/macro/fair-value/legs-chart',
        method: 'post',
        data: payload
      }),
    1, 1000),
  })
}

export function getFairValueLegsLatestPoint(data = {}) {
  const payload = { ...data, _ts: Date.now() }
  return discoveryService({
    url: '/api/macro/fair-value/legs-chart/latest',
    method: 'post',
    data: payload
  })
}

export function getFairValueMarkovRegime(data = {}) {
  const payload = { ...data }
  const forceRefresh = Boolean(payload.force_refresh)
  return sharedRequest({
    scope: 'macro-fair-value-markov-regime',
    payload,
    ttlMs: forceRefresh ? 0 : 5_000,
    forceRefresh,
    requestFn: () => requestWithRetry(() =>
      fairValueMarkovService({
        url: '/api/macro/fair-value/markov-regime',
        method: 'post',
        data: payload
      }),
    1, 1000),
  })
}

export function getFairValueMarkovRegimeLatest(data = {}) {
  const payload = { ...data, _ts: Date.now() }
  return fairValueMarkovService({
    url: '/api/macro/fair-value/markov-regime/latest',
    method: 'post',
    data: payload
  })
}

export function getAtemporalPriceChart(data = {}) {
  const payload = { ...data }
  const forceRefresh = Boolean(payload.force_refresh)
  return sharedRequest({
    scope: 'macro-atemporal-price-chart',
    payload,
    ttlMs: forceRefresh ? 0 : 2_500,
    forceRefresh,
    requestFn: () => requestWithRetry(() =>
      atemporalChartService({
        url: '/api/macro/atemporal/price-chart',
        method: 'post',
        data: payload
      }),
    1, 1000),
  })
}

export function getAtemporalPriceChartLatest(data = {}) {
  const payload = { ...data, _ts: Date.now() }
  return atemporalChartService({
    url: '/api/macro/atemporal/price-chart/latest',
    method: 'post',
    data: payload
  })
}

export function getAtemporalPriceChartLatestPrice(data = {}) {
  const payload = { ...data, _ts: Date.now() }
  return atemporalChartService({
    url: '/api/macro/atemporal/price-chart/latest-price',
    method: 'post',
    data: payload
  })
}

export function getLatestW32BasicaScreenCapture() {
  return sharedRequest({
    scope: 'macro-w32-latest',
    payload: {},
    ttlMs: 1_500,
    requestFn: () => discoveryService({
      url: '/api/macro/screen-capture/w32-basica/latest',
      method: 'get'
    }),
  })
}

export function getLatestW32BasicaSymbol(params = {}) {
  return discoveryService({
    url: '/api/macro/screen-capture/w32-basica/latest-symbol',
    method: 'get',
    params: { ...params, _ts: Date.now() },
  })
}

export function compactScreenCaptureCsv(params = {}) {
  return service({
    url: '/api/macro/screen-capture/compact-csv',
    method: 'post',
    params
  })
}

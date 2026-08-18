import service, { requestWithRetry, optionsModelService, optionsVolumeTrackerService, volAnalyticsService } from './index'

function withFreshParams(params = {}) {
  return {
    ...params,
    _ts: Date.now()
  }
}

const sharedRequestCache = new Map()
const sharedInFlightRequests = new Map()

function normalizeRequestKey(value) {
  if (Array.isArray(value)) {
    return value.map(normalizeRequestKey)
  }
  if (value && typeof value === 'object') {
    return Object.keys(value)
      .filter(key => key !== '_ts' && value[key] !== undefined)
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

function invalidateSharedCache(prefixes = []) {
  if (!Array.isArray(prefixes) || !prefixes.length) return
  for (const key of sharedRequestCache.keys()) {
    if (prefixes.some(prefix => key.startsWith(prefix))) {
      sharedRequestCache.delete(key)
    }
  }
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

export function getOptionsStatus() {
  return requestWithRetry(() =>
    service({
      url: '/api/options/status',
      method: 'get',
      params: withFreshParams()
    }),
  2, 1000)
}

export function getOptionsUniverse(params = {}) {
  return requestWithRetry(() =>
    service({
      url: '/api/options/universe',
      method: 'get',
      params: withFreshParams(params)
    }),
  2, 1000)
}

export function getLatestOptionsModel(params = {}) {
  const payload = {
    compact: true,
    ...params,
  }
  const forceRefresh = Boolean(payload.refresh)
  return sharedRequest({
    scope: 'options-model-latest',
    payload,
    ttlMs: forceRefresh ? 0 : 3_000,
    forceRefresh,
    requestFn: () => requestWithRetry(() =>
      optionsModelService({
        url: '/api/options/model/latest',
        method: 'get',
        params: withFreshParams(payload)
      }),
    2, 1000),
  })
}

export function runOptionsModel(data = {}) {
  return requestWithRetry(() =>
    service({
      url: '/api/options/model/run',
      method: 'post',
      data: {
        async: false,
        persist: true,
        compact: true,
        refresh_snapshot: true,
        ...data
      }
    }),
  2, 1500)
}

export function getLatestOptionsGlobal(params = {}) {
  return requestWithRetry(() =>
    service({
      url: '/api/options/global/latest',
      method: 'get',
      params: withFreshParams(params)
    }),
  2, 1000)
}

export function runOptionsGlobal(data = {}) {
  return requestWithRetry(() =>
    service({
      url: '/api/options/global/run',
      method: 'post',
      data: {
        async: false,
        persist: true,
        ...data
      }
    }),
  2, 1500)
}

export function hardRefreshOptionsBase(data = {}) {
  return requestWithRetry(() =>
    service({
      url: '/api/options/hard-refresh',
      method: 'post',
      data: {
        async: false,
        ...data
      }
    }),
  1, 1000)
}

export function getLatestOptionsHeatmapContext(params = {}) {
  return requestWithRetry(() =>
    service({
      url: '/api/options/heatmap-context/latest',
      method: 'get',
      params: withFreshParams(params)
    }),
  1, 500)
}

export function getLatestIntradayCorrelationHistory(params = {}) {
  return requestWithRetry(() =>
    service({
      url: '/api/options/intraday-correlation-history/latest',
      method: 'get',
      params: withFreshParams(params)
    }),
  1, 500)
}

export function getOptionsChat(params = {}) {
  return requestWithRetry(() =>
    service({
      url: '/api/options/chat',
      method: 'get',
      params: withFreshParams(params)
    }),
  2, 1000)
}

export function sendOptionsChatMessage(data = {}) {
  return requestWithRetry(() =>
    service({
      url: '/api/options/chat/message',
      method: 'post',
      data
    }),
  2, 1500)
}

// ─── Volume Activity Tracker ──────────────────────────────────────────────────

export function getVolumeActivity(params = {}) {
  const payload = { ...params }
  const forceRefresh = Boolean(payload.refresh)
  return sharedRequest({
    scope: 'volume-activity',
    payload,
    ttlMs: forceRefresh ? 0 : 2_000,
    forceRefresh,
    requestFn: () => requestWithRetry(() =>
      optionsVolumeTrackerService({
        url: '/api/options/volume/activity',
        method: 'get',
        params: withFreshParams(payload)
      }),
    1, 500),
  })
}

export function getVolumeSummary(params = {}) {
  return optionsVolumeTrackerService({
    url: '/api/options/volume/summary',
    method: 'get',
    params: withFreshParams(params)
  })
}

export function getVolumeIvHistory(params = {}) {
  const payload = { ...params }
  const forceRefresh = Boolean(payload.refresh)
  return sharedRequest({
    scope: 'volume-iv-history',
    payload,
    ttlMs: forceRefresh ? 0 : 3_000,
    forceRefresh,
    requestFn: () => requestWithRetry(() =>
      volAnalyticsService({
        url: '/api/options/volume/iv-history',
        method: 'get',
        params: withFreshParams(payload)
      }),
    1, 500),
  })
}

export function getVolumeTrackerStatus() {
  return sharedRequest({
    scope: 'volume-tracker-status',
    ttlMs: 2_000,
    requestFn: () => optionsVolumeTrackerService({ url: '/api/options/volume/tracker/status', method: 'get' }),
  })
}

export function startVolumeTracker() {
  return optionsVolumeTrackerService({ url: '/api/options/volume/tracker/start', method: 'post' })
}

export function pollVolume(underlying_security) {
  return optionsVolumeTrackerService({
    url: '/api/options/volume/poll',
    method: 'post',
    data: { underlying_security }
  })
}

export function backfillVolumeActivity() {
  return optionsVolumeTrackerService({ url: '/api/options/volume/tracker/backfill', method: 'post' })
}

// ─── SABR + Whalley-Wilmott Delta Hedge Model ─────────────────────────────────

/**
 * Calcula contratos de hedge delta usando o modelo SABR (smile-consistent)
 * com banda ótima de Whalley-Wilmott.
 *
 * @param {Object} data
 *   spot            {number}  Spot atual do IBOV
 *   market_ctx      {Object}  { implied_vol, days_to_expiry, risk_free_rate }
 *   vol_surface     {Array}   Pontos de vol para calibração [{strike,iv,dte}]
 *   events          {Array}   Eventos de volume [{strike,put_call,volume,...}]
 *   session_date    {string}  YYYY-MM-DD (alternativa a events — carrega do banco)
 *   underlying_security {string}
 *   fut_type        {string}  'WIN' | 'IND'
 *   tc_bps          {number}  Custo de transação round-trip em bps (padrão 10)
 *   dt_minutes      {number}  Intervalo de monitoramento em minutos (padrão 60)
 *   beta            {number}  SABR beta fixo (padrão 0.5)
 */
export function computeHedgeDelta(data = {}) {
  return requestWithRetry(() =>
    service({
      url: '/api/options/hedge/delta',
      method: 'post',
      data
    }),
  2, 1500)
}

export function getLiveSpot(underlying = 'IBOV') {
  return service({
    url: '/api/options/market/spot',
    method: 'get',
    params: { underlying, _ts: Date.now() }
  })
}

export function getLatestSnapshot(params = {}) {
  return service({
    url: '/api/options/snapshot/latest',
    method: 'get',
    params: withFreshParams(params)
  })
}

export function getSnapshotByStrike(params = {}) {
  const payload = { ...params }
  const forceRefresh = Boolean(payload.refresh)
  return sharedRequest({
    scope: 'snapshot-by-strike',
    payload,
    ttlMs: forceRefresh ? 0 : 10_000,
    forceRefresh,
    requestFn: () => requestWithRetry(() =>
      optionsModelService({
        url: '/api/options/snapshot/by-strike',
        method: 'get',
        params: withFreshParams(payload)
      }),
    1, 500),
  })
}

export function getB3OiLatest(params = {}) {
  const payload = { ...params }
  const forceRefresh = Boolean(payload.refresh)
  return sharedRequest({
    scope: 'b3-oi-latest',
    payload,
    ttlMs: forceRefresh ? 0 : 60_000,
    forceRefresh,
    requestFn: () => requestWithRetry(() =>
      optionsModelService({
        url: '/api/options/b3-oi/latest',
        method: 'get',
        params: withFreshParams(payload)
      }),
    1, 500),
  })
}

export function getB3OiDates() {
  return optionsModelService({
    url: '/api/options/b3-oi/dates',
    method: 'get',
    params: withFreshParams()
  })
}

export function getVolSurface(params = {}) {
  const payload = { ...params }
  const forceRefresh = Boolean(payload.refresh)
  return sharedRequest({
    scope: 'vol-surface',
    payload,
    ttlMs: forceRefresh ? 0 : 10_000,
    forceRefresh,
    requestFn: () => requestWithRetry(() =>
      optionsModelService({
        url: '/api/options/vol-surface',
        method: 'get',
        params: withFreshParams(payload)
      }),
    1, 500),
  })
}

export function getOptionsDiagnostics(params = {}) {
  return service({
    url: '/api/options/diagnostics',
    method: 'get',
    params: withFreshParams(params)
  })
}

// ─── Volatility Index ──────────────────────────────────────────────────────────

export function getVolIndexHistory(params = {}) {
  const payload = { ...params }
  const forceRefresh = Boolean(payload.refresh)
  return sharedRequest({
    scope: 'vol-index-history',
    payload,
    ttlMs: forceRefresh ? 0 : 15_000,
    forceRefresh,
    requestFn: () => requestWithRetry(() =>
      volAnalyticsService({
        url: '/api/options/vol-index/history',
        method: 'get',
        params: withFreshParams(payload)
      }),
    2, 1000),
  })
}

export function getVolIndexLatest(params = {}) {
  const payload = { ...params }
  const forceRefresh = Boolean(payload.refresh)
  return sharedRequest({
    scope: 'vol-index-latest',
    payload,
    ttlMs: forceRefresh ? 0 : 5_000,
    forceRefresh,
    requestFn: () => requestWithRetry(() =>
      volAnalyticsService({
        url: '/api/options/vol-index/latest',
        method: 'get',
        params: withFreshParams(payload)
      }),
    2, 1000),
  })
}

export function collectVolIndex(data = {}) {
  const payload = { ...data }
  const forceRefresh = Boolean(payload.force)
  return sharedRequest({
    scope: 'vol-index-collect',
    payload: { underlying: payload.underlying || 'IBOVE Index', force: forceRefresh },
    ttlMs: forceRefresh ? 0 : 45_000,
    forceRefresh,
    requestFn: async () => {
      const result = await requestWithRetry(() =>
        service({
          url: '/api/options/vol-index/collect',
          method: 'post',
          data: payload
        }),
      1, 2000)
      invalidateSharedCache(['vol-index-history:', 'vol-index-latest:'])
      return result
    },
  })
}

export function appendVolIndexPrice(data = {}) {
  return service({
    url: '/api/options/vol-index/price',
    method: 'post',
    data
  })
}

export function getLiveCaptureWorkbookSeries(params = {}) {
  const payload = { ...params }
  const forceRefresh = Boolean(payload.refresh)
  return sharedRequest({
    scope: 'live-capture-workbook-series',
    payload,
    ttlMs: forceRefresh ? 0 : 10_000,
    forceRefresh,
    requestFn: () => requestWithRetry(() =>
      volAnalyticsService({
        url: '/api/options/live-capture/workbook-series',
        method: 'get',
        params: withFreshParams(payload)
      }),
    2, 1000),
  })
}

export function getLiveCaptureWorkbookLatest(params = {}) {
  const payload = { ...params }
  const forceRefresh = Boolean(payload.refresh)
  return sharedRequest({
    scope: 'live-capture-workbook-latest',
    payload,
    ttlMs: forceRefresh ? 0 : 3_000,
    forceRefresh,
    requestFn: () => requestWithRetry(() =>
      volAnalyticsService({
        url: '/api/options/live-capture/workbook-latest',
        method: 'get',
        params: withFreshParams(payload)
      }),
    2, 1000),
  })
}

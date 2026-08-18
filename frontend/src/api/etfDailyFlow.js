import { etfDailyFlowService, requestWithRetry } from './index'

export function getEtfDailyFlowDashboard(params = {}) {
  const payload = { ...params, _ts: params._ts ?? Date.now() }
  return requestWithRetry(() =>
    etfDailyFlowService({
      url: '/api/v1/etf-daily-flow/dashboard',
      method: 'get',
      params: payload,
    }),
  1, 1200)
}

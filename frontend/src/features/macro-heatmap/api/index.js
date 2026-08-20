import service from '@/api'

export {
  getLatestIntradayCorrelationHistory,
  getLatestOptionsHeatmapContext,
  hardRefreshOptionsBase,
} from '@/api/options'

export function getParticipantHeatmap({ refresh = false } = {}) {
  return service({
    url: '/api/macro/participant-heatmap',
    method: 'get',
    params: {
      refresh,
      _ts: Date.now(),
    },
    timeout: 30000,
  })
}

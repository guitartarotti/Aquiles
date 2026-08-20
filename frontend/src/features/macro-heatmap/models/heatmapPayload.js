import { toNumber } from '../../../utils/marketFormatters.js'

export function normalizeHeatmapPayload(raw) {
  if (!raw || typeof raw !== 'object') return null
  if (Array.isArray(raw.assets)) return raw
  if (Array.isArray(raw?.data?.assets)) return raw.data
  if (raw.assets && typeof raw.assets === 'object') {
    return {
      ...raw,
      assets: Object.values(raw.assets),
    }
  }
  if (raw?.data?.assets && typeof raw.data.assets === 'object') {
    return {
      ...raw.data,
      assets: Object.values(raw.data.assets),
    }
  }
  return raw
}

export function buildOptionsContextFallbackPanel(context) {
  if (!context || typeof context !== 'object') return null
  const fairValueHistory = context.fair_value_history && typeof context.fair_value_history === 'object'
    ? structuredClone(context.fair_value_history)
    : {}
  const liveCaptureHistory = context.live_capture_history && typeof context.live_capture_history === 'object'
    ? structuredClone(context.live_capture_history)
    : {}
  const gammaContext = context.gamma_context && typeof context.gamma_context === 'object'
    ? structuredClone(context.gamma_context)
    : {}
  const sampleIntervalSeconds = toNumber(fairValueHistory.sample_interval_seconds)
    || toNumber(context.collector?.fair_value_interval_seconds)
    || 300
  const sampleCount = toNumber(fairValueHistory.samples_total)
    || (Array.isArray(fairValueHistory.samples) ? fairValueHistory.samples.length : 0)
    || 0
  const historyMinutes = sampleCount > 0
    ? Math.max(1, Math.round((sampleCount * sampleIntervalSeconds) / 60))
    : Math.max(1, Math.round(sampleIntervalSeconds / 60))

  return {
    generated_at: context.generated_at || fairValueHistory.latest_sample?.captured_at || null,
    sample_interval_seconds: sampleIntervalSeconds,
    history_minutes: historyMinutes,
    collector: {
      running: Boolean(context.collector?.running),
      sample_count: sampleCount,
    },
    assets: [
      {
        key: 'win',
        label: 'WIN',
        ticker: 'IBOVE Index',
        samples: [],
        participant_catalog: [],
        latest_participants: [],
        heat_points: [],
        gamma_context: gammaContext,
        fair_value_history: fairValueHistory,
        live_capture_history: liveCaptureHistory,
        options_flow_alignment: {},
      },
    ],
    options_heatmap_context: structuredClone(context),
  }
}

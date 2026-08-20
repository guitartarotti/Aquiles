import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildOptionsContextFallbackPanel,
  normalizeHeatmapPayload,
} from '../models/heatmapPayload.js'

test('normalizes nested and keyed asset payloads', () => {
  assert.equal(normalizeHeatmapPayload(null), null)
  assert.deepEqual(normalizeHeatmapPayload({ data: { assets: [{ key: 'win' }] } }), {
    assets: [{ key: 'win' }],
  })
  assert.deepEqual(normalizeHeatmapPayload({ assets: { win: { key: 'win' } } }).assets, [
    { key: 'win' },
  ])
})

test('builds an isolated fallback panel from options context', () => {
  const context = {
    generated_at: '2026-08-18T12:00:00Z',
    collector: { running: true, fair_value_interval_seconds: 60 },
    fair_value_history: {
      samples: [{ value: 1 }, { value: 2 }, { value: 3 }],
    },
    gamma_context: { regime: 'positive' },
  }

  const panel = buildOptionsContextFallbackPanel(context)

  assert.equal(panel.history_minutes, 3)
  assert.equal(panel.collector.sample_count, 3)
  assert.equal(panel.assets[0].gamma_context.regime, 'positive')
  panel.assets[0].gamma_context.regime = 'negative'
  assert.equal(context.gamma_context.regime, 'positive')
})

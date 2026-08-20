import assert from 'node:assert/strict'
import test from 'node:test'

import {
  arrangeDiscoveryGrid,
  getNextWidgetSequence,
  normalizeDiscoveryZStack,
  parseDiscoveryLayout,
  serializeDiscoveryLayout,
} from '../src/utils/discoveryLayout.js'
import {
  formatBytes,
  formatDays,
  formatMoney,
  formatPeriodDate,
  formatRatio,
  formatUsdMillions,
  ratioPercent,
} from '../src/features/funds-flow/models/formatters.js'
import {
  getSourceStatusClass,
  getSourceStatusLabel,
  hasPublicationGap,
} from '../src/features/funds-flow/models/sourceStatus.js'
import {
  buildNormalizedSeries,
  formatCurveMacroRegime,
  getCurveRegimeRanking,
} from '../src/features/macro-heatmap/models/macroCurve.js'
import {
  formatPrice,
  formatSignedBps,
  formatSignedQuantity,
  toNumber,
} from '../src/utils/marketFormatters.js'

test('market formatters reject missing or invalid values', () => {
  assert.equal(toNumber('invalid'), null)
  assert.equal(formatPrice(undefined), '--')
  assert.equal(formatSignedBps(null), '+0,0 bps')
})

test('market formatters preserve signs and financial units', () => {
  assert.match(formatSignedQuantity(1250), /^\+/)
  assert.match(formatSignedBps(-12.5), /^-/)
  assert.equal(formatMoney(-2_500_000), '-R$ 2.5 mi')
  assert.equal(formatUsdMillions(1_500), 'US$ 1.5 bi')
})

test('funds flow formatters preserve existing period conventions', () => {
  assert.equal(formatRatio(0.125), '12.50%')
  assert.equal(formatDays(8), '8.0d')
  assert.equal(formatDays(999), '999d+')
  assert.equal(formatBytes(1_048_576), '1.0 MB')
  assert.equal(formatPeriodDate('2026:Q2'), '2026:Q2')
  assert.equal(ratioPercent(25, 100), 25)
  assert.equal(ratioPercent(25, 0), null)
})

test('discovery layout round-trips only persisted widget state', () => {
  const raw = serializeDiscoveryLayout([
    { id: 'w7', type: 'pcr', x: 10, y: 20, w: 300, h: 200, z: 4, transient: true },
  ], 'WIN')
  const parsed = parseDiscoveryLayout(raw, widget => ({ ...widget, normalized: true }))

  assert.equal(parsed.underlying, 'WIN')
  assert.equal(parsed.widgets[0].transient, undefined)
  assert.equal(parsed.widgets[0].normalized, true)
  assert.equal(getNextWidgetSequence(parsed.widgets), 8)
})

test('discovery layout rejects corrupt state and arranges deterministic rows', () => {
  assert.equal(parseDiscoveryLayout('{broken'), null)
  const widgets = [
    { id: 'w2', w: 100, h: 80, z: 9 },
    { id: 'w1', w: 120, h: 60, z: 3 },
    { id: 'w3', w: 90, h: 50, z: 12 },
  ]

  assert.equal(normalizeDiscoveryZStack(widgets), 13)
  arrangeDiscoveryGrid(widgets, { columns: 2, gap: 10, start: 5 })
  assert.deepEqual(
    widgets.map(({ x, y, z }) => ({ x, y, z })),
    [
      { x: 5, y: 5, z: 1 },
      { x: 115, y: 5, z: 2 },
      { x: 5, y: 95, z: 3 },
    ],
  )
})

test('funds flow source status distinguishes publication gaps from failures', () => {
  const publicationGap = { latest_error: 'Sem linhas publicadas no intervalo consultado' }
  assert.equal(hasPublicationGap(publicationGap), true)
  assert.equal(getSourceStatusClass(publicationGap), 'warning')
  assert.equal(getSourceStatusLabel(publicationGap), 'sem publicacao')
  assert.equal(getSourceStatusClass({ error: 'timeout' }), 'error')
  assert.equal(getSourceStatusClass({ status: 'configured' }), 'configured')
})

test('macro curve helpers rank regimes and build deterministic chart coordinates', () => {
  const ranking = getCurveRegimeRanking({
    regime_probabilities: { fiscal: 20, desinflacionario: 65, misto: 15 },
  }, 2)
  assert.deepEqual(ranking.map(item => item.key), ['desinflacionario', 'fiscal'])
  assert.equal(formatCurveMacroRegime({ fiscal_risk_flag: true }), 'risco fiscal / duration')

  const series = buildNormalizedSeries(
    [{ tenor: 10, rate: 2 }, { tenor: 5, rate: 1 }],
    'rate',
    120,
    80,
    10,
    10,
  )
  assert.deepEqual(series.nodes.map(node => [node.tenor, node.x, node.y]), [
    [5, 10, 70],
    [10, 110, 10],
  ])
  assert.equal(series.path, 'M 10.00 70.00 L 110.00 10.00')
})

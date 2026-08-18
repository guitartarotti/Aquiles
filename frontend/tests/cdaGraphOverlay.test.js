import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildCdaGraphOverlay,
  countGraphEdgesByType,
  countGraphNodesByLabel,
  inferCdaAssetBucket,
  normalizeCdaKey,
} from '../src/utils/cdaGraphOverlay.js'
import { movementClass } from '../src/utils/fundsFlowFormatters.js'

test('CDA graph overlay adds lens nodes without mutating source data', () => {
  const graph = {
    month: '2026-07',
    nodes: [
      {
        uuid: 'asset-petr4',
        name: 'PETR4',
        labels: ['CdaAsset'],
        attributes: { asset_class: 'Ações' },
      },
    ],
    edges: [],
  }
  const trails = {
    asset_lenses: {
      buckets: [
        {
          bucket: 'equity',
          label: 'Ações',
          asset_count: 1,
          fund_count: 2,
          gross_value: 5_000_000,
          reported_activity: -100_000,
        },
      ],
      rows: [],
    },
  }

  const result = buildCdaGraphOverlay(graph, trails)
  const lens = result.nodes.find(node => node.labels.includes('CdaAssetLens'))
  const asset = result.nodes.find(node => node.uuid === 'asset-petr4')

  assert.equal(lens.name, 'Ações')
  assert.equal(lens.attributes.tone, 'down')
  assert.equal(asset.attributes.cluster_key, 'equity')
  assert.equal(graph.nodes[0].attributes.cluster_key, undefined)
  assert.equal(result.edges.some(edge => edge.fact_type === 'BELONGS_TO_ASSET_SEGMENT'), true)
})

test('CDA graph helpers normalize classifications and count contracts', () => {
  assert.equal(inferCdaAssetBucket({ asset_class: 'Ações' }, 'PETR4'), 'equity')
  assert.equal(inferCdaAssetBucket({ asset_class: 'Títulos Públicos' }, 'NTN-B'), 'public_bonds')
  assert.equal(normalizeCdaKey('  Crédito   Privado  '), 'credito privado')
  assert.deepEqual(
    countGraphNodesByLabel([
      { labels: ['Entity', 'Fund'] },
      { labels: ['Fund'] },
      { labels: ['Asset'] },
    ]),
    [{ label: 'Fund', count: 2 }, { label: 'Asset', count: 1 }],
  )
  assert.deepEqual(
    countGraphEdgesByType([
      { fact_type: 'HOLDS_POSITION' },
      { fact_type: 'HOLDS_POSITION' },
      { name: 'RELATED' },
    ]),
    [{ type: 'HOLDS_POSITION', count: 2 }, { type: 'RELATED', count: 1 }],
  )
})

test('movement class handles positive, negative, and neutral values', () => {
  assert.equal(movementClass(10), 'up')
  assert.equal(movementClass(-10), 'down')
  assert.equal(movementClass(0), 'flat')
  assert.equal(movementClass('invalid'), 'flat')
})

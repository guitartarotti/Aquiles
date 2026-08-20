import {
  formatCount as fmtCount,
  formatMoney as fmtMoney,
  movementClass as moveClass,
} from './formatters.js'

const cdaGraphOverlayLayout = {
  public_bonds: { x: 0.2, y: 0.2, radius: 118 },
  private_credit: { x: 0.34, y: 0.18, radius: 104 },
  fund_fixed_income: { x: 0.48, y: 0.2, radius: 100 },
  fund_quotas: { x: 0.35, y: 0.5, radius: 112 },
  fund_multimarket: { x: 0.5, y: 0.54, radius: 104 },
  fund_real_estate: { x: 0.66, y: 0.54, radius: 94 },
  equity: { x: 0.78, y: 0.28, radius: 116 },
  fund_equity: { x: 0.83, y: 0.48, radius: 88 },
  options_call: { x: 0.7, y: 0.76, radius: 86 },
  options_put: { x: 0.9, y: 0.76, radius: 86 },
  options_unknown: { x: 0.8, y: 0.9, radius: 78 },
  options_quadrant: { x: 0.8, y: 0.82, radius: 150 },
  portfolio_profiles: { x: 0.43, y: 0.84, radius: 138 },
  derivatives: { x: 0.58, y: 0.78, radius: 88 },
  foreign: { x: 0.17, y: 0.72, radius: 92 },
  fund_structured: { x: 0.23, y: 0.48, radius: 90 },
}
const cdaGraphOverlayFocus = [
  'public_bonds',
  'private_credit',
  'fund_fixed_income',
  'fund_quotas',
  'fund_multimarket',
  'fund_real_estate',
  'equity',
  'fund_equity',
  'options_call',
  'options_put',
  'options_unknown',
  'derivatives',
  'foreign',
  'fund_structured',
]

export function buildCdaGraphOverlay(graph, trails, fallbackMonth = 'latest') {
  const month = graph.month || fallbackMonth || 'latest'
  const nodes = (graph.nodes || []).map(node => ({
    ...node,
    attributes: { ...(node.attributes || {}) },
  }))
  const edges = (graph.edges || []).map(edge => ({
    ...edge,
    attributes: { ...(edge.attributes || {}) },
  }))
  const nodeMap = new Map(nodes.map(node => [node.uuid, node]))
  const edgeMap = new Map(edges.map(edge => [edge.uuid, edge]))
  const buckets = (trails.asset_lenses?.buckets || [])
    .filter(bucket => bucket.bucket && bucket.bucket !== 'all')
  const bucketByKey = new Map(buckets.map(bucket => [bucket.bucket, bucket]))
  const visibleBuckets = cdaGraphOverlayFocus
    .map(key => bucketByKey.get(key))
    .filter(Boolean)
  const lensRows = trails.asset_lenses?.rows || []
  const bucketNodes = new Map()

  visibleBuckets.forEach((bucket, index) => {
    const layout = cdaGraphOverlayLayout[bucket.bucket] || {
      x: 0.2 + (index % 5) * 0.15,
      y: 0.22 + Math.floor(index / 5) * 0.22,
      radius: 84,
    }
    const node = {
      uuid: cdaOverlayId('lens', month, bucket.bucket),
      name: bucket.label || bucket.bucket,
      labels: ['CdaAssetLens'],
      summary: `${bucket.label || bucket.bucket}: ${fmtCount(bucket.asset_count)} ativos, ${fmtCount(bucket.fund_count)} fundos, ${fmtMoney(bucket.gross_value)} gross.`,
      attributes: {
        bucket: bucket.bucket,
        asset_count: bucket.asset_count,
        fund_count: bucket.fund_count,
        gross_value: bucket.gross_value,
        reported_activity: bucket.reported_activity,
        cluster_key: bucket.bucket,
        cluster_x_ratio: layout.x,
        cluster_y_ratio: layout.y,
        cluster_radius: layout.radius,
        cluster_strength: 0.36,
        node_radius: 18,
        node_role: 'asset_lens',
        tone: moveClass(bucket.reported_activity),
      },
    }
    bucketNodes.set(bucket.bucket, node)
    upsertCdaGraphNode(nodeMap, nodes, node)
  })

  const assetIndex = buildCdaAssetNodeIndex(nodes)
  const rowCountByBucket = {}
  lensRows.forEach(row => {
    const bucket = row.bucket
    const bucketNode = bucketNodes.get(bucket)
    if (!bucketNode) return
    rowCountByBucket[bucket] = rowCountByBucket[bucket] || 0
    if (rowCountByBucket[bucket] >= 12) return
    rowCountByBucket[bucket] += 1
    const assetNode = ensureCdaOverlayAssetNode({
      row,
      month,
      bucketNode,
      assetIndex,
      nodeMap,
      nodes,
    })
    addCdaOverlaySegmentEdge({ edgeMap, edges, source: assetNode, target: bucketNode, row, month, synthetic: Boolean(assetNode.attributes?.overlay_asset) })
  })

  const edgeAssetBuckets = new Map()
  nodes.forEach(node => {
    if (!(node.labels || []).includes('CdaAsset')) return
    const bucket = inferCdaAssetBucket(node.attributes || {}, node.name)
    if (!bucket || !bucketNodes.has(bucket)) return
    const layout = cdaGraphOverlayLayout[bucket] || {}
    node.attributes.asset_bucket = bucket
    node.attributes.cluster_key = bucket
    node.attributes.cluster_x_ratio = layout.x
    node.attributes.cluster_y_ratio = layout.y
    node.attributes.cluster_radius = layout.radius
    node.attributes.cluster_strength = node.attributes.overlay_asset ? 0.22 : 0.14
    node.attributes.node_radius = node.attributes.overlay_asset ? 8 : 9
    edgeAssetBuckets.set(node.uuid, bucket)
    addCdaOverlaySegmentEdge({ edgeMap, edges, source: node, target: bucketNodes.get(bucket), row: node.attributes, month, synthetic: Boolean(node.attributes.overlay_asset) })
  })

  const fundBucketWeights = new Map()
  edges.forEach(edge => {
    if (edge.fact_type !== 'HOLDS_POSITION') return
    const bucket = edgeAssetBuckets.get(edge.target_node_uuid)
    if (!bucket) return
    const weight = Math.abs(Number(edge.attributes?.abs_value_market ?? edge.attributes?.value_market ?? 0))
    if (!weight) return
    const current = fundBucketWeights.get(edge.source_node_uuid) || {}
    current[bucket] = (current[bucket] || 0) + weight
    fundBucketWeights.set(edge.source_node_uuid, current)
  })
  fundBucketWeights.forEach((weights, fundUuid) => {
    const node = nodeMap.get(fundUuid)
    if (!node) return
    const mainBucket = Object.entries(weights).sort((a, b) => b[1] - a[1])[0]?.[0]
    const layout = cdaGraphOverlayLayout[mainBucket] || {}
    if (!mainBucket) return
    node.attributes.cluster_key = mainBucket
    node.attributes.cluster_x_ratio = layout.x
    node.attributes.cluster_y_ratio = layout.y
    node.attributes.cluster_strength = 0.045
  })

  addCdaParticipantOverlay({ month, trails, bucketNodes, nodeMap, edgeMap, nodes, edges })
  addCdaOptionTriangulationOverlay({ month, trails, bucketNodes, nodeMap, edgeMap, nodes, edges })
  addCdaPortfolioSimilarityOverlay({ month, trails, nodeMap, edgeMap, nodes, edges })

  return { nodes, edges }
}

export function countGraphNodesByLabel(nodes) {
  const counts = new Map()
  nodes.forEach(node => {
    const label = (node.labels || []).find(item => item !== 'Entity') || 'Entity'
    counts.set(label, (counts.get(label) || 0) + 1)
  })
  return [...counts.entries()]
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count)
}

export function countGraphEdgesByType(edges) {
  const counts = new Map()
  edges.forEach(edge => {
    const type = edge.fact_type || edge.name || 'RELATED'
    counts.set(type, (counts.get(type) || 0) + 1)
  })
  return [...counts.entries()]
    .map(([type, count]) => ({ type, count }))
    .sort((a, b) => b.count - a.count)
}

function addCdaParticipantOverlay({ month, trails, bucketNodes, nodeMap, edgeMap, nodes, edges }) {
  const participantRows = trails.participant_asset_coherence?.rows || []
  const participantTypes = [...new Set(participantRows.map(row => row.participant_type).filter(Boolean))]
  const yStep = participantTypes.length > 1 ? 0.62 / (participantTypes.length - 1) : 0
  participantTypes.forEach((participant, index) => {
    const participantRowsForType = participantRows.filter(row => row.participant_type === participant)
    const flow = participantRowsForType[0]?.participant_flow_21d_brl ?? 0
    const node = {
      uuid: cdaOverlayId('participant', month, participant),
      name: participant,
      labels: ['B3Participant'],
      summary: `${participant}: fluxo 21d B3 de ${fmtMoney(flow)}. Arestas conectam o participante aos segmentos CDA com atividade mensal coincidente ou divergente.`,
      attributes: {
        participant_type: participant,
        rolling_21d_net_flow_brl: flow,
        daily_net_flow_brl: participantRowsForType[0]?.participant_daily_flow_brl,
        cluster_key: 'b3_participants',
        cluster_x_ratio: 0.06,
        cluster_y_ratio: 0.2 + index * yStep,
        cluster_radius: 74,
        cluster_strength: 0.42,
        node_radius: 15,
        node_role: 'b3_participant',
        tone: moveClass(flow),
      },
    }
    upsertCdaGraphNode(nodeMap, nodes, node)
  })

  participantRows.slice(0, 26).forEach(row => {
    const bucketNode = bucketNodes.get(row.bucket)
    const participantNode = nodeMap.get(cdaOverlayId('participant', month, row.participant_type))
    if (!bucketNode || !participantNode) return
    const uuid = cdaOverlayId('participant-bucket', month, row.participant_type, row.bucket)
    const relationship = row.relationship || 'coerencia'
    const edge = {
      uuid,
      name: 'B3_FLOW_COHERENCE',
      fact_type: 'B3_FLOW_COHERENCE',
      fact: `${row.participant_type} tem fluxo 21d B3 de ${fmtMoney(row.participant_flow_21d_brl)} e ${row.bucket_label} teve atividade CDA de ${fmtMoney(row.bucket_activity)}; leitura ${relationship}, sem atribuicao causal.`,
      source_node_uuid: participantNode.uuid,
      target_node_uuid: bucketNode.uuid,
      source_node_name: participantNode.name,
      target_node_name: bucketNode.name,
      attributes: {
        participant_type: row.participant_type,
        bucket: row.bucket,
        bucket_label: row.bucket_label,
        relationship,
        participant_flow_21d_brl: row.participant_flow_21d_brl,
        bucket_activity: row.bucket_activity,
        bucket_gross_value: row.bucket_gross_value,
        sample_assets: row.sample_assets || [],
        tone: row.tone || moveClass(row.bucket_activity),
      },
      episodes: [],
    }
    upsertCdaGraphEdge(edgeMap, edges, edge)
  })
}

function addCdaOptionTriangulationOverlay({ month, trails, bucketNodes, nodeMap, edgeMap, nodes, edges }) {
  const optionTriangulation = trails.option_triangulation || {}
  const links = optionTriangulation.fund_option_equity_links || []
  const pairs = optionTriangulation.asset_pair_rows || []
  const underlyings = optionTriangulation.underlying_rows || []
  if (!links.length && !pairs.length && !underlyings.length) return

  const layout = cdaGraphOverlayLayout.options_quadrant
  const quadrantNode = {
    uuid: cdaOverlayId('option-quadrant', month),
    name: 'Triangulacao opcoes',
    labels: ['CdaOptionQuadrant'],
    summary: `Quadrante de opcoes: ${fmtCount(optionTriangulation.summary?.fund_option_equity_link_count)} ligacoes fundo-opcao-ativo-base e ${fmtCount(optionTriangulation.summary?.underlying_count)} subjacentes inferidos.`,
    attributes: {
      cluster_key: 'options_quadrant',
      cluster_x_ratio: layout.x,
      cluster_y_ratio: layout.y,
      cluster_radius: layout.radius,
      cluster_strength: 0.42,
      node_radius: 19,
      node_role: 'option_quadrant',
      link_count: optionTriangulation.summary?.fund_option_equity_link_count || 0,
      pair_count: optionTriangulation.summary?.pair_count || 0,
    },
  }
  upsertCdaGraphNode(nodeMap, nodes, quadrantNode)
  const fundIndex = buildCdaFundNodeIndex(nodes)
  const assetIndex = buildCdaAssetNodeIndex(nodes)
  const underlyingNodes = new Map()

  underlyings.slice(0, 14).forEach((row, index) => {
    const underlyingNode = ensureCdaUnderlyingNode({ row, index, month, nodeMap, nodes, underlyingNodes })
    addCdaTriangulationEdge({
      edgeMap,
      edges,
      month,
      source: underlyingNode,
      target: quadrantNode,
      type: 'OPTION_QUADRANT_MEMBER',
      fact: `${underlyingNode.name} pertence ao quadrante de opcoes com ${fmtMoney(row.option_gross_value)} em gross opcional e ${fmtCount(row.fund_count)} fundos.`,
      attributes: {
        underlying_key: row.underlying_key,
        option_gross_value: row.option_gross_value,
        equity_gross_value: row.equity_gross_value,
        coverage_ratio: row.coverage_ratio,
        tone: moveClass((row.holder_value || 0) - (row.written_value || 0)),
      },
    })
  })

  pairs.slice(0, 18).forEach(row => {
    const underlyingNode = ensureCdaUnderlyingNode({ row, month, nodeMap, nodes, underlyingNodes })
    const optionBucket = row.option_side === 'put' ? 'options_put' : row.option_side === 'call' ? 'options_call' : 'options_unknown'
    const optionNode = ensureCdaOverlayAssetNode({
      row: {
        ...row,
        asset_key: row.option_key,
        display_name: row.option_display || row.option_key,
        asset_desc: row.option_display,
        asset_class: 'Opcoes',
        bucket: optionBucket,
        bucket_label: optionBucket === 'options_put' ? 'Opcoes put' : optionBucket === 'options_call' ? 'Opcoes call' : 'Opcoes sem ticker',
        gross_value: row.option_gross_value,
        fund_count: row.shared_fund_count,
      },
      month,
      bucketNode: bucketNodes.get(optionBucket) || quadrantNode,
      assetIndex,
      nodeMap,
      nodes,
    })
    const equityNode = ensureCdaOverlayAssetNode({
      row: {
        ...row,
        asset_key: row.equity_key,
        display_name: row.equity_display || row.equity_key,
        asset_desc: row.equity_display,
        asset_class: 'Acoes',
        bucket: 'equity',
        bucket_label: 'Acoes/BDR',
        gross_value: row.equity_gross_value,
        fund_count: row.shared_fund_count,
      },
      month,
      bucketNode: bucketNodes.get('equity') || quadrantNode,
      assetIndex,
      nodeMap,
      nodes,
    })
    addCdaTriangulationEdge({
      edgeMap,
      edges,
      month,
      source: optionNode,
      target: underlyingNode,
      type: 'OPTION_ON_UNDERLYING',
      fact: `${optionNode.name} foi ligada ao subjacente inferido ${underlyingNode.name}.`,
      attributes: row,
    })
    addCdaTriangulationEdge({
      edgeMap,
      edges,
      month,
      source: equityNode,
      target: underlyingNode,
      type: 'EQUITY_UNDERLYING',
      fact: `${equityNode.name} representa a perna de acao/ETF associada ao subjacente ${underlyingNode.name}.`,
      attributes: row,
    })
    addCdaTriangulationEdge({
      edgeMap,
      edges,
      month,
      source: optionNode,
      target: equityNode,
      type: 'OPTION_EQUITY_TRIANGULATION',
      fact: `${optionNode.name} e ${equityNode.name} aparecem em ${fmtCount(row.shared_fund_count)} fundos no mesmo subjacente ${row.underlying_key}; leitura de triangulacao, nao causal.`,
      attributes: {
        ...row,
        gross_value: row.option_gross_value,
        tone: row.option_position_role === 'written' ? 'down' : 'up',
      },
    })
  })

  links.slice(0, 24).forEach(row => {
    const underlyingNode = ensureCdaUnderlyingNode({ row, month, nodeMap, nodes, underlyingNodes })
    const fundNode = ensureCdaOverlayFundNode({ row, month, fundIndex, nodeMap, nodes })
    const optionBucket = row.option_side === 'put' ? 'options_put' : row.option_side === 'call' ? 'options_call' : 'options_unknown'
    const optionNode = ensureCdaOverlayAssetNode({
      row: {
        ...row,
        asset_key: row.option_key,
        display_name: row.option_display || row.option_key,
        asset_desc: row.option_display,
        asset_class: 'Opcoes',
        bucket: optionBucket,
        bucket_label: optionBucket === 'options_put' ? 'Opcoes put' : optionBucket === 'options_call' ? 'Opcoes call' : 'Opcoes sem ticker',
        gross_value: row.option_gross_value,
        reported_activity: row.option_net_value,
      },
      month,
      bucketNode: bucketNodes.get(optionBucket) || quadrantNode,
      assetIndex,
      nodeMap,
      nodes,
    })
    const equityNode = ensureCdaOverlayAssetNode({
      row: {
        ...row,
        asset_key: row.equity_key,
        display_name: row.equity_display || row.equity_key,
        asset_desc: row.equity_display,
        asset_class: 'Acoes',
        bucket: 'equity',
        bucket_label: 'Acoes/BDR',
        gross_value: row.equity_gross_value,
        reported_activity: row.equity_net_value,
      },
      month,
      bucketNode: bucketNodes.get('equity') || quadrantNode,
      assetIndex,
      nodeMap,
      nodes,
    })
    ;[
      {
        source: fundNode,
        target: optionNode,
        type: 'OPTION_LEG',
        fact: `${fundNode.name} reportou perna de opcao ${optionNode.name} em ${fmtMoney(row.option_gross_value)}; posicao ${row.option_position_role || 'nao classificada'}.`,
        attributes: {
          ...row,
          gross_value: row.option_gross_value,
          net_value: row.option_net_value,
          side: row.option_position_role === 'written' ? 'short' : 'long',
        },
      },
      {
        source: fundNode,
        target: equityNode,
        type: 'EQUITY_LEG',
        fact: `${fundNode.name} tambem reportou perna de ativo-base ${equityNode.name} em ${fmtMoney(row.equity_gross_value)}.`,
        attributes: {
          ...row,
          gross_value: row.equity_gross_value,
          net_value: row.equity_net_value,
          side: Number(row.equity_net_value || 0) < 0 ? 'short' : 'long',
        },
      },
      {
        source: optionNode,
        target: underlyingNode,
        type: 'OPTION_ON_UNDERLYING',
        fact: `${optionNode.name} foi associada ao subjacente ${underlyingNode.name} por ticker/descricao.`,
        attributes: row,
      },
    ].forEach(edge => addCdaTriangulationEdge({ edgeMap, edges, month, ...edge }))
  })
}

function addCdaPortfolioSimilarityOverlay({ month, trails, nodeMap, edgeMap, nodes, edges }) {
  const similarity = trails.portfolio_similarity || {}
  const pairs = similarity.pairs || []
  const structures = similarity.structures || []
  const fundProfiles = similarity.fund_profiles || []
  if (!pairs.length && !structures.length && !fundProfiles.length) return

  const layout = cdaGraphOverlayLayout.portfolio_profiles
  const fundIndex = buildCdaFundNodeIndex(nodes)
  const profileNodes = new Map()

  structures.slice(0, 16).forEach((structure, index) => {
    const angle = (index / 16) * Math.PI * 2
    const node = {
      uuid: cdaOverlayId('portfolio-profile', month, structure.structure_key),
      name: structure.label || structure.structure_key,
      labels: ['CdaPortfolioProfile'],
      summary: `${structure.label}: ${fmtCount(structure.fund_count)} fundos com ${fmtMoney(structure.gross_value)} em gross perfilado.`,
      attributes: {
        ...structure,
        cluster_key: 'portfolio_profiles',
        cluster_x_ratio: layout.x + Math.cos(angle) * 0.055,
        cluster_y_ratio: layout.y + Math.sin(angle) * 0.05,
        cluster_radius: 100,
        cluster_strength: 0.36,
        node_radius: 14,
        node_role: 'portfolio_profile',
        tone: 'flat',
      },
    }
    profileNodes.set(structure.structure_key, node)
    upsertCdaGraphNode(nodeMap, nodes, node)
  })

  fundProfiles.slice(0, 42).forEach(profile => {
    const fundNode = ensureCdaPortfolioFundNode({ row: profile, month, fundIndex, nodeMap, nodes })
    ;(profile.structures || []).slice(0, 4).forEach(structure => {
      const profileNode = profileNodes.get(structure.structure_key)
      if (!profileNode) return
      upsertCdaGraphEdge(edgeMap, edges, {
        uuid: cdaOverlayId('fund-profile', month, fundNode.uuid, profileNode.uuid),
        name: 'HAS_PORTFOLIO_PROFILE',
        fact_type: 'HAS_PORTFOLIO_PROFILE',
        fact: `${fundNode.name} foi classificado como ${profileNode.name}; valor perfilado ${fmtMoney(structure.value)}.`,
        source_node_uuid: fundNode.uuid,
        target_node_uuid: profileNode.uuid,
        source_node_name: fundNode.name,
        target_node_name: profileNode.name,
        attributes: {
          ...structure,
          synthetic: true,
          gross_value: structure.value,
          similarity_score: structure.score,
          tone: 'flat',
        },
        episodes: [],
      })
    })
  })

  pairs.slice(0, 56).forEach(pair => {
    const left = ensureCdaPortfolioFundNode({
      row: { fund_cnpj: pair.fund_a_cnpj, fund_name: pair.fund_a, fund_type: pair.fund_a_type },
      month,
      fundIndex,
      nodeMap,
      nodes,
    })
    const right = ensureCdaPortfolioFundNode({
      row: { fund_cnpj: pair.fund_b_cnpj, fund_name: pair.fund_b, fund_type: pair.fund_b_type },
      month,
      fundIndex,
      nodeMap,
      nodes,
    })
    upsertCdaGraphEdge(edgeMap, edges, {
      uuid: cdaOverlayId('portfolio-similarity', month, left.uuid, right.uuid),
      name: 'PORTFOLIO_SIMILARITY',
      fact_type: 'PORTFOLIO_SIMILARITY',
      fact: pair.explanation || `${left.name} e ${right.name} possuem perfil de carteira semelhante.`,
      source_node_uuid: left.uuid,
      target_node_uuid: right.uuid,
      source_node_name: left.name,
      target_node_name: right.name,
      attributes: {
        ...pair,
        synthetic: true,
        similarity_score: pair.similarity_score,
        similarity_pct: pair.similarity_pct,
        tone: 'flat',
      },
      episodes: [],
    })
  })
}

function ensureCdaPortfolioFundNode({ row, month, fundIndex, nodeMap, nodes }) {
  const cnpj = normalizeCdaDigits(row?.fund_cnpj)
  const existingUuid = cnpj ? fundIndex.get(cnpj) : ''
  if (existingUuid && nodeMap.has(existingUuid)) return nodeMap.get(existingUuid)
  const layout = cdaGraphOverlayLayout.portfolio_profiles
  const node = {
    uuid: cdaOverlayId('portfolio-fund', month, cnpj || row?.fund_name),
    name: row?.fund_name || row?.fund_cnpj || 'Fundo perfilado',
    labels: ['CdaFund'],
    summary: `${row?.fund_name || row?.fund_cnpj}: fundo destacado por similaridade de perfil de carteira.`,
    attributes: {
      ...(row || {}),
      cnpj,
      fund_cnpj: row?.fund_cnpj,
      fund_type: row?.fund_type,
      overlay_fund: true,
      cluster_key: 'portfolio_profiles',
      cluster_x_ratio: layout.x,
      cluster_y_ratio: layout.y,
      cluster_radius: layout.radius,
      cluster_strength: 0.16,
      node_radius: 8,
      node_role: 'portfolio_fund',
    },
  }
  upsertCdaGraphNode(nodeMap, nodes, node)
  if (cnpj) fundIndex.set(cnpj, node.uuid)
  return node
}

function ensureCdaUnderlyingNode({ row, index = 0, month, nodeMap, nodes, underlyingNodes }) {
  const key = row?.underlying_key || 'UNDERLYING'
  const existing = underlyingNodes?.get(key)
  if (existing) return existing
  const layout = cdaGraphOverlayLayout.options_quadrant
  const angle = (index / 14) * Math.PI * 2
  const node = {
    uuid: cdaOverlayId('underlying', month, key),
    name: key,
    labels: ['CdaUnderlying'],
    summary: `${key}: subjacente inferido para triangulacao de opcoes, com ${fmtMoney(row?.option_gross_value)} em gross opcional quando disponivel.`,
    attributes: {
      ...(row || {}),
      underlying_key: key,
      cluster_key: 'options_quadrant',
      cluster_x_ratio: layout.x + Math.cos(angle) * 0.055,
      cluster_y_ratio: layout.y + Math.sin(angle) * 0.05,
      cluster_radius: 96,
      cluster_strength: 0.34,
      node_radius: 13,
      node_role: 'option_underlying',
    },
  }
  upsertCdaGraphNode(nodeMap, nodes, node)
  underlyingNodes?.set(key, node)
  return node
}

function ensureCdaOverlayFundNode({ row, month, fundIndex, nodeMap, nodes }) {
  const cnpj = normalizeCdaDigits(row?.fund_cnpj)
  const existingUuid = cnpj ? fundIndex.get(cnpj) : ''
  if (existingUuid && nodeMap.has(existingUuid)) return nodeMap.get(existingUuid)
  const layout = cdaGraphOverlayLayout.options_quadrant
  const node = {
    uuid: cdaOverlayId('option-fund', month, cnpj || row?.fund_name),
    name: row?.fund_name || row?.fund_cnpj || 'Fundo com opcao',
    labels: ['CdaFund'],
    summary: `${row?.fund_name || row?.fund_cnpj}: fundo destacado na triangulacao opcao/ativo-base.`,
    attributes: {
      cnpj,
      fund_cnpj: row?.fund_cnpj,
      fund_type: row?.fund_type,
      overlay_fund: true,
      cluster_key: 'options_quadrant',
      cluster_x_ratio: layout.x - 0.07,
      cluster_y_ratio: layout.y + 0.09,
      cluster_radius: 100,
      cluster_strength: 0.18,
      node_radius: 8,
      node_role: 'option_fund',
    },
  }
  upsertCdaGraphNode(nodeMap, nodes, node)
  if (cnpj) fundIndex.set(cnpj, node.uuid)
  return node
}

function addCdaTriangulationEdge({ edgeMap, edges, month, source, target, type, fact, attributes = {} }) {
  if (!source || !target) return
  const uuid = cdaOverlayId(type.toLowerCase(), month, source.uuid, target.uuid, attributes.option_key, attributes.equity_key)
  upsertCdaGraphEdge(edgeMap, edges, {
    uuid,
    name: type,
    fact_type: type,
    fact,
    source_node_uuid: source.uuid,
    target_node_uuid: target.uuid,
    source_node_name: source.name,
    target_node_name: target.name,
    attributes: {
      ...attributes,
      synthetic: true,
      tone: attributes.tone || moveClass(attributes.net_value || attributes.option_net_value || attributes.gross_value),
    },
    episodes: [],
  })
}

function ensureCdaOverlayAssetNode({ row, month, bucketNode, assetIndex, nodeMap, nodes }) {
  const keys = cdaAssetLookupKeys(row)
  const existingUuid = keys.map(key => assetIndex.get(key)).find(Boolean)
  if (existingUuid && nodeMap.has(existingUuid)) {
    const existing = nodeMap.get(existingUuid)
    existing.attributes = {
      ...(existing.attributes || {}),
      asset_bucket: row.bucket,
      bucket_label: row.bucket_label,
      fund_count: row.fund_count ?? existing.attributes?.fund_count,
      gross_value: row.gross_value ?? existing.attributes?.gross_value,
      reported_activity: row.reported_activity ?? existing.attributes?.reported_activity,
    }
    return existing
  }
  const layout = cdaGraphOverlayLayout[row.bucket] || {}
  const node = {
    uuid: cdaOverlayId('asset', month, row.bucket, row.asset_key || row.display_name),
    name: row.display_name || row.asset_key || bucketNode.name,
    labels: ['CdaAsset'],
    summary: `${row.display_name || row.asset_key}: ativo destacado em ${bucketNode.name}, ${fmtCount(row.fund_count)} fundos e ${fmtMoney(row.gross_value)} gross.`,
    attributes: {
      ...(row || {}),
      overlay_asset: true,
      asset_bucket: row.bucket,
      cluster_key: row.bucket,
      cluster_x_ratio: layout.x,
      cluster_y_ratio: layout.y,
      cluster_radius: layout.radius,
      cluster_strength: 0.22,
      node_radius: 8,
      node_role: 'overlay_asset',
    },
  }
  upsertCdaGraphNode(nodeMap, nodes, node)
  cdaAssetLookupKeys(row).forEach(key => assetIndex.set(key, node.uuid))
  return node
}

function addCdaOverlaySegmentEdge({ edgeMap, edges, source, target, row, month, synthetic }) {
  if (!source || !target) return
  const uuid = cdaOverlayId('asset-segment', month, source.uuid, target.uuid)
  const gross = row.gross_value ?? row.abs_value_market ?? row.value_market ?? row.long_value
  const edge = {
    uuid,
    name: 'BELONGS_TO_ASSET_SEGMENT',
    fact_type: 'BELONGS_TO_ASSET_SEGMENT',
    fact: `${source.name} foi agrupado na lente ${target.name}; gross ${fmtMoney(gross)} e ${fmtCount(row.fund_count)} fundos quando disponivel.`,
    source_node_uuid: source.uuid,
    target_node_uuid: target.uuid,
    source_node_name: source.name,
    target_node_name: target.name,
    attributes: {
      bucket: target.attributes?.bucket,
      bucket_label: target.name,
      gross_value: gross,
      fund_count: row.fund_count,
      reported_activity: row.reported_activity,
      synthetic,
      tone: moveClass(row.reported_activity),
    },
    episodes: [],
  }
  upsertCdaGraphEdge(edgeMap, edges, edge)
}

function upsertCdaGraphNode(nodeMap, nodes, node) {
  const existing = nodeMap.get(node.uuid)
  if (existing) {
    existing.attributes = { ...(existing.attributes || {}), ...(node.attributes || {}) }
    existing.summary = existing.summary || node.summary
    return existing
  }
  nodeMap.set(node.uuid, node)
  nodes.push(node)
  return node
}

function upsertCdaGraphEdge(edgeMap, edges, edge) {
  if (edgeMap.has(edge.uuid)) return edgeMap.get(edge.uuid)
  edgeMap.set(edge.uuid, edge)
  edges.push(edge)
  return edge
}

function buildCdaAssetNodeIndex(nodes) {
  const index = new Map()
  nodes.forEach(node => {
    if (!(node.labels || []).includes('CdaAsset')) return
    cdaAssetLookupKeys({
      asset_key: node.attributes?.security_key || node.attributes?.asset_code || node.name,
      asset_code: node.attributes?.asset_code,
      asset_desc: node.attributes?.asset_desc,
      issuer_name: node.attributes?.issuer_name,
      display_name: node.name,
    }).forEach(key => index.set(key, node.uuid))
  })
  return index
}

function buildCdaFundNodeIndex(nodes) {
  const index = new Map()
  nodes.forEach(node => {
    if (!(node.labels || []).includes('CdaFund')) return
    const cnpj = normalizeCdaDigits(node.attributes?.cnpj || node.attributes?.fund_cnpj || node.cnpj)
    if (cnpj) index.set(cnpj, node.uuid)
  })
  return index
}

function cdaAssetLookupKeys(row) {
  return [
    row?.asset_key,
    row?.asset_code,
    row?.security_key,
    row?.asset_desc,
    row?.issuer_name,
    row?.display_name,
  ]
    .map(value => normalizeCdaKey(value))
    .filter(Boolean)
}

export function inferCdaAssetBucket(attrs = {}, name = '') {
  const text = normalizeCdaText(`${attrs.asset_class || ''} ${attrs.asset_subclass || ''} ${attrs.asset_desc || ''} ${attrs.tp_ativo || ''} ${attrs.tp_aplic || ''} ${name}`)
  if (text.includes('opcao de compra') || text.includes('opcoes call') || text.includes('opcao call')) return 'options_call'
  if (text.includes('opcao de venda') || text.includes('opcoes put') || text.includes('opcao put')) return 'options_put'
  if (text.includes('opcao') || text.includes('opcoes')) return 'options_unknown'
  if (attrs.is_fund_quota) {
    if (text.includes('imobili') || text.includes(' fii')) return 'fund_real_estate'
    if (text.includes('fidc') || text.includes('fip') || text.includes('fiagro')) return 'fund_structured'
    if (text.includes('multimercado') || text.includes(' fim')) return 'fund_multimarket'
    if (text.includes('acoes') || text.includes('equity')) return 'fund_equity'
    if (text.includes('renda fixa') || text.includes('referenciado') || text.includes(' di ')) return 'fund_fixed_income'
    return 'fund_quotas'
  }
  if (attrs.is_derivative || text.includes('derivativo') || text.includes('swap')) return 'derivatives'
  if (attrs.is_foreign || text.includes('investimento exterior') || text.includes('exterior')) return 'foreign'
  if (text.includes('titulos publicos') || text.includes('titulo publico')) return 'public_bonds'
  if (text.includes('debenture') || text.includes('credito privado') || text.includes('letra financeira') || text.includes('cri') || text.includes('cra')) return 'private_credit'
  if (text.includes('deposito') || text.includes('disponibilidade')) return 'cash_if'
  if (text.includes('confidencial')) return 'confidential'
  if (text.includes('acoes') || text.includes('acao ') || text.includes('bdr') || text.includes('fundos de indice')) return 'equity'
  return ''
}

function normalizeCdaText(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
}

export function normalizeCdaKey(value) {
  return normalizeCdaText(value).replace(/\s+/g, ' ').trim()
}

function normalizeCdaDigits(value) {
  return String(value || '').replace(/\D+/g, '')
}

function cdaOverlayId(...parts) {
  return `cda:overlay:${stableCdaHash(parts.join('|'))}`
}

function stableCdaHash(value) {
  const text = String(value || '')
  let hash = 2166136261
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0).toString(16)
}

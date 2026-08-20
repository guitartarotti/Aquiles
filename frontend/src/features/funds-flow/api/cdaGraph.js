import { cdaGraphService, requestWithRetry } from '@/api'

export function getCdaGraphStatus() {
  return requestWithRetry(() =>
    cdaGraphService({
      url: '/api/v1/cda-graph/status',
      method: 'get'
    })
  )
}

export function getCdaGraphSchema() {
  return requestWithRetry(() =>
    cdaGraphService({
      url: '/api/v1/cda-graph/schema',
      method: 'get'
    })
  )
}

export function buildCdaGraph(payload = {}) {
  return requestWithRetry(() =>
    cdaGraphService({
      url: '/api/v1/cda-graph/build',
      method: 'post',
      data: payload
    })
  )
}

export function getCdaGraphNetwork(params = {}) {
  return requestWithRetry(() =>
    cdaGraphService({
      url: '/api/v1/cda-graph/network',
      method: 'get',
      params
    })
  )
}

export function getCdaFundGraphNetwork(fundCnpj, params = {}) {
  return requestWithRetry(() =>
    cdaGraphService({
      url: `/api/v1/cda-graph/fund/${encodeURIComponent(fundCnpj)}/network`,
      method: 'get',
      params
    })
  )
}

export function getCdaIssuerCrowding(params = {}) {
  return requestWithRetry(() =>
    cdaGraphService({
      url: '/api/v1/cda-graph/crowding/issuers',
      method: 'get',
      params
    })
  )
}

export function getCdaMoneyTrails(params = {}) {
  return requestWithRetry(() =>
    cdaGraphService({
      url: '/api/v1/cda-graph/money-trails',
      method: 'get',
      params
    })
  )
}

export function getCdaBridgePathDetail(params = {}) {
  return requestWithRetry(() =>
    cdaGraphService({
      url: '/api/v1/cda-graph/bridge-path-detail',
      method: 'get',
      params
    })
  )
}

export function getCdaAssetTrailDetail(params = {}) {
  return requestWithRetry(() =>
    cdaGraphService({
      url: '/api/v1/cda-graph/asset-trail-detail',
      method: 'get',
      params
    })
  )
}

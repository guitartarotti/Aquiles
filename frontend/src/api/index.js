import axios from 'axios'
import i18n from '../i18n'
import { clearAuthSession, getAccessToken } from '../auth/session'

function resolveServiceBaseUrl(explicitBaseUrl, port) {
  if (explicitBaseUrl) return explicitBaseUrl

  const protocol = typeof window === 'undefined' ? 'http:' : window.location.protocol || 'http:'
  const hostname = typeof window === 'undefined' ? 'localhost' : window.location.hostname || 'localhost'
  return `${protocol}//${hostname}:${port}`
}

export const resolveApiBaseUrl = () => resolveServiceBaseUrl(import.meta.env.VITE_API_BASE_URL, 5001)
export const resolveDiscoveryApiBaseUrl = () =>
  resolveServiceBaseUrl(import.meta.env.VITE_DISCOVERY_API_BASE_URL, 5012)
export const resolveVolAnalyticsApiBaseUrl = () =>
  resolveServiceBaseUrl(import.meta.env.VITE_VOL_ANALYTICS_API_BASE_URL, 5013)
export const resolveOptionsModelApiBaseUrl = () =>
  resolveServiceBaseUrl(import.meta.env.VITE_OPTIONS_MODEL_API_BASE_URL, 5014)
export const resolveOptionsVolumeTrackerApiBaseUrl = () =>
  resolveServiceBaseUrl(import.meta.env.VITE_OPTIONS_VOLUME_TRACKER_API_BASE_URL, 5015)
export const resolveFairValueMarkovApiBaseUrl = () =>
  resolveServiceBaseUrl(import.meta.env.VITE_FAIR_VALUE_MARKOV_API_BASE_URL, 5016)
export const resolveCdaGraphApiBaseUrl = () =>
  resolveServiceBaseUrl(import.meta.env.VITE_CVM_CDA_GRAPH_API_BASE_URL, 5017)
export const resolveEtfDailyFlowApiBaseUrl = () =>
  resolveServiceBaseUrl(import.meta.env.VITE_ETF_DAILY_FLOW_API_BASE_URL, 5018)
export const resolveAtemporalChartApiBaseUrl = () =>
  resolveServiceBaseUrl(import.meta.env.VITE_ATEMPORAL_CHART_API_BASE_URL, 5019)
export const resolveFlowReplicatorApiBaseUrl = () =>
  resolveServiceBaseUrl(import.meta.env.VITE_FLOW_REPLICATOR_API_BASE_URL, 5020)

function createApiClient(baseURL) {
  return axios.create({
    baseURL,
    timeout: 300000,
    headers: {
      'Content-Type': 'application/json'
    }
  })
}

function attachApiInterceptors(client) {
  client.interceptors.request.use(
    config => {
      config.headers['Accept-Language'] = i18n.global.locale.value
      const accessToken = getAccessToken()
      if (accessToken) {
        config.headers.Authorization = `Bearer ${accessToken}`
      }
      return config
    },
    error => {
      console.error('Request error:', error)
      return Promise.reject(error)
    }
  )

  client.interceptors.response.use(
    response => {
      const res = response.data

      if (!res.success && res.success !== undefined) {
        console.error('API Error:', res.error || res.message || 'Unknown error')
        return Promise.reject(new Error(res.error || res.message || 'Error'))
      }

      return res
    },
    error => {
      console.error('Response error:', error)

      if (error?.response?.status === 401 && !error?.config?.url?.endsWith('/api/auth/login')) {
        clearAuthSession()
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('aquiles:auth-required'))
        }
      }

      const backendMessage = error?.response?.data?.error || error?.response?.data?.message
      if (backendMessage) {
        error.message = backendMessage
      }
      
      if (error.code === 'ECONNABORTED' && error.message.includes('timeout')) {
        console.error('Request timeout')
      }

      if (error.message === 'Network Error') {
        console.error('Network error - please check your connection')
      }

      return Promise.reject(error)
    }
  )

  return client
}

const service = attachApiInterceptors(createApiClient(resolveApiBaseUrl()))

export const discoveryService = attachApiInterceptors(createApiClient(resolveDiscoveryApiBaseUrl()))

export const volAnalyticsService = attachApiInterceptors(createApiClient(resolveVolAnalyticsApiBaseUrl()))

export const optionsModelService = attachApiInterceptors(createApiClient(resolveOptionsModelApiBaseUrl()))

export const optionsVolumeTrackerService = attachApiInterceptors(createApiClient(resolveOptionsVolumeTrackerApiBaseUrl()))

export const fairValueMarkovService = attachApiInterceptors(createApiClient(resolveFairValueMarkovApiBaseUrl()))

export const atemporalChartService = attachApiInterceptors(createApiClient(resolveAtemporalChartApiBaseUrl()))

export const flowReplicatorService = attachApiInterceptors(createApiClient(resolveFlowReplicatorApiBaseUrl()))

export const cdaGraphService = attachApiInterceptors(createApiClient(resolveCdaGraphApiBaseUrl()))

export const etfDailyFlowService = attachApiInterceptors(createApiClient(resolveEtfDailyFlowApiBaseUrl()))

export const requestWithRetry = async (requestFn, maxRetries = 3, delay = 1000) => {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await requestFn()
    } catch (error) {
      if (i === maxRetries - 1) throw error

      console.warn(`Request failed, retrying (${i + 1}/${maxRetries})...`)
      await new Promise(resolve => setTimeout(resolve, delay * Math.pow(2, i)))
    }
  }
}

export default service

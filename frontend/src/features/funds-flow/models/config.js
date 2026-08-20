export const tabs = [
  { key: 'overview', label: 'Overview' },
  { key: 'b3', label: 'B3' },
  { key: 'etf', label: 'ETF' },
  { key: 'map', label: 'Mapa' },
  { key: 'stress', label: 'Stress' },
  { key: 'anbima', label: 'ANBIMA' },
  { key: 'global', label: 'ICI' },
  { key: 'cftc', label: 'CFTC' },
  { key: 'nport', label: 'N-Port' },
  { key: 'cda', label: 'CDA BR' },
  { key: 'radar_cda', label: 'Radar CDA' },
  { key: 'graph', label: 'Grafo' },
  { key: 'sources', label: 'Fontes' },
]

export const colors = ['#2dd4bf', '#60a5fa', '#facc15', '#fb7185', '#a78bfa', '#34d399', '#f97316', '#c084fc']
export const gridLines = [42, 86, 130, 174, 218]
export const b3FocusAssets = ['DI1', 'DDI', 'DOL', 'WDO', 'WIN']
export const b3AssetTabs = ['ALL', ...b3FocusAssets]
export const b3MonthOrder = Object.fromEntries([...('FGHJKMNQUVXZ')].map((code, index) => [code, index + 1]))
export const FUNDS_FLOW_HISTORY_DAYS = 30
export const nportTargets = [
  { key: 'brazil', label: 'Brasil' },
  { key: 'china', label: 'China/HK' },
  { key: 'emerging', label: 'Emergentes' },
]
export const nportSides = [
  { key: 'long', label: 'Comprados' },
  { key: 'short', label: 'Shorts' },
]
export const cdaTargets = [
  { key: 'foreign', label: 'Exterior' },
  { key: 'public_bonds', label: 'Tit. publicos' },
  { key: 'private_credit', label: 'Credito priv.' },
  { key: 'fund_quotas', label: 'Cotas fundos' },
  { key: 'equity', label: 'Acoes' },
  { key: 'derivatives', label: 'Derivativos' },
  { key: 'confidential', label: 'Confidencial' },
]
export const cdaSides = [
  { key: 'long', label: 'Comprados' },
  { key: 'short', label: 'Shorts' },
  { key: 'net', label: 'Liquido' },
]
export const cdaGraphTargets = [
  { key: 'all', label: 'Todos' },
  ...cdaTargets,
]
export const moneyFlowModes = [
  { key: 'mixed', label: 'Mixed', detail: 'CDA + N-PORT + ICI + B3 + CVM' },
  { key: 'quarterly', label: 'Trimestral', detail: 'CDA + N-PORT' },
  { key: 'daily_weekly', label: 'Semanal/diario', detail: 'ICI + B3 + CVM + ANBIMA' },
]

export function hasPublicationGap(source) {
  const message = String(source?.latest_error || source?.error || '').toLowerCase()
  return [
    'sem linhas publicadas',
    'candidate window',
    'intervalo consultado',
  ].some(fragment => message.includes(fragment))
}

export function getSourceStatusClass(source) {
  if (source?.ok || source?.status === 'active') return 'active'
  if (hasPublicationGap(source)) return 'warning'
  if (source?.latest_error || source?.error) return 'error'
  if (source?.status === 'configured' || source?.status === 'configured_not_loaded') return 'configured'
  return 'inactive'
}

export function getSourceStatusLabel(source) {
  const labels = {
    active: 'ativo',
    warning: 'sem publicacao',
    configured: 'configuravel',
    error: 'erro',
    inactive: 'inativo',
  }
  return labels[getSourceStatusClass(source)]
}

export function formatSourceCadence(value) {
  const labels = {
    daily_monthly_file: 'diario, arquivo mensal',
    daily_file: 'diario',
    daily_monthly: 'diario/mensal',
    daily_weekly: 'diario/semanal',
    weekly_quarterly: 'semanal/trimestral',
    daily: 'diario',
    monthly_daily_publication: 'mensal, publicado diariamente',
    weekly: 'semanal',
    weekly_tuesday_position_friday_release: 'semanal, posicao terca / release sexta',
  }
  return labels[value] || value || '-'
}

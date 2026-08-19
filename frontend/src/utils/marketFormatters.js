/** @param {unknown} value */
export function toNumber(value) {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

/** @param {unknown} value */
export function formatPrice(value) {
  const numeric = toNumber(value)
  if (numeric == null) return '--'
  const fractionDigits = Math.abs(numeric) >= 1000 ? 0 : 3
  return numeric.toLocaleString('pt-BR', {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  })
}

/** @param {unknown} value @param {boolean} [signed] */
export function formatSignedQuantity(value, signed = true) {
  const numeric = toNumber(value)
  if (numeric == null) return '--'
  return numeric.toLocaleString('pt-BR', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
    signDisplay: signed ? 'always' : 'never',
  })
}

/** @param {unknown} value */
export function formatSignedPoints(value) {
  const numeric = toNumber(value)
  if (numeric == null) return '--'
  const fractionDigits = Math.abs(numeric) >= 1000 ? 0 : 1
  return numeric.toLocaleString('pt-BR', {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
    signDisplay: 'always',
  })
}

/** @param {unknown} value */
export function formatSignedBps(value) {
  const numeric = toNumber(value)
  if (numeric == null) return '--'
  return `${numeric.toLocaleString('pt-BR', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
    signDisplay: 'always',
  })} bps`
}

/** @param {unknown} value */
export function formatPressureScore(value) {
  const numeric = toNumber(value)
  if (numeric == null) return '--'
  return numeric.toLocaleString('pt-BR', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
    signDisplay: 'always',
  })
}

/** @param {unknown} value */
export function formatCompactFloat(value) {
  const numeric = toNumber(value)
  if (numeric == null) return '--'
  return numeric.toLocaleString('pt-BR', {
    minimumFractionDigits: 1,
    maximumFractionDigits: Math.abs(numeric) >= 100 ? 1 : 2,
  })
}

/** @param {unknown} value @param {number} [digits] */
export function formatSignedFloat(value, digits = 1) {
  const numeric = toNumber(value)
  if (numeric == null) return '--'
  return numeric.toLocaleString('pt-BR', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    signDisplay: 'always',
  })
}

export const DISCOVERY_LAYOUT_STORAGE_KEY = 'discovery_layout_v3'

const persistedWidgetFields = ['id', 'type', 'icon', 'title', 'x', 'y', 'w', 'h', 'z']

export function serializeDiscoveryLayout(widgets, underlying) {
  const layout = widgets.map(widget => Object.fromEntries(
    persistedWidgetFields.map(field => [field, widget[field]]),
  ))
  return JSON.stringify({ widgets: layout, underlying })
}

export function parseDiscoveryLayout(raw, normalizeWidget = widget => widget) {
  if (!raw) return null
  try {
    const saved = JSON.parse(raw)
    if (!Array.isArray(saved?.widgets) || !saved.widgets.length) return null
    return {
      underlying: saved.underlying || null,
      widgets: saved.widgets.map(widget => normalizeWidget({ ...widget })),
    }
  } catch {
    return null
  }
}

export function getNextWidgetSequence(widgets, fallback = 1) {
  const sequences = widgets
    .map(widget => /^w(\d+)$/.exec(String(widget?.id || ''))?.[1])
    .map(Number)
    .filter(Number.isFinite)
  return sequences.length ? Math.max(...sequences) + 1 : fallback
}

export function normalizeDiscoveryZStack(widgets) {
  const ordered = [...widgets].sort((left, right) => {
    const zDifference = Number(left.z || 0) - Number(right.z || 0)
    return zDifference || String(left.id).localeCompare(String(right.id))
  })
  ordered.forEach((widget, index) => {
    widget.z = index + 1
  })
  return ordered.length + 10
}

export function arrangeDiscoveryGrid(widgets, { columns = 2, gap = 16, start = 16 } = {}) {
  let column = 0
  let rowHeight = 0
  let x = start
  let y = start

  widgets.forEach((widget, index) => {
    widget.x = x
    widget.y = y
    widget.z = index + 1
    rowHeight = Math.max(rowHeight, Number(widget.h) || 0)
    column += 1

    if (column >= columns) {
      column = 0
      x = start
      y += rowHeight + gap
      rowHeight = 0
    } else {
      x += (Number(widget.w) || 0) + gap
    }
  })
  return widgets
}

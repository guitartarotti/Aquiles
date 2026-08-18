import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const repoRoot = path.resolve(__dirname, '..', '..')
const widgetPath = path.join(repoRoot, 'frontend', 'src', 'components', 'discovery', 'widgets', 'VolatilityIgnitionDetectorWidget.vue')
const analysisDir = path.join(repoRoot, 'backend', 'uploads', 'analysis')

const sessionDate = process.argv[2] || '2026-05-22'
const underlying = process.argv[3] || 'IBOVE Index'

function readJsonl(filePath) {
  if (!fs.existsSync(filePath)) return []
  const text = fs.readFileSync(filePath, 'utf8')
  return text
    .split(/\r?\n/)
    .filter(Boolean)
    .map(line => {
      try {
        return JSON.parse(line)
      } catch {
        return null
      }
    })
    .filter(Boolean)
}

function extractScriptSetup(source) {
  const match = source.match(/<script setup>([\s\S]*?)<\/script>/)
  if (!match) throw new Error('Could not find <script setup> in VolatilityIgnitionDetectorWidget.vue')
  return match[1]
    .replace(/^import .*$/gm, '')
}

const propsObject = {
  modelData: {
    underlying_security: underlying,
    market_context: {},
    aggregates: {
      by_strike: [],
      totals: {},
    },
    pressure: {
      curve: [],
    },
    gamma_flip_history: {
      latest_flip_points: [],
    },
  },
  underlyingSecurity: underlying,
  refreshNonce: 0,
}

const localStorageMap = new Map()
const windowStub = {
  devicePixelRatio: 1,
  setTimeout,
  clearTimeout,
  localStorage: {
    getItem: key => localStorageMap.get(key) ?? null,
    setItem: (key, value) => localStorageMap.set(key, String(value)),
    removeItem: key => localStorageMap.delete(key),
  },
}

const vueStubs = {
  computed: fn => ({
    get value() {
      return fn()
    },
  }),
  ref: value => ({ value }),
  watch: () => {},
  onMounted: () => {},
  onUnmounted: () => {},
  nextTick: () => Promise.resolve(),
  defineProps: () => propsObject,
}

const script = extractScriptSetup(fs.readFileSync(widgetPath, 'utf8'))
const factory = new Function(
  'computed',
  'nextTick',
  'onMounted',
  'onUnmounted',
  'ref',
  'watch',
  'defineProps',
  'window',
  'getLiveCaptureWorkbookSeries',
  'getVolIndexHistory',
  'getVolumeActivity',
  `${script}
return {
  props,
  dailyHistory,
  intradayHistory,
  flowEvents,
  futurePriceHistory,
  spotPriceHistory,
  analytics,
  normalizeVolRecord,
  normalizeFlowEvent,
  normalizeWorkbookSeriesRecord,
}
`,
)

const engine = factory(
  vueStubs.computed,
  vueStubs.nextTick,
  vueStubs.onMounted,
  vueStubs.onUnmounted,
  vueStubs.ref,
  vueStubs.watch,
  vueStubs.defineProps,
  windowStub,
  async () => ({ data: { series: [] } }),
  async () => ({ data: {} }),
  async () => ({ data: { events: [] } }),
)

const ivRows = readJsonl(path.join(repoRoot, 'backend', 'uploads', 'options', 'volume', 'iv_history', `${sessionDate}.jsonl`))
const flowRows = readJsonl(path.join(repoRoot, 'backend', 'uploads', 'options', 'volume', 'activity', `${sessionDate}.jsonl`))
const archiveName = `${sessionDate}_${underlying.replace(/\s+/g, '_').toUpperCase()}.jsonl`
const archiveRows = readJsonl(path.join(repoRoot, 'backend', 'uploads', 'macro', 'live_capture_archive', archiveName))

engine.intradayHistory.value = ivRows
  .filter(row => String(row.session_date || '').slice(0, 10) === sessionDate)
  .map(engine.normalizeVolRecord)
  .filter(row => row._epoch != null)
  .sort((left, right) => left._epoch - right._epoch)

engine.flowEvents.value = flowRows
  .filter(row => String(row.session_date || '').slice(0, 10) === sessionDate)
  .map(engine.normalizeFlowEvent)
  .filter(row => row._epoch != null)
  .sort((left, right) => left._epoch - right._epoch)

engine.futurePriceHistory.value = archiveRows
  .filter(row => String(row.session_date || '').slice(0, 10) === sessionDate)
  .map(row => engine.normalizeWorkbookSeriesRecord({
    captured_at: row.captured_at,
    session_date: row.session_date,
    raw_value: row.current_future_price,
  }))
  .filter(row => row._epoch != null && row.raw_value != null)
  .sort((left, right) => left._epoch - right._epoch)

engine.spotPriceHistory.value = archiveRows
  .filter(row => String(row.session_date || '').slice(0, 10) === sessionDate)
  .map(row => engine.normalizeWorkbookSeriesRecord({
    captured_at: row.captured_at,
    session_date: row.session_date,
    raw_value: row.current_spot_price,
  }))
  .filter(row => row._epoch != null && row.raw_value != null)
  .sort((left, right) => left._epoch - right._epoch)

const snapshot = engine.analytics.value
if (!snapshot || !Array.isArray(snapshot.historySeries)) {
  throw new Error('Widget engine did not produce historySeries')
}

fs.mkdirSync(analysisDir, { recursive: true })
const outputBase = path.join(analysisDir, `vol_ignition_widget_engine_${sessionDate}`)
const csvPath = `${outputBase}.csv`
const jsonPath = `${outputBase}.json`

const csvColumns = [
  'epoch',
  'timestamp',
  'sessionDate',
  'axisLabel',
  'score',
  'surfaceShockScore',
  'transmissionScore',
  'confirmationProbability',
  'state',
  'signalRank',
  'signalKind',
  'signalLabel',
  'directionLabel',
  'triggerLabel',
]

const csvLines = [
  csvColumns.join(','),
  ...snapshot.historySeries.map(row => csvColumns
    .map(column => {
      const value = row[column]
      if (value == null) return ''
      const text = String(value)
      return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
    })
    .join(',')),
]
fs.writeFileSync(csvPath, `${csvLines.join('\n')}\n`, 'utf8')

const summary = {
  source: 'VolatilityIgnitionDetectorWidget.vue::<script setup>::analytics',
  widgetPath,
  sessionDate,
  underlying,
  csvPath,
  pointCount: snapshot.historySeries.length,
  latest: snapshot.historySeries.at(-1),
  countsByState: snapshot.historySeries.reduce((acc, row) => {
    acc[row.state] = (acc[row.state] || 0) + 1
    return acc
  }, {}),
  countsBySignalRank: snapshot.historySeries.reduce((acc, row) => {
    const key = String(row.signalRank ?? 0)
    acc[key] = (acc[key] || 0) + 1
    return acc
  }, {}),
  maxScore: snapshot.historySeries.reduce((best, row) => (row.score || 0) > (best.score || 0) ? row : best, snapshot.historySeries[0]),
}
fs.writeFileSync(jsonPath, JSON.stringify(summary, null, 2), 'utf8')
console.log(JSON.stringify(summary, null, 2))

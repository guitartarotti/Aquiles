<template>
  <div class="home-shell">
    <nav class="navbar">
      <div class="nav-brand-block">
        <AquilesBrand variant="nav" subtitle="PLATAFORMA QUANT" clickable @click="router.push('/')" />
        <div class="nav-subbrand">Live macro flow, trend detection, and scenario intelligence</div>
      </div>
      <div class="nav-links">
        <LanguageSwitcher />
        <a href="https://github.com/666ghj/MiroFish" target="_blank" class="github-link">
          {{ $t('nav.visitGithub') }} <span class="arrow">-&gt;</span>
        </a>
      </div>
    </nav>

    <div class="main-content">
      <section class="hero-section">
        <div class="hero-copy">
          <div class="tag-row">
            <span class="orange-tag">LIVE MACRO + QUANT SCENARIO LAB</span>
            <span class="version-text">/ macro desk build</span>
          </div>

          <h1 class="main-title">
            Aquiles
            <span class="gradient-text">Macro Data</span>
          </h1>

          <p class="hero-lead">
            Ingest impact news, participant concentration, five-minute price action, and book pressure into one macro board.
            Detect trends automatically, focus the right market narrative, and let synthetic agents debate probable buy, sell, or watch scenarios.
          </p>

          <div class="hero-feature-grid">
            <div v-for="feature in heroFeatures" :key="feature.title" class="hero-feature-card">
              <div class="hero-feature-label">{{ feature.label }}</div>
              <div class="hero-feature-title">{{ feature.title }}</div>
              <p class="hero-feature-desc">{{ feature.description }}</p>
            </div>
          </div>

          <div class="hero-story-strip">
            <div class="story-title">What the macro mode does</div>
            <div class="story-steps">
              <div v-for="step in storySteps" :key="step.index" class="story-step">
                <span class="story-index">{{ step.index }}</span>
                <div>
                  <div class="story-headline">{{ step.title }}</div>
                  <div class="story-text">{{ step.description }}</div>
                </div>
              </div>
            </div>
          </div>

          <div class="hero-cta-row">
            <button class="scroll-cta" @click="scrollToBottom">
              Open the macro control deck
            </button>
            <button class="scroll-cta options-cta" @click="openOptionsDashboard">
              Open the options dashboard
            </button>
            <button class="scroll-cta chart-cta" @click="openChartBoard">
              Open the live chart board
            </button>
            <button class="scroll-cta discovery-cta" @click="openDiscovery">
              Open Discovery
            </button>
          </div>
        </div>

        <div class="hero-visual">
          <div class="logo-stage">
            <div class="logo-halo"></div>
            <img :src="aquilesLogoPrimary" alt="Aquiles primary logo" class="hero-logo" />
          </div>

          <div class="quant-playout">
            <div class="playout-header">
              <div>
                <div class="playout-kicker">Quant Payout</div>
                <div class="playout-title">Ingestion to scenario forecast</div>
              </div>
              <div class="playout-badge">LIVE</div>
            </div>

            <div class="stream-stack">
              <div
                v-for="stream in ingestionStreams"
                :key="stream.name"
                class="stream-row"
                :style="{ '--lane-delay': stream.delay }"
              >
                <div class="stream-meta">
                  <span class="stream-name">{{ stream.name }}</span>
                  <span class="stream-status">{{ stream.status }}</span>
                </div>
                <div class="stream-track">
                  <div class="stream-track-label">{{ stream.flow }}</div>
                  <div class="stream-pulse"></div>
                </div>
              </div>
            </div>

            <div class="forecast-grid">
              <div
                v-for="card in forecastCards"
                :key="card.title"
                class="forecast-card"
                :class="card.tone"
                :style="{ '--float-delay': card.delay }"
              >
                <div class="forecast-top">
                  <span class="forecast-title">{{ card.title }}</span>
                  <span class="forecast-prob">{{ card.probability }}</span>
                </div>
                <div class="forecast-body">{{ card.body }}</div>
                <div class="forecast-foot">{{ card.foot }}</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="dashboard-section">
        <div class="left-panel">
          <div class="panel-header">
            <span class="status-dot">■</span> Macro Desk Status
          </div>

          <h2 class="section-title">Market context online</h2>
          <p class="section-desc">
            The macro workflow is ready to normalize live feeds, validate impact, create trends, and coordinate agent commentary around the strongest intraday scenarios.
          </p>

          <div class="metrics-row">
            <div v-for="metric in deskMetrics" :key="metric.label" class="metric-card">
              <div class="metric-value">{{ metric.value }}</div>
              <div class="metric-label">{{ metric.label }}</div>
            </div>
          </div>

          <div class="steps-container">
            <div class="steps-header">
              <span class="diamond-icon">◇</span> Macro workflow
            </div>
            <div class="workflow-list">
              <div v-for="step in workflowSteps" :key="step.index" class="workflow-item">
                <span class="step-num">{{ step.index }}</span>
                <div class="step-info">
                  <div class="step-title">{{ step.title }}</div>
                  <div class="step-desc">{{ step.description }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="right-panel">
          <div class="console-box">
            <div class="console-top-banner">
              <div>
                <div class="console-banner-kicker">Macro Data Launchpad</div>
                <div class="console-banner-title">Configure the feed basket and describe the scenario you want the desk to think through.</div>
              </div>
              <div class="console-banner-badge">Macro default</div>
            </div>

            <div class="console-section">
              <div class="console-header">
                <span class="console-label">{{ $t('home.inputModeLabel') }}</span>
                <span class="console-meta">
                  {{ inputMode === 'macro' ? $t('home.modeMacroMeta') : $t('home.modeDocumentsMeta') }}
                </span>
              </div>

              <div class="mode-switch">
                <button
                  class="mode-switch-btn"
                  :class="{ active: inputMode === 'documents' }"
                  @click="inputMode = 'documents'"
                  :disabled="loading"
                >
                  {{ $t('home.modeDocuments') }}
                </button>
                <button
                  class="mode-switch-btn"
                  :class="{ active: inputMode === 'macro' }"
                  @click="inputMode = 'macro'"
                  :disabled="loading"
                >
                  {{ $t('home.modeMacro') }}
                </button>
              </div>
            </div>

            <div class="console-section">
              <div class="console-header">
                <span class="console-label">
                  {{ inputMode === 'macro' ? $t('home.macroFeedsLabel') : $t('home.realitySeed') }}
                </span>
                <span class="console-meta">
                  {{ inputMode === 'macro' ? $t('home.macroFeedsMeta') : $t('home.supportedFormats') }}
                </span>
              </div>

              <div v-if="inputMode === 'documents'">
                <div
                  class="upload-zone"
                  :class="{ 'drag-over': isDragOver, 'has-files': files.length > 0 }"
                  @dragover.prevent="handleDragOver"
                  @dragleave.prevent="handleDragLeave"
                  @drop.prevent="handleDrop"
                  @click="triggerFileInput"
                >
                  <input
                    ref="fileInput"
                    type="file"
                    multiple
                    accept=".pdf,.md,.txt"
                    @change="handleFileSelect"
                    class="hidden-input"
                    :disabled="loading"
                  />

                  <div v-if="files.length === 0" class="upload-placeholder">
                    <div class="upload-icon">↑</div>
                    <div class="upload-title">{{ $t('home.dragToUpload') }}</div>
                    <div class="upload-hint">{{ $t('home.orBrowse') }}</div>
                  </div>

                  <div v-else class="file-list">
                    <div v-for="(file, index) in files" :key="index" class="file-item">
                      <span class="file-icon">FILE</span>
                      <span class="file-name">{{ file.name }}</span>
                      <button @click.stop="removeFile(index)" class="remove-btn">x</button>
                    </div>
                  </div>
                </div>
              </div>

              <div v-else class="macro-feed-card">
                <div class="macro-panel">
                  <div class="macro-panel-header">Live sources</div>
                  <div class="macro-panel-desc">
                    Macro mode listens to Bleu headlines and pulls AQuant participants, candles, books, and security headers before graph construction.
                  </div>
                  <div class="macro-pill-row">
                    <span v-for="pill in macroSourcePills" :key="pill" class="macro-pill">{{ pill }}</span>
                  </div>
                </div>

                <div class="macro-panel">
                  <div class="macro-panel-header">Tracked basket</div>
                  <div class="macro-panel-desc">
                    This basket powers the long-curve, short-curve, index, dollar, and equity lenses used by the trend engine.
                  </div>
                  <div class="macro-basket-grid">
                    <div class="macro-basket-item">
                      <span class="macro-basket-label">Index</span>
                      <span class="macro-basket-value">{{ macroPreset.index.join(', ') }}</span>
                    </div>
                    <div class="macro-basket-item">
                      <span class="macro-basket-label">Dollar</span>
                      <span class="macro-basket-value">{{ macroPreset.dollar.join(', ') }}</span>
                    </div>
                    <div class="macro-basket-item">
                      <span class="macro-basket-label">Short Curve</span>
                      <span class="macro-basket-value">{{ macroPreset.curveShort.join(', ') }}</span>
                    </div>
                    <div class="macro-basket-item">
                      <span class="macro-basket-label">Long Curve</span>
                      <span class="macro-basket-value">{{ macroPreset.curveLong.join(', ') }}</span>
                    </div>
                    <div class="macro-basket-item">
                      <span class="macro-basket-label">Equities</span>
                      <span class="macro-basket-value">{{ macroPreset.equities.join(', ') }}</span>
                    </div>
                    <div class="macro-basket-item">
                      <span class="macro-basket-label">Output</span>
                      <span class="macro-basket-value">Trends, agent comments, market overview, final scenario bias</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div class="console-divider">
              <span>{{ $t('home.inputParams') }}</span>
            </div>

            <div class="console-section">
              <div class="console-header">
                <span class="console-label">{{ $t('home.simulationPrompt') }}</span>
              </div>
              <div class="input-wrapper">
                <textarea
                  v-model="formData.simulationRequirement"
                  class="code-input"
                  placeholder="Describe the macro question, the trading scenario, or the market regime you want the system to analyze."
                  rows="6"
                  :disabled="loading"
                ></textarea>
                  <div class="model-badge">Engine: Aquiles Plataforma Quant</div>
              </div>
            </div>

            <div class="console-section btn-section">
              <button
                class="start-engine-btn"
                @click="startSimulation"
                :disabled="!canSubmit || loading"
              >
                <span v-if="!loading">Start Macro Engine</span>
                <span v-else>{{ $t('home.initializing') }}</span>
                <span class="btn-arrow">-&gt;</span>
              </button>
            </div>
          </div>
        </div>
      </section>

      <HistoryDatabase />
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import HistoryDatabase from '../components/HistoryDatabase.vue'
import AquilesBrand from '../components/AquilesBrand.vue'
import LanguageSwitcher from '../components/LanguageSwitcher.vue'
import aquilesLogoPrimary from '../assets/branding/aquiles-logo-primary.png'
import { setPendingUpload } from '../store/pendingUpload'

const router = useRouter()

const heroFeatures = [
  {
    label: 'Impact detection',
    title: 'From headline to tradeable trend',
    description: 'Validate whether a headline really matters for DI, index, dollar, or equities before turning it into a narrative.'
  },
  {
    label: 'Flow context',
    title: 'Participant concentration by asset',
    description: 'Read the distribution of participants per contract and use five-minute flow concentration as part of the market debate.'
  },
  {
    label: 'Scenario output',
    title: 'Agent discussion plus final macro bias',
    description: 'Focus one trend, read what hedge funds, macro traders, sell-side and retail personalities say, then summarize the probable path.'
  }
]

const storySteps = [
  { index: '01', title: 'Ingest live feeds', description: 'Bleu headlines, AQuant participants, OHLCV, book, and equity headers enter one normalized snapshot.' },
  { index: '02', title: 'Validate impact', description: 'Only macro-relevant news becomes a trend candidate after impact scoring and asset linkage.' },
  { index: '03', title: 'Build market context', description: 'Five-minute moves, participant concentration, and book imbalance frame the intraday tone.' },
  { index: '04', title: 'Let agents debate', description: 'Macro personas react to the selected trend instead of treating contracts and brokers as agents.' }
]

const deskMetrics = [
  { value: '5m', label: 'Intraday windows' },
  { value: 'Multi-asset', label: 'DI, WIN, DOL, equities' },
  { value: 'Trendboard', label: 'Focusable market narratives' }
]

const workflowSteps = [
  { index: '01', title: 'Collect', description: 'Listen to macro headlines and pull participants, candles, and book data from the tracked basket.' },
  { index: '02', title: 'Normalize', description: 'Transform the raw feed into snapshot state, impact links, market windows, and participant context.' },
  { index: '03', title: 'Detect', description: 'Create trends only when the system finds relevant price action, impactful news, or concentrated flow.' },
  { index: '04', title: 'Debate', description: 'Macro personas comment on the focused trend with different biases, motivations, and risk framing.' },
  { index: '05', title: 'Forecast', description: 'Summarize probable buy, sell, or watch scenarios with reasons, risks, and what to monitor next.' }
]

const ingestionStreams = [
  { name: 'BLEU NEWS', status: 'streaming', flow: 'headline -> impact validator -> trend seed', delay: '0s' },
  { name: 'AQUANT FLOW', status: 'syncing', flow: 'participants -> concentration score -> player tone', delay: '0.7s' },
  { name: 'AQUANT OHLCV', status: 'syncing', flow: 'candles -> 5m windows -> momentum state', delay: '1.4s' },
  { name: 'BOOK PRESSURE', status: 'parsing', flow: 'bid/ask -> imbalance -> scenario trigger', delay: '2.1s' }
]

const forecastCards = [
  { title: 'Bull Case', probability: '62%', body: 'Long curve and index remain aligned with constructive local risk tone.', foot: 'Trend support: flow + price + dollar relief', tone: 'buy', delay: '0s' },
  { title: 'Watch', probability: '25%', body: 'Constructive tone fades if volume cools and impact news stays weak.', foot: 'Trigger: weaker follow-through in the next windows', tone: 'watch', delay: '0.5s' },
  { title: 'Bear Case', probability: '13%', body: 'Reversal risk appears when concentrated flow loses sponsorship and the dollar snaps back.', foot: 'Trigger: news shock or failed momentum', tone: 'sell', delay: '1s' }
]

const macroSourcePills = [
  'Bleu WS / Breaking',
  'AQuant / Participants',
  'AQuant / OHLCV',
  'AQuant / Book',
  'AQuant / Equities'
]

const formData = ref({
  simulationRequirement: ''
})

const inputMode = ref('macro')
const macroPreset = {
  index: ['WINM26'],
  dollar: ['WDOK26'],
  curveShort: ['DI1F27', 'DI1F28'],
  curveLong: ['DI1F29', 'DI1F30', 'DI1F31', 'DI1F35'],
  equities: ['VALE3', 'PETR4', 'ITUB4', 'BPAC11', 'BBDC4']
}

const files = ref([])
const loading = ref(false)
const isDragOver = ref(false)
const fileInput = ref(null)

const canSubmit = computed(() => {
  if (formData.value.simulationRequirement.trim() === '') {
    return false
  }
  if (inputMode.value === 'macro') {
    return true
  }
  return files.value.length > 0
})

const triggerFileInput = () => {
  if (!loading.value) {
    fileInput.value?.click()
  }
}

const handleFileSelect = (event) => {
  const selectedFiles = Array.from(event.target.files)
  addFiles(selectedFiles)
}

const handleDragOver = () => {
  if (!loading.value) {
    isDragOver.value = true
  }
}

const handleDragLeave = () => {
  isDragOver.value = false
}

const handleDrop = (event) => {
  isDragOver.value = false
  if (loading.value) return
  const droppedFiles = Array.from(event.dataTransfer.files)
  addFiles(droppedFiles)
}

const addFiles = (newFiles) => {
  const validFiles = newFiles.filter((file) => {
    const ext = file.name.split('.').pop().toLowerCase()
    return ['pdf', 'md', 'txt'].includes(ext)
  })
  files.value.push(...validFiles)
}

const removeFile = (index) => {
  files.value.splice(index, 1)
}

const scrollToBottom = () => {
  window.scrollTo({
    top: document.body.scrollHeight,
    behavior: 'smooth'
  })
}

const openOptionsDashboard = () => {
  router.push({ name: 'OptionsDashboard' })
}

const openChartBoard = () => {
  router.push({ name: 'Chart' })
}

const openDiscovery = () => {
  router.push({ name: 'Discovery' })
}

const startSimulation = () => {
  if (!canSubmit.value || loading.value) return

  setPendingUpload(files.value, formData.value.simulationRequirement, {
    inputMode: inputMode.value
  })

  router.push({
    name: 'Process',
    params: { projectId: 'new' }
  })
}
</script>

<style scoped>
.home-shell {
  --black: #07090d;
  --ink: #151922;
  --white: #fcfcfd;
  --orange: #8793a5;
  --orange-soft: #dce2eb;
  --sand: #eef2f7;
  --paper: #f7f9fc;
  --border: #d8dee8;
  --gray-text: #586272;
  --font-mono: 'JetBrains Mono', monospace;
  --font-sans: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
  min-height: 100vh;
  background:
    radial-gradient(circle at top right, rgba(191, 201, 214, 0.22), transparent 30%),
    radial-gradient(circle at left top, rgba(120, 134, 153, 0.10), transparent 22%),
    linear-gradient(180deg, #fbfcfd 0%, #eef2f7 100%);
  color: var(--ink);
  font-family: var(--font-sans);
}

.navbar {
  min-height: 72px;
  padding: 18px 40px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: linear-gradient(180deg, rgba(10, 12, 16, 0.98) 0%, rgba(6, 8, 11, 0.98) 100%);
  color: #fff;
  border-bottom: 1px solid rgba(205, 213, 225, 0.12);
  box-shadow: 0 16px 30px rgba(7, 9, 13, 0.24);
}

.nav-brand-block {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.nav-subbrand {
  font-size: 0.78rem;
  color: rgba(214, 222, 232, 0.72);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.nav-links {
  display: flex;
  align-items: center;
  gap: 16px;
}

.github-link {
  color: #eef2f7;
  text-decoration: none;
  font-family: var(--font-mono);
  font-size: 0.82rem;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.github-link:hover {
  opacity: 0.82;
}

.main-content {
  max-width: 1440px;
  margin: 0 auto;
  padding: 42px 40px 72px;
}

.hero-section {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(420px, 0.95fr);
  gap: 40px;
  align-items: start;
  margin-bottom: 64px;
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  align-items: center;
  margin-bottom: 22px;
  font-family: var(--font-mono);
}

.orange-tag {
  background: linear-gradient(135deg, #10151c 0%, #202833 100%);
  color: #f7f9fc;
  border: 1px solid rgba(205, 213, 225, 0.16);
  padding: 6px 12px;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.12em;
}

.version-text {
  color: #798395;
  font-size: 0.78rem;
  letter-spacing: 0.06em;
}

.main-title {
  margin: 0 0 20px;
  font-size: 5.2rem;
  line-height: 0.96;
  letter-spacing: -0.06em;
  font-weight: 700;
}

.gradient-text {
  display: block;
  background: linear-gradient(135deg, #12161d 0%, #d9e0ea 42%, #687383 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.hero-lead {
  max-width: 700px;
  font-size: 1.08rem;
  line-height: 1.9;
  color: var(--gray-text);
  margin-bottom: 26px;
}

.hero-feature-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 24px;
}

.hero-feature-card {
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(10px);
  padding: 18px;
  min-height: 188px;
  box-shadow: 0 18px 36px rgba(17, 24, 39, 0.05);
}

.hero-feature-label {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  letter-spacing: 0.12em;
  color: #697588;
  text-transform: uppercase;
  margin-bottom: 10px;
}

.hero-feature-title {
  font-size: 1.02rem;
  font-weight: 700;
  margin-bottom: 10px;
}

.hero-feature-desc {
  font-size: 0.9rem;
  line-height: 1.65;
  color: var(--gray-text);
}

.hero-story-strip {
  border: 1px solid var(--border);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.94) 0%, rgba(240, 244, 249, 0.94) 100%);
  padding: 20px;
  margin-bottom: 24px;
  box-shadow: 0 18px 36px rgba(17, 24, 39, 0.05);
}

.story-title {
  font-family: var(--font-mono);
  font-size: 0.76rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: #788293;
  margin-bottom: 14px;
}

.story-steps {
  display: grid;
  gap: 12px;
}

.story-step {
  display: grid;
  grid-template-columns: 52px minmax(0, 1fr);
  gap: 12px;
  align-items: start;
}

.story-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  background: linear-gradient(180deg, #141922 0%, #090b10 100%);
  color: #f6f8fb;
  font-family: var(--font-mono);
  font-size: 0.82rem;
  font-weight: 800;
  border: 1px solid rgba(205, 213, 225, 0.12);
}

.story-headline {
  font-size: 0.95rem;
  font-weight: 700;
  margin-bottom: 4px;
}

.story-text {
  font-size: 0.88rem;
  color: var(--gray-text);
  line-height: 1.6;
}

.scroll-cta {
  border: none;
  background: #111;
  color: #fff;
  padding: 14px 18px;
  font-family: var(--font-mono);
  font-size: 0.82rem;
  font-weight: 700;
  cursor: pointer;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.hero-cta-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.scroll-cta:hover {
  background: #2a3340;
}

.options-cta {
  background: #e7edf5;
  color: #171b22;
  border: 1px solid #c7d0dc;
}

.chart-cta {
  background: rgba(15, 118, 110, 0.08);
  color: #0d9488;
  border: 1px solid rgba(15, 118, 110, 0.35);
}
.chart-cta:hover {
  background: rgba(15, 118, 110, 0.16);
  border-color: rgba(15, 118, 110, 0.6);
}

.discovery-cta {
  background: rgba(99, 102, 241, 0.08);
  color: #6366f1;
  border: 1px solid rgba(99, 102, 241, 0.35);
}
.discovery-cta:hover {
  background: rgba(99, 102, 241, 0.16);
  border-color: rgba(99, 102, 241, 0.6);
}

.hero-visual {
  position: relative;
  display: grid;
  gap: 18px;
}

.logo-stage {
  position: relative;
  overflow: hidden;
  min-height: 280px;
  padding: 18px 26px 0;
  border: 1px solid rgba(205, 213, 225, 0.14);
  background:
    radial-gradient(circle at 60% 18%, rgba(220, 228, 238, 0.16), transparent 24%),
    linear-gradient(180deg, #10141b 0%, #050608 100%);
  box-shadow: 0 28px 60px rgba(7, 9, 13, 0.22);
}

.logo-halo {
  position: absolute;
  right: 42px;
  top: 36px;
  width: 180px;
  height: 180px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(220, 228, 238, 0.28) 0%, rgba(220, 228, 238, 0.06) 58%, transparent 74%);
  animation: pulseHalo 5s ease-in-out infinite;
}

.hero-logo {
  position: relative;
  width: min(100%, 540px);
  display: block;
  margin-left: auto;
  z-index: 1;
}

.quant-playout {
  border: 1px solid rgba(205, 213, 225, 0.12);
  background: linear-gradient(180deg, #171717 0%, #0d0d0d 100%);
  color: #fff;
  padding: 18px;
  overflow: hidden;
  position: relative;
}

.quant-playout::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.04) 1px, transparent 1px);
  background-size: 28px 28px;
  pointer-events: none;
}

.playout-header,
.stream-stack,
.forecast-grid {
  position: relative;
  z-index: 1;
}

.playout-header {
  display: flex;
  justify-content: space-between;
  align-items: start;
  gap: 16px;
  margin-bottom: 18px;
}

.playout-kicker {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  color: var(--orange-soft);
  text-transform: uppercase;
  letter-spacing: 0.12em;
  margin-bottom: 8px;
}

.playout-title {
  font-size: 1.2rem;
  font-weight: 700;
}

.playout-badge {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  color: #10141b;
  background: #e4eaf3;
  padding: 6px 10px;
  font-weight: 800;
}

.stream-stack {
  display: grid;
  gap: 12px;
  margin-bottom: 18px;
}

.stream-row {
  display: grid;
  gap: 8px;
}

.stream-meta {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-family: var(--font-mono);
  font-size: 0.74rem;
}

.stream-name {
  color: #fff;
  letter-spacing: 0.08em;
}

.stream-status {
  color: #d4dbe6;
  text-transform: uppercase;
}

.stream-track {
  position: relative;
  border: 1px solid rgba(255, 255, 255, 0.12);
  min-height: 48px;
  display: flex;
  align-items: center;
  padding: 0 14px;
  background: rgba(255, 255, 255, 0.04);
  overflow: hidden;
}

.stream-track-label {
  position: relative;
  z-index: 1;
  font-size: 0.84rem;
  color: #dad4cb;
}

.stream-pulse {
  position: absolute;
  top: 50%;
  left: -18%;
  width: 36%;
  height: 14px;
  transform: translateY(-50%);
  border-radius: 999px;
  background: linear-gradient(90deg, transparent 0%, rgba(213, 221, 232, 0.78) 54%, transparent 100%);
  filter: blur(2px);
  animation: streamPulse 4.8s linear infinite;
  animation-delay: var(--lane-delay);
}

.forecast-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.forecast-card {
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.05);
  padding: 14px;
  min-height: 154px;
  animation: floatCard 4.5s ease-in-out infinite;
  animation-delay: var(--float-delay);
}

.forecast-card.buy {
  border-color: rgba(117, 212, 150, 0.45);
}

.forecast-card.watch {
  border-color: rgba(255, 194, 92, 0.45);
}

.forecast-card.sell {
  border-color: rgba(255, 129, 129, 0.45);
}

.forecast-top {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: baseline;
  margin-bottom: 10px;
}

.forecast-title {
  font-weight: 700;
}

.forecast-prob {
  font-family: var(--font-mono);
  color: #e0e6ef;
}

.forecast-body,
.forecast-foot {
  font-size: 0.82rem;
  line-height: 1.6;
}

.forecast-body {
  color: #e4ddd3;
  margin-bottom: 10px;
}

.forecast-foot {
  color: #9f978d;
}

.dashboard-section {
  display: grid;
  grid-template-columns: minmax(320px, 0.9fr) minmax(0, 1.1fr);
  gap: 36px;
  border-top: 1px solid var(--border);
  padding-top: 42px;
  margin-bottom: 52px;
}

.left-panel,
.right-panel {
  display: flex;
  flex-direction: column;
}

.panel-header,
.steps-header,
.console-header,
.macro-panel-header,
.console-label,
.console-meta,
.macro-basket-label,
.upload-hint,
.model-badge,
.nav-brand {
  font-family: var(--font-mono);
}

.panel-header {
  font-size: 0.78rem;
  color: #726d66;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.status-dot {
  color: #8f9aab;
}

.section-title {
  font-size: 2.2rem;
  margin-bottom: 10px;
  font-weight: 700;
}

.section-desc {
  font-size: 0.96rem;
  color: var(--gray-text);
  line-height: 1.7;
  margin-bottom: 18px;
}

.metrics-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 18px;
}

.metric-card {
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.76);
  padding: 16px;
}

.metric-value {
  font-size: 1.2rem;
  font-weight: 700;
  margin-bottom: 6px;
}

.metric-label {
  font-size: 0.82rem;
  color: #716b64;
}

.steps-container {
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.78);
  padding: 22px;
}

.steps-header {
  font-size: 0.78rem;
  color: #7a746c;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  margin-bottom: 18px;
  display: flex;
  gap: 8px;
  align-items: center;
}

.workflow-list {
  display: grid;
  gap: 16px;
}

.workflow-item {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr);
  gap: 12px;
}

.step-num {
  font-family: var(--font-mono);
  font-size: 0.92rem;
  font-weight: 800;
  color: #727d8d;
}

.step-title {
  font-size: 0.95rem;
  font-weight: 700;
  margin-bottom: 4px;
}

.step-desc {
  font-size: 0.85rem;
  color: var(--gray-text);
  line-height: 1.6;
}

.console-box {
  border: 1px solid #1a1a1a;
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(10px);
  padding: 8px;
}

.console-top-banner {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  padding: 18px 20px 10px;
}

.console-banner-kicker {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: #667487;
  margin-bottom: 8px;
}

.console-banner-title {
  font-size: 1.02rem;
  font-weight: 700;
  line-height: 1.5;
  max-width: 620px;
}

.console-banner-badge {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  text-transform: uppercase;
  background: #111;
  color: #fff;
  padding: 7px 10px;
}

.console-section {
  padding: 18px 20px;
}

.console-section.btn-section {
  padding-top: 0;
}

.console-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
  font-size: 0.74rem;
  color: #5f5952;
}

.mode-switch {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.mode-switch-btn {
  border: 1px solid var(--border);
  background: #fff;
  color: #111;
  font-family: var(--font-mono);
  font-size: 0.8rem;
  font-weight: 700;
  padding: 12px 14px;
  cursor: pointer;
}

.mode-switch-btn.active {
  background: #111;
  color: #fff;
  border-color: #111;
}

.mode-switch-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.macro-feed-card {
  display: grid;
  gap: 14px;
}

.macro-panel {
  border: 1px solid var(--border);
  background: linear-gradient(180deg, #fff 0%, #f5efe2 100%);
  padding: 16px;
}

.macro-panel-header {
  font-size: 0.76rem;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  margin-bottom: 8px;
}

.macro-panel-desc {
  font-size: 0.9rem;
  line-height: 1.6;
  color: var(--gray-text);
  margin-bottom: 12px;
}

.macro-pill-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.macro-pill {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  background: linear-gradient(180deg, #161b22 0%, #0a0d11 100%);
  color: #f7f9fc;
  font-family: var(--font-mono);
  font-size: 0.72rem;
  letter-spacing: 0.04em;
}

.macro-basket-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.macro-basket-item {
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.92);
  padding: 12px;
  min-height: 92px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  justify-content: space-between;
}

.macro-basket-label {
  font-size: 0.72rem;
  color: #7c756c;
  text-transform: uppercase;
  letter-spacing: 0.12em;
}

.macro-basket-value {
  font-size: 0.92rem;
  line-height: 1.5;
  font-weight: 700;
  word-break: break-word;
}

.upload-zone {
  border: 1px dashed var(--border);
  min-height: 220px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f8f4eb;
  cursor: pointer;
  transition: all 0.2s ease;
  overflow-y: auto;
}

.upload-zone:hover,
.upload-zone.drag-over {
  border-color: #a0abba;
  background: #f3f7fb;
}

.upload-zone.has-files {
  align-items: flex-start;
}

.hidden-input {
  display: none;
}

.upload-placeholder {
  text-align: center;
}

.upload-icon {
  width: 48px;
  height: 48px;
  border: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 15px;
  color: #7e8999;
  font-family: var(--font-mono);
}

.upload-title {
  font-size: 0.94rem;
  font-weight: 700;
  margin-bottom: 5px;
}

.upload-hint {
  font-size: 0.75rem;
  color: #827c75;
}

.file-list {
  width: 100%;
  padding: 14px;
  display: grid;
  gap: 10px;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--border);
  background: #fff;
  padding: 10px 12px;
  font-family: var(--font-mono);
  font-size: 0.82rem;
}

.file-icon {
  font-size: 0.72rem;
  color: #7e8999;
}

.file-name {
  flex: 1;
}

.remove-btn {
  border: none;
  background: none;
  color: #807970;
  font-size: 1rem;
  cursor: pointer;
}

.console-divider {
  display: flex;
  align-items: center;
  margin: 4px 0;
}

.console-divider::before,
.console-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border);
}

.console-divider span {
  padding: 0 15px;
  font-family: var(--font-mono);
  font-size: 0.72rem;
  color: #8a837a;
  letter-spacing: 0.12em;
}

.input-wrapper {
  position: relative;
  border: 1px solid var(--border);
  background: #fbf7ee;
}

.code-input {
  width: 100%;
  min-height: 170px;
  border: none;
  background: transparent;
  padding: 18px 18px 32px;
  font-family: var(--font-mono);
  font-size: 0.88rem;
  line-height: 1.7;
  resize: vertical;
  outline: none;
}

.model-badge {
  position: absolute;
  right: 14px;
  bottom: 12px;
  font-size: 0.7rem;
  color: #8d857c;
}

.start-engine-btn {
  width: 100%;
  border: 1px solid #111;
  background: #111;
  color: #fff;
  padding: 18px 20px;
  font-family: var(--font-mono);
  font-size: 0.98rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  animation: pulseBorder 2s infinite;
}

.start-engine-btn:hover:not(:disabled) {
  background: #29313d;
  border-color: #29313d;
  transform: translateY(-1px);
}

.start-engine-btn:disabled {
  background: #d9d2c7;
  border-color: #d9d2c7;
  color: #8d857a;
  cursor: not-allowed;
  animation: none;
}

.btn-arrow,
.arrow {
  font-family: var(--font-mono);
}

@keyframes streamPulse {
  0% {
    left: -22%;
  }
  100% {
    left: 112%;
  }
}

@keyframes floatCard {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-5px);
  }
}

@keyframes pulseHalo {
  0%,
  100% {
    transform: scale(0.96);
    opacity: 0.8;
  }
  50% {
    transform: scale(1.06);
    opacity: 1;
  }
}

@keyframes pulseBorder {
  0% {
    box-shadow: 0 0 0 0 rgba(16, 16, 16, 0.18);
  }
  70% {
    box-shadow: 0 0 0 8px rgba(16, 16, 16, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(16, 16, 16, 0);
  }
}

@media (max-width: 1180px) {
  .hero-section,
  .dashboard-section {
    grid-template-columns: 1fr;
  }

  .hero-feature-grid,
  .metrics-row,
  .forecast-grid,
  .macro-basket-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .navbar,
  .main-content {
    padding-left: 18px;
    padding-right: 18px;
  }

  .navbar {
    flex-direction: column;
    align-items: flex-start;
    gap: 14px;
  }

  .main-title {
    font-size: 3.5rem;
  }

  .hero-cta-row {
    width: 100%;
  }

  .hero-feature-grid,
  .metrics-row,
  .forecast-grid,
  .macro-basket-grid {
    grid-template-columns: 1fr;
  }

  .story-step,
  .workflow-item {
    grid-template-columns: 42px minmax(0, 1fr);
  }

  .console-top-banner,
  .playout-header {
    flex-direction: column;
  }
}
</style>

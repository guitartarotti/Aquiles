<template>
  <div class="mmhp-widget" ref="rootEl">

    <!-- Loading / empty state -->
    <div v-if="loading && !timeline.length" class="mmhp-empty">
      <span class="mmhp-spin">⟳</span>
      <span>Carregando movimentações do dia…</span>
    </div>
    <div v-else-if="!timeline.length" class="mmhp-empty">
      <span>Sem movimentações desde 10h BRT</span>
      <span class="mmhp-sub">{{ rawEvents.length }} eventos capturados — {{ deltaLookupSize }} strikes com delta</span>
      <div class="mmhp-tracker-badge" :class="trackerRunning === false ? 'badge-off' : trackerRunning === true ? 'badge-on' : 'badge-unk'">
        <span v-if="trackerRunning === true">● Tracker rodando</span>
        <span v-else-if="trackerRunning === false">● Tracker parado</span>
        <span v-else>○ Verificando tracker…</span>
      </div>
      <button v-if="trackerRunning === false" class="mmhp-reload-btn badge-restart"
              :disabled="trackerStarting" @click="ensureTrackerRunning">
        {{ trackerStarting ? '⟳ Iniciando…' : '▶ Iniciar Captura' }}
      </button>
      <button class="mmhp-reload-btn" @click="load">⟳ Recarregar</button>
    </div>

    <template v-else>

      <!-- ── KPI Header ─────────────────────────────────────────────────── -->
      <div class="mmhp-header">

        <div class="mmhp-kpi" :class="currentHedge >= 0 ? 'kpi-buy' : 'kpi-sell'">
          <span class="mmhp-kpi-lbl">Hedge {{ futLabel }}</span>
          <span class="mmhp-kpi-val">{{ fmtContracts(currentHedge) }}</span>
          <span class="mmhp-kpi-sub">
            {{ currentHedge >= 0 ? '▲ Comprar futuro' : '▼ Vender futuro' }}
          </span>
        </div>

        <div class="mmhp-sep" />

        <div class="mmhp-kpi">
          <span class="mmhp-kpi-lbl">DEX Mov Dia</span>
          <span class="mmhp-kpi-val" :class="cumulDex >= 0 ? 'cyan' : 'orange'">
            {{ fmtDex(cumulDex) }}
          </span>
          <span class="mmhp-kpi-sub">Σ delta × vol movimentado</span>
        </div>

        <div class="mmhp-sep" />

        <div class="mmhp-kpi">
          <span class="mmhp-kpi-lbl">Mov. Call</span>
          <span class="mmhp-kpi-val emerald">{{ fmtContracts(hedgeCall) }}</span>
          <span class="mmhp-kpi-sub">contratos call</span>
        </div>

        <div class="mmhp-sep" />

        <div class="mmhp-kpi">
          <span class="mmhp-kpi-lbl">Mov. Put</span>
          <span class="mmhp-kpi-val rose">{{ fmtContracts(hedgePut) }}</span>
          <span class="mmhp-kpi-sub">contratos put</span>
        </div>

        <div class="mmhp-sep" />

        <!-- Gamma KPI -->
        <div class="mmhp-kpi" v-if="gammaByStrike.length">
          <span class="mmhp-kpi-lbl">Γ Líquido ±{{ gammaBand }}%</span>
          <span class="mmhp-kpi-val"
                :class="gammaStatus === 'long' ? 'emerald' : gammaStatus === 'short' ? 'rose' : 'slate'">
            {{ fmtGamma(netGamma) }}
          </span>
          <span class="mmhp-kpi-sub"
                :class="gammaStatus === 'long' ? 'emerald' : gammaStatus === 'short' ? 'rose' : ''">
            {{ gammaStatus === 'long' ? '▲ Long Gamma'
             : gammaStatus === 'short' ? '▼ Short Gamma'
             : '— Neutro' }}
          </span>
        </div>

        <div class="mmhp-sep" />

        <div class="mmhp-kpi">
          <span class="mmhp-kpi-lbl">Eventos</span>
          <span class="mmhp-kpi-val slate">{{ timeline.length }}</span>
          <span class="mmhp-kpi-sub">
            <span v-if="loading" class="mmhp-loading-dot">↻</span>
            {{ lastFetch ? fmtTime(lastFetch) : '—' }}
          </span>
        </div>

        <div style="flex:1" />

        <!-- Controls -->
        <div class="mmhp-controls">
          <div class="mmhp-ctrl-group">
            <span class="mmhp-ctrl-lbl">Limiar contratos</span>
            <div class="mmhp-ctrl-btns">
              <button v-for="t in THRESHOLDS" :key="t"
                      class="mmhp-btn" :class="{ active: threshold === t }"
                      @click="threshold = t">
                {{ fmtK(t) }}
              </button>
            </div>
          </div>
          <div class="mmhp-ctrl-group">
            <span class="mmhp-ctrl-lbl">Futuro</span>
            <div class="mmhp-ctrl-btns">
              <button class="mmhp-btn" :class="{ active: futType === 'WIN' }" @click="futType = 'WIN'">WIN</button>
              <button class="mmhp-btn" :class="{ active: futType === 'IND' }" @click="futType = 'IND'">IND</button>
            </div>
          </div>
          <!-- Gamma toggle + band -->
          <div class="mmhp-ctrl-group">
            <span class="mmhp-ctrl-lbl">Gamma ±%</span>
            <div class="mmhp-ctrl-btns">
              <button v-for="b in GAMMA_BANDS" :key="b"
                      class="mmhp-btn" :class="{ active: gammaBand === b && showGamma }"
                      @click="gammaBand = b; showGamma = true">
                {{ b }}%
              </button>
            </div>
          </div>
          <button class="mmhp-btn" :class="{ active: showGamma }"
                  @click="showGamma = !showGamma" title="Mostrar/ocultar Gamma por Strike">Γ</button>
          <button class="mmhp-btn" :class="{ loading }" @click="load" title="Atualizar">⟳</button>
        </div>

        <span class="mmhp-meta">Spot: <b>{{ spotFmt }}</b></span>

        <!-- SABR model badge -->
        <span class="mmhp-sabr-pill"
              :class="!sabrEnabled ? 'sabr-off'
                    : sabrLoading  ? 'sabr-loading'
                    : sabrParams   ? 'sabr-on'
                    : sabrError    ? 'sabr-error'
                    :                'sabr-off'"
              :title="!sabrEnabled
                ? 'SABR desativado — clique para ativar'
                : sabrLoading
                ? 'Calibrando SABR…'
                : sabrParams
                ? `SABR ativo — α=${sabrParams.alpha?.toFixed(2)} β=${sabrParams.beta} ρ=${sabrParams.rho?.toFixed(2)} ν=${sabrParams.nu?.toFixed(2)} | ${sabrParams.source} | RMSE=${sabrParams.rmse?.toFixed(4)} (${sabrParams.n_pts} pts)`
                : sabrError
                ? `Erro SABR: ${sabrError} — clique para tentar novamente`
                : 'SABR sem dados — clique para tentar'"
              @click="toggleSabr">
          {{ !sabrEnabled ? '○ BS' : sabrLoading ? '⟳' : sabrParams ? '◈ SABR' : sabrError ? '! SABR' : '○ SABR' }}
        </span>

        <!-- Tracker status pill -->
        <span class="mmhp-tracker-pill"
              :class="trackerRunning === true ? 'pill-on' : trackerRunning === false ? 'pill-off' : 'pill-unk'"
              :title="trackerRunning === true ? 'Tracker ativo — capturando volume em tempo real'
                    : trackerRunning === false ? 'Tracker parado — clique para reiniciar'
                    : 'Verificando status do tracker…'"
              @click="trackerRunning === false ? ensureTrackerRunning() : null">
          {{ trackerRunning === true ? '● LIVE' : trackerRunning === false ? '○ OFF' : '○ …' }}
        </span>
      </div>

      <!-- ── Bar chart: individual moves ────────────────────────────────── -->
      <div class="mmhp-section-lbl">
        Movimentações de hedge &gt; {{ fmtK(threshold) }} contratos {{ futLabel }}
        <span class="mmhp-sub-lbl">
          — {{ largeMoves.length }} evento{{ largeMoves.length !== 1 ? 's' : '' }}
          — {{ filteredOut }} mov abaixo do limiar oculta{{ filteredOut !== 1 ? 's' : '' }}
        </span>
      </div>
      <div class="mmhp-chart-wrap" style="flex:1">
        <svg class="mmhp-svg" :viewBox="`0 0 ${CW} ${BH}`" preserveAspectRatio="none"
             @mousemove="onHoverBar" @mouseleave="hoverBar = null">

          <!-- Time grid -->
          <line v-for="g in timeGrid" :key="'bg' + g.ts"
                :x1="g.x" :x2="g.x" :y1="bPadT" :y2="BH - bPadB"
                stroke="rgba(148,163,184,0.08)" stroke-width="1" stroke-dasharray="2,4" />

          <!-- Zero line -->
          <line :x1="bPadL" :x2="CW - bPadR" :y1="bYZero" :y2="bYZero"
                stroke="rgba(148,163,184,0.22)" stroke-width="1" stroke-dasharray="3,3" />

          <!-- Y grid -->
          <line v-for="t in bYTicks" :key="'byg' + t.val"
                :x1="bPadL" :x2="CW - bPadR" :y1="t.py" :y2="t.py"
                stroke="rgba(148,163,184,0.05)" stroke-width="1" stroke-dasharray="2,5" />

          <!-- Bars: stacked call (green) + put (red) side by side -->
          <g v-for="m in largeMoves" :key="'bm' + m.ts">
            <!-- Call hedge bar -->
            <rect v-if="m.callH > 0 || m.callH < 0"
                  :x="m.x - BAR_W + 1" :y="m.callBarY" :width="BAR_W - 1" :height="m.callBarH"
                  fill="#10b981" :fill-opacity="hoverBar?.ts === m.ts ? 1 : 0.75" rx="1" />
            <!-- Put hedge bar -->
            <rect v-if="m.putH > 0 || m.putH < 0"
                  :x="m.x + 1" :y="m.putBarY" :width="BAR_W - 1" :height="m.putBarH"
                  fill="#f43f5e" :fill-opacity="hoverBar?.ts === m.ts ? 1 : 0.75" rx="1" />
            <!-- Net tick line -->
            <line :x1="m.x - BAR_W" :x2="m.x + BAR_W"
                  :y1="m.netY" :y2="m.netY"
                  :stroke="m.net >= 0 ? '#06b6d4' : '#f97316'"
                  stroke-width="1.5" />
            <!-- Value label -->
            <text v-if="Math.abs(m.netBarH) >= 10"
                  :x="m.x" :y="m.net >= 0 ? m.netY - 4 : m.netY + 11"
                  :fill="m.net >= 0 ? '#10b981' : '#f43f5e'"
                  font-size="8" font-weight="700" text-anchor="middle">
              {{ m.net >= 0 ? '+' : '' }}{{ fmtK(m.net) }}
            </text>
          </g>

          <!-- Empty state -->
          <text v-if="!largeMoves.length"
                :x="CW / 2" :y="BH / 2 + 4"
                fill="#334155" font-size="11" text-anchor="middle">
            Nenhuma movimentação acima de {{ fmtK(threshold) }} contratos
          </text>

          <!-- X time labels -->
          <text v-for="g in timeGrid" :key="'bxl' + g.ts"
                :x="g.x" :y="BH - bPadB + 13"
                fill="#334155" font-size="8" text-anchor="middle">{{ g.label }}</text>

          <!-- Y labels -->
          <text v-for="t in bYTicks" :key="'byl' + t.val"
                :x="bPadL - 4" :y="t.py"
                fill="#334155" font-size="8" text-anchor="end" dominant-baseline="middle">
            {{ fmtK(t.val) }}
          </text>

          <!-- Hover crosshair -->
          <line v-if="hoverBar"
                :x1="hoverBar.x" :x2="hoverBar.x" :y1="bPadT" :y2="BH - bPadB"
                stroke="rgba(255,255,255,0.22)" stroke-width="1" stroke-dasharray="2,2" />
        </svg>

        <div class="mmhp-tt" v-if="hoverBar" :style="ttStyle(hoverBar.px, hoverBar.py)">
          <div class="tt-head">{{ fmtTime(hoverBar.ts) }}</div>
          <div class="tt-row">
            <span class="tt-lbl">Net hedge</span>
            <span :class="hoverBar.net >= 0 ? 'tt-emerald' : 'tt-rose'">
              {{ hoverBar.net >= 0 ? '▲ ' : '▼ ' }}{{ fmtContracts(hoverBar.net) }}
            </span>
          </div>
          <div class="tt-row">
            <span class="tt-lbl">Call</span>
            <span class="tt-emerald">{{ fmtContracts(hoverBar.callHedge) }}</span>
          </div>
          <div class="tt-row">
            <span class="tt-lbl">Put</span>
            <span class="tt-rose">{{ fmtContracts(hoverBar.putHedge) }}</span>
          </div>
          <!-- SABR enrichment row -->
          <template v-if="hoverBar.sabrResult">
            <div class="tt-divider" />
            <div class="tt-row">
              <span class="tt-lbl">Δ SABR</span>
              <span class="tt-cyan">{{ hoverBar.sabrResult.delta_sabr?.toFixed(4) }}</span>
            </div>
            <div class="tt-row">
              <span class="tt-lbl">Δ BS</span>
              <span class="tt-val">{{ hoverBar.sabrResult.delta_bs?.toFixed(4) }}</span>
            </div>
            <div class="tt-row">
              <span class="tt-lbl">σ impl</span>
              <span class="tt-amber">{{ ((hoverBar.sabrResult.sigma_impl ?? 0) * 100).toFixed(2) }}%</span>
            </div>
            <div class="tt-row">
              <span class="tt-lbl">Γ SABR</span>
              <span class="tt-val">{{ fmtGamma(hoverBar.sabrResult.gamma_sabr) }}</span>
            </div>
            <div class="tt-row">
              <span class="tt-lbl">Banda W-W</span>
              <span :class="hoverBar.sabrResult.needs_hedge ? 'tt-rose' : 'tt-emerald'">
                ±{{ fmtContracts(hoverBar.sabrResult.band_win) }}
                {{ hoverBar.sabrResult.needs_hedge ? ' ⚠ rehedge' : '' }}
              </span>
            </div>
          </template>
          <div class="tt-row" v-if="hoverBar.vol">
            <span class="tt-lbl">Volume</span>
            <span class="tt-val">{{ fmtK(hoverBar.vol) }} contratos</span>
          </div>
          <div class="tt-row" v-if="hoverBar.spot">
            <span class="tt-lbl">Spot</span>
            <span class="tt-amber">{{ fmtLevel(hoverBar.spot) }}</span>
          </div>
        </div>
      </div>

      <!-- ── Cumulative hedge line ─────────────────────────────────────────── -->
      <div class="mmhp-section-lbl">
        Posição de Hedge Acumulada — Sessão
        <span class="mmhp-sub-lbl">(+compra / −vende futuro)</span>
      </div>
      <div class="mmhp-chart-wrap" style="flex:1">
        <svg class="mmhp-svg" :viewBox="`0 0 ${CW} ${LH}`" preserveAspectRatio="none"
             @mousemove="onHoverLine" @mouseleave="hoverLine = null">

          <defs>
            <clipPath id="mmhp-clip-pos">
              <rect :x="lPadL" :y="lPadT" :width="CW - lPadL - lPadR" :height="lYZero - lPadT" />
            </clipPath>
            <clipPath id="mmhp-clip-neg">
              <rect :x="lPadL" :y="lYZero" :width="CW - lPadL - lPadR" :height="LH - lPadB - lYZero" />
            </clipPath>
          </defs>

          <!-- Time grid -->
          <line v-for="g in timeGrid" :key="'lg' + g.ts"
                :x1="g.x" :x2="g.x" :y1="lPadT" :y2="LH - lPadB"
                stroke="rgba(148,163,184,0.08)" stroke-width="1" stroke-dasharray="2,4" />

          <!-- Zero line -->
          <line :x1="lPadL" :x2="CW - lPadR" :y1="lYZero" :y2="lYZero"
                stroke="rgba(148,163,184,0.22)" stroke-width="1" stroke-dasharray="3,3" />

          <!-- Y grid -->
          <line v-for="t in lYTicks" :key="'lyg' + t.val"
                :x1="lPadL" :x2="CW - lPadR" :y1="t.py" :y2="t.py"
                stroke="rgba(148,163,184,0.05)" stroke-width="1" stroke-dasharray="2,5" />

          <!-- Area fills -->
          <path v-if="cumulArea" :d="cumulArea" fill="#10b981" fill-opacity="0.13"
                clip-path="url(#mmhp-clip-pos)" />
          <path v-if="cumulArea" :d="cumulArea" fill="#f43f5e" fill-opacity="0.13"
                clip-path="url(#mmhp-clip-neg)" />

          <!-- Lines -->
          <path v-if="cumulLine" :d="cumulLine" stroke="#10b981" stroke-width="2"
                fill="none" stroke-linejoin="round" stroke-linecap="round"
                clip-path="url(#mmhp-clip-pos)" />
          <path v-if="cumulLine" :d="cumulLine" stroke="#f43f5e" stroke-width="2"
                fill="none" stroke-linejoin="round" stroke-linecap="round"
                clip-path="url(#mmhp-clip-neg)" />

          <!-- Event tick marks for large moves -->
          <line v-for="m in largeMoves" :key="'lt' + m.ts"
                :x1="m.lx" :x2="m.lx" :y1="lPadT" :y2="LH - lPadB"
                :stroke="m.net >= 0 ? '#10b981' : '#f43f5e'"
                stroke-width="1" stroke-opacity="0.30" stroke-dasharray="2,3" />

          <!-- Hover crosshair + dot -->
          <line v-if="hoverLine"
                :x1="hoverLine.svgX" :x2="hoverLine.svgX" :y1="lPadT" :y2="LH - lPadB"
                stroke="rgba(255,255,255,0.22)" stroke-width="1" stroke-dasharray="2,2" />
          <circle v-if="hoverLine"
                  :cx="hoverLine.svgX" :cy="hoverLine.svgY" r="3.5"
                  :fill="hoverLine.cumul >= 0 ? '#10b981' : '#f43f5e'"
                  fill-opacity="0.95" />

          <!-- X time labels -->
          <text v-for="g in timeGrid" :key="'lxl' + g.ts"
                :x="g.x" :y="LH - lPadB + 13"
                fill="#334155" font-size="8" text-anchor="middle">{{ g.label }}</text>

          <!-- Y labels -->
          <text v-for="t in lYTicks" :key="'lyl' + t.val"
                :x="lPadL - 4" :y="t.py"
                fill="#334155" font-size="8" text-anchor="end" dominant-baseline="middle">
            {{ fmtContracts(t.val) }}
          </text>

          <!-- Current level label right edge -->
          <text v-if="cumulPts.length"
                :x="CW - lPadR + 3" :y="cumulPts.at(-1).y"
                :fill="cumulPts.at(-1).cumul >= 0 ? '#10b981' : '#f43f5e'"
                font-size="8" font-weight="700" dominant-baseline="middle">
            {{ fmtContracts(cumulPts.at(-1).cumul) }}
          </text>
        </svg>

        <div class="mmhp-tt" v-if="hoverLine" :style="ttStyle(hoverLine.px, hoverLine.py)">
          <div class="tt-head">{{ fmtTime(hoverLine.ts) }}</div>
          <div class="tt-row">
            <span class="tt-lbl">Hedge acumulado</span>
            <span :class="hoverLine.cumul >= 0 ? 'tt-emerald' : 'tt-rose'">
              {{ fmtContracts(hoverLine.cumul) }}
            </span>
          </div>
          <div class="tt-row">
            <span class="tt-lbl">Δ Hedge</span>
            <span :class="hoverLine.hedge >= 0 ? 'tt-emerald' : 'tt-rose'">
              {{ hoverLine.hedge >= 0 ? '+' : '' }}{{ fmtContracts(hoverLine.hedge) }}
            </span>
          </div>
          <div class="tt-row">
            <span class="tt-lbl">DEX mov</span>
            <span class="tt-cyan">{{ fmtDex(hoverLine.dex) }}</span>
          </div>
          <div class="tt-row" v-if="hoverLine.spot">
            <span class="tt-lbl">Spot</span>
            <span class="tt-amber">{{ fmtLevel(hoverLine.spot) }}</span>
          </div>
        </div>
      </div>

      <!-- ── Gamma por Strike ───────────────────────────────────────────────── -->
      <template v-if="showGamma">
        <div class="mmhp-section-lbl">
          Γ Gamma por Strike — Fluxo do Dia ±{{ gammaBand }}% do Spot
          <span class="mmhp-sub-lbl">
            — {{ gammaByStrike.length }} strike{{ gammaByStrike.length !== 1 ? 's' : '' }}
            — <span :class="gammaStatus === 'long' ? 'emerald' : gammaStatus === 'short' ? 'rose' : ''">
                {{ gammaStatus === 'long' ? '▲ Long Gamma' : gammaStatus === 'short' ? '▼ Short Gamma' : 'Neutro' }}
              </span>
          </span>
        </div>

        <div class="mmhp-chart-wrap" style="flex:1; min-height: 170px">
          <div v-if="!gammaByStrike.length" class="mmhp-gamma-empty">
            Sem movimentações próximas ao spot (±{{ gammaBand }}%)
          </div>
          <svg v-else class="mmhp-svg" :viewBox="`0 0 ${CW} ${GH}`" preserveAspectRatio="none"
               @mousemove="onHoverGamma" @mouseleave="hoverGamma = null">

            <!-- Zero line -->
            <line :x1="gPadL" :x2="CW - gPadR" :y1="gYZero" :y2="gYZero"
                  stroke="rgba(148,163,184,0.22)" stroke-width="1" stroke-dasharray="3,3" />

            <!-- Y grid -->
            <line v-for="t in gYTicks" :key="'gyg' + t.val"
                  :x1="gPadL" :x2="CW - gPadR" :y1="t.py" :y2="t.py"
                  stroke="rgba(148,163,184,0.05)" stroke-width="1" stroke-dasharray="2,5" />

            <!-- Spot vertical line -->
            <line v-if="gBars.spotX != null"
                  :x1="gBars.spotX" :x2="gBars.spotX" :y1="gPadT" :y2="GH - gPadB"
                  stroke="#f59e0b" stroke-width="1" stroke-dasharray="3,3" stroke-opacity="0.60" />
            <text v-if="gBars.spotX != null"
                  :x="gBars.spotX" :y="gPadT - 4"
                  fill="#f59e0b" font-size="7" text-anchor="middle" opacity="0.8">
              SPOT
            </text>

            <!-- Y labels -->
            <text v-for="t in gYTicks" :key="'gyl' + t.val"
                  :x="gPadL - 4" :y="t.py"
                  fill="#334155" font-size="8" text-anchor="end" dominant-baseline="middle">
              {{ fmtGamma(t.val) }}
            </text>

            <!-- Per-strike groups -->
            <g v-for="b in gBars.bars" :key="'gbg' + b.strike">

              <!-- Selected-strike highlight background -->
              <rect v-if="selectedGammaStrike === b.strike"
                    :x="b.x - b.bW" :y="gPadT"
                    :width="b.bW * 2" :height="GH - gPadT - gPadB"
                    fill="rgba(245,158,11,0.07)" rx="2" />

              <!-- Call bar (positive, emerald) -->
              <rect v-if="b.callH > 0.5"
                    :x="b.x - b.bW / 2" :y="b.callY"
                    :width="b.bW / 2 - 0.5" :height="b.callH"
                    fill="#10b981"
                    :fill-opacity="hoverGamma?.strike === b.strike || selectedGammaStrike === b.strike ? 1 : 0.75"
                    rx="1" />

              <!-- Put bar (negative, rose) -->
              <rect v-if="b.putH > 0.5"
                    :x="b.x + 0.5" :y="b.putY"
                    :width="b.bW / 2 - 0.5" :height="b.putH"
                    fill="#f43f5e"
                    :fill-opacity="hoverGamma?.strike === b.strike || selectedGammaStrike === b.strike ? 1 : 0.75"
                    rx="1" />

              <!-- Net tick line -->
              <line :x1="b.x - b.bW / 2" :x2="b.x + b.bW / 2"
                    :y1="gYOf(b.gamma)" :y2="gYOf(b.gamma)"
                    :stroke="b.gamma >= 0 ? '#06b6d4' : '#f97316'"
                    stroke-width="1.5" />

              <!-- Strike label -->
              <text :x="b.x" :y="GH - gPadB + 12"
                    :fill="selectedGammaStrike === b.strike ? '#f59e0b' : '#334155'"
                    font-size="7" text-anchor="middle"
                    :font-weight="selectedGammaStrike === b.strike ? '700' : '400'">
                {{ fmtLevel(b.strike) }}
              </text>

              <!-- Hit area LAST = topo do z-order, captura todos os cliques da coluna -->
              <rect :x="b.x - b.bW" :y="gPadT"
                    :width="b.bW * 2" :height="GH - gPadT - gPadB"
                    fill="transparent"
                    style="cursor: pointer"
                    @click="selectStrike(b.strike)" />
            </g>

            <!-- Hover crosshair (on top of everything) -->
            <line v-if="hoverGamma"
                  :x1="hoverGamma.x" :x2="hoverGamma.x" :y1="gPadT" :y2="GH - gPadB"
                  stroke="rgba(255,255,255,0.18)" stroke-width="1" stroke-dasharray="2,2"
                  style="pointer-events: none" />
          </svg>

          <!-- Tooltip -->
          <div class="mmhp-tt" v-if="hoverGamma" :style="ttStyle(hoverGamma.px, hoverGamma.py)">
            <div class="tt-head">Strike {{ fmtLevel(hoverGamma.strike) }}</div>
            <div class="tt-row">
              <span class="tt-lbl">Gamma líquido</span>
              <span :class="hoverGamma.gamma >= 0 ? 'tt-emerald' : 'tt-rose'">
                {{ fmtGamma(hoverGamma.gamma) }}
              </span>
            </div>
            <div class="tt-row">
              <span class="tt-lbl">Call Γ</span>
              <span class="tt-emerald">+{{ fmtGamma(hoverGamma.callGamma) }}</span>
            </div>
            <div class="tt-row">
              <span class="tt-lbl">Put Γ</span>
              <span class="tt-rose">{{ fmtGamma(hoverGamma.putGamma) }}</span>
            </div>
            <div class="tt-row">
              <span class="tt-lbl">Volume</span>
              <span class="tt-val">{{ fmtK(hoverGamma.vol) }} opções</span>
            </div>
          </div>
        </div>

        <!-- ── Strike GEX History (drill-down) ──────────────────────────────── -->
        <template v-if="selectedGammaStrike !== null">
          <div class="mmhp-section-lbl" style="margin-top: 4px">
            Γ GEX Intraday — Strike {{ fmtLevel(selectedGammaStrike) }}
            <span class="mmhp-sub-lbl">GEX acumulado das movimentações</span>
            <button class="mmhp-strike-close" @click="selectedGammaStrike = null" title="Fechar">✕</button>
          </div>

          <div class="mmhp-chart-wrap" style="flex:1; min-height: 130px">
            <div v-if="!strikeGexHistory.length" class="mmhp-gamma-empty">
              Sem movimentações registradas para o strike {{ fmtLevel(selectedGammaStrike) }}
            </div>
            <svg v-else class="mmhp-svg" :viewBox="`0 0 ${CW} ${SH}`" preserveAspectRatio="none"
                 @mousemove="onHoverStrikeHistory" @mouseleave="hoverStrikeHistory = null">

              <defs>
                <clipPath id="mmhp-sclip-pos">
                  <rect :x="sPadL" :y="sPadT"
                        :width="CW - sPadL - sPadR"
                        :height="Math.max(0, sYZero - sPadT)" />
                </clipPath>
                <clipPath id="mmhp-sclip-neg">
                  <rect :x="sPadL" :y="sYZero"
                        :width="CW - sPadL - sPadR"
                        :height="Math.max(0, SH - sPadB - sYZero)" />
                </clipPath>
              </defs>

              <!-- Time grid -->
              <line v-for="g in timeGrid" :key="'sg' + g.ts"
                    :x1="tsToX(g.ts, sPadL, sPadR)"
                    :x2="tsToX(g.ts, sPadL, sPadR)"
                    :y1="sPadT" :y2="SH - sPadB"
                    stroke="rgba(148,163,184,0.08)" stroke-width="1" stroke-dasharray="2,4" />

              <!-- Zero line -->
              <line :x1="sPadL" :x2="CW - sPadR" :y1="sYZero" :y2="sYZero"
                    stroke="rgba(148,163,184,0.22)" stroke-width="1" stroke-dasharray="3,3" />

              <!-- Y grid -->
              <line v-for="t in sYTicks" :key="'syg' + t.val"
                    :x1="sPadL" :x2="CW - sPadR" :y1="t.py" :y2="t.py"
                    stroke="rgba(148,163,184,0.05)" stroke-width="1" stroke-dasharray="2,5" />

              <!-- Area fill — positive (emerald) -->
              <path v-if="sCumulArea" :d="sCumulArea"
                    fill="#10b981" fill-opacity="0.13"
                    clip-path="url(#mmhp-sclip-pos)" />
              <!-- Area fill — negative (rose) -->
              <path v-if="sCumulArea" :d="sCumulArea"
                    fill="#f43f5e" fill-opacity="0.13"
                    clip-path="url(#mmhp-sclip-neg)" />

              <!-- Line — positive -->
              <path v-if="sCumulLine" :d="sCumulLine"
                    stroke="#10b981" stroke-width="2"
                    fill="none" stroke-linejoin="round" stroke-linecap="round"
                    clip-path="url(#mmhp-sclip-pos)" />
              <!-- Line — negative -->
              <path v-if="sCumulLine" :d="sCumulLine"
                    stroke="#f43f5e" stroke-width="2"
                    fill="none" stroke-linejoin="round" stroke-linecap="round"
                    clip-path="url(#mmhp-sclip-neg)" />

              <!-- Event tick marks (bucket boundaries) -->
              <line v-for="p in sCumulPts" :key="'stk' + p.ts"
                    :x1="p.x" :x2="p.x" :y1="SH - sPadB" :y2="SH - sPadB + 3"
                    :stroke="p.cumul >= 0 ? '#10b981' : '#f43f5e'"
                    stroke-width="1" stroke-opacity="0.45" />

              <!-- Hover crosshair + dot -->
              <line v-if="hoverStrikeHistory"
                    :x1="hoverStrikeHistory.svgX" :x2="hoverStrikeHistory.svgX"
                    :y1="sPadT" :y2="SH - sPadB"
                    stroke="rgba(255,255,255,0.22)" stroke-width="1" stroke-dasharray="2,2" />
              <circle v-if="hoverStrikeHistory"
                      :cx="hoverStrikeHistory.svgX" :cy="hoverStrikeHistory.svgY" r="3.5"
                      :fill="hoverStrikeHistory.cumul >= 0 ? '#10b981' : '#f43f5e'"
                      fill-opacity="0.95" />

              <!-- X time labels -->
              <text v-for="g in timeGrid" :key="'sxl' + g.ts"
                    :x="tsToX(g.ts, sPadL, sPadR)" :y="SH - sPadB + 13"
                    fill="#334155" font-size="8" text-anchor="middle">{{ g.label }}</text>

              <!-- Y labels -->
              <text v-for="t in sYTicks" :key="'syl' + t.val"
                    :x="sPadL - 4" :y="t.py"
                    fill="#334155" font-size="8" text-anchor="end" dominant-baseline="middle">
                {{ fmtGamma(t.val) }}
              </text>

              <!-- Current value label at right edge -->
              <text v-if="sCumulPts.length"
                    :x="CW - sPadR + 3" :y="sCumulPts.at(-1).y"
                    :fill="sCumulPts.at(-1).cumul >= 0 ? '#10b981' : '#f43f5e'"
                    font-size="8" font-weight="700" dominant-baseline="middle">
                {{ fmtGamma(sCumulPts.at(-1).cumul) }}
              </text>
            </svg>

            <!-- Tooltip -->
            <div class="mmhp-tt" v-if="hoverStrikeHistory"
                 :style="ttStyle(hoverStrikeHistory.px, hoverStrikeHistory.py)">
              <div class="tt-head">{{ fmtTime(hoverStrikeHistory.ts) }}</div>
              <div class="tt-row">
                <span class="tt-lbl">GEX acumulado</span>
                <span :class="hoverStrikeHistory.cumul >= 0 ? 'tt-emerald' : 'tt-rose'">
                  {{ fmtGamma(hoverStrikeHistory.cumul) }}
                </span>
              </div>
              <div class="tt-row">
                <span class="tt-lbl">Δ GEX bucket</span>
                <span :class="hoverStrikeHistory.gc >= 0 ? 'tt-emerald' : 'tt-rose'">
                  {{ fmtGamma(hoverStrikeHistory.gc) }}
                </span>
              </div>
              <div class="tt-row">
                <span class="tt-lbl">Volume</span>
                <span class="tt-val">{{ fmtK(hoverStrikeHistory.vol) }} opções</span>
              </div>
            </div>
          </div>
        </template>

      </template>

    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { getVolumeActivity, getVolumeTrackerStatus, startVolumeTracker, computeHedgeDelta } from '@/api/options'

const props = defineProps({ modelData: { type: Object, default: null } })

// ─── Constants ────────────────────────────────────────────────────────────────
// IBOVE (opções) = IBOV / 10 → cada contrato de opção vale 1/10 de um contrato futuro
// WIN = R$0,20/pt IBOV ; IND = R$1,00/pt IBOV
// Para comparar, o multiplicador efetivo das opções IBOVE em termos de IBOV:
//   opt_mult_ibov = opt_mult_ibove × (IBOVE/IBOV) = 1.0 × 0.10 = 0.10
// Fator de conversão opção IBOVE → futuro IBOV
// Calibrado empiricamente: 50k calls típicas (delta 0.3-0.74) → 3–7k WIN
// Não usar 0.10 (superdimensiona 2-3×) nem 0.01 (subdimensiona 4×)
const IBOVE_TO_IBOV = 0.04
const FUT_MULT      = { WIN: 0.20, IND: 1.00 }   // R$ por ponto de IBOV
const MIN_VOL_CUMUL = 1_000         // mínimo para entrar no cumulativo
const THRESHOLDS    = [1_000, 5_000, 10_000, 25_000]  // em opções
const BAR_W         = 8
const REFRESH_MS    = 5 * 60_000
// Gamma — banda de strikes ao redor do spot (em %)
const GAMMA_BANDS   = [1, 2, 3, 5]
const STRIKE_ROUND  = 1_000         // agrupa strikes em múltiplos de 1.000

// Chart geometry
const CW = 600
const BH = 160; const bPadL = 52; const bPadR = 18; const bPadT = 18; const bPadB = 26
const LH = 140; const lPadL = 52; const lPadR = 36; const lPadT = 14; const lPadB = 26
// Gamma strike profile chart
const GH = 170; const gPadL = 60; const gPadR = 20; const gPadT = 18; const gPadB = 32
// Strike GEX history (drill-down) chart
const SH = 130; const sPadL = 52; const sPadR = 40; const sPadT = 14; const sPadB = 26

// ─── UI state ─────────────────────────────────────────────────────────────────
const futType    = ref('WIN')
const threshold  = ref(1_000)
const gammaBand  = ref(3)        // ±N% do spot para filtrar strikes
const showGamma  = ref(false)    // toggle do painel de gamma
const hoverBar            = ref(null)
const hoverLine           = ref(null)
const hoverGamma          = ref(null)
const hoverStrikeHistory  = ref(null)
const selectedGammaStrike = ref(null)   // strike selecionado (arredondado) para drill-down
const loading        = ref(false)
const lastFetch      = ref(null)
const rootEl         = ref(null)
const trackerRunning = ref(null)   // null = unknown, true/false
const trackerStarting = ref(false)

// ─── SABR model state ─────────────────────────────────────────────────────────
// sabrDeltaMap: { eventKey → { delta_sabr, delta_bs, sigma_impl, gamma_sabr,
//                               n_win, n_ind, band_win, band_ind, needs_hedge } }
// A chave é composta de strike|put_call|volume para matching com rawEvents
const sabrDeltaMap    = ref({})   // populated by loadSabr()
const sabrParams      = ref(null) // { alpha, beta, rho, nu, rmse, n_pts, source }
const sabrLoading     = ref(false)
const sabrLastFetch   = ref(null)
const sabrEnabled     = ref(true) // toggle do modelo SABR
const sabrError       = ref(null) // string de erro, null = sem erro

// ─── Raw data ─────────────────────────────────────────────────────────────────
const rawEvents = ref([])   // all events fetched from backend (today since 10h BRT)

// ─── Source helpers ───────────────────────────────────────────────────────────
const futLabel = computed(() => futType.value)
const futMult  = computed(() => FUT_MULT[futType.value])
const spot     = computed(() => props.modelData?.market_context?.spot_price ?? null)
const spotFmt  = computed(() => spot.value ? fmtLevel(spot.value) : '—')

// ─── BRT helpers ─────────────────────────────────────────────────────────────
function brtDateStr() {
  return new Date().toLocaleDateString('sv-SE', { timeZone: 'America/Sao_Paulo' })
}
function mkBrtTs(hh, mm = 0) {
  const d = brtDateStr()
  return new Date(`${d}T${String(hh).padStart(2,'0')}:${String(mm).padStart(2,'0')}:00-03:00`).getTime()
}
const MKT_OPEN  = computed(() => mkBrtTs(10, 0))
const MKT_CLOSE = computed(() => mkBrtTs(18, 5))

// ─── Delta lookup map (from model's by_strike) ────────────────────────────────
// { strikeKey: { C: delta_call, P: delta_put } }
const deltaMap = computed(() => {
  const byStrike = props.modelData?.aggregates?.by_strike ?? []
  const mult     = props.modelData?.config?.option_multiplier ?? 1.0
  const map = {}

  byStrike.forEach(r => {
    const k = String(Math.round(parseFloat(r.key ?? r.strike ?? 0)))
    const callOi = r.call_oi ?? 0
    const putOi  = r.put_oi  ?? 0
    // delta = dex / (oi × multiplier), falls back to null if oi = 0
    const dC = callOi > 0 ? (r.dex_call ?? 0) / (callOi * mult) : null
    const dP = putOi  > 0 ? (r.dex_put  ?? 0) / (putOi  * mult) : null
    map[k] = { C: dC, P: dP }
  })
  return map
})

const deltaLookupSize = computed(() => Object.keys(deltaMap.value).length)

// ─── Black-Scholes delta fallback ─────────────────────────────────────────────
// Φ(x) — normal CDF via rational approx (Abramowitz & Stegun)
function normCDF(x) {
  const t = 1 / (1 + 0.2316419 * Math.abs(x))
  const d = 0.3989423 * Math.exp(-0.5 * x * x)
  const p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.7814779 + t * (-1.8212560 + t * 1.3302744))))
  return x >= 0 ? 1 - p : p
}

function bsDelta(S, K, sigma, T, r, pc) {
  if (!S || !K || sigma <= 0 || T <= 0) return pc === 'C' ? 0.5 : -0.5
  const d1 = (Math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * Math.sqrt(T))
  const cDelta = normCDF(d1)
  return pc === 'P' ? cDelta - 1 : cDelta
}

// Γ = φ(d₁) / (S × σ × √T)  — mesmas inputs do bsDelta
function bsGamma(S, K, sigma, T, r = 0.115) {
  if (!S || !K || sigma <= 0 || T <= 0) return 0
  const d1 = (Math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * Math.sqrt(T))
  const phi = Math.exp(-0.5 * d1 * d1) / Math.sqrt(2 * Math.PI)
  return phi / (S * sigma * Math.sqrt(T))
}

// Retorna true se o strike K está dentro de ±bandPct% do spot S
function isNearSpot(K, S, bandPct) {
  if (!S || !K) return false
  return Math.abs(K - S) / S <= bandPct / 100
}

// Gamma para um evento de movimentação
function getGammaForEvent(ev) {
  const S     = ev.spot_price || spot.value || 130_000
  const K     = parseFloat(ev.strike ?? 0)
  const ctx   = props.modelData?.market_context ?? {}
  const sigma = ctx.implied_vol ?? 0.18
  const T     = Math.max((ctx.days_to_expiry ?? (ev.days_to_maturity ?? 21)) / 252, 1 / 252)
  const r     = ctx.risk_free_rate ?? 0.115
  return bsGamma(S, K, sigma, T, r)
}

// Clamp delta para o intervalo fisicamente válido [-1, 1]
// Necessário porque o deltaMap pode retornar valores > 1 se option_multiplier
// do modelo for < 1 (ex: 0.01 → dC = avg_delta / 0.01 = 100× acima do correto)
function _clampDelta(d, pc) {
  if (!isFinite(d)) return pc === 'C' ? 0.5 : -0.5
  return Math.min(1.0, Math.max(-1.0, d))
}

function _sabrKey(ev) {
  // Chave de lookup no sabrDeltaMap: strike|put_call|volume
  const k  = String(Math.round(parseFloat(ev.strike ?? 0)))
  const pc = (ev.put_call ?? 'C').toUpperCase()[0] === 'P' ? 'P' : 'C'
  const v  = String(Math.round(parseFloat(ev.volume_delta ?? ev.volume ?? 0)))
  return `${k}|${pc}|${v}`
}

function getDeltaForEvent(ev) {
  const pc = (ev.put_call ?? 'C').toUpperCase()[0] === 'P' ? 'P' : 'C'

  // Priority 1: SABR smile-consistent (backend calibrado)
  if (sabrEnabled.value && sabrDeltaMap.value) {
    const key   = _sabrKey(ev)
    const entry = sabrDeltaMap.value[key]
    if (entry?.delta_sabr != null) {
      return _clampDelta(entry.delta_sabr, pc)
    }
  }

  // Priority 2: observed_delta da Bloomberg (vencimentos mensais)
  if (ev.observed_delta != null) {
    const d = parseFloat(ev.observed_delta)
    return _clampDelta(d, pc)
  }

  // Priority 3: delta map derivado do modelo (dex / oi)
  const k = String(Math.round(parseFloat(ev.strike ?? 0)))
  const entry = deltaMap.value[k]
  if (entry) {
    const d = pc === 'C' ? entry.C : entry.P
    if (d != null) {
      const clamped = _clampDelta(d, pc)
      if (Math.abs(d) > 1.05) {
        console.warn(`[MMHedge] deltaMap strike=${k} pc=${pc} delta=${d.toFixed(3)} → clamped=${clamped.toFixed(3)} (verifique option_multiplier no config do modelo)`)
      }
      return clamped
    }
  }

  // Priority 4: Black-Scholes (fallback final)
  const S     = ev.spot_price || spot.value || 130000
  const K     = parseFloat(ev.strike ?? 0)
  const ctx   = props.modelData?.market_context ?? {}
  const sigma = ctx.implied_vol ?? 0.18
  const T     = Math.max((ctx.days_to_expiry ?? (ev.days_to_maturity ?? 21)) / 252, 1 / 252)
  const r     = ctx.risk_free_rate ?? 0.115
  return _clampDelta(bsDelta(S, K, sigma, T, r, pc), pc)
}

// Retorna o resultado SABR completo para um evento (para exibir no tooltip)
function getSabrResult(ev) {
  if (!sabrEnabled.value || !sabrDeltaMap.value) return null
  return sabrDeltaMap.value[_sabrKey(ev)] ?? null
}

// ─── Timeline build ───────────────────────────────────────────────────────────
// Processes rawEvents into chronological hedge-per-event objects
// grouped into 1-minute buckets (one point per minute in the cumulative line)

const timeline = computed(() => {
  if (!rawEvents.value.length) return []

  const futM = futMult.value
  if (!futM) return []

  // Convert each event to { ts, hedge, callHedge, putHedge, dex, spot, vol }
  const pts = rawEvents.value
    .filter(ev => {
      // Aceita captured_at (ISO UTC) ou fallback para session_date + hora atual BRT
      // Evita filtrar eventos cuja data é válida mas sem hora (midnight UTC)
      const rawTs = ev.captured_at
      if (!rawTs) return true   // sem timestamp → inclui (vai pegar o ts do bucket)
      const ts = new Date(rawTs).getTime()
      if (isNaN(ts)) return true
      // Se o timestamp veio de session_date (apenas data), não filtrar por hora
      if (rawTs.length <= 10) return true
      return ts >= MKT_OPEN.value
    })
    .map(ev => {
      // Timestamp: prefere captured_at; fallback para agora (evento com só session_date)
      const rawTs = ev.captured_at
      let ts = rawTs && rawTs.length > 10 ? new Date(rawTs).getTime() : Date.now()
      if (isNaN(ts)) ts = Date.now()

      const vol  = parseFloat(ev.volume_delta ?? 0)
      const spt  = parseFloat(ev.spot_price ?? 0) || spot.value || 0
      const pc   = (ev.put_call ?? 'C').toUpperCase()[0] === 'P' ? 'P' : 'C'

      const delta = getDeltaForEvent(ev)
      // Hedge = delta × vol × IBOVE_TO_IBOV / fut_mult
      const hedge     = (delta * vol * IBOVE_TO_IBOV) / futM
      const dex       = delta * vol
      const callHedge = pc === 'C' ? hedge : 0
      const putHedge  = pc === 'P' ? hedge : 0

      return { ts, hedge, callHedge, putHedge, dex, spot: spt, vol, pc, strike: ev.strike, delta, rawEv: ev }
    })
    // Inclui no cumulativo qualquer movimento com >= MIN_VOL_CUMUL opções
    .filter(p => p.vol >= MIN_VOL_CUMUL)
    .sort((a, b) => a.ts - b.ts)

  // Bucket into 1-minute intervals and accumulate
  if (!pts.length) return []

  let cumul     = 0
  let cumulDexAcc = 0
  let cumulCall = 0
  let cumulPut  = 0

  // Group by 1-minute bucket
  const BUCKET = 60_000
  const buckets = []
  let curBucket = null

  for (const p of pts) {
    const bucketTs = Math.floor(p.ts / BUCKET) * BUCKET
    if (!curBucket || curBucket.ts !== bucketTs) {
      if (curBucket) buckets.push(curBucket)
      curBucket = {
        ts: bucketTs,
        hedge: 0, callHedge: 0, putHedge: 0, dex: 0,
        spot: p.spot, vol: 0, events: 0,
      }
    }
    curBucket.hedge     += p.hedge
    curBucket.callHedge += p.callHedge
    curBucket.putHedge  += p.putHedge
    curBucket.dex       += p.dex
    curBucket.spot       = p.spot || curBucket.spot
    curBucket.vol       += p.vol
    curBucket.events++
  }
  if (curBucket) buckets.push(curBucket)

  return buckets.map(b => {
    cumul       += b.hedge
    cumulDexAcc += b.dex
    cumulCall   += b.callHedge
    cumulPut    += b.putHedge
    return {
      ...b,
      cumul,
      cumulDex:  cumulDexAcc,
      cumulCall,
      cumulPut,
    }
  })
})

// ─── KPI aggregates ───────────────────────────────────────────────────────────
const currentHedge = computed(() => timeline.value.at(-1)?.cumul ?? 0)
const cumulDex     = computed(() => timeline.value.at(-1)?.cumulDex ?? 0)
const hedgeCall    = computed(() => timeline.value.at(-1)?.cumulCall ?? 0)
const hedgePut     = computed(() => timeline.value.at(-1)?.cumulPut  ?? 0)

// ─── Gamma por Strike (fluxo do dia, apenas strikes perto do spot) ────────────
// Sinal: calls → +gamma (long gamma), puts → -gamma (short gamma)
// Convenção: o dealer fica short gamma ao vender opções ao cliente.
// Se o fluxo de calls domina (net positivo) → mercado precificando mais risco de alta.
// Se o fluxo de puts domina (net negativo) → risco de queda mais coberto.

const gammaByStrike = computed(() => {
  const bandPct = gammaBand.value
  const S       = spot.value || 0
  if (!S) return []

  // Agrega gamma por strike arredondado
  const map = {}    // { strikeRounded: { gamma: number, callGamma: number, putGamma: number, vol: number } }

  rawEvents.value.forEach(ev => {
    const rawTs = ev.captured_at
    // Mesmo filtro de data-only da timeline
    if (rawTs && rawTs.length > 10) {
      const ts = new Date(rawTs).getTime()
      if (!isNaN(ts) && ts < MKT_OPEN.value) return
    }

    const vol = parseFloat(ev.volume_delta ?? 0)
    if (vol < 1) return   // ignora ruído

    const K  = parseFloat(ev.strike ?? 0)
    if (!K) return
    if (!isNearSpot(K, S, bandPct)) return

    const pc    = (ev.put_call ?? 'C').toUpperCase()[0] === 'P' ? 'P' : 'C'
    const gamma = getGammaForEvent(ev)
    // Sign: calls adicionam gamma positivo, puts adicionam gamma negativo
    const sign  = pc === 'C' ? +1 : -1
    const gc    = sign * gamma * vol

    const kr = Math.round(K / STRIKE_ROUND) * STRIKE_ROUND
    if (!map[kr]) map[kr] = { gamma: 0, callGamma: 0, putGamma: 0, vol: 0 }
    map[kr].gamma     += gc
    map[kr].vol       += vol
    if (pc === 'C') map[kr].callGamma += gamma * vol
    else            map[kr].putGamma  -= gamma * vol  // negativo
  })

  return Object.entries(map)
    .map(([k, v]) => ({ strike: Number(k), ...v }))
    .sort((a, b) => a.strike - b.strike)
})

// Gamma líquido total = soma de todos os strikes próximos ao spot
const netGamma = computed(() => gammaByStrike.value.reduce((s, b) => s + b.gamma, 0))

// Status: long, short, ou neutro (band < 20% do máximo absoluto)
const gammaStatus = computed(() => {
  const vals = gammaByStrike.value.map(b => b.gamma)
  if (!vals.length) return 'neutral'
  const net = netGamma.value
  const maxAbs = Math.max(...vals.map(Math.abs), 1e-12)
  if (Math.abs(net) < 0.05 * maxAbs) return 'neutral'
  return net > 0 ? 'long' : 'short'
})

// ─── Gamma chart: SVG coords ─────────────────────────────────────────────────
const gMaxAbs = computed(() => {
  const vals = gammaByStrike.value.map(b => Math.abs(b.gamma))
  return Math.max(...vals, 1e-12)
})

const gYZero = computed(() => gPadT + (GH - gPadT - gPadB) / 2)

function gYOf(v) {
  const half = (GH - gPadT - gPadB) / 2
  return gYZero.value - (v / gMaxAbs.value) * half * 0.9
}

const gBars = computed(() => {
  const data = gammaByStrike.value
  if (!data.length) return []

  const n     = data.length
  const inner = CW - gPadL - gPadR
  const bW    = Math.max(4, Math.min(28, Math.floor(inner / (n + 1)) - 2))
  const step  = inner / (n > 1 ? n - 1 : 1)

  const S = spot.value || 0
  const spotX = S && n > 1
    ? gPadL + ((S - data[0].strike) / (data[n-1].strike - data[0].strike || 1)) * inner
    : null

  return {
    bars: data.map((b, i) => {
      const x  = n > 1 ? gPadL + i * step : CW / 2
      const y0 = gYZero.value
      const yC = gYOf(b.callGamma)
      const yP = gYOf(b.putGamma)

      // Call bars: positive → rect starts ABOVE zero line (callY = min), goes up
      const callH  = Math.abs(y0 - yC)
      const callY  = Math.min(y0, yC)
      // Put bars: negative → rect starts AT zero line, goes DOWN (higher y in SVG)
      const putH   = Math.abs(y0 - yP)
      const putY   = y0   // always anchor at zero, height extends downward

      return {
        strike: b.strike, gamma: b.gamma, vol: b.vol,
        callGamma: b.callGamma, putGamma: b.putGamma,
        x, bW,
        callH, callY,
        putH,  putY,
      }
    }),
    spotX,
  }
})

// Gamma Y-axis ticks
const gYTicks = computed(() => {
  const m = gMaxAbs.value
  return [m, m * 0.5, 0, -m * 0.5, -m].map(v => ({ val: v, py: gYOf(v) }))
})

// ─── Strike GEX History (drill-down ao clicar em uma barra) ──────────────────
// Mostra o histórico intraday de GEX acumulado para o strike selecionado
const strikeGexHistory = computed(() => {
  const K = selectedGammaStrike.value
  if (K == null) return []

  const BUCKET = 60_000
  const allForStrike = rawEvents.value.filter(ev => {
    const kr = Math.round(parseFloat(ev.strike ?? 0) / STRIKE_ROUND) * STRIKE_ROUND
    return kr === K
  })
  console.log('[Gamma] strikeGexHistory K=', K, '| total rawEvents:', rawEvents.value.length,
              '| matching strike:', allForStrike.length)

  const pts = rawEvents.value
    .filter(ev => {
      const rawTs = ev.captured_at
      if (rawTs && rawTs.length > 10) {
        const ts = new Date(rawTs).getTime()
        if (!isNaN(ts) && ts < MKT_OPEN.value) return false
      }
      const kr = Math.round(parseFloat(ev.strike ?? 0) / STRIKE_ROUND) * STRIKE_ROUND
      return kr === K && parseFloat(ev.volume_delta ?? 0) >= 1
    })
    .map(ev => {
      const rawTs = ev.captured_at
      let ts = rawTs && rawTs.length > 10 ? new Date(rawTs).getTime() : Date.now()
      if (isNaN(ts)) ts = Date.now()
      const vol   = parseFloat(ev.volume_delta ?? 0)
      const pc    = (ev.put_call ?? 'C').toUpperCase()[0] === 'P' ? 'P' : 'C'
      const gamma = getGammaForEvent(ev)
      const gc    = (pc === 'C' ? +1 : -1) * gamma * vol
      return { ts, gc, vol, pc }
    })
    .sort((a, b) => a.ts - b.ts)

  if (!pts.length) return []

  // Agrupa em buckets de 1 minuto
  const buckets = []
  let cur = null
  for (const p of pts) {
    const bt = Math.floor(p.ts / BUCKET) * BUCKET
    if (!cur || cur.ts !== bt) {
      if (cur) buckets.push(cur)
      cur = { ts: bt, gc: 0, callGc: 0, putGc: 0, vol: 0, events: 0 }
    }
    cur.gc      += p.gc
    cur.vol     += p.vol
    cur.events++
    if (p.pc === 'C') cur.callGc += p.gc
    else              cur.putGc  += p.gc
  }
  if (cur) buckets.push(cur)

  let cumul = 0
  return buckets.map(b => { cumul += b.gc; return { ...b, cumul } })
})

// Y-axis scaling para o drill-down (range-based, igual ao cumulative hedge)
const sDataMin = computed(() => Math.min(...strikeGexHistory.value.map(b => b.cumul), 0))
const sDataMax = computed(() => Math.max(...strikeGexHistory.value.map(b => b.cumul), 0))
const sDataSpan = computed(() => {
  const span = sDataMax.value - sDataMin.value
  return span === 0 ? 1e-10 : span * 1.25
})
const sYZero = computed(() => {
  const inner = SH - sPadT - sPadB
  return sPadT + (sDataMax.value / sDataSpan.value) * inner
})
function sYOf(v) {
  const inner = SH - sPadT - sPadB
  const frac  = (sDataMax.value - v) / sDataSpan.value
  return sPadT + Math.min(Math.max(frac, 0), 1) * inner
}

const sCumulPts = computed(() =>
  strikeGexHistory.value.map(b => ({
    x:     tsToX(b.ts, sPadL, sPadR),
    y:     sYOf(b.cumul),
    cumul: b.cumul,
    gc:    b.gc,
    vol:   b.vol,
    ts:    b.ts,
  }))
)
const sCumulLine = computed(() => {
  const pts = sCumulPts.value
  if (pts.length < 2) return null
  return pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
})
const sCumulArea = computed(() => {
  const pts = sCumulPts.value
  if (pts.length < 2) return null
  const yz   = sYZero.value
  const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
  return `${line} L${pts.at(-1).x.toFixed(1)},${yz} L${pts[0].x.toFixed(1)},${yz} Z`
})
const sYTicks = computed(() => {
  const lo   = sDataMin.value - sDataSpan.value * 0.125
  const hi   = sDataMax.value + sDataSpan.value * 0.125
  const step = (hi - lo) / 3
  return Array.from({ length: 4 }, (_, i) => {
    const v = lo + i * step
    return { val: v, py: sYOf(v) }
  })
})

// ─── X-axis (shared time) ─────────────────────────────────────────────────────
const xMin = computed(() => {
  const first = timeline.value[0]?.ts
  return first ? Math.min(first, MKT_OPEN.value) : MKT_OPEN.value
})
const xMax = computed(() => {
  const now = Date.now()
  return Math.max(now + 2 * 60_000, MKT_CLOSE.value)
})
function tsToX(ts, pL, pR) {
  const span = xMax.value - xMin.value || 1
  return pL + ((ts - xMin.value) / span) * (CW - pL - pR)
}

const timeGrid = computed(() => {
  const d = brtDateStr()
  return [10, 11, 12, 13, 14, 15, 16, 17, 18].flatMap(h => {
    const ts = new Date(`${d}T${String(h).padStart(2,'0')}:00:00-03:00`).getTime()
    const x  = tsToX(ts, bPadL, bPadR)
    if (x < bPadL + 2 || x > CW - bPadR - 2) return []
    return [{ ts, x, label: `${h}h` }]
  })
})

// ─── Bar chart ────────────────────────────────────────────────────────────────
// Filtro por VOLUME DE OPÇÕES (bruto) — não por contratos futuros transformados.
// Isso evita que o fator de escala (IBOVE_TO_IBOV) torne todos os eventos invisíveis.
const filteredOut = computed(() => {
  const thr = threshold.value
  return timeline.value.filter(b => b.vol > 0 && b.vol < thr).length
})

const largeMoves = computed(() => {
  const thr = threshold.value
  // Filtra por volume de opções >= limiar (ex: 1.000 opções)
  const relevant = timeline.value.filter(b => b.vol >= thr)
  if (!relevant.length) return []

  // Escala das barras pelo volume de opções (tamanho visual = volume negociado)
  // Altura máxima proporcional ao volume de opções
  // Mas Y dos bars em contratos de hedge (net/call/put)
  const maxAbsC = Math.max(...relevant.map(b => Math.abs(b.callHedge)), 1)
  const maxAbsP = Math.max(...relevant.map(b => Math.abs(b.putHedge)),  1)
  const maxAbs  = Math.max(maxAbsC, maxAbsP, 1)
  const inner   = (BH - bPadT - bPadB) / 2

  return relevant.map(b => {
    const x    = tsToX(b.ts, bPadL, bPadR)
    const lx   = tsToX(b.ts, lPadL, lPadR)

    const cH    = (Math.abs(b.callHedge) / maxAbs) * inner
    const cBarY = bYZero.value - cH
    const pH    = (Math.abs(b.putHedge) / maxAbs) * inner
    const pBarY = bYZero.value
    const netH  = (b.hedge / maxAbs) * inner
    const netY  = bYZero.value - netH

    return {
      ts: b.ts, x, lx,
      net: b.hedge, callHedge: b.callHedge, putHedge: b.putHedge,
      vol: b.vol, spot: b.spot,
      callH: cH, callBarY: cBarY,
      putH: pH,  putBarY: pBarY,
      netY, netBarH: netH,
      rawEv: b.rawEv ?? null,
    }
  })
})

const bMaxAbs = computed(() => {
  const thr = threshold.value
  const vals = timeline.value.filter(b => b.vol >= thr)
    .flatMap(b => [Math.abs(b.callHedge), Math.abs(b.putHedge)])
  return Math.max(...vals, 1)
})
const bYZero = computed(() => bPadT + (BH - bPadT - bPadB) / 2)

function bYOf(v) {
  const half = (BH - bPadT - bPadB) / 2
  return bYZero.value - (v / bMaxAbs.value) * half
}
const bYTicks = computed(() => {
  const m = bMaxAbs.value
  return [m, m * 0.5, 0, -m * 0.5, -m].map(v => ({ val: v, py: bYOf(v) }))
})

// ─── Cumulative line chart ────────────────────────────────────────────────────
// Escala baseada no range REAL dos dados (não simétrica em torno de zero).
// Isso garante que mudanças pequenas mas reais (ex: +50 num acumulado de 3000)
// sejam visivelmente perceptíveis, ocupando proporção adequada do gráfico.
const lDataMin = computed(() => {
  const vals = timeline.value.map(b => b.cumul)
  return Math.min(...vals, 0)
})
const lDataMax = computed(() => {
  const vals = timeline.value.map(b => b.cumul)
  return Math.max(...vals, 0)
})
const lDataSpan = computed(() => {
  const span = lDataMax.value - lDataMin.value
  // Padding de 10% em cada lado para não encostar nas bordas
  return span === 0 ? 2 : span * 1.20
})
const lYZero = computed(() => {
  // Posição do zero no eixo Y (pode não ser o centro)
  const inner = LH - lPadT - lPadB
  const frac  = (lDataMax.value - 0) / lDataSpan.value
  return lPadT + frac * inner
})

function lYOf(v) {
  const inner = LH - lPadT - lPadB
  const frac  = (lDataMax.value - v) / lDataSpan.value
  return lPadT + Math.min(Math.max(frac, 0), 1) * inner
}

const cumulPts = computed(() =>
  timeline.value.map(b => ({
    x:     tsToX(b.ts, lPadL, lPadR),
    y:     lYOf(b.cumul),
    cumul: b.cumul,
    hedge: b.hedge,
    dex:   b.dex,
    spot:  b.spot,
    ts:    b.ts,
  }))
)

const cumulLine = computed(() => {
  const pts = cumulPts.value
  if (pts.length < 2) return null
  return pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
})

const cumulArea = computed(() => {
  const pts = cumulPts.value
  if (pts.length < 2) return null
  const yz   = lYZero.value
  const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
  return `${line} L${pts.at(-1).x.toFixed(1)},${yz} L${pts[0].x.toFixed(1)},${yz} Z`
})

const lYTicks = computed(() => {
  // 5 ticks distribuídos no range real dos dados
  const lo  = lDataMin.value - (lDataSpan.value * 0.10)
  const hi  = lDataMax.value + (lDataSpan.value * 0.10)
  const step = (hi - lo) / 4
  return Array.from({ length: 5 }, (_, i) => {
    const v = lo + i * step
    return { val: v, py: lYOf(v) }
  })
})

// ─── Tracker management ───────────────────────────────────────────────────────
async function checkTracker() {
  try {
    const res = await getVolumeTrackerStatus()
    const running = res?.data?.data?.running ?? res?.data?.running ?? false
    trackerRunning.value = running
    return running
  } catch (e) {
    console.warn('[MMHedge] tracker status check failed', e)
    return null
  }
}

async function ensureTrackerRunning() {
  const running = await checkTracker()
  if (running === false) {
    trackerStarting.value = true
    try {
      await startVolumeTracker()
      trackerRunning.value = true
      console.info('[MMHedge] volume tracker iniciado automaticamente')
    } catch (e) {
      console.warn('[MMHedge] falha ao iniciar tracker', e)
    } finally {
      trackerStarting.value = false
    }
  }
}

// ─── SABR toggle ─────────────────────────────────────────────────────────────
function toggleSabr() {
  // Se está em estado de erro → retry direto sem toggle
  if (sabrEnabled.value && sabrError.value && !sabrLoading.value) {
    sabrError.value = null
    loadSabr()
    return
  }
  // Se está ativo sem params (esperando dados) → tenta carregar direto
  if (sabrEnabled.value && !sabrParams.value && !sabrLoading.value) {
    loadSabr()
    return
  }
  sabrEnabled.value = !sabrEnabled.value
  if (sabrEnabled.value && !sabrLoading.value && rawEvents.value.length) {
    sabrError.value = null
    loadSabr()
  }
}

// ─── SABR Delta fetch ─────────────────────────────────────────────────────────
// Envia os rawEvents para o backend calcular deltas SABR + bandas W-W.
// Roda após cada load() ou quando o modelo muda.
async function loadSabr() {
  const events = rawEvents.value
  if (!events.length || sabrLoading.value || !sabrEnabled.value) return

  const ctx = props.modelData?.market_context ?? {}
  const S   = parseFloat(ctx.spot_price ?? 0) || spot.value || 0
  if (!S) return

  sabrLoading.value = true
  try {
    const volSurface = (props.modelData?.vol_surface_points ?? []).map(p => ({
      strike: p.strike,
      iv:     p.iv,
      dte:    p.dte,
    }))

    const res = await computeHedgeDelta({
      spot:       S,
      market_ctx: {
        implied_vol:     ctx.implied_vol     ?? 0.18,
        days_to_expiry:  ctx.days_to_expiry  ?? 21,
        risk_free_rate:  ctx.risk_free_rate  ?? 0.115,
      },
      vol_surface: volSurface,
      events:      events.map(ev => ({
        strike:           ev.strike,
        put_call:         ev.put_call,
        volume:           ev.volume_delta,
        days_to_maturity: ev.days_to_maturity,
        spot_price:       ev.spot_price,
        observed_delta:   ev.observed_delta ?? null,
      })),
      fut_type:    futType.value,
      tc_bps:      10,
      dt_minutes:  60,
    })

    const data    = res?.events ? res : (res?.data ?? {})
    const results = data.events ?? []

    // Só aplica se SABR ainda está ativo (usuário pode ter desativado enquanto carregava)
    if (!sabrEnabled.value) return

    // Constrói o mapa strike|put_call|volume → resultado SABR
    const newMap = {}
    results.forEach(r => {
      const key = `${Math.round(r.strike)}|${r.put_call}|${Math.round(r.volume)}`
      newMap[key] = r
    })
    sabrDeltaMap.value  = newMap
    // Só atualiza params se veio algo válido (não apaga estado anterior em caso de resposta vazia)
    if (data.sabr_params && data.sabr_params.alpha) {
      sabrParams.value = data.sabr_params
      sabrError.value  = null   // limpa erro anterior
    }
    sabrLastFetch.value = Date.now()

    const src = data.sabr_params?.source ?? 'unknown'
    const rmse = data.sabr_params?.rmse ?? 0
    console.info(
      `[MMHedge] SABR carregado — fonte=${src} α=${data.sabr_params?.alpha?.toFixed(4)} ρ=${data.sabr_params?.rho?.toFixed(3)} ν=${data.sabr_params?.nu?.toFixed(4)} RMSE=${rmse.toFixed(4)} eventos=${results.length}`
    )
  } catch (e) {
    console.warn('[MMHedge] SABR fetch falhou, usando fallback BS', e)
    sabrError.value = e?.response?.data?.error ?? e?.message ?? 'falha na requisição'
    // NÃO reseta sabrParams — mantém último estado válido para não perder UI
  } finally {
    sabrLoading.value = false
  }
}

// ─── Data fetch ───────────────────────────────────────────────────────────────
async function load() {
  if (loading.value) return
  loading.value = true
  try {
    const today = brtDateStr()
    const res   = await getVolumeActivity({
      session_date: today,
      limit:        5000,
    })
    const rows = res?.data?.data ?? res?.data ?? []

    // Filter to events since market open (10:00 BRT).
    // Same logic as timeline: se captured_at é só data (length ≤ 10) → inclui sempre
    // para não cortar eventos cujo captured_at veio apenas como session_date.
    const open = MKT_OPEN.value
    rawEvents.value = rows.filter(ev => {
      const rawTs = ev.captured_at ?? ev.session_date ?? ''
      if (!rawTs) return true
      const ts = new Date(rawTs).getTime()
      if (isNaN(ts)) return true
      if (rawTs.length <= 10) return true   // date-only → inclui
      return ts >= open
    })

    lastFetch.value = Date.now()
  } catch (e) {
    console.warn('[MMHedge] fetch failed', e)
  } finally {
    loading.value = false
  }
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────
let pollTimer        = null
let trackerCheckTimer = null

onMounted(async () => {
  // 1) Garante que o tracker está rodando antes de tentar buscar dados
  await ensureTrackerRunning()
  // 2) Carrega eventos do dia
  await load()
  // 3) Re-fetch periódico (5 min)
  pollTimer = setInterval(async () => { await load() }, REFRESH_MS)
  // 4) Verifica status do tracker a cada 2 min
  trackerCheckTimer = setInterval(checkTracker, 2 * 60_000)
})
onUnmounted(() => {
  clearInterval(pollTimer)
  clearInterval(trackerCheckTimer)
})

// Reload quando o ativo subjacente mudar
watch(() => props.modelData?.market_context?.underlying_security, (v, old) => {
  if (v && v !== old) load()
})

// Dispara SABR após novos eventos chegarem (só se SABR ativo)
watch(rawEvents, (events) => {
  if (events.length && sabrEnabled.value) loadSabr()
})

// Recalibra SABR se o tipo de futuro mudar (só se SABR ativo e com dados)
watch(futType, () => {
  if (rawEvents.value.length && sabrEnabled.value && sabrParams.value) loadSabr()
})

// ─── Hover ────────────────────────────────────────────────────────────────────
function onHoverBar(e) {
  if (!largeMoves.value.length) return
  const rect  = e.currentTarget.getBoundingClientRect()
  const px    = e.clientX - rect.left
  const svgX  = px / rect.width * CW
  let nearest = null, minD = Infinity
  for (const m of largeMoves.value) {
    const d = Math.abs(m.x - svgX)
    if (d < minD) { minD = d; nearest = m }
  }
  if (!nearest || minD > 20) { hoverBar.value = null; return }
  // Enriquece com resultado SABR se disponível
  const sabrResult = nearest.rawEv ? getSabrResult(nearest.rawEv) : null
  hoverBar.value = { ...nearest, px, py: e.clientY - rect.top, sabrResult }
}

function onHoverLine(e) {
  if (!cumulPts.value.length) return
  const rect = e.currentTarget.getBoundingClientRect()
  const px   = e.clientX - rect.left
  const py   = e.clientY - rect.top
  const svgX = px / rect.width * CW
  if (svgX < lPadL || svgX > CW - lPadR) { hoverLine.value = null; return }
  let nearest = null, minD = Infinity
  for (const p of cumulPts.value) {
    const d = Math.abs(p.x - svgX)
    if (d < minD) { minD = d; nearest = p }
  }
  if (!nearest) return
  hoverLine.value = { px, py, svgX: nearest.x, svgY: nearest.y, ...nearest }
}

function onHoverGamma(e) {
  const bars = gBars.value?.bars ?? gBars.value
  if (!Array.isArray(bars) || !bars.length) return
  const rect = e.currentTarget.getBoundingClientRect()
  const px   = e.clientX - rect.left
  const svgX = px / rect.width * CW
  let nearest = null, minD = Infinity
  for (const b of bars) {
    const d = Math.abs(b.x - svgX)
    if (d < minD) { minD = d; nearest = b }
  }
  if (!nearest || minD > nearest.bW * 3) { hoverGamma.value = null; return }
  hoverGamma.value = { ...nearest, px, py: e.clientY - rect.top }
}

// Seleciona/deseleciona um strike para o drill-down de GEX intraday
function selectStrike(strike) {
  const next = selectedGammaStrike.value === strike ? null : strike
  selectedGammaStrike.value = next
  hoverStrikeHistory.value = null
}

function onHoverStrikeHistory(e) {
  const pts = sCumulPts.value
  if (!pts.length) return
  const rect = e.currentTarget.getBoundingClientRect()
  const px   = e.clientX - rect.left
  const py   = e.clientY - rect.top
  const svgX = px / rect.width * CW
  if (svgX < sPadL || svgX > CW - sPadR) { hoverStrikeHistory.value = null; return }
  let nearest = null, minD = Infinity
  for (const p of pts) {
    const d = Math.abs(p.x - svgX)
    if (d < minD) { minD = d; nearest = p }
  }
  if (!nearest) return
  hoverStrikeHistory.value = { px, py, svgX: nearest.x, svgY: nearest.y, ...nearest }
}

function ttStyle(px, py) {
  const rootW = rootEl.value?.offsetWidth ?? 400
  const x = Math.max(85, Math.min(rootW - 85, px))
  return { left: x + 'px', top: Math.max(8, py - 112) + 'px' }
}

// ─── Formatters ───────────────────────────────────────────────────────────────
function fmtContracts(v) {
  if (v == null || !isFinite(v)) return '—'
  const abs  = Math.abs(v)
  const sign = v < 0 ? '−' : '+'
  if (abs >= 1e9) return sign + (abs / 1e9).toFixed(1) + 'B'
  if (abs >= 1e6) return sign + (abs / 1e6).toFixed(2) + 'M'
  if (abs >= 1e3) return sign + (abs / 1e3).toFixed(1) + 'K'
  return (v >= 0 ? '+' : '−') + abs.toFixed(0)
}
function fmtK(v) {
  if (v == null) return '—'
  const abs = Math.abs(v)
  if (abs >= 1e6) return (v / 1e6).toFixed(1) + 'M'
  if (abs >= 1e3) return (v / 1e3).toFixed(0) + 'K'
  return String(v)
}
function fmtDex(v) {
  if (v == null || !isFinite(v)) return '—'
  const abs = Math.abs(v); const sign = v < 0 ? '-' : ''
  if (abs >= 1e9) return sign + (abs / 1e9).toFixed(2) + 'B'
  if (abs >= 1e6) return sign + (abs / 1e6).toFixed(2) + 'M'
  if (abs >= 1e3) return sign + (abs / 1e3).toFixed(1) + 'K'
  return v.toFixed(1)
}
function fmtLevel(v) {
  if (!v) return '—'
  return Math.abs(v) >= 1000 ? (v / 1000).toFixed(2) + 'k' : v.toFixed(0)
}
function fmtGamma(v) {
  if (v == null || !isFinite(v)) return '—'
  const abs = Math.abs(v)
  const sign = v >= 0 ? '+' : '−'
  if (abs >= 1e6) return sign + (abs / 1e6).toFixed(2) + 'M'
  if (abs >= 1e3) return sign + (abs / 1e3).toFixed(1) + 'K'
  if (abs >= 1)   return sign + abs.toFixed(0)
  // Scientific for very small values
  return sign + abs.toExponential(2)
}
function fmtTime(ts) {
  if (!ts) return '—'
  return new Date(ts).toLocaleTimeString('pt-BR', {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    timeZone: 'America/Sao_Paulo',
  })
}
</script>

<style scoped>
.mmhp-widget {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 8px;
  gap: 5px;
  background: #05101c;
  color: #e2e8f0;
  font-family: "JetBrains Mono", monospace;
  overflow: hidden;
}
.mmhp-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #475569;
  font-size: 12px;
}
.mmhp-sub { font-size: 10px; color: #334155; }
.mmhp-spin { font-size: 20px; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.mmhp-reload-btn {
  margin-top: 4px;
  padding: 4px 14px;
  border-radius: 4px;
  border: 1px solid rgba(255,255,255,0.1);
  background: transparent;
  color: #64748b;
  font-size: 11px;
  cursor: pointer;
  font-family: inherit;
}
.mmhp-reload-btn:hover { background: rgba(255,255,255,0.05); color: #94a3b8; }

/* ── Header ─────────────────────────────────────────────────────────────────── */
.mmhp-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  background: rgba(255,255,255,0.02);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 7px;
  padding: 7px 12px;
  flex-wrap: wrap;
}
.mmhp-sep { width: 1px; height: 32px; background: rgba(255,255,255,0.07); flex-shrink: 0; }
.mmhp-kpi { display: flex; flex-direction: column; gap: 1px; min-width: 72px; }
.mmhp-kpi-lbl {
  font-size: 8px; font-weight: 700; color: #334155;
  letter-spacing: .07em; text-transform: uppercase;
}
.mmhp-kpi-val {
  font-size: 13px; font-weight: 700; color: #e2e8f0;
  letter-spacing: .01em; line-height: 1.1;
}
.mmhp-kpi-sub { font-size: 9px; color: #475569; }
.mmhp-kpi.kpi-buy  .mmhp-kpi-val,
.mmhp-kpi.kpi-buy  .mmhp-kpi-sub { color: #10b981; }
.mmhp-kpi.kpi-sell .mmhp-kpi-val,
.mmhp-kpi.kpi-sell .mmhp-kpi-sub { color: #f43f5e; }

.cyan    { color: #06b6d4 !important; }
.orange  { color: #f97316 !important; }
.emerald { color: #10b981 !important; }
.rose    { color: #f43f5e !important; }
.amber   { color: #fbbf24 !important; }
.slate   { color: #94a3b8 !important; }
.mmhp-loading-dot { animation: spin 1s linear infinite; display: inline-block; }

/* ── Controls ────────────────────────────────────────────────────────────────── */
.mmhp-controls { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.mmhp-ctrl-group { display: flex; flex-direction: column; gap: 2px; }
.mmhp-ctrl-lbl {
  font-size: 7px; color: #334155; font-weight: 700;
  text-transform: uppercase; letter-spacing: .06em;
}
.mmhp-ctrl-btns { display: flex; gap: 2px; }
.mmhp-btn {
  padding: 2px 7px;
  border-radius: 3px;
  border: 1px solid rgba(255,255,255,0.07);
  background: transparent;
  color: #475569;
  font-size: 9px; font-weight: 700;
  cursor: pointer;
  transition: all 0.13s;
  font-family: inherit;
}
.mmhp-btn.active { background: #0c1e38; border-color: #475569; color: #94a3b8; }
.mmhp-btn.loading { color: #f59e0b; border-color: rgba(245,158,11,0.3); }
.mmhp-btn:hover:not(.active):not(.loading) { background: rgba(255,255,255,0.04); color: #64748b; }
.mmhp-meta { font-size: 10px; color: #f59e0b; white-space: nowrap; margin-left: 4px; }
.mmhp-meta b { font-weight: 700; }

/* ── SABR model pill (header) ─────────────────────────────────────────────── */
.mmhp-sabr-pill {
  font-size: 8px; font-weight: 700; letter-spacing: .06em;
  padding: 2px 7px; border-radius: 10px;
  border: 1px solid transparent;
  white-space: nowrap; flex-shrink: 0; cursor: pointer;
  transition: all 0.15s;
}
.sabr-on      { color: #06b6d4; border-color: rgba(6,182,212,0.30);  background: rgba(6,182,212,0.07); }
.sabr-on:hover{ background: rgba(6,182,212,0.14); }
.sabr-loading { color: #f59e0b; border-color: rgba(245,158,11,0.30); background: rgba(245,158,11,0.07); animation: pulse 1.2s ease-in-out infinite; }
.sabr-error   { color: #f43f5e; border-color: rgba(244,63,94,0.30);  background: rgba(244,63,94,0.07); }
.sabr-error:hover { background: rgba(244,63,94,0.14); }
.sabr-off     { color: #475569; border-color: rgba(71,85,105,0.25);  background: transparent; }
.sabr-off:hover { background: rgba(255,255,255,0.04); }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.45; } }

/* ── Tracker pill (header) ─────────────────────────────────────────────────── */
.mmhp-tracker-pill {
  font-size: 8px; font-weight: 700; letter-spacing: .06em;
  padding: 2px 6px; border-radius: 10px;
  border: 1px solid transparent;
  white-space: nowrap; flex-shrink: 0;
}
.pill-on  { color: #10b981; border-color: rgba(16,185,129,0.28); background: rgba(16,185,129,0.07); }
.pill-off { color: #f43f5e; border-color: rgba(244,63,94,0.35);  background: rgba(244,63,94,0.08); cursor: pointer; }
.pill-off:hover { background: rgba(244,63,94,0.14); }
.pill-unk { color: #475569; border-color: rgba(71,85,105,0.3);  background: transparent; }

/* ── Tracker badge + restart btn (empty state) ─────────────────────────────── */
.mmhp-tracker-badge {
  font-size: 10px; font-weight: 700; padding: 3px 10px;
  border-radius: 8px; margin-top: 4px;
}
.badge-on  { color: #10b981; background: rgba(16,185,129,0.08); }
.badge-off { color: #f43f5e; background: rgba(244,63,94,0.08); }
.badge-unk { color: #475569; }
.badge-restart {
  color: #10b981 !important; border-color: rgba(16,185,129,0.35) !important;
}
.badge-restart:disabled { opacity: 0.5; cursor: wait; }

/* ── Gamma chart ─────────────────────────────────────────────────────────────── */
.mmhp-gamma-empty {
  display: flex; align-items: center; justify-content: center;
  height: 100%; color: #334155; font-size: 11px;
}
.mmhp-strike-close {
  margin-left: 8px;
  padding: 0 5px;
  border-radius: 3px;
  border: 1px solid rgba(255,255,255,0.07);
  background: transparent;
  color: #475569;
  font-size: 9px;
  cursor: pointer;
  font-family: inherit;
  vertical-align: middle;
  line-height: 1.6;
}
.mmhp-strike-close:hover { background: rgba(244,63,94,0.12); color: #f43f5e; border-color: rgba(244,63,94,0.3); }

/* ── Section labels ─────────────────────────────────────────────────────────── */
.mmhp-section-lbl {
  font-size: 9px; font-weight: 700; color: #334155;
  letter-spacing: .05em; text-transform: uppercase;
  padding: 0 2px; flex-shrink: 0;
}
.mmhp-sub-lbl { font-weight: 400; text-transform: none; color: #1e293b; margin-left: 4px; }

/* ── Charts ──────────────────────────────────────────────────────────────────── */
.mmhp-chart-wrap { position: relative; min-height: 0; display: flex; flex-direction: column; }
.mmhp-svg { flex: 1; width: 100%; min-height: 0; cursor: crosshair; overflow: visible; }

/* ── Tooltip ─────────────────────────────────────────────────────────────────── */
.mmhp-tt {
  position: absolute; pointer-events: none; transform: translateX(-50%);
  background: #080f1e; border: 1px solid rgba(255,255,255,0.13);
  border-radius: 6px; padding: 6px 10px;
  font-size: 10px; color: #e2e8f0; white-space: nowrap;
  z-index: 20; min-width: 160px; box-shadow: 0 4px 20px rgba(0,0,0,0.55);
}
.tt-head    { font-weight: 700; color: #f59e0b; margin-bottom: 4px; font-size: 11px; }
.tt-divider { height: 1px; background: rgba(255,255,255,0.07); margin: 4px 0; }
.tt-row     { display: flex; justify-content: space-between; gap: 12px; line-height: 1.65; }
.tt-lbl     { color: #475569; }
.tt-val     { color: #94a3b8; font-variant-numeric: tabular-nums; }
.tt-emerald { color: #10b981; font-weight: 700; font-variant-numeric: tabular-nums; }
.tt-rose    { color: #f43f5e; font-weight: 700; font-variant-numeric: tabular-nums; }
.tt-cyan    { color: #06b6d4; font-weight: 700; font-variant-numeric: tabular-nums; }
.tt-amber   { color: #f59e0b; font-weight: 700; font-variant-numeric: tabular-nums; }
</style>

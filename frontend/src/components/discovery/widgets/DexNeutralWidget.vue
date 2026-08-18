<template>
  <div class="dex-widget" ref="rootEl">
    <div v-if="!hasData" class="dex-empty">Sem dados de modelo</div>
    <template v-else>

      <!-- ── Info header ──────────────────────────────────────────────────────── -->
      <div class="dex-header">
        <div class="dex-kpi" :class="dexNeutralKpiClass">
          <span class="dex-kpi-lbl">DEX Neutral</span>
          <span class="dex-kpi-val">{{ dexNeutralFmt }}</span>
          <span class="dex-kpi-sub" v-if="dexNeutralDist != null">
            {{ dexNeutralDist >= 0 ? '+' : '' }}{{ dexNeutralDist.toFixed(0) }}pts
            ({{ (dexNeutralPct * 100).toFixed(2) }}%)
          </span>
        </div>

        <div class="dex-sep" />

        <div class="dex-kpi">
          <span class="dex-kpi-lbl">DEX @ Spot</span>
          <span class="dex-kpi-val" :class="dexAtSpot >= 0 ? 'cyan' : 'orange'">
            {{ fmtDex(dexAtSpot) }}
          </span>
          <span class="dex-kpi-sub" :class="dexAtSpot >= 0 ? 'cyan' : 'orange'">
            {{ dexAtSpot >= 0 ? 'long Δ' : 'short Δ' }}
          </span>
        </div>

        <div class="dex-sep" />

        <div class="dex-kpi">
          <span class="dex-kpi-lbl">Regime</span>
          <span class="dex-bias" :class="dexAtSpot >= 0 ? 'bias-long' : 'bias-short'">
            {{ dexAtSpot >= 0 ? '▲ Absorve' : '▼ Amplifica' }}
          </span>
          <span class="dex-kpi-sub">{{ dexAtSpot >= 0 ? 'vende rali' : 'compra queda' }}</span>
        </div>

        <div class="dex-sep" />

        <div class="dex-kpi">
          <span class="dex-kpi-lbl">DEX Total</span>
          <span class="dex-kpi-val" :class="totDex >= 0 ? 'cyan' : 'orange'">
            {{ fmtDex(totDex) }}
          </span>
          <span class="dex-kpi-sub">
            {{ totDexCall >= 0 ? '+' : '' }}{{ fmtDex(totDexCall) }} C &nbsp;
            {{ totDexPut  >= 0 ? '+' : '' }}{{ fmtDex(totDexPut)  }} P
          </span>
        </div>

        <!-- Intraday KPIs (só na aba Intraday, quando já tem curva) -->
        <template v-if="view === 'intraday' && intraCombinedCurve.length">
          <div class="dex-sep" />
          <div class="dex-kpi">
            <span class="dex-kpi-lbl">Neutro Intra</span>
            <span class="dex-kpi-val"
                  :class="intraNeutralNow > (spot ?? 0) ? 'cyan' : 'orange'">
              {{ fmtLevel(intraNeutralNow) }}
            </span>
            <span class="dex-kpi-sub">
              {{ (intraNeutralNow - (dexNeutralPrice ?? 0)) >= 0 ? '+' : '' }}{{ ((intraNeutralNow - (dexNeutralPrice ?? 0)) / 1000).toFixed(2) }}k vs modelo
            </span>
          </div>
          <div class="dex-sep" />
          <div class="dex-kpi">
            <span class="dex-kpi-lbl">Pressão @ Spot</span>
            <span class="dex-kpi-val"
                  :class="intraPressureAtSpot >= 0 ? 'cyan' : 'orange'">
              {{ fmtDex(intraPressureAtSpot) }}
            </span>
            <span class="dex-kpi-sub">
              {{ intraPressureAtSpot >= 0 ? 'long Γ · absorve' : 'short Γ · amplifica' }}
            </span>
          </div>
          <template v-if="intraNeutralZones.length">
            <div class="dex-sep" />
            <div class="dex-kpi">
              <span class="dex-kpi-lbl">HP Acima</span>
              <span class="dex-kpi-val cyan">{{ fmtLevel(hpAbove?.strike) }}</span>
              <span class="dex-kpi-sub">{{ fmtDex(hpAbove?.dex) }}</span>
            </div>
            <div class="dex-sep" />
            <div class="dex-kpi">
              <span class="dex-kpi-lbl">HP Abaixo</span>
              <span class="dex-kpi-val orange">{{ fmtLevel(hpBelow?.strike) }}</span>
              <span class="dex-kpi-sub">{{ fmtDex(hpBelow?.dex) }}</span>
            </div>
          </template>
        </template>

        <div style="flex:1" />

        <div class="dex-mode-btns">
          <button class="dex-btn" :class="{ active: view === 'curve' }"
                  @click="view = 'curve'">Curva</button>
          <button class="dex-btn" :class="{ active: view === 'strikes' }"
                  @click="view = 'strikes'">Strikes</button>
          <button class="dex-btn" :class="{ active: view === 'split' }"
                  @click="view = 'split'">Split</button>
          <button class="dex-btn dex-btn-intra" :class="{ active: view === 'intraday' }"
                  @click="view = 'intraday'; ensureIntraday()">
            <span v-if="intradayLoading" class="dex-spin">⟳</span>
            <span v-else>Intraday</span>
          </button>
        </div>
        <span class="dex-meta">Spot: <b>{{ spotFmt }}</b></span>
      </div>

      <!-- ── Curve view ───────────────────────────────────────────────────────── -->
      <div v-if="view === 'curve' || view === 'split'"
           class="dex-chart-wrap" :class="{ half: view === 'split' }">
        <svg class="dex-svg" :viewBox="`0 0 ${CW} ${CH}`" preserveAspectRatio="none"
             @mousemove="onHoverCurve" @mouseleave="hoverCurve = null">

          <rect v-if="posArea.w > 0"
                :x="posArea.x" :y="cPadT" :width="posArea.w" :height="cYZero - cPadT"
                fill="#06b6d4" fill-opacity="0.04" />
          <rect v-if="negArea.w > 0"
                :x="negArea.x" :y="cYZero" :width="negArea.w" :height="CH - cPadB - cYZero"
                fill="#f97316" fill-opacity="0.04" />

          <line v-for="t in cYTicks" :key="'cg' + t.val"
                :x1="cPadL" :x2="CW - cPadR" :y1="t.py" :y2="t.py"
                stroke="rgba(148,163,184,0.07)" stroke-width="1" stroke-dasharray="3,5" />
          <line :x1="cPadL" :x2="CW - cPadR" :y1="cYZero" :y2="cYZero"
                stroke="rgba(148,163,184,0.22)" stroke-width="1" stroke-dasharray="4,3" />

          <clipPath id="dex-clip-pos">
            <rect :x="cPadL" :y="cPadT" :width="CW - cPadL - cPadR" :height="cYZero - cPadT" />
          </clipPath>
          <path v-if="cAreaPath" :d="cAreaPath"
                fill="#06b6d4" fill-opacity="0.20" clip-path="url(#dex-clip-pos)" />
          <clipPath id="dex-clip-neg">
            <rect :x="cPadL" :y="cYZero" :width="CW - cPadL - cPadR" :height="CH - cPadB - cYZero" />
          </clipPath>
          <path v-if="cAreaPath" :d="cAreaPath"
                fill="#f97316" fill-opacity="0.20" clip-path="url(#dex-clip-neg)" />

          <path v-if="cLinePosPath" :d="cLinePosPath"
                stroke="#06b6d4" stroke-width="2" fill="none"
                stroke-linejoin="round" stroke-linecap="round"
                clip-path="url(#dex-clip-pos)" />
          <path v-if="cLineNegPath" :d="cLineNegPath"
                stroke="#f97316" stroke-width="2" fill="none"
                stroke-linejoin="round" stroke-linecap="round"
                clip-path="url(#dex-clip-neg)" />

          <g v-for="(zc, zi) in cZeroCrossings" :key="'zc' + zi">
            <line :x1="zc.x" :x2="zc.x" :y1="cPadT" :y2="CH - cPadB"
                  stroke="#fbbf24" stroke-width="1" stroke-dasharray="3,3" stroke-opacity="0.7" />
            <circle :cx="zc.x" :cy="cYZero" r="4.5"
                    fill="#fbbf24" fill-opacity="0.95" stroke="#060c18" stroke-width="1.5" />
            <text :x="zc.x + 5" :y="cPadT + 11"
                  fill="#fbbf24" font-size="9" font-weight="700">
              DEX N {{ (zc.strike / 1000).toFixed(1) }}k
            </text>
          </g>

          <line v-if="cSpotX != null" :x1="cSpotX" :x2="cSpotX" :y1="cPadT" :y2="CH - cPadB"
                stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="2,2" />
          <text v-if="cSpotX != null" :x="cSpotX + 3" :y="cPadT + 10"
                fill="#f59e0b" font-size="9" font-weight="600">Spot</text>

          <line v-if="hoverCurve"
                :x1="hoverCurve.svgX" :x2="hoverCurve.svgX" :y1="cPadT" :y2="CH - cPadB"
                stroke="rgba(255,255,255,0.25)" stroke-width="1" stroke-dasharray="2,2" />
          <circle v-if="hoverCurve"
                  :cx="hoverCurve.svgX" :cy="hoverCurve.svgY" r="3.5"
                  :fill="hoverCurve.val >= 0 ? '#06b6d4' : '#f97316'" fill-opacity="0.95" />

          <text v-for="p in cXLabels" :key="'cxl' + p.strike"
                :x="p.px" :y="CH - cPadB + 12"
                fill="#475569" font-size="8" text-anchor="middle">
            {{ (p.strike / 1000).toFixed(0) }}k
          </text>
          <text v-for="t in cYTicks" :key="'cyl' + t.val"
                :x="cPadL - 4" :y="t.py"
                fill="#334155" font-size="8" text-anchor="end" dominant-baseline="middle">
            {{ t.label }}
          </text>
        </svg>

        <div class="dex-tt" v-if="hoverCurve" :style="ttStyle(hoverCurve.px, hoverCurve.py)">
          <div class="tt-head">{{ (hoverCurve.strike / 1000).toFixed(2) }}k</div>
          <div class="tt-row">
            <span class="tt-lbl">DEX</span>
            <span class="tt-val" :class="hoverCurve.val >= 0 ? 'tt-cyan' : 'tt-orange'">
              {{ fmtDex(hoverCurve.val) }}
            </span>
          </div>
          <div class="tt-row" v-if="dexNeutralPrice != null">
            <span class="tt-lbl">vs Neutral</span>
            <span class="tt-val">
              {{ (hoverCurve.strike - dexNeutralPrice) >= 0 ? '+' : '' }}{{ (hoverCurve.strike - dexNeutralPrice).toFixed(0) }}pts
            </span>
          </div>
        </div>
      </div>

      <!-- ── Per-strike DEX bars ──────────────────────────────────────────────── -->
      <div v-if="view === 'strikes' || view === 'split'"
           class="dex-chart-wrap" :class="{ half: view === 'split' }">
        <svg class="dex-svg" :viewBox="`0 0 ${SW} ${SH}`" preserveAspectRatio="none"
             @mousemove="onHoverStrike" @mouseleave="hoverStrike = null">

          <line :x1="sPadL" :x2="SW - sPadR" :y1="sYZero" :y2="sYZero"
                stroke="rgba(255,255,255,0.15)" stroke-width="1" stroke-dasharray="3,3" />
          <line v-for="t in sYTicks" :key="'sg' + t.val"
                :x1="sPadL" :x2="SW - sPadR" :y1="t.py" :y2="t.py"
                stroke="rgba(148,163,184,0.06)" stroke-width="1" stroke-dasharray="3,5" />

          <g v-for="b in sBars" :key="'sb' + b.strike">
            <rect v-if="b.callH > 0"
                  :x="b.x" :y="b.callY" :width="sBarW - 1" :height="b.callH"
                  fill="#10b981" fill-opacity="0.75" rx="1" />
            <rect v-if="b.putH > 0"
                  :x="b.x" :y="b.putY" :width="sBarW - 1" :height="b.putH"
                  fill="#f87171" fill-opacity="0.75" rx="1" />
            <line v-if="b.netY != null"
                  :x1="b.x" :x2="b.x + sBarW - 1" :y1="b.netY" :y2="b.netY"
                  :stroke="b.net >= 0 ? '#06b6d4' : '#f97316'"
                  stroke-width="1.5" />
          </g>

          <line v-if="sSpotX != null" :x1="sSpotX" :x2="sSpotX" :y1="sPadT" :y2="SH - sPadB"
                stroke="#f59e0b" stroke-width="1.5" />

          <line v-if="hoverStrike"
                :x1="hoverStrike.svgX" :x2="hoverStrike.svgX" :y1="sPadT" :y2="SH - sPadB"
                stroke="rgba(255,255,255,0.3)" stroke-width="1" stroke-dasharray="2,2" />

          <text v-for="b in sLabelBars" :key="'sxl' + b.strike"
                :x="b.x + sBarW / 2" :y="SH - sPadB + 12"
                fill="#475569" font-size="8" text-anchor="middle">
            {{ (b.strike / 1000).toFixed(0) }}k
          </text>
          <text v-for="t in sYTicks" :key="'syl' + t.val"
                :x="sPadL - 4" :y="t.py"
                fill="#334155" font-size="8" text-anchor="end" dominant-baseline="middle">
            {{ t.label }}
          </text>
        </svg>

        <div class="dex-tt" v-if="hoverStrike" :style="ttStyle(hoverStrike.px, hoverStrike.py)">
          <div class="tt-head">{{ (hoverStrike.bar.strike / 1000).toFixed(2) }}k</div>
          <div class="tt-row">
            <span class="tt-lbl">DEX Call</span>
            <span class="tt-cyan">{{ fmtDex(hoverStrike.bar.dexCall) }}</span>
          </div>
          <div class="tt-row">
            <span class="tt-lbl">DEX Put</span>
            <span class="tt-orange">{{ fmtDex(hoverStrike.bar.dexPut) }}</span>
          </div>
          <div class="tt-row">
            <span class="tt-lbl">DEX Net</span>
            <span :class="hoverStrike.bar.net >= 0 ? 'tt-cyan' : 'tt-orange'">
              {{ fmtDex(hoverStrike.bar.net) }}
            </span>
          </div>
          <div class="tt-row" v-if="hoverStrike.bar.callOi || hoverStrike.bar.putOi">
            <span class="tt-lbl">OI C/P</span>
            <span class="tt-val">{{ fmtK(hoverStrike.bar.callOi) }} / {{ fmtK(hoverStrike.bar.putOi) }}</span>
          </div>
        </div>
      </div>

      <!-- ── Intraday Pressure Curve ──────────────────────────────────────────── -->
      <template v-if="view === 'intraday'">
        <div v-if="intradayLoading && !intraCombinedCurve.length" class="dex-empty">
          <span class="dex-spin" style="font-size:18px">⟳</span>
          <span style="margin-top:6px">Carregando movimentações do dia…</span>
        </div>

        <div v-else-if="!intradayEvents.length" class="dex-empty">
          <span>Sem movimentações registradas hoje</span>
          <button class="dex-reload-btn" @click="loadIntraday">⟳ Recarregar</button>
        </div>

        <template v-else>
          <div class="dex-section-lbl">
            Curva de Pressão DEX — Intraday
            <span class="dex-sub-lbl">
              — base modelo + fluxo do dia · ±3k do spot · neutro, HP e ação do dealer
            </span>
            <button class="dex-reload-btn dex-reload-inline"
                    :class="{ loading: intradayLoading }"
                    @click="loadIntraday">⟳</button>
          </div>

          <div class="dex-chart-wrap" style="flex:1.1; min-height:0">
            <svg class="dex-svg" :viewBox="`0 0 ${CW} ${ICH}`" preserveAspectRatio="none"
                 @mousemove="onHoverIntra" @mouseleave="hoverIntra = null">

              <defs>
                <clipPath id="ic-clip-pos">
                  <rect :x="icPadL" :y="icPadT"
                        :width="CW - icPadL - icPadR"
                        :height="Math.max(0, icYZero - icPadT)" />
                </clipPath>
                <clipPath id="ic-clip-neg">
                  <rect :x="icPadL" :y="icYZero"
                        :width="CW - icPadL - icPadR"
                        :height="Math.max(0, ICH - icPadB - icYZero)" />
                </clipPath>
              </defs>

              <!-- Y grid -->
              <line v-for="t in icYTicks" :key="'icyg'+t.val"
                    :x1="icPadL" :x2="CW - icPadR" :y1="t.py" :y2="t.py"
                    stroke="rgba(148,163,184,0.06)" stroke-width="1" stroke-dasharray="2,5" />

              <!-- Zero pressure line -->
              <line :x1="icPadL" :x2="CW - icPadR" :y1="icYZero" :y2="icYZero"
                    stroke="rgba(148,163,184,0.28)" stroke-width="1" stroke-dasharray="4,3" />
              <text :x="CW - icPadR + 2" :y="icYZero"
                    fill="#475569" font-size="7" dominant-baseline="middle">0</text>

              <!-- Zone labels (background callout) -->
              <text :x="icPadL + 6" :y="icPadT + 13"
                    fill="#06b6d4" font-size="8" font-weight="700" opacity="0.38">
                LONG Γ · Dealer Absorve (vende rali / compra queda)
              </text>
              <text :x="icPadL + 6" :y="ICH - icPadB - 6"
                    fill="#f97316" font-size="8" font-weight="700" opacity="0.38">
                SHORT Γ · Dealer Amplifica (compra rali / vende queda)
              </text>

              <!-- Model base curve (reference, faint dashed) -->
              <path v-if="intraModelBasePath"
                    :d="intraModelBasePath"
                    stroke="rgba(100,116,139,0.28)" stroke-width="1" fill="none"
                    stroke-dasharray="4,4" />

              <!-- Area fills -->
              <path v-if="intraCurveAreaPath" :d="intraCurveAreaPath"
                    fill="#06b6d4" fill-opacity="0.13" clip-path="url(#ic-clip-pos)" />
              <path v-if="intraCurveAreaPath" :d="intraCurveAreaPath"
                    fill="#f97316" fill-opacity="0.13" clip-path="url(#ic-clip-neg)" />

              <!-- Combined DEX curve (solid, bicolor) -->
              <path v-if="intraCurvePath" :d="intraCurvePath"
                    stroke="#06b6d4" stroke-width="2.5" fill="none"
                    stroke-linejoin="round" stroke-linecap="round"
                    clip-path="url(#ic-clip-pos)" />
              <path v-if="intraCurvePath" :d="intraCurvePath"
                    stroke="#f97316" stroke-width="2.5" fill="none"
                    stroke-linejoin="round" stroke-linecap="round"
                    clip-path="url(#ic-clip-neg)" />

              <!-- ── HP zones ─────────────────────────────────────────────────── -->
              <g v-for="(hp, hi) in intraHPZones" :key="'hp'+hi">
                <!-- Vertical guide from axis to peak -->
                <line :x1="hp.x" :x2="hp.x"
                      :y1="hp.dex > 0 ? icPadT + 2 : ICH - icPadB - 2"
                      :y2="hp.y"
                      :stroke="hp.dex > 0 ? '#06b6d4' : '#f97316'"
                      stroke-width="1" stroke-opacity="0.22" stroke-dasharray="2,3" />
                <!-- Peak dot -->
                <circle :cx="hp.x" :cy="hp.y" r="5"
                        :fill="hp.dex > 0 ? '#06b6d4' : '#f97316'"
                        fill-opacity="0.92" stroke="#060c18" stroke-width="1.5" />
                <!-- HP label (strike) -->
                <text :x="hp.x" :y="hp.dex > 0 ? hp.y - 9 : hp.y + 17"
                      :fill="hp.dex > 0 ? '#06b6d4' : '#f97316'"
                      font-size="8" font-weight="700" text-anchor="middle">
                  HP {{ fmtLevel(hp.strike) }}
                </text>
                <!-- Dealer action micro-label -->
                <text :x="hp.x" :y="hp.dex > 0 ? hp.y - 19 : hp.y + 27"
                      :fill="hp.dex > 0 ? '#06b6d4' : '#f97316'"
                      font-size="6.5" text-anchor="middle" opacity="0.65">
                  {{ hp.dex > 0 ? 'vende rali' : 'compra queda' }}
                </text>
              </g>

              <!-- ── Neutral crossings ───────────────────────────────────────── -->
              <g v-for="(nc, ni) in intraNeutralZones" :key="'icnc'+ni">
                <line :x1="nc.x" :x2="nc.x" :y1="icPadT" :y2="ICH - icPadB"
                      stroke="#fbbf24" stroke-width="1" stroke-dasharray="3,3" stroke-opacity="0.75" />
                <!-- Circle on zero line -->
                <circle :cx="nc.x" :cy="icYZero" r="5.5"
                        fill="#fbbf24" fill-opacity="0.95" stroke="#060c18" stroke-width="1.5" />
                <!-- Level above zero -->
                <text :x="nc.x" :y="icYZero - 12"
                      fill="#fbbf24" font-size="8.5" font-weight="700" text-anchor="middle">
                  {{ fmtLevel(nc.strike) }}
                </text>
                <!-- "Neutro" label below zero -->
                <text :x="nc.x" :y="icYZero + 18"
                      fill="#fbbf24" font-size="7" text-anchor="middle" opacity="0.85">
                  Neutro
                </text>
              </g>

              <!-- ── Spot line ───────────────────────────────────────────────── -->
              <line v-if="intraSpotX != null"
                    :x1="intraSpotX" :x2="intraSpotX" :y1="icPadT" :y2="ICH - icPadB"
                    stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="2,2" />
              <text v-if="intraSpotX != null"
                    :x="intraSpotX + 3" :y="icPadT + 10"
                    fill="#f59e0b" font-size="9" font-weight="600">Spot</text>

              <!-- Hover crosshair + dot -->
              <line v-if="hoverIntra"
                    :x1="hoverIntra.svgX" :x2="hoverIntra.svgX"
                    :y1="icPadT" :y2="ICH - icPadB"
                    stroke="rgba(255,255,255,0.22)" stroke-width="1" stroke-dasharray="2,2" />
              <circle v-if="hoverIntra"
                      :cx="hoverIntra.svgX" :cy="hoverIntra.svgY" r="3.5"
                      :fill="hoverIntra.val >= 0 ? '#06b6d4' : '#f97316'"
                      fill-opacity="0.95" />

              <!-- X axis labels (strikes) -->
              <text v-for="lbl in icXLabels" :key="'icxl'+lbl.strike"
                    :x="lbl.x" :y="ICH - icPadB + 12"
                    fill="#475569" font-size="8" text-anchor="middle">
                {{ (lbl.strike / 1000).toFixed(0) }}k
              </text>

              <!-- Y axis labels -->
              <text v-for="t in icYTicks" :key="'icyl'+t.val"
                    :x="icPadL - 4" :y="t.py"
                    fill="#334155" font-size="8" text-anchor="end" dominant-baseline="middle">
                {{ t.label }}
              </text>

              <!-- Legend (base vs combined) -->
              <line :x1="CW - icPadR - 80" :x2="CW - icPadR - 65"
                    :y1="icPadT + 8" :y2="icPadT + 8"
                    stroke="rgba(100,116,139,0.5)" stroke-width="1" stroke-dasharray="4,3" />
              <text :x="CW - icPadR - 62" :y="icPadT + 11"
                    fill="#64748b" font-size="7">Base modelo</text>
              <line :x1="CW - icPadR - 80" :x2="CW - icPadR - 65"
                    :y1="icPadT + 19" :y2="icPadT + 19"
                    stroke="#06b6d4" stroke-width="2" />
              <text :x="CW - icPadR - 62" :y="icPadT + 22"
                    fill="#94a3b8" font-size="7">Base + Intraday</text>
            </svg>

            <!-- Tooltip -->
            <div class="dex-tt" v-if="hoverIntra" :style="ttStyle(hoverIntra.px, hoverIntra.py)">
              <div class="tt-head">{{ (hoverIntra.strike / 1000).toFixed(2) }}k</div>
              <div class="tt-row">
                <span class="tt-lbl">DEX Total</span>
                <span :class="hoverIntra.val >= 0 ? 'tt-cyan' : 'tt-orange'">
                  {{ fmtDex(hoverIntra.val) }}
                </span>
              </div>
              <div class="tt-row">
                <span class="tt-lbl">Base Modelo</span>
                <span class="tt-val">{{ fmtDex(hoverIntra.dexBase) }}</span>
              </div>
              <div class="tt-row">
                <span class="tt-lbl">Fluxo Intra</span>
                <span :class="hoverIntra.dexIntra >= 0 ? 'tt-cyan' : 'tt-orange'">
                  {{ fmtDex(hoverIntra.dexIntra) }} ({{ hoverIntra.dexIntra >= 0 ? '+' : '' }}{{ hoverIntra.dexBase !== 0 ? ((hoverIntra.dexIntra / Math.abs(hoverIntra.dexBase)) * 100).toFixed(0) + '%' : 'N/A' }})
                </span>
              </div>
              <div class="tt-row" v-if="intraNeutralZones.length">
                <span class="tt-lbl">Δ Neutro</span>
                <span class="tt-val">
                  {{ (hoverIntra.strike - intraNeutralZones[0].strike) >= 0 ? '+' : '' }}{{ (hoverIntra.strike - intraNeutralZones[0].strike).toFixed(0) }}pts
                </span>
              </div>
              <div class="tt-row">
                <span class="tt-lbl">Dealer</span>
                <span :class="hoverIntra.val >= 0 ? 'tt-cyan' : 'tt-orange'">
                  {{ hoverIntra.val >= 0 ? 'Absorve mov.' : 'Amplifica mov.' }}
                </span>
              </div>
            </div>
          </div>

          <!-- ── Strikes do Diário (modelo, janela ±3k) ───────────────────────── -->
          <div class="dex-section-lbl" style="margin-top:2px">
            Strikes — Modelo Diário
            <span class="dex-sub-lbl">— DEX call/put por strike · mesma janela ±3k</span>
          </div>
          <div class="dex-chart-wrap" style="flex:0.85; min-height:0">
            <svg class="dex-svg" :viewBox="`0 0 ${CW} ${SH}`" preserveAspectRatio="none"
                 @mousemove="onHoverIntraStrike" @mouseleave="hoverIntraStrike = null">

              <line :x1="sPadL" :x2="CW - sPadR" :y1="isYZero" :y2="isYZero"
                    stroke="rgba(255,255,255,0.15)" stroke-width="1" stroke-dasharray="3,3" />
              <line v-for="t in isYTicks" :key="'isg'+t.val"
                    :x1="sPadL" :x2="CW - sPadR" :y1="t.py" :y2="t.py"
                    stroke="rgba(148,163,184,0.06)" stroke-width="1" stroke-dasharray="3,5" />

              <g v-for="b in isFilteredBars" :key="'isb'+b.strike">
                <rect v-if="b.callH > 0"
                      :x="b.x" :y="b.callY" :width="b.bW - 1" :height="b.callH"
                      fill="#10b981"
                      :fill-opacity="hoverIntraStrike?.strike === b.strike ? 1 : 0.72"
                      rx="1" />
                <rect v-if="b.putH > 0"
                      :x="b.x" :y="b.putY" :width="b.bW - 1" :height="b.putH"
                      fill="#f87171"
                      :fill-opacity="hoverIntraStrike?.strike === b.strike ? 1 : 0.72"
                      rx="1" />
                <line v-if="b.netY != null"
                      :x1="b.x" :x2="b.x + b.bW - 1" :y1="b.netY" :y2="b.netY"
                      :stroke="b.net >= 0 ? '#06b6d4' : '#f97316'"
                      stroke-width="1.5" />
                <!-- Hit area -->
                <rect :x="b.x - 2" :y="sPadT"
                      :width="b.bW + 4" :height="SH - sPadT - sPadB"
                      fill="transparent" style="cursor:crosshair"
                      @mouseenter="hoverIntraStrike = b"
                      @mouseleave="hoverIntraStrike = null" />
              </g>

              <!-- Spot line -->
              <line v-if="isSpotX != null"
                    :x1="isSpotX" :x2="isSpotX" :y1="sPadT" :y2="SH - sPadB"
                    stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="2,2" />
              <text v-if="isSpotX != null"
                    :x="isSpotX + 3" :y="sPadT + 10"
                    fill="#f59e0b" font-size="9" font-weight="600">Spot</text>

              <!-- Neutro marker (da curva combinada) -->
              <line v-if="isNeutralX != null"
                    :x1="isNeutralX" :x2="isNeutralX" :y1="sPadT" :y2="SH - sPadB"
                    stroke="#fbbf24" stroke-width="1" stroke-dasharray="3,3" stroke-opacity="0.7" />
              <circle v-if="isNeutralX != null"
                      :cx="isNeutralX" :cy="isYZero" r="4"
                      fill="#fbbf24" fill-opacity="0.9" stroke="#060c18" stroke-width="1.2" />
              <text v-if="isNeutralX != null"
                    :x="isNeutralX" :y="isYZero - 8"
                    fill="#fbbf24" font-size="7" font-weight="700" text-anchor="middle">Neutro</text>

              <!-- X labels -->
              <text v-for="b in isFilteredBars" :key="'isxl'+b.strike"
                    :x="b.x + b.bW / 2"
                    :y="SH - sPadB + 12"
                    :fill="hoverIntraStrike?.strike === b.strike ? '#e2e8f0' : '#475569'"
                    font-size="8" text-anchor="middle">
                {{ (b.strike / 1000).toFixed(0) }}k
              </text>

              <!-- Y labels -->
              <text v-for="t in isYTicks" :key="'isyl'+t.val"
                    :x="sPadL - 4" :y="t.py"
                    fill="#334155" font-size="8" text-anchor="end" dominant-baseline="middle">
                {{ t.label }}
              </text>
            </svg>

            <div class="dex-tt" v-if="hoverIntraStrike"
                 :style="ttStyle(hoverIntraStrike.x + hoverIntraStrike.bW / 2, SH * 0.4)">
              <div class="tt-head">{{ (hoverIntraStrike.strike / 1000).toFixed(2) }}k</div>
              <div class="tt-row">
                <span class="tt-lbl">DEX Call</span>
                <span class="tt-emerald">{{ fmtDex(hoverIntraStrike.dexCall) }}</span>
              </div>
              <div class="tt-row">
                <span class="tt-lbl">DEX Put</span>
                <span class="tt-rose">{{ fmtDex(hoverIntraStrike.dexPut) }}</span>
              </div>
              <div class="tt-row">
                <span class="tt-lbl">DEX Net</span>
                <span :class="hoverIntraStrike.net >= 0 ? 'tt-cyan' : 'tt-orange'">
                  {{ fmtDex(hoverIntraStrike.net) }}
                </span>
              </div>
              <div class="tt-row" v-if="hoverIntraStrike.callOi || hoverIntraStrike.putOi">
                <span class="tt-lbl">OI C/P</span>
                <span class="tt-val">{{ fmtK(hoverIntraStrike.callOi) }} / {{ fmtK(hoverIntraStrike.putOi) }}</span>
              </div>
            </div>
          </div>

        </template>
      </template>

    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { getVolumeActivity } from '@/api/options'

const props = defineProps({ modelData: { type: Object, default: null } })

// ─── Layout constants ─────────────────────────────────────────────────────────
const CW = 600; const CH = 200
const cPadL = 44; const cPadR = 12; const cPadT = 16; const cPadB = 24

const SW = 600; const SH = 180
const sPadL = 44; const sPadR = 10; const sPadT = 12; const sPadB = 24

// Intraday pressure curve
const ICH = 240
const icPadL = 50; const icPadR = 54; const icPadT = 20; const icPadB = 28

const IBOVE_TO_IBOV = 0.04
const STRIKE_ROUND  = 1_000
const REFRESH_MS    = 5 * 60_000

// ─── State ────────────────────────────────────────────────────────────────────
const view        = ref('split')
const hoverCurve  = ref(null)
const hoverStrike = ref(null)
const hoverIntra  = ref(null)
const rootEl      = ref(null)

// Intraday state
const intradayEvents    = ref([])
const intradayLoading   = ref(false)
const intradayLastFetch = ref(null)

// ─── Source data ──────────────────────────────────────────────────────────────
const pressure = computed(() => props.modelData?.pressure ?? null)
const spot     = computed(() => props.modelData?.market_context?.spot_price ?? null)
const spotFmt  = computed(() => spot.value ? (spot.value / 1000).toFixed(2) + 'k' : '—')
const byStrike = computed(() => props.modelData?.aggregates?.by_strike ?? [])
const totals   = computed(() => props.modelData?.aggregates?.totals ?? {})

const hasData = computed(() => {
  const c = pressure.value?.curve
  return Array.isArray(c) && c.length > 0
})

// ─── Curve data ───────────────────────────────────────────────────────────────
const curvePts = computed(() => {
  const raw = pressure.value?.curve ?? []
  return raw
    .map(p => ({ strike: parseFloat(p.strike ?? p.key ?? 0), dex: p.dex ?? 0 }))
    .filter(p => p.strike > 0)
    .sort((a, b) => a.strike - b.strike)
})

const cMinS   = computed(() => curvePts.value[0]?.strike ?? 0)
const cMaxS   = computed(() => curvePts.value[curvePts.value.length - 1]?.strike ?? 1)
const cMaxAbs = computed(() => Math.max(...curvePts.value.map(p => Math.abs(p.dex)), 1))
const cYZero  = computed(() => cPadT + (CH - cPadT - cPadB) / 2)

function cXOf(s) {
  const range = cMaxS.value - cMinS.value || 1
  return cPadL + ((s - cMinS.value) / range) * (CW - cPadL - cPadR)
}
function cYOf(v) {
  const half = (CH - cPadT - cPadB) / 2
  return cYZero.value - (v / cMaxAbs.value) * half
}

const cPoints = computed(() =>
  curvePts.value.map(p => ({ x: cXOf(p.strike), y: cYOf(p.dex), val: p.dex, strike: p.strike }))
)

const cAreaPath = computed(() => {
  const pts = cPoints.value; if (!pts.length) return null
  const yz = cYZero.value
  const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
  return `${line} L${pts.at(-1).x.toFixed(1)},${yz} L${pts[0].x.toFixed(1)},${yz} Z`
})
const cLinePosPath = computed(() => {
  const pts = cPoints.value; if (!pts.length) return null
  return pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
})
const cLineNegPath = computed(() => cLinePosPath.value)
const posArea = computed(() => ({ x: cPadL, w: CW - cPadL - cPadR }))
const negArea = computed(() => ({ x: cPadL, w: CW - cPadL - cPadR }))

const cZeroCrossings = computed(() => {
  const pts = cPoints.value
  return pts.slice(1).reduce((acc, pt, i) => {
    const prev = pts[i]
    if ((prev.val >= 0) !== (pt.val >= 0)) {
      const t = prev.val / (prev.val - pt.val)
      acc.push({ x: prev.x + t * (pt.x - prev.x), strike: prev.strike + t * (pt.strike - prev.strike) })
    }
    return acc
  }, [])
})

const dexNeutralPrice = computed(() => {
  const zcs = cZeroCrossings.value; if (!zcs.length) return null
  if (!spot.value) return zcs[0].strike
  return zcs.reduce((best, zc) =>
    Math.abs(zc.strike - spot.value) < Math.abs(best.strike - spot.value) ? zc : best
  ).strike
})

const dexNeutralFmt  = computed(() => dexNeutralPrice.value ? (dexNeutralPrice.value / 1000).toFixed(2) + 'k' : '—')
const dexNeutralDist = computed(() => (dexNeutralPrice.value && spot.value) ? dexNeutralPrice.value - spot.value : null)
const dexNeutralPct  = computed(() => (dexNeutralDist.value && spot.value) ? dexNeutralDist.value / spot.value : null)
const dexNeutralKpiClass = computed(() => !dexNeutralDist.value ? '' : dexNeutralDist.value > 0 ? 'kpi-above' : 'kpi-below')

const dexAtSpot = computed(() => {
  if (!spot.value || !curvePts.value.length) return 0
  return curvePts.value.reduce((best, p) =>
    Math.abs(p.strike - spot.value) < Math.abs(best.strike - spot.value) ? p : best
  ).dex
})

const totDex     = computed(() => totals.value.dex != null ? totals.value.dex : byStrike.value.reduce((s, r) => s + (r.dex ?? 0), 0))
const totDexCall = computed(() => byStrike.value.reduce((s, r) => s + (r.dex_call ?? 0), 0))
const totDexPut  = computed(() => byStrike.value.reduce((s, r) => s + (r.dex_put  ?? 0), 0))

const cSpotX = computed(() => {
  if (!spot.value || !curvePts.value.length) return null
  if (spot.value < cMinS.value || spot.value > cMaxS.value) return null
  return cXOf(spot.value)
})
const cXLabels = computed(() => {
  const step = Math.max(1, Math.floor(cPoints.value.length / 8))
  return cPoints.value.filter((_, i) => i % step === 0).map(p => ({ strike: p.strike, px: p.x }))
})
const cYTicks = computed(() => {
  const m = cMaxAbs.value
  return [m, m * 0.5, 0, -m * 0.5, -m].map(v => ({ val: v, py: cYOf(v), label: fmtDex(v) }))
})

// ─── Per-strike data ──────────────────────────────────────────────────────────
const strikeRows = computed(() =>
  byStrike.value
    .map(r => ({
      strike: parseFloat(r.key ?? r.strike),
      dexCall: r.dex_call ?? 0, dexPut: r.dex_put ?? 0,
      net: r.dex ?? ((r.dex_call ?? 0) + (r.dex_put ?? 0)),
      callOi: r.call_oi ?? 0, putOi: r.put_oi ?? 0,
    }))
    .filter(r => r.strike > 0)
    .sort((a, b) => a.strike - b.strike)
)

const sMaxAbs = computed(() => Math.max(...strikeRows.value.flatMap(r => [Math.abs(r.dexCall), Math.abs(r.dexPut)]), 1))
const sBarW   = computed(() => strikeRows.value.length ? (SW - sPadL - sPadR) / strikeRows.value.length : 0)
const sYZero  = computed(() => sPadT + (SH - sPadT - sPadB) / 2)

function sYOf(v, maxAbs) {
  return sYZero.value - (v / (maxAbs || 1)) * ((SH - sPadT - sPadB) / 2)
}

const sBars = computed(() => strikeRows.value.map((r, i) => {
  const x     = sPadL + i * sBarW.value
  const callY1 = sYOf(r.dexCall, sMaxAbs.value), callY0 = sYZero.value
  const putY1  = sYOf(r.dexPut,  sMaxAbs.value), putY0  = sYZero.value
  return {
    strike: r.strike, x, sBarW: sBarW.value,
    callY: Math.min(callY1, callY0), callH: Math.max(Math.abs(callY1 - callY0), 1),
    putY:  Math.min(putY1,  putY0),  putH:  Math.max(Math.abs(putY1  - putY0),  1),
    netY:  r.net !== 0 ? sYOf(r.net, sMaxAbs.value) : null,
    net: r.net, dexCall: r.dexCall, dexPut: r.dexPut, callOi: r.callOi, putOi: r.putOi,
  }
}))

const sSpotX = computed(() => {
  if (!spot.value || !strikeRows.value.length) return null
  const rows = strikeRows.value
  let loIdx = -1
  for (let i = 0; i < rows.length; i++) { if (rows[i].strike <= spot.value) loIdx = i }
  if (loIdx < 0 || loIdx >= rows.length - 1) return null
  const t = (spot.value - rows[loIdx].strike) / (rows[loIdx + 1].strike - rows[loIdx].strike)
  return sPadL + loIdx * sBarW.value + sBarW.value / 2 + t * sBarW.value
})

const sLabelBars = computed(() => {
  const step = Math.max(1, Math.floor(sBars.value.length / 10))
  return sBars.value.filter((_, i) => i % step === 0)
})
const sYTicks = computed(() => {
  const m = sMaxAbs.value
  return [m, m * 0.5, 0, -m * 0.5, -m].map(v => ({ val: v, py: sYOf(v, m), label: fmtDex(v) }))
})

// ─── Intraday: BRT time helpers ───────────────────────────────────────────────
function brtDateStr() {
  return new Date().toLocaleDateString('sv-SE', { timeZone: 'America/Sao_Paulo' })
}
function mkBrtTs(hh, mm = 0) {
  const d = brtDateStr()
  return new Date(`${d}T${String(hh).padStart(2,'0')}:${String(mm).padStart(2,'0')}:00-03:00`).getTime()
}
const MKT_OPEN = computed(() => mkBrtTs(10, 0))

// ─── Intraday: BS delta approximation ─────────────────────────────────────────
function _normCDF(x) {
  // Abramowitz & Stegun §26.2.17 rational approximation (max |ε| < 7.5e-8)
  const t    = 1 / (1 + 0.2316419 * Math.abs(x))
  const poly = t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))))
  const cdf  = 1 - (Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI)) * poly
  return x >= 0 ? cdf : 1 - cdf
}

function bsDeltaApprox(pc, S, K, sigma, T) {
  if (!S || !K || sigma <= 0 || T <= 0) return pc === 'C' ? 0.5 : -0.5
  const d1 = (Math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * Math.sqrt(T))
  const nd1 = _normCDF(d1)
  return pc === 'P' ? nd1 - 1 : nd1
}

function getDeltaIntra(ev) {
  const pc = (ev.put_call ?? 'C').toUpperCase()[0] === 'P' ? 'P' : 'C'
  if (ev.observed_delta != null) return Math.max(-1, Math.min(1, parseFloat(ev.observed_delta)))
  const S     = parseFloat(ev.spot_price ?? 0) || spot.value || 130_000
  const K     = parseFloat(ev.strike ?? 0)
  const ctx   = props.modelData?.market_context ?? {}
  const sigma = ctx.implied_vol ?? 0.20
  const T     = Math.max((ctx.days_to_expiry ?? (ev.days_to_maturity ?? 21)) / 252, 1 / 252)
  if (!K) return pc === 'C' ? 0.5 : -0.5
  return Math.max(-1, Math.min(1, bsDeltaApprox(pc, S, K, sigma, T)))
}

// ─── Intraday: DEX flow per strike (accumulated from today's events) ──────────
const intradayDexFlowByStrike = computed(() => {
  const map = {}
  for (const ev of intradayEvents.value) {
    const rawTs = ev.captured_at
    if (rawTs && rawTs.length > 10) {
      const ts = new Date(rawTs).getTime()
      if (!isNaN(ts) && ts < MKT_OPEN.value) continue
    }
    const vol = parseFloat(ev.volume_delta ?? 0); if (vol < 1) continue
    const K   = parseFloat(ev.strike ?? 0);       if (!K) continue
    const pc  = (ev.put_call ?? 'C').toUpperCase()[0] === 'P' ? 'P' : 'C'
    const d   = getDeltaIntra(ev)
    const kr  = Math.round(K / STRIKE_ROUND) * STRIKE_ROUND
    if (!map[kr]) map[kr] = { dexCall: 0, dexPut: 0, net: 0, vol: 0 }
    const dex = d * vol
    if (pc === 'C') map[kr].dexCall += dex
    else            map[kr].dexPut  += dex
    map[kr].net += dex
    map[kr].vol += vol
  }
  return map
})

// ─── Intraday: Combined pressure curve (model base + intraday flow) ───────────
// Restringe a janela a ±3k pontos do spot — foco no range operacional imediato
const INTRA_WINDOW = 3_000

const intraCombinedCurve = computed(() => {
  const base = curvePts.value
  const flow = intradayDexFlowByStrike.value
  if (!base.length) return []
  const S    = spot.value
  const lo   = S ? S - INTRA_WINDOW : -Infinity
  const hi   = S ? S + INTRA_WINDOW :  Infinity
  return base
    .filter(p => p.strike >= lo && p.strike <= hi)
    .map(p => {
      const kr       = Math.round(p.strike / STRIKE_ROUND) * STRIKE_ROUND
      const dexIntra = (flow[kr]?.net ?? 0) * IBOVE_TO_IBOV
      return { strike: p.strike, dexBase: p.dex, dexIntra, dex: p.dex + dexIntra }
    })
})

// SVG coordinate system for intraday chart
const icMinS   = computed(() => intraCombinedCurve.value[0]?.strike ?? cMinS.value)
const icMaxS   = computed(() => intraCombinedCurve.value.at(-1)?.strike ?? cMaxS.value)
const icMaxAbs = computed(() => {
  const vals = intraCombinedCurve.value.flatMap(p => [Math.abs(p.dex), Math.abs(p.dexBase)])
  return Math.max(...vals, cMaxAbs.value, 1)
})
const icYZero  = computed(() => icPadT + (ICH - icPadT - icPadB) / 2)

function icXOf(s) {
  return icPadL + ((s - icMinS.value) / (icMaxS.value - icMinS.value || 1)) * (CW - icPadL - icPadR)
}
function icYOf(v) {
  return icYZero.value - (v / icMaxAbs.value) * ((ICH - icPadT - icPadB) / 2)
}

const intraCurvePoints = computed(() =>
  intraCombinedCurve.value.map(p => ({
    x: icXOf(p.strike), y: icYOf(p.dex),
    val: p.dex, dexBase: p.dexBase, dexIntra: p.dexIntra, strike: p.strike
  }))
)

const intraCurvePath = computed(() => {
  const pts = intraCurvePoints.value; if (pts.length < 2) return null
  return pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
})

const intraCurveAreaPath = computed(() => {
  const pts = intraCurvePoints.value; if (pts.length < 2) return null
  const yz   = icYZero.value
  const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
  return `${line} L${pts.at(-1).x.toFixed(1)},${yz} L${pts[0].x.toFixed(1)},${yz} Z`
})

const intraModelBasePath = computed(() => {
  const base = curvePts.value; if (base.length < 2) return null
  return base.map((p, i) => {
    const x = icXOf(p.strike), y = icYOf(p.dex)
    return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
})

// ─── Intraday: zero crossings (neutral zones) ─────────────────────────────────
const intraNeutralZones = computed(() => {
  const pts = intraCurvePoints.value
  const crossings = []
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1], b = pts[i]
    if ((a.val >= 0) !== (b.val >= 0)) {
      const t = a.val / (a.val - b.val)
      crossings.push({
        x:      a.x      + t * (b.x      - a.x),
        strike: a.strike + t * (b.strike  - a.strike),
      })
    }
  }
  // Keep crossings within ±30k of spot, cap at 4
  return crossings
    .filter(nc => !spot.value || Math.abs(nc.strike - spot.value) < 30_000)
    .slice(0, 4)
})

// ─── Intraday: local extrema (HP zones) ──────────────────────────────────────
const intraHPZones = computed(() => {
  const pts = intraCurvePoints.value
  if (pts.length < 5) return []
  const threshold = icMaxAbs.value * 0.22   // only mark significant peaks

  // Smooth with 3-point moving average before peak detection
  const smooth = pts.map((p, i) => {
    if (i === 0 || i === pts.length - 1) return p
    return { ...p, val: (pts[i-1].val + p.val + pts[i+1].val) / 3 }
  })

  const peaks = []
  for (let i = 2; i < smooth.length - 2; i++) {
    const v = smooth[i].val
    const isMax = v > threshold
      && v >= smooth[i-1].val && v >= smooth[i+1].val
      && v >= smooth[i-2].val && v >= smooth[i+2].val
    const isMin = v < -threshold
      && v <= smooth[i-1].val && v <= smooth[i+1].val
      && v <= smooth[i-2].val && v <= smooth[i+2].val
    if (isMax || isMin) {
      peaks.push({
        x: pts[i].x, y: pts[i].y,
        strike: pts[i].strike,
        dex: pts[i].val,
        type: isMax ? 'max' : 'min',
      })
    }
  }

  // Deduplicate: keep dominant peak in each 8k-wide cluster
  const deduped = []
  for (const pk of peaks) {
    const neighbor = deduped.find(d => Math.abs(d.strike - pk.strike) < 8_000)
    if (!neighbor) deduped.push(pk)
    else if (Math.abs(pk.dex) > Math.abs(neighbor.dex)) Object.assign(neighbor, pk)
  }

  return deduped.slice(0, 6)
})

// ─── Intraday: KPI values ─────────────────────────────────────────────────────
const intraNeutralNow = computed(() => {
  const zones = intraNeutralZones.value
  if (!zones.length) return dexNeutralPrice.value ?? 0
  if (!spot.value)   return zones[0].strike
  return zones.reduce((best, nc) =>
    Math.abs(nc.strike - spot.value) < Math.abs(best.strike - spot.value) ? nc : best
  ).strike
})

const intraPressureAtSpot = computed(() => {
  if (!spot.value || !intraCombinedCurve.value.length) return 0
  return intraCombinedCurve.value.reduce((best, p) =>
    Math.abs(p.strike - spot.value) < Math.abs(best.strike - spot.value) ? p : best
  ).dex
})

// HP zones above and below spot
const hpAbove = computed(() => {
  if (!spot.value) return null
  return intraHPZones.value
    .filter(hp => hp.strike > spot.value)
    .sort((a, b) => a.strike - b.strike)[0] ?? null
})
const hpBelow = computed(() => {
  if (!spot.value) return null
  return intraHPZones.value
    .filter(hp => hp.strike < spot.value)
    .sort((a, b) => b.strike - a.strike)[0] ?? null
})

const intraSpotX = computed(() => {
  if (!spot.value) return null
  const x = icXOf(spot.value)
  return (x >= icPadL && x <= CW - icPadR) ? x : null
})

const icXLabels = computed(() => {
  const pts  = intraCurvePoints.value
  const step = Math.max(1, Math.floor(pts.length / 8))
  return pts.filter((_, i) => i % step === 0).map(p => ({ strike: p.strike, x: p.x }))
})

const icYTicks = computed(() => {
  const m = icMaxAbs.value
  return [m, m * 0.5, 0, -m * 0.5, -m].map(v => ({
    val: v, py: icYOf(v), label: fmtDex(v)
  }))
})

// ─── Intraday: strikes do modelo filtrados ±3k ────────────────────────────────
const hoverIntraStrike = ref(null)

const isFilteredRows = computed(() => {
  const S  = spot.value
  const lo = S ? S - INTRA_WINDOW : -Infinity
  const hi = S ? S + INTRA_WINDOW :  Infinity
  return strikeRows.value.filter(r => r.strike >= lo && r.strike <= hi)
})

const isMaxAbs = computed(() =>
  Math.max(...isFilteredRows.value.flatMap(r => [Math.abs(r.dexCall), Math.abs(r.dexPut)]), 1)
)
const isYZero = computed(() => sPadT + (SH - sPadT - sPadB) / 2)

function isYOf(v) {
  return isYZero.value - (v / isMaxAbs.value) * ((SH - sPadT - sPadB) / 2)
}

const isFilteredBars = computed(() => {
  const rows = isFilteredRows.value
  if (!rows.length) return []
  const inner = CW - sPadL - sPadR
  const bW    = Math.max(6, Math.min(40, Math.floor(inner / rows.length) - 2))
  const step  = rows.length > 1 ? inner / (rows.length - 1) : inner

  return rows.map((r, i) => {
    const x     = rows.length > 1 ? sPadL + i * step - bW / 2 : (CW - bW) / 2
    const y0    = isYZero.value
    const callY1 = isYOf(r.dexCall), putY1 = isYOf(r.dexPut)
    return {
      strike: r.strike, x, bW,
      callY: Math.min(callY1, y0), callH: Math.max(Math.abs(callY1 - y0), 1),
      putY:  Math.min(putY1,  y0), putH:  Math.max(Math.abs(putY1  - y0), 1),
      netY:  r.net !== 0 ? isYOf(r.net) : null,
      net: r.net, dexCall: r.dexCall, dexPut: r.dexPut, callOi: r.callOi, putOi: r.putOi,
    }
  })
})

// Spot X no gráfico de strikes filtrado
const isSpotX = computed(() => {
  const rows = isFilteredRows.value
  if (!spot.value || rows.length < 2) return null
  const mn = rows[0].strike, mx = rows.at(-1).strike
  return sPadL + ((spot.value - mn) / (mx - mn || 1)) * (CW - sPadL - sPadR)
})

// Neutro intraday projetado no mesmo eixo X
const isNeutralX = computed(() => {
  const rows = isFilteredRows.value
  if (!intraNeutralNow.value || rows.length < 2) return null
  const mn = rows[0].strike, mx = rows.at(-1).strike
  const x  = sPadL + ((intraNeutralNow.value - mn) / (mx - mn || 1)) * (CW - sPadL - sPadR)
  return (x >= sPadL && x <= CW - sPadR) ? x : null
})

const isYTicks = computed(() => {
  const m = isMaxAbs.value
  return [m, m * 0.5, 0, -m * 0.5, -m].map(v => ({
    val: v, py: isYOf(v), label: fmtDex(v)
  }))
})

function onHoverIntraStrike(e) {
  const bars = isFilteredBars.value; if (!bars.length) return
  const rect = e.currentTarget.getBoundingClientRect()
  const svgX = (e.clientX - rect.left) / rect.width * CW
  let nearest = null, minD = Infinity
  for (const b of bars) {
    const cx = b.x + b.bW / 2
    const d  = Math.abs(cx - svgX)
    if (d < minD) { minD = d; nearest = b }
  }
  hoverIntraStrike.value = nearest
}

// ─── Intraday data fetch ──────────────────────────────────────────────────────
async function loadIntraday() {
  if (intradayLoading.value) return
  intradayLoading.value = true
  try {
    const today = brtDateStr()
    const res   = await getVolumeActivity({ session_date: today, limit: 5000 })
    const rows  = res?.data?.data ?? res?.data ?? []
    const open  = MKT_OPEN.value
    intradayEvents.value = rows.filter(ev => {
      const rawTs = ev.captured_at ?? ev.session_date ?? ''
      if (!rawTs) return true
      const ts = new Date(rawTs).getTime()
      if (isNaN(ts) || rawTs.length <= 10) return true
      return ts >= open
    })
    intradayLastFetch.value = Date.now()
  } catch (e) {
    console.warn('[DexNeutral] intraday fetch failed', e)
  } finally {
    intradayLoading.value = false
  }
}

function ensureIntraday() {
  if (!intradayEvents.value.length && !intradayLoading.value) loadIntraday()
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────
let pollTimer = null
onMounted(() => {
  pollTimer = setInterval(() => {
    if (view.value === 'intraday') loadIntraday()
  }, REFRESH_MS)
})
onUnmounted(() => clearInterval(pollTimer))

// ─── Hover handlers ───────────────────────────────────────────────────────────
function onHoverCurve(e) {
  if (!cPoints.value.length) return
  const rect = e.currentTarget.getBoundingClientRect()
  const px   = e.clientX - rect.left
  const svgX = px / rect.width * CW
  if (svgX < cPadL || svgX > CW - cPadR) { hoverCurve.value = null; return }
  let nearest = null, minD = Infinity
  for (const p of cPoints.value) { const d = Math.abs(p.x - svgX); if (d < minD) { minD = d; nearest = p } }
  if (!nearest) return
  hoverCurve.value = { px, py: e.clientY - rect.top, svgX: nearest.x, svgY: nearest.y, val: nearest.val, strike: nearest.strike }
}

function onHoverStrike(e) {
  if (!sBars.value.length) return
  const rect = e.currentTarget.getBoundingClientRect()
  const px   = e.clientX - rect.left
  const svgX = px / rect.width * SW
  if (svgX < sPadL || svgX > SW - sPadR) { hoverStrike.value = null; return }
  const i = Math.max(0, Math.min(sBars.value.length - 1, Math.floor((svgX - sPadL) / sBarW.value)))
  hoverStrike.value = { px, py: e.clientY - rect.top, svgX: sPadL + i * sBarW.value + sBarW.value / 2, bar: sBars.value[i] }
}

function onHoverIntra(e) {
  const pts = intraCurvePoints.value; if (!pts.length) return
  const rect = e.currentTarget.getBoundingClientRect()
  const px   = e.clientX - rect.left
  const svgX = px / rect.width * CW
  if (svgX < icPadL || svgX > CW - icPadR) { hoverIntra.value = null; return }
  let nearest = null, minD = Infinity
  for (const p of pts) { const d = Math.abs(p.x - svgX); if (d < minD) { minD = d; nearest = p } }
  if (!nearest) return
  hoverIntra.value = {
    px, py: e.clientY - rect.top,
    svgX: nearest.x, svgY: nearest.y,
    ...nearest,
  }
}

function ttStyle(px, py) {
  const rootW = rootEl.value?.offsetWidth ?? 400
  return { left: Math.max(75, Math.min(rootW - 75, px)) + 'px', top: Math.max(8, py - 95) + 'px' }
}

// ─── Formatters ───────────────────────────────────────────────────────────────
function fmtDex(v) {
  if (v == null || !isFinite(v)) return '—'
  const abs = Math.abs(v), sign = v < 0 ? '-' : ''
  if (abs >= 1e9) return sign + (abs / 1e9).toFixed(2) + 'B'
  if (abs >= 1e6) return sign + (abs / 1e6).toFixed(2) + 'M'
  if (abs >= 1e3) return sign + (abs / 1e3).toFixed(1) + 'K'
  return v.toFixed(1)
}
function fmtK(v) {
  if (!v) return '—'
  if (v >= 1e6) return (v / 1e6).toFixed(1) + 'M'
  if (v >= 1e3) return (v / 1e3).toFixed(0) + 'K'
  return String(v)
}
function fmtLevel(v) {
  if (!v) return '—'
  return Math.abs(v) >= 1000 ? (v / 1000).toFixed(2) + 'k' : v.toFixed(0)
}
</script>

<style scoped>
.dex-widget {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 8px;
  gap: 6px;
  background: #05101c;
  color: #e2e8f0;
  font-family: "JetBrains Mono", monospace;
  overflow: hidden;
}
.dex-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: #475569;
  font-size: 12px;
}
.dex-spin { animation: spin 1s linear infinite; display: inline-block; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Header ─────────────────────────────────────────────────────────────────── */
.dex-header {
  display: flex; align-items: center; gap: 8px; flex-shrink: 0;
  background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.06);
  border-radius: 7px; padding: 7px 12px; flex-wrap: wrap;
}
.dex-sep { width: 1px; height: 32px; background: rgba(255,255,255,0.07); flex-shrink: 0; }
.dex-kpi { display: flex; flex-direction: column; gap: 1px; min-width: 78px; }
.dex-kpi-lbl { font-size: 8px; font-weight: 700; color: #334155; letter-spacing: .07em; text-transform: uppercase; }
.dex-kpi-val { font-size: 15px; font-weight: 700; color: #e2e8f0; letter-spacing: .01em; line-height: 1.1; }
.dex-kpi-sub { font-size: 9px; color: #475569; letter-spacing: .02em; }
.dex-kpi.kpi-above .dex-kpi-val { color: #06b6d4; }
.dex-kpi.kpi-below .dex-kpi-val { color: #f97316; }
.cyan    { color: #06b6d4 !important; }
.orange  { color: #f97316 !important; }
.emerald { color: #10b981 !important; }
.rose    { color: #f43f5e !important; }

.dex-bias { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 4px; letter-spacing: .03em; }
.bias-long  { background: rgba(6,182,212,0.12);  color: #06b6d4;  border: 1px solid rgba(6,182,212,0.25); }
.bias-short { background: rgba(249,115,22,0.12); color: #f97316; border: 1px solid rgba(249,115,22,0.25); }

.dex-mode-btns { display: flex; gap: 3px; }
.dex-btn {
  padding: 3px 8px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.08);
  background: transparent; color: #64748b; font-size: 9px; font-weight: 700;
  cursor: pointer; transition: all 0.15s; font-family: inherit;
}
.dex-btn.active { background: #0c1e38; border-color: #06b6d4; color: #06b6d4; }
.dex-btn:hover:not(.active) { background: rgba(255,255,255,0.05); color: #94a3b8; }
.dex-btn-intra.active { border-color: #fbbf24; color: #fbbf24; background: rgba(251,191,36,0.08); }
.dex-meta { font-size: 10px; color: #f59e0b; white-space: nowrap; margin-left: 4px; }
.dex-meta b { font-weight: 700; }

/* ── Section labels ──────────────────────────────────────────────────────────── */
.dex-section-lbl {
  font-size: 9px; font-weight: 700; color: #334155;
  letter-spacing: .05em; text-transform: uppercase;
  padding: 0 2px; flex-shrink: 0; display: flex; align-items: center; gap: 4px;
}
.dex-sub-lbl { font-weight: 400; text-transform: none; color: #1e293b; font-size: 8px; }

/* ── Reload button ───────────────────────────────────────────────────────────── */
.dex-reload-btn {
  padding: 4px 12px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.1);
  background: transparent; color: #64748b; font-size: 11px; cursor: pointer; font-family: inherit;
}
.dex-reload-btn:hover { background: rgba(255,255,255,0.05); color: #94a3b8; }
.dex-reload-inline {
  padding: 1px 5px; font-size: 9px; margin-left: 4px; border-radius: 3px;
}
.dex-reload-inline.loading { color: #f59e0b; border-color: rgba(245,158,11,0.3); }

/* ── Chart areas ────────────────────────────────────────────────────────────── */
.dex-chart-wrap {
  position: relative; flex: 1; min-height: 0;
  display: flex; flex-direction: column;
}
.dex-chart-wrap.half { flex: 0 0 calc(50% - 3px); }
.dex-svg { flex: 1; width: 100%; min-height: 0; cursor: crosshair; overflow: visible; }

/* ── Tooltip ───────────────────────────────────────────────────────────────── */
.dex-tt {
  position: absolute; pointer-events: none; transform: translateX(-50%);
  background: #080f1e; border: 1px solid rgba(255,255,255,0.13);
  border-radius: 6px; padding: 6px 10px; font-size: 10px; color: #e2e8f0;
  white-space: nowrap; z-index: 20; min-width: 150px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.55);
}
.tt-head    { font-weight: 700; color: #f59e0b; margin-bottom: 4px; font-size: 11px; }
.tt-row     { display: flex; justify-content: space-between; gap: 14px; line-height: 1.65; }
.tt-lbl     { color: #475569; }
.tt-val     { font-variant-numeric: tabular-nums; color: #94a3b8; }
.tt-cyan    { color: #06b6d4; font-weight: 700; font-variant-numeric: tabular-nums; }
.tt-orange  { color: #f97316; font-weight: 700; font-variant-numeric: tabular-nums; }
.tt-emerald { color: #10b981; font-weight: 700; font-variant-numeric: tabular-nums; }
.tt-rose    { color: #f43f5e; font-weight: 700; font-variant-numeric: tabular-nums; }
</style>

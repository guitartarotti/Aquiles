<template>
  <div class="vs-root" ref="rootEl">
    <div class="vs-controls">
      <!-- Surface type -->
      <button v-for="sm in surfaceModes" :key="sm.key"
              class="vs-btn" :class="{ active: surfaceMode === sm.key }"
              @click="surfaceMode = sm.key">{{ sm.label }}</button>
      <div class="vs-divider" />
      <!-- Color mode (IV only) -->
      <template v-if="surfaceMode === 'iv'">
        <button v-for="cm in colorModes" :key="cm.key"
                class="vs-btn sm" :class="{ active: colorMode === cm.key }"
                @click="colorMode = cm.key">{{ cm.label }}</button>
        <div class="vs-divider" />
      </template>
      <label class="vs-chk"><input type="checkbox" v-model="showWire" /> Wire</label>
      <button class="vs-btn" style="font-size:13px;padding:1px 6px" @click="resetCamera">⟳</button>
      <button class="vs-btn" @click="reloadAll">↺</button>
      <span class="vs-info" v-if="!loading">
        {{ sliceCount }} venc · {{ totalPts }} pts
      </span>
      <span class="vs-loading" v-if="loading">Carregando…</span>
      <span class="vs-error"  v-if="errorMsg && !loading">{{ errorMsg }}</span>
    </div>

    <div class="vs-canvas-wrap" ref="wrapEl">
      <canvas ref="canvasEl" class="vs-canvas"
              @mousedown.prevent="onMouseDown"
              @touchstart.prevent="onTouchStart"
              @wheel.prevent="onWheel"
              @dblclick="resetCamera" />
      <div class="vs-empty" v-if="!loading && !hasData">
        {{ errorMsg || (surfaceMode === 'iv' ? 'Sem dados de IV' : 'Execute o modelo para ver exposição') }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { getSnapshotByStrike } from '@/api/options'

const props = defineProps({ modelData: { type: Object, default: null } })

// ─── Layout padding (fixed 2D axis strips) ────────────────────────────────────
const PAD_L = 52, PAD_R = 60, PAD_T = 14, PAD_B = 30

// ─── Surface / color mode ─────────────────────────────────────────────────────
const surfaceMode  = ref('iv')
const surfaceModes = [
  { key: 'iv',  label: 'IV Smile' },
  { key: 'gex', label: 'GEX'      },
  { key: 'dex', label: 'DEX'      },
]
const colorMode  = ref('iv')
const colorModes = [{ key: 'iv', label: 'IV' }, { key: 'term', label: 'Prazo' }]

const showWire = ref(true)

// ─── Camera ───────────────────────────────────────────────────────────────────
const wrapEl   = ref(null)
const canvasEl = ref(null)
const rotX = ref(-0.42), rotY = ref(0.52), scale = ref(110), panX = ref(0), panY = ref(0)
let isDragging = false, lastMX = 0, lastMY = 0, lastTouches = []

// ─── IV data (from snapshot endpoint) ────────────────────────────────────────
const loading    = ref(false)
const errorMsg   = ref('')
const ivRawOpts  = ref([])
const spot       = computed(() => props.modelData?.market_context?.spot_price ?? null)

async function reloadIV() {
  const underlying = props.modelData?.underlying_security || 'IBOVE Index'
  loading.value = true; errorMsg.value = ''; ivRawOpts.value = []
  try {
    const res  = await getSnapshotByStrike({ underlying_security: underlying, tier: 'all' })
    // axios wraps JSON: res.data = { success, data: { options, by_strike } }
    const payload = res?.data ?? res
    const opts = payload?.data?.options ?? payload?.options ?? []
    if (!opts.length) { errorMsg.value = 'Snapshot vazio'; return }
    const S = spot.value || 1
    const parsed = opts.map(o => ({
      k: parseFloat(o.strike), dte: parseInt(o.days_to_expiry),
      m: o.moneyness != null ? parseFloat(o.moneyness) : parseFloat(o.strike)/S - 1,
      iv: parseFloat(o.iv), pc: String(o.put_call||'').toLowerCase(),
      expiry: o.expiry_date || '',
    })).filter(o =>
      isFinite(o.iv) && o.iv > 0.005 && o.iv < 3 &&
      o.k > 0 && o.dte >= 1 && o.dte <= 365 &&
      isFinite(o.m) && Math.abs(o.m) <= 0.20
    )
    // OTM convention
    const otm = parsed.filter(o =>
      !(o.pc.startsWith('c') && o.m < -0.03) &&
      !(o.pc.startsWith('p') && o.m >  0.03)
    )
    const base = otm.length >= 10 ? otm : parsed
    // Per-expiry IQR outlier removal
    const byExp = new Map()
    for (const o of base) {
      if (!byExp.has(o.expiry)) byExp.set(o.expiry, [])
      byExp.get(o.expiry).push(o)
    }
    const clean = []
    for (const [, pts] of byExp) {
      if (pts.length < 3) { clean.push(...pts); continue }
      const ivs = pts.map(p=>p.iv).sort((a,b)=>a-b)
      const q1=ivs[Math.floor(ivs.length*0.25)], q3=ivs[Math.floor(ivs.length*0.75)]
      const iqr=Math.max(q3-q1,0.005)
      const inl=pts.filter(p=>p.iv>=q1-2.5*iqr && p.iv<=q3+2.5*iqr)
      clean.push(...(inl.length>=3?inl:pts))
    }
    if (!clean.length) { errorMsg.value = `${opts.length} opts, nenhuma válida`; return }
    ivRawOpts.value = clean
  } catch(e) { errorMsg.value = e.message||'Erro IV'; console.error('[VS3D IV]',e) }
  finally { loading.value = false }
}

// ─── GEX / DEX data (from compact model run) ─────────────────────────────────
const gexRawPts = computed(() => {
  const pts = props.modelData?.gex_surface_points ?? []
  const S   = spot.value || 1
  return pts
    .filter(p => p.strike && p.expiry && p.dte >= 1 && p.dte <= 365 && isFinite(p.gex) && isFinite(p.dex))
    .map(p => ({
      strike: parseFloat(p.strike),
      expiry: p.expiry,
      dte:    parseInt(p.dte),
      m:      p.m != null ? parseFloat(p.m) : parseFloat(p.strike)/S - 1,
      gex:    parseFloat(p.gex),
      dex:    parseFloat(p.dex),
    }))
})

async function reloadAll() {
  await reloadIV()
}

// ─── Active slices (per surfaceMode) ─────────────────────────────────────────
const ivSlices = computed(() => groupSlices(ivRawOpts.value))
const gexSlices = computed(() => groupSlicesExposure(gexRawPts.value))

function groupSlices(opts) {
  const byExp = new Map()
  for (const o of opts) {
    if (!byExp.has(o.expiry)) byExp.set(o.expiry, { expiry: o.expiry, dte: o.dte, pts: [] })
    byExp.get(o.expiry).pts.push(o)
  }
  return Array.from(byExp.values()).filter(sl=>sl.pts.length>=3).sort((a,b)=>a.dte-b.dte)
}
function groupSlicesExposure(pts) {
  const byExp = new Map()
  for (const o of pts) {
    if (!byExp.has(o.expiry)) byExp.set(o.expiry, { expiry: o.expiry, dte: o.dte, pts: [] })
    byExp.get(o.expiry).pts.push(o)
  }
  return Array.from(byExp.values()).filter(sl=>sl.pts.length>=1).sort((a,b)=>a.dte-b.dte)
}

const activeSlices = computed(() => surfaceMode.value === 'iv' ? ivSlices.value : gexSlices.value)
const sliceCount   = computed(() => activeSlices.value.length)
const totalPts     = computed(() => surfaceMode.value === 'iv' ? ivRawOpts.value.length : gexRawPts.value.length)
const hasData      = computed(() => sliceCount.value >= 2)

// ─── Value ranges ─────────────────────────────────────────────────────────────
const ivRange = computed(() => {
  if (!ivRawOpts.value.length) return { min: 0.05, max: 0.60 }
  let mn=Infinity,mx=-Infinity
  for (const o of ivRawOpts.value) { if(o.iv<mn)mn=o.iv; if(o.iv>mx)mx=o.iv }
  const pad=Math.max((mx-mn)*0.05,0.01)
  return { min: Math.max(0.01,mn-pad), max: mx+pad }
})

const expRange = computed(() => {
  const field = surfaceMode.value === 'dex' ? 'dex' : 'gex'
  const pts   = gexRawPts.value
  if (!pts.length) return { min: -1, max: 1, absMax: 1 }
  let mn=Infinity,mx=-Infinity
  for (const p of pts) { const v=p[field]; if(v<mn)mn=v; if(v>mx)mx=v }
  const absMax=Math.max(Math.abs(mn),Math.abs(mx),1)
  return { min: -absMax, max: absMax, absMax }
})

// ─── Surface grid ─────────────────────────────────────────────────────────────
const GRID_NX = 30
const M_MIN=-0.12, M_MAX=0.12
const ZH=0.7

const surfaceGrid = computed(() => {
  if (!hasData.value) return null
  const sorted = [...activeSlices.value].sort((a,b)=>a.dte-b.dte)
  const mAxis  = Array.from({length:GRID_NX},(_,i)=>M_MIN+i*(M_MAX-M_MIN)/(GRID_NX-1))
  const minDte=sorted[0].dte, maxDte=sorted[sorted.length-1].dte

  const rows = sorted.map(sl => {
    let vals
    if (surfaceMode.value === 'iv') {
      const pts=sl.pts.map(o=>({m:o.m,iv:o.iv})).sort((a,b)=>a.m-b.m)
      const c=fitPoly(pts)
      const ivAtm=Math.max(0.01,evalPoly(c,0))
      vals=mAxis.map(m=>{
        const v=evalPoly(c,m)
        return Math.max(ivAtm*0.3,Math.min(ivAtm*3,isFinite(v)?v:ivAtm))
      })
    } else {
      const field = surfaceMode.value==='dex' ? 'dex' : 'gex'
      vals=mAxis.map(m=>gaussianKernel(sl.pts.map(p=>({m:p.m,v:p[field]})), m, 0.018))
    }
    return { dte:sl.dte, expiry:sl.expiry, vals }
  })
  return { mAxis, rows, minDte, maxDte }
})

// ─── Gaussian kernel (for GEX/DEX smoothing) ─────────────────────────────────
function gaussianKernel(pts, m, sigma) {
  let num=0, den=0
  for (const p of pts) {
    const w=Math.exp(-((m-p.m)**2)/(2*sigma**2))
    num+=p.v*w; den+=w
  }
  return den>1e-12 ? num/den : 0
}

// ─── Polynomial fit WLS degree 3 (IV mode) ───────────────────────────────────
function fitPoly(pts) {
  if (pts.length<2) return [0.25,0,0,0]
  const n=Math.min(4,pts.length)
  const w=pts.map(p=>Math.exp(-15*p.m*p.m)+0.05)
  const A=pts.map(p=>Array.from({length:n},(_,j)=>Math.pow(p.m,j)))
  const AtWA=Array.from({length:n},(_,i)=>Array.from({length:n},(_,j)=>A.reduce((s,a,r)=>s+a[i]*a[j]*w[r],0)))
  const AtWy=Array.from({length:n},(_,i)=>A.reduce((s,a,r)=>s+a[i]*pts[r].iv*w[r],0))
  return gaussSolve(AtWA,AtWy)??[pts.reduce((s,p)=>s+p.iv,0)/pts.length,0,0,0]
}
function evalPoly(c,x){return c?c.reduce((s,v,i)=>s+v*Math.pow(x,i),0):0.25}
function gaussSolve(A,b){
  const n=b.length,M=A.map((r,i)=>[...r,b[i]])
  for(let col=0;col<n;col++){
    let piv=col
    for(let r=col+1;r<n;r++)if(Math.abs(M[r][col])>Math.abs(M[piv][col]))piv=r
    ;[M[col],M[piv]]=[M[piv],M[col]]
    if(Math.abs(M[col][col])<1e-12)return null
    const d=M[col][col];for(let j=col;j<=n;j++)M[col][j]/=d
    for(let r=0;r<n;r++){if(r===col)continue;const f=M[r][col];for(let j=col;j<=n;j++)M[r][j]-=f*M[col][j]}
  }
  return M.map(r=>r[n])
}

// ─── Color maps ───────────────────────────────────────────────────────────────
const TURBO=[[0,[25,25,180]],[0.25,[30,180,220]],[0.5,[50,200,80]],[0.75,[230,200,30]],[1,[220,30,30]]]
function ivColor(iv, alpha=0.85) {
  const {min,max}=ivRange.value
  let t=Math.max(0,Math.min(1,(iv-min)/Math.max(max-min,0.001)))
  for(let i=0;i<TURBO.length-1;i++){
    const [t0,c0]=TURBO[i],[t1,c1]=TURBO[i+1]
    if(t>=t0&&t<=t1){const f=(t-t0)/(t1-t0);return `rgba(${~~(c0[0]+f*(c1[0]-c0[0]))},${~~(c0[1]+f*(c1[1]-c0[1]))},${~~(c0[2]+f*(c1[2]-c0[2]))},${alpha})`}
  }
  return `rgba(220,30,30,${alpha})`
}
function termColor(dte, alpha=0.85) {
  const g=surfaceGrid.value;if(!g)return ivColor(0.3,alpha)
  const t=Math.max(0,Math.min(1,(dte-g.minDte)/Math.max(g.maxDte-g.minDte,1)))
  return `rgba(${~~(30+190*t)},${~~(180-100*t)},${~~(220-190*t)},${alpha})`
}
// Diverging: negative=red, zero=very dark, positive=green/blue
function expColor(v, alpha=0.85) {
  const {absMax}=expRange.value
  const t=Math.max(-1,Math.min(1,v/Math.max(absMax,1)))
  if(t>=0){
    const f=t
    return `rgba(${~~(20+30*f)},${~~(60+140*f)},${~~(30+80*f)},${alpha})`  // dark→green
  } else {
    const f=-t
    return `rgba(${~~(60+160*f)},${~~(20+20*f)},${~~(20+20*f)},${alpha})`  // dark→red
  }
}
function activeColor(v, dte, alpha=0.85) {
  if(surfaceMode.value==='iv') return colorMode.value==='term'?termColor(dte,alpha):ivColor(v,alpha)
  return expColor(v,alpha)
}

// ─── 3D Projection ───────────────────────────────────────────────────────────
let cw=600,ch=350
const surfCX=()=>PAD_L+(cw-PAD_L-PAD_R)/2
const surfCY=()=>PAD_T+(ch-PAD_T-PAD_B)/2

function proj(x,y,z){
  const cx=Math.cos(rotX.value),sx=Math.sin(rotX.value)
  const cy=Math.cos(rotY.value),sy=Math.sin(rotY.value)
  const x1=x*cy+z*sy,z1=-x*sy+z*cy
  const y2=y*cx-z1*sx,z2=y*sx+z1*cx
  const d=4.5+z2*0.5
  return{sx:surfCX()+panX.value+(x1/d)*scale.value,sy:surfCY()+panY.value+(y2/d)*scale.value,depth:z2}
}

// ─── Z mapping ────────────────────────────────────────────────────────────────
// IV mode: val ∈ [ivMin, ivMax] → Z ∈ [0, ZH]
// GEX/DEX mode: val ∈ [-absMax, +absMax] → Z ∈ [0, ZH], zero at ZH/2
function valToZ(val) {
  if(surfaceMode.value==='iv'){
    const {min,max}=ivRange.value
    return Math.max(0,Math.min(ZH,((val-min)/Math.max(max-min,0.001))*ZH))
  } else {
    const {absMax}=expRange.value
    return ZH/2 + (val/Math.max(absMax,1))*(ZH/2)   // zero → ZH/2
  }
}
// Z value at zero (for reference plane label)
const zZero = computed(()=> surfaceMode.value==='iv' ? 0 : ZH/2)

// ─── Render ───────────────────────────────────────────────────────────────────
let animFrame=null
function render(){
  const canvas=canvasEl.value;if(!canvas)return
  const ctx=canvas.getContext('2d')
  cw=canvas.width;ch=canvas.height
  ctx.clearRect(0,0,cw,ch)
  const grid=surfaceGrid.value
  if(grid){
    drawFrame3D(ctx,grid,'back')
    if(surfaceMode.value!=='iv') drawZeroPlane(ctx)
    drawSurface(ctx,grid)
    drawAtmLine(ctx,grid)
    drawFrame3D(ctx,grid,'front')
  }
  drawFixed2DAxes(ctx,grid)
}

// ─── Zero reference plane (GEX/DEX) ──────────────────────────────────────────
function drawZeroPlane(ctx){
  const z=zZero.value
  const corners=[[-1,0.8],[ 1,0.8],[ 1,-0.8],[-1,-0.8]]
  const pts=corners.map(([x,y])=>proj(x,y,z))
  ctx.save()
  ctx.fillStyle='rgba(148,163,184,0.06)'
  ctx.strokeStyle='rgba(148,163,184,0.20)'
  ctx.setLineDash([3,4]);ctx.lineWidth=0.8
  ctx.beginPath();ctx.moveTo(pts[0].sx,pts[0].sy)
  for(let i=1;i<pts.length;i++)ctx.lineTo(pts[i].sx,pts[i].sy)
  ctx.closePath();ctx.fill();ctx.stroke()
  ctx.setLineDash([])
  ctx.restore()
}

// ─── 3D wireframe box + axis labels ──────────────────────────────────────────
function text3D(ctx,txt,x3d,y3d,z3d,opts={}){
  const p=proj(x3d,y3d,z3d)
  if(p.sx<PAD_L-4||p.sx>cw-PAD_R+4||p.sy<PAD_T-4||p.sy>ch-PAD_B+4)return
  ctx.save()
  ctx.font=opts.font||'8px monospace'
  ctx.fillStyle=opts.color||'rgba(148,163,184,0.85)'
  ctx.textAlign=opts.align||'center'
  ctx.textBaseline=opts.base||'middle'
  ctx.fillText(txt,p.sx+(opts.dx||0),p.sy+(opts.dy||0))
  ctx.restore()
}

function drawFrame3D(ctx,grid,pass){
  const {minDte,maxDte}=grid
  const C={
    b0:proj(-1,0.8,0),b1:proj(1,0.8,0),b2:proj(1,-0.8,0),b3:proj(-1,-0.8,0),
    t0:proj(-1,0.8,ZH),t1:proj(1,0.8,ZH),t2:proj(1,-0.8,ZH),t3:proj(-1,-0.8,ZH),
  }
  const edges=[
    ['b0','b1'],['b1','b2'],['b2','b3'],['b3','b0'],
    ['t0','t1'],['t1','t2'],['t2','t3'],['t3','t0'],
    ['b0','t0'],['b1','t1'],['b2','t2'],['b3','t3'],
  ]
  ctx.save()
  for(const [a,b] of edges){
    const pa=C[a],pb=C[b],isFront=(pa.depth+pb.depth)/2>0
    if(pass==='back'&&isFront)continue
    if(pass==='front'&&!isFront)continue
    ctx.setLineDash(pass==='back'?[3,4]:[])
    ctx.strokeStyle=pass==='back'?'rgba(148,163,184,0.12)':'rgba(148,163,184,0.30)'
    ctx.lineWidth=0.8
    ctx.beginPath();ctx.moveTo(pa.sx,pa.sy);ctx.lineTo(pb.sx,pb.sy);ctx.stroke()
  }
  ctx.setLineDash([])

  if(pass==='front'){
    // ── Moneyness axis (bottom-front, y=+0.8, z=0) ─────────────────────────
    for(const m of [-0.12,-0.08,-0.04,0,0.04,0.08,0.12]){
      const x=m/0.12,isAtm=m===0
      const p0=proj(x,0.8,0),p1=proj(x,0.8,0.045)
      ctx.strokeStyle=isAtm?'rgba(251,191,36,0.55)':'rgba(148,163,184,0.28)'
      ctx.lineWidth=isAtm?1.2:0.7
      ctx.beginPath();ctx.moveTo(p0.sx,p0.sy);ctx.lineTo(p1.sx,p1.sy);ctx.stroke()
      text3D(ctx,isAtm?'ATM':`${m>0?'+':''}${(m*100).toFixed(0)}%`,x,0.96,-0.02,
        {color:isAtm?'rgba(251,191,36,0.9)':'rgba(148,163,184,0.72)'})
    }
    text3D(ctx,'Moneyness',0,1.15,-0.06,
      {color:'rgba(100,116,139,0.8)',font:'bold 8px monospace'})

    // ── DTE / Prazo axis (left-bottom, x=−1, z=0) ──────────────────────────
    const nDte=Math.min(activeSlices.value.length,5)
    for(let i=0;i<=nDte;i++){
      const dte=Math.round(minDte+(maxDte-minDte)*(i/nDte))
      const y=0.8-(i/nDte)*1.6
      const p0=proj(-1,y,0),p1=proj(-1.08,y,0)
      ctx.strokeStyle='rgba(148,163,184,0.25)';ctx.lineWidth=0.7
      ctx.beginPath();ctx.moveTo(p0.sx,p0.sy);ctx.lineTo(p1.sx,p1.sy);ctx.stroke()
      text3D(ctx,`${dte}d`,-1.17,y,0,{color:'rgba(148,163,184,0.75)',align:'center'})
    }
    text3D(ctx,'Prazo',-1.30,0,0,{color:'rgba(100,116,139,0.8)',font:'bold 8px monospace'})

    // ── Z axis (front-left pillar, x=−1, y=+0.8) ───────────────────────────
    const zLabel = surfaceMode.value==='iv' ? 'IV impl.' : (surfaceMode.value==='gex'?'GEX':'DEX')
    const nZ=4
    for(let i=0;i<=nZ;i++){
      const z=(i/nZ)*ZH
      const p0=proj(-1,0.8,z),p1=proj(-1.08,0.8,z)
      let lbl,clr
      if(surfaceMode.value==='iv'){
        const iv=ivRange.value.min+(ivRange.value.max-ivRange.value.min)*(i/nZ)
        lbl=`${(iv*100).toFixed(0)}%`; clr=ivColor(iv,0.85)
      } else {
        // Use inverse of valToZ: val = (z/ZH - 0.5)*2*absMax
        const v=(i/nZ - 0.5)*2*expRange.value.absMax
        lbl=fmtExp(v); clr=expColor(v,0.85)
        // Mark zero line (exactly at i=nZ/2 with even nZ)
        if(Math.abs(v)<1e-10){clr='rgba(148,163,184,0.9)';lbl='0'}
      }
      ctx.strokeStyle=clr;ctx.lineWidth=0.7
      ctx.beginPath();ctx.moveTo(p0.sx,p0.sy);ctx.lineTo(p1.sx,p1.sy);ctx.stroke()
      text3D(ctx,lbl,-1.17,0.8,z,{color:clr,align:'center'})
    }
    text3D(ctx,zLabel,-1.17,0.8,ZH+0.13,{color:'rgba(100,116,139,0.8)',font:'bold 8px monospace'})
  }
  ctx.restore()
}

// ─── Surface quads ────────────────────────────────────────────────────────────
function drawSurface(ctx,grid){
  const {mAxis,rows}=grid
  const nX=mAxis.length,nY=rows.length
  if(nX<2||nY<2)return

  function toW(iY,iX){
    const m=mAxis[iX],row=rows[iY],val=row.vals[iX]
    return{
      x:m/0.12,
      y:0.8-((row.dte-grid.minDte)/Math.max(grid.maxDte-grid.minDte,1))*1.6,
      z:valToZ(val),
      val,dte:row.dte,
    }
  }

  const quads=[]
  for(let iY=0;iY<nY-1;iY++)for(let iX=0;iX<nX-1;iX++){
    const w00=toW(iY,iX),w10=toW(iY+1,iX),w11=toW(iY+1,iX+1),w01=toW(iY,iX+1)
    const p00=proj(w00.x,w00.y,w00.z),p10=proj(w10.x,w10.y,w10.z)
    const p11=proj(w11.x,w11.y,w11.z),p01=proj(w01.x,w01.y,w01.z)
    quads.push({p00,p10,p11,p01,
      depth:(p00.depth+p10.depth+p11.depth+p01.depth)/4,
      avgVal:(w00.val+w10.val+w11.val+w01.val)/4,
      avgDte:(w00.dte+w10.dte+w11.dte+w01.dte)/4,
    })
  }
  quads.sort((a,b)=>b.depth-a.depth)
  for(const q of quads){
    ctx.beginPath()
    ctx.moveTo(q.p00.sx,q.p00.sy);ctx.lineTo(q.p01.sx,q.p01.sy)
    ctx.lineTo(q.p11.sx,q.p11.sy);ctx.lineTo(q.p10.sx,q.p10.sy)
    ctx.closePath()
    ctx.fillStyle=activeColor(q.avgVal,q.avgDte);ctx.fill()
    if(showWire.value){ctx.strokeStyle='rgba(255,255,255,0.07)';ctx.lineWidth=0.4;ctx.stroke()}
  }
}

// ─── ATM line ─────────────────────────────────────────────────────────────────
function drawAtmLine(ctx,grid){
  const{rows}=grid
  const atmIdx=Math.floor(GRID_NX/2)
  ctx.save();ctx.setLineDash([4,3]);ctx.strokeStyle='rgba(251,191,36,0.85)';ctx.lineWidth=2
  let ok=false
  for(const row of rows){
    const val=row.vals[atmIdx]
    const y=0.8-((row.dte-grid.minDte)/Math.max(grid.maxDte-grid.minDte,1))*1.6
    const p=proj(0,y,valToZ(val))
    if(!ok){ctx.beginPath();ctx.moveTo(p.sx,p.sy);ok=true}else ctx.lineTo(p.sx,p.sy)
  }
  if(ok)ctx.stroke()
  ctx.restore()
}

// ─── Fixed 2D axis strips ─────────────────────────────────────────────────────
function drawFixed2DAxes(ctx,grid){
  const areaX=PAD_L,areaY=PAD_T,areaW=cw-PAD_L-PAD_R,areaH=ch-PAD_T-PAD_B
  ctx.save();ctx.font='9px monospace'
  // Opaque strips
  ctx.fillStyle='rgba(6,12,24,0.82)'
  ctx.fillRect(0,0,PAD_L,ch)
  ctx.fillRect(cw-PAD_R,0,PAD_R,ch)
  ctx.fillRect(PAD_L,ch-PAD_B,areaW,PAD_B)

  // Bottom: Moneyness
  ctx.strokeStyle='rgba(148,163,184,0.2)';ctx.lineWidth=1;ctx.setLineDash([])
  ctx.beginPath();ctx.moveTo(areaX,ch-PAD_B);ctx.lineTo(areaX+areaW,ch-PAD_B);ctx.stroke()
  for(const m of [-0.12,-0.08,-0.04,0,0.04,0.08,0.12]){
    const x=areaX+((m-M_MIN)/(M_MAX-M_MIN))*areaW,isAtm=m===0
    ctx.setLineDash([2,4]);ctx.strokeStyle=isAtm?'rgba(251,191,36,0.10)':'rgba(148,163,184,0.05)'
    ctx.beginPath();ctx.moveTo(x,areaY);ctx.lineTo(x,ch-PAD_B);ctx.stroke();ctx.setLineDash([])
    ctx.strokeStyle=isAtm?'rgba(251,191,36,0.45)':'rgba(148,163,184,0.22)';ctx.lineWidth=1
    ctx.beginPath();ctx.moveTo(x,ch-PAD_B);ctx.lineTo(x,ch-PAD_B+4);ctx.stroke()
    ctx.textAlign='center'
    ctx.fillStyle=isAtm?'rgba(251,191,36,0.92)':'rgba(148,163,184,0.72)'
    ctx.fillText(isAtm?'ATM':`${m>0?'+':''}${(m*100).toFixed(0)}%`,x,ch-PAD_B+14)
  }
  ctx.textAlign='center';ctx.fillStyle='rgba(100,116,139,0.55)';ctx.fillText('Moneyness',areaX+areaW/2,ch-2)

  // Left: Z axis (IV or Exposure)
  ctx.strokeStyle='rgba(148,163,184,0.2)';ctx.lineWidth=1;ctx.setLineDash([])
  ctx.beginPath();ctx.moveTo(PAD_L,areaY);ctx.lineTo(PAD_L,ch-PAD_B);ctx.stroke()
  const nZ=4
  for(let i=0;i<=nZ;i++){
    const y=(ch-PAD_B)-(i/nZ)*areaH
    ctx.setLineDash([2,4]);ctx.strokeStyle='rgba(148,163,184,0.05)'
    ctx.beginPath();ctx.moveTo(PAD_L,y);ctx.lineTo(cw-PAD_R,y);ctx.stroke();ctx.setLineDash([])
    ctx.strokeStyle='rgba(148,163,184,0.22)';ctx.lineWidth=1
    ctx.beginPath();ctx.moveTo(PAD_L-3,y);ctx.lineTo(PAD_L,y);ctx.stroke()
    let lbl,clr
    if(surfaceMode.value==='iv'){
      const iv=ivRange.value.min+(ivRange.value.max-ivRange.value.min)*(i/nZ)
      lbl=`${(iv*100).toFixed(0)}%`;clr=ivColor(iv,0.88)
    } else {
      // Symmetric: i=0→-absMax, i=nZ/2→0, i=nZ→+absMax
      const v=(i/nZ - 0.5)*2*expRange.value.absMax
      lbl=fmtExp(v);clr=expColor(v,0.88)
      if(Math.abs(v)<1e-10){lbl='0';clr='rgba(148,163,184,0.8)'}
    }
    ctx.textAlign='right';ctx.fillStyle=clr;ctx.fillText(lbl,PAD_L-5,y+3)
  }
  // Zero reference line for exposure modes
  if(surfaceMode.value!=='iv'){
    const yZero=(ch-PAD_B)-areaH/2
    ctx.save();ctx.setLineDash([4,3]);ctx.strokeStyle='rgba(148,163,184,0.22)';ctx.lineWidth=1
    ctx.beginPath();ctx.moveTo(PAD_L,yZero);ctx.lineTo(cw-PAD_R,yZero);ctx.stroke()
    ctx.restore()
  }
  const zAxisLbl=surfaceMode.value==='iv'?'IV impl.':(surfaceMode.value==='gex'?'GEX':'DEX')
  ctx.save();ctx.translate(11,areaY+areaH/2);ctx.rotate(-Math.PI/2)
  ctx.textAlign='center';ctx.fillStyle='rgba(100,116,139,0.55)';ctx.font='9px monospace'
  ctx.fillText(zAxisLbl,0,0);ctx.restore()

  // Right: DTE bar
  if(grid){
    const{minDte,maxDte}=grid
    const barX=cw-PAD_R+7,barW=10
    const grad=ctx.createLinearGradient(barX,areaY+areaH,barX,areaY)
    grad.addColorStop(0,'rgba(30,180,220,0.85)');grad.addColorStop(1,'rgba(220,80,30,0.85)')
    ctx.fillStyle=grad;ctx.setLineDash([])
    ctx.beginPath()
    if(ctx.roundRect)ctx.roundRect(barX,areaY,barW,areaH,3)
    else ctx.rect(barX,areaY,barW,areaH)
    ctx.fill();ctx.strokeStyle='rgba(255,255,255,0.07)';ctx.lineWidth=0.5;ctx.stroke()
    ctx.textAlign='left';ctx.fillStyle='rgba(148,163,184,0.78)';ctx.font='9px monospace'
    for(let i=0;i<=4;i++){
      const t=i/4,dte=Math.round(minDte+(maxDte-minDte)*t),y=(ch-PAD_B)-t*areaH
      ctx.fillText(`${dte}d`,barX+barW+4,y+3)
    }
    ctx.save();ctx.translate(cw-4,areaY+areaH/2);ctx.rotate(-Math.PI/2)
    ctx.textAlign='center';ctx.fillStyle='rgba(100,116,139,0.55)';ctx.font='9px monospace'
    ctx.fillText('Prazo',0,0);ctx.restore()
  }
  ctx.restore()
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function fmtExp(v){
  const a=Math.abs(v)
  if(a>=1e9)return`${(v/1e9).toFixed(1)}B`
  if(a>=1e6)return`${(v/1e6).toFixed(1)}M`
  if(a>=1e3)return`${(v/1e3).toFixed(0)}k`
  return v.toFixed(1)
}

// ─── Schedule / resize ────────────────────────────────────────────────────────
function scheduleRender(){if(animFrame)cancelAnimationFrame(animFrame);animFrame=requestAnimationFrame(render)}
watch([rotX,rotY,scale,panX,panY,showWire,colorMode,surfaceMode,surfaceGrid],scheduleRender)

let ro=null
function setupResize(){
  const wrap=wrapEl.value;if(!wrap)return
  ro=new ResizeObserver(()=>{
    const c=canvasEl.value;if(!c)return
    c.width=wrap.clientWidth||560;c.height=wrap.clientHeight||300;scheduleRender()
  });ro.observe(wrap)
}

onMounted(async()=>{
  await nextTick()
  const c=canvasEl.value,w=wrapEl.value
  if(c&&w){c.width=w.clientWidth||560;c.height=w.clientHeight||300}
  if(c)c.addEventListener('touchmove',onTouchMove,{passive:false})
  setupResize();await reloadAll()
})
onUnmounted(()=>{if(ro)ro.disconnect();if(animFrame)cancelAnimationFrame(animFrame)})
watch(()=>props.modelData?.underlying_security,(v,old)=>{if(v&&v!==old)reloadAll()})
watch(()=>props.modelData?.captured_at,()=>scheduleRender())

// ─── Mouse / Touch ────────────────────────────────────────────────────────────
function onMouseDown(e){isDragging=true;lastMX=e.clientX;lastMY=e.clientY;window.addEventListener('mousemove',onMouseMove);window.addEventListener('mouseup',onMouseUp)}
function onMouseMove(e){if(!isDragging)return;rotY.value+=(e.clientX-lastMX)*0.007;rotX.value+=(e.clientY-lastMY)*0.007;lastMX=e.clientX;lastMY=e.clientY}
function onMouseUp(){isDragging=false;window.removeEventListener('mousemove',onMouseMove);window.removeEventListener('mouseup',onMouseUp)}
function onTouchStart(e){lastTouches=Array.from(e.touches)}
function onTouchMove(e){const t=Array.from(e.touches);if(t.length===1&&lastTouches.length===1){rotY.value+=(t[0].clientX-lastTouches[0].clientX)*0.007;rotX.value+=(t[0].clientY-lastTouches[0].clientY)*0.007}lastTouches=t}
function onWheel(e){scale.value=Math.max(60,Math.min(400,scale.value-e.deltaY*0.3))}
function resetCamera(){rotX.value=-0.42;rotY.value=0.52;scale.value=110;panX.value=0;panY.value=0}
</script>

<style scoped>
.vs-root{height:100%;display:flex;flex-direction:column;padding:6px;gap:4px;}
.vs-controls{display:flex;align-items:center;gap:4px;flex-shrink:0;flex-wrap:wrap;}
.vs-divider{width:1px;height:16px;background:rgba(255,255,255,0.08);margin:0 2px;}
.vs-btn{padding:2px 8px;border-radius:4px;border:1px solid rgba(255,255,255,0.08);background:transparent;color:#64748b;font-size:10px;font-weight:600;cursor:pointer;transition:all 0.15s;}
.vs-btn.sm{font-size:9px;padding:2px 6px;}
.vs-btn.active{background:#1e1b4b;border-color:#6366f1;color:#a5b4fc;}
.vs-btn:hover:not(.active){background:rgba(255,255,255,0.05);color:#94a3b8;}
.vs-chk{display:flex;align-items:center;gap:3px;font-size:10px;color:#64748b;cursor:pointer;user-select:none;}
.vs-chk input{accent-color:#6366f1;}
.vs-info{margin-left:auto;font-size:10px;color:#475569;}
.vs-loading{font-size:10px;color:#f59e0b;margin-left:auto;}
.vs-error{font-size:10px;color:#f87171;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.vs-canvas-wrap{flex:1;min-height:0;position:relative;}
.vs-canvas{display:block;width:100%;height:100%;cursor:grab;touch-action:none;}
.vs-canvas:active{cursor:grabbing;}
.vs-empty{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#475569;font-size:12px;text-align:center;padding:20px;}
</style>

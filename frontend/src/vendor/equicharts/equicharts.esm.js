var Q = /* @__PURE__ */ ((n) => (n.Dashed = "dashed", n.Solid = "solid", n))(Q || {}), V = /* @__PURE__ */ ((n) => (n.Stroke = "stroke", n.Fill = "fill", n.StrokeFill = "stroke_fill", n))(V || {}), we = /* @__PURE__ */ ((n) => (n.Always = "always", n.FollowCross = "follow_cross", n.None = "none", n))(we || {}), Ct = /* @__PURE__ */ ((n) => (n.Standard = "standard", n.Rect = "rect", n))(Ct || {}), Qt = /* @__PURE__ */ ((n) => (n.Left = "left", n.Middle = "middle", n.Right = "right", n))(Qt || {}), ns = /* @__PURE__ */ ((n) => (n.Fixed = "fixed", n.Pointer = "pointer", n))(ns || {}), O = /* @__PURE__ */ ((n) => (n.CandleSolid = "candle_solid", n.CandleStroke = "candle_stroke", n.CandleUpStroke = "candle_up_stroke", n.CandleDownStroke = "candle_down_stroke", n.Ohlc = "ohlc", n.Area = "area", n.Line = "line", n.LineMark = "line_marks", n.StepLine = "step_line", n.HeikinAshi = "heikin_ashi", n.CandleHighLow = "candle_high_low", n.CandleVolume = "candle_volume", n))(O || {}), Ft = /* @__PURE__ */ ((n) => (n.Left = "left", n.Right = "right", n))(Ft || {}), G = /* @__PURE__ */ ((n) => (n.Normal = "normal", n.Percentage = "percentage", n.Log = "log", n))(G || {});
const Nt = "#DE4646", te = "#DE464696", Wt = "#399068", ee = "#39906896", xt = "#888888", Gt = "#FFFFFF", Z = "#1677FF", It = "#76808F", be = "#DDDDDD", $e = "#000000";
function bt(n) {
  return `rgba(22, 119, 255, ${n})`;
}
function Xs() {
  function n() {
    return {
      show: !0,
      size: 1,
      color: "#EDEDED",
      style: "dashed",
      dashedValue: [2, 2]
    };
  }
  return {
    show: !0,
    horizontal: n(),
    vertical: n()
  };
}
function Ys() {
  const n = {
    show: !0,
    color: It,
    textOffset: 5,
    textSize: 10,
    textFamily: '"Roboto", sans-serif',
    textWeight: "normal"
  };
  return {
    type: "candle_solid",
    bar: {
      upColor: Wt,
      downColor: Nt,
      noChangeColor: xt,
      upBorderColor: Wt,
      downBorderColor: Nt,
      noChangeBorderColor: xt,
      upWickColor: ee,
      downWickColor: te,
      noChangeWickColor: xt
    },
    area: {
      lineSize: 2,
      lineColor: Z,
      smooth: !1,
      value: "close",
      backgroundColor: [
        {
          offset: 0,
          color: bt(0.01)
        },
        {
          offset: 1,
          color: bt(0.2)
        }
      ],
      point: {
        show: !0,
        color: Z,
        radius: 4,
        rippleColor: bt(0.3),
        rippleRadius: 8,
        animation: !0,
        animationDuration: 1e3
      }
    },
    highLow: {
      color: Z
    },
    line: {
      lineSize: 2,
      lineColor: Z,
      smooth: !1,
      value: "close",
      point: {
        show: !0,
        color: Z,
        radius: 4,
        rippleColor: bt(0.3),
        rippleRadius: 8,
        animation: !0,
        animationDuration: 1e3
      }
    },
    priceMark: {
      show: !0,
      high: { ...n },
      low: { ...n },
      last: {
        show: !0,
        upColor: Wt,
        downColor: Nt,
        noChangeColor: xt,
        line: {
          show: !0,
          style: "dashed",
          dashedValue: [4, 4],
          size: 1
        },
        text: {
          show: !0,
          style: "fill",
          size: 12,
          paddingLeft: 4,
          paddingTop: 4,
          paddingRight: 4,
          paddingBottom: 4,
          borderColor: "transparent",
          borderStyle: "solid",
          borderSize: 0,
          borderDashedValue: [2, 2],
          color: Gt,
          family: '"Roboto", sans-serif',
          weight: "normal",
          borderRadius: 2
        }
      }
    },
    visiblePriceMark: {
      show: !0,
      high: { ...n, color: Wt },
      low: { ...n, color: Nt },
      last: {
        show: !0,
        upColor: Wt,
        downColor: Nt,
        noChangeColor: xt,
        line: {
          show: !0,
          style: "dashed",
          dashedValue: [4, 4],
          size: 1
        },
        text: {
          show: !0,
          style: "stroke_fill",
          size: 12,
          paddingLeft: 4,
          paddingTop: 4,
          paddingRight: 4,
          paddingBottom: 4,
          borderColor: "transparent",
          borderStyle: "solid",
          borderSize: 1,
          borderDashedValue: [2, 2],
          color: Gt,
          family: '"Roboto", sans-serif',
          weight: "normal",
          borderRadius: 2
        }
      }
    },
    tooltip: {
      offsetLeft: 4,
      offsetTop: 6,
      offsetRight: 4,
      offsetBottom: 6,
      showRule: "always",
      showType: "standard",
      custom: [
        { title: "time", value: "{time}" },
        { title: "open", value: "{open}" },
        { title: "high", value: "{high}" },
        { title: "low", value: "{low}" },
        { title: "close", value: "{close}" },
        { title: "volume", value: "{volume}" }
      ],
      defaultValue: "n/a",
      rect: {
        position: "fixed",
        paddingLeft: 4,
        paddingRight: 4,
        paddingTop: 4,
        paddingBottom: 4,
        offsetLeft: 4,
        offsetTop: 4,
        offsetRight: 4,
        offsetBottom: 4,
        borderRadius: 4,
        borderSize: 1,
        borderColor: "#F2F3F5",
        color: "#FEFEFE"
      },
      text: {
        size: 12,
        family: '"Roboto", sans-serif',
        weight: "normal",
        color: It,
        marginLeft: 8,
        marginTop: 4,
        marginRight: 8,
        marginBottom: 4
      },
      icons: []
    }
  };
}
function Hs() {
  const n = ["#FF9600", "#935EBD", Z, "#E11D74", "#01C5C4"].map(
    (t) => ({
      style: "solid",
      smooth: !1,
      size: 1,
      dashedValue: [2, 2],
      color: t
    })
  );
  return {
    ohlc: {
      upColor: ee,
      downColor: te,
      noChangeColor: xt
    },
    bars: [
      {
        style: "fill",
        borderStyle: "solid",
        borderSize: 1,
        borderDashedValue: [2, 2],
        upColor: ee,
        downColor: te,
        noChangeColor: xt
      }
    ],
    lines: n,
    circles: [
      {
        style: "fill",
        borderStyle: "solid",
        borderSize: 1,
        borderDashedValue: [2, 2],
        upColor: ee,
        downColor: te,
        noChangeColor: xt
      }
    ],
    lastValueMark: {
      show: !1,
      text: {
        show: !1,
        style: "fill",
        color: Gt,
        size: 12,
        family: '"Roboto", sans-serif',
        weight: "normal",
        borderStyle: "solid",
        borderColor: "transparent",
        borderSize: 0,
        borderDashedValue: [2, 2],
        paddingLeft: 4,
        paddingTop: 4,
        paddingRight: 4,
        paddingBottom: 4,
        borderRadius: 2
      }
    },
    tooltip: {
      offsetLeft: 4,
      offsetTop: 6,
      offsetRight: 4,
      offsetBottom: 6,
      showRule: "always",
      showType: "standard",
      showName: !0,
      showParams: !0,
      defaultValue: "n/a",
      text: {
        size: 12,
        family: '"Roboto", sans-serif',
        weight: "normal",
        color: It,
        marginLeft: 8,
        marginTop: 4,
        marginRight: 8,
        marginBottom: 4
      },
      icons: []
    }
  };
}
function os() {
  return {
    show: !0,
    size: "auto",
    axisLine: {
      show: !0,
      color: be,
      size: 1
    },
    tickText: {
      show: !0,
      color: It,
      size: 12,
      family: '"Roboto", sans-serif',
      weight: "normal",
      marginStart: 4,
      marginEnd: 4
    },
    tictView: {
      show: !0,
      size: 1,
      length: 3,
      color: be
    }
  };
}
function $s() {
  const n = os();
  return n.type = "normal", n.position = "right", n.inside = !1, n.reverse = !1, n;
}
function Gs() {
  function n() {
    return {
      show: !0,
      line: {
        show: !0,
        style: "dashed",
        dashedValue: [4, 2],
        size: 1,
        color: It
      },
      text: {
        show: !0,
        style: "fill",
        color: Gt,
        size: 12,
        family: '"Roboto", sans-serif',
        weight: "normal",
        borderStyle: "solid",
        borderDashedValue: [2, 2],
        borderSize: 1,
        borderColor: It,
        borderRadius: 2,
        paddingLeft: 4,
        paddingRight: 4,
        paddingTop: 4,
        paddingBottom: 4,
        backgroundColor: It
      }
    };
  }
  return {
    show: !0,
    horizontal: n(),
    vertical: n()
  };
}
function js() {
  const n = bt(0.35), t = bt(0.25);
  function e() {
    return {
      style: "fill",
      color: Gt,
      size: 12,
      family: '"Roboto", sans-serif',
      weight: "normal",
      borderStyle: "solid",
      borderDashedValue: [2, 2],
      borderSize: 1,
      borderRadius: 2,
      borderColor: Z,
      paddingLeft: 4,
      paddingRight: 4,
      paddingTop: 4,
      paddingBottom: 4,
      backgroundColor: Z
    };
  }
  return {
    point: {
      color: $e,
      borderColor: Z,
      borderSize: 1,
      radius: 5,
      activeColor: $e,
      activeBorderColor: n,
      activeBorderSize: 3,
      activeRadius: 5
    },
    line: {
      style: "solid",
      smooth: !1,
      color: Z,
      size: 1,
      dashedValue: [2, 2]
    },
    rect: {
      style: "fill",
      color: t,
      borderColor: Z,
      borderSize: 1,
      borderRadius: 0,
      borderStyle: "solid",
      borderDashedValue: [2, 2]
    },
    polygon: {
      style: "fill",
      color: Z,
      borderColor: Z,
      borderSize: 1,
      borderStyle: "solid",
      borderDashedValue: [2, 2]
    },
    circle: {
      style: "fill",
      color: t,
      borderColor: Z,
      borderSize: 1,
      borderStyle: "solid",
      borderDashedValue: [2, 2]
    },
    arc: {
      style: "solid",
      color: Z,
      size: 1,
      dashedValue: [2, 2]
    },
    text: e(),
    rectText: e()
  };
}
function Us() {
  return {
    size: 1,
    color: be,
    fill: !0,
    activeBackgroundColor: bt(0.08)
  };
}
function Zs() {
  return {
    grid: Xs(),
    candle: Ys(),
    indicator: Hs(),
    xAxis: os(),
    yAxis: $s(),
    separator: Us(),
    crosshair: Gs(),
    overlay: js()
  };
}
function tt(n, t) {
  if (!(!at(n) && !at(t))) {
    for (const e in t)
      if (Object.prototype.hasOwnProperty.call(t, e)) {
        const s = n[e], i = t[e];
        at(i) && at(s) ? tt(s, i) : C(t[e]) && (n[e] = Lt(t[e]));
      }
  }
}
function Lt(n) {
  if (!at(n))
    return n;
  let t;
  rt(n) ? t = [] : t = {};
  for (const e in n)
    if (Object.prototype.hasOwnProperty.call(n, e)) {
      const s = n[e];
      at(s) ? t[e] = Lt(s) : t[e] = s;
    }
  return t;
}
function rt(n) {
  return Object.prototype.toString.call(n) === "[object Array]";
}
function lt(n) {
  return typeof n == "function";
}
function at(n) {
  return typeof n == "object" && C(n);
}
function E(n) {
  return typeof n == "number" && !isNaN(n);
}
function C(n) {
  return n != null;
}
function ae(n) {
  return typeof n == "boolean";
}
function D(n) {
  return typeof n == "string";
}
const Ks = /\\(\\)?/g, qs = RegExp(
  `[^.[\\]]+|\\[(?:([^"'][^[]*)|(["'])((?:(?!\\2)[^\\\\]|\\\\.)*?)\\2)\\]|(?=(?:\\.|\\[\\])(?:\\.|\\[\\]|$))`,
  "g"
);
function H(n, t, e) {
  if (C(n)) {
    const s = [];
    t.replace(qs, (a, ...l) => {
      let c = a;
      return C(l[1]) ? c = l[2].replace(Ks, "$1") : C(l[0]) && (c = l[0].trim()), s.push(c), "";
    });
    let i = n, o = 0;
    const r = s.length;
    for (; C(i) && o < r; )
      i = i?.[s[o++]];
    return C(i) ? i : e ?? "--";
  }
  return e ?? "--";
}
function rs(n, t, e) {
  const s = {}, i = new Date(t), o = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December"
  ], r = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec"
  ];
  let a = 0;
  n.formatToParts(i).forEach(({ type: h, value: u }) => {
    switch (h) {
      case "year":
        s.YYYY = u;
        break;
      case "month":
        a = parseInt(u, 10) - 1, s.MM = u.padStart(2, "0"), s.M = String(parseInt(u, 10)), s.MMMM = o[a], s.MMM = r[a], s.LL = r[a], s.LLL = r[a], s.LLLL = o[a], s.L = String(a + 1), s.ll = r[a].toLowerCase(), s.lll = r[a].toLowerCase(), s.llll = o[a].toLowerCase(), s.l = String(a + 1), s.Mo = ye(parseInt(u, 10));
        break;
      case "day":
        s.DD = u.padStart(2, "0"), s.D = String(parseInt(u, 10)), s.do = ye(parseInt(u, 10));
        break;
      case "hour": {
        const d = parseInt(u, 10);
        s.HH = u.padStart(2, "0"), s.H = String(d), s.hh = String(d % 12 === 0 ? 12 : d % 12).padStart(2, "0"), s.h = String(d % 12 === 0 ? 12 : d % 12), s.k = String(d === 0 ? 24 : d), s.kk = String(d === 0 ? 24 : d).padStart(2, "0"), s.K = String(d % 12), s.KK = String(d % 12).padStart(2, "0");
        break;
      }
      case "minute":
        s.mm = u.padStart(2, "0"), s.m = String(parseInt(u, 10));
        break;
      case "second":
        s.ss = u.padStart(2, "0"), s.s = String(parseInt(u, 10));
        break;
      case "dayPeriod":
        s.a = u.toLowerCase(), s.A = u.toUpperCase();
        break;
      case "weekday": {
        const d = [
          "Sunday",
          "Monday",
          "Tuesday",
          "Wednesday",
          "Thursday",
          "Friday",
          "Saturday"
        ], g = d.map((f) => f.slice(0, 3)), m = d.map((f) => f[0]);
        s.EEEE = d[i.getDay()], s.EEE = g[i.getDay()], s.E = m[i.getDay()];
        break;
      }
    }
  });
  const l = Js(i);
  s.DDD = String(l).padStart(3, "0"), s.DDDD = String(l).padStart(4, "0"), s.Do = ye(l);
  const c = /YYYY|MMMM|MMM|MM|M|LL|LLL|LLLL|L|ll|lll|llll|l|Mo|DD|D|do|HH|H|hh|h|k|kk|K|KK|mm|m|ss|s|a|A|EEEE|EEE|E|DDD|DDDD|Do/g;
  return e.replace(c, (h) => s[h] ?? h);
}
function ye(n) {
  const t = ["th", "st", "nd", "rd"], e = n % 100;
  return n + (t[(e - 20) % 10] ?? t[e] ?? t[0]);
}
function Js(n) {
  const t = new Date(n.getFullYear(), 0, 0), e = n.getTime() - t.getTime() + (t.getTimezoneOffset() - n.getTimezoneOffset()) * 60 * 1e3;
  return Math.floor(e / (1e3 * 60 * 60 * 24));
}
function N(n, t) {
  const e = +n;
  return E(e) ? e.toFixed(t ?? 2) : `${n}`;
}
function as(n) {
  const t = +n;
  if (E(t)) {
    if (t > 1e9)
      return `${+(t / 1e9).toFixed(3)}B`;
    if (t > 1e6)
      return `${+(t / 1e6).toFixed(3)}M`;
    if (t > 1e3)
      return `${+(t / 1e3).toFixed(3)}K`;
  }
  return `${n}`;
}
function W(n, t) {
  const e = `${n}`;
  if (t.length === 0)
    return e;
  if (e.includes(".")) {
    const s = e.split(".");
    return `${s[0].replace(/(\d)(?=(\d{3})+$)/g, (i) => `${i}${t}`)}.${s[1]}`;
  }
  return e.replace(/(\d)(?=(\d{3})+$)/g, (s) => `${s}${t}`);
}
function z(n, t) {
  const e = `${n}`;
  if (new RegExp("\\.0{" + t + ",}[1-9][0-9]*$").test(e)) {
    const i = e.split("."), o = i[i.length - 1], r = o.match(/0*/);
    if (C(r)) {
      const a = r[0].length;
      return i[i.length - 1] = o.replace(/0*/, `0{${a}}`), i.join(".");
    }
  }
  return e;
}
let zt;
function yt(n) {
  return n.ownerDocument?.defaultView?.devicePixelRatio ?? 1;
}
function Tt(n, t, e) {
  return `${t ?? "normal"} ${n ?? 12}px ${e ?? '"Roboto", sans-serif'}`;
}
function jt(n, t, e, s) {
  if (!C(zt)) {
    const i = document.createElement("canvas"), o = yt(i);
    zt = i.getContext("2d"), zt.scale(o, o);
  }
  return zt.font = Tt(t, e, s), Math.round(zt.measureText(n).width);
}
var et = /* @__PURE__ */ ((n) => (n.OnDataReady = "onDataReady", n.OnZoom = "onZoom", n.OnScroll = "onScroll", n.OnVisibleRangeChange = "onVisibleRangeChange", n.OnTooltipIconClick = "onTooltipIconClick", n.OnCrosshairChange = "onCrosshairChange", n.OnCandleBarClick = "onCandleBarClick", n.OnPaneDrag = "onPaneDrag", n))(et || {});
class Qs {
  constructor() {
    this._callbacks = [];
  }
  subscribe(t) {
    (this._callbacks.indexOf(t) ?? -1) < 0 && this._callbacks.push(t);
  }
  unsubscribe(t) {
    if (lt(t)) {
      const e = this._callbacks.indexOf(t) ?? -1;
      e > -1 && this._callbacks.splice(e, 1);
    } else
      this._callbacks = [];
  }
  execute(t) {
    this._callbacks.forEach((e) => {
      e(t);
    });
  }
  isEmpty() {
    return this._callbacks.length === 0;
  }
}
var st = /* @__PURE__ */ ((n) => (n.Normal = "normal", n.Price = "price", n.Volume = "volume", n))(st || {});
function De(n, t, e, s, i) {
  const o = t.result, r = t.figures, a = t.styles, l = H(
    a,
    "circles",
    s.circles
  ), c = l.length, h = H(
    a,
    "bars",
    s.bars
  ), u = h.length, d = H(
    a,
    "lines",
    s.lines
  ), g = d.length;
  let m = 0, f = 0, _ = 0, p, x = 0;
  r.forEach((y) => {
    switch (y.type) {
      case "circle": {
        x = m;
        const v = l[m % c];
        p = { ...v, color: v.noChangeColor }, m++;
        break;
      }
      case "bar": {
        x = f;
        const v = h[f % u];
        p = { ...v, color: v.noChangeColor }, f++;
        break;
      }
      case "line": {
        x = _, p = d[_ % g], _++;
        break;
      }
    }
    if (C(p)) {
      const v = {
        prev: {
          TViewData: n[e - 1],
          indicatorData: o[e - 1]
        },
        current: {
          TViewData: n[e],
          indicatorData: o[e]
        },
        next: {
          TViewData: n[e + 1],
          indicatorData: o[e + 1]
        }
      }, S = y.styles?.(v, t, s);
      i(
        y,
        { ...p, ...S },
        x
      );
    }
  });
}
class le {
  constructor(t) {
    this._indicator = {
      name: "",
      shortName: "",
      precision: 4,
      calcParams: [],
      shouldOhlc: !1,
      shouldFormatBigNumber: !1,
      visible: !0,
      zLevel: 0,
      extendData: null,
      series: "normal",
      figures: [],
      minValue: null,
      maxValue: null,
      styles: {},
      regenerateFigures: null,
      createTooltipDataSource: null,
      shouldUpdate: (e, s) => {
        const i = JSON.stringify(e.calcParams) !== JSON.stringify(s.calcParams) || e.figures !== s.figures || e.calc !== s.calc, o = i || e.shortName !== s.shortName || e.series !== s.series || e.minValue !== s.minValue || e.maxValue !== s.maxValue || e.precision !== s.precision || e.shouldOhlc !== s.shouldOhlc || e.shouldFormatBigNumber !== s.shouldFormatBigNumber || e.visible !== s.visible || e.zLevel !== s.zLevel || e.extendData !== s.extendData || e.regenerateFigures !== s.regenerateFigures || e.createTooltipDataSource !== s.createTooltipDataSource || e.draw !== s.draw;
        return { calc: i, draw: o };
      },
      calc: () => [],
      draw: null,
      result: []
    }, this._lockSeriesPrecision = !1, this.override(t), this._indicator.shortName ??= this._indicator.name, rt(t.figures) && (this._indicator.figures = t.figures);
  }
  getIndicator() {
    return this._indicator;
  }
  override(t) {
    this._prevIndicator = Lt(this._indicator), tt(this._indicator, t), E(t.precision) && (this._lockSeriesPrecision = !0);
  }
  setSeriesPrecision(t) {
    this._lockSeriesPrecision || (this._indicator.precision = t);
  }
  shouldUpdate() {
    const t = this._prevIndicator.zLevel !== this._indicator.zLevel, e = this._indicator.shouldUpdate(
      this._prevIndicator,
      this._indicator
    );
    return ae(e) ? { calc: e, draw: e, sort: t } : { ...e, sort: t };
  }
  async calc(t) {
    try {
      const e = await this._indicator.calc(t, this._indicator);
      return this._indicator.result = e, !0;
    } catch {
      return !1;
    }
  }
  static extend(t) {
    class e extends le {
      constructor() {
        super(t);
      }
    }
    return e;
  }
}
var se = /* @__PURE__ */ ((n) => (n.Normal = "normal", n.WeakMagnet = "weak_magnet", n.StrongMagnet = "strong_magnet", n))(se || {});
function ti() {
  return [
    "mouseClickEvent",
    "mouseDoubleClickEvent",
    "mouseRightClickEvent",
    "tapEvent",
    "doubleTapEvent",
    "mouseDownEvent",
    "touchStartEvent",
    "mouseMoveEvent",
    "touchMoveEvent"
  ];
}
const Ge = 1, Xt = -1, ei = "overlay_", At = "overlay_figure_";
class ce {
  constructor(t) {
    this._overlay = {
      id: "",
      groupId: "",
      paneId: "",
      name: "",
      totalStep: 1,
      currentStep: Ge,
      needDefaultPointFigure: !1,
      needDefaultXAxisFigure: !1,
      needDefaultYAxisFigure: !1,
      lock: !1,
      visible: !0,
      zLevel: 0,
      mode: "normal",
      modeSensitivity: 8,
      points: [],
      extendData: null,
      styles: {},
      createPointFigures: null,
      createXAxisFigures: null,
      createYAxisFigures: null,
      performEventPressedMove: null,
      performEventMoveForDrawing: null,
      onDrawStart: null,
      onDrawing: null,
      onDrawEnd: null,
      onClick: null,
      onDoubleClick: null,
      onRightClick: null,
      onPressedMoveStart: null,
      onPressedMoving: null,
      onPressedMoveEnd: null,
      onMouseEnter: null,
      onMouseLeave: null,
      onRemoved: null,
      onSelected: null,
      onDeselected: null
    }, this._prevPressedPoint = null, this._prevPressedPoints = [], this.override(t);
  }
  getOverlay() {
    return this._overlay;
  }
  override(t) {
    this._prevOverlay = Lt(this._overlay);
    const e = this._overlay.id;
    if (tt(this._overlay, t), D(e) && (this._overlay.id = e), rt(t.points) && t.points.length > 0) {
      let s;
      if (this._overlay.points = [...t.points], t.points.length >= this._overlay.totalStep - 1 ? (this._overlay.currentStep = Xt, s = this._overlay.totalStep - 1) : (this._overlay.currentStep = t.points.length + 1, s = t.points.length), lt(this._overlay.performEventMoveForDrawing))
        for (let i = 0; i < s; i++)
          this._overlay.performEventMoveForDrawing({
            currentStep: i + 2,
            mode: this._overlay.mode,
            points: this._overlay.points,
            performPointIndex: i,
            performPoint: this._overlay.points[i]
          });
      this._overlay.currentStep === Xt && lt(this._overlay.performEventPressedMove) && this._overlay.performEventPressedMove({
        currentStep: this._overlay.currentStep,
        mode: this._overlay.mode,
        points: this._overlay.points,
        performPointIndex: this._overlay.points.length - 1,
        performPoint: this._overlay.points[this._overlay.points.length - 1]
      });
    }
  }
  shouldUpdate() {
    const t = this._prevOverlay.zLevel !== this._overlay.zLevel, e = t || JSON.stringify(this._prevOverlay) !== JSON.stringify(this._overlay.points) || this._prevOverlay.visible !== this._overlay.visible || this._prevOverlay.extendData !== this._overlay.extendData || this._prevOverlay.styles !== this._overlay.styles;
    return { sort: t, draw: e };
  }
  nextStep() {
    this._overlay.currentStep === this._overlay.totalStep - 1 ? this._overlay.currentStep = Xt : this._overlay.currentStep++;
  }
  forceComplete() {
    this._overlay.currentStep = Xt;
  }
  isDrawing() {
    return this._overlay.currentStep !== Xt;
  }
  isStart() {
    return this._overlay.currentStep === Ge;
  }
  eventMoveForDrawing(t) {
    const e = this._overlay.currentStep - 1, s = {};
    E(t.timestamp) && (s.timestamp = t.timestamp), E(t.dataIndex) && (s.dataIndex = t.dataIndex), E(t.value) && (s.value = t.value), this._overlay.points[e] = s, this._overlay.performEventMoveForDrawing?.({
      currentStep: this._overlay.currentStep,
      mode: this._overlay.mode,
      points: this._overlay.points,
      performPointIndex: e,
      performPoint: s
    });
  }
  eventPressedPointMove(t, e) {
    E(t.dataIndex) && (this._overlay.points[e].dataIndex = t.dataIndex, this._overlay.points[e].timestamp = t.timestamp), E(t.value) && (this._overlay.points[e].value = t.value), this._overlay.performEventPressedMove?.({
      currentStep: this._overlay.currentStep,
      points: this._overlay.points,
      mode: this._overlay.mode,
      performPointIndex: e,
      performPoint: this._overlay.points[e]
    });
  }
  startPressedMove(t) {
    this._prevPressedPoint = { ...t }, this._prevPressedPoints = Lt(this._overlay.points);
  }
  eventPressedOtherMove(t, e) {
    if (this._prevPressedPoint !== null) {
      let s;
      E(t.dataIndex) && E(this._prevPressedPoint.dataIndex) && (s = t.dataIndex - this._prevPressedPoint.dataIndex);
      let i;
      E(t.value) && E(this._prevPressedPoint.value) && (i = t.value - this._prevPressedPoint.value), this._overlay.points = this._prevPressedPoints.map((o) => {
        E(o.timestamp) && (o.dataIndex = e.timestampToDataIndex(o.timestamp));
        const r = { ...o };
        return E(s) && E(o.dataIndex) && (r.dataIndex = o.dataIndex + s, r.timestamp = e.dataIndexToTimestamp(r.dataIndex) ?? void 0), E(i) && E(o.value) && (r.value = o.value + i), r;
      });
    }
  }
  static extend(t) {
    class e extends ce {
      constructor() {
        super(t);
      }
    }
    return e;
  }
}
var U = /* @__PURE__ */ ((n) => (n[n.Tooltip = 0] = "Tooltip", n[n.Crosshair = 1] = "Crosshair", n[n.XAxis = 2] = "XAxis", n))(U || {});
function si() {
  return {
    formatDate: rs,
    formatBigNumber: as
  };
}
const ii = "en-US";
var Yt = /* @__PURE__ */ ((n) => (n.Candle = "candle", n.Indicator = "indicator", n.XAxis = "xAxis", n))(Yt || {}), F = /* @__PURE__ */ ((n) => (n[n.Main = 0] = "Main", n[n.Overlay = 1] = "Overlay", n[n.Separator = 2] = "Separator", n[n.Drawer = 3] = "Drawer", n[n.All = 4] = "All", n))(F || {});
const ve = -1;
function ne(n) {
  return lt(window.requestAnimationFrame) ? window.requestAnimationFrame(n) : window.setTimeout(n, 20);
}
function je(n) {
  lt(window.cancelAnimationFrame) ? window.cancelAnimationFrame(n) : window.clearTimeout(n);
}
class Ie {
  constructor(t) {
    this._options = { duration: 500, iterationCount: 1 }, this._currentIterationCount = 0, this._running = !1, this._time = 0, tt(this._options, t);
  }
  _loop() {
    this._running = !0;
    const t = () => {
      if (this._running) {
        const e = (/* @__PURE__ */ new Date()).getTime() - this._time;
        e < this._options.duration ? (this._doFrameCallback?.(e), ne(t)) : (this.stop(), this._currentIterationCount++, this._currentIterationCount < this._options.iterationCount && this.start());
      }
    };
    ne(t);
  }
  doFrame(t) {
    return this._doFrameCallback = t, this;
  }
  setDuration(t) {
    return this._options.duration = t, this;
  }
  setIterationCount(t) {
    return this._options.iterationCount = t, this;
  }
  start() {
    this._running || (this._time = (/* @__PURE__ */ new Date()).getTime(), this._loop());
  }
  stop() {
    this._running && this._doFrameCallback?.(this._options.duration), this._running = !1;
  }
}
let Se = 1, Ue = (/* @__PURE__ */ new Date()).getTime();
function ls(n) {
  const t = (/* @__PURE__ */ new Date()).getTime();
  return t === Ue ? ++Se : Se = 1, Ue = t, `${n ?? ""}${t}_${Se}`;
}
function ft(n, t) {
  const e = document.createElement(n), s = t ?? {};
  for (const i in s)
    e.style[i] = s[i] ?? "";
  return e;
}
function Te(n, t, e) {
  let s = 0, i = 0;
  for (i = n.length - 1; s !== i; ) {
    const o = Math.floor((i + s) / 2), r = i - s, a = n[o][t];
    if (e === n[s][t])
      return s;
    if (e === n[i][t])
      return i;
    if (e === a)
      return o;
    if (e > a ? s = o : i = o, r <= 2)
      break;
  }
  return s;
}
function Ze(n) {
  const t = Math.floor(Ht(n)), e = wt(t), s = n / e;
  let i = 0;
  return s < 1.5 ? i = 1 : s < 2.5 ? i = 2 : s < 3.5 ? i = 3 : s < 4.5 ? i = 4 : s < 5.5 ? i = 5 : s < 6.5 ? i = 6 : i = 8, n = i * e, t >= -20 ? +n.toFixed(t < 0 ? -t : 0) : n;
}
function Ke(n, t) {
  return t == null && (t = 10), t = Math.min(Math.max(0, t), 20), +(+n).toFixed(t);
}
function qe(n) {
  const t = n.toString(), e = t.indexOf("e");
  if (e > 0) {
    const s = +t.slice(e + 1);
    return s < 0 ? -s : 0;
  } else {
    const s = t.indexOf(".");
    return s < 0 ? 0 : t.length - 1 - s;
  }
}
function Ae(n, t, e) {
  const s = [Number.MIN_SAFE_INTEGER, Number.MAX_SAFE_INTEGER];
  return n.forEach((i) => {
    s[0] = Math.max(i[t] ?? i, s[0]), s[1] = Math.min(i[e] ?? i, s[1]);
  }), s;
}
function Ht(n) {
  return Math.log(n) / Math.log(10);
}
function wt(n) {
  return Math.pow(10, n);
}
var ot = /* @__PURE__ */ ((n) => (n.Init = "init", n.Forward = "forward", n.Backward = "backward", n))(ot || {});
function Je() {
  return { from: 0, to: 0, realFrom: 0, realTo: 0 };
}
const Qe = {
  MIN: 1,
  MAX: 50
}, ni = 8, oi = 80, ri = 0.88, Ee = 10;
class ai {
  constructor(t) {
    this._dateTimeFormat = this._buildDateTimeFormat(), this._zoomEnabled = !0, this._scrollEnabled = !0, this._totalBarSpace = 0, this._barSpace = ni, this._offsetRightDistance = oi, this._startLastBarRightSideDiffBarCount = 0, this._scrollLimitRole = 0, this._minVisibleBarCount = { left: 2, right: 2 }, this._maxOffsetDistance = { left: 50, right: 50 }, this._visibleRange = Je(), this._chartStore = t, this._gapBarSpace = this._calcGapBarSpace(), this._lastBarRightSideDiffBarCount = this._offsetRightDistance / this._barSpace;
  }
  _calcGapBarSpace() {
    let t;
    return this._barSpace > 3 ? t = Math.floor(this._barSpace * ri) : (t = Math.floor(this._barSpace), t === this._barSpace && t--), t % 2 === 0 && t--, t = Math.max(1, t), t;
  }
  /**
   * adjust visible range
   */
  adjustVisibleRange() {
    const t = this._chartStore.getDataList(), e = t.length, s = this._totalBarSpace / this._barSpace;
    let i, o;
    this._scrollLimitRole === 1 ? (i = (this._totalBarSpace - this._maxOffsetDistance.right) / this._barSpace, o = (this._totalBarSpace - this._maxOffsetDistance.left) / this._barSpace) : (i = this._minVisibleBarCount.left, o = this._minVisibleBarCount.right), i = Math.max(0, i), o = Math.max(0, o);
    const r = s - Math.min(i, e);
    this._lastBarRightSideDiffBarCount > r && (this._lastBarRightSideDiffBarCount = r);
    const a = -e + Math.min(o, e);
    this._lastBarRightSideDiffBarCount < a && (this._lastBarRightSideDiffBarCount = a);
    let l = Math.round(
      this._lastBarRightSideDiffBarCount + e + 0.5
    );
    const c = l;
    l > e && (l = e);
    let h = Math.round(l - s) - 1;
    h < 0 && (h = 0);
    const u = this._lastBarRightSideDiffBarCount > 0 ? Math.round(
      e + this._lastBarRightSideDiffBarCount - s
    ) - 1 : h;
    if (this._visibleRange = { from: h, to: l, realFrom: u, realTo: c }, this._chartStore.getActionStore().execute(et.OnVisibleRangeChange, this._visibleRange), this._chartStore.adjustVisibleDataList(), h === 0) {
      const d = t[0];
      this._chartStore.executeLoadMoreCallback(d?.timestamp ?? null), this._chartStore.executeLoadDataCallback({
        type: ot.Forward,
        data: d ?? null
      });
    }
    l === e && this._chartStore.executeLoadDataCallback({
      type: ot.Backward,
      data: t[e - 1] ?? null
    });
  }
  getDateTimeFormat() {
    return this._dateTimeFormat;
  }
  _buildDateTimeFormat(t) {
    const e = {
      hour12: !1,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit"
    };
    D(t) && (e.timeZone = t);
    let s = null;
    try {
      s = new Intl.DateTimeFormat("en", e);
    } catch {
    }
    return s;
  }
  setTimezone(t) {
    const e = this._buildDateTimeFormat(t);
    e !== null && (this._dateTimeFormat = e);
  }
  getTimezone() {
    return this._dateTimeFormat.resolvedOptions().timeZone;
  }
  getBarSpace() {
    return {
      bar: this._barSpace,
      halfBar: this._barSpace / 2,
      gapBar: this._gapBarSpace,
      halfGapBar: Math.floor(this._gapBarSpace / 2)
    };
  }
  setBarSpace(t, e) {
    t < Qe.MIN || t > Qe.MAX || this._barSpace === t || (this._barSpace = t, this._gapBarSpace = this._calcGapBarSpace(), e?.(), this.adjustVisibleRange(), this._chartStore.getTooltipStore().recalculateCrosshair(!0), this._chartStore.getChart().adjustPaneViewport(!1, !0, !0, !0));
  }
  setTotalBarSpace(t) {
    return this._totalBarSpace !== t && (this._totalBarSpace = t, this.adjustVisibleRange(), this._chartStore.getTooltipStore().recalculateCrosshair(!0)), this;
  }
  setOffsetRightDistance(t, e) {
    return this._offsetRightDistance = this._scrollLimitRole === 1 ? Math.min(this._maxOffsetDistance.right, t) : t, this._lastBarRightSideDiffBarCount = this._offsetRightDistance / this._barSpace, (e ?? !1) && (this.adjustVisibleRange(), this._chartStore.getTooltipStore().recalculateCrosshair(!0), this._chartStore.getChart().adjustPaneViewport(!1, !0, !0, !0)), this;
  }
  resetOffsetRightDistance() {
    this.setOffsetRightDistance(this._offsetRightDistance);
  }
  getInitialOffsetRightDistance() {
    return this._offsetRightDistance;
  }
  getOffsetRightDistance() {
    return Math.max(0, this._lastBarRightSideDiffBarCount * this._barSpace);
  }
  getLastBarRightSideDiffBarCount() {
    return this._lastBarRightSideDiffBarCount;
  }
  setLastBarRightSideDiffBarCount(t) {
    return this._lastBarRightSideDiffBarCount = t, this;
  }
  setMaxOffsetLeftDistance(t) {
    return this._scrollLimitRole = 1, this._maxOffsetDistance.left = t, this;
  }
  setMaxOffsetRightDistance(t) {
    return this._scrollLimitRole = 1, this._maxOffsetDistance.right = t, this;
  }
  setLeftMinVisibleBarCount(t) {
    return this._scrollLimitRole = 0, this._minVisibleBarCount.left = t, this;
  }
  setRightMinVisibleBarCount(t) {
    return this._scrollLimitRole = 0, this._minVisibleBarCount.right = t, this;
  }
  getVisibleRange() {
    return this._visibleRange;
  }
  startScroll() {
    this._startLastBarRightSideDiffBarCount = this._lastBarRightSideDiffBarCount;
  }
  scroll(t) {
    if (!this._scrollEnabled)
      return;
    const e = t / this._barSpace, s = this._lastBarRightSideDiffBarCount * this._barSpace;
    this._lastBarRightSideDiffBarCount = this._startLastBarRightSideDiffBarCount - e, this.adjustVisibleRange(), this._chartStore.getTooltipStore().recalculateCrosshair(!0), this._chartStore.getChart().adjustPaneViewport(!1, !0, !0, !0);
    const i = Math.round(
      s - this._lastBarRightSideDiffBarCount * this._barSpace
    );
    i !== 0 && this._chartStore.getActionStore().execute(et.OnScroll, { distance: i });
  }
  getDataByDataIndex(t) {
    return this._chartStore.getDataList()[t] ?? null;
  }
  coordinateToFloatIndex(t) {
    const e = this._chartStore.getDataList().length, s = (this._totalBarSpace - t) / this._barSpace, i = e + this._lastBarRightSideDiffBarCount - s;
    return Math.round(i * 1e6) / 1e6;
  }
  dataIndexToTimestamp(t) {
    return this.getDataByDataIndex(t)?.timestamp ?? null;
  }
  timestampToDataIndex(t) {
    const e = this._chartStore.getDataList();
    return e.length === 0 ? 0 : Te(e, "timestamp", t);
  }
  dataIndexToCoordinate(t) {
    const s = this._chartStore.getDataList().length + this._lastBarRightSideDiffBarCount - t;
    return Math.floor(
      this._totalBarSpace - (s - 0.5) * this._barSpace
    );
  }
  coordinateToDataIndex(t) {
    return Math.ceil(this.coordinateToFloatIndex(t)) - 1;
  }
  zoom(t, e) {
    if (!this._zoomEnabled)
      return;
    let s = e ?? null;
    E(s?.x) || (s = { x: this._chartStore.getTooltipStore().getCrosshair()?.x ?? this._totalBarSpace / 2 });
    const i = s.x, o = this.coordinateToFloatIndex(i), r = this._barSpace, a = this._barSpace + t * (this._barSpace / Ee);
    this.setBarSpace(a, () => {
      this._lastBarRightSideDiffBarCount += o - this.coordinateToFloatIndex(i);
    });
    const l = this._barSpace / r;
    l !== 1 && this._chartStore.getActionStore().execute(et.OnZoom, { scale: l });
  }
  setZoomEnabled(t) {
    return this._zoomEnabled = t, this;
  }
  getZoomEnabled() {
    return this._zoomEnabled;
  }
  setScrollEnabled(t) {
    return this._scrollEnabled = t, this;
  }
  getScrollEnabled() {
    return this._scrollEnabled;
  }
  clear() {
    this._visibleRange = Je();
  }
}
const li = {
  name: "AVP",
  shortName: "AVP",
  series: st.Price,
  precision: 2,
  figures: [{ key: "avp", title: "AVP: ", type: "line" }],
  calc: (n) => {
    let t = 0, e = 0;
    return n.map((s) => {
      const i = {}, o = s?.turnover ?? 0, r = s?.volume ?? 0;
      return t += o, e += r, e !== 0 && (i.avp = t / e), i;
    });
  }
}, ci = {
  name: "AO",
  shortName: "AO",
  calcParams: [5, 34],
  figures: [
    {
      key: "ao",
      title: "AO: ",
      type: "bar",
      baseValue: 0,
      styles: (n, t, e) => {
        const { prev: s, current: i } = n, o = s.indicatorData?.ao ?? Number.MIN_SAFE_INTEGER, r = i.indicatorData?.ao ?? Number.MIN_SAFE_INTEGER;
        let a;
        r > o ? a = H(
          t.styles,
          "bars[0].upColor",
          e.bars[0].upColor
        ) : a = H(
          t.styles,
          "bars[0].downColor",
          e.bars[0].downColor
        );
        const l = r > o ? V.Stroke : V.Fill;
        return { color: a, style: l, borderColor: a };
      }
    }
  ],
  calc: (n, t) => {
    const e = t.calcParams, s = Math.max(e[0], e[1]);
    let i = 0, o = 0, r = 0, a = 0;
    return n.map((l, c) => {
      const h = {}, u = (l.low + l.high) / 2;
      if (i += u, o += u, c >= e[0] - 1) {
        r = i / e[0];
        const d = n[c - (e[0] - 1)];
        i -= (d.low + d.high) / 2;
      }
      if (c >= e[1] - 1) {
        a = o / e[1];
        const d = n[c - (e[1] - 1)];
        o -= (d.low + d.high) / 2;
      }
      return c >= s - 1 && (h.ao = r - a), h;
    });
  }
}, hi = {
  name: "BIAS",
  shortName: "BIAS",
  calcParams: [6, 12, 24],
  figures: [
    { key: "bias1", title: "BIAS6: ", type: "line" },
    { key: "bias2", title: "BIAS12: ", type: "line" },
    { key: "bias3", title: "BIAS24: ", type: "line" }
  ],
  regenerateFigures: (n) => n.map((t, e) => ({ key: `bias${e + 1}`, title: `BIAS${t}: `, type: "line" })),
  calc: (n, t) => {
    const { calcParams: e, figures: s } = t, i = [];
    return n.map((o, r) => {
      const a = {}, l = o.close;
      return e.forEach((c, h) => {
        if (i[h] = (i[h] ?? 0) + l, r >= c - 1) {
          const u = i[h] / e[h];
          a[s[h].key] = (l - u) / u * 100, i[h] -= n[r - (c - 1)].close;
        }
      }), a;
    });
  }
};
function ui(n, t) {
  const e = n.length;
  let s = 0;
  return n.forEach((i) => {
    const o = i.close - t;
    s += o * o;
  }), s = Math.abs(s), Math.sqrt(s / e);
}
const di = {
  name: "BOLL",
  shortName: "BOLL",
  series: st.Price,
  calcParams: [20, 2],
  precision: 2,
  shouldOhlc: !0,
  figures: [
    { key: "up", title: "UP: ", type: "line" },
    { key: "mid", title: "MID: ", type: "line" },
    { key: "dn", title: "DN: ", type: "line" }
  ],
  calc: (n, t) => {
    const e = t.calcParams, s = e[0] - 1;
    let i = 0;
    return n.map((o, r) => {
      const a = o.close, l = {};
      if (i += a, r >= s) {
        l.mid = i / e[0];
        const c = ui(n.slice(r - s, r + 1), l.mid);
        l.up = l.mid + e[1] * c, l.dn = l.mid - e[1] * c, i -= n[r - s].close;
      }
      return l;
    });
  }
}, gi = {
  name: "BRAR",
  shortName: "BRAR",
  calcParams: [26],
  figures: [
    { key: "br", title: "BR: ", type: "line" },
    { key: "ar", title: "AR: ", type: "line" }
  ],
  calc: (n, t) => {
    const e = t.calcParams;
    let s = 0, i = 0, o = 0, r = 0;
    return n.map((a, l) => {
      const c = {}, h = a.high, u = a.low, d = a.open, g = (n[l - 1] ?? a).close;
      if (o += h - d, r += d - u, s += h - g, i += g - u, l >= e[0] - 1) {
        r !== 0 ? c.ar = o / r * 100 : c.ar = 0, i !== 0 ? c.br = s / i * 100 : c.br = 0;
        const m = n[l - (e[0] - 1)], f = m.high, _ = m.low, p = m.open, x = (n[l - e[0]] ?? n[l - (e[0] - 1)]).close;
        s -= f - x, i -= x - _, o -= f - p, r -= p - _;
      }
      return c;
    });
  }
}, fi = {
  name: "BBI",
  shortName: "BBI",
  series: st.Price,
  precision: 2,
  calcParams: [3, 6, 12, 24],
  shouldOhlc: !0,
  figures: [{ key: "bbi", title: "BBI: ", type: "line" }],
  calc: (n, t) => {
    const e = t.calcParams, s = Math.max(...e), i = [], o = [];
    return n.map((r, a) => {
      const l = {}, c = r.close;
      if (e.forEach((h, u) => {
        i[u] = (i[u] ?? 0) + c, a >= h - 1 && (o[u] = i[u] / h, i[u] -= n[a - (h - 1)].close);
      }), a >= s - 1) {
        let h = 0;
        o.forEach((u) => {
          h += u;
        }), l.bbi = h / 4;
      }
      return l;
    });
  }
}, mi = {
  name: "candle_volume",
  shortName: "Volume",
  title: "VOLUME: ",
  type: "bar",
  series: st.Volume,
  shouldFormatBigNumber: !0,
  precision: 0,
  minValue: 0,
  calc: (n) => n.map((t) => t.volume),
  createTooltipDataSource: ({
    TViewDataList: n,
    crosshair: t,
    indicator: e,
    defaultStyles: s
  }) => {
    const { dataIndex: i } = t, { result: o } = e;
    if (i !== void 0 && o[i] !== null) {
      const r = s;
      let a;
      const l = n[i];
      return l.close > l.open ? a = r.ohlc?.upColor : l.close < l.open ? a = r.ohlc?.downColor : a = r.ohlc?.noChangeColor, {
        name: "Volume",
        values: [
          { title: "", value: { text: o[i] ?? "n/a", color: a } }
        ]
      };
    }
    return null;
  },
  draw: ({
    ctx: n,
    TViewDataList: t,
    bounding: e,
    visibleRange: s,
    barSpace: i,
    defaultStyles: o,
    indicator: r,
    xAxis: a
  }) => {
    const { from: l, to: c } = s, h = r.result;
    let u = Number.MIN_SAFE_INTEGER;
    for (let f = l; f < c; f++) {
      const _ = h[f];
      u = Math.max(_, u);
    }
    const d = e.height, g = d / 4;
    n.globalCompositeOperation = "destination-over";
    const m = o;
    for (let f = l; f < c; f++) {
      const _ = t[f], p = h[f];
      let x;
      _.close > _.open ? x = m.ohlc?.upColor : _.close < _.open ? x = m.ohlc?.downColor : x = m.ohlc?.noChangeColor;
      const y = a.convertToPixel(f);
      n.fillStyle = x;
      const v = d - p / u * g;
      n.fillRect(
        y - i.halfGapBar,
        v,
        i.gapBar,
        d - v
      );
    }
    return !1;
  }
}, pi = {
  name: "CCI",
  shortName: "CCI",
  calcParams: [20],
  figures: [{ key: "cci", title: "CCI: ", type: "line" }],
  calc: (n, t) => {
    const e = t.calcParams, s = e[0] - 1;
    let i = 0;
    const o = [];
    return n.map((r, a) => {
      const l = {}, c = (r.high + r.low + r.close) / 3;
      if (i += c, o.push(c), a >= s) {
        const h = i / e[0], u = o.slice(a - s, a + 1);
        let d = 0;
        u.forEach((f) => {
          d += Math.abs(f - h);
        });
        const g = d / e[0];
        l.cci = g !== 0 ? (c - h) / g / 0.015 : 0;
        const m = (n[a - s].high + n[a - s].low + n[a - s].close) / 3;
        i -= m;
      }
      return l;
    });
  }
}, _i = {
  name: "CR",
  shortName: "CR",
  calcParams: [26, 10, 20, 40, 60],
  figures: [
    { key: "cr", title: "CR: ", type: "line" },
    { key: "ma1", title: "MA1: ", type: "line" },
    { key: "ma2", title: "MA2: ", type: "line" },
    { key: "ma3", title: "MA3: ", type: "line" },
    { key: "ma4", title: "MA4: ", type: "line" }
  ],
  calc: (n, t) => {
    const e = t.calcParams, s = Math.ceil(e[1] / 2.5 + 1), i = Math.ceil(e[2] / 2.5 + 1), o = Math.ceil(e[3] / 2.5 + 1), r = Math.ceil(e[4] / 2.5 + 1);
    let a = 0;
    const l = [];
    let c = 0;
    const h = [];
    let u = 0;
    const d = [];
    let g = 0;
    const m = [], f = [];
    return n.forEach((_, p) => {
      const x = {}, y = n[p - 1] ?? _, v = (y.high + y.close + y.low + y.open) / 4, S = Math.max(0, _.high - v), w = Math.max(0, v - _.low);
      p >= e[0] - 1 && (w !== 0 ? x.cr = S / w * 100 : x.cr = 0, a += x.cr, c += x.cr, u += x.cr, g += x.cr, p >= e[0] + e[1] - 2 && (l.push(a / e[1]), p >= e[0] + e[1] + s - 3 && (x.ma1 = l[l.length - 1 - s]), a -= f[p - (e[1] - 1)].cr ?? 0), p >= e[0] + e[2] - 2 && (h.push(c / e[2]), p >= e[0] + e[2] + i - 3 && (x.ma2 = h[h.length - 1 - i]), c -= f[p - (e[2] - 1)].cr ?? 0), p >= e[0] + e[3] - 2 && (d.push(u / e[3]), p >= e[0] + e[3] + o - 3 && (x.ma3 = d[d.length - 1 - o]), u -= f[p - (e[3] - 1)].cr ?? 0), p >= e[0] + e[4] - 2 && (m.push(g / e[4]), p >= e[0] + e[4] + r - 3 && (x.ma4 = m[m.length - 1 - r]), g -= f[p - (e[4] - 1)].cr ?? 0)), f.push(x);
    }), f;
  }
}, xi = {
  name: "DMA",
  shortName: "DMA",
  calcParams: [10, 50, 10],
  figures: [
    { key: "dma", title: "DMA: ", type: "line" },
    { key: "ama", title: "AMA: ", type: "line" }
  ],
  calc: (n, t) => {
    const e = t.calcParams, s = Math.max(e[0], e[1]);
    let i = 0, o = 0, r = 0;
    const a = [];
    return n.forEach((l, c) => {
      const h = {}, u = l.close;
      i += u, o += u;
      let d = 0, g = 0;
      if (c >= e[0] - 1 && (d = i / e[0], i -= n[c - (e[0] - 1)].close), c >= e[1] - 1 && (g = o / e[1], o -= n[c - (e[1] - 1)].close), c >= s - 1) {
        const m = d - g;
        h.dma = m, r += m, c >= s + e[2] - 2 && (h.ama = r / e[2], r -= a[c - (e[2] - 1)].dma ?? 0);
      }
      a.push(h);
    }), a;
  }
}, yi = {
  name: "DMI",
  shortName: "DMI",
  calcParams: [14, 6],
  figures: [
    { key: "pdi", title: "PDI: ", type: "line" },
    { key: "mdi", title: "MDI: ", type: "line" },
    { key: "adx", title: "ADX: ", type: "line" },
    { key: "adxr", title: "ADXR: ", type: "line" }
  ],
  calc: (n, t) => {
    const e = t.calcParams;
    let s = 0, i = 0, o = 0, r = 0, a = 0, l = 0, c = 0, h = 0;
    const u = [];
    return n.forEach((d, g) => {
      const m = {}, f = n[g - 1] ?? d, _ = f.close, p = d.high, x = d.low, y = p - x, v = Math.abs(p - _), S = Math.abs(_ - x), w = p - f.high, b = f.low - x, I = Math.max(Math.max(y, v), S), T = w > 0 && w > b ? w : 0, P = b > 0 && b > w ? b : 0;
      if (s += I, i += T, o += P, g >= e[0] - 1) {
        g > e[0] - 1 ? (r = r - r / e[0] + I, a = a - a / e[0] + T, l = l - l / e[0] + P) : (r = s, a = i, l = o);
        let M = 0, B = 0;
        r !== 0 && (M = a * 100 / r, B = l * 100 / r), m.pdi = M, m.mdi = B;
        let X = 0;
        B + M !== 0 && (X = Math.abs(B - M) / (B + M) * 100), c += X, g >= e[0] * 2 - 2 && (g > e[0] * 2 - 2 ? h = (h * (e[0] - 1) + X) / e[0] : h = c / e[0], m.adx = h, g >= e[0] * 2 + e[1] - 3 && (m.adxr = ((u[g - (e[1] - 1)].adx ?? 0) + h) / 2));
      }
      u.push(m);
    }), u;
  }
}, vi = {
  name: "EMV",
  shortName: "EMV",
  calcParams: [14, 9],
  figures: [
    { key: "emv", title: "EMV: ", type: "line" },
    { key: "maEmv", title: "MAEMV: ", type: "line" }
  ],
  calc: (n, t) => {
    const e = t.calcParams;
    let s = 0;
    const i = [];
    return n.map((o, r) => {
      const a = {};
      if (r > 0) {
        const l = n[r - 1], c = o.high, h = o.low, u = o.volume ?? 0, d = (c + h) / 2 - (l.high + l.low) / 2;
        if (u === 0 || c - h === 0)
          a.emv = 0;
        else {
          const g = u / 1e8 / (c - h);
          a.emv = d / g;
        }
        s += a.emv, i.push(a.emv), r >= e[0] && (a.maEmv = s / e[0], s -= i[r - e[0]]);
      }
      return a;
    });
  }
}, Si = {
  name: "EMA",
  shortName: "EMA",
  series: st.Price,
  calcParams: [9],
  precision: 2,
  shouldOhlc: !1,
  figures: [{ key: "ema", title: "EMA: ", type: "line" }],
  regenerateFigures: (n) => n.map((t, e) => ({ key: `ema${e + 1}`, title: `EMA${t}: `, type: "line" })),
  calc: (n, t) => {
    const { calcParams: e, figures: s } = t;
    let i = 0;
    const o = [];
    return n.map((r, a) => {
      const l = {}, c = r.close;
      return i += c, e.forEach((h, u) => {
        a >= h - 1 && (a > h - 1 ? o[u] = (2 * c + (h - 1) * o[u]) / (h + 1) : o[u] = i / h, l[s[u].key] = o[u]);
      }), l;
    });
  }
}, Ci = {
  name: "MTM",
  shortName: "MTM",
  calcParams: [12, 6],
  figures: [
    { key: "mtm", title: "MTM: ", type: "line" },
    { key: "maMtm", title: "MAMTM: ", type: "line" }
  ],
  calc: (n, t) => {
    const e = t.calcParams;
    let s = 0;
    const i = [];
    return n.forEach((o, r) => {
      const a = {};
      if (r >= e[0]) {
        const l = o.close, c = n[r - e[0]].close;
        a.mtm = l - c, s += a.mtm, r >= e[0] + e[1] - 1 && (a.maMtm = s / e[1], s -= i[r - (e[1] - 1)].mtm ?? 0);
      }
      i.push(a);
    }), i;
  }
}, wi = {
  name: "MA",
  shortName: "MA",
  series: st.Price,
  calcParams: [5],
  precision: 2,
  shouldOhlc: !1,
  figures: [{ key: "ma", title: "MA: ", type: "line" }],
  regenerateFigures: (n) => n.map((t, e) => ({ key: `ma${e + 1}`, title: `MA${t}: `, type: "line" })),
  calc: (n, t) => {
    const { calcParams: e, figures: s } = t, i = [];
    return n.map((o, r) => {
      const a = {}, l = o.close;
      return e.forEach((c, h) => {
        i[h] = (i[h] ?? 0) + l, r >= c - 1 && (a[s[h].key] = i[h] / c, i[h] -= n[r - (c - 1)].close);
      }), a;
    });
  }
}, bi = {
  name: "MACD",
  shortName: "MACD",
  calcParams: [12, 26, 9],
  figures: [
    { key: "dif", title: "DIF: ", type: "line" },
    { key: "dea", title: "DEA: ", type: "line" },
    {
      key: "macd",
      title: "MACD: ",
      type: "bar",
      baseValue: 0,
      styles: (n, t, e) => {
        const { prev: s, current: i } = n, o = s.indicatorData?.macd ?? Number.MIN_SAFE_INTEGER, r = i.indicatorData?.macd ?? Number.MIN_SAFE_INTEGER;
        let a;
        return r > 0 ? a = H(
          t.styles,
          "bars[0].upColor",
          e.bars[0].upColor
        ) : r < 0 ? a = H(
          t.styles,
          "bars[0].downColor",
          e.bars[0].downColor
        ) : a = H(
          t.styles,
          "bars[0].noChangeColor",
          e.bars[0].noChangeColor
        ), { style: o < r ? V.Stroke : V.Fill, color: a, borderColor: a };
      }
    }
  ],
  calc: (n, t) => {
    const e = t.calcParams;
    let s = 0, i, o, r = 0, a = 0, l = 0;
    const c = Math.max(e[0], e[1]);
    return n.map((h, u) => {
      const d = {}, g = h.close;
      return s += g, u >= e[0] - 1 && (u > e[0] - 1 ? i = (2 * g + (e[0] - 1) * i) / (e[0] + 1) : i = s / e[0]), u >= e[1] - 1 && (u > e[1] - 1 ? o = (2 * g + (e[1] - 1) * o) / (e[1] + 1) : o = s / e[1]), u >= c - 1 && (r = i - o, d.dif = r, a += r, u >= c + e[2] - 2 && (u > c + e[2] - 2 ? l = (r * 2 + l * (e[2] - 1)) / (e[2] + 1) : l = a / e[2], d.macd = (r - l) * 2, d.dea = l)), d;
    });
  }
}, Ii = {
  name: "OBV",
  shortName: "OBV",
  calcParams: [30],
  figures: [
    { key: "obv", title: "OBV: ", type: "line" },
    { key: "maObv", title: "MAOBV: ", type: "line" }
  ],
  calc: (n, t) => {
    const e = t.calcParams;
    let s = 0, i = 0;
    const o = [];
    return n.forEach((r, a) => {
      const l = n[a - 1] ?? r;
      r.close < l.close ? i -= r.volume ?? 0 : r.close > l.close && (i += r.volume ?? 0);
      const c = { obv: i };
      s += i, a >= e[0] - 1 && (c.maObv = s / e[0], s -= o[a - (e[0] - 1)].obv ?? 0), o.push(c);
    }), o;
  }
}, Ti = {
  name: "PVT",
  shortName: "PVT",
  figures: [{ key: "pvt", title: "PVT: ", type: "line" }],
  calc: (n) => {
    let t = 0;
    return n.map((e, s) => {
      const i = {}, o = e.close, r = e.volume ?? 1, a = (n[s - 1] ?? e).close;
      let l = 0;
      const c = a * r;
      return c !== 0 && (l = (o - a) / c), t += l, i.pvt = t, i;
    });
  }
}, Ei = {
  name: "PSY",
  shortName: "PSY",
  calcParams: [12, 6],
  figures: [
    { key: "psy", title: "PSY: ", type: "line" },
    { key: "maPsy", title: "MAPSY: ", type: "line" }
  ],
  calc: (n, t) => {
    const e = t.calcParams;
    let s = 0, i = 0;
    const o = [], r = [];
    return n.forEach((a, l) => {
      const c = {}, h = (n[l - 1] ?? a).close, u = a.close - h > 0 ? 1 : 0;
      o.push(u), s += u, l >= e[0] - 1 && (c.psy = s / e[0] * 100, i += c.psy, l >= e[0] + e[1] - 2 && (c.maPsy = i / e[1], i -= r[l - (e[1] - 1)].psy ?? 0), s -= o[l - (e[0] - 1)]), r.push(c);
    }), r;
  }
}, Pi = {
  name: "ROC",
  shortName: "ROC",
  calcParams: [12, 6],
  figures: [
    { key: "roc", title: "ROC: ", type: "line" },
    { key: "maRoc", title: "MAROC: ", type: "line" }
  ],
  calc: (n, t) => {
    const e = t.calcParams, s = [];
    let i = 0;
    return n.forEach((o, r) => {
      const a = {};
      if (r >= e[0] - 1) {
        const l = o.close, c = (n[r - e[0]] ?? n[r - (e[0] - 1)]).close;
        c !== 0 ? a.roc = (l - c) / c * 100 : a.roc = 0, i += a.roc, r >= e[0] - 1 + e[1] - 1 && (a.maRoc = i / e[1], i -= s[r - (e[1] - 1)].roc ?? 0);
      }
      s.push(a);
    }), s;
  }
}, Mi = {
  name: "RSI",
  shortName: "RSI",
  calcParams: [6, 12, 24],
  figures: [
    { key: "rsi1", title: "RSI1: ", type: "line" },
    { key: "rsi2", title: "RSI2: ", type: "line" },
    { key: "rsi3", title: "RSI3: ", type: "line" }
  ],
  regenerateFigures: (n) => n.map((t, e) => {
    const s = e + 1;
    return { key: `rsi${s}`, title: `RSI${s}: `, type: "line" };
  }),
  calc: (n, t) => {
    const { calcParams: e, figures: s } = t, i = [], o = [];
    return n.map((r, a) => {
      const l = {}, c = (n[a - 1] ?? r).close, h = r.close - c;
      return e.forEach((u, d) => {
        if (h > 0 ? i[d] = (i[d] ?? 0) + h : o[d] = (o[d] ?? 0) + Math.abs(h), a >= u - 1) {
          o[d] !== 0 ? l[s[d].key] = 100 - 100 / (1 + i[d] / o[d]) : l[s[d].key] = 0;
          const g = n[a - (u - 1)], m = n[a - u] ?? g, f = g.close - m.close;
          f > 0 ? i[d] -= f : o[d] -= Math.abs(f);
        }
      }), l;
    });
  }
}, Di = {
  name: "SMA",
  shortName: "SMA",
  series: st.Price,
  calcParams: [12, 2],
  precision: 2,
  figures: [{ key: "sma", title: "SMA: ", type: "line" }],
  shouldOhlc: !0,
  calc: (n, t) => {
    const e = t.calcParams;
    let s = 0, i = 0;
    return n.map((o, r) => {
      const a = {}, l = o.close;
      return s += l, r >= e[0] - 1 && (r > e[0] - 1 ? i = (l * e[1] + i * (e[0] - e[1] + 1)) / (e[0] + 1) : i = s / e[0], a.sma = i), a;
    });
  }
}, Ai = {
  name: "KDJ",
  shortName: "KDJ",
  calcParams: [9, 3, 3],
  figures: [
    { key: "k", title: "K: ", type: "line" },
    { key: "d", title: "D: ", type: "line" },
    { key: "j", title: "J: ", type: "line" }
  ],
  calc: (n, t) => {
    const e = t.calcParams, s = [];
    return n.forEach((i, o) => {
      const r = {}, a = i.close;
      if (o >= e[0] - 1) {
        const l = Ae(
          n.slice(o - (e[0] - 1), o + 1),
          "high",
          "low"
        ), c = l[0], h = l[1], u = c - h, d = (a - h) / (u === 0 ? 1 : u) * 100;
        r.k = ((e[1] - 1) * (s[o - 1]?.k ?? 50) + d) / e[1], r.d = ((e[2] - 1) * (s[o - 1]?.d ?? 50) + r.k) / e[2], r.j = 3 * r.k - 2 * r.d;
      }
      s.push(r);
    }), s;
  }
}, ki = {
  name: "SAR",
  shortName: "SAR",
  series: st.Price,
  calcParams: [2, 2, 20],
  precision: 2,
  shouldOhlc: !0,
  figures: [
    {
      key: "sar",
      title: "SAR: ",
      type: "circle",
      styles: (n, t, e) => {
        const { current: s } = n, i = s.indicatorData?.sar ?? Number.MIN_SAFE_INTEGER, o = s.TViewData, r = (o?.high + o?.low) / 2;
        return { color: i < r ? H(
          t.styles,
          "circles[0].upColor",
          e.circles[0].upColor
        ) : H(
          t.styles,
          "circles[0].downColor",
          e.circles[0].downColor
        ) };
      }
    }
  ],
  calc: (n, t) => {
    const e = t.calcParams, s = e[0] / 100, i = e[1] / 100, o = e[2] / 100;
    let r = s, a = -100, l = !1, c = 0;
    return n.map((h, u) => {
      const d = c, g = h.high, m = h.low;
      if (l) {
        (a === -100 || a < g) && (a = g, r = Math.min(r + i, o)), c = d + r * (a - d);
        const f = Math.min(n[Math.max(1, u) - 1].low, m);
        c > h.low ? (c = a, r = s, a = -100, l = !l) : c > f && (c = f);
      } else {
        (a === -100 || a > m) && (a = m, r = Math.min(r + i, o)), c = d + r * (a - d);
        const f = Math.max(n[Math.max(1, u) - 1].high, g);
        c < h.high ? (c = a, r = 0, a = -100, l = !l) : c < f && (c = f);
      }
      return { sar: c };
    });
  }
}, Fi = {
  name: "TRIX",
  shortName: "TRIX",
  calcParams: [12, 9],
  figures: [
    { key: "trix", title: "TRIX: ", type: "line" },
    { key: "maTrix", title: "MATRIX: ", type: "line" }
  ],
  calc: (n, t) => {
    const e = t.calcParams;
    let s = 0, i, o, r, a = 0, l = 0, c = 0;
    const h = [];
    return n.forEach((u, d) => {
      const g = {}, m = u.close;
      if (s += m, d >= e[0] - 1 && (d > e[0] - 1 ? i = (2 * m + (e[0] - 1) * i) / (e[0] + 1) : i = s / e[0], a += i, d >= e[0] * 2 - 2 && (d > e[0] * 2 - 2 ? o = (2 * i + (e[0] - 1) * o) / (e[0] + 1) : o = a / e[0], l += o, d >= e[0] * 3 - 3))) {
        let f, _ = 0;
        d > e[0] * 3 - 3 ? (f = (2 * o + (e[0] - 1) * r) / (e[0] + 1), _ = (f - r) / r * 100) : f = l / e[0], r = f, g.trix = _, c += _, d >= e[0] * 3 + e[1] - 4 && (g.maTrix = c / e[1], c -= h[d - (e[1] - 1)].trix ?? 0);
      }
      h.push(g);
    }), h;
  }
};
function ts() {
  return {
    key: "volume",
    title: "VOLUME: ",
    type: "bar",
    baseValue: 0,
    styles: (n, t, e) => {
      const s = n.current.TViewData;
      let i = H(
        t.styles,
        "bars[0].noChangeColor",
        e.bars[0].noChangeColor
      );
      return C(s) && (s.close > s.open ? i = H(
        t.styles,
        "bars[0].upColor",
        e.bars[0].upColor
      ) : s.close < s.open && (i = H(
        t.styles,
        "bars[0].downColor",
        e.bars[0].downColor
      ))), { color: i };
    }
  };
}
const Li = {
  name: "VOL",
  shortName: "VOL",
  series: st.Volume,
  calcParams: [],
  shouldFormatBigNumber: !0,
  precision: 0,
  minValue: 0,
  figures: [
    // { key: 'ma1', title: 'MA5: ', type: 'line' },
    // { key: 'ma2', title: 'MA10: ', type: 'line' },
    // { key: 'ma3', title: 'MA20: ', type: 'line' },
    ts()
  ],
  regenerateFigures: (n) => {
    const t = n.map(
      (e, s) => ({ key: `ma${s + 1}`, title: `MA${e}: `, type: "line" })
    );
    return t.push(ts()), t;
  },
  calc: (n) => n.map((t) => ({ volume: t.volume ?? 0 }))
}, Bi = {
  name: "VR",
  shortName: "VR",
  calcParams: [26, 6],
  figures: [
    { key: "vr", title: "VR: ", type: "line" },
    { key: "maVr", title: "MAVR: ", type: "line" }
  ],
  calc: (n, t) => {
    const e = t.calcParams;
    let s = 0, i = 0, o = 0, r = 0;
    const a = [];
    return n.forEach((l, c) => {
      const h = {}, u = l.close, d = (n[c - 1] ?? l).close, g = l.volume ?? 0;
      if (u > d ? s += g : u < d ? i += g : o += g, c >= e[0] - 1) {
        const m = o / 2;
        i + m === 0 ? h.vr = 0 : h.vr = (s + m) / (i + m) * 100, r += h.vr, c >= e[0] + e[1] - 2 && (h.maVr = r / e[1], r -= a[c - (e[1] - 1)].vr ?? 0);
        const f = n[c - (e[0] - 1)], _ = n[c - e[0]] ?? f, p = f.close, x = f.volume ?? 0;
        p > _.close ? s -= x : p < _.close ? i -= x : o -= x;
      }
      a.push(h);
    }), a;
  }
}, Ri = {
  name: "WR",
  shortName: "WR",
  calcParams: [6, 10, 14],
  figures: [
    { key: "wr1", title: "WR1: ", type: "line" },
    { key: "wr2", title: "WR2: ", type: "line" },
    { key: "wr3", title: "WR3: ", type: "line" }
  ],
  regenerateFigures: (n) => n.map((t, e) => ({ key: `wr${e + 1}`, title: `WR${e + 1}: `, type: "line" })),
  calc: (n, t) => {
    const { calcParams: e, figures: s } = t;
    return n.map((i, o) => {
      const r = {}, a = i.close;
      return e.forEach((l, c) => {
        const h = l - 1;
        if (o >= h) {
          const u = Ae(
            n.slice(o - h, o + 1),
            "high",
            "low"
          ), d = u[0], g = u[1], m = d - g;
          r[s[c].key] = m === 0 ? 0 : (a - d) / m * 100;
        }
      }), r;
    });
  }
}, he = {}, Oi = [
  li,
  ci,
  hi,
  di,
  gi,
  fi,
  pi,
  _i,
  xi,
  yi,
  vi,
  Si,
  Ci,
  wi,
  bi,
  Ii,
  Ti,
  Ei,
  Pi,
  Mi,
  Di,
  Ai,
  ki,
  Fi,
  Li,
  Bi,
  Ri,
  mi
];
Oi.forEach((n) => {
  he[n.name] = le.extend(n);
});
function ao(n) {
  he[n.name] = le.extend(n);
}
function cs(n) {
  return he[n] ?? null;
}
function lo() {
  return Object.keys(he);
}
class Vi {
  constructor(t) {
    this._instances = /* @__PURE__ */ new Map(), this._chartStore = t;
  }
  _sort(t) {
    D(t) ? this._instances.get(t)?.sort((e, s) => e.getIndicator().zLevel - s.getIndicator().zLevel) : this._instances.forEach((e) => {
      e.sort(
        (s, i) => s.getIndicator().zLevel - i.getIndicator().zLevel
      );
    });
  }
  async addInstance(t, e, s) {
    const { name: i } = t;
    let o = this._instances.get(e);
    if (C(o)) {
      const l = o.find(
        (c) => c.getIndicator().name === i
      );
      if (C(l))
        return await Promise.reject(new Error("Duplicate indicators."));
    }
    C(o) || (o = []);
    const r = cs(i), a = new r();
    return this.synchronizeSeriesPrecision(a), a.override(t), s || (o = []), o.push(a), this._instances.set(e, o), this._sort(e), await a.calc(this._chartStore.getDataList());
  }
  getInstances(t) {
    return this._instances.get(t) ?? [];
  }
  removeInstance(t, e) {
    let s = !1;
    const i = this._instances.get(t);
    if (C(i)) {
      if (D(e)) {
        const o = i.findIndex(
          (r) => r.getIndicator().name === e
        );
        o > -1 && (i.splice(o, 1), s = !0);
      } else
        this._instances.set(t, []), s = !0;
      this._instances.get(t)?.length === 0 && this._instances.delete(t);
    }
    return s;
  }
  hasInstances(t) {
    return this._instances.has(t);
  }
  async calcInstance(t, e) {
    const s = [];
    if (D(t))
      if (D(e)) {
        const o = this._instances.get(e);
        if (C(o)) {
          const r = o.find(
            (a) => a.getIndicator().name === t
          );
          C(r) && s.push(r.calc(this._chartStore.getDataList()));
        }
      } else
        this._instances.forEach((o) => {
          const r = o.find(
            (a) => a.getIndicator().name === t
          );
          C(r) && s.push(r.calc(this._chartStore.getDataList()));
        });
    else
      this._instances.forEach((o) => {
        o.forEach((r) => {
          s.push(r.calc(this._chartStore.getDataList()));
        });
      });
    return (await Promise.all(s)).includes(!0);
  }
  getInstanceByPaneId(t, e) {
    const s = (o) => {
      const r = /* @__PURE__ */ new Map();
      return o.forEach((a) => {
        r.set(a.getIndicator().name, a.getIndicator());
      }), r;
    };
    if (D(t)) {
      const o = this._instances.get(t) ?? [];
      return D(e) ? o?.find((r) => r.getIndicator().name === e)?.getIndicator() ?? null : s(o);
    }
    const i = /* @__PURE__ */ new Map();
    return this._instances.forEach((o, r) => {
      i.set(r, s(o));
    }), i;
  }
  synchronizeSeriesPrecision(t) {
    const { price: e, volume: s } = this._chartStore.getPrecision(), i = (o) => {
      switch (o.getIndicator().series) {
        case st.Price: {
          o.setSeriesPrecision(e);
          break;
        }
        case st.Volume: {
          o.setSeriesPrecision(s);
          break;
        }
      }
    };
    C(t) ? i(t) : this._instances.forEach((o) => {
      o.forEach((r) => {
        i(r);
      });
    });
  }
  async override(t, e) {
    const { name: s } = t;
    let i = /* @__PURE__ */ new Map();
    if (e !== null) {
      const c = this._instances.get(e);
      C(c) && i.set(e, c);
    } else
      i = this._instances;
    let o = !1;
    const r = [];
    let a = !1;
    i.forEach((c) => {
      const h = c.find(
        (u) => u.getIndicator().name === s
      );
      if (C(h)) {
        h.override(t);
        const { calc: u, draw: d, sort: g } = h.shouldUpdate();
        g && (a = !0), u ? r.push(h.calc(this._chartStore.getDataList())) : d && (o = !0);
      }
    }), a && this._sort();
    const l = await Promise.all(r);
    return [o, l.includes(!0)];
  }
}
class Ni {
  constructor(t) {
    this._crosshair = {}, this._activeIcon = null, this._chartStore = t;
  }
  /**
   * 设置十字光标点信息
   * @param crosshair
   * @param notInvalidate
   */
  setCrosshair(t, e) {
    const s = this._chartStore.getDataList(), i = t ?? {};
    let o, r;
    E(i.x) ? (o = this._chartStore.getTimeScaleStore().coordinateToDataIndex(i.x), o < 0 ? r = 0 : o > s.length - 1 ? r = s.length - 1 : r = o) : (o = s.length - 1, r = o);
    const a = s[r], l = this._chartStore.getTimeScaleStore().dataIndexToCoordinate(o), c = {
      x: this._crosshair.x,
      y: this._crosshair.y,
      paneId: this._crosshair.paneId
    };
    this._crosshair = { ...i, realX: l, TViewData: a, realDataIndex: o, dataIndex: r }, (c.x !== i.x || c.y !== i.y || c.paneId !== i.paneId) && (a !== null && this._chartStore.getChart().crosshairChange(this._crosshair), (e ?? !1) || this._chartStore.getChart().updatePane(F.Overlay));
  }
  /**
   * 重新计算十字光标
   * @param notInvalidate
   */
  recalculateCrosshair(t) {
    this.setCrosshair(this._crosshair, t);
  }
  /**
   * 获取crosshair信息
   * @returns
   */
  getCrosshair() {
    return this._crosshair;
  }
  setActiveIcon(t) {
    this._activeIcon = t ?? null;
  }
  getActiveIcon() {
    return this._activeIcon;
  }
  clear() {
    this.setCrosshair({}, !0), this.setActiveIcon();
  }
}
const Wi = {
  name: "fibonacciLine",
  totalStep: 3,
  needDefaultPointFigure: !0,
  needDefaultXAxisFigure: !0,
  needDefaultYAxisFigure: !0,
  createPointFigures: ({
    coordinates: n,
    bounding: t,
    overlay: e,
    precision: s,
    thousandsSeparator: i,
    decimalFoldThreshold: o,
    yAxis: r
  }) => {
    const a = e.points;
    if (n.length > 0) {
      const l = r?.isInCandle() ?? !0 ? s.price : s.excludePriceVolumeMax, c = [], h = [], u = 0, d = t.width;
      if (n.length > 1 && E(a[0].value) && E(a[1].value)) {
        const g = [1, 0.786, 0.618, 0.5, 0.382, 0.236, 0], m = n[0].y - n[1].y, f = a[0].value - a[1].value;
        g.forEach((_) => {
          const p = n[1].y + m * _, x = z(
            W(
              ((a[1].value ?? 0) + f * _).toFixed(
                l
              ),
              i
            ),
            o
          );
          c.push({
            coordinates: [
              { x: u, y: p },
              { x: d, y: p }
            ]
          }), h.push({
            x: u,
            y: p,
            text: `${x} (${(_ * 100).toFixed(1)}%)`,
            baseline: "bottom"
          });
        });
      }
      return [
        {
          type: "line",
          attrs: c
        },
        {
          type: "text",
          isCheckEvent: !1,
          attrs: h
        }
      ];
    }
    return [];
  }
}, zi = {
  name: "horizontalRayLine",
  totalStep: 3,
  needDefaultPointFigure: !0,
  needDefaultXAxisFigure: !0,
  needDefaultYAxisFigure: !0,
  createPointFigures: ({ coordinates: n, bounding: t }) => {
    const e = { x: 0, y: n[0].y };
    return C(n[1]) && n[0].x < n[1].x && (e.x = t.width), [
      {
        type: "line",
        attrs: { coordinates: [n[0], e] }
      }
    ];
  },
  performEventPressedMove: ({ points: n, performPoint: t }) => {
    n[0].value = t.value, n[1].value = t.value;
  },
  performEventMoveForDrawing: ({ currentStep: n, points: t, performPoint: e }) => {
    n === 2 && (t[0].value = e.value);
  }
}, Xi = {
  name: "horizontalSegment",
  totalStep: 3,
  needDefaultPointFigure: !0,
  needDefaultXAxisFigure: !0,
  needDefaultYAxisFigure: !0,
  createPointFigures: ({ coordinates: n }) => {
    const t = [];
    return n.length === 2 && t.push({ coordinates: n }), [
      {
        type: "line",
        attrs: t
      }
    ];
  },
  performEventPressedMove: ({ points: n, performPoint: t }) => {
    n[0].value = t.value, n[1].value = t.value;
  },
  performEventMoveForDrawing: ({ currentStep: n, points: t, performPoint: e }) => {
    n === 2 && (t[0].value = e.value);
  }
}, Yi = {
  name: "horizontalStraightLine",
  totalStep: 2,
  needDefaultPointFigure: !0,
  needDefaultXAxisFigure: !0,
  needDefaultYAxisFigure: !0,
  createPointFigures: ({ coordinates: n, bounding: t }) => [
    {
      type: "line",
      attrs: {
        coordinates: [
          {
            x: 0,
            y: n[0].y
          },
          {
            x: t.width,
            y: n[0].y
          }
        ]
      }
    }
  ]
};
class ke {
  constructor() {
    this._children = [], this._callbacks = /* @__PURE__ */ new Map();
  }
  registerEvent(t, e) {
    return this._callbacks.set(t, e), this;
  }
  onEvent(t, e, s) {
    const i = this._callbacks.get(t);
    return C(i) && this.checkEventOn(e) ? i(e, s) : !1;
  }
  checkEventOn(t) {
    for (const e of this._children)
      if (e.checkEventOn(t))
        return !0;
    return !1;
  }
  dispatchEvent(t, e, s) {
    const i = this._children.length - 1;
    if (i > -1) {
      for (let o = i; o > -1; o--)
        if (this._children[o].dispatchEvent(t, e, s))
          return !0;
    }
    return this.onEvent(t, e, s);
  }
  addChild(t) {
    return this._children.push(t), this;
  }
  clear() {
    this._children = [];
  }
}
const Y = 2;
class ue extends ke {
  constructor(t) {
    super(), this.attrs = t.attrs, this.styles = t.styles;
  }
  checkEventOn(t) {
    return this.checkEventOnImp(t, this.attrs, this.styles);
  }
  setAttrs(t) {
    return this.attrs = t, this;
  }
  setStyles(t) {
    return this.styles = t, this;
  }
  draw(t) {
    this.drawImp(t, this.attrs, this.styles);
  }
  static extend(t) {
    class e extends ue {
      checkEventOnImp(i, o, r) {
        return t.checkEventOn(i, o, r);
      }
      drawImp(i, o, r) {
        t.draw(i, o, r);
      }
    }
    return e;
  }
}
function hs(n, t) {
  let e = [];
  e = e.concat(t);
  for (let s = 0; s < e.length; s++) {
    const { coordinates: i } = e[s];
    if (i.length > 1)
      for (let o = 1; o < i.length; o++) {
        const r = i[o - 1], a = i[o];
        if (r.x === a.x) {
          if (Math.abs(r.y - n.y) + Math.abs(a.y - n.y) - Math.abs(r.y - a.y) < Y + Y && Math.abs(n.x - r.x) < Y)
            return !0;
        } else {
          const l = de(
            r,
            a
          ), c = Fe(l, n), h = Math.abs(c - n.y);
          if (Math.abs(r.x - n.x) + Math.abs(a.x - n.x) - Math.abs(r.x - a.x) < Y + Y && h * h / (l[0] * l[0] + 1) < Y * Y)
            return !0;
        }
      }
  }
  return !1;
}
function Fe(n, t) {
  return n !== null ? t.x * n[0] + n[1] : t.y;
}
function Ut(n, t, e) {
  const s = de(n, t);
  return Fe(s, e);
}
function de(n, t) {
  const e = n.x - t.x;
  if (e !== 0) {
    const s = (n.y - t.y) / e, i = n.y - s * n.x;
    return [s, i];
  }
  return null;
}
function ie(n, t, e) {
  const s = t.length, i = E(e) ? e > 0 && e < 1 ? e : 0 : e ? 0.5 : 0;
  if (i > 0 && s > 2) {
    let o = t[0].x, r = t[0].y;
    for (let l = 1; l < s - 1; l++) {
      const c = t[l - 1], h = t[l], u = t[l + 1], d = h.x - c.x, g = h.y - c.y, m = u.x - h.x, f = u.y - h.y;
      let _ = u.x - c.x, p = u.y - c.y;
      const x = Math.sqrt(d * d + g * g), y = Math.sqrt(m * m + f * f), v = y / (y + x);
      let S = h.x + _ * i * v, w = h.y + p * i * v;
      S = Math.min(S, Math.max(u.x, h.x)), w = Math.min(w, Math.max(u.y, h.y)), S = Math.max(S, Math.min(u.x, h.x)), w = Math.max(w, Math.min(u.y, h.y)), _ = S - h.x, p = w - h.y;
      let b = h.x - _ * x / y, I = h.y - p * x / y;
      b = Math.min(b, Math.max(c.x, h.x)), I = Math.min(I, Math.max(c.y, h.y)), b = Math.max(b, Math.min(c.x, h.x)), I = Math.max(I, Math.min(c.y, h.y)), _ = h.x - b, p = h.y - I, S = h.x + _ * y / x, w = h.y + p * y / x, n.bezierCurveTo(o, r, b, I, h.x, h.y), o = S, r = w;
    }
    const a = t[s - 1];
    n.bezierCurveTo(
      o,
      r,
      a.x,
      a.y,
      a.x,
      a.y
    );
  } else
    for (let o = 1; o < s; o++)
      n.lineTo(t[o].x, t[o].y);
}
function us(n, t, e) {
  let s = [];
  s = s.concat(t);
  const {
    style: i = Q.Solid,
    smooth: o = !1,
    size: r = 1,
    color: a = "currentColor",
    dashedValue: l = [2, 2]
  } = e;
  n.lineWidth = r, n.strokeStyle = a, i === Q.Dashed ? n.setLineDash(l) : n.setLineDash([]);
  const c = r % 2 === 1 ? 0.5 : 0;
  s.forEach(({ coordinates: h }) => {
    h.length > 1 && (h.length === 2 && (h[0].x === h[1].x || h[0].y === h[1].y) ? (n.beginPath(), h[0].x === h[1].x ? (n.moveTo(h[0].x + c, h[0].y), n.lineTo(h[1].x + c, h[1].y)) : (n.moveTo(h[0].x, h[0].y + c), n.lineTo(h[1].x, h[1].y + c)), n.stroke(), n.closePath()) : (n.save(), r % 2 === 1 && n.translate(0.5, 0.5), n.beginPath(), n.moveTo(h[0].x, h[0].y), ie(n, h, o), n.stroke(), n.closePath(), n.restore()));
  });
}
const Hi = {
  name: "line",
  checkEventOn: hs,
  draw: (n, t, e) => {
    us(n, t, e);
  }
};
function ds(n, t, e) {
  const s = e ?? 0, i = [];
  if (n.length > 1)
    if (n[0].x === n[1].x) {
      const r = t.height;
      if (i.push({
        coordinates: [
          { x: n[0].x, y: 0 },
          { x: n[0].x, y: r }
        ]
      }), n.length > 2) {
        i.push({
          coordinates: [
            { x: n[2].x, y: 0 },
            { x: n[2].x, y: r }
          ]
        });
        const a = n[0].x - n[2].x;
        for (let l = 0; l < s; l++) {
          const c = a * (l + 1);
          i.push({
            coordinates: [
              { x: n[0].x + c, y: 0 },
              { x: n[0].x + c, y: r }
            ]
          });
        }
      }
    } else {
      const r = t.width, a = de(n[0], n[1]), l = a[0], c = a[1];
      if (i.push({
        coordinates: [
          { x: 0, y: 0 * l + c },
          { x: r, y: r * l + c }
        ]
      }), n.length > 2) {
        const h = n[2].y - l * n[2].x;
        i.push({
          coordinates: [
            { x: 0, y: 0 * l + h },
            { x: r, y: r * l + h }
          ]
        });
        const u = c - h;
        for (let d = 0; d < s; d++) {
          const g = c + u * (d + 1);
          i.push({
            coordinates: [
              { x: 0, y: 0 * l + g },
              { x: r, y: r * l + g }
            ]
          });
        }
      }
    }
  return i;
}
const $i = {
  name: "parallelStraightLine",
  totalStep: 4,
  needDefaultPointFigure: !0,
  needDefaultXAxisFigure: !0,
  needDefaultYAxisFigure: !0,
  createPointFigures: ({ coordinates: n, bounding: t }) => [
    {
      type: "line",
      attrs: ds(n, t)
    }
  ]
}, Gi = {
  name: "priceChannelLine",
  totalStep: 4,
  needDefaultPointFigure: !0,
  needDefaultXAxisFigure: !0,
  needDefaultYAxisFigure: !0,
  createPointFigures: ({ coordinates: n, bounding: t }) => [
    {
      type: "line",
      attrs: ds(n, t, 1)
    }
  ]
}, ji = {
  name: "priceLine",
  totalStep: 2,
  needDefaultPointFigure: !0,
  needDefaultXAxisFigure: !0,
  needDefaultYAxisFigure: !0,
  createPointFigures: ({
    coordinates: n,
    bounding: t,
    precision: e,
    overlay: s,
    thousandsSeparator: i,
    decimalFoldThreshold: o,
    yAxis: r
  }) => {
    const { value: a = 0 } = s.points[0], l = r?.isInCandle() ?? !0 ? e.price : e.excludePriceVolumeMax;
    return [
      {
        type: "line",
        attrs: {
          coordinates: [
            n[0],
            { x: t.width, y: n[0].y }
          ]
        }
      },
      {
        type: "text",
        ignoreEvent: !0,
        attrs: {
          x: n[0].x,
          y: n[0].y,
          text: z(
            W(
              a.toFixed(l),
              i
            ),
            o
          ),
          baseline: "bottom"
        }
      }
    ];
  }
};
function Ui(n, t) {
  if (n.length > 1) {
    let e;
    return n[0].x === n[1].x && n[0].y !== n[1].y ? n[0].y < n[1].y ? e = {
      x: n[0].x,
      y: t.height
    } : e = {
      x: n[0].x,
      y: 0
    } : n[0].x > n[1].x ? e = {
      x: 0,
      y: Ut(n[0], n[1], {
        x: 0,
        y: n[0].y
      })
    } : e = {
      x: t.width,
      y: Ut(n[0], n[1], {
        x: t.width,
        y: n[0].y
      })
    }, { coordinates: [n[0], e] };
  }
  return [];
}
const Zi = {
  name: "rayLine",
  totalStep: 3,
  needDefaultPointFigure: !0,
  needDefaultXAxisFigure: !0,
  needDefaultYAxisFigure: !0,
  createPointFigures: ({ coordinates: n, bounding: t }) => [
    {
      type: "line",
      attrs: Ui(n, t)
    }
  ]
}, Ki = {
  name: "segment",
  totalStep: 3,
  needDefaultPointFigure: !0,
  needDefaultXAxisFigure: !0,
  needDefaultYAxisFigure: !0,
  createPointFigures: ({ coordinates: n }) => n.length === 2 ? [
    {
      type: "line",
      attrs: { coordinates: n }
    }
  ] : []
}, qi = {
  name: "straightLine",
  totalStep: 3,
  needDefaultPointFigure: !0,
  needDefaultXAxisFigure: !0,
  needDefaultYAxisFigure: !0,
  createPointFigures: ({ coordinates: n, bounding: t }) => n.length === 2 ? n[0].x === n[1].x ? [
    {
      type: "line",
      attrs: {
        coordinates: [
          {
            x: n[0].x,
            y: 0
          },
          {
            x: n[0].x,
            y: t.height
          }
        ]
      }
    }
  ] : [
    {
      type: "line",
      attrs: {
        coordinates: [
          {
            x: 0,
            y: Ut(n[0], n[1], {
              x: 0,
              y: n[0].y
            })
          },
          {
            x: t.width,
            y: Ut(n[0], n[1], {
              x: t.width,
              y: n[0].y
            })
          }
        ]
      }
    }
  ] : []
}, Ji = {
  name: "verticalRayLine",
  totalStep: 3,
  needDefaultPointFigure: !0,
  needDefaultXAxisFigure: !0,
  needDefaultYAxisFigure: !0,
  createPointFigures: ({ coordinates: n, bounding: t }) => {
    if (n.length === 2) {
      const e = { x: n[0].x, y: 0 };
      return n[0].y < n[1].y && (e.y = t.height), [
        {
          type: "line",
          attrs: { coordinates: [n[0], e] }
        }
      ];
    }
    return [];
  },
  performEventPressedMove: ({ points: n, performPoint: t }) => {
    n[0].timestamp = t.timestamp, n[0].dataIndex = t.dataIndex, n[1].timestamp = t.timestamp, n[1].dataIndex = t.dataIndex;
  },
  performEventMoveForDrawing: ({ currentStep: n, points: t, performPoint: e }) => {
    n === 2 && (t[0].timestamp = e.timestamp, t[0].dataIndex = e.dataIndex);
  }
}, Qi = {
  name: "verticalSegment",
  totalStep: 3,
  needDefaultPointFigure: !0,
  needDefaultXAxisFigure: !0,
  needDefaultYAxisFigure: !0,
  createPointFigures: ({ coordinates: n }) => n.length === 2 ? [
    {
      type: "line",
      attrs: { coordinates: n }
    }
  ] : [],
  performEventPressedMove: ({ points: n, performPoint: t }) => {
    n[0].timestamp = t.timestamp, n[0].dataIndex = t.dataIndex, n[1].timestamp = t.timestamp, n[1].dataIndex = t.dataIndex;
  },
  performEventMoveForDrawing: ({ currentStep: n, points: t, performPoint: e }) => {
    n === 2 && (t[0].timestamp = e.timestamp, t[0].dataIndex = e.dataIndex);
  }
}, tn = {
  name: "verticalStraightLine",
  totalStep: 2,
  needDefaultPointFigure: !0,
  needDefaultXAxisFigure: !0,
  needDefaultYAxisFigure: !0,
  createPointFigures: ({ coordinates: n, bounding: t }) => [
    {
      type: "line",
      attrs: {
        coordinates: [
          {
            x: n[0].x,
            y: 0
          },
          {
            x: n[0].x,
            y: t.height
          }
        ]
      }
    }
  ]
}, en = {
  name: "simpleAnnotation",
  totalStep: 2,
  styles: {
    line: { style: Q.Dashed }
  },
  createPointFigures: ({ overlay: n, coordinates: t }) => {
    let e;
    C(n.extendData) && (lt(n.extendData) ? e = n.extendData(n) : e = n.extendData ?? "");
    const s = t[0].x, i = t[0].y - 6, o = i - 50, r = o - 5;
    return [
      {
        type: "line",
        attrs: {
          coordinates: [
            { x: s, y: i },
            { x: s, y: o }
          ]
        },
        ignoreEvent: !0
      },
      {
        type: "polygon",
        attrs: {
          coordinates: [
            { x: s, y: o },
            { x: s - 4, y: r },
            { x: s + 4, y: r }
          ]
        },
        ignoreEvent: !0
      },
      {
        type: "text",
        attrs: {
          x: s,
          y: r,
          text: e ?? "",
          align: "center",
          baseline: "bottom"
        },
        ignoreEvent: !0
      }
    ];
  }
}, sn = {
  name: "simpleTag",
  totalStep: 2,
  styles: {
    line: { style: Q.Dashed }
  },
  createPointFigures: ({ bounding: n, coordinates: t }) => ({
    type: "line",
    attrs: {
      coordinates: [
        { x: 0, y: t[0].y },
        { x: n.width, y: t[0].y }
      ]
    },
    ignoreEvent: !0
  }),
  createYAxisFigures: ({
    overlay: n,
    coordinates: t,
    bounding: e,
    yAxis: s,
    precision: i
  }) => {
    const o = s?.isFromZero() ?? !1;
    let r, a;
    o ? (r = "left", a = 0) : (r = "right", a = e.width);
    let l;
    return C(n.extendData) && (lt(n.extendData) ? l = n.extendData(n) : l = n.extendData ?? ""), !C(l) && E(n.points[0].value) && (l = N(n.points[0].value, i.price)), {
      type: "text",
      attrs: {
        x: a,
        y: t[0].y,
        text: l ?? "",
        align: r,
        baseline: "middle"
      }
    };
  }
}, Zt = {}, nn = [
  Wi,
  zi,
  Xi,
  Yi,
  $i,
  Gi,
  ji,
  Zi,
  Ki,
  qi,
  Ji,
  Qi,
  tn,
  en,
  sn
];
nn.forEach((n) => {
  Zt[n.name] = ce.extend(n);
});
function co(n) {
  Zt[n.name] = ce.extend(n);
}
function on(n) {
  return Zt[n] ?? null;
}
function ho(n) {
  return Zt[n] ?? null;
}
function uo() {
  return Object.keys(Zt);
}
var kt = /* @__PURE__ */ ((n) => (n.Top = "top", n.Bottom = "bottom", n))(kt || {});
const rn = 30, an = 100, L = {
  CANDLE: "candle_pane",
  INDICATOR: "indicator_pane_",
  X_AXIS: "x_axis_pane"
};
var K = /* @__PURE__ */ ((n) => (n[n.None = 0] = "None", n[n.Point = 1] = "Point", n[n.Other = 2] = "Other", n))(K || {});
class ln {
  constructor(t) {
    this._instances = /* @__PURE__ */ new Map(), this._progressInstanceInfo = null, this._pressedInstanceInfo = {
      paneId: "",
      instance: null,
      figureType: 0,
      figureKey: "",
      figureIndex: -1,
      attrsIndex: -1
    }, this._hoverInstanceInfo = {
      paneId: "",
      instance: null,
      figureType: 0,
      figureKey: "",
      figureIndex: -1,
      attrsIndex: -1
    }, this._clickInstanceInfo = {
      paneId: "",
      instance: null,
      figureType: 0,
      figureKey: "",
      figureIndex: -1,
      attrsIndex: -1
    }, this._chartStore = t;
  }
  getInstanceById(t) {
    for (const e of this._instances) {
      const i = e[1].find((o) => o.getOverlay().id === t);
      if (C(i))
        return i;
    }
    return this._progressInstanceInfo !== null && this._progressInstanceInfo.instance.getOverlay().id === t ? this._progressInstanceInfo.instance : null;
  }
  _sort(t) {
    D(t) ? this._instances.get(t)?.sort((e, s) => e.getOverlay().zLevel - s.getOverlay().zLevel) : this._instances.forEach((e) => {
      e.sort(
        (s, i) => s.getOverlay().zLevel - i.getOverlay().zLevel
      );
    });
  }
  addInstances(t, e, s) {
    const i = t.map((o) => {
      const r = o.id ?? ls(ei);
      if (this.getInstanceById(r) === null) {
        const a = on(o.name);
        if (a !== null) {
          const l = new a();
          l.override({ paneId: e });
          const c = o.groupId ?? r;
          if (o.id = r, o.paneId = e, o.groupId = c, l.override(o), l.isDrawing() ? this._progressInstanceInfo = { paneId: e, instance: l, appointPaneFlag: s } : (this._instances.has(e) || this._instances.set(e, []), this._instances.get(e)?.push(l)), l.isStart()) {
            const h = l.getOverlay();
            h.onDrawStart?.({ overlay: h });
          }
          return r;
        }
      }
      return null;
    });
    if (i.some((o) => o !== null)) {
      this._sort();
      const o = this._chartStore.getChart();
      o.updatePane(F.Overlay, e), o.updatePane(F.Overlay, L.X_AXIS);
    }
    return i;
  }
  getProgressInstanceInfo() {
    return this._progressInstanceInfo;
  }
  progressInstanceComplete() {
    if (this._progressInstanceInfo !== null) {
      const { instance: t, paneId: e } = this._progressInstanceInfo;
      t.isDrawing() || (this._instances.has(e) || this._instances.set(e, []), this._instances.get(e)?.push(t), this._sort(e), this._progressInstanceInfo = null);
    }
  }
  updateProgressInstanceInfo(t, e) {
    this._progressInstanceInfo !== null && (ae(e) && e && (this._progressInstanceInfo.appointPaneFlag = e), this._progressInstanceInfo.paneId = t, this._progressInstanceInfo.instance.override({ paneId: t }));
  }
  getInstances(t) {
    if (!D(t)) {
      let e = [];
      return this._instances.forEach((s) => {
        e = e.concat(s);
      }), e;
    }
    return this._instances.get(t) ?? [];
  }
  override(t) {
    const { id: e, groupId: s, name: i } = t;
    let o = !1, r = !1;
    const a = (l) => {
      l.override(t);
      const { sort: c, draw: h } = l.shouldUpdate();
      h && (o = !0), c && (r = !0);
    };
    if (D(e)) {
      const l = this.getInstanceById(e);
      l !== null && a(l);
    } else {
      const l = D(i), c = D(s);
      if (this._instances.forEach((h) => {
        h.forEach((u) => {
          const d = u.getOverlay();
          (l && d.name === i || c && d.groupId === s || !l && !c) && a(u);
        });
      }), this._progressInstanceInfo !== null) {
        const h = this._progressInstanceInfo.instance, u = h.getOverlay();
        (l && u.name === i || c && u.groupId === s || !l && !c) && a(h);
      }
    }
    r && this._sort(), o && this._chartStore.getChart().updatePane(F.Overlay);
  }
  removeInstance(t) {
    const e = (o, r) => {
      const a = r.getOverlay();
      if (D(o.id)) {
        if (a.id !== o.id)
          return !1;
      } else if (D(o.groupId)) {
        if (a.groupId !== o.groupId)
          return !1;
      } else if (D(o.name) && a.name !== o.name)
        return !1;
      return !0;
    }, s = [], i = C(t);
    if (this._progressInstanceInfo !== null) {
      const { instance: o } = this._progressInstanceInfo;
      if (!i || i && e(t, o)) {
        s.push(this._progressInstanceInfo.paneId);
        const r = o.getOverlay();
        r.onRemoved?.({ overlay: r }), this._progressInstanceInfo = null;
      }
    }
    if (i) {
      const o = /* @__PURE__ */ new Map();
      for (const r of this._instances) {
        const l = r[1].filter((c) => {
          if (e(t, c)) {
            s.includes(r[0]) || s.push(r[0]);
            const h = c.getOverlay();
            return h.onRemoved?.({ overlay: h }), !1;
          }
          return !0;
        });
        l.length > 0 && o.set(r[0], l);
      }
      this._instances = o;
    } else
      this._instances.forEach((o, r) => {
        s.push(r), o.forEach((a) => {
          const l = a.getOverlay();
          l.onRemoved?.({ overlay: l });
        });
      }), this._instances.clear();
    if (s.length > 0) {
      const o = this._chartStore.getChart();
      s.forEach((r) => {
        o.updatePane(F.Overlay, r);
      }), o.updatePane(F.Overlay, L.X_AXIS);
    }
  }
  setPressedInstanceInfo(t) {
    this._pressedInstanceInfo = t;
  }
  getPressedInstanceInfo() {
    return this._pressedInstanceInfo;
  }
  updatePointPosition(t, e) {
    if (t > 0) {
      const s = this._chartStore.getDataList();
      this._instances.forEach((i) => {
        i.forEach((o) => {
          o.getOverlay().points.forEach((l) => {
            if (!C(l.timestamp) && C(l.dataIndex)) {
              e === ot.Forward && (l.dataIndex = l.dataIndex + t);
              const c = s[l.dataIndex];
              l.timestamp = c?.timestamp;
            }
          });
        });
      });
    }
  }
  setHoverInstanceInfo(t, e) {
    const { instance: s, figureType: i, figureKey: o, figureIndex: r } = this._hoverInstanceInfo, a = s?.getOverlay(), l = t.instance?.getOverlay();
    if ((a?.id !== l?.id || i !== t.figureType || r !== t.figureIndex) && (this._hoverInstanceInfo = t, a?.id !== l?.id)) {
      let c = !1, h = !1;
      s !== null && (h = !0, lt(a?.onMouseLeave) && (a?.onMouseLeave({
        overlay: a,
        figureKey: o,
        figureIndex: r,
        ...e
      }), c = !0)), l !== null && (h = !0, lt(l?.onMouseEnter) && (l?.onMouseEnter({
        overlay: l,
        figureKey: t.figureKey,
        figureIndex: t.figureIndex,
        ...e
      }), c = !0)), h && this._sort(), c || this._chartStore.getChart().updatePane(F.Overlay);
    }
  }
  getHoverInstanceInfo() {
    return this._hoverInstanceInfo;
  }
  setClickInstanceInfo(t, e) {
    const { paneId: s, instance: i, figureType: o, figureKey: r, figureIndex: a } = this._clickInstanceInfo, l = i?.getOverlay(), c = t.instance?.getOverlay();
    if ((t.instance?.isDrawing() ?? !1) || c?.onClick?.({
      overlay: c,
      figureKey: t.figureKey,
      figureIndex: t.figureIndex,
      ...e
    }), (l?.id !== c?.id || o !== t.figureType || a !== t.figureIndex) && (this._clickInstanceInfo = t, l?.id !== c?.id)) {
      l?.onDeselected?.({ overlay: l, figureKey: r, figureIndex: a, ...e }), c?.onSelected?.({
        overlay: c,
        figureKey: t.figureKey,
        figureIndex: t.figureIndex,
        ...e
      });
      const h = this._chartStore.getChart();
      h.updatePane(F.Overlay, t.paneId), s !== t.paneId && h.updatePane(F.Overlay, s), h.updatePane(F.Overlay, L.X_AXIS);
    }
  }
  getClickInstanceInfo() {
    return this._clickInstanceInfo;
  }
  isEmpty() {
    return this._instances.size === 0 && this._progressInstanceInfo === null;
  }
  isDrawing() {
    return this._progressInstanceInfo !== null && (this._progressInstanceInfo?.instance.isDrawing() ?? !1);
  }
}
class cn {
  constructor() {
    this._actions = /* @__PURE__ */ new Map();
  }
  execute(t, e) {
    this._actions.get(t)?.execute(e);
  }
  subscribe(t, e) {
    this._actions.has(t) || this._actions.set(t, new Qs()), this._actions.get(t)?.subscribe(e);
  }
  /**
   * 取消事件订阅
   * @param type
   * @param callback
   * @return {boolean}
   */
  unsubscribe(t, e) {
    const s = this._actions.get(t);
    C(s) && (s.unsubscribe(e), s.isEmpty() && this._actions.delete(t));
  }
  has(t) {
    const e = this._actions.get(t);
    return C(e) && !e.isEmpty();
  }
}
const hn = {
  grid: {
    horizontal: {
      color: "#EDEDED"
    },
    vertical: {
      color: "#EDEDED"
    }
  },
  candle: {
    priceMark: {
      high: {
        color: "#76808F"
      },
      low: {
        color: "#76808F"
      }
    },
    tooltip: {
      rect: {
        color: "#FEFEFE",
        borderColor: "#F2F3F5"
      },
      text: {
        color: "#76808F"
      }
    }
  },
  indicator: {
    tooltip: {
      text: {
        color: "#76808F"
      }
    }
  },
  xAxis: {
    axisLine: {
      color: "#DDDDDD"
    },
    tickText: {
      color: "#76808F"
    },
    tictView: {
      color: "#DDDDDD"
    }
  },
  yAxis: {
    axisLine: {
      color: "#DDDDDD"
    },
    tickText: {
      color: "#76808F"
    },
    tictView: {
      color: "#DDDDDD"
    }
  },
  separator: {
    color: "#DDDDDD"
  },
  crosshair: {
    horizontal: {
      line: {
        color: "#76808F"
      },
      text: {
        borderColor: "#686D76",
        backgroundColor: "#686D76"
      }
    },
    vertical: {
      line: {
        color: "#76808F"
      },
      text: {
        borderColor: "#686D76",
        backgroundColor: "#686D76"
      }
    }
  }
}, un = {
  grid: {
    horizontal: {
      color: "#1F1F1F69"
    },
    vertical: {
      color: "#1F1F1F69"
    }
  },
  candle: {
    priceMark: {
      high: {
        color: "#929AA5"
      },
      low: {
        color: "#929AA5"
      }
    },
    tooltip: {
      rect: {
        color: "rgba(10, 10, 10, .6)",
        borderColor: "rgba(10, 10, 10, .6)"
      },
      text: {
        color: "#929AA5"
      }
    }
  },
  indicator: {
    tooltip: {
      text: {
        color: "#929AA5"
      }
    }
  },
  xAxis: {
    axisLine: {
      color: "#333333"
    },
    tickText: {
      color: "#929AA5"
    },
    tictView: {
      color: "#333333"
    }
  },
  yAxis: {
    axisLine: {
      color: "#333333"
    },
    tickText: {
      color: "#929AA5"
    },
    tictView: {
      color: "#333333"
    }
  },
  separator: {
    color: "#333333"
  },
  crosshair: {
    horizontal: {
      line: {
        color: "#929AA5"
      },
      text: {
        borderColor: "#373a40",
        backgroundColor: "#373a40"
      }
    },
    vertical: {
      line: {
        color: "#929AA5"
      },
      text: {
        borderColor: "#373a40",
        backgroundColor: "#373a40"
      }
    }
  }
}, gs = {
  light: hn,
  dark: un
};
function go(n, t) {
  gs[n] = t;
}
function fs(n) {
  return gs[n] ?? null;
}
class dn {
  constructor(t, e) {
    this._styles = Zs(), this._customApi = si(), this._locale = ii, this._precision = { price: 2, volume: 0 }, this._thousandsSeparator = ",", this._decimalFoldThreshold = 3, this._dataList = [], this._loadMoreCallback = null, this._loadDataCallback = null, this._loading = !0, this._forwardMore = !0, this._backwardMore = !0, this._yScrolling = !0, this._timeScaleStore = new ai(this), this._indicatorStore = new Vi(this), this._overlayStore = new ln(this), this._tooltipStore = new Ni(this), this._actionStore = new cn(), this._visibleDataList = [], this._chart = t, this.setOptions(e);
  }
  /**
   * @description Adjust visible data
   * @return {*}
   */
  adjustVisibleDataList() {
    this._visibleDataList = [];
    const { realFrom: t, realTo: e } = this._timeScaleStore.getVisibleRange();
    for (let s = t; s < e; s++) {
      const i = this._dataList[s], o = this._timeScaleStore.dataIndexToCoordinate(s);
      this._visibleDataList.push({
        dataIndex: s,
        x: o,
        data: i
      });
    }
  }
  setOptions(t) {
    if (C(t)) {
      const {
        locale: e,
        yScrolling: s,
        timezone: i,
        styles: o,
        customApi: r,
        thousandsSeparator: a,
        decimalFoldThreshold: l
      } = t;
      if (D(e) && (this._locale = e), D(i) && this._timeScaleStore.setTimezone(i), s !== void 0 && (this._yScrolling = s), C(o)) {
        let c = null;
        D(o) ? c = fs(o) : c = o, tt(this._styles, c), rt(c?.candle?.tooltip?.custom) && (this._styles.candle.tooltip.custom = c?.candle?.tooltip?.custom);
      }
      C(r) && tt(this._customApi, r), D(a) && (this._thousandsSeparator = a), E(l) && l > 0 && (this._decimalFoldThreshold = l);
    }
    return this;
  }
  getStyles() {
    return this._styles;
  }
  getLocale() {
    return this._locale;
  }
  getCustomApi() {
    return this._customApi;
  }
  getThousandsSeparator() {
    return this._thousandsSeparator;
  }
  getDecimalFoldThreshold() {
    return this._decimalFoldThreshold;
  }
  getPrecision() {
    return this._precision;
  }
  setPrecision(t) {
    return this._precision = t, this._indicatorStore.synchronizeSeriesPrecision(), this;
  }
  getDataList() {
    return this._dataList;
  }
  getVisibleFirstData() {
    const { from: t } = this._timeScaleStore.getVisibleRange();
    return this._dataList[t] ?? null;
  }
  getVisibleLastData() {
    const { to: t } = this._timeScaleStore.getVisibleRange();
    return this._dataList[t] ?? null;
  }
  getVisibleDataList() {
    return this._visibleDataList;
  }
  getYScrolling() {
    return this._yScrolling;
  }
  async addData(t, e, s) {
    let i = !1, o = !1, r = 0;
    if (rt(t)) {
      switch (r = t.length, e) {
        case ot.Init: {
          this.clear(), this._dataList = t, this._forwardMore = s ?? !0, this._timeScaleStore.resetOffsetRightDistance(), o = !0;
          break;
        }
        case ot.Backward: {
          this._dataList = this._dataList.concat(t), this._backwardMore = s ?? !1, o = r > 0;
          break;
        }
        case ot.Forward:
          this._dataList = t.concat(this._dataList), this._forwardMore = s ?? !1, o = r > 0;
      }
      this._loading = !1, i = !0;
    } else {
      const a = this._dataList.length, l = t.timestamp, c = H(
        this._dataList[a - 1],
        "timestamp",
        0
      );
      if (l > c) {
        this._dataList.push(t);
        let h = this._timeScaleStore.getLastBarRightSideDiffBarCount();
        h < 0 && this._timeScaleStore.setLastBarRightSideDiffBarCount(
          --h
        ), r = 1, i = !0, o = !0;
      } else l === c && (this._dataList[a - 1] = t, i = !0, o = !0);
    }
    if (i)
      try {
        this._overlayStore.updatePointPosition(r, e), o && (this._timeScaleStore.adjustVisibleRange(), this._tooltipStore.recalculateCrosshair(!0), await this._indicatorStore.calcInstance(), this._chart.adjustPaneViewport(!1, !0, !0, !0)), this._actionStore.execute(et.OnDataReady);
      } catch {
      }
  }
  setLoadMoreCallback(t) {
    this._loadMoreCallback = t;
  }
  executeLoadMoreCallback(t) {
    this._forwardMore && !this._loading && C(this._loadMoreCallback) && (this._loading = !0, this._loadMoreCallback(t));
  }
  setLoadDataCallback(t) {
    this._loadDataCallback = t;
  }
  executeLoadDataCallback(t) {
    if (!this._loading && C(this._loadDataCallback) && (this._forwardMore && t.type === ot.Forward || this._backwardMore && t.type === ot.Backward)) {
      const e = (s, i) => {
        this.addData(s, t.type, i).then(() => {
        }).catch(() => {
        });
      };
      this._loading = !0, this._loadDataCallback({ ...t, callback: e });
    }
  }
  clear() {
    this._forwardMore = !0, this._backwardMore = !0, this._loading = !0, this._dataList = [], this._visibleDataList = [], this._timeScaleStore.clear(), this._tooltipStore.clear();
  }
  getTimeScaleStore() {
    return this._timeScaleStore;
  }
  getIndicatorStore() {
    return this._indicatorStore;
  }
  getOverlayStore() {
    return this._overlayStore;
  }
  getTooltipStore() {
    return this._tooltipStore;
  }
  getActionStore() {
    return this._actionStore;
  }
  getChart() {
    return this._chart;
  }
}
const k = {
  MAIN: "main",
  X_AXIS: "xAxis",
  Y_AXIS: "yAxis",
  SEPARATOR: "separator"
}, $t = 7;
async function gn() {
  return await new Promise((n) => {
    const t = new ResizeObserver((e) => {
      n(e.every((s) => "devicePixelContentBoxSize" in s)), t.disconnect();
    });
    t.observe(document.body, { box: "device-pixel-content-box" });
  }).catch(() => !1);
}
class es {
  constructor(t, e) {
    this._supportedDevicePixelContentBox = !1, this._width = 0, this._height = 0, this._pixelWidth = 0, this._pixelHeight = 0, this._nextPixelWidth = 0, this._nextPixelHeight = 0, this._requestAnimationId = ve, this._mediaQueryListener = () => {
      const s = yt(this._element);
      this._nextPixelWidth = Math.round(this._element.clientWidth * s), this._nextPixelHeight = Math.round(this._element.clientHeight * s), this._resetPixelRatio();
    }, this._listener = e, this._element = ft("canvas", t), this._ctx = this._element.getContext("2d", { willReadFrequently: !0 }), gn().then((s) => {
      this._supportedDevicePixelContentBox = s, s ? (this._resizeObserver = new ResizeObserver(
        (i) => {
          const r = i.find(
            (a) => a.target === this._element
          )?.devicePixelContentBoxSize?.[0];
          C(r) && (this._nextPixelWidth = r.inlineSize, this._nextPixelHeight = r.blockSize, (this._pixelWidth !== this._nextPixelWidth || this._pixelHeight !== this._nextPixelHeight) && this._resetPixelRatio());
        }
      ), this._resizeObserver.observe(this._element, {
        box: "device-pixel-content-box"
      })) : (this._mediaQueryList = window.matchMedia(
        `(resolution: ${yt(this._element)}dppx)`
      ), this._mediaQueryList.addListener(this._mediaQueryListener));
    }).catch((s) => !1);
  }
  _resetPixelRatio() {
    this._executeListener(() => {
      const t = this._element.clientWidth, e = this._element.clientHeight, s = this._nextPixelWidth / t, i = this._nextPixelHeight / e;
      this._width = t, this._height = e, this._pixelWidth = this._nextPixelWidth, this._pixelHeight = this._nextPixelHeight, this._element.width = this._nextPixelWidth, this._element.height = this._nextPixelHeight, this._ctx.scale(s, i);
    });
  }
  _executeListener(t) {
    this._requestAnimationId === ve && (this._requestAnimationId = ne(() => {
      this._ctx.clearRect(0, 0, this._width, this._height), t?.(), this._listener(), this._requestAnimationId = ve;
    }));
  }
  update(t, e) {
    if (this._width !== t || this._height !== e) {
      if (this._element.style.width = `${t}px`, this._element.style.height = `${e}px`, !this._supportedDevicePixelContentBox) {
        const s = yt(this._element);
        this._nextPixelWidth = Math.round(t * s), this._nextPixelHeight = Math.round(e * s), this._resetPixelRatio();
      }
    } else
      this._executeListener();
  }
  getElement() {
    return this._element;
  }
  getContext() {
    return this._ctx;
  }
  destroy() {
    this._resizeObserver?.unobserve(this._element), this._mediaQueryList?.removeListener(this._mediaQueryListener);
  }
}
function ms(n) {
  const t = {
    width: 0,
    height: 0,
    left: 0,
    right: 0,
    top: 0,
    bottom: 0
  };
  return C(n) && tt(t, n), t;
}
class ps extends ke {
  constructor(t, e) {
    super(), this._bounding = ms(), this._pane = e, this.init(t);
  }
  init(t) {
    this._rootContainer = t, this._container = this.createContainer(), t.appendChild(this._container);
  }
  setBounding(t) {
    return tt(this._bounding, t), this;
  }
  getContainer() {
    return this._container;
  }
  getBounding() {
    return this._bounding;
  }
  getPane() {
    return this._pane;
  }
  update(t) {
    this.updateImp(
      this._container,
      this._bounding,
      t ?? F.Drawer
    );
  }
  destroy() {
    this._rootContainer.removeChild(this._container);
  }
}
class Le extends ps {
  init(t) {
    super.init(t), this._mainCanvas = new es(
      {
        position: "absolute",
        top: "0",
        left: "0",
        zIndex: "2",
        boxSizing: "border-box"
      },
      () => {
        this.updateMain(this._mainCanvas.getContext());
      }
    ), this._overlayCanvas = new es(
      {
        position: "absolute",
        top: "0",
        left: "0",
        zIndex: "2",
        boxSizing: "border-box"
      },
      () => {
        this.updateOverlay(this._overlayCanvas.getContext());
      }
    );
    const e = this.getContainer();
    e.appendChild(this._mainCanvas.getElement()), e.appendChild(this._overlayCanvas.getElement());
  }
  createContainer() {
    return ft("div", {
      margin: "0",
      padding: "0",
      position: "absolute",
      top: "0",
      overflow: "hidden",
      boxSizing: "border-box",
      zIndex: "1"
    });
  }
  updateImp(t, e, s) {
    const { width: i, height: o, left: r } = e;
    t.style.left = `${r}px`;
    let a = s;
    const l = t.clientWidth, c = t.clientHeight;
    switch ((i !== l || o !== c) && (t.style.width = `${i}px`, t.style.height = `${o}px`, a = F.Drawer), a) {
      case F.Main: {
        this._mainCanvas.update(i, o);
        break;
      }
      case F.Overlay: {
        this._overlayCanvas.update(i, o);
        break;
      }
      case F.Drawer:
      case F.All: {
        this._mainCanvas.update(i, o), this._overlayCanvas.update(i, o);
        break;
      }
    }
  }
  destroy() {
    this._mainCanvas.destroy(), this._overlayCanvas.destroy();
  }
  getImage(t) {
    const { width: e, height: s } = this.getBounding(), i = ft("canvas", {
      width: `${e}px`,
      height: `${s}px`,
      boxSizing: "border-box"
    }), o = i.getContext("2d"), r = yt(i);
    return i.width = e * r, i.height = s * r, o.scale(r, r), o.drawImage(this._mainCanvas.getElement(), 0, 0, e, s), t && o.drawImage(this._overlayCanvas.getElement(), 0, 0, e, s), i;
  }
}
function Bt(n) {
  return n === "transparent" || n === "none" || /^[rR][gG][Bb][Aa]\(([\s]*(2[0-4][0-9]|25[0-5]|[01]?[0-9][0-9]?)[\s]*,){3}[\s]*0[\s]*\)$/.test(
    n
  ) || /^[hH][Ss][Ll][Aa]\(([\s]*(360｜3[0-5][0-9]|[012]?[0-9][0-9]?)[\s]*,)([\s]*((100|[0-9][0-9]?)%|0)[\s]*,){2}([\s]*0[\s]*)\)$/.test(
    n
  );
}
function _s(n, t) {
  let e = [];
  e = e.concat(t);
  for (let s = 0; s < e.length; s++) {
    const { x: i, y: o, r } = e[s], a = n.x - i, l = n.y - o;
    if (!(a * a + l * l > r * r))
      return !0;
  }
  return !1;
}
function xs(n, t, e) {
  let s = [];
  s = s.concat(t);
  const {
    style: i = V.Fill,
    color: o = "currentColor",
    borderSize: r = 1,
    borderColor: a = "currentColor",
    borderStyle: l = Q.Solid,
    borderDashedValue: c = [2, 2]
  } = e, h = (i === V.Fill || e.style === V.StrokeFill) && (!D(o) || !Bt(o));
  h && (n.fillStyle = o, s.forEach(({ x: u, y: d, r: g }) => {
    n.beginPath(), n.arc(u, d, g, 0, Math.PI * 2), n.closePath(), n.fill();
  })), (i === V.Stroke || e.style === V.StrokeFill) && r > 0 && !Bt(a) && (n.strokeStyle = a, n.lineWidth = r, l === Q.Dashed ? n.setLineDash(c) : n.setLineDash([]), s.forEach(({ x: u, y: d, r: g }) => {
    (!h || g > r) && (n.beginPath(), n.arc(u, d, g, 0, Math.PI * 2), n.closePath(), n.stroke());
  }));
}
const fn = {
  name: "circle",
  checkEventOn: _s,
  draw: (n, t, e) => {
    xs(n, t, e);
  }
};
function ys(n, t) {
  let e = [];
  e = e.concat(t);
  for (let s = 0; s < e.length; s++) {
    let i = !1;
    const { coordinates: o } = e[s];
    for (let r = 0, a = o.length - 1; r < o.length; a = r++)
      o[r].y > n.y != o[a].y > n.y && n.x < (o[a].x - o[r].x) * (n.y - o[r].y) / (o[a].y - o[r].y) + o[r].x && (i = !i);
    if (i)
      return !0;
  }
  return !1;
}
function vs(n, t, e) {
  let s = [];
  s = s.concat(t);
  const {
    style: i = V.Fill,
    color: o = "currentColor",
    borderSize: r = 1,
    borderColor: a = "currentColor",
    borderStyle: l = Q.Solid,
    borderDashedValue: c = [2, 2]
  } = e;
  (i === V.Fill || e.style === V.StrokeFill) && (!D(o) || !Bt(o)) && (n.fillStyle = o, s.forEach(({ coordinates: h }) => {
    n.beginPath(), n.moveTo(h[0].x, h[0].y);
    for (let u = 1; u < h.length; u++)
      n.lineTo(h[u].x, h[u].y);
    n.closePath(), n.fill();
  })), (i === V.Stroke || e.style === V.StrokeFill) && r > 0 && !Bt(a) && (n.strokeStyle = a, n.lineWidth = r, l === Q.Dashed ? n.setLineDash(c) : n.setLineDash([]), s.forEach(({ coordinates: h }) => {
    n.beginPath(), n.moveTo(h[0].x, h[0].y);
    for (let u = 1; u < h.length; u++)
      n.lineTo(h[u].x, h[u].y);
    n.closePath(), n.stroke();
  }));
}
const mn = {
  name: "polygon",
  checkEventOn: ys,
  draw: (n, t, e) => {
    vs(n, t, e);
  }
};
function Ss(n, t) {
  let e = [];
  e = e.concat(t);
  for (let s = 0; s < e.length; s++) {
    const i = e[s];
    let o = i.x, r = i.width;
    r < Y * 2 && (o -= Y, r = Y * 2);
    let a = i.y, l = i.height;
    if (l < Y * 2 && (a -= Y, l = Y * 2), n.x >= o && n.x <= o + r && n.y >= a && n.y <= a + l)
      return !0;
  }
  return !1;
}
function Be(n, t, e) {
  let s = [];
  s = s.concat(t);
  const {
    style: i = V.Fill,
    color: o = "transparent",
    borderSize: r = 1,
    borderColor: a = "transparent",
    borderStyle: l = Q.Solid,
    borderRadius: c = 0,
    borderDashedValue: h = [2, 2]
  } = e, u = n.roundRect ?? n.rect, d = (i === V.Fill || e.style === V.StrokeFill) && (!D(o) || !Bt(o));
  if (d && (n.fillStyle = o, s.forEach(({ x: g, y: m, width: f, height: _ }) => {
    n.beginPath(), u.call(n, g, m, f, _, c), n.closePath(), n.fill();
  })), (i === V.Stroke || e.style === V.StrokeFill) && r > 0 && !Bt(a)) {
    n.strokeStyle = a, n.fillStyle = a, n.lineWidth = r, l === Q.Dashed ? n.setLineDash(h) : n.setLineDash([]);
    const g = r % 2 === 1 ? 0.5 : 0, m = Math.round(g * 2);
    s.forEach(({ x: f, y: _, width: p, height: x }) => {
      p > r * 2 && x > r * 2 ? (n.beginPath(), u.call(
        n,
        f + g,
        _ + g,
        p - m,
        x - m,
        c
      ), n.closePath(), n.stroke()) : d || n.fillRect(f, _, p, x);
    });
  }
}
const pn = {
  name: "rect",
  checkEventOn: Ss,
  draw: (n, t, e) => {
    Be(n, t, e);
  }
};
function Cs(n, t) {
  const {
    size: e = 12,
    paddingLeft: s = 0,
    paddingTop: i = 0,
    paddingRight: o = 0,
    paddingBottom: r = 0,
    weight: a = "normal",
    family: l
  } = t, {
    x: c,
    y: h,
    text: u,
    align: d = "left",
    baseline: g = "top",
    width: m,
    height: f
  } = n, _ = m ?? s + jt(u, e, a, l) + o, p = f ?? i + e + r;
  let x;
  switch (d) {
    case "left":
    case "start": {
      x = c;
      break;
    }
    case "right":
    case "end": {
      x = c - _;
      break;
    }
    default: {
      x = c - _ / 2;
      break;
    }
  }
  let y;
  switch (g) {
    case "top":
    case "hanging": {
      y = h;
      break;
    }
    case "bottom":
    case "ideographic":
    case "alphabetic": {
      y = h - p;
      break;
    }
    default: {
      y = h - p / 2;
      break;
    }
  }
  return { x, y, width: _, height: p };
}
function ws(n, t, e) {
  let s = [];
  s = s.concat(t);
  for (let i = 0; i < s.length; i++) {
    const { x: o, y: r, width: a, height: l } = Cs(s[i], e);
    if (n.x >= o && n.x <= o + a && n.y >= r && n.y <= r + l)
      return !0;
  }
  return !1;
}
function Re(n, t, e) {
  let s = [];
  s = s.concat(t);
  const {
    color: i = "currentColor",
    size: o = 12,
    family: r,
    weight: a,
    paddingLeft: l = 0,
    paddingTop: c = 0,
    paddingRight: h = 0
  } = e, u = s.map((d) => Cs(d, e));
  Be(n, u, { ...e, color: e.backgroundColor }), n.textAlign = "left", n.textBaseline = "top", n.font = Tt(o, a, r), n.fillStyle = i, s.forEach((d, g) => {
    const m = u[g];
    n.fillText(
      d.text,
      m.x + l,
      m.y + c,
      m.width - l - h
    );
  });
}
const bs = {
  name: "text",
  checkEventOn: ws,
  draw: (n, t, e) => {
    Re(n, t, e);
  }
}, _n = bs, xn = Re;
function yn(n, t) {
  const e = n.x - t.x, s = n.y - t.y;
  return Math.sqrt(e * e + s * s);
}
function Is(n, t) {
  let e = [];
  e = e.concat(t);
  for (let s = 0; s < e.length; s++) {
    const i = e[s];
    if (Math.abs(yn(n, i) - i.r) < Y) {
      const { r: o, startAngle: r, endAngle: a } = i, l = o * Math.cos(r) + i.x, c = o * Math.sin(r) + i.y, h = o * Math.cos(a) + i.x, u = o * Math.sin(a) + i.y;
      if (n.x <= Math.max(l, h) + Y && n.x >= Math.min(l, h) - Y && n.y <= Math.max(c, u) + Y && n.y >= Math.min(c, u) - Y)
        return !0;
    }
  }
  return !1;
}
function Ts(n, t, e) {
  let s = [];
  s = s.concat(t);
  const {
    style: i = Q.Solid,
    size: o = 1,
    color: r = "currentColor",
    dashedValue: a = [2, 2]
  } = e;
  n.lineWidth = o, n.strokeStyle = r, i === Q.Dashed ? n.setLineDash(a) : n.setLineDash([]), s.forEach(({ x: l, y: c, r: h, startAngle: u, endAngle: d }) => {
    n.beginPath(), n.arc(l, c, h, u, d), n.stroke(), n.closePath();
  });
}
const vn = {
  name: "arc",
  checkEventOn: Is,
  draw: (n, t, e) => {
    Ts(n, t, e);
  }
};
function Sn(n, t) {
  const e = document.createElement("div");
  return e.style.position = "absolute", e.style.zIndex = "1000", e.style.left = `${n.x}px`, e.style.top = `${n.y}px`, e.innerHTML = n.content, e.id = n.id, t.width != null && t.width > 0 && (e.style.width = `${t.width}px`), t.height != null && t.height > 0 && (e.style.height = `${t.height}px`), t.backgroundColor != null && t.backgroundColor !== "" && (e.style.backgroundColor = t.backgroundColor), t.color != null && t.color !== "" && (e.style.color = t.color), t.fontSize != null && t.fontSize > 0 && (e.style.fontSize = `${t.fontSize}px`), t.fontFamily != null && t.fontFamily !== "" && (e.style.fontFamily = t.fontFamily), t.border != null && t.border !== "" && (e.style.border = t.border), t.padding != null && t.padding > 0 && (e.style.padding = `${t.padding}px`), t.borderRadius != null && t.borderRadius > 0 && (e.style.borderRadius = `${t.borderRadius}px`), e;
}
function Cn(n, t) {
  return document.elementFromPoint(n.x, n.y)?.closest(`#${t.id}`) !== null;
}
function wn(n, t, e) {
  const s = n.canvas, i = document.createElement("div");
  i.style.position = "absolute", i.style.left = "0", i.style.top = "0", i.style.pointerEvents = "none";
  const o = Sn(t, e);
  i.appendChild(o), s.parentNode != null ? s.parentNode.appendChild(i) : console.warn("Canvas has no parent node to append HTML content");
}
const bn = {
  name: "html",
  checkEventOn: Cn,
  draw: wn
}, Kt = {}, In = [fn, Hi, mn, pn, bs, _n, vn, bn];
In.forEach((n) => {
  Kt[n.name] = ue.extend(n);
});
function fo() {
  return Object.keys(Kt);
}
function mo(n) {
  Kt[n.name] = ue.extend(n);
}
function Tn(n) {
  return Kt[n] ?? null;
}
function po(n) {
  return Kt[n] ?? null;
}
class ct extends ke {
  constructor(t) {
    super(), this._widget = t;
  }
  getWidget() {
    return this._widget;
  }
  createFigure(t, e) {
    const s = Tn(t.name);
    if (s !== null) {
      const i = new s(t);
      if (C(e)) {
        for (const o in e)
          e.hasOwnProperty(o) && i.registerEvent(o, e[o]);
        this.addChild(i);
      }
      return i;
    }
    return null;
  }
  draw(t) {
    this.clear(), this.drawImp(t);
  }
}
class En extends ct {
  drawImp(t) {
    const e = this.getWidget(), s = this.getWidget().getPane(), i = s.getChart(), o = e.getBounding(), r = i.getStyles().grid;
    if (r.show) {
      t.save(), t.globalCompositeOperation = "destination-over";
      const l = r.horizontal;
      if (l.show) {
        const g = s.getAxisComponent().getTicks().map((m) => ({
          coordinates: [
            { x: 0, y: m.coord },
            { x: o.width, y: m.coord }
          ]
        }));
        this.createFigure({
          name: "line",
          attrs: g,
          styles: l
        })?.draw(t);
      }
      const h = r.vertical;
      if (h.show) {
        const g = i.getXAxisPane().getAxisComponent().getTicks().map((m) => ({
          coordinates: [
            { x: m.coord, y: 0 },
            { x: m.coord, y: o.height }
          ]
        }));
        this.createFigure({
          name: "line",
          attrs: g,
          styles: h
        })?.draw(t);
      }
      t.restore();
    }
  }
}
class ge extends ct {
  eachChildren(t) {
    const s = this.getWidget().getPane().getChart().getChartStore(), i = s.getVisibleDataList(), o = s.getTimeScaleStore().getBarSpace();
    i.forEach((r, a) => {
      t(r, o, a);
    });
  }
}
class Es extends ge {
  constructor() {
    super(...arguments), this._boundCandleBarClickEvent = (t) => () => (this.getWidget().getPane().getChart().getChartStore().getActionStore().execute(et.OnCandleBarClick, t), !1);
  }
  drawImp(t) {
    const e = this.getWidget().getPane(), s = e.getId() === L.CANDLE, i = e.getChart().getChartStore(), o = this.getCandleBarOptions(i);
    if (o !== null) {
      let r = 0, a = 0, l = [1, 1];
      if (o.type === O.CandleVolume) {
        const u = i.getVisibleDataList().filter((d) => d.data !== void 0 && d.data !== null).map((d) => d.data);
        l = Ae(u, "volume", "volume");
      }
      if (o.type === O.Ohlc) {
        const { gapBar: h } = i.getTimeScaleStore().getBarSpace();
        r = Math.min(Math.max(Math.round(h * 0.2), 1), 8), r > 2 && r % 2 === 1 && r--, a = Math.floor(a / 2);
      }
      const c = e.getAxisComponent();
      this.eachChildren((h, u) => {
        const { data: d, x: g } = h;
        if (C(d)) {
          const { open: m, high: f, low: _, close: p, volume: x } = d, { type: y, styles: v } = o, S = [];
          p > m ? (S[0] = v.upColor, S[1] = v.upBorderColor, S[2] = v.upWickColor) : p < m ? (S[0] = v.downColor, S[1] = v.downBorderColor, S[2] = v.downWickColor) : (S[0] = v.noChangeColor, S[1] = v.noChangeBorderColor, S[2] = v.noChangeWickColor);
          const w = c.convertToPixel(m), b = c.convertToPixel(p), I = [
            w,
            b,
            c.convertToPixel(f),
            c.convertToPixel(_)
          ];
          I.sort((P, M) => P - M);
          let T = [];
          switch (y) {
            case O.CandleSolid: {
              T = this._createSolidBar(g, I, u, S);
              break;
            }
            case O.CandleVolume: {
              let P = 0;
              x !== void 0 && (P = Math.round(
                -6 + (x - l[1]) * (6 - -0.4) / (l[0] - l[1])
              )), T = this._createVolumeCandleBar(
                g + P,
                I,
                u,
                S
              );
              break;
            }
            case O.CandleHighLow: {
              const P = i.getStyles().candle.highLow.color;
              T = this._createHighLowCandle(g, I, u, P);
              break;
            }
            case O.CandleStroke: {
              T = this._createStrokeBar(g, I, u, S);
              break;
            }
            case O.CandleUpStroke: {
              p > m ? T = this._createStrokeBar(g, I, u, S) : T = this._createSolidBar(g, I, u, S);
              break;
            }
            case O.CandleDownStroke: {
              m > p ? T = this._createStrokeBar(g, I, u, S) : T = this._createSolidBar(g, I, u, S);
              break;
            }
            case O.Ohlc: {
              T = [
                {
                  name: "rect",
                  attrs: [
                    {
                      x: g - a,
                      y: I[0],
                      width: r,
                      height: I[3] - I[0]
                    },
                    {
                      x: g - u.halfGapBar,
                      y: w + r > I[3] ? I[3] - r : w,
                      width: u.halfGapBar,
                      height: r
                    },
                    {
                      x: g + a,
                      y: b + r > I[3] ? I[3] - r : b,
                      width: u.halfGapBar - a,
                      height: r
                    }
                  ],
                  styles: { color: S[0] }
                }
              ];
              break;
            }
          }
          T.forEach((P) => {
            let M;
            s && (M = {
              mouseClickEvent: this._boundCandleBarClickEvent(h)
            }), this.createFigure(P, M)?.draw(t);
          });
        }
      });
    }
  }
  getCandleBarOptions(t) {
    const e = t.getStyles().candle;
    return {
      type: e.type,
      styles: e.bar
    };
  }
  _createSolidBar(t, e, s, i) {
    return [
      {
        name: "rect",
        attrs: [
          {
            x: t,
            y: e[0],
            width: 1,
            height: e[1] - e[0]
          },
          {
            x: t,
            y: e[2],
            width: 1,
            height: e[3] - e[2]
          }
        ],
        styles: { color: i[2] }
      },
      {
        name: "rect",
        attrs: {
          x: t - s.halfGapBar,
          y: e[1],
          width: s.gapBar,
          height: Math.max(1, e[2] - e[1])
        },
        styles: {
          style: V.StrokeFill,
          color: i[0],
          borderColor: i[1]
        }
      }
    ];
  }
  _createVolumeCandleBar(t, e, s, i) {
    return [
      {
        name: "rect",
        attrs: {
          x: t,
          y: e[0],
          width: 1,
          height: e[3] - e[0]
        },
        styles: { color: i[2] }
      },
      {
        name: "rect",
        attrs: {
          x: t - s.halfGapBar,
          y: e[1],
          width: s.gapBar,
          height: Math.max(1, e[2] - e[1])
        },
        styles: {
          style: V.StrokeFill,
          color: i[0],
          borderColor: i[1]
        }
      }
    ];
  }
  _createHighLowCandle(t, e, s, i) {
    return [
      {
        name: "rect",
        attrs: {
          x: t,
          y: e[0],
          width: s.gapBar,
          height: e[3] - e[0]
        },
        styles: { color: i, borderColor: i }
      }
    ];
  }
  _createStrokeBar(t, e, s, i) {
    return [
      {
        name: "rect",
        attrs: [
          {
            x: t,
            y: e[0],
            width: 1,
            height: e[1] - e[0]
          },
          {
            x: t,
            y: e[2],
            width: 1,
            height: e[3] - e[2]
          }
        ],
        styles: { color: i[2] }
      },
      {
        name: "rect",
        attrs: {
          x: t - s.halfGapBar,
          y: e[1],
          width: s.gapBar,
          height: Math.max(1, e[2] - e[1])
        },
        styles: {
          style: V.Stroke,
          borderColor: i[1]
        }
      }
    ];
  }
}
class Pn extends Es {
  getCandleBarOptions(t) {
    const e = this.getWidget().getPane();
    if (!e.getAxisComponent().isInCandle()) {
      const i = t.getIndicatorStore().getInstances(e.getId());
      for (const o of i) {
        const r = o.getIndicator();
        if (r.shouldOhlc && r.visible) {
          const a = r.styles, l = t.getStyles().indicator, c = H(
            a,
            "ohlc.upColor",
            l.ohlc.upColor
          ), h = H(
            a,
            "ohlc.downColor",
            l.ohlc.downColor
          ), u = H(
            a,
            "ohlc.noChangeColor",
            l.ohlc.noChangeColor
          );
          return {
            type: O.Ohlc,
            styles: {
              upColor: c,
              downColor: h,
              noChangeColor: u,
              upBorderColor: c,
              downBorderColor: h,
              noChangeBorderColor: u,
              upWickColor: c,
              downWickColor: h,
              noChangeWickColor: u
            }
          };
        }
      }
    }
    return null;
  }
  drawImp(t) {
    super.drawImp(t);
    const e = this.getWidget(), s = e.getPane(), i = s.getChart(), o = e.getBounding(), r = i.getXAxisPane().getAxisComponent(), a = s.getAxisComponent(), l = i.getChartStore(), c = l.getDataList(), h = l.getTimeScaleStore(), u = h.getVisibleRange(), d = l.getIndicatorStore().getInstances(s.getId()), g = l.getStyles().indicator;
    t.save(), d.forEach((m) => {
      const f = m.getIndicator();
      if (f.visible) {
        f.zLevel < 0 ? t.globalCompositeOperation = "destination-over" : t.globalCompositeOperation = "source-over";
        let _ = !1;
        if (f.draw !== null && (t.save(), _ = f.draw({
          ctx: t,
          TViewDataList: c,
          indicator: f,
          visibleRange: u,
          bounding: o,
          barSpace: h.getBarSpace(),
          defaultStyles: g,
          xAxis: r,
          yAxis: a
        }) ?? !1, t.restore()), !_) {
          const p = f.result, x = [];
          this.eachChildren((y, v) => {
            const { halfGapBar: S } = v, { dataIndex: w, x: b } = y, I = r.convertToPixel(w - 1), T = r.convertToPixel(w + 1), P = p[w - 1] ?? null, M = p[w] ?? null, B = p[w + 1] ?? null, X = { x: I }, q = { x: b }, R = { x: T };
            f.figures.forEach(({ key: A }) => {
              const j = P?.[A];
              E(j) && (X[A] = a.convertToPixel(j));
              const ht = M?.[A];
              E(ht) && (q[A] = a.convertToPixel(ht));
              const J = B?.[A];
              E(J) && (R[A] = a.convertToPixel(J));
            }), De(
              c,
              f,
              w,
              g,
              (A, j, ht) => {
                if (C(M?.[A.key])) {
                  const J = q[A.key];
                  let it = A.attrs?.({
                    data: {
                      prev: P,
                      current: M,
                      next: B
                    },
                    coordinate: {
                      prev: X,
                      current: q,
                      next: R
                    },
                    bounding: o,
                    barSpace: v,
                    xAxis: r,
                    yAxis: a
                  });
                  if (!C(it))
                    switch (A.type) {
                      case "circle": {
                        it = { x: b, y: J, r: Math.max(1, S) };
                        break;
                      }
                      case "rect":
                      case "bar": {
                        const qt = A.baseValue ?? a.getRange().from, Et = a.convertToPixel(qt);
                        let Pt = Math.abs(Et - J);
                        qt !== M?.[A.key] && (Pt = Math.max(1, Pt));
                        let vt;
                        J > Et ? vt = Et : vt = J, it = {
                          x: b - S,
                          y: vt,
                          width: Math.max(1, S * 2),
                          height: Pt
                        };
                        break;
                      }
                      case "line": {
                        C(x[ht]) || (x[ht] = []), E(q[A.key]) && E(R[A.key]) && x[ht].push({
                          coordinates: [
                            {
                              x: q.x,
                              y: q[A.key]
                            },
                            {
                              x: R.x,
                              y: R[A.key]
                            }
                          ],
                          styles: j
                        });
                        break;
                      }
                    }
                  const ut = A.type;
                  C(it) && ut !== "line" && this.createFigure({
                    name: ut === "bar" ? "rect" : ut,
                    attrs: it,
                    styles: j
                  })?.draw(t);
                }
              }
            );
          }), x.forEach((y) => {
            if (y.length > 1) {
              const v = [
                {
                  coordinates: [
                    y[0].coordinates[0],
                    y[0].coordinates[1]
                  ],
                  styles: y[0].styles
                }
              ];
              for (let S = 1; S < y.length; S++) {
                const w = v[v.length - 1], b = y[S], I = w.coordinates[w.coordinates.length - 1];
                I.x === b.coordinates[0].x && I.y === b.coordinates[0].y && w.styles.style === b.styles.style && w.styles.color === b.styles.color && w.styles.size === b.styles.size && w.styles.smooth === b.styles.smooth && w.styles.dashedValue[0] === b.styles.dashedValue[0] && w.styles.dashedValue[1] === b.styles.dashedValue[1] ? w.coordinates.push(b.coordinates[1]) : v.push({
                  coordinates: [
                    b.coordinates[0],
                    b.coordinates[1]
                  ],
                  styles: b.styles
                });
              }
              v.forEach(({ coordinates: S, styles: w }) => {
                this.createFigure({
                  name: "line",
                  attrs: { coordinates: S },
                  styles: w
                })?.draw(t);
              });
            }
          });
        }
      }
    }), t.restore();
  }
}
class Mn extends ct {
  drawImp(t) {
    const e = this.getWidget(), s = e.getPane(), i = e.getBounding(), o = e.getPane().getChart().getChartStore(), r = o.getTooltipStore().getCrosshair(), a = o.getStyles().crosshair;
    if (D(r.paneId) && a.show) {
      if (r.paneId === s.getId()) {
        const c = r.y;
        this._drawLine(
          t,
          [
            { x: 0, y: c },
            { x: i.width, y: c }
          ],
          a.horizontal
        );
      }
      const l = r.realX;
      this._drawLine(
        t,
        [
          { x: l, y: 0 },
          { x: l, y: i.height }
        ],
        a.vertical
      );
    }
  }
  _drawLine(t, e, s) {
    if (s.show) {
      const i = s.line;
      i.show && this.createFigure({
        name: "line",
        attrs: { coordinates: e },
        styles: i
      })?.draw(t);
    }
  }
}
class Ps extends ct {
  constructor() {
    super(...arguments), this._boundIconClickEvent = (t) => () => (this.getWidget().getPane().getChart().getChartStore().getActionStore().execute(et.OnTooltipIconClick, { ...t }), !0), this._boundIconMouseMoveEvent = (t) => () => (this.getWidget().getPane().getChart().getChartStore().getTooltipStore().setActiveIcon({ ...t }), !0);
  }
  drawImp(t) {
    const e = this.getWidget(), s = e.getPane(), i = s.getChart().getChartStore(), o = i.getTooltipStore().getCrosshair();
    if (C(o.TViewData)) {
      const r = e.getBounding(), a = i.getCustomApi(), l = i.getThousandsSeparator(), c = i.getDecimalFoldThreshold(), h = i.getIndicatorStore().getInstances(s.getId()), u = i.getTooltipStore().getActiveIcon(), d = i.getStyles().indicator, { offsetLeft: g, offsetTop: m, offsetRight: f } = d.tooltip;
      this.drawIndicatorTooltip(
        t,
        s.getId(),
        i.getDataList(),
        o,
        u,
        h,
        a,
        l,
        c,
        g,
        m,
        r.width - f,
        d
      );
    }
  }
  drawIndicatorTooltip(t, e, s, i, o, r, a, l, c, h, u, d, g) {
    const m = g.tooltip;
    if (this.isDrawTooltip(i, m)) {
      const f = m.text;
      r.forEach((_) => {
        const p = _.getIndicator();
        let x = 0;
        const y = { x: h, y: u }, {
          name: v,
          calcParamsText: S,
          values: w,
          icons: b
        } = this.getIndicatorTooltipData(
          s,
          i,
          p,
          a,
          l,
          c,
          g
        ), I = v.length > 0, T = w.length > 0;
        if (I || T) {
          const [P, M, B] = this.classifyTooltipIcons(b);
          if (x = this.drawStandardTooltipIcons(
            t,
            o,
            P,
            y,
            e,
            p.name,
            h,
            x,
            d
          ), I) {
            let X = v;
            S.length > 0 && (X = `${X}${S}`), x = this.drawStandardTooltipLegends(
              t,
              [
                {
                  title: { text: "", color: f.color },
                  value: { text: X, color: f.color }
                }
              ],
              y,
              h,
              x,
              d,
              f
            );
          }
          x = this.drawStandardTooltipIcons(
            t,
            o,
            M,
            y,
            e,
            p.name,
            h,
            x,
            d
          ), T && (x = this.drawStandardTooltipLegends(
            t,
            w,
            y,
            h,
            x,
            d,
            m.text
          )), x = this.drawStandardTooltipIcons(
            t,
            o,
            B,
            y,
            e,
            p.name,
            h,
            x,
            d
          ), u = y.y + x;
        }
      });
    }
    return u;
  }
  drawStandardTooltipIcons(t, e, s, i, o, r, a, l, c) {
    if (s.length > 0) {
      let h = 0, u = 0;
      s.forEach((d) => {
        const {
          marginLeft: g = 0,
          marginTop: m = 0,
          marginRight: f = 0,
          marginBottom: _ = 0,
          paddingLeft: p = 0,
          paddingTop: x = 0,
          paddingRight: y = 0,
          paddingBottom: v = 0,
          size: S,
          fontFamily: w,
          icon: b
        } = d;
        t.font = Tt(S, "normal", w), h += g + p + t.measureText(b).width + y + f, u = Math.max(
          u,
          m + x + S + v + _
        );
      }), i.x + h > c ? (i.x = a, i.y += l, l = u) : l = Math.max(l, u), s.forEach((d) => {
        const {
          marginLeft: g = 0,
          marginTop: m = 0,
          marginRight: f = 0,
          paddingLeft: _ = 0,
          paddingTop: p = 0,
          paddingRight: x = 0,
          paddingBottom: y = 0,
          color: v,
          activeColor: S,
          size: w,
          fontFamily: b,
          icon: I,
          backgroundColor: T,
          activeBackgroundColor: P
        } = d, M = e?.paneId === o && e?.indicatorName === r && e?.iconId === d.id;
        this.createFigure(
          {
            name: "text",
            attrs: {
              text: I,
              x: i.x + g,
              y: i.y + m
            },
            styles: {
              paddingLeft: _,
              paddingTop: p,
              paddingRight: x,
              paddingBottom: y,
              color: M ? S : v,
              size: w,
              family: b,
              backgroundColor: M ? P : T
            }
          },
          {
            mouseClickEvent: this._boundIconClickEvent({
              paneId: o,
              indicatorName: r,
              iconId: d.id
            }),
            mouseMoveEvent: this._boundIconMouseMoveEvent({
              paneId: o,
              indicatorName: r,
              iconId: d.id
            })
          }
        )?.draw(t), i.x += g + _ + t.measureText(I).width + x + f;
      });
    }
    return l;
  }
  drawStandardTooltipLegends(t, e, s, i, o, r, a) {
    if (e.length > 0) {
      const {
        marginLeft: l,
        marginTop: c,
        marginRight: h,
        marginBottom: u,
        size: d,
        family: g,
        weight: m
      } = a;
      t.font = Tt(d, m, g), e.forEach((f) => {
        const _ = f.title, p = f.value, x = t.measureText(_.text).width, y = t.measureText(p.text).width, v = x + y, S = c + d + u;
        s.x + l + v + h > r ? (s.x = i, s.y += o, o = S) : o = Math.max(o, S), _.text.length > 0 && this.createFigure({
          name: "text",
          attrs: {
            x: s.x + l,
            y: s.y + c,
            text: _.text
          },
          styles: { color: _.color, size: d, family: g, weight: m }
        })?.draw(t), this.createFigure({
          name: "text",
          attrs: {
            x: s.x + l + x,
            y: s.y + c,
            text: p.text
          },
          styles: { color: p.color, size: d, family: g, weight: m }
        })?.draw(t), s.x += l + v + h;
      });
    }
    return o;
  }
  isDrawTooltip(t, e) {
    const s = e.showRule;
    return s === we.Always || s === we.FollowCross && D(t.paneId);
  }
  getIndicatorTooltipData(t, e, s, i, o, r, a) {
    const l = a.tooltip, c = l.showName ? s.shortName : "";
    let h = "";
    const u = s.calcParams;
    u.length > 0 && l.showParams && (h = `(${u.join(",")})`);
    const d = {
      name: c,
      calcParamsText: h,
      values: [],
      icons: l.icons
    }, g = e.dataIndex, m = s.result ?? [], f = [];
    if (s.visible) {
      const _ = m[g] ?? {};
      De(
        t,
        s,
        g,
        a,
        (p, x) => {
          if (D(p.title)) {
            const y = x.color;
            let v = _[p.key];
            E(v) && (v = N(v, s.precision), s.shouldFormatBigNumber && (v = i.formatBigNumber(v))), f.push({
              title: { text: p.title, color: y },
              value: {
                text: z(
                  W(
                    v ?? l.defaultValue,
                    o
                  ),
                  r
                ),
                color: y
              }
            });
          }
        }
      ), d.values = f;
    }
    if (s.createTooltipDataSource !== null) {
      const _ = this.getWidget(), p = _.getPane(), x = p.getChart().getChartStore(), {
        name: y,
        calcParamsText: v,
        values: S,
        icons: w
      } = s.createTooltipDataSource({
        TViewDataList: t,
        indicator: s,
        visibleRange: x.getTimeScaleStore().getVisibleRange(),
        bounding: _.getBounding(),
        crosshair: e,
        defaultStyles: a,
        xAxis: p.getChart().getXAxisPane().getAxisComponent(),
        yAxis: p.getAxisComponent()
      });
      if (D(y) && l.showName && (d.name = y), D(v) && l.showParams && (d.calcParamsText = v), C(w) && (d.icons = w), C(S) && s.visible) {
        const b = [], I = a.tooltip.text.color;
        S.forEach((T) => {
          let P = { text: "", color: I };
          at(T.title) ? P = T.title : P.text = T.title;
          let M = { text: "", color: I };
          at(T.value) ? M = T.value : M.text = T.value, M.text = z(
            W(M.text, o),
            r
          ), b.push({ title: P, value: M });
        }), d.values = b;
      }
    }
    return d;
  }
  classifyTooltipIcons(t) {
    const e = [], s = [], i = [];
    return t.forEach((o) => {
      switch (o.position) {
        case Qt.Left: {
          e.push(o);
          break;
        }
        case Qt.Middle: {
          s.push(o);
          break;
        }
        case Qt.Right: {
          i.push(o);
          break;
        }
      }
    }), [e, s, i];
  }
}
class Ms extends ct {
  constructor(t) {
    super(t), this._initEvent();
  }
  _initEvent() {
    const t = this.getWidget().getPane(), e = t.getId(), s = t.getChart().getChartStore().getOverlayStore();
    this.registerEvent("mouseMoveEvent", (i) => {
      const o = s.getProgressInstanceInfo();
      if (o !== null) {
        const r = o.instance;
        let a = o.paneId;
        r.isStart() && (s.updateProgressInstanceInfo(e), a = e);
        const l = r.getOverlay(), c = l.points.length - 1, h = `${At}point_${c}`;
        return r.isDrawing() && a === e && (r.eventMoveForDrawing(
          this._coordinateToPoint(
            o.instance.getOverlay(),
            i
          )
        ), l.onDrawing?.({
          overlay: l,
          figureKey: h,
          figureIndex: c,
          ...i
        })), this._figureMouseMoveEvent(
          r,
          K.Point,
          h,
          c,
          0
        )(i);
      }
      return s.setHoverInstanceInfo(
        {
          paneId: e,
          instance: null,
          figureType: K.None,
          figureKey: "",
          figureIndex: -1,
          attrsIndex: -1
        },
        i
      ), !1;
    }).registerEvent("mouseClickEvent", (i) => {
      const o = s.getProgressInstanceInfo();
      if (o !== null) {
        const r = o.instance;
        let a = o.paneId;
        r.isStart() && (s.updateProgressInstanceInfo(e, !0), a = e);
        const l = r.getOverlay(), c = l.points.length - 1, h = `${At}point_${c}`;
        return r.isDrawing() && a === e && (r.eventMoveForDrawing(this._coordinateToPoint(l, i)), l.onDrawing?.({
          overlay: l,
          figureKey: h,
          figureIndex: c,
          ...i
        }), r.nextStep(), r.isDrawing() || (s.progressInstanceComplete(), l.onDrawEnd?.({
          overlay: l,
          figureKey: h,
          figureIndex: c,
          ...i
        }))), this._figureMouseClickEvent(
          r,
          K.Point,
          h,
          c,
          0
        )(i);
      }
      return s.setClickInstanceInfo(
        {
          paneId: e,
          instance: null,
          figureType: K.None,
          figureKey: "",
          figureIndex: -1,
          attrsIndex: -1
        },
        i
      ), !1;
    }).registerEvent("mouseDoubleClickEvent", (i) => {
      const o = s.getProgressInstanceInfo();
      if (o !== null) {
        const r = o.instance, a = o.paneId, l = r.getOverlay();
        if (r.isDrawing() && a === e && (r.forceComplete(), !r.isDrawing())) {
          s.progressInstanceComplete();
          const h = l.points.length - 1, u = `${At}point_${h}`;
          l.onDrawEnd?.({
            overlay: l,
            figureKey: u,
            figureIndex: h,
            ...i
          });
        }
        const c = l.points.length - 1;
        return this._figureMouseClickEvent(
          r,
          K.Point,
          `${At}point_${c}`,
          c,
          0
        )(i);
      }
      return !1;
    }).registerEvent("mouseRightClickEvent", (i) => {
      const o = s.getProgressInstanceInfo();
      if (o !== null) {
        const r = o.instance;
        if (r.isDrawing()) {
          const a = r.getOverlay().points.length - 1;
          return this._figureMouseRightClickEvent(
            r,
            K.Point,
            `${At}point_${a}`,
            a,
            0
          )(i);
        }
      }
      return !1;
    }).registerEvent("mouseUpEvent", (i) => {
      const { instance: o, figureIndex: r, figureKey: a } = s.getPressedInstanceInfo();
      if (o !== null) {
        const l = o.getOverlay();
        l.onPressedMoveEnd?.({
          overlay: l,
          figureKey: a,
          figureIndex: r,
          ...i
        });
      }
      return s.setPressedInstanceInfo({
        paneId: e,
        instance: null,
        figureType: K.None,
        figureKey: "",
        figureIndex: -1,
        attrsIndex: -1
      }), !1;
    }).registerEvent("pressedMouseMoveEvent", (i) => {
      const { instance: o, figureType: r, figureIndex: a, figureKey: l } = s.getPressedInstanceInfo();
      if (o !== null) {
        const c = o.getOverlay();
        if (!c.lock && !(c.onPressedMoving?.({
          overlay: c,
          figureIndex: a,
          figureKey: l,
          ...i
        }) ?? !1)) {
          const h = this._coordinateToPoint(c, i);
          r === K.Point ? o.eventPressedPointMove(h, a) : o.eventPressedOtherMove(
            h,
            this.getWidget().getPane().getChart().getChartStore().getTimeScaleStore()
          );
        }
        return !0;
      }
      return !1;
    });
  }
  _createFigureEvents(t, e, s, i, o, r) {
    let a;
    if (!t.isDrawing()) {
      let l = [];
      if (C(r) && (ae(r) ? r && (l = ti()) : l = r), l.length === 0)
        return {
          mouseMoveEvent: this._figureMouseMoveEvent(
            t,
            e,
            s,
            i,
            o
          ),
          mouseDownEvent: this._figureMouseDownEvent(
            t,
            e,
            s,
            i,
            o
          ),
          mouseClickEvent: this._figureMouseClickEvent(
            t,
            e,
            s,
            i,
            o
          ),
          mouseRightClickEvent: this._figureMouseRightClickEvent(
            t,
            e,
            s,
            i,
            o
          ),
          mouseDoubleClickEvent: this._figureMouseDoubleClickEvent(
            t,
            e,
            s,
            i,
            o
          )
        };
      a = {}, !l.includes("mouseMoveEvent") && !l.includes("touchMoveEvent") && (a.mouseMoveEvent = this._figureMouseMoveEvent(
        t,
        e,
        s,
        i,
        o
      )), !l.includes("mouseDownEvent") && !l.includes("touchStartEvent") && (a.mouseDownEvent = this._figureMouseDownEvent(
        t,
        e,
        s,
        i,
        o
      )), !l.includes("mouseClickEvent") && !l.includes("tapEvent") && (a.mouseClickEvent = this._figureMouseClickEvent(
        t,
        e,
        s,
        i,
        o
      )), !l.includes("mouseDoubleClickEvent") && !l.includes("doubleTapEvent") && (a.mouseDoubleClickEvent = this._figureMouseDoubleClickEvent(
        t,
        e,
        s,
        i,
        o
      )), l.includes("mouseRightClickEvent") || (a.mouseRightClickEvent = this._figureMouseRightClickEvent(
        t,
        e,
        s,
        i,
        o
      ));
    }
    return a;
  }
  _figureMouseMoveEvent(t, e, s, i, o) {
    return (r) => {
      const a = this.getWidget().getPane();
      return a.getChart().getChartStore().getOverlayStore().setHoverInstanceInfo(
        {
          paneId: a.getId(),
          instance: t,
          figureType: e,
          figureKey: s,
          figureIndex: i,
          attrsIndex: o
        },
        r
      ), !0;
    };
  }
  _figureMouseDownEvent(t, e, s, i, o) {
    return (r) => {
      const a = this.getWidget().getPane(), l = a.getId(), c = a.getChart().getChartStore().getOverlayStore(), h = t.getOverlay();
      return t.startPressedMove(this._coordinateToPoint(h, r)), h.onPressedMoveStart?.({ overlay: h, figureIndex: i, figureKey: s, ...r }), c.setPressedInstanceInfo({
        paneId: l,
        instance: t,
        figureType: e,
        figureKey: s,
        figureIndex: i,
        attrsIndex: o
      }), !0;
    };
  }
  _figureMouseClickEvent(t, e, s, i, o) {
    return (r) => {
      const a = this.getWidget().getPane(), l = a.getId();
      return a.getChart().getChartStore().getOverlayStore().setClickInstanceInfo(
        {
          paneId: l,
          instance: t,
          figureType: e,
          figureKey: s,
          figureIndex: i,
          attrsIndex: o
        },
        r
      ), !0;
    };
  }
  _figureMouseDoubleClickEvent(t, e, s, i, o) {
    return (r) => {
      const a = t.getOverlay();
      return a.onDoubleClick?.({ ...r, figureIndex: i, figureKey: s, overlay: a }), !0;
    };
  }
  _figureMouseRightClickEvent(t, e, s, i, o) {
    return (r) => {
      const a = t.getOverlay();
      return (a.onRightClick?.({ overlay: a, figureIndex: i, figureKey: s, ...r }) ?? !1) || this.getWidget().getPane().getChart().getChartStore().getOverlayStore().removeInstance(a), !0;
    };
  }
  _coordinateToPoint(t, e) {
    const s = {}, i = this.getWidget().getPane(), o = i.getChart(), r = i.getId(), a = o.getChartStore().getTimeScaleStore();
    if (this.coordinateToPointTimestampDataIndexFlag()) {
      const c = o.getXAxisPane().getAxisComponent().convertFromPixel(e.x), h = a.dataIndexToTimestamp(c) ?? void 0;
      s.dataIndex = c, s.timestamp = h;
    }
    if (this.coordinateToPointValueFlag()) {
      const l = i.getAxisComponent();
      let c = l.convertFromPixel(e.y);
      if (t.mode !== se.Normal && r === L.CANDLE && E(s.dataIndex)) {
        const h = a.getDataByDataIndex(s.dataIndex);
        if (h !== null) {
          const u = t.modeSensitivity;
          if (c > h.high)
            if (t.mode === se.WeakMagnet) {
              const d = l.convertToPixel(h.high), g = l.convertFromPixel(d - u);
              c < g && (c = h.high);
            } else
              c = h.high;
          else if (c < h.low)
            if (t.mode === se.WeakMagnet) {
              const d = l.convertToPixel(h.low), g = l.convertFromPixel(d - u);
              c > g && (c = h.low);
            } else
              c = h.low;
          else {
            const d = Math.max(h.open, h.close), g = Math.min(h.open, h.close);
            c > d ? c - d < h.high - c ? c = d : c = h.high : c < g ? c - h.low < g - c ? c = h.low : c = g : d - c < c - g ? c = d : c = g;
          }
        }
      }
      s.value = c;
    }
    return s;
  }
  coordinateToPointValueFlag() {
    return !0;
  }
  coordinateToPointTimestampDataIndexFlag() {
    return !0;
  }
  dispatchEvent(t, e, s) {
    return this.getWidget().getPane().getChart().getChartStore().getOverlayStore().isDrawing() ? this.onEvent(t, e, s) : super.dispatchEvent(t, e, s);
  }
  checkEventOn() {
    return !0;
  }
  drawImp(t) {
    const e = this.getWidget(), s = e.getPane(), i = s.getId(), o = s.getChart(), r = s.getAxisComponent(), a = o.getXAxisPane().getAxisComponent(), l = e.getBounding(), c = o.getChartStore(), h = c.getCustomApi(), u = c.getThousandsSeparator(), d = c.getDecimalFoldThreshold(), g = c.getTimeScaleStore(), m = g.getDateTimeFormat(), f = g.getBarSpace(), _ = c.getPrecision(), p = c.getStyles().overlay, x = c.getOverlayStore(), y = x.getHoverInstanceInfo(), v = x.getClickInstanceInfo(), S = this.getCompleteOverlays(x, i), b = c.getIndicatorStore().getInstances(i).reduce(
      (T, P) => {
        const M = P.getIndicator(), B = M.precision;
        return T[M.name] = B, T.max = Math.max(T.max, B), T.min = Math.min(T.min, B), T.excludePriceVolumeMax = Math.max(
          T.excludePriceVolumeMax,
          B
        ), T.excludePriceVolumeMin = Math.min(
          T.excludePriceVolumeMin,
          B
        ), T;
      },
      {
        ..._,
        max: Math.max(_.price, _.volume),
        min: Math.min(_.price, _.volume),
        excludePriceVolumeMax: Number.MIN_SAFE_INTEGER,
        excludePriceVolumeMin: Number.MAX_SAFE_INTEGER
      }
    );
    S.forEach((T) => {
      T.getOverlay().visible && this._drawOverlay(
        t,
        T,
        l,
        f,
        b,
        m,
        h,
        u,
        d,
        p,
        a,
        r,
        y,
        v,
        g
      );
    });
    const I = x.getProgressInstanceInfo();
    if (I !== null) {
      const T = this.getProgressOverlay(I, i);
      C(T) && T.getOverlay().visible && this._drawOverlay(
        t,
        T,
        l,
        f,
        b,
        m,
        h,
        u,
        d,
        p,
        a,
        r,
        y,
        v,
        g
      );
    }
  }
  _drawOverlay(t, e, s, i, o, r, a, l, c, h, u, d, g, m, f) {
    const _ = e.getOverlay(), { points: p } = _, x = p.map((y) => {
      let v = y.dataIndex;
      E(y.timestamp) && (v = f.timestampToDataIndex(y.timestamp));
      const S = { x: 0, y: 0 };
      return E(v) && (S.x = u?.convertToPixel(v) ?? 0), E(y.value) && (S.y = d?.convertToPixel(y.value) ?? 0), S;
    });
    if (x.length > 0) {
      const y = new Array().concat(
        this.getFigures(
          _,
          x,
          s,
          i,
          o,
          l,
          c,
          r,
          h,
          u,
          d
        )
      );
      this.drawFigures(t, e, y, h);
    }
    this.drawDefaultFigures(
      t,
      e,
      x,
      s,
      o,
      r,
      a,
      l,
      c,
      h,
      u,
      d,
      g,
      m
    );
  }
  drawFigures(t, e, s, i) {
    const o = e.getOverlay();
    s.forEach((r, a) => {
      const { type: l, styles: c, attrs: h, ignoreEvent: u } = r;
      [].concat(h).forEach((g, m) => {
        const f = this._createFigureEvents(
          e,
          K.Other,
          r.key ?? "",
          a,
          m,
          u
        ), _ = { ...i[l], ...o.styles?.[l], ...c };
        this.createFigure(
          {
            name: l,
            attrs: g,
            styles: _
          },
          f
        )?.draw(t);
      });
    });
  }
  getCompleteOverlays(t, e) {
    return t.getInstances(e);
  }
  getProgressOverlay(t, e) {
    return t.paneId === e ? t.instance : null;
  }
  getFigures(t, e, s, i, o, r, a, l, c, h, u) {
    return t.createPointFigures?.({
      overlay: t,
      coordinates: e,
      bounding: s,
      barSpace: i,
      precision: o,
      thousandsSeparator: r,
      decimalFoldThreshold: a,
      dateTimeFormat: l,
      defaultStyles: c,
      xAxis: h,
      yAxis: u
    }) ?? [];
  }
  drawDefaultFigures(t, e, s, i, o, r, a, l, c, h, u, d, g, m) {
    const f = e.getOverlay();
    if (f.needDefaultPointFigure && (g.instance?.getOverlay().id === f.id && g.figureType !== K.None || m.instance?.getOverlay().id === f.id && m.figureType !== K.None)) {
      const _ = f.styles, p = { ...h.point, ..._?.point };
      s.forEach(({ x, y }, v) => {
        let S = p.radius, w = p.color, b = p.borderColor, I = p.borderSize;
        g.instance?.getOverlay().id === f.id && g.figureType === K.Point && g.figureIndex === v && (S = p.activeRadius, w = p.activeColor, b = p.activeBorderColor, I = p.activeBorderSize), this.createFigure(
          {
            name: "circle",
            attrs: { x, y, r: S + I },
            styles: { color: b }
          },
          this._createFigureEvents(
            e,
            K.Point,
            `${At}point_${v}`,
            v,
            0
          )
        )?.draw(t), this.createFigure({
          name: "circle",
          attrs: { x, y, r: S },
          styles: { color: w }
        })?.draw(t);
      });
    }
  }
}
class Ds extends Le {
  constructor(t, e) {
    super(t, e), this._gridView = new En(this), this._indicatorView = new Pn(this), this._crosshairLineView = new Mn(this), this._tooltipView = this.createTooltipView(), this._overlayView = new Ms(this), this.addChild(this._tooltipView), this.addChild(this._overlayView), this.getContainer().style.cursor = "crosshair", this.registerEvent("mouseMoveEvent", () => (e.getChart().getChartStore().getTooltipStore().setActiveIcon(), !1));
  }
  getName() {
    return k.MAIN;
  }
  updateMain(t) {
    this.updateMainContent(t), this._indicatorView.draw(t), this._gridView.draw(t);
  }
  createTooltipView() {
    return new Ps(this);
  }
  /* eslint-disable @typescript-eslint/no-unused-vars */
  updateMainContent(t) {
  }
  updateOverlay(t) {
    this._overlayView.draw(t), this._crosshairLineView.draw(t), this._tooltipView.draw(t);
  }
}
class Dn extends ge {
  constructor() {
    super(...arguments), this._ripplePoint = this.createFigure({
      name: "circle",
      attrs: {
        x: 0,
        y: 0,
        r: 0
      },
      styles: {
        style: "fill"
      }
    }), this._animationFrameTime = 0, this._animation = new Ie({
      iterationCount: 1 / 0
    }).doFrame((t) => {
      this._animationFrameTime = t;
      const e = this.getWidget().getPane();
      e.getChart().updatePane(F.Main, e.getId());
    });
  }
  drawImp(t) {
    const e = this.getWidget(), s = e.getPane(), i = s.getChart(), r = i.getDataList().length - 1, a = e.getBounding(), l = s.getAxisComponent(), c = i.getStyles().candle.area, h = i.getStyles().candle.type, u = [];
    let d = Number.MAX_SAFE_INTEGER, g = Number.MIN_SAFE_INTEGER, m = null;
    this.eachChildren((_) => {
      const { data: p, x } = _, y = p?.[c.value];
      if (E(y)) {
        const v = l.convertToPixel(y);
        g === Number.MIN_SAFE_INTEGER && (g = x), u.push({ x, y: v }), d = Math.min(d, v), _.dataIndex === r && (m = { x, y: v });
      }
    });
    const f = c.point;
    if (h === O.Line)
      u.length > 0 && (this.createFigure({
        name: "line",
        attrs: { coordinates: u },
        styles: {
          color: c.lineColor,
          size: c.lineSize,
          smooth: c.smooth
        }
      })?.draw(t), t.beginPath(), t.moveTo(g, a.height), t.lineTo(u[0].x, u[0].y), ie(t, u, c.smooth), t.lineTo(u[u.length - 1].x, a.height), t.closePath());
    else if (h === O.LineMark)
      u.length > 0 && (this.createFigure({
        name: "line",
        attrs: { coordinates: u },
        styles: {
          color: c.lineColor,
          size: c.lineSize,
          smooth: c.smooth
        }
      })?.draw(t), t.beginPath(), t.moveTo(g, a.height), t.lineTo(u[0].x, u[0].y), ie(t, u, c.smooth), t.lineTo(u[u.length - 1].x, a.height), t.closePath(), u.forEach((_) => {
        this.createFigure({
          name: "circle",
          attrs: {
            x: _.x,
            y: _.y,
            r: f.radius
          },
          styles: {
            style: "fill",
            color: f.color
          }
        })?.draw(t);
      }));
    else if (h === O.StepLine) {
      if (u.length > 0) {
        const _ = [];
        for (let p = 0; p < u.length; p++)
          p > 0 && _.push({
            x: u[p].x,
            y: u[p - 1].y
          }), _.push(u[p]);
        this.createFigure({
          name: "line",
          attrs: { coordinates: _ },
          styles: {
            color: c.lineColor,
            size: c.lineSize,
            smooth: !1
          }
        })?.draw(t), t.beginPath(), t.moveTo(g, a.height), t.lineTo(_[0].x, _[0].y);
        for (let p = 1; p < _.length; p++)
          t.lineTo(_[p].x, _[p].y);
        t.lineTo(
          _[_.length - 1].x,
          a.height
        ), t.closePath();
      }
    } else if (h === O.Area && u.length > 0) {
      this.createFigure({
        name: "line",
        attrs: { coordinates: u },
        styles: {
          color: c.lineColor,
          size: c.lineSize,
          smooth: c.smooth
        }
      })?.draw(t);
      const _ = c.backgroundColor;
      let p;
      if (rt(_)) {
        const x = t.createLinearGradient(
          0,
          a.height,
          0,
          d
        );
        try {
          _.forEach(({ offset: y, color: v }) => {
            x.addColorStop(y, v);
          });
        } catch {
        }
        p = x;
      } else
        p = _;
      t.fillStyle = p, t.beginPath(), t.moveTo(g, a.height), t.lineTo(u[0].x, u[0].y), ie(t, u, c.smooth), t.lineTo(u[u.length - 1].x, a.height), t.closePath(), t.fill();
    }
    if (f.show && C(m)) {
      this.createFigure({
        name: "circle",
        attrs: {
          x: m.x,
          y: m.y,
          r: f.radius
        },
        styles: {
          style: "fill",
          color: f.color
        }
      })?.draw(t);
      let _ = f.rippleRadius;
      f.animation && (_ = f.radius + this._animationFrameTime / f.animationDuration * (f.rippleRadius - f.radius), this._animation.setDuration(f.animationDuration).start()), this._ripplePoint?.setAttrs({
        x: m.x,
        y: m.y,
        r: _
      }).setStyles({ style: "fill", color: f.rippleColor }).draw(t);
    } else
      this.stopAnimation();
  }
  stopAnimation() {
    this._animation.stop();
  }
}
class An extends ge {
  drawImp(t) {
    const s = this.getWidget().getPane(), i = s.getChart().getChartStore(), o = i.getStyles().candle.priceMark, r = o.high, a = o.low;
    if (o.show && (r.show || a.show)) {
      const l = i.getThousandsSeparator(), c = i.getDecimalFoldThreshold(), h = i.getPrecision(), u = s.getAxisComponent();
      let d = Number.MIN_SAFE_INTEGER, g = 0, m = Number.MAX_SAFE_INTEGER, f = 0;
      this.eachChildren((x) => {
        const { data: y, x: v } = x;
        C(y) && (d < y.high && (d = y.high, g = v), m > y.low && (m = y.low, f = v));
      });
      const _ = u.convertToPixel(d), p = u.convertToPixel(m);
      r.show && d !== Number.MIN_SAFE_INTEGER && this._drawMark(
        t,
        z(
          W(
            N(d, h.price),
            l
          ),
          c
        ),
        { x: g, y: _ },
        _ < p ? [-2, -5] : [2, 5],
        r
      ), a.show && m !== Number.MAX_SAFE_INTEGER && this._drawMark(
        t,
        z(
          W(
            N(m, h.price),
            l
          ),
          c
        ),
        { x: f, y: p },
        _ < p ? [2, 5] : [-2, -5],
        a
      );
    }
  }
  _drawMark(t, e, s, i, o) {
    const r = s.x, a = s.y + i[0];
    this.createFigure({
      name: "line",
      attrs: {
        coordinates: [
          { x: r - 2, y: a + i[0] },
          { x: r, y: a },
          { x: r + 2, y: a + i[0] }
        ]
      },
      styles: { color: o.color }
    })?.draw(t);
    let l, c, h;
    const { width: u } = this.getWidget().getBounding();
    r > u / 2 ? (l = r - 5, c = l - o.textOffset, h = "right") : (l = r + 5, h = "left", c = l + o.textOffset);
    const d = a + i[1];
    this.createFigure({
      name: "line",
      attrs: {
        coordinates: [
          { x: r, y: a },
          { x: r, y: d },
          { x: l, y: d }
        ]
      },
      styles: { color: o.color }
    })?.draw(t), this.createFigure({
      name: "text",
      attrs: {
        x: c,
        y: d,
        text: e,
        align: h,
        baseline: "middle"
      },
      styles: {
        color: o.color,
        size: o.textSize,
        family: o.textFamily,
        weight: o.textWeight
      }
    })?.draw(t);
  }
}
class kn extends ct {
  drawImp(t) {
    const e = this.getWidget(), s = e.getPane(), i = e.getBounding(), o = s.getChart().getChartStore(), r = o.getStyles().candle.priceMark, a = r.last, l = a.line;
    if (r.show && a.show && l.show) {
      const c = s.getAxisComponent(), h = o.getDataList(), u = h[h.length - 1];
      if (u != null) {
        const { close: d, open: g } = u, m = c.convertToNicePixel(d);
        let f;
        d > g ? f = a.upColor : d < g ? f = a.downColor : f = a.noChangeColor, this.createFigure({
          name: "line",
          attrs: {
            coordinates: [
              { x: 0, y: m },
              { x: i.width, y: m }
            ]
          },
          styles: {
            style: l.style,
            color: f,
            size: l.size,
            dashedValue: l.dashedValue
          }
        })?.draw(t);
      }
    }
  }
}
const Fn = {
  time: "时间：",
  open: "开：",
  high: "高：",
  low: "低：",
  close: "收：",
  volume: "成交量：",
  turnover: "成交额：",
  change: "涨幅："
}, Ln = {
  time: "Time: ",
  open: "Open: ",
  high: "High: ",
  low: "Low: ",
  close: "Close: ",
  volume: "Volume: ",
  turnover: "Turnover: ",
  change: "Change: "
}, oe = {
  "zh-CN": Fn,
  "en-US": Ln
};
function _o(n, t) {
  oe[n] = { ...oe[n], ...t };
}
function xo() {
  return Object.keys(oe);
}
function Bn(n, t) {
  return oe[t]?.[n] ?? n;
}
class Rn extends Ps {
  drawImp(t) {
    const e = this.getWidget(), s = e.getPane(), i = s.getId(), o = s.getChart().getChartStore(), r = o.getTooltipStore().getCrosshair();
    if (C(r.TViewData)) {
      const a = e.getBounding(), l = s.getYAxisWidget().getBounding(), h = this._addHeading(a.top + 10).height, u = o.getDataList(), d = o.getPrecision(), g = o.getLocale(), m = o.getCustomApi(), f = o.getThousandsSeparator(), _ = o.getDecimalFoldThreshold(), p = o.getTooltipStore().getActiveIcon(), x = o.getIndicatorStore().getInstances(s.getId()), y = o.getTimeScaleStore().getDateTimeFormat(), v = o.getStyles(), S = v.candle, w = v.indicator;
      if (S.tooltip.showType === Ct.Rect && w.tooltip.showType === Ct.Rect) {
        const b = this.isDrawTooltip(
          r,
          S.tooltip
        ), I = this.isDrawTooltip(
          r,
          w.tooltip
        );
        this._drawRectTooltip(
          t,
          u,
          x,
          a,
          l,
          r,
          d,
          y,
          g,
          m,
          f,
          _,
          b,
          I,
          h,
          v
        );
      } else if (S.tooltip.showType === Ct.Standard && w.tooltip.showType === Ct.Standard) {
        const { offsetLeft: b, offsetRight: I } = S.tooltip, T = a.width - I, P = this._drawCandleStandardTooltip(
          t,
          u,
          i,
          r,
          p,
          d,
          y,
          g,
          m,
          f,
          _,
          b + 6,
          h,
          T,
          S
        );
        this.drawIndicatorTooltip(
          t,
          i,
          u,
          r,
          p,
          x,
          m,
          f,
          _,
          b + 1,
          P,
          T,
          w
        );
      } else if (S.tooltip.showType === Ct.Rect && w.tooltip.showType === Ct.Standard) {
        const { offsetLeft: b, offsetTop: I, offsetRight: T } = S.tooltip, P = a.width - T, M = this.drawIndicatorTooltip(
          t,
          i,
          u,
          r,
          p,
          x,
          m,
          f,
          _,
          b,
          I,
          P,
          w
        ), B = this.isDrawTooltip(
          r,
          S.tooltip
        );
        this._drawRectTooltip(
          t,
          u,
          x,
          a,
          l,
          r,
          d,
          y,
          g,
          m,
          f,
          _,
          B,
          !1,
          M,
          v
        );
      } else {
        const { offsetLeft: b, offsetTop: I, offsetRight: T } = S.tooltip, P = a.width - T, M = this._drawCandleStandardTooltip(
          t,
          u,
          i,
          r,
          p,
          d,
          y,
          g,
          m,
          f,
          _,
          b,
          I,
          P,
          S
        ), B = this.isDrawTooltip(
          r,
          w.tooltip
        );
        this._drawRectTooltip(
          t,
          u,
          x,
          a,
          l,
          r,
          d,
          y,
          g,
          m,
          f,
          _,
          !1,
          B,
          M,
          v
        );
      }
    }
  }
  _addHeading(t) {
    return { height: t + 30, left: 330 };
  }
  _drawCandleStandardTooltip(t, e, s, i, o, r, a, l, c, h, u, d, g, m, f) {
    const _ = f.tooltip, p = _.text;
    let x = 0;
    const y = { x: d, y: g };
    if (this.isDrawTooltip(i, _)) {
      const v = i.dataIndex ?? 0, S = this._getCandleTooltipLegends(
        {
          prev: e[v - 1] ?? null,
          current: i.TViewData,
          next: e[v + 1] ?? null
        },
        r,
        a,
        l,
        c,
        h,
        u,
        f
      ), [w, b, I] = this.classifyTooltipIcons(
        _.icons
      );
      x = this.drawStandardTooltipIcons(
        t,
        o,
        w,
        y,
        s,
        "",
        d,
        x,
        m
      ), x = this.drawStandardTooltipIcons(
        t,
        o,
        b,
        y,
        s,
        "",
        d,
        x,
        m
      ), S.length > 0 && (x = this.drawStandardTooltipLegends(
        t,
        S,
        y,
        d,
        x,
        m,
        p
      )), x = this.drawStandardTooltipIcons(
        t,
        o,
        I,
        y,
        s,
        "",
        d,
        x,
        m
      );
    }
    return y.y + x;
  }
  _drawRectTooltip(t, e, s, i, o, r, a, l, c, h, u, d, g, m, f, _) {
    const p = _.candle, x = _.indicator, y = p.tooltip, v = x.tooltip;
    if (g || m) {
      const S = r.dataIndex ?? 0, w = this._getCandleTooltipLegends(
        {
          prev: e[S - 1] ?? null,
          current: r.TViewData,
          next: e[S + 1] ?? null
        },
        a,
        l,
        c,
        h,
        u,
        d,
        p
      ), { offsetLeft: b, offsetTop: I, offsetRight: T, offsetBottom: P } = y, {
        marginLeft: M,
        marginRight: B,
        marginTop: X,
        marginBottom: q,
        size: R,
        weight: A,
        family: j
      } = y.text, {
        position: ht,
        paddingLeft: J,
        paddingRight: it,
        paddingTop: ut,
        paddingBottom: qt,
        offsetLeft: Et,
        offsetRight: Pt,
        offsetTop: vt,
        offsetBottom: Oe,
        borderSize: mt,
        borderRadius: Ns,
        borderColor: Ws,
        color: zs
      } = y.rect;
      let Rt = 0, pt = 0, _t = 0;
      g && (t.font = Tt(R, A, j), w.forEach((Mt) => {
        const Dt = Mt.title, St = Mt.value, $ = `${Dt.text}${St.text}`, nt = t.measureText($).width + M + B;
        Rt = Math.max(Rt, nt);
      }), _t += (q + X + R) * w.length);
      const {
        marginLeft: Ve,
        marginRight: Ne,
        marginTop: We,
        marginBottom: ze,
        size: Ot,
        weight: pe,
        family: _e
      } = v.text, Xe = [];
      if (m && (t.font = Tt(
        Ot,
        pe,
        _e
      ), s.forEach((Mt) => {
        const Dt = Mt.getIndicator(), St = this.getIndicatorTooltipData(
          e,
          r,
          Dt,
          h,
          u,
          d,
          x
        ).values ?? [];
        Xe.push(St), St.forEach(($) => {
          const nt = $.title, xe = $.value, dt = `${nt.text}${xe.text}`, gt = t.measureText(dt).width + Ve + Ne;
          Rt = Math.max(Rt, gt), _t += We + ze + Ot;
        });
      })), pt += Rt, pt !== 0 && _t !== 0) {
        pt += mt * 2 + J + it, _t += mt * 2 + ut + qt;
        const Mt = i.width / 2, Dt = ht === ns.Pointer && r.paneId === L.CANDLE, St = (r.realX ?? 0) > Mt;
        let $ = 0;
        if (Dt) {
          const gt = r.realX;
          St ? $ = gt - Pt - pt : $ = gt + Et;
        } else
          St ? ($ = Et + b, _.yAxis.inside && _.yAxis.position === Ft.Left && ($ += o.width)) : ($ = i.width - Pt - pt - T, _.yAxis.inside && _.yAxis.position === Ft.Right && ($ -= o.width));
        let nt = f + vt;
        Dt && (nt = r.y - _t / 2, nt + _t > i.height - Oe - P && (nt = i.height - Oe - _t - P), nt < f + vt && (nt = f + vt + I)), this.createFigure({
          name: "rect",
          attrs: {
            x: $,
            y: nt,
            width: pt,
            height: _t
          },
          styles: {
            style: V.StrokeFill,
            color: zs,
            borderColor: Ws,
            borderSize: mt,
            borderRadius: Ns
          }
        })?.draw(t);
        const xe = $ + mt + J + M;
        let dt = nt + mt + ut;
        if (g && w.forEach((gt) => {
          dt += X;
          const Jt = gt.title;
          this.createFigure({
            name: "text",
            attrs: {
              x: xe,
              y: dt,
              text: Jt.text
            },
            styles: {
              color: Jt.color,
              size: R,
              family: j,
              weight: A
            }
          })?.draw(t);
          const Vt = gt.value;
          this.createFigure({
            name: "text",
            attrs: {
              x: $ + pt - mt - B - it,
              y: dt,
              text: Vt.text,
              align: "right"
            },
            styles: {
              color: Vt.color,
              size: R,
              family: j,
              weight: A
            }
          })?.draw(t), dt += R + q;
        }), m) {
          const gt = $ + mt + J + Ve;
          Xe.forEach((Jt) => {
            Jt.forEach((Vt) => {
              dt += We;
              const Ye = Vt.title, He = Vt.value;
              this.createFigure({
                name: "text",
                attrs: {
                  x: gt,
                  y: dt,
                  text: Ye.text
                },
                styles: {
                  color: Ye.color,
                  size: Ot,
                  family: _e,
                  weight: pe
                }
              })?.draw(t), this.createFigure({
                name: "text",
                attrs: {
                  x: $ + pt - mt - Ne - it,
                  y: dt,
                  text: He.text,
                  align: "right"
                },
                styles: {
                  color: He.color,
                  size: Ot,
                  family: _e,
                  weight: pe
                }
              })?.draw(t), dt += Ot + ze;
            });
          });
        }
      }
    }
  }
  _getCandleTooltipLegends(t, e, s, i, o, r, a, l) {
    const c = l.tooltip, h = c.text.color, u = t.current, d = t.prev?.close ?? u.close, g = u.close - d, { price: m, volume: f } = e, _ = {
      "{time}": o.formatDate(
        s,
        u.timestamp,
        "YYYY-MM-DD HH:mm",
        U.Tooltip
      ),
      "{open}": z(
        W(
          N(u.open, m),
          r
        ),
        a
      ),
      "{high}": z(
        W(
          N(u.high, m),
          r
        ),
        a
      ),
      "{low}": z(
        W(
          N(u.low, m),
          r
        ),
        a
      ),
      "{close}": z(
        W(
          N(u.close, m),
          r
        ),
        a
      ),
      "{volume}": z(
        W(
          o.formatBigNumber(
            N(
              u.volume ?? c.defaultValue,
              f
            )
          ),
          r
        ),
        a
      ),
      "{turnover}": z(
        W(
          N(
            u.turnover ?? c.defaultValue,
            m
          ),
          r
        ),
        a
      ),
      "{change}": d === 0 ? c.defaultValue : `${W(N(g / d * 100), r)}%`
    };
    return ((lt(c.custom) ? c.custom(t, l) : c.custom) ?? []).map(({ title: x, value: y }) => {
      let v = { text: "", color: "" };
      at(x) ? v = { ...x } : (v.text = x, v.color = h), v.text = Bn(v.text, i);
      let S = {
        text: c.defaultValue,
        color: ""
      };
      at(y) ? S = { ...y } : (S.text = y, S.color = h);
      const w = S.text.match(/{(\S*)}/);
      if (w !== null && w.length > 1) {
        const b = `{${w[1]}}`;
        S.text = S.text.replace(
          b,
          _[b] ?? c.defaultValue
        ), b === "{change}" && (S.color = g === 0 ? l.priceMark.last.noChangeColor : g > 0 ? l.priceMark.last.upColor : l.priceMark.last.downColor);
      }
      return { title: v, value: S };
    });
  }
}
class On extends ge {
  constructor() {
    super(...arguments), this._boundCandleBarClickEvent = (t) => () => (this.getWidget().getPane().getChart().getChartStore().getActionStore().execute(et.OnCandleBarClick, t), !1);
  }
  drawImp(t) {
    const e = this.getWidget().getPane(), s = e.getId() === L.CANDLE, i = e.getChart().getChartStore(), o = i.getDataList(), r = i.getVisibleDataList(), a = this._calculateHeikinAshi(o), l = this.getCandleBarOptions(i), c = i.getTimeScaleStore().getBarSpace();
    if (l !== null) {
      const h = e.getAxisComponent();
      r.length > 0 && r.map((d) => {
        const g = a.find(
          (m) => m.timestamp === d?.data?.timestamp
        );
        return g ? { data: g, dataIndex: d.dataIndex, x: d.x } : d;
      }).forEach((d) => {
        const { data: g, x: m } = d;
        if (C(g)) {
          const { open: f, high: _, low: p, close: x } = g, { styles: y } = l, v = [];
          x > f ? (v[0] = y.upColor, v[1] = y.upBorderColor, v[2] = y.upWickColor) : x < f ? (v[0] = y.downColor, v[1] = y.downBorderColor, v[2] = y.downWickColor) : (v[0] = y.noChangeColor, v[1] = y.noChangeBorderColor, v[2] = y.noChangeWickColor);
          const S = h.convertToPixel(f), w = h.convertToPixel(x), b = [
            S,
            w,
            h.convertToPixel(_),
            h.convertToPixel(p)
          ];
          b.sort((T, P) => T - P);
          let I = [];
          I = this._createSolidBar(m, b, c, v), I.forEach((T) => {
            let P;
            s && (P = {
              mouseClickEvent: this._boundCandleBarClickEvent(d)
            }), this.createFigure(T, P)?.draw(t);
          });
        }
      });
    }
  }
  getCandleBarOptions(t) {
    const e = t.getStyles().candle;
    return {
      type: O.HeikinAshi,
      styles: e.bar
    };
  }
  _createSolidBar(t, e, s, i) {
    return [
      {
        name: "rect",
        attrs: {
          x: t,
          y: e[0],
          width: 1,
          height: e[3] - e[0]
        },
        styles: { color: i[2] }
      },
      {
        name: "rect",
        attrs: {
          x: t - s.halfGapBar,
          y: e[1],
          width: s.gapBar,
          height: Math.max(1, e[2] - e[1])
        },
        styles: {
          style: V.StrokeFill,
          color: i[0],
          borderColor: i[1]
        }
      }
    ];
  }
  _calculateHeikinAshi(t) {
    const e = [];
    for (let s = 0; s < t.length; s++) {
      const i = t[s];
      let o, r, a, l;
      if (s === 0)
        o = (i.open + i.close) / 2, r = (i.open + i.high + i.low + i.close) / 4, a = i.high, l = i.low;
      else {
        const c = e[s - 1];
        o = (c.open + c.close) / 2, r = (i.open + i.high + i.low + i.close) / 4, a = Math.max(i.high, o, r), l = Math.min(i.low, o, r);
      }
      e.push({
        open: o,
        high: a,
        low: l,
        close: r,
        timestamp: i.timestamp,
        volume: i.volume,
        turnover: i.turnover
      });
    }
    return e;
  }
}
class Vn extends Ds {
  constructor(t, e) {
    super(t, e), this._candleBarView = new Es(this), this._candleHeikinAshiView = new On(this), this._candleAreaView = new Dn(this), this._candleHighLowPriceView = new An(this), this._candleLastPriceLineView = new kn(this), this.addChild(this._candleBarView);
  }
  updateMainContent(t) {
    const e = this.getPane().getChart().getStyles().candle;
    e.type !== O.Area && e.type !== O.Line && e.type !== O.LineMark && e.type !== O.StepLine ? (e.type === O.HeikinAshi ? this._candleHeikinAshiView.draw(t) : this._candleBarView.draw(t), this._candleHighLowPriceView.draw(t), this._candleAreaView.stopAnimation()) : (e.type === O.Area || e.type === O.Line || e.type === O.LineMark || e.type === O.StepLine) && this._candleAreaView.draw(t), this._candleLastPriceLineView.draw(t);
  }
  createTooltipView() {
    return new Rn(this);
  }
}
class As extends ct {
  drawImp(t) {
    const e = this.getWidget(), s = e.getPane(), i = e.getBounding(), o = s.getAxisComponent(), r = this.getAxisStyles(s.getChart().getStyles());
    if (r.show) {
      r.axisLine.show && this.createFigure({
        name: "line",
        attrs: this.createAxisLine(i, r),
        styles: r.axisLine
      })?.draw(t);
      const a = o.getTicks();
      if (r.tictView.show && this.createTictViews(a, i, r).forEach((c) => {
        this.createFigure({
          name: "line",
          attrs: c,
          styles: r.tictView
        })?.draw(t);
      }), r.tickText.show) {
        const l = this.createTickTexts(a, i, r);
        this.createFigure({
          name: "text",
          attrs: l,
          styles: r.tickText
        })?.draw(t);
      }
    }
  }
}
class Nn extends As {
  getAxisStyles(t) {
    return t.yAxis;
  }
  createAxisLine(t, e) {
    const s = this.getWidget().getPane().getAxisComponent(), i = e.axisLine.size;
    let o;
    return s.isFromZero() ? o = 0 : o = t.width - i, {
      coordinates: [
        { x: o, y: 0 },
        { x: o, y: t.height }
      ]
    };
  }
  createTictViews(t, e, s) {
    const i = this.getWidget().getPane().getAxisComponent(), o = s.axisLine, r = s.tictView;
    let a = 0, l = 0;
    return i.isFromZero() ? (a = 0, o.show && (a += o.size), l = a + r.length) : (a = e.width, o.show && (a -= o.size), l = a - r.length), t.map((c) => ({
      coordinates: [
        { x: a, y: c.coord },
        { x: l, y: c.coord }
      ]
    }));
  }
  createTickTexts(t, e, s) {
    const i = this.getWidget().getPane().getAxisComponent(), o = s.axisLine, r = s.tictView, a = s.tickText;
    let l = 0;
    i.isFromZero() ? (l = a.marginStart, o.show && (l += o.size), r.show && (l += r.length)) : (l = e.width - a.marginEnd, o.show && (l -= o.size), r.show && (l -= r.length));
    const c = this.getWidget().getPane().getAxisComponent().isFromZero() ? "left" : "right";
    return t.map((h) => ({
      x: l,
      y: h.coord,
      text: h.text,
      align: c,
      baseline: "middle"
    }));
  }
}
class Wn extends ct {
  drawImp(t) {
    const e = this.getWidget(), s = e.getPane(), i = e.getBounding(), o = s.getChart().getChartStore(), r = o.getStyles().candle.priceMark, a = r.last, l = a.text;
    if (r.show && a.show && l.show) {
      const c = o.getPrecision(), h = s.getAxisComponent(), u = o.getDataList(), d = u[u.length - 1];
      if (C(d)) {
        const { close: g, open: m } = d, f = h.convertToNicePixel(g);
        let _;
        g > m ? _ = a.upColor : g < m ? _ = a.downColor : _ = a.noChangeColor;
        let p;
        if (h.getType() === G.Percentage) {
          const S = o.getVisibleFirstData().close;
          p = `${((g - S) / S * 100).toFixed(2)}%`;
        } else
          p = N(g, c.price);
        p = z(
          W(p, o.getThousandsSeparator()),
          o.getDecimalFoldThreshold()
        );
        let x, y;
        h.isFromZero() ? (x = 0, y = "left") : (x = i.width, y = "right"), this.createFigure({
          name: "text",
          attrs: {
            x,
            y: f,
            text: p,
            align: y,
            baseline: "middle"
          },
          styles: {
            ...l,
            backgroundColor: _
          }
        })?.draw(t);
      }
    }
  }
}
class zn extends ct {
  drawImp(t) {
    const e = this.getWidget(), s = e.getPane(), i = e.getBounding(), o = s.getChart().getChartStore(), r = o.getCustomApi(), a = o.getStyles().indicator, l = a.lastValueMark, c = l.text;
    if (l.show) {
      const h = s.getAxisComponent(), u = o.getDataList(), d = u.length - 1, g = o.getIndicatorStore().getInstances(s.getId()), m = o.getThousandsSeparator(), f = o.getDecimalFoldThreshold();
      g.forEach((_) => {
        const p = _.getIndicator(), y = p.result[d];
        if (C(y) && p.visible) {
          const v = p.precision;
          De(
            u,
            p,
            d,
            a,
            (S, w) => {
              const b = y[S.key];
              if (E(b)) {
                const I = h.convertToNicePixel(b);
                let T = N(b, v);
                p.shouldFormatBigNumber && (T = r.formatBigNumber(T)), T = z(
                  W(T, m),
                  f
                );
                let P, M;
                h.isFromZero() ? (P = 0, M = "left") : (P = i.width, M = "right"), this.createFigure({
                  name: "text",
                  attrs: {
                    x: P,
                    y: I,
                    text: T,
                    align: M,
                    baseline: "middle"
                  },
                  styles: {
                    ...c,
                    backgroundColor: w.color
                  }
                })?.draw(t);
              }
            }
          );
        }
      });
    }
  }
}
class ks extends Ms {
  coordinateToPointTimestampDataIndexFlag() {
    return !1;
  }
  drawDefaultFigures(t, e, s, i, o, r, a, l, c, h, u, d, g, m) {
    this.drawFigures(
      t,
      e,
      this.getDefaultFigures(
        e.getOverlay(),
        s,
        i,
        o,
        r,
        a,
        l,
        c,
        u,
        d,
        m
      ),
      h
    );
  }
  getDefaultFigures(t, e, s, i, o, r, a, l, c, h, u) {
    const d = [];
    if (t.needDefaultYAxisFigure && t.id === u.instance?.getOverlay().id && u.paneId === this.getWidget().getPane().getId()) {
      let g = Number.MAX_SAFE_INTEGER, m = Number.MIN_SAFE_INTEGER;
      const f = h?.isFromZero() ?? !1;
      let _, p;
      f ? (_ = "left", p = 0) : (_ = "right", p = s.width), e.forEach((x, y) => {
        const v = t.points[y];
        if (E(v.value)) {
          g = Math.min(g, x.y), m = Math.max(m, x.y);
          const S = z(
            W(
              N(v.value, i.price),
              a
            ),
            l
          );
          d.push({
            type: "text",
            attrs: {
              x: p,
              y: x.y,
              text: S,
              align: _,
              baseline: "middle"
            },
            ignoreEvent: !0
          });
        }
      }), e.length > 1 && d.unshift({
        type: "rect",
        attrs: {
          x: 0,
          y: g,
          width: s.width,
          height: m - g
        },
        ignoreEvent: !0
      });
    }
    return d;
  }
  getFigures(t, e, s, i, o, r, a, l, c, h, u) {
    return t.createYAxisFigures?.({
      overlay: t,
      coordinates: e,
      bounding: s,
      barSpace: i,
      precision: o,
      thousandsSeparator: r,
      decimalFoldThreshold: a,
      dateTimeFormat: l,
      defaultStyles: c,
      xAxis: h,
      yAxis: u
    }) ?? [];
  }
}
class Fs extends ct {
  drawImp(t) {
    const e = this.getWidget(), s = e.getPane(), i = e.getBounding(), o = e.getPane().getChart().getChartStore(), r = o.getTooltipStore().getCrosshair(), a = o.getStyles().crosshair;
    if (D(r.paneId) && this.compare(r, s.getId()) && a.show) {
      const l = this.getDirectionStyles(a), c = l.text;
      if (l.show && c.show) {
        const h = s.getAxisComponent(), u = this.getText(r, o, h);
        t.font = Tt(
          c.size,
          c.weight,
          c.family
        ), this.createFigure({
          name: "text",
          attrs: this.getTextAttrs(
            u,
            t.measureText(u).width,
            r,
            i,
            h,
            c
          ),
          styles: c
        })?.draw(t);
      }
    }
  }
  compare(t, e) {
    return t.paneId === e;
  }
  getDirectionStyles(t) {
    return t.horizontal;
  }
  getText(t, e, s) {
    const i = s, o = s.convertFromPixel(t.y);
    let r;
    if (i.getType() === G.Percentage) {
      const a = e.getVisibleFirstData();
      r = `${((o - a.close) / a.close * 100).toFixed(2)}%`;
    } else {
      const a = e.getIndicatorStore().getInstances(t.paneId);
      let l = 0, c = !1;
      i.isInCandle() ? l = e.getPrecision().price : a.forEach((h) => {
        const u = h.getIndicator();
        l = Math.max(u.precision, l), c || (c = u.shouldFormatBigNumber);
      }), r = N(o, l), c && (r = e.getCustomApi().formatBigNumber(r));
    }
    return z(
      W(r, e.getThousandsSeparator()),
      e.getDecimalFoldThreshold()
    );
  }
  getTextAttrs(t, e, s, i, o, r) {
    const a = o;
    let l, c;
    return a.isFromZero() ? (l = 1, c = "left") : (l = i.width, c = "right"), { x: l, y: s.y, text: t, align: c, baseline: "middle" };
  }
}
class Xn extends ct {
  drawImp(t) {
    const e = this.getWidget(), s = e.getPane(), i = e.getBounding(), o = s.getChart().getChartStore(), r = o.getStyles().candle.visiblePriceMark, a = o.getStyles().xAxis.axisLine.color, l = r.last, c = l.text;
    if (r.show && l.show && c.show) {
      const h = o.getPrecision(), u = s.getAxisComponent(), d = o.getVisibleLastData();
      if (C(d)) {
        const { close: g, open: m } = d, f = u.convertToNicePixel(g);
        let _;
        g > m ? _ = l.upColor : g < m ? _ = l.downColor : _ = l.noChangeColor;
        let p;
        if (u.getType() === G.Percentage) {
          const S = o.getVisibleFirstData().close;
          p = `${((g - S) / S * 100).toFixed(2)}%`;
        } else
          p = N(g, h.price);
        p = z(
          W(p, o.getThousandsSeparator()),
          o.getDecimalFoldThreshold()
        );
        let x, y;
        u.isFromZero() ? (x = 0, y = "left") : (x = i.width, y = "right"), this.createFigure({
          name: "text",
          attrs: {
            x,
            y: f,
            text: p,
            align: y,
            baseline: "middle"
          },
          styles: {
            ...c,
            color: _,
            borderColor: _,
            backgroundColor: a
          }
        })?.draw(t);
      }
    }
  }
}
class Yn extends Le {
  constructor(t, e) {
    super(t, e), this._yAxisView = new Nn(this), this._candleLastPriceLabelView = new Wn(
      this
    ), this._candleVisibleLastPriceLabelView = new Xn(this), this._indicatorLastValueView = new zn(this), this._overlayYAxisView = new ks(this), this._crosshairHorizontalLabelView = new Fs(this), this.getContainer().style.cursor = "ns-resize", this.addChild(this._overlayYAxisView);
  }
  getName() {
    return k.Y_AXIS;
  }
  updateMain(t) {
    this._yAxisView.draw(t), this.getPane().getAxisComponent().isInCandle() && (this._candleLastPriceLabelView.draw(t), this._candleVisibleLastPriceLabelView.draw(t)), this._indicatorLastValueView.draw(t);
  }
  updateOverlay(t) {
    this._overlayYAxisView.draw(t), this._crosshairHorizontalLabelView.draw(t);
  }
}
class Ls {
  constructor(t, e, s, i) {
    this._bounding = ms(), this._chart = s, this._id = i, this._init(t, e);
  }
  _init(t, e) {
    this._rootContainer = t, this._container = ft("div", {
      width: "100%",
      margin: "0",
      padding: "0",
      position: "relative",
      overflow: "hidden",
      boxSizing: "border-box"
    }), e !== null ? t.insertBefore(this._container, e) : t.appendChild(this._container);
  }
  getContainer() {
    return this._container;
  }
  getId() {
    return this._id;
  }
  getChart() {
    return this._chart;
  }
  getBounding() {
    return this._bounding;
  }
  update(t) {
    this._bounding.height !== this._container.clientHeight && (this._container.style.height = `${this._bounding.height}px`), this.updateImp(
      t ?? F.Drawer,
      this._container,
      this._bounding
    );
  }
  destroy() {
    this._rootContainer.removeChild(this._container);
  }
}
class Bs extends Ls {
  constructor(t, e, s, i, o) {
    super(t, e, s, i), this._yAxisWidget = null, this._options = {
      minHeight: rn,
      dragEnabled: !0,
      gap: { top: 0.2, bottom: 0.1 },
      axisOptions: { name: "default", scrollZoomEnabled: !0 }
    };
    const r = this.getContainer();
    this._mainWidget = this.createMainWidget(r), this._yAxisWidget = this.createYAxisWidget(r), this.setOptions(o);
  }
  setOptions(t) {
    const e = t.axisOptions?.name;
    (this._options.axisOptions.name !== e && D(e) || !C(this._axis)) && (this._axis = this.createAxisComponent(e ?? "default")), tt(this._options, t);
    let s, i;
    return this.getId() === L.X_AXIS ? (s = this.getMainWidget().getContainer(), i = "ew-resize") : (s = this.getYAxisWidget().getContainer(), i = "ns-resize"), t.axisOptions?.scrollZoomEnabled ?? !0 ? s.style.cursor = i : s.style.cursor = "default", this;
  }
  getOptions() {
    return this._options;
  }
  getAxisComponent() {
    return this._axis;
  }
  setBounding(t, e, s) {
    tt(this.getBounding(), t);
    const i = {};
    return C(t.height) && (i.height = t.height), C(t.top) && (i.top = t.top), this._mainWidget.setBounding(i), this._yAxisWidget?.setBounding(i), C(e) && this._mainWidget.setBounding(e), C(s) && this._yAxisWidget?.setBounding(s), this;
  }
  getMainWidget() {
    return this._mainWidget;
  }
  getYAxisWidget() {
    return this._yAxisWidget;
  }
  updateImp(t) {
    this._mainWidget.update(t), this._yAxisWidget?.update(t);
  }
  destroy() {
    super.destroy(), this._mainWidget.destroy(), this._yAxisWidget?.destroy();
  }
  getImage(t) {
    const { width: e, height: s } = this.getBounding(), i = ft("canvas", {
      width: `${e}px`,
      height: `${s}px`,
      boxSizing: "border-box"
    }), o = i.getContext("2d"), r = yt(i);
    i.width = e * r, i.height = s * r, o.scale(r, r);
    const a = this._mainWidget.getBounding();
    if (o.drawImage(
      this._mainWidget.getImage(t),
      a.left,
      0,
      a.width,
      a.height
    ), this._yAxisWidget !== null) {
      const l = this._yAxisWidget.getBounding();
      o.drawImage(
        this._yAxisWidget.getImage(t),
        l.left,
        0,
        l.width,
        l.height
      );
    }
    return i;
  }
  /* eslint-disable @typescript-eslint/no-unused-vars */
  createYAxisWidget(t) {
    return null;
  }
}
class Rs {
  constructor(t) {
    this._range = {
      from: 0,
      to: 0,
      range: 0,
      realFrom: 0,
      realTo: 0,
      realRange: 0
    }, this._extremum = {
      min: 0,
      max: 0,
      range: 0,
      realMin: 0,
      realMax: 0,
      realRange: 0
    }, this._prevRange = {
      from: 0,
      to: 0,
      range: 0,
      realFrom: 0,
      realTo: 0,
      realRange: 0
    }, this._ticks = [], this._autoCalcTickFlag = !0, this._parent = t;
  }
  getParent() {
    return this._parent;
  }
  buildTicks(t) {
    if (this._autoCalcTickFlag && (this._range = this.calcRange()), this._prevRange.from !== this._range.from || this._prevRange.to !== this._range.to || t) {
      this._prevRange = this._range;
      const e = this.optimalTicks(this._calcTicks());
      return this._ticks = this.createTicks({
        range: this._range,
        bounding: this.getSelfBounding(),
        defaultTicks: e
      }), !0;
    }
    return !1;
  }
  getTicks() {
    return this._ticks;
  }
  getScrollZoomEnabled() {
    return this.getParent().getOptions().axisOptions.scrollZoomEnabled ?? !0;
  }
  setRange(t) {
    this._autoCalcTickFlag = !1, this._range = t;
  }
  setExtremum(t) {
    this.getParent().getChart().getChartStore().getYScrolling() && (this._autoCalcTickFlag = !1), this._extremum = t;
  }
  getExtremum() {
    return this._extremum;
  }
  getRange() {
    return this._range;
  }
  setAutoCalcTickFlag(t) {
    this._autoCalcTickFlag = t;
  }
  getAutoCalcTickFlag() {
    return this._autoCalcTickFlag;
  }
  _calcTicks() {
    const { realFrom: t, realTo: e, realRange: s } = this._range, i = [];
    if (s >= 0) {
      const [o, r] = this._calcTickInterval(s), a = Ke(Math.ceil(t / o) * o, r), l = Ke(Math.floor(e / o) * o, r);
      let c = 0, h = a;
      if (o !== 0)
        for (; h <= l; ) {
          const u = h.toFixed(r);
          i[c] = { text: u, coord: 0, value: u }, ++c, h += o;
        }
    }
    return i;
  }
  _calcTickInterval(t) {
    if (this.getParent().getMainWidget().getName() === "xAxis") {
      const e = Ze(t / 8), s = qe(e);
      return [e, s];
    } else {
      const e = Ze(t / 18), s = qe(e);
      return [e, s];
    }
  }
}
class fe extends Rs {
  calcRange() {
    const t = this.getParent(), e = t.getChart(), s = e.getChartStore();
    let i = Number.MAX_SAFE_INTEGER, o = Number.MIN_SAFE_INTEGER;
    const r = [];
    let a = !1, l = Number.MAX_SAFE_INTEGER, c = Number.MIN_SAFE_INTEGER, h = Number.MAX_SAFE_INTEGER;
    s.getIndicatorStore().getInstances(t.getId()).forEach((R) => {
      const A = R.getIndicator();
      a || (a = A.shouldOhlc ?? !1), h = Math.min(h, A.precision), E(A.minValue) && (l = Math.min(l, A.minValue)), E(A.maxValue) && (c = Math.max(c, A.maxValue)), r.push({
        figures: A.figures ?? [],
        result: A.result ?? []
      });
    });
    let d = 4;
    const g = this.isInCandle();
    if (g) {
      const { price: R } = s.getPrecision();
      h !== Number.MAX_SAFE_INTEGER ? d = Math.min(h, R) : d = R;
    } else
      h !== Number.MAX_SAFE_INTEGER && (d = h);
    const m = s.getVisibleDataList(), f = e.getStyles().candle, _ = f.type === O.Area, p = f.type === O.Line, x = f.type === O.LineMark, y = _ ? f.area.value : f.line.value, v = g && !_ || !g && a || g && !p || g && !x;
    m.forEach(({ dataIndex: R, data: A }) => {
      if (C(A) && (v && (i = Math.min(i, A.low), o = Math.max(o, A.high)), g && _ || g && p || g && x)) {
        const j = A[y];
        E(j) && (i = Math.min(i, j), o = Math.max(o, j));
      }
      r.forEach(({ figures: j, result: ht }) => {
        const J = ht[R] ?? {};
        j.forEach((it) => {
          const ut = J[it.key];
          E(ut) && (i = Math.min(i, ut), o = Math.max(o, ut));
        });
      });
    }), i !== Number.MAX_SAFE_INTEGER && o !== Number.MIN_SAFE_INTEGER ? (i = Math.min(l, i), o = Math.max(c, o)) : (i = 0, o = 10);
    const S = this.getType();
    let w;
    switch (S) {
      case G.Percentage: {
        const R = s.getVisibleFirstData();
        C(R) && E(R.close) && (i = (i - R.close) / R.close * 100, o = (o - R.close) / R.close * 100), w = Math.pow(10, -2);
        break;
      }
      case G.Log: {
        i = Ht(i), o = Ht(o), w = 0.05 * wt(-d);
        break;
      }
      default:
        w = wt(-d);
    }
    if (i === o || Math.abs(i - o) < w) {
      const R = l === i, A = c === o;
      i = R ? i : A ? i - 8 * w : i - 4 * w, o = A ? o : R ? o + 8 * w : o + 4 * w;
    }
    const b = this.getParent().getYAxisWidget()?.getBounding().height ?? 0, { gap: I } = t.getOptions();
    let T = I?.top ?? 0.2;
    T >= 1 && (T = T / b);
    let P = I?.bottom ?? 0.1;
    P >= 1 && (P = P / b);
    let M = Math.abs(o - i);
    i = i - M * P, o = o + M * T, M = Math.abs(o - i);
    let B, X, q;
    return S === G.Log ? (B = wt(i), X = wt(o), q = Math.abs(X - B)) : (B = i, X = o, q = M), {
      from: i,
      to: o,
      range: M,
      realFrom: B,
      realTo: X,
      realRange: q
    };
  }
  /**
   * 内部值转换成坐标
   * @param value
   * @return {number}
   * @private
   */
  _innerConvertToPixel(t) {
    const e = this.getParent().getYAxisWidget()?.getBounding().height ?? 0, { from: s, range: i } = this.getRange(), o = (t - s) / i;
    return this.isReverse() ? Math.round(o * e) : Math.round((1 - o) * e);
  }
  /**
   * 是否是蜡烛图轴
   * @return {boolean}
   */
  isInCandle() {
    return this.getParent().getId() === L.CANDLE;
  }
  /**
   * y轴类型
   * @return {YAxisType}
   */
  getType() {
    return this.isInCandle() ? this.getParent().getChart().getStyles().yAxis.type : G.Normal;
  }
  getPosition() {
    return this.getParent().getChart().getStyles().yAxis.position;
  }
  /**
   * 是否反转
   * @return {boolean}
   */
  isReverse() {
    return this.isInCandle() ? this.getParent().getChart().getStyles().yAxis.reverse : !1;
  }
  /**
   * 是否从y轴0开始
   * @return {boolean}
   */
  isFromZero() {
    const t = this.getParent().getChart().getStyles().yAxis, e = t.inside;
    return t.position === Ft.Left && e || t.position === Ft.Right && !e;
  }
  optimalTicks(t) {
    const e = this.getParent(), s = e.getYAxisWidget()?.getBounding().height ?? 0, i = e.getChart().getChartStore(), o = i.getCustomApi(), r = [], a = this.getType(), l = i.getIndicatorStore().getInstances(e.getId()), c = i.getThousandsSeparator(), h = i.getDecimalFoldThreshold();
    let u = 0, d = !1;
    this.isInCandle() ? u = i.getPrecision().price : l.forEach((f) => {
      const _ = f.getIndicator();
      u = Math.max(u, _.precision), d || (d = _.shouldFormatBigNumber);
    });
    const g = i.getStyles().xAxis.tickText.size;
    let m;
    return t.forEach(({ value: f }) => {
      let _, p = this._innerConvertToPixel(+f);
      switch (a) {
        case G.Percentage: {
          _ = `${N(f, 2)}%`;
          break;
        }
        case G.Log: {
          p = this._innerConvertToPixel(Ht(+f)), _ = N(f, u);
          break;
        }
        default: {
          _ = N(f, u), d && (_ = o.formatBigNumber(f));
          break;
        }
      }
      _ = z(
        W(_, c),
        h
      );
      const x = E(m);
      p > g && p < s - g && (x && Math.abs(m - p) > g * 2 || !x) && (r.push({ text: _, coord: p, value: f }), m = p);
    }), r;
  }
  getAutoSize() {
    const t = this.getParent(), e = t.getChart(), s = e.getStyles(), i = s.yAxis, o = i.size;
    if (o !== "auto")
      return o;
    const r = e.getChartStore(), a = r.getCustomApi();
    let l = 0;
    if (i.show && (i.axisLine.show && (l += i.axisLine.size), i.tictView.show && (l += i.tictView.length), i.tickText.show)) {
      let u = 0;
      this.getTicks().forEach((d) => {
        u = Math.max(
          u,
          jt(
            d.text,
            i.tickText.size,
            i.tickText.weight,
            i.tickText.family
          )
        );
      }), l += i.tickText.marginStart + i.tickText.marginEnd + u;
    }
    const c = s.crosshair;
    let h = 0;
    if (c.show && c.horizontal.show && c.horizontal.text.show) {
      const u = r.getIndicatorStore().getInstances(t.getId());
      let d = 0, g = !1;
      u.forEach((_) => {
        const p = _.getIndicator();
        d = Math.max(p.precision, d), g || (g = p.shouldFormatBigNumber);
      });
      let m = 2;
      if (this.getType() !== G.Percentage)
        if (this.isInCandle()) {
          const { price: _ } = r.getPrecision(), p = s.indicator.lastValueMark;
          p.show && p.text.show ? m = Math.max(d, _) : m = _;
        } else
          m = d;
      let f = N(this.getRange().to, m);
      g && (f = a.formatBigNumber(f)), f = z(
        f,
        r.getDecimalFoldThreshold()
      ), h += c.horizontal.text.paddingLeft + c.horizontal.text.paddingRight + c.horizontal.text.borderSize * 2 + jt(
        f,
        c.horizontal.text.size,
        c.horizontal.text.weight,
        c.horizontal.text.family
      );
    }
    return Math.max(l, h);
  }
  getSelfBounding() {
    return this.getParent().getYAxisWidget().getBounding();
  }
  convertFromPixel(t) {
    const e = this.getParent().getYAxisWidget()?.getBounding().height ?? 0, { from: s, range: i } = this.getRange(), r = (this.isReverse() ? t / e : 1 - t / e) * i + s;
    switch (this.getType()) {
      case G.Percentage: {
        const a = this.getParent().getChart().getChartStore().getVisibleFirstData();
        return C(a) && E(a.close) ? a.close * r / 100 + a.close : 0;
      }
      case G.Log:
        return wt(r);
      default:
        return r;
    }
  }
  convertToRealValue(t) {
    let e = t;
    return this.getType() === G.Log && (e = wt(t)), e;
  }
  convertToPixel(t) {
    let e = t;
    switch (this.getType()) {
      case G.Percentage: {
        const s = this.getParent().getChart().getChartStore().getVisibleFirstData();
        C(s) && E(s.close) && (e = (t - s.close) / s.close * 100);
        break;
      }
      case G.Log: {
        e = Ht(t);
        break;
      }
      default:
        e = t;
    }
    return this._innerConvertToPixel(e);
  }
  convertToNicePixel(t) {
    const e = this.getParent().getYAxisWidget()?.getBounding().height ?? 0, s = this.convertToPixel(t);
    return Math.round(Math.max(e * 0.05, Math.min(s, e * 0.98)));
  }
  static extend(t) {
    class e extends fe {
      createTicks(i) {
        return t.createTicks(i);
      }
    }
    return e;
  }
}
const Hn = {
  name: "default",
  createTicks: ({ defaultTicks: n }) => n
}, Pe = {
  default: fe.extend(Hn)
};
function yo(n) {
  Pe[n.name] = fe.extend(n);
}
function $n(n) {
  return Pe[n] ?? Pe.default;
}
class Os extends Bs {
  createAxisComponent(t) {
    const e = $n(t ?? "default");
    return new e(this);
  }
  createMainWidget(t) {
    return new Ds(t, this);
  }
  createYAxisWidget(t) {
    return new Yn(t, this);
  }
}
class Gn extends Os {
  createMainWidget(t) {
    return new Vn(t, this);
  }
}
class jn extends As {
  getAxisStyles(t) {
    return t.xAxis;
  }
  createAxisLine(t) {
    return {
      coordinates: [
        { x: 0, y: 0 },
        { x: t.width, y: 0 }
      ]
    };
  }
  createTictViews(t, e, s) {
    const i = s.tictView, o = s.axisLine.size;
    return t.map((r) => ({
      coordinates: [
        { x: r.coord, y: 0 },
        { x: r.coord, y: o + i.length }
      ]
    }));
  }
  createTickTexts(t, e, s) {
    const i = s.tickText, o = s.axisLine.size, r = s.tictView.length;
    return t.map((a) => ({
      x: a.coord,
      y: o + r + i.marginStart,
      text: a.text,
      align: "center",
      baseline: "top"
    }));
  }
}
class Un extends ks {
  coordinateToPointTimestampDataIndexFlag() {
    return !0;
  }
  coordinateToPointValueFlag() {
    return !1;
  }
  getCompleteOverlays(t) {
    return t.getInstances();
  }
  getProgressOverlay(t) {
    return t.instance;
  }
  getDefaultFigures(t, e, s, i, o, r, a, l, c, h, u) {
    const d = [];
    if (t.needDefaultXAxisFigure && t.id === u.instance?.getOverlay().id) {
      let g = Number.MAX_SAFE_INTEGER, m = Number.MIN_SAFE_INTEGER;
      e.forEach((f, _) => {
        g = Math.min(g, f.x), m = Math.max(m, f.x);
        const p = t.points[_];
        if (E(p.timestamp)) {
          const x = r.formatDate(
            o,
            p.timestamp,
            "YYYY-MM-DD HH:mm",
            U.Crosshair
          );
          d.push({
            type: "text",
            attrs: { x: f.x, y: 0, text: x, align: "center" },
            ignoreEvent: !0
          });
        }
      }), e.length > 1 && d.unshift({
        type: "rect",
        attrs: {
          x: g,
          y: 0,
          width: m - g,
          height: s.height
        },
        ignoreEvent: !0
      });
    }
    return d;
  }
  getFigures(t, e, s, i, o, r, a, l, c, h, u) {
    return t.createXAxisFigures?.({
      overlay: t,
      coordinates: e,
      bounding: s,
      barSpace: i,
      precision: o,
      thousandsSeparator: r,
      decimalFoldThreshold: a,
      dateTimeFormat: l,
      defaultStyles: c,
      xAxis: h,
      yAxis: u
    }) ?? [];
  }
}
class Zn extends Fs {
  compare(t) {
    return C(t.TViewData) && t.dataIndex === t.realDataIndex;
  }
  getDirectionStyles(t) {
    return t.vertical;
  }
  getText(t, e) {
    const s = t.TViewData?.timestamp;
    return e.getCustomApi().formatDate(
      e.getTimeScaleStore().getDateTimeFormat(),
      s,
      "YYYY-MM-DD HH:mm",
      U.Crosshair
    );
  }
  getTextAttrs(t, e, s, i, o, r) {
    const a = s.realX;
    let l, c = "center";
    return a - e / 2 - r.paddingLeft < 0 ? (l = 0, c = "left") : a + e / 2 + r.paddingRight > i.width ? (l = i.width, c = "right") : l = a, { x: l, y: 1, text: t, align: c, baseline: "top" };
  }
}
class Kn extends Le {
  constructor(t, e) {
    super(t, e), this._xAxisView = new jn(this), this._overlayXAxisView = new Un(this), this._crosshairVerticalLabelView = new Zn(
      this
    ), this.getContainer().style.cursor = "ew-resize", this.addChild(this._overlayXAxisView);
  }
  getName() {
    return k.X_AXIS;
  }
  updateMain(t) {
    this._xAxisView.draw(t);
  }
  updateOverlay(t) {
    this._overlayXAxisView.draw(t), this._crosshairVerticalLabelView.draw(t);
  }
}
class me extends Rs {
  calcRange() {
    const t = this.getParent().getChart().getChartStore(), { from: e, to: s } = t.getTimeScaleStore().getVisibleRange(), i = e, o = s - 1, r = s - e;
    return {
      from: i,
      to: o,
      range: r,
      realFrom: i,
      realTo: o,
      realRange: r
    };
  }
  optimalTicks(t) {
    const e = this.getParent().getChart(), s = e.getChartStore(), i = s.getCustomApi().formatDate, o = [], r = t.length, a = s.getDataList();
    if (r > 0) {
      const l = s.getTimeScaleStore().getDateTimeFormat(), c = e.getStyles().xAxis.tickText, h = jt(
        "00-00 00:00",
        c.size,
        c.weight,
        c.family
      ), u = parseInt(t[0].value, 10), d = this.convertToPixel(u);
      let g = 1;
      if (r > 1) {
        const f = parseInt(t[1].value, 10), _ = this.convertToPixel(f), p = Math.abs(_ - d);
        p < h && (g = Math.ceil(h / p));
      }
      for (let f = 0; f < r; f += g) {
        const _ = parseInt(t[f].value, 10), x = a[_].timestamp;
        let y = i(
          l,
          x,
          "HH:mm",
          U.XAxis
        );
        if (f !== 0) {
          const S = parseInt(t[f - g].value, 10), b = a[S].timestamp;
          y = this._optimalTickLabel(
            i,
            l,
            x,
            b
          ) ?? y;
        }
        const v = this.convertToPixel(_);
        if (o.push({ text: y, coord: v, value: x }), o.length > 2 && f === r - 1 * g) {
          const S = o[o.length - 1], w = Number(S.value) - Number(o[o.length - 2].value), b = S.coord - o[o.length - 2].coord;
          for (let I = 1; I < 10; I += 1)
            o.push({
              text: this._optimalTickLabel(
                i,
                l,
                Number(S.value) + Number(I * w),
                Number(S.value)
              ) ?? y,
              coord: S.coord + I * b,
              value: Number(S.value) + Number(I * w)
            });
        }
      }
      if (o.length === 1)
        o[0].text = i(
          l,
          o[0].value,
          "YYYY-MM-DD HH:mm",
          U.XAxis
        );
      else {
        const f = o[0].value, _ = o[1].value;
        if (C(o[2])) {
          const p = o[2].text;
          /^[0-9]{2}-[0-9]{2}$/.test(p) ? o[0].text = i(
            l,
            f,
            "MM-DD",
            U.XAxis
          ) : /^[0-9]{4}-[0-9]{2}$/.test(p) ? o[0].text = i(
            l,
            f,
            "YYYY-MM",
            U.XAxis
          ) : /^[0-9]{4}$/.test(p) && (o[0].text = i(
            l,
            f,
            "YYYY",
            U.XAxis
          ));
        } else
          o[0].text = this._optimalTickLabel(
            i,
            l,
            f,
            _
          ) ?? o[0].text;
      }
    }
    return o;
  }
  _optimalTickLabel(t, e, s, i) {
    const o = t(
      e,
      s,
      "YYYY",
      U.XAxis
    ), r = t(
      e,
      s,
      "YYYY-MM",
      U.XAxis
    ), a = t(
      e,
      s,
      "MM-DD",
      U.XAxis
    );
    return o !== t(
      e,
      i,
      "YYYY",
      U.XAxis
    ) ? o : r !== t(
      e,
      i,
      "YYYY-MM",
      U.XAxis
    ) ? r : a !== t(
      e,
      i,
      "MM-DD",
      U.XAxis
    ) ? a : null;
  }
  getAutoSize() {
    const t = this.getParent().getChart().getStyles(), e = t.xAxis, s = e.size;
    if (s !== "auto")
      return s;
    const i = t.crosshair;
    let o = 0;
    e.show && (e.axisLine.show && (o += e.axisLine.size), e.tictView.show && (o += e.tictView.length), e.tickText.show && (o += e.tickText.marginStart + e.tickText.marginEnd + e.tickText.size));
    let r = 0;
    return i.show && i.vertical.show && i.vertical.text.show && (r += i.vertical.text.paddingTop + i.vertical.text.paddingBottom + i.vertical.text.borderSize * 2 + i.vertical.text.size), Math.max(o, r);
  }
  getSelfBounding() {
    return this.getParent().getMainWidget().getBounding();
  }
  convertTimestampFromPixel(t) {
    const e = this.getParent().getChart().getChartStore().getTimeScaleStore(), s = e.coordinateToDataIndex(t);
    return e.dataIndexToTimestamp(s);
  }
  convertTimestampToPixel(t) {
    const e = this.getParent().getChart().getChartStore().getTimeScaleStore(), s = e.timestampToDataIndex(t);
    return e.dataIndexToCoordinate(s);
  }
  convertFromPixel(t) {
    return this.getParent().getChart().getChartStore().getTimeScaleStore().coordinateToDataIndex(t);
  }
  convertToPixel(t) {
    return this.getParent().getChart().getChartStore().getTimeScaleStore().dataIndexToCoordinate(t);
  }
  convertTimestampToData(t) {
    const e = this.getParent().getChart().getChartStore().getTimeScaleStore(), s = e.timestampToDataIndex(t);
    return e.getDataByDataIndex(s);
  }
  static extend(t) {
    class e extends me {
      createTicks(i) {
        return t.createTicks(i);
      }
    }
    return e;
  }
}
const qn = {
  name: "default",
  createTicks: ({ defaultTicks: n }) => n
}, Me = {
  default: me.extend(qn)
};
function vo(n) {
  Me[n.name] = me.extend(n);
}
function Jn(n) {
  return Me[n] ?? Me.default;
}
class Qn extends Bs {
  createAxisComponent(t) {
    const e = Jn(t);
    return new e(this);
  }
  createMainWidget(t) {
    return new Kn(t, this);
  }
}
function to(n, t) {
  let e = 0;
  return function() {
    const s = Date.now();
    s - e > t && (n.apply(this, arguments), e = s);
  };
}
class eo extends ps {
  constructor(t, e) {
    super(t, e), this._dragFlag = !1, this._dragStartY = 0, this._topPaneHeight = 0, this._bottomPaneHeight = 0, this._pressedMouseMoveEvent = to(
      this._pressedTouchMouseMoveEvent,
      20
    ), this.registerEvent("touchStartEvent", this._mouseDownEvent.bind(this)).registerEvent("touchMoveEvent", this._pressedMouseMoveEvent.bind(this)).registerEvent("touchEndEvent", this._mouseUpEvent.bind(this)).registerEvent("mouseDownEvent", this._mouseDownEvent.bind(this)).registerEvent("mouseUpEvent", this._mouseUpEvent.bind(this)).registerEvent(
      "pressedMouseMoveEvent",
      this._pressedMouseMoveEvent.bind(this)
    ).registerEvent("mouseEnterEvent", this._mouseEnterEvent.bind(this)).registerEvent("mouseLeaveEvent", this._mouseLeaveEvent.bind(this));
  }
  getName() {
    return k.SEPARATOR;
  }
  checkEventOn() {
    return !0;
  }
  _mouseDownEvent(t) {
    this._dragFlag = !0, this._dragStartY = t.pageY;
    const e = this.getPane();
    return this._topPaneHeight = e.getTopPane().getBounding().height, this._bottomPaneHeight = e.getBottomPane().getBounding().height, !0;
  }
  _mouseUpEvent() {
    return this._dragFlag = !1, this._mouseLeaveEvent();
  }
  _pressedTouchMouseMoveEvent(t) {
    const e = t.pageY - this._dragStartY, s = this.getPane(), i = s.getTopPane(), o = s.getBottomPane(), r = e < 0;
    if (i !== null && o?.getOptions().dragEnabled) {
      let a, l, c, h;
      r ? (a = i, l = o, c = this._topPaneHeight, h = this._bottomPaneHeight) : (a = o, l = i, c = this._bottomPaneHeight, h = this._topPaneHeight);
      const u = a.getOptions().minHeight;
      if (c > u) {
        const d = Math.max(
          c - Math.abs(e),
          u
        ), g = c - d;
        a.setBounding({ height: d }), l.setBounding({
          height: h + g
        });
        const m = s.getChart();
        m.getChartStore().getActionStore().execute(et.OnPaneDrag, { paneId: s.getId() }), m.adjustPaneViewport(!0, !0, !0, !0, !0);
      }
    }
    return !0;
  }
  _mouseEnterEvent() {
    const t = this.getPane();
    if (t.getBottomPane()?.getOptions().dragEnabled ?? !1) {
      const i = t.getChart().getStyles().separator;
      return this.getContainer().style.background = i.activeBackgroundColor, !0;
    }
    return !1;
  }
  _mouseLeaveEvent() {
    return this._dragFlag ? !1 : (this.getContainer().style.background = "", !0);
  }
  createContainer() {
    return ft("div", {
      width: "100%",
      height: `${$t}px`,
      margin: "0",
      padding: "0",
      position: "absolute",
      top: "-3px",
      zIndex: "20",
      boxSizing: "border-box",
      cursor: "ns-resize"
    });
  }
  updateImp(t, e, s) {
    if (s === F.All || s === F.Separator) {
      const i = this.getPane().getChart().getStyles().separator;
      t.style.top = `${-Math.floor(($t - i.size) / 2)}px`, t.style.height = `${$t}px`;
    }
  }
}
class ss extends Ls {
  constructor(t, e, s, i, o, r) {
    super(t, e, s, i), this.getContainer().style.overflow = "", this._topPane = o, this._bottomPane = r, this._separatorWidget = new eo(this.getContainer(), this);
  }
  setBounding(t) {
    return tt(this.getBounding(), t), this;
  }
  getTopPane() {
    return this._topPane;
  }
  setTopPane(t) {
    return this._topPane = t, this;
  }
  getBottomPane() {
    return this._bottomPane;
  }
  setBottomPane(t) {
    return this._bottomPane = t, this;
  }
  getWidget() {
    return this._separatorWidget;
  }
  /* eslint-disable @typescript-eslint/no-unused-vars */
  getImage(t) {
    const { width: e, height: s } = this.getBounding(), i = this.getChart().getStyles().separator, o = ft("canvas", {
      width: `${e}px`,
      height: `${s}px`,
      boxSizing: "border-box"
    }), r = o.getContext("2d"), a = yt(o);
    return o.width = e * a, o.height = s * a, r.scale(a, a), r.fillStyle = i.color, r.fillRect(0, 0, e, s), o;
  }
  updateImp(t, e, s) {
    if (t === F.All || t === F.Separator) {
      const i = this.getChart().getStyles().separator;
      e.style.backgroundColor = i.color, e.style.height = `${s.height}px`, e.style.marginLeft = `${s.left}px`, e.style.width = `${s.width}px`, this._separatorWidget.update(t);
    }
  }
}
function is() {
  return typeof window > "u" ? !1 : (window.navigator.userAgent.toLowerCase().indexOf("firefox") ?? -1) > -1;
}
function Ce() {
  return typeof window > "u" ? !1 : /iPhone|iPad|iPod/.test(window.navigator.platform);
}
const so = 10;
class io {
  constructor(t, e, s) {
    this._clickCount = 0, this._clickTimeoutId = null, this._clickCoordinate = {
      x: Number.NEGATIVE_INFINITY,
      y: Number.POSITIVE_INFINITY
    }, this._tapCount = 0, this._tapTimeoutId = null, this._tapCoordinate = {
      x: Number.NEGATIVE_INFINITY,
      y: Number.POSITIVE_INFINITY
    }, this._longTapTimeoutId = null, this._longTapActive = !1, this._mouseMoveStartCoordinate = null, this._touchMoveStartCoordinate = null, this._touchMoveExceededManhattanDistance = !1, this._cancelClick = !1, this._cancelTap = !1, this._unsubscribeOutsideMouseEvents = null, this._unsubscribeOutsideTouchEvents = null, this._unsubscribeMobileSafariEvents = null, this._unsubscribeMousemove = null, this._unsubscribeMouseWheel = null, this._unsubscribeContextMenu = null, this._unsubscribeRootMouseEvents = null, this._unsubscribeRootTouchEvents = null, this._startPinchMiddleCoordinate = null, this._startPinchDistance = 0, this._pinchPrevented = !1, this._preventTouchDragProcess = !1, this._mousePressed = !1, this._lastTouchEventTimeStamp = 0, this._activeTouchId = null, this._acceptMouseLeave = !Ce(), this._onFirefoxOutsideMouseUp = (i) => {
      this._mouseUpHandler(i);
    }, this._onMobileSafariDoubleClick = (i) => {
      if (this._firesTouchEvents(i)) {
        if (++this._tapCount, this._tapTimeoutId !== null && this._tapCount > 1) {
          const { manhattanDistance: o } = this._mouseTouchMoveWithDownInfo(
            this._getCoordinate(i),
            this._tapCoordinate
          );
          o < 30 && !this._cancelTap && this._processEvent(
            this._makeCompatEvent(i),
            this._handler.doubleTapEvent
          ), this._resetTapTimeout();
        }
      } else if (++this._clickCount, this._clickTimeoutId !== null && this._clickCount > 1) {
        const { manhattanDistance: o } = this._mouseTouchMoveWithDownInfo(
          this._getCoordinate(i),
          this._clickCoordinate
        );
        o < 5 && !this._cancelClick && this._processEvent(
          this._makeCompatEvent(i),
          this._handler.mouseDoubleClickEvent
        ), this._resetClickTimeout();
      }
    }, this._target = t, this._handler = e, this._options = s, this._init();
  }
  destroy() {
    this._unsubscribeOutsideMouseEvents !== null && (this._unsubscribeOutsideMouseEvents(), this._unsubscribeOutsideMouseEvents = null), this._unsubscribeOutsideTouchEvents !== null && (this._unsubscribeOutsideTouchEvents(), this._unsubscribeOutsideTouchEvents = null), this._unsubscribeMousemove !== null && (this._unsubscribeMousemove(), this._unsubscribeMousemove = null), this._unsubscribeMouseWheel !== null && (this._unsubscribeMouseWheel(), this._unsubscribeMouseWheel = null), this._unsubscribeContextMenu !== null && (this._unsubscribeContextMenu(), this._unsubscribeContextMenu = null), this._unsubscribeRootMouseEvents !== null && (this._unsubscribeRootMouseEvents(), this._unsubscribeRootMouseEvents = null), this._unsubscribeRootTouchEvents !== null && (this._unsubscribeRootTouchEvents(), this._unsubscribeRootTouchEvents = null), this._unsubscribeMobileSafariEvents !== null && (this._unsubscribeMobileSafariEvents(), this._unsubscribeMobileSafariEvents = null), this._clearLongTapTimeout(), this._resetClickTimeout();
  }
  _mouseEnterHandler(t) {
    this._unsubscribeMousemove?.(), this._unsubscribeMouseWheel?.(), this._unsubscribeContextMenu?.();
    const e = this._mouseMoveHandler.bind(this);
    this._unsubscribeMousemove = () => {
      this._target.removeEventListener("mousemove", e);
    }, this._target.addEventListener("mousemove", e);
    const s = this._mouseWheelHandler.bind(this);
    this._unsubscribeMouseWheel = () => {
      this._target.removeEventListener("wheel", s);
    }, this._target.addEventListener("wheel", s, { passive: !1 });
    const i = this._contextMenuHandler.bind(this);
    this._unsubscribeContextMenu = () => {
      this._target.removeEventListener("contextmenu", i);
    }, this._target.addEventListener("contextmenu", i, {
      passive: !1
    }), !this._firesTouchEvents(t) && (this._processEvent(
      this._makeCompatEvent(t),
      this._handler.mouseEnterEvent
    ), this._acceptMouseLeave = !0);
  }
  _resetClickTimeout() {
    this._clickTimeoutId !== null && clearTimeout(this._clickTimeoutId), this._clickCount = 0, this._clickTimeoutId = null, this._clickCoordinate = {
      x: Number.NEGATIVE_INFINITY,
      y: Number.POSITIVE_INFINITY
    };
  }
  _resetTapTimeout() {
    this._tapTimeoutId !== null && clearTimeout(this._tapTimeoutId), this._tapCount = 0, this._tapTimeoutId = null, this._tapCoordinate = {
      x: Number.NEGATIVE_INFINITY,
      y: Number.POSITIVE_INFINITY
    };
  }
  _mouseMoveHandler(t) {
    this._mousePressed || this._touchMoveStartCoordinate !== null || this._firesTouchEvents(t) || (this._processEvent(
      this._makeCompatEvent(t),
      this._handler.mouseMoveEvent
    ), this._acceptMouseLeave = !0);
  }
  _mouseWheelHandler(t) {
    if (Math.abs(t.deltaX) > Math.abs(t.deltaY)) {
      if (!C(this._handler.mouseWheelHortEvent) || (this._preventDefault(t), Math.abs(t.deltaX) === 0))
        return;
      this._handler.mouseWheelHortEvent(
        this._makeCompatEvent(t),
        -t.deltaX
      );
    } else {
      if (!C(this._handler.mouseWheelVertEvent))
        return;
      let e = -(t.deltaY / 100);
      if (e === 0)
        return;
      switch (this._preventDefault(t), t.deltaMode) {
        case t.DOM_DELTA_PAGE:
          e *= 120;
          break;
        case t.DOM_DELTA_LINE:
          e *= 32;
          break;
      }
      if (e !== 0) {
        const s = Math.sign(e) * Math.min(1, Math.abs(e));
        this._handler.mouseWheelVertEvent(
          this._makeCompatEvent(t),
          s
        );
      }
    }
  }
  _contextMenuHandler(t) {
    this._preventDefault(t);
  }
  _touchMoveHandler(t) {
    const e = this._touchWithId(
      t.changedTouches,
      this._activeTouchId
    );
    if (e === null || (this._lastTouchEventTimeStamp = this._eventTimeStamp(t), this._startPinchMiddleCoordinate !== null) || this._preventTouchDragProcess)
      return;
    this._pinchPrevented = !0;
    const s = this._mouseTouchMoveWithDownInfo(
      this._getCoordinate(e),
      this._touchMoveStartCoordinate
    ), { xOffset: i, yOffset: o, manhattanDistance: r } = s;
    if (!(!this._touchMoveExceededManhattanDistance && r < 5)) {
      if (!this._touchMoveExceededManhattanDistance) {
        const a = i * 0.5, l = o >= a && !this._options.treatVertDragAsPageScroll(), c = a > o && !this._options.treatHorzDragAsPageScroll();
        !l && !c && (this._preventTouchDragProcess = !0), this._touchMoveExceededManhattanDistance = !0, this._cancelTap = !0, this._clearLongTapTimeout(), this._resetTapTimeout();
      }
      this._preventTouchDragProcess || this._processEvent(
        this._makeCompatEvent(t, e),
        this._handler.touchMoveEvent
      );
    }
  }
  _mouseMoveWithDownHandler(t) {
    if (t.button !== 0)
      return;
    const e = this._mouseTouchMoveWithDownInfo(
      this._getCoordinate(t),
      this._mouseMoveStartCoordinate
    ), { manhattanDistance: s } = e;
    s >= 5 && (this._cancelClick = !0, this._resetClickTimeout()), this._cancelClick && this._processEvent(
      this._makeCompatEvent(t),
      this._handler.pressedMouseMoveEvent
    );
  }
  _mouseTouchMoveWithDownInfo(t, e) {
    const s = Math.abs(e.x - t.x), i = Math.abs(e.y - t.y), o = s + i;
    return { xOffset: s, yOffset: i, manhattanDistance: o };
  }
  // eslint-disable-next-line complexity
  _touchEndHandler(t) {
    let e = this._touchWithId(
      t.changedTouches,
      this._activeTouchId
    );
    if (e === null && t.touches.length === 0 && (e = t.changedTouches[0]), e === null)
      return;
    this._activeTouchId = null, this._lastTouchEventTimeStamp = this._eventTimeStamp(t), this._clearLongTapTimeout(), this._touchMoveStartCoordinate = null, this._unsubscribeRootTouchEvents !== null && (this._unsubscribeRootTouchEvents(), this._unsubscribeRootTouchEvents = null);
    const s = this._makeCompatEvent(t, e);
    if (this._processEvent(s, this._handler.touchEndEvent), ++this._tapCount, this._tapTimeoutId !== null && this._tapCount > 1) {
      const { manhattanDistance: i } = this._mouseTouchMoveWithDownInfo(
        this._getCoordinate(e),
        this._tapCoordinate
      );
      i < 30 && !this._cancelTap && this._processEvent(s, this._handler.doubleTapEvent), this._resetTapTimeout();
    } else
      this._cancelTap || (this._processEvent(s, this._handler.tapEvent), C(this._handler.tapEvent) && this._preventDefault(t));
    this._tapCount === 0 && this._preventDefault(t), t.touches.length === 0 && this._longTapActive && (this._longTapActive = !1, this._preventDefault(t));
  }
  _mouseUpHandler(t) {
    if (t.button !== 0)
      return;
    const e = this._makeCompatEvent(t);
    if (this._mouseMoveStartCoordinate = null, this._mousePressed = !1, this._unsubscribeRootMouseEvents !== null && (this._unsubscribeRootMouseEvents(), this._unsubscribeRootMouseEvents = null), is() && this._target.ownerDocument.documentElement.removeEventListener(
      "mouseleave",
      this._onFirefoxOutsideMouseUp
    ), !this._firesTouchEvents(t))
      if (this._processEvent(e, this._handler.mouseUpEvent), ++this._clickCount, this._clickTimeoutId !== null && this._clickCount > 1) {
        const { manhattanDistance: s } = this._mouseTouchMoveWithDownInfo(
          this._getCoordinate(t),
          this._clickCoordinate
        );
        s < 5 && !this._cancelClick && this._processEvent(e, this._handler.mouseDoubleClickEvent), this._resetClickTimeout();
      } else
        this._cancelClick || this._processEvent(e, this._handler.mouseClickEvent);
  }
  _clearLongTapTimeout() {
    this._longTapTimeoutId !== null && (clearTimeout(this._longTapTimeoutId), this._longTapTimeoutId = null);
  }
  _touchStartHandler(t) {
    if (this._activeTouchId !== null)
      return;
    const e = t.changedTouches[0];
    this._activeTouchId = e.identifier, this._lastTouchEventTimeStamp = this._eventTimeStamp(t);
    const s = this._target.ownerDocument.documentElement;
    this._cancelTap = !1, this._touchMoveExceededManhattanDistance = !1, this._preventTouchDragProcess = !1, this._touchMoveStartCoordinate = this._getCoordinate(e), this._unsubscribeRootTouchEvents !== null && (this._unsubscribeRootTouchEvents(), this._unsubscribeRootTouchEvents = null);
    {
      const i = this._touchMoveHandler.bind(this), o = this._touchEndHandler.bind(this);
      this._unsubscribeRootTouchEvents = () => {
        s.removeEventListener(
          "touchmove",
          i
        ), s.removeEventListener("touchend", o);
      }, s.addEventListener("touchmove", i, {
        passive: !1
      }), s.addEventListener("touchend", o, {
        passive: !1
      }), this._clearLongTapTimeout(), this._longTapTimeoutId = setTimeout(
        this._longTapHandler.bind(this, t),
        500
        /* LongTap */
      );
    }
    this._processEvent(
      this._makeCompatEvent(t, e),
      this._handler.touchStartEvent
    ), this._tapTimeoutId === null && (this._tapCount = 0, this._tapTimeoutId = setTimeout(
      this._resetTapTimeout.bind(this),
      500
      /* ResetClick */
    ), this._tapCoordinate = this._getCoordinate(e));
  }
  _mouseDownHandler(t) {
    if (t.button === 2) {
      this._preventDefault(t), this._processEvent(
        this._makeCompatEvent(t),
        this._handler.mouseRightClickEvent
      );
      return;
    }
    if (t.button !== 0)
      return;
    const e = this._target.ownerDocument.documentElement;
    is() && e.addEventListener("mouseleave", this._onFirefoxOutsideMouseUp), this._cancelClick = !1, this._mouseMoveStartCoordinate = this._getCoordinate(t), this._unsubscribeRootMouseEvents !== null && (this._unsubscribeRootMouseEvents(), this._unsubscribeRootMouseEvents = null);
    {
      const s = this._mouseMoveWithDownHandler.bind(this), i = this._mouseUpHandler.bind(this);
      this._unsubscribeRootMouseEvents = () => {
        e.removeEventListener(
          "mousemove",
          s
        ), e.removeEventListener("mouseup", i);
      }, e.addEventListener("mousemove", s), e.addEventListener("mouseup", i);
    }
    this._mousePressed = !0, !this._firesTouchEvents(t) && (this._processEvent(
      this._makeCompatEvent(t),
      this._handler.mouseDownEvent
    ), this._clickTimeoutId === null && (this._clickCount = 0, this._clickTimeoutId = setTimeout(
      this._resetClickTimeout.bind(this),
      500
      /* ResetClick */
    ), this._clickCoordinate = this._getCoordinate(t)));
  }
  _init() {
    this._target.addEventListener(
      "mouseenter",
      this._mouseEnterHandler.bind(this)
    ), this._target.addEventListener(
      "touchcancel",
      this._clearLongTapTimeout.bind(this)
    );
    {
      const t = this._target.ownerDocument, e = (s) => {
        this._handler.mouseDownOutsideEvent != null && (s.composed && this._target.contains(s.composedPath()[0]) || s.target !== null && this._target.contains(s.target) || this._handler.mouseDownOutsideEvent({ x: 0, y: 0, pageX: 0, pageY: 0 }));
      };
      this._unsubscribeOutsideTouchEvents = () => {
        t.removeEventListener("touchstart", e);
      }, this._unsubscribeOutsideMouseEvents = () => {
        t.removeEventListener("mousedown", e);
      }, t.addEventListener("mousedown", e), t.addEventListener("touchstart", e, { passive: !0 });
    }
    Ce() && (this._unsubscribeMobileSafariEvents = () => {
      this._target.removeEventListener(
        "dblclick",
        this._onMobileSafariDoubleClick
      );
    }, this._target.addEventListener(
      "dblclick",
      this._onMobileSafariDoubleClick
    )), this._target.addEventListener(
      "mouseleave",
      this._mouseLeaveHandler.bind(this)
    ), this._target.addEventListener(
      "touchstart",
      this._touchStartHandler.bind(this),
      { passive: !0 }
    ), this._target.addEventListener("mousedown", (t) => {
      if (t.button === 1)
        return t.preventDefault(), !1;
    }), this._target.addEventListener(
      "mousedown",
      this._mouseDownHandler.bind(this)
    ), this._initPinch(), this._target.addEventListener("touchmove", () => {
    }, { passive: !1 });
  }
  _initPinch() {
    !C(this._handler.pinchStartEvent) && !C(this._handler.pinchEvent) && !C(this._handler.pinchEndEvent) || (this._target.addEventListener(
      "touchstart",
      (t) => {
        this._checkPinchState(t.touches);
      },
      { passive: !0 }
    ), this._target.addEventListener(
      "touchmove",
      (t) => {
        if (!(t.touches.length !== 2 || this._startPinchMiddleCoordinate === null) && C(this._handler.pinchEvent)) {
          const s = this._getTouchDistance(
            t.touches[0],
            t.touches[1]
          ) / this._startPinchDistance;
          this._handler.pinchEvent(
            { ...this._startPinchMiddleCoordinate, pageX: 0, pageY: 0 },
            s
          ), this._preventDefault(t);
        }
      },
      { passive: !1 }
    ), this._target.addEventListener("touchend", (t) => {
      this._checkPinchState(t.touches);
    }));
  }
  _checkPinchState(t) {
    t.length === 1 && (this._pinchPrevented = !1), t.length !== 2 || this._pinchPrevented || this._longTapActive ? this._stopPinch() : this._startPinch(t);
  }
  _startPinch(t) {
    const e = this._target.getBoundingClientRect() ?? { left: 0, top: 0 };
    this._startPinchMiddleCoordinate = {
      x: (t[0].clientX - e.left + (t[1].clientX - e.left)) / 2,
      y: (t[0].clientY - e.top + (t[1].clientY - e.top)) / 2
    }, this._startPinchDistance = this._getTouchDistance(t[0], t[1]), C(this._handler.pinchStartEvent) && this._handler.pinchStartEvent({ x: 0, y: 0, pageX: 0, pageY: 0 }), this._clearLongTapTimeout();
  }
  _stopPinch() {
    this._startPinchMiddleCoordinate !== null && (this._startPinchMiddleCoordinate = null, C(this._handler.pinchEndEvent) && this._handler.pinchEndEvent({ x: 0, y: 0, pageX: 0, pageY: 0 }));
  }
  _mouseLeaveHandler(t) {
    this._unsubscribeMousemove?.(), this._unsubscribeMouseWheel?.(), this._unsubscribeContextMenu?.(), !this._firesTouchEvents(t) && this._acceptMouseLeave && (this._processEvent(
      this._makeCompatEvent(t),
      this._handler.mouseLeaveEvent
    ), this._acceptMouseLeave = !Ce());
  }
  _longTapHandler(t) {
    const e = this._touchWithId(t.touches, this._activeTouchId);
    e !== null && (this._processEvent(
      this._makeCompatEvent(t, e),
      this._handler.longTapEvent
    ), this._cancelTap = !0, this._longTapActive = !0);
  }
  _firesTouchEvents(t) {
    return C(t.sourceCapabilities?.firesTouchEvents) ? t.sourceCapabilities.firesTouchEvents : this._eventTimeStamp(t) < this._lastTouchEventTimeStamp + 500;
  }
  _processEvent(t, e) {
    e?.call(this._handler, t);
  }
  _makeCompatEvent(t, e) {
    const s = e ?? t, i = this._target.getBoundingClientRect() ?? { left: 0, top: 0 };
    return {
      x: s.clientX - i.left,
      y: s.clientY - i.top,
      pageX: s.pageX,
      pageY: s.pageY,
      isTouch: !t.type.startsWith("mouse") && t.type !== "contextmenu" && t.type !== "click" && t.type !== "wheel",
      preventDefault: () => {
        t.type !== "touchstart" && this._preventDefault(t);
      }
    };
  }
  _getTouchDistance(t, e) {
    const s = t.clientX - e.clientX, i = t.clientY - e.clientY;
    return Math.sqrt(s * s + i * i);
  }
  _preventDefault(t) {
    t.cancelable && t.preventDefault();
  }
  _getCoordinate(t) {
    return {
      x: t.pageX,
      y: t.pageY
    };
  }
  _eventTimeStamp(t) {
    return t.timeStamp ?? performance.now();
  }
  _touchWithId(t, e) {
    for (let s = 0; s < t.length; ++s)
      if (t[s].identifier === e)
        return t[s];
    return null;
  }
}
class no {
  constructor(t, e) {
    this._flingStartTime = (/* @__PURE__ */ new Date()).getTime(), this._flingScrollRequestId = null, this._startScrollCoordinate = null, this._touchCoordinate = null, this._touchCancelCrosshair = !1, this._touchZoomed = !1, this._pinchScale = 1, this._mouseDownWidget = null, this._prevYAxisRange = null, this._xAxisStartScaleCoordinate = null, this._xAxisStartScaleDistance = 0, this._xAxisScale = 1, this._yAxisStartScaleDistance = 0, this._mouseMoveTriggerWidgetInfo = {
      pane: null,
      widget: null
    }, this._boundKeyBoardDownEvent = (s) => {
      if (s.shiftKey)
        switch (s.code) {
          case "Equal": {
            this._chart.getChartStore().getTimeScaleStore().zoom(0.5);
            break;
          }
          case "Minus": {
            this._chart.getChartStore().getTimeScaleStore().zoom(-0.5);
            break;
          }
          case "ArrowLeft": {
            const i = this._chart.getChartStore().getTimeScaleStore();
            i.startScroll(), i.scroll(-3 * i.getBarSpace().bar);
            break;
          }
          case "ArrowRight": {
            const i = this._chart.getChartStore().getTimeScaleStore();
            i.startScroll(), i.scroll(3 * i.getBarSpace().bar);
            break;
          }
        }
    }, this._container = t, this._chart = e, this._event = new io(t, this, {
      treatVertDragAsPageScroll: () => !1,
      treatHorzDragAsPageScroll: () => !1
    }), t.addEventListener("keydown", this._boundKeyBoardDownEvent);
  }
  pinchStartEvent() {
    return this._touchZoomed = !0, this._pinchScale = 1, !0;
  }
  pinchEvent(t, e) {
    const { pane: s, widget: i } = this._findWidgetByEvent(t);
    if (s?.getId() !== L.X_AXIS && i?.getName() === k.MAIN) {
      const o = this._makeWidgetEvent(t, i), r = (e - this._pinchScale) * 5;
      return this._pinchScale = e, this._chart.getChartStore().getTimeScaleStore().zoom(r, { x: o.x, y: o.y }), !0;
    }
    return !1;
  }
  mouseWheelHortEvent(t, e) {
    const s = this._chart.getChartStore().getTimeScaleStore();
    return s.startScroll(), s.scroll(e), !0;
  }
  mouseWheelVertEvent(t, e) {
    const { widget: s } = this._findWidgetByEvent(t), i = this._makeWidgetEvent(t, s);
    return s?.getName() === k.MAIN ? (this._chart.getChartStore().getTimeScaleStore().zoom(e, { x: i.x, y: i.y }), !0) : !1;
  }
  mouseDownEvent(t) {
    const { pane: e, widget: s } = this._findWidgetByEvent(t);
    if (this._mouseDownWidget = s, s !== null) {
      const i = this._makeWidgetEvent(t, s);
      switch (s.getName()) {
        case k.SEPARATOR:
          return s.dispatchEvent("mouseDownEvent", i);
        case k.MAIN: {
          const r = e.getAxisComponent().getRange() ?? null;
          return this._prevYAxisRange = r === null ? r : { ...r }, this._startScrollCoordinate = { x: i.x, y: i.y }, this._chart.getChartStore().getTimeScaleStore().startScroll(), s.dispatchEvent("mouseDownEvent", i);
        }
        case k.X_AXIS: {
          const r = s.dispatchEvent("mouseDownEvent", i);
          return r && this._chart.updatePane(F.Overlay), this._xAxisStartScaleCoordinate = { x: i.x, y: i.y }, this._xAxisStartScaleDistance = i.pageX, r;
        }
        case k.Y_AXIS: {
          const r = s.dispatchEvent("mouseDownEvent", i);
          r && this._chart.updatePane(F.Overlay);
          const a = e.getAxisComponent().getRange() ?? null;
          return this._prevYAxisRange = a === null ? a : { ...a }, this._yAxisStartScaleDistance = i.pageY, r;
        }
      }
    }
    return !1;
  }
  mouseMoveEvent(t) {
    const { pane: e, widget: s } = this._findWidgetByEvent(t), i = this._makeWidgetEvent(t, s);
    if ((this._mouseMoveTriggerWidgetInfo.pane?.getId() !== e?.getId() || this._mouseMoveTriggerWidgetInfo.widget?.getName() !== s?.getName()) && (s?.dispatchEvent("mouseEnterEvent", i), this._mouseMoveTriggerWidgetInfo.widget?.dispatchEvent(
      "mouseLeaveEvent",
      i
    ), this._mouseMoveTriggerWidgetInfo = { pane: e, widget: s }), s !== null)
      switch (s.getName()) {
        case k.MAIN: {
          const r = s.dispatchEvent("mouseMoveEvent", i), a = this._chart.getChartStore();
          let l = {
            x: i.x,
            y: i.y,
            paneId: e?.getId()
          };
          return r && a.getTooltipStore().getActiveIcon() !== null && (l = void 0, s !== null && (s.getContainer().style.cursor = "pointer")), this._chart.getChartStore().getTooltipStore().setCrosshair(l), r;
        }
        case k.SEPARATOR:
        case k.X_AXIS:
        case k.Y_AXIS: {
          const r = s.dispatchEvent("mouseMoveEvent", i);
          return this._chart.getChartStore().getTooltipStore().setCrosshair(), r;
        }
      }
    return !1;
  }
  pressedMouseMoveEvent(t) {
    if (this._mouseDownWidget !== null && this._mouseDownWidget.getName() === k.SEPARATOR)
      return this._mouseDownWidget.dispatchEvent("pressedMouseMoveEvent", t);
    const { pane: e, widget: s } = this._findWidgetByEvent(t);
    if (s !== null && this._mouseDownWidget?.getPane().getId() === e?.getId() && this._mouseDownWidget?.getName() === s.getName()) {
      const i = this._makeWidgetEvent(t, s);
      switch (s.getName()) {
        case k.MAIN: {
          const r = s.getBounding(), a = s.dispatchEvent("pressedMouseMoveEvent", i);
          if (!a && this._startScrollCoordinate !== null) {
            const l = e.getAxisComponent();
            if (this._prevYAxisRange !== null && !l.getAutoCalcTickFlag() && l.getScrollZoomEnabled()) {
              const { from: h, to: u, range: d } = this._prevYAxisRange;
              let g;
              l?.isReverse() ?? !1 ? g = this._startScrollCoordinate.y - i.y : g = i.y - this._startScrollCoordinate.y;
              const m = g / r.height, f = d * m, _ = h + f, p = u + f, x = l.convertToRealValue(_), y = l.convertToRealValue(p);
              l.setRange({
                from: _,
                to: p,
                range: p - _,
                realFrom: x,
                realTo: y,
                realRange: y - x
              });
            }
            const c = i.x - this._startScrollCoordinate.x;
            this._chart.getChartStore().getTimeScaleStore().scroll(c);
          }
          return this._chart.getChartStore().getTooltipStore().setCrosshair({ x: i.x, y: i.y, paneId: e?.getId() }), a;
        }
        case k.X_AXIS: {
          const r = s.dispatchEvent("pressedMouseMoveEvent", i);
          if (r)
            this._chart.updatePane(F.Overlay);
          else if (e.getAxisComponent()?.getScrollZoomEnabled() ?? !0) {
            const l = this._xAxisStartScaleDistance / i.pageX;
            if (Number.isFinite(l)) {
              const c = (l - this._xAxisScale) * 10;
              this._xAxisScale = l, this._chart.getChartStore().getTimeScaleStore().zoom(
                c,
                this._xAxisStartScaleCoordinate ?? void 0
              );
            }
          }
          return r;
        }
        case k.Y_AXIS: {
          const r = s.dispatchEvent("pressedMouseMoveEvent", i);
          if (r)
            this._chart.updatePane(F.Overlay);
          else {
            const a = e.getAxisComponent();
            if (this._prevYAxisRange !== null && a.getScrollZoomEnabled()) {
              const { from: l, to: c, range: h } = this._prevYAxisRange, u = i.pageY / this._yAxisStartScaleDistance, d = h * u, g = (d - h) / 2, m = l - g, f = c + g, _ = a.convertToRealValue(m), p = a.convertToRealValue(f);
              a.setRange({
                from: m,
                to: f,
                range: d,
                realFrom: _,
                realTo: p,
                realRange: p - _
              }), this._chart.adjustPaneViewport(!1, !0, !0, !0);
            }
          }
          return r;
        }
      }
    }
    return !1;
  }
  mouseUpEvent(t) {
    const { widget: e } = this._findWidgetByEvent(t);
    let s = !1;
    if (e !== null) {
      const i = this._makeWidgetEvent(t, e);
      switch (e.getName()) {
        case k.MAIN:
        case k.SEPARATOR:
        case k.X_AXIS:
        case k.Y_AXIS: {
          s = e.dispatchEvent("mouseUpEvent", i);
          break;
        }
      }
      s && this._chart.updatePane(F.Overlay);
    }
    return this._mouseDownWidget = null, this._startScrollCoordinate = null, this._prevYAxisRange = null, this._xAxisStartScaleCoordinate = null, this._xAxisStartScaleDistance = 0, this._xAxisScale = 1, this._yAxisStartScaleDistance = 0, s;
  }
  mouseClickEvent(t) {
    const { widget: e } = this._findWidgetByEvent(t);
    if (e !== null) {
      const s = this._makeWidgetEvent(t, e);
      return e.dispatchEvent("mouseClickEvent", s);
    }
    return !1;
  }
  mouseRightClickEvent(t) {
    const { widget: e } = this._findWidgetByEvent(t);
    let s = !1;
    if (e !== null) {
      const i = this._makeWidgetEvent(t, e);
      switch (e.getName()) {
        case k.MAIN:
        case k.X_AXIS:
        case k.Y_AXIS: {
          s = e.dispatchEvent("mouseRightClickEvent", i);
          break;
        }
      }
      s && this._chart.updatePane(F.Overlay);
    }
    return !1;
  }
  mouseDoubleClickEvent(t) {
    const { pane: e, widget: s } = this._findWidgetByEvent(t);
    if (s !== null)
      switch (s.getName()) {
        case k.MAIN: {
          const o = this._makeWidgetEvent(t, s);
          return s.dispatchEvent("mouseDoubleClickEvent", o);
        }
        case k.Y_AXIS: {
          const o = e.getAxisComponent();
          if (!o.getAutoCalcTickFlag())
            return o.setAutoCalcTickFlag(!0), this._chart.adjustPaneViewport(!1, !0, !0, !0), !0;
          break;
        }
      }
    return !1;
  }
  mouseLeaveEvent() {
    return this._chart.getChartStore().getTooltipStore().setCrosshair(), !0;
  }
  touchStartEvent(t) {
    const { pane: e, widget: s } = this._findWidgetByEvent(t);
    if (s !== null) {
      const i = this._makeWidgetEvent(t, s);
      switch (s.getName()) {
        case k.MAIN: {
          const r = this._chart.getChartStore(), a = r.getTooltipStore();
          if (s.dispatchEvent("mouseDownEvent", i))
            return this._touchCancelCrosshair = !0, this._touchCoordinate = null, a.setCrosshair(void 0, !0), this._chart.updatePane(F.Overlay), !0;
          if (this._flingScrollRequestId !== null && (je(this._flingScrollRequestId), this._flingScrollRequestId = null), this._flingStartTime = (/* @__PURE__ */ new Date()).getTime(), this._startScrollCoordinate = { x: i.x, y: i.y }, r.getTimeScaleStore().startScroll(), this._touchZoomed = !1, this._touchCoordinate !== null) {
            const l = i.x - this._touchCoordinate.x, c = i.y - this._touchCoordinate.y;
            Math.sqrt(l * l + c * c) < so ? (this._touchCoordinate = { x: i.x, y: i.y }, a.setCrosshair({
              x: i.x,
              y: i.y,
              paneId: e?.getId()
            })) : (this._touchCoordinate = null, this._touchCancelCrosshair = !0, a.setCrosshair());
          }
          return !0;
        }
        case k.X_AXIS:
        case k.Y_AXIS: {
          const r = s.dispatchEvent("mouseDownEvent", i);
          return r && this._chart.updatePane(F.Overlay), r;
        }
      }
    }
    return !1;
  }
  touchMoveEvent(t) {
    const { pane: e, widget: s } = this._findWidgetByEvent(t);
    if (s !== null) {
      const i = this._makeWidgetEvent(t, s), o = s.getName(), r = this._chart.getChartStore(), a = r.getTooltipStore();
      switch (o) {
        case k.MAIN: {
          if (s.dispatchEvent("pressedMouseMoveEvent", i))
            return i.preventDefault?.(), a.setCrosshair(void 0, !0), this._chart.updatePane(F.Overlay), !0;
          if (this._touchCoordinate !== null)
            i.preventDefault?.(), a.setCrosshair({
              x: i.x,
              y: i.y,
              paneId: e?.getId()
            });
          else if (this._startScrollCoordinate !== null && Math.abs(this._startScrollCoordinate.x - i.x) > this._startScrollCoordinate.y - i.y) {
            const l = i.x - this._startScrollCoordinate.x;
            r.getTimeScaleStore().scroll(l);
          }
          return !0;
        }
        case k.X_AXIS:
        case k.Y_AXIS: {
          const l = s.dispatchEvent("pressedMouseMoveEvent", i);
          return l && (i.preventDefault?.(), this._chart.updatePane(F.Overlay)), l;
        }
      }
    }
    return !1;
  }
  touchEndEvent(t) {
    const { widget: e } = this._findWidgetByEvent(t);
    if (e !== null) {
      const s = this._makeWidgetEvent(t, e);
      switch (e.getName()) {
        case k.MAIN: {
          if (e.dispatchEvent("mouseUpEvent", s), this._startScrollCoordinate !== null) {
            const o = (/* @__PURE__ */ new Date()).getTime() - this._flingStartTime;
            let a = (s.x - this._startScrollCoordinate.x) / (o > 0 ? o : 1) * 20;
            if (o < 200 && Math.abs(a) > 0) {
              const l = this._chart.getChartStore().getTimeScaleStore(), c = () => {
                this._flingScrollRequestId = ne(() => {
                  l.startScroll(), l.scroll(a), a = a * (1 - 0.025), Math.abs(a) < 1 ? this._flingScrollRequestId !== null && (je(this._flingScrollRequestId), this._flingScrollRequestId = null) : c();
                });
              };
              c();
            }
          }
          return !0;
        }
        case k.X_AXIS:
        case k.Y_AXIS:
          e.dispatchEvent("mouseUpEvent", s) && this._chart.updatePane(F.Overlay);
      }
    }
    return !1;
  }
  tapEvent(t) {
    const { pane: e, widget: s } = this._findWidgetByEvent(t);
    let i = !1;
    if (s !== null) {
      const o = this._makeWidgetEvent(t, s), r = s.dispatchEvent("mouseClickEvent", o);
      if (s.getName() === k.MAIN) {
        const a = this._makeWidgetEvent(t, s), c = this._chart.getChartStore().getTooltipStore();
        r ? (this._touchCancelCrosshair = !0, this._touchCoordinate = null, c.setCrosshair(void 0, !0), i = !0) : (!this._touchCancelCrosshair && !this._touchZoomed && (this._touchCoordinate = { x: a.x, y: a.y }, c.setCrosshair(
          { x: a.x, y: a.y, paneId: e?.getId() },
          !0
        ), i = !0), this._touchCancelCrosshair = !1);
      }
      (i || r) && this._chart.updatePane(F.Overlay);
    }
    return i;
  }
  doubleTapEvent(t) {
    return this.mouseDoubleClickEvent(t);
  }
  longTapEvent(t) {
    const { pane: e, widget: s } = this._findWidgetByEvent(t);
    if (s !== null && s.getName() === k.MAIN) {
      const i = this._makeWidgetEvent(t, s);
      return this._touchCoordinate = { x: i.x, y: i.y }, this._chart.getChartStore().getTooltipStore().setCrosshair({ x: i.x, y: i.y, paneId: e?.getId() }), !0;
    }
    return !1;
  }
  _findWidgetByEvent(t) {
    const { x: e, y: s } = t, i = this._chart.getAllSeparatorPanes(), o = this._chart.getChartStore().getStyles().separator.size;
    for (const [, c] of i) {
      const h = c.getBounding(), u = h.top - Math.round(($t - o) / 2);
      if (e >= h.left && e <= h.left + h.width && s >= u && s <= u + $t)
        return { pane: c, widget: c.getWidget() };
    }
    const r = this._chart.getAllDrawPanes();
    let a = null;
    for (const c of r) {
      const h = c.getBounding();
      if (e >= h.left && e <= h.left + h.width && s >= h.top && s <= h.top + h.height) {
        a = c;
        break;
      }
    }
    let l = null;
    if (a !== null) {
      if (l === null) {
        const c = a.getMainWidget(), h = c.getBounding();
        e >= h.left && e <= h.left + h.width && s >= h.top && s <= h.top + h.height && (l = c);
      }
      if (l === null) {
        const c = a.getYAxisWidget();
        if (c !== null) {
          const h = c.getBounding();
          e >= h.left && e <= h.left + h.width && s >= h.top && s <= h.top + h.height && (l = c);
        }
      }
    }
    return { pane: a, widget: l };
  }
  _makeWidgetEvent(t, e) {
    const s = e?.getBounding() ?? null;
    return {
      ...t,
      x: t.x - (s?.left ?? 0),
      y: t.y - (s?.top ?? 0)
    };
  }
  destroy() {
    this._container.removeEventListener(
      "keydown",
      this._boundKeyBoardDownEvent
    ), this._event.destroy();
  }
}
var oo = /* @__PURE__ */ ((n) => (n.Root = "root", n.Main = "main", n.YAxis = "yAxis", n))(oo || {});
class Vs {
  constructor(t, e) {
    this._drawPanes = [], this._separatorPanes = /* @__PURE__ */ new Map(), this._initContainer(t), this._chartEvent = new no(this._chartContainer, this), this._chartStore = new dn(this, e), this._initPanes(e), this.adjustPaneViewport(!0, !0, !0);
  }
  _initContainer(t) {
    this._container = t, this._chartContainer = ft("div", {
      position: "relative",
      width: "100%",
      outline: "none",
      borderStyle: "none",
      cursor: "crosshair",
      boxSizing: "border-box",
      userSelect: "none",
      webkitUserSelect: "none",
      // eslint-disable-next-line @typescript-eslint/ban-ts-comment
      // @ts-expect-error
      msUserSelect: "none",
      MozUserSelect: "none",
      webkitTapHighlightColor: "transparent"
    }), this._chartContainer.tabIndex = 1, t.appendChild(this._chartContainer);
  }
  _initPanes(t) {
    const e = t?.layout ?? [{ type: Yt.Candle }];
    let s = !1, i = !1;
    const o = (r) => {
      if (!i) {
        const a = this._createPane(
          Qn,
          L.X_AXIS,
          r ?? {}
        );
        this._xAxisPane = a, i = !0;
      }
    };
    e.forEach((r) => {
      switch (r.type) {
        case Yt.Candle: {
          if (!s) {
            const a = r.options ?? {};
            tt(a, { id: L.CANDLE }), this._candlePane = this._createPane(
              Gn,
              L.CANDLE,
              a
            ), (r.content ?? []).forEach((c) => {
              this.createIndicator(c, !0, a);
            }), s = !0;
          }
          break;
        }
        case Yt.Indicator: {
          const a = r.content ?? [];
          if (a.length > 0) {
            let l;
            a.forEach((c) => {
              C(l) ? this.createIndicator(c, !0, { id: l }) : l = this.createIndicator(c, !0, r.options);
            });
          }
          break;
        }
        case Yt.XAxis: {
          o(r.options);
          break;
        }
      }
    }), o({ position: kt.Bottom });
  }
  _createPane(t, e, s) {
    let i = null, o = null;
    switch (s?.position) {
      case kt.Top: {
        const l = this._drawPanes[0];
        C(l) && (o = new t(
          this._chartContainer,
          l.getContainer(),
          this,
          e,
          s ?? {}
        ), i = 0);
        break;
      }
      case kt.Bottom:
        break;
      default:
        for (let l = this._drawPanes.length - 1; l > -1; l--) {
          const c = this._drawPanes[l], h = this._drawPanes[l - 1];
          if (c?.getOptions().position === kt.Bottom && h?.getOptions().position !== kt.Bottom) {
            o = new t(
              this._chartContainer,
              c.getContainer(),
              this,
              e,
              s ?? {}
            ), i = l;
            break;
          }
        }
    }
    C(o) || (o = new t(
      this._chartContainer,
      null,
      this,
      e,
      s ?? {}
    ));
    let a;
    if (E(i) ? (this._drawPanes.splice(i, 0, o), a = i) : (this._drawPanes.push(o), a = this._drawPanes.length - 1), o.getId() !== L.X_AXIS) {
      let l = this._drawPanes[a + 1];
      if (C(l) && l.getId() === L.X_AXIS && (l = this._drawPanes[a + 2]), C(l)) {
        let h = this._separatorPanes.get(l);
        C(h) ? h.setTopPane(o) : (h = new ss(
          this._chartContainer,
          l.getContainer(),
          this,
          "",
          o,
          l
        ), this._separatorPanes.set(l, h));
      }
      let c = this._drawPanes[a - 1];
      if (C(c) && c.getId() === L.X_AXIS && (c = this._drawPanes[a - 2]), C(c)) {
        const h = new ss(
          this._chartContainer,
          o.getContainer(),
          this,
          "",
          c,
          o
        );
        this._separatorPanes.set(o, h);
      }
    }
    return o;
  }
  _measurePaneHeight() {
    const t = Math.floor(this._container.clientHeight), e = this._chartStore.getStyles().separator.size, s = this._xAxisPane.getAxisComponent().getAutoSize();
    let i = t - s - this._separatorPanes.size * e;
    i < 0 && (i = 0);
    let o = 0;
    this._drawPanes.forEach((l) => {
      if (l.getId() !== L.CANDLE && l.getId() !== L.X_AXIS) {
        let c = l.getBounding().height;
        const h = l.getOptions().minHeight;
        c < h && (c = h), o + c > i ? (o = i, c = Math.max(
          i - o,
          0
        )) : o += c, l.setBounding({ height: c });
      }
    });
    const r = i - o;
    this._candlePane?.setBounding({ height: r }), this._xAxisPane.setBounding({ height: s });
    let a = 0;
    this._drawPanes.forEach((l) => {
      const c = this._separatorPanes.get(l);
      C(c) && (c.setBounding({ height: e, top: a }), a += e), l.setBounding({ top: a }), a += l.getBounding().height;
    });
  }
  _measurePaneWidth() {
    const t = Math.floor(this._container.clientWidth), e = this._chartStore.getStyles(), s = e.yAxis, i = s.position === Ft.Left, o = !s.inside;
    let r = 0, a = 0, l = 0, c = 0;
    this._drawPanes.forEach((f) => {
      f.getId() !== L.X_AXIS && (a = Math.max(
        a,
        f.getAxisComponent().getAutoSize()
      ));
    }), a > t && (a = t), o ? (r = t - a, i ? (l = 0, c = a) : (l = t - a, c = 0)) : (r = t, c = 0, i ? l = 0 : l = t - a), this._chartStore.getTimeScaleStore().setTotalBarSpace(r);
    const h = { width: t }, u = { width: r, left: c }, d = { width: a, left: l }, g = e.separator.fill;
    let m;
    o && !g ? m = u : m = h, this._drawPanes.forEach((f) => {
      this._separatorPanes.get(f)?.setBounding(m), f.setBounding(h, u, d);
    });
  }
  _setPaneOptions(t, e) {
    if (D(t.id)) {
      const s = this.getDrawPaneById(t.id);
      let i = !1;
      if (s !== null) {
        let o = e;
        if (t.id !== L.CANDLE && E(t.height) && t.height > 0) {
          const r = Math.max(
            t.minHeight ?? s.getOptions().minHeight,
            0
          ), a = Math.max(r, t.height);
          s.setBounding({ height: a }), o = !0, i = !0;
        }
        (D(t.axisOptions?.name) || C(t.gap)) && (o = !0), s.setOptions(t), o && this.adjustPaneViewport(i, !0, !0, !0, !0);
      }
    }
  }
  getDrawPaneById(t) {
    return t === L.CANDLE ? this._candlePane : t === L.X_AXIS ? this._xAxisPane : this._drawPanes.find((s) => s.getId() === t) ?? null;
  }
  getContainer() {
    return this._container;
  }
  getChartStore() {
    return this._chartStore;
  }
  getXAxisPane() {
    return this._xAxisPane;
  }
  getAllDrawPanes() {
    return this._drawPanes;
  }
  getAllSeparatorPanes() {
    return this._separatorPanes;
  }
  adjustPaneViewport(t, e, s, i, o) {
    t && this._measurePaneHeight();
    let r = e;
    const a = i ?? !1, l = o ?? !1;
    (a || l) && this._drawPanes.forEach((c) => {
      const h = c.getAxisComponent().buildTicks(l);
      r || (r = h);
    }), r && this._measurePaneWidth(), (s ?? !1) && (this._xAxisPane.getAxisComponent().buildTicks(!0), this.updatePane(F.All));
  }
  updatePane(t, e) {
    C(e) ? this.getDrawPaneById(e)?.update(t) : (this._separatorPanes.forEach((s) => {
      s.update(t);
    }), this._drawPanes.forEach((s) => {
      s.update(t);
    }));
  }
  crosshairChange(t) {
    const e = this._chartStore.getActionStore();
    if (e.has(et.OnCrosshairChange)) {
      const s = {};
      this._drawPanes.forEach((i) => {
        const o = i.getId(), r = {};
        this._chartStore.getIndicatorStore().getInstances(o).forEach((l) => {
          const c = l.getIndicator(), h = c.result;
          r[c.name] = h[t.dataIndex ?? h.length - 1];
        }), s[o] = r;
      }), D(t.paneId) && e.execute(et.OnCrosshairChange, {
        ...t,
        indicatorData: s
      });
    }
  }
  getDom(t, e) {
    if (D(t)) {
      const s = this.getDrawPaneById(t);
      if (s !== null)
        switch (e ?? "root") {
          case "root":
            return s.getContainer();
          case "main":
            return s.getMainWidget().getContainer();
          case "yAxis":
            return s.getYAxisWidget()?.getContainer() ?? null;
        }
    } else
      return this._chartContainer;
    return null;
  }
  getSize(t, e) {
    if (C(t)) {
      const s = this.getDrawPaneById(t);
      if (s !== null)
        switch (e ?? "root") {
          case "root":
            return s.getBounding();
          case "main":
            return s.getMainWidget().getBounding();
          case "yAxis":
            return s.getYAxisWidget()?.getBounding() ?? null;
        }
    } else
      return {
        width: Math.floor(this._chartContainer.clientWidth),
        height: Math.floor(this._chartContainer.clientHeight),
        left: 0,
        top: 0,
        right: 0,
        bottom: 0
      };
    return null;
  }
  setStyles(t) {
    this._chartStore.setOptions({ styles: t });
    let e;
    D(t) ? e = fs(t) : e = t, C(e?.yAxis?.type) && this._candlePane?.getAxisComponent().setAutoCalcTickFlag(!0), this.adjustPaneViewport(!0, !0, !0, !0, !0);
  }
  getStyles() {
    return this._chartStore.getStyles();
  }
  setLocale(t) {
    this._chartStore.setOptions({ locale: t }), this.adjustPaneViewport(!0, !0, !0, !0, !0);
  }
  getLocale() {
    return this._chartStore.getLocale();
  }
  setCustomApi(t) {
    this._chartStore.setOptions({ customApi: t }), this.adjustPaneViewport(!0, !0, !0, !0, !0);
  }
  setPriceVolumePrecision(t, e) {
    this._chartStore.setPrecision({
      price: t,
      volume: e
    });
  }
  getPriceVolumePrecision() {
    return this._chartStore.getPrecision();
  }
  setTimezone(t) {
    this._chartStore.setOptions({ timezone: t }), this._xAxisPane.getAxisComponent().buildTicks(!0), this._xAxisPane.update(F.Drawer);
  }
  getTimezone() {
    return this._chartStore.getTimeScaleStore().getTimezone();
  }
  setOffsetRightDistance(t) {
    this._chartStore.getTimeScaleStore().setOffsetRightDistance(t, !0);
  }
  getOffsetRightDistance() {
    return this._chartStore.getTimeScaleStore().getOffsetRightDistance();
  }
  setMaxOffsetLeftDistance(t) {
    t < 0 || this._chartStore.getTimeScaleStore().setMaxOffsetLeftDistance(t);
  }
  setMaxOffsetRightDistance(t) {
    t < 0 || this._chartStore.getTimeScaleStore().setMaxOffsetRightDistance(t);
  }
  setLeftMinVisibleBarCount(t) {
    t < 0 || this._chartStore.getTimeScaleStore().setLeftMinVisibleBarCount(Math.ceil(t));
  }
  setRightMinVisibleBarCount(t) {
    t < 0 || this._chartStore.getTimeScaleStore().setRightMinVisibleBarCount(Math.ceil(t));
  }
  setBarSpace(t) {
    this._chartStore.getTimeScaleStore().setBarSpace(t);
  }
  getBarSpace() {
    return this._chartStore.getTimeScaleStore().getBarSpace().bar;
  }
  getVisibleRange() {
    return this._chartStore.getTimeScaleStore().getVisibleRange();
  }
  clearData() {
    this._chartStore.clear();
  }
  getDataList() {
    return this._chartStore.getDataList();
  }
  applyNewData(t, e, s) {
    this._chartStore.addData(t, ot.Init, e).then(() => {
    }).catch(() => {
    }).finally(() => {
      s?.();
    });
  }
  /**
   * @deprecated
   * Since v9.8.0 deprecated, since v10 removed
   */
  applyMoreData(t, e, s) {
    this._chartStore.addData(t, ot.Forward, e ?? !0).then(() => {
    }).catch(() => {
    }).finally(() => {
      s?.();
    });
  }
  updateData(t, e) {
    this._chartStore.addData(t).then(() => {
    }).catch(() => {
    }).finally(() => {
      e?.();
    });
  }
  /**
   * @deprecated
   * Since v9.8.0 deprecated, since v10 removed
   */
  loadMore(t) {
    this._chartStore.setLoadMoreCallback(t);
  }
  setLoadDataCallback(t) {
    this._chartStore.setLoadDataCallback(t);
  }
  createIndicator(t, e, s, i) {
    const o = D(t) ? { name: t } : t;
    if (cs(o.name) === null)
      return null;
    let r = s?.id;
    const a = this.getDrawPaneById(r ?? "");
    if (a !== null)
      this._chartStore.getIndicatorStore().addInstance(o, r ?? "", e ?? !1).then((l) => {
        this._setPaneOptions(
          s ?? {},
          a.getAxisComponent().buildTicks(!0) ?? !1
        );
      }).catch((l) => {
      });
    else {
      r ??= ls(L.INDICATOR);
      const l = this._createPane(Os, r, s ?? {}), c = s?.height ?? an;
      l.setBounding({ height: c }), this._chartStore.getIndicatorStore().addInstance(o, r, e ?? !1).finally(() => {
        this.adjustPaneViewport(!0, !0, !0, !0, !0), i?.();
      });
    }
    return r ?? null;
  }
  overrideIndicator(t, e, s) {
    this._chartStore.getIndicatorStore().override(t, e ?? null).then(([i, o]) => {
      (i || o) && (this.adjustPaneViewport(!1, o, !0, o), s?.());
    }).catch(() => {
    });
  }
  getIndicatorByPaneId(t, e) {
    return this._chartStore.getIndicatorStore().getInstanceByPaneId(t, e);
  }
  removeIndicator(t, e) {
    const s = this._chartStore.getIndicatorStore();
    if (s.removeInstance(t, e)) {
      let o = !1;
      if (t !== L.CANDLE && !s.hasInstances(t)) {
        const r = this.getDrawPaneById(t), a = this._drawPanes.findIndex((l) => l.getId() === t);
        if (r !== null) {
          o = !0;
          const l = this._separatorPanes.get(r);
          if (C(l)) {
            const h = l?.getTopPane();
            for (const u of this._separatorPanes)
              if (u[1].getTopPane().getId() === r.getId()) {
                u[1].setTopPane(h);
                break;
              }
            l.destroy(), this._separatorPanes.delete(r);
          }
          this._drawPanes.splice(a, 1), r.destroy();
          let c = this._drawPanes[0];
          C(c) && c.getId() === L.X_AXIS && (c = this._drawPanes[1]), this._separatorPanes.get(c)?.destroy(), this._separatorPanes.delete(c);
        }
      }
      this.adjustPaneViewport(o, !0, !0, !0, !0);
    }
  }
  createOverlay(t, e) {
    let s = [];
    D(t) ? s = [{ name: t }] : rt(t) ? s = t.map(
      (r) => D(r) ? { name: r } : r
    ) : s = [t];
    let i = !0;
    (!C(e) || this.getDrawPaneById(e) === null) && (e = L.CANDLE, i = !1);
    const o = this._chartStore.getOverlayStore().addInstances(s, e, i);
    return rt(t) ? o : o[0];
  }
  getOverlayById(t) {
    return this._chartStore.getOverlayStore().getInstanceById(t)?.getOverlay() ?? null;
  }
  overrideOverlay(t) {
    this._chartStore.getOverlayStore().override(t);
  }
  removeOverlay(t) {
    let e;
    C(t) && (D(t) ? e = { id: t } : e = t), this._chartStore.getOverlayStore().removeInstance(e);
  }
  setPaneOptions(t) {
    this._setPaneOptions(t, !1);
  }
  setZoomEnabled(t) {
    this._chartStore.getTimeScaleStore().setZoomEnabled(t);
  }
  isZoomEnabled() {
    return this._chartStore.getTimeScaleStore().getZoomEnabled();
  }
  setScrollEnabled(t) {
    this._chartStore.getTimeScaleStore().setScrollEnabled(t);
  }
  isScrollEnabled() {
    return this._chartStore.getTimeScaleStore().getScrollEnabled();
  }
  scrollByDistance(t, e) {
    const s = E(e) && e > 0 ? e : 0, i = this._chartStore.getTimeScaleStore();
    if (i.startScroll(), s > 0) {
      const o = new Ie({ duration: s });
      o.doFrame((r) => {
        const a = t * (r / s);
        i.scroll(a);
      }), o.start();
    } else
      i.scroll(t);
  }
  scrollToRealTime(t) {
    const e = this._chartStore.getTimeScaleStore(), { bar: s } = e.getBarSpace(), o = (e.getLastBarRightSideDiffBarCount() - e.getInitialOffsetRightDistance() / s) * s;
    this.scrollByDistance(o, t);
  }
  scrollToDataIndex(t, e) {
    const s = this._chartStore.getTimeScaleStore(), i = (s.getLastBarRightSideDiffBarCount() + (this.getDataList().length - 1 - t)) * s.getBarSpace().bar;
    this.scrollByDistance(i, e);
  }
  scrollToTimestamp(t, e) {
    const s = Te(
      this.getDataList(),
      "timestamp",
      t
    );
    this.scrollToDataIndex(s, e);
  }
  zoomAtCoordinate(t, e, s) {
    const i = E(s) && s > 0 ? s : 0, o = this._chartStore.getTimeScaleStore(), { bar: r } = o.getBarSpace(), l = r * t - r;
    if (i > 0) {
      let c = 0;
      const h = new Ie({ duration: i });
      h.doFrame((u) => {
        const d = l * (u / i), g = (d - c) / o.getBarSpace().bar * Ee;
        o.zoom(g, e), c = d;
      }), h.start();
    } else
      o.zoom(l / r * Ee, e);
  }
  zoomAtDataIndex(t, e, s) {
    const i = this._chartStore.getTimeScaleStore().dataIndexToCoordinate(e);
    this.zoomAtCoordinate(t, { x: i, y: 0 }, s);
  }
  zoomAtTimestamp(t, e, s) {
    const i = Te(
      this.getDataList(),
      "timestamp",
      e
    );
    this.zoomAtDataIndex(t, i, s);
  }
  convertToPixel(t, e) {
    const { paneId: s = L.CANDLE, absolute: i = !1 } = e;
    let o = [];
    if (s !== L.X_AXIS) {
      const r = this.getDrawPaneById(s);
      if (r !== null) {
        const a = this._chartStore.getTimeScaleStore(), l = r.getBounding(), c = new Array().concat(t), h = this._xAxisPane.getAxisComponent(), u = r.getAxisComponent();
        o = c.map((d) => {
          const g = {};
          let m = d.dataIndex;
          if (E(d.timestamp) && (m = a.timestampToDataIndex(d.timestamp)), E(m) && (g.x = h?.convertToPixel(m)), E(d.value)) {
            const f = u?.convertToPixel(d.value);
            g.y = i ? l.top + f : f;
          }
          return g;
        });
      }
    }
    return rt(t) ? o : o[0] ?? {};
  }
  convertFromPixel(t, e) {
    const { paneId: s = L.CANDLE, absolute: i = !1 } = e;
    let o = [];
    if (s !== L.X_AXIS) {
      const r = this.getDrawPaneById(s);
      if (r !== null) {
        const a = this._chartStore.getTimeScaleStore(), l = r.getBounding(), c = new Array().concat(t), h = this._xAxisPane.getAxisComponent(), u = r.getAxisComponent();
        o = c.map((d) => {
          const g = {};
          if (E(d.x)) {
            const m = h?.convertFromPixel(d.x) ?? -1;
            g.dataIndex = m, g.timestamp = a.dataIndexToTimestamp(m) ?? void 0;
          }
          if (E(d.y)) {
            const m = i ? d.y - l.top : d.y;
            g.value = u.convertFromPixel(m);
          }
          return g;
        });
      }
    }
    return rt(t) ? o : o[0] ?? {};
  }
  executeAction(t, e) {
    switch (t) {
      case et.OnCrosshairChange: {
        const s = { ...e };
        s.paneId = s.paneId ?? L.CANDLE, this._chartStore.getTooltipStore().setCrosshair(s);
        break;
      }
    }
  }
  subscribeAction(t, e) {
    this._chartStore.getActionStore().subscribe(t, e);
  }
  unsubscribeAction(t, e) {
    this._chartStore.getActionStore().unsubscribe(t, e);
  }
  getConvertPictureUrl(t, e, s) {
    const i = this._chartContainer.clientWidth, o = this._chartContainer.clientHeight, r = ft("canvas", {
      width: `${i}px`,
      height: `${o}px`,
      boxSizing: "border-box"
    }), a = r.getContext("2d"), l = yt(r);
    r.width = i * l, r.height = o * l, a.scale(l, l), a.fillStyle = s ?? "#FFFFFF", a.fillRect(0, 0, i, o);
    const c = t ?? !1;
    return this._drawPanes.forEach((h) => {
      const u = this._separatorPanes.get(h);
      if (C(u)) {
        const g = u.getBounding();
        a.drawImage(
          u.getImage(c),
          g.left,
          g.top,
          g.width,
          g.height
        );
      }
      const d = h.getBounding();
      a.drawImage(
        h.getImage(c),
        0,
        d.top,
        i,
        d.height
      );
    }), r.toDataURL(`image/${e ?? "jpeg"}`);
  }
  resize() {
    this.adjustPaneViewport(!0, !0, !0, !0, !0);
  }
  destroy() {
    this._chartEvent.destroy(), this._drawPanes.forEach((t) => {
      t.destroy();
    }), this._drawPanes = [], this._separatorPanes.forEach((t) => {
      t.destroy();
    }), this._separatorPanes.clear(), this._container.removeChild(this._chartContainer);
  }
  setYScrolling(t) {
    this._chartStore.setOptions({ yScrolling: t }), this.adjustPaneViewport(!0, !0, !0, !0, !0);
  }
  getYScrolling() {
    return this._chartStore.getYScrolling();
  }
}
const re = /* @__PURE__ */ new Map();
let ro = 1;
function So() {
  return "__VERSION__";
}
function Co(n, t) {
  let e;
  if (D(n) ? e = document.getElementById(n) : e = n, e === null)
    return null;
  let s = re.get(e.id);
  if (C(s))
    return s;
  const i = `k_line_chart_${ro++}`;
  return s = new Vs(e, t), s.id = i, e.setAttribute("k-line-chart-id", i), re.set(i, s), s;
}
function wo(n) {
  let t;
  if (n instanceof Vs)
    t = n.id;
  else {
    let e;
    D(n) ? e = document.getElementById(n) : e = n, t = e?.getAttribute("k-line-chart-id") ?? null;
  }
  t !== null && (re.get(t)?.destroy(), re.delete(t));
}
const bo = {
  clone: Lt,
  merge: tt,
  isString: D,
  isNumber: E,
  isValid: C,
  isObject: at,
  isArray: rt,
  isFunction: lt,
  isBoolean: ae,
  formatValue: H,
  formatPrecision: N,
  formatBigNumber: as,
  formatDate: rs,
  formatThousands: W,
  formatFoldDecimal: z,
  calcTextWidth: jt,
  getLinearSlopeIntercept: de,
  getLinearYFromSlopeIntercept: Fe,
  getLinearYFromCoordinates: Ut,
  checkCoordinateOnArc: Is,
  checkCoordinateOnCircle: _s,
  checkCoordinateOnLine: hs,
  checkCoordinateOnPolygon: ys,
  checkCoordinateOnRect: Ss,
  checkCoordinateOnText: ws,
  drawArc: Ts,
  drawCircle: xs,
  drawLine: us,
  drawPolygon: vs,
  drawRect: Be,
  drawText: Re,
  drawRectText: xn
};
export {
  et as ActionType,
  ns as CandleTooltipRectPosition,
  O as CandleType,
  oo as DomPosition,
  U as FormatDateType,
  st as IndicatorSeries,
  Q as LineType,
  se as OverlayMode,
  V as PolygonType,
  Qt as TooltipIconPosition,
  we as TooltipShowRule,
  Ct as TooltipShowType,
  Ft as YAxisPosition,
  G as YAxisType,
  wo as dispose,
  po as getFigureClass,
  ho as getOverlayClass,
  fo as getSupportedFigures,
  lo as getSupportedIndicators,
  xo as getSupportedLocales,
  uo as getSupportedOverlays,
  Co as init,
  mo as registerFigure,
  ao as registerIndicator,
  _o as registerLocale,
  co as registerOverlay,
  go as registerStyles,
  vo as registerXAxis,
  yo as registerYAxis,
  bo as utils,
  So as version
};

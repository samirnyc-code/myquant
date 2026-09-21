#!/usr/bin/env python3
"""Build the interactive regime-tracker HTML artifact from regime_data.json."""
import json, argparse

TEMPLATE = r"""<title>__TITLE__</title>
<style>
.viz-root {
  color-scheme: light;
  --surface-1:      #fcfcfb;
  --page:           #f9f9f7;
  --text-primary:   #0b0b0b;
  --text-secondary: #52514e;
  --text-muted:     #898781;
  --grid:           #e1e0d9;
  --axis:           #c3c2b7;
  --border:         rgba(11,11,11,0.10);
  --good:           #0ca30c;
  --critical:       #d03b3b;
  --warning:        #fab219;
  --undefined:      #898781;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) .viz-root {
    color-scheme: dark;
    --surface-1:      #1a1a19;
    --page:           #0d0d0d;
    --text-primary:   #ffffff;
    --text-secondary: #c3c2b7;
    --text-muted:     #898781;
    --grid:           #2c2c2a;
    --axis:           #383835;
    --border:         rgba(255,255,255,0.10);
    --good:           #0ca30c;
    --critical:       #e66767;
    --warning:        #c98500;
  }
}
:root[data-theme="dark"] .viz-root {
  color-scheme: dark;
  --surface-1:      #1a1a19;
  --page:           #0d0d0d;
  --text-primary:   #ffffff;
  --text-secondary: #c3c2b7;
  --text-muted:     #898781;
  --grid:           #2c2c2a;
  --axis:           #383835;
  --border:         rgba(255,255,255,0.10);
  --good:           #0ca30c;
  --critical:       #e66767;
  --warning:        #c98500;
}
* { box-sizing: border-box; }
body { background: var(--page); }
.viz-root {
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  background: var(--page);
  padding: 20px;
  min-height: 100vh;
}
.card {
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px 20px 12px;
  max-width: 1400px;
  margin: 0 auto;
}
h1 {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 2px;
}
.subtitle {
  font-size: 12.5px;
  color: var(--text-secondary);
  margin: 0 0 14px;
}
.legend {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  margin-bottom: 10px;
  font-size: 12.5px;
  color: var(--text-primary);
}
.legend-item { display: flex; align-items: center; gap: 6px; }
.swatch { width: 12px; height: 12px; border-radius: 3px; flex: none; }
.chart-wrap { position: relative; width: 100%; height: 520px; }
#bands { position: absolute; inset: 0; pointer-events: none; z-index: 0; }
.band { position: absolute; top: 0; bottom: 0; }
#chart { position: absolute; inset: 0; z-index: 1; }
.tooltip {
  position: absolute;
  display: none;
  pointer-events: none;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 11.5px;
  color: var(--text-primary);
  box-shadow: 0 4px 16px rgba(0,0,0,0.12);
  z-index: 5;
  line-height: 1.5;
  white-space: nowrap;
}
.tooltip .row { display: flex; justify-content: space-between; gap: 14px; }
.tooltip .k { color: var(--text-secondary); }
.foot-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
  padding-top: 10px;
  border-top: 1px solid var(--grid);
}
.hint { font-size: 11px; color: var(--text-muted); }
.table-toggle {
  font-size: 11.5px;
  color: var(--text-secondary);
  background: transparent;
  border: 1px solid var(--axis);
  border-radius: 6px;
  padding: 4px 10px;
  cursor: pointer;
  font-family: inherit;
}
.table-toggle:hover { color: var(--text-primary); border-color: var(--text-secondary); }
#tableView { display: none; margin-top: 14px; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--grid); color: var(--text-primary); }
th { color: var(--text-secondary); font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.02em; }
td.regime-cell { display: flex; align-items: center; gap: 6px; }
</style>

<div class="viz-root">
  <div class="card">
    <h1>__TITLE__</h1>
    <p class="subtitle">Bull / Bear / Trading-range classification from mywedge swing structure -- major pivots only, break-of-structure invalidation (HH+HL / LH+LL, ends on a break of the last HL / LH)</p>
    <div class="legend">
      <div class="legend-item"><span class="swatch" style="background:var(--good)"></span>Bull &mdash; higher highs + higher lows</div>
      <div class="legend-item"><span class="swatch" style="background:var(--critical)"></span>Bear &mdash; lower highs + lower lows</div>
      <div class="legend-item"><span class="swatch" style="background:var(--warning)"></span>Range &mdash; mixed structure</div>
      <div class="legend-item"><span class="swatch" style="background:#eb6834;border-radius:50%"></span>Major pivot (drives regime)</div>
      <div class="legend-item"><span class="swatch" style="background:rgba(235,104,52,0.4);border-radius:50%"></span>Minor pivot (context only)</div>
    </div>
    <div class="chart-wrap">
      <div id="bands"></div>
      <div id="chart"></div>
      <div class="tooltip" id="tooltip"></div>
    </div>
    <div class="foot-row">
      <span class="hint">Scroll / drag to zoom &amp; pan &middot; hover for bar detail</span>
      <button class="table-toggle" id="tableToggle">Show segment table</button>
    </div>
    <div id="tableView">
      <table>
        <thead><tr><th>Regime</th><th>Start</th><th>End</th><th>Bars</th></tr></thead>
        <tbody id="tableBody"></tbody>
      </table>
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<script>
const DATA = __DATA_JSON__;

const REGIME_VAR = { Bull: "--good", Bear: "--critical", Range: "--warning" };

function cssVar(name) {
  return getComputedStyle(document.querySelector(".viz-root")).getPropertyValue(name).trim();
}

// lightweight-charts needs UTCTimestamp (epoch seconds) for intraday bars --
// a date-only string collapses every same-day bar onto one point. Daily+ bars
// use the 'yyyy-mm-dd' business-day string instead (cleaner axis labels).
const epochSecs = DATA.bars.map(b => Math.floor(new Date(b.t).getTime() / 1000));
const isIntraday = epochSecs.length > 1 && (epochSecs[1] - epochSecs[0]) < 20 * 3600;

const bars = DATA.bars.map((b, i) => ({
  time: isIntraday ? epochSecs[i] : b.t.slice(0, 10),
  open: b.o, high: b.h, low: b.l, close: b.c,
}));

function fmtTime(t) {
  if (!isIntraday) return t;
  const d = new Date(t * 1000);
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

const chartEl = document.getElementById("chart");
const bandsEl = document.getElementById("bands");
const tooltipEl = document.getElementById("tooltip");
const wrapEl = document.querySelector(".chart-wrap");

function isDark() {
  const explicit = document.documentElement.getAttribute("data-theme");
  if (explicit === "dark") return true;
  if (explicit === "light") return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function chartColors() {
  return {
    grid: cssVar("--grid"),
    text: cssVar("--text-secondary"),
    axis: cssVar("--axis"),
  };
}

// the chart's own canvas background must stay transparent so the regime-band
// divs behind it (#bands, z-index 0) show through -- lightweight-charts paints
// an opaque fill otherwise, which sits in front of any DOM behind the canvas
const chart = LightweightCharts.createChart(chartEl, {
  layout: { background: { color: "transparent" }, textColor: chartColors().text, fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif" },
  grid: { vertLines: { color: chartColors().grid }, horzLines: { color: chartColors().grid } },
  rightPriceScale: { borderColor: chartColors().axis },
  timeScale: { borderColor: chartColors().axis, timeVisible: isIntraday, secondsVisible: false },
  crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
  autoSize: true,
});

// classic monochrome OHLC bars (hollow up, solid down) so bar direction doesn't
// visually compete with the regime bands, which carry the actual signal
const series = chart.addCandlestickSeries({
  upColor: cssVar("--surface-1"), downColor: cssVar("--text-primary"),
  borderUpColor: cssVar("--text-primary"), borderDownColor: cssVar("--text-primary"),
  wickUpColor: cssVar("--text-primary"), wickDownColor: cssVar("--text-primary"),
});
series.setData(bars);
chart.timeScale().fitContent();

// swing pivot markers -- small dots just outside the bar (below swing lows,
// above swing highs), like NinjaTrader's SwingLow/SwingHigh dot style. Major
// pivots (drove the regime classification) are bigger and fully opaque; minor
// ones (context only) are smaller and faded.
const pivotStyle = p => p.major
  ? { color: "rgba(235,104,52,0.95)", shape: "circle", size: 1 }
  : { color: "rgba(235,104,52,0.4)", shape: "circle", size: 0.4 };
const pivotMarkers = [
  ...DATA.pivot_lows.map(p => ({ time: bars[p.i].time, position: "belowBar", ...pivotStyle(p) })),
  ...DATA.pivot_highs.map(p => ({ time: bars[p.i].time, position: "aboveBar", ...pivotStyle(p) })),
].sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0));
series.setMarkers(pivotMarkers);

function renderBands() {
  bandsEl.innerHTML = "";
  const ts = chart.timeScale();
  const n = bars.length;
  DATA.segments.forEach(seg => {
    const startIdx = seg.start;
    const endIdx = Math.min(seg.end, n - 1);
    const x0 = ts.timeToCoordinate(bars[startIdx].time);
    const x1 = ts.timeToCoordinate(bars[endIdx].time);
    if (x0 === null || x1 === null) return;
    const left = Math.min(x0, x1);
    const width = Math.max(Math.abs(x1 - x0), 1);
    const div = document.createElement("div");
    div.className = "band";
    div.style.left = left + "px";
    div.style.width = width + "px";
    div.style.background = `color-mix(in srgb, var(${REGIME_VAR[seg.regime]}) 28%, transparent)`;
    bandsEl.appendChild(div);
  });
}

chart.timeScale().subscribeVisibleTimeRangeChange(renderBands);
new ResizeObserver(renderBands).observe(chartEl);
setTimeout(renderBands, 50);

// regime + bar-index lookup per bar time for the tooltip
const regimeByTime = {};
const barIndexByTime = {};
bars.forEach((b, i) => { regimeByTime[b.time] = DATA.regime[i]; barIndexByTime[b.time] = i + 1; });

chart.subscribeCrosshairMove(param => {
  if (!param.point || !param.time || !param.seriesData.size) {
    tooltipEl.style.display = "none";
    return;
  }
  const d = param.seriesData.get(series);
  if (!d) { tooltipEl.style.display = "none"; return; }
  const regime = regimeByTime[param.time] || "Range";
  tooltipEl.innerHTML = `
    <div class="row"><span class="k">Bar</span><span>#${barIndexByTime[param.time]}</span></div>
    <div class="row"><span class="k">Date</span><span>${fmtTime(param.time)}</span></div>
    <div class="row"><span class="k">O</span><span>${d.open.toFixed(2)}</span></div>
    <div class="row"><span class="k">H</span><span>${d.high.toFixed(2)}</span></div>
    <div class="row"><span class="k">L</span><span>${d.low.toFixed(2)}</span></div>
    <div class="row"><span class="k">C</span><span>${d.close.toFixed(2)}</span></div>
    <div class="row"><span class="k">Regime</span><span>${regime}</span></div>
  `;
  const wrapRect = wrapEl.getBoundingClientRect();
  let left = param.point.x + 16;
  if (left + 150 > wrapRect.width) left = param.point.x - 166;
  tooltipEl.style.left = left + "px";
  tooltipEl.style.top = Math.max(param.point.y - 10, 0) + "px";
  tooltipEl.style.display = "block";
});

// segment table
const tbody = document.getElementById("tableBody");
DATA.segments.forEach(seg => {
  const endIdx = Math.min(seg.end, bars.length - 1);
  const tr = document.createElement("tr");
  tr.innerHTML = `
    <td class="regime-cell"><span class="swatch" style="background:var(${REGIME_VAR[seg.regime]})"></span>${seg.regime}</td>
    <td>${fmtTime(bars[seg.start].time)}</td>
    <td>${fmtTime(bars[endIdx].time)}</td>
    <td>${endIdx - seg.start + 1}</td>
  `;
  tbody.appendChild(tr);
});
document.getElementById("tableToggle").addEventListener("click", (e) => {
  const tv = document.getElementById("tableView");
  const show = tv.style.display !== "block";
  tv.style.display = show ? "block" : "none";
  e.target.textContent = show ? "Hide segment table" : "Show segment table";
});
</script>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", nargs="?", default="regime_data.json")
    ap.add_argument("--out", default="regime_artifact.html")
    ap.add_argument("--title", default="Regime Tracker")
    a = ap.parse_args()

    with open(a.data) as f:
        data = json.load(f)

    html = TEMPLATE.replace("__TITLE__", a.title).replace("__DATA_JSON__", json.dumps(data))
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()

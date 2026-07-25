"""mq_regime_page_20260725.py — MC page for the 19-year MQ-style gamma regime series.

Renders data/regime/mq_regime_daily_2007_2026_v2.csv into a self-contained HTML page at
docs/artifacts/mq_gamma_regime_19y.html (auto-listed in Mission Control's Artifact
Library, served at :8590/artifact/mq_gamma_regime_19y — no launcher restart needed)
plus the chart PNG alongside in data/regime/.

Re-run after any backfill refresh to regenerate the page.
"""
import base64
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
d = pd.read_csv(ROOT / "data" / "regime" / "mq_regime_daily_2007_2026_v2.csv",
                parse_dates=["date"]).set_index("date")

# ---- stats
pos = (d["regime"] == "positive_gamma")
flips = (pos != pos.shift()).sum() - 1
yrs = (d.index[-1] - d.index[0]).days / 365.25
stats = {
    "Days": f"{len(d):,}",
    "Range": f"{d.index[0]:%Y-%m-%d} → {d.index[-1]:%Y-%m-%d}",
    "Positive-gamma days": f"{pos.mean()*100:.1f}%",
    "Regime flips": f"{flips} (~{flips/yrs:.0f}/yr)",
    "Latest": (f"{d.index[-1]:%Y-%m-%d}: {d['regime'].iloc[-1].replace('_',' ')} "
               f"(spot {d['spot'].iloc[-1]:,.0f} vs HVL {d['hvl'].iloc[-1]:,.0f})"),
}

# ---- chart: spot + HVL, negative-gamma spans shaded (validated 2-series palette)
BLUE, ORANGE, MUT, INK, SURF = "#2a78d6", "#eb6834", "#898781", "#0b0b0b", "#fcfcfb"
w = d.resample("W").last().dropna(subset=["spot", "hvl"])
fig, ax = plt.subplots(figsize=(13, 5.5), dpi=130)
fig.patch.set_facecolor(SURF)
ax.set_facecolor(SURF)
neg = (w["regime"] == "negative_gamma").to_numpy()
ax.fill_between(w.index, 0, 1, where=neg, transform=ax.get_xaxis_transform(),
                color=ORANGE, alpha=0.12, linewidth=0, label="negative-gamma regime")
ax.plot(w.index, w["spot"], color=BLUE, lw=1.3, label="SPX spot (weekly)")
ax.plot(w.index, w["hvl"], color=ORANGE, lw=1.0, label="HVL (computed, MQ spec)")
ax.legend(frameon=False, loc="upper left", fontsize=9)
ax.set_title("MQ-style gamma regime, 2007–2026 — HVL vs spot, shaded = negative gamma",
             color=INK, fontsize=11, loc="left")
for s in ax.spines.values():
    s.set_color(MUT)
ax.tick_params(colors=MUT, labelsize=8)
ax.grid(color="#f0efec", lw=0.6)
fig.tight_layout()
png = ROOT / "data" / "regime" / "mq_regime_19y_20260725.png"
fig.savefig(png, facecolor=SURF)
b64 = base64.b64encode(png.read_bytes()).decode()

# ---- html
recent = d.tail(30).iloc[::-1]
rows = "\n".join(
    f"<tr><td>{ix:%Y-%m-%d}</td><td>{r.spot:,.0f}</td><td>{r.hvl:,.0f}</td>"
    f"<td>{r.cr:,.0f}</td><td>{r.ps:,.0f}</td>"
    f"<td class='{'pg' if r.regime=='positive_gamma' else 'ng'}'>{r.regime.replace('_',' ')}</td></tr>"
    for ix, r in recent.iterrows())
stat_html = "\n".join(f"<div class='tile'><div class='k'>{k}</div><div class='v'>{v}</div></div>"
                      for k, v in stats.items())
html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>MQ Gamma Regime — 19y Backfill</title>
<style>
 body{{background:#fcfcfb;color:#0b0b0b;font:14px/1.5 system-ui,sans-serif;margin:24px;max-width:1200px}}
 h1{{font-size:19px}} h2{{font-size:15px;margin-top:28px}}
 .tiles{{display:flex;gap:12px;flex-wrap:wrap}}
 .tile{{background:#f9f9f7;border:1px solid #e5e4e0;border-radius:8px;padding:10px 14px}}
 .k{{color:#52514e;font-size:11px;text-transform:uppercase;letter-spacing:.04em}}
 .v{{font-size:15px;font-weight:600}}
 img{{max-width:100%;border:1px solid #e5e4e0;border-radius:8px;margin-top:8px}}
 table{{border-collapse:collapse;margin-top:8px}} td,th{{padding:4px 12px;border-bottom:1px solid #eee;text-align:right}}
 th{{color:#52514e;font-size:11px;text-transform:uppercase}} td:first-child,th:first-child{{text-align:left}}
 .pg{{color:#0ca30c}} .ng{{color:#d03b3b}}
 .meta{{color:#52514e;font-size:12px}}
</style></head><body>
<h1>MQ-style Gamma Regime — 19-Year Backfill (cracked spec)</h1>
<p class="meta">Source: <code>data/regime/mq_regime_daily_2007_2026_v2.csv</code>
(<a href="http://localhost:8620/">Data Catalog</a> family <code>mq_gamma_regime</code>) ·
spec: S84 reverse-engineering (<code>docs/research_notes/mq_level_reveng_20260724.md</code>) ·
validated vs 1,181 MenthorQ days: regime agreement 95.1%, HVL medAE 10pt ·
pre-2022 expect ~89–92% fidelity (no daily expiries then) · generated {dt.date.today()}</p>
<div class="tiles">{stat_html}</div>
<img src="data:image/png;base64,{b64}" alt="19y gamma regime chart">
<h2>Last 30 sessions</h2>
<table><tr><th>date</th><th>spot</th><th>HVL</th><th>CR</th><th>PS</th><th>regime</th></tr>
{rows}</table>
</body></html>"""
out = ROOT / "docs" / "artifacts" / "mq_gamma_regime_19y.html"
out.write_text(html, encoding="utf-8")
print("saved:", out)
print("saved:", png)

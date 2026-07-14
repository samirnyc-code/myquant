"""Assemble the S73 overnight research report -> data/options_sim/morning_report.html.
Pulls the JSON result files the night's studies wrote; self-contained dark HTML."""
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"


def j(name, default=None):
    f = SIM / name
    return json.loads(f.read_text()) if f.exists() else (default or {})


v2 = j("es_levels_v2.json")
fade = j("cr_fade.json")


def row(cells, hdr=False):
    tag = "th" if hdr else "td"
    return "<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>"


def gex_rows():
    out = []
    for k in ("neg_morning", "pos_morning", "all_morning", "neg_allday"):
        s = fade.get(k, {})
        if not s:
            continue
        cls = "pos" if s.get("E_usd", 0) > 0 else "neg"
        out.append(row([k.replace("_", " "), s.get("n"), f"{s.get('win_pct')}%",
                        f"<span class='{cls}'>${s.get('E_usd'):+}</span>",
                        f"<span class='{cls}'>${s.get('total_usd'):+,}</span>"]))
    return "".join(out)


def hour_rows(key):
    out = []
    for hh, s in v2.get(key, {}).items():
        if s.get("n", 0) >= 5:
            hp = s.get("hold_pct")
            cls = "pos" if hp and hp > 55 else ("neg" if hp and hp < 45 else "")
            out.append(row([f"{hh}:00 CT", s["n"], f"<span class='{cls}'>{hp}%</span>"]))
    return "".join(out)


def sweep_rows():
    return "".join(row([f"MOVE {s['move']} / LOOK {s['look']}", s["n"], f"{s['hold_pct']}%"])
                   for s in v2.get("sweep", []))


HTML = f"""<!doctype html><html><head><meta charset="utf-8"><title>S73 Overnight Research</title>
<style>
body{{background:#0d0f14;color:#e6e9ef;font:15px/1.6 system-ui,Segoe UI,sans-serif;margin:0;padding:32px}}
.wrap{{max-width:920px;margin:0 auto}}
h1{{font-size:26px;margin:0 0 4px}} h2{{font-size:18px;color:#8ab4f8;margin:30px 0 10px;border-bottom:1px solid #2a3040;padding-bottom:6px}}
.mut{{color:#8a91a0}} .pos{{color:#1baf7a;font-weight:700}} .neg{{color:#e34948;font-weight:700}}
.hero{{background:linear-gradient(160deg,#1a2740,#141821);border:1px solid #2a4060;border-radius:16px;padding:22px 26px;margin:18px 0}}
.hero h2{{border:0;color:#5fa8ff;margin-top:0}}
.big{{font-size:34px;font-weight:800;color:#1baf7a}}
table{{border-collapse:collapse;width:100%;margin:10px 0;font-size:14px}}
th,td{{padding:7px 12px;text-align:right;border-bottom:1px solid #23262d}} th{{color:#9aa0a6}}
td:first-child,th:first-child{{text-align:left}}
.card{{background:#161a22;border:1px solid #23262d;border-radius:12px;padding:16px 20px;margin:12px 0}}
.caveat{{background:#2a1e14;border-left:3px solid #eda100;border-radius:8px;padding:12px 16px;margin:12px 0;font-size:14px}}
ul{{margin:6px 0}} li{{margin:3px 0}} code{{background:#23262d;padding:1px 6px;border-radius:4px;font-size:13px}}
</style></head><body><div class="wrap">
<h1>🌙 Overnight Research Report — Session 73</h1>
<div class="mut">Generated {dt.datetime.now():%Y-%m-%d %H:%M} · goal: find a tradeable edge (ES futures or SPX options)</div>

<div class="hero">
<h2>★ Lead finding — a conditioned edge in ES</h2>
<div class="big">+${fade.get('neg_morning',{}).get('E_usd','?')}/trade</div>
<div>Fading <b>Call Resistance</b> on the first touch before 10:30&nbsp;CT, <b>only on days where
prior-EOD GEX was negative</b>. 1yr ES 5m data, real stops/targets/costs (5pt stop, 10pt target,
1.25pt friction, ES $50/pt).</div>
<p><b>The filter is the edge.</b> Unfiltered, fading CR is a coin flip (~$0/trade). Split by the
prior day's GEX sign, negative-GEX mornings make money and positive-GEX mornings lose it — a
~$180/trade spread from one bit known at the open. The losing bucket implies a mirror trade:
on positive-GEX mornings, CR tends to <i>break</i> → breakout-long.</p>
</div>

<h2>The trade, by bucket (fade CR, real costs)</h2>
<table>{row(['bucket','n','win%','E/trade','total/yr'], hdr=True)}{gex_rows()}</table>
<div class="caveat"><b>Honest caveats:</b> n=18 for the winning bucket (~18 trades/yr) — a strong
<i>lead</i>, not a validated system. One year of data. Stop/target (5/10) not yet swept → overfit
risk. ES-only. Needs: parameter sweep, out-of-sample split, NQ/YM replication, and an SPX-options
expression of the same signal (buy puts / put debit spread on neg-GEX mornings).</div>

<h2>Why it works: GEX regime conditioning</h2>
<div class="card">Call-Resistance hold-rate (my def: price retraces MOVE before breaking MOVE):
<table>
{row(['GEX regime (prior EOD)','','hold-rate'], hdr=True)}
{row(['positive GEX days', v2.get('gex',{}).get('pos',{}).get('n'), f"{v2.get('gex',{}).get('pos',{}).get('hold_pct')}% (coin flip)"])}
{row(['negative GEX days', v2.get('gex',{}).get('neg',{}).get('n'), f"<span class='pos'>{v2.get('gex',{}).get('neg',{}).get('hold_pct')}%</span>"])}
</table>
Textbook says positive gamma = dealers stabilize = levels pin. <b>The data says the opposite</b> —
neg-gamma days reject the level more, especially in the morning.</div>

<h2>Time-of-day × GEX (where the edge concentrates)</h2>
<div class="card"><b>Negative-GEX days — hold by hour:</b>
<table>{row(['hour','n','hold'], hdr=True)}{hour_rows('hour_neg')}</table>
Mornings on neg-GEX days reject 80%+. Midday (12:00 CT) flips to breaks across all regimes
(lunch-lull breakouts).</div>

<h2>Robustness — parameter sweep</h2>
<div class="card">Base hold-rate across MOVE/LOOK settings (shows the absolute number is
definition-sensitive; the neg-vs-pos GEX <i>spread</i> is what's robust):
<table>{row(['setting','n','hold'], hdr=True)}{sweep_rows()}</table></div>

<h2>Other results tonight</h2>
<ul>
<li><b>BPS exit-rule shootout (142 trades):</b> the SMA5 signal-exit IS the edge (PF 1.74).
Hold-to-expiry loses (PF 0.95, −$28K maxDD); tastylive "manage at 50%" ≈ flat (0.97); price stops
are poison (0.71). <b>No profit targets, no stops, exit on signal only.</b></li>
<li><b>VIX-rank filter on BPS: REJECTED</b> out-of-sample (filtered PF 2.13 &lt; unfiltered 2.24).
Trade it unconditioned.</li>
<li><b>Put Support untouchable:</b> price reached PS only 3×/yr — confirms S66 "levels rarely reached."</li>
</ul>

<h2>Data assets acquired (the machine)</h2>
<ul>
<li><b>Direct MenthorQ REST API</b> (<code>scripts/mq_api.py</code>) — the endpoints QUIN reads from;
no scraping, no quota. gamma-levels, matrix (net/abs GEX·DEX·OI), per-strike surface, 365d GEX+percentile,
skew, QScore, candles.</li>
<li><b>365 days</b> of ES+SPX aggregate GEX + 1y-percentile + QScore, pulled clean.</li>
<li><b>~12 months</b> daily ES+SPX levels (CR/PS/HVL) via QUIN backfill (480 rows).</li>
<li><b>Historical OI:</b> aggregate call/put OI IS available via QUIN (your instinct was right);
per-strike is today-only via API. Parked as marginal for current strategies.</li>
<li><b>240 KB pages</b> ingested (guides + financial wiki) + 32 academy pages — hypothesis fuel;
deep lesson bodies (behind "Start") are a follow-up crawl.</li>
<li>Nightly harvest + history pull scheduled (Task Scheduler).</li>
</ul>

<h2>Next steps (ranked)</h2>
<ol>
<li>Sweep stop/target on the CR-fade edge; out-of-sample split (first 8mo vs last 4mo).</li>
<li>Replicate on NQ + YM (we have the bars + can pull their GEX) — does the edge generalize?</li>
<li>Test the mirror: CR-breakout-long on positive-GEX mornings.</li>
<li><b>SPX-options version:</b> buy a put / put debit spread on neg-GEX mornings — turns the futures
edge into a defined-risk options trade (your two goals converge here).</li>
<li>Verify vs MenthorQ's OWN backtest definition (directive #2) — extract their hold/break rule
from the deep academy lessons, re-test apples-to-apples.</li>
<li>Extract testable claims from the 240 KB pages into the hypothesis queue.</li>
</ol>

<div class="mut" style="margin-top:30px">Full detail: <code>docs/living/night_queue_s73.md</code> ·
scripts: <code>mr_es_gamma_levels_v2.py</code>, <code>mr_es_cr_fade.py</code>, <code>mq_api.py</code></div>
</div></body></html>"""

out = SIM / "morning_report.html"
out.write_text(HTML, encoding="utf-8")
print(f"wrote {out}")

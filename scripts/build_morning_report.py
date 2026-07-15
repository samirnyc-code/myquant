"""Assemble the S73 overnight research report (v2, night-2 rewrite)
-> data/options_sim/morning_report.html"""
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HTML = f"""<!doctype html><html><head><meta charset="utf-8"><title>S73 Overnight Research v2</title>
<style>
body{{background:#0d0f14;color:#e6e9ef;font:15px/1.6 system-ui,Segoe UI,sans-serif;margin:0;padding:32px}}
.wrap{{max-width:940px;margin:0 auto}}
h1{{font-size:26px;margin:0 0 4px}} h2{{font-size:18px;color:#8ab4f8;margin:30px 0 10px;border-bottom:1px solid #2a3040;padding-bottom:6px}}
.mut{{color:#8a91a0}} .pos{{color:#1baf7a;font-weight:700}} .neg{{color:#e34948;font-weight:700}}
.hero{{background:linear-gradient(160deg,#1a2740,#141821);border:1px solid #2a4060;border-radius:16px;padding:22px 26px;margin:18px 0}}
.hero h2{{border:0;color:#5fa8ff;margin-top:0}}
.big{{font-size:32px;font-weight:800;color:#1baf7a}}
.dead{{background:#241318;border:1px solid #58242c;border-radius:16px;padding:18px 24px;margin:18px 0}}
.dead h2{{border:0;color:#e34948;margin-top:0}}
table{{border-collapse:collapse;width:100%;margin:10px 0;font-size:14px}}
th,td{{padding:7px 12px;text-align:right;border-bottom:1px solid #23262d}} th{{color:#9aa0a6}}
td:first-child,th:first-child{{text-align:left}}
.card{{background:#161a22;border:1px solid #23262d;border-radius:12px;padding:16px 20px;margin:12px 0}}
.caveat{{background:#2a1e14;border-left:3px solid #eda100;border-radius:8px;padding:12px 16px;margin:12px 0;font-size:14px}}
ul,ol{{margin:6px 0}} li{{margin:4px 0}} code{{background:#23262d;padding:1px 6px;border-radius:4px;font-size:13px}}
</style></head><body><div class="wrap">
<h1>🌙 Overnight Research — Session 73, Night 2</h1>
<div class="mut">Generated {dt.datetime.now():%Y-%m-%d %H:%M} · the honest version, invalidations included</div>

<div class="dead">
<h2>⚠ First: last night's "CR fade edge" is RETRACTED — and why that's the system working</h2>
<p>A data audit at 4 AM found the continuous ES contract is <b>back-adjusted</b>: bars from mid-2025
sit up to <b>+465 points above</b> the actual prices MenthorQ's levels were struck at. Every
bar-vs-level "touch" in the early studies happened at wrong distances. With repaired prices
(per-day offsets derived from actual front-contract closes), the negative-GEX CR fade fires
<b>once</b> a year, not 18 times — the +$1,875 result was an artifact. The 1D-Max fade dies too.
The 18-chart artifact from last night shows fake touches — disregard it; it will be regenerated.</p>
<p><b>Credit where due:</b> your chart review ("the scale of these charts is BS", "shouldn't price
come from below?") is what pulled the thread. Eyeballs + machine caught this before a dollar
was risked on it.</p>
</div>

<div class="hero">
<h2>★ The survivor — CR-0DTE first-touch fade (repaired data)</h2>
<div class="big">+$123/trade · 60 trades/yr · OOS-positive</div>
<p>Fade (short) the <b>first touch of Call Resistance 0DTE from below</b>, any regime, stop 8 /
target 10, real friction. This is on the 0DTE levels YOU directed the study toward.</p>
<table>
<tr><th>check</th><th>result</th></tr>
<tr><td>trades/yr (first-touch)</td><td>60, spread evenly across all 12 months (2–9/mo — no regime clustering)</td></tr>
<tr><td>touch hold-rate</td><td>81.6% (103 touches incl. re-touches), holds in BOTH GEX regimes</td></tr>
<tr><td>stop/target sweep</td><td><span class="pos">36/36 cells positive</span> (E ranges +$28…+$292)</td></tr>
<tr><td>out-of-sample (last ⅓)</td><td><span class="pos">+$29/trade — degraded but positive</span> (in-sample +$170)</td></tr>
<tr><td>total / maxDD @ ref cell</td><td>+$7,400/yr vs −$1,000 maxDD</td></tr>
</table>
</div>

<h2>All levels, repaired data (fade E$ at stop8/tgt10)</h2>
<table>
<tr><th>level</th><th>touches/yr</th><th>hold%</th><th>fade E$/trade</th><th>verdict</th></tr>
<tr><td>CR 0DTE</td><td>103</td><td>81.6%</td><td class="pos">+$174</td><td>★ lead candidate (sweep+OOS pass)</td></tr>
<tr><td>PS 0DTE (fade long)</td><td>115</td><td>71.3%</td><td>+$68</td><td>second candidate — sweep next</td></tr>
<tr><td>PS major, neg-GEX</td><td>15</td><td>86.7%</td><td>+$198</td><td>promising, n small</td></tr>
<tr><td>CR major</td><td>26</td><td>80.8%</td><td>+$255</td><td>n small, watch</td></tr>
<tr><td>1D Min (fade long)</td><td>52</td><td>75.0%</td><td>+$43</td><td>thin after costs</td></tr>
<tr><td>1D Max</td><td>15</td><td>86.7%</td><td class="neg">−$79</td><td>dead as a trade</td></tr>
</table>
<div class="caveat"><b>Open caveats on the survivor:</b> price repair uses Yahoo daily offsets
(±1–2pt intraday roll-timing error possible); level-date convention verified causal for majors
(your morning paste matched QUIN's same-date row) and assumed for 0DTE; needs NQ replication +
MenthorQ-definition cross-check; n=60 is one year. Next: paper-trade it live alongside the BPS.</div>

<h2>Knowledge extraction — the corpus is mined</h2>
<div class="card">
<b>~70 testable claims</b> extracted from 240 wiki/guides/academy pages into
<code>docs/living/mq_claims_backlog.md</code>, including MenthorQ's own published stats to verify
(SPX closes below 1D Max ~85% / above 1D Min ~87%; swing-model 88% success; IV-0DTE-percentile
ROI buckets; the <b>four GEX×DEX Option-Matrix regimes</b>). Full definitions recovered: HVL =
inflection of the cumulative-gamma curve; GEX-percentile semantics; Q-Score sub-scores; update
schedules (futures levels compute 11pm ET — our causality convention is right).
<br><br><b>26 web-sourced GEX strategy ideas</b> in <code>docs/living/gex_ideas_web.md</code>, ranked by
data fit. Top pick: <b>gamma-conditioned last-30-min momentum</b> (JFE-published mechanism).
Key discipline finding: raw GEX→vol signals often collapse after VIX control — all our tests
get a VIX-residualization pass. Strategic unlock: compute our OWN GEX from OptionsDX chains →
13 years of backtests instead of 1.
</div>

<h2>Also standing from night 1 (unaffected by the bar repair)</h2>
<ul>
<li><b>BPS exit-rule shootout:</b> SMA5 signal-exit IS the edge (PF 1.74); expiry-hold and
tastylive-TP50 rejected; stops are poison. (Options data — no futures bars involved.)</li>
<li><b>VIX-rank filter on BPS: rejected</b> OOS. Trade unconditioned.</li>
<li>Paper pipeline live: day-1 trades settled, journal/marks/margin recording, daily automation scheduled.</li>
<li>MenthorQ API client + 365d GEX/skew/QScore histories + levels backfills.</li>
</ul>

<h2>Today's plan (in order)</h2>
<ol>
<li>Morning: BPS leg reconciliation at IB; daily protocol runs automatically.</li>
<li>Regenerate the setup-chart artifact from repaired bars (CR-0DTE fades this time).</li>
<li>PS-0DTE fade sweep + NQ replication of CR-0DTE.</li>
<li>Verify MenthorQ's published 1D Max/Min close-rates (their def, our data) — directive #2.</li>
<li>Start paper-trading the CR-0DTE fade rule alongside the BPS (1-lot, logged+journaled).</li>
<li>BO-PB entries: waiting on your walkthrough — building it together as agreed.</li>
</ol>

<div class="mut" style="margin-top:30px">Everything committed. Detail: <code>docs/living/night_queue_s73.md</code>,
<code>mq_claims_backlog.md</code>, <code>gex_ideas_web.md</code> · scripts <code>es_unadjust.py</code> (the repair),
<code>es_cr0_sweep.py</code> (the survivor)</div>
</div></body></html>"""

out = ROOT / "data" / "options_sim" / "morning_report.html"
out.write_text(HTML, encoding="utf-8")
print(f"wrote {out}")

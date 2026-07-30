"""Build the EminiAddict Measured-Move artifact for Mission Control.

Writes docs/artifacts/eminiaddict_measured_move_method.html — a self-contained,
themed page (the readable form of notes/RULEBOOK.md) with the ES demo chart
embedded as base64. Auto-listed in Mission Control's Artifact Library
(/artifact/eminiaddict_measured_move_method). Run from repo root or eminiaddict/.
"""
import base64
import glob
import html as _html
import json
import os
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]  # repo root
NOTES = ROOT / "eminiaddict" / "notes"
CHART = ROOT / "eminiaddict" / "figures" / "es_daily_mm_fib_dominant.png"
OUT = ROOT / "docs" / "artifacts" / "eminiaddict_measured_move_method.html"
CATALOG = ROOT / "data" / "_catalog" / "claude_artifacts.json"
TITLE = "EminiAddict Measured Move Method"  # slugifies to the file stem
DATE = "2026-07-30"

chart_b64 = base64.b64encode(CHART.read_bytes()).decode() if CHART.exists() else ""


def _inline(s):
    s = _html.escape(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    return s


def md2html(text):
    """Minimal markdown -> HTML for the chapter notes (headings, tables, lists,
    hr, bold, inline code, paragraphs). Not a general converter."""
    lines = text.split("\n")
    out, i, n = [], 0, len(lines)
    while i < n:
        ln = lines[i]
        # table block
        if ln.lstrip().startswith("|") and i + 1 < n and set(lines[i + 1].strip()) <= set("|-: "):
            rows = []
            while i < n and lines[i].lstrip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            head, body = rows[0], rows[2:]
            t = ["<table><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in head) + "</tr>"]
            for r in body:
                t.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>")
            out.append("".join(t) + "</table>")
            continue
        # headings
        m = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if m:
            lvl = min(len(m.group(1)) + 1, 6)  # bump so chapter # -> h3 under section
            out.append(f"<h{lvl}>{_inline(m.group(2))}</h{lvl}>")
            i += 1
            continue
        # hr
        if ln.strip() in ("---", "***", "___"):
            out.append("<hr>")
            i += 1
            continue
        # unordered list
        if re.match(r"^\s*[-*]\s+", ln):
            items = []
            while i < n and re.match(r"^\s*[-*]\s+", lines[i]):
                items.append("<li>" + _inline(re.sub(r"^\s*[-*]\s+", "", lines[i])) + "</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        # ordered list
        if re.match(r"^\s*\d+\.\s+", ln):
            items = []
            while i < n and re.match(r"^\s*\d+\.\s+", lines[i]):
                items.append("<li>" + _inline(re.sub(r"^\s*\d+\.\s+", "", lines[i])) + "</li>")
                i += 1
            out.append("<ol>" + "".join(items) + "</ol>")
            continue
        # paragraph (gather until blank)
        if ln.strip():
            para = [ln]
            i += 1
            while i < n and lines[i].strip() and not re.match(r"^(\s*[-*]\s+|\s*\d+\.\s+|#{1,6}\s|\|)", lines[i]):
                para.append(lines[i])
                i += 1
            out.append("<p>" + _inline(" ".join(para)) + "</p>")
            continue
        i += 1
    return "\n".join(out)


# --- assemble chapter-by-chapter section from notes/chNN_*.md ---
chap_files = sorted(glob.glob(str(NOTES / "ch[0-9][0-9]_*.md")))
chap_nav, chap_sec = [], []
for f in chap_files:
    stem = pathlib.Path(f).stem              # e.g. ch06_setups
    num = stem[2:4]
    body_md = pathlib.Path(f).read_text(encoding="utf-8")
    first = body_md.lstrip().split("\n", 1)[0].lstrip("# ").strip()  # "# Ch N — Title"
    chap_nav.append(f'<a href="#{stem}">Ch {int(num)} — {_html.escape(first.split("—")[-1].strip())}</a>')
    chap_sec.append(f'<section id="{stem}" class="chap"><div class="chaphd">{_html.escape(first)}</div>'
                    + md2html(body_md.split("\n", 1)[1] if "\n" in body_md else "") + "</section>")
CHAPTERS = ("".join(chap_sec)) if chap_sec else "<p class='lead'>No chapter notes found.</p>"
CHAP_NAV = "".join(chap_nav)

CSS = """
:root{--bg:#0d1117;--card:#161b22;--chip:#30363d;--fg:#e6edf3;--muted:#8b949e;
  --blue:#58a6ff;--green:#3fb950;--red:#f85149;--yellow:#e3b341}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font:14px/1.6 -apple-system,Segoe UI,Roboto,sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--chip);
  padding:14px 24px;display:flex;align-items:center;gap:12px;z-index:10}
header h1{font-size:17px;margin:0}
.tag{font-size:11px;color:var(--muted);border:1px solid var(--chip);border-radius:999px;padding:2px 10px}
a{color:var(--blue);text-decoration:none}
.wrap{max-width:1000px;margin:0 auto;padding:8px 24px 80px}
.toc{background:var(--card);border:1px solid var(--chip);border-radius:10px;padding:12px 18px;
  margin:18px 0;columns:2;font-size:13px}
.toc a{display:block;padding:2px 0}
h2{font-size:16px;margin:34px 0 10px;padding-top:8px;border-top:1px solid var(--chip);color:var(--fg)}
h3{font-size:14px;margin:18px 0 6px;color:var(--blue)}
p{margin:8px 0}
code{background:#1f2630;padding:1px 6px;border-radius:5px;font:12.5px ui-monospace,Consolas,monospace;color:#c9d6e4}
table{border-collapse:collapse;width:100%;margin:10px 0;font-size:12.8px}
th,td{border:1px solid var(--chip);padding:6px 10px;text-align:left}
th{background:#1c2430;color:var(--muted);font-weight:600}
tr:nth-child(even) td{background:#12171f}
.card{background:var(--card);border:1px solid var(--chip);border-radius:10px;padding:14px 18px;margin:12px 0}
.hard{border-left:3px solid var(--red)}
.k{color:var(--yellow);font-weight:600}
.fail{color:var(--red);font-weight:600}
.tgt{color:var(--green);font-weight:600}
ul{margin:8px 0;padding-left:22px}
li{margin:3px 0}
img.chart{width:100%;border:1px solid var(--chip);border-radius:10px;margin:12px 0}
.lead{color:var(--muted);font-size:13.5px}
.chapnav{background:var(--card);border:1px solid var(--chip);border-radius:10px;padding:12px 18px;
  margin:12px 0 20px;columns:2;font-size:12.5px}
.chapnav a{display:block;padding:2px 0}
section.chap{border-top:2px solid var(--chip);margin-top:26px;padding-top:6px}
.chaphd{font-size:16px;font-weight:700;color:var(--yellow);margin:14px 0 4px}
hr{border:none;border-top:1px solid var(--chip);margin:16px 0}
.pill{display:inline-block;background:#1f2630;border:1px solid var(--chip);border-radius:6px;
  padding:1px 8px;margin:2px 3px 2px 0;font-size:12px}
"""

CHART_BLOCK = (
    f'<img class="chart" alt="ES daily measured move" '
    f'src="data:image/png;base64,{chart_b64}">' if chart_b64 else "")

BODY = f"""
<h2 id="what">What this is</h2>
<p class="lead">David Halsey's <b>Measured Move (MM)</b> method — the codified,
number-exact ruleset extracted from his book <i>Trading the Measured Move</i>
(Wiley, 2014, 226pp) and cross-checked against eminiaddict.com. Source notes:
one file per chapter in <code>eminiaddict/notes/</code>; this page is the
synthesis (<code>RULEBOOK.md</code>). <b>The whole method is mechanical except one
step</b> — picking the seed swing.</p>

<h2 id="geometry">1 · Measured-move geometry</h2>
<p>Draw a Fib on a swing leg. UP leg = swing low <code>L</code> → swing high
<code>H</code>; range <code>R = H − L</code>. Down leg mirrors.</p>
<table>
<tr><th>Level</th><th>Formula (up leg)</th><th>Role</th></tr>
<tr><td>100% (start)</td><td><code>L</code></td><td>swing low = origin</td></tr>
<tr><td class="fail">61.8%</td><td><code>L + 0.382·R</code></td><td>FAILURE — breach kills the MM</td></tr>
<tr><td class="k">50% (HWB)</td><td><code>L + 0.500·R</code></td><td>ENTRY (half-way-back)</td></tr>
<tr><td>38.2%</td><td><code>L + 0.618·R</code></td><td>Distance-Formula exit</td></tr>
<tr><td>0% (end)</td><td><code>H</code></td><td>swing high</td></tr>
<tr><td class="tgt">−23.6% = "123%"</td><td><code>H + 0.236·R</code></td><td>TARGET (seeds next swing)</td></tr>
</table>
<p class="lead">Halsey pronounces negative Fib levels as positives ("−23.6%" = "123%").</p>

<h2 id="swing">2 · What defines a swing</h2>
<div class="card hard">
<p><b>Seed swing = the only discretionary step</b> — the "significant high-low that
jumps off the page." After the seed it is mechanical & recursive: new peak = prior
MM's retrace high; new trough = prior MM's 123% target. A leg is confirmed real
when the <b>opposing MM's 61.8% breaks</b> (a "trend break").</p>
<p><b>To codify:</b> replace the seed with a ZigZag / ATR / fractal detector — its
threshold is the one parameter to tune & validate.</p>
</div>
<p>The chart below is drawn exactly by these rules on ES daily (seed = the dominant
leg 6,420.75 → 7,699.75). Entry (HWB) 7,060 · failure 6,909 · target 8,001.59.</p>
{CHART_BLOCK}

<h2 id="setups">3 · The three setups</h2>
<p>Trend order: <b>traditionals → extensions → straight up; a 61.8% failure flips it.</b></p>
<h3>3a · Traditional 50% MM</h3>
<ul>
<li><b>Anchor:</b> initial trailed swing (long low→high / short high→low)</li>
<li><b>Entry:</b> LIMIT at 50% (HWB), front-run per §4</li>
<li><b>Target:</b> 123% = <code>H + 0.236·R</code></li>
<li><b>Stop:</b> structural = 61.8% breach (numeric tick stops in §4)</li>
<li><b>Series:</b> entry → target → re-anchor at last low → next pullback, repeat</li>
</ul>
<h3>3b · Extension 50% MM (bull/bear flags)</h3>
<ul>
<li><b>Trigger:</b> new highs PAST a 123% target with NO pullback</li>
<li><b>Anchor:</b> previous highs; a series re-uses ONE fixed anchor</li>
<li><b>Entry / Target:</b> LIMIT at extension 50% (often = prior target) / 123%</li>
<li class="fail">HARD GATE: the FIRST extension off a new anchor is <b>observe-only</b> — it can fail</li>
</ul>
<h3>3c · 61.8% Failure (trend-change signal)</h3>
<ul>
<li><b>Mechanic:</b> fails 2nd test of 50%, pierces 61.8% → series broken → new trend</li>
<li><b>Trade:</b> the first pullback after the trend break (Entry #3); also a valid EXIT</li>
<li class="fail">HARD GATE: if it becomes a retest of the prior high/low (double top/bottom) → skip</li>
</ul>

<h2 id="entries">4 · Entry strategies — fixed order every MM</h2>
<p><b>First Test → Front-Run 2nd Test → Trend Break &amp; Next MM.</b> All LIMIT,
front-run in front of the 50%.</p>
<table>
<tr><th>Instr</th><th>Init stop</th><th>Front-run</th><th>1st target</th><th>Adj stop</th></tr>
<tr><td>/ES</td><td>−6</td><td>+2</td><td>+2</td><td>−4</td></tr>
<tr><td>/YM /TF /NQ /GC</td><td>−12</td><td>+4</td><td>+6</td><td>−6</td></tr>
<tr><td>/6A /6B /6C /6E /6J</td><td>−12</td><td>+4</td><td>+6</td><td>−6</td></tr>
<tr><td>/ZB</td><td>−8</td><td>+4</td><td>+4</td><td>−4</td></tr>
</table>
<ul>
<li><b>First Test</b> — highest prob/volume; ES limit +2t, stop −6→−4 after 1st target</li>
<li><b>Front-Run 2nd Test</b> — riskiest/best R:R; 4-tick total stop, all-in/out, smaller size</li>
<li><b>Trend Break &amp; Next MM</b> — opposing-MM break confirms trend + target; trade next MM at first-test specs</li>
</ul>
<p class="lead">Hard order rules: unfilled → pull the limit; never chase; stopped/BE → wait for next. "Fade the first test, go with the second."</p>

<h2 id="exits">5 · Taking profit (four methods)</h2>
<p><b>Rule:</b> take profit on the time frame you entered.</p>
<ul>
<li><b>Distance Formula</b> = <code>|50% − 38.2%| = 0.118·R</code> — fast scalp / first target (Fri PM, Mon AM, doldrums)</li>
<li><b>Trail the series</b> — trail 61.8% through traditional→extension; fail → take profit (trending Tue–Thu)</li>
<li><b>Confirmation of trend</b> — partial when an opposing MM breaks</li>
<li><b>−23% (123%) target</b> — the "exact reversal point"; intraday swings</li>
</ul>
<p class="lead">Execution ("90% factor"): trade ≥2 contracts, sell half at 1st target,
move stop to make it a <b>free trade</b>. Caps: ≤1% risk, ≥2:1 R:R.</p>

<h2 id="gaps">6 · Gap-fill book (ES)</h2>
<p><b>Fill</b> = price reaches prior day's 4pm cash close. <b>±10-pt gap-and-go</b> = prior close ± 10.</p>
<table>
<tr><th>Open vs fill</th><th>Fill rate (2010–12)</th><th>Action</th></tr>
<tr><td>&lt; 10 pts</td><td class="tgt">~77–79%</td><td>trade toward the fill</td></tr>
<tr><td>&gt; 10 pts (professional)</td><td class="fail">~9–26%</td><td>let it run away</td></tr>
</table>
<p><b>Workflow (all YES):</b> not opt-ex/rollover-Thu/1st-of-month · time 08:00–09:30 ET ·
inside the 10-pt band · a large S/R points toward the fill. Best entry 08:00–08:30 ET; ES gap 5–10 pts.</p>

<h2 id="sessions">7 · Sessions &amp; timing</h2>
<p>
<span class="pill">Sessions 08:00–11:30 &amp; 13:30–16:00 ET</span>
<span class="pill">No-trade 09:30–10:00</span>
<span class="pill">No new trades after 15:45</span>
<span class="pill">10:00 ET = volume push (day H/L)</span>
<span class="pill">Doldrums 11:30–13:30 = scalps only</span>
<span class="pill">Half size Mon/Fri/opt-ex/rollover</span>
<span class="pill">Trend days Tue–Thu</span>
<span class="pill">EUR/USD 03:00–11:30 ET</span>
<span class="pill">DP = (H+L+C)/3</span>
</p>

<h2 id="rules">8 · Ch 16 — the 31 rules</h2>
<h3>General (10)</h3>
<p class="lead">never add money · never trade without a stop · target for every trade ·
enter at MMs with the trend · use limit orders · ≤1% risk/trade · don't pick tops/bottoms
(wait for the MM failure at S/R) · don't rush undefined trades · focus on rules not money ·
half-size Mon/Fri/opt-ex/rollover.</p>
<h3>Gap (8)</h3>
<p class="lead">enter 08:00–08:30 · ES gap 5–10 pts else pass · pro-gap no-fill → trade first
signal WITH the gap · record unfilled gaps · stay in till fill or stop · avoid opt-ex Fri /
rollover Thu / 1st of month · narrow-range then gap &gt; prior range → stay away · ES leads.</p>
<h3>NYSE (9)</h3>
<p class="lead">trade only 15-min 50% setups (5–7/day) · strong breadth → longs only ·
weak breadth → shorts only · use NYSE tick to time · confirm 2nd test via time &amp; sales ·
Nasdaq-Bank confirm · two sessions only · no new trades after 15:45 · EOD review.</p>
<h3>Euro (4)</h3>
<p class="lead">income (EOD) vs wealth (week+) · trade the larger-TF trend · rank by R:R ·
trade 03:00–11:30 ET.</p>
<p><b>Setup priority:</b> Daily (≈1/wk, spot 24–36h ahead) &gt; 15-min (3–7/day) &gt; Micro. Journal everything.</p>

<h2 id="build">9 · What to build (for backtesting)</h2>
<ol>
<li>Seed-swing detector (ZigZag/ATR) — the one tunable knob</li>
<li>MM level engine (61.8/50/38.2/0/123%) + series chaining</li>
<li>Setup classifier (traditional / extension / 61.8%-failure)</li>
<li>Entry model (first-test / 2nd-test / trend-break) + ES tick table</li>
<li>Exit model (distance-formula / trail-61.8 / −23%)</li>
<li>Session &amp; calendar filter + standalone gap-fill module</li>
<li>Risk: 1% sizing, 2:1 floor, free-trade bracket</li>
</ol>
<p class="lead"><b>Discretionary (needs proxy/manual flag):</b> seed selection, "participation"/
time &amp; sales, breadth bias, "trust this MM?", double-top recognition, choosing among the 4 exits.</p>
"""

HTML = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{TITLE}</title><style>{CSS}</style></head><body>
<header><h1>EminiAddict — The Measured Move Method</h1>
<span class="tag">Halsey · Wiley 2014</span>
<span class="tag">synthesis of 16 chapters</span>
<span style="margin-left:auto"></span>
<a href="/artifacts">← Artifact Library</a></header>
<div class="wrap">
<div class="toc">
<a href="#what">What this is</a><a href="#geometry">1 · MM geometry</a>
<a href="#swing">2 · What defines a swing</a><a href="#setups">3 · Three setups</a>
<a href="#entries">4 · Entry strategies</a><a href="#exits">5 · Taking profit</a>
<a href="#gaps">6 · Gap-fill book</a><a href="#sessions">7 · Sessions &amp; timing</a>
<a href="#rules">8 · The 31 rules</a><a href="#build">9 · What to build</a>
<a href="#chapters">▸ Chapter-by-chapter notes</a>
</div>
{BODY}
<h2 id="chapters">Chapter-by-chapter notes (full extraction)</h2>
<p class="lead">The complete, number-exact read of all 16 chapters — the source
behind the synthesis above.</p>
<div class="chapnav">{CHAP_NAV}</div>
{CHAPTERS}
</div></body></html>"""

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(HTML, encoding="utf-8")
print(f"wrote {OUT}  ({round(len(HTML)/1024,1)} KB)")

# register title/info/date in the catalog (slug of title must == file stem)
cat = json.loads(CATALOG.read_text(encoding="utf-8"))
items = cat["artifacts"]
info = ("Codified, number-exact synthesis of David Halsey's Measured Move method "
        "(Trading the Measured Move, Wiley 2014) from a full 16-chapter extraction: "
        "MM Fib geometry (50% HWB entry / 61.8% failure / 123% target), the 3 setups "
        "(traditional / extension / 61.8%-failure), 3 entries + ES tick table, 4 exits "
        "(Distance Formula = 0.118R), the ES gap-fill book with fill stats, all 31 Ch-16 "
        "rules, session/timing rules, and a build spec for backtesting. The only "
        "discretionary step is the seed swing; everything downstream is mechanical.")
items[:] = [a for a in items if a.get("title") != TITLE]
items.insert(0, {"title": TITLE, "url": "", "updated": DATE,
                 "group": "EminiAddict", "info": info})
CATALOG.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"registered in catalog: '{TITLE}' (group EminiAddict, {DATE})")

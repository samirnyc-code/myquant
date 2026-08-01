"""Build the EminiAddict Academy — a ground-up learning hub in Mission Control that ties
together everything built for the Halsey Measured-Move method: the rulebook, his teaching
diagrams + the two flow charts, the sequence library, and the study quiz, in a structured
curriculum. Self-contained, links to the other artifacts (served on the same :8590).

Output: docs/artifacts/eminiaddict_academy.html  (/artifact/eminiaddict_academy)
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "artifacts" / "eminiaddict_academy.html"
CATALOG = ROOT / "data" / "_catalog" / "claude_artifacts.json"
TITLE = "EminiAddict Academy"          # slug -> eminiaddict_academy
DATE = "2026-08-02"

# curriculum: (module, blurb, [(label, href|None)])
A_METHOD = "/artifact/eminiaddict_measured_move_method"
A_DIAG = "/artifact/eminiaddict_diagrams"
A_SEQ = "/artifact/eminiaddict_mm_sequence_library"
A_QUIZ = "/artifact/eminiaddict_method_study_quiz"

MODULES = [
    ("1 · Foundations — what a Measured Move is",
     "Every setup is a Fib on a swing leg. Learn the geometry cold before anything else: "
     "50% = HWB (entry), 61.8% = failure (breach kills it), 123%/−23.6% = target (also seeds "
     "the next swing).",
     [("Method reference §1–2 (geometry, what defines a swing)", A_METHOD + "#geometry"),
      ("Diagrams: Types of Moves · Basic Moves · Levels", A_DIAG)]),
    ("2 · The three setups",
     "Traditional 50% MM → Extension (when a target is blown through with no 50% pullback) → "
     "61.8% Failure (the trend-change signal). Trend order: traditionals → extensions → straight "
     "up; a 61.8% failure flips it.",
     [("Method reference §3 (the three setups)", A_METHOD + "#setups"),
      ("Diagrams: Long Series · Short Series", A_DIAG)]),
    ("3 · Entries — fixed order, every MM",
     "First Test → Front-Run of the 2nd Test → Trend Break & Next MM. All limit orders "
     "front-run the 50%. Per-instrument ticks (ES: front-run +2, stop −6→−4, 1st target +2).",
     [("Method reference §4 (entries + ES tick table)", A_METHOD + "#entries")]),
    ("4 · Exits & position management",
     "Take profit on the timeframe you entered. Four methods: Distance Formula (|50%−38.2%| = "
     "0.118·R), trail the 61.8%, confirmation-of-trend partials, and the −23.6% target. Free "
     "trade + ≤1% risk + 2:1 floor.",
     [("Method reference §5 (four exits)", A_METHOD + "#exits")]),
    ("5 · The series & extensions — the decision tree ⭐",
     "How MMs chain into a trend: draw a basic MM → enter at HWB → tick-by-tick → profit "
     "target → beyond PT? → next MM… A trend break routes to STOP → draw the ATW-HWB of the "
     "whole series as the possible limit → reverse. THIS is the core process flowchart.",
     [("Diagram #5: Measured Move Flow Chart (the decision tree)", A_DIAG),
      ("Sequence Library — 71 real detected sequences (5M/15M/1D)", A_SEQ)]),
    ("6 · The daily process — Market Analysis Flow Chart",
     "Start on the Daily → find the last completed MM → is there a series/trend? → identify the "
     "Active MM & its phase → identify the larger opposing MM → drop to the 15-minute for the "
     "entry at the new 50% retracement.",
     [("Diagram #8: Market Analysis Flow Chart", A_DIAG)]),
    ("7 · Signal alignment — VX / Indices / TICK / BANK / USD",
     "Don't take the ES trade on the ES fib alone. Wait for alignment: VIX down-MM · Indices "
     "up-MM · new LOW tick · BANK strength · USD weakness (mirror for shorts). The internals "
     "are the gate, not optional confirmation.",
     [("Diagram: Signal Alignment Checklist", A_DIAG)]),
    ("8 · Gap fills, sessions & the rules",
     "ES gap 5–10pt; <10pt fills ~77–79%, >10pt (pro gap-and-go) ~9–26%. Sessions 08:00–11:30 "
     "& 13:30–16:00 ET; no-trade 09:30–10:00 & after 15:45; ≤1% risk; half-size Mon/Fri/opt-ex/"
     "rollover. The full Ch-16 rule list (31 rules).",
     [("Method reference §6–8 (gaps, sessions, the 31 rules)", A_METHOD + "#gaps"),
      ("Diagram: Gap Fill Statistics", A_DIAG)]),
    ("9 · Practice",
     "Drill it until the mechanics are automatic: flip-card definitions, a scored quiz (incl. "
     "numeric level computations), a live MM-level calculator, sequence-order drills, and a "
     "chart-reading drill.",
     [("Study & Quiz tool", A_QUIZ)]),
]

CHEAT = [
    ("50% (HWB)", "entry", "#e3b341"), ("61.8%", "failure — breach kills the MM", "#e2453c"),
    ("38.2%", "Distance-Formula exit", "#e08a2b"), ("123% / −23.6%", "profit target (seeds next swing)", "#3fb950"),
    ("Traditional", "50% pullback MM", "#58a6ff"), ("Extension", "target blown through w/ no 50% pullback", "#c77dff"),
    ("61.8% failure", "trend-change signal", "#f85149"), ("ATW-HWB", "50% of the whole series after a break", "#e3b341"),
]

cheat_html = "".join(
    f'<div class="cc"><span class="sw" style="background:{c}"></span><b>{k}</b> — {v}</div>'
    for k, v, c in CHEAT)
mods_html = ""
for title, blurb, links in MODULES:
    li = "".join(f'<li><a href="{href}">{lab}</a></li>' if href else f"<li>{lab}</li>"
                 for lab, href in links)
    mods_html += (f'<div class="mod"><h3>{title}</h3><p>{blurb}</p><ul>{li}</ul></div>')

HTML = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{TITLE}</title>
<style>
:root{{--bg:#0d1117;--card:#161b22;--chip:#30363d;--fg:#e6edf3;--mut:#8b949e;--blue:#58a6ff;--gold:#e3b341}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);
 font:14.5px/1.6 -apple-system,Segoe UI,Roboto,sans-serif}}
header{{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--chip);
 padding:14px 24px;display:flex;align-items:center;gap:12px;z-index:10}}
header h1{{font-size:18px;margin:0}}a{{color:var(--blue);text-decoration:none}}a:hover{{text-decoration:underline}}
.wrap{{max-width:920px;margin:0 auto;padding:20px 24px 80px}}
.lead{{color:var(--mut);font-size:14px;margin:6px 0 20px}}
.cheat{{background:var(--card);border:1px solid var(--chip);border-radius:12px;padding:14px 18px;margin:0 0 24px;
 display:grid;grid-template-columns:1fr 1fr;gap:6px 20px}}
.cc{{font-size:13px;color:var(--mut)}}.cc b{{color:var(--fg)}}
.sw{{width:11px;height:11px;border-radius:3px;display:inline-block;margin-right:7px;vertical-align:middle}}
.mod{{background:var(--card);border:1px solid var(--chip);border-radius:12px;padding:16px 20px;margin:12px 0;
 border-left:3px solid var(--blue)}}
.mod h3{{margin:0 0 6px;font-size:15.5px}}.mod p{{margin:0 0 10px;color:var(--mut);font-size:13.5px}}
.mod ul{{margin:0;padding-left:20px}}.mod li{{margin:4px 0;font-size:13.5px}}
h2{{font-size:13px;color:var(--mut);text-transform:uppercase;letter-spacing:.05em;margin:26px 0 10px}}
</style></head><body>
<header><h1>EminiAddict Academy</h1>
 <span style="color:var(--mut);font-size:13px">David Halsey · Measured-Move method</span>
 <span style="margin-left:auto"></span>
 <a href="/artifacts">← Artifact Library</a></header>
<div class="wrap">
 <p class="lead">A ground-up path through Halsey's Measured-Move method — built from the full
  book extraction, his own teaching diagrams &amp; flow charts, 71 real detected sequences, and a
  practice quiz. Work top to bottom. Each module links to the deep material.</p>
 <h2>Cheat-sheet</h2>
 <div class="cheat">{cheat_html}</div>
 <h2>Curriculum</h2>
 {mods_html}
 <h2>Everything in one place</h2>
 <div class="mod">
  <ul>
   <li><a href="{A_METHOD}">Method Reference</a> — the full synthesis + all 16 chapter notes</li>
   <li><a href="{A_DIAG}">Diagram Library</a> — his 16 teaching diagrams + both flow charts</li>
   <li><a href="{A_SEQ}">Sequence Library</a> — 71 auto-detected MM sequences (5M/15M/1D)</li>
   <li><a href="{A_QUIZ}">Study &amp; Quiz</a> — flashcards, quiz, MM calculator, drills</li>
  </ul>
 </div>
</div></body></html>"""

OUT.write_text(HTML, encoding="utf-8")
print(f"wrote {OUT} ({round(len(HTML)/1024,1)} KB)")

cat = json.loads(CATALOG.read_text(encoding="utf-8"))
its = cat["artifacts"]
info = ("Ground-up learning hub for David Halsey's Measured-Move method — a 9-module "
        "curriculum (foundations -> setups -> entries -> exits -> the decision-tree flow chart "
        "-> daily process -> signal alignment -> gaps/rules -> practice) that ties together the "
        "method reference, his teaching diagrams + both flow charts, the 71-sequence library, and "
        "the study quiz, with a cheat-sheet.")
its[:] = [a for a in its if a.get("title") != TITLE]
its.insert(0, {"title": TITLE, "url": "", "updated": DATE, "group": "EminiAddict", "info": info})
CATALOG.write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"registered '{TITLE}'")

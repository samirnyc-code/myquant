"""methodology_coverage.py — VERIFY where each component of Halsey's method is
actually taught, and surface concepts that are covered thinly or only in the
live/daily room (not the book or webinars).

Method: a curated lexicon of the method's components (term + regex aliases),
counted across 4 corpora — BOOK, WEBINARS (11 method webinars + 8 GS lessons),
ROOM (daily-analysis video transcripts = our proxy for the trade room), and the
DIAGRAMS' filenames. Counts are normalized per 10,000 words so corpora of very
different sizes compare fairly. A per-component classifier flags:
  - WELL COVERED  : present in the book AND (webinars or room)
  - BOOK-ONLY     : in the book, thin/absent in webinars+room
  - POST-BOOK     : ~absent from the book, present in webinars/room (his later teaching)
  - ROOM-LEANING  : room rate >> book+webinar rate (candidate trade-room concept)
  - THIN EVERYWHERE: low everywhere (poorly covered / named-but-undefined)

CAVEAT printed in the report: the ROOM corpus is small (5 daily transcripts).
Transcribe more daily videos (ea_transcribe.py --daily MMDDYY; S3 keys verified
live) to harden the room signal before drawing strong conclusions.

Outputs (dated): data/analysis/method_coverage_<UTCstamp>.csv + a printed report.
Run:  python methodology_coverage.py
"""
import csv
import glob
import os
import re
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
EA = os.path.join(ROOT, "eminiaddict")
OUTDIR = os.path.join(EA, "data", "analysis")

# ---- corpora -------------------------------------------------------------
def read(paths):
    txt = []
    for p in paths:
        try:
            txt.append(open(p, encoding="utf-8", errors="ignore").read())
        except FileNotFoundError:
            pass
    return "\n".join(txt)

CORPORA = {
    "BOOK": read([os.path.join(EA, "data", "book_text.txt")]),
    "WEBINARS": read(
        glob.glob(os.path.join(EA, "data", "site", "webinars", "transcripts", "*.txt"))
        + glob.glob(os.path.join(EA, "data", "site", "getting_started", "transcripts", "*.txt"))
    ),
    "ROOM": read(glob.glob(os.path.join(EA, "data", "daily", "*", "transcript.txt"))),
    "DIAGRAMS": " ".join(
        os.path.basename(p) for p in glob.glob(os.path.join(EA, "data", "site", "_diagrams", "*.png"))
    ).replace("_", " ").replace("-", " "),
}
WORDS = {k: max(1, len(v.split())) for k, v in CORPORA.items()}

# ---- the component lexicon ----------------------------------------------
# (component, category, [regex aliases]). Regexes are matched case-insensitively.
LEX = [
 # --- CORE GEOMETRY ---
 ("Measured move", "geometry", [r"measured move", r"\bMM\b"]),
 ("Halfway back (HWB / 50%)", "geometry", [r"halfway back", r"\bHWB\b", r"50\s?%", r"50 percent"]),
 ("61.8% failure level", "geometry", [r"61\.?8", r"failure level"]),
 ("-23.6% / 123.6% target", "geometry", [r"23\.?6", r"123\.?6", r"profit target"]),
 ("Distance formula / 38.2%", "geometry", [r"distance formula", r"38\.?2"]),
 ("Seed / anchor / starting point", "geometry", [r"\banchor", r"starting point", r"seed", r"significant.{0,12}high.?low"]),
 ("Zones vs lines", "geometry", [r"\bzone", r"not.{0,6}exact", r"close but not"]),
 ("Fibonacci", "geometry", [r"fibonacc", r"\bfib\b", r"golden ratio"]),
 # --- SETUPS ---
 ("Traditional setup", "setups", [r"traditional"]),
 ("Extension setup", "setups", [r"\bextension"]),
 ("Expanded / extension-of-extension", "setups", [r"expanded extension", r"extension of (an )?extension", r"straight up", r"straight down"]),
 ("Trend break / 61.8 failure", "setups", [r"trend break", r"break.{0,10}trend", r"trend fail", r"trend change"]),
 ("Series progression", "setups", [r"series of measured", r"series of mm", r"traditionals?, to extensions"]),
 ("All-the-way-halfway-back", "setups", [r"all the way halfway", r"\bATWHWB\b", r"halfway back short", r"halfway back long"]),
 ("Nested / fractal timeframes", "setups", [r"nested", r"fractal", r"babushka", r"micros fail"]),
 # --- ENTRIES ---
 ("First test", "entries", [r"first test"]),
 ("Second test / gotcha", "entries", [r"second test", r"gotcha", r"failed breakout", r"shake ?out"]),
 ("Front-run", "entries", [r"front ?run"]),
 ("Limit order entry", "entries", [r"limit order"]),
 ("Reduced-risk / free trade", "entries", [r"free trade", r"reduced risk"]),
 # --- EXITS / RISK ---
 ("Trailing the series", "exits", [r"trail.{0,15}(series|61)"]),
 ("Confirmation of trend", "exits", [r"confirmation of.{0,6}trend", r"confirm.{0,10}target", r"opposing measured move"]),
 ("Four phases", "exits", [r"four phases", r"phase [1-4]", r"phase one|phase two|phase three|phase four"]),
 ("1% risk / position sizing", "exits", [r"1 ?percent", r"1\s?%", r"position siz", r"over ?lever"]),
 ("Half-size days", "exits", [r"half size", r"half position", r"mondays and fridays", r"options expiration"]),
 # --- TIMEFRAMES ---
 ("Weekly trend", "timeframes", [r"weekly"]),
 ("Daily trend", "timeframes", [r"daily (trend|chart|setup|measured)"]),
 ("15-minute trend", "timeframes", [r"15.?minute", r"fifteen minute"]),
 ("Micro trend", "timeframes", [r"\bmicro"]),
 ("Top-down / path of least resistance", "timeframes", [r"top ?down", r"path of least resistance", r"with the (trend|flow)"]),
 # --- INTERNALS / TIMING ---
 ("NYSE TICK", "internals", [r"\btick\b"]),
 ("Tick hook", "internals", [r"tick hook"]),
 ("Tick divergence / extremes", "internals", [r"tick diverg", r"tick extreme", r"divergence"]),
 ("Bank (Nasdaq banking index)", "internals", [r"\bbank\b"]),
 ("Breadth", "internals", [r"breadth"]),
 ("Time & sales / tape", "internals", [r"time (and|&) sales", r"time ?and ?sales", r"tape"]),
 ("VIX", "internals", [r"\bVIX\b", r"volatility index"]),
 ("USD / Dollar correlation", "internals", [r"\bUSD\b", r"\bDXY\b", r"dollar", r"correlat"]),
 ("Signal-alignment checklist", "internals", [r"checklist", r"alignment", r"signals? align"]),
 ("Daily pivot", "internals", [r"daily pivot", r"\bpivot\b"]),
 ("Sessions / no-trade zones", "internals", [r"no.?trade zone", r"9:?30", r"session", r"3:?45", r"doldrums"]),
 # --- PLAYBOOKS ---
 ("Gap fills", "playbooks", [r"gap ?fill", r"professional gap", r"gap and go", r"gap ?up|gap ?down"]),
 ("Instrument idiosyncrasies", "playbooks", [r"crude|\bCL\b|\bgold\b|\bGC\b", r"euro|6E|EUR/?USD", r"monster"]),
 ("Seasonality", "playbooks", [r"seasonal", r"sell in may", r"july 4"]),
 ("History / replay (Groundhog)", "playbooks", [r"groundhog", r"replay", r"predict the future", r"history repeat"]),
 ("Dead cat / crash anatomy", "playbooks", [r"dead cat", r"crash", r"bear market", r"bull market"]),
 # --- PSYCHOLOGY / PLAN ---
 ("Casino vs gambler", "psychology", [r"casino", r"gambler"]),
 ("Emotional capital", "psychology", [r"emotional capital", r"emotion"]),
 ("Proactive vs reactive", "psychology", [r"proactive", r"reactive"]),
 ("90/10 rule", "psychology", [r"90 ?%|90 percent|ninety percent", r"10 ?%|10 percent"]),
 ("Trading journal", "psychology", [r"journal"]),
 ("Four legs / trading plan", "psychology", [r"four legs", r"trading plan", r"money management"]),
 ("Deliberate practice / 10k hours", "psychology", [r"10,?000 hours", r"ten thousand hours", r"perfect practice"]),
 # --- KNOWN-UNDEFINED (discretionary, flagged in chapter notes) ---
 ("Seed selection RULE (how to pick)", "discretionary", [r"how.{0,20}(pick|choose|select|draw).{0,20}(swing|anchor|fib)", r"which swing"]),
 ("'Blows past target' threshold", "discretionary", [r"blow.{0,6}(past|through).{0,10}target", r"blows past"]),
 ("Failure significance by context", "discretionary", [r"significan", r"how significant"]),
 ("Which touch counts", "discretionary", [r"first.{0,4}touch", r"second.{0,4}touch", r"third.{0,4}touch"]),
]

STAMP = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(os.path.getmtime(__file__)) if False else time.gmtime())


def rate(count, corpus):
    return round(count / WORDS[corpus] * 10000, 2)


def classify(rb, rw, rr):
    """rb/rw/rr = per-10k rates in book / webinars / room."""
    book_present = rb >= 1.0
    web_present = rw >= 1.0
    room_present = rr >= 1.0
    lessons = max(rw, rr)
    if not (book_present or web_present or room_present):
        return "ABSENT (lexicon miss?)"
    if rb < 0.5 and (web_present or room_present):
        return "POST-BOOK (not in book)"
    if room_present and rr > 2.5 * max(rb, rw, 0.1):
        return "ROOM-LEANING"
    if book_present and lessons < 0.5:
        return "BOOK-ONLY"
    if max(rb, rw, rr) < 1.5:
        return "THIN EVERYWHERE"
    if book_present and (web_present or room_present):
        return "WELL COVERED"
    return "PARTIAL"


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    rows = []
    for comp, cat, aliases in LEX:
        pat = re.compile("|".join(aliases), re.I)
        counts = {c: len(pat.findall(CORPORA[c])) for c in CORPORA}
        rb, rw, rr = rate(counts["BOOK"], "BOOK"), rate(counts["WEBINARS"], "WEBINARS"), rate(counts["ROOM"], "ROOM")
        cls = classify(rb, rw, rr)
        rows.append((cat, comp, counts["BOOK"], rb, counts["WEBINARS"], rw,
                     counts["ROOM"], rr, counts["DIAGRAMS"], cls))

    out = os.path.join(OUTDIR, f"method_coverage_{STAMP}.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["category", "component", "book_n", "book_/10k", "web_n", "web_/10k",
                    "room_n", "room_/10k", "diagram_n", "classification"])
        w.writerows(rows)

    # ---- printed report ----
    print(f"CORPUS WORDS: BOOK={WORDS['BOOK']:,}  WEBINARS={WORDS['WEBINARS']:,}  "
          f"ROOM={WORDS['ROOM']:,} (5 daily videos — SMALL)")
    print(f"wrote {os.path.relpath(out, ROOT)}\n")
    order = {"WELL COVERED": 0, "PARTIAL": 1, "BOOK-ONLY": 2, "POST-BOOK": 3,
             "ROOM-LEANING": 4, "THIN EVERYWHERE": 5, "ABSENT (lexicon miss?)": 6}
    print(f"{'COMPONENT':40s} {'BOOK':>6} {'WEB':>6} {'ROOM':>6}  CLASS")
    print("-" * 78)
    for r in sorted(rows, key=lambda x: (order.get(x[9], 9), x[0])):
        print(f"{r[1]:40s} {r[3]:6.1f} {r[5]:6.1f} {r[7]:6.1f}  {r[9]}")
    # summary by class
    print("\nBY CLASS:")
    from collections import Counter
    for cls, n in Counter(r[9] for r in rows).most_common():
        print(f"  {n:2d}  {cls}")
    # the gap lists the user cares about
    print("\n>>> POST-BOOK (his later teaching, not in the 2014 book):")
    for r in rows:
        if r[9] == "POST-BOOK":
            print(f"     - {r[1]}")
    print(">>> ROOM-LEANING (heavier in daily room than book/webinars — trade-room candidates):")
    for r in rows:
        if r[9] == "ROOM-LEANING":
            print(f"     - {r[1]}")
    print(">>> THIN EVERYWHERE (poorly covered / possibly named-but-undefined):")
    for r in rows:
        if r[9] == "THIN EVERYWHERE":
            print(f"     - {r[1]}")


if __name__ == "__main__":
    main()

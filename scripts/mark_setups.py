"""Setup-marking tool — forward-reveal chart annotator (S75J/K).

The user marks great trade setups (BOPB, second-entry fades) on ES volume-bar
charts; marks feed feature discovery vs matched controls. Design locked S75K:

  * FORWARD-ONLY REVEAL — bars draw left-to-right (play / step keys); a mark can
    only be placed on an already-revealed bar. Enforced client AND server side
    (`reveal_idx` is stored with every mark so the no-lookahead property is
    auditable). Rewinding the *view* is allowed; un-revealing is not.
  * PRICE + MQ LEVELS ONLY — deliberately no delta/CVD on screen, so marks stay
    independent of the footprint features the analysis will test (anchoring).
  * LABELS — setup type (BOPB / 2nd-entry fade / other) + direction + optional
    A/B grade. 3 keystrokes per mark.
  * Day order: chronological, dates shown (user's call; noted as a limitation).

Marks append to data/annotations/marks.csv:
  marked_at,day,bar_idx,bar_time,price,setup,direction,grade,reveal_idx,note

Inputs: data/footprint/ES_bars.csv, data/menthorq/ES1!_mq_levels_history.csv
Run:    .venv/Scripts/python.exe scripts/mark_setups.py [--port 8630] [--open]
        (8590-8620 are taken by Mission Control dashboards — see launcher.py)
"""
import argparse
import csv
import json
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BARS_CSV = ROOT / "data" / "footprint" / "ES_bars.csv"
LEVELS_CSV = ROOT / "data" / "menthorq" / "ES1!_mq_levels_history.csv"
FOOTPRINT_CSV = ROOT / "data" / "footprint" / "ES_footprint.csv"
MARKS_CSV = ROOT / "data" / "annotations" / "marks.csv"
DRAWINGS_JSON = ROOT / "data" / "annotations" / "drawings.json"
MARK_FIELDS = ["marked_at", "day", "bar_idx", "bar_time", "price",
               "setup", "direction", "grade", "reveal_idx", "note", "wedge_id"]

LEVEL_STEMS = ["cr", "ps", "hvl", "cr0", "ps0", "hvl0", "gw0",
               "d1_min", "d1_max"] + [f"gex_{i}" for i in range(1, 11)]

# Setup vocabulary (Brooks). key -> (hotkey, label, chart badge, implied direction)
# Implied direction is pre-filled to cut the keystrokes; L/S still overrides it.
SETUPS = {
    "h1":     ("1", "H1", "H1", "long"),
    "h2":     ("2", "H2", "H2", "long"),
    "l1":     ("3", "L1", "L1", "short"),
    "l2":     ("4", "L2", "L2", "short"),
    "w1p":    ("5", "W1P", "W1P", None),
    "w1":     ("q", "Wedge push 1", "W1", None),
    "w2":     ("w", "Wedge push 2", "W2", None),
    "w3":     ("e", "Wedge push 3", "W3", None),
    "boft":   ("6", "BOFT", "BOFT", None),
    "dbbull": ("7", "DB Bull", "DB", "long"),
    "dtbear": ("8", "DT Bear", "DT", "short"),
    "tfto":   ("9", "TFTO", "TFTO", None),
    "bopb":   ("0", "BOPB", "BO", None),
    "fade2":  ("f", "2nd-entry fade", "F2", None),
    "other":  ("o", "other", "O", None),
}


TF_MIN = 5          # chart timeframe, minutes
ATR_LEN = 14        # ATR period, on the chart timeframe


def _bucket(hhmm):
    """'08:31' -> '08:35' — the TF_MIN bar that this 1M bar belongs to.

    The export is END-STAMPED: the row labelled 08:31 covers 08:30-08:31. So the
    5M bar covering 08:30-08:35 is made of the rows 08:31..08:35 and is itself
    labelled 08:35. Flooring instead of ceiling (the first version of this) put
    08:31-08:34 into an "08:30" bucket and started a new one at 08:35 — every bar
    misaligned by one minute, and the first bucket only four minutes long.
    Verified against the known-good 5M export: 08:31..08:35 aggregates to
    O 7485.00 H 7491.25 L 7475.00 C 7475.25, which matches exactly.
    """
    h, m = int(hhmm[:2]), int(hhmm[3:5])
    tot = h * 60 + m
    end = -(-tot // TF_MIN) * TF_MIN          # ceil to the grid
    return f"{(end // 60) % 24:02d}:{end % 60:02d}"


def load_days():
    """{day: {bars: [[idx,time,o,h,l,c],...], levels: [[price,'cr0+gw0'],...]}}

    The source export (data/footprint/ES_bars.csv) is 1-MINUTE and its timeframe
    has changed under us before, so bars are aggregated to TF_MIN here rather than
    trusted as-is. `idx` is the bar's ordinal within the session (0-based), which
    is stable regardless of what the exporter emits.
    """
    raw = {}
    with open(BARS_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d, hhmm = r["BarTime"][:10], r["BarTime"][11:16]
            key = _bucket(hhmm)
            o, h, l, c = (float(r["Open"]), float(r["High"]),
                          float(r["Low"]), float(r["Close"]))
            slot = raw.setdefault(d, {}).get(key)
            if slot is None:
                raw[d][key] = [o, h, l, c]
            else:                                  # extend the 5M bar
                slot[1] = max(slot[1], h)
                slot[2] = min(slot[2], l)
                slot[3] = c
    days = {}
    for d, buckets in raw.items():
        bars = []
        for i, key in enumerate(sorted(buckets)):
            o, h, l, c = buckets[key]
            bars.append([i, key, o, h, l, c])
        days[d] = {"bars": bars, "levels": []}
    with open(LEVELS_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d = r["session_date"]
            if d not in days:
                continue
            by_price = {}
            for stem in LEVEL_STEMS:
                v = r.get(stem)
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    continue
                by_price.setdefault(v, []).append(stem)
            lo = min(b[4] for b in days[d]["bars"]) - 15
            hi = max(b[3] for b in days[d]["bars"]) + 15
            days[d]["levels"] = sorted(
                [[p, "+".join(s)] for p, s in by_price.items() if lo <= p <= hi])
    for d in days.values():
        d["bars"].sort()

    # ---- ATR(ATR_LEN) on the chart timeframe --------------------------------
    # Computed across the CONTINUOUS series (previous session's bars roll into the
    # next), so the first bars of a session get a real ATR instead of a degenerate
    # one. atr[i] uses bars up to and including i only — nothing ahead of it — which
    # matters because this tool is a forward-reveal annotator and a lookahead ATR
    # would quietly leak the future into the zone you are marking against.
    prev_close, trs = None, []
    for d in sorted(days):
        atr = []
        for _i, _t, o, h, l, c in days[d]["bars"]:
            tr = h - l if prev_close is None else max(
                h - l, abs(h - prev_close), abs(l - prev_close))
            trs.append(tr)
            win = trs[-ATR_LEN:]
            atr.append(round(sum(win) / len(win), 3))
            prev_close = c
        days[d]["atr"] = atr

    # ---- per-session volume profile -> POC / VAH / VAL ----------------------
    # Real value area from the footprint export (volume at price), not an estimate:
    # start at POC and expand to whichever neighbouring price has more volume until
    # 70% of the session's volume is enclosed.
    prof = {}
    if FOOTPRINT_CSV.exists():
        with open(FOOTPRINT_CSV, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                d = r["BarTime"][:10]
                try:
                    p = float(r["Price"])
                    v = float(r["BidVol"]) + float(r["AskVol"])
                except (TypeError, ValueError):
                    continue
                prof.setdefault(d, {})
                prof[d][p] = prof[d].get(p, 0.0) + v
    va = {}
    for d, pv in prof.items():
        if not pv:
            continue
        prices = sorted(pv)
        total = sum(pv.values())
        poc_i = max(range(len(prices)), key=lambda k: pv[prices[k]])
        lo_i = hi_i = poc_i
        acc = pv[prices[poc_i]]
        while acc < 0.70 * total and (lo_i > 0 or hi_i < len(prices) - 1):
            up = pv[prices[hi_i + 1]] if hi_i < len(prices) - 1 else -1
            dn = pv[prices[lo_i - 1]] if lo_i > 0 else -1
            if up >= dn:
                hi_i += 1
                acc += up
            else:
                lo_i -= 1
                acc += dn
        va[d] = {"poc": prices[poc_i], "vah": prices[hi_i], "val": prices[lo_i]}

    # ---- prior session's LAST bar + gap stats --------------------------------
    # The overnight gap is context you have before the first bar prints, so it is
    # legitimate to show at reveal 0 — unlike anything from the current session.
    keys = sorted(days)
    for k, d in enumerate(keys):
        if k == 0:
            days[d]["prev"] = None
            days[d]["gap"] = None
            continue
        pd_ = keys[k - 1]
        pbars = days[pd_]["bars"]
        last = pbars[-1]
        prev_close = last[5]
        first_open = days[d]["bars"][0][2]
        gap = first_open - prev_close
        # measure the gap against the PRIOR session's ATR — the only one that was
        # knowable before this session opened
        patr = days[pd_]["atr"][-1] if days[pd_].get("atr") else 0
        prng_hi = max(b[3] for b in pbars)
        prng_lo = min(b[4] for b in pbars)
        days[d]["prev"] = {"day": pd_, "time": last[1], "o": last[2], "h": last[3],
                           "l": last[4], "c": last[5],
                           "hi": prng_hi, "lo": prng_lo,
                           **({"poc": va[pd_]["poc"], "vah": va[pd_]["vah"],
                               "val": va[pd_]["val"]} if pd_ in va else {})}
        days[d]["gap"] = {
            "pts": round(gap, 2),
            "pct": round(gap / prev_close * 100, 3),
            "atr_mult": round(gap / patr, 2) if patr else None,
            "prev_atr": patr,
            "dir": "up" if gap > 0 else ("down" if gap < 0 else "flat"),
            # where the open sits relative to the prior session's range
            "vs_prev_range": ("above prior high" if first_open > prng_hi else
                              "below prior low" if first_open < prng_lo else
                              "inside prior range"),
        }
    return dict(sorted(days.items()))  # chronological (user's choice)


def read_drawings():
    """{day: [ {id,type,x1,y1,x2,y2}, ... ]} — visual aids, persisted per session.

    Stored in DATA coordinates (bar index + price), never pixels, so they stay put
    through zoom, resize and bar-width changes.
    """
    if not DRAWINGS_JSON.exists():
        return {}
    try:
        return json.loads(DRAWINGS_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def write_drawings(d):
    DRAWINGS_JSON.parent.mkdir(parents=True, exist_ok=True)
    DRAWINGS_JSON.write_text(json.dumps(d, indent=1), encoding="utf-8")


def read_marks():
    if not MARKS_CSV.exists():
        return []
    with open(MARKS_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def append_mark(row):
    MARKS_CSV.parent.mkdir(parents=True, exist_ok=True)
    new = not MARKS_CSV.exists()
    # If the file predates a column (wedge_id was added later), rewrite it with the
    # current header first. Appending regardless writes values past the header, and
    # csv.DictReader then silently drops them on read — which is exactly how the
    # first wedge_ids went missing despite being written to disk.
    if not new:
        with open(MARKS_CSV, encoding="utf-8") as f:
            rows = list(csv.reader(f))
        if rows and rows[0] != MARK_FIELDS:
            hdr, body = rows[0], rows[1:]
            with open(MARKS_CSV, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=MARK_FIELDS)
                w.writeheader()
                for r in body:
                    d = dict(zip(hdr, r))
                    if len(r) > len(hdr):
                        d[MARK_FIELDS[-1]] = r[-1]
                    w.writerow({k: d.get(k, "") for k in MARK_FIELDS})
    with open(MARKS_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MARK_FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


def delete_mark(day, bar_idx, setup):
    """Remove the LAST mark matching (day, bar_idx, setup); rewrite the file."""
    rows = read_marks()
    for i in range(len(rows) - 1, -1, -1):
        r = rows[i]
        if r["day"] == day and r["bar_idx"] == str(bar_idx) and r["setup"] == setup:
            del rows[i]
            break
    else:
        return False
    with open(MARKS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MARK_FIELDS)
        w.writeheader()
        w.writerows(rows)
    return True


class Handler(BaseHTTPRequestHandler):
    days = {}  # set in main()

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, separators=(",", ":")).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = HTML_TMPL.replace(
                "__DAYS__", json.dumps(list(self.days), separators=(",", ":"))).replace(
                "__SETUPS__", json.dumps(SETUPS, separators=(",", ":"))).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/api/day?d="):
            d = self.path.split("=", 1)[1]
            if d not in self.days:
                return self._json({"err": "unknown day"}, 404)
            # Existing marks were recorded against 1-minute bar indices. Re-resolve
            # every mark by its TIMESTAMP into the current timeframe's bar, so the
            # 7 marks already on disk survive the switch to 5M instead of pointing
            # at nonexistent bars.
            by_time = {b[1]: b[0] for b in self.days[d]["bars"]}
            marks = []
            for m in read_marks():
                if m["day"] != d:
                    continue
                hhmm = (m.get("bar_time") or "")[11:16]
                bi = by_time.get(_bucket(hhmm)) if hhmm else None
                marks.append({**m, "bar_idx": bi if bi is not None else -1})
            return self._json({**self.days[d], "marks": marks,
                               "drawings": read_drawings().get(d, [])})
        self._json({"err": "not found"}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._json({"err": "bad json"}, 400)
        if self.path == "/api/mark":
            day, bi = req.get("day"), req.get("bar_idx")
            bars = {b[0]: b for b in self.days.get(day, {}).get("bars", [])}
            if bi not in bars:
                return self._json({"err": "unknown bar"}, 400)
            # no-lookahead guardrail: the marked bar must already be revealed
            if not isinstance(req.get("reveal_idx"), int) or bi > req["reveal_idx"]:
                return self._json({"err": "mark beyond reveal edge rejected"}, 400)
            if req.get("setup") not in SETUPS \
                    or req.get("direction") not in ("long", "short"):
                return self._json({"err": "bad setup/direction"}, 400)
            # Wedge pushes chain into one object: W1 opens a new wedge, W2/W3
            # attach to the most recent wedge on that day still missing that push.
            wedge_id = ""
            setup = req["setup"]
            if setup in ("w1", "w2", "w3"):
                day_marks = [m for m in read_marks() if m["day"] == day
                             and m.get("wedge_id")]
                if setup == "w1":
                    n = len({m["wedge_id"] for m in day_marks})
                    wedge_id = f"{day}-W{n + 1}"
                else:
                    open_ids = []
                    for m in day_marks:
                        wid = m["wedge_id"]
                        if wid not in open_ids:
                            open_ids.append(wid)
                    have = {wid: {m["setup"] for m in day_marks
                                  if m["wedge_id"] == wid} for wid in open_ids}
                    cand = [wid for wid in open_ids if setup not in have[wid]]
                    wedge_id = cand[-1] if cand else f"{day}-W{len(open_ids) + 1}"
            append_mark({
                "marked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "day": day, "bar_idx": bi, "bar_time": f"{day} {bars[bi][1]}",
                "price": (bars[bi][3] if req["direction"] == "long" else bars[bi][4])
                         if setup in ("w1", "w2", "w3") else bars[bi][5],
                "setup": setup,
                "direction": req["direction"], "grade": req.get("grade", ""),
                "reveal_idx": req["reveal_idx"], "note": req.get("note", ""),
                "wedge_id": wedge_id})
            return self._json({"ok": True})
        if self.path == "/api/draw":
            d = req.get("day")
            if d not in self.days:
                return self._json({"err": "unknown day"}, 400)
            g = req.get("drawing") or {}
            if g.get("type") not in ("line", "box", "fib"):
                return self._json({"err": "bad type"}, 400)
            try:
                g = {"id": str(g.get("id") or datetime.now(timezone.utc).timestamp()),
                     "type": g["type"],
                     "x1": float(g["x1"]), "y1": float(g["y1"]),
                     "x2": float(g["x2"]), "y2": float(g["y2"])}
            except (KeyError, TypeError, ValueError):
                return self._json({"err": "bad coords"}, 400)
            all_ = read_drawings()
            all_.setdefault(d, []).append(g)
            write_drawings(all_)
            return self._json({"ok": True, "drawing": g})
        if self.path == "/api/undraw":
            d, gid = req.get("day"), str(req.get("id"))
            all_ = read_drawings()
            before = len(all_.get(d, []))
            all_[d] = [g for g in all_.get(d, []) if g["id"] != gid]
            write_drawings(all_)
            return self._json({"ok": len(all_[d]) < before})
        if self.path == "/api/unmark":
            ok = delete_mark(req.get("day"), req.get("bar_idx"), req.get("setup"))
            return self._json({"ok": ok})
        self._json({"err": "not found"}, 404)


# ---------------------------------------------------------------- HTML template
HTML_TMPL = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mark Setups — forward reveal</title>
<style>
:root{
  --surface:#fcfcfb; --plane:#f9f9f7; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,.10); --card:#ffffff;
  --up:#1f8a4c; --dn:#cf3f3f; --sel:#2a78d6; --long:#1f8a4c; --short:#cf3f3f;
  --draw:#3f7fbf; --wedge:#c060c0; --va:#2f7fa8; --yday:#b8860b; --cr:#cf3f3f; --ps:#1f8a4c; --hvl:#7a3aa7; --gw:#d67f2a; --gex:#9a988f; --band:#2a78d6;
}
@media (prefers-color-scheme:dark){:root{
  --surface:#1a1a19; --plane:#0d0d0d; --ink:#fff; --ink2:#c3c2b7; --muted:#898781;
  --grid:#262624; --axis:#383835; --border:rgba(255,255,255,.12); --card:#1f1f1e;
  --up:#37b06a; --dn:#e66767; --sel:#3987e5;
  --draw:#6ea8e0; --wedge:#d98fd9; --va:#5aa9d0; --yday:#d8a93a; --cr:#e66767; --ps:#37b06a; --hvl:#9c6fd0; --gw:#e6a45c; --gex:#6f6e66; --band:#3987e5;
}}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:14px}
header{padding:10px 16px;border-bottom:1px solid var(--border);display:flex;
  align-items:center;gap:14px;flex-wrap:wrap;background:var(--surface)}
h1{font-size:15px;margin:0;font-weight:650}
select,button,input{font:inherit;color:var(--ink);background:var(--card);
  border:1px solid var(--border);border-radius:8px;padding:5px 10px;cursor:pointer}
button.on{background:var(--sel);color:#fff;border-color:var(--sel)}
.pill{font-size:12px;color:var(--ink2)}
#stage{position:relative;margin:8px 8px}
canvas{display:block;width:100%;background:var(--surface);
  border:1px solid var(--border);border-radius:12px;cursor:crosshair}
#picker{position:absolute;display:none;z-index:20;background:var(--card);
  border:1px solid var(--sel);border-radius:12px;padding:10px 12px;
  box-shadow:0 8px 26px rgba(0,0,0,.35);min-width:290px}
#picker .hd{font-size:12px;color:var(--muted);margin-bottom:7px}
#picker .grid{display:grid;grid-template-columns:repeat(4,1fr);gap:5px}
#picker button{padding:6px 4px;font-size:12px;border-radius:7px}
#picker .row{display:flex;gap:6px;margin-top:8px}
#picker .row button{flex:1}
#prompt{position:absolute;top:12px;left:14px;background:var(--card);border:1px solid var(--sel);
  border-radius:10px;padding:8px 14px;font-size:13.5px;display:none;box-shadow:0 4px 14px rgba(0,0,0,.18)}
#done{position:absolute;top:12px;right:14px;background:var(--up);color:#fff;border-radius:10px;
  padding:6px 12px;font-size:13px;display:none;cursor:pointer;user-select:none}
#help{margin:4px 16px 8px;color:var(--muted);font-size:12px}
#marks{margin:0 16px 40px}
#marks table{border-collapse:collapse;font-size:12.5px}
#marks td,#marks th{padding:3px 10px;border-bottom:1px solid var(--border);text-align:left}
#marks button{padding:1px 8px;font-size:11.5px}
kbd{background:var(--card);border:1px solid var(--border);border-radius:4px;
  padding:0 5px;font-size:11px;font-family:inherit}
</style></head><body>
<header>
  <h1>Mark Setups</h1>
  <select id="day"></select>
  <button id="play">▶ play</button>
  <span class="pill">speed <span id="spd"></span> bars/s</span>
  <span class="pill" id="tf" style="font-weight:650"></span>
  <span class="pill" id="gap"></span>
  <span class="pill">Y <button onclick="zoomY(1/1.25)">−</button>
    <button onclick="zoomY(1.25)">+</button>
    <button onclick="zoomY(0)">reset</button></span>
  <span class="pill">draw
    <button id="t_none" class="on" onclick="setTool('none')">✋</button>
    <button id="t_line" onclick="setTool('line')">line</button>
    <button id="t_box" onclick="setTool('box')">box</button>
    <button id="t_fib" onclick="setTool('fib')">fib</button></span>
  <span class="pill">X <button onclick="zoomX(1/1.25)">−</button>
    <button onclick="zoomX(1.25)">+</button>
    <button onclick="zoomX(0)">fit</button></span>
  <span class="pill" id="pos"></span>
  <span class="pill" id="nmarks"></span>
  <span class="pill" style="margin-left:auto">forward-only reveal · price + MQ levels only</span>
</header>
<div id="stage">
  <canvas id="cv" height="760"></canvas>
  <div id="prompt"></div>
  <div id="picker"></div>
  <div id="done" onclick="nextDay()" title="load the next session">day complete — next session ▸</div>
</div>
<div id="help">
  <kbd>space</kbd> play/pause · <kbd>→</kbd> +1 bar · <kbd>shift→</kbd> +10 ·
  <kbd>+</kbd>/<kbd>-</kbd> speed · <kbd>↑</kbd>/<kbd>↓</kbd> price zoom · <kbd>[</kbd>/<kbd>]</kbd> bar width · click a revealed bar to select ·
  mark: <kbd>1</kbd>H1 <kbd>2</kbd>H2 <kbd>3</kbd>L1 <kbd>4</kbd>L2 <kbd>5</kbd>W1P
  <kbd>6</kbd>BOFT <kbd>7</kbd>DBBull <kbd>8</kbd>DTBear <kbd>9</kbd>TFTO
  <kbd>0</kbd>BOPB <kbd>F</kbd>fade2 <kbd>O</kbd>other —
  H/L/DB/DT pre-fill the side, else <kbd>L</kbd> long / <kbd>S</kbd> short;
  then <kbd>A</kbd>/<kbd>B</kbd> grade or <kbd>enter</kbd> skip ·
  <kbd>esc</kbd> cancel · <kbd>Q</kbd>/<kbd>W</kbd>/<kbd>E</kbd> wedge push 1/2/3 · draw tools save per day (click a drawing then <kbd>del</kbd> to remove) · <kbd>M</kbd> mark current bar · click a bar for the popup · <kbd>Z</kbd> undo last mark ·
  wheel/drag to look back (view only — never reveals)
</div>
<div id="marks"></div>
<script>
const DAYS=__DAYS__;
const SETUPS=__SETUPS__;                 // key -> [hotkey,label,badge,dir]
const SLABEL=k=>SETUPS[k]?SETUPS[k][1]:k;
const SBADGE=k=>SETUPS[k]?SETUPS[k][2]:"?";
const SKEY={};for(const k in SETUPS)SKEY[SETUPS[k][0]]=k;
const LC={cr:"--cr",cr0:"--cr",ps:"--ps",ps0:"--ps",hvl:"--hvl",hvl0:"--hvl",
          gw0:"--gw",d1_min:"--band",d1_max:"--band"};
let bars=[],levels=[],marks=[],day=null,atr=[],prev=null,gap=null;
let drawings=[],tool="none",dragging=null,selDraw=null;
let reveal=0,sel=null,follow=true,playing=false,timer=null,speed=4,scroll=0;
let pending=null; // {setup, direction}
const cv=document.getElementById("cv"),ctx=cv.getContext("2d");
const css=v=>getComputedStyle(document.documentElement).getPropertyValue(v).trim();
// BW is now derived: the WHOLE session (plus one prior-session bar) is laid out
// across the canvas, so 81 bars fill the screen instead of scrolling past a fixed
// 9px slot. CH fills the viewport height.
let BW=9,CH=560,yZoom=1,xZoom=1;   // 1 = fit; <1 compresses, >1 expands
const LPAD=62,RPAD=88;
function slots(){return bars.length+1;}            // +1 = prior session's last bar
function fitBW(W){return Math.max(1.2,(W-LPAD-RPAD)/slots()*xZoom);}
function availW(){return cv.clientWidth-LPAD-RPAD;}
function xOff(){                       // pan so the reveal edge stays on screen
  const t=slots()*BW,a=availW();
  if(t<=a)return 0;
  const revX=(reveal+2)*BW;
  return Math.max(0,Math.min(t-a,revX-a+BW*3));}
let dpr=1;
function sizeCanvas(){dpr=window.devicePixelRatio||1;
  const w=cv.clientWidth;
  CH=Math.max(420,window.innerHeight-Math.round(document.querySelector("header").offsetHeight)
      -Math.round(document.getElementById("help").offsetHeight)-42);
  cv.style.height=CH+"px";
  cv.width=w*dpr;cv.height=CH*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);
  if(bars.length)BW=fitBW(w);}
async function loadDay(d){
  const r=await fetch("/api/day?d="+d);const j=await r.json();
  day=d;bars=j.bars;levels=j.levels;marks=j.marks;atr=j.atr||[];prev=j.prev;gap=j.gap;
  drawings=j.drawings||[];selDraw=null;
  reveal=0;
  sel=null;follow=true;scroll=0;pause();draw();table();tfPill();}
function pause(){playing=false;clearInterval(timer);document.getElementById("play").textContent="▶ play";
  document.getElementById("play").classList.remove("on");}
function play(){if(reveal>=bars.length-1)return;playing=true;
  document.getElementById("play").textContent="❚❚ pause";document.getElementById("play").classList.add("on");
  clearInterval(timer);timer=setInterval(()=>{step(1);if(reveal>=bars.length-1)pause();},1000/speed);}
function step(n){reveal=Math.min(bars.length-1,reveal+n);if(follow)scroll=0;
  if(sel===null||follow)sel=null;draw();}
function xIdx(i){return LPAD+(i+1)*BW+BW/2-xOff();}
function draw(){
  if(!bars.length)return;
  const W=cv.width/dpr,H=CH,padB=26;
  BW=fitBW(W);
  ctx.clearRect(0,0,W,H);
  const iEnd=reveal, i0=0;
  const vis=bars.slice(0,iEnd+1);
  // the prior bar participates in the price scale so the gap is visible
  let lo=Math.min(...vis.map(b=>b[4])),hi=Math.max(...vis.map(b=>b[3]));
  if(prev){lo=Math.min(lo,prev.l);hi=Math.max(hi,prev.h);}
  if(hi-lo<8){const m=(hi+lo)/2;lo=m-4;hi=m+4;}
  const pad=(hi-lo)*0.08;lo-=pad;hi+=pad;
  // yZoom<1 shows MORE price in the same pixels (compressed); >1 zooms in
  const mid=(hi+lo)/2,half=(hi-lo)/2/yZoom;lo=mid-half;hi=mid+half;
  const y=p=>(hi-p)/(hi-lo)*(H-padB-10)+10;
  YLO=lo;YHI=hi;YH=H;YPADB=padB;
  // gridlines
  ctx.strokeStyle=css("--grid");ctx.lineWidth=1;ctx.font="10.5px system-ui";
  ctx.fillStyle=css("--muted");
  const stepP=(hi-lo)>40?10:(hi-lo)>16?5:2;
  for(let p=Math.ceil(lo/stepP)*stepP;p<hi;p+=stepP){
    ctx.beginPath();ctx.moveTo(60,y(p));ctx.lineTo(W-8,y(p));ctx.stroke();
    ctx.fillText(p.toFixed(0),8,y(p)+3);}
  // 1x ATR(14) zone around CR and PS, on the chart timeframe.
  // ATR is taken AT THE REVEAL EDGE (atr[reveal]) — not the session's final ATR —
  // so the zone is only ever as wide as what was knowable at that bar.
  const aNow=atr.length?atr[Math.min(reveal,atr.length-1)]:0;
  if(aNow>0){
    for(const [p,name] of levels){
      const stem=name.split("+")[0];
      if(stem!=="cr"&&stem!=="ps"&&stem!=="cr0"&&stem!=="ps0")continue;
      const yTop=y(p+aNow), yBot=y(p-aNow);
      if(yBot<0||yTop>H)continue;
      ctx.fillStyle=css(stem.startsWith("cr")?"--cr":"--ps");
      ctx.globalAlpha=0.10;
      ctx.fillRect(60,yTop,W-68,Math.max(1,yBot-yTop));
      ctx.globalAlpha=1;
      ctx.strokeStyle=css(stem.startsWith("cr")?"--cr":"--ps");
      ctx.setLineDash([2,3]);ctx.lineWidth=1;
      ctx.beginPath();ctx.moveTo(60,yTop);ctx.lineTo(W-8,yTop);ctx.stroke();
      ctx.beginPath();ctx.moveTo(60,yBot);ctx.lineTo(W-8,yBot);ctx.stroke();
      ctx.setLineDash([]);
    }
  }
  // HOY / LOY / COY — the prior session's high, low and close. Known before the
  // open, so legitimate at reveal 0.
  if(prev){
    ctx.font="10.5px system-ui";
    const yl=[[prev.hi,"HOY"],[prev.lo,"LOY"],[prev.c,"COY"]];
    if(prev.vah!==undefined)yl.push([prev.vah,"VAH"],[prev.val,"VAL"],[prev.poc,"POC"]);
    for(const [p,lab] of yl){
      if(p>hi||p<lo){
        // off the top/bottom of the current scale — pin it to the edge with an
        // arrow rather than dropping it silently, which is what happened before
        const above=p>hi, yy=above?14:H-padB-4;
        ctx.fillStyle=css("--yday");ctx.font="10.5px system-ui";
        const t=(above?"▲ ":"▼ ")+lab+" "+p.toFixed(2)+" (off scale)";
        ctx.fillText(t,W-10-ctx.measureText(t).width,yy);
        continue;}
      const isVA=(lab==="VAH"||lab==="VAL"||lab==="POC");
      ctx.strokeStyle=css(isVA?"--va":"--yday");ctx.lineWidth=isVA?1.1:1.3;
      ctx.setLineDash(lab==="POC"?[2,3]:[7,4]);
      ctx.beginPath();ctx.moveTo(LPAD,y(p));ctx.lineTo(W-8,y(p));ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle=css(isVA?"--va":"--yday");
      const t=lab+" "+p.toFixed(2);
      ctx.fillText(t,W-10-ctx.measureText(t).width,y(p)+11);}
  }
  // MQ levels (in view)
  ctx.font="10px system-ui";
  for(const [p,name] of levels){
    if(p<lo||p>hi)continue;
    const stem=name.split("+")[0];
    ctx.strokeStyle=css(LC[stem]||"--gex");
    ctx.setLineDash(name.startsWith("d1_")?[2,4]:(LC[stem]?[]:[4,4]));
    ctx.lineWidth=LC[stem]&&!name.startsWith("d1_")?1.4:1;
    ctx.beginPath();ctx.moveTo(60,y(p));ctx.lineTo(W-8,y(p));ctx.stroke();ctx.setLineDash([]);
    ctx.fillStyle=css(LC[stem]||"--gex");
    ctx.fillText(name+" "+p,W-8-ctx.measureText(name+" "+p).width,y(p)-3);}
  // ---- saved drawings (visual aids) ----------------------------------------
  const FIB=[0,0.236,0.382,0.5,0.618,0.786,1];
  for(const g of drawings){
    const X1=barToPx(g.x1),X2=barToPx(g.x2),Y1=y(g.y1),Y2=y(g.y2);
    const on=selDraw===g.id;
    ctx.strokeStyle=css(on?"--sel":"--draw");ctx.lineWidth=on?2:1.4;
    ctx.fillStyle=css(on?"--sel":"--draw");
    if(g.type==="line"){
      ctx.beginPath();ctx.moveTo(X1,Y1);ctx.lineTo(X2,Y2);ctx.stroke();
    } else if(g.type==="box"){
      ctx.globalAlpha=0.10;
      ctx.fillRect(Math.min(X1,X2),Math.min(Y1,Y2),Math.abs(X2-X1),Math.abs(Y2-Y1));
      ctx.globalAlpha=1;
      ctx.strokeRect(Math.min(X1,X2),Math.min(Y1,Y2),Math.abs(X2-X1),Math.abs(Y2-Y1));
    } else if(g.type==="fib"){
      ctx.font="9.5px system-ui";
      for(const f of FIB){
        const p=g.y1+(g.y2-g.y1)*f, yy=y(p);
        ctx.globalAlpha=(f===0||f===1)?1:0.75;
        ctx.setLineDash((f===0||f===1)?[]:[4,3]);
        ctx.beginPath();ctx.moveTo(Math.min(X1,X2),yy);ctx.lineTo(Math.max(X1,X2),yy);ctx.stroke();
        ctx.setLineDash([]);ctx.globalAlpha=1;
        ctx.fillText((f*100).toFixed(1)+"%  "+p.toFixed(2),Math.max(X1,X2)+4,yy+3);}
    }
  }
  // live preview while dragging a new drawing
  if(dragging){
    const X1=barToPx(dragging.x1),Y1=y(dragging.y1),X2=dragging.px,Y2=dragging.py;
    ctx.strokeStyle=css("--sel");ctx.lineWidth=1.2;ctx.setLineDash([4,3]);
    if(dragging.type==="box")ctx.strokeRect(Math.min(X1,X2),Math.min(Y1,Y2),
      Math.abs(X2-X1),Math.abs(Y2-Y1));
    else{ctx.beginPath();ctx.moveTo(X1,Y1);ctx.lineTo(X2,Y2);ctx.stroke();}
    ctx.setLineDash([]);
  }
  // ---- wedge chains: W1 -> W2 -> W3 joined so the wedge reads as one object --
  const wedges={};
  for(const m of marks){
    if(!m.wedge_id||!["w1","w2","w3"].includes(m.setup))continue;
    (wedges[m.wedge_id]=wedges[m.wedge_id]||[]).push(m);}
  for(const wid in wedges){
    const ws=wedges[wid].slice().sort((a,b)=>a.setup.localeCompare(b.setup));
    const pts=ws.map(m=>{const i=bars.findIndex(b=>b[0]==m.bar_idx);
      if(i<0)return null;
      const b=bars[i];
      return [barToPx(i),y(m.direction==="long"?b[3]:b[4])];}).filter(Boolean);
    if(pts.length<2)continue;
    ctx.strokeStyle=css("--wedge");ctx.lineWidth=1.6;ctx.setLineDash([6,3]);
    ctx.beginPath();ctx.moveTo(pts[0][0],pts[0][1]);
    for(const q of pts.slice(1))ctx.lineTo(q[0],q[1]);
    ctx.stroke();ctx.setLineDash([]);
    ctx.fillStyle=css("--wedge");ctx.font="10px system-ui";
    ctx.fillText(wid.slice(-2)+(pts.length===3?"":" ("+pts.length+"/3)"),
      pts[pts.length-1][0]+5,pts[pts.length-1][1]-5);}
  // candles
  let lastLbl=-1;
  const BODY=Math.max(2,BW*0.62), WICK=Math.max(1,BW*0.13);
  // prior session's final bar, drawn dimmed in slot 0 with a divider
  if(prev){
    const px=LPAD+BW/2-xOff();
    ctx.globalAlpha=0.55;
    ctx.strokeStyle=ctx.fillStyle=css(prev.c>=prev.o?"--up":"--dn");
    ctx.lineWidth=WICK;
    ctx.beginPath();ctx.moveTo(px,y(prev.h));ctx.lineTo(px,y(prev.l));ctx.stroke();
    const pyo=y(Math.max(prev.o,prev.c)),pyc=y(Math.min(prev.o,prev.c));
    ctx.fillRect(px-BODY/2,pyo,BODY,Math.max(1,pyc-pyo));
    ctx.globalAlpha=1;
    ctx.strokeStyle=css("--muted");ctx.setLineDash([3,3]);ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(LPAD+BW-xOff(),10);ctx.lineTo(LPAD+BW-xOff(),H-padB);ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle=css("--muted");ctx.font="10px system-ui";
    ctx.fillText("prev "+prev.day.slice(5),LPAD-2,H-8);
    // prior close as a reference line across the session
    ctx.strokeStyle=css("--muted");ctx.setLineDash([1,4]);
    ctx.beginPath();ctx.moveTo(LPAD,y(prev.c));ctx.lineTo(W-8,y(prev.c));ctx.stroke();
    ctx.setLineDash([]);
  }
  for(let i=i0;i<=iEnd;i++){
    const [bi,t,o,h,l,c]=bars[i],x=xIdx(i);
    const up=c>=o;ctx.strokeStyle=ctx.fillStyle=css(up?"--up":"--dn");
    ctx.lineWidth=WICK;
    ctx.beginPath();ctx.moveTo(x,y(h));ctx.lineTo(x,y(l));ctx.stroke();
    const yo=y(Math.max(o,c)),yc=y(Math.min(o,c));
    ctx.fillRect(x-BODY/2,yo,BODY,Math.max(1,yc-yo));
    if(sel===i){ctx.strokeStyle=css("--sel");ctx.lineWidth=1.5;
      ctx.strokeRect(x-BODY/2-2,y(h)-4,BODY+4,y(l)-y(h)+8);}
    const mins=parseInt(t.slice(3));
    // bar ordinal every 10 bars (and on the selected one) — sits above the times
    if((i+1)%10===0||i===sel){ctx.fillStyle=css(i===sel?"--sel":"--muted");
      ctx.font="9.5px system-ui";
      const bn="#"+(i+1);ctx.fillText(bn,x-ctx.measureText(bn).width/2,H-20);}
    if(mins%30===0&&i-lastLbl>=6){lastLbl=i;ctx.fillStyle=css("--muted");
      ctx.font="10.5px system-ui";ctx.fillText(t,x-13,H-8);
      ctx.strokeStyle=css("--grid");ctx.beginPath();ctx.moveTo(x,10);ctx.lineTo(x,H-padB);ctx.stroke();}
  }
  // marks
  for(const m of marks){
    const i=bars.findIndex(b=>b[0]==m.bar_idx);
    if(i<i0||i>iEnd)continue;
    const x=xIdx(i),b=bars[i],lng=m.direction==="long";
    const isW=["w1","w2","w3"].includes(m.setup);
    if(isW){
      // long wedge -> dot on the HIGH, short wedge -> dot on the LOW
      const py=y(lng?b[3]:b[4]);
      ctx.fillStyle=css("--wedge");
      ctx.beginPath();ctx.arc(x,py,4.5,0,Math.PI*2);ctx.fill();
      ctx.strokeStyle=css("--surface");ctx.lineWidth=1.2;ctx.stroke();
      ctx.fillStyle=css("--wedge");ctx.font="bold 10px system-ui";
      ctx.fillText(SBADGE(m.setup),x-6,lng?py-9:py+17);
      continue;}
    ctx.fillStyle=css(lng?"--long":"--short");
    const yy=lng?y(b[4])+14:y(b[3])-14;
    ctx.beginPath();
    if(lng){ctx.moveTo(x,yy-7);ctx.lineTo(x-5,yy);ctx.lineTo(x+5,yy);}
    else{ctx.moveTo(x,yy+7);ctx.lineTo(x-5,yy);ctx.lineTo(x+5,yy);}
    ctx.closePath();ctx.fill();
    ctx.font="bold 10px system-ui";
    ctx.fillText(SBADGE(m.setup)+(m.grade||""),
                 x-6,lng?yy+16:yy-10);}
  // reveal edge
  if(scroll===0){const x=xIdx(iEnd,i0)+BW;ctx.strokeStyle=css("--axis");
    ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(x,10);ctx.lineTo(x,H-padB);ctx.stroke();
    ctx.setLineDash([]);}
  document.getElementById("pos").textContent=
    `bar ${reveal+1}/${bars.length} · ${bars[reveal][1]}`+(scroll?` (viewing −${scroll})`:"");
  document.getElementById("nmarks").textContent=`${marks.length} marks this day`;
  document.getElementById("done").style.display=reveal>=bars.length-1?"block":"none";
  document.getElementById("spd").textContent=speed;
}
function nextDay(){
  const i=DAYS.indexOf(day);
  if(i<0||i>=DAYS.length-1){
    const el=document.getElementById("done");
    el.textContent="last session in the data";
    setTimeout(()=>{el.textContent="day complete — next session ▸";},1600);
    return;}
  const nd=DAYS[i+1];
  document.getElementById("day").value=nd;
  loadDay(nd);}
// ---- click-to-mark popup ---------------------------------------------------
function closePicker(){document.getElementById("picker").style.display="none";}
function openPicker(i){
  if(i<0||i>reveal)return;                 // never offer a bar that isn't revealed
  sel=i;draw();
  const pk=document.getElementById("picker");
  const b=bars[i];
  pk.dataset.bar=i;
  let g="";
  for(const k in SETUPS)
    g+=`<button onclick="pick('${k}')">${SETUPS[k][1]}<br><span style="opacity:.55">${SETUPS[k][0]}</span></button>`;
  pk.innerHTML=`<div class="hd">bar ${i+1} · ${b[1]} · close ${b[5]}</div>`+
    `<div class="grid">${g}</div>`+
    `<div class="row"><button onclick="closePicker()">esc</button></div>`;
  const st=document.getElementById("stage").getBoundingClientRect();
  const x=Math.min(Math.max(xIdx(i)-140,8),st.width-310);
  pk.style.left=x+"px";pk.style.top="46px";pk.style.display="block";}
function pick(k){
  pending={setup:k};
  if(SETUPS[k][3])pending.direction=SETUPS[k][3];
  const pk=document.getElementById("picker");
  const i=+pk.dataset.bar,b=bars[i];
  if(!pending.direction){
    pk.innerHTML=`<div class="hd">${SETUPS[k][1]} · bar ${i+1} — which side?</div>`+
      `<div class="row"><button onclick="side('long')">L long</button>`+
      `<button onclick="side('short')">S short</button>`+
      `<button onclick="cancelPick()">esc</button></div>`;
  } else side(pending.direction);}
function side(d){
  pending.direction=d;
  const pk=document.getElementById("picker");
  const i=+pk.dataset.bar;
  pk.innerHTML=`<div class="hd">${SLABEL(pending.setup)} ${d} · bar ${i+1} — grade?</div>`+
    `<div class="row"><button onclick="grade('A')">A</button>`+
    `<button onclick="grade('B')">B</button>`+
    `<button onclick="grade('')">skip</button>`+
    `<button onclick="cancelPick()">esc</button></div>`;}
function grade(g){const i=+document.getElementById("picker").dataset.bar;
  sel=i;commit(g);closePicker();}
function cancelPick(){pending=null;closePicker();}
function setTool(t){tool=t;
  for(const n of ["none","line","box","fib"])
    document.getElementById("t_"+n).classList.toggle("on",n===t);
  document.getElementById("cv").style.cursor=(t==="none"?"crosshair":"copy");}
// pixel <-> data. Drawings store bar index + price so zooming never moves them.
function pxToBar(x){return (x-LPAD+xOff()-BW/2)/BW-1;}
function barToPx(bi){return LPAD+(bi+1)*BW+BW/2-xOff();}
let YLO=0,YHI=1,YH=1,YPADB=26;
function pxToPrice(py){return YHI-(py-10)/(YH-YPADB-10)*(YHI-YLO);}
function priceToPx(p){return (YHI-p)/(YHI-YLO)*(YH-YPADB-10)+10;}
async function saveDrawing(g){
  const r=await fetch("/api/draw",{method:"POST",
    body:JSON.stringify({day,drawing:g})});
  const j=await r.json();
  if(j.ok){drawings.push(j.drawing);draw();} else alert(j.err);}
async function deleteDrawing(id){
  await fetch("/api/undraw",{method:"POST",body:JSON.stringify({day,id})});
  drawings=drawings.filter(g=>g.id!==id);selDraw=null;draw();}
function zoomY(f){yZoom=f?Math.max(0.15,Math.min(8,yZoom*f)):1;draw();}
function zoomX(f){xZoom=f?Math.max(0.2,Math.min(12,xZoom*f)):1;draw();}
function tfPill(){
  const el=document.getElementById("tf");
  let lab="?";
  if(bars.length>1){
    const t=x=>{const p=bars[x][1].split(":");return +p[0]*60+ +p[1];};
    lab=(t(1)-t(0))+"M";
  }
  el.textContent=lab+" · "+bars.length+" bars";
  const g=document.getElementById("gap");
  if(gap&&prev){
    const sign=gap.pts>0?"+":"";
    g.innerHTML="gap <b>"+sign+gap.pts.toFixed(2)+"</b> ("+sign+gap.pct.toFixed(2)+"%"
      +(gap.atr_mult!==null?" · "+gap.atr_mult.toFixed(2)+"× prev ATR":"")+") · open "
      +gap.vs_prev_range+" · prev close "+prev.c.toFixed(2);
    g.style.color=gap.pts>0?css("--up"):(gap.pts<0?css("--dn"):css("--ink2"));
  } else {g.textContent="first session — no prior bar";g.style.color="";}}
function table(){
  const el=document.getElementById("marks");
  if(!marks.length){el.innerHTML="";return;}
  el.innerHTML="<table><tr><th>time</th><th>setup</th><th>dir</th><th>grade</th>"+
    "<th>price</th><th></th></tr>"+marks.map(m=>
    `<tr><td>${m.bar_time.slice(11)}</td><td>${SLABEL(m.setup)}</td><td>${m.direction}</td>`+
    `<td>${m.grade||"—"}</td><td>${m.price}</td>`+
    `<td><button onclick="unmark('${m.bar_idx}','${m.setup}')">✕</button></td></tr>`).join("")+
    "</table>";}
async function unmark(bi,setup){
  await fetch("/api/unmark",{method:"POST",body:JSON.stringify({day,bar_idx:+bi,setup})});
  marks=marks.filter(m=>!(m.bar_idx==bi&&m.setup===setup));draw();table();}
function promptTxt(){
  const el=document.getElementById("prompt");
  if(!pending){el.style.display="none";return;}
  const i=sel===null?reveal:sel,b=bars[i];
  el.style.display="block";
  el.innerHTML=`<b>${SLABEL(pending.setup)}</b> @ ${b[1]} (${b[5]}) — `+
    (!pending.direction?"direction? <kbd>L</kbd>ong / <kbd>S</kbd>hort":
     `${pending.direction} — grade? <kbd>A</kbd>/<kbd>B</kbd> or <kbd>enter</kbd> to skip`);}
async function commit(grade){
  const i=sel===null?reveal:sel,b=bars[i];
  const body={day,bar_idx:b[0],setup:pending.setup,direction:pending.direction,
              grade:grade||"",reveal_idx:bars[reveal][0]};
  pending=null;promptTxt();
  const r=await fetch("/api/mark",{method:"POST",body:JSON.stringify(body)});
  const j=await r.json();
  if(j.ok){marks.push({...body,bar_time:day+" "+b[1],price:b[5],
    bar_idx:String(b[0])});sel=null;draw();table();}
  else alert(j.err);}
document.addEventListener("keydown",e=>{
  const k=e.key;
  // Arrow keys were being consumed by the day <select> / zoom buttons once they
  // had focus, so the right arrow jumped a whole SESSION instead of one bar.
  const tag=(e.target&&e.target.tagName)||"";
  if(tag==="SELECT"||tag==="INPUT"||tag==="BUTTON"){
    if(k.startsWith("Arrow")||k===" "){e.target.blur();e.preventDefault();}
  }
  if(k==="Escape"){cancelPick();}
  if(pending){
    if(k==="Escape"){pending=null;promptTxt();}
    else if(!pending.direction){
      if(k==="l"||k==="L"){pending.direction="long";promptTxt();}
      if(k==="s"||k==="S"){pending.direction="short";promptTxt();}}
    else{
      if(k==="a"||k==="A")commit("A");
      else if(k==="b"||k==="B")commit("B");
      else if(k==="Enter")commit("");}
    e.preventDefault();return;}
  if(k===" "){playing?pause():play();e.preventDefault();}
  else if(k==="ArrowRight"){pause();step(e.shiftKey?10:1);e.preventDefault();}
  else if(k==="ArrowLeft"){pause();
    sel=(sel===null?reveal:Math.max(0,sel-(e.shiftKey?10:1)));draw();e.preventDefault();}
  else if(k==="ArrowUp"){zoomY(1.25);e.preventDefault();}
  else if(k==="ArrowDown"){zoomY(1/1.25);e.preventDefault();}
  else if(k==="]"){zoomX(1.25);}
  else if(k==="["){zoomX(1/1.25);}
  else if(k==="+"||k==="="){speed=Math.min(20,speed+1);if(playing)play();draw();}
  else if(k==="-"){speed=Math.max(1,speed-1);if(playing)play();draw();}
  else if(SKEY[k.toLowerCase()]){
    const sk=SKEY[k.toLowerCase()];
    pending={setup:sk};
    if(SETUPS[sk][3])pending.direction=SETUPS[sk][3];   // H*/L*/DB/DT imply a side
    promptTxt();}
  else if(k==="m"||k==="M"){openPicker(sel===null?reveal:sel);e.preventDefault();}
  else if((k==="Delete"||k==="Backspace")&&selDraw){deleteDrawing(selDraw);e.preventDefault();}
  else if(k==="z"||k==="Z"){const m=marks[marks.length-1];
    if(m)unmark(m.bar_idx,m.setup);}
});
function hitDrawing(x,py){
  for(let k=drawings.length-1;k>=0;k--){
    const g=drawings[k];
    const X1=barToPx(g.x1),X2=barToPx(g.x2),Y1=priceToPx(g.y1),Y2=priceToPx(g.y2);
    if(g.type==="box"||g.type==="fib"){
      if(x>=Math.min(X1,X2)-4&&x<=Math.max(X1,X2)+4&&
         py>=Math.min(Y1,Y2)-4&&py<=Math.max(Y1,Y2)+4)return g;
    } else {                       // distance to the segment
      const dx=X2-X1,dy=Y2-Y1,L=Math.hypot(dx,dy)||1;
      const t=Math.max(0,Math.min(1,((x-X1)*dx+(py-Y1)*dy)/(L*L)));
      if(Math.hypot(x-(X1+t*dx),py-(Y1+t*dy))<6)return g;}}
  return null;}
cv.addEventListener("mousedown",e=>{
  if(tool==="none")return;
  const r=cv.getBoundingClientRect();
  dragging={type:tool,x1:pxToBar(e.clientX-r.left),y1:pxToPrice(e.clientY-r.top),
            px:e.clientX-r.left,py:e.clientY-r.top};
  e.preventDefault();});
cv.addEventListener("mousemove",e=>{
  if(!dragging)return;
  const r=cv.getBoundingClientRect();
  dragging.px=e.clientX-r.left;dragging.py=e.clientY-r.top;draw();});
cv.addEventListener("mouseup",e=>{
  if(!dragging)return;
  const r=cv.getBoundingClientRect();
  const g={type:dragging.type,x1:dragging.x1,y1:dragging.y1,
           x2:pxToBar(e.clientX-r.left),y2:pxToPrice(e.clientY-r.top)};
  const d0=dragging;dragging=null;
  // ignore accidental click-sized drags
  if(Math.hypot(e.clientX-r.left-barToPx(d0.x1),e.clientY-r.top-priceToPx(d0.y1))<6){
    draw();return;}
  saveDrawing(g);});
cv.addEventListener("click",e=>{
  const rect=cv.getBoundingClientRect(),x=e.clientX-rect.left,py=e.clientY-rect.top;
  if(tool!=="none")return;                    // drawing mode owns the mouse
  const g=hitDrawing(x,py);                   // click a drawing to select it
  if(g){selDraw=(selDraw===g.id?null:g.id);draw();return;}
  selDraw=null;
  const i=Math.round((x-LPAD-BW/2)/BW)-1;
  if(i>=0&&i<=reveal){openPicker(i);return;}
  draw();});
cv.addEventListener("wheel",e=>{e.preventDefault();
  scroll=Math.max(0,Math.min(reveal,scroll+(e.deltaY>0?-10:10)));follow=scroll===0;draw();},
  {passive:false});
document.getElementById("play").onclick=()=>playing?pause():play();
const sel_d=document.getElementById("day");
for(const d of DAYS){const o=document.createElement("option");o.value=o.textContent=d;sel_d.appendChild(o);}
sel_d.onchange=()=>{loadDay(sel_d.value);sel_d.blur();};
window.addEventListener("resize",()=>{sizeCanvas();draw();});
sizeCanvas();loadDay(DAYS[0]);
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8630)
    ap.add_argument("--open", action="store_true")
    a = ap.parse_args()
    Handler.days = load_days()
    print(f"loaded {len(Handler.days)} sessions: {', '.join(Handler.days)}")
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"marking tool at {url}")
    if a.open:
        webbrowser.open(url)
    srv.serve_forever()


if __name__ == "__main__":
    main()

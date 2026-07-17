#!/usr/bin/env python3
"""
discord_report.py — turn Discord exports into an actionable intel report.

Consumes raw DiscordChatExporter JSON in data/discord/raw/*.json (each file
carries guild+channel metadata and a messages[] list) and produces:

  data/discord/report.json   machine-readable summary (feeds Mission Control)
  data/discord/report.html   human dashboard (per-channel: nuggets, setups, links)

Extraction buckets ("the reporting model"):
  LINKS      categorized URLs (youtube / tradingview / twitter-x / github /
             substack / gdocs / image / other) with context + author + ts
  SETUPS     "testable" messages: ticker + price level + setup vocabulary
             (long/short/entry/stop/target/gamma/level/reject/breakout/fade...)
  NUGGETS    knowledge/insight lines (rules of thumb, definitions, "the key is",
             "i've found that", parameter/threshold statements)
  TICKERS    frequency table of instruments mentioned
  VOICES     who posts the most signal (by setups+nuggets, not raw volume)

Usage:
  python scripts/discord_report.py            # all raw exports
  python scripts/discord_report.py --open      # + open the HTML in VSCode
"""
from __future__ import annotations
import argparse, html, json, re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "discord" / "raw"
OUT_JSON = ROOT / "data" / "discord" / "report.json"
OUT_HTML = ROOT / "data" / "discord" / "report.html"

URL_RE = re.compile(r"https?://[^\s<>\)\]]+")
# tickers: $AAPL, ES/NQ/RTY/YM/CL/GC futures, common index symbols
TICKER_RE = re.compile(
    r"(?<![A-Za-z])(?:\$[A-Za-z]{1,5}"
    r"|/?(?:ES|NQ|RTY|YM|CL|GC|SI|NG|ZB|ZN|ZC|ZS|6E|6J|6A|6B)\d?!?"
    r"|SPX|NDX|VIX|SPY|QQQ|IWM|DXY|BTC|ETH)(?![A-Za-z])"
)
PRICE_RE = re.compile(r"\b\d{2,6}(?:\.\d{1,4})?\b")

SETUP_VOCAB = re.compile(
    r"\b(long|short|entry|enter|stop|target|tp\d?|sl|reject(?:ion)?|"
    r"breakout|break down|breakdown|fade|bounce|reclaim|reversal|"
    r"gamma|gex|vix|blind|hvl|call wall|put wall|0dte|absorb|absorption|"
    r"trend day|balance|value area|vah|val|poc|level|support|resistance)\b",
    re.I,
)
NUGGET_VOCAB = re.compile(
    r"\b(the key is|i(?:'ve| have) found|rule of thumb|generally|"
    r"tends to|usually|most of the time|the trick|remember to|"
    r"never |always |avoid |wait for|only trade|best when|works when|"
    r"if .* then|threshold|setting|parameter|backtest|win rate|expectancy|"
    r"edge|filter)\b",
    re.I,
)

LINK_KINDS = [
    ("youtube", re.compile(r"(youtube\.com|youtu\.be)", re.I)),
    ("tradingview", re.compile(r"tradingview\.com", re.I)),
    ("twitter-x", re.compile(r"(twitter\.com|x\.com)", re.I)),
    ("github", re.compile(r"github\.com", re.I)),
    ("substack", re.compile(r"substack\.com", re.I)),
    ("gdocs", re.compile(r"(docs\.google\.com|drive\.google\.com)", re.I)),
    ("image", re.compile(r"\.(png|jpg|jpeg|gif|webp)(\?|$)", re.I)),
]


def classify_link(url: str) -> str:
    for kind, rx in LINK_KINDS:
        if rx.search(url):
            return kind
    return "other"


def _salvage(text: str) -> dict | None:
    """Recover a truncated DCE export by trimming to the last complete message."""
    i = text.find('"messages"')
    if i < 0:
        return None
    br = text.find("[", i)
    if br < 0:
        return None
    # walk the array, tracking string/escape/brace depth; remember last spot
    # where depth returned to 1 (i.e. a complete message object just closed)
    depth = 0
    in_str = False
    esc = False
    last_complete = -1
    for j in range(br, len(text)):
        ch = text[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "[" or ch == "{":
            depth += 1
        elif ch == "]" or ch == "}":
            depth -= 1
            if depth == 1:  # a message object just closed
                last_complete = j
    if last_complete < 0:
        return None
    header = text[:br + 1]
    body = text[br + 1:last_complete + 1]
    try:
        msgs = json.loads("[" + body + "]") if not body.strip().startswith("{") \
            else json.loads("[" + body + "]")
        # header may carry guild/channel; parse it leniently
        meta = {}
        gm = re.search(r'"guild"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]*)"', text[:i])
        cm = re.search(r'"channel"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]*)"', text[:i])
        if gm:
            meta["guild"] = {"name": gm.group(1)}
        if cm:
            meta["channel"] = {"name": cm.group(1)}
        meta["messages"] = msgs
        return meta
    except Exception:
        return None


def iter_exports():
    for p in sorted(RAW_DIR.glob("*.json")):
        txt = p.read_text(encoding="utf-8")
        try:
            data = json.loads(txt)
        except Exception:
            data = _salvage(txt)
            if data is None:
                print(f"[discord_report] skip (unparseable): {p.name}")
                continue
            print(f"[discord_report] salvaged {len(data.get('messages',[]))} msgs from truncated {p.name}")
        if "messages" not in data:
            continue
        guild = (data.get("guild") or {}).get("name", "?")
        chan = (data.get("channel") or {}).get("name", p.stem)
        yield p, guild, chan, data["messages"]


def _merged_channels():
    """Group every raw export by (guild, channel) and dedupe messages by id, so a
    channel with both a full-history file and a later incremental file appears once."""
    buckets: dict = {}
    for p, guild, chan, msgs in iter_exports():
        key = (guild, chan)
        b = buckets.setdefault(key, {"guild": guild, "chan": chan, "seen": set(), "msgs": []})
        for m in msgs:
            mid = m.get("id")
            if mid in b["seen"]:
                continue
            b["seen"].add(mid)
            b["msgs"].append(m)
    for (guild, chan), b in buckets.items():
        # keep chronological order
        b["msgs"].sort(key=lambda m: m.get("timestamp", ""))
        yield guild, chan, b["msgs"]


# P&L / results talk — a proxy for a trader who actually posts outcomes
PNL_RE = re.compile(r"([+\-]?\$\s?\d[\d,]*(?:\.\d+)?|[+\-]\d[\d,]*\s?(?:pts|ticks|R\b)"
                    r"|\bP&?L\b|profit|\bwin(?:ning)?\b|\bloss\b|filled|entry|stopped out)", re.I)


def analyze():
    report = {"channels": [], "totals": {}}
    tick_total = Counter()
    kind_total = Counter()
    # per-author signal accumulation (for the Traders-to-Watch leaderboard)
    A = defaultdict(lambda: {"msgs": 0, "subst": 0, "chars": 0, "setups": 0,
                             "nuggets": 0, "pnl": 0, "links": 0,
                             "chans": Counter(), "first": "", "last": ""})
    for guild, chan, msgs in _merged_channels():
        p = type("P", (), {"name": f"{chan}"})()  # lightweight shim for existing refs
        links, setups, nuggets = [], [], []
        tickers = Counter()
        voice_signal = Counter()
        for m in msgs:
            content = (m.get("content") or "").strip()
            author = (m.get("author") or {}).get("name", "?")
            ts = m.get("timestamp", "")
            a = A[author]
            a["msgs"] += 1
            a["chars"] += len(content)
            a["chans"][chan] += 1
            if len(content) >= 120:
                a["subst"] += 1
            if PNL_RE.search(content):
                a["pnl"] += 1
            if ts and (not a["first"] or ts < a["first"]):
                a["first"] = ts
            if ts > a["last"]:
                a["last"] = ts
            # links (message content + attachments)
            urls = URL_RE.findall(content)
            urls += [a.get("url", "") for a in m.get("attachments", []) if a.get("url")]
            for u in urls:
                kind = classify_link(u)
                kind_total[kind] += 1
                a["links"] += 1
                links.append({"url": u, "kind": kind, "author": author,
                              "ts": ts, "ctx": content[:160]})
            # tickers
            for t in TICKER_RE.findall(content):
                tt = t.upper().lstrip("/")
                tickers[tt] += 1
                tick_total[tt] += 1
            # setups: needs ticker + a price + setup vocab
            has_ticker = bool(TICKER_RE.search(content))
            has_price = bool(PRICE_RE.search(content))
            if has_ticker and has_price and SETUP_VOCAB.search(content):
                setups.append({"author": author, "ts": ts, "text": content[:400]})
                voice_signal[author] += 1
                a["setups"] += 1
            # nuggets: insight vocab, reasonable length, not a pure link
            if (NUGGET_VOCAB.search(content) and len(content) > 40
                    and not content.startswith("http")):
                nuggets.append({"author": author, "ts": ts, "text": content[:400]})
                voice_signal[author] += 1
                a["nuggets"] += 1
        report["channels"].append({
            "guild": guild, "channel": chan, "file": p.name,
            "n_messages": len(msgs),
            "n_links": len(links), "n_setups": len(setups), "n_nuggets": len(nuggets),
            "top_tickers": tickers.most_common(15),
            "top_voices": voice_signal.most_common(10),
            "links": links, "setups": setups, "nuggets": nuggets,
        })
    report["totals"] = {
        "channels": len(report["channels"]),
        "messages": sum(c["n_messages"] for c in report["channels"]),
        "links": sum(c["n_links"] for c in report["channels"]),
        "setups": sum(c["n_setups"] for c in report["channels"]),
        "nuggets": sum(c["n_nuggets"] for c in report["channels"]),
        "top_tickers": tick_total.most_common(25),
        "link_kinds": kind_total.most_common(),
    }
    # ---- Traders to Watch: rank authors by a signal score ------------------
    # Score rewards SUBSTANCE (long posts), demonstrated OUTCOMES (P&L talk),
    # and teaching (setups+nuggets) — not raw chatter volume. Requires a
    # minimum footprint so one-off posters don't rank.
    authors = []
    for name, a in A.items():
        if a["msgs"] < 20 or name in ("?", "Deleted User"):
            continue
        avg = a["chars"] / max(a["msgs"], 1)
        score = (a["subst"] * 2.0 + a["pnl"] * 1.5 + a["setups"] * 1.2
                 + a["nuggets"] * 1.0 + min(avg, 300) * 0.15)
        authors.append({
            "author": name, "score": round(score),
            "msgs": a["msgs"], "substantive": a["subst"], "avg_len": round(avg),
            "pnl_posts": a["pnl"], "setups": a["setups"], "nuggets": a["nuggets"],
            "links": a["links"], "channels": a["chans"].most_common(4),
            "active": f"{(a['first'] or '')[:10]} → {(a['last'] or '')[:10]}",
        })
    authors.sort(key=lambda x: -x["score"])
    report["authors"] = authors[:60]
    return report


def esc(s):
    return html.escape(str(s), quote=True)


def render_html(rep: dict) -> str:
    t = rep["totals"]
    parts = ["""<!-- discord intel report -->
<style>
body{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;background:#0f1115;color:#e6e6e6;margin:0;padding:24px}
h1{font-size:20px;margin:0 0 4px} h2{font-size:16px;border-bottom:1px solid #2a2f3a;padding-bottom:6px;margin-top:32px}
h3{font-size:13px;color:#8fb7ff;margin:14px 0 6px;text-transform:uppercase;letter-spacing:.5px}
.kpis{display:flex;gap:14px;flex-wrap:wrap;margin:16px 0}
.kpi{background:#1a1e27;border:1px solid #2a2f3a;border-radius:10px;padding:12px 18px;min-width:110px}
.kpi .n{font-size:24px;font-weight:700} .kpi .l{font-size:11px;color:#9aa4b2;text-transform:uppercase}
.chip{display:inline-block;background:#232838;border:1px solid #313a4f;border-radius:12px;padding:2px 9px;margin:2px;font-size:12px}
.card{background:#161a22;border:1px solid #262c38;border-radius:8px;padding:10px 12px;margin:6px 0}
.meta{color:#7b8494;font-size:11px} a{color:#6fa8ff;text-decoration:none} a:hover{text-decoration:underline}
.chan{border:1px solid #262c38;border-radius:10px;padding:8px 16px;margin:10px 0;background:#12151c}
details summary{cursor:pointer;font-weight:600;font-size:15px;padding:6px 0}
.k-youtube{color:#ff6b6b}.k-tradingview{color:#4fd1c5}.k-github{color:#c9a2ff}.k-image{color:#9aa4b2}
</style>"""]
    parts.append(f"<h1>Discord Intel Report</h1><div class='meta'>Generated from {t['channels']} channel export(s)</div>")
    parts.append("<div class='kpis'>")
    for lab, key in [("Messages","messages"),("Setups","setups"),("Nuggets","nuggets"),("Links","links"),("Channels","channels")]:
        parts.append(f"<div class='kpi'><div class='n'>{t[key]:,}</div><div class='l'>{lab}</div></div>")
    parts.append("</div>")
    parts.append("<h3>Top instruments</h3><div>")
    for tk,n in t["top_tickers"]:
        parts.append(f"<span class='chip'>{esc(tk)} · {n}</span>")
    parts.append("</div>")
    parts.append("<h3>Link types</h3><div>")
    for k,n in t["link_kinds"]:
        parts.append(f"<span class='chip k-{esc(k)}'>{esc(k)} · {n}</span>")
    parts.append("</div>")

    for c in sorted(rep["channels"], key=lambda x:-(x["n_setups"]+x["n_nuggets"])):
        parts.append(f"<div class='chan'><details><summary>{esc(c['guild'])} / #{esc(c['channel'])} "
                     f"<span class='meta'>· {c['n_messages']} msgs · {c['n_setups']} setups · "
                     f"{c['n_nuggets']} nuggets · {c['n_links']} links</span></summary>")
        if c["top_tickers"]:
            parts.append("<div>"+"".join(f"<span class='chip'>{esc(tk)}·{n}</span>" for tk,n in c["top_tickers"])+"</div>")
        if c["setups"]:
            parts.append("<h3>Testable setups</h3>")
            for s in c["setups"][:40]:
                parts.append(f"<div class='card'>{esc(s['text'])}<div class='meta'>{esc(s['author'])} · {esc(s['ts'][:16])}</div></div>")
        if c["nuggets"]:
            parts.append("<h3>Nuggets</h3>")
            for s in c["nuggets"][:40]:
                parts.append(f"<div class='card'>{esc(s['text'])}<div class='meta'>{esc(s['author'])} · {esc(s['ts'][:16])}</div></div>")
        if c["links"]:
            parts.append("<h3>Links</h3>")
            for l in c["links"][:60]:
                parts.append(f"<div class='card'><a href='{esc(l['url'])}' target='_blank' class='k-{esc(l['kind'])}'>[{esc(l['kind'])}] {esc(l['url'][:90])}</a>"
                             f"<div class='meta'>{esc(l['author'])} · {esc(l['ctx'])}</div></div>")
        parts.append("</details></div>")
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()
    if not RAW_DIR.exists() or not list(RAW_DIR.glob("*.json")):
        print(f"[discord_report] no exports in {RAW_DIR}. Run discord_scrape.py first.")
        return
    rep = analyze()
    OUT_JSON.write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    OUT_HTML.write_text(render_html(rep), encoding="utf-8")
    t = rep["totals"]
    print(f"[discord_report] {t['channels']} channels | {t['messages']} msgs | "
          f"{t['setups']} setups | {t['nuggets']} nuggets | {t['links']} links")
    print(f"[discord_report] -> {OUT_HTML}")
    if args.open:
        import subprocess
        subprocess.run(["code", str(OUT_HTML)], shell=True)


if __name__ == "__main__":
    main()

"""Data Catalog — one place to see every data family in this project (S75E, Phase 1).

Three parts, deliberately decoupled so the 108 GB / 12k-file `data/` tree is NEVER
blind-walked on page load:

  1. REGISTRY  — catalog.yaml (hand-maintained), one entry per data family.
  2. SCANNER   — `data_catalog.py scan`: for each REGISTERED path only, compute size,
                 file_count, newest mtime, health verdict -> data/_catalog/manifest.json.
                 Per-family os.scandir (fast: whole 85 GB flatfiles dir measures in <0.1s).
  3. SERVER    — `data_catalog.py serve`: stdlib http.server; reads registry + cached
                 manifest and renders instantly. "Rescan" runs the scanner in a background
                 thread (never synchronously in the request handler).

Run:
  .venv/Scripts/python.exe scripts/data_catalog.py scan
  .venv/Scripts/python.exe scripts/data_catalog.py serve [--port 8620] [--open]
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "catalog.yaml"
MANIFEST = ROOT / "data" / "_catalog" / "manifest.json"
PY = ROOT / ".venv" / "Scripts" / "python.exe"

CATEGORY_ORDER = ["Raw vendor", "Ticks", "Bars/continuous", "MenthorQ",
                  "Options desk", "Research/WFA", "Educational", "Misc"]

_scan_lock = threading.Lock()
_scan_state = {"running": False, "log": "", "at": None}


# --------------------------------------------------------------------- registry
def load_registry():
    """Tiny stdlib loader for OUR catalog.yaml subset (no PyYAML dependency).

    Supported shape only: a top-level `families:` list of mappings; scalar values
    `key: value` (value may be single/double quoted); list values `paths:` followed
    by `  - item` lines. Colons inside free text must be quoted in the file.
    """
    fams = []
    cur = None
    list_key = None
    list_indent = -1  # indent of the `key:` that opened the active block list
    for raw in REGISTRY.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        s = line.strip()
        if s == "families:":
            continue
        # A `- item` line is a LIST ITEM (not a new family) only if it is indented
        # deeper than the key that opened the active list (e.g. paths:). Otherwise
        # the dash starts a new family.
        if s.startswith("-") and list_key is not None and indent > list_indent:
            cur[list_key].append(_unquote(s[1:].strip()))
            continue
        if s.startswith("- "):
            cur = {}
            fams.append(cur)
            list_key = None
            list_indent = -1
            s = s[2:].strip()  # fall through to parse the first key on the dash line
        if ":" in s and cur is not None:
            k, _, v = s.partition(":")
            k = k.strip()
            v = v.strip()
            if v == "":
                list_key = k
                list_indent = indent
                cur[k] = []
            else:
                cur[k] = _unquote(v)
                list_key = None
    # coerce types
    for f in fams:
        f.setdefault("paths", [])
        f["expected_freshness_days"] = _int(f.get("expected_freshness_days"), 999)
        f["count_rows"] = str(f.get("count_rows", "")).lower() == "true"
        f["optional"] = str(f.get("optional", "")).lower() == "true"
    return fams


def _unquote(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def _int(v, default):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------- scanner
def scan_path(path):
    """Recursive os.scandir over ONE registered path. Returns (n, size, newest_mtime).

    Handles both files (globs/single files) and directories. Never walks all of data/.
    """
    p = ROOT / path
    if not p.exists():
        return {"exists": False, "n": 0, "size": 0, "newest": None, "zero_byte": 0}
    n = size = zero = 0
    newest = 0.0
    if p.is_file():
        st = p.stat()
        return {"exists": True, "n": 1, "size": st.st_size,
                "newest": st.st_mtime, "zero_byte": 1 if st.st_size == 0 else 0}
    stack = [str(p)]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        else:
                            st = e.stat()
                            n += 1
                            size += st.st_size
                            if st.st_size == 0:
                                zero += 1
                            if st.st_mtime > newest:
                                newest = st.st_mtime
                    except OSError:
                        pass
        except OSError:
            pass
    return {"exists": True, "n": n, "size": size,
            "newest": newest or None, "zero_byte": zero}


def health(fam, agg):
    """Verdict for a family: ok / stale / missing / empty, plus reasons."""
    reasons = []
    if not agg["exists_any"]:
        # a family flagged `optional: true` is data we INTENTIONALLY removed (e.g. the
        # ~81GB vendor flat files deleted to free disk, rebuildable on demand) — that is
        # "offline" (grey), not "missing" (red alarm). 2026-07-21.
        if fam.get("optional"):
            return "offline", ["intentionally offline — deleted to free disk; rebuildable (see gotchas)"]
        return "missing", ["no registered path exists on disk"]
    if agg["n"] == 0:
        return "empty", ["path(s) exist but contain no files"]
    verdict = "ok"
    if agg["newest"] is not None:
        age = (dt.datetime.now().timestamp() - agg["newest"]) / 86400.0
        if age > fam["expected_freshness_days"]:
            verdict = "stale"
            reasons.append(f"newest file {age:.0f}d old (budget {fam['expected_freshness_days']}d)")
    if agg["zero_byte"]:
        reasons.append(f"{agg['zero_byte']} zero-byte file(s)")
    return verdict, reasons


def maybe_rows(fam):
    """Row/schema counts ONLY for small flagged key datasets (count_rows: true)."""
    if not fam.get("count_rows"):
        return None
    out = {}
    for path in fam["paths"]:
        p = ROOT / path
        if p.is_dir():
            # sample the CSVs in a flagged small dir
            csvs = sorted(p.glob("*.csv"))
            files = csvs[:1]
        elif p.is_file():
            files = [p]
        else:
            files = []
        for f in files:
            try:
                if f.suffix == ".csv":
                    with open(f, encoding="utf-8", errors="replace") as fh:
                        header = fh.readline().rstrip("\n").split(",")
                        rows = sum(1 for _ in fh)
                    out[f.name] = {"rows": rows, "cols": len(header),
                                   "schema": header[:12]}
            except OSError:
                pass
    return out or None


def run_scan(verbose=True):
    fams = load_registry()
    manifest = {"generated": dt.datetime.now().isoformat(timespec="seconds"),
                "families": {}, "total_size": 0, "total_files": 0}
    t0 = dt.datetime.now()
    for fam in fams:
        per_path = {}
        agg = {"n": 0, "size": 0, "newest": None, "zero_byte": 0, "exists_any": False}
        for path in fam["paths"]:
            r = scan_path(path)
            per_path[path] = r
            if r["exists"]:
                agg["exists_any"] = True
            agg["n"] += r["n"]
            agg["size"] += r["size"]
            agg["zero_byte"] += r["zero_byte"]
            if r["newest"] and (agg["newest"] is None or r["newest"] > agg["newest"]):
                agg["newest"] = r["newest"]
        verdict, reasons = health(fam, agg)
        manifest["families"][fam["key"]] = {
            "n": agg["n"], "size": agg["size"], "zero_byte": agg["zero_byte"],
            "newest": agg["newest"], "exists_any": agg["exists_any"],
            "health": verdict, "reasons": reasons,
            "per_path": per_path, "rows": maybe_rows(fam)}
        manifest["total_size"] += agg["size"]
        manifest["total_files"] += agg["n"]
        if verbose:
            nm = ("—" if not agg["newest"]
                  else dt.datetime.fromtimestamp(agg["newest"]).strftime("%Y-%m-%d"))
            print(f"  {agg['size']/1e9:8.3f} GB  {agg['n']:6d}  {verdict:8s}  "
                  f"newest {nm}  {fam['key']}")
    manifest["scan_seconds"] = (dt.datetime.now() - t0).total_seconds()
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    if verbose:
        print(f"\n  TOTAL {manifest['total_size']/1e9:.1f} GB, "
              f"{manifest['total_files']} files, {manifest['scan_seconds']:.2f}s "
              f"-> {MANIFEST.relative_to(ROOT)}")
    return manifest


def run_scan_bg():
    with _scan_lock:
        if _scan_state["running"]:
            return
        _scan_state["running"] = True
    try:
        p = subprocess.run([str(PY), str(Path(__file__).resolve()), "scan"],
                           cwd=str(ROOT), capture_output=True, text=True, timeout=600)
        _scan_state["log"] = (p.stdout or "")[-4000:] + (p.stderr or "")[-1000:]
    except Exception as e:
        _scan_state["log"] = f"scan failed: {e}"
    finally:
        _scan_state["running"] = False
        _scan_state["at"] = dt.datetime.now().strftime("%H:%M:%S")


# ------------------------------------------------------------------ view model
def build_view():
    """Merge registry + cached manifest into the JSON the page renders."""
    fams = load_registry()
    manifest = {}
    if MANIFEST.exists():
        try:
            manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}
    mfam = manifest.get("families", {})
    total = manifest.get("total_size", 0) or 1
    cats = {}
    worst = {"health": "ok", "key": None, "reasons": []}
    rank = {"missing": 3, "empty": 2, "stale": 1, "ok": 0, "offline": 0}
    for f in fams:
        m = mfam.get(f["key"], {})
        size = m.get("size", 0)
        card = {
            "key": f["key"], "title": f.get("title", f["key"]),
            "category": f.get("category", "Misc"), "paths": f["paths"],
            "produced_by": f.get("produced_by", "TODO"),
            "update_cadence": f.get("update_cadence", "—"),
            "expected_freshness_days": f["expected_freshness_days"],
            "useful_for": f.get("useful_for", ""), "access": f.get("access", ""),
            "gotchas": f.get("gotchas", ""),
            "size": size, "n": m.get("n", 0),
            "pct": round(100 * size / total, 1),
            "newest": m.get("newest"), "health": m.get("health", "unknown"),
            "reasons": m.get("reasons", []), "rows": m.get("rows"),
            "per_path": m.get("per_path", {}),
        }
        cats.setdefault(f.get("category", "Misc"), []).append(card)
        if rank.get(card["health"], 0) > rank.get(worst["health"], 0):
            worst = {"health": card["health"], "key": card["key"],
                     "reasons": card["reasons"]}
    ordered = [{"name": c, "families": sorted(cats[c], key=lambda x: -x["size"])}
               for c in CATEGORY_ORDER if c in cats]
    for c in cats:
        if c not in CATEGORY_ORDER:
            ordered.append({"name": c, "families": cats[c]})
    return {
        "categories": ordered,
        "total_size": manifest.get("total_size", 0),
        "total_files": manifest.get("total_files", 0),
        "family_count": len(fams),
        "scan_generated": manifest.get("generated"),
        "scan_seconds": manifest.get("scan_seconds"),
        "worst": worst,
        "scan": {"running": _scan_state["running"], "at": _scan_state["at"]},
    }


# ----------------------------------------------------------------------- server
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype="application/json"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            return self._send(HTML, "text/html; charset=utf-8")
        if path == "/view.json":
            return self._send(json.dumps(build_view()))
        if path == "/scan_log":
            return self._send(json.dumps({"running": _scan_state["running"],
                                          "log": _scan_state["log"], "at": _scan_state["at"]}))
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path == "/rescan":
            threading.Thread(target=run_scan_bg, daemon=True).start()
            return self._send(json.dumps({"started": True}))
        self.send_response(404)
        self.end_headers()


# ------------------------------------------------------------------------- HTML
HTML = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📚</text></svg>"><title>Data Catalog</title>
<style>
:root{--surface:#fcfcfb;--plane:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
  --grid:#e1e0d9;--border:rgba(11,11,11,.10);--pos:#2a78d6;--card:#fff;
  --good:#0ca30c;--warn:#fab219;--bad:#e34948;--chip:#f0efea}
@media(prefers-color-scheme:dark){:root{--surface:#1a1a19;--plane:#0d0d0d;--ink:#fff;--ink2:#c3c2b7;
  --muted:#898781;--grid:#2c2c2a;--border:rgba(255,255,255,.10);--pos:#3987e5;--card:#1f1f1e;
  --good:#0ca30c;--warn:#fab219;--bad:#e66767;--chip:#26261f}}
:root[data-theme=dark]{--surface:#1a1a19;--plane:#0d0d0d;--ink:#fff;--ink2:#c3c2b7;--muted:#898781;
  --grid:#2c2c2a;--border:rgba(255,255,255,.10);--pos:#3987e5;--card:#1f1f1e;--chip:#26261f}
:root[data-theme=light]{--surface:#fcfcfb;--plane:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
  --grid:#e1e0d9;--border:rgba(11,11,11,.10);--pos:#2a78d6;--card:#fff;--chip:#f0efea}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--ink);font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:14px}
header{padding:13px 20px;border-bottom:1px solid var(--border);background:var(--surface);display:flex;gap:18px;align-items:baseline;flex-wrap:wrap;position:sticky;top:0;z-index:5}
h1{font-size:16px;margin:0;font-weight:650}
.wrap{max-width:1420px;margin:0 auto;padding:16px 20px 80px}
.kpis{display:flex;gap:26px;flex-wrap:wrap}
.kpi .l{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.03em}
.kpi .v{font-size:17px;font-weight:650;font-variant-numeric:tabular-nums}
button{font:inherit;color:var(--ink);background:var(--card);border:1px solid var(--border);border-radius:8px;padding:6px 12px;cursor:pointer}
button:hover{border-color:var(--muted)}
button.primary{background:var(--pos);color:#fff;border-color:var(--pos)}
.cat{margin:22px 0 8px;font-size:12px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:var(--ink2);border-bottom:1px solid var(--border);padding-bottom:5px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(400px,1fr));gap:12px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:13px 15px;display:flex;flex-direction:column;gap:7px}
.card .top{display:flex;align-items:baseline;gap:8px}
.card .title{font-weight:650;font-size:14px}
.card .key{font-size:11px;color:var(--muted);font-family:ui-monospace,monospace}
.dot{width:9px;height:9px;border-radius:50%;display:inline-block;flex:0 0 auto}
.metrics{display:flex;gap:16px;flex-wrap:wrap;font-variant-numeric:tabular-nums}
.metrics .m .l{font-size:10.5px;color:var(--muted);text-transform:uppercase}
.metrics .m .v{font-size:14px;font-weight:600}
.bar{height:5px;border-radius:3px;background:var(--grid);overflow:hidden}
.bar>i{display:block;height:100%;background:var(--pos)}
.row{font-size:12.5px;color:var(--ink2);line-height:1.45}
.row b{color:var(--ink);font-weight:600}
.chip{display:inline-block;background:var(--chip);border-radius:5px;padding:1px 7px;font-size:11px;font-family:ui-monospace,monospace;color:var(--ink2);margin:1px 2px 1px 0}
.reasons{font-size:12px;color:var(--warn)}
.reasons.bad{color:var(--bad)}
code{font-family:ui-monospace,monospace;font-size:11.5px;background:var(--chip);padding:1px 5px;border-radius:4px;word-break:break-all}
.draft{color:var(--warn)}
details summary{cursor:pointer;font-size:12px;color:var(--muted);user-select:none}
.spin{display:inline-block;width:13px;height:13px;border:2px solid var(--border);border-top-color:var(--pos);border-radius:50%;animation:s .7s linear infinite;vertical-align:-2px}
@keyframes s{to{transform:rotate(360deg)}}
.muted{color:var(--muted)}
.warnbanner{background:rgba(250,178,25,.12);border:1px solid var(--warn);border-radius:9px;padding:9px 13px;margin-bottom:14px;font-size:13px}
</style></head><body>
<header>
  <h1>⬡ Data Catalog</h1>
  <div class="kpis">
    <div class="kpi"><div class="l">Footprint</div><div class="v" id="k-size">…</div></div>
    <div class="kpi"><div class="l">Files</div><div class="v" id="k-files">…</div></div>
    <div class="kpi"><div class="l">Families</div><div class="v" id="k-fam">…</div></div>
    <div class="kpi"><div class="l">Worst health</div><div class="v" id="k-worst">…</div></div>
  </div>
  <span style="margin-left:auto"></span>
  <span class="muted" id="k-scan"></span>
  <button class="primary" id="btn-rescan">↻ Rescan</button>
  <span id="scan-status" class="muted"></span>
</header>
<div class="wrap">
  <div class="warnbanner" id="draftnote">Some cards show <span class="draft">DRAFT</span> useful-for / gotchas — confirm these with the user before trusting them.</div>
  <div id="cats"></div>
</div>
<script>
const HB={ok:'--good',stale:'--warn',empty:'--warn',missing:'--bad',offline:'--muted',unknown:'--muted'};
const css=k=>getComputedStyle(document.documentElement).getPropertyValue(k).trim();
const gb=b=>b>=1e9?(b/1e9).toFixed(b>=1e10?0:2)+' GB':b>=1e6?(b/1e6).toFixed(1)+' MB':b>=1e3?(b/1e3).toFixed(0)+' KB':b+' B';
const nfmt=n=>n.toLocaleString('en-US');
function ago(iso){if(!iso)return '—';const d=(Date.now()-new Date(iso*1000))/86400000;
  if(d<1)return 'today';if(d<2)return '1d ago';return Math.floor(d)+'d ago';}
function drafty(t){return (t||'').replace(/DRAFT/g,'<span class="draft">DRAFT</span>').replace(/⚠/g,'<span style="color:var(--bad)">⚠</span>');}

async function load(){
  const v=await(await fetch('/view.json')).json();
  document.getElementById('k-size').textContent=gb(v.total_size);
  document.getElementById('k-files').textContent=nfmt(v.total_files);
  document.getElementById('k-fam').textContent=v.family_count;
  const w=document.getElementById('k-worst');
  w.textContent=v.worst.key?`${v.worst.health} · ${v.worst.key}`:'ok';
  w.style.color=css('--'+(HB[v.worst.health]||'--muted').replace('--',''));
  document.getElementById('k-scan').textContent=v.scan_generated?
    `scanned ${v.scan_generated.replace('T',' ')} (${(v.scan_seconds||0).toFixed(2)}s)`:'never scanned — hit Rescan';
  let anyDraft=false, h='';
  for(const cat of v.categories){
    h+=`<div class="cat">${cat.name} · ${cat.families.length}</div><div class="grid">`;
    for(const f of cat.families){
      if(/DRAFT/.test(f.useful_for+f.gotchas))anyDraft=true;
      const col=css('--'+(HB[f.health]||'--muted').replace('--',''));
      const rc=f.reasons&&f.reasons.length?`<div class="reasons ${f.health==='missing'?'bad':''}">${f.reasons.join(' · ')}</div>`:'';
      const rows=f.rows?`<div class="row"><b>rows:</b> ${Object.entries(f.rows).map(([k,r])=>`${k} — ${nfmt(r.rows)}×${r.cols}`).join(' · ')}</div>`:'';
      h+=`<div class="card">
        <div class="top"><span class="dot" style="background:${col}"></span>
          <span class="title">${f.title}</span><span class="key">${f.key}</span></div>
        <div class="metrics">
          <div class="m"><div class="l">Size</div><div class="v">${gb(f.size)}</div></div>
          <div class="m"><div class="l">Files</div><div class="v">${nfmt(f.n)}</div></div>
          <div class="m"><div class="l">% disk</div><div class="v">${f.pct}%</div></div>
          <div class="m"><div class="l">Updated</div><div class="v">${ago(f.newest)}</div></div>
          <div class="m"><div class="l">Cadence</div><div class="v">${f.update_cadence}</div></div>
        </div>
        <div class="bar"><i style="width:${Math.min(100,f.pct)}%;background:${col}"></i></div>
        ${rc}${rows}
        <div class="row"><b>Useful for:</b> ${drafty(f.useful_for)||'<span class="muted">—</span>'}</div>
        <div class="row"><b>Gotchas:</b> ${drafty(f.gotchas)||'<span class="muted">—</span>'}</div>
        <div class="row"><b>Access:</b> <code>${(f.access||'—').replace(/</g,'&lt;')}</code></div>
        <div class="row muted"><b>Produced by:</b> ${f.produced_by} · <b>freshness budget</b> ${f.expected_freshness_days}d</div>
        <details><summary>paths (${f.paths.length})</summary>
          ${f.paths.map(p=>`<span class="chip">${p}</span>`).join('')}</details>
      </div>`;
    }
    h+='</div>';
  }
  document.getElementById('cats').innerHTML=h;
  document.getElementById('draftnote').style.display=anyDraft?'':'none';
}

const btn=document.getElementById('btn-rescan');
btn.onclick=async()=>{btn.disabled=true;
  document.getElementById('scan-status').innerHTML='<span class="spin"></span> scanning…';
  await fetch('/rescan',{method:'POST'});poll();};
async function poll(){const j=await(await fetch('/scan_log')).json();
  if(j.running){setTimeout(poll,1200);return;}
  document.getElementById('scan-status').textContent=j.at?('rescanned '+j.at):'done';
  btn.disabled=false;await load();}
load();
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser(description="Data Catalog — scan + serve")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan", help="scan registered paths -> manifest.json")
    sp = sub.add_parser("serve", help="serve the catalog page")
    sp.add_argument("--port", type=int, default=8620)
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--open", action="store_true")
    args = ap.parse_args()

    if args.cmd == "scan":
        print("Scanning registered data families…")
        run_scan()
        return

    if not MANIFEST.exists():
        print("No manifest yet — running an initial scan…")
        run_scan()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"Data Catalog at {url}  (Ctrl-C to stop)")
    if args.open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()

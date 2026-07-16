"""EOD desk report (S75) — a full checkmark of the day's autonomous chain, so the
options desk can be trusted without Claude open.

Runs ~15:20 CT (after 15:00 daemon stop + 15:15 postmortem). Reconstructs every
step of the daily chain from ground-truth artifacts (did the file get produced?
is the port up? did the daemon feed the postmortem?), pulls the day's P&L from the
SAME KPI computation the dashboard uses, and emits:

  data/options_sim/eod_report_<date>.html   — rich checklist + P&L (opens on the dashboard link)
  data/options_sim/eod_status_<date>.json   — machine-readable ledger (dashboard can surface it)
  desktop toast                             — one-line green/red summary
  HTML email                                — full report, IF scratchpad/email_cfg.json exists

Never raises — a report that crashes helps no one.

Run:  .venv/Scripts/python.exe scripts/eod_report.py
"""
import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
LOG = ROOT / "data" / "options_log"
CT = ZoneInfo("America/Chicago")

OK, WARN, INFO = "ok", "warn", "info"


def _today():
    return dt.datetime.now(CT)


def _fresh_today(path, use_ct=True):
    """True if `path` was modified today (CT)."""
    if not path.exists():
        return False
    tz = CT if use_ct else None
    mtime = dt.datetime.fromtimestamp(path.stat().st_mtime, tz)
    return mtime.date() == _today().date()


def build_steps(date):
    """Each step: (label, status, detail). status in {ok, warn, info}."""
    steps = []

    # 1-5: reuse the health-check probes so the report agrees with the 08:40 check
    try:
        import options_healthcheck as hc
        for label, fn in [("Gateway login (API 4002)", hc.check_gateway),
                          ("Live feed", hc.check_feed),
                          ("MenthorQ levels", hc.check_levels),
                          ("Game plan", hc.check_gameplan)]:
            try:
                good, detail = fn()
            except Exception as e:
                good, detail = False, f"probe errored: {type(e).__name__}"
            steps.append((label, OK if good else WARN, detail))
    except Exception as e:
        steps.append(("Health probes", WARN, f"could not import healthcheck: {e}"))

    # 6: gamma scanner ran (cross-symbol screen)
    scan = SIM / f"scanner_{date}.json"
    steps.append(("Gamma scanner", OK if scan.exists() else WARN,
                  f"scanner_{date}.json written" if scan.exists() else "no scanner output today"))

    # 7: trigger daemon ran the session -> evidenced by the postmortem it feeds
    pm = SIM / f"postmortem_{date}.json"
    fired = []
    if pm.exists():
        try:
            pmd = json.loads(pm.read_text(encoding="utf-8"))
            trigs = pmd.get("triggers", [])
            fired = [t for t in trigs if t.get("fired")]
            steps.append(("Trigger daemon (→15:00 CT)", OK,
                          f"{len(trigs)} armed · {len(fired)} fired"))
        except Exception:
            steps.append(("Trigger daemon (→15:00 CT)", WARN, "postmortem unreadable"))
    else:
        steps.append(("Trigger daemon (→15:00 CT)", WARN, "no postmortem yet (runs 15:15 CT)"))

    # 8: trade log touched today (marks / sim writes)
    tp = LOG / "trades.parquet"
    steps.append(("Trade log / marks", OK if _fresh_today(tp) else INFO,
                  "trades.parquet updated today" if _fresh_today(tp) else "no trade-log write today"))

    # 9: postmortem generated
    steps.append(("Postmortem", OK if pm.exists() else WARN,
                  f"postmortem_{date}.json" if pm.exists() else "not generated"))

    return steps, fired


def kpis():
    """Reuse the dashboard's own KPI tiles so the numbers match exactly."""
    try:
        import options_dashboard as dash
        s = dash.load_stats()
        return [(label, value, cls) for _k, label, value, cls in dash.tile_specs(s)]
    except Exception as e:
        return [("KPIs unavailable", str(e), "muted")]


def render_html(date, steps, fired, tiles):
    now = _today().strftime("%Y-%m-%d %H:%M CT")
    n_ok = sum(1 for _l, st, _d in steps if st == OK)
    n_bad = sum(1 for _l, st, _d in steps if st == WARN)
    icon = {OK: "✓", WARN: "✗", INFO: "•"}
    color = {OK: "#2fbf8f", WARN: "#e5484d", INFO: "#8a91a0"}
    banner_ok = n_bad == 0
    rows = "".join(
        f'<tr><td style="color:{color[st]};font-weight:800;width:26px">{icon[st]}</td>'
        f'<td style="font-weight:600">{lbl}</td>'
        f'<td style="color:#8a91a0">{det}</td></tr>'
        for lbl, st, det in steps)
    tile_html = "".join(
        f'<div style="background:#161a22;border:1px solid #23262d;border-radius:11px;padding:11px 14px">'
        f'<div style="color:#8a91a0;font-size:10.5px;text-transform:uppercase;letter-spacing:.04em">{lbl}</div>'
        f'<div style="font-size:19px;font-weight:750;margin-top:4px;'
        f'color:{"#2fbf8f" if cls=="pos" else "#e5484d" if cls=="neg" else "#e8ebf0"}">{val}</div></div>'
        for lbl, val, cls in tiles)
    fired_html = ""
    if fired:
        fired_html = '<h2>Fired triggers</h2><table style="width:100%;border-collapse:collapse">' + "".join(
            f'<tr><td style="padding:5px 0;border-bottom:1px solid #23262d">{t.get("name","?")}</td>'
            f'<td style="padding:5px 0;border-bottom:1px solid #23262d;color:#8a91a0">'
            f'grade {t.get("projected_grade","?")} · {t.get("status","?")}</td></tr>'
            for t in fired) + '</table>'
    else:
        fired_html = '<p style="color:#8a91a0">No triggers fired today.</p>'

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>EOD Desk Report — {date}</title></head>
<body style="margin:0;background:#0b0d12;color:#e8ebf0;font:15px/1.55 system-ui,Segoe UI,sans-serif;padding:28px">
<div style="max-width:760px;margin:0 auto">
  <div style="display:flex;align-items:center;gap:12px">
    <span style="display:inline-flex;align-items:center;gap:8px;padding:6px 14px;border-radius:999px;
      font-weight:800;letter-spacing:.06em;font-size:12px;
      background:{'rgba(47,191,143,.12)' if banner_ok else 'rgba(229,72,77,.12)'};
      color:{'#2fbf8f' if banner_ok else '#e5484d'};
      border:1px solid {'rgba(47,191,143,.45)' if banner_ok else 'rgba(229,72,77,.45)'}">
      {'✓ DESK RAN CLEAN' if banner_ok else '✗ ATTENTION NEEDED'}</span>
    <h1 style="font-size:20px;margin:0">Options Desk — EOD Report</h1>
  </div>
  <div style="color:#8a91a0;font-size:12.5px;margin:6px 0 20px">{now} · {n_ok}/{len(steps)} steps green
    {('· ' + str(n_bad) + ' need attention') if n_bad else ''}</div>

  <h2 style="font-size:15px;color:#8ab4f8;border-bottom:1px solid #23262d;padding-bottom:6px">Daily chain</h2>
  <table style="width:100%;border-collapse:collapse;font-size:14px">{rows}</table>

  <h2 style="font-size:15px;color:#8ab4f8;border-bottom:1px solid #23262d;padding-bottom:6px;margin-top:26px">P&amp;L snapshot</h2>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:9px;margin:12px 0">{tile_html}</div>

  <h2 style="font-size:15px;color:#8ab4f8;border-bottom:1px solid #23262d;padding-bottom:6px;margin-top:26px">Fired triggers</h2>
  {fired_html}

  <p style="color:#5f6672;font-size:11.5px;margin-top:28px">Generated by scripts/eod_report.py ·
     data-collection mode (unvalidated) · times in Exchange/Central</p>
</div></body></html>"""


def main():
    date = _today().strftime("%Y%m%d")
    steps, fired = build_steps(date)
    tiles = kpis()
    html = render_html(date, steps, fired, tiles)

    out = SIM / f"eod_report_{date}.html"
    out.write_text(html, encoding="utf-8")

    n_ok = sum(1 for _l, st, _d in steps if st == OK)
    n_bad = sum(1 for _l, st, _d in steps if st == WARN)
    ledger = {"date": date, "generated_ct": _today().isoformat(),
              "steps": [{"label": l, "status": s, "detail": d} for l, s, d in steps],
              "n_ok": n_ok, "n_bad": n_bad, "fired": len(fired)}
    (SIM / f"eod_status_{date}.json").write_text(json.dumps(ledger, indent=2), encoding="utf-8")

    # one-line console + toast + optional HTML email
    for lbl, st, det in steps:
        print(f"  {'OK ' if st == OK else 'XX ' if st == WARN else '.. '} {lbl:28} {det}")
    summary = f"{n_ok}/{len(steps)} steps green · {len(fired)} fired" + (
        f" · {n_bad} NEED ATTENTION" if n_bad else "")
    title = ("✓ Options desk ran clean" if n_bad == 0 else "⚠ Options desk — attention needed")
    print(f"\n{title}: {summary}\n-> {out}")
    try:
        from notify import desktop, email_html, _log
        _log(title, summary)
        desktop(title, summary)
        sent = email_html(f"EOD Report {date} — {summary}", html,
                          text_fallback=f"{title}: {summary}")
        print("email:", "sent" if sent else "skipped (no scratchpad/email_cfg.json yet)")
    except Exception as e:
        print(f"notify failed (non-fatal): {e}")
    return 1 if n_bad else 0


if __name__ == "__main__":
    sys.exit(main())

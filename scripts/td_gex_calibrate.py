"""Calibrate a TD-computed per-strike GEX profile against gexlog's OWN saved
profile (the reverse-engineering step before trusting TD walls for July).

Standard tier has NO greeks and NO bulk (verified 2026-09-08), so we compute
gamma ourselves via Black-Scholes:
  * OI            -> /v3/option/history/open_interest   (per strike/right)
  * option price  -> /v3/option/history/eod (prior close) -> solve IV via BSM
  * spot          -> gexlog's own gex_spot_ref for the day (prior SPX close)
  * gamma         -> BSM gamma(spot, K, T, r, iv)

Per-strike raw GEX:  call_raw = OI_call * gamma_call ;  put_raw = -OI_put * gamma_put
We then REGRESS gexlog's published call_gex / put_gex / net_gex against our raw
values THROUGH THE ORIGIN. A high R^2 means our gamma SHAPE matches theirs (so
the walls will match); the slope is just their multiplier convention
(contract_mult * spot^2 * 0.01 etc) which is irrelevant to wall LOCATION.

Hypotheses tested per day are driven by CLI:
  --oi-date prior|report   which OI daily record to use
  --expiry 0dte            (only 0dte implemented; all-expiry is the fallback if
                            0dte R^2 is poor -- see NEXT in handoff)

Outputs a DATED CSV per day + a summary line (slope, R^2, wall deltas).
Usage:
  python scripts/td_gex_calibrate.py 2026-09-03 --oi-date prior
  python scripts/td_gex_calibrate.py 2026-09-03 2026-07-31 ... --oi-date both
"""
import argparse
import csv
import json
import math
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/gexlog/raw"
OUT = ROOT / "data/options_sim"
BASE = "http://127.0.0.1:25503/v3"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import market_calendar as MC  # rules-derived US market calendar (holidays + early closes)
R_FREE = 0.043  # ~2y from the reports' treasury block; gamma is ~insensitive to r


# ---------------------------------------------------------------- TD http
def td_get(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=20) as r:
            body = r.read().decode("utf-8", "replace")
    except Exception as e:
        return None
    if not body or body.lstrip().startswith("<"):
        return None
    lines = [ln for ln in body.splitlines() if ln.strip()]
    if len(lines) < 2:
        return None
    hdr = [h.strip().strip('"') for h in lines[0].split(",")]
    rows = []
    for ln in lines[1:]:
        vals = [v.strip().strip('"') for v in ln.split(",")]
        rows.append(dict(zip(hdr, vals)))
    return rows


def oi_for(expiry, strike, right, rec_date):
    """OI daily record on rec_date for the given contract."""
    p = (f"/option/history/open_interest?symbol=SPXW&expiration={expiry}"
         f"&strike={strike:.3f}&right={right}&start_date={rec_date}&end_date={rec_date}")
    rows = td_get(p)
    if not rows:
        return None
    try:
        return float(rows[-1]["open_interest"])
    except (KeyError, ValueError):
        return None


def index_close(symbol, day):
    """SPX cash close for `day` (the spot the EOD option prices correspond to)."""
    rows = td_get(f"/index/history/eod?symbol={symbol}&start_date={day}&end_date={day}")
    if not rows:
        return None
    try:
        return float(rows[-1]["close"])
    except (KeyError, ValueError):
        return None


def eod_mid(expiry, strike, right, day):
    p = (f"/option/history/eod?symbol=SPXW&expiration={expiry}"
         f"&strike={strike:.3f}&right={right}&start_date={day}&end_date={day}")
    rows = td_get(p)
    if not rows:
        return None
    r = rows[-1]
    try:
        bid, ask, close = float(r["bid"]), float(r["ask"]), float(r["close"])
    except (KeyError, ValueError):
        return None
    if bid > 0 and ask > 0 and ask >= bid:
        return (bid + ask) / 2
    return close if close > 0 else None


# ---------------------------------------------------------------- BSM
def bsm_price(S, K, T, r, sigma, right):
    if T <= 0 or sigma <= 0:
        return max(0.0, (S - K) if right == "call" else (K - S))
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if right == "call":
        return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def bsm_gamma(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    return norm.pdf(d1) / (S * sigma * math.sqrt(T))


def implied_vol(price, S, K, T, r, right):
    if price is None or price <= 0 or T <= 0:
        return None
    intrinsic = max(0.0, (S - K) if right == "call" else (K - S))
    if price <= intrinsic + 1e-6:
        return None
    try:
        return brentq(lambda s: bsm_price(S, K, T, r, s, right) - price, 1e-3, 5.0, maxiter=100)
    except (ValueError, RuntimeError):
        return None


# ---------------------------------------------------------------- calendar
def prior_trading_day(dstr):
    """Prior US-market trading session, holidays + weekends excluded (market_calendar)."""
    d = datetime.strptime(dstr, "%Y-%m-%d").date()
    return MC.prev_trading_day(d).strftime("%Y-%m-%d")


def year_frac_to_expiry(report_date, expiry_date):
    # report generated ~06:20 ET; 0DTE SPXW settles 16:00 ET same day.
    # crude but consistent: hours from ~09:30 ET open to 16:00 ET / (252*6.5h)
    d0 = datetime.strptime(report_date, "%Y-%m-%d")
    d1 = datetime.strptime(expiry_date, "%Y-%m-%d")
    days = (d1 - d0).days
    if days <= 0:
        return 6.5 / (252 * 6.5)  # ~1 trading day of intraday decay for 0DTE morning
    return days / 252.0


# ---------------------------------------------------------------- per-day
def load_profile(date):
    f = RAW / f"{date}_morning.json"
    if not f.exists():
        return None
    d = json.loads(f.read_text(encoding="utf-8"))
    gm = d.get("forecast", {}).get("factors", {}).get("gamma", {})
    prof = gm.get("gex_profile")
    if not prof:
        return None
    spot = gm.get("gex_spot_ref") or d.get("levels", {}).get("current")
    return dict(profile=sorted(prof, key=lambda p: p["strike"]),
                spot=float(spot),
                putWall=d["levels"].get("putWall"), callWall=d["levels"].get("callWall"),
                net_gex=gm.get("net_gex"))


def wall_from(rows, spot, key):
    below = [r for r in rows if r["strike"] < spot and r[key] is not None]
    above = [r for r in rows if r["strike"] > spot and r[key] is not None]
    pw = min(below, key=lambda r: r[key])["strike"] if below else None
    cw = max(above, key=lambda r: r[key])["strike"] if above else None
    return pw, cw


def regress_origin(x, y):
    x = np.array(x, float)
    y = np.array(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    if len(x) < 3 or (x == 0).all():
        return None, None, len(x)
    slope = float((x * y).sum() / (x * x).sum())
    ss_res = float(((y - slope * x) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else None
    return slope, r2, len(x)


def calibrate_day(date, oi_date_mode, vol_mode, gamma_spot_mode="ref"):
    prof = load_profile(date)
    if not prof:
        return None
    spot = prof["spot"]
    expiry = date.replace("-", "")  # 0DTE
    prior = prior_trading_day(date)
    oi_rec = prior if oi_date_mode == "prior" else date
    oi_rec = oi_rec.replace("-", "")
    T = year_frac_to_expiry(date, date)  # 0DTE
    # IV is solved at the CASH-CLOSE spot the option prices belong to (not
    # gexlog's premarket ES ref); gamma is then evaluated at gexlog's spot.
    iv_spot = index_close("SPX", prior.replace("-", "")) or spot
    # gamma centering: gexlog's gex_spot_ref (ES premarket) vs the cash close
    gamma_spot = iv_spot if gamma_spot_mode == "cash" else spot

    strikes = [float(p["strike"]) for p in prof["profile"]]
    gl = {float(p["strike"]): p for p in prof["profile"]}

    def work(K):
        row = {"strike": K}
        # pull OI + price for both rights
        oi_c = oi_for(expiry, K, "call", oi_rec)
        oi_p = oi_for(expiry, K, "put", oi_rec)
        px_c = eod_mid(expiry, K, "call", prior)
        px_p = eod_mid(expiry, K, "put", prior)
        iv_c = implied_vol(px_c, iv_spot, K, T, R_FREE, "call")
        iv_p = implied_vol(px_p, iv_spot, K, T, R_FREE, "put")
        # per-strike IV from the OTM side (clean extrinsic), relative to the
        # cash-close spot the prices belong to: call above iv_spot, put below.
        iv_skew = (iv_c if K >= iv_spot else iv_p) or iv_p or iv_c
        row.update(oi_c=oi_c, oi_p=oi_p, iv_c=iv_c, iv_p=iv_p, iv_skew=iv_skew)
        return row

    with ThreadPoolExecutor(max_workers=4) as ex:
        rows = list(ex.map(work, strikes))

    # ATM implied vol = median of solved OTM IVs within +-0.5% of spot (for flat mode)
    band = [r["iv_skew"] for r in rows
            if r["iv_skew"] and abs(r["strike"] - iv_spot) <= 0.005 * iv_spot]
    atm_iv = float(np.median(band)) if band else next(
        (r["iv_skew"] for r in sorted(rows, key=lambda r: abs(r["strike"] - iv_spot)) if r["iv_skew"]), None)

    # gamma pass: flat = one ATM vol for every strike; skew = per-strike OTM vol
    for r in rows:
        sigma = atm_iv if vol_mode == "flat" else r["iv_skew"]
        gm = bsm_gamma(gamma_spot, r["strike"], T, R_FREE, sigma) if sigma else None
        r["iv_used"] = sigma
        r["gamma_c"] = r["gamma_p"] = gm
        r["call_raw"] = (r["oi_c"] * gm) if (r["oi_c"] is not None and gm) else None
        r["put_raw"] = (-r["oi_p"] * gm) if (r["oi_p"] is not None and gm) else None
        cr, pr = r["call_raw"], r["put_raw"]
        r["net_raw"] = (cr or 0) + (pr or 0) if (cr is not None or pr is not None) else None

    # attach gexlog values
    for r in rows:
        g = gl[r["strike"]]
        r["gl_call"] = g.get("call_gex")
        r["gl_put"] = g.get("put_gex")
        r["gl_net"] = g.get("net_gex")

    # regressions
    stats = {}
    for tag, xk, yk in (("call", "call_raw", "gl_call"), ("put", "put_raw", "gl_put"),
                        ("net", "net_raw", "gl_net")):
        s, r2, n = regress_origin([r[xk] for r in rows], [r[yk] for r in rows])
        stats[tag] = dict(slope=s, r2=r2, n=n)

    # walls: split above/below at the CASH close (= gexlog_brief's `current`),
    # for both our profile and gexlog's own — apples to apples.
    split = iv_spot
    td_pw, td_cw = wall_from(rows, split, "net_raw")
    gl_pw, gl_cw = wall_from([{"strike": r["strike"], "net_raw": r["gl_net"]} for r in rows],
                             split, "net_raw")

    return dict(date=date, spot=spot, iv_spot=iv_spot, oi_rec=oi_rec, T=T, rows=rows, stats=stats,
                td_walls=(td_pw, td_cw), gl_corr_walls=(gl_pw, gl_cw),
                gl_pub_walls=(prof["putWall"], prof["callWall"]))


def all_profile_days():
    import glob as _glob
    out = []
    for f in sorted(_glob.glob(str(RAW / "*_morning.json"))):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        if d.get("forecast", {}).get("factors", {}).get("gamma", {}).get("gex_profile"):
            out.append(Path(f).name[:10])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dates", nargs="*")
    ap.add_argument("--oi-date", choices=["prior", "report"], default="prior")
    ap.add_argument("--vol", choices=["flat", "skew"], default="skew",
                    help="flat = one ATM IV for all strikes; skew = per-strike OTM IV")
    ap.add_argument("--gamma-spot", choices=["ref", "cash"], default="ref",
                    help="center gamma at gexlog's gex_spot_ref (ES) or the cash close")
    ap.add_argument("--all", action="store_true", help="every morning day with a gex_profile")
    a = ap.parse_args()

    dates = all_profile_days() if a.all else a.dates
    print(f"vol-mode={a.vol}  oi-date={a.oi_date}  gamma-spot={a.gamma_spot}  n_days={len(dates)}")
    summary = []
    for date in dates:
        res = calibrate_day(date, a.oi_date, a.vol, a.gamma_spot)
        if not res:
            print(f"{date}: no gexlog profile on disk -- skip")
            continue
        # save dated per-strike CSV
        out = OUT / f"td_gex_calib_{date}.csv"
        cols = ["strike", "oi_c", "oi_p", "iv_c", "iv_p", "gamma_c", "gamma_p",
                "call_raw", "put_raw", "net_raw", "gl_call", "gl_put", "gl_net"]
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(res["rows"])
        st = res["stats"]
        oi_ok = sum(1 for r in res["rows"] if r["oi_c"] is not None)
        iv_ok = sum(1 for r in res["rows"] if r["iv_c"] is not None)
        print(f"\n=== {date}  gamma_spot={res['spot']:.1f}  iv_spot={res['iv_spot']:.1f}  "
              f"gap={res['spot']-res['iv_spot']:+.1f}  OIrec={res['oi_rec']}  "
              f"T={res['T']:.4f}  (OI {oi_ok}/{len(res['rows'])}, IV {iv_ok}) ===")
        for tag in ("call", "put", "net"):
            s = st[tag]
            r2 = f"{s['r2']:.3f}" if s['r2'] is not None else "  -  "
            sl = f"{s['slope']:.3e}" if s['slope'] is not None else "  -  "
            print(f"  {tag:4s} R^2={r2}  slope={sl}  n={s['n']}")
        print(f"  walls  TD net -> put {res['td_walls'][0]} / call {res['td_walls'][1]}")
        print(f"         gexlog corr -> put {res['gl_corr_walls'][0]} / call {res['gl_corr_walls'][1]}")
        print(f"         gexlog pub  -> put {res['gl_pub_walls'][0]} / call {res['gl_pub_walls'][1]}")
        print(f"  -> {out}")
        summary.append(dict(date=date, r2=st["net"]["r2"],
                             td_pw=res["td_walls"][0], td_cw=res["td_walls"][1],
                             gl_pw=res["gl_corr_walls"][0], gl_cw=res["gl_corr_walls"][1],
                             pub_pw=res["gl_pub_walls"][0], pub_cw=res["gl_pub_walls"][1]))

    # aggregate
    def dpts(a, b):
        return abs(a - b) if (a is not None and b is not None) else None

    for s in summary:
        s["dpw_corr"] = dpts(s["td_pw"], s["gl_pw"])
        s["dcw_corr"] = dpts(s["td_cw"], s["gl_cw"])
        s["dpw_pub"] = dpts(s["td_pw"], s["pub_pw"])
        s["dcw_pub"] = dpts(s["td_cw"], s["pub_cw"])

    sc = OUT / "td_gex_calib_summary.csv"
    with open(sc, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        w.writeheader()
        w.writerows(summary)

    r2s = [s["r2"] for s in summary if s["r2"] is not None]
    def rate(key, tol):
        vals = [s[key] for s in summary if s[key] is not None]
        return (sum(1 for v in vals if v <= tol) / len(vals) * 100, len(vals)) if vals else (0, 0)
    def med(key):
        vals = sorted(s[key] for s in summary if s[key] is not None)
        return vals[len(vals) // 2] if vals else None

    print("\n================ SUMMARY (per day) ================")
    for s in summary:
        r2 = f"{s['r2']:.3f}" if s['r2'] is not None else "  -  "
        m = "MATCH" if (s["dpw_corr"] == 0 and s["dcw_corr"] == 0) else "diff"
        print(f"  {s['date']}  R^2={r2}  TD({s['td_pw']},{s['td_cw']}) "
              f"corr({s['gl_pw']},{s['gl_cw']}) pub({s['pub_pw']},{s['pub_cw']})  [{m}]")

    print("\n================ AGGREGATE ================")
    print(f"  days: {len(summary)}   net R^2: median {med('r2'):.3f}  "
          f">=0.90: {sum(1 for x in r2s if x>=0.9)}/{len(r2s)}  "
          f">=0.80: {sum(1 for x in r2s if x>=0.8)}/{len(r2s)}")
    for lbl, ck, pk in (("call wall", "dcw_corr", "dcw_pub"), ("put wall", "dpw_corr", "dpw_pub")):
        e0, n = rate(ck, 0); e5, _ = rate(ck, 5); e10, _ = rate(ck, 10)
        print(f"  {lbl} vs gexlog CORR: exact {e0:.0f}%  <=5pt {e5:.0f}%  <=10pt {e10:.0f}%  "
              f"median|d| {med(ck)}  (n={n})")
        p0, _ = rate(pk, 0); p5, _ = rate(pk, 5)
        print(f"  {lbl} vs gexlog PUB : exact {p0:.0f}%  <=5pt {p5:.0f}%  median|d| {med(pk)}")
    print(f"\n  summary CSV -> {sc}")


if __name__ == "__main__":
    main()

"""Diagnose IV-coverage on a calibration day: for every strike in gexlog's
profile, show the TD OI + prior-close EOD bid/ask/close for call & put, the
solved IV, and — when the solve fails — the IV the price WOULD require (to see
if we're hitting the solver ceiling vs missing data). Answers "do we have the
right data, and why does coverage drop."

Usage: python scripts/td_gex_diag.py 2026-07-24
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import td_gex_calibrate as C  # reuse td_get/oi_for/eod_mid/bsm/implied_vol

ROOT = Path(__file__).resolve().parents[1]


def eod_raw(expiry, K, right, day):
    p = (f"/option/history/eod?symbol=SPXW&expiration={expiry}"
         f"&strike={K:.3f}&right={right}&start_date={day}&end_date={day}")
    rows = C.td_get(p)
    if not rows:
        return None
    r = rows[-1]
    try:
        return dict(bid=float(r["bid"]), ask=float(r["ask"]), close=float(r["close"]),
                    vol=float(r.get("volume", 0)))
    except (KeyError, ValueError):
        return None


def main():
    date = sys.argv[1]
    prof = C.load_profile(date)
    spot = prof["spot"]
    expiry = date.replace("-", "")
    prior = C.prior_trading_day(date)
    T = C.year_frac_to_expiry(date, date)
    print(f"{date}  spot={spot}  expiry={expiry}  prior_close_day={prior}  T={T:.5f}")
    print(f"{'strike':>7} {'side':>4} {'OI':>6} {'bid':>7} {'ask':>7} {'close':>7} "
          f"{'vol':>5} {'IV':>6} note")
    n_ok = n_noprice = n_ceiling = n_intrinsic = 0
    for p in prof["profile"]:
        K = float(p["strike"])
        otm = "call" if K >= spot else "put"   # the side we rely on
        oi = C.oi_for(expiry, K, otm, prior.replace("-", ""))
        e = eod_raw(expiry, K, otm, prior)
        if not e:
            n_noprice += 1
            print(f"{K:>7.0f} {otm:>4} {str(oi):>6} {'—':>7} {'—':>7} {'—':>7} {'—':>5} {'—':>6} NO EOD ROW")
            continue
        mid = (e["bid"] + e["ask"]) / 2 if (e["bid"] > 0 and e["ask"] >= e["bid"]) else e["close"]
        intrinsic = max(0.0, (spot - K) if otm == "call" else (K - spot))
        iv = C.implied_vol(mid, spot, K, T, C.R_FREE, otm)
        note = ""
        if iv:
            n_ok += 1
        elif mid <= 0:
            note = "price<=0"; n_noprice += 1
        elif mid <= intrinsic + 1e-6:
            note = f"<=intrinsic({intrinsic:.1f})"; n_intrinsic += 1
        else:
            # would-be IV above the 5.0 ceiling?
            hi = C.bsm_price(spot, K, T, C.R_FREE, 5.0, otm)
            note = f"needs IV>500% (px {mid:.2f} > cap {hi:.2f})" if mid > hi else "solve-fail"
            n_ceiling += 1
        ivs = f"{iv*100:5.1f}%" if iv else "  —  "
        print(f"{K:>7.0f} {otm:>4} {str(oi):>6} {e['bid']:>7.2f} {e['ask']:>7.2f} "
              f"{e['close']:>7.2f} {e['vol']:>5.0f} {ivs:>6} {note}")
    tot = len(prof["profile"])
    print(f"\nOTM-side coverage: ok={n_ok}/{tot}  no-price={n_noprice}  "
          f"<=intrinsic={n_intrinsic}  ceiling/fail={n_ceiling}")


if __name__ == "__main__":
    main()

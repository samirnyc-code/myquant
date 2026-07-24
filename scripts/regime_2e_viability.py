"""Financial viability of the vol-stop books: expectancy, DD detail, account sizing,
ES vs MES economics. Reads volstops_20260724.csv (EOD-hold books).

  python scripts/regime_2e_viability.py
Output: data/regime/viability_20260724.csv + tables on stdout.
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
d = pd.read_csv(ROOT / "data" / "regime" / "volstops_20260724.csv")
YEARS = 5.06
ES_DAY_MARGIN = 1000      # typical broker intraday margin assumption, stated not verified
MES_DAY_MARGIN = 100
LEAD = ["adr.30", "abr3.0", "abr1.5", "fx4p"]


def pf(s):
    gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else float("inf")


rows = []
for sid in LEAD:
    x = d[(d["stop"] == sid) & (d.target == "eod")].sort_values("Date").reset_index(drop=True)
    eq = x.net.cumsum()
    dd = eq - eq.cummax()
    maxdd = float(dd.min())
    # longest underwater stretch in trades and calendar days
    uw = 0; mx = 0; start_i = None; mx_days = 0
    for i, v in enumerate(dd.values):
        if v < -1e-9:
            if start_i is None:
                start_i = i
            uw += 1; mx = max(mx, uw)
            d0 = pd.Timestamp(x.Date.iloc[start_i]); d1 = pd.Timestamp(x.Date.iloc[i])
            mx_days = max(mx_days, (d1 - d0).days)
        else:
            uw = 0; start_i = None
    exp_tr = x.net.mean()
    tpm = len(x) / (YEARS * 12)
    net_yr = x.net.sum() / YEARS
    acct_min = -maxdd + ES_DAY_MARGIN
    acct_cf = -maxdd * 1.5 + ES_DAY_MARGIN
    # MES per contract
    gross = (x.net + 5.0) / 10.0
    for comm in (5.0, 2.5):
        m = gross - comm
        meq = m.cumsum(); mdd = float((meq - meq.cummax()).min())
        rows.append((sid, f"MES@${comm:.2f}RT", round(m.mean(), 2), round(m.sum()),
                     round(m.sum() / YEARS), round(mdd), round(pf(m), 2),
                     round(-mdd + MES_DAY_MARGIN), "YES" if -mdd <= 4500 else "no"))
    rows.append((sid, "ES@$5RT", round(exp_tr, 1), round(x.net.sum()),
                 round(net_yr), round(maxdd), pf(x.net),
                 round(acct_cf), "n/a"))
    print(f"\n== {sid} (EOD) ==")
    print(f"  ES: exp {exp_tr:+.1f}$/tr · {tpm:.1f} tr/mo · {net_yr/12:+,.0f}$/mo · "
          f"{net_yr:+,.0f}$/yr · PF {pf(x.net)}")
    print(f"  DD: max closed {maxdd:+,.0f}$ · longest underwater {mx} trades / ~{mx_days} days")
    print(f"  account (1 ES): min {acct_min:,.0f}$ (DD+margin) · comfortable {acct_cf:,.0f}$ "
          f"(1.5xDD+margin) · return on comfortable {net_yr/acct_cf*100:.0f}%/yr")
    m5 = gross - 5.0
    meq5 = m5.cumsum(); mdd5 = float((meq5 - meq5.cummax()).min())
    m25 = gross - 2.5
    meq25 = m25.cumsum(); mdd25 = float((meq25 - meq25.cummax()).min())
    print(f"  1 MES @$5RT: {m5.mean():+.2f}$/tr · {m5.sum()/YEARS:+,.0f}$/yr · DD {mdd5:+,.0f}$ "
          f"· fits $4.5k prop: {'YES' if -mdd5 <= 4500 else 'no'}")
    print(f"  1 MES @$2.50RT: {m25.mean():+.2f}$/tr · {m25.sum()/YEARS:+,.0f}$/yr · DD {mdd25:+,.0f}$ "
          f"· fits: {'YES' if -mdd25 <= 4500 else 'no'}")
    n_prop = int(4500 // -mdd5) if mdd5 < 0 else 0
    print(f"  MES contracts fitting $4.5k trailing (@$5RT, closed-DD basis): {n_prop}")

out = pd.DataFrame(rows, columns=["book", "instrument", "exp$/tr", "net5yr", "net/yr",
                                  "maxDD", "PF", "acct_needed", "fits$4.5k"])
out.to_csv(ROOT / "data" / "regime" / "viability_20260724.csv", index=False)
print("\nsaved -> data/regime/viability_20260724.csv")
print("\nNOTE: DD here is CLOSED-TRADE. Intra-trade adverse adds up to ~1 stop distance "
      "(~15.8pt = 790$/ES, 79$/MES) to a trailing-style measure. Margins assumed "
      f"ES {ES_DAY_MARGIN}$/MES {MES_DAY_MARGIN}$ intraday - verify with broker.")

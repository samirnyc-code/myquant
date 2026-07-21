"""
Daily MenthorQ calibration logger.

Pulls live SPX OI/gamma from IB (both SPXW + SPX classes), computes our candidate
levels for BOTH the near-term aggregate AND 0DTE, logs them next to MenthorQ's
published levels, and archives the full per-strike profile for later rule-fitting.

Workflow each morning:
  1. edit scratchpad/mq_levels_today.json with today's MenthorQ $SPX levels
  2. python scratchpad/mq_logger.py
Outputs:
  data/menthorq/spx_calibration.csv                  (one row/day, IB vs MenthorQ)
  data/menthorq/spx_ib_profiles/YYYY-MM-DD.csv       (full per-strike profile)
"""
import os, csv, json, time, datetime
from collections import defaultdict
from ib_async import IB, Index, Option

HOST, PORT, CID = "127.0.0.1", int(os.environ.get("IB_PORT", 4002)), 25  # 4002 = PAPER (S73)
LO, HI = 0.92, 1.05
STEP = 25
N_WEEKLY, N_MONTHLY = 10, 6
BATCH = 50            # <= IB simultaneous market-data line cap (~100); stay well under
GREEK_WAIT = 20       # max seconds to wait for a batch's greeks to populate
GREEK_FRAC = 0.95     # accept batch once this fraction have modelGreeks
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MQ_FILE  = os.path.join(ROOT, "scratchpad", "mq_levels_today.json")
CALIB    = os.path.join(ROOT, "data", "menthorq", "spx_calibration.csv")
PROF_DIR = os.path.join(ROOT, "data", "menthorq", "spx_ib_profiles")

# ---------- pull ----------
def pull_profile():
    ib = IB(); ib.connect(HOST, PORT, clientId=CID, timeout=15); ib.reqMarketDataType(3)
    spx = Index("SPX", "CBOE", "USD"); ib.qualifyContracts(spx)
    t = ib.reqMktData(spx, "", snapshot=False); ib.sleep(3)
    spot = t.last if t.last == t.last else t.close
    params = ib.reqSecDefOptParams(spx.symbol, "", spx.secType, spx.conId)
    cf = lambda tc: next((c for c in params if c.tradingClass==tc and c.exchange=="SMART"), None)
    cw, cm = cf("SPXW"), cf("SPX")
    exps = [("SPXW", e) for e in sorted(cw.expirations)[:N_WEEKLY]] + \
           [("SPX",  e) for e in sorted(cm.expirations)[:N_MONTHLY]]
    dte0 = min(cw.expirations)                                    # 0DTE expiry
    grid = [k for k in sorted(set(cw.strikes)|set(cm.strikes))
            if LO*spot <= k <= HI*spot and k % STEP == 0]
    def harvest(batch, d):
        """request a batch, wait until greeks populate, accumulate, cancel."""
        tks = [(c, ib.reqMktData(c, "100,101,104,106", snapshot=False)) for c in batch]
        waited, frac = 0.0, 0.0
        while waited < GREEK_WAIT:
            ib.sleep(2.0); waited += 2.0
            have = sum(1 for _, tk in tks if tk.modelGreeks is not None)
            frac = have / max(1, len(tks))
            if frac >= GREEK_FRAC: break
        miss = 0
        for c, tk in tks:
            g = getattr(tk.modelGreeks, "gamma", None) if tk.modelGreeks else None
            if g is None or g != g: g = 0.; miss += 1
            oi = tk.callOpenInterest if c.right == "C" else tk.putOpenInterest
            oi = oi if oi == oi else 0.
            a = d[c.strike]
            if c.right == "C": a[0] += oi; a[1] += g*oi
            else:              a[2] += oi; a[3] += g*oi
        for c, _ in tks: ib.cancelMktData(c)
        return frac, miss

    byexp = {}
    for tc, exp in exps:
        cons = [Option("SPX", exp, k, r, "SMART", tradingClass=tc)
                for k in grid for r in ("C","P")]
        q = [c for c in ib.qualifyContracts(*cons) if c and getattr(c,"conId",None)]
        d = byexp.setdefault(exp, defaultdict(lambda:[0.,0.,0.,0.]))
        fracs = []
        for i in range(0, len(q), BATCH):
            f, m = harvest(q[i:i+BATCH], d)
            fracs.append(f)
        print(f"  pulled {tc} {exp}  ({len(q)} opt, greeks {min(fracs):.0%}-{max(fracs):.0%})")
    ib.disconnect()
    return spot, dte0, byexp

# ---------- levels from an aggregated {strike:[cOI,cGn,pOI,pGn]} ----------
def levels(agg, spot):
    rows = []
    for k in sorted(agg):
        coi,cgn,poi,pgn = agg[k]
        rows.append(dict(k=k, coi=coi, poi=poi,
                         cgex= cgn*100*spot*spot*1e-9,
                         pgex=-pgn*100*spot*spot*1e-9,
                         tgam=abs(cgn)+abs(pgn)))
    above = [r for r in rows if r["k"]>spot]
    below = [r for r in rows if r["k"]<spot]
    CR   = max(above, key=lambda r:r["cgex"])["k"] if above else None      # gamma call wall
    PSg  = min(below, key=lambda r:r["pgex"])["k"] if below else None      # most-neg put gex
    PSoi = max(below, key=lambda r:r["poi"])["k"]  if below else None      # raw put OI wall
    GW   = max(rows,  key=lambda r:r["tgam"])["k"]                          # gamma wall (max tot gamma)
    # HVL = dominant gamma flip: strike where cumulative net-GEX is nearest zero.
    # Deterministic, single-valued, side UNconstrained (can be above or below spot).
    cum = 0.0
    for r in rows:
        cum += r["cgex"] + r["pgex"]; r["cum"] = cum
    HVL = min(rows, key=lambda r: abs(r["cum"]))["k"]
    return dict(CR=CR, PS_gamma=PSg, PS_oi=PSoi, HVL=HVL, GW=GW), rows

# ---------- run ----------
mq = json.load(open(MQ_FILE))
today = datetime.date.today().isoformat()
print(f"MenthorQ levels for {today}: CR={mq.get('cr')} PS={mq.get('ps')} HVL={mq.get('hvl')}")

spot, dte0, byexp = pull_profile()

# aggregate all expiries (standard) and 0DTE only
agg = defaultdict(lambda:[0.,0.,0.,0.])
for exp, d in byexp.items():
    for k,v in d.items():
        a=agg[k]; a[0]+=v[0]; a[1]+=v[1]; a[2]+=v[2]; a[3]+=v[3]
std, rows = levels(agg, spot)
zero = defaultdict(lambda:[0.,0.,0.,0.]); zero.update(byexp.get(dte0, {}))
d0, _ = levels(zero, spot)

print("\n============ IB vs MenthorQ ============")
print(f"                MenthorQ    IB(std)   IB(0DTE)")
print(f"  Call Resist :   {mq.get('cr')}       {std['CR']}      {d0['CR']}")
print(f"  Put Support :   {mq.get('ps')}       {std['PS_gamma']}(g)/{std['PS_oi']}(oi)   {d0['PS_gamma']}(g)/{d0['PS_oi']}(oi)")
print(f"  HVL         :   {mq.get('hvl')}       {std['HVL']}      {d0['HVL']}")
print(f"  GammaWall0  :   {mq.get('gw0')}                 {d0['GW']}")

# archive full profile
os.makedirs(PROF_DIR, exist_ok=True)
pf = os.path.join(PROF_DIR, f"{today}.csv")
with open(pf,"w",newline="") as f:
    w=csv.writer(f); w.writerow(["strike","call_oi","put_oi","call_gex","put_gex","tot_gamma"])
    for r in rows: w.writerow([r["k"],int(r["coi"]),int(r["poi"]),
                               round(r["cgex"],3),round(r["pgex"],3),round(r["tgam"],6)])

# append calibration row
cols = ["date","spot","dte0",
        "mq_cr","mq_ps","mq_hvl","mq_cr0","mq_ps0","mq_hvl0","mq_gw0",
        "ib_cr","ib_ps_gamma","ib_ps_oi","ib_hvl","ib_gw",
        "ib_cr0","ib_ps0_gamma","ib_ps0_oi","ib_hvl0","ib_gw0"]
row = dict(date=today, spot=round(spot,2), dte0=dte0,
           mq_cr=mq.get("cr"), mq_ps=mq.get("ps"), mq_hvl=mq.get("hvl"),
           mq_cr0=mq.get("cr0"), mq_ps0=mq.get("ps0"), mq_hvl0=mq.get("hvl0"), mq_gw0=mq.get("gw0"),
           ib_cr=std["CR"], ib_ps_gamma=std["PS_gamma"], ib_ps_oi=std["PS_oi"],
           ib_hvl=std["HVL"], ib_gw=std["GW"],
           ib_cr0=d0["CR"], ib_ps0_gamma=d0["PS_gamma"], ib_ps0_oi=d0["PS_oi"],
           ib_hvl0=d0["HVL"], ib_gw0=d0["GW"])
# replace any existing row for today, else append (idempotent per day)
existing = []
if os.path.exists(CALIB):
    with open(CALIB, newline="") as f:
        existing = [r for r in csv.DictReader(f) if r.get("date") != today]
with open(CALIB,"w",newline="") as f:
    w=csv.DictWriter(f, fieldnames=cols); w.writeheader()
    for r in existing: w.writerow(r)
    w.writerow(row)
print(f"\nlogged -> {CALIB}  ({len(existing)+1} rows)\nprofile -> {pf}")

"""verify_roll.py — exhaustive check of the ES 09-26 -> 12-26 roll (S116-B).
Every check prints PASS/FAIL. Non-zero exit if ANY fails.
"""
import sys, time, glob, datetime as dt
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import contracts
from contracts import load_rolls, get_active_contract, get_contract_windows
RTH = ROOT / "data" / "ticks_continuous"
ETH = ROOT / "data" / "ticks_continuous_eth"
r = load_rolls()
fails = []
def chk(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{(' — '+detail) if detail else ''}")
    if not cond: fails.append(name)

print("A. OFFSET direction/magnitude")
z = next(w for w in get_contract_windows([c.ticker for c in contracts.CATALOG], r) if w["ticker"]=="ESZ6")
chk("ESZ6 cum_offset == -67.75", z["cum_offset"]==-67.75, f"got {z['cum_offset']}")

print("B. EXISTING contracts' offsets UNCHANGED (trove stays valid)")
expected = {"ESU6":0.0,"ESZ5":170.75,"ESH6":111.0,"ESM6":61.25,"ESU5":227.5}
for tk,exp in expected.items():
    w = next(w for w in get_contract_windows([c.ticker for c in contracts.CATALOG], r) if w["ticker"]==tk)
    chk(f"{tk} == {exp}", w["cum_offset"]==exp, f"got {w['cum_offset']}")

print("C. ROLL boundary")
chk("09-11 -> ESU6", get_active_contract(dt.date(2026,9,11),r)["ticker"]=="ESU6")
chk("09-14 -> ESZ6", get_active_contract(dt.date(2026,9,14),r)["ticker"]=="ESZ6")
chk("09-15 -> ESZ6", get_active_contract(dt.date(2026,9,15),r)["ticker"]=="ESZ6")

print("D. CONTINUITY: offset correct + gap is real")
new = pd.read_parquet(RTH/"2026-09-14.parquet")
old = pd.read_parquet(ROOT/"data/ticks_continuous_rth_bak/2026-09-14.parquet")  # from 09-26, offset 0
d_open = abs(new["Price"].iloc[0]-old["Price"].iloc[0])
chk("09-14 open matches un-offset 09-26 (<=2pt) => offset right, gap real",
    d_open<=2.0, f"12-26adj {new['Price'].iloc[0]:.2f} vs 09-26raw {old['Price'].iloc[0]:.2f} d={d_open:.2f}")
p11 = pd.read_parquet(RTH/"2026-09-11.parquet")
gap = new["Price"].iloc[0]-p11["Price"].iloc[-1]
chk("seam gap same in offset & un-offset data (real market move)",
    abs((old['Price'].iloc[0]-p11['Price'].iloc[-1]) - gap) <= 2.0, f"gap {gap:.2f}")

print("E. 09-14 front-month volume (12-26 > 09-26)")
chk("09-14 vol == 694,640 (from 12-26)", int(new["Volume"].sum())==694640, f"{int(new['Volume'].sum()):,}")
chk("12-26 vol > old 09-26 vol", new["Volume"].sum()>old["Volume"].sum(),
    f"{int(new['Volume'].sum()):,} vs {int(old['Volume'].sum()):,}")

print("F. EXISTING trove files UNTOUCHED (no file < 09-14 modified in last 2h)")
cutoff = time.time()-7200
touched = [Path(f).name for f in glob.glob(str(RTH/"*.parquet"))
           if Path(f).stem < "2026-09-14" and Path(f).stat().st_mtime > cutoff]
chk("no pre-roll RTH file modified", not touched, f"touched: {touched[:5]}")
touchedE = [Path(f).name for f in glob.glob(str(ETH/"*.parquet"))
            if not Path(f).stem.startswith("_") and Path(f).stem < "2026-09-14" and Path(f).stat().st_mtime > cutoff]
chk("no pre-roll ETH file modified", not touchedE, f"touched: {touchedE[:5]}")

print("G. No partial/junk days")
chk("no RTH 2026-09-15 (session in progress)", not (RTH/"2026-09-15.parquet").exists())
chk("no ETH 2026-09-15", not (ETH/"2026-09-15.parquet").exists())

print("H. RTH & ETH agree on 09-14")
eth14 = pd.read_parquet(ETH/"2026-09-14.parquet"); eth14["DateTime"]=pd.to_datetime(eth14["DateTime"])
t=eth14["DateTime"].dt.time
slc=eth14[(t>=dt.time(8,30))&(t<dt.time(15,15))]
chk("ETH RTH-slice vol == RTH trove vol", int(slc["Volume"].sum())==int(new["Volume"].sum()),
    f"eth {int(slc['Volume'].sum()):,} vs rth {int(new['Volume'].sum()):,}")

print("I. canonical accessor + health")
import tickdata
chk("tickdata.load_rth('2026-09-14') works", len(tickdata.load_rth("2026-09-14"))>0)
import pipeline_health as ph
chk("front_month() == 12-26", ph.front_month()=="12-26", f"got {ph.front_month()}")

print("\n" + ("*** ROLL VERIFICATION FAILED: "+", ".join(fails)+" ***" if fails
             else "ALL CHECKS PASS — roll is correct."))
sys.exit(1 if fails else 0)

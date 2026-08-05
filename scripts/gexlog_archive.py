"""Pull the full gexlog.com report archive (morning+evening) via the archive API.

Endpoint discovered 2026-08-04: api/archive.php?action=report&type={morning|evening}&date=YYYY-MM-DD
History spans 2026-04-06 .. present, ~2 reports/day. No history route exists for
per-strike gex_profile beyond what each report embeds. Saves raw JSON per
report + a flattened per-day CSV for backtesting.
"""
import json, csv, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT/"data/gexlog/raw"; RAW.mkdir(parents=True, exist_ok=True)
OUT = ROOT/"data/gexlog"

def g(d,*path,default=None):
    for k in path:
        if isinstance(d,dict): d=d.get(k)
        else: return default
    return d if d is not None else default

def flat_morning(d):
    lv=g(d,"levels",default={}); gm=g(d,"forecast","factors","gamma",default={})
    return dict(
        regime=gm.get("value"), net_gex=gm.get("net_gex"), gex_flip=gm.get("gex_flip"),
        gex_method=gm.get("gex_method"),
        putWall=lv.get("putWall"), callWall=lv.get("callWall"), current=lv.get("current"),
        r2=lv.get("r2"), r1=lv.get("r1"), s1=lv.get("s1"), s2=lv.get("s2"),
        expectedMove=lv.get("expectedMove"), emUpper=lv.get("emUpper"), emLower=lv.get("emLower"),
        signal=g(d,"guidance","signal"), risk_level=g(d,"risk","level"),
        forecast_type=g(d,"forecast","type"), confidence=g(d,"forecast","confidence"),
        es=g(d,"market","es","price"), vix=g(d,"market","vix","price"),
        regime_streak=g(d,"forecast","regime_streak","regime_count"),
        day_type_label=g(d,"forecast","regime_streak","day_type_label"),
    )

def flat_evening(d):
    sa=g(d,"session_analysis",default={}); lv=g(d,"levels",default={}); gm=g(d,"forecast","factors","gamma",default={})
    return dict(
        e_spx_change=sa.get("spx_change"), e_vix_change=sa.get("vix_change"),
        e_session_type=sa.get("session_type"), e_forecast_accurate=sa.get("forecast_accurate"),
        e_em_hit=sa.get("expected_move_hit"),
        e_net_gex=gm.get("net_gex"), e_putWall=lv.get("putWall"), e_callWall=lv.get("callWall"),
        e_current=lv.get("current"), e_regime=gm.get("value"),
    )

def main():
    with sync_playwright() as p:
        b=p.chromium.launch(); pg=b.new_page()
        dates=pg.request.get("https://gexlog.com/dashboard/api/archive.php?action=dates").json()
        m_dates=dates.get("morning",[]); e_dates=dates.get("evening",[])
        all_dates=sorted(set(m_dates)|set(e_dates))
        print(f"pulling {len(all_dates)} dates ({all_dates[0]}..{all_dates[-1]})")
        rows=[]
        for i,dt in enumerate(all_dates):
            row={"date":dt}
            for typ,flat in (("morning",flat_morning),("evening",flat_evening)):
                url=f"https://gexlog.com/dashboard/api/archive.php?action=report&type={typ}&date={dt}"
                try:
                    j=pg.request.get(url).json()
                    if isinstance(j,dict) and "error" not in j:
                        (RAW/f"{dt}_{typ}.json").write_text(json.dumps(j))
                        row.update(flat(j))
                except Exception as ex:
                    row[f"{typ}_err"]=str(ex)[:60]
            rows.append(row)
            if i%10==0: print(f"  {i}/{len(all_dates)} {dt}")
        b.close()
    cols=sorted({k for r in rows for k in r}, key=lambda c:(c!="date",c))
    with open(OUT/"gexlog_daily.csv","w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=cols); w.writeheader(); w.writerows(rows)
    print(f"\nSAVED {len(rows)} rows -> data/gexlog/gexlog_daily.csv  ({len(cols)} cols)")
    return rows

if __name__=="__main__":
    main()

import sys; sys.path.insert(0,'scripts')
import absorption_engine as ae, json
date="2026-01-02"
mf=ae._mbo_file(date); print("mbo file:",bool(mf))
tr=ae._trades_mbo(mf)
print("MBO ESH6 trades:",len(tr))
print("  price range:",round(tr.price.min(),2),"->",round(tr.price.max(),2))
print("  time range (CT):",tr.ts.min(),"->",tr.ts.max())
su=ae._load_setups(date)
for s in su["setups"]:
    print(f"  setup {s['setup']} {s['dir']} level={s['level']} window {s['t0'].strftime('%H:%M')}-{s['t1'].strftime('%H:%M')}")

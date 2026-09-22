from playwright.sync_api import sync_playwright
import json
got={}
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page()
    # 1) full dates list
    r=pg.request.get("https://gexlog.com/dashboard/api/archive.php?action=dates")
    dates=r.json(); got["dates"]=dates
    # 2) try fetching one historical report a few ways
    tests=[
      "https://gexlog.com/dashboard/api/archive.php?action=report&type=morning&date=2026-07-15",
      "https://gexlog.com/dashboard/api/archive.php?type=morning&date=2026-07-15",
      "https://gexlog.com/dashboard/api/report.php?type=morning&date=2026-07-15",
      "https://gexlog.com/dashboard/api/archive.php?action=get&type=evening&date=2026-07-15",
    ]
    for u in tests:
        rr=pg.request.get(u)
        try: j=rr.json()
        except: j=None
        got[u]=(rr.status, list(j.keys()) if isinstance(j,dict) else type(j).__name__, (json.dumps(j)[:200] if j else rr.text()[:120]))
    b.close()
m=got["dates"].get("morning",[]); e=got["dates"].get("evening",[])
print(f"MORNING dates: {len(m)}  range {m[-1]} .. {m[0]}")
print(f"EVENING dates: {len(e)}  range {e[-1] if e else '-'} .. {e[0] if e else '-'}")
print("\n=== fetch tests ===")
for k,v in got.items():
    if k.startswith("http"): print(k, "\n   ->", v, "\n")
json.dump(got, open("scratchpad/gexlog_archive_probe.json","w"), indent=2, default=str)

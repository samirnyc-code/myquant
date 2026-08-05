import sys, json
sys.path.insert(0, "scripts")
from mq_api import MQ

mq = MQ()
out = {}
for sym in ("SPX",):
    d = {}
    try: d["levels"] = mq.levels(sym)
    except Exception as e: d["levels_err"] = str(e)
    try: d["matrix"] = mq.matrix(sym, "eod")
    except Exception as e: d["matrix_err"] = str(e)
    try: d["blindspots"] = mq.blindspot_levels(sym)
    except Exception as e: d["blindspots_err"] = str(e)
    try: d["levels_report"] = mq.levels_report(sym)
    except Exception as e: d["levels_report_err"] = str(e)
    try:
        gi = mq.gamma_insights(sym, 5)
        d["gamma_insights_latest"] = gi[0] if gi else None
    except Exception as e: d["gi_err"] = str(e)
    out[sym] = d

json.dump(out, open("scratchpad/mq_now.json","w"), indent=2, default=str)
print("SAVED. Top-level keys per sym:")
for sym,d in out.items():
    print(sym, {k:(type(v).__name__) for k,v in d.items()})
print("\n=== LEVELS raw ===")
print(json.dumps(out["SPX"].get("levels"), indent=2, default=str)[:2500])

import json
g = json.load(open(r"c:\Users\Admin\myquant\data\options_sim\gameplan_20260717.json"))
print("regime:", g.get("regime"), "| spot at build:", g.get("spot"), "| keys:", list(g.keys()))
for t in g.get("triggers", []):
    cond = t.get("condition") or t.get("when") or {k: v for k, v in t.items() if k not in ("id",)}
    print(f"  {str(t.get('id','?')):24s} {str(cond)[:150]}")

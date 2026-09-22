import json, glob, os
base = r"c:\Users\Admin\myquant\data\discord\parsed"
for f in ["mq_patrick-journaling", "mq_patrick-mq-analysis"]:
    p = os.path.join(base, f + ".jsonl")
    print("=" * 70); print(f, "exists:", os.path.exists(p))
    rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    print(len(rows), "msgs")
    ts = [r.get("timestamp", "") for r in rows if r.get("timestamp")]
    if ts:
        print("range:", min(ts)[:16], "->", max(ts)[:16])
    auth = {}
    for r in rows:
        a = r.get("author", "?"); auth[a] = auth.get(a, 0) + 1
    print("authors:", auth)

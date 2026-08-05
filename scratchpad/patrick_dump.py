import json, os
base = r"c:\Users\Admin\myquant\data\discord\parsed"
for f in ["mq_patrick-journaling", "mq_patrick-mq-analysis"]:
    p = os.path.join(base, f + ".jsonl")
    print("\n" + "=" * 78); print("#### " + f); print("=" * 78)
    rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    rows.sort(key=lambda r: r.get("timestamp", ""))
    for r in rows:
        c = (r.get("content") or "").strip()
        att = r.get("attachments") or ""
        ts = r.get("timestamp", "")[:16]
        if not c and not att:
            continue
        print(f"\n[{ts}]")
        if c:
            print(c)
        if att:
            print("  <attach:", str(att)[:120], ">")

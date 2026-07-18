import glob
import json
import re

for f in glob.glob(r"C:\Users\Admin\myquant\scratchpad\mq_endpoints\resp_*.json"):
    d = json.load(open(f, encoding="utf-8"))
    if "net-gex-by-expiration" in d["url"]:
        raw = d["body"]
        print("URL:", d["url"])
        keys = sorted(set(re.findall(r'"(\w+)":', raw[:5000])))
        print("field keys:", keys)
        i = raw.find('"strikes"')
        print("\nstrike block sample:")
        print(raw[i:i + 800] if i > 0 else raw[600:1500])
        break
else:
    print("no net-gex-by-expiration capture found")

# also the matrix totals — does it carry OI?
for f in glob.glob(r"C:\Users\Admin\myquant\scratchpad\mq_endpoints\resp_*.json"):
    d = json.load(open(f, encoding="utf-8"))
    if "options/matrix" in d["url"]:
        raw = d["body"]
        print("\n\nMATRIX URL:", d["url"])
        oi = re.findall(r'"(\w*oi\w*)":([-\d.]+)', raw[:2000])
        print("OI fields in totals:", oi[:8])
        break

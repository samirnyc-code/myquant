import sys
sys.path.insert(0, "scripts")
import options_trade_log as t

df = t.load()
print(df.shape)
for _, r in df.iterrows():
    c = r["commentary"]
    ok = f"YES ({len(c)} ch)" if isinstance(c, str) and c else repr(c)
    print(f"{r['trade_id']:35s} grade={r['grade']!s:3s} commentary={ok}")

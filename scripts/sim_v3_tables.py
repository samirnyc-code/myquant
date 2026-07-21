"""Read the v3 sim trades and print clean tables: every entry type x every exit,
overall and for FIRST-ENTRY-AFTER-A-FLIP only."""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
df = pd.read_parquet(ROOT / "docs" / "living" / "brooks_sim_trades_v3.parquet")
EXITS = ["1R", "1.5R", "2R", "3R", "EOD"]
df["etype"] = df["dir"] + df["count"].astype(str) + "-" + df["setup"]
ORDER = [f"{d}{c}-{s}" for d in ("L", "S") for c in (1, 2) for s in ("IB", "OB", "N")]


def tbl(sub, title):
    print(f"\n### {title}")
    n = sub[sub.book == "1R"].groupby("etype").size()
    mr = sub.pivot_table(index="etype", columns="book", values="R", aggfunc="mean")
    net = sub[sub.book == "EOD"].groupby("etype")["net"].sum()
    win = sub[sub.book == "EOD"].groupby("etype")["R"].apply(lambda s: (s > 0).mean() * 100)
    print("| entry | n | " + " | ".join(f"{e} R" for e in EXITS) + " | EODwin% | EOD net |")
    print("|---|---:|" + "---:|" * (len(EXITS) + 2))
    for e in ORDER:
        if e not in n.index:
            continue
        cells = " | ".join(f"{mr.loc[e, b]:+.3f}" if b in mr.columns and not pd.isna(mr.loc[e, b]) else "  ." for b in EXITS)
        print(f"| {e} | {n[e]} | {cells} | {win.get(e, 0):.0f}% | ${net.get(e, 0):,.0f} |")
    # rollups
    for lab, mask in [("ALL", sub.etype.notna()),
                      ("IB+OB only", sub.setup.isin(["IB", "OB"])),
                      ("N only", sub.setup == "N"),
                      ("count1 only", sub["count"] == 1),
                      ("count2 only", sub["count"] == 2)]:
        s2 = sub[mask]
        n1 = len(s2[s2.book == "1R"])
        mrr = {b: s2[s2.book == b]["R"].mean() for b in EXITS}
        netE = s2[s2.book == "EOD"]["net"].sum()
        winE = (s2[s2.book == "EOD"]["R"] > 0).mean() * 100
        cells = " | ".join(f"{mrr[b]:+.3f}" for b in EXITS)
        print(f"| **{lab}** | {n1} | {cells} | {winE:.0f}% | ${netE:,.0f} |")


tbl(df, "ALL entries")
tbl(df[df.pf == 1], "FIRST ENTRY AFTER A FLIP only")
tbl(df[df.pf == 0], "NOT first-after-flip")

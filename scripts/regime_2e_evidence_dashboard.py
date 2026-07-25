"""EVIDENCE DASHBOARD — one figure that visually supports the S85 16yr-OOS verdict.
Reads the committed CSVs (oos_pertrade / durable / durable_realtick) and renders a 6-panel PNG.

  python scripts/regime_2e_evidence_dashboard.py
Output: docs/living/evidence_dashboard_20260725.png (+ prints the backing tables)
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

WT = Path(__file__).resolve().parent.parent
R = WT / "data" / "regime"
BLUE, RED, GREY, GREEN, ORANGE = "#2a78d6", "#c0392b", "#8b8f96", "#27a35a", "#e08a1e"


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def main():
    pt = pd.read_csv(R / "oos_pertrade_20260725.csv")
    g = pt[pt.with_trend].copy(); g["pre21"] = g.yr <= 2020            # frozen gated book (net @0.30)
    dur = pd.read_csv(R / "durable_20260725.csv").sort_values("Date")  # durable book (netd)
    rt = pd.read_csv(R / "durable_realtick_20260725.csv")             # real-tick specs

    fig = plt.figure(figsize=(16, 11), dpi=115)
    gs = fig.add_gridspec(3, 2, hspace=0.42, wspace=0.22)

    # ---- Panel 1: frozen 16yr equity, 2021 boundary ----
    ax = fig.add_subplot(gs[0, 0])
    x = g.sort_values("Date"); eq = x.net.cumsum().values
    noos = int((x.yr <= 2020).sum())
    ax.plot(range(len(x)), eq, lw=1.6, color=BLUE)
    ax.axvline(noos, color=RED, ls="--", lw=1.2); ax.axhline(0, color=GREY, lw=0.8)
    ax.annotate("pre-2021\nPF 0.96, -$6.4k", (noos*0.5, eq.max()*0.15), color=RED, ha="center", fontsize=9)
    ax.annotate("2021+\nPF 1.38, +$90.4k", (noos+ (len(x)-noos)*0.5, eq.max()*0.55), color=GREEN, ha="center", fontsize=9)
    ax.set_title("1. FROZEN book equity 2010-2026 — regime-fit: flat pre-2021, all the money post", fontweight="bold", fontsize=10)
    ax.set_ylabel("cum $ (1 ES)")

    # ---- Panel 2: PF by year frozen vs durable ----
    ax = fig.add_subplot(gs[0, 1])
    yrs = sorted(g.yr.unique())
    pf_fr = [pf(g[g.yr == y].net) for y in yrs]
    pf_du = [pf(dur[dur.yr == y].netd) for y in yrs]
    w = 0.4
    ax.bar([i-w/2 for i in range(len(yrs))], pf_fr, w, color=GREY, label="FROZEN (symmetric)")
    ax.bar([i+w/2 for i in range(len(yrs))], pf_du, w, color=BLUE, label="DURABLE (long-biased+gated short)")
    ax.axhline(1.0, color=RED, lw=1, ls="--"); ax.set_xticks(range(len(yrs)))
    ax.set_xticklabels([str(y)[2:] for y in yrs], fontsize=8)
    ax.set_ylabel("PF"); ax.legend(fontsize=8, frameon=False)
    ax.set_title("2. PF by year — durable stays >1 through the pre-2021 grind", fontweight="bold", fontsize=10)

    # ---- Panel 3: long vs short net by era ----
    ax = fig.add_subplot(gs[1, 0])
    data = {"longs (2EL)": [g[(g.dir=="L")&g.pre21].net.sum(), g[(g.dir=="L")&~g.pre21].net.sum()],
            "shorts (2ES)": [g[(g.dir=="S")&g.pre21].net.sum(), g[(g.dir=="S")&~g.pre21].net.sum()]}
    idx = np.arange(2)
    ax.bar(idx-0.2, [data["longs (2EL)"][0], data["shorts (2ES)"][0]], 0.4, color=GREEN, label="pre-2021")
    ax.bar(idx+0.2, [data["longs (2EL)"][1], data["shorts (2ES)"][1]], 0.4, color=ORANGE, label="2021+")
    ax.axhline(0, color=GREY, lw=0.8); ax.set_xticks(idx); ax.set_xticklabels(["LONGS", "SHORTS"])
    ax.set_ylabel("net $"); ax.legend(fontsize=8, frameon=False)
    ax.annotate("shorts pre-2021\n-$8.6k (PF 0.91)\nTHE KILLER", (1-0.2, data["shorts (2ES)"][0]),
                color=RED, ha="center", va="top", fontsize=8)
    ax.set_title("3. Long vs short by era — the pre-2021 loss is ALL the short side", fontweight="bold", fontsize=10)

    # ---- Panel 4: PF by ADR bucket, pre vs post ----
    ax = fig.add_subplot(gs[1, 1])
    edges = np.quantile(g.adr, [0, .2, .4, .6, .8, 1.0]); g["adrb"] = pd.cut(g.adr, np.unique(edges), labels=False, include_lowest=True)
    labs = [f"{edges[i]:.0f}-{edges[i+1]:.0f}" for i in range(5)]
    pre = [pf(g[(g.adrb==i)&g.pre21].net) for i in range(5)]
    pos = [pf(g[(g.adrb==i)&~g.pre21].net) for i in range(5)]
    ax.bar(np.arange(5)-0.2, pre, 0.4, color=GREEN, label="pre-2021")
    ax.bar(np.arange(5)+0.2, pos, 0.4, color=ORANGE, label="2021+")
    ax.axhline(1.0, color=RED, lw=1, ls="--"); ax.set_xticks(range(5)); ax.set_xticklabels(labs, fontsize=8)
    ax.set_xlabel("ADR10 bucket (pts)"); ax.set_ylabel("PF"); ax.legend(fontsize=8, frameon=False)
    ax.set_title("4. PF by volatility bucket — moderate-vol (ADR 22-37) works in BOTH eras", fontweight="bold", fontsize=10)

    # ---- Panel 5: durable equity + underwater ----
    ax = fig.add_subplot(gs[2, 0])
    v = dur.netd.values; eq = np.cumsum(v); uw = eq - np.maximum.accumulate(eq)
    noos2 = int((dur.yr <= 2020).sum())
    ax.plot(range(len(eq)), eq, lw=1.5, color=BLUE); ax.axvline(noos2, color=RED, ls="--", lw=1.1); ax.axhline(0, color=GREY, lw=0.8)
    ax2 = ax.twinx(); ax2.fill_between(range(len(uw)), uw, 0, color=RED, alpha=0.25); ax2.set_ylabel("underwater $", color=RED)
    ax.set_ylabel("cum $"); ax.set_title("5. DURABLE equity+underwater — positive all 16y but 90% underwater, vol-lumpy", fontweight="bold", fontsize=10)

    # ---- Panel 6: real-tick FROZEN vs DURABLE ----
    ax = fig.add_subplot(gs[2, 1])
    specs = ["FROZEN", "DURABLE40", "DURABLE30"]
    nets = [rt[rt.spec==s].net.sum() for s in specs]
    def mdd(s):
        e = rt[rt.spec==s].sort_values("Date").net.cumsum(); return float((e-e.cummax()).min())
    ndd = [nets[i]/-mdd(specs[i]) for i in range(3)]
    b = ax.bar(range(3), nets, 0.5, color=[GREY, BLUE, "#9bc0ea"])
    ax.set_xticks(range(3)); ax.set_xticklabels(specs, fontsize=9); ax.set_ylabel("net $ (2021-26, real ticks)")
    for i, (n, r) in enumerate(zip(nets, ndd)):
        ax.annotate(f"${n/1000:.0f}k\nnet/DD {r:.1f}", (i, n), ha="center", va="bottom", fontsize=8)
    ax.set_title("6. REAL ticks 2021-26 — FROZEN wins the modern regime (net/DD 9.8 vs 3.9)", fontweight="bold", fontsize=10)

    for a in fig.get_axes():
        for sp in ("top", "right"):
            if a.get_ylabel() != "underwater $":
                a.spines[sp].set_visible(False)
        a.grid(axis="y", color="#eceeed", lw=0.6)
    fig.suptitle("2E BOOK — 16-YEAR OOS EVIDENCE (ES, Databento 1-min 2010-2026 + real NT ticks 2021-26)",
                 fontweight="bold", fontsize=13, y=0.995)
    p = WT / "docs" / "living" / "evidence_dashboard_20260725.png"
    fig.savefig(p, facecolor="white", bbox_inches="tight"); print("saved", p)


if __name__ == "__main__":
    main()

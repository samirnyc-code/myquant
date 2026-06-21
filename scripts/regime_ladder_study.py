"""regime_ladder_study.py — base rates for the nested balance-edge ladder.

Tests three rungs of "is price accepting through a balance edge (discovery/trend) or
rotating within it (TR/fade)?", from RTH bars + the overnight (ETH) levels built by
build_eth_levels.py. NO sim engine here — this is the cheapest-first headline that
decides whether the CC overlay (Phase B) is worth running.

  Rung 1 — ETH edge:   first RTH break of ETH_High/Low → accept vs reject.
  Rung 2 — Brooks magnet (prior-day range): conditioned on open INSIDE prior range,
           P(touch prior High / Low / both / neither), which first, and accept/reject
           at the prior extreme (discovery vs failed break).
  Rung 3 — ADR exhaustion: empirical continuation curve P(range≥(k+Δ)·ADR | ≥k·ADR).
           No assumed threshold — developing range is monotone, so this is just the
           survival curve of final day-range / ADR.

Definitions (per the session brief):
  • magnet "touch" = intraday High≥level (up) / Low≤level (down).
  • accept/reject = CLOSE-based: N bars after first touch, did it CLOSE beyond the
    level (accept) or back inside (reject)?  N=ACCEPT_N.
  • ADR = trailing-14 mean of RTH daily range (High−Low), causal (prior days only).
  • 2022 is reported as a separate row everywhere (the chop/bear holdout).

Run: .venv/Scripts/python.exe scripts/regime_ladder_study.py
Out: docs/living/regime_ladder_<date>.md  +  data/regime_ladder_sessions.parquet
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

_BARS = _ROOT / "data" / "bars" / "_continuous.parquet"
_ETH  = _ROOT / "data" / "eth_levels.parquet"
_OUT  = _ROOT / "docs" / "living"
_SESS_OUT = _ROOT / "data" / "regime_ladder_sessions.parquet"

ADR_WINDOW = 14
ACCEPT_N   = 12        # bars after first touch to classify accept/reject (60 min)
TICK       = 0.25


def log(m: str) -> None:
    print(f"[ladder] {datetime.now():%H:%M:%S} {m}", flush=True)


# ── per-session level-reaction (shared by ETH and prior-day rungs) ────────────

def level_reaction(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
                   level: float, up: bool, n: int = ACCEPT_N) -> dict:
    """Classify the first break of `level` in `direction` within one session.

    up=True  → break = first bar High≥level; accept = close beyond above.
    up=False → break = first bar Low≤level;  accept = close beyond below.
    Returns touched / first_touch_bar / accept (close-based, n bars later) / eod_beyond.
    """
    if up:
        hit = np.where(highs >= level)[0]
    else:
        hit = np.where(lows <= level)[0]
    if len(hit) == 0:
        return {"touched": False, "touch_bar": -1, "accept": None, "eod_beyond": None}
    b = int(hit[0])
    j = min(b + n, len(closes) - 1)
    beyond = (closes[j] > level) if up else (closes[j] < level)
    eod = (closes[-1] > level) if up else (closes[-1] < level)
    return {"touched": True, "touch_bar": b, "accept": bool(beyond), "eod_beyond": bool(eod)}


def build_sessions() -> pd.DataFrame:
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars["Date"] = bars["DateTime"].dt.date
    eth_cols = ["Date", "ETH_High", "ETH_Low", "ETH_Open", "ETH_Close"]
    eth_raw = pd.read_parquet(_ETH)
    if {"PC_High", "PC_Low"}.issubset(eth_raw.columns):
        eth_cols += ["PC_High", "PC_Low"]
    eth = eth_raw[eth_cols]

    rows = []
    for d, g in bars.groupby("Date"):
        g = g.sort_values("DateTime")
        H, L, C = g["High"].to_numpy(), g["Low"].to_numpy(), g["Close"].to_numpy()
        rows.append({
            "Date": d, "OOD": float(g["Open"].iloc[0]),
            "RTH_High": float(H.max()), "RTH_Low": float(L.min()),
            "RTH_Close": float(C[-1]), "n_bars": len(g),
            "Hs": H, "Ls": L, "Cs": C,
        })
    s = pd.DataFrame(rows).sort_values("Date").reset_index(drop=True)
    s = s.merge(eth, on="Date", how="left")

    # prior-day levels + ADR (causal)
    s["HOY"] = s["RTH_High"].shift(1)
    s["LOY"] = s["RTH_Low"].shift(1)
    s["prior_close"] = s["RTH_Close"].shift(1)
    s["rng"] = s["RTH_High"] - s["RTH_Low"]
    s["ADR"] = s["rng"].shift(1).rolling(ADR_WINDOW, min_periods=5).mean()
    s["year"] = pd.to_datetime(s["Date"]).dt.year

    # open location vs prior range / gap
    s["open_loc"] = np.select(
        [s["OOD"] > s["HOY"], s["OOD"] < s["LOY"]],
        ["above", "below"], default="inside")
    s["gap_adr"] = (s["OOD"] - s["prior_close"]) / s["ADR"]

    # ── per-session level reactions ──────────────────────────────────────────
    rec = []
    for r in s.itertuples():
        H, L, C = r.Hs, r.Ls, r.Cs
        out = {}
        if not np.isnan(r.ETH_High):
            up = level_reaction(H, L, C, r.ETH_High, up=True)
            dn = level_reaction(H, L, C, r.ETH_Low, up=False)
            out.update(ethH_touch=up["touched"], ethH_accept=up["accept"], ethH_eod=up["eod_beyond"],
                       ethL_touch=dn["touched"], ethL_accept=dn["accept"], ethL_eod=dn["eod_beyond"])
        if not np.isnan(r.HOY):
            hu = level_reaction(H, L, C, r.HOY, up=True)
            ld = level_reaction(H, L, C, r.LOY, up=False)
            out.update(hoy_touch=hu["touched"], hoy_bar=hu["touch_bar"], hoy_accept=hu["accept"],
                       loy_touch=ld["touched"], loy_bar=ld["touch_bar"], loy_accept=ld["accept"])
        rec.append(out)
    s = pd.concat([s.drop(columns=["Hs", "Ls", "Cs"]), pd.DataFrame(rec)], axis=1)
    return s


# ── reporting helpers ─────────────────────────────────────────────────────────

def pct(x) -> str:
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{100*x:.0f}%"


def rung1_eth(s: pd.DataFrame) -> list[str]:
    L = ["## Rung 1 — ETH edge (overnight balance break)\n",
         "First RTH break of the overnight high/low → accept (closes beyond) vs reject.\n",
         "| side | break rate | accept\\|break | held EOD\\|break | n |",
         "|---|---|---|---|---|"]
    for side, tcol, acol, ecol in [("ETH High (up)", "ethH_touch", "ethH_accept", "ethH_eod"),
                                   ("ETH Low (down)", "ethL_touch", "ethL_accept", "ethL_eod")]:
        d = s[s[tcol].notna()]
        broke = d[d[tcol]]
        L.append(f"| {side} | {pct(d[tcol].mean())} | {pct(broke[acol].mean())} "
                 f"| {pct(broke[ecol].mean())} | {len(broke)} |")
    return L + [""]


def rung2_magnet(s: pd.DataFrame) -> list[str]:
    ins = s[(s["open_loc"] == "inside") & s["hoy_touch"].notna()].copy()
    ins["hoy_touch"] = ins["hoy_touch"].astype(bool)      # concat left these object-dtype;
    ins["loy_touch"] = ins["loy_touch"].astype(bool)      # ~ on object misfires → cast first
    both = (ins["hoy_touch"] & ins["loy_touch"])
    neither = (~ins["hoy_touch"] & ~ins["loy_touch"])
    # which first
    first_hi = ((ins["hoy_touch"] & ~ins["loy_touch"]) |
                (ins["hoy_touch"] & ins["loy_touch"] & (ins["hoy_bar"] <= ins["loy_bar"]))).sum()
    L = ["## Rung 2 — Brooks magnet (open INSIDE prior range)\n",
         f"Sessions opening inside prior range: **{len(ins)}** of {len(s)} "
         f"({pct(len(ins)/len(s))}).\n",
         "| metric | value |", "|---|---|",
         f"| touch prior High before close | {pct(ins['hoy_touch'].mean())} |",
         f"| touch prior Low before close  | {pct(ins['loy_touch'].mean())} |",
         f"| touch BOTH extremes           | {pct(both.mean())} |",
         f"| touch NEITHER (pure inside)   | {pct(neither.mean())} |",
         f"| of touchers, High touched first | {pct(first_hi/max((ins['hoy_touch']|ins['loy_touch']).sum(),1))} |",
         "",
         "**Acceptance at the prior extreme (discovery vs failed break):**\n",
         "| level | accept\\|touch | n |", "|---|---|---|",
         f"| prior High | {pct(ins[ins['hoy_touch']]['hoy_accept'].mean())} | {ins['hoy_touch'].sum()} |",
         f"| prior Low  | {pct(ins[ins['loy_touch']]['loy_accept'].mean())} | {ins['loy_touch'].sum()} |",
         ""]
    return L


def rung3_adr(s: pd.DataFrame) -> list[str]:
    d = s[s["ADR"].notna()].copy()
    d["rr"] = d["rng"] / d["ADR"]
    ks = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0]
    L = ["## Rung 3 — ADR exhaustion (continuation survival curve)\n",
         f"final RTH range / ADR — median **{d['rr'].median():.2f}×**, "
         f"mean {d['rr'].mean():.2f}×.  No assumed threshold; curve below.\n",
         "| reached k×ADR | P(reach this) | P(reach next 0.25 \\| here) | n |",
         "|---|---|---|---|"]
    for i, k in enumerate(ks):
        n_here = (d["rr"] >= k).sum()
        p_here = n_here / len(d)
        if i < len(ks) - 1:
            n_next = (d["rr"] >= ks[i + 1]).sum()
            cont = n_next / n_here if n_here else np.nan
        else:
            cont = np.nan
        L.append(f"| {k:.2f}× | {pct(p_here)} | {pct(cont)} | {n_here} |")
    return L + [""]


def by_year(s: pd.DataFrame) -> list[str]:
    L = ["## Per-year (2022 = chop/bear holdout)\n",
         "| year | n | open-inside% | ETH-H break% | ETH-H accept\\|brk | inside→touch-an-extreme% |",
         "|---|---|---|---|---|---|"]
    for y, g in s.groupby("year"):
        ins = g[g["open_loc"] == "inside"]
        ehb = g[g["ethH_touch"].notna()]
        broke = ehb[ehb["ethH_touch"]]
        touched_extreme = (ins["hoy_touch"] | ins["loy_touch"]) if len(ins) else pd.Series([], dtype=bool)
        L.append(f"| {y} | {len(g)} | {pct((g['open_loc']=='inside').mean())} "
                 f"| {pct(ehb['ethH_touch'].mean())} | {pct(broke['ethH_accept'].mean())} "
                 f"| {pct(touched_extreme.mean() if len(ins) else np.nan)} |")
    return L + [""]


def main() -> int:
    if not _ETH.exists():
        log(f"ERROR: {_ETH} not found — run build_eth_levels.py first.")
        return 1
    log("building per-session table...")
    s = build_sessions()
    s.to_parquet(_SESS_OUT, index=False)
    log(f"wrote {len(s)} sessions -> {_SESS_OUT}")

    eth_cov = s["ETH_High"].notna().mean()
    head = [f"# Regime Ladder — base rates ({datetime.now():%Y-%m-%d})\n",
            f"Sessions: **{len(s)}** ({s['Date'].min()} → {s['Date'].max()}).  "
            f"ETH coverage: {pct(eth_cov)}.  ADR={ADR_WINDOW}d, accept N={ACCEPT_N} bars.\n",
            f"Open location: inside {pct((s['open_loc']=='inside').mean())}, "
            f"above {pct((s['open_loc']=='above').mean())}, "
            f"below {pct((s['open_loc']=='below').mean())}.\n"]
    md = head + rung1_eth(s) + rung2_magnet(s) + rung3_adr(s) + by_year(s)
    txt = "\n".join(md)

    out = _OUT / f"regime_ladder_{datetime.now():%Y%m%d}.md"
    out.write_text(txt, encoding="utf-8")
    log(f"wrote report -> {out}")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("\n" + txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())

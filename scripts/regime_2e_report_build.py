"""Builds the S83 comprehensive report artifact: docs/artifacts/regime_2e_report.html.

Heavy pass: re-simulates the HEADLINE book (WT | h09-13 | retest 4t | 4pt stop | EOD,
STRICT through-fills) trade-by-trade to record fill/exit bars, hold time, MFE/MAE and
exit type -> data/regime/headline_trades_detail_20260723.csv (committed).

Then emits the single-file HTML from scripts/regime_2e_report_template.html with:
equity curves (touch+strict), stat tiles, detailed trade metrics, monthly chart,
stop x target PF matrices, the full robustness cell grid, zoomed single-trade
anatomy charts, and three annotated full sessions. All images base64-inlined.

  python scripts/regime_2e_report_build.py [--skip-detail]  (reuse existing detail CSV)
"""
import base64, io, json, sys, time
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

TICK = 0.25; PT = 50.0; COMM = 5.0
WT_ROOT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
sys.path.insert(0, str(WT_ROOT / "scripts"))
from regime_second_entry_study import phase_transitions, load_day  # noqa: E402
from regime_2e_sweeps import detect_entries  # noqa: E402

R = WT_ROOT / "data" / "regime"
OUT = WT_ROOT / "docs" / "artifacts" / "regime_2e_report.html"
DETAIL = R / "headline_trades_detail_20260723.csv"
GOOD_HOURS = {"09", "10", "11", "12", "13"}
SHADE = {"neutral": ("#9aa0a6", 0.10), "bull": ("#1f7a3d", 0.07), "bear": ("#b23a2e", 0.07)}


def pf(s):
    gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return gp / gl if gl > 0 else float("inf")


def b64fig(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="white")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


b = pd.read_parquet(DATA / "bars" / "_continuous.parquet")
b["Date"] = b["DateTime"].dt.date.astype(str)


# ================= 1. headline trade-detail pass (strict fills) =================
def qualifying_trades(dstr, g, tP, tbar, want_trace=False):
    """Headline-config trades for one day with full detail. Returns (trades, trace)."""
    O, Hh, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
    n = len(g)
    trace = {} if want_trace else None
    transitions = phase_transitions(Hh, L, n, tP, tbar, trace=trace)
    entries = detect_entries(g, tP, tbar)
    tr_ix = [t for (t, _) in transitions]; tr_md = [m for (_, m) in transitions]
    g_dt = g["DateTime"].values
    out = []
    for (fb, sb, dr, cnt, trig) in entries:
        if cnt != 2:
            continue
        short = dr == "S"
        a = np.searchsorted(tbar, fb, "left"); z = np.searchsorted(tbar, fb, "right")
        s = tP[a:z]
        hit = np.nonzero(s <= trig)[0] if short else np.nonzero(s >= trig)[0]
        if not len(hit):
            continue
        jf = a + int(hit[0])
        regime = tr_md[bisect_right(tr_ix, jf) - 1]
        if (short and regime != "BEAR") or (not short and regime != "BULL"):
            continue
        lim = trig + 4 * TICK if short else trig - 4 * TICK
        seg0 = tP[jf:]
        jl_ = np.nonzero(seg0 > lim)[0] if short else np.nonzero(seg0 < lim)[0]
        if not len(jl_):
            continue
        jfl = jf + int(jl_[0])
        fill = lim; fill_bar = int(tbar[jfl])
        hh_ = pd.Timestamp(g_dt[min(fill_bar, n - 1)]).strftime("%H:%M")
        if hh_[:2] not in GOOD_HOURS:
            continue
        stop = fill + 16 * TICK if short else fill - 16 * TICK
        seg = tP[jfl:]
        js_ = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
        if len(js_):
            jx = int(js_[0]); ex = stop; ext = "stop"
        else:
            jx = len(seg) - 1; ex = seg[-1]; ext = "eod"
        exit_bar = int(tbar[min(jfl + jx, len(tbar) - 1)])
        path = seg[:jx + 1]
        mfe = (fill - path.min()) if short else (path.max() - fill)
        mae = (path.max() - fill) if short else (fill - path.min())
        pnl = ((fill - ex) if short else (ex - fill)) * PT - COMM
        out.append(dict(Date=dstr, dir=dr, trig=trig, fill=fill, stop=stop, exit=ex,
                        fill_bar=fill_bar, exit_bar=exit_bar, sig_bar=sb,
                        hold_bars=exit_bar - fill_bar, exit_type=ext,
                        mfe_pts=round(float(mfe), 2), mae_pts=round(float(mae), 2),
                        net=round(pnl, 1), fill_time=hh_))
    return out, trace


if DETAIL.exists() and "--skip-detail" in sys.argv:
    det = pd.read_csv(DETAIL)
else:
    rows = []; t0 = time.time()
    days = sorted(b["Date"].unique())
    for di, dstr in enumerate(days):
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        try:
            tr_, _ = qualifying_trades(dstr, g, tP, tbar)
            rows += tr_
        except Exception as e:
            print(dstr, "ERR", repr(e), flush=True)
        if (di + 1) % 150 == 0:
            print(f"[{di+1}/{len(days)}] trades={len(rows)} ({time.time()-t0:.0f}s)", flush=True)
    det = pd.DataFrame(rows)
    det.to_csv(DETAIL, index=False)
    print(f"detail -> {DETAIL}  n={len(det)}")

det = det.sort_values(["Date", "fill_bar"]).reset_index(drop=True)

# ================= 2. metrics =================
wins = det[det.net > 0]; losses = det[det.net <= 0]
streak = mx = 0
for v in det.net.values:
    streak = streak + 1 if v <= 0 else 0
    mx = max(mx, streak)
det["ym"] = det.Date.str[:7]
mon = det.groupby("ym").net.agg(n="size", net="sum")
all_months = pd.period_range(det.Date.min()[:7], det.Date.max()[:7], freq="M").astype(str)
mon = mon.reindex(all_months, fill_value=0)
tpm_med = int(mon.n.median()); tpm_min = int(mon.n.min()); tpm_max = int(mon.n.max())

stats = dict(
    EXP_TR=f"{det.net.mean():+,.0f}", AVG_WIN=f"{wins.net.mean():+,.0f}",
    AVG_LOSS=f"{losses.net.mean():,.0f}",
    PAYOFF=f"{abs(wins.net.mean()/losses.net.mean()):.2f}",
    HOLD_MED=f"{int(det.hold_bars.median())}",
    TPM=f"{tpm_med} · {tpm_min}–{tpm_max}",
    MAX_LSTREAK=str(mx), STOP_PCT=f"{(det.exit_type=='stop').mean()*100:.0f}",
    BEST_TR=f"{det.net.max():+,.0f}", WORST_TR=f"{det.net.min():,.0f}",
    POS_MONTHS=f"{int((mon.net>0).sum())}/{len(mon)}",
)

# monthly chart (two stacked panels, one measure each)
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 5), dpi=110, sharex=True,
                               gridspec_kw=dict(height_ratios=[3, 1], hspace=0.12))
xs = np.arange(len(mon))
cols = ["#1f7a3d" if v >= 0 else "#b23a2e" for v in mon.net.values]
ax1.bar(xs, mon.net.values, color=cols, width=0.82)
ax1.axhline(0, color="#c3c2b7", lw=1)
ax1.set_ylabel("net $ / month"); ax1.grid(axis="y", color="#eceeed", lw=0.7)
ax2.bar(xs, mon.n.values, color="#7a8894", width=0.82)
ax2.set_ylabel("trades"); ax2.grid(axis="y", color="#eceeed", lw=0.7)
tick_ix = [i for i, m in enumerate(mon.index) if m.endswith("-01")]
ax2.set_xticks(tick_ix); ax2.set_xticklabels([mon.index[i][:4] for i in tick_ix])
for ax in (ax1, ax2):
    for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
fig.tight_layout()
MONTHLY_IMG = b64fig(fig)

# ================= 3. matrices =================
tbl = pd.read_csv(R / "sweep_report_tables_20260723.csv")
ST_T = ["r05", "r10", "r15", "r20", "r30", "r40", "f2p", "f4p", "f6p", "eod"]
ST_S = ["sb1", "sb4", "fx2p", "fx3p", "fx4p"]


def st_matrix(scope, label):
    d = tbl[(tbl.table == scope) & (tbl.a == "PF")]
    cells = {(r.b, r.c): r.value for r in d.itertuples()}
    h = [f"<h3 style='margin:18px 0 4px'>{label}</h3>",
         "<div class='tablewrap'><table><tr><th>stop \\ target</th>"]
    h += [f"<th>{t}</th>" for t in ST_T] + ["</tr>"]
    for s_ in ST_S:
        h.append(f"<tr><td>{s_}</td>")
        for t_ in ST_T:
            v = cells.get((s_, t_))
            if v is None or pd.isna(v):
                h.append("<td>·</td>"); continue
            cls = "c-g" if v > 1 else "c-r"
            h.append(f"<td class='{cls}'>{v:.2f}</td>")
        h.append("</tr>")
    h.append("</table></div>")
    return "".join(h)


MATRIX_ST = (st_matrix("ALL 2E", "All second entries (n=3,340)") +
             st_matrix("WITH-TREND", "With-trend only (n=1,186)") +
             st_matrix("BROOKS CELL (WT+SBstrong+EMAside)",
                       "Brooks cell: with-trend + strong signal bar + EMA side (n=170)"))

rob_t = pd.read_csv(R / "robustness_through_20260723.csv")
rob_c = pd.read_csv(R / "robustness_20260723.csv")
ROB_S = ["3p", "4p", "5p", "6p", "sb1"]


def rob_matrix(df, label):
    d = df[df["filter"] == "WT"]
    cells = {(r.window, r.retest, getattr(r, "stop")): (r.PF_tr, r.PF_te)
             for r in d.itertuples()}
    h = [f"<h3 style='margin:18px 0 4px'>{label}</h3>",
         "<div class='tablewrap'><table><tr><th>window · retest</th>"]
    h += [f"<th>{s_}</th>" for s_ in ROB_S] + ["</tr>"]
    for w in ["h09-12", "h09-13", "h10-13", "all"]:
        for rt in [2, 4, 6, 8]:
            h.append(f"<tr><td>{w} · {rt}t</td>")
            for s_ in ROB_S:
                v = cells.get((w, rt, s_))
                if v is None:
                    h.append("<td>·</td>"); continue
                a_, b_ = v
                cls = "c-g" if (a_ > 1 and b_ > 1) else ("c-a" if (a_ > 1 or b_ > 1) else "c-r")
                bold = " style='outline:2px solid var(--teal)'" if (w == "h09-13" and rt == 4 and s_ == "4p") else ""
                h.append(f"<td class='{cls}'{bold}>{a_:.2f} / {b_:.2f}</td>")
            h.append("</tr>")
    h.append("</table></div>")
    return "".join(h)


MATRIX_ROB = (rob_matrix(rob_t, "Strict through-fills (the conservative grid — headline cell outlined)") +
              rob_matrix(rob_c, "Touch-fills (the optimistic bound)"))

# ================= 4. zoom charts =================
w_sorted = det.sort_values("net")
zoom_picks = [
    (det.loc[det.net.idxmax()], "Biggest winner"),
    (wins.iloc[(wins.net - wins.net.median()).abs().argmin()], "Median winner"),
    (det[det.exit_type == "stop"].loc[lambda d: d.net.idxmin()] if len(det[det.exit_type == "stop"]) else w_sorted.iloc[0], "Stop-out"),
    (det[det.exit_type == "eod"].loc[lambda d: d.net.idxmin()], "Worst EOD-hold loser"),
]


def render_zoom(t, label):
    g, tP, tbar = load_day(b, t.Date)
    O, Hh, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
    n = len(g)
    a0 = max(0, int(t.fill_bar) - 18); z0 = min(n - 1, int(t.exit_bar) + 6)
    fig, ax = plt.subplots(figsize=(13, 6), dpi=115)
    rng = Hh[a0:z0 + 1].max() - L[a0:z0 + 1].min()
    for k in range(a0, z0 + 1):
        up_ = C[k] >= O[k]
        col = "#2e9e8f" if up_ else "#e0574a"
        ax.plot([k, k], [L[k], Hh[k]], color=col, lw=1.8, zorder=2)
        ax.add_patch(plt.Rectangle((k - 0.32, min(O[k], C[k])), 0.64,
                                   max(abs(C[k] - O[k]), rng * 0.001),
                                   facecolor=col, edgecolor="black", lw=0.5, zorder=3))
    short = t.dir == "S"
    col = "#b23a2e" if short else "#1f7a3d"
    fb = int(t.fill_bar); xb = int(t.exit_bar)
    ax.plot([fb - 4, fb + 1], [t.trig] * 2, color="#33454d", lw=1.6, zorder=5)
    ax.text(fb - 4.2, t.trig, "trigger", ha="right", va="center", fontsize=10, color="#33454d")
    ax.plot([fb - 4, fb + 1], [t.fill] * 2, color=col, lw=1.6, zorder=5)
    ax.text(fb - 4.2, t.fill, "limit (retest)", ha="right", va="center", fontsize=10, color=col)
    ax.plot(fb, t.fill, "v" if short else "^", ms=17, color=col, mec="black", mew=1.5, zorder=7)
    ax.plot([fb - 1, xb + 1], [t.stop] * 2, ls=":", lw=1.8, color=col, zorder=5)
    ax.text(xb + 1.2, t.stop, "stop 4pt", va="center", fontsize=10, color=col)
    ax.plot([fb, xb], [t.fill, t.exit], ls="--", lw=1.5, color=col, alpha=0.7, zorder=5)
    ax.plot(xb, t.exit, "s", ms=11, color=col, mec="black", mew=1.2, zorder=7)
    ax.text(xb, t.exit + (rng * 0.05 if not short else -rng * 0.05),
            f"exit ({t.exit_type})", ha="center", fontsize=10, color=col, fontweight="bold")
    sgn = "+" if t.net >= 0 else ""
    ax.set_title(f"{label} — {t.Date}  ·  2E{t.dir} @ {t.fill_time} (machine-tz)  ·  "
                 f"hold {int(t.hold_bars)} bars  ·  MFE {t.mfe_pts}pt / MAE {t.mae_pts}pt  ·  "
                 f"net {sgn}{t.net:,.0f}$", fontsize=12.5, fontweight="bold", pad=10)
    ax.grid(axis="y", color="#eceeed", lw=0.7); ax.set_axisbelow(True)
    for s_ in ("top", "right", "bottom"): ax.spines[s_].set_visible(False)
    ax.tick_params(axis="x", bottom=False, labelbottom=False)
    ax.set_xlim(a0 - 5.5, z0 + 3)
    fig.tight_layout()
    return b64fig(fig)


ZOOMS = "".join(
    f"<figure><img alt='Zoomed trade chart {t.Date}' src='data:image/png;base64,{render_zoom(t, lab)}'></figure>"
    for (t, lab) in zoom_picks)
print("zooms rendered")

# ================= 5. day examples =================
det_day = det.groupby("Date").net.agg(["sum", "size"])
EXAMPLES_DAYS = [(det_day["sum"].idxmax(), "Best day"),
                 (det_day[det_day.index != det_day["sum"].idxmax()]["size"].idxmax(), "Busiest day"),
                 (det_day["sum"].idxmin(), "Worst day")]


def render_day(dstr, label):
    g, tP, tbar = load_day(b, dstr)
    O, Hh, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
    n = len(g)
    quals, trace = qualifying_trades(dstr, g, tP, tbar, want_trace=True)
    vhi = Hh.max(); vlo = L.min(); rng = vhi - vlo; off = rng * 0.02
    fig, ax = plt.subplots(figsize=(22, 8), dpi=105)
    bounds = sorted([(s_, "start", sd) for (s_, sd, _) in trace["starts"]] +
                    [(b_, "term", None) for (_, _, b_, _) in trace["terms"]])
    cur = "neutral"; x0 = 0; segs = []
    for (xb, ktp, sd) in bounds:
        segs.append((x0, xb, cur)); x0 = xb
        cur = sd if ktp == "start" else "neutral"
    segs.append((x0, n - 1, cur))
    for (a2, b2, sdv) in segs:
        colr, al = SHADE[sdv]
        ax.axvspan(a2 + 0.5 if a2 else -0.9, b2 + 0.5, color=colr, alpha=al, zorder=0)
        if b2 - a2 >= 4:
            ax.text((a2 + b2) / 2, vhi + rng * 0.05, sdv.upper(), ha="center",
                    fontsize=11, fontweight="bold",
                    color={"neutral": "#0e7c86", "bull": "#1f7a3d", "bear": "#b23a2e"}[sdv])
    for k in range(n):
        up_ = C[k] >= O[k]
        colr = "#2e9e8f" if up_ else "#e0574a"
        ax.plot([k, k], [L[k], Hh[k]], color=colr, lw=1.4, zorder=2)
        ax.add_patch(plt.Rectangle((k - 0.3, min(O[k], C[k])), 0.6,
                                   max(abs(C[k] - O[k]), rng * 0.001),
                                   facecolor=colr, edgecolor="black", lw=0.4, zorder=3))
    tot = 0.0
    for q in quals:
        short = q["dir"] == "S"
        colr = "#b23a2e" if short else "#1f7a3d"
        fb, xb = q["fill_bar"], q["exit_bar"]
        ax.plot(fb, q["fill"], "v" if short else "^", ms=16, color=colr, mec="black",
                mew=1.4, zorder=7)
        ax.plot([fb - 1, xb], [q["stop"]] * 2, ls=":", lw=1.6, color=colr, zorder=6)
        ax.plot([fb, xb], [q["fill"], q["exit"]], ls="--", lw=1.4, color=colr, alpha=0.7, zorder=6)
        ax.plot(xb, q["exit"], "s", ms=9, color=colr, mec="black", mew=1.0, zorder=7)
        sgn = "+" if q["net"] >= 0 else ""
        ax.annotate(f"2E{q['dir']}  {sgn}{q['net']:,.0f}$", (fb, q["fill"]),
                    xytext=(fb, q["fill"] + (off * 3.2 if short else -off * 3.2)),
                    ha="center", fontsize=11, fontweight="bold", color=colr,
                    bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=colr, lw=1.4))
        tot += q["net"]
    ax.set_xlim(-1, n); ax.set_ylim(vlo - rng * 0.06, vhi + rng * 0.10)
    ax.set_title(f"{dstr}  ·  qualifying edge trades: {len(quals)}  ·  day net "
                 f"{'+' if tot >= 0 else ''}{tot:,.0f}$  (strict fills)",
                 fontsize=14, fontweight="bold", pad=10)
    ax.grid(axis="y", color="#eceeed", lw=0.7); ax.set_axisbelow(True)
    for s_ in ("top", "right", "bottom"): ax.spines[s_].set_visible(False)
    ax.tick_params(axis="x", bottom=False, labelbottom=False)
    fig.tight_layout()
    return b64fig(fig), len(quals), tot


EXAMPLES = ""
for dstr, label in EXAMPLES_DAYS:
    b64, nq, tot = render_day(dstr, label)
    EXAMPLES += (f"<figure><figcaption><span class='cap-label'>{label}</span> — {dstr} · "
                 f"{nq} qualifying trade{'s' if nq != 1 else ''} · "
                 f"<span class='{'pos' if tot >= 0 else 'neg'}'>{tot:+,.0f}$</span></figcaption>"
                 f"<img alt='Annotated 5-minute ES chart for {dstr}' "
                 f"src='data:image/png;base64,{b64}'></figure>")
    print(f"day chart {dstr}: {nq} trades {tot:+,.0f}$")

# ================= 5b. prop / MES feasibility =================
thrj = pd.read_csv(R / "robustness_through_20260723.trades.csv")
thrj = thrj[(thrj.retest == 4) & (thrj["stop"] == "4p") &
            thrj.hh.astype(str).str.zfill(2).isin(GOOD_HOURS)]
thrj = thrj[["Date", "dir", "net", "er10"]].copy()
thrj["net"] = thrj.net.round(1)
det2 = det.copy(); det2["net"] = det2.net.round(1)
det2 = det2.merge(thrj.drop_duplicates(["Date", "dir", "net"]),
                  on=["Date", "dir", "net"], how="left")
print(f"ER join match rate: {det2.er10.notna().mean()*100:.1f}%")
ER_MED = 0.201
YEARS = 5.06


def book_stats(d, mult, comm):
    """Returns (net_series, closed_eq, dd_closed, max_dd_closed, max_dd_trail, uw_len)."""
    gross_pts = (d.net + COMM) / PT
    net = gross_pts * mult - comm
    closed = net.cumsum().values
    peak_c = np.maximum.accumulate(closed)
    ddc = closed - peak_c
    tr_high = np.concatenate([[0.0], closed[:-1]]) + d.mfe_pts.values * mult
    tr_low = np.concatenate([[0.0], closed[:-1]]) - d.mae_pts.values * mult
    peak = 0.0; worst = 0.0
    for i in range(len(closed)):
        peak = max(peak, tr_high[i])
        worst = min(worst, tr_low[i] - peak)
        peak = max(peak, closed[i])
        worst = min(worst, closed[i] - peak)
    uw = 0; mxuw = 0
    for v in ddc:
        uw = uw + 1 if v < -1e-9 else 0
        mxuw = max(mxuw, uw)
    return net, closed, ddc, float(ddc.min()), float(worst), mxuw


net_es, eq_es, ddc_es, ddmin_es, ddtrail_es, uw_es = book_stats(det2, PT, COMM)

fig, (axA, axB) = plt.subplots(2, 1, figsize=(14, 6.5), dpi=110, sharex=True,
                               gridspec_kw=dict(height_ratios=[2.2, 1], hspace=0.10))
xs = np.arange(len(eq_es))
axA.plot(xs, eq_es, color="#2a78d6", lw=1.8)
axA.axhline(0, color="#c3c2b7", lw=1)
axA.set_ylabel("closed equity $ (1 ES)")
tr_low_plot = np.concatenate([[0.0], eq_es[:-1]]) - det2.mae_pts.values * PT
peak_run = np.maximum.accumulate(np.maximum(eq_es, np.concatenate([[0.0], eq_es[:-1]]) + det2.mfe_pts.values * PT))
axB.fill_between(xs, np.minimum(tr_low_plot - peak_run, eq_es - peak_run), 0,
                 color="#b23a2e", alpha=0.25, label="trailing-style (incl. unrealized)")
axB.plot(xs, ddc_es, color="#b23a2e", lw=1.4, label="closed-trade")
axB.axhline(-4500 * 10, color="#33454d", lw=0)  # no-op keep scale natural
axB.set_ylabel("drawdown $"); axB.legend(loc="lower left", fontsize=9, frameon=False)
yrs_ = det2.Date.str[:4].values
tick_ix = [i for i in range(1, len(yrs_)) if yrs_[i] != yrs_[i - 1]]
axB.set_xticks(tick_ix); axB.set_xticklabels([yrs_[i] for i in tick_ix])
for ax in (axA, axB):
    ax.grid(axis="y", color="#eceeed", lw=0.7)
    for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
fig.tight_layout()
PROP_IMG = b64fig(fig)

BOOKS = [("headline (all qualifying)", det2),
         ("+ ER10 top-half filter", det2[det2.er10 >= ER_MED])]
mes_rows = []
scale_rows = []
verdict_bits = []
for bname, d_ in BOOKS:
    for comm_ in (5.0, 2.5):
        netm, _, _, ddc_m, ddt_m, _ = book_stats(d_, 5.0, comm_)
        gross = float(((d_.net + COMM) / PT * 5.0).mean())
        mes_rows.append(
            f"<tr><td>{bname} @ ${comm_:.2f} RT</td><td>{gross:+.1f}</td>"
            f"<td>{comm_:.2f}</td><td>{netm.mean():+.2f}</td>"
            f"<td class='{'pos' if netm.sum()>=0 else 'neg'}'>{netm.sum():+,.0f}</td>"
            f"<td>{pf(pd.Series(netm)):.2f}</td><td>{ddt_m:,.0f}</td></tr>")
    netm, _, _, _, ddt1, _ = book_stats(d_, 5.0, 5.0)
    for nc in (1, 2, 3, 5):
        tot = netm.sum() * nc; ddn = ddt1 * nc
        fits = "YES" if -ddn <= 4500 else "no"
        fits_b = "YES" if -ddn <= 3150 else "no"
        cls = "pos" if tot >= 0 else "neg"
        scale_rows.append(
            f"<tr><td>{nc}</td><td>{bname}</td><td class='{cls}'>{tot/YEARS:+,.0f}</td>"
            f"<td>{ddn:,.0f}</td><td>{fits}</td><td>{fits_b}</td></tr>")
    verdict_bits.append((bname, netm.sum(), ddt1))

hb, eb = verdict_bits[0], verdict_bits[1]
PROP_VERDICT = (
    f"1 ES cannot live inside a $4,500 trailing account (trail DD {ddtrail_es:,.0f}$). "
    f"On MES at your $5 RT the headline book nets {hb[1]:+,.0f}$ over 5 yrs per contract "
    f"({'viable' if hb[1] > 0 else 'commission-dead'}); the ER-filtered book nets "
    f"{eb[1]:+,.0f}$ per contract with a {eb[2]:,.0f}$ trailing DD — "
    f"{'it fits the account with room to scale as shown above' if -eb[2] * 1 <= 4500 and eb[1] > 0 else 'it does not clear the bar'}. "
    "Cheaper micro commissions (the $2.50 rows) change the math materially — worth negotiating "
    "before writing the strategy off at micro scale.")

prop_repl = dict(
    PROP_IMG=PROP_IMG, DD_CLOSED=f"{ddmin_es:,.0f}", DD_TRAIL=f"{ddtrail_es:,.0f}",
    DD_LEN=str(uw_es), DD_X=f"{-ddtrail_es/4500:.1f}",
    MES_ROWS="".join(mes_rows), SCALE_ROWS="".join(scale_rows),
    PROP_VERDICT=PROP_VERDICT)

# ================= 6. equity + yearly + assemble =================
thr = det.copy()
tch_raw = pd.read_csv(R / "robustness_20260723.trades.csv")
tch = tch_raw[(tch_raw.retest == 4) & (tch_raw["stop"] == "4p") &
              tch_raw.hh.astype(str).str.zfill(2).isin(GOOD_HOURS)].sort_values("Date")
W, H_, PAD = 1000, 300, 8
eq_t = thr.net.cumsum().values; eq_c = tch.net.cumsum().values
lo = min(eq_t.min(), eq_c.min(), 0) - 500; hi = max(eq_t.max(), eq_c.max()) + 500


def to_poly(eq):
    xs = np.linspace(PAD, W - PAD, len(eq))
    ys = H_ - PAD - (eq - lo) / (hi - lo) * (H_ - 2 * PAD)
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))


zero_y = H_ - PAD - (0 - lo) / (hi - lo) * (H_ - 2 * PAD)
yrs = thr.Date.str[:4].values
yr_ticks = "".join(f"<text x='{PAD + (W-2*PAD)*i/(len(yrs)-1):.0f}' y='{H_-2}' class='ax'>{yrs[i]}</text>"
                   for i in range(1, len(yrs)) if yrs[i] != yrs[i - 1])
tt_data = json.dumps([{"d": d, "v": round(float(v))} for d, v in zip(thr.Date.values, eq_t)])


def yr_rows(df):
    x = df.copy(); x["yr"] = x.Date.str[:4]
    y = x.groupby("yr").net.agg(n="size", net="sum", _pf=lambda s: round(pf(s), 2))
    return "".join(f"<tr><td>{ix}</td><td>{r.n}</td><td class='{'pos' if r.net>=0 else 'neg'}'>"
                   f"{r.net:+,.0f}</td><td>{r._pf}</td></tr>" for ix, r in y.iterrows())


dd_thr = float((thr.net.cumsum() - thr.net.cumsum().cummax()).min())
er_med = 0.201
ft = pd.read_csv(R / "robustness_through_20260723.trades.csv")
ft = ft[(ft.retest == 4) & (ft["stop"] == "4p") & ft.hh.astype(str).str.zfill(2).isin(GOOD_HOURS)]
ft_er = ft[ft.er10 >= er_med]

repl = dict(
    POLY_THR=to_poly(eq_t), POLY_TCH=to_poly(eq_c), ZERO_Y=f"{zero_y:.1f}",
    YR_TICKS=yr_ticks, TT_DATA=tt_data,
    NET_THR=f"{thr.net.sum():+,.0f}", N_THR=str(len(thr)),
    PF_THR=f"{pf(thr.net):.2f}", WIN_THR=f"{(thr.net>0).mean()*100:.1f}",
    DD_THR=f"{dd_thr:,.0f}",
    NET_TCH=f"{tch.net.sum():+,.0f}", PF_TCH=f"{pf(tch.net):.2f}",
    NET_ER=f"{ft_er.net.sum():+,.0f}", N_ER=str(len(ft_er)), PF_ER=f"{pf(ft_er.net):.2f}",
    PF_L=f"{pf(thr[thr.dir=='L'].net):.2f}", PF_S=f"{pf(thr[thr.dir=='S'].net):.2f}",
    YR_ROWS_THR=yr_rows(thr), YR_ROWS_TCH=yr_rows(tch),
    MATRIX_ST=MATRIX_ST, MATRIX_ROB=MATRIX_ROB,
    MONTHLY_IMG=MONTHLY_IMG, ZOOMS=ZOOMS, EXAMPLES=EXAMPLES, **stats, **prop_repl)

html = (WT_ROOT / "scripts" / "regime_2e_report_template.html").read_text(encoding="utf-8")
for k, v in repl.items():
    html = html.replace("{{" + k + "}}", str(v))
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(html, encoding="utf-8")
left = [t for t in ("{{" ) if False]
import re
miss = sorted(set(re.findall(r"\{\{([A-Z_]+)\}\}", html)))
if miss:
    print("WARNING unfilled placeholders:", miss)
print("wrote", OUT, f"({OUT.stat().st_size/1e6:.1f} MB)")

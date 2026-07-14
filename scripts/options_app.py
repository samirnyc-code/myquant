"""Options forward-sim dashboard (S73, v3) — Streamlit.

Read-only over the pipeline's files (no IB connection):
  data/options_log/trades.parquet     unified trade log (§B schema + commentary/grade/POP)
  data/options_sim/decisions.csv      daily 15:59 causal decisions
  data/options_sim/marks.csv          running PnL marks (~5 min) + live VIX
  data/options_sim/underlying_*.csv   intraday parity-spot samples
  data/options_sim/quotes_*.csv       16:00-16:15 NBBO fill tapes
  data/menthorq/spx_calibration.csv   MenthorQ vs IB levels
  data/nt8_es_1m.csv                  live ES via nt8/QSBarExporter.cs (optional)

Run:  .venv/Scripts/streamlit.exe run scripts/options_app.py
"""
import glob
import json
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
LOG = ROOT / "data" / "options_log" / "trades.parquet"

C_BLUE, C_ORANGE = "#2a78d6", "#eb6834"
C_GOOD, C_WARN, C_CRIT = "#0ca30c", "#eda100", "#d03b3b"
GRADE_C = {"A": C_GOOD, "B": C_BLUE, "C": C_WARN, "D": C_ORANGE, "F": C_CRIT}

st.set_page_config(page_title="Options Forward-Sim", layout="wide", page_icon="🎯")
st.markdown("""<style>
.block-container {padding-top: 1.6rem;}
div[data-testid="stMetric"] {background: rgba(128,128,128,.08); border: 1px solid rgba(128,128,128,.18);
  border-radius: 10px; padding: 10px 14px;}
div[data-testid="stMetric"] label {font-size: .72rem; opacity: .75;}
.gchip {display:inline-block; min-width:2.1em; text-align:center; padding:2px 8px; border-radius:8px;
  color:#fff; font-weight:700; font-size:.95rem;}
.tmeta {opacity:.8; font-size:.85rem;}
.pnlpos {color:#0ca30c; font-weight:700;} .pnlneg {color:#d03b3b; font-weight:700;}
h3 {margin-top: .4rem;}
</style>""", unsafe_allow_html=True)


@st.cache_data(ttl=60)
def load_trades():
    if not LOG.exists():
        return pd.DataFrame()
    df = pd.read_parquet(LOG)
    df["legs_str"] = df.legs.map(
        lambda s: "  ·  ".join(f"{l['side'][0].upper()}{l.get('qty', 1)} {l['strike']:.0f}{l['right']} {l['expiry'][4:6]}/{l['expiry'][6:]}"
                               for l in json.loads(s)) if isinstance(s, str) else "")
    return df


@st.cache_data(ttl=60)
def load_csv(p):
    return pd.read_csv(p) if Path(p).exists() else pd.DataFrame()


def money(v, signed=True):
    if v is None or v != v:
        return "—"
    return f"${v:+,.0f}" if signed else f"${v:,.0f}"


def chip(grade):
    g = str(grade) if isinstance(grade, str) else "?"
    c = GRADE_C.get(g[:1], "#777")
    return f"<span class='gchip' style='background:{c}'>{g}</span>"


def pnl_span(v):
    if v is None or v != v:
        return "—"
    cls = "pnlpos" if v >= 0 else "pnlneg"
    return f"<span class='{cls}'>{money(v)}</span>"


trades = load_trades()
marks = load_csv(SIM / "marks.csv")
last_marks = marks.groupby("trade_id").last() if len(marks) else pd.DataFrame()

col_t, col_b = st.columns([5, 1])
col_t.markdown("### 🎯 Options Forward-Sim — causal 15:59 BPS + paper strategies")
if col_b.button("🔄 Reload", use_container_width=True):
    st.cache_data.clear()
    st.rerun()


@st.fragment(run_every="5s")
def live_ticker():
    """Live SPX/ES/VIX strip — reads live.json written by scripts/spot_feed.py."""
    f = SIM / "live.json"
    if not f.exists():
        st.caption("⚪ live feed offline — start `scripts/spot_feed.py` after Gateway login")
        return
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return
    if d.get("state") != "live":
        st.caption(f"⚪ live feed: {d.get('state', 'offline')} (last {d.get('ts_et', '—')} ET)")
        return
    basis_note = f"basis {d['basis']:+.2f} @ {d['basis_ts']}" if d.get("basis") is not None else "basis —"
    st.markdown(
        f"<div style='display:flex;gap:2.2rem;align-items:baseline;padding:6px 14px;"
        f"background:rgba(42,120,214,.10);border:1px solid rgba(42,120,214,.35);border-radius:10px'>"
        f"<span>🟢 <b>LIVE</b> <span style='opacity:.6;font-size:.8em'>{d['ts_et']} ET</span></span>"
        f"<span style='font-size:1.25em'><b>SPX {d['spx']:,.2f}</b></span>"
        f"<span style='font-size:1.25em'>ES<sub>est</sub> <b>{d['es_est']:,.2f}</b> "
        f"<span style='opacity:.6;font-size:.7em'>{basis_note}</span></span>"
        f"<span style='font-size:1.25em'>VIX <b>{d['vix'] if d['vix'] else '—'}</b> "
        f"<span style='opacity:.6;font-size:.7em'>15-min delayed</span></span></div>",
        unsafe_allow_html=True)


live_ticker()

# ---------- headline ----------
closed = trades[trades.exit_dt.notna()] if len(trades) else trades
p = closed.pnl.astype(float) if len(closed) else pd.Series(dtype=float)
pf = p[p > 0].sum() / -p[p < 0].sum() if len(p) and (p < 0).any() else None
open_ids = set(trades[trades.exit_dt.isna()].trade_id) if len(trades) else set()
unreal = last_marks[last_marks.index.isin(open_ids)].unreal_pnl.sum() if len(last_marks) else None
vix_now = marks.vix.dropna().iloc[-1] if len(marks) and marks.vix.notna().any() else None
mark_ts = marks.ts_et.iloc[-1][11:16] if len(marks) else ""

open_tr = trades[trades.exit_dt.isna()] if len(trades) else trades
coll_log = open_tr.collateral.astype(float).sum() if len(open_tr) else 0.0
acct = load_csv(SIM / "account.csv")
acc_last = acct.iloc[-1] if len(acct) else None

m = st.columns(9)
m[0].metric("open trades", int(len(trades) - len(closed)))
m[1].metric("closed", len(closed))
m[2].metric("win %", f"{(p > 0).mean() * 100:.0f}%" if len(p) else "—")
m[3].metric("profit factor", f"{pf:.2f}" if pf else "—")
m[4].metric("realized P&L", money(p.sum()) if len(p) else "—")
m[5].metric(f"running P&L {('@ ' + mark_ts) if mark_ts else ''}", money(unreal) if unreal is not None else "—")
m[6].metric("collateral at risk (log)", money(coll_log, signed=False))
m[7].metric(f"IB margin {('@ ' + str(acc_last.ts_et)[11:16]) if acc_last is not None else ''}",
            money(float(acc_last.maint_margin), signed=False) if acc_last is not None else "—",
            help="FullMaintMarginReq from the paper account; init margin and NetLiq in Market data tab")
m[8].metric("VIX (live)", f"{vix_now:.1f}" if vix_now else "—")

tab_tr, tab_jr, tab_perf, tab_dec, tab_mkt = st.tabs(
    ["📋 Trades", "📓 Journal", "📈 Performance", "🕓 Decisions & fill tapes", "🌊 Market data & levels"])

# ---------- trades tab: interactive card wall ----------
with tab_tr:
    if not len(trades):
        st.info("No trades yet.")
    else:
        import streamlit.components.v1 as components
        import options_build_cards
        cards_f = options_build_cards.main()  # rebuild with freshest marks/spot
        rows = -(-len(trades) // 4)
        components.html(cards_f.read_text(encoding="utf-8"), height=max(430, rows * 230 + 40),
                        scrolling=True)
        st.caption("click a card → zooms to center · click again → flips to details + payoff diagram · Esc closes")

# ---------- journal tab ----------
with tab_jr:
    import options_journal as oj
    jn = oj.refresh()  # auto sections recomputed; reviews preserved
    jstats = oj.stats(jn)
    if jstats.get("closed"):
        jc = st.columns(6)
        jc[0].metric("closed", jstats["closed"])
        jc[1].metric("win rate", f"{jstats['win_rate']:.0%}")
        jc[2].metric("expectancy/trade", money(jstats["expectancy_$"]))
        jc[3].metric("avg R", jstats["avg_R"] if jstats["avg_R"] is not None else "—")
        jc[4].metric("PF", jstats["profit_factor"] or "—")
        jc[5].metric("avg MAE", money(jstats["avg_MAE"]) if jstats["avg_MAE"] is not None else "—")
    for tid, e in list(jn.items())[::-1]:
        a = e["auto"]
        state = a["state"].upper()
        life = a.get("lifecycle") or {}
        res = a["result"]
        head = (f"{a['strategy']} · {state} · "
                f"{'R ' + str(res['r_multiple']) if res['r_multiple'] is not None else ''} "
                f"{money(res['pnl']) if res['pnl'] is not None else ''}")
        with st.expander(f"📓 {head}", expanded=False):
            un_j = last_marks.unreal_pnl.get(tid) if len(last_marks) and a["state"] == "open" else None
            hl_pnl = res["pnl"] if res["pnl"] is not None else un_j
            t1 = st.columns(6)
            t1[0].metric("P&L" + (" (running)" if a["state"] == "open" else ""),
                         money(hl_pnl) if hl_pnl is not None else "—")
            t1[1].metric("R multiple", res["r_multiple"] if res["r_multiple"] is not None else "—")
            t1[2].metric("MFE", f"{money(life['mfe'])} · {life['mfe_R']}R" if life else "—")
            t1[3].metric("MAE", f"{money(life['mae'])} · {life['mae_R']}R" if life else "—")
            t1[4].metric("POP @ entry", "—" if a["plan"]["pop"] is None else f"{a['plan']['pop']:.0%}")
            t1[5].metric("entry grade", a["plan"]["entry_grade"] or "—")
            t2 = st.columns(6)
            t2[0].metric("max gain", money(a["plan"]["max_gain"], signed=False)
                         if a["plan"]["max_gain"] is not None else "unbounded")
            t2[1].metric("max loss", money(a["plan"]["max_loss"], signed=False)
                         if a["plan"]["max_loss"] is not None else "—")
            t2[2].metric("net credit/debit", a["execution"]["net_credit"])
            t2[3].metric("collateral", money(a["execution"]["collateral"], signed=False)
                         if a["execution"]["collateral"] else "—")
            t2[4].metric("VIX / rank", f"{a['context']['vix']} / {a['context']['vix_rank']}")
            t2[5].metric("gamma regime", a["context"]["gamma_regime"].split(" ")[0])
            l, r = st.columns(2)
            with l:
                st.caption(f"planned exit: {a['plan']['planned_exit']}"
                           + (f" · MFE @ {life['best_ts'][11:16]}, MAE @ {life['worst_ts'][11:16]}, "
                              f"{life['n_marks']} marks" if life else ""))
                st.markdown(f"_{a['plan']['thesis']}_")
            with r:
                rv = e["review"]
                og = st.selectbox("outcome grade (process, not P&L)",
                                  ["", "A+", "A", "B", "C", "D", "F"],
                                  index=(["", "A+", "A", "B", "C", "D", "F"].index(rv["outcome_grade"])
                                         if rv["outcome_grade"] in ["", "A+", "A", "B", "C", "D", "F"] else 0),
                                  key=f"og_{tid}")
                fp = st.selectbox("followed plan?", ["", "yes", "partial", "no"],
                                  index=(["", "yes", "partial", "no"].index(rv["followed_plan"])
                                         if rv["followed_plan"] in ["", "yes", "partial", "no"] else 0),
                                  key=f"fp_{tid}")
                xr = st.text_input("exit reason", rv["exit_reason"], key=f"xr_{tid}")
                mi = st.text_area("mistakes", rv["mistakes"], key=f"mi_{tid}", height=68)
                le = st.text_area("lesson", rv["lesson"], key=f"le_{tid}", height=68)
                dd = st.text_area("do differently", rv["do_differently"], key=f"dd_{tid}", height=68)
                if st.button("💾 Save review", key=f"sv_{tid}"):
                    jn[tid]["review"] = {"outcome_grade": og, "followed_plan": fp,
                                         "exit_reason": xr, "mistakes": mi,
                                         "lesson": le, "do_differently": dd}
                    oj.save_journal(jn)
                    st.success("saved")

# ---------- performance tab ----------
with tab_perf:
    if len(closed) > 1:
        st.markdown("**Equity curve (closed trades)**")
        eq = closed.sort_values("exit_dt")[["exit_dt", "pnl"]].copy()
        eq["equity $"] = eq.pnl.astype(float).cumsum()
        st.line_chart(eq.set_index("exit_dt")[["equity $"]], color=C_BLUE, height=280)
    if len(trades):
        st.markdown("**By strategy**")
        g = trades.copy()
        g["real"] = g.pnl.astype(float)
        if len(last_marks):
            g = g.merge(last_marks[["unreal_pnl"]], left_on="trade_id", right_index=True, how="left")
        agg = g.groupby("strategy_id").agg(trades=("trade_id", "count"), grade=("grade", "first"),
                                           realized=("real", "sum"), running=("unreal_pnl", "sum"))
        st.dataframe(agg.style.format({"realized": "${:+,.0f}", "running": "${:+,.0f}"}, na_rep="—"),
                     use_container_width=True)
    if not len(marks) and not len(closed):
        st.info("Charts appear once marks/closed trades exist.")

# ---------- decisions tab ----------
with tab_dec:
    dec = load_csv(SIM / "decisions.csv")
    st.markdown("**Causal 15:59 ET decisions** — one row per session, `fire` = BPS entry signal")
    if len(dec):
        st.dataframe(dec.iloc[::-1], use_container_width=True, height=220)
    else:
        st.caption("first row lands after today's 15:59 ET run")
    q_files = sorted(glob.glob(str(SIM / "quotes_*.csv")))
    st.markdown("**Fill tapes (16:00–16:15 NBBO)** — measures real fill drift")
    if q_files:
        qf = st.selectbox("tape", q_files, index=len(q_files) - 1, format_func=lambda x: Path(x).stem)
        q = load_csv(qf)
        if len(q):
            leg = st.selectbox("leg (strike)", sorted(q.strike.unique()))
            ql = q[q.strike == leg].set_index("ts_et")[["bid", "ask"]]
            st.line_chart(ql, color=[C_BLUE, C_ORANGE], height=260)
            st.caption(f"strike {leg}: bid (blue) / ask (orange)")
    else:
        st.caption("written when a sim signal fires or a sim trade closes")

# ---------- market tab ----------
with tab_mkt:
    left, right = st.columns(2)
    with left:
        st.markdown("**Intraday SPX (parity-spot samples)**")
        u_files = sorted(glob.glob(str(SIM / "underlying_*.csv")))
        if u_files:
            uf = st.selectbox("day", u_files, index=len(u_files) - 1,
                              format_func=lambda x: Path(x).stem.replace("underlying_", ""))
            u = load_csv(uf)
            if len(u):
                st.line_chart(u.set_index("ts_et")[["und"]].rename(columns={"und": "SPX"}),
                              color=C_BLUE, height=260)
        else:
            st.caption("no samples yet")
        es_f = ROOT / "data" / "nt8_es_1m.csv"
        if es_f.exists():
            st.markdown("**ES 1-min (NT8 live export)**")
            es = load_csv(es_f).tail(390)
            st.line_chart(es.set_index("DateTime")[["Close"]].rename(columns={"Close": "ES"}),
                          color=C_BLUE, height=260)
        else:
            st.caption("ES: compile nt8/QSBarExporter.cs in NT8 to light this up")
    with right:
        st.markdown("**VIX daily (auto-refreshed)**")
        vixd = load_csv(ROOT / "data" / "vix_daily.csv")
        if len(vixd):
            vixd = vixd.tail(250)
            st.line_chart(vixd.set_index(vixd.columns[0])[[vixd.columns[-1]]]
                          .rename(columns={vixd.columns[-1]: "VIX close"}), color=C_BLUE, height=260)
        st.markdown("**Account (paper) — NetLiq / margin history**")
        if len(acct):
            st.dataframe(acct.tail(12).iloc[::-1], use_container_width=True)
        else:
            st.caption("first row lands on the next options_mark.py run")
        st.markdown("**MenthorQ vs IB levels (daily calibration)**")
        mq = load_csv(ROOT / "data" / "menthorq" / "spx_calibration.csv")
        if len(mq):
            st.dataframe(mq.iloc[::-1], use_container_width=True)
        else:
            st.caption("run scratchpad/mq_logger.py after pasting levels")

        st.markdown("**Gamma levels — SPX vs ES** (paste ES levels into "
                    "`scratchpad/mq_levels_today.json` → `es` block)")
        lvl_f = ROOT / "scratchpad" / "mq_levels_today.json"
        live_f = SIM / "live.json"
        if lvl_f.exists():
            lv = json.loads(lvl_f.read_text(encoding="utf-8"))
            basis = None
            if live_f.exists():
                try:
                    basis = json.loads(live_f.read_text(encoding="utf-8")).get("basis")
                except Exception:
                    pass
            es = lv.get("es", {})
            rows = []
            for key, label in [("cr", "Call Resistance"), ("ps", "Put Support"), ("hvl", "HVL"),
                               ("cr0", "CR 0DTE"), ("ps0", "PS 0DTE"), ("hvl0", "HVL 0DTE"),
                               ("gw0", "Gamma Wall 0DTE")]:
                spx_v, es_v = lv.get(key), es.get(key)
                conv = round(spx_v + basis, 1) if (spx_v is not None and basis is not None) else None
                rows.append({"level": label, "SPX (MQ)": spx_v,
                             "SPX+basis → ES-equiv": conv, "ES (MQ)": es_v,
                             "ES vs converted": round(es_v - conv, 1)
                             if (es_v is not None and conv is not None) else None})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            if basis is None:
                st.caption("basis unavailable (feed offline) — ES-equivalents blank until "
                           "spot_feed.py runs during market hours")

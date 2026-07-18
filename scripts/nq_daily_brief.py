"""NQ Daily Brief generator (S75) — options-positioning briefing from the MQ API.

Renders the user's fixed template (recovered from the S73 PDF: BIAS / DEALER INTENT /
STRUCTURAL LEVELS / TODAY SESSION CONTEXT / TOMORROW PRESSURE / WEEK CONTEXT / SKIP
TODAY IF) with today's live data. Deterministic — every number comes straight from an
API field; nothing is estimated. Blind Spots are QUIN-only (API 404) and are marked
as unavailable rather than filled in.

Data: gamma-levels eod, options/matrix (eod + intraday), gamma-insights history,
metrics eod (Q-Score components), volatility-insights, net-gex-by-expiration
(per-strike surface), swing-levels, candles (spot).

Run: .venv/Scripts/python.exe scripts/nq_daily_brief.py [--symbol NQ1!]
Outputs: data/briefs/<SYM>_brief_<date>.md (+ raw JSON snapshot next to it), stdout.
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mq_api import MQ, GW

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "briefs"

NARROW_PIN = 300  # template rule: pin under 300 NQ points = narrow


def fm(x, nd=0):
    """29750.0 -> '29,750'"""
    return f"{x:,.{nd}f}"


def ordn(n):
    """31 -> '31st'"""
    n = int(round(n))
    sfx = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{sfx}"


def fgex(x):
    """Human GEX magnitude: -1908401 -> '-1.91M'"""
    a = abs(x)
    if a >= 1e9:
        s = f"{x/1e9:,.2f}B"
    elif a >= 1e6:
        s = f"{x/1e6:,.2f}M"
    elif a >= 1e3:
        s = f"{x/1e3:,.0f}K"
    else:
        s = f"{x:,.0f}"
    return s


def pull(sym):
    mq = MQ()
    d = {}
    d["levels"] = mq.levels(sym)
    d["matrix_eod"] = mq.matrix(sym, "eod")
    d["matrix_intra"] = mq.matrix(sym, "intraday")
    d["insights"] = mq.gamma_insights(sym, 30)
    d["metrics"] = mq.metrics(sym, 5)
    d["vol"] = mq.vol_insights(sym)
    d["per_strike"] = mq.per_strike(sym)
    d["swings"] = mq.get(f"swing-levels/{sym}")
    now = int(dt.datetime.now().timestamp() * 1000)
    r = mq.s.get(f"{GW}/tickers/{sym}/candles", headers={"authorization": mq.token},
                 params={"interval": "5m", "from": now - 3 * 24 * 3600 * 1000,
                         "to": now, "countBack": 300}, timeout=60)
    r.raise_for_status()
    d["candles_tail"] = r.json()[-3:]
    return d


def expiry_gravity(ps, expiry):
    """Gamma-weighted average strike for one expiry — its centre of hedging mass.
    (Max-OI midpoints were tried first and land on far-OTM lottery strikes.)"""
    try:
        ei = [e["expiration_date"] for e in ps["expirations"]].index(expiry)
    except ValueError:
        return None
    c = ps["cells"]
    wsum = ksum = 0.0
    for i in range(len(c["expiration_idx"])):
        if c["expiration_idx"][i] != ei:
            continue
        w = c["abs_gex"][i]
        ksum += w * ps["strikes"][c["strike_idx"][i]]
        wsum += w
    return ksum / wsum if wsum else None


def build(sym="NQ1!"):
    d = pull(sym)
    lv = d["levels"]
    mx = d["matrix_eod"]
    mi = d["matrix_intra"]
    gi = d["insights"]
    ps = d["per_strike"]
    today = dt.date.today().isoformat()

    spot = d["candles_tail"][-1]["c"]
    spot_ts = dt.datetime.fromtimestamp(d["candles_tail"][-1]["t"] / 1000)

    gex_now = mi["totals"]["net_gex"]          # freshest intraday total
    gex_eod = gi[0]["gex"]
    gex_prev = gi[1]["gex"]
    shift24 = gex_eod - gex_prev
    pctile = gi[0]["gex_percentile_1y"] * 100
    positive = gex_now > 0

    # Q-Score components
    m = d["metrics"][0]["metrics"]
    qvals = {k: m.get(k) for k in ("momentum", "option", "volatility", "seasonality")}
    qavg = sum(qvals.values()) / 4
    conv = "HIGH" if qavg >= 3.5 else ("MODERATE" if qavg >= 2.0 else "LOW")

    # pin (0DTE walls) + width
    cr0, ps0 = lv["call_resistance_0dte"], lv["put_support_0dte"]
    pin_w = cr0 - ps0
    pin_lbl = "narrow" if pin_w < NARROW_PIN else ("normal" if pin_w < 2 * NARROW_PIN else "wide")

    # gamma walls gex_1..10 ranked by index; split around spot
    walls = sorted(((lv[f"gex_{i}"], i) for i in range(1, 11)), key=lambda t: t[0])
    above = sorted([w for w in walls if w[0] > spot])[:2]           # nearest two above
    below = sorted([w for w in walls if w[0] < spot], reverse=True)[:2]

    # expiries (matrix eod = tonight's chain for today's session)
    exps = mx["expirations"]
    chain_abs = sum(e["abs_gex"] for e in exps) or 1.0
    e_today = next((e for e in exps if e["expiration_date"] == today), exps[0])
    later = [e for e in exps if e["expiration_date"] > e_today["expiration_date"]]
    e_next = later[0] if later else None
    # this week's largest (Mon..Fri of today)
    wk = dt.date.fromisoformat(today)
    week_end = (wk + dt.timedelta(days=6 - wk.weekday())).isoformat()
    wk_exps = [e for e in exps if today <= e["expiration_date"] <= week_end]
    e_week = max(wk_exps, key=lambda e: e["abs_gex"]) if wk_exps else e_today

    # OI put/call across the chain (per-strike surface)
    c = ps["cells"]
    oi_c, oi_p = sum(c["oi_call"]), sum(c["oi_put"])
    oi_pc = oi_p / oi_c if oi_c else float("nan")
    # gamma concentration above vs below spot (plain-English stand-in for GEX P/C)
    gex_abv = sum(c["abs_gex"][i] for i in range(len(c["strike_idx"]))
                  if ps["strikes"][c["strike_idx"][i]] > spot)
    gex_blw = sum(c["abs_gex"][i] for i in range(len(c["strike_idx"]))
                  if ps["strikes"][c["strike_idx"][i]] < spot)

    # gravity level for next expiry = gamma-weighted centre of its strikes
    grav = expiry_gravity(ps, e_next["expiration_date"]) if e_next else None

    # week trend from EOD gex history (last 5 sessions)
    hist5 = [g["gex"] for g in gi[:5]][::-1]
    building = hist5[-1] > hist5[0]

    flip0, hvl = lv["hvl_0dte"], lv["hvl"]
    dflip = spot - flip0
    sw = d["swings"][0] if d["swings"] else None
    in_pin = ps0 <= spot <= cr0          # position vs today's expiry band
    net_vs_gross = abs(gex_now) / (mi["totals"]["abs_gex"] or 1)

    mode = "FADE EDGES" if positive else "FOLLOW MOMENTUM"
    NA_BL = ("not available — MenthorQ publishes Blind Spot levels only inside QUIN, "
             "not through the data API, so this line cannot be filled honestly")

    # ---------------- render ----------------
    L = []
    A = L.append
    A(f"NQ DAILY BRIEF — {today}  (spot {fm(spot, 2)} as of {spot_ts:%H:%M} local, "
      f"levels snapshot {lv['timestamp']}, intraday gamma {mi['timestamp']})")
    A("")
    A("**BIAS**")
    A(f"Regime: {'Positive' if positive else 'Negative'} GEX (gamma exposure — the total "
      f"options hedging position of all market makers): the current net reading is "
      f"{fgex(gex_now)}, which sits in the {ordn(pctile)} percentile of the past year, so "
      f"dealers as a group are {'long options and will trade against price moves, dampening them'
       if positive else 'short options and must trade in the same direction as price, which adds fuel to moves'}.")
    A(f"Mode: {mode} — "
      + ("price tends to stall and reverse at the outer levels because dealer hedging pushes back "
         "against every move, so buying weakness near support and selling strength near resistance is favoured."
         if positive else
         "once price starts moving, dealer hedging pushes it further in the same direction, so "
         "breakouts and trends are more likely to keep going than to snap back."))
    A(f"Conviction: {conv} — based on Q-Score (a 0-5 rating of market strength across four factors): "
      f"Momentum {qvals['momentum']:.1f} meaning the recent price trend is "
      f"{'strong' if qvals['momentum'] >= 3.5 else 'middling' if qvals['momentum'] >= 2 else 'weak'}, "
      f"Options {qvals['option']:.1f} meaning options positioning is "
      f"{'supportive' if qvals['option'] >= 3.5 else 'mixed' if qvals['option'] >= 2 else 'unsupportive'}, "
      f"Volatility {qvals['volatility']:.1f} meaning the volatility backdrop is "
      f"{'calm and favourable' if qvals['volatility'] >= 3.5 else 'unsettled' if qvals['volatility'] >= 2 else 'hostile'}, "
      f"Seasonality {qvals['seasonality']:.1f} meaning the calendar has historically been "
      f"{'a tailwind' if qvals['seasonality'] >= 3.5 else 'neutral' if qvals['seasonality'] >= 2 else 'a headwind'} here.")
    A(f"GEX shift 24h: {'+' if shift24 >= 0 else ''}{fgex(shift24)} — this means dealers "
      f"{'covered short-option exposure overnight, so their positioning is less explosive than yesterday and today’s levels start on firmer footing'
       if shift24 > 0 else
       'added short-option exposure overnight, so their hedging will amplify moves more than yesterday and levels are less trustworthy'} "
      f"(yesterday {fgex(gex_prev)} → {fgex(gex_eod)} at last night's close).")
    iv = d["vol"]["iv"]
    ivp = iv["iv_1m_50d_percentile_1y"] * 100
    gex_size = ("small next to the gross book" if net_vs_gross < 0.15
                else "a meaningful fraction of the gross book" if net_vs_gross < 0.4
                else "dominant relative to the gross book")
    iv_desc = (f"1-month implied volatility in the {ordn(ivp)} percentile of the year (options are "
               f"pricing {'larger' if ivp >= 60 else 'smaller' if ivp <= 40 else 'roughly average'}"
               f"-than-usual moves)")
    A(f"Why today is different from a typical session: the net dealer gamma reading "
      f"({fgex(gex_now)}) is only {net_vs_gross*100:.0f}% of the {fgex(mi['totals']['abs_gex'])} "
      f"gross book — {gex_size} — combined with {iv_desc}, so the push dealers give price is "
      f"{'weaker than the level map implies and price has more freedom to travel' if net_vs_gross < 0.15 else 'a real force behind the level map today'}.")
    A("")
    A("**DEALER INTENT**")
    if positive:
        A(f"Dealer position: dealers are net long options overall (net gamma {fgex(gex_now)}), meaning "
          f"customers sold them calls and puts; to keep their books flat they sell NQ futures as price "
          f"rises and buy as it falls, which squeezes price toward the middle of the range.")
    else:
        A(f"Dealer position: dealers are net short options overall (net gamma {fgex(gex_now)}), meaning "
          f"customers own the options and dealers wear the risk; to keep their books flat dealers must "
          f"sell NQ futures as price falls and buy as it rises — chasing, not stabilising.")
    A(f"What they do when price rises: approaching the call wall at {fm(lv['call_resistance'])} "
      f"(and today's expiry wall at {fm(cr0)}) dealers {'sell futures into the rally to stay hedged, capping it'
       if positive else 'have to buy futures to keep up with their short-call exposure, adding to the rally until the wall’s concentrated gamma finally forces two-way flow'}.")
    A(f"What they do when price falls: into the put support at {fm(lv['put_support'])} "
      f"(today's expiry floor {fm(ps0)}) dealers {'buy futures to stay hedged, cushioning the drop'
       if positive else 'must sell futures alongside the fall, accelerating it until the put strike’s gamma is absorbed'}.")
    A(f"Their goal today: with {e_today['abs_gex']/chain_abs*100:.0f}% of the whole chain's gamma "
      f"expiring today, the cleanest outcome for dealers is a close inside the "
      f"{fm(ps0)}–{fm(cr0)} band so the bulk of that exposure expires worthless and they can "
      f"take hedges off without moving the market"
      + ("." if in_pin else
         f" — note price is currently {'below' if spot < ps0 else 'above'} that band at "
         f"{fm(spot)}, so their incentive is a drift back {'up toward' if spot < ps0 else 'down toward'} it."))
    A(f"What changes their behaviour: a decisive move through the flip level at {fm(flip0)} — the "
      f"price where their books swing from one hedging direction to the other — would force them to "
      f"reverse their futures flow, which in price terms looks like a stall, a re-test, then a faster "
      f"move in the new direction.")
    A("")
    A("**STRUCTURAL LEVELS**")
    A("Red lines — resistance")
    A(f"R1: {fm(cr0)} — 0DTE Call Resistance (the price where the most call options expiring today "
      f"are concentrated — dealers must sell NQ futures here to hedge their exposure)")
    A(f"Why mark this: today's expiry carries {fgex(e_today['abs_gex'])} of gamma "
      f"({e_today['abs_gex']/chain_abs*100:.0f}% of the entire chain), so the hedging flow anchored "
      f"to this strike is large enough to stall the first test.")
    A(f"R2: {fm(lv['call_resistance'])} — All-Exp Call Resistance (the price where the most call "
      f"options across all future expiry dates are concentrated)")
    A(f"Why mark this: the whole chain holds {fgex(mx['totals']['abs_gex'])} of gross gamma and this "
      f"strike is its biggest call-side anchor, making it the structural ceiling until large positions roll.")
    for tag, (lvl, rank) in zip(("R3", "R4"), above):
        A(f"{tag}: {fm(lvl)} — GEX Wall (a price strike where a significant concentration of options "
          f"gamma exists, creating a zone of forced dealer activity), ranked {rank} by size today")
        A(f"Why mark this: it is the {'nearest' if tag == 'R3' else 'second-nearest'} large gamma "
          f"concentration above the current price ({fm(lvl - spot)} points away), and MenthorQ ranks "
          f"it #{rank} of the top ten, so expect the first touch to produce visible two-way trade.")
    A(f"R5: Blind Spot — {NA_BL}.")
    A("Green lines — support")
    A(f"S1: {fm(ps0)} — 0DTE Put Support (the price where the most put options expiring today are "
      f"concentrated — dealers must buy NQ futures here to hedge their put exposure)")
    A(f"Why mark this: puts outnumber calls across the chain {oi_pc:.2f}-to-1 by open contracts, "
      f"meaning the crowd is paying for downside protection, which loads the biggest forced-buying "
      f"flows onto put strikes like this one"
      + ("." if spot >= ps0 else
         f" — but price is already trading {fm(ps0 - spot)} points BELOW it, so until it is "
         f"reclaimed this level acts as overhead resistance, not support."))
    A(f"S2: {fm(lv['put_support'])} — All-Exp Put Support (structural put concentration across all "
      f"expiry dates combined)")
    A(f"Why mark this: the same {oi_pc:.2f}-to-1 put-heavy open interest makes this the deepest "
      f"pool of forced dealer buying below the market — the structural floor of the whole chain.")
    for tag, (lvl, rank) in zip(("S3", "S4"), below):
        A(f"{tag}: {fm(lvl)} — GEX Wall ranked {rank}, "
          f"{'nearest' if tag == 'S3' else 'second nearest'} below price")
        A(f"Why mark this: it sits {fm(spot - lvl)} points below current price at MenthorQ's #{rank} "
          f"gamma concentration, so it is the {'first' if tag == 'S3' else 'second'} place a decline "
          f"should meet mechanical dealer buying.")
    A(f"S5: Blind Spot — {NA_BL}.")
    A("Yellow lines — key zones")
    A(f"FLIP: {fm(flip0)} — HVL 0DTE (High Volatility Level — the exact price where dealer behaviour "
      f"switches from stabilising the market to amplifying moves, for today's expiry only)")
    A(f"Why mark this: price is currently {fm(abs(dflip))} points {'above' if dflip >= 0 else 'below'} "
      f"the flip, {'a thin cushion — one impulse bar can change the whole session’s character' if abs(dflip) < 100 else 'a reasonable buffer, so the current regime should survive ordinary rotations'}.")
    A(f"HVL: {fm(hvl)} — HVL All-Exp (the structural version of the regime switch line, calculated "
      f"across all open options positions)")
    A(f"Why mark this: the 0DTE flip moves daily with today's strikes while this one is anchored by "
      f"the whole chain — when price is between them, today's hedging and the structural hedging "
      f"disagree, and moves get choppy until one side wins.")
    A(f"BL1: Blind Spot — {NA_BL}.")
    A(f"BL_near: Blind Spot — {NA_BL}.")
    A(f"RANGE HIGH: {fm(lv['max_1d'])} — Session ceiling derived from the options market's implied "
      f"range (how far options pricing suggests NQ could move today)")
    A(f"Why mark this: reaching it means the day has already used the full move options were paying "
      f"for, so dealers who sold that movement start defending it and continuation beyond needs fresh news.")
    A(f"RANGE LOW: {fm(lv['min_1d'])} — Session floor from options-implied range")
    A(f"Why mark this: same mechanics in reverse — at this price the sellers of downside movement "
      f"are fully stretched and their re-hedging tends to slow the decline.")
    if sw:
        A(f"SWING TRIGGER {fm(sw['trigger'])} / SWING BAND {fm(sw['band'])} — MenthorQ's multi-day "
          f"swing model (direction: {sw['direction']}): a close beyond the band, or a reversal "
          f"through the trigger, marks a change in the multi-day path rather than intraday noise.")
    A("")
    A("**TODAY SESSION CONTEXT**")
    A(f"Active expiry pin: {e_today['expiration_date']} | {fm(ps0)} – {fm(cr0)}")
    A("What expiry pin means: Options expiring today create a mechanical band where dealers are "
      "simultaneously buying at the put wall and selling at the call wall — trapping price between "
      "them until expiry")
    A(f"Pin width: {fm(pin_w)} points — {pin_lbl}")
    A(f"Why this width matters today: a {pin_lbl} {fm(pin_w)}-point band backed by "
      f"{fgex(e_today['abs_gex'])} of expiring gamma ({e_today['abs_gex']/chain_abs*100:.0f}% of the "
      f"chain) means the boundaries are "
      f"{'well funded and should hold on a first test' if e_today['abs_gex']/chain_abs > 0.15 else 'only lightly funded, so treat them as reference prices, not hard walls'}"
      f"{'' if positive else ' — and with dealers net short gamma overall, a boundary break gets pushed rather than faded'}.")
    A("Pin expires: 16:00 ET (when today's index options stop trading and the hedges tied to them unwind)")
    if not in_pin:
        A(f"Position check: price ({fm(spot)}) is currently {'BELOW' if spot < ps0 else 'ABOVE'} "
          f"the pin band, so the walls read as a target zone to be reclaimed, not a cage — the "
          f"break scenario {'below' if spot < ps0 else 'above'} is already in progress.")
    A(f"If price breaks above {fm(cr0)}: dealers who were selling futures at the wall stop, and "
      f"those short the calls must chase the move by buying; with {fgex(gex_abv)} of gross gamma "
      f"stacked above spot versus {fgex(gex_blw)} below, the next mechanical brake is not until "
      f"R2 at {fm(lv['call_resistance'])}.")
    A(f"If price {'stays' if spot < ps0 else 'breaks'} below {fm(ps0)}: the forced buying at the "
      f"put wall is exhausted and, with "
      f"open puts outnumbering calls {oi_pc:.2f}-to-1 (a crowd already positioned for downside), "
      f"dealer selling pressure compounds toward S2 at {fm(lv['put_support'])}.")
    A("")
    A("**TOMORROW PRESSURE ON TODAY**")
    if e_next:
        A(f"Next expiry: {e_next['expiration_date']} | GEX {fgex(e_next['abs_gex'])} "
          f"({e_next['abs_gex']/chain_abs*100:.0f}% of total chain)")
        if grav:
            A(f"Gravity level: {fm(grav)} (the average strike of that expiry, weighted by how much "
              f"gamma sits at each strike — its centre of hedging mass)")
        A(f"Why it pulls today: {e_next['abs_gex']/chain_abs*100:.0f}% of all chain gamma expires "
          f"{'tomorrow' if e_next.get('dte', 9) <= 2 else 'at the next expiry'}, and as today's "
          f"contracts die that expiry's strikes take over the hedging math — so late-session flows "
          f"already start drifting price toward where its positioning is centred"
          + (f", around {fm(grav)}." if grav else "."))
    else:
        A("Next expiry: none found beyond today in the chain snapshot.")
    A("")
    A("**WEEK CONTEXT**")
    A(f"Largest expiry this week: {e_week['expiration_date']} | GEX {fgex(e_week['abs_gex'])} | "
      f"{e_week['abs_gex']/chain_abs*100:.0f}% of chain")
    A(f"Effect on today: that single date controls {e_week['abs_gex']/chain_abs*100:.0f}% of all "
      f"open gamma, so the strikes tied to it act like a magnet all week — today's range boundaries "
      f"get {'reinforced' if e_week['expiration_date'] != today else 'their final and strongest day of enforcement'} by hedging tied to that expiry.")
    if building and hist5[-1] <= 0:
        trend_txt = ("the destabilising short-gamma position is shrinking toward flat, so the "
                     "amplification of moves should fade and levels become more reliable as the week goes on")
    elif building:
        trend_txt = ("the stabilising force is growing, so ranges should tighten and levels "
                     "become more reliable as the week goes on")
    elif hist5[-1] <= 0:
        trend_txt = ("dealers are getting shorter gamma, so expect moves to be amplified more and "
                     "levels to give way more easily as the week goes on")
    else:
        trend_txt = ("the market is losing its stabilising gamma, so expect ranges to widen and "
                     "levels to give way more easily as the week goes on")
    A(f"GEX trend this week: {'building' if building else 'decaying'} — over the last five sessions "
      f"the net dealer gamma reading went from {fgex(hist5[0])} to {fgex(hist5[-1])}, meaning {trend_txt}.")
    A("")
    A("**SKIP TODAY IF**")
    if abs(dflip) < 100:
        A(f"Price keeps criss-crossing the flip level at {fm(flip0)} (it is only {fm(abs(dflip))} "
          f"points away right now) — when the switch between dealer-stabilised and dealer-amplified "
          f"trading flips back and forth intraday, every level on this page becomes unreliable.")
    elif e_today["abs_gex"] / chain_abs < 0.10:
        A(f"Only {e_today['abs_gex']/chain_abs*100:.0f}% of chain gamma expires today, so the pin "
          f"band is thinly funded — if the first test of either wall slices straight through, stand "
          f"aside because the map is not being enforced.")
    else:
        A(f"Price gaps or trends straight through the flip at {fm(flip0)} AND a wall "
          f"({fm(ps0)} or {fm(cr0)}) in the first hour — that combination means positioning has been "
          f"overwhelmed by outside news and none of today's dealer-driven levels can be trusted.")
    A("")
    A(f"[data: MenthorQ API | levels {lv['timestamp']} | intraday gamma {mi['timestamp']} | "
      f"chain totals net {fgex(mx['totals']['net_gex'])} / gross {fgex(mx['totals']['abs_gex'])} | "
      f"Blind Spots unavailable via API]")
    return "\n".join(L), d


def main():
    sym = sys.argv[sys.argv.index("--symbol") + 1] if "--symbol" in sys.argv else "NQ1!"
    text, raw = build(sym)
    OUT.mkdir(parents=True, exist_ok=True)
    stem = f"{re.sub(r'[^A-Za-z0-9]', '', sym)}_brief_{dt.date.today().isoformat()}"
    (OUT / f"{stem}.md").write_text(text, encoding="utf-8")
    (OUT / f"{stem}_raw.json").write_text(json.dumps(raw, indent=1), encoding="utf-8")
    print(text)
    print(f"\n[saved {OUT / (stem + '.md')}]", file=sys.stderr)


if __name__ == "__main__":
    main()

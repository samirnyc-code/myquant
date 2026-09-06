# Zen Trading Tech (Tim Fairweather) — Research Digest

Full-site crawl (S111). 104 posts enumerated, 20 read deeply. Base: https://zentradingtech.com
His data = own TradingView CSV exports → Claude. Core set = **ES RTH 5-min, Aug 2021+ (~1,279 days)**.
GitHub (his code + some ES CSVs + research reports): **https://github.com/Zen-Tim/zen-trading-tech-public**

## Leg counting (fully specified — matches our reproduction)
- Leg = walk from open, track extreme; reverse by > threshold → leg closes, new one starts.
- Threshold default **0.15 × ADR** (ADR = 8-day lookback). Also tested 0.10/0.20/0.25/0.33×.
- "Scalp floor" = 10% of day range; swing target = 40% of ADR (his toolkit constants).
- ES median 15 legs/day, FDAX 15 (mean 16.2). 0.20×→9.5, 0.33×→3.8. Worst ES day 39.
- **ES↔FDAX leg-count correlation ≈ 0** — don't borrow across markets.
- Asymmetry: extreme-down ~18 legs, extreme-up ~12. His guess: "panic doesn't travel straight."
- 2024 post gives 3 counting METHODS: (1) spike breaks (close beyond prior bar), (2) inside
  bars end a leg (consecutive IBs = one), (3) combination/multi-TF. Legs are fractal —
  a strong leg becomes a higher-TF leg needing its own sub-legs.

## Second-leg framework (2026)
- Hierarchy: bars → legs → moves → structures. "Everything gets a second leg" (breakouts,
  pullbacks, CT moves, and second legs themselves). Strong 2nd leg → its own 2nd leg;
  2nd legs often subdivide (3 legs reframe as 2).
- "A **failed second leg** is one of the most reliable reversal signals"; "second attempts
  have significantly higher probability than first attempts." No numeric thresholds — a guide.

## RLS ratio + day types (his own admission: UNSOLVED)
- **RLS = travel ABOVE the open vs travel BELOW the open** (open-relative up/down ratio).
  Distribution is inverse-bell/bimodal (days cluster one-sided). Letters not expanded.
- Leg count by RLS band: balanced 15-16 legs, one-sided up ~12, one-sided down ~18.
  **More directional = fewer legs.** Heuristic only: "fewer legs = more trend." No formula.
- Swing-point route (Samurai Scroll III): **1 swing break = trading range; 2 breaks = flip**
  (opposite trend / that-side range). Swing break = first CLOSE beyond a prior swing hi/lo.

## Backtestable setups with published stats (ES 5M RTH unless noted)
- **Consecutive opening bars** (two same-color 60min RTH bars, ~50% of days): after firing,
  same-dir close ~80%, HOD/LOD set 85%. Rule A: enter bar2 close, stop 0.5×, tgt 1.0× →
  57% win 0.114R/day. Rule B: 33% pullback, stop 0.5×, tgt 0.5× → 78% win 0.113R/day. TR days: fails.
- **Shaved opens (OOH/OOL):** bar1 = HOD/LOD 27.1% of ES days; shaved open 1.82%; survives
  whole day 0.42%. FDAX 6.44%/1.63%. Play = fade back to the open tick after a retest.
- **Bull streaks (29y ES):** weekly baseline 56% bull; **after 9 up-weeks, week10 reverses.**
  Daily: bull continuation 2-7 runs only 50-56% (no edge); **after 2-5 BEAR days, next leans
  bull** (bear-reversal bias). Asymmetric — reversal edge on bear runs, not bull runs.
- **Big ES days:** bar range ≥ ~3.3× ABR8 → **85% get a same-dir 2nd leg next day** (12/14).
  Enter 50% pullback, stop beyond the big-day bar.
- **18-bar range:** hi/lo of first 18 RTH bars (90 min on 5m). Small range → expansion;
  target = 50% of range (full MM "lower prob than expected"). "By bar 6 on 15m, 79% the
  day's HOD or LOD is in."
- **Consecutive 5m bars:** enter 4th/5th same-color close; 5-CSC swing most profit,
  4-5 CSC reversal (MA filter: sell CSC-bear ABOVE MA) highest hit rate. Numbers chart-only.
- **EMA20 streaks:** bars with hi&lo both one side of EMA20; 90% of streaks ≤20 bars.
- **MM of yesterday's range:** 0.5× "common enough to target", 1× marginal; prior-bar
  color + IBS combo → ~40% swing-target hit.
- **Inside/outside daily bars:** inside ~11%, outside ~11%; ~90% of sessions break the
  prior day's range.
- **Always-In (mechanical, backtestable):** flip needs (1) 2 consecutive same-color bars,
  (2) both close same side of a MA, (3) IBS>65 long / <35 short, (4) ≥1 bar range>ABR.
  States Long/Short/Neutral. 60m bias + 5m entries; 60m MA ≈ 5m 200MA.
  Brooks rule cited: 80% of reversals fail in a trend; 80% of breakouts fail in a range.
  NOTE: distinct from our broken Brooks regime engine ([[brooks_regime_engine_broken]]).

## His open questions (adds to our agenda)
- Leg count in first 2-3h predicts rest-of-day? (he calls this the tradeable version)
- Why sell-offs make more legs (we partly answered: +2.89 residual, gamma candidate).
- Classify days by type → % per bucket → does it feed a strategy? (reader challenge)
- Second-leg homework: 2nd-leg travel vs 1st; when does a pullback become a reversal?
- Run bull-streak study on FDAX/NQ/HSI; EMA20 streaks from the open (bulls vs bears differ).

## Tools / data to pull for exact methodology match
- GitHub Zen-Tim/zen-trading-tech-public: /indicators (Pine), /data (some ES CSVs),
  /research (reports w/ full tables). research-kits/Consecutive-Bar-Streaks has ready ES CSVs.
- TradingView Pine (open source): Zen RTH Trading Toolkit v1.8.1 (ABR MM + Opening Range +
  Vol Stats), Zen Open 18-Bar v5, Zen Consecutive Bars V9, Zen CSC Bar Strategy v2,
  Zen OOH/OOL v3, Zen EMA20 Streaks v1, Zen Always In v1, Zen Measured Moves, Zen IB v OB.
- Many stat posts put numbers ONLY in chart images — text gives method, not full distributions.

---

# Second pass — remaining research posts

## Backtestable ES 5M RTH setups (numbers are ours to generate where chart-only)
- **CSC bars (ES 5m RTH):** enter close of Nth consecutive same-color bar (N=4/5),
  1-at-a-time fill-or-kill, exit at session close. Test 0.5/1/1.5/2R ± MA filter
  (with-trend only), longs-only vs both-ways. Blog shows charts only → we generate PF/hit.
  "4-CSC reversals" highest hit-rate; best PF at 1–1.5R. (script/WEXwahbE)
- **Micro-gap reversal (MIG):** Bull = 3 consecutive bull bars, bar3.low > bar1.high
  (gap up) AND that low is BELOW EMA20 → fade SHORT; bear = mirror above EMA20.
  Author claims "very high hit rate", ZERO numbers → fully ours to test. (script/NmBTPCYQ)
- **Open-on-High/Low fade:** first bar opens exactly on its extreme (no tail that side)
  → fade to the open, stop beyond extreme. ES daily 0.5% freq, hourly 2.5%.
- **Shaved-open HOD/LOD survival:** first RTH bar opens on extreme AND it holds all day:
  ES 0.42% / FDAX 1.63% / HSI 2.22% / NK 5.17% (no n/date given). (script/NFjaD5lk)
- **Inside/Outside daily:** IB (H≤prevH & L≥prevL) ~11%, OB ~11%, regular ~78%;
  ~90% of sessions break the prior day's H or L. Context filter, no direction. (script/VRJ1GoSc)
- **Bar Range Category (vol-state feature, reusable):** each bar vs 8-bar avg range —
  Small <80%, Normal ±20%, Large 1.2–2.2×, X-Large >2.2×. Tag any ES study. (script/xnS68Lm8)

## DAX/FDAX + index (secondary market, stat-heavy)
- **DAX post-FOMC (50 events):** decision tree — OOR-bear + gap-down → 100% bear (n=8);
  prev-day IBS 0–25 → 89% bear; gap-down → 75% bear; XL gap-up >1×ABR → 0% bull (short).
  Mean reaction range 1.21× ABR. Fully codeable on FDAX; ≥60%=scalp, ≤40%=fade.
- **DAX Frankfurt/Globex both-sides break (1,878 days):** PM range broken both sides 62.4%
  (87% when PM range <10% ADR); overnight range broken 94.1%. PM levels = magnets, not S/R.
- **Nikkei historic gap-down (≥~3×ABR, 0.4% of days):** buy the open — 80% bull-bar day,
  O→H +1.17×ABR vs O→L −0.22×ABR, gap doesn't fill same day; invalidate if range<1×ABR & IBS<30.
- **Weekly-ABR gap (≥~37% ABR):** week's close usually tested that week (fade toward prior close).

## Price-action setups (conceptual, no stats) that CROSS with our leg/2E work
- **H1/H2/L1/L2 entries** = our second-entry construct: H2 = two-legged pullback entry
  (above a bull bar AND above MA); **L1-fade = fade first weak attempt expecting the 2nd
  entry** → directly = our S85 2EL/2ES book. "Stop after 3 signals/legs" recurs everywhere.
- **Failure-of-a-failure:** failed high-prob entry → price returns to it ("test target");
  if that fails, wait 3 legs against you before re-entry; hard-failure (big no-tail bars) →
  treat as range day. Maps to day-type transitions.
- **Tight channels:** "70% chance a new low gets retested"; avoid 3rd+ legs; fade failed
  signal bars for 1–2R.
- **Market-cycle drills:** channel = most common structure, breakout = rarest, "90% sideways"
  (assertion, not backtested). Spike→channel→range regime framing = our day-type engine.
- **First-three-bars / RTH-open consecutive bars:** open-spike failure ~50%; same open-structure
  bucket as shaved-open / consecutive-opening-bar work.

## Flags
- **ES stats "bookmark this" (/2025/09/02):** the richest stat page but ENTIRELY image-based
  (gap × open-structure × consecutive-60m-bar probabilities) — needs an OCR/manual pass on the
  PNGs, or pull the same numbers from his GitHub datasets.
- **Clone his GitHub** github.com/Zen-Tim/zen-trading-tech-public (MIT): ES/FDAX/HSI/Nikkei OHLC
  + research kits (FDAX Pre-Market Breakout, Daily Range Distribution #1). Data/code hub.

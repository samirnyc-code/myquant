# New-chat prompt — using the NYSE internals for turning points, the reversal indi & fibs

Paste the block below into a new chat to start the research cleanly.

---

## PROMPT

I'm researching the **EminiAddict / David Halsey Measured-Move method** (project lives in
`eminiaddict/`; read `docs/living/handoff.md` — especially the **S92-EA** block — and
`eminiaddict/notes/RULEBOOK.md` + `eminiaddict/notes/ch11_tick_extremes.md` FIRST).

I just exported **5 years of NYSE market internals** from NinjaTrader. I want to learn how to
**use the internals to identify and confirm turning points — especially at market-structure
extremes**, how they interact with **my reversal indicator**, and how they line up with the
**Halsey fib / measured-move levels**. Think of this as a research study, not a one-shot chart.

### Data I have (verify each before using — don't assume)
- **Internals (5-min bars, OHLCV):** `data/nt_internals/*_5m_*.csv` — symbols `^TICK, ^VIX, ^ADD,
  ^ADV, ^UVOL, ^DVOL, ^TRIN, ^TICKQ, BANK, DX 09-26`. Each file: a `# symbol=...` line, then
  `Time,Open,High,Low,Close,Volume`. Bars are **NT CLOSE-labeled** (bar time = bar close) and in
  **Central time**. ⚠️ There are multiple export runs — **pick the newest NON-EMPTY file per
  symbol** (many small/0-byte files are test runs); some symbols (e.g. BANK) may be empty/not
  entitled — report which.
- **ES bars:** `research/scalp_swing/es_5m_rth.parquet` (5M RTH, 2021→now; ⚠️ this pipeline is
  **OPEN-labeled** — reconcile the 5-min offset vs the close-labeled internals when you join).
  Also `eminiaddict/data/es_5m_24h.parquet` (recent 24H) and `data/ticks_continuous/*.parquet`
  (ES RTH tick-level 2021→now, `DateTime,Price,Volume`).
- **Reversal indicator ("rev indi"):** Python port in `research/revsim/` (`revdetect.py`,
  `revsim.py`, `combined_book.py`) — it detects reversals / FT-long / FT-short signals.
- **Halsey method:** `eminiaddict/notes/RULEBOOK.md`, the `chNN_*.md` chapter notes, and the
  method artifact at Mission Control `:8590/artifact/eminiaddict_measured_move_method`.

### What Halsey actually says about internals (test these, don't take on faith)
- **TICK divergence → reversal** (Ch 11): a new price extreme WITHOUT a new NYSE-TICK extreme.
- **TICK extremes ±1000** (±800 too) = reversal risk (programs take profit into them).
- **Buy low-TICK in an up series, sell high-TICK in a down series** (entry timing).
- **Breadth = advancing vol / declining vol = `^UVOL/^DVOL`**; strong/rising → longs only,
  weak/falling → shorts only. `^ADD` is the net adv-decl.
- **TRIN** (Arms) extremes = exhaustion. **VIX** inverse to indices; VIX < ~18.85 = risk-on gate.
- **Signal-alignment gate** (his flowchart): long only when VIX down-MM + Indices up-MM + new low
  TICK + BANK strength + USD (DX) weakness (mirror for shorts).

### Research questions (my priorities, in order)
1. **Turning points at market-structure extremes.** Define turning points two ways: (a) the rev
   indicator's signals, (b) structural swing highs/lows (bar-by-bar swing detector, not a
   %-zigzag). At each, characterize the internals: did TICK hit an extreme? Was there a TICK
   **divergence**? TRIN extreme? VIX/breadth flip? Build the empirical distribution at turning
   points vs ordinary bars — do internals actually mark the turns, and which ones matter most?
2. **Condition the rev indicator on internals.** Do rev signals that coincide with a TICK extreme
   + divergence (and/or TRIN extreme, breadth flip) have a higher forward win-rate / better
   excursion than unconfirmed ones? Build an "internals-confluence score" and test for a
   monotonic edge. This is the practical payoff — a filter that makes the rev signals better.
3. **Fib-related.** Do turning points cluster at Halsey fib levels (50% HWB, 61.8%, 123.6% of the
   prevailing MM)? Is a reversal **at a fib level + an internal extreme + structure** the
   high-probability setup? Test the alignment gate at a fib HWB entry: does "aligned" beat
   "unaligned"?

### Suggested phasing
- **Phase 0 — align the data (do first).** Write `scripts/ingest_nt_internals.py` (parallel to
  `ingest_nt_ticks.py`): read the newest non-empty `_5m_` file per symbol, build one master 5M
  table joined to ES (reconcile the open/close bar-label offset; internals are NYSE-RTH only, ES
  is 24H → join on RTH bars). Derive features: TICK bar-extreme (max |High|/|Low|), cumulative
  TICK, TICK-divergence flag, breadth ratio + slope, TRIN level, VIX level/regime, BANK & DX
  direction. Persist a dated parquet + a quick coverage/QA report (per symbol: rows, date range,
  % non-null, session).
- **Phase 1 — characterize** (Q1): stats + charts of internals at turning points vs baseline.
- **Phase 2 — condition** (Q2): confluence score → forward-return / win-rate study on the rev
  signals, out-of-sample.
- **Phase 3 — fibs + alignment gate** (Q3).

### Discipline (hard rules — see the memories)
- **Verify everything from the data before stating it**; if not checked, say "not verified".
- **No look-ahead** — internals only up to the signal bar; **reconcile bar labeling** (NT bars are
  CLOSE-labeled; `es_5m_rth` is OPEN-labeled — a 5-min mismatch will silently corrupt joins).
- **Real fills, treat any high PF as a bug** until audited on charts; out-of-sample, per-regime.
- **Persist everything** to committed `.py` files that also save dated output CSVs; **commit per
  unit of work**; no throwaway inline analysis.
- Start by **auditing the internals CSVs** (which symbols have real data, coverage, sessions) and
  building Phase 0. Show me the coverage report before modeling.

Start with Phase 0 (ingest + align + QA report) and show me what the internals coverage looks like.

---

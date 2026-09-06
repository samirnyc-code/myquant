# ThetaData v3 — Integration Reference (SPX/SPXW/SPY 0DTE + GEX walls)

Prepared 2026-09-06 from a scour of docs.thetadata.us (v3), http-docs.thetadata.us
(v2 legacy), the Subscriptions/Data-Issues pages, and ThetaData support (Sean).
Goal: be ready to pull the moment we subscribe. **Target tier: Options Standard ($80/mo).**

> ⚠️ ThetaData is mid-migration v2→v3. Everything below is **v3** unless noted.
> Several "v2" encodings (integer-cent strikes, `ms_of_day` timestamps, port 25510,
> Next-Page pagination) are GONE in v3 — do not copy v2 examples.

---

## 1. Which tier (and why)

| Need | Tier that unlocks it |
|---|---|
| 1-min NBBO (quote) history for SPXW/SPY/SPX | Value ($40) and up |
| Open interest history (full chain) | Value and up |
| **Implied volatility history** (needed to compute our own gamma) | **Standard ($80)** — Value does NOT include IV/greeks (confirmed by support) |
| Precomputed all-order greeks | Pro ($160) — *not needed*, we compute gamma from IV |
| Standalone SPX **index** 1-min series | separate **Index** subscription (see §6) — *probably not needed*, underlying is embedded in greeks/IV responses |

**Decision: Options Standard.** Gives NBBO + full-chain OI + IV, real-time (not
delayed), 4 concurrent requests, options history to 2016-01-01 (we only need ~2022+
for meaningful 0DTE). We compute gamma ourselves → no Pro. Underlying is embedded →
likely no separate Index sub (VERIFY, see §6/§8).

---

## 2. Architecture — a LOCAL terminal, not a cloud API

- Data is served by the **Theta Terminal**, a local auto-updating **Java 21+** app
  (`ThetaTerminalv3.jar`). Your code hits `http://127.0.0.1:25503` and the terminal
  proxies to ThetaData's backend. **There is no public cloud REST host.**
- Install: `java -jar ThetaTerminalv3.jar` (download from downloads.thetadata.us).
  Auth via `creds.txt` (line1 email, line2 password) or API key (CLI/env). Once the
  terminal is up + authenticated, REST calls carry **no auth headers** (localhost).
- **Port 25503 = v3.** (25510 is the old v2 terminal; 25504 staging.) Read the port
  from the auto-generated config since it's user-changeable.
- **REST-only in v3** — no pagination (single full response), **no streaming yet**
  (streaming still requires the v2 terminal; irrelevant for historical backfills).
- **One connection per terminal** — a second connection kicks the first. Run one
  puller per terminal instance.
- Terminal-up ≠ data-ready (same lesson as the IB gateway) — health-check with a
  trivial request before a big backfill.

---

## 3. Symbology & request conventions (v3)

- **Root (`symbol`):**
  - **`SPXW` → all daily/weekly/0DTE SPX** (PM-settled, cash, European). **Use this
    for every 0DTE pull.**
  - **`SPX` → traditional 3rd-Friday monthly only** (AM-settled). Querying `SPX` for
    0DTE returns EMPTY/WRONG data. (Highest-impact mistake.)
  - **`SPY` → SPY equity options** (same Options sub, all tiers).
  - For full-board GEX OI you may want both `SPXW` and `SPX`.
- **`strike` = dollars as a float** — e.g. `strike=5500.00`. (`*` = all.) [v2 used
  integer 1/1000-dollar, e.g. 5500000 — NOT v3.]
- **`expiration` = `YYYYMMDD` or `YYYY-MM-DD`** (`*` = all expirations).
- **`right` = `call` | `put` | `both`** (default `both`). [v2 used `C`/`P`.]
- **`interval` = string**: `1m` for one-minute. Allowed: `tick,10ms,100ms,500ms,1s,
  5s,10s,15s,30s,1m,5m,10m,15m,30m,1h` (default `1s`). [v2 used ms int `ivl=60000`.]
- **Timestamps in responses = ISO ET** `YYYY-MM-DDTHH:mm:ss.SSS`. [v2 `ms_of_day`.]
- **`date=YYYYMMDD`** = single day (overrides start/end). **`start_date`/`end_date`**
  = range.
- **Session window:** defaults `start_time=09:30:00`, `end_time=16:00:00` ET. **SPXW
  trades to 16:15** — set `end_time=16:15:00` (or `rth=false`) to capture the tail.
- **`strike_range=n`** = n strikes above + n below spot + ATM (cheap tight strip).
- **`format` = `csv`(default) | `json` | `ndjson` | `html`.** Use `ndjson` for
  streaming into Polars/Pandas on big pulls.

---

## 4. Endpoints we use (base `http://127.0.0.1:25503`)

| Purpose | Path | Key params | Notes |
|---|---|---|---|
| **NBBO quote** (fills) | `/v3/option/history/quote` | symbol, expiration, interval, strike, right, date | bid/ask + sizes/exch |
| OHLC bars | `/v3/option/history/ohlc` | + interval | o/h/l/c/vol/vwap |
| **Open interest** (walls) | `/v3/option/history/open_interest` | symbol, expiration, strike, right, date | **no interval**; EOD daily; use `expiration=*&strike=*` for full board |
| **IV + greeks** (gamma + synced underlying) | `/v3/option/history/greeks/all` | symbol, expiration, interval, strike, right, date | returns `implied_vol`, `delta/gamma/...`, **`underlying_price` + `underlying_timestamp`**, `iv_error` |
| IV only | `/v3/option/history/implied_volatility` | same | `implied_vol`, `underlying_price` |
| EOD report | `/v3/option/history/eod` | symbol, expiration, start_date, end_date | one row/contract/day |
| list expirations | `/v3/option/list/expirations` | symbol | discovery |
| list strikes | `/v3/option/list/strikes` | symbol, expiration | discovery |
| list roots | `/v3/option/list/symbols` | — | all option roots |
| SPX index level | `/v3/index/history/price` | symbol=SPX, interval | separate Index sub |

**Bulk = wildcards** (no separate bulk endpoint): `strike=*&right=both` pulls a whole
expiry's chain in ONE request; `open_interest` also accepts `expiration=*` for the
whole board.

### Example calls (verbatim-style)
```
# Full 0DTE chain, 1-min IV+gamma+synced underlying (one request):
http://127.0.0.1:25503/v3/option/history/greeks/all?symbol=SPXW&expiration=20260904&strike=*&right=both&date=20260904&interval=1m&end_time=16:15:00

# Full 0DTE chain, 1-min NBBO (fills):
http://127.0.0.1:25503/v3/option/history/quote?symbol=SPXW&expiration=20260904&strike=*&right=both&date=20260904&interval=1m&end_time=16:15:00

# Whole-board OI for GEX walls (all expirations, all strikes, one request):
http://127.0.0.1:25503/v3/option/history/open_interest?symbol=SPXW&expiration=*&strike=*&right=both&date=20260904
```

---

## 5. Pull recipe (per trading day)
1. `greeks/all` — `symbol=SPXW&expiration=<day>&strike=*&right=both&date=<day>&interval=1m&end_time=16:15:00`
   → 1-min IV + gamma + synced `underlying_price` for the full 0DTE strip.
2. `quote` — same params → 1-min NBBO for exact-strike fills (bid/ask).
3. `open_interest` — `symbol=SPXW&expiration=*&strike=*&right=both&date=<day>` (+ `SPX`)
   → full-board EOD OI; combine with gamma from step 1 → GEX walls.
4. Repeat 1–2 with `symbol=SPY` for the oversold→SPY-call backtest.
5. Use `list/expirations` + `list/strikes` once to enumerate/validate the board.

**~4 requests/day/underlying.** Byte volume is small (single-digit GB/year); the real
constraints are the chunking rules and concurrency, not size.

---

## 6. Underlying sync
- `greeks/all` and `implied_volatility` return **`underlying_price` (midpoint at the
  option timestamp) + `underlying_timestamp`**, tick-aligned to each option row. That
  gives option quote + synced SPX level **in one row** — exactly what the level-accept
  exit needs. No cross-vendor alignment.
- Standalone SPX index series = **separate Index subscription** (Value 15-min from
  2023; Standard venue-res from 2022; Pro from 2017). **Likely unnecessary** — the
  embedded underlying covers the backtest. **VERIFY** the embedded underlying ships
  with the Options sub for SPXW without an Index add-on.

---

## 7. Limits & chunking (build the loop before the first big pull)
- **Multi-day requests capped at 1 month AND must pin one `expiration`** (no
  `expiration=*` across a date range). Loop backfills as (one expiration) × (≤1-month
  windows). For 1-min 0DTE you pull one `date` at a time anyway.
- **Sub-minute intervals (tick…30s) = single-day only.** 1m+ can span the ≤1-month
  multi-day window.
- **Concurrency, not per-minute, is the paid-tier limiter:** Value/Standard/Pro ≈
  **2 / 4 / 8** concurrent (Subscriptions page; a legacy page says 1/2/4 worker
  threads — verify empirically). Keep in-flight ≤ `HTTP_CONCURRENCY` (config default
  4). **Over-concurrency shows up as TIMEOUTS, not a clean 429** — add backoff+jitter.
- No documented monthly request quota on paid tiers.
- Don't pull during the **00:00–01:45 ET** daily reset (prior-day data unavailable).

---

## 8. PITFALLS (prioritized)
1. **`SPXW` for 0DTE, never `SPX`** — `SPX` is AM-settled monthlies; wrong root =
   empty data. #1 mistake.
2. **Value tier lacks IV/greeks** — we need IV for gamma → **Standard**. (Agents that
   said "Value suffices for 1-min" meant quotes-only; our use needs IV.)
3. **Extend the session to 16:15** (`end_time`/`rth=false`) or you truncate the SPXW
   settlement tail on expiration day.
4. **Chunk ≤1 month + pin expiration; sub-minute = single-day.**
5. **Use wildcard bulk** (`strike=*&right=both`), not per-strike loops — keeps you
   under concurrency.
6. **Late-day wing gaps are REAL, not missing data** — deep ITM/OTM 0DTE stop being
   quoted in the final hour. Keep `iv_error` and filter; restrict greeks to RTH.
7. **0DTE OI is stale/thin — do NOT use it for walls.** Walls come from later-dated OI
   across the board.
8. **v3 encoding traps:** strike = **dollar float** (not ×1000/1000-cent), timestamps
   = **ISO ET** (not ms_of_day), **no Next-Page** loop, right = `call/put`. Porting v2
   code blindly silently corrupts requests.
9. **One puller per terminal** (2nd connection kicks the 1st); size JVM heap
   (`-Xms4G -Xmx8G`) for big jobs; premarket zero bid/ask is valid.
10. **Confirm tier-per-endpoint before paying** — the one recurring complaint is
    surprise upgrade requirements / no refunds.

## 9. Verify before/at subscribe (open items)
- [ ] Does the embedded `underlying_price` on SPXW greeks/IV ship with **Options
      Standard** alone (no Index add-on)?
- [ ] Confirm Standard's real concurrency (2 vs 4) empirically.
- [ ] Confirm `greeks/all` accepts `expiration=*` (docs show `strike=*`; OI/EOD
      confirm `expiration=*`).
- [ ] Confirm exact SPXW greeks entitlement on Standard.

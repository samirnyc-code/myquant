# Learning Log — lingo, AI process, data craft

**Status:** Living. Every session adds entries when a teachable concept comes up.
Ask "explain X" anytime and it lands here. Newest lessons at the top of each section.

---

## Lesson 5 (2026-07-15) — who actually HAS data: platforms vs vendors vs brokers

Three kinds of players, often confused:
- **Charting platforms (TradingView)** license data IN to display it; they sell you the
  chart, not the feed. No official export API; scraping your own account (tvDatafeed) is
  gray-area and shallow (~5–20k bars). MenthorQ uses TV's *widget* but bought its data
  from a vendor and built its own backend — that's the standard fintech pattern.
- **Data vendors (Databento, Polygon, ThetaData, ORATS)** sell the raw feed/history —
  the only place deep history is truly "for sale."
- **Brokers (IB)** give account holders real data access as a side effect:
  `reqHistoricalData` serves YEARS of intraday bars (rate-limited, not bulk-priced) and
  even expired futures contracts — often the best free deep-history source you already own.

Rule of thumb: before paying anyone, inventory what your broker + existing subs already
expose via API. We found 6mo×1,400 assets (MQ) + years-deep (IB) hiding behind logins we
already had.

## Lesson 4 (2026-07-15) — replication: why we test the same rule on NQ

A result from one market + one year has two live explanations: real mechanism, or lucky
sample. **Replication** on an independent-but-comparable market (NQ: own options chain,
own dealer book, correlated underlying) is the cheapest way to separate them — the price
noise is fresh, but the mechanism (dealer 0DTE hedging) should carry over. A **panel test**
(same rule, many markets) is the stronger version: surviving 4–6 independent panels is
worth more than doubling the years on one market. Related trap: **survivorship/selection** —
if you test 6 markets and only report the ones that worked, you've re-created the
multiple-comparisons problem at the market level. Report the whole panel, always.

Practical constraint lesson: the *levels* exist for 1,400 assets (MenthorQ), but the
*bars* to test against are the scarce resource — intraday history is what costs money
(free tier: our own futures parquets + ~60 days of stock intraday from Yahoo). Match the
test's granularity to the data you own: daily-close tests scale to any ticker for free.

## Lesson 1 (2026-07-15) — "the data behind something": scraping vs APIs

Your question "can u get the actual data behind the vol and cta models?" in correct lingo:
**"Is there a data endpoint for these, or do we have to scrape the rendered page?"**

The hierarchy of how you get data out of a website, best to worst:

1. **API (Application Programming Interface)** — the site offers data on request, by design.
   You call an **endpoint** (a URL that returns data, not a page), e.g.
   `cf.menthorq.io/.../market-status/NYSE`, and get **JSON** (structured text:
   `{"status": "OPEN"}`) or CSV back. Stable, clean, intended.
   - **REST API** = the common style: one URL per resource, you GET/POST to it.
   - **WebSocket (WS)** = a persistent two-way connection; the server *pushes* updates
     (tickers, live GEX) without you re-asking. What "live" dashboards usually use.
   - **XHR / fetch** = the browser-side calls a page makes to endpoints while you look
     at it. Watching those in DevTools ("the Network tab") is how you discover an
     **undocumented / internal API** — often the jackpot: MenthorQ's dashboard calls
     `clickhouse-api` endpoints we can hit directly.
2. **Scraping the DOM** — no endpoint, but the numbers are in the page's HTML (the
   **DOM** = the page's element tree). We drive a **headless browser** (Playwright —
   a real Chrome without a window) and read the rendered text/tables. Works, but
   fragile: a site redesign breaks your **selectors** (the addresses of elements).
   - Gotcha we hit tonight: **virtualized tables** render only the rows on screen
     (for speed), so a naive text-grab misses off-screen strikes — you must scroll
     programmatically and stitch.
3. **Pixels** — the data exists only as an image (MenthorQ's CTA charts are
   **server-side pre-rendered PNGs** stored on **S3**, Amazon's file storage, behind
   **presigned URLs** — temporary tokenized links). Then your options are OCR
   (reading numbers out of the image — last resort) or finding routes 1–2 elsewhere.

Related terms from tonight: **session / auth state** (the cookies proving you're
logged in — we save them to a file and reuse them, so no re-login); **backfill**
(fetching history in bulk vs **accruing** it forward day by day); **rate limit /
quota** (how much the service lets you pull before throttling you).

## Lesson 2 (2026-07-15) — prompt engineering, live example: QUIN

Getting parseable data out of an LLM (QUIN, or me) is **prompt engineering**. What
made the QUIN queries work:

1. **Specify the output format explicitly** — "as a plain table, one row per day,
   columns: Date, Call Resistance, Put Support, HVL". Without it the model chooses
   prose, and every answer parses differently.
2. **Constrain scope** — a date range and an exact column list beats "show me the
   history". Smaller ask = fewer degrees of freedom = consistent answers.
3. **Expect nondeterminism** — same prompt, different runs, different formats
   (QUIN added `$` signs on run 2 and skipped the GEX table on run 3). Robust
   pipelines parse defensively AND have a follow-up prompt ready ("list the top 10
   GEX strikes as a two-column table") when a section is missing.
4. **Verify against ground truth** — we cross-check QUIN's numbers against the
   dashboard tiles daily (`mq_logger`). Trust is earned per-source, continuously.
   In AI lingo: guard against **hallucination** with an independent check.

## Lesson 3 (2026-07-15) — AI process optimization: the agent loop we run

The system running your research tonight is an **agent loop**: an AI that plans →
acts (runs code, browses, trades) → observes results → re-plans, autonomously.
Key patterns in use, with their names:

- **Background tasks / async orchestration** — long jobs (backfill, crawls) run in
  parallel; the agent gets woken by **notifications** instead of waiting idle.
- **Pipelines** — data flows through staged scripts (harvest → parse → archive →
  dashboard), each stage restartable. Failures stay contained to a stage.
- **Idempotency** — safe to re-run: the backfill dedupes on (date, symbol), so
  running it twice can't double-write. Design goal for every data job.
- **Audit trails** — every order, decision, and mark is logged with provenance
  (which model, which fill rule). Enables debugging AND honest research.
- **Hypothesis-driven mining** — "data mining" done right: form a specific claim
  ("VIX filter improves BPS"), test out-of-sample (**walk-forward**), accept the
  kill. The graveyard of rejected ideas is what makes the survivors credible —
  mining without this discipline finds only **overfitting** (patterns that fit the
  past by chance and die live).

---

*Format note: one lesson block per concept-cluster, dated, tied to the real work
where it came up — abstract definitions don't stick; "the thing we did tonight" does.*

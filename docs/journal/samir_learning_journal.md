# Samir's Learning Journal
**Last Updated:** June 7, 2026

---

## Tag 1 — June 1, 2026
### Developer Setup (Zero to Repo in One Day)

| Concept | What it is |
|---------|------------|
| **VS Code** | Code editor (free, by Microsoft) |
| **Git** | Local tool for version control — tracks every change to code |
| **GitHub** | Cloud hosting for git repos — your code is backed up online |
| **Repository (Repo)** | A folder/project managed by git |
| **Clone** | Load a copy of a GitHub repo locally onto your computer |
| **Commit** | A saved change in the git system |
| **Command Palette** | Cmd+Shift+P — search bar for all VS Code commands |
| **Extension** | Plugin that extends VS Code |
| **GitLens** | VS Code extension — visualizes your full git history (see Tag 2) |
| **Claude Code** | Anthropic's AI integrated directly into VS Code |
| **Settings Sync** | VS Code settings synced across devices |

### Installed and configured
- VS Code, Git, GitHub account (samirnyc-code)
- GitHub connected to VS Code
- GitLens, C# Dev Kit, Claude Code installed
- First GitHub repo created (myquant — Private)
- Repo cloned locally in VS Code

### Mac shortcuts
| Shortcut | Function |
|----------|----------|
| `Cmd+Shift+P` | Open Command Palette |
| `Cmd+V` | Paste |
| `Cmd+C` | Copy |

### Mac to PC workflow
```
Mac → (Cmd+S save) → Git Commit → Push → GitHub
                                            ↓
PC  ← Git Pull ←────────────────────── GitHub
```

---

## Tag 2 — June 2, 2026
### Git Workflow, GitLens, and Hard Lessons

#### Concepts learned

| Concept | What it is |
|---------|------------|
| **GitLens** | VS Code extension that shows the full git commit graph — every commit, who made it, when, what changed. Also shows inline "blame" — which commit last changed each line of code. |
| **Commit graph** | The timeline of every change ever made to the repo. Never shrinks. Every commit is permanent. |
| **git add .** | Stages all changed files — tells git "include everything in the next commit" |
| **git rm** | Removes a file from git tracking. The deletion itself becomes a commit in the graph. |
| **git pull** | Syncs remote changes to your local copy |
| **git pull --rebase** | Same as pull but used when local and remote have diverged — git replays your local commits on top of the remote state instead of creating a merge conflict |
| **git push** | Sends your local commits to GitHub |
| **unzip -d** | Extracts a zip file to a specific folder location |
| **.gitignore** | A file in the repo root that tells git to permanently ignore specific files. Once a file is in .gitignore, git never tracks it again. |
| **.DS_Store** | A hidden Mac system file created automatically in every folder. Useless in a repo. Add to .gitignore so it never appears again. |
| **Remote vs local** | GitHub (remote) and your computer (local) are two separate states. Git keeps them in sync. When they diverge, git blocks you and tells you exactly why. |

#### Key mental models

**Git never deletes history.**
Every state your repo has ever been in is recoverable. When you delete a file with `git rm`, the deletion is recorded as a commit — the file is gone from the current state but permanently visible in the graph. You can always go back. This means mistakes are always recoverable. Commit frequently.

**Local and remote are two separate states.**
When you delete files on GitHub web without pulling locally first, your local copy is behind. Git will reject your next push with "fetch first." Fix: `git pull --rebase` then `git push`.

**Dragging a zip into a repo creates wrong folder nesting.**
If you drag a zip file (not its extracted contents) into a repo folder, git tracks the zip and the extracted folder has an extra level. Always extract first, then move the files.

**The .gitignore lesson.**
`.DS_Store` showed up in multiple commits today because it wasn't ignored. Fix once with:
```
echo ".DS_Store" >> .gitignore
git add .gitignore
git commit -m "add gitignore"
git push
```
Never appears again.

#### Commands used today
```bash
git pull --rebase        # sync when remote is ahead of local
git rm <file>            # remove file from git tracking
git rm -r <folder>       # remove folder from git tracking
git add .                # stage all changes
git commit -m "message"  # commit with message
git push                 # push to GitHub
ls                       # list files in current directory
mkdir -p a/b/c           # create nested folders in one command
mv <source> <dest>       # move file or folder
unzip file.zip -d /path  # extract zip to specific location
cp -r <source> <dest>    # copy folder recursively
```

---

## Tag 3 — June 3, 2026
### First Python Data App — Streamlit Candlestick Viewer

#### What we built
A fully working Streamlit app (`app.py`) that reads 48 million rows of raw ESM6 tick data, filters to Regular Trading Hours, aggregates into 5-minute OHLCV bars, and displays an interactive candlestick chart + table.

#### Concepts learned

| Concept | What it is |
|---------|------------|
| **Tick data** | Every individual trade printed to the tape. Each row = one transaction. The raw form of market data before any aggregation. |
| **OHLCV bar** | A time-bucketed summary of tick data: Open (first price), High (max), Low (min), Close (last price), Volume (sum). |
| **RTH** | Regular Trading Hours. For ES futures: 08:30–15:15 CT. Everything outside is pre/post market and excluded from most analysis. |
| **pandas** | The core Python data library. Think Excel pivot tables and formulas but in code — handles millions of rows in memory. |
| **DataFrame** | pandas' main data structure. Like a spreadsheet table: rows and columns, each column has a type (float, string, datetime). |
| **resample()** | pandas method that groups time-series data into fixed buckets. `df.resample("5min")` groups ticks into 5-minute windows. |
| **chunked reading** | Reading a huge file in smaller pieces instead of all at once. Used `chunksize=500_000` to read 48M rows without running out of memory. |
| **@st.cache_data** | Streamlit decorator that saves the result of a function after the first run. The 48M-row load only happens once — every page interaction after is instant. |
| **plotly** | Python charting library. Used `go.Candlestick` for the interactive chart — hover, zoom, pan all built in. |
| **Streamlit** | Python library that turns a script into a web app. No HTML/CSS/JavaScript needed. |
| **virtual environment (.venv)** | An isolated Python installation for one project. Keeps dependencies separate so different projects don't conflict. |
| **requirements.txt** | A file listing all Python packages a project needs. Anyone can recreate your environment with `pip install -r requirements.txt`. |

#### Key mental models

**Tick data is huge — filter early, parse late.**
The file had 48M rows. Reading and parsing all of them would be slow and memory-heavy. The app filters to RTH using a fast string comparison *before* doing any datetime parsing — so only ~28% of rows ever get parsed. Always push filters as early in the pipeline as possible.

**Cache expensive operations at the boundary.**
The slow part (reading 48M rows, building bars) happens once and the result is cached. After that, changing the date selector is instant because you're just filtering an already-built DataFrame. Identify what's slow, cache it, keep everything downstream fast.

**Large files never go in git.**
The tick file is ~3GB. GitHub has a 100MB file limit. Added `data/raw/ESM6.CME_BarData.txt` to `.gitignore` — code is versioned, data is not.

**48M rows is still only 65 calendar days.**
ES futures trades nearly 24 hours a day with ~860K ticks/day. File size tells you nothing about the time range — check the first and last row.

#### App architecture
```
ESM6.CME_BarData.txt (48M rows, tick data)
        ↓
  pd.read_csv (chunked, 500k rows at a time)
        ↓
  RTH string filter (08:30 ≤ Time < 15:15)
        ↓
  pd.to_datetime (parse only filtered rows)
        ↓
  df.resample("5min").agg(OHLCV)
        ↓
  @st.cache_data (cached after first run)
        ↓
  Streamlit UI: date selector → metrics → candlestick → table
```

#### Commands used today
```bash
python3 -m venv .venv                        # create virtual environment
.venv/bin/pip install -r requirements.txt    # install dependencies
.venv/bin/streamlit run app.py               # launch the app
open -a "Google Chrome" http://localhost:8501 # open in Chrome
ngrok http 8501                              # share app over the internet
```

---

## Tag 4 — June 4, 2026
### Bar Validation Module — Comparing Two Data Sources

#### What we built
A full data validation tab inside the Streamlit app that compares SC-built 5-minute bars (from raw tick data) against pre-built 5-minute bars exported from NinjaTrader. The goal: confirm the two sources agree before trusting either for backtesting.

#### The core alignment problem
NT exports bar data with **close times** in **Berlin (CEST)** timezone. SC builds bars with **open times** in **CT**. To compare apples to apples: subtract 7 hours (timezone) and 5 minutes (close→open) from every NT timestamp.

| Source | Bar label | Timezone | Example |
|--------|-----------|----------|---------|
| SC | Open time | CT (CDT) | 08:30 CT |
| NT | Close time | Berlin (CEST) | 15:35 Berlin |
| After conversion | Open time | CT | 08:30 CT ✓ |

#### Key findings from the comparison
- **Open** has the most mismatches (3.8%) — both feeds capture a different "first print" at the bar boundary
- **High/Low** are nearly perfect (<0.1%) — extreme prices are boundary-insensitive
- **Close** has moderate mismatches (2.5%) — same boundary issue as Open but less severe
- **Volume** often differs — expected: SC sums raw tick volumes, NT records broker-feed volume
- **Mismatch pattern**: spikes at 08:30 (opening auction) and 14:45–15:10 (end of session) — normal. Mid-session is clean.

#### Why summary OHLC % < individual field rates
The summary "OHLC Exact Match" counts a bar as a mismatch if **any** of the four fields differ. A bar where only Open is wrong still counts as one full mismatch. The individual field rates (Open 96%, High 99.9%, Low 99.97%, Close 97.5%) are each measuring that field in isolation. This is correct and expected — the summary is the more conservative and useful number.

#### Concepts learned

| Concept | What it is |
|---------|------------|
| **Timezone conversion** | `dt.tz_localize("Europe/Berlin").dt.tz_convert("America/Chicago")` — attaches a timezone, then converts. Use zoneinfo-backed string names for DST correctness. |
| **exchange-calendars** | Python package with full market calendars back to the 1990s. `xcals.get_calendar("XNYS")` gives the NYSE calendar including all holidays. Free, no API key, works offline. |
| **NYSE vs CME calendar** | CME (CMES) considers Memorial Day a live session (Globex never closes). NYSE (XNYS) marks it as a holiday. For ES futures RTH strategy purposes, NYSE calendar is the right filter. |
| **Outer join** | `df1.join(df2, how="outer")` keeps all rows from both sides. Rows in one but not the other get NaN for the missing columns — used to detect bars present in SC but not NT and vice versa. |
| **Day-separator rows** | NT exports `-----` divider lines between each trading day. pandas read_csv chokes on these. Fix: read the file line-by-line in Python, skip non-digit rows, then build a DataFrame. |
| **Bar boundary sensitivity** | Open and Close are "boundary bars" — the exact first/last tick within a 5-minute window. Under fast price movement, two feeds with 1ms latency difference capture different ticks. High/Low are the full range and are unaffected. |

#### Module architecture
```
data_loader.py
  load_sc_bars()      ← tick data → 5-min bars (existing)
  load_nt_bars()      ← NT txt → timezone convert → open time
  get_market_holidays() ← NYSE calendar via exchange-calendars

validation.py
  build_comparison()  ← outer join, compute Δ ticks per field
  show_validation_tab()
    ├── 4 filter toggles (holidays, first bar, late session, volume)
    ├── Summary metrics strip
    ├── Field breakdown table (Total, Exact, Mismatch, Match%, Min/Max/Mean Δ)
    ├── Mismatch Table tab
    ├── Time of Day tab (bar chart + rate % line)
    ├── By Date tab (bar chart per trading day)
    └── Delta Distribution tab (value counts tables)
```

---

## Tag 5 — June 4, 2026
### Economic Event Filter — FRED API, FOMC Hardcoding, PPI Decision

#### What we built
An economic event filter inside the Bar Validation tab. Allows excluding bars near FOMC, NFP, and CPI announcements to test whether mismatch rates are driven by high-impact news events (hypothesis: fast price movement amplifies feed-latency boundary differences).

Two filter modes:
- **Skip full day** — removes all RTH bars on event dates. Most useful for NFP/CPI since they release at 7:30 CT, before RTH opens.
- **Window ±N minutes** — removes bars within N minutes of the announcement time. Useful for FOMC (1:00 PM CT, inside RTH). A window under 60 min has no effect on RTH bars for NFP/CPI since those release 60+ min before the open.

#### FOMC — hardcoded, not API
FOMC dates are hardcoded 2015–2026. Reason: there is no reliable free API for FOMC dates. The Fed publishes them on federalreserve.gov annually. 2026 dates were confirmed by fetching the page directly on 2026-06-04.

The emergency cuts in 2020 (Mar 3 and Mar 15) are included alongside the scheduled meetings.

#### FRED API — NFP and CPI
FRED (Federal Reserve Economic Data) provides a free REST API with no rate limit for low-volume use. Release dates for any economic series can be fetched by release ID.

| Event | Release ID | Series |
|-------|-----------|--------|
| NFP | 50 | Employment Situation (BLS) |
| CPI | 10 | Consumer Price Index (BLS) |

Key detail: FRED returns **multiple dates per month** for some releases — the initial release date plus revision dates. Only the **first date per calendar month** is the market-moving event. Fix: deduplicate by `YYYY-MM`, keeping earliest.

```python
seen = set()
result = []
for d in raw_dates:
    ym = d[:7]          # "YYYY-MM"
    if ym not in seen:
        seen.add(ym)
        result.append(d)
```

#### PPI — added then removed
PPI was initially included (release_id=31). Removed because it is not in scope for the current analysis — the hypothesis is about high-impact events that move ES significantly, and PPI is secondary to NFP/CPI. Keeping the scope tight.

#### By Date chart — event lines
The By Date bar chart received colored dashed vertical lines marking event dates, with a legend. Color coding: FOMC orange (`#ff6b35`), NFP teal (`#4ecdc4`), CPI blue (`#45b7d1`).

#### Concepts learned

| Concept | What it is |
|---------|------------|
| **FRED API** | Free REST API from the St. Louis Fed. No rate limit for low-volume use. Register at fred.stlouisfed.org for a free key. Endpoint: `/fred/release/dates?release_id=N`. |
| **FRED revision dates** | FRED stores every release date including data revisions, not just the initial publication. Always deduplicate to first-per-month when you want the market event date. |
| **`st.secrets`** | Streamlit's built-in secrets manager. Reads `.streamlit/secrets.toml` (gitignored). Access via `st.secrets.get("KEY")`. Safe pattern for API keys in Streamlit apps. |
| **Graceful degradation** | FRED-dependent checkboxes are `disabled=True` when no API key is configured. App stays functional — FOMC works without a key. |

---

## Tag 6 — June 4, 2026 (evening)
### UI Polish — Filters, Navigation, Shading, Defaults

#### What we built
A full UI polish pass on the Streamlit app. No new analysis features — all changes are about making the tool faster to use and cleaner to read.

#### Single Filters expander
All filter controls (Display, Session Boundaries, Day of Week, Economic Events) consolidated into one `⚙️ Filters` expander. Previously each was its own expander, which made the page tall and fragmented. Now one click opens/closes all controls. Sections separated by `st.divider()` since Streamlit doesn't allow nested expanders.

#### Save as Default
"💾 Save as Default" button at the bottom of the Filters panel writes all current filter values to `filter_defaults.json`. On next app load, those values are injected into `st.session_state` before any widgets are created, so the widgets render with saved defaults. The pattern:

```python
# Inject defaults on first load only
if "vt_initialized" not in st.session_state:
    for k, v in _load_filter_defaults().items():
        st.session_state.setdefault(k, v)
    st.session_state["vt_initialized"] = True

# Widget uses key= — Streamlit picks up session_state value automatically
excl_holidays = st.checkbox("...", key="f_excl_holidays", value=True)
```

The `value=` parameter is only used when the key is not yet in session state. Once the key exists, `value=` is ignored. This means defaults loaded from file are honoured on first render.

#### Commentary toggle
`Show commentary` checkbox in the Filters panel. When off, all `_info()` and `_commentary()` calls are skipped, removing the blue info boxes and text paragraphs. Layout tightens automatically — no special rearrangement needed.

#### Excluded zone shading — the hard part
`add_vrect` and `add_shape` are unreliable on Plotly categorical x-axes. Multiple approaches failed:
- `add_vrect` with string category labels — ignored silently
- `add_shape` with integer category indices — not rendered
- Secondary y-axis bar trace — rendered as tall grey bars, looked terrible

**Solution that worked:** overlay bar traces with explicit y-axis range. Add a grey bar trace first (y = very large number), then add the data bars on top, then set an explicit y-axis range that clips the grey bars at the chart height. `barmode="overlay"` ensures data bars render on top. `categoryorder="category ascending"` ensures time strings sort chronologically regardless of trace insertion order.

For the datetime (by-date) chart, the same overlay approach works. For the candlestick chart, `add_vrect` works correctly on a continuous time axis — offset x0/x1 by ±2.5 minutes (half a 5-min bar width) so the shaded region covers the full bar, not just its center.

#### Candlestick bar numbers
Positioned at `yref="y"` (data coordinates) with `yanchor="top"` and `yshift=-6` pixels — sits just below each bar's low. Font size 12 to match axis tick labels. Every 3rd bar starting from 1, plus the last bar always labeled regardless of step position.

#### Prev/Next navigation
`st.session_state` used to share the current date index between the buttons and the selectbox. Button click modifies `st.session_state.bar_viewer_idx`; selectbox reads it on the next render. Sync back: `st.session_state.bar_viewer_idx = dates.index(selected_date)` after the selectbox so direct dropdown changes are captured.

#### Concepts learned

| Concept | What it is |
|---------|------------|
| **Plotly categorical shading** | `add_vrect`/`add_shape` fail silently on categorical axes. Reliable workaround: overlay bar trace with clipped y-range. |
| **Streamlit widget defaults** | `value=` is only used when the widget key is not yet in `st.session_state`. Pre-populate session state before widget creation to control initial values. |
| **`barmode="overlay"`** | Plotly bar traces at the same x position render on top of each other. Add background trace first (low z-order), data trace second. Clip with explicit `yaxis.range`. |
| **`header { visibility: hidden }` danger** | Hides the Streamlit header including the Rerun button and sidebar toggle. Use `#MainMenu { visibility: hidden }` to hide only the hamburger menu. |

---

## Tag 7 — June 6–7, 2026
### Trade Simulation — Sweeps, Multileg, and Streamlit Gotchas

#### What we built
- T1×T2 2D sweep: heatmap + ranked table to find the optimal T1/T2 combo for 2-leg trades
- Stop multiplier sweep: simulate 10 stop sizes (0.25×–2.00× of the original signal stop)
- Single-leg BE Stop mode: T1 moves stop to break-even, full position exits at T2
- Mode-switching fix: replaced `st.button` pattern with `st.radio` for trade mode selection
- Sweep table highlighting: best value per metric column in heatmap green; T1/T2 of best combo also highlighted

#### The `st.button` mode-switching trap

This burned us. The original code used three buttons ("Single Leg", "2-Leg", "3-Leg") to switch trade mode, storing the choice in session state. It appeared to work — until we noticed that changing any other widget (slippage, target R, etc.) caused the mode to silently reset back to Single Leg.

**Why:** `st.button` only returns `True` in the single Streamlit rerun caused by clicking that button. The next rerun — triggered by any other widget — all buttons return `False`. If any code path checked button state to set mode, it ran False on that rerun and overwrote the saved state.

**Fix:** `st.radio("Trade Mode", ["Single Leg", "2-Leg"], key="ba_trade_mode")`. Streamlit manages `ba_trade_mode` in session state natively. The value persists across all reruns, regardless of what triggered the rerun. No `st.rerun()` needed.

**Rule:** Use `st.button` for one-shot actions (run sweep, save defaults). Use `st.radio` or `st.selectbox` for anything that must persist as a selection.

#### The `Styler.apply` kwargs trap

We wanted to pass a threshold to a highlighting function:

```python
# WRONG — pandas passes "kwargs" as a literal keyword arg name
styled.apply(_hl_max, kwargs={"thr": thr}, subset=[col])

# RIGHT — pass extra args directly as keyword args
styled.apply(_hl_max, thr=thr, subset=[col])
```

`Styler.apply(func, **kwargs)` passes any extra keyword arguments directly to `func`. Wrapping them in a `kwargs={}` dict doesn't unpack them — pandas just tries to call `func(series, kwargs={"thr": thr})`, which fails because `_hl_max` has no `kwargs` parameter.

#### Stop sweep — targets auto-scale with the stop

When sweeping stop sizes, the question was: does the target also change, or stay fixed? Answer: it changes automatically, because of how the simulator works.

The target price is computed as:
```
risk_pts = abs(actual_entry - actual_stop)   # uses the modified stop
target_price = actual_entry + target_r * risk_pts
```

So if you use a 0.5× stop, `risk_pts` is half as large, and a 2R target is placed at half the original distance. The **R ratio is preserved** relative to the new stop. You're not changing the R — you're changing the dollar size of 1R. This is the correct behavior for sweep analysis: each row tests a different risk/reward dollar amount at the same R multiple.

#### Validation flags instead of mode overrides

When T1 ≥ T2 in the 2-leg column, the original code set `_is_ml = False` inside the column block. Bug: on the next Streamlit rerun, `ba_trade_mode` was still "2-Leg" so `_is_ml` reset to True, then T1≥T2 fired again — flickering, and the column disappeared.

**Fix:** introduce a `_ml_invalid = False` flag initialized before the columns block. Set it to `True` only when T1≥T2. The column stays visible (the user can see and fix it). The derive block reads:

```python
if _is_ml and not _ml_invalid:   # valid 2-leg path
elif _sl_be_deriv:               # single-leg BE mode
else:                            # single-leg AIAO
```

The flag pattern separates "what did the user select" from "is that selection currently valid." Never override the user's selection — show a warning and degrade gracefully.

#### Win rate definition matters

The Setup Analysis table was showing win rates around 11% when the real number was closer to 40%. Root cause: the win filter was `ExitReason.str.contains("Target")`, which missed `"T1+BE"` exits (T1 hits, stop moves to break-even, then price hits EOD or BE stop).

`T1+BE` is a win — you protected your capital and had a partial winner. The contains-based filter only caught `"Target"` and `"T1+Target"`. Fix: add an explicit OR condition.

**Broader lesson:** define "win" precisely before you write any filter. For this strategy: a win is any trade that hit at least one profit target. Exits at stop, EOD, or BE (no T1) are losses.

#### Concepts learned

| Concept | What it is |
|---------|------------|
| **`st.radio` vs `st.button`** | `st.radio` is a persistent selection — value lives in session state across all reruns. `st.button` is a one-shot event — True only in the rerun it caused. Use radio for mode switches, button for actions. |
| **`Styler.apply` extra args** | Pass extra args directly as keyword args (`thr=thr`), not wrapped in `kwargs={}`. The Styler unpacks them into the function call. |
| **Risk pts auto-scaling** | In the ES simulator, `risk_pts = entry - stop`. Modifying the stop before simulation automatically scales both the target price and the dollar value of 1R. Target R ratio is preserved. |
| **`_ml_invalid` flag pattern** | For input validation in multi-column UIs: use a flag, not a mode override. Keep the column visible, degrade the simulation path, show a warning. Don't hide the widget the user needs to fix. |
| **matplotlib required for `background_gradient`** | `pandas Styler.background_gradient` requires matplotlib as a backend. It's not installed by default in a fresh venv. `pip install matplotlib` if you see `ImportError: Import matplotlib failed`. |


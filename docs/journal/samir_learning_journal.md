# Samir's Learning Journal
**Last Updated:** June 4, 2026

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


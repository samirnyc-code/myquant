# myquant — Collaborator Onboarding
**For:** Thomas  
**Last Updated:** July 7, 2026

---

## One-time machine setup (do this before anything else)

### 1. Install Git
Download from [git-scm.com](https://git-scm.com). During install, check **"Add Git to PATH"**.

### 2. Install Python 3
You need Python 3.11 or 3.12. Download from [python.org](https://python.org). During install, check **"Add Python to PATH"**. Check what you have with `python --version`.

### 3. Install VS Code (recommended)
Download from [code.visualstudio.com](https://code.visualstudio.com). Free. Install the **GitLens** extension inside VS Code (Extensions panel → search GitLens).

---

## Step 1 — Clone the repo
```
git clone https://github.com/samirnyc-code/myquant.git
cd myquant
```
(If you already cloned it, just `git pull` to get the latest.)

## Step 2 — Set up the Python environment

Open a terminal in the `myquant` folder, then run:

```bash
# Create a virtual environment
python -m venv .venv

# Activate it (Windows)
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```
(On Mac/Linux, activate with `source .venv/bin/activate` instead.)

Your prompt will show `(.venv)` when the environment is active. You must activate it every time you open a new terminal.

## Step 3 — Run the app

```bash
streamlit run app.py
```

Open **http://localhost:8501** in your browser when you see:
```
  Local URL: http://localhost:8501
```

## Step 4 — Get the price data

The app needs Massive price data to run signals against. The roll schedule and offsets are already done — nothing for you to configure. `rolls.json` is committed to the repo, so you have the exact same roll dates and offsets already entered. The Massive API key needed to download data is also already in the code — no setup needed there either.

The actual price data (bars + ticks) is too large to put in git (tens of GB), so you have two options:

- **Option A — get a copy from Samir directly.** He'll send you the `data/` folder (drive/USB/etc). Drop it into the project folder so it sits next to `app.py`, `massive.py`, etc. Fast — no downloading or waiting.
- **Option B — download it yourself in the app.** Open the **📂 Massive** tab → **📋 Roll Schedule & Downloads** → check the contracts you want → **Download Selected**. Pulls fresh data using the built-in API key. Automatic, but downloading + processing all 20 contracts and building the tick cache takes multiple hours — only do this if you don't have a copy of the `data/` folder.

Either way, once the data is in place:
- The **📂 Massive** tab shows contracts as already downloaded (✅).
- Click **🔗 Build Continuous Series** to stitch them into one continuous price history (only needed once, or after adding new contracts).
- Click **🔨 Build / Update Tick Cache** to build the tick-level cache used for precise trade simulation (also only needed once).

## Step 5 — Using the app

- **📊 Bar Viewer** — browse the price chart day by day.
- **📈 Bar Analysis** — this is where you'll spend most of your time. Upload a signals file under **📊 MC Signals** (or **🔁 RevFTSignals** for a second signal set), then adjust parameters (target R, stops, slippage, etc.) and the app simulates every trade automatically.
- **📊 Portfolio** — combine and compare multiple parameter configs.

You shouldn't need to touch any code — everything is adjustable through the app's UI.

## Alternative workflow — Claude Code instead of the app (no Streamlit)

You don't have to use the Streamlit app at all. The app is just a UI layer —
the actual simulation engine is plain Python (`simulation_engine.py` +
`massive.py`), and every research script in `scripts/` calls it directly. If
you prefer, you can drive everything through **Claude Code** in VS Code and
skip the app entirely.

What you need for this route:

1. **Steps 1–2 above** (clone + Python environment). Skip Step 3 — you never
   need `streamlit run app.py`.
2. **The `data/` folder from Samir** (Option A in Step 4). This is strongly
   recommended over downloading fresh: the download/stitch/cache-build steps
   live in the app UI, so without the app they'd have to be driven from
   `massive.py` by hand. Samir's copy already includes the built
   `_continuous.parquet` and the tick cache — nothing to build.
3. **The `saved_signals/` folder** — the signal parquets
   (`ba_signals_revft.parquet` etc.) are **not in git**, so make sure they're
   included with the data copy. It sits next to `app.py` in the project root.
4. **Claude Code** ([claude.com/claude-code](https://claude.com/claude-code)) —
   install the VS Code extension or CLI, then open the `myquant` folder.

From there you can ask things like *"run a 1R sim on the RevFT signals with $5
commission"* and Claude Code will write and run a script the same way the
existing ones in `scripts/` work (see `scripts/fade_revft_test.py` for the
pattern). The repo's `CLAUDE.md` will automatically steer its sessions —
including reading `docs/living/handoff.md` first.

Two caveats:

- **Tick sims are slow and RAM-hungry.** Scripts replay ticks day-by-day
  specifically to bound memory — keep that pattern. A full multi-year sweep
  can take a long time depending on your hardware.
- **House rules still apply** (see Rules below): no code until agreed, pull
  before push, read the four docs in Step 6 first. Since we'll both be
  updating `docs/living/handoff.md` and the research-note number ledger,
  always claim your note number in the same edit that adds your note.

---

## Step 6 — Read these first, in this order
1. `docs/README.md` — what every file is
2. `docs/living/handoff.md` — current state of the project
3. `docs/living/roadmap.md` — what gets built and in what order
4. `docs/living/open_questions.md` — unresolved decisions

Do not touch anything until you have read all four.

---

## Daily workflow
```
git pull                  # always pull before starting work
# do your work
git add .
git commit -m "category: what you did"
git push
```

---

## Commit message format
```
docs: update handoff with X
journal: add learnings from session
architecture: update bar_validation spec
fix: correct typo in roadmap
```

Always `category: description`. No exceptions.

---

## Rules

1. Never push directly without pulling first
2. Never delete a file without discussing it
3. Never duplicate information across files — one source of truth per topic
4. Every new doc gets added to `docs/README.md`
5. `docs/living/handoff.md` gets updated at the end of every session
6. Never modify `docs/reference/` files without discussion — these are stable
7. No code gets written until it is explicitly agreed on

---

## If something breaks
```
git status        # see what changed
git diff          # see exact changes
git log           # see recent commits
```

Don't panic. Nothing is ever deleted permanently. Every state is recoverable.

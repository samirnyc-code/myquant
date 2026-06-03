# myquant — Collaborator Onboarding
**For:** Thomas  
**Last Updated:** June 3, 2026

---

## One-time machine setup (do this before anything else)

### 1. Install Git
Download from [git-scm.com](https://git-scm.com). During install, check **"Add Git to PATH"**.

### 2. Install Python 3
Download from [python.org](https://python.org). During install, check **"Add Python to PATH"**.

### 3. Install VS Code (recommended)
Download from [code.visualstudio.com](https://code.visualstudio.com). Free. Install the **GitLens** extension inside VS Code (Extensions panel → search GitLens).

---

## Step 1 — Clone the repo
```
git clone https://github.com/samirnyc-code/myquant.git
cd myquant
```

## Step 2 — Get the data file

The tick data file (`ESM6.CME_BarData.txt`) is ~3GB and is intentionally excluded from git. Samir will send it via Dropbox or Google Drive.

Once you have it, place it here — create the folder if it doesn't exist:
```
myquant/
└── data/
    └── raw/
        └── ESM6.CME_BarData.txt   ← goes here
```

---

## Step 3 — Set up the Python environment

Open a terminal in the `myquant` folder, then run:

```bash
# Create a virtual environment
python -m venv .venv

# Activate it (Windows)
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

Your prompt will show `(.venv)` when the environment is active. You must activate it every time you open a new terminal.

---

## Step 4 — Run the app

```bash
streamlit run app.py
```

The first run takes a few minutes — it reads and processes the full 48M-row tick file and caches the result. Every run after that is instant.

Open **http://localhost:8501** in Chrome when you see:
```
  Local URL: http://localhost:8501
```

---

## Step 5 — Read these first, in this order
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

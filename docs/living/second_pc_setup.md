# myquant — Second PC Setup + Regime Engine Kickoff

**Written:** 2026-07-13 (S71→S72 transition, main PC)
**For:** the second PC (GitHub account `tdeutschmann-byte`, VS Code + extensions already installed)
**Goal:** get a working clone with data, then start the NEW multi-state regime engine on a branch.

> This file lives in the repo (`docs/living/second_pc_setup.md`). Before cloning, read it
> on GitHub: <https://github.com/samirnyc-code/myquant/blob/main/docs/living/second_pc_setup.md>
> The market data does NOT come with the clone — it's staged on Google Drive
> (`G:\My Drive\myquant_transfer\`), see step 1.3.

---

## Part 1 — One-time machine setup

### 1.1 Verify Git + GitHub account

Open a terminal (PowerShell) and check Git is installed:

```powershell
git --version
```

If missing, install from https://git-scm.com/download/win (defaults are fine), then reopen the terminal.

Make sure the **browser** on this PC is signed into GitHub as **tdeutschmann-byte**
(github.com → avatar top-right → "Signed in as ..."). The account is already a
collaborator on the repo — nothing to accept. The first `git push` will pop up a
browser sign-in; whatever account the browser holds at that moment gets cached by
Windows for all future pushes, so get this right BEFORE the first push.

> If the wrong account ever gets cached: Windows **Credential Manager → Windows
> Credentials** → delete `git:https://github.com`, then push again to re-authenticate.

### 1.2 Clone the repo

```powershell
cd C:\Users\<you>          # or wherever you keep code
git clone https://github.com/samirnyc-code/myquant.git
cd myquant
git config user.name  "tdeutschmann-byte"
git config user.email "<tdeutschmann-byte's GitHub email>"
```

Use the email registered to the tdeutschmann-byte account (or its GitHub noreply
address, under GitHub → Settings → Emails) so commits attribute correctly.

### 1.3 Copy the data in (NOT in git — comes from Google Drive)

`data/bars/` and `data/ticks_continuous/` are **gitignored** (licensed market data,
public repo). They were staged on Drive at `G:\My Drive\myquant_transfer\`.
Wait for Drive to finish syncing (system tray icon idle), then:

```powershell
# from inside the myquant clone
New-Item -ItemType Directory -Force data\bars, data\ticks_continuous
Copy-Item "G:\My Drive\myquant_transfer\data\bars\*"             data\bars\
Copy-Item "G:\My Drive\myquant_transfer\data\ticks_continuous\*" data\ticks_continuous\
```

Adjust `G:` if Drive mounts under a different letter on this PC. Expected result:

| Folder | Contents | Why needed |
|---|---|---|
| `data/bars/` | `_continuous.parquet` (5-min ES, 2.0 MB), `_continuous_1m.parquet` (8.1 MB), `_continuous_15m.parquet` (0.9 MB) | the bars every Brooks script loads |
| `data/ticks_continuous/` | 1,270 daily parquets `YYYY-MM-DD.parquet` (~3.4 GB), 2021-06-18 → 2026-07-09 | OB (outside-bar) first-break tick-order decomposition in the structure engine — **days without ticks are skipped entirely** |

You do NOT need the 40+ GB `flatfiles_cache` — that's only the raw source used to
build these two caches on the main PC.

### 1.4 Python environment

Any Python 3.10+. Minimal deps for the regime work:

```powershell
pip install pandas pyarrow numpy matplotlib
```

(If you plan to run the Streamlit app too: `pip install -r requirements.txt` if
present, or add `streamlit` — not needed for the regime engine.)

### 1.5 Smoke test — MUST pass before doing anything else

```powershell
python scripts\brooks_structure_engine.py 2022-02-24
```

Success = it writes `docs/living/tri_20220224.png` with swing pivots (HH/HL/LH/LL),
triangle lines, and TTR zones drawn. Open the PNG in VS Code and check it looks sane.
If it errors on the parquet load → step 1.3 didn't complete. If it silently produces
nothing → ticks for that day are missing (also step 1.3).

---

## Part 2 — Branch and session discipline

### 2.1 Create the working branch

```powershell
git pull
git checkout -b regime/v2-multistate
git push -u origin regime/v2-multistate
```

Work and commit on this branch for the whole regime effort. Merge to `main` only at
session end, together with the handoff update.

### 2.2 Session rules (same as main PC — they travel with the repo)

- **Read `docs/living/handoff.md` FIRST, every session.** It is the only source of
  truth. Relevant blocks for this work: **S62** (why the old regime is broken and
  banned), **S63** (the structure engine — the foundation), **S71** (mechanical
  backtest killed; hard rule against resurrecting the old engine).
- **`git pull` at session start, push at session end** — two machines now commit to
  this repo, and handoff.md is edited at the top of the file by both, so pulling
  first avoids conflicts there.
- **At session end:** add a new session block at the TOP of `docs/living/handoff.md`,
  commit, push.
- **Never commit** anything under `data/bars/`, `data/ticks_continuous/`, or any
  market data — the repo is public. The `.gitignore` already covers these; don't
  override it.
- NT8 `.cs` files (if any get touched) must be committed under `nt8/` immediately.

---

## Part 3 — The regime engine work (what to build)

### 3.1 Context — read these first

- **handoff.md S62:** the old regime state machine flip logic (single close through
  one confirmed LH/HL) is fatally weak — it flipped BULL inside 50-bar bear trends
  and then froze on the wrong side. ALL its sim results are invalid. **Banned.**
- **handoff.md S63:** `scripts/brooks_structure_engine.py` is the clean, user-validated
  foundation: two-bar H/L/OB/IB labels → swing pivots (OB decomposed by tick order)
  tagged HH/HL/LH/LL → triangles (contracting + 5-point expanding) → TTR zones.
  **Do not "improve" the structure engine without asking the user.**
- **The S62 invariant (the design contract):** a clean HH+HL sequence must hold BULL;
  a clean LH+LL sequence must hold BEAR. Triangles / TTR = neutral.

### 3.2 The task

Wire the structure engine's outputs into a **NEW multi-state regime layer** — a
separate module (e.g. `scripts/brooks_regime_v2.py`) that imports/reuses the
structure engine, never a patch of the old regime code.

Primary goal: **a precise, defensible bar-by-bar regime shading.** Setup/entry
identification is explicitly SECONDARY for now.

### 3.3 Proposed state set (starting point — refine bar-by-bar with the user)

More than 3 states, because a trend *attempt* is neither trend nor neutral:

| State | Enter on | Leave on |
|---|---|---|
| `BULL` | clean HH+HL sequence holding (S62 invariant) | sequence breaks — structural evidence, never one close |
| `BULL_ATTEMPT` | first HH / breakout from neutral, no confirmed HL yet | confirms (e.g. HL prints + holds) → `BULL`; fails (fBO back into range) → `NEUTRAL` |
| `NEUTRAL` | triangle or TTR active, or no valid sequence | breakout attempt → an `*_ATTEMPT` state |
| `BEAR_ATTEMPT` | mirror of `BULL_ATTEMPT` | mirror |
| `BEAR` | clean LH+LL sequence holding | mirror |

Why ATTEMPT states fix the S62 bug: the old engine promoted a single close straight
to a full flip. With ATTEMPT as a buffer, promotion to a full trend requires
*sequence* evidence, and a failed attempt falls back to NEUTRAL without ever having
flipped. The S62 flip-strength candidates (subsequent HH required, breakout-bar
size/strength, follow-through bar, EMA-close as component, major-TL break + test)
become **promotion criteria** for ATTEMPT→TREND, to be decided with the user.

Open design questions to settle WITH the user before coding transitions:
1. Exact promotion rule ATTEMPT→TREND (which combination of the candidates above).
2. Exact demotion rule TREND→? (straight to NEUTRAL, or via a weakening/ATTEMPT-against state).
3. Open-of-day seeding (S62: officially unsolved; first-triggered-entry adoption
   worked on the test day; user's b0-H/L seed idea never implemented).
4. mDB/mDT neckline flip (S62: user-identified — micro double-bottom at extreme +
   close above neckline = BULL candidate; tolerance spec still open).

### 3.4 Method — validate by eye BEFORE any sim (standing keep-in-check order)

1. Build the **chart overlay first**: regime as low-opacity background color bands
   on the 5-min chart, structure labels always drawn, dotted line from structure
   level to flip bar for every regime change (user's locked chart directives).
2. Grade it on the known hard days that exposed the old engine — **2022-02-24,
   2022-04-12, 2022-01-22** — plus S63's spot-check days (2022-04-01, 2022-04-02,
   2021-12-06) and a handful of random days.
3. Iterate the transition rules bar-by-bar with the user on those charts.
4. Only after the user signs off on the shading does ANY simulation get built —
   and no sim results from the old engine are ever cited.
5. Resist state inflation: 5 states is already a lot to specify. Get 5 right before
   discussing a 6th.

### 3.5 First prompt to give Claude Code on this PC

> Read docs/living/handoff.md (S62, S63, S71 blocks). We're on branch
> `regime/v2-multistate`. Continue the regime work: build a NEW multi-state regime
> layer (BULL / BULL_ATTEMPT / NEUTRAL / BEAR_ATTEMPT / BEAR) on top of
> `scripts/brooks_structure_engine.py` — reuse its primitives, do not modify it,
> and do not touch or reuse the old broken regime engine. Start with the chart
> overlay (regime background shading + structure labels + dotted flip lines) on
> 2022-02-24, and we'll refine the transition rules together bar-by-bar.

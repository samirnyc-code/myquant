# CLAUDE.md — read before doing anything

## ⚠️ SOURCE OF TRUTH: `docs/living/handoff.md`

**Read `docs/living/handoff.md` FIRST, every session, before any other context
or action.** It is the ONLY authoritative record of current state, direction,
and what is paused/agreed.

Do **NOT** treat the `.claude/projects/.../memory/` session-state files as the
handoff. They are secondary reference notes and may be stale or mislabeled. If
anything there conflicts with `docs/living/handoff.md`, **handoff.md wins**.

At the END of every session, update `docs/living/handoff.md` (add the new
session block at the top). Do not create parallel handoff files anywhere else.

## ⚠️ PERSIST EVERYTHING — NO INLINE, NO THROWAWAY (S80 hard rule)

Every script, analysis, and data pull is a work product, not a scratch note:

- **No inline analysis.** Never `python -c` for anything that produces a result.
  Write it to a `.py` file that also saves its DATED output/trade-list CSV.
- **Commit at the end of every unit of work** (each fix, each study) — never defer
  to session-end. Deferred = lost (S80: the gameplan `TR` fix was never in git).
- Research scripts live in the repo and are committed (`git add -f` if scratch is ignored).
- **Catalog every data pull** the moment it lands (ORATS/Databento/ticks/depth → data_catalog).
- **VERIFY EVERYTHING BEFORE YOU SPEAK.** Every claim, value, status, result, and
  timestamp — check the actual source THIS moment before stating it. Never assert from
  memory, assumption, or a stale reading. If not checked, say "not verified" — do not guess.
- **TIME/timezone:** this machine's clock/timezone does NOT match the user's local time
  (machine reads "W. Europe"; user is on CT). NEVER state a converted or "CT" wall-clock
  time as fact. Report the raw machine value labeled as machine-time, or defer to the user.
  Getting the time wrong repeatedly (2026-07-22) was a top complaint.

## ⚠️ NEVER CHANGE SYSTEM STATE WITHOUT ASKING

Never enable/disable/modify scheduled tasks, start/stop/kill processes or daemons,
restart servers, change configs, or delete/move data **without explicit user approval
first** — even if it seems safe or reversible. Present the option, wait for "yes".
Read-only checks are fine. (2026-07-22: disabled the NT8 Restart task unasked — do NOT.)
See memory `no-unilateral-state-changes`.

## ⚠️ COMMUNICATION — hard facts only (the user has demanded this repeatedly)

Bullets, brief, verified. No fluff, no opinion/recommendation unless asked, no
guesses (say "not verified"). **NEVER write meta-commentary about the user's
frustration or my own reliability** — banned: "you've been burned enough",
"straight answer not reassurance", "no bluffing", "I won't reassure blindly",
"I keep breaking things", "not the S79 mistake", references to past failures or
their emotional state as framing. Delete any such sentence and start with the
fact. See memory `communication-style` + `persist-work-discipline`.

## ⚠️ NT8 NINJASCRIPT FILES — ALWAYS COMMIT

All NinjaTrader 8 `.cs` files (indicators, strategies, drawing tools) **must**
be saved in `nt8/` and committed immediately. **Never** leave a CS file only on
the NT8 machine. Prior sessions lost `ZerolagExporter.cs`, `AlwaysIn.cs`,
`QSSignalOverlay.cs`, and `MCBreakout.cs` this way — they must be recreated.

See `nt8/README.md` for structure, lost-file registry, and naming conventions.

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
- **Verify from the data/metadata, never from memory or the handoff.** Else say "not verified".

Communication: hard facts only, bullets, brief; no fluff/opinion/sweet-talk/guesses;
opinions ONLY when asked. See memory `communication-style` + `persist-work-discipline`.

## ⚠️ NT8 NINJASCRIPT FILES — ALWAYS COMMIT

All NinjaTrader 8 `.cs` files (indicators, strategies, drawing tools) **must**
be saved in `nt8/` and committed immediately. **Never** leave a CS file only on
the NT8 machine. Prior sessions lost `ZerolagExporter.cs`, `AlwaysIn.cs`,
`QSSignalOverlay.cs`, and `MCBreakout.cs` this way — they must be recreated.

See `nt8/README.md` for structure, lost-file registry, and naming conventions.

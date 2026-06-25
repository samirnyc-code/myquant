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

## ⚠️ NT8 NINJASCRIPT FILES — ALWAYS COMMIT

All NinjaTrader 8 `.cs` files (indicators, strategies, drawing tools) **must**
be saved in `nt8/` and committed immediately. **Never** leave a CS file only on
the NT8 machine. Prior sessions lost `ZerolagExporter.cs`, `AlwaysIn.cs`,
`QSSignalOverlay.cs`, and `MCBreakout.cs` this way — they must be recreated.

See `nt8/README.md` for structure, lost-file registry, and naming conventions.

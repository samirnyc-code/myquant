# ClaudeTrackerAddOn — Setup for Thomas

**Written:** 2026-10-23 (Samir's machine)
**For:** whichever Claude Code session Thomas opens on his own machine to do this setup.
**Human context for Thomas:** GitHub account `tdeutschmann-byte`, already a collaborator on
this repo — same repo Samir works from, see `docs/living/second_pc_setup.md`.
**Goal:** get the new `ClaudeTrackerAddOn` running on Thomas's machine, immune to the
auto-disable bug that's been hitting `ClaudeTrackerV2` (the Strategy), with screenshots
correctly tagged to his real execution chart.

---

## Instructions for Claude (do these steps directly, don't just hand them to Thomas)

1. **Pull `main`** in Thomas's local clone of this repo (`git pull`, confirm you land on
   commit `8749c04` or later — `nt8: ClaudeTrackerAddOn screenshot — tag the real execution
   chart, don't guess by title`). If the clone doesn't exist yet, see
   `docs/living/second_pc_setup.md` Part 1 first — that's a separate one-time machine setup,
   not part of this doc.

2. **Ask Thomas directly for 3 values before editing anything** (do not guess or default
   these — they're per-machine and wrong values will silently corrupt his tracking data or
   collide with his existing Strategy's output):
   - His exact NT8 **account name** (whatever shows in NT8's Control Center — could be a
     Sim account like `Sim101` or a live account name).
   - His current **contract** if it's not `ES 12-26` (unlikely to differ from Samir's, but
     confirm).
   - Where he wants the AddOn's **export folder** to live. It must NOT be the same folder
     his existing `ClaudeTrackerV2` Strategy already writes to — both writing to one folder
     at once will corrupt each other's CSVs (same reason Samir's copy uses a `_AddOnTest`
     suffix on his own machine, see `nt8/addons/ClaudeTrackerAddOn.cs:355`). If he doesn't
     know what his Strategy's current export folder is, find it by reading his deployed
     `ClaudeTrackerV2.cs`'s `ExportRootFolder` const, then pick a sibling folder for the
     AddOn.

3. **Copy 3 files** from the repo into Thomas's NT8 Custom folders (adjust the Documents
   path if his Windows username differs from the repo-relative assumption):

   ```text
   nt8\addons\ClaudeTrackerAddOn.cs            -> <Documents>\NinjaTrader 8\bin\Custom\AddOns\ClaudeTrackerAddOn.cs
   nt8\indicators\ClaudeTrackerChartTag.cs      -> <Documents>\NinjaTrader 8\bin\Custom\Indicators\ClaudeTrackerChartTag.cs
   nt8\indicators\ClaudeTrackerChartRegistry.cs -> <Documents>\NinjaTrader 8\bin\Custom\Indicators\ClaudeTrackerChartRegistry.cs
   ```

   Byte-verify each copy (diff source vs destination) before moving on — same discipline
   Samir's sessions use, see CLAUDE.md / memory `nt8-deploy-repo-to-custom-folder`.

4. **Edit the per-machine consts in the DEPLOYED copy** (the one in `Custom\AddOns\`, not
   the repo copy — the repo copy should stay generic/Samir's-values so it doesn't produce a
   misleading diff on the next commit; if Thomas wants his own values tracked in git too,
   that's his call to make explicitly, don't do it silently):
   - `nt8/addons/ClaudeTrackerAddOn.cs` (~line 90): `AccountName`, `SymbolName`,
     `TraderTag = "Thomas"`.
   - Same file (~line 355): `ExportRootFolder` — the value Thomas gave you in step 2.

5. **Tell Thomas to F5 when flat** (no open position) — this step needs a human in the NT8
   UI, you can't do it. Watch the Output log with him if possible for compile errors.

6. **Tell Thomas to tag his execution chart** — this also needs a human:
   right-click the ONE chart he actually places orders from → **Indicators...** → add
   **"ClaudeTracker Chart Tag"**. No settings to configure, it's invisible. Only the one
   real execution chart — if tagged on more than one chart for the same instrument,
   whichever loads last silently wins.
   This step matters: without it, the AddOn falls back to guessing the right chart by
   window title, which **can grab the wrong one** if more than one open window shows the
   same instrument — confirmed live on Samir's machine (a real screenshot landed, just from
   the wrong chart, before this tag mechanism was added).

7. **Verify together.** Have Thomas fire a Sim test trade. Grep his NT8 log for
   `ClaudeTrackerAddOn`. Expect `Screenshot saved (tagged chart): ...`. If you instead see
   `Screenshot: no window titled "Chart - ..." ...` or a plain `Screenshot saved: ...`
   (missing "tagged chart"), the tag isn't registering — recheck step 6 was applied to the
   right chart and that the AddOn actually recompiled afterward.

8. **Recommend Thomas run the AddOn side by side with his existing `ClaudeTrackerV2`, not
   instead of it, for at least one full session** — compare the two output folders before
   he trusts the AddOn alone. Don't disable/remove the Strategy for him.

---

## Why this exists (context for Thomas, not an instruction)

`ClaudeTrackerV2` (the Strategy Thomas runs now) keeps getting disabled by NT8 itself — see
`docs/living/claudetracker_incidents.md`, including Thomas's own 2026-10-21 incident where a
whole trading day went untracked. `ClaudeTrackerAddOn` is a straight port of the same
tracking logic as an AddOn instead — AddOns have no enable/disable state for NT8 to touch,
so that whole class of bug goes away. It's been running side-by-side with the Strategy on
Samir's machine since 2026-10-23, trade-tracking confirmed correct on live tests.
Screenshots took a few extra rounds to get right (see `docs/living/handoff.md`'s 2026-10-23
entries for the full chain) — the chart-tag step above is the fix, don't skip it.

## If something looks wrong

Check `docs/living/claudetracker_incidents.md` first — most past failures are documented
there with root cause and fix. If it's something new, report back with the exact NT8 Output
log lines rather than guessing at a fix blind — this file's whole history is examples of why
that goes wrong.

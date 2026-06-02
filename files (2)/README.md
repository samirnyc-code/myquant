# myquant / docs — Index
**Last Updated:** June 2, 2026  
**Rule:** Every doc in this repo is listed here. If it's not in this index, it doesn't exist.  
**Rule:** One source of truth per topic. Never duplicate information across files.  
**Rule:** Update this index every session before closing.

---

## reference/ — Stable, authoritative. Changes only when literature is added.

| File | What it is |
|------|------------|
| `library_tenets.md` | Pardo chapter-by-chapter extraction. Key thresholds, quotes, warnings. |
| `strategy_validation_framework.md` | Full testing protocol for MC setups. Layers 1-6. Per-setup report structure. |

---

## architecture/ — How the system is built. Changes when design decisions are made.

| File | What it is |
|------|------------|
| `data_sources.md` | Single source of truth for all data. Providers, formats, validation gates. |
| `bar_validation.md` | Bar comparison architecture. Sierra vs Python vs NT8/Rithmic. Decision gates. |
| `nt8_simulator.md` | Current NT8 sim architecture. CSV schema, signal logic, Sheets pipeline. |
| `python_wfa_spec.md` | Full Python WFA engine specification. Phases A-G. Pardo compliance checklist. |

---

## living/ — Changes every session.

| File | What it is |
|------|------------|
| `handoff.md` | Current state of all active work. Versions, bugs, pending items. Read first every session. |
| `roadmap.md` | All phases and their status. Single source of truth for what gets built next. |
| `open_questions.md` | Undecided design questions only. Resolved questions are removed, not kept here. |

---

## journal/ — Personal learning log.

| File | What it is |
|------|------------|
| `samir_learning_journal.md` | Developer setup log. Concepts, tools, shortcuts. |

---

## archive/ — Completed task briefs. Read-only. Never reference these in active work.

| File | What it is |
|------|------------|
| `handoff_pardo_extraction.md` | Task brief for Pardo extraction. Completed June 2, 2026. Output: library_tenets.md |

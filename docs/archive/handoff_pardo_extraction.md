# Handoff — Pardo Extraction Session
**Date:** June 1, 2026  
**From:** MCSimulator V3 Project — Architecture Session  
**Purpose:** Extract key tenets from Pardo into library_tenets.md

---

## Context

We are building a Python-based trading simulator for MC (micro-channel) signals on ES futures. The simulator will validate 5 independent setups (1cc–5cc) using a rigorous statistical framework grounded in established literature.

Robert Pardo's *The Evaluation and Optimization of Trading Strategies* is the primary reference for walk-forward methodology — the core robustness test of our framework.

---

## What We Need From Pardo

Extract into `library_tenets.md` — a living document in the `myquant` GitHub repo under `docs/`.

For each chapter, extract:
1. **Core tenet** — the main principle in 1-2 sentences
2. **Specific thresholds or rules** — any numbers Pardo defines (e.g. WFE > 0.5)
3. **Direct quotes** — exact wording for anything we will cite in our framework
4. **Warnings** — things Pardo explicitly says NOT to do
5. **Applicability to our setup** — how it applies to 3cc/MC signal validation

---

## Already Established in Our Framework

These are in `strategy_validation_framework.md` — verify against actual Pardo text:
- Walk-Forward Efficiency (WFE) threshold: >0.5
- OOS profitable windows: >60% minimum
- Parameter selection via robustness plateau (not peak performance)
- IS/OOS split methodology
- Rolling vs anchored walk-forward configurations

---

## Output Format

```markdown
## Pardo — Chapter X: [Title]

### Core Tenet
[1-2 sentence summary]

### Key Rules / Thresholds
- [Rule 1] (page X)
- [Rule 2] (page X)

### Direct Quotes
> "[exact quote]" — p.X

### Warnings
- [What Pardo says NOT to do]

### Applicability to MC Sim
[How this applies to our specific setup]
```

---

## Priority Chapters

Focus on these first:
1. Walk-forward methodology (IS/OOS split)
2. Parameter optimization
3. Robustness testing
4. Interpreting results
5. Common mistakes / what invalidates a backtest

---

*Once extraction is complete, paste into `myquant/docs/library_tenets.md` and commit.*

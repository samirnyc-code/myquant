# myquant — Collaborator Onboarding
**For:** Thomas  
**Last Updated:** June 2, 2026

---

## Step 1 — Clone the repo
```
git clone https://github.com/samirnyc-code/myquant.git
cd myquant
```

## Step 2 — Read these first, in this order
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

# Samir's Learning Journal
**Last Updated:** June 2, 2026

---

## Tag 1 — June 1, 2026
### Developer Setup (Zero to Repo in One Day)

| Concept | What it is |
|---------|------------|
| **VS Code** | Code editor (free, by Microsoft) |
| **Git** | Local tool for version control — tracks every change to code |
| **GitHub** | Cloud hosting for git repos — your code is backed up online |
| **Repository (Repo)** | A folder/project managed by git |
| **Clone** | Load a copy of a GitHub repo locally onto your computer |
| **Commit** | A saved change in the git system |
| **Command Palette** | Cmd+Shift+P — search bar for all VS Code commands |
| **Extension** | Plugin that extends VS Code |
| **GitLens** | VS Code extension — visualizes your full git history (see Tag 2) |
| **Claude Code** | Anthropic's AI integrated directly into VS Code |
| **Settings Sync** | VS Code settings synced across devices |

### Installed and configured
- VS Code, Git, GitHub account (samirnyc-code)
- GitHub connected to VS Code
- GitLens, C# Dev Kit, Claude Code installed
- First GitHub repo created (myquant — Private)
- Repo cloned locally in VS Code

### Mac shortcuts
| Shortcut | Function |
|----------|----------|
| `Cmd+Shift+P` | Open Command Palette |
| `Cmd+V` | Paste |
| `Cmd+C` | Copy |

### Mac to PC workflow
```
Mac → (Cmd+S save) → Git Commit → Push → GitHub
                                            ↓
PC  ← Git Pull ←────────────────────── GitHub
```

---

## Tag 2 — June 2, 2026
### Git Workflow, GitLens, and Hard Lessons

#### Concepts learned

| Concept | What it is |
|---------|------------|
| **GitLens** | VS Code extension that shows the full git commit graph — every commit, who made it, when, what changed. Also shows inline "blame" — which commit last changed each line of code. |
| **Commit graph** | The timeline of every change ever made to the repo. Never shrinks. Every commit is permanent. |
| **git add .** | Stages all changed files — tells git "include everything in the next commit" |
| **git rm** | Removes a file from git tracking. The deletion itself becomes a commit in the graph. |
| **git pull** | Syncs remote changes to your local copy |
| **git pull --rebase** | Same as pull but used when local and remote have diverged — git replays your local commits on top of the remote state instead of creating a merge conflict |
| **git push** | Sends your local commits to GitHub |
| **unzip -d** | Extracts a zip file to a specific folder location |
| **.gitignore** | A file in the repo root that tells git to permanently ignore specific files. Once a file is in .gitignore, git never tracks it again. |
| **.DS_Store** | A hidden Mac system file created automatically in every folder. Useless in a repo. Add to .gitignore so it never appears again. |
| **Remote vs local** | GitHub (remote) and your computer (local) are two separate states. Git keeps them in sync. When they diverge, git blocks you and tells you exactly why. |

#### Key mental models

**Git never deletes history.**
Every state your repo has ever been in is recoverable. When you delete a file with `git rm`, the deletion is recorded as a commit — the file is gone from the current state but permanently visible in the graph. You can always go back. This means mistakes are always recoverable. Commit frequently.

**Local and remote are two separate states.**
When you delete files on GitHub web without pulling locally first, your local copy is behind. Git will reject your next push with "fetch first." Fix: `git pull --rebase` then `git push`.

**Dragging a zip into a repo creates wrong folder nesting.**
If you drag a zip file (not its extracted contents) into a repo folder, git tracks the zip and the extracted folder has an extra level. Always extract first, then move the files.

**The .gitignore lesson.**
`.DS_Store` showed up in multiple commits today because it wasn't ignored. Fix once with:
```
echo ".DS_Store" >> .gitignore
git add .gitignore
git commit -m "add gitignore"
git push
```
Never appears again.

#### Commands used today
```bash
git pull --rebase        # sync when remote is ahead of local
git rm <file>            # remove file from git tracking
git rm -r <folder>       # remove folder from git tracking
git add .                # stage all changes
git commit -m "message"  # commit with message
git push                 # push to GitHub
ls                       # list files in current directory
mkdir -p a/b/c           # create nested folders in one command
mv <source> <dest>       # move file or folder
unzip file.zip -d /path  # extract zip to specific location
cp -r <source> <dest>    # copy folder recursively
```


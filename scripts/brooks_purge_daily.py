"""Permanently delete user-marked non-chart images from the daily set.

Reads the newest brooks_deletions*.json from Downloads (exported via the
'⤓ Export delete list' button in daily.html), deletes those jpgs from
daily2/, adds the ids to the permanent exclusion list
(docs/living/brooks_daily_excluded.json), rebuilds daily.html, and clears
nothing else — favorites are untouched.

  python scripts/brooks_purge_daily.py            # newest Downloads export
  python scripts/brooks_purge_daily.py <file.json>
"""
import json, sys, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HUB = ROOT / 'docs' / 'living' / 'brooks_codex'
EXC = ROOT / 'docs' / 'living' / 'brooks_daily_excluded.json'
DL = Path(r'C:\Users\Admin\Downloads')

if len(sys.argv) > 1:
    src = Path(sys.argv[1])
else:
    cands = sorted(DL.glob('brooks_deletions*.json'), key=lambda p: p.stat().st_mtime)
    if not cands:
        sys.exit('No brooks_deletions*.json in Downloads — export it from daily.html first.')
    src = cands[-1]

ids = set(json.load(open(src, encoding='utf-8')))
excluded = set(json.load(open(EXC, encoding='utf-8'))) if EXC.exists() else set()
deleted = 0
for i in ids:
    p = HUB / 'daily2' / f'{i}.jpg'
    if p.exists():
        p.unlink(); deleted += 1
excluded |= ids
json.dump(sorted(excluded), open(EXC, 'w', encoding='utf-8'), indent=0)
print(f'{src.name}: {len(ids)} ids -> deleted {deleted} files; exclusion list now {len(excluded)}')
subprocess.run([sys.executable, str(ROOT / 'scripts' / 'brooks_build_daily2.py')], check=True)
print('daily.html rebuilt. (Tip: the trash in your browser can now be emptied.)')

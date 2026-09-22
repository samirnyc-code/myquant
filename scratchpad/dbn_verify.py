"""Verify a Databento batch download: on-disk file sizes vs the job manifest (list_files)."""
import json, sys
from pathlib import Path
import databento as db
k = json.load(open(r'C:\Users\Admin\AppData\Local\myquant\databento.json', encoding='utf-8-sig'))['key']
job = sys.argv[1] if len(sys.argv) > 1 else 'GLBX-20260721-JRSPF47X5J'
out = Path(r'data\databento') / job / job
fs = db.Historical(k).batch.list_files(job)
exp = disk = 0
miss = []
for f in fs:
    fn = f['filename']; sz = f.get('size', 0); exp += sz
    p = out / fn
    d = p.stat().st_size if p.exists() else 0
    disk += d
    if d != sz:
        miss.append((fn, sz, d))
print(f'job {job}: {len(fs)} files')
print(f'  manifest total: {exp/1e9:.2f} GB | on-disk: {disk/1e9:.2f} GB')
print(f'  size-matched: {len(fs)-len(miss)}/{len(fs)}')
if miss:
    print('  MISMATCH/MISSING:')
    for fn, s, d in miss[:20]:
        print(f'    {fn}: manifest {s/1e6:.1f}MB, disk {d/1e6:.1f}MB')
else:
    print('  COMPLETE — every file matches the manifest byte-for-byte')

import json, time, databento as db
from pathlib import Path
k=json.load(open(r'C:\Users\Admin\AppData\Local\myquant\databento.json',encoding='utf-8-sig'))['key']
c=db.Historical(k); job='GLBX-20260721-4T649EM33V'
out=Path(r'data\databento\GLBX-20260721')
fs=c.batch.list_files(job); n=len(fs)
for i,f in enumerate(fs,1):
    fn=f['filename']; sz=f.get('size',0)
    dest=out/job/fn
    if dest.exists() and dest.stat().st_size==sz:
        print(f'[{i}/{n}] skip {fn}',flush=True); continue
    for a in range(5):
        try:
            c.batch.download(output_dir=str(out),job_id=job,filename_to_download=fn)
            print(f'[{i}/{n}] OK {fn} {sz/1e6:.0f}MB',flush=True); break
        except Exception as e:
            print(f'[{i}/{n}] retry{a} {fn}: {str(e)[:60]}',flush=True); time.sleep(15)
print('ALL DONE',flush=True)

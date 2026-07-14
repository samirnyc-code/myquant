"""Tag forum bar-by-bar day texts with official Brooks Encyclopedia sections.

Uses docs/living/brooks_encyc_index.json (596 sections, abbr -> name) as the
tag vocabulary. A day text matches a section when the section's abbreviation
appears as a whole-token sequence in the text (longest codes win; generic
1-token codes like 'PB'/'DT' are only counted when they appear >= MIN_GENERIC
times, to keep tag noise down).

  python scripts/brooks_tag_days.py <forum_index.json>   # tag scrape output
  python scripts/brooks_tag_days.py --demo               # demo on test data
"""
import json, re, sys
from pathlib import Path
from collections import Counter

ROOT = Path(r'c:\Users\Admin\myquant')
IDX = json.load(open(ROOT / 'docs' / 'living' / 'brooks_encyc_index.json', encoding='utf-8'))
MIN_GENERIC = 3   # occurrences required for 1-token generic codes

def _tokens(s):
    # strip the tooltip expansions "H2(Two legged...)" -> "H2", then tokenize
    s = re.sub(r'\(([^()]|\([^()]*\))*\)', ' ', s)
    return re.findall(r"[A-Za-z0-9=/+\-']+", s)

# precompile: abbr -> token tuple, longest first so specific codes win
VOCAB = []
for e in IDX:
    tt = tuple(t.upper() for t in _tokens(e['abbr']))
    if tt:
        VOCAB.append((tt, e))
VOCAB.sort(key=lambda x: -len(x[0]))

def tag_text(text):
    toks = [t.upper() for t in _tokens(text)]
    joined = ' ' + ' '.join(toks) + ' '
    counts = {}
    for tt, e in VOCAB:
        pat = ' ' + ' '.join(tt) + ' '
        n = joined.count(pat)
        if not n:
            continue
        if len(tt) == 1 and len(tt[0]) <= 3 and n < MIN_GENERIC:
            continue  # generic single token (PB, DT, BX...) mentioned in passing
        counts[e['abbr']] = {'section': e['section'], 'part': e['part'], 'n': n}
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]['n']))

if __name__ == '__main__':
    if '--demo' in sys.argv:
        scr = Path(r'C:\Users\Admin\AppData\Local\Temp\claude\c--Users-Admin-myquant'
                   r'\f04593f3-53f8-4ab9-9690-dd0509e339a3\scratchpad')
        raw = open(scr / 'bbb_6042_text.txt', encoding='utf-8').read()
        tags = tag_text(raw)
        print('=== day 6042 (07-26-2022):', len(tags), 'tags')
        for k, v in list(tags.items())[:15]:
            print(f"  {v['n']:>3}x  {k:<18} {v['section']}")
        ft = json.load(open(scr / 'forum_test.json', encoding='utf-8'))
        for r in ft:
            if r.get('text'):
                tags = tag_text(r['text'])
                top = ', '.join(list(tags)[:6])
                print(f"=== {r['date']} t={r['id']}: {len(tags)} tags | {top}")
    else:
        src = Path(sys.argv[1])
        days = json.load(open(src, encoding='utf-8'))
        for d in days:
            if d.get('text'):
                d['tags'] = tag_text(d['text'])
        json.dump(days, open(src.with_name(src.stem + '_tagged.json'), 'w',
                             encoding='utf-8'), ensure_ascii=False)
        c = Counter(t for d in days for t in d.get('tags', {}))
        print(f"tagged {sum(1 for d in days if d.get('tags'))} days; "
              f"top tags: {c.most_common(12)}")

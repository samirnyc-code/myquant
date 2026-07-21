"""Parse the official Brooks Encyclopedia of Chart Patterns index (Oct 1, 2025,
Parts 1-16) from the Drive spreadsheet's flattened CSV text into
docs/living/brooks_encyc_index.json: [{part, section, abbr}].

Source: 'Copy of The-Brooks-Encyclopedia-of-Chart-Patterns-Index.xlsx'
(Drive id 1A9KIU9D3vV5HVCyb4nZfeP8E0B7I5uXI). The Drive API flattens the sheet
to one line: rows are ' ,' separated, fields comma-separated with quoted
fields; a bare part number is glued to the END of the previous part's last
row (e.g. '...,BX Y 2,Consecutive Complex Bottoms,...').
"""
import csv, io, json, re, sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
RAW = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    _ROOT / "scratchpad" / "encyc_index_raw.txt")
OUT = _ROOT / "docs" / "living" / "brooks_encyc_index.json"

raw = RAW.read_text(encoding='utf-8')
# drop the title/header preamble up to the column header row
raw = raw.split('Abbreviations in Presentation', 1)[1]

# Flatten to one CSV field stream, then walk (section, abbr) pairs. Part
# numbers appear glued to the END of the previous part's last abbr field
# ("...BX Y 2") or standalone; parts run sequentially 1..16, so only accept
# the number we expect next.
fields = next(csv.reader(io.StringIO(raw.replace('\n', ' '))))
entries, part, i = [], 0, 0
while i < len(fields):
    f = fields[i].strip()
    if not f:
        i += 1; continue
    if f.isdigit() and int(f) == part + 1:      # standalone part marker
        part += 1; i += 1; continue
    m = re.match(r'^(\d{1,2}),?\s*$', f)
    section = f
    if i + 1 >= len(fields):
        break
    abbr = fields[i + 1].strip()
    bump = False
    m = re.match(r'^(.*\S)\s+(\d{1,2})$', abbr)  # part number glued to abbr
    if m and int(m.group(2)) == part + 1:
        abbr = m.group(1); bump = True
    m = re.match(r'^(.*\S)\s+(\d{1,2})$', section)
    if m and int(m.group(2)) == part + 1 and not section[0].isdigit():
        pass  # section text legitimately ending in a number — leave it
    entries.append({'part': part, 'section': section, 'abbr': abbr})
    if bump:
        part += 1
    i += 2

OUT.write_text(json.dumps(entries, indent=1, ensure_ascii=False), encoding='utf-8')
parts = sorted(set(e['part'] for e in entries))
print(f'{len(entries)} sections across parts {parts}')
print('sample:', entries[1], entries[-1])
dups = {}
for e in entries:
    dups.setdefault(e['abbr'], []).append(e['section'])
d = {k: v for k, v in dups.items() if len(v) > 1}
print(f'{len(d)} duplicate abbrs (expected few):', list(d)[:5])

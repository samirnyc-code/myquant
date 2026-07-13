"""Generate the 25-chart pilot workflow (verify-match + Brooks-method commentary),
embedding the selected items so it can run by scriptPath.
"""
import json, re
from pathlib import Path
SCR = Path(r"C:\Users\Admin\AppData\Local\Temp\claude\c--Users-Admin-myquant\f04593f3-53f8-4ab9-9690-dd0509e339a3\scratchpad")
items = json.load(open(SCR / "daily_pilot25.json", encoding="utf-8"))

def clean(o):
    if isinstance(o, str):
        return re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', o).replace('�', '')
    if isinstance(o, list):
        return [clean(x) for x in o]
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    return o

items = clean(items)
items_js = json.dumps(items, ensure_ascii=True)   # escape non-ascii; no raw control chars

JS = r'''export const meta = {
  name: 'brooks-daily-pilot25',
  description: 'Verify each daily chart is a real matching Emini 5-min chart, then write Brooks-method commentary',
  phases: [{ title: 'Analyze', detail: 'vision: verify match + write commentary' }],
}
const ITEMS = __ITEMS__;
const DIR = 'C:/Users/Admin/myquant/docs/living/brooks_codex/daily';
const SCHEMA = {
  type: 'object',
  properties: {
    image_kind: { type: 'string', enum: ['emini_5min_intraday','emini_other_timeframe','other_market','macro_multiyear','decorative_photo','other'] },
    is_valid_match: { type: 'boolean', description: 'true only if the image is a real Emini 5-min INTRADAY chart consistent with the stated day-type' },
    why: { type: 'string', description: 'one sentence: what the image actually is / why valid or not' },
    commentary: { type: 'string', description: 'Brooks-method analysis (~180 words) ONLY if is_valid_match; else empty string' },
  },
  required: ['image_kind','is_valid_match','why','commentary'],
}
const PRIMER = `AL BROOKS METHOD (for grounding your commentary):
- Day types: Trend-from-the-open, Trending Trading Range, Trading Range, Spike-and-Channel, Reversal, Climax. A close near the open = trading range day.
- Setups: High/Low 1-2 pullbacks (H2 = 2-legged pullback to the 20-EMA, his best with-trend entry); wedge (3 pushes = reversal, take the 2nd signal); double top/bottom; breakout pullback (2nd entry); final flag; major trend reversal (needs a trendline break THEN a lower-high/higher-low test); buy/sell climax (too far too fast -> fade for a 2-legged correction, don't initiate with-climax).
- Rules: the Trader's Equation (prob x reward vs prob x risk); Always-in (which way institutions lean); never trade countertrend before a trendline break; a weak rally is unlikely to last all day; on a range day buy low / sell high / scalp more; respect the 20-EMA.
- His chart annotations: green up-arrows = buy signals, red down-arrows = sell signals; he labels wedges, double tops/bottoms, climaxes, trendlines; blue line = 20-EMA.`

function prompt(it){
  return `You are Al Brooks writing the end-of-day analysis for ONE chart, in his method and vocabulary. Be rigorous and HONEST.

Open and look at the chart image:
  Read(file_path="${DIR}/${it.id}.jpg")

This post's REAL metadata (from his blog): title/day-type = "${it.day_type}"; short type = "${it.day_type_short}"; date = ${it.date}; tags = ${JSON.stringify(it.tags)}.

STEP 1 — VERIFY THE IMAGE. Blog posts sometimes had the wrong image scraped. Decide what the image actually is (image_kind) and whether it is a genuine Emini 5-minute INTRADAY chart consistent with the day-type (is_valid_match). If it is a decorative photo, a multi-year macro chart, a different market's daily chart, or otherwise NOT a 5-min intraday Emini session matching the day-type, set is_valid_match=false and commentary="". Do not force it.

STEP 2 — ONLY IF VALID, write the commentary (~180 words), grounded ONLY in what is visibly annotated on the chart:
- Open with the day-type call.
- Walk the day chronologically through the features Brooks marked (open -> first leg -> reversal/climax -> close), naming the arrows/labels you see.
- Tie each feature to the matching Brooks setup/rule.
- End with a Trader's-Equation "how to trade it" takeaway.
Voice: Brooks textbook, declarative, teaching. Do NOT invent bars or levels not visible.

${PRIMER}

Return the structured object.`
}

phase('Analyze')
log(`Analyzing ${ITEMS.length} pilot charts (verify + commentary) ...`)
const res = await parallel(ITEMS.map(it => () =>
  agent(prompt(it), { label: it.id, phase: 'Analyze', schema: SCHEMA, model: 'sonnet' })
    .then(r => ({ id: it.id, date: it.date, day_type: it.day_type, ...(r||{}) }))
    .catch(e => ({ id: it.id, error: String(e) }))
))
const ok = res.filter(Boolean)
const valid = ok.filter(r => r.is_valid_match)
log(`Done. valid matching Emini charts: ${valid.length}/${ok.length}`)
return { results: ok, valid_count: valid.length, total: ok.length }
'''
JS = JS.replace("__ITEMS__", items_js)
out = SCR / "brooks_pilot25.workflow.js"
out.write_text(JS, encoding="utf-8")
print("wrote", out, len(JS), "bytes,", len(items), "items")

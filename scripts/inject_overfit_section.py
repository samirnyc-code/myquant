"""Inject the significance / overfitting-evidence section (two figures + corrected
stats) into docs/artifacts/regime_2e_summary.html. Idempotent (marker-guarded);
re-run after regenerating the figures to refresh.

  python scripts/inject_overfit_section.py
"""
import base64
from pathlib import Path

WT = Path(__file__).resolve().parent.parent
ART = WT / "docs" / "artifacts" / "regime_2e_summary.html"
SIG = WT / "docs" / "living" / "overfit_evidence_significance.png"
FP = WT / "docs" / "living" / "overfit_evidence_fingerprint.png"
MARK = "<!-- OVERFIT-EVIDENCE -->"


def b64(p):
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


section = f"""{MARK}
<h2 id="significance">Is it overfit? — statistical significance &amp; fingerprint checks</h2>
<div class="box warn">
<span class="k">Correction (2026-07-25).</span> Two claims carried in earlier notes were wrong and
<span class="k">pessimistic</span>: "~20 effective observations" and "PF CI straddles 1.0". Both are
corrected below on the current <span class="k">three-book</span> system (678 trades). Numbers recomputed
from committed trade data via <code>regime_2e_overfit_evidence.py</code> (reproducible).
</div>
<div class="tw"><table>
<tr><th>significance metric</th><th>value</th></tr>
<tr><td>P(profit factor &gt; 1) — bootstrap 20k</td><td class="pos"><span class="k">99.9%</span></td></tr>
<tr><td>P(5-yr net &gt; 0)</td><td class="pos"><span class="k">99.9%</span></td></tr>
<tr><td>PF 5th percentile (iid / 5-block)</td><td>1.20 / 1.16 — <span class="k">does NOT straddle 1.0</span></td></tr>
<tr><td>Net 5th–95th CI</td><td>[+$44k, +$146k]</td></tr>
<tr><td>Kish effective-N</td><td><span class="k">115 winners / 273 all-trades</span> (not ~20)</td></tr>
<tr><td>Winners</td><td>286 of 678; 50% of gross profit = top 48, 80% = top 124</td></tr>
<tr><td>Train vs Test PF</td><td>test <span class="k">&ge;</span> train at every stop (overfit shows the opposite)</td></tr>
<tr><td>Parameter neighborhood</td><td>broad plateau 1.3–1.5 (no sharp peak)</td></tr>
<tr><td>Leave-one-year-out</td><td>drop any year → rest holds 1.35–1.50</td></tr>
<tr><td>Quarterly PF (fixed params)</td><td>15 of 19 quarters green</td></tr>
</table></div>
<p><b>The edge is in-sample significant and the overfitting fingerprints are absent.</b> What these
figures cannot show is forward performance — that requires the live/paper test, not a backtest.</p>
<figure><img alt="bootstrap significance" src="{b64(SIG)}"/>
<figcaption>Bootstrap PF &amp; net distributions (right of 1.0 / 0), positive-skew P&amp;L, and the
profit-concentration curve (Kish effective-N = 115).</figcaption></figure>
<figure><img alt="overfitting fingerprint" src="{b64(FP)}"/>
<figcaption>Overfitting checks: train≤test, parameter plateau, leave-one-year-out, quarterly PF —
all pointing away from overfitting.</figcaption></figure>
"""

html = ART.read_text(encoding="utf-8")
if MARK in html:
    pre, rest = html.split(MARK, 1)
    post = rest.split("<h2", 1)[1]
    html = pre + section + "\n<h2" + post
    note = "refreshed"
else:
    anchor = "<h2>Verdict</h2>"
    html = html.replace(anchor, section + "\n" + anchor, 1)
    note = "inserted before Verdict"
ART.write_text(html, encoding="utf-8")
print(f"{note}: {ART.name}  ({len(html)} bytes)")

# Artifact page generators

Each script builds one self-contained HTML review page for the regime tracker and
writes it to `out/` (git-ignored — the pages embed their charts as base64 and run
0.2–1.3 MB each). They read the committed `regime_data_es_*.json` and
`ms_chart_*.png` in the parent directory, so regenerate a chart first if the data
changed:

```
python run_regime_parquet.py ../data/bars/_continuous_1m.parquet --date 2026-02-13 \
    --out regime_data_es_20260213.json
python plot_regime.py regime_data_es_20260213.json --out ms_chart_20260213.png
python pages/build_day_page_0213.py
```

| Script | Page | Covers |
| --- | --- | --- |
| `build_ms_page.py` | `market_structure.html` | The Market Structure.pdf rules as implemented |
| `build_audit_page.py` | `transition_audit.html` | Transition-rule audit (pre-PDF rules — historical) |
| `build_day_page.py` | `es_regime_0625.html` | 25 Jun — the b69 second Bear leg |
| `build_day_page_0406.py` | `es_regime_0406.html` | 6 Apr — the b25 Bear entry |
| `build_day_page_0213.py` | `es_regime_0213.html` | 13 Feb — the b9 BOS |
| `build_week_page.py` | `es_regime_week_0518.html` | 18–22 May, with the week regime tape |
| `build_recheck_page.py` | `es_regime_recheck_three.html` | 12-26 / 05-19 / 05-21 after a rule change |
| `build_reconciled_page.py` | `es_regime_reconciled.html` | The four sessions the outside-bar rule settles |
| `build_delta_page.py` | `es_regime_outside_bar_delta.html` | Before/after pairs for a rule change |

## Before/after pages

`build_delta_page.py` compares the current output against a **baseline snapshot**
that is not in the repo, because it only exists while a rule change is being
evaluated. Build one by checking out the previous engine and re-running the
sessions into a scratch directory:

```
git show <old-rev>:regime_tracker/regime_tracker.py > /tmp/rt_old.py   # swap in
python run_regime_parquet.py ... --out <dir>/prev/regime_data_es_<slug>.json
python plot_regime.py <dir>/prev/regime_data_es_<slug>.json \
    --out <dir>/prev/ms_chart_<slug>_before.png
python pages/build_delta_page.py <dir>
```

It takes the directory *containing* `prev/`, and defaults to `pages/_baseline`.

## Note on duplication

The three `build_day_page*.py` and the three multi-day scripts are near-copies —
each was derived from the one before it by patching the title, the session list
and the prose. They are kept as-is so every published page stays reproducible
byte-for-byte. Consolidating them into one generator driven by a content file is
worth doing before the next batch of pages.

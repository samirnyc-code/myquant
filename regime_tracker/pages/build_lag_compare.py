#!/usr/bin/env python3
"""Side-by-side regime charts for one session under two views (e.g. Lag 1 vs finalised).

    python pages/build_lag_compare.py SLUG DIR_A DIR_B [--label-a ..] [--label-b ..]
                                     [--note "html"] [--out name.html]

Each DIR holds regime_data_es_<SLUG>.json and a chart PNG for it (ms_chart_<SLUG>.png,
or any ms_chart_<SLUG>*.png). Writes a self-contained page to pages/out/.
"""
import argparse, base64, json, pathlib

HERE = pathlib.Path(__file__).resolve().parent
OUT_DIR = HERE / "out"
OUT_DIR.mkdir(exist_ok=True)


def side(d, slug):
    js = json.load(open(d / f"regime_data_es_{slug}.json"))
    png = sorted(d.glob(f"ms_chart_{slug}*.png"))[0]
    shape = " → ".join(f'<b class="r-{g["regime"].lower()}">{g["regime"]} {g["start"] + 1}</b>'
                       for g in js["segments"])
    return shape, base64.b64encode(png.read_bytes()).decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("a", type=pathlib.Path)
    ap.add_argument("b", type=pathlib.Path)
    ap.add_argument("--label-a", default="A")
    ap.add_argument("--label-b", default="B")
    ap.add_argument("--note", default="")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    sa, ia = side(a.a, a.slug)
    sb, ib = side(a.b, a.slug)
    s = a.slug
    title = f"ES {s[:4]}-{s[4:6]}-{s[6:]} · {a.label_a} vs {a.label_b}"
    out = OUT_DIR / (a.out or f"lag_compare_{s}.html")

    css = """
:root{--paper:#faf8f4;--surface:#fff;--ink:#17140e;--body:#3c372e;--muted:#77705f;--rule:#e4dfd3;
 --bull:#0f8a10;--bear:#c33a3a;--range:#c98500}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--paper:#14120e;--surface:#1c1a15;
 --ink:#f6f2e9;--body:#ccc5b6;--muted:#938b78;--rule:#2e2b23;--bull:#35b436;--bear:#e46a6a;--range:#e2a52a}}
:root[data-theme="dark"]{--paper:#14120e;--surface:#1c1a15;--ink:#f6f2e9;--body:#ccc5b6;--muted:#938b78;
 --rule:#2e2b23;--bull:#35b436;--bear:#e46a6a;--range:#e2a52a}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--body);font-family:"IBM Plex Sans",system-ui,sans-serif;
 font-size:15.5px;line-height:1.6}
.wrap{max-width:1240px;margin:0 auto;padding-block:48px 80px;padding-inline:24px}
.eyebrow{font-family:"IBM Plex Mono",monospace;font-size:11.5px;letter-spacing:.14em;text-transform:uppercase;
 color:var(--muted);margin:0 0 12px}
h1{font-family:"IBM Plex Serif",Georgia,serif;font-weight:600;font-size:clamp(26px,3.6vw,36px);color:var(--ink);
 margin:0 0 14px;text-wrap:balance}
.note{max-width:72ch;margin:0 0 30px}.note b{color:var(--ink)}
section{margin:0 0 36px}
h2{font-family:"IBM Plex Mono",monospace;font-size:12px;letter-spacing:.12em;text-transform:uppercase;
 color:var(--muted);font-weight:500;margin:0 0 6px}
.shape{font-family:"IBM Plex Mono",monospace;font-size:13px;margin:0 0 12px}
.r-bull{color:var(--bull)}.r-bear{color:var(--bear)}.r-range{color:var(--range)}
img{display:block;width:100%;height:auto;border:1px solid var(--rule);background:var(--surface)}
a.full{font-family:"IBM Plex Mono",monospace;font-size:12px;color:var(--muted)}
"""
    html = f"""<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;600&family=IBM+Plex+Serif:wght@600&display=swap">
<style>{css}</style>
<div class="wrap">
  <p class="eyebrow">Regime tracker · ES 5-minute</p>
  <h1>{title}</h1>
  <div class="note">{a.note}</div>
  <section><h2>{a.label_a}</h2><p class="shape">{sa}</p>
    <img src="data:image/png;base64,{ia}" alt="{a.label_a} chart"></section>
  <section><h2>{a.label_b}</h2><p class="shape">{sb}</p>
    <img src="data:image/png;base64,{ib}" alt="{a.label_b} chart"></section>
</div>
"""
    out.write_text(html, encoding="utf-8")
    print("wrote", out, "%.1f MB" % (out.stat().st_size / 1e6))


if __name__ == "__main__":
    main()

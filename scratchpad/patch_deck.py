import json, re, pathlib

P = pathlib.Path(r"C:\Users\Admin\AppData\Local\Temp\claude\c--Users-Admin-myquant"
                 r"\d54fb158-9ac4-48d2-916c-15358e2e88ff\scratchpad\atr_rule_slides.html")
s = P.read_text(encoding="utf-8")

# ---------- 1. gallery slide, before the evidence slide ----------
gallery = """
  <section class="slide">
    <p class="kicker">04 &mdash; six more, no cherry-picking</p>
    <h2>The same rule across volatility regimes</h2>
    <p class="lede">ATR spans <strong>2.5 to 12.3 points</strong> across these six sessions. The
      band widens and narrows with it &mdash; that is the point of using ATR rather than a fixed
      buffer. Top row cleared and ran; bottom row never cleared.</p>
    <div class="gal" id="gal"></div>
    <p class="foot">One example per session, chosen to span the ATR range &mdash; not selected on outcome.</p>
  </section>
"""
s = s.replace('  <section class="slide">\n    <p class="kicker">04 &mdash; the evidence</p>',
              gallery + '\n  <section class="slide">\n    <p class="kicker">05 &mdash; the evidence</p>')

# ---------- 2. trade slide, after the evidence slide ----------
trade = """
  <section class="slide">
    <p class="kicker">06 &mdash; does it make money?</p>
    <h2>Traded mechanically, it loses after costs</h2>
    <p class="lede">Enter at the clearing close. Stop back at the level (a failed breakout).
      Target = R &times; risk. Costs charged at <strong>1.25 ES points</strong> all-in &mdash; one
      tick of slippage plus commission.</p>
    <div class="scroll"><table id="tradeTbl"></table></div>
    <p class="foot">Every configuration is negative, at gamma levels and random levels alike. The
      stop sits ~1 ATR away by construction, win rates land at 33&ndash;56%, and costs take the rest.</p>
  </section>
"""
s = s.replace('  <section class="slide">\n    <p class="kicker">05 &mdash; the honest part</p>',
              trade + '\n  <section class="slide">\n    <p class="kicker">07 &mdash; the honest part</p>')

# ---------- 3. rewrite conclusion ----------
anchor = "<h2>It works. It just isn&rsquo;t about gamma.</h2>"
i = s.index(anchor); j = s.index("</section>", i)
new = """<h2>A strong statistic is not an edge</h2>
    <p class="lede">Two findings, pointing in different directions. Both matter.</p>
    <div class="row" id="ctrlStats"></div>
    <ul>
      <li><strong>The relationship is real.</strong> Clearing the band is followed by ~2.5&times;
        more movement &mdash; <strong>9 standard errors</strong>. That is not noise.</li>
      <li><strong>It is not gamma-specific.</strong> Random levels at the same distance give
        +2.32 ATR against the gamma level&rsquo;s +2.81. The advantage is
        <strong>+0.50 ATR (~1.4 se)</strong> &mdash; indistinguishable from zero.</li>
      <li><strong>And it is not tradeable as specified.</strong> Every stop/target configuration
        loses money after costs (slide 06).</li>
      <li><strong>Why all three can be true:</strong> &ldquo;cleared&rdquo; means price has already
        moved 1 ATR. Momentum persists &mdash; so the statistic is largely <em>selection</em>, not
        prediction. It describes what already happened rather than forecasting what comes next.</li>
    </ul>
    <blockquote><p>The same trap MenthorQ themselves warn about: their 0DTE condor at the 1D band
      won <b>77%</b> of the time and still lost money. A high conditional statistic and a
      profitable rule are different objects.</p></blockquote>
    <p class="foot">ES 5-min front-month, SPX-equivalent via daily basis. ATR(14) computed
      gap-adjusted &mdash; the first bar of an RTH session uses High&minus;Low, not the overnight
      gap. Levels are prior-session end-of-day. Internal research; not investment advice.</p>
    """
s = s[:i] + new + s[j:]

# ---------- 4. CSS ----------
s = s.replace("ul{margin:0;padding-left:20px;max-width:68ch}li{margin-bottom:8px}",
"""ul{margin:0;padding-left:20px;max-width:68ch}li{margin-bottom:8px}
.gal{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
.gal figure{margin:0}
.gal figcaption{font-family:var(--mono);font-size:10.5px;color:var(--mut);margin-top:5px;
 display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}
.gal .tag{font-weight:700}
.gal .tag.ok{color:var(--ok)} .gal .tag.no{color:var(--no)}
table{border-collapse:collapse;width:100%;font-size:13.5px;font-family:var(--mono)}
th,td{padding:8px 11px;border-bottom:1px solid var(--rule);text-align:right;
 font-variant-numeric:tabular-nums;white-space:nowrap}
th:first-child,td:first-child{text-align:left}
thead th{font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--mut);
 border-bottom:1px solid var(--fg);font-weight:600}
tbody tr:last-child td{border-bottom:none}
td.neg{color:var(--no)} .scroll{overflow-x:auto}""")

# ---------- 5. JS ----------
s = s.replace("function draw(){diagram();",
"""function gallery(){
  var G=D.gal, box=cv('gal');
  if(box.childElementCount===0){
    box.innerHTML=G.map(function(g,i){
      var tag=g.cleared
        ? '<span class="tag ok">CLEARED &middot; ran '+g.ft.toFixed(1)+' ATR</span>'
        : '<span class="tag no">PINNED &middot; range '+g.ft.toFixed(1)+' ATR</span>';
      return '<figure><canvas id="g'+i+'" height="190"></canvas><figcaption><span>'+g.sess+
        ' &middot; '+g.kind.toUpperCase()+' &middot; ATR '+g.atr.toFixed(2)+'</span>'+tag+'</figcaption></figure>';
    }).join('');
  }
  G.forEach(function(g,i){ candles(cv('g'+i),190,g,g.cleared); });
}
function tradeTbl(){
  var T=D.trade;
  cv('tradeTbl').innerHTML='<thead><tr><th>target</th><th>gamma win%</th><th>gamma expectancy</th>'+
   '<th>random win%</th><th>random expectancy</th></tr></thead><tbody>'+
   T.map(function(r){return '<tr><td>'+r.R.toFixed(1)+'R</td><td>'+r.gw.toFixed(1)+'%</td>'+
     '<td class="neg">'+r.ge.toFixed(3)+' R</td><td>'+r.rw.toFixed(1)+'%</td>'+
     '<td class="neg">'+r.re.toFixed(3)+' R</td></tr>';}).join('')+'</tbody>';
}
function draw(){diagram();gallery();tradeTbl();""")

# ---------- 6. data ----------
gal = json.load(open('scratchpad/atr_examples_multi.json', encoding='utf-8'))
trade_rows = [{"R":1.0,"gw":56.0,"ge":-0.038,"rw":54.8,"re":-0.066},
              {"R":1.5,"gw":46.8,"ge":-0.039,"rw":43.7,"re":-0.129},
              {"R":2.0,"gw":36.9,"ge":-0.159,"rw":36.9,"re":-0.183},
              {"R":3.0,"gw":33.3,"ge":-0.165,"rw":32.3,"re":-0.181}]
cur = json.loads(re.search(r'<script id="d" type="application/json">(.*?)</script>', s, re.S).group(1))
cur['gal'] = gal
cur['trade'] = trade_rows
cur['st']['stats']['cleared_med'] = 3.47
cur['st']['stats']['notcleared_med'] = 1.40
data = json.dumps(cur, separators=(',', ':'))
s = re.sub(r'(<script id="d" type="application/json">).*?(</script>)',
           lambda m: m.group(1) + data + m.group(2), s, flags=re.S)

# ---------- 7. corrected stat tiles + counter ----------
old_tiles = ("     stat(S.cleared_med.toFixed(2),'gamma level, cleared','ok')\n"
             "    +stat(S.rand_cleared_med.toFixed(2),'RANDOM level, cleared','')\n"
             "    +stat('+0.41','ATR advantage of the gamma level (~1.2 se)','acc');")
new_tiles = ("     stat('+2.81','ATR lift at GAMMA levels (9.1 se)','ok')\n"
             "    +stat('+2.32','ATR lift at RANDOM levels (14.5 se)','')\n"
             "    +stat('+0.50','gamma advantage (~1.4 se) - not significant','acc');")
assert old_tiles in s
s = s.replace(old_tiles, new_tiles)
s = s.replace('<span class="cnt" id="cnt">1 / 6</span>', '<span class="cnt" id="cnt">1 / 8</span>')

P.write_text(s, encoding="utf-8")
print("deck rebuilt:", P.stat().st_size // 1024, "KB")

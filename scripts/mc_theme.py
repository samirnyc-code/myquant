"""mc_theme.py — one shared 7-mode theme toggle for every Mission Control page.

A floating button (bottom-right) cycles dark -> light -> blue -> green -> red -> yellow ->
grey and back. The choice is saved in localStorage and applied on load BEFORE paint, so
there is no flash and it persists across every page and reload.

Injected verbatim before </body> of each page (launcher main + /health + /timeline +
/artifacts). It overrides the CSS custom properties the pages already use, so nothing else
has to change. Status colours (--pos/--good/--bad, the green/amber/red dots) are left
alone so health stays readable in every mode.
"""

# name -> core CSS variables. Kept semantic-neutral: bg/surface/text/border/muted only.
SNIPPET = """
<style>
#mcThemeBtn{position:fixed;right:14px;bottom:14px;z-index:9999;display:flex;align-items:center;
  gap:7px;background:var(--card,#161b22);color:var(--fg,#e6edf3);border:1px solid var(--chip,#30363d);
  border-radius:999px;padding:6px 13px 6px 10px;font:600 12px/1 -apple-system,Segoe UI,Roboto,sans-serif;
  cursor:pointer;box-shadow:0 4px 14px rgba(0,0,0,.35);opacity:.85;transition:opacity .15s,transform .1s}
#mcThemeBtn:hover{opacity:1;transform:translateY(-1px)}
#mcThemeBtn .sw{width:13px;height:13px;border-radius:50%;border:1px solid rgba(128,128,128,.5)}
</style>
<button id="mcThemeBtn" title="cycle theme (dark/light/blue/green/red/yellow/grey)">
  <span class="sw" id="mcThemeSw"></span><span id="mcThemeLbl">dark</span>
</button>
<script>
(function(){
  var THEMES = {
    dark:  {bg:'#0d1117',card:'#161b22',surface:'#161b22',chip:'#30363d',border:'#30363d',
            line:'#30363d',fg:'#e6edf3',ink:'#e6edf3',muted:'#8b949e',ink2:'#8b949e',sw:'#0d1117'},
    light: {bg:'#f6f7f9',card:'#ffffff',surface:'#ffffff',chip:'#e2e6ee',border:'#e2e6ee',
            line:'#e2e6ee',fg:'#161b24',ink:'#161b24',muted:'#5b6472',ink2:'#5b6472',sw:'#ffffff'},
    blue:  {bg:'#0a1628',card:'#10233d',surface:'#10233d',chip:'#1e3f66',border:'#1e3f66',
            line:'#1e3f66',fg:'#dbe9fb',ink:'#dbe9fb',muted:'#7fa2ca',ink2:'#7fa2ca',sw:'#1e6fe0'},
    green: {bg:'#08150e',card:'#0e2418',surface:'#0e2418',chip:'#1c4630',border:'#1c4630',
            line:'#1c4630',fg:'#d6f5e4',ink:'#d6f5e4',muted:'#6fb089',ink2:'#6fb089',sw:'#1f9d57'},
    red:   {bg:'#180b0b',card:'#2a1414',surface:'#2a1414',chip:'#4a2020',border:'#4a2020',
            line:'#4a2020',fg:'#f6dede',ink:'#f6dede',muted:'#c78a8a',ink2:'#c78a8a',sw:'#d24a3f'},
    yellow:{bg:'#171307',card:'#28220f',surface:'#28220f',chip:'#49401c',border:'#49401c',
            line:'#49401c',fg:'#f5ecd0',ink:'#f5ecd0',muted:'#b8a566',ink2:'#b8a566',sw:'#e6a94a'},
    grey:  {bg:'#181818',card:'#232323',surface:'#232323',chip:'#393939',border:'#393939',
            line:'#393939',fg:'#e9e9e9',ink:'#e9e9e9',muted:'#8f8f8f',ink2:'#8f8f8f',sw:'#7a7a7a'}
  };
  var ORDER = ['dark','light','blue','green','red','yellow','grey'];
  function apply(name){
    var t = THEMES[name] || THEMES.dark, r = document.documentElement.style;
    for (var k in t){ if(k!=='sw') r.setProperty('--'+k, t[k]); }
    document.documentElement.setAttribute('data-theme', (name==='light')?'light':'dark');
    var sw=document.getElementById('mcThemeSw'), lbl=document.getElementById('mcThemeLbl');
    if(sw) sw.style.background=t.sw;
    if(lbl) lbl.textContent=name;
  }
  window.__mcTheme = localStorage.getItem('mcTheme') || 'dark';
  // apply immediately (button labels get set once DOM is ready)
  apply(window.__mcTheme);
  // CROSS-PAGE LIVE SYNC: changing the theme on ANY open Mission Control tab writes
  // localStorage, which fires a 'storage' event in every OTHER tab - apply it there too,
  // so all open pages recolour together without a reload.
  window.addEventListener('storage', function(e){
    if(e.key==='mcTheme' && e.newValue){ window.__mcTheme=e.newValue; apply(e.newValue); }
  });
  document.addEventListener('DOMContentLoaded', function(){
    apply(window.__mcTheme);
    var b=document.getElementById('mcThemeBtn');
    if(b) b.onclick=function(){
      var i=(ORDER.indexOf(window.__mcTheme)+1)%ORDER.length;
      window.__mcTheme=ORDER[i]; localStorage.setItem('mcTheme',window.__mcTheme); apply(window.__mcTheme);
    };
  });
})();
</script>
"""

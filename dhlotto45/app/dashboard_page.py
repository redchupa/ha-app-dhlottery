"""
dashboard_page.py
Sidebar (Ingress) dashboard HTML. main.py's GET / fills in the placeholders:
__NONCE__ (CSP nonce), __CSRF__ (purchase/prefs token), __VERSION__, __THEME__ (initial theme,
whitelisted) and __PREFS_JSON__ (saved preferences, JSON with '<' escaped).

- All data comes from api/dashboard and is rendered with textContent only (no innerHTML -> no XSS).
- Scripts and styles run only via the CSP nonce; element.style (CSSOM) is used for swatches.
- Relative URLs (api/...) so it works under the Ingress path /api/hassio_ingress/<token>/.
- Design concept: "lucky 1st-prize ticket" - glossy draw balls, ticket stubs, next-draw countdown,
  gold glow and confetti for winning tickets. Themes follow the Good Tools pattern (grouped, KO/EN).
"""

PAGE_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko" data-theme="__THEME__">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="dhl-csrf" content="__CSRF__">
<title>DH Lotto 45</title>
<script type="application/json" id="dhl-prefs" nonce="__NONCE__">__PREFS_JSON__</script>
<style nonce="__NONCE__">
/* ================================================================ tokens */
:root {
  --bg: #f4f6fb; --card: #ffffff; --ink: #1d2330; --muted: #667085; --line: #e4e7ee; --chip: #eef1f7;
  --accent: #4f46e5; --accent-ink: #ffffff; --accent2: #06b6d4;
  --hero: linear-gradient(135deg, #4f46e5 0%, #2563eb 55%, #06b6d4 100%); --hero-ink: #ffffff;
  --win: #16a34a; --lose: #dc2626; --wait: #8a93a0; --gold: #d4a017;
  --shadow: 0 1px 2px rgba(16,24,40,.05), 0 2px 8px rgba(16,24,40,.06);
  --pattern: none; --radius: 16px; --gap: 14px; --pad: 16px;
}
:root[data-theme="dark"] {
  --bg: #0b1120; --card: #131c2e; --ink: #e6e9f2; --muted: #94a3b8; --line: #24304a; --chip: #1b2640;
  --accent: #818cf8; --accent-ink: #0b1020; --accent2: #22d3ee;
  --hero: linear-gradient(135deg, #312e81 0%, #1e3a8a 55%, #0e7490 100%);
  --win: #4ade80; --lose: #f87171; --wait: #8a93a0; --gold: #fbbf24; --shadow: none;
}
@media (prefers-color-scheme: dark) {
  :root[data-theme="system"] {
    --bg: #0b1120; --card: #131c2e; --ink: #e6e9f2; --muted: #94a3b8; --line: #24304a; --chip: #1b2640;
    --accent: #818cf8; --accent-ink: #0b1020; --accent2: #22d3ee;
    --hero: linear-gradient(135deg, #312e81 0%, #1e3a8a 55%, #0e7490 100%);
    --win: #4ade80; --lose: #f87171; --gold: #fbbf24; --shadow: none;
  }
}
:root[data-theme="ha-blue"] {
  --bg: #f0f8ff; --chip: #e3f2fd; --line: #d6e7f5; --accent: #0284c7; --accent2: #22d3ee;
  --hero: linear-gradient(135deg, #0284c7 0%, #0ea5e9 55%, #22d3ee 100%);
}
/* ---- lucky group */
:root[data-theme="jackpot-gold"] {
  --bg: #0d0b07; --card: #17130b; --ink: #f6ecd2; --muted: #b8a77e; --line: #3a2f17; --chip: #221b0e;
  --accent: #f5c542; --accent-ink: #1a1406; --accent2: #ffde7a;
  --hero: linear-gradient(135deg, #2b1f05 0%, #8a6410 45%, #f5c542 100%); --hero-ink: #fff8e1;
  --win: #ffd54a; --lose: #e57373; --wait: #9c8f70; --gold: #ffd54a; --shadow: 0 0 0 1px rgba(245,197,66,.08);
  --pattern: radial-gradient(rgba(245,197,66,.10) 1px, transparent 1.5px);
}
:root[data-theme="clover"] {
  --bg: #f1faf3; --card: #ffffff; --ink: #173022; --muted: #5d7a66; --line: #d5ead9; --chip: #e7f6ea;
  --accent: #16a34a; --accent2: #84cc16;
  --hero: linear-gradient(135deg, #14532d 0%, #16a34a 50%, #a3e635 100%);
  --pattern: radial-gradient(rgba(22,163,74,.12) 1.5px, transparent 2px);
}
:root[data-theme="lucky-red"] {
  --bg: #fff6f2; --card: #ffffff; --ink: #3b1110; --muted: #8a5a55; --line: #f3d6cf; --chip: #fdebe6;
  --accent: #c8102e; --accent2: #f5b700; --gold: #c99700;
  --hero: linear-gradient(135deg, #7a0610 0%, #c8102e 50%, #f5b700 100%);
  --pattern: radial-gradient(rgba(245,183,0,.16) 1.5px, transparent 2px);
}
:root[data-theme="golden-pig"] {
  --bg: #fff7f9; --card: #ffffff; --ink: #3d2230; --muted: #8b6577; --line: #f6d8e4; --chip: #ffe9f1;
  --accent: #e0457b; --accent2: #f5b301;
  --hero: linear-gradient(135deg, #f472b6 0%, #fb7185 45%, #fbbf24 100%);
  --pattern: radial-gradient(rgba(244,114,182,.14) 1.5px, transparent 2px);
}
:root[data-theme="lotto-pop"] {
  --bg: #fbfbff; --card: #ffffff; --ink: #1f2233; --muted: #6b6f85; --line: #e6e7f2; --chip: #f1f2f8;
  --accent: #ef4444; --accent2: #3fa9de;
  --hero: linear-gradient(110deg, #e0ad00 0%, #3fa9de 28%, #e5534b 52%, #8a8f98 74%, #79b33a 100%);
  --pattern: radial-gradient(rgba(63,169,222,.10) 2px, transparent 2.5px);
}
:root[data-theme="lotto-pop"] .hero, :root[data-theme="golden-pig"] .hero, :root[data-theme="clover"] .hero { text-shadow: 0 1px 3px rgba(0,0,0,.35); }
/* ---- night group */
:root[data-theme="neon-draw"] {
  --bg: #07060f; --card: #110f22; --ink: #eae6ff; --muted: #a49fc7; --line: #2a2550; --chip: #1a1735;
  --accent: #22d3ee; --accent-ink: #06121a; --accent2: #e879f9;
  --hero: linear-gradient(135deg, #0e7490 0%, #7c3aed 55%, #db2777 100%);
  --win: #5eead4; --lose: #fb7185; --gold: #fde047; --shadow: 0 0 0 1px rgba(34,211,238,.10), 0 0 24px rgba(124,58,237,.10);
}
:root[data-theme="aurora"] {
  --bg: #071417; --card: #0f2125; --ink: #e2f3f1; --muted: #8fb3ad; --line: #1d3a3f; --chip: #15302f;
  --accent: #2dd4bf; --accent-ink: #04201c; --accent2: #a78bfa;
  --hero: linear-gradient(135deg, #0f766e 0%, #14b8a6 40%, #7c3aed 100%);
  --win: #5eead4; --lose: #fb7185; --gold: #fcd34d; --shadow: none;
}
:root[data-theme="galaxy"] {
  --bg: #070a1a; --card: #10152c; --ink: #e8e6ff; --muted: #9ea3c9; --line: #232a4d; --chip: #181f3d;
  --accent: #a78bfa; --accent-ink: #120a2a; --accent2: #fbbf24;
  --hero: linear-gradient(135deg, #1e1b4b 0%, #4c1d95 55%, #be185d 100%);
  --win: #86efac; --lose: #fda4af; --gold: #fcd34d; --shadow: none;
  --pattern: radial-gradient(rgba(255,255,255,.16) 1px, transparent 1.5px);
}
:root.compact { --gap: 10px; --pad: 12px; --radius: 12px; }

/* ================================================================ base */
* { box-sizing: border-box; }
html, body { margin: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.6 "Pretendard", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans KR", "Apple SD Gothic Neo", sans-serif; }
body { background-image: var(--pattern); background-size: 22px 22px; min-height: 100vh; }
button, input, select { font: inherit; color: inherit; }
.mono { font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }

header { position: sticky; top: 0; z-index: 10; background: color-mix(in srgb, var(--card) 88%, transparent);
  backdrop-filter: blur(10px); border-bottom: 1px solid var(--line); }
.bar { max-width: 1240px; margin: 0 auto; padding: 10px 16px; display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.brand { display: flex; align-items: center; gap: 10px; font-weight: 800; font-size: 17px; letter-spacing: -.01em; }
.logo { width: 32px; height: 32px; border-radius: 10px; background: var(--hero); display: grid; place-items: center; font-size: 17px; }
.ver { color: var(--muted); font-size: 12px; font-weight: 500; }
.tabs { display: flex; gap: 6px; flex-wrap: wrap; }
.tab { border: 1px solid var(--line); background: var(--chip); border-radius: 999px; padding: 5px 12px; cursor: pointer; }
.tab[aria-selected="true"] { background: var(--accent); color: var(--accent-ink); border-color: var(--accent); }
.spacer { flex: 1; }
.tool { border: 1px solid var(--line); background: var(--card); border-radius: 10px; padding: 6px 11px; cursor: pointer; display: inline-flex; gap: 6px; align-items: center; }
.tool .sw { width: 14px; height: 14px; border-radius: 50%; border: 1px solid var(--line); }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }
.dot.on { background: var(--win); } .dot.off { background: var(--lose); }
main { max-width: 1240px; margin: 0 auto; padding: 16px; }

/* ================================================================ hero */
.hero { position: relative; overflow: hidden; border-radius: calc(var(--radius) + 6px); background: var(--hero); color: var(--hero-ink);
  padding: 22px 24px; margin-bottom: var(--gap); display: grid; grid-template-columns: 1.1fr 1fr auto; gap: 18px; align-items: center; }
.hero-art { width: 190px; height: auto; margin: -14px -8px -22px 0; filter: drop-shadow(0 10px 18px rgba(0,0,0,.28)); }
.logo-img { width: 34px; height: 34px; display: block; filter: drop-shadow(0 2px 4px rgba(0,0,0,.2)); }
.hero[hidden] { display: none; }
.hero::before { content: ""; position: absolute; inset: 0; pointer-events: none;
  background: radial-gradient(circle at 85% -10%, rgba(255,255,255,.35), transparent 45%), radial-gradient(circle at 0% 120%, rgba(255,255,255,.18), transparent 40%); }
.hero > * { position: relative; }
.hero h2 { margin: 0; font-size: 24px; font-weight: 800; letter-spacing: -.02em; }
.hero .msg { margin: 6px 0 14px; opacity: .92; font-size: 15px; min-height: 22px; }
.counts { display: flex; flex-wrap: wrap; gap: 8px; }
.count { background: rgba(255,255,255,.16); border: 1px solid rgba(255,255,255,.25); border-radius: 12px; padding: 8px 12px; min-width: 150px; }
.count .k { font-size: 12px; opacity: .85; } .count .v { font-size: 17px; font-weight: 800; font-variant-numeric: tabular-nums; }
.hero-right { display: flex; flex-direction: column; align-items: flex-end; gap: 10px; }
.hero-right .lbl { font-size: 12px; opacity: .9; }
.hero-balls { display: flex; flex-wrap: wrap; gap: 6px; justify-content: flex-end; align-items: center; }
.prize { font-size: 13px; opacity: .95; } .prize b { font-size: 20px; font-weight: 800; }
.hero .ball { width: 40px; height: 40px; font-size: 15px; }

/* ================================================================ cards */
.notice { border-radius: 12px; padding: 10px 14px; margin-bottom: 12px; border: 1px solid var(--line); background: var(--card); }
.notice.warn { border-color: #f0c36d; background: color-mix(in srgb, #f0c36d 16%, var(--card)); }
.notice.err { border-color: #ef9a9a; background: color-mix(in srgb, #ef9a9a 16%, var(--card)); }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: var(--gap); }
.card { background: var(--card); border: 1px solid var(--line); border-radius: var(--radius); padding: var(--pad); box-shadow: var(--shadow); min-width: 0; }
.card h3 { font-size: 16px; margin: 0 0 12px; display: flex; align-items: center; gap: 10px; letter-spacing: -.01em; }
.card h3 .ic-img { width: 40px; height: 40px; flex: none; filter: drop-shadow(0 3px 6px rgba(0,0,0,.18)); }
.card h3 .ttl { min-width: 0; }
.card h3 .ic { font-size: 16px; }
.card h3 .sub { color: var(--muted); font-weight: 500; font-size: 12.5px; }
.kv { display: grid; grid-template-columns: auto 1fr; gap: 6px 14px; margin: 10px 0 0; }
.kv dt { color: var(--muted); } .kv dd { margin: 0; text-align: right; font-variant-numeric: tabular-nums; }
.big { font-size: 26px; font-weight: 800; letter-spacing: -.02em; }
.hint { color: var(--muted); font-size: 13px; line-height: 1.55; }
.luck { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; margin-top: 6px; }
.luck b { font-size: 30px; font-weight: 800; color: var(--gold); line-height: 1.1; }
.luck span { font-size: 14px; font-weight: 700; }
.gauge { position: relative; height: 12px; border-radius: 999px; background: var(--chip); overflow: hidden; margin: 8px 0 6px; }
.gauge > i { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 999px; background: linear-gradient(90deg, #3fa9de, var(--gold)); }
.gauge.over > i { background: var(--lose); }
.gauge > em { position: absolute; top: 0; bottom: 0; width: 2px; background: var(--ink); opacity: .5; }
.claim { display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; padding: 8px 10px; border-radius: 10px; background: var(--chip); margin-top: 6px; font-size: 13px; }
.claim.visit { border-left: 4px solid var(--lose); }
.claim .dd { font-weight: 800; white-space: nowrap; }
.rows { display: flex; flex-direction: column; gap: 8px; }
.row { display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-radius: 12px; background: var(--chip); min-width: 0; border: 1px solid transparent; }
.compact .row { padding: 6px 8px; }
.row .idx { color: var(--muted); width: 18px; text-align: center; font-variant-numeric: tabular-nums; flex: none; }
.row .main { flex: 1; min-width: 0; display: flex; flex-wrap: wrap; gap: 5px; align-items: center; }
.row .res { font-size: 12px; white-space: nowrap; font-weight: 700; }
.row.won { border-color: var(--gold); background: color-mix(in srgb, var(--gold) 14%, var(--chip));
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--gold) 40%, transparent), 0 0 18px color-mix(in srgb, var(--gold) 30%, transparent); }
.empty { color: var(--muted); padding: 6px 2px; }
.r-win { color: var(--win); } .r-lose { color: var(--lose); } .r-wait { color: var(--wait); } .r-gold { color: var(--gold); }

/* lotto ball: glossy 3D by default */
.ball { --c: #8a8f98; width: 30px; height: 30px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center;
  font-weight: 800; font-size: 12px; color: #fff; text-shadow: 0 1px 1px rgba(0,0,0,.35); flex: none;
  background: radial-gradient(circle at 32% 28%, rgba(255,255,255,.95) 0 8%, rgba(255,255,255,.35) 18%, rgba(255,255,255,0) 42%), var(--c);
  box-shadow: inset -3px -4px 8px rgba(0,0,0,.25), inset 2px 2px 4px rgba(255,255,255,.25), 0 2px 4px rgba(0,0,0,.18); }
.flat .ball { background: var(--c); box-shadow: none; text-shadow: none; }
.ball.y { --c: #e0ad00; } .ball.b { --c: #3fa9de; } .ball.r { --c: #e5534b; } .ball.g { --c: #8a8f98; } .ball.l { --c: #79b33a; }
.ball.hit { outline: 3px solid var(--gold); outline-offset: 1px; }
.plus { color: var(--muted); margin: 0 2px; font-weight: 700; }
.hero .plus { color: inherit; opacity: .8; }

/* pension ticket stub */
.ticket { display: inline-flex; align-items: center; gap: 8px; position: relative; padding: 4px 12px 4px 10px; border-radius: 8px;
  background: var(--card); border: 1px dashed var(--line); }
.ticket .grp { font-weight: 800; color: var(--accent); font-size: 13px; }
.ticket .num { font-size: 16px; font-weight: 700; letter-spacing: .14em; }
.hero .ticket { background: rgba(255,255,255,.18); border-color: rgba(255,255,255,.45); color: inherit; }
.hero .ticket .grp { color: inherit; }

/* buy */
.sect { font-size: 13px; margin: 14px 0 8px; color: var(--muted); font-weight: 700; display: flex; align-items: center; gap: 6px; }
.sect:first-child { margin-top: 0; }
.btns { display: flex; flex-wrap: wrap; gap: 8px; }
.btn { border: 0; border-radius: 11px; padding: 9px 14px; font-weight: 700; cursor: pointer; background: var(--accent); color: var(--accent-ink);
  box-shadow: 0 2px 0 color-mix(in srgb, var(--accent) 55%, #000); transition: transform .08s ease; }
.btn:active { transform: translateY(1px); }
.btn.secondary { background: var(--chip); color: var(--ink); border: 1px solid var(--line); box-shadow: none; }
.btn.lucky { background: linear-gradient(135deg, var(--accent2), var(--accent)); color: var(--accent-ink); }
.btn:disabled { opacity: .45; cursor: not-allowed; }
.manual { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; align-items: center; }
.manual input, .manual select, .field input, .field select { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 8px 10px; min-width: 0; }
.manual input.lotto { flex: 1 1 200px; }
.manual input.pnum { width: 120px; letter-spacing: .12em; }
.preview { display: flex; gap: 5px; margin-top: 8px; flex-wrap: wrap; }
.preview:empty { display: none; }
.status { margin-top: 12px; padding: 8px 10px; border-radius: 10px; background: var(--chip); font-size: 13px; }
.status.running { color: var(--gold); } .status.success { color: var(--win); } .status.error, .status.skipped { color: var(--lose); }

/* celebration */
.celebrate { position: relative; overflow: hidden; border-radius: var(--radius); padding: 14px 18px; margin-bottom: var(--gap);
  background: linear-gradient(135deg, color-mix(in srgb, var(--gold) 70%, #fff), var(--gold)); color: #2b2005; font-weight: 800; }
.celebrate.jackpot { font-size: 20px; padding: 20px 22px; background: linear-gradient(135deg, #fff1b8, #ffd54a 40%, #f59e0b); }
.celebrate small { display: block; font-weight: 600; opacity: .8; font-size: 13px; }
.celebrate { display: flex; align-items: center; gap: 14px; }
.celebrate .cel-img { width: 58px; height: 58px; flex: none; position: relative; }
.celebrate.jackpot .cel-img { width: 128px; height: auto; margin: -8px 0; }
.celebrate .cel-text { position: relative; min-width: 0; }
.empty.art { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 6px 0 2px; text-align: center; }
.empty.art img { width: 112px; height: auto; opacity: .95; }
.notice.has-art { display: flex; align-items: center; gap: 12px; }
.notice .notice-img { width: 76px; height: auto; flex: none; }
.confetti { position: absolute; top: -12px; width: 8px; height: 12px; border-radius: 2px; opacity: .9; animation: fall 2.6s linear infinite; }
@keyframes fall { to { transform: translateY(140px) rotate(540deg); opacity: 0; } }
@keyframes pop { 0% { transform: scale(.4) rotate(-30deg); opacity: 0; } 70% { transform: scale(1.15); } 100% { transform: none; opacity: 1; } }
.rolling .ball { animation: pop .35s ease both; }
@media (prefers-reduced-motion: reduce) { .confetti { display: none; } .rolling .ball { animation: none; } }
.noeffects .confetti { display: none; } .noeffects .rolling .ball { animation: none; }

/* modal + drawer */
.modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,.5); display: none; align-items: center; justify-content: center; z-index: 30; padding: 16px; }
.modal-bg.show { display: flex; }
.modal { background: var(--card); border-radius: 18px; padding: 20px; width: 100%; max-width: 400px; border: 1px solid var(--line); }
.modal h4 { margin: 0 0 8px; font-size: 17px; }
.modal p { margin: 0 0 16px; color: var(--muted); }
.modal .amt { color: var(--ink); font-weight: 800; }
.modal .btns { justify-content: flex-end; }
.drawer-bg { position: fixed; inset: 0; background: rgba(0,0,0,.35); display: none; z-index: 25; }
.drawer-bg.show { display: block; }
.drawer { position: fixed; top: 0; right: 0; bottom: 0; width: min(420px, 100vw); background: var(--card); border-left: 1px solid var(--line);
  z-index: 26; transform: translateX(105%); transition: transform .2s ease; overflow-y: auto; padding: 18px 18px 28px; visibility: hidden; }
.drawer.show { transform: none; visibility: visible; }
.drawer h4 { margin: 0; font-size: 18px; }
.drawer h5 { margin: 18px 0 8px; font-size: 13px; color: var(--muted); }
.drawer .hint { margin: 8px 0 6px; }
.themes { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.theme { border: 1px solid var(--line); border-radius: 12px; padding: 8px; cursor: pointer; background: var(--chip); text-align: left; font-size: 12px; }
.theme[aria-pressed="true"] { border-color: var(--accent); box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 40%, transparent); }
.theme .sw { display: block; height: 26px; border-radius: 8px; margin-bottom: 6px; border: 1px solid rgba(0,0,0,.08); }
.seg { display: inline-flex; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
.seg button { border: 0; background: transparent; padding: 6px 12px; cursor: pointer; }
.seg button[aria-pressed="true"] { background: var(--accent); color: var(--accent-ink); }
.field { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 6px 0; }
.field input[type=text] { flex: 1; }
.cardlist { display: flex; flex-direction: column; gap: 6px; }
.cardlist .item { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 10px; background: var(--chip); }
.cardlist .item span { flex: 1; }
.mini { border: 1px solid var(--line); background: var(--card); border-radius: 8px; padding: 2px 8px; cursor: pointer; }
.mini:disabled { opacity: .35; cursor: default; }
.saved { font-size: 12px; color: var(--muted); min-height: 18px; }
.notice .closed { margin-top: 4px; line-height: 1.5; }
.notice.ok { border-color: #8bd3a0; background: color-mix(in srgb, #8bd3a0 16%, var(--card)); }
.btn.small { padding: 6px 10px; font-size: 13px; border-radius: 9px; }
.row.fav { flex-wrap: wrap; row-gap: 8px; }
.row.fav .fname { flex: 1 1 auto; min-width: 0; font-weight: 700; font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row.fav .main { order: 5; flex: 1 1 100%; }
.ticket { white-space: nowrap; }
.ball.q { background: var(--chip); color: var(--muted); border: 1px dashed var(--line); box-shadow: none; }
.genopts { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; font-size: 12px; margin-top: 8px; }
.genopts label { display: inline-flex; gap: 4px; align-items: center; background: var(--chip); border-radius: 8px; padding: 4px 8px; cursor: pointer; }
.genopts select { background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 4px 6px; }
.bars { display: flex; align-items: flex-end; gap: 4px; height: 120px; margin: 12px 0 4px; }
.bcol { flex: 1; display: flex; flex-direction: column; align-items: center; height: 100%; min-width: 0; }
.bstack { flex: 1; width: 100%; display: flex; align-items: flex-end; justify-content: center; gap: 2px; }
.sbar { width: 42%; min-height: 2px; border-radius: 4px 4px 0 0; }
.sbar.spend { background: color-mix(in srgb, var(--ink) 38%, transparent); } .sbar.win { background: var(--gold); }
.blbl { font-size: 11px; color: var(--muted); margin-top: 3px; }
.legend { display: flex; gap: 12px; font-size: 12px; color: var(--muted); margin-bottom: 6px; }
.legend i { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 4px; vertical-align: -1px; }
.days { display: flex; gap: 4px; flex-wrap: wrap; }
.days button { border: 1px solid var(--line); background: var(--card); color: var(--ink); border-radius: 8px; padding: 5px 9px; cursor: pointer; }
.days button[aria-pressed="true"] { background: var(--accent); color: var(--accent-ink); border-color: transparent; }
.sched { display: flex; align-items: center; gap: 8px; padding: 7px 9px; border-radius: 10px; background: var(--chip); font-size: 13px; }
.sched span { flex: 1; min-width: 0; }
.sched.off span { opacity: .5; }
.field.strong > span { font-weight: 800; }
.manual input[type=time] { width: 110px; }
textarea.diag { display: block; width: 100%; height: 240px; font-size: 11px; margin-top: 8px; background: var(--chip); color: var(--ink);
  border: 1px solid var(--line); border-radius: 10px; padding: 8px; resize: vertical; }
.picker-wrap { margin-top: 8px; padding: 10px; border-radius: 12px; background: var(--chip); border: 1px solid var(--line); }
.picker-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; font-size: 12px; color: var(--muted); }
.picker-grid { display: grid; grid-template-columns: repeat(9, 1fr); gap: 5px; }
.pball { border: 1px solid var(--line); background: var(--card); color: var(--ink); border-radius: 999px; height: 32px; font-size: 12px; font-weight: 700; cursor: pointer; display: grid; place-items: center; transition: transform .1s ease, background .12s ease; }
.pball:hover { border-color: var(--accent); }
.pball[aria-pressed="true"] { border-color: transparent; color: #fff; transform: scale(1.06); box-shadow: 0 2px 6px rgba(0,0,0,.22); }
.pball[aria-pressed="true"].y { background: #e0ad00; color: #2b2005; }
.pball[aria-pressed="true"].b { background: #3fa9de; }
.pball[aria-pressed="true"].r { background: #e5534b; }
.pball[aria-pressed="true"].g { background: #79b33a; }
.pball[aria-pressed="true"].l { background: #8a8f98; }
.cooldown-pill { margin-bottom: 8px; padding: 8px 10px; border-radius: 10px; background: color-mix(in srgb, var(--gold) 18%, var(--card)); border: 1px solid color-mix(in srgb, var(--gold) 55%, var(--line)); font-size: 13px; font-weight: 700; color: var(--ink); }
.sim-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin: 10px 0; }
.sim-stat { background: var(--chip); border-radius: 10px; padding: 8px; text-align: center; }
.sim-stat b { display: block; font-size: 15px; color: var(--ink); }
.sim-stat span { font-size: 11px; color: var(--muted); }
.sim-ranks { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }
.sim-chip { background: var(--chip); border: 1px solid var(--line); border-radius: 999px; padding: 3px 9px; font-size: 12px; }
.sim-chip.hit { border-color: var(--gold); color: var(--gold); font-weight: 700; }
.inline-btn { margin-left: 8px; vertical-align: middle; }
@media (max-width: 520px) { .picker-grid { grid-template-columns: repeat(7, 1fr); } }
/* number stats heatmap */
.heat { display: grid; grid-template-columns: repeat(9, 1fr); gap: 5px; margin: 10px 0 6px; }
.heat .cell { position: relative; aspect-ratio: 1; border-radius: 10px; display: flex; flex-direction: column; align-items: center; justify-content: center;
  background: var(--chip); border: 1px solid var(--line); font-variant-numeric: tabular-nums; min-width: 0; }
.heat .cell b { font-size: 14px; line-height: 1; }
.heat .cell small { font-size: 11px; color: var(--muted); margin-top: 2px; }
.heat .cell.top { border-color: var(--gold); box-shadow: 0 0 0 1px var(--gold) inset; }
.heat-legend { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--muted); }
.heat-legend .scale { flex: 1; height: 8px; border-radius: 6px; }
.numlist { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; margin-top: 4px; }
.numlist .gap { font-size: 11px; color: var(--muted); margin-right: 6px; }
.btns.tight { display: flex; flex-wrap: wrap; gap: 6px; }
.mt8 { margin-top: 8px; } .mt10 { margin-top: 10px; }
/* receipt-style ticket */
.receipt { position: relative; background: #fffdf6; color: #2a2a2a; border-radius: 6px; padding: 16px 16px 14px; margin-top: 4px;
  font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace; box-shadow: 0 6px 18px rgba(0,0,0,.18);
  -webkit-mask: radial-gradient(circle 7px at 0 50%, transparent 98%, #000) left / 51% 100% no-repeat, radial-gradient(circle 7px at 100% 50%, transparent 98%, #000) right / 51% 100% no-repeat;
          mask: radial-gradient(circle 7px at 0 50%, transparent 98%, #000) left / 51% 100% no-repeat, radial-gradient(circle 7px at 100% 50%, transparent 98%, #000) right / 51% 100% no-repeat; }
.receipt + .receipt { margin-top: 14px; }
.receipt .rh { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; border-bottom: 2px solid #2a2a2a; padding-bottom: 6px; }
.receipt .rh b { font-size: 16px; letter-spacing: .02em; }
.receipt .rh span { font-size: 11px; color: #666; }
.receipt .rmeta { display: flex; justify-content: space-between; font-size: 11px; color: #555; margin: 6px 0 4px; }
.receipt .rline { display: flex; align-items: center; gap: 8px; padding: 5px 0; border-bottom: 1px dashed #c9c2ae; font-size: 14px; }
.receipt .rline:last-of-type { border-bottom: 0; }
.receipt .slot { width: 18px; font-weight: 800; }
.receipt .mode { width: 46px; font-size: 11px; color: #666; }
.receipt .nums { flex: 1; letter-spacing: .08em; font-weight: 700; word-spacing: 4px; }
.receipt .nums .q { color: #999; }
.receipt .rfoot { display: flex; justify-content: space-between; border-top: 2px solid #2a2a2a; margin-top: 6px; padding-top: 6px; font-size: 13px; font-weight: 800; }
.receipt .barcode { height: 34px; margin-top: 10px; border-radius: 2px; }
.receipt .rnote { font-size: 11px; color: #777; text-align: center; margin-top: 4px; }
/* mobile quick-jump bar */
#qnav { display: none; }
.card { scroll-margin-top: 150px; }
@media (max-width: 720px) {
  #qnav { display: flex; position: fixed; left: 0; right: 0; bottom: 0; z-index: 20; gap: 4px; overflow-x: auto; padding: 6px 8px calc(6px + env(safe-area-inset-bottom));
    background: color-mix(in srgb, var(--card) 92%, transparent); backdrop-filter: blur(10px); border-top: 1px solid var(--line); scrollbar-width: none; }
  #qnav::-webkit-scrollbar { display: none; }
  #qnav button { flex: none; display: flex; flex-direction: column; align-items: center; gap: 2px; min-width: 54px; padding: 4px 6px; border: 0; border-radius: 10px;
    background: transparent; color: var(--ink); font-size: 11px; cursor: pointer; }
  #qnav button img { width: 26px; height: 26px; }
  #qnav button.top { font-size: 18px; justify-content: center; }
  #qnav button:active { background: var(--chip); }
  main { padding-bottom: 86px; }
  footer { padding-bottom: 90px; }
}
/* collapsible cards and sections */
.card-head { display: flex; align-items: center; gap: 10px; width: 100%; padding: 0; margin: 0; border: 0; background: none; color: inherit;
  font: inherit; text-align: left; cursor: pointer; border-radius: 10px; min-height: 44px; }
.card-head:focus-visible, .fold-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
.card-head .ttl { font-weight: 800; }
.card-head .sub { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chev { margin-left: auto; flex: none; width: 28px; height: 28px; display: grid; place-items: center; border-radius: 8px; background: var(--chip);
  color: var(--muted); font-size: 14px; transition: transform .18s ease; }
.card.collapsed .chev, .fold:not(.open) > .fold-btn .chev { transform: rotate(-90deg); }
.card.collapsed h3 { margin-bottom: 0; }
.card.collapsed { padding-top: calc(var(--pad) - 4px); padding-bottom: calc(var(--pad) - 4px); }
.fold { margin-top: 10px; border: 1px dashed var(--line); border-radius: 12px; }
.fold-btn { display: flex; align-items: center; gap: 8px; width: 100%; padding: 10px 12px; border: 0; background: none; color: inherit;
  font: inherit; font-weight: 700; text-align: left; cursor: pointer; border-radius: 12px; min-height: 44px; }
.fold-body { padding: 0 12px 12px; }
.fold-body > .manual:first-child { margin-top: 0; }
@media (prefers-reduced-motion: reduce) { .chev { transition: none; } }
/* phone: bigger tap targets, 16px inputs (no iOS zoom), roomier text */
@media (max-width: 720px) {
  html, body { font-size: 15.5px; }
  .btn { min-height: 44px; padding: 10px 16px; }
  .btn.small { min-height: 40px; }
  .mini { min-height: 36px; min-width: 36px; padding: 6px 10px; }
  .tab { padding: 8px 14px; min-height: 40px; }
  .tool { min-height: 40px; }
  input, select, textarea { font-size: 16px !important; min-height: 44px; }
  .pball { height: 38px; font-size: 14px; }
  .row { padding: 10px 12px; }
  .hint { font-size: 13.5px; }
  #qnav button { font-size: 11px; min-height: 48px; }
}
footer { color: var(--muted); font-size: 12px; text-align: center; padding: 22px 16px 30px; }
@media (max-width: 900px) { .hero { grid-template-columns: 1.1fr 1fr; } .hero-art { display: none; } }
@media (max-width: 720px) { .hero { grid-template-columns: 1fr; } .hero-right { align-items: flex-start; } .hero-balls { justify-content: flex-start; } }
@media (max-width: 520px) { .notice .notice-img { width: 56px; } .celebrate.jackpot .cel-img { width: 84px; } }
@media (max-width: 420px) { .grid { grid-template-columns: 1fr; } .hero { padding: 18px; } .hero h2 { font-size: 20px; } .hero .ball { width: 34px; height: 34px; font-size: 13px; }
  .themes { grid-template-columns: repeat(2, 1fr); } .count { min-width: 0; flex: 1; } }
</style>
</head>
<body>
<header><div class="bar">
  <div class="brand"><img class="logo-img" src="static/img/logo.webp" alt="" width="34" height="34"><span>DH Lotto 45</span><span class="ver">v__VERSION__</span></div>
  <div class="tabs" id="tabs" role="tablist"></div>
  <span class="spacer"></span>
  <button class="tool" id="btn-lang" type="button"></button>
  <button class="tool" id="btn-theme" type="button"><span class="sw" id="theme-sw"></span><span id="theme-name"></span></button>
  <button class="tool" id="btn-reload" type="button"></button>
</div></header>
<main>
  <section class="hero" id="hero"></section>
  <div id="celebrate"></div>
  <div id="notices"></div>
  <div class="grid" id="grid"></div>
</main>
<footer id="footer"></footer>
<nav id="qnav" aria-label="quick jump"></nav>

<div class="modal-bg" id="modal" role="dialog" aria-modal="true" aria-labelledby="m-title">
  <div class="modal">
    <h4 id="m-title"></h4>
    <p id="m-body"></p>
    <div class="btns"><button class="btn secondary" id="m-cancel" type="button"></button><button class="btn" id="m-ok" type="button"></button></div>
  </div>
</div>
<div class="drawer-bg" id="drawer-bg"></div>
<aside class="drawer" id="drawer" aria-labelledby="d-title"></aside>

<script nonce="__NONCE__">
(function () {
  "use strict";
  var CSRF = document.querySelector('meta[name="dhl-csrf"]').getAttribute("content");
  var root = document.documentElement;

  // ------------------------------------------------------------ i18n
  var T = {
    ko: { reload: "↻ 새로고침", settings: "설정", lang: "EN", summary: "계정 요약", deposit: "예치금", available: "구매 가능 금액",
      login: "로그인", ok: "정상", fail: "실패", sync: "동기화", updatedAt: "마지막 갱신", buy: "구매하기",
      lottoCur: "로또 이번 회차", lottoPrev: "로또 지난 회차", penCur: "연금복권 이번 회차", penPrev: "연금복권 지난 회차",
      winning: "최신 당첨번호", none: "구매 내역 없음", weekly: "주간", games: "게임", tickets: "매", round: "회",
      winNums: "당첨번호", auto1: "자동 1게임", auto5: "자동 5게임", manual1: "수동 1게임", pAuto1: "자동 1매", pAuto5: "자동 5매", pManual: "수동 1매",
      luckyPick: "🍀 행운 번호 뽑기", manualHint: "6칸을 쉼표로 구분 · 자동으로 채울 칸은 auto (반자동)",
      running: "진행 중… (연금은 최대 1~2분)", confirmTitle: "구매 확인", cancel: "취소", confirm: "구매",
      confirmBody1: " 계정으로 ", confirmBody2: " 을(를) 구매합니다. 예치금에서 바로 결제됩니다.",
      lottoClosed: "🌙 지금은 로또 구매 불가 시간이에요 (매일 00:00~06:00, 토요일은 20:00부터)",
      closedBody: "이 시간에는 동행복권에서 예치금·구매 내역을 새로 조회하지 않아 마지막으로 불러온 값이 보여요. 06:00가 지나면 자동으로 다시 불러옵니다. 당첨번호와 통계는 계속 갱신돼요.",
      lottoName: "로또 복권", pensionName: "연금 복권", lottoShort: "로또", pensionShort: "연금",
      loginErr: "로그인 오류", lottoErr: "로또 구매 오류", penErr: "연금 구매 오류", loadFail: "불러오기 실패: ", buyFail: "구매 요청 실패: ",
      noAcc: "설정된 계정이 없습니다. 애드온 설정에서 계정을 추가하세요.", ingressOnly: "사이드바(Ingress)에서 열어야 볼 수 있습니다.",
      nextLotto: "로또 추첨까지", nextPension: "연금 추첨까지", day: "일", lastPrize: "지난 회차 1등 당첨금", latestDraw: "회 당첨번호",
      heroTitle: "오늘도 1등을 향해", bonus: "보너스", notLoaded: "당첨번호를 아직 불러오지 못했습니다",
      congrats: "🎉 축하합니다! 당첨 티켓이 있어요", jackpot: "🏆 1등 당첨! 축하합니다!", congratsSub: "지난 회차 결과를 확인하세요.",
      footer: "복권 구매는 만 19세 이상만 가능합니다. 구매 전 금액과 계정을 꼭 확인하세요.",
      sTheme: "테마", sLang: "언어", sDisplay: "표시", sCards: "카드 구성", sLucky: "나만의 행운 문구", sAccount: "기본 계정",
      density: "간격", comfortable: "넉넉하게", compact: "촘촘하게", ballStyle: "로또볼", glossy: "입체", flat: "평면",
      effects: "당첨 축하·애니메이션", showHero: "상단 행운 배너", luckyPh: "예: 이번 주는 내가 1등!", firstAcc: "첫 번째 계정",
      reset: "기본값으로", savedOk: "HA에 저장됨 · 모든 기기에 적용", saveFail: "저장 실패 (이 기기에만 적용됨)", close: "닫기",
      gBasic: "기본", gLucky: "행운", gNight: "밤하늘 · 미래", up: "위로", down: "아래로", groupSuffix: "조",
      favorites: "즐겨찾기 번호", favEmpty: "저장한 번호가 없습니다. 아래에서 추가하세요.", favName: "이름(선택)", favAdd: "추가",
      favBuy: "구매", favDel: "삭제", favLotto: "로또", favPension: "연금", favFromInput: "구매 카드 입력값", favInvalid: "번호 형식이 올바르지 않습니다 (로또 1,7,12,23,34,45 / 연금 3,123456).",
      stats: "지출 · 당첨 통계", statSpend: "구매", statWin: "당첨금", statRatio: "회수율", statSince: "기록 시작", statAll: "전체 계정", statThis: "이 계정",
      statWins: "최근 당첨", statNone: "아직 기록이 없습니다.", statNote: "애드온이 확인한 구매·당첨 기준입니다 (다른 곳에서 산 복권도 동기화되면 포함).",
      auto: "자동 구매 · 알림", autoMaster: "정기 자동 구매 사용", autoOnTitle: "정기 자동 구매 켜기", autoOn: "켜기",
      autoOnConfirm: "예약한 시각에 확인 창 없이 예치금에서 결제됩니다. 주간 5게임·연금 하루 한도·계정 간 20초 간격·판매 시간·예치금 확인은 그대로 적용됩니다. 켤까요?",
      autoAdd: "일정 추가", autoEmpty: "등록된 일정이 없습니다.", autoAllAcc: "모든 계정", autoDel: "일정 삭제",
      autoGuard: "보호 장치: 일정당 하루 1번 · 예약 후 10분 안에만 실행 · 판매 시간·로그인·예치금 확인 · 주간 5게임·연금 하루 한도·계정 간 20초",
      autoNeedDay: "요일을 하나 이상 고르세요.", dayNames: "월,화,수,목,금,토,일",
      notify: "알림", nPersistent: "HA 알림(종 모양)", nService: "모바일 알림 서비스", nServicePh: "notify.mobile_app_내폰", nWin: "당첨 알림",
      nPurchase: "구매 결과 알림", nLow: "예치금 부족 알림", nThreshold: "부족 기준(원)", nTest: "테스트 알림", nTestOk: "보냈습니다. HA 알림·휴대폰을 확인하세요.",
      nTestFail: "보내지 못했습니다. 알림 서비스 이름을 확인하세요.", nEvents: "자동화용 이벤트: dhlotto45_purchase · dhlotto45_win · dhlotto45_low_deposit · dhlotto45_weekly_report",
      insight: "럭키 랩", q_insight: "럭키랩", luckTitle: "운 지수", luckTop: "상위", luckNone: "추첨이 끝난 구매 기록이 쌓이면 운 지수를 계산합니다.",
      luck_legend: "🍀 전설급 행운", luck_lucky: "😊 운이 좋은 편", luck_average: "🙂 딱 평균", luck_unlucky: "😅 조금 아쉬운 편", luck_rain: "🌧️ 운이 쉬는 중",
      luckDetail: "추첨 끝난 로또 {g}게임·연금 {p}매 · 확률상 기대 당첨 {e}회 · 실제 {w}회 · 환급률 {r}%",
      luckJackpot: "지금 속도(주 {n}게임)라면 로또 1등 기대 시점은 약 {y}년 뒤입니다 (1등 확률 1/8,145,060).",
      luckNote: "운 지수 = 산 복권 수로 기대되는 당첨 횟수와 실제 당첨 횟수를 비교한 백분위(이항분포 정확 계산). 재미로 보는 통계이며 다음 추첨 확률은 바뀌지 않습니다.",
      budgetTitle: "이번 달 예산", budgetOff: "월 예산이 꺼져 있습니다 — ⏰ 설정에서 계정별 월 예산을 정하면 넘는 구매를 자동으로 막아 줍니다.",
      budgetUsed: "사용", budgetLeft: "남음", budgetOver: "예산을 다 썼습니다 — 이번 달 추가 구매는 막힙니다.",
      claimTitle: "당첨금 수령 도우미", claimNone: "직접 수령해야 할 당첨이 없습니다 (200만원 이하 인터넷 당첨금은 예치금으로 자동 지급).",
      claimVisit: "지급기한은 추첨일로부터 1년이며, 그날이 은행 휴무일(주말·공휴일)이면 다음 영업일까지입니다. 화면의 날짜는 주말만 반영했으니 공휴일과 겹치면 하루 이상 늘어납니다. 기한이 지나면 당첨금은 복권기금으로 귀속됩니다. (출처: 동행복권 이용안내·당첨자 가이드)",
      how_auto: "예치금 자동 지급", how_bank_branch: "🏦 농협은행 지점 방문 · 신분증·당첨 복권 번호", how_bank_hq: "🏦 농협은행 본점 방문 · 신분증·당첨 복권 번호",
      how_pension_office: "🏢 (주)동행복권 본사 방문 · 신분증 → 청구한 다음 달부터 매월 20일 지급",
      claimAuto: "예치금 자동 지급", claimExpired: "기한 지남", icsBtn: "📅 캘린더 받기 (.ics)",
      icsHint: "휴대폰 캘린더에 '로또 마감 2시간 전'·'당첨금 지급기한' 알림을 넣어 주는 파일입니다. 필요한지 모르겠다면 아래 안내를 펼쳐 보세요.",
      icsFold: "❓ 캘린더 받기는 언제 쓰나요? · 사용 방법",
      icsWhyT: "이런 분께 좋아요",
      icsWhy1: "• HA 알림을 안 쓰거나, 집 밖·HA가 꺼져 있을 때도 휴대폰 자체 알림으로 받고 싶은 분 — 일정과 알림이 휴대폰에 저장되어 HA·인터넷이 없어도 울립니다.",
      icsWhy2: "• 가족 공유 캘린더에 넣어 다른 가족도 마감·추첨·지급기한을 보게 하고 싶은 분.",
      icsWhy3: "• 고액 당첨이 있을 때 지급기한(1년)을 놓치지 않도록 30일·7일·1일 전 알림을 휴대폰에 확실히 남겨 두고 싶은 분.",
      icsSkipT: "안 써도 되는 경우",
      icsSkip: "⏰ 설정의 마감 알림·당첨금 수령 기한 알림·주간 리포트를 HA 앱(또는 카카오톡)으로 받고 있다면 내용이 거의 같으니 받지 않아도 됩니다.",
      icsWhatT: "파일에 들어가는 일정",
      icsWhat: "앞으로 8주 로또 판매 마감(토 20:00, 2시간 전 알림)·연금복권 추첨(목 19:05), 켜 둔 정기 자동 구매 일정(매주 반복), 직접 받아야 하는 당첨금의 지급기한(30·7·1일 전 알림).",
      icsHowT: "사용 방법",
      icsHow1: "① 위 '캘린더 받기' 버튼을 누르면 dhlotto45.ics 파일이 내려받아집니다. (HA 앱 안에서 저장이 안 되면 휴대폰·PC 웹 브라우저로 HA에 접속해 받으세요.)",
      icsHow2: "② 아이폰: 파일 앱에서 dhlotto45.ics 를 눌러 '모두 추가' → 넣을 캘린더 선택.",
      icsHow3: "③ 안드로이드(구글 캘린더): PC에서 calendar.google.com → 설정 ⚙️ → 가져오기 및 내보내기 → 파일 선택 → 캘린더 선택 → 가져오기. 휴대폰 구글 캘린더에 자동으로 나타납니다.",
      icsHow4: "④ 삼성 캘린더: 내 파일에서 dhlotto45.ics 를 눌러 삼성 캘린더로 열고 저장.",
      icsNoteT: "알아 두세요",
      icsNote: "받은 순간의 내용만 담기고 저절로 갱신되지 않습니다. 8주가 지나거나, 정기 구매 일정을 바꾸거나, 새로 고액 당첨되면 다시 받으세요. 다시 가져올 때는 'DH Lotto' 같은 별도 캘린더를 만들어 두고 그 캘린더를 비운 뒤 가져오면 일정이 겹치지 않습니다.",
      nWeekly: "📬 주간 리포트 (일요일 09시)", nDeadline: "⏰ 마감 알림 (토요일 18시, 이번 주 미구매 계정)", nClaim: "💰 당첨금 수령 기한 알림 (D-30·7·1)",
      nBudget: "💳 계정별 월 예산 (원, 0 = 끄기)", nBudgetHint: "예산을 넘는 구매는 대시보드·HA 버튼·정기 자동 구매 모두에서 막힙니다.",
      hhLabel: "🧾 가계부 자동 기록 (kr_ledger_kit)", hhHint: "kr_ledger_kit 통합이 있으면 구매는 지출, 당첨은 수입으로 회차별로 기록합니다 (카테고리: 복권).",
      hhMissing: "kr_ledger_kit 통합을 찾지 못했습니다 — 설치한 뒤 다시 켜 주세요.", hhOk: "가계부 연동이 켜졌습니다.",
      fairOk: "🔬 공정성 검정 (χ²={c}, p={p}, 번호 {n}개): 번호 쏠림은 우연 범위입니다 — 많이·적게 나온 번호는 다음 추첨에 영향이 없습니다.",
      fairSkew: "🔬 공정성 검정 (χ²={c}, p={p}, 번호 {n}개): 이 표본에서는 쏠림이 보이지만, 추첨은 매번 독립입니다.",
      diag: "🩺 진단 리포트 복사", diagCopied: "진단 리포트를 복사했습니다. 문의 글에 붙여넣으세요 (아이디·IP는 가려져 있음).",
      diagManual: "아래 내용을 전체 선택해 복사하세요 (아이디·IP는 가려져 있음).", diagTitle: "진단 리포트", sSupport: "문의 · 진단",
      genMode: "방식", genRandom: "완전 무작위", genHot: "자주 나온 번호 위주", genCold: "덜 나온 번호 위주", genMix: "자주+덜 섞기",
      genOdd: "홀짝 균형", genSum: "합계 100~175", genSeq: "3연속 제외", genNote: "어떤 방식이든 당첨 확률은 같습니다 (재미용).", saveErr: "저장 실패: ",
      relogin: "🔄 재로그인", reloginBusy: "로그인 중…", reloginOk: "세션을 갱신했습니다.", reloginFail: "재로그인 실패: ",
      cooldownWait: "⏳ 계정 간 보안 대기: ", cooldownSec: "초 후 구매 가능",
      receipt: "구매 용지", rcptLotto: "로또 복권 6/45", rcptPension: "연금 복권 720+", rcptDraw: "추첨", rcptTotal: "합계", rcptGames: "게임",
      rcptNote: "화면용 확인 용지입니다 (실제 복권 아님)", mAuto: "자동", mManual: "수동", mSemi: "반자동", rcptNone: "이번 회차 구매 내역이 없습니다.",
      numstats: "번호 통계", nsFreq: "출현 빈도", nsGap: "미출현 기간", nsRounds: "최근", nsHot: "많이 나온 번호", nsCold: "적게 나온 번호",
      nsAbsent: "오래 안 나온 번호", nsTimes: "회", nsAgo: "회 전", nsNever: "범위 밖", nsExpected: "평균 기대", nsTotal: "누적",
      nsNote: "보너스 번호 제외 · 과거 통계일 뿐 다음 추첨 확률은 모든 번호가 같습니다.", nsLoading: "통계를 불러오는 중…", nsFail: "번호 통계를 불러오지 못했습니다: ",
      exportCsv: "⬇ CSV 내보내기", exportJson: "⬇ 백업(JSON)", importJson: "⬆ 백업 가져오기", importOk: "가져오기 완료: 추가 ", importSkip: "건, 건너뜀 ", importFail: "가져오기 실패: ",
      exportFail: "내보내기 실패: ", qTop: "맨 위로",
      mqttDown: "📡 MQTT 브로커에 연결되지 않아 HA 센서·버튼이 갱신되지 않아요",
      mqttHow: "Mosquitto broker 애드온이 실행 중인지 확인하세요. 애드온 구성의 MQTT 아이디·비밀번호를 비워 두면 Mosquitto 가 이 애드온 전용 계정을 자동으로 줍니다. 연결되면 센서·버튼이 자동으로 다시 만들어지고, 이 화면의 구매는 MQTT 와 상관없이 됩니다.", expand: "펼치기", collapse: "접기",
      foldLotto: "✍️ 번호 직접 고르기 (수동·반자동)", foldPension: "✍️ 조·번호 직접 고르기 (수동)", foldSchedule: "➕ 일정 추가", foldNotify: "🔔 알림 설정",
      q_summary: "요약", q_buy: "구매", q_receipt: "용지", q_favorites: "즐겨찾기", q_lotto_current: "로또", q_lotto_prev: "지난 로또",
      q_pension_current: "연금", q_pension_prev: "지난 연금", q_winning: "당첨번호", q_numstats: "번호통계", q_stats: "지출통계", q_auto: "자동",
      pickerOpen: "🎱 번호판", pickerClose: "🎱 번호판 닫기", pickerClear: "초기화", pickerHint: "1~45 중 최대 6개 선택 (남은 칸은 자동)",
      simBtn: "🔍", simTitle: "과거 당첨 시뮬레이션", simLoading: "최근 50회차 당첨 이력을 조회 중…", simNone: "최근 50회차 중 5등 이상 당첨 이력이 없습니다.",
      simFail: "시뮬레이션 실패: ", simRounds: "검사 회차", simRank: "등", simNote: "1~3등은 추정 평균 상금 기준이며, 과거 결과는 미래 당첨을 보장하지 않습니다." },
    en: { reload: "↻ Refresh", settings: "Settings", lang: "KO", summary: "Account", deposit: "Deposit", available: "Available to buy",
      login: "Login", ok: "OK", fail: "Failed", sync: "Sync", updatedAt: "Last update", buy: "Buy tickets",
      lottoCur: "Lotto · this round", lottoPrev: "Lotto · last round", penCur: "Pension · this round", penPrev: "Pension · last round",
      winning: "Latest winning numbers", none: "No tickets", weekly: "Week", games: "games", tickets: " tickets", round: "",
      winNums: "Winning", auto1: "Auto 1 game", auto5: "Auto 5 games", manual1: "Manual 1 game", pAuto1: "Auto 1", pAuto5: "Auto 5", pManual: "Manual 1",
      luckyPick: "🍀 Lucky pick", manualHint: "6 values, comma separated · use auto to fill the rest",
      running: "in progress… (pension takes up to 1-2 min)", confirmTitle: "Confirm purchase", cancel: "Cancel", confirm: "Buy",
      confirmBody1: " will buy ", confirmBody2: ". It is paid from the deposit right away.",
      lottoClosed: "🌙 Lotto sales are closed now (daily 00:00-06:00, Saturday from 20:00 KST)",
      closedBody: "During this time the deposit and purchase history are not fetched from DH Lottery, so the last loaded values are shown. They refresh automatically after 06:00. Winning numbers and statistics keep updating.",
      lottoName: "Lotto 6/45", pensionName: "Pension 720+", lottoShort: "Lotto", pensionShort: "Pension",
      loginErr: "Login error", lottoErr: "Lotto purchase error", penErr: "Pension purchase error", loadFail: "Failed to load: ", buyFail: "Purchase request failed: ",
      noAcc: "No accounts configured. Add one in the add-on settings.", ingressOnly: "Open this from the Home Assistant sidebar (Ingress).",
      nextLotto: "Next lotto draw", nextPension: "Next pension draw", day: "d", lastPrize: "Last 1st prize", latestDraw: " · winning numbers",
      heroTitle: "Aim for the jackpot", bonus: "Bonus", notLoaded: "Winning numbers not loaded yet",
      congrats: "🎉 Congratulations! You have a winning ticket", jackpot: "🏆 1st prize! Congratulations!", congratsSub: "Check last round's results.",
      footer: "You must be 19 or older to buy lottery tickets. Check the amount and account before buying.",
      sTheme: "Theme", sLang: "Language", sDisplay: "Display", sCards: "Cards", sLucky: "My lucky message", sAccount: "Default account",
      density: "Spacing", comfortable: "Comfortable", compact: "Compact", ballStyle: "Lotto balls", glossy: "Glossy", flat: "Flat",
      effects: "Win celebration & animation", showHero: "Lucky banner", luckyPh: "e.g. This week is mine!", firstAcc: "First account",
      reset: "Reset", savedOk: "Saved to HA · applies on every device", saveFail: "Save failed (this device only)", close: "Close",
      gBasic: "Basic", gLucky: "Lucky", gNight: "Night & future", up: "Up", down: "Down", groupSuffix: "G",
      favorites: "Favorite numbers", favEmpty: "No saved numbers yet. Add one below.", favName: "Name (optional)", favAdd: "Add",
      favBuy: "Buy", favDel: "Delete", favLotto: "Lotto", favPension: "Pension", favFromInput: "Use buy-card input", favInvalid: "Invalid numbers (lotto 1,7,12,23,34,45 / pension 3,123456).",
      stats: "Spending & winnings", statSpend: "Spent", statWin: "Won", statRatio: "Return", statSince: "Since", statAll: "All accounts", statThis: "This account",
      statWins: "Recent wins", statNone: "No records yet.", statNote: "Based on purchases and wins the add-on has seen (tickets bought elsewhere count once synced).",
      auto: "Auto-buy & alerts", autoMaster: "Use scheduled auto-buy", autoOnTitle: "Turn on scheduled auto-buy", autoOn: "Turn on",
      autoOnConfirm: "Tickets will be paid from the deposit at the scheduled time without a confirmation dialog. Weekly 5 games, pension daily limit, 20 s between accounts, sales hours and deposit checks still apply. Turn it on?",
      autoAdd: "Add schedule", autoEmpty: "No schedules yet.", autoAllAcc: "All accounts", autoDel: "Delete schedule",
      autoGuard: "Safeguards: once per schedule per day · runs only within 10 min of the time · sales hours, login and deposit checks · weekly 5 games, pension daily limit, 20 s between accounts",
      autoNeedDay: "Pick at least one day.", dayNames: "Mon,Tue,Wed,Thu,Fri,Sat,Sun",
      notify: "Notifications", nPersistent: "HA notifications (bell)", nService: "Mobile notify service", nServicePh: "notify.mobile_app_my_phone", nWin: "Win alerts",
      nPurchase: "Purchase results", nLow: "Low deposit alerts", nThreshold: "Low deposit below (KRW)", nTest: "Send test", nTestOk: "Sent. Check HA notifications and your phone.",
      nTestFail: "Could not send. Check the notify service name.", nEvents: "Automation events: dhlotto45_purchase · dhlotto45_win · dhlotto45_low_deposit · dhlotto45_weekly_report",
      insight: "Lucky Lab", q_insight: "Lab", luckTitle: "Luck index", luckTop: "Top", luckNone: "The luck index appears once some drawn tickets are recorded.",
      luck_legend: "🍀 Legendary luck", luck_lucky: "😊 Luckier than most", luck_average: "🙂 Right on average", luck_unlucky: "😅 A bit unlucky", luck_rain: "🌧️ Luck is resting",
      luckDetail: "Drawn: {g} lotto games · {p} pension tickets · expected wins {e} · actual {w} · return {r}%",
      luckJackpot: "At your pace ({n} games a week) a lotto jackpot is expected in about {y} years (odds 1 in 8,145,060).",
      luckNote: "Luck index = percentile of your actual wins against the wins expected from the tickets you bought (exact binomial). Just for fun: it never changes the odds of the next draw.",
      budgetTitle: "This month's budget", budgetOff: "No monthly budget — set one per account in ⏰ settings and purchases over it are blocked automatically.",
      budgetUsed: "Used", budgetLeft: "Left", budgetOver: "Budget used up — more purchases this month are blocked.",
      claimTitle: "Prize claim helper", claimNone: "No prizes to claim in person (online prizes up to 2,000,000 won are credited to your deposit).",
      claimVisit: "The claim deadline is one year from the draw date; if that day is not a bank business day it moves to the next one. Dates here skip weekends only, so a public holiday can push them later. Unclaimed prizes go to the Lottery Fund. (Source: DH Lottery user guide and winner guide)",
      how_auto: "Credited to deposit", how_bank_branch: "🏦 Any NH Bank branch · ID and ticket number", how_bank_hq: "🏦 NH Bank head office only · ID and ticket number",
      how_pension_office: "🏢 Visit the DH Lottery head office with your ID → paid on the 20th of each month from the month after you claim",
      claimAuto: "Credited to deposit", claimExpired: "Expired", icsBtn: "📅 Download calendar (.ics)",
      icsHint: "A file that puts 'lotto cut-off in 2 hours' and 'prize claim deadline' reminders into your phone calendar. Not sure you need it? Open the guide below.",
      icsFold: "❓ When is the calendar useful? · How to use it",
      icsWhyT: "Good for you if",
      icsWhy1: "• You don't use HA notifications, or want reminders from the phone itself even when you're away or HA is down — the events and alarms live on the phone.",
      icsWhy2: "• You want family members to see cut-offs, draws and claim deadlines in a shared calendar.",
      icsWhy3: "• You have a big prize and want 30-, 7- and 1-day reminders before the one-year claim deadline saved on your phone.",
      icsSkipT: "You can skip it if",
      icsSkip: "You already receive the cut-off reminder, claim deadline alerts and weekly report from ⏰ settings in the HA app (or Kakao Talk) — the content is almost the same.",
      icsWhatT: "What the file contains",
      icsWhat: "Next 8 weeks of lotto sales cut-offs (Sat 20:00, alarm 2 h before) and pension draws (Thu 19:05), your enabled schedules (repeating weekly), and claim deadlines for prizes you must claim yourself (alarms 30, 7 and 1 day before).",
      icsHowT: "How to use",
      icsHow1: "① Tap 'Download calendar' above to save dhlotto45.ics. (If saving doesn't work inside the HA app, open HA in your phone or PC web browser and download it there.)",
      icsHow2: "② iPhone: open dhlotto45.ics in the Files app → 'Add All' → pick a calendar.",
      icsHow3: "③ Android (Google Calendar): on a PC go to calendar.google.com → Settings ⚙️ → Import & export → choose the file → pick a calendar → Import. It then shows on your phone.",
      icsHow4: "④ Samsung Calendar: tap dhlotto45.ics in My Files, open it with Samsung Calendar and save.",
      icsNoteT: "Good to know",
      icsNote: "The file is a snapshot and does not update by itself. Download it again after 8 weeks, after changing schedules, or after a new big win. To avoid duplicates, import into a separate calendar such as 'DH Lotto' and clear it before re-importing.",
      nWeekly: "📬 Weekly report (Sunday 09:00)", nDeadline: "⏰ Cut-off reminder (Saturday 18:00, accounts without tickets)", nClaim: "💰 Prize claim deadline alerts (D-30·7·1)",
      nBudget: "💳 Monthly budget per account (won, 0 = off)", nBudgetHint: "Purchases over the budget are blocked from the dashboard, HA buttons and schedules.",
      hhLabel: "🧾 Household ledger (kr_ledger_kit)", hhHint: "With the kr_ledger_kit integration, purchases are recorded as expenses and wins as income, per round (category: 복권).",
      hhMissing: "kr_ledger_kit integration not found — install it and turn this on again.", hhOk: "Household ledger sync is on.",
      fairOk: "🔬 Fairness test (χ²={c}, p={p}, {n} numbers): the spread is within chance — hot and cold numbers do not affect the next draw.",
      fairSkew: "🔬 Fairness test (χ²={c}, p={p}, {n} numbers): this sample looks skewed, but every draw is independent.",
      diag: "🩺 Copy diagnostic report", diagCopied: "Diagnostic report copied. Paste it into your question (IDs and IPs are hidden).",
      diagManual: "Select all of the text below and copy it (IDs and IPs are hidden).", diagTitle: "Diagnostic report", sSupport: "Support",
      genMode: "Mode", genRandom: "Fully random", genHot: "Mostly hot numbers", genCold: "Mostly cold numbers", genMix: "Hot + cold mix",
      genOdd: "Odd/even balance", genSum: "Sum 100-175", genSeq: "No 3 in a row", genNote: "Every method has the same odds (just for fun).", saveErr: "Save failed: ",
      relogin: "🔄 Re-login", reloginBusy: "Signing in…", reloginOk: "Session refreshed.", reloginFail: "Re-login failed: ",
      cooldownWait: "⏳ Inter-account cooldown: ", cooldownSec: "s left",
      receipt: "Ticket slip", rcptLotto: "LOTTO 6/45", rcptPension: "PENSION 720+", rcptDraw: "Draw", rcptTotal: "Total", rcptGames: "games",
      rcptNote: "On-screen slip for checking only (not a real ticket)", mAuto: "Auto", mManual: "Manual", mSemi: "Semi", rcptNone: "No tickets for this round.",
      numstats: "Number stats", nsFreq: "Frequency", nsGap: "Rounds absent", nsRounds: "Last", nsHot: "Most drawn", nsCold: "Least drawn",
      nsAbsent: "Long absent", nsTimes: "x", nsAgo: " ago", nsNever: "out of range", nsExpected: "Expected", nsTotal: "All-time",
      nsNote: "Bonus numbers excluded · past statistics only; every number has the same odds next draw.", nsLoading: "Loading statistics…", nsFail: "Could not load number stats: ",
      exportCsv: "⬇ Export CSV", exportJson: "⬇ Backup (JSON)", importJson: "⬆ Import backup", importOk: "Imported: added ", importSkip: ", skipped ", importFail: "Import failed: ",
      exportFail: "Export failed: ", qTop: "Top",
      mqttDown: "📡 Not connected to the MQTT broker, so HA sensors and buttons are not updating",
      mqttHow: "Check that the Mosquitto broker add-on is running. Leave the MQTT username/password empty in the add-on configuration and Mosquitto gives this add-on its own account automatically. Sensors and buttons are recreated once connected; buying from this page works without MQTT.", expand: "Expand", collapse: "Collapse",
      foldLotto: "✍️ Pick numbers (manual / semi-auto)", foldPension: "✍️ Pick group & number (manual)", foldSchedule: "➕ Add schedule", foldNotify: "🔔 Notification settings",
      q_summary: "Summary", q_buy: "Buy", q_receipt: "Slip", q_favorites: "Favorites", q_lotto_current: "Lotto", q_lotto_prev: "Last lotto",
      q_pension_current: "Pension", q_pension_prev: "Last pension", q_winning: "Winning", q_numstats: "Numbers", q_stats: "Spending", q_auto: "Auto",
      pickerOpen: "🎱 Number Pad", pickerClose: "🎱 Hide Pad", pickerClear: "Clear", pickerHint: "Pick up to 6 numbers (rest filled with auto)",
      simBtn: "🔍", simTitle: "Past Draw Simulation", simLoading: "Checking last 50 draws…", simNone: "No 5th-prize or higher matches in the last 50 draws.",
      simFail: "Simulation failed: ", simRounds: "Draws", simRank: " prize", simNote: "1st-3rd prizes use average estimates; past results do not predict future draws." }
  };
  var LUCKY = {
    ko: ["오늘의 행운은 당신 편 🍀", "1등의 주인공은 바로 나!", "이번 주, 인생 역전의 기회 ✨", "행운은 준비된 사람에게 온다", "황금 공이 굴러오는 소리 🎱"],
    en: ["Luck is on your side today 🍀", "The next winner could be you!", "This could be the week ✨", "Fortune favors the prepared", "Hear the golden ball rolling 🎱"]
  };
  var THEMES = [
    { id: "system", g: "gBasic", ko: "시스템 자동", en: "System", sw: "linear-gradient(135deg,#f4f6fb 50%,#0b1120 50%)" },
    { id: "light", g: "gBasic", ko: "라이트", en: "Light", sw: "linear-gradient(135deg,#4f46e5,#06b6d4)" },
    { id: "dark", g: "gBasic", ko: "다크", en: "Dark", sw: "linear-gradient(135deg,#312e81,#0e7490)" },
    { id: "ha-blue", g: "gBasic", ko: "HA 블루", en: "HA Blue", sw: "linear-gradient(135deg,#0284c7,#22d3ee)" },
    { id: "jackpot-gold", g: "gLucky", ko: "잭팟 골드", en: "Jackpot Gold", sw: "linear-gradient(135deg,#2b1f05,#f5c542)" },
    { id: "clover", g: "gLucky", ko: "네잎클로버", en: "Four-leaf Clover", sw: "linear-gradient(135deg,#16a34a,#a3e635)" },
    { id: "lucky-red", g: "gLucky", ko: "복주머니", en: "Lucky Pouch", sw: "linear-gradient(135deg,#c8102e,#f5b700)" },
    { id: "golden-pig", g: "gLucky", ko: "황금돼지", en: "Golden Pig", sw: "linear-gradient(135deg,#f472b6,#fbbf24)" },
    { id: "lotto-pop", g: "gLucky", ko: "로또볼 팝", en: "Lotto Ball Pop", sw: "linear-gradient(110deg,#e0ad00,#3fa9de,#e5534b,#8a8f98,#79b33a)" },
    { id: "neon-draw", g: "gNight", ko: "네온 추첨기", en: "Neon Draw", sw: "linear-gradient(135deg,#0e7490,#7c3aed,#db2777)" },
    { id: "aurora", g: "gNight", ko: "오로라", en: "Aurora", sw: "linear-gradient(135deg,#0f766e,#7c3aed)" },
    { id: "galaxy", g: "gNight", ko: "은하수 소원", en: "Galaxy Wish", sw: "linear-gradient(135deg,#1e1b4b,#be185d)" }
  ];
  var DEFAULT_ORDER = ["summary", "buy", "receipt", "favorites", "lotto_current", "lotto_prev", "pension_current", "pension_prev", "winning", "numstats", "stats", "insight", "auto"];
  var CARD_NAMES = { summary: "summary", buy: "buy", favorites: "favorites", lotto_current: "lottoCur", lotto_prev: "lottoPrev",
    pension_current: "penCur", pension_prev: "penPrev", winning: "winning", stats: "stats", auto: "auto", receipt: "receipt", numstats: "numstats", insight: "insight" };

  var prefs = {};
  try { prefs = JSON.parse(document.getElementById("dhl-prefs").textContent || "{}") || {}; } catch (e) { prefs = {}; }
  var data = null, current = null, timer = null, saveTimer = null, saveState = "";
  var settings = null, stats = null, statsScope = "all", modalOk = null;
  var numStats = null, numStatsAt = 0, numStatsErr = "", nsRounds = 50, nsView = "freq";
  var insights = null, insightScope = "acc";
  var gen = { mode: "random", odd: false, sum: false, seq: false };
  var autoDraft = { action: "lotto_auto_1", time: "09:00", days: [5], account: "all" };
  var luckyIdx = Math.floor(Math.random() * 5);
  // Unsent manual inputs per account, kept across the periodic re-render.
  var drafts = {};
  var cooldownUntil = {};
  var reloginBusy = {};
  function draft(acc) { return drafts[acc.id] || (drafts[acc.id] = {}); }
  function cooldownLeft(acc) {
    if (!acc || !cooldownUntil[acc.id]) return 0;
    return Math.max(0, Math.ceil((cooldownUntil[acc.id] - Date.now()) / 1000));
  }
  function syncCooldowns(resp) {
    var now = Date.now();
    ((resp && resp.accounts) || []).forEach(function (a) {
      var rem = Number(a.cooldown_remaining || 0);
      cooldownUntil[a.id] = rem > 0 ? now + rem * 1000 : 0;
    });
  }
  function t(k) { var d = T[prefs.lang] || T.ko; return d[k] !== undefined ? d[k] : (T.ko[k] !== undefined ? T.ko[k] : k); }

  // ------------------------------------------------------------ helpers
  function h(tag, attrs, kids) {
    var e = document.createElement(tag);
    if (attrs) for (var k in attrs) {
      var v = attrs[k];
      if (k === "text") e.textContent = v;
      else if (k === "cls") e.className = v;
      else if (k === "bg") e.style.background = v;
      else if (k.slice(0, 2) === "on") e.addEventListener(k.slice(2), v);
      else if (v !== null && v !== undefined && v !== false) e.setAttribute(k, v);
    }
    (kids || []).forEach(function (c) { if (c !== null && c !== undefined) e.appendChild(typeof c === "string" ? document.createTextNode(c) : c); });
    return e;
  }
  function S(acc, id) { return (acc && acc.sensors && acc.sensors[id]) || null; }
  function st(acc, id) { var s = S(acc, id); return s ? s.state : null; }
  function at(acc, id) { var s = S(acc, id); return (s && s.attributes) || {}; }
  function won(n) {
    var v = Number(n); if (!isFinite(v)) return "-";
    return prefs.lang === "en" ? "₩" + v.toLocaleString("en-US") : v.toLocaleString("ko-KR") + "원";
  }
  function bigWon(n) {
    var v = Number(n); if (!isFinite(v) || v <= 0) return "-";
    if (prefs.lang === "en") return v >= 1e9 ? "₩" + (v / 1e9).toFixed(1).replace(/\.0$/, "") + "B" : "₩" + Math.round(v / 1e6) + "M";
    if (v >= 1e8) { var eok = Math.floor(v / 1e8), man = Math.round((v % 1e8) / 1e4); return eok + "억" + (man ? " " + man.toLocaleString("ko-KR") + "만" : "") + "원"; }
    return won(v);
  }
  function ballCls(n) { n = Number(n); return n <= 10 ? "y" : n <= 20 ? "b" : n <= 30 ? "r" : n <= 40 ? "g" : "l"; }
  function ball(n, hit) { return h("span", { cls: "ball " + ballCls(n) + (hit ? " hit" : ""), text: String(n) }); }
  function balls(list, hits) { return (list || []).map(function (n) { return ball(n, hits && hits.indexOf(Number(n)) >= 0); }); }
  function isWin(r) { r = String(r || ""); return /당첨|\d등/.test(r) && r.indexOf("낙첨") < 0 && r.indexOf("등외") < 0; }
  function resCls(r) {
    r = String(r || "");
    if (!r || r === "-" || r.indexOf("미추첨") >= 0 || r === "구매 내역 없음") return "r-wait";
    if (r.indexOf("1등") >= 0) return "r-gold";
    return isWin(r) ? "r-win" : "r-lose";
  }
  var ART = { summary: "icon_wallet", buy: "icon_buy", favorites: "icon_favorite", lotto_current: "icon_lotto",
    lotto_prev: "icon_history", pension_current: "icon_pension", pension_prev: "icon_history", winning: "icon_winning",
    stats: "icon_stats", auto: "icon_auto", receipt: "icon_history", numstats: "icon_numstats", insight: "icon_stats" };
  // Decorative image; if it fails to load, fall back to the emoji (or nothing).
  function art(name, cls, fallback) {
    var img = h("img", { cls: cls, src: "static/img/" + name + ".webp", alt: "", decoding: "async" });
    img.addEventListener("error", function () {
      var alt = h("span", { cls: "ic", text: fallback || "" });
      if (img.parentNode) img.parentNode.replaceChild(alt, img);
    });
    return img;
  }
  function emptyArt(text) { return h("div", { cls: "empty art" }, [art("empty", "", ""), h("span", { text: text })]); }
  var DEFAULT_COLLAPSED = ["receipt", "winning", "numstats", "stats", "auto"];
  var openFolds = {};
  function collapsedList() { return Array.isArray(prefs.collapsed_cards) ? prefs.collapsed_cards : DEFAULT_COLLAPSED; }
  function isCollapsed(id) { return collapsedList().indexOf(id) >= 0; }
  function toggleCard(id) {
    var list = collapsedList().slice(), i = list.indexOf(id);
    if (i >= 0) list.splice(i, 1); else list.push(id);
    setPref("collapsed_cards", list);
    if (i >= 0 && id === "numstats") loadNumStats(false).then(render);
  }
  // Collapsible card: the whole title row is a button (keyboard + screen reader friendly).
  function card(id, icon, title, sub, body) {
    var closed = isCollapsed(id), bid = "cb-" + id;
    var head = ART[id] ? art(ART[id], "ic-img", icon) : h("span", { cls: "ic", text: icon });
    var btn = h("button", { cls: "card-head", type: "button", "aria-expanded": closed ? "false" : "true", "aria-controls": bid,
      title: closed ? t("expand") : t("collapse"), onclick: function () { toggleCard(id); } },
      [head, h("span", { cls: "ttl", text: title }), sub ? h("span", { cls: "sub", text: sub }) : null, h("span", { cls: "chev", "aria-hidden": "true", text: "▾" })]);
    var bodyEl = h("div", { cls: "card-body", id: bid }, body);
    if (closed) bodyEl.hidden = true;
    return h("section", { cls: "card" + (closed ? " collapsed" : ""), "data-card": id }, [h("h3", null, [btn]), bodyEl]);
  }
  // Fold the nodes pushed since `start` into an expandable section (closed until the user opens it).
  function foldTail(body, start, key, label) {
    var nodes = body.splice(start, body.length - start), open = !!openFolds[key], fid = "fold-" + key;
    var btn = h("button", { cls: "fold-btn", type: "button", "aria-expanded": open ? "true" : "false", "aria-controls": fid,
      onclick: function () { openFolds[key] = !openFolds[key]; render(); } }, [h("span", { text: label }), h("span", { cls: "chev", "aria-hidden": "true", text: "▾" })]);
    var box = h("div", { cls: "fold-body", id: fid }, nodes);
    if (!open) box.hidden = true;
    body.push(h("div", { cls: "fold" + (open ? " open" : "") }, [btn, box]));
  }
  function fmtTime(ts) {
    if (!ts) return "-";
    return new Date(ts * 1000).toLocaleString(prefs.lang === "en" ? "en-US" : "ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
  }
  function rnd(n) { var a = new Uint32Array(1); crypto.getRandomValues(a); return a[0] % n; }

  // Next draw in KST: lotto Sat 20:35, pension Thu 19:05
  function nextDraw(dow, hh, mm) {
    var now = Date.now(), k = new Date(now + 9 * 3600e3);
    var target = Date.UTC(k.getUTCFullYear(), k.getUTCMonth(), k.getUTCDate(), hh, mm) - 9 * 3600e3;
    target += ((dow - k.getUTCDay() + 7) % 7) * 86400e3;
    if (target <= now) target += 7 * 86400e3;
    return target - now;
  }
  function fmtLeft(ms) {
    var s = Math.max(0, Math.floor(ms / 1000)), d = Math.floor(s / 86400); s %= 86400;
    var hh = Math.floor(s / 3600), mm = Math.floor((s % 3600) / 60), ss = s % 60;
    function p(x) { return (x < 10 ? "0" : "") + x; }
    return (d ? d + t("day") + " " : "") + p(hh) + ":" + p(mm) + ":" + p(ss);
  }

  // ------------------------------------------------------------ prefs
  function themeOf(id) { return THEMES.filter(function (x) { return x.id === id; })[0] || THEMES[0]; }
  function applyPrefs() {
    var th = themeOf(prefs.theme);
    root.setAttribute("data-theme", th.id);
    root.classList.toggle("compact", prefs.density === "compact");
    root.classList.toggle("flat", prefs.ball_style === "flat");
    root.classList.toggle("noeffects", prefs.effects === false);
    root.setAttribute("lang", prefs.lang === "en" ? "en" : "ko");
    document.getElementById("theme-sw").style.background = th.sw;
    document.getElementById("theme-name").textContent = prefs.lang === "en" ? th.en : th.ko;
    document.getElementById("btn-theme").setAttribute("title", t("settings"));
    document.getElementById("btn-lang").textContent = t("lang");
    document.getElementById("btn-reload").textContent = t("reload");
    document.getElementById("footer").textContent = t("footer");
    document.getElementById("m-cancel").textContent = t("cancel");
    document.getElementById("m-ok").textContent = t("confirm");
    document.getElementById("m-title").textContent = t("confirmTitle");
  }
  function setPref(key, value) {
    prefs[key] = value; applyPrefs(); render(); if (drawerOpen()) renderDrawer();
    clearTimeout(saveTimer);
    saveTimer = setTimeout(savePrefs, 350);
  }
  function savePrefs() {
    fetch("api/prefs", { method: "PUT", credentials: "same-origin", cache: "no-store",
      headers: { "Content-Type": "application/json", "X-DHL-CSRF": CSRF }, body: JSON.stringify(prefs) })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (p) { prefs = p; saveState = "ok"; })
      .catch(function () { saveState = "fail"; })
      .then(function () { var s = document.getElementById("saved"); if (s) s.textContent = saveState === "ok" ? t("savedOk") : t("saveFail"); });
  }

  // ------------------------------------------------------------ hero
  function luckyMsg() { var l = LUCKY[prefs.lang] || LUCKY.ko; return prefs.lucky_message || l[luckyIdx % l.length]; }
  function renderHero(acc) {
    var hero = document.getElementById("hero");
    hero.hidden = prefs.show_hero === false;
    hero.textContent = "";
    if (hero.hidden) return;
    var counts = [h("div", { cls: "count" }, [h("div", { cls: "k", text: "🎱 " + t("nextLotto") }), h("div", { cls: "v", id: "cd-lotto", text: fmtLeft(nextDraw(6, 20, 35)) })])];
    if (!data || data.pension_enabled) counts.push(h("div", { cls: "count" }, [h("div", { cls: "k", text: "🎟️ " + t("nextPension") }), h("div", { cls: "v", id: "cd-pension", text: fmtLeft(nextDraw(4, 19, 5)) })]));
    hero.appendChild(h("div", null, [h("h2", { text: t("heroTitle") + " 🏆" }), h("div", { cls: "msg", id: "hero-msg", text: luckyMsg() }), h("div", { cls: "counts" }, counts)]));
    var right = h("div", { cls: "hero-right" });
    var la = at(acc, "lotto645_winning_numbers");
    if ((la.numbers || []).length) {
      right.appendChild(h("div", { cls: "lbl", text: t("lottoName") + " · " + (la.round || "") + t("latestDraw") }));
      right.appendChild(h("div", { cls: "hero-balls" }, balls(la.numbers).concat([h("span", { cls: "plus", text: "+" }), ball(la.bonus)])));
    }
    var fp = st(acc, "lotto645_first_prize");
    if (Number(fp) > 0) right.appendChild(h("div", { cls: "prize" }, [t("lastPrize") + "  ", h("b", { text: bigWon(fp) })]));
    hero.appendChild(right);
    hero.appendChild(art("hero_machine", "hero-art", ""));
  }
  setInterval(function () {
    var a = document.getElementById("cd-lotto"), b = document.getElementById("cd-pension");
    if (a) a.textContent = fmtLeft(nextDraw(6, 20, 35));
    if (b) b.textContent = fmtLeft(nextDraw(4, 19, 5));
    var cdEl = document.getElementById("cd-buy-banner");
    var acc = currentAcc();
    if (cdEl && acc) {
      var left = cooldownLeft(acc);
      if (left > 0) cdEl.textContent = t("cooldownWait") + left + t("cooldownSec");
      else render();
    }
  }, 1000);
  setInterval(function () { luckyIdx++; var m = document.getElementById("hero-msg"); if (m) m.textContent = luckyMsg(); }, 8000);

  // ------------------------------------------------------------ cards
  function doRelogin(acc) {
    if (!acc || reloginBusy[acc.id]) return;
    reloginBusy[acc.id] = true; render();
    postJson("api/relogin", { account: acc.id })
      .then(function () { toast(t("reloginOk"), "ok"); return load(); })
      .catch(function (e) { toast(t("reloginFail") + e.message, "err"); })
      .then(function () { delete reloginBusy[acc.id]; render(); });
  }
  function summaryCard(acc) {
    var bal = st(acc, "lotto45_balance"), ba = at(acc, "lotto45_balance"), last = S(acc, "lotto45_last_update");
    var busy = !!reloginBusy[acc.id];
    var reloginBtn = h("button", { cls: "mini inline-btn", type: "button", disabled: busy ? "disabled" : null,
      text: busy ? t("reloginBusy") : t("relogin"), onclick: function () { doRelogin(acc); } });
    return card("summary", "💰", t("summary"), acc.label, [
      h("div", { cls: "big", text: bal === null ? "-" : won(bal) }), h("div", { cls: "hint", text: t("deposit") }),
      h("dl", { cls: "kv" }, [
        h("dt", { text: t("available") }), h("dd", { text: ba.purchase_available !== undefined ? won(ba.purchase_available) : "-" }),
        h("dt", { text: t("login") }), h("dd", null, [h("span", { cls: "dot " + (acc.logged_in ? "on" : "off") }), acc.logged_in ? t("ok") : t("fail"), reloginBtn]),
        h("dt", { text: t("sync") }), h("dd", { text: st(acc, "lotto45_sync_status") || "-" }),
        h("dt", { text: t("updatedAt") }), h("dd", { text: last ? fmtTime(last.ts) : "-" })
      ])
    ]);
  }
  function lottoRows(acc, prefix, hits) {
    var rows = [];
    for (var i = 1; i <= 5; i++) {
      var g = S(acc, prefix + i);
      if (!g || !g.attributes || !(g.attributes.numbers || []).length) continue;
      var res = st(acc, prefix + i + "_result") || g.attributes.result || "-";
      rows.push(h("div", { cls: "row" + (isWin(res) ? " won" : "") }, [h("span", { cls: "idx", text: String(i) }),
        h("span", { cls: "main" }, balls(g.attributes.numbers, hits)), h("span", { cls: "res " + resCls(res), text: res })]));
    }
    return rows.length ? h("div", { cls: "rows" }, rows) : emptyArt(t("none"));
  }
  function lottoCurrentCard(acc) {
    var w = at(acc, "lotto45_weekly_purchase_count"), cnt = st(acc, "lotto45_weekly_purchase_count"), round = at(acc, "lotto45_game_1").round_no;
    return card("lotto_current", "🎱", t("lottoCur"), (round ? round + t("round") + " · " : "") + t("weekly") + " " + (cnt === null ? "-" : cnt) + "/" + (w.weekly_limit || 5) + " " + t("games"), [lottoRows(acc, "lotto45_game_")]);
  }
  function lottoPrevCard(acc) {
    var r = st(acc, "lotto45_prev_round"), wa = at(acc, "lotto45_prev_game_1_result");
    var hits = (wa.winning_numbers || []).map(Number);
    var body = [lottoRows(acc, "lotto45_prev_game_", hits)];
    if (hits.length) body.unshift(h("div", { cls: "row" }, [h("span", { cls: "idx", text: "★" }),
      h("span", { cls: "main" }, balls(wa.winning_numbers).concat([h("span", { cls: "plus", text: "+" }), ball(wa.bonus_number)])), h("span", { cls: "res r-gold", text: t("winNums") })]));
    return card("lotto_prev", "📜", t("lottoPrev"), r && Number(r) > 0 ? r + t("round") : "", body);
  }
  function ticket(group, number) {
    return h("span", { cls: "ticket mono" }, [group ? h("span", { cls: "grp", text: group + t("groupSuffix") }) : null, h("span", { cls: "num", text: String(number || "") })]);
  }
  function pensionRows(games) {
    if (!games || !games.length) return emptyArt(t("none"));
    return h("div", { cls: "rows" }, games.map(function (g, i) {
      return h("div", { cls: "row" + (isWin(g.result) ? " won" : "") }, [h("span", { cls: "idx", text: String(i + 1) }), h("span", { cls: "main" }, [ticket(g.group, g.number)]),
        h("span", { cls: "res " + resCls(g.result), text: (g.result || "-") + (g.win_amount > 0 ? " · " + won(g.win_amount) : "") })]);
    }));
  }
  function pensionCurrentCard(acc) {
    var a = at(acc, "pension720_this_round");
    return card("pension_current", "🎟️", t("penCur"), (a.round_no ? a.round_no + t("round") + " · " : "") + (a.games ? a.games.length : 0) + t("tickets"), [pensionRows(a.games)]);
  }
  function pensionPrevCard(acc) {
    var a = at(acc, "pension720_last_round"), body = [];
    if (a.result_summary) body.push(h("div", { cls: "hint", text: a.result_summary }));
    body.push(pensionRows(a.games));
    return card("pension_prev", "📜", t("penPrev"), a.round_no ? a.round_no + t("round") : "", body);
  }
  function winningCard(acc) {
    var la = at(acc, "lotto645_winning_numbers"), pa = at(acc, "pension720_winning_number"), body = [];
    if ((la.numbers || []).length) {
      body.push(h("div", { cls: "hint", text: "🎱 " + t("lottoName") + " · " + la.round + t("round") }));
      body.push(h("div", { cls: "row" }, [h("span", { cls: "main" }, balls(la.numbers).concat([h("span", { cls: "plus", text: "+" }), ball(la.bonus)]))]));
    }
    if (pa.number) {
      body.push(h("div", { cls: "hint", text: "🎟️ " + t("pensionName") + " · " + pa.round + t("round") }));
      body.push(h("div", { cls: "row" }, [h("span", { cls: "main" }, [ticket(pa.group, pa.number)]), h("span", { cls: "res r-wait", text: pa.bonus ? t("bonus") + " " + pa.bonus : "" })]));
    }
    if (!body.length) body.push(h("div", { cls: "empty", text: t("notLoaded") }));
    return card("winning", "🏆", t("winning"), "", body);
  }
  function parseFixedNums(text) {
    var out = [];
    String(text || "").split(",").forEach(function (p) {
      var n = Number(p.trim());
      if (Number.isInteger(n) && n >= 1 && n <= 45 && out.indexOf(n) < 0) out.push(n);
    });
    return out.slice(0, 6).sort(function (a, b) { return a - b; });
  }
  function formatManualNums(nums) {
    var arr = nums.slice(0, 6).sort(function (a, b) { return a - b; }).map(String);
    while (arr.length < 6) arr.push("auto");
    return arr.join(",");
  }
  function buyCard(acc) {
    var avail = data.purchase_available, running = acc.last_action && acc.last_action.status === "running", cdLeft = cooldownLeft(acc), body = [];
    if (cdLeft > 0) body.push(h("div", { cls: "cooldown-pill", id: "cd-buy-banner", text: t("cooldownWait") + cdLeft + t("cooldownSec") }));
    function btn(label, action, extra, disabled) {
      return h("button", { cls: "btn" + (extra || ""), type: "button", disabled: (running || cdLeft > 0 || disabled) ? "disabled" : null, onclick: function () { ask(acc, action); }, text: label });
    }
    if (data.lotto_enabled) {
      body.push(h("div", { cls: "sect", text: "🎱 " + t("lottoName") }));
      body.push(h("div", { cls: "btns" }, [btn(t("auto1"), "lotto_auto_1", "", !avail), btn(t("auto5"), "lotto_auto_5", "", !avail)]));
      var lottoFoldStart = body.length;
      var dr = draft(acc);
      var curVal = dr.lotto !== undefined ? dr.lotto : (acc.manual_numbers || "");
      var li = h("input", { cls: "lotto mono", id: "lotto-manual", value: curVal, oninput: function () { dr.lotto = li.value; if (dr.pickerOpen) syncPicker(); }, placeholder: "1,7,12,auto,auto,auto", "aria-label": t("manual1"), autocomplete: "off" });
      var prev = h("div", { cls: "preview", id: "lotto-preview" });
      var pickerBox = h("div", { cls: "picker-wrap" });
      pickerBox.hidden = !dr.pickerOpen;
      function syncPicker() {
        var selNums = parseFixedNums(li.value);
        pickerBox.textContent = "";
        pickerBox.appendChild(h("div", { cls: "picker-head" }, [
          h("span", { text: t("pickerHint") + " (" + selNums.length + "/6)" }),
          h("button", { cls: "mini", type: "button", text: t("pickerClear"), onclick: function () { li.value = "auto,auto,auto,auto,auto,auto"; dr.lotto = li.value; syncPicker(); } })
        ]));
        var gridEl = h("div", { cls: "picker-grid" });
        for (var n = 1; n <= 45; n++) (function (num) {
          var active = selNums.indexOf(num) >= 0;
          gridEl.appendChild(h("button", { cls: "pball " + ballCls(num), type: "button", "aria-pressed": active ? "true" : "false", text: String(num), onclick: function () {
            var cur = parseFixedNums(li.value);
            var idx = cur.indexOf(num);
            if (idx >= 0) cur.splice(idx, 1);
            else if (cur.length < 6) cur.push(num);
            li.value = formatManualNums(cur); dr.lotto = li.value;
            syncPicker();
          } }));
        })(n);
        pickerBox.appendChild(gridEl);
      }
      if (dr.pickerOpen) syncPicker();
      body.push(h("div", { cls: "manual" }, [li, btn(t("manual1"), "lotto_manual", " secondary", !avail)]));
      body.push(h("div", { cls: "manual" }, [
        h("button", { cls: "btn lucky", type: "button", text: t("luckyPick"), onclick: function () {
          var picks = pickLotto(acc);
          li.value = picks.join(","); dr.lotto = li.value;
          prev.textContent = ""; prev.classList.remove("rolling"); void prev.offsetWidth; prev.classList.add("rolling");
          picks.forEach(function (p, i) { var b = ball(p); b.style.animationDelay = (i * 0.08) + "s"; prev.appendChild(b); });
          if (dr.pickerOpen) syncPicker();
        } }),
        h("button", { cls: "btn secondary small", type: "button", text: dr.pickerOpen ? t("pickerClose") : t("pickerOpen"), onclick: function () {
          dr.pickerOpen = !dr.pickerOpen; render();
        } })
      ]));
      body.push(pickerBox);
      body.push(genOptions());
      body.push(prev);
      body.push(h("div", { cls: "hint", text: t("manualHint") + " · " + t("genNote") }));
      foldTail(body, lottoFoldStart, "lotto-manual", t("foldLotto"));
    }
    if (data.pension_enabled) {
      body.push(h("div", { cls: "sect", text: "🎟️ " + t("pensionName") }));
      body.push(h("div", { cls: "btns" }, [btn(t("pAuto1"), "pension_auto_1"), btn(t("pAuto5"), "pension_auto_5")]));
      var penFoldStart = body.length;
      var pd = draft(acc), pm = String(acc.pension_manual || "").split(",");
      var pg = pd.group !== undefined ? pd.group : (pm[0] || "").trim(), pn = pd.digits !== undefined ? pd.digits : (pm[1] || "").trim();
      var sel = h("select", { id: "p-group", "aria-label": "group" }, [1, 2, 3, 4, 5].map(function (g) {
        return h("option", { value: String(g), selected: String(g) === pg ? "selected" : null, text: prefs.lang === "en" ? "Group " + g : g + "조" });
      }));
      sel.addEventListener("change", function () { pd.group = sel.value; });
      var num = h("input", { cls: "pnum mono", id: "p-num", value: pn, oninput: function () { pd.digits = num.value; }, placeholder: "123456", maxlength: "6", inputmode: "numeric", "aria-label": "6 digits", autocomplete: "off" });
      body.push(h("div", { cls: "manual" }, [sel, num, btn(t("pManual"), "pension_manual", " secondary")]));
      body.push(h("div", { cls: "manual" }, [h("button", { cls: "btn lucky", type: "button", text: t("luckyPick"), onclick: function () {
        sel.value = String(rnd(5) + 1); var d = ""; for (var i = 0; i < 6; i++) d += String(rnd(10)); num.value = d;
        pd.group = sel.value; pd.digits = d;
      } })]));
      foldTail(body, penFoldStart, "pension-manual", t("foldPension"));
    }
    var la = acc.last_action;
    if (la) {
      var txt = la.status === "running" ? "⏳ " + la.label + " " + t("running") :
        (la.status === "success" ? "✅ " : la.status === "skipped" ? "⚠️ " : "❌ ") + la.label + " — " + (la.message || "");
      body.push(h("div", { cls: "status " + la.status, text: txt + (la.finished ? " (" + fmtTime(la.finished) + ")" : "") }));
    }
    return card("buy", "🛒", t("buy"), acc.label, body);
  }

  // ------------------------------------------------------------ number generator
  function numsFrom(acc, id) { return (at(acc, id).numbers || []).map(Number).filter(function (n) { return n >= 1 && n <= 45; }); }
  function takeFrom(picks, src, k) {
    var s = src.filter(function (x) { return picks.indexOf(x) < 0; });
    for (var i = 0; i < k && s.length; i++) picks.push(s.splice(rnd(s.length), 1)[0]);
  }
  function genOk(p) {
    var odd = p.filter(function (n) { return n % 2; }).length, sum = p.reduce(function (a, b) { return a + b; }, 0);
    if (gen.odd && (odd < 2 || odd > 4)) return false;
    if (gen.sum && (sum < 100 || sum > 175)) return false;
    if (gen.seq) for (var i = 2; i < p.length; i++) if (p[i] - p[i - 1] === 1 && p[i - 1] - p[i - 2] === 1) return false;
    return true;
  }
  function pickLotto(acc) {
    var hot = numsFrom(acc, "lotto45_hot_numbers"), cold = numsFrom(acc, "lotto45_cold_numbers"), all = [], picks = [];
    for (var n = 1; n <= 45; n++) all.push(n);
    for (var tries = 0; tries < 3000; tries++) {
      picks = [];
      if (gen.mode === "hot") takeFrom(picks, hot, 3);
      else if (gen.mode === "cold") takeFrom(picks, cold, 3);
      else if (gen.mode === "mix") { takeFrom(picks, hot, 2); takeFrom(picks, cold, 2); }
      takeFrom(picks, all, 6 - picks.length);
      picks.sort(function (a, b) { return a - b; });
      if (genOk(picks)) break;
    }
    return picks;
  }
  function genOptions() {
    var sel = h("select", { "aria-label": t("genMode"), onchange: function (e) { gen.mode = e.target.value; } },
      [["random", t("genRandom")], ["hot", t("genHot")], ["cold", t("genCold")], ["mix", t("genMix")]].map(function (o) {
        return h("option", { value: o[0], selected: gen.mode === o[0] ? "selected" : null, text: o[1] });
      }));
    function opt(key, label) {
      return h("label", null, [h("input", { type: "checkbox", checked: gen[key] ? "checked" : null, onchange: function (e) { gen[key] = e.target.checked; } }), label]);
    }
    return h("div", { cls: "genopts" }, [h("span", { text: t("genMode") }), sel, opt("odd", t("genOdd")), opt("sum", t("genSum")), opt("seq", t("genSeq"))]);
  }

  // ------------------------------------------------------------ favorites
  function runSimulate(numbers) {
    openModal(t("simTitle"), [h("div", { cls: "hint", text: t("simLoading") })], t("close"), null, true);
    getJson("api/simulate?rounds=50&numbers=" + encodeURIComponent(numbers))
      .then(function (r) {
        var nodes = [
          h("div", { cls: "preview" }, String(r.numbers).split(",").map(function (x) { return x === "auto" ? h("span", { cls: "ball q", text: "?" }) : ball(x); })),
          h("div", { cls: "sim-grid" }, [
            h("div", { cls: "sim-stat" }, [h("b", { text: r.checked_rounds + t("round") }), h("span", { text: t("simRounds") })]),
            h("div", { cls: "sim-stat" }, [h("b", { text: won(r.total_win) }), h("span", { text: t("statWin") })]),
            h("div", { cls: "sim-stat" }, [h("b", { text: r.roi + "%" }), h("span", { text: t("statRatio") })])
          ]),
          h("div", { cls: "sim-ranks" }, [1, 2, 3, 4, 5].map(function (rk) {
            var cnt = (r.rank_counts && r.rank_counts[String(rk)]) || 0;
            return h("span", { cls: "sim-chip" + (cnt > 0 ? " hit" : ""), text: rk + t("simRank") + " " + cnt });
          }))
        ];
        if ((r.hits || []).length) {
          nodes.push(h("div", { cls: "rows" }, r.hits.slice(0, 5).map(function (ht) {
            return h("div", { cls: "row won" }, [
              h("span", { cls: "main", text: ht.round + t("round") + " · " + ht.matched.join(", ") + (ht.bonus ? " +B" : "") }),
              h("span", { cls: "res r-gold", text: ht.rank + t("simRank") })
            ]);
          })));
        } else {
          nodes.push(h("div", { cls: "hint", text: t("simNone") }));
        }
        nodes.push(h("div", { cls: "hint", text: t("simNote") }));
        openModal(t("simTitle"), nodes, t("close"), null, true);
      })
      .catch(function (e) { openModal(t("simTitle"), [t("simFail") + e.message], t("close"), null, true); });
  }
  function favoritesCard(acc) {
    var favs = (settings && settings.favorites) || [], body = [];
    var running = acc.last_action && acc.last_action.status === "running", cdLeft = cooldownLeft(acc);
    if (!favs.length) body.push(h("div", { cls: "empty", text: t("favEmpty") }));
    else body.push(h("div", { cls: "rows" }, favs.map(function (f) {
      var isL = f.type === "lotto";
      var vis = isL ? String(f.numbers).split(",").map(function (x) { return x === "auto" ? h("span", { cls: "ball q", text: "?" }) : ball(x); }) : [ticket(f.group, f.digits)];
      var off = running || cdLeft > 0 || (isL ? (!data.purchase_available || !data.lotto_enabled) : !data.pension_enabled);
      var simBtn = isL ? h("button", { cls: "mini", type: "button", text: t("simBtn"), title: t("simTitle"), "aria-label": t("simTitle"), onclick: function () { runSimulate(f.numbers); } }) : null;
      return h("div", { cls: "row fav" }, [h("span", { cls: "fname", text: f.name || (isL ? t("favLotto") : t("favPension")) }), h("span", { cls: "main" }, vis),
        simBtn,
        h("button", { cls: "btn small", type: "button", disabled: off ? "disabled" : null, text: t("favBuy"), onclick: function () {
          ask(acc, isL ? "lotto_manual" : "pension_manual", isL ? { numbers: f.numbers } : { group: String(f.group), digits: f.digits });
        } }),
        h("button", { cls: "mini", type: "button", text: "✕", title: t("favDel"), "aria-label": t("favDel"), onclick: function () {
          saveSettings({ favorites: favs.filter(function (x) { return x.id !== f.id; }) });
        } })]);
    })));
    var type = h("select", { "aria-label": t("favLotto") + "/" + t("favPension") }, [h("option", { value: "lotto", text: t("favLotto") }), h("option", { value: "pension", text: t("favPension") })]);
    var val = h("input", { cls: "mono lotto", placeholder: "1,7,12,23,34,45", autocomplete: "off", "aria-label": "numbers" });
    var nm = h("input", { maxlength: "20", placeholder: t("favName"), "aria-label": t("favName") });
    type.addEventListener("change", function () { val.placeholder = type.value === "lotto" ? "1,7,12,23,34,45" : "3,123456"; });
    body.push(h("div", { cls: "manual" }, [type, val]));
    body.push(h("div", { cls: "manual" }, [nm,
      h("button", { cls: "btn secondary small", type: "button", text: t("favFromInput"), onclick: function () {
        var d = draft(acc);
        if (type.value === "lotto") val.value = d.lotto !== undefined ? d.lotto : (acc.manual_numbers || "");
        else { var pm = String(acc.pension_manual || "").split(","); val.value = (d.group || pm[0] || "1") + "," + (d.digits || pm[1] || ""); }
      } }),
      h("button", { cls: "btn small", type: "button", text: t("favAdd"), disabled: favs.length >= 10 ? "disabled" : null, onclick: function () {
        var f = { type: type.value, name: nm.value };
        if (type.value === "lotto") f.numbers = val.value;
        else { var parts = val.value.split(","); f.group = Number((parts[0] || "").trim()); f.digits = (parts[1] || "").trim(); }
        var before = favs.length;
        saveSettings({ favorites: favs.concat([f]) }, function (ok) { if (ok && settings.favorites.length === before) toast(t("favInvalid"), "err"); });
      } })]));
    return card("favorites", "⭐", t("favorites"), favs.length + "/10", body);
  }

  // ------------------------------------------------------------ stats

  // ------------------------------------------------------------ download helper
  function download(url) {
    fetch(url, { credentials: "same-origin", cache: "no-store" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      var cd = r.headers.get("Content-Disposition") || "", m = /filename="([^"]+)"/.exec(cd);
      return r.blob().then(function (b) { return { blob: b, name: m ? m[1] : "dhlotto45-ledger" }; });
    }).then(function (x) {
      var a = h("a", { href: URL.createObjectURL(x.blob), download: x.name });
      document.body.appendChild(a); a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
    }).catch(function (e) { toast(t("exportFail") + e.message, "err"); });
  }

  // ------------------------------------------------------------ receipt-style slip
  function modeName(m) { m = String(m || ""); return m.indexOf("semi") >= 0 ? t("mSemi") : m.indexOf("manual") >= 0 ? t("mManual") : t("mAuto"); }
  function barcode(seed) {
    var x = 0, stops = [], pos = 0;
    for (var i = 0; i < seed.length; i++) x = (x * 31 + seed.charCodeAt(i)) >>> 0;
    while (pos < 100) {
      x = (x * 1103515245 + 12345) >>> 0;
      var w = 0.6 + (x % 7) * 0.35, gapw = 0.5 + ((x >> 5) % 5) * 0.4;
      stops.push("#2a2a2a " + pos.toFixed(2) + "%", "#2a2a2a " + (pos + w).toFixed(2) + "%", "transparent " + (pos + w).toFixed(2) + "%", "transparent " + (pos + w + gapw).toFixed(2) + "%");
      pos += w + gapw;
    }
    var el = h("div", { cls: "barcode" }); el.style.background = "linear-gradient(90deg," + stops.join(",") + ")"; return el;
  }
  function drawDate(dow, hh, mm) {
    var d = new Date(Date.now() + nextDraw(dow, hh, mm) + 9 * 3600e3);
    function p(x) { return (x < 10 ? "0" : "") + x; }
    return d.getUTCFullYear() + "." + p(d.getUTCMonth() + 1) + "." + p(d.getUTCDate()) + " " + p(hh) + ":" + p(mm);
  }
  function receiptCard(acc) {
    var body = [], lines = [], round = 0;
    for (var i = 1; i <= 5; i++) {
      var g = at(acc, "lotto45_game_" + i);
      if (!(g.numbers || []).length) continue;
      round = g.round_no || round;
      lines.push(h("div", { cls: "rline" }, [h("span", { cls: "slot", text: g.slot || String.fromCharCode(64 + i) }), h("span", { cls: "mode", text: modeName(g.mode) }),
        h("span", { cls: "nums", text: g.numbers.map(function (n) { return (n < 10 ? "0" : "") + n; }).join(" ") })]));
    }
    if (data.lotto_enabled && lines.length) {
      body.push(h("div", { cls: "receipt" }, [h("div", { cls: "rh" }, [h("b", { text: t("rcptLotto") }), h("span", { text: acc.label })]),
        h("div", { cls: "rmeta" }, [h("span", { text: round + t("round") }), h("span", { text: t("rcptDraw") + " " + drawDate(6, 20, 35) })])].concat(lines).concat([
        h("div", { cls: "rfoot" }, [h("span", { text: t("rcptTotal") + " · " + lines.length + t("rcptGames") }), h("span", { text: won(lines.length * 1000) })]),
        barcode(acc.id + ":L:" + round + ":" + lines.length), h("div", { cls: "rnote", text: t("rcptNote") })])));
    }
    var pa = at(acc, "pension720_this_round"), pg = pa.games || [];
    if (data.pension_enabled && pg.length) {
      body.push(h("div", { cls: "receipt" }, [h("div", { cls: "rh" }, [h("b", { text: t("rcptPension") }), h("span", { text: acc.label })]),
        h("div", { cls: "rmeta" }, [h("span", { text: (pa.round_no || "") + t("round") }), h("span", { text: t("rcptDraw") + " " + drawDate(4, 19, 5) })])].concat(
        pg.slice(0, 20).map(function (g, k) {
          return h("div", { cls: "rline" }, [h("span", { cls: "slot", text: String(k + 1) }), h("span", { cls: "mode", text: (g.group || "-") + t("groupSuffix") }),
            h("span", { cls: "nums", text: String(g.number || "").split("").join(" ") })]);
        })).concat([h("div", { cls: "rfoot" }, [h("span", { text: t("rcptTotal") + " · " + pg.length + t("tickets") }), h("span", { text: won(pg.length * 1000) })]),
        barcode(acc.id + ":P:" + pa.round_no + ":" + pg.length), h("div", { cls: "rnote", text: t("rcptNote") })])));
    }
    if (!body.length) body.push(emptyArt(t("rcptNone")));
    return card("receipt", "🧾", t("receipt"), "", body);
  }

  // ------------------------------------------------------------ number stats heatmap
  function loadNumStats(force) {
    if (!data || !data.lotto_enabled || isCollapsed("numstats")) return Promise.resolve();
    if (!force && numStats && numStats.window === nsRounds && Date.now() - numStatsAt < 600000) return Promise.resolve();
    return getJson("api/number-stats?rounds=" + nsRounds).then(function (j) { numStats = j; numStatsAt = Date.now(); numStatsErr = ""; })
      .catch(function (e) { numStatsErr = e.message; });
  }
  function numStatsCard() {
    var body = [h("div", { cls: "btns tight" }, [
      h("div", { cls: "seg" }, [50, 100].map(function (r) {
        return h("button", { type: "button", "aria-pressed": nsRounds === r ? "true" : "false", text: t("nsRounds") + " " + r + t("round"),
          onclick: function () { nsRounds = r; loadNumStats(true).then(render); } });
      })),
      h("div", { cls: "seg" }, [["freq", t("nsFreq")], ["gap", t("nsGap")]].map(function (o) {
        return h("button", { type: "button", "aria-pressed": nsView === o[0] ? "true" : "false", text: o[1], onclick: function () { nsView = o[0]; render(); } });
      }))])];
    if (!numStats) {
      body.push(h("div", { cls: "empty", text: numStatsErr ? t("nsFail") + numStatsErr : t("nsLoading") }));
      return card("numstats", "🔢", t("numstats"), "", body);
    }
    var ns = numStats, max = Math.max(1, ns.max_count), win = Math.max(1, ns.window);
    var hot = ns.hot.slice(0, 6);
    body.push(h("div", { cls: "heat" }, ns.numbers.map(function (x) {
      var v = nsView === "freq" ? x.count / max : (x.gap === null ? 1 : x.gap / win);
      var color = nsView === "freq" ? "var(--gold)" : "#3fa9de";
      var c = h("div", { cls: "cell" + (nsView === "freq" && hot.indexOf(x.n) >= 0 ? " top" : ""),
        title: x.n + " · " + x.count + t("nsTimes") + " · " + (x.gap === null ? t("nsNever") : x.gap + t("nsAgo")) + (x.total ? " · " + t("nsTotal") + " " + x.total + t("nsTimes") : "") },
        [h("b", { text: String(x.n) }), h("small", { text: nsView === "freq" ? String(x.count) : (x.gap === null ? "—" : String(x.gap)) })]);
      c.style.background = "color-mix(in srgb, " + color + " " + Math.round(8 + v * 72) + "%, var(--chip))";
      return c;
    })));
    var sc = h("span", { cls: "scale" });
    sc.style.background = "linear-gradient(90deg, var(--chip), " + (nsView === "freq" ? "var(--gold)" : "#3fa9de") + ")";
    body.push(h("div", { cls: "heat-legend" }, [h("span", { text: nsView === "freq" ? "0" + t("nsTimes") : "0" + t("nsAgo") }), sc,
      h("span", { text: nsView === "freq" ? max + t("nsTimes") : win + t("nsAgo") + "+" })]));
    body.push(h("div", { cls: "sect", text: "🔥 " + t("nsHot") }));
    body.push(h("div", { cls: "numlist" }, balls(ns.hot)));
    body.push(h("div", { cls: "sect", text: "🧊 " + t("nsCold") }));
    body.push(h("div", { cls: "numlist" }, balls(ns.cold)));
    body.push(h("div", { cls: "sect", text: "⏳ " + t("nsAbsent") }));
    body.push(h("div", { cls: "numlist" }, ns.absent.map(function (a) {
      return h("span", { cls: "numlist" }, [ball(a.n), h("span", { cls: "gap", text: a.gap === null ? t("nsNever") : a.gap + t("nsAgo") })]);
    })));
    body.push(h("div", { cls: "hint mt8", text: t("nsExpected") + " " + ns.expected + t("nsTimes") + " · " + t("nsNote") }));
    var fr = ns.fairness && (ns.fairness.total || ns.fairness.window);
    if (fr) body.push(h("div", { cls: "hint mt8", text: t(fr.verdict === "random" ? "fairOk" : "fairSkew").replace("{c}", fr.chi2).replace("{p}", fr.p_value).replace("{n}", Number(fr.samples).toLocaleString()) }));
    return card("numstats", "🔢", t("numstats"), (ns.latest_round ? ns.latest_round + t("round") + " · " : "") + t("nsRounds") + " " + ns.window + t("round"), body);
  }

  // ------------------------------------------------------------ mobile quick-jump bar
  function renderQnav(ids) {
    var nav = document.getElementById("qnav"); if (!nav) return;
    nav.textContent = "";
    ids.forEach(function (id) {
      var b = h("button", { type: "button", "aria-label": t("q_" + id), onclick: function () {
        var el = document.querySelector('[data-card="' + id + '"]'); if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
      } }, [ART[id] ? art(ART[id], "", "•") : h("span", { text: "•" }), h("span", { text: t("q_" + id) })]);
      nav.appendChild(b);
    });
    nav.appendChild(h("button", { cls: "top", type: "button", "aria-label": t("qTop"), title: t("qTop"), text: "▲", onclick: function () { window.scrollTo({ top: 0, behavior: "smooth" }); } }));
  }
  function statsCard() {
    var body = [h("div", { cls: "seg" }, [["all", t("statAll")], ["acc", t("statThis")]].map(function (o) {
      return h("button", { type: "button", "aria-pressed": statsScope === o[0] ? "true" : "false", text: o[1], onclick: function () { statsScope = o[0]; loadStats().then(render); } });
    }))];
    if (!stats || !stats.total || !(stats.total.spend || stats.total.win)) {
      body.push(h("div", { cls: "empty", text: t("statNone") }));
    } else {
      var tot = stats.total;
      body.push(h("dl", { cls: "kv" }, [h("dt", { text: t("statSpend") }), h("dd", { text: won(tot.spend) + " · " + tot.tickets + t("tickets") }),
        h("dt", { text: t("statWin") }), h("dd", { text: won(tot.win) + " · " + tot.wins + t("tickets") }),
        h("dt", { text: t("statRatio") }), h("dd", { text: tot.ratio + "%" }), h("dt", { text: t("statSince") }), h("dd", { text: stats.since || "-" })]));
      var max = 1;
      stats.months.forEach(function (m) { max = Math.max(max, m.spend, m.win); });
      body.push(h("div", { cls: "bars" }, stats.months.map(function (m) {
        var sp = h("span", { cls: "sbar spend", title: m.month + " · " + t("statSpend") + " " + won(m.spend) });
        var wn = h("span", { cls: "sbar win", title: m.month + " · " + t("statWin") + " " + won(m.win) });
        sp.style.height = Math.round(m.spend / max * 100) + "%"; wn.style.height = Math.round(m.win / max * 100) + "%";
        return h("div", { cls: "bcol" }, [h("div", { cls: "bstack" }, [sp, wn]), h("span", { cls: "blbl", text: m.month.slice(5) })]);
      })));
      body.push(h("div", { cls: "legend" }, [h("span", null, [h("i", { bg: "color-mix(in srgb, var(--ink) 38%, transparent)" }), t("statSpend")]), h("span", null, [h("i", { bg: "var(--gold)" }), t("statWin")])]));
      if ((stats.recent_wins || []).length) {
        body.push(h("div", { cls: "sect", text: "🎉 " + t("statWins") }));
        body.push(h("div", { cls: "rows" }, stats.recent_wins.slice(0, 5).map(function (w) {
          return h("div", { cls: "row won" }, [h("span", { cls: "main", text: (stats.labels && stats.labels[w.acct] || w.acct) + " · " + (w.game === "lotto" ? t("lottoShort") : t("pensionShort")) + " " + w.round + t("round") + " " + w.info }),
            h("span", { cls: "res r-gold", text: w.amount ? won(w.amount) : "-" })]);
        })));
      }
    }
    body.push(h("div", { cls: "hint", text: t("statNote") }));
    var file = h("input", { type: "file", accept: ".json,application/json", hidden: "hidden", onchange: function (e) {
      var f = e.target.files && e.target.files[0]; if (!f) return;
      f.text().then(function (txt) { return postJson("api/ledger/import", JSON.parse(txt)); })
        .then(function (j) { toast(t("importOk") + j.added + t("importSkip") + j.skipped, "ok"); return loadStats(); })
        .then(render)
        .catch(function (err) { toast(t("importFail") + err.message, "err"); });
      e.target.value = "";
    } });
    body.push(h("div", { cls: "btns tight mt10" }, [
      h("button", { cls: "btn secondary small", type: "button", text: t("exportCsv"), onclick: function () { download("api/ledger/export?format=csv"); } }),
      h("button", { cls: "btn secondary small", type: "button", text: t("exportJson"), onclick: function () { download("api/ledger/export?format=json"); } }),
      h("button", { cls: "btn secondary small", type: "button", text: t("importJson"), onclick: function () { file.click(); } }), file]));
    return card("stats", "📊", t("stats"), "", body);
  }

  // ------------------------------------------------------------ lucky lab (luck index · budget · claims · calendar)
  function gauge(pct, marker, over) {
    var g = h("div", { cls: "gauge" + (over ? " over" : "") }, [h("i"), marker === null ? null : h("em")]);
    g.firstChild.style.width = Math.max(0, Math.min(100, Number(pct) || 0)) + "%";
    if (marker !== null) g.lastChild.style.left = marker + "%";
    return g;
  }
  function insightCard(acc) {
    var body = [h("div", { cls: "seg" }, [["acc", t("statThis")], ["all", t("statAll")]].map(function (o) {
      return h("button", { type: "button", "aria-pressed": insightScope === o[0] ? "true" : "false", text: o[1], onclick: function () { insightScope = o[0]; render(); } });
    }))];
    if (!insights) { body.push(h("div", { cls: "empty", text: "…" })); return card("insight", "🧠", t("insight"), "", body); }
    var row = (insights.accounts || []).filter(function (r) { return r.id === acc.id; })[0] || {};
    var lk = (insightScope === "all" ? insights.all.luck : row.luck) || {};
    body.push(h("div", { cls: "sect", text: "🍀 " + t("luckTitle") }));
    if (lk.percentile === null || lk.percentile === undefined) body.push(h("div", { cls: "empty", text: t("luckNone") }));
    else {
      body.push(h("div", { cls: "luck" }, [h("b", { text: t("luckTop") + " " + lk.top_pct + "%" }), h("span", { text: t("luck_" + lk.grade) })]));
      body.push(gauge(lk.percentile, 50, false));
      body.push(h("div", { cls: "hint", text: t("luckDetail").replace("{g}", lk.lotto_games).replace("{p}", lk.pension_tickets)
        .replace("{e}", lk.expected).replace("{w}", lk.wins).replace("{r}", Number(lk.ratio).toLocaleString()) }));
      if (lk.jackpot_years) body.push(h("div", { cls: "hint", text: t("luckJackpot").replace("{n}", lk.lotto_per_week).replace("{y}", Number(lk.jackpot_years).toLocaleString()) }));
    }
    if (insightScope === "acc") {
      var bd = row.budget || {};
      body.push(h("div", { cls: "sect", text: "💳 " + t("budgetTitle") + (bd.month ? " · " + bd.month : "") }));
      if (!insights.budget_monthly) body.push(h("div", { cls: "hint", text: t("budgetOff") }));
      else {
        var over = bd.left !== null && bd.left <= 0;
        body.push(h("dl", { cls: "kv" }, [h("dt", { text: t("budgetUsed") }), h("dd", { text: won(bd.used) + " / " + won(bd.budget) }),
          h("dt", { text: t("budgetLeft") }), h("dd", { text: won(Math.max(0, bd.left)) })]));
        body.push(gauge(bd.pct, null, over));
        if (over) body.push(h("div", { cls: "hint", text: t("budgetOver") }));
      }
    }
    body.push(h("div", { cls: "sect", text: "💰 " + t("claimTitle") }));
    var cl = (insights.claims || []).filter(function (x) { return (insightScope === "all" || x.acct === acc.id) && x.days_left >= -30; });
    var visit = cl.filter(function (x) { return x.action === "visit"; });
    if (!visit.length) body.push(h("div", { cls: "hint", text: t("claimNone") }));
    cl.slice(0, 6).forEach(function (x) {
      body.push(h("div", { cls: "claim " + x.action }, [
        h("span", { text: (insightScope === "all" ? x.label + " · " : "") + (x.game === "lotto" ? t("lottoShort") : t("pensionShort")) + " " + x.round + t("round") + " " + x.info + (x.amount ? " · " + won(x.amount) : "") }),
        h("span", { cls: "dd", text: x.action === "auto" ? t("claimAuto") : (x.days_left >= 0 ? "D-" + x.days_left + " · " + x.deadline : t("claimExpired")) })]));
      if (x.action !== "auto" && x.how) body.push(h("div", { cls: "hint", text: t("how_" + x.how) }));
    });
    if (visit.length) body.push(h("div", { cls: "hint mt8", text: t("claimVisit") }));
    body.push(h("div", { cls: "btns tight mt10" }, [h("button", { cls: "btn secondary small", type: "button", text: t("icsBtn"), onclick: function () { download("api/calendar.ics"); } })]));
    body.push(h("div", { cls: "hint", text: t("icsHint") }));
    var icsStart = body.length;
    [["icsWhyT", ["icsWhy1", "icsWhy2", "icsWhy3"]], ["icsSkipT", ["icsSkip"]], ["icsWhatT", ["icsWhat"]],
      ["icsHowT", ["icsHow1", "icsHow2", "icsHow3", "icsHow4"]], ["icsNoteT", ["icsNote"]]].forEach(function (sec) {
      body.push(h("div", { cls: "sect", text: t(sec[0]) }));
      sec[1].forEach(function (k) { body.push(h("div", { cls: "hint", text: t(k) })); });
    });
    foldTail(body, icsStart, "ics-guide", t("icsFold"));
    body.push(h("div", { cls: "hint mt8", text: t("luckNote") }));
    return card("insight", "🧠", t("insight"), lk.top_pct ? t("luckTop") + " " + lk.top_pct + "%" : "", body);
  }
  function loadInsights() { return getJson("api/insights").then(function (j) { insights = j; }).catch(function () {}); }

  // ------------------------------------------------------------ auto-buy & notifications
  function dayNames() { return t("dayNames").split(","); }
  function autoCard() {
    if (!settings) return card("auto", "⏰", t("auto"), "", [h("div", { cls: "empty", text: "…" })]);
    var ab = settings.auto_buy, nt = settings.notify, body = [], dn = dayNames();
    var master = h("input", { type: "checkbox", checked: ab.enabled ? "checked" : null, "aria-label": t("autoMaster"), onchange: function (e) {
      if (e.target.checked) {
        e.target.checked = false;
        openModal(t("autoOnTitle"), [t("autoOnConfirm")], t("autoOn"), function () { saveSettings({ auto_buy: { enabled: true } }); });
      } else saveSettings({ auto_buy: { enabled: false } });
    } });
    body.push(h("label", { cls: "field strong" }, [h("span", { text: "⏰ " + t("autoMaster") }), master]));
    var accs = {}; (data.accounts || []).forEach(function (a) { accs[a.id] = a.label; });
    if (!ab.schedules.length) body.push(h("div", { cls: "empty", text: t("autoEmpty") }));
    else body.push(h("div", { cls: "rows" }, ab.schedules.map(function (sc) {
      var on = h("input", { type: "checkbox", checked: sc.enabled ? "checked" : null, "aria-label": sc.time, onchange: function (e) {
        saveSettings({ auto_buy: { schedules: ab.schedules.map(function (x) { return x.id === sc.id ? Object.assign({}, x, { enabled: e.target.checked }) : x; }) } });
      } });
      var what = sc.days.map(function (d) { return dn[d]; }).join("·") + " " + sc.time + " · " + ((data.actions[sc.action] || {}).label || sc.action) + " · " + (sc.account === "all" ? t("autoAllAcc") : (accs[sc.account] || sc.account));
      return h("div", { cls: "sched" + (sc.enabled ? "" : " off") }, [on, h("span", { text: what }),
        h("button", { cls: "mini", type: "button", text: "✕", title: t("autoDel"), "aria-label": t("autoDel"), onclick: function () {
          saveSettings({ auto_buy: { schedules: ab.schedules.filter(function (x) { return x.id !== sc.id; }) } });
        } })]);
    })));
    var act = h("select", { "aria-label": "action", onchange: function (e) { autoDraft.action = e.target.value; } },
      ["lotto_auto_1", "lotto_auto_5", "pension_auto_1", "pension_auto_5"].filter(function (a) { return a.indexOf("lotto") === 0 ? data.lotto_enabled : data.pension_enabled; }).map(function (a) {
        return h("option", { value: a, selected: autoDraft.action === a ? "selected" : null, text: (data.actions[a] || {}).label || a });
      }));
    var tm = h("input", { type: "time", value: autoDraft.time, "aria-label": "time", onchange: function (e) { autoDraft.time = e.target.value; } });
    var who = h("select", { "aria-label": "account", onchange: function (e) { autoDraft.account = e.target.value; } },
      [h("option", { value: "all", text: t("autoAllAcc") })].concat((data.accounts || []).map(function (a) {
        return h("option", { value: a.id, selected: autoDraft.account === a.id ? "selected" : null, text: a.label });
      })));
    var days = h("div", { cls: "days" }, dn.map(function (nm, i) {
      return h("button", { type: "button", "aria-pressed": autoDraft.days.indexOf(i) >= 0 ? "true" : "false", text: nm, onclick: function (e) {
        var k = autoDraft.days.indexOf(i); if (k >= 0) autoDraft.days.splice(k, 1); else autoDraft.days.push(i);
        e.target.setAttribute("aria-pressed", k >= 0 ? "false" : "true");
      } });
    }));
    var addStart = body.length;
    body.push(h("div", { cls: "manual" }, [act, tm, who]));
    body.push(h("div", { cls: "manual" }, [days, h("button", { cls: "btn small", type: "button", text: t("autoAdd"), disabled: ab.schedules.length >= 8 ? "disabled" : null, onclick: function () {
      if (!autoDraft.days.length) { toast(t("autoNeedDay"), "err"); return; }
      var sc = { action: act.value || autoDraft.action, time: tm.value || autoDraft.time, days: autoDraft.days.slice(), account: who.value || "all", enabled: true };
      saveSettings({ auto_buy: { schedules: ab.schedules.concat([sc]) } });
    } })]));
    body.push(h("div", { cls: "hint", text: "🛡️ " + t("autoGuard") }));
    foldTail(body, addStart, "schedule-add", t("foldSchedule"));
    var bud = h("input", { type: "text", inputmode: "numeric", value: String((settings.budget || {}).monthly || 0), "aria-label": t("nBudget"), onchange: function (e) {
      var v = Number(String(e.target.value).replace(/[^0-9]/g, "")); saveSettings({ budget: { monthly: isFinite(v) ? v : 0 } }, function () { loadInsights().then(render); });
    } });
    body.push(h("div", { cls: "field" }, [h("span", { text: t("nBudget") }), bud]));
    body.push(h("div", { cls: "hint", text: t("nBudgetHint") }));

    var notifyStart = body.length;
    function ntog(key, label) {
      return h("label", { cls: "field" }, [h("span", { text: label }), h("input", { type: "checkbox", checked: nt[key] ? "checked" : null, onchange: function (e) {
        var c = {}; c[key] = e.target.checked; saveSettings({ notify: c });
      } })]);
    }
    body.push(ntog("persistent", t("nPersistent")));
    var svc = h("input", { type: "text", value: nt.service || "", placeholder: t("nServicePh"), "aria-label": t("nService"), autocomplete: "off", onchange: function (e) {
      saveSettings({ notify: { service: e.target.value.trim() } }, function (ok) { if (ok && e.target.value.trim() && !settings.notify.service) toast(t("nTestFail"), "err"); });
    } });
    body.push(h("div", { cls: "field" }, [h("span", { text: t("nService") }), svc]));
    body.push(ntog("win", t("nWin")));
    body.push(ntog("purchase", t("nPurchase")));
    body.push(ntog("low_deposit", t("nLow")));
    var thr = h("input", { type: "text", inputmode: "numeric", value: String(nt.low_deposit_threshold), "aria-label": t("nThreshold"), onchange: function (e) {
      var v = Number(String(e.target.value).replace(/[^0-9]/g, "")); saveSettings({ notify: { low_deposit_threshold: isFinite(v) ? v : 0 } });
    } });
    body.push(h("div", { cls: "field" }, [h("span", { text: t("nThreshold") }), thr]));
    body.push(ntog("weekly_report", t("nWeekly")));
    body.push(ntog("deadline_reminder", t("nDeadline")));
    body.push(ntog("claim_reminder", t("nClaim")));
    var hh = h("input", { type: "checkbox", checked: (settings.household || {}).enabled ? "checked" : null, "aria-label": t("hhLabel"), onchange: function (e) {
      var on = e.target.checked;
      saveSettings({ household: { enabled: on } });
      if (on) getJson("api/household/status").then(function (j) { toast(j.available ? t("hhOk") : t("hhMissing"), j.available ? "ok" : "err"); }).catch(function () {});
    } });
    body.push(h("label", { cls: "field" }, [h("span", { text: t("hhLabel") }), hh]));
    body.push(h("div", { cls: "hint", text: t("hhHint") }));
    body.push(h("div", { cls: "manual" }, [h("button", { cls: "btn secondary small", type: "button", text: "🔔 " + t("nTest"), onclick: function () {
      postJson("api/notify-test", {}).then(function (j) { toast(j.ok ? t("nTestOk") : t("nTestFail"), j.ok ? "ok" : "err"); }).catch(function (e) { toast(t("nTestFail") + " " + e.message, "err"); });
    } }), h("button", { cls: "btn secondary small", type: "button", text: t("diag"), onclick: copyDiag })]));
    body.push(h("div", { cls: "hint", text: t("nEvents") }));
    foldTail(body, notifyStart, "notify", t("foldNotify"));
    return card("auto", "⏰", t("auto"), ab.enabled ? "ON" : "OFF", body);
  }

  // ------------------------------------------------------------ settings / stats / diagnostics IO
  function toast(msg, kind) { var n = document.getElementById("notices"); n.insertBefore(h("div", { cls: "notice " + (kind || ""), text: msg }), n.firstChild); }
  function getJson(url) {
    return fetch(url, { credentials: "same-origin", cache: "no-store" }).then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); });
  }
  function sendJson(url, method, body) {
    return fetch(url, { method: method, credentials: "same-origin", cache: "no-store",
      headers: { "Content-Type": "application/json", "X-DHL-CSRF": CSRF }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok) throw new Error(j.detail || ("HTTP " + r.status)); return j; }); });
  }
  function postJson(url, body) { return sendJson(url, "POST", body); }
  function loadSettings() { return getJson("api/settings").then(function (j) { settings = j; }).catch(function () {}); }
  function loadStats() {
    var q = statsScope === "acc" && current ? "?account=" + encodeURIComponent(current) : "";
    return getJson("api/stats" + q).then(function (j) { stats = j; }).catch(function () {});
  }
  function saveSettings(change, after) {
    return sendJson("api/settings", "PUT", change)
      .then(function (j) { settings = j; render(); if (after) after(true); })
      .catch(function (e) { toast(t("saveErr") + e.message, "err"); if (after) after(false); });
  }
  function copyDiag() {
    getJson("api/diagnostics").then(function (j) {
      var txt = j.text || "";
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(txt).then(function () { toast(t("diagCopied"), "ok"); }, function () { showDiag(txt); });
      } else showDiag(txt);
    }).catch(function (e) { toast(t("loadFail") + e.message, "err"); });
  }
  function showDiag(txt) {
    var ta = h("textarea", { cls: "diag mono", readonly: "readonly", "aria-label": t("diagTitle") }); ta.value = txt;
    openModal(t("diagTitle"), [t("diagManual"), ta], t("close"), null, true);
    setTimeout(function () { ta.focus(); ta.select(); }, 50);
  }

  function renderCelebrate(acc) {
    var box = document.getElementById("celebrate"); box.textContent = "";
    if (!acc || prefs.effects === false) return;
    var results = [];
    for (var i = 1; i <= 5; i++) results.push(st(acc, "lotto45_prev_game_" + i + "_result"));
    (at(acc, "pension720_last_round").games || []).forEach(function (g) { results.push(g.result); });
    var wins = results.filter(isWin);
    if (!wins.length) return;
    var jackpot = wins.some(function (r) { return String(r).indexOf("1등") >= 0; });
    var best = jackpot ? wins.filter(function (r) { return String(r).indexOf("1등") >= 0; })[0] : wins[0];
    var el = h("div", { cls: "celebrate" + (jackpot ? " jackpot" : "") }, [art(jackpot ? "jackpot" : "icon_win", "cel-img", ""),
      h("div", { cls: "cel-text" }, [jackpot ? t("jackpot") : t("congrats"), h("small", { text: best + " · " + t("congratsSub") })])]);
    var colors = ["#e0ad00", "#3fa9de", "#e5534b", "#8a8f98", "#79b33a", "#ffffff"];
    for (var c = 0; c < (jackpot ? 36 : 18); c++) {
      var p = h("span", { cls: "confetti" });
      p.style.left = rnd(100) + "%"; p.style.background = colors[c % colors.length];
      p.style.animationDelay = (rnd(2600) / 1000) + "s"; p.style.animationDuration = (2 + rnd(1500) / 1000) + "s";
      el.appendChild(p);
    }
    box.appendChild(el);
  }

  // ------------------------------------------------------------ render
  function currentAcc() { return data && data.accounts.filter(function (a) { return a.id === current; })[0]; }
  function render() {
    var tabs = document.getElementById("tabs"), grid = document.getElementById("grid"), notes = document.getElementById("notices");
    tabs.textContent = ""; grid.textContent = ""; notes.textContent = "";
    if (!data) { renderHero(null); return; }
    if (!data.accounts.length) { renderHero(null); grid.appendChild(h("div", { cls: "notice", text: t("noAcc") })); return; }
    if (!data.accounts.some(function (a) { return a.id === current; })) {
      current = data.accounts.some(function (a) { return a.id === prefs.default_account; }) ? prefs.default_account : data.accounts[0].id;
    }
    data.accounts.forEach(function (a) {
      tabs.appendChild(h("button", { cls: "tab", role: "tab", type: "button", "aria-selected": a.id === current ? "true" : "false",
        onclick: function () { current = a.id; render(); } }, [h("span", { cls: "dot " + (a.logged_in ? "on" : "off") }), a.label]));
    });
    var acc = currentAcc();
    renderHero(acc);
    renderCelebrate(acc);
    if (data.mqtt_connected === false) notes.appendChild(h("div", { cls: "notice warn" }, [h("b", { text: t("mqttDown") }),
      h("div", { cls: "hint closed", text: (data.mqtt_error ? "(" + data.mqtt_error + ") " : "") + t("mqttHow") })]));
    if (!data.purchase_available) notes.appendChild(h("div", { cls: "notice warn has-art" }, [art("empty", "notice-img", ""),
      h("div", null, [h("b", { text: t("lottoClosed") }), h("div", { cls: "hint closed", text: t("closedBody") })])]));
    [["lotto45_login_error", "loginErr"], ["lotto45_purchase_error", "lottoErr"], ["pension720_purchase_error", "penErr"]].forEach(function (p) {
      var v = st(acc, p[0]); if (v && v !== "없음") notes.appendChild(h("div", { cls: "notice err", text: t(p[1]) + ": " + v }));
    });
    var builders = { summary: summaryCard, buy: buyCard, favorites: favoritesCard, lotto_current: lottoCurrentCard, lotto_prev: lottoPrevCard,
      pension_current: pensionCurrentCard, pension_prev: pensionPrevCard, winning: winningCard, stats: statsCard, auto: autoCard,
      receipt: receiptCard, numstats: numStatsCard, insight: insightCard };
    var shown = [];
    var hidden = prefs.hidden_cards || [];
    (prefs.card_order || DEFAULT_ORDER).forEach(function (id) {
      if (hidden.indexOf(id) >= 0 || !builders[id]) return;
      if ((id === "lotto_current" || id === "lotto_prev") && !data.lotto_enabled) return;
      if ((id === "pension_current" || id === "pension_prev") && !data.pension_enabled) return;
      if (id === "numstats" && !data.lotto_enabled) return;
      grid.appendChild(builders[id](acc));
      shown.push(id);
    });
    renderQnav(shown);
  }

  function schedule() {
    clearTimeout(timer);
    var busy = data && data.accounts.some(function (a) { return a.last_action && a.last_action.status === "running"; });
    timer = setTimeout(load, busy ? 4000 : 60000);
  }
  function load() {
    fetch("api/dashboard", { credentials: "same-origin", cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error(r.status === 403 ? t("ingressOnly") : "HTTP " + r.status); return r.json(); })
      .then(function (j) { data = j; syncCooldowns(j); return Promise.all([loadSettings(), loadStats(), loadNumStats(false), loadInsights()]); })
      .then(function () { render(); })
      .catch(function (e) { render(); document.getElementById("notices").appendChild(h("div", { cls: "notice err", text: t("loadFail") + e.message })); })
      .then(schedule);
  }

  // ------------------------------------------------------------ purchase
  function collect(action) {
    var body = { account: current, action: action };
    if (action === "lotto_manual") body.numbers = (document.getElementById("lotto-manual") || {}).value || "";
    if (action === "pension_manual") { body.group = (document.getElementById("p-group") || {}).value || ""; body.digits = (document.getElementById("p-num") || {}).value || ""; }
    return body;
  }
  function openModal(title, nodes, okText, onOk, hideCancel) {
    document.getElementById("m-title").textContent = title;
    var b = document.getElementById("m-body"); b.textContent = "";
    nodes.forEach(function (n) { b.appendChild(typeof n === "string" ? document.createTextNode(n) : n); });
    var ok = document.getElementById("m-ok"), cancel = document.getElementById("m-cancel");
    ok.textContent = okText; cancel.textContent = t("cancel"); cancel.hidden = !!hideCancel; modalOk = onOk || null;
    document.getElementById("modal").classList.add("show");
    (hideCancel ? ok : cancel).focus();
  }
  function closeModal() { document.getElementById("modal").classList.remove("show"); modalOk = null; }
  function modalConfirm() { var cb = modalOk; closeModal(); if (cb) cb(); }
  function ask(acc, action, preset) {
    var info = data.actions[action]; if (!info) return;
    var body = preset ? Object.assign({ account: acc.id, action: action }, preset) : collect(action);
    var detail = action === "lotto_manual" ? " (" + body.numbers + ")" : action === "pension_manual" ? " (" + body.group + "-" + body.digits + ")" : "";
    openModal(t("confirmTitle"), [acc.label + t("confirmBody1") + info.label + detail + " — ", h("span", { cls: "amt", text: won(info.amount) }), t("confirmBody2")],
      t("confirm"), function () { sendBuy(body); });
  }
  function sendBuy(body) {
    postJson("api/purchase", body)
      .then(function () { delete drafts[body.account]; load(); })
      .catch(function (e) { toast(t("buyFail") + e.message, "err"); });
  }

  // ------------------------------------------------------------ settings drawer
  function drawerOpen() { return document.getElementById("drawer").classList.contains("show"); }
  function openDrawer() { saveState = ""; renderDrawer(); document.getElementById("drawer").classList.add("show"); document.getElementById("drawer-bg").classList.add("show"); }
  function closeDrawer() { document.getElementById("drawer").classList.remove("show"); document.getElementById("drawer-bg").classList.remove("show"); }
  function seg(key, options) {
    return h("div", { cls: "seg" }, options.map(function (o) {
      return h("button", { type: "button", "aria-pressed": prefs[key] === o[0] ? "true" : "false", text: o[1], onclick: function () { setPref(key, o[0]); } });
    }));
  }
  function toggle(key, label) {
    var cb = h("input", { type: "checkbox", checked: prefs[key] !== false ? "checked" : null, onchange: function (e) { setPref(key, e.target.checked); } });
    return h("label", { cls: "field" }, [h("span", { text: label }), cb]);
  }
  function renderDrawer() {
    var d = document.getElementById("drawer"), scroll = d.scrollTop; d.textContent = "";
    d.appendChild(h("div", { cls: "field" }, [h("h4", { id: "d-title", text: "⚙️ " + t("settings") }), h("button", { cls: "mini", type: "button", text: t("close"), onclick: closeDrawer })]));
    d.appendChild(h("div", { cls: "saved", id: "saved", text: saveState === "ok" ? t("savedOk") : saveState === "fail" ? t("saveFail") : "" }));
    d.appendChild(h("h5", { text: t("sTheme") }));
    ["gBasic", "gLucky", "gNight"].forEach(function (g) {
      d.appendChild(h("div", { cls: "hint", text: t(g) }));
      d.appendChild(h("div", { cls: "themes" }, THEMES.filter(function (x) { return x.g === g; }).map(function (x) {
        return h("button", { cls: "theme", type: "button", "aria-pressed": prefs.theme === x.id ? "true" : "false", onclick: function () { setPref("theme", x.id); } },
          [h("span", { cls: "sw", bg: x.sw }), prefs.lang === "en" ? x.en : x.ko]);
      })));
    });
    d.appendChild(h("h5", { text: t("sLang") }));
    d.appendChild(seg("lang", [["ko", "한국어"], ["en", "English"]]));
    d.appendChild(h("h5", { text: t("sDisplay") }));
    d.appendChild(h("div", { cls: "field" }, [h("span", { text: t("density") }), seg("density", [["comfortable", t("comfortable")], ["compact", t("compact")]])]));
    d.appendChild(h("div", { cls: "field" }, [h("span", { text: t("ballStyle") }), seg("ball_style", [["glossy", t("glossy")], ["flat", t("flat")]])]));
    d.appendChild(toggle("effects", t("effects")));
    d.appendChild(toggle("show_hero", t("showHero")));
    d.appendChild(h("h5", { text: t("sLucky") }));
    var lm = h("input", { type: "text", maxlength: "40", value: prefs.lucky_message || "", placeholder: t("luckyPh"), "aria-label": t("sLucky") });
    lm.addEventListener("change", function () { setPref("lucky_message", lm.value); });
    d.appendChild(h("div", { cls: "field" }, [lm]));
    if (data && data.accounts.length > 1) {
      d.appendChild(h("h5", { text: t("sAccount") }));
      var sel = h("select", { "aria-label": t("sAccount"), onchange: function (e) { setPref("default_account", e.target.value); } },
        [h("option", { value: "", text: t("firstAcc") })].concat(data.accounts.map(function (a) {
          return h("option", { value: a.id, selected: prefs.default_account === a.id ? "selected" : null, text: a.label });
        })));
      d.appendChild(h("div", { cls: "field" }, [sel]));
    }
    d.appendChild(h("h5", { text: t("sCards") }));
    var order = (prefs.card_order || DEFAULT_ORDER).slice(), hidden = prefs.hidden_cards || [];
    d.appendChild(h("div", { cls: "cardlist" }, order.map(function (id, i) {
      var cb = h("input", { type: "checkbox", checked: hidden.indexOf(id) < 0 ? "checked" : null, "aria-label": t(CARD_NAMES[id]), onchange: function (e) {
        var hs = (prefs.hidden_cards || []).filter(function (x) { return x !== id; }); if (!e.target.checked) hs.push(id); setPref("hidden_cards", hs);
      } });
      function move(delta) { var o = order.slice(), j = i + delta, tmp = o[i]; o[i] = o[j]; o[j] = tmp; setPref("card_order", o); }
      return h("div", { cls: "item" }, [cb, h("span", { text: t(CARD_NAMES[id]) }),
        h("button", { cls: "mini", type: "button", title: t("up"), "aria-label": t("up"), disabled: i === 0 ? "disabled" : null, text: "↑", onclick: function () { move(-1); } }),
        h("button", { cls: "mini", type: "button", title: t("down"), "aria-label": t("down"), disabled: i === order.length - 1 ? "disabled" : null, text: "↓", onclick: function () { move(1); } })]);
    })));
    d.appendChild(h("h5", { text: t("sSupport") }));
    d.appendChild(h("div", { cls: "field" }, [h("button", { cls: "btn secondary small", type: "button", text: t("diag"), onclick: copyDiag })]));
    d.appendChild(h("div", { cls: "field" }, [h("span"), h("button", { cls: "btn secondary", type: "button", text: t("reset"), onclick: function () {
      prefs = { theme: "system", lang: prefs.lang || "ko", density: "comfortable", ball_style: "glossy", effects: true, show_hero: true,
        lucky_message: "", default_account: "", hidden_cards: [] };
      setPref("card_order", DEFAULT_ORDER.slice());
    } })]));
    d.scrollTop = scroll;
  }

  // ------------------------------------------------------------ wire up
  document.getElementById("m-cancel").addEventListener("click", closeModal);
  document.getElementById("m-ok").addEventListener("click", modalConfirm);
  document.getElementById("modal").addEventListener("click", function (e) { if (e.target.id === "modal") closeModal(); });
  document.getElementById("drawer-bg").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") { closeModal(); closeDrawer(); } });
  document.getElementById("btn-reload").addEventListener("click", load);
  document.getElementById("btn-theme").addEventListener("click", openDrawer);
  document.getElementById("btn-lang").addEventListener("click", function () { setPref("lang", prefs.lang === "en" ? "ko" : "en"); });
  applyPrefs();
  render();
  load();
})();
</script>
</body>
</html>
"""

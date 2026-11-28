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
  font: 14px/1.5 "Pretendard", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans KR", "Apple SD Gothic Neo", sans-serif; }
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
  padding: 22px 24px; margin-bottom: var(--gap); display: grid; grid-template-columns: 1.1fr 1fr; gap: 18px; align-items: center; }
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
.card h3 { font-size: 15px; margin: 0 0 10px; display: flex; align-items: baseline; gap: 8px; }
.card h3 .ic { font-size: 16px; }
.card h3 .sub { color: var(--muted); font-weight: 500; font-size: 12px; }
.kv { display: grid; grid-template-columns: auto 1fr; gap: 6px 14px; margin: 10px 0 0; }
.kv dt { color: var(--muted); } .kv dd { margin: 0; text-align: right; font-variant-numeric: tabular-nums; }
.big { font-size: 26px; font-weight: 800; letter-spacing: -.02em; }
.hint { color: var(--muted); font-size: 12px; }
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
footer { color: var(--muted); font-size: 12px; text-align: center; padding: 22px 16px 30px; }
@media (max-width: 720px) { .hero { grid-template-columns: 1fr; } .hero-right { align-items: flex-start; } .hero-balls { justify-content: flex-start; } }
@media (max-width: 420px) { .grid { grid-template-columns: 1fr; } .hero { padding: 18px; } .hero h2 { font-size: 20px; } .hero .ball { width: 34px; height: 34px; font-size: 13px; }
  .themes { grid-template-columns: repeat(2, 1fr); } .count { min-width: 0; flex: 1; } }
</style>
</head>
<body>
<header><div class="bar">
  <div class="brand"><span class="logo">🎰</span><span>DH Lotto 45</span><span class="ver">v__VERSION__</span></div>
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
      lottoClosed: "지금은 로또 구매 불가 시간입니다 (토 20:00 ~ 일 06:00). 로또 버튼이 잠겨 있습니다.",
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
      gBasic: "기본", gLucky: "행운", gNight: "밤하늘 · 미래", up: "위로", down: "아래로", groupSuffix: "조" },
    en: { reload: "↻ Refresh", settings: "Settings", lang: "KO", summary: "Account", deposit: "Deposit", available: "Available to buy",
      login: "Login", ok: "OK", fail: "Failed", sync: "Sync", updatedAt: "Last update", buy: "Buy tickets",
      lottoCur: "Lotto · this round", lottoPrev: "Lotto · last round", penCur: "Pension · this round", penPrev: "Pension · last round",
      winning: "Latest winning numbers", none: "No tickets", weekly: "Week", games: "games", tickets: " tickets", round: "",
      winNums: "Winning", auto1: "Auto 1 game", auto5: "Auto 5 games", manual1: "Manual 1 game", pAuto1: "Auto 1", pAuto5: "Auto 5", pManual: "Manual 1",
      luckyPick: "🍀 Lucky pick", manualHint: "6 values, comma separated · use auto to fill the rest",
      running: "in progress… (pension takes up to 1-2 min)", confirmTitle: "Confirm purchase", cancel: "Cancel", confirm: "Buy",
      confirmBody1: " will buy ", confirmBody2: ". It is paid from the deposit right away.",
      lottoClosed: "Lotto sales are closed now (Sat 20:00 - Sun 06:00 KST). Lotto buttons are locked.",
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
      gBasic: "Basic", gLucky: "Lucky", gNight: "Night & future", up: "Up", down: "Down", groupSuffix: "G" }
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
  var DEFAULT_ORDER = ["summary", "buy", "lotto_current", "lotto_prev", "pension_current", "pension_prev", "winning"];
  var CARD_NAMES = { summary: "summary", buy: "buy", lotto_current: "lottoCur", lotto_prev: "lottoPrev",
    pension_current: "penCur", pension_prev: "penPrev", winning: "winning" };

  var prefs = {};
  try { prefs = JSON.parse(document.getElementById("dhl-prefs").textContent || "{}") || {}; } catch (e) { prefs = {}; }
  var data = null, current = null, timer = null, pending = null, saveTimer = null, saveState = "";
  var luckyIdx = Math.floor(Math.random() * 5);
  // Unsent manual inputs per account, kept across the periodic re-render.
  var drafts = {};
  function draft(acc) { return drafts[acc.id] || (drafts[acc.id] = {}); }
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
  function card(id, icon, title, sub, body) {
    return h("section", { cls: "card", "data-card": id }, [h("h3", null, [h("span", { cls: "ic", text: icon }), title, sub ? h("span", { cls: "sub", text: sub }) : null])].concat(body));
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
      right.appendChild(h("div", { cls: "lbl", text: "LOTTO 6/45 · " + (la.round || "") + t("latestDraw") }));
      right.appendChild(h("div", { cls: "hero-balls" }, balls(la.numbers).concat([h("span", { cls: "plus", text: "+" }), ball(la.bonus)])));
    }
    var fp = st(acc, "lotto645_first_prize");
    if (Number(fp) > 0) right.appendChild(h("div", { cls: "prize" }, [t("lastPrize") + "  ", h("b", { text: bigWon(fp) })]));
    hero.appendChild(right);
  }
  setInterval(function () {
    var a = document.getElementById("cd-lotto"), b = document.getElementById("cd-pension");
    if (a) a.textContent = fmtLeft(nextDraw(6, 20, 35));
    if (b) b.textContent = fmtLeft(nextDraw(4, 19, 5));
  }, 1000);
  setInterval(function () { luckyIdx++; var m = document.getElementById("hero-msg"); if (m) m.textContent = luckyMsg(); }, 8000);

  // ------------------------------------------------------------ cards
  function summaryCard(acc) {
    var bal = st(acc, "lotto45_balance"), ba = at(acc, "lotto45_balance"), last = S(acc, "lotto45_last_update");
    return card("summary", "💰", t("summary"), acc.label, [
      h("div", { cls: "big", text: bal === null ? "-" : won(bal) }), h("div", { cls: "hint", text: t("deposit") }),
      h("dl", { cls: "kv" }, [
        h("dt", { text: t("available") }), h("dd", { text: ba.purchase_available !== undefined ? won(ba.purchase_available) : "-" }),
        h("dt", { text: t("login") }), h("dd", null, [h("span", { cls: "dot " + (acc.logged_in ? "on" : "off") }), acc.logged_in ? t("ok") : t("fail")]),
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
    return rows.length ? h("div", { cls: "rows" }, rows) : h("div", { cls: "empty", text: t("none") });
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
    if (!games || !games.length) return h("div", { cls: "empty", text: t("none") });
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
      body.push(h("div", { cls: "hint", text: "LOTTO 6/45 · " + la.round + t("round") }));
      body.push(h("div", { cls: "row" }, [h("span", { cls: "main" }, balls(la.numbers).concat([h("span", { cls: "plus", text: "+" }), ball(la.bonus)]))]));
    }
    if (pa.number) {
      body.push(h("div", { cls: "hint", text: "PENSION 720+ · " + pa.round + t("round") }));
      body.push(h("div", { cls: "row" }, [h("span", { cls: "main" }, [ticket(pa.group, pa.number)]), h("span", { cls: "res r-wait", text: pa.bonus ? t("bonus") + " " + pa.bonus : "" })]));
    }
    if (!body.length) body.push(h("div", { cls: "empty", text: t("notLoaded") }));
    return card("winning", "🏆", t("winning"), "", body);
  }
  function buyCard(acc) {
    var avail = data.purchase_available, running = acc.last_action && acc.last_action.status === "running", body = [];
    function btn(label, action, extra, disabled) {
      return h("button", { cls: "btn" + (extra || ""), type: "button", disabled: (running || disabled) ? "disabled" : null, onclick: function () { ask(acc, action); }, text: label });
    }
    if (data.lotto_enabled) {
      body.push(h("div", { cls: "sect", text: "🎱 LOTTO 6/45" }));
      body.push(h("div", { cls: "btns" }, [btn(t("auto1"), "lotto_auto_1", "", !avail), btn(t("auto5"), "lotto_auto_5", "", !avail)]));
      var dr = draft(acc);
      var li = h("input", { cls: "lotto mono", id: "lotto-manual", value: dr.lotto !== undefined ? dr.lotto : (acc.manual_numbers || ""), oninput: function () { dr.lotto = li.value; }, placeholder: "1,7,12,auto,auto,auto", "aria-label": t("manual1"), autocomplete: "off" });
      var prev = h("div", { cls: "preview", id: "lotto-preview" });
      body.push(h("div", { cls: "manual" }, [li, btn(t("manual1"), "lotto_manual", " secondary", !avail)]));
      body.push(h("div", { cls: "manual" }, [h("button", { cls: "btn lucky", type: "button", text: t("luckyPick"), onclick: function () {
        var pool = [], picks = [];
        for (var n = 1; n <= 45; n++) pool.push(n);
        for (var k = 0; k < 6; k++) picks.push(pool.splice(rnd(pool.length), 1)[0]);
        picks.sort(function (a, b) { return a - b; });
        li.value = picks.join(","); dr.lotto = li.value;
        prev.textContent = ""; prev.classList.remove("rolling"); void prev.offsetWidth; prev.classList.add("rolling");
        picks.forEach(function (p, i) { var b = ball(p); b.style.animationDelay = (i * 0.08) + "s"; prev.appendChild(b); });
      } })]));
      body.push(prev);
      body.push(h("div", { cls: "hint", text: t("manualHint") }));
    }
    if (data.pension_enabled) {
      body.push(h("div", { cls: "sect", text: "🎟️ PENSION 720+" }));
      body.push(h("div", { cls: "btns" }, [btn(t("pAuto1"), "pension_auto_1"), btn(t("pAuto5"), "pension_auto_5")]));
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
    }
    var la = acc.last_action;
    if (la) {
      var txt = la.status === "running" ? "⏳ " + la.label + " " + t("running") :
        (la.status === "success" ? "✅ " : la.status === "skipped" ? "⚠️ " : "❌ ") + la.label + " — " + (la.message || "");
      body.push(h("div", { cls: "status " + la.status, text: txt + (la.finished ? " (" + fmtTime(la.finished) + ")" : "") }));
    }
    return card("buy", "🛒", t("buy"), acc.label, body);
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
    var el = h("div", { cls: "celebrate" + (jackpot ? " jackpot" : "") }, [jackpot ? t("jackpot") : t("congrats"), h("small", { text: best + " · " + t("congratsSub") })]);
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
    if (!data.purchase_available) notes.appendChild(h("div", { cls: "notice warn", text: t("lottoClosed") }));
    [["lotto45_login_error", "loginErr"], ["lotto45_purchase_error", "lottoErr"], ["pension720_purchase_error", "penErr"]].forEach(function (p) {
      var v = st(acc, p[0]); if (v && v !== "없음") notes.appendChild(h("div", { cls: "notice err", text: t(p[1]) + ": " + v }));
    });
    var builders = { summary: summaryCard, buy: buyCard, lotto_current: lottoCurrentCard, lotto_prev: lottoPrevCard,
      pension_current: pensionCurrentCard, pension_prev: pensionPrevCard, winning: winningCard };
    var hidden = prefs.hidden_cards || [];
    (prefs.card_order || DEFAULT_ORDER).forEach(function (id) {
      if (hidden.indexOf(id) >= 0 || !builders[id]) return;
      if ((id === "lotto_current" || id === "lotto_prev") && !data.lotto_enabled) return;
      if ((id === "pension_current" || id === "pension_prev") && !data.pension_enabled) return;
      grid.appendChild(builders[id](acc));
    });
  }

  function schedule() {
    clearTimeout(timer);
    var busy = data && data.accounts.some(function (a) { return a.last_action && a.last_action.status === "running"; });
    timer = setTimeout(load, busy ? 4000 : 60000);
  }
  function load() {
    fetch("api/dashboard", { credentials: "same-origin", cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error(r.status === 403 ? t("ingressOnly") : "HTTP " + r.status); return r.json(); })
      .then(function (j) { data = j; render(); })
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
  function ask(acc, action) {
    var info = data.actions[action]; if (!info) return;
    pending = collect(action);
    var detail = action === "lotto_manual" ? " (" + pending.numbers + ")" : action === "pension_manual" ? " (" + pending.group + "-" + pending.digits + ")" : "";
    var b = document.getElementById("m-body"); b.textContent = "";
    b.appendChild(document.createTextNode(acc.label + t("confirmBody1") + info.label + detail + " — "));
    b.appendChild(h("span", { cls: "amt", text: won(info.amount) }));
    b.appendChild(document.createTextNode(t("confirmBody2")));
    document.getElementById("modal").classList.add("show");
    document.getElementById("m-cancel").focus();
  }
  function closeModal() { document.getElementById("modal").classList.remove("show"); pending = null; }
  function confirmBuy() {
    var body = pending; closeModal(); if (!body) return;
    fetch("api/purchase", { method: "POST", credentials: "same-origin", cache: "no-store",
      headers: { "Content-Type": "application/json", "X-DHL-CSRF": CSRF }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok) throw new Error(j.detail || ("HTTP " + r.status)); return j; }); })
      .then(function () { delete drafts[body.account]; load(); })
      .catch(function (e) { var n = document.getElementById("notices"); n.insertBefore(h("div", { cls: "notice err", text: t("buyFail") + e.message }), n.firstChild); });
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
    d.appendChild(h("div", { cls: "field" }, [h("span"), h("button", { cls: "btn secondary", type: "button", text: t("reset"), onclick: function () {
      prefs = { theme: "system", lang: prefs.lang || "ko", density: "comfortable", ball_style: "glossy", effects: true, show_hero: true,
        lucky_message: "", default_account: "", hidden_cards: [] };
      setPref("card_order", DEFAULT_ORDER.slice());
    } })]));
    d.scrollTop = scroll;
  }

  // ------------------------------------------------------------ wire up
  document.getElementById("m-cancel").addEventListener("click", closeModal);
  document.getElementById("m-ok").addEventListener("click", confirmBuy);
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

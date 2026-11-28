"""
dashboard_page.py
사이드바(Ingress) 대시보드 HTML. main.py 의 GET / 가 __NONCE__/__CSRF__/__VERSION__ 을 치환해 응답한다.

- 모든 데이터는 api/dashboard(JSON)에서 받아 textContent 로만 그린다(innerHTML 미사용 → XSS 차단).
- 스크립트·스타일은 CSP nonce 로만 실행된다.
- 경로는 상대경로(api/...)라 Ingress 경로(/api/hassio_ingress/<token>/) 아래에서도 동작한다.
"""

PAGE_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="dhl-csrf" content="__CSRF__">
<title>DH Lotto 45</title>
<style nonce="__NONCE__">
:root {
  --bg: #f3f4f7; --card: #ffffff; --ink: #1d2330; --muted: #6b7280; --line: #e5e7eb;
  --accent: #03a9f4; --accent-ink: #ffffff; --ok: #2e7d32; --warn: #b26a00; --err: #c62828;
  --chip: #eef2f7; --shadow: 0 1px 2px rgba(16,24,40,.06), 0 1px 3px rgba(16,24,40,.08);
  --gold: #c99700; --silver: #7d8691; --bronze: #a05a2c; --green: #2e7d32; --red: #c62828; --grey: #8a93a0;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #111418; --card: #1c2026; --ink: #e6e9ee; --muted: #9aa3af; --line: #2c323b;
    --accent: #29b6f6; --accent-ink: #0b1220; --chip: #262c34; --shadow: none;
  }
}
* { box-sizing: border-box; }
html, body { margin: 0; background: var(--bg); color: var(--ink);
  font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans KR", "Apple SD Gothic Neo", sans-serif; }
header { position: sticky; top: 0; z-index: 5; background: var(--card); border-bottom: 1px solid var(--line);
  padding: 12px 16px; display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
header h1 { font-size: 18px; margin: 0; font-weight: 700; letter-spacing: -.01em; }
header .ver { color: var(--muted); font-size: 12px; }
header .spacer { flex: 1; }
.tabs { display: flex; gap: 6px; flex-wrap: wrap; }
.tab { border: 1px solid var(--line); background: var(--chip); color: var(--ink); border-radius: 999px;
  padding: 5px 12px; cursor: pointer; font: inherit; }
.tab[aria-selected="true"] { background: var(--accent); color: var(--accent-ink); border-color: var(--accent); }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }
.dot.on { background: var(--ok); } .dot.off { background: var(--err); }
button.icon { border: 1px solid var(--line); background: var(--card); color: var(--ink); border-radius: 8px;
  padding: 6px 10px; cursor: pointer; font: inherit; }
main { max-width: 1200px; margin: 0 auto; padding: 16px; }
.notice { border-radius: 10px; padding: 10px 14px; margin-bottom: 14px; border: 1px solid var(--line); background: var(--card); }
.notice.warn { border-color: #f0c36d; background: rgba(240,195,109,.15); }
.notice.err { border-color: #ef9a9a; background: rgba(239,154,154,.15); }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 14px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px; box-shadow: var(--shadow); min-width: 0; }
.card h2 { font-size: 15px; margin: 0 0 10px; display: flex; align-items: baseline; gap: 8px; }
.card h2 .sub { color: var(--muted); font-weight: 400; font-size: 12px; }
.kv { display: grid; grid-template-columns: auto 1fr; gap: 6px 14px; }
.kv dt { color: var(--muted); } .kv dd { margin: 0; text-align: right; font-variant-numeric: tabular-nums; }
.big { font-size: 22px; font-weight: 700; }
.rows { display: flex; flex-direction: column; gap: 8px; }
.row { display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-radius: 10px; background: var(--chip); min-width: 0; }
.row .idx { color: var(--muted); width: 18px; text-align: center; font-variant-numeric: tabular-nums; }
.row .main { flex: 1; min-width: 0; display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.row .res { font-size: 12px; white-space: nowrap; font-weight: 600; }
.empty { color: var(--muted); padding: 6px 2px; }
.ball { width: 28px; height: 28px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 12px; color: #fff; text-shadow: 0 1px 1px rgba(0,0,0,.25); flex: none; }
.ball.y { background: #e0ad00; } .ball.b { background: #3fa9de; } .ball.r { background: #e5534b; }
.ball.g { background: #8a8f98; } .ball.l { background: #79b33a; } .ball.q { background: transparent; color: var(--muted);
  border: 1px dashed var(--muted); text-shadow: none; }
.plus { color: var(--muted); margin: 0 2px; }
.ticket { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 15px; letter-spacing: .08em; }
.ticket .grp { font-family: inherit; letter-spacing: 0; color: var(--muted); margin-right: 6px; font-size: 13px; }
.c-gold { color: var(--gold); } .c-silver { color: var(--silver); } .c-bronze { color: var(--bronze); }
.c-green { color: var(--green); } .c-red { color: var(--red); } .c-grey { color: var(--grey); }
.c-blue { color: var(--accent); }
.buy h3 { font-size: 13px; margin: 12px 0 8px; color: var(--muted); font-weight: 600; }
.buy h3:first-of-type { margin-top: 0; }
.btns { display: flex; flex-wrap: wrap; gap: 8px; }
.btn { border: 0; border-radius: 9px; padding: 9px 14px; font: inherit; font-weight: 600; cursor: pointer;
  background: var(--accent); color: var(--accent-ink); }
.btn.secondary { background: var(--chip); color: var(--ink); border: 1px solid var(--line); }
.btn:disabled { opacity: .45; cursor: not-allowed; }
.manual { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; align-items: center; }
.manual input, .manual select { font: inherit; color: var(--ink); background: var(--card); border: 1px solid var(--line);
  border-radius: 8px; padding: 8px 10px; min-width: 0; }
.manual input.lotto { flex: 1 1 220px; }
.manual input.pnum { width: 120px; font-family: ui-monospace, Menlo, Consolas, monospace; letter-spacing: .1em; }
.hint { color: var(--muted); font-size: 12px; margin-top: 6px; }
.status { margin-top: 12px; padding: 8px 10px; border-radius: 8px; background: var(--chip); font-size: 13px; }
.status.running { color: var(--warn); } .status.success { color: var(--ok); } .status.error, .status.skipped { color: var(--err); }
.modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: none; align-items: center; justify-content: center; z-index: 20; padding: 16px; }
.modal-bg.show { display: flex; }
.modal { background: var(--card); color: var(--ink); border-radius: 14px; padding: 18px; width: 100%; max-width: 380px; border: 1px solid var(--line); }
.modal h3 { margin: 0 0 8px; font-size: 16px; }
.modal p { margin: 0 0 14px; color: var(--muted); }
.modal .amt { color: var(--ink); font-weight: 700; }
.modal .btns { justify-content: flex-end; }
footer { color: var(--muted); font-size: 12px; text-align: center; padding: 20px 16px 28px; }
@media (max-width: 420px) { .grid { grid-template-columns: 1fr; } header h1 { font-size: 16px; } }
</style>
</head>
<body>
<header>
  <h1>🎰 DH Lotto 45</h1><span class="ver">v__VERSION__</span>
  <div class="tabs" id="tabs" role="tablist"></div>
  <span class="spacer"></span>
  <span class="ver" id="updated"></span>
  <button class="icon" id="reload" type="button" title="새로고침">↻ 새로고침</button>
</header>
<main>
  <div id="notices"></div>
  <div class="grid" id="grid"></div>
</main>
<footer>복권 구매는 만 19세 이상만 가능합니다. 구매 전 금액과 계정을 꼭 확인하세요.</footer>

<div class="modal-bg" id="modal" role="dialog" aria-modal="true" aria-labelledby="m-title">
  <div class="modal">
    <h3 id="m-title">구매 확인</h3>
    <p id="m-body"></p>
    <div class="btns">
      <button class="btn secondary" id="m-cancel" type="button">취소</button>
      <button class="btn" id="m-ok" type="button">구매</button>
    </div>
  </div>
</div>

<script nonce="__NONCE__">
(function () {
  "use strict";
  var CSRF = document.querySelector('meta[name="dhl-csrf"]').getAttribute("content");
  var data = null, current = null, timer = null, pending = null;
  try { current = localStorage.getItem("dhl_account"); } catch (e) {}

  function h(tag, attrs, kids) {
    var e = document.createElement(tag);
    if (attrs) for (var k in attrs) {
      if (k === "text") e.textContent = attrs[k];
      else if (k === "cls") e.className = attrs[k];
      else if (k.slice(0, 2) === "on") e.addEventListener(k.slice(2), attrs[k]);
      else if (attrs[k] !== null && attrs[k] !== undefined && attrs[k] !== false) e.setAttribute(k, attrs[k]);
    }
    (kids || []).forEach(function (c) { if (c !== null && c !== undefined) e.appendChild(typeof c === "string" ? document.createTextNode(c) : c); });
    return e;
  }
  function S(acc, id) { return (acc.sensors && acc.sensors[id]) || null; }
  function st(acc, id) { var s = S(acc, id); return s ? s.state : null; }
  function at(acc, id) { var s = S(acc, id); return (s && s.attributes) || {}; }
  function won(n) { var v = Number(n); return isFinite(v) ? v.toLocaleString("ko-KR") + "원" : "-"; }
  function ballCls(n) { n = Number(n); return n <= 10 ? "y" : n <= 20 ? "b" : n <= 30 ? "r" : n <= 40 ? "g" : "l"; }
  function ball(n) { return h("span", { cls: "ball " + ballCls(n), text: String(n) }); }
  function balls(list) { return (list || []).map(ball); }
  function resColor(r) {
    r = String(r || "");
    if (!r || r === "-" || r.indexOf("미추첨") >= 0 || r === "구매 내역 없음") return "c-grey";
    if (r.indexOf("낙첨") >= 0 || r.indexOf("등외") >= 0) return "c-red";
    if (r.indexOf("1등") >= 0) return "c-gold";
    if (r.indexOf("2등") >= 0) return "c-silver";
    if (r.indexOf("3등") >= 0) return "c-bronze";
    return "c-green";
  }
  function card(title, sub, body) {
    return h("section", { cls: "card" }, [h("h2", null, [title, sub ? h("span", { cls: "sub", text: sub }) : null])].concat(body));
  }
  function fmtTime(ts) {
    if (!ts) return "-";
    var d = new Date(ts * 1000);
    return d.toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
  }

  // ---------------------------------------------------------------- cards
  function summaryCard(acc) {
    var bal = st(acc, "lotto45_balance"), ba = at(acc, "lotto45_balance");
    var sync = st(acc, "lotto45_sync_status"), last = S(acc, "lotto45_last_update");
    return card("계정 요약", acc.label, [
      h("div", { cls: "big", text: bal === null ? "-" : won(bal) }),
      h("div", { cls: "hint", text: "예치금" }),
      h("dl", { cls: "kv" }, [
        h("dt", { text: "구매 가능 금액" }), h("dd", { text: ba.purchase_available !== undefined ? won(ba.purchase_available) : "-" }),
        h("dt", { text: "로그인" }), h("dd", null, [h("span", { cls: "dot " + (acc.logged_in ? "on" : "off") }), acc.logged_in ? "정상" : "실패"]),
        h("dt", { text: "동기화" }), h("dd", { text: sync || "-" }),
        h("dt", { text: "마지막 갱신" }), h("dd", { text: last ? fmtTime(last.ts) : "-" })
      ])
    ]);
  }

  function lottoRows(acc, prefix) {
    var rows = [];
    for (var i = 1; i <= 5; i++) {
      var g = S(acc, prefix + i);
      if (!g || !g.attributes || !(g.attributes.numbers || []).length) continue;
      var res = st(acc, prefix + i + "_result") || g.attributes.result || "-";
      rows.push(h("div", { cls: "row" }, [
        h("span", { cls: "idx", text: String(i) }),
        h("span", { cls: "main" }, balls(g.attributes.numbers)),
        h("span", { cls: "res " + resColor(res), text: res })
      ]));
    }
    return rows.length ? h("div", { cls: "rows" }, rows) : h("div", { cls: "empty", text: "구매 내역 없음" });
  }
  function lottoCurrentCard(acc) {
    var w = at(acc, "lotto45_weekly_purchase_count"), cnt = st(acc, "lotto45_weekly_purchase_count");
    var round = at(acc, "lotto45_game_1").round_no;
    return card("로또 이번 회차", (round ? round + "회 · " : "") + "주간 " + (cnt === null ? "-" : cnt) + "/" + (w.weekly_limit || 5) + "게임",
      [lottoRows(acc, "lotto45_game_")]);
  }
  function lottoPrevCard(acc) {
    var r = st(acc, "lotto45_prev_round"), wa = at(acc, "lotto45_prev_game_1_result");
    var body = [lottoRows(acc, "lotto45_prev_game_")];
    if ((wa.winning_numbers || []).length) {
      body.unshift(h("div", { cls: "row" }, [h("span", { cls: "idx", text: "★" }),
        h("span", { cls: "main" }, balls(wa.winning_numbers).concat([h("span", { cls: "plus", text: "+" }), ball(wa.bonus_number)])),
        h("span", { cls: "res c-blue", text: "당첨번호" })]));
    }
    return card("로또 지난 회차", r && Number(r) > 0 ? r + "회" : "", body);
  }

  function pensionRows(games) {
    if (!games || !games.length) return h("div", { cls: "empty", text: "구매 내역 없음" });
    return h("div", { cls: "rows" }, games.map(function (g, i) {
      return h("div", { cls: "row" }, [
        h("span", { cls: "idx", text: String(i + 1) }),
        h("span", { cls: "main ticket" }, [g.group ? h("span", { cls: "grp", text: g.group + "조" }) : null, String(g.number || "")]),
        h("span", { cls: "res " + resColor(g.result), text: (g.result || "-") + (g.win_amount > 0 ? " · " + won(g.win_amount) : "") })
      ]);
    }));
  }
  function pensionCurrentCard(acc) {
    var a = at(acc, "pension720_this_round");
    return card("연금복권 이번 회차", (a.round_no ? a.round_no + "회 · " : "") + (a.games ? a.games.length : 0) + "매", [pensionRows(a.games)]);
  }
  function pensionPrevCard(acc) {
    var a = at(acc, "pension720_last_round");
    var body = [];
    if (a.result_summary) body.push(h("div", { cls: "hint", text: a.result_summary }));
    body.push(pensionRows(a.games));
    return card("연금복권 지난 회차", a.round_no ? a.round_no + "회" : "", body);
  }

  function winningCard(acc) {
    var la = at(acc, "lotto645_winning_numbers"), pa = at(acc, "pension720_winning_number");
    var body = [];
    if ((la.numbers || []).length) {
      body.push(h("div", { cls: "hint", text: "로또 6/45 · " + la.round + "회" }));
      body.push(h("div", { cls: "row" }, [h("span", { cls: "main" }, balls(la.numbers).concat([h("span", { cls: "plus", text: "+" }), ball(la.bonus)]))]));
    }
    if (pa.number) {
      body.push(h("div", { cls: "hint", text: "연금복권720+ · " + pa.round + "회" }));
      body.push(h("div", { cls: "row" }, [h("span", { cls: "main ticket" }, [h("span", { cls: "grp", text: pa.group + "조" }), String(pa.number)]),
        h("span", { cls: "res c-grey", text: pa.bonus ? "보너스 " + pa.bonus : "" })]));
    }
    if (!body.length) body.push(h("div", { cls: "empty", text: "당첨번호를 아직 불러오지 못했습니다" }));
    return card("최신 당첨번호", "", body);
  }

  function buyCard(acc) {
    var avail = data.purchase_available;
    var running = acc.last_action && acc.last_action.status === "running";
    var body = [];
    function btn(label, action, extra, disabled) {
      return h("button", { cls: "btn" + (extra || ""), type: "button", disabled: (running || disabled) ? "disabled" : null,
        onclick: function () { ask(acc, action); } , text: label });
    }
    if (data.lotto_enabled) {
      body.push(h("h3", { text: "로또 6/45" }));
      body.push(h("div", { cls: "btns" }, [btn("자동 1게임", "lotto_auto_1", "", !avail), btn("자동 5게임", "lotto_auto_5", "", !avail)]));
      var li = h("input", { cls: "lotto", id: "lotto-manual", value: acc.manual_numbers || "", placeholder: "1,7,12,auto,auto,auto",
        "aria-label": "로또 수동 번호", autocomplete: "off", inputmode: "text" });
      body.push(h("div", { cls: "manual" }, [li, btn("수동 1게임", "lotto_manual", " secondary", !avail)]));
      body.push(h("div", { cls: "hint", text: "6칸을 쉼표로 구분 · 자동으로 채울 칸은 auto (반자동)" }));
    }
    if (data.pension_enabled) {
      body.push(h("h3", { text: "연금복권720+" }));
      body.push(h("div", { cls: "btns" }, [btn("자동 1매", "pension_auto_1"), btn("자동 5매", "pension_auto_5")]));
      var pm = String(acc.pension_manual || "").split(",");
      var sel = h("select", { id: "p-group", "aria-label": "조" }, [1, 2, 3, 4, 5].map(function (g) {
        return h("option", { value: String(g), selected: String(g) === (pm[0] || "").trim() ? "selected" : null, text: g + "조" });
      }));
      var num = h("input", { cls: "pnum", id: "p-num", value: (pm[1] || "").trim(), placeholder: "123456", maxlength: "6",
        inputmode: "numeric", "aria-label": "연금 번호 6자리", autocomplete: "off" });
      body.push(h("div", { cls: "manual" }, [sel, num, btn("수동 1매", "pension_manual", " secondary")]));
    }
    var la = acc.last_action;
    if (la) {
      var txt = la.status === "running" ? "⏳ " + la.label + " 진행 중… (연금은 최대 1~2분)" :
        (la.status === "success" ? "✅ " : la.status === "skipped" ? "⚠️ " : "❌ ") + la.label + " — " + (la.message || "");
      body.push(h("div", { cls: "status " + la.status, text: txt + (la.finished ? " (" + fmtTime(la.finished) + ")" : "") }));
    }
    return card("구매하기", acc.label, [h("div", { cls: "buy" }, body)]);
  }

  // ---------------------------------------------------------------- render
  function render() {
    var tabs = document.getElementById("tabs"), grid = document.getElementById("grid"), notes = document.getElementById("notices");
    tabs.textContent = ""; grid.textContent = ""; notes.textContent = "";
    if (!data || !data.accounts.length) { grid.appendChild(h("div", { cls: "notice", text: "설정된 계정이 없습니다. 애드온 설정에서 계정을 추가하세요." })); return; }
    if (!data.accounts.some(function (a) { return a.id === current; })) current = data.accounts[0].id;
    data.accounts.forEach(function (a) {
      tabs.appendChild(h("button", { cls: "tab", role: "tab", type: "button", "aria-selected": a.id === current ? "true" : "false",
        onclick: function () { current = a.id; try { localStorage.setItem("dhl_account", current); } catch (e) {} render(); } },
        [h("span", { cls: "dot " + (a.logged_in ? "on" : "off") }), a.label]));
    });
    var acc = data.accounts.filter(function (a) { return a.id === current; })[0];
    if (!data.purchase_available) notes.appendChild(h("div", { cls: "notice warn", text: "지금은 로또 구매 불가 시간입니다 (토 20:00 ~ 일 06:00). 로또 구매 버튼이 잠겨 있습니다." }));
    [["lotto45_login_error", "로그인 오류"], ["lotto45_purchase_error", "로또 구매 오류"], ["pension720_purchase_error", "연금 구매 오류"]].forEach(function (p) {
      var v = st(acc, p[0]);
      if (v && v !== "없음") notes.appendChild(h("div", { cls: "notice err", text: p[1] + ": " + v }));
    });
    grid.appendChild(summaryCard(acc));
    grid.appendChild(buyCard(acc));
    if (data.lotto_enabled) { grid.appendChild(lottoCurrentCard(acc)); grid.appendChild(lottoPrevCard(acc)); }
    if (data.pension_enabled) { grid.appendChild(pensionCurrentCard(acc)); grid.appendChild(pensionPrevCard(acc)); }
    grid.appendChild(winningCard(acc));
    document.getElementById("updated").textContent = "업데이트 " + new Date().toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
  }

  function schedule() {
    clearTimeout(timer);
    var busy = data && data.accounts.some(function (a) { return a.last_action && a.last_action.status === "running"; });
    timer = setTimeout(load, busy ? 4000 : 60000);
  }
  function load() {
    fetch("api/dashboard", { credentials: "same-origin", cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error(r.status === 403 ? "사이드바(Ingress)에서 열어야 볼 수 있습니다." : "HTTP " + r.status); return r.json(); })
      .then(function (j) { data = j; render(); })
      .catch(function (e) {
        var notes = document.getElementById("notices"); notes.textContent = "";
        notes.appendChild(h("div", { cls: "notice err", text: "불러오기 실패: " + e.message }));
      })
      .then(schedule);
  }

  // ---------------------------------------------------------------- purchase
  function collect(action) {
    var body = { account: current, action: action };
    if (action === "lotto_manual") body.numbers = (document.getElementById("lotto-manual") || {}).value || "";
    if (action === "pension_manual") {
      body.group = (document.getElementById("p-group") || {}).value || "";
      body.digits = (document.getElementById("p-num") || {}).value || "";
    }
    return body;
  }
  function ask(acc, action) {
    var info = data.actions[action]; if (!info) return;
    pending = collect(action);
    var detail = "";
    if (action === "lotto_manual") detail = " · 번호 " + pending.numbers;
    if (action === "pension_manual") detail = " · " + pending.group + "조 " + pending.digits;
    var b = document.getElementById("m-body"); b.textContent = "";
    b.appendChild(document.createTextNode(acc.label + " 계정으로 " + info.label + detail + " — "));
    b.appendChild(h("span", { cls: "amt", text: won(info.amount) }));
    b.appendChild(document.createTextNode(" 을(를) 구매합니다. 예치금에서 바로 결제됩니다."));
    document.getElementById("modal").classList.add("show");
    document.getElementById("m-cancel").focus();
  }
  function closeModal() { document.getElementById("modal").classList.remove("show"); pending = null; }
  function confirmBuy() {
    var body = pending; closeModal(); if (!body) return;
    fetch("api/purchase", { method: "POST", credentials: "same-origin", cache: "no-store",
      headers: { "Content-Type": "application/json", "X-DHL-CSRF": CSRF }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok) throw new Error(j.detail || ("HTTP " + r.status)); return j; }); })
      .then(load)
      .catch(function (e) {
        var notes = document.getElementById("notices");
        notes.insertBefore(h("div", { cls: "notice err", text: "구매 요청 실패: " + e.message }), notes.firstChild);
      });
  }
  document.getElementById("m-cancel").addEventListener("click", closeModal);
  document.getElementById("m-ok").addEventListener("click", confirmBuy);
  document.getElementById("modal").addEventListener("click", function (e) { if (e.target.id === "modal") closeModal(); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeModal(); });
  document.getElementById("reload").addEventListener("click", load);
  load();
})();
</script>
</body>
</html>
"""

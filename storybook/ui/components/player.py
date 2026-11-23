"""브라우저 책 재생기 — 실시간 스트리밍.

book.json 을 계속 읽어 가며, 음성 조각(p<n>_<i>.pcm)이 생기는 대로 Web Audio 로 끊김 없이 이어 재생하고,
지금 읽는 줄(해설/인물 대사)을 강조합니다. 그림은 완성되는 대로 나타나고, 페이지는 자동으로 넘어갑니다.

주의: Streamlit(st.html)은 DOMPurify 로 HTML 을 정리하는데, <script> 안에 '<글자' 나 '</' 가 있으면
스크립트를 통째로 지운다. 그래서 화면 구조는 스크립트 밖에 두고, 스크립트에는 태그 모양 문자열을 쓰지 않는다.
"""

import json
import re

import streamlit as st

from storybook import config

BASE_URL = "app/static/books/"
_BTN = "padding:6px 14px;border-radius:999px;border:1px solid #d9c6a5;background:#fff;color:#3b2f2f;cursor:pointer;"

_HTML = """
<div id="bk-__ID__" style="background:#fffaf0;color:#3b2f2f;border-radius:18px;padding:14px;box-shadow:0 2px 12px rgba(0,0,0,.12);max-width:960px;margin:0 auto;">
  <div id="bk-__ID__-status" style="font-size:.9rem;color:#8a6d4b;min-height:1.3em;margin-bottom:8px;">📖 책을 펼치는 중...</div>
  <div style="position:relative;width:100%;aspect-ratio:4/3;max-height:50vh;background:#f3e9d8;border-radius:12px;overflow:hidden;display:flex;align-items:center;justify-content:center;">
    <img id="bk-__ID__-img" alt="" style="width:100%;height:100%;object-fit:cover;display:none;transition:opacity .35s ease;">
    <div id="bk-__ID__-ph" style="font-size:1rem;color:#a08360;text-align:center;">🎨<br>그림을 그리는 중...</div>
  </div>
  <div id="bk-__ID__-lines" style="font-size:1.2rem;line-height:1.65;padding:10px 4px 4px;min-height:5em;max-height:32vh;overflow-y:auto;word-break:keep-all;"></div>
  <div style="display:flex;gap:8px;align-items:center;justify-content:center;flex-wrap:wrap;padding-top:8px;">
    <button id="bk-__ID__-prev" style="__BTN__">◀ 이전</button>
    <button id="bk-__ID__-play" style="padding:6px 18px;border-radius:999px;border:none;background:#e07a5f;color:#fff;cursor:pointer;font-weight:600;">⏸ 멈춤</button>
    <button id="bk-__ID__-next" style="__BTN__">다음 ▶</button>
    <button id="bk-__ID__-again" style="__BTN__">↺ 처음부터</button>
    <span id="bk-__ID__-page" style="font-size:.9rem;color:#8a6d4b;margin-left:6px;"></span>
  </div>
  <div id="bk-__ID__-chaps" style="display:flex;gap:6px;flex-wrap:wrap;justify-content:center;padding-top:8px;"></div>
</div>
<script>
(async () => {
  const id = __ID_JS__, P = "bk-" + id, SR = 24000, NARR = "해설", PAUSE = __PAUSE__;
  const base = window.location.pathname.replace(/[^/]*$/, "") + __BASE_JS__ + id + "/";
  const $ = (k) => document.getElementById(P + "-" + k);
  const img = $("img"), ph = $("ph"), linesEl = $("lines"), status = $("status"), pageEl = $("page");
  const bPrev = $("prev"), bPlay = $("play"), bNext = $("next"), bAgain = $("again"), chapsEl = $("chaps");
  let chapBtns = [];
  const COLORS = ["#c0392b", "#2471a3", "#1e8449", "#8e44ad", "#d35400", "#16a085"];

  if (window.__bookStop) window.__bookStop();            // 다른 책 재생 중이면 멈춤
  // 새 책이 열리면 재생기가 보이도록 스크롤 (휴대폰처럼 재생기가 아래에 있는 화면)
  window.__bookScrolled = window.__bookScrolled || {};
  if (__SCROLL__ && !window.__bookScrolled[id]) {
    window.__bookScrolled[id] = true;
    const r = document.getElementById(P).getBoundingClientRect();
    if (r.top > window.innerHeight * 0.5 || r.bottom < 80) document.getElementById(P).scrollIntoView({ behavior: "smooth", block: "start" });
  }
  const AC = window.AudioContext || window.webkitAudioContext;
  window.__bookCtx = window.__bookCtx || new AC({ sampleRate: SR });
  const ctx = window.__bookCtx;
  ctx.resume().catch(() => {});

  let stopped = false, book = null, cur = -1, sched = 0, t = 0, starts = [], srcs = [];
  let paused = false, finished = false, endAt = 0, lineEls = [], shownImg = null, lastFetch = 0, active = -1;
  const bufs = new Map();
  const stopAudio = () => { srcs.forEach(s => { try { s.stop(); } catch (e) {} }); srcs = []; };
  window.__bookStop = () => { stopped = true; stopAudio(); };
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const pages = () => (book && book.pages) || [];
  const chars = () => (book && book.characters) || [];
  const colorOf = (who) => COLORS[Math.max(0, chars().findIndex(c => c.name === who)) % COLORS.length];

  const getBuf = async (n, i) => {
    const key = n + "_" + i;
    if (bufs.has(key)) return bufs.get(key);
    const r = await fetch(base + "p" + key + ".pcm", { cache: "no-store" });
    if (!r.ok) return null;
    const i16 = new Int16Array(await r.arrayBuffer());
    const f = new Float32Array(i16.length);
    for (let k = 0; k < i16.length; k++) f[k] = i16[k] / 32768;
    const b = ctx.createBuffer(1, Math.max(1, f.length), SR);
    if (f.length) b.copyToChannel(f, 0);
    bufs.set(key, b);
    return b;
  };

  const addLines = (p) => {
    for (let k = lineEls.length; k < p.lines.length; k++) {
      const ln = p.lines[k], d = document.createElement("div");
      d.style.cssText = "padding:4px 10px;border-radius:10px;transition:background .25s;";
      if (p.cover) { d.style.fontSize = "1.9rem"; d.style.fontWeight = "700"; d.style.textAlign = "center"; }
      if (ln.who !== NARR) {
        const name = document.createElement("span");
        name.textContent = ln.who + "  ";
        name.style.cssText = "font-weight:700;font-size:.95rem;color:" + colorOf(ln.who) + ";";
        d.appendChild(name);
      }
      // 글자 따라 읽기: 읽은 부분(said) 진하게, 남은 부분(rest) 연하게
      const q = ln.who !== NARR ? ["“", "”"] : ["", ""];
      const said = document.createElement("span"), rest = document.createElement("span");
      rest.textContent = q[0] + ln.text + q[1];
      d.appendChild(said); d.appendChild(rest);
      d.__text = q[0] + ln.text + q[1]; d.__said = said; d.__rest = rest; d.__n = -1;
      if (ln.emotion) d.title = "말투: " + ln.emotion;
      linesEl.appendChild(d); lineEls.push(d);
    }
  };

  const open = (n) => {
    const p = pages()[n]; if (!p) return;
    stopAudio(); cur = n; sched = 0; starts = []; t = ctx.currentTime + 0.15;
    finished = false; endAt = 0; active = -1;
    while (linesEl.firstChild) linesEl.removeChild(linesEl.firstChild);
    lineEls = [];
    if (paused) { paused = false; ctx.resume(); setPlay(); }
  };

  const setPlay = () => { bPlay.textContent = paused ? "▶ 계속 읽기" : "⏸ 멈춤"; };
  // 소리가 한 번 끊기면(생성이 재생보다 늦음 — 여러 권을 동시에 만들 때 등) 그 뒤로는
  // 조각을 몇 개 모아 둔 뒤 이어서 재생 → 문장 중간 잦은 끊김 대신 한 번의 짧은 쉼. 끊김이 없으면 지금처럼 바로 재생.
  let starved = false;
  const pump = async () => {
    const p = pages()[cur];
    if (!p) return;
    const idle = t <= ctx.currentTime + 0.05;            // 예약된 소리가 다 끝남
    if (starved && idle && !p.audio_done && p.chunks - sched < 3) return;   // 약 2초분 모일 때까지 대기
    while (!stopped && sched < p.chunks) {
      const b = await getBuf(cur, sched);
      if (!b) break;
      const s = ctx.createBufferSource(); s.buffer = b; s.connect(ctx.destination);
      if (sched > 0 && t < ctx.currentTime - 0.02) starved = true;   // 다음 조각이 늦게 와서 틈이 생김
      const at = Math.max(t, ctx.currentTime + 0.03);
      s.start(at); starts[sched] = at; t = at + b.duration; srcs.push(s); sched++;
    }
  };
  const highlight = (p) => {
    const now = ctx.currentTime;
    let idx = -1;
    for (let i = 0; i < starts.length; i++) if (starts[i] <= now) idx = i;
    let k = -1;
    p.lines.forEach((ln, j) => { if (ln.chunk !== null && ln.chunk !== undefined && ln.chunk <= idx) k = j; });
    if (k !== active) {
      if (lineEls[active]) { lineEls[active].style.background = "transparent"; paintWords(lineEls[active], 1); }
      if (lineEls[k]) { lineEls[k].style.background = "#ffe8c2"; lineEls[k].scrollIntoView({ block: "nearest", behavior: "smooth" }); }
      active = k;
    }
    // 지금 줄에서 몇 글자째를 읽는지: 이 줄 음성의 시작~끝(다음 줄 시작 또는 지금까지 예약된 끝 − 줄 사이 쉼) 비율
    const ln = p.lines[k], el = lineEls[k];
    if (!ln || !el) return;
    const t0 = starts[ln.chunk];
    const nx = p.lines.slice(k + 1).find(x => x.chunk !== null && x.chunk !== undefined && starts[x.chunk] !== undefined);
    const t1 = (nx ? starts[nx.chunk] : (p.audio_done && sched >= p.chunks ? t : null));
    if (t0 === undefined) return;
    const end = t1 !== null ? t1 - PAUSE : Math.max(now + 0.5, t - 0.1);
    paintWords(el, Math.max(0, Math.min(1, (now - t0) / Math.max(0.3, end - t0))));
  };
  const paintWords = (el, frac) => {
    const n = Math.round(el.__text.length * frac);
    if (n === el.__n) return;
    el.__n = n;
    el.__said.textContent = el.__text.slice(0, n);
    el.__rest.textContent = el.__text.slice(n);
    el.__said.style.cssText = "color:#3b2f2f;";
    el.__rest.style.cssText = frac >= 1 || n === 0 && el.style.background === "transparent" ? "color:#3b2f2f;" : "color:#a8957a;";
  };

  // 삽화: 지금 읽는 줄에 지정된 삽화(없으면 이 페이지 첫 삽화). 아직 안 그려졌으면 그 앞의 준비된 삽화를 유지.
  const showImage = (p) => {
    let src = null;
    const ill = book.illus;
    if (ill) {
      const ln = p.lines[active];
      let j = ln && ln.img !== null && ln.img !== undefined ? ln.img : p.img0;
      while (j !== null && j !== undefined && j >= 0 && !(ill[j] && ill[j].image === true)) {
        j = j > (p.img0 ?? 0) ? j - 1 : null;
      }
      if (j !== null && j !== undefined && j >= 0) src = "img_" + j + ".png";
    } else if (p.image === true) {
      src = "page_" + cur + ".png";                     // 예전 형식의 책
    }
    if (!src) { if (shownImg === null) { img.style.display = "none"; ph.style.display = "block"; } return; }
    if (src === shownImg) return;
    shownImg = src;
    const next = new Image();
    next.onload = () => {
      img.style.opacity = "0";
      setTimeout(() => { img.src = next.src; img.style.display = "block"; ph.style.display = "none"; img.style.opacity = "1"; }, img.style.display === "block" ? 300 : 0);
    };
    next.src = base + src;
  };

  // 장(챕터) 이동 버튼: 장이 생기는 대로 추가, 지금 장 강조
  const renderChapters = () => {
    const chs = (book && book.chapters) || [];
    for (let k = chapBtns.length; k !== chs.length; k++) {
      const ch = chs[k], b = document.createElement("button");
      b.textContent = ch.no + "장" + (ch.title ? " · " + ch.title : "");
      b.title = ch.title || "";
      b.style.cssText = "padding:3px 10px;border-radius:999px;border:1px solid #d9c6a5;background:#fff;color:#6b4f2f;cursor:pointer;font-size:.8rem;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;";
      b.onclick = () => { const p = pages()[ch.page]; if (p && p.chunks > 0) open(ch.page); };
      chapsEl.appendChild(b); chapBtns.push(b);
    }
    const now = (pages()[cur] || {}).chapter;
    chapBtns.forEach((b, k) => {
      const on = chs[k] && chs[k].no === now;
      b.style.background = on ? "#e07a5f" : "#fff"; b.style.color = on ? "#fff" : "#6b4f2f";
    });
  };
  const pageLabel = (p) => {
    if (cur === 0) return "표지";
    const rq = (book && book.request) || {};
    const total = rq.chapters && rq.pages_per ? rq.chapters * rq.pages_per : (book.story_done ? pages().length - 1 : "…");
    return (p.chapter && rq.chapters > 1 ? p.chapter + "장 · " : "") + cur + " / " + total + "쪽";
  };

  bPlay.onclick = () => {
    if (ctx.state !== "running" && !paused) { ctx.resume(); return; }
    if (finished) { open(0); return; }
    paused = !paused; setPlay();
    if (paused) ctx.suspend(); else ctx.resume();
  };
  bPrev.onclick = () => { if (cur > 0) open(cur - 1); };
  bNext.onclick = () => { const nx = pages()[cur + 1]; if (nx && nx.chunks > 0) open(cur + 1); };
  bAgain.onclick = () => { if (pages().length) open(0); };

  while (!stopped) {
    if (!document.getElementById(P)) { window.__bookStop(); break; }       // 화면에서 사라지면 정지
    const done = book && book.story_done && ["done", "partial", "error"].includes(book.status);
    if (performance.now() - lastFetch > (done ? 3000 : 350)) {
      lastFetch = performance.now();
      try { const r = await fetch(base + "book.json?t=" + Date.now(), { cache: "no-store" }); if (r.ok) book = await r.json(); } catch (e) {}
    }
    if (book) {
      if (cur === -1 && pages().length && pages()[0].chunks > 0) open(0);
      const p = pages()[cur];
      let msg = book.message || "";
      if (book.status === "error") msg = "❌ " + (book.error || "만들기 실패");
      if (p) {
        addLines(p);
        pageEl.textContent = pageLabel(p);
        renderChapters();
        if (!paused) await pump();
        highlight(p);
        showImage(p);
        const played = p.audio_done && sched >= p.chunks && ctx.currentTime >= t;
        if (!paused && played && !finished) {
          if (!endAt) endAt = performance.now();
          const nx = pages()[cur + 1];
          if (performance.now() - endAt > 900) {
            if (nx && nx.chunks > 0) open(cur + 1);
            else if (!nx && book.story_done) { finished = true; bPlay.textContent = "↺ 다시 듣기"; }
            else msg = book.status === "choice" ? "🤔 아래에서 골라 주세요! (버튼을 누르거나 🎤 말로 대답)" : "⏳ 다음 장을 쓰는 중이에요...";
          }
        } else if (!played) endAt = 0;
        if (finished) msg = "🎉 이야기 끝! 다시 들으려면 ↺ 를 누르세요.";
      }
      // 선택형 동화: 질문을 읽기 시작하면 선택 칸을 보여 줌 (그 전에는 숨김 → 아이가 미리 고르지 않게)
      const ch = book.choice, pane = document.querySelector(".st-key-choice_pane");
      if (pane) {
        const show = !!ch && ch.answer === null && cur === ch.page && active >= ch.line;
        if (pane.style.display !== (show ? "flex" : "none")) pane.style.display = show ? "flex" : "none";
      }
      if (ctx.state !== "running" && !paused) { msg = "🔇 소리가 막혀 있어요. ▶ 버튼을 눌러 주세요."; bPlay.textContent = "▶ 눌러서 소리 켜기"; }
      else if (!paused && !finished) setPlay();
      if (status.textContent !== msg) status.textContent = msg;
    }
    await sleep(120);
  }
})();
</script>
"""


def _check_script_safe(html: str):
    body = html.split("<script>", 1)[1].rsplit("</script>", 1)[0]
    if re.search(r"<[/\w!]", body):
        raise ValueError("player script contains tag-like text; Streamlit would strip it")


_check_script_safe(_HTML)


def book_player(book_id: str, scroll_into_view: bool = False):
    st.html(
        _HTML.replace("__ID_JS__", json.dumps(book_id)).replace("__BASE_JS__", json.dumps(BASE_URL))
        .replace("__SCROLL__", "true" if scroll_into_view else "false").replace("__PAUSE__", str(config.LINE_PAUSE))
        .replace("__BTN__", _BTN).replace("__ID__", book_id),
        unsafe_allow_javascript=True,
    )

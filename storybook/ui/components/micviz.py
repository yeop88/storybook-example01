"""녹음 파형 — 녹음하는 동안 실시간으로 그리고, 녹음이 끝나면 전체 파형을 그대로 남겨 둠.

- Streamlit 녹음기(st.audio_input)가 마이크를 열 때(getUserMedia) 그 스트림을 함께 받아 그림
  → 마이크를 두 번 열지 않음 (일부 PC·브라우저에서 두 번째 마이크 열기가 실패하는 문제 방지)
- 녹음이 끝나면 전체 녹음을 한 줄 파형으로 압축해 "✅ 녹음됨 · N초" 와 함께 표시
- 모두 브라우저 안에서만 그림 (서버 부담 없음)

주의: st.html 의 DOMPurify 때문에 스크립트 안에 '<글자' 같은 태그 모양 문자열을 쓰지 않는다.
"""

import re

import streamlit as st

_HTML = """
<div id="micviz-box" style="display:none;margin-top:-6px;"></div>
<script>
(() => {
  const HAS_REC = __HAS_REC__;
  if (window.__micViz) window.__micViz.dispose();
  const box = document.getElementById("micviz-box");
  const cv = document.createElement("canvas");
  cv.style.cssText = "width:100%;height:64px;display:block;border-radius:10px;background:#fff4e6;";
  const note = document.createElement("div");
  note.style.cssText = "font-size:.85rem;color:#b5651d;padding:4px 2px;font-weight:600;";
  box.appendChild(cv); box.appendChild(note);

  let ac = null, an = null, own = null, raf = 0, levels = [], t0 = 0, live = false, opening = false;

  const isRecording = () => !!document.querySelector('[data-testid="stAudioInput"] [aria-label="Stop recording"]');
  const levelNow = () => {
    const buf = new Float32Array(an.fftSize); an.getFloatTimeDomainData(buf);
    let s = 0; for (let i = 0; i !== buf.length; i++) s += buf[i] * buf[i];
    return Math.min(1, Math.pow(Math.sqrt(s / buf.length) * 8, 0.7));   // 작은 소리도 잘 보이게 확대
  };
  const paint = (vals, color) => {
    const W = cv.clientWidth || 300, H = cv.clientHeight || 64, dpr = window.devicePixelRatio || 1;
    if (cv.width !== Math.round(W * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
    const g = cv.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
    const step = 6, n = Math.floor(W / step);
    const v = vals.length > n ? vals.slice(vals.length - n) : vals;
    v.forEach((x, i) => {
      const h = Math.max(2, x * (H - 8));
      g.fillStyle = color(x);
      g.fillRect((n - v.length + i) * step, (H - h) / 2, 4, h);   // 오른쪽 끝이 지금 소리
    });
  };
  const liveColor = (x) => x > 0.85 ? "#e63946" : x > 0.12 ? "#e07a5f" : "#e9c9a8";

  // 녹음 전체를 화면 폭에 맞게 압축 (구간별 최댓값)
  const summary = (vals) => {
    const n = Math.max(1, Math.floor((cv.clientWidth || 300) / 6));
    if (vals.length === 0) return [];
    const out = [];
    for (let i = 0; i !== n; i++) {
      const a = Math.floor(i * vals.length / n), b = Math.max(a + 1, Math.floor((i + 1) * vals.length / n));
      out.push(Math.max(...vals.slice(a, b)));
    }
    return out;
  };
  const showFrozen = (rec) => {
    box.style.display = "block";
    const W = cv.clientWidth || 300, H = cv.clientHeight || 64, dpr = window.devicePixelRatio || 1;
    if (cv.width !== Math.round(W * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
    const g = cv.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
    summary(rec.levels).forEach((x, i) => {
      const h = Math.max(2, x * (H - 8));
      g.fillStyle = x > 0.12 ? "#3d8b6e" : "#b7d7c6";
      g.fillRect(i * 6, (H - h) / 2, 4, h);
    });
    const loud = rec.levels.filter(x => x > 0.12).length;
    note.style.color = loud ? "#2e7d5b" : "#c0392b";
    note.textContent = loud ? "✅ 녹음됨 · " + rec.secs.toFixed(1) + "초" : "⚠️ 소리가 거의 녹음되지 않았어요. 마이크를 확인하고 다시 녹음해 주세요.";
  };

  const draw = () => {
    if (!live) return;
    levels.push(levelNow());
    paint(levels, liveColor);
    const secs = (performance.now() - t0) / 1000;
    note.style.color = "#b5651d";
    note.textContent = "🔴 녹음 중 " + secs.toFixed(1) + "초 — " + (levels[levels.length - 1] > 0.12 ? "잘 들려요!" : "말해 보세요...") + "  다 말했으면 ⏹ 버튼";
    raf = requestAnimationFrame(draw);
  };
  const startWith = (stream) => {
    if (live) return;
    try {
      ac = new (window.AudioContext || window.webkitAudioContext)();
      ac.resume().catch(() => {});
      an = ac.createAnalyser(); an.fftSize = 1024;
      ac.createMediaStreamSource(stream).connect(an);
    } catch (e) { return; }
    levels = []; t0 = performance.now(); live = true; box.style.display = "block"; draw();
  };
  const finish = () => {
    if (!live) return;
    live = false; cancelAnimationFrame(raf);
    const rec = { levels: levels.slice(), secs: (performance.now() - t0) / 1000 };
    window.__micVizLast = rec;
    if (own) own.getTracks().forEach(t => t.stop());
    if (ac) ac.close().catch(() => {});
    ac = null; an = null; own = null;
    showFrozen(rec);
  };

  // 1) 녹음기가 마이크를 열 때 그 스트림을 받음 (한 번만 패치)
  if (!window.__gumPatched && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    window.__gumPatched = true;
    const orig = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia = async (c) => {
      const s = await orig(c);
      try { if (c && c.audio && window.__onMicStream) window.__onMicStream(s); } catch (e) {}
      return s;
    };
  }
  let pendingStream = null;
  window.__onMicStream = (s) => { pendingStream = s; };

  // 2) 녹음 상태 감시: 시작되면 받은 스트림(없으면 직접 열어서)으로 그리고, 끝나면 파형을 고정
  const timer = setInterval(async () => {
    if (!document.body.contains(box)) { clearInterval(timer); if (live) finish(); return; }
    const rec = isRecording();
    if (rec && !live && !opening) {
      if (pendingStream && pendingStream.active) { startWith(pendingStream); }
      else {
        opening = true;
        try { own = await navigator.mediaDevices.getUserMedia({ audio: true }); startWith(own); } catch (e) {}
        opening = false;
      }
    }
    if (!rec && live) finish();
  }, 100);

  // 화면이 다시 그려져도(Streamlit rerun) 마지막 녹음 파형 유지. 녹음을 지우면 같이 숨김.
  if (HAS_REC && window.__micVizLast) showFrozen(window.__micVizLast);
  if (!HAS_REC) window.__micVizLast = null;

  window.__micViz = { dispose: () => { clearInterval(timer); if (live) finish(); } };
})();
</script>
"""

if re.search(r"<[/\w!]", _HTML.split("<script>", 1)[1].rsplit("</script>", 1)[0]):
    raise ValueError("micviz script contains tag-like text; Streamlit would strip it")


def mic_visualizer(has_recording: bool):
    st.html(_HTML.replace("__HAS_REC__", "true" if has_recording else "false"), unsafe_allow_javascript=True)

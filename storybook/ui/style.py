"""화면 공통 스타일 (반응형).

- 칸(st.columns)은 화면 너비가 아니라 **실제 칸 너비** 기준으로 접힘: 칸이 --col-min 보다 좁아지면 아래 줄로 내려감.
  → 사이드바를 열었든 닫았든, 노트북·태블릿·휴대폰 어디서든 입력칸이 찌그러지지 않음.
- 한글은 단어 중간에서 줄을 바꾸지 않음 (keep-all).
- 아이콘 글꼴(Material Symbols)이 늦게 오면 아이콘 이름("arrow_down")이 글자로 보이며 옆 글자와 겹침 → 한 글자 폭으로 자름.
"""

import streamlit as st

_CSS = """
<style>
/* --- 글자 --- */
body, button, input, textarea { word-break: keep-all; overflow-wrap: break-word; }

/* --- 아이콘 글꼴이 오기 전 아이콘 이름이 글자로 새어 나오지 않게: 한 글자 폭 + 글꼴이 올 때까지 투명 --- */
[data-testid="stIconMaterial"] {
  display: inline-block; width: 1em; min-width: 1em; max-width: 1em;
  overflow: hidden; white-space: nowrap; text-overflow: clip;
}
html:not(.icons-ready) [data-testid="stIconMaterial"] { color: transparent !important; }

/* --- 칸 나누기: 좁아지면 아래로 (--col-min 은 줄마다 다시 정해 안쪽 칸이 바깥 값을 물려받지 않게) --- */
[data-testid="stHorizontalBlock"] { flex-wrap: wrap; row-gap: 0.75rem; --col-min: 180px; }
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
  flex-grow: 1; min-width: min(100%, var(--col-min, 180px));
}
/* 동화 만들기: 왼쪽 옵션 | 오른쪽 재생기 */
[data-testid="stHorizontalBlock"]:has(.st-key-player_pane) { --col-min: 340px; row-gap: 1.5rem; }
/* 책장 카드 · 통계 지표 · 선택 버튼 */
.st-key-shelf_grid [data-testid="stHorizontalBlock"] { --col-min: 220px; }
.st-key-shelf_grid [data-testid="stHorizontalBlock"] [data-testid="stHorizontalBlock"] { --col-min: 90px; }
.st-key-stats_now [data-testid="stHorizontalBlock"],
.st-key-stats_quality [data-testid="stHorizontalBlock"] { --col-min: 150px; }
.st-key-choice_pane [data-testid="stHorizontalBlock"] { --col-min: 160px; }
.st-key-shelf_top [data-testid="stHorizontalBlock"] { --col-min: 110px; align-items: center; }

/* 재생기: 옆 칸이 있을 때만 화면에 고정(sticky). 아래로 접혔을 때는 그냥 흐름대로 */
@media (min-width: 768px) {
  /* 고정된 재생기가 창보다 길면 그림(위쪽)이 잘리므로 창 높이에 맞추고, 넘치면 재생기 안에서 스크롤 */
  .st-key-player_pane { position: sticky; top: 3.75rem; z-index: 2; max-height: calc(100vh - 4.5rem); overflow-y: auto; }
  div[data-testid="stColumn"]:has(.st-key-player_pane) { align-self: stretch; }
}

/* 예시 주제 칩: 긴 문장도 칩 안에서 줄바꿈 */
.st-key-examples [data-testid="stButtonGroup"] button { white-space: normal; text-align: left; height: auto; }

/* --- 여백 --- */
.block-container { padding-top: 2.5rem; }
@media (max-width: 640px) {
  .block-container { padding-left: 1rem; padding-right: 1rem; padding-top: 3rem; }
  h1 { font-size: 1.6rem; } h4 { font-size: 1.15rem; }
}
.st-key-choice_pane { display: none; }  /* 선택형 질문을 읽기 시작하면 재생기가 보여 줌 */
.st-key-icon_js { display: none; }      /* 아이콘 확인 스크립트 자리 (빈 줄 간격 없애기) */
</style>
"""


# 아이콘 글꼴(Material Symbols)이 실제로 올라오면 <html> 에 icons-ready 를 붙여 아이콘을 보이게 함
_ICON_JS = """
<script>
(() => {
  const root = window.parent && window.parent.document ? window.parent.document : document;
  const html = root.documentElement;
  if (html.classList.contains("icons-ready")) return;
  const icons = () => [...root.fonts].filter((f) => f.family.replace(/["']/g, "").startsWith("Material Symbols"));
  let n = 0;
  const tick = () => {
    const faces = icons();
    if (faces.some((f) => f.status === "loaded")) { html.classList.add("icons-ready"); return; }
    faces.forEach((f) => f.status === "unloaded" && f.load().catch(() => {}));
    if (++n < 300) setTimeout(tick, 100);  // 30초까지 기다림 (글꼴이 끝내 안 오면 이름 글자 대신 빈 자리)
  };
  tick();
})();
</script>
"""


def apply():
    st.markdown(_CSS, unsafe_allow_html=True)
    with st.container(key="icon_js"):
        st.html(_ICON_JS, unsafe_allow_javascript=True)

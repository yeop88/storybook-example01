"""화면 공통 스타일."""

import streamlit as st

_CSS = """
<style>
/* 넓은 화면에서는 오른쪽 재생기를 화면에 고정(sticky), 좁은 화면에서는 자연스럽게 아래로 */
@media (min-width: 768px) {
  .st-key-player_pane { position: sticky; top: 3.75rem; z-index: 2; }
  div[data-testid="stColumn"]:has(.st-key-player_pane) { align-self: stretch; }
}
.block-container { padding-top: 2.5rem; }
.st-key-choice_pane { display: none; }  /* 선택형 질문을 읽기 시작하면 재생기가 보여 줌 */
</style>
"""


def apply():
    st.markdown(_CSS, unsafe_allow_html=True)

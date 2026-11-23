"""선택형 동화의 선택 칸: 장 끝 질문이 오면 ①② 버튼 + 🎤 말로 고르기.

1초마다 book.json 을 확인 (재생기는 그대로 둔 채 이 칸만 다시 그림).
질문을 읽어 주기 전에는 재생기 스크립트가 이 칸을 숨겨 둠 (.st-key-choice_pane).
"""

import hashlib

import streamlit as st

from storybook.application.book_maker import answer_choice
from storybook.domain.choices import match_choice
from storybook.infra import book_store, stt


@st.fragment(run_every=1.0)
def choice_panel(book_id: str):
    b = book_store.read_book(book_id)
    ch = (b or {}).get("choice")
    if not ch or ch.get("answer") is not None:
        return
    with st.container(key="choice_pane", border=True):
        st.markdown(f"#### 🤔 {ch['question']}")
        cols = st.columns(len(ch["options"]))
        for i, o in enumerate(ch["options"]):
            if cols[i].button(f"{'①②③'[i]} {o}", key=f"opt_{book_id}_{ch['no']}_{i}", type="primary",
                              width="stretch"):
                answer_choice(book_id, i, "(버튼)")
                st.rerun(scope="fragment")
        rec = st.audio_input("🎤 말로 고르기", key=f"choice_rec_{book_id}_{ch['no']}")
        if rec is None:
            return
        data = rec.getvalue()
        h = hashlib.sha1(data).hexdigest()
        if st.session_state.get("choice_rec_hash") != h:
            st.session_state.choice_rec_hash = h
            lang = "english" if (b.get("request") or {}).get("language") == "English" else "korean"
            with st.spinner("받아쓰는 중..."):
                heard = stt.transcribe(data, lang)
            i = match_choice(heard, ch["options"])
            st.session_state.choice_heard = (heard, i)
            if i is not None:
                answer_choice(book_id, i, heard)
                st.rerun(scope="fragment")
        heard, i = st.session_state.get("choice_heard", ("", None))
        if heard and i is None:
            st.warning(f"📝 '{heard}' — 잘 못 알아들었어요. 다시 말하거나 버튼을 눌러 주세요.")

"""✨ 동화 만들기 화면: 왼쪽은 주제·옵션, 오른쪽은 책 재생기."""

import hashlib

import streamlit as st

from storybook import config
from storybook.application import scheduler
from storybook.application.book_maker import BookMaker
from storybook.infra import stt
from storybook.ui.components.choice_panel import choice_panel
from storybook.ui.components.micviz import mic_visualizer
from storybook.ui.components.player import book_player

EXAMPLES = [
    "바다에 사는 꼬마 문어가 친구를 사귀는 이야기",
    "구름을 타고 하늘 여행을 떠난 아기 고양이",
    "양치하기 싫어하는 꼬마 공룡",
    "숲속 동물들이 함께 겨울을 준비하는 이야기",
    "밤하늘의 별을 따러 간 소녀",
]


def render(ctx: dict):
    left, right = st.columns([1, 1], gap="large")
    with left:
        req = _form()
        _submit(req, ctx)
    with right.container(key="player_pane"):  # 스크롤해도 재생기가 따라오도록 (CSS sticky)
        if bid := st.session_state.get("open_book"):
            book_player(bid, scroll_into_view=True)
            choice_panel(bid)
            st.caption("AI가 이야기를 쓰는 동시에 실시간으로 읽어 줘요. 줄 위에 마우스를 올리면 AI가 정한 말투·감정이 보여요.")
        else:
            st.markdown("#### 📖 여기에 동화책이 펼쳐져요")
            st.info("왼쪽에서 주제를 말하거나 입력하고 **✨ 동화 만들기**를 누르세요.\n\n"
                    "AI가 이야기를 쓰고, 그림을 그리고, 목소리로 읽어 줘요. 페이지는 자동으로 넘어가요.")


def _record_theme():
    """🎤 말로 주제 말하기 → 받아써서 주제 칸에 넣음."""
    rec = st.audio_input("🎤 말로 주제 말하기", key="rec",
                         help="🎙 버튼을 누르고 말한 뒤 ⏹ 버튼을 누르면 받아써서 주제 칸에 넣어요.")
    mic_visualizer(rec is not None)
    if rec is None:
        return
    data = rec.getvalue()
    h = hashlib.sha1(data).hexdigest()
    if st.session_state.get("rec_hash") != h:
        st.session_state.rec_hash = h
        lang = "english" if st.session_state.get("language") == "English" else "korean"
        with st.spinner("받아쓰는 중..."):
            try:
                heard = stt.transcribe(data, lang)
            except Exception as e:  # noqa: BLE001
                heard = ""
                st.error(f"받아쓰기 실패: {e}")
        st.session_state.heard = heard
        if heard:
            st.session_state.theme = heard
    if st.session_state.get("heard"):
        st.success(f"📝 **녹음된 말:** {st.session_state.heard}")
    else:
        st.warning("목소리가 들리지 않았어요. 마이크를 가까이 하고 조금 더 크게 다시 말해 주세요.")


def _form() -> dict:
    st.markdown("##### 1. 어떤 이야기를 들려줄까요?")
    _record_theme()
    with st.expander("💡 예시 주제", expanded=False):
        for ex in EXAMPLES:
            st.button(ex, key=f"ex_{ex}", width="stretch",
                      on_click=lambda e=ex: st.session_state.update(theme=e))
    theme = st.text_area("이야기 주제 (말하거나 직접 입력)", key="theme", height=90,
                         placeholder="예: 바다에 사는 꼬마 문어가 친구를 사귀는 이야기")

    st.markdown("##### 2. 꾸미기")
    c1, c2 = st.columns(2)
    hero = c1.text_input("주인공 이름 (선택)", placeholder="예: 도담이")
    lesson = c2.text_input("담고 싶은 교훈 (선택)", placeholder="예: 나눔의 기쁨")
    age = st.segmented_control("듣는 아이 나이", list(config.AGES), default="6~8세", key="age") or "6~8세"
    language = st.segmented_control("언어", list(config.LANGUAGES), default="Korean",
                                    format_func=config.LANGUAGES.get, key="language") or "Korean"

    st.markdown("##### 3. 구성")
    chapters = st.segmented_control("장(챕터) 수", config.CHAPTER_COUNTS, default=1,
                                    format_func=lambda n: f"{n}장", key="chapters") or 1
    per = st.segmented_control("쪽수 (장마다)", config.PAGES_PER_CHAPTER, default=4,
                               format_func=lambda n: f"{n}쪽", key="pages_per") or 4
    total = chapters * per
    st.caption(f"📄 표지 + 전체 **{total}쪽**" + (f" ({chapters}장 × {per}쪽)" if chapters > 1 else "")
               + f" · 듣는 시간 약 {max(1, round(total * 27 / 60))}분 — 쪽수는 정확히 지켜요")
    outline = []
    if chapters > 1:
        with st.expander("📝 장별 제목·줄거리 직접 정하기 (선택 — 비우면 AI가 정해요)"):
            for i in range(chapters):
                a, b = st.columns([2, 3])
                t = a.text_input(f"{i + 1}장 제목", key=f"ch_title_{i}", placeholder="예: 외톨이 문어")
                pl = b.text_input(f"{i + 1}장 줄거리", key=f"ch_plot_{i}", placeholder="예: 친구가 없어 혼자 노는 문어")
                outline.append({"title": t.strip(), "plot": pl.strip()})
    interactive = st.toggle("🔀 선택형 동화 (장마다 아이가 다음 이야기 고르기)", key="interactive",
                            disabled=chapters == 1,
                            help="장이 2개 이상일 때 쓸 수 있어요. 고른 선택대로 AI가 다음 장을 바로 이어 써요.")

    st.markdown("##### 4. 그림과 목소리")
    style = st.selectbox("그림체", list(config.STYLES))
    c1, c2 = st.columns(2)
    narrator = c1.selectbox("해설 목소리", list(config.NARRATORS))
    voice = c2.selectbox("해설 느낌", list(config.VOICES))
    cast = st.radio("등장인물 대사", list(config.CHARACTER_VOICE_MODES), format_func=config.CHARACTER_VOICE_MODES.get,
                    help="AI가 줄마다 말투·감정(예: 깜짝 놀라 숨을 들이켜며 높고 빠르게)을 정해 연기합니다.")
    return {"theme": theme.strip(), "hero": hero.strip(), "lesson": lesson.strip(), "age": age,
            "chapters": chapters, "pages_per": per, "outline": outline, "style": style, "narrator": narrator,
            "voice": voice, "language": language, "cast": cast, "interactive": bool(interactive and chapters > 1)}


def _submit(req: dict, ctx: dict):
    qs = scheduler.status()
    if len(qs["making"]) >= qs["limit"]:
        st.caption(f"⏳ 지금 {len(qs['making'])}권을 만드는 중이에요 (기다리는 책 {len(qs['waiting'])}권). "
                   "누르면 차례대로 바로 이어서 만들어요.")
    elif qs["making"]:
        st.caption(f"📚 지금 다른 책 {len(qs['making'])}권도 함께 만드는 중이에요. 바로 시작할 수 있어요.")
    if st.button("✨ 동화 만들기", type="primary", width="stretch",
                 disabled=not (req["theme"] and ctx["ready"])):
        st.session_state.open_book = BookMaker({**req, "llm": ctx["llm"]}).start()
    if not ctx["ready"]:
        st.info(f"⏳ 목소리 모델을 준비하고 있어요 ({ctx['tts_status']}). 서버를 켠 뒤 처음 한 번 약 2분 걸려요.")

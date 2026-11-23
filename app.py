"""AI 동화 낭독기 (Streamlit, HTTPS — 브라우저 마이크 사용).

- 🎤 말로 이야기 주제 말하기 → STT(Whisper)
- ✍️ 내부 LLM 이 그림 동화를 씀 (think 끔)
- 🎨 SDXL-Lightning 이 페이지마다 그림을 그림
- 🔊 TTS(tts_app_streaming 의 모델 공유)가 낭독 → 브라우저에서 페이지를 넘기며 읽어 줌
- 📚 만든 책은 책장에 저장
"""

import hashlib

import config  # noqa: F401  (.env 를 가장 먼저 로드)

import streamlit as st

st.set_page_config(page_title="AI 동화 낭독기", page_icon="📖", layout="wide")

import book  # noqa: E402
import gpu  # noqa: E402
import tts_client  # noqa: E402
from micviz import mic_visualizer  # noqa: E402
from player import book_player  # noqa: E402

gpu.preload()  # STT·그림 모델을 백그라운드로 미리 올림 (서버가 꺼질 때까지 유지)
book.prewarm_greetings()  # 누르자마자 읽을 인사말을 미리 만들어 둠 (낮은 우선순위)

# 화면 보정: 넓은 화면에서는 오른쪽 재생기를 화면에 고정(sticky), 좁은 화면에서는 자연스럽게 아래로
st.markdown("""
<style>
@media (min-width: 768px) {
  .st-key-player_pane { position: sticky; top: 3.75rem; z-index: 2; }
  div[data-testid="stColumn"]:has(.st-key-player_pane) { align-self: stretch; }
}
.block-container { padding-top: 2.5rem; }
.st-key-choice_pane { display: none; }  /* 질문을 읽기 시작하면 재생기가 보여 줌 */
</style>
""", unsafe_allow_html=True)

EXAMPLES = [
    "바다에 사는 꼬마 문어가 친구를 사귀는 이야기",
    "구름을 타고 하늘 여행을 떠난 아기 고양이",
    "양치하기 싫어하는 꼬마 공룡",
    "숲속 동물들이 함께 겨울을 준비하는 이야기",
    "밤하늘의 별을 따러 간 소녀",
]

# ---------------------------------------------------------------------------
# 사이드바: 상태
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("📖 AI 동화 낭독기")
    st.caption("말로 주제를 들려주면 AI가 그림 동화를 만들어 읽어 줘요.")
    st.markdown("#### 준비 상태")
    tts = tts_client.health()
    s = gpu.status()
    st.write(("✅" if tts.get("ready") else "⏳") + f" 목소리(TTS): {tts.get('status')}")
    st.write(("✅" if s["stt"] == "준비 완료" else "⏳") + f" 받아쓰기(STT): {s['stt']}")
    st.write(("✅" if s["paint"].startswith("준비 완료") else "⏳") + f" 그림: {s['paint']}")
    if st.button("🔄 상태 새로고침", use_container_width=True):
        st.rerun()
    st.divider()
    providers = list(config.LLM_PROVIDERS)
    llm = st.selectbox("이야기 AI 서버", providers,
                       index=providers.index(config.LLM_DEFAULT) if config.LLM_DEFAULT in providers else 0)
    with st.expander("🔒 보안 연결(인증서) 설치"):
        st.caption("마이크는 HTTPS 에서만 동작해요. 아래 파일을 PC마다 **한 번** 실행하면 "
                   "'안전하지 않음' 경고 없이 접속돼요. (관리자 권한 불필요, 무료 사내 인증서)")
        bat, crt = config.CERT_DIR / "install_cert.bat", config.CERT_DIR / "ca.crt"
        if bat.exists():
            st.download_button("🪟 Windows 설치 파일", bat.read_bytes(), "install_cert.bat",
                               mime="application/octet-stream", use_container_width=True)
            st.caption("① 내려받은 파일 실행 → ② 보안 경고에서 '예' → ③ 브라우저를 모두 닫고 다시 접속")
        if crt.exists():
            st.download_button("📱 인증서 파일 (Mac·휴대폰용)", crt.read_bytes(), "ai_story_lan_ca.crt",
                               mime="application/x-x509-ca-cert", use_container_width=True)
            st.caption("Android: 설정 → 보안 → 인증서 설치 → CA 인증서 / iPhone: 프로필 설치 후 "
                       "설정 → 일반 → 정보 → 인증서 신뢰 설정에서 켜기")

@st.fragment(run_every=1.0)
def choice_panel(bid: str):
    """선택형 동화: 장 끝 질문이 오면 선택 버튼 + 말로 고르기를 보여 줌 (1초마다 확인, 재생기는 그대로).
    질문을 읽어 주기 전에는 재생기 스크립트가 이 칸을 숨겨 둠 (.st-key-choice_pane)."""
    b = book.read_book(bid)
    ch = (b or {}).get("choice")
    if not ch or ch.get("answer") is not None:
        return
    with st.container(key="choice_pane", border=True):
        st.markdown(f"#### 🤔 {ch['question']}")
        cols = st.columns(len(ch["options"]))
        for i, o in enumerate(ch["options"]):
            if cols[i].button(f"{'①②③'[i]} {o}", key=f"opt_{bid}_{ch['no']}_{i}", type="primary",
                              use_container_width=True):
                book.answer_choice(bid, i, "(버튼)")
                st.rerun(scope="fragment")
        rec = st.audio_input("🎤 말로 고르기", key=f"choice_rec_{bid}_{ch['no']}")
        if rec is not None:
            data = rec.getvalue()
            h = hashlib.sha1(data).hexdigest()
            if st.session_state.get("choice_rec_hash") != h:
                st.session_state.choice_rec_hash = h
                lang = "english" if (b.get("request") or {}).get("language") == "English" else "korean"
                with st.spinner("받아쓰는 중..."):
                    heard = gpu.transcribe(data, lang)
                i = book.match_choice(heard, ch["options"])
                st.session_state.choice_heard = (heard, i)
                if i is not None:
                    book.answer_choice(bid, i, heard)
                    st.rerun(scope="fragment")
            heard, i = st.session_state.get("choice_heard", ("", None))
            if heard and i is None:
                st.warning(f"📝 '{heard}' — 잘 못 알아들었어요. 다시 말하거나 버튼을 눌러 주세요.")


view = st.radio("화면", ["✨ 동화 만들기", "📚 책장", "📊 통계"], horizontal=True, label_visibility="collapsed",
                key="view")

# ---------------------------------------------------------------------------
# ✨ 동화 만들기
# ---------------------------------------------------------------------------
if view == "✨ 동화 만들기":
    left, right = st.columns([1, 1], gap="large")
    with left:
        st.markdown("##### 1. 어떤 이야기를 들려줄까요?")
        rec = st.audio_input("🎤 말로 주제 말하기", key="rec",
                             help="🎙 버튼을 누르고 말한 뒤 ⏹ 버튼을 누르면 받아써서 주제 칸에 넣어요.")
        mic_visualizer(rec is not None)
        if rec is not None:
            data = rec.getvalue()
            h = hashlib.sha1(data).hexdigest()
            if st.session_state.get("rec_hash") != h:
                st.session_state.rec_hash = h
                lang = "english" if st.session_state.get("language") == "English" else "korean"
                with st.spinner("받아쓰는 중..."):
                    try:
                        heard = gpu.transcribe(data, lang)
                    except Exception as e:  # noqa: BLE001
                        heard = ""
                        st.error(f"받아쓰기 실패: {e}")
                st.session_state.heard = heard
                if heard:
                    st.session_state.theme = heard
        if rec is not None:
            if st.session_state.get("heard"):
                st.success(f"📝 **녹음된 말:** {st.session_state.heard}")
            else:
                st.warning("목소리가 들리지 않았어요. 마이크를 가까이 하고 조금 더 크게 다시 말해 주세요.")

        with st.expander("💡 예시 주제", expanded=False):
            for ex in EXAMPLES:
                st.button(ex, key=f"ex_{ex}", use_container_width=True,
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
        interactive = st.toggle("🔀 선택형 동화 (장마다 아이가 다음 이야기 고르기)",
                                key="interactive", disabled=chapters == 1,
                                help="장이 2개 이상일 때 쓸 수 있어요. 고른 선택대로 AI가 다음 장을 바로 이어 써요.")

        st.markdown("##### 4. 그림과 목소리")
        style = st.selectbox("그림체", list(config.STYLES))
        c1, c2 = st.columns(2)
        narrator = c1.selectbox("해설 목소리", list(config.NARRATORS))
        voice = c2.selectbox("해설 느낌", list(config.VOICES))
        cast = st.radio("등장인물 대사", list(config.CHARACTER_VOICE_MODES),
                        format_func=config.CHARACTER_VOICE_MODES.get,
                        help="AI가 줄마다 말투·감정(예: 깜짝 놀라 숨을 들이켜며 높고 빠르게)을 정해 연기합니다.")

        ready = bool(tts.get("ready")) and bool(config.LLM_PROVIDERS)
        qs = book.queue_status()
        if len(qs["making"]) >= qs["limit"]:
            st.caption(f"⏳ 지금 {len(qs['making'])}권을 만드는 중이에요 (기다리는 책 {len(qs['waiting'])}권). "
                       "누르면 차례대로 바로 이어서 만들어요.")
        elif qs["making"]:
            st.caption(f"📚 지금 다른 책 {len(qs['making'])}권도 함께 만드는 중이에요. 바로 시작할 수 있어요.")
        if st.button("✨ 동화 만들기", type="primary", use_container_width=True, disabled=not (theme.strip() and ready)):
            maker = book.BookMaker({
                "llm": llm, "theme": theme.strip(), "hero": hero.strip(), "lesson": lesson.strip(), "age": age,
                "chapters": chapters, "pages_per": per, "outline": outline, "style": style,
                "narrator": narrator, "voice": voice, "language": language, "cast": cast,
                "interactive": bool(interactive and chapters > 1),
            })
            st.session_state.open_book = maker.start()
        if not tts.get("ready"):
            st.warning("목소리(TTS) 서버가 준비되지 않았어요. tts_app_streaming 이 켜져 있는지 확인하세요.")

    with right.container(key="player_pane"):  # 스크롤해도 재생기가 따라오도록 (CSS sticky)
        if bid := st.session_state.get("open_book"):
            book_player(bid, scroll_into_view=True)
            choice_panel(bid)
            st.caption("AI가 이야기를 쓰는 동시에 실시간으로 읽어 줘요. 줄 위에 마우스를 올리면 AI가 정한 말투·감정이 보여요.")
        else:
            st.markdown("#### 📖 여기에 동화책이 펼쳐져요")
            st.info("왼쪽에서 주제를 말하거나 입력하고 **✨ 동화 만들기**를 누르세요.\n\n"
                    "AI가 이야기를 쓰고, 그림을 그리고, 목소리로 읽어 줘요. 페이지는 자동으로 넘어가요.")

# ---------------------------------------------------------------------------
# 📊 통계 (관리자용)
# ---------------------------------------------------------------------------
elif view == "📊 통계":
    import stats

    stats.render()

# ---------------------------------------------------------------------------
# 📚 책장
# ---------------------------------------------------------------------------
else:
    if bid := st.session_state.get("shelf_book"):
        b = book.read_book(bid)
        if b:
            top = st.columns([6, 1])
            top[0].markdown(f"### {b.get('title') or '만드는 중인 책'}")
            if top[1].button("✖ 닫기", use_container_width=True):
                st.session_state.shelf_book = None
                st.rerun()
            book_player(bid)
            st.divider()

    books = book.list_books()
    n_books, used = book.books_usage()
    keep = f" · {config.BOOK_KEEP_DAYS}일 지난 책은 자동 정리" if config.BOOK_KEEP_DAYS > 0 else ""
    st.caption(f"📚 책 {n_books}권 · 사용 용량 {used / 1e6:,.0f}MB{keep}")
    if not books:
        st.info("아직 만든 책이 없어요. ✨ 동화 만들기에서 첫 책을 만들어 보세요.")
    cols = st.columns(4)
    for i, b in enumerate(books):
        with cols[i % 4]:
            with st.container(border=True):
                d = book.book_dir(b["id"])
                cover = d / "img_0.png" if (d / "img_0.png").exists() else d / "page_0.png"
                if cover.exists():
                    st.image(str(cover), use_container_width=True)
                st.markdown(f"**{b.get('title') or '(제목 없음)'}**")
                state = {"done": "✅", "partial": "⚠️", "error": "❌"}.get(b.get("status"), "⏳")
                n = max(0, len(b.get("pages", [])) - 1)
                ch = len(b.get("chapters", []))
                st.caption(f"{state} {b.get('created', '')} · " + (f"{ch}장 " if ch else "") + f"{n}쪽 · "
                           f"{b.get('request', {}).get('style', '')}")
                c1, c2 = st.columns(2)
                if c1.button("📖 읽기", key=f"read_{b['id']}", use_container_width=True):
                    st.session_state.shelf_book = b["id"]
                    st.rerun()
                if c2.button("🗑️ 삭제", key=f"del_{b['id']}", use_container_width=True):
                    book.delete_book(b["id"])
                    if st.session_state.get("shelf_book") == b["id"]:
                        st.session_state.shelf_book = None
                    st.rerun()

"""📚 책장: 만든 책 다시 읽기 / 삭제, 책 수·용량 표시."""

import streamlit as st

from storybook import config
from storybook.infra import book_store
from storybook.ui.components.player import book_player

_STATE = {"done": "✅", "partial": "⚠️", "error": "❌"}


def render():
    if bid := st.session_state.get("shelf_book"):
        b = book_store.read_book(bid)
        if b:
            top = st.columns([6, 1])
            top[0].markdown(f"### {b.get('title') or '만드는 중인 책'}")
            if top[1].button("✖ 닫기", width="stretch"):
                st.session_state.shelf_book = None
                st.rerun()
            book_player(bid)
            st.divider()

    books = book_store.list_books()
    n_books, used = book_store.usage()
    keep = f" · {config.BOOK_KEEP_DAYS}일 지난 책은 자동 정리" if config.BOOK_KEEP_DAYS > 0 else ""
    st.caption(f"📚 책 {n_books}권 · 사용 용량 {used / 1e6:,.0f}MB{keep}")
    if not books:
        st.info("아직 만든 책이 없어요. ✨ 동화 만들기에서 첫 책을 만들어 보세요.")
    cols = st.columns(4)
    for i, b in enumerate(books):
        with cols[i % 4], st.container(border=True):
            _card(b)


def _card(b: dict):
    if cover := book_store.cover_path(b["id"]):
        st.image(str(cover), width="stretch")
    st.markdown(f"**{b.get('title') or '(제목 없음)'}**")
    n = max(0, len(b.get("pages", [])) - 1)
    ch = len(b.get("chapters", []))
    st.caption(f"{_STATE.get(b.get('status'), '⏳')} {b.get('created', '')} · " + (f"{ch}장 " if ch else "")
               + f"{n}쪽 · {b.get('request', {}).get('style', '')}")
    c1, c2 = st.columns(2)
    if c1.button("📖 읽기", key=f"read_{b['id']}", width="stretch"):
        st.session_state.shelf_book = b["id"]
        st.rerun()
    if c2.button("🗑️ 삭제", key=f"del_{b['id']}", width="stretch"):
        book_store.delete_book(b["id"])
        if st.session_state.get("shelf_book") == b["id"]:
            st.session_state.shelf_book = None
        st.rerun()

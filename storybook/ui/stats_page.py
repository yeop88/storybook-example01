"""📊 통계 화면 (관리자용): 책마다 기록된 시간·오류를 모아 서비스 상태를 봄."""

import math
from statistics import mean, median

import pandas as pd
import streamlit as st

from storybook import config
from storybook.application import scheduler, startup
from storybook.infra import book_store


def _nums(xs):
    """None·NaN(예전 책에는 없는 값)을 뺀 숫자만."""
    return [x for x in xs if isinstance(x, (int, float)) and not math.isnan(x)]


def _avg(xs):
    xs = _nums(xs)
    return round(mean(xs), 2) if xs else None


def _row(b: dict) -> dict:
    r = b.get("request") or {}
    pages = b.get("pages") or []
    ill = [i.get("seconds") for i in b.get("illus", []) if isinstance(i.get("seconds"), (int, float))]
    return {
        "만든 시각": b.get("created", ""),
        "제목": b.get("title") or "(제목 없음)",
        "상태": {"done": "✅ 완료", "partial": "⚠️ 일부", "error": "❌ 실패", "choice": "🤔 선택 대기"}.get(
            b.get("status"), "⏳ 만드는 중"),
        "구성": f"{r.get('chapters', 1)}장×{r.get('pages_per', r.get('pages', '?'))}쪽" + (" 🔀" if r.get("interactive") else ""),
        "대기(초)": b.get("queue_seconds"),
        "첫 소리(초)": b.get("first_audio_seconds"),
        "이야기 쓰기(초)": b.get("story_seconds"),
        "전체 제작(초)": b.get("total_seconds"),
        "음성 길이(초)": round(sum(p.get("duration", 0) for p in pages), 1),
        "삽화 수": len(ill),
        "삽화 평균(초)": round(mean(ill), 2) if ill else None,
        "선택 수": len(b.get("choices", [])),
        "한자 수정": len(b.get("fixed", [])),
        "서버 전환": len(b.get("notes", [])),
        "해설": r.get("narrator", ""),
        "오류": (b.get("error") or "")[:80],
    }


def render():
    st.subheader("📊 서비스 통계")
    books = book_store.list_books()
    rows = [_row(b) for b in books]

    # 지금 상태
    qs = scheduler.status()
    n_books, used = book_store.usage()
    s = startup.status()
    c = st.columns(4)
    c[0].metric(f"지금 만드는 책 (대기 {len(qs['waiting'])}권)", f"{len(qs['making'])} / {qs['limit']}권")
    c[1].metric(f"저장된 책 ({used / 1e6:,.0f}MB)", f"{n_books}권")
    c[2].metric("목소리(TTS)", "준비" if s["tts_ready"] else s["tts"].split(" (")[0])
    c[3].metric("그림", s["paint"].split(" (")[0])

    if not rows:
        st.info("아직 만든 책이 없어요.")
        return

    df = pd.DataFrame(rows)
    done = df[df["상태"].isin(["✅ 완료", "⚠️ 일부"])]
    st.markdown("##### 품질·속도 (완료된 책 기준)")
    c = st.columns(5)
    firsts = _nums(done["첫 소리(초)"])
    c[0].metric(f"완료율 ({len(df)}권 중)", f"{len(df[df['상태'] == '✅ 완료']) / len(df) * 100:.0f}%")
    c[1].metric("첫 소리 (중앙값)", f"{median(firsts):.1f}초" if firsts else "-")
    c[2].metric("삽화 한 장 (평균)", f"{_avg(done['삽화 평균(초)']) or 0:.1f}초")
    c[3].metric("동화 길이 (평균)", f"{(_avg(done['음성 길이(초)']) or 0) / 60:.1f}분")
    c[4].metric("서버 전환 / 한자 수정", f"{int(df['서버 전환'].sum())} / {int(df['한자 수정'].sum())}회")

    st.markdown("##### 책별 기록")
    st.dataframe(df, width="stretch", hide_index=True)
    st.caption("첫 소리 = 만들기를 누른 뒤 첫 음성이 만들어지기까지 (대기 포함). 대기 = 동시 제작 한도"
               f"({config.MAX_BOOKS_AT_ONCE}권) 때문에 차례를 기다린 시간. 예전 책에는 일부 값이 없을 수 있어요.")

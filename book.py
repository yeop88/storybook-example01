"""책 만들기 (백그라운드 스레드) — 이야기·음성·그림을 모두 실시간으로.

  LLM 스트리밍 ──줄 완성──▶ 말하기 스레드: TTS API 스트리밍 → PCM 조각을 바로 파일로
              └─장면 바뀜──▶ 그리기 스레드: SDXL-Lightning → 삽화 (한 장 약 1초)

static/books/<id>/
  book.json         진행 상황 + 내용 (브라우저 재생기가 계속 읽어 감)
  p<n>_<i>.pcm      n 쪽 음성의 i 번째 조각 (int16 24kHz mono, 생성되는 대로 추가)
  img_<j>.png       j 번째 삽화 (0 = 표지). 줄마다 "img" 로 어떤 삽화를 보여 줄지 지정
                    → 장면이 바뀌는 줄에서 삽화가 바뀜 (쪽마다 1장 이상)
"""

import json
import queue
import random
import shutil
import sys
import threading
import time
import uuid
from datetime import datetime

import numpy as np

import config
import gpu
import storyteller
import tts_client
from storyteller import NARRATOR, clean


def _queue_lock() -> threading.Lock:
    """책은 한 번에 한 권씩 만듦 (GPU 메모리 보호)."""
    if not hasattr(sys, "_story_book_lock"):
        sys._story_book_lock = threading.Lock()
        sys._story_waiting = []      # 차례를 기다리는 책 id (먼저 누른 순서)
        sys._story_making = None     # 지금 만드는 책 id
    return sys._story_book_lock


def queue_status() -> dict:
    """지금 만드는 책 / 기다리는 책 수 (화면 표시용)."""
    _queue_lock()
    return {"making": sys._story_making, "waiting": list(sys._story_waiting)}


def book_dir(book_id: str):
    return config.BOOKS_DIR / book_id


def read_book(book_id: str) -> dict | None:
    try:
        return json.loads((book_dir(book_id) / "book.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def list_books() -> list[dict]:
    books = [b for d in config.BOOKS_DIR.iterdir() if d.is_dir() and (b := read_book(d.name))]
    return sorted(books, key=lambda b: b.get("created", ""), reverse=True)


def delete_book(book_id: str):
    shutil.rmtree(book_dir(book_id), ignore_errors=True)


def page_audio(book_id: str, n: int) -> np.ndarray:
    """저장된 조각을 이어 붙인 n 쪽 음성 (다운로드용)."""
    b = read_book(book_id)
    k = b["pages"][n]["chunks"] if b else 0
    parts = [np.frombuffer((book_dir(book_id) / f"p{n}_{i}.pcm").read_bytes(), dtype="<i2") for i in range(k)]
    return np.concatenate(parts).astype(np.float32) / 32768 if parts else np.zeros(0, dtype=np.float32)


def _new_page(scene: str = "", cast=None, cover: bool = False) -> dict:
    return {"scene": scene, "cast": cast or [], "cover": cover, "lines": [], "img0": None,
            "chunks": 0, "duration": 0.0, "audio_done": False}


class ChoiceStop(Exception):
    """LLM 이 장 끝 선택(choice)을 썼음 → 쓰기를 멈추고 아이의 선택을 기다림."""

    def __init__(self, choice: dict | None):
        super().__init__("choice")
        self.choice = choice  # None 이면 LLM 이 질문 없이 다음 장을 시작하려 한 것 → 질문은 따로 만듦


def _cut_raw_after_choice(raw: list[str]):
    """이어 쓰기용 원문을 choice 줄까지만 남김 (LLM 이 그 뒤를 더 썼어도 버림)."""
    text = "".join(raw)
    i = text.rfind('"choice"')
    j = text.find("\n", i) if i != -1 else -1
    raw[:] = [text[: j + 1] if j != -1 else text + "\n"]


def _cut_raw_before_next_chapter(raw: list[str]):
    """이어 쓰기용 원문에서 다음 장을 시작한 page/chapter 줄부터 뒤를 버림."""
    lines = "".join(raw).split("\n")
    while lines:
        ev = storyteller._event(lines.pop())
        if ev and ev.get("type") in ("page", "chapter"):
            break
    while lines and (ev := storyteller._event(lines[-1])) and ev.get("type") == "chapter":
        lines.pop()
    raw[:] = ["\n".join(lines) + "\n"]


def makers() -> dict:
    """만드는 중인 책 (선택형 동화의 답을 전달하려고 보관)."""
    if not hasattr(sys, "_story_makers"):
        sys._story_makers = {}
    return sys._story_makers


def answer_choice(book_id: str, i: int, heard: str = "") -> bool:
    m = makers().get(book_id)
    if not m:
        return False
    m.answer(i, heard)
    return True


def match_choice(text: str, options: list[str]) -> int | None:
    """말한 내용 → 선택지 번호. 선택지 낱말이 들어 있으면 그것, 아니면 '첫 번째/두 번째' 같은 순서 말."""
    import re
    t = re.sub(r"[^\w]", "", text or "")
    if not t:
        return None

    def grams(x):
        x = re.sub(r"[^\w]", "", x)
        return {x[i:i + 2] for i in range(len(x) - 1)} or {x}

    # 두 글자 조각이 겹치는 수 + 선택지 낱말(예: '숲')이 통째로 들어 있으면 가산점
    scores = [len(grams(o) & grams(t)) + 2 * sum(1 for w in re.findall(r"\w+", o) if w in t) for o in options]
    best = max(scores)
    if best and scores.count(best) == 1:
        return scores.index(best)
    ordinals = [("첫", "하나", "일번", "1번", "1"), ("두", "둘", "이번", "2번", "2"), ("세", "셋", "삼번", "3번", "3")]
    for i, words in enumerate(ordinals):
        if i < len(options) and any(w in t for w in words):
            return i
    return None


class BookMaker:
    def __init__(self, request: dict):
        self.id = datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:4]
        self.dir = book_dir(self.id)
        self.dir.mkdir(parents=True)
        narrator = config.NARRATORS.get(request.get("narrator"), next(iter(config.NARRATORS.values())))
        self.req = {**request, "speaker": narrator[0], "narrator_timbre": narrator[1]}
        request = self.req
        self.cast: dict[str, tuple[str, str]] = {}  # 인물 → (화자, 음색·말투 지시)
        self.errors: list[str] = []
        self.answers: queue.Queue = queue.Queue()  # 선택형 동화: 아이의 선택
        self.ref_img = None  # 표지 그림 (이후 삽화가 주인공 모습을 따라 그리도록)
        self._lock = threading.RLock()
        self.book = {
            "id": self.id, "created": datetime.now().strftime("%Y-%m-%d %H:%M"), "request": request,
            "status": "waiting", "message": "앞선 책을 만드는 중이라 잠시 기다립니다...", "error": "",
            "title": "", "characters": [], "pages": [], "illus": [], "chapters": [], "story_done": False, "choice": None,
        }
        self._save()

    def start(self) -> str:
        makers()[self.id] = self
        threading.Thread(target=self._run, daemon=True, name=f"book-{self.id}").start()
        return self.id

    # --- 저장 ---------------------------------------------------------------
    def _save(self):
        data = json.dumps(self.book, ensure_ascii=False)
        tmp = self.dir / "book.json.tmp"
        tmp.write_text(data, encoding="utf-8")
        for _ in range(50):  # 브라우저가 읽는 중이면 Windows 에서 교체가 잠깐 막힐 수 있음
            try:
                tmp.replace(self.dir / "book.json")
                return
            except PermissionError:
                time.sleep(0.01)

    def _update(self, **kw):
        with self._lock:
            self.book.update(kw)
            self._save()

    def _add_chunk(self, n: int, pcm: np.ndarray):
        with self._lock:
            page = self.book["pages"][n]
            i = page["chunks"]
            tmp = self.dir / f"p{n}_{i}.tmp"
            tmp.write_bytes((np.clip(pcm, -1, 1) * 32767).astype("<i2").tobytes())
            tmp.replace(self.dir / f"p{n}_{i}.pcm")
            page["chunks"] = i + 1
            page["duration"] = round(page["duration"] + len(pcm) / config.SR, 2)
            self._save()

    # --- 목소리 배정 -----------------------------------------------------------
    def _add_character(self, c: dict):
        r = self.req
        voice = c["voice"] if c["voice"] in config.VOICE_TYPES else "creature"
        speaker, timbre = config.VOICE_TYPES[voice]
        if r["cast"] == "same":
            speaker = r["speaker"]
        else:  # 해설자·다른 인물과 겹치지 않게
            used = {r["speaker"]} | {s for s, _ in self.cast.values()}
            if speaker in used:
                alt = [s for s, _ in config.VOICE_TYPES.values() if s not in used]
                speaker = alt[0] if alt else speaker
        self.cast[c["name"]] = (speaker, " ".join(x for x in (timbre, c["tone"]) if x))
        with self._lock:
            self.book["characters"].append({**c, "voice": voice, "speaker": speaker})
            self._save()

    def _voice(self, line: dict) -> tuple[str, str]:
        """줄 하나의 (화자, 지시문) = 인물 음색·기본 말투(또는 해설 느낌) + 이 줄의 감정."""
        if line["who"] in self.cast:
            speaker, base = self.cast[line["who"]]
        else:
            speaker = self.req["speaker"]
            base = " ".join(x for x in (self.req.get("narrator_timbre", ""), config.VOICES[self.req["voice"]]) if x)
        emotion = line.get("emotion", "")
        return speaker, " ".join(x for x in (base, f"이번 문장은 {emotion} 말하세요." if emotion else "") if x)

    # --- 실행 ---------------------------------------------------------------
    def _run(self):
        self._acquire_turn()
        try:
            self._make()
        except Exception as e:  # noqa: BLE001
            self._update(status="error", error=str(e), message=f"만들기 실패: {e}", story_done=True)
        finally:
            self._release_turn()

    def _acquire_turn(self, resumed: bool = False):
        """차례 기다리기: 앞에 몇 권이 있는지 1초마다 알려 줌."""
        lock = _queue_lock()
        sys._story_waiting.append(self.id)
        while not lock.acquire(timeout=1.0):
            ahead = sys._story_waiting.index(self.id) + 1  # 지금 만드는 책 + 앞에서 기다리는 책
            self._update(status="waiting" if not resumed else "choice_wait",
                         message=f"⏳ 앞에 {ahead}권이 만들어지는 중이에요. 차례가 되면 바로 시작해요.")
        sys._story_waiting.remove(self.id)
        sys._story_making = self.id

    def _release_turn(self):
        if sys._story_making == self.id:
            sys._story_making = None
        _queue_lock().release()

    def _make(self):
        r = self.req
        t0 = time.time()
        self._update(status="writing", message="✍️ 이야기를 쓰면서 바로 읽어 줄게요...")
        draw_q: queue.Queue = queue.Queue()
        speak_q: queue.Queue = queue.Queue()
        workers = [threading.Thread(target=self._drawer, args=(draw_q,), daemon=True),
                   threading.Thread(target=self._speaker, args=(speak_q,), daemon=True)]
        for w in workers:
            w.start()

        pages = self.book["pages"]

        def ensure_cover():
            if not pages:
                with self._lock:
                    pages.append(_new_page(cover=True))
                    self._save()

        cover_drawn = False
        self.cur_img = None  # 지금 쓰고 있는 줄에 걸릴 삽화 번호

        def new_illus(n: int, scene: str, cast: list) -> int:
            """삽화 하나 추가 → 바로 그리기 대기열로. 이후 줄은 이 삽화를 보여 줌."""
            with self._lock:
                ill = self.book["illus"]
                ill.append({"page": n, "scene": scene, "cast": cast, "image": False})
                j = len(ill) - 1
                if pages[n].get("img0") is None:
                    pages[n]["img0"] = j
                self.cur_img = j
                self._save()
            draw_q.put(j)
            return j

        total = r["chapters"] * r["pages_per"]     # 정확히 지킬 전체 쪽수
        per = r["pages_per"]
        outline = r.get("outline") or []
        llm_titles: dict[int, str] = {}           # LLM 이 붙인 장 제목

        def content_pages() -> int:
            return max(0, len(pages) - 1)

        def chapter_title(c: int) -> str:
            mine = outline[c - 1].get("title", "") if c - 1 < len(outline) else ""
            return mine or llm_titles.get(c, "")

        def add_page(scene: str, cast: list) -> int:
            nonlocal cover_drawn
            if not cover_drawn:  # 표지는 인물 소개가 끝난 뒤 그려야 생김새가 맞음
                new_illus(0, pages[0]["scene"], [])
                cover_drawn = True
            with self._lock:
                pages.append(_new_page(scene, cast))
                n = len(pages) - 1
                chapter = (n - 1) // per + 1
                pages[n]["chapter"] = chapter
                self.book["message"] = f"✍️ {n} / {total}쪽을 쓰는 중..."
                self._save()
            speak_q.put(("end", n - 1))  # 앞 페이지는 더 쓸 줄이 없음
            new_illus(n, scene or pages[0]["scene"], cast)
            if r["chapters"] > 1 and (n - 1) % per == 0:  # 새 장의 첫 쪽: "제N장. 제목." 부터 읽음
                title = chapter_title(chapter)
                with self._lock:
                    self.book["chapters"].append({"no": chapter, "title": title, "page": n})
                    self._save()
                self._add_line(n, {"who": NARRATOR, "text": f"제{chapter}장. {title}." if title else f"제{chapter}장.",
                                   "emotion": "새 장을 여는 설렘을 담아, 장 제목을 또렷하고 천천히"}, speak_q)
            return n

        def ensure_page():
            """첫 page 줄 전에 line/scene 이 오면 1쪽을 만들어 줌."""
            if len(pages) == 1:
                add_page(pages[0]["scene"], [])

        intro_done = [False]

        def need_intro():
            """LLM 이 도입 인사를 빠뜨렸으면 바로 넣음 → 표지에서 인물 소개·1쪽을 쓰는 동안 읽을 거리."""
            if not intro_done[0] and self.book["title"] and len(pages) == 1:
                intro_done[0] = True
                self._add_line(0, {"who": NARRATOR, "text": "자, 그럼 이야기를 시작해 볼까요?",
                                   "emotion": "설레는 마음으로 다정하게, 아이에게 말을 건네듯"}, speak_q)

        providers = [r["llm"]] + [p for p in config.LLM_PROVIDERS if p != r["llm"]]  # 실패하면 다음 서버로

        def ko(text: str) -> str:
            """한국어 동화에 한자·중국어가 섞이면 읽기 전에 한글로 고침."""
            if r["language"] == "Korean" and storyteller.has_foreign(text):
                fixed = storyteller.fix_foreign(providers[0], text)
                with self._lock:
                    self.book.setdefault("fixed", []).append({"from": text, "to": fixed})
                return fixed
            return text

        asked: set[int] = set()  # 선택 질문을 이미 한 장 번호

        def at_boundary():
            """선택형: 한 장을 다 쓰고 다음 장을 시작하려 하면 멈추고 아이에게 물음 (LLM 이 질문을 빠뜨려도)."""
            done = content_pages()
            if r.get("interactive") and done and done % per == 0 and done < total and done // per not in asked:
                asked.add(done // per)
                raise ChoiceStop(None)

        def handle(ev: dict):
            typ = ev.get("type")
            for key in ("text", "title"):
                if isinstance(ev.get(key), str) and typ in ("title", "intro", "line", "chapter"):
                    ev[key] = ko(ev[key])
            cast = [clean(c) for c in ev.get("cast", []) if isinstance(c, str)]
            if typ == "title" and not self.book["title"]:
                title = clean(ev.get("text")) or "제목 없는 동화"
                ensure_cover()
                self._update(title=title)
                self._add_line(0, {"who": NARRATOR, "text": title if title.endswith((".", "!", "?")) else title + ".",
                                   "emotion": "설레고 다정하게, 이야기를 시작하듯 또박또박"}, speak_q)
            elif typ == "intro":
                text = clean(ev.get("text"))
                if text and not intro_done[0] and len(pages) == 1:
                    intro_done[0] = True
                    self._add_line(0, {"who": NARRATOR, "text": text,
                                       "emotion": clean(ev.get("emotion")) or "다정하게 말을 건네듯 천천히"}, speak_q)
            elif typ == "cover":
                ensure_cover()
                need_intro()
                with self._lock:
                    pages[0]["scene"] = clean(ev.get("scene"))
            elif typ == "character":
                need_intro()
                name = clean(ev.get("name"))
                if name and name != NARRATOR and name not in self.cast:
                    self._add_character({"name": name, "look": clean(ev.get("look")), "voice": clean(ev.get("voice")),
                                         "tone": clean(ev.get("tone"))})
            elif typ == "chapter":
                at_boundary()
                try:
                    no, title = int(ev.get("no")), clean(ev.get("title"))
                    llm_titles[no] = title
                    with self._lock:  # 장 줄이 쪽보다 늦게 와도 화면의 장 이름은 채움
                        for c in self.book["chapters"]:
                            if c["no"] == no and not c["title"] and title:
                                c["title"] = title
                                self._save()
                except (TypeError, ValueError):
                    pass
            elif typ == "page":
                ensure_cover()
                need_intro()
                at_boundary()
                if content_pages() >= total:
                    # 쪽수를 넘김 → 새 쪽을 만들지 않고 마지막 쪽에 이어 붙임 (결말은 살리고 쪽수는 정확히)
                    new_illus(len(pages) - 1, clean(ev.get("scene")), cast)
                else:
                    add_page(clean(ev.get("scene")), cast)
            elif typ == "scene":
                scene = clean(ev.get("scene"))
                if scene:
                    ensure_cover()
                    ensure_page()
                    new_illus(len(pages) - 1, scene, cast)
            elif typ == "choice":
                opts = [clean(o) for o in ev.get("options", []) if clean(o)][:3]
                last_chapter = (content_pages() - 1) // per + 1 >= r["chapters"]
                chapter_end = content_pages() > 0 and content_pages() % per == 0  # 장의 마지막 쪽에서만 물음
                if r.get("interactive") and len(opts) >= 2 and chapter_end and not last_chapter:
                    asked.add(content_pages() // per)
                    raise ChoiceStop({"question": clean(ev.get("question")) or "어느 쪽으로 가 볼까요?", "options": opts})
            elif typ == "line":
                text = clean(ev.get("text"))
                if not text:
                    return
                ensure_cover()
                ensure_page()
                who = clean(ev.get("who"))
                self._add_line(len(pages) - 1, {"who": who if who in self.cast else NARRATOR, "text": text,
                                                "emotion": clean(ev.get("emotion"))}, speak_q)

        raw: list[str] = []

        def write(choice: str = ""):
            """LLM 서버가 실패하면 다음 서버로 넘어가 (쓴 데까지 이어서) 계속 씀."""
            last = None
            for prov in list(providers):
                try:
                    if not raw:
                        gen = storyteller.stream_story(prov, r, raw)
                    else:
                        gen = storyteller.continue_story(prov, r, raw, content_pages(), choice)
                    for ev in gen:
                        handle(ev)
                    if prov != r["llm"]:
                        with self._lock:
                            self.book["llm_used"] = prov
                    return
                except ChoiceStop as c:
                    gen.close()  # 지금 바로 LLM 연결을 끊음 (안 그러면 아이가 고르는 동안 서버가 남은 글을 계속 씀)
                    if c.choice is None:
                        _cut_raw_before_next_chapter(raw)
                    else:
                        _cut_raw_after_choice(raw)
                    raise
                except Exception as e:  # noqa: BLE001
                    last = e
                    with self._lock:  # 오류가 아니라 안내 기록 (다음 서버가 이어서 씀)
                        self.book.setdefault("notes", []).append(f"AI 서버 {prov} 실패 → 다음 서버로: {type(e).__name__}")
                    providers.remove(prov)
                    providers.append(prov)
            raise RuntimeError(f"모든 AI 서버가 응답하지 않습니다: {last}")

        choice, stalls = "", 0
        for _ in range(r["chapters"] + 6):
            before = content_pages()
            try:
                write(choice)
                choice = ""
            except ChoiceStop as c:  # 장 끝에서 아이에게 묻고, 고른 대로 다음 장을 이어 씀
                ch = c.choice or storyteller.make_choice(providers[0], r, raw)
                choice = self._ask_choice(ch, speak_q)
                continue
            if content_pages() >= total or not self.book["title"]:
                break
            stalls = stalls + 1 if content_pages() == before else 0
            if stalls >= 2:
                break
            self._update(message=f"✍️ 남은 {total - content_pages()}쪽을 이어서 쓰는 중...")
        if not pages or len(pages) == 1 and not pages[0]["lines"]:
            raise RuntimeError("AI 가 이야기를 만들지 못했습니다. 다시 시도해 주세요.")
        if not cover_drawn:
            new_illus(0, pages[0]["scene"], [])
        speak_q.put(("end", len(pages) - 1))
        self._update(story_done=True, status="making", story_seconds=round(time.time() - t0, 1),
                     message="🎨 남은 그림과 목소리를 마무리하는 중...")
        draw_q.put(None)
        speak_q.put(None)
        for w in workers:
            w.join()
        self._update(status="done" if not self.errors else "partial", error="; ".join(self.errors)[:500],
                     message="✅ 완성!" if not self.errors else "⚠️ 일부를 만들지 못했어요.",
                     total_seconds=round(time.time() - t0, 1))

    # --- 선택형 동화 -------------------------------------------------------------
    def _ask_choice(self, ch: dict, speak_q: queue.Queue) -> str:
        """장 끝: 질문을 읽어 주고 아이의 선택을 기다림 (버튼 또는 말). 고른 선택지 글을 돌려줌."""
        n = len(self.book["pages"]) - 1
        opts = ch["options"]
        nums = ["첫 번째", "두 번째", "세 번째"]
        ask = ch["question"] + " " + " ".join(f"{nums[i]}, {o}." for i, o in enumerate(opts))
        self._add_line(n, {"who": NARRATOR, "text": ask, "emotion": "궁금한 듯 밝게, 아이에게 물어보듯 또박또박"}, speak_q)
        with self._lock:
            k = len(self.book["pages"][n]["lines"]) - 1
            self.book["choice"] = {"no": len(self.book.get("choices", [])) + 1, "page": n, "line": k,
                                   "question": ch["question"], "options": opts, "answer": None, "heard": ""}
            self.book["status"] = "choice"
            self.book["message"] = "🤔 아래에서 골라 주세요! (버튼을 누르거나 말로 대답)"
            self._save()
        while not self.answers.empty():  # 앞선 질문에 두 번 누른 답 등은 버림
            self.answers.get_nowait()
        # 아이가 고르는 동안에는 차례를 양보 → 기다리던 다른 사람의 책을 먼저 만들 수 있음
        self._release_turn()
        try:
            i, heard = self.answers.get(timeout=300)
        except queue.Empty:  # 5분 동안 대답이 없으면 첫 번째로
            i, heard = 0, "(대답 없음)"
        pick = opts[i]
        with self._lock:  # 답은 바로 기록 (선택 칸이 곧바로 사라지게)
            self.book["choice"].update(answer=i, heard=heard)
            self.book.setdefault("choices", []).append(dict(self.book["choice"]))
            self.book["status"] = "writing"
            self.book["message"] = f"✍️ '{pick}' 이야기를 이어서 쓰는 중..."
            self._save()
        self._add_line(n, {"who": NARRATOR, "text": f"좋아요! {pick}. 그럼 이야기를 계속해 볼까요?",
                           "emotion": "신이 나서 밝고 경쾌하게"}, speak_q)
        self._acquire_turn(resumed=True)
        self._update(status="writing", message=f"✍️ '{pick}' 이야기를 이어서 쓰는 중...")
        return pick

    def answer(self, i: int, heard: str = ""):
        self.answers.put((i, heard))

    def _add_line(self, n: int, line: dict, speak_q: queue.Queue):
        with self._lock:
            lines = self.book["pages"][n]["lines"]
            img = self.cur_img if n == len(self.book["pages"]) - 1 and n > 0 else None
            lines.append({**line, "chunk": None, "img": img})
            k = len(lines) - 1
            self._save()
        speak_q.put((n, k))

    # --- 말하기: 줄마다 TTS 스트리밍 → 조각을 바로 파일로 -------------------------
    def _speaker(self, q: queue.Queue):
        pause = np.zeros(int(config.SR * config.LINE_PAUSE), dtype=np.float32)
        while (item := q.get()) is not None:
            if item[0] == "end":
                with self._lock:
                    self.book["pages"][item[1]]["audio_done"] = True
                    self._save()
                continue
            n, k = item
            with self._lock:
                page = self.book["pages"][n]
                line = page["lines"][k]
                speaker, instruct = self._voice(line)
                line.update(chunk=page["chunks"], speaker=speaker, instruct=instruct)
            try:
                for pcm in tts_client.stream(line["text"], speaker, self.req["language"], instruct):
                    self._add_chunk(n, pcm)
            except Exception as e:  # noqa: BLE001
                self.errors.append(f"음성 {n}-{k}: {e}")
            self._add_chunk(n, pause)

    # --- 그리기: 삽화가 생기는 대로 바로 (GPU 상주, 한 장 약 1초) ---------------------
    def _drawer(self, q: queue.Queue):
        style = config.STYLES[self.req["style"]]
        seed = random.randint(0, 2**31 - 1)  # 한 권 안에서는 같은 시드 → 그림체 일관성
        while (j := q.get()) is not None:
            with self._lock:
                il = self.book["illus"][j]
                cover = self.book["pages"][il["page"]]["cover"]
                chars = self.book["characters"]
                names = il["cast"] or ([c["name"] for c in chars[:2]] if cover else [])
                looks = ([c["look"] for c in chars if c["name"] in names and c["look"]]
                         or [c["look"] for c in chars[:1] if c["look"]])
                scene = il["scene"] or self.book["pages"][il["page"]]["scene"]
            head = f"{style}, book cover illustration" if cover else style
            prompt = ", ".join([head, *looks, scene, "no text, no letters"])
            t = time.time()
            try:
                # 표지를 먼저 그리고, 이후 삽화는 표지 속 주인공 모습을 참고해서 그림 (IP-Adapter)
                img = gpu.paint(prompt, seed=seed, ref=None if cover else self.ref_img)
                img.save(self.dir / f"img_{j}.png")
                if cover:
                    self.ref_img = img
                ok = True
            except Exception as e:  # noqa: BLE001
                self.errors.append(f"그림 {j}: {e}")
                ok = "error"
            with self._lock:
                il.update(image=ok, prompt=prompt, seconds=round(time.time() - t, 2))
                self._save()

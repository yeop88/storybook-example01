"""책 저장소: static/books/<id>/ 폴더 (브라우저가 /app/static/books/<id>/ 로 바로 읽음).

  book.json         내용·진행 상황 (재생기가 계속 읽어 감)
  p<n>_<i>.pcm      n 쪽 음성의 i 번째 조각 (int16 24kHz mono, 생성되는 대로 추가)
  img_<j>.png       j 번째 삽화 (0 = 표지). 줄마다 "img" 로 어떤 삽화를 보여 줄지 지정
"""

import json
import secrets
import shutil
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from storybook import config


def new_id() -> str:
    """날짜(정렬용) + 추측할 수 없는 64비트 난수 → 다른 사람이 책 주소를 짐작해 열 수 없음."""
    return datetime.now().strftime("%Y%m%d_%H%M%S_") + secrets.token_hex(8)


def book_dir(book_id: str) -> Path:
    return config.BOOKS_DIR / book_id


def read_book(book_id: str) -> dict | None:
    try:
        return json.loads((book_dir(book_id) / "book.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_book(book_id: str, book: dict):
    """원자적으로 저장 (브라우저가 읽는 중이면 Windows 에서 교체가 잠깐 막힐 수 있어 재시도)."""
    d = book_dir(book_id)
    tmp = d / "book.json.tmp"
    tmp.write_text(json.dumps(book, ensure_ascii=False), encoding="utf-8")
    for _ in range(50):
        try:
            tmp.replace(d / "book.json")
            return
        except PermissionError:
            time.sleep(0.01)


def write_chunk(book_id: str, page: int, index: int, pcm: np.ndarray):
    d = book_dir(book_id)
    tmp = d / f"p{page}_{index}.tmp"
    tmp.write_bytes((np.clip(pcm, -1, 1) * 32767).astype("<i2").tobytes())
    tmp.replace(d / f"p{page}_{index}.pcm")


def image_path(book_id: str, j: int) -> Path:
    return book_dir(book_id) / f"img_{j}.png"


def cover_path(book_id: str) -> Path | None:
    d = book_dir(book_id)
    for name in ("img_0.png", "page_0.png"):  # page_0.png: 예전 형식의 책
        if (d / name).exists():
            return d / name
    return None


def list_books() -> list[dict]:
    books = [b for d in config.BOOKS_DIR.iterdir() if d.is_dir() and (b := read_book(d.name))]
    return sorted(books, key=lambda b: b.get("created", ""), reverse=True)


def delete_book(book_id: str):
    shutil.rmtree(book_dir(book_id), ignore_errors=True)


def usage() -> tuple[int, int]:
    """(책 수, 사용 용량 바이트)."""
    count = size = 0
    for d in config.BOOKS_DIR.iterdir():
        if d.is_dir():
            count += 1
            size += sum(f.stat().st_size for f in d.iterdir() if f.is_file())
    return count, size


def cleanup_old(keep_days: int, active: set[str]) -> int:
    """keep_days 일보다 오래된 책 지우기 (0 이면 지우지 않음, 만드는 중인 책은 건드리지 않음)."""
    if keep_days <= 0:
        return 0
    cutoff = time.time() - keep_days * 86400
    n = 0
    for d in config.BOOKS_DIR.iterdir():
        try:
            if d.is_dir() and d.name not in active and (d / "book.json").stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
                n += 1
        except OSError:
            pass
    return n

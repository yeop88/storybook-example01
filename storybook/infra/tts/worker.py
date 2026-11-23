"""TTS 전용 작업 프로세스 (story_app 이 직접 띄우고 관리).

TTS 는 실시간이어야 하는데, 웹 화면·LLM·그림 스레드와 한 프로세스에 있으면 Python 잠금(GIL)을 나눠 써서 밀린다.
그래서 TTS 모델만 이 프로세스에서 돌리고, 본 프로세스와는 큐 두 개로 주고받는다.

  본 프로세스 ──요청 (job_id, text, speaker, language, instruct, priority)──▶ 이 프로세스
             ◀──("status", 상태, 준비됨, 불러오기 끝남) / ("chunk", job_id, PCM) / ("done", job_id, 오류)──
"""

import threading
import time


def run(req_q, resp_q):
    from storybook.infra.tts.engine import TTSEngine

    eng = TTSEngine()
    eng.start()

    def report_status():
        last = None
        while True:
            cur = (eng.status, eng.ready.is_set() and eng.load_error is None, eng.ready.is_set())
            if cur != last:
                resp_q.put(("status", *cur))
                last = cur
            time.sleep(0.3)

    def serve(job_id, job):
        try:
            for chunk in job.iter_chunks():
                resp_q.put(("chunk", job_id, chunk))
            resp_q.put(("done", job_id, None))
        except Exception as e:  # noqa: BLE001
            resp_q.put(("done", job_id, str(e)))

    threading.Thread(target=report_status, daemon=True, name="tts-status").start()
    while (msg := req_q.get()) is not None:
        job_id, text, speaker, language, instruct, priority = msg
        eng.wait_ready()
        if eng.load_error:
            resp_q.put(("done", job_id, eng.status))
            continue
        job = eng.stream(text, speaker, language, instruct, priority)
        threading.Thread(target=serve, args=(job_id, job), daemon=True).start()

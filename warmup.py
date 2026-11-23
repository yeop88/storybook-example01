"""서버 시작 직후 세션을 하나 열어 STT·그림 모델을 미리 GPU 에 올립니다 (HTTPS, 자체 서명 인증서 허용).

사용: python warmup.py [host:port]   (기본 localhost:8502)
"""

import asyncio
import ssl
import sys
import time

import websockets
from streamlit.proto.BackMsg_pb2 import BackMsg
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg

HOST = sys.argv[1] if len(sys.argv) > 1 else "localhost:8502"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE  # 이 PC 의 자체 서명 인증서


async def main():
    async with websockets.connect(f"wss://{HOST}/_stcore/stream", ssl=CTX, max_size=None, open_timeout=60) as ws:
        msg = BackMsg()
        msg.rerun_script.query_string = ""
        msg.rerun_script.page_script_hash = ""
        await ws.send(msg.SerializeToString())
        while True:
            fwd = ForwardMsg()
            fwd.ParseFromString(await asyncio.wait_for(ws.recv(), timeout=600))
            if fwd.WhichOneof("type") == "script_finished":
                return


for _ in range(60):
    try:
        asyncio.run(main())
        break
    except OSError:
        time.sleep(2)
else:
    sys.exit("warmup failed: server not reachable")
print("warmup done", time.strftime("%H:%M:%S"))

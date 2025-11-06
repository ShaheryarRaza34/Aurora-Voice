# backend/server.py
import os
import time
import json
import asyncio
import collections
import subprocess
from pathlib import Path
from typing import Deque

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from faster_whisper import WhisperModel
import webrtcvad
import uvicorn

# -------------------------
# CONFIG
# -------------------------
SAMPLE_RATE = 16000                   # we send 16 kHz to the server
FRAME_MS = 20                         # client sends 20 ms frames
FRAME_BYTES = int(SAMPLE_RATE * (FRAME_MS / 1000)) * 2  # 16-bit PCM
CHUNK_SECONDS = 1.0                   # decode window for partials
OVERLAP_SECONDS = 0.2                 # left overlap for stability
PARTIAL_EMIT_SEC = 0.35               # cadence for partials
FINAL_SILENCE_MS = 700                # endpointing (silence to finalize)

ASR_MODEL_NAME = os.getenv("ASR_MODEL", "medium")  # "small", "medium", "large-v3" etc.
ASR_DEVICE = os.getenv("ASR_DEVICE", "auto")       # "cpu", "cuda", or "auto"
ASR_COMPUTE = os.getenv("ASR_COMPUTE", "int8_float16")  # good default on modern GPUs/CPUs

# Piper
PIPER_BIN = os.getenv("PIPER_BIN", "piper")
PIPER_MODEL = os.getenv("PIPER_MODEL", "")  # e.g. models/en_US-amy-low.onnx
PIPER_OUT = Path(os.getenv("PIPER_OUT", "out.wav")).resolve()

# -------------------------
# INIT
# -------------------------
app = FastAPI(title="Local Voice Assistant (MS1)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# Load ASR model once at startup
model = WhisperModel(ASR_MODEL_NAME, device=ASR_DEVICE, compute_type=ASR_COMPUTE)
vad = webrtcvad.Vad(2)  # 0-3, 3 = most aggressive


# -------------------------
# UTIL
# -------------------------
def bytes_to_float32(buf: bytes) -> np.ndarray:
    """16-bit little-endian PCM -> float32 [-1, 1]."""
    arr = np.frombuffer(buf, dtype=np.int16).astype(np.float32) / 32768.0
    return arr


def is_speech(frame_bytes: bytes) -> bool:
    """WebRTC VAD expects 10/20/30 ms frames at 8/16/32 kHz."""
    return vad.is_speech(frame_bytes, SAMPLE_RATE)


# -------------------------
# ROUTES
# -------------------------
@app.get("/")
def root():
    return HTMLResponse("<h3>ASR WS at /ws/asr — TTS at /tts?text=...</h3>")


@app.websocket("/ws/asr")
async def ws_asr(ws: WebSocket):
    """Receive 16 kHz PCM16 frames; send partial/final transcripts."""
    await ws.accept()
    ring: Deque[float] = collections.deque(
        maxlen=int(SAMPLE_RATE * (CHUNK_SECONDS + OVERLAP_SECONDS) * 2)
    )
    last_emit = 0.0
    last_speech_time = time.time()
    have_text = False
    pending = b""

    try:
        while True:
            chunk = await ws.receive_bytes()
            pending += chunk

            # process in 20 ms steps
            while len(pending) >= FRAME_BYTES:
                frame = pending[:FRAME_BYTES]
                pending = pending[FRAME_BYTES:]

                # VAD for endpointing
                if is_speech(frame):
                    last_speech_time = time.time()

                # push into ring buffer
                ring.extend(bytes_to_float32(frame))

                # emit partials at cadence
                if (time.time() - last_emit) > PARTIAL_EMIT_SEC and len(ring) > SAMPLE_RATE * 0.4:
                    last_emit = time.time()
                    arr = np.array(ring)
                    n_ctx = int(SAMPLE_RATE * (CHUNK_SECONDS + OVERLAP_SECONDS))
                    window = arr[-n_ctx:] if arr.shape[0] > n_ctx else arr

                    segments, _ = model.transcribe(
                        window,
                        language=None,                 # auto
                        beam_size=1,                   # speed
                        vad_filter=False,
                        condition_on_previous_text=False,
                    )
                    partial = "".join(s.text for s in segments).strip()
                    if partial:
                        have_text = True
                        await ws.send_text(json.dumps({"type": "partial", "text": partial}))

                # finalize on silence
                if have_text and (time.time() - last_speech_time) * 1000 > FINAL_SILENCE_MS:
                    arr = np.array(ring)
                    segments, _ = model.transcribe(
                        arr,
                        language=None,
                        beam_size=1,
                        vad_filter=False,
                        condition_on_previous_text=False,
                        word_timestamps=True,
                    )
                    final_text = "".join(s.text for s in segments).strip()
                    # optional word timestamps (flat list)
                    words = []
                    for s in segments:
                        if s.words:
                            for w in s.words:
                                words.append({"word": w.word, "start": float(w.start), "end": float(w.end)})

                    await ws.send_text(json.dumps({"type": "final", "text": final_text, "ts": words}))
                    # reset state
                    ring.clear()
                    have_text = False
                    last_emit = time.time()

    except WebSocketDisconnect:
        return
    except Exception as e:
        try:
            await ws.send_text(json.dumps({"type": "error", "message": str(e)}))
        finally:
            await ws.close()


@app.get("/tts")
def tts(text: str):
    """Generate speech via Piper and return audio/wav."""
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="text is empty")

    if not PIPER_MODEL:
        return JSONResponse(
            status_code=400,
            content={"error": "PIPER_MODEL not set. Example: export PIPER_MODEL=./models/en_US-amy-low.onnx"},
        )

    # Run Piper once per request
    try:
        if PIPER_OUT.exists():
            PIPER_OUT.unlink(missing_ok=True)

        cmd = [
            PIPER_BIN,
            "--model", PIPER_MODEL,
            "--output_file", str(PIPER_OUT),
            "--text", text,
        ]
        subprocess.run(cmd, check=True)
        return FileResponse(str(PIPER_OUT), media_type="audio/wav")
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Piper failed: {e}") from e


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

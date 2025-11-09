# backend/server.py
import os, time, json, collections, subprocess
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
# CONFIG (tuned for accuracy + stability)
# -------------------------
SAMPLE_RATE = 16000
FRAME_MS = 20
FRAME_BYTES = int(SAMPLE_RATE * (FRAME_MS / 1000)) * 2  # 16-bit PCM
CHUNK_SECONDS = 2.4          # enough context for phrases
OVERLAP_SECONDS = 0.6
PARTIAL_EMIT_SEC = 0.5
FINAL_SILENCE_MS = 1200      # finalize after ~1.2s of silence

# Defaults that work everywhere; override via env when you have a GPU
ASR_MODEL_NAME = os.getenv("ASR_MODEL", "medium.en")   # English-only model is more accurate for English
ASR_DEVICE = os.getenv("ASR_DEVICE", "cpu")            # "cpu" or "cuda"
ASR_COMPUTE = os.getenv("ASR_COMPUTE", "int8")         # great baseline on CPU

# Piper (optional)
PIPER_BIN = os.getenv("PIPER_BIN", "piper")
PIPER_MODEL = os.getenv("PIPER_MODEL", "")
PIPER_OUT = Path(os.getenv("PIPER_OUT", "out.wav")).resolve()

# -------------------------
# INIT
# -------------------------
app = FastAPI(title="Local Voice Assistant (MS1)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

print(f"[INIT] Loading Whisper: {ASR_MODEL_NAME} on {ASR_DEVICE} ({ASR_COMPUTE})")
model = WhisperModel(ASR_MODEL_NAME, device=ASR_DEVICE, compute_type=ASR_COMPUTE)
vad = webrtcvad.Vad(1)  # 0-3; 1 is a good balance

# -------------------------
# UTIL
# -------------------------
def bytes_to_float32(buf: bytes) -> np.ndarray:
    # 16-bit little-endian PCM -> float32 [-1, 1]
    return np.frombuffer(buf, dtype=np.int16).astype(np.float32) / 32768.0

def is_speech(frame_bytes: bytes) -> bool:
    # WebRTC VAD expects 10/20/30ms frames at 8/16/32kHz
    return vad.is_speech(frame_bytes, SAMPLE_RATE)

# -------------------------
# ROUTES
# -------------------------
@app.get("/")
def root():
    return HTMLResponse("<h3>ASR WS at /ws/asr — TTS at /tts?text=...</h3>")

@app.websocket("/ws/asr")
async def ws_asr(ws: WebSocket):
    """Receive 16kHz PCM16 frames; send partial/final transcripts."""
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

                # endpointing via VAD
                if is_speech(frame):
                    last_speech_time = time.time()

                # push into ring buffer
                ring.extend(bytes_to_float32(frame))

                # emit partials on cadence (need a bit of audio first)
                if (time.time() - last_emit) > PARTIAL_EMIT_SEC and len(ring) > SAMPLE_RATE * 0.6:
                    last_emit = time.time()
                    arr = np.array(ring)
                    n_ctx = int(SAMPLE_RATE * (CHUNK_SECONDS + OVERLAP_SECONDS))
                    window = arr[-n_ctx:] if arr.shape[0] > n_ctx else arr

                    # IMPORTANT: English-only & transcription-only for partials
                    segments, _ = model.transcribe(
                        window,
                        task="transcribe",            # force transcription (no translation)
                        language="en",                # force English
                        beam_size=1,                  # fast partials
                        vad_filter=False,
                        condition_on_previous_text=False,
                        temperature=0.0,
                        without_timestamps=True,      # partials don't need timestamps
                    )
                    partial = "".join(s.text for s in segments).strip()
                    if partial:
                        have_text = True
                        await ws.send_text(json.dumps({"type": "partial", "text": partial}))

                # finalize on silence
                if have_text and (time.time() - last_speech_time) * 1000 > FINAL_SILENCE_MS:
                    arr = np.array(ring)

                    # IMPORTANT: English-only & transcription-only for finals
                    segments, _ = model.transcribe(
                        arr,
                        task="transcribe",            # force transcription (no translation)
                        language="en",                # force English
                        beam_size=5,                  # more accurate final
                        vad_filter=True,
                        condition_on_previous_text=True,   # use context to avoid drops
                        temperature=0.0,
                        word_timestamps=True,
                    )
                    final_text = "".join(s.text for s in segments).strip()
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

from tempfile import NamedTemporaryFile
from starlette.background import BackgroundTask
import shutil

@app.get("/tts")
def tts(text: str):
    text = (text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is empty")

    # Validate piper binary & model path
    if not shutil.which(PIPER_BIN):
        return JSONResponse(
            status_code=400,
            content={"error": f"PIPER_BIN not found: '{PIPER_BIN}'. Set PIPER_BIN to your piper executable."},
        )

    model_path = Path(PIPER_MODEL)
    cfg_path = model_path.with_suffix(model_path.suffix + ".json")  # .onnx.json
    if not model_path.exists() or not cfg_path.exists():
        return JSONResponse(
            status_code=400,
            content={"error": f"Missing Piper files. Need both:\n{model_path}\n{cfg_path}\nFix your volume mount or PIPER_MODEL."},
        )

    try:
        # Unique temp output per request
        with NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            out_path = Path(tmp.name)

        # Pipe text via stdin (most reliable across platforms)
        cmd = [PIPER_BIN, "--model", str(model_path), "--output_file", str(out_path)]
        proc = subprocess.run(cmd, input=text.encode("utf-8"), capture_output=True, check=True)

        if not out_path.exists() or out_path.stat().st_size == 0:
            err = proc.stderr.decode("utf-8", errors="ignore")
            raise RuntimeError(f"piper produced no audio. stderr: {err}")

        # Delete the temp file after the response is finished
        cleanup = BackgroundTask(lambda p=str(out_path): os.path.exists(p) and os.remove(p))
        return FileResponse(str(out_path), media_type="audio/wav", background=cleanup)

    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Piper failed (exit {e.returncode}). stderr: {e.stderr.decode('utf-8', errors='ignore')}"
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS error: {e}") from e

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

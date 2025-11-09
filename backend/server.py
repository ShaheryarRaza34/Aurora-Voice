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
CHUNK_SECONDS = 2.0                   # decode window for partials (increased)
CHUNK_SECONDS = 0.8
OVERLAP_SECONDS = 0.2
PARTIAL_EMIT_SEC = 0.35
FINAL_SILENCE_MS = 800

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
print(f"[INIT] Loading Whisper model: {ASR_MODEL_NAME} on {ASR_DEVICE} with {ASR_COMPUTE}")
model = WhisperModel(ASR_MODEL_NAME, device=ASR_DEVICE, compute_type=ASR_COMPUTE)
print("[INIT] Whisper model loaded successfully")

vad = webrtcvad.Vad(0)  # Changed from 2 to 0 (least aggressive)
print("[INIT] VAD initialized with aggressiveness level 0")


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
    await ws.accept()
    print("[WS] open")
    ring: Deque[float] = collections.deque(
        maxlen=int(SAMPLE_RATE * (CHUNK_SECONDS + OVERLAP_SECONDS) * 2)
    )
    last_emit = 0.0
    last_speech_time = time.time()
    have_text = False
    pending = b""
    byte_counter = 0
    seconds_logged = 0

    try:
        while True:
            chunk = await ws.receive_bytes()
            byte_counter += len(chunk)
            pending += chunk

            # log every ~1s of incoming audio (16k * 2 bytes)
            while byte_counter >= (SAMPLE_RATE * 2) * (seconds_logged + 1):
                seconds_logged += 1
                print(f"[WS] received ~{seconds_logged}s audio")

            # process in 20 ms steps
            while len(pending) >= FRAME_BYTES:
                frame = pending[:FRAME_BYTES]
                pending = pending[FRAME_BYTES:]

                # VAD - temporarily force speech detection for testing
                speech = True  # Force to True to bypass VAD issues
                try:
                    vad_result = is_speech(frame)
                    # Uncomment the line below to use actual VAD
                    # speech = vad_result
                    if seconds_logged % 5 == 0 and len(pending) == 0:  # Log occasionally
                        print(f"[VAD] Speech detected: {vad_result}")
                except Exception as e:
                    print(f"[VAD] Error: {e}")
                    pass

                if speech:
                    last_speech_time = time.time()

                # push into ring buffer
                ring.extend(bytes_to_float32(frame))

                # emit partials at cadence
                if (time.time() - last_emit) > PARTIAL_EMIT_SEC and len(ring) > SAMPLE_RATE * 1.0:
                    last_emit = time.time()
                    arr = np.array(ring)
                    n_ctx = int(SAMPLE_RATE * (CHUNK_SECONDS + OVERLAP_SECONDS))
                    window = arr[-n_ctx:] if arr.shape[0] > n_ctx else arr

                    # Only transcribe if we have at least 1 second of audio
                    if len(window) < SAMPLE_RATE:
                        print(f"[ASR] Skipping partial, buffer too small: {len(window)} samples")
                        continue

                    print(f"[ASR] Attempting partial transcription, window size: {len(window)} samples ({len(window)/SAMPLE_RATE:.2f}s)")
                    
                    # DEBUG: Check audio statistics
                    audio_max = np.max(np.abs(window))
                    audio_mean = np.mean(np.abs(window))
                    print(f"[ASR] Audio stats: max={audio_max:.6f}, mean={audio_mean:.6f}")
                    
                    if audio_max < 0.001:
                        print(f"[ASR] WARNING: Audio is too quiet (max={audio_max}), likely silent!")
                    
                    # Auto-gain: Boost quiet audio
                    if audio_max > 0.001 and audio_max < 0.2:
                        # Audio is too quiet, apply gain
                        target_level = 0.3
                        gain = target_level / audio_max
                        window = window * gain
                        new_max = np.max(np.abs(window))
                        print(f"[ASR] Applied auto-gain: {gain:.2f}x, new max={new_max:.6f}")

                    try:
                        segments, info = model.transcribe(
                            window,
                            language="en",  # Changed from None to "en"
                            beam_size=1,
                            vad_filter=False,
                            condition_on_previous_text=False,
                        )
                        partial = "".join(s.text for s in segments).strip()
                        print(f"[ASR] Partial result: '{partial}'")
                        if partial:
                            have_text = True
                            await ws.send_text(json.dumps({"type": "partial", "text": partial}))
                        else:
                            print("[ASR] No text in partial (empty result)")
                    except Exception as e:
                        print("[ASR] partial error:", e)
                        await ws.send_text(json.dumps({"type": "error", "message": str(e)}))

                # finalize on silence
                silence_duration = (time.time() - last_speech_time) * 1000
                if have_text and silence_duration > FINAL_SILENCE_MS:
                    arr = np.array(ring)
                    
                    # Only finalize if we have meaningful audio
                    if len(arr) < SAMPLE_RATE * 0.5:
                        print(f"[ASR] Skipping finalization, buffer too small: {len(arr)} samples")
                        ring.clear()
                        have_text = False
                        last_emit = time.time()
                        continue
                    
                    print(f"[ASR] Finalizing transcription after {silence_duration:.0f}ms silence, buffer size: {len(arr)} samples")
                    
                    # Check and boost audio if needed
                    audio_max = np.max(np.abs(arr))
                    if audio_max > 0.001 and audio_max < 0.2:
                        gain = 0.3 / audio_max
                        arr = arr * gain
                        print(f"[ASR] Final: Applied auto-gain {gain:.2f}x")
                    
                    try:
                        segments, info = model.transcribe(
                            arr,
                            language="en",  # Changed from None to "en"
                            beam_size=1,
                            vad_filter=False,
                            condition_on_previous_text=False,
                            word_timestamps=True,
                        )
                        final_text = "".join(s.text for s in segments).strip()
                        print(f"[ASR] Final result: '{final_text}'")
                        words = []
                        for s in segments:
                            if s.words:
                                for w in s.words:
                                    words.append({"word": w.word, "start": float(w.start), "end": float(w.end)})

                        await ws.send_text(json.dumps({"type": "final", "text": final_text, "ts": words}))
                    except Exception as e:
                        print("[ASR] final error:", e)
                        await ws.send_text(json.dumps({"type": "error", "message": str(e)}))
                    # reset
                    ring.clear()
                    have_text = False
                    last_emit = time.time()
                    print("[ASR] Reset buffer, ready for next utterance")
    except WebSocketDisconnect:
        print("[WS] disconnect")
        return
    except Exception as e:
        print("[WS] error:", e)
        try:
            await ws.send_text(json.dumps({"type": "error", "message": str(e)}))
        finally:
            await ws.close()
    finally:
        print("[WS] close")


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
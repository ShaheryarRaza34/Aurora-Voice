import os
import time
import json
import base64
import shutil
import uuid
import subprocess
import asyncio
from pathlib import Path
from tempfile import NamedTemporaryFile
from collections import deque
from typing import Deque

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from faster_whisper import WhisperModel
import webrtcvad
import uvicorn

from conversation_manager import ConversationManager
from dialog_manager import DialogManager

# =============================================================================
# CONFIGURATION
# =============================================================================
SAMPLE_RATE = 16000
FRAME_MS = 20  # WebRTC VAD requires 10, 20, or 30ms frames
FRAME_BYTES = int(SAMPLE_RATE * (FRAME_MS / 1000)) * 2  # 16-bit PCM = 2 bytes per sample

# ASR Config - OPTIMIZED FOR SPEED
ASR_MODEL_NAME = os.getenv("ASR_MODEL", "tiny.en")  # tiny.en for maximum speed (2-3x faster than base.en)
ASR_DEVICE = os.getenv("ASR_DEVICE", "cpu")
ASR_COMPUTE = os.getenv("ASR_COMPUTE", "int8")

# TTS Config
PIPER_BIN = shutil.which("piper") or "/usr/local/bin/piper"
PIPER_MODEL = os.getenv("PIPER_MODEL", "./models/en_US-amy-low.onnx")

# Voice Activity Detection - OPTIMIZED FOR SPEED
VAD_AGGRESSIVENESS = 1  # 0-3, higher = more aggressive filtering
BUFFER_DURATION_SEC = 30.0  # Keep 30 seconds of audio (enough for long queries)
MIN_FINAL_CHARS = 3  # Minimum characters for final transcription
IGNORED_PHRASES = {
    "thank you.", "thanks for watching.", "you", 
    "thank you for watching.", "thanks.", 
    "thank you very much.", "thank you so much.",
    "bye.", "goodbye.",
    ""  # Empty string
}

# =============================================================================
# INITIALIZE
# =============================================================================
app = FastAPI(title="Aurora Voice Assistant")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print(f"[INIT] Loading faster-whisper model: {ASR_MODEL_NAME}")
whisper_model = WhisperModel(
    ASR_MODEL_NAME,
    device=ASR_DEVICE,
    compute_type=ASR_COMPUTE,
    download_root=None,
    local_files_only=False
)
print(f"[INIT] faster-whisper model loaded")

vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)
print(f"[INIT] VAD initialized with aggressiveness={VAD_AGGRESSIVENESS}")

try:
    conversation_manager = ConversationManager()
    dialog_manager = DialogManager(conversation_manager)
    print(f"[INIT] Voice assistant components initialized")
except Exception as e:
    print(f"[INIT] ERROR initializing ConversationManager: {e}")
    import traceback
    traceback.print_exc()
    raise

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def bytes_to_float32(audio_bytes: bytes) -> np.ndarray:
    """Convert 16-bit PCM bytes to float32 array normalized to [-1, 1]"""
    int16_array = np.frombuffer(audio_bytes, dtype=np.int16)
    return int16_array.astype(np.float32) / 32768.0


def is_speech(frame_bytes: bytes) -> bool:
    """Check if audio frame contains speech using WebRTC VAD"""
    try:
        return vad.is_speech(frame_bytes, SAMPLE_RATE)
    except:
        return False


def transcribe_audio(audio_array: np.ndarray, beam_size: int = 1) -> str:
    """Transcribe audio array using faster-whisper - OPTIMIZED FOR SPEED"""
    if len(audio_array) < SAMPLE_RATE * 0.5:  # Need at least 500ms
        return ""
    
    # faster-whisper returns segments and info
    segments, info = whisper_model.transcribe(
        audio_array,
        task="transcribe",
        language="en",
        beam_size=beam_size,  # beam_size=1 for maximum speed
        condition_on_previous_text=False,
        temperature=0.0,
        vad_filter=False,  # We're already doing VAD
        log_prob_threshold=-1.0,
        no_speech_threshold=0.6
    )
    
    # Collect text from all segments
    text = " ".join([segment.text for segment in segments]).strip()
    return text


def generate_speech(text: str) -> bytes:
    """Generate speech using Piper TTS"""
    if not text.strip():
        return b""
    
    try:
        print(f"[TTS] Generating speech for: '{text[:50]}...'")
        
        with NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            output_path = tmp_file.name
        
        # Run Piper TTS
        result = subprocess.run(
            [PIPER_BIN, "--model", PIPER_MODEL, "--output_file", output_path],
            input=text,
            text=True,
            capture_output=True,
            timeout=30
        )
        
        if result.returncode != 0:
            print(f"[TTS] Error: {result.stderr}")
            return b""
        
        # Read generated audio
        audio_data = Path(output_path).read_bytes()
        Path(output_path).unlink()  # Clean up
        
        print(f"[TTS] Generated {len(audio_data)} bytes of audio")
        return audio_data
        
    except Exception as e:
        print(f"[TTS] Exception: {e}")
        return b""

# =============================================================================
# WEBSOCKET HANDLER
# =============================================================================

@app.websocket("/ws/assistant")
async def websocket_assistant(websocket: WebSocket):
    await websocket.accept()
    
    # Initialize with a temporary session_id (will be updated if client sends one)
    session_id = str(uuid.uuid4())
    session_id_received = False
    
    audio_queue = asyncio.Queue()
    stop_event = asyncio.Event()
    
    print(f"[WS] Session {session_id} connected (temporary, waiting for client session_id)")
    
    # Send ready signal immediately
    await websocket.send_text(json.dumps({
        "type": "ready",
        "session_id": session_id
    }))
    
    # --- TASK 1: RECEIVER (Non-blocking) ---
    async def receive_audio():
        """Receive audio data from client without blocking"""
        nonlocal session_id, session_id_received
        
        try:
            while not stop_event.is_set():
                # Receive either bytes (audio) or text (signals)
                message = await websocket.receive()
                
                if "bytes" in message:
                    # Audio data
                    data = message["bytes"]
                    await audio_queue.put(data)
                    
                elif "text" in message:
                    # Control signal or session_id
                    try:
                        msg_data = json.loads(message["text"])
                        # Handle session_id - update if we receive it
                        if msg_data.get("type") == "session_id" and msg_data.get("value"):
                            if not session_id_received:
                                old_session_id = session_id
                                session_id = msg_data["value"]
                                session_id_received = True
                                print(f"[WS] Updated session_id from {old_session_id} to persistent: {session_id}")
                            else:
                                print(f"[WS] Received session_id but already using: {session_id}")
                        elif msg_data.get("type") == "signal" and msg_data.get("value") == "end_of_speech":
                            print(f"[WS] Received end_of_speech signal")
                            await audio_queue.put("STOP_SIGNAL")  # Poison pill
                            break  # Stop receiving more data
                    except json.JSONDecodeError:
                        print(f"[WS] Invalid JSON in text message")
                        
        except WebSocketDisconnect:
            print(f"[WS] Session {session_id} disconnected")
            # Put stop signal in queue in case of unexpected disconnect
            try:
                await audio_queue.put("STOP_SIGNAL")
            except:
                pass
        except Exception as e:
            print(f"[WS] Receive error: {e}")
            try:
                await audio_queue.put("STOP_SIGNAL")
            except:
                pass
    
    # --- TASK 2: PROCESSOR (Simplified - only transcribe on stop) ---
    async def process_audio():
        """Process audio data - buffer until stop signal, then transcribe"""
        # State variables
        pending_bytes = b""
        max_buffer_samples = int(SAMPLE_RATE * BUFFER_DURATION_SEC)
        audio_buffer = deque(maxlen=max_buffer_samples)
        
        try:
            while True:  # Keep processing until STOP_SIGNAL
                # Get audio from queue with timeout to check stop_event periodically
                try:
                    data = await asyncio.wait_for(audio_queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    # Check if we should exit
                    if stop_event.is_set():
                        break
                    continue
                
                # Handle stop signal
                if data == "STOP_SIGNAL":
                    print(f"[WS] Received STOP_SIGNAL - transcribing entire audio buffer...")
                    
                    # Transcribe entire audio buffer
                    if len(audio_buffer) > 0:
                        audio_array = np.array(audio_buffer)
                        final_text = await asyncio.to_thread(transcribe_audio, audio_array, 1)
                        
                        print(f"[WS] Transcription result: '{final_text}' (len={len(final_text)})")
                        
                        # Process if valid
                        if final_text and len(final_text) >= MIN_FINAL_CHARS and final_text.lower() not in IGNORED_PHRASES:
                            try:
                                # Send final transcription
                                await websocket.send_text(json.dumps({
                                    "type": "final",
                                    "text": final_text
                                }))
                                
                                # Process with dialog manager
                                result = await asyncio.to_thread(dialog_manager.process_user_input, final_text, session_id)
                                response_text = result["response"]
                                
                                # Send response
                                await websocket.send_text(json.dumps({
                                    "type": "response",
                                    "text": response_text,
                                    "intent": result.get("intent", "unknown")
                                }))
                                
                                print(f"[WS] Response: '{response_text}'")
                                
                                # Generate and send TTS audio
                                audio_data = await asyncio.to_thread(generate_speech, response_text)
                                if audio_data:
                                    audio_b64 = base64.b64encode(audio_data).decode("utf-8")
                                    await websocket.send_text(json.dumps({
                                        "type": "audio",
                                        "data": audio_b64,
                                        "format": "wav"
                                    }))
                                    print(f"[WS] TTS audio sent ({len(audio_data)} bytes)")
                            except Exception as send_error:
                                print(f"[WS] Error processing request: {send_error}")
                                try:
                                    error_msg = f"Sorry, I encountered an error: {str(send_error)}"
                                    await websocket.send_text(json.dumps({
                                        "type": "response",
                                        "text": error_msg,
                                        "intent": "error"
                                    }))
                                except:
                                    pass
                        else:
                            print(f"[WS] Transcription too short or ignored: '{final_text}'")
                    
                    # Exit gracefully
                    break
                
                # Regular audio data - just buffer it
                pending_bytes += data
                
                # Process complete frames and add to buffer
                while len(pending_bytes) >= FRAME_BYTES:
                    frame = pending_bytes[:FRAME_BYTES]
                    pending_bytes = pending_bytes[FRAME_BYTES:]
                    
                    # Add to buffer (no VAD check needed, just buffer everything)
                    audio_buffer.extend(bytes_to_float32(frame))
        
        except Exception as e:
            print(f"[ERROR] Processing error: {e}")
        finally:
            print(f"[WS] Processing task completed for session {session_id}")
            stop_event.set()
    
    # Run both tasks concurrently
    await asyncio.gather(receive_audio(), process_audio())
    
    # Close WebSocket gracefully
    try:
        await websocket.close()
        print(f"[WS] Connection closed gracefully for session {session_id}")
    except Exception as e:
        print(f"[WS] Error closing connection: {e}")
    
    # Clean up session
    #conversation_manager.clear_session(session_id)


@app.get("/health")
async def health_check():
    return {"status": "ok", "model": ASR_MODEL_NAME}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

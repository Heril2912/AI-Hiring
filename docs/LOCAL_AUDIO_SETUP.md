# Local Audio Speech Runtime Setup (Phase 4D.3)

AI-Hiring Phase 4D.3 uses **100% local, free, open-source speech processing** for conversational audio interviews:
1. **Piper TTS**: Local neural text-to-speech for generating question audio.
2. **whisper.cpp STT**: Local quantized Whisper speech-to-text for transcribing candidate voice responses.
3. **FFmpeg**: Optional local audio converter for standardizing web audio payloads into 16kHz mono WAV format.

**Privacy & Zero Cloud Leakage**:
- No candidate voice recording or audio payload is ever sent to external cloud APIs or remote LLMs.
- All candidate voice uploads are processed in ephemeral local temp memory/directories and deleted immediately upon transcription completion.
- Candidate answers are persisted only as confirmed text transcripts.

---

## 1. Required Components

| Component | Purpose | Recommended Version |
| :--- | :--- | :--- |
| **whisper.cpp** | Local Speech-to-Text (`whisper-cli` or `main`) | v1.5.0+ |
| **Whisper Model** | Quantized model file (`ggml-small.en.bin` recommended, or `ggml-base.en.bin`) | GGML format |
| **Piper** | Local Text-to-Speech binary (`piper`) | v1.2.0+ |
| **Piper Voice Model** | ONNX voice model (`en_US-lessac-medium.onnx` + `.onnx.json`) | ONNX format |
| **FFmpeg** | Ephemeral audio conversion (`ffmpeg`) | v5.0+ |

---

## 2. macOS Manual Installation Instructions

### Option A: Homebrew & Pre-built Binaries (Recommended)
```bash
# 1. Install FFmpeg and whisper.cpp via Homebrew (optional / manual)
brew install ffmpeg whisper-cpp

# 2. Download Whisper GGML Model (small.en recommended for higher accuracy)
mkdir -p ~/.local/share/ai-hiring/models/whisper
curl -L -o ~/.local/share/ai-hiring/models/whisper/ggml-small.en.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en.bin

# 3. Download Piper binary and Voice Model
mkdir -p ~/.local/share/ai-hiring/bin ~/.local/share/ai-hiring/models/piper
# Download Piper for macOS (arm64 or x86_64) from Piper Releases:
# https://github.com/rhasspy/piper/releases
# Place executable at ~/.local/share/ai-hiring/bin/piper

# Download Piper English Voice:
curl -L -o ~/.local/share/ai-hiring/models/piper/en_US-lessac-medium.onnx \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
curl -L -o ~/.local/share/ai-hiring/models/piper/en_US-lessac-medium.onnx.json \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

---

## 3. Environment Configuration (`.env`)

Add or update the following variables in your root `.env` or `backend/.env`:

```env
# Local Speech Processing Paths (Phase 4D.3)
WHISPER_CPP_BIN=/opt/homebrew/bin/whisper-cli
WHISPER_CPP_MODEL=/Users/<your-username>/.local/share/ai-hiring/models/whisper/ggml-small.en.bin
PIPER_BIN=/Users/<your-username>/.local/share/ai-hiring/bin/piper
PIPER_MODEL=/Users/<your-username>/.local/share/ai-hiring/models/piper/en_US-lessac-medium.onnx
FFMPEG_BIN=/opt/homebrew/bin/ffmpeg

# Speech Processing Limits
AUDIO_MAX_SECONDS=120
AUDIO_MAX_UPLOAD_BYTES=10485760
AUDIO_PROCESSING_TIMEOUT_SECONDS=30.0
AUDIO_TTS_CACHE_DIR=backend/runtime/audio_tts_cache
AUDIO_EPHEMERAL_TEMP_DIR=backend/runtime/audio_temp
```

---

## 4. Non-Destructive Readiness Verification

To verify that your local environment is correctly configured without running full interviews:

1. Check system capability endpoint:
```bash
curl -s http://localhost:8000/api/v1/candidate/interviews/capabilities
```
Expected response when configured:
```json
{
  "speech_to_text_available": true,
  "text_to_speech_available": true,
  "microphone_required": true,
  "secure_context_required": true,
  "max_recording_seconds": 120,
  "max_upload_bytes": 10485760,
  "safe_unavailable_reason": null
}
```

2. If binaries or models are not yet configured or found at the specified paths:
```json
{
  "speech_to_text_available": false,
  "text_to_speech_available": false,
  "microphone_required": true,
  "secure_context_required": true,
  "max_recording_seconds": 120,
  "max_upload_bytes": 10485760,
  "safe_unavailable_reason": "Local speech processing runtime is not configured or available."
}
```

The application will fail safely and inform the candidate with clear, non-intrusive status badges on the Audio interview preparation view.

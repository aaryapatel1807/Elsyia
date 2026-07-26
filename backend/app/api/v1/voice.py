"""
Voice API Endpoints

Handles speech-to-text (transcription) and text-to-speech (synthesis)
for the push-to-talk voice pipeline.
"""

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.core import STTError, TTSError, get_logger, get_settings
from app.models import SpeakRequest, TranscribeResponse
from app.services.voice.factory import get_stt_provider, get_tts_provider

logger = get_logger("api.voice")
router = APIRouter()


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(audio: UploadFile) -> TranscribeResponse:
    """
    Transcribe an uploaded audio clip (push-to-talk recording) to text.

    Args:
        audio: Audio file upload. faster-whisper decodes via PyAV, so
            common browser recording formats (webm/opus, ogg, wav) all
            work without client-side conversion — see
            frontend/src/lib/voice.ts for what the Electron app sends.

    Returns:
        Transcribed text.
    """
    settings = get_settings()
    audio_bytes = await audio.read()

    logger.info(f"Voice API received: {len(audio_bytes)} bytes, content-type={audio.content_type}")

    try:
        stt = get_stt_provider(settings.DEFAULT_STT_PROVIDER)
        text = await stt.transcribe(audio_bytes)
    except STTError as e:
        logger.error(f"Transcription failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during transcription: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred")

    return TranscribeResponse(text=text)


@router.post("/speak")
async def speak(request: SpeakRequest) -> StreamingResponse:
    """
    Synthesize speech audio from text.

    Args:
        request: Text to speak.

    Returns:
        WAV audio stream.
    """
    settings = get_settings()

    try:
        tts = get_tts_provider(settings.DEFAULT_TTS_PROVIDER)

        async def generate():
            async for chunk in tts.synthesize(request.text):
                yield chunk

        return StreamingResponse(generate(), media_type="audio/wav")
    except TTSError as e:
        logger.error(f"Synthesis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during synthesis: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred")

"""
Speech Service for AI-Native Windows OS Assistant.
Handles Neural Text-to-Speech (Microsoft Edge-TTS) and spoken text normalization.
"""

import re
import io
import asyncio
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger("speech_service")
logger.setLevel(logging.INFO)

RECOMMENDED_NEURAL_VOICES = [
    {"id": "en-US-JennyNeural", "name": "Jenny (Natural US Female)", "lang": "en-US"},
    {"id": "en-US-GuyNeural", "name": "Guy (Natural US Male)", "lang": "en-US"},
    {"id": "en-US-AriaNeural", "name": "Aria (Expressive US Female)", "lang": "en-US"},
    {"id": "en-GB-SoniaNeural", "name": "Sonia (British Female)", "lang": "en-GB"},
    {"id": "en-IN-NeerjaNeural", "name": "Neerja (Indian English Female)", "lang": "en-IN"}
]


def normalize_for_speech(text: str) -> str:
    """
    Cleans raw assistant responses into smooth, natural human speech.
    Removes markdown formatting, code blocks, URLs, and JSON data.
    """
    if not text:
        return ""

    # Remove fenced code blocks
    cleaned = re.sub(r"```[\s\S]*?```", " Code snippet omitted for speech. ", text)
    # Remove inline backticks
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    # Remove URLs
    cleaned = re.sub(r"https?://\S+", " web link ", cleaned)
    # Remove markdown headers and bullets
    cleaned = re.sub(r"^[#*>-]+\s*", "", cleaned, flags=re.MULTILINE)
    # Remove bold / italic formatting
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
    # Remove JSON and bracket blocks
    cleaned = re.sub(r"\{[^{}]*\}", " ", cleaned)
    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Limit spoken length to ~3 concise sentences (max 300 chars)
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    if len(sentences) > 3:
        cleaned = " ".join(sentences[:3])

    return cleaned


class SpeechService:
    def __init__(self):
        self.default_voice = "en-US-JennyNeural"

    def filter_text_for_speech(self, text: str) -> str:
        return normalize_for_speech(text)

    async def generate_speech_audio(self, text: str, voice: Optional[str] = None) -> Optional[bytes]:
        """Synthesizes natural speech audio using Microsoft Edge-TTS."""
        spoken_text = self.filter_text_for_speech(text)
        if not spoken_text:
            return None

        target_voice = voice or self.default_voice
        try:
            import edge_tts
            communicate = edge_tts.Communicate(spoken_text, target_voice)
            audio_buffer = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_buffer.extend(chunk["data"])
            return bytes(audio_buffer)
        except Exception as e:
            logger.warning(f"Edge-TTS synthesis note: {e}")
            return None

    async def transcribe_audio(self, audio_bytes: bytes, mime_type: str = "audio/wav") -> Dict[str, Any]:
        """
        Transcribes speech audio into text using Google Gemini Multimodal Audio API.
        Enables seamless STT across all browsers, mobile remotes, and desktop sessions.
        """
        import base64
        import httpx
        from config import settings

        api_key = settings.effective_api_key
        if not api_key:
            return {"success": False, "error": "No API key configured for speech transcription.", "transcript": ""}

        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        candidates = ["gemini-3.1-flash-lite", "gemini-3-flash-preview", "gemini-flash-lite-latest", "gemini-flash-latest"]

        clean_mime = (mime_type or "audio/wav").split(";")[0].strip().lower()
        if clean_mime in ["audio/x-wav", "audio/wave"]:
            clean_mime = "audio/wav"
        elif clean_mime in ["audio/mpeg", "audio/mp3"]:
            clean_mime = "audio/mp3"

        payload = {
            "contents": [{
                "parts": [
                    {"text": "Transcribe the spoken speech in this audio recording word for word into a concise user prompt. Return ONLY the transcribed text. If the audio is silent or contains no intelligible speech, return an empty string."},
                    {"inlineData": {"mimeType": clean_mime, "data": audio_b64}}
                ]
            }],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 1000}
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            for model in candidates:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                try:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        cands = data.get("candidates", [])
                        if cands:
                            parts = cands[0].get("content", {}).get("parts", [])
                            text = "".join(p.get("text", "") for p in parts).strip()
                            if text.upper() in ["SILENCE", "SILENT", "NO SPEECH", "NO SPEECH DETECTED"]:
                                text = ""
                            return {"success": True, "transcript": text, "model": model}
                except Exception as e:
                    logger.warning(f"Audio transcription attempt with {model} failed: {e}")
                    continue

        return {"success": False, "error": "Audio transcription unavailable.", "transcript": ""}


speech_service = SpeechService()

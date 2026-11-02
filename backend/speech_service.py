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


speech_service = SpeechService()

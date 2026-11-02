"""
Configuration and Environment Settings for AI-Native Windows OS Assistant.
Default Option A: Google Gemini 2.0 Flash / Groq (Zero-Setup Free Cloud API).
"""

import os
import secrets
from pathlib import Path
from typing import Optional, Dict, Any

# Root paths
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
ENV_PATH = BACKEND_DIR / ".env"
DATA_DIR = BACKEND_DIR / "data"
SCRATCH_DIR = PROJECT_ROOT / "scratch"
BACKUPS_DIR = SCRATCH_DIR / ".file_backups"
OUTPUT_DOCS_DIR = PROJECT_ROOT / "generated_documents"

DATA_DIR.mkdir(parents=True, exist_ok=True)
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DOCS_DIR.mkdir(parents=True, exist_ok=True)

# Load environment variables
from dotenv import load_dotenv
load_dotenv(dotenv_path=ENV_PATH)


class Settings:
    # Server network bindings
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    # Option A: Free Cloud Providers (Google Gemini & Groq)
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini").lower()
    
    # API Keys (Stored locally in backend/.env, never exposed to clients)
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # Selected Models
    # Primary: gemini-2.0-flash (Sub-second speed, 1M token context, native multimodal vision, 100% free)
    # Fallback: llama-3.3-70b-versatile on Groq (300+ tok/s)
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-2.0-flash")
    LLM_VISION_MODEL: str = os.getenv("LLM_VISION_MODEL", "gemini-2.0-flash")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "")

    # Security & Mobile LAN Pairing
    REMOTE_PAIRING_PIN: str = os.getenv("REMOTE_PAIRING_PIN", "4826")
    REMOTE_AUTH_TOKEN: str = os.getenv("REMOTE_AUTH_TOKEN", "nexus_remote_auth_token_safe_99")
    
    # Phone Screen Mirror Streaming Defaults
    STREAM_FPS: int = int(os.getenv("STREAM_FPS", "15"))
    STREAM_QUALITY: int = int(os.getenv("STREAM_QUALITY", "75"))
    STREAM_SCALE: float = float(os.getenv("STREAM_SCALE", "0.75"))

    # Speech Services (Edge-TTS & Whisper)
    TTS_PROVIDER: str = os.getenv("TTS_PROVIDER", "edge_tts")
    DEFAULT_VOICE: str = os.getenv("DEFAULT_VOICE", "en-US-JennyNeural")
    VOICE_SPEED: float = float(os.getenv("VOICE_SPEED", "1.0"))
    STT_PROVIDER: str = os.getenv("STT_PROVIDER", "browser")

    @property
    def effective_api_key(self) -> str:
        """Returns the active provider key based on current provider."""
        if self.LLM_PROVIDER == "gemini":
            return self.GEMINI_API_KEY or os.getenv("GOOGLE_API_KEY", "")
        elif self.LLM_PROVIDER == "groq":
            return self.GROQ_API_KEY
        elif self.LLM_PROVIDER == "openai":
            return self.OPENAI_API_KEY
        return self.GEMINI_API_KEY or self.GROQ_API_KEY or self.OPENAI_API_KEY

    @property
    def effective_base_url(self) -> str:
        """Resolves OpenAI-compatible base URL for the active provider."""
        if self.LLM_BASE_URL:
            return self.LLM_BASE_URL
        if self.LLM_PROVIDER == "gemini":
            # Google AI Studio OpenAI-compatible endpoint
            return "https://generativelanguage.googleapis.com/v1beta/openai/"
        elif self.LLM_PROVIDER == "groq":
            return "https://api.groq.com/openai/v1"
        elif self.LLM_PROVIDER == "openai":
            return "https://api.openai.com/v1"
        return "https://generativelanguage.googleapis.com/v1beta/openai/"


settings = Settings()


def mask_key(key: Optional[str]) -> str:
    """Masks secret keys for safe display in UI and logs."""
    if not key or len(key) < 8:
        return "Not Configured"
    return f"{key[:4]}...{key[-4:]}"


def update_env(key_values: Dict[str, Any]) -> bool:
    """Updates key-value pairs in backend/.env file cleanly."""
    lines = []
    existing_keys = set()
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

    updated_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k, v = stripped.split("=", 1)
            k = k.strip()
            if k in key_values:
                updated_lines.append(f"{k}={key_values[k]}\n")
                existing_keys.add(k)
                continue
        updated_lines.append(line)

    for k, v in key_values.items():
        if k not in existing_keys:
            updated_lines.append(f"{k}={v}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(updated_lines)

    # Reload into settings
    load_dotenv(dotenv_path=ENV_PATH, override=True)
    for k, v in key_values.items():
        if hasattr(settings, k):
            setattr(settings, k, v)
    return True

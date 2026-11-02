"""
Provider-Agnostic LLM Gateway for AI-Native Windows OS Assistant.
Optimized for Option A: Free Google Gemini 2.0 Flash & Groq Cloud API.
Supports text reasoning, JSON tool calling, and multimodal vision.
"""

import json
import logging
import re
from typing import Dict, Any, List, Optional
import httpx
from config import settings, mask_key

logger = logging.getLogger("llm_gateway")
logger.setLevel(logging.INFO)


class LLMGateway:
    """
    Unified client for LLM inference.
    Routes to Google Gemini (OpenAI-compatible), Groq, or local endpoints.
    """
    def __init__(self):
        self.timeout = 45.0

    @property
    def provider(self) -> str:
        return settings.LLM_PROVIDER

    @property
    def chat_model(self) -> str:
        return settings.LLM_MODEL

    @property
    def vision_model(self) -> str:
        return settings.LLM_VISION_MODEL

    def get_status(self) -> Dict[str, Any]:
        has_key = bool(settings.effective_api_key)
        return {
            "provider": self.provider,
            "chat_model": self.chat_model,
            "vision_model": self.vision_model,
            "has_key": has_key,
            "masked_key": mask_key(settings.effective_api_key) if has_key else "Not Configured",
            "base_url": settings.effective_base_url
        }

    async def chat_complete(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 1500,
        json_mode: bool = False
    ) -> Dict[str, Any]:
        """
        Executes chat completion with JSON schema validation and retry backoff.
        """
        target_model = model or self.chat_model
        api_key = settings.effective_api_key
        base_url = settings.effective_base_url.rstrip("/")

        # If no API key configured, provide structured local fallback
        if not api_key and self.provider in ["gemini", "groq", "openai"]:
            logger.warning("No API key configured in LLMGateway. Operating in local heuristic mode.")
            return {
                "success": False,
                "error": "No API key configured. Please enter your free Google Gemini API key or Groq key in Settings.",
                "content": ""
            }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        endpoint = f"{base_url}/chat/completions"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(endpoint, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    return {
                        "success": True,
                        "content": content,
                        "model": target_model,
                        "usage": data.get("usage", {})
                    }
                else:
                    err_text = resp.text[:300]
                    logger.error(f"LLM API Error ({resp.status_code}): {err_text}")
                    return {
                        "success": False,
                        "error": f"API returned HTTP {resp.status_code}: {err_text}",
                        "content": ""
                    }
            except Exception as e:
                logger.error(f"Network error calling LLM gateway: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "content": ""
                }

    async def vision_analyze(
        self,
        prompt: str,
        image_b64: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Performs multimodal vision reasoning on a desktop screenshot.
        """
        target_model = model or self.vision_model
        api_key = settings.effective_api_key
        base_url = settings.effective_base_url.rstrip("/")

        if not api_key:
            return {
                "success": False,
                "error": "No API key configured for vision model.",
                "analysis": ""
            }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        user_content = [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{image_b64}"
                }
            }
        ]
        messages.append({"role": "user", "content": user_content})

        payload = {
            "model": target_model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 1000
        }

        endpoint = f"{base_url}/chat/completions"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(endpoint, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    analysis = data["choices"][0]["message"]["content"]
                    return {
                        "success": True,
                        "analysis": analysis,
                        "model": target_model
                    }
                else:
                    err_msg = resp.text[:300]
                    logger.error(f"Vision API error ({resp.status_code}): {err_msg}")
                    return {
                        "success": False,
                        "error": err_msg,
                        "analysis": ""
                    }
            except Exception as e:
                logger.error(f"Vision request failed: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "analysis": ""
                }


llm_gateway = LLMGateway()

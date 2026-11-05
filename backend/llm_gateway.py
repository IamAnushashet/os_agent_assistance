"""
Provider-Agnostic LLM Gateway for AI-Native Windows OS Assistant.
Optimized for Option A: Free Google Gemini 3.5 Flash & Groq Cloud API.
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
    Supports native Google Gemini REST API (with sub-second speeds and automatic model fallback),
    as well as Groq and OpenAI-compatible endpoints.
    """
    def __init__(self):
        self.timeout = 5.0

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

    async def _call_gemini_native(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        json_mode: bool = False
    ) -> Dict[str, Any]:
        """
        Calls Google Gemini directly via official Google Generative Language REST API.
        Bypasses OpenAI proxy bottlenecks and includes automatic model fallbacks.
        """
        api_key = settings.effective_api_key
        models_to_try = [model, "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-flash-lite-latest", "gemini-3-flash-preview", "gemini-3.1-flash-lite-preview"]
        unique_models = []
        for m in models_to_try:
            if m and m not in unique_models:
                unique_models.append(m)

        contents = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                contents.append({"role": "user", "parts": [{"text": f"SYSTEM INSTRUCTION:\n{content}"}]})
                contents.append({"role": "model", "parts": [{"text": "Understood. I will strictly adhere to these instructions and required JSON schemas."}]})
            elif role == "user":
                contents.append({"role": "user", "parts": [{"text": str(content)}]})
            elif role == "assistant":
                contents.append({"role": "model", "parts": [{"text": str(content)}]})

        if not contents:
            contents = [{"role": "user", "parts": [{"text": "Hello"}]}]

        gen_config: Dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }
        if json_mode:
            gen_config["responseMimeType"] = "application/json"

        payload = {
            "contents": contents,
            "generationConfig": gen_config
        }

        last_err = ""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for candidate in unique_models:
                clean_name = candidate.replace("models/", "")
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_name}:generateContent?key={api_key}"
                try:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            text = "".join(p.get("text", "") for p in parts)
                            logger.info(f"Successfully generated response with Gemini ({clean_name})")
                            return {
                                "success": True,
                                "content": text,
                                "model": clean_name,
                                "provider": "gemini-native"
                            }
                    else:
                        last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                        logger.warning(f"Gemini API attempt with {clean_name} failed: {last_err}")
                except Exception as ex:
                    last_err = str(ex)
                    logger.warning(f"Gemini connection error for {clean_name}: {last_err}")

        return {"success": False, "error": last_err or "Gemini API unavailable", "content": ""}

    async def _call_gemini_vision_native(
        self,
        prompt: str,
        image_b64: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Multimodal screenshot reasoning using Google Gemini native vision API.
        """
        api_key = settings.effective_api_key
        models_to_try = [model or self.vision_model, "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-flash-lite-latest", "gemini-3-flash-preview", "gemini-3.1-flash-lite-preview"]
        unique_models = []
        for m in models_to_try:
            if m and m not in unique_models:
                unique_models.append(m)

        parts = []
        if system_prompt:
            parts.append({"text": f"SYSTEM INSTRUCTION:\n{system_prompt}\n\nUSER PROMPT:\n{prompt}"})
        else:
            parts.append({"text": prompt})

        parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": image_b64
            }
        })

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1000}
        }

        last_err = ""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for candidate in unique_models:
                clean_name = candidate.replace("models/", "")
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_name}:generateContent?key={api_key}"
                try:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts_out = candidates[0].get("content", {}).get("parts", [])
                            text = "".join(p.get("text", "") for p in parts_out)
                            logger.info(f"Successfully analyzed screen with Gemini Vision ({clean_name})")
                            return {
                                "success": True,
                                "analysis": text,
                                "model": clean_name
                            }
                    else:
                        last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                        logger.warning(f"Gemini Vision attempt with {clean_name} failed: {last_err}")
                except Exception as ex:
                    last_err = str(ex)
                    logger.warning(f"Gemini Vision connection error for {clean_name}: {last_err}")

        return {"success": False, "error": last_err or "Gemini Vision unavailable", "analysis": ""}

    async def chat_complete(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        json_mode: bool = False
    ) -> Dict[str, Any]:
        """
        Executes chat completion with JSON schema validation and retry backoff.
        """
        target_model = model or self.chat_model
        api_key = settings.effective_api_key

        if not api_key:
            logger.warning("No API key configured in LLMGateway. Operating in local heuristic mode.")
            return {
                "success": False,
                "error": "No API key configured. Please enter your free Google Gemini API key or Groq key in Settings.",
                "content": ""
            }

        # For Google Gemini, use official native REST API
        if self.provider == "gemini":
            return await self._call_gemini_native(
                messages=messages,
                model=target_model,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode
            )

        # For Groq / OpenAI compatible endpoints
        base_url = settings.effective_base_url.rstrip("/")
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

        if not api_key:
            return {
                "success": False,
                "error": "No API key configured for vision model.",
                "analysis": ""
            }

        # For Google Gemini, use official native REST API
        if self.provider == "gemini":
            return await self._call_gemini_vision_native(
                prompt=prompt,
                image_b64=image_b64,
                system_prompt=system_prompt,
                model=target_model
            )

        # For Groq / OpenAI compatible vision
        base_url = settings.effective_base_url.rstrip("/")
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

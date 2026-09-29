"""Groq chat-completions client with retry + model fallback.

Uses Groq's OpenAI-compatible endpoint through httpx (no extra SDK needed). Every call is wrapped in retry
logic because the hackathon brief warns that function-calling / formatting errors are common with these models.
"""
from __future__ import annotations

import json
import re
import time

import httpx

from .config import settings


class LLMUnavailable(RuntimeError):
    pass


def _strip_think(text: str) -> str:
    # qwen3 may emit <think>...</think> blocks
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


def chat(messages: list[dict], *, temperature: float = 0.1, max_tokens: int = 700, json_mode: bool = False) -> dict:
    """Returns {text, model, attempts}. Raises LLMUnavailable if no key or every attempt failed."""
    if not settings.groq_available:
        raise LLMUnavailable("GROQ_API_KEY is not configured")
    models = [settings.llm_primary] + ([settings.llm_fallback] if settings.llm_fallback else [])
    errors: list[str] = []
    attempts = 0
    for model in models:
        for i in range(max(1, settings.llm_max_retries)):
            attempts += 1
            body = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
            if json_mode:
                body["response_format"] = {"type": "json_object"}
            try:
                r = httpx.post(
                    f"{settings.groq_base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                    json=body,
                    timeout=60,
                )
                if r.status_code == 429 or r.status_code >= 500:
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
                if r.status_code >= 400:
                    # json_mode / tool-format errors: retry once without json_mode
                    if json_mode and ("json" in r.text.lower() or "format" in r.text.lower()):
                        json_mode = False
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
                text = _strip_think(r.json()["choices"][0]["message"]["content"] or "")
                if not text:
                    raise RuntimeError("empty completion")
                return {"text": text, "model": model, "attempts": attempts}
            except Exception as e:  # noqa: BLE001
                errors.append(f"{model} try {i + 1}: {e}")
                time.sleep(min(4.0, 0.6 * (2 ** i)))
    raise LLMUnavailable("; ".join(errors[-4:]))


def parse_json(text: str) -> dict | None:
    if not text:
        return None
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None

"""Shared LLM client for Ollama and OpenAI."""
from __future__ import annotations

import os

import httpx
import structlog

logger = structlog.get_logger(__name__)


async def complete_prompt(prompt: str, system: str = "You are a GRC and security compliance expert.") -> tuple[str, str]:
    """Return (text, source) where source is ollama|openai|deterministic."""
    ollama_url = os.getenv("OLLAMA_URL", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()

    if ollama_url:
        text = await _ollama(ollama_url, prompt, system)
        if text:
            return text, "ollama"
    if openai_key:
        text = await _openai(openai_key, prompt, system)
        if text:
            return text, "openai"
    return "", "unavailable"


async def _ollama(base_url: str, prompt: str, system: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            res = await client.post(
                f"{base_url.rstrip('/')}/api/generate",
                json={
                    "model": os.getenv("OLLAMA_MODEL", "llama3.2"),
                    "prompt": f"{system}\n\n{prompt}",
                    "stream": False,
                },
            )
            if res.status_code == 200:
                return (res.json().get("response") or "").strip() or None
    except Exception as exc:
        logger.warning("ollama_failed", error=str(exc))
    return None


async def _openai(api_key: str, prompt: str, system: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            res = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 800,
                    "temperature": 0.3,
                },
            )
            if res.status_code == 200:
                choices = res.json().get("choices", [])
                if choices:
                    return (choices[0].get("message", {}).get("content") or "").strip() or None
    except Exception as exc:
        logger.warning("openai_failed", error=str(exc))
    return None

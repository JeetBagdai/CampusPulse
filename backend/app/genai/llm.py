"""Thin async Groq client (OpenAI-compatible) with model fallback and caching.

Groq rate limits are per model, so falling back to the next model keeps the
demo alive if one model hits its limit.
"""
import hashlib
import json
import re

import httpx

from ..config import GROQ_API_KEY, GROQ_TEXT_MODELS, GROQ_VISION_MODELS

URL = "https://api.groq.com/openai/v1/chat/completions"
_cache: dict[str, dict] = {}
_client: httpx.AsyncClient | None = None


class LLMError(Exception):
    pass


def available() -> bool:
    return bool(GROQ_API_KEY)


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=45, headers={"Authorization": f"Bearer {GROQ_API_KEY}"})
    return _client


def _strip(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()


async def chat(messages: list[dict], *, json_mode: bool = False, tools: list | None = None,
               vision: bool = False, temperature: float = 0.2, max_tokens: int = 1500,
               use_cache: bool = True) -> dict:
    """Returns the assistant message dict ({content, tool_calls?}). Raises LLMError."""
    if not available():
        raise LLMError("GROQ_API_KEY not set")
    models = GROQ_VISION_MODELS if vision else GROQ_TEXT_MODELS
    key = None
    if use_cache and not tools:
        key = hashlib.sha256(json.dumps([messages, json_mode, models], sort_keys=True, default=str).encode()).hexdigest()
        if key in _cache:
            return _cache[key]
    last = "no model tried"
    for model in models:
        body = {"model": model, "messages": messages, "temperature": temperature, "max_completion_tokens": max_tokens}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if tools:
            body["tools"], body["tool_choice"] = tools, "auto"
        if model.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = "low"
        try:
            r = await _http().post(URL, json=body)
        except httpx.HTTPError as e:
            last = f"{model}: {type(e).__name__}"
            continue
        if r.status_code != 200:
            last = f"{model}: HTTP {r.status_code} {r.text[:160]}"
            continue
        msg = r.json()["choices"][0]["message"]
        msg["content"] = _strip(msg.get("content") or "")
        msg["model"] = model
        if key:
            _cache[key] = msg
        return msg
    raise LLMError(last)


async def chat_json(messages: list[dict], **kw) -> dict:
    msg = await chat(messages, json_mode=True, **kw)
    try:
        return json.loads(msg["content"])
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", msg["content"], re.S)
        if not m:
            raise LLMError("model did not return JSON")
        return json.loads(m.group(0))

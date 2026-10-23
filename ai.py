"""
Асинхронный клиент нейросети поверх aiohttp.
Работает с OpenRouter (если в .env есть OPENROUTER_API_KEY) или с Mistral.
Оба API OpenAI-совместимые, поэтому код общий.
"""
import asyncio
import json
import logging
import os
import re

import aiohttp

from config import AI_MODEL, AI_PROVIDER, AI_VISION_MODEL, MISTRAL_API_KEY, OPENROUTER_API_KEY

log = logging.getLogger("ai")

if AI_PROVIDER == "openrouter":
    API_URL = "https://openrouter.ai/api/v1/chat/completions"
    API_KEY = OPENROUTER_API_KEY
    EXTRA_HEADERS = {"HTTP-Referer": "https://t.me/NYVA_bot", "X-Title": "NYVA bot"}
else:
    API_URL = "https://api.mistral.ai/v1/chat/completions"
    API_KEY = MISTRAL_API_KEY
    EXTRA_HEADERS = {}

TEXT_MODEL = AI_MODEL
MIN_TOKENS = 1000 if AI_PROVIDER == "openrouter" else 0  # «думающим» моделям нужен запас, длину держит промпт

_session: aiohttp.ClientSession | None = None


class AIError(Exception):
    pass


async def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=90), trust_env=True)
    return _session


async def close() -> None:
    if _session and not _session.closed:
        await _session.close()


def clean(text: str) -> str:
    """Убираем markdown-звёздочки и случайные «мысли» модели."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    return text.replace("**", "").replace("__", "").strip()


FALLBACK_MODELS = [m.strip() for m in os.getenv(
    "AI_FALLBACK_MODELS", "xingchen-agi/xing4.0-29b-a4b:free,recursive/flint-v1.0:free").split(",") if m.strip()]


async def _post(payload: dict) -> tuple[int, dict]:
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json", **EXTRA_HEADERS}
    session = await _get_session()
    async with session.post(API_URL, json=payload, headers=headers) as resp:
        return resp.status, await resp.json(content_type=None)


async def chat(messages: list, *, model: str | None = None, temperature: float = 0.8,
               top_p: float = 0.95, max_tokens: int = 300, json_mode: bool = False, **extra) -> str:
    payload = {
        "model": model or TEXT_MODEL,
        "messages": messages,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max(max_tokens, MIN_TOKENS),
    }
    for key in ("frequency_penalty", "presence_penalty"):
        if key in extra:
            payload[key] = extra[key]
    if AI_PROVIDER == "openrouter":
        # рассуждения выключаем: так быстрее и модель не съедает весь лимит на «мысли»
        payload["reasoning"] = {"enabled": False}
        fallbacks = [m for m in FALLBACK_MODELS if m != payload["model"]]
        if fallbacks:
            payload["models"] = [payload["model"], *fallbacks][:3]
    elif json_mode:
        payload["response_format"] = {"type": "json_object"}

    last_error = None
    for attempt in range(4):
        try:
            status, data = await _post(payload)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            last_error = repr(e)
            await asyncio.sleep(3 * (attempt + 1))
            continue

        if status == 429 or status >= 500:
            last_error = f"HTTP {status}: {str(data)[:300]}"
            await asyncio.sleep(3 * (attempt + 1))
            continue
        if status == 400 and "reasoning" in str(data).lower() and "reasoning" in payload:
            # модель не умеет выключать рассуждения — разрешаем, но с запасом токенов и скрытыми «мыслями»
            payload["reasoning"] = {"effort": "low", "exclude": True}
            payload["max_tokens"] = max(payload["max_tokens"], 4000)
            last_error = f"HTTP 400: {str(data)[:300]}"
            continue
        if status != 200 or "choices" not in data:
            raise AIError(f"{AI_PROVIDER} {status}: {str(data)[:500]}")

        choice = data["choices"][0]
        content = choice.get("message", {}).get("content") or ""
        if isinstance(content, list):
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        content = clean(content)
        if content:
            return content

        # пустой ответ: модель всё равно «думала» и упёрлась в лимит — даём больше токенов
        last_error = f"пустой ответ (finish_reason={choice.get('finish_reason')}, model={data.get('model')})"
        log.warning(last_error)
        payload["reasoning"] = {"effort": "low", "exclude": True} if AI_PROVIDER == "openrouter" else None
        if payload["reasoning"] is None:
            payload.pop("reasoning")
        payload["max_tokens"] = max(payload["max_tokens"] * 3, 4000)
    raise AIError(f"{AI_PROVIDER} не ответил: {last_error}")


async def chat_json(messages: list, **kwargs) -> dict:
    messages = list(messages)
    messages[-1] = {**messages[-1], "content": str(messages[-1]["content"]) +
                    "\n\nОтветь СТРОГО одним JSON-объектом, без пояснений и без ```."}
    text = await chat(messages, json_mode=True, **kwargs)
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            return json.loads(match.group(0))
        raise AIError(f"Не JSON: {text[:200]}")


async def vision(system_prompt: str, question: str, image_b64: str, max_tokens: int = 250,
                 temperature: float = 0.8) -> str:
    data_url = f"data:image/jpeg;base64,{image_b64}"
    image_part = ({"type": "image_url", "image_url": {"url": data_url}} if AI_PROVIDER == "openrouter"
                  else {"type": "image_url", "image_url": data_url})
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": [{"type": "text", "text": question}, image_part]},
    ]
    return await chat(messages, model=AI_VISION_MODEL, max_tokens=max_tokens, temperature=temperature)

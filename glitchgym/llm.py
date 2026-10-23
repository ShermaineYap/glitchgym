"""Thin LLM client: Gemini (Google AI Studio) first, Groq as fallback.

Uses plain REST calls so there are no SDK version surprises on deploy day.
Every call asks for JSON and is parsed defensively.
"""

from __future__ import annotations

import json
import os
import re
import time

import requests

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

DEFAULT_GEMINI_MODELS = ["gemini-flash-latest", "gemini-2.5-flash"]
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


class LLMError(RuntimeError):
    pass


def _secret(name: str) -> str | None:
    val = os.environ.get(name)
    if val:
        return val.strip()
    try:  # Streamlit Cloud secrets
        import streamlit as st
        if name in st.secrets:
            return str(st.secrets[name]).strip()
    except Exception:
        pass
    return None


def available() -> dict[str, bool]:
    return {"gemini": bool(_secret("GEMINI_API_KEY")), "groq": bool(_secret("GROQ_API_KEY"))}


def any_available() -> bool:
    return any(available().values())


def parse_json(text: str) -> dict:
    """Parse JSON from a model reply, tolerating ```json fences and chatter."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _gemini(system: str, user: str, temperature: float, timeout: float) -> tuple[str, str]:
    key = _secret("GEMINI_API_KEY")
    models = [m for m in [_secret("GEMINI_MODEL")] if m] + DEFAULT_GEMINI_MODELS
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }
    last = None
    for model in dict.fromkeys(models):
        resp = requests.post(
            GEMINI_URL.format(model=model),
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            json=body,
            timeout=timeout,
        )
        if resp.status_code == 404:  # model name not available on this key
            last = f"{model}: 404"
            continue
        if resp.status_code != 200:
            raise LLMError(f"Gemini {model} HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        try:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts), f"Gemini ({model})"
        except (KeyError, IndexError):
            raise LLMError(f"Gemini returned no text: {str(data)[:300]}")
    raise LLMError(f"No Gemini model available ({last})")


def _groq(system: str, user: str, temperature: float, timeout: float) -> tuple[str, str]:
    key = _secret("GROQ_API_KEY")
    model = _secret("GROQ_MODEL") or DEFAULT_GROQ_MODEL
    resp = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        },
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise LLMError(f"Groq HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json()["choices"][0]["message"]["content"], f"Groq ({model})"


def ask_json(system: str, user: str, temperature: float = 0.4, timeout: float = 45) -> tuple[dict, str]:
    """Return (parsed_json, provider_label). Tries Gemini, then Groq."""
    errors = []
    providers = []
    if _secret("GEMINI_API_KEY"):
        providers.append(_gemini)
    if _secret("GROQ_API_KEY"):
        providers.append(_groq)
    if not providers:
        raise LLMError("No API key configured (set GEMINI_API_KEY or GROQ_API_KEY).")
    for fn in providers:
        for attempt in range(2):
            try:
                text, label = fn(system, user, temperature, timeout)
                return parse_json(text), label
            except (LLMError, requests.RequestException, json.JSONDecodeError, KeyError) as e:
                errors.append(f"{fn.__name__}: {e}")
                if "429" in str(e) and attempt == 0:
                    time.sleep(2)
                    continue
                break
    raise LLMError(" | ".join(errors))

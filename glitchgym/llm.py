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

# Fast models first; each one that is slow, overloaded or unavailable falls through to the next.
DEFAULT_GEMINI_MODELS = ["gemini-flash-lite-latest", "gemini-flash-latest"]
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


def _thinking(model: str) -> dict:
    """Keep 'thinking' minimal: these are short, well-specified JSON tasks and the
    sandbox verifies the output anyway, so speed matters more than deliberation."""
    if "2.5" in model or "2.0" in model:
        return {"thinkingBudget": 0}
    return {"thinkingLevel": "low"}


def _post_gemini(model: str, key: str, body: dict, timeout: float) -> requests.Response:
    return requests.post(
        GEMINI_URL.format(model=model),
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        json=body,
        timeout=timeout,
    )


def gemini_models() -> list[str]:
    return list(dict.fromkeys([m for m in [_secret("GEMINI_MODEL")] if m] + DEFAULT_GEMINI_MODELS))


def _gemini_one(model: str, key: str, system: str, user: str, temperature: float, timeout: float) -> str:
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json",
                             "thinkingConfig": _thinking(model)},
    }
    resp = _post_gemini(model, key, body, timeout)
    if resp.status_code == 400 and "thinking" in resp.text.lower():
        # This model doesn't accept that thinking setting: retry with its defaults.
        body["generationConfig"].pop("thinkingConfig", None)
        resp = _post_gemini(model, key, body, timeout)
    if resp.status_code != 200:
        raise LLMError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts if not p.get("thought"))
    except (KeyError, IndexError):
        raise LLMError(f"no text: {str(data)[:200]}")


def _gemini(system: str, user: str, temperature: float, timeout: float) -> tuple[str, str]:
    """Try each model in turn; a slow, overloaded or missing model falls through to the next."""
    key = _secret("GEMINI_API_KEY")
    errors = []
    for model in gemini_models():
        try:
            return _gemini_one(model, key, system, user, temperature, timeout), f"Gemini ({model})"
        except requests.Timeout:
            errors.append(f"{model}: timed out after {timeout:.0f}s")
        except (LLMError, requests.RequestException) as e:
            errors.append(f"{model}: {str(e)[:160]}")
    raise LLMError("; ".join(errors))


def health_check() -> list[dict]:
    """Time a tiny JSON request against every configured Gemini model."""
    key = _secret("GEMINI_API_KEY")
    out = []
    if not key:
        return [{"model": "-", "ok": False, "seconds": 0, "detail": "GEMINI_API_KEY not set"}]
    for model in gemini_models():
        t0 = time.time()
        try:
            text = _gemini_one(model, key, "Reply with JSON only.", 'Return {"ok": true}', 0.0, 30)
            out.append({"model": model, "ok": True, "seconds": round(time.time() - t0, 1), "detail": text[:60]})
        except Exception as e:
            out.append({"model": model, "ok": False, "seconds": round(time.time() - t0, 1), "detail": str(e)[:160]})
    return out


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


def ask_json(system: str, user: str, temperature: float = 0.4, timeout: float = 30) -> tuple[dict, str]:
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
        try:
            text, label = fn(system, user, temperature, timeout)
            return parse_json(text), label
        except (LLMError, requests.RequestException, json.JSONDecodeError, KeyError) as e:
            errors.append(f"{fn.__name__}: {e}")
    raise LLMError(" | ".join(errors))

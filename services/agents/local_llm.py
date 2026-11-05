"""A language model on this machine (Ollama), for the agents that write text.

Nothing leaves the computer, no key is needed, and every caller works without it: `chat_json` answers None when the model is switched off,
not running or too slow, and the caller keeps its own wording. What the model answers is treated as data, never as instructions.
Switches: LOCAL_LLM=0 turns it off, OLLAMA_URL, LOCAL_LLM_MODEL and LOCAL_LLM_TIMEOUT (seconds) change where it is, which one, and how long to wait.
"""
import json
import os

import httpx


def url() -> str:
    return os.environ.get("OLLAMA_URL", "http://localhost:11434")


def model() -> str:
    return os.environ.get("LOCAL_LLM_MODEL", "qwen2.5:7b")


def enabled() -> bool:
    return os.environ.get("LOCAL_LLM", "1") != "0"


def available() -> bool:
    """Is the model installed and the server up? Asked for the health page, so it gives up after a second."""
    if not enabled():
        return False
    try:
        tags = httpx.get(f"{url()}/api/tags", timeout=1).json()
        return any(m.get("name") == model() for m in tags.get("models", []))
    except (httpx.HTTPError, ValueError):
        return False


def chat_json(system: str, user: str, temperature: float = 0.4, max_tokens: int = 160) -> dict | None:
    """One answer as a JSON object, or None when there is no usable answer."""
    if not enabled():
        return None
    body = dict(model=model(), stream=False, format="json", keep_alive="30m", options=dict(temperature=temperature, num_predict=max_tokens),
                messages=[dict(role="system", content=system), dict(role="user", content=user)])
    try:
        r = httpx.post(f"{url()}/api/chat", json=body, timeout=float(os.environ.get("LOCAL_LLM_TIMEOUT", "20")))
        r.raise_for_status()
        value = json.loads(r.json()["message"]["content"])
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def warm() -> None:
    """Load the model into memory at start-up, so the first automatic call does not wait for it."""
    if available():
        chat_json("Answer with a JSON object.", '{"ready": true}', max_tokens=8)

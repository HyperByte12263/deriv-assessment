"""The single boundary for LLM calls.

`complete()` returns None when no provider is configured or the call fails, so
every caller must have an offline path. Each call is appended to
outputs/llm_calls.jsonl for traceability.

Provider: LLM_PROVIDER (anthropic | gemini) if set, else whichever key exists.
"""
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

LOG_PATH = Path(os.getenv("LLM_LOG", "outputs/llm_calls.jsonl"))
KEY_VARS = {"anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY"}


def provider():
    chosen = os.getenv("LLM_PROVIDER")
    if chosen:
        return chosen if os.getenv(KEY_VARS.get(chosen, "")) else None
    return next((name for name, var in KEY_VARS.items() if os.getenv(var)), None)


def _anthropic(prompt, system, json_mode, timeout):
    import anthropic

    client = anthropic.Anthropic(timeout=timeout, max_retries=1)
    if json_mode:
        system = (system + "\n\nRespond with a single JSON value only, no prose.").strip()
    kwargs = {
        "model": os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5"),
        "max_tokens": 4096,
        "output_config": {"effort": os.getenv("ANTHROPIC_EFFORT", "low")},
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    response = client.messages.create(**kwargs)
    if response.stop_reason == "refusal":
        raise RuntimeError("model refused")
    return "".join(block.text for block in response.content if block.type == "text")


def _gemini(prompt, system, json_mode, timeout):
    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=os.environ["GEMINI_API_KEY"],
        http_options=types.HttpOptions(timeout=timeout * 1000),
    )
    config = types.GenerateContentConfig(
        temperature=0,
        system_instruction=system or None,
        response_mime_type="application/json" if json_mode else None,
    )
    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest"),
        contents=prompt,
        config=config,
    )
    return response.text


CALLERS = {"anthropic": _anthropic, "gemini": _gemini}


def _log(record):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def complete(prompt, system="", json_mode=False, timeout=30, tag=""):
    """Return the model's text, or None (no key / error / refusal)."""
    name = provider()
    if name is None:
        return None
    start = time.time()
    text, error = None, None
    try:
        text = CALLERS[name](prompt, system, json_mode, timeout)
    except Exception as e:  # any provider failure -> caller falls back
        error = f"{type(e).__name__}: {e}"
    _log({
        "tag": tag,
        "provider": name,
        "prompt": prompt,
        "system": system,
        "response": text,
        "error": error,
        "seconds": round(time.time() - start, 2),
    })
    return text


def strip_fences(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    return text.strip()


def complete_json(prompt, system="", timeout=30, tag=""):
    """Parsed JSON from the model, or None. Callers still validate the shape."""
    text = complete(prompt, system, json_mode=True, timeout=timeout, tag=tag)
    if text is None:
        return None
    try:
        return json.loads(strip_fences(text))
    except json.JSONDecodeError:
        return None

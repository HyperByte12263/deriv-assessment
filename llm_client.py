"""The single boundary for LLM calls.

`complete()` returns None when no provider is configured or the call fails, so
every caller must have an offline path. Each call is appended to
outputs/llm_calls.jsonl for traceability.

Provider: LLM_PROVIDER (anthropic | gemini) if set, else whichever key exists.
"""
import hashlib
import json
import os
import time
from datetime import datetime, timezone
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
MODEL_DEFAULTS = {"anthropic": ("ANTHROPIC_MODEL", "claude-opus-5-5"), "gemini": ("GEMINI_MODEL", "gemini-flash-lite-latest")}


def model_name(name):
    if name not in MODEL_DEFAULTS:
        return "rules-fallback"
    var, default = MODEL_DEFAULTS[name]
    return os.getenv(var, default)


def _log(record):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _record(stage, name, prompt, system, input_artifacts, output_artifact, **extra):
    return {
        "stage": stage,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": name or "offline",
        "model": model_name(name),
        "prompt_hash": hashlib.sha256((system + "\n" + prompt).encode("utf-8")).hexdigest()[:16],
        "input_artifacts": list(input_artifacts),
        "output_artifact": output_artifact,
        **extra,
    }


def complete(prompt, system="", json_mode=False, timeout=60, tag="", input_artifacts=(), output_artifact=None):
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
    _log(_record(tag, name, prompt, system, input_artifacts, output_artifact,
                 prompt=prompt, response=text, error=error, seconds=round(time.time() - start, 2)))
    return text


def log_offline(stage, prompt, system="", input_artifacts=(), output_artifact=None):
    """Record a stage that ran on the rules fallback because no provider is configured."""
    _log(_record(stage, None, prompt, system, input_artifacts, output_artifact,
                 response=None, error="no LLM provider configured; rules fallback used"))


def strip_fences(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    return text.strip()


def complete_json(prompt, system="", timeout=60, tag="", input_artifacts=(), output_artifact=None):
    """Parsed JSON from the model, or None. Callers still validate the shape."""
    text = complete(prompt, system, json_mode=True, timeout=timeout, tag=tag,
                    input_artifacts=input_artifacts, output_artifact=output_artifact)
    if text is None:
        return None
    try:
        return json.loads(strip_fences(text))
    except json.JSONDecodeError:
        return None

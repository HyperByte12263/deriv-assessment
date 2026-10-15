import llm_client


def test_no_key_means_offline(monkeypatch):
    for var in ("LLM_PROVIDER", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert llm_client.provider() is None
    assert llm_client.complete("hi") is None
    assert llm_client.complete_json("hi") is None


def test_provider_failure_falls_back_and_logs(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.setattr(llm_client, "LOG_PATH", tmp_path / "calls.jsonl")

    def boom(*args):
        raise TimeoutError("slow")

    monkeypatch.setitem(llm_client.CALLERS, "gemini", boom)
    assert llm_client.complete("hi", tag="t") is None
    assert "TimeoutError" in (tmp_path / "calls.jsonl").read_text(encoding="utf-8")


def test_strip_fences():
    assert llm_client.strip_fences('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert llm_client.strip_fences('{"a": 1}') == '{"a": 1}'

import json
import random
import sys

import pytest

import llm_client
import main
import route
from priority import score_ticket

ARTIFACTS = ["preprocessed_tickets.json", "classified_tickets.json", "retrieval_results.json", "priority_scores.json",
             "routing_decisions.json", "reply_drafts.json", "retrieval_quality.json", "ops_summary.md"]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for var in ("LLM_PROVIDER", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setenv(var, "")


def run(monkeypatch, out_dir, tickets="tickets.json", kb="kb_articles.json"):
    monkeypatch.setattr(sys, "argv", ["main.py", "--tickets", str(tickets), "--kb", str(kb), "--out-dir", str(out_dir)])
    main.main()
    return {name: (out_dir / name).read_text(encoding="utf-8") for name in ARTIFACTS}


def load(out_dir, name):
    return json.loads((out_dir / name).read_text(encoding="utf-8"))


def test_priority_formula():
    cls = {"urgency": "critical", "mentions_funds_blocked": True, "mentions_regulator_or_legal_threat": True,
           "requires_specialist_handling": True}
    assert score_ticket(cls, "vip", 0.30)[0] == 40 + 10 + 20 + 25 + 10 + 8
    cls = {"urgency": "low", "mentions_funds_blocked": False, "mentions_regulator_or_legal_threat": False,
           "requires_specialist_handling": False}
    assert score_ticket(cls, "standard", 0.55)[0] == 3  # 0.55 is not weak: the bonus is strictly below


def test_offline_run_is_reproducible(monkeypatch, tmp_path):
    first = run(monkeypatch, tmp_path / "a")
    second = run(monkeypatch, tmp_path / "b")
    assert first == second


def test_swapped_ids_and_order_give_same_results(monkeypatch, tmp_path):
    """The evaluator may replace fixtures: logic must key on content, not IDs or order."""
    tickets = json.load(open("tickets.json", encoding="utf-8"))
    rename = {t["ticket_id"]: f"X-{900 + i}" for i, t in enumerate(tickets)}
    swapped = [{**t, "ticket_id": rename[t["ticket_id"]]} for t in tickets]
    random.Random(7).shuffle(swapped)
    path = tmp_path / "swapped_tickets.json"
    path.write_text(json.dumps(swapped), encoding="utf-8")

    run(monkeypatch, tmp_path / "orig")
    run(monkeypatch, tmp_path / "swap", tickets=path)

    def by_id(out, name, key):
        return {r["ticket_id"]: r[key] for r in load(out, name)}
    for name, key in [("classified_tickets.json", "intent"), ("priority_scores.json", "priority_score"),
                      ("routing_decisions.json", "queues"), ("priority_scores.json", "expedited")]:
        orig, swap = by_id(tmp_path / "orig", name, key), by_id(tmp_path / "swap", name, key)
        assert {rename[k]: v for k, v in orig.items()} == swap, name


def test_stage_order_is_enforced(tmp_path):
    pipe = main.Pipeline(tmp_path)
    pipe.advance("TICKETS_LOADED")
    with pytest.raises(RuntimeError, match="illegal transition"):
        pipe.advance("TICKETS_CLASSIFIED")  # skips PREPROCESSING_COMPLETE


def test_legal_threat_overrides_lenient_llm_routing(monkeypatch):
    """The model may only make the safety label stricter; legal threats always reach Compliance."""
    cls = [{"ticket_id": "Z1", "intent": "withdrawal_issue", "urgency": "critical", "sentiment": "angry",
            "mentions_funds_blocked": False, "mentions_regulator_or_legal_threat": True,
            "requires_specialist_handling": True}]
    ret = [{"ticket_id": "Z1", "retrieved_articles": [{"article_id": "KB01", "title": "t", "score": 0.4},
                                                      {"article_id": "KB02", "title": "t", "score": 0.1}]}]
    prio = [{"ticket_id": "Z1", "priority_score": 100, "expedited": True}]
    monkeypatch.setattr(llm_client, "provider", lambda: "gemini")
    monkeypatch.setattr(llm_client, "complete_json", lambda *a, **k: [
        {"ticket_id": "Z1", "queues": ["Payments", "Not A Queue"], "routing_rationale": "x",
         "reply_safety_label": "safe_to_send_after_review"}])
    [r] = route.route(cls, ret, prio, [], None)
    assert r["reply_safety_label"] == "needs_legal_or_compliance_review"
    assert "Compliance" in r["queues"] and "Not A Queue" not in r["queues"]

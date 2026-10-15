"""Validate pipeline artifacts against the brief. Exit 1 on any failure; writes validation_report.md.

Usage: python validate.py [--tickets tickets.json] [--kb kb_articles.json] [--out-dir outputs]
"""
import argparse
import json
import sys
from pathlib import Path

from priority import compute_priorities
from vocab import INTENTS, LLM_STAGES, QUEUES, SAFETY_LABELS, SENTIMENTS, STAGES, TOP_N_EXPEDITED, URGENCIES

REQUIRED = ["preprocessed_tickets.json", "classified_tickets.json", "retrieval_results.json", "priority_scores.json",
            "routing_decisions.json", "reply_drafts.json", "llm_calls.jsonl"]
OPTIONAL = ["retrieval_quality.json", "ops_summary.md", "handoff_memory.json"]
HANDOFF_FIELDS = ["ticket_id", "customer_problem_summary", "open_questions", "do_not_say", "recommended_next_action"]
LOG_FIELDS = ["stage", "timestamp", "provider", "model", "prompt_hash", "input_artifacts", "output_artifact"]


def run_checks(tickets_path, kb_path, out_dir):
    out = Path(out_dir)
    results = []

    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))
        return ok

    missing = [f for f in REQUIRED if not (out / f).exists()] + [p for p in (tickets_path, kb_path) if not Path(p).exists()]
    if not check("required artifacts exist", not missing, f"missing: {missing}" if missing else ""):
        return results

    data = {}
    try:
        tickets = json.loads(Path(tickets_path).read_text(encoding="utf-8"))
        kb = json.loads(Path(kb_path).read_text(encoding="utf-8"))
        for f in REQUIRED[:-1] + [f for f in OPTIONAL if f.endswith(".json") and (out / f).exists()]:
            data[f] = json.loads((out / f).read_text(encoding="utf-8"))
        logs = [json.loads(line) for line in (out / "llm_calls.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        check("JSON files are valid", True)
    except (json.JSONDecodeError, OSError) as e:
        check("JSON files are valid", False, str(e))
        return results

    ids = {t["ticket_id"] for t in tickets}
    pre, cls, ret = data["preprocessed_tickets.json"], data["classified_tickets.json"], data["retrieval_results.json"]
    prio, routes, drafts = data["priority_scores.json"], data["routing_decisions.json"], data["reply_drafts.json"]

    for name, rows in [("preprocessed", pre), ("classified", cls), ("retrieval", ret), ("priority", prio), ("routing", routes)]:
        got = [r["ticket_id"] for r in rows]
        check(f"all tickets processed: {name}", sorted(got) == sorted(ids), f"got {len(got)} of {len(ids)}")

    t_by_id = {t["ticket_id"]: t for t in tickets}
    bad_lang = [p["ticket_id"] for p in pre
                if (t_by_id[p["ticket_id"]].get("language_hint", "en").lower() not in ("en", "en-us", "en-gb"))
                and not (p["translated"] and p["original_message"] == t_by_id[p["ticket_id"]]["message"]
                         and p["original_subject"] == t_by_id[p["ticket_id"]]["subject"] and p["message_for_processing"].strip())]
    check("non-English tickets keep original text and have English processing text", not bad_lang, str(bad_lang))

    bad_vocab = [c["ticket_id"] for c in cls if c["intent"] not in INTENTS or c["urgency"] not in URGENCIES
                 or c["sentiment"] not in SENTIMENTS
                 or not all(isinstance(c[f], bool) for f in ("mentions_funds_blocked", "mentions_regulator_or_legal_threat",
                                                               "requires_specialist_handling"))]
    check("classified outputs use only controlled vocabularies", not bad_vocab, str(bad_vocab))

    kb_ids = {a["article_id"] for a in kb}
    bad_kb = [r["ticket_id"] for r in ret if any(a["article_id"] not in kb_ids for a in r["retrieved_articles"])]
    check("retrieval references valid article IDs", not bad_kb, str(bad_kb))
    not_two = [r["ticket_id"] for r in ret if len(r["retrieved_articles"]) != 2
               or len({a["article_id"] for a in r["retrieved_articles"]}) != 2]
    check("each ticket has exactly 2 retrieved articles", not not_two, str(not_two))

    recomputed = compute_priorities(tickets, cls, ret)
    same = [(r["ticket_id"], r["priority_score"]) for r in recomputed] == [(p["ticket_id"], p["priority_score"]) for p in prio]
    check("priority scores recompute identically from classification + retrieval", same)
    state_path = out / "run_state.json"
    if state_path.exists():
        order = [s["state"] for s in json.loads(state_path.read_text(encoding="utf-8"))["history"]]
        ok = "KB_RETRIEVAL_COMPLETE" in order and "PRIORITY_SCORES_COMPUTED" in order and \
            order.index("KB_RETRIEVAL_COMPLETE") < order.index("PRIORITY_SCORES_COMPUTED")
        check("priority computed after retrieval (run_state order)", ok, " -> ".join(order))
        check("stages ran in the brief's order", order == STAGES[:len(order)], " -> ".join(order))

    expected_top = [r["ticket_id"] for r in recomputed[:TOP_N_EXPEDITED]]
    flagged = [p["ticket_id"] for p in prio if p["expedited"]]
    check("top 5 expedited tickets selected from computed scores", flagged == expected_top, f"{flagged} vs {expected_top}")

    bad_q = [r["ticket_id"] for r in routes if not r["queues"] or any(q not in QUEUES for q in r["queues"])
             or r["reply_safety_label"] not in SAFETY_LABELS]
    check("routing uses only the controlled queue vocabulary and safety labels", not bad_q, str(bad_q))

    drafted = {d["ticket_id"] for d in drafts}
    check("reply drafts exist for all top 5 priority tickets", drafted == set(expected_top),
          f"drafted {sorted(drafted)}, expected {sorted(expected_top)}")
    ret_by_id = {r["ticket_id"]: {a["article_id"] for a in r["retrieved_articles"]} for r in ret}
    bad_cite = [d["ticket_id"] for d in drafts if not d["citations"]
                or not set(d["citations"]) <= ret_by_id.get(d["ticket_id"], set())]
    check("reply drafts cite retrieved KB articles", not bad_cite, str(bad_cite))
    no_gate = [d["ticket_id"] for d in drafts if not d.get("review_gate_note") or not d.get("draft_reply")]
    check("reply drafts have text and a human review gate note", not no_gate, str(no_gate))
    if "handoff_memory.json" in data:  # STRETCH 9, checked only when produced
        handoff = data["handoff_memory.json"]
        bad = [h.get("ticket_id") for h in handoff if any(f not in h for f in HANDOFF_FIELDS)]
        check("handoff memory covers all top 5 tickets with required fields",
              not bad and {h["ticket_id"] for h in handoff} == set(expected_top), str(bad))

    stages_logged = [r.get("stage") for r in logs]
    required_stages = [LLM_STAGES[k] for k in ("classification", "routing", "drafting")]
    missing_stages = [s for s in required_stages if s not in stages_logged]
    check("LLM call log has separate records for classification, routing, drafting", not missing_stages,
          f"missing {missing_stages}" if missing_stages else ", ".join(stages_logged))
    bad_logs = [i for i, r in enumerate(logs) if any(f not in r for f in LOG_FIELDS)]
    check("LLM call records include all required fields", not bad_logs, f"bad lines {bad_logs}")
    return results


def write_report(results, out_dir):
    passed = sum(ok for _, ok, _ in results)
    lines = ["# Validation report", "", f"**{passed}/{len(results)} checks passed**", "",
             "| Check | Result | Detail |", "|---|---|---|"]
    lines += [f"| {name} | {'PASS' if ok else 'FAIL'} | {detail.replace('|', '/')} |" for name, ok, detail in results]
    Path(out_dir, "validation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickets", default="tickets.json")
    parser.add_argument("--kb", default="kb_articles.json")
    parser.add_argument("--out-dir", default="outputs")
    args = parser.parse_args()
    results = run_checks(args.tickets, args.kb, args.out_dir)
    if Path(args.out_dir).exists():
        write_report(results, args.out_dir)
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else ""))
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

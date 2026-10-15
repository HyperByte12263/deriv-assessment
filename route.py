"""Stage 2: queue routing LLM call. Queues are validated against the vocabulary; code sets a safety-label floor."""
import json

import llm_client
from vocab import LLM_STAGES, QUEUES, SAFETY_LABELS

INTENT_QUEUES = {
    "withdrawal_issue": ["Payments"],
    "deposit_issue": ["Payments"],
    "login_access": ["General Support", "Engineering"],
    "verification_kyc": ["Compliance"],
    "account_restriction": ["Compliance", "Risk"],
    "product_behavior": ["Product", "Engineering"],
    "privacy_request": ["Privacy"],
    "statement_export": ["General Support"],
    "api_support": ["Developer Support"],
    "other": ["General Support"],
}
LEGAL_REVIEW_INTENTS = {"account_restriction", "privacy_request"}


def safety_floor(cls):
    if cls["mentions_regulator_or_legal_threat"] or cls["intent"] in LEGAL_REVIEW_INTENTS:
        return "needs_legal_or_compliance_review"
    if cls["requires_specialist_handling"]:
        return "needs_specialist_review"
    return "safe_to_send_after_review"


def required_queues(cls):
    extra = []
    if cls["mentions_regulator_or_legal_threat"]:
        extra.append("Compliance")
    if cls["mentions_funds_blocked"]:
        extra.append("Risk")
    return extra


def rule_route(cls, ret, prio):
    queues = list(dict.fromkeys(INTENT_QUEUES.get(cls["intent"], ["General Support"]) + required_queues(cls)))
    top = ret["retrieved_articles"][0]
    flags = [f for f in ("mentions_funds_blocked", "mentions_regulator_or_legal_threat") if cls[f]]
    rationale = (f"intent={cls['intent']}, urgency={cls['urgency']}"
                 + (f", flags={'+'.join(flags)}" if flags else "")
                 + f"; best KB {top['article_id']} ({top['score']}); priority {prio['priority_score']}"
                 + (" (expedited)" if prio["expedited"] else ""))
    return queues, rationale


SYSTEM = "You route support tickets to internal queues. Use ONLY the allowed queue names and safety labels. Return JSON only."


def build_prompt(classified, retrieval, priorities):
    top5 = [p["ticket_id"] for p in priorities if p["expedited"]]
    return (
        f"Allowed queues: {QUEUES}\nAllowed reply_safety_label values: {SAFETY_LABELS}\n"
        "Route every ticket. Output a JSON array, one object per ticket:\n"
        '{"ticket_id": str, "queues": [allowed queue, ...], "routing_rationale": str (one short sentence citing '
        'the evidence: intent, flags, KB article), "reply_safety_label": allowed label}\n'
        "Multiple queues only where justified. Legal/regulatory threats need Compliance.\n"
        f"Top 5 priority tickets (expedited): {top5}\n"
        f"Classified tickets:\n{json.dumps(classified, ensure_ascii=False)}\n"
        f"Top retrieval results:\n{json.dumps(retrieval, ensure_ascii=False)}\n"
    )


def route(classified, retrieval, priorities, input_artifacts, output_artifact):
    prompt = build_prompt(classified, retrieval, priorities)
    stage = LLM_STAGES["routing"]
    if llm_client.provider() is None:
        llm_client.log_offline(stage, prompt, SYSTEM, input_artifacts, output_artifact)
        response = None
    else:
        response = llm_client.complete_json(prompt, SYSTEM, tag=stage,
                                            input_artifacts=input_artifacts, output_artifact=output_artifact)
    by_id = {str(r.get("ticket_id")): r for r in response if isinstance(r, dict)} if isinstance(response, list) else {}
    ret_by_id = {r["ticket_id"]: r for r in retrieval}
    prio_by_id = {p["ticket_id"]: p for p in priorities}

    out = []
    for cls in classified:
        tid = cls["ticket_id"]
        rule_queues, rule_rationale = rule_route(cls, ret_by_id[tid], prio_by_id[tid])
        llm = by_id.get(tid, {})
        llm_queues = [q for q in llm.get("queues", []) if q in QUEUES] if isinstance(llm.get("queues"), list) else []
        if llm_queues:
            queues = list(dict.fromkeys(llm_queues + required_queues(cls)))
            rationale = str(llm.get("routing_rationale") or rule_rationale)[:300]
            source = "llm"
        else:
            queues, rationale, source = rule_queues, rule_rationale, "rules"
        floor = safety_floor(cls)
        label = llm.get("reply_safety_label")
        if label not in SAFETY_LABELS or SAFETY_LABELS.index(label) < SAFETY_LABELS.index(floor):
            label = floor  # the model may only make the label stricter
        out.append({"ticket_id": tid, "queues": queues, "routing_rationale": rationale,
                    "reply_safety_label": label, "expedited": prio_by_id[tid]["expedited"],
                    "routing_source": source})
    return out

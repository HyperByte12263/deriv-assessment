"""Stage 3: safe reply drafts for the top-5 priority tickets only.

The prompt contains only the retrieved KB articles. Code checks citations (subset of retrieved IDs)
and banned phrases; anything that fails gets the template fallback. The review gate note is set by code.
"""
import json
import re

import llm_client
from vocab import LLM_STAGES, MIN_GUIDANCE_SCORE

BANNED = re.compile(
    r"\b(guarantee[ds]?|will be (approved|released|resolved|refunded)|within \d+\s*(hours?|days?|minutes?)"
    r"|definitely|promise|triggered by|our (risk|fraud) (system|model|rules)"
    r"|shortly|right away|as soon as possible"  # unsupported timelines
    r"|(the|a) customer|should be escalated|agents? should)\b", re.I)  # agent-facing KB wording copied verbatim
AGENT_FACING = re.compile(r"\b(support should|agents should|support may|should be escalated|ask the customer|avoid"
                          r"|(the|a) customer)\b", re.I)


def customer_sentences(body):
    """KB sentences safe to paraphrase to a customer (drop internal agent instructions)."""
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", body) if s.strip() and not AGENT_FACING.search(s)]


def review_gate_note(route):
    return (f"HUMAN REVIEW REQUIRED before sending ({route['reply_safety_label']}). "
            f"Owner queue(s): {', '.join(route['queues'])}. Do not send automatically.")


def relevant(retrieved):
    """Articles worth using: the top hit always, others only above the filler threshold."""
    return [a for i, a in enumerate(retrieved) if i == 0 or a["score"] >= MIN_GUIDANCE_SCORE]


def template_draft(ticket, pre, retrieved, kb_by_id):
    greeting = "Dear customer," if ticket.get("channel") == "email" else "Hi,"
    guidance = []
    for a in relevant(retrieved):
        guidance += customer_sentences(kb_by_id[a["article_id"]]["body"])[:1]
    body = " ".join(guidance) if guidance else "Your request has been passed to the relevant team."
    return (f"{greeting} thank you for contacting us about \"{pre['subject_for_processing']}\". "
            f"We understand this is important to you. {body} "
            "A specialist will review your case and contact you if any further information is needed. "
            "We are not able to confirm an outcome or timeline until that review is complete.")


SYSTEM = (
    "You draft customer support replies. Use ONLY the knowledge-base articles provided for each ticket. "
    "Do not speculate, do not promise outcomes or timelines not stated in the articles, do not reveal internal "
    "review logic, triggers or risk rules, and give no financial or trading advice. Return JSON only."
)


def build_prompt(items):
    return (
        "Write a reply draft for each ticket. Each draft must acknowledge the issue, use the provided KB guidance "
        "where relevant (rephrased for the customer, addressing them as 'you'), and say a team member will review "
        "the case. Never state or imply a timeline such as 'shortly'. Keep it under 120 words, matching the channel "
        "(email = formal, chat = short).\n"
        'Output a JSON array: {"ticket_id": str, "draft_reply": str, "citations": [article_id used]}\n'
        "Cite only article IDs given for that ticket, and only articles you actually used; ignore an article "
        "with a low relevance_score if it is unrelated to the customer's issue.\n"
        f"Tickets:\n{json.dumps(items, ensure_ascii=False, indent=2)}"
    )


def draft_replies(tickets, preprocessed, retrieval, priorities, routes, articles, input_artifacts, output_artifact):
    t_by_id = {t["ticket_id"]: t for t in tickets}
    pre_by_id = {p["ticket_id"]: p for p in preprocessed}
    ret_by_id = {r["ticket_id"]: r["retrieved_articles"] for r in retrieval}
    route_by_id = {r["ticket_id"]: r for r in routes}
    kb_by_id = {a["article_id"]: a for a in articles}
    top5 = [p["ticket_id"] for p in priorities if p["expedited"]]

    items = [{"ticket_id": tid, "channel": t_by_id[tid].get("channel"),
              "subject": pre_by_id[tid]["subject_for_processing"], "message": pre_by_id[tid]["message_for_processing"],
              "kb_articles": [{"article_id": a["article_id"], "title": kb_by_id[a["article_id"]]["title"],
                               "relevance_score": a["score"],
                               "body": kb_by_id[a["article_id"]]["body"]} for a in ret_by_id[tid]]}
             for tid in top5]
    prompt = build_prompt(items)
    stage = LLM_STAGES["drafting"]
    if llm_client.provider() is None:
        llm_client.log_offline(stage, prompt, SYSTEM, input_artifacts, output_artifact)
        response = None
    else:
        response = llm_client.complete_json(prompt, SYSTEM, tag=stage,
                                            input_artifacts=input_artifacts, output_artifact=output_artifact)
    by_id = {str(r.get("ticket_id")): r for r in response if isinstance(r, dict)} if isinstance(response, list) else {}

    out = []
    for tid in top5:
        retrieved_ids = [a["article_id"] for a in ret_by_id[tid]]
        llm = by_id.get(tid, {})
        text = llm.get("draft_reply") if isinstance(llm.get("draft_reply"), str) else ""
        citations = [c for c in llm.get("citations", []) if c in retrieved_ids] if isinstance(llm.get("citations"), list) else []
        if text and citations and not BANNED.search(text):
            source = "llm"
        else:
            text = template_draft(t_by_id[tid], pre_by_id[tid], ret_by_id[tid], kb_by_id)
            citations = [a["article_id"] for a in relevant(ret_by_id[tid])]
            source = "template" if not llm else "template (llm draft failed checks)"
        out.append({"ticket_id": tid, "channel": t_by_id[tid].get("channel", ""), "draft_reply": text,
                    "citations": citations, "review_gate_note": review_gate_note(route_by_id[tid]),
                    "draft_source": source})
    return out

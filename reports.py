"""Deterministic analysis artifacts: retrieval quality notes, the ops batch summary, and handoff memory seeds."""
import re
from collections import Counter

from draft import relevant
from vocab import INTENTS, URGENCIES, WEAK_RETRIEVAL_THRESHOLD

AMBIGUOUS_MARGIN = 0.05


def retrieval_quality(retrieval):
    notes = []
    for r in retrieval:
        top, second = r["retrieved_articles"][0], r["retrieved_articles"][1]
        issues, fixes = [], []
        if top["score"] < WEAK_RETRIEVAL_THRESHOLD:
            issues.append(f"top score {top['score']} for {top['article_id']} is below {WEAK_RETRIEVAL_THRESHOLD}")
            fixes.append("calibrate the threshold to the scorer (TF-IDF cosine rarely exceeds 0.55 on short KB "
                         "articles) or add embedding similarity")
        if top["score"] - second["score"] < AMBIGUOUS_MARGIN:
            issues.append(f"ambiguous: {top['article_id']} ({top['score']}) vs {second['article_id']} ({second['score']})")
            fixes.append("add KB tags/synonyms to separate these articles")
        if second["score"] == 0:
            issues.append(f"second article {second['article_id']} has zero overlap and is filler")
            fixes.append("allow fewer than 2 relevant articles or expand the KB for this topic")
        if issues:
            notes.append({"ticket_id": r["ticket_id"], "issue": "; ".join(issues),
                          "recommended_improvement": "; ".join(dict.fromkeys(fixes))})
    return notes


def ops_summary(tickets, classified, retrieval, priorities, routes):
    intents = Counter(c["intent"] for c in classified)
    urgencies = Counter(c["urgency"] for c in classified)
    themes = Counter(r["retrieved_articles"][0]["title"] for r in retrieval)
    route_by_id = {r["ticket_id"]: r for r in routes}
    lines = ["# Ops summary", "", f"Tickets processed: {len(tickets)}", "", "## Count by intent", "",
             "| Intent | Count |", "|---|---|"]
    lines += [f"| {i} | {intents[i]} |" for i in INTENTS if intents[i]]
    lines += ["", "## Count by urgency", "", "| Urgency | Count |", "|---|---|"]
    lines += [f"| {u} | {urgencies[u]} |" for u in URGENCIES if urgencies[u]]
    lines += ["", "## Top recurring themes (best-matching KB article)", ""]
    lines += [f"- {title}: {n}" for title, n in themes.most_common(5)]
    lines += ["", "## Legal / regulatory risk", ""]
    legal = [c["ticket_id"] for c in classified if c["mentions_regulator_or_legal_threat"]]
    lines += [f"- {tid} -> {', '.join(route_by_id[tid]['queues'])}" for tid in legal] or ["- none"]
    lines += ["", "## Needs specialist handling", ""]
    lines += [f"- {c['ticket_id']} ({c['intent']})" for c in classified if c["requires_specialist_handling"]] or ["- none"]
    lines += ["", "## Top 5 expedited", "", "| Rank | Ticket | Score | Queues | Safety label |", "|---|---|---|---|---|"]
    lines += [f"| {p['rank']} | {p['ticket_id']} | {p['priority_score']} | {', '.join(route_by_id[p['ticket_id']]['queues'])} "
              f"| {route_by_id[p['ticket_id']]['reply_safety_label']} |" for p in priorities if p["expedited"]]
    return "\n".join(lines) + "\n"


OPEN_QUESTIONS = {
    "withdrawal_issue": ["Which payment method was used for the withdrawal?", "Were all requested documents accepted?"],
    "deposit_issue": ["What is the transaction reference and amount?", "Has the bank confirmed the payment settled?"],
    "login_access": ["Which platform and device show the error?", "Does a clean login flow (cleared session) still fail?"],
    "verification_kyc": ["Which document was requested or rejected?", "Has the customer been told the acceptable-document criteria?"],
    "account_restriction": ["Has the specialist team already contacted the customer?"],
    "product_behavior": ["Which strategy configuration and time window differ from the backtest?"],
    "privacy_request": ["Has the customer's identity been verified for the closure/deletion request?"],
    "statement_export": ["Which date range is needed, and is it available in-app?"],
    "api_support": ["Which endpoint, environment and auth method hit the limit?"],
    "other": ["What outcome is the customer looking for?"],
}
BASE_DO_NOT_SAY = [
    "Any guaranteed outcome or timeline not stated in the KB",
    "Internal review triggers, risk rules or reasons for a review",
    "Financial or trading advice",
]
GUIDANCE_RE = re.compile(r"\b(avoid|should not|not guarantee|not promise)\b", re.I)


def handoff_memory(preprocessed, classified, retrieval, priorities, routes, articles):
    pre = {p["ticket_id"]: p for p in preprocessed}
    cls = {c["ticket_id"]: c for c in classified}
    ret = {r["ticket_id"]: r["retrieved_articles"] for r in retrieval}
    rte = {r["ticket_id"]: r for r in routes}
    kb = {a["article_id"]: a for a in articles}
    out = []
    for p in priorities:
        if not p["expedited"]:
            continue
        tid, c, r = p["ticket_id"], cls[p["ticket_id"]], rte[p["ticket_id"]]
        sentences = [s.strip() for a in relevant(ret[tid]) for s in re.split(r"(?<=[.!?])\s+", kb[a["article_id"]]["body"])]
        flags = [label for flag, label in (("mentions_funds_blocked", "says funds are blocked"),
                                           ("mentions_regulator_or_legal_threat", "threatens regulator/legal action"))
                 if c[flag]]
        do_not_say = BASE_DO_NOT_SAY + [f"KB: {s}" for s in sentences if GUIDANCE_RE.search(s)]
        if c["mentions_regulator_or_legal_threat"]:
            do_not_say.append("Anything that discourages the customer from complaining to a regulator")
        out.append({
            "ticket_id": tid,
            "customer_problem_summary": f"{c['intent'].replace('_', ' ')} ({c['urgency']} urgency, {c['sentiment']}): "
                                        f"{pre[tid]['subject_for_processing']}" + (f"; customer {', '.join(flags)}" if flags else ""),
            "open_questions": OPEN_QUESTIONS.get(c["intent"], OPEN_QUESTIONS["other"]),
            "do_not_say": do_not_say,
            "recommended_next_action": f"{r['reply_safety_label'].replace('_', ' ')}: {', '.join(r['queues'])} to review "
                                       "the draft in reply_drafts.json before anything is sent",
            "kb_context": [a["article_id"] for a in relevant(ret[tid])],
        })
    return out

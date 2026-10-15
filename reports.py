"""Deterministic analysis artifacts: retrieval quality notes and the ops batch summary."""
from collections import Counter

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

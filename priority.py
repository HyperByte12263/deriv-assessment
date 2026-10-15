"""Deterministic priority scoring with the brief's formula. The LLM never sets priority."""
from vocab import (BASE_PRIORITY, FUNDS_BLOCKED_BONUS, LEGAL_THREAT_BONUS, SPECIALIST_BONUS, TIER_BONUS,
                   TOP_N_EXPEDITED, WEAK_RETRIEVAL_BONUS, WEAK_RETRIEVAL_THRESHOLD)


def score_ticket(cls, tier, top_score):
    components = {
        "base_priority": BASE_PRIORITY[cls["urgency"]],
        "customer_tier_bonus": TIER_BONUS.get(tier, 0),
        "funds_blocked_bonus": FUNDS_BLOCKED_BONUS if cls["mentions_funds_blocked"] else 0,
        "regulatory_legal_threat_bonus": LEGAL_THREAT_BONUS if cls["mentions_regulator_or_legal_threat"] else 0,
        "specialist_handling_bonus": SPECIALIST_BONUS if cls["requires_specialist_handling"] else 0,
        "retrieval_weakness_bonus": WEAK_RETRIEVAL_BONUS if top_score < WEAK_RETRIEVAL_THRESHOLD else 0,
    }
    return sum(components.values()), components


def compute_priorities(tickets, classified, retrieval):
    tickets_by_id = {t["ticket_id"]: t for t in tickets}
    top_by_id = {r["ticket_id"]: r["retrieved_articles"][0]["score"] for r in retrieval}
    rows = []
    for c in classified:
        t = tickets_by_id[c["ticket_id"]]
        score, components = score_ticket(c, t.get("customer_tier", "standard"), top_by_id[c["ticket_id"]])
        rows.append({"ticket_id": c["ticket_id"], "priority_score": score, "components": components,
                     "top_retrieval_score": top_by_id[c["ticket_id"]], "created_at": t.get("created_at", "")})
    # Ties: older ticket first, then ID, so the order never depends on input file order.
    rows.sort(key=lambda r: (-r["priority_score"], r["created_at"], r["ticket_id"]))
    for rank, r in enumerate(rows, 1):
        r["rank"] = rank
        r["expedited"] = rank <= TOP_N_EXPEDITED
    return rows

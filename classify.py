"""Stage 1: one batched LLM classification call; rules fill any field the model gets wrong or omits.

Risk flags are final = LLM OR rule, so a model miss can never lower priority on a legal threat or blocked funds.
"""
import json
import re

import llm_client
from vocab import INTENTS, LLM_STAGES, SENTIMENTS, URGENCIES

INTENT_KEYWORDS = {
    "withdrawal_issue": ["withdrawal", "withdraw", "payout", "cash out"],
    "deposit_issue": ["deposit", "debit", "debited", "charged", "top up", "payment"],
    "login_access": ["log in", "login", "password", "session", "sign in", "2fa", "locked out"],
    "verification_kyc": ["verification", "verify", "verified", "document", "documents", "proof of address", "kyc", "identity"],
    "account_restriction": ["suspended", "suspension", "restricted", "restriction", "blocked", "frozen", "disabled"],
    "product_behavior": ["bot", "strategy", "backtest", "execution", "feature", "behaving"],
    "privacy_request": ["delete", "deletion", "personal data", "close my account", "closure", "privacy", "gdpr"],
    "statement_export": ["statement", "export", "account history", "download"],
    "api_support": ["api", "rate limit", "rate limited", "endpoint", "per-token", "per-ip", "webhook"],
}
SPECIALIST_INTENTS = {"withdrawal_issue", "verification_kyc", "account_restriction", "privacy_request"}

LEGAL_RE = re.compile(r"\b(regulator|ombudsman|lawyer|solicitor|legal action|sue|court|formal complaint)\b", re.I)
FUNDS_BLOCKED_RE = re.compile(
    r"\b(funds?|money|balance)\b[^.]{0,40}\b(blocked|frozen|stuck|held|locked)\b"
    r"|\b(blocked|frozen)\b[^.]{0,20}\b(funds?|money|balance)\b", re.I)
URGENT_RE = re.compile(r"\b(urgent|urgently|immediately|asap|right now|today)\b", re.I)
DUPLICATE_RE = re.compile(r"\b(twice|duplicate|double)\b", re.I)


def _text(p):
    return f"{p['subject_for_processing']}. {p['message_for_processing']}"


def _has(text, kw):
    return re.search(rf"\b{re.escape(kw)}\b", text, re.I) is not None


def rule_classify(p):
    text = _text(p)
    scores = {i: sum(_has(text, kw) for kw in kws) for i, kws in INTENT_KEYWORDS.items()}
    best = max(scores.values())
    intent = next(i for i in INTENT_KEYWORDS if scores[i] == best) if best else "other"
    legal = bool(LEGAL_RE.search(text))
    funds = bool(FUNDS_BLOCKED_RE.search(text))
    if legal:
        urgency = "critical"
    elif funds or URGENT_RE.search(text) or DUPLICATE_RE.search(text) or intent in {"withdrawal_issue", "account_restriction"}:
        urgency = "high"
    elif intent == "statement_export" or re.search(r"quick question|where (do|can) i", text, re.I):
        urgency = "low"
    else:
        urgency = "medium"
    if legal:
        sentiment = "angry"
    elif re.search(r"urgent|still|twice|keep getting|without a clear reason|declined|rejected|pending for", text, re.I):
        sentiment = "frustrated"
    elif re.search(r"quick question|thanks|thank you", text, re.I):
        sentiment = "calm"
    else:
        sentiment = "neutral"
    specialist = intent in SPECIALIST_INTENTS or legal or funds or bool(DUPLICATE_RE.search(text))
    return {"intent": intent, "urgency": urgency, "sentiment": sentiment,
            "mentions_funds_blocked": funds, "mentions_regulator_or_legal_threat": legal,
            "requires_specialist_handling": specialist}


SYSTEM = (
    "You are a support-ops classifier. Use ONLY the allowed values given. "
    "Never invent new categories. Return JSON only."
)


def build_prompt(preprocessed):
    tickets = [{"ticket_id": p["ticket_id"], "subject": p["subject_for_processing"],
                "message": p["message_for_processing"]} for p in preprocessed]
    return (
        "Classify every ticket below. Output a JSON array with one object per ticket and these fields:\n"
        "- ticket_id: string, copied exactly from the input\n"
        f"- intent: one of {INTENTS}\n"
        f"- urgency: one of {URGENCIES} (critical = legal/regulatory threat or severe financial harm; "
        "high = money affected or customer blocked; medium = needs action; low = how-to question)\n"
        f"- sentiment: one of {SENTIMENTS}\n"
        "- mentions_funds_blocked: boolean, true only if the customer says their funds/balance are blocked, frozen or held\n"
        "- mentions_regulator_or_legal_threat: boolean, true only for a threat of regulator complaint, legal action or lawyers\n"
        "- requires_specialist_handling: boolean, true if compliance, payments investigation, privacy/legal, "
        "account restriction or engineering investigation is needed\n"
        "Tickets (already normalised to English):\n" + json.dumps(tickets, ensure_ascii=False, indent=2)
    )


def _valid(field, value):
    allowed = {"intent": INTENTS, "urgency": URGENCIES, "sentiment": SENTIMENTS}
    if field in allowed:
        return value in allowed[field]
    return isinstance(value, bool)


def classify(preprocessed, input_artifacts, output_artifact):
    prompt = build_prompt(preprocessed)
    stage = LLM_STAGES["classification"]
    if llm_client.provider() is None:
        llm_client.log_offline(stage, prompt, SYSTEM, input_artifacts, output_artifact)
        response = None
    else:
        response = llm_client.complete_json(prompt, SYSTEM, tag=stage,
                                            input_artifacts=input_artifacts, output_artifact=output_artifact)
    by_id = {str(r.get("ticket_id")): r for r in response if isinstance(r, dict)} if isinstance(response, list) else {}

    out = []
    for p in preprocessed:
        rules = rule_classify(p)
        llm = by_id.get(p["ticket_id"], {})
        result = {"ticket_id": p["ticket_id"]}
        fallback_fields = []
        for field, rule_value in rules.items():
            value = llm.get(field)
            if not _valid(field, value):
                value = rule_value
                fallback_fields.append(field)
            if field in ("mentions_funds_blocked", "mentions_regulator_or_legal_threat", "requires_specialist_handling"):
                value = bool(value) or rule_value  # conservative: either source can raise a flag
            result[field] = value
        result["original_language"] = p["original_language"]
        result["translated"] = p["translated"]
        result["classification_source"] = "rules" if len(fallback_fields) == len(rules) else (
            "llm" if not fallback_fields else "llm+rules:" + ",".join(fallback_fields))
        out.append(result)
    return out

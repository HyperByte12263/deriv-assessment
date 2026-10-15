"""Controlled vocabularies and stage names from the brief. Model output is validated against these."""

INTENTS = [
    "withdrawal_issue", "deposit_issue", "login_access", "verification_kyc", "account_restriction",
    "product_behavior", "privacy_request", "statement_export", "api_support", "other",
]
URGENCIES = ["critical", "high", "medium", "low"]
SENTIMENTS = ["calm", "frustrated", "angry", "neutral"]
QUEUES = [
    "General Support", "Payments", "Compliance", "Risk",
    "Engineering", "Product", "Privacy", "Developer Support",
]
# Ordered from least to most restrictive, so code can take the stricter of two labels.
SAFETY_LABELS = ["safe_to_send_after_review", "needs_specialist_review", "needs_legal_or_compliance_review"]

STAGES = [
    "INIT", "TICKETS_LOADED", "PREPROCESSING_COMPLETE", "TICKETS_CLASSIFIED", "KB_RETRIEVAL_COMPLETE",
    "PRIORITY_SCORES_COMPUTED", "ROUTING_COMPLETE", "REPLY_DRAFTS_GENERATED", "VALIDATION_COMPLETE",
    "RESULTS_FINALISED",
]

# LLM call stage names as written to llm_calls.jsonl.
LLM_STAGES = {
    "translation": "PREPROCESSING_TRANSLATION",
    "classification": "STAGE1_CLASSIFICATION",
    "routing": "STAGE2_ROUTING",
    "drafting": "STAGE3_REPLY_DRAFTING",
}

BASE_PRIORITY = {"critical": 40, "high": 25, "medium": 10, "low": 3}
TIER_BONUS = {"vip": 10, "standard": 0}
FUNDS_BLOCKED_BONUS = 20
LEGAL_THREAT_BONUS = 25
SPECIALIST_BONUS = 10
WEAK_RETRIEVAL_BONUS = 8
WEAK_RETRIEVAL_THRESHOLD = 0.55
TOP_N_EXPEDITED = 5
MIN_GUIDANCE_SCORE = 0.15  # retrieved articles below this are filler and never quoted in a draft

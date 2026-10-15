## BUILD

Build a replayable AI support-ops pipeline that ingests customer support tickets from disk, normalises multilingual inputs, classifies intent and urgency, retrieves the most relevant help-center guidance, routes tickets to the correct internal queue, and drafts safe customer replies with human-review gates.

This is not a one-shot chatbot task. The evaluator will run your pipeline from a clean checkout, may replace the ticket and knowledge-base fixtures with equivalent files using the same schema, and will verify that ingestion, preprocessing, classification, retrieval, routing, and reply drafting are implemented as separate staged steps.

The pipeline must preserve intermediate artifacts, enforce controlled vocabularies, log LLM calls, and keep routing priority deterministic in code.

---

## INPUT FILES

Your pipeline must read these files from disk:

- `tickets.json`
- `kb_articles.json`

The sample data below is provided for local testing. The evaluator may replace these files with equivalent fixtures using the same schema. Your implementation must not depend on exact ticket IDs, ordering, wording, or expected final routing from the public fixture.

---

## SAMPLE `tickets.json`

```json
[
  {
    "ticket_id": "T01",
    "channel": "email",
    "customer_tier": "standard",
    "language_hint": "en",
    "subject": "Withdrawal still pending after 5 days",
    "message": "Hi team, my withdrawal has been pending for 5 days even though the app said 24 hours. I already uploaded the requested documents last week. Can someone tell me what is happening?",
    "created_at": "2025-04-14T08:10:00Z"
  },
  {
    "ticket_id": "T02",
    "channel": "chat",
    "customer_tier": "vip",
    "language_hint": "en",
    "subject": "Can't log in after password reset",
    "message": "Reset my password twice and now I keep getting an invalid session error on web and mobile. Need this fixed urgently.",
    "created_at": "2025-04-14T08:22:00Z"
  },
  {
    "ticket_id": "T03",
    "channel": "email",
    "customer_tier": "standard",
    "language_hint": "ms",
    "subject": "Dokumen tambahan diminta",
    "message": "Saya sudah lulus pengesahan sebelum ini tetapi sekarang diminta dokumen tambahan lagi. Kenapa akaun saya disemak semula?",
    "created_at": "2025-04-14T08:45:00Z"
  },
  {
    "ticket_id": "T04",
    "channel": "chat",
    "customer_tier": "standard",
    "language_hint": "en",
    "subject": "Bot performance looks different from backtest",
    "message": "My automated strategy is behaving very differently live compared with the backtest results from last week. Did execution rules change after the update?",
    "created_at": "2025-04-14T09:05:00Z"
  },
  {
    "ticket_id": "T05",
    "channel": "email",
    "customer_tier": "standard",
    "language_hint": "en",
    "subject": "Need account closure and data deletion",
    "message": "Please close my account and let me know the process to request deletion of my personal data. Also confirm whether anything must be retained for legal reasons.",
    "created_at": "2025-04-14T09:15:00Z"
  },
  {
    "ticket_id": "T06",
    "channel": "chat",
    "customer_tier": "standard",
    "language_hint": "hi-en",
    "subject": "Deposit failed but money debited",
    "message": "Mera bank account se paise cut gaye but deposit platform pe reflect nahi hua. Kya mujhe wait karna chahiye ya complaint raise karu?",
    "created_at": "2025-04-14T09:28:00Z"
  },
  {
    "ticket_id": "T07",
    "channel": "email",
    "customer_tier": "vip",
    "language_hint": "en",
    "subject": "Formal complaint if funds remain blocked",
    "message": "If my account remains restricted and my funds stay blocked today, I will file a formal complaint with the regulator. I want a written explanation immediately.",
    "created_at": "2025-04-14T09:40:00Z"
  },
  {
    "ticket_id": "T08",
    "channel": "chat",
    "customer_tier": "standard",
    "language_hint": "en",
    "subject": "Where can I find statement export?",
    "message": "Quick question: where do I download my account statement for the last 3 months?",
    "created_at": "2025-04-14T10:00:00Z"
  },
  {
    "ticket_id": "T09",
    "channel": "email",
    "customer_tier": "standard",
    "language_hint": "en",
    "subject": "Charged twice for one deposit",
    "message": "I attempted one deposit, got an error, retried once, and now I see two bank debits. Only one deposit reached the account. Please investigate.",
    "created_at": "2025-04-14T10:18:00Z"
  },
  {
    "ticket_id": "T10",
    "channel": "chat",
    "customer_tier": "standard",
    "language_hint": "en",
    "subject": "Verification question",
    "message": "Why was my proof of address rejected? The document is recent and clearly shows my name.",
    "created_at": "2025-04-14T10:35:00Z"
  },
  {
    "ticket_id": "T11",
    "channel": "email",
    "customer_tier": "standard",
    "language_hint": "en",
    "subject": "Please tell me exact reason for suspension",
    "message": "My account was suspended without a clear reason. I need to know exactly what triggered this and whether my balance is safe.",
    "created_at": "2025-04-14T10:55:00Z"
  },
  {
    "ticket_id": "T12",
    "channel": "chat",
    "customer_tier": "standard",
    "language_hint": "en",
    "subject": "API rate limit confusion",
    "message": "I am getting rate limited much earlier than expected from the docs. Is there a per-token or per-IP limit?",
    "created_at": "2025-04-14T11:10:00Z"
  }
]
```

---

## SAMPLE `kb_articles.json`

```json
[
  {
    "article_id": "KB01",
    "title": "Withdrawal review timelines",
    "category": "payments",
    "body": "Withdrawals may be delayed if additional verification or security review is required. Customers should check whether all requested documents were submitted and whether the chosen payment method is eligible for withdrawal.",
    "tags": ["withdrawal", "review", "documents"]
  },
  {
    "article_id": "KB02",
    "title": "Additional verification checks",
    "category": "compliance",
    "body": "Previously verified customers may occasionally be asked for additional documents due to regulatory, risk, or account-security checks. Review requests do not always indicate a permanent account issue.",
    "tags": ["kyc", "verification", "documents"]
  },
  {
    "article_id": "KB03",
    "title": "Deposit pending or missing after bank debit",
    "category": "payments",
    "body": "If a customer was charged but the deposit is not visible, first confirm transaction reference details and whether the payment settled successfully. Some payment methods can take time to reconcile. Duplicate charges should be escalated with payment evidence.",
    "tags": ["deposit", "bank", "duplicate", "reconciliation"]
  },
  {
    "article_id": "KB04",
    "title": "Account access and session issues",
    "category": "technical",
    "body": "Invalid session or login failures can result from expired sessions, password-reset timing, cached credentials, or device-specific authentication issues. Ask the customer to try a clean login flow and capture platform details if the issue persists.",
    "tags": ["login", "session", "password"]
  },
  {
    "article_id": "KB05",
    "title": "Statement and report exports",
    "category": "account",
    "body": "Customers can download account statements from the reports or account history section. If the desired date range is unavailable in-app, support may provide guidance on export limitations.",
    "tags": ["statement", "export", "report"]
  },
  {
    "article_id": "KB06",
    "title": "Proof of address review guidance",
    "category": "compliance",
    "body": "Proof of address documents may be rejected if they are outdated, incomplete, cropped, mismatched, or unsupported. Support should avoid promising approval and instead explain the acceptable-document criteria.",
    "tags": ["proof_of_address", "rejected", "verification"]
  },
  {
    "article_id": "KB07",
    "title": "Account restriction and review communication",
    "category": "compliance",
    "body": "When an account is under restriction or review, agents should acknowledge the concern, avoid disclosing internal triggers, avoid speculation, and explain that the specialist team will contact the customer if more information is needed.",
    "tags": ["restricted", "suspended", "review"]
  },
  {
    "article_id": "KB08",
    "title": "Trading bot and strategy-performance caveats",
    "category": "product",
    "body": "Backtest and live execution conditions may differ due to market conditions, latency, slippage, configuration changes, or data assumptions. Support should not guarantee strategy outcomes and may route suspected platform defects to product or engineering teams.",
    "tags": ["bot", "backtest", "live", "execution"]
  },
  {
    "article_id": "KB09",
    "title": "Data deletion and account closure requests",
    "category": "privacy",
    "body": "Account closure and data deletion requests may involve identity verification and legal retention requirements. Support should acknowledge the request, avoid making legal guarantees, and route privacy-specific questions to the relevant team when needed.",
    "tags": ["privacy", "deletion", "closure"]
  },
  {
    "article_id": "KB10",
    "title": "API usage and rate limits",
    "category": "developer",
    "body": "Rate limits may vary by endpoint, environment, authentication state, or abuse protections. Support should collect request context and route persistent discrepancies for technical review.",
    "tags": ["api", "rate_limit", "developer"]
  }
]
```

---

## CONTROLLED VOCABULARIES

Define these vocabularies in code and validate model outputs against them.

Allowed intent values:

```text
withdrawal_issue
deposit_issue
login_access
verification_kyc
account_restriction
product_behavior
privacy_request
statement_export
api_support
other
```

Allowed urgency values:

```text
critical
high
medium
low
```

Allowed sentiment values:

```text
calm
frustrated
angry
neutral
```

Allowed internal queues:

```text
General Support
Payments
Compliance
Risk
Engineering
Product
Privacy
Developer Support
```

Allowed reply safety labels:

```text
safe_to_send_after_review
needs_specialist_review
needs_legal_or_compliance_review
```

---

## PIPELINE STAGES

Your implementation must enforce these stages in code:

```text
INIT
 -> TICKETS_LOADED
 -> PREPROCESSING_COMPLETE
 -> TICKETS_CLASSIFIED
 -> KB_RETRIEVAL_COMPLETE
 -> PRIORITY_SCORES_COMPUTED
 -> ROUTING_COMPLETE
 -> REPLY_DRAFTS_GENERATED
 -> VALIDATION_COMPLETE
 -> RESULTS_FINALISED
```

Retrieval must happen after classification so the query can use normalised ticket metadata.

Priority scoring must happen after retrieval because unresolved high-risk intents with poor retrieval confidence may need stronger routing.

---

## MUST COMPLETE

### 1. Multilingual Preprocessing

Before classification, detect or use the language hint to identify non-English or mixed-language tickets and produce English text for downstream classification and retrieval.

For the public fixture, at least T03 and T06 must be normalised into English before classification.

Each preprocessed ticket must preserve:

```json
{
  "ticket_id": "string",
  "original_subject": "string",
  "original_message": "string",
  "subject_for_processing": "string",
  "message_for_processing": "string",
  "original_language": "string",
  "translated": true
}
```

Save output to `preprocessed_tickets.json`.

---

### 2. Ticket Classification

Make one Stage 1 LLM call using all preprocessed tickets.

The prompt must define all schema fields and controlled vocabularies.

For each ticket, output:

```json
{
  "ticket_id": "string",
  "intent": "withdrawal_issue",
  "urgency": "high",
  "sentiment": "frustrated",
  "mentions_funds_blocked": false,
  "mentions_regulator_or_legal_threat": false,
  "requires_specialist_handling": true,
  "original_language": "en",
  "translated": false
}
```

Save output to `classified_tickets.json`.

The model must not invent new intent, urgency, sentiment, or safety categories.

---

### 3. Knowledge Retrieval

Implement a retrieval step that matches each ticket to the most relevant help-center guidance.

You may use embeddings, keyword scoring, TF-IDF, or another reproducible retrieval method.

For each ticket, return the top 2 articles:

```json
{
  "ticket_id": "string",
  "retrieved_articles": [
    {
      "article_id": "KB01",
      "title": "string",
      "score": 0.87
    },
    {
      "article_id": "KB02",
      "title": "string",
      "score": 0.73
    }
  ]
}
```

Save output to `retrieval_results.json`.

The evaluator will check that retrieval uses the provided `kb_articles.json` rather than hardcoded mappings.

---

### 4. Deterministic Priority Scoring

Compute ticket priority scores deterministically in code.

Do not use the LLM to assign final priority scores.

Use this formula:

```text
base priority:
critical = 40
high = 25
medium = 10
low = 3

customer tier bonus:
vip = 10
standard = 0

funds blocked bonus = 20 if mentions_funds_blocked is true

regulatory/legal threat bonus = 25 if mentions_regulator_or_legal_threat is true

specialist handling bonus = 10 if requires_specialist_handling is true

retrieval weakness bonus = 8 if top retrieval score < 0.55

priority_score = base priority + customer tier bonus + funds blocked bonus + regulatory/legal threat bonus + specialist handling bonus + retrieval weakness bonus
```

Sort tickets by `priority_score` descending.

Flag the top 5 tickets for expedited routing.

Save output to `priority_scores.json`.

---

### 5. Queue Routing

Make a separate Stage 2 LLM call.

The call must include:

- classified tickets
- top retrieval results
- top 5 priority tickets
- controlled internal queue vocabulary

For each routed ticket, output:

```json
{
  "ticket_id": "string",
  "queues": ["Payments", "Compliance"],
  "routing_rationale": "string",
  "reply_safety_label": "needs_specialist_review"
}
```

Multiple queues may be assigned where justified.

Routing rationale must be short, concrete, and evidence-based.

Save output to `routing_decisions.json`.

---

### 6. Safe Customer Reply Drafts

Make a separate Stage 3 LLM call.

Generate reply drafts only for tickets in the top 5 priority list.

Each draft must:

- acknowledge the issue
- avoid speculation
- avoid promising outcomes or timelines that are not supported by the KB
- avoid disclosing internal review logic
- use the retrieved KB guidance where relevant
- include a human review gate note

Each reply must include:

```json
{
  "ticket_id": "string",
  "channel": "string",
  "draft_reply": "string",
  "citations": ["KB01", "KB02"],
  "review_gate_note": "string"
}
```

Save output to `reply_drafts.json`.

---

## SHOULD ATTEMPT

### 7. Retrieval Quality Notes

Produce a lightweight analysis of weak or ambiguous retrieval cases.

For each such ticket, output:

```json
{
  "ticket_id": "string",
  "issue": "string",
  "recommended_improvement": "string"
}
```

Save output to `retrieval_quality.json`.

---

### 8. Batch Summary for Operations

Create an internal summary for the day’s ticket batch.

Include:

- count by intent
- count by urgency
- top recurring problem themes
- tickets with legal/regulatory risk
- tickets needing specialist handling

Save output to `ops_summary.md`.

---

## STRETCH

### 9. Conversation Memory Seed

For each top-5 ticket, create a compact structured handoff object that a follow-up assistant could use in the next turn.

Example shape:

```json
{
  "ticket_id": "string",
  "customer_problem_summary": "string",
  "open_questions": ["string"],
  "do_not_say": ["string"],
  "recommended_next_action": "string"
}
```

Save output to `handoff_memory.json`.

---

### 10. Validation Report

Produce a human-readable report summarising which checks passed or failed in your validation step.

Save output to `validation_report.md`.

---

## REQUIRED ARTIFACTS

Your repository must produce:

- `tickets.json`
- `kb_articles.json`
- `preprocessed_tickets.json`
- `classified_tickets.json`
- `retrieval_results.json`
- `priority_scores.json`
- `routing_decisions.json`
- `reply_drafts.json`
- `retrieval_quality.json`, if attempted
- `ops_summary.md`, if attempted
- `handoff_memory.json`, if attempted
- `validation_report.md`, if attempted
- `llm_calls.jsonl`

---

## `llm_calls.jsonl` REQUIREMENTS

Log one JSON object per LLM call.

Each record must include:

```json
{
  "stage": "string",
  "timestamp": "ISO-8601 timestamp",
  "provider": "string",
  "model": "string",
  "prompt_hash": "string",
  "input_artifacts": ["path"],
  "output_artifact": "path"
}
```

There must be separate records for:

- ticket classification
- queue routing
- reply drafting
- optional analysis stages, if attempted

If retrieval is LLM-assisted, log it too. If retrieval is purely deterministic code, no LLM log is required for that step.

---

## VALIDATION REQUIREMENTS

The repository must include a validation command, for example:

```bash
make validate
```

or:

```bash
python validate.py
```

The validation command must check that:

- required artifacts exist
- JSON files are valid
- all tickets were processed
- non-English or mixed-language tickets preserve original text and include English processing text
- classified outputs use only controlled vocabularies
- retrieval results reference valid article IDs from `kb_articles.json`
- each ticket has exactly 2 retrieved articles
- priority scores are computed deterministically after retrieval
- top 5 expedited tickets are selected from computed scores
- routing queues use only the controlled queue vocabulary
- reply drafts exist for all top 5 priority tickets
- reply drafts cite retrieved KB articles
- LLM call logs contain separate records for required stages

---

## EXECUTION REQUIREMENTS

The evaluator will run the pipeline from a clean checkout.

Generated artifacts may be deleted before evaluation.

The evaluator may replace `tickets.json` and `kb_articles.json` with equivalent support and KB data using the same schema.

Static precomputed outputs are not sufficient.

The solution must actually run the staged pipeline and regenerate the required artifacts.

---

## TOOLS

Any programming language may be used.

Any LLM provider or AI tooling may be used.

---

## TECHNICAL CONSTRAINTS

- Read `tickets.json` and `kb_articles.json` from disk.
- Normalise non-English or mixed-language tickets before classification and retrieval while preserving original text.
- Retrieval must use `kb_articles.json` and be reproducible.
- Final priority scoring must be deterministic code.
- Classification, retrieval, routing, and reply drafting must be separate stages.
- Reply drafts must avoid speculation, unsupported promises, and disclosure of internal review logic.
- Static precomputed outputs are not sufficient.

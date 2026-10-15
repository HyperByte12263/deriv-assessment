"""Pydantic schemas: one model per artifact, built from vocab.py so there is one source of truth.

Strict mode (no "0.5" -> 0.5 coercion) and extra="forbid" (a typo like `queus` is an error, not a silent extra key).
The pipeline validates each stage's output before writing it; validate.py re-checks the files on disk.
"""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from vocab import INTENTS, QUEUES, SAFETY_LABELS, SENTIMENTS, URGENCIES

Intent = Literal[tuple(INTENTS)]
Urgency = Literal[tuple(URGENCIES)]
Sentiment = Literal[tuple(SENTIMENTS)]
Queue = Literal[tuple(QUEUES)]
SafetyLabel = Literal[tuple(SAFETY_LABELS)]
NonEmpty = Field(min_length=1)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PreprocessedTicket(Strict):
    ticket_id: str
    original_subject: str
    original_message: str
    subject_for_processing: str = NonEmpty
    message_for_processing: str = NonEmpty
    original_language: str
    translated: bool
    translation_method: Literal["llm", "glossary", "none"]


class ClassifiedTicket(Strict):
    ticket_id: str
    intent: Intent
    urgency: Urgency
    sentiment: Sentiment
    mentions_funds_blocked: bool
    mentions_regulator_or_legal_threat: bool
    requires_specialist_handling: bool
    original_language: str
    translated: bool
    classification_source: str


class RetrievedArticle(Strict):
    article_id: str
    title: str
    score: float = Field(ge=0, le=1)


class RetrievalResult(Strict):
    ticket_id: str
    retrieved_articles: list[RetrievedArticle] = Field(min_length=2, max_length=2)


class PriorityRow(Strict):
    ticket_id: str
    priority_score: int = Field(ge=0)
    components: dict[str, int]
    top_retrieval_score: float
    created_at: str
    rank: int = Field(ge=1)
    expedited: bool

    @model_validator(mode="after")
    def score_is_sum_of_components(self):
        if sum(self.components.values()) != self.priority_score:
            raise ValueError(f"priority_score {self.priority_score} != sum of components {sum(self.components.values())}")
        return self


class RoutingDecision(Strict):
    ticket_id: str
    queues: list[Queue] = NonEmpty
    routing_rationale: str = NonEmpty
    reply_safety_label: SafetyLabel
    expedited: bool
    routing_source: Literal["llm", "rules"]


class ReplyDraft(Strict):
    ticket_id: str
    channel: str
    draft_reply: str = NonEmpty
    citations: list[str] = NonEmpty
    review_gate_note: str = NonEmpty
    draft_source: str


class RetrievalQualityNote(Strict):
    ticket_id: str
    issue: str = NonEmpty
    recommended_improvement: str = NonEmpty


class HandoffMemory(Strict):
    ticket_id: str
    customer_problem_summary: str = NonEmpty
    open_questions: list[str]
    do_not_say: list[str] = NonEmpty
    recommended_next_action: str = NonEmpty
    kb_context: list[str]


class LlmCallRecord(BaseModel):
    """The brief's required fields; extra diagnostic fields (prompt_text, response, error) are allowed."""
    model_config = ConfigDict(extra="allow", strict=True)
    stage: str = NonEmpty
    timestamp: str = NonEmpty
    provider: str = NonEmpty
    model: str = NonEmpty
    prompt_hash: str = NonEmpty
    input_artifacts: list[str]
    output_artifact: Optional[str]


ARTIFACT_SCHEMAS = {
    "preprocessed_tickets.json": PreprocessedTicket,
    "classified_tickets.json": ClassifiedTicket,
    "retrieval_results.json": RetrievalResult,
    "priority_scores.json": PriorityRow,
    "routing_decisions.json": RoutingDecision,
    "reply_drafts.json": ReplyDraft,
    "retrieval_quality.json": RetrievalQualityNote,
    "handoff_memory.json": HandoffMemory,
    "llm_calls.jsonl": LlmCallRecord,
}


def schema_errors(name, rows, limit=3):
    """Human-readable errors for rows that don't match the artifact's schema (empty list = valid)."""
    model = ARTIFACT_SCHEMAS[name]
    errors = []
    for i, row in enumerate(rows):
        try:
            model.model_validate(row)
        except ValidationError as e:
            for err in e.errors()[:limit]:
                where = ".".join(str(p) for p in err["loc"])
                errors.append(f"{name}[{i}] ({row.get('ticket_id', row.get('stage', '?')) if isinstance(row, dict) else '?'}) "
                              f"{where}: {err['msg']}")
    return errors


def ensure_valid(name, rows):
    """Fail fast: stop the pipeline at the stage that produced bad data."""
    errors = schema_errors(name, rows)
    if errors:
        raise SystemExit(f"schema check failed for {name}:\n  " + "\n  ".join(errors[:10]))
    return rows

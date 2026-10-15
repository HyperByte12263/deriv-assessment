# SPEC

> Written before implementation. Brief: [`docs/BRIEF.md`](docs/BRIEF.md).

## 1. Problem in one paragraph

A replayable support-ops pipeline: read `tickets.json` + `kb_articles.json` from disk, normalise non-English tickets to English, classify (LLM stage 1), retrieve the top 2 KB articles (deterministic TF-IDF), score priority with the brief's formula in code, route to internal queues (LLM stage 2), and draft safe replies for the top 5 (LLM stage 3). Every stage writes an artifact to `outputs/`; every LLM call is logged; `validate.py` checks everything. Consumers: support agents (drafts behind a human review gate) and ops leads (summary).

## 2. Requirements (MoSCoW, tagged with the brief's own tier)

| MoSCoW | Brief | Requirement | How | Checked by |
|---|---|---|---|---|
| Must | MUST 1 | Multilingual preprocessing, originals preserved | `language_hint` != `en` → LLM translation; offline: keyword glossary gloss | validate: non-en tickets keep original + English text |
| Must | MUST 2 | One batched Stage 1 classification call, controlled vocab | single prompt with all tickets + every vocabulary; each field validated, invalid → rule fallback per field | validate: vocab check |
| Must | MUST 3 | Top-2 retrieval from `kb_articles.json`, reproducible | TF-IDF over title+body+tags+category; query = processed subject+message + intent words; ties by article_id | validate: exactly 2, valid IDs; test: rerun identical |
| Must | MUST 4 | Deterministic priority formula, top 5 flagged | pure function of classification + tier + top score | validate: recompute and compare |
| Must | MUST 5 | Separate Stage 2 routing call | one call with classified tickets, retrieval, top-5, queue vocab; queues validated | validate: queue vocab |
| Must | MUST 6 | Separate Stage 3 reply drafts for top 5 only | prompt holds only retrieved KB text; citations must be a subset of retrieved IDs; banned-phrase check; else template fallback | validate: drafts for all top 5, citations ⊆ retrieved |
| Must | Stages | 10 named stages enforced in code | `Pipeline` state machine: a transition out of order raises | `outputs/run_state.json` order checked |
| Must | Logging | `llm_calls.jsonl` with stage, timestamp, provider, model, prompt_hash, input_artifacts, output_artifact | `llm_client` writes one record per stage call (offline fallback logged as provider `offline`) | validate: separate records per stage |
| Must | Validation | `python validate.py` covering all 13 listed checks, non-zero exit on failure | | itself + pytest |
| Should | SHOULD 7 | `retrieval_quality.json` | deterministic: top score < 0.55, small top-2 margin, or article category not matching intent | |
| Should | SHOULD 8 | `ops_summary.md` | deterministic counts from artifacts | |
| Could | STRETCH 10 | `validation_report.md` | written by `validate.py` | |
| Could | STRETCH 9 | `handoff_memory.json` | deterministic, built from classification, routing and retrieved KB text (no extra LLM call, so it is reproducible) | validate: covers top 5, required fields |
| Won't | — | embeddings/vector DB, UI, language-detection library, real queue integration, sending replies | out of scope for 60 min; drafts are never sent | |

## 3. Inputs

- `tickets.json`, `kb_articles.json` at repo root (defaults; override with `--tickets` / `--kb`).
- Loader checks required fields and duplicate IDs and fails fast with a clear message.
- **Assumption:** the evaluator's replacement files keep the same field names; IDs, order, wording and languages may differ.

## 4. Output schemas

Exactly as in the brief, sections MUST 1–6. Artifacts go to `outputs/` (override with `--out-dir`).
`classified_tickets.json.original_language` / `translated` are copied from preprocessing by code, not taken from the LLM.

## 5. Pipeline stages

```text
INIT -> TICKETS_LOADED -> PREPROCESSING_COMPLETE -> TICKETS_CLASSIFIED -> KB_RETRIEVAL_COMPLETE
 -> PRIORITY_SCORES_COMPUTED -> ROUTING_COMPLETE -> REPLY_DRAFTS_GENERATED -> VALIDATION_COMPLETE -> RESULTS_FINALISED
```

| Stage reached | Work | LLM? | Deterministic? |
|---|---|---|---|
| TICKETS_LOADED | read + schema-check both files | no | yes |
| PREPROCESSING_COMPLETE | translate non-en tickets | yes (translation) | fallback yes |
| TICKETS_CLASSIFIED | Stage 1 batched classification | yes | fallback yes |
| KB_RETRIEVAL_COMPLETE | TF-IDF top 2 | no | yes |
| PRIORITY_SCORES_COMPUTED | formula, sort, top 5 | no | yes |
| ROUTING_COMPLETE | Stage 2 routing | yes | fallback yes |
| REPLY_DRAFTS_GENERATED | Stage 3 drafts for top 5 | yes | fallback yes |
| VALIDATION_COMPLETE | run validate checks in-process | no | yes |
| RESULTS_FINALISED | quality notes, ops summary, run_state | no | yes |

## 6. Decisions and trade-offs

| Component | Choice | Why | Swappable via |
|---|---|---|---|
| Translation | LLM, glossary fallback | a batch of 12 tickets doesn't justify an MT dependency; offline still produces English keywords | `preprocess.translate()` |
| Classifier | LLM proposes, rules fill any invalid field | brief requires an LLM call; rules keep it running offline and catch off-vocabulary output | `classify.py` |
| Risk flags | final = LLM **OR** keyword rule | never under-flag a regulator threat or blocked funds | `classify.py` |
| Retrieval | pure-Python TF-IDF + cosine (scikit-learn dropped mid-session: its DLL was blocked by Windows Application Control) | reproducible, no key, no compiled dependency, fine for 10 articles | `retrieve.py` |
| Priority | pure Python formula | brief: never the LLM | `priority.py` |
| Safety label | code sets a floor: legal threat → `needs_legal_or_compliance_review`; compliance intents → at least `needs_specialist_review` | LLM may only make it stricter | `route.py` |
| Drafts | LLM with retrieved KB only; template fallback | citations and banned phrases are checked in code | `draft.py` |

## 7. Safety and edge cases

- Drafts: no timelines or outcomes unless they are in the KB; never reveal internal triggers; each draft gets a `review_gate_note` (a human must approve before sending).
- Banned-phrase check on drafts (`guarantee`, `will be approved`, `within N hours/days`, `refund will`) → template fallback.
- LLM returns bad JSON, a missing ticket or an unknown label → per-ticket rule fallback, recorded in the log.
- Priority ties → `created_at` ascending, then `ticket_id`, so the order doesn't depend on input order.
- No key → whole pipeline runs offline; log records say `provider: offline`.

## 8. Test plan

- `validate.py`: all 13 checks from the brief; exit 1 on any failure; writes `outputs/validation_report.md`.
- pytest: priority formula on hand-built cases; retrieval reproducible and exactly 2; **swap test**: shuffled tickets with renamed IDs still produce the same per-ticket results; offline run end to end.

## 9. Time plan (start 19:35)

| By | Target |
|---|---|
| 19:47 | this spec pushed |
| 20:10 | offline pipeline end to end |
| 20:20 | validate.py + tests green |
| 20:27 | LLM path with fallback |
| 20:32 | README, final push |

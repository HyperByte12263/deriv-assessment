# Deriv hands-on assessment: replayable support-ops pipeline

> **Provenance:** the scaffold (`llm_client.py` provider wrapper, test setup, `SPEC.md`/`README.md` templates) was prepared before the session. Everything problem-specific was written during the session; see the commit history.

## Problem

Ingest support tickets and a help-centre KB from disk, normalise multilingual tickets to English, classify intent/urgency/sentiment/risk (LLM stage 1), retrieve the top 2 KB articles, compute priority in code, route to internal queues (LLM stage 2), and draft safe replies for the top 5 tickets behind a human review gate (LLM stage 3). Full brief: [`docs/BRIEF.md`](docs/BRIEF.md). Design: [`SPEC.md`](SPEC.md).

## Run

```bash
pip install -r requirements.txt
python main.py          # runs every stage, writes outputs/
python validate.py      # 22 checks (the brief's list + optional artifacts); exit 1 on any failure; writes outputs/validation_report.md
python -m pytest -q     # 8 tests, run offline
```

- **No key needed.** With no key, every LLM stage uses a deterministic rules fallback, and `llm_calls.jsonl` records it as `provider: offline`. To enable the LLM, copy `.env.example` to `.env` and set `GEMINI_API_KEY` (or `ANTHROPIC_API_KEY`).
- **Swapped fixtures:** `python main.py --tickets other_tickets.json --kb other_kb.json --out-dir out2`, then `python validate.py --tickets other_tickets.json --kb other_kb.json --out-dir out2`.
- Inputs `tickets.json` and `kb_articles.json` sit at the repo root. Artifacts go to `outputs/`. The committed `outputs/` come from a live Gemini run.

## Architecture

```text
INIT -> TICKETS_LOADED -> PREPROCESSING_COMPLETE -> TICKETS_CLASSIFIED -> KB_RETRIEVAL_COMPLETE
 -> PRIORITY_SCORES_COMPUTED -> ROUTING_COMPLETE -> REPLY_DRAFTS_GENERATED -> VALIDATION_COMPLETE -> RESULTS_FINALISED
```

`main.Pipeline` is a state machine. Advancing to anything but the next stage raises an error, and each transition is written to `outputs/run_state.json`.

| Module | Role | LLM? |
|---|---|---|
| `main.py` | loader (schema + duplicate-ID checks), stage orchestration, artifact writing | – |
| `preprocess.py` | non-English/mixed tickets → English; keeps originals → `preprocessed_tickets.json` | translation call; glossary fallback |
| `classify.py` | **Stage 1**: one batched call → `classified_tickets.json` | yes; keyword-rules fallback |
| `retrieve.py` | pure-Python TF-IDF + cosine over `kb_articles.json`, top 2 → `retrieval_results.json` | no |
| `priority.py` | the brief's formula, sort, top 5 expedited → `priority_scores.json` | **never** |
| `route.py` | **Stage 2**: queues + safety label → `routing_decisions.json` | yes; intent→queue fallback |
| `draft.py` | **Stage 3**: top-5 drafts + review gate → `reply_drafts.json` | yes; KB-template fallback |
| `reports.py` | `retrieval_quality.json`, `ops_summary.md`, `handoff_memory.json` (deterministic, built from classification, routing and retrieved KB guidance) | no |
| `validate.py` | all brief checks + `validation_report.md` | no |
| `vocab.py` | controlled vocabularies, stage names, formula constants | – |
| `llm_client.py` | single LLM boundary: provider, temperature 0, one retry, JSON parsing, `llm_calls.jsonl` | – |

## Design choices

- **The LLM proposes, code decides.** Every LLM field is checked against the vocabularies in `vocab.py`. An invalid or missing field falls back to the rules value for that ticket and field. The `*_source` field in each artifact records which path was used.
- **Risk flags are LLM OR rules.** A model miss can never hide a regulator threat or blocked funds, so it can't lower a ticket's priority.
- **Safety-label floor in code.** A legal or regulatory threat, account restriction or privacy request → `needs_legal_or_compliance_review`. Specialist cases → at least `needs_specialist_review`. The model may only make the label stricter, and legal threats always add Compliance (tested).
- **Drafts are grounded and gated.** The prompt holds only the retrieved KB text. Citations must be a subset of the retrieved IDs. A banned-phrase check (guarantees, "within N days", "shortly", internal triggers, agent-facing KB wording) sends a failing draft to the safe template. `review_gate_note` is set by code, never by the model. In the committed run, T09's LLM draft failed this check ("should be escalated") and used the template.
- **Retrieval runs after classification.** The query is the English text plus the classified intent. A filler second hit (score < 0.15) is never quoted in a draft.
- **Deterministic ordering.** Priority ties sort by `created_at`, then `ticket_id`. Articles are sorted by ID before indexing, so input file order never matters (tested with shuffled, renamed tickets).
- **LLM log** (`outputs/llm_calls.jsonl`): one record per call or attempt, with `stage`, `timestamp`, `provider`, `model`, `prompt_hash`, `input_artifacts`, `output_artifact`, plus the error and response for traceability. Retrieval is pure code, so it isn't logged.

## Limitations and next steps

- **The 0.55 weak-retrieval threshold doesn't fit TF-IDF cosine.** Scores on short KB articles sit around 0.3–0.56, so most tickets get the +8 bonus. I kept the brief's formula and the honest score rather than inflating it. `retrieval_quality.json` flags each case. Next step: calibrate the threshold on labelled data, or blend in embedding similarity.
- **The offline translation is a small Malay/Hinglish glossary.** It produces rough English that's good enough for keyword rules and TF-IDF. A new language offline would pass through untranslated (the LLM path handles it).
- **scikit-learn was dropped.** Windows Application Control blocked its compiled DLL on the dev machine, so TF-IDF is about 30 lines of pure Python. The behaviour matches sklearn's smoothed-IDF, sublinear-TF setup.
- **Exactly 2 articles per ticket**, as required, even when only one is relevant. The second is then marked as filler in `retrieval_quality.json`.
- Not done: embeddings, multi-turn conversations, real queue integration. Drafts are never sent.

## How AI tools were used

I used Claude Code as a pair programmer. I wrote the brief breakdown and the MoSCoW spec first and reviewed them, then had Claude implement against the spec stage by stage. Examples of output I checked and corrected rather than accepted:
- **Translation:** the model returned `message` instead of `message_en`, so the code silently fell back to the glossary. Now either key is accepted, but an untranslated echo is still rejected.
- **Drafts:** reading the drafts showed "will review your case shortly" (an unsupported timeline) and KB wording meant for agents ("a customer… should be escalated"). Both are now banned-phrase checks.
- **Filler article:** the template quoted a near-zero-score second article (statement exports) in a regulator-threat reply. A relevance floor was added.
- **Two silent patch failures:** two of Claude's string-replace edits didn't match and changed nothing. I caught it by re-reading the output and redid them as exact edits.
- **Environment:** the scikit-learn DLL was blocked, so we replaced it with pure Python instead of debugging the machine.

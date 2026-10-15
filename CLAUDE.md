# CLAUDE.md

A timed (60 min), screen-recorded hands-on assessment for an AI engineering role at **Deriv**. The problem brief arrives at the start of the session; paste it verbatim into `docs/BRIEF.md`. The brief is the source of truth: where it conflicts with anything below, the brief wins.

## Domain

Deriv runs an online trading platform (CFDs, options, multipliers on forex, indices, commodities, crypto) for retail clients across several regulated jurisdictions. Day-to-day data: client support conversations, deposits and withdrawals across many payment methods, identity verification (KYC) documents, trading activity, risk/fraud signals, and internal policy or help-centre text.

Likely problem shapes, each a small Python pipeline of input files → AI step → validated output files:
- **Classify / route / triage** free text (tickets, emails, chats) into a fixed label set, with priority and escalation.
- **Grounded Q&A** over provided documents, citing sources and refusing when the documents don't support an answer.
- **Extraction** of structured fields from unstructured text, checked against a schema.
- **Scoring / flagging** records (risk, priority, anomalies) where rules decide and the LLM assists.
- **Evaluation** of an LLM step against labelled data, with metrics computed in code.

## Guardrails that hold for any brief

- Replies to clients: no financial or trading advice, no market predictions, no profit promises; decline politely.
- No promises about payment or withdrawal outcomes or timelines; state only facts present in the inputs.
- Compliance-sensitive cases (verification, AML, withdrawals, account restrictions, legal threats, vulnerable clients) route to a human.
- Every decision is traceable to its inputs and sources; every LLM call is logged.

## Engineering conventions

- Python 3.10+. Run from repo root: `python main.py`, `python validate.py`, `python -m pytest -q`.
- `main.py` runs named stages via `run_stage()`; stage names follow the brief.
- All LLM calls go through `llm_client.complete()` / `complete_json()`, which return None when offline; each caller has a deterministic fallback, and the pipeline runs end to end with no API key.
- Code owns every checkable decision (labels, scores, IDs, refusals); LLM output is validated before use.
- Logic keys on content and schema, so the evaluator can swap in new inputs with new IDs.
- Inputs live in `data/`, generated artifacts in `outputs/` (committed).

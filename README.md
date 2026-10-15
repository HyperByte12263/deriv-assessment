# Deriv hands-on assessment

> **Provenance:** the scaffold (`llm_client.py`, test setup, `SPEC.md`/`README.md` templates) was prepared before the session. Everything problem-specific was written during the session; see the commit history.

## Problem

_TODO: one paragraph. Full brief in [`docs/BRIEF.md`](docs/BRIEF.md), design in [`SPEC.md`](SPEC.md)._

## Run

```bash
pip install -r requirements.txt
python main.py          # writes outputs/
python validate.py      # checks outputs, exits non-zero on failure
python -m pytest -q
```

Runs fully offline. To enable the LLM path, copy `.env.example` to `.env` and set one key.

## Architecture

_TODO: stage diagram and one line per module._

## Design choices

_TODO_

## Limitations and next steps

_TODO_

## How AI tools were used

_TODO: what was generated, what was reviewed or rejected, and why._

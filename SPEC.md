# SPEC

> Written before implementation. Brief: [`docs/BRIEF.md`](docs/BRIEF.md).

## 1. Problem in one paragraph

_TODO: what goes in, what comes out, who uses the output._

## 2. Requirements

| Tier | Requirement | How it is satisfied | Checked by |
|---|---|---|---|
| MUST | | | |
| SHOULD | | | |
| STRETCH | | | |

## 3. Inputs

_TODO: files, fields, assumptions; what happens on malformed input._

## 4. Output schema

```json
{}
```

## 5. Pipeline stages

```text
STAGE_1 -> STAGE_2 -> ...
```

| Stage | Input | Output | Deterministic? |
|---|---|---|---|

## 6. Decisions and trade-offs

| Component | Choice | Why | Swappable via |
|---|---|---|---|

## 7. Safety and edge cases

_TODO: refusals, escalation rules, empty/unsupported cases, swapped inputs._

## 8. Test plan

_TODO: each MUST maps to a test or validate.py check._

## 9. Time plan

| By | Target |
|---|---|
| 12 min | this spec pushed |
| 35 min | offline pipeline end to end |
| 45 min | validate.py + tests green |
| 52 min | LLM path with fallback |
| 57 min | README, final push |

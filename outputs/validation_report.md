# Validation report

**21/21 checks passed**

| Check | Result | Detail |
|---|---|---|
| required artifacts exist | PASS |  |
| JSON files are valid | PASS |  |
| all tickets processed: preprocessed | PASS | got 12 of 12 |
| all tickets processed: classified | PASS | got 12 of 12 |
| all tickets processed: retrieval | PASS | got 12 of 12 |
| all tickets processed: priority | PASS | got 12 of 12 |
| all tickets processed: routing | PASS | got 12 of 12 |
| non-English tickets keep original text and have English processing text | PASS | [] |
| classified outputs use only controlled vocabularies | PASS | [] |
| retrieval references valid article IDs | PASS | [] |
| each ticket has exactly 2 retrieved articles | PASS | [] |
| priority scores recompute identically from classification + retrieval | PASS |  |
| priority computed after retrieval (run_state order) | PASS | INIT -> TICKETS_LOADED -> PREPROCESSING_COMPLETE -> TICKETS_CLASSIFIED -> KB_RETRIEVAL_COMPLETE -> PRIORITY_SCORES_COMPUTED -> ROUTING_COMPLETE -> REPLY_DRAFTS_GENERATED -> VALIDATION_COMPLETE -> RESULTS_FINALISED |
| stages ran in the brief's order | PASS | INIT -> TICKETS_LOADED -> PREPROCESSING_COMPLETE -> TICKETS_CLASSIFIED -> KB_RETRIEVAL_COMPLETE -> PRIORITY_SCORES_COMPUTED -> ROUTING_COMPLETE -> REPLY_DRAFTS_GENERATED -> VALIDATION_COMPLETE -> RESULTS_FINALISED |
| top 5 expedited tickets selected from computed scores | PASS | ['T07', 'T02', 'T01', 'T09', 'T11'] vs ['T07', 'T02', 'T01', 'T09', 'T11'] |
| routing uses only the controlled queue vocabulary and safety labels | PASS | [] |
| reply drafts exist for all top 5 priority tickets | PASS | drafted ['T01', 'T02', 'T07', 'T09', 'T11'], expected ['T01', 'T02', 'T07', 'T09', 'T11'] |
| reply drafts cite retrieved KB articles | PASS | [] |
| reply drafts have text and a human review gate note | PASS | [] |
| LLM call log has separate records for classification, routing, drafting | PASS | PREPROCESSING_TRANSLATION, STAGE1_CLASSIFICATION, STAGE2_ROUTING, STAGE3_REPLY_DRAFTING |
| LLM call records include all required fields | PASS | bad lines [] |

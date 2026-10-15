"""Pipeline entry point: a state machine over the brief's stages. Every stage writes its artifact to --out-dir."""
import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import classify
import draft
import llm_client
import preprocess
import reports
import retrieve
import route
import validate
from schemas import ARTIFACT_SCHEMAS, ensure_valid
from priority import compute_priorities
from vocab import STAGES

log = logging.getLogger("pipeline")

TICKET_FIELDS = ["ticket_id", "channel", "customer_tier", "subject", "message"]
KB_FIELDS = ["article_id", "title", "body"]


class Pipeline:
    """Enforces the stage order: advancing to anything but the next stage raises."""

    def __init__(self, out_dir):
        self.out_dir = Path(out_dir)
        self.state = "INIT"
        self.history = [{"state": "INIT", "at": now()}]
        self._started = time.perf_counter()
        self._save()

    def advance(self, new_state):
        expected = STAGES[STAGES.index(self.state) + 1]
        if new_state != expected:
            raise RuntimeError(f"illegal transition {self.state} -> {new_state} (expected {expected})")
        self.state = new_state
        self.history.append({"state": new_state, "at": now()})
        log.info("[%s] reached (%.2fs)", new_state, time.perf_counter() - self._started)
        self._save()

    def _save(self):
        write_json(self.out_dir / "run_state.json", {"state": self.state, "history": self.history,
                                                    "llm_provider": llm_client.provider() or "offline"})


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    path = Path(path)
    if path.name in ARTIFACT_SCHEMAS:
        ensure_valid(path.name, data)  # fail fast at the stage that produced bad data
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def load_records(path, id_field, fields):
    records = read_json(path)
    if not isinstance(records, list):
        raise SystemExit(f"{path}: expected a JSON array")
    for i, r in enumerate(records):
        missing = [f for f in fields if f not in r]
        if missing:
            raise SystemExit(f"{path}[{i}]: missing fields {missing}")
    ids = [r[id_field] for r in records]
    if len(ids) != len(set(ids)):
        raise SystemExit(f"{path}: duplicate {id_field} values")
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickets", default="tickets.json")
    parser.add_argument("--kb", default="kb_articles.json")
    parser.add_argument("--out-dir", default="outputs")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    llm_client.LOG_PATH = out / "llm_calls.jsonl"
    llm_client.LOG_PATH.unlink(missing_ok=True)  # the log describes this run only
    p = lambda name: str(out / name)  # noqa: E731  artifact path as logged

    pipe = Pipeline(out)
    log.info("LLM provider: %s", llm_client.provider() or "none (offline rules fallback)")

    tickets = load_records(args.tickets, "ticket_id", TICKET_FIELDS)
    articles = load_records(args.kb, "article_id", KB_FIELDS)
    if len(articles) < retrieve.TOP_K:
        raise SystemExit(f"{args.kb}: need at least {retrieve.TOP_K} articles to return the top {retrieve.TOP_K}")
    pipe.advance("TICKETS_LOADED")

    pre = preprocess.preprocess(tickets, [args.tickets], p("preprocessed_tickets.json"))
    write_json(p("preprocessed_tickets.json"), pre)
    pipe.advance("PREPROCESSING_COMPLETE")

    cls = classify.classify(pre, [p("preprocessed_tickets.json")], p("classified_tickets.json"))
    write_json(p("classified_tickets.json"), cls)
    pipe.advance("TICKETS_CLASSIFIED")

    ret = retrieve.retrieve(pre, cls, articles)
    write_json(p("retrieval_results.json"), ret)
    pipe.advance("KB_RETRIEVAL_COMPLETE")

    prio = compute_priorities(tickets, cls, ret)
    write_json(p("priority_scores.json"), prio)
    pipe.advance("PRIORITY_SCORES_COMPUTED")

    routes = route.route(cls, ret, prio, [p("classified_tickets.json"), p("retrieval_results.json"),
                                          p("priority_scores.json")], p("routing_decisions.json"))
    write_json(p("routing_decisions.json"), routes)
    pipe.advance("ROUTING_COMPLETE")

    drafts = draft.draft_replies(tickets, pre, ret, prio, routes, articles,
                                 [p("preprocessed_tickets.json"), p("retrieval_results.json"), p("priority_scores.json"),
                                  p("routing_decisions.json"), args.kb], p("reply_drafts.json"))
    write_json(p("reply_drafts.json"), drafts)
    pipe.advance("REPLY_DRAFTS_GENERATED")

    results = validate.run_checks(args.tickets, args.kb, out)
    validate.write_report(results, out)
    failed = [name for name, ok, _ in results if not ok]
    if failed:
        log.error("validation failed: %s", failed)
        sys.exit(1)
    pipe.advance("VALIDATION_COMPLETE")

    write_json(p("retrieval_quality.json"), reports.retrieval_quality(ret))
    Path(p("ops_summary.md")).write_text(reports.ops_summary(tickets, cls, ret, prio, routes), encoding="utf-8")
    write_json(p("handoff_memory.json"), reports.handoff_memory(pre, cls, ret, prio, routes, articles))
    pipe.advance("RESULTS_FINALISED")
    validate.write_report(validate.run_checks(args.tickets, args.kb, out), out)  # final report includes optional artifacts
    log.info("done: %d tickets, top 5 = %s", len(tickets), [r["ticket_id"] for r in prio if r["expedited"]])


if __name__ == "__main__":
    main()

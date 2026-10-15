"""Pipeline entry point. Stages are defined during the session from SPEC.md."""
import argparse
import json
import logging
import time
from pathlib import Path

log = logging.getLogger("pipeline")


def run_stage(name, fn, *args, **kwargs):
    """Run one named stage with timing, so the log shows the pipeline shape."""
    log.info("[%s] start", name)
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    log.info("[%s] done in %.2fs", name, time.perf_counter() - start)
    return result


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=False)
        f.write("\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--out-dir", default="outputs")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    # Stages go here, e.g.:
    # records = run_stage("LOAD_DATA", load_records, Path(args.data_dir) / "input.json")
    raise SystemExit("No stages defined yet - see SPEC.md")


if __name__ == "__main__":
    main()

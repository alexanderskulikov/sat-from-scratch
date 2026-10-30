"""One-command correctness and benchmark verification: python3 -m tests."""

import argparse
import json
import os
import sys
import unittest
from pathlib import Path

from tests.benchmark import run_benchmarks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="omit the 80 repository benchmarks")
    parser.add_argument("--results", type=Path, help="write detailed benchmark measurements as JSON")
    parser.add_argument("--artifacts", type=Path, help="retain benchmark output and proof files")
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    if args.quick:
        return 0
    artifacts = args.artifacts
    if artifacts is None and os.environ.get("AIR_ARTIFACTS_DIR"):
        artifacts = Path(os.environ["AIR_ARTIFACTS_DIR"]) / "sat-verification"
    report = run_benchmarks(artifacts)
    if args.results is not None:
        args.results.parent.mkdir(parents=True, exist_ok=True)
        args.results.write_text(json.dumps(report, indent=2) + "\n")
    if artifacts is not None:
        (artifacts / "benchmark_results.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if all(record["solved"] for record in report["formulas"]) else 1


if __name__ == "__main__":
    sys.exit(main())

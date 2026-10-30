"""Run every listed benchmark in a fresh process and verify its certificate."""

import csv
import hashlib
import io
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import check


ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_benchmarks(artifacts=None):
    bench = ROOT / "bench"
    with (bench / "answers.csv").open(newline="") as stream:
        expected = list(csv.DictReader(stream))
    filenames = [row["file"] for row in expected]
    if len(set(filenames)) != len(filenames):
        raise ValueError("duplicate benchmark in answers.csv")
    if set(filenames) != {path.name for path in bench.glob("*.cnf")}:
        raise ValueError("answers.csv must cover every benchmark exactly once")
    if any(row["answer"] not in ("SAT", "UNSAT") for row in expected):
        raise ValueError("unrecognized benchmark answer")
    if artifacts is not None:
        artifacts.mkdir(parents=True, exist_ok=True)
    records = []
    with tempfile.TemporaryDirectory(prefix="sat-verification-") as temporary:
        outputs = artifacts if artifacts is not None else Path(temporary)
        for row in expected:
            formula = bench / row["file"]
            nvars, clauses = check.read_formula(formula)
            proof = outputs / (formula.stem + ".drat")
            record = dict(file=row["file"], variables=nvars, clauses=len(clauses),
                          expected=row["answer"], formula_sha256=digest(formula),
                          solved=False)
            start = time.perf_counter()
            try:
                result = subprocess.run(
                    [sys.executable, str(ROOT / "solver.py"), str(formula), "--proof", str(proof)],
                    capture_output=True, text=True, timeout=60, cwd=ROOT,
                )
                record["solver_seconds"] = time.perf_counter() - start
                record["returncode"] = result.returncode
                (outputs / (formula.stem + ".out")).write_text(result.stdout)
                if result.stderr:
                    (outputs / (formula.stem + ".err")).write_text(result.stderr)
                expected_code = 10 if row["answer"] == "SAT" else 20
                if result.returncode != expected_code:
                    raise ValueError(f"expected exit {expected_code}, got {result.returncode}: {result.stderr}")
                verification_start = time.perf_counter()
                if row["answer"] == "SAT":
                    check.check_model(nvars, clauses, io.StringIO(result.stdout))
                    record["certificate"] = "full model"
                else:
                    if result.stdout != "s UNSATISFIABLE\n":
                        raise ValueError("invalid UNSAT status output")
                    with proof.open() as stream:
                        record["proof_additions"] = check.check_proof(nvars, clauses, stream)
                    record["certificate"] = "RUP refutation"
                record["verification_seconds"] = time.perf_counter() - verification_start
                record["proof_bytes"] = proof.stat().st_size
                record["proof_sha256"] = digest(proof)
                if record["solver_seconds"] > 60:
                    raise ValueError("exceeded the 60-second solver budget")
                record["solved"] = True
            except subprocess.TimeoutExpired:
                record["solver_seconds"] = time.perf_counter() - start
                record["error"] = "solver timed out after 60 seconds"
            except (ValueError, OSError) as error:
                record["error"] = str(error)
            records.append(record)
            state = "verified" if record["solved"] else "FAILED: " + record["error"]
            print(f"{formula.name}: {row['answer']:5} {record.get('solver_seconds', 0):.3f}s {state}",
                  flush=True)
    groups = []
    for size in sorted({record["variables"] for record in records}):
        rows = [record for record in records if record["variables"] == size]
        times = [record["solver_seconds"] for record in rows]
        groups.append(dict(variables=size, formulas=len(rows),
                           solved=sum(record["solved"] for record in rows),
                           mean_seconds=statistics.mean(times), max_seconds=max(times)))
    print("\nVariables  Formulas  Verified  Mean (s)  Max (s)")
    for group in groups:
        print(f"{group['variables']:9} {group['formulas']:9} {group['solved']:9} "
              f"{group['mean_seconds']:9.4f} {group['max_seconds']:8.4f}")
    cpu = "unknown"
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        cpu = next((line.split(":", 1)[1].strip() for line in cpuinfo.read_text().splitlines()
                    if line.startswith("model name")), "unknown")
    return dict(timestamp_utc=datetime.now(timezone.utc).isoformat(),
                python=sys.version, platform=platform.platform(), cpu=cpu,
                solver_sha256=digest(ROOT / "solver.py"),
                checker_sha256=digest(ROOT / "check.py"),
                answers_sha256=digest(bench / "answers.csv"),
                timing="sequential fresh-process wall time, including startup, parsing, and proof I/O; checking excluded",
                timeout_seconds=60, groups=groups, formulas=records)

A SAT solver written from scratch in Python, with independent certificate
checking and reproducible tests. Python's standard library is the only dependency.

Run the solver:

```sh
python3 solver.py bench/n050_00.cnf
python3 solver.py bench/n050_03.cnf --proof proof.drat
```

SAT returns exit code **10** and prints a complete assignment. UNSAT returns
**20**. Input or I/O errors return **2** and print a diagnostic on stderr.
The nonzero SAT/UNSAT exit codes are intentional SAT Competition conventions.
DIMACS requires one `p cnf N M` header and exactly M zero-terminated clauses;
comments, blank lines, multiline clauses, and multiple clauses per line are
supported.

Check a result independently:

```sh
python3 solver.py bench/n050_00.cnf > model.txt
python3 check.py bench/n050_00.cnf --model model.txt
python3 check.py bench/n050_03.cnf --proof proof.drat
```

The checker returns **0** for a verified certificate and **1** for a rejected
certificate or input error. UNSAT requires a proof ending in a verified empty
clause; a status line alone is insufficient. The proof checker accepts RUP
additions and clause deletions, which cover this solver's output. It is not a
checker for arbitrary RAT proofs. A proof file produced during a SAT run may
contain learned clauses but is not an UNSAT certificate.

Run all correctness tests and all 80 benchmarks with one command:

```sh
python3 -m tests
```

To record fresh measurements and retain the benchmark certificates:

```sh
python3 -m tests --results results.json --artifacts verification
```

Each benchmark solver process has a 60-second timeout. Without `--artifacts`,
the suite retains outputs under `AIR_ARTIFACTS_DIR/sat-verification` when that
environment variable is set, otherwise it uses a temporary directory.
`python3 -m tests --quick` runs the correctness tests without the repository
benchmarks. The measured results and limitations are documented in
[REPORT.md](REPORT.md), with individual measurements in
[benchmark_results.json](tests/benchmark_results.json).

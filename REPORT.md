All **80 of 80** repository benchmarks were solved within 60 seconds each,
agreed with the supplied answers, and passed independent certificate checks:
43 satisfying assignments and 37 UNSAT proofs. The slowest solver invocation
took **1.269 seconds** on the available host. No test was weakened or skipped
after a failure, and no benchmark file was modified.

The implementation in [solver.py](solver.py) uses two watched literals,
trail-based propagation, first-UIP resolution, non-chronological backjumping,
EVSIDS variable activity with a heap, Luby restarts, and phase saving. Activity
starts with occurrence counts, conflict bumps decay by a factor of 0.95, and
the restart unit is 64 conflicts. Initial phases are false. Ties use variable
numbers, making runs deterministic. Activity rescaling and periodic heap
rebuilding bound numerical growth and stale heap entries. There is no learned
clause deletion, learned clause minimization, or substantial preprocessing;
input normalization removes duplicate literals and tautological clauses.

The solver assigns every declared variable, including unused variables. Empty
formulas, empty clauses, conflicting units, duplicate clauses, tautologies,
and zero-variable instances are supported. DIMACS parsing checks the header,
literal ranges, clause terminators, and declared clause count. Malformed input
produces an error rather than a SAT/UNSAT answer. The solver uses only Python's
standard library, starts no processes, and never reads the answers file or
examines the formula's filename to choose an answer.

With `--proof`, every learned clause is streamed before it is added to the
database. A level-zero contradiction emits the final empty clause. Each
learned clause is obtained by resolution on implication reasons; assignments
at level zero can be omitted because unit propagation can reconstruct them.
The resulting proof uses RUP additions, a subset of DRAT. No deletion lines
are emitted. A SAT run may leave a prefix of learned clauses without an empty
clause. Existing proof destinations are overwritten, except that the solver
rejects paths or hard links that alias its input formula.

The independent [check.py](check.py) imports no solver code and contains its own
DIMACS parser. Its model checker requires a total, consistent assignment,
rejects out-of-range variables, and evaluates every original clause directly.
Its proof checker negates each proposed lemma and derives a conflict by unit
propagation using literal occurrence lists and remaining-literal counts. It
does not use watched literals, the solver's trail, conflict analysis, or the
solver's assignment. Each accepted lemma is then added to the checker's own
database. Every UNSAT proof must finish with a verified empty clause. Deletions
remove one matching clause copy; duplicate literals are normalized and clause
multiplicity is preserved. Absent-clause deletions are rejected.

This establishes a concrete trust argument: a checked model satisfies the
original input, and a checked RUP sequence derives a contradiction from that
input. An expected-answer match alone is not considered verification. The
checker is still software written for this task; it is not a formally verified
kernel. Its core propagation rule was therefore also compared against a
separate, deliberately simple full-clause-scan implementation and truth-table
search.

The complete reproducible command used was:

```sh
python3 -m tests --results tests/benchmark_results.json
```

The 13 correctness test methods passed in 4.570 seconds. Their coverage includes:

- **3,000 random formulas**, 250 for each variable count from 1 through 12,
  with seed 20261030. These include uniform 3-CNF, planted satisfiable formulas,
  mixed clause lengths, duplicate literals, tautologies, and occasional empty
  clauses. Each answer is compared with exhaustive truth-table search, and
  each model or refutation is independently checked. One third of cases use a
  restart unit of one to exercise frequent restarts.
- **All 512 subsets of the nine canonical clauses over two variables**,
  including the empty clause. These cover all canonical two-variable formulas
  without duplicate clauses or tautologies. Every answer and certificate is
  checked against brute force.
- **100 additional transformations**, seed 81173, that permute variables,
  flip variable polarities, and shuffle clauses and literals, with answers
  compared to brute force on the original formula.
- **6,000 RUP queries** across 1,000 random databases, seed 42801, compared to
  the full-scan reference. Repeated queries exercise count rollback; accepted
  lemmas are additionally checked by brute force. Additions and deletions
  between queries exercise the changing database and duplicate-clause handling.
- Boundary cases, 2,500-variable implication chains and a long clause,
  a six-pigeons/five-holes refutation, and checks that learning, restarts, and
  non-chronological backjumps actually occur.
- CLI exit codes, output syntax, independent checker CLI invocations, filename
  independence from an unrelated working directory, and execution with Python
  assertions disabled. Invalid DIMACS, incomplete or contradictory models,
  forged lemmas, truncated proofs, missing derivations, invalid deletions, and
  instructions after a final empty clause are rejected.

Every benchmark is run sequentially in a fresh solver process with `--proof`
and a 60-second timeout. The harness checks that the answers CSV covers every
benchmark exactly once, checks the process exit code and output, and validates
the certificate. All **24,993 proof additions**, including the 37 final empty
clauses, were RUP-checked. Certificate checking took 14.106 seconds in total;
the slowest individual check took 6.097 seconds. Solver invocations together
took 7.303 seconds.

The following measurements were collected on 2026-10-30 using CPython 3.12.3,
Linux x86-64, on a host reporting an AMD EPYC 7R13 processor. Times are single
runs measured with `time.perf_counter`, including process startup, parsing,
solving, and proof-file writing, but excluding certificate checking. Groups
use the declared variable count. Individual times, certificate counts, input
and proof SHA-256 hashes, and solver/checker hashes are recorded in
[benchmark_results.json](tests/benchmark_results.json).

| Variables | Formulas | Solved and verified | Mean seconds | Maximum seconds |
| ---: | ---: | ---: | ---: | ---: |
| 50 | 20 | 20 | 0.0335 | 0.0357 |
| 75 | 20 | 20 | 0.0385 | 0.0469 |
| 100 | 20 | 20 | 0.0558 | 0.0899 |
| 125 | 10 | 10 | 0.0908 | 0.1408 |
| 150 | 10 | 10 | 0.3837 | 1.2686 |

No known failing case remains in the checked suite. These measurements were
made in the supplied development environment, **not on a physical laptop**;
the large margin below 60 seconds is evidence, not a measurement of every
laptop's performance. There are no repeated timing trials or confidence
intervals. Other Python versions and operating systems were not tested.

There is no claim of completeness of testing on larger or industrial inputs.
CDCL can take exponential time, and retaining every learned clause can consume
substantial memory. The CLI has no internal timeout or resource limit; the
benchmark harness imposes its own timeout. Long-chain tests do not demonstrate
performance on large, difficult industrial instances. The activity-rescaling
threshold was not reached by this test suite. No external SAT solver or
third-party proof checker was used, and the supplied expected answers' original
derivation was not independently investigated. Shared misunderstandings of
formats or proof rules remain possible despite separate implementations,
brute-force comparisons, and deliberately invalid certificate tests.

The checker accepts textual RUP proofs with variables inside the formula's
declared range; it does not implement general RAT steps, variable-extension
proofs, or binary DRAT. The DIMACS readers require a header and full-line `c`
comments and do not support optional dialect extensions such as `%` end
markers. Benchmark SAT models and UNSAT refutations were checked; partial
learned-clause prefixes from SAT runs were not separately verified.

Decisions made without asking: use deterministic occurrence-seeded EVSIDS,
Luby restarts, false initial phases, strict DIMACS validation, complete models
split into 20-variable zero-terminated `v` lines, and a single independent
checker supporting both certificate types. Keep all learned clauses and omit
optional optimizations to keep the implementation inspectable. Use fixed
random seeds and standard-library `unittest`, measure complete subprocess
invocations rather than only the search loop, and preserve detailed measured
results. Work was performed without subagents. Milestones were committed
directly to main, as requested.

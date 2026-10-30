#!/usr/bin/env python3
"""A deterministic, standard-library-only CDCL SAT solver.

Literals are signed DIMACS integers. Clause positions 0 and 1 are watched.
The proof stream contains only RUP additions (a subset of DRAT).
"""

import argparse
import heapq
import sys
from pathlib import Path


def read_dimacs(path):
    """Read strict DIMACS, allowing comments and clauses spanning lines."""
    header = None
    clauses = []
    pending = []
    with open(path, encoding="ascii") as source:
        for line_number, line in enumerate(source, 1):
            words = line.split()
            if not words or words[0] == "c":
                continue
            if words[0] == "p":
                if header is not None or len(words) != 4 or words[1] != "cnf":
                    raise ValueError(f"line {line_number}: invalid or repeated header")
                n, m = map(int, words[2:])
                if n < 0 or m < 0:
                    raise ValueError("negative variable or clause count")
                header = n, m
                continue
            if header is None:
                raise ValueError(f"line {line_number}: expected 'p cnf N M'")
            for word in words:
                lit = int(word)
                if abs(lit) > header[0]:
                    raise ValueError(f"line {line_number}: literal outside declared range")
                if lit:
                    pending.append(lit)
                else:
                    clauses.append(pending)
                    pending = []
    if header is None:
        raise ValueError("missing DIMACS header")
    if pending:
        raise ValueError("unterminated clause")
    if len(clauses) != header[1]:
        raise ValueError("clause count does not match header")
    return header[0], clauses


def luby(index):
    """1-based Luby restart multipliers: 1, 1, 2, 1, 1, 2, 4, ..."""
    size = 1
    while size < index:
        size = 2 * size + 1
    while size != index:
        size = (size - 1) // 2
        index = (index - 1) % size + 1
    return (size + 1) // 2


class Solver:
    def __init__(self, nvars, clauses, proof=None, restart_base=64):
        if nvars < 0 or restart_base < 1:
            raise ValueError("invalid variable count or restart interval")
        self.nvars = nvars
        self.proof = proof
        self.clauses = []
        # Negative Python indices give each signed literal its own bucket.
        self.watches = [[] for _ in range(2 * nvars + 1)]
        self.values = [0] * (nvars + 1)
        self.levels = [0] * (nvars + 1)
        self.reasons = [-1] * (nvars + 1)
        self.phases = [-1] * (nvars + 1)
        self.activity = [0.0] * (nvars + 1)
        self.increment = 1.0
        self.trail = []
        self.limits = []
        self.qhead = 0
        self.initial_conflict = False
        self.restart_base = restart_base
        self.stats = dict(conflicts=0, decisions=0, propagations=0,
                          learned=0, restarts=0, backjumps=0)
        self.result = None
        for raw in clauses:
            if any(lit == 0 or abs(lit) > nvars for lit in raw):
                raise ValueError("invalid clause literal")
            clause = list(dict.fromkeys(raw))
            members = set(clause)
            if any(-lit in members for lit in clause):
                continue  # Tautologies impose no restriction.
            cid = self.add_clause(clause)
            for lit in clause:
                self.activity[abs(lit)] += 1.0
            if not clause:
                self.initial_conflict = True
            elif len(clause) == 1 and not self.enqueue(clause[0], cid):
                self.initial_conflict = True
        self.heap = [(-self.activity[v], v) for v in range(1, nvars + 1)
                     if not self.values[v]]
        heapq.heapify(self.heap)

    def add_clause(self, clause):
        cid = len(self.clauses)
        self.clauses.append(clause)
        if len(clause) >= 2:
            self.watches[clause[0]].append(cid)
            self.watches[clause[1]].append(cid)
        return cid

    def enqueue(self, lit, reason):
        var = abs(lit)
        value = 1 if lit > 0 else -1
        if self.values[var]:
            return self.values[var] == value
        self.values[var] = value
        self.phases[var] = value
        self.levels[var] = len(self.limits)
        self.reasons[var] = reason
        self.trail.append(lit)
        return True

    def propagate(self):
        values = self.values
        while self.qhead < len(self.trail):
            false_lit = -self.trail[self.qhead]
            self.qhead += 1
            self.stats["propagations"] += 1
            watching = self.watches[false_lit]
            i = 0
            while i < len(watching):
                cid = watching[i]
                clause = self.clauses[cid]
                if clause[0] == false_lit:
                    clause[0], clause[1] = clause[1], clause[0]
                other = clause[0]
                other_value = values[abs(other)] * (1 if other > 0 else -1)
                if other_value == 1:
                    i += 1
                    continue
                for k in range(2, len(clause)):
                    candidate = clause[k]
                    if values[abs(candidate)] * (1 if candidate > 0 else -1) >= 0:
                        clause[1], clause[k] = candidate, false_lit
                        self.watches[candidate].append(cid)
                        watching[i] = watching[-1]
                        watching.pop()
                        break
                else:
                    if other_value == -1:
                        return cid
                    self.enqueue(other, cid)
                    i += 1
        return -1

    def bump(self, var):
        self.activity[var] += self.increment
        if self.activity[var] > 1e100:
            self.activity = [score * 1e-100 for score in self.activity]
            self.increment *= 1e-100
            self.heap = [(-self.activity[v], v) for v in range(1, self.nvars + 1)
                         if not self.values[v]]
            heapq.heapify(self.heap)

    def analyze(self, conflict):
        """Resolve backwards on the trail until one current-level literal remains."""
        seen = [False] * (self.nvars + 1)
        learned = [0]
        open_paths = 0
        pivot = 0
        index = len(self.trail) - 1
        current_level = len(self.limits)
        while True:
            for lit in self.clauses[conflict]:
                var = abs(lit)
                if var == abs(pivot) or seen[var] or self.levels[var] == 0:
                    continue
                seen[var] = True
                self.bump(var)
                if self.levels[var] == current_level:
                    open_paths += 1
                else:
                    learned.append(lit)
            while not seen[abs(self.trail[index])]:
                index -= 1
            pivot = self.trail[index]
            index -= 1
            seen[abs(pivot)] = False
            open_paths -= 1
            if open_paths == 0:
                learned[0] = -pivot
                break
            conflict = self.reasons[abs(pivot)]
            assert conflict >= 0, "a decision cannot precede the first UIP"
        back_level = 0
        if len(learned) > 1:
            best = max(range(1, len(learned)),
                       key=lambda k: self.levels[abs(learned[k])])
            learned[1], learned[best] = learned[best], learned[1]
            back_level = self.levels[abs(learned[1])]
        self.increment /= 0.95
        return learned, back_level

    def backtrack(self, level):
        if len(self.limits) <= level:
            return
        cut = self.limits[level]
        for lit in self.trail[cut:]:
            var = abs(lit)
            self.values[var] = 0
            self.levels[var] = 0
            self.reasons[var] = -1
            heapq.heappush(self.heap, (-self.activity[var], var))
        del self.trail[cut:]
        del self.limits[level:]
        self.qhead = min(self.qhead, cut)
        # Bound stale heap entries without changing the ordering heuristic.
        if len(self.heap) > 4 * max(1, self.nvars):
            self.heap = [(-self.activity[v], v) for v in range(1, self.nvars + 1)
                         if not self.values[v]]
            heapq.heapify(self.heap)

    def decide(self):
        while self.heap:
            negative_score, var = heapq.heappop(self.heap)
            if not self.values[var] and -negative_score == self.activity[var]:
                return var * self.phases[var]
        return 0

    def emit(self, clause):
        if self.proof is not None:
            self.proof.write(" ".join(map(str, clause)) + (" 0\n" if clause else "0\n"))

    def solve(self):
        """Return SAT as a bool; a SAT model is in values[1:]."""
        if self.result is not None:
            return self.result
        if self.initial_conflict:
            self.emit([])
            self.result = False
            return False
        restart_index = 1
        since_restart = 0
        budget = self.restart_base * luby(restart_index)
        while True:
            conflict = self.propagate()
            if conflict >= 0:
                self.stats["conflicts"] += 1
                since_restart += 1
                if not self.limits:
                    self.emit([])
                    self.result = False
                    return False
                learned, back_level = self.analyze(conflict)
                self.emit(learned)
                self.stats["learned"] += 1
                if back_level < len(self.limits) - 1:
                    self.stats["backjumps"] += 1
                self.backtrack(back_level)
                cid = self.add_clause(learned)
                enqueued = self.enqueue(learned[0], cid)
                assert enqueued, "learned clause must be asserting after backtracking"
            else:
                # Propagate the asserting clause before considering a restart.
                if since_restart >= budget and self.limits:
                    self.backtrack(0)
                    self.stats["restarts"] += 1
                    since_restart = 0
                    restart_index += 1
                    budget = self.restart_base * luby(restart_index)
                    continue
                lit = self.decide()
                if not lit:
                    self.result = True
                    return True
                self.stats["decisions"] += 1
                self.limits.append(len(self.trail))
                self.enqueue(lit, -1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("formula", type=Path)
    parser.add_argument("--proof", type=Path, help="write a text DRAT (RUP) proof")
    args = parser.parse_args(argv)
    proof = None
    try:
        if args.proof is not None and (
            args.formula.resolve() == args.proof.resolve()
            or (args.proof.exists() and args.formula.samefile(args.proof))
        ):
            raise ValueError("formula and proof paths must differ")
        nvars, clauses = read_dimacs(args.formula)
        if args.proof is not None:
            proof = args.proof.open("w", encoding="ascii")
        solver = Solver(nvars, clauses, proof)
        satisfiable = solver.solve()
        if proof is not None:
            proof.close()
            proof = None
        if satisfiable:
            print("s SATISFIABLE")
            literals = [v * solver.values[v] for v in range(1, nvars + 1)]
            for start in range(0, max(1, nvars), 20):
                print("v", *literals[start:start + 20], 0)
            return 10
        print("s UNSATISFIABLE")
        return 20
    except (OSError, ValueError) as error:
        print(f"c error: {error}", file=sys.stderr)
        return 2
    finally:
        if proof is not None:
            proof.close()


if __name__ == "__main__":
    sys.exit(main())

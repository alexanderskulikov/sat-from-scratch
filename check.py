#!/usr/bin/env python3
"""Independent SAT-model and RUP-proof checker; does not import solver.py.

Usage: python3 check.py FORMULA.cnf --model SOLVER_OUTPUT
   or: python3 check.py FORMULA.cnf --proof PROOF.drat

Proof checking uses occurrence counts, not watched literals or CDCL. Only
RUP additions are accepted, not the more general RAT rule of full DRAT.
"""

import argparse
import sys


def read_formula(path):
    """Separate DIMACS implementation, retaining duplicate/tautological clauses."""
    variables = None
    expected = None
    formula = []
    clause = []
    with open(path, encoding="ascii") as stream:
        for number, text in enumerate(stream, 1):
            text = text.strip()
            if not text or text.split()[0] == "c":
                continue
            fields = text.split()
            if fields[0] == "p":
                if variables is not None or fields[:2] != ["p", "cnf"] or len(fields) != 4:
                    raise ValueError(f"line {number}: bad DIMACS header")
                variables, expected = int(fields[2]), int(fields[3])
                if min(variables, expected) < 0:
                    raise ValueError("negative DIMACS size")
                continue
            if variables is None:
                raise ValueError("clause before header")
            numbers = [int(field) for field in fields]
            for literal in numbers:
                if literal == 0:
                    formula.append(tuple(clause))
                    clause.clear()
                elif 1 <= abs(literal) <= variables:
                    clause.append(literal)
                else:
                    raise ValueError("literal outside DIMACS variable range")
    if variables is None or clause or len(formula) != expected:
        raise ValueError("missing header, missing terminator, or incorrect clause count")
    return variables, formula


def check_assignment(nvars, clauses, literals):
    assignment = {}
    for literal in literals:
        if not 1 <= abs(literal) <= nvars:
            raise ValueError("model literal out of range")
        var, value = abs(literal), literal > 0
        if var in assignment and assignment[var] != value:
            raise ValueError("contradictory model literals")
        assignment[var] = value
    if len(assignment) != nvars:
        raise ValueError("model must assign every declared variable")
    for index, clause in enumerate(clauses, 1):
        if not any(assignment[abs(lit)] == (lit > 0) for lit in clause):
            raise ValueError(f"model falsifies clause {index}")
    return True


def check_model(nvars, clauses, stream):
    status = None
    literals = []
    has_values = False
    terminated = False
    for line in stream:
        fields = line.split()
        if not fields or fields[0] == "c":
            continue
        if fields[0] == "s" and fields == ["s", "SATISFIABLE"] and status is None:
            status = "SAT"
        elif fields[0] == "v" and status == "SAT":
            values = [int(word) for word in fields[1:]]
            if not values or 0 in values[:-1]:
                raise ValueError("invalid model terminator")
            has_values = True
            terminated = values[-1] == 0
            literals.extend(values[:-1] if terminated else values)
        else:
            raise ValueError("expected one SAT status followed by v lines")
    if status != "SAT" or not has_values or not terminated:
        raise ValueError("missing SAT status or terminated model")
    return check_assignment(nvars, clauses, literals)


class RUPChecker:
    """Check F => C by deriving a unit conflict in F AND (NOT C).

    Each clause counts its not-yet-false literals. All assignments and count
    changes are rolled back after each check. No solver code is reused.
    """

    def __init__(self, nvars, clauses):
        self.nvars = nvars
        self.clauses = []
        self.remaining = []
        self.active = []
        self.occurrences = {}
        self.units = []
        self.empty = set()
        self.ids = {}
        for clause in clauses:
            self.add(clause)

    def canonical(self, clause):
        if any(not 1 <= abs(lit) <= self.nvars for lit in clause):
            raise ValueError("proof literal outside formula variable range")
        return tuple(sorted(set(clause)))

    def add(self, clause):
        clause = self.canonical(clause)
        cid = len(self.clauses)
        self.clauses.append(clause)
        self.remaining.append(len(clause))
        self.active.append(True)
        self.ids.setdefault(clause, []).append(cid)
        for literal in clause:
            self.occurrences.setdefault(literal, []).append(cid)
        if not clause:
            self.empty.add(cid)
        elif len(clause) == 1:
            self.units.append(cid)

    def delete(self, clause):
        key = self.canonical(clause)
        matches = self.ids.get(key)
        if not matches:
            raise ValueError("deletion of a nonexistent clause")
        cid = matches.pop()
        self.active[cid] = False
        self.empty.discard(cid)

    def is_rup(self, clause):
        clause = self.canonical(clause)
        if self.empty:
            return True
        values = {}
        queue = []
        changed = []

        def assign(literal):
            var, value = abs(literal), literal > 0
            if var in values:
                return values[var] == value
            values[var] = value
            queue.append(literal)
            return True

        try:
            for literal in clause:
                if not assign(-literal):
                    return True
            for cid in self.units:
                if self.active[cid] and not assign(self.clauses[cid][0]):
                    return True
            head = 0
            while head < len(queue):
                literal = queue[head]
                head += 1
                for cid in self.occurrences.get(-literal, ()):
                    if not self.active[cid]:
                        continue
                    self.remaining[cid] -= 1
                    changed.append(cid)
                    if self.remaining[cid] == 0:
                        return True
                    if self.remaining[cid] == 1:
                        for candidate in self.clauses[cid]:
                            value = values.get(abs(candidate))
                            if value is None:
                                if not assign(candidate):
                                    return True
                                break
                            if value == (candidate > 0):
                                break
                        else:
                            return True
            return False
        finally:
            for cid in changed:
                self.remaining[cid] += 1


def check_proof(nvars, clauses, stream):
    checker = RUPChecker(nvars, clauses)
    additions = 0
    ended = False
    for line_number, line in enumerate(stream, 1):
        words = line.split()
        if not words or words[0] == "c":
            continue
        if ended:
            raise ValueError("proof has instructions after the empty clause")
        deletion = words[0] == "d"
        if deletion:
            words = words[1:]
        literals = [int(word) for word in words]
        if not literals or literals[-1] != 0 or 0 in literals[:-1]:
            raise ValueError(f"line {line_number}: expected one zero-terminated clause")
        clause = literals[:-1]
        if deletion:
            checker.delete(clause)
        else:
            if not checker.is_rup(clause):
                raise ValueError(f"line {line_number}: clause is not RUP")
            checker.add(clause)
            additions += 1
            ended = not clause
    if not ended:
        raise ValueError("proof does not end with a verified empty clause")
    return additions


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("formula")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--model")
    mode.add_argument("--proof")
    args = parser.parse_args(argv)
    try:
        nvars, clauses = read_formula(args.formula)
        with open(args.model or args.proof, encoding="ascii") as stream:
            if args.model:
                check_model(nvars, clauses, stream)
                print("VERIFIED SAT model")
            else:
                count = check_proof(nvars, clauses, stream)
                print(f"VERIFIED UNSAT proof ({count} RUP additions)")
        return 0
    except (OSError, ValueError) as error:
        print(f"REJECTED: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

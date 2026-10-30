import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import check
from solver import Solver, luby, read_dimacs


ROOT = Path(__file__).resolve().parents[1]


class SolverTests(unittest.TestCase):
    def verify(self, nvars, clauses, expected, restart_base=64):
        proof = io.StringIO()
        solver = Solver(nvars, clauses, proof, restart_base=restart_base)
        result = solver.solve()
        self.assertEqual(result, expected)
        if result:
            check.check_assignment(nvars, clauses,
                                   [v * solver.values[v] for v in range(1, nvars + 1)])
        else:
            check.check_proof(nvars, clauses, io.StringIO(proof.getvalue()))
        # Repeated calls must return the cached answer and not append a second proof.
        saved = proof.getvalue()
        self.assertEqual(solver.solve(), expected)
        self.assertEqual(proof.getvalue(), saved)
        return solver

    def test_boundary_formulas(self):
        cases = [(0, [], True), (0, [[]], False), (5, [], True),
                 (1, [[1], [-1]], False), (2, [[1, 1], [-1, 2]], True),
                 (3, [[1, -1], [2, 2, -2]], True),
                 (2, [[1], [-1, 2], [-2]], False),
                 (2, [[1, 2], [1, -2], [-1, 2], [-1, -2]], False),
                 (5, [[5], [5], [-1, 2, 3, 4, 5]], True)]
        for n, clauses, expected in cases:
            with self.subTest(n=n, clauses=clauses):
                self.verify(n, clauses, expected)

    def test_long_unit_chain_and_long_clause(self):
        n = 2500
        chain = [[1]] + [[-v, v + 1] for v in range(1, n)]
        self.verify(n, chain, True)
        self.verify(n, chain + [[-n]], False)
        self.verify(n, [list(range(1, n + 1))] + [[-v] for v in range(1, n)], True)

    def test_luby(self):
        self.assertEqual([luby(i) for i in range(1, 16)],
                         [1, 1, 2, 1, 1, 2, 4, 1, 1, 2, 1, 1, 2, 4, 8])

    def test_pigeonhole_restarts_and_learning(self):
        pigeons, holes = 6, 5
        var = lambda p, h: p * holes + h + 1
        clauses = [[var(p, h) for h in range(holes)] for p in range(pigeons)]
        clauses += [[-var(p, h), -var(q, h)] for h in range(holes)
                    for p in range(pigeons) for q in range(p + 1, pigeons)]
        solver = self.verify(pigeons * holes, clauses, False, restart_base=2)
        self.assertGreater(solver.stats["restarts"], 0)
        self.assertGreater(solver.stats["learned"], 0)
        self.assertGreater(solver.stats["backjumps"], 0)

    def test_dimacs_valid_and_invalid(self):
        valid = "c heading\n\np cnf 4 4\n1 1\nc middle\n-2 0 3 0\n0\n4 -4 0\n"
        malformed = ["", "1 0\n", "p cnf -1 0\n", "p cnf 1 -1\n",
                     "p cnf 1 1\n1\n", "p cnf 1 0\n0\n", "p cnf 1 1\n2 0\n",
                     "p cnf 1 1\nx 0\n", "p cnf 1 0\np cnf 1 0\n",
                     "p cnf 1 1 extra\n1 0\n", "p dnf 1 0\n"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.cnf"
            path.write_text(valid)
            n, clauses = read_dimacs(path)
            self.assertEqual((n, clauses), (4, [[1, 1, -2], [3], [], [4, -4]]))
            self.assertEqual(check.read_formula(path), (4, [(1, 1, -2), (3,), (), (4, -4)]))
            for text in malformed:
                path.write_text(text)
                for reader in (read_dimacs, check.read_formula):
                    with self.subTest(text=text, reader=reader.__name__):
                        with self.assertRaises(ValueError):
                            reader(path)

    def test_cli_contract_and_filename_independence(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            for text, expected in [("p cnf 25 2\n1 -2 0\n25 0\n", 10),
                                   ("p cnf 2 4\n1 2 0\n1 -2 0\n-1 2 0\n-1 -2 0\n", 20),
                                   ("p cnf 0 0\n", 10), ("p cnf 0 1\n0\n", 20)]:
                outputs = []
                for name in ("n150_00.cnf", "arbitrary name.cnf"):
                    formula, proof = directory / name, directory / "proof.drat"
                    formula.write_text(text)
                    result = subprocess.run([sys.executable, "-O", str(ROOT / "solver.py"),
                                             str(formula), "--proof", str(proof)],
                                            capture_output=True, text=True, timeout=10,
                                            cwd=directory)
                    self.assertEqual(result.returncode, expected, result.stderr)
                    self.assertEqual(result.stderr, "")
                    outputs.append((result.stdout, proof.read_text()))
                    n, clauses = check.read_formula(formula)
                    if expected == 10:
                        check.check_model(n, clauses, io.StringIO(result.stdout))
                        mode, witness = "--model", directory / "output.txt"
                        witness.write_text(result.stdout)
                    else:
                        self.assertEqual(result.stdout, "s UNSATISFIABLE\n")
                        with proof.open() as stream:
                            check.check_proof(n, clauses, stream)
                        mode, witness = "--proof", proof
                    checked = subprocess.run([sys.executable, str(ROOT / "check.py"),
                                              str(formula), mode, str(witness)],
                                             capture_output=True, text=True, timeout=10)
                    self.assertEqual(checked.returncode, 0, checked.stderr)
                self.assertEqual(outputs[0], outputs[1])
            formula.write_text("p cnf 1 1\n2 0\n")
            failed = subprocess.run([sys.executable, str(ROOT / "solver.py"), str(formula)],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(failed.returncode, 2)
            self.assertNotIn("s SATISFIABLE", failed.stdout)
            original = "p cnf 1 1\n1 0\n"
            formula.write_text(original)
            for proof_path in (formula, directory / "hardlink.drat"):
                if proof_path != formula:
                    proof_path.hardlink_to(formula)
                failed = subprocess.run([sys.executable, str(ROOT / "solver.py"),
                                         str(formula), "--proof", str(proof_path)],
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(failed.returncode, 2)
                self.assertEqual(formula.read_text(), original)

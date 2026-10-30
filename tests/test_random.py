import io
import itertools
import random
import unittest

from check import check_assignment, check_proof
from solver import Solver
from tests.helpers import brute_force


def generated_formula(rng, n, index):
    mode = index % 5
    count = rng.randint(0, 6 * n)
    planted = [rng.choice((-1, 1)) for _ in range(n)]
    result = []
    for _ in range(count):
        width = min(n, 3) if mode in (0, 1, 2) else rng.randint(1, min(n, 6))
        clause = [v * rng.choice((-1, 1)) for v in rng.sample(range(1, n + 1), width)]
        if mode == 2 and not any(lit * planted[abs(lit) - 1] > 0 for lit in clause):
            clause[0] *= -1
        if mode == 4:
            clause += [rng.choice(clause)] * rng.randint(0, 2)
            if rng.random() < 0.15:
                clause.append(-clause[0])
        result.append(clause)
    if index % 37 == 0:
        result.append([])
    return result


class RandomTests(unittest.TestCase):
    def verify(self, n, clauses, expected, restart_base=64):
        proof = io.StringIO()
        solver = Solver(n, clauses, proof, restart_base=restart_base)
        self.assertEqual(solver.solve(), expected)
        if expected:
            check_assignment(n, clauses, [v * solver.values[v] for v in range(1, n + 1)])
        else:
            check_proof(n, clauses, io.StringIO(proof.getvalue()))

    def test_all_two_variable_formulas(self):
        # Each variable is absent, positive, or negative: 9 canonical clauses.
        clauses = [[v * sign for v, sign in enumerate(signs, 1) if sign]
                   for signs in itertools.product((0, 1, -1), repeat=2)]
        for mask in range(1 << len(clauses)):
            formula = [clause for i, clause in enumerate(clauses) if mask & (1 << i)]
            with self.subTest(mask=mask):
                self.verify(2, formula, brute_force(2, formula), restart_base=1)

    def test_3000_seeded_random_formulas(self):
        rng = random.Random(20261030)
        for n in range(1, 13):
            for index in range(250):
                formula = generated_formula(rng, n, index)
                with self.subTest(n=n, index=index):
                    self.verify(n, formula, brute_force(n, formula),
                                restart_base=1 if index % 3 == 0 else 64)

    def test_100_variable_and_polarity_permutations(self):
        rng = random.Random(81173)
        for case in range(100):
            n = rng.randint(3, 12)
            formula = generated_formula(rng, n, 5 * case)
            expected = brute_force(n, formula)
            permutation = rng.sample(range(1, n + 1), n)
            renamed = [v * rng.choice((-1, 1)) for v in permutation]
            transformed = [[renamed[abs(lit) - 1] * (1 if lit > 0 else -1)
                            for lit in clause] for clause in formula]
            rng.shuffle(transformed)
            for clause in transformed:
                rng.shuffle(clause)
            with self.subTest(case=case):
                self.verify(n, transformed, expected, restart_base=2)

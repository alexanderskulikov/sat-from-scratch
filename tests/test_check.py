import io
import random
import unittest

from check import RUPChecker, check_assignment, check_model, check_proof
from tests.helpers import brute_force, slow_rup


class CheckerTests(unittest.TestCase):
    def test_reject_bad_models(self):
        for model in ["", "s UNSATISFIABLE\n", "s SATISFIABLE\nv 1 0\n",
                      "s SATISFIABLE\nv 1 -1 2 0\n", "s SATISFIABLE\nv 1 3 0\n",
                      "s SATISFIABLE\nv -1 -2 0\n", "s SATISFIABLE\nv 1 2\n",
                      "s SATISFIABLE\nv 1 0 2\n", "v 1 2 0\n",
                      "s SATISFIABLE\ns SATISFIABLE\nv 1 2 0\n"]:
            with self.subTest(model=model), self.assertRaises(ValueError):
                check_model(2, [[1, 2]], io.StringIO(model))
        check_model(2, [[1, 2]], io.StringIO("s SATISFIABLE\nv 1\nv -2 0\n"))
        check_model(2, [[1, 2]], io.StringIO("s SATISFIABLE\nv 1 0\nv -2 0\n"))
        with self.assertRaises(ValueError):
            check_assignment(1, [[]], [1])

    def test_reject_bad_proofs(self):
        # These clauses imply UNSAT, but the empty clause is not yet RUP.
        formula = [[1, 2], [1, -2], [-1, 2], [-1, -2]]
        check_proof(2, formula, io.StringIO("1 0\n0\n"))
        for proof in ["", "0\n", "1 0\n", "1\n0\n", "3 0\n0\n",
                      "1 0 2 0\n0\n", "1 0\n0\n2 0\n", "d 0\n1 0\n0\n"]:
            with self.subTest(proof=proof), self.assertRaises(ValueError):
                check_proof(2, formula, io.StringIO(proof))
        # A forged lemma must not be accepted merely because a later empty clause follows.
        for proof in ["0\n", "-1 0\n0\n", "1 -1 0\n0\n"]:
            with self.subTest(proof=proof), self.assertRaises(ValueError):
                check_proof(2, [[1, 2]], io.StringIO(proof))

    def test_deletions_duplicates_and_tautologies(self):
        check_proof(1, [[1], [1], [-1]], io.StringIO("d 1 0\n0\n"))
        with self.assertRaises(ValueError):
            check_proof(1, [[1], [-1]], io.StringIO("d 1 0\n0\n"))
        check_proof(1, [[1, 1], [-1, -1]], io.StringIO("0\n"))
        checker = RUPChecker(2, [[1, -1], [2]])
        self.assertFalse(checker.is_rup([]))
        self.assertTrue(checker.is_rup([1, -1]))
        self.assertTrue(checker.is_rup([2, 2]))
        self.assertFalse(checker.is_rup([-2]))

    def test_occurrence_checker_against_reference_and_truth_table(self):
        rng = random.Random(42801)
        for case in range(1000):
            n = rng.randint(1, 6)
            formula = [[rng.choice((-1, 1)) * rng.randint(1, n)
                        for _ in range(rng.randint(1, 4))]
                       for _ in range(rng.randint(0, 20))]
            checker = RUPChecker(n, formula)
            for step in range(6):
                lemma = [rng.choice((-1, 1)) * rng.randint(1, n)
                         for _ in range(rng.randint(0, 4))]
                actual = checker.is_rup(lemma)
                with self.subTest(case=case, step=step):
                    self.assertEqual(actual, slow_rup(formula, lemma))
                    # Repeating the query checks rollback of every modified count.
                    self.assertEqual(checker.is_rup(lemma), actual)
                    if actual:
                        self.assertFalse(brute_force(n, formula + [[-lit] for lit in lemma]))
                if actual and lemma:
                    checker.add(lemma)
                    formula.append(lemma)
                if formula and step % 2:
                    clause = formula.pop(rng.randrange(len(formula)))
                    checker.delete(clause)

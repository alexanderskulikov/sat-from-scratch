import itertools


def brute_force(nvars, clauses):
    """Exhaustively evaluate the input, without any SAT propagation machinery."""
    for assignment in itertools.product((False, True), repeat=nvars):
        if all(any(assignment[abs(lit) - 1] == (lit > 0) for lit in clause)
               for clause in clauses):
            return True
    return False


def slow_rup(clauses, lemma):
    """Small reference checker: repeatedly scan every clause for a unit."""
    assigned = {}
    for lit in lemma:
        var, value = abs(lit), lit < 0
        if var in assigned and assigned[var] != value:
            return True
        assigned[var] = value
    while True:
        progress = False
        for raw in clauses:
            clause = set(raw)
            if any(assigned.get(abs(lit)) == (lit > 0)
                   for lit in clause if abs(lit) in assigned):
                continue
            unset = [lit for lit in clause if abs(lit) not in assigned]
            if not unset:
                return True
            if len(unset) == 1:
                lit = unset[0]
                assigned[abs(lit)] = lit > 0
                progress = True
        if not progress:
            return False

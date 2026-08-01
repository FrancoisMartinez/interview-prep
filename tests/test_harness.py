"""Tests for the shared harness.

Every problem depends on this code, so a bug here looks like a wrong answer in
150 places at once. The comparator modes in particular are easy to ship without
ever running -- `custom`, `any_of` and `float` have no natural coverage from the
problem set, so they get exercised here.
"""

import json
import textwrap

import pytest

from lib.compare import VALID_MODES, compare
from lib.harness import evaluate
from lib.lcnodes import build_list, build_tree, serialize_linked_list, serialize_tree


# --------------------------------------------------------------------------
# Comparators
# --------------------------------------------------------------------------

def test_exact():
    assert compare("exact", [1, 2], [1, 2])[0]
    assert not compare("exact", [1, 2], [2, 1])[0]


def test_unordered_ignores_outer_order_only():
    assert compare("unordered", [[1, 2], [3]], [[3], [1, 2]])[0]
    # inner order still matters -- n-queens boards must keep their row order
    assert not compare("unordered", [[1, 2]], [[2, 1]])[0]


def test_set_of_sets_ignores_both():
    assert compare("set_of_sets", [[-1, 0, 1], [-1, -1, 2]], [[2, -1, -1], [1, 0, -1]])[0]
    assert not compare("set_of_sets", [[1, 2]], [[1, 3]])[0]


def test_float_respects_tolerance():
    assert compare("float", 2.0, 2.0000001)[0]
    assert not compare("float", 2.0, 2.1)[0]
    assert compare("float", [1.0, 2.5], [1.0000001, 2.5])[0]
    assert not compare("float", [1.0], [1.0, 2.0])[0]


def test_float_routes_bools_around_isclose():
    # isclose(True, False) would be a tolerance question; equality is the
    # right one. (1 == True stays true, as it is everywhere in Python.)
    assert compare("float", True, True)[0]
    assert not compare("float", True, False)[0]


def test_any_of_accepts_any_listed_answer():
    assert compare("any_of", [[0, 1], [1, 0]], [1, 0])[0]
    assert not compare("any_of", [[0, 1], [1, 0]], [2, 3])[0]
    # `expected` must be the list of answers, not a single answer
    assert not compare("any_of", 5, 5)[0]


def test_custom_without_validator_fails_loudly():
    ok, detail = compare("custom", None, [1], validator=None)
    assert not ok and "validate.py" in detail


def test_custom_uses_the_validator():
    def validator(args, actual):
        return sum(actual) == args[0]

    assert compare("custom", None, [2, 3], validator=validator, args=[5])[0]
    assert not compare("custom", None, [2, 3], validator=validator, args=[9])[0]


def test_custom_can_return_a_reason():
    def validator(args, actual):
        return False, "not a valid board"

    ok, detail = compare("custom", None, [], validator=validator, args=[])
    assert not ok and detail == "not a valid board"


def test_unknown_mode_is_rejected():
    ok, detail = compare("nonsense", 1, 1)
    assert not ok and "unknown compare mode" in detail


def test_documented_modes_all_exist():
    for mode in VALID_MODES:
        # none of these should report an unknown mode
        _, detail = compare(mode, [], [], validator=lambda a, b: True, args=[])
        assert "unknown compare mode" not in detail


# --------------------------------------------------------------------------
# Node serialization -- LeetCode's level-order-with-nulls format
# --------------------------------------------------------------------------

@pytest.mark.parametrize("values", [
    [],
    [1],
    [1, 2],
    [1, None, 2],
    [4, 2, 7, 1, 3, 6, 9],
    [1, 2, 3, 4, None, None, 5],
    [1, 2, None, 3],
])
def test_tree_round_trip(values):
    assert serialize_tree(build_tree(values)) == values


@pytest.mark.parametrize("values", [[], [1], [1, 2, 3, 4, 5]])
def test_list_round_trip(values):
    assert serialize_linked_list(build_list(values)) == values


def test_serialize_linked_list_survives_a_cycle():
    head = build_list([1, 2, 3])
    head.next.next.next = head          # a solution that mis-wires its pointers
    assert "...<cycle>" in serialize_linked_list(head)


# --------------------------------------------------------------------------
# evaluate() -- the wiring, not just the pieces
# --------------------------------------------------------------------------

def _make_problem(tmp_path, *, solution, spec, validate=None):
    (tmp_path / "solution.py").write_text(textwrap.dedent(solution), encoding="utf-8")
    (tmp_path / "cases.json").write_text(json.dumps(spec), encoding="utf-8")
    if validate is not None:
        (tmp_path / "validate.py").write_text(textwrap.dedent(validate), encoding="utf-8")
    return tmp_path


BASE_ENTRY = {
    "kind": "function", "class": "Solution", "method": "solve",
    "param_types": ["integer[]"], "return_type": "integer[]",
    "output_from_param": None, "truncate_to_ret": False,
}


def test_evaluate_reports_not_attempted_for_a_stub(tmp_path):
    _make_problem(
        tmp_path,
        solution="""
            class Solution:
                def solve(self, nums):
                    raise NotImplementedError
        """,
        spec={"verified": True, "entry": BASE_ENTRY, "compare": "exact",
              "cases": [{"args": [[1]], "expected": [1]}]},
    )
    report = evaluate(tmp_path / "solution.py", tmp_path / "cases.json", tmp_path)
    assert report.not_attempted and not report.failures


def test_evaluate_finds_and_calls_validate_py(tmp_path):
    """The `custom` path has no coverage from the problem set -- prove the
    validate.py is discovered, imported and called with (args, actual)."""
    _make_problem(
        tmp_path,
        solution="""
            class Solution:
                def solve(self, nums):
                    return [n * 2 for n in nums]
        """,
        spec={"verified": True, "entry": BASE_ENTRY, "compare": "custom",
              "cases": [{"args": [[1, 2, 3]], "expected": None}]},
        validate="""
            def validate(args, actual):
                return actual == [n * 2 for n in args[0]]
        """,
    )
    report = evaluate(tmp_path / "solution.py", tmp_path / "cases.json", tmp_path)
    assert report.ok and report.passed == 1


def test_evaluate_custom_rejects_a_wrong_answer(tmp_path):
    _make_problem(
        tmp_path,
        solution="""
            class Solution:
                def solve(self, nums):
                    return [0]
        """,
        spec={"verified": True, "entry": BASE_ENTRY, "compare": "custom",
              "cases": [{"args": [[1, 2, 3]], "expected": None}]},
        validate="""
            def validate(args, actual):
                return False, "always wrong"
        """,
    )
    report = evaluate(tmp_path / "solution.py", tmp_path / "cases.json", tmp_path)
    assert not report.ok and "always wrong" in report.failures[0]


def test_evaluate_reads_the_mutated_argument_for_in_place_problems(tmp_path):
    entry = dict(BASE_ENTRY, return_type="void", output_from_param=0)
    _make_problem(
        tmp_path,
        solution="""
            class Solution:
                def solve(self, nums):
                    nums.reverse()
        """,
        spec={"verified": True, "entry": entry, "compare": "exact",
              "cases": [{"args": [[1, 2, 3]], "expected": [3, 2, 1]}]},
    )
    report = evaluate(tmp_path / "solution.py", tmp_path / "cases.json", tmp_path)
    assert report.ok


def test_evaluate_truncates_to_the_returned_length(tmp_path):
    entry = dict(BASE_ENTRY, return_type="integer", output_from_param=0,
                 truncate_to_ret=True)
    _make_problem(
        tmp_path,
        solution="""
            class Solution:
                def solve(self, nums):
                    keep = sorted(set(nums))
                    nums[:len(keep)] = keep
                    return len(keep)
        """,
        spec={"verified": True, "entry": entry, "compare": "exact",
              "cases": [{"args": [[1, 1, 2]], "expected": [1, 2]}]},
    )
    report = evaluate(tmp_path / "solution.py", tmp_path / "cases.json", tmp_path)
    assert report.ok


def test_evaluate_reports_the_input_on_failure(tmp_path):
    _make_problem(
        tmp_path,
        solution="""
            class Solution:
                def solve(self, nums):
                    return [999]
        """,
        spec={"verified": True, "entry": BASE_ENTRY, "compare": "exact",
              "cases": [{"args": [[1, 2]], "expected": [1, 2]}]},
    )
    report = evaluate(tmp_path / "solution.py", tmp_path / "cases.json", tmp_path)
    failure = report.failures[0]
    assert "[1, 2]" in failure and "999" in failure


def test_evaluate_catches_an_exception_without_aborting_the_run(tmp_path):
    _make_problem(
        tmp_path,
        solution="""
            class Solution:
                def solve(self, nums):
                    return [1 // nums[0]]
        """,
        spec={"verified": True, "entry": BASE_ENTRY, "compare": "exact",
              "cases": [{"args": [[0]], "expected": [0]},
                        {"args": [[1]], "expected": [1]}]},
    )
    report = evaluate(tmp_path / "solution.py", tmp_path / "cases.json", tmp_path)
    assert report.passed == 1
    assert "ZeroDivisionError" in report.failures[0]


def test_evaluate_drives_a_design_problem(tmp_path):
    entry = {"kind": "design", "class": "Counter", "method": None,
             "param_types": [], "return_type": None,
             "output_from_param": None, "truncate_to_ret": False}
    _make_problem(
        tmp_path,
        solution="""
            class Counter:
                def __init__(self, start):
                    self.n = start
                def bump(self):
                    self.n += 1
                def value(self):
                    return self.n
        """,
        spec={"verified": True, "entry": entry, "compare": "exact",
              "cases": [{"ops": ["Counter", "bump", "value"],
                         "args": [[5], [], []],
                         "expected": [None, None, 6]}]},
    )
    report = evaluate(tmp_path / "solution.py", tmp_path / "cases.json", tmp_path)
    assert report.ok


def test_two_problems_do_not_share_a_solution_module(tmp_path):
    """150 sibling files all named solution.py must not collide in sys.modules."""
    reports = []
    for name, value in (("prob-a", 1), ("prob-b", 2)):
        directory = tmp_path / name
        directory.mkdir()
        _make_problem(
            directory,
            solution=f"""
                class Solution:
                    def solve(self, nums):
                        return [{value}]
            """,
            spec={"verified": True, "entry": BASE_ENTRY, "compare": "exact",
                  "cases": [{"args": [[0]], "expected": [value]}]},
        )
        reports.append(
            evaluate(directory / "solution.py", directory / "cases.json", directory)
        )
    assert all(r.ok for r in reports)

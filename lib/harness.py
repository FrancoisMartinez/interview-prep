"""The test harness. Every problem's test_solution.py is a two-line shim
that calls run_cases(__file__); all the logic lives here so a comparator fix
at problem 40 doesn't mean regenerating 150 directories.

Solution modules are loaded via spec_from_file_location under a name derived
from the problem directory (prob_0001_two_sum), never the bare name
`solution` -- 150 sibling files all called solution.py would otherwise
collide in sys.modules and silently test the wrong file.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from lib.compare import DEFAULT_TOLERANCE, compare
from lib.lcnodes import (
    ListNode,
    Node,
    TreeNode,
    build_list,
    build_tree,
    serialize_linked_list,
    serialize_tree,
)

_MAX_SHOWN = 400


# --------------------------------------------------------------------------
# Module loading
# --------------------------------------------------------------------------

def module_name_for(problem_dir: Path) -> str:
    return "prob_" + problem_dir.name.replace("-", "_").replace(".", "_")


def load_module(py_path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, py_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {py_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# (De)serialization between JSON test data and LeetCode's node types
# --------------------------------------------------------------------------

def deserialize_arg(value, type_str):
    t = (type_str or "").strip()
    if t == "TreeNode":
        return build_tree(value)
    if t == "ListNode":
        return build_list(value)
    if t == "TreeNode[]":
        return [build_tree(v) for v in (value or [])]
    if t == "ListNode[]":
        return [build_list(v) for v in (value or [])]
    return value


def serialize(value):
    if isinstance(value, TreeNode):
        return serialize_tree(value)
    if isinstance(value, ListNode):
        return serialize_linked_list(value)
    if isinstance(value, Node):
        return value.val
    if isinstance(value, (list, tuple)):
        return [serialize(v) for v in value]
    return value


def serialize_result(value, declared_type):
    # An empty tree/list comes back as None but is written as [] in test data.
    if (declared_type or "").strip() in ("TreeNode", "ListNode") and value is None:
        return []
    return serialize(value)


def _show(value) -> str:
    try:
        text = json.dumps(value, default=repr)
    except (TypeError, ValueError):
        text = repr(value)
    return text if len(text) <= _MAX_SHOWN else text[:_MAX_SHOWN] + " ...(truncated)"


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

@dataclass
class Report:
    not_attempted: bool = False
    passed: int = 0
    failures: list[str] = field(default_factory=list)
    unverified: bool = False

    @property
    def ok(self) -> bool:
        return not self.failures and not self.not_attempted


# --------------------------------------------------------------------------
# Case execution
# --------------------------------------------------------------------------

def _run_function_case(module, entry, case):
    """Return the value to compare against `expected`."""
    cls = getattr(module, entry.get("class", "Solution"))
    method = getattr(cls(), entry["method"])

    param_types = entry.get("param_types") or []
    raw_args = case["args"]
    args = [
        deserialize_arg(copy.deepcopy(raw), param_types[i] if i < len(param_types) else None)
        for i, raw in enumerate(raw_args)
    ]

    returned = method(*args)

    index = entry.get("output_from_param")
    if index is None:
        return serialize_result(returned, entry.get("return_type"))

    # In-place problems: the answer is the mutated argument, not the return.
    mutated = serialize_result(
        args[index], param_types[index] if index < len(param_types) else None
    )
    if entry.get("truncate_to_ret"):
        if not isinstance(returned, int):
            raise TypeError(
                f"expected an int length to truncate by, got {type(returned).__name__}"
            )
        mutated = mutated[:returned]
    return mutated


def _run_design_case(module, entry, case):
    classname = entry.get("class")
    cls = getattr(module, classname)

    ops = case["ops"]
    call_args = copy.deepcopy(case["args"])

    instance = cls(*call_args[0])
    results = [None]
    for op, a in zip(ops[1:], call_args[1:]):
        results.append(serialize(getattr(instance, op)(*a)))
    return results


def _describe_input(entry, case) -> str:
    if entry.get("kind") == "design":
        return f"ops={_show(case['ops'])}\n    args={_show(case['args'])}"
    return _show(case["args"])


# --------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------

def evaluate(solution_path: Path, cases_path: Path, problem_dir: Path,
             module_name: str | None = None) -> Report:
    """Run a solution file against a cases.json. Used by both pytest and the
    importer's reference-solution check."""
    solution_path = Path(solution_path)
    cases_path = Path(cases_path)
    problem_dir = Path(problem_dir)

    spec = json.loads(cases_path.read_text(encoding="utf-8"))
    entry = spec["entry"]
    mode = spec.get("compare", "exact")
    tolerance = spec.get("tolerance", DEFAULT_TOLERANCE)
    cases = spec.get("cases", [])

    report = Report(unverified=not spec.get("verified", False))

    validator = None
    if mode == "custom":
        validate_py = problem_dir / "validate.py"
        if validate_py.exists():
            validator = getattr(
                load_module(validate_py, module_name_for(problem_dir) + "_validate"),
                "validate",
            )

    module = load_module(
        solution_path, module_name or module_name_for(problem_dir)
    )

    runner = _run_design_case if entry.get("kind") == "design" else _run_function_case

    for i, case in enumerate(cases, start=1):
        try:
            actual = runner(module, entry, case)
        except NotImplementedError:
            if i == 1:
                return Report(not_attempted=True, unverified=report.unverified)
            report.failures.append(f"case {i}: raised NotImplementedError")
            continue
        except Exception:
            report.failures.append(
                f"case {i}: raised while running\n"
                f"    input:    {_describe_input(entry, case)}\n"
                f"    expected: {_show(case.get('expected'))}\n"
                f"{traceback.format_exc()}"
            )
            continue

        expected = case.get("expected")
        ok, detail = compare(
            mode, expected, actual,
            tolerance=tolerance, validator=validator, args=case.get("args"),
        )
        if ok:
            report.passed += 1
        else:
            note = f"  ({detail})" if detail else ""
            report.failures.append(
                f"case {i}{note}\n"
                f"    input:    {_describe_input(entry, case)}\n"
                f"    expected: {_show(expected)}\n"
                f"    actual:   {_show(actual)}"
            )

    return report


def run_cases(test_file):
    """Called by every problem's test_solution.py."""
    import pytest

    problem_dir = Path(test_file).resolve().parent
    report = evaluate(
        problem_dir / "solution.py", problem_dir / "cases.json", problem_dir
    )

    if report.not_attempted:
        pytest.skip("not attempted yet")

    if report.failures:
        header = f"{len(report.failures)} of {len(report.failures) + report.passed} cases failed"
        if report.unverified:
            header += (
                "\nNOTE: cases.json is marked verified=false -- the expected "
                "outputs were not confirmed at import. Check them before "
                "assuming your solution is wrong."
            )
        pytest.fail(header + "\n\n" + "\n\n".join(report.failures), pytrace=False)

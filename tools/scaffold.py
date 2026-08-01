"""Turn a fetched question into a problem directory."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from tools.fetch import python_snippet
from tools.render import extract_example_outputs, to_markdown

ROOT = Path(__file__).resolve().parent.parent
PROBLEMS_DIR = ROOT / "problems"
ROADMAP = ROOT / "roadmap.md"

REFERENCE_TODO = "<!-- TODO: reference solution not written yet -->"

_ROADMAP_ENTRY_RE = re.compile(r"^\s*-\s*\[( |x|X)\]\s*`([a-z0-9\-]+)`")


# --------------------------------------------------------------------------
# metaData -> cases.json entry
# --------------------------------------------------------------------------

def parse_entry(question: dict) -> dict:
    meta = json.loads(question["metaData"])

    if meta.get("systemdesign"):
        return {
            "kind": "design",
            "class": meta["classname"],
            "method": None,
            "param_types": [],
            "return_type": None,
            "output_from_param": None,
            "truncate_to_ret": False,
        }

    output = meta.get("output") or {}
    return {
        "kind": "function",
        "class": "Solution",
        "method": meta["name"],
        "param_types": [p["type"] for p in meta.get("params") or []],
        "return_type": (meta.get("return") or {}).get("type"),
        "output_from_param": output.get("paramindex"),
        "truncate_to_ret": output.get("size") == "ret",
    }


def _loads_lenient(text: str):
    try:
        return json.loads(text), True
    except (json.JSONDecodeError, TypeError):
        return text, False


def build_cases(question: dict, entry: dict) -> tuple[list[dict], bool, list[str]]:
    """Pair `exampleTestcases` (inputs, one value per line in params order)
    positionally with the `Output:` lines scraped from the statement."""
    meta = json.loads(question["metaData"])
    warnings: list[str] = []

    if meta.get("manual"):
        # LeetCode judges these itself (round-trip codecs, mainly). There is no
        # single method to call and no fixed expected output, so nothing here
        # can be generated correctly.
        warnings.append(
            "LeetCode marks this problem as manually judged -- the entry and "
            "cases must be written by hand, with compare set to 'custom' and a "
            "validate.py alongside"
        )

    if entry["kind"] == "design":
        # Design problems are always driven by two lines per case -- the op
        # list and the arg list. Some (min-stack, implement-trie) declare no
        # top-level params at all, so don't trust the count for these.
        n_params = 2
    else:
        n_params = len(meta.get("params") or [])

    raw = (question.get("exampleTestcases") or "").split("\n")
    while raw and not raw[-1].strip():
        raw.pop()

    if n_params == 0:
        return [], False, ["metaData declares no params -- cases must be written by hand"]

    if len(raw) % n_params:
        warnings.append(
            f"{len(raw)} testcase lines is not a multiple of {n_params} params -- "
            "the chunking is unreliable"
        )

    chunks = [raw[i:i + n_params] for i in range(0, len(raw), n_params)]
    outputs = extract_example_outputs(question.get("content") or "")

    if len(chunks) != len(outputs):
        warnings.append(
            f"{len(chunks)} input chunk(s) but {len(outputs)} 'Output:' line(s) "
            "in the statement -- inputs and expected answers may be misaligned"
        )

    cases: list[dict] = []
    clean = True

    for index, chunk in enumerate(chunks):
        parsed = []
        for line in chunk:
            value, ok = _loads_lenient(line)
            clean &= ok
            parsed.append(value)

        if index < len(outputs):
            expected, ok = _loads_lenient(outputs[index])
            if not ok:
                clean = False
                warnings.append(
                    f"case {index + 1}: could not parse expected output "
                    f"{outputs[index]!r} as JSON"
                )
        else:
            expected = None
            clean = False

        if entry["kind"] == "design":
            ops = parsed[0] if parsed else []
            call_args = parsed[1] if len(parsed) > 1 else []
            cases.append({"ops": ops, "args": call_args, "expected": expected})
        else:
            cases.append({"args": parsed, "expected": expected})

    verified = clean and not warnings and bool(cases)
    return cases, verified, warnings


# --------------------------------------------------------------------------
# solution.py
# --------------------------------------------------------------------------

_HEADER_RE = re.compile(r"^\s*(async\s+def|def|class)\b.*:\s*$")


def _stub_out_placeholder_bodies(code: str) -> str:
    """Second pass: bodies that are only a docstring or only `pass`.

    In-place problems ship a snippet whose entire body is
    `\"\"\"Do not return anything, modify matrix in-place instead.\"\"\"` --
    valid Python, so the textual pass leaves it alone, and the function then
    silently returns None. That reads as a *wrong* answer rather than an
    unattempted one, which is worse than useless."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code

    edits: list[tuple[int, int, bool]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if len(node.body) != 1:
            continue
        first = node.body[0]
        is_pass = isinstance(first, ast.Pass)
        is_docstring = (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        )
        if is_pass or is_docstring:
            edits.append((first.end_lineno, first.col_offset, is_pass))

    lines = code.split("\n")
    for end_lineno, indent, is_pass in sorted(edits, reverse=True):
        statement = " " * indent + "raise NotImplementedError"
        if is_pass:
            lines[end_lineno - 1] = statement
        else:
            lines.insert(end_lineno, statement)
    return "\n".join(lines)


def fill_empty_bodies(code: str) -> str:
    """LeetCode's snippets have whitespace-only bodies, which is a SyntaxError
    once written to a real file. Give every empty def a NotImplementedError --
    which the harness reads as 'not attempted yet' and reports as a skip."""
    lines = code.split("\n")
    out: list[str] = []

    for i, line in enumerate(lines):
        out.append(line)
        if not _HEADER_RE.match(line):
            continue
        indent = len(line) - len(line.lstrip())
        following = next(
            (nxt for nxt in lines[i + 1:] if nxt.strip() and not nxt.lstrip().startswith("#")),
            None,
        )
        if following is None or (len(following) - len(following.lstrip())) <= indent:
            out.append(" " * (indent + 4) + "raise NotImplementedError")

    return _stub_out_placeholder_bodies("\n".join(line.rstrip() for line in out))


def dump_spec(spec: dict) -> str:
    """Pretty-print cases.json, but keep each case on one line.

    A plain indent=2 dump puts every integer of every array on its own line,
    which makes the file miserable to review and hand-edit -- and reviewing it
    is a step in every single import."""
    tokens: dict[str, str] = {}
    shell = dict(spec)

    def _compact(key: str, values: list) -> list:
        out = []
        for i, value in enumerate(values):
            token = f"@@{key}{i}@@"
            tokens[token] = json.dumps(value, separators=(", ", ": "))
            out.append(token)
        return out

    shell["entry"] = dict(spec["entry"])
    shell["entry"]["param_types"] = "@@PARAMS@@"
    tokens["@@PARAMS@@"] = json.dumps(spec["entry"]["param_types"])
    shell["cases"] = _compact("CASE", spec.get("cases") or [])
    shell["perf"] = _compact("PERF", spec.get("perf") or [])

    text = json.dumps(shell, indent=2)
    for token, compact in tokens.items():
        text = text.replace(f'"{token}"', compact)
    return text + "\n"


SOLUTION_TEMPLATE = '''"""{title} ({difficulty})
https://leetcode.com/problems/{slug}/

Read README.md, write your solution below, then run:
    pytest problems/{dirname}
"""

from typing import *

from lib.lcnodes import ListNode, Node, TreeNode


{body}
'''


def make_solution(question: dict, dirname: str) -> str:
    snippet = python_snippet(question)
    # The real classes are imported above; the snippet's commented-out
    # definitions of them are just noise in an editor.
    body = fill_empty_bodies(snippet).strip("\n")
    return SOLUTION_TEMPLATE.format(
        title=question["title"],
        difficulty=question["difficulty"],
        slug=question["titleSlug"],
        dirname=dirname,
        body=body,
    )


TEST_TEMPLATE = '''"""Generated -- do not edit. The harness lives in lib/harness.py."""

from lib.harness import run_cases


def test_solution():
    run_cases(__file__)
'''


# --------------------------------------------------------------------------
# README.md / notes/reference.md
# --------------------------------------------------------------------------

def make_readme(question: dict, pattern: str | None, dirname: str) -> str:
    tags = ", ".join(t["name"] for t in question.get("topicTags") or []) or "-"
    hints = question.get("hints") or []

    parts = [
        f"# {question['questionFrontendId']}. {question['title']}",
        "",
        f"- **Difficulty:** {question['difficulty']}",
        f"- **Pattern:** {pattern or '-'}",
        f"- **Topics:** {tags}",
        f"- **Source:** https://leetcode.com/problems/{question['titleSlug']}/",
        "",
        "---",
        "",
        to_markdown(question.get("content") or ""),
        "",
    ]

    if hints:
        parts += ["---", "", "<details>", "<summary><b>Hints</b> (click to expand)</summary>", ""]
        for i, hint in enumerate(hints, start=1):
            parts.append(f"{i}. {re.sub(r'<[^>]+>', '', hint)}")
        parts += ["", "</details>", ""]

    parts += [
        "---",
        "",
        "## Workflow",
        "",
        "1. Write your solution in `solution.py`.",
        f"2. Run `pytest problems/{dirname}` (or the gutter icon in VSCode).",
        "3. Compare against `notes/reference.md` when you're done.",
        "",
    ]
    return "\n".join(parts)


def make_reference_placeholder(question: dict) -> str:
    return "\n".join([
        f"# {question['questionFrontendId']}. {question['title']} - reference",
        "",
        REFERENCE_TODO,
        "",
        "Ask Claude to write this up.",
        "",
    ])


# --------------------------------------------------------------------------
# roadmap lookup
# --------------------------------------------------------------------------

def pattern_for(slug: str) -> str | None:
    if not ROADMAP.exists():
        return None
    current = None
    for line in ROADMAP.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            continue
        match = _ROADMAP_ENTRY_RE.match(line)
        if match and match.group(2) == slug:
            return current
    return None


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def problem_dirname(question: dict) -> str:
    return f"{int(question['questionFrontendId']):04d}-{question['titleSlug']}"


def scaffold(question: dict, *, pattern: str | None = None,
             force: bool = False,
             reset_cases: bool = False) -> tuple[Path, dict, list[str]]:
    dirname = problem_dirname(question)
    target = PROBLEMS_DIR / dirname
    entry = parse_entry(question)
    cases, verified, warnings = build_cases(question, entry)

    if target.exists() and not force:
        raise FileExistsError(
            f"{target.relative_to(ROOT)} already exists -- pass force=True to overwrite"
        )

    (target / "notes").mkdir(parents=True, exist_ok=True)

    solution_path = target / "solution.py"
    solution_code = make_solution(question, dirname)
    compile(solution_code, str(solution_path), "exec")  # fail loudly, not at collection

    # Re-importing must never clobber a solution you're partway through.
    if not solution_path.exists():
        solution_path.write_text(solution_code, encoding="utf-8")

    (target / "test_solution.py").write_text(TEST_TEMPLATE, encoding="utf-8")
    (target / "README.md").write_text(
        make_readme(question, pattern or pattern_for(question["titleSlug"]), dirname),
        encoding="utf-8",
    )

    spec = {
        "slug": question["titleSlug"],
        "verified": verified,
        "entry": entry,
        "compare": "exact",
        "cases": cases,
        "perf": [],
    }
    # Curated cases are the expensive part of an import -- edge cases someone
    # thought up, a hand-set compare mode. A re-import must not eat them.
    cases_path = target / "cases.json"
    if cases_path.exists() and not reset_cases:
        spec = json.loads(cases_path.read_text(encoding="utf-8"))
        warnings.append("kept the existing cases.json (pass reset_cases to regenerate)")
    else:
        cases_path.write_text(dump_spec(spec), encoding="utf-8")

    reference = target / "notes" / "reference.md"
    if not reference.exists():
        reference.write_text(make_reference_placeholder(question), encoding="utf-8")

    return target, spec, warnings

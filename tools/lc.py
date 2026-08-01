"""Command line entry point.

    python tools/lc.py import <slug> [--pattern P] [--force] [--refresh]
    python tools/lc.py verify <slug|dir>      # run notes/reference.md as an oracle
    python tools/lc.py status [--all]
    python tools/lc.py check-slugs            # validate roadmap.md against LeetCode
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.harness import evaluate, module_name_for  # noqa: E402
from tools.fetch import FetchError, fetch_question  # noqa: E402
from tools.scaffold import (  # noqa: E402
    PROBLEMS_DIR,
    REFERENCE_TODO,
    ROADMAP,
    _ROADMAP_ENTRY_RE,
    scaffold,
)

CACHE_DIR = ROOT / ".cache"
_PY_BLOCK_RE = re.compile(r"```python\n(.*?)```", re.DOTALL)

if sys.stdout.isatty():
    GREEN, RED, YELLOW, DIM, RESET = (
        "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
    )
else:
    GREEN = RED = YELLOW = DIM = RESET = ""


def _resolve_problem_dir(token: str) -> Path:
    candidate = Path(token)
    if candidate.is_dir():
        return candidate.resolve()
    matches = sorted(PROBLEMS_DIR.glob(f"*-{token}")) or sorted(PROBLEMS_DIR.glob(f"{token}*"))
    if not matches:
        raise SystemExit(f"{RED}no imported problem matching {token!r}{RESET}")
    if len(matches) > 1:
        raise SystemExit(
            f"{RED}ambiguous: {', '.join(m.name for m in matches)}{RESET}"
        )
    return matches[0].resolve()


# --------------------------------------------------------------------------

def cmd_import(args) -> int:
    try:
        question = fetch_question(args.slug, refresh=args.refresh, polite_delay=args.delay)
    except FetchError as exc:
        print(f"{RED}{exc}{RESET}")
        return 1

    try:
        target, spec, warnings = scaffold(
            question, pattern=args.pattern, force=args.force,
            reset_cases=args.reset_cases,
        )
    except FileExistsError as exc:
        print(f"{RED}{exc}{RESET}")
        return 1

    rel = target.relative_to(ROOT)
    entry = spec["entry"]
    print(f"{GREEN}scaffolded{RESET} {rel}")
    print(f"  difficulty   {question['difficulty']}")
    print(f"  kind         {entry['kind']}"
          + (f" / {entry['class']}" if entry["kind"] == "design" else f" / {entry['method']}()"))
    if entry["output_from_param"] is not None:
        print(f"  in-place     answer read from param {entry['output_from_param']}"
              + (" (truncated to return value)" if entry["truncate_to_ret"] else ""))
    print(f"  cases        {len(spec['cases'])}")

    verdict = f"{GREEN}verified{RESET}" if spec["verified"] else f"{YELLOW}NEEDS REVIEW{RESET}"
    print(f"  cases.json   {verdict}")
    for warning in warnings:
        print(f"    {YELLOW}! {warning}{RESET}")

    print()
    print(f"{DIM}next: review cases.json, set `compare`, write notes/reference.md,{RESET}")
    print(f"{DIM}      then: python tools/lc.py verify {question['titleSlug']}{RESET}")
    return 0


def cmd_verify(args) -> int:
    """Run the reference solution against cases.json.

    The count check in the importer can't catch a mispaired example or a wrong
    `compare` mode. A known-good solution can. This must go green before a
    problem is handed over, so that red always means *your* bug."""
    problem_dir = _resolve_problem_dir(args.problem)
    reference = problem_dir / "notes" / "reference.md"

    if not reference.exists():
        print(f"{RED}no notes/reference.md in {problem_dir.name}{RESET}")
        return 1

    text = reference.read_text(encoding="utf-8")
    if REFERENCE_TODO in text:
        print(f"{YELLOW}{problem_dir.name}: reference solution not written yet{RESET}")
        return 1

    spec = json.loads((problem_dir / "cases.json").read_text(encoding="utf-8"))
    wanted = f"class {spec['entry'].get('class') or 'Solution'}"

    # A write-up often shows more than one implementation. Check every block
    # that actually defines the entry class, so alternates aren't left untested.
    blocks = [b for b in _PY_BLOCK_RE.findall(text) if wanted in b]
    if not blocks:
        print(f"{RED}no ```python block defining `{wanted}` in "
              f"{reference.relative_to(ROOT)}{RESET}")
        return 1

    CACHE_DIR.mkdir(exist_ok=True)
    stem = problem_dir.name.replace("-", "_")
    failed = False

    for index, block in enumerate(blocks, start=1):
        label = f"solution {index}/{len(blocks)}"
        scratch = CACHE_DIR / f"ref_{stem}_{index}.py"
        scratch.write_text(
            "from typing import *\n"
            "from lib.lcnodes import ListNode, Node, TreeNode\n\n" + block,
            encoding="utf-8",
        )

        try:
            report = evaluate(
                scratch, problem_dir / "cases.json", problem_dir,
                module_name=f"{module_name_for(problem_dir)}_reference_{index}",
            )
        except Exception as exc:  # a broken write-up shouldn't look like a pass
            print(f"{RED}{problem_dir.name} [{label}]: {type(exc).__name__}: {exc}{RESET}")
            failed = True
            continue

        if report.not_attempted:
            print(f"{RED}{problem_dir.name} [{label}]: raised NotImplementedError{RESET}")
            failed = True
        elif report.failures:
            total = len(report.failures) + report.passed
            print(f"{RED}{problem_dir.name} [{label}]: FAILED "
                  f"{len(report.failures)}/{total} cases{RESET}")
            print(f"{DIM}the test data or the compare mode is wrong, "
                  f"not the reference{RESET}\n")
            for failure in report.failures:
                print(failure + "\n")
            failed = True
        else:
            print(f"{GREEN}{problem_dir.name} [{label}]: passes "
                  f"{report.passed}/{report.passed} cases{RESET}")

    if failed:
        return 1

    spec_unverified = not spec.get("verified", False)
    if spec_unverified:
        print(f"{YELLOW}cases.json still says verified=false -- flip it now that "
              f"the reference agrees{RESET}")
    return 0


def cmd_status(args) -> int:
    if not PROBLEMS_DIR.exists():
        print("no problems imported yet")
        return 0

    rows = []
    for problem_dir in sorted(PROBLEMS_DIR.iterdir()):
        if not (problem_dir / "cases.json").exists():
            continue
        report = evaluate(
            problem_dir / "solution.py", problem_dir / "cases.json", problem_dir
        )
        if report.not_attempted:
            state = f"{DIM}todo{RESET}"
        elif report.failures:
            state = f"{RED}failing{RESET}"
        else:
            state = f"{GREEN}solved{RESET}"
        flag = f" {YELLOW}(cases unverified){RESET}" if report.unverified else ""
        rows.append((problem_dir.name, state, flag))

    for name, state, flag in rows:
        print(f"  {state:<20} {name}{flag}")
    print(f"\n{len(rows)} problem(s) imported")
    return 0


def cmd_check_slugs(args) -> int:
    if not ROADMAP.exists():
        print(f"{RED}no roadmap.md{RESET}")
        return 1

    slugs = [
        m.group(2)
        for m in (_ROADMAP_ENTRY_RE.match(line) for line in ROADMAP.read_text(encoding="utf-8").splitlines())
        if m
    ]
    print(f"checking {len(slugs)} slug(s)...")

    bad = []
    for slug in slugs:
        try:
            fetch_question(slug, polite_delay=args.delay)
        except FetchError as exc:
            bad.append((slug, str(exc)))
            print(f"  {RED}x{RESET} {slug}: {exc}")

    if bad:
        print(f"\n{RED}{len(bad)} bad slug(s){RESET}")
        return 1
    print(f"{GREEN}all {len(slugs)} slugs resolve{RESET}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="lc")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("import", help="scaffold a problem directory")
    p.add_argument("slug")
    p.add_argument("--pattern", default=None, help="override the roadmap.md pattern group")
    p.add_argument("--force", action="store_true",
                   help="rewrite an existing directory (keeps solution.py and cases.json)")
    p.add_argument("--reset-cases", action="store_true",
                   help="with --force, also discard the curated cases.json")
    p.add_argument("--refresh", action="store_true", help="ignore the .cache copy")
    p.add_argument("--delay", type=float, default=0.0)
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("verify", help="run notes/reference.md against cases.json")
    p.add_argument("problem")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("status", help="show progress across imported problems")
    p.add_argument("--all", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("check-slugs", help="validate roadmap.md against LeetCode")
    p.add_argument("--delay", type=float, default=0.3)
    p.set_defaults(func=cmd_check_slugs)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

"""Repo-root conftest: puts the project root on sys.path.

Every generated test is a two-line shim that does `from lib.harness import
run_cases`, and every generated solution does `from lib.lcnodes import ...`.
Neither resolves unless the repo root is importable, so this must run before
collection -- which is exactly what a rootdir conftest guarantees.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# interview-prep

LeetCode practice in VSCode instead of in a browser tab. Read the problem in
Markdown, write Python in a real editor, run tests to see if it passes, and
keep the worked solution beside it for afterwards.

Problems are pulled from LeetCode on demand — nothing is pre-built. The catalog
of what's available is [`roadmap.md`](roadmap.md) (NeetCode 150).

## Two repos

This one is the framework: the importer, the test harness, the catalog. It has
no problems and no solutions in it.

`problems/` is a **separate repo** nested inside this checkout (and gitignored
here) holding imported problems and solutions. Keeping them apart means the
framework stays shareable while progress stays its own history.

To set up from scratch:

```
git clone <this repo> interview-prep
cd interview-prep
git clone <progress repo> problems      # or just start importing
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

Nothing in the tooling knows about the split — `problems/` is just a directory
as far as it's concerned.

---

## The loop

**1. Import a problem.** Ask Claude — "import `3sum`" — or do it yourself:

```
.venv\Scripts\python tools\lc.py import 3sum
```

That creates `problems/0015-3sum/` with the statement, a stub, test data, and a
reference write-up.

**2. Read `README.md`, solve it in `solution.py`.**

**3. Run it.** Click the gutter icon next to the test in VSCode, or:

```
.venv\Scripts\python -m pytest problems/0015-3sum
```

A failure shows the input, what was expected, and what you returned.

**4. Read `notes/reference.md`** once you're done — or ask Claude about it.
It carries the approach, complexity, the pitfalls that actually bite, and
pointers to related problems.

**5. Tick the box in `roadmap.md`.**

Running bare `pytest` from the root does the whole repo at once: green for
solved, red for broken, skipped for anything you haven't started. It also runs
`tests/`, which covers the shared harness itself — a bug in there would look
like a wrong answer in every problem at once.

VSCode's Test Explorer is pointed at `problems/` only, so it stays a board of
what you're practising. The harness tests show up on the terminal run.

---

## Commands

```
lc.py import <slug>       scaffold a problem  (--force to refresh a statement)
lc.py verify <slug>       run notes/reference.md against cases.json
lc.py status              solved / failing / todo across everything imported
lc.py check-slugs         confirm every roadmap.md slug still resolves
```

All of them want the venv's Python: `.venv\Scripts\python tools\lc.py ...`

---

## How a problem directory is laid out

```
problems/0015-3sum/
  README.md            the statement, in Markdown, with hints folded away
  solution.py          you write here
  test_solution.py     generated shim -- don't edit
  cases.json           test data and the comparison rule
  notes/reference.md   worked solution, complexity, pitfalls
```

### cases.json

The importer fills this in from LeetCode's own data, then Claude reviews it and
adds edge cases. `compare` picks how your answer is judged, which matters
because plenty of problems accept more than one right answer:

| mode | when |
|---|---|
| `exact` | the default |
| `unordered` | outer order irrelevant — `two-sum` may return `[1,0]` |
| `set_of_sets` | inner and outer order irrelevant — `3sum`, `group-anagrams` |
| `float` | numeric, within `tolerance` |
| `any_of` | `expected` is a list of acceptable answers |
| `custom` | delegates to `validate(args, actual)` in a `validate.py` beside it |

`"verified": false` means the importer couldn't confirm the expected outputs
line up with the inputs. The test run says so too. If that's set, distrust the
test data before you distrust yourself.

`"verified": true` is weaker than it sounds — it means the inputs and outputs
lined up *structurally* and every value parsed. Counts can line up while the
data is still wrong. Only `lc.py verify` passing means the cases are actually
right, which is why it's a step in every import.

---

## Why imports go through Claude

Two things in an import need judgment rather than parsing. LeetCode's API gives
inputs but not expected outputs — those are scraped from the statement HTML, and
the pairing needs checking. And the right `compare` mode can't be derived from
anything the API returns.

So each import ends with Claude writing `notes/reference.md` and running it
against `cases.json` via `lc.py verify`. That's the point of the step: a known
good solution proves the test data is right, so when *you* see red later, the
bug is yours. It has already caught a bad expected value during setup.

---

## Adding a problem that isn't in roadmap.md

Any LeetCode slug works — take it from the URL:

```
.venv\Scripts\python tools\lc.py import spiral-matrix-ii --pattern "Math & Geometry"
```

LeetCode Premium problems can't be imported; their statements aren't public.
The seven in NeetCode 150 are marked in `roadmap.md`.

A few problems are judged by LeetCode itself rather than against fixed expected
output — `serialize-and-deserialize-binary-tree` is the one in this catalog,
since any encoding is valid so long as it round-trips. The importer flags these
and their `cases.json` has to be written by hand with `compare: "custom"` and a
`validate.py` beside it.

---

## Performance tests

Off by default (`pytest.ini` sets `-m "not perf"`) so a slow laptop can't produce
a spurious red. `cases.json` keeps a `perf` list for when you want one; run them
with `pytest -m perf`.

---

## Setup, if you ever need to rebuild it

```
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

Optional, so `python problems/xxxx/solution.py` runs directly rather than only
under pytest — write the repo path into the venv:

```
.venv\Scripts\python -c "import pathlib,sysconfig; pathlib.Path(sysconfig.get_paths()['purelib'],'interview_prep.pth').write_text(str(pathlib.Path().resolve()))"
```

Python 3.12 specifically — the `python` on PATH is a 32-bit 3.8 and won't do.

---

## A note on the imported statements

Problem text belongs to LeetCode. This is a personal, local study copy. Keep the
repo private if you ever push it anywhere.

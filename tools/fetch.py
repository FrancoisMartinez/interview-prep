"""LeetCode GraphQL client.

The endpoint answers unauthenticated. Raw responses are cached under .cache/
so re-scaffolding a problem never refetches, and a bulk pass is resumable.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ENDPOINT = "https://leetcode.com/graphql/"
ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / ".cache"

QUESTION_QUERY = """
query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    questionId
    questionFrontendId
    title
    titleSlug
    difficulty
    isPaidOnly
    content
    hints
    topicTags { name slug }
    codeSnippets { lang langSlug code }
    exampleTestcases
    sampleTestCase
    metaData
  }
}
"""

_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (interview-prep local study tool)",
    "Referer": "https://leetcode.com/",
}


class FetchError(RuntimeError):
    pass


def _post(query: str, variables: dict, timeout: int = 30) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = urllib.request.Request(ENDPOINT, data=payload, headers=_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise FetchError(f"HTTP {exc.code} from LeetCode: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise FetchError(f"network error reaching LeetCode: {exc.reason}") from exc

    if body.get("errors"):
        raise FetchError(f"GraphQL error: {body['errors']}")
    return body["data"]


def fetch_question(slug: str, *, refresh: bool = False, polite_delay: float = 0.0) -> dict:
    """Return the raw question payload for `slug`, caching it under .cache/."""
    CACHE_DIR.mkdir(exist_ok=True)
    cached = CACHE_DIR / f"{slug}.json"

    if cached.exists() and not refresh:
        return json.loads(cached.read_text(encoding="utf-8"))

    if polite_delay:
        time.sleep(polite_delay)

    data = _post(QUESTION_QUERY, {"titleSlug": slug})
    question = data.get("question")
    if question is None:
        raise FetchError(
            f"no such problem: {slug!r} -- check the slug against the leetcode.com URL"
        )
    if question.get("isPaidOnly"):
        raise FetchError(
            f"{slug!r} is LeetCode Premium-only; its statement is not available"
        )

    cached.write_text(json.dumps(question, indent=2), encoding="utf-8")
    return question


def python_snippet(question: dict) -> str:
    for snippet in question.get("codeSnippets") or []:
        if snippet.get("langSlug") == "python3":
            return snippet["code"]
    raise FetchError(f"{question['titleSlug']} has no Python3 code snippet")

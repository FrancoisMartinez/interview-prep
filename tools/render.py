"""HTML statement -> Markdown, and expected-output extraction.

markdownify renders <pre> as indented text, which mangles LeetCode's worked
examples. So <pre> blocks are lifted out first and re-emitted as fenced code
blocks; only the remainder goes through markdownify.
"""

from __future__ import annotations

import html
import re

from markdownify import markdownify

_PRE_RE = re.compile(r"<pre\b[^>]*>(.*?)</pre>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_SUP_RE = re.compile(r"<sup>(.*?)</sup>", re.DOTALL | re.IGNORECASE)
_SUB_RE = re.compile(r"<sub>(.*?)</sub>", re.DOTALL | re.IGNORECASE)
_BLANKS_RE = re.compile(r"\n{3,}")
# Function problems write "Output: [0,1]"; design problems write "Output" on
# its own line with the value beneath it.
_OUTPUT_RE = re.compile(r"Output:?[ \t]*", re.IGNORECASE)
_EXPLANATION_RE = re.compile(r"Explanation:?", re.IGNORECASE)

# An example is either an old-style <pre> or a new-style example-block div.
_EXAMPLE_BLOCK_RE = re.compile(
    r"<pre\b[^>]*>(.*?)</pre>"
    r"|<div\b[^>]*class=\"[^\"]*example-block[^\"]*\"[^>]*>(.*?)</div>",
    re.DOTALL | re.IGNORECASE,
)


def _plain_text(fragment: str) -> str:
    """Strip tags and unescape entities, preserving line structure."""
    text = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.IGNORECASE)
    text = _TAG_RE.sub("", text)
    return html.unescape(text).replace("\xa0", " ")


def extract_example_outputs(content_html: str) -> list[str]:
    """The expected answers, in document order.

    `exampleTestcases` gives inputs only -- outputs live here. Older statements
    wrap each example in <pre>; newer ones use <div class="example-block">.
    Blocks without an "Output:" (diagrams, follow-up notes) are skipped so they
    can't shift the pairing.
    """
    outputs: list[str] = []
    for match in _EXAMPLE_BLOCK_RE.finditer(content_html or ""):
        text = _plain_text(match.group(1) if match.group(1) is not None else match.group(2))
        found = _OUTPUT_RE.search(text)
        if not found:
            continue

        # Everything up to "Explanation", so multi-line answers survive --
        # combination-sum-ii prints its list of lists across six lines.
        rest = text[found.end():].lstrip("\n")
        answer = _EXPLANATION_RE.split(rest)[0].strip()
        outputs.append(answer)
    return outputs


def to_markdown(content_html: str) -> str:
    if not content_html:
        return "_No statement returned by LeetCode._"

    html_text = _SUP_RE.sub(r"^\1", content_html)
    html_text = _SUB_RE.sub(r"_\1", html_text)

    blocks: list[str] = []

    def _stash(match: re.Match) -> str:
        blocks.append(_plain_text(match.group(1)).strip("\n"))
        return f"<p>@@PRE{len(blocks) - 1}@@</p>"

    html_text = _PRE_RE.sub(_stash, html_text)

    markdown = markdownify(html_text, heading_style="ATX", bullets="-")
    markdown = markdown.replace("\xa0", " ")

    for index, block in enumerate(blocks):
        markdown = markdown.replace(
            f"@@PRE{index}@@", f"```\n{block}\n```"
        )

    markdown = _BLANKS_RE.sub("\n\n", markdown)
    return markdown.strip()

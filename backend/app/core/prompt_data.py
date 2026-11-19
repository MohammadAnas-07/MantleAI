"""Untrusted text inside a prompt: make our data tags and chat-template markers harmless.

Prompts wrap data (memory, code, summaries, plans) in tags such as `<source>`. Text inside the
data that looks like one of those tags, or like a chat-template boundary, could end the block
early or fake a new turn. `defang` escapes just those markers; the rest of the text is unchanged.
Shared by the conversations and workflow modules. No I/O.
"""

import re
from collections.abc import Iterable
from functools import cache


@cache
def _markers(tags: tuple[str, ...]) -> re.Pattern[str]:
    names = "|".join(re.escape(t) for t in tags)
    return re.compile(
        rf"</?\s*({names})\b"
        r"|<\||\|>"
        r"|\[/?INST\]"
        r"|<</?SYS>>",
        re.IGNORECASE,
    )


def _escape(match: re.Match[str]) -> str:
    return match.group(0).replace("<", "&lt;").replace(">", "&gt;").replace("[", "&#91;")


def defang(text: str, tags: Iterable[str]) -> str:
    """`</source>` becomes `&lt;/source>`, `<|im_start|>` becomes `&lt;|im_start|&gt;`,
    `[INST]` becomes `&#91;INST]`. The text stays readable; it just can't open or close a
    block whose tag is in `tags`."""
    return _markers(tuple(tags)).sub(_escape, text)

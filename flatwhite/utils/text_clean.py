"""Reader-facing text hygiene.

Victor's ABSOLUTE rule: never an em dash in anything a reader sees (emails,
editorials, newsletter copy). Use hyphens. LLM output routinely contains em
dashes, and prompt rules do not reliably stop it, so this is applied as a
deterministic post-process at every point where generated/pasted text becomes
reader-facing (segment generation output and the beehiiv HTML converter).
"""

import re

# Em dash (U+2014) and horizontal bar (U+2015), with any surrounding spaces,
# become a spaced hyphen: "soft patch — it is" and "soft patch—it is" both
# render as "soft patch - it is".
_EM_DASH = re.compile(r"\s*[—―]\s*")

# En dash (U+2013) between digits is a numeric range: "2010–2020" -> "2010-2020".
_EN_DASH_RANGE = re.compile(r"(?<=\d)\s*–\s*(?=\d)")

# En dash used as sentence punctuation -> spaced hyphen.
_EN_DASH = re.compile(r"\s*–\s*")

# A line that is nothing but dashes is the DIVIDER FURNITURE the published
# editions run between Off the Clock entries and event groups - it is not
# prose punctuation, so the em-dash rule must not touch it. Without this,
# generating Off the Clock turned the divider into a row of " - " fragments
# (caught on a real run, 25 Aug 2026).
_DIVIDER_LINE = re.compile(r"^[—―–\-]{3,}$")


def strip_reader_dashes(text: str) -> str:
    """Replace em/en dashes with hyphens for reader-facing copy.

    Idempotent and safe on empty/None-ish input. Numeric ranges collapse to a
    plain hyphen; every other dash becomes a spaced hyphen. Divider-only lines
    are left exactly as they are.
    """
    if not text:
        return text
    out = []
    for line in text.split("\n"):
        if _DIVIDER_LINE.match(line.strip()):
            out.append(line)
            continue
        line = _EM_DASH.sub(" - ", line)
        line = _EN_DASH_RANGE.sub("-", line)
        line = _EN_DASH.sub(" - ", line)
        out.append(line)
    return "\n".join(out)

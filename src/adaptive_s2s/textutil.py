"""Small text helpers: tokens, sentences and a syllable estimate.

The syllable count is a heuristic. It is only used as the numerator of speaking rate, and the same
function measures the user's speech and the agent's speech, so its bias cancels in comparisons.
"""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)*")
_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]*")
_VOWEL_GROUP_RE = re.compile(r"[aeiouy]+")

_ONES = {0: 2, 1: 1, 2: 1, 3: 1, 4: 1, 5: 1, 6: 1, 7: 2, 8: 1, 9: 1, 10: 1, 11: 3, 12: 1,
         13: 2, 14: 2, 15: 2, 16: 2, 17: 3, 18: 2, 19: 2}
_TENS = {2: 2, 3: 2, 4: 2, 5: 2, 6: 2, 7: 3, 8: 2, 9: 2}


def normalize(text: str) -> str:
    """Lower-case and straighten apostrophes."""
    return text.lower().replace("’", "'").replace("‘", "'")


def tokens(text: str) -> list[str]:
    """Word tokens, lower-cased, with inner apostrophes kept ("don't", "y'all")."""
    return _TOKEN_RE.findall(normalize(text))


def sentences(text: str) -> list[str]:
    """Sentences split on . ! ? (good enough for short spoken replies)."""
    return [s.strip() for s in _SENTENCE_RE.findall(text) if tokens(s)]


def _number_syllables(digits: str) -> int:
    n = int(digits)
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + (_ONES[n % 10] if n % 10 else 0)
    return 2 * len(digits)  # rough: longer numbers are rare in these scripts


def count_syllables(word: str) -> int:
    """Estimate the syllables in one word."""
    w = normalize(word).strip("'")
    if not w:
        return 0
    if w.isdigit():
        return _number_syllables(w)
    extra = 0
    if w.endswith("n't"):
        stem = w[:-3]
        # "didn't", "wasn't", "couldn't" add a syllable; "don't", "can't", "won't" do not.
        if stem and stem[-1] not in "aeiouy":
            extra = 1
        w = stem
    w = re.sub(r"[^a-z]", "", w)
    if not w:
        return max(1, extra)
    count = len(_VOWEL_GROUP_RE.findall(w))
    if count > 1:
        syllabic_le = w.endswith("le") and len(w) > 2 and w[-3] not in "aeiouy"  # "table", "people"
        if w.endswith("e") and not syllabic_le and not w.endswith(("ee", "ye")):
            count -= 1  # silent final e: "make", "time", "schedule"
        elif w.endswith("es") and not w.endswith(("ses", "xes", "zes", "ches", "shes", "ces", "ges")):
            count -= 1  # "makes", "times"
        elif w.endswith("ed") and len(w) > 3 and w[-3] not in "td":
            count -= 1  # "walked", "called"
    return max(1, count) + extra


def count_syllables_text(text: str) -> int:
    return sum(count_syllables(t) for t in tokens(text))

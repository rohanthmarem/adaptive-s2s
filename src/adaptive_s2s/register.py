"""Lexical measurements: what words a turn used.

This is deliberately a small, inspectable rule set. It reads the transcript only. It never looks at
pace, pitch or loudness, because fast speech is not evidence that someone uses slang.

The word lists are short on purpose. Ambiguous words ("fire", "sick", "mid", "died") are left out so
that ordinary sentences do not trigger a style change.
"""

from __future__ import annotations

import re

from .textutil import normalize, sentences, tokens
from .types import RegisterFeatures

SLANG = (
    "ngl", "not gonna lie", "lowkey", "low key", "highkey", "high key", "no cap", "for real", "fr",
    "vibe", "vibes", "vibing", "slay", "bruh", "bro", "dude", "sus", "rizz", "cooked", "tbh", "idk",
    "imo", "legit", "deadass", "goated", "bussin", "ghosted", "salty", "chill", "cringe", "sheesh",
    "fam", "bestie", "banger", "hits different", "omg", "lol", "lmao", "af",
)
REDUCTIONS = (
    "gonna", "wanna", "gotta", "kinda", "sorta", "lemme", "gimme", "dunno", "y'all", "ain't", "cuz",
    "tryna", "finna", "imma", "outta", "lotta",
)
CASUAL_MARKERS = (
    "yeah", "nah", "yep", "nope", "hey", "okay", "ok", "cool", "awesome", "stuff", "guys", "totally",
    "super", "pretty much",
)
FORMAL_STRONG = (
    "regarding", "furthermore", "moreover", "therefore", "additionally", "accordingly", "consequently",
    "pursuant", "kindly", "please advise", "at your earliest convenience", "i would like to",
    "i would appreciate", "could you please", "would you be able", "with respect to", "in order to",
    "as per", "per our", "going forward", "prior to", "action items", "stakeholders", "stakeholder",
    "deliverable", "deliverables",
)
FORMAL_WEAK = (
    "however", "ensure", "confirm", "clarify", "provide", "assistance", "inquire", "request",
    "timeline", "quarterly", "follow up", "thank you for", "i appreciate", "schedule a",
)
DISTRESS = (
    "overwhelmed", "exhausted", "hopeless", "worthless", "heartbroken", "devastated", "terrified",
    "panicking", "panic attack", "can't cope", "can't do this", "can't take", "falling apart",
    "lost my job", "got fired", "laid off", "passed away", "funeral", "crying", "cried", "can't sleep",
    "so tired", "so stressed", "stressed out", "burned out", "burnt out", "depressed", "anxious",
    "lonely", "scared", "i failed", "failed my", "don't know what to do", "give up", "giving up",
    "miserable", "broke up", "diagnosed", "bad news", "struggling", "rough day", "hard day",
    "worst day", "not okay", "grief", "grieving",
)
# Words that call for a fixed safety reply instead of a generated one.
CRISIS = (
    "kill myself", "killing myself", "suicide", "suicidal", "end my life", "end it all", "want to die",
    "wanna die", "hurt myself", "harm myself", "self harm", "don't want to be here",
    "better off without me", "no reason to live",
)

_CONTRACTION_RE = re.compile(r"^[a-z]+'(?:s|re|ve|ll|d|m|t)$|^[a-z]+n't$")


def _hits(padded: str, terms: tuple[str, ...]) -> list[str]:
    """Terms that appear as whole words or whole phrases, in list order, without duplicates."""
    return [t for t in terms if f" {t} " in padded]


def analyze(text: str) -> RegisterFeatures:
    """Measure the register cues in one transcript."""
    toks = tokens(text)
    sents = sentences(text)
    n = len(toks)
    padded = " " + " ".join(toks) + " "

    contractions = sum(1 for t in toks if _CONTRACTION_RE.match(t))
    per_100 = 100.0 * contractions / n if n else 0.0
    slang = _hits(padded, SLANG)
    reductions = _hits(padded, REDUCTIONS)
    casual_markers = _hits(padded, CASUAL_MARKERS)
    strong = _hits(padded, FORMAL_STRONG)
    weak = _hits(padded, FORMAL_WEAK)
    mean_len = n / len(sents) if sents else 0.0

    casual = 0.5 * len(slang) + 0.25 * len(reductions) + 0.1 * min(len(casual_markers), 3)
    if per_100 >= 8.0 and n >= 6:
        casual += 0.2
    formal = 0.4 * len(strong) + 0.15 * len(weak)
    if contractions == 0 and not reductions and not slang and n >= 12:
        formal += 0.25
    if mean_len >= 16.0:
        formal += 0.15

    return RegisterFeatures(
        n_tokens=n,
        n_sentences=len(sents),
        mean_sentence_len=mean_len,
        contractions_per_100=per_100,
        reductions=reductions,
        slang_hits=slang,
        formal_hits=strong + weak,
        distress_hits=_hits(padded, DISTRESS),
        crisis_hits=_hits(padded, CRISIS),
        casual_evidence=min(1.0, casual),
        formal_evidence=min(1.0, formal),
    )


def style_counts(text: str) -> dict[str, float]:
    """Style measurements of any text. The evaluation runs this on the agent's replies."""
    f = analyze(text)
    return {
        "n_tokens": f.n_tokens,
        "contractions_per_100": f.contractions_per_100,
        "slang": len(f.slang_hits),
        "reductions": len(f.reductions),
        "formal_markers": len(f.formal_hits),
        "mean_sentence_len": f.mean_sentence_len,
    }


__all__ = ["analyze", "style_counts", "normalize", "SLANG", "REDUCTIONS", "DISTRESS", "CRISIS"]

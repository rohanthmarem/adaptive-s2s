"""Turns the text controls into the prompt, and cleans the model's reply for speech."""

from __future__ import annotations

import re

from .textutil import sentences
from .types import TextControls

SYSTEM_BASE = (
    "You are a voice assistant in a spoken conversation. Your reply is read aloud, so write plain "
    "spoken English: no markdown, no lists, no emojis and no stage directions. Respond to what the "
    "user said. The substance of your answer must stay the same whatever the style instructions say."
)

_REGISTER_BRIEF = {
    "casual": "Style: casual and relaxed, like talking with a friend. Use contractions. Keep sentences short.",
    "neutral": "Style: plain and friendly. Use contractions where they sound natural. No slang.",
    "formal": (
        "Style: professional and structured. Use complete sentences. No slang and no contractions. "
        "Give the answer first, then the next step."
    ),
}

SUPPORTIVE_BRIEF = (
    "The user sounds upset. Start with one short sentence that acknowledges how they feel. Stay calm "
    "and warm. Do not joke, do not lecture and do not list advice. Offer one small next step or ask "
    "one gentle question."
)

# Used instead of a generated reply when the user's words signal a crisis.
CRISIS_REPLY = (
    "I'm really sorry you're feeling this way, and I'm glad you told me. I'm an AI, so I can't give "
    "you the help you deserve right now. If you might be in danger, please call your local emergency "
    "number. In the US and Canada you can call or text 988 to talk with someone right away. Is there "
    "someone you trust who can be with you?"
)


def style_brief(tc: TextControls) -> str:
    """The style part of the system prompt for one turn."""
    lines = [_REGISTER_BRIEF[tc.register]]
    if tc.register == "casual":
        if tc.slang_allowed:
            lines.append(
                f"The user used these expressions: {', '.join(tc.slang_allowed)}. You may reuse one of "
                "them once if it fits naturally. Do not add any other slang."
            )
        else:
            lines.append("Do not add slang the user did not use.")
    if tc.supportive:
        lines.append(SUPPORTIVE_BRIEF)
    lines.append(f"Reply in at most {tc.max_sentences} sentences.")
    return "\n".join(lines)


def build_messages(history: list[tuple[str, str]], user_text: str, tc: TextControls) -> list[dict[str, str]]:
    """Chat messages for the language model. `history` holds earlier (user, assistant) turns."""
    messages = [{"role": "system", "content": SYSTEM_BASE + "\n\n" + style_brief(tc)}]
    for user, assistant in history[-6:]:
        messages.append({"role": "user", "content": user})
        messages.append({"role": "assistant", "content": assistant})
    messages.append({"role": "user", "content": user_text})
    return messages


_MARKUP_RE = re.compile(r"[*_#`>|]+")
_STAGE_RE = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_NON_SPEECH_RE = re.compile(r"[^\w\s.,!?;:'\"%$&/+-]", flags=re.UNICODE)


def clean_reply(text: str, max_sentences: int) -> str:
    """Make a model reply safe to read aloud: strip markup and emojis, and enforce the length cap."""
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = text.replace("—", ", ").replace("–", ", ")
    text = _STAGE_RE.sub(" ", text)
    text = _MARKUP_RE.sub(" ", text)
    text = _NON_SPEECH_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)
    kept = sentences(text)[:max_sentences]
    result = " ".join(kept) if kept else text
    if result.count('"') % 2:  # the length cap can cut a quotation in half
        result = result.replace('"', "")
    return result

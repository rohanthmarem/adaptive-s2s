from dataclasses import replace
import numpy as np
import pytest
from adaptive_s2s.acoustic import measure
from adaptive_s2s.config import DEFAULT_POLICY as C
from adaptive_s2s.textutil import count_syllables
from adaptive_s2s.register import analyze
from adaptive_s2s.state import update_state
from adaptive_s2s.policy import decide
from adaptive_s2s.prompting import clean_reply
from adaptive_s2s.types import ARMS, AffectReading, StyleState, Tracked


@pytest.mark.parametrize("word,n", [("cat", 1), ("table", 2), ("walking", 2), ("make", 1), ("seven", 2), ("42", 3)])
def test_syllables(word, n):
    assert count_syllables(word) == n


def signal():
    rng = np.random.default_rng(1)
    return np.concatenate([rng.normal(0, .1, 16000), np.zeros(8000), rng.normal(0, .1, 16000)]).astype("float32")


def features():
    return measure(signal(), 16000, "we can discuss the whole plan today", with_pitch=False)


def test_acoustics():
    f = features()
    assert f.valid and .17 < f.pause_fraction < .22
    for x in (signal() * .1, np.pad(signal(), (16000, 0))):
        other = measure(x, 16000, "we can discuss the whole plan today", with_pitch=False)
        assert other.articulation_rate_sps == pytest.approx(f.articulation_rate_sps, rel=.02)
    assert not measure(np.zeros(16000), 16000, "hello").valid
    assert not measure(signal(), 16000, "hi").valid


def test_register():
    casual = analyze("Hey dude I'm kinda gonna chill with my bro today")
    formal = analyze("Regarding our meeting, could you please provide the timeline and confirm the deliverables?")
    neutral = analyze("The book is on the table.")
    assert casual.casual_evidence > casual.formal_evidence
    assert formal.formal_evidence > formal.casual_evidence
    assert neutral.casual_evidence == 0
    assert analyze("I feel overwhelmed and scared").distress_hits


def test_state():
    f, a = features(), AffectReading(False)
    s = update_state(StyleState(), f, a, analyze("The book is on the table."))
    assert s.rate.value == f.articulation_rate_sps
    s2 = update_state(s, replace(f, articulation_rate_sps=8), a, analyze("The book is on the table."))
    assert s2.rate.value == pytest.approx(s.rate.value * .6 + 8 * .4)
    relaxed = update_state(s2, replace(f, valid=False), a, analyze("Yes."))
    assert abs(relaxed.rate.value - C.neutral_rate_sps) < abs(s2.rate.value - C.neutral_rate_sps)
    casual = replace(s, casual=1., register="casual")
    short = update_state(casual, f, a, analyze("Yes."))
    assert short.casual > .9
    upset = update_state(s, f, a, analyze("I am overwhelmed and scared"))
    assert upset.support == 1.
    calm = update_state(upset, f, a, analyze("The book is here"))
    assert calm.support == pytest.approx(C.support_release)
    crisis = update_state(s, f, a, analyze("I want to kill myself"))
    assert crisis.crisis
    assert not update_state(crisis, f, a, analyze("The book is here")).crisis


def test_policy():
    state = StyleState(rate=Tracked(100), register="casual", casual=1)
    assert decide(state).voice.speed == C.speed_max
    assert decide(replace(state, rate=Tracked(.1))).voice.speed == C.speed_min
    assert decide(state, ARMS["static"]) == decide(StyleState(), ARMS["static"])
    assert decide(state, ARMS["text-only"]).voice.speed == 1.
    assert decide(state, ARMS["voice-only"]).text.register == "neutral"
    assert decide(replace(state, support=1)).voice.speed <= C.supportive_speed_cap
    for arm in ARMS.values():
        assert decide(replace(state, crisis=True), arm).text.crisis


def test_clean():
    assert clean_reply("**Hello!** (smiles) Next sentence. Third.", 2) == "Hello! Next sentence."


def test_possessive_is_not_a_contraction():
    from adaptive_s2s import register
    assert register.analyze("The doctor's office left a message.").contractions_per_100 == 0
    assert register.analyze("It's fine, I don't mind, and that's all we've got.").contractions_per_100 > 0

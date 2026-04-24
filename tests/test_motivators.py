import pytest

from engine.motivators import Motivator, MotivatorSource
from engine.stats import StatName


def test_motivator_decays_over_time():
    m = Motivator(
        target_stat=StatName.CONFIDENCE,
        delta=0.2,
        decay_rate=0.5,
        source=MotivatorSource.COMPLIMENT,
        salience=1.0,
    )
    assert m.current_value(0) == pytest.approx(0.2)
    assert m.current_value(1) == pytest.approx(0.1)
    assert m.current_value(2) == pytest.approx(0.05)


def test_high_salience_slows_decay():
    fast = Motivator(
        target_stat=StatName.CONFIDENCE,
        delta=0.2,
        decay_rate=0.5,
        source=MotivatorSource.CROWD,
        salience=1.0,
    )
    slow = Motivator(
        target_stat=StatName.CONFIDENCE,
        delta=0.2,
        decay_rate=0.5,
        source=MotivatorSource.CROWD,
        salience=4.0,
    )
    assert slow.current_value(4) > fast.current_value(4)


def test_motivator_roundtrip():
    m = Motivator(
        target_stat=StatName.MOTIVATION,
        delta=-0.1,
        decay_rate=0.3,
        source=MotivatorSource.CRITICISM,
        salience=1.5,
    )
    assert Motivator.from_dict(m.to_dict()) == m

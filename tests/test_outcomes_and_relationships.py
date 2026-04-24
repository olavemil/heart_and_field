from engine.outcomes import OutcomeRecord, WeekPhase
from engine.relationships import RelationshipDynamic, RelationshipState


def test_week_phase_roundtrip():
    wp = WeekPhase(season=2, week=7, phase=3)
    assert WeekPhase.from_dict(wp.to_dict()) == wp


def test_outcome_roundtrip_preserves_flags_and_deltas():
    o = OutcomeRecord(
        event_id="argument",
        timestamp=WeekPhase(season=1, week=4),
        participants={"aggressor": "p1", "target": "p2"},
        branch_taken="apologise",
        summary="He backed down.",
        arc_summary="First crack in the bond.",
        stat_deltas={
            "p1": {"confidence": -0.05},
            "p2": {"trust_in_p1": -0.1},
        },
        flags={"private"},
    )
    restored = OutcomeRecord.from_dict(o.to_dict())
    assert restored == o


def test_relationship_roundtrip():
    r = RelationshipState(
        familiarity=0.8,
        trust=0.3,
        tension=0.6,
        attraction=0.2,
        dynamic=RelationshipDynamic.ROMANTIC,
        hidden_flags={"secret_kiss", "unresolved_argument"},
    )
    assert RelationshipState.from_dict(r.to_dict()) == r

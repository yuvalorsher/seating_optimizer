import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from seating_optimizer.scorer import score_consistency, score_dept_proximity, compute_total_score
from seating_optimizer.models import Block, Team


def _make_blocks():
    return {
        "B0": Block("B0", 0, 1, 9),
        "B1": Block("B1", 0, 3, 12),
        "B2": Block("B2", 2, 0, 8),
    }


def test_score_consistency_all_same():
    da = {"t1": (1, 2), "t2": (1, 3)}
    ba = {("t1", 1): "B0", ("t1", 2): "B0", ("t2", 1): "B1", ("t2", 3): "B1"}
    assert score_consistency(da, ba) == 1.0


def test_score_consistency_none_same():
    da = {"t1": (1, 2)}
    ba = {("t1", 1): "B0", ("t1", 2): "B1"}
    assert score_consistency(da, ba) == 0.0


def test_score_consistency_partial():
    da = {"t1": (1, 2), "t2": (1, 3)}
    ba = {("t1", 1): "B0", ("t1", 2): "B0", ("t2", 1): "B0", ("t2", 3): "B1"}
    assert score_consistency(da, ba) == 0.5


def test_score_dept_proximity_same_block():
    teams_by_id = {
        "t1": Team("t1", "T1", "D1", 3),
        "t2": Team("t2", "T2", "D1", 3),
    }
    blocks_by_id = _make_blocks()
    dept_map = {"D1": [teams_by_id["t1"], teams_by_id["t2"]]}
    da = {"t1": (1, 2), "t2": (1, 2)}
    ba = {("t1", 1): "B0", ("t1", 2): "B0", ("t2", 1): "B0", ("t2", 2): "B0"}
    score = score_dept_proximity(da, ba, teams_by_id, blocks_by_id, dept_map)
    assert score == 1.0  # same block → distance 0


def test_score_dept_proximity_different_blocks():
    teams_by_id = {
        "t1": Team("t1", "T1", "D1", 3),
        "t2": Team("t2", "T2", "D1", 3),
    }
    blocks_by_id = _make_blocks()
    dept_map = {"D1": [teams_by_id["t1"], teams_by_id["t2"]]}
    da = {"t1": (1, 2), "t2": (1, 2)}
    # B0=(0,1), B1=(0,3) → manhattan distance = 2
    ba = {("t1", 1): "B0", ("t1", 2): "B0", ("t2", 1): "B1", ("t2", 2): "B1"}
    score = score_dept_proximity(da, ba, teams_by_id, blocks_by_id, dept_map)
    expected = 1.0 - 2 / 8  # = 0.75
    assert abs(score - expected) < 1e-9

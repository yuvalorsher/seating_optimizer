import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from seating_optimizer.scorer import score_compactness, score_consistency, compute_total_score
from seating_optimizer.models import GroupBlockAssignment


def _ba(group_id, day, block_id, count):
    return GroupBlockAssignment(group_id=group_id, day=day, block_id=block_id, count=count)


def test_score_compactness_all_single():
    da = {"g1": (1, 2), "g2": (1, 3)}
    bas = [
        _ba("g1", 1, "B0", 10), _ba("g1", 2, "B0", 10),
        _ba("g2", 1, "B1", 8),  _ba("g2", 3, "B1", 8),
    ]
    assert score_compactness(da, bas) == 1.0


def test_score_compactness_partial():
    da = {"g1": (1, 2)}
    bas = [
        _ba("g1", 1, "B0", 10),                        # single block
        _ba("g1", 2, "B0", 8), _ba("g1", 2, "B2", 2),  # split
    ]
    # Day 1: single (1/2), Day 2: split (0/2) → 1 out of 2
    assert score_compactness(da, bas) == 0.5


def test_score_compactness_all_split():
    da = {"g1": (1, 2)}
    bas = [
        _ba("g1", 1, "B0", 8), _ba("g1", 1, "B2", 2),
        _ba("g1", 2, "B0", 8), _ba("g1", 2, "B2", 2),
    ]
    assert score_compactness(da, bas) == 0.0


def test_score_consistency_all_same():
    da = {"g1": (1, 2), "g2": (1, 3)}
    bas = [
        _ba("g1", 1, "B0", 10), _ba("g1", 2, "B0", 10),
        _ba("g2", 1, "B1", 8),  _ba("g2", 3, "B1", 8),
    ]
    assert score_consistency(da, bas) == 1.0


def test_score_consistency_none_same():
    da = {"g1": (1, 2)}
    bas = [_ba("g1", 1, "B0", 10), _ba("g1", 2, "B1", 10)]
    assert score_consistency(da, bas) == 0.0


def test_score_consistency_partial():
    da = {"g1": (1, 2), "g2": (1, 3)}
    bas = [
        _ba("g1", 1, "B0", 10), _ba("g1", 2, "B0", 10),  # same → consistent
        _ba("g2", 1, "B0", 8),  _ba("g2", 3, "B1", 8),   # different → not consistent
    ]
    assert score_consistency(da, bas) == 0.5


def test_compute_total_score():
    da = {"g1": (1, 2)}
    bas = [_ba("g1", 1, "B0", 10), _ba("g1", 2, "B0", 10)]
    total, breakdown = compute_total_score(da, bas)
    assert breakdown["compactness"] == 1.0
    assert breakdown["consistency"] == 1.0
    assert abs(total - 1.0) < 1e-9

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from seating_optimizer.updater import SolutionUpdater


def test_updater_stub_raises():
    updater = SolutionUpdater()
    try:
        updater.update()
        assert False, "Should have raised NotImplementedError"
    except NotImplementedError:
        pass

import cv2
import numpy as np

import recognition_timing
from recognition_timing import UltimateTiming
from vision import Vision


def test_ultimate_interval_pauses_and_resumes(monkeypatch):
    intervals = iter((7, 14))

    def choose_interval(low, high):
        assert (low, high) == (7, 14)
        return next(intervals)

    monkeypatch.setattr(recognition_timing, 'uniform', choose_interval)
    timer = UltimateTiming()
    assert not timer.ready(0, active=True, can_click=True)
    assert not timer.ready(4, active=True, can_click=True)
    assert not timer.ready(100, active=False, can_click=True)
    assert not timer.ready(200, active=True, can_click=True)
    assert not timer.ready(202, active=True, can_click=True)
    assert not timer.ready(203, active=True, can_click=False)
    assert timer.ready(204, active=True, can_click=True)
    timer.clicked()
    assert not timer.ready(217, active=True, can_click=True)
    assert timer.ready(218, active=True, can_click=True)


def test_ultimate_needs_enemy_health_and_slot_six():
    detector = Vision.__new__(Vision)
    detector.frame = np.zeros((1000, 800, 3), dtype=np.uint8)
    detector.gray = cv2.cvtColor(detector.frame, cv2.COLOR_BGR2GRAY)
    badge = detector.skill_badge_templates()[-1][1]
    height, width = badge.shape
    detector.gray[840:840+height, 551:551+width] = badge

    assert detector.ultimate_target() is None
    detector.frame[347:355, 318:467] = (30, 30, 225)
    assert detector.ultimate_target() == (583, 871)
    detector.gray.fill(0)
    assert detector.ultimate_target() is None

import pytest
from window_sizing import covers_monitor,fit_position


def test_fullscreen_detected_on_any_monitor():
    assert covers_monitor((0,0,1920,1080),(0,0,1920,1080))
    assert covers_monitor((-1920,0,0,1080),(-1920,0,0,1080))
    assert not covers_monitor((50,50,850,1050),(0,0,1920,1080))


def test_position_clamped_to_work_area():
    assert fit_position((1800,900),(816,1039),(0,0,1920,1040))==(1104,1)
    assert fit_position((-1900,-50),(816,1039),(-1920,0,0,1040))==(-1900,0)


def test_small_monitor_reports_actual_reason():
    with pytest.raises(ValueError,match='작업 영역 1920×984'):
        fit_position((0,0),(816,1039),(0,0,1920,984))


def test_caption_and_client_fit_uploaded_1080p_layout():
    from window_sizing import fit_framed_position
    # User log: 1920×1080 monitor, 48px taskbar, 31px above client + 8px bottom frame.
    pos=fit_framed_position((1080,4),(816,1039),(0,0,1920,1032),(0,0,1920,1080),(8,31,8,8))
    assert pos==(1080,1)
    assert pos[1]+31+1000<=1032
    assert pos[1]+1039<=1080


def test_caption_is_not_removed_when_space_is_insufficient():
    from window_sizing import fit_framed_position
    with pytest.raises(ValueError,match='제목 표시줄을 숨기지 않고'):
        fit_framed_position((0,0),(816,1039),(0,0,1920,984),(0,0,1920,1024),(8,31,8,8))

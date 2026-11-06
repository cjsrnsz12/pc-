from capture_guard import CapturePause,within_desktop


def test_logged_125_percent_pc_sizing_and_offscreen_restore():
    bounds=(0,0,1920,1200)
    assert within_desktop((533,117,800,1000),bounds)
    assert not within_desktop((533,220,800,1000),bounds)
    assert within_desktop((533,117,800,1000),bounds)


def test_live_desktop_and_negative_monitor_coordinates():
    assert within_desktop((-1000,20,800,1000),(-1920,0,1920,1200))
    assert not within_desktop((-1000,20,800,1000),(0,0,1920,1200))
    assert not within_desktop((0,0,800,1000),(0,0,1920,900))
    assert within_desktop((0,0,800,1000),(0,0,1920,1200))


def test_multiple_pause_reasons_count_elapsed_only_once():
    pause=CapturePause()
    assert pause.hold('offscreen',10)
    assert not pause.hold('offscreen',11)
    assert pause.hold('inactive',15)
    assert pause.hold('offscreen',20)
    assert pause.resume(30)==20
    assert pause.resume(31) is None
    assert pause.hold('inactive',50)
    assert pause.resume(52)==2

import pytest
from mouse_sequence import deliver_click


def test_stationary_pointer_still_gets_hover_before_each_click():
    events=[]
    def send(phase):events.append(phase)
    def pause(delay):events.append(('wait',delay))
    assert deliver_click(send,lambda:True,pause)
    assert events==['move',('wait',.06),'down',('wait',.025),'up']
    events.clear()
    assert deliver_click(send,lambda:True,pause)
    assert events[0]=='move' and events[-1]=='up'


def test_foreground_loss_during_hover_cannot_press():
    events=[];active=iter([True,False])
    assert not deliver_click(events.append,lambda:next(active),lambda _:None)
    assert events==['move']


def test_inactive_window_does_not_move_or_click():
    events=[]
    assert not deliver_click(events.append,lambda:False,lambda _:None)
    assert not events


def test_failure_after_press_always_releases_mouse():
    events=[]
    def send(phase):
        events.append(phase)
        if phase=='down':raise OSError('injected failure')
    with pytest.raises(OSError):deliver_click(send,lambda:True,lambda _:None)
    assert events==['move','down','up']

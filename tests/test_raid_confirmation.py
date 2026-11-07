"""Exercise the application's actual start path without controlling a game."""
from types import SimpleNamespace
import threading
import pytest

class Variable:
    def __init__(self,value):self.value=value
    def get(self):return self.value
    def set(self,value):self.value=value

@pytest.fixture
def start_case(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'data'))
    import app as module
    calls=[]
    case=SimpleNamespace(running=False,sizing_busy=False,installing=False,closing=False,
        play_mode=Variable(module.PLAY_MODES[0]),content=Variable('레이드'),dungeon=Variable('카브락'),
        difficulty=Variable('입문'),status=Variable('대기'),root=None,stop_event=threading.Event(),worker=None,
        settings_path=tmp_path/'settings.json',settings={},
        refresh=lambda:calls.append('refresh'),selected=lambda:123,
        win=SimpleNamespace(require_control_permission=lambda hwnd:calls.append('permission'),rect=lambda hwnd:(0,0,800,1000)),
        collect_settings=lambda:{'content':'레이드','dungeon':'카브락','difficulty':'입문'},
        lock_controls=lambda running:calls.append(('lock',running)),log=lambda message:calls.append(('log',message)),
        run=lambda *args:None)
    class Worker:
        def __init__(self,**kwargs):self.kwargs=kwargs
        def start(self):calls.append('worker_started')
    monkeypatch.setattr(module.threading,'Thread',Worker)
    return module,case,calls

@pytest.mark.parametrize('content',['레이드','어비스'])
def test_start_runs_without_unfinished_confirmation(start_case,monkeypatch,content):
    module,case,calls=start_case;case.content.set(content)
    def unexpected(*args,**kw):raise AssertionError('Unexpected unfinished confirmation')
    monkeypatch.setattr(module.messagebox,'askyesno',unexpected)
    module.App.start(case)
    assert case.running and not case.stop_event.is_set()
    assert 'permission' in calls and 'worker_started' in calls and case.settings_path.exists()


@pytest.mark.parametrize('flag',['running','sizing_busy','installing','closing'])
def test_busy_or_closing_app_does_not_start_again(start_case,flag):
    module,case,calls=start_case;setattr(case,flag,True)
    module.App.start(case)
    assert 'refresh' not in calls and 'worker_started' not in calls


def test_abyss_party_mode_can_start_without_unfinished_raid_prompt(start_case,monkeypatch):
    module,case,calls=start_case;case.content.set('어비스');case.play_mode.set(module.PLAY_MODES[1])
    def unexpected(*args,**kw):raise AssertionError('Unexpected prompt for Abyss party')
    monkeypatch.setattr(module.messagebox,'askyesno',unexpected)
    monkeypatch.setattr(module.messagebox,'showinfo',unexpected)
    module.App.start(case)
    assert case.running and 'worker_started' in calls

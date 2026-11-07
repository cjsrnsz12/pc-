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
    case=SimpleNamespace(running=False,sizing_busy=False,installing=False,closing=False,raid_confirming=False,
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

@pytest.mark.parametrize('answer',[False,None])
def test_no_or_close_never_enters_game_preflight_or_starts_worker(start_case,monkeypatch,answer):
    module,case,calls=start_case;asked=[]
    monkeypatch.setattr(module.messagebox,'askyesno',lambda *args,**kw:asked.append((args,kw)) or answer)
    module.App.start(case)
    assert len(asked)==1 and asked[0][0][1]=='현재 미완성인 기능입니다.\n사용하시겠습니까?'
    assert asked[0][1]['default']==module.messagebox.NO
    assert not case.running and case.stop_event.is_set() and case.worker is None
    assert 'refresh' not in calls and not case.settings_path.exists()


def test_yes_runs_normal_preflight_and_starts_worker(start_case,monkeypatch):
    module,case,calls=start_case
    monkeypatch.setattr(module.messagebox,'askyesno',lambda *args,**kw:True)
    module.App.start(case)
    assert case.running and not case.raid_confirming and not case.stop_event.is_set()
    assert 'permission' in calls and 'worker_started' in calls and case.settings_path.exists()


def test_abyss_start_does_not_ask_raid_question(start_case,monkeypatch):
    module,case,calls=start_case;case.content.set('어비스')
    def unexpected(*args,**kw):raise AssertionError('Raid confirmation shown for Abyss')
    monkeypatch.setattr(module.messagebox,'askyesno',unexpected)
    module.App.start(case)
    assert case.running and 'worker_started' in calls


def test_nested_start_cannot_open_duplicate_confirmation(start_case,monkeypatch):
    module,case,calls=start_case;asked=[]
    def answer(*args,**kw):
        asked.append(1);module.App.start(case);return False
    monkeypatch.setattr(module.messagebox,'askyesno',answer)
    module.App.start(case)
    assert asked==[1] and not case.running and not case.raid_confirming

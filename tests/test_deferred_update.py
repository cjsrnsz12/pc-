"""Exercise the real event pump without Tk windows or network requests."""
import queue
from types import SimpleNamespace
import pytest

class Var:
    def __init__(self,value=''):self.value=value
    def set(self,value):self.value=value
    def get(self):return self.value

class Prompt:
    closed=False
    def __init__(self):self.results=[];self.errors=[];self.empty=0;self.shows=0;self.status=Var()
    def set_release(self,result):self.results.append(result)
    def set_check_error(self,error):self.errors.append(error)
    def set_no_release(self):self.empty+=1
    def show(self):self.shows+=1

@pytest.fixture
def case(monkeypatch,tmp_path):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    import app
    a=app.App.__new__(app.App)
    a.running=True;a.closing=False;a.installing=False
    a.pending_update=None;a.pending_installed_notice=None
    a.update_manual_requested=False;a.update_busy=True;a.latest_release=None
    a.seen_updates=set();a.update_notice=None;a.update_prompt=None
    a.update_text=Var();a.completed_count=Var('완료 7판');a.status=Var('전투중');a.detail=Var()
    a.events=queue.Queue();a.previous_keys=(False,False)
    a.root=SimpleNamespace(after=lambda *args:None)
    a.win=SimpleNamespace(keys=lambda:(False,False))
    a.lock_controls=lambda *args:None
    a.log=lambda *args:None
    made=[]
    def create(*args):
        p=Prompt();made.append(p);return p
    monkeypatch.setattr(app,'UpdatePrompt',create)
    return app,a,made

def release(version='v99.1.0',newer=True):return dict(version=version,is_new=newer)

def dispatch(a,kind,value):
    a.events.put((kind,value));a.pump()


def test_automatic_update_waits_for_worker_stop_and_shows_once(case):
    _,a,made=case;r=release()
    dispatch(a,'update',(r,None))
    assert not made and a.pending_update==(r,None,False)
    assert r['version'] not in a.seen_updates and a.latest_release==r
    # More captures/checks in the same run must not create another window.
    dispatch(a,'update',(r,None));assert not made
    import threading
    a.stop_event=threading.Event();a.stop()
    assert a.running and a.stop_event.is_set() and not made
    dispatch(a,'stopped',None)
    assert len(made)==1 and a.pending_update is None
    assert r['version'] in a.seen_updates and a.completed_count.get()=='완료 7판'
    dispatch(a,'update',(r,None));assert len(made)==1 and made[0].shows==0


def test_idle_update_is_still_shown_immediately(case):
    _,a,made=case;a.running=False
    dispatch(a,'update',(release(),None))
    assert len(made)==1 and a.pending_update is None


def test_later_failure_does_not_erase_pending_release(case):
    _,a,made=case;r=release()
    dispatch(a,'update',(r,None));dispatch(a,'update',(None,'offline'))
    assert a.pending_update==(r,None,False) and not made
    dispatch(a,'stopped',None);assert len(made)==1


def test_manual_error_is_deferred_until_stopped(case):
    _,a,made=case;a.update_manual_requested=True
    dispatch(a,'update',(None,'offline'));assert not made
    dispatch(a,'stopped',None)
    assert made[0].errors==['offline']


def test_last_detected_release_is_used_after_stop(case):
    _,a,made=case
    dispatch(a,'update',(release('v99.1.0'),None))
    dispatch(a,'update',(release('v99.2.0'),None))
    assert a.pending_update[0]['version']=='v99.2.0'
    dispatch(a,'stopped',None)
    assert len(made)==1 and 'v99.2.0' in a.seen_updates


def test_direct_window_or_install_requests_do_not_open_during_run(case,monkeypatch):
    app,a,made=case;r=release()
    monkeypatch.setattr(app,'UpdateNotice',lambda *args:pytest.fail('Notice opened while running'))
    a.show_update_prompt(r);a.show_update(r)
    assert not a.update_from_prompt(r)
    assert not made and a.pending_update==(r,None,True)


def test_manual_check_during_run_does_not_create_loading_popup(case):
    _,a,made=case;a.update_busy=True
    a.update_check(True)
    assert a.update_manual_requested and not made
    dispatch(a,'update',(release(newer=False),None));assert not made
    dispatch(a,'stopped',None);assert len(made)==1


def test_installed_version_notes_are_deferred_too(case,tmp_path):
    _,a,made=case;state=tmp_path/'notice.json'
    assert not a.show_installed_changes(state)
    assert a.pending_installed_notice==(state,) and not state.exists()
    shown=[];a.show_installed_changes=lambda path:shown.append(path)
    dispatch(a,'stopped',None);assert shown==[state]


def test_exit_does_not_show_pending_popup(case):
    _,a,made=case;dispatch(a,'update',(release(),None))
    a.closing=True;dispatch(a,'stopped',None)
    assert not made

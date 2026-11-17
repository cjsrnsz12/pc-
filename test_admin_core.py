import json,os,threading
from pathlib import Path
import pytest
from admin_core import AdminSession,Diagnostics,clean,dpapi
from players_sync import PlayerError
from test_players_sync import manager,until

KEY='a'*64
def cipher(data,decrypt=False):return data[3:] if decrypt else b'enc'+data
class Service:
    def __init__(self):self.calls=[];self.error=None;self.block=None;self.started=threading.Event()
    def service(self,body):
        self.calls.append(body);self.started.set()
        if self.block:self.block.wait(2)
        if self.error:raise self.error
        return dict(ok=True,reports=[],total=0,offset=0,report_id=body.get('report',{}).get('id'))
class Sync:
    def __init__(self):self.api=Service();self.cv=threading.RLock();self.run_id='run';self.ready=True
    def identity_body(self):return dict(member_id='id',token='b'*64) if self.ready else None

def test_admin_validates_before_saving_and_restores(tmp_path):
    s=Sync();p=tmp_path/'key';a=AdminSession(p,s,cipher);s.api.error=PlayerError('admin_required')
    with pytest.raises(PlayerError):a.request(key=KEY,offset=0,unread_only=True)
    assert not p.exists() and not a.key
    s.api.error=None;a.request(key=KEY,offset=0,unread_only=True)
    assert KEY.encode() not in p.read_bytes()
    assert AdminSession(p,s,cipher).key==KEY
    a.logout();assert not p.exists() and not a.key

def test_transient_failure_keeps_key_revocation_removes_it(tmp_path):
    s=Sync();a=AdminSession(tmp_path/'key',s,cipher);a.request(key=KEY,offset=0,unread_only=True)
    s.api.error=PlayerError()
    with pytest.raises(PlayerError):a.request(offset=0,unread_only=True)
    assert a.key==KEY and a.path.exists()
    s.api.error=PlayerError('admin_required')
    with pytest.raises(PlayerError):a.request(offset=0,unread_only=True)
    assert not a.key and not a.path.exists()

def test_late_auth_cannot_undo_logout(tmp_path):
    s=Sync();s.api.block=threading.Event();a=AdminSession(tmp_path/'key',s,cipher);errors=[]
    def work():
        try:a.request(key=KEY,offset=0,unread_only=True)
        except ValueError as e:errors.append(e)
    t=threading.Thread(target=work);t.start();assert s.api.started.wait(1);a.logout();s.api.block.set();t.join(2)
    assert errors and not a.key and not a.path.exists()

def test_save_failure_does_not_authenticate(tmp_path):
    s=Sync();a=AdminSession(tmp_path/'missing'/'key',s,lambda *_:(_ for _ in ()).throw(OSError('unavailable')))
    with pytest.raises(OSError):a.request(key=KEY,offset=0,unread_only=True)
    assert not a.key

def test_scrub_limits_and_credentials():
    raw='token=abc password=qwerty https://host/path user@example.com C:\\Users\\Person\\file '+KEY
    text=clean(raw)
    for value in ('abc','qwerty','https://','user@example.com','Person',KEY):assert value not in text
    assert len(clean('x'*5000))==4000

def test_outbox_requires_consent_deduplicates_and_survives_restart(tmp_path):
    s=Sync();d=Diagnostics(tmp_path/'reports',s,'1.1.48');d.close();d.thread.join(1)
    assert not d.report('failure','log','어비스','800x1000')
    d.consent(True);assert d.report('failure','\n'.join(map(str,range(40))),'어비스','800x1000')
    assert not d.report('failure','log','어비스','800x1000')
    report=d.state['pending'][0];assert len(report['logs'].splitlines())==30 and 'token' not in report
    other=Diagnostics(d.path,s,'1.1.48');other.close();other.thread.join(1)
    assert other.state==d.state
    other.consent(False);assert not other.state['pending'] and not other.state['seen']

def test_consent_off_during_request_never_restores_queue(tmp_path):
    s=Sync();s.api.block=threading.Event();d=Diagnostics(tmp_path/'reports',s,'1.1.48');d.consent(True);d.report('failure','log','어비스','800x1000')
    assert s.api.started.wait(1);d.consent(False);s.api.block.set();until(lambda:not d.state['pending']);d.close();d.thread.join(1)
    assert json.loads(d.path.read_text())==dict(consent=False,pending=[],seen=[])

def test_pc_device_selection_and_own_counter_preserved(tmp_path):
    s=manager(tmp_path);s.set_devices(6);s.set_nickname('냐르');until(lambda:s.registered)
    assert s.view()['used_devices']==7
    assert all(c['device_type']=='pc' and c['used_devices']==7 for c in s.api.calls)
    s.new_run('어비스');s.count(4);s.close();s.thread.join(1)
    other=manager(tmp_path);assert other.view()['used_devices']==7 and other.view()['devices_confirmed']
    assert other.lifetime_completed==4;other.close();other.thread.join(1)

@pytest.mark.skipif(os.name!='nt',reason='Windows DPAPI')
def test_native_windows_dpapi_restart(tmp_path):
    s=Sync();a=AdminSession(tmp_path/'admin',s);a.request(key=KEY,offset=0,unread_only=True)
    assert KEY.encode() not in a.path.read_bytes() and AdminSession(a.path,s).key==KEY
    encrypted=bytearray(dpapi(KEY.encode()));encrypted[-1]^=1
    with pytest.raises(OSError):dpapi(bytes(encrypted),True)
    a.logout();assert not AdminSession(a.path,s).key

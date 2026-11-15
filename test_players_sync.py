import copy,json,threading,time
import pytest
from players_sync import PlayerSync,PlayerError,nickname
class API:
 def __init__(self):self.calls=[];self.fail=False;self.block=None;self.started=threading.Event()
 def call(self,body):
  self.calls.append(copy.deepcopy(body));self.started.set()
  if self.block:self.block.wait(2)
  if self.fail:raise PlayerError()
  return dict(ok=True,protocol=2,players=[],offset=body['offset'],total=0,page_size=100)
def until(check):
 end=time.monotonic()+2
 while not check():
  if time.monotonic()>end:raise AssertionError('worker state timed out')
  time.sleep(.005)
def manager(tmp_path,api=None):return PlayerSync(tmp_path/'players.json','1.1.46',api=api or API(),interval=300)
def test_first_nickname_required_and_no_private_room_migration(tmp_path):
 (tmp_path/'shared_room.json').write_text(json.dumps({'member':{'nickname':'private name','token':'a'*64}}))
 api=API();s=manager(tmp_path,api);s.new_run('어비스');s.count(4);time.sleep(.02)
 assert not s.has_nickname() and not api.calls;s.close();s.thread.join(1)
def test_onboarding_registers_once_and_syncs_count(tmp_path):
 api=API();s=manager(tmp_path,api);s.set_nickname('냥이');until(lambda:len(api.calls)>1)
 assert api.calls[0]['op']=='players_register' and api.calls[0]['consent_version']==2
 s.new_run('레이드');s.count(29);until(lambda:any(c.get('completed')==29 for c in api.calls));s.count(2);assert s.completed==29
 s.stopped();until(lambda:api.calls[-1].get('running') is False and api.calls[-1].get('completed')==29)
 previous=s.run_id;s.new_run('어비스');assert s.completed==0 and s.run_id!=previous
 assert 'token' not in s.view();s.close();s.thread.join(1);assert not s.thread.is_alive();assert api.calls[-1]['present'] is False
 defunct=json.loads((tmp_path/'players.json').read_text());assert defunct['identity']['consent_version']==2

def test_restart_stopped_and_no_nickname_prompt(tmp_path):
 api=API();s=manager(tmp_path,api);s.set_nickname('재실행');until(lambda:s.registered);s.new_run('어비스');s.count(43);s.close();s.thread.join(1)
 api2=API();other=manager(tmp_path,api2);until(lambda:len(api2.calls)>1)
 assert other.has_nickname() and api2.calls[1]['completed']==43 and api2.calls[1]['running'] is False
 assert api2.calls[1]['seq']>api.calls[-1]['seq'];other.close();other.thread.join(1)

def test_network_failure_retries_same_identity_and_keeps_nickname(tmp_path):
 api=API();api.fail=True;s=manager(tmp_path,api);s.set_nickname('오프라인');until(lambda:bool(api.calls))
 identity=api.calls[0]['member_id'];assert s.has_nickname() and not s.connected
 api.fail=False;s.refresh();until(lambda:s.connected)
 assert api.calls[1]['member_id']==identity;s.close();s.thread.join(1)

def test_rename_during_request_ignores_stale_result(tmp_path):
 api=API();api.block=threading.Event();s=manager(tmp_path,api);s.set_nickname('이전');assert api.started.wait(1)
 s.set_nickname('새이름');api.block.set();until(lambda:s.registered and len(api.calls)>2)
 assert api.calls[1]['nickname']=='새이름' and api.calls[1]['member_id']==api.calls[0]['member_id'];s.close();s.thread.join(1)

@pytest.mark.parametrize('value',['','x'*21,'in\nvalid','x\x7fname'])
def test_bad_nicknames(value):
 with pytest.raises(ValueError):nickname(value)

def test_storage_failure_does_not_consent(tmp_path,monkeypatch):
 s=manager(tmp_path);monkeypatch.setattr(s,'_save',lambda:(_ for _ in ()).throw(OSError()))
 with pytest.raises(ValueError):s.set_nickname('공개안됨')
 assert not s.has_nickname();s.close();s.thread.join(1)

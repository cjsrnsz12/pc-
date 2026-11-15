import copy,json,threading,time
import pytest
from players_sync import PlayerSync,PlayerError,nickname
class API:
 def __init__(self):self.calls=[];self.fail=False;self.block=None;self.started=threading.Event()
 def call(self,body):
  self.calls.append(copy.deepcopy(body));self.started.set()
  if self.block:self.block.wait(2)
  if self.fail:raise PlayerError()
  return dict(ok=True,protocol=2,players=[],offset=body['offset'],total=0,page_size=100,self_lifetime_completed=body.get('lifetime_completed',0))
def until(check):
 end=time.monotonic()+2
 while not check():
  if time.monotonic()>end:raise AssertionError('worker state timed out')
  time.sleep(.005)
def manager(tmp_path,api=None):return PlayerSync(tmp_path/'players.json','1.1.47',api=api or API(),interval=300)
def test_first_nickname_required_and_no_private_room_migration(tmp_path):
 (tmp_path/'shared_room.json').write_text(json.dumps({'member':{'nickname':'private name','token':'a'*64}}))
 api=API();s=manager(tmp_path,api);s.new_run('어비스');s.count(4);time.sleep(.02)
 assert not s.has_nickname() and not api.calls;s.close();s.thread.join(1)
def test_onboarding_registers_once_and_syncs_count(tmp_path):
 api=API();s=manager(tmp_path,api);s.set_nickname('냥이');until(lambda:len(api.calls)>1)
 assert api.calls[0]['op']=='players_register' and api.calls[0]['consent_version']==2
 s.new_run('레이드');s.count(29);until(lambda:any(c.get('completed')==29 for c in api.calls));s.count(2);assert s.completed==29
 s.stopped();until(lambda:api.calls[-1].get('running') is False and api.calls[-1].get('completed')==29)
 previous=s.run_id;s.new_run('어비스');assert s.completed==0 and s.run_id!=previous and s.lifetime_completed==29
 assert 'token' not in s.view();s.close();s.thread.join(1);assert not s.thread.is_alive();assert api.calls[-1]['present'] is False
 defunct=json.loads((tmp_path/'players.json').read_text(encoding='utf-8'));assert defunct['identity']['consent_version']==2

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

def test_lifetime_survives_runs_restart_and_offline(tmp_path):
 api=API();api.fail=True;s=manager(tmp_path,api);s.set_nickname('누적')
 for content,count in [('어비스',12),('레이드',7),('어비스',4)]:
  s.new_run(content);s.count(count);s.count(count);s.count(count-1);s.stopped()
 assert s.lifetime_completed==23 and s.completed==4
 s.close();s.thread.join(1)
 restored_api=API();restored=manager(tmp_path,restored_api);until(lambda:restored.registered)
 assert restored.lifetime_completed==23 and not restored.running
 restored.new_run('레이드');restored.count(8);assert restored.lifetime_completed==31
 restored.close();restored.thread.join(1)

def test_migration_uses_retained_count_only(tmp_path):
 import uuid
 identity=dict(member_id=str(uuid.uuid4()),token='a'*64,nickname='이전',consent_version=2)
 (tmp_path/'players.json').write_text(json.dumps(dict(identity=identity,seq=20,completed=19,content='어비스',run_id=str(uuid.uuid4()))),encoding='utf-8')
 s=manager(tmp_path);until(lambda:s.registered)
 assert s.lifetime_completed==19;s.new_run('레이드');s.count(3);assert s.lifetime_completed==22
 s.close();s.thread.join(1)

def test_server_recovery_preserves_inflight_completions(tmp_path):
 class Recover(API):
  def call(self,body):
   result=super().call(body);result['self_lifetime_completed']=max(200,body['lifetime_completed']);return result
 api=Recover();api.block=threading.Event();s=manager(tmp_path,api);s.set_nickname('복구');assert api.started.wait(1)
 s.new_run('어비스');s.count(3);api.block.set();until(lambda:s.registered and s.lifetime_completed>=203)
 assert s.lifetime_completed==203
 s.refresh();until(lambda:len(api.calls)>=3);assert s.lifetime_completed==203
 s.new_run('레이드');s.count(5);assert s.lifetime_completed==208
 s.close();s.thread.join(1)

def test_large_lifetime_and_no_unbounded_double_count(tmp_path):
 s=manager(tmp_path);s.set_nickname('큰수');until(lambda:s.registered)
 for _ in range(3):s.new_run('어비스');s.count(1000000000);s.count(1000000000)
 assert s.lifetime_completed==3000000000
 s.close();s.thread.join(1)
 saved=json.loads((tmp_path/'players.json').read_text(encoding='utf-8'));assert saved['lifetime_completed']==3000000000

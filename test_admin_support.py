import copy,json,sys,threading,time,uuid
import pytest
from admin_auth import AdminSession,CredentialStore,AdminAPI,_dpapi
from diagnostics_sync import Diagnostics,clean
from players_sync import PlayerSync,PlayerError
from test_players_sync import API,until

class Store:
 def __init__(self):self.value='';self.writes=0
 def load(self):return self.value
 def save(self,key):self.value=key;self.writes+=1;return True
 def clear(self):self.value='';return True

def test_remember_restart_logout_and_stale_response():
 store=Store();session=AdminSession(store);assert not session.restore();key='a'*64;session.begin(key);request=session.current();assert not store.value;assert session.accepted(request);assert session.accepted(request) and store.writes==1
 session.close();assert store.value==key and not session.key;restored=AdminSession(store);assert restored.restore();restored.rejected(restored.current(),'unavailable');assert store.value==key;restored.rejected(restored.current(),'unauthorized');assert store.value==key
 attempt=restored.current();restored.logout();assert not restored.accepted(attempt) and not store.value;restored.begin(key);restored.accepted(restored.current());restored.rejected(restored.current(),'admin_required');assert not store.value

def test_credential_store_never_falls_back_to_plaintext(tmp_path):
 path=tmp_path/'credential.json';key='a'*64
 protect=lambda data:bytes(b^0xa5 for b in data)
 store=CredentialStore(path,protect,protect);assert store.save(key);assert key not in path.read_text();assert store.load()==key
 def broken(data):raise OSError()
 other=CredentialStore(path,broken,broken);assert other.load()=='' and path.exists();assert not other.save(key);assert key not in path.read_text();assert store.clear() and not path.exists()

@pytest.mark.skipif(sys.platform!='win32',reason='real Windows DPAPI')
def test_native_windows_dpapi_roundtrip(tmp_path):
 path=tmp_path/'admin.json';key='a'*64;store=CredentialStore(path);assert store.save(key);assert key not in path.read_text();assert CredentialStore(path).load()==key
 encrypted=_dpapi(key.encode());assert key.encode() not in encrypted and _dpapi(encrypted,True)==key.encode();assert store.clear()

def test_multiple_device_choices_and_group_total_is_not_local_count(tmp_path):
 class GroupAPI(API):
  def call(self,body):
   result=super().call(body);result['players']=[dict(id=body['member_id'],nickname='냥이',platform='pc',device_type='pc',device_types=['pc','tablet'],status='running',content='',contents=['어비스','레이드'],completed=10,lifetime_completed=500)];result['total']=1;return result
 api=GroupAPI();sync=PlayerSync(tmp_path/'players.json','1.1.48',api=api,interval=300)
 try:
  sync.set_profile('냥이',6);until(lambda:sync.connected);assert sync.view()['used_devices']==7 and not sync.needs_devices();assert sync.lifetime_completed==0 and sync.view()['players'][0]['lifetime_completed']==500
  sync.new_run('어비스');sync.count(2);sync.new_run('레이드');sync.count(3);sync.count(3);assert sync.lifetime_completed==5
  until(lambda:any(c.get('lifetime_completed')==5 for c in api.calls));assert all(c.get('device_type')=='pc' and c.get('used_devices')==7 for c in api.calls);assert 'token' not in sync.view()
 finally:sync.close();sync.thread.join(1)

def test_opt_in_reports_redaction_retry_queue_and_opt_out(tmp_path):
 sync=PlayerSync(tmp_path/'players.json','1.1.48',api=API(),interval=300);sync.set_nickname('냥이');sync.new_run('어비스');path=tmp_path/'diagnostics.json';sender=Diagnostics(path,sync,'1.1.48',start=False)
 try:
  assert not sender.record('오류','log','1600x2560','어비스');sender.set_enabled(True)
  logs='\n'.join(f'line {i}' for i in range(40))+'\npassword=private-value {"admin_key":"shortSecret"} Bearer abcdef.123 test@example.com /home/alice/private'
  assert sender.record('터치 오류',logs,'1600x2560','어비스');assert not sender.record('터치 오류',logs,'1600x2560','어비스');report=sender.pending[0]
  for value in ['private-value','shortSecret','abcdef.123','test@example.com','alice']:assert value not in report['logs']
  assert len(report['logs'].splitlines())==30 and report['device_type']=='pc' and not any(k in report for k in ('image','screenshot','token'))
  restored=Diagnostics(path,sync,'1.1.48',start=False);assert restored.consent and len(restored.pending)==1
  for i in range(19):sync.new_run('어비스');assert restored.record('오류','log','0x0','어비스')
  assert len(restored.pending)==20;sync.new_run('어비스');assert not restored.record('over limit','log','0x0','어비스');restored.set_enabled(False);assert not restored.pending and not Diagnostics(path,sync,'1.1.48',start=False).consent
 finally:sync.close();sync.thread.join(1)

def test_admin_api_checks_identity_and_metadata(tmp_path):
 sync=PlayerSync(tmp_path/'players.json','1.1.48',api=API(),interval=300);sync.set_nickname('냥이');report_id=str(uuid.uuid4())
 class Service:
  def __init__(self):self.body=None;self.result=dict(ok=True,total=1,offset=0,reports=[dict(id=report_id,device_type='tablet')])
  def service(self,body):self.body=copy.deepcopy(body);return copy.deepcopy(self.result)
 service=Service();api=AdminAPI(sync,service)
 try:
  with pytest.raises(ValueError):api.call('admin_list_errors','nickname')
  assert service.body is None;assert api.call('admin_list_errors','a'*64)['total']==1;assert service.body['member_id']==sync.identity['member_id'];service.result['reports'][0]['logs']='must not be in list'
  with pytest.raises(PlayerError):api.call('admin_list_errors','a'*64)
 finally:sync.close();sync.thread.join(1)

def test_redaction_and_report_size():
 assert clean('가'*10000,4000)=='가'*4000
 assert 'abcdef' not in clean('token=abcdef',100)

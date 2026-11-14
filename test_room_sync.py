import copy
import json
import threading
import time
from pathlib import Path
import pytest
from room_sync import RoomSync,RoomAPI,RoomError,normalize_code,nickname

class API:
    def __init__(self):self.calls=[];self.fail=False;self.block=None;self.started=threading.Event()
    def call(self,body):
        self.calls.append(copy.deepcopy(body));self.started.set()
        if self.block:self.block.wait(2)
        if self.fail:raise RoomError()
        if body['op']=='leave':return {'ok':True}
        return {'ok':True,'protocol':1,'room_code':'ABCDEF0123456789ABCD','members':[]}

def until(predicate):
    end=time.monotonic()+2
    while not predicate():
        if time.monotonic()>end:raise AssertionError('worker did not reach expected state')
        time.sleep(.005)

def manager(tmp_path,api=None):return RoomSync(tmp_path/'room.json','1.1.45',api=api or API(),interval=300)

def test_opt_in(tmp_path):
    api=API();sync=manager(tmp_path,api);sync.new_run('어비스');sync.count(9);sync.stopped();time.sleep(.02)
    assert api.calls==[];assert not (tmp_path/'room.json').exists();sync.close();sync.thread.join(1)

def test_join_sync_count_stop_new_run(tmp_path):
    api=API();sync=manager(tmp_path,api);sync.join('고양이');until(lambda:sync.view()['joined'] and len(api.calls)>=2)
    assert api.calls[0]['platform']=='pc';assert api.calls[0]['op']=='create'
    sync.new_run('레이드');until(lambda:any(c.get('running') is True for c in api.calls));run=sync.run_id
    sync.count(12);until(lambda:any(c.get('completed')==12 for c in api.calls));sync.count(3);assert sync.completed==12
    sync.stopped();until(lambda:api.calls[-1].get('running') is False and api.calls[-1].get('completed')==12)
    sync.new_run('어비스');assert sync.run_id!=run;assert sync.completed==0
    sync.close();sync.thread.join(1);assert not sync.thread.is_alive()

def test_retry_is_idempotent(tmp_path):
    api=API();api.fail=True;sync=manager(tmp_path,api);sync.join('재시도');until(lambda:not sync.busy)
    credentials=api.calls[0];assert not sync.view()['joined'];api.fail=False;sync.join('재시도');until(lambda:sync.view()['joined'])
    assert credentials['member_id']==api.calls[1]['member_id'];assert credentials['token']==api.calls[1]['token'];sync.close();sync.thread.join(1)

def test_restart_reports_stopped_and_preserves_count(tmp_path):
    api=API();sync=manager(tmp_path,api);sync.join('보관');until(lambda:sync.view()['joined']);sync.new_run('어비스');sync.count(48);sync.close();sync.thread.join(1)
    before=sync.seq;api2=API();restored=manager(tmp_path,api2);until(lambda:bool(api2.calls))
    assert api2.calls[0]['running'] is False;assert api2.calls[0]['completed']==48;assert api2.calls[0]['seq']>before
    restored.close();restored.thread.join(1)

def test_leave_during_inflight_cannot_restore_membership(tmp_path):
    api=API();sync=manager(tmp_path,api);sync.join('나가기');until(lambda:sync.view()['joined'] and len(api.calls)>1)
    api.block=threading.Event();api.started.clear();sync.refresh();assert api.started.wait(1)
    sync.leave();assert not sync.view()['joined'];api.block.set();until(lambda:any(c['op']=='leave' for c in api.calls))
    assert not sync.view()['joined'];assert sync.view()['members']==[]
    assert json.loads((tmp_path/'room.json').read_text())['member'] is None;sync.close();sync.thread.join(1)

def test_disconnect_keeps_last_confirmed_data_unconfirmed(tmp_path):
    api=API();sync=manager(tmp_path,api);sync.join('연결');until(lambda:sync.view()['connected']);api.fail=True;sync.refresh();until(lambda:not sync.view()['connected'])
    assert sync.view()['joined'];assert '연결' in sync.view()['message'];sync.close();sync.thread.join(1)

@pytest.mark.parametrize('value',['','a'*21,'a\nname','a\x7fname'])
def test_invalid_nickname(value):
    with pytest.raises(ValueError):nickname(value)

def test_code_and_unicode():
    assert normalize_code('abcd-ef01-2345-6789-abcd')=='ABCDEF0123456789ABCD'
    assert nickname(' 🐱고양이 ')=='🐱고양이'
    with pytest.raises(ValueError):normalize_code('abcd')

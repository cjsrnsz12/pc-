"""Opt-in room presence. Only this worker performs network I/O; no game commands."""
import copy
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
import uuid
from room_config import ENDPOINT, PUBLISHABLE_KEY

MESSAGES={'invalid_request':'입력 내용을 확인해 주세요.','unauthorized':'방 참여 정보가 만료되었습니다. 나간 뒤 다시 참여해 주세요.', 'room_not_found':'방 코드를 확인해 주세요.','room_full':'이 방은 참여 인원이 가득 찼습니다.','rate_limit':'요청이 많습니다. 잠시 후 다시 시도해 주세요.','room_capacity':'잠시 후 새 방을 만들어 주세요.'}
class RoomError(Exception):
    def __init__(self,code='unavailable'):
        self.code=code
        super().__init__(MESSAGES.get(code,'공유 서버에 연결할 수 없습니다. 자동으로 다시 확인합니다.'))

def normalize_code(value):
    value=re.sub(r'[ -]','',value.strip()).upper()
    if not re.fullmatch(r'[A-F0-9]{20}',value):raise ValueError('방 코드 20자리를 확인해 주세요.')
    return value

def nickname(value):
    value=value.strip()
    if not 1<=len(value)<=20 or any(ord(c)<32 or 127<=ord(c)<=159 for c in value):raise ValueError('닉네임을 1~20자로 입력해 주세요.')
    return value

class RoomAPI:
    def __init__(self,endpoint=ENDPOINT,key=PUBLISHABLE_KEY):self.endpoint=endpoint;self.key=key
    def call(self,body):
        request=urllib.request.Request(self.endpoint,json.dumps(body,ensure_ascii=False).encode(),{'Content-Type':'application/json','apikey':self.key},method='POST')
        try:
            with urllib.request.urlopen(request,timeout=7) as response:raw=response.read(65537)
        except urllib.error.HTTPError as error:
            try:code=json.loads(error.read(65537)).get('error','unavailable')
            except (ValueError,OSError):code='unavailable'
            raise RoomError(code) from None
        except (OSError,ValueError):raise RoomError() from None
        try:
            if len(raw)>65536:raise ValueError()
            result=json.loads(raw)
            if not isinstance(result,dict) or result.get('ok') is not True:raise RoomError(result.get('error','unavailable') if isinstance(result,dict) else 'unavailable')
            if body['op']=='leave':return result
            if result.get('protocol')!=1:raise ValueError()
            normalize_code(result['room_code'])
            members=result['members']
            if not isinstance(members,list) or len(members)>50:raise ValueError()
            for m in members:
                uuid.UUID(m['id']);nickname(m['nickname'])
                if m['platform'] not in ('pc','mobile') or m['status'] not in ('running','stopped','offline') or m['content'] not in ('','어비스','레이드'):raise ValueError()
                if type(m['completed']) is not int or not 0<=m['completed']<=1000000000:raise ValueError()
            return result
        except (ValueError,KeyError,TypeError):raise RoomError() from None

class RoomSync:
    def __init__(self,path,version,notify=lambda value:None,api=None,interval=15):
        self.path=Path(path);self.version=version;self.notify=notify;self.api=api or RoomAPI();self.interval=interval
        self.cv=threading.Condition(threading.RLock());self.closed=False;self.busy=False;self.generation=0;self.job=None;self.dirty=False
        self.member=None;self.pending=None;self.seq=0;self.running=False;self.completed=0;self.content='';self.run_id='';self.members=[];self.message='방에 참여하면 현황이 공유됩니다.';self.connected=False
        try:
            saved=json.loads(self.path.read_text(encoding='utf-8'))
            candidate=saved.get('member');pending=saved.get('pending')
            for item in (candidate,pending):
                if item:
                    uuid.UUID(item['member_id'])
                    if not re.fullmatch('[a-f0-9]{64}',item['token']):raise ValueError()
                    nickname(item['nickname'])
                    if item.get('room_code'):normalize_code(item['room_code'])
            self.member=candidate;self.pending=pending;self.seq=max(0,int(saved.get('seq',0)))
            self.completed=max(0,min(1000000000,int(saved.get('completed',0))));self.content=saved.get('content','');self.run_id=str(saved.get('run_id',''))
            if self.content not in ('','어비스','레이드') or not re.fullmatch('[a-fA-F0-9-]{0,36}',self.run_id):raise ValueError()
            if self.member:self.message='연결 확인 중';self.dirty=True
        except (OSError,ValueError,KeyError,TypeError):self.member=None;self.pending=None;self.seq=0;self.completed=0;self.content='';self.run_id=''
        self.thread=threading.Thread(target=self._loop,name='NyacroRoomSync',daemon=True);self.thread.start()
    def _save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        tmp=self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(dict(member=self.member,pending=self.pending,seq=self.seq,completed=self.completed,content=self.content,run_id=self.run_id),ensure_ascii=False),encoding='utf-8')
        try:os.chmod(tmp,0o600)
        except OSError:pass
        os.replace(tmp,self.path)
    def view(self):
        with self.cv:return copy.deepcopy(dict(joined=bool(self.member),busy=self.busy,room_code=self.member.get('room_code','') if self.member else '',member_id=self.member.get('member_id','') if self.member else '',nickname=(self.member or self.pending or {}).get('nickname',''),members=self.members,message=self.message,connected=self.connected))
    def _emit(self):
        try:self.notify(self.view())
        except Exception:pass
    def join(self,name,code=None):
        name=nickname(name);code=normalize_code(code) if code is not None else None
        with self.cv:
            if self.closed or self.busy or self.member:return
            previous=self.pending
            self.pending=previous if previous and previous['nickname']==name and previous.get('room_code')==code else dict(member_id=str(uuid.uuid4()),token=secrets.token_hex(32),nickname=name,room_code=code)
            try:self._save()
            except OSError:self.pending=previous;raise ValueError('방 참여 정보를 저장할 수 없습니다.') from None
            self.busy=True;self.job=('join',copy.deepcopy(self.pending));self.message='방 연결 중…';self.cv.notify_all()
        self._emit()
    def leave(self):
        with self.cv:
            if self.busy:return
            old=self.member;old_pending=self.pending;self.member=None;self.pending=None
            try:self._save()
            except OSError:
                self.member=old;self.pending=old_pending;self.message='저장 실패 · 다시 나가기를 눌러 주세요.';return
            self.members=[];self.connected=False;self.generation+=1;self.message='방에서 나왔습니다.'
            if old:self.job=('leave',old);self.busy=True;self.cv.notify_all()
        self._emit()
    def new_run(self,content):
        with self.cv:self.run_id=str(uuid.uuid4());self.completed=0;self.content=content;self.running=True;self._changed()
    def count(self,value):
        with self.cv:
            if self.running:self.completed=max(self.completed,min(1000000000,max(0,int(value))));self._changed()
    def stopped(self):
        with self.cv:self.running=False;self._changed()
    def _changed(self):
        if self.member:
            try:self._save()
            except OSError:pass
            self.dirty=True;self.cv.notify_all()
    def refresh(self):
        with self.cv:self.dirty=True;self.cv.notify_all()
    def close(self):
        self.stopped()
        # Allow the daemon one bounded final sync; exit never waits for the server.
        with self.cv:self.closed=True;self.cv.notify_all()
    def _loop(self):
        due=0
        while True:
            with self.cv:
                now=time.monotonic()
                if not self.job and (not self.member or (not self.dirty and now<due)):
                    if self.closed:return
                    self.cv.wait(max(.05,due-now) if self.member else None);continue
                generation=self.generation
                if self.job:kind,credentials=self.job;self.job=None
                else:
                    kind='sync';credentials=copy.deepcopy(self.member);self.seq+=1;self.dirty=False
                    try:self._save()
                    except OSError:
                        self.message='참여 정보 저장 실패 · 다시 연결해 주세요.';self.connected=False;self.dirty=False;due=now+self.interval
                        if self.closed:return
                        continue
                body={k:credentials[k] for k in ('member_id','token')}
                if kind=='join':
                    body.update(op='join' if credentials.get('room_code') else 'create',nickname=credentials['nickname'],platform='pc',app_version=self.version)
                    if credentials.get('room_code'):body['room_code']=credentials['room_code']
                elif kind=='sync':body.update(op='sync',seq=self.seq,running=self.running,completed=self.completed,content=self.content,run_id=self.run_id)
                else:body['op']='leave'
            try:
                result=self.api.call(body)
                with self.cv:
                    if generation!=self.generation:continue
                    if kind=='join':
                        credentials['room_code']=result['room_code'];self.member=credentials;self.pending=None;self.dirty=True
                        try:self._save()
                        except OSError:
                            self.member=None;self.pending=credentials;self.message='참여 정보 저장 실패 · 다시 시도해 주세요.';self.connected=False;continue
                    if kind!='leave':self.members=result['members'];self.connected=True;self.message='연결됨 · 15초마다 갱신'
            except RoomError as error:
                with self.cv:
                    if generation==self.generation:self.connected=False;self.message=str(error)
            except Exception:
                with self.cv:self.connected=False;self.message='방 연결을 다시 확인해 주세요.'
            finally:
                with self.cv:
                    self.busy=False;due=time.monotonic()+self.interval
                    if self.closed and not self.dirty:return
                self._emit()

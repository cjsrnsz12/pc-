"""Public player presence after explicit nickname setup; no game control."""
import copy,json,os,re,secrets,threading,time,uuid,urllib.request,urllib.error
from pathlib import Path
from room_config import ENDPOINT,PUBLISHABLE_KEY

class PlayerError(Exception):
    def __init__(self,code='unavailable'):
        self.code=code
        super().__init__({'invalid_request':'입력 내용을 확인해 주세요.','unauthorized':'플레이어 정보를 다시 연결하고 있습니다.','rate_limit':'요청이 많습니다. 잠시 후 다시 확인합니다.'}.get(code,'플레이어 목록에 연결할 수 없습니다. 자동으로 다시 확인합니다.'))

def nickname(value):
    value=value.strip()
    if not 1<=len(value)<=20 or any(ord(c)<32 or 127<=ord(c)<=159 for c in value):raise ValueError('닉네임을 1~20자로 입력해 주세요.')
    return value

class PlayerAPI:
    def __init__(self,endpoint=ENDPOINT,key=PUBLISHABLE_KEY):self.endpoint=endpoint;self.key=key
    def call(self,body):
        req=urllib.request.Request(self.endpoint,json.dumps(body,ensure_ascii=False).encode(),{'Content-Type':'application/json','apikey':self.key},method='POST')
        try:
            with urllib.request.urlopen(req,timeout=7) as response:raw=response.read(131073)
        except urllib.error.HTTPError as error:
            try:code=json.loads(error.read(8192)).get('error','unavailable')
            except (ValueError,OSError):code='unavailable'
            raise PlayerError(code) from None
        except (OSError,ValueError):raise PlayerError() from None
        try:
            if len(raw)>131072:raise ValueError()
            result=json.loads(raw)
            if not isinstance(result,dict) or result.get('ok') is not True:raise PlayerError()
            if body['op']=='players_remove':return result
            if result.get('protocol')!=2 or result.get('page_size')!=100:raise ValueError()
            if type(result['total']) is not int or not 0<=result['total']<=10000 or type(result['offset']) is not int or not 0<=result['offset']<=10000:raise ValueError()
            rows=result['players']
            if not isinstance(rows,list) or len(rows)>100:raise ValueError()
            for m in rows:
                uuid.UUID(m['id']);nickname(m['nickname'])
                if m['platform'] not in ('mobile','pc') or m['status'] not in ('running','stopped') or m['content'] not in ('','어비스','레이드'):raise ValueError()
                if type(m['completed']) is not int or not 0<=m['completed']<=1000000000:raise ValueError()
            return result
        except (ValueError,KeyError,TypeError):raise PlayerError() from None

class PlayerSync:
    def __init__(self,path,version,api=None,interval=15):
        self.path=Path(path);self.version=version;self.api=api or PlayerAPI();self.interval=interval;self.cv=threading.Condition(threading.RLock())
        self.identity=None;self.seq=0;self.completed=0;self.content='';self.run_id='';self.running=False;self.present=True;self.closed=False
        self.registered=False;self.revision=0;self.dirty=False;self.players=[];self.total=0;self.offset=0;self.connected=False;self.message='닉네임을 설정해 주세요.'
        try:
            saved=json.loads(self.path.read_text(encoding='utf-8'));item=saved['identity']
            uuid.UUID(item['member_id']);nickname(item['nickname'])
            if item.get('consent_version')!=2 or not re.fullmatch('[a-f0-9]{64}',item['token']):raise ValueError()
            self.identity=item;self.seq=max(0,min(8999999999999999,int(saved.get('seq',0))));self.completed=max(0,min(1000000000,int(saved.get('completed',0))));self.content=saved.get('content','');self.run_id=saved.get('run_id','')
            if self.content not in ('','어비스','레이드') or not re.fullmatch('[a-fA-F0-9-]{0,36}',self.run_id):raise ValueError()
            self.message='플레이어 목록 연결 중';self.dirty=True
        except (OSError,ValueError,KeyError,TypeError):self.identity=None;self.seq=0;self.completed=0;self.content='';self.run_id=''
        self.thread=threading.Thread(target=self._loop,name='NyacroPlayers',daemon=True);self.thread.start()
    def has_nickname(self):
        with self.cv:return bool(self.identity)
    def _save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True);tmp=self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(dict(identity=self.identity,seq=self.seq,completed=self.completed,content=self.content,run_id=self.run_id),ensure_ascii=False),encoding='utf-8')
        try:os.chmod(tmp,0o600)
        except OSError:pass
        os.replace(tmp,self.path)
    def set_nickname(self,value):
        name=nickname(value)
        with self.cv:
            if self.closed:return
            old=copy.deepcopy(self.identity)
            self.identity=dict(self.identity,nickname=name) if self.identity else dict(member_id=str(uuid.uuid4()),token=secrets.token_hex(32),nickname=name,consent_version=2)
            try:self._save()
            except OSError:self.identity=old;raise ValueError('닉네임을 저장할 수 없습니다.') from None
            self.revision+=1;self.registered=False;self.connected=False;self.message='플레이어 목록 연결 중';self.dirty=True;self.cv.notify_all()
    def view(self):
        with self.cv:return copy.deepcopy(dict(ready=bool(self.identity),nickname=(self.identity or {}).get('nickname',''),member_id=(self.identity or {}).get('member_id',''),players=self.players,total=self.total,offset=self.offset,connected=self.connected,message=self.message))
    def new_run(self,content):
        with self.cv:self.running=True;self.completed=0;self.content=content;self.run_id=str(uuid.uuid4());self._changed()
    def count(self,value):
        with self.cv:
            if self.running:self.completed=max(self.completed,min(1000000000,max(0,int(value))));self._changed()
    def stopped(self):
        with self.cv:self.running=False;self._changed()
    def _changed(self):
        if self.identity:
            try:self._save()
            except OSError:pass
            self.dirty=True;self.cv.notify_all()
    def page(self,offset):
        with self.cv:self.offset=max(0,min(10000,int(offset)//100*100));self.dirty=True;self.cv.notify_all()
    def refresh(self):
        with self.cv:self.dirty=True;self.cv.notify_all()
    def close(self):
        with self.cv:self.running=False;self.present=False;self.closed=True;self._changed();self.cv.notify_all()
    def _loop(self):
        due=0
        while True:
            with self.cv:
                now=time.monotonic()
                if not self.identity or not self.dirty and now<due:
                    if self.closed:return
                    self.cv.wait(max(.05,due-now) if self.identity else None);continue
                if self.closed and not self.registered:return
                revision=self.revision;credentials=copy.deepcopy(self.identity);register=not self.registered;self.dirty=False
                body={k:credentials[k] for k in ('member_id','token')};body['offset']=self.offset
                if register:body.update(op='players_register',nickname=credentials['nickname'],platform='pc',app_version=self.version,consent_version=2)
                else:
                    self.seq+=1
                    try:self._save()
                    except OSError:
                        self.connected=False;self.message='플레이어 정보 저장 실패 · 다시 확인합니다.';due=now+self.interval
                        if self.closed:return
                        continue
                    body.update(op='players_sync',seq=self.seq,running=self.running,present=self.present,completed=self.completed,content=self.content,run_id=self.run_id)
            try:
                result=self.api.call(body)
                with self.cv:
                    if revision!=self.revision:continue
                    if register:self.registered=True;self.dirty=True
                    if result['offset']==self.offset:
                        self.players=result['players'];self.total=result['total'];self.connected=True;self.message='사용중인 플레이어 '+str(self.total)+'명 · 15초마다 갱신'
                        if self.offset and self.offset>=self.total:self.offset=max(0,(max(1,self.total)-1)//100*100);self.dirty=True
            except PlayerError as error:
                with self.cv:
                    if revision==self.revision:
                        self.connected=False;self.message=str(error)
                        if error.code=='unauthorized':self.registered=False
            except Exception:
                with self.cv:self.connected=False;self.message='플레이어 목록을 다시 확인합니다.'
            finally:
                with self.cv:
                    due=time.monotonic()+self.interval
                    if self.closed and not self.dirty:return

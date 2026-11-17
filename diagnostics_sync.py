"""Opt-in, bounded text-only error-stop reports; independent of game input."""
import copy,hashlib,json,os,platform,re,threading,time,uuid
from pathlib import Path
from players_sync import PlayerAPI,PlayerError

def clean(value,limit):
    value=str(value or '')
    for pattern,replacement in [(r'(?i)(bearer\s+)[A-Za-z0-9._~-]+',r'\1[가림]'),(r'''(?i)(token|password|passwd|secret|api[_-]?key|admin[_-]?key)["']?\s*[=:]\s*["']?[^\s,;"'}]+''',r'\1=[가림]'),(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}','[이메일 가림]'),(r'(?i)https?://[^\s]+','[주소 가림]'),(r'(?i)[a-f0-9]{32,}','[인증값 가림]'),(r'(?i)(?:[A-Z]:\\Users\\|/Users/|/home/)[^\s]+','[경로 가림]')]:value=re.sub(pattern,replacement,value)
    return ''.join(c for c in value if c in '\n\t' or ord(c)>=32 and not 127<=ord(c)<=159)[-limit:]

class Diagnostics:
    def __init__(self,path,sync,version,api=None,start=True):
        self.path=Path(path);self.sync=sync;self.version=version;self.api=api or PlayerAPI();self.cv=threading.Condition();self.consent=False;self.pending=[];self.seen=[];self.closed=False;self.status='오류 기록 전송 꺼짐'
        try:
            if self.path.stat().st_size>400000:raise ValueError()
            saved=json.loads(self.path.read_text('utf-8'));self.consent=saved.get('consent') is True
            if self.consent:
                for row in saved.get('pending',[])[:20]:
                    uuid.UUID(row['id'])
                    if len(json.dumps(row))<30000:self.pending.append(row)
                self.seen=[x for x in saved.get('seen',[])[:60] if isinstance(x,str) and re.fullmatch('[a-f0-9]{64}',x)];self.status='오류로 중지하면 관리자에게 기록을 보냅니다.'
        except (OSError,ValueError,KeyError,TypeError):self.consent=False;self.pending=[];self.seen=[]
        if start:threading.Thread(target=self._loop,name='NyacroDiagnostics',daemon=True).start()
    def enabled(self):
        with self.cv:return self.consent
    def _save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True);tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(dict(consent=self.consent,pending=self.pending,seen=self.seen),ensure_ascii=False),'utf-8');os.chmod(tmp,0o600);os.replace(tmp,self.path)
    def set_enabled(self,enabled):
        with self.cv:
            self.consent=bool(enabled)
            if not enabled:self.pending=[];self.seen=[]
            self.status='오류로 중지하면 관리자에게 기록을 보냅니다.' if enabled else '오류 기록 전송 꺼짐'
            try:self._save()
            except OSError:self.status='오류 전송 설정 저장을 다시 확인해 주세요.'
            self.cv.notify_all()
    def record(self,reason,logs,screen,content):
        with self.cv:
            if not self.consent or len(self.pending)>=20:return False
            with self.sync.cv:run=self.sync.run_id
            reason=clean(reason,240);fingerprint=hashlib.sha256((run+'\n'+reason).encode()).hexdigest()
            if fingerprint in self.seen:return False
            report=dict(id=str(uuid.uuid4()),occurred_at=int(time.time()*1000),device_type='pc',app_version=self.version,device_model=clean(platform.system()+' '+platform.release(),80),screen=screen if re.fullmatch('[0-9]{1,5}x[0-9]{1,5}',screen) else '0x0',content=content,stop_reason=reason or '오류로 중지',logs=clean('\n'.join(clean(logs,12000).splitlines()[-30:]),4000))
            self.pending.append(report);self.seen=(self.seen+[fingerprint])[-60:]
            try:self._save()
            except OSError:self.status='오류 기록 저장 확인 대기'
            else:self.status='오류 기록 전송 대기';self.cv.notify_all()
            return True
    def close(self):
        with self.cv:self.closed=True;self.cv.notify_all()
    def _loop(self):
        due=0
        while True:
            with self.cv:
                if self.closed:return
                if not self.consent or not self.pending or time.monotonic()<due:self.cv.wait(None if not self.consent or not self.pending else max(.1,due-time.monotonic()));continue
                report=copy.deepcopy(self.pending[0]);identity=self.sync.identity_body()
                if not identity:due=time.monotonic()+30;continue
                try:self._save()
                except OSError:due=time.monotonic()+30;continue
            try:
                r=self.api.service(dict(identity,op='diagnostics_submit',consent=True,report=report))
                if r.get('report_id')!=report['id']:raise PlayerError()
                with self.cv:
                    if self.consent and self.pending and self.pending[0]['id']==report['id']:
                        self.pending.pop(0);self._save();self.status='최근 오류 기록을 관리자에게 보냈습니다.'
            except Exception:
                with self.cv:self.status='전송 연결 대기 · 오류 기록은 기기에 보관 중'
            due=time.monotonic()+60

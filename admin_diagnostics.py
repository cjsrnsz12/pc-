"""Opt-in bounded text reports and owner authentication; never uploads images."""
import base64,copy,ctypes,json,os,platform,re,threading,time,uuid
from pathlib import Path
from players_sync import PlayerError


def clean(value,limit=4000):
    text=str(value)
    for pattern,replacement in [
        (r'(?i)bearer\s+[A-Za-z0-9._~-]+','Bearer [가림]'),
        (r'''(?i)(token|password|passwd|secret|api[_-]?key|admin[_-]?key)["']?\s*[=:]\s*["']?[^\s,;"'}]+''',r'\1=[가림]'),
        (r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}','[이메일 가림]'),
        (r'https?://[^\s]+','[주소 가림]'),(r'(?i)[a-f0-9]{32,}','[인증값 가림]'),
        (r'(?i)(?:[A-Z]:\\Users\\|/Users/|/home/)[^\s]+','[경로 가림]')]:text=re.sub(pattern,replacement,text)
    return ''.join(c for c in text if c in '\n\t' or ord(c)>=32 and not 127<=ord(c)<=159)[-limit:]


def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    try:os.chmod(tmp,0o600)
    except OSError:pass
    os.replace(tmp,path)


def crypt(data,decrypt=False):
    if os.name!='nt':raise OSError('관리자 인증 저장은 Windows에서 지원합니다.')
    from ctypes import wintypes
    class Blob(ctypes.Structure):_fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    buffer=ctypes.create_string_buffer(data);source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));target=Blob()
    dll=ctypes.WinDLL('crypt32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree.restype=ctypes.c_void_p
    function=dll.CryptUnprotectData if decrypt else dll.CryptProtectData
    function.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)];function.restype=wintypes.BOOL
    if not function(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target)):raise ctypes.WinError(ctypes.get_last_error())
    try:return ctypes.string_at(target.data,target.size)
    finally:kernel.LocalFree(target.data)

class Diagnostics:
    def __init__(self,sync,directory,version):
        self.sync=sync;self.version=version;self.path=Path(directory)/'error_reports.json';self.key_path=Path(directory)/'admin_auth.json'
        self.lock=threading.RLock();self.consent=False;self.pending=[];self.seen=[];self.key='';self.generation=0;self.stop=threading.Event()
        try:
            state=json.loads(self.path.read_text(encoding='utf-8'));self.consent=state.get('consent') is True
            if self.consent:
                self.pending=[r for r in state.get('pending',[])[:20] if isinstance(r,dict) and len(json.dumps(r))<12000];self.seen=state.get('seen',[])[-60:]
        except (OSError,ValueError,TypeError):pass
        try:
            saved=json.loads(self.key_path.read_text(encoding='utf-8'));key=crypt(base64.b64decode(saved['ciphertext']),True).decode()
            if re.fullmatch('[a-f0-9]{64}',key):self.key=key
        except Exception:pass
        self.thread=threading.Thread(target=self.loop,name='NyacroDiagnostics',daemon=True);self.thread.start()
    def save(self):atomic(self.path,dict(consent=self.consent,pending=self.pending,seen=self.seen))
    def set_consent(self,enabled):
        with self.lock:
            old=(self.consent,copy.deepcopy(self.pending),self.seen[:]);self.consent=bool(enabled)
            if not enabled:self.pending=[];self.seen=[]
            try:self.save()
            except OSError:self.consent,self.pending,self.seen=old;raise
    def report(self,reason,logs,content,screen):
        with self.sync.cv:run=self.sync.run_id
        reason=clean(reason,240);fingerprint=run+'\n'+reason
        with self.lock:
            if not self.consent or not reason or fingerprint in self.seen or len(self.pending)>=20:return False
            report=dict(id=str(uuid.uuid4()),occurred_at=int(time.time()*1000),stop_reason=reason,logs=clean('\n'.join(clean(logs,12000).splitlines()[-30:])),device_model=clean(platform.system()+' '+platform.release(),80),screen=screen,content=content,device_type='pc',app_version=self.version,run_id=run)
            self.pending.append(report);self.seen=(self.seen+[fingerprint])[-60:];self.save();return True
    def loop(self):
        while not self.stop.wait(15):
            with self.lock:
                if not self.consent or not self.pending:continue
                report=copy.deepcopy(self.pending[0]);body=self.sync.identity_body()
                if not body:continue
                # Keep consent changes ordered with sending; UI performs changes on a worker.
                try:
                    result=self.sync.api.call(dict(body,op='diagnostics_submit',report=report))
                    if result.get('report_id')==report['id']:self.pending.pop(0);self.save()
                except Exception:pass
    def admin(self,op,key=None,**fields):
        with self.lock:secret=self.key if key is None else key;generation=self.generation
        if not re.fullmatch('[a-f0-9]{64}',secret):raise ValueError('관리자 인증키를 확인해 주세요.')
        body=self.sync.identity_body()
        if not body:raise ValueError('닉네임을 먼저 저장해 주세요.')
        try:result=self.sync.api.call(dict(body,op=op,admin_key=secret,**fields))
        except PlayerError as error:
            if error.code=='admin_required':
                with self.lock:
                    if generation==self.generation:self.logout()
            raise
        with self.lock:
            if generation!=self.generation:raise ValueError('관리자 인증이 변경되었습니다.')
            if key is not None:
                atomic(self.key_path,dict(ciphertext=base64.b64encode(crypt(secret.encode())).decode()));self.key=secret
        return result
    def logout(self):
        with self.lock:self.generation+=1;self.key='';self.key_path.unlink(missing_ok=True)
    def close(self):self.stop.set()

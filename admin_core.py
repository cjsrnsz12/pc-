"""Opt-in text diagnostics and Windows-user-bound administrator credentials."""
import base64,copy,ctypes,json,os,re,threading,time,uuid
from pathlib import Path
from players_sync import PlayerError

def clean(value,limit=4000):
    value=str(value)
    for pattern,replacement in [
        (r'(?i)bearer\s+[\w.~/-]+','Bearer [가림]'),
        (r'''(?i)(token|password|passwd|secret|api[_-]?key|admin[_-]?key)["']?\s*[=:]\s*["']?[^\s,;"'}]+''',r'\1=[가림]'),
        (r'[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}','[이메일 가림]'),
        (r'https?://\S+','[주소 가림]'),(r'(?i)[a-f0-9]{32,}','[인증값 가림]'),
        (r'(?i)(?:[A-Z]:\\Users\\|/Users/|/home/)\S+','[경로 가림]')]:
        value=re.sub(pattern,replacement,value)
    return ''.join(c for c in value if c in '\n\t' or ord(c)>=32)[-limit:]

def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    try:os.chmod(tmp,0o600)
    except OSError:pass
    os.replace(tmp,path)

def dpapi(data,decrypt=False):
    if os.name!='nt':raise OSError('관리자 인증 저장은 Windows에서 지원됩니다.')
    from ctypes import wintypes
    class Blob(ctypes.Structure):_fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    buffer=ctypes.create_string_buffer(data);source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));target=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    fn=crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.restype=wintypes.BOOL
    fn.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree.restype=ctypes.c_void_p
    if not fn(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target)):raise ctypes.WinError(ctypes.get_last_error())
    try:return ctypes.string_at(target.data,target.size)
    finally:kernel.LocalFree(target.data)

class AdminSession:
    def __init__(self,path,sync,cipher=dpapi):
        self.path=Path(path);self.sync=sync;self.cipher=cipher;self.lock=threading.RLock();self.generation=0;self.key=''
        try:
            key=cipher(base64.b64decode(self.path.read_bytes(),validate=True),True).decode()
            if re.fullmatch('[a-f0-9]{64}',key):self.key=key
        except (OSError,ValueError,UnicodeError):pass
    def logout(self):
        with self.lock:
            self.generation+=1;self.key=''
            self.path.unlink(missing_ok=True)
    def request(self,op='admin_list_errors',key=None,**fields):
        with self.lock:generation=self.generation;credential=self.key if key is None else key
        if not re.fullmatch('[a-f0-9]{64}',credential):raise ValueError('관리자 인증키를 확인해 주세요.')
        body=self.sync.identity_body()
        if not body:raise ValueError('닉네임을 먼저 저장해 주세요.')
        try:result=self.sync.api.service(dict(body,op=op,admin_key=credential,**fields))
        except PlayerError as error:
            if error.code=='admin_required':
                with self.lock:
                    if generation==self.generation and credential==self.key:self.logout()
            raise
        with self.lock:
            if generation!=self.generation:raise ValueError('관리자 인증이 해제되었습니다.')
            if key is not None:
                encrypted=base64.b64encode(self.cipher(key.encode()))
                self.path.parent.mkdir(parents=True,exist_ok=True);tmp=self.path.with_suffix('.tmp');tmp.write_bytes(encrypted);os.replace(tmp,self.path);self.key=key
        return result

class Diagnostics:
    def __init__(self,path,sync,version):
        self.path=Path(path);self.sync=sync;self.version=version;self.lock=threading.RLock();self.wake=threading.Event();self.closed=False
        self.state=dict(consent=False,pending=[],seen=[])
        try:
            saved=json.loads(self.path.read_text(encoding='utf-8'))
            if saved.get('consent') is True and isinstance(saved.get('pending'),list) and isinstance(saved.get('seen'),list):
                for item in saved['pending'][:20]:uuid.UUID(item['id'])
                self.state=dict(consent=True,pending=saved['pending'][:20],seen=saved['seen'][-60:])
        except (OSError,ValueError,KeyError,TypeError):pass
        self.thread=threading.Thread(target=self._loop,daemon=True,name='NyacroDiagnostics');self.thread.start()
    def consent(self,enabled):
        with self.lock:
            old=copy.deepcopy(self.state);self.state['consent']=bool(enabled)
            if not enabled:self.state.update(pending=[],seen=[])
            try:atomic(self.path,self.state)
            except OSError:self.state=old;raise
        self.wake.set()
    def report(self,reason,logs,content,screen):
        with self.sync.cv:run=self.sync.run_id
        reason=clean(reason,240);fingerprint=run+'\n'+reason
        with self.lock:
            if not self.state['consent'] or len(self.state['pending'])>=20 or fingerprint in self.state['seen']:return False
            report=dict(id=str(uuid.uuid4()),occurred_at=int(time.time()*1000),stop_reason=reason,logs=clean('\n'.join(str(logs).splitlines()[-30:])),device_model='Windows PC',screen=screen,content=content,device_type='pc',app_version=self.version,run_id=run)
            old=copy.deepcopy(self.state);self.state['pending'].append(report);self.state['seen']=(self.state['seen']+[fingerprint])[-60:]
            try:atomic(self.path,self.state)
            except OSError:self.state=old;return False
        self.wake.set();return True
    def _loop(self):
        while not self.closed:
            self.wake.wait(15);self.wake.clear()
            if self.closed:return
            with self.lock:
                body=self.sync.identity_body()
                if not self.state['consent'] or not self.state['pending'] or not body:continue
                report=copy.deepcopy(self.state['pending'][0])
            try:
                result=self.sync.api.service(dict(body,op='diagnostics_submit',consent=True,report=report))
                if result.get('report_id')!=report['id']:continue
                with self.lock:
                    if not self.state['pending'] or self.state['pending'][0]['id']!=report['id']:continue
                    old=copy.deepcopy(self.state);self.state['pending'].pop(0)
                    try:atomic(self.path,self.state)
                    except OSError:self.state=old
            except (PlayerError,OSError,ValueError):pass
    def close(self):self.closed=True;self.wake.set()

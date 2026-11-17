"""Private administrator client; Windows DPAPI protects remembered credentials."""
import base64,ctypes,json,os,re,sys,threading,uuid
from pathlib import Path
from players_sync import PlayerAPI,PlayerError

def valid_key(value):return isinstance(value,str) and re.fullmatch('[a-f0-9]{64}',value) is not None

def _dpapi(data,decrypt=False):
    if sys.platform!='win32':raise OSError('Windows protected storage is required')
    from ctypes import wintypes as w
    class Blob(ctypes.Structure):_fields_=[('size',w.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    raw=ctypes.create_string_buffer(data);source=Blob(len(data),ctypes.cast(raw,ctypes.POINTER(ctypes.c_ubyte)));target=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    function=crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,w.DWORD,ctypes.POINTER(Blob)];function.restype=w.BOOL
    kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree.restype=ctypes.c_void_p
    if not function(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target)):raise ctypes.WinError(ctypes.get_last_error())
    try:return ctypes.string_at(target.data,target.size)
    finally:kernel.LocalFree(target.data)

class CredentialStore:
    def __init__(self,path,protect=None,unprotect=None):self.path=Path(path);self.protect=protect or _dpapi;self.unprotect=unprotect or (lambda data:_dpapi(data,True))
    def load(self):
        try:
            if self.path.stat().st_size>4096:return ''
            saved=json.loads(self.path.read_text('utf-8'))
            if saved.get('version')!=1:return ''
            key=self.unprotect(base64.b64decode(saved['encrypted'],validate=True)).decode('ascii')
            return key if valid_key(key) else ''
        except Exception:return ''  # Keep ciphertext on transient OS/storage errors.
    def save(self,key):
        if not valid_key(key):return False
        temporary=self.path.with_suffix('.tmp')
        try:
            encoded=base64.b64encode(self.protect(key.encode('ascii'))).decode('ascii')
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temporary.write_text(json.dumps(dict(version=1,encrypted=encoded)),encoding='utf-8')
            os.chmod(temporary,0o600);os.replace(temporary,self.path);return True
        except Exception:
            try:temporary.unlink(missing_ok=True)
            except OSError:pass
            return False
    def clear(self):
        try:self.path.unlink(missing_ok=True);return True
        except OSError:return False

class AdminSession:
    def __init__(self,store):self.store=store;self.lock=threading.RLock();self.key='';self.revision=0;self.remembered=False
    def restore(self):
        with self.lock:
            if self.revision:return False
            self.revision+=1;self.key=self.store.load();self.remembered=valid_key(self.key);return self.remembered
    def begin(self,key):
        if not valid_key(key):raise ValueError('관리자 인증키를 확인해 주세요.')
        with self.lock:self.revision+=1;self.key=key;self.remembered=False
    def current(self):
        with self.lock:return self.revision,self.key
    def accepted(self,attempt):
        with self.lock:
            if attempt!=self.current():return False
            if not self.remembered:self.remembered=self.store.save(self.key)
            return self.remembered
    def rejected(self,attempt,code):
        with self.lock:
            if attempt==self.current() and code=='admin_required':self.logout()
    def logout(self):
        with self.lock:self.revision+=1;self.key='';self.remembered=False;return self.store.clear()
    def close(self):
        with self.lock:self.revision+=1;self.key='';self.remembered=False

class AdminAPI:
    def __init__(self,sync,api=None):self.sync=sync;self.api=api or PlayerAPI()
    def call(self,op,key,offset=0,unread=False,report_id=None):
        if not valid_key(key):raise ValueError('관리자 인증키를 확인해 주세요.')
        body=self.sync.identity_body()
        if not body:raise ValueError('닉네임을 먼저 저장해 주세요.')
        body.update(op=op,admin_key=key)
        if op=='admin_list_errors':body.update(offset=max(0,offset),unread_only=bool(unread))
        else:uuid.UUID(report_id);body['report_id']=report_id
        result=self.api.service(body)
        try:
            if op=='admin_list_errors':
                rows=result['reports']
                if not isinstance(rows,list) or len(rows)>20 or result['offset']!=max(0,offset) or type(result['total']) is not int or result['total']<0:raise ValueError()
                for row in rows:
                    uuid.UUID(row['id'])
                    if row['device_type'] not in ('pc','mobile','tablet') or 'logs' in row or 'token' in row:raise ValueError()
            elif op=='admin_read_error':
                row=result['report']
                if row['id']!=report_id or not isinstance(row.get('logs',''),str) or len(row.get('logs',''))>6000:raise ValueError()
            return result
        except (ValueError,KeyError,TypeError):raise PlayerError() from None

import hashlib
import io
import threading
import pytest
import updates

URL='https://github.com/cjsrnsz12/pc-/releases/download/v1.0.2/AbyssHelper.exe'


class Response(io.BytesIO):
    def __init__(self,data,headers=None):
        super().__init__(data);self.headers=headers or {}
    def geturl(self):
        return 'https://release-assets.githubusercontent.com/github-production-release-asset/test'


def release(data):
    return {'version':'v1.0.2','asset':{'browser_download_url':URL,'size':len(data),'digest':'sha256:'+hashlib.sha256(data).hexdigest()}}


def test_success_verified_and_atomically_saved(tmp_path,monkeypatch):
    data=b'MZ'+b'a'*600000
    monkeypatch.setattr(updates,'urlopen',lambda *a,**kw:Response(data,{'Content-Length':str(len(data))}))
    progress=[];path=tmp_path/'new.exe'
    assert updates.download_release(release(data),path,lambda d,t:progress.append((d,t)))==path
    assert path.read_bytes()==data
    assert progress[-1]==(len(data),len(data))
    assert not list(tmp_path.glob('*.part'))


@pytest.mark.parametrize('fault',['truncated','digest','format','oversized'])
def test_failed_download_preserves_existing_file(tmp_path,monkeypatch,fault):
    data=b'MZ'+b'a'*5000;r=release(data)
    delivered=data
    if fault=='truncated':delivered=data[:-5]
    elif fault=='digest':r['asset']['digest']='sha256:'+'0'*64
    elif fault=='format':delivered=b'XX'+data[2:]
    elif fault=='oversized':delivered=data+b'EXTRA'
    monkeypatch.setattr(updates,'urlopen',lambda *a,**kw:Response(delivered))
    path=tmp_path/'new.exe';path.write_bytes(b'previous')
    with pytest.raises(ValueError):updates.download_release(r,path)
    assert path.read_bytes()==b'previous'
    assert not list(tmp_path.glob('*.part'))


def test_cancel_removes_partial_file(tmp_path,monkeypatch):
    data=b'MZ'+b'a'*600000;cancel=threading.Event()
    monkeypatch.setattr(updates,'urlopen',lambda *a,**kw:Response(data))
    with pytest.raises(updates.DownloadCancelled):
        updates.download_release(release(data),tmp_path/'new.exe',lambda *_:cancel.set(),cancel)
    assert not list(tmp_path.iterdir())


def test_reject_other_repositories_and_mismatched_versions(tmp_path,monkeypatch):
    r=release(b'MZ1234')
    def no_network(*_,**__):raise AssertionError('Network must not be called')
    monkeypatch.setattr(updates,'urlopen',no_network)
    r['asset']['browser_download_url']=URL.replace('pc-','other')
    with pytest.raises(ValueError):updates.download_release(r,tmp_path/'new.exe')
    r['asset']['browser_download_url']=URL;r['version']='v1.0.3'
    with pytest.raises(ValueError):updates.download_release(r,tmp_path/'new.exe')

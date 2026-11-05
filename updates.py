"""Public GitHub Releases update notices; no credentials or background installation."""
import hashlib
import os
from pathlib import Path
import tempfile
import threading
import json
import re
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlparse
from version import VERSION, REPOSITORY


def version_tuple(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)',str(value).strip())
    if not match:
        raise ValueError('지원하지 않는 버전 형식')
    return tuple(map(int,match.groups()))


def release_url(url):
    p = urlparse(url)
    return p.scheme == 'https' and p.netloc == 'github.com' and p.path.startswith('/'+REPOSITORY+'/releases/') and not p.username


def parse_release(data, current=VERSION):
    if data.get('draft') or data.get('prerelease'):
        return None
    version = str(data.get('tag_name',''))
    if version_tuple(version) <= version_tuple(current):
        return None
    url = data.get('html_url','')
    if not release_url(url):
        raise ValueError('업데이트 페이지 주소가 저장소와 다릅니다.')
    assets = data.get('assets',[])
    asset = next((a for a in assets if a.get('name') == 'AbyssHelper.exe'),None)
    if asset is None:
        return None  # Do not announce a release until its Windows binary exists.
    return {'version':version,'url':url,'asset':asset,'notes':str(data.get('body') or '변경 내용은 배포 페이지에서 확인하세요.')[:24000]}


def check_update():
    request = Request('https://api.github.com/repos/'+REPOSITORY+'/releases/latest',headers={'User-Agent':'AbyssHelper/'+VERSION,'Accept':'application/vnd.github+json'})
    try:
        with urlopen(request,timeout=10) as response:
            data = response.read(512_001)
        if len(data) > 512_000:
            raise ValueError('업데이트 응답이 너무 큽니다.')
        return parse_release(json.loads(data))
    except HTTPError as e:
        if e.code == 404:
            return None
        raise


MAX_DOWNLOAD = 300 * 1024 * 1024


class DownloadCancelled(Exception):
    pass


def download_url(url):
    p = urlparse(url)
    prefix = '/' + REPOSITORY + '/releases/download/'
    parts = p.path[len(prefix):].split('/') if p.path.startswith(prefix) else []
    return (p.scheme == 'https' and p.netloc == 'github.com' and not p.query and not p.fragment
            and len(parts) == 2 and bool(re.fullmatch(r'v?\d+\.\d+\.\d+',parts[0]))
            and parts[1] == 'AbyssHelper.exe')


def download_release(release, destination, progress=None, cancel=None):
    """Stream to a private partial file, verify, then atomically replace destination."""
    cancel = cancel if cancel is not None else threading.Event()
    asset = release.get('asset',{})
    url = asset.get('browser_download_url','')
    if not download_url(url):
        raise ValueError('이 저장소의 실행 파일 다운로드 주소가 아닙니다.')
    tag = urlparse(url).path.split('/')[-2]
    if version_tuple(tag) != version_tuple(release.get('version','')):
        raise ValueError('다운로드 파일의 버전이 안내된 버전과 다릅니다.')
    expected = asset.get('size')
    if type(expected) is not int or expected <= 0 or expected > MAX_DOWNLOAD:
        raise ValueError('다운로드 파일 크기 정보를 확인할 수 없습니다.')
    destination = Path(destination)
    if destination.suffix.lower() != '.exe':
        raise ValueError('실행 파일은 .exe 확장자로 저장하세요.')
    if not destination.parent.is_dir():
        raise ValueError('저장 폴더를 찾을 수 없습니다.')
    digest = asset.get('digest') or ''
    if digest and not re.fullmatch(r'sha256:[0-9a-fA-F]{64}',digest):
        raise ValueError('지원하지 않는 파일 검증 정보입니다.')
    request = Request(url,headers={'User-Agent':'AbyssHelper/'+VERSION,'Accept':'application/octet-stream'})
    temp = None
    try:
        if cancel.is_set():raise DownloadCancelled()
        with urlopen(request,timeout=15) as response:
            target = urlparse(response.geturl())
            if target.scheme != 'https' or target.hostname not in {'github.com','release-assets.githubusercontent.com','objects.githubusercontent.com'}:
                raise ValueError('다운로드 서버 주소를 확인할 수 없습니다.')
            header = response.headers.get('Content-Length')
            if header and int(header) != expected:
                raise ValueError('서버 파일 크기가 배포 정보와 다릅니다.')
            fd,tempname = tempfile.mkstemp(prefix='.abyss-',suffix='.part',dir=destination.parent)
            temp = Path(tempname)
            received = 0
            sha = hashlib.sha256()
            signature = b''
            with os.fdopen(fd,'wb') as output:
                while True:
                    if cancel.is_set():raise DownloadCancelled()
                    chunk = response.read(256*1024)
                    if not chunk:break
                    if not signature:signature = chunk[:2]
                    received += len(chunk)
                    if received > expected or received > MAX_DOWNLOAD:
                        raise ValueError('예상 크기를 초과한 파일입니다.')
                    sha.update(chunk);output.write(chunk)
                    if progress:progress(received,expected)
                output.flush();os.fsync(output.fileno())
            if cancel.is_set():raise DownloadCancelled()
            if received != expected:
                raise ValueError('다운로드가 중간에 끊겼습니다. 다시 시도하세요.')
            if signature != b'MZ':
                raise ValueError('올바른 Windows 실행 파일이 아닙니다.')
            if digest and sha.hexdigest().lower() != digest.split(':',1)[1].lower():
                raise ValueError('파일 검증에 실패했습니다. 다시 다운로드하세요.')
            os.replace(temp,destination)
            return destination
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)

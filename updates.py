"""Public GitHub Releases update notices; no credentials or background installation."""
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
    if not any(a.get('name') == 'AbyssHelper.exe' for a in assets):
        return None  # Do not announce a release until its Windows binary exists.
    return {'version':version,'url':url,'notes':str(data.get('body') or '변경 내용은 배포 페이지에서 확인하세요.')[:24000]}


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

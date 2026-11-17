import copy,json,os,threading,uuid
import pytest
from admin_diagnostics import Diagnostics,clean,crypt
from players_sync import PlayerSync,device_labels,PlayerError
from test_players_sync import API,until


def test_device_choices_persist_and_actual_connection_stays_pc(tmp_path):
    api=API();s=PlayerSync(tmp_path/'p.json','1.1.48',api=api,interval=300)
    s.set_devices(['mobile','tablet']);s.set_nickname('같은이름');until(lambda:len(api.calls)>=2)
    registration=next(b for b in api.calls if b['op']=='players_register')
    assert registration['device_type']=='pc' and registration['used_devices']==['mobile','tablet']
    s.close();s.thread.join(1);s=PlayerSync(tmp_path/'p.json','1.1.48',api=api,interval=300)
    assert s.view()['devices_confirmed'] and s.view()['used_devices']==['mobile','tablet']
    s.close();s.thread.join(1)
    assert device_labels(dict(platform='mobile',device_types=['pc','mobile','tablet']))=='PC · 모바일 · 태블릿'


def service(tmp_path):
    s=PlayerSync(tmp_path/'p.json','1.1.48',api=API(),interval=300);s.set_nickname('냥이');s.new_run('어비스');until(lambda:s.registered)
    d=Diagnostics(s,tmp_path,'1.1.48');return s,d


def test_opt_in_redaction_dedup_and_revocation(tmp_path):
    s,d=service(tmp_path)
    assert not d.report('오류','secret=abcd','어비스','1920x1080')
    d.set_consent(True)
    assert d.report('오류','token=abc\nmail@example.com\nhttps://example.com\n'+'a'*64,'어비스','1920x1080')
    assert not d.report('오류','다름','어비스','1920x1080')
    text=json.dumps(d.pending,ensure_ascii=False)
    assert 'mail@example.com' not in text and 'token=abc' not in text and 'a'*64 not in text and 'example.com' not in text
    d.close();d=Diagnostics(s,tmp_path,'1.1.48');assert len(d.pending)==1 and d.consent
    d.set_consent(False);assert not d.pending and not json.loads(d.path.read_text())['pending']
    d.close();s.close();s.thread.join(1)


def test_report_bound_and_last_thirty_lines(tmp_path):
    s,d=service(tmp_path);d.set_consent(True)
    for i in range(25):d.report(str(i),'\n'.join(str(n) for n in range(80)),'어비스','1920x1080')
    assert len(d.pending)==20 and d.pending[0]['logs'].splitlines()==[str(n) for n in range(50,80)]
    d.close();s.close();s.thread.join(1)


def test_logout_blocks_late_successful_login(tmp_path,monkeypatch):
    s,d=service(tmp_path);started=threading.Event();release=threading.Event()
    def call(body):started.set();release.wait(2);return dict(ok=True,reports=[],total=0)
    s.api=type('API',(),{'call':staticmethod(call)})();errors=[]
    def attempt():
        try:d.admin('admin_list_errors','a'*64,offset=0,unread_only=True)
        except Exception as error:errors.append(error)
    t=threading.Thread(target=attempt);t.start();assert started.wait(1);d.logout();release.set();t.join(2)
    assert errors and not d.key and not d.key_path.exists()
    d.close();s.close();s.thread.join(1)


@pytest.mark.skipif(os.name!='nt',reason='Windows DPAPI')
def test_windows_dpapi_roundtrip_and_tamper():
    data=b'a'*64;encrypted=crypt(data);assert encrypted!=data and crypt(encrypted,True)==data
    with pytest.raises(OSError):crypt(encrypted[:-10]+b'changed',True)

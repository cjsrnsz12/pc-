"""Native Tk/DPAPI check using synthetic data only."""
import tempfile,time,threading
from pathlib import Path
from admin_core import AdminSession
from admin_ui import AdminWindow

def exercise_admin(parent):
    class Sync:
        def __init__(self):self.api=self;self.cv=threading.RLock()
        def identity_body(self):return {'member_id':'00000000-0000-4000-8000-000000000001','token':'b'*64}
        def service(self,body):
            if body['op']=='admin_list_errors':return dict(ok=True,total=1,reports=[dict(id='00000000-0000-4000-8000-000000000002',nickname='검사 예시',device_type='tablet',stop_reason='오류 중지 예시')])
            if body['op']=='admin_read_error':return dict(ok=True,report=dict(id=body['report_id'],logs='예시 기록',device_type='tablet'))
            return dict(ok=True)
    class Reports:
        state={'consent':False}
        def consent(self,value):self.state={'consent':value}
    def settle(window):
        end=time.monotonic()+4
        while window.busy and time.monotonic()<end:parent.update();time.sleep(.01)
        assert not window.busy
    with tempfile.TemporaryDirectory() as temp:
        sync=Sync();session=AdminSession(Path(temp)/'credential',sync);window=AdminWindow(parent,session,Reports());parent.update()
        window.key.set('a'*64);window.load();settle(window)
        assert len(window.table.get_children())==1 and session.key
        window.table.selection_set(window.table.get_children()[0]);parent.update();settle(window)
        assert '예시 기록' in window.text.get('1.0','end')
        window.close();assert AdminSession(session.path,sync).key==session.key
        window=AdminWindow(parent,session,Reports());settle(window);window.logout();assert not session.key and not session.path.exists();window.close()
    return {'native_ui':True,'encrypted_restart':True,'logout':True,'data':'synthetic'}

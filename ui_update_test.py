"""Packaged Windows test: invoke real notification buttons with local test downloads."""
from pathlib import Path
import time
from update_notice import UpdateNotice,UpdateOperations
from updates import parse_release
import update_notice


def exercise_update_buttons(app):
    calls=[];closed=[];errors=[]
    release=parse_release({'tag_name':'v99.0.0','html_url':'https://github.com/cjsrnsz12/pc-/releases/tag/v99.0.0',
        'assets':[{'name':'AbyssHelper.exe'}],
        'body':'# v99.0.0\n## 새 기능\n- 새 알림창\n## 개선\n- 색 구분\n## 버그 수정\n- 버튼 반응 수정\n# v98.0.0\n- 과거 내용'},current='0.0.0')
    old_close=app.close;old_error=update_notice.messagebox.showerror
    app.close=lambda:closed.append(True)
    update_notice.messagebox.showerror=lambda *a,**kw:errors.append(a)
    root=app.root;root.deiconify();root.update()
    def pump(predicate):
        end=time.monotonic()+8
        while time.monotonic()<end:
            root.update()
            if predicate():return
            time.sleep(.01)
        raise AssertionError('Update button UI transition timed out')
    def prepare(path,*args):
        calls.append('prepare');p=Path(path).parent/'test-plan.json';p.write_text('{}');return p
    def launch(path):calls.append('launch')
    def download(release,path,progress,cancel):
        calls.append('download');Path(path).write_bytes(b'MZ-test');progress(7,7);return path
    notice=None
    try:
        app.installing=True  # Regression: a stale busy flag used to silently swallow clicks.
        app.download_workers=[]
        notice=UpdateNotice(app,release,UpdateOperations(download,prepare,launch))
        app.update_notice=notice;app.update_dialog=notice.dialog
        assert '과거' not in notice.notes.get('1.0','end')
        for kind in ['new','improvement','fix']:assert notice.notes.tag_ranges(kind)
        notice.dialog.withdraw();app.show_update(release);root.update()
        assert notice.dialog.state()!='withdrawn'
        notice.primary.invoke()
        assert '다운로드' in notice.status.get()  # Immediate visible feedback from the actual click.
        pump(lambda:bool(closed))
        assert calls==['download','prepare','launch']
        notice.phase='idle';notice.close();root.update()
        calls.clear();closed.clear()
        attempt=[0]
        def retry_download(release,path,progress,cancel):
            attempt[0]+=1
            if attempt[0]==1:raise OSError('Test disconnected network')
            return download(release,path,progress,cancel)
        notice=UpdateNotice(app,release,UpdateOperations(retry_download,prepare,launch))
        app.update_notice=notice;app.update_dialog=notice.dialog
        notice.primary.invoke();pump(lambda:notice.phase=='failed')
        assert not app.installing and errors
        assert '실패' in notice.status.get()
        notice.primary.invoke();pump(lambda:bool(closed))
        assert attempt[0]==2 and calls==['download','prepare','launch']
        notice.phase='idle';notice.close();root.update()
        return {'button_invoke':'download-prepare-launch','stale_busy_recovery':True,'hidden_window_recovery':True,'retry':True,'latest_notes_only':True,'colored_groups':True}
    finally:
        if notice and not notice.closed:notice.phase='idle';notice.close()
        app.close=old_close;update_notice.messagebox.showerror=old_error

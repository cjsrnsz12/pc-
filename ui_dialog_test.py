"""Verify compact update decision and fixed action footer in a small native window."""
import time
from pathlib import Path
import ctypes as C
from ctypes import wintypes as W
from PIL import Image
from update_notice import UpdateNotice,UpdateOperations
from update_prompt import UpdatePrompt
from ui_controls import RoundScrollbar
from release_notes import grouped_changes


def exercise_update_dialogs(app,report_path):
    import mss
    root=app.root;root.deiconify();root.update()
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        notice_state=Path(directory)/'release-notice.json'
        assert app.show_installed_changes(notice_state)
        installed=app.installed_notice;root.update()
        assert installed.heading.cget('text')=='업데이트 소식'
        assert not installed.primary.winfo_ismapped() and not installed.file_button.winfo_ismapped()
        assert not installed.footer.winfo_ismapped() and not installed.close_button.winfo_ismapped()
        assert installed.notes.winfo_ismapped()
        # Design-only releases need not invent a bug-fix section.
        changes=installed.release['changes']
        for kind,items in changes.items():
            assert bool(installed.notes.tag_ranges(kind))==bool(items)
        assert not app.show_installed_changes(notice_state)
        installed.close();root.update()
        assert not app.show_installed_changes(notice_state)

    release={'version':'v99.0.0','is_new':True,'notes':'## 새 기능\n- 작은 업데이트 창\n## 개선\n- 둥근 스크롤바\n## 버그 수정\n- 설치 버튼 잘림 수정',
             'changes':grouped_changes('## 새 기능\n- 작은 업데이트 창\n## 개선\n- 둥근 스크롤바\n## 버그 수정\n- 설치 버튼 잘림 수정')}
    def pump(predicate,timeout=6):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            root.update()
            if predicate():return
            time.sleep(.01)
        raise AssertionError('Update decision test timed out')
    def inside(widget,dialog):
        return (widget.winfo_rooty()>=dialog.winfo_rooty() and
                widget.winfo_rooty()+widget.winfo_height()<=dialog.winfo_rooty()+dialog.winfo_height()+1)
    called=[];closed=[];old_close=app.close;app.close=lambda:closed.append(True)
    def download(r,p,report,cancel):Path(p).write_bytes(b'MZ-test');report(7,7);called.append('download');return p
    def prepare(p,*args):f=Path(p).parent/'test-plan.json';f.write_text('{}');called.append('prepare');return f
    def launch(p):called.append('launch')
    notice=UpdateNotice(app,release,UpdateOperations(download,prepare,launch));app.update_notice=notice;app.update_dialog=notice.dialog
    prompt=None
    try:
        notice.dialog.geometry('600x450');root.update()
        assert inside(notice.primary,notice.dialog) and inside(notice.close_button,notice.dialog)
        assert isinstance(notice.scroll,RoundScrollbar)
        assert notice.scroll.winfo_viewable() and notice.scroll.winfo_width()>=12
        assert notice.scroll.last-notice.scroll.first<.999
        assert notice.scroll.itemcget(notice.scroll._thumb,'state')=='normal'
        assert notice.scroll.cget('background')=='#09101b'
        hwnd=app.win.u.GetAncestor(notice.dialog.winfo_id(),2);rect=W.RECT();origin=W.POINT()
        app.win.u.GetClientRect(hwnd,C.byref(rect));app.win.u.ClientToScreen(hwnd,C.byref(origin))
        preview=Path(report_path).with_name('abyss-dialog.png')
        with mss.mss() as capture:
            shot=capture.grab({'left':origin.x,'top':origin.y,'width':rect.right,'height':rect.bottom})
            Image.frombytes('RGB',shot.size,shot.rgb).save(preview)
        prompt=UpdatePrompt(app,release);app.update_prompt=prompt;root.update()
        assert inside(prompt.primary,prompt.dialog) and inside(prompt.details,prompt.dialog)
        outer=W.RECT();phwnd=app.win.u.GetAncestor(prompt.dialog.winfo_id(),2)
        app.win.u.GetWindowRect(phwnd,C.byref(outer));_,work=app.win.monitor_info(phwnd)
        assert outer.top>=work[1] and outer.bottom<=work[3]
        prompt.primary.invoke();pump(lambda:bool(closed))
        assert prompt.closed and called==['download','prepare','launch']
        return {'small_window_install_visible':True,'compact_prompt_visible':True,'prompt_button_starts_update':True,'rounded_scrollbar':True,'dialog_preview':str(preview)}
    finally:
        if prompt and not prompt.closed:prompt.close()
        notice.phase='idle';notice.close();app.close=old_close

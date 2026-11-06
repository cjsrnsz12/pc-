"""Exercise real Win32 sizing on a disposable test window, never another app."""
import sys
import pytest

pytestmark = pytest.mark.skipif(sys.platform != 'win32',reason='Windows native API test')


@pytest.fixture(scope='module')
def native_root():
    from windows import dpi_aware
    import tkinter as tk
    dpi_aware()
    root=tk.Tk();root.withdraw()
    yield root
    root.destroy()


def test_native_resize_restores_and_sizes_client(monkeypatch,native_root):
    from windows import Windows, WindowError, dpi_aware
    import tkinter as tk
    dpi_aware()
    root=tk.Toplevel(native_root)
    try:
        root.title('Abyss Helper sizing test')
        root.maxsize(4000,4000)
        root.geometry('500x600')
        root.update()
        win=Windows()
        hwnd=win.u.GetAncestor(root.winfo_id(),2)
        with pytest.raises(WindowError):win.ensure_game(hwnd)
        # Bypass identity for this test's own window only; all native sizing remains real.
        original=win.ensure_game
        monkeypatch.setattr(win,'ensure_game',lambda handle:None if handle==hwnd else original(handle))
        _,work=win.monitor_info(hwnd)
        if work[2]-work[0]<800 or work[3]-work[1]<1000:
            with pytest.raises(WindowError,match='작업 영역'):
                win.resize(hwnd)
            return
        for mode in [1,2,3]: # normal, minimized, maximized
            win.u.ShowWindow(hwnd,mode)
            root.update()
            try:win.resize(hwnd)
            except WindowError as error:
                assert '제목 표시줄' in str(error) and '작업 영역' in str(error)
                return
            root.update()
            if win.rect(hwnd)[2:]!=(800,1000):
                win.resize(hwnd,correction=True);root.update()
            assert win.rect(hwnd)[2:]==(800,1000)
            assert win.u.GetWindowLongW(hwnd,-16)&0x00C00000
    finally:
        root.destroy()



def test_native_borderless_conversion(monkeypatch,native_root):
    from windows import Windows, dpi_aware
    import tkinter as tk
    dpi_aware()
    root=tk.Toplevel(native_root)
    try:
        root.title('Abyss Helper borderless test');root.overrideredirect(True)
        root.geometry('600x700');root.update()
        win=Windows();hwnd=win.u.GetAncestor(root.winfo_id(),2)
        monkeypatch.setattr(win,'ensure_game',lambda handle:None)
        win.make_windowed(hwnd)
        assert win.u.GetWindowLongW(hwnd,-16)&0x00C00000
        info=win.diagnostics(hwnd)
        assert 'dpi' in info and 'work' in info and 'fullscreen_like' in info
    finally:root.destroy()


def test_native_elevation_read_and_preflight_block(monkeypatch,native_root):
    from windows import Windows,PermissionRequired
    from privileges import process_elevated
    import os
    assert type(process_elevated()) is bool
    assert process_elevated(os.getpid())==process_elevated()
    win=Windows()
    monkeypatch.setattr(win,'permission_status',lambda _:{'app_admin':False,'game_admin':True})
    with pytest.raises(PermissionRequired) as error:win.require_control_permission(0)
    assert error.value.winerror==5


def test_native_click_without_manual_pointer_movement(monkeypatch,native_root):
    import tkinter as tk
    import threading
    import time
    from windows import Windows
    root=tk.Toplevel(native_root);root.geometry('500x400+0+0');hits=[];errors=[]
    button=tk.Button(root,text='Stationary pointer test',command=lambda:hits.append(1))
    button.place(x=50,y=60,width=180,height=45)
    root.update();win=Windows();hwnd=win.u.GetAncestor(root.winfo_id(),2)
    monkeypatch.setattr(win,'ensure_game',lambda handle:None if handle==hwnd else (_ for _ in ()).throw(AssertionError('wrong test window')))
    monkeypatch.setattr(win,'require_control_permission',lambda handle:None)
    left,top,_,_=win.rect(hwnd)
    monkeypatch.setattr(win,'rect',lambda handle:(left,top,800,1000))
    try:
        win.u.SetForegroundWindow(hwnd);root.focus_force();root.update()
        for _ in range(2):
            def click():
                try:win.click(hwnd,(130,80))
                except Exception as error:errors.append(error)
            worker=threading.Thread(target=click);worker.start()
            deadline=time.monotonic()+5
            while worker.is_alive() and time.monotonic()<deadline:
                root.update();time.sleep(.005)
            worker.join(timeout=1);root.update()
            assert not worker.is_alive() and not errors
        assert hits==[1,1]
    finally:root.destroy()


def test_native_list_center_move_ends_at_client_center_without_click(monkeypatch,native_root):
    import tkinter as tk
    import threading
    import ctypes as C
    from ctypes import wintypes as W
    from windows import Windows
    root=tk.Toplevel(native_root);root.geometry('500x600+0+0');clicks=[]
    root.bind('<ButtonPress-1>',lambda _:clicks.append(1))
    root.update();win=Windows();hwnd=win.u.GetAncestor(root.winfo_id(),2)
    monkeypatch.setattr(win,'ensure_game',lambda handle:None)
    monkeypatch.setattr(win,'require_control_permission',lambda handle:None)
    left,top,_,_=win.rect(hwnd)
    monkeypatch.setattr(win,'rect',lambda handle:(left,top,800,1000))
    try:
        win.u.SetForegroundWindow(hwnd);root.focus_force();root.update()
        assert win.center_list_pointer(hwnd,threading.Event())
        point=W.POINT();assert win.u.GetCursorPos(C.byref(point))
        assert (point.x,point.y)==(left+400,top+500)
        root.update();assert not clicks
        stopped=threading.Event();stopped.set()
        assert not win.center_list_pointer(hwnd,stopped)
        again=W.POINT();win.u.GetCursorPos(C.byref(again))
        assert (again.x,again.y)==(point.x,point.y)
    finally:root.destroy()

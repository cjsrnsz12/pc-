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

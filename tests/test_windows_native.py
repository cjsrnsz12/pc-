"""Exercise real Win32 sizing on a disposable test window, never another app."""
import sys
import pytest

pytestmark = pytest.mark.skipif(sys.platform != 'win32',reason='Windows native API test')


def test_native_resize_restores_and_sizes_client(monkeypatch):
    from windows import Windows, WindowError, dpi_aware
    import tkinter as tk
    dpi_aware()
    root=tk.Tk()
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
        for mode in [1,2,3]: # normal, minimized, maximized
            win.u.ShowWindow(hwnd,mode)
            root.update()
            win.resize(hwnd)
            root.update()
            if win.rect(hwnd)[2:]!=(800,1000):
                win.resize(hwnd,correction=True);root.update()
            assert win.rect(hwnd)[2:]==(800,1000)
    finally:
        root.destroy()

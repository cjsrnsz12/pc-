"""Keep dialogs inside the current monitor's usable desktop, including their title bar."""
import ctypes as C
from ctypes import wintypes as W


def fit_dialog(app,dialog,preferred=(700,700),minimum=(520,440)):
    dialog.update_idletasks()
    try:
        hwnd=app.win.u.GetAncestor(dialog.winfo_id(),2)
        outer,client=W.RECT(),W.RECT()
        app.win.u.GetWindowRect(hwnd,C.byref(outer));app.win.u.GetClientRect(hwnd,C.byref(client))
        frame_w=max(0,outer.right-outer.left-client.right);frame_h=max(0,outer.bottom-outer.top-client.bottom)
        parent=app.win.u.GetAncestor(app.root.winfo_id(),2)
        _,work=app.win.monitor_info(parent)
    except Exception:
        work=(0,0,dialog.winfo_screenwidth(),dialog.winfo_screenheight());frame_w,frame_h=16,40
    width=min(preferred[0],max(300,work[2]-work[0]-frame_w-24))
    height=min(preferred[1],max(240,work[3]-work[1]-frame_h-24))
    dialog.minsize(min(minimum[0],width),min(minimum[1],height))
    x=max(work[0]+12,min(app.root.winfo_rootx()+24,work[2]-width-frame_w-12))
    y=max(work[1]+12,min(app.root.winfo_rooty()+24,work[3]-height-frame_h-12))
    dialog.geometry(f'{width}x{height}+{x}+{y}')

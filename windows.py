"""Windows game client selection, physical-pixel capture and guarded mouse input."""
import sys
import ctypes as C
from ctypes import wintypes as W
from game_identity import is_game_window


def dpi_aware():
    if sys.platform == 'win32':
        try:
            C.windll.user32.SetProcessDpiAwarenessContext(C.c_void_p(-4))
        except (AttributeError, OSError):
            C.windll.user32.SetProcessDPIAware()


class WindowError(RuntimeError):
    pass


class Windows:
    def __init__(self):
        if sys.platform != 'win32':
            raise WindowError('이 앱은 Windows 10/11 PC용입니다.')
        self.u = C.WinDLL('user32', use_last_error=True)
        self.k = C.WinDLL('kernel32',use_last_error=True)
        self.k.OpenProcess.argtypes = [W.DWORD,W.BOOL,W.DWORD]
        self.k.OpenProcess.restype = W.HANDLE
        self.k.QueryFullProcessImageNameW.argtypes = [W.HANDLE,W.DWORD,W.LPWSTR,C.POINTER(W.DWORD)]
        self.k.CloseHandle.argtypes = [W.HANDLE]
        self.u.GetWindowThreadProcessId.argtypes = [W.HWND,C.POINTER(W.DWORD)]
        self.u.GetWindowRect.argtypes = [W.HWND,C.POINTER(W.RECT)]
        self.u.MonitorFromWindow.argtypes = [W.HWND,W.DWORD]
        self.u.MonitorFromWindow.restype = W.HANDLE
        self.u.GetForegroundWindow.restype = W.HWND
        self.u.GetAncestor.argtypes = [W.HWND, W.UINT]
        self.u.GetAncestor.restype = W.HWND
        self.u.IsWindow.argtypes = [W.HWND]
        self.u.IsIconic.argtypes = [W.HWND]
        self.u.GetClientRect.argtypes = [W.HWND,C.POINTER(W.RECT)]
        self.u.ClientToScreen.argtypes = [W.HWND,C.POINTER(W.POINT)]
        self.u.GetMenu.argtypes = [W.HWND]
        self.u.GetMenu.restype = W.HMENU
        self.u.ShowWindow.argtypes = [W.HWND,C.c_int]
        self.u.AdjustWindowRectEx.argtypes = [C.POINTER(W.RECT),W.DWORD,W.BOOL,W.DWORD]
        self.u.GetWindowLongW.argtypes = [W.HWND,C.c_int]
        self.u.SetWindowPos.argtypes = [W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT]
        self.callback = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
        self.u.GetWindowTextLengthW.argtypes = [W.HWND]
        self.u.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
        self.u.IsWindowVisible.argtypes = [W.HWND]
        self.u.EnumWindows.argtypes = [self.callback,W.LPARAM]
        self.u.GetAsyncKeyState.argtypes = [C.c_int]
        self.u.GetAsyncKeyState.restype = C.c_short

    def identity(self, hwnd):
        if not self.u.IsWindow(hwnd):
            return ('','')
        n = self.u.GetWindowTextLengthW(hwnd)
        title = C.create_unicode_buffer(n+1)
        self.u.GetWindowTextW(hwnd,title,n+1)
        pid = W.DWORD()
        self.u.GetWindowThreadProcessId(hwnd,C.byref(pid))
        handle = self.k.OpenProcess(0x1000,False,pid.value)
        if not handle:
            return (title.value,'')
        try:
            size = W.DWORD(32768)
            path = C.create_unicode_buffer(size.value)
            if not self.k.QueryFullProcessImageNameW(handle,0,path,C.byref(size)):
                return (title.value,'')
            return (title.value,path.value)
        finally:
            self.k.CloseHandle(handle)

    def ensure_game(self, hwnd):
        if not is_game_window(*self.identity(hwnd)):
            raise WindowError('마비노기 모바일 게임 창을 확인하지 못했습니다. 게임을 실행하고 다시 시도하세요.')

    def list_windows(self):
        result = []
        @self.callback
        def each(hwnd, _):
            if self.u.IsWindowVisible(hwnd):
                title, path = self.identity(hwnd)
                if is_game_window(title,path):
                    r = W.RECT()
                    if self.u.GetClientRect(hwnd,C.byref(r)):
                        result.append((int(hwnd),title,r.right,r.bottom))
            return True
        self.u.EnumWindows(each,0)
        return result

    def rect(self, hwnd):
        if not self.u.IsWindow(hwnd) or self.u.IsIconic(hwnd):
            raise WindowError('게임 창이 닫혔거나 최소화되었습니다.')
        r, p = W.RECT(), W.POINT(0,0)
        if not self.u.GetClientRect(hwnd,C.byref(r)) or not self.u.ClientToScreen(hwnd,C.byref(p)):
            raise WindowError('게임 화면 위치를 읽지 못했습니다.')
        return (p.x,p.y,r.right,r.bottom)

    def resize(self, hwnd, correction=False):
        self.ensure_game(hwnd)
        self.u.ShowWindow(hwnd,9)
        style = self.u.GetWindowLongW(hwnd,-16)
        exstyle = self.u.GetWindowLongW(hwnd,-20)
        rect = W.RECT(0,0,800,1000)
        has_menu = bool(self.u.GetMenu(hwnd))
        try:
            self.u.GetDpiForWindow.argtypes = [W.HWND]
            dpi = self.u.GetDpiForWindow(hwnd)
            self.u.AdjustWindowRectExForDpi.argtypes = [C.POINTER(W.RECT),W.DWORD,W.BOOL,W.DWORD,W.UINT]
            self.u.AdjustWindowRectExForDpi(C.byref(rect),style,has_menu,exstyle,dpi)
        except AttributeError:
            self.u.AdjustWindowRectEx(C.byref(rect),style,has_menu,exstyle)
        width,height = rect.right-rect.left,rect.bottom-rect.top
        outer = W.RECT()
        self.u.GetWindowRect(hwnd,C.byref(outer))
        if correction:
            _,_,cw,ch = self.rect(hwnd)
            width,height = outer.right-outer.left+800-cw,outer.bottom-outer.top+1000-ch
        class MONITORINFO(C.Structure):
            _fields_ = [('cbSize',W.DWORD),('rcMonitor',W.RECT),('rcWork',W.RECT),('dwFlags',W.DWORD)]
        info = MONITORINFO();info.cbSize = C.sizeof(info)
        monitor = self.u.MonitorFromWindow(hwnd,2)
        self.u.GetMonitorInfoW.argtypes = [W.HANDLE,C.POINTER(MONITORINFO)]
        x,y = outer.left,outer.top
        if self.u.GetMonitorInfoW(monitor,C.byref(info)):
            r = info.rcWork
            x = max(r.left,min(x,r.right-width))
            y = max(r.top,min(y,r.bottom-height))
        if not self.u.SetWindowPos(hwnd,None,x,y,width,height,0x0004|0x0010):
            raise WindowError('창 크기를 바꿀 수 없습니다. 게임을 창 모드로 설정하세요.')

    def active(self, hwnd):
        current = self.u.GetForegroundWindow()
        return bool(current and self.u.GetAncestor(current,2) == hwnd)

    def keys(self):
        return (bool(self.u.GetAsyncKeyState(0x77)&0x8000), bool(self.u.GetAsyncKeyState(0x78)&0x8000))

    def click(self, hwnd, point):
        # Recheck identity, foreground, client size and visibility before every click.
        self.ensure_game(hwnd)
        if not self.active(hwnd):
            raise WindowError('게임 창이 앞에 있지 않아 입력을 보류했습니다.')
        left,top,width,height = self.rect(hwnd)
        if (width,height) != (800,1000):
            raise WindowError('게임 화면이 800×1000이 아닙니다. 중지 후 크기를 다시 맞추세요.')
        x,y = point
        if not (0 <= x < width and 0 <= y < height):
            raise WindowError('화면 밖 클릭을 차단했습니다.')
        vx,vy = self.u.GetSystemMetrics(76), self.u.GetSystemMetrics(77)
        vw,vh = self.u.GetSystemMetrics(78), self.u.GetSystemMetrics(79)
        sx,sy = left+x, top+y
        if not (vx <= sx < vx+vw and vy <= sy < vy+vh):
            raise WindowError('클릭 위치가 모니터 밖에 있습니다.')
        class MOUSEINPUT(C.Structure):
            _fields_ = [('dx',W.LONG),('dy',W.LONG),('mouseData',W.DWORD),('dwFlags',W.DWORD),('time',W.DWORD),('dwExtraInfo',C.c_size_t)]
        class KEYBDINPUT(C.Structure):
            _fields_ = [('wVk',W.WORD),('wScan',W.WORD),('dwFlags',W.DWORD),('time',W.DWORD),('dwExtraInfo',C.c_size_t)]
        class HARDWAREINPUT(C.Structure):
            _fields_ = [('uMsg',W.DWORD),('wParamL',W.WORD),('wParamH',W.WORD)]
        class U(C.Union):
            _fields_ = [('mi',MOUSEINPUT),('ki',KEYBDINPUT),('hi',HARDWAREINPUT)]
        class INPUT(C.Structure):
            _anonymous_ = ('union',)
            _fields_ = [('type',W.DWORD),('union',U)]
        ax = round((sx-vx)*65535/max(1,vw-1))
        ay = round((sy-vy)*65535/max(1,vh-1))
        events = (INPUT*3)()
        for i,flags in enumerate((0x8000|0x4000|0x0001,0x0002,0x0004)):
            events[i].type = 0
            events[i].mi = MOUSEINPUT(ax if i==0 else 0,ay if i==0 else 0,0,flags,0,0)
        self.u.SendInput.argtypes = [W.UINT,C.POINTER(INPUT),C.c_int]
        if self.u.SendInput(3,events,C.sizeof(INPUT)) != 3:
            raise WindowError('마우스 입력이 전달되지 않았습니다. 게임과 앱의 실행 권한을 확인하세요.')

"""Windows game client selection, physical-pixel capture and guarded mouse input."""
import sys
import ctypes as C
from ctypes import wintypes as W
from game_identity import is_game_window
from window_sizing import covers_monitor, fit_framed_position
from privileges import process_elevated
from mouse_sequence import deliver_click
from list_centering import smooth_move,LIST_PARK_POINT


def dpi_aware():
    if sys.platform == 'win32':
        try:
            C.windll.user32.SetProcessDpiAwarenessContext(C.c_void_p(-4))
        except (AttributeError, OSError):
            C.windll.user32.SetProcessDPIAware()


class WindowError(RuntimeError):
    def __init__(self,message,winerror=None):
        super().__init__(message)
        self.winerror=winerror


class PermissionRequired(WindowError):
    def __init__(self,rights):
        super().__init__('게임은 관리자 권한이며 현재 앱은 일반 권한입니다. 앱을 관리자 권한으로 다시 실행하세요.',winerror=5)
        self.rights=rights


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
        if hasattr(self.u,'GetDpiForWindow'):self.u.GetDpiForWindow.argtypes=[W.HWND]
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
        self.u.SetWindowLongW.argtypes = [W.HWND,C.c_int,W.LONG]
        self.u.SetForegroundWindow.argtypes = [W.HWND]
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

    def permission_status(self,hwnd=None):
        pid=W.DWORD()
        if hwnd:self.u.GetWindowThreadProcessId(hwnd,C.byref(pid))
        return {'app_admin':process_elevated(),'game_admin':process_elevated(pid.value) if pid.value else None}

    def require_control_permission(self,hwnd):
        rights=self.permission_status(hwnd)
        if rights['app_admin'] is False and rights['game_admin'] is True:
            raise PermissionRequired(rights)
        return rights

    def monitor_info(self, hwnd):
        class MONITORINFO(C.Structure):
            _fields_ = [('cbSize',W.DWORD),('rcMonitor',W.RECT),('rcWork',W.RECT),('dwFlags',W.DWORD)]
        info=MONITORINFO();info.cbSize=C.sizeof(info)
        self.u.GetMonitorInfoW.argtypes=[W.HANDLE,C.POINTER(MONITORINFO)]
        if not self.u.GetMonitorInfoW(self.u.MonitorFromWindow(hwnd,2),C.byref(info)):
            raise WindowError('모니터 정보를 읽지 못했습니다.')
        rect=lambda r:(r.left,r.top,r.right,r.bottom)
        return rect(info.rcMonitor),rect(info.rcWork)

    def desktop_bounds(self):
        # Query live Win32 metrics rather than MSS's cached monitor layout.
        x,y=self.u.GetSystemMetrics(76),self.u.GetSystemMetrics(77)
        w,h=self.u.GetSystemMetrics(78),self.u.GetSystemMetrics(79)
        if w<=0 or h<=0:raise WindowError('현재 모니터 영역을 확인할 수 없습니다.')
        return x,y,x+w,y+h

    def diagnostics(self, hwnd):
        title,path=self.identity(hwnd)
        outer=W.RECT();self.u.GetWindowRect(hwnd,C.byref(outer))
        client=W.RECT();self.u.GetClientRect(hwnd,C.byref(client))
        style=self.u.GetWindowLongW(hwnd,-16)&0xffffffff
        monitor,work=self.monitor_info(hwnd)
        dpi=self.u.GetDpiForWindow(hwnd) if hasattr(self.u,'GetDpiForWindow') else 96
        box=(outer.left,outer.top,outer.right,outer.bottom)
        return {'title':title,'executable':path,'client':[client.right,client.bottom],
                'outer':box,'style':hex(style),'dpi':dpi,'monitor':monitor,'work':work,
                'fullscreen_like':covers_monitor(box,monitor),'minimized':bool(self.u.IsIconic(hwnd)),
                'permissions':self.permission_status(hwnd)}

    def prepare_resize(self, hwnd):
        self.ensure_game(hwnd)
        self.require_control_permission(hwnd)
        self.u.ShowWindow(hwnd,9)
        info=self.diagnostics(hwnd)
        if info['fullscreen_like']:
            self.u.SetForegroundWindow(hwnd)
        return info

    def toggle_fullscreen(self, hwnd):
        self.ensure_game(hwnd)
        if not self.active(hwnd):
            raise WindowError('전체 화면 전환을 위해 게임을 활성화하지 못했습니다. 게임을 한 번 클릭한 뒤 다시 맞추기를 눌러 주세요.')
        class KEYBDINPUT(C.Structure):
            _fields_=[('wVk',W.WORD),('wScan',W.WORD),('dwFlags',W.DWORD),('time',W.DWORD),('dwExtraInfo',C.c_size_t)]
        class MOUSEINPUT(C.Structure):
            _fields_=[('dx',W.LONG),('dy',W.LONG),('mouseData',W.DWORD),('dwFlags',W.DWORD),('time',W.DWORD),('dwExtraInfo',C.c_size_t)]
        class U(C.Union):
            _fields_=[('ki',KEYBDINPUT),('mi',MOUSEINPUT)]
        class INPUT(C.Structure):
            _anonymous_=('union',)
            _fields_=[('type',W.DWORD),('union',U)]
        events=(INPUT*4)()
        for i,(vk,flags) in enumerate([(0x12,0),(0x0D,0),(0x0D,2),(0x12,2)]):
            events[i].type=1;events[i].ki=KEYBDINPUT(vk,0,flags,0,0)
        self.u.SendInput.argtypes=[W.UINT,C.POINTER(INPUT),C.c_int]
        if self.u.SendInput(4,events,C.sizeof(INPUT))!=4:
            # Release modifiers even if only a prefix of the batch was accepted.
            self.u.SendInput(2,C.cast(C.byref(events,2*C.sizeof(INPUT)),C.POINTER(INPUT)),C.sizeof(INPUT))
            raise WindowError('Alt+Enter 전환 입력이 거부되었습니다. 게임과 앱의 실행 권한 차이를 확인하세요.')

    def make_windowed(self, hwnd):
        self.ensure_game(hwnd)
        self.require_control_permission(hwnd)
        self.u.ShowWindow(hwnd,9)
        style=self.u.GetWindowLongW(hwnd,-16)&0xffffffff
        # A borderless/pop-up window needs a frame change, not just SetWindowPos.
        desired=(style&~(0x80000000|0x01000000|0x20000000))|0x00CF0000
        C.set_last_error(0)
        previous=self.u.SetWindowLongW(hwnd,-16,C.c_long(desired).value)
        error=C.get_last_error()
        if not previous and error:
            raise WindowError(f'창 모드 스타일 적용 실패 (Windows 오류 {error}). 게임과 앱의 실행 권한을 확인하세요.',winerror=error)
        if not self.u.SetWindowPos(hwnd,None,0,0,0,0,0x0001|0x0002|0x0004|0x0010|0x0020):
            error=C.get_last_error()
            self.u.SetWindowLongW(hwnd,-16,C.c_long(style).value)
            raise WindowError(f'창 테두리 전환 실패 (Windows 오류 {error}).',winerror=error)

    def resize(self, hwnd, correction=False):
        self.ensure_game(hwnd)
        self.require_control_permission(hwnd)
        self.u.ShowWindow(hwnd,9)
        style=self.u.GetWindowLongW(hwnd,-16)
        if (style&0x00C00000)!=0x00C00000:
            self.make_windowed(hwnd)
            style=self.u.GetWindowLongW(hwnd,-16)
        exstyle=self.u.GetWindowLongW(hwnd,-20)
        rect=W.RECT(0,0,800,1000)
        has_menu=bool(self.u.GetMenu(hwnd))
        adjusted=False
        if hasattr(self.u,'AdjustWindowRectExForDpi'):
            self.u.GetDpiForWindow.argtypes=[W.HWND]
            dpi=self.u.GetDpiForWindow(hwnd)
            self.u.AdjustWindowRectExForDpi.argtypes=[C.POINTER(W.RECT),W.DWORD,W.BOOL,W.DWORD,W.UINT]
            adjusted=bool(self.u.AdjustWindowRectExForDpi(C.byref(rect),style,has_menu,exstyle,dpi))
        if not adjusted:
            rect=W.RECT(0,0,800,1000)
            adjusted=bool(self.u.AdjustWindowRectEx(C.byref(rect),style,has_menu,exstyle))
        if not adjusted:
            raise WindowError('DPI와 테두리 크기 계산에 실패했습니다.')
        width,height=rect.right-rect.left,rect.bottom-rect.top
        outer=W.RECT();self.u.GetWindowRect(hwnd,C.byref(outer))
        if correction:
            _,_,cw,ch=self.rect(hwnd)
            width,height=outer.right-outer.left+800-cw,outer.bottom-outer.top+1000-ch
        monitor,work=self.monitor_info(hwnd)
        insets=(-rect.left,-rect.top,rect.right-800,rect.bottom-1000)
        if correction:
            cx,cy,cw,ch=self.rect(hwnd)
            insets=(cx-outer.left,cy-outer.top,outer.right-cx-cw,outer.bottom-cy-ch)
        try:x,y=fit_framed_position((outer.left,outer.top),(width,height),work,monitor,insets)
        except ValueError as e:raise WindowError(str(e)) from e
        if not self.u.SetWindowPos(hwnd,None,x,y,width,height,0x0004|0x0010):
            error=C.get_last_error()
            raise WindowError(f'창 크기 적용 실패 (Windows 오류 {error}). 게임이 크기 변경을 제한하거나 실행 권한이 다를 수 있습니다.',winerror=error)

    def active(self, hwnd):
        current = self.u.GetForegroundWindow()
        return bool(current and self.u.GetAncestor(current,2) == hwnd)

    def keys(self):
        return (bool(self.u.GetAsyncKeyState(0x77)&0x8000), bool(self.u.GetAsyncKeyState(0x78)&0x8000))

    def center_list_pointer(self,hwnd,cancel):
        self.ensure_game(hwnd)
        self.require_control_permission(hwnd)
        rect=self.rect(hwnd)
        left,top,width,height=rect
        if (width,height)!=(800,1000):raise WindowError('게임 화면 크기가 변경되어 중앙 이동을 중단했습니다.')
        point=W.POINT()
        self.u.GetCursorPos.argtypes=[C.POINTER(W.POINT)]
        self.u.SetCursorPos.argtypes=[C.c_int,C.c_int]
        if not self.u.GetCursorPos(C.byref(point)):raise WindowError('마우스 위치를 확인할 수 없습니다.')
        def ready():
            return not cancel.is_set() and self.active(hwnd) and self.rect(hwnd)==rect
        def emit(position):
            if not self.u.SetCursorPos(*position):raise WindowError('중앙으로 마우스를 이동하지 못했습니다.')
        return smooth_move((point.x,point.y),(left+LIST_PARK_POINT[0],top+LIST_PARK_POINT[1]),emit,ready,cancel.wait)

    def click(self, hwnd, point):
        # Recheck identity, rights and foreground before every click.
        self.ensure_game(hwnd)
        self.require_control_permission(hwnd)
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
        self.u.SendInput.argtypes = [W.UINT,C.POINTER(INPUT),C.c_int]
        self.u.SendInput.restype = W.UINT
        def send(phase):
            flags={'move':0x8000|0x4000|0x2000|0x0001,'down':0x0002,'up':0x0004}[phase]
            event=INPUT();event.type=0
            event.mi=MOUSEINPUT(ax if phase=='move' else 0,ay if phase=='move' else 0,0,flags,0,0)
            if self.u.SendInput(1,C.byref(event),C.sizeof(INPUT))!=1:
                raise WindowError('마우스 입력이 전달되지 않았습니다. 게임과 앱의 실행 권한을 확인하세요.')
        if not deliver_click(send,lambda:self.active(hwnd)):
            raise WindowError('버튼 확인 중 게임 창이 비활성화되어 클릭을 보류했습니다.')

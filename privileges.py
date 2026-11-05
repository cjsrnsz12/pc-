"""Read process elevation and explain permission failures; never elevate silently."""
import ctypes as C
from ctypes import wintypes as W
from pathlib import Path
import sys


def process_elevated(pid=None):
    if sys.platform!='win32':return None
    k=C.WinDLL('kernel32',use_last_error=True)
    a=C.WinDLL('advapi32',use_last_error=True)
    k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];k.OpenProcess.restype=W.HANDLE
    k.GetCurrentProcess.restype=W.HANDLE;k.CloseHandle.argtypes=[W.HANDLE]
    a.OpenProcessToken.argtypes=[W.HANDLE,W.DWORD,C.POINTER(W.HANDLE)]
    a.GetTokenInformation.argtypes=[W.HANDLE,C.c_int,W.LPVOID,W.DWORD,C.POINTER(W.DWORD)]
    handle=k.GetCurrentProcess() if pid is None else k.OpenProcess(0x1000,False,pid)
    if not handle:return None
    token=W.HANDLE()
    try:
        if not a.OpenProcessToken(handle,0x0008,C.byref(token)):return None
        try:
            elevated=W.DWORD();size=W.DWORD()
            if not a.GetTokenInformation(token,20,C.byref(elevated),C.sizeof(elevated),C.byref(size)):return None
            return bool(elevated.value)
        finally:k.CloseHandle(token)
    finally:
        if pid is not None:k.CloseHandle(handle)


def permission_advice(operation, app_admin, game_admin=None, error_code=None, file_access=False):
    status=lambda v:'관리자' if v is True else '일반' if v is False else '확인 불가'
    levels=f'현재 앱: {status(app_admin)} / 게임: {status(game_admin)}'
    mismatch=app_admin is False and game_admin is True
    if file_access:
        return {'title':'저장 폴더 쓰기 권한 안내','levels':levels,'can_elevate':False,
                'message':'업데이트 파일을 저장하거나 교체할 폴더에 쓰기 권한이 필요합니다.\n\n앱을 다운로드·바탕 화면 등 사용자 폴더로 옮겨 다시 실행하세요. 파일만 받기를 사용할 때는 저장 가능한 폴더를 선택하세요.\n\nWindows 보안이 별도로 차단 알림을 표시한 경우 그 알림의 대상 파일과 차단 이유를 확인하세요.'}
    if mismatch or (error_code==5 and app_admin is False):
        confirmed='게임은 관리자 권한인데 현재 앱은 일반 권한입니다.' if mismatch else 'Windows가 창 변경 요청을 액세스 거부(오류 5)로 차단했습니다. 권한 차이가 원인일 수 있습니다.'
        return {'title':'Windows 관리자 권한 안내','levels':levels,'can_elevate':True,
                'message':confirmed+'\n\n관리자 권한으로 실행 중인 게임의 창 크기를 변경하거나 클릭하려면 앱도 같은 권한으로 실행해야 합니다.\n\n아래 관리자 권한으로 다시 실행을 누른 뒤 Windows 사용자 계정 컨트롤(UAC)에서 예를 선택하세요. 직접 하려면 앱을 종료하고 EXE를 우클릭 → 관리자 권한으로 실행을 선택하세요.\n\n승인은 Windows 창에서 사용자가 직접 선택합니다.'}
    if error_code==5:
        return {'title':'Windows 액세스 거부 안내','levels':levels,'can_elevate':False,
                'message':'Windows 오류 5(액세스 거부)가 확인되었습니다.\n\n'+('현재 앱은 이미 관리자 권한입니다. 추가 관리자 권한을 반복해서 줄 필요는 없습니다.' if app_admin is True else '현재 프로그램의 권한을 확인하지 못했습니다. 앱 EXE의 관리자 권한으로 실행 여부를 확인하세요.')+'\n\n게임의 창 변경 제한이나 보안 정책이 원인일 수도 있습니다. 게임을 재실행한 뒤 다시 확인하고, 계속 실패하면 기록 폴더의 app.log를 확인하세요.'}
    if game_admin is None:
        message='게임 권한을 확인하지 못했습니다. 게임이 실행 중인지 확인하세요. 창 맞추기나 시작에서 권한 오류가 발생하면 해당 원인에 맞춰 다시 안내합니다.'
    else:
        message='확인된 앱·게임 권한 사이에 관리자 권한 차단 조건은 없습니다. 현재 상태에서는 추가 관리자 권한이 필요한 것으로 판단되지 않습니다.\n\n실제 작업 중 액세스 거부가 발생하면 원인과 조치를 별도로 안내합니다.'
    return {'title':operation+' 권한 확인','levels':levels,'can_elevate':False,'message':message}


def relaunch_admin(executable):
    if sys.platform!='win32':raise OSError('Windows에서만 사용할 수 있습니다.')
    target=Path(executable).resolve()
    class SHELLEXECUTEINFOW(C.Structure):
        _fields_=[('cbSize',W.DWORD),('fMask',W.ULONG),('hwnd',W.HWND),('lpVerb',W.LPCWSTR),
                  ('lpFile',W.LPCWSTR),('lpParameters',W.LPCWSTR),('lpDirectory',W.LPCWSTR),
                  ('nShow',C.c_int),('hInstApp',W.HINSTANCE),('lpIDList',W.LPVOID),
                  ('lpClass',W.LPCWSTR),('hkeyClass',W.HKEY),('dwHotKey',W.DWORD),
                  ('hIcon',W.HANDLE),('hProcess',W.HANDLE)]
    shell=C.WinDLL('shell32',use_last_error=True)
    shell.ShellExecuteExW.argtypes=[C.POINTER(SHELLEXECUTEINFOW)]
    info=SHELLEXECUTEINFOW();info.cbSize=C.sizeof(info);info.fMask=0x40
    info.lpVerb='runas';info.lpFile=str(target);info.lpDirectory=str(target.parent);info.nShow=1
    if not shell.ShellExecuteExW(C.byref(info)):
        error=C.get_last_error()
        if error==1223:return False
        raise OSError(error,'Windows 관리자 권한 재실행을 시작하지 못했습니다.')
    if info.hProcess:
        k=C.WinDLL('kernel32');k.CloseHandle.argtypes=[W.HANDLE];k.CloseHandle(info.hProcess)
    return True

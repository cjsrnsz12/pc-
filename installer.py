"""Console-free, out-of-process replacement of the running Windows executable."""
import ctypes
from branding import APP_NAME
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0


class InstallError(RuntimeError):
    pass


def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def validate_plan(plan, session):
    session=Path(session).resolve()
    if plan.get('format')!=1 or not re.fullmatch(r'v?\d+\.\d+\.\d+',str(plan.get('version',''))):
        raise InstallError('업데이트 계획을 확인할 수 없습니다.')
    for name in ['staged','helper','ready','status']:
        if Path(plan[name]).resolve().parent!=session:
            raise InstallError('업데이트 임시 파일 위치가 올바르지 않습니다.')
    target=Path(plan['target']).resolve()
    if target.suffix.lower()!='.exe' or target.parent==session:
        raise InstallError('업데이트 대상 실행 파일이 올바르지 않습니다.')
    if not isinstance(plan.get('parent_pid'),int) or plan['parent_pid']<=0:
        raise InstallError('기존 앱의 프로세스 정보를 확인할 수 없습니다.')
    for key in ['old_sha256','new_sha256']:
        if not re.fullmatch('[a-f0-9]{64}',plan.get(key,'')):
            raise InstallError('실행 파일 검증 정보가 없습니다.')
    return plan


def prepare_install(staged, target, version, parent_pid):
    staged,target=Path(staged).resolve(),Path(target).resolve()
    session=staged.parent
    if not staged.is_file() or not target.is_file() or staged==target:
        raise InstallError('업데이트 실행 파일을 찾을 수 없습니다.')
    with staged.open('rb') as f:
        if f.read(2)!=b'MZ':raise InstallError('올바른 실행 파일이 아닙니다.')
    # Fail before closing the app if the installation directory is not writable.
    probe=target.parent/('.abyss-probe-'+uuid.uuid4().hex)
    try:
        with probe.open('xb') as f:f.write(b'')
    except OSError as e:
        raise InstallError('앱 폴더에 쓰기 권한이 없습니다. 사용자 폴더로 앱을 옮겨 실행한 뒤 업데이트하세요.') from e
    finally:probe.unlink(missing_ok=True)
    if shutil.disk_usage(target.parent).free<staged.stat().st_size*2+10*1024*1024:
        raise InstallError('업데이트할 디스크의 여유 공간이 부족합니다.')
    if shutil.disk_usage(session).free<target.stat().st_size+10*1024*1024:
        raise InstallError('업데이트 임시 폴더의 여유 공간이 부족합니다.')
    helper=session/'Updater.exe'
    shutil.copyfile(target,helper)
    plan={'format':1,'version':version,'parent_pid':parent_pid,'target':str(target),
          'staged':str(staged),'helper':str(helper),'ready':str(session/'ready.json'),
          'status':str(session/'status.json'),'old_sha256':sha256(target),'new_sha256':sha256(staged)}
    validate_plan(plan,session)
    path=session/'plan.json'
    path.write_text(json.dumps(plan,ensure_ascii=False),encoding='utf-8')
    return path


def launch_installer(plan_path):
    path=Path(plan_path).resolve()
    plan=validate_plan(json.loads(path.read_text(encoding='utf-8')),path.parent)
    return subprocess.Popen([plan['helper'],'--apply-update',str(path)],creationflags=NO_WINDOW,close_fds=True)


def wait_for_exit(pid, timeout=90):
    if sys.platform!='win32':raise InstallError('Windows에서만 실행할 수 있습니다.')
    from ctypes import wintypes as W
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];k.OpenProcess.restype=W.HANDLE
    k.WaitForSingleObject.argtypes=[W.HANDLE,W.DWORD];k.CloseHandle.argtypes=[W.HANDLE]
    h=k.OpenProcess(0x00100000,False,pid)
    if not h:
        if ctypes.get_last_error()==87:return
        raise InstallError('기존 앱의 종료를 확인할 권한이 없습니다.')
    try:
        if k.WaitForSingleObject(h,int(timeout*1000))!=0:
            raise InstallError('기존 앱이 종료되지 않아 업데이트를 보류했습니다.')
    finally:k.CloseHandle(h)


def replace_retry(source,destination,timeout=20):
    end=time.monotonic()+timeout
    while True:
        try:os.replace(source,destination);return
        except PermissionError:
            if time.monotonic()>=end:raise
            time.sleep(.25)


def start_and_confirm(plan, test_exit=False):
    ready=Path(plan['ready']);ready.unlink(missing_ok=True)
    args=[plan['target'],'--update-ready',str(ready)]
    if test_exit:args.append('--update-test-exit')
    process=subprocess.Popen(args,creationflags=NO_WINDOW,close_fds=True,cwd=str(Path(plan['target']).parent))
    end=time.monotonic()+60
    while time.monotonic()<end:
        try:
            report=json.loads(ready.read_text(encoding='utf-8'))
            if report.get('ok') and report.get('version','').lstrip('v')==plan['version'].lstrip('v'):
                return True
        except (OSError,ValueError):pass
        if process.poll() is not None:return False
        time.sleep(.2)
    if process.poll() is None:
        # Kill only the child tree launched above; do not leave a locked failed EXE.
        subprocess.run(['taskkill.exe','/PID',str(process.pid),'/T','/F'],creationflags=NO_WINDOW,
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15,check=False)
        process.wait(timeout=15)
    return False


def install_transaction(plan, confirm=start_and_confirm):
    target=Path(plan['target']);staged=Path(plan['staged'])
    if sha256(staged)!=plan['new_sha256'] or sha256(target)!=plan['old_sha256']:
        raise InstallError('파일이 변경되어 업데이트를 중단했습니다. 다시 확인하세요.')
    token=uuid.uuid4().hex
    pending=target.parent/('.abyss-new-'+token+'.exe')
    backup=target.parent/('.abyss-backup-'+token+'.exe')
    moved=False
    try:
        shutil.copyfile(staged,pending)
        if sha256(pending)!=plan['new_sha256']:raise InstallError('복사한 파일 검증에 실패했습니다.')
        replace_retry(target,backup);moved=True
        replace_retry(pending,target)
        if not confirm(plan):raise InstallError('새 버전 시작을 확인하지 못해 이전 버전으로 복구했습니다.')
        try:backup.unlink(missing_ok=True)
        except OSError:pass
        return target
    except Exception:
        if moved:
            try:replace_retry(backup,target)
            except OSError as e:
                raise InstallError('자동 복구를 완료하지 못했습니다. 이전 파일 위치: '+str(backup)) from e
        raise
    finally:pending.unlink(missing_ok=True)


def apply_plan(path):
    path=Path(path).resolve()
    plan=None;old_exited=False
    try:
        plan=validate_plan(json.loads(path.read_text(encoding='utf-8')),path.parent)
        if Path(sys.executable).resolve()!=Path(plan['helper']).resolve():
            raise InstallError('업데이트 보조 프로그램의 위치가 일치하지 않습니다.')
        wait_for_exit(plan['parent_pid']);old_exited=True
        install_transaction(plan,lambda p:start_and_confirm(p,test_exit=bool(p.get('test_exit'))))
        Path(plan['status']).write_text(json.dumps({'result':'success','version':plan['version']}),encoding='utf-8')
        Path(plan['staged']).unlink(missing_ok=True)
        return 0
    except Exception as e:
        message=str(e)
        if plan:
            Path(plan['status']).write_text(json.dumps({'result':'failed','message':message},ensure_ascii=False),encoding='utf-8')
        if sys.platform=='win32' and not (plan and plan.get('test_exit')):
            ctypes.windll.user32.MessageBoxW(None,message,APP_NAME+' 업데이트',0x10)
            if old_exited and plan and Path(plan['target']).is_file() and sha256(plan['target'])==plan['old_sha256']:
                subprocess.Popen([plan['target']],creationflags=NO_WINDOW,close_fds=True)
        return 1


def cleanup_updates(root):
    root=Path(root)
    if not root.exists():return
    for folder in root.glob('session-*'):
        if not folder.is_dir() or not (folder/'status.json').is_file():continue
        try:shutil.rmtree(folder)
        except OSError:pass  # A still-running updater owns this session; try next launch.


def integration_owner(session):
    from version import VERSION
    session=Path(session)
    path=prepare_install(session/'new.exe',sys.executable,VERSION,os.getpid())
    plan=json.loads(path.read_text(encoding='utf-8'));plan['test_exit']=True
    path.write_text(json.dumps(plan),encoding='utf-8')
    launch_installer(path)


def integration_self_test(report_path):
    """Real EXE → separate helper → replacement → GUI ready receipt on Windows."""
    from version import VERSION
    root=Path(os.getenv('LOCALAPPDATA',str(Path.home())))/'AbyssHelper'/'updates'
    session=root/('session-'+uuid.uuid4().hex);session.mkdir(parents=True)
    target_dir=root/('test-target-'+uuid.uuid4().hex);target_dir.mkdir()
    target=target_dir/'AbyssHelper.exe'
    report={'ok':False}
    try:
        shutil.copyfile(sys.executable,target)
        shutil.copyfile(sys.executable,session/'new.exe')
        owner=subprocess.Popen([str(target),'--test-update-owner',str(session)],creationflags=NO_WINDOW,close_fds=True)
        end=time.monotonic()+150
        while time.monotonic()<end:
            status=session/'status.json'
            if status.exists():
                result=json.loads(status.read_text(encoding='utf-8'))
                if result.get('result')!='success':raise InstallError(result.get('message','업데이트 검사 실패'))
                ready=json.loads((session/'ready.json').read_text(encoding='utf-8'))
                if ready.get('version')!=VERSION:raise InstallError('재실행 버전이 다릅니다.')
                owner.wait(timeout=10)
                report={'ok':True,'version':VERSION,'replacement':'success','restart_ui':'ready','owner_exit':owner.returncode}
                time.sleep(3)
                return 0
            time.sleep(.25)
        raise InstallError('업데이트 전체 경로 검사 시간 초과')
    except Exception as e:
        report={'ok':False,'error':str(e)}
        return 1
    finally:
        Path(report_path).write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8')
        shutil.rmtree(target_dir,ignore_errors=True)
        shutil.rmtree(session,ignore_errors=True)

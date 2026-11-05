"""Run on Windows to create the console-free executable."""
import subprocess
import sys
from pathlib import Path

if sys.platform != 'win32':
    raise SystemExit('Windows 환경에서 실행하세요. GitHub Actions에서도 자동 빌드됩니다.')
subprocess.check_call([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed',
                      '--name','AbyssHelper','--add-data','assets.json;.',
                      '--version-file','version_info.txt','app.py'],cwd=Path(__file__).parent)

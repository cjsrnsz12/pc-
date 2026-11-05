"""Run on Windows to create the console-free executable."""
import subprocess
import sys
from pathlib import Path

if sys.platform != 'win32':
    raise SystemExit('Windows 환경에서 실행하세요. GitHub Actions에서도 자동 빌드됩니다.')
from ui_theme import app_icon
app_icon(256).save(Path(__file__).parent/'build_icon.ico',format='ICO',sizes=[(16,16),(32,32),(48,48),(64,64),(256,256)])
subprocess.check_call([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed',
                      '--icon','build_icon.ico','--name','AbyssHelper','--add-data','assets.json;.','--add-data','release_notes.md;.',
                      '--version-file','version_info.txt','app.py'],cwd=Path(__file__).parent)

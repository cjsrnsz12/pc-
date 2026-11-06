"""A bounded local snapshot of the selected game client; no upload or desktop capture."""
import json
from pathlib import Path
import cv2
from datetime import datetime
from log_retention import LOG_FILENAME,retained_text,cleanup_artifacts


def save_failure(directory,frame,metadata):
    if frame.shape[:2]!=(1000,800):raise ValueError('게임 영역 800×1000만 진단으로 저장합니다.')
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    ok,png=cv2.imencode('.png',frame)
    if not ok:raise OSError('진단 화면 저장에 실패했습니다.')
    image=directory/'last-unrecognized.png';info=directory/'last-unrecognized.json'
    staged_image=directory/'image.tmp';staged_info=directory/'metadata.tmp'
    staged_image.write_bytes(png.tobytes())
    staged_info.write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    staged_image.replace(image);staged_info.replace(info)
    return image,info




def create_bundle(directory,destination=None):
    import zipfile
    directory=Path(directory)
    now=datetime.now();cleanup_artifacts(directory,now)
    destination=Path(destination) if destination else directory/'로그 파일.zip'
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=destination.with_name(destination.name+'.tmp')
    primary=directory/LOG_FILENAME
    if not primary.exists():primary=directory/'app.log'
    with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as archive:
        if primary.is_file():archive.writestr(LOG_FILENAME,retained_text(primary.read_text(encoding='utf-8-sig',errors='replace'),now))
        for i in range(1,4):
            rotated=primary.with_name(primary.name+'.'+str(i))
            if rotated.is_file():
                kept=retained_text(rotated.read_text(encoding='utf-8-sig',errors='replace'),now)
                if kept:archive.writestr(LOG_FILENAME+'.'+str(i),kept)
        for source,name in [('last-unrecognized.png','오류 화면.png'),('last-unrecognized.json','오류 정보.json')]:
            path=directory/'diagnostics'/source
            if path.is_file():archive.write(path,name)
    temporary.replace(destination)
    return destination

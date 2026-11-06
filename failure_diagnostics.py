"""A bounded local snapshot of the selected game client; no upload or desktop capture."""
import json
from pathlib import Path
import cv2


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

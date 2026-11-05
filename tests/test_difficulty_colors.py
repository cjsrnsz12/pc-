"""Regression: actual selected purple/gold/red chips, including overlapping labels."""
import base64
import json
from pathlib import Path
import cv2
import numpy as np
import pytest
from vision import Vision, DIFFICULTIES, DIFFICULTY_BOXES

ROOT=Path(__file__).resolve().parents[1]
CHIPS=json.loads((Path(__file__).parent/'fixtures/difficulty_chips.json').read_text(encoding='utf-8'))

def frame_with(*titles):
    frame=np.full((1000,800,3),40,np.uint8)
    for title,box in zip(DIFFICULTIES,DIFFICULTY_BOXES):
        chip=cv2.imdecode(np.frombuffer(base64.b64decode(CHIPS[title]),np.uint8),cv2.IMREAD_COLOR)
        hsv=cv2.cvtColor(chip,cv2.COLOR_BGR2HSV)
        x,y,w,h=cv2.boundingRect(cv2.findNonZero(((hsv[:,:,1]>140)&(hsv[:,:,2]>120)).astype('uint8')))
        chip=chip[y:y+h,x:x+w]
        if title not in titles:chip=cv2.cvtColor(cv2.cvtColor(chip,cv2.COLOR_BGR2GRAY),cv2.COLOR_GRAY2BGR)
        x1,y1,x2,y2=box
        frame[y1+2:y2-2,x1+1:x2-1]=cv2.resize(chip,(x2-x1-2,y2-y1-4))
    return frame

def detect(frame):
    v=Vision(ROOT/'assets.json');v.frame=frame;v.gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
    return v

@pytest.mark.parametrize('title',DIFFICULTIES)
def test_selected_color_exact_label(title):
    v=detect(frame_with(title))
    assert v.difficulty_selection(title)[0]==title

def test_ambiguous_and_grey_tabs_cannot_allow_entry():
    assert detect(frame_with()).difficulty_selection('입문')[0]==''
    assert detect(frame_with('입문','매우 어려움')).difficulty_selection('입문')[0]==''

def test_difficulty_text_searches_do_not_overlap():
    v=Vision(ROOT/'assets.json')
    for title,box in zip(DIFFICULTIES,DIFFICULTY_BOXES):
        assert v.data['diff_'+title]['roi']==list(box)

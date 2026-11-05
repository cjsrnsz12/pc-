from pathlib import Path
import cv2
import numpy as np
from vision import Vision, Stillness

ASSETS=Path(__file__).resolve().parents[1]/'assets.json'


def test_unknown_black_screen_never_becomes_gameplay():
    v=Vision(ASSETS)
    assert v.observe(np.zeros((1000,800,3),np.uint8),'허상의 정박지','매우 어려움').screen=='unknown'


def test_clear_needs_both_texts():
    v=Vision(ASSETS)
    f=np.zeros((1000,800,3),np.uint8)
    def put(name,x,y):
        t=v.templates[name][0];h,w=t.shape
        f[y:y+h,x:x+w]=cv2.cvtColor(t,cv2.COLOR_GRAY2BGR)
    put('clear',299,216)
    assert v.observe(f,'허상의 정박지','매우 어려움').screen!='clear'
    put('touch',315,939)
    assert v.observe(f,'허상의 정박지','매우 어려움').screen=='clear'


def test_stillness_ignores_chat_but_resets_for_ground_movement():
    rng=np.random.default_rng(5)
    frame=rng.integers(0,256,(1000,800,3),np.uint8)
    s=Stillness()
    assert not s.update(frame)
    assert s.update(frame)
    chat=frame.copy();chat[700:800,0:200]=0
    assert s.update(chat)
    shifted=cv2.warpAffine(frame,np.float32([[1,0,14],[0,1,0]]),(800,1000))
    assert not s.update(shifted)

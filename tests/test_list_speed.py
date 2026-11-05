from pathlib import Path
import cv2
import numpy as np
import pytest
from engine import Controller,Observation
from vision import Vision,DUNGEONS
from recognition_timing import poll_interval,same_detection

ASSETS=Path(__file__).resolve().parents[1]/'assets.json'

def list_frame(key,overlay=False):
    v=Vision(ASSETS);frame=np.zeros((1000,800,3),np.uint8)
    def put(name,x,y):
        t=v.templates[name][0];h,w=t.shape
        frame[y:y+h,x:x+w]=cv2.cvtColor(t,cv2.COLOR_GRAY2BGR)
    put('list_title',57,49);put('list_'+key,195,510)
    if overlay:put('matching',145,550)
    return frame

@pytest.mark.parametrize('title,key',DUNGEONS.items())
def test_list_uses_requested_name_and_skips_detail_search(monkeypatch,title,key):
    v=Vision(ASSETS);called=[];hit=v.hit
    def tracked(name):called.append(name);return hit(name)
    monkeypatch.setattr(v,'hit',tracked)
    o=v.observe(list_frame(key),title,'입문')
    assert o.screen=='list' and o.points['dungeon'][0]>=195
    assert 'enter' not in called and 'loading_name' not in called
    wrong=next(name for name in DUNGEONS if name!=title)
    assert v.observe(list_frame(key),wrong,'입문').screen!='list'

def test_matching_overlay_keeps_priority_over_list():
    v=Vision(ASSETS)
    assert v.observe(list_frame('harbor',overlay=True),'허상의 정박지','입문').screen=='matching'

def test_moving_list_target_requires_fresh_confirmation():
    a=Observation('list',{'dungeon':(240,520)})
    assert not same_detection(None,a)
    assert same_detection(a,Observation('list',{'dungeon':(243,523)}))
    assert not same_detection(a,Observation('list',{'dungeon':(240,550)}))

def test_faster_menu_transition_still_bounds_retries_and_combat_polling():
    c=Controller()
    assert c.step(Observation('menu',{'abyss':(525,480)}),0).key=='abyss'
    target=Observation('list',{'dungeon':(240,520)})
    assert c.step(target,.19) is None
    assert c.step(target,.27).key=='dungeon'
    assert c.step(target,.7) is None
    assert c.step(target,2.76) is None
    assert c.step(target,2.77).key=='dungeon'
    assert poll_interval('list')==.07 and poll_interval('menu')==.07
    assert poll_interval('combat')==.25

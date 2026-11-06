from pathlib import Path
import cv2
import numpy as np
import pytest
from vision import Vision
from engine import Controller,Observation,State

ROOT=Path(__file__).resolve().parents[1]

def put(v,frame,name,point,scale):
    text=cv2.resize(v.templates[name][0],None,fx=scale,fy=scale)
    h,w=text.shape;x,y=point
    frame[y:y+h,x:x+w]=cv2.cvtColor(text,cv2.COLOR_GRAY2BGR)
    return x+w//2,y+h//2

@pytest.mark.parametrize('scale',[.8,1.1,1.25])
def test_scaled_reward_is_found_at_actual_current_button_positions(scale):
    v=Vision(ROOT/'assets.json');f=np.zeros((1000,800,3),np.uint8)
    target=put(v,f,'retry',(360,820),scale);put(v,f,'exit',(120,820),scale)
    o=v.observe(f,'허상의 정박지','매우 어려움',after_clear=True)
    assert o.screen=='reward' and o.points['retry']==target
    c=Controller();c.step(Observation('clear'),0)
    assert c.step(o,1).point==target


def test_partial_result_cannot_click_and_clear_context_survives_transient_combat():
    v=Vision(ROOT/'assets.json');f=np.zeros((1000,800,3),np.uint8)
    put(v,f,'retry',(360,820),1.25)
    assert v.observe(f,'허상의 정박지','매우 어려움',after_clear=True).screen!='reward'
    c=Controller();assert c.step(Observation('clear'),0).key=='clear'
    assert c.step(Observation('combat'),1) is None and c.clear_clicked
    assert c.state==State.CLEAR


def test_verified_dungeon_list_after_clear_can_resume_selection():
    c=Controller();c.step(Observation('clear'),0)
    o=Observation('list',{'dungeon':(240,520)},dungeon='허상의 정박지')
    assert c.step(o,1).key=='dungeon'
    assert not c.combat_latched and not c.clear_clicked


def test_scaled_clear_and_touch_are_both_required():
    v=Vision(ROOT/'assets.json');f=np.zeros((1000,800,3),np.uint8)
    put(v,f,'clear',(230,180),1.25)
    assert v.observe(f,'허상의 정박지','매우 어려움').screen!='clear'
    put(v,f,'touch',(240,840),1.25)
    assert v.observe(f,'허상의 정박지','매우 어려움').screen=='clear'


def test_matching_popup_has_priority_over_reward_background():
    v=Vision(ROOT/'assets.json');f=np.zeros((1000,800,3),np.uint8)
    put(v,f,'retry',(360,930),1);put(v,f,'exit',(120,930),1)
    put(v,f,'matching',(145,550),1)
    assert v.observe(f,'허상의 정박지','매우 어려움',after_clear=True).screen=='matching'

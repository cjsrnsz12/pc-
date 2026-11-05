import base64
import json
from pathlib import Path
import cv2
import numpy as np
from engine import Controller, Observation, State
from vision import Vision

ROOT=Path(__file__).resolve().parents[1]

def hud(food=True,objective=True):
    frame=np.zeros((1000,800,3),np.uint8)
    patches=json.loads((Path(__file__).parent/'fixtures/food_hud.json').read_text())
    for index,patch in enumerate(patches):
        if (index==1 and not food) or (index==2 and not objective):continue
        x1,y1,x2,y2=patch['box']
        frame[y1:y2,x1:x2]=cv2.imdecode(np.frombuffer(base64.b64decode(patch['png']),np.uint8),cv2.IMREAD_COLOR)
    return frame

def test_food_above_buff_row_with_collapsed_skills_is_eaten_once():
    v=Vision(ROOT/'assets.json');frame=hud()
    assert not v.combat_hud(frame)
    o=v.observe(frame,'허상의 정박지','매우 어려움')
    assert o.screen=='combat' and o.food
    assert 190<=o.points['food'][0]<=225 and 70<=o.points['food'][1]<=100
    c=Controller()
    assert c.step(o,0).key=='food'
    assert c.state==State.COMBAT
    for t in (1,4,11,20):assert c.step(o,t) is None
    assert c.step(v.observe(hud(food=False),'허상의 정박지','매우 어려움'),21) is None
    assert c.step(o,22).key=='food'

def test_objective_without_food_never_clicks_food_or_opens_menu():
    v=Vision(ROOT/'assets.json');c=Controller()
    for t in range(8):
        o=v.observe(hud(food=False),'허상의 정박지','매우 어려움')
        assert o.screen=='combat' and not o.food
        assert c.step(o,t) is None

def test_food_icon_alone_cannot_prove_combat_or_valid_hud():
    frame=hud(objective=False);frame[92:105,80:170]=0
    assert Vision(ROOT/'assets.json').observe(frame,'허상의 정박지','매우 어려움').screen=='unknown'

def test_field_food_precedes_menu_after_stillness_timer():
    c=Controller();c.step(Observation('field',{'menu':(770,65)},still=True),0)
    o=Observation('field',{'food':(207,85),'menu':(770,65)},still=True,food=True)
    assert c.step(o,5).key=='food'

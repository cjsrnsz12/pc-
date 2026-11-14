import base64
import json
from pathlib import Path
from types import SimpleNamespace
import cv2
import numpy as np
import pytest
from food_templates import selected_food_kind
from vision import Vision
from raid import RaidVision, RaidController
from engine import Controller

ROOT=Path(__file__).resolve().parents[1]

def scene(raid=False,food='snack',scale=1.):
    name='raid-reference.json' if raid else 'food_hud.json'
    patches=json.loads((ROOT/'tests/fixtures'/name).read_text())
    if raid:patches=patches['inside']
    frame=np.zeros((1000,800,3),np.uint8)
    for i,p in enumerate(patches):
        if i==1 and food!='snack':continue
        x,y,x2,y2=p['box'];frame[y:y2,x:x2]=cv2.imdecode(np.frombuffer(base64.b64decode(p['png']),np.uint8),cv2.IMREAD_COLOR)
    if food=='egg':
        reference=json.loads((ROOT/'tests/fixtures/food-egg-reference.json').read_text())
        egg=cv2.imdecode(np.frombuffer(base64.b64decode(reference['png']),np.uint8),cv2.IMREAD_COLOR)
        egg=cv2.resize(egg,None,fx=scale,fy=scale);h,w=egg.shape[:2]
        frame[85-h//2:85-h//2+h,207-w//2:207-w//2+w]=egg
    return frame

@pytest.mark.parametrize('raid',[False,True])
@pytest.mark.parametrize('size',[(800,1000),(784,980),(640,800)])
@pytest.mark.parametrize('kind',['none','snack','egg'])
@pytest.mark.parametrize('shown',['snack','egg','absent'])
def test_only_the_selected_food_is_detected(raid,size,kind,shown):
    detector=(RaidVision if raid else Vision)(ROOT/'assets.json',food_kind=kind)
    o=detector.observe(cv2.resize(scene(raid,shown),size),'카브락' if raid else '허상의 정박지','입문' if raid else '매우 어려움')
    assert o.food==(kind==shown and kind!='none')
    assert ('food' in o.points)==o.food
    if o.food:assert abs(o.points['food'][0]-207)<12 and abs(o.points['food'][1]-85)<12

@pytest.mark.parametrize('raid',[False,True])
@pytest.mark.parametrize('scale',[.55,.65,.85,1.,1.15,1.35])
def test_egg_size_variants_and_one_click_per_appearance(raid,scale):
    detector=(RaidVision if raid else Vision)(ROOT/'assets.json',food_kind='egg')
    controller=RaidController() if raid else Controller()
    o=detector.observe(scene(raid,'egg',scale),'허상의 정박지','매우 어려움')
    assert o.food
    assert controller.step(o,0).key=='food'
    assert controller.step(o,15) is None
    o=detector.observe(scene(raid,'absent'),'허상의 정박지','매우 어려움');controller.step(o,16)
    o=detector.observe(scene(raid,'egg',scale),'허상의 정박지','매우 어려움')
    assert controller.step(o,17).key=='food'

@pytest.mark.parametrize('raid',[False,True])
def test_grey_egg_and_egg_without_game_hud_cannot_trigger(raid):
    detector=(RaidVision if raid else Vision)(ROOT/'assets.json',food_kind='egg')
    frame=scene(raid,'egg');frame[60:110,180:235]=cv2.cvtColor(cv2.cvtColor(frame[60:110,180:235],cv2.COLOR_BGR2GRAY),cv2.COLOR_GRAY2BGR)
    assert not detector.observe(frame,'허상의 정박지','매우 어려움').food
    frame=scene(raid,'egg');frame[80:115,80:175]=0
    assert not detector.observe(frame,'허상의 정박지','매우 어려움').food

@pytest.mark.parametrize('settings,expected',[({},'snack'),({'food':False},'none'),({'food':True},'snack'),({'food_kind':'egg'},'egg'),({'food_kind':'none'},'none'),({'food_kind':'unknown'},'none')])
def test_saved_selection_and_legacy_settings(settings,expected):
    assert selected_food_kind(settings)==expected


def test_food_selection_is_saved_immediately(tmp_path):
    import app
    class Var:
        def __init__(self,value):self.value=value
        def get(self):return self.value
        def set(self,value):self.value=value
    case=SimpleNamespace(food_kind=Var('egg'),food=Var(False),settings_path=tmp_path/'settings.json',log=lambda *a:None)
    case.collect_settings=lambda:dict(food_kind=case.food_kind.get(),food=case.food_kind.get()!='none')
    app.App.food_changed(case)
    assert case.food.get() and json.loads(case.settings_path.read_text())=={'food_kind':'egg','food':True}
    case.food_kind.set('none');app.App.food_changed(case)
    assert not case.food.get() and json.loads(case.settings_path.read_text())['food_kind']=='none'

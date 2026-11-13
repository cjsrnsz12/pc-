"""UI-only patches from the supplied v1.1.37 cave entry failure."""
import base64
import json
from pathlib import Path
import cv2
import numpy as np
import pytest
from engine import Controller,Observation as O,State
from vision import Vision,DIFFICULTIES

ROOT=Path(__file__).resolve().parents[1]

def detail():
    f=np.zeros((1000,800,3),np.uint8)
    for p in json.loads((ROOT/'tests/fixtures/detail-large-ui.json').read_text()):
        x,y,x2,y2=p['box'];f[y:y2,x:x2]=cv2.imdecode(np.frombuffer(base64.b64decode(p['png']),np.uint8),cv2.IMREAD_COLOR)
    return f

@pytest.mark.parametrize('size',[(800,1000),(784,980),(640,800)])
@pytest.mark.parametrize('requested',DIFFICULTIES)
def test_supplied_large_ui_preserves_selected_difficulty_and_target(size,requested):
    v=Vision(ROOT/'assets.json')
    o=v.observe(cv2.resize(detail(),size),'광기의 동굴',requested)
    assert (o.screen,o.dungeon,o.difficulty)==('detail','광기의 동굴','매우 어려움')
    assert o.together and o.encounter is True
    x,y=o.points['difficulty']
    left,right={'입문':(32,92),'어려움':(100,172),'매우 어려움':(180,285),'매우 어려움2':(294,410)}[requested]
    assert left<=x<=right and 190<=y<=225
    assert 360<=o.points['enter'][0]<=440 and 930<=o.points['enter'][1]<=960

@pytest.mark.parametrize('party',[False,True])
def test_supplied_detail_can_enter_without_manual_help(party):
    c=Controller('광기의 동굴','매우 어려움',party=party)
    if party:
        assert c.step(O('reward',{'other':(550,950)}),0).key=='other'
        assert c.step(O('list',{'dungeon':(225,692)},dungeon='광기의 동굴'),1).key=='dungeon'
    o=Vision(ROOT/'assets.json').observe(detail(),'광기의 동굴','매우 어려움')
    a=c.step(o,2);assert a.key=='enter' and c.state==State.ENTERING
    c.step(O('matching'),3);c.step(O('combat'),4)
    assert c.state==State.COMBAT


def test_unverified_name_and_wrong_difficulty_never_enter():
    v=Vision(ROOT/'assets.json')
    for name in ('허상의 정박지','흩어진 물길'):
        o=v.observe(detail(),name,'매우 어려움')
        c=Controller(name,'매우 어려움')
        assert c.step(o,0) is None and c.state==State.BLOCKED
    o=v.observe(detail(),'광기의 동굴','매우 어려움2')
    assert Controller('광기의 동굴','매우 어려움2').step(o,0).key=='difficulty'
    f=detail();f[140:177,20:180]=0
    assert Controller('광기의 동굴','매우 어려움').step(v.observe(f,'광기의 동굴','매우 어려움'),0) is None


def test_together_and_encounter_are_checked_in_large_ui():
    v=Vision(ROOT/'assets.json');f=detail()
    f[40:100,270:585]=cv2.cvtColor(cv2.cvtColor(f[40:100,270:585],cv2.COLOR_BGR2GRAY),cv2.COLOR_GRAY2BGR)
    o=v.observe(f,'광기의 동굴','매우 어려움')
    assert o.screen=='detail' and not o.together
    assert Controller('광기의 동굴','매우 어려움').step(o,0).key=='together'
    f=detail();f[606:631,614:660]=(100,100,100)
    cv2.circle(f,(624,618),9,(245,245,245),-1)
    o=v.observe(f,'광기의 동굴','매우 어려움')
    assert o.encounter is False
    assert Controller('광기의 동굴','매우 어려움').step(o,0).key=='encounter'
    f[606:631,614:660]=0
    o=v.observe(f,'광기의 동굴','매우 어려움')
    assert o.encounter is None
    assert Controller('광기의 동굴','매우 어려움').step(o,0) is None


def test_scale_does_not_leak_into_next_normal_frame():
    v=Vision(ROOT/'assets.json');v.observe(detail(),'광기의 동굴','매우 어려움')
    f=np.zeros((1000,800,3),np.uint8)
    for p in json.loads((ROOT/'tests/fixtures/party-reference.json').read_text())['detail']:
        x,y,x2,y2=p['box'];f[y:y2,x:x2]=cv2.imdecode(np.frombuffer(base64.b64decode(p['png']),np.uint8),cv2.IMREAD_COLOR)
    o=v.observe(f,'흩어진 물길','매우 어려움2')
    assert o.screen=='detail' and o.difficulty=='매우 어려움2' and o.together and o.encounter

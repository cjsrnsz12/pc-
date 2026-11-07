"""Shared Abyss/raid survival checks using supplied UI-only screenshots."""
import base64
import json
from pathlib import Path
import cv2
import numpy as np
import pytest
from engine import Controller,Observation,State
from raid import RaidController,RaidVision
from vision import Vision

ROOT=Path(__file__).resolve().parents[1]
PATCHES=json.loads((Path(__file__).parent/'fixtures/survival.json').read_text())

def frame(name):
    f=np.zeros((1000,800,3),np.uint8)
    for p in PATCHES[name]:
        x,y,x2,y2=p['box'];f[y:y2,x:x2]=cv2.imdecode(np.frombuffer(base64.b64decode(p['png']),np.uint8),cv2.IMREAD_COLOR)
    return f

def observe(v,f):return v.observe(f,'허상의 정박지','입문')

@pytest.mark.parametrize('cls',[Vision,RaidVision])
@pytest.mark.parametrize('size',[(800,1000),(784,980),(640,800)])
def test_death_and_text_only_revive_at_supported_sizes(cls,size):
    v=cls(ROOT/'assets.json');f=frame('dead')
    # Replace the item icon/count with unrelated pixels. Only lettering matters.
    f[810:855,415:470]=(30,140,240)
    o=observe(v,cv2.resize(f,size))
    assert o.screen=='dead' and 470<=o.points['revive'][0]<=555

@pytest.mark.parametrize('cls',[Vision,RaidVision])
def test_death_without_orange_lettered_button_never_clicks_other_revive(cls):
    v=cls(ROOT/'assets.json')
    f=frame('dead');f[810:855,470:560]=0
    o=observe(v,f);assert o.screen=='dead' and not o.points
    assert Controller().step(o,0) is None
    f=frame('dead');area=f[810:855,470:560];f[810:855,470:560]=cv2.cvtColor(cv2.cvtColor(area,cv2.COLOR_BGR2GRAY),cv2.COLOR_GRAY2BGR)
    assert 'revive' not in observe(v,f).points
    f=frame('dead');f[250:300,325:465]=0
    assert observe(v,f).screen!='dead'

@pytest.mark.parametrize('cls',[Vision,RaidVision])
@pytest.mark.parametrize('size',[(800,1000),(784,980),(640,800)])
def test_sample_low_health_with_f1_potion_only(cls,size):
    v=cls(ROOT/'assets.json')
    assert 'potion' in observe(v,cv2.resize(frame('low'),size)).points
    assert 'potion' not in observe(v,cv2.resize(frame('healthy'),size)).points

@pytest.mark.parametrize('cls',[Vision,RaidVision])
def test_missing_f1_gray_potion_and_enemy_bar_cannot_trigger_heal(cls):
    v=cls(ROOT/'assets.json')
    f=frame('low');f[747:770,245:274]=0
    assert 'potion' not in observe(v,f).points
    f=frame('low');a=f[765:810,260:305];f[765:810,260:305]=cv2.cvtColor(cv2.cvtColor(a,cv2.COLOR_BGR2GRAY),cv2.COLOR_GRAY2BGR)
    assert 'potion' not in observe(v,f).points
    f=frame('healthy');f[500:507,330:380]=(0,255,0)
    assert 'potion' not in observe(v,f).points

@pytest.mark.parametrize('cls',[Controller,RaidController])
def test_revive_retries_bounded_then_real_combat_resumes(cls):
    c=cls();c.combat_latched=True
    if isinstance(c,RaidController):c.phase='inside'
    dead=Observation('dead',{'revive':(512,832)})
    assert c.step(dead,0).key=='revive' and c.state==State.DEAD
    assert c.step(dead,1) is None
    assert c.step(Observation(),1.5) is None and c.state==State.DEAD
    assert c.revive_attempts==1
    assert c.step(dead,2.5).key=='revive'
    assert c.step(dead,5).key=='revive'
    alive=Observation('raid_inside' if isinstance(c,RaidController) else 'combat')
    assert c.step(alive,6) is None and c.state==State.COMBAT
    assert c.step(dead,7).key=='revive'  # A later death gets a new retry budget.
    assert c.step(dead,9.5).key=='revive'
    assert c.step(dead,12).key=='revive'
    assert c.step(dead,14.5) is None and c.state==State.BLOCKED

@pytest.mark.parametrize('cls',[Controller,RaidController])
def test_potion_rechecks_health_and_rate_limits_independently_of_food(cls):
    c=cls();screen='raid_inside' if isinstance(c,RaidController) else 'combat'
    low=Observation(screen,{'potion':(279,783)})
    assert c.step(low,0) is None
    assert c.step(low,.25).key=='potion'
    for t in (1,3,9,10):assert c.step(low,t) is None
    assert c.step(low,10.25).key=='potion'
    assert c.step(Observation(screen),21) is None
    assert c.step(low,22) is None
    assert c.step(low,22.25).key=='potion'
    assert c.step(Observation('dead',{'revive':(512,832),'potion':(279,783)}),22.3).key=='revive'


@pytest.mark.parametrize('cls',[Vision,RaidVision])
def test_critical_hp_also_requests_potion_and_empty_hp_does_not(cls):
    v=cls(ROOT/'assets.json');f=frame('low')
    f[94:104,85:215]=0;f[95:102,87:90]=(0,220,0)
    assert 'potion' in observe(v,f).points
    f[94:104,85:215]=0
    assert 'potion' not in observe(v,f).points

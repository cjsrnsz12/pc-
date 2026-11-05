from pathlib import Path
import cv2
import numpy as np
import pytest
from vision import Vision, DUNGEONS
from engine import Controller, Observation, State

ASSETS=Path(__file__).resolve().parents[1]/'assets.json'

@pytest.mark.parametrize('dungeon',DUNGEONS)
def test_all_dungeons_require_correct_name_and_share_boss_transition(dungeon):
    controller=Controller(dungeon,'매우 어려움')
    points={'enter':(400,955),'skip':(715,64),'retry':(400,955)}
    assert controller.step(Observation('detail',points,dungeon,True,'매우 어려움',True),0).key=='enter'
    assert controller.step(Observation('loading'),1) is None
    assert controller.step(Observation('cutscene',points),2).key=='skip'
    assert controller.step(Observation('cutscene',points),3) is None
    assert controller.step(Observation('clear'),4).key=='clear'
    assert controller.step(Observation('clear'),5) is None
    assert controller.step(Observation('reward',points),6).key=='retry'
    wrong=next(name for name in DUNGEONS if name!=dungeon)
    blocked=Controller(dungeon,'매우 어려움')
    assert blocked.step(Observation('detail',points,wrong,True,'매우 어려움',True),0) is None
    assert blocked.state==State.BLOCKED

@pytest.mark.parametrize('dungeon,key',DUNGEONS.items())
def test_detail_name_templates_are_unique(dungeon,key):
    v=Vision(ASSETS);frame=np.zeros((1000,800),np.uint8)
    template=v.templates['detail_'+key][0];h,w=template.shape
    frame[132:132+h,27:27+w]=template;v.gray=frame
    names=[title for title,k in DUNGEONS.items() if v.hit('detail_'+k)]
    assert names==[dungeon]

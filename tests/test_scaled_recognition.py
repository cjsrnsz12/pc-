import json,base64
from pathlib import Path
import cv2
import numpy as np
import pytest
from raid import RaidVision

ROOT=Path(__file__).resolve().parents[1]
FIXTURES=json.loads((Path(__file__).parent/'fixtures/raid-reference.json').read_text())

@pytest.mark.parametrize('size',[(784,980),(640,800)])
@pytest.mark.parametrize('name,screen',[('list','raid_list'),('depart','raid_detail'),('boat','raid_boat'),('intro','raid_cutscene'),('inside','raid_inside')])
def test_reference_ui_is_recognized_after_supported_physical_resize(size,name,screen):
    f=np.zeros((1000,800,3),np.uint8)
    for patch in FIXTURES[name]:
        x,y,x2,y2=patch['box'];f[y:y2,x:x2]=cv2.imdecode(np.frombuffer(base64.b64decode(patch['png']),np.uint8),cv2.IMREAD_COLOR)
    physical=cv2.resize(f,size)
    observed=RaidVision(ROOT/'assets.json').observe(physical)
    assert observed.screen==screen

@pytest.mark.parametrize('size',[(784,980),(640,800)])
@pytest.mark.parametrize('index',range(4))
@pytest.mark.parametrize('dungeon',['허상의 정박지','광기의 동굴','흩어진 물길'])
def test_abyss_names_survive_proportional_resize(size,index,dungeon):
    from vision import Vision
    entries=json.loads((Path(__file__).parent/'fixtures/list_names.json').read_text())[index]
    f=np.zeros((1000,800,3),np.uint8)
    for patch in entries:
        x,y,w,h=patch['box'];f[y:y+h,x:x+w]=cv2.imdecode(np.frombuffer(base64.b64decode(patch['png']),np.uint8),cv2.IMREAD_COLOR)
    o=Vision(ROOT/'assets.json').observe(cv2.resize(f,size),dungeon,'매우 어려움')
    assert o.screen=='list' and o.dungeon==dungeon and 'dungeon' in o.points

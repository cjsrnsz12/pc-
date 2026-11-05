import base64
import json
from pathlib import Path
import cv2
import numpy as np
import pytest
from vision import Vision,DUNGEONS
from engine import Controller,Observation,State

ROOT=Path(__file__).resolve().parents[1]
FIXTURES=json.loads((Path(__file__).parent/'fixtures/list_names.json').read_text())

@pytest.mark.parametrize('patches',FIXTURES,ids=['very-hard-2','hard','very-hard','intro'])
@pytest.mark.parametrize('dungeon',DUNGEONS)
def test_actual_names_across_all_card_colors_without_difficulty_labels(patches,dungeon):
    frame=np.zeros((1000,800,3),np.uint8)
    for patch in patches:
        x,y,w,h=patch['box'];frame[y:y+h,x:x+w]=cv2.imdecode(np.frombuffer(base64.b64decode(patch['png']),np.uint8),cv2.IMREAD_COLOR)
    v=Vision(ROOT/'assets.json')
    o=v.observe(frame,dungeon,'매우 어려움2')
    assert o.screen=='list' and o.dungeon==dungeon
    name=next(p for p in patches if p['name']=='list_'+DUNGEONS[dungeon])
    x,y,w,h=name['box'];cx,cy=o.points['dungeon']
    assert x<=cx<x+w and y<=cy<y+h

def test_list_name_mismatch_cannot_be_clicked():
    c=Controller('광기의 동굴')
    assert c.step(Observation('list',{'dungeon':(250,520)},dungeon='허상의 정박지'),0) is None
    assert c.state==State.BLOCKED

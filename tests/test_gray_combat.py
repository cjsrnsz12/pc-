"""Regression for the supplied party timeout: the character was already fighting."""
import base64
import json
from pathlib import Path
import cv2
import numpy as np
import pytest
from engine import Controller, Observation as O, State
from vision import Vision

ROOT=Path(__file__).resolve().parents[1]

def combat_frame():
    f=np.zeros((1000,800,3),np.uint8)
    for p in json.loads((ROOT/'tests/fixtures/gray-combat.json').read_text()):
        x,y,x2,y2=p['box']
        f[y:y2,x:x2]=cv2.imdecode(np.frombuffer(base64.b64decode(p['png']),np.uint8),cv2.IMREAD_COLOR)
    return f

@pytest.mark.parametrize('size',[(800,1000),(784,980),(640,800)])
@pytest.mark.parametrize('dungeon',['허상의 정박지','광기의 동굴','흩어진 물길'])
def test_gray_skills_establish_combat_across_jobs_and_client_sizes(size,dungeon):
    f=combat_frame();f[287:318,590:795]=0  # Do not depend on a particular objective.
    o=Vision(ROOT/'assets.json').observe(cv2.resize(f,size),dungeon,'매우 어려움')
    assert o.screen=='combat'


def test_gray_skill_row_needs_all_six_ordered_numbers():
    f=combat_frame();assert Vision.combat_hud(f)
    f[815:845,560:595]=0
    assert not Vision.combat_hud(f)
    f=combat_frame();left=f[815:845,160:185].copy()
    f[815:845,160:185]=f[815:845,242:267]
    f[815:845,242:267]=left
    assert not Vision.combat_hud(f)

@pytest.mark.parametrize('stage',['list','detail','entering'])
@pytest.mark.parametrize('screen',['combat','cutscene','matching','loading'])
def test_party_actual_progress_supersedes_stale_menu_stage(stage,screen):
    c=Controller(party=True)
    assert c.step(O('reward',{'other':(550,950)}),0).key=='other'
    c.party_stage=stage;c.clear_clicked=True;c.skip_clicked=True
    if screen=='combat':
        o=Vision(ROOT/'assets.json').observe(combat_frame(),c.dungeon,c.difficulty)
    else:o=O(screen,{'skip':(720,65)})
    c.step(o,30)
    assert c.party_stage is None and c.repeats==1
    assert c.state=={'combat':State.COMBAT,'cutscene':State.BOSS,'matching':State.ENTERING,'loading':State.ENTERING}[screen]
    assert not c.clear_clicked
    c.step(O('combat'),31)
    assert c.repeats==1

@pytest.mark.parametrize('screen',['combat','cutscene','matching','loading'])
def test_party_progress_after_old_menu_deadline_still_accepted(screen):
    c=Controller(party=True)
    c.step(O('reward',{'other':(550,950)}),0)
    c.party_stage='detail'
    c.step(O(screen,{'skip':(720,65)}),241)
    assert c.state!=State.BLOCKED and c.party_stage is None

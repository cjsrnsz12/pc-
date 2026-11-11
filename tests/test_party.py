import base64
import json
from pathlib import Path
import cv2
import numpy as np
import pytest
from engine import Controller,Observation as O,State
from vision import Vision,DUNGEONS

ROOT=Path(__file__).resolve().parents[1]
FIXTURES=json.loads((Path(__file__).parent/'fixtures/party-reference.json').read_text())
def frame(name):
    f=np.zeros((1000,800,3),np.uint8)
    for p in FIXTURES[name]:
        x,y,x2,y2=p['box'];f[y:y2,x:x2]=cv2.imdecode(np.frombuffer(base64.b64decode(p['png']),np.uint8),cv2.IMREAD_COLOR)
    return f

@pytest.mark.parametrize('size',[(800,1000),(784,980),(640,800)])
def test_supplied_party_reward_list_and_entry(size):
    v=Vision(ROOT/'assets.json');c=Controller('흩어진 물길','매우 어려움2',party=True)
    observe=lambda name:v.observe(cv2.resize(frame(name),size),'흩어진 물길','매우 어려움2',after_clear=True)
    reward=observe('reward');assert reward.screen=='reward'
    a=c.step(reward,0);assert a.key=='other' and a.point==reward.points['other'] and 480<=a.point[0]<=620
    listing=observe('list');assert listing.screen=='list' and listing.dungeon=='흩어진 물길'
    assert c.step(listing,1).key=='dungeon'
    detail=observe('detail');assert detail.screen=='detail' and detail.encounter and detail.together and detail.difficulty=='매우 어려움2'
    assert c.step(detail,2).key=='enter'
    assert c.step(O('matching'),3) is None and c.repeats==1

@pytest.mark.parametrize('dungeon',DUNGEONS)
def test_every_party_dungeon_repeats_twice_with_existing_entry_checks(dungeon):
    c=Controller(dungeon,'매우 어려움',party=True)
    for start in (0,20):
        c.step(O('combat'),start)
        assert c.step(O('clear'),start+1).key=='clear'
        assert c.step(O('reward',{'retry':(400,950),'other':(550,950)}),start+2).key=='other'
        assert c.step(O('field',{'menu':(770,60)},still=True),start+7) is None
        assert c.step(O('list',{'dungeon':(240,600)},dungeon=dungeon),start+8).key=='dungeon'
        points={'enter':(490,950),'together':(510,70),'difficulty':(200,190),'encounter':(615,658)}
        assert c.step(O('detail',points,dungeon,False,'매우 어려움',True),start+9).key=='together'
        assert c.step(O('detail',points,dungeon,True,'어려움',True),start+10).key=='difficulty'
        assert c.step(O('detail',points,dungeon,True,'매우 어려움',False),start+11).key=='encounter'
        assert c.step(O('detail',points,dungeon,True,'매우 어려움',True),start+12).key=='enter'
        c.step(O('combat'),start+13)
        assert c.step(O('cutscene',{'skip':(720,65)}),start+14).key=='skip'
    assert c.repeats==2


def test_party_never_falls_back_to_retry_and_limits_other_clicks():
    c=Controller(party=True)
    assert c.step(O('reward',{'retry':(400,950)}),0) is None
    o=O('reward',{'other':(550,950),'retry':(400,950)})
    for t in (1,3.5,6):assert c.step(o,t).key=='other'
    assert c.step(o,8.5) is None and c.state==State.BLOCKED


def test_solo_still_uses_retry_and_nonrepeat_still_waits():
    o=O('reward',{'other':(550,950),'retry':(400,950)})
    assert Controller().step(o,0).key=='retry'
    assert Controller(repeat=False,party=True).step(o,0) is None


def test_party_wrong_dungeon_or_unknown_encounter_cannot_enter():
    c=Controller('흩어진 물길',party=True)
    c.step(O('reward',{'other':(550,950)}),0)
    assert c.step(O('list',{'dungeon':(250,500)},dungeon='광기의 동굴'),1) is None
    assert c.state==State.BLOCKED
    c=Controller('흩어진 물길',party=True)
    c.step(O('reward',{'other':(550,950)}),0)
    assert c.step(O('detail',{'enter':(490,950)},'흩어진 물길',True,'매우 어려움',None),1) is None


def test_other_text_alone_cannot_establish_reward_screen():
    v=Vision(ROOT/'assets.json');f=frame('reward');f[910:990,165:470]=0
    assert v.observe(f,'흩어진 물길','매우 어려움2',after_clear=True).screen!='reward'


@pytest.mark.parametrize('dungeon',DUNGEONS)
@pytest.mark.parametrize('size',[(800,1000),(784,980),(640,800)])
def test_other_pc_list_prepares_pointer_before_destination_selection(dungeon,size):
    from list_centering import ListCentering
    f=np.zeros((1000,800,3),np.uint8)
    patches=json.loads((ROOT/'tests/fixtures/party-small-list.json').read_text())
    for p in patches:
        x,y,x2,y2=p['box'];f[y:y2,x:x2]=cv2.imdecode(np.frombuffer(base64.b64decode(p['png']),np.uint8),cv2.IMREAD_COLOR)
    v=Vision(ROOT/'assets.json');c=Controller(dungeon,party=True);center=ListCentering()
    assert c.step(O('reward',{'other':(550,950)}),0).key=='other'
    # Header alone must trigger centering; no dungeon coordinates are needed yet.
    heading=f.copy();heading[400:860,170:390]=0
    for index in range(2):
        o=v.observe(cv2.resize(heading,size),dungeon,'매우 어려움')
        assert o.screen=='list' and not o.points
        assert center.observe(o.screen)==(index==1)
    center.completed()
    # Only a fresh post-move capture is used to select the actual label position.
    o=v.observe(cv2.resize(f,size),dungeon,'매우 어려움')
    assert o.screen=='list' and o.dungeon==dungeon
    assert not center.observe(o.screen)
    assert c.step(o,1).point==o.points['dungeon']


def party_pending_entry():
    c=Controller('흩어진 물길','매우 어려움2',party=True)
    c.step(O('reward',{'other':(550,950)}),0)
    c.step(O('list',{'dungeon':(240,600)},dungeon='흩어진 물길'),1)
    detail=O('detail',{'enter':(490,950)},'흩어진 물길',True,'매우 어려움2',True)
    assert c.step(detail,2).key=='enter'
    return c,detail


def test_slow_entry_retries_current_detail_after_unknown_frames_without_resetting_limit():
    c,detail=party_pending_entry()
    for lost,now in [(3,4.5),(5.5,7)]:
        assert c.step(O(),lost) is None
        assert c.step(detail,now).key=='enter'
    c.step(O(),8)
    assert c.step(detail,9.5) is None and c.state==State.BLOCKED


def test_old_field_frame_does_not_count_as_new_entry_or_prevent_retry():
    c,detail=party_pending_entry()
    assert c.step(O('field',{'menu':(770,60)},still=True),3) is None
    assert c.party_stage=='entering' and c.repeats==0 and c.state==State.ENTERING
    assert c.step(detail,4.5).key=='enter'
    c.step(O('matching'),6);assert c.repeats==1 and c.party_stage is None
    c.step(O('loading'),7);assert c.repeats==1


def test_reentry_deadline_covers_unknown_frames_and_known_list_with_missing_target():
    c,_=party_pending_entry()
    assert c.step(O(),243) is None and c.state==State.BLOCKED
    c=Controller(party=True);c.step(O('reward',{'other':(550,950)}),0)
    assert c.step(O('list'),241) is None and c.state==State.BLOCKED


def test_pending_retry_revalidates_changed_entry_conditions():
    from dataclasses import replace
    c,detail=party_pending_entry();c.step(O(),3)
    assert c.step(replace(detail,encounter=None),4.5) is None
    assert c.step(replace(detail,dungeon='광기의 동굴'),5) is None
    assert c.state==State.BLOCKED


def test_first_party_entry_does_not_increment_completion_count():
    c=Controller('흩어진 물길','매우 어려움2',party=True)
    c.step(O('detail',{'enter':(490,950)},'흩어진 물길',True,'매우 어려움2',True),0)
    c.step(O('matching'),1)
    assert c.repeats==0

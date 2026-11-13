"""Actual UI-only wipe patches, pixel recognition and shared restart flow."""
import base64
import json
from pathlib import Path
import cv2
import numpy as np
import pytest
from engine import Controller,Observation,State
from raid import RaidController,RaidVision,RaidObservation
from vision import Vision

ROOT=Path(__file__).resolve().parents[1]
PATCHES=json.loads((ROOT/'tests/fixtures/wipe-pc.json').read_text())


def frame(name,scale=1.):
    image=np.zeros((1000,800,3),np.uint8)
    for patch in PATCHES[name]:
        x,y,x2,y2=patch['box'];pixels=cv2.imdecode(np.frombuffer(base64.b64decode(patch['png']),np.uint8),cv2.IMREAD_COLOR)
        if scale!=1:
            pixels=cv2.resize(pixels,None,fx=scale,fy=scale)
            h,w=pixels.shape[:2];x=round((x+x2-w)/2);y=round((y+y2-h)/2);x2=x+w;y2=y+h
        left,top,right,bottom=max(0,x),max(0,y),min(800,x2),min(1000,y2)
        image[top:bottom,left:right]=pixels[top-y:bottom-y,left-x:right-x]
    return image


@pytest.fixture(params=[Vision,RaidVision])
def detector(request):return request.param(ROOT/'assets.json')


@pytest.mark.parametrize('size',[(800,1000),(784,980),(640,800)])
@pytest.mark.parametrize('scale',[.8,1.,1.2])
def test_supplied_wipe_and_both_exit_sentences_are_recognized(detector,size,scale):
    wipe=detector.observe(cv2.resize(frame('wipe',scale),size),'광기의 동굴','매우 어려움')
    assert wipe.screen=='wipe' and wipe.wipe_verified
    assert 730<=wipe.points['exit'][0]<=795 and 85<=wipe.points['exit'][1]<=160
    modal=detector.observe(cv2.resize(frame('dialog',scale),size),'카브락','입문')
    assert modal.screen=='wipe_dialog' and modal.wipe_verified
    assert 450<=modal.points['leave'][0]<=545 and 880<=modal.points['leave'][1]<=950


@pytest.mark.parametrize('missing',['dialog','warning','leave','red','green'])
def test_incomplete_or_wrong_color_confirmation_never_produces_leave(detector,missing):
    image=frame('dialog')
    boxes={'dialog':(268,769,534,797),'warning':(282,820,518,846),'leave':(470,907,528,932),'red':(270,250,550,345),'green':(400,885,600,955)}
    x,y,x2,y2=boxes[missing]
    if missing=='green':image[y:y2,x:x2]=cv2.cvtColor(cv2.cvtColor(image[y:y2,x:x2],cv2.COLOR_BGR2GRAY),cv2.COLOR_GRAY2BGR)
    else:image[y:y2,x:x2]=0
    observation=detector.observe(image,'광기의 동굴','입문')
    if missing=='red':
        assert observation.screen=='wipe_dialog' and not observation.wipe_verified
        assert Controller().step(observation,0) is None
    else:assert 'leave' not in observation.points


@pytest.mark.parametrize('part',[0,1,2])
def test_warning_requires_every_part_of_the_complete_phrase(detector,part):
    image=frame('dialog');edges=[282,360,439,518]
    image[820:846,edges[part]:edges[part+1]]=0
    assert 'leave' not in detector.observe(image,'광기의 동굴','입문').points


def test_wipe_needs_red_heading_and_observed_exit_shape(detector):
    image=frame('wipe');image[250:345,270:550]=cv2.cvtColor(cv2.cvtColor(image[250:345,270:550],cv2.COLOR_BGR2GRAY),cv2.COLOR_GRAY2BGR)
    assert detector.observe(image,'광기의 동굴','입문').screen!='wipe'
    for shape in ('missing','square','cross','ring'):
        image=frame('wipe');image[85:150,735:795]=0
        if shape=='square':cv2.rectangle(image,(750,100),(782,132),(255,255,255),-1)
        elif shape=='cross':
            cv2.line(image,(765,100),(765,132),(255,255,255),4);cv2.line(image,(749,116),(781,116),(255,255,255),4)
        elif shape=='ring':cv2.circle(image,(765,116),18,(255,255,255),3)
        o=detector.observe(image,'광기의 동굴','입문')
        assert o.screen=='wipe' and not o.points


@pytest.mark.parametrize('make',[Controller,lambda:Controller(party=True),lambda:Controller('광기의 동굴','매우 어려움',False),RaidController])
def test_wipe_ends_combat_and_restarts_initial_sequence_after_verified_exit(make):
    c=make();raid=isinstance(c,RaidController)
    if raid:c.phase='inside'
    c.combat_latched=True;c.clear_clicked=True;c.skip_clicked=True;c.clear_seen_at=0;c.entered_at=0;c.repeats=7
    c.dead_since=0;c.revive_attempts=2
    wipe=Observation('wipe',{'exit':(765,116)},wipe_verified=True)
    modal=Observation('wipe_dialog',{'leave':(499,919)},wipe_verified=True)
    assert c.step(wipe,500).key=='wipe_exit'
    assert c.state.value=='재시작 대기중' and not c.combat_latched and c.clear_seen_at is None
    assert c.step(Observation('dead',{'revive':(512,832)}),501) is None
    assert c.step(Observation('combat',{'potion':(279,783),'food':(210,80)},food=True),501.2) is None
    assert c.state==State.RESTART and c.repeats==7
    assert c.step(modal,502).key=='wipe_leave'
    assert c.step(wipe,502.8) is None
    # Loading, lost OCR, stale reward and battle cannot count a failed round or unlock combat.
    for i,screen in enumerate(['unknown','loading','reward','raid_inside','clear']):
        assert c.step(Observation(screen,{'retry':(400,950),'ship':(600,900)}),505+i) is None
        assert c.state==State.RESTART and c.repeats==7
    field=Observation('field',{'menu':(770,60)},still=True)
    assert c.step(field,511) is None and c.wipe_stage
    assert c.step(field,511.5) is None and not c.wipe_stage and c.wipe_recoveries==1
    assert not c.combat_latched and not c.clear_clicked and not c.skip_clicked and c.repeats==7
    if raid:
        assert c.phase=='prepare' and not c.wing_clicked and not c.boat_requested and not c.intro_skipped and not c.defeat_skipped and not c.return_requested
    else:assert c.party_stage is None and not c.entry_requested
    assert c.step(field,512) is None
    assert c.step(field,515.9) is None
    assert c.step(field,516).key=='menu'
    menu=Observation('raid_menu' if raid else 'menu',{'raid' if raid else 'abyss':(515,450)})
    assert c.step(menu,517).key==('raid' if raid else 'abyss')
    listing=Observation('raid_list' if raid else 'list',{'dungeon':(250,520)},dungeon=c.dungeon)
    assert c.step(listing,518).key==('raid_dungeon' if raid else 'dungeon')
    detail=RaidObservation('raid_detail',{'depart':(400,950)},dungeon='카브락',difficulty=c.difficulty,solo=True) if raid else Observation('detail',{'enter':(400,950)},dungeon=c.dungeon,together=True,difficulty=c.difficulty,encounter=True)
    assert c.step(detail,519).key==('raid_depart' if raid else 'enter')


@pytest.mark.parametrize('cls',[Controller,RaidController])
@pytest.mark.parametrize('stage',['exit','leave'])
def test_each_exit_stage_retries_at_2_5_seconds_with_persistent_three_attempt_limit(cls,stage):
    c=cls();wipe=Observation('wipe',{'exit':(765,116)},wipe_verified=True)
    assert c.step(wipe,0).key=='wipe_exit'
    o=wipe;start=0
    if stage=='leave':
        o=Observation('wipe_dialog',{'leave':(499,919)},wipe_verified=True);start=1
        assert c.step(o,start).key=='wipe_leave'
    for n in (1,2):
        assert c.step(Observation(),start+n*2.5-.2) is None
        assert c.step(o,start+n*2.5).key=='wipe_'+stage
    assert c.step(Observation(),start+7.3) is None
    assert c.step(o,start+7.5) is None and c.state==State.BLOCKED


@pytest.mark.parametrize('cls',[Controller,RaidController])
def test_no_guessed_buttons_and_timeout_and_outside_requires_actual_menu_hud(cls):
    c=cls();assert c.step(Observation('wipe',wipe_verified=True),0) is None and c.state==State.RESTART
    assert c.step(Observation('wipe_dialog',wipe_verified=True),1) is None
    field=Observation('field',{'menu':(770,60)},still=True)
    assert c.step(field,3) is None and c.wipe_stage
    modal=Observation('wipe_dialog',{'leave':(499,919)},wipe_verified=True)
    assert c.step(modal,4).key=='wipe_leave'
    assert c.step(Observation('field'),5) is None and c.wipe_stage
    c.step(field,6);c.step(Observation(),7);c.step(field,8)
    assert c.wipe_stage
    c.step(field,9);assert not c.wipe_stage
    d=cls();d.step(Observation('wipe',wipe_verified=True),0)
    assert d.step(Observation(),241) is None and d.state==State.BLOCKED


@pytest.mark.parametrize('cls',[Controller,RaidController])
def test_plain_user_exit_dialog_does_not_claim_a_wipe_but_visible_red_heading_can_resume(cls):
    o=Observation('wipe_dialog',{'leave':(499,919)})
    c=cls();assert c.step(o,0) is None and not c.wipe_stage
    assert c.step(Observation('wipe_dialog',{'leave':(499,919)},wipe_verified=True),1).key=='wipe_leave'

from pathlib import Path
import base64
import json
import cv2
import numpy as np
import pytest
from raid import RaidController,RaidVision,RaidObservation
from engine import State,Observation

ROOT=Path(__file__).resolve().parents[1]
FIXTURES=json.loads((Path(__file__).parent/'fixtures/raid-reference.json').read_text())

def frame(name):
    f=np.zeros((1000,800,3),np.uint8)
    for patch in FIXTURES[name]:
        x,y,x2,y2=patch['box'];f[y:y2,x:x2]=cv2.imdecode(np.frombuffer(base64.b64decode(patch['png']),np.uint8),cv2.IMREAD_COLOR)
    return f

@pytest.mark.parametrize('name,screen',[('menu','raid_menu'),('list','raid_list'),('move','raid_detail'),('wing','raid_travel'),('depart','raid_detail'),('boat','raid_boat'),('intro','raid_cutscene'),('inside','raid_inside')])
def test_supplied_screens_are_recognized(name,screen):
    v=RaidVision(ROOT/'assets.json');o=v.observe(frame(name),difficulty='입문')
    assert o.screen==screen
    if name=='move':assert not o.solo and o.difficulty=='어려움' and 'move' in o.points and 'depart' not in o.points
    if name=='depart':assert o.solo and o.difficulty=='입문' and 'depart' in o.points and 'move' not in o.points


def test_full_sequence_rechecks_solo_and_difficulty_before_travel_and_departure():
    c=RaidController('입문');v=RaidVision(ROOT/'assets.json')
    observe=lambda name:v.observe(frame(name),difficulty='입문')
    assert c.step(observe('menu'),0).key=='raid'
    assert c.step(observe('list'),1).key=='raid_dungeon'
    assert c.step(observe('move'),2).key=='raid_solo'
    points=observe('move').points
    hard=RaidObservation('raid_detail',points,dungeon='카브락',difficulty='어려움',solo=True)
    assert c.step(hard,3).key=='raid_difficulty'
    ready=RaidObservation('raid_detail',points,dungeon='카브락',difficulty='입문',solo=True)
    assert c.step(ready,4).key=='raid_move'
    assert c.step(observe('wing'),5).key=='raid_wing'
    for t in (6,8,10):assert c.step(observe('wing'),t) is None
    assert c.step(observe('depart'),11).key=='raid_depart'
    assert c.step(Observation('loading'),12) is None
    assert c.phase=='boarding'
    assert c.step(observe('boat'),13).key=='raid_boat_depart'
    assert c.step(observe('intro'),14).key=='raid_intro_skip'
    assert c.step(observe('intro'),15) is None
    assert c.step(observe('inside'),16).key=='food'
    assert c.phase=='inside' and c.state==State.COMBAT
    assert c.step(observe('inside'),30) is None


def test_difficulty_mismatch_on_arrival_cannot_depart():
    c=RaidController('어려움');v=RaidVision(ROOT/'assets.json')
    assert c.step(v.observe(frame('depart'),difficulty='어려움'),0).key=='raid_difficulty'
    assert c.phase=='prepare'


def test_wrong_name_or_ambiguous_solo_cannot_move():
    c=RaidController()
    assert c.step(RaidObservation('raid_detail',{'move':(490,950)},dungeon='적월의 스카스',difficulty='입문',solo=True),0) is None
    assert c.state==State.BLOCKED
    c=RaidController()
    assert c.step(RaidObservation('raid_detail',{'move':(490,950)},dungeon='카브락',difficulty='입문',solo=None),0) is None


def test_travel_wing_is_not_detected_without_raid_navigation_goal():
    f=frame('wing');f[210:410,650:800]=0
    assert RaidVision(ROOT/'assets.json').observe(f).screen!='raid_travel'


def test_starting_on_navigation_can_press_wing_only_once():
    c=RaidController();o=RaidObservation('raid_travel',{'wing':(585,872)})
    assert c.step(o,0).key=='raid_wing'
    assert c.step(o,10) is None
    assert c.step(o,241) is None and c.state==State.BLOCKED


def test_no_raid_entry_action_without_depart_button():
    c=RaidController()
    o=RaidObservation('raid_detail',{'enter':(400,950)},dungeon='카브락',difficulty='입문',solo=True)
    assert c.step(o,0) is None
    with pytest.raises(ValueError):RaidController('매우 어려움')


def test_move_retries_are_bounded_without_assuming_arrival():
    c=RaidController();o=RaidObservation('raid_detail',{'move':(490,950)},dungeon='카브락',difficulty='입문',solo=True)
    assert c.step(o,0).key=='raid_move'
    assert c.step(o,2.5).key=='raid_move'
    assert c.step(o,5).key=='raid_move'
    assert c.step(o,7.5) is None and c.state==State.BLOCKED


def test_cooperative_popup_preserves_travel_phase_and_single_wing_press():
    c=RaidController()
    ready=RaidObservation('raid_detail',{'move':(490,950)},dungeon='카브락',difficulty='입문',solo=True)
    assert c.step(ready,0).key=='raid_move'
    assert c.step(Observation('mission',{'confirm':(400,950)}),1).key=='mission'
    assert c.phase=='travel'
    assert c.step(Observation(),2) is None
    wing=RaidObservation('raid_travel',{'wing':(585,872)})
    assert c.step(wing,3).key=='raid_wing'
    assert c.step(wing,10) is None


def test_raid_inside_only_clicks_exact_brown_bread_and_rearms_after_absence():
    v=RaidVision(ROOT/'assets.json');c=RaidController();bread=v.observe(frame('inside'))
    assert bread.food and c.step(bread,0).key=='food'
    assert c.step(bread,20) is None
    no_bread=frame('inside');no_bread[60:110,185:235]=0
    # Food effect/gauge present without the specified icon cannot trigger input.
    no_bread[110:115,85:106]=(255,180,0)
    no_bread[110:115,108:129]=(255,180,0)
    eaten=v.observe(no_bread)
    assert eaten.screen=='raid_inside' and not eaten.food and 'food' not in eaten.points
    assert c.step(eaten,21) is None
    assert c.step(bread,22).key=='food'


def test_grey_same_shape_and_other_brown_shape_are_not_food():
    v=RaidVision(ROOT/'assets.json');f=frame('inside')
    icon=f[60:110,185:235]
    f[60:110,185:235]=cv2.cvtColor(cv2.cvtColor(icon,cv2.COLOR_BGR2GRAY),cv2.COLOR_GRAY2BGR)
    o=v.observe(f)
    assert v.hit('r_food_bread') is not None  # Shape alone is insufficient.
    assert not o.food
    f=frame('inside');f[60:110,185:235]=0
    cv2.circle(f,(208,83),15,(35,70,115),-1)
    assert not v.observe(f).food


def test_food_on_boat_or_outside_raid_goal_does_not_trigger_eating():
    v=RaidVision(ROOT/'assets.json');o=v.observe(frame('boat'))
    assert o.screen=='raid_boat' and not o.food
    c=RaidController();assert c.step(o,0).key=='raid_boat_depart'
    not_raid=frame('inside');not_raid[210:420,600:800]=0
    assert not v.observe(not_raid).food


def test_starting_on_boat_or_intro_resumes_without_reopening_menu():
    v=RaidVision(ROOT/'assets.json');c=RaidController()
    assert c.step(v.observe(frame('boat')),0).key=='raid_boat_depart'
    assert c.step(Observation('field',{'menu':(770,65)},still=True),1) is None
    assert c.step(v.observe(frame('intro')),2).key=='raid_intro_skip'
    assert c.step(v.observe(frame('intro')),10) is None
    assert c.step(v.observe(frame('inside')),11).key=='food'
    assert c.step(Observation('field',{'menu':(770,65)},still=True),30) is None


def test_raid_entry_timeout_keeps_repeated_cutscene_safe():
    c=RaidController();o=Observation('raid_cutscene',{'skip':(725,66)})
    assert c.step(o,0).key=='raid_intro_skip'
    assert c.step(o,10) is None
    assert c.step(o,241) is None and c.state==State.BLOCKED


def test_boat_navigation_quest_is_not_repeated_while_walking_to_helm():
    c=RaidController();o=Observation('raid_boat',{'boat_depart':(753,279)})
    assert c.step(o,0).key=='raid_boat_depart'
    for now in (1,3,10,30):assert c.step(o,now) is None
    assert c.step(o,241) is None and c.state==State.BLOCKED


def test_depart_available_at_initial_detail_skips_region_travel_and_wing():
    v=RaidVision(ROOT/'assets.json');c=RaidController('입문')
    assert c.step(v.observe(frame('menu')),0).key=='raid'
    assert c.step(v.observe(frame('list')),1).key=='raid_dungeon'
    action=c.step(v.observe(frame('depart')),2)
    assert action.key=='raid_depart' and c.phase=='launching'
    assert not c.wing_clicked
    assert c.step(RaidObservation('raid_travel',{'wing':(585,872)}),3) is None
    assert not c.wing_clicked
    assert c.step(v.observe(frame('boat')),4).key=='raid_boat_depart'


def test_skipping_region_travel_does_not_skip_solo_or_difficulty_checks():
    c=RaidController('어려움');points={'solo':(325,70),'difficulty':(123,215),'depart':(400,950)}
    wrong_mode=RaidObservation('raid_detail',points,dungeon='카브락',difficulty='입문',solo=False)
    assert c.step(wrong_mode,0).key=='raid_solo'
    wrong_difficulty=RaidObservation('raid_detail',points,dungeon='카브락',difficulty='입문',solo=True)
    assert c.step(wrong_difficulty,1).key=='raid_difficulty'
    ready=RaidObservation('raid_detail',points,dungeon='카브락',difficulty='어려움',solo=True)
    assert c.step(ready,2).key=='raid_depart'
    assert c.phase=='launching' and not c.wing_clicked


def test_depart_has_priority_over_stale_move_detection():
    c=RaidController()
    o=RaidObservation('raid_detail',{'depart':(400,950),'move':(490,950)},dungeon='카브락',difficulty='입문',solo=True)
    assert c.step(o,0).key=='raid_depart'
    assert c.phase=='launching'

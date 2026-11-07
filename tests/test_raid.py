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
    assert c.step(o,1) is None
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
    assert c.step(v.observe(frame('intro')),3) is None
    assert c.step(v.observe(frame('inside')),11).key=='food'
    assert c.step(Observation('field',{'menu':(770,65)},still=True),30) is None


def test_raid_entry_timeout_keeps_repeated_cutscene_safe():
    c=RaidController();o=Observation('raid_cutscene',{'skip':(725,66)})
    assert c.step(o,0).key=='raid_intro_skip'
    assert c.step(o,1) is None
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


@pytest.mark.parametrize('size',[(800,1000),(784,980),(640,800)])
def test_actual_boss_defeat_skip_after_intro_is_independent_and_once(size):
    v=RaidVision(ROOT/'assets.json');c=RaidController()
    intro=v.observe(frame('intro'))
    assert c.step(intro,0).key=='raid_intro_skip' and c.intro_skipped
    inside=v.observe(frame('inside'))
    assert c.step(inside,1).key=='food'
    ending=v.observe(cv2.resize(frame('defeat'),size))
    assert ending.screen=='raid_cutscene' and 670<=ending.points['skip'][0]<=780
    action=c.step(ending,2)
    assert action.key=='raid_defeat_skip' and action.point==ending.points['skip']
    assert c.defeat_skipped and c.phase=='aftermath' and c.state==State.CLEAR
    for now in (3,10,30):assert c.step(ending,now) is None
    assert c.step(Observation('field',{'menu':(770,60)},still=True),31) is None
    assert c.step(inside,32) is None  # Never re-enter battle/menu automation after the ending.


def test_defeat_skip_requires_visible_button_not_just_elapsed_combat_time():
    v=RaidVision(ROOT/'assets.json');c=RaidController()
    c.step(v.observe(frame('inside')),0)
    blank=frame('defeat');blank[25:110,620:795]=255
    o=v.observe(blank)
    assert o.screen!='raid_cutscene' and c.step(o,60) is None
    assert not c.defeat_skipped and c.phase=='inside'


def test_starting_in_raid_can_skip_defeat_even_without_observing_intro():
    v=RaidVision(ROOT/'assets.json');c=RaidController()
    c.step(v.observe(frame('inside')),0)
    assert not c.intro_skipped
    assert c.step(v.observe(frame('defeat')),1).key=='raid_defeat_skip'


@pytest.mark.parametrize('size',[(800,1000),(784,980),(640,800)])
def test_weekend_popup_matches_title_reward_and_green_confirmation(size):
    v=RaidVision(ROOT/'assets.json');o=v.observe(cv2.resize(frame('weekend'),size))
    assert o.screen=='raid_weekend' and 380<=o.points['confirm'][0]<=425
    c=RaidController();action=c.step(o,0)
    assert action.key=='raid_weekend_confirm' and action.point==o.points['confirm']


@pytest.mark.parametrize('missing',['title','reward','green'])
def test_weekend_popup_never_confirms_with_partial_evidence(missing):
    v=RaidVision(ROOT/'assets.json');f=frame('weekend')
    if missing=='title':f[145:335,200:610]=0
    elif missing=='reward':f[420:720,250:560]=0
    else:f[915:985,170:630]=cv2.cvtColor(cv2.cvtColor(f[915:985,170:630],cv2.COLOR_BGR2GRAY),cv2.COLOR_GRAY2BGR)
    o=v.observe(f)
    assert o.screen!='raid_weekend'
    action=RaidController().step(o,0)
    assert action is None or action.key!='raid_weekend_confirm'


def test_weekend_popup_after_defeat_reclassifies_actual_combat_after_close():
    v=RaidVision(ROOT/'assets.json');c=RaidController()
    c.step(v.observe(frame('inside')),0)
    assert c.step(v.observe(frame('defeat')),1).key=='raid_defeat_skip'
    popup=v.observe(frame('weekend'))
    assert c.step(popup,2).key=='raid_weekend_confirm'
    assert c.phase=='aftermath'
    assert c.step(Observation(),3) is None and c.weekend_resync
    assert c.step(Observation(),3.2) is None and c.state==State.SCAN
    assert c.step(v.observe(frame('inside')),4) is None
    assert c.state==State.COMBAT and c.phase=='inside' and not c.weekend_resync
    assert c.step(v.observe(frame('inside')),5) is None  # Existing food icon cannot be consumed twice.


def test_popup_close_can_report_results_or_combat_without_unrelated_clicks():
    for observed,state in [(Observation('combat'),State.COMBAT),(Observation('clear'),State.CLEAR),(Observation('reward',{'retry':(400,950)}),State.REWARD),(Observation('field',{'menu':(770,60)},still=True),State.IDLE)]:
        c=RaidController();c.phase='aftermath'
        assert c.step(Observation('raid_weekend',{'confirm':(400,950)}),0).key=='raid_weekend_confirm'
        assert c.step(observed,1) is None
        assert c.step(observed,1.2) is None and c.state==state
        assert c.step(observed,3) is None and c.state==state


def test_weekend_overlay_preserves_travel_timeout_and_bounds_click_retries():
    c=RaidController();c.phase='travel';c.entered_at=0
    popup=Observation('raid_weekend',{'confirm':(400,950)})
    assert c.step(popup,2).key=='raid_weekend_confirm'
    assert c.step(popup,3) is None
    assert c.step(Observation(),35) is None and c.entered_at==33
    assert c.step(Observation('raid_travel',{'wing':(585,872)}),36) is None
    # Unknown/unsupported closing frame cannot trigger unrelated navigation.
    assert c.state==State.SCAN
    d=RaidController()
    assert d.step(popup,0).key=='raid_weekend_confirm'
    assert d.step(popup,2.5).key=='raid_weekend_confirm'
    assert d.step(popup,5).key=='raid_weekend_confirm'
    assert d.step(popup,7.5) is None and d.state==State.BLOCKED


def test_brief_popup_detection_gap_cannot_cause_rapid_reconfirm():
    c=RaidController();popup=Observation('raid_weekend',{'confirm':(400,950)})
    assert c.step(popup,0).key=='raid_weekend_confirm'
    assert c.step(Observation(),1) is None
    assert c.step(popup,1.2) is None
    assert c.step(popup,2.5).key=='raid_weekend_confirm'


@pytest.mark.parametrize('size',[(800,1000),(784,980),(640,800)])
def test_return_quest_and_moving_highlight_recognition(size):
    v=RaidVision(ROOT/'assets.json')
    for name in ['return','return_active','return_new']:
        o=v.observe(cv2.resize(frame(name),size))
        assert o.screen=='raid_return' and o.return_ready
        assert 740<=o.points['exit'][0]<=790 and o.points['exit'][1]<180
    assert v.observe(cv2.resize(frame('returned_boat'),size)).screen=='raid_boat'


@pytest.mark.parametrize('missing',['title','hint'])
def test_return_requires_completed_kabrak_title_and_ship_instruction(missing):
    f=frame('return')
    if missing=='title':f[266:290,645:790]=0
    else:f[292:325,695:790]=0
    assert RaidVision(ROOT/'assets.json').observe(f).screen!='raid_return'


def test_two_complete_raid_loops_rearm_departure_and_both_cutscenes():
    c=RaidController();v=RaidVision(ROOT/'assets.json')
    observe=lambda name:v.observe(frame(name))
    for start in (0,40):
        c.step(observe('inside'),start)
        assert c.step(observe('defeat'),start+1).key=='raid_defeat_skip'
        assert c.step(Observation('reward'),start+2) is None
        o=observe('return');a=c.step(o,start+3)
        assert a.key=='raid_exit' and a.point==o.points['exit']
        assert c.step(observe('return_dialog'),start+4).key=='raid_return_ship'
        for t,n in [(5,'return'),(8,'return_active')]:assert c.step(observe(n),start+t) is None
        assert c.step(Observation('field',{'menu':(770,60)},still=True),start+9) is None
        assert c.phase=='returning'
        assert c.step(observe('returned_boat'),start+10).key=='raid_boat_depart'
        assert c.step(observe('returned_boat'),start+11) is None
        assert c.step(observe('intro'),start+12).key=='raid_intro_skip'
        assert c.step(observe('intro'),start+13) is None
        c.step(observe('inside'),start+14)
    assert c.repeats==2 and c.phase=='inside'


def test_cyan_quest_highlight_still_uses_exit_icon_and_ship_dialog():
    c=RaidController();v=RaidVision(ROOT/'assets.json')
    assert c.step(v.observe(frame('return_active')),0).key=='raid_exit'
    assert c.step(v.observe(frame('return_dialog')),1).key=='raid_return_ship'
    assert c.return_requested and c.phase=='returning'
    assert c.step(v.observe(frame('return')),241) is None and c.state==State.BLOCKED


def test_weekend_popup_during_return_keeps_latch_until_boat():
    c=RaidController();v=RaidVision(ROOT/'assets.json')
    assert c.step(v.observe(frame('return')),0).key=='raid_exit'
    assert c.step(v.observe(frame('return_dialog')),.7).key=='raid_return_ship'
    assert c.step(v.observe(frame('weekend')),1.5).key=='raid_weekend_confirm'
    assert c.step(Observation('loading'),2) is None
    assert c.step(Observation('loading'),3) is None and c.phase=='returning'
    assert c.step(v.observe(frame('return')),4) is None
    assert c.step(v.observe(frame('returned_boat')),5).key=='raid_boat_depart'


@pytest.mark.parametrize('background',[40,150,220,240])
@pytest.mark.parametrize('scale',[.8,1.,1.25])
def test_entry_skip_lettering_survives_background_scale_and_position_changes(background,scale):
    v=RaidVision(ROOT/'assets.json')
    # Use the supplied skip lettering against dark/bright moving-scene colors.
    source=v.templates['skip'][0].astype(np.float32)
    alpha=np.clip((source-130)/125,0,1)
    letters=cv2.resize((background*(1-alpha)+255*alpha).astype(np.uint8),None,fx=scale,fy=scale)
    h,w=letters.shape;f=np.full((1000,800,3),background,np.uint8)
    x,y=640,115;f[y:y+h,x:x+w]=cv2.cvtColor(letters,cv2.COLOR_GRAY2BGR)
    o=v.observe(f)
    assert o.screen=='raid_cutscene'
    assert max(abs(a-b) for a,b in zip(o.points['skip'],(x+w//2,y+h//2)))<=3


@pytest.mark.parametrize('kind',['flat','border','partial'])
def test_skip_outline_matching_needs_both_words_not_a_bright_box(kind):
    v=RaidVision(ROOT/'assets.json');f=np.zeros((1000,800,3),np.uint8)
    if kind=='flat':f[30:145,580:790]=245
    elif kind=='border':cv2.rectangle(f,(610,40),(785,100),(245,245,245),2)
    else:
        t=v.templates['skip'][0];h,w=t.shape
        f[70:70+h,670:670+w]=cv2.cvtColor(t,cv2.COLOR_GRAY2BGR)
        f[70:70+h,670:670+int(w*.42)]=0
    assert v.observe(f).screen!='raid_cutscene'


def test_skip_has_priority_over_lingering_boat_hud_during_transition():
    v=RaidVision(ROOT/'assets.json');f=frame('boat');intro=frame('intro')
    f[25:110,620:795]=intro[25:110,620:795]
    assert v.observe(f).screen=='raid_cutscene'


def test_failed_intro_click_rechecks_current_button_and_retries_with_limit():
    v=RaidVision(ROOT/'assets.json');c=RaidController();o=v.observe(frame('intro'))
    assert c.step(o,0).key=='raid_intro_skip'
    for t in (.7,1,2.4):assert c.step(o,t) is None
    assert c.step(Observation(),2.45) is None
    assert c.step(o,2.5).key=='raid_intro_skip'
    assert c.step(o,5).key=='raid_intro_skip'
    assert c.step(o,7.5) is None and c.state==State.BLOCKED


def test_intro_retry_stops_as_soon_as_current_screen_confirms_entry():
    v=RaidVision(ROOT/'assets.json');c=RaidController()
    assert c.step(v.observe(frame('intro')),0).key=='raid_intro_skip'
    c.step(v.observe(frame('inside')),1)
    for t in (3,6,10):assert c.step(v.observe(frame('inside')),t) is None
    assert c.phase=='inside' and c.state==State.COMBAT


@pytest.mark.parametrize('size',[(800,1000),(784,980),(640,800)])
def test_supplied_failure_capture_clear_reward_confirms_then_returns_to_ship(size):
    v=RaidVision(ROOT/'assets.json');c=RaidController();c.phase='sailing';c.intro_skipped=True
    o=v.observe(cv2.resize(frame('clear_reward'),size))
    assert o.screen=='raid_reward'
    action=c.step(o,0)
    assert action.key=='raid_reward_confirm' and action.point==o.points['confirm']
    assert c.step(o,1) is None
    assert c.step(v.observe(frame('return')),2).key=='raid_exit'
    assert c.step(v.observe(frame('return_dialog')),3).key=='raid_return_ship'
    assert c.step(v.observe(frame('returned_boat')),4).key=='raid_boat_depart'


@pytest.mark.parametrize('missing',['name','done','green'])
def test_kabrak_reward_confirmation_requires_boss_name_completion_and_green_button(missing):
    v=RaidVision(ROOT/'assets.json');f=frame('clear_reward')
    if missing=='name':f[120:165,345:460]=0
    elif missing=='done':f[175:205,345:460]=0
    else:f[910:985,170:630]=cv2.cvtColor(cv2.cvtColor(f[910:985,170:630],cv2.COLOR_BGR2GRAY),cv2.COLOR_GRAY2BGR)
    assert v.observe(f).screen!='raid_reward'


@pytest.mark.parametrize('size',[(800,1000),(784,980),(640,800)])
def test_exit_popup_from_supplied_screen_matches_ship_button_not_party_exit(size):
    v=RaidVision(ROOT/'assets.json');c=RaidController()
    o=v.observe(cv2.resize(frame('return_dialog'),size))
    assert o.screen=='raid_return_dialog' and o.return_ready
    a=c.step(o,0)
    assert a.key=='raid_return_ship' and a.point==o.points['ship']
    assert 430<a.point[0]<575 and a.point[1]>800
    assert c.step(o,1) is None
    assert c.step(o,2.5).key=='raid_return_ship'
    assert c.step(o,5).key=='raid_return_ship'
    assert c.step(o,7.5) is None and c.state==State.BLOCKED


def test_completed_quest_without_exit_icon_never_clicks_the_quest():
    v=RaidVision(ROOT/'assets.json');f=frame('return_new');f[75:180,710:800]=0
    o=v.observe(f)
    assert o.screen=='raid_return' and not o.points
    assert RaidController().step(o,0) is None


@pytest.mark.parametrize('missing',['ship','green','completion'])
def test_missing_ship_button_or_completion_never_clicks_party_exit(missing):
    v=RaidVision(ROOT/'assets.json');f=frame('return_dialog')
    if missing=='ship':f[810:890,420:580]=0
    elif missing=='green':f[810:890,420:580]=cv2.cvtColor(cv2.cvtColor(f[810:890,420:580],cv2.COLOR_BGR2GRAY),cv2.COLOR_GRAY2BGR)
    else:f[245:330,610:800]=0
    o=v.observe(f);assert o.screen=='raid_return_dialog'
    assert RaidController().step(o,0) is None


@pytest.mark.parametrize('phase',['prepare','launching','boarding','boat','sailing'])
def test_actual_combat_hud_exits_entry_wait_even_when_raid_goal_is_hidden(phase):
    c=RaidController();c.phase=phase;c.entered_at=0
    assert c.step(Observation('combat'),20) is None
    assert c.phase=='inside' and c.state==State.COMBAT and c.entered_at is None
    assert c.step(Observation('combat'),300) is None and c.state==State.COMBAT
    assert c.step(Observation('field',{'menu':(770,60)},still=True),305) is None
    assert c.state==State.COMBAT


@pytest.mark.parametrize('background',[50,160,230])
@pytest.mark.parametrize('scale',[.8,1.,1.2])
def test_raid_goal_lettering_on_changed_scene_and_lower_quest_position(background,scale):
    v=RaidVision(ROOT/'assets.json');source=v.templates['r_inside_goal'][0].astype(np.float32)
    # Photometric changes and relocation preserve the supplied glyph shapes.
    label=cv2.resize(np.clip(source*.4+background*.6,0,255).astype(np.uint8),None,fx=scale,fy=scale)
    f=frame('inside');f[210:420,600:800]=0
    h,w=label.shape;f[435:435+h,640:640+w]=cv2.cvtColor(label,cv2.COLOR_GRAY2BGR)
    o=v.observe(f)
    assert o.screen=='raid_inside'
    c=RaidController();c.phase='sailing';c.entered_at=0
    c.step(o,20);assert c.state==State.COMBAT and c.entered_at is None


def test_low_hp_with_menu_and_raid_goal_still_confirms_entry():
    from tests.test_survival import frame as survival_frame
    v=RaidVision(ROOT/'assets.json');f=frame('inside');hud=survival_frame('low')
    f[85:110,75:220]=0;f[95:102,87:90]=(0,220,0)
    f[40:85,740:800]=hud[40:85,740:800]
    assert v.observe(f).screen=='raid_inside'
    f[85:110,75:220]=0
    assert v.observe(f).screen=='raid_inside' and not v.observe(f).food


@pytest.mark.parametrize('scale',[.8,1.,1.2])
def test_user_supplied_kabrak_clear_text_proves_combat_without_hp_or_revive_count(scale):
    v=RaidVision(ROOT/'assets.json');f=np.zeros((1000,800,3),np.uint8)
    t=cv2.resize(v.templates['r_inside_goal_new'][0],None,fx=scale,fy=scale)
    h,w=t.shape;f[275:275+h,640:640+w]=cv2.cvtColor(t,cv2.COLOR_GRAY2BGR)
    o=v.observe(f)
    assert o.screen=='raid_inside' and not o.food
    c=RaidController();c.phase='sailing';c.entered_at=0
    c.step(o,20)
    assert c.state==State.COMBAT and c.phase=='inside' and c.entered_at is None
    assert c.step(Observation(),300) is None and c.state==State.COMBAT

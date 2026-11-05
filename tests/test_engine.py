from engine import Controller, Observation as O, State


def test_four_continuous_seconds_and_motion_reset():
    c=Controller();p={'menu':(770,65)}
    assert c.step(O('field',p,still=True),0) is None
    assert c.step(O('field',p,still=True),3.99) is None
    c.step(O('field',p,still=False),4)
    assert c.step(O('field',p,still=True),5) is None
    assert c.step(O('field',p,still=True),8.9) is None
    assert c.step(O('field',p,still=True),9).key=='menu'


def test_start_during_combat_never_opens_menu_when_stationary():
    c=Controller();c.step(O('combat'),0)
    for t in range(1,80):
        assert c.step(O('field',{'menu':(770,65)},still=True),t) is None
    assert c.combat_latched


def test_correct_detail_and_switch_are_required():
    c=Controller();p={'enter':(400,950),'together':(520,65),'difficulty':(205,188),'encounter':(615,650)}
    a=c.step(O('detail',p,'허상의 정박지',True,'매우 어려움',False),0)
    assert a.key=='encounter'
    assert c.step(O('detail',p,'허상의 정박지',True,'매우 어려움',True),1).key=='enter'
    assert c.state==State.ENTERING
    assert c.step(O('loading'),2) is None
    assert c.step(O('field',{'menu':(770,65)},still=True),7) is None
    assert c.state==State.COMBAT
    wrong=Controller()
    assert wrong.step(O('detail',p,'광기의 동굴',True,'매우 어려움',True),0) is None
    assert wrong.state==State.BLOCKED
    unknown=Controller()
    assert unknown.step(O('detail',p,'허상의 정박지',True,'매우 어려움',None),0) is None


def test_difficulty_2_is_not_difficulty_1():
    c=Controller();p={'difficulty':(205,188)}
    assert c.step(O('detail',p,'허상의 정박지',True,'매우 어려움2',True),0).key=='difficulty'


def test_retry_wait_and_loading_do_not_open_menu():
    c=Controller()
    assert c.step(O('reward',{'retry':(400,955)}),0).key=='retry'
    for t,s in [(1,'matching'),(3,'loading'),(5,'unknown')]:
        assert c.step(O(s),t) is None
        assert c.state==State.ENTERING
    assert c.step(O('combat'),6) is None
    assert c.state==State.COMBAT


def test_retry_repeats_after_2_5_seconds_then_stops():
    c=Controller();o=O('reward',{'retry':(400,955)})
    assert c.step(o,0)
    assert c.step(o,2.4) is None
    assert c.step(o,2.5)
    assert c.step(o,5)
    assert c.step(o,7.5) is None
    assert c.state==State.BLOCKED


def test_clear_single_click_and_popup_preserves_phase():
    c=Controller();c.step(O('combat'),0)
    assert c.step(O('cutscene',{'skip':(715,65)}),1).key=='skip'
    assert c.step(O('cutscene',{'skip':(715,65)}),2) is None
    c.step(O('mission',{'confirm':(400,950)}),3)
    assert c.state==State.BOSS
    assert c.step(O('field',still=True),4) is None
    assert c.combat_latched
    assert c.step(O('clear'),5).point==(400,500)
    assert c.step(O('clear'),20) is None


def test_food_only_once_until_icon_disappears():
    c=Controller();o=O('combat',{'food':(90,125)},food=True)
    assert c.step(o,0).key=='food'
    assert c.step(o,11) is None
    c.step(O('combat'),12)
    assert c.step(o,13).key=='food'


def test_non_repeat_stays_at_rewards_and_entering_times_out():
    c=Controller(repeat=False)
    assert c.step(O('reward',{'retry':(400,955)}),0) is None
    assert c.state==State.WAIT
    d=Controller();d.step(O('matching'),0)
    assert d.step(O('loading'),241) is None
    assert d.state==State.BLOCKED


def test_enter_button_no_response_is_retried_with_conditions_rechecked():
    c=Controller();p={'enter':(400,950)}
    o=O('detail',p,'허상의 정박지',True,'매우 어려움',True)
    assert c.step(o,0).key=='enter'
    assert c.step(o,1) is None
    assert c.step(o,2.5).key=='enter'
    assert c.step(O('matching'),3) is None
    assert c.state==State.ENTERING

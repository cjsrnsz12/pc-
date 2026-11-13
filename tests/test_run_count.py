from engine import Controller,Observation as O,State
from raid import RaidController
from run_count import RunCount


def step(counter,controller,screen,now,points=None):
    controller.step(O(screen,points or {},dungeon=controller.dungeon if screen=='list' else ''),now)
    counter.observe(screen,controller)


def test_solo_counts_clear_once_before_next_entry_and_ignores_survival():
    c=Controller();n=RunCount()
    for start in (0,20):
        step(n,c,'combat',start)
        step(n,c,'clear',start+1)
        step(n,c,'clear',start+2)
        step(n,c,'reward',start+3,{'retry':(400,950)})
        step(n,c,'reward',start+4,{'retry':(400,950)})
        assert n.total==start//20+1
        step(n,c,'matching',start+6)
    assert n.total==2
    for screen in ('unknown','field','dead','mission','loading','cutscene'):
        # Only directly exercise noncompletion observations; don't trigger dialogs.
        n.observe(screen,c)
    assert n.total==2


def test_party_counts_a_completed_run_before_list_or_entry():
    c=Controller(party=True);n=RunCount()
    step(n,c,'combat',0);step(n,c,'clear',1)
    assert n.total==1 and c.repeats==0
    step(n,c,'reward',2,{'other':(550,950)})
    step(n,c,'list',4,{'dungeon':(225,600)})
    assert n.total==1
    # Leader may begin the new run while our app still waits for a menu.
    step(n,c,'combat',5);step(n,c,'clear',7)
    assert n.total==2


def test_raid_intro_does_not_count_but_defeat_and_rewards_count_once():
    c=RaidController();n=RunCount()
    c.phase='boarding'
    n.observe('raid_cutscene',c);assert n.total==0
    c.phase='inside'
    step(n,c,'raid_cutscene',0,{'skip':(720,65)})
    assert n.total==1
    for screen in ('raid_cutscene','raid_weekend','raid_reward','raid_return'):
        n.observe(screen,c)
    assert n.total==1
    c.phase='returning'
    step(n,c,'raid_boat',5,{'depart':(740,280)})
    assert n.total==1 and c.repeats==1
    c.phase='inside'
    step(n,c,'raid_reward',10,{'confirm':(400,950)})
    assert n.total==2


def test_reward_fallback_counts_when_clear_was_missed_and_new_session_is_zero():
    c=Controller();n=RunCount()
    step(n,c,'reward',0,{'retry':(400,950)})
    assert n.total==1
    assert RunCount().total==0
    c.state=State.BLOCKED;c.repeats+=1
    assert not n.observe('reward',c) and n.total==1


def test_solo_next_round_can_skip_matching_and_loading():
    c=Controller();n=RunCount()
    for t in (0,10,20):
        step(n,c,'combat',t)
        step(n,c,'clear',t+1)
        step(n,c,'reward',t+2,{'retry':(400,950)})
    assert n.total==3


def test_wipe_does_not_count_or_erase_finished_runs():
    for c in (Controller(),RaidController()):
        n=RunCount();assert n.observe('reward',c) and n.total==1
        c.wipe_stage='leaving';assert not n.observe('reward',c)
        assert not n.observe('wipe',c) and n.total==1
        c.reset_after_wipe()
        assert n.total==1
        assert n.observe('reward',c) and n.total==2

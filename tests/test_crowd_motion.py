import cv2
import numpy as np
from motion import Stillness
from vision import Vision
from engine import Controller,Observation


def background(seed=3):
    rng=np.random.default_rng(seed)
    texture=rng.integers(25,150,(1000,800),np.uint8)
    frame=cv2.cvtColor(texture,cv2.COLOR_GRAY2BGR)
    frame[100:240,650:795]=25
    return frame


def crowd(frame,tick):
    im=frame.copy()
    for i,x in enumerate([90,170,260,340,420,500,580]):
        y=380+(i%3)*65;offset=(tick*(i+2))%17
        cv2.rectangle(im,(x+offset,y),(x+offset+42,y+125),(70+i*7,65+i*6,85+i*4),-1)
        cv2.putText(im,'PLAYER '+str(tick),(max(5,x-25),y-14),cv2.FONT_HERSHEY_SIMPLEX,.55,(210,130,220),1)
    return im


def test_other_players_and_nameplates_do_not_reset_start_timer():
    base=background();s=Stillness();c=Controller();action=None
    states=[]
    for i in range(24):
        stable=s.update(crowd(base,i))
        states.append(stable)
        action=c.step(Observation('field',{'menu':(770,65)},still=stable),i*.25)
        if action:break
    assert action is not None and action.key=='menu'
    assert i*.25>=4.
    assert sum(states)>=16


def test_walking_camera_motion_is_not_ignored_as_crowd():
    base=background();s=Stillness();assert not s.update(crowd(base,0))
    for i in range(1,6):
        shifted=cv2.warpAffine(base,np.float32([[1,0,i*2],[0,1,0]]),(800,1000))
        assert not s.update(crowd(shifted,i))


def test_minimap_motion_vetoes_static_scene():
    base=background();rng=np.random.default_rng(12)
    terrain=rng.integers(20,160,(96,98),np.uint8)
    base[118:214,676:774]=cv2.cvtColor(terrain,cv2.COLOR_GRAY2BGR)
    s=Stillness();s.update(base);assert s.update(base)
    moved=base.copy()
    moved[118:214,676:774]=cv2.cvtColor(np.roll(terrain,3,axis=1),cv2.COLOR_GRAY2BGR)
    assert not s.update(moved)
    assert '미니맵' in s.note


def test_occluded_or_featureless_scene_waits_instead_of_clicking():
    s=Stillness();blank=np.full((1000,800,3),240,np.uint8)
    assert not s.update(blank) and not s.update(blank)


def test_a_few_world_circles_do_not_count_as_combat_hud():
    frame=np.zeros((1000,800,3),np.uint8)
    for x,y in [(225,855),(360,900),(520,880)]:cv2.circle(frame,(x,y),33,(240,240,240),2)
    assert not Vision.combat_hud(frame)


def test_other_player_dots_on_minimap_do_not_look_like_walking():
    base=background();rng=np.random.default_rng(18)
    terrain=rng.integers(30,155,(96,98),np.uint8)
    base[118:214,676:774]=cv2.cvtColor(terrain,cv2.COLOR_GRAY2BGR)
    s=Stillness()
    for tick in range(5):
        f=base.copy()
        for x,y in [(694,145),(715,180),(750,160)]:cv2.circle(f,(x+tick,y),3,(40,240,80),-1)
        stable=s.update(f)
        if tick:assert stable

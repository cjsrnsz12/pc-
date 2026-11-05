from pathlib import Path
import cv2
import numpy as np
from vision import Vision
from engine import Controller

ASSETS=Path(__file__).resolve().parents[1]/'assets.json'


def menu_frame(variant='old',shift=0,close=True,anchors=True):
    v=Vision(ASSETS);frame=np.zeros((1000,800,3),np.uint8)
    def put(name,x,y):
        template=v.templates[name][1] # Original scale; variants also support small rescaling.
        h,w=template.shape;frame[y:y+h,x:x+w]=cv2.cvtColor(template,cv2.COLOR_GRAY2BGR)
    if close:put('menu_close',755,53)
    if variant=='old':
        put('abyss',513,326+shift);row=324+shift
    else:
        put('abyss_collab',513,458+shift);row=457+shift
    if anchors:
        put('menu_field_boss',432,row);put('menu_raid',649,row)
    return frame


def test_original_menu_target_is_detected():
    v=Vision(ASSETS);o=v.observe(menu_frame(),'허상의 정박지','매우 어려움')
    assert o.screen=='menu' and abs(o.points['abyss'][1]-347)<=2


def test_collaboration_banner_moves_target_and_controller_uses_new_position():
    v=Vision(ASSETS);o=v.observe(menu_frame('collab'),'허상의 정박지','매우 어려움')
    assert o.screen=='menu' and abs(o.points['abyss'][1]-481)<=2
    assert Controller().step(o,0).point==o.points['abyss']
    assert o.points['abyss'][1]>450


def test_variable_banner_height_does_not_use_fixed_offset():
    v=Vision(ASSETS);o=v.observe(menu_frame('collab',shift=125),'허상의 정박지','매우 어려움')
    assert o.screen=='menu' and abs(o.points['abyss'][1]-606)<=2


def test_isolated_abyss_icon_does_not_prove_menu_is_open():
    for close,anchors in [(False,True),(True,False)]:
        v=Vision(ASSETS);o=v.observe(menu_frame(close=close,anchors=anchors),'허상의 정박지','매우 어려움')
        assert o.screen!='menu'

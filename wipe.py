"""Shared, frame-local wipe/exit recognition. No controller or OS side effects."""
import cv2
import numpy as np
from engine import Observation


def phrase_hit(view,name):
    hit=view.hit(name)
    if hit is None:return None
    x,y,w,h=hit.box
    candidate=view.gray[y:y+h,x:x+w]
    # Require the complete phrase, rather than a shared suffix or one short word.
    for template in view.templates[name]:
        if template.shape!=(h,w):continue
        if all(float(cv2.matchTemplate(candidate[:,a:b],template[:,a:b],cv2.TM_CCOEFF_NORMED)[0,0])>=.66
               for a,b in ((0,w//3),(w//3,2*w//3),(2*w//3,w))):return hit
    return None


def red_heading(view,hit):
    if hit is None:return False
    x,y,w,h=hit.box
    b,g,r=cv2.split(view.frame[y:y+h,x:x+w])
    # A confirmation overlay dims the red text, while preserving its hue.
    return float(np.mean((r>45)&(g<r.astype(np.float32)*.62)&(b<r.astype(np.float32)*.62)))>.06


def observe_wipe(view):
    heading=phrase_hit(view,'w_title')
    verified=red_heading(view,heading)
    dialog=phrase_hit(view,'w_dialog')
    if dialog is not None:
        warning=phrase_hit(view,'w_warning')
        leave=phrase_hit(view,'w_leave') if warning is not None else None
        points={}
        if warning is not None and leave is not None:
            dx,dy,dw,dh=dialog.box;wx,wy,ww,wh=warning.box;x,y,w,h=leave.box
            aligned=dy+dh<wy and wy+wh<y and abs(dialog.center[0]-warning.center[0])<75
            green=view.color_fraction((x-20,y-9,x+w+20,y+h+9),'green')>.42
            if aligned and leave.center[0]>400 and green:points['leave']=leave.center
        return Observation('wipe_dialog',points,wipe_verified=verified)
    if not verified:return None
    points={}
    if (button:=view.hit('w_exit')) is not None:
        x,y,w,h=button.box;area=view.frame[y:y+h,x:x+w]
        white=np.mean(np.min(area,axis=2)>180);dark=np.mean(np.max(area,axis=2)<120)
        if .04<white<.6 and dark>.2:points['exit']=button.center
    return Observation('wipe',points,wipe_verified=True)

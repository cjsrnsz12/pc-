"""Local image matching, normalized to the 800 × 1000 game client."""
import base64
import json
from dataclasses import dataclass
from pathlib import Path
import cv2
import numpy as np
from engine import Observation
from motion import Stillness
from detail_templates import DETAIL_TEMPLATES

DUNGEONS = {'허상의 정박지': 'harbor', '광기의 동굴': 'cave', '흩어진 물길': 'water'}
DIFFICULTIES = ['입문', '어려움', '매우 어려움', '매우 어려움2']
DIFFICULTY_BOXES = [(26,170,80,205),(87,170,154,205),(160,170,256,205),(263,170,366,205)]


@dataclass
class Hit:
    score: float
    box: tuple

    @property
    def center(self):
        x, y, w, h = self.box
        return (x + w // 2, y + h // 2)


class Vision:
    def __init__(self, asset_path: Path):
        self.data = json.loads(asset_path.read_text(encoding='utf-8'))
        self.data.update(DETAIL_TEMPLATES)
        # Separate text searches so 어려움 cannot match inside 매우 어려움2.
        for title, box in zip(DIFFICULTIES, DIFFICULTY_BOXES):
            self.data['diff_'+title]['roi'] = list(box)
        self.templates = {}
        for name, item in self.data.items():
            png = cv2.imdecode(np.frombuffer(base64.b64decode(item['png']), np.uint8), cv2.IMREAD_GRAYSCALE)
            self.templates[name] = [cv2.resize(png, None, fx=s, fy=s) for s in item['scales']]
        self.stillness = Stillness()
        self.cache = {}
        self.gray = None
        self.frame = None

    def hit(self, name):
        if name in self.cache:
            return self.cache[name]
        d = self.data[name]
        x1, y1, x2, y2 = d['roi']
        roi = self.gray[y1:y2, x1:x2]
        best = None
        for template in self.templates[name]:
            h, w = template.shape
            if h > roi.shape[0] or w > roi.shape[1]:
                continue
            scores = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
            _, score, _, pos = cv2.minMaxLoc(scores)
            if best is None or score > best.score:
                best = Hit(score, (x1 + pos[0], y1 + pos[1], w, h))
        result = best if best and best.score >= d['threshold'] else None
        self.cache[name] = result
        return result

    def color_fraction(self, box, kind):
        x1, y1, x2, y2 = map(int, box)
        a = self.frame[max(0,y1):min(1000,y2), max(0,x1):min(800,x2)]
        if not a.size:
            return 0.
        hsv = cv2.cvtColor(a, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        if kind == 'green':
            mask = (h >= 37) & (h <= 92) & (s > 90) & (v > 90)
        elif kind == 'orange':
            mask = ((h < 18) | (h > 170)) & (s > 160) & (v > 95)
        elif kind == 'purple':
            mask = (h > 120) & (h < 165) & (s > 105) & (v > 80)
        else:
            mask = (h > 75) & (h < 125) & (s > 100) & (v > 100)
        return float(np.mean(mask))

    def difficulty_selection(self, requested):
        candidates = []
        point = None
        for title, box in zip(DIFFICULTIES, DIFFICULTY_BOXES):
            hit = self.hit('diff_'+title)
            if title == requested and hit:
                point = hit.center
            x1,y1,x2,y2 = box
            hsv = cv2.cvtColor(self.frame[y1:y2,x1:x2], cv2.COLOR_BGR2HSV)
            h,s,v = cv2.split(hsv)
            if title == '입문': hue = (h >= 120) & (h <= 145)
            elif title == '어려움': hue = (h >= 15) & (h <= 35)
            else: hue = (h <= 12) | (h >= 173)
            # Selection outline and lettering are bright and saturated; grey tabs fail.
            fraction = float(np.mean(hue & (s > 140) & (v > 120)))
            if fraction > .12:
                candidates.append(title)
        # Ambiguous/transitional frames must never satisfy the entry condition.
        return (candidates[0] if len(candidates) == 1 else ''), point

    def menu_target(self):
        # Banner height is variable. Match the actual icon/label and corroborate its row.
        if self.hit('menu_close') is None:return None
        left=self.hit('menu_field_boss');right=self.hit('menu_raid')
        candidates=[]
        for name in ('abyss','abyss_collab'):
            hit=self.hit(name)
            if hit is None:continue
            x,y=hit.center
            left_ok=left is not None and 50<=x-left.center[0]<=95 and abs(y-left.center[1])<=13
            right_ok=right is not None and 115<=right.center[0]-x<=170 and abs(y-right.center[1])<=13
            if left_ok or right_ok:candidates.append(hit)
        return max(candidates,key=lambda h:h.score) if candidates else None

    @staticmethod
    def combat_hud(frame):
        # World objects alone must not latch the entire run into combat.
        gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
        circles=cv2.HoughCircles(gray[820:940,160:640],cv2.HOUGH_GRADIENT,1.3,48,param1=100,param2=26,minRadius=23,maxRadius=44)
        if circles is None:return False
        hsv=cv2.cvtColor(frame[825:925,170:625],cv2.COLOR_BGR2HSV)
        yy,xx=np.indices(hsv.shape[:2]);colored=(hsv[:,:,1]>100)&(hsv[:,:,2]>120)&(((hsv[:,:,0]>70)&(hsv[:,:,0]<125))|((hsv[:,:,0]>10)&(hsv[:,:,0]<40)))
        matched=0
        for slot in (215,287,360,434,506,578):
            aligned=any(abs(float(x)+160-slot)<=17 and abs(float(y)+820-873)<=18 for x,y,r in circles[0])
            radius=np.sqrt((xx+170-slot)**2+(yy+825-873)**2);ring=(radius>28)&(radius<39)
            if aligned and np.mean(colored[ring])>.07:matched+=1
        return matched>=4

    def observe(self, frame, dungeon, difficulty):
        self.frame = cv2.resize(frame, (800, 1000))
        self.gray = cv2.cvtColor(self.frame, cv2.COLOR_BGR2GRAY)
        self.cache = {}
        p = {}
        if self.hit('mission') and (h := self.hit('confirm')):
            return Observation('mission', {'confirm': h.center})
        if self.hit('clear') and self.hit('touch'):
            return Observation('clear')
        if (h := self.hit('retry')) and self.hit('exit'):
            return Observation('reward', {'retry': h.center})
        if self.hit('matching'):
            return Observation('matching')
        if self.hit('loading_name'):
            return Observation('loading')
        if (h := self.hit('skip')):
            return Observation('cutscene', {'skip': h.center})
        if (e := self.hit('enter')) and (t := self.hit('together')):
            names = [title for title,key in DUNGEONS.items() if self.hit('detail_'+key)]
            detected = names[0] if len(names)==1 else ''
            p['enter'], p['together'] = e.center, t.center
            # Selection is the purple panel behind the text, not mere text presence.
            together = self.color_fraction((461, 36, 610, 94), 'purple') > .35
            selected, target = self.difficulty_selection(difficulty)
            if target is not None:p['difficulty'] = target
            toggle = None
            if (label := self.hit('encounter_label')):
                lx, ly, lw, lh = label.box
                tx, ty = lx+lw+32, ly+lh//2
                p['encounter'] = (tx, ty)
                # Distinguish green ON from grey OFF; unknown colors cause a wait.
                green = self.color_fraction((tx-19, ty-11, tx+20, ty+11),'green')
                region = self.frame[ty-10:ty+11, tx-18:tx+19]
                if green > .25:
                    toggle = True
                elif region.size:
                    hsv = cv2.cvtColor(region,cv2.COLOR_BGR2HSV)
                    white_right = float(np.mean(np.all(region[:,19:] > 210,axis=2)))
                    # Only a grey switch with its white thumb on the left is OFF.
                    white_left = float(np.mean(np.all(region[:,:18] > 210,axis=2)))
                    if white_left > .15 and white_left > white_right and float(np.median(hsv[:,:,1])) < 100:
                        toggle = False
            return Observation('detail',p,detected,together,selected,toggle)
        if self.hit('list_title'):
            if (h := self.hit('list_' + DUNGEONS[dungeon])):
                p['dungeon'] = h.center
                return Observation('list', p)
        if (h := self.menu_target()):
            return Observation('menu', {'abyss': h.center})
        # Health bar and game menu together establish a live game HUD.
        hud = self.color_fraction((80,85,214,105),'green') > .10 or self.color_fraction((80,50,220,78),'green') > .10
        menu = self.hit('menu')
        if hud:
            if menu:
                p['menu'] = menu.center
            food = self.hit('food')
            if food:
                p['food'] = food.center
            combat=self.combat_hud(self.frame)
            if not combat and not menu:
                self.stillness.reset()
                return Observation()
            still = self.stillness.update(self.frame)
            return Observation('combat' if combat else 'field',p,still=still,food=bool(food),motion_note=self.stillness.note)
        self.stillness.reset()
        return Observation()

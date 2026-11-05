"""Local image matching, normalized to the 800 × 1000 game client."""
import base64
import json
from dataclasses import dataclass
from pathlib import Path
import cv2
import numpy as np
from engine import Observation

DUNGEONS = {'허상의 정박지': 'harbor', '광기의 동굴': 'cave', '흩어진 물길': 'water'}
DIFFICULTIES = ['입문', '어려움', '매우 어려움', '매우 어려움2']


@dataclass
class Hit:
    score: float
    box: tuple

    @property
    def center(self):
        x, y, w, h = self.box
        return (x + w // 2, y + h // 2)


class Stillness:
    def __init__(self):
        self.previous = None

    def reset(self):
        self.previous = None

    def update(self, frame):
        gray = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (9, 9), 0)
        patches = [(260, 390, 340, 620), (465, 390, 560, 620), (350, 605, 460, 655)]
        previous, self.previous = self.previous, gray
        if previous is None:
            return False
        changes = []
        for x1, y1, x2, y2 in patches:
            a, b = previous[y1:y2, x1:x2], gray[y1:y2, x1:x2]
            changes.append(float(np.mean(cv2.absdiff(a, b) > 15)))
        return max(changes[:2]) < .035 and changes[2] < .09


class Vision:
    def __init__(self, asset_path: Path):
        self.data = json.loads(asset_path.read_text(encoding='utf-8'))
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
            detected = ''
            if self.hit('detail_harbor'):
                detected = '허상의 정박지'
            else:
                for title, key in DUNGEONS.items():
                    if self.hit('name_' + key):
                        detected = title
                        break
            p['enter'], p['together'] = e.center, t.center
            # Selection is the purple panel behind the text, not mere text presence.
            together = self.color_fraction((461, 36, 610, 94), 'purple') > .35
            selected = ''
            for title in DIFFICULTIES:
                h = self.hit('diff_' + title)
                if h:
                    if title == difficulty:
                        p['difficulty'] = h.center
                    x,y,w,hg = h.box
                    if self.color_fraction((x-8,y-7,x+w+8,y+hg+7),'orange') > .12:
                        selected = title
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
        if (h := self.hit('abyss')):
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
            # Combat skill row contains several bright circular rims; the field does not.
            crop = self.gray[820:940,160:640]
            circles = cv2.HoughCircles(crop,cv2.HOUGH_GRADIENT,1.3,48,param1=100,param2=26,minRadius=23,maxRadius=44)
            combat = circles is not None and len(circles[0]) >= 3
            if not combat and not menu:
                self.stillness.reset()
                return Observation()
            still = self.stillness.update(self.frame)
            return Observation('combat' if combat else 'field',p,still=still,food=bool(food))
        self.stillness.reset()
        return Observation()

"""Local image matching, normalized to the 800 × 1000 game client."""
import base64
import json
from dataclasses import dataclass, replace
from pathlib import Path
import cv2
import numpy as np
from engine import Observation
from motion import Stillness
from detail_templates import DETAIL_TEMPLATES
from hud_templates import HUD_TEMPLATES
from combat_templates import SKILL_BADGES
from functools import lru_cache
from survival_templates import SURVIVAL_TEMPLATES
from party_templates import PARTY_TEMPLATES

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
        self.data.update(HUD_TEMPLATES)
        self.data.update(SURVIVAL_TEMPLATES)
        self.data.update(PARTY_TEMPLATES)
        for name in ('abyss','abyss_collab','menu_field_boss','menu_raid'):
            self.data[name]=dict(self.data[name],roi=(350,180,760,870))
        # The food button sits beside the portrait, above the buff icon row.
        self.data['food']['roi'] = [65,45,250,180]
        for key in DUNGEONS.values():
            # All three card labels share this column, including the supplied newer list.
            self.data['list_'+key]['roi'] = [170,410,390,860]
        # Separate text searches so 어려움 cannot match inside 매우 어려움2.
        for title, box in zip(DIFFICULTIES, DIFFICULTY_BOXES):
            self.data['diff_'+title]['roi'] = list(box)
        self.templates = {}
        for name, item in self.data.items():
            png = cv2.imdecode(np.frombuffer(base64.b64decode(item['png']), np.uint8), cv2.IMREAD_GRAYSCALE)
            self.templates[name] = [cv2.resize(png, None, fx=s, fy=s) for s in item['scales']]
            if name.startswith('s_'):
                self.templates[name].append(cv2.GaussianBlur(png,(3,3),.5))
            if name.startswith('list_'):
                # A normalized smaller client has slightly softer glyph edges.
                self.templates[name].append(cv2.GaussianBlur(png,(3,3),.5))
                base=self.templates[name][0]
                for scale in (.7,.75,.8,.85,.9,1.1,1.15,1.2,1.25,1.3):
                    scaled=cv2.resize(base,None,fx=scale,fy=scale)
                    self.templates[name].extend([scaled,cv2.GaussianBlur(scaled,(3,3),.5)])
            if name in ('abyss','abyss_collab','menu_field_boss','menu_raid'):
                # Window sizing does not fix the game's independent UI scale.
                # Keep the existing variants first, then search larger/smaller
                # glyphs while still requiring the close button and a row anchor.
                base=self.templates[name][0]
                self.templates[name].extend(cv2.resize(base,None,fx=s,fy=s) for s in (.8,.85,.9,1.1,1.15,1.2,1.25,1.3))
        self.result_templates={name:[cv2.resize(self.templates[name][0],None,fx=s,fy=s) for s in (.8,.85,.9,.95,1.05,1.1,1.15,1.2,1.25,1.3)] for name in ('clear','touch','retry','exit','party_other')}
        self.stillness = Stillness()
        self.cache = {}
        self.scores = {}
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
        self.scores[name]=round(best.score,4) if best else None
        result = best if best and best.score >= d['threshold'] else None
        self.cache[name] = result
        return result

    def result_hit(self,name):
        original=self.hit(name)
        if original:return original
        box={'clear':(100,100,700,370),'touch':(80,780,720,1000),'retry':(80,760,740,1000),'exit':(30,760,420,1000),'party_other':(430,760,780,1000)}[name]
        x,y,x2,y2=box;roi=self.gray[y:y2,x:x2];best=None
        for template in self.result_templates[name]:
            h,w=template.shape
            if h>roi.shape[0] or w>roi.shape[1]:continue
            _,score,_,pos=cv2.minMaxLoc(cv2.matchTemplate(roi,template,cv2.TM_CCOEFF_NORMED))
            if best is None or score>best.score:best=Hit(score,(x+pos[0],y+pos[1],w,h))
        self.scores['result_'+name]=round(best.score,4) if best else None
        return best if best and best.score>=self.data[name]['threshold'] else None

    def result_screen(self):
        if self.result_hit('clear') and self.result_hit('touch'):return Observation('clear')
        if (retry:=self.result_hit('retry')) and self.result_hit('exit'):
            return self.reward_observation(retry,recover=True)
        return None

    def reward_observation(self,retry,recover=False):
        points={'retry':retry.center}
        other=self.result_hit('party_other') if recover else self.hit('party_other')
        if other:points['other']=other.center
        return Observation('reward',points)

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

    def list_target(self,dungeon):
        # Match only the white dungeon name. The difficulty label and card tint
        # underneath are deliberately excluded from both identity and selection.
        if self.hit('list_title'):
            return self.hit('list_'+DUNGEONS[dungeon])
        return None

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
    @lru_cache(maxsize=1)
    def skill_badge_templates():
        patterns=[]
        for encoded in SKILL_BADGES:
            badge=cv2.imdecode(np.frombuffer(base64.b64decode(encoded),np.uint8),cv2.IMREAD_GRAYSCALE)
            patterns.append([cv2.resize(badge,None,fx=s,fy=s) for s in (.85,.9,1.,1.1,1.15)])
        return patterns

    @staticmethod
    def numbered_skill_row(gray):
        # Six ordered hotkeys establish the expanded combat HUD even while
        # cooldowns grey out the skills. A few circles in scenery do not.
        roi=gray[780:915,125:680]
        centers=[]
        for variants in Vision.skill_badge_templates():
            best=None
            for template in variants:
                _,score,_,point=cv2.minMaxLoc(cv2.matchTemplate(roi,template,cv2.TM_CCOEFF_NORMED))
                if best is None or score>best[0]:best=(score,point,template.shape)
            score,(x,y),(h,w)=best
            if score<.84:return False
            centers.append((x+w/2,y+h/2))
        gaps=np.diff([p[0] for p in centers])
        return bool(np.all((gaps>50)&(gaps<105)) and np.ptp([p[1] for p in centers])<12 and np.ptp(gaps)<18)

    @staticmethod
    def combat_hud(frame):
        # World objects alone must not latch the entire run into combat.
        gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
        if Vision.numbered_skill_row(gray):return True
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

    def observe(self, frame, dungeon, difficulty, after_clear=False):
        return self.with_survival(self.observe_scene(frame,dungeon,difficulty,after_clear))

    def with_survival(self, observed):
        dead=self.hit('s_dead')
        if dead:
            button=self.hit('s_revive')
            points={}
            if button:
                x,y,w,h=button.box
                hsv=cv2.cvtColor(self.frame[y-3:y+h+4,x-4:x+w+4],cv2.COLOR_BGR2HSV)
                hue,saturation,value=cv2.split(hsv)
                if float(np.mean((hue>=5)&(hue<=30)&(saturation>110)&(value>100)))>.25:
                    points['revive']=button.center
            return Observation('dead',points)
        if observed.screen not in ('combat','field','raid_inside','unknown'):return observed
        if observed.screen=='unknown' and not self.hit('menu'):return observed
        # Only the player's fixed top-left HP row, never overhead enemy/party bars.
        hsv=cv2.cvtColor(self.frame[94:104,85:215],cv2.COLOR_BGR2HSV)
        hue,saturation,value=cv2.split(hsv)
        columns=np.mean((hue>=35)&(hue<=85)&(saturation>100)&(value>100),axis=0)>.3
        indices=np.flatnonzero(columns)
        low=bool(len(indices)>=2 and indices[0]<8 and indices[-1]<65)
        points={k:v for k,v in observed.points.items() if k!='potion'}
        if low and (label:=self.hit('s_f1')) and (potion:=self.hit('s_potion')):
            x,y,w,h=potion.box
            hsv=cv2.cvtColor(self.frame[y:y+h,x:x+w],cv2.COLOR_BGR2HSV)
            hue,saturation,value=cv2.split(hsv)
            ready=float(np.mean((hue<35)&(saturation>90)&(value>120)))>.20
            if ready and abs(potion.center[0]-label.center[0])<40 and 0<potion.center[1]-label.center[1]<60:
                points['potion']=potion.center
        # A nearly empty HP row can fail the ordinary live-HUD area threshold.
        # Menu + positive HP + F1 + ready potion still establish the action bar.
        return replace(observed,points=points,screen='combat' if observed.screen=='unknown' and 'potion' in points else observed.screen)

    def observe_scene(self, frame, dungeon, difficulty, after_clear=False):
        self.frame = cv2.resize(frame, (800, 1000))
        self.gray = cv2.cvtColor(self.frame, cv2.COLOR_BGR2GRAY)
        self.cache = {}
        self.scores = {}
        p = {}
        if self.hit('mission') and (h := self.hit('confirm')):
            return Observation('mission', {'confirm': h.center})
        if self.hit('matching'):
            return Observation('matching')
        if self.hit('clear') and self.hit('touch'):
            return Observation('clear')
        if (h := self.hit('retry')) and self.hit('exit'):
            return self.reward_observation(h,recover=True)
        if after_clear:
            recovered=self.result_screen()
            if recovered is not None:return recovered
        if self.hit('list_title'):
            h=self.list_target(dungeon)
            return Observation('list', {'dungeon':h.center} if h else {}, dungeon=dungeon if h else '')
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
            combat=self.combat_hud(self.frame) or self.hit('objective_harbor') is not None
            if not combat and not menu:
                self.stillness.reset()
                return Observation()
            still = self.stillness.update(self.frame)
            return Observation('combat' if combat else 'field',p,still=still,food=bool(food),motion_note=self.stillness.note)
        self.stillness.reset()
        recovered=self.result_screen()
        return recovered if recovered is not None else Observation()

"""Kabrak solo raid recognition and return-to-ship repeat flow (unfinished preview)."""
from dataclasses import dataclass,replace
from pathlib import Path
import base64
import cv2
import numpy as np
from engine import Controller,Observation,State
from vision import Vision
from raid_templates import RAID_TEMPLATES

RAID_DIFFICULTIES=['입문','어려움']

@dataclass(frozen=True)
class RaidObservation(Observation):
    solo: bool | None=None
    return_active: bool=False


class RaidVision(Vision):
    def __init__(self,asset_path):
        super().__init__(asset_path)
        self.data.update(RAID_TEMPLATES)
        for name,item in RAID_TEMPLATES.items():
            png=cv2.imdecode(np.frombuffer(base64.b64decode(item['png']),np.uint8),cv2.IMREAD_GRAYSCALE)
            self.templates[name]=[cv2.resize(png,None,fx=s,fy=s) for s in item['scales']]
            if name in ('r_return_title','r_return_hint'):
                self.templates[name].append(cv2.GaussianBlur(png,(3,3),.5))

    def bread_button(self):
        button=self.hit('r_food_bread')
        if button is None:return None
        x,y,w,h=button.box;hsv=cv2.cvtColor(self.frame[y:y+h,x:x+w],cv2.COLOR_BGR2HSV)
        hue,saturation,value=cv2.split(hsv)
        brown=(hue>=5)&(hue<=30)&(saturation>70)&(value>60)
        return button if float(np.mean(brown))>.25 else None

    def observe(self,frame,dungeon='카브락',difficulty='입문',after_clear=False):
        return self.with_survival(self.observe_raid_scene(frame,dungeon,difficulty,after_clear))

    def observe_raid_scene(self,frame,dungeon='카브락',difficulty='입문',after_clear=False):
        self.frame=cv2.resize(frame,(800,1000));self.gray=cv2.cvtColor(self.frame,cv2.COLOR_BGR2GRAY)
        self.cache={};self.scores={}
        if self.hit('r_weekend_title') and self.hit('r_weekend_reward') and (button:=self.hit('r_weekend_confirm')):
            x,y=button.center
            if self.color_fraction((x-140,y-13,x+140,y+15),'green')>.40:
                return RaidObservation('raid_weekend',{'confirm':button.center})
        if self.hit('mission') and (button:=self.hit('confirm')):return Observation('mission',{'confirm':button.center})
        if (title:=self.hit('r_return_title')) and self.hit('r_return_hint'):
            x,y,w,h=title.box
            hsv=cv2.cvtColor(self.frame[y+h:y+h+32,max(0,x-10):min(800,x+w)],cv2.COLOR_BGR2HSV)
            hue,saturation,value=cv2.split(hsv)
            active=float(np.mean((hue>=85)&(hue<=110)&(saturation>60)&(value>60)))>.10
            return RaidObservation('raid_return',{'return':title.center},return_active=active)
        if self.hit('r_boat_task') and (button:=self.hit('r_boat_depart')):
            return RaidObservation('raid_boat',{'boat_depart':button.center})
        if (button:=self.hit('r_intro_skip') or self.hit('r_defeat_skip')):
            return RaidObservation('raid_cutscene',{'skip':button.center})
        hud=self.color_fraction((80,85,214,110),'green')>.10
        if hud and self.hit('r_inside_goal'):
            bread=self.bread_button()
            return RaidObservation('raid_inside',{'food':bread.center} if bread else {},dungeon='카브락',food=bread is not None)

        if (title:=self.hit('r_detail_name')) and (solo:=self.hit('r_solo') or self.hit('r_solo_on')):
            points={'solo':solo.center}
            for name,key in [('r_move','move'),('r_depart','depart')]:
                if (button:=self.hit(name)):points[key]=button.center
            green=self.color_fraction((270,45,380,95),'green')>.18
            purple=self.color_fraction((470,40,610,95),'purple')>.35
            alone=True if green and not purple else False if purple and not green else None
            selected=[]
            for label,key,box,kind in [('입문','r_diff_intro',(28,197,85,233),'purple'),('어려움','r_diff_hard',(90,197,158,233),'gold')]:
                button=self.hit(key)
                if button and label==difficulty:points['difficulty']=button.center
                x,y,x2,y2=box;hsv=cv2.cvtColor(self.frame[y:y2,x:x2],cv2.COLOR_BGR2HSV)
                h,s,v=cv2.split(hsv)
                hue=(h>=120)&(h<=145) if kind=='purple' else (h>=15)&(h<=35)
                if float(np.mean(hue&(s>140)&(v>120)))>.12:selected.append(label)
            return RaidObservation('raid_detail',points,dungeon='카브락',difficulty=selected[0] if len(selected)==1 else '',solo=alone)
        if self.hit('r_list_title'):
            button=self.hit('r_list_kabrak')
            return RaidObservation('raid_list',{'dungeon':button.center} if button else {},dungeon='카브락' if button else '')
        if self.hit('r_travel_goal') and (wing:=self.hit('r_wing')):
            return RaidObservation('raid_travel',{'wing':wing.center})
        if self.hit('menu_close') and (button:=self.hit('menu_raid')):
            anchors=[self.hit('abyss'),self.hit('abyss_collab'),self.hit('menu_field_boss')]
            if any(a and 110<=button.center[0]-a.center[0]<=245 and abs(button.center[1]-a.center[1])<=15 for a in anchors):
                return RaidObservation('raid_menu',{'raid':button.center})
        observed=super().observe(frame,'허상의 정박지',difficulty)
        return replace(observed,food=False,points={k:v for k,v in observed.points.items() if k!='food'}) if observed.screen in ('field','combat','mission','clear','reward','loading','matching') else Observation()


class RaidController(Controller):
    def __init__(self,difficulty='입문'):
        if difficulty not in RAID_DIFFICULTIES:raise ValueError('레이드 난이도는 입문 또는 어려움입니다.')
        super().__init__('카브락',difficulty,False)
        self.phase='prepare';self.wing_clicked=False;self.intro_skipped=False;self.boat_requested=False;self.defeat_skipped=False
        self.weekend_since=None;self.weekend_resync=False;self.weekend_last=-999.;self.weekend_attempts=0
        self.return_requested=False

    def step(self,o,now):
        if self.state==State.BLOCKED:return None
        action=self.survival_action(o,now)
        if o.screen=='dead' or self.dead_since is not None or action is not None:return action
        if o.screen=='raid_weekend':
            if self.weekend_since is None:self.weekend_since=now
            self.state=State.REWARD;self.reason='주말 레이드 퀘스트 보상 확인'
            if now-self.weekend_last<2.5:return None
            if self.weekend_attempts>=3:
                self.state,self.reason=State.BLOCKED,'주말 레이드 보상 확인창이 닫히지 않습니다.'
                return None
            action=self.emit('raid_weekend_confirm',o.points.get('confirm'),'주말 레이드 문구·보상·초록 확인 버튼 검증 → 확인',now)
            if action:self.weekend_last=now;self.weekend_attempts+=1
            return action
        if self.weekend_since is not None:
            elapsed=now-self.weekend_since
            if self.entered_at is not None:self.entered_at+=elapsed
            if self.clear_seen_at is not None:self.clear_seen_at+=elapsed
            self.weekend_since=None;self.weekend_resync=True
            self.last_key='';self.attempts=0;self.settle_until=now+.1
            self.state=State.SCAN;self.reason='주말 보상 창 닫힘 · 새 화면으로 현재 상태 재확인'
            return None
        if o.screen=='mission':return super().step(o,now)
        if self.popup_since is not None:
            super().step(Observation(),now)
            return None
        if self.phase=='prepare' and o.screen=='raid_travel':
            self.phase='travel';self.entered_at=now
        if now<self.settle_until:return None
        if self.weekend_resync:
            if o.screen in ('raid_inside','combat'):
                self.phase='inside';self.state=State.COMBAT;self.entered_at=None;self.clear_seen_at=None
                self.reason='주말 보상 후 현재 전투 화면 확인'
            elif o.screen in ('clear','reward'):
                self.phase='aftermath';self.state=State.CLEAR if o.screen=='clear' else State.REWARD
                self.reason='주말 보상 후 현재 레이드 결과 화면 확인'
            elif o.screen in ('loading','matching'):
                self.phase='returning' if self.return_requested else 'boarding';self.state=State.ENTERING;self.entered_at=now;self.clear_seen_at=None
                self.reason='주말 보상 후 현재 입장·로딩 화면 확인'
            elif o.screen=='field':
                self.phase='returning' if self.return_requested else 'post_popup_field';self.state=State.IDLE;self.reason='주말 보상 후 일반 지역 확인 · 후속 진행 대기'
            elif o.screen in ('raid_detail','raid_menu','raid_list'):
                self.phase='prepare';self.state=State.SCAN;self.entered_at=None;self.clear_seen_at=None
                self.reason='주말 보상 후 레이드 설정·메뉴 재확인'
            elif o.screen=='raid_boat':
                self.state=State.ENTERING;self.reason='주말 보상 후 배 탑승 화면 확인'
            elif o.screen=='raid_return':
                self.state=State.CLEAR;self.reason='주말 보상 후 카브락 토벌 완료 확인'
            elif o.screen=='raid_cutscene':
                self.state=State.CLEAR if self.phase=='aftermath' else State.ENTERING
                self.reason='주말 보상 후 현재 장면 확인'
            else:
                self.state=State.SCAN;self.reason='주말 보상 후 현재 화면 확인 중'
                return None
            self.weekend_resync=False;self.weekend_attempts=0
            return None
        if o.screen=='raid_return':
            self.state=State.ENTERING;self.reason='카브락 토벌 완료 · 출항선 복귀 대기'
            if self.phase!='returning':
                self.phase='returning';self.entered_at=now
            if getattr(o,'return_active',False):self.return_requested=True
            if not self.return_requested:
                action=self.emit('raid_return',o.points.get('return'),'카브락 토벌 완료 퀘스트 선택 → 배로 복귀 대기',now)
                if action:self.return_requested=True
                return action
        if self.phase=='returning':
            if o.screen=='raid_boat':
                self.repeats+=1
                self.phase='boat';self.boat_requested=False;self.intro_skipped=False;self.defeat_skipped=False
                self.return_requested=False;self.clear_seen_at=None;self.clear_clicked=False
                self.last_key='';self.attempts=0;self.entered_at=now
            else:
                self.state=State.ENTERING;self.reason='출항선 복귀 중 · 배의 출항하기 확인 대기'
                if self.entered_at is not None and now-self.entered_at>240:
                    self.state,self.reason=State.BLOCKED,'출항선 복귀 대기가 4분을 넘었습니다. 화면을 확인하세요.'
                return None
        if o.screen in ('clear','reward'):
            self.phase='aftermath';self.state=State.CLEAR if o.screen=='clear' else State.REWARD
            self.reason='레이드 클리어 화면 확인 · 후속 동작 대기' if o.screen=='clear' else '레이드 전리품 화면 확인 · 후속 동작 대기'
            return None
        if self.phase=='post_popup_field' and o.screen=='field':
            self.state=State.IDLE;self.reason='일반 지역 화면 · 후속 진행 대기'
            return None
        if self.phase=='aftermath':
            self.state=State.CLEAR;self.reason='보스 처치 장면 넘김 완료 · 이후 결과 화면 처리 대기'
            return None
        if o.screen=='raid_cutscene' and self.phase=='inside':
            self.state=State.CLEAR;self.reason='레이드 보스 처치 장면 · 장면 넘기기 확인'
            action=self.emit('raid_defeat_skip',o.points.get('skip'),'보스 처치 장면 넘기기 한 번 클릭',now)
            if action:
                self.defeat_skipped=True;self.phase='aftermath';self.clear_seen_at=now
            return action
        if o.screen=='raid_inside':
            self.phase='inside';self.entered_at=None;self.state=State.COMBAT
            self.reason='카브락 입장 확인 · 지정된 빵 아이콘이 보일 때만 음식 사용'
            return self.food_action(o,now)
        if self.phase=='inside':
            self.state=State.COMBAT;self.reason='카브락 전투 중 · 입장·메뉴 조작 없이 음식 아이콘 확인'
            return None
        if self.phase in ('launching','boarding','boat','sailing') and self.entered_at is not None and now-self.entered_at>240:
            self.state,self.reason=State.BLOCKED,'레이드 출항·입장 대기가 4분을 넘었습니다. 화면을 확인하세요.'
            return None
        if o.screen=='raid_boat':
            self.phase='boat';self.state=State.ENTERING;self.reason='배 탑승 확인 · 퀘스트 출항하기 확인'
            if self.boat_requested:return None
            action=self.emit('raid_boat_depart',o.points.get('boat_depart'),'배 위 퀘스트 출항하기 선택',now)
            if action:self.entered_at=now;self.boat_requested=True
            return action
        if o.screen=='raid_cutscene':
            self.phase='sailing';self.state=State.ENTERING;self.reason='출항 장면 확인 · 레이드 입장 대기'
            if self.entered_at is None:self.entered_at=now
            if self.intro_skipped:return None
            action=self.emit('raid_intro_skip',o.points.get('skip'),'레이드 출항 장면 넘기기 한 번 클릭',now)
            if action:self.intro_skipped=True
            return action
        if self.phase=='launching':
            self.state=State.ENTERING;self.reason='출항 요청 후 배 탑승 화면 확인 중'
            if o.screen=='raid_detail' and o.points.get('depart'):
                if getattr(o,'solo',None) is True and o.difficulty==self.difficulty:
                    return self.emit('raid_depart',o.points['depart'],'출항하기 재시도',now)
                return None
            self.phase='boarding'
        if self.phase in ('boarding','boat','sailing'):
            self.state=State.ENTERING;self.reason='배·출항 장면 이후 카브락 입장 화면 확인 중'
            if self.entered_at is not None and now-self.entered_at>240:
                self.state,self.reason=State.BLOCKED,'레이드 출항·입장 대기가 4분을 넘었습니다. 화면을 확인하세요.'
            return None

        if self.phase=='travel':
            self.state=State.ENTERING;self.reason='레이드 입장 지역으로 이동 중'
            if self.entered_at is not None and now-self.entered_at>240:
                self.state,self.reason=State.BLOCKED,'지역 이동 대기가 4분을 넘었습니다. 화면을 확인하세요.'
                return None
            if o.screen=='raid_travel':
                if self.wing_clicked:return None
                action=self.emit('raid_wing',o.points.get('wing'),'지역 이동 날개 버튼 한 번 클릭',now)
                if action:self.wing_clicked=True
                return action
            if o.screen!='raid_detail':return None
        if o.screen=='raid_detail':
            self.state=State.DETAIL;self.reason='카브락 · 혼자하기 · 선택한 난이도 확인'
            if o.dungeon!='카브락':
                self.state,self.reason=State.BLOCKED,'카브락 이름을 확인하지 못했습니다.';return None
            if getattr(o,'solo',None) is False:return self.emit('raid_solo',o.points.get('solo'),'레이드 혼자하기 선택',now)
            if getattr(o,'solo',None) is not True:return None
            if o.difficulty!=self.difficulty:return self.emit('raid_difficulty',o.points.get('difficulty'),'레이드 '+self.difficulty+' 선택',now)
            # Departure is sufficient: no prior region move or wing press is required.
            if o.points.get('depart'):
                action=self.emit('raid_depart',o.points['depart'],'카브락·혼자하기·난이도 확인 → 출항하기 (이동하기·날개 추가 실행 없음)',now)
                if action:self.phase='launching';self.state=State.ENTERING;self.entered_at=now
                return action
            if o.points.get('move'):
                if self.phase=='travel' and self.wing_clicked:return None
                action=self.emit('raid_move',o.points['move'],'레이드 입장 가능 지역으로 이동하기 (던전 입장 아님)',now)
                if action:
                    self.phase='travel';self.entered_at=self.entered_at if self.entered_at is not None else now
                    self.state=State.ENTERING
                return action
            self.reason='이동하기·출항하기 버튼 확인 대기';return None
        if self.phase!='prepare':return None
        if o.screen=='raid_menu':
            self.state=State.LIST;self.reason='메뉴에서 레이드 선택'
            return self.emit('raid',o.points.get('raid'),'메뉴 → 레이드',now)
        if o.screen=='raid_list':
            self.state=State.LIST;self.reason='레이드 목록에서 카브락 선택'
            return self.emit('raid_dungeon',o.points.get('dungeon'),'카브락 레이드 선택',now)
        if o.screen=='field':return super().step(o,now)
        if o.screen=='combat':
            self.state=State.WAIT;self.reason='레이드 전투 화면 · 전투 동작은 추가 구현 대기'
        return None

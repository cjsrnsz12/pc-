"""Deterministic screen state controller. No operating-system calls in this module."""
from dataclasses import dataclass, field
from enum import Enum
from recognition_timing import click_settle


class State(str, Enum):
    SCAN = '화면 확인 중'
    IDLE = '시작 전 정지 확인'
    MENU = '메뉴 열기'
    LIST = '어비스 선택'
    DETAIL = '입장 조건 확인'
    ENTERING = '던전 입장 중'
    COMBAT = '전투 중'
    BOSS = '보스 전투 중'
    CLEAR = '클리어 확인'
    REWARD = '보상 확인'
    WAIT = '보상 화면에서 대기'
    BLOCKED = '확인 필요'
    DEAD = '행동 불능'


@dataclass(frozen=True)
class Observation:
    screen: str = 'unknown'
    points: dict = field(default_factory=dict)
    dungeon: str = ''
    together: bool = False
    difficulty: str = ''
    encounter: bool | None = None
    still: bool = False
    food: bool = False
    motion_note: str = ''


@dataclass(frozen=True)
class Action:
    key: str
    point: tuple[int, int]
    message: str


class Controller:
    def __init__(self, dungeon='허상의 정박지', difficulty='매우 어려움', repeat=True, party=False):
        self.dungeon, self.difficulty, self.repeat = dungeon, difficulty, repeat
        self.party=party;self.party_stage=None
        self.party_entry_last=-999.;self.party_entry_attempts=0
        self.state = State.SCAN
        self.reason = ''
        self.still_since = None
        self.last_key, self.last_at = '', -999.0
        self.attempts = 0
        self.settle_until = 0.0
        self.entered_at = None
        self.combat_latched = False
        self.clear_clicked = False
        self.clear_seen_at = None
        self.skip_clicked = False
        self.repeats = 0
        self.reward_since = None
        self.food_armed = True
        self.food_last = -999.0
        self.popup_since = None
        self.popup_last = -999.0
        self.popup_attempts = 0
        self.last_screen = None
        self.dead_since=None
        self.revive_last=-999.;self.revive_attempts=0
        self.potion_last=-999.;self.low_health_since=None

    def emit(self, key, point, message, now):
        if point is None or now < self.settle_until:
            return None
        if self.last_key == key:
            if now - self.last_at < 2.5:
                return None
            if self.attempts >= 3:
                self.state, self.reason = State.BLOCKED, message + ' 반응 없음 — 화면 확인 후 다시 시작하세요.'
                return None
        else:
            self.attempts = 0
        self.last_key, self.last_at = key, now
        self.attempts += 1
        self.settle_until = now + click_settle(key)
        return Action(key, point, message)

    def step(self, o: Observation, now: float):
        if self.state == State.BLOCKED:
            return None
        action=self.survival_action(o,now)
        if o.screen=='dead' or self.dead_since is not None or action is not None:return action
        # Cooperative mission is an overlay: never reset the underlying dungeon phase.
        if o.screen == 'mission':
            if self.popup_since is None:
                self.popup_since = now
                self.popup_attempts = 0
            if now - self.popup_last < 2.5:
                return None
            if self.popup_attempts >= 3:
                self.state, self.reason = State.BLOCKED, '협동 미션 확인창이 닫히지 않습니다.'
                return None
            self.popup_last = now
            self.popup_attempts += 1
            self.settle_until = now + 0.65
            return Action('mission', o.points['confirm'], '협동 미션 완료 → 확인')
        if self.popup_since is not None:
            elapsed = now - self.popup_since
            if self.entered_at is not None:
                self.entered_at += elapsed
            self.popup_since = None
            self.popup_attempts = 0
            self.still_since = None
            self.settle_until = now + 0.65
        if now < self.settle_until:
            return None
        if o.screen != self.last_screen:
            self.last_key, self.attempts = '', 0
            self.last_screen = o.screen
        if o.screen == 'list' and self.clear_clicked and o.dungeon==self.dungeon and o.points.get('dungeon'):
            self.combat_latched=False;self.state=State.SCAN;self.entered_at=None
            self.clear_clicked=False;self.clear_seen_at=None
        if o.screen == 'reward':
            self.reason='파티 보상 · 다른 던전 가기 확인' if self.party else '보상 · 다시 하기 확인'
            self.clear_seen_at=None;self.clear_clicked=False
            self.state = State.REWARD if self.repeat else State.WAIT
            self.combat_latched = False
            if self.reward_since is None:
                self.reward_since = now
            if not self.repeat:
                return None
            a = self.emit('other',o.points.get('other'),'파티 보상 → 다른 던전 가기',now) if self.party else self.emit('retry', o.points.get('retry'), '보상 → 다시 하기', now)
            if a:
                self.party_stage='list' if self.party else None
                self.state = State.LIST if self.party else State.ENTERING
                self.entered_at = now
            return a
        if self.party_stage is not None and self.entered_at is not None and now-self.entered_at>240:
            self.state,self.reason=State.BLOCKED,'파티 재입장 대기가 4분을 넘었습니다. 현재 화면을 확인하세요.'
            return None
        if self.party_stage in ('list','detail'):
            if o.screen not in ('list','detail'):
                self.state=State.LIST if self.party_stage=='list' else State.DETAIL
                self.reason='파티 반복 · 선택한 던전 목록·입장 설정 확인 대기'
                return None
            self.combat_latched=False;self.clear_clicked=False;self.clear_seen_at=None
        if self.party_stage=='entering' and o.screen in ('matching','loading','combat','cutscene'):
            self.repeats+=int(self.reward_since is not None);self.reward_since=None;self.party_stage=None
            self.party_entry_last=-999.;self.party_entry_attempts=0
        elif self.party_stage=='entering' and o.screen=='field':
            # A brief world HUD can be the old scene while the click is handled.
            # It proves neither matching nor a new dungeon entry.
            self.state=State.ENTERING;self.reason='파티 입장 요청 후 우연한 만남·로딩·전투 화면 확인 중'
            return None
        if o.screen in ('matching', 'loading'):
            self.reason='우연한 만남·던전 입장 화면 확인'
            self.clear_seen_at=None
            if self.state != State.ENTERING:
                self.repeats += int(self.reward_since is not None)
            self.state = State.ENTERING
            if self.entered_at is None:
                self.entered_at = now
            self.reward_since = None
            self.clear_clicked = False
            self.skip_clicked = False
            self.combat_latched = True
            self.still_since = None
            if now - self.entered_at > 240:
                self.state, self.reason = State.BLOCKED, '입장 대기가 4분을 넘었습니다. 화면을 확인하세요.'
            return None
        if o.screen == 'clear':
            if self.clear_seen_at is None:self.clear_seen_at=now
            self.state, self.combat_latched = State.CLEAR, True
            if self.clear_clicked:
                return None
            a = self.emit('clear', (400, 500), '클리어·터치 안내 확인 → 중앙 한 번 클릭', now)
            if a:
                self.clear_clicked = True
            return a
        if o.screen == 'cutscene':
            self.state, self.combat_latched = State.BOSS, True
            if self.skip_clicked:
                return None
            a = self.emit('skip', o.points.get('skip'), '장면 넘기기 → 보스방', now)
            if a:
                self.skip_clicked = True
            return a
        if o.screen == 'combat':
            self.reason='전투 화면 확인'
            if self.clear_clicked:
                self.state=State.CLEAR
                return None
            self.combat_latched = True
            self.state = State.BOSS if self.skip_clicked else State.COMBAT
            self.entered_at = None
            self.still_since = None
            self.clear_clicked = False
            return self.food_action(o, now)
        if o.screen == 'detail' and ((self.state == State.ENTERING and self.last_key == 'enter') or self.party_stage=='entering'):
            # The button can fail to react; recheck every condition before a bounded retry.
            self.state, self.combat_latched = State.DETAIL, False
        if self.combat_latched:
            # A stationary character, black frame or missing HUD must never reopen the menu.
            if o.screen == 'field':
                if self.state == State.ENTERING:
                    self.state = State.COMBAT
                    self.entered_at = None
                return self.food_action(o, now)
            return None
        if self.state == State.ENTERING:
            if self.entered_at is not None and now - self.entered_at > 240:
                self.state, self.reason = State.BLOCKED, '입장 후 화면을 확인할 수 없습니다.'
            elif o.screen == 'field':
                self.combat_latched, self.state = True, State.COMBAT
            return None
        if o.screen == 'detail':
            self.state = State.DETAIL
            self.reason='선택한 던전·함께하기·난이도·우연한 만남 확인'
            if o.dungeon != self.dungeon:
                self.state, self.reason = State.BLOCKED, '선택한 던전과 화면 이름이 다르거나 인식되지 않습니다.'
                return None
            if not o.together:
                return self.emit('together', o.points.get('together'), '함께하기 선택', now)
            if o.difficulty != self.difficulty:
                return self.emit('difficulty', o.points.get('difficulty'), self.difficulty + ' 선택', now)
            if o.encounter is False:
                return self.emit('encounter', o.points.get('encounter'), '우연한 만남 켜기', now)
            if o.encounter is not True:
                return None
            if self.party and self.party_stage=='entering':
                # Keep the entry retry budget through unknown frames and overlays.
                # Each attempt still rechecks dungeon, mode, difficulty and toggle.
                self.last_key='enter';self.last_at=self.party_entry_last;self.attempts=self.party_entry_attempts
            a = self.emit('enter', o.points.get('enter'), '입장 조건 확인 완료 → 입장하기', now)
            if a:
                self.state, self.entered_at = State.ENTERING, now
                self.combat_latched = True
                if self.party:
                    self.party_stage='entering';self.skip_clicked=False
                    self.party_entry_last=now;self.party_entry_attempts+=1
            return a
        if o.screen == 'list':
            self.reason='어비스 목록에서 설정한 목적지 확인'
            if o.dungeon and o.dungeon != self.dungeon:
                self.state,self.reason=State.BLOCKED,'목록의 던전 이름이 선택한 목적지와 다릅니다.'
                return None
            self.state = State.LIST
            action=self.emit('dungeon', o.points.get('dungeon'), self.dungeon + ' 선택', now)
            if action and self.party_stage=='list':self.party_stage='detail'
            return action
        if o.screen == 'menu':
            self.state = State.LIST
            return self.emit('abyss', o.points.get('abyss'), '메뉴 → 어비스', now)
        if o.screen == 'field':
            food = self.food_action(o, now)
            if food:return food
            self.state = State.IDLE
            if not o.still:
                self.still_since = None
                return self.food_action(o, now)
            if self.still_since is None:
                self.still_since = now
            if now - self.still_since >= 4.0:
                self.state = State.MENU
                return self.emit('menu', o.points.get('menu'), '4초 정지 확인 → 메뉴', now)
        else:
            self.still_since = None
        return None

    def survival_action(self,o,now):
        if o.screen=='dead':
            if self.dead_since is None:self.dead_since=now
            self.low_health_since=None;self.state=State.DEAD
            self.reason='행동 불능 · 주황색 여기서 부활 글씨 확인 중'
            if not o.points.get('revive') or now-self.revive_last<2.5:return None
            if self.revive_attempts>=3:
                self.state,self.reason=State.BLOCKED,'여기서 부활이 반응하지 않습니다. 부활 가능 횟수와 화면을 확인하세요.'
                return None
            self.revive_attempts+=1;self.revive_last=now;self.settle_until=now+.65
            return Action('revive',o.points['revive'],'행동 불능·주황색 여기서 부활 글씨 확인 → 부활')
        if self.dead_since is not None:
            if o.screen=='unknown':return None
            elapsed=now-self.dead_since
            if self.entered_at is not None:self.entered_at+=elapsed
            if self.clear_seen_at is not None:self.clear_seen_at+=elapsed
            self.dead_since=None;self.revive_attempts=0;self.revive_last=-999.
            self.state=State.SCAN;self.reason='부활 화면 닫힘 · 현재 화면 재확인'
        if o.screen not in ('combat','field','raid_inside') or not o.points.get('potion'):
            self.low_health_since=None
            return None
        if self.low_health_since is None:self.low_health_since=now
        if now-self.low_health_since<.15 or now-self.potion_last<10 or now<self.settle_until:return None
        self.potion_last=now;self.settle_until=now+.65
        return Action('potion',o.points['potion'],'체력 감소·F1 회복물약 확인 → 한 번 사용 (재사용 간격 10초)')

    def food_action(self, o, now):
        if not o.food:
            self.food_armed = True
            return None
        if self.food_armed and now - self.food_last >= 10:
            self.food_armed, self.food_last = False, now
            return Action('food', o.points['food'], '음식 아이콘 확인 → 한 번 클릭')
        return None

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
    def __init__(self, dungeon='허상의 정박지', difficulty='매우 어려움', repeat=True):
        self.dungeon, self.difficulty, self.repeat = dungeon, difficulty, repeat
        self.state = State.SCAN
        self.reason = ''
        self.still_since = None
        self.last_key, self.last_at = '', -999.0
        self.attempts = 0
        self.settle_until = 0.0
        self.entered_at = None
        self.combat_latched = False
        self.clear_clicked = False
        self.skip_clicked = False
        self.repeats = 0
        self.reward_since = None
        self.food_armed = True
        self.food_last = -999.0
        self.popup_since = None
        self.popup_last = -999.0
        self.popup_attempts = 0
        self.last_screen = None

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
        if o.screen == 'reward':
            self.state = State.REWARD if self.repeat else State.WAIT
            self.combat_latched = False
            if self.reward_since is None:
                self.reward_since = now
            if not self.repeat:
                return None
            a = self.emit('retry', o.points.get('retry'), '보상 → 다시 하기', now)
            if a:
                self.state = State.ENTERING
                self.entered_at = now
            return a
        if o.screen in ('matching', 'loading'):
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
            self.combat_latched = True
            self.state = State.BOSS if self.skip_clicked else State.COMBAT
            self.entered_at = None
            self.still_since = None
            self.clear_clicked = False
            return self.food_action(o, now)
        if o.screen == 'detail' and self.state == State.ENTERING and self.last_key == 'enter':
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
            a = self.emit('enter', o.points.get('enter'), '입장 조건 확인 완료 → 입장하기', now)
            if a:
                self.state, self.entered_at = State.ENTERING, now
                self.combat_latched = True
            return a
        if o.screen == 'list':
            self.state = State.LIST
            return self.emit('dungeon', o.points.get('dungeon'), self.dungeon + ' 선택', now)
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

    def food_action(self, o, now):
        if not o.food:
            self.food_armed = True
            return None
        if self.food_armed and now - self.food_last >= 10:
            self.food_armed, self.food_last = False, now
            return Action('food', o.points['food'], '음식 아이콘 확인 → 한 번 클릭')
        return None

"""Responsive menu polling; retain slower capture cadence during combat."""

from random import uniform


def poll_interval(screen):
    return .07 if screen in ('menu','list','raid_menu','raid_list') else .12 if screen in ('detail','raid_detail') else .25


def click_settle(key):
    return .20 if key=='abyss' else .35 if key=='dungeon' else .65


def same_detection(previous,current):
    if previous is None or previous.screen!=current.screen:return False
    if current.screen in ('list','raid_list'):
        a=previous.points.get('dungeon');b=current.points.get('dungeon')
        return a is not None and b is not None and max(abs(x-y) for x,y in zip(a,b))<=6
    return True


class UltimateTiming:
    def __init__(self):
        self.remaining = uniform(7, 14)
        self.last_active = None

    def pause(self):
        self.last_active = None

    def ready(self, now, *, active, can_click):
        if not active:
            self.pause()
            return False

        if self.last_active is not None:
            self.remaining -= now - self.last_active
        self.last_active = now
        return can_click and self.remaining <= 0

    def clicked(self):
        self.remaining = uniform(7, 14)

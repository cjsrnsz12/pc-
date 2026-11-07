"""One pointer preparation per Abyss-list visit, followed by fresh recognition."""

LIST_PARK_POINT=(400,350)
RAID_PARK_POINT=(400,500)


class ListCentering:
    def __init__(self):
        self.prepared=False
        self.frames=0

    def observe(self,screen):
        if screen=='list':self.frames+=1
        else:
            self.frames=0
            # A brief missing frame or mission overlay is not a new list visit.
            if screen not in ('unknown','mission'):self.prepared=False
        return screen=='list' and self.frames>=2 and not self.prepared

    def completed(self):
        self.prepared=True
        self.frames=0


class RaidEntryCentering:
    """Park once per verified raid entry; HUD gaps and revival are the same run."""
    def __init__(self):
        self.prepared=False;self.frames=0

    def observe(self,screen,entered=False):
        inside=screen=='raid_inside' or (screen=='combat' and entered)
        if inside:self.frames+=1
        else:
            self.frames=0
            if screen in ('raid_boat','raid_detail','raid_return','raid_travel','raid_list','raid_menu'):
                self.prepared=False
        return inside and self.frames>=2 and not self.prepared

    def completed(self):
        self.prepared=True;self.frames=0


def smooth_move(start,target,emit,ready,wait,steps=20):
    for step in range(1,steps+1):
        if not ready():return False
        t=step/steps
        ease=t*t*(3-2*t)
        point=tuple(round(a+(b-a)*ease) for a,b in zip(start,target))
        emit(point)
        if wait(.016):return False
    return ready()

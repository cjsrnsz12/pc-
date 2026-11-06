"""Pause unavailable game capture, preserving dungeon timers until it is visible."""

def within_desktop(client,bounds):
    x,y,w,h=client;left,top,right,bottom=bounds
    return w>0 and h>0 and x>=left and y>=top and x+w<=right and y+h<=bottom


class CapturePause:
    def __init__(self):self.since=None;self.reason=None

    def hold(self,reason,now):
        changed=self.reason!=reason
        if self.since is None:self.since=now
        self.reason=reason
        return changed

    def resume(self,now):
        if self.since is None:return None
        elapsed=max(0,now-self.since)
        self.since=None;self.reason=None
        return elapsed

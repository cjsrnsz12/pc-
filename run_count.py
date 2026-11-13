"""Completed runs in one Start-to-Stop session, independent of click retries."""
from engine import State


class RunCount:
    def __init__(self):
        self.total=0
        self._completed_cycle=None

    def observe(self,screen,controller):
        if controller.state==State.BLOCKED or getattr(controller,'wipe_stage',None):return False
        completed=screen in ('clear','reward','raid_reward','raid_weekend','raid_return')
        # The same skip button is also shown during departure. Count only the
        # controller-verified boss-defeat scene, never the departure animation.
        if screen=='raid_cutscene':completed=getattr(controller,'phase',None)=='aftermath'
        cycle=(getattr(controller,'wipe_recoveries',0),controller.repeats)
        if not completed or cycle==self._completed_cycle:return False
        self._completed_cycle=cycle
        self.total+=1
        return True

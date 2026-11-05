"""Responsive menu polling; retain slower capture cadence during combat."""

def poll_interval(screen):
    return .07 if screen in ('menu','list') else .12 if screen=='detail' else .25


def click_settle(key):
    return .20 if key=='abyss' else .35 if key=='dungeon' else .65


def same_detection(previous,current):
    if previous is None or previous.screen!=current.screen:return False
    if current.screen=='list':
        a=previous.points.get('dungeon');b=current.points.get('dungeon')
        return a is not None and b is not None and max(abs(x-y) for x,y in zip(a,b))<=6
    return True

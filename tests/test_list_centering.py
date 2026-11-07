from list_centering import ListCentering,smooth_move


def test_center_once_per_visit_and_rearm_after_detail():
    c=ListCentering()
    assert not c.observe('list')
    assert c.observe('list')
    c.completed()
    for s in ['list','unknown','list','mission','list','list']:assert not c.observe(s)
    assert not c.observe('detail')
    assert not c.observe('list')
    assert c.observe('list')


def test_only_list_can_request_smooth_centering():
    c=ListCentering()
    for s in ['menu','detail','combat','cutscene','clear','reward','matching','loading','field','unknown']:
        assert not c.observe(s) and not c.observe(s)


def test_interrupted_move_is_not_marked_complete():
    c=ListCentering();c.observe('list')
    assert c.observe('list') and c.observe('list')
    c.completed();assert not c.observe('list')


def test_smooth_move_uses_small_steps_and_finishes_at_center_without_clicking():
    points=[];waits=[]
    assert smooth_move((0,0),(400,500),points.append,lambda:True,lambda dt:waits.append(dt) or False)
    assert len(points)==20 and points[-1]==(400,500)
    assert all(a[0]<=b[0] and a[1]<=b[1] for a,b in zip(points,points[1:]))
    assert points[0]!=(400,500) and max(b[0]-a[0] for a,b in zip(points,points[1:]))<40
    assert abs(sum(waits)-.32)<.001


def test_focus_change_or_stop_interrupts_without_final_jump():
    points=[]
    assert not smooth_move((0,0),(400,500),points.append,lambda:len(points)<3,lambda _:False)
    assert len(points)==3 and points[-1]!=(400,500)
    points.clear()
    assert not smooth_move((0,0),(400,500),points.append,lambda:True,lambda _:True)
    assert len(points)==1


def test_raid_entry_parks_once_and_preserves_latch_across_combat_revive_and_popups():
    from list_centering import RaidEntryCentering,RAID_PARK_POINT
    assert RAID_PARK_POINT==(400,500)
    c=RaidEntryCentering()
    assert not c.observe('raid_inside') and c.observe('raid_inside')
    # An interrupted movement stays pending until completed.
    assert c.observe('raid_inside');c.completed()
    for screen in ['raid_inside','unknown','mission','raid_inside','dead','raid_inside','combat','raid_cutscene','raid_reward','raid_weekend','raid_inside']:
        assert not c.observe(screen)
    assert not c.observe('raid_return')
    assert not c.observe('raid_boat')
    assert not c.observe('raid_inside') and c.observe('raid_inside')


def test_other_screens_and_abyss_never_request_raid_entry_centering():
    from list_centering import RaidEntryCentering
    c=RaidEntryCentering()
    for screen in ['field','list','detail','combat','raid_menu','raid_list','raid_detail','raid_boat','raid_cutscene','raid_reward','dead']:
        assert not c.observe(screen) and not c.observe(screen)


def test_confirmed_generic_combat_also_parks_once_when_goal_is_hidden():
    from list_centering import RaidEntryCentering
    c=RaidEntryCentering()
    assert not c.observe('combat')
    assert not c.observe('combat',entered=True)
    assert c.observe('combat',entered=True)
    c.completed()
    for _ in range(5):assert not c.observe('combat',entered=True)

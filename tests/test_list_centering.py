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

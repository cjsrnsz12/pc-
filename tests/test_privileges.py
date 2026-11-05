from privileges import permission_advice,process_elevated


def test_elevated_game_requires_matching_app_rights():
    d=permission_advice('창 맞추기',False,True)
    assert d['can_elevate']
    assert 'UAC' in d['message'] and '예' in d['message']


def test_access_denied_five_explains_admin_option_without_claiming_cause():
    d=permission_advice('창 맞추기',False,None,error_code=5)
    assert d['can_elevate']
    assert '원인일 수' in d['message']


def test_already_elevated_app_is_not_told_to_elevate_again():
    d=permission_advice('창 맞추기',True,True,error_code=5)
    assert not d['can_elevate']
    assert '이미 관리자' in d['message']


def test_folder_access_suggests_writable_folder_not_admin():
    d=permission_advice('업데이트',False,True,file_access=True)
    assert not d['can_elevate']
    assert '사용자 폴더' in d['message']


def test_matching_normal_rights_need_no_extra_permission():
    d=permission_advice('조작',False,False)
    assert not d['can_elevate']
    assert '추가 관리자 권한이 필요한 것으로 판단되지 않습니다' in d['message']

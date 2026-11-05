from release_notes import latest_notes,grouped_changes
from updates import parse_release


def test_only_matching_version_is_displayed():
    body='# v1.0.7\n## 새 기능\n- 알림창 표시\n## 버그 수정\n- 버튼 오류 해결\n\n# v1.0.6\n- 오래된 기능\n# v1.0.5\n- 더 오래된 기능'
    notes=latest_notes(body,'v1.0.7')
    assert '알림창' in notes and '버튼 오류' in notes
    assert '오래된' not in notes
    groups=grouped_changes(notes)
    assert groups['new']==['알림창 표시'] and groups['fix']==['버튼 오류 해결']


def test_section_without_blank_line_is_not_lost():
    notes=latest_notes('# v1.0.7\n## 개선\n- 진행률 표시\n# v1.0.6\n- 과거','1.0.7')
    assert notes.startswith('## 개선')
    assert grouped_changes(notes)['improvement']==['진행률 표시']


def test_missing_version_does_not_show_old_history():
    notes=latest_notes('# v1.0.6\n- 과거','v1.0.7')
    assert '과거' not in notes


def test_explicit_categories_and_unstructured_legacy_notes():
    groups=grouped_changes('- [새 기능] 설정 추가\n- [개선] 안내 가독성\n- [버그 수정] 클릭 오류 수정')
    assert groups=={'new':['설정 추가'],'improvement':['안내 가독성'],'fix':['클릭 오류 수정']}


def test_current_version_notes_are_available_without_install_action():
    d={'tag_name':'v1.0.7','html_url':'https://github.com/cjsrnsz12/pc-/releases/tag/v1.0.7','assets':[{'name':'AbyssHelper.exe'}],'body':'# v1.0.7\n## 개선\n- 현재 변경\n# v1.0.6\n- 과거'}
    assert parse_release(d,current='1.0.7') is None
    parsed=parse_release(d,current='1.0.7',include_current=True)
    assert parsed['is_new'] is False and '과거' not in parsed['notes']

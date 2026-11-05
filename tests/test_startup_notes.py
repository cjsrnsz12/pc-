import json
import pytest
from startup_notes import needs_notice,installed_release,mark_shown


def test_notice_persists_across_launches_and_returns_for_next_version(tmp_path):
    path=tmp_path/'release-notice.json'
    assert needs_notice(path,'1.0.18')
    mark_shown(path,'v1.0.18')
    assert not needs_notice(path,'1.0.18')
    assert not needs_notice(path,'v1.0.18')
    assert needs_notice(path,'1.0.19')
    mark_shown(path,'1.0.19')
    assert not needs_notice(path,'1.0.19')

@pytest.mark.parametrize('body',['bad','[]','null','{}','{"last_shown_version":"bad"}'])
def test_corrupt_notice_state_does_not_crash_or_suppress_notes(tmp_path,body):
    path=tmp_path/'state.json';path.write_text(body)
    assert needs_notice(path,'1.0.18')

def test_bundled_notes_use_installed_version_even_when_newer_release_exists(tmp_path):
    path=tmp_path/'release_notes.md'
    path.write_text('# v1.0.19\n## 개선\n- 다음 버전\n# v1.0.18\n## 버그 수정\n- 이번 버전\n# v1.0.17\n- 과거 버전',encoding='utf-8')
    release=installed_release(path,'1.0.18')
    assert release['is_new'] is False and release['installed_notice']
    assert '이번 버전' in release['notes'] and '다음 버전' not in release['notes'] and '과거' not in release['notes']
    with pytest.raises(ValueError):installed_release(path,'1.0.16')

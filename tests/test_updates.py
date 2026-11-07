import pytest
from updates import version_tuple, parse_release, release_url


def test_semantic_version_order():
    assert version_tuple('v1.10.0')>version_tuple('1.9.9')
    for value in ['1.0.0-preview','x','1.2','1.2.3.4']:
        with pytest.raises(ValueError):version_tuple(value)


def test_update_only_when_binary_is_published():
    d={'tag_name':'v1.1.0','html_url':'https://github.com/cjsrnsz12/pc-/releases/tag/v1.1.0','body':'수정','assets':[]}
    assert parse_release(d,current='1.0.0') is None
    d['assets']=[{'name':'AbyssHelper.exe'}]
    assert parse_release(d,current='1.0.0')['version']=='v1.1.0'
    assert parse_release(d,current='1.2.0') is None
    d['prerelease']=True
    assert parse_release(d,current='1.0.0') is None


def test_urls_are_restricted_to_this_repository():
    assert release_url('https://github.com/cjsrnsz12/pc-/releases/tag/v1.0.0')
    for url in ['http://github.com/cjsrnsz12/pc-/releases/latest','https://evil.test/a','https://github.com/cjsrnsz12/other/releases/latest','https://github.com.evil.test/cjsrnsz12/pc-/releases/latest']:
        assert not release_url(url)

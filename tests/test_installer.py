import json
from pathlib import Path
import pytest
import installer


def setup_plan(tmp_path):
    root=tmp_path/'installed';root.mkdir()
    target=root/'AbyssHelper.exe';target.write_bytes(b'MZ-old-version')
    session=tmp_path/'session-new';session.mkdir()
    staged=session/'new.exe';staged.write_bytes(b'MZ-new-version')
    path=installer.prepare_install(staged,target,'1.0.4',12345)
    return json.loads(path.read_text()),target,staged


def test_transaction_installs_and_confirms_new_version(tmp_path):
    plan,target,_=setup_plan(tmp_path)
    def confirmed(p):
        assert Path(p['target']).read_bytes()==b'MZ-new-version'
        return True
    assert installer.install_transaction(plan,confirmed)==target
    assert target.read_bytes()==b'MZ-new-version'
    assert not list(target.parent.glob('.abyss-*'))


def test_failed_start_rolls_back_old_file(tmp_path):
    plan,target,_=setup_plan(tmp_path)
    with pytest.raises(installer.InstallError,match='이전 버전으로 복구'):
        installer.install_transaction(plan,lambda _:False)
    assert target.read_bytes()==b'MZ-old-version'
    assert not list(target.parent.glob('.abyss-*'))


def test_replace_failure_restores_backup(tmp_path,monkeypatch):
    plan,target,_=setup_plan(tmp_path)
    original=installer.replace_retry
    def fail_new(source,destination,**kwargs):
        if Path(source).name.startswith('.abyss-new-'):raise PermissionError('locked')
        return original(source,destination,**kwargs)
    monkeypatch.setattr(installer,'replace_retry',fail_new)
    with pytest.raises(PermissionError):installer.install_transaction(plan,lambda _:True)
    assert target.read_bytes()==b'MZ-old-version'


def test_tampered_download_never_changes_installed_file(tmp_path):
    plan,target,staged=setup_plan(tmp_path);staged.write_bytes(b'MZ-altered')
    with pytest.raises(installer.InstallError):installer.install_transaction(plan,lambda _:True)
    assert target.read_bytes()==b'MZ-old-version'


def test_changed_installed_file_not_overwritten(tmp_path):
    plan,target,_=setup_plan(tmp_path);target.write_bytes(b'MZ-another-updater')
    with pytest.raises(installer.InstallError):installer.install_transaction(plan,lambda _:True)
    assert target.read_bytes()==b'MZ-another-updater'


def test_plan_cannot_stage_outside_session(tmp_path):
    plan,_,staged=setup_plan(tmp_path);plan['ready']=str(tmp_path/'outside.json')
    with pytest.raises(installer.InstallError):installer.validate_plan(plan,staged.parent)

"""Installed-version notes are bundled and shown once per version, without network IO."""
import json
import os
from pathlib import Path
from release_notes import latest_notes,grouped_changes
from updates import version_tuple


def needs_notice(state_path,version):
    current=version_tuple(version)
    try:
        saved=json.loads(Path(state_path).read_text(encoding='utf-8'))
        return version_tuple(saved['last_shown_version'])!=current
    except (OSError,ValueError,KeyError,TypeError):
        return True


def installed_release(notes_path,version):
    notes=latest_notes(Path(notes_path).read_text(encoding='utf-8'),version)
    if not notes:raise ValueError('현재 버전의 업데이트 내용이 없습니다.')
    return {'version':'v'+version.lstrip('v'),'notes':notes,'changes':grouped_changes(notes),'is_new':False,'installed_notice':True}


def mark_shown(state_path,version):
    path=Path(state_path);path.parent.mkdir(parents=True,exist_ok=True)
    staged=path.with_name(path.name+'.tmp')
    staged.write_text(json.dumps({'last_shown_version':version.lstrip('v')},ensure_ascii=False),encoding='utf-8')
    os.replace(staged,path)

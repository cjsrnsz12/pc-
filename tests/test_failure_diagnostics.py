import json
import cv2
import numpy as np
import pytest
from failure_diagnostics import save_failure


def test_local_capture_and_metadata_are_bounded_and_overwritten(tmp_path):
    frame=np.zeros((1000,800,3),np.uint8)
    image,info=save_failure(tmp_path,frame,{'dpi':120,'reason':'unknown'})
    assert cv2.imread(str(image)).shape==frame.shape
    assert json.loads(info.read_text())['dpi']==120
    save_failure(tmp_path,frame,{'dpi':96})
    assert len(list(tmp_path.iterdir()))==2 and json.loads(info.read_text())=={'dpi':96}


def test_only_game_client_size_is_saved(tmp_path):
    with pytest.raises(ValueError):save_failure(tmp_path,np.zeros((1200,1920,3),np.uint8),{})
    assert not list(tmp_path.iterdir())


def test_unknown_template_scores_are_available_without_changing_thresholds():
    from pathlib import Path
    from vision import Vision
    v=Vision(Path(__file__).resolve().parents[1]/'assets.json')
    assert v.observe(np.zeros((1000,800,3),np.uint8),'허상의 정박지','매우 어려움').screen=='unknown'
    assert 'menu_close' in v.scores and 'list_title' in v.scores
    assert v.scores['list_title']<v.data['list_title']['threshold']


def test_korean_log_bundle_contains_log_and_error_screen_together(tmp_path):
    import zipfile
    from failure_diagnostics import create_bundle,LOG_FILENAME
    from datetime import datetime
    text=datetime.now().strftime('%Y-%m-%d %H:%M:%S')+' INFO 오류 기록\n'
    (tmp_path/LOG_FILENAME).write_text(text,encoding='utf-8')
    save_failure(tmp_path/'diagnostics',np.zeros((1000,800,3),np.uint8),{'reason':'after_clear'})
    path=create_bundle(tmp_path)
    assert path.name=='로그 파일.zip'
    with zipfile.ZipFile(path) as archive:
        assert set(archive.namelist())=={LOG_FILENAME,'오류 화면.png','오류 정보.json'}
        assert archive.read(LOG_FILENAME).decode()==text
        assert json.loads(archive.read('오류 정보.json'))['reason']=='after_clear'


def test_legacy_log_can_be_exported_with_requested_filename(tmp_path):
    import zipfile
    from failure_diagnostics import create_bundle
    from datetime import datetime
    text=datetime.now().strftime('%Y-%m-%d %H:%M:%S')+' INFO legacy\n'
    (tmp_path/'app.log').write_text(text)
    with zipfile.ZipFile(create_bundle(tmp_path)) as archive:
        assert archive.read('로그 파일.log').decode()==text

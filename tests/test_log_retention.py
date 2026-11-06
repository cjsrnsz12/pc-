from datetime import datetime,timedelta
import logging
import os
import zipfile
from log_retention import DailyRetentionHandler,LOG_FILENAME,retained_text,cleanup_artifacts


def test_today_only_including_tracebacks_and_not_sliding_yesterday():
    now=datetime(2026,11,7,1,0)
    text='2026-11-06 23:59:59 ERROR old\nold traceback\n2026-11-07 00:00:01 ERROR new\nnew traceback\n'
    assert retained_text(text,now)=='2026-11-07 00:00:01 ERROR new\nnew traceback\n'
    assert retained_text(text,now+timedelta(days=1))==''


def test_startup_removes_old_records_even_when_file_modified_today(tmp_path):
    now=datetime(2026,11,7,13,0)
    path=tmp_path/LOG_FILENAME
    path.write_text('2026-11-06 23:00:00 INFO old\n2026-11-07 01:00:00 INFO keep\n')
    (tmp_path/'app.log.1').write_text('2026-11-06 23:00:00 INFO old\n')
    handler=DailyRetentionHandler(tmp_path,clock=lambda:now)
    try:
        assert path.read_text()=='2026-11-07 01:00:00 INFO keep\n'
        assert not (tmp_path/'app.log.1').exists()
    finally:handler.close()


def test_open_handler_can_purge_at_midnight_without_new_messages(tmp_path):
    clock=[datetime(2026,11,7,23,59,59)]
    handler=DailyRetentionHandler(tmp_path,clock=lambda:clock[0])
    handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
    record=logging.LogRecord('test',logging.INFO,'',0,'old',(),None)
    record.created=clock[0].timestamp()
    handler.handle(record);handler.flush()
    assert 'old' in (tmp_path/LOG_FILENAME).read_text()
    clock[0]=datetime(2026,11,8,0,0,1);handler.purge()
    assert (tmp_path/LOG_FILENAME).read_text()==''
    record.created=clock[0].timestamp();record.msg='new'
    handler.handle(record);handler.flush()
    assert 'new' in (tmp_path/LOG_FILENAME).read_text()
    handler.close()


def test_stale_error_pair_and_zip_removed_but_settings_untouched(tmp_path):
    now=datetime(2026,11,7,1,0);old=(now-timedelta(hours=2)).timestamp()
    folder=tmp_path/'diagnostics';folder.mkdir()
    paths=[folder/'last-unrecognized.png',folder/'last-unrecognized.json',tmp_path/'로그 파일.zip']
    for path in paths:path.write_text('old');os.utime(path,(old,old))
    settings=tmp_path/'settings.json';settings.write_text('keep');os.utime(settings,(old,old))
    cleanup_artifacts(tmp_path,now)
    assert all(not p.exists() for p in paths) and settings.read_text()=='keep'


def test_export_cannot_reintroduce_yesterday_from_legacy_logs(tmp_path):
    from failure_diagnostics import create_bundle
    now=datetime.now();old=now-timedelta(days=1)
    text=old.strftime('%Y-%m-%d %H:%M:%S')+' INFO old\n'+now.strftime('%Y-%m-%d %H:%M:%S')+' INFO current\n'
    (tmp_path/LOG_FILENAME).write_text(text)
    with zipfile.ZipFile(create_bundle(tmp_path)) as archive:
        exported=archive.read(LOG_FILENAME).decode()
        assert 'current' in exported and 'old' not in exported


def test_midnight_cleanup_is_scheduled_before_regular_poll(tmp_path):
    now=datetime(2026,11,7,23,59,59,500000)
    handler=DailyRetentionHandler(tmp_path,clock=lambda:now)
    try:assert handler.next_cleanup_ms()==501
    finally:handler.close()

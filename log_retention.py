"""Keep only this PC's current local day, never more than 24 hours."""
from datetime import datetime,timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re

LOG_FILENAME='로그 파일.log'
STAMP=re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}')


def cutoff(now):
    return max(now.replace(hour=0,minute=0,second=0,microsecond=0),now-timedelta(hours=24))


def retained_text(text,now):
    result=[];keep=False;start=cutoff(now)
    for line in text.splitlines(keepends=True):
        if STAMP.match(line):
            try:stamp=datetime.strptime(line[:19],'%Y-%m-%d %H:%M:%S');keep=stamp>=start and stamp.date()==now.date()
            except ValueError:keep=False
        if keep:result.append(line)
    return ''.join(result)


def log_paths(directory):
    root=Path(directory)
    return [root/(name+suffix) for name in (LOG_FILENAME,'app.log') for suffix in ('','.1','.2','.3')]


def cleanup_artifacts(directory,now):
    root=Path(directory);start=cutoff(now).timestamp()
    pair=[root/'diagnostics'/name for name in ('last-unrecognized.png','last-unrecognized.json')]
    existing=[p for p in pair if p.is_file()]
    if existing and any(p.stat().st_mtime<start for p in existing):
        for path in existing:path.unlink(missing_ok=True)
    for path in [root/'로그 파일.zip',root/'로그 파일.zip.tmp',root/'diagnostics'/'image.tmp',root/'diagnostics'/'metadata.tmp']:
        if path.is_file() and path.stat().st_mtime<start:path.unlink(missing_ok=True)


class DailyRetentionHandler(RotatingFileHandler):
    def __init__(self,directory,clock=datetime.now):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.clock=clock;self.last_cleanup=None
        super().__init__(self.directory/LOG_FILENAME,maxBytes=1_000_000,backupCount=3,encoding='utf-8',delay=True)
        self.purge(force=True)

    def purge(self,force=False):
        now=self.clock()
        if not force and self.last_cleanup is not None:
            elapsed=(now-self.last_cleanup).total_seconds()
            if now.date()==self.last_cleanup.date() and 0<=elapsed<30:return
        self.acquire()
        try:
            if self.stream is not None:self.stream.close();self.stream=None
            for path in log_paths(self.directory):
                if not path.is_file():continue
                original=path.read_text(encoding='utf-8-sig',errors='replace')
                kept=retained_text(original,now)
                if kept==original:continue
                if not kept and path.name!=LOG_FILENAME:path.unlink(missing_ok=True)
                else:
                    staged=path.with_name(path.name+'.retention.tmp')
                    staged.write_text(kept,encoding='utf-8');staged.replace(path)
            cleanup_artifacts(self.directory,now)
            self.last_cleanup=now
        finally:self.release()

    def next_cleanup_ms(self):
        now=self.clock()
        midnight=(now+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
        return max(1,min(30000,int((midnight-now).total_seconds()*1000)+1))

    def emit(self,record):
        try:self.purge()
        except OSError:pass
        super().emit(record)

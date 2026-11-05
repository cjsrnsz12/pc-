"""Update notification owns its UI state; installation exists only in this window."""
from dataclasses import dataclass
from pathlib import Path
import queue
import shutil
import sys
import threading
import time
import uuid
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from updates import download_release, DownloadCancelled
from installer import prepare_install, launch_installer
from release_notes import KINDS, grouped_changes
from version import VERSION
from ui_controls import smooth_buttons,RoundScrollbar
from dialog_layout import fit_dialog


@dataclass
class UpdateOperations:
    download: object=download_release
    prepare: object=prepare_install
    launch: object=launch_installer


class UpdateNotice:
    def __init__(self,app,release=None,operations=None):
        self.app=app;self.release=None;self.ops=operations or UpdateOperations()
        self.cancel=threading.Event();self.events=queue.Queue()
        self.phase='idle';self.closed=False;self.thread=None;self.session=None;self.saved=None
        self.dialog=tk.Toplevel(app.root);self.dialog.title('업데이트 소식');self.dialog.geometry('700x700')
        self.dialog.configure(bg='#0c1220');self.dialog.transient(app.root)
        self.dialog.protocol('WM_DELETE_WINDOW',self.close)
        frame=ttk.Frame(self.dialog,padding=24);frame.pack(fill='both',expand=True)
        self.footer=ttk.Frame(frame);self.footer.pack(side='bottom',fill='x')
        header=ttk.Frame(frame);header.pack(side='top',fill='x')
        self.heading=ttk.Label(header,text='업데이트 확인 중',font=('맑은 고딕',20,'bold'));self.heading.pack(anchor='w')
        self.version=ttk.Label(header,text='새 버전 정보를 가져오고 있습니다.',foreground='#9caccc');self.version.pack(anchor='w',pady=(8,10))
        legend=ttk.Frame(header);legend.pack(fill='x',pady=(0,8))
        for _,title,color in KINDS:ttk.Label(legend,text='● '+title,foreground=color).pack(side='left',padx=(0,18))
        notes_frame=ttk.Frame(frame);notes_frame.pack(fill='both',expand=True)
        self.notes=tk.Text(notes_frame,bg='#09101b',fg='#edf2ff',relief='flat',wrap='word',font=('맑은 고딕',10),padx=14,pady=12,state='disabled',height=6)
        self.notes.pack(side='left',fill='both',expand=True)
        self.scroll=RoundScrollbar(notes_frame,command=self.notes.yview,bg='#09101b');self.scroll.pack(side='right',fill='y');self.notes.configure(yscrollcommand=self.scroll.set)
        for kind,_,color in KINDS:
            self.notes.tag_configure(kind,foreground=color,spacing1=4,spacing3=8)
            self.notes.tag_configure(kind+'_heading',foreground=color,font=('맑은 고딕',12,'bold'),spacing1=12,spacing3=6)
        self.progress=ttk.Progressbar(self.footer,mode='determinate',maximum=100);self.progress.pack(fill='x',pady=(14,4))
        self.status=tk.StringVar(value='업데이트 확인 중…')
        self.status_label=ttk.Label(self.footer,textvariable=self.status,wraplength=600);self.status_label.pack(anchor='w',pady=(3,6))
        self.hint_label=ttk.Label(self.footer,text='이 버전의 변경 사항만 표시합니다. 업데이트 시 매크로는 중지되고 설정은 유지됩니다.',style='Muted.TLabel',wraplength=600);self.hint_label.pack(anchor='w')
        row=ttk.Frame(self.footer);row.pack(fill='x',pady=(14,0))
        self.primary=ttk.Button(row,text='업데이트',style='Start.TButton',state='disabled',command=self.begin);self.primary.pack(side='left')
        self.cancel_button=ttk.Button(row,text='다운로드 취소',command=self.request_cancel,state='disabled');self.cancel_button.pack(side='left',padx=8)
        self.close_button=ttk.Button(row,text='닫기',command=self.close);self.close_button.pack(side='right')
        extra=ttk.Frame(self.footer);extra.pack(fill='x',pady=(8,0))
        self.file_button=ttk.Button(extra,text='파일만 다운로드',command=lambda:self.begin(False),state='disabled');self.file_button.pack(side='left')
        self.folder_button=ttk.Button(extra,text='저장 폴더 열기',command=lambda:os.startfile(self.saved.parent),state='disabled');self.folder_button.pack(side='left',padx=8)
        self.dialog.bind('<Configure>',self.wrap_footer,add='+')
        smooth_buttons(self.dialog)
        if release:self.set_release(release)
        self.show();app.root.after(80,self.poll)

    def wrap_footer(self,event):
        if event.widget is self.dialog:
            width=max(240,event.width-48)
            self.status_label.configure(wraplength=width);self.hint_label.configure(wraplength=width)

    def show(self):
        if self.closed:return
        if self.app.root.state()=='iconic':self.app.root.deiconify()
        self.dialog.deiconify();self.dialog.lift()
        fit_dialog(self.app,self.dialog,(700,700),(520,440))
        self.dialog.attributes('-topmost',True)
        self.app.root.after(1800,lambda:self.dialog.attributes('-topmost',False) if not self.closed else None)

    def set_loading(self):
        if self.phase in ('downloading','preparing','installing'):
            self.show();return
        self.status.set('새 버전 확인 중… 잠시 기다려 주세요.');self.primary.configure(state='disabled')

    def set_release(self,release):
        if self.closed:return
        if self.phase in ('downloading','preparing','installing'):return
        self.release=release
        newer=release.get('is_new',True)
        self.heading.configure(text='업데이트가 필요합니다' if newer else '최신 버전을 사용 중입니다')
        self.version.configure(text=f"현재 v{VERSION}  →  {release['version']}" if newer else '현재 버전: '+release['version'])
        groups=release.get('changes') or grouped_changes(release.get('notes',''))
        self.notes.configure(state='normal');self.notes.delete('1.0','end')
        for kind,title,_ in KINDS:
            if not groups.get(kind):continue
            self.notes.insert('end',title+'\n',kind+'_heading')
            for content in groups[kind]:self.notes.insert('end','• '+content+'\n',kind)
        self.notes.configure(state='disabled')
        self.phase='idle';self.primary.configure(text='업데이트',state='normal' if newer else 'disabled',command=self.begin)
        self.file_button.configure(state='normal')
        self.status.set('업데이트를 누르면 다운로드·설치 후 새 버전으로 다시 실행합니다.' if newer else '표시된 내용은 현재 최신 버전에 적용된 변경 사항입니다.')

    def set_check_error(self,message):
        if self.closed:return
        self.status.set('업데이트 확인 실패: '+str(message));self.status_label.configure(foreground='#ff9da9')
        self.primary.configure(text='다시 확인',state='normal',command=lambda:self.app.update_check(True))

    def set_no_release(self):
        if self.closed:return
        self.heading.configure(text='새 배포 정보가 없습니다');self.status.set('배포 정보를 다시 확인하려면 다시 확인을 눌러 주세요.')
        self.primary.configure(text='다시 확인',state='normal',command=lambda:self.app.update_check(True))

    def begin(self,auto=True):
        if self.closed:return
        if self.phase in ('downloading','preparing','installing'):
            self.status.set('이미 업데이트를 진행하고 있습니다. 진행률을 확인해 주세요.');return
        if not self.release:
            self.status.set('아직 새 버전 정보를 확인하지 못했습니다. 다시 확인해 주세요.');return
        if auto and not self.release.get('is_new',True):
            self.status.set('현재 최신 버전이므로 설치할 업데이트가 없습니다.');return
        if self.app.installing:
            if any(t.is_alive() for t in self.app.download_workers):
                self.status.set('이전 업데이트 작업을 정리 중입니다. 잠시 후 다시 눌러 주세요.');return
            # Recover an orphaned UI busy flag instead of silently ignoring every click.
            self.app.installing=False
        if auto and not getattr(sys,'frozen',False):
            messagebox.showinfo('자동 업데이트','자동 설치는 배포된 EXE에서 지원합니다. 파일만 다운로드를 이용하세요.',parent=self.dialog);return
        self.session=None
        if auto:
            self.session=self.app.data_path/'updates'/('session-'+uuid.uuid4().hex)
            destination=self.session/'new.exe'
        else:
            folder=Path.home()/'Downloads'
            filename=filedialog.asksaveasfilename(parent=self.dialog,title='실행 파일 저장',initialdir=str(folder if folder.is_dir() else Path.home()),initialfile='AbyssHelper-'+self.release['version']+'.exe',defaultextension='.exe',filetypes=[('Windows 실행 파일','*.exe')])
            if not filename:return
            destination=Path(filename)
            if getattr(sys,'frozen',False) and destination.resolve()==Path(sys.executable).resolve():
                messagebox.showinfo('저장 위치','실행 중인 앱과 다른 파일명으로 저장하세요.',parent=self.dialog);return
        self.phase='downloading';self.cancel.clear();self.app.download_cancels.add(self.cancel)
        self.status_label.configure(foreground='#edf2ff');self.status.set('다운로드를 시작합니다. 서버 연결 중…')
        self.progress['value']=0;self.primary.configure(state='disabled');self.file_button.configure(state='disabled');self.cancel_button.configure(state='normal')
        if auto:
            self.app.installing=True;self.app.install_owner=self;self.app.stop();self.app.start_button.configure(state='disabled')
        self.app.log('업데이트 버튼 클릭: '+self.release['version']+(' / 자동 설치' if auto else ' / 파일 저장'))
        self.dialog.update_idletasks()
        def worker():
            last=0.
            def report(done,total):
                nonlocal last
                now=time.monotonic()
                if now-last>.1 or done==total:self.events.put(('progress',(done,total)));last=now
            try:
                if self.session:self.session.mkdir(parents=True,exist_ok=True)
                path=self.ops.download(self.release,destination,report,self.cancel)
                if self.cancel.is_set():raise DownloadCancelled()
                if auto:
                    self.events.put(('phase','설치 파일 검증 및 교체 준비 중…'))
                    plan=self.ops.prepare(path,sys.executable,self.release['version'],os.getpid())
                    if self.cancel.is_set():raise DownloadCancelled()
                    self.events.put(('ready',plan))
                else:self.events.put(('saved',path))
            except DownloadCancelled:self.events.put(('cancelled',None))
            except Exception as e:self.events.put(('error',e))
        self.thread=threading.Thread(target=worker,daemon=True)
        self.app.download_workers=[t for t in self.app.download_workers if t.is_alive()]+[self.thread]
        self.thread.start()

    def request_cancel(self):
        self.cancel.set();self.status.set('다운로드를 취소하는 중…');self.cancel_button.configure(state='disabled')

    def reset(self):
        if getattr(self.app,'install_owner',None) is self:
            self.app.installing=False;self.app.install_owner=None
            if not self.app.running and not self.app.sizing_busy:self.app.start_button.configure(state='normal')
        self.app.download_cancels.discard(self.cancel)
        if self.session:shutil.rmtree(self.session,ignore_errors=True)
        if not self.closed:
            self.primary.configure(text='업데이트 다시 시도',state='normal',command=self.begin)
            self.file_button.configure(state='normal');self.cancel_button.configure(state='disabled')

    def poll(self):
        for _ in range(100):
            try:kind,value=self.events.get_nowait()
            except queue.Empty:break
            if self.closed:
                self.reset();continue
            if kind=='progress':
                done,total=value;self.progress['value']=100*done/total
                self.status.set(f'다운로드 {100*done/total:.0f}%  ·  {done/1048576:.1f} / {total/1048576:.1f} MB')
            elif kind=='phase':self.phase='preparing';self.status.set(value)
            elif kind=='ready':
                if self.cancel.is_set():self.phase='cancelled';self.reset();continue
                try:
                    self.phase='installing';self.primary.configure(state='disabled');self.cancel_button.configure(state='disabled');self.close_button.configure(state='disabled')
                    self.status.set('앱을 종료하고 새 버전으로 교체합니다…');self.dialog.update_idletasks()
                    self.ops.launch(value);self.app.log('업데이트 설치 프로그램 시작');self.app.close();return
                except Exception as e:self.fail(e)
            elif kind=='saved':
                self.phase='saved';self.saved=Path(value);self.reset()
                self.progress['value']=100;self.status.set('다운로드 완료: '+str(value));self.folder_button.configure(state='normal')
            elif kind=='cancelled':self.phase='cancelled';self.reset();self.status.set('취소했습니다. 업데이트 버튼으로 다시 시도할 수 있습니다.')
            elif kind=='error':self.fail(value)
        if not self.closed or (self.thread and self.thread.is_alive()):self.app.root.after(80,self.poll)
        elif self.closed:self.reset()

    def fail(self,error):
        self.phase='failed';self.reset();self.status_label.configure(foreground='#ff9da9');self.status.set('업데이트 실패: '+str(error))
        self.app.log('업데이트 실패: '+str(error))
        if isinstance(error,PermissionError) or '쓰기 권한' in str(error):self.app.show_permission_notice('업데이트 파일 저장',error,file_access=True)
        else:messagebox.showerror('업데이트 실패',str(error)+'\n업데이트 다시 시도를 눌러 재시도할 수 있습니다.',parent=self.dialog)

    def close(self):
        if self.closed:return
        if self.phase=='installing':self.status.set('앱을 종료하고 설치 중입니다. 잠시 기다려 주세요.');return
        self.closed=True;self.cancel.set();self.dialog.destroy()
        if not self.thread or not self.thread.is_alive():self.reset()

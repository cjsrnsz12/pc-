"""Administrator archive window; workers never call Tk and never log keys."""
import queue,threading
import tkinter as tk
from tkinter import ttk
from admin_auth import AdminAPI,AdminSession,CredentialStore
from ui_controls import smooth_buttons,RoundScrollbar

LABELS={'pc':'PC','mobile':'모바일','tablet':'태블릿'}

class AdminWindow:
    def __init__(self,parent,sync,credential_path,api=None,store=None):
        self.api=api or AdminAPI(sync);self.session=AdminSession(store or CredentialStore(credential_path));self.alive=True;self.busy=False;self.revision=0;self.offset=0;self.total=0;self.results=queue.Queue();self.details_id=None;self.detail_text=''
        self.window=tk.Toplevel(parent);self.window.title('냐크로 · 관리자 설정');self.window.configure(bg='#0c1220');self.window.geometry(f"{min(800,parent.winfo_screenwidth()-48)}x{min(780,parent.winfo_screenheight()-100)}+24+24");self.window.protocol('WM_DELETE_WINDOW',self.close)
        shell=ttk.Frame(self.window,padding=18);shell.pack(fill='both',expand=True)
        ttk.Label(shell,text='관리자 설정 · 오류 보관함',font=('맑은 고딕',19,'bold')).pack(anchor='w')
        self.status=tk.StringVar(value='한 번 인증하면 이 PC에서 관리자 권한이 유지됩니다.');ttk.Label(shell,textvariable=self.status,wraplength=700).pack(fill='x',pady=10)
        self.login=ttk.Frame(shell);self.login.pack(fill='x');self.key=tk.StringVar();self.entry=ttk.Entry(self.login,textvariable=self.key,show='*');self.entry.pack(fill='x',pady=5);self.authenticate=ttk.Button(self.login,text='관리자 인증',command=self.login_key);self.authenticate.pack(fill='x',pady=5)
        self.archive=ttk.Frame(shell)
        toolbar=ttk.Frame(self.archive);toolbar.pack(fill='x');self.unread=tk.BooleanVar();ttk.Checkbutton(toolbar,text='읽지 않은 오류만',variable=self.unread,command=lambda:self.load(0)).pack(side='left');self.refresh_button=ttk.Button(toolbar,text='새로 고침',command=lambda:self.load(self.offset));self.refresh_button.pack(side='left',padx=6);self.logout_button=ttk.Button(toolbar,text='관리자 로그아웃',command=self.logout);self.logout_button.pack(side='right')
        pages=ttk.Frame(self.archive);pages.pack(fill='x',pady=6);self.page=tk.StringVar();ttk.Label(pages,textvariable=self.page).pack(side='left');ttk.Button(pages,text='다음',command=lambda:self.load(self.offset+20) if self.offset+20<self.total else None).pack(side='right');ttk.Button(pages,text='이전',command=lambda:self.load(max(0,self.offset-20))).pack(side='right',padx=6)
        self.table_host=ttk.Frame(self.archive);self.table_host.pack(fill='both',expand=True)
        self.table=ttk.Treeview(self.table_host,columns=('name','device','reason'),show='headings',height=8)
        for name,label,width in [('name','닉네임 / 읽음',170),('device','접속 기기',95),('reason','중지 원인',350)]:self.table.heading(name,text=label);self.table.column(name,width=width,minwidth=65)
        scroll=RoundScrollbar(self.table_host,command=self.table.yview);scroll.pack(side='right',fill='y');self.table.configure(yscrollcommand=scroll.set);self.table.pack(fill='both',expand=True);self.table.bind('<Double-1>',lambda _:self.open_selected())
        self.open_button=ttk.Button(self.table_host,text='선택한 오류 확인',command=self.open_selected);self.open_button.pack(fill='x',pady=6)
        self.detail=ttk.Frame(self.archive);text_host=ttk.Frame(self.detail);text_host.pack(fill='both',expand=True);self.text=tk.Text(text_host,bg='#101929',fg='#edf2ff',wrap='word',height=16,state='disabled');bar=RoundScrollbar(text_host,command=self.text.yview);bar.pack(side='right',fill='y');self.text.configure(yscrollcommand=bar.set);self.text.pack(fill='both',expand=True)
        actions=ttk.Frame(self.detail);actions.pack(fill='x',pady=6);ttk.Button(actions,text='목록으로',command=lambda:self.load(self.offset)).pack(side='left');ttk.Button(actions,text='오류 기록 복사',command=self.copy).pack(side='left',padx=6);ttk.Button(actions,text='읽음으로 표시',command=self.mark).pack(side='right')
        smooth_buttons(self.window);self.window.after(100,self.poll)
        threading.Thread(target=lambda:self.results.put(('restore',self.session.restore())),daemon=True).start()
    def login_key(self):
        if self.busy:return
        try:self.session.begin(self.key.get().strip())
        except ValueError as e:self.status.set(str(e));return
        self.load(0)
    def logout(self):
        self.revision+=1;self.busy=False;cleared=self.session.logout();self.key.set('');self.archive.pack_forget();self.login.pack(fill='x');self.table.delete(*self.table.get_children());self.detail_text='';self.text.configure(state='normal');self.text.delete('1.0','end');self.text.configure(state='disabled');self.status.set('이 PC의 관리자 인증을 해제했습니다.' if cleared else '인증 정보 삭제를 다시 확인해 주세요.')
    def request(self,op,done,offset=0,report_id=None):
        if self.busy or not self.alive:return
        self.busy=True;revision=self.revision;attempt=self.session.current();unread=self.unread.get();self.status.set('관리자 권한 확인 중…')
        def work():
            try:
                result=self.api.call(op,attempt[1],offset,unread,report_id);remembered=op!='admin_list_errors' or self.session.accepted(attempt);self.results.put(('ok',revision,done,result,remembered))
            except Exception as e:
                code=getattr(e,'code','');self.session.rejected(attempt,code);message=str(e) if isinstance(e,ValueError) or code else '관리자 서버 연결을 다시 확인해 주세요.';self.results.put(('error',revision,message,code))
        threading.Thread(target=work,name='NyacroAdmin',daemon=True).start()
    def load(self,offset=0):
        def loaded(result):
            self.offset=result['offset'];self.total=result['total'];self.login.pack_forget();self.key.set('');self.archive.pack(fill='both',expand=True);self.detail.pack_forget();self.table_host.pack(fill='both',expand=True);self.table.delete(*self.table.get_children());self.details_id=None;self.detail_text=''
            for row in result['reports']:self.table.insert('',tk.END,iid=row['id'],values=(('읽음 · ' if row.get('read') else '새 오류 · ')+row['nickname'],LABELS[row['device_type']],row['stop_reason']))
            self.page.set(f'{offset//20+1}페이지 · 전체 {self.total}건');self.status.set('관리자 오류 보관함 · 이 PC 인증 유지')
        self.request('admin_list_errors',loaded,offset)
    def open_selected(self):
        selection=self.table.selection()
        if not selection:return
        report_id=selection[0]
        def opened(result):
            row=result['report'];self.details_id=report_id;self.detail_text=f"{row['nickname']} · {LABELS[row['device_type']]}\n발생: {row.get('occurred_at','')}\n기기: {row.get('device_model','')} · {row.get('screen','')}\n버전: {row.get('app_version','')} · {row.get('content','')}\n\n중지 원인\n{row.get('stop_reason','')}\n\n오류 직전 진행 기록\n{row.get('logs','')}";self.table_host.pack_forget();self.detail.pack(fill='both',expand=True);self.text.configure(state='normal');self.text.delete('1.0','end');self.text.insert('end',self.detail_text);self.text.configure(state='disabled');self.status.set('관리자 오류 보관함 · 이 PC 인증 유지')
        self.request('admin_read_error',opened,report_id=report_id)
    def copy(self):
        self.window.clipboard_clear();self.window.clipboard_append(self.detail_text);self.status.set('오류 기록을 복사했습니다.')
    def mark(self):
        if self.details_id:self.request('admin_mark_read',lambda _:self.load(self.offset),report_id=self.details_id)
    def poll(self):
        if not self.alive:return
        for _ in range(20):
            try:item=self.results.get_nowait()
            except queue.Empty:break
            if item[0]=='restore':
                if item[1] and not self.busy:self.login.pack_forget();self.archive.pack(fill='both',expand=True);self.load(0)
            elif item[1]==self.revision:
                self.busy=False
                if item[0]=='ok':
                    item[2](item[3])
                    if not item[4]:self.status.set('관리자 인증은 완료됐지만 기기에 저장하지 못했습니다.')
                else:
                    if item[3]=='admin_required':self.archive.pack_forget();self.login.pack(fill='x');self.table.delete(*self.table.get_children());self.detail_text=''
                    self.status.set(item[2])
        self.window.after(100,self.poll)
    def close(self):self.alive=False;self.revision+=1;self.session.close();self.key.set('');self.window.destroy()

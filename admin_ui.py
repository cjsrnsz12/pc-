import json,queue,threading,tkinter as tk
from tkinter import ttk
from ui_controls import smooth_buttons,RoundScrollbar

class AdminWindow:
    def __init__(self,parent,diagnostics):
        self.service=diagnostics;self.alive=True;self.busy=False;self.events=queue.Queue();self.offset=0;self.total=0;self.current=None
        self.window=tk.Toplevel(parent);self.window.title('냐크로 · 관리자 설정');self.window.geometry('760x650');self.window.configure(bg='#0c1220');self.window.protocol('WM_DELETE_WINDOW',self.close)
        shell=ttk.Frame(self.window,padding=16);shell.pack(fill='both',expand=True)
        ttk.Label(shell,text='관리자 설정 · 오류 보관함',font=('맑은 고딕',18,'bold')).pack(anchor='w')
        self.consent=tk.BooleanVar(value=diagnostics.consent)
        ttk.Checkbutton(shell,text='오류 종료 시 텍스트 기록 전송에 동의',variable=self.consent,command=self.change_consent).pack(anchor='w',pady=8)
        ttk.Label(shell,text='닉네임·버전·PC 정보·콘텐츠·중지 사유·최근 30줄을 보냅니다. 화면은 보내지 않습니다. 전송 대기는 최대 20건이며 동의를 끄면 삭제합니다.',wraplength=710).pack(fill='x')
        auth=ttk.Frame(shell);auth.pack(fill='x',pady=10);self.key=tk.StringVar();ttk.Entry(auth,textvariable=self.key,show='•').pack(side='left',fill='x',expand=True)
        ttk.Button(auth,text='관리자 인증',command=self.login).pack(side='left',padx=5);ttk.Button(auth,text='로그아웃',command=self.logout).pack(side='left')
        self.status=tk.StringVar(value='인증된 기기는 앱 종료·업데이트 후에도 유지됩니다.');ttk.Label(shell,textvariable=self.status,wraplength=710).pack(fill='x')
        controls=ttk.Frame(shell);controls.pack(fill='x',pady=8);self.unread=tk.BooleanVar(value=True)
        ttk.Checkbutton(controls,text='읽지 않은 오류만',variable=self.unread,command=self.reset).pack(side='left')
        ttk.Button(controls,text='새로 고침',command=self.reset).pack(side='left',padx=8)
        ttk.Button(controls,text='이전',command=lambda:self.page(-20)).pack(side='right');ttk.Button(controls,text='다음',command=lambda:self.page(20)).pack(side='right',padx=5)
        table=ttk.Frame(shell);table.pack(fill='both',expand=True)
        self.table=ttk.Treeview(table,columns=('name','device','reason'),show='headings',height=5)
        for k,label,w in [('name','닉네임',120),('device','기기',80),('reason','중지 사유',450)]:self.table.heading(k,text=label);self.table.column(k,width=w)
        scroll=RoundScrollbar(table,command=self.table.yview);scroll.pack(side='right',fill='y');self.table.configure(yscrollcommand=scroll.set);self.table.pack(fill='both',expand=True);self.table.bind('<<TreeviewSelect>>',self.read)
        self.detail=tk.Text(shell,height=7,wrap='word',bg='#162136',fg='#edf2ff');self.detail.pack(fill='both',expand=True,pady=8);self.detail.configure(state='disabled')
        buttons=ttk.Frame(shell);buttons.pack(fill='x');ttk.Button(buttons,text='기록 복사',command=self.copy).pack(side='left');ttk.Button(buttons,text='읽음 표시',command=self.mark).pack(side='left',padx=8)
        smooth_buttons(self.window);self.window.after(100,self.poll)
        if diagnostics.key:self.reset()
    def task(self,work,kind):
        if self.busy:return
        self.busy=True;self.status.set('처리 중…')
        def run():
            try:self.events.put((kind,work(),None))
            except Exception as e:self.events.put((kind,None,str(e)))
        threading.Thread(target=run,daemon=True).start()
    def poll(self):
        if not self.alive:return
        try:
            kind,result,error=self.events.get_nowait();self.busy=False
            if error:self.status.set(error)
            elif kind=='list':
                self.table.delete(*self.table.get_children());self.total=result['total'];self.current=None;self.key.set('')
                for r in result['reports']:self.table.insert('',tk.END,iid=r['id'],values=(r['nickname'],{'pc':'PC','mobile':'모바일','tablet':'태블릿'}[r['device_type']],r['stop_reason']))
                self.status.set(f'{self.offset//20+1}페이지 · 전체 {self.total}건')
            elif kind=='read':
                self.current=result['report'];self.detail.configure(state='normal');self.detail.delete('1.0','end');self.detail.insert('1.0',json.dumps(self.current,ensure_ascii=False,indent=2));self.detail.configure(state='disabled');self.status.set('기록을 불러왔습니다.')
            elif kind=='consent':self.status.set('오류 전송 설정을 저장했습니다.')
            elif kind=='logout':self.status.set('관리자 로그아웃했습니다.');self.key.set('');self.table.delete(*self.table.get_children());self.current=None;self.detail.configure(state='normal');self.detail.delete('1.0','end');self.detail.configure(state='disabled')
            elif kind=='mark':self.reset()
        except queue.Empty:pass
        self.window.after(100,self.poll)
    def change_consent(self):
        if self.busy:self.consent.set(self.service.consent);return
        enabled=self.consent.get();self.task(lambda:self.service.set_consent(enabled),'consent')
    def login(self):
        key=self.key.get().strip();self.offset=0;unread=self.unread.get();self.task(lambda:self.service.admin('admin_list_errors',key,offset=0,unread_only=unread),'list')
    def reset(self):self.offset=0;self.load()
    def load(self):
        offset=self.offset;unread=self.unread.get();self.task(lambda:self.service.admin('admin_list_errors',offset=offset,unread_only=unread),'list')
    def page(self,delta):
        if self.busy:return
        offset=self.offset+delta
        if offset<0 or offset>=self.total:return
        self.offset=offset;self.load()
    def read(self,event=None):
        selected=self.table.selection()
        if selected:self.task(lambda:self.service.admin('admin_read_error',report_id=selected[0]),'read')
    def mark(self):
        if self.current:
            rid=self.current['id'];self.task(lambda:self.service.admin('admin_mark_read',report_id=rid),'mark')
    def copy(self):
        if self.current:self.window.clipboard_clear();self.window.clipboard_append(json.dumps(self.current,ensure_ascii=False,indent=2));self.status.set('기록을 복사했습니다.')
    def logout(self):self.task(self.service.logout,'logout')
    def close(self):self.alive=False;self.window.destroy()

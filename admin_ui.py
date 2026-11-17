import json,queue,threading,tkinter as tk
from tkinter import ttk
from ui_controls import smooth_buttons,RoundScrollbar

class AdminWindow:
    def __init__(self,parent,session,diagnostics):
        self.session=session;self.diagnostics=diagnostics;self.alive=True;self.busy=False;self.offset=0;self.total=0;self.events=queue.Queue();self.detail='';self.generation=0
        self.window=tk.Toplevel(parent);self.window.title('냐크로 · 관리자 설정 / 오류 보관함');self.window.geometry('760x650');self.window.minsize(560,480);self.window.protocol('WM_DELETE_WINDOW',self.close)
        shell=ttk.Frame(self.window,padding=18);shell.pack(fill='both',expand=True)
        ttk.Label(shell,text='관리자 설정 · 오류 보관함',font=('맑은 고딕',18,'bold')).pack(anchor='w')
        self.consent=tk.BooleanVar(value=diagnostics.state['consent'])
        ttk.Checkbutton(shell,text='오류로 멈출 때 진단 기록 전송에 동의',variable=self.consent,command=self.change_consent).pack(anchor='w',pady=6)
        ttk.Label(shell,text='닉네임·PC·버전·해상도·콘텐츠·중지 사유와 최근 30줄만 전송합니다. 화면 캡처는 전송하지 않습니다.',wraplength=690).pack(fill='x')
        auth=ttk.Frame(shell);auth.pack(fill='x',pady=8)
        self.key=tk.StringVar();ttk.Entry(auth,textvariable=self.key,show='•').pack(side='left',fill='x',expand=True)
        ttk.Button(auth,text='인증 / 새로 고침',command=self.load).pack(side='left',padx=5)
        ttk.Button(auth,text='관리자 로그아웃',command=self.logout).pack(side='right')
        controls=ttk.Frame(shell);controls.pack(fill='x')
        self.unread=tk.BooleanVar(value=True);ttk.Checkbutton(controls,text='읽지 않은 오류만',variable=self.unread,command=self.reset).pack(side='left')
        ttk.Button(controls,text='이전',command=lambda:self.page(-20)).pack(side='right');ttk.Button(controls,text='다음',command=lambda:self.page(20)).pack(side='right')
        self.status=tk.StringVar(value='닉네임 설정 후 관리자 키로 인증해 주세요. 인증은 이 Windows 사용자에 암호화 저장됩니다.')
        ttk.Label(shell,textvariable=self.status,wraplength=690).pack(fill='x',pady=6)
        table=ttk.Frame(shell);table.pack(fill='both',expand=True)
        self.table=ttk.Treeview(table,columns=('name','device','reason'),show='headings',height=5)
        for key,label,width in [('name','닉네임',130),('device','기기',70),('reason','중지 사유',400)]:self.table.heading(key,text=label);self.table.column(key,width=width,minwidth=50)
        scroll=RoundScrollbar(table,command=self.table.yview);scroll.pack(side='right',fill='y');self.table.configure(yscrollcommand=scroll.set);self.table.pack(fill='both',expand=True);self.table.bind('<<TreeviewSelect>>',self.read)
        self.text=tk.Text(shell,height=9,wrap='word',state='disabled');self.text.pack(fill='both',expand=True,pady=8)
        buttons=ttk.Frame(shell);buttons.pack(fill='x')
        ttk.Button(buttons,text='상세 복사',command=self.copy).pack(side='left');ttk.Button(buttons,text='읽음 표시',command=self.mark).pack(side='right')
        smooth_buttons(self.window);self.window.after(100,self.poll)
        if session.key:self.load()
    def change_consent(self):
        try:self.diagnostics.consent(self.consent.get());self.status.set('진단 전송 설정을 저장했습니다.')
        except OSError:self.consent.set(self.diagnostics.state['consent']);self.status.set('진단 전송 설정을 저장할 수 없습니다.')
    def action(self,op,**fields):
        if self.busy:return
        self.busy=True;key=self.key.get().strip() or None;self.key.set('');self.status.set('확인 중…');generation=self.generation
        def work():
            try:self.events.put((generation,op,self.session.request(op,key=key,**fields),None))
            except Exception as error:self.events.put((generation,op,None,error))
        threading.Thread(target=work,daemon=True).start()
    def load(self):self.action('admin_list_errors',offset=self.offset,unread_only=self.unread.get())
    def reset(self):self.offset=0;self.load()
    def page(self,delta):
        if self.busy:return
        offset=max(0,self.offset+delta)
        if offset and offset>=self.total:return
        self.offset=offset;self.load()
    def read(self,event=None):
        selected=self.table.selection()
        if selected:self.action('admin_read_error',report_id=selected[0])
    def mark(self):
        selected=self.table.selection()
        if selected:self.action('admin_mark_read',report_id=selected[0])
    def copy(self):
        if self.detail:self.window.clipboard_clear();self.window.clipboard_append(self.detail)
    def logout(self):
        self.generation+=1;self.busy=False;self.key.set('')
        try:self.session.logout()
        except OSError:self.status.set('저장된 인증을 삭제할 수 없습니다. 다시 시도해 주세요.');return
        self.table.delete(*self.table.get_children());self.detail='';self.show_text('');self.status.set('관리자 인증을 해제했습니다.')
    def show_text(self,value):self.text.configure(state='normal');self.text.delete('1.0','end');self.text.insert('end',value);self.text.configure(state='disabled')
    def poll(self):
        if not self.alive:return
        try:
            generation,op,result,error=self.events.get_nowait()
            if generation!=self.generation:self.window.after(100,self.poll);return
            self.busy=False
            if error:self.status.set(str(error))
            elif op=='admin_list_errors':
                self.total=result['total'];self.table.delete(*self.table.get_children())
                for row in result['reports']:self.table.insert('',tk.END,iid=row['id'],values=(row['nickname'],{'pc':'PC','mobile':'모바일','tablet':'태블릿'}.get(row['device_type'],'—'),row['stop_reason']))
                self.status.set(f'전체 {self.total}건 · {self.offset//20+1}페이지 · 인증 유지 중')
            elif op=='admin_read_error':self.detail=json.dumps(result['report'],ensure_ascii=False,indent=2);self.show_text(self.detail);self.status.set('오류 상세 확인 완료')
            else:self.load()
        except queue.Empty:pass
        self.window.after(100,self.poll)
    def close(self):self.alive=False;self.key.set('');self.window.destroy()

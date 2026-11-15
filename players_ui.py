import tkinter as tk
from tkinter import ttk
from ui_controls import smooth_buttons,RoundScrollbar

class PlayersWindow:
    def __init__(self,parent,sync,on_ready=lambda:None):
        self.sync=sync;self.on_ready=on_ready;self.alive=True;self.last=None;self.editing=not sync.has_nickname()
        self.window=tk.Toplevel(parent);self.window.title('냐크로 · 사용중인 플레이어');self.window.configure(bg='#0c1220')
        w=min(760,max(560,parent.winfo_screenwidth()-48));h=min(660,max(470,parent.winfo_screenheight()-100));self.window.geometry(f'{w}x{h}+24+24');self.window.minsize(min(560,w),min(470,h));self.window.protocol('WM_DELETE_WINDOW',self.close)
        shell=ttk.Frame(self.window,padding=18);shell.pack(fill='both',expand=True)
        ttk.Label(shell,text='사용중인 플레이어',font=('맑은 고딕',20,'bold')).pack(anchor='w')
        ttk.Label(shell,text='닉네임을 저장하면 모든 냐크로 사용자에게 닉네임 · 모바일/PC · 실행 상태 · 콘텐츠 · 완료 횟수가 공개됩니다.',wraplength=690,style='Muted.TLabel').pack(fill='x',pady=(7,12))
        self.status=tk.StringVar();ttk.Label(shell,textvariable=self.status,wraplength=690).pack(fill='x',pady=6)
        self.form=ttk.Frame(shell);self.form.pack(fill='x');ttk.Label(self.form,text='처음 사용할 닉네임 (1~20자)').pack(anchor='w')
        self.name=tk.StringVar(value=sync.view()['nickname']);self.entry=ttk.Entry(self.form,textvariable=self.name);self.entry.pack(fill='x',pady=6)
        self.save=ttk.Button(self.form,text='닉네임 저장 · 목록에 공개',command=self.submit);self.save.pack(fill='x',pady=5);self.entry.bind('<Return>',lambda event:self.submit())
        self.controls=ttk.Frame(shell);self.controls.pack(fill='x',pady=5)
        self.rename=ttk.Button(self.controls,text='닉네임 변경',command=self.edit);self.rename.pack(side='left')
        ttk.Button(self.controls,text='새로 고침',command=sync.refresh).pack(side='left',padx=8)
        self.prev=ttk.Button(self.controls,text='이전',command=lambda:self.page(-100));self.prev.pack(side='right')
        self.next=ttk.Button(self.controls,text='다음',command=lambda:self.page(100));self.next.pack(side='right',padx=8)
        table=ttk.Frame(shell);table.pack(fill='both',expand=True,pady=8)
        style=ttk.Style(self.window);style.configure('Players.Treeview',background='#162136',fieldbackground='#162136',foreground='#edf2ff',rowheight=32);style.map('Players.Treeview',background=[('selected','#354e73')])
        self.table=ttk.Treeview(table,style='Players.Treeview',columns=('name','platform','state','content','count'),show='headings',height=7)
        for key,label,width in [('name','닉네임',170),('platform','사용 기기',80),('state','상태',90),('content','콘텐츠',85),('count','완료',80)]:self.table.heading(key,text=label);self.table.column(key,width=width,minwidth=55)
        scroll=RoundScrollbar(table,command=self.table.yview);scroll.pack(side='right',fill='y');self.table.configure(yscrollcommand=scroll.set);self.table.pack(fill='both',expand=True)
        self.page_label=tk.StringVar();ttk.Label(shell,textvariable=self.page_label,style='Muted.TLabel').pack(anchor='w')
        ttk.Label(shell,text='새 실행은 0판부터 계산합니다. 연결이 끊긴 사용자는 약 1분 후 목록에서 빠집니다.',wraplength=690,style='Muted.TLabel').pack(fill='x',pady=(5,0))
        smooth_buttons(self.window);self.refresh()
        if self.editing:self.entry.focus_set()
    def submit(self):
        try:self.sync.set_nickname(self.name.get())
        except ValueError as error:self.status.set(str(error));return
        self.editing=False;self.last=None;self.render();self.on_ready()
    def edit(self):self.editing=True;self.name.set(self.sync.view()['nickname']);self.last=None;self.render();self.entry.focus_set()
    def page(self,delta):self.sync.page(self.sync.view()['offset']+delta)
    def render(self):
        if not self.alive:return
        v=self.sync.view();snapshot=(v,self.editing)
        if snapshot!=self.last:
            self.last=snapshot;self.status.set(v['message'])
            if self.editing:self.form.pack(fill='x',before=self.controls)
            else:self.form.pack_forget()
            self.rename.configure(state='normal' if v['ready'] else 'disabled');self.prev.configure(state='normal' if v['offset']>0 else 'disabled');self.next.configure(state='normal' if v['offset']+100<v['total'] else 'disabled')
            self.table.delete(*self.table.get_children())
            for m in v['players']:
                status=('실행 중' if m['status']=='running' else '중지') if v['connected'] else '연결 확인 중'
                self.table.insert('',tk.END,iid=m['id'],values=(m['nickname']+(' (나)' if m['id']==v['member_id'] else ''),'모바일' if m['platform']=='mobile' else 'PC',status,m['content'] or '—',str(m['completed'])+'판'))
            self.page_label.set(f"{v['offset']//100+1}페이지 · 전체 {v['total']}명")
    def refresh(self):
        if not self.alive:return
        self.render();self.window.after(500,self.refresh)
    def close(self):self.alive=False;self.window.destroy()

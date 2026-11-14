"""Room controls. All rendering occurs on Tk's main thread."""
import tkinter as tk
from tkinter import ttk
from ui_controls import smooth_buttons, RoundScrollbar

class RoomWindow:
    def __init__(self,parent,sync):
        self.sync=sync;self.alive=True;self.last=None
        self.window=tk.Toplevel(parent);self.window.title('냐크로 · 함께보기');self.window.geometry('720x630');self.window.minsize(560,480);self.window.configure(bg='#0c1220')
        self.window.protocol('WM_DELETE_WINDOW',self.close)
        box=ttk.Frame(self.window,padding=18);box.pack(fill='both',expand=True)
        ttk.Label(box,text='함께보기',font=('맑은 고딕',20,'bold')).pack(anchor='w')
        ttk.Label(box,text='같은 방에서 닉네임 · 모바일/PC · 상태 · 이번 실행 완료 횟수를 공유합니다.\n방에 참여할 때부터 공유되며, 나가면 공유가 끝납니다.',wraplength=650,style='Muted.TLabel').pack(fill='x',pady=(6,12))
        self.status=tk.StringVar();ttk.Label(box,textvariable=self.status,wraplength=650).pack(fill='x',pady=6)
        self.code_label=tk.StringVar();ttk.Label(box,textvariable=self.code_label,font=('맑은 고딕',13,'bold')).pack(anchor='w',pady=5)
        self.form=ttk.Frame(box);self.form.pack(fill='x')
        ttk.Label(self.form,text='닉네임 (1~20자)').pack(anchor='w');self.name=tk.StringVar(value=sync.view()['nickname']);ttk.Entry(self.form,textvariable=self.name).pack(fill='x',pady=(4,8))
        ttk.Label(self.form,text='방 코드 (참여할 때 입력)').pack(anchor='w');self.code=tk.StringVar();ttk.Entry(self.form,textvariable=self.code).pack(fill='x',pady=(4,8))
        controls=ttk.Frame(self.form);controls.pack(fill='x')
        self.create=ttk.Button(controls,text='방 만들기',command=lambda:self.join(False));self.create.pack(side='left',expand=True,fill='x')
        self.join_button=ttk.Button(controls,text='코드로 참여',command=lambda:self.join(True));self.join_button.pack(side='left',expand=True,fill='x',padx=(8,0))
        self.joined=ttk.Frame(box)
        ttk.Button(self.joined,text='방 코드 복사',command=self.copy).pack(side='left')
        ttk.Button(self.joined,text='새로 고침',command=sync.refresh).pack(side='left',padx=8)
        self.leave=ttk.Button(self.joined,text='방 나가기',command=sync.leave);self.leave.pack(side='right')
        table=ttk.Frame(box);table.pack(fill='both',expand=True,pady=(12,5))
        style=ttk.Style(self.window);style.configure('Room.Treeview',background='#162136',fieldbackground='#162136',foreground='#edf2ff',rowheight=32);style.map('Room.Treeview',background=[('selected','#354e73')])
        self.table=ttk.Treeview(table,style='Room.Treeview',columns=('name','platform','state','content','count'),show='headings',height=8)
        for key,label,width in [('name','닉네임',155),('platform','사용 기기',75),('state','상태',95),('content','콘텐츠',75),('count','완료',75)]:
            self.table.heading(key,text=label);self.table.column(key,width=width,minwidth=55,stretch=True)
        scrollbar=RoundScrollbar(table,command=self.table.yview);scrollbar.pack(side='right',fill='y');self.table.configure(yscrollcommand=scrollbar.set);self.table.pack(fill='both',expand=True)
        ttk.Label(box,text='새 실행을 시작하면 0판부터 계산합니다. 연결이 끊기면 약 1분 후 오프라인으로 표시됩니다.',wraplength=650,style='Muted.TLabel').pack(fill='x')
        smooth_buttons(self.window);self.refresh()
    def join(self,existing):
        try:self.sync.join(self.name.get(),self.code.get() if existing else None)
        except ValueError as error:self.status.set(str(error))
    def copy(self):
        code=self.sync.view()['room_code']
        if code:self.window.clipboard_clear();self.window.clipboard_append(code);self.status.set('방 코드를 복사했습니다. 같은 방에 참여할 사람에게 전달해 주세요.')
    def refresh(self):
        if not self.alive:return
        value=self.sync.view()
        if value!=self.last:
            self.last=value;self.status.set(value['message']);self.code_label.set('방 코드  '+value['room_code'] if value['joined'] else '방을 만들거나 코드로 참여하세요.')
            if value['joined']:self.form.pack_forget();self.joined.pack(fill='x',before=self.table.master)
            else:self.joined.pack_forget();self.form.pack(fill='x',before=self.table.master)
            for button in (self.create,self.join_button,self.leave):button.configure(state='disabled' if value['busy'] else 'normal')
            selection=self.table.selection();self.table.delete(*self.table.get_children())
            for m in value['members']:
                status={'running':'실행 중','stopped':'중지','offline':'오프라인'}[m['status']] if value['connected'] else '연결 확인 중'
                self.table.insert('',tk.END,iid=m['id'],values=(m['nickname']+(' (나)' if m['id']==value['member_id'] else ''),'모바일' if m['platform']=='mobile' else 'PC',status,m['content'] or '—',str(m['completed'])+'판'))
            for item in selection:
                if self.table.exists(item):self.table.selection_add(item)
        self.window.after(500,self.refresh)
    def close(self):self.alive=False;self.window.destroy()

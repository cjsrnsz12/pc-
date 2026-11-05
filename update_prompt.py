"""Compact update decision window; long release notes live in a separate view."""
import tkinter as tk
from tkinter import ttk
from version import VERSION
from ui_controls import smooth_buttons
from dialog_layout import fit_dialog


class UpdatePrompt:
    def __init__(self,app,release=None):
        self.app=app;self.release=None;self.closed=False
        self.dialog=tk.Toplevel(app.root);self.dialog.title('새 버전 업데이트');self.dialog.configure(bg='#0c1220');self.dialog.transient(app.root)
        self.dialog.protocol('WM_DELETE_WINDOW',self.close)
        frame=ttk.Frame(self.dialog,padding=22);frame.pack(fill='both',expand=True)
        self.footer=ttk.Frame(frame);self.footer.pack(side='bottom',fill='x',pady=(16,0))
        self.primary=ttk.Button(self.footer,text='지금 업데이트',style='Start.TButton',state='disabled',command=self.install);self.primary.pack(side='left')
        self.details=ttk.Button(self.footer,text='업데이트 내용',state='disabled',command=self.open_details);self.details.pack(side='left',padx=8)
        ttk.Button(self.footer,text='나중에',command=self.close).pack(side='right')
        self.heading=ttk.Label(frame,text='새 버전 확인 중…',font=('맑은 고딕',19,'bold'));self.heading.pack(anchor='w',pady=(0,10))
        self.version=ttk.Label(frame,text='최신 버전 정보를 확인하고 있습니다.',foreground='#79b8ff');self.version.pack(anchor='w')
        self.status=tk.StringVar(value='새 버전이 있으면 이 창에서 바로 업데이트할 수 있습니다.')
        self.status_label=ttk.Label(frame,textvariable=self.status,wraplength=490);self.status_label.pack(anchor='w',pady=(15,8))
        self.hint_label=ttk.Label(frame,text='업데이트하면 앱이 다시 실행됩니다. 설정은 유지되고 매크로는 중지됩니다.',style='Muted.TLabel',wraplength=490);self.hint_label.pack(anchor='w')
        self.dialog.bind('<Configure>',self.wrap_body,add='+')
        smooth_buttons(self.dialog)
        if release:self.set_release(release)
        self.show()

    def wrap_body(self,event):
        if event.widget is self.dialog:
            width=max(240,event.width-44)
            self.heading.configure(wraplength=width);self.status_label.configure(wraplength=width);self.hint_label.configure(wraplength=width)

    def show(self):
        if self.closed:return
        if self.app.root.state()=='iconic':self.app.root.deiconify()
        self.dialog.deiconify();fit_dialog(self.app,self.dialog,(560,290),(460,250));self.dialog.lift()
        self.dialog.attributes('-topmost',True)
        self.app.root.after(1800,lambda:self.dialog.attributes('-topmost',False) if not self.closed else None)

    def set_loading(self):
        self.status.set('새 버전 확인 중… 잠시 기다려 주세요.');self.primary.configure(state='disabled')

    def set_release(self,release):
        if self.closed:return
        self.release=release;newer=release.get('is_new',True)
        self.heading.configure(text='새 버전으로 업데이트할까요?' if newer else '최신 버전을 사용 중입니다')
        self.version.configure(text=f"v{VERSION}  →  {release['version']}" if newer else '현재 버전 '+release['version'])
        self.status.set('지금 업데이트를 누르면 다운로드·설치·재실행까지 진행합니다.' if newer else '업데이트 내용에서 이번 버전의 변경 사항을 확인하세요.')
        self.primary.configure(text='지금 업데이트',state='normal' if newer else 'disabled',command=self.install)
        self.details.configure(state='normal')

    def set_check_error(self,error):
        self.status.set('확인 실패: '+str(error));self.primary.configure(text='다시 확인',state='normal',command=lambda:self.app.update_check(True))

    def set_no_release(self):
        self.heading.configure(text='새 배포 정보가 없습니다');self.primary.configure(text='다시 확인',state='normal',command=lambda:self.app.update_check(True))
        self.status.set('최신 배포 정보를 다시 확인해 주세요.')

    def install(self):
        if not self.release:return
        self.primary.configure(state='disabled');self.status.set('업데이트를 준비하고 있습니다…');self.dialog.update_idletasks()
        try:
            if self.app.update_from_prompt(self.release):self.close()
            else:self.primary.configure(state='normal');self.status.set('업데이트 창의 안내를 확인하고 다시 시도하세요.')
        except Exception as e:
            self.primary.configure(state='normal');self.status.set('업데이트 시작 실패: '+str(e));self.app.log(str(e))

    def open_details(self):
        if self.release:self.app.show_update(self.release);self.close()

    def close(self):
        if self.closed:return
        self.closed=True;self.dialog.destroy()

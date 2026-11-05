"""Dark, colored dropdown with a short nonblocking reveal animation."""
import time
import tkinter as tk

DIFFICULTY_COLORS={'입문':'#a084ff','어려움':'#ffc454','매우 어려움':'#ff6547','매우 어려움2':'#ff6547'}
PLAY_MODES=['솔로 플레이','파티 플레이 (3인 제한 · 우만) · 준비 중']

class SmoothChoice(tk.Frame):
    def __init__(self,parent,textvariable,values,colors=None,command=None,**kwargs):
        super().__init__(parent,bg='#263550',highlightthickness=1,highlightbackground='#455577',**kwargs)
        self.variable=textvariable;self.values=list(values);self.colors=colors or {};self.command=command
        self.disabled=False;self.popup=None;self.job=None
        self.label=tk.Label(self,textvariable=textvariable,bg='#263550',anchor='w',padx=10,pady=8,font=('맑은 고딕',10))
        self.label.pack(side='left',fill='both',expand=True)
        self.arrow=tk.Label(self,text='⌄',bg='#263550',fg='#b9cbea',padx=8);self.arrow.pack(side='right',fill='y')
        for w in (self,self.label,self.arrow):w.bind('<Button-1>',self.open)
        self.configure(takefocus=True);self.bind('<Return>',self.open);self.bind('<space>',self.open)
        self.trace=self.variable.trace_add('write',self.repaint)
        self.bind('<Destroy>',self.cleanup,add='+');self.repaint()

    def repaint(self,*_):
        self.label.configure(fg='#728098' if self.disabled else self.colors.get(self.variable.get(),'#edf2ff'))

    def configure(self,cnf=None,**kwargs):
        state=kwargs.pop('state',None)
        if state is not None:
            self.disabled=state=='disabled'
            if self.disabled:self.dismiss()
            self.repaint()
        return super().configure(cnf,**kwargs)

    config=configure

    def choose(self,value):
        if self.disabled:return
        self.variable.set(value);self.dismiss()
        if self.command:self.command()

    def open(self,event=None):
        if self.disabled:return
        if self.popup is not None:self.dismiss();return
        self.update_idletasks()
        popup=self.popup=tk.Toplevel(self);popup.withdraw();popup.overrideredirect(True)
        popup.configure(bg='#455577');popup.transient(self.winfo_toplevel())
        panel=tk.Frame(popup,bg='#111c30',padx=1,pady=1);panel.pack(fill='both',expand=True,padx=1,pady=1)
        for value in self.values:
            label=tk.Label(panel,text=('✓  ' if value==self.variable.get() else '    ')+value,anchor='w',bg='#111c30',fg=self.colors.get(value,'#edf2ff'),padx=10,pady=10,font=('맑은 고딕',10))
            label.pack(fill='x');label.bind('<Enter>',lambda e:e.widget.configure(bg='#293c58'));label.bind('<Leave>',lambda e:e.widget.configure(bg='#111c30'))
            label.bind('<Button-1>',lambda e,v=value:self.choose(v))
        popup.update_idletasks();width=max(self.winfo_width(),panel.winfo_reqwidth()+2);height=panel.winfo_reqheight()+2
        x=min(self.winfo_rootx(),max(0,self.winfo_screenwidth()-width));below=self.winfo_rooty()+self.winfo_height()
        y=below if below+height<self.winfo_screenheight()-40 else max(0,self.winfo_rooty()-height)
        popup.geometry(f'{width}x1+{x}+{y}');popup.deiconify();popup.lift();popup.grab_set();popup.focus_set()
        popup.bind('<Escape>',lambda _:self.dismiss());popup.bind('<FocusOut>',lambda _:self.after_idle(self.close_if_unfocused))
        popup.bind('<Button-1>',self.outside,add='+');started=time.monotonic()
        def tick():
            if self.popup is not popup:return
            t=min(1.,(time.monotonic()-started)/.16);ease=1-(1-t)**3
            popup.geometry(f'{width}x{max(1,round(height*ease))}+{x}+{y}')
            self.job=self.after(12,tick) if t<1 else None
        tick()

    def outside(self,event):
        if self.popup and not (0<=event.x_root-self.popup.winfo_rootx()<self.popup.winfo_width() and 0<=event.y_root-self.popup.winfo_rooty()<self.popup.winfo_height()):self.dismiss()

    def close_if_unfocused(self):
        if self.popup and self.popup.focus_displayof() is None:self.dismiss()

    def dismiss(self):
        if self.job:self.after_cancel(self.job);self.job=None
        if self.popup:
            popup=self.popup;self.popup=None
            try:popup.grab_release();popup.destroy()
            except tk.TclError:pass

    def cleanup(self,event):
        if event.widget is self:
            self.dismiss();self.variable.trace_remove('write',self.trace)

"""Dark controls with a drawn check mark and short, event-driven transitions."""
import itertools
import time
import tkinter as tk
from tkinter import ttk
from PIL import Image,ImageDraw,ImageTk

BG='#0c1220';TEXT='#edf2ff';ACCENT='#51dfb0'
_IDS=itertools.count()


def blend(a,b,t):
    a=tuple(int(a[i:i+2],16) for i in (1,3,5));b=tuple(int(b[i:i+2],16) for i in (1,3,5))
    return '#'+''.join(f'{round(x+(y-x)*t):02x}' for x,y in zip(a,b))


class SmoothCheckbutton(tk.Frame):
    def __init__(self,parent,text,variable,command=None,**kwargs):
        self.disabled=False;self.hover=0.;self.selected=float(bool(variable.get()));self.variable=variable;self.command=command
        self._job=None;self._hover_target=0.;self._select_target=self.selected
        super().__init__(parent,bg=BG,bd=0,highlightthickness=1,highlightbackground=BG,takefocus=True,**kwargs)
        scale=max(1.,float(self.tk.call('tk','scaling'))/(96/72))
        self.size=round(28*scale)
        self.icon=tk.Canvas(self,width=self.size,height=self.size,bg=BG,bd=0,highlightthickness=0)
        self.icon.pack(side='left')
        self.label=tk.Label(self,text=text,bg=BG,fg=TEXT,font=('맑은 고딕',10),bd=0,padx=5,activebackground=BG,activeforeground=TEXT)
        self.label.pack(side='left')
        self._image_id=self.icon.create_image(self.size/2,self.size/2)
        for widget in (self,self.icon,self.label):
            widget.bind('<Enter>',self._enter,add='+');widget.bind('<Leave>',self._leave,add='+')
            widget.bind('<Button-1>',self._click,add='+')
        self.bind('<space>',self._key,add='+');self.bind('<Return>',self._key,add='+')
        self.bind('<FocusIn>',lambda _:self.configure(highlightbackground='#426d8b'),add='+')
        self.bind('<FocusOut>',lambda _:self.configure(highlightbackground=BG),add='+')
        self._trace=variable.trace_add('write',lambda *_:self._animate(self._hover_target,float(bool(variable.get()))))
        self.bind('<Destroy>',self._destroy,add='+');self._draw()

    def _enter(self,_=None):
        if not self.disabled:self._animate(1.,float(bool(self.variable.get())))

    def _leave(self,event=None):
        # Ignore a leave caused by crossing between the icon and its label.
        x,y=self.winfo_pointerxy();inside=self.winfo_containing(x,y)
        if inside is not None and (inside is self or str(inside).startswith(str(self)+'.')):return
        self._animate(0.,float(bool(self.variable.get())))

    def _click(self,_=None):
        if not self.disabled:self.focus_set();self.invoke()
        return 'break'

    def _key(self,_=None):
        self.invoke();return 'break'

    def invoke(self):
        if self.disabled:return
        self.variable.set(not self.variable.get())
        if self.command:return self.command()

    def configure(self,cnf=None,**kwargs):
        if isinstance(cnf,dict):kwargs={**cnf,**kwargs};cnf=None
        state=kwargs.pop('state',None)
        if state is not None:
            self.disabled=state=='disabled'
            self.label.configure(fg='#8190aa' if self.disabled else TEXT)
            self.configure(cursor='' if self.disabled else 'hand2',takefocus=not self.disabled)
            self._animate(0. if self.disabled else self._hover_target,float(bool(self.variable.get())))
        return super().configure(cnf,**kwargs)

    config=configure

    def _animate(self,hover,selected):
        if self._job is not None:self.after_cancel(self._job);self._job=None
        self._hover_target=hover;self._select_target=selected
        start=time.monotonic();initial=(self.hover,self.selected)
        def tick():
            t=min(1.,(time.monotonic()-start)/.16);ease=1-(1-t)**3
            self.hover=initial[0]+(hover-initial[0])*ease;self.selected=initial[1]+(selected-initial[1])*ease
            self._draw()
            self._job=self.after(16,tick) if t<1 else None
        tick()

    def _draw(self):
        factor=4;s=self.size
        image=Image.new('RGB',(s*factor,s*factor),BG);draw=ImageDraw.Draw(image)
        width=s*(.63+.035*self.hover);left=(s-width)/2;right=left+width
        box=tuple(round(v*factor) for v in (left,left,right,right))
        accent='#53657c' if self.disabled else ACCENT
        fill=blend('#162136',accent,self.selected*.86)
        edge=blend('#62718d',accent,max(self.selected,self.hover*.75))
        draw.rounded_rectangle(box,radius=round(4*factor*s/28),fill=fill,outline=edge,width=max(1,round(1.4*factor*s/28)))
        # Reveal a ✓ along two connected segments; there are no crossed strokes.
        if self.selected>.001:
            points=[(s*.34,s*.50),(s*.46,s*.62),(s*.69,s*.37)]
            lengths=[((b[0]-a[0])**2+(b[1]-a[1])**2)**.5 for a,b in zip(points,points[1:])]
            remaining=sum(lengths)*self.selected;path=[points[0]]
            for a,b,length in zip(points,points[1:],lengths):
                amount=min(1.,remaining/length)
                path.append((a[0]+(b[0]-a[0])*amount,a[1]+(b[1]-a[1])*amount));remaining-=length
                if remaining<=0:break
            coords=[(round(x*factor),round(y*factor)) for x,y in path]
            stroke=max(2,round(2*factor*s/28));color='#b8c4d5' if self.disabled else '#072a21'
            draw.line(coords,fill=color,width=stroke,joint='curve')
            for x,y in coords:draw.ellipse((x-stroke/2,y-stroke/2,x+stroke/2,y+stroke/2),fill=color)
        self._image=ImageTk.PhotoImage(image.resize((s,s),Image.Resampling.LANCZOS),master=self.icon)
        self.icon.itemconfigure(self._image_id,image=self._image)

    def _destroy(self,event):
        if event.widget is not self:return
        if self._job is not None:self.after_cancel(self._job);self._job=None
        self.variable.trace_remove('write',self._trace)


class ButtonTransition:
    def __init__(self,widget):
        self.widget=widget;self.styles=ttk.Style(widget);self.job=None;self.value=0.
        base=widget.cget('style') or 'TButton'
        self.base=self.styles.lookup(base,'background') or '#263550'
        self.disabled=self.styles.lookup(base,'background',('disabled',)) or '#172239'
        self.target='#7cecc8' if 'Start.' in base else '#354b6e'
        self.style=f'Fade{next(_IDS)}.{base}'
        widget.configure(style=self.style)
        widget.bind('<Enter>',lambda _:self.animate(1.),add='+')
        widget.bind('<Leave>',lambda _:self.animate(0.),add='+')
        widget.bind('<Destroy>',self.destroy,add='+');self.paint()

    def paint(self):
        color=blend(self.base,self.target,self.value)
        self.styles.configure(self.style,background=color,bordercolor=color,lightcolor=color,darkcolor=color)
        self.styles.map(self.style,background=[('disabled',self.disabled),('pressed',color),('active',color),('!disabled',color)],
                        bordercolor=[('disabled',self.disabled),('!disabled',color)],lightcolor=[('!disabled',color)],darkcolor=[('!disabled',color)])

    def animate(self,target):
        if self.job is not None:self.widget.after_cancel(self.job);self.job=None
        start=time.monotonic();initial=self.value
        def tick():
            t=min(1.,(time.monotonic()-start)/.14);ease=1-(1-t)**3
            self.value=initial+(target-initial)*ease;self.paint()
            self.job=self.widget.after(16,tick) if t<1 else None
        tick()

    def destroy(self,event):
        if event.widget is self.widget and self.job is not None:self.widget.after_cancel(self.job);self.job=None


def smooth_buttons(parent):
    for child in parent.winfo_children():
        if isinstance(child,ttk.Button) and not hasattr(child,'_transition'):
            child._transition=ButtonTransition(child)
        smooth_buttons(child)

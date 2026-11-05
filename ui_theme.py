"""Game-launcher accents, an animated header and a code-drawn application icon."""
import math
import time
import tkinter as tk
from PIL import Image,ImageDraw,ImageTk,ImageFilter
from ui_controls import blend


def app_icon(size=256):
    scale=4;s=size*scale
    image=Image.new('RGBA',(s,s),(0,0,0,0));d=ImageDraw.Draw(image)
    d.rounded_rectangle((1,1,s-2,s-2),radius=s*.23,fill='#111a32',outline='#745bd0',width=max(2,round(s*.018)))
    glow=Image.new('RGBA',(s,s));g=ImageDraw.Draw(glow)
    g.ellipse((s*.14,s*.14,s*.86,s*.86),fill=(87,79,212,160));glow=glow.filter(ImageFilter.GaussianBlur(s*.09));image=Image.alpha_composite(image,glow);d=ImageDraw.Draw(image)
    diamond=[(s*.50,s*.15),(s*.84,s*.50),(s*.50,s*.85),(s*.16,s*.50)]
    d.line(diamond+[diamond[0]],fill='#72edcb',width=max(2,round(s*.025)),joint='curve')
    d.line([(s*.32,s*.65),(s*.50,s*.31),(s*.68,s*.65)],fill='#f5f6ff',width=max(2,round(s*.055)),joint='curve')
    d.line([(s*.40,s*.54),(s*.60,s*.54)],fill='#ac92ff',width=max(2,round(s*.04)))
    return image.resize((size,size),Image.Resampling.LANCZOS)


class LauncherHeader(tk.Canvas):
    def __init__(self,parent,version):
        super().__init__(parent,height=128,bg='#11182b',bd=0,highlightthickness=0)
        self.version=version;self._resize_job=None;self._tick_job=None;self._phase=time.monotonic();self._width=700
        self.bind('<Configure>',self.schedule);self.bind('<Destroy>',self.destroyed)
        self._tick_job=self.after(40,self.animate)

    def schedule(self,event):
        if self._resize_job:self.after_cancel(self._resize_job)
        self._width=max(400,event.width);self._resize_job=self.after(50,self.paint)

    def paint(self):
        self._resize_job=None;self._last_offset=0.;self.delete('all');w=self._width;h=128
        image=Image.new('RGB',(w,h));d=ImageDraw.Draw(image)
        for x in range(w):
            t=x/max(1,w-1)
            color=blend('#2c2153','#102b3a',t)
            d.line((x,0,x,h),fill=color)
        d.line((0,h-2,w,h-2),fill='#5b51a5',width=2)
        for x in range(w-230,w+60,52):d.line((x,0,x-100,h),fill='#343255',width=1)
        self._background=ImageTk.PhotoImage(image,master=self)
        self.create_image(0,0,anchor='nw',image=self._background)
        self.create_text(22,22,anchor='w',text='MABINOGI MOBILE  /  AUTOMATION',font=('맑은 고딕',8,'bold'),fill='#ac9fea')
        self.create_text(20,57,anchor='w',text='어비스 헬퍼',font=('맑은 고딕',25,'bold'),fill='#f3f6ff')
        self.create_text(23,96,anchor='w',text='화면을 읽고, 다음 모험으로.',font=('맑은 고딕',10),fill='#bac8e1')
        self.create_rectangle(w-154,87,w-20,112,fill='#1f334d',outline='#42628b')
        self.create_text(w-87,99,text='PC  •  v'+self.version,font=('맑은 고딕',9,'bold'),fill='#8ef3d4')
        self._orb_x=w-86
        self.create_oval(w-124,10,w-48,86,outline='#474073',width=1,tags='halo')
        self.create_polygon(w-86,17,w-56,47,w-86,77,w-116,47,fill='#27355b',outline='#74e8cd',width=2,tags='orb')
        self.create_text(w-86,47,text='✦',font=('Segoe UI Symbol',25),fill='#c0acff',tags='orb')
        self._stars=[]
        for i in range(5):
            x=w-225+i*43;y=18+(i*19)%52
            ident=self.create_oval(x,y,x+2,y+2,fill='#96c6d4',outline='')
            self._stars.append((ident,x,y,i))

    def animate(self):
        if self.winfo_viewable() and hasattr(self,'_stars'):
            t=time.monotonic()-self._phase
            offset=math.sin(t*.9)*2.7
            for item in self.find_withtag('orb'):
                # The group shifts only a few pixels without changing the layout.
                previous=getattr(self,'_last_offset',0.)
                self.move(item,0,offset-previous)
            self._last_offset=offset
            for ident,x,y,i in self._stars:
                dy=math.sin(t*.7+i)*3
                self.coords(ident,x,y+dy,x+2,y+dy+2)
        self._tick_job=self.after(33 if self.winfo_viewable() else 250,self.animate)

    def destroyed(self,event):
        if event.widget is not self:return
        for job in (self._resize_job,self._tick_job):
            if job:self.after_cancel(job)

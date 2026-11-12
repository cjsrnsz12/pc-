"""Game-launcher accents, an animated header and a code-drawn application icon."""
import math
import time
import tkinter as tk
from PIL import Image,ImageDraw,ImageTk,ImageFilter
from ui_controls import blend
from branding import APP_NAME,TAGLINE


def app_icon(size=256):
    scale=4;s=size*scale
    image=Image.new('RGBA',(s,s),(0,0,0,0));d=ImageDraw.Draw(image)
    d.rounded_rectangle((1,1,s-2,s-2),radius=s*.25,fill='#131d35',outline='#8b80cf',width=max(2,round(s*.018)))
    glow=Image.new('RGBA',(s,s));g=ImageDraw.Draw(glow)
    g.ellipse((s*.10,s*.08,s*.90,s*.94),fill=(106,91,208,145))
    image=Image.alpha_composite(image,glow.filter(ImageFilter.GaussianBlur(s*.09)));d=ImageDraw.Draw(image)
    # Cat silhouette stays legible at taskbar size. Shapes are antialiased below.
    d.polygon([(s*.22,s*.45),(s*.24,s*.20),(s*.43,s*.34)],fill='#b6a4ee')
    d.polygon([(s*.57,s*.34),(s*.76,s*.20),(s*.78,s*.45)],fill='#b6a4ee')
    d.ellipse((s*.21,s*.30,s*.79,s*.80),fill='#b6a4ee')
    d.polygon([(s*.27,s*.35),(s*.28,s*.26),(s*.36,s*.34)],fill='#526588')
    d.polygon([(s*.64,s*.34),(s*.72,s*.26),(s*.73,s*.35)],fill='#526588')
    for x in (.39,.61):d.ellipse((s*(x-.025),s*.49,s*(x+.025),s*.565),fill='#18253e')
    d.polygon([(s*.46,s*.59),(s*.54,s*.59),(s*.50,s*.64)],fill='#f7efff')
    d.arc((s*.40,s*.58,s*.50,s*.69),0,85,fill='#18253e',width=max(2,round(s*.012)))
    d.arc((s*.50,s*.58,s*.60,s*.69),95,180,fill='#18253e',width=max(2,round(s*.012)))
    d.ellipse((s*.68,s*.68,s*.89,s*.89),fill='#72e5c2',outline='#13223b',width=max(2,round(s*.014)))
    d.polygon([(s*.75,s*.73),(s*.75,s*.83),(s*.83,s*.78)],fill='#16352e')
    return image.resize((size,size),Image.Resampling.LANCZOS)


class LauncherHeader(tk.Canvas):
    def __init__(self,parent,version):
        super().__init__(parent,height=116,bg='#11182b',bd=0,highlightthickness=0)
        self.version=version;self._resize_job=None;self._tick_job=None;self._phase=time.monotonic();self._width=700
        self.bind('<Configure>',self.schedule);self.bind('<Destroy>',self.destroyed)
        self._tick_job=self.after(40,self.animate)

    def schedule(self,event):
        if self._resize_job:self.after_cancel(self._resize_job)
        self._width=max(400,event.width);self._resize_job=self.after(50,self.paint)

    def paint(self):
        self._resize_job=None;self._last_offset=0.;self.delete('all');w=self._width;h=116
        image=Image.new('RGB',(w,h));d=ImageDraw.Draw(image)
        for x in range(w):
            t=x/max(1,w-1)
            color=blend('#282342','#122c37',t)
            d.line((x,0,x,h),fill=color)
        d.line((0,h-2,w,h-2),fill='#5b51a5',width=2)
        for x in range(w-230,w+60,52):d.line((x,0,x-100,h),fill='#343255',width=1)
        self._background=ImageTk.PhotoImage(image,master=self)
        self.create_image(0,0,anchor='nw',image=self._background)
        self.create_text(24,19,anchor='w',text='NYACRO  /  PLAY COMPANION',font=('맑은 고딕',8,'bold'),fill='#b4a6e4')
        self.create_text(22,53,anchor='w',text=APP_NAME,font=('맑은 고딕',28,'bold'),fill='#f3f6ff')
        self.create_text(24,91,anchor='w',text=TAGLINE,font=('맑은 고딕',10),fill='#bdcbe1')
        self.create_rectangle(w-154,78,w-20,103,fill='#1f334d',outline='#42628b')
        self.create_text(w-87,91,text='PC  •  v'+self.version,font=('맑은 고딕',9,'bold'),fill='#8ef3d4')
        self._orb_x=w-86
        self._cat=ImageTk.PhotoImage(app_icon(64),master=self)
        self.create_image(w-86,37,image=self._cat,tags='orb')
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

"""Offline photo editor and sticker library inside Nyacro."""
from datetime import datetime
from io import BytesIO
import json
import os
from pathlib import Path
import queue
import shutil
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import zipfile
from PIL import Image, ImageTk
from emoticon_core import load_image, edit_sticker
from ui_controls import smooth_buttons, SmoothCheckbutton, RoundScrollbar

BG='#0c1220';SURFACE='#162136';TEXT='#edf2ff';MUTED='#9caccc'

class EmoticonWindow:
    def __init__(self,parent,base,data):
        self.base=Path(base)/'emoticons';self.data=Path(data)/'emoticons'
        self.data.mkdir(parents=True,exist_ok=True)
        self.pack=json.loads((self.base/'pack.json').read_text(encoding='utf-8'))
        self.window=tk.Toplevel(parent);self.window.title('냐크로 · 로컬 이모티콘 공방')
        self.window.geometry('820x760');self.window.minsize(710,650);self.window.configure(bg=BG)
        self.images=[];self.events=queue.Queue();self.busy=False;self.alive=True;self.result=None;self.font_path=None
        self.selected=tk.StringVar(value=self.pack[0]['name']);self.caption=tk.StringVar()
        self.remove_bg=tk.BooleanVar(value=False);self.outline=tk.BooleanVar(value=True);self.mirror=tk.BooleanVar(value=False)
        self.tolerance=tk.IntVar(value=30)
        self.status=tk.StringVar(value='인터넷·API 키 없이 이 PC에서 편집하고 저장합니다.')
        self.window.protocol('WM_DELETE_WINDOW',self.close)
        shell=ttk.Frame(self.window,padding=18);shell.pack(fill='both',expand=True)
        ttk.Label(shell,text='로컬 이모티콘 공방',font=('맑은 고딕',22,'bold')).pack(anchor='w')
        ttk.Label(shell,text='사진 불러오기 → 자르기·꾸미기 → PNG 저장',style='Muted.TLabel').pack(anchor='w',pady=(3,10))
        self.status_label=ttk.Label(shell,textvariable=self.status,wraplength=750,style='Muted.TLabel');self.status_label.pack(side='bottom',fill='x',pady=(8,0))
        notebook=ttk.Notebook(shell);notebook.pack(fill='both',expand=True)
        maker_page=ttk.Frame(notebook,padding=12);library_page=ttk.Frame(notebook,padding=12)
        notebook.add(maker_page,text='사진 편집');notebook.add(library_page,text='기본 8종 · 내 보관함')
        actions=ttk.Frame(maker_page);actions.pack(side='bottom',fill='x',pady=(8,0))
        scroll_area=ttk.Frame(maker_page);scroll_area.pack(fill='both',expand=True)
        canvas=tk.Canvas(scroll_area,bg=BG,highlightthickness=0)
        scrollbar=RoundScrollbar(scroll_area,command=canvas.yview);scrollbar.pack(side='right',fill='y')
        canvas.pack(side='left',fill='both',expand=True);canvas.configure(yscrollcommand=scrollbar.set)
        maker=ttk.Frame(canvas);item=canvas.create_window(0,0,anchor='nw',window=maker)
        maker.bind('<Configure>',lambda _:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(item,width=e.width))
        self.editor_canvas=canvas
        library_canvas=tk.Canvas(library_page,bg=BG,highlightthickness=0)
        library_scroll=RoundScrollbar(library_page,command=library_canvas.yview);library_scroll.pack(side='right',fill='y')
        library_canvas.pack(side='left',fill='both',expand=True);library_canvas.configure(yscrollcommand=library_scroll.set)
        self.library=ttk.Frame(library_canvas);library_item=library_canvas.create_window(0,0,anchor='nw',window=self.library)
        self.library.bind('<Configure>',lambda _:library_canvas.configure(scrollregion=library_canvas.bbox('all')))
        library_canvas.bind('<Configure>',lambda e:library_canvas.itemconfigure(library_item,width=e.width))
        def wheel(event):
            widget=event.widget
            while widget is not None:
                if widget is maker:canvas.yview_scroll(-int(event.delta/120),'units');return 'break'
                if widget is self.library:library_canvas.yview_scroll(-int(event.delta/120),'units');return 'break'
                widget=getattr(widget,'master',None)
        self.window.bind('<MouseWheel>',wheel,add='+')
        row=ttk.Frame(maker);row.pack(fill='x')
        choice=ttk.Combobox(row,textvariable=self.selected,values=[p['name'] for p in self.pack],state='readonly',width=12)
        choice.pack(side='left');choice.bind('<<ComboboxSelected>>',lambda _:self.choose_character())
        ttk.Button(row,text='사진·스크린샷 불러오기',command=self.pick_character).pack(side='left',padx=6)
        ttk.Button(row,text='사진 자르기',command=self.crop).pack(side='left')
        pictures=ttk.Frame(maker);pictures.pack(fill='x',pady=10)
        for label in ('원본 사진','편집 결과'):
            panel=ttk.Frame(pictures);panel.pack(side='left',expand=True)
            ttk.Label(panel,text=label).pack()
            preview=tk.Label(panel,bg=SURFACE,fg=TEXT);preview.pack()
            if label=='원본 사진':self.character_preview=preview
            else:self.result_preview=preview
        ttk.Label(maker,text='문구 (최대 40자 · 비우면 글자 없이 저장)').pack(anchor='w')
        ttk.Entry(maker,textvariable=self.caption).pack(fill='x',pady=(3,6))
        options=ttk.Frame(maker);options.pack(fill='x')
        for text,var in [('단색 배경 지우기',self.remove_bg),('흰 테두리',self.outline),('좌우 반전',self.mirror)]:
            SmoothCheckbutton(options,text=text,variable=var).pack(side='left',padx=(0,6))
        tolerance_row=ttk.Frame(maker);tolerance_row.pack(fill='x')
        ttk.Label(tolerance_row,text='배경 색상 허용 범위').pack(side='left')
        ttk.Scale(tolerance_row,from_=0,to=100,variable=self.tolerance,command=lambda v:self.tolerance.set(round(float(v)))).pack(side='left',fill='x',expand=True,padx=8)
        ttk.Label(tolerance_row,textvariable=self.tolerance,width=4).pack(side='left')
        ttk.Label(maker,text='배경 지우기는 가장자리와 비슷한 단색 부분에 적용됩니다. 복잡한 배경은 사진을 먼저 잘라 주세요.\n원본의 포즈·표정을 유지하며 새 그림으로 다시 그리지 않습니다.',style='Muted.TLabel',wraplength=700).pack(anchor='w',pady=(3,6))
        self.generate_button=ttk.Button(actions,text='로컬로 이모티콘 만들기',style='Start.TButton',command=self.make);self.generate_button.pack(side='left')
        self.save_button=ttk.Button(actions,text='PNG 다른 이름으로 저장',command=self.save_result,state='disabled');self.save_button.pack(side='left',padx=6)
        ttk.Button(actions,text='글꼴 선택',command=self.pick_font).pack(side='left')
        self.choose_character();self.preview(self.result_preview,Image.new('RGBA',(360,360)))
        self.draw_library();smooth_buttons(self.window);self.window.after(100,self.poll)

    def preview(self,label,image):
        image=image.copy();image.thumbnail((170,170),Image.Resampling.LANCZOS)
        background=Image.new('RGBA',(180,180),'#edf2ff')
        background.alpha_composite(image,((180-image.width)//2,(180-image.height)//2))
        photo=ImageTk.PhotoImage(background,master=self.window);label.configure(image=photo,width=180,height=180);label.image=photo

    def choose_character(self):
        item=next(p for p in self.pack if p['name']==self.selected.get())
        self.source=load_image(self.base/item['file']);self.original=self.source.copy()
        self.preview(self.character_preview,self.source)

    def pick_character(self):
        path=filedialog.askopenfilename(parent=self.window,title='편집할 사진·스크린샷',filetypes=[('사진','*.png *.jpg *.jpeg *.webp')])
        if path:
            try:
                self.source=load_image(path);self.original=self.source.copy();self.preview(self.character_preview,self.source)
                self.status.set('사진을 불러왔습니다. 필요한 부분을 잘라서 편집해 주세요.')
            except Exception as error:self.status.set(str(error))

    def pick_font(self):
        path=filedialog.askopenfilename(parent=self.window,title='문구에 사용할 한글 글꼴',filetypes=[('글꼴','*.ttf *.ttc *.otf')])
        if path:self.font_path=path;self.status.set('선택한 글꼴로 문구를 만듭니다.')

    def crop(self):
        window=tk.Toplevel(self.window);window.title('사용할 부분을 드래그하세요');window.configure(bg=BG)
        image=self.original.copy();image.thumbnail((720,560),Image.Resampling.LANCZOS)
        canvas=tk.Canvas(window,width=image.width,height=image.height,highlightthickness=0);canvas.pack()
        photo=ImageTk.PhotoImage(image,master=window);canvas.create_image(0,0,image=photo,anchor='nw');canvas.image=photo
        selection={'start':None,'rect':None,'box':None}
        def begin(e):
            x=max(0,min(image.width,e.x));y=max(0,min(image.height,e.y));selection['start']=(x,y);selection['box']=None
            if selection['rect']:canvas.delete(selection['rect'])
            selection['rect']=canvas.create_rectangle(x,y,x,y,outline='#51dfb0',width=3)
        def drag(e):
            if selection['start']:
                x,y=selection['start'];x2=max(0,min(image.width,e.x));y2=max(0,min(image.height,e.y))
                selection['box']=(min(x,x2),min(y,y2),max(x,x2),max(y,y2));canvas.coords(selection['rect'],*selection['box'])
        def apply():
            b=selection['box']
            if not b or b[2]-b[0]<10 or b[3]-b[1]<10:return
            sx=self.original.width/image.width;sy=self.original.height/image.height
            self.source=self.original.crop(tuple(round(v*(sx if i%2==0 else sy)) for i,v in enumerate(b)))
            self.preview(self.character_preview,self.source);window.destroy()
        canvas.bind('<ButtonPress-1>',begin);canvas.bind('<B1-Motion>',drag)
        ttk.Button(window,text='선택한 부분 사용',command=apply).pack(pady=8);smooth_buttons(window)

    def make(self):
        if self.busy:return
        options=dict(caption=self.caption.get(),remove_bg=self.remove_bg.get(),tolerance=self.tolerance.get(),mirror=self.mirror.get(),outline=self.outline.get(),font_path=self.font_path)
        source=self.source.copy();self.busy=True;self.generate_button.configure(state='disabled');self.status.set('이 PC에서 편집 중…')
        def work():
            try:
                raw=edit_sticker(source,**options)
                path=self.data/('이모티콘_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.png');path.write_bytes(raw)
                self.events.put(('ok',raw))
            except Exception as error:self.events.put(('error',str(error)))
        threading.Thread(target=work,daemon=True).start()

    def poll(self):
        if not self.alive:return
        try:
            while True:
                kind,value=self.events.get_nowait();self.busy=False;self.generate_button.configure(state='normal')
                if kind=='ok':
                    self.result=value;self.preview(self.result_preview,Image.open(BytesIO(value)).convert('RGBA'));self.save_button.configure(state='normal')
                    self.status.set('완료! 360×360 PNG로 보관함에 저장했습니다. 카카오톡에 이미지로 보내세요.');self.draw_library()
                else:self.status.set(value)
        except queue.Empty:pass
        self.window.after(100,self.poll)

    def save_result(self):
        if not self.result:return
        path=filedialog.asksaveasfilename(parent=self.window,title='이모티콘 저장',defaultextension='.png',initialfile='내_이모티콘.png',filetypes=[('PNG 이미지','*.png')])
        if path:
            try:Path(path).write_bytes(self.result);self.status.set('저장했습니다. 카카오톡 채팅창에 이 PNG를 끌어 넣어 전송하세요.')
            except OSError:self.status.set('저장하지 못했습니다. 다른 폴더를 선택해 주세요.')

    def draw_library(self):
        for child in self.library.winfo_children():child.destroy()
        self.images.clear()
        ttk.Label(self.library,text='눌러서 개별 저장 · 카카오톡에 이미지로 전송',style='Muted.TLabel').pack(anchor='w')
        grid=ttk.Frame(self.library);grid.pack(fill='x',pady=12)
        for i,item in enumerate(self.pack):
            image=load_image(self.base/item['file']); image.thumbnail((100,100),Image.Resampling.LANCZOS)
            photo=ImageTk.PhotoImage(image,master=self.window);self.images.append(photo)
            button=ttk.Button(grid,text=item['name']+' · '+item['caption'],image=photo,compound='top',command=lambda p=self.base/item['file']:self.export_one(p))
            button.grid(row=i//4,column=i%4,sticky='nsew',padx=4,pady=4);grid.columnconfigure(i%4,weight=1)
        ttk.Button(self.library,text='기본 8종 ZIP 저장',command=self.export_pack).pack(anchor='w')
        files=sorted(self.data.glob('*.png'),reverse=True)
        ttk.Label(self.library,text=f'내가 만든 이모티콘 {len(files)}개',font=('맑은 고딕',12,'bold')).pack(anchor='w',pady=(16,6))
        ttk.Button(self.library,text='내 보관함 폴더 열기',command=lambda:os.startfile(self.data)).pack(anchor='w')
        for path in files[:4]:ttk.Button(self.library,text=path.name,command=lambda p=path:self.export_one(p)).pack(anchor='w',pady=3)
        smooth_buttons(self.library)

    def export_one(self,path):
        target=filedialog.asksaveasfilename(parent=self.window,defaultextension='.png',initialfile=path.name,filetypes=[('PNG 이미지','*.png')])
        if target:
            try:shutil.copyfile(path,target);self.status.set('저장 완료 · 카카오톡 채팅창에 PNG를 끌어 넣어 보내세요.')
            except OSError:messagebox.showerror('저장 실패','다른 폴더를 선택해 주세요.',parent=self.window)

    def export_pack(self):
        target=filedialog.asksaveasfilename(parent=self.window,defaultextension='.zip',initialfile='냐크로_이모티콘_8종.zip',filetypes=[('ZIP','*.zip')])
        if target:
            try:
                with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
                    for item in self.pack:archive.write(self.base/item['file'],item['name']+'_'+item['caption'].replace('!','')+'.png')
            except OSError:messagebox.showerror('저장 실패','다른 폴더를 선택해 주세요.',parent=self.window)

    def close(self):
        if self.busy:
            self.status.set('편집 결과를 저장 중입니다. 끝난 뒤 창을 닫아 주세요.');return
        self.alive=False;self.window.destroy()

"""Emoticon workspace opened from Nyacro's main window."""
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
from emoticon_core import load_image, png_bytes, sticker_bytes, build_prompt, generate
from ui_controls import smooth_buttons

BG = '#0c1220'
SURFACE = '#162136'
TEXT = '#edf2ff'
MUTED = '#9caccc'


class EmoticonWindow:
    def __init__(self, parent, base, data):
        self.base = Path(base)/'emoticons'
        self.data = Path(data)/'emoticons'
        self.data.mkdir(parents=True, exist_ok=True)
        self.pack = json.loads((self.base/'pack.json').read_text(encoding='utf-8'))
        self.window = tk.Toplevel(parent)
        self.window.title('냐크로 · 이모티콘 만들기')
        self.window.geometry('850x850')
        self.window.minsize(710, 650)
        self.window.configure(bg=BG)
        self.images = []
        self.events = queue.Queue()
        self.busy = False
        self.alive = True
        self.character = None
        self.reference = load_image(self.base/'example.png')
        self.result = None
        self.key = tk.StringVar()
        self.selected = tk.StringVar(value=self.pack[0]['name'])
        self.caption = tk.StringVar(value='빼꼼')
        self.status = tk.StringVar(value='참고 이미지의 포즈와 표정을 내 캐릭터로 바꿔요.')
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        shell = ttk.Frame(self.window, padding=18); shell.pack(fill='both', expand=True)
        ttk.Label(shell, text='이모티콘 공방', font=('맑은 고딕', 22, 'bold')).pack(anchor='w')
        ttk.Label(shell, text='사진을 넣고 · 캐릭터를 골라 · 나만의 한 컷', style='Muted.TLabel').pack(anchor='w', pady=(3, 12))
        notebook = ttk.Notebook(shell); notebook.pack(fill='both', expand=True)
        maker = ttk.Frame(notebook, padding=12); library = ttk.Frame(notebook, padding=12)
        notebook.add(maker, text='사진으로 만들기'); notebook.add(library, text='기본 8종 · 내 보관함')
        row = ttk.Frame(maker); row.pack(fill='x')
        ttk.Label(row, text='캐릭터').pack(side='left')
        choice = ttk.Combobox(row, textvariable=self.selected, values=[p['name'] for p in self.pack], state='readonly', width=13)
        choice.pack(side='left', padx=8); choice.bind('<<ComboboxSelected>>', lambda _:self.choose_character())
        ttk.Button(row, text='내 캐릭터 사진', command=self.pick_character).pack(side='left')
        pictures = ttk.Frame(maker); pictures.pack(fill='x', pady=10)
        self.character_preview = tk.Label(pictures, bg=SURFACE, fg=TEXT); self.character_preview.pack(side='left', expand=True)
        self.reference_preview = tk.Label(pictures, bg=SURFACE, fg=TEXT); self.reference_preview.pack(side='left', expand=True)
        self.result_preview = tk.Label(pictures, bg=SURFACE, fg=TEXT, text='생성 결과', width=23, height=11); self.result_preview.pack(side='left', expand=True)
        tools = ttk.Frame(maker); tools.pack(fill='x')
        ttk.Button(tools, text='참고 사진·스크린샷 넣기', command=self.pick_reference).pack(side='left')
        ttk.Button(tools, text='참고 이미지 자르기', command=self.crop).pack(side='left', padx=6)
        ttk.Label(maker, text='문구 (비우면 글자 없이 생성)').pack(anchor='w', pady=(12, 2))
        ttk.Entry(maker, textvariable=self.caption).pack(fill='x')
        ttk.Label(maker, text='추가 요청 (선택)').pack(anchor='w', pady=(8, 2))
        self.note = tk.Text(maker, height=2, bg=SURFACE, fg=TEXT, insertbackground=TEXT, wrap='word', relief='flat')
        self.note.pack(fill='x'); self.note.insert('1.0', '귀엽게, 원래 머리색과 의상을 유지해줘')
        settings = ttk.LabelFrame(maker, text='AI 연결', padding=8); settings.pack(fill='x', pady=10)
        ttk.Entry(settings, textvariable=self.key, show='●').pack(fill='x')
        ttk.Label(settings, text='OpenAI API 키 · 이 창을 닫으면 삭제돼요.\n생성할 때 두 사진이 OpenAI로 전송되며 API 사용료가 발생할 수 있어요.', style='Muted.TLabel', wraplength=680).pack(anchor='w', pady=(4, 0))
        actions = ttk.Frame(maker); actions.pack(fill='x')
        self.generate_button = ttk.Button(actions, text='포즈 인식 · 이모티콘 생성', command=self.make); self.generate_button.pack(side='left')
        self.save_button = ttk.Button(actions, text='결과 다른 이름으로 저장', command=self.save_result, state='disabled'); self.save_button.pack(side='left', padx=6)
        ttk.Label(maker, textvariable=self.status, wraplength=680, style='Muted.TLabel').pack(anchor='w', pady=8)
        ttk.Label(shell, text='카카오톡에는 이미지로 보내세요. 공식 이모티콘 목록에는 자동 등록되지 않아요.', style='Muted.TLabel', wraplength=780).pack(anchor='w', pady=(10, 0))
        self.library = library
        self.choose_character(); self.preview(self.reference_preview, self.reference)
        self.draw_library()
        smooth_buttons(self.window)
        self.window.after(150, self.poll)

    def preview(self, label, image):
        image = image.copy(); image.thumbnail((180, 180), Image.Resampling.LANCZOS)
        background = Image.new('RGBA', (184, 184), '#edf2ff')
        background.alpha_composite(image, ((184-image.width)//2, (184-image.height)//2))
        photo = ImageTk.PhotoImage(background, master=self.window); label.configure(image=photo, text='', width=184, height=184); label.image = photo

    def choose_character(self):
        item = next(p for p in self.pack if p['name']==self.selected.get())
        self.character = load_image(self.base/item['file']); self.description = item['description']
        self.preview(self.character_preview, self.character)

    def pick_character(self):
        path = filedialog.askopenfilename(parent=self.window, title='변환할 내 캐릭터 사진', filetypes=[('사진', '*.png *.jpg *.jpeg *.webp')])
        if path:
            try:
                self.character = load_image(path); self.description = 'The character in image 1; preserve all visible identity details.'
                self.preview(self.character_preview, self.character)
            except Exception as e: self.status.set(str(e))

    def pick_reference(self):
        path = filedialog.askopenfilename(parent=self.window, title='따라 할 포즈·표정 사진', filetypes=[('사진', '*.png *.jpg *.jpeg *.webp')])
        if path:
            try: self.reference = load_image(path); self.preview(self.reference_preview, self.reference)
            except Exception as e: self.status.set(str(e))

    def crop(self):
        window = tk.Toplevel(self.window); window.title('마우스로 이모티콘 부분을 드래그하세요'); window.configure(bg=BG)
        image = self.reference.copy(); image.thumbnail((720, 600), Image.Resampling.LANCZOS)
        canvas = tk.Canvas(window, width=image.width, height=image.height, highlightthickness=0); canvas.pack()
        photo = ImageTk.PhotoImage(image, master=window); canvas.create_image(0, 0, image=photo, anchor='nw'); canvas.image=photo
        selection = {'start':None, 'rect':None, 'box':None}
        def begin(e):
            selection['start']=(max(0,min(image.width,e.x)),max(0,min(image.height,e.y)))
            if selection['rect']:canvas.delete(selection['rect'])
            selection['rect']=canvas.create_rectangle(e.x,e.y,e.x,e.y,outline='#51dfb0',width=3)
        def drag(e):
            if selection['start']:
                x,y=selection['start']; x2=max(0,min(image.width,e.x));y2=max(0,min(image.height,e.y))
                selection['box']=(min(x,x2),min(y,y2),max(x,x2),max(y,y2));canvas.coords(selection['rect'],*selection['box'])
        def apply():
            b=selection['box']
            if not b or b[2]-b[0]<10 or b[3]-b[1]<10:return
            sx=self.reference.width/image.width;sy=self.reference.height/image.height
            self.reference=self.reference.crop(tuple(round(v*(sx if i%2==0 else sy)) for i,v in enumerate(b)))
            self.preview(self.reference_preview,self.reference);window.destroy()
        canvas.bind('<ButtonPress-1>',begin);canvas.bind('<B1-Motion>',drag)
        ttk.Button(window,text='이 부분 사용',command=apply).pack(pady=8)
        smooth_buttons(window)

    def make(self):
        if self.busy:return
        if not self.key.get().strip():self.status.set('AI 연결 칸에 OpenAI API 키를 입력해 주세요. 기본 8종은 키 없이 저장할 수 있어요.');return
        self.busy=True; self.generate_button.configure(state='disabled'); self.status.set('참고 이미지의 포즈를 읽고 그리는 중… 잠시 기다려 주세요.')
        key=self.key.get(); character=self.character.copy(); reference=self.reference.copy()
        prompt=build_prompt(self.description,self.caption.get(),self.note.get('1.0','end'))
        def work():
            try:
                raw=generate(key,character,reference,prompt)
                path=self.data/('이모티콘_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.png');path.write_bytes(raw)
                self.events.put(('ok',path,raw))
            except Exception as error:self.events.put(('error',str(error),None))
        threading.Thread(target=work,daemon=True).start()

    def poll(self):
        if not self.alive:return
        try:
            while True:
                kind,value,raw=self.events.get_nowait();self.busy=False;self.generate_button.configure(state='normal')
                if kind=='ok':
                    self.result=raw;self.preview(self.result_preview,Image.open(BytesIO(raw)).convert('RGBA'));self.save_button.configure(state='normal')
                    self.status.set('완료! 360×360 PNG로 내 보관함에 저장했어요.');self.draw_library()
                else:self.status.set(value)
        except queue.Empty:pass
        self.window.after(150,self.poll)

    def save_result(self):
        if self.result:
            path=filedialog.asksaveasfilename(parent=self.window,title='이모티콘 저장',defaultextension='.png',initialfile='내_이모티콘.png',filetypes=[('PNG 이미지','*.png')])
            if path:
                try:Path(path).write_bytes(self.result);self.status.set('저장했어요. 카카오톡 채팅창에 이 PNG를 끌어 넣어 전송하세요.')
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
            self.status.set('생성이 진행 중입니다. 결과 저장이 끝나면 창을 닫아 주세요.');return
        self.key.set('');self.alive=False;self.window.destroy()
